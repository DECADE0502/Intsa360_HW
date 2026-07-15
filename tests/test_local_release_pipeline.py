from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.backend.lifecycle_v3_archive import REQUIRED_RUNTIME_FILES
from app.backend.lifecycle_v3_contract import verify_signed_manifest
from app.backend.release_manifest import ReleaseManifest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_TOOL_PATH = ROOT / "scripts" / "release" / "release_bundle.py"


def _load_release_tool():
    spec = importlib.util.spec_from_file_location("release_bundle", RELEASE_TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_key_pair(private_path: Path, public_path: Path) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
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
    return key


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
            path.write_bytes((relative + "\n").encode("utf-8"))


def test_local_bundle_is_deterministic_signed_and_has_a_legacy_setup_bridge(tmp_path: Path) -> None:
    release_tool = _load_release_tool()
    version = "0.4.0"
    revision = "a" * 40
    private_key = tmp_path / "keys" / "update_private_key.pem"
    public_key = tmp_path / "keys" / "update_public_key.pem"
    _write_key_pair(private_key, public_key)
    runtime = tmp_path / "runtime"
    _write_runtime(runtime, public_key, version, revision)
    setup = tmp_path / "Insta360_HW_Setup.exe"
    setup.write_bytes(b"signed setup fixture")
    notice = {
        "title": "0.4.0",
        "summary": "切换到原子生命周期。",
        "highlights": ["本地构建", "签名更新"],
        "compatibility": "0.3.3 必须通过 Setup 升级。",
    }
    published_at = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)

    first = release_tool.build_bundle(
        runtime_root=runtime,
        setup_path=setup,
        output_dir=tmp_path / "bundle-a",
        private_key_path=private_key,
        public_key_path=public_key,
        version=version,
        revision=revision,
        repository="DECADE0502/Intsa360_HW",
        notice=notice,
        published_at=published_at,
        source_date_epoch=1_783_756_800,
    )
    second = release_tool.build_bundle(
        runtime_root=runtime,
        setup_path=setup,
        output_dir=tmp_path / "bundle-b",
        private_key_path=private_key,
        public_key_path=public_key,
        version=version,
        revision=revision,
        repository="DECADE0502/Intsa360_HW",
        notice=notice,
        published_at=published_at,
        source_date_epoch=1_783_756_800,
    )

    runtime_name = f"Insta360_HW_Runtime_{version}.zip"
    assert (first / runtime_name).read_bytes() == (second / runtime_name).read_bytes()
    with zipfile.ZipFile(first / runtime_name) as archive:
        assert "VERSION" in archive.namelist()
        assert not any(name.startswith("HWAgent_release/") for name in archive.namelist())

    signed_raw = json.loads((first / "update-manifest-v3.json").read_text(encoding="utf-8"))
    signed = verify_signed_manifest(signed_raw, public_key)
    assert signed.version == version
    assert signed.revision == revision
    assert signed.min_updater_version == version
    assets = {asset.name: asset for asset in signed.assets}
    assert assets[runtime_name].sha256 == hashlib.sha256((first / runtime_name).read_bytes()).hexdigest()
    assert assets["Insta360_HW_Setup.exe"].sha256 == hashlib.sha256(setup.read_bytes()).hexdigest()

    bridge = json.loads((first / "update-manifest.json").read_text(encoding="utf-8"))
    legacy = ReleaseManifest.parse(bridge)
    assert bridge["schema"] == 2
    assert bridge["minimum_launcher_version"] == version
    assert bridge["assets"]["setup"]["name"] == "Insta360_HW_Setup.exe"
    assert legacy.runtime.name == f"Insta360_HW_runtime_v{version}.zip"
    assert (first / legacy.runtime.name).read_bytes() == (first / runtime_name).read_bytes()
    assert "Setup" in bridge["notice"]["compatibility"]

    verified = release_tool.verify_bundle(first, public_key, version, revision)
    assert verified["version"] == version
    assert verified["revision"] == revision
    assert verified["artifact_count"] == 5


def test_local_bundle_rejects_a_private_key_that_does_not_match_the_runtime_anchor(tmp_path: Path) -> None:
    release_tool = _load_release_tool()
    version = "0.4.0"
    revision = "b" * 40
    private_key = tmp_path / "trusted" / "private.pem"
    public_key = tmp_path / "trusted" / "public.pem"
    _write_key_pair(private_key, public_key)
    wrong_private = tmp_path / "wrong" / "private.pem"
    wrong_public = tmp_path / "wrong" / "public.pem"
    _write_key_pair(wrong_private, wrong_public)
    runtime = tmp_path / "runtime"
    _write_runtime(runtime, public_key, version, revision)
    setup = tmp_path / "Insta360_HW_Setup.exe"
    setup.write_bytes(b"setup")

    with pytest.raises(ValueError, match="does not match"):
        release_tool.build_bundle(
            runtime_root=runtime,
            setup_path=setup,
            output_dir=tmp_path / "bundle",
            private_key_path=wrong_private,
            public_key_path=public_key,
            version=version,
            revision=revision,
            repository="DECADE0502/Intsa360_HW",
            notice={"highlights": ["test"]},
            published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            source_date_epoch=1_783_756_800,
        )


def test_signing_key_verification_accepts_only_the_trusted_pair(tmp_path: Path) -> None:
    release_tool = _load_release_tool()
    private_key = tmp_path / "trusted" / "private.pem"
    public_key = tmp_path / "trusted" / "public.pem"
    _write_key_pair(private_key, public_key)
    wrong_private = tmp_path / "wrong" / "private.pem"
    wrong_public = tmp_path / "wrong" / "public.pem"
    _write_key_pair(wrong_private, wrong_public)

    fingerprint = release_tool.verify_signing_key(private_key, public_key)

    assert len(fingerprint) == 64
    assert all(character in "0123456789abcdef" for character in fingerprint)
    with pytest.raises(ValueError, match="does not match"):
        release_tool.verify_signing_key(wrong_private, public_key)


def test_release_entrypoint_treats_key_generation_as_bootstrap_only() -> None:
    script = (ROOT / "scripts" / "build_release_bundle.ps1").read_text(encoding="utf-8")

    assert "verify-key" in script
    assert "bootstrap-only" in script
    assert "secure backup" in script


def test_release_verifier_retries_transient_windows_temp_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_tool = _load_release_tool()
    original = release_tool.shutil.rmtree
    attempts = 0

    def flaky_rmtree(path, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(145, "directory not empty")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(release_tool.shutil, "rmtree", flaky_rmtree)
    with release_tool.temporary_workspace(parent=tmp_path) as workspace:
        (workspace / "probe.txt").write_text("probe", encoding="utf-8")

    assert attempts == 2
    assert not workspace.exists()


def test_release_orchestration_builds_locally_and_github_only_validates_uploaded_assets() -> None:
    local_build = (ROOT / "scripts" / "build_release_bundle.ps1").read_text(encoding="utf-8")
    runtime_build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "release_bundle.py" in local_build
    assert "update-manifest-v3.json" in local_build
    assert "schema = 3" in runtime_build
    assert 'layout = "runtime-v3"' in runtime_build
    assert "BundleDir" in publisher
    assert "build_installer.ps1" not in publisher
    assert "workflow_dispatch" in publisher
    assert "validation_id" in publisher
    assert "npm ci" not in workflow
    assert "choco install" not in workflow
    assert "build_installer.ps1" not in workflow
    assert "release_bundle.py verify" in workflow
    assert "gh release edit" in workflow


def test_release_orchestration_keeps_embedded_python_from_mutating_the_runtime() -> None:
    script = (ROOT / "scripts" / "build_release_bundle.ps1").read_text(encoding="utf-8")
    build_call = "& $EmbeddedPython -B $ReleaseTool build"
    verify_call = "& $EmbeddedPython -B $ReleaseTool verify"
    final_assertion = "Assert-NoRuntimeCacheArtifacts -RuntimeRoot $RuntimeRoot"

    assert build_call in script
    assert verify_call in script
    assert "function Assert-NoRuntimeCacheArtifacts" in script
    assert script.rindex(final_assertion) > script.index(verify_call)


def test_runtime_zip_rejects_python_cache_artifacts(tmp_path: Path) -> None:
    release_tool = _load_release_tool()
    runtime = tmp_path / "runtime"
    cache = runtime / "runtime" / "python" / "Lib" / "site-packages" / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-311.pyc").write_bytes(b"cached")
    target = tmp_path / "runtime.zip"

    with pytest.raises(ValueError, match="Python cache artifact"):
        release_tool.write_runtime_zip(runtime, target, 1_783_756_800)

    assert not target.exists()


def test_release_workflow_never_interpolates_dispatch_inputs_into_privileged_shell() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "RELEASE_TAG: ${{ inputs.tag }}" in workflow
    assert "RELEASE_REVISION: ${{ inputs.revision }}" in workflow
    assert "RELEASE_ID: ${{ inputs.release_id }}" in workflow
    assert "VALIDATION_ID: ${{ inputs.validation_id }}" in workflow
    assert '[[ "$RELEASE_REVISION" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[[ "$RELEASE_ID" =~ ^[1-9][0-9]*$ ]]' in workflow
    assert '"${{ inputs.revision }}"' not in workflow
    assert '"${{ inputs.tag }}"' not in workflow
    assert "releases/${{ inputs.release_id }}" not in workflow


def test_frontend_release_build_does_not_reinstall_dependencies_on_every_run() -> None:
    script = (ROOT / "scripts" / "build_frontend.ps1").read_text(encoding="utf-8")

    assert "node_modules" in script
    assert "npm ci" in script
    assert "npm install" not in script
