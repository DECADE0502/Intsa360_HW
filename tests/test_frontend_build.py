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


if __name__ == "__main__":
    unittest.main()
