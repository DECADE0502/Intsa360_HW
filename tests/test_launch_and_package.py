from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LaunchAndPackageTests(unittest.TestCase):
    def test_cadence_jump_uses_hidden_powershell_window(self) -> None:
        text = (ROOT / "iac_jump.bat").read_text(encoding="utf-8")

        self.assertIn("wscript.exe", text.lower())
        self.assertIn("launch_tool_suite_hidden.vbs", text)
        self.assertIn("launch_tool_suite.ps1", text)

    def test_launcher_logs_and_uses_shell_url_open(self) -> None:
        text = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8")
        vbs = (ROOT / "launch_tool_suite_hidden.vbs").read_text(encoding="utf-8")

        self.assertIn("scripts\\lib\\Paths.ps1", text)
        self.assertIn("Find-Python", text)
        self.assertNotIn("codex-primary-runtime\\dependencies\\python\\python.exe", text)
        self.assertIn("launcher_latest.log", text)
        self.assertIn("Write-LauncherLog", text)
        self.assertIn("Open-WaitingPage", text)
        self.assertIn("waiting.html", text)
        self.assertIn("/api/plugins", text)
        self.assertIn("url.dll,FileProtocolHandler", text)
        self.assertIn("Insta360硬件提效平台已就绪", text)
        self.assertNotIn("Hardware Efficiency Suite ready", text)
        self.assertIn("WScript.Shell", vbs)
        self.assertIn("launch_tool_suite.ps1", vbs)

    def test_waiting_page_is_readable_chinese_and_redirects_to_target(self) -> None:
        text = (ROOT / "app" / "frontend" / "waiting.html").read_text(encoding="utf-8")

        self.assertIn("<html lang=\"zh-CN\">", text)
        self.assertIn("<title>正在启动 Insta360硬件提效平台</title>", text)
        self.assertIn("<h1>正在启动 Insta360硬件提效平台</h1>", text)
        self.assertIn("首次启动需要几秒钟", text)
        self.assertIn("正在连接本地服务", text)
        self.assertIn("location.replace(target)", text)
        self.assertNotIn("姝ｅ湪", text)
        self.assertNotIn("鍚", text)
        self.assertNotIn("纭欢", text)

    def test_package_endpoint_uses_requested_name_for_zip(self) -> None:
        backend = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")

        self.assertIn("_timestamp_for_filename", backend)
        self.assertIn('f"{name}_{stamp}.zip"', backend)
        self.assertIn('params.get("name")', backend)
        mojibake = bytes.fromhex("424f4de780b5e7858ee59ab9").decode("utf-8")
        self.assertNotIn(mojibake, backend)


if __name__ == "__main__":
    unittest.main()
