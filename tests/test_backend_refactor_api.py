from __future__ import annotations

import json
import threading
import unittest
from urllib.request import urlopen

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
            self.assertEqual(len(tools["tools"]), 6)
            self.assertTrue({tool["id"] for tool in tools["tools"]} >= {"bom_process", "netlist_compare"})

            version = get_json("/api/version")
            self.assertEqual(version["status"], "ok")
            self.assertIn("version", version)

            update = get_json("/api/update/check")
            self.assertEqual(update["status"], "ok")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
