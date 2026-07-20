from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.backend.api.cadence import CADENCE_LOADER_MARKER, parse_cadence_loader_paths


ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPTS = (
    ROOT / "scripts" / "redeploy_cadence_loader.ps1",
    ROOT / "scripts" / "remove_cadence_loader.ps1",
)
LIBRARY_SCRIPTS = (
    ROOT / "scripts" / "lib" / "Cadence.ps1",
    ROOT / "scripts" / "lib" / "CadenceDiscovery.ps1",
    ROOT / "scripts" / "lib" / "TclScripts.ps1",
)


class SubprocessEncodingTests(unittest.TestCase):
    def test_entry_scripts_declare_utf8_output_before_writing(self) -> None:
        for script in ENTRY_SCRIPTS:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8-sig")
                header = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"
                output_positions = [pos for token in ("Write-Host", "Write-Output", "Write-Warning") if (pos := text.find(token)) >= 0]

                self.assertIn(header, "\n".join(text.splitlines()[:30]))
                self.assertLess(text.index(header), min(output_positions))

    def test_cadence_libraries_normalize_output_when_dot_sourced(self) -> None:
        header = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"
        for script in LIBRARY_SCRIPTS:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8-sig")
                self.assertIn(header, "\n".join(text.splitlines()[:20]))
                self.assertIn("$OutputEncoding = [System.Text.Encoding]::UTF8", "\n".join(text.splitlines()[:20]))

    @unittest.skipIf(shutil.which("powershell") is None, "Windows PowerShell is unavailable")
    def test_powershell_chinese_path_roundtrips_under_utf8_decode(self) -> None:
        expected = r"C:\用户\测试\iac_bom_tool.tcl"
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "utf8-output.ps1"
            script.write_text(
                "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}\n"
                "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
                f'Write-Host "{CADENCE_LOADER_MARKER}{expected}"\n',
                encoding="utf-8-sig",
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("\ufffd", completed.stdout)
        self.assertEqual(parse_cadence_loader_paths(completed.stdout), [expected])


if __name__ == "__main__":
    unittest.main()
