import { Button, Checkbox, Popconfirm, Space, Typography } from "antd";

import type { PlacementDecisionInput } from "./api";
import type { SmtPlacement } from "./types";
import styles from "./SmtAnalysisPane.module.css";


export function DecisionBar({
  visible,
  selected,
  busy,
  onSelectAll,
  onApply,
}: {
  visible: SmtPlacement[];
  selected: Set<string>;
  busy: boolean;
  onSelectAll: (checked: boolean) => void;
  onApply: (input: PlacementDecisionInput) => void;
}) {
  const selectedRows = visible.filter((item) =>
    selected.has(item.placement_id),
  );
  const homogeneous =
    selectedRows.length > 0 &&
    new Set(selectedRows.map((item) => item.assembly_state)).size === 1;
  const safeBatch =
    homogeneous &&
    selectedRows.every(
      (item) => item.assembly_state !== "conflicting",
    );
  return (
    <div className={styles.decisionBar}>
      <Space>
        <Checkbox
          checked={Boolean(visible.length) && selected.size === visible.length}
          indeterminate={selected.size > 0 && selected.size < visible.length}
          onChange={(event) => onSelectAll(event.target.checked)}
        >
          当前筛选全部
        </Checkbox>
        <Typography.Text type="secondary">
          已选 {selectedRows.length} 项
        </Typography.Text>
      </Space>
      <Space wrap>
        <Popconfirm
          title={`将当前选择的 ${selectedRows.length} 个位号确认为装机`}
          description="批量操作只作用于当前明确选中的同类结果。"
          disabled={!safeBatch}
          onConfirm={() =>
            onApply({
              action: "confirm_installed",
              reason: "批量人工确认装机",
            })
          }
        >
          <Button disabled={!safeBatch} loading={busy}>
            批量确认装机
          </Button>
        </Popconfirm>
        <Popconfirm
          title={`将当前选择的 ${selectedRows.length} 个位号确认为 NC`}
          description="请确认坐标范围足以支持该结论。"
          disabled={!safeBatch}
          onConfirm={() =>
            onApply({ action: "confirm_nc", reason: "批量人工确认 NC" })
          }
        >
          <Button danger disabled={!safeBatch} loading={busy}>
            批量确认 NC
          </Button>
        </Popconfirm>
      </Space>
    </div>
  );
}
