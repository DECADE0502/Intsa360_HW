from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.backend import lifecycle_update
from app.backend.release_manifest import ReleaseManifest


ROOT = Path(__file__).resolve().parents[1]
_REVISION_A = "a" * 40
_REVISION_B = "b" * 40


def _manifest(version: str, revision: str, build_kind: str | None = "published") -> ReleaseManifest:
    raw: dict[str, object] = {
        "schema": 2,
        "product": "Insta360_HW",
        "version": version,
        "revision": revision,
        "published_at": "2026-07-14T00:00:00Z",
        "channel": "stable",
        "minimum_launcher_version": "0.3.3",
        "assets": {
            "runtime": {
                "name": f"Insta360_HW_runtime_v{version}.zip",
                "url": "https://example.invalid/runtime.zip",
                "sha256": "c" * 64,
                "size_bytes": 1,
            },
            "setup": {
                "name": "Insta360_HW_Setup.exe",
                "url": "https://example.invalid/Insta360_HW_Setup.exe",
                "sha256": "d" * 64,
                "size_bytes": 1,
            },
        },
        "notice": {"title": "Release", "summary": "Canonical", "highlights": ["identity"]},
    }
    if build_kind is not None:
        raw["build_kind"] = build_kind
    return ReleaseManifest.parse(raw)


def _installed_runtime(root: Path, version: str, revision: str, build_kind: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "REVISION").write_text(revision + "\n", encoding="utf-8")
    manifest: dict[str, object] = {
        "schema": 2,
        "product": "Insta360_HW",
        "version": version,
        "revision": revision,
        "layout": "runtime-v2",
    }
    if build_kind is not None:
        manifest["build_kind"] = build_kind
    (root / "install_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class ReleaseIdentityTests(unittest.TestCase):
    def test_033_style_install_detects_canonical_040_published_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.3.3", _REVISION_B)

            result = lifecycle_update._evaluate_update(root, _manifest("0.4.0", _REVISION_A))

        self.assertTrue(result["has_update"])
        self.assertTrue(result["can_update"])
        self.assertEqual(result["update_reason"], "newer_version")

    def test_same_version_dev_install_updates_to_canonical_published_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.4.0", _REVISION_B, build_kind="dev")

            result = lifecycle_update._evaluate_update(root, _manifest("0.4.0", _REVISION_A))

        self.assertTrue(result["has_update"])
        self.assertTrue(result["can_update"])
        self.assertEqual(result["update_reason"], "canonical_published_revision")

    def test_same_version_published_revisions_are_an_integrity_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.4.0", _REVISION_B, build_kind="published")

            result = lifecycle_update._evaluate_update(root, _manifest("0.4.0", _REVISION_A))

        self.assertFalse(result["has_update"])
        self.assertFalse(result["can_update"])
        self.assertEqual(result["update_reason"], "integrity_conflict")
        self.assertTrue(result["identity_conflict"])

    def test_legacy_manifest_without_build_kind_defaults_to_published(self) -> None:
        self.assertEqual(_manifest("0.3.3", _REVISION_A, build_kind=None).build_kind, "published")

    def test_public_build_preflight_rejects_dirty_and_duplicate_identities_before_packaging(self) -> None:
        script = ROOT / "scripts" / "build_release.ps1"
        source = script.read_text(encoding="utf-8")
        self.assertIn("[switch]$PreflightOnly", source)
        self.assertIn("Assert-PublicBuildIdentity", source)
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            fake_git = bin_dir / "git.cmd"
            fake_git.write_text(
                "@echo off\r\n"
                "setlocal\r\n"
                ":scan\r\n"
                "if \"%~1\"==\"\" exit /b 0\r\n"
                "if /I \"%~1\"==\"rev-parse\" (echo " + _REVISION_A + "& exit /b 0)\r\n"
                "if /I \"%~1\"==\"status\" (if not \"%FAKE_GIT_STATUS%\"==\"\" echo %FAKE_GIT_STATUS%& exit /b 0)\r\n"
                "if /I \"%~1\"==\"tag\" (if not \"%FAKE_GIT_TAG%\"==\"\" echo %FAKE_GIT_TAG%& exit /b 0)\r\n"
                "shift\r\n"
                "goto scan\r\n",
                encoding="ascii",
            )
            base_env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
            dirty = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-BuildKind", "published", "-PreflightOnly", "-GitExecutable", str(fake_git),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**base_env, "FAKE_GIT_STATUS": " M app/backend/release_manifest.py", "FAKE_GIT_TAG": ""},
                timeout=30,
            )
            duplicate = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-BuildKind", "published", "-PreflightOnly", "-GitExecutable", str(fake_git),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**base_env, "FAKE_GIT_STATUS": "", "FAKE_GIT_TAG": "v0.3.3"},
                timeout=30,
            )

        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("clean git worktree", dirty.stdout + dirty.stderr)
        self.assertNotIn("Building release tree", dirty.stdout + dirty.stderr)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("already has a public build", duplicate.stdout + duplicate.stderr)
        self.assertNotIn("Building release tree", duplicate.stdout + duplicate.stderr)

    def test_packaging_scripts_propagate_build_kind_and_pre_release_checks_identity(self) -> None:
        release = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")
        gate = (ROOT / "scripts" / "pre_release_check.ps1").read_text(encoding="utf-8")

        self.assertIn('[ValidateSet("dev", "published")]', release)
        self.assertIn('build_kind = $BuildKind', release)
        self.assertIn('"-BuildKind", $BuildKind', installer)
        self.assertIn('InstallManifest.build_kind', gate)


if __name__ == "__main__":
    unittest.main()
