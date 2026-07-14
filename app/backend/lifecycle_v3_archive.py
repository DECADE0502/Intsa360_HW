from __future__ import annotations

import hashlib
import shutil
import stat
import threading
import zipfile
from pathlib import Path

from app.backend.contracts.releases import ReleaseManifestV3
from app.backend.lifecycle_v3_contract import PRODUCT, RUNTIME_LAYOUT, read_json_object


MAX_ARCHIVE_ENTRIES = 50_000
MAX_UNCOMPRESSED_BYTES = 3 * 1024 * 1024 * 1024
EXTRACTION_FREE_SPACE_RESERVE = 256 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

REQUIRED_RUNTIME_FILES = (
    "VERSION",
    "REVISION",
    "install_manifest.json",
    "launch_tool_suite.ps1",
    "app/backend/suite_app.py",
    "app/frontend/index.html",
    "runtime/python/python.exe",
    "scripts/lifecycle_v3/Worker.ps1",
    "scripts/lifecycle_v3/Recover.ps1",
    "scripts/lifecycle_v3/Resume.ps1",
    "scripts/lifecycle_v3/Contract.ps1",
    "scripts/lifecycle_v3/Runtime.ps1",
    "scripts/lifecycle/Contract.ps1",
    "scripts/lifecycle/Runtime.ps1",
    "scripts/lib/Paths.ps1",
    "scripts/lib/Cadence.ps1",
    "scripts/lib/TclScripts.ps1",
    "config/update_public_key.pem",
)


def _read_text(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def safe_extract(archive: Path, destination: Path, cancel: threading.Event | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if not infos:
            raise ValueError("runtime archive is empty")
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("runtime archive contains too many entries")
        expanded_bytes = sum(info.file_size for info in infos)
        if expanded_bytes > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("runtime archive expands beyond the 3 GiB limit")
        if shutil.disk_usage(destination).free < expanded_bytes + EXTRACTION_FREE_SPACE_RESERVE:
            raise ValueError("insufficient free disk space to stage the verified runtime")

        targets: set[str] = set()
        planned: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in infos:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("更新已在提交前取消")
            if info.flag_bits & 0x1:
                raise ValueError(f"runtime archive contains an encrypted entry: {info.filename}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"runtime archive contains a symbolic link: {info.filename}")
            target = (destination / info.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"runtime archive path escapes staging root: {info.filename}") from exc
            key = str(target).casefold()
            if key in targets:
                raise ValueError(f"runtime archive contains a duplicate path: {info.filename}")
            targets.add(key)
            planned.append((info, target))

        for info, target in planned:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("更新已在提交前取消")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("更新已在提交前取消")
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)


def validate_payload(path: Path, manifest: ReleaseManifestV3) -> None:
    for relative in REQUIRED_RUNTIME_FILES:
        if not (path / relative).is_file():
            raise ValueError(f"runtime payload is incomplete; missing {relative}")
    if _read_text(path, "VERSION") != manifest.version:
        raise ValueError("payload VERSION does not match the signed manifest")
    if _read_text(path, "REVISION").lower() != manifest.revision.lower():
        raise ValueError("payload REVISION does not match the signed manifest")
    runtime_manifest = read_json_object(path / "install_manifest.json", label="runtime install manifest")
    if runtime_manifest.get("schema") != 3 or runtime_manifest.get("product") != PRODUCT:
        raise ValueError("payload runtime identity is invalid")
    if runtime_manifest.get("layout") != RUNTIME_LAYOUT:
        raise ValueError("payload runtime layout must be runtime-v3")
    if runtime_manifest.get("version") != manifest.version:
        raise ValueError("payload runtime version does not match the signed manifest")
    if str(runtime_manifest.get("revision") or "").lower() != manifest.revision.lower():
        raise ValueError("payload runtime revision does not match the signed manifest")
    if runtime_manifest.get("build_kind") != manifest.build_kind.value:
        raise ValueError("payload runtime build kind does not match the signed manifest")


def runtime_tree_sha256(root: Path) -> str:
    records: list[str] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"runtime payload contains a symbolic link: {path}")
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
        records.append(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}\t{digest.hexdigest()}\n")
    return hashlib.sha256("".join(sorted(records)).encode("utf-8")).hexdigest()
