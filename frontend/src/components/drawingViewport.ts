/** Pan/zoom maths for a fixed-size image stage. Independent of any drawing domain. */

export type StageBounds = {
  width: number;
  height: number;
};

export type StageTransform = {
  /** Pixels on screen per stage pixel. */
  scale: number;
  centerX: number;
  centerY: number;
  viewportWidth: number;
  viewportHeight: number;
};

const INSET = 24;

export function buildStageTransform({
  bounds,
  viewportWidth,
  viewportHeight,
  zoom,
  centerX,
  centerY,
}: {
  bounds: StageBounds;
  viewportWidth: number;
  viewportHeight: number;
  zoom: number;
  centerX?: number | null;
  centerY?: number | null;
}): StageTransform {
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  const fitScale = Math.max(
    0.0001,
    Math.min(
      Math.max(1, viewportWidth - INSET * 2) / width,
      Math.max(1, viewportHeight - INSET * 2) / height,
    ),
  );
  return {
    scale: fitScale * zoom,
    centerX: centerX == null ? width / 2 : centerX,
    centerY: centerY == null ? height / 2 : centerY,
    viewportWidth,
    viewportHeight,
  };
}

export function stageToScreen(transform: StageTransform, x: number, y: number) {
  return {
    x: (x - transform.centerX) * transform.scale + transform.viewportWidth / 2,
    y: (y - transform.centerY) * transform.scale + transform.viewportHeight / 2,
  };
}

export function screenToStage(transform: StageTransform, x: number, y: number) {
  return {
    x: (x - transform.viewportWidth / 2) / transform.scale + transform.centerX,
    y: (y - transform.viewportHeight / 2) / transform.scale + transform.centerY,
  };
}

export function cssTransform(transform: StageTransform) {
  const offsetX = transform.viewportWidth / 2 - transform.centerX * transform.scale;
  const offsetY = transform.viewportHeight / 2 - transform.centerY * transform.scale;
  return `translate(${offsetX}px, ${offsetY}px) scale(${transform.scale})`;
}
