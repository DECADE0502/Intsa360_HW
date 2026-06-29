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
