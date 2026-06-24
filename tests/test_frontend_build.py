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
        self.assertIn("@tanstack/react-table", dependencies)
        self.assertIn("lucide-react", dependencies)

    def test_build_script_installs_builds_and_copies_dist_to_app_frontend(self) -> None:
        text = (ROOT / "scripts" / "build_frontend.ps1").read_text(encoding="utf-8")

        self.assertIn("npm install", text)
        self.assertIn("npm run build", text)
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

        self.assertIn("fetchCapabilities", app)
        self.assertIn("fetchPlatformStatus", app)
        self.assertIn("工作台", app)
        self.assertIn("脚本管理", app)
        self.assertIn("系统状态", app)
        self.assertIn("可挂载脚本", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("待拆分脚本", (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8"))
        self.assertIn("/api/capabilities", client)
        self.assertIn("setCadenceMenuVisibility", client)
        self.assertIn("/cadence-menu", client)
        self.assertIn("show_in_cadence", script_manager)
        self.assertIn("未挂载", script_manager)
        self.assertIn("Switch", script_manager)
        self.assertIn("Popconfirm", script_manager)
        self.assertIn("确认挂载脚本", script_manager)
        self.assertIn("待拆分", script_manager)

    def test_bom_process_capture_config_contains_required_fields(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        expected = (
            "{Item}\\\\t{Quantity}\\\\t{Reference}\\\\t{Part Number}\\\\t{Value}\\\\t{规格型号}\\\\t"
            "{器件描述（新整理）}\\\\t{物料名称}\\\\t{等级}\\\\t{PCB Footprint}\\\\t{PCB封装}\\\\t"
            "{Part Type}\\\\t{Part Reference}\\\\t{Source Package}\\\\t{Source Part}"
        )

        self.assertIn(expected, wizard)
        self.assertIn("复制配置", wizard)

    def test_bom_process_wizard_consumes_cadence_url_preset_and_runs_backend(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("URLSearchParams", wizard)
        self.assertIn('params.get("source")', wizard)
        self.assertIn('params.get("name")', wizard)
        self.assertIn("source_bom: presetSource", wizard)
        self.assertIn('runTool("bom_process"', wizard)

    def test_bom_conflict_review_supports_user_selected_variants(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("conflict_choices", wizard)
        self.assertIn("conflictChoices", wizard)
        self.assertIn("保留此项", wizard)
        self.assertIn("受影响位号", wizard)


if __name__ == "__main__":
    unittest.main()
