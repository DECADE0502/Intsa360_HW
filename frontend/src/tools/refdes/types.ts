export type RefdesSide = "top" | "bottom" | "unknown";

/** A printed refdes instance in normalised page coordinates (0..1, top-left origin). */
export type RefdesMark = {
  ref: string;
  x: number;
  y: number;
  left: number;
  top: number;
  right: number;
  bottom: number;
  order: number;
};

export type RefdesDrawingPage = {
  page_number: number;
  pixel_width: number;
  pixel_height: number;
  image_url: string;
  side_guess: RefdesSide;
  has_text_layer: boolean;
  ref_count: number;
  marks: RefdesMark[];
};

export type RefdesDrawing = {
  drawing_id: string;
  file_name: string;
  media_type: string;
  page_count: number;
  ref_count: number;
  pages: RefdesDrawingPage[];
  notices: string[];
};

/** One row of the navigator: a refdes plus every place it is printed. */
export type RefdesEntry = {
  ref: string;
  marks: RefdesMark[];
};

export const SIDE_LABELS: Record<RefdesSide, string> = {
  top: "正面",
  bottom: "背面",
  unknown: "未标注",
};

export function groupMarks(marks: RefdesMark[]): RefdesEntry[] {
  const grouped = new Map<string, RefdesMark[]>();
  marks.forEach((mark) => {
    const bucket = grouped.get(mark.ref);
    if (bucket) bucket.push(mark);
    else grouped.set(mark.ref, [mark]);
  });
  return Array.from(grouped.entries())
    .map(([ref, items]) => ({
      ref,
      marks: [...items].sort((left, right) => left.order - right.order),
    }))
    .sort((left, right) =>
      left.ref.localeCompare(right.ref, undefined, {
        numeric: true,
        sensitivity: "base",
      }),
    );
}
