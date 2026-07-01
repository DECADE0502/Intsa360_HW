from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateApiTests(unittest.TestCase):
    def test_suite_app_exposes_version_and_update_endpoints(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")

        self.assertIn('"/api/version"', text)
        self.assertIn('"/api/update/check"', text)
        self.assertIn('"/api/update/run"', text)

    def test_update_api_reads_version_file_and_uses_update_script(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")

        self.assertIn("VERSION", text)
        self.assertIn("update.ps1", text)
        self.assertIn("版本", text)
        self.assertIn("更新", text)

    def test_compare_versions_handles_prerelease_and_build_metadata(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        cases = [
            ("0.2.15", "0.2.16", -1),
            ("0.2.15", "0.2.15", 0),
            ("0.2.16", "0.2.15", 1),
            ("0.2.15-rc1", "0.2.15", -1),
            ("0.2.15", "0.2.15-rc1", 1),
            ("0.2.15-rc1", "0.2.15-rc2", -1),
            ("0.2.15+build.1", "0.2.15", 0),
            ("1.0.0", "0.9.9", 1),
        ]
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                self.assertEqual(update_api._compare_versions(left, right), expected)

        with self.assertRaises(ValueError):
            update_api._compare_versions("not-a-version", "0.2.15")

    def test_remote_repo_path_prefers_update_notice_trace(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "UPDATE_NOTICE.json").write_text(
                json.dumps({"trace": {"repo": "OWNER_FROM_NOTICE/RepoFromNotice"}}),
                encoding="utf-8",
            )
            (root / "update.ps1").write_text(
                '$Repo = "https://github.com/OWNER_FROM_SCRIPT/RepoFromScript"\n',
                encoding="utf-8",
            )

            self.assertEqual(update_api._remote_repo_path(root), "OWNER_FROM_NOTICE/RepoFromNotice")

    def test_remote_repo_path_prefers_local_config_override(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "local.json").write_text(
                json.dumps({"update": {"repo": "OWNER_FROM_CONFIG/RepoFromConfig"}}),
                encoding="utf-8",
            )
            (root / "UPDATE_NOTICE.json").write_text(
                json.dumps({"trace": {"repo": "OWNER_FROM_NOTICE/RepoFromNotice"}}),
                encoding="utf-8",
            )

            self.assertEqual(update_api._remote_repo_path(root), "OWNER_FROM_CONFIG/RepoFromConfig")


if __name__ == "__main__":
    unittest.main()
