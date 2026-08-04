from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from _constants import BRAND_NAME_LEGACY


ROOT = Path(__file__).resolve().parents[1]


class FrontendBuildTests(unittest.TestCase):
    def test_update_progress_modal_shows_the_complete_scrollable_log(self) -> None:
        component = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('className="update-progress-modal"', component)
        self.assertIn("width={900}", component)
        self.assertIn("updateLogRef", component)
        self.assertIn("updateLogAutoFollowRef", component)
        self.assertIn("scrollHeight", component)
        self.assertIn("min-height: 260px", styles)
        self.assertIn("max-height: 46vh", styles)
        self.assertIn("overflow: auto", styles)

    def test_bom_review_can_return_to_source_and_clear_the_current_workflow(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("function clearBomWorkflow", wizard)
        self.assertIn("function clearAndReturnToSource", wizard)
        self.assertIn("onClear={clearAndReturnToSource}", wizard)
        self.assertIn("onClear", wizard)
        self.assertIn("返回并清空", wizard)
        self.assertIn("setPresetConsumed(true)", wizard)
        self.assertIn('window.history.replaceState({}, "", cleanUrl)', wizard)
        self.assertIn("bom-review-actions", wizard)

    def test_frontend_package_uses_required_stack(self) -> None:
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        dependencies = package["dependencies"]

        self.assertIn("react", dependencies)
        self.assertIn("antd", dependencies)
        self.assertIn("@ant-design/icons", dependencies)
        self.assertIn("lucide-react", dependencies)

    def test_user_notifications_use_the_antd_app_context(self) -> None:
        paths = [
            ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx",
            ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx",
        ]

        for path in paths:
            source = path.read_text(encoding="utf-8")
            antd_import = source.split('from "antd";', 1)[0]
            self.assertNotRegex(antd_import, r"\bmessage\b", path.name)
            self.assertIn("App.useApp()", source, path.name)

    def test_service_health_poll_is_bounded_and_nonoverlapping(self) -> None:
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        runtime_refresh = app.split("async function refreshRuntimeStatus", 1)[1].split(
            "function triggerReconnectProtocol", 1
        )[0]

        self.assertIn("HEALTH_PROBE_TIMEOUT_MS", client)
        self.assertIn("fetchServiceHealth(opts?: ApiOpts)", client)
        self.assertIn('"/api/health"', client)
        self.assertIn("fetchServiceHealth", runtime_refresh)
        self.assertNotIn("fetchPlatformStatus", runtime_refresh)
        self.assertNotIn("fetchVersion", runtime_refresh)
        self.assertIn("healthProbeInFlight", app)
        self.assertIn("healthProbeFailures", app)
        self.assertIn("healthProbeFailures.current >= 2", app)
        self.assertIn("if (healthProbeInFlight.current) return healthProbeInFlight.current", app)

    def test_vite_build_separates_stable_vendor_chunks(self) -> None:
        config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")

        self.assertIn("manualChunks", config)
        self.assertIn('return "vendor-react"', config)
        self.assertIn('return "vendor-antd"', config)

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
        self.assertIn('import("./SingleNetworkCheckPane")', legacy)
        self.assertIn('import("./tools/smtView/SmtViewPane")', app)

    def test_frontend_exposes_reusable_history_assets_and_persistent_workspaces(self) -> None:
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        asset_picker = ROOT / "frontend" / "src" / "components" / "HistoryBomPicker.tsx"
        workspace_store = ROOT / "frontend" / "src" / "state" / "toolWorkspace.ts"
        bom_compare = (ROOT / "frontend" / "src" / "tools" / "BomComparePane.tsx").read_text(encoding="utf-8")
        smt = (ROOT / "frontend" / "src" / "tools" / "smtView" / "SmtViewPane.tsx").read_text(encoding="utf-8")
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

    def test_bom_finish_syncs_history_assets_and_resets_for_next_bom(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        picker = (ROOT / "frontend" / "src" / "components" / "HistoryBomPicker.tsx").read_text(encoding="utf-8")

        self.assertIn("insta360_hw:assets-updated", wizard)
        self.assertIn("window.dispatchEvent", wizard)
        self.assertIn("完成并处理新的 BOM", wizard)
        self.assertIn("finishAndStartNewBom", wizard)
        self.assertIn("window.history.replaceState", wizard)
        self.assertIn('setStage("source")', wizard)
        self.assertIn("setSp(\"\")", wizard)
        self.assertIn("setPres(null)", wizard)
        self.assertIn("setRres(null)", wizard)
        self.assertIn("setPresetConsumed(true)", wizard)

        self.assertIn("insta360_hw:assets-updated", picker)
        self.assertIn("addEventListener", picker)
        self.assertIn("removeEventListener", picker)
        self.assertIn("load()", picker)

    def test_frontend_review_fix_regressions_are_guarded(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        netlist = (ROOT / "frontend" / "src" / "tools" / "NetlistComparePane.tsx").read_text(encoding="utf-8")
        panes = [
            ROOT / "frontend" / "src" / "tools" / "NetlistComparePane.tsx",
            ROOT / "frontend" / "src" / "tools" / "SingleNetworkCheckPane.tsx",
        ]
        bom_compare = (ROOT / "frontend" / "src" / "tools" / "BomComparePane.tsx").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('textOf(data?.["位号"]) || textOf(data?.["位号"])', netlist)
        self.assertIn('textOf(data?.["位号"]) || textOf(data?.["Pin"])', netlist)
        self.assertIn("document.body.appendChild(a)", wizard)
        self.assertIn("setTimeout(() =>", wizard)
        self.assertIn("URL.revokeObjectURL(u)", wizard)
        self.assertIn("a.remove()", wizard)
        self.assertIn("Upload.LIST_IGNORE", wizard)
        self.assertIn("toUserMessage(e)", wizard)
        self.assertNotIn("String(e?.message ?? e)", wizard)
        for pane in panes:
            text = pane.read_text(encoding="utf-8")
            self.assertIn("setSelectedKey((prev)", text, pane.name)
            self.assertIn("prev &&", text, pane.name)
        self.assertIn(
            'setSelectedReference(next.semantic?.placement_diff?.[0]?.reference || "")',
            bom_compare,
        )
        self.assertIn('setSelectedReference("")', bom_compare)

    def test_update_controls_split_check_and_run_actions(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

        self.assertIn("onCheckUpdate", text)
        self.assertIn("检查更新", text)
        self.assertIn("立即更新", text)
        self.assertNotIn("一键更新", text)
        self.assertIn("update_notice", client)
        self.assertIn("notice_status", client)
        self.assertIn("UpdateNotice", text)
        self.assertIn("noticeOpen", text)
        self.assertIn("setUpdateNotice", text)
        self.assertIn("更新公告", text)
        self.assertIn("查看更新公告", text)
        self.assertIn("本次更新要点", text)

    def test_update_notice_surfaces_download_integrity_status(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

        self.assertIn("integrity_status", client)
        self.assertIn("download_strategy", client)
        self.assertIn("integrityStatus", text)
        self.assertIn("manifest_sha256_required", text)
        self.assertNotIn("source_zip_fallback", text)

    def test_update_ui_rehydrates_active_jobs_and_respects_update_eligibility(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

        self.assertIn("setCanUpdate", text)
        self.assertIn("disabled={!canUpdate}", text)
        self.assertIn('updateReason === "updater_too_old"', text)
        self.assertNotIn('updateReason === "launcher_too_old"', text)
        self.assertIn("info.can_update", text)
        self.assertIn("info.remote_status", text)
        self.assertIn("fetchUpdateStatus", text)
        self.assertIn("status.running", text)
        self.assertIn("setProgressOpen(true)", text)
        self.assertIn('updateStatus?.phase === "cancelled"', text)
        self.assertIn("cancelled: boolean", client)

    def test_update_ui_starts_polling_only_after_the_job_exists(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        start = text.index("async function onUpdate()")
        end = text.index("async function onCancelUpdate()", start)
        handler = text[start:end]

        self.assertLess(handler.index("await startUpdate()"), handler.index("setProgressOpen(true)"))
        self.assertIn("loading={startingUpdate}", text)

    def test_update_ui_treats_missing_release_manifest_as_unpublished_and_links_windows_apps(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

        self.assertIn('info.remote_status === "not_published"', text)
        self.assertIn('window.location.href = "ms-settings:appsfeatures"', text)
        self.assertIn("打开 Windows 应用列表", text)
        self.assertIn("maint-uninstall", text)
        self.assertIn('"release_runtime_zip" | "none"', client)

    def test_frontend_regressions_keep_context_paths_history_and_typecheck_gate(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        update = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        history = (ROOT / "frontend" / "src" / "platform" / "HistoryView.tsx").read_text(encoding="utf-8")
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        netlist = (ROOT / "frontend" / "src" / "tools" / "NetlistComparePane.tsx").read_text(encoding="utf-8")
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

        self.assertIn("App as AntdApp", app)
        self.assertIn("<AntdApp>", app)
        self.assertIn("</AntdApp>", app)
        self.assertIn("App.useApp()", update)
        self.assertIn("App.useApp()", history)

        update_start = update.index("async function onUpdate()")
        notice_close = update.index("setNoticeOpen(false);", update_start)
        progress_open = update.index("setProgressOpen(true);", update_start)
        self.assertLess(notice_close, progress_open)

        self.assertIn('import { outputHref } from "../utils/outputHref"', history)
        self.assertIn("href={outputHref(name)}", history)
        self.assertIn('import { outputHref } from "../utils/outputHref"', wizard)
        self.assertIn("href={outputHref(p)}", wizard)

        self.assertIn('HISTORY_UPDATED_EVENT = "insta360_hw:history-updated"', client)
        self.assertIn("window.dispatchEvent(new Event(HISTORY_UPDATED_EVENT))", client)
        self.assertIn("HISTORY_UPDATED_EVENT", app)
        self.assertIn("window.addEventListener(HISTORY_UPDATED_EVENT", app)
        self.assertIn("window.removeEventListener(HISTORY_UPDATED_EVENT", app)
        self.assertIn("setHistoryRuns(await fetchHistory())", app)

        self.assertIn("useToolWorkspace", netlist)
        self.assertIn('"netlist_compare"', netlist)
        self.assertIn("setWorkspace({ filter, query, selectedKey, result })", netlist)
        self.assertIn("resetWorkspace()", netlist)

        self.assertEqual(package["scripts"].get("typecheck"), "tsc --noEmit")
        self.assertIn("npm run typecheck", package["scripts"].get("build", ""))

    def test_output_download_urls_encode_each_relative_path_segment(self) -> None:
        cases = [
            [r"C:\workspace\data\outputs\子目录 A\嵌套#层\报告 100%?.xlsx", "子目录 A/嵌套#层/报告 100%?.xlsx"],
            ["data/outputs/项目 #1/版本+50%/检查&确认?.csv", "项目 #1/版本+50%/检查&确认?.csv"],
        ]
        helper_path = ROOT / "frontend/src/utils/outputHref.ts"
        source = helper_path.read_text(encoding="utf-8")
        helper = re.search(r"export function outputHref\(path: string\): string \{(?P<body>[\s\S]+?)\n\}", source)
        self.assertIsNotNone(helper, str(helper_path))
        script = (
            f"function outputHref(path) {{{helper.group('body')}\n}}\n"
            f"const cases = {json.dumps(cases, ensure_ascii=False)};\n"
            "for (const [input, relative] of cases) {\n"
            "  const expected = `/outputs/${relative.split('/').map(encodeURIComponent).join('/')}`;\n"
            "  const actual = outputHref(input);\n"
            "  if (actual !== expected) {\n"
            "    console.error(JSON.stringify({ input, expected, actual }));\n"
            "    process.exit(1);\n"
            "  }\n"
            "}\n"
        )
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        for relative_path in [
            "frontend/src/components/ResultPanel.tsx",
            "frontend/src/platform/HistoryView.tsx",
            "frontend/src/tools/bomCompare/ExportPanel.tsx",
            "frontend/src/tools/BomProcessWizard.tsx",
            "frontend/src/tools/NetlistComparePane.tsx",
            "frontend/src/tools/SingleNetworkCheckPane.tsx",
            "frontend/src/tools/smtView/SmtViewPane.tsx",
        ]:
            consumer = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("utils/outputHref", consumer, relative_path)

    def test_frontend_build_reaches_shared_error_status_and_output_utilities(self) -> None:
        sources = {
            "api/errors": (ROOT / "frontend/src/api/errors.ts").read_text(encoding="utf-8"),
            "utils/statusText": (ROOT / "frontend/src/utils/statusText.ts").read_text(encoding="utf-8"),
            "utils/outputHref": (ROOT / "frontend/src/utils/outputHref.ts").read_text(encoding="utf-8"),
        }
        frontend_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "frontend/src").rglob("*.ts*")
        )

        self.assertIn("export function toUserMessage", sources["api/errors"])
        self.assertIn("export function riskStatusText", sources["utils/statusText"])
        self.assertIn("export function outputHref", sources["utils/outputHref"])
        for module in sources:
            self.assertIn(f'from "../{module}"', frontend_sources, module)

    def test_frontend_marks_backend_offline_when_health_check_fails(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        errors = (ROOT / "frontend" / "src" / "api" / "errors.ts").read_text(encoding="utf-8")

        self.assertIn("serviceOnline", app)
        self.assertIn("refreshRuntimeStatus", app)
        self.assertIn("window.setInterval", app)
        self.assertIn("服务离线", app)
        self.assertIn("重新连接", app)
        self.assertIn("toUserMessage", app)
        self.assertIn("后端服务已断开", errors)
        self.assertIn("requestJson", client)

    def test_reconnect_button_restarts_backend_via_local_protocol(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        handler = app.split("async function restartBackendAndReconnect()", 1)[1].split("useEffect(() =>", 1)[0]

        self.assertIn("restartBackendAndReconnect", app)
        self.assertIn("insta360-hw://reconnect", app)
        self.assertIn("serviceReconnecting", app)
        self.assertIn("pollBackendUntilReady", app)
        self.assertIn("refreshRuntimeStatus", app)
        # Reconnect must use a top-level window.location assignment. The earlier
        # hidden-iframe trick is blocked by Chrome 90+/Firefox for programmatic
        # navigation to unknown schemes without a user gesture.
        self.assertIn("window.location.href = RECONNECT_PROTOCOL_URL", app)
        self.assertNotIn('document.createElement("iframe")', app)
        self.assertIn("const alreadyReady = await refreshRuntimeStatus", handler)
        self.assertLess(handler.index("const alreadyReady"), handler.index("triggerReconnectProtocol()"))
        self.assertIn("if (alreadyReady)", handler)
        self.assertIn("正在重新连接本地服务，请稍候", app)
        self.assertNotIn("如新窗口未自动打开", app)
        self.assertIn("await refreshPlatformCatalog()", handler)

    def test_platform_page_removes_full_uninstall_flow(self) -> None:
        text = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.close()", text)
        self.assertNotIn("完整卸载", text)
        self.assertNotIn("DELETE", text)
        self.assertNotIn("setUninstallOpen", text)
        self.assertNotIn("fetchUninstallStatus", text)
        self.assertNotIn('runUninstall("full")', text)
        self.assertNotIn("正在卸载平台", text)
        self.assertNotIn("卸载完成", text)
        self.assertIn("请通过 Windows 设置或 Insta360_HW_Setup.exe 卸载平台", text)

    def test_build_script_restores_locked_dependencies_only_when_needed(self) -> None:
        text = (ROOT / "scripts" / "build_frontend.ps1").read_text(encoding="utf-8")

        self.assertIn("node_modules", text)
        self.assertIn("ForceDependencyRestore", text)
        self.assertIn("npm ci", text)
        self.assertIn("npm ci failed", text)
        self.assertNotIn("npm install", text)
        self.assertIn("npm run build", text)
        self.assertIn("frontend build failed", text)
        self.assertIn("app\\frontend", text)
        self.assertRegex(text, r"Copy-Item[\s\S]+dist")
        self.assertIn("waiting.html", text)
        self.assertIn("[System.IO.File]::ReadAllBytes($Waiting)", text)
        self.assertIn("[System.IO.File]::WriteAllBytes($WaitingTarget, $WaitingBytes)", text)
        self.assertLess(
            text.index("[System.IO.File]::ReadAllBytes($Waiting)"),
            text.index("Remove-Item -LiteralPath $Target"),
        )

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
        self.assertNotIn(BRAND_NAME_LEGACY, waiting)
        self.assertNotIn("姝", waiting)
        self.assertNotIn("鈿", waiting)

    def test_platform_branding_uses_final_chinese_name(self) -> None:
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        zh = (ROOT / "frontend" / "src" / "i18n" / "zhCN.ts").read_text(encoding="utf-8")
        config = (ROOT / "config" / "default.json").read_text(encoding="utf-8")

        self.assertIn("Insta360硬件提效平台", index)
        self.assertIn('appTitle: "Insta360硬件提效平台"', zh)
        self.assertIn('"app_name": "Insta360硬件提效平台"', config)
        self.assertNotIn(BRAND_NAME_LEGACY, zh)

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
        self.assertIn("toolsResult.value.some((tool) => tool.id === requested)", app)
        self.assertIn("setActive(requested)", app)
        self.assertIn("URLSearchParams", wizard)
        self.assertIn('params.get("source")', wizard)
        self.assertIn('params.get("name")', wizard)
        self.assertIn("source_bom: sp", wizard)
        self.assertIn('runTool("bom_process"', wizard)

    def test_bom_conflict_review_supports_user_selected_variants(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        choices = (ROOT / "frontend" / "src" / "tools" / "bomConflictChoices.ts").read_text(encoding="utf-8")

        self.assertIn("merge_conflicts", wizard)
        self.assertIn("conflict_choices", wizard)
        self.assertIn('pres?.reason === "part_property_conflicts"', wizard)
        self.assertIn("conflicts.length", wizard)
        self.assertIn("onApply", wizard)
        self.assertIn("conflictChoices", wizard)
        for action in ("select_variant", "split_refs", "move_non_smt", "return_to_capture"):
            self.assertIn(action, choices)
            self.assertIn(action, wizard)
        self.assertIn("conflictChoiceComplete", wizard)

    def test_bom_conflict_review_supports_recommended_merge_without_manual_choices(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("applyRecommendedMerge", wizard)
        self.assertIn("onRecommendedMerge", wizard)
        self.assertIn("一键采用安全推荐", wizard)
        self.assertIn("一键合并为第一候选", wizard)
        self.assertIn("buildRecommendedConflictChoices", wizard)
        self.assertIn("conflict_choices: choices", wizard)
        self.assertIn("剩余 ${unresolved.length} 项需要人工处理", wizard)

    def test_bom_process_wizard_uses_unified_placement_review_for_shields(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        placement = (ROOT / "frontend" / "src" / "tools" / "PlacementReview.tsx").read_text(encoding="utf-8")

        self.assertIn('pres.reason === "placement_review"', wizard)
        self.assertIn("placement_resolutions", wizard)
        self.assertNotIn("confirm_shields", wizard)
        self.assertIn('{ label: "屏蔽支架", value: "bracket" }', placement)
        self.assertIn('{ label: "屏蔽罩", value: "cover" }', placement)
        self.assertIn('{ label: "其他", value: "other" }', placement)
        self.assertIn("value={resolution.subtype}", placement)
        self.assertNotIn("value={resolution.subtype || undefined}", placement)
        self.assertIn("支架自动进入贴片区；屏蔽罩自动作为范围排除", placement)
        self.assertIn("按审查结果继续", placement)

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
        placement = (ROOT / "frontend" / "src" / "tools" / "PlacementReview.tsx").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("conflict-main", wizard)
        self.assertIn("conflict-workbench", wizard)
        self.assertIn("activeConflictCode", wizard)
        self.assertIn("conflict-index-list", wizard)
        self.assertIn("renderFullRefs", wizard)
        self.assertIn(".conflict-workbench", css)
        self.assertIn(".conflict-index-list", css)
        self.assertIn("placement-dual-workbench", placement)
        self.assertIn("placement-evidence-pane", placement)
        self.assertIn("placement-zone-smt", css)
        self.assertIn("placement-zone-non_smt", css)
        self.assertIn("placement-raw-grid", css)
        self.assertIn("placement-edit-grid", css)
        self.assertIn("grid-template-columns", css)

    def test_bom_wizard_does_not_blank_when_risk_step_has_no_process_file(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")

        self.assertIn("process_file", wizard)
        self.assertIn("bom_risk_check", wizard)
        self.assertIn('setRres({ status: "error"', wizard)

    def test_bom_risk_review_is_split_into_tabs(self) -> None:
        wizard = (ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx").read_text(encoding="utf-8")
        findings = (ROOT / "frontend" / "src" / "tools" / "bomRisk" / "RiskFindings.tsx").read_text(encoding="utf-8")

        self.assertIn('import { RiskFindings } from "./bomRisk/RiskFindings"', wizard)
        self.assertIn("<RiskFindings", wizard)
        self.assertIn("<Tabs", findings)
        self.assertIn('key: "findings"', findings)
        self.assertIn('key: "grades"', findings)
        self.assertIn('key: "types"', findings)
        self.assertIn('key: "substitutes"', findings)
        self.assertIn('key: "categories"', findings)
        self.assertIn('key: "versions"', findings)
        self.assertIn('key: "outputs"', findings)

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
        self.assertIn("<RiskFindings", wizard)
        self.assertIn("preview={<BomPreviewTable", wizard)
        self.assertIn("<BomPreviewTable preview={pres?.preview} />", wizard)

    def test_bom_compare_uses_dedicated_horizontal_workbench(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "BomComparePane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('tool.id === "bom_compare"', legacy)
        self.assertIn("<BomComparePane", legacy)
        self.assertIn("bom-compare-workbench", pane)
        self.assertIn("bom-source-band", pane)
        self.assertIn("bom-result-verdict", pane)
        self.assertIn("bom-semantic-tabs", pane)
        self.assertIn("<CompareOverview", pane)
        self.assertIn("<PlacementDiff", pane)
        self.assertIn("<SubstituteDiff", pane)
        self.assertIn("<MetadataDiff", pane)
        self.assertIn("<ExportPanel", pane)
        self.assertIn(".bom-source-band", css)
        self.assertIn(".bom-result-verdict", css)
        self.assertIn(".bom-review-route", css)
        self.assertIn(
            "grid-template-columns: minmax(300px, 1fr) 38px minmax(300px, 1fr) minmax(190px, 230px)",
            css,
        )
        self.assertIn(".bom-source-inspection-grid", css)

    def test_bom_compare_can_use_wide_desktop_space(self) -> None:
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        app_content = re.search(r"\.app-content\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(app_content)
        self.assertNotIn("max-width: 1280px", app_content.group("body"))
        self.assertIn("width: 100%", app_content.group("body"))

        workbench = re.search(r"\.bom-compare-workbench\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(workbench)
        self.assertIn("width: 100%", workbench.group("body"))
        self.assertNotIn("1480px", workbench.group("body"))

        source_band = re.search(r"\.bom-source-band\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(source_band)
        self.assertIn(
            "minmax(300px, 1fr) 38px minmax(300px, 1fr) minmax(190px, 230px)",
            source_band.group("body"),
        )

        inspection = re.search(r"\.bom-source-inspection-grid\s*\{(?P<body>[^}]+)\}", css)
        self.assertIsNotNone(inspection)
        self.assertIn("repeat(2, minmax(0, 1fr))", inspection.group("body"))

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
        self.assertIn("directory", pane)
        self.assertNotIn('directory="true"', pane)
        self.assertNotIn("webkitdirectory", pane)
        self.assertIn("Allegro", pane)
        self.assertIn("pstxnet.dat", pane)
        self.assertIn(".netlist-shell", css)
        self.assertIn(".netlist-inspector", css)

    def test_smt_package_check_is_merged_into_the_smt_view(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "smtView" / "SmtViewPane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "tools" / "smtView" / "smtView.module.css").read_text(encoding="utf-8")

        self.assertNotIn('tool.id === "smt_package_check"', legacy)
        self.assertNotIn("SmtPackageCheckPane", legacy)
        self.assertIn("封装一致性", pane)
        self.assertIn("package_report_outputs", pane)
        self.assertIn("下载封装报告", pane)
        self.assertIn("已处理成品 BOM", pane)
        self.assertIn("XY 有而成品 BOM 没有的位号直接判为 NC", pane)
        self.assertIn("webkitdirectory", pane)
        self.assertIn("pstxprt.dat", pane)
        self.assertIn("选择网表目录", pane)
        self.assertIn(".workbench", css)
        self.assertIn(".detailPane", css)
        self.assertIn(".drawingImage", css)

    def test_single_network_check_uses_dedicated_review_workbench(self) -> None:
        legacy = (ROOT / "frontend" / "src" / "tools" / "LegacyToolPane.tsx").read_text(encoding="utf-8")
        pane_path = ROOT / "frontend" / "src" / "tools" / "SingleNetworkCheckPane.tsx"
        self.assertTrue(pane_path.exists())
        pane = pane_path.read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('tool.id === "single_network_check"', legacy)
        self.assertIn("<SingleNetworkCheckPane", legacy)
        self.assertIn("single-network-workbench", pane)
        self.assertIn("single_network_review", pane)
        self.assertIn("focus_items", pane)
        self.assertIn("重点复核", pane)
        self.assertIn("NC 网络", pane)
        self.assertIn("单一位号网络", pane)
        self.assertIn("机械/安装孔", pane)
        self.assertIn("测试点/工艺", pane)
        self.assertIn("电源/地", pane)
        self.assertIn("directory", pane)
        self.assertNotIn('directory="true"', pane)
        self.assertNotIn("webkitdirectory", pane)
        self.assertIn("pstxnet.dat", pane)
        self.assertIn("下载单网络检查报告", pane)
        self.assertIn(".single-network-shell", css)
        self.assertIn(".single-network-inspector", css)


if __name__ == "__main__":
    unittest.main()
