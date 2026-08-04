import { useEffect, useMemo, useRef, useState } from "react";
import { Empty, Input, Tag, Typography } from "antd";
import { SearchOutlined } from "@ant-design/icons";

import type { RefdesEntry } from "./types";
import styles from "./RefdesViewer.module.css";


const ROW_HEIGHT = 38;
const OVERSCAN = 10;

export function RefdesList({
  entries,
  selectedRef,
  markIndex,
  onSelect,
}: {
  entries: RefdesEntry[];
  selectedRef: string;
  /** Which printed instance of the selected refdes is showing. */
  markIndex: number;
  onSelect: (ref: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(560);
  const viewportRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    const query = search.trim().toUpperCase();
    return query ? entries.filter((entry) => entry.ref.includes(query)) : entries;
  }, [entries, search]);

  const window = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const count = Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
    return { start, rows: items.slice(start, start + count) };
  }, [items, scrollTop, viewportHeight]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const sync = () => setViewportHeight(Math.max(240, viewport.clientHeight || 560));
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  // Keep the selected row on screen when the pick came from the drawing.
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

  function step(delta: number) {
    if (!items.length) return;
    const current = items.findIndex((entry) => entry.ref === selectedRef);
    const next = Math.min(
      items.length - 1,
      Math.max(0, (current < 0 ? 0 : current) + delta),
    );
    onSelect(items[next].ref);
  }

  function handleKeys(event: { key: string; preventDefault: () => void }) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "Enter" && selectedRef) {
      event.preventDefault();
      onSelect(selectedRef);
    }
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
        onKeyDown={handleKeys}
      />
      {items.length ? (
        <div
          ref={viewportRef}
          className={styles.listViewport}
          role="listbox"
          aria-label="位号列表"
          tabIndex={0}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          onKeyDown={handleKeys}
        >
          <div className={styles.listTrack} style={{ height: items.length * ROW_HEIGHT }}>
            {window.rows.map((entry, offset) => {
              const isSelected = entry.ref === selectedRef;
              const total = entry.marks.length;
              return (
                <div
                  key={entry.ref}
                  role="option"
                  aria-selected={isSelected}
                  data-testid={`refdes-row-${entry.ref}`}
                  data-selected={isSelected}
                  className={styles.listRow}
                  style={{ top: (window.start + offset) * ROW_HEIGHT }}
                  onClick={() => onSelect(entry.ref)}
                >
                  <span className={styles.listRef}>{entry.ref}</span>
                  {total > 1 ? (
                    <span className={styles.listBadge}>
                      {isSelected ? `${markIndex + 1}/${total}` : `×${total}`}
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
        <Typography.Text type="secondary">显示 {items.length} 个</Typography.Text>
      </div>
    </section>
  );
}
