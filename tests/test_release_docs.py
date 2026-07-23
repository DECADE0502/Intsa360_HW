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
            ("docs/RELEASE.md", "发布"),
        ]:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(BRAND_NAME_CANONICAL, text, "docs must use canonical brand name")
                self.assertNotIn(BRAND_NAME_LEGACY, text, "docs must not reference legacy brand name")
                self.assertIn(title, text)

    def test_install_doc_covers_smartscreen_uac_silent_and_standard_maintenance(self) -> None:
        text = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

        self.assertIn("SmartScreen", text)
        self.assertIn("UAC", text)
        self.assertIn("静默安装", text)
        self.assertIn("/VERYSILENT", text)
        self.assertIn("Cadence 16.6", text)
        self.assertIn("再次运行 Setup", text)
        self.assertIn("标准卸载", text)
        self.assertIn("/ACTION=Uninstall", text)
        self.assertIn("/PRESERVEDATA", text)

    def test_update_doc_covers_signature_integrity_bridge_and_downgrade_policy(self) -> None:
        text = (ROOT / "docs" / "UPDATE.md").read_text(encoding="utf-8")

        self.assertIn("SHA256", text)
        self.assertIn("Ed25519", text)
        self.assertIn("升级到 `0.4.2`", text)
        self.assertIn("自动降级都会被拒绝", text)

    def test_release_documentation_uses_send_pack_only_channel(self) -> None:
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")

        self.assertIn("publish_ota.ps1", text)
        self.assertIn("ota", text)
        self.assertIn("send-pack", text)
        self.assertNotIn("$env:GH_TOKEN", text)

    def test_uninstall_doc_matches_standard_uninstaller_contract(self) -> None:
        text = (ROOT / "docs" / "UNINSTALL.md").read_text(encoding="utf-8")

        self.assertIn("Windows 设置", text)
        self.assertIn("移除 Cadence 集成", text)
        self.assertIn("uninstall.ps1", text)
        self.assertIn("unins000.exe", text)
        self.assertIn("PreserveData", text)
        self.assertIn("PurgeData", text)
        self.assertIn("/PRESERVEDATA", text)
        self.assertIn("/PURGEDATA", text)
        self.assertIn("%LOCALAPPDATA%\\Insta360_HW", text)
        self.assertNotIn("-Force", text)
        self.assertNotIn("keep_data", text)

    def test_rollback_doc_matches_v3_recovery_contract(self) -> None:
        text = (ROOT / "docs" / "ROLLBACK.md").read_text(encoding="utf-8")

        self.assertIn("installation.json", text)
        self.assertIn(".recovery", text)
        self.assertIn("启动器", text)
        self.assertNotIn("_hwagent_backup_", text)
        self.assertNotIn("update.ps1 -AllowDowngrade", text)

    def test_verify_all_script_runs_required_checks(self) -> None:
        text = (ROOT / "scripts" / "verify_all.ps1").read_text(encoding="utf-8")

        self.assertIn("$Python -m pytest", text)
        self.assertIn('throw "pytest group failed: $Name"', text)
        self.assertIn('Invoke-PytestGroup -Name "bom"', text)
        self.assertIn('Invoke-PytestGroup -Name "runtime"', text)
        self.assertIn('Invoke-PytestGroup -Name "lifecycle"', text)
        self.assertIn('Invoke-PytestGroup -Name "platform-api"', text)
        self.assertIn('throw "pytest verification groups overlap"', text)
        self.assertIn('throw "pytest verification groups do not cover every test file"', text)
        self.assertNotIn("unittest discover", text)
        self.assertIn('-c "import pytest"', text)
        self.assertIn("Python with pytest not found", text)
        self.assertIn("py_compile", text)
        self.assertIn('Test-Path -LiteralPath "node_modules"', text)
        self.assertIn("npm ci --prefer-offline --no-audit --no-fund", text)
        self.assertLess(
            text.index("npm ci --prefer-offline --no-audit --no-fund"),
            text.index("npm run test:unit"),
        )
        self.assertIn("npm run test:unit", text)
        self.assertIn("npm run build", text)
        self.assertIn("English UI text found", text)

    def test_pre_release_tests_are_anchored_to_the_repository_root(self) -> None:
        text = (ROOT / "scripts" / "pre_release_check.ps1").read_text(encoding="utf-8")
        test_gate = text.split("if (-not $SkipTests)", 1)[1].split("$releaseTool", 1)[0]

        self.assertIn("Push-Location $Root", test_gate)
        self.assertIn("-m pytest tests -q", test_gate)
        self.assertIn("npm run test:unit", test_gate)
        self.assertIn("npm run build", test_gate)

    def test_verify_all_uses_a_short_windows_safe_test_temp_root_and_restores_environment(self) -> None:
        text = (ROOT / "scripts" / "verify_all.ps1").read_text(encoding="utf-8")

        self.assertIn("[Environment+SpecialFolder]::LocalApplicationData", text)
        self.assertIn('Join-Path $LocalAppData ("Temp\\ihv\\"', text)
        self.assertIn(".Substring(0, 12)", text)
        self.assertNotIn("Insta360_HW_Verify", text)
        self.assertNotIn("verify-temp", text)
        self.assertIn('$VerifyPytestRoot = Join-Path $VerifyTempRoot "p"', text)
        self.assertIn('$BaseTemp = Join-Path $VerifyPytestRoot $Name', text)
        self.assertIn("-m pytest -q --basetemp $BaseTemp", text)
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
