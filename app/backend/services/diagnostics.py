from __future__ import annotations

import argparse
import io
import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

from app.backend import update_api
from app.backend.api.context import build_context
from app.backend.repositories.assets_repository import AssetsRepository
from app.backend.services.health import collect_health
from app.backend.services.platform_logging import redact_text


MAX_LOG_FILES = 10
MAX_LOG_BYTES_PER_FILE = 2 * 1024 * 1024
MAX_SELECTED_ASSETS = 20
MAX_SELECTED_BYTES = 100 * 1024 * 1024
_RUNTIME_LOG_NAMES = frozenset(
    {
        "launcher_latest.log",
        "cadence_loader_probe.log",
        "update_latest.log",
        "tool_suite_server_latest.log",
        "tool_suite_server_error_latest.log",
    }
)
_STATE_LOG_NAMES = frozenset({"launcher.log", "install_latest.log", "uninstall_latest.log"})


def _tail_text(path: Path, limit: int) -> str:
    with path.open("rb") as handle:
        size = path.stat().st_size
        if size > limit:
            handle.seek(size - limit)
        return handle.read(limit).decode("utf-8", errors="replace")


def _diagnostic_logs(context) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    runtime_dir = context.paths.runtime_log_dir
    if runtime_dir.is_dir():
        for path in runtime_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith("platform.jsonl") or path.name in _RUNTIME_LOG_NAMES:
                candidates.append((f"logs/{path.name}", path))
    state_log_dir = context.paths.state_root / "logs"
    if state_log_dir.is_dir():
        for name in _STATE_LOG_NAMES:
            path = state_log_dir / name
            if path.is_file():
                candidates.append((f"logs/state/{name}", path))

    def modified(item: tuple[str, Path]) -> float:
        try:
            return item[1].stat().st_mtime
        except OSError:
            return 0.0

    return sorted(candidates, key=modified, reverse=True)[:MAX_LOG_FILES]


def _selected_asset_files(
    root: Path,
    asset_ids: Sequence[object],
) -> tuple[list[tuple[str, Path]], list[dict[str, object]]]:
    if len(asset_ids) > MAX_SELECTED_ASSETS:
        raise ValueError(f"一次最多选择 {MAX_SELECTED_ASSETS} 个诊断资产")
    repository = AssetsRepository(root)
    files: list[tuple[str, Path]] = []
    metadata: list[dict[str, object]] = []
    total = 0
    seen: set[str] = set()
    for raw_id in asset_ids:
        asset = repository.get(str(raw_id))
        identifier = str(asset.id)
        if identifier in seen:
            continue
        seen.add(identifier)
        path = repository.resolve(asset.relative_path)
        if path is None or not path.exists():
            raise FileNotFoundError(f"资产文件不存在: {asset.display_name}")
        metadata.append(asset.model_dump(mode="json"))
        candidates: list[tuple[str, Path]] = []
        if path.is_file():
            candidates.append((path.name, path))
        elif path.is_dir():
            for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().casefold()):
                if child.is_symlink() or not child.is_file():
                    continue
                try:
                    relative = child.resolve().relative_to(path.resolve()).as_posix()
                except ValueError:
                    continue
                candidates.append((relative, child))
        for relative, candidate in candidates:
            total += candidate.stat().st_size
            if total > MAX_SELECTED_BYTES:
                raise ValueError(f"所选诊断资产总量超过 {MAX_SELECTED_BYTES} 字节")
            files.append((f"selected_assets/{identifier}/{relative}", candidate))
    return files, metadata


def build_diagnostic_package(
    root: Path,
    *,
    selected_asset_ids: Sequence[object] = (),
    secrets: Iterable[str] = (),
) -> bytes:
    runtime_root = Path(root).resolve()
    secret_values = tuple(str(secret) for secret in secrets if str(secret))
    context = build_context(runtime_root)
    health = collect_health(context, immediate_database_check=True)
    report = redact_text(update_api.collect_diagnostic_report(runtime_root), secret_values)
    selected_files, selected_metadata = _selected_asset_files(runtime_root, selected_asset_ids) if selected_asset_ids else ([], [])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostic_report.txt", report.encode("utf-8"))
        archive.writestr(
            "health.json",
            json.dumps(health, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        if selected_metadata:
            archive.writestr(
                "selected_assets/manifest.json",
                json.dumps(selected_metadata, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        for archive_name, log in _diagnostic_logs(context):
            try:
                content = redact_text(_tail_text(log, MAX_LOG_BYTES_PER_FILE), secret_values)
            except OSError:
                continue
            archive.writestr(archive_name, content.encode("utf-8"))
        for archive_name, path in selected_files:
            archive.write(path, arcname=archive_name)
    return buffer.getvalue()


def write_diagnostic_package(root: Path, output_path: Path) -> Path:
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(build_diagnostic_package(root))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect an offline Insta360_HW diagnostic package.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(write_diagnostic_package(args.root, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
