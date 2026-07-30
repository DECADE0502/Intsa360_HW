from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from uuid import uuid4

from app.backend.contracts.smt_analysis import (
    AssemblyState,
    BoardSide,
    CoordinateScope,
    PlacementRole,
    RegistrationModel,
    SmtAnalysisRunResponse,
    SmtAnalysisSummary,
    SmtBomRequirement,
    SmtCoordinateOccurrence,
    SmtCoordinateSet,
    SmtDrawingPage,
    SmtPlacement,
    SmtPlacementDecision,
    SmtRegistration,
    SmtRegistrationAnchor,
    SmtSourceAsset,
)
from app.backend.parsers.bom_table import read_bom_rows
from app.backend.parsers.cadence_pst import parse_part_file
from app.backend.paths import AppPaths
from app.backend.repositories.smt_analysis_repository import SmtAnalysisRepository
from app.backend.smt_analysis.assembly import (
    ExplicitAssemblyDecision,
    analyze_assembly,
    blocking_reasons_for_placements,
    requirements_from_rows,
)
from app.backend.smt_analysis.auto_registration import propose_vector_registration
from app.backend.smt_analysis.classifiers import sniff_media_type
from app.backend.smt_analysis.coordinates import default_coordinate_registry
from app.backend.smt_analysis.drawings import build_drawing_pages
from app.backend.smt_analysis.export import export_analysis
from app.backend.smt_analysis.ingest import scan_source_directory, source_fingerprint
from app.backend.smt_analysis.page_cache import PageCache
from app.backend.smt_analysis.registration import apply_transform, solve_registration
from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_semantic_manifest import load_semantic_manifest


PARSER_VERSION = "smt-parser-v2"
RULE_VERSION = "smt-rules-v2"
_HASH_CHUNK = 1024 * 1024
_UNRESOLVED_STATES: set[AssemblyState] = {
    "candidate_nc",
    "bom_only",
    "coordinate_only",
    "conflicting",
    "unresolved",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _finite_float(value: object, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}不是有效数值") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}不能为无穷大或 NaN")
    return result


def _asset_cache_key(page: SmtDrawingPage) -> str:
    for item in page.evidence:
        if item.kind == "cache_key" and item.value:
            return item.value
    raise ValueError(f"位号图页面 {page.page_id} 缺少缓存证据")


class SmtAnalysisService:
    """Orchestrates the versioned SMT assembly-review workflow.

    Parsing, classification, registration and assembly rules remain pure
    modules. This service owns path security, run state and immutable snapshots.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.paths = AppPaths(self.root)
        self.paths.ensure_runtime_dirs()
        self.repository = SmtAnalysisRepository(self.root)

    def _data_path(
        self,
        raw: str | Path,
        *,
        label: str,
        kind: str,
        optional: bool = False,
    ) -> Path | None:
        text = str(raw or "").strip()
        if not text:
            if optional:
                return None
            raise ValueError(f"缺少{label}")
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = self.paths.data_dir / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.paths.data_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"{label}必须位于平台数据目录内") from exc
        if kind == "file" and not resolved.is_file():
            raise ValueError(f"{label}不存在：{candidate.name}")
        if kind == "directory" and not resolved.is_dir():
            raise ValueError(f"{label}不存在")
        return resolved

    def _relative_data_path(self, path: Path | None) -> str:
        if path is None:
            return ""
        return path.resolve().relative_to(self.paths.data_dir.resolve()).as_posix()

    def _source_asset(
        self,
        path: Path,
        *,
        role: str,
        relative_path: str | None = None,
    ) -> SmtSourceAsset:
        sha256 = _sha256_file(path)
        with path.open("rb") as handle:
            prefix = handle.read(256 * 1024)
        media_type = sniff_media_type(path, prefix)
        relative = relative_path or self._relative_data_path(path)
        return SmtSourceAsset(
            asset_id=_stable_id("src", relative.casefold(), sha256),
            relative_path=relative,
            sha256=sha256,
            media_type=media_type,
            file_size=path.stat().st_size,
            roles=[role],
            classification_state="classified",
            evidence=[],
            page_count=None,
            sheet_names=[],
        )

    def _combined_fingerprint(
        self,
        assets: Sequence[SmtSourceAsset],
        hidden_inputs: Sequence[Path | None],
    ) -> str:
        digest = hashlib.sha256(source_fingerprint(assets).encode("ascii"))
        for path in hidden_inputs:
            if path is None:
                continue
            digest.update(b"\0")
            digest.update(self._relative_data_path(path).encode("utf-8"))
            digest.update(b"\0")
            digest.update(_sha256_file(path).encode("ascii"))
        return digest.hexdigest()

    def _coordinate_sets(
        self,
        source_root: Path,
        assets: Sequence[SmtSourceAsset],
    ) -> list[SmtCoordinateSet]:
        registry = default_coordinate_registry()
        result: list[SmtCoordinateSet] = []
        seen: set[tuple[str, str, str]] = set()
        by_relative = {asset.relative_path: asset for asset in assets}
        for relative, asset in by_relative.items():
            path = (source_root / relative).resolve()
            if not path.is_file():
                continue
            for probe in registry.probes(path):
                if probe.confidence < 70:
                    continue
                key = (asset.asset_id, probe.adapter_id, probe.sheet_or_section)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    parsed = registry.parse(path, probe)
                except ValueError:
                    continue
                stable_set_id = _stable_id(
                    "coords",
                    asset.asset_id,
                    probe.adapter_id,
                    probe.sheet_or_section,
                )
                occurrences = [
                    occurrence.model_copy(
                        update={
                            "occurrence_id": f"{stable_set_id}-{occurrence.source_line}",
                        }
                    )
                    for occurrence in parsed.occurrences
                ]
                result.append(
                    parsed.model_copy(
                        update={
                            "coordinate_set_id": stable_set_id,
                            "source_asset_id": asset.asset_id,
                            "occurrences": occurrences,
                        }
                    )
                )
        return result

    def _explicit_decisions(
        self,
        *,
        processed_bom: Path,
        decision_manifest: Path | None,
        semantic_manifest: Path | None,
    ) -> dict[str, ExplicitAssemblyDecision]:
        records: Mapping[str, Mapping[str, object]] = {}
        if semantic_manifest is not None:
            semantic = load_semantic_manifest(semantic_manifest)
            semantic.verify_processed_bom(processed_bom)
            records = {
                str(ref): item
                for ref, item in {
                    **semantic.installed_by_ref(),
                    **semantic.non_smt_by_ref(),
                }.items()
            }
        elif decision_manifest is not None:
            records = load_decision_manifest(decision_manifest).by_ref()
        return {
            str(ref).strip().upper(): ExplicitAssemblyDecision(
                destination=str(item.get("destination") or "smt"),
                exclusion_kind=str(item.get("exclusion_kind") or ""),
                role=str(item.get("role") or "unknown"),
                subtype=str(item.get("subtype") or ""),
            )
            for ref, item in records.items()
            if str(ref).strip()
        }

    def _summary(
        self,
        *,
        sources: Sequence[SmtSourceAsset],
        coordinate_sets: Sequence[SmtCoordinateSet],
        drawing_pages: Sequence[SmtDrawingPage],
        placements: Sequence[SmtPlacement],
    ) -> SmtAnalysisSummary:
        return SmtAnalysisSummary(
            source_count=len(sources),
            coordinate_set_count=len(coordinate_sets),
            drawing_page_count=len(drawing_pages),
            placement_count=len(placements),
            installed_count=sum(item.assembly_state == "installed" for item in placements),
            confirmed_nc_count=sum(item.assembly_state == "confirmed_nc" for item in placements),
            candidate_nc_count=sum(item.assembly_state == "candidate_nc" for item in placements),
            unresolved_count=sum(item.assembly_state in _UNRESOLVED_STATES for item in placements),
            blocking_count=sum(bool(item.blocking_reasons) for item in placements),
        )

    def _context_paths(
        self,
        *,
        source_root: Path,
        processed_bom: Path,
        netlist_root: Path | None,
        decision_manifest: Path | None,
        semantic_manifest: Path | None,
    ) -> dict[str, object]:
        return {
            "source_root": self._relative_data_path(source_root),
            "processed_bom": self._relative_data_path(processed_bom),
            "netlist_root": self._relative_data_path(netlist_root),
            "decision_manifest": self._relative_data_path(decision_manifest),
            "semantic_manifest": self._relative_data_path(semantic_manifest),
            "selected_coordinate_set_id": "",
            "selected_pages": {},
        }

    def start(
        self,
        *,
        smt_folder: str | Path,
        processed_bom: str | Path,
        netlist_folder: str | Path | None = None,
        decision_manifest: str | Path | None = None,
        semantic_manifest: str | Path | None = None,
    ) -> SmtAnalysisRunResponse:
        source_root = self._data_path(
            smt_folder,
            label="SMT 资料目录",
            kind="directory",
        )
        bom_path = self._data_path(
            processed_bom,
            label="成品 BOM",
            kind="file",
        )
        netlist_root = self._data_path(
            netlist_folder or "",
            label="Cadence 网表目录",
            kind="directory",
            optional=True,
        )
        decision_path = self._data_path(
            decision_manifest or "",
            label="BOM 处理记录",
            kind="file",
            optional=True,
        )
        semantic_path = self._data_path(
            semantic_manifest or "",
            label="BOM 语义记录",
            kind="file",
            optional=True,
        )
        assert source_root is not None
        assert bom_path is not None

        scanned = scan_source_directory(source_root)
        bom_asset = self._source_asset(bom_path, role="bom")
        netlist_assets: list[SmtSourceAsset] = []
        if netlist_root is not None:
            for name in ("pstxprt.dat", "pstxnet.dat"):
                path = netlist_root / name
                if path.is_file():
                    netlist_assets.append(self._source_asset(path, role="netlist"))
        sources = [*scanned, bom_asset, *netlist_assets]
        fingerprint = self._combined_fingerprint(
            sources,
            [decision_path, semantic_path],
        )
        context = self._context_paths(
            source_root=source_root,
            processed_bom=bom_path,
            netlist_root=netlist_root,
            decision_manifest=decision_path,
            semantic_manifest=semantic_path,
        )
        run_id, reused = self.repository.create_or_reuse(
            source_fingerprint=fingerprint,
            parser_version=PARSER_VERSION,
            rule_version=RULE_VERSION,
            source_relative_path=self._relative_data_path(source_root),
            context=context,
        )
        if reused:
            return self.repository.get_snapshot(run_id)

        try:
            coordinate_sets = self._coordinate_sets(source_root, scanned)
            cache = PageCache(source_root, self.paths.smt_analysis_cache_dir)
            drawing_pages = build_drawing_pages(
                run_id=run_id,
                source_root=source_root,
                assets=scanned,
                cache=cache,
            )
            for page in drawing_pages:
                cached = cache.resolve(_asset_cache_key(page))
                self.repository.register_page_asset(
                    run_id=run_id,
                    page_id=page.page_id,
                    path=cached.image_path,
                    media_type=cached.media_type,
                    pixel_width=cached.pixel_width,
                    pixel_height=cached.pixel_height,
                )

            rows = read_bom_rows(bom_path, require_refs=True)
            requirements = requirements_from_rows(rows)
            explicit = self._explicit_decisions(
                processed_bom=bom_path,
                decision_manifest=decision_path,
                semantic_manifest=semantic_path,
            )
            netlist_refs = (
                set(parse_part_file(netlist_root))
                if netlist_root is not None and (netlist_root / "pstxprt.dat").is_file()
                else None
            )
            selected_sets = coordinate_sets if len(coordinate_sets) == 1 else []
            assembly = analyze_assembly(
                coordinate_sets=selected_sets,
                bom_requirements=requirements,
                explicit_decisions=explicit,
                netlist_refs=netlist_refs,
                drawing_refs={
                    ref
                    for page in drawing_pages
                    for ref in page.extracted_refs
                },
            )
            blocking: list[str] = list(assembly.blocking_reasons)
            if not coordinate_sets:
                blocking.append("未识别到可信坐标数据，可继续使用无热点的资料检查模式。")
            elif len(coordinate_sets) > 1:
                blocking.append("发现多个坐标数据候选，请确认本次使用的数据集。")
            if not drawing_pages:
                blocking.append("未识别到可用位号图，将使用坐标诊断视图。")
            elif len(
                [
                    page
                    for page in drawing_pages
                    if page.drawing_role.startswith("board_")
                ]
            ) != 2:
                blocking.append("位号图页面和正反面关系需要确认。")
            now = _utc_now()
            state = (
                "needs_confirmation"
                if coordinate_sets and drawing_pages
                else "review"
            )
            snapshot = SmtAnalysisRunResponse(
                schema_version=2,
                run_id=run_id,
                state=state,
                parser_version=PARSER_VERSION,
                rule_version=RULE_VERSION,
                source_fingerprint=fingerprint,
                created_at=now,
                updated_at=now,
                sources=sources,
                coordinate_sets=coordinate_sets,
                drawing_pages=drawing_pages,
                registrations=[],
                placements=list(assembly.placements),
                summary=self._summary(
                    sources=sources,
                    coordinate_sets=coordinate_sets,
                    drawing_pages=drawing_pages,
                    placements=assembly.placements,
                ),
                blocking_reasons=list(dict.fromkeys(blocking)),
            )
            self.repository.save_snapshot(
                snapshot,
                dependencies={
                    "source_fingerprint": fingerprint,
                    "parser_version": PARSER_VERSION,
                    "rule_version": RULE_VERSION,
                },
            )
            return snapshot
        except Exception as exc:
            self.repository.record_failure(run_id, str(exc))
            raise

    def get(self, run_id: str) -> SmtAnalysisRunResponse:
        return self.repository.get_snapshot(run_id)

    def status(self, run_id: str) -> dict[str, object]:
        return self.repository.status(run_id)

    def preview(self, run_id: str, page_id: str) -> tuple[Path, str]:
        return self.repository.resolve_page_asset(run_id, page_id)

    def delete(self, run_id: str) -> bool:
        return self.repository.remove(run_id)

    def _path_from_context(
        self,
        context: Mapping[str, object],
        key: str,
        *,
        optional: bool = False,
        directory: bool = False,
    ) -> Path | None:
        return self._data_path(
            str(context.get(key) or ""),
            label=key,
            kind="directory" if directory else "file",
            optional=optional,
        )

    def _requirements_and_decisions(
        self,
        context: Mapping[str, object],
    ) -> tuple[
        dict[str, SmtBomRequirement],
        dict[str, ExplicitAssemblyDecision],
        set[str] | None,
    ]:
        bom = self._path_from_context(context, "processed_bom")
        assert bom is not None
        decision = self._path_from_context(
            context,
            "decision_manifest",
            optional=True,
        )
        semantic = self._path_from_context(
            context,
            "semantic_manifest",
            optional=True,
        )
        netlist = self._path_from_context(
            context,
            "netlist_root",
            optional=True,
            directory=True,
        )
        requirements = requirements_from_rows(read_bom_rows(bom, require_refs=True))
        explicit = self._explicit_decisions(
            processed_bom=bom,
            decision_manifest=decision,
            semantic_manifest=semantic,
        )
        refs = (
            set(parse_part_file(netlist))
            if netlist is not None and (netlist / "pstxprt.dat").is_file()
            else None
        )
        return requirements, explicit, refs

    def _confirmed_coordinate_set(
        self,
        coordinate_set: SmtCoordinateSet,
        *,
        scope: CoordinateScope,
        unit: str | None,
        side_mapping: Mapping[str, BoardSide],
    ) -> SmtCoordinateSet:
        normalized_unit = coordinate_set.normalized_unit
        unit_state = coordinate_set.unit_state
        occurrences = list(coordinate_set.occurrences)
        if unit is not None:
            if unit not in {"mm", "mil", "inch"}:
                raise ValueError("坐标单位必须为 mm、mil 或 inch")
            normalized_unit = unit
            unit_state = "verified"
            scale = {"mm": 1.0, "mil": 0.0254, "inch": 25.4}[unit]
            occurrences = [
                item.model_copy(
                    update={
                        "normalized_x": _finite_float(item.raw_x, label="X 坐标") * scale,
                        "normalized_y": _finite_float(item.raw_y, label="Y 坐标") * scale,
                    }
                )
                for item in occurrences
            ]
        if side_mapping:
            occurrences = [
                item.model_copy(
                    update={"side": side_mapping.get(item.raw_side, item.side)}
                )
                for item in occurrences
            ]
        return coordinate_set.model_copy(
            update={
                "normalized_unit": normalized_unit,
                "unit_state": unit_state,
                "scope_semantics": scope,
                "side_mapping": dict(side_mapping) or coordinate_set.side_mapping,
                "occurrences": occurrences,
            }
        )

    def confirm_sources(
        self,
        run_id: str,
        *,
        coordinate_set_id: str,
        scope_semantics: CoordinateScope,
        pages: Mapping[str, BoardSide],
        unit: str | None = None,
        side_mapping: Mapping[str, BoardSide] | None = None,
    ) -> SmtAnalysisRunResponse:
        current = self.get(run_id)
        selected = next(
            (
                item
                for item in current.coordinate_sets
                if item.coordinate_set_id == coordinate_set_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("所选坐标数据集不存在")
        if not pages and current.drawing_pages:
            raise ValueError("请至少选择一个位号图页面")
        page_lookup = {page.page_id: page for page in current.drawing_pages}
        invalid_pages = set(pages) - set(page_lookup)
        if invalid_pages:
            raise ValueError("所选位号图页面不存在")
        if any(side not in {"top", "bottom"} for side in pages.values()):
            raise ValueError("已选择的位号图必须明确指定为正面或背面")
        selected_sides = [side for side in pages.values() if side in {"top", "bottom"}]
        if len(selected_sides) != len(set(selected_sides)):
            raise ValueError("同一面只能选择一个位号图页面")

        confirmed_set = self._confirmed_coordinate_set(
            selected,
            scope=scope_semantics,
            unit=unit,
            side_mapping=side_mapping or {},
        )
        updated_sets = [
            confirmed_set if item.coordinate_set_id == coordinate_set_id else item
            for item in current.coordinate_sets
        ]
        updated_pages = [
            page.model_copy(update={"side_candidate": pages[page.page_id]})
            if page.page_id in pages
            else page
            for page in current.drawing_pages
        ]
        context = self.repository.get_context(run_id)
        context["selected_coordinate_set_id"] = coordinate_set_id
        context["selected_pages"] = dict(pages)
        self.repository.update_context(run_id, context)
        requirements, explicit, netlist_refs = self._requirements_and_decisions(context)
        drawing_refs = {
            ref
            for page in updated_pages
            if page.page_id in pages
            for ref in page.extracted_refs
        }
        assembly = analyze_assembly(
            coordinate_sets=[confirmed_set],
            bom_requirements=requirements,
            explicit_decisions=explicit,
            netlist_refs=netlist_refs,
            drawing_refs=drawing_refs,
        )
        registrations = [
            proposal
            for page_id, side in pages.items()
            if (
                proposal := propose_vector_registration(
                    coordinate_set=confirmed_set,
                    page=next(
                        item
                        for item in updated_pages
                        if item.page_id == page_id
                    ),
                    side=side,
                )
            )
            is not None
        ]
        placements = self._project_placements(
            assembly.placements,
            confirmed_set,
            registrations,
        )
        blocking_reasons = list(assembly.blocking_reasons)
        if registrations:
            blocking_reasons.append("已生成位号文字自动叠加候选，请核对后确认。")
        now = _utc_now()
        next_snapshot = current.model_copy(
            update={
                "state": "needs_calibration" if pages else "review",
                "updated_at": now,
                "coordinate_sets": updated_sets,
                "drawing_pages": updated_pages,
                "registrations": registrations,
                "placements": placements,
                "summary": self._summary(
                    sources=current.sources,
                    coordinate_sets=updated_sets,
                    drawing_pages=updated_pages,
                    placements=placements,
                ),
                "blocking_reasons": blocking_reasons,
            }
        )
        self.repository.save_snapshot(next_snapshot, dependencies={"source_confirmation": context})
        return next_snapshot

    def register(
        self,
        run_id: str,
        *,
        coordinate_set_id: str,
        page_id: str,
        side: str,
        model: RegistrationModel,
        anchors: Sequence[SmtRegistrationAnchor],
        confirmed: bool,
    ) -> SmtAnalysisRunResponse:
        current = self.get(run_id)
        coordinate_set = next(
            (
                item
                for item in current.coordinate_sets
                if item.coordinate_set_id == coordinate_set_id
            ),
            None,
        )
        page = next((item for item in current.drawing_pages if item.page_id == page_id), None)
        if coordinate_set is None or page is None:
            raise ValueError("配准所需的坐标数据集或位号图页面不存在")
        points = [
            (item.normalized_x, item.normalized_y)
            for item in coordinate_set.occurrences
            if item.normalized_x is not None and item.normalized_y is not None
        ]
        if not points:
            raise ValueError("坐标单位尚未确认，不能进行配准")
        coordinate_bounds = (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )
        assert page.pixel_width is not None
        assert page.pixel_height is not None
        registration = solve_registration(
            coordinate_set_id=coordinate_set_id,
            page_id=page_id,
            side=side,
            model=model,
            anchors=anchors,
            coordinate_bounds=coordinate_bounds,
            image_bounds=(0.0, 0.0, float(page.pixel_width), float(page.pixel_height)),
            validation_points=points,
            decision_source="user_confirmed" if confirmed else "user_calibrated",
        )
        registrations = [
            item
            for item in current.registrations
            if not (item.coordinate_set_id == coordinate_set_id and item.side == side)
        ]
        registrations.append(registration)
        placements = self._project_placements(
            current.placements,
            coordinate_set,
            registrations,
        )
        context = self.repository.get_context(run_id)
        selected_pages = context.get("selected_pages")
        required_sides = (
            set(str(value) for value in selected_pages.values())
            if isinstance(selected_pages, Mapping)
            else {side}
        )
        verified_sides = {
            item.side
            for item in registrations
            if item.confidence_state == "verified"
        }
        ready = required_sides <= verified_sides
        now = _utc_now()
        next_snapshot = current.model_copy(
            update={
                "state": "review" if ready else "needs_calibration",
                "updated_at": now,
                "registrations": registrations,
                "placements": placements,
                "summary": self._summary(
                    sources=current.sources,
                    coordinate_sets=current.coordinate_sets,
                    drawing_pages=current.drawing_pages,
                    placements=placements,
                ),
                "blocking_reasons": list(
                    blocking_reasons_for_placements(placements)
                )
                + ([] if ready else ["正反面位号图尚未全部完成配准确认。"]),
            }
        )
        self.repository.save_snapshot(
            next_snapshot,
            dependencies={"registration_id": registration.registration_id},
        )
        return next_snapshot

    def _project_placements(
        self,
        placements: Sequence[SmtPlacement],
        coordinate_set: SmtCoordinateSet,
        registrations: Sequence[SmtRegistration],
    ) -> list[SmtPlacement]:
        occurrences = {
            item.occurrence_id: item
            for item in coordinate_set.occurrences
        }
        by_side = {
            item.side: item
            for item in registrations
            if item.coordinate_set_id == coordinate_set.coordinate_set_id
            and item.confidence_state != "rejected"
        }
        projected: list[SmtPlacement] = []
        for placement in placements:
            occurrence = next(
                (
                    occurrences[identifier]
                    for identifier in placement.coordinate_occurrence_ids
                    if identifier in occurrences
                ),
                None,
            )
            registration = by_side.get(placement.side)
            if (
                occurrence is None
                or registration is None
                or occurrence.normalized_x is None
                or occurrence.normalized_y is None
            ):
                projected.append(
                    placement.model_copy(update={"image_x": None, "image_y": None})
                )
                continue
            image_x, image_y = apply_transform(
                registration.transform,
                occurrence.normalized_x,
                occurrence.normalized_y,
            )
            projected.append(
                placement.model_copy(update={"image_x": image_x, "image_y": image_y})
            )
        return projected

    def decide(
        self,
        run_id: str,
        *,
        placement_id: str,
        action: str,
        role: PlacementRole | None = None,
        reason: str = "",
        operator: str | None = None,
    ) -> SmtAnalysisRunResponse:
        current = self.get(run_id)
        if current.state not in {"review", "deliver"}:
            raise ValueError("请先完成资料确认和位号图配准")
        placement = next(
            (item for item in current.placements if item.placement_id == placement_id),
            None,
        )
        if placement is None:
            raise ValueError("待审核位号不存在")
        decision = self._make_decision(
            placement,
            action=action,
            role=role,
            reason=reason,
            operator=operator,
        )
        self.repository.save_decision(run_id, placement_id, decision)
        placements = [
            self._placement_with_decision(item, decision)
            if item.placement_id == placement_id
            else item
            for item in current.placements
        ]
        unresolved = any(
            item.assembly_state in _UNRESOLVED_STATES
            for item in placements
        )
        next_snapshot = current.model_copy(
            update={
                "state": "review" if unresolved else "deliver",
                "updated_at": _utc_now(),
                "placements": placements,
                "summary": self._summary(
                    sources=current.sources,
                    coordinate_sets=current.coordinate_sets,
                    drawing_pages=current.drawing_pages,
                    placements=placements,
                ),
            }
        )
        self.repository.save_snapshot(
            next_snapshot,
            dependencies={"decision_id": decision.decision_id},
        )
        return next_snapshot

    def _make_decision(
        self,
        placement: SmtPlacement,
        *,
        action: str,
        role: PlacementRole | None,
        reason: str,
        operator: str | None,
    ) -> SmtPlacementDecision:
        target_role = role or placement.role
        state_by_action: dict[str, AssemblyState] = {
            "confirm_installed": "installed",
            "confirm_nc": "confirmed_nc",
            "mark_process": "non_smt",
            "mark_non_smt": "non_smt",
            "leave_unresolved": "unresolved",
            "change_role": placement.assembly_state,
        }
        if action not in state_by_action:
            raise ValueError("审核动作无效")
        input_payload = placement.model_copy(update={"decision": None}).model_dump(
            mode="json"
        )
        input_fingerprint = hashlib.sha256(
            json.dumps(
                input_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        decision = SmtPlacementDecision(
            decision_id=f"decision-{uuid4().hex}",
            action=action,
            role=target_role,
            assembly_state=state_by_action[action],
            reason=reason.strip(),
            source="user",
            input_fingerprint=input_fingerprint,
            rule_version=RULE_VERSION,
            operator=operator,
            created_at=_utc_now(),
        )
        return decision

    @staticmethod
    def _placement_with_decision(
        placement: SmtPlacement,
        decision: SmtPlacementDecision,
    ) -> SmtPlacement:
        return placement.model_copy(
            update={
                "role": decision.role,
                "assembly_state": decision.assembly_state,
                "blocking_reasons": []
                if decision.assembly_state
                in {"installed", "confirmed_nc", "non_smt"}
                else placement.blocking_reasons,
                "decision": decision,
            }
        )

    def decide_many(
        self,
        run_id: str,
        *,
        placement_ids: Sequence[str],
        action: str,
        role: PlacementRole | None = None,
        reason: str = "",
        operator: str | None = None,
    ) -> SmtAnalysisRunResponse:
        identifiers = list(dict.fromkeys(str(value) for value in placement_ids if str(value)))
        if not identifiers:
            raise ValueError("请至少选择一个待审核位号")
        if len(identifiers) > 5000:
            raise ValueError("单次批量审核不能超过 5000 个位号")
        current = self.get(run_id)
        if current.state not in {"review", "deliver"}:
            raise ValueError("请先完成资料确认和位号图配准")
        available = {item.placement_id for item in current.placements}
        if not set(identifiers) <= available:
            raise ValueError("批量审核包含不存在的位号")
        states = {
            item.assembly_state
            for item in current.placements
            if item.placement_id in identifiers
        }
        if len(states) != 1 or "conflicting" in states:
            raise ValueError("批量审核只允许作用于同一类且非冲突的结果")
        selected = {
            item.placement_id: item
            for item in current.placements
            if item.placement_id in identifiers
        }
        decisions = {
            placement_id: self._make_decision(
                selected[placement_id],
                action=action,
                role=role,
                reason=reason,
                operator=operator,
            )
            for placement_id in identifiers
        }
        self.repository.save_decisions(run_id, decisions)
        placements = [
            self._placement_with_decision(
                item,
                decisions[item.placement_id],
            )
            if item.placement_id in decisions
            else item
            for item in current.placements
        ]
        unresolved = any(
            item.assembly_state in _UNRESOLVED_STATES
            for item in placements
        )
        snapshot = current.model_copy(
            update={
                "state": "review" if unresolved else "deliver",
                "updated_at": _utc_now(),
                "placements": placements,
                "summary": self._summary(
                    sources=current.sources,
                    coordinate_sets=current.coordinate_sets,
                    drawing_pages=current.drawing_pages,
                    placements=placements,
                ),
            }
        )
        self.repository.save_snapshot(
            snapshot,
            dependencies={
                "batch_decision_ids": [
                    decision.decision_id
                    for decision in decisions.values()
                ]
            },
        )
        return snapshot

    def finalize(self, run_id: str) -> SmtAnalysisRunResponse:
        current = self.get(run_id)
        unresolved = [
            item.ref
            for item in current.placements
            if item.assembly_state in _UNRESOLVED_STATES
        ]
        if unresolved:
            preview = ",".join(unresolved[:20])
            suffix = "…" if len(unresolved) > 20 else ""
            raise ValueError(
                f"仍有 {len(unresolved)} 个待解决位号，不能完成复核：{preview}{suffix}"
            )
        if current.state not in {"review", "deliver"}:
            raise ValueError("当前分析尚未完成资料确认和配准")
        if current.state == "deliver":
            return current
        snapshot = current.model_copy(
            update={
                "state": "deliver",
                "updated_at": _utc_now(),
                "blocking_reasons": [],
            }
        )
        self.repository.save_snapshot(
            snapshot,
            dependencies={"review_finalized": True},
        )
        return snapshot

    def export(self, run_id: str) -> dict[str, object]:
        snapshot = self.get(run_id)
        return export_analysis(
            snapshot=snapshot,
            outputs_root=self.paths.outputs_dir,
            page_resolver=lambda page_id: self.preview(run_id, page_id),
        )
