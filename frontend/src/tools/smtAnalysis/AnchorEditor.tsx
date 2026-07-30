import { useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import {
  Button,
  Empty,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { DeleteOutlined, UndoOutlined } from "@ant-design/icons";

import type {
  SmtCoordinateOccurrence,
  SmtDrawingPage,
  SmtRegistrationAnchor,
} from "./types";
import styles from "./SmtAnalysisPane.module.css";


type AnchorEditorProps = {
  page: SmtDrawingPage;
  occurrences: SmtCoordinateOccurrence[];
  anchors: SmtRegistrationAnchor[];
  onChange: (anchors: SmtRegistrationAnchor[]) => void;
};

export function AnchorEditor({
  page,
  occurrences,
  anchors,
  onChange,
}: AnchorEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedRef, setSelectedRef] = useState("");
  const usable = useMemo(
    () =>
      occurrences.filter(
        (item) => item.normalized_x != null && item.normalized_y != null,
      ),
    [occurrences],
  );
  const byRef = useMemo(
    () => new Map(usable.map((item) => [item.ref, item])),
    [usable],
  );
  const anchoredRefs = new Set(anchors.map((anchor) => anchor.ref));

  function addAt(event: ReactMouseEvent<SVGSVGElement>) {
    const occurrence = byRef.get(selectedRef);
    const rect = svgRef.current?.getBoundingClientRect();
    if (
      !occurrence ||
      !rect?.width ||
      !rect.height ||
      !page.pixel_width ||
      !page.pixel_height ||
      occurrence.normalized_x == null ||
      occurrence.normalized_y == null
    ) {
      return;
    }
    const imageX =
      ((event.clientX - rect.left) / rect.width) * page.pixel_width;
    const imageY =
      ((event.clientY - rect.top) / rect.height) * page.pixel_height;
    const next: SmtRegistrationAnchor = {
      anchor_id: `anchor-${selectedRef}`,
      ref: selectedRef,
      coordinate_x: occurrence.normalized_x,
      coordinate_y: occurrence.normalized_y,
      image_x: imageX,
      image_y: imageY,
      source: "user",
      inlier: true,
    };
    onChange([...anchors.filter((item) => item.ref !== selectedRef), next]);
    const nextRef = usable.find((item) => !anchoredRefs.has(item.ref));
    setSelectedRef(nextRef?.ref || selectedRef);
  }

  if (!page.preview_url || !page.pixel_width || !page.pixel_height) {
    return <Empty description="页面预览不可用" />;
  }

  return (
    <>
      <div className={styles.anchorPanel}>
        <Typography.Text strong>1. 选择一个清晰位号</Typography.Text>
        <Select
          showSearch
          aria-label="选择校准位号"
          value={selectedRef || undefined}
          placeholder="搜索位号"
          style={{ width: "100%", marginTop: 7 }}
          optionFilterProp="label"
          options={usable.map((item) => ({
            value: item.ref,
            label: `${item.ref}${item.footprint ? ` · ${item.footprint}` : ""}`,
          }))}
          onChange={setSelectedRef}
        />
        <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0" }}>
          2. 在右侧位号图上点击同一个位号的中心。至少选择三个分散位置。
        </Typography.Paragraph>
        <div className={styles.anchorList}>
          {anchors.map((anchor, index) => (
            <div className={styles.anchorRow} key={anchor.anchor_id}>
              <span>
                <Tag color="blue">{index + 1}</Tag>
                <Typography.Text strong>{anchor.ref}</Typography.Text>
                <br />
                <Typography.Text type="secondary">
                  图像 ({anchor.image_x.toFixed(1)}, {anchor.image_y.toFixed(1)})
                </Typography.Text>
              </span>
              <Button
                aria-label={`删除锚点 ${anchor.ref}`}
                icon={<DeleteOutlined />}
                onClick={() =>
                  onChange(
                    anchors.filter(
                      (candidate) => candidate.anchor_id !== anchor.anchor_id,
                    ),
                  )
                }
              />
            </div>
          ))}
          {!anchors.length ? (
            <Typography.Text type="secondary">尚未添加锚点</Typography.Text>
          ) : null}
        </div>
        <Space>
          <Button
            icon={<UndoOutlined />}
            disabled={!anchors.length}
            onClick={() => onChange(anchors.slice(0, -1))}
          >
            撤销
          </Button>
          <Button disabled={!anchors.length} onClick={() => onChange([])}>
            清空
          </Button>
        </Space>
      </div>
      <div className={styles.calibrationCanvas}>
        <svg
          ref={svgRef}
          className={styles.calibrationImage}
          viewBox={`0 0 ${page.pixel_width} ${page.pixel_height}`}
          role="img"
          aria-label="位号图锚点编辑器"
          onClick={addAt}
        >
          <image
            href={page.preview_url}
            x={0}
            y={0}
            width={page.pixel_width}
            height={page.pixel_height}
          />
          {anchors.map((anchor, index) => (
            <g
              key={anchor.anchor_id}
              transform={`translate(${anchor.image_x} ${anchor.image_y})`}
              pointerEvents="none"
            >
              <circle r={9} fill="#1677ff" stroke="#fff" strokeWidth={2} />
              <text
                y={3.5}
                textAnchor="middle"
                fill="#fff"
                fontSize={10}
              >
                {index + 1}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </>
  );
}
