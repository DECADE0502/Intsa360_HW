from __future__ import annotations

import subprocess
import sys
import tempfile
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

        self.assertIn("$Python -m pytest", text)
        self.assertIn('throw "pytest failed"', text)
        self.assertNotIn("unittest discover", text)
        self.assertIn('-c "import pytest"', text)
        self.assertIn("Python with pytest not found", text)
        self.assertIn("py_compile", text)
        self.assertIn("npm run build", text)
        self.assertIn("English UI text found", text)

    def test_verify_all_uses_and_restores_a_canonical_test_temp_root(self) -> None:
        text = (ROOT / "scripts" / "verify_all.ps1").read_text(encoding="utf-8")

        self.assertIn("[Environment+SpecialFolder]::LocalApplicationData", text)
        self.assertIn("Insta360_HW_Verify", text)
        self.assertIn("verify-temp", text)
        self.assertNotIn('("Insta360_HW\\verify-temp\\"', text)
        self.assertIn("$env:TEMP = $VerifyTempRoot", text)
        self.assertIn("$env:TMP = $VerifyTempRoot", text)
        self.assertIn("$env:TEMP = $OriginalTemp", text)
        self.assertIn("$env:TMP = $OriginalTmp", text)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell only")
    def test_verify_all_probe_skips_incapable_python_and_selects_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rejected = root / "python-without-pytest.cmd"
            fallback = root / "python-with-pytest.cmd"
            rejected_marker = root / "rejected.txt"
            fallback_marker = root / "fallback.txt"
            rejected.write_text(
                f'@echo called>"{rejected_marker}"\n@echo pytest import failed 1>&2\n@exit /b 1\n',
                encoding="ascii",
            )
            fallback.write_text(
                f'@echo called>"{fallback_marker}"\n@exit /b 0\n',
                encoding="ascii",
            )

            def ps_quote(path: Path) -> str:
                return str(path).replace("'", "''")

            script = ps_quote(ROOT / "scripts" / "verify_all.ps1")
            command = (
                "$ErrorActionPreference='Stop'; "
                f"& '{script}' -ProbeOnly -PythonCandidates "
                f"@('{ps_quote(rejected)}','{ps_quote(fallback)}')"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(rejected_marker.exists())
            self.assertTrue(fallback_marker.exists())
            self.assertEqual(Path(result.stdout.strip()).resolve(), fallback.resolve())


if __name__ == "__main__":
    unittest.main()
