# Insta360硬件提效平台恢复与落地执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先恢复 Cadence 正常启动，再把 BOM、启动、脚本管理、安装更新和中文 UI 全部落地到「Insta360硬件提效平台」，且原有 6 个 Web 工具不退化。

**Architecture:** Cadence 侧只保留一个受控 loader，默认只提供 `进入平台` 和 `导出并处理BOM`；所有增强 Tcl 脚本从官方 autoload 移出，改由平台能力注册表管理。Web 后端继续用 Python 标准库 HTTP，前端用 React/Vite/Ant Design 风格组件组织中文工作台，BOM 转换和冲突确认走结构化 API。

**Tech Stack:** PowerShell 安装/更新/部署、GBK Tcl loader、Python 标准库后端、React + Vite + TypeScript、unittest、Vite build。

---

## Task 1: Cadence 恢复与安全 loader

**Files:**
- Modify: `scripts/lib/TclScripts.ps1`
- Modify: `scripts/lib/Paths.ps1`
- Modify: `scripts/lib/Cadence.ps1`
- Modify: `cadence/iac_bom_tool.tcl`
- Test: `tests/test_cadence_loader.py`
- Test: `tests/test_cadence_integration.py`

- [ ] 证据检查：确认用户 autoload 目录没有 `iac_bom_tool.tcl`，vendor autoload 根目录没有 `orCAD_Enhanced_Tools_V*.tcl*`。
- [ ] 加回安全 loader 生成测试：loader 必须 GBK 可解码，菜单为 `insta360_HW`，中文项为 `进入平台`、`导出并处理BOM`，不得包含 `orcad_enhanced_tools.tcl`、`rename RegisterAction`、自定义增强脚本菜单。
- [ ] 修复/保持 `Disable-HwAgentVendorAutoLoadScripts`：只移动自定义增强脚本及其备份，不移动 Cadence 官方脚本。
- [ ] 重新部署安全 loader 到用户 autoload 目录。
- [ ] 验证 deployed loader 字节内容和菜单内容。

## Task 2: 启动链路可见、可复用、不卡死

**Files:**
- Modify: `launch_tool_suite.ps1`
- Modify: `launch_tool_suite_hidden.vbs`
- Modify: `app/frontend/waiting.html`
- Modify: `scripts/lib/Service.ps1`
- Test: `tests/test_launch_and_package.py`
- Test: `tests/test_cadence_integration.py`

- [ ] 写启动复用测试：已有健康服务时不再开新服务进程，仍然打开目标 URL。
- [ ] 写等待页测试：首次启动服务时先打开中文等待页，轮询 `/api/health`，就绪后跳转平台。
- [ ] 修复隐藏启动无反馈问题：把等待页作为用户反馈，后台启动失败时显示中文错误和日志路径。
- [ ] 验证从 PowerShell 调用 `launch_tool_suite.ps1 -Tool bom_process -Source <xlsx> -Name <board>` 能打开或打印目标 URL。

## Task 3: BOM 字段完整和冲突合并

**Files:**
- Modify: `tools/bom/convert_cadence_bom.py`
- Modify: `app/backend/bom_process.py`
- Modify: `frontend/src/tools/BomProcessWizard.tsx`
- Test: `tests/test_capture_bom_fields.py`
- Test: `tests/test_bom_process_conflicts.py`

- [ ] 固化完整模板字段：`父项编码、描述、子项编码、名称、型号、描述、单位、数量、位号、备注、物料优选等级、物料优选等级备注、替代组编码、替代策略、替代方式、替代优先级、发料方式、是否参与MRP运算、是否跳层`。
- [ ] Tcl/JSON/Cadence xlsx 转换尽量保留所有 EffectiveProps，并扩充中英属性映射。
- [ ] 后端检测同一物料编码的名称/型号/描述/等级等冲突，返回 `needs_confirmation` 和逐字段候选值。
- [ ] 前端弹出中文冲突确认框，让用户逐字段选择保留项后再提交合并决策。
- [ ] 最终 ZIP 文件名使用 `单板名_yyyyMMdd_HHmmss.zip`。

## Task 4: 平台能力注册表与 Tcl 脚本管理

**Files:**
- Modify: `config/capabilities.json`
- Modify: `app/backend/capabilities.py`
- Modify: `app/backend/suite_app.py`
- Modify: `frontend/src/platform/ScriptManager.tsx`
- Create/Modify: `cadence/modules/*.tcl`
- Test: `tests/test_capabilities_registry.py`
- Test: `tests/test_platform_api.py`
- Test: `tests/test_cadence_loader.py`

- [ ] 注册所有 Web 工具和 Tcl 脚本能力，默认危险脚本 `show_in_cadence=false` 且 `requires_confirmation=true`。
- [ ] 从 `orCAD_Enhanced_Tools_V1.8.tcl` 拆模块，不允许模块内出现 `RegisterAction` 或 `AddAccessoryMenu`。
- [ ] 脚本管理页中文展示脚本状态、风险、启用/禁用操作。
- [ ] loader 只注入已启用且允许显示的脚本菜单。

## Task 5: 中文 UI、安装更新、全量验收

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n/zhCN.ts`
- Modify: `frontend/src/styles.css`
- Modify: `install.ps1`
- Modify: `update.ps1`
- Modify: `docs/INSTALL.md`
- Modify: `docs/UPDATE.md`
- Test: `tests/test_frontend_build.py`
- Test: `tests/test_distribution_install.py`
- Test: `tests/test_update_api.py`
- Test: `scripts/verify_all.ps1`

- [ ] 全 UI 扫描，不保留英文用户可见标题、按钮和错误提示。
- [ ] 平台标题统一为 `Insta360硬件提效平台`。
- [ ] 安装/更新保留 `data/`、`config/local.json`、历史记录和用户输出。
- [ ] 一键安装/更新后自动清理危险 autoload 并部署安全 loader。
- [ ] 运行 `scripts\verify_all.ps1`，确认 unittest 和前端 build 全部通过。