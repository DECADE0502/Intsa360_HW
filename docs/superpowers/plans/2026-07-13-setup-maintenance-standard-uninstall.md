# Setup Maintenance And Standard Uninstall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rerunning Setup enter a clear maintenance mode and route Setup, Windows Settings, and Geek Uninstaller through one standard Inno uninstaller.

**Architecture:** `HWAgent_Setup.iss` remains the single owner of installation and uninstall registration. A custom Inno option page selects repair, uninstall, or cancel before `PrepareToInstall`; uninstall launches the registered `unins000.exe` and exits Setup without opening an install transaction. Existing lifecycle PowerShell remains the only owner of service, Cadence, and user-data cleanup.

**Tech Stack:** Inno Setup 6 Pascal Script, PowerShell 5.1 lifecycle scripts, Python `unittest`/`pytest`, existing release builder.

---

## File Map

- Modify `HWAgent_Setup.iss`: maintenance detection/page, uninstaller launch, standard registration directives, uninstall command-line policy.
- Modify `tests/test_distribution_install.py`: static contracts for the maintenance page and command-line modes.
- Verify `scripts/lifecycle/Uninstall.ps1`: existing cleanup behavior remains unchanged and is exercised by current executable tests.

### Task 1: Maintenance Mode Before Installation

**Files:**
- Modify: `tests/test_distribution_install.py`
- Modify: `HWAgent_Setup.iss`

- [x] **Step 1: Write failing maintenance-mode tests**

Add assertions that `ExistingInstallPage` is a `TInputOptionWizardPage`, contains repair/uninstall/cancel options, defaults to repair, and handles uninstall before `PrepareToInstall` through `NextButtonClick`.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_distribution_install.py -k "maintenance or existing_install"
```

Expected: failure because the current page is informational and has no maintenance actions.

- [x] **Step 3: Implement the maintenance page**

Use these Pascal Script boundaries:

```pascal
const
  MAINTENANCE_REPAIR = 0;
  MAINTENANCE_UNINSTALL = 1;
  MAINTENANCE_CANCEL = 2;

ExistingInstallPage := CreateInputOptionPage(..., True, False);
ExistingInstallPage.Add(RepairLabel);
ExistingInstallPage.Add('卸载 Insta360硬件提效平台');
ExistingInstallPage.Add('取消，不做任何更改');
ExistingInstallPage.SelectedValueIndex := MAINTENANCE_REPAIR;
```

`NextButtonClick` must launch `ExistingUninstaller` with `ewNoWait` only for the uninstall option, close Setup without confirmation through `CancelButtonClick`, and never enter `PrepareToInstall` on uninstall/cancel.

- [x] **Step 4: Run focused tests and compile Inno Setup**

Run:

```powershell
python -m pytest -q tests/test_distribution_install.py -k "maintenance or existing_install"
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" HWAgent_Setup.iss
```

Expected: tests pass and compiler reports `Successful compile`.

### Task 2: Standard Windows And Geek Uninstall Contract

**Files:**
- Modify: `tests/test_distribution_install.py`
- Modify: `HWAgent_Setup.iss`

- [x] **Step 1: Write failing standard-registration tests**

Assert the stable `AppId`, explicit `Uninstallable=yes`, explicit `CreateUninstallRegKey=yes`, display name/icon/install location behavior, and absence of a second custom uninstall executable.

- [x] **Step 2: Write failing uninstall-mode tests**

Assert command-line parsing through `ParamCount`/`ParamStr`, mutually exclusive `/PURGEDATA` and `/PRESERVEDATA`, and `UninstallSilent` defaulting to preserved user data.

- [x] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_distribution_install.py -k "standard_uninstall or uninstall_command_line"
```

Expected: failure because the explicit directives and custom mode parameters do not exist.

- [x] **Step 4: Implement registration and command-line policy**

Add:

```ini
Uninstallable=yes
CreateUninstallRegKey=yes
```

Implement case-insensitive parameter detection with `ParamCount` and `ParamStr`. `/PURGEDATA` selects `PurgeData`, `/PRESERVEDATA` selects `PreserveData`, both together abort, and silent uninstall without either flag preserves data.

- [x] **Step 5: Run focused and lifecycle uninstall tests**

Run:

```powershell
python -m pytest -q tests/test_distribution_install.py -k "standard_uninstall or uninstall_command_line or preserve_uninstall or purge_uninstall"
```

Expected: all selected tests pass.

### Task 3: Distribution Verification

**Files:**
- Generated: `D:\desktop\工具集\Insta360_HW_Setup.exe`

- [x] **Step 1: Run lifecycle regression tests**

```powershell
python -m pytest -q tests/test_distribution_install.py tests/test_lifecycle_v2_contract.py tests/test_lifecycle_v2_worker.py
```

Expected: all tests pass.

- [x] **Step 2: Build the installer**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

Expected: `Installer ready: D:\desktop\工具集\Insta360_HW_Setup.exe`.

- [x] **Step 3: Run the full release gate**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\pre_release_check.ps1 -SkipNetwork
```

Expected: PowerShell parsing, pytest, frontend build, and manifest validation all pass.

- [x] **Step 4: Record artifact identity without installing it**

```powershell
Get-Item D:\desktop\工具集\Insta360_HW_Setup.exe
Get-FileHash -Algorithm SHA256 D:\desktop\工具集\Insta360_HW_Setup.exe
```

Do not run Setup automatically; the user validates maintenance mode manually against the installed runtime.
