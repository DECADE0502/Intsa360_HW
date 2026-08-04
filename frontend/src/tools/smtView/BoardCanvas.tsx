import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Tooltip } from "antd";
import { CompressOutlined, MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { buildStageTransform, cssTransform, screenToStage } from "../../components/drawingViewport";
import { GridSpatialIndex } from "../../components/spatialIndex";
import type { BoardSide, Placement, SmtBoard, ViewMode } from "./types";
import styles from "./smtView.module.css";

const MIN_ZOOM = 0.7;
const MAX_ZOOM = 24;

function markerClass(item: Placement, mode: ViewMode) {
  if (mode === "nc") return item.status === "nc" ? styles.markerNc : styles.markerMuted;
  if (mode === "supply") {
    const grade = item.grade.trim();
    return grade && !/(优选|正常)/.test(grade) ? styles.markerRisk : styles.markerPlaced;
  }
  if (mode === "version") {
    if (item.version_change === "added") return styles.markerAdded;
    if (item.version_change === "removed") return styles.markerRemoved;
    if (item.version_change === "replaced") return styles.markerReplaced;
    return styles.markerMuted;
  }
  if (item.status === "placed") return styles.markerPlaced;
  if (item.status === "nc") return styles.markerNc;
  if (item.status === "non_smt") return styles.markerNonSmt;
  return styles.markerOnly;
}

export function BoardCanvas({
  board,
  side,
  mode,
  selectedRef,
  highlightedRefs,
  onSelect,
}: {
  board: SmtBoard;
  side: BoardSide;
  mode: ViewMode;
  selectedRef: string;
  highlightedRefs: string[];
  onSelect: (ref: string) => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; centerX: number; centerY: number; moved: boolean } | null>(null);
  const [viewport, setViewport] = useState({ width: 900, height: 620 });
  const [view, setView] = useState({ zoom: 1, centerX: null as number | null, centerY: null as number | null });
  const bounds = useMemo(() => ({ width: board.bbox.width, height: board.bbox.height }), [board]);
  const points = useMemo(() => board.placements.filter((item) => item.side === side).map((item) => {
    const rawX = item.x_mm - board.bbox.min_x;
    return {
      x: side === "bottom" ? board.bbox.width - rawX : rawX,
      y: board.bbox.max_y - item.y_mm,
      value: item,
    };
  }), [board, side]);
  const index = useMemo(() => new GridSpatialIndex(points, Math.max(1, Math.max(bounds.width, bounds.height) / 20)), [bounds, points]);
  const transform = useMemo(() => buildStageTransform({
    bounds,
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
    zoom: view.zoom,
    centerX: view.centerX,
    centerY: view.centerY,
  }), [bounds, view, viewport]);
  const visible = useMemo(() => {
    const inset = 24 / Math.max(transform.scale, 0.0001);
    const a = screenToStage(transform, -24, -24);
    const b = screenToStage(transform, viewport.width + 24, viewport.height + 24);
    return index.query({
      minX: Math.min(a.x, b.x) - inset,
      minY: Math.min(a.y, b.y) - inset,
      maxX: Math.max(a.x, b.x) + inset,
      maxY: Math.max(a.y, b.y) + inset,
    });
  }, [index, transform, viewport]);
  const selectedPoint = points.find((point) => point.value.ref === selectedRef);
  const highlighted = useMemo(() => new Set(highlightedRefs), [highlightedRefs]);

  const fit = useCallback(() => setView({ zoom: 1, centerX: null, centerY: null }), []);
  const changeZoom = useCallback((factor: number) => {
    setView((current) => ({ ...current, zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.zoom * factor)) }));
  }, []);

  useEffect(() => {
    const node = frameRef.current;
    if (!node) return;
    const update = () => setViewport({ width: Math.max(360, node.clientWidth), height: Math.max(420, node.clientHeight) });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { fit(); }, [board.board_id, side, fit]);
  useEffect(() => {
    if (!selectedPoint) return;
    setView((current) => ({ zoom: Math.max(current.zoom, 5), centerX: selectedPoint.x, centerY: selectedPoint.y }));
  }, [selectedPoint?.x, selectedPoint?.y]);

  function onWheel(event: React.WheelEvent) {
    event.preventDefault();
    const frame = frameRef.current;
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const anchor = screenToStage(transform, x, y);
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * Math.exp(-event.deltaY * 0.0015)));
    const next = buildStageTransform({ bounds, viewportWidth: viewport.width, viewportHeight: viewport.height, zoom });
    setView({
      zoom,
      centerX: anchor.x - (x - viewport.width / 2) / next.scale,
      centerY: anchor.y - (y - viewport.height / 2) / next.scale,
    });
  }

  function pointerDown(event: React.PointerEvent) {
    if (event.button !== 0) return;
    dragRef.current = { x: event.clientX, y: event.clientY, centerX: transform.centerX, centerY: transform.centerY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function pointerMove(event: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    setView((current) => ({ ...current, centerX: drag.centerX - dx / transform.scale, centerY: drag.centerY - dy / transform.scale }));
  }

  function pointerUp(event: React.PointerEvent) {
    dragRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }

  const inverseScale = 1 / Math.max(transform.scale, 0.0001);
  return (
    <section className={styles.canvasPane}>
      <div className={styles.canvasToolbar}>
        <span>{side === "top" ? "正面" : "背面（已镜像）"} · 显示 {points.length} 个位号</span>
        <div>
          <Tooltip title="缩小"><Button size="small" icon={<MinusOutlined />} onClick={() => changeZoom(1 / 1.3)} /></Tooltip>
          <Tooltip title="放大"><Button size="small" icon={<PlusOutlined />} onClick={() => changeZoom(1.3)} /></Tooltip>
          <Tooltip title="适合窗口"><Button size="small" icon={<CompressOutlined />} onClick={fit} /></Tooltip>
        </div>
      </div>
      <div
        ref={frameRef}
        className={styles.canvasFrame}
        onWheel={onWheel}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
      >
        <div className={styles.stage} style={{ width: bounds.width, height: bounds.height, transform: cssTransform(transform) }}>
          <div className={styles.boardOutline} />
          {visible.map((point) => {
            const item = point.value;
            const selected = item.ref === selectedRef;
            const searched = highlighted.has(item.ref);
            return (
              <button
                type="button"
                key={item.ref}
                data-ref={item.ref}
                aria-label={item.ref}
                className={`${styles.marker} ${markerClass(item, mode)} ${selected ? styles.markerSelected : ""} ${searched ? styles.markerSearched : ""}`}
                style={{
                  left: point.x,
                  top: point.y,
                  width: 10 * inverseScale,
                  height: 7 * inverseScale,
                  borderWidth: (selected ? 2.2 : 1.2) * inverseScale,
                  borderRadius: 2 * inverseScale,
                  transform: `translate(-50%, -50%) rotate(${side === "bottom" ? -item.rotation : item.rotation}deg)`,
                }}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => { event.stopPropagation(); onSelect(item.ref); }}
              >
                {view.zoom >= 3.2 || selected ? (
                  <span style={{ fontSize: 10 * inverseScale, transform: `translate(-50%, -140%) rotate(${side === "bottom" ? item.rotation : -item.rotation}deg)` }}>
                    {item.ref}
                  </span>
                ) : null}
              </button>
            );
          })}
          {selectedPoint ? <div className={styles.selectionPulse} style={{ left: selectedPoint.x, top: selectedPoint.y, width: 24 * inverseScale, height: 24 * inverseScale }} /> : null}
        </div>
      </div>
    </section>
  );
}
