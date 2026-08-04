export type PlacementStatus = "placed" | "nc" | "non_smt" | "bom_only" | "xy_only";
export type BoardSide = "top" | "bottom";
export type ViewMode = "placement" | "nc" | "supply" | "version";
export type VersionChange = "none" | "added" | "removed" | "replaced";

export type Placement = {
  ref: string;
  x_mm: number;
  y_mm: number;
  rotation: number;
  side: BoardSide;
  footprint: string;
  status: PlacementStatus;
  material_code: string;
  name: string;
  model: string;
  description: string;
  grade: string;
  package: string;
  reason: string;
  decision_kind: string;
  version_change: VersionChange;
  baseline_material_code: string;
};

export type BomOnlyItem = {
  ref: string;
  status: "bom_only";
  material_code: string;
  name: string;
  model: string;
  description: string;
  reason: string;
  version_change: VersionChange;
};

export type SmtBoard = {
  schema_version: 1;
  board_id: string;
  label: string;
  xy_file_name: string;
  xy_version: string;
  xy_units: "mils" | "mm";
  bbox: { min_x: number; min_y: number; max_x: number; max_y: number; width: number; height: number };
  source_span: { width: number; height: number };
  placements: Placement[];
  bom_only: BomOnlyItem[];
  xy_only: string[];
  summary: Record<string, number>;
  reference_drawing_name?: string | null;
  reference_drawing_url?: string | null;
  notices: string[];
};

export type CreateBoardRequest = {
  source_dir: string;
  bom_path: string;
  nc_path?: string;
  semantic_manifest_path?: string;
  decision_manifest_path?: string;
  baseline_bom_path?: string;
  label?: string;
};
