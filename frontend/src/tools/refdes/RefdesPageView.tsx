import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";

import {
  buildStageTransform,
  cssTransform,
  screenToStage,
  stageToScreen,
} from "../../components/drawingViewport";
import { GridSpatialIndex } from "../../components/spatialIndex";
import type { RefdesDrawingPage, RefdesMark } from "./types";
import styles from "./RefdesViewer.module.css";


const MIN_ZOOM = 0.5;
const MAX_ZOOM = 40;
/** Zoom used when jumping to a refdes so the label reads comfortably. */
const LOCATE_ZOOM = 7;
const LOCATE_MS = 240;
const HIT_RADIUS_PX = 18;

type View = { zoom: number; centerX: number | null; centerY: number | null };

type Pan = {
  clientX: number;
  clientY: number;
  centerX: number;
  centerY: number;
  scale: number;
  moved: boolean;
} | null;

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export function RefdesPageView({
  page,
  selectedRef,
  target,
  onPick,
}: {
  page: RefdesDrawingPage;
  selectedRef: string;
  /** The mark to centre on. A new object identity re-triggers the jump. */
  target: RefdesMark | null;
  onPick: (mark: RefdesMark) => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<Pan>(null);
  const frameId = useRef<number | null>(null);
  const [view, setView] = useState<View>({ zoom: 1, centerX: null, centerY: null });
  const [size, setSize] = useState({ width: 900, height: 620 });
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">("loading");

  const stage = useMemo(
    () => ({ width: page.pixel_width, height: page.pixel_height }),
    [page.pixel_height, page.pixel_width],
  );

  // Marks arrive normalised (0..1); everything below works in stage pixels.
  const marks = useMemo(
    () =>
      page.marks.map((mark) => ({
        mark,
        x: mark.x * stage.width,
        y: mark.y * stage.height,
      })),
    [page.marks, stage.height, stage.width],
  );

  const transform = useMemo(
    () =>
      buildStageTransform({
        bounds: stage,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: view.zoom,
        centerX: view.centerX,
        centerY: view.centerY,
      }),
    [size.height, size.width, stage, view],
  );

  const index = useMemo(
    () =>
      new GridSpatialIndex(
        marks.map((item) => ({ x: item.x, y: item.y, value: item.mark })),
        Math.max(16, Math.max(stage.width, stage.height) / 24),
      ),
    [marks, stage.height, stage.width],
  );

  // Draw only what is on screen: a dense page carries hundreds of labels.
  const visible = useMemo(() => {
    const pad = 48 / Math.max(transform.scale, 0.0001);
    const topLeft = screenToStage(transform, -pad, -pad);
    const bottomRight = screenToStage(transform, size.width + pad, size.height + pad);
    return index.query({
      minX: Math.min(topLeft.x, bottomRight.x),
      minY: Math.min(topLeft.y, bottomRight.y),
      maxX: Math.max(topLeft.x, bottomRight.x),
      maxY: Math.max(topLeft.y, bottomRight.y),
    });
  }, [index, size.height, size.width, transform]);

  const stopAnimation = useCallback(() => {
    if (frameId.current !== null) {
      cancelAnimationFrame(frameId.current);
      frameId.current = null;
    }
  }, []);

  const jumpTo = useCallback(
    (x: number, y: number, zoom: number) => {
      stopAnimation();
      if (typeof requestAnimationFrame === "undefined") {
        setView({ zoom, centerX: x, centerY: y });
        return;
      }
      const fromZoom = view.zoom;
      const fromX = transform.centerX;
      const fromY = transform.centerY;
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      const step = (now: number) => {
        const elapsed = Math.min(1, (now - started) / LOCATE_MS);
        const t = easeOutCubic(elapsed);
        setView({
          zoom: fromZoom + (zoom - fromZoom) * t,
          centerX: fromX + (x - fromX) * t,
          centerY: fromY + (y - fromY) * t,
        });
        frameId.current = elapsed < 1 ? requestAnimationFrame(step) : null;
      };
      frameId.current = requestAnimationFrame(step);
    },
    [stopAnimation, transform.centerX, transform.centerY, view.zoom],
  );

  useEffect(() => {
    if (!target) return;
    jumpTo(
      target.x * stage.width,
      target.y * stage.height,
      Math.max(view.zoom, LOCATE_ZOOM),
    );
    // Only `target` may retrigger this: including the animated view would restart
    // the animation on every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => stopAnimation, [stopAnimation]);

  useEffect(() => {
    stopAnimation();
    setView({ zoom: 1, centerX: null, centerY: null });
    setImageState("loading");
  }, [page.page_number, stopAnimation]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const sync = () => {
      const rect = frame.getBoundingClientRect();
      setSize({
        width: Math.max(320, Math.round(rect.width || 900)),
        height: Math.max(320, Math.round(rect.height || 620)),
      });
    };
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  function zoomBy(factor: number) {
    stopAnimation();
    setView((current) => ({
      ...current,
      zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.zoom * factor)),
    }));
  }

  function reset() {
    stopAnimation();
    setView({ zoom: 1, centerX: null, centerY: null });
  }

  function onWheel(event: ReactWheelEvent<HTMLDivElement>) {
    const frame = frameRef.current;
    if (!frame) return;
    event.preventDefault();
    stopAnimation();
    const rect = frame.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    setView((current) => {
      const before = buildStageTransform({
        bounds: stage,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: current.zoom,
        centerX: current.centerX,
        centerY: current.centerY,
      });
      const anchor = screenToStage(before, px, py);
      const zoom = Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, current.zoom * Math.exp(-event.deltaY * 0.0015)),
      );
      const after = buildStageTransform({
        bounds: stage,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom,
      });
      return {
        zoom,
        centerX: anchor.x - (px - size.width / 2) / after.scale,
        centerY: anchor.y - (py - size.height / 2) / after.scale,
      };
    });
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    stopAnimation();
    panRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      centerX: transform.centerX,
      centerY: transform.centerY,
      scale: transform.scale,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const pan = panRef.current;
    if (!pan) return;
    const dx = event.clientX - pan.clientX;
    const dy = event.clientY - pan.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 3) pan.moved = true;
    setView((current) => ({
      ...current,
      centerX: pan.centerX - dx / pan.scale,
      centerY: pan.centerY - dy / pan.scale,
    }));
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    const pan = panRef.current;
    panRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!pan || pan.moved) return;
    const frame = frameRef.current;
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const point = screenToStage(transform, px, py);
    const reach = HIT_RADIUS_PX / Math.max(transform.scale, 0.0001);
    const nearest = index
      .query({
        minX: point.x - reach,
        minY: point.y - reach,
        maxX: point.x + reach,
        maxY: point.y + reach,
      })
      .map((candidate) => {
        const screen = stageToScreen(transform, candidate.x, candidate.y);
        return {
          mark: candidate.value,
          distance: Math.hypot(screen.x - px, screen.y - py),
        };
      })
      .filter((candidate) => candidate.distance <= HIT_RADIUS_PX)
      .sort((left, right) => left.distance - right.distance)[0];
    if (nearest) onPick(nearest.mark);
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(1.3);
    } else if (event.key === "-") {
      event.preventDefault();
      zoomBy(1 / 1.3);
    } else if (event.key === "0") {
      event.preventDefault();
      reset();
    }
  }

  const selected = selectedRef.toUpperCase();
  const inverse = 1 / Math.max(transform.scale, 0.0001);
  // The page already prints every refdes, so only the selected one is outlined;
  // boxing all of them would bury the drawing. Hit testing still uses the index,
  // so any printed refdes remains clickable.
  const highlighted = useMemo(
    () => page.marks.filter((mark) => mark.ref.toUpperCase() === selected),
    [page.marks, selected],
  );

  return (
    <div className={styles.pageRoot}>
      <div className={styles.pageToolbar}>
        <span className={styles.pageHint}>滚轮缩放 · 拖动平移 · 点击图上位号</span>
        <span className={styles.pageActions}>
          <button type="button" aria-label="缩小" onClick={() => zoomBy(1 / 1.3)}>
            −
          </button>
          <button type="button" aria-label="放大" onClick={() => zoomBy(1.3)}>
            ＋
          </button>
          <button type="button" aria-label="适合窗口" onClick={reset}>
            适合
          </button>
        </span>
      </div>
      <div
        ref={frameRef}
        className={styles.pageFrame}
        tabIndex={0}
        role="application"
        aria-label="位号图"
        data-render-state={imageState}
        data-visible-marks={visible.length}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
      >
        <div
          className={styles.pageStage}
          style={{
            width: stage.width,
            height: stage.height,
            transform: cssTransform(transform),
          }}
        >
          <img
            className={styles.pageImage}
            src={page.image_url}
            width={stage.width}
            height={stage.height}
            alt=""
            draggable={false}
            onLoad={() => setImageState("ready")}
            onError={() => setImageState("error")}
          />
          <svg
            className={styles.pageMarkers}
            width={stage.width}
            height={stage.height}
            viewBox={`0 0 ${stage.width} ${stage.height}`}
          >
            {highlighted.map((mark) => {
              const isTarget =
                target != null && target.ref === mark.ref && target.order === mark.order;
              const left = mark.left * stage.width;
              const top = mark.top * stage.height;
              const width = Math.max((mark.right - mark.left) * stage.width, 6);
              const height = Math.max((mark.bottom - mark.top) * stage.height, 6);
              const padX = width * 0.3 + 2;
              const padY = height * 0.45 + 2;
              return (
                <g key={`${mark.ref}-${mark.order}`} data-ref={mark.ref} data-selected="true">
                  <rect
                    x={left - padX}
                    y={top - padY}
                    width={width + padX * 2}
                    height={height + padY * 2}
                    rx={Math.min(4, height * 0.4)}
                    fill="rgba(22,119,255,0.20)"
                    stroke={isTarget ? "#f5222d" : "#1677ff"}
                    strokeWidth={(isTarget ? 2.4 : 1.6) * inverse}
                  />
                  <text
                    x={left + width + padX + 5 * inverse}
                    y={top + height}
                    fontSize={Math.max(height * 1.2, 11 * inverse)}
                    fontWeight={700}
                    fill="#0b2545"
                    stroke="#ffffff"
                    strokeWidth={3 * inverse}
                    paintOrder="stroke"
                  >
                    {mark.ref}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        {imageState === "error" ? (
          <div className={styles.pageMessage}>位号图载入失败</div>
        ) : imageState === "loading" ? (
          <div className={styles.pageMessage}>正在载入位号图…</div>
        ) : null}
      </div>
    </div>
  );
}
