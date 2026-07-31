import type {
  SmtAssemblyState,
  SmtBoardSide,
  SmtPlacement,
} from "../tools/smtAnalysis/types";


export const ASSEMBLY_STATE_COLORS: Record<SmtAssemblyState, string> = {
  installed: "#237f73",
  confirmed_nc: "#d4380d",
  candidate_nc: "#d89614",
  non_smt: "#6b7280",
  bom_only: "#c41d7f",
  coordinate_only: "#7c3aed",
  conflicting: "#cf1322",
  unresolved: "#1677ff",
};

export type BoardBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export type BoardViewportTransform = {
  scale: number;
  centerX: number;
  centerY: number;
  viewportWidth: number;
  viewportHeight: number;
};

export function visiblePlacements(
  placements: SmtPlacement[],
  side: SmtBoardSide,
  states?: Set<SmtAssemblyState>,
) {
  return placements.filter(
    (placement) =>
      placement.image_x != null &&
      placement.image_y != null &&
      Number.isFinite(placement.image_x) &&
      Number.isFinite(placement.image_y) &&
      (side === "unknown" || placement.side === side) &&
      (!states || states.has(placement.assembly_state)),
  );
}

export function pageBounds(width: number, height: number): BoardBounds {
  return {
    minX: 0,
    minY: 0,
    maxX: Math.max(1, width),
    maxY: Math.max(1, height),
  };
}

export function placementContentBounds(
  placements: SmtPlacement[],
  pageWidth: number,
  pageHeight: number,
): BoardBounds {
  const points = placements
    .filter(
      (item) =>
        item.image_x != null &&
        item.image_y != null &&
        Number.isFinite(item.image_x) &&
        Number.isFinite(item.image_y),
    )
    .map((item) => [Number(item.image_x), Number(item.image_y)] as const);
  if (points.length < 2) {
    return pageBounds(pageWidth, pageHeight);
  }
  const minX = Math.min(...points.map(([x]) => x));
  const maxX = Math.max(...points.map(([x]) => x));
  const minY = Math.min(...points.map(([, y]) => y));
  const maxY = Math.max(...points.map(([, y]) => y));
  const span = Math.max(maxX - minX, maxY - minY, 1);
  const padding = Math.max(12, span * 0.08);
  return {
    minX: Math.max(0, minX - padding),
    minY: Math.max(0, minY - padding),
    maxX: Math.min(pageWidth, maxX + padding),
    maxY: Math.min(pageHeight, maxY + padding),
  };
}

export function buildViewportTransform({
  bounds,
  viewportWidth,
  viewportHeight,
  zoom,
  centerX,
  centerY,
}: {
  bounds: BoardBounds;
  viewportWidth: number;
  viewportHeight: number;
  zoom: number;
  centerX?: number | null;
  centerY?: number | null;
}): BoardViewportTransform {
  const width = Math.max(1, bounds.maxX - bounds.minX);
  const height = Math.max(1, bounds.maxY - bounds.minY);
  const inset = 24;
  const baseScale = Math.max(
    0.001,
    Math.min(
      Math.max(1, viewportWidth - inset * 2) / width,
      Math.max(1, viewportHeight - inset * 2) / height,
    ),
  );
  return {
    scale: baseScale * Math.min(12, Math.max(0.5, zoom)),
    centerX:
      centerX == null ? bounds.minX + width / 2 : Number(centerX),
    centerY:
      centerY == null ? bounds.minY + height / 2 : Number(centerY),
    viewportWidth,
    viewportHeight,
  };
}

export function imageToScreen(
  transform: BoardViewportTransform,
  x: number,
  y: number,
) {
  return {
    x:
      (x - transform.centerX) * transform.scale +
      transform.viewportWidth / 2,
    y:
      (y - transform.centerY) * transform.scale +
      transform.viewportHeight / 2,
  };
}

export function screenToImage(
  transform: BoardViewportTransform,
  x: number,
  y: number,
) {
  return {
    x:
      (x - transform.viewportWidth / 2) / transform.scale +
      transform.centerX,
    y:
      (y - transform.viewportHeight / 2) / transform.scale +
      transform.centerY,
  };
}

export function hotspotRadius(emphasized: boolean) {
  return emphasized ? 6.5 : 2.6;
}
