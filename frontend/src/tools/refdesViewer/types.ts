export type RefdesSide = "top" | "bottom" | "unknown";
export type RefdesTextLayer = "vector" | "absent" | "image";

export type RefdesOccurrence = {
  occurrence_id: string;
  ref: string;
  x: number;
  y: number;
  left: number;
  top: number;
  right: number;
  bottom: number;
};

export type RefdesPage = {
  page_id: string;
  page_number: number;
  pixel_width: number;
  pixel_height: number;
  preview_url: string;
  side_guess: RefdesSide;
  text_layer: RefdesTextLayer;
  ref_count: number;
  occurrence_count: number;
  occurrences: RefdesOccurrence[];
};

export type RefdesDocument = {
  doc_id: string;
  file_name: string;
  media_type: string;
  page_count: number;
  ref_count: number;
  pages: RefdesPage[];
  notices: string[];
};

/** One entry in the left-hand navigator: a refdes plus where it is printed. */
export type RefdesEntry = {
  ref: string;
  occurrences: RefdesOccurrence[];
};

export const SIDE_LABELS: Record<RefdesSide, string> = {
  top: "正面",
  bottom: "背面",
  unknown: "未标注",
};
