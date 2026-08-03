import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";

import {
  buildViewportTransform,
  imageToScreen,
  pageBounds,
  screenToImage,
} from "../../components/smtBoardRenderer";
import { GridSpatialIndex } from "../../components/spatialIndex";
import type { RefdesOccurrence, RefdesPage } from "./types";
import styles from "./RefdesViewer.module.css";


const MIN_ZOOM = 0.4;
const MAX_ZOOM = 40;
/** Zoom used when jumping to a refdes, so the label is comfortably readable. */
const LOCATE_ZOOM = 6;
const LOCATE_MS = 260;

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

export function RefdesCanvas({
  page,
  selectedRef,
  target,
  onSelect,
}: {
  page: RefdesPage;
  selectedRef: string;
  /** The exact occurrence to centre on; changes on every locate request. */
  target: RefdesOccurrence | null;
  onSelect: (occurrence: RefdesOccurrence) => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<Pan>(null);
  const animationRef = useRef<number | null>(null);
  const [view, setView] = useState<View>({
    zoom: 1,
    centerX: null,
    centerY: null,
  });
  const [size, setSize] = useState({ width: 900, height: 600 });
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">(
    "loading",
  );

  const bounds = useMemo(
    () => pageBounds(page.pixel_width, page.pixel_height),
    [page.pixel_height, page.pixel_width],
  );
  const transform = useMemo(
    () =>
      buildViewportTransform({
        bounds,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: view.zoom,
        centerX: view.centerX,
        centerY: view.centerY,
      }),
    [bounds, size.height, size.width, view],
  );
  const index = useMemo(
    () =>
      new GridSpatialIndex(
        page.occurrences.map((item) => ({
          x: item.x,
          y: item.y,
          value: item,
        })),
        Math.max(16, Math.max(page.pixel_width, page.pixel_height) / 24),
      ),
    [page.occurrences, page.pixel_height, page.pixel_width],
  );

  // Only draw what is on screen: dense drawings carry hundreds of labels.
  const visible = useMemo(() => {
    const pad = 40 / Math.max(transform.scale, 0.001);
    const topLeft = screenToImage(transform, -pad, -pad);
    const bottomRight = screenToImage(
      transform,
      size.width + pad,
      size.height + pad,
    );
    return index
      .query({
        minX: Math.min(topLeft.x, bottomRight.x),
        minY: Math.min(topLeft.y, bottomRight.y),
        maxX: Math.max(topLeft.x, bottomRight.x),
        maxY: Math.max(topLeft.y, bottomRight.y),
      })
      .map((item) => item.value);
  }, [index, size.height, size.width, transform]);

  const stopAnimation = useCallback(() => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
  }, []);

  const animateTo = useCallback(
    (x: number, y: number, zoom: number) => {
      stopAnimation();
      if (typeof requestAnimationFrame === "undefined") {
        setView({ zoom, centerX: x, centerY: y });
        return;
      }
      const startZoom = view.zoom;
      const startX = transform.centerX;
      const startY = transform.centerY;
      const start =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      const step = (now: number) => {
        const elapsed = Math.min(1, (now - start) / LOCATE_MS);
        const t = easeOutCubic(elapsed);
        setView({
          zoom: startZoom + (zoom - startZoom) * t,
          centerX: startX + (x - startX) * t,
          centerY: startY + (y - startY) * t,
        });
        if (elapsed < 1) {
          animationRef.current = requestAnimationFrame(step);
        } else {
          animationRef.current = null;
        }
      };
      animationRef.current = requestAnimationFrame(step);
    },
    [stopAnimation, transform.centerX, transform.centerY, view.zoom],
  );

  // Locate: centre and zoom onto whichever occurrence was requested.
  useEffect(() => {
    if (!target) return;
    animateTo(target.x, target.y, Math.max(view.zoom, LOCATE_ZOOM));
    // `animateTo` and `view.zoom` intentionally excluded: re-running on every
    // frame of the animation would restart it forever.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => stopAnimation, [stopAnimation]);

  useEffect(() => {
    stopAnimation();
    setView({ zoom: 1, centerX: null, centerY: null });
    setImageState("loading");
  }, [page.page_id, stopAnimation]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const sync = () => {
      const rect = frame.getBoundingClientRect();
      setSize({
        width: Math.max(320, Math.round(rect.width || 900)),
        height: Math.max(320, Math.round(rect.height || 600)),
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
      const currentTransform = buildViewportTransform({
        bounds,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: current.zoom,
        centerX: current.centerX,
        centerY: current.centerY,
      });
      const anchor = screenToImage(currentTransform, px, py);
      const nextZoom = Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, current.zoom * Math.exp(-event.deltaY * 0.0015)),
      );
      const nextTransform = buildViewportTransform({
        bounds,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: nextZoom,
      });
      return {
        zoom: nextZoom,
        centerX: anchor.x - (px - size.width / 2) / nextTransform.scale,
        centerY: anchor.y - (py - size.height / 2) / nextTransform.scale,
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
    const point = screenToImage(transform, px, py);
    const reach = 18 / Math.max(transform.scale, 0.001);
    const nearest = index
      .query({
        minX: point.x - reach,
        minY: point.y - reach,
        maxX: point.x + reach,
        maxY: point.y + reach,
      })
      .map((candidate) => {
        const screen = imageToScreen(transform, candidate.x, candidate.y);
        return {
          occurrence: candidate.value,
          distance: Math.hypot(screen.x - px, screen.y - py),
        };
      })
      .filter((candidate) => candidate.distance <= 18)
      .sort((left, right) => left.distance - right.distance)[0];
    if (nearest) onSelect(nearest.occurrence);
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
  const labelScale = 1 / Math.max(transform.scale, 0.001);

  return (
    <div className={styles.canvasRoot}>
      <div className={styles.canvasToolbar}>
        <span className={styles.canvasHint}>
          滚轮缩放 · 拖动平移 · 点击图上位号
        </span>
        <span className={styles.canvasActions}>
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
        className={styles.canvasFrame}
        tabIndex={0}
        role="application"
        aria-label="位号图"
        data-render-state={imageState}
        data-marker-count={visible.length}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
      >
        <div
          className={styles.canvasStage}
          style={{
            width: page.pixel_width,
            height: page.pixel_height,
            transform: `translate(${
              size.width / 2 - transform.centerX * transform.scale
            }px, ${
              size.height / 2 - transform.centerY * transform.scale
            }px) scale(${transform.scale})`,
          }}
        >
          <img
            className={styles.canvasImage}
            src={page.preview_url}
            width={page.pixel_width}
            height={page.pixel_height}
            alt=""
            draggable={false}
            onLoad={() => setImageState("ready")}
            onError={() => setImageState("error")}
          />
          <svg
            className={styles.canvasMarkers}
            width={page.pixel_width}
            height={page.pixel_height}
            viewBox={`0 0 ${page.pixel_width} ${page.pixel_height}`}
          >
            {visible.map((item) => {
              const isSelected = item.ref.toUpperCase() === selected;
              const isTarget = target?.occurrence_id === item.occurrence_id;
              const width = Math.max(item.right - item.left, 6);
              const height = Math.max(item.bottom - item.top, 6);
              const padX = width * 0.28 + 2;
              const padY = height * 0.42 + 2;
              return (
                <g
                  key={item.occurrence_id}
                  data-ref={item.ref}
                  data-selected={isSelected ? "true" : "false"}
                >
                  <rect
                    x={item.left - padX}
                    y={item.top - padY}
                    width={width + padX * 2}
                    height={height + padY * 2}
                    rx={Math.min(4, height * 0.4)}
                    fill={isSelected ? "rgba(22,119,255,0.22)" : "transparent"}
                    stroke={
                      isTarget
                        ? "#f5222d"
                        : isSelected
                          ? "#1677ff"
                          : "rgba(22,119,255,0)"
                    }
                    strokeWidth={(isTarget ? 2.2 : 1.6) * labelScale}
                  />
                  {isSelected ? (
                    <text
                      x={item.right + padX + 4 * labelScale}
                      y={item.bottom}
                      fontSize={Math.max(height * 1.15, 11 * labelScale)}
                      fontWeight={700}
                      fill="#0b2545"
                      stroke="#ffffff"
                      strokeWidth={3 * labelScale}
                      paintOrder="stroke"
                    >
                      {item.ref}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>
        {imageState === "error" ? (
          <div className={styles.canvasMessage}>位号图载入失败</div>
        ) : imageState === "loading" ? (
          <div className={styles.canvasMessage}>正在载入位号图…</div>
        ) : null}
      </div>
    </div>
  );
}
