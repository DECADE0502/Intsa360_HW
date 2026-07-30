export const SMT_RUN_STATES = [
  "source",
  "identifying",
  "needs_confirmation",
  "needs_calibration",
  "review",
  "deliver",
  "failed",
] as const;

export const SMT_SOURCE_ROLES = [
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
] as const;

export const SMT_COORDINATE_SCOPES = [
  "full_design_set",
  "placement_only",
  "smt_only",
  "unknown",
] as const;

export const SMT_REGISTRATION_STATES = [
  "verified",
  "needs_confirmation",
  "needs_calibration",
  "rejected",
] as const;

export const SMT_PLACEMENT_ROLES = [
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
] as const;

export const SMT_ASSEMBLY_STATES = [
  "installed",
  "confirmed_nc",
  "candidate_nc",
  "non_smt",
  "bom_only",
  "coordinate_only",
  "conflicting",
  "unresolved",
] as const;

export type SmtRunState = (typeof SMT_RUN_STATES)[number];
export type SmtSourceRole = (typeof SMT_SOURCE_ROLES)[number];
export type SmtCoordinateScope = (typeof SMT_COORDINATE_SCOPES)[number];
export type SmtRegistrationState = (typeof SMT_REGISTRATION_STATES)[number];
export type SmtPlacementRole = (typeof SMT_PLACEMENT_ROLES)[number];
export type SmtAssemblyState = (typeof SMT_ASSEMBLY_STATES)[number];
export type SmtBoardSide = "top" | "bottom" | "unknown";

export type SmtEvidence = {
  kind: string;
  source_id?: string | null;
  source_location?: string | null;
  value?: string | null;
  weight: "strong" | "supporting" | "weak" | "conflicting";
  message: string;
};

export type SmtQualityIssue = {
  code: string;
  severity: "blocking" | "warning" | "info";
  message: string;
  source_location?: string | null;
};

export type SmtSourceAsset = {
  asset_id: string;
  relative_path: string;
  sha256: string;
  media_type: string;
  file_size: number;
  roles: SmtSourceRole[];
  classification_state: "classified" | "candidate" | "unresolved" | "rejected";
  evidence: SmtEvidence[];
  page_count?: number | null;
  sheet_names: string[];
};

export type SmtCoordinateOccurrence = {
  occurrence_id: string;
  raw_ref: string;
  ref: string;
  raw_x: string;
  raw_y: string;
  normalized_x?: number | null;
  normalized_y?: number | null;
  raw_side: string;
  side: SmtBoardSide;
  raw_rotation: string;
  normalized_rotation?: number | null;
  footprint: string;
  source_line: number;
  warnings: string[];
};

export type SmtCoordinateQuality = {
  valid_rows: number;
  rejected_rows: number;
  unnamed_rows: number;
  duplicate_refs: string[];
  issues: SmtQualityIssue[];
};

export type SmtCoordinateSet = {
  coordinate_set_id: string;
  source_asset_id: string;
  adapter_id: string;
  sheet_or_section: string;
  declared_unit?: string | null;
  normalized_unit?: "mm" | "mil" | "inch" | null;
  unit_state: "declared" | "verified" | "unknown" | "conflicting";
  scope_semantics: SmtCoordinateScope;
  side_mapping: Record<string, SmtBoardSide>;
  rotation_semantics: "degrees_cw" | "degrees_ccw" | "quadrant" | "unknown";
  quality_report: SmtCoordinateQuality;
  occurrences: SmtCoordinateOccurrence[];
};

export type SmtExtractedRef = {
  extracted_ref_id: string;
  ref: string;
  image_x: number;
  image_y: number;
  bbox: [number, number, number, number];
  source: "vector_text" | "ocr";
  source_index: number;
};

export type SmtDrawingPage = {
  page_id: string;
  source_asset_id: string;
  page_number: number;
  pixel_width?: number | null;
  pixel_height?: number | null;
  page_rotation: 0 | 90 | 180 | 270;
  crop_rect?: [number, number, number, number] | null;
  side_candidate: SmtBoardSide;
  drawing_role:
    | "board_top_candidate"
    | "board_bottom_candidate"
    | "board_unknown_side"
    | "assembly_note"
    | "table_page"
    | "multi_board_page"
    | "unrelated_page";
  preview_url?: string | null;
  tile_manifest_url?: string | null;
  extracted_refs: string[];
  positioned_refs?: SmtExtractedRef[];
  evidence: SmtEvidence[];
};

export type SmtRegistrationAnchor = {
  anchor_id: string;
  ref?: string | null;
  coordinate_x: number;
  coordinate_y: number;
  image_x: number;
  image_y: number;
  source: "vector_text" | "ocr" | "user" | "feature";
  inlier: boolean;
};

export type SmtRegistrationValidation = {
  anchor_count: number;
  inlier_ratio?: number | null;
  spatial_coverage?: number | null;
  median_error?: number | null;
  p95_error?: number | null;
  inside_ratio?: number | null;
  runner_up_gap?: number | null;
  mirror_ambiguous: boolean;
  blocking_reasons: string[];
};

export type SmtRegistration = {
  registration_id: string;
  coordinate_set_id: string;
  page_id: string;
  side: "top" | "bottom";
  model: "similarity" | "similarity_with_mirror" | "affine";
  transform: [number, number, number, number, number, number];
  anchors: SmtRegistrationAnchor[];
  validation: SmtRegistrationValidation;
  confidence_state: SmtRegistrationState;
  decision_source: "automatic" | "user_confirmed" | "user_calibrated";
};

export type SmtMaterialOption = {
  part_number: string;
  description: string;
  model: string;
  grade: string;
  is_primary: boolean;
};

export type SmtBomRequirement = {
  parent_code: string;
  quantity?: number | null;
  materials: SmtMaterialOption[];
  source_rows: number[];
};

export type SmtPlacementDecision = {
  decision_id: string;
  action:
    | "confirm_installed"
    | "confirm_nc"
    | "mark_process"
    | "mark_non_smt"
    | "leave_unresolved"
    | "change_role";
  role: SmtPlacementRole;
  assembly_state: SmtAssemblyState;
  reason: string;
  source: "rule" | "history_exact" | "user";
  input_fingerprint: string;
  rule_version: string;
  operator?: string | null;
  created_at: string;
};

export type SmtPlacement = {
  placement_id: string;
  ref: string;
  side: SmtBoardSide;
  coordinate_occurrence_ids: string[];
  image_x?: number | null;
  image_y?: number | null;
  bom_requirement?: SmtBomRequirement | null;
  netlist_present?: boolean | null;
  drawing_present?: boolean | null;
  role: SmtPlacementRole;
  assembly_state: SmtAssemblyState;
  blocking_reasons: string[];
  evidence_chain: SmtEvidence[];
  decision?: SmtPlacementDecision | null;
};

export type SmtAnalysisSummary = {
  source_count: number;
  coordinate_set_count: number;
  drawing_page_count: number;
  placement_count: number;
  installed_count: number;
  confirmed_nc_count: number;
  candidate_nc_count: number;
  unresolved_count: number;
  blocking_count: number;
};

export type SmtAnalysisRunResponse = {
  schema_version: 2;
  run_id: string;
  state: SmtRunState;
  parser_version: string;
  rule_version: string;
  source_fingerprint: string;
  created_at: string;
  updated_at: string;
  sources: SmtSourceAsset[];
  coordinate_sets: SmtCoordinateSet[];
  drawing_pages: SmtDrawingPage[];
  registrations: SmtRegistration[];
  placements: SmtPlacement[];
  summary: SmtAnalysisSummary;
  blocking_reasons: string[];
};
