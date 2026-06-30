from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendBuildTests(unittest.TestCase):
    def test_frontend_package_uses_required_stack(self) -> None:
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        dependencies = package["dependencies"]

        self.assertIn("react", dependencies)
        self.assertIn("antd", dependencies)
        self.assertIn("@ant-design/icons", dependencies)
        self.assertIn("@tanstack/react-table", dependencies)
        self.assertIn("lucide-react", dependencies)

    def test_frontend_lazy_loads_large_workbench_views(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")

        self.assertIn("lazy(", app)
        self.assertIn('import("./tools/BomProcessWizard")', app)
        self.assertIn('import("./tools/LegacyToolPane")', app)
        self.assertIn("Suspense", app)
        self.assertIn("lazy(", legacy)
        self.assertIn('import("./BomComparePane")', legacy)
        self.assertIn('import("./NetlistComparePane")', legacy)
        self.assertIn('import("./SmtPackageCheckPane")', legacy)

    def test_frontend_exposes_reusable_history_assets_and_persistent_workspaces(self) -> None:
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        asset_picker = ROOT / "frontend" / "src" / "components" / "HistoryBomPicker.tsx"
        workspace_store = ROOT / "frontend" / "src" / "state" / "toolWorkspace.ts"
        bom_compare = (ROOT / "frontend" / "src" / "tools" / "BomComparePane.tsx").read_text(encoding="utf-8")
        smt = (ROOT / "frontend" / "src" / "tools" / "SmtPackageCheckPane.tsx").read_text(encoding="utf-8")
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertTrue(asset_picker.exists())
        self.assertTrue(workspace_store.exists())
        self.assertIn("/api/assets", client)
        self.assertIn("fetchAssets", client)
        self.assertIn("HistoryBomPicker", asset_picker.read_text(encoding="utf-8"))
        self.assertIn("选择历史 BOM", asset_picker.read_text(encoding="utf-8"))
        self.assertIn("Modal", asset_picker.read_text(encoding="utf-8"))
        self.assertIn("DatabaseOutlined", asset_picker.read_text(encoding="utf-8"))
        self.assertIn("useToolWorkspace", workspace_store.read_text(encoding="utf-8"))
        self.assertIn("localStorage", workspace_store.read_text(encoding="utf-8"))
        self.assertIn("HistoryBomPicker", bom_compare)
        self.assertIn("historyBom1", bom_compare)
        self.assertIn("historyBom2", bom_compare)
        self.assertIn("HistoryBomPicker", smt)
        self.assertIn("historyBom", smt)
        self.assertIn("useToolWorkspace", legacy)
        self.assertIn("useToolWorkspace", wizard)

    def test_update_controls_split_check_and_run_actions(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")

        self.assertIn("onCheckUpdate", text)
        self.assertIn("检查更新", text)
        self.assertIn("立即更新", text)
        self.assertNotIn("一键更新", text)

    def test_uninstall_progress_modal_requires_user_close_and_marks_service_exit_done(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.close()", text)
        self.assertIn("setUninstallOpen(false)", text)
        self.assertIn("progress: 100", text)
        self.assertIn("done: true", text)
        self.assertIn("onCloseUninstallProgress", text)
        self.assertIn("\u5173\u95ed", text)
        self.assertIn("\u5378\u8f7d\u5b8c\u6210", text)

    def test_build_script_installs_builds_and_copies_dist_to_app_frontend(self) -> None:
        text = (ROOT / "scripts" / "build_frontend.ps1").read_text(encoding="utf-8")

        self.assertIn("npm install", text)
        self.assertIn("npm install failed", text)
        self.assertIn("npm run build", text)
        self.assertIn("frontend build failed", text)
        self.assertIn("app\\frontend", text)
        self.assertRegex(text, r"Copy-Item[\s\S]+dist")
        self.assertIn("waiting.html", text)

    def test_frontend_ui_is_simplified_chinese(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        zh = (ROOT / "frontend" / "src" / "i18n" / "zhCN.ts").read_text(encoding="utf-8")
        combined = app + index + zh

        self.assertIn('lang="zh-CN"', index)
        self.assertIn("<title>Insta360硬件提效平台</title>", index)
        self.assertIn("zhCN", app)
        self.assertIn("Insta360硬件提效平台", combined)
        forbidden_visible_words = r">\s*(Upload|Download|Run|Update|Loading|Error|Settings|Tools)\s*<"
        self.assertIsNone(re.search(forbidden_visible_words, combined))

    def test_waiting_page_uses_final_chinese_platform_name(self) -> None:
        waiting = (ROOT / "app" / "frontend" / "waiting.html").read_text(encoding="utf-8")

        self.assertIn("Insta360硬件提效平台", waiting)
        self.assertIn("正在启动", waiting)
        self.assertIn("本地服务", waiting)
        self.assertNotIn("硬件效率工具集", waiting)
        self.assertNotIn("姝", waiting)
        self.assertNotIn("鈿", waiting)

    def test_platform_branding_uses_final_chinese_name(self) -> None:
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        zh = (ROOT / "frontend" / "src" / "i18n" / "zhCN.ts").read_text(encoding="utf-8")
        config = (ROOT / "config" / "default.json").read_text(encoding="utf-8")

        self.assertIn("Insta360硬件提效平台", index)
        self.assertIn('appTitle: "Insta360硬件提效平台"', zh)
        self.assertIn('"app_name": "Insta360硬件提效平台"', config)
        self.assertNotIn("硬件效率工具集", zh)

    def test_platform_workbench_loads_capabilities_and_script_manager(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        script_manager = (ROOT / "frontend" / "src" / "platform" / "ScriptManager.tsx").read_text(encoding="utf-8")
        history_view = ROOT / "frontend" / "src" / "platform" / "HistoryView.tsx"

        self.assertIn("fetchCapabilities", app)
        self.assertIn("fetchPlugins", app)
        self.assertIn("fetchHistory", app)
        self.assertIn("fetchPlatformStatus", app)
        self.assertIn("Promise.allSettled", app)
        self.assertIn("工作台", app)
        self.assertIn("插件管理", app)
        self.assertIn("历史记录", app)
        self.assertIn("系统状态", app)
        self.assertIn("可挂载脚本", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("待拆分脚本", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("fetchLifecycleCheck", client)
        self.assertIn("/api/lifecycle/check", client)
        self.assertIn("安装自检", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("Badge", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("/api/capabilities", client)
        self.assertIn("/api/plugins", client)
        self.assertIn("/api/history", client)
        self.assertIn("setCadenceMenuVisibility", client)
        self.assertIn("setPluginCadenceMenuVisibility", client)
        self.assertIn("deleteHistoryRun", client)
        self.assertIn("clearHistory", client)
        self.assertIn("/cadence-menu", client)
        self.assertIn("platform: PluginInfo[]", client)
        self.assertIn("show_in_cadence", script_manager)
        self.assertIn("Tabs", script_manager)
        self.assertIn("已挂载", script_manager)
        self.assertIn("未挂载", script_manager)
        self.assertIn("刷新", script_manager)
        self.assertIn("Capture 热更新指令", script_manager)
        self.assertIn("Command Window", script_manager)
        self.assertIn("source [file join $env(HOME)", script_manager)
        self.assertIn("onRefresh", script_manager)
        self.assertIn("refreshPlugins", app)
        self.assertIn("Cadence 系统脚本", script_manager)
        self.assertIn("平台自带", script_manager)
        self.assertIn("自定义脚本", script_manager)
        self.assertIn("只读", script_manager)
        self.assertIn("未挂载", script_manager)
        self.assertIn("Switch", script_manager)
        self.assertIn("Popconfirm", script_manager)
        self.assertIn("确认挂载脚本", script_manager)
        self.assertIn("待拆分", script_manager)
        self.assertTrue(history_view.exists())
        history_text = history_view.read_text(encoding="utf-8")
        self.assertIn("历史记录", history_text)
        self.assertIn("查看详情", history_text)
        self.assertIn("删除记录", history_text)
        self.assertIn("清空历史", history_text)
        self.assertIn("输出文件", history_text)

    def test_bom_process_capture_config_contains_required_fields(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        for field in [
            "Item",
            "Quantity",
            "Reference",
            "Part Number",
            "Value",
            "\u89c4\u683c\u578b\u53f7",
            "\u5668\u4ef6\u63cf\u8ff0\uff08\u65b0\u6574\u7406\uff09",
            "\u7269\u6599\u540d\u79f0",
            "\u7b49\u7ea7",
            "PCB Footprint",
            "PCB\u5c01\u88c5",
            "Part Type",
            "Part Reference",
            "Source Package",
            "Source Part",
        ]:
            self.assertIn(f"{{{field}}}", wizard)
        self.assertIn("const CONFIG", wizard)

    def test_bom_process_wizard_consumes_cadence_url_preset_and_runs_backend(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn('new URLSearchParams(window.location.search).get("tool")', app)
        self.assertIn('setActive(requested || "__home")', app)
        self.assertIn("URLSearchParams", wizard)
        self.assertIn('params.get("source")', wizard)
        self.assertIn('params.get("name")', wizard)
        self.assertIn("source_bom: sp", wizard)
        self.assertIn('runTool("bom_process"', wizard)

    def test_bom_conflict_review_supports_user_selected_variants(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("merge_conflicts", wizard)
        self.assertIn("conflict_choices", wizard)
        self.assertIn('pres?.reason === "part_property_conflicts"', wizard)
        self.assertIn("conflicts.length", wizard)
        self.assertIn("onApply", wizard)
        self.assertIn("onSplit", wizard)
        self.assertIn("CConflict", wizard)
        self.assertIn("conflictChoices", wizard)

    def test_bom_conflict_review_supports_recommended_merge_without_manual_choices(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("applyRecommendedMerge", wizard)
        self.assertIn("onRecommendedMerge", wizard)
        self.assertIn("按推荐合并", wizard)
        self.assertIn("conflict_choices: {}", wizard)

    def test_bom_process_wizard_confirms_shield_bracket_candidates(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("shield_bracket_candidates", wizard)
        self.assertIn("confirm_shields", wizard)
        self.assertIn("shield_candidates", wizard)
        self.assertIn("屏蔽支架、NC、等级、位号类型、硬件版本敏感物料", wizard)
        self.assertNotIn("屏蔽支架/屏蔽罩", wizard)
        self.assertIn("确认作为屏蔽支架进入 BOM", wizard)

    def test_bom_wizard_does_not_treat_successful_merge_summary_as_pending_conflict(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        helper = re.search(r"function hasBomConflicts\(pres: any\) \{(?P<body>[\s\S]+?)\n\}", wizard)
        self.assertIsNotNone(helper)
        body = helper.group("body")
        self.assertIn('pres?.reason === "part_property_conflicts"', body)
        self.assertIn("conflict_count", body)
        self.assertNotIn("summary?.conflicts", body)
        self.assertIn('r.status === "ok"', wizard)
        self.assertIn('setStage("risk")', wizard)

    def test_bom_process_review_uses_horizontal_workspace(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("process-grid", wizard)
        self.assertIn("conflict-main", wizard)
        self.assertIn("conflict-workbench", wizard)
        self.assertIn("activeConflictCode", wizard)
        self.assertIn("conflict-index-list", wizard)
        self.assertIn("renderFullRefs", wizard)
        self.assertIn(".process-grid", css)
        self.assertIn(".conflict-workbench", css)
        self.assertIn(".conflict-index-list", css)
        self.assertIn(".variant-field--wide", css)
        self.assertIn("grid-template-columns", css)

    def test_bom_wizard_does_not_blank_when_risk_step_has_no_process_file(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("process_file", wizard)
        self.assertIn("bom_risk_check", wizard)
        self.assertIn('setRres({ status: "error"', wizard)

    def test_bom_risk_review_is_split_into_tabs(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("Tabs", wizard)
        self.assertIn("riskTabs", wizard)
        self.assertIn('key: "risk-overview"', wizard)
        self.assertIn('key: "risk-basic"', wizard)
        self.assertIn('key: "risk-grade"', wizard)
        self.assertIn('key: "risk-type"', wizard)
        self.assertIn('key: "risk-outputs"', wizard)

    def test_bom_deliver_view_previews_final_bom(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("function BomPreviewTable", wizard)
        self.assertIn("pres?.preview", wizard)
        self.assertIn("preview.rows", wizard)
        self.assertIn("preview.headers", wizard)
        self.assertIn("final-bom-preview", wizard)

    def test_bom_risk_step_keeps_final_bom_preview(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("<RiskView rrun={rrun} rres={rres} pres={pres}", wizard)
        self.assertIn("function RiskView({ rrun, rres, pres, onNext, onBack }: any)", wizard)
        self.assertIn('key: "risk-final-preview"', wizard)
        self.assertIn("<BomPreviewTable preview={pres?.preview} />", wizard)

    def test_bom_compare_uses_dedicated_horizontal_workbench(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "BomComparePane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('tool.id === "bom_compare"', legacy)
        self.assertIn("<BomComparePane", legacy)
        self.assertIn("compare-workbench", pane)
        self.assertIn("compare-shell", pane)
        self.assertIn("compare-rail", pane)
        self.assertIn("compare-detail", pane)
        self.assertIn("compare-inspector", pane)
        self.assertIn("part_summary", pane)
        self.assertIn("origin", pane)
        self.assertIn("risks", pane)
        self.assertIn("review_guide", pane)
        self.assertIn("focus_items", pane)
        self.assertIn(".compare-shell", css)
        self.assertIn("grid-template-columns: minmax(320px, 380px) minmax(560px, 1fr) minmax(420px, 520px)", css)
        self.assertIn(".compare-inspector", css)

    def test_bom_compare_can_use_wide_desktop_space(self) -> None:
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        app_content = re.search(r"\.app-content\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(app_content)
        self.assertNotIn("max-width: 1280px", app_content.group("body"))
        self.assertIn("width: 100%", app_content.group("body"))

        workbench = re.search(r"\.compare-workbench\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(workbench)
        self.assertIn("width: 100%", workbench.group("body"))
        self.assertNotIn("1480px", workbench.group("body"))

        shell = re.search(r"\.compare-shell\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(shell)
        self.assertIn("minmax(320px, 380px) minmax(560px, 1fr) minmax(420px, 520px)", shell.group("body"))

    def test_netlist_compare_uses_dedicated_review_workbench(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "NetlistComparePane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('tool.id === "netlist_compare"', legacy)
        self.assertIn("<NetlistComparePane", legacy)
        self.assertIn("netlist-workbench", pane)
        self.assertIn("netlist_review", pane)
        self.assertIn("focus_items", pane)
        self.assertIn("网络改名", pane)
        self.assertIn("疑似拆网", pane)
        self.assertIn("疑似并网", pane)
        self.assertIn("关键网络变化", pane)
        self.assertIn("result.warnings", pane)
        self.assertIn("pstxprt.dat 可选", pane)
        self.assertIn('directory="true"', pane)
        self.assertIn('webkitdirectory="true"', pane)
        self.assertIn("Allegro", pane)
        self.assertIn("pstxnet.dat", pane)
        self.assertIn(".netlist-shell", css)
        self.assertIn(".netlist-inspector", css)

    def test_smt_package_check_uses_dedicated_review_workbench(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "SmtPackageCheckPane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('tool.id === "smt_package_check"', legacy)
        self.assertIn("<SmtPackageCheckPane", legacy)
        self.assertIn("smt-workbench", pane)
        self.assertIn("smt_package_review", pane)
        self.assertIn("focus_items", pane)
        self.assertIn("BOM 缺位号", pane)
        self.assertIn("BOM 多余位号", pane)
        self.assertIn("同料多封装", pane)
        self.assertIn("高风险封装", pane)
        self.assertIn("NC 未贴跳过", pane)
        self.assertIn("非贴片对象跳过", pane)
        self.assertIn("跳过未贴/工艺", pane)
        self.assertIn("已跳过", pane)
        self.assertIn("已处理 PLM/OA 成品 BOM", pane)
        self.assertIn("不要选择 Capture 原始 BOM", pane)
        self.assertIn("选择 PLM/OA BOM", pane)
        self.assertIn("smt-filter-grid", pane)
        self.assertIn("smt-filter-chip", pane)
        self.assertIn("smt-focus-package", pane)
        self.assertNotIn("<Segmented", pane)
        self.assertIn('directory="true"', pane)
        self.assertIn('webkitdirectory="true"', pane)
        self.assertIn("pstxprt.dat", pane)
        self.assertIn("选择 Allegro 目录", pane)
        self.assertIn(".smt-shell", css)
        self.assertIn(".smt-inspector", css)
        self.assertIn(".smt-filter-grid", css)
        self.assertIn(".smt-filter-chip", css)


if __name__ == "__main__":
    unittest.main()
