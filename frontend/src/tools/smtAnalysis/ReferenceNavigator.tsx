import { useMemo, useState } from "react";
import { Input, Segmented, Space, Tag, Typography } from "antd";
import { SearchOutlined } from "@ant-design/icons";

import type {
  SmtAnalysisRunResponse,
  SmtPlacement,
} from "./types";
import { SmtPlacementVirtualList } from "./SmtPlacementVirtualList";
import styles from "./SmtAnalysisPane.module.css";


const NC_STATES = new Set(["confirmed_nc", "candidate_nc"]);
const EMPTY_SELECTION = new Set<string>();

function naturalCompare(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function ReferenceNavigator({
  run,
  selectedRef,
  onSelect,
}: {
  run: SmtAnalysisRunResponse;
  selectedRef?: string;
  onSelect: (placement: SmtPlacement) => void;
}) {
  const ncCount = run.placements.filter((item) =>
    NC_STATES.has(item.assembly_state),
  ).length;
  const nonNcCount = run.placements.length - ncCount;
  const [category, setCategory] = useState<"nc" | "non_nc">(
    ncCount ? "nc" : "non_nc",
  );
  const [search, setSearch] = useState("");
  const items = useMemo(() => {
    const query = search.trim().toUpperCase();
    return run.placements
      .filter((item) =>
        category === "nc"
          ? NC_STATES.has(item.assembly_state)
          : !NC_STATES.has(item.assembly_state),
      )
      .filter((item) => {
        if (!query) return true;
        const material =
          item.bom_requirement?.materials
            .map((candidate) => candidate.part_number)
            .join(" ") || "";
        return `${item.ref} ${material}`.toUpperCase().includes(query);
      })
      .sort((left, right) => naturalCompare(left.ref, right.ref));
  }, [category, run.placements, search]);

  return (
    <section
      className={styles.referenceNavigator}
      data-testid="smt-reference-navigator"
    >
      <div className={styles.panelHeader}>
        <Space size={8}>
          <Typography.Text strong>位号</Typography.Text>
          <Tag>{run.placements.length}</Tag>
        </Space>
        <Typography.Text type="secondary">点击后右侧定位</Typography.Text>
      </div>
      <div className={styles.referenceControls}>
        <Segmented
          block
          value={category}
          options={[
            { label: `NC ${ncCount}`, value: "nc" },
            { label: `非 NC ${nonNcCount}`, value: "non_nc" },
          ]}
          onChange={(value) => setCategory(value as "nc" | "non_nc")}
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          aria-label="搜索位号"
          placeholder="搜索位号或料号"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      <SmtPlacementVirtualList
        items={items}
        selectedRef={selectedRef}
        selectedIds={EMPTY_SELECTION}
        showCheckbox={false}
        onSelect={onSelect}
      />
      <div className={styles.referenceFooter}>
        <Typography.Text type="secondary">
          当前显示 {items.length} 个位号
        </Typography.Text>
      </div>
    </section>
  );
}
