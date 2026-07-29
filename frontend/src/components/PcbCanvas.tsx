import { useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from "react";

import type { SmtComponent } from "../api/client";
import styles from "./PcbCanvas.module.css";


export type PcbCanvasProps = {
  outline: Array<Array<[number, number]>>;
  components: SmtComponent[];
  side: "top" | "bottom" | "both";
  highlightedRefs: Set<string>;
  onHover?: (ref: string | null) => void;
  onSelect?: (ref: string) => void;
  onFrameSelect?: (refs: string[]) => void;
  colorScheme?: "nc-emphasis" | "sanity-emphasis" | "default";
};

type ViewTransform = { scale: number; tx: number; ty: number };
type Point = { x: number; y: number };
type Gesture =
  | { mode: "frame"; start: Point; current: Point }
  | { mode: "pan"; clientX: number; clientY: number };

function boardBounds(outline: PcbCanvasProps["outline"], components: SmtComponent[]) {
  const points = outline.flat();
  const xs = [...points.map(([x]) => x), ...components.map((item) => item.x_mm)];
  const ys = [...points.map(([, y]) => y), ...components.map((item) => item.y_mm)];
  const minX = xs.length ? Math.min(...xs) : 0;
  const maxX = xs.length ? Math.max(...xs) : 100;
  const minY = ys.length ? Math.min(...ys) : 0;
  const maxY = ys.length ? Math.max(...ys) : 80;
  const boardWidth = Math.max(maxX - minX, 1);
  const boardHeight = Math.max(maxY - minY, 1);
  const padX = boardWidth * 0.05;
  const padY = boardHeight * 0.05;
  return {
    x: minX - padX,
    y: minY - padY,
    width: boardWidth + padX * 2,
    height: boardHeight + padY * 2,
  };
}

function normalizeRefs(refs: Set<string>) {
  return new Set(Array.from(refs, (ref) => ref.toUpperCase()));
}

function componentStatusClass(component: SmtComponent) {
  if (component.status === "nc") return styles.nc;
  if (component.status === "candidate_nc") return styles.candidateNc;
  if (component.status === "unverified") return styles.unverified;
  if (component.status === "missing_bom") return styles.missingBom;
  if (component.status === "missing_layout") return styles.missingLayout;
  return styles.installed;
}


export function PcbCanvas({
  outline,
  components,
  side,
  highlightedRefs,
  onHover,
  onSelect,
  onFrameSelect,
  colorScheme = "default",
}: PcbCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const [transform, setTransform] = useState<ViewTransform>({ scale: 1, tx: 0, ty: 0 });
  const [frame, setFrame] = useState<{ start: Point; current: Point } | null>(null);
  const bounds = useMemo(() => boardBounds(outline, components), [outline, components]);
  const visibleComponents = useMemo(
    () => components.filter((component) => side === "both" || component.side === side),
    [components, side],
  );
  const highlighted = useMemo(() => normalizeRefs(highlightedRefs), [highlightedRefs]);

  function eventToViewPoint(clientX: number, clientY: number): Point {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return { x: bounds.x, y: bounds.y };
    return {
      x: bounds.x + ((clientX - rect.left) / rect.width) * bounds.width,
      y: bounds.y + ((clientY - rect.top) / rect.height) * bounds.height,
    };
  }

  function eventToBoardPoint(clientX: number, clientY: number): Point {
    const point = eventToViewPoint(clientX, clientY);
    return {
      x: (point.x - transform.tx) / transform.scale,
      y: (point.y - transform.ty) / transform.scale,
    };
  }

  function handleWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const focus = eventToViewPoint(event.clientX, event.clientY);
    setTransform((current) => {
      const nextScale = Math.min(20, Math.max(0.25, current.scale * Math.exp(-event.deltaY * 0.0015)));
      const ratio = nextScale / current.scale;
      return {
        scale: nextScale,
        tx: focus.x - (focus.x - current.tx) * ratio,
        ty: focus.y - (focus.y - current.ty) * ratio,
      };
    });
  }

  function handleMouseDown(event: ReactMouseEvent<SVGSVGElement>) {
    if (event.button === 1 || (event.button === 0 && event.altKey)) {
      gestureRef.current = { mode: "pan", clientX: event.clientX, clientY: event.clientY };
      return;
    }
    if (event.button !== 0) return;
    const point = eventToBoardPoint(event.clientX, event.clientY);
    gestureRef.current = { mode: "frame", start: point, current: point };
    setFrame({ start: point, current: point });
  }

  function handleMouseMove(event: ReactMouseEvent<SVGSVGElement>) {
    const gesture = gestureRef.current;
    if (!gesture) return;
    if (gesture.mode === "pan") {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect?.width || !rect.height) return;
      const dx = ((event.clientX - gesture.clientX) / rect.width) * bounds.width;
      const dy = ((event.clientY - gesture.clientY) / rect.height) * bounds.height;
      gestureRef.current = { mode: "pan", clientX: event.clientX, clientY: event.clientY };
      setTransform((current) => ({ ...current, tx: current.tx + dx, ty: current.ty + dy }));
      return;
    }
    const current = eventToBoardPoint(event.clientX, event.clientY);
    gestureRef.current = { ...gesture, current };
    setFrame({ start: gesture.start, current });
  }

  function handleMouseUp(event: ReactMouseEvent<SVGSVGElement>) {
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.mode !== "frame") return;
    const current = eventToBoardPoint(event.clientX, event.clientY);
    const minX = Math.min(gesture.start.x, current.x);
    const maxX = Math.max(gesture.start.x, current.x);
    const minY = Math.min(gesture.start.y, current.y);
    const maxY = Math.max(gesture.start.y, current.y);
    const refs = visibleComponents
      .filter((component) => component.x_mm >= minX && component.x_mm <= maxX && component.y_mm >= minY && component.y_mm <= maxY)
      .map((component) => component.ref);
    setFrame(null);
    onFrameSelect?.(refs);
  }

  const frameRect = frame
    ? {
        x: Math.min(frame.start.x, frame.current.x),
        y: Math.min(frame.start.y, frame.current.y),
        width: Math.abs(frame.current.x - frame.start.x),
        height: Math.abs(frame.current.y - frame.start.y),
      }
    : null;

  return (
    <div className={styles.root} data-color-scheme={colorScheme}>
      <svg
        ref={svgRef}
        className={styles.svg}
        viewBox={`${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="PCB 布局视图"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          gestureRef.current = null;
          setFrame(null);
          onHover?.(null);
        }}
      >
        <defs>
          <filter id="pcb-component-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feDropShadow dx="0" dy="0" stdDeviation="0.9" floodColor="#1677ff" floodOpacity="0.95" />
          </filter>
        </defs>
        <g data-testid="pcb-transform" transform={`matrix(${transform.scale} 0 0 ${transform.scale} ${transform.tx} ${transform.ty})`}>
          {outline.map((ring, index) => (
            <polygon
              key={index}
              className={styles.outline}
              points={ring.map(([x, y]) => `${x},${y}`).join(" ")}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {visibleComponents.map((component) => {
            const isHighlighted = highlighted.has(component.ref.toUpperCase());
            const className = [
              "pcb-comp",
              styles.component,
              componentStatusClass(component),
              component.high_risk ? styles.highRisk : "",
              side === "both" && component.side === "bottom" ? styles.bottom : "",
              isHighlighted ? `pcb-comp--highlight ${styles.highlighted}` : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <rect
                key={component.ref}
                data-ref={component.ref}
                data-side={component.side}
                data-status={component.status}
                className={className}
                x={component.x_mm - 0.5}
                y={component.y_mm - 0.5}
                width={1}
                height={1}
                rx={0.12}
                transform={`rotate(${component.rotation} ${component.x_mm} ${component.y_mm})`}
                vectorEffect="non-scaling-stroke"
                onMouseDown={(event) => event.stopPropagation()}
                onMouseEnter={() => onHover?.(component.ref)}
                onMouseLeave={() => onHover?.(null)}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect?.(component.ref);
                }}
              >
                <title>{`${component.ref} · ${component.footprint || "未知封装"}`}</title>
              </rect>
            );
          })}
          {frameRect ? <rect className={styles.frame} {...frameRect} vectorEffect="non-scaling-stroke" /> : null}
        </g>
      </svg>
    </div>
  );
}
