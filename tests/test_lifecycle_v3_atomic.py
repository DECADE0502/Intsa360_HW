from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.backend import lifecycle_v3
from app.backend.lifecycle_v3_archive import REQUIRED_RUNTIME_FILES


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = "powershell.exe"
OLD_VERSION = "0.3.3"
NEW_VERSION = "0.4.0"
OLD_REVISION = "a" * 40
NEW_REVISION = "b" * 40


def _runtime_relative(version: str, revision: str) -> str:
    return f"runtime/{version}+{revision}"


def _open_exclusive_read_handle(path: Path):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    invalid_handle = ctypes.c_void_p(-1).value
    assert handle not in (None, invalid_handle), ctypes.get_last_error()
    return kernel32, handle


def _powershell_quote(value: object) -> str:
    return str(value).replace("'", "''")


def _write_runtime(path: Path, version: str, revision: str) -> None:
    path.mkdir(parents=True)
    (path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (path / "REVISION").write_text(revision + "\n", encoding="utf-8")
    (path / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "layout": "runtime-v3",
                "version": version,
                "revision": revision,
                "build_kind": "published",
            }
        ),
        encoding="utf-8",
    )
    for relative in REQUIRED_RUNTIME_FILES:
        if relative in {"VERSION", "REVISION", "install_manifest.json"}:
            continue
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"fixture:{relative}\n", encoding="utf-8")


def _write_installation(install_root: Path, active_relative: str) -> Path:
    install_root.mkdir(parents=True, exist_ok=True)
    (install_root / "Insta360_HW.exe").write_bytes(b"launcher")
    metadata = install_root / "installation.json"
    metadata.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "product": "Insta360_HW",
                "layout": "versioned-runtime-v3",
                "active_runtime": active_relative,
                "previous_runtime": "",
                "generation": 1,
                "updated_at": "2026-07-14T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return metadata


def _tree_sha256(root: Path) -> str:
    records: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}\t{digest}\n")
    return hashlib.sha256("".join(sorted(records)).encode("utf-8")).hexdigest()


def _signed_manifest() -> tuple[dict[str, object], Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    raw: dict[str, object] = {
        "schema_version": 3,
        "version": NEW_VERSION,
        "revision": NEW_REVISION,
        "build_kind": "published",
        "published_at": "2026-07-14T00:00:00Z",
        "min_updater_version": "0.4.0",
        "assets": [
            {
                "name": f"Insta360_HW_Runtime_{NEW_VERSION}.zip",
                "url": f"https://github.com/DECADE0502/Intsa360_HW/releases/download/v{NEW_VERSION}/Insta360_HW_Runtime_{NEW_VERSION}.zip",
                "size": 1024,
                "sha256": "c" * 64,
            }
        ],
        "changelog": ["Atomic runtime switch"],
        "signature": "pending",
    }
    signature = private_key.sign(lifecycle_v3.canonical_manifest_payload(raw))
    raw["signature"] = "ed25519:" + base64.b64encode(signature).decode("ascii")
    return raw, private_key


def _public_key_file(tmp_path: Path, private_key: Ed25519PrivateKey) -> Path:
    path = tmp_path / "update_public_key.pem"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def test_trust_anchor_identity_accepts_lf_and_crlf_but_rejects_another_key(tmp_path: Path) -> None:
    trusted_private = Ed25519PrivateKey.generate()
    trusted_lf = _public_key_file(tmp_path / "trusted", trusted_private)
    trusted_crlf = tmp_path / "trusted-crlf.pem"
    trusted_crlf.write_bytes(trusted_lf.read_bytes().replace(b"\n", b"\r\n"))
    other_key = _public_key_file(tmp_path / "other", Ed25519PrivateKey.generate())

    assert lifecycle_v3._trust_anchors_match(trusted_lf, trusted_crlf)
    assert not lifecycle_v3._trust_anchors_match(trusted_lf, other_key)


def _prepare_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    install_root = tmp_path / "HWAgent"
    old_relative = _runtime_relative(OLD_VERSION, OLD_REVISION)
    old_runtime = install_root / Path(old_relative)
    stage = tmp_path / "state" / "lifecycle" / "v3" / "transactions" / ("1" * 32) / "stage"
    _write_runtime(old_runtime, OLD_VERSION, OLD_REVISION)
    _write_runtime(stage, NEW_VERSION, NEW_REVISION)
    metadata = _write_installation(install_root, old_relative)
    state_root = tmp_path / "state"
    (state_root / "lifecycle" / "v3" / "jobs").mkdir(parents=True, exist_ok=True)
    return install_root, old_runtime, stage, metadata


def _run_worker(
    install_root: Path,
    state_root: Path,
    stage: Path,
    *,
    fault_at: str = "",
    skip_recovery_registration: bool = True,
) -> subprocess.CompletedProcess[str]:
    job_id = "1" * 32
    command = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "lifecycle_v3" / "Worker.ps1"),
        "-InstallRoot",
        str(install_root),
        "-StateRoot",
        str(state_root),
        "-JobId",
        job_id,
        "-StageRoot",
        str(stage),
        "-ExpectedVersion",
        NEW_VERSION,
        "-ExpectedRevision",
        NEW_REVISION,
        "-ExpectedTreeSha256",
        _tree_sha256(stage),
        "-NoRestart",
        "-SkipCadence",
    ]
    if skip_recovery_registration:
        command.append("-SkipRecoveryRegistration")
    if fault_at:
        command.extend(["-FaultAt", fault_at])
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)


def _run_recover(install_root: Path, state_root: Path, job_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "lifecycle_v3" / "Recover.ps1"),
            "-InstallRoot",
            str(install_root),
            "-StateRoot",
            str(state_root),
            "-JobId",
            job_id,
            "-NoRestart",
            "-SkipCadence",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_fails_loudly_when_journal_is_missing(tmp_path: Path) -> None:
    install_root = tmp_path / "HWAgent"
    state_root = tmp_path / "state"
    install_root.mkdir()
    state_root.mkdir()
    job_id = "9" * 32

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode != 0
    assert "Protected lifecycle recovery metadata is missing" in result.stdout + result.stderr
    assert "already completed by a concurrent recoverer" not in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_concurrent_recovery_second_caller_succeeds(tmp_path: Path) -> None:
    install_root, _, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "c" * 32
    old_relative = _runtime_relative(OLD_VERSION, OLD_REVISION)
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)
    original = json.loads(metadata.read_text(encoding="utf-8"))
    metadata.write_text(
        json.dumps(
            {
                **original,
                "active_runtime": new_relative,
                "previous_runtime": old_relative,
                "generation": 2,
            }
        ),
        encoding="utf-8",
    )
    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": old_relative,
                "new_relative": new_relative,
                "runtime_created": True,
                "outcome": "completed",
            }
        ),
        encoding="utf-8",
    )
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True)

    first = _run_recover(install_root, state_root, job_id)
    second = _run_recover(install_root, state_root, job_id)

    assert first.returncode == 0, first.stdout + first.stderr
    assert "recovery_outcome=committed" in first.stdout
    assert second.returncode == 0, second.stdout + second.stderr
    assert "already completed by a concurrent recoverer" in second.stdout
    assert "recovery_outcome=already_recovered" in second.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing semantics")
def test_tree_hash_retries_a_transient_file_sharing_violation(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    locked_file = runtime / "Recover.ps1"
    locked_file.write_text("# fixture\n", encoding="utf-8")
    ready = tmp_path / "hash-ready.txt"

    kernel32, handle = _open_exclusive_read_handle(locked_file)
    command = (
        f". '{_powershell_quote(ROOT / 'scripts/lifecycle_v3/Contract.ps1')}'; "
        f"Set-Content -LiteralPath '{_powershell_quote(ready)}' -Value ready; "
        f"Get-HwV3TreeSha256 -Path '{_powershell_quote(runtime)}'"
    )
    process = subprocess.Popen(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "PowerShell did not reach the hash operation"
        time.sleep(0.4)
    finally:
        kernel32.CloseHandle(handle)

    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stdout + stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing semantics")
def test_legacy_atomic_json_retries_a_transient_target_lock(tmp_path: Path) -> None:
    target = tmp_path / "journal.json"
    target.write_text('{"state":"old"}\n', encoding="utf-8")
    ready = tmp_path / "replace-ready.txt"
    kernel32, handle = _open_exclusive_read_handle(target)
    command = (
        f". '{_powershell_quote(ROOT / 'scripts/lifecycle/Contract.ps1')}'; "
        f"Set-Content -LiteralPath '{_powershell_quote(ready)}' -Value ready; "
        f"Write-HwLifecycleJsonAtomic -Path '{_powershell_quote(target)}' "
        "-Value @{ state = 'new' }"
    )
    process = subprocess.Popen(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "PowerShell did not reach the atomic replacement"
        time.sleep(0.4)
    finally:
        kernel32.CloseHandle(handle)

    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stdout + stderr
    assert json.loads(target.read_text(encoding="utf-8-sig")) == {"state": "new"}


def test_layout_resolves_only_the_declared_active_runtime(tmp_path: Path) -> None:
    install_root, old_runtime, _, metadata = _prepare_layout(tmp_path)

    layout = lifecycle_v3.resolve_installation(old_runtime)

    assert layout.install_root == install_root.resolve()
    assert layout.active_runtime == old_runtime.resolve()
    assert lifecycle_v3.is_versioned_install(old_runtime)

    raw = json.loads(metadata.read_text(encoding="utf-8"))
    raw["active_runtime"] = "../outside"
    metadata.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="active_runtime"):
        lifecycle_v3.resolve_installation(old_runtime)


def test_signed_manifest_verification_rejects_tampering_and_source_archives(tmp_path: Path) -> None:
    raw, private_key = _signed_manifest()
    public_key = _public_key_file(tmp_path, private_key)

    parsed = lifecycle_v3.verify_signed_manifest(raw, public_key)
    assert parsed.version == NEW_VERSION

    tampered = json.loads(json.dumps(raw))
    tampered["version"] = "0.4.1"
    with pytest.raises(ValueError, match="signature"):
        lifecycle_v3.verify_signed_manifest(tampered, public_key)

    source_archive = json.loads(json.dumps(raw))
    source_archive["assets"][0]["url"] = "https://codeload.github.com/DECADE0502/Intsa360_HW/zip/refs/heads/main"
    signature = private_key.sign(lifecycle_v3.canonical_manifest_payload(source_archive))
    source_archive["signature"] = "ed25519:" + base64.b64encode(signature).decode("ascii")
    with pytest.raises(ValueError, match="source archive"):
        lifecycle_v3.verify_signed_manifest(source_archive, public_key)


def test_recovery_registration_is_machine_scoped_and_non_restarting() -> None:
    worker = (ROOT / "scripts" / "lifecycle_v3" / "Worker.ps1").read_text(encoding="utf-8")
    recover = (ROOT / "scripts" / "lifecycle_v3" / "Recover.ps1").read_text(encoding="utf-8")
    resume = (ROOT / "scripts" / "lifecycle_v3" / "Resume.ps1").read_text(encoding="utf-8")
    contract = (ROOT / "scripts" / "lifecycle_v3" / "Contract.ps1").read_text(encoding="utf-8")

    assert "HKCU:" not in worker
    assert "NoRestart = $true" in resume
    registration = worker.split("function Set-RecoveryRegistration", 1)[1].split(
        "function Clear-RecoveryRegistration", 1
    )[0]
    assert "$protectedRecoveryBootstrap" in registration
    assert "Register-HwV3RecoveryTask" in registration
    assert "/TR $command" not in registration
    assert "-InstallRoot" not in registration
    assert 'New-Object -ComObject "Schedule.Service"' in contract
    assert "$action.Path = $powershell" in contract
    assert "$action.Arguments = $arguments" in contract
    assert "$definition.Principal.UserId = \"SYSTEM\"" in contract
    assert "$trigger.Delay = \"PT30S\"" in contract
    assert "$definition.Settings.StartWhenAvailable = $false" in contract
    assert "armed_boot_id = $armedBootId" in worker
    assert "Get-RecoveryBootIdentity" in resume
    assert "transaction.json" in resume
    assert "RecoveryTaskName" in resume
    assert "RecoveryTaskName" in recover
    assert "Remove-HwV3RecoveryTask" in recover
    assert "$env:INSTA360_HW_STATE_ROOT = $StateRoot" in worker
    assert "$env:INSTA360_HW_STATE_ROOT = $StateRoot" in recover
    assert "$stream.Flush($true)" in contract
    assert '"scripts\\lifecycle_v3\\Resume.ps1"' in contract
    assert '"scripts\\lifecycle\\Contract.ps1"' in contract
    assert '"scripts\\lifecycle\\Runtime.ps1"' in contract


@pytest.mark.skipif(
    sys.platform != "win32" or not bool(ctypes.windll.shell32.IsUserAnAdmin()),
    reason="Task Scheduler integration requires an elevated Windows process",
)
def test_recovery_task_registration_preserves_spaced_script_path(tmp_path: Path) -> None:
    script = tmp_path / "Program Files simulation" / "Resume.ps1"
    script.parent.mkdir(parents=True)
    script.write_text("exit 0\n", encoding="utf-8")
    task_name = f"Insta360_HW_Test_{time.time_ns()}"
    contract = ROOT / "scripts" / "lifecycle_v3" / "Contract.ps1"
    command = (
        "$ErrorActionPreference='Stop'; "
        f". '{_powershell_quote(contract)}'; "
        "$registered=$false; "
        "try { "
        f"Register-HwV3RecoveryTask -TaskName '{task_name}' "
        f"-PowerShellPath 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe' "
        f"-ScriptPath '{_powershell_quote(script)}' | Out-Null; "
        "$registered=$true; "
        f"& 'C:\\Windows\\System32\\schtasks.exe' /Query /TN '{task_name}' /XML; "
        "if ($LASTEXITCODE -ne 0) { throw 'task query failed' } "
        f"}} finally {{ if ($registered) {{ "
        f"Remove-HwV3RecoveryTask -TaskName '{task_name}' | Out-Null; "
        f"Remove-HwV3RecoveryTask -TaskName '{task_name}' | Out-Null "
        "} }"
    )

    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(script) in result.stdout
    assert "<UserId>S-1-5-18</UserId>" in result.stdout
    assert "<RunLevel>HighestAvailable</RunLevel>" in result.stdout
    assert "<Delay>PT30S</Delay>" in result.stdout
    assert "<StartWhenAvailable>true</StartWhenAvailable>" not in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_bootstrap_is_a_noop_during_the_boot_session_that_armed_it(tmp_path: Path) -> None:
    job_id = "9" * 32
    recovery_root = tmp_path / ".recovery" / job_id
    recovery_root.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "lifecycle_v3" / "Resume.ps1", recovery_root / "Resume.ps1")
    boot_identity = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            "(Get-CimInstance -ClassName Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    ).stdout.strip()
    descriptor = {
        "schema": 3,
        "product": "Insta360_HW",
        "job_id": job_id,
        "install_root": str(tmp_path / "install"),
        "state_root": str(tmp_path / "state"),
        "old_relative": _runtime_relative(OLD_VERSION, OLD_REVISION),
        "new_relative": _runtime_relative(NEW_VERSION, NEW_REVISION),
        "runtime_created": True,
        "skip_cadence": True,
        "armed_boot_id": boot_identity,
        "outcome": "pending",
    }
    descriptor_path = recovery_root / "transaction.json"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(recovery_root / "Resume.ps1")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert descriptor_path.is_file()


def test_v3_serializes_with_legacy_setup_and_uninstall_mutex() -> None:
    legacy = (ROOT / "scripts" / "lifecycle" / "Contract.ps1").read_text(encoding="utf-8-sig")
    current = (ROOT / "scripts" / "lifecycle_v3" / "Contract.ps1").read_text(encoding="utf-8")

    expected = "Global\\Insta360_HW_Lifecycle_V2"
    assert expected in legacy
    assert expected in current


def test_stable_launcher_resolves_active_runtime_and_forwards_state_root() -> None:
    launcher = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
    service_launcher = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8")
    runtime = (ROOT / "scripts" / "lifecycle_v3" / "Runtime.ps1").read_text(encoding="utf-8")

    assert "InstallationMetadata" in launcher
    assert "ResolveActiveRuntime(installRoot)" in launcher
    assert 'Path.Combine(runtimeRoot, "launch_tool_suite.ps1")' in launcher
    assert '" -StateRoot " + Quote(stateRoot)' in launcher
    assert "FindPendingV3Recovery" in launcher
    assert "ProtectedRecoveryDescriptor" in launcher
    recovery = launcher.split("private static int RunRecovery", 1)[1].split(
        "private static bool FindPendingV3Recovery", 1
    )[0]
    assert "while (FindPendingV3Recovery" in recovery
    assert 'File.Exists(Path.Combine(installRoot, "installation.json"))' in recovery
    assert 'Path.Combine(runtimeRoot, "scripts", "lifecycle_v3", "Recover.ps1")' not in recovery
    assert 'Verb = "runas"' in launcher
    assert '[string]$StateRoot = ""' in service_launcher
    assert "$env:INSTA360_HW_STATE_ROOT = $StateRoot" in service_launcher
    assert '-StateRoot "{1}"' in runtime


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher build")
def test_stable_launcher_accepts_utf8_bom_runtime_identity(tmp_path: Path) -> None:
    launcher = tmp_path / "Insta360_HW.exe"
    built = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "launcher" / "build.ps1"),
            "-Output",
            str(launcher),
            "-Version",
            NEW_VERSION,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert built.returncode == 0, built.stdout + built.stderr

    install_root = tmp_path / "installed app"
    relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    runtime_root = install_root / Path(relative)
    runtime_root.mkdir(parents=True)
    (runtime_root / "VERSION").write_text(NEW_VERSION + "\n", encoding="utf-8-sig")
    (runtime_root / "REVISION").write_text(NEW_REVISION + "\n", encoding="utf-8-sig")
    (runtime_root / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "version": NEW_VERSION,
                "revision": NEW_REVISION,
                "build_kind": "published",
                "layout": "runtime-v3",
            }
        ),
        encoding="utf-8-sig",
    )
    (install_root / "installation.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "product": "Insta360_HW",
                "layout": "versioned-runtime-v3",
                "active_runtime": relative,
            }
        ),
        encoding="utf-8",
    )

    command = (
        "Add-Type -AssemblyName System.Runtime.Serialization; "
        f"$assembly = [Reflection.Assembly]::LoadFile('{_powershell_quote(launcher)}'); "
        "$type = $assembly.GetType('Program', $true); "
        "$method = $type.GetMethod('ResolveActiveRuntime', "
        "[Reflection.BindingFlags]'NonPublic,Static'); "
        "try { "
        f"$resolved = $method.Invoke($null, [object[]]@('{_powershell_quote(install_root)}')); "
        "[Console]::Out.WriteLine($resolved) "
        "} catch { "
        "$failure = if ($_.Exception.InnerException) { $_.Exception.InnerException } else { $_.Exception }; "
        "[Console]::Error.WriteLine($failure.ToString()); exit 1 "
        "}"
    )
    resolved = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert str(runtime_root.resolve()).lower() in resolved.stdout.strip().lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher build")
def test_stable_launcher_waits_for_script_process_not_long_lived_child(tmp_path: Path) -> None:
    launcher = tmp_path / "Insta360_HW.exe"
    built = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "launcher" / "build.ps1"),
            "-Output",
            str(launcher),
            "-Version",
            NEW_VERSION,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert built.returncode == 0, built.stdout + built.stderr

    script = tmp_path / "spawn_child.ps1"
    script.write_text(
        "$stdout = Join-Path $PSScriptRoot 'child.stdout.log'\n"
        "$stderr = Join-Path $PSScriptRoot 'child.stderr.log'\n"
        "Start-Process -FilePath powershell.exe "
        "-ArgumentList '-NoProfile -Command \"Start-Sleep -Seconds 6\"' "
        "-WindowStyle Hidden -RedirectStandardOutput $stdout "
        "-RedirectStandardError $stderr | Out-Null\n"
        "exit 0\n",
        encoding="utf-8-sig",
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    command = (
        "Add-Type -AssemblyName System.Runtime.Serialization; "
        f"$assembly = [Reflection.Assembly]::LoadFile('{_powershell_quote(launcher)}'); "
        "$type = $assembly.GetType('Program', $true); "
        "$method = $type.GetMethod('RunPowerShellHidden', "
        "[Reflection.BindingFlags]'NonPublic,Static'); "
        "$arguments = New-Object 'object[]' 4; "
        f"$arguments[0] = '{_powershell_quote(tmp_path)}'; "
        f"$arguments[1] = '{_powershell_quote(script)}'; "
        "$arguments[2] = ''; "
        f"$arguments[3] = '{_powershell_quote(state_root)}'; "
        "$timer = [Diagnostics.Stopwatch]::StartNew(); "
        "$code = $method.Invoke($null, $arguments); "
        "$timer.Stop(); "
        "[Console]::Out.WriteLine(('{0}|{1}' -f $code, $timer.ElapsedMilliseconds))"
    )
    invoked = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert invoked.returncode == 0, invoked.stdout + invoked.stderr
    code, elapsed_ms = invoked.stdout.strip().split("|")
    assert code == "0"
    assert int(elapsed_ms) < 3000, invoked.stdout


def test_cadence_update_uses_original_user_plugin_state_path() -> None:
    worker = (ROOT / "scripts" / "lifecycle_v3" / "Worker.ps1").read_text(encoding="utf-8")

    assert '-PluginStatePath $pluginStatePath' in worker
    assert r'Join-Path $StateRoot "config\plugin_state.json"' in worker
    assert "Get-HwAgentManagedCadenceAutoLoadDirs" not in worker
    assert "Get-HwAgentCadenceCleanupAutoLoadDirs" in worker
    assert "-SkipDiscovery" in worker


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle worker")
def test_worker_switches_pointer_without_replacing_previous_runtime(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"

    result = _run_worker(install_root, state_root, stage)

    assert result.returncode == 0, result.stdout + result.stderr
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    assert current["active_runtime"] == new_relative
    assert current["previous_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
    assert current["generation"] == 2
    assert old_runtime.is_dir()
    assert (install_root / Path(new_relative)).is_dir()
    assert (install_root / "Insta360_HW.exe").read_bytes() == b"launcher"
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / (("1" * 32) + ".json")).read_text(encoding="utf-8-sig"))
    assert job["message"] == "Update completed and the new runtime passed verification."
    assert "Verifying staged runtime files." in job["log_tail"]
    assert "Moving the verified runtime into the installation atomically." in job["log_tail"]
    assert "Candidate runtime installed by atomic directory move." in job["log_tail"]
    assert not stage.exists()
    assert job["started_at"]
    assert job["updated_at"]


@pytest.mark.skipif(
    sys.platform != "win32" or not bool(ctypes.windll.shell32.IsUserAnAdmin()),
    reason="Full recovery registration requires an elevated Windows process",
)
def test_worker_switches_runtime_with_recovery_task_under_spaced_install_path(tmp_path: Path) -> None:
    layout_root = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / f"Insta360 HW {time.time_ns()}"
    try:
        install_root, old_runtime, stage, metadata = _prepare_layout(layout_root)
        state_root = layout_root / "state"

        result = _run_worker(
            install_root,
            state_root,
            stage,
            skip_recovery_registration=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        current = json.loads(metadata.read_text(encoding="utf-8-sig"))
        assert current["active_runtime"] == _runtime_relative(NEW_VERSION, NEW_REVISION)
        assert current["previous_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
        assert old_runtime.is_dir()
        assert not (install_root / ".recovery" / ("1" * 32)).exists()
        query = subprocess.run(
            [r"C:\Windows\System32\schtasks.exe", "/Query", "/TN", f"Insta360_HW_Recovery_{'1' * 32}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        assert query.returncode != 0, query.stdout + query.stderr
    finally:
        shutil.rmtree(layout_root, ignore_errors=True)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle worker")
def test_worker_failure_does_not_delete_preexisting_candidate_runtime(tmp_path: Path) -> None:
    install_root, _, stage, _ = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    candidate = install_root / Path(_runtime_relative(NEW_VERSION, NEW_REVISION))
    candidate.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(candidate)
    _write_runtime(stage, NEW_VERSION, NEW_REVISION)

    result = _run_worker(install_root, state_root, stage, fault_at="runtime_ready")

    assert result.returncode != 0
    assert candidate.is_dir()
    assert _tree_sha256(candidate) == _tree_sha256(stage)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle worker")
def test_worker_rolls_back_pointer_after_post_commit_failure(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"

    result = _run_worker(install_root, state_root, stage, fault_at="pointer_committed")

    assert result.returncode != 0
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert current["active_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
    assert old_runtime.is_dir()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / (("1" * 32) + ".json")).read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert job["rolled_back"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle worker")
def test_worker_failure_before_pointer_keeps_previous_runtime_active(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"

    result = _run_worker(install_root, state_root, stage, fault_at="service_stopped")

    assert result.returncode != 0
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert current["active_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
    assert old_runtime.is_dir()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / (("1" * 32) + ".json")).read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert job["rolled_back"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_restores_pointer_after_worker_process_disappears(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "3" * 32
    previous_version = "0.3.2"
    previous_revision = "d" * 40
    previous_relative = _runtime_relative(previous_version, previous_revision)
    _write_runtime(install_root / Path(previous_relative), previous_version, previous_revision)
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)

    original = {
        **json.loads(metadata.read_text(encoding="utf-8")),
        "previous_runtime": previous_relative,
        "generation": 7,
    }
    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "installation-before.json").write_text(json.dumps(original), encoding="utf-8")
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": _runtime_relative(OLD_VERSION, OLD_REVISION),
                "new_relative": new_relative,
                "runtime_created": True,
                "outcome": "pending",
            }
        ),
        encoding="utf-8",
    )
    committed = {
        **original,
        "active_runtime": new_relative,
        "previous_runtime": _runtime_relative(OLD_VERSION, OLD_REVISION),
        "generation": 8,
    }
    metadata.write_text(json.dumps(committed), encoding="utf-8")
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True, exist_ok=True)
    (transaction / "journal.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "phase": "pointer_committed",
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_runtime": str(old_runtime),
                "new_runtime": str(new_runtime),
                "old_relative": _runtime_relative(OLD_VERSION, OLD_REVISION),
                "new_relative": new_relative,
                "previous_metadata": original,
                "cadence_snapshot": "",
            }
        ),
        encoding="utf-8",
    )

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode == 0, result.stdout + result.stderr
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert current["active_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
    assert current["previous_runtime"] == previous_relative
    assert current["generation"] == 7
    assert not protected_recovery.exists()
    assert not new_runtime.exists()
    journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8-sig"))
    assert journal["phase"] == "rolled_back"
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert job["rolled_back"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_handles_crash_after_service_stop_before_pointer_commit(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "5" * 32
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True, exist_ok=True)
    (transaction / "journal.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "phase": "recovery_armed",
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_runtime": str(old_runtime),
                "new_runtime": str(new_runtime),
                "old_relative": _runtime_relative(OLD_VERSION, OLD_REVISION),
                "new_relative": new_relative,
                "runtime_created": True,
                "cadence_snapshot": "",
            }
        ),
        encoding="utf-8",
    )

    missing_protected = _run_recover(install_root, state_root, job_id)

    assert missing_protected.returncode != 0
    assert new_runtime.is_dir()
    original = json.loads(metadata.read_text(encoding="utf-8"))
    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "installation-before.json").write_text(json.dumps(original), encoding="utf-8")
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": _runtime_relative(OLD_VERSION, OLD_REVISION),
                "new_relative": new_relative,
                "runtime_created": False,
                "outcome": "pending",
            }
        ),
        encoding="utf-8",
    )

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode == 0, result.stdout + result.stderr
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert current["active_runtime"] == _runtime_relative(OLD_VERSION, OLD_REVISION)
    assert new_runtime.is_dir()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert job["rolled_back"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_uses_protected_snapshot_when_pointer_and_candidate_are_damaged(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "6" * 32
    old_relative = _runtime_relative(OLD_VERSION, OLD_REVISION)
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)
    original = json.loads(metadata.read_text(encoding="utf-8"))

    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "installation-before.json").write_text(json.dumps(original), encoding="utf-8")
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": old_relative,
                "new_relative": new_relative,
                "runtime_created": True,
                "outcome": "pending",
            }
        ),
        encoding="utf-8",
    )
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True)
    (transaction / "journal.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "phase": "pointer_committed",
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_runtime": str(old_runtime),
                "new_runtime": str(new_runtime),
                "old_relative": old_relative,
                "new_relative": new_relative,
                "cadence_snapshot": "",
            }
        ),
        encoding="utf-8",
    )
    metadata.write_text("{broken", encoding="utf-8")
    (new_runtime / "install_manifest.json").unlink()

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode == 0, result.stdout + result.stderr
    restored = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert restored["active_runtime"] == old_relative
    assert old_runtime.is_dir()
    assert not new_runtime.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_completed_protected_outcome_only_cleans_recovery_state(tmp_path: Path) -> None:
    install_root, _, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "7" * 32
    old_relative = _runtime_relative(OLD_VERSION, OLD_REVISION)
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)
    original = json.loads(metadata.read_text(encoding="utf-8"))
    metadata.write_text(
        json.dumps(
            {
                **original,
                "active_runtime": new_relative,
                "previous_runtime": old_relative,
                "generation": 2,
            }
        ),
        encoding="utf-8",
    )
    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "installation-before.json").write_text(json.dumps(original), encoding="utf-8")
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": old_relative,
                "new_relative": new_relative,
                "runtime_created": True,
                "outcome": "completed",
            }
        ),
        encoding="utf-8",
    )
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True)
    (transaction / "journal.json").write_text(
        json.dumps({"schema": 3, "product": "Insta360_HW", "job_id": job_id, "phase": "completed"}),
        encoding="utf-8",
    )

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode == 0, result.stdout + result.stderr
    current = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert current["active_runtime"] == new_relative
    assert new_runtime.is_dir()
    assert not protected_recovery.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_does_not_depend_on_mutable_transaction_directory(tmp_path: Path) -> None:
    install_root, old_runtime, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "8" * 32
    old_relative = _runtime_relative(OLD_VERSION, OLD_REVISION)
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)
    original = json.loads(metadata.read_text(encoding="utf-8"))
    metadata.write_text("{broken", encoding="utf-8")

    protected_recovery = install_root / ".recovery" / job_id
    protected_recovery.mkdir(parents=True)
    (protected_recovery / "installation-before.json").write_text(json.dumps(original), encoding="utf-8")
    (protected_recovery / "transaction.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_relative": old_relative,
                "new_relative": new_relative,
                "runtime_created": True,
                "outcome": "pending",
            }
        ),
        encoding="utf-8",
    )

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode == 0, result.stdout + result.stderr
    restored = json.loads(metadata.read_text(encoding="utf-8-sig"))
    assert restored["active_runtime"] == old_relative
    assert old_runtime.is_dir()
    assert not new_runtime.exists()
    assert not protected_recovery.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lifecycle recovery")
def test_recovery_rejects_tampered_runtime_pointer(tmp_path: Path) -> None:
    install_root, _, stage, metadata = _prepare_layout(tmp_path)
    state_root = tmp_path / "state"
    job_id = "4" * 32
    new_relative = _runtime_relative(NEW_VERSION, NEW_REVISION)
    new_runtime = install_root / Path(new_relative)
    new_runtime.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(new_runtime)

    original = json.loads(metadata.read_text(encoding="utf-8"))
    committed = {
        **original,
        "active_runtime": new_relative,
        "previous_runtime": _runtime_relative(OLD_VERSION, OLD_REVISION),
        "generation": 2,
    }
    metadata.write_text(json.dumps(committed), encoding="utf-8")
    transaction = state_root / "lifecycle" / "v3" / "transactions" / job_id
    transaction.mkdir(parents=True, exist_ok=True)
    (transaction / "journal.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "job_id": job_id,
                "phase": "pointer_committed",
                "install_root": str(install_root),
                "state_root": str(state_root),
                "old_runtime": str(install_root / Path(_runtime_relative(OLD_VERSION, OLD_REVISION))),
                "new_runtime": str(new_runtime),
                "old_relative": "../outside",
                "new_relative": new_relative,
                "previous_metadata": original,
                "cadence_snapshot": "",
            }
        ),
        encoding="utf-8",
    )

    result = _run_recover(install_root, state_root, job_id)

    assert result.returncode != 0
    current = json.loads(metadata.read_text(encoding="utf-8"))
    assert current["active_runtime"] == new_relative
