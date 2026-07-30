from __future__ import annotations

import io
import json
import shutil
import threading
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen
from unittest.mock import patch

from app.backend import assets
from app.backend import history
from app.backend import update_api
from app.backend.suite_app import _cadence_hot_reload_command, _parse_cadence_loader_paths, create_server


ROOT = Path(__file__).resolve().parents[1]


def _make_temp_root() -> Path:
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "app", root / "app")
    shutil.copytree(ROOT / "cadence", root / "cadence")
    (root / "plugins" / "user" / "scripts").mkdir(parents=True)
    return root


def _mutation_headers(server, content_type: str | None = None) -> dict[str, str]:
    headers = {"X-Insta360-Session": server.session_token}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


class PlatformApiTests(unittest.TestCase):
    def test_cadence_hot_reload_uses_the_deployed_loader_path(self) -> None:
        output = (
            "noise\n"
            "__HWAGENT_CADENCE_LOADER__ D:\\Cadence Data\\cdssetup\\OrCAD_Capture\\tclscripts\\capAutoLoad\\iac_bom_tool.tcl\n"
        )

        installed = _parse_cadence_loader_paths(output)
        command = _cadence_hot_reload_command(installed)

        self.assertEqual(len(installed), 1)
        self.assertEqual(
            command,
            "source {D:/Cadence Data/cdssetup/OrCAD_Capture/tclscripts/capAutoLoad/iac_bom_tool.tcl}",
        )
        self.assertNotIn("$env(HOME)", command)

    def test_cadence_install_endpoint_reports_missing_environment_as_skipped(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            request = Request(
                f"http://{host}:{port}/api/cadence/install",
                data=b"{}",
                headers=_mutation_headers(server, "application/json"),
                method="POST",
            )
            output = "__HWAGENT_CADENCE_NONE__ 未检测到 Cadence 环境，已跳过菜单部署\n"
            with patch(
                "app.backend.api.routers.plugins.redeploy_cadence_loader",
                return_value=(True, [], output),
            ):
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(payload["installed"], [])
        self.assertEqual(payload["hot_reload_command"], "")
        self.assertIn("未检测到 Cadence", payload["message"])
        self.assertIn("已跳过", payload["message"])

    def test_capabilities_endpoint_returns_platform_and_scripts(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/api/capabilities", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(payload["platform"]["name"], "Insta360硬件提效平台")
        self.assertTrue(any(item["type"] == "cadence_tcl" for item in payload["capabilities"]))

    def test_plugins_endpoint_returns_system_platform_and_user_groups(self) -> None:
        root = _make_temp_root()
        try:
            official_dir = root / "fake-cadence" / "capAutoLoad"
            official_dir.mkdir(parents=True)
            (official_dir / "capAutoPDFExport.tcl").write_text("# official\n", encoding="utf-8")
            (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "plugins" / "user" / "demo.json").write_text(
                json.dumps(
                    {
                        "id": "user.demo",
                        "name": "Demo Script",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                        "show_in_platform": True,
                        "show_in_cadence": False,
                    }
                ),
                encoding="utf-8",
            )
            from app.backend import plugins as plugin_registry

            original_dirs = plugin_registry.DEFAULT_CADENCE_SYSTEM_SCRIPT_DIRS
            plugin_registry.DEFAULT_CADENCE_SYSTEM_SCRIPT_DIRS = [official_dir]
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/api/plugins", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                plugin_registry.DEFAULT_CADENCE_SYSTEM_SCRIPT_DIRS = original_dirs

            self.assertEqual(payload["platform"]["cadence_menu"], "insta360_HW")
            self.assertEqual(payload["groups"]["system"][0]["id"], "cadence_official.capAutoPDFExport")
            self.assertTrue(payload["groups"]["system"][0]["readonly"])
            self.assertTrue(payload["groups"]["platform"][0]["manageable"])
            self.assertTrue(any(item["id"] == "cadence_nc_toggle" for item in payload["groups"]["platform"]))
            self.assertFalse(payload["groups"]["user"][0]["readonly"])
            self.assertEqual(payload["groups"]["user"][0]["id"], "user.demo")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_plugins_endpoint_reports_bad_manifest_without_500(self) -> None:
        root = _make_temp_root()
        try:
            (root / "plugins" / "user" / "bad.json").write_text("{bad json", encoding="utf-8")
            (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "plugins" / "user" / "good.json").write_text(
                json.dumps(
                    {
                        "id": "user.good",
                        "name": "Good Script",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                    }
                ),
                encoding="utf-8",
            )
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/api/plugins", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["groups"]["user"][0]["id"], "user.good")
            self.assertEqual(payload["warnings"][0]["source"], "user")
            self.assertIn("bad.json", payload["warnings"][0]["path"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_plugin_menu_endpoint_updates_shared_state_without_redeploy_for_dry_run(self) -> None:
        root = _make_temp_root()
        try:
            (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            manifest = root / "plugins" / "user" / "demo.json"
            manifest.write_text(
                json.dumps(
                    {
                        "id": "user.demo",
                        "name": "Demo Script",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                        "show_in_platform": True,
                        "show_in_cadence": False,
                    }
                ),
                encoding="utf-8",
            )
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/plugins/user.demo/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["plugin"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])
            self.assertFalse(json.loads(manifest.read_text(encoding="utf-8"))["show_in_cadence"])
            state = json.loads((root / "config" / "plugin_state.json").read_text(encoding="utf-8"))
            self.assertTrue(state["plugins"]["user.demo"]["enabled"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_plugin_menu_endpoint_survives_bad_user_manifest(self) -> None:
        root = _make_temp_root()
        try:
            (root / "plugins" / "user" / "bad.json").write_text("{bad json", encoding="utf-8")
            (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "plugins" / "user" / "demo.json").write_text(
                json.dumps(
                    {
                        "id": "user.demo",
                        "name": "Demo Script",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                    }
                ),
                encoding="utf-8",
            )
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/plugins/user.demo/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["plugin"]["show_in_cadence"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_plugin_menu_endpoint_can_update_platform_scripts(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/plugins/cadence_nc_toggle/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["plugin"]["source"], "platform")
            self.assertTrue(payload["plugin"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_platform_status_endpoint_returns_runtime_summary(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/api/platform/status", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["platform"], "Insta360硬件提效平台")
        self.assertEqual(payload["tools"], 7)
        self.assertEqual(payload["cadence_scripts"], 19)
        self.assertEqual(payload["enableable_scripts"], 19)
        self.assertEqual(payload["enabled_scripts"], 0)
        self.assertEqual(payload["pending_scripts"], 0)
        self.assertEqual(Path(payload["root"]).resolve(), ROOT.resolve())

    def test_frontend_static_files_are_not_cached(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/", timeout=5) as response:
                response.read()
                cache_control = response.headers.get("Cache-Control")
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(cache_control, "no-store")

    def test_history_endpoints_list_detail_delete_and_clear_runs(self) -> None:
        root = _make_temp_root()
        try:
            run_id = history.record(
                root,
                "bom_process",
                "BOM 处理",
                {"source_bom": str(root / "demo.xlsx")},
                {"status": "ok", "summary": {"records": 2}, "outputs": [str(root / "data" / "outputs" / "demo.xlsx")]},
            )
            self.assertIsNotNone(run_id)
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/api/history", timeout=5) as response:
                    listing = json.loads(response.read().decode("utf-8"))
                with urlopen(f"http://{host}:{port}/api/history/{run_id}", timeout=5) as response:
                    detail = json.loads(response.read().decode("utf-8"))
                delete_request = Request(
                    f"http://{host}:{port}/api/history/{run_id}",
                    method="DELETE",
                    headers=_mutation_headers(server),
                )
                with urlopen(delete_request, timeout=5) as response:
                    deleted = json.loads(response.read().decode("utf-8"))
                clear_request = Request(
                    f"http://{host}:{port}/api/history",
                    method="DELETE",
                    headers=_mutation_headers(server),
                )
                with urlopen(clear_request, timeout=5) as response:
                    cleared = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(listing["runs"][0]["id"], run_id)
            self.assertEqual(detail["_meta"]["id"], run_id)
            self.assertEqual(deleted["status"], "ok")
            self.assertEqual(cleared["status"], "ok")
            self.assertEqual(history.list_runs(root), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_delete_history_rejects_path_traversal_run_id(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                request = Request(
                    f"http://{host}:{port}/api/history/../foo",
                    method="DELETE",
                    headers=_mutation_headers(server),
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(ctx.exception.code, 400)
            payload = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(payload["status"], "error")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_history_index_rebuilds_from_runs_when_corrupt(self) -> None:
        root = _make_temp_root()
        try:
            run_id = history.record(
                root,
                "bom_process",
                "BOM 处理",
                {"source_bom": str(root / "source.xlsx")},
                {"status": "ok", "summary": {"records": 1}, "outputs": []},
            )
            self.assertIsNotNone(run_id)
            index_path = root / "data" / "history" / "index.json"
            index_path.write_text("{bad json", encoding="utf-8")

            runs = history.list_runs(root)

            self.assertEqual(runs[0]["id"], run_id)
            repaired = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired[0]["id"], run_id)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_assets_endpoint_exposes_reusable_processed_boms_from_history(self) -> None:
        root = _make_temp_root()
        try:
            output_dir = root / "data" / "outputs" / "bom"
            output_dir.mkdir(parents=True)
            plm = output_dir / "BOARD_A_20260630_PLM_BOM.xlsx"
            oa = output_dir / "BOARD_A_20260630_OA_BOM.xlsx"
            nc = output_dir / "BOARD_A_20260630_NC未贴汇总.xlsx"
            plm.write_bytes(b"plm")
            oa.write_bytes(b"oa")
            nc.write_bytes(b"nc")
            run_id = history.record(
                root,
                "bom_process",
                "BOM 处理",
                {"source_bom": str(root / "source.xlsx")},
                {
                    "status": "ok",
                    "summary": {"name": "BOARD_A"},
                    "outputs": [str(plm), str(oa), str(nc)],
                    "process_file": str(plm),
                },
            )
            self.assertIsNotNone(run_id)

            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/api/assets", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            processed = payload["groups"]["processed_bom"]
            self.assertEqual([item["name"] for item in processed], [plm.name, oa.name])
            self.assertEqual(processed[0]["path"], str(plm))
            self.assertEqual(processed[0]["run_id"], run_id)
            self.assertEqual(processed[0]["source_tool"], "bom_process")
            self.assertEqual(processed[0]["format"], "PLM")
            self.assertEqual(payload["summary"]["processed_bom"], 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_history_keeps_output_paths_relative_to_outputs_root(self) -> None:
        root = _make_temp_root()
        try:
            output = root / "data" / "outputs" / "bom" / "BOARD_A_PLM_BOM.xlsx"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"plm")

            run_id = history.record(
                root,
                "bom_process",
                "BOM processing",
                {},
                {"status": "ok", "outputs": [str(output)]},
            )

            self.assertIsNotNone(run_id)
            self.assertEqual(history.list_runs(root)[0]["outputs"], ["bom/BOARD_A_PLM_BOM.xlsx"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_assets_use_recorded_subdirectories_for_duplicate_output_names(self) -> None:
        root = _make_temp_root()
        try:
            first = root / "data" / "outputs" / "alpha" / "BOARD_PLM_BOM.xlsx"
            second = root / "data" / "outputs" / "beta" / "BOARD_PLM_BOM.xlsx"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            first_run = history.record(root, "bom_process", "BOM processing", {}, {"status": "ok", "outputs": [str(first)]})
            second_run = history.record(root, "bom_process", "BOM processing", {}, {"status": "ok", "outputs": [str(second)]})

            processed = assets.list_assets(root)["groups"]["processed_bom"]
            by_path = {item["path"]: item for item in processed}

            self.assertEqual(set(by_path), {str(first), str(second)})
            self.assertEqual(by_path[str(first)]["run_id"], first_run)
            self.assertEqual(by_path[str(second)]["run_id"], second_run)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_assets_accept_legacy_basename_history_output(self) -> None:
        root = _make_temp_root()
        try:
            output = root / "data" / "outputs" / "LEGACY_PLM_BOM.xlsx"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"legacy")
            index = root / "data" / "history" / "index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                json.dumps(
                    [{"id": "legacy", "outputs": [output.name], "tool": "bom_process", "time": "2026-01-01 00:00:00"}]
                ),
                encoding="utf-8",
            )

            processed = assets.list_assets(root)["groups"]["processed_bom"]

            self.assertEqual([item["path"] for item in processed], [str(output)])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_assets_accept_legacy_basename_for_unique_nested_output(self) -> None:
        root = _make_temp_root()
        try:
            output = root / "data" / "outputs" / "bom" / "LEGACY_NESTED_PLM_BOM.xlsx"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"legacy")
            index = root / "data" / "history" / "index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                json.dumps(
                    [{"id": "legacy", "outputs": [output.name], "tool": "bom_process", "time": "2026-01-01 00:00:00"}]
                ),
                encoding="utf-8",
            )

            processed = assets.list_assets(root)["groups"]["processed_bom"]

            self.assertEqual([item["path"] for item in processed], [str(output)])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_assets_do_not_choose_ambiguous_legacy_nested_basename(self) -> None:
        root = _make_temp_root()
        try:
            first = root / "data" / "outputs" / "bom" / "LEGACY_DUPLICATE_PLM_BOM.xlsx"
            second = root / "data" / "outputs" / "risk" / "LEGACY_DUPLICATE_PLM_BOM.xlsx"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            index = root / "data" / "history" / "index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                json.dumps(
                    [{"id": "legacy", "outputs": [first.name], "tool": "bom_process", "time": "2026-01-01 00:00:00"}]
                ),
                encoding="utf-8",
            )

            processed = assets.list_assets(root)["groups"]["processed_bom"]

            self.assertEqual(processed, [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_outputs_and_package_endpoints_use_server_root(self) -> None:
        root = _make_temp_root()
        try:
            output_dir = root / "data" / "outputs"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "demo.txt"
            output_file.write_text("server-root-output", encoding="utf-8")

            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/outputs/demo.txt", timeout=5) as response:
                    downloaded = response.read().decode("utf-8")

                body = json.dumps({"name": "demo", "files": [str(output_file)]}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/package",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    package_type = response.headers.get("Content-Type")
                    package_body = response.read()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(downloaded, "server-root-output")
            self.assertEqual(package_type, "application/zip")
            self.assertGreater(len(package_body), 20)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_installed_tool_output_can_be_packaged_from_external_state_root(self) -> None:
        root = _make_temp_root()
        state = Path(tempfile.mkdtemp()).resolve()
        try:
            (root / "install_manifest.json").write_text(
                json.dumps({"schema": 3, "product": "Insta360_HW", "layout": "runtime-v3"}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False):
                from app.backend.tools.common import _output_dir

                output_file = _output_dir({}, root, "bom") / "installed-output.txt"
                output_file.write_text("state-root-output", encoding="utf-8")
                server = create_server(root, port=0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    host, port = server.server_address
                    body = json.dumps({"name": "demo", "files": [str(output_file)]}).encode("utf-8")
                    request = Request(
                        f"http://{host}:{port}/api/package",
                        data=body,
                        method="POST",
                        headers=_mutation_headers(server, "application/json"),
                    )
                    with urlopen(request, timeout=5) as response:
                        archive = response.read()
                finally:
                    server.shutdown()
                    server.server_close()

            self.assertTrue(output_file.is_relative_to(state / "data" / "outputs"))
            self.assertFalse((root / "data").exists())
            with zipfile.ZipFile(io.BytesIO(archive)) as packaged:
                self.assertEqual(packaged.namelist(), ["bom/installed-output.txt"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_output_download_and_package_preserve_subdirectories(self) -> None:
        root = _make_temp_root()
        try:
            output_file = root / "data" / "outputs" / "bom" / "review" / "demo.txt"
            output_file.parent.mkdir(parents=True)
            output_file.write_text("server-root-output", encoding="utf-8")

            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/outputs/bom/review/demo.txt", timeout=5) as response:
                    downloaded = response.read().decode("utf-8")

                body = json.dumps({"name": "demo", "files": ["bom/review/demo.txt"]}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/package",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    archive = response.read()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(downloaded, "server-root-output")
            with zipfile.ZipFile(io.BytesIO(archive)) as packaged:
                self.assertEqual(packaged.namelist(), ["bom/review/demo.txt"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_package_endpoint_rejects_paths_outside_outputs(self) -> None:
        root = _make_temp_root()
        try:
            output_dir = root / "data" / "outputs"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "demo.txt"
            output_file.write_text("server-root-output", encoding="utf-8")

            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                safe_body = json.dumps({"name": "demo", "files": [str(output_file)]}).encode("utf-8")
                safe_request = Request(
                    f"http://{host}:{port}/api/package",
                    data=safe_body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(safe_request, timeout=5) as response:
                    self.assertEqual(response.headers.get("Content-Type"), "application/zip")

                for unsafe in ["../demo.txt", "C:/Windows/win.ini", r"\\server\share\demo.txt"]:
                    body = json.dumps({"name": "demo", "files": [unsafe]}).encode("utf-8")
                    request = Request(
                        f"http://{host}:{port}/api/package",
                        data=body,
                        method="POST",
                        headers=_mutation_headers(server, "application/json"),
                    )
                    with self.subTest(unsafe=unsafe):
                        with self.assertRaises(HTTPError) as ctx:
                            urlopen(request, timeout=5)
                        self.assertEqual(ctx.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_tool_run_rejects_output_dir_outside_outputs(self) -> None:
        root = _make_temp_root()
        try:
            outside = root / "outside"
            outside.mkdir()
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"bom1": str(root / "missing1.xlsx"), "bom2": str(root / "missing2.xlsx"), "output_dir": str(outside)}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/tools/bom_compare/run",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(ctx.exception.code, 400)
            payload = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error_kind"], "bad_output_dir")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_upload_large_body_does_not_load_into_memory(self) -> None:
        router_text = (ROOT / "app" / "backend" / "api" / "routers" / "files.py").read_text(encoding="utf-8")
        stream_text = (ROOT / "app" / "backend" / "api" / "uploads.py").read_text(encoding="utf-8")

        upload_impl = router_text.split("async def _upload_files", 1)[1].split(
            '@api_router.post("/upload")',
            1,
        )[0]
        route_impl = router_text.split("async def upload_files", 1)[1].split(
            '@api_router.post("/upload/tree")',
            1,
        )[0]
        self.assertIn("NamedTemporaryFile", upload_impl)
        self.assertIn("stream_request_to_disk", upload_impl)
        self.assertIn("parse_multipart_files_from_disk", upload_impl)
        self.assertIn("return await _upload_files(", route_impl)
        self.assertIn("async for chunk in request.stream()", stream_text)
        self.assertIn("file_limit", stream_text)
        self.assertNotIn("await request.body()", upload_impl)
        self.assertNotIn("read_bytes()", upload_impl)

    def test_upload_multipart_stream_parser_saves_files(self) -> None:
        root = _make_temp_root()
        try:
            boundary = "----hwagent-test-boundary"
            body = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="demo.txt"\r\n'
                "Content-Type: text/plain\r\n\r\n"
                "hello upload\r\n"
                f"--{boundary}--\r\n"
            ).encode("utf-8")
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                request = Request(
                    f"http://{host}:{port}/api/upload",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, f"multipart/form-data; boundary={boundary}"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            saved = Path(payload["files"][0]["path"])
            self.assertEqual(saved.name, "demo.txt")
            self.assertEqual(saved.read_text(encoding="utf-8"), "hello upload")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_run_tool_returns_400_for_bad_zip(self) -> None:
        root = _make_temp_root()
        try:
            bad = root / "bad.xlsx"
            bad.write_bytes(b"not a zip workbook")
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"bom1": str(bad), "bom2": str(bad)}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/tools/bom_compare/run",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(ctx.exception.code, 400)
            payload = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(payload["status"], "error")
            self.assertIn("user_message", payload)
            self.assertIn("error_kind", payload)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_run_tool_returns_400_for_invalid_xlsx(self) -> None:
        root = _make_temp_root()
        try:
            bad = root / "bad.txt"
            bad.write_text("not an excel file", encoding="utf-8")
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"bom1": str(bad), "bom2": str(bad)}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/tools/bom_compare/run",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(ctx.exception.code, 400)
            payload = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(payload["status"], "error")
            self.assertIn("user_message", payload)
            self.assertIn("error_kind", payload)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cadence_script_menu_endpoint_updates_registry_without_redeploy_for_dry_run(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/capabilities/cadence_nc_toggle/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["capability"]["id"], "cadence_nc_toggle")
            self.assertTrue(payload["capability"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])

            overrides = json.loads((root / "config" / "capability_overrides.json").read_text(encoding="utf-8"))
            self.assertTrue(overrides["cadence_nc_toggle"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cadence_script_menu_endpoint_rejects_web_tools(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/capabilities/bom_process/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(ctx.exception.code, 400)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cadence_script_menu_endpoint_can_enable_split_high_risk_scripts(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                body = json.dumps({"show_in_cadence": True, "redeploy": False}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/capabilities/cadence_net_name_replace/cadence-menu",
                    data=body,
                    method="POST",
                    headers=_mutation_headers(server, "application/json"),
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["capability"]["id"], "cadence_net_name_replace")
            self.assertEqual(payload["capability"]["module"], "cadence/entries/cadence_net_name_replace.tcl")
            self.assertEqual(
                payload["capability"]["implementation_module"],
                "cadence/modules/enhanced_core_tools.tcl",
            )
            self.assertTrue(payload["capability"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


    def test_collect_diagnostic_report_covers_all_required_sections(self) -> None:
        root = _make_temp_root()
        try:
            # Give the temp root a UPDATE_NOTICE.json so the integrity section
            # has a real target to parse; the invalid sha256 length is verified
            # to prove the diagnostic actually inspects the field.
            (root / "UPDATE_NOTICE.json").write_text(
                json.dumps(
                    {
                        "version": "9.9.9",
                        "revision": "deadbeef",
                        "assets": [
                            {
                                "kind": "release_zip",
                                "url": "https://example.com/x.zip",
                                "sha256": "too-short",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = update_api.collect_diagnostic_report(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        required_sections = [
            "## Python Runtime",
            "## Launcher VersionInfo",
            "## UPDATE_NOTICE.json Integrity",
            "## GitHub Reachability",
            "## Cadence Home",
            "## Port 8765",
            "## Filesystem Permissions",
            "## Recent launcher.log",
        ]
        for section in required_sections:
            self.assertIn(section, report, f"missing section: {section}")
        # Verify the notice was actually parsed (sha256 length is shown).
        self.assertIn("sha256_len=9", report)
        self.assertIn("INVALID", report)
        # Report should be non-trivial and end with the sentinel.
        self.assertGreater(len(report), 500)
        self.assertIn("=== End of Report ===", report)

    def test_diagnostic_report_is_populated_without_a_remote_update_request(self) -> None:
        root = _make_temp_root()
        try:
            with patch("app.backend.lifecycle_update.urlopen", side_effect=AssertionError("diagnostics must stay offline")):
                report = update_api.collect_diagnostic_report(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertIn("## GitHub Reachability", report)
        self.assertIn("not probed", report)
        self.assertIn("## Filesystem Permissions", report)

    def test_diagnostic_report_endpoint_returns_populated_text(self) -> None:
        root = _make_temp_root()
        try:
            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urlopen(f"http://{host}:{port}/api/diagnostic/report", timeout=15) as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers.get("Content-Type", "")
                    disposition = response.headers.get("Content-Disposition", "")
            finally:
                server.shutdown()
                server.server_close()

            self.assertIn("text/plain", content_type)
            self.assertIn("attachment", disposition)
            self.assertIn("insta360_hw_diagnostic_", disposition)
            for section in [
                "Python Runtime",
                "Launcher VersionInfo",
                "UPDATE_NOTICE.json",
                "GitHub Reachability",
                "Cadence Home",
                "Port 8765",
                "Filesystem Permissions",
                "Recent launcher.log",
            ]:
                self.assertIn(section, body, f"missing section: {section}")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
