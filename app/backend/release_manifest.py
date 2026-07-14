from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse


MANIFEST_SCHEMA = 2
PRODUCT = "Insta360_HW"
BUILD_KINDS = frozenset({"dev", "published"})
DEFAULT_MANIFEST_URL = (
    "https://github.com/DECADE0502/Intsa360_HW/"
    "releases/latest/download/update-manifest.json"
)
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_SOURCE_ARCHIVE_MARKERS = ("/archive/", "/zipball/", "/tarball/", "/zip/refs/")


def parse_version(value: str) -> tuple[tuple[int, int, int], tuple[tuple[int, str], ...]]:
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    core = tuple(int(match.group(index)) for index in (1, 2, 3))
    prerelease: list[tuple[int, str]] = []
    if match.group(4):
        for part in match.group(4).split("."):
            prerelease.append((0, f"{int(part):020d}") if part.isdigit() else (1, part.lower()))
    return core, tuple(prerelease)


def compare_versions(left: str, right: str) -> int:
    left_core, left_pre = parse_version(left)
    right_core, right_pre = parse_version(right)
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    if not left_pre and not right_pre:
        return 0
    if not left_pre:
        return 1
    if not right_pre:
        return -1
    for lpart, rpart in zip(left_pre, right_pre):
        if lpart == rpart:
            continue
        return -1 if lpart < rpart else 1
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


def parse_build_kind(value: Any, *, legacy_default: str = "published") -> str:
    if value is None:
        return legacy_default
    if not isinstance(value, str):
        raise ValueError("build_kind must be a string")
    build_kind = value.strip().lower()
    if build_kind not in BUILD_KINDS:
        raise ValueError("build_kind must be dev or published")
    return build_kind


def _require_object(raw: Any, *, label: str, required: set[str], allowed: set[str]) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"{label} is missing required field(s): {', '.join(missing)}")
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise ValueError(f"{label} has unexpected field(s): {', '.join(unexpected)}")
    return raw


def _parse_published_at(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("update manifest published_at must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("update manifest published_at must be an RFC3339 UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError("update manifest published_at must be in UTC")
    return value


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    sha256: str
    size_bytes: int

    @classmethod
    def parse(cls, raw: Any, *, version: str, kind: str) -> "ReleaseAsset":
        asset = _require_object(
            raw,
            label=f"{kind} asset",
            required={"name", "url", "sha256", "size_bytes"},
            allowed={"name", "url", "sha256", "size_bytes"},
        )
        name = asset["name"]
        url = asset["url"]
        sha256 = asset["sha256"]
        size = asset["size_bytes"]
        expected_name = f"{PRODUCT}_runtime_v{version}.zip" if kind == "runtime" else f"{PRODUCT}_Setup.exe"
        if not isinstance(name, str) or name != expected_name:
            raise ValueError(f"{kind} asset name must be {expected_name}")
        if "/" in name or "\\" in name or PurePosixPath(name).name != name:
            raise ValueError(f"{kind} asset name must be a filename")
        if not isinstance(url, str):
            raise ValueError(f"{kind} asset URL must be a string")
        parsed_url = urlparse(url)
        lower_path = parsed_url.path.lower()
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError(f"{kind} asset URL must use HTTPS")
        if parsed_url.netloc.lower() == "codeload.github.com" or any(marker in lower_path for marker in _SOURCE_ARCHIVE_MARKERS):
            raise ValueError(f"{kind} asset must not use a source archive")
        if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
            raise ValueError(f"{kind} asset requires a 64-character SHA256")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"{kind} asset size_bytes must be a positive integer")
        return cls(name=name, url=url, sha256=sha256.lower(), size_bytes=size)


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    revision: str
    build_kind: str
    published_at: str
    channel: str
    minimum_launcher_version: str
    runtime: ReleaseAsset
    setup: ReleaseAsset
    title: str
    summary: str
    highlights: tuple[str, ...]
    compatibility: str

    @classmethod
    def parse(cls, raw: Any) -> "ReleaseManifest":
        manifest = _require_object(
            raw,
            label="update manifest",
            required={
                "schema",
                "product",
                "version",
                "revision",
                "published_at",
                "channel",
                "minimum_launcher_version",
                "assets",
                "notice",
            },
            allowed={
                "schema",
                "product",
                "version",
                "revision",
                "build_kind",
                "published_at",
                "channel",
                "minimum_launcher_version",
                "assets",
                "notice",
            },
        )
        if type(manifest["schema"]) is not int or manifest["schema"] != MANIFEST_SCHEMA:
            raise ValueError(f"unsupported update manifest schema: {manifest['schema']!r}")
        if manifest["product"] != PRODUCT:
            raise ValueError("update manifest product mismatch")
        if not isinstance(manifest["version"], str):
            raise ValueError("update manifest version must be a string")
        version = manifest["version"].strip()
        parse_version(version)
        if not isinstance(manifest["revision"], str):
            raise ValueError("update manifest revision must be a string")
        revision = manifest["revision"].strip().lower()
        if not _REVISION_RE.fullmatch(revision):
            raise ValueError("update manifest revision is invalid")
        build_kind = parse_build_kind(manifest.get("build_kind"))
        published_at = _parse_published_at(manifest["published_at"])
        if not isinstance(manifest["minimum_launcher_version"], str):
            raise ValueError("minimum_launcher_version must be a semantic version")
        launcher = manifest["minimum_launcher_version"].strip()
        parse_version(launcher)
        if not isinstance(manifest["channel"], str):
            raise ValueError("update manifest channel must be a string")
        channel = manifest["channel"].strip().lower()
        if channel not in {"stable", "beta"}:
            raise ValueError(f"unsupported update channel: {channel}")
        assets = _require_object(
            manifest["assets"],
            label="update manifest assets",
            required={"runtime", "setup"},
            allowed={"runtime", "setup"},
        )
        notice = _require_object(
            manifest["notice"],
            label="update manifest notice",
            required={"title", "summary", "highlights"},
            allowed={"title", "summary", "highlights", "compatibility"},
        )
        if not isinstance(notice["title"], str) or not isinstance(notice["summary"], str):
            raise ValueError("update manifest notice title and summary must be strings")
        highlights_raw = notice["highlights"]
        if not isinstance(highlights_raw, list) or not all(isinstance(item, str) for item in highlights_raw):
            raise ValueError("notice.highlights must be a string list")
        compatibility = notice.get("compatibility", "")
        if not isinstance(compatibility, str):
            raise ValueError("notice.compatibility must be a string")
        return cls(
            version=version,
            revision=revision,
            build_kind=build_kind,
            published_at=published_at,
            channel=channel,
            minimum_launcher_version=launcher,
            runtime=ReleaseAsset.parse(assets["runtime"], version=version, kind="runtime"),
            setup=ReleaseAsset.parse(assets["setup"], version=version, kind="setup"),
            title=notice["title"],
            summary=notice["summary"],
            highlights=tuple(highlights_raw),
            compatibility=compatibility,
        )

    def update_notice(self) -> dict[str, object]:
        return {
            "version": self.version,
            "revision": self.revision,
            "build_kind": self.build_kind,
            "target_revision": self.revision,
            "date": self.published_at,
            "title": self.title,
            "summary": self.summary,
            "highlights": list(self.highlights),
            "compatibility": self.compatibility,
            "trace": {"source": "github_release_manifest", "channel": self.channel},
        }


def validate_manifest_file(path: str | Path) -> ReleaseManifest:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    return ReleaseManifest.parse(raw)


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_manifest.py <update-manifest.json>", file=sys.stderr)
        return 2
    try:
        validate_manifest_file(argv[1])
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"invalid release manifest: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
