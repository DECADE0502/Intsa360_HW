from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
