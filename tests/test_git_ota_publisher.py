from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.backend.lifecycle_v3_archive import REQUIRED_RUNTIME_FILES


ROOT = Path(__file__).resolve().parents[1]
RELEASE_TOOL_PATH = ROOT / "scripts" / "release" / "release_bundle.py"
PUBLISHER_PATH = ROOT / "scripts" / "release" / "git_ota.py"


def _load_module(path: Path, name: str):
    assert path.is_file(), f"missing implementation: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _git_bytes(cwd: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
    ).stdout


def _write_key_pair(private_path: Path, public_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _write_runtime(root: Path, public_key: Path, version: str, revision: str) -> None:
    for relative in REQUIRED_RUNTIME_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "config/update_public_key.pem":
            path.write_bytes(public_key.read_bytes())
        elif relative == "VERSION":
            path.write_text(version + "\n", encoding="utf-8")
        elif relative == "REVISION":
            path.write_text(revision + "\n", encoding="utf-8")
        elif relative == "install_manifest.json":
            path.write_text(
                json.dumps(
                    {
                        "schema": 3,
                        "product": "Insta360_HW",
                        "version": version,
                        "revision": revision,
                        "build_kind": "published",
                        "layout": "runtime-v3",
                    }
                ),
                encoding="utf-8",
            )
        else:
            path.write_bytes(f"{version}:{relative}\n".encode())


def _bundle(
    tmp_path: Path,
    version: str,
    revision: str,
    public_key: Path,
    private_key: Path,
) -> Path:
    release_tool = _load_module(RELEASE_TOOL_PATH, f"release_bundle_{version.replace('.', '_')}")
    runtime = tmp_path / f"runtime-{version}"
    _write_runtime(runtime, public_key, version, revision)
    setup = tmp_path / "setup" / version / "Insta360_HW_Setup.exe"
    setup.parent.mkdir(parents=True)
    setup.write_bytes(f"setup {version}".encode())
    return release_tool.build_bundle(
        runtime_root=runtime,
        setup_path=setup,
        output_dir=tmp_path / f"bundle-{version}",
        private_key_path=private_key,
        public_key_path=public_key,
        version=version,
        revision=revision,
        repository="owner/repo",
        asset_base_url=(
            "https://raw.githubusercontent.com/owner/repo/"
            f"ota/versions/{version}"
        ),
        notice={"highlights": [version]},
        published_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        source_date_epoch=1_784_160_000,
    )


@pytest.fixture
def repositories(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    source.mkdir()
    _git(source, "init")
    (source / "README.md").write_text("source\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(
        source,
        "-c",
        "user.name=OTA Test",
        "-c",
        "user.email=ota@example.invalid",
        "commit",
        "-m",
        "initial",
    )
    _git(source, "branch", "-M", "main")
    remote.mkdir()
    _git(remote, "init", "--bare")
    _git(source, "push", str(remote), "main:main")
    return source, remote


def _channel_tree(tmp_path: Path, remote: Path) -> Path:
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", "--branch", "ota", "--single-branch", str(remote), str(checkout))
    return checkout


def _snapshot(path: Path, value: str) -> None:
    path.mkdir()
    _git(path, "init")
    (path / "value.txt").write_text(value, encoding="utf-8")
    _git(path, "add", ".")
    _git(
        path,
        "-c",
        "user.name=OTA Test",
        "-c",
        "user.email=ota@example.invalid",
        "commit",
        "-m",
        value,
    )


def test_first_publish_creates_verified_parentless_channel(
    tmp_path: Path, repositories: tuple[Path, Path]
) -> None:
    publisher = _load_module(PUBLISHER_PATH, "git_ota_first")
    source, remote = repositories
    private_key = tmp_path / "keys" / "private.pem"
    public_key = tmp_path / "keys" / "public.pem"
    _write_key_pair(private_key, public_key)
    bundle = _bundle(tmp_path, "0.4.2", _git(source, "rev-parse", "HEAD"), public_key, private_key)

    result = publisher.publish_bundle(
        bundle_dir=bundle,
        public_key_path=public_key,
        source_repo=source,
        remote_url=str(remote),
        repository="owner/repo",
    )

    checkout = _channel_tree(tmp_path, remote)
    assert result["version"] == "0.4.2"
    assert result["retained_versions"] == ["0.4.2"]
    assert _git_bytes(checkout, "show", "HEAD:channel/stable/update-manifest-v3.json") == (
        bundle / "update-manifest-v3.json"
    ).read_bytes()
    assert sorted(path.name for path in (checkout / "versions").iterdir()) == ["0.4.2"]
    assert len(_git(checkout, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 1


def test_successive_publish_keeps_only_current_and_previous(
    tmp_path: Path, repositories: tuple[Path, Path]
) -> None:
    publisher = _load_module(PUBLISHER_PATH, "git_ota_retention")
    source, remote = repositories
    private_key = tmp_path / "keys" / "private.pem"
    public_key = tmp_path / "keys" / "public.pem"
    _write_key_pair(private_key, public_key)
    revision = _git(source, "rev-parse", "HEAD")

    for version in ("0.4.2", "0.4.3", "0.4.4"):
        publisher.publish_bundle(
            bundle_dir=_bundle(tmp_path, version, revision, public_key, private_key),
            public_key_path=public_key,
            source_repo=source,
            remote_url=str(remote),
            repository="owner/repo",
        )

    checkout = _channel_tree(tmp_path, remote)
    assert sorted(path.name for path in (checkout / "versions").iterdir()) == ["0.4.3", "0.4.4"]
    stable = json.loads((checkout / "channel/stable/update-manifest-v3.json").read_text(encoding="utf-8"))
    assert stable["version"] == "0.4.4"
    assert len(_git(checkout, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 1


def test_push_snapshot_rejects_a_stale_remote_lease(
    tmp_path: Path, repositories: tuple[Path, Path]
) -> None:
    publisher = _load_module(PUBLISHER_PATH, "git_ota_lease")
    _source, remote = repositories
    first = tmp_path / "first"
    _snapshot(first, "first")
    publisher.push_snapshot(first, str(remote), "ota", expected_remote_sha=None)
    stale_sha = _git(first, "rev-parse", "HEAD")

    second = tmp_path / "second"
    _snapshot(second, "second")
    publisher.push_snapshot(second, str(remote), "ota", expected_remote_sha=stale_sha)

    third = tmp_path / "third"
    _snapshot(third, "third")

    with pytest.raises(RuntimeError, match="lease"):
        publisher.push_snapshot(third, str(remote), "ota", expected_remote_sha=stale_sha)


def test_source_local_ssh_transport_is_forwarded_to_snapshot_git(
    tmp_path: Path, repositories: tuple[Path, Path]
) -> None:
    publisher = _load_module(PUBLISHER_PATH, "git_ota_transport")
    source, _remote = repositories
    command = f'ssh -i "{tmp_path / "test identity"}" -o IdentitiesOnly=yes'
    _git(source, "config", "--local", "core.sshCommand", command)

    environment = publisher._transport_environment(source)

    assert environment == {"GIT_SSH_COMMAND": command}
