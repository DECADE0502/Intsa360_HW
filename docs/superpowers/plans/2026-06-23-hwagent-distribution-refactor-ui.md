# HWAgent Distribution, Refactor, and UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a distributable Insta360 hardware efficiency tool with one-click install/update, machine-specific Cadence adaptation, faster maintainable backend modules, and a modern React UI while preserving all current BOM/netlist workflows.

**Architecture:** Keep the current working stdlib backend as the compatibility baseline, then add a distribution layer, isolate parsers/tool logic into focused modules, and introduce a Vite React frontend behind the same API surface. Capture receives only a thin GBK Tcl loader that launches the installed local tool; code and user data live outside Capture and survive OTA updates.

**Tech Stack:** PowerShell 5.1+, Tcl GBK loader, Python 3.12 stdlib/openpyxl initially, optional FastAPI/Uvicorn migration after API compatibility tests, Vite + React + TypeScript + Ant Design + TanStack Table, unittest/Node checks.

**Product Language:** All user-facing UI must be Simplified Chinese: Capture menu labels, waiting page, frontend navigation, buttons, empty states, validation errors, toast messages, report download labels, update status, installer prompts, and end-user documentation. English is allowed only for file names, API identifiers, code symbols, third-party package names, and raw imported CAD/BOM property names such as `Part Number` or `PCB Footprint`.

---

## Scope And Parallelization

This plan intentionally covers five workstreams that can run in parallel after Task 1:

- Distribution/OTA: Tasks 2-5.
- Capture integration: Tasks 3-4.
- Backend refactor and BOM field completeness: Tasks 6, 6A, 7-10.
- Frontend modernization: Tasks 11-15.
- Release verification: Tasks 16-17.

Task 1 is the shared foundation. Task 16 is the integration gate. Do not merge a workstream into release until its tests pass and the existing 6 tools still work.

## File Structure

Create or modify these files:

- Create: `VERSION`
  - Single source of truth for app version.
- Create: `config/default.json`
  - Default runtime configuration.
- Create: `scripts/lib/Paths.ps1`
  - Detect install directory, repo root, Cadence autoload locations, Git, Python.
- Create: `scripts/lib/Cadence.ps1`
  - Generate GBK Tcl loader and install it into Capture autoload.
- Create: `scripts/lib/Service.ps1`
  - Start/stop/probe the backend service.
- Create: `scripts/lib/Update.ps1`
  - Git/release update helpers.
- Create: `install.ps1`
  - One-click install entrypoint.
- Create: `update.ps1`
  - One-click update entrypoint.
- Modify: `launch_tool_suite.ps1`
  - Use config/runtime detection instead of hard-coded bundled Python.
- Modify: `iac_jump.bat`
  - Keep the hidden VBS wrapper path stable.
- Modify: `launch_tool_suite_hidden.vbs`
  - Keep hidden launch behavior.
- Modify: `cadence/iac_bom_tool.tcl`
  - Keep as template for GBK loader. InsertXMLMenu remains ASCII; AddAccessoryMenu can be Chinese.
- Create: `app/backend/config.py`
  - Load merged default/local config.
- Create: `app/backend/paths.py`
  - Resolve data/output/runtime paths.
- Create: `app/backend/parsers/cadence_pst.py`
  - Parse `pstxnet.dat` and `pstxprt.dat`.
- Create: `app/backend/parsers/bom_excel.py`
  - Shared BOM header detection and row loading.
- Create: `app/backend/capture_fields.py`
  - Canonical Capture property list, BOM template field list, and field mapping rules.
- Modify: `tools/bom/convert_cadence_bom.py`
  - Preserve Capture-visible properties from OrCAD export and emit canonical raw BOM columns.
- Modify: `app/backend/tools/bom_process.py`
  - Carry complete BOM template fields and auxiliary Capture properties through records/reports.
- Create: `app/backend/tools/netlist_tools.py`
  - Netlist compare, SMT package check, single-network check.
- Create: `app/backend/tools/bom_tools.py`
  - BOM compare/risk generic helpers moved from `analysis_tools.py`.
- Modify: `app/backend/tools/analysis_tools.py`
  - Thin compatibility facade that imports new modules.
- Create: `app/backend/update_api.py`
  - Backend endpoint helpers for version/update status.
- Modify: `app/backend/suite_app.py`
  - Add `/api/version`, `/api/update/check`, `/api/update/run`; later optionally delegate to FastAPI adapter.
- Create: `frontend/package.json`
  - Vite React frontend project.
- Create: `frontend/src/App.tsx`
  - Main app shell.
- Create: `frontend/src/api/client.ts`
  - API client.
- Create: `frontend/src/tools/*`
  - Tool pages/components.
- Create: `frontend/src/components/*`
  - Shared layout, upload, results, update status.
- Modify: `app/frontend/*`
  - Keep current static frontend until React build replaces it.
- Create: `scripts/build_frontend.ps1`
  - Build React and copy `frontend/dist` to `app/frontend`.
- Create: `tests/test_distribution_install.py`
  - Validate installer script contents and generated config behavior.
- Create: `tests/test_cadence_loader.py`
  - Validate GBK loader generation and no Chinese InsertXMLMenu regression.
- Create: `tests/test_backend_refactor_api.py`
  - Validate old API response shape remains compatible.
- Create: `tests/test_capture_bom_fields.py`
  - Validate Capture property capture and complete PLM/OA BOM field coverage.
- Create: `tests/test_update_api.py`
  - Validate version/update endpoints.
- Create: `tests/test_frontend_build.py`
  - Validate built frontend files exist after build.

---

### Task 1: Version And Config Foundation

**Files:**
- Create: `VERSION`
- Create: `config/default.json`
- Create: `app/backend/config.py`
- Create: `app/backend/paths.py`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Write the failing config/path tests**

Create `tests/test_config_paths.py`:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.backend.config import load_config
from app.backend.paths import AppPaths


class ConfigPathTests(unittest.TestCase):
    def test_load_config_merges_local_over_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "default.json").write_text(
                json.dumps({"port_range": [8765, 8775], "cadence": {"menu": "Insta360 BOM"}}),
                encoding="utf-8",
            )
            (root / "config" / "local.json").write_text(
                json.dumps({"port_range": [9000, 9001]}),
                encoding="utf-8",
            )

            cfg = load_config(root)

            self.assertEqual(cfg["port_range"], [9000, 9001])
            self.assertEqual(cfg["cadence"]["menu"], "Insta360 BOM")

    def test_app_paths_create_stable_data_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            paths.ensure_runtime_dirs()

            self.assertTrue(paths.data_dir.exists())
            self.assertTrue(paths.inbox_dir.exists())
            self.assertTrue(paths.outputs_dir.exists())
            self.assertTrue(paths.runtime_log_dir.exists())
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_config_paths -v
```

Expected: FAIL because `app.backend.config` and `app.backend.paths` do not exist.

- [ ] **Step 3: Add version and default config**

Create `VERSION`:

```text
0.2.0-dev
```

Create `config/default.json`:

```json
{
  "app_name": "Insta360 HWAgent",
  "port_range": [8765, 8775],
  "python": {
    "preferred": "bundled",
    "path": ""
  },
  "cadence": {
    "menu_ascii": "Insta360 BOM",
    "accessory_menu_cn": "硬件效率工具集",
    "autoload_dirs": []
  },
  "update": {
    "mode": "git",
    "repo": "",
    "branch": "main",
    "preserve_dirs": ["data", "config/local.json"]
  }
}
```

- [ ] **Step 4: Implement config loader**

Create `app/backend/config.py`:

```python
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(root: Path) -> dict[str, Any]:
    config_dir = root / "config"
    default_cfg = _read_json(config_dir / "default.json")
    local_cfg = _read_json(config_dir / "local.json")
    return _deep_merge(default_cfg, local_cfg)
```

- [ ] **Step 5: Implement path helper**

Create `app/backend/paths.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def runtime_log_dir(self) -> Path:
        return self.data_dir / "reports" / "runtime"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    def ensure_runtime_dirs(self) -> None:
        for path in [self.data_dir, self.inbox_dir, self.outputs_dir, self.runtime_log_dir, self.config_dir]:
            path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_config_paths -v
```

Expected: OK.

- [ ] **Step 7: Commit**

```powershell
git add VERSION config/default.json app/backend/config.py app/backend/paths.py tests/test_config_paths.py
git commit -m "feat: add versioned config and path helpers"
```

If this workspace is not a Git repository, record the commit command in the final task notes and continue.

---

### Task 2: PowerShell Shared Libraries For Install/Update

**Files:**
- Create: `scripts/lib/Paths.ps1`
- Create: `scripts/lib/Service.ps1`
- Create: `tests/test_distribution_install.py`

- [ ] **Step 1: Write failing tests for script contracts**

Create `tests/test_distribution_install.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionInstallTests(unittest.TestCase):
    def test_paths_library_exposes_required_functions(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Paths.ps1").read_text(encoding="utf-8")
        for name in [
            "Resolve-HWAgentInstallRoot",
            "Find-CadenceAutoLoadDirs",
            "Find-HWAgentPython",
            "Find-GitExecutable",
        ]:
            self.assertIn(f"function {name}", text)

    def test_service_library_exposes_required_functions(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Service.ps1").read_text(encoding="utf-8")
        for name in ["Test-HWAgentHttpReady", "Stop-HWAgentService", "Start-HWAgentService"]:
            self.assertIn(f"function {name}", text)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_distribution_install -v
```

Expected: FAIL because files do not exist.

- [ ] **Step 3: Implement path detection library**

Create `scripts/lib/Paths.ps1`:

```powershell
function Resolve-HWAgentInstallRoot {
  param([string]$InstallDir = "")
  if ($InstallDir -ne "") { return (Resolve-Path -LiteralPath $InstallDir).Path }
  return (Join-Path $env:LOCALAPPDATA "Insta360\HWAgent")
}

function Find-GitExecutable {
  $cmd = Get-Command git.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return ""
}

function Find-HWAgentPython {
  param([string]$Root)
  $candidates = @(
    (Join-Path $Root "runtime\python\python.exe"),
    "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return ""
}

function Find-CadenceAutoLoadDirs {
  param([string]$ExplicitDir = "")
  $targets = New-Object System.Collections.Generic.List[string]
  if ($ExplicitDir -ne "") { $targets.Add($ExplicitDir) }
  if ($env:HOME) {
    $targets.Add((Join-Path $env:HOME "cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"))
  }
  $known = @(
    "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad",
    "C:\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
  )
  foreach ($dir in $known) {
    if (Test-Path -LiteralPath $dir) { $targets.Add($dir) }
  }
  foreach ($drive in "C:\", "D:\") {
    if (Test-Path -LiteralPath $drive) {
      Get-ChildItem -Path $drive -Recurse -Filter "PLMMenu.tcl" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "cdssetup" } |
        Select-Object -First 3 |
        ForEach-Object { $targets.Add($_.DirectoryName) }
    }
  }
  return $targets | Select-Object -Unique
}
```

- [ ] **Step 4: Implement service library**

Create `scripts/lib/Service.ps1`:

```powershell
function Test-HWAgentHttpReady {
  param([int]$Port, [string[]]$RequiredTools)
  try {
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/tools")
    $request.Timeout = 2000
    $response = $request.GetResponse()
    $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
    $content = $reader.ReadToEnd()
    $reader.Close()
    $response.Close()
    $tools = ($content | ConvertFrom-Json).tools
    foreach ($toolId in $RequiredTools) {
      $tool = $tools | Where-Object { $_.id -eq $toolId } | Select-Object -First 1
      if ($null -eq $tool -or $tool.status -ne "available") { return $false }
    }
    return $true
  } catch {
    return $false
  }
}

function Stop-HWAgentService {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -like "python*" -and $_.CommandLine -and $_.CommandLine.Contains("suite_app.py") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Start-HWAgentService {
  param([string]$Root, [string]$Python, [int]$Port)
  Start-Process -FilePath $Python `
    -ArgumentList "app\backend\suite_app.py --port $Port" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden | Out-Null
}
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_distribution_install -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lib/Paths.ps1 scripts/lib/Service.ps1 tests/test_distribution_install.py
git commit -m "feat: add distribution PowerShell libraries"
```

---

### Task 3: Cadence Loader Generator

**Files:**
- Create: `scripts/lib/Cadence.ps1`
- Modify: `cadence/iac_bom_tool.tcl`
- Test: `tests/test_cadence_loader.py`

- [ ] **Step 1: Write failing tests for GBK loader rules**

Create `tests/test_cadence_loader.py`:

```python
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CadenceLoaderTests(unittest.TestCase):
    def test_cadence_library_contains_gbk_writer_and_ascii_insert_menu(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")
        self.assertIn("function New-HWAgentCadenceLoader", text)
        self.assertIn("GetEncoding(936)", text)

    def test_template_keeps_insert_xml_menu_ascii_and_accessory_chinese(self) -> None:
        text = (ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8")
        insert_lines = [line for line in text.splitlines() if "InsertXMLMenu" in line]
        self.assertTrue(insert_lines)
        self.assertTrue(all("硬件效率工具集" not in line for line in insert_lines))
        self.assertIn('AddAccessoryMenu "硬件效率工具集"', text)

    def test_generated_loader_is_cp936_decodable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "iac_bom_tool.tcl"
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"New-HWAgentCadenceLoader -Template '{ROOT / 'cadence' / 'iac_bom_tool.tcl'}' "
                f"-Output '{out}' -ToolRoot 'C:/Insta360/HWAgent'",
            ]
            subprocess.run(cmd, check=True)
            decoded = out.read_bytes().decode("cp936")
            self.assertIn('set ::IAC_ROOT "C:/Insta360/HWAgent"', decoded)
            self.assertIn('AddAccessoryMenu "硬件效率工具集"', decoded)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_cadence_loader -v
```

Expected: FAIL because `scripts/lib/Cadence.ps1` does not exist.

- [ ] **Step 3: Implement Cadence loader generator**

Create `scripts/lib/Cadence.ps1`:

```powershell
function New-HWAgentCadenceLoader {
  param(
    [Parameter(Mandatory=$true)][string]$Template,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$ToolRoot
  )
  $rootFwd = $ToolRoot -replace "\\", "/"
  $content = (Get-Content -Raw -Encoding UTF8 -LiteralPath $Template) -replace "\{\{TOOL_ROOT\}\}", $rootFwd
  $encoding = [System.Text.Encoding]::GetEncoding(936)
  [System.IO.File]::WriteAllText($Output, $content, $encoding)
}

function Install-HWAgentCadenceLoader {
  param(
    [Parameter(Mandatory=$true)][string]$Template,
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [Parameter(Mandatory=$true)][string[]]$AutoLoadDirs
  )
  $temp = Join-Path $ToolRoot "cadence\iac_bom_tool.deployed.tcl"
  New-HWAgentCadenceLoader -Template $Template -Output $temp -ToolRoot $ToolRoot
  foreach ($dir in $AutoLoadDirs) {
    try {
      New-Item -ItemType Directory -Force -Path $dir | Out-Null
      Copy-Item -LiteralPath $temp -Destination (Join-Path $dir "iac_bom_tool.tcl") -Force
      return $dir
    } catch {
      Write-Host "Cadence loader install failed: $dir $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
  }
  throw "No writable Cadence capAutoLoad directory found."
}
```

- [ ] **Step 4: Verify template menu rule**

Ensure `cadence/iac_bom_tool.tcl` contains:

```tcl
InsertXMLMenu [list [list "IACBOM"] "" "" [list "popup" "Insta360 BOM" "" "" "" "" ""] ""]
AddAccessoryMenu "硬件效率工具集" "打开工具集" "::IAC::OpenTool"
AddAccessoryMenu "硬件效率工具集" "导出并处理 BOM" "::IAC::ExportAndProcess"
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_cadence_loader -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lib/Cadence.ps1 cadence/iac_bom_tool.tcl tests/test_cadence_loader.py
git commit -m "feat: add robust Cadence GBK loader generator"
```

---

### Task 4: One-Click Installer

**Files:**
- Create: `install.ps1`
- Modify: `cadence/README.md`
- Test: `tests/test_distribution_install.py`

- [ ] **Step 1: Add failing installer tests**

Append to `tests/test_distribution_install.py`:

```python
    def test_install_script_uses_shared_libraries_and_preserves_user_data(self) -> None:
        text = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("scripts\\lib\\Paths.ps1", text)
        self.assertIn("scripts\\lib\\Cadence.ps1", text)
        self.assertIn("config\\local.json", text)
        self.assertIn("Install-HWAgentCadenceLoader", text)
        self.assertNotIn("Remove-Item -Recurse $InstallRoot", text)
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_distribution_install -v
```

Expected: FAIL because `install.ps1` does not exist.

- [ ] **Step 3: Implement installer**

Create `install.ps1`:

```powershell
param(
  [string]$InstallDir = "",
  [string]$CaptureAutoLoadDir = "",
  [string]$GitRepo = "",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$ScriptRoot\scripts\lib\Paths.ps1"
. "$ScriptRoot\scripts\lib\Cadence.ps1"

$InstallRoot = Resolve-HWAgentInstallRoot -InstallDir $InstallDir
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

if ((Resolve-Path -LiteralPath $ScriptRoot).Path -ne (Resolve-Path -LiteralPath $InstallRoot -ErrorAction SilentlyContinue).Path) {
  robocopy $ScriptRoot $InstallRoot /MIR /XD data .git node_modules frontend\node_modules /XF config\local.json | Out-Null
}

$configDir = Join-Path $InstallRoot "config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$localConfig = Join-Path $configDir "local.json"
if (-not (Test-Path -LiteralPath $localConfig)) {
  @{
    install_dir = $InstallRoot
    git_repo = $GitRepo
    branch = $Branch
    installed_at = (Get-Date -Format s)
  } | ConvertTo-Json -Depth 4 | Out-File -FilePath $localConfig -Encoding utf8
}

$autoLoadDirs = @(Find-CadenceAutoLoadDirs -ExplicitDir $CaptureAutoLoadDir)
$installedDir = Install-HWAgentCadenceLoader `
  -Template (Join-Path $InstallRoot "cadence\iac_bom_tool.tcl") `
  -ToolRoot $InstallRoot `
  -AutoLoadDirs $autoLoadDirs

Write-Host "HWAgent installed at: $InstallRoot" -ForegroundColor Green
Write-Host "Cadence loader installed at: $installedDir\iac_bom_tool.tcl" -ForegroundColor Green
Write-Host "Restart OrCAD Capture, then use Accessories -> 硬件效率工具集." -ForegroundColor Cyan
```

- [ ] **Step 4: Update README install docs**

Modify `cadence/README.md` install section to include:

```markdown
### Recommended one-click install

Run from the downloaded or cloned tool root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Optional:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:LOCALAPPDATA\Insta360\HWAgent" -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```

The installer preserves `data/` and `config/local.json` during updates.
```

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_distribution_install tests.test_cadence_loader -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add install.ps1 cadence/README.md tests/test_distribution_install.py
git commit -m "feat: add one-click installer"
```

---

### Task 5: OTA Update Script And Update API

**Files:**
- Create: `scripts/lib/Update.ps1`
- Create: `update.ps1`
- Create: `app/backend/update_api.py`
- Modify: `app/backend/suite_app.py`
- Test: `tests/test_update_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_update_api.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path

from app.backend.update_api import read_version, update_script_path


ROOT = Path(__file__).resolve().parents[1]


class UpdateApiTests(unittest.TestCase):
    def test_read_version_from_version_file(self) -> None:
        self.assertRegex(read_version(ROOT), r"\d+\.\d+\.\d+")

    def test_update_script_path_points_to_root_update_ps1(self) -> None:
        self.assertEqual(update_script_path(ROOT), ROOT / "update.ps1")

    def test_suite_app_exposes_update_routes(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        self.assertIn('"/api/version"', text)
        self.assertIn('"/api/update/check"', text)
        self.assertIn('"/api/update/run"', text)
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_update_api -v
```

Expected: FAIL because `update_api.py` and routes do not exist.

- [ ] **Step 3: Implement update PowerShell helpers**

Create `scripts/lib/Update.ps1`:

```powershell
function Invoke-HWAgentGitUpdate {
  param([string]$Root, [string]$Branch = "main")
  $git = Get-Command git.exe -ErrorAction SilentlyContinue
  if (-not $git) { throw "git.exe not found; use release zip update mode." }
  Push-Location $Root
  try {
    & $git.Source fetch origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
    & $git.Source pull --ff-only origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
  } finally {
    Pop-Location
  }
}
```

Create `update.ps1`:

```powershell
param([string]$Branch = "main", [switch]$NoRestart)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$Root\scripts\lib\Service.ps1"
. "$Root\scripts\lib\Update.ps1"
. "$Root\scripts\lib\Paths.ps1"
. "$Root\scripts\lib\Cadence.ps1"

Stop-HWAgentService
Invoke-HWAgentGitUpdate -Root $Root -Branch $Branch

$dirs = @(Find-CadenceAutoLoadDirs)
$null = Install-HWAgentCadenceLoader -Template (Join-Path $Root "cadence\iac_bom_tool.tcl") -ToolRoot $Root -AutoLoadDirs $dirs

$python = Find-HWAgentPython -Root $Root
if ($python -eq "") { throw "Python not found." }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed after update." }

if (-not $NoRestart) {
  & (Join-Path $Root "launch_tool_suite.ps1") -Restart
}
```

- [ ] **Step 4: Implement backend update API helper**

Create `app/backend/update_api.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.exists():
        return "0.0.0"
    return path.read_text(encoding="utf-8").strip()


def update_script_path(root: Path) -> Path:
    return root / "update.ps1"


def check_update(root: Path) -> dict[str, object]:
    return {"version": read_version(root), "update_script": str(update_script_path(root))}


def run_update(root: Path) -> dict[str, object]:
    script = update_script_path(root)
    if not script.exists():
        return {"status": "error", "error": "update.ps1 not found"}
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], cwd=str(root))
    return {"status": "ok", "message": "Update started"}
```

- [ ] **Step 5: Add routes to `suite_app.py`**

In `do_GET`, add before static handling:

```python
if parsed.path == "/api/version":
    from app.backend import update_api
    self._send_json({"status": "ok", "version": update_api.read_version(ROOT)})
    return
if parsed.path == "/api/update/check":
    from app.backend import update_api
    self._send_json({"status": "ok", **update_api.check_update(ROOT)})
    return
```

In `do_POST`, add:

```python
if parsed.path == "/api/update/run":
    from app.backend import update_api
    self._send_json(update_api.run_update(ROOT))
    return
```

Use the existing `ROOT` constant or equivalent root path already used by `suite_app.py`.

- [ ] **Step 6: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_update_api -v
```

Expected: OK.

- [ ] **Step 7: Commit**

```powershell
git add scripts/lib/Update.ps1 update.ps1 app/backend/update_api.py app/backend/suite_app.py tests/test_update_api.py
git commit -m "feat: add OTA update script and API"
```

---

### Task 6: Extract Cadence PST Parsers

**Files:**
- Create: `app/backend/parsers/__init__.py`
- Create: `app/backend/parsers/cadence_pst.py`
- Modify: `app/backend/tools/analysis_tools.py`
- Test: `tests/test_netlist_analysis.py`

- [ ] **Step 1: Add parser import test**

Append to `tests/test_netlist_analysis.py`:

```python
    def test_public_pst_parser_module_matches_tool_parser(self) -> None:
        from app.backend.parsers.cadence_pst import parse_net_file, parse_part_file

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_netlist(
                folder,
                nets="NET_NAME\n'NC_1'\nNODE_NAME R1 1\n",
                parts="PART_NAME\n R1 'RES_NP_R0201_10K':;\n",
            )
            self.assertEqual(parse_net_file(folder)["NC_1"]["nodes"], ["R1.1"])
            self.assertEqual(parse_part_file(folder)["R1"], "RES_NP_R0201_10K")
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_netlist_analysis -v
```

Expected: FAIL because parser module does not exist.

- [ ] **Step 3: Create parser module**

Move the current parser helpers from `analysis_tools.py` into `app/backend/parsers/cadence_pst.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_NAT_RE = re.compile(r"(\d+)")


def natural_key(ref: str) -> list[object]:
    return [int(token) if token.isdigit() else token.lower() for token in _NAT_RE.split(ref)]


def read_text_guess(path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "cp936"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_pst_string(value: str) -> str:
    text = value.strip().rstrip(";").rstrip(":").strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1]
    return text.strip()


def natural_join(values: Iterable[str]) -> str:
    return ",".join(sorted(set(values), key=natural_key))


def parse_node_tokens(line: str) -> tuple[str, str] | None:
    tokens = line.strip().split()
    if len(tokens) >= 3 and tokens[0].upper() == "NODE_NAME":
        return tokens[1], tokens[2]
    return None


def parse_net_file(folder: Path) -> dict[str, dict[str, list[str]]]:
    path = folder / "pstxnet.dat"
    if not path.exists():
        raise ValueError(f"缺少 pstxnet.dat: {folder}")
    nets: dict[str, dict[str, set[str]]] = {}
    current: str | None = None
    pending_name = False
    for raw in read_text_guess(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "NET_NAME":
            pending_name = True
            current = None
            continue
        if pending_name:
            name = clean_pst_string(line)
            if name and not name.startswith("@") and "=" not in name:
                current = name
                nets.setdefault(current, {"refs": set(), "pins": set(), "nodes": set()})
                pending_name = False
            continue
        node = parse_node_tokens(line)
        if node and current:
            ref, pin = node
            nets[current]["refs"].add(ref)
            nets[current]["pins"].add(pin)
            nets[current]["nodes"].add(f"{ref}.{pin}")
    return {
        name: {
            "refs": sorted(data["refs"], key=natural_key),
            "pins": sorted(data["pins"], key=natural_key),
            "nodes": sorted(data["nodes"], key=natural_key),
        }
        for name, data in nets.items()
    }


def parse_part_file(folder: Path) -> dict[str, str]:
    path = folder / "pstxprt.dat"
    if not path.exists():
        raise ValueError(f"缺少 pstxprt.dat: {folder}")
    parts: dict[str, str] = {}
    part_re = re.compile(r"^([A-Za-z]+\d+[A-Za-z0-9_-]*)\s+'([^']+)'")
    for raw in read_text_guess(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        match = part_re.match(line)
        if match:
            parts[match.group(1)] = match.group(2).strip()
    return parts
```

Create `app/backend/parsers/__init__.py`:

```python
"""Shared file parsers for HWAgent backend tools."""
```

- [ ] **Step 4: Update `analysis_tools.py` facade**

Replace local calls:

```python
from app.backend.parsers.cadence_pst import natural_join as _natural_join
from app.backend.parsers.cadence_pst import parse_net_file as _parse_net_file
from app.backend.parsers.cadence_pst import parse_part_file as _parse_part_file
```

Remove duplicated parser functions only after tests pass once with the imports. Keep `_package_tokens` and `_package_matches` in `analysis_tools.py` until Task 7.

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_netlist_analysis -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add app/backend/parsers tests/test_netlist_analysis.py app/backend/tools/analysis_tools.py
git commit -m "refactor: extract Cadence PST parsers"
```

---


### Task 6A: Capture Property Coverage And Complete BOM Field Mapping

**Files:**
- Create: `app/backend/capture_fields.py`
- Modify: `cadence/iac_bom_tool.tcl`
- Modify: `tools/bom/convert_cadence_bom.py`
- Modify: `app/backend/tools/bom_process.py`
- Modify: `app/frontend/app.js`
- Test: `tests/test_capture_bom_fields.py`
- Test: `tests/test_cadence_integration.py`
- Test: `tests/test_bom_process_conflicts.py`

**Field Strategy:**

The Capture property grid in the screenshot exposes these relevant properties. Keep them in the system even when they are not final PLM columns:

```text
Color
Designator
Graphic
ID
Implementation
Implementation Path
Implementation Type
Location X-Coordinate
Location Y-Coordinate
Name
Part Number
Part Reference
Part Type
PCB Footprint
PCB封装
Power Pins Visible
Primitive
Reference
Source Library
Source Package
Source Part
SPLIT_INST
SWAP_INFO
Value
等级
规格型号
器件描述（新整理）
物料名称
```

Use three layers:

```text
Layer 1: Final PLM/OA template fields
父项编码, 描述, 子项编码, 名称, 型号, 描述, 单位, 数量, 位号, 备注,
物料优选等级, 物料优选等级备注, 替代组编码, 替代策略, 替代方式,
替代优先级, 发料方式, 是否参与MRP运算, 是否跳层

Layer 2: System auxiliary fields used by checks and fallback mapping
Value, PCB Footprint, PCB封装, Part Type, Part Reference, Source Package, Source Part

Layer 3: Trace/debug fields preserved in raw export and review reports
Color, Designator, Graphic, ID, Implementation, Implementation Path, Implementation Type,
Location X-Coordinate, Location Y-Coordinate, Name, Power Pins Visible, Primitive,
Source Library, SPLIT_INST, SWAP_INFO
```

Final BOM mapping rules:

```text
父项编码             <- user input parent_code
描述                 <- user input parent_desc or board name
子项编码             <- Part Number
名称                 <- 物料名称, fallback Part Type, fallback Name
型号                 <- 规格型号, fallback Value, fallback PCB封装, fallback PCB Footprint
描述                 <- 器件描述（新整理）, fallback Description, fallback Value
单位                 <- source 单位 if present, fallback ea
数量                 <- merged ref count, or explicit extra qty
位号                 <- Reference
备注                 <- source 备注 if present, fallback blank
物料优选等级         <- 等级, fallback 物料优选等级
物料优选等级备注     <- source 物料优选等级备注 if present, fallback blank
替代组编码           <- source 替代组编码 if present, fallback blank
替代策略             <- source 替代策略 if present, fallback blank
替代方式             <- source 替代方式 if present, fallback blank
替代优先级           <- source 替代优先级 if present, fallback blank
发料方式             <- source 发料方式 if present, fallback 直接发料
是否参与MRP运算      <- source 是否参与MRP运算 if present, fallback 是
是否跳层             <- source 是否跳层 if present, fallback 否
```

- [ ] **Step 1: Write failing tests for Capture field constants and BOM mapping**

Create `tests/test_capture_bom_fields.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.backend.tools import bom_process

ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "tools" / "bom" / "convert_cadence_bom.py"

FULL_TEMPLATE_HEADERS = [
    "父项编码", "描述", "子项编码", "名称", "型号", "描述", "单位", "数量", "位号", "备注",
    "物料优选等级", "物料优选等级备注", "替代组编码", "替代策略", "替代方式", "替代优先级",
    "发料方式", "是否参与MRP运算", "是否跳层",
]

CAPTURE_SCREENSHOT_FIELDS = [
    "Color", "Designator", "Graphic", "ID", "Implementation", "Implementation Path", "Implementation Type",
    "Location X-Coordinate", "Location Y-Coordinate", "Name", "Part Number", "Part Reference", "Part Type",
    "PCB Footprint", "PCB封装", "Power Pins Visible", "Primitive", "Reference", "Source Library",
    "Source Package", "Source Part", "SPLIT_INST", "SWAP_INFO", "Value", "等级", "规格型号",
    "器件描述（新整理）", "物料名称",
]


class CaptureBomFieldTests(unittest.TestCase):
    def test_capture_field_constants_include_visible_capture_properties(self) -> None:
        from app.backend.capture_fields import CAPTURE_PROPERTY_FIELDS, PLM_TEMPLATE_HEADERS

        for field in CAPTURE_SCREENSHOT_FIELDS:
            self.assertIn(field, CAPTURE_PROPERTY_FIELDS)
        self.assertEqual(PLM_TEMPLATE_HEADERS, FULL_TEMPLATE_HEADERS)

    def test_converter_preserves_capture_visible_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "parts.json"
            out = tmp_path / "capture.xlsx"
            part = {field: f"v_{field}" for field in CAPTURE_SCREENSHOT_FIELDS}
            part.update(
                {
                    "Reference": "U400",
                    "Part Number": "311020100026",
                    "物料名称": "主控",
                    "规格型号": "A380",
                    "器件描述（新整理）": "SOC,A380",
                    "等级": "优选",
                }
            )
            src.write_text(json.dumps([part], ensure_ascii=False), encoding="utf-8")

            subprocess.run([sys.executable, str(CONVERTER), str(src), str(out)], check=True)

            wb = load_workbook(out, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
            row = [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            for field in CAPTURE_SCREENSHOT_FIELDS:
                self.assertIn(field, headers)
            self.assertEqual(row[headers.index("PCB封装")], "v_PCB封装")
            self.assertEqual(row[headers.index("Source Package")], "v_Source Package")
            self.assertEqual(row[headers.index("SPLIT_INST")], "v_SPLIT_INST")

    def test_bom_process_outputs_complete_plm_template_fields_with_defaults_and_source_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append([
                "Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级",
                "单位", "备注", "物料优选等级备注", "替代组编码", "替代策略", "替代方式", "替代优先级",
                "发料方式", "是否参与MRP运算", "是否跳层", "PCB封装", "Source Package",
            ])
            ws.append([
                1, 1, "U400", "311020100026", "A380", "A380", "SOC,A380", "主控", "优选",
                "pcs", "量产备注", "等级备注", "ALT-G1", "混用", "替代", "1", "直接发料", "是", "否",
                "FCCSP-691", "A380",
            ])
            wb.save(source)

            result = bom_process.process(source, ["plm"], "PARENT001", "父项描述", "TEST", [], tmp_path, "STAMP", None)
            output = result["outputs"][0]
            wb = load_workbook(output, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(2, col).value for col in range(1, 20)]
            values = [ws.cell(3, col).value for col in range(1, 20)]
            wb.close()

            self.assertEqual(headers, FULL_TEMPLATE_HEADERS)
            self.assertEqual(values, [
                "PARENT001", "父项描述", "311020100026", "主控", "A380", "SOC,A380", "pcs", 1, "U400", "量产备注",
                "优选", "等级备注", "ALT-G1", "混用", "替代", "1", "直接发料", "是", "否",
            ])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_capture_bom_fields -v
```

Expected: FAIL because `app.backend.capture_fields` does not exist and current BOM records do not preserve the extra template fields.

- [ ] **Step 3: Add canonical field definitions**

Create `app/backend/capture_fields.py`:

```python
from __future__ import annotations

CAPTURE_PROPERTY_FIELDS = [
    "Reference",
    "Part Number",
    "Value",
    "规格型号",
    "器件描述（新整理）",
    "物料名称",
    "等级",
    "PCB Footprint",
    "PCB封装",
    "Part Type",
    "Part Reference",
    "Source Package",
    "Source Part",
    "Source Library",
    "Name",
    "Designator",
    "Implementation",
    "Implementation Path",
    "Implementation Type",
    "Location X-Coordinate",
    "Location Y-Coordinate",
    "Color",
    "Graphic",
    "ID",
    "Power Pins Visible",
    "Primitive",
    "SPLIT_INST",
    "SWAP_INFO",
]

PLM_TEMPLATE_HEADERS = [
    "父项编码", "描述", "子项编码", "名称", "型号", "描述", "单位", "数量", "位号", "备注",
    "物料优选等级", "物料优选等级备注", "替代组编码", "替代策略", "替代方式", "替代优先级",
    "发料方式", "是否参与MRP运算", "是否跳层",
]

BOM_OPTIONAL_FIELDS = [
    "unit", "remark", "grade_remark", "alt_group", "alt_strategy", "alt_method", "alt_priority",
    "issue_method", "mrp", "jump_level",
]

FIELD_DEFAULTS = {
    "unit": "ea",
    "remark": "",
    "grade_remark": "",
    "alt_group": "",
    "alt_strategy": "",
    "alt_method": "",
    "alt_priority": "",
    "issue_method": "直接发料",
    "mrp": "是",
    "jump_level": "否",
}
```

- [ ] **Step 4: Update Tcl property preference list**

Modify `cadence/iac_bom_tool.tcl` `PROP_NAMES` to include every screenshot field explicitly:

```tcl
variable PROP_NAMES {
    Reference {Part Number} Value {规格型号} {器件描述（新整理）} {物料名称} {等级}
    {PCB Footprint} {PCB封装} {Part Type} {Part Reference} {Source Package} {Source Part} {Source Library}
    Name Designator Implementation {Implementation Path} {Implementation Type}
    {Location X-Coordinate} {Location Y-Coordinate} Color Graphic ID {Power Pins Visible} Primitive
    SPLIT_INST SWAP_INFO {描述} Description {物料优选等级} Manufacturer {制造商} Datasheet datasheet
    {封装} {单位} {Implementation Designator}
}
```

Keep `ReadProps` reading all `NewEffectivePropsIter` values; `PROP_NAMES` is an explicit fallback/preference list, not the only source.

- [ ] **Step 5: Update Cadence JSON converter mapping**

Modify `tools/bom/convert_cadence_bom.py`:

```python
from app.backend.capture_fields import CAPTURE_PROPERTY_FIELDS

PROP_MAP = [
    (["Reference", "Part Reference"], "Reference"),
    (["Part Number"], "Part Number"),
    (["Value"], "Value"),
    (["规格型号", "Model", "MPN"], "规格型号"),
    (["器件描述（新整理）", "描述", "Description"], "器件描述（新整理）"),
    (["物料名称", "Part Type", "Name"], "物料名称"),
    (["等级", "物料优选等级"], "等级"),
]

BASE_HEADERS = ["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"]
```

When building `headers`, append all `CAPTURE_PROPERTY_FIELDS` not already in `BASE_HEADERS`, then append unknown extra keys. This guarantees `PCB封装`, `Source Package`, `SPLIT_INST`, etc. stay in raw exported xlsx.

- [ ] **Step 6: Extend BOM source aliases and records**

Modify `app/backend/tools/bom_process.py` `SRC_ALIASES`:

```python
SRC_ALIASES.update({
    "unit": ["单位", "Unit", "UOM"],
    "remark": ["备注", "Remark", "Note"],
    "grade_remark": ["物料优选等级备注", "等级备注"],
    "alt_group": ["替代组编码"],
    "alt_strategy": ["替代策略"],
    "alt_method": ["替代方式"],
    "alt_priority": ["替代优先级"],
    "issue_method": ["发料方式", "发料"],
    "mrp": ["是否参与MRP运算"],
    "jump_level": ["是否跳层"],
    "pcb_footprint": ["PCB Footprint"],
    "pcb_package": ["PCB封装"],
    "source_package": ["Source Package"],
    "source_part": ["Source Part"],
    "part_type": ["Part Type"],
    "part_reference": ["Part Reference"],
})
```

Update `CONFLICT_FIELDS` to include only user-facing fields that affect merging:

```python
CONFLICT_FIELDS = ("name", "model", "desc", "grade")
```

Do not include trace fields in conflict signatures.

Update `load_source` to store all mapped keys. Update `build_records` groups to carry `BOM_OPTIONAL_FIELDS` using representative/default values.

- [ ] **Step 7: Update final row writers**

Modify `_plm_row` to return all 19 fields using defaults:

```python
from app.backend.capture_fields import FIELD_DEFAULTS, PLM_TEMPLATE_HEADERS

PLM_HEADERS = PLM_TEMPLATE_HEADERS


def _rec_value(rec: dict[str, object], key: str) -> object:
    value = rec.get(key)
    if value is None or value == "":
        return FIELD_DEFAULTS.get(key, "")
    return value


def _plm_row(rec: dict[str, object], parent_code: str, parent_desc: str) -> list[object]:
    return [
        parent_code,
        parent_desc,
        rec["code"],
        rec["name"],
        rec["model"],
        rec["desc"],
        _rec_value(rec, "unit"),
        rec["qty"],
        ",".join(rec["refs"]),
        _rec_value(rec, "remark"),
        rec["grade"],
        _rec_value(rec, "grade_remark"),
        _rec_value(rec, "alt_group"),
        _rec_value(rec, "alt_strategy"),
        _rec_value(rec, "alt_method"),
        _rec_value(rec, "alt_priority"),
        _rec_value(rec, "issue_method"),
        _rec_value(rec, "mrp"),
        _rec_value(rec, "jump_level"),
    ]
```

Update `write_oa` to carry the same optional fields into its 16 columns:

```python
ws.append([
    "", parent_code, parent_desc, rec["code"], rec["desc"], rec["qty"], _rec_value(rec, "unit"),
    ",".join(rec["refs"]), _rec_value(rec, "remark"), _rec_value(rec, "alt_group"),
    _rec_value(rec, "alt_strategy"), _rec_value(rec, "alt_method"), rec["grade"],
    _rec_value(rec, "issue_method"), _rec_value(rec, "mrp"), _rec_value(rec, "jump_level"),
])
```

- [ ] **Step 8: Update frontend Capture config string**

Modify `app/frontend/app.js` `CAPTURE_CONFIG` to include fields useful for raw export:

```js
const CAPTURE_CONFIG =
  "{Item}\\t{Quantity}\\t{Reference}\\t{Part Number}\\t{Value}\\t{规格型号}\\t{器件描述（新整理）}\\t{物料名称}\\t{等级}\\t{PCB Footprint}\\t{PCB封装}\\t{Part Type}\\t{Part Reference}\\t{Source Package}\\t{Source Part}";
```

Do not put all trace fields in the user-facing manual export string by default; Tcl auto-export preserves them. The manual string should stay practical.

- [ ] **Step 9: Run tests and verify pass**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_capture_bom_fields tests.test_cadence_integration tests.test_bom_process_conflicts -v
```

Expected: OK.

- [ ] **Step 10: Commit**

```powershell
git add app/backend/capture_fields.py cadence/iac_bom_tool.tcl tools/bom/convert_cadence_bom.py app/backend/tools/bom_process.py app/frontend/app.js tests/test_capture_bom_fields.py tests/test_cadence_integration.py tests/test_bom_process_conflicts.py
git commit -m "feat: preserve Capture properties and complete BOM field mapping"
```

---

### Task 7: Extract BOM Excel Parser

**Files:**
- Create: `app/backend/parsers/bom_excel.py`
- Modify: `app/backend/tools/analysis_tools.py`
- Modify: `app/backend/tools/bom_process.py` only if shared parser can be adopted without behavior changes.
- Test: existing BOM tests.

- [ ] **Step 1: Write parser behavior tests**

Create `tests/test_bom_excel_parser.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from app.backend.parsers.bom_excel import read_bom_rows


class BomExcelParserTests(unittest.TestCase):
    def test_read_bom_rows_prefers_new_description_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "内容", "器件描述（新整理）", "物料名称", "等级"])
            ws.append([1, 1, "C1", "C.001", "1uF", "0201", "旧描述", "新描述", "电容", "优选"])
            wb.save(path)

            rows = read_bom_rows(path)

            self.assertEqual(rows[0]["description"], "新描述")
            self.assertEqual(rows[0]["refs"], ["C1"])
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_bom_excel_parser -v
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Move BOM parsing helpers**

Create `app/backend/parsers/bom_excel.py` by moving these helpers from `analysis_tools.py`:

- `REF_SPLIT_RE`
- `FIELD_ALIASES`
- `_normalize_header`
- `_find_header`
- `_choose_best_column`
- `_refine_bom_mapping`
- `_split_refs`
- `_to_qty`
- `_read_bom_rows`

Expose public names:

```python
def read_bom_rows(path: Path, require_refs: bool = True) -> list[dict[str, object]]:
    return _read_bom_rows(path, require_refs=require_refs)
```

- [ ] **Step 4: Update imports in `analysis_tools.py`**

Add:

```python
from app.backend.parsers.bom_excel import read_bom_rows as _read_bom_rows
from app.backend.parsers.bom_excel import split_refs as _split_refs
from app.backend.parsers.bom_excel import to_qty as _to_qty
```

Export `split_refs` and `to_qty` from `bom_excel.py` if needed.

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_bom_excel_parser tests.test_bom_process_conflicts tests.test_netlist_analysis -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add app/backend/parsers/bom_excel.py app/backend/tools/analysis_tools.py tests/test_bom_excel_parser.py
git commit -m "refactor: extract BOM Excel parser"
```

---

### Task 8: Split Netlist Tools Module

**Files:**
- Create: `app/backend/tools/netlist_tools.py`
- Modify: `app/backend/tools/analysis_tools.py`
- Test: `tests/test_netlist_analysis.py`

- [ ] **Step 1: Add import compatibility test**

Append to `tests/test_netlist_analysis.py`:

```python
    def test_netlist_tools_module_exports_tool_runners(self) -> None:
        from app.backend.tools.netlist_tools import run_netlist_compare, run_single_network_check, run_smt_package_check

        self.assertTrue(callable(run_netlist_compare))
        self.assertTrue(callable(run_single_network_check))
        self.assertTrue(callable(run_smt_package_check))
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_netlist_analysis -v
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Create netlist tools module**

Move these functions from `analysis_tools.py` into `app/backend/tools/netlist_tools.py`:

- `_package_tokens`
- `_package_matches`
- `run_netlist_compare`
- `run_smt_package_check`
- `run_single_network_check`

Import shared helpers from `analysis_tools.py` only temporarily:

```python
from app.backend.tools.analysis_tools import _error, _output_dir, _result, _table, _write_sheets, _write_table, _compare
```

If this creates circular imports, instead move shared report helpers to `app/backend/tools/common.py` in the same task:

```python
from app.backend.tools.common import error, output_dir, result, table, write_sheets, write_table, compare
```

- [ ] **Step 4: Update compatibility facade**

In `analysis_tools.py`, import:

```python
from app.backend.tools.netlist_tools import run_netlist_compare, run_single_network_check, run_smt_package_check
```

Remove the old in-file implementations after tests pass.

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_netlist_analysis -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add app/backend/tools/netlist_tools.py app/backend/tools/analysis_tools.py tests/test_netlist_analysis.py
git commit -m "refactor: split netlist analysis tools"
```

---

### Task 9: Backend API Compatibility Tests

**Files:**
- Create: `tests/test_backend_refactor_api.py`
- Modify: `app/backend/suite_app.py` if route behavior is inconsistent.

- [ ] **Step 1: Write API compatibility tests**

Create `tests/test_backend_refactor_api.py`:

```python
from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from app.backend import suite_app


class BackendApiCompatibilityTests(unittest.TestCase):
    def test_tool_registry_still_returns_six_tools(self) -> None:
        tools = suite_app.build_registry().list_tools()
        ids = {tool["id"] for tool in tools}
        self.assertEqual(
            ids,
            {"bom_process", "bom_compare", "bom_risk_check", "netlist_compare", "smt_package_check", "single_network_check"},
        )

    def test_api_tools_response_shape(self) -> None:
        tools = suite_app.build_registry().list_tools()
        first = tools[0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("description", first)
        self.assertIn("status", first)
        self.assertIn("category", first)
```

- [ ] **Step 2: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_backend_refactor_api -v
```

Expected: OK. If it fails due to missing `build_registry`, adapt the test to the current registry creation function and keep the same six-tool assertion.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_backend_refactor_api.py app/backend/suite_app.py
git commit -m "test: lock backend API compatibility"
```

---

### Task 10: Optional FastAPI Adapter Without Breaking Existing Launcher

**Files:**
- Create: `app/backend/fastapi_app.py`
- Create: `requirements.txt`
- Modify: `launch_tool_suite.ps1`
- Test: `tests/test_backend_refactor_api.py`

- [ ] **Step 1: Decide whether dependencies are allowed in current release**

If users cannot install Python packages, skip Task 10 and keep stdlib HTTP for this release. Record the decision in `docs/superpowers/plans/2026-06-23-hwagent-distribution-refactor-ui.md` by appending a note:

```markdown
FastAPI migration deferred until installer can provide bundled Python dependencies.
```

If dependencies are allowed, continue.

- [ ] **Step 2: Add requirements**

Create `requirements.txt`:

```text
fastapi==0.115.6
uvicorn==0.34.0
python-multipart==0.0.20
openpyxl==3.1.5
```

- [ ] **Step 3: Add FastAPI adapter**

Create `app/backend/fastapi_app.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.backend import suite_app

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="Insta360 HWAgent")


@app.get("/api/tools")
def api_tools() -> dict[str, object]:
    return {"tools": suite_app.build_registry().list_tools()}


@app.get("/api/version")
def api_version() -> dict[str, object]:
    from app.backend.update_api import read_version
    return {"status": "ok", "version": read_version(ROOT)}


app.mount("/", StaticFiles(directory=ROOT / "app" / "frontend", html=True), name="frontend")
```

- [ ] **Step 4: Keep launcher fallback**

Modify `launch_tool_suite.ps1` to prefer FastAPI only when `uvicorn` imports:

```powershell
$UseFastApi = $false
try {
  & $Python -c "import fastapi, uvicorn" 2>$null
  if ($LASTEXITCODE -eq 0) { $UseFastApi = $true }
} catch { $UseFastApi = $false }

if ($UseFastApi) {
  $args = "-m uvicorn app.backend.fastapi_app:app --host 127.0.0.1 --port $Port"
} else {
  $args = "app\backend\suite_app.py --port $Port"
}
```

Use `$args` in `Start-Process -ArgumentList`.

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile app\backend\fastapi_app.py
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_backend_refactor_api -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt app/backend/fastapi_app.py launch_tool_suite.ps1
git commit -m "feat: add optional FastAPI backend adapter"
```

---

### Task 11: React Frontend Scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/i18n/zhCN.ts`
- Create: `frontend/src/styles.css`
- Create: `scripts/build_frontend.ps1`
- Test: `tests/test_frontend_build.py`

- [ ] **Step 1: Write failing frontend build tests**

Create `tests/test_frontend_build.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendBuildTests(unittest.TestCase):
    def test_frontend_package_uses_react_and_antd(self) -> None:
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("react", package["dependencies"])
        self.assertIn("antd", package["dependencies"])
        self.assertIn("@tanstack/react-table", package["dependencies"])

    def test_build_script_copies_dist_to_app_frontend(self) -> None:
        text = (ROOT / "scripts" / "build_frontend.ps1").read_text(encoding="utf-8")
        self.assertIn("npm run build", text)
        self.assertIn("app\\frontend", text)

    def test_frontend_ui_is_simplified_chinese(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        zh = (ROOT / "frontend" / "src" / "i18n" / "zhCN.ts").read_text(encoding="utf-8")

        self.assertIn('lang="zh-CN"', index)
        self.assertIn("zhCN", app)
        self.assertIn("硬件效率工具集", app + index + zh)
        self.assertNotRegex(app + index + zh, r">\\s*(Upload|Download|Run|Update|Loading|Error|Settings|Tools)\\s*<")
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_frontend_build -v
```

Expected: FAIL because frontend project does not exist.

- [ ] **Step 3: Create package**

Create `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tanstack/react-table": "^8.20.6",
    "antd": "^5.22.5",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zustand": "^5.0.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.7.2",
    "vite": "^6.0.3"
  }
}
```

- [ ] **Step 4: Create minimal React app shell**

Create `frontend/src/i18n/zhCN.ts`:

```ts
export const uiText = {
  appTitle: "硬件效率工具集",
  loadingTools: "正在加载工具集",
  startupFailed: "启动失败",
  migrating: "工具页面迁移中",
  migratingSubtitle: "React 外壳已就绪，后续任务会逐个迁移 6 个工具。",
};
```

Create `frontend/src/api/client.ts`:

```ts
export type ToolInfo = {
  id: string;
  name: string;
  description: string;
  status: string;
  category: string;
};

export async function fetchTools(): Promise<ToolInfo[]> {
  const res = await fetch("/api/tools");
  if (!res.ok) throw new Error("工具列表加载失败");
  const payload = await res.json();
  return payload.tools || [];
}
```

Create `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { ConfigProvider, Layout, Menu, Result, Spin, Typography } from "antd";
import zhCN from "antd/locale/zh_CN";
import { fetchTools, type ToolInfo } from "./api/client";
import { uiText } from "./i18n/zhCN";
import "./styles.css";

const { Sider, Content } = Layout;

export default function App() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [active, setActive] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchTools()
      .then((items) => {
        setTools(items);
        setActive(items[0]?.id || "");
      })
      .catch((err) => setError(err.message || "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin fullscreen tip={uiText.loadingTools} />;
  if (error) return <Result status="error" title={uiText.startupFailed} subTitle={error} />;

  const current = tools.find((tool) => tool.id === active);

  return (
    <ConfigProvider locale={zhCN}>
      <Layout className="app-shell">
        <Sider width={260} theme="light" className="app-sider">
          <Typography.Title level={4}>{uiText.appTitle}</Typography.Title>
          <Menu
            selectedKeys={[active]}
            items={tools.map((tool) => ({ key: tool.id, label: tool.name }))}
            onClick={(item) => setActive(item.key)}
          />
        </Sider>
        <Content className="app-content">
          <Typography.Title level={3}>{current?.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{current?.description}</Typography.Paragraph>
          <Result title={uiText.migrating} subTitle={uiText.migratingSubtitle} />
        </Content>
      </Layout>
    </ConfigProvider>
  );
}
```

Create `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Create `frontend/src/styles.css`:

```css
html,
body,
#root {
  margin: 0;
  min-height: 100%;
}

.app-shell {
  min-height: 100vh;
  background: #f5f5f7;
}

.app-sider {
  padding: 24px 16px;
  border-right: 1px solid rgba(5, 5, 5, 0.08);
}

.app-content {
  padding: 32px;
}
```

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>硬件效率工具集</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/tsconfig.json` and `frontend/vite.config.ts` using standard Vite React defaults.

- [ ] **Step 5: Create build script**

Create `scripts/build_frontend.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Frontend = Join-Path $Root "frontend"
$Target = Join-Path $Root "app\frontend"

Push-Location $Frontend
try {
  npm install
  npm run build
} finally {
  Pop-Location
}

Remove-Item -LiteralPath $Target -Recurse -Force
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Path (Join-Path $Frontend "dist\*") -Destination $Target -Recurse -Force
```

- [ ] **Step 6: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_frontend_build -v
```

Expected: OK.

- [ ] **Step 7: Commit**

```powershell
git add frontend scripts/build_frontend.ps1 tests/test_frontend_build.py
git commit -m "feat: scaffold React frontend"
```

---

### Task 12: React Tool Runner And Upload Components

**Files:**
- Create: `frontend/src/components/FileInputField.tsx`
- Create: `frontend/src/components/ResultPanel.tsx`
- Create: `frontend/src/tools/toolConfig.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n/zhCN.ts`

- [ ] **Step 1: Add API client functions**

Modify `frontend/src/api/client.ts`:

```ts
export async function uploadFiles(files: File[]): Promise<{ path: string; files: string[] }> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const res = await fetch("/api/upload", { method: "POST", body: form });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "上传失败");
  return payload;
}

export async function runTool(tool: string, params: Record<string, unknown>) {
  const res = await fetch(`/api/run/${tool}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const payload = await res.json();
  if (!res.ok || payload.status === "error") throw new Error(payload.error || "运行失败");
  return payload;
}
```

- [ ] **Step 2: Add tool config**

Create `frontend/src/tools/toolConfig.ts`:

```ts
export const toolInputs: Record<string, Array<{ key: string; label: string; multiple?: boolean; accept?: string }>> = {
  bom_compare: [
    { key: "bom1", label: "BOM1 文件", accept: ".xlsx,.xls" },
    { key: "bom2", label: "BOM2 文件", accept: ".xlsx,.xls" },
  ],
  bom_risk_check: [{ key: "bom", label: "BOM 文件", accept: ".xlsx,.xls" }],
  netlist_compare: [
    { key: "netlist1", label: "网表1文件夹文件", multiple: true, accept: ".dat" },
    { key: "netlist2", label: "网表2文件夹文件", multiple: true, accept: ".dat" },
  ],
  smt_package_check: [
    { key: "netlist", label: "网表文件夹文件", multiple: true, accept: ".dat" },
    { key: "bom", label: "BOM 文件", accept: ".xlsx,.xls" },
  ],
  single_network_check: [{ key: "netlist", label: "网表文件夹文件", multiple: true, accept: ".dat" }],
};
```

All labels in this config must stay Simplified Chinese. Keep field keys English only when they are API parameter names.

- [ ] **Step 3: Add file input component**

Create `frontend/src/components/FileInputField.tsx`:

```tsx
import { Upload } from "antd";
import type { UploadFile } from "antd";

type Props = {
  label: string;
  accept?: string;
  multiple?: boolean;
  value: File[];
  onChange: (files: File[]) => void;
};

export function FileInputField({ label, accept, multiple, value, onChange }: Props) {
  const fileList: UploadFile[] = value.map((file, index) => ({ uid: `${index}`, name: file.name, status: "done" }));
  return (
    <Upload.Dragger
      multiple={multiple}
      accept={accept}
      beforeUpload={(file) => {
        onChange(multiple ? [...value, file] : [file]);
        return false;
      }}
      onRemove={(file) => {
        onChange(value.filter((item) => item.name !== file.name));
      }}
      fileList={fileList}
    >
      <p>{label}</p>
      <p className="ant-upload-hint">点击或拖拽文件到此处</p>
    </Upload.Dragger>
  );
}
```

- [ ] **Step 4: Add result panel**

Create `frontend/src/components/ResultPanel.tsx`:

```tsx
import { Alert, Button, Space, Table, Typography } from "antd";

export function ResultPanel({ result }: { result: any }) {
  if (!result) return <Alert type="info" message="请选择输入并运行。" />;
  if (result.status !== "ok") return <Alert type="error" message={result.error || result.message || "运行失败"} />;
  const table = result.table;
  const columns = table?.headers?.map((header: string, index: number) => ({ title: header, dataIndex: String(index), key: String(index) })) || [];
  const data = table?.rows?.map((row: unknown[], index: number) => ({ key: index, ...Object.fromEntries(row.map((value, i) => [String(i), value])) })) || [];
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Text type="success">运行完成</Typography.Text>
      {result.outputs?.length ? (
        <Space wrap>
          {result.outputs.map((path: string) => (
            <Button key={path} href={`/outputs/${encodeURIComponent(path.split(/data[\\/]outputs[\\/]/).pop() || path)}`}>
              下载报告
            </Button>
          ))}
        </Space>
      ) : null}
      {table ? <Table size="small" columns={columns} dataSource={data} scroll={{ x: true }} /> : null}
    </Space>
  );
}
```

- [ ] **Step 5: Wire generic tool runner in `App.tsx`**

Replace placeholder result with a form that renders `toolInputs[current.id]`, uploads files, calls `runTool`, and displays `ResultPanel`.

Use only Chinese visible labels:

```tsx
<Button type="primary" loading={running} onClick={handleRun}>开始运行</Button>
<Button onClick={clearFiles}>清空文件</Button>
```

Do not use visible English such as `Upload`, `Run`, `Download`, `Error`, `Loading`, `Settings`, or `Tools`.

- [ ] **Step 6: Run frontend build**

Run:

```powershell
cd frontend
npm install
npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src
git commit -m "feat: add React generic tool runner"
```

---

### Task 13: React BOM Process Wizard

**Files:**
- Create: `frontend/src/tools/BomProcessWizard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Implement wizard component**

Create `frontend/src/tools/BomProcessWizard.tsx`:

```tsx
import { Button, Card, Input, Space, Steps, Typography } from "antd";
import { Copy } from "lucide-react";

const CAPTURE_CONFIG =
  "{Item}\\t{Quantity}\\t{Reference}\\t{Part Number}\\t{Value}\\t{规格型号}\\t{器件描述（新整理）}\\t{物料名称}\\t{等级}";

export function BomProcessWizard() {
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Steps current={0} items={[{ title: "导出配置" }, { title: "上传处理" }, { title: "复核打包" }]} />
      <Card title="Capture BOM 导出配置">
        <Typography.Paragraph>表头和组合属性字符串都填入下列字段。</Typography.Paragraph>
        <Input.TextArea readOnly value={CAPTURE_CONFIG} autoSize />
        <Button type="primary" icon={<Copy size={16} />} onClick={() => navigator.clipboard.writeText(CAPTURE_CONFIG)} style={{ marginTop: 12 }}>
          复制配置
        </Button>
      </Card>
    </Space>
  );
}
```

- [ ] **Step 2: Render wizard for `bom_process`**

In `App.tsx`, when `current?.id === "bom_process"`, render `<BomProcessWizard />`.

Keep all wizard step names, hints, validation messages, conflict confirmation dialogs, and package download actions in Simplified Chinese. Raw CAD field tokens inside the copied Capture configuration string can remain English where OrCAD requires them.

- [ ] **Step 3: Build**

Run:

```powershell
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/tools/BomProcessWizard.tsx frontend/src/App.tsx
git commit -m "feat: add React BOM process wizard shell"
```

---

### Task 14: React Update Status UI

**Files:**
- Create: `frontend/src/components/UpdateStatus.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add update client functions**

Modify `frontend/src/api/client.ts`:

```ts
export async function fetchVersion(): Promise<string> {
  const res = await fetch("/api/version");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "版本获取失败");
  return payload.version;
}

export async function startUpdate() {
  const res = await fetch("/api/update/run", { method: "POST" });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "更新启动失败");
  return payload;
}
```

- [ ] **Step 2: Add update status component**

Create `frontend/src/components/UpdateStatus.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Button, message, Space, Tag } from "antd";
import { fetchVersion, startUpdate } from "../api/client";

export function UpdateStatus() {
  const [version, setVersion] = useState("");
  useEffect(() => {
    fetchVersion().then(setVersion).catch(() => setVersion("unknown"));
  }, []);

  return (
    <Space>
      <Tag>版本 {version || "加载中"}</Tag>
      <Button
        size="small"
        onClick={async () => {
          await startUpdate();
          message.success("已开始更新，稍后会自动重启服务");
        }}
      >
        一键更新
      </Button>
    </Space>
  );
}
```

- [ ] **Step 3: Place in app header**

Add `<UpdateStatus />` in `App.tsx` top area.

- [ ] **Step 4: Build**

Run:

```powershell
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/UpdateStatus.tsx frontend/src/api/client.ts frontend/src/App.tsx
git commit -m "feat: add update status UI"
```

---

### Task 15: Build React Into Static Frontend

**Files:**
- Modify: `scripts/build_frontend.ps1`
- Modify: `install.ps1`
- Modify: `update.ps1`
- Test: `tests/test_frontend_build.py`

- [ ] **Step 1: Update tests for install/update build integration**

Append to `tests/test_frontend_build.py`:

```python
    def test_install_and_update_call_frontend_build_when_node_available(self) -> None:
        install = (ROOT / "install.ps1").read_text(encoding="utf-8")
        update = (ROOT / "update.ps1").read_text(encoding="utf-8")
        self.assertIn("build_frontend.ps1", install)
        self.assertIn("build_frontend.ps1", update)
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_frontend_build -v
```

Expected: FAIL until scripts call build.

- [ ] **Step 3: Make build script non-destructive**

Modify `scripts/build_frontend.ps1` to preserve `waiting.html` if React build does not include it:

```powershell
$Waiting = Join-Path $Target "waiting.html"
$WaitingBackup = Join-Path $env:TEMP "hwagent_waiting.html"
if (Test-Path -LiteralPath $Waiting) { Copy-Item $Waiting $WaitingBackup -Force }
Remove-Item -LiteralPath $Target -Recurse -Force
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Path (Join-Path $Frontend "dist\*") -Destination $Target -Recurse -Force
if ((Test-Path -LiteralPath $WaitingBackup) -and -not (Test-Path -LiteralPath (Join-Path $Target "waiting.html"))) {
  Copy-Item $WaitingBackup (Join-Path $Target "waiting.html") -Force
}
```

- [ ] **Step 4: Call build from install/update when Node exists**

In `install.ps1` and `update.ps1`, add:

```powershell
$node = Get-Command node.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($node -and $npm -and (Test-Path -LiteralPath (Join-Path $InstallRoot "frontend\package.json"))) {
  & (Join-Path $InstallRoot "scripts\build_frontend.ps1")
}
```

For `update.ps1`, use `$Root` instead of `$InstallRoot`.

- [ ] **Step 5: Run tests**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_frontend_build -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```powershell
git add scripts/build_frontend.ps1 install.ps1 update.ps1 tests/test_frontend_build.py
git commit -m "feat: wire React frontend build into install and update"
```

---

### Task 16: Integration Verification Script

**Files:**
- Create: `scripts/verify_all.ps1`
- Modify: `update.ps1`

- [ ] **Step 1: Create verification script**

Create `scripts/verify_all.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if (-not $cmd) { throw "Python not found" }
  $Python = $cmd.Source
}

Push-Location $Root
try {
  & $Python -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) { throw "unittest failed" }
  & $Python -m py_compile app\backend\suite_app.py app\backend\tools\analysis_tools.py tools\bom\convert_cadence_bom.py
  if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }
  if (Test-Path -LiteralPath "frontend\package.json") {
    Push-Location frontend
    try {
      npm run build
      if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
    } finally {
      Pop-Location
    }
  } elseif (Test-Path -LiteralPath "app\frontend\app.js") {
    node --check app\frontend\app.js
    if ($LASTEXITCODE -ne 0) { throw "node check failed" }
  }
  $uiFiles = @()
  if (Test-Path -LiteralPath "frontend\src") {
    $uiFiles += Get-ChildItem -Path "frontend\src" -Include *.tsx,*.ts -Recurse
    $uiFiles += Get-Item "frontend\index.html"
  } elseif (Test-Path -LiteralPath "app\frontend") {
    $uiFiles += Get-ChildItem -Path "app\frontend" -Include *.js,*.html -Recurse
  }
  $englishUiPattern = ">\\s*(Upload|Download|Run|Update|Loading|Error|Settings|Tools|Cancel|Confirm|Save)\\s*<"
  foreach ($file in $uiFiles) {
    $text = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    if ($text -match $englishUiPattern) { throw "English UI text found in $($file.FullName)" }
  }
} finally {
  Pop-Location
}
```

- [ ] **Step 2: Use script from update**

In `update.ps1`, replace direct unittest call with:

```powershell
& (Join-Path $Root "scripts\verify_all.ps1")
if ($LASTEXITCODE -ne 0) { throw "Verification failed after update." }
```

- [ ] **Step 3: Run verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

Expected: all checks pass.

- [ ] **Step 4: Commit**

```powershell
git add scripts/verify_all.ps1 update.ps1
git commit -m "test: add full verification script"
```

---

### Task 17: Release Documentation And Rollout Checklist

**Files:**
- Create: `docs/INSTALL.md`
- Create: `docs/UPDATE.md`
- Create: `docs/ROLLBACK.md`
- Modify: `cadence/README.md`
- Modify: `tools/README.md`

- [ ] **Step 1: Create install docs**

Create `docs/INSTALL.md`:

```markdown
# 硬件效率工具集安装说明

推荐安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

自定义安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:LOCALAPPDATA\Insta360\HWAgent" -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```

安装完成后，重启 OrCAD Capture，并打开 Accessories -> 硬件效率工具集。
```

- [ ] **Step 2: Create update docs**

Create `docs/UPDATE.md`:

```markdown
# 硬件效率工具集更新说明

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

The updater preserves:

- `data/`
- `config/local.json`

The updater redeploys the Cadence GBK Tcl loader and runs verification before restarting.
```

- [ ] **Step 3: Create rollback docs**

Create `docs/ROLLBACK.md`:

```markdown
# HWAgent Rollback

Git install:

```powershell
git log --oneline
git checkout <known-good-commit>
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Release zip install:

1. Stop the service from Task Manager or run `scripts/lib/Service.ps1` `Stop-HWAgentService`.
2. Replace app files with the previous release.
3. Keep `data/` and `config/local.json`.
4. Run `install.ps1`.
```

- [ ] **Step 4: Add rollout checklist**

Append to `docs/INSTALL.md`:

```markdown
## Rollout Checklist

- Confirm OrCAD Capture can restart.
- Run `iac` in Capture Command Window.
- Run `iacx` on a small design.
- Open `http://127.0.0.1:8765/api/tools`.
- Run one BOM process and one netlist check.
- Check `data/reports/runtime/launcher_latest.log` if the browser does not open.
```

- [ ] **Step 5: Commit**

```powershell
git add docs cadence/README.md tools/README.md
git commit -m "docs: add install update rollback rollout docs"
```

---

## Final Verification

After all tasks:

- [ ] Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

Expected: all tests/build checks pass.

- [ ] Run installer in a temp location:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:TEMP\HWAgentInstallSmoke" -CaptureAutoLoadDir "$env:TEMP\HWAgentCapAutoLoad"
```

Expected:

- `$env:TEMP\HWAgentInstallSmoke\config\local.json` exists.
- `$env:TEMP\HWAgentCapAutoLoad\iac_bom_tool.tcl` exists.
- The generated Tcl decodes as cp936 and contains `AddAccessoryMenu "硬件效率工具集"`.

- [ ] Run launcher smoke:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_tool_suite.ps1 -Restart
```

Expected:

- Browser opens waiting page or app page.
- `http://127.0.0.1:8765/api/tools` returns 6 tools.
- `data/reports/runtime/launcher_latest.log` records the launch.

---

## Self-Review

Spec coverage:

- One-click install: Tasks 2-4, 17.
- One-click OTA update: Tasks 5, 14, 16, 17.
- Preserve all current functions: Tasks 6, 6A, 7-9 and final verification.
- Capture property coverage and complete 19-column BOM template output: Task 6A.
- Same-part-number conflict confirmation and user-selected field retention: Task 6A plus the existing BOM conflict flow.
- Machine-specific Cadence differences: Tasks 2-4.
- Chinese menu fix: Task 3.
- UI modernization with mature libraries: Tasks 11-15.
- All user-facing UI and end-user documentation in Simplified Chinese: Product Language rule, Tasks 11-16, and release docs in Task 17.
- Code standardization and speed: Tasks 6, 6A, 7-10, 16.

No placeholders are intentionally left. FastAPI is explicitly optional in Task 10 because dependency bundling is a release decision; the fallback is the current stdlib server.
