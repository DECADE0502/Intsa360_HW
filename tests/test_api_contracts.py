from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.backend.contracts.api import ApiEnvelope, ApiError
from app.backend.contracts.assets import Asset, AssetKind, ToolRun, ToolRunStatus
from app.backend.contracts.jobs import Job, JobPhase, JobStatus
from app.backend.contracts.plugins import ActivationMode, PluginSource, PluginState
from app.backend.contracts.releases import BuildKind, ReleaseAsset, ReleaseManifestV3


NOW = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)


class ApiContractTests(unittest.TestCase):
    def test_api_envelope_has_exact_public_fields(self) -> None:
        envelope = ApiEnvelope[dict[str, str]](
            ok=True,
            request_id=uuid4(),
            data={"status": "healthy"},
            error=None,
        )

        payload = envelope.model_dump(mode="json")

        self.assertEqual(set(payload), {"ok", "request_id", "data", "error"})
        self.assertEqual(payload["data"], {"status": "healthy"})

    def test_error_envelope_rejects_success_without_data_contract(self) -> None:
        error = ApiError(code="invalid_input", message="输入无效", details={"field": "bom"})
        envelope = ApiEnvelope[dict[str, str]](
            ok=False,
            request_id=uuid4(),
            data=None,
            error=error,
        )
        self.assertEqual(envelope.error.code, "invalid_input")

    def test_asset_rejects_invalid_sha256_and_negative_size(self) -> None:
        with self.assertRaises(ValidationError):
            Asset(
                id=uuid4(),
                kind=AssetKind.BOM,
                format="xlsx",
                display_name="主板 BOM",
                relative_path="bom/main.xlsx",
                sha256="not-a-hash",
                size=-1,
                created_at=NOW,
            )

    def test_asset_rejects_absolute_and_parent_paths(self) -> None:
        base = {
            "id": uuid4(),
            "kind": AssetKind.BOM,
            "format": "xlsx",
            "display_name": "主板 BOM",
            "sha256": "a" * 64,
            "size": 12,
            "created_at": NOW,
        }
        for path in (
            "../main.xlsx",
            "/tmp/main.xlsx",
            r"C:\release\main.xlsx",
            "C:/release/main.xlsx",
            "C:main.xlsx",
            ".",
            "NUL",
            "reports/COM1.xlsx",
            "reports/report.xlsx:payload",
            "reports/report.xlsx.",
        ):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                Asset(**base, relative_path=path)

    def test_asset_size_is_a_strict_integer(self) -> None:
        base = {
            "id": uuid4(),
            "kind": AssetKind.BOM,
            "format": "xlsx",
            "display_name": "主板 BOM",
            "relative_path": "bom/main.xlsx",
            "sha256": "a" * 64,
            "created_at": NOW,
        }
        for size in (True, 1.5, "1"):
            with self.subTest(size=size), self.assertRaises(ValidationError):
                Asset(**base, size=size)

    def test_tool_run_serializes_asset_lineage_and_decisions(self) -> None:
        source_id = uuid4()
        output_id = uuid4()
        run = ToolRun(
            id=uuid4(),
            tool_id="bom_process",
            status=ToolRunStatus.SUCCEEDED,
            input_asset_ids=[source_id],
            output_asset_ids=[output_id],
            params={"formats": ["plm", "oa"]},
            decisions={"confirm_shields": True},
            created_at=NOW,
            completed_at=NOW,
        )
        payload = run.model_dump(mode="json")
        self.assertEqual(payload["input_asset_ids"], [str(source_id)])
        self.assertTrue(payload["decisions"]["confirm_shields"])

    def test_job_rejects_unknown_phase_and_progress_outside_range(self) -> None:
        base = {
            "id": uuid4(),
            "kind": "tool_run",
            "status": JobStatus.RUNNING,
            "phase": JobPhase.PROCESSING,
            "progress": 50,
            "message": "正在处理",
            "cancellable": True,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.assertEqual(Job(**base).phase, JobPhase.PROCESSING)
        with self.assertRaises(ValidationError):
            Job(**{**base, "phase": "mystery"})
        with self.assertRaises(ValidationError):
            Job(**{**base, "progress": 101})

    def test_plugin_state_rejects_unknown_source_and_activation_mode(self) -> None:
        plugin = PluginState(
            id="quick_nc_toggle",
            name="Quick NC Toggle",
            source=PluginSource.PLATFORM,
            enabled=True,
            entry_script="cadence/modules/nc_toggle_selected.tcl",
            activation=ActivationMode.RESTART,
            compatible_capture_versions=["16.6", "17.4"],
        )
        self.assertEqual(plugin.activation, ActivationMode.RESTART)
        with self.assertRaises(ValidationError):
            PluginState(**{**plugin.model_dump(), "source": "unknown"})
        with self.assertRaises(ValidationError):
            PluginState(**{**plugin.model_dump(), "activation": "unknown"})

    def test_release_manifest_requires_https_assets_and_valid_hashes(self) -> None:
        asset = ReleaseAsset(
            name="Insta360_HW_Runtime_0.4.0.zip",
            url="https://github.com/DECADE0502/Intsa360_HW/releases/download/v0.4.0/runtime.zip",
            size=1024,
            sha256="a" * 64,
        )
        manifest = ReleaseManifestV3(
            schema_version=3,
            version="0.4.0",
            revision="b" * 40,
            build_kind=BuildKind.PUBLISHED,
            published_at=NOW,
            min_updater_version="0.3.3",
            assets=[asset],
            changelog=["修复物料合并"],
            signature="ed25519:test-signature",
        )
        self.assertEqual(manifest.assets[0].size, 1024)

        with self.assertRaises(ValidationError):
            ReleaseAsset(name="bad.zip", url="http://example.com/bad.zip", size=1, sha256="x")

    def test_release_asset_rejects_path_names_and_non_strict_sizes(self) -> None:
        base = {
            "url": "https://example.com/runtime.zip",
            "sha256": "a" * 64,
        }
        for name in (
            "../runtime.zip",
            "nested/runtime.zip",
            r"nested\runtime.zip",
            "C:runtime.zip",
            "C:.",
            ".",
            "..",
            "NUL",
            "COM1.zip",
            "runtime.zip:payload",
            "runtime.zip.",
            "  ",
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                ReleaseAsset(name=name, size=1, **base)
        for size in (True, 1.5, "1024"):
            with self.subTest(size=size), self.assertRaises(ValidationError):
                ReleaseAsset(name="runtime.zip", size=size, **base)

    def test_all_contract_enums_reject_unknown_values(self) -> None:
        asset = {
            "id": uuid4(),
            "kind": AssetKind.BOM,
            "format": "xlsx",
            "display_name": "主板 BOM",
            "relative_path": "bom/main.xlsx",
            "sha256": "a" * 64,
            "size": 12,
            "created_at": NOW,
        }
        tool_run = {
            "id": uuid4(),
            "tool_id": "bom_process",
            "status": ToolRunStatus.SUCCEEDED,
            "created_at": NOW,
        }
        job = {
            "id": uuid4(),
            "kind": "tool_run",
            "status": JobStatus.RUNNING,
            "phase": JobPhase.PROCESSING,
            "progress": 50,
            "message": "正在处理",
            "cancellable": True,
            "created_at": NOW,
            "updated_at": NOW,
        }
        plugin = {
            "id": "quick_nc_toggle",
            "name": "Quick NC Toggle",
            "source": PluginSource.PLATFORM,
            "enabled": True,
            "entry_script": "cadence/modules/nc_toggle_selected.tcl",
            "activation": ActivationMode.RESTART,
        }
        manifest = {
            "version": "0.4.0",
            "revision": "b" * 40,
            "build_kind": BuildKind.PUBLISHED,
            "published_at": NOW,
            "min_updater_version": "0.3.3",
            "assets": [{"name": "runtime.zip", "url": "https://example.com/runtime.zip", "size": 1, "sha256": "a" * 64}],
            "signature": "ed25519:test-signature",
        }
        cases = (
            (Asset, {**asset, "kind": "unknown"}),
            (ToolRun, {**tool_run, "status": "unknown"}),
            (Job, {**job, "status": "unknown"}),
            (Job, {**job, "phase": "unknown"}),
            (PluginState, {**plugin, "source": "unknown"}),
            (PluginState, {**plugin, "activation": "unknown"}),
            (ReleaseManifestV3, {**manifest, "build_kind": "unknown"}),
        )
        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model(**payload)

    def test_wire_primitives_do_not_coerce_strings_or_integers(self) -> None:
        job = {
            "id": uuid4(),
            "kind": "tool_run",
            "status": JobStatus.RUNNING,
            "phase": JobPhase.PROCESSING,
            "progress": 50,
            "message": "正在处理",
            "cancellable": True,
            "created_at": NOW,
            "updated_at": NOW,
        }
        plugin = {
            "id": "quick_nc_toggle",
            "name": "Quick NC Toggle",
            "source": PluginSource.PLATFORM,
            "enabled": True,
            "entry_script": "nc.tcl",
            "activation": ActivationMode.RESTART,
        }
        asset = {
            "id": uuid4(),
            "kind": AssetKind.BOM,
            "format": "xlsx",
            "display_name": "BOM",
            "relative_path": "bom/main.xlsx",
            "sha256": "a" * 64,
            "size": 1,
            "created_at": NOW,
        }
        cases = (
            (ApiEnvelope[dict[str, str]], {"ok": "false", "request_id": uuid4(), "data": {}}),
            (Job, {**job, "progress": "50"}),
            (Job, {**job, "cancellable": 1}),
            (PluginState, {**plugin, "enabled": "false"}),
            (Asset, {**asset, "pinned": "false"}),
            (
                ReleaseManifestV3,
                {
                    "schema_version": "3",
                    "version": "0.4.0",
                    "revision": "b" * 40,
                    "build_kind": BuildKind.PUBLISHED,
                    "published_at": NOW,
                    "min_updater_version": "0.3.3",
                    "assets": [{"name": "runtime.zip", "url": "https://example.com/runtime.zip", "size": 1, "sha256": "a" * 64}],
                    "signature": "signature",
                },
            ),
        )
        for model, payload in cases:
            with self.subTest(model=str(model), payload=payload), self.assertRaises(ValidationError):
                model(**payload)

    def test_release_versions_follow_semver_2(self) -> None:
        base = {
            "revision": "b" * 40,
            "build_kind": BuildKind.PUBLISHED,
            "published_at": NOW,
            "min_updater_version": "0.3.3",
            "assets": [{"name": "runtime.zip", "url": "https://example.com/runtime.zip", "size": 1, "sha256": "a" * 64}],
            "signature": "signature",
        }
        for version in ("0.0.0", "1.0.0-alpha", "1.0.0-alpha+build.1", "1.2.3-rc.1+sha.abc"):
            with self.subTest(version=version):
                self.assertEqual(ReleaseManifestV3(version=version, **base).version, version)
        for version in ("01.0.0", "1.01.0", "1.0.01", "1.0", "1.0.0-alpha..1", "1.0.0-01"):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                ReleaseManifestV3(version=version, **base)

    def test_dynamic_contract_fields_accept_only_json_values(self) -> None:
        invalid = object()
        cases = (
            (ApiError, {"code": "invalid", "message": "输入无效", "details": {"value": invalid}}),
            (Asset, {"id": uuid4(), "kind": AssetKind.BOM, "format": "xlsx", "display_name": "BOM", "relative_path": "bom/main.xlsx", "sha256": "a" * 64, "size": 1, "created_at": NOW, "metadata": {"value": invalid}}),
            (ToolRun, {"id": uuid4(), "tool_id": "bom_process", "status": ToolRunStatus.QUEUED, "created_at": NOW, "params": {"value": invalid}}),
            (Job, {"id": uuid4(), "kind": "tool_run", "status": JobStatus.RUNNING, "phase": JobPhase.PROCESSING, "progress": 1, "message": "开始", "cancellable": True, "created_at": NOW, "updated_at": NOW, "result": {"value": invalid}}),
        )
        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model(**payload)

    def test_every_public_model_rejects_unknown_fields(self) -> None:
        release_asset = {
            "name": "runtime.zip",
            "url": "https://example.com/runtime.zip",
            "size": 1,
            "sha256": "a" * 64,
        }
        cases = (
            (ApiError, {"code": "invalid", "message": "输入无效"}),
            (ApiEnvelope[dict[str, str]], {"ok": True, "request_id": uuid4(), "data": {"status": "ok"}}),
            (Asset, {"id": uuid4(), "kind": "bom", "format": "xlsx", "display_name": "BOM", "relative_path": "bom/main.xlsx", "sha256": "a" * 64, "size": 1, "created_at": NOW}),
            (ToolRun, {"id": uuid4(), "tool_id": "bom_process", "status": "queued", "created_at": NOW}),
            (Job, {"id": uuid4(), "kind": "tool_run", "status": "running", "phase": "processing", "progress": 1, "message": "开始", "cancellable": True, "created_at": NOW, "updated_at": NOW}),
            (PluginState, {"id": "quick_nc_toggle", "name": "Quick NC Toggle", "source": "platform", "enabled": True, "entry_script": "nc.tcl", "activation": "restart"}),
            (ReleaseAsset, release_asset),
            (ReleaseManifestV3, {"version": "0.4.0", "revision": "b" * 40, "build_kind": "published", "published_at": NOW, "min_updater_version": "0.3.3", "assets": [release_asset], "signature": "signature"}),
        )
        for model, payload in cases:
            with self.subTest(model=str(model)), self.assertRaises(ValidationError):
                model(**payload, unexpected="forbidden")

    def test_every_public_model_serializes_to_json_values(self) -> None:
        asset_id = uuid4()
        run_id = uuid4()
        release_asset = ReleaseAsset(
            name="runtime.zip",
            url="https://example.com/runtime.zip",
            size=1024,
            sha256="a" * 64,
        )
        models_and_expected = (
            (ApiError(code="invalid", message="输入无效"), ("code", "invalid")),
            (ApiEnvelope[dict[str, str]](ok=True, request_id=uuid4(), data={"status": "ok"}), ("data", {"status": "ok"})),
            (Asset(id=asset_id, kind=AssetKind.BOM, format="xlsx", display_name="BOM", relative_path=r"bom\main.xlsx", sha256="a" * 64, size=1, created_at=NOW), ("relative_path", "bom/main.xlsx")),
            (ToolRun(id=run_id, tool_id="bom_process", status=ToolRunStatus.QUEUED, created_at=NOW), ("id", str(run_id))),
            (Job(id=uuid4(), kind="tool_run", status=JobStatus.RUNNING, phase=JobPhase.PROCESSING, progress=1, message="开始", cancellable=True, created_at=NOW, updated_at=NOW), ("phase", "processing")),
            (PluginState(id="quick_nc_toggle", name="Quick NC Toggle", source=PluginSource.PLATFORM, enabled=True, entry_script="nc.tcl", activation=ActivationMode.RESTART), ("activation", "restart")),
            (release_asset, ("size", 1024)),
            (ReleaseManifestV3(version="0.4.0", revision="b" * 40, build_kind=BuildKind.PUBLISHED, published_at=NOW, min_updater_version="0.3.3", assets=[release_asset], signature="signature"), ("build_kind", "published")),
        )
        for model, (key, expected) in models_and_expected:
            with self.subTest(model=model.__class__.__name__):
                payload = model.model_dump(mode="json")
                self.assertEqual(payload[key], expected)

    def test_contract_json_schema_is_deterministic(self) -> None:
        first = ReleaseManifestV3.model_json_schema()
        second = ReleaseManifestV3.model_json_schema()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
