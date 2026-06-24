from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.backend.config import load_config
from app.backend.paths import AppPaths


class ConfigPathTests(unittest.TestCase):
    def test_default_config_uses_final_platform_branding(self) -> None:
        cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "default.json").read_text(encoding="utf-8-sig"))

        self.assertEqual(cfg["app_name"], "Insta360硬件提效平台")
        self.assertEqual(cfg["cadence"]["menu_ascii"], "insta360_HW")
        self.assertEqual(cfg["cadence"]["accessory_menu_cn"], "Insta360硬件提效平台")

    def test_load_config_merges_local_over_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "default.json").write_text(
                json.dumps({"port_range": [8765, 8775], "cadence": {"menu": "insta360_HW"}}),
                encoding="utf-8",
            )
            (root / "config" / "local.json").write_text(
                json.dumps({"port_range": [9000, 9001]}),
                encoding="utf-8",
            )

            cfg = load_config(root)

            self.assertEqual(cfg["port_range"], [9000, 9001])
            self.assertEqual(cfg["cadence"]["menu"], "insta360_HW")

    def test_app_paths_create_stable_data_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            paths.ensure_runtime_dirs()

            self.assertTrue(paths.data_dir.exists())
            self.assertTrue(paths.inbox_dir.exists())
            self.assertTrue(paths.outputs_dir.exists())
            self.assertTrue(paths.runtime_log_dir.exists())

