import { Empty, Table, Tag } from "antd";
import type { SubstituteDiff as SubstituteDiffType, SubstituteSnapshot } from "./types";

function groupCode(row: SubstituteDiffType) {
  return row.new.group_code || row.old.group_code || "";
}

function relation(snapshot: SubstituteSnapshot) {
  const main = snapshot.main_material_code || "无主料";
  const alternatives = snapshot.alternative_material_codes || [];
  return [main, ...alternatives].join(" / ");
}

function priorities(snapshot: SubstituteSnapshot) {
  return Object.entries(snapshot.priorities || {})
    .sort((left, right) => Number(left[1]) - Number(right[1]))
    .map(([code, priority]) => `${priority}:${code}`)
    .join(" · ");
}

export function SubstituteDiff({ rows }: { rows: SubstituteDiffType[] }) {
  if (!rows.length) return <Empty description="替代关系没有变化" />;
  return (
    <Table
      className="bom-layer-table"
      size="small"
      rowKey={(row) => `${row.status}:${groupCode(row)}`}
      dataSource={rows}
      pagination={{ pageSize: 12, showSizeChanger: true }}
      scroll={{ x: 1180 }}
      columns={[
        {
          title: "状态",
          dataIndex: "status",
          width: 96,
          fixed: "left",
          render: (value: SubstituteDiffType["status"]) => (
            <Tag color={value === "added" ? "blue" : value === "removed" ? "orange" : "gold"}>
              {value === "added" ? "新增" : value === "removed" ? "删除" : "变更"}
            </Tag>
          ),
        },
        { title: "父项", width: 150, render: (_, row) => row.new.parent_code || row.old.parent_code },
        { title: "替代组编码", width: 180, render: (_, row) => groupCode(row) },
        { title: "旧版关系", width: 270, render: (_, row) => relation(row.old) },
        { title: "新版关系", width: 270, render: (_, row) => relation(row.new) },
        { title: "旧优先级", width: 260, render: (_, row) => priorities(row.old) || "-" },
        { title: "新优先级", width: 260, render: (_, row) => priorities(row.new) || "-" },
        {
          title: "实际位号",
          width: 260,
          render: (_, row) => (row.new.references || row.old.references || []).join(", ") || "-",
        },
      ]}
    />
  );
}

