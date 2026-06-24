# Insta360硬件提效平台最终落地计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 Cadence 启动报错并完成「Insta360硬件提效平台」的 BOM、脚本管理、一键安装更新、中文 UI 和验收闭环，且原有 6 个 Web 工具不退化。

**Architecture:** Cadence 侧只保留一个 GBK、无 BOM 的安全 loader，默认菜单只有 `进入平台` 和 `导出并处理BOM`，其他 Tcl 能力由平台注册表显式启用后再挂载。后端继续以当前 Python 标准库 HTTP 服务为稳定基线，前端使用 React/Vite/Ant Design 构建中文工作台，安装/更新通过 PowerShell 适配不同电脑路径并保护用户数据。

**Tech Stack:** PowerShell 5.1、GBK Tcl、Python 标准库 HTTP、openpyxl、React + Vite + TypeScript + Ant Design、unittest、浏览器手工验收、OrCAD Capture Command Window 诊断。

---

## 当前已完成的止血状态

- [x] Cadence 顶层菜单模板统一为 `insta360_HW`。
- [x] 默认只挂 `进入平台` 和 `导出并处理BOM`。
- [x] `iac`、`iacx`、`iacdiag` 三个 Capture 命令已存在。
- [x] vendor autoload 根目录不再保留 `orCAD_Enhanced_Tools_V*.tcl*`。
- [x] 两个用户 autoload 目录下的 `_disabled_*` 备份目录已经迁到 autoload 外层归档目录，避免被递归加载。
- [x] 完整旧增强脚本从 `cadence/modules/` 移到 `cadence/archive/orcad_enhanced_tools_reference.tcl`，保留参考但不作为可加载模块。
- [x] 诊断脚本会检查 loader、旧增强脚本、autoload 备份目录和平台 API。

## Task 1: Cadence 恢复与安全 loader

**Files:**
- Modify: `scripts/lib/TclScripts.ps1`
- Modify: `scripts/diagnose_platform.ps1`
- Modify: `install.ps1`
- Modify: `update.ps1`
- Modify: `scripts/redeploy_cadence_loader.ps1`
- Modify: `cadence/modules/orcad_enhanced_tools.tcl`
- Create: `cadence/archive/orcad_enhanced_tools_reference.tcl`
- Test: `tests/test_distribution_install.py`
- Test: `tests/test_cadence_loader.py`

- [x] **Step 1: 写失败测试，禁止 autoload 里保留禁用备份目录**

Run:

```powershell
python -m unittest tests.test_distribution_install.DistributionInstallTests.test_tcl_script_library_moves_disabled_backup_dirs_outside_autoload
```

Expected before implementation: fail because `Move-HwAgentAutoLoadBackupDirs` does not exist.

- [x] **Step 2: 写失败测试，禁止 active modules 里保留完整旧增强脚本**

Run:

```powershell
python -m unittest tests.test_distribution_install.DistributionInstallTests.test_active_cadence_modules_do_not_include_full_legacy_enhanced_script
```

Expected before implementation: fail because `cadence/modules/orcad_enhanced_tools.tcl` exists.

- [x] **Step 3: 实现 autoload 备份目录外迁**

Add `Move-HwAgentAutoLoadBackupDirs` in `scripts/lib/TclScripts.ps1`; it moves `_disabled_hwagent_loader_*` and `_disabled_custom_scripts_*` from `capAutoLoad` into sibling `_hwagent_disabled_autoload_backups/<timestamp>/`.

- [x] **Step 4: 接入安装、更新、重部署和诊断**

Call `Move-HwAgentAutoLoadBackupDirs` from `install.ps1`, `update.ps1`, `scripts/redeploy_cadence_loader.ps1`, and check it in `scripts/diagnose_platform.ps1`.

- [x] **Step 5: 归档完整旧增强脚本**

Move `cadence/modules/orcad_enhanced_tools.tcl` to `cadence/archive/orcad_enhanced_tools_reference.tcl`.

- [x] **Step 6: 真实目录止血**

Run:

```powershell
$ErrorActionPreference='Stop'
. .\scripts\lib\TclScripts.ps1
foreach ($d in @(
  'D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad',
  'C:\Users\Administrator\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad'
)) { Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $d }
```

Expected: both `_disabled_hwagent_loader_*` folders move outside `capAutoLoad`.

- [x] **Step 7: 诊断验证**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\diagnose_platform.ps1
```

Expected: diagnostics pass and explicitly report no disabled backup directories under both autoload dirs.

## Task 2: 启动链路可见、复用、不多开终端

**Files:**
- Modify: `launch_tool_suite.ps1`
- Modify: `launch_tool_suite_hidden.vbs`
- Modify: `app/frontend/waiting.html`
- Test: `tests/test_cadence_integration.py`
- Test: `tests/test_distribution_install.py`

- [x] **Step 1: 保留健康服务复用逻辑**

`launch_tool_suite.ps1` must scan ports `8765..8775`; if `/api/tools` responds with all 6 original tools available, it opens the target URL and exits without starting another backend process.

- [x] **Step 2: 首次启动显示等待页**

When no healthy service exists, `launch_tool_suite.ps1` opens `app/frontend/waiting.html?target=<encoded>` before launching Python hidden. The waiting page must show Chinese startup text and poll the target until ready.

- [x] **Step 3: 验证 Capture 点击行为**

Manual verification in OrCAD Capture:

```tcl
iac
iacx
iacdiag
```

Expected: no visible extra terminal, browser opens platform, `iacx` passes BOM source/name when export succeeds.

Evidence: `scripts\verify_capture_runtime.ps1 -CloseStartedCapture` starts real Capture and confirms `cadence_loader_probe.log` reports `RegisterAction=available`, `InsertXMLMenu=available`, and `AddAccessoryMenu=available`. `launch_tool_suite.ps1 -Name ReuseSmoke` kept the backend process count at 1 and reused port 8766. Full `iacx` export from an opened DSN still depends on a user-opened design context.

## Task 3: BOM 字段、冲突确认和 ZIP 命名

**Files:**
- Modify: `cadence/iac_bom_tool.tcl`
- Modify: `tools/bom/convert_cadence_bom.py`
- Modify: `app/backend/tools/bom_process.py`
- Modify: `frontend/src/tools/BomProcessWizard.tsx`
- Test: `tests/test_capture_bom_fields.py`
- Test: `tests/test_bom_process_conflicts.py`
- Test: `tests/test_launch_and_package.py`

- [x] **Step 1: Capture 导出字段覆盖**

Preserve all `EffectiveProps` and explicitly query common visible Capture fields including `Part Number`, `Value`, `规格型号`, `器件描述（新整理）`, `物料名称`, `等级`, `物料优选等级`, `PCB Footprint`, `PCB封装`.

- [x] **Step 2: PLM 19 列模板完整**

Output must cover: `父项编码`, `描述`, `子项编码`, `名称`, `型号`, `描述`, `单位`, `数量`, `位号`, `备注`, `物料优选等级`, `物料优选等级备注`, `替代组编码`, `替代策略`, `替代方式`, `替代优先级`, `发料方式`, `是否参与MRP运算`, `是否跳层`.

- [x] **Step 3: 同编码冲突确认**

When rows have the same material code but conflicting name/model/description/grade fields, backend returns `needs_confirmation` with per-field candidates. Frontend shows a Chinese confirmation modal/table; user-selected values are submitted back and used for merge.

- [x] **Step 4: ZIP 命名**

`/api/package` uses `<单板名>_<yyyyMMdd_HHmmss>.zip`.

- [x] **Step 5: 真实 BOM 样本闭环验收**

Use:

```text
D:\desktop\IAC4功耗版\功耗版V2\IAC4_MB_POWER_V02_20260618A.xlsx
D:\desktop\IAC4功耗版\最终交付_20260622\BOM导入资料\IAC4_MB_POWER_V02_PCBA_BOM.xlsx
```

Expected: fields match required template, conflicts are visible and selectable, package name includes board name and timestamp.

Evidence: real IAC4 source BOM returned `needs_confirmation` with same-code variants; running with `merge_conflicts=false` produced PLM/OA/NC outputs, a 19-column PLM header, and `IAC4_MB_POWER_V02_20260618A_<timestamp>.zip`.

## Task 4: 平台能力注册表和 Tcl 脚本管理

**Files:**
- Modify: `config/capabilities.json`
- Modify: `app/backend/capabilities.py`
- Modify: `app/backend/suite_app.py`
- Modify: `frontend/src/platform/ScriptManager.tsx`
- Modify: `cadence/modules/*.tcl`
- Test: `tests/test_cadence_loader.py`
- Test: `tests/test_platform_api.py`

- [x] **Step 1: 注册 6 个 Web 工具**

`/api/platform/status` must report `tools: 6`.

- [x] **Step 2: 注册 19 个 Cadence Tcl 能力**

All Tcl capabilities default to `show_in_cadence=false`; high-risk actions require confirmation.

- [x] **Step 3: loader 只注入显式启用脚本**

Generated loader may source module files and add menu items only for `show_in_cadence=true` capabilities.

- [x] **Step 4: 高风险脚本拆成无菜单注册模块**

Active module files must not contain `RegisterAction` or `AddAccessoryMenu`.

- [ ] **Step 5: 真实启用/禁用验收**

Enable one low-risk script in platform, redeploy loader, restart Capture, confirm the actual script name appears under `insta360_HW`; then disable it and confirm it disappears.

## Task 5: 中文 UI、一键安装更新和全量验收

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/api/client.ts`
- Modify: `install.ps1`
- Modify: `update.ps1`
- Modify: `docs/INSTALL.md`
- Modify: `docs/UPDATE.md`
- Test: `tests/test_frontend_build.py`
- Test: `tests/test_distribution_install.py`
- Test: `tests/test_update_api.py`

- [x] **Step 1: 平台名统一**

Visible platform name is `Insta360硬件提效平台`; Capture menu is `insta360_HW`.

- [x] **Step 2: 前端中文工作台**

React/Vite frontend includes Chinese navigation, dashboard, script manager, BOM page, update control, status view.

- [x] **Step 3: 一键安装更新**

`install.ps1` and `update.ps1` preserve user data (`data`, `uploads`, `outputs`, `history`, `config/local.json`), deploy safe loader, clean old enhanced autoload scripts, and build/copy frontend when Node is available.

- [x] **Step 4: 浏览器 UI 验收**

Open `http://127.0.0.1:<port>` and verify:

- Home shows title, 6 Web tools, 19 Cadence scripts, 0 mounted by default.
- Script manager has Chinese labels and risk tags.
- BOM page can accept source/name URL parameters.
- Waiting page is Chinese and redirects when backend is ready.

- [x] **Step 5: 全量自动化验收**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_frontend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\diagnose_platform.ps1
```

Expected: all pass. Vite chunk-size warning is acceptable only if build succeeds.

Evidence: `scripts\verify_all.ps1` passed 87 unittest tests and Vite build; `scripts\build_frontend.ps1` copied the current React build to `app/frontend`; `scripts\diagnose_platform.ps1` passed and included the Capture loader probe log.

- [x] **Step 6: Capture 真实验收**

After restarting OrCAD Capture, verify:

- Command Window no longer loads old `orCAD_Enhanced_Tools_V*.tcl`.
- Command Window no longer shows errors caused by our custom scripts.
- `iacdiag` reports loader paths and command availability.
- `insta360_HW -> 进入平台` opens platform.
- `insta360_HW -> 导出并处理BOM` exports and opens BOM flow.
- Repeated clicks reuse existing service and do not create multiple visible terminals.

Evidence: `scripts\verify_capture_runtime.ps1 -CloseStartedCapture` launched real OrCAD Capture, waited for the loader probe, verified all three Capture menu APIs were available, and closed the Capture instance it started. The default loader still contains only `进入平台` and `导出并处理BOM`; actual DSN export should be smoke-tested from an opened design when convenient.
