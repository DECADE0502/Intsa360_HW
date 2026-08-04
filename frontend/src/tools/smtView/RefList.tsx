import { useEffect, useMemo, useRef, useState } from "react";
import { Empty, Input, Segmented, Tag, Typography } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { Placement, PlacementStatus } from "./types";
import styles from "./smtView.module.css";

const ROW_HEIGHT = 52;
const OVERSCAN = 8;
const statusLabel: Record<PlacementStatus, string> = {
  placed: "贴装",
  nc: "NC",
  non_smt: "非贴片",
  bom_only: "仅 BOM",
  xy_only: "仅坐标",
};

export function parseRefQuery(value: string) {
  return Array.from(
    new Set(value.split(/[,，;；\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)),
  );
}

export function RefList({
  placements,
  selectedRef,
  onSelect,
  onQueryRefs,
}: {
  placements: Placement[];
  selectedRef: string;
  onSelect: (ref: string) => void;
  onQueryRefs: (refs: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | PlacementStatus>("all");
  const [scrollTop, setScrollTop] = useState(0);
  const viewportRef = useRef<HTMLDivElement>(null);
  const queryRefs = useMemo(() => parseRefQuery(query), [query]);
  const counts = useMemo(() => {
    const result: Record<string, number> = { all: placements.length };
    placements.forEach((item) => { result[item.status] = (result[item.status] || 0) + 1; });
    return result;
  }, [placements]);
  const filtered = useMemo(() => {
    return placements.filter((item) => {
      if (filter !== "all" && item.status !== filter) return false;
      if (!queryRefs.length) return true;
      return queryRefs.some((token) => item.ref.includes(token) || item.material_code.toUpperCase().includes(token));
    });
  }, [filter, placements, queryRefs]);
  const height = 520;
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visible = filtered.slice(start, start + Math.ceil(height / ROW_HEIGHT) + OVERSCAN * 2);

  useEffect(() => { onQueryRefs(queryRefs); }, [queryRefs, onQueryRefs]);
  useEffect(() => {
    if (!selectedRef || !viewportRef.current) return;
    const index = filtered.findIndex((item) => item.ref === selectedRef);
    if (index < 0) return;
    const top = index * ROW_HEIGHT;
    const viewport = viewportRef.current;
    if (top < viewport.scrollTop || top + ROW_HEIGHT > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTo({ top: Math.max(0, top - ROW_HEIGHT * 2), behavior: "smooth" });
    }
  }, [filtered, selectedRef]);

  return (
    <section className={styles.listPane}>
      <div className={styles.listHeader}>
        <Typography.Text strong>位号</Typography.Text>
        <Typography.Text type="secondary">{filtered.length} / {placements.length}</Typography.Text>
      </div>
      <Input
        allowClear
        prefix={<SearchOutlined />}
        value={query}
        placeholder="位号或料号，支持逗号分隔"
        onChange={(event) => setQuery(event.target.value)}
      />
      <Segmented
        block
        size="small"
        value={filter}
        onChange={(value) => setFilter(value as typeof filter)}
        options={[
          { value: "all", label: `全部 ${counts.all || 0}` },
          { value: "nc", label: `NC ${counts.nc || 0}` },
          { value: "xy_only", label: `异常 ${counts.xy_only || 0}` },
        ]}
      />
      {filtered.length ? (
        <div
          ref={viewportRef}
          className={styles.listViewport}
          style={{ height }}
          role="listbox"
          aria-label="贴片位号列表"
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
          <div className={styles.listTrack} style={{ height: filtered.length * ROW_HEIGHT }}>
            {visible.map((item, index) => (
              <button
                type="button"
                key={item.ref}
                className={`${styles.listRow} ${item.ref === selectedRef ? styles.listRowSelected : ""}`}
                style={{ top: (start + index) * ROW_HEIGHT }}
                onClick={() => onSelect(item.ref)}
              >
                <span><strong>{item.ref}</strong><small>{item.material_code || item.footprint || "无物料信息"}</small></span>
                <Tag color={item.status === "nc" ? "red" : item.status === "placed" ? "green" : "default"}>
                  {statusLabel[item.status]}
                </Tag>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配位号" />
      )}
    </section>
  );
}
