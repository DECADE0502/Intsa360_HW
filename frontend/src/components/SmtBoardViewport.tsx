import { useEffect, useMemo, useRef, useState } from "react";
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
  ASSEMBLY_STATE_COLORS,
  buildViewportTransform,
  hotspotRadius,
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

type ViewportSize = {
  width: number;
  height: number;
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

function eventPoint(element: HTMLElement, clientX: number, clientY: number) {
  const rect = element.getBoundingClientRect();
  return {
    x: clientX - rect.left,
    y: clientY - rect.top,
  };
}

function stageTransform(transform: BoardViewportTransform) {
  return `translate(${transform.viewportWidth / 2 - transform.centerX * transform.scale}px, ${transform.viewportHeight / 2 - transform.centerY * transform.scale}px) scale(${transform.scale})`;
}

function PlacementMarker({
  placement,
  scale,
  selected,
  emphasized,
  muted,
}: {
  placement: SmtPlacement;
  scale: number;
  selected: boolean;
  emphasized: boolean;
  muted: boolean;
}) {
  const x = Number(placement.image_x);
  const y = Number(placement.image_y);
  const color = ASSEMBLY_STATE_COLORS[placement.assembly_state] || "#667085";
  const radius = hotspotRadius(selected || emphasized) / Math.max(scale, 0.001);
  const stroke = selected ? "#101828" : "#ffffff";
  const strokeWidth = (selected ? 3 : emphasized ? 1.5 : 0.8) / Math.max(scale, 0.001);
  const opacity = muted ? 0.16 : emphasized ? 1 : 0.58;
  const labelSize = 12 / Math.max(scale, 0.001);
  const labelOffset = 10 / Math.max(scale, 0.001);
  const labelY = -8 / Math.max(scale, 0.001);
  const ref = placement.ref.toUpperCase();

  return (
    <g
      data-ref={placement.ref}
      data-placement-id={placement.placement_id}
      data-state={placement.assembly_state}
      transform={`translate(${x} ${y})`}
      opacity={opacity}
    >
      <title>{`${placement.ref} · ${placement.assembly_state}`}</title>
      {placement.assembly_state === "conflicting" ? (
        <path
          d={`M 0 ${-radius} L ${radius} ${radius} L ${-radius} ${radius} Z`}
          fill={color}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      ) : placement.assembly_state === "unresolved" ||
        placement.assembly_state === "coordinate_only" ? (
        <path
          d={`M 0 ${-radius} L ${radius} 0 L 0 ${radius} L ${-radius} 0 Z`}
          fill={color}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      ) : placement.assembly_state === "non_smt" ? (
        <rect
          x={-radius}
          y={-radius}
          width={radius * 2}
          height={radius * 2}
          fill={color}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      ) : (
        <circle
          r={radius}
          fill={placement.assembly_state === "candidate_nc" ? "none" : color}
          stroke={placement.assembly_state === "candidate_nc" ? color : stroke}
          strokeWidth={placement.assembly_state === "candidate_nc" ? strokeWidth * 1.4 : strokeWidth}
        />
      )}
      {placement.assembly_state === "confirmed_nc" ? (
        <path
          d={`M ${-radius * 0.62} ${radius * 0.62} L ${radius * 0.62} ${-radius * 0.62}`}
          stroke="#ffffff"
          strokeWidth={2 / Math.max(scale, 0.001)}
        />
      ) : null}
      {selected && (
        <text
          x={radius + labelOffset}
          y={labelY}
          fontSize={labelSize}
          fontWeight={600}
          fill="#101828"
          stroke="#ffffff"
          strokeWidth={4 / Math.max(scale, 0.001)}
          paintOrder="stroke"
        >
          {ref}
        </text>
      )}
    </g>
  );
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
  const [size, setSize] = useState<ViewportSize>({
    width: 900,
    height: 560,
  });
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const frameRef = useRef<HTMLDivElement>(null);
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
  const renderedPlacements = useMemo(() => {
    const padding = 24 / Math.max(transform.scale, 0.001);
    const topLeft = screenToImage(transform, -padding, -padding);
    const bottomRight = screenToImage(
      transform,
      size.width + padding,
      size.height + padding,
    );
    const visible = index.query({
      minX: Math.min(topLeft.x, bottomRight.x),
      minY: Math.min(topLeft.y, bottomRight.y),
      maxX: Math.max(topLeft.x, bottomRight.x),
      maxY: Math.max(topLeft.y, bottomRight.y),
    });
    return visible.map((item) => item.value);
  }, [index, size.height, size.width, transform]);

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

  function wheel(event: ReactWheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const frame = frameRef.current;
    if (!frame) return;
    const point = eventPoint(frame, event.clientX, event.clientY);
    setView((current) => {
      const currentTransform = transformFor(current);
      const imagePoint = screenToImage(currentTransform, point.x, point.y);
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

  function pointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
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

  function pointerMove(event: ReactPointerEvent<HTMLDivElement>) {
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

  function selectAt(event: ReactPointerEvent<HTMLDivElement>) {
    const frame = frameRef.current;
    if (!frame) return;
    const point = eventPoint(frame, event.clientX, event.clientY);
    const imagePoint = screenToImage(transform, point.x, point.y);
    const radius = 14 / Math.max(transform.scale, 0.001);
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
    if (nearest) onSelect?.(nearest.placement);
  }

  function pointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    const pan = panRef.current;
    panRef.current = null;
    event.currentTarget.dataset.dragging = "false";
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (pan && !pan.moved) selectAt(event);
  }

  function keyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
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
      const step = 36 / Math.max(transform.scale, 0.001);
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
    setImageState(page?.preview_url ? "loading" : "error");
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

  if (!page?.preview_url || !page.pixel_width || !page.pixel_height) {
    return (
      <div className={styles.root}>
        <div className={styles.toolbar}>
          <Typography.Text strong>PDF 位号图</Typography.Text>
          <Tag color="gold">暂无可用 PDF 页面或配准结果</Tag>
        </div>
        <div className={styles.empty}>位号图尚未完成配准，暂时不能显示叠加结果</div>
      </div>
    );
  }

  const stageStyle = {
    width: `${page.pixel_width}px`,
    height: `${page.pixel_height}px`,
    transform: stageTransform(transform),
  };

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
              {side === "bottom" ? "背面" : "正面"} PDF 位号图
            </Typography.Text>
          )}
          <Segmented
            aria-label="页面显示范围"
            size="small"
            value={fitMode}
            options={[
              { label: "器件区域", value: "components" },
              { label: "完整 PDF 页面", value: "page" },
            ]}
            onChange={(value) => setFitMode(value as FitMode)}
          />
          <Typography.Text type="secondary">
            PDF 原页 · {renderedPlacements.length} 个可见坐标
          </Typography.Text>
        </Space>
        <Space size={4}>
          <Tooltip title="缩小">
            <Button
              aria-label="缩小页面"
              icon={<MinusOutlined />}
              onClick={() => zoom(0.8)}
            />
          </Tooltip>
          <Tooltip title="放大">
            <Button
              aria-label="放大页面"
              icon={<PlusOutlined />}
              onClick={() => zoom(1.25)}
            />
          </Tooltip>
          <Tooltip title="适合窗口">
            <Button
              aria-label="重置页面视图"
              icon={<FullscreenOutlined />}
              onClick={reset}
            />
          </Tooltip>
        </Space>
      </div>
      <div
        ref={frameRef}
        className={styles.viewportFrame}
        role="img"
        tabIndex={0}
        aria-label={`${side === "bottom" ? "背面" : "正面"} PDF 位号图与坐标热点`}
        data-pdf-source="true"
        data-render-state={imageState}
        data-marker-count={renderedPlacements.length}
        onWheel={wheel}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onKeyDown={keyboard}
      >
        <div className={styles.pdfStage} style={stageStyle}>
          <img
            className={styles.pdfPage}
            src={page.preview_url}
            width={page.pixel_width}
            height={page.pixel_height}
            alt=""
            aria-hidden="true"
            draggable={false}
            onLoad={() => setImageState("ready")}
            onError={() => setImageState("error")}
          />
          <svg
            className={styles.markerLayer}
            width={page.pixel_width}
            height={page.pixel_height}
            viewBox={`0 0 ${page.pixel_width} ${page.pixel_height}`}
            aria-hidden="true"
          >
            {renderedPlacements.map((placement) => {
              const selected =
                placement.ref.toUpperCase() === selectedRef.toUpperCase();
              const emphasized =
                selected || highlighted.has(placement.ref.toUpperCase());
              return (
                <PlacementMarker
                  key={placement.placement_id}
                  placement={placement}
                  scale={transform.scale}
                  selected={selected}
                  emphasized={emphasized}
                  muted={highlighted.size > 0 && !emphasized}
                />
              );
            })}
          </svg>
        </div>
        {imageState === "error" ? (
          <div className={styles.renderMessage}>PDF 页面载入失败</div>
        ) : imageState === "loading" ? (
          <div className={styles.renderMessage}>正在载入 PDF 页面</div>
        ) : null}
        <div className={styles.canvasHint}>
          滚轮缩放 · 拖动平移 · 点击坐标热点查看位号
        </div>
      </div>
    </div>
  );
}
