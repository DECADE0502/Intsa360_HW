from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess

from app.backend.contracts.releases import ReleaseManifestV3
from app.backend.windows_process import system_powershell


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _kernel32_process_api():
    if os.name != "nt":
        raise RuntimeError("Windows process APIs are available only on Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def process_alive(process_id: int) -> bool:
    if os.name != "nt" or process_id <= 0:
        return False
    kernel32 = _kernel32_process_api()
    process = kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(process)


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _launch_elevated_process(executable: str, arguments: list[str], working_directory: Path) -> int:
    if os.name != "nt":
        raise RuntimeError("elevated lifecycle switching is supported only on Windows")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfoW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    info = _ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = subprocess.list2cmdline(arguments)
    info.lpDirectory = str(working_directory)
    info.nShow = 0
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise RuntimeError("用户取消了更新所需的系统授权")
        raise OSError(error, "无法启动提权更新进程")
    if not info.hProcess:
        raise RuntimeError("系统授权成功，但没有返回更新工作进程")
    try:
        process_id = int(kernel32.GetProcessId(info.hProcess))
        if process_id <= 0:
            raise OSError(ctypes.get_last_error(), "无法读取更新工作进程编号")
        return process_id
    finally:
        kernel32.CloseHandle(info.hProcess)


def launch_worker(
    install_root: Path,
    runtime_root: Path,
    state_root: Path,
    job_id: str,
    stage: Path,
    manifest: ReleaseManifestV3,
    tree_sha256: str,
) -> int:
    worker = runtime_root / "scripts" / "lifecycle_v3" / "Worker.ps1"
    if not worker.is_file():
        raise ValueError("trusted lifecycle V3 worker is missing from the active runtime")
    arguments = [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(worker),
        "-InstallRoot", str(install_root), "-StateRoot", str(state_root),
        "-JobId", job_id, "-StageRoot", str(stage),
        "-ExpectedVersion", manifest.version,
        "-ExpectedRevision", manifest.revision.lower(),
        "-ExpectedTreeSha256", tree_sha256,
    ]
    powershell = system_powershell()
    if os.environ.get("INSTA360_HW_NO_ELEVATION") == "1" or _is_admin():
        process = subprocess.Popen(
            [powershell, *arguments],
            cwd=str(state_root),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return process.pid
    return _launch_elevated_process(powershell, arguments, state_root)
