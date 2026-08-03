import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Checkbox, Empty, Tag, Typography } from "antd";

import type { SmtPlacement } from "./types";
import { SMT_STATE_LABELS } from "./labels";
import styles from "./SmtAnalysisPane.module.css";


const ROW_HEIGHT = 66;
const OVERSCAN = 8;

function stateColor(placement: SmtPlacement) {
  if (placement.assembly_state === "conflicting") return "red";
  if (placement.assembly_state === "candidate_nc") return "gold";
  if (placement.assembly_state === "installed") return "green";
  if (placement.assembly_state === "non_smt") return "default";
  return "blue";
}

export function SmtPlacementVirtualList({
  items,
  selectedRef,
  selectedIds = new Set<string>(),
  onSelect,
  onCheck,
  showCheckbox = true,
}: {
  items: SmtPlacement[];
  selectedRef?: string;
  selectedIds?: Set<string>;
  onSelect: (placement: SmtPlacement) => void;
  onCheck?: (placementId: string, checked: boolean) => void;
  showCheckbox?: boolean;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(520);
  const range = useMemo(() => {
    const start = Math.max(
      0,
      Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN,
    );
    const count =
      Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
    return {
      start,
      visible: items.slice(start, start + count),
    };
  }, [items, scrollTop, viewportHeight]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const sync = () =>
      setViewportHeight(Math.max(240, viewport.clientHeight || 520));
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!selectedRef) return;
    const index = items.findIndex((item) => item.ref === selectedRef);
    const viewport = viewportRef.current;
    if (index < 0 || !viewport) return;
    const rowTop = index * ROW_HEIGHT;
    const rowBottom = rowTop + ROW_HEIGHT;
    if (
      rowTop < viewport.scrollTop ||
      rowBottom > viewport.scrollTop + viewport.clientHeight
    ) {
      viewport.scrollTop = Math.max(0, rowTop - ROW_HEIGHT * 2);
    }
  }, [items, selectedRef]);

  if (!items.length) {
    return (
      <div className={styles.virtualListEmpty}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="当前筛选下没有位号"
        />
      </div>
    );
  }

  return (
    <div
      ref={viewportRef}
      role="listbox"
      aria-label="SMT 位号与异常列表"
      className={styles.virtualList}
      onScroll={(event) =>
        setScrollTop(event.currentTarget.scrollTop)
      }
    >
      <div
        className={styles.virtualListTrack}
        style={{ height: items.length * ROW_HEIGHT }}
      >
        {range.visible.map((placement, offset) => {
          const primary = placement.bom_requirement?.materials.find(
            (item) => item.is_primary,
          );
          return (
            <div
              role="option"
              aria-selected={placement.ref === selectedRef}
              tabIndex={0}
              className={styles.placementRow}
              data-checkbox={showCheckbox}
              data-testid={`smt-placement-${placement.ref}`}
              data-selected={placement.ref === selectedRef}
              key={placement.placement_id}
              style={{ top: (range.start + offset) * ROW_HEIGHT }}
              onClick={() => onSelect(placement)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(placement);
                }
              }}
            >
              {showCheckbox ? (
                <Checkbox
                  aria-label={`选择 ${placement.ref}`}
                  checked={selectedIds.has(placement.placement_id)}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) =>
                    onCheck?.(
                      placement.placement_id,
                      event.target.checked,
                    )
                  }
                />
              ) : null}
              <span className={styles.placementIdentity}>
                <Typography.Text strong ellipsis>
                  {placement.ref}
                </Typography.Text>
                <Typography.Text type="secondary" ellipsis>
                  {primary?.part_number || "无 BOM 料号"}
                </Typography.Text>
              </span>
              <Tag color={stateColor(placement)}>
                {SMT_STATE_LABELS[placement.assembly_state]}
              </Tag>
            </div>
          );
        })}
      </div>
    </div>
  );
}
