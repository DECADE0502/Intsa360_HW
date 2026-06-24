# Insta360硬件提效平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前工具从 BOM/脚本集合升级为可安装、可更新、可管理、可扩展的 **Insta360硬件提效平台**，并在全过程保持现有 BOM、网表、封装、单网络、历史、打包功能不退化。

**Architecture:** 先保持 Cadence loader 极薄且稳定，只负责 `进入平台` 和 `导出并处理BOM`，避免自定义 Tcl 破坏 Capture 原生 autoload。随后新增统一注册表，把 Web 工具和 Cadence Tcl 脚本作为同一种“平台能力”管理；Web 后端暴露能力清单、脚本清单、安装状态、更新状态，前端用 Ant Design 做中文工程工作台。最后再用注册表生成受控 Cadence 菜单，把原生 Tcl 脚本逐个恢复。

**Tech Stack:** Python 标准库 HTTP 后端、PowerShell 安装/更新/部署脚本、GBK Tcl loader、React + Vite + TypeScript + Ant Design + TanStack Table、unittest + Vite build 验证。

---

## Current Baseline

- `D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl` 已恢复成安全版。
- 安全版只保留 `insta360_HW` 下的 `进入平台` 和 `导出并处理BOM`。
- 安全版不加载 `orcad_enhanced_tools.tcl`，不 rename 全局 `RegisterAction`。
- `D:\CADENCE\Cadence\SPB_17.4\tools\capture\tclscripts\capAutoLoad\orCAD_Enhanced_Tools_V1.3.tcl` 和 `orCAD_Enhanced_Tools_V1.8.tcl` 已移动到 `_disabled_custom_scripts_20260623`，避免 Capture 官方 autoload 报错。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1` 当前通过，53 个测试 OK。

## Non-Negotiable Requirements

- 所有用户可见 UI 和文档使用简体中文。
- 平台名统一为 `Insta360硬件提效平台`。
- Capture 顶层菜单保留 ASCII/安全命名 `insta360_HW`。
- 自定义 Tcl 脚本不能再直接散落到 Cadence 官方 `capAutoLoad` 目录；必须由平台注册表受控部署。
- 原有 6 个 Web 工具必须继续可用：
  - BOM 处理
  - BOM 差异比较
  - BOM 风险检查
  - 网表差异比较
  - 贴片封装检查
  - 单网络检查
- Cadence `导出并处理BOM` 必须继续能自动导出并把 `source/name/tool=bom_process` 传给 Web 平台。
- 一键安装、一键更新必须保留 `data/`、`config/local.json`、历史记录和用户输出。

## File Structure

- Create: `config/capabilities.json`
  - 平台能力注册表，统一描述 Web 工具和 Cadence Tcl 脚本。
- Create: `app/backend/capabilities.py`
  - 读取、校验、合并能力注册表。
- Modify: `app/backend/tool_registry.py`
  - 从注册表生成 Web 工具元数据，同时继续绑定已有 runner。
- Modify: `app/backend/suite_app.py`
  - 新增 `/api/capabilities`、`/api/platform/status`。
- Modify: `scripts/lib/Cadence.ps1`
  - 从注册表生成 GBK Tcl loader 菜单，但默认只启用安全入口。
- Modify: `cadence/iac_bom_tool.tcl`
  - 继续作为安全模板；后续只通过生成器注入受控菜单。
- Create: `scripts/lib/TclScripts.ps1`
  - 管理 Tcl 脚本部署、禁用、备份、编码转换。
- Modify: `install.ps1`, `update.ps1`
  - 安装/更新后重新生成 Cadence loader；不直接复制自定义 Tcl 到官方 autoload。
- Create: `frontend/src/platform/*`
  - 平台工作台、能力管理、脚本管理、系统状态页面。
- Modify: `frontend/src/App.tsx`, `frontend/src/i18n/zhCN.ts`, `frontend/src/styles.css`
  - 改成 `Insta360硬件提效平台` 工程工作台布局。
- Create/Modify tests:
  - `tests/test_capabilities_registry.py`
  - `tests/test_cadence_loader.py`
  - `tests/test_distribution_install.py`
  - `tests/test_frontend_build.py`

---

### Task 1: Stabilize Cadence Safe Mode

**Files:**
- Modify: `cadence/iac_bom_tool.tcl`
- Modify: `tests/test_cadence_integration.py`
- Modify: `tests/test_cadence_loader.py`

- [ ] **Step 1: Keep failing regression test for unsafe RegisterAction manipulation**

Ensure `tests/test_cadence_integration.py` contains:

```python
def test_tcl_template_does_not_load_custom_enhanced_tools_until_platform_registry_exists(self) -> None:
    text = TCL_TEMPLATE.read_text(encoding="utf-8")

    self.assertNotIn("LoadEnhancedTools", text)
    self.assertNotIn("orcad_enhanced_tools.tcl", text)
    self.assertNotIn("rename RegisterAction", text)
    self.assertNotIn("proc ::RegisterAction", text)
    self.assertNotIn('AddAccessoryMenu "insta360_HW" "选中器件切换NC"', text)
    self.assertNotIn('AddAccessoryMenu "insta360_HW" "其他脚本"', text)
```

- [ ] **Step 2: Verify Cadence tests**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m unittest discover -s tests -p 'test_cadence_integration.py' -v
python -m unittest discover -s tests -p 'test_cadence_loader.py' -v
```

Expected: both OK.

- [ ] **Step 3: Deploy safe loader**

Run:

```powershell
$autoload = 'D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad'
. .\scripts\lib\Paths.ps1
. .\scripts\lib\Cadence.ps1
$root = Get-HwAgentRoot -StartPath (Get-Location).Path
$python = Find-Python -Root $root
Install-CadenceLoader -ToolRoot $root -PythonPath $python -AutoLoadDirs @($autoload) | Out-Null
```

- [ ] **Step 4: Verify deployed loader text**

Run:

```powershell
$target='D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl'
$decoded=[Text.Encoding]::GetEncoding(936).GetString([IO.File]::ReadAllBytes($target))
$decoded.Contains('AddAccessoryMenu "insta360_HW" "进入平台"')
$decoded.Contains('AddAccessoryMenu "insta360_HW" "导出并处理BOM"')
$decoded.Contains('orcad_enhanced_tools.tcl')
$decoded.Contains('rename RegisterAction')
```

Expected:

```text
True
True
False
False
```

---

### Task 2: Platform Capability Registry

**Files:**
- Create: `config/capabilities.json`
- Create: `app/backend/capabilities.py`
- Modify: `app/backend/tool_registry.py`
- Create: `tests/test_capabilities_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_capabilities_registry.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path

from app.backend.capabilities import load_capabilities
from app.backend.tool_registry import build_registry


ROOT = Path(__file__).resolve().parents[1]


class CapabilitiesRegistryTests(unittest.TestCase):
    def test_registry_contains_platform_name_and_existing_web_tools(self) -> None:
        data = load_capabilities(ROOT)

        self.assertEqual(data["platform"]["name"], "Insta360硬件提效平台")
        web_ids = [item["id"] for item in data["capabilities"] if item["type"] == "web_tool"]
        self.assertEqual(
            web_ids,
            [
                "bom_process",
                "bom_compare",
                "bom_risk_check",
                "netlist_compare",
                "smt_package_check",
                "single_network_check",
            ],
        )

    def test_cadence_scripts_are_registered_but_disabled_for_capture_menu_by_default(self) -> None:
        data = load_capabilities(ROOT)
        scripts = [item for item in data["capabilities"] if item["type"] == "cadence_tcl"]

        self.assertGreaterEqual(len(scripts), 10)
        self.assertTrue(all("command" in item for item in scripts))
        self.assertTrue(all(item["show_in_cadence"] is False for item in scripts))

    def test_build_registry_uses_capability_metadata_for_existing_runners(self) -> None:
        tools = build_registry(ROOT).list_tools()

        self.assertEqual(tools[0]["id"], "bom_process")
        self.assertEqual(tools[0]["name"], "BOM 处理")
        self.assertTrue(all(tool["status"] == "available" for tool in tools))
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m unittest tests.test_capabilities_registry -v
```

Expected: FAIL because `app.backend.capabilities` does not exist.

- [ ] **Step 3: Add capability registry JSON**

Create `config/capabilities.json`:

```json
{
  "platform": {
    "name": "Insta360硬件提效平台",
    "cadence_menu": "insta360_HW"
  },
  "capabilities": [
    {
      "id": "bom_process",
      "type": "web_tool",
      "name": "BOM 处理",
      "description": "Capture 原始 BOM 转 PLM/OA 成品 BOM，并输出 NC 未贴汇总。",
      "category": "BOM",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "bom_compare",
      "type": "web_tool",
      "name": "BOM 差异比较",
      "description": "两份 BOM 按位号对比，识别换料、新增、删除和用量差异。",
      "category": "BOM",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "bom_risk_check",
      "type": "web_tool",
      "name": "BOM 风险检查",
      "description": "单份 BOM 导入前体检：裸板、屏蔽罩、NC 未贴、机构件、测试点、重复位号和数量一致性。",
      "category": "BOM",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "netlist_compare",
      "type": "web_tool",
      "name": "网表差异比较",
      "description": "比较两个 pstxnet/pstxprt 网表文件夹中的网络节点和器件封装。",
      "category": "网表",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "smt_package_check",
      "type": "web_tool",
      "name": "贴片封装检查",
      "description": "检查网表封装与 BOM 描述、名称、型号、封装字段的一致性。",
      "category": "SMT",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "single_network_check",
      "type": "web_tool",
      "name": "单网络检查",
      "description": "提取 NC 网络和只有单一位号的网络，辅助原理图检查。",
      "category": "网表",
      "status": "available",
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_nc_toggle",
      "type": "cadence_tcl",
      "name": "选中器件切换NC",
      "description": "对 Capture 中选中的器件切换 NC 前缀和灰色显示。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capNCToggleSelected::toggleFromMenu",
      "danger_level": "medium",
      "requires_confirmation": false,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_ground_name_visible",
      "type": "cadence_tcl",
      "name": "显示GND网络名",
      "description": "显示 GND 网络名。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::GroundNameVisible",
      "danger_level": "low",
      "requires_confirmation": false,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_ground_name_hidden",
      "type": "cadence_tcl",
      "name": "隐藏GND网络名",
      "description": "隐藏 GND 网络名。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::GroundNameHidden",
      "danger_level": "low",
      "requires_confirmation": false,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_net_name_replace",
      "type": "cadence_tcl",
      "name": "网络名替换",
      "description": "打开网络名替换工具。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::showNetNameExchangeDialog",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_nc_part_gray",
      "type": "cadence_tcl",
      "name": "NC器件置灰",
      "description": "将 NC 器件置灰。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::NcPartGrayed",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_restore_part_color",
      "type": "cadence_tcl",
      "name": "恢复器件默认颜色",
      "description": "恢复器件默认颜色。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::RestorePartDefaultColor",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_grayed_part_value_nc",
      "type": "cadence_tcl",
      "name": "NC器件Value改为NC",
      "description": "将灰色 NC 器件 Value 改为 NC。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmGrayedPartToNC",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_reset_net_color",
      "type": "cadence_tcl",
      "name": "恢复网络名颜色",
      "description": "恢复网络名颜色。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::ResetNetnameColor",
      "danger_level": "low",
      "requires_confirmation": false,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_randomize_net_names",
      "type": "cadence_tcl",
      "name": "随机化网络名",
      "description": "随机化原理图网络名。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmRandomizeNetNames",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_delete_all_graphic",
      "type": "cadence_tcl",
      "name": "删除所有图形",
      "description": "删除所有图形对象。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmDeleteAllGraphic",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_delete_text_titleblocks",
      "type": "cadence_tcl",
      "name": "删除文本和标题栏",
      "description": "删除文本和标题栏。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmDeleteTextTitleblocks",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_hide_u_value",
      "type": "cadence_tcl",
      "name": "隐藏U器件Value",
      "description": "隐藏 U 器件 Value。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmHideUcomponent",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_show_u_value",
      "type": "cadence_tcl",
      "name": "显示U器件Value",
      "description": "显示 U 器件 Value。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmShowUcomponent",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_hide_all_value",
      "type": "cadence_tcl",
      "name": "隐藏所有器件Value",
      "description": "隐藏所有器件 Value。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmHideALLcomponent",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_show_all_value",
      "type": "cadence_tcl",
      "name": "显示所有器件Value",
      "description": "显示所有器件 Value。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmShowALLcomponent",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_hide_u_pin_names",
      "type": "cadence_tcl",
      "name": "隐藏U器件Pin名",
      "description": "隐藏 U 器件 Pin 名。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmHideUPinNames",
      "danger_level": "medium",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_required_sanitize",
      "type": "cadence_tcl",
      "name": "一键按要求脱敏",
      "description": "按要求脱敏 Value 和规格型号，并生成恢复文件。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capRequiredSanitize::sanitizeFromMenu",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_required_restore",
      "type": "cadence_tcl",
      "name": "恢复按要求脱敏",
      "description": "从最近一次本地恢复文件恢复 Value 和规格型号。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capRequiredSanitize::restoreFromMenu",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    },
    {
      "id": "cadence_schematic_obfuscation",
      "type": "cadence_tcl",
      "name": "一键混淆原理图",
      "description": "对原理图关键信息执行一键混淆。",
      "category": "Cadence 脚本",
      "status": "disabled",
      "command": "::capMenuUtil::confirmSchematicObfuscation",
      "danger_level": "high",
      "requires_confirmation": true,
      "show_in_platform": true,
      "show_in_cadence": false
    }
  ]
}
```

- [ ] **Step 4: Implement capability loader**

Create `app/backend/capabilities.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = {"id", "type", "name", "description", "category", "status", "show_in_platform", "show_in_cadence"}


def load_capabilities(root: Path) -> dict[str, Any]:
    path = root / "config" / "capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("platform", {}).get("name") != "Insta360硬件提效平台":
        raise ValueError("平台名称必须为 Insta360硬件提效平台")
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be a list")
    seen: set[str] = set()
    for item in capabilities:
        if not isinstance(item, dict):
            raise ValueError("capability item must be object")
        missing = REQUIRED_KEYS - set(item)
        if missing:
            raise ValueError(f"{item.get('id', '<unknown>')} 缺少字段: {', '.join(sorted(missing))}")
        if item["id"] in seen:
            raise ValueError(f"重复能力 id: {item['id']}")
        seen.add(str(item["id"]))
        if item["type"] == "cadence_tcl" and "command" not in item:
            raise ValueError(f"Cadence 脚本缺少 command: {item['id']}")
    return data
```

- [ ] **Step 5: Update `tool_registry.py` to use metadata but keep existing runners**

Modify `app/backend/tool_registry.py`:

```python
def build_registry(root: Path) -> ToolRegistry:
    from app.backend.capabilities import load_capabilities
    from app.backend.tools.analysis_tools import create_analysis_tools

    runners = {tool.id: tool.runner for tool in create_analysis_tools(root)}
    tools: list[Tool] = []
    for item in load_capabilities(root)["capabilities"]:
        if item["type"] != "web_tool":
            continue
        runner = runners.get(item["id"])
        tools.append(
            Tool(
                str(item["id"]),
                str(item["name"]),
                str(item["description"]),
                str(item["status"]),
                str(item["category"]),
                runner,
            )
        )
    return ToolRegistry(tools)
```

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m unittest tests.test_capabilities_registry -v
python -m unittest discover -s tests -v
```

Expected: OK.

---

### Task 3: Platform Status API

**Files:**
- Modify: `app/backend/suite_app.py`
- Test: `tests/test_update_api.py` or new `tests/test_platform_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_platform_api.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.backend.suite_app import create_server


ROOT = Path(__file__).resolve().parents[1]


class PlatformApiTests(unittest.TestCase):
    def test_capabilities_endpoint_returns_platform_and_scripts(self) -> None:
        server = create_server(ROOT, port=0)
        try:
            handler = server.RequestHandlerClass
            self.assertTrue(hasattr(handler, "registry"))
        finally:
            server.server_close()

        data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(data["platform"]["name"], "Insta360硬件提效平台")
        self.assertTrue(any(item["type"] == "cadence_tcl" for item in data["capabilities"]))
```

This test is intentionally light because `SuiteRequestHandler` is hard to call directly; it locks the data contract before endpoint work.

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m unittest tests.test_platform_api -v
```

Expected: FAIL before registry file exists, then PASS after Task 2. Add endpoint implementation next.

- [ ] **Step 3: Add GET endpoints**

In `app/backend/suite_app.py`, import:

```python
from app.backend.capabilities import load_capabilities
```

In `do_GET`, before history routes:

```python
if parsed.path == "/api/capabilities":
    self._send_json(load_capabilities(self.root))
    return
if parsed.path == "/api/platform/status":
    self._send_json({
        "status": "ok",
        "platform": "Insta360硬件提效平台",
        "tools": len(self.registry.list_tools()),
        "root": str(self.root),
    })
    return
```

- [ ] **Step 4: Verify API with live server smoke**

Run:

```powershell
python -m unittest tests.test_platform_api -v
python -m unittest tests.test_backend_refactor_api -v
```

Expected: OK.

---

### Task 4: Controlled Tcl Script Management

**Files:**
- Create: `scripts/lib/TclScripts.ps1`
- Modify: `scripts/lib/Cadence.ps1`
- Test: `tests/test_distribution_install.py`
- Test: `tests/test_cadence_loader.py`

- [ ] **Step 1: Write failing script-management tests**

Append to `tests/test_distribution_install.py`:

```python
def test_tcl_script_library_disables_custom_scripts_in_vendor_autoload(self) -> None:
    text = (ROOT / "scripts" / "lib" / "TclScripts.ps1").read_text(encoding="utf-8")
    self.assertIn("function Disable-HwAgentVendorAutoLoadScripts", text)
    self.assertIn("_disabled_custom_scripts", text)
    self.assertIn("Move-Item", text)

def test_cadence_loader_generator_does_not_source_custom_tcl_by_default(self) -> None:
    text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")
    self.assertNotIn("orcad_enhanced_tools.tcl", text)
    self.assertNotIn("rename RegisterAction", text)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m unittest tests.test_distribution_install -v
```

Expected: FAIL because `TclScripts.ps1` does not exist.

- [ ] **Step 3: Implement safe disable helper**

Create `scripts/lib/TclScripts.ps1`:

```powershell
function Disable-HwAgentVendorAutoLoadScripts {
  param([Parameter(Mandatory=$true)][string]$VendorAutoLoadDir)
  if (-not (Test-Path -LiteralPath $VendorAutoLoadDir)) { return @() }
  $backup = Join-Path $VendorAutoLoadDir "_disabled_custom_scripts_$(Get-Date -Format yyyyMMdd)"
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  $moved = @()
  Get-ChildItem -Path $VendorAutoLoadDir -File -Filter "orCAD_Enhanced_Tools_V*.tcl" -ErrorAction SilentlyContinue |
    ForEach-Object {
      $dest = Join-Path $backup $_.Name
      Move-Item -LiteralPath $_.FullName -Destination $dest -Force
      $moved += $dest
    }
  return $moved
}
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m unittest tests.test_distribution_install -v
python -m unittest tests.test_cadence_loader -v
```

Expected: OK.

---

### Task 5: Rename Product UI To Insta360硬件提效平台

**Files:**
- Modify: `frontend/src/i18n/zhCN.ts`
- Modify: `frontend/index.html`
- Modify: `config/default.json`
- Modify: `docs/*.md`
- Test: `tests/test_frontend_build.py`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_frontend_build.py`:

```python
def test_platform_branding_uses_final_chinese_name(self) -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    zh = (ROOT / "frontend" / "src" / "i18n" / "zhCN.ts").read_text(encoding="utf-8")
    self.assertIn("Insta360硬件提效平台", index)
    self.assertIn('appTitle: "Insta360硬件提效平台"', zh)
    self.assertNotIn("硬件效率工具集", zh)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m unittest tests.test_frontend_build.FrontendBuildTests.test_platform_branding_uses_final_chinese_name -v
```

Expected: FAIL while old title is present.

- [ ] **Step 3: Update frontend title and text**

Change `frontend/src/i18n/zhCN.ts`:

```ts
export const uiText = {
  appTitle: "Insta360硬件提效平台",
  loadingTools: "正在加载平台能力",
  startupFailed: "平台启动失败",
  run: "开始运行",
  clear: "清空文件",
  uploadHint: "点击或拖拽文件到此处",
  noResult: "请选择输入并运行。",
  runFinished: "运行完成",
  downloadReport: "下载报告",
};
```

Change `frontend/index.html` title to:

```html
<title>Insta360硬件提效平台</title>
```

Change `config/default.json`:

```json
"app_name": "Insta360硬件提效平台"
```

- [ ] **Step 4: Build and verify**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_frontend.ps1
python -m unittest tests.test_frontend_build -v
```

Expected: OK.

---

### Task 6: Platform Workbench UI

**Files:**
- Create: `frontend/src/platform/PlatformHome.tsx`
- Create: `frontend/src/platform/ScriptManager.tsx`
- Create: `frontend/src/platform/SystemStatus.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add API client functions**

In `frontend/src/api/client.ts`, add:

```ts
export type Capability = ToolInfo & {
  type: "web_tool" | "cadence_tcl" | "system";
  command?: string;
  danger_level?: "low" | "medium" | "high";
  requires_confirmation?: boolean;
  show_in_platform: boolean;
  show_in_cadence: boolean;
};

export async function fetchCapabilities(): Promise<{ platform: { name: string; cadence_menu: string }; capabilities: Capability[] }> {
  const res = await fetch("/api/capabilities");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "平台能力加载失败");
  return payload;
}

export async function fetchPlatformStatus() {
  const res = await fetch("/api/platform/status");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "平台状态加载失败");
  return payload;
}
```

- [ ] **Step 2: Implement home dashboard**

Create `frontend/src/platform/PlatformHome.tsx`:

```tsx
import { Card, Col, Row, Statistic, Typography } from "antd";
import type { Capability } from "../api/client";

export function PlatformHome({ capabilities }: { capabilities: Capability[] }) {
  const webTools = capabilities.filter((item) => item.type === "web_tool");
  const scripts = capabilities.filter((item) => item.type === "cadence_tcl");
  return (
    <Row gutter={[16, 16]}>
      <Col span={8}><Card><Statistic title="Web 工具" value={webTools.length} /></Card></Col>
      <Col span={8}><Card><Statistic title="Cadence 脚本" value={scripts.length} /></Card></Col>
      <Col span={8}><Card><Statistic title="已启用脚本" value={scripts.filter((item) => item.show_in_cadence).length} /></Card></Col>
      <Col span={24}>
        <Card title="今日工作台">
          <Typography.Text type="secondary">从左侧选择 BOM、网表、SMT 或脚本管理能力。</Typography.Text>
        </Card>
      </Col>
    </Row>
  );
}
```

- [ ] **Step 3: Implement script manager view**

Create `frontend/src/platform/ScriptManager.tsx`:

```tsx
import { Table, Tag } from "antd";
import type { Capability } from "../api/client";

const dangerText: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险" };

export function ScriptManager({ capabilities }: { capabilities: Capability[] }) {
  const scripts = capabilities.filter((item) => item.type === "cadence_tcl");
  return (
    <Table
      size="middle"
      rowKey="id"
      dataSource={scripts}
      columns={[
        { title: "脚本名称", dataIndex: "name" },
        { title: "说明", dataIndex: "description" },
        { title: "命令", dataIndex: "command" },
        { title: "风险", dataIndex: "danger_level", render: (value) => <Tag color={value === "high" ? "red" : value === "medium" ? "gold" : "green"}>{dangerText[value] || "未分级"}</Tag> },
        { title: "状态", dataIndex: "show_in_cadence", render: (value) => value ? <Tag color="blue">已挂载</Tag> : <Tag>未挂载</Tag> },
      ]}
    />
  );
}
```

- [ ] **Step 4: Implement status view**

Create `frontend/src/platform/SystemStatus.tsx`:

```tsx
import { Card, Descriptions } from "antd";

export function SystemStatus({ status }: { status: any }) {
  return (
    <Card title="系统状态">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="平台">{status?.platform || "Insta360硬件提效平台"}</Descriptions.Item>
        <Descriptions.Item label="工具数量">{status?.tools ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="安装目录">{status?.root || "-"}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
```

- [ ] **Step 5: Wire navigation in `App.tsx`**

Add menu entries:

```tsx
const platformItems = [
  { key: "__home", label: "工作台" },
  { key: "__scripts", label: "脚本管理" },
  { key: "__status", label: "系统状态" },
];
```

Render:

```tsx
if (active === "__home") return <PlatformHome capabilities={capabilities} />;
if (active === "__scripts") return <ScriptManager capabilities={capabilities} />;
if (active === "__status") return <SystemStatus status={platformStatus} />;
```

- [ ] **Step 6: Build and verify**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_frontend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

Expected: OK.

---

### Task 7: BOM Conflict Review UX

**Files:**
- Modify: `frontend/src/tools/BomProcessWizard.tsx`
- Modify: `tests/test_frontend_build.py`

- [ ] **Step 1: Write failing frontend source test**

Append to `tests/test_frontend_build.py`:

```python
def test_bom_conflict_review_supports_user_selected_variants(self) -> None:
    text = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
    self.assertIn("conflict_choices", text)
    self.assertIn("保留此项", text)
    self.assertIn("受影响位号", text)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m unittest tests.test_frontend_build.FrontendBuildTests.test_bom_conflict_review_supports_user_selected_variants -v
```

Expected: FAIL if current UI only offers first-description merge.

- [ ] **Step 3: Implement conflict chooser**

In `BomProcessWizard.tsx`, when `result.status === "needs_confirmation"`:

- Render a table per conflict group.
- Each variant row shows `name`、`model`、`desc`、`grade`、`refs`/受影响位号.
- Add button text `保留此项`.
- Maintain state:

```ts
const [conflictChoices, setConflictChoices] = useState<Record<string, number>>({});
```

Call:

```ts
handleRun({ merge_conflicts: true, conflict_choices: conflictChoices })
```

- [ ] **Step 4: Verify existing backend conflict tests**

Run:

```powershell
python -m unittest tests.test_bom_process_conflicts -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_frontend.ps1
```

Expected: OK.

---

### Task 8: Controlled Tcl Re-Enablement

**Files:**
- Modify: `scripts/lib/Cadence.ps1`
- Modify: `config/capabilities.json`
- Test: `tests/test_cadence_loader.py`

- [ ] **Step 1: Write test for opt-in script menu generation**

Add to `tests/test_cadence_loader.py`:

```python
def test_generated_loader_can_mount_enabled_tcl_scripts_without_renaming_registeraction(self) -> None:
    text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")
    self.assertIn("show_in_cadence", text)
    self.assertIn("AddAccessoryMenu", text)
    self.assertNotIn("rename RegisterAction", text)
```

- [ ] **Step 2: Implement generator from registry**

In `scripts/lib/Cadence.ps1`, add a helper that reads `config/capabilities.json`, filters `type == cadence_tcl` and `show_in_cadence == true`, then injects lines like:

```tcl
AddAccessoryMenu "insta360_HW" "选中器件切换NC" "::capNCToggleSelected::toggleFromMenu"
```

Do not source enhanced modules inside the loader until encoding and namespace behavior are independently verified.

- [ ] **Step 3: Keep default disabled**

Keep all Cadence script `show_in_cadence` values as `false` in the committed default registry. Enable only on a local test branch or `config/local.json` after Capture validation.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m unittest tests.test_cadence_loader -v
```

Expected: OK and no regression to unsafe loader.

---

### Task 9: One-Click Install/Update Platform Hardening

**Files:**
- Modify: `install.ps1`
- Modify: `update.ps1`
- Modify: `scripts/lib/Update.ps1`
- Modify: `scripts/lib/Cadence.ps1`
- Test: `tests/test_distribution_install.py`
- Test: `tests/test_update_api.py`

- [ ] **Step 1: Add tests**

Ensure tests assert:

- `install.ps1` sources `TclScripts.ps1`.
- `install.ps1` calls `Disable-HwAgentVendorAutoLoadScripts` for known vendor autoload dirs only when explicitly enabled or detected.
- `update.ps1` preserves `data`, `config/local.json`, and reruns `Install-CadenceLoader`.
- `/api/update/run` calls update script.

- [ ] **Step 2: Implement preservation and redeploy**

After `Invoke-HwAgentGitUpdate`, update script must:

```powershell
. (Join-Path $Root "scripts\lib\Cadence.ps1")
$Python = Find-Python -Root $Root
$AutoLoadDirs = Find-CadenceAutoLoadDirs
Install-CadenceLoader -ToolRoot $Root -PythonPath $Python -AutoLoadDirs $AutoLoadDirs | Out-Null
```

- [ ] **Step 3: Verify**

Run:

```powershell
python -m unittest tests.test_distribution_install tests.test_update_api -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

Expected: OK.

---

### Task 10: Visual Verification

**Files:**
- No production files unless screenshot review reveals defects.

- [ ] **Step 1: Start local service**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_tool_suite.ps1 -Restart
```

- [ ] **Step 2: Browser verify**

Open:

```text
http://127.0.0.1:8765
```

Verify:

- 首页首屏是工作台，不是营销页。
- 标题是 `Insta360硬件提效平台`。
- 左侧有 `工作台`、`脚本管理`、`系统状态` 和现有 6 个工具。
- BOM 处理仍支持 Cadence URL 参数：
  - `?tool=bom_process&source=<path>&name=<dsn>`
- 冲突确认有 `保留此项`、`受影响位号`。
- 按钮、提示、空状态都是中文。

- [ ] **Step 3: Runtime API verify**

Run:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/tools
Invoke-RestMethod http://127.0.0.1:8765/api/capabilities
Invoke-RestMethod http://127.0.0.1:8765/api/platform/status
```

Expected:

- `/api/tools` 返回 6 个 available Web 工具。
- `/api/capabilities` 返回平台名和 Web/Tcl 能力。
- `/api/platform/status` 返回 status ok。

---

## Final Verification

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

Expected: all tests and frontend build pass.

Run deployment smoke:

```powershell
$target='D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl'
$decoded=[Text.Encoding]::GetEncoding(936).GetString([IO.File]::ReadAllBytes($target))
$decoded.Contains('AddAccessoryMenu "insta360_HW" "进入平台"')
$decoded.Contains('AddAccessoryMenu "insta360_HW" "导出并处理BOM"')
$decoded.Contains('rename RegisterAction')
$decoded.Contains('orcad_enhanced_tools.tcl')
```

Expected:

```text
True
True
False
False
```

Manual Capture gate:

- 重启 Capture。
- Command Window 不再出现由 `iac_bom_tool.tcl` 引发的 `invalid command name "RegisterAction"`。
- 菜单 `insta360_HW` 出现。
- 点击 `进入平台` 能打开 Web 平台。
- 点击 `导出并处理BOM` 能导出并进入 BOM 处理流程。

## Self-Review

- Cadence 报错消除：Task 1 + 当前安全部署覆盖。
- 去掉自定义脚本：Task 1 当前完成；Task 4 防止回归。
- 平台名：Task 5。
- 统一管理 Web 工具和 Tcl 脚本：Task 2、3、6、8。
- 一键安装/更新：Task 9。
- UI 更自然高效美观：Task 6、7、10。
- 原有功能不退化：Final Verification + 现有 53 个测试。
- 自定义 Tcl 后续恢复：Task 8 明确要求注册表 opt-in，不再直接 autoload。
