from __future__ import annotations

import json
import threading
import unittest
from urllib.request import urlopen
from unittest.mock import patch

from app.backend import lifecycle_update
from app.backend.suite_app import ROOT, create_server


class BackendRefactorApiTests(unittest.TestCase):
    def test_stdlib_api_keeps_tool_version_and_update_shapes(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address

            def get_json(path: str) -> dict[str, object]:
                with urlopen(f"http://{host}:{port}{path}", timeout=5) as response:
                    return json.loads(response.read().decode("utf-8"))

            tools = get_json("/api/tools")
            self.assertIn("tools", tools)
            self.assertEqual(len(tools["tools"]), 7)
            self.assertTrue({tool["id"] for tool in tools["tools"]} >= {"bom_process", "netlist_compare"})

            version = get_json("/api/version")
            self.assertEqual(version["status"], "ok")
            self.assertIn("version", version)

            update = get_json("/api/update/check")
            self.assertEqual(update["status"], "ok")

            lifecycle = get_json("/api/lifecycle/check")
            self.assertEqual(lifecycle["status"], "ok")
            self.assertIn("checks", lifecycle)
            check_ids = {check["id"] for check in lifecycle["checks"]}
            self.assertTrue({"install_root", "manifest", "frontend", "python", "data_dirs"} <= check_ids)
            lifecycle_text = json.dumps(lifecycle, ensure_ascii=False)
            for bad in ["瀹", "鍓", "绔", "鐩", "鏃"]:
                self.assertNotIn(bad, lifecycle_text)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_update_check_keeps_a_stable_payload_when_the_manifest_is_offline(self) -> None:
        server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with patch.object(lifecycle_update, "_fetch_manifest", side_effect=OSError("offline for test")):
                with urlopen(f"http://{host}:{port}/api/update/check", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(payload["status"], "ok")
            self.assertFalse(payload["has_update"])
            self.assertEqual(payload["remote_status"], "error")
            self.assertEqual(payload["update_reason"], "manifest_unavailable")
            self.assertIn("error", payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
