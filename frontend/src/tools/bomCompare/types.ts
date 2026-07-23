export type FindingSeverity = "info" | "warning" | "blocker";

export type ValidationFinding = {
  code: string;
  severity: FindingSeverity;
  message: string;
  parent_code?: string;
  references?: string[];
  details?: Record<string, unknown>;
};

export type SourceBoard = {
  parent_code: string;
  parent_description?: string;
  hardware_version?: string;
  placements?: unknown[];
  substitute_groups?: unknown[];
  items?: unknown[];
  placement_count?: number;
  substitute_group_count?: number;
  material_count?: number;
};

export type SourceInspectionPayload = {
  envelope: {
    profile: string;
    source_path: string;
    source_fingerprint: string;
    data_sheet?: string;
  };
  boards: SourceBoard[];
  findings: ValidationFinding[];
  can_compare: boolean;
};

export type PlacementDiff = {
  parent_code: string;
  reference: string;
  status: "added" | "removed" | "migrated";
  old_material_code: string;
  new_material_code: string;
};

export type SubstituteSnapshot = {
  parent_code?: string;
  group_code?: string;
  main_material_code?: string;
  alternative_material_codes?: string[];
  members?: string[];
  priorities?: Record<string, number>;
  quantity?: string | null;
  references?: string[];
  valid?: boolean;
};

export type SubstituteDiff = {
  status: "added" | "removed" | "changed";
  old: SubstituteSnapshot;
  new: SubstituteSnapshot;
};

export type MetadataDiff = {
  parent_code: string;
  material_code: string;
  old_variants: Array<Record<string, unknown>>;
  new_variants: Array<Record<string, unknown>>;
  old_metadata?: Record<string, unknown>;
  new_metadata?: Record<string, unknown>;
  changed_fields?: string[];
};

export type BoardMetadataDiff = {
  comparison_parent_code: string;
  old: Record<string, unknown>;
  new: Record<string, unknown>;
  changed_fields: string[];
};

export type RawRowDiff = {
  parent_code: string;
  material_code: string;
  status: "added" | "removed" | "changed";
  old_rows: Array<Record<string, unknown>>;
  new_rows: Array<Record<string, unknown>>;
  old_source_ids: string[];
  new_source_ids: string[];
};

export type ChangeEvent = {
  event_id: string;
  kind: string;
  parent_code: string;
  title: string;
  impact: "none" | "metadata" | "supply" | "placement" | "blocker";
  old_snapshot?: Record<string, unknown>;
  new_snapshot?: Record<string, unknown>;
  references?: string[];
  group_codes?: string[];
  blocker_reasons?: string[];
  oa_change_type?: string;
};

export type SemanticSummary = {
  parent_count_old: number;
  parent_count_new: number;
  material_count_old: number;
  material_count_new: number;
  actual_reference_count_old: number;
  actual_reference_count_new: number;
  substitute_group_count_old: number;
  substitute_group_count_new: number;
  changed_event_count: number;
  blocker_count: number;
  event_counts: Record<string, number>;
};

export type SemanticCompare = {
  schema_version: 2;
  model_version: string;
  analysis_fingerprint: string;
  summary: SemanticSummary;
  events: ChangeEvent[];
  raw_row_diff: RawRowDiff[];
  placement_diff: PlacementDiff[];
  substitute_diff: SubstituteDiff[];
  board_metadata_diff: BoardMetadataDiff[];
  metadata_diff: MetadataDiff[];
  blockers: ValidationFinding[];
  warnings: ValidationFinding[];
  can_export: boolean;
};

export type BomCompareResponse = {
  status: "ok" | "error";
  tool: "bom_compare";
  schema_version?: number;
  model_version?: string;
  action?: "inspect" | "compare" | "export";
  error?: string;
  message?: string;
  can_export?: boolean;
  needs_scope_confirmation?: boolean;
  comparison_scope?: ComparisonScope;
  outputs?: string[];
  semantic?: SemanticCompare;
  source_inspections?: {
    old: SourceInspectionPayload;
    new: SourceInspectionPayload;
  };
  summary?: Record<string, any>;
  compare?: Record<string, any>;
  part_summary?: Record<string, any>;
  origin?: Record<string, any>;
  risks?: Record<string, any>;
};

export type BomCompareParams = {
  action?: "inspect" | "compare" | "export";
  bom1?: string;
  bom2?: string;
  source?: string;
  format?: "report" | "json" | "plm" | "oa" | "ecr";
  template?: string;
  side?: "old" | "new";
  scope_confirmation?: boolean;
  parent_mappings?: Record<string, string>;
  reference_resolutions?: Record<string, unknown>;
};

export type ComparisonScopeEvidence = {
  old_reference_count: number;
  new_reference_count: number;
  shared_reference_count: number;
  reference_overlap: number;
  old_material_count: number;
  new_material_count: number;
  shared_material_count: number;
  material_overlap: number;
};

export type ComparisonScopePair = {
  old_parent_code: string;
  new_parent_code: string;
  old_parent_description: string;
  new_parent_description: string;
  status: "exact" | "suggested" | "confirmed";
  evidence: ComparisonScopeEvidence;
};

export type ComparisonScope = {
  status: "exact" | "suggested" | "confirmed" | "unresolved";
  needs_confirmation: boolean;
  pairs: ComparisonScopePair[];
  unresolved_old_parent_codes: string[];
  unresolved_new_parent_codes: string[];
};

export const changeKindLabels: Record<string, string> = {
  unchanged: "无变化",
  metadata_only: "仅描述 / 元数据变化",
  substitute_priority_only: "仅替代优先级变化",
  substitute_configuration_changed: "替代策略 / 方式变化",
  main_changed_refs_migrated: "主料变化并迁移位号",
  alternative_added: "新增替代料",
  alternative_removed: "删除替代料",
  replacement: "A 换成 B",
  quantity_changed: "数量变化",
  reference_added: "位号新增",
  reference_removed: "位号删除",
  reference_migrated: "位号迁移",
  reference_set_changed: "位号集合调整",
  material_added: "新增物料",
  material_removed: "删除物料",
  substitute_structure_invalid: "替代组结构错误",
  placement_blocker: "可能贴错，需阻断",
};

export const profileLabels: Record<string, string> = {
  capture_raw: "Capture 原始 BOM",
  plm_single_board: "PLM 单板 BOM",
  plm_multi_board: "PLM 多 PCBA 汇总",
  oa_bom: "OA BOM",
  oa_ecr: "OA / ECR 变更表",
  unknown: "未识别",
};
