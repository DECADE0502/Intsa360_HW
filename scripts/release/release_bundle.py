from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from typing import Any, Mapping
import uuid
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.backend.lifecycle_v3_archive import (  # noqa: E402
    REQUIRED_RUNTIME_FILES,
    safe_extract,
    validate_payload,
)
from app.backend.lifecycle_v3_contract import (  # noqa: E402
    canonical_manifest_payload,
    verify_signed_manifest,
)
from app.backend.release_manifest import ReleaseManifest  # noqa: E402


PRODUCT = "Insta360_HW"
V3_MANIFEST_NAME = "update-manifest-v3.json"
LEGACY_MANIFEST_NAME = "update-manifest.json"
CHECKSUMS_NAME = "SHA256SUMS.txt"
SETUP_NAME = "Insta360_HW_Setup.exe"
DEFAULT_MIN_UPDATER_VERSION = "0.4.0"


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"release signing private key is invalid: {path}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("release signing private key must be Ed25519")
    return key


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"release signing public key is invalid: {path}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("release signing public key must be Ed25519")
    return key


def _public_der(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def initialize_signing_key(private_key_path: Path, public_key_path: Path) -> None:
    if private_key_path.exists() or public_key_path.exists():
        raise FileExistsError("refusing to replace an existing release signing key")
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    private_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_key_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def verify_signing_key(private_key_path: Path, public_key_path: Path) -> str:
    private_key = _load_private_key(private_key_path)
    public_key = _load_public_key(public_key_path)
    trusted_der = _public_der(public_key)
    if _public_der(private_key.public_key()) != trusted_der:
        raise ValueError("release signing private key does not match the trusted public key")
    return hashlib.sha256(trusted_der).hexdigest()


def _assert_identity(runtime_root: Path, version: str, revision: str) -> None:
    for relative in REQUIRED_RUNTIME_FILES:
        if not (runtime_root / relative).is_file():
            raise ValueError(f"runtime payload is incomplete; missing {relative}")
    if (runtime_root / "VERSION").read_text(encoding="utf-8-sig").strip() != version:
        raise ValueError("runtime VERSION does not match the requested release")
    if (runtime_root / "REVISION").read_text(encoding="utf-8-sig").strip().lower() != revision.lower():
        raise ValueError("runtime REVISION does not match the requested release")
    try:
        identity = json.loads((runtime_root / "install_manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime install manifest is invalid") from exc
    expected = {
        "schema": 3,
        "product": PRODUCT,
        "version": version,
        "revision": revision.lower(),
        "build_kind": "published",
        "layout": "runtime-v3",
    }
    actual = {
        "schema": identity.get("schema"),
        "product": identity.get("product"),
        "version": identity.get("version"),
        "revision": str(identity.get("revision") or "").lower(),
        "build_kind": identity.get("build_kind"),
        "layout": identity.get("layout"),
    }
    if actual != expected:
        raise ValueError("runtime install manifest does not identify the requested published V3 release")


def _is_reparse_point(path: Path) -> bool:
    value = getattr(path.lstat(), "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(value & marker)


def _assert_no_python_cache_artifacts(root: Path) -> None:
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.suffix.casefold() == ".pyc" or any(
            part.casefold() == "__pycache__" for part in relative.parts
        ):
            raise ValueError(f"runtime payload contains Python cache artifact: {relative.as_posix()}")


def _zip_timestamp(source_date_epoch: int) -> tuple[int, int, int, int, int, int]:
    moment = datetime.fromtimestamp(source_date_epoch, tz=timezone.utc)
    if moment.year < 1980:
        moment = datetime(1980, 1, 1, tzinfo=timezone.utc)
    return moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second - moment.second % 2


def write_runtime_zip(runtime_root: Path, target: Path, source_date_epoch: int) -> None:
    root = runtime_root.resolve()
    _assert_no_python_cache_artifacts(root)
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() or _is_reparse_point(path):
            raise ValueError(f"runtime payload contains a reparse point: {path}")
        if path.is_file():
            files.append(path)
    if not files:
        raise ValueError("runtime payload is empty")
    target.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _zip_timestamp(source_date_epoch)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=timestamp)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits |= 0x800
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _asset(path: Path, url: str) -> dict[str, Any]:
    return {
        "name": path.name,
        "url": url,
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _legacy_asset(asset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": asset["name"],
        "url": asset["url"],
        "sha256": asset["sha256"],
        "size_bytes": asset["size"],
    }


def _published_at(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("published_at must include a timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _replace_directory(staging: Path, target: Path) -> None:
    backup = target.with_name(f".{target.name}.{uuid.uuid4().hex}.previous")
    moved_old = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_old = True
        os.replace(staging, target)
    except Exception:
        if moved_old and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


@contextmanager
def temporary_workspace(*, parent: Path | None = None):
    path = Path(tempfile.mkdtemp(prefix="insta360-release-verify-", dir=parent))
    body_failed = False
    try:
        yield path
    except BaseException:
        body_failed = True
        raise
    finally:
        cleanup_error: OSError | None = None
        for attempt in range(8):
            try:
                shutil.rmtree(path)
                cleanup_error = None
                break
            except FileNotFoundError:
                cleanup_error = None
                break
            except OSError as exc:
                cleanup_error = exc
                time.sleep(0.05 * (attempt + 1))
        if cleanup_error is not None:
            if body_failed:
                warnings.warn(f"release verifier could not clean temporary workspace {path}: {cleanup_error}")
            else:
                raise cleanup_error


def build_bundle(
    *,
    runtime_root: Path,
    setup_path: Path,
    output_dir: Path,
    private_key_path: Path,
    public_key_path: Path,
    version: str,
    revision: str,
    repository: str,
    notice: Mapping[str, Any],
    published_at: datetime,
    source_date_epoch: int,
    min_updater_version: str = DEFAULT_MIN_UPDATER_VERSION,
) -> Path:
    runtime_root = runtime_root.resolve()
    setup_path = setup_path.resolve()
    output_dir = output_dir.resolve()
    private_key_path = private_key_path.resolve()
    public_key_path = public_key_path.resolve()
    if not setup_path.is_file() or setup_path.name != SETUP_NAME:
        raise ValueError(f"setup package must be named {SETUP_NAME}")
    if len(revision) != 40 or any(character not in "0123456789abcdefABCDEF" for character in revision):
        raise ValueError("release revision must be a full 40-character git SHA")
    _assert_identity(runtime_root, version, revision)
    private_key = _load_private_key(private_key_path)
    public_key = _load_public_key(public_key_path)
    if _public_der(private_key.public_key()) != _public_der(public_key):
        raise ValueError("release signing private key does not match the trusted public key")
    runtime_anchor = _load_public_key(runtime_root / "config" / "update_public_key.pem")
    if _public_der(runtime_anchor) != _public_der(public_key):
        raise ValueError("runtime trust anchor does not match the release public key")

    staging = output_dir.with_name(f".{output_dir.name}.{uuid.uuid4().hex}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        runtime_name = f"Insta360_HW_Runtime_{version}.zip"
        legacy_runtime_name = f"Insta360_HW_runtime_v{version}.zip"
        runtime_zip = staging / runtime_name
        write_runtime_zip(runtime_root, runtime_zip, source_date_epoch)
        legacy_runtime_zip = staging / legacy_runtime_name
        shutil.copyfile(runtime_zip, legacy_runtime_zip)
        setup_copy = staging / SETUP_NAME
        shutil.copyfile(setup_path, setup_copy)
        release_base = f"https://github.com/{repository}/releases/download/v{version}"
        runtime_asset = _asset(runtime_zip, f"{release_base}/{runtime_name}")
        legacy_runtime_asset = _asset(legacy_runtime_zip, f"{release_base}/{legacy_runtime_name}")
        setup_asset = _asset(setup_copy, f"{release_base}/{SETUP_NAME}")
        highlights = [str(item) for item in notice.get("highlights", []) if str(item).strip()]
        signed_manifest: dict[str, Any] = {
            "schema_version": 3,
            "version": version,
            "revision": revision.lower(),
            "build_kind": "published",
            "published_at": _published_at(published_at),
            "min_updater_version": min_updater_version,
            "assets": [runtime_asset, setup_asset],
            "changelog": highlights,
            "signature": "pending",
        }
        signature = private_key.sign(canonical_manifest_payload(signed_manifest))
        signed_manifest["signature"] = "ed25519:" + base64.b64encode(signature).decode("ascii")
        (staging / V3_MANIFEST_NAME).write_bytes(_json_bytes(signed_manifest))
        verify_signed_manifest(signed_manifest, public_key_path)

        compatibility = str(notice.get("compatibility") or "")
        if "Setup" not in compatibility:
            compatibility = (compatibility + " 0.3.3 用户必须通过 Setup 升级。 ").strip()
        legacy_manifest = {
            "schema": 2,
            "product": PRODUCT,
            "version": version,
            "revision": revision.lower(),
            "published_at": _published_at(published_at),
            "channel": "stable",
            "minimum_launcher_version": min_updater_version,
            "assets": {
                "runtime": _legacy_asset(legacy_runtime_asset),
                "setup": _legacy_asset(setup_asset),
            },
            "notice": {
                "title": str(notice.get("title") or f"Insta360_HW {version}"),
                "summary": str(notice.get("summary") or f"Insta360_HW {version}"),
                "highlights": highlights,
                "compatibility": compatibility,
            },
        }
        (staging / LEGACY_MANIFEST_NAME).write_bytes(_json_bytes(legacy_manifest))

        artifact_names = [
            runtime_name,
            legacy_runtime_name,
            SETUP_NAME,
            V3_MANIFEST_NAME,
            LEGACY_MANIFEST_NAME,
        ]
        checksum_lines = [f"{_sha256(staging / name)}  {name}" for name in sorted(artifact_names)]
        (staging / CHECKSUMS_NAME).write_text("\n".join(checksum_lines) + "\n", encoding="ascii")
        verify_bundle(staging, public_key_path, version, revision)
        _replace_directory(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output_dir


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"release JSON is invalid: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"release JSON must be an object: {path.name}")
    return value


def verify_bundle(
    bundle_dir: Path,
    public_key_path: Path,
    expected_version: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    bundle = bundle_dir.resolve()
    raw = _read_json(bundle / V3_MANIFEST_NAME)
    manifest = verify_signed_manifest(raw, public_key_path)
    if expected_version and manifest.version != expected_version:
        raise ValueError("signed manifest version does not match the expected release")
    if expected_revision and manifest.revision.lower() != expected_revision.lower():
        raise ValueError("signed manifest revision does not match the expected release")
    runtime_name = f"Insta360_HW_Runtime_{manifest.version}.zip"
    assets = {asset.name: asset for asset in manifest.assets}
    if set(assets) != {runtime_name, SETUP_NAME}:
        raise ValueError("signed manifest must contain exactly the runtime and Setup assets")
    for name, asset in assets.items():
        path = bundle / name
        if not path.is_file() or path.stat().st_size != asset.size or _sha256(path) != asset.sha256.lower():
            raise ValueError(f"release asset integrity check failed: {name}")
        if str(asset.url).rsplit("/", 1)[-1] != name:
            raise ValueError(f"release asset URL does not match its file name: {name}")

    bridge = _read_json(bundle / LEGACY_MANIFEST_NAME)
    try:
        legacy_manifest = ReleaseManifest.parse(bridge)
    except ValueError as exc:
        raise ValueError(f"legacy Setup bridge is rejected by the 0.3.3 client: {exc}") from exc
    if (
        bridge.get("schema") != 2
        or bridge.get("product") != PRODUCT
        or bridge.get("version") != manifest.version
        or str(bridge.get("revision") or "").lower() != manifest.revision.lower()
        or bridge.get("minimum_launcher_version") != manifest.min_updater_version
    ):
        raise ValueError("legacy Setup bridge does not match the signed release")
    legacy_runtime_name = f"Insta360_HW_runtime_v{manifest.version}.zip"
    legacy_runtime_path = bundle / legacy_runtime_name
    signed_runtime = assets[runtime_name]
    if (
        legacy_manifest.runtime.name != legacy_runtime_name
        or not legacy_runtime_path.is_file()
        or legacy_manifest.runtime.sha256 != signed_runtime.sha256
        or legacy_manifest.runtime.size_bytes != signed_runtime.size
        or _sha256(legacy_runtime_path) != signed_runtime.sha256
    ):
        raise ValueError("legacy Setup bridge runtime alias does not match the signed runtime")
    signed_setup = assets[SETUP_NAME]
    if (
        legacy_manifest.setup.name != SETUP_NAME
        or legacy_manifest.setup.sha256 != signed_setup.sha256
        or legacy_manifest.setup.size_bytes != signed_setup.size
    ):
        raise ValueError("legacy Setup bridge Setup asset does not match the signed release")

    expected_artifacts = {
        runtime_name,
        legacy_runtime_name,
        SETUP_NAME,
        V3_MANIFEST_NAME,
        LEGACY_MANIFEST_NAME,
    }
    checksum_lines = (bundle / CHECKSUMS_NAME).read_text(encoding="ascii").splitlines()
    checksums: dict[str, str] = {}
    for line in checksum_lines:
        digest, separator, name = line.partition("  ")
        if not separator or len(digest) != 64 or name in checksums:
            raise ValueError("SHA256SUMS.txt is invalid")
        checksums[name] = digest
    if set(checksums) != expected_artifacts:
        raise ValueError("SHA256SUMS.txt does not cover the exact release artifact set")
    for name, digest in checksums.items():
        if _sha256(bundle / name) != digest:
            raise ValueError(f"SHA256SUMS.txt mismatch: {name}")

    with temporary_workspace() as temporary:
        extracted = temporary / "runtime"
        safe_extract(bundle / runtime_name, extracted)
        validate_payload(extracted, manifest)
        _assert_no_python_cache_artifacts(extracted)
        extracted_anchor = (extracted / "config" / "update_public_key.pem").read_bytes()
        trusted_anchor = public_key_path.read_bytes()
        if extracted_anchor != trusted_anchor:
            raise ValueError(
                "runtime trust anchor bytes do not match the release public key "
                f"(runtime={hashlib.sha256(extracted_anchor).hexdigest()}, "
                f"trusted={hashlib.sha256(trusted_anchor).hexdigest()})"
            )
    return {
        "version": manifest.version,
        "revision": manifest.revision.lower(),
        "artifact_count": len(expected_artifacts),
        "runtime": runtime_name,
    }


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("published timestamp must include a timezone")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and verify signed Insta360_HW release bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("initialize-key")
    initialize.add_argument("--private-key", type=Path, required=True)
    initialize.add_argument("--public-key", type=Path, required=True)
    verify_key = subparsers.add_parser("verify-key")
    verify_key.add_argument("--private-key", type=Path, required=True)
    verify_key.add_argument("--public-key", type=Path, required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--runtime-root", type=Path, required=True)
    build.add_argument("--setup", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--private-key", type=Path, required=True)
    build.add_argument("--public-key", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--revision", required=True)
    build.add_argument("--repository", required=True)
    build.add_argument("--notice", type=Path, required=True)
    build.add_argument("--published-at", required=True)
    build.add_argument("--source-date-epoch", type=int, required=True)
    build.add_argument("--min-updater-version", default=DEFAULT_MIN_UPDATER_VERSION)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle-dir", type=Path, required=True)
    verify.add_argument("--public-key", type=Path, required=True)
    verify.add_argument("--version")
    verify.add_argument("--revision")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "initialize-key":
        initialize_signing_key(arguments.private_key, arguments.public_key)
        print(f"Created Ed25519 signing key: {arguments.private_key}")
        print(f"Created update trust anchor: {arguments.public_key}")
        return 0
    if arguments.command == "verify-key":
        fingerprint = verify_signing_key(arguments.private_key, arguments.public_key)
        print(f"Release signing key matches trust anchor: sha256:{fingerprint}")
        return 0
    if arguments.command == "build":
        notice = _read_json(arguments.notice)
        output = build_bundle(
            runtime_root=arguments.runtime_root,
            setup_path=arguments.setup,
            output_dir=arguments.output_dir,
            private_key_path=arguments.private_key,
            public_key_path=arguments.public_key,
            version=arguments.version,
            revision=arguments.revision,
            repository=arguments.repository,
            notice=notice,
            published_at=_parse_datetime(arguments.published_at),
            source_date_epoch=arguments.source_date_epoch,
            min_updater_version=arguments.min_updater_version,
        )
        print(f"Release bundle ready: {output}")
        return 0
    result = verify_bundle(
        arguments.bundle_dir,
        arguments.public_key,
        arguments.version,
        arguments.revision,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
