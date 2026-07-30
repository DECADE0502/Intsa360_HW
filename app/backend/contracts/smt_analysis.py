from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.backend.contracts.api import ContractModel


SmtRunState = Literal[
    "source",
    "identifying",
    "needs_confirmation",
    "needs_calibration",
    "review",
    "deliver",
    "failed",
]
SourceRole = Literal[
    "placement_coordinate",
    "assembly_drawing",
    "schematic_drawing",
    "panel_drawing",
    "stencil_data",
    "board_outline",
    "bom",
    "netlist",
    "unrelated",
    "unknown",
]
ClassificationState = Literal["classified", "candidate", "unresolved", "rejected"]
CoordinateScope = Literal["full_design_set", "placement_only", "smt_only", "unknown"]
UnitState = Literal["declared", "verified", "unknown", "conflicting"]
BoardSide = Literal["top", "bottom", "unknown"]
RegistrationModel = Literal["similarity", "similarity_with_mirror", "affine"]
RegistrationConfidence = Literal["verified", "needs_confirmation", "needs_calibration", "rejected"]
PlacementRole = Literal[
    "smt_component",
    "tht_component",
    "manual_assembly",
    "fiducial",
    "tooling_hole",
    "mounting_hole",
    "test_point",
    "mechanical",
    "panel_object",
    "unknown",
]
AssemblyState = Literal[
    "installed",
    "confirmed_nc",
    "candidate_nc",
    "non_smt",
    "bom_only",
    "coordinate_only",
    "conflicting",
    "unresolved",
]
DecisionAction = Literal[
    "confirm_installed",
    "confirm_nc",
    "mark_process",
    "mark_non_smt",
    "leave_unresolved",
    "change_role",
]
DecisionSource = Literal["rule", "history_exact", "user"]


class SmtEvidence(ContractModel):
    kind: str = Field(min_length=1, max_length=80)
    source_id: Optional[str] = Field(default=None, max_length=160)
    source_location: Optional[str] = Field(default=None, max_length=240)
    value: Optional[str] = None
    weight: Literal["strong", "supporting", "weak", "conflicting"]
    message: str = Field(min_length=1)


class SmtQualityIssue(ContractModel):
    code: str = Field(min_length=1, max_length=80)
    severity: Literal["blocking", "warning", "info"]
    message: str = Field(min_length=1)
    source_location: Optional[str] = Field(default=None, max_length=240)


class SmtSourceAsset(ContractModel):
    asset_id: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1, max_length=160)
    file_size: int = Field(ge=0, strict=True)
    roles: list[SourceRole] = Field(default_factory=list)
    classification_state: ClassificationState
    evidence: list[SmtEvidence] = Field(default_factory=list)
    page_count: Optional[int] = Field(default=None, ge=1)
    sheet_names: list[str] = Field(default_factory=list)


class SmtCoordinateOccurrence(ContractModel):
    occurrence_id: str = Field(min_length=1, max_length=160)
    raw_ref: str
    ref: str
    raw_x: str
    raw_y: str
    normalized_x: Optional[float] = None
    normalized_y: Optional[float] = None
    raw_side: str = ""
    side: BoardSide
    raw_rotation: str = ""
    normalized_rotation: Optional[float] = None
    footprint: str = ""
    source_line: int = Field(ge=1)
    warnings: list[str] = Field(default_factory=list)


class SmtCoordinateQuality(ContractModel):
    valid_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    unnamed_rows: int = Field(ge=0)
    duplicate_refs: list[str] = Field(default_factory=list)
    issues: list[SmtQualityIssue] = Field(default_factory=list)


class SmtCoordinateSet(ContractModel):
    coordinate_set_id: str = Field(min_length=1, max_length=160)
    source_asset_id: str = Field(min_length=1, max_length=160)
    adapter_id: str = Field(min_length=1, max_length=160)
    sheet_or_section: str = ""
    declared_unit: Optional[str] = Field(default=None, max_length=40)
    normalized_unit: Optional[Literal["mm", "mil", "inch"]] = None
    unit_state: UnitState
    scope_semantics: CoordinateScope
    side_mapping: dict[str, BoardSide] = Field(default_factory=dict)
    rotation_semantics: Literal["degrees_cw", "degrees_ccw", "quadrant", "unknown"]
    quality_report: SmtCoordinateQuality
    occurrences: list[SmtCoordinateOccurrence] = Field(default_factory=list)


class SmtExtractedRef(ContractModel):
    extracted_ref_id: str = Field(min_length=1, max_length=160)
    ref: str = Field(min_length=1, max_length=120)
    image_x: float
    image_y: float
    bbox: tuple[float, float, float, float]
    source: Literal["vector_text", "ocr"]
    source_index: int = Field(ge=0)


class SmtDrawingPage(ContractModel):
    page_id: str = Field(min_length=1, max_length=160)
    source_asset_id: str = Field(min_length=1, max_length=160)
    page_number: int = Field(ge=1)
    pixel_width: Optional[int] = Field(default=None, ge=1)
    pixel_height: Optional[int] = Field(default=None, ge=1)
    page_rotation: Literal[0, 90, 180, 270] = 0
    crop_rect: Optional[tuple[float, float, float, float]] = None
    side_candidate: BoardSide
    drawing_role: Literal[
        "board_top_candidate",
        "board_bottom_candidate",
        "board_unknown_side",
        "assembly_note",
        "table_page",
        "multi_board_page",
        "unrelated_page",
    ]
    preview_url: Optional[str] = None
    tile_manifest_url: Optional[str] = None
    extracted_refs: list[str] = Field(default_factory=list)
    positioned_refs: list[SmtExtractedRef] = Field(default_factory=list)
    evidence: list[SmtEvidence] = Field(default_factory=list)


class SmtRegistrationAnchor(ContractModel):
    anchor_id: str = Field(min_length=1, max_length=160)
    ref: Optional[str] = Field(default=None, max_length=120)
    coordinate_x: float
    coordinate_y: float
    image_x: float
    image_y: float
    source: Literal["vector_text", "ocr", "user", "feature"]
    inlier: bool = True


class SmtRegistrationValidation(ContractModel):
    anchor_count: int = Field(ge=0)
    inlier_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    spatial_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    median_error: Optional[float] = Field(default=None, ge=0)
    p95_error: Optional[float] = Field(default=None, ge=0)
    inside_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    runner_up_gap: Optional[float] = Field(default=None, ge=0)
    mirror_ambiguous: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class SmtRegistration(ContractModel):
    registration_id: str = Field(min_length=1, max_length=160)
    coordinate_set_id: str = Field(min_length=1, max_length=160)
    page_id: str = Field(min_length=1, max_length=160)
    side: Literal["top", "bottom"]
    model: RegistrationModel
    transform: tuple[float, float, float, float, float, float]
    anchors: list[SmtRegistrationAnchor] = Field(default_factory=list)
    validation: SmtRegistrationValidation
    confidence_state: RegistrationConfidence
    decision_source: Literal["automatic", "user_confirmed", "user_calibrated"]


class SmtMaterialOption(ContractModel):
    part_number: str
    description: str = ""
    model: str = ""
    grade: str = ""
    is_primary: bool


class SmtBomRequirement(ContractModel):
    parent_code: str = ""
    quantity: Optional[float] = Field(default=None, ge=0)
    materials: list[SmtMaterialOption] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)


class SmtPlacementDecision(ContractModel):
    decision_id: str = Field(min_length=1, max_length=160)
    action: DecisionAction
    role: PlacementRole
    assembly_state: AssemblyState
    reason: str = ""
    source: DecisionSource
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_version: str = Field(min_length=1, max_length=80)
    operator: Optional[str] = Field(default=None, max_length=160)
    created_at: datetime


class SmtPlacement(ContractModel):
    placement_id: str = Field(min_length=1, max_length=160)
    ref: str = Field(min_length=1, max_length=120)
    side: BoardSide
    coordinate_occurrence_ids: list[str] = Field(default_factory=list)
    image_x: Optional[float] = None
    image_y: Optional[float] = None
    bom_requirement: Optional[SmtBomRequirement] = None
    netlist_present: Optional[bool] = None
    drawing_present: Optional[bool] = None
    role: PlacementRole
    assembly_state: AssemblyState
    blocking_reasons: list[str] = Field(default_factory=list)
    evidence_chain: list[SmtEvidence] = Field(default_factory=list)
    decision: Optional[SmtPlacementDecision] = None


class SmtAnalysisSummary(ContractModel):
    source_count: int = Field(ge=0)
    coordinate_set_count: int = Field(ge=0)
    drawing_page_count: int = Field(ge=0)
    placement_count: int = Field(ge=0)
    installed_count: int = Field(ge=0)
    confirmed_nc_count: int = Field(ge=0)
    candidate_nc_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    blocking_count: int = Field(ge=0)


class SmtAnalysisRunResponse(ContractModel):
    schema_version: Literal[2]
    run_id: str = Field(min_length=1, max_length=160)
    state: SmtRunState
    parser_version: str = Field(min_length=1, max_length=80)
    rule_version: str = Field(min_length=1, max_length=80)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    updated_at: datetime
    sources: list[SmtSourceAsset] = Field(default_factory=list)
    coordinate_sets: list[SmtCoordinateSet] = Field(default_factory=list)
    drawing_pages: list[SmtDrawingPage] = Field(default_factory=list)
    registrations: list[SmtRegistration] = Field(default_factory=list)
    placements: list[SmtPlacement] = Field(default_factory=list)
    summary: SmtAnalysisSummary
    blocking_reasons: list[str] = Field(default_factory=list)
