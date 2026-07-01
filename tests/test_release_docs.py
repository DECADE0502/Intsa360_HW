from __future__ import annotations

import unittest
from pathlib import Path

from _constants import BRAND_NAME_CANONICAL, BRAND_NAME_LEGACY


ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocsTests(unittest.TestCase):
    def test_release_docs_exist_and_are_chinese(self) -> None:
        for relative, title in [
            ("docs/INSTALL.md", "安装"),
            ("docs/UPDATE.md", "更新"),
            ("docs/ROLLBACK.md", "回滚"),
            ("docs/UNINSTALL.md", "卸载"),
        ]:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(BRAND_NAME_CANONICAL, text, "docs must use canonical brand name")
                self.assertNotIn(BRAND_NAME_LEGACY, text, "docs must not reference legacy brand name")
                self.assertIn(title, text)

    def test_install_doc_covers_smartscreen_uac_silent_and_cadence_recovery(self) -> None:
        text = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

        self.assertIn("SmartScreen", text)
        self.assertIn("UAC", text)
        self.assertIn("静默安装", text)
        self.assertIn("/VERYSILENT", text)
        self.assertIn("Cadence 集成失败恢复", text)
        self.assertIn("首次启动", text)

    def test_update_doc_covers_sha256_and_downgrade_policy(self) -> None:
        text = (ROOT / "docs" / "UPDATE.md").read_text(encoding="utf-8")

        self.assertIn("SHA256", text)
        self.assertIn("integrity_verified", text)
        self.assertIn("AllowDowngrade", text)

    def test_uninstall_doc_covers_three_modes_and_keep_data(self) -> None:
        text = (ROOT / "docs" / "UNINSTALL.md").read_text(encoding="utf-8")

        self.assertIn("Windows 设置", text)
        self.assertIn("移除 Cadence 集成", text)
        self.assertIn("uninstall.ps1", text)
        self.assertIn("keep_data", text)
        self.assertIn("%LOCALAPPDATA%\\Insta360_HW", text)

    def test_verify_all_script_runs_required_checks(self) -> None:
        text = (ROOT / "scripts" / "verify_all.ps1").read_text(encoding="utf-8")

        self.assertIn("unittest discover", text)
        self.assertIn("py_compile", text)
        self.assertIn("npm run build", text)
        self.assertIn("English UI text found", text)


if __name__ == "__main__":
    unittest.main()
