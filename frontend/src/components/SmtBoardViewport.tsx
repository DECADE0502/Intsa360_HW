import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import { Button, Segmented, Space, Tag, Tooltip, Typography } from "antd";
import {
  FullscreenOutlined,
  MinusOutlined,
  PlusOutlined,
} from "@ant-design/icons";

import type {
  SmtAnalysisRunResponse,
  SmtAssemblyState,
  SmtBoardSide,
  SmtPlacement,
} from "../tools/smtAnalysis/types";
import {
  buildViewportTransform,
  drawPlacementHotspot,
  imageToScreen,
  pageBounds,
  placementContentBounds,
  screenToImage,
  visiblePlacements,
} from "./smtBoardRenderer";
import type {
  BoardBounds,
  BoardViewportTransform,
} from "./smtBoardRenderer";
import { GridSpatialIndex } from "./spatialIndex";
import styles from "./SmtBoardViewport.module.css";


type BoardView = {
  zoom: number;
  centerX: number | null;
  centerY: number | null;
};

type PanState = {
  clientX: number;
  clientY: number;
  centerX: number;
  centerY: number;
  scale: number;
  moved: boolean;
} | null;

type CanvasSize = {
  width: number;
  height: number;
  dpr: number;
};

type FitMode = "components" | "page";

type SmtBoardViewportProps = {
  run: SmtAnalysisRunResponse;
  side?: SmtBoardSide;
  selectedRef?: string;
  highlightedRefs?: Set<string>;
  visibleStates?: Set<SmtAssemblyState>;
  onSideChange?: (side: "top" | "bottom") => void;
  onSelect?: (placement: SmtPlacement) => void;
};

const INITIAL_VIEW: BoardView = {
  zoom: 1,
  centerX: null,
  centerY: null,
};

function normalizeSet(values?: Set<string>) {
  return new Set(Array.from(values || [], (value) => value.toUpperCase()));
}

function canvasPoint(
  canvas: HTMLCanvasElement,
  clientX: number,
  clientY: number,
) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: clientX - rect.left,
    y: clientY - rect.top,
  };
}

export function SmtBoardViewport({
  run,
  side: controlledSide,
  selectedRef = "",
  highlightedRefs,
  visibleStates,
  onSideChange,
  onSelect,
}: SmtBoardViewportProps) {
  const availableSides = useMemo(
    () =>
      Array.from(
        new Set(
          run.registrations
            .filter((item) => item.confidence_state !== "rejected")
            .map((item) => item.side),
        ),
      ) as Array<"top" | "bottom">,
    [run.registrations],
  );
  const [localSide, setLocalSide] = useState<"top" | "bottom">(
    availableSides[0] || "top",
  );
  const side =
    controlledSide === "top" || controlledSide === "bottom"
      ? controlledSide
      : localSide;
  const registration = run.registrations.find(
    (item) => item.side === side && item.confidence_state !== "rejected",
  );
  const page = run.drawing_pages.find(
    (item) => item.page_id === registration?.page_id,
  );
  const [view, setView] = useState<BoardView>(INITIAL_VIEW);
  const [fitMode, setFitMode] = useState<FitMode>("components");
  const [size, setSize] = useState<CanvasSize>({
    width: 900,
    height: 560,
    dpr: 1,
  });
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [imageError, setImageError] = useState(false);
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transformRef = useRef<BoardViewportTransform | null>(null);
  const panRef = useRef<PanState>(null);
  const highlighted = useMemo(
    () => normalizeSet(highlightedRefs),
    [highlightedRefs],
  );
  const placements = useMemo(
    () => visiblePlacements(run.placements, side, visibleStates),
    [run.placements, side, visibleStates],
  );
  const bounds = useMemo<BoardBounds>(() => {
    if (!page?.pixel_width || !page.pixel_height) {
      return pageBounds(1, 1);
    }
    return fitMode === "components"
      ? placementContentBounds(
          placements,
          page.pixel_width,
          page.pixel_height,
        )
      : pageBounds(page.pixel_width, page.pixel_height);
  }, [fitMode, page?.pixel_height, page?.pixel_width, placements]);
  const index = useMemo(() => {
    const span = Math.max(
      bounds.maxX - bounds.minX,
      bounds.maxY - bounds.minY,
      1,
    );
    return new GridSpatialIndex(
      placements.map((placement) => ({
        x: Number(placement.image_x),
        y: Number(placement.image_y),
        value: placement,
      })),
      Math.max(12, span / 18),
    );
  }, [bounds, placements]);

  function reset() {
    setView(INITIAL_VIEW);
  }

  function transformFor(current: BoardView) {
    return buildViewportTransform({
      bounds,
      viewportWidth: size.width,
      viewportHeight: size.height,
      zoom: current.zoom,
      centerX: current.centerX,
      centerY: current.centerY,
    });
  }

  function zoom(factor: number) {
    setView((current) => ({
      ...current,
      zoom: Math.min(12, Math.max(0.5, current.zoom * factor)),
    }));
  }

  function wheel(event: ReactWheelEvent<HTMLCanvasElement>) {
    event.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const point = canvasPoint(canvas, event.clientX, event.clientY);
    setView((current) => {
      const currentTransform = transformFor(current);
      const imagePoint = screenToImage(
        currentTransform,
        point.x,
        point.y,
      );
      const nextZoom = Math.min(
        12,
        Math.max(0.5, current.zoom * Math.exp(-event.deltaY * 0.0012)),
      );
      const nextTransform = buildViewportTransform({
        bounds,
        viewportWidth: size.width,
        viewportHeight: size.height,
        zoom: nextZoom,
      });
      return {
        zoom: nextZoom,
        centerX:
          imagePoint.x -
          (point.x - size.width / 2) / nextTransform.scale,
        centerY:
          imagePoint.y -
          (point.y - size.height / 2) / nextTransform.scale,
      };
    });
  }

  function pointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0) return;
    const transform = transformFor(view);
    panRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      centerX: transform.centerX,
      centerY: transform.centerY,
      scale: transform.scale,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.currentTarget.dataset.dragging = "true";
  }

  function pointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const pan = panRef.current;
    if (!pan) return;
    const dx = event.clientX - pan.clientX;
    const dy = event.clientY - pan.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      pan.moved = true;
    }
    setView((current) => ({
      ...current,
      centerX: pan.centerX - dx / pan.scale,
      centerY: pan.centerY - dy / pan.scale,
    }));
  }

  function selectAt(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const transform = transformRef.current;
    if (!canvas || !transform) return;
    const point = canvasPoint(canvas, event.clientX, event.clientY);
    const imagePoint = screenToImage(transform, point.x, point.y);
    const radius = 14 / transform.scale;
    const matches = index.query({
      minX: imagePoint.x - radius,
      minY: imagePoint.y - radius,
      maxX: imagePoint.x + radius,
      maxY: imagePoint.y + radius,
    });
    const nearest = matches
      .map((candidate) => {
        const screen = imageToScreen(
          transform,
          candidate.x,
          candidate.y,
        );
        return {
          placement: candidate.value,
          distance: Math.hypot(screen.x - point.x, screen.y - point.y),
        };
      })
      .filter((candidate) => candidate.distance <= 14)
      .sort((left, right) => left.distance - right.distance)[0];
    if (nearest) {
      onSelect?.(nearest.placement);
    }
  }

  function pointerUp(event: ReactPointerEvent<HTMLCanvasElement>) {
    const pan = panRef.current;
    panRef.current = null;
    event.currentTarget.dataset.dragging = "false";
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (pan && !pan.moved) {
      selectAt(event);
    }
  }

  function keyboard(event: ReactKeyboardEvent<HTMLCanvasElement>) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoom(1.25);
    } else if (event.key === "-") {
      event.preventDefault();
      zoom(0.8);
    } else if (event.key === "0") {
      event.preventDefault();
      reset();
    } else if (
      ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
        event.key,
      )
    ) {
      event.preventDefault();
      const transform = transformFor(view);
      const step = 36 / transform.scale;
      setView((current) => ({
        ...current,
        centerX:
          transform.centerX +
          (event.key === "ArrowLeft"
            ? -step
            : event.key === "ArrowRight"
              ? step
              : 0),
        centerY:
          transform.centerY +
          (event.key === "ArrowUp"
            ? -step
            : event.key === "ArrowDown"
              ? step
              : 0),
      }));
    }
  }

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const sync = () => {
      const rect = frame.getBoundingClientRect();
      setSize({
        width: Math.max(320, Math.round(rect.width || 900)),
        height: Math.max(360, Math.round(rect.height || 560)),
        dpr: Math.min(2, Math.max(1, window.devicePixelRatio || 1)),
      });
    };
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setView(INITIAL_VIEW);
  }, [page?.page_id, side, fitMode]);

  useEffect(() => {
    if (!page?.preview_url) {
      setImage(null);
      setImageError(false);
      return;
    }
    let cancelled = false;
    const next = new Image();
    next.decoding = "async";
    next.onload = () => {
      if (cancelled) return;
      setImage(next);
      setImageError(false);
    };
    next.onerror = () => {
      if (cancelled) return;
      setImage(null);
      setImageError(true);
    };
    next.src = page.preview_url;
    return () => {
      cancelled = true;
    };
  }, [page?.preview_url]);

  useEffect(() => {
    const selected = placements.find(
      (item) => item.ref.toUpperCase() === selectedRef.toUpperCase(),
    );
    if (selected?.image_x == null || selected.image_y == null) return;
    setView((current) => ({
      zoom: Math.max(current.zoom, 2.2),
      centerX: Number(selected.image_x),
      centerY: Number(selected.image_y),
    }));
  }, [placements, selectedRef]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !page?.pixel_width || !page.pixel_height) return;
    canvas.width = Math.round(size.width * size.dpr);
    canvas.height = Math.round(size.height * size.dpr);
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
    context.clearRect(0, 0, size.width, size.height);
    context.fillStyle = "#eef2f1";
    context.fillRect(0, 0, size.width, size.height);

    const transform = transformFor(view);
    transformRef.current = transform;
    if (image) {
      context.save();
      context.translate(size.width / 2, size.height / 2);
      context.scale(transform.scale, transform.scale);
      context.translate(-transform.centerX, -transform.centerY);
      context.imageSmoothingEnabled = true;
      context.drawImage(
        image,
        0,
        0,
        page.pixel_width,
        page.pixel_height,
      );
      context.restore();
    } else {
      context.fillStyle = imageError ? "#a61d24" : "#667085";
      context.font = "14px system-ui, sans-serif";
      context.textAlign = "center";
      context.fillText(
        imageError ? "位号图载入失败" : "正在载入位号图",
        size.width / 2,
        size.height / 2,
      );
    }

    const hasHighlights = highlighted.size > 0;
    for (const placement of placements) {
      const screen = imageToScreen(
        transform,
        Number(placement.image_x),
        Number(placement.image_y),
      );
      if (
        screen.x < -20 ||
        screen.y < -20 ||
        screen.x > size.width + 20 ||
        screen.y > size.height + 20
      ) {
        continue;
      }
      const selected =
        placement.ref.toUpperCase() === selectedRef.toUpperCase();
      const emphasized =
        selected || highlighted.has(placement.ref.toUpperCase());
      drawPlacementHotspot(context, placement, screen.x, screen.y, {
        selected,
        emphasized,
        muted: hasHighlights && !emphasized,
      });
      if (selected && view.zoom >= 1.6) {
        context.save();
        context.font = "600 12px system-ui, sans-serif";
        context.textBaseline = "bottom";
        context.lineWidth = 4;
        context.strokeStyle = "#ffffff";
        context.fillStyle = "#101828";
        context.strokeText(placement.ref, screen.x + 10, screen.y - 8);
        context.fillText(placement.ref, screen.x + 10, screen.y - 8);
        context.restore();
      }
    }
    canvas.dataset.renderState = image
      ? "ready"
      : imageError
        ? "error"
        : "loading";
    canvas.dataset.hotspotCount = String(placements.length);
  }, [
    bounds,
    highlighted,
    image,
    imageError,
    page?.pixel_height,
    page?.pixel_width,
    placements,
    selectedRef,
    size,
    view,
  ]);

  if (!page?.preview_url || !page.pixel_width || !page.pixel_height) {
    return (
      <div className={styles.root}>
        <div className={styles.toolbar}>
          <Typography.Text strong>坐标诊断视图</Typography.Text>
          <Tag color="gold">无可信底图或配准</Tag>
        </div>
        <div className={styles.empty}>
          位号图尚未完成配准，不能显示可信叠加结果
        </div>
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <Space size={8} wrap>
          {availableSides.length > 1 ? (
            <Segmented
              value={side}
              options={[
                { label: "正面", value: "top" },
                { label: "背面", value: "bottom" },
              ]}
              onChange={(value) => {
                const next = value as "top" | "bottom";
                setLocalSide(next);
                onSideChange?.(next);
              }}
            />
          ) : (
            <Typography.Text strong>
              {side === "bottom" ? "背面" : "正面"}位号图
            </Typography.Text>
          )}
          <Segmented
            aria-label="板图显示范围"
            size="small"
            value={fitMode}
            options={[
              { label: "器件区域", value: "components" },
              { label: "完整页面", value: "page" },
            ]}
            onChange={(value) => setFitMode(value as FitMode)}
          />
          <Typography.Text type="secondary">
            {placements.length} 个坐标热点
          </Typography.Text>
        </Space>
        <Space size={4}>
          <Tooltip title="缩小">
            <Button
              aria-label="缩小板面"
              icon={<MinusOutlined />}
              onClick={() => zoom(0.8)}
            />
          </Tooltip>
          <Tooltip title="放大">
            <Button
              aria-label="放大板面"
              icon={<PlusOutlined />}
              onClick={() => zoom(1.25)}
            />
          </Tooltip>
          <Tooltip title="适合窗口">
            <Button
              aria-label="重置板面"
              icon={<FullscreenOutlined />}
              onClick={reset}
            />
          </Tooltip>
        </Space>
      </div>
      <div ref={frameRef} className={styles.canvasFrame}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          role="img"
          tabIndex={0}
          aria-label={`${side === "bottom" ? "背面" : "正面"}真实位号图与坐标热点`}
          onWheel={wheel}
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerCancel={pointerUp}
          onKeyDown={keyboard}
        />
        <div className={styles.canvasHint}>
          滚轮缩放 · 拖动平移 · 点击热点查看位号
        </div>
      </div>
    </div>
  );
}
