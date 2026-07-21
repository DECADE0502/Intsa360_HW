import { useMemo, useState } from "react";
import { Empty, Typography } from "antd";


export type RefdesListItem = {
  ref: string;
  part_number: string;
  description: string;
  side: "top" | "bottom";
  high_risk?: boolean;
};

type RefdesVirtualListProps = {
  items: RefdesListItem[];
  selectedRef?: string;
  onHover?: (ref: string | null) => void;
  onSelect?: (ref: string) => void;
  height?: number;
};

const ROW_HEIGHT = 52;
const WINDOW_SIZE = 60;


export function RefdesVirtualList({
  items,
  selectedRef = "",
  onHover,
  onSelect,
  height = 468,
}: RefdesVirtualListProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 10);
  const visible = useMemo(() => items.slice(start, start + WINDOW_SIZE), [items, start]);

  if (!items.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有 NC 位号" />;
  }

  return (
    <div
      role="list"
      aria-label="NC 位号列表"
      style={{ height, overflowY: "auto", position: "relative" }}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      <div style={{ height: items.length * ROW_HEIGHT, position: "relative" }}>
        {visible.map((item, offset) => {
          const selected = item.ref === selectedRef;
          return (
            <button
              key={item.ref}
              type="button"
              role="listitem"
              data-testid={`nc-row-${item.ref}`}
              data-selected={selected ? "true" : "false"}
              onMouseEnter={() => onHover?.(item.ref)}
              onMouseLeave={() => onHover?.(null)}
              onClick={() => onSelect?.(item.ref)}
              style={{
                position: "absolute",
                top: (start + offset) * ROW_HEIGHT,
                left: 0,
                right: 0,
                height: ROW_HEIGHT - 4,
                display: "grid",
                gridTemplateColumns: "64px minmax(0, 1fr) 46px",
                alignItems: "center",
                gap: 8,
                padding: "0 10px",
                border: selected ? "1px solid #91caff" : "1px solid transparent",
                borderBottomColor: selected ? "#91caff" : "#edf0f3",
                borderRadius: 4,
                background: selected ? "#eaf4ff" : "transparent",
                color: "inherit",
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <Typography.Text strong>{item.ref}</Typography.Text>
              <span style={{ minWidth: 0 }}>
                <Typography.Text ellipsis style={{ display: "block", fontSize: 12 }}>
                  {item.part_number || "无料号"}
                </Typography.Text>
                <Typography.Text type="secondary" ellipsis style={{ display: "block", fontSize: 11 }}>
                  {item.description || "无描述"}
                </Typography.Text>
              </span>
              <Typography.Text type="secondary" style={{ fontSize: 11, textAlign: "right" }}>
                {item.side === "top" ? "正面" : "背面"}
              </Typography.Text>
            </button>
          );
        })}
      </div>
    </div>
  );
}
