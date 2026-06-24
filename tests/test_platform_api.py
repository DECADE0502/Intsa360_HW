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

from app.backend.suite_app import create_server


ROOT = Path(__file__).resolve().parents[1]


def _make_temp_root() -> Path:
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "app", root / "app")
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
