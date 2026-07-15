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

    def test_service_launcher_uses_exact_v2_identity_and_shell_url_open(self) -> None:
        text = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8")
        vbs = (ROOT / "launch_tool_suite_hidden.vbs").read_text(encoding="utf-8")

        self.assertIn("scripts\\lib\\Paths.ps1", text)
        self.assertIn("scripts\\lifecycle\\Contract.ps1", text)
        self.assertIn("scripts\\lifecycle\\Runtime.ps1", text)
        self.assertIn("Find-Python", text)
        self.assertIn("launcher_latest.log", text)
        self.assertIn("Open-WaitingPage", text)
        self.assertIn("waiting.html", text)
        self.assertIn("/api/tools", text)
        self.assertIn("url.dll,FileProtocolHandler", text)
        self.assertIn("schema = 2", text)
        self.assertIn("executable = $Python", text)
        self.assertIn("version = $Version", text)
        self.assertIn("Test-HwLifecycleService", text)
        self.assertIn("Global\\Insta360_HW_ServiceLaunch_V2", text)
        self.assertIn("AbandonedMutexException", text)
        self.assertIn("ReleaseMutex", text)
        self.assertIn("Launch failed:", text)
        self.assertNotIn("Get-NetTCPConnection", text)
        self.assertNotIn("codex-primary-runtime\\dependencies\\python\\python.exe", text)
        self.assertIn("WScript.Shell", vbs)

    def test_gui_launcher_checks_full_identity_contract(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        for member in ("Schema", "Product", "Executable", "Root", "StateRoot", "Version", "InstanceToken"):
            self.assertIn(member, text)
        self.assertIn("health.Version != identity.Version", text)
        self.assertIn("SamePath(stateRoot, health.StateRoot)", text)
        self.assertIn("mutex.WaitOne(ScriptTimeoutMilliseconds)", text)
        self.assertIn("Launcher operation timed out", text)
        self.assertIn("Platform did not pass final health verification", text)
        self.assertNotIn("first-run", text.lower())

    def test_service_restart_reclaims_exact_runtime_processes_without_state_file(self) -> None:
        runtime = (ROOT / "scripts" / "lifecycle" / "Runtime.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("Get-HwLifecycleRuntimeBackendProcesses", runtime)
        self.assertIn("app\\backend\\suite_app.py", runtime)
        self.assertIn("runtime\\python\\python.exe", runtime)
        self.assertIn("remaining owned backend process", runtime)
        self.assertIn("[string]$health.state_root", runtime)

    def test_waiting_page_is_readable_chinese_and_redirects_to_target(self) -> None:
        text = (ROOT / "app" / "frontend" / "waiting.html").read_text(encoding="utf-8")

        self.assertIn('<html lang="zh-CN">', text)
        self.assertIn("正在启动 Insta360硬件提效平台", text)
        self.assertIn("首次启动需要几秒钟", text)
        self.assertIn("正在连接本地服务", text)
        self.assertIn("location.replace(target)", text)
        self.assertNotIn("姝ｅ湪", text)
        self.assertNotIn("纭欢", text)

    def test_package_endpoint_uses_requested_name_for_zip(self) -> None:
        backend = (ROOT / "app" / "backend" / "api" / "routers" / "files.py").read_text(encoding="utf-8")

        self.assertIn("_timestamp_for_filename", backend)
        self.assertIn('f"{name}_{stamp}.zip"', backend)
        self.assertIn('params.get("name")', backend)
        mojibake = bytes.fromhex("424f4de780b5e7858ee59ab9").decode("utf-8")
        self.assertNotIn(mojibake, backend)


if __name__ == "__main__":
    unittest.main()
