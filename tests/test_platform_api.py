from __future__ import annotations

import json
import shutil
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen

from app.backend import history
from app.backend.suite_app import create_server


ROOT = Path(__file__).resolve().parents[1]


def _make_temp_root() -> Path:
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "app", root / "app")
    (root / "plugins" / "user" / "scripts").mkdir(parents=True)
    return root


class PlatformApiTests(unittest.TestCase):
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

    def test_user_plugin_menu_endpoint_updates_manifest_without_redeploy_for_dry_run(self) -> None:
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
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["plugin"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])
            self.assertTrue(json.loads(manifest.read_text(encoding="utf-8"))["show_in_cadence"])
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
                    headers={"Content-Type": "application/json"},
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
                    headers={"Content-Type": "application/json"},
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
        self.assertEqual(payload["tools"], 6)
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
                delete_request = Request(f"http://{host}:{port}/api/history/{run_id}", method="DELETE")
                with urlopen(delete_request, timeout=5) as response:
                    deleted = json.loads(response.read().decode("utf-8"))
                clear_request = Request(f"http://{host}:{port}/api/history", method="DELETE")
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
                request = Request(f"http://{host}:{port}/api/history/../foo", method="DELETE")
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
                    headers={"Content-Type": "application/json"},
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
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(safe_request, timeout=5) as response:
                    self.assertEqual(response.headers.get("Content-Type"), "application/zip")

                for unsafe in ["../demo.txt", "C:/Windows/win.ini", r"\\server\share\demo.txt"]:
                    body = json.dumps({"name": "demo", "files": [unsafe]}).encode("utf-8")
                    request = Request(
                        f"http://{host}:{port}/api/package",
                        data=body,
                        method="POST",
                        headers={"Content-Type": "application/json"},
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
                    headers={"Content-Type": "application/json"},
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
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")

        upload_impl = text.split("def _handle_upload", 1)[1].split("def _handle_package", 1)[0]
        self.assertIn("NamedTemporaryFile", upload_impl)
        self.assertIn("_copy_exact_request_body", upload_impl)
        self.assertIn("_parse_multipart_files_from_disk", upload_impl)
        self.assertNotIn("body = self.rfile.read(length)", upload_impl)
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
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
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
                    headers={"Content-Type": "application/json"},
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
                    headers={"Content-Type": "application/json"},
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
                    headers={"Content-Type": "application/json"},
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

            saved = json.loads((root / "config" / "capabilities.json").read_text(encoding="utf-8"))
            enabled = [item for item in saved["capabilities"] if item["id"] == "cadence_nc_toggle"][0]
            self.assertTrue(enabled["show_in_cadence"])
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
                    headers={"Content-Type": "application/json"},
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
            shutil.copytree(ROOT / "cadence", root / "cadence")
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
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["capability"]["id"], "cadence_net_name_replace")
            self.assertEqual(payload["capability"]["module"], "cadence/modules/enhanced_core_tools.tcl")
            self.assertTrue(payload["capability"]["show_in_cadence"])
            self.assertFalse(payload["redeployed"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
