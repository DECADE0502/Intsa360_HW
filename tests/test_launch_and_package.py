from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LaunchAndPackageTests(unittest.TestCase):
    def test_raw_suite_entry_requires_explicit_dev_only_switch(self) -> None:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        self.assertIsNotNone(powershell)
        script = ROOT / "run_tool_suite.ps1"
        completed = subprocess.run(
            [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        source = script.read_text(encoding="utf-8-sig")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("launch_tool_suite.ps1", completed.stdout + completed.stderr)
        self.assertIn("[switch]$DevOnly", source)
        self.assertIn("Write-Warning", source)

    def _run_runtime_probe(self, body: str) -> str:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        self.assertIsNotNone(powershell, "PowerShell is required for lifecycle behavior tests")
        runtime = ROOT / "scripts" / "lifecycle" / "Runtime.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.ps1"
            script.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                f". '{runtime.as_posix()}'\n"
                + body,
                encoding="utf-8-sig",
            )
            completed = subprocess.run(
                [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed.stdout.strip()

    def test_probe_retries_before_declaring_dead(self) -> None:
        output = self._run_runtime_probe(
            r'''
$runtimeRoot = [System.IO.Path]::GetFullPath("C:\runtime")
$stateRoot = [System.IO.Path]::GetFullPath("C:\state")
$script:calls = 0
function Get-HwLifecycleServiceProcessState { param($RuntimeRoot, $StateRoot) return "Alive" }
function Read-HwLifecycleJson {
  return [pscustomobject]@{ pid=42; port=8765; root=$runtimeRoot; state_root=$stateRoot; version="0.4.0"; instance_token=("a" * 32) }
}
function Get-HwLifecycleHealth {
  param($Port, $TimeoutMs)
  $script:calls += 1
  if ($script:calls -lt 3) { return $null }
  return [pscustomobject]@{ product="Insta360_HW"; status="ok"; pid=42; root=$runtimeRoot; state_root=$stateRoot; version="0.4.0"; instance_token=("a" * 32) }
}
$state = Get-HwLifecycleServiceState -RuntimeRoot $runtimeRoot -StateRoot $stateRoot -ProbeTimeouts @(1, 1, 1, 1)
Write-Output "$state|$script:calls"
'''
        )
        self.assertEqual(output, "Alive|3")

    def test_busy_service_is_not_stopped(self) -> None:
        runtime = (ROOT / "scripts" / "lifecycle" / "Runtime.ps1").read_text(encoding="utf-8-sig")
        launcher = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8-sig")

        self.assertIn('return "Busy"', runtime)
        self.assertIn('$serviceState -eq "Busy"', launcher)
        busy_branch = launcher.index('$serviceState -eq "Busy"')
        stop_call = launcher.index("Stop-HwLifecycleService", busy_branch)
        self.assertIn('$serviceState -in @("Dead", "Foreign")', launcher[busy_branch:stop_call])

    def test_reconnect_arguments_have_no_restart(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
        start = text.index("private static string BuildLaunchArgs")
        end = text.index("private static bool IsReconnectRequest", start)
        reconnect_branch = text[start:end]

        self.assertNotIn('values.Add("-Restart")', reconnect_branch)
        self.assertNotIn('values.Add("-NoOpen")', reconnect_branch)
        self.assertNotIn("OpenPlatformUrl", text)

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
        self.assertIn("AddSeconds(90)", text)
        self.assertIn("ProbeTimeouts @(1000)", text)
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
        v3_runtime = (ROOT / "scripts" / "lifecycle_v3" / "Runtime.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("Get-HwLifecycleRuntimeBackendProcesses", runtime)
        self.assertIn("app\\backend\\suite_app.py", runtime)
        self.assertIn("runtime\\python\\python.exe", runtime)
        self.assertIn("remaining owned backend process", runtime)
        self.assertIn("[string]$health.state_root", runtime)
        self.assertIn("AddSeconds(120)", v3_runtime)

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
