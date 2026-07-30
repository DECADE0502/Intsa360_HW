export type SpatialPoint<T> = {
  x: number;
  y: number;
  value: T;
};

export type SpatialBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export class GridSpatialIndex<T> {
  private readonly cells = new Map<string, SpatialPoint<T>[]>();

  constructor(
    points: SpatialPoint<T>[],
    private readonly cellSize: number,
  ) {
    if (!Number.isFinite(cellSize) || cellSize <= 0) {
      throw new Error("spatial index cell size must be positive");
    }
    points.forEach((point) => {
      const key = this.key(point.x, point.y);
      const bucket = this.cells.get(key) || [];
      bucket.push(point);
      this.cells.set(key, bucket);
    });
  }

  private key(x: number, y: number) {
    return `${Math.floor(x / this.cellSize)}:${Math.floor(y / this.cellSize)}`;
  }

  query(bounds: SpatialBounds): SpatialPoint<T>[] {
    const minColumn = Math.floor(bounds.minX / this.cellSize);
    const maxColumn = Math.floor(bounds.maxX / this.cellSize);
    const minRow = Math.floor(bounds.minY / this.cellSize);
    const maxRow = Math.floor(bounds.maxY / this.cellSize);
    const result: SpatialPoint<T>[] = [];
    for (let column = minColumn; column <= maxColumn; column += 1) {
      for (let row = minRow; row <= maxRow; row += 1) {
        const bucket = this.cells.get(`${column}:${row}`) || [];
        bucket.forEach((point) => {
          if (
            point.x >= bounds.minX &&
            point.x <= bounds.maxX &&
            point.y >= bounds.minY &&
            point.y <= bounds.maxY
          ) {
            result.push(point);
          }
        });
      }
    }
    return result;
  }
}
