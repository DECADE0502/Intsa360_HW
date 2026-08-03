import { useEffect, useMemo, useRef, useState } from "react";
import { Empty, Input, Tag, Typography } from "antd";
import { SearchOutlined } from "@ant-design/icons";

import type { RefdesEntry } from "./types";
import styles from "./RefdesViewer.module.css";


const ROW_HEIGHT = 40;
const OVERSCAN = 10;

export function RefdesList({
  entries,
  selectedRef,
  occurrenceIndex,
  onSelect,
}: {
  entries: RefdesEntry[];
  selectedRef: string;
  /** Which occurrence of the selected refdes is currently shown. */
  occurrenceIndex: number;
  onSelect: (ref: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(560);
  const viewportRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    const query = search.trim().toUpperCase();
    if (!query) return entries;
    return entries.filter((entry) => entry.ref.includes(query));
  }, [entries, search]);

  const range = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const count = Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
    return { start, visible: items.slice(start, start + count) };
  }, [items, scrollTop, viewportHeight]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const sync = () =>
      setViewportHeight(Math.max(240, viewport.clientHeight || 560));
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  // Keep the selected row visible when the selection comes from the drawing.
  useEffect(() => {
    if (!selectedRef) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const index = items.findIndex((entry) => entry.ref === selectedRef);
    if (index < 0) return;
    const top = index * ROW_HEIGHT;
    const bottom = top + ROW_HEIGHT;
    if (top < viewport.scrollTop) {
      viewport.scrollTop = Math.max(0, top - ROW_HEIGHT * 2);
    } else if (bottom > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTop = bottom - viewport.clientHeight + ROW_HEIGHT * 2;
    }
  }, [items, selectedRef]);

  function move(step: number) {
    if (!items.length) return;
    const current = items.findIndex((entry) => entry.ref === selectedRef);
    const next = Math.min(
      items.length - 1,
      Math.max(0, (current < 0 ? 0 : current) + step),
    );
    onSelect(items[next].ref);
  }

  return (
    <section className={styles.listRoot} data-testid="refdes-list">
      <div className={styles.listHeader}>
        <Typography.Text strong>位号</Typography.Text>
        <Tag>{entries.length}</Tag>
        <Typography.Text type="secondary" className={styles.listHint}>
          点击定位
        </Typography.Text>
      </div>
      <Input
        allowClear
        size="small"
        prefix={<SearchOutlined />}
        aria-label="搜索位号"
        placeholder="搜索位号"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            move(1);
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            move(-1);
          }
        }}
      />
      {items.length ? (
        <div
          ref={viewportRef}
          className={styles.listViewport}
          role="listbox"
          aria-label="位号列表"
          tabIndex={0}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              move(1);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              move(-1);
            } else if (event.key === "Enter" && selectedRef) {
              event.preventDefault();
              onSelect(selectedRef);
            }
          }}
        >
          <div
            className={styles.listTrack}
            style={{ height: items.length * ROW_HEIGHT }}
          >
            {range.visible.map((entry, offset) => {
              const selected = entry.ref === selectedRef;
              const total = entry.occurrences.length;
              return (
                <div
                  key={entry.ref}
                  role="option"
                  aria-selected={selected}
                  data-testid={`refdes-row-${entry.ref}`}
                  data-selected={selected}
                  className={styles.listRow}
                  style={{ top: (range.start + offset) * ROW_HEIGHT }}
                  onClick={() => onSelect(entry.ref)}
                >
                  <span className={styles.listRef}>{entry.ref}</span>
                  {total > 1 ? (
                    <span className={styles.listBadge}>
                      {selected ? `${occurrenceIndex + 1}/${total}` : `×${total}`}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className={styles.listEmpty}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={entries.length ? "没有匹配的位号" : "这一页没有位号"}
          />
        </div>
      )}
      <div className={styles.listFooter}>
        <Typography.Text type="secondary">
          显示 {items.length} 个
        </Typography.Text>
      </div>
    </section>
  );
}
