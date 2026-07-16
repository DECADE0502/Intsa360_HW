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
from typing import Any
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
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
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


def _remote_sha(cwd: Path, remote_url: str, branch: str) -> str | None:
    reference = f"refs/heads/{branch}"
    completed = _run_git(cwd, "ls-remote", "--heads", remote_url, reference)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise RuntimeError(f"remote returned multiple values for {reference}")
    sha, separator, actual = lines[0].partition("\t")
    if not separator or actual != reference or len(sha) != 40:
        raise RuntimeError(f"remote returned an invalid value for {reference}")
    return sha.lower()


def _assert_same_snapshot(expected: Path, actual: Path) -> None:
    expected_tree = _run_git(expected, "rev-parse", "HEAD^{tree}").stdout.strip().lower()
    actual_tree = _run_git(actual, "rev-parse", "HEAD^{tree}").stdout.strip().lower()
    if actual_tree != expected_tree:
        raise RuntimeError("remote OTA snapshot tree does not match the staged snapshot")


def _clone_branch(remote_url: str, branch: str, target: Path) -> None:
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


def _configure_snapshot(repository: Path, source_repo: Path) -> None:
    _run_git(repository, "init")
    name = _run_git(source_repo, "config", "user.name", check=False).stdout.strip() or "Insta360 OTA Publisher"
    email = (
        _run_git(source_repo, "config", "user.email", check=False).stdout.strip()
        or "ota-publisher@localhost.invalid"
    )
    _run_git(repository, "config", "user.name", name)
    _run_git(repository, "config", "user.email", email)


def push_snapshot(
    snapshot_repo: Path,
    remote_url: str,
    branch: str,
    *,
    expected_remote_sha: str | None,
) -> str:
    reference = f"refs/heads/{branch}"
    lease = f"--force-with-lease={reference}:{expected_remote_sha or ''}"
    completed = _run_git(
        snapshot_repo,
        "push",
        lease,
        remote_url,
        f"HEAD:{reference}",
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"OTA publish lease rejected or push failed: {detail}")
    published = _remote_sha(snapshot_repo, remote_url, branch)
    local = _run_git(snapshot_repo, "rev-parse", "HEAD").stdout.strip().lower()
    if published != local:
        raise RuntimeError("remote OTA branch does not point at the staged snapshot")
    return local


def _cache_busted(url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["published"] = str(time.time_ns())
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _verify_public_manifest(url: str, expected: bytes, attempts: int = 12) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                _cache_busted(url),
                headers={"User-Agent": "Insta360-HWAgent-GitPublisher/1", "Cache-Control": "no-cache"},
            )
            with urlopen(request, timeout=15.0) as response:
                actual = response.read(len(expected) + 1)
            if actual == expected:
                return
            last_error = RuntimeError("public stable manifest bytes do not match the local signed manifest")
        except Exception as exc:  # Network errors are retried before publication is reported.
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(1 + attempt, 5))
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
    source_revision = _run_git(source, "rev-parse", "HEAD").stdout.strip().lower()
    remote_main = _remote_sha(source, remote_url, "main")
    if remote_main != source_revision:
        raise ValueError("release revision must already be the remote main head")
    verified = verify_bundle(bundle, public_key)
    version = str(verified["version"])
    revision = str(verified["revision"]).lower()
    if revision != source_revision:
        raise ValueError("release bundle revision does not match the source head")
    _assert_channel_urls(bundle, repository, branch, version)

    observed_sha = _remote_sha(source, remote_url, branch)
    with temporary_workspace() as temporary:
        current: Path | None = None
        previous_version: str | None = None
        if observed_sha:
            current = temporary / "current"
            _clone_branch(remote_url, branch, current)
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
        snapshot.mkdir()
        _configure_snapshot(snapshot, source)
        if current is not None and previous_version is not None:
            _copy_previous_version(current, snapshot, previous_version)
        _copy_bundle(bundle, snapshot / "versions" / version, version)
        stable = snapshot / "channel" / "stable"
        stable.mkdir(parents=True)
        shutil.copy2(bundle / V3_MANIFEST_NAME, stable / V3_MANIFEST_NAME)
        shutil.copy2(bundle / LEGACY_MANIFEST_NAME, stable / LEGACY_MANIFEST_NAME)
        _run_git(snapshot, "add", ".")
        _run_git(snapshot, "commit", "-m", f"Publish Insta360_HW {version}")
        commit = push_snapshot(
            snapshot,
            remote_url,
            branch,
            expected_remote_sha=observed_sha,
        )
        verified_clone = temporary / "verified"
        _clone_branch(remote_url, branch, verified_clone)
        _assert_same_snapshot(snapshot, verified_clone)
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
    parser = argparse.ArgumentParser(description="Publish a signed OTA snapshot using only Git push.")
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
