from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EmbeddedPythonTests(unittest.TestCase):
    @unittest.skipUnless(__import__("sys").platform == "win32", "Windows PowerShell only")
    def test_sha256_assertion_rejects_mismatched_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload.bin"
            payload.write_bytes(b"not the expected payload")
            command = (
                "$ErrorActionPreference='Stop'; "
                ". '.\\scripts\\lib\\EmbeddedPython.ps1'; "
                f"Assert-HwAgentSha256 -Path '{payload}' -ExpectedSha256 '{'0' * 64}'"
            )

            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 mismatch", result.stdout + result.stderr)

    @unittest.skipUnless(__import__("sys").platform == "win32", "Windows PowerShell only")
    def test_find_python_prefers_embedded_runtime_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = root / "app" / "backend"
            backend.mkdir(parents=True)
            (backend / "suite_app.py").write_text("# marker", encoding="utf-8")
            (root / "launch_tool_suite.ps1").write_text("# marker", encoding="utf-8")
            embedded = root / "runtime" / "python" / "python.exe"
            embedded.parent.mkdir(parents=True)
            embedded.write_bytes(b"MZ")

            command = (
                "$ErrorActionPreference='Stop'; "
                ". '.\\scripts\\lib\\Paths.ps1'; "
                f"Find-Python -Root '{root}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), embedded.resolve())

    @unittest.skipUnless(__import__("sys").platform == "win32", "Windows PowerShell only")
    def test_install_wheel_extracts_files_into_site_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wheel = root / "demo-1.0.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("demo_pkg/__init__.py", "VALUE = 1\n")
                archive.writestr("demo-1.0.0.dist-info/METADATA", "Name: demo\n")
            site_packages = root / "Lib" / "site-packages"
            site_packages.mkdir(parents=True)

            command = (
                "$ErrorActionPreference='Stop'; "
                ". '.\\scripts\\lib\\EmbeddedPython.ps1'; "
                f"Install-HwAgentWheel -WheelPath '{wheel}' -SitePackages '{site_packages}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((site_packages / "demo_pkg" / "__init__.py").exists())


if __name__ == "__main__":
    unittest.main()
