from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.backend import history
from app.backend.config import load_config
from app.backend.paths import AppPaths
from app.backend.tools.common import _output_dir


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

    def test_installed_runtime_uses_local_app_data_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as local:
            root = Path(tmp)
            (root / "install_manifest.json").write_text(
                json.dumps({"schema": 2, "product": "Insta360_HW", "layout": "runtime-v2"}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"LOCALAPPDATA": local}, clear=False):
                paths = AppPaths(root)
                self.assertEqual(paths.state_root, (Path(local) / "Insta360_HW").resolve())

    def test_installed_tool_outputs_and_history_mirror_use_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            root = Path(tmp)
            state_root = Path(state).resolve()
            (root / "install_manifest.json").write_text(
                json.dumps({"schema": 3, "product": "Insta360_HW", "layout": "runtime-v3"}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
                output = _output_dir({}, root, "bom")
                history_dir = history._history_dir(root)

            self.assertEqual(output, state_root / "data" / "outputs" / "bom")
            self.assertEqual(history_dir, state_root / "data" / "history")
            self.assertFalse((root / "data").exists())

    def test_cadence_export_jobs_and_probe_logs_use_state_root(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "cadence" / "iac_bom_tool.tcl"
        ).read_text(encoding="utf-8-sig")

        self.assertIn("set ::IAC_STATE_ROOT", source)
        self.assertIn('$::IAC_STATE_ROOT/data/jobs', source)
        self.assertIn('$::IAC_STATE_ROOT/data/reports/runtime', source)
        self.assertNotIn('$::IAC_ROOT/data/jobs', source)

    def test_incomplete_install_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "install_manifest.json").write_text(
                json.dumps({"product": "Insta360_HW"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "schema"):
                _ = AppPaths(root).state_root

    def test_development_root_keeps_in_tree_state_even_with_a_local_app_data_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as local:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": local}, clear=False):
                paths = AppPaths(root)
                self.assertTrue(paths.is_development)
                self.assertEqual(paths.runtime_root, root.resolve())
                self.assertEqual(paths.state_root, root.resolve())

    def test_development_root_ignores_stale_install_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as local:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            (root / "install_manifest.json").write_text("{not json", encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": local}, clear=False):
                self.assertEqual(AppPaths(root).state_root, root.resolve())

    def test_explicit_state_root_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": state}, clear=False):
                self.assertEqual(AppPaths(Path(tmp)).state_root, Path(state).resolve())

