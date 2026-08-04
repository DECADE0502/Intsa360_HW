from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.release_manifest import compare_versions, parse_version  # noqa: E402
from scripts.release.release_bundle import (  # noqa: E402
    CHECKSUMS_NAME,
    LEGACY_MANIFEST_NAME,
    SETUP_NAME,
    V3_MANIFEST_NAME,
    temporary_workspace,
    verify_bundle,
)


DEFAULT_BRANCH = "ota"
DEFAULT_REPOSITORY = "DECADE0502/Intsa360_HW"


def _run_git(
    cwd: Path,
    *arguments: str,
    check: bool = True,
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    if extra_environment:
        environment.update(extra_environment)
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    if check and completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _transport_environment(source_repo: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    ssh_command = _run_git(
        source_repo, "config", "--local", "--get", "core.sshCommand", check=False
    ).stdout.strip()
    ssh_variant = _run_git(
        source_repo, "config", "--local", "--get", "ssh.variant", check=False
    ).stdout.strip()
    if ssh_command:
        environment["GIT_SSH_COMMAND"] = ssh_command
    if ssh_variant:
        environment["GIT_SSH_VARIANT"] = ssh_variant
    return environment


def _remote_sha(
    cwd: Path,
    remote_url: str,
    branch: str,
    transport_environment: Mapping[str, str] | None = None,
) -> str | None:
    reference = f"refs/heads/{branch}"
    completed = _run_git(
        cwd,
        "ls-remote",
        "--heads",
        remote_url,
        reference,
        extra_environment=transport_environment,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise RuntimeError(f"remote returned multiple values for {reference}")
    sha, separator, actual = lines[0].partition("\t")
    if not separator or actual != reference or len(sha) != 40:
        raise RuntimeError(f"remote returned an invalid value for {reference}")
    return sha.lower()


def _progress(message: str) -> None:
    print(f"[OTA] {message}", flush=True)


def _clone_branch(
    remote_url: str,
    branch: str,
    target: Path,
    transport_environment: Mapping[str, str] | None = None,
) -> None:
    # A failed Windows clone can leave a partial .git directory behind. The
    # target is always publisher-owned temporary state, so remove that stale
    # checkout before asking Git to create a fresh one.
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        target.parent,
        "clone",
        "--depth",
        "1",
        "--branch",
        branch,
        "--single-branch",
        remote_url,
        str(target),
        extra_environment=transport_environment,
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"OTA manifest is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"OTA manifest must be a JSON object: {path}")
    return value


def _bundle_names(version: str) -> tuple[str, ...]:
    return (
        f"Insta360_HW_Runtime_{version}.zip",
        f"Insta360_HW_runtime_v{version}.zip",
        SETUP_NAME,
        V3_MANIFEST_NAME,
        LEGACY_MANIFEST_NAME,
        CHECKSUMS_NAME,
    )


def _assert_channel_urls(bundle: Path, repository: str, branch: str, version: str) -> None:
    base = f"https://raw.githubusercontent.com/{repository}/{branch}/versions/{version}"
    signed = _read_manifest(bundle / V3_MANIFEST_NAME)
    signed_urls = {
        str(asset.get("name")): str(asset.get("url"))
        for asset in signed.get("assets", [])
        if isinstance(asset, dict)
    }
    expected_signed = {
        f"Insta360_HW_Runtime_{version}.zip": f"{base}/Insta360_HW_Runtime_{version}.zip",
        SETUP_NAME: f"{base}/{SETUP_NAME}",
    }
    if signed_urls != expected_signed:
        raise ValueError("signed bundle asset URLs do not target the Git OTA channel")
    legacy = _read_manifest(bundle / LEGACY_MANIFEST_NAME)
    assets = legacy.get("assets")
    if not isinstance(assets, dict):
        raise ValueError("legacy bundle manifest has no assets")
    expected_legacy = {
        "runtime": (f"Insta360_HW_runtime_v{version}.zip", f"{base}/Insta360_HW_runtime_v{version}.zip"),
        "setup": (SETUP_NAME, f"{base}/{SETUP_NAME}"),
    }
    for kind, (name, url) in expected_legacy.items():
        asset = assets.get(kind)
        if not isinstance(asset, dict) or asset.get("name") != name or asset.get("url") != url:
            raise ValueError(f"legacy {kind} URL does not target the Git OTA channel")


def _copy_bundle(bundle: Path, destination: Path, version: str) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in _bundle_names(version):
        source = bundle / name
        if not source.is_file():
            raise ValueError(f"release bundle is missing {name}")
        shutil.copy2(source, destination / name)


def _copy_previous_version(current: Path, snapshot: Path, version: str) -> None:
    parse_version(version)
    source = current / "versions" / version
    if not source.is_dir():
        raise ValueError(f"current OTA channel is missing stable version {version}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("current OTA channel contains a symbolic link")
    target = snapshot / "versions" / version
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def _source_identity(source_repo: Path) -> tuple[str, str]:
    name = _run_git(source_repo, "config", "user.name", check=False).stdout.strip()
    email = _run_git(source_repo, "config", "user.email", check=False).stdout.strip()
    return name or "Insta360 OTA Publisher", email or "ota-publisher@localhost.invalid"


def _configure_snapshot(repository: Path) -> None:
    _run_git(repository, "init")


def push_snapshot(
    snapshot_repo: Path,
    remote_url: str,
    branch: str,
    *,
    expected_remote_sha: str | None,
    transport_environment: Mapping[str, str] | None = None,
) -> str:
    reference = f"refs/heads/{branch}"
    lease = f"--force-with-lease={reference}:{expected_remote_sha or ''}"
    completed = _run_git(
        snapshot_repo,
        "send-pack",
        lease,
        remote_url,
        f"HEAD:{reference}",
        check=False,
        extra_environment=transport_environment,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"OTA publish lease rejected or send-pack failed: {detail}")
    published = _remote_sha(snapshot_repo, remote_url, branch, transport_environment)
    local = _run_git(snapshot_repo, "rev-parse", "HEAD").stdout.strip().lower()
    if published != local:
        raise RuntimeError("remote OTA branch does not point at the staged snapshot")
    return local


def _cache_busted(url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["published"] = str(time.time_ns())
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _verify_public_manifest(url: str, expected: bytes, attempts: int = 5) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        _progress(f"Verifying public manifest ({attempt + 1}/{attempts})...")
        try:
            request = Request(
                _cache_busted(url),
                headers={"User-Agent": "Insta360-HWAgent-GitPublisher/1", "Cache-Control": "no-cache"},
            )
            with urlopen(request, timeout=5.0) as response:
                actual = response.read(len(expected) + 1)
            if actual == expected:
                _progress("Public manifest is available and byte-identical.")
                return
            last_error = RuntimeError("public stable manifest bytes do not match the local signed manifest")
        except Exception as exc:  # Network errors are retried before publication is reported.
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(1 + attempt, 3))
    raise RuntimeError(f"public OTA manifest verification failed: {last_error}")


def publish_bundle(
    *,
    bundle_dir: Path,
    public_key_path: Path,
    source_repo: Path,
    remote_url: str,
    repository: str = DEFAULT_REPOSITORY,
    branch: str = DEFAULT_BRANCH,
    verify_public: bool = False,
) -> dict[str, Any]:
    bundle = bundle_dir.resolve()
    public_key = public_key_path.resolve()
    source = source_repo.resolve()
    if _run_git(source, "status", "--porcelain", "--untracked-files=normal").stdout.strip():
        raise ValueError("publishing requires a clean source worktree")
    _progress("Checking source revision and destination refs...")
    transport = _transport_environment(source)
    source_revision = _run_git(source, "rev-parse", "HEAD").stdout.strip().lower()
    remote_main = _remote_sha(source, remote_url, "main", transport)
    if remote_main != source_revision:
        raise ValueError("release revision must already be the remote main head")
    _progress("Verifying signed release bundle...")
    verified = verify_bundle(bundle, public_key)
    version = str(verified["version"])
    revision = str(verified["revision"]).lower()
    if revision != source_revision:
        raise ValueError("release bundle revision does not match the source head")
    _assert_channel_urls(bundle, repository, branch, version)

    observed_sha = _remote_sha(source, remote_url, branch, transport)
    with temporary_workspace() as temporary:
        current: Path | None = None
        previous_version: str | None = None
        if observed_sha:
            _progress("Reading the current OTA snapshot for retention and version checks...")
            current = temporary / "current"
            _clone_branch(remote_url, branch, current, transport)
            if _run_git(current, "rev-parse", "HEAD").stdout.strip().lower() != observed_sha:
                raise RuntimeError("OTA branch changed while preparing the release")
            current_manifest = _read_manifest(current / "channel" / "stable" / V3_MANIFEST_NAME)
            previous_version = str(current_manifest.get("version") or "")
            parse_version(previous_version)
            order = compare_versions(version, previous_version)
            if order < 0:
                raise ValueError("refusing to publish an OTA version older than the current stable version")
            if order == 0:
                current_bundle = current / "versions" / version
                if any(
                    not (current_bundle / name).is_file()
                    or _sha256(current_bundle / name) != _sha256(bundle / name)
                    for name in _bundle_names(version)
                ):
                    raise ValueError("refusing to replace an already published version with different bytes")
                if verify_public:
                    _verify_public_manifest(
                        f"https://raw.githubusercontent.com/{repository}/{branch}/channel/stable/{V3_MANIFEST_NAME}",
                        (bundle / V3_MANIFEST_NAME).read_bytes(),
                    )
                retained = sorted(path.name for path in (current / "versions").iterdir() if path.is_dir())
                return {
                    "version": version,
                    "revision": revision,
                    "branch": branch,
                    "commit": observed_sha,
                    "retained_versions": retained,
                    "published": False,
                }

        snapshot = temporary / "snapshot"
        _progress("Staging the current and previous runtime snapshots...")
        snapshot.mkdir()
        _configure_snapshot(snapshot)
        if current is not None and previous_version is not None:
            _copy_previous_version(current, snapshot, previous_version)
        _copy_bundle(bundle, snapshot / "versions" / version, version)
        stable = snapshot / "channel" / "stable"
        stable.mkdir(parents=True)
        shutil.copy2(bundle / V3_MANIFEST_NAME, stable / V3_MANIFEST_NAME)
        shutil.copy2(bundle / LEGACY_MANIFEST_NAME, stable / LEGACY_MANIFEST_NAME)
        _run_git(snapshot, "add", ".")
        author_name, author_email = _source_identity(source)
        _run_git(
            snapshot,
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            f"Publish Insta360_HW {version}",
        )
        _progress("Sending the staged snapshot with an explicit lease...")
        commit = push_snapshot(
            snapshot,
            remote_url,
            branch,
            expected_remote_sha=observed_sha,
            transport_environment=transport,
        )
        _progress(f"Remote OTA ref now points to {commit[:12]}.")
        if verify_public:
            _verify_public_manifest(
                f"https://raw.githubusercontent.com/{repository}/{branch}/channel/stable/{V3_MANIFEST_NAME}",
                (bundle / V3_MANIFEST_NAME).read_bytes(),
            )
        retained = sorted(path.name for path in (snapshot / "versions").iterdir() if path.is_dir())
        return {
            "version": version,
            "revision": revision,
            "branch": branch,
            "commit": commit,
            "retained_versions": retained,
            "published": True,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a signed OTA snapshot using only Git send-pack.")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, default=ROOT)
    parser.add_argument("--remote-url")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--verify-public", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    remote_url = arguments.remote_url
    if not remote_url:
        remote_url = _run_git(arguments.source_repo, "remote", "get-url", "--push", "origin").stdout.strip()
    result = publish_bundle(
        bundle_dir=arguments.bundle_dir,
        public_key_path=arguments.public_key,
        source_repo=arguments.source_repo,
        remote_url=remote_url,
        repository=arguments.repository,
        branch=arguments.branch,
        verify_public=arguments.verify_public,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
