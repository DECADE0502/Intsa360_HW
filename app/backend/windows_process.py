from __future__ import annotations

import ctypes
import os
from pathlib import Path


def system_powershell() -> str:
    if os.name != "nt":
        raise RuntimeError("Windows PowerShell is available only on Windows")
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise OSError(ctypes.get_last_error(), "cannot resolve the Windows system directory")
    executable = Path(buffer.value) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise RuntimeError(f"system Windows PowerShell is missing: {executable}")
    return str(executable)
