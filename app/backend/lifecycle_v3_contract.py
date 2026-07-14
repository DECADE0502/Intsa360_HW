from __future__ import annotations

import base64
import binascii
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ValidationError

from app.backend.contracts.releases import ReleaseManifestV3


PRODUCT = "Insta360_HW"
INSTALLATION_SCHEMA = 3
INSTALLATION_LAYOUT = "versioned-runtime-v3"
RUNTIME_SCHEMA = 3
RUNTIME_LAYOUT = "runtime-v3"

_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_RUNTIME_ID_RE = re.compile(
    r"^(?P<version>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\+(?P<revision>[0-9a-fA-F]{40})$"
)
_SOURCE_ARCHIVE_MARKERS = ("/archive/", "/zipball/", "/tarball/", "/zip/refs/")


@dataclass(frozen=True)
class InstallationLayout:
    install_root: Path
    active_runtime: Path
    previous_runtime: Path | None
    metadata_path: Path
    generation: int
    metadata: Mapping[str, Any]


def canonical_manifest_payload(raw: Mapping[str, Any]) -> bytes:
    if not isinstance(raw, Mapping):
        raise ValueError("release manifest must be an object")
    payload = copy.deepcopy(dict(raw))
    payload.pop("signature", None)
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("release manifest cannot be canonicalized") from exc
    return encoded.encode("utf-8")


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("update signature public key is invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("update signature public key must be Ed25519")
    return key


def _decode_signature(value: object) -> bytes:
    if not isinstance(value, str) or not value.startswith("ed25519:"):
        raise ValueError("release manifest signature must use ed25519")
    try:
        signature = base64.b64decode(value.removeprefix("ed25519:"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("release manifest signature is invalid") from exc
    if len(signature) != 64:
        raise ValueError("release manifest signature is invalid")
    return signature


def _reject_source_archives(manifest: ReleaseManifestV3) -> None:
    for asset in manifest.assets:
        parsed = urlparse(str(asset.url))
        path = parsed.path.lower()
        if parsed.netloc.lower() == "codeload.github.com" or any(
            marker in path for marker in _SOURCE_ARCHIVE_MARKERS
        ):
            raise ValueError("release asset must not use a source archive")


def verify_signed_manifest(
    raw: Mapping[str, Any],
    public_key_path: str | Path,
) -> ReleaseManifestV3:
    if not isinstance(raw, Mapping):
        raise ValueError("release manifest must be an object")
    signature = _decode_signature(raw.get("signature"))
    key = _load_public_key(Path(public_key_path))
    try:
        key.verify(signature, canonical_manifest_payload(raw))
    except InvalidSignature as exc:
        raise ValueError("release manifest signature verification failed") from exc
    try:
        manifest = ReleaseManifestV3.model_validate(dict(raw))
    except ValidationError as exc:
        raise ValueError(f"release manifest is invalid: {exc}") from exc
    _reject_source_archives(manifest)
    return manifest


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return raw


def _runtime_relative(value: object, *, field: str, allow_empty: bool = False) -> PurePosixPath | None:
    if allow_empty and value in (None, ""):
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a runtime path")
    if "\\" in value:
        raise ValueError(f"{field} must use forward slashes")
    relative = PurePosixPath(value)
    if relative.is_absolute() or relative.parts[:1] != ("runtime",) or len(relative.parts) != 2:
        raise ValueError(f"{field} must identify one versioned runtime")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{field} escapes the installation root")
    if not _RUNTIME_ID_RE.fullmatch(relative.parts[1]):
        raise ValueError(f"{field} has an invalid runtime identity")
    return relative


def _resolve_under_install_root(install_root: Path, relative: PurePosixPath, *, field: str) -> Path:
    target = (install_root / Path(*relative.parts)).resolve()
    runtime_parent = (install_root / "runtime").resolve()
    try:
        target.relative_to(runtime_parent)
    except ValueError as exc:
        raise ValueError(f"{field} escapes the installation root") from exc
    return target


def _validate_runtime_manifest(runtime: Path, runtime_id: str) -> None:
    manifest = read_json_object(runtime / "install_manifest.json", label="runtime install manifest")
    if manifest.get("product") != PRODUCT:
        raise ValueError("runtime install manifest product mismatch")
    if type(manifest.get("schema")) is not int or manifest["schema"] != RUNTIME_SCHEMA:
        raise ValueError("runtime install manifest schema is unsupported")
    if manifest.get("layout") != RUNTIME_LAYOUT:
        raise ValueError("runtime install manifest layout is unsupported")
    match = _RUNTIME_ID_RE.fullmatch(runtime_id)
    if match is None:
        raise ValueError("active_runtime has an invalid runtime identity")
    version = manifest.get("version")
    revision = manifest.get("revision")
    if version != match.group("version") or not isinstance(revision, str):
        raise ValueError("runtime install manifest does not match active_runtime")
    if not _REVISION_RE.fullmatch(revision) or revision.lower() != match.group("revision").lower():
        raise ValueError("runtime install manifest does not match active_runtime")


def candidate_install_root(runtime_root: Path) -> Path | None:
    runtime = runtime_root.resolve()
    if runtime.parent.name.lower() != "runtime":
        return None
    candidate = runtime.parent.parent
    if not (candidate / "installation.json").is_file():
        return None
    return candidate.resolve()


def resolve_installation(runtime_root: str | Path) -> InstallationLayout:
    runtime = Path(runtime_root).expanduser().resolve()
    install_root = candidate_install_root(runtime)
    if install_root is None:
        raise ValueError("runtime is not part of a versioned installation")
    metadata_path = install_root / "installation.json"
    metadata = read_json_object(metadata_path, label="installation metadata")
    if metadata.get("product") != PRODUCT:
        raise ValueError("installation metadata product mismatch")
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"] != INSTALLATION_SCHEMA:
        raise ValueError("installation metadata schema is unsupported")
    if metadata.get("layout") != INSTALLATION_LAYOUT:
        raise ValueError("installation metadata layout is unsupported")
    generation = metadata.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ValueError("installation metadata generation is invalid")

    active_relative = _runtime_relative(metadata.get("active_runtime"), field="active_runtime")
    assert active_relative is not None
    active_runtime = _resolve_under_install_root(install_root, active_relative, field="active_runtime")
    if active_runtime != runtime:
        raise ValueError("active_runtime does not identify the running runtime")
    if not active_runtime.is_dir():
        raise ValueError("active_runtime does not exist")
    _validate_runtime_manifest(active_runtime, active_relative.parts[1])

    previous_relative = _runtime_relative(
        metadata.get("previous_runtime"), field="previous_runtime", allow_empty=True
    )
    previous_runtime = (
        _resolve_under_install_root(install_root, previous_relative, field="previous_runtime")
        if previous_relative is not None
        else None
    )
    return InstallationLayout(
        install_root=install_root,
        active_runtime=active_runtime,
        previous_runtime=previous_runtime,
        metadata_path=metadata_path,
        generation=generation,
        metadata=metadata,
    )


def is_versioned_install(runtime_root: str | Path) -> bool:
    runtime = Path(runtime_root).expanduser().resolve()
    if candidate_install_root(runtime) is None:
        return False
    resolve_installation(runtime)
    return True
