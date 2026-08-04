export type PlacementStatus = "placed" | "nc" | "bom_only";
export type BoardSide = "top" | "bottom";
export type ViewMode = "placement" | "nc" | "package" | "supply";

export type RegistrationQuality = {
  anchor_count: number;
  rejected_count: number;
  median_mm: number;
  p90_mm: number;
  max_mm: number;
  trusted: boolean;
};

export type DrawingSide = {
  page_number: number;
  image_url: string;
  pixel_width: number;
  pixel_height: number;
  registration: RegistrationQuality;
};

export type Placement = {
  ref: string;
  x_mm: number;
  y_mm: number;
  drawing_x: number;
  drawing_y: number;
  rotation: number;
  side: BoardSide;
  footprint: string;
  status: "placed" | "nc";
  material_code: string;
  name: string;
  model: string;
  description: string;
  grade: string;
  package: string;
  reason: string;
  package_status: string;
  package_kind: string;
  net_package: string;
  package_note: string;
};

export type BomOnlyItem = {
  ref: string;
  status: "bom_only";
  material_code: string;
  name: string;
  model: string;
  description: string;
  reason: string;
};

export type SmtBoard = {
  schema_version: 2;
  board_id: string;
  label: string;
  xy_file_name: string;
  xy_version: string;
  xy_units: "mils" | "mm";
  placements: Placement[];
  bom_only: BomOnlyItem[];
  summary: Record<string, number>;
  drawings: Partial<Record<BoardSide, DrawingSide>>;
  reference_drawing_name: string;
  reference_drawing_url: string;
  package_report_outputs: string[];
  notices: string[];
};

export type CreateBoardRequest = {
  source_dir: string;
  bom_path: string;
  semantic_manifest_path?: string;
  netlist_dir?: string;
  label?: string;
};
