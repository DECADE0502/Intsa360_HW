import { Empty, Table, Tag } from "antd";
import type { MetadataDiff as MetadataDiffType } from "./types";

function compact(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function MetadataDiff({ rows }: { rows: MetadataDiffType[] }) {
  if (!rows.length) return <Empty description="名称、型号、描述和等级没有变化" />;
  return (
    <Table
      className="bom-layer-table"
      size="small"
      rowKey={(row) => `${row.parent_code}:${row.material_code}`}
      dataSource={rows}
      pagination={{ pageSize: 12 }}
      scroll={{ x: 1180 }}
      columns={[
        { title: "父项", dataIndex: "parent_code", width: 170, fixed: "left" },
        {
          title: "物料编码",
          dataIndex: "material_code",
          width: 190,
          fixed: "left",
          render: (value) => <Tag>{value}</Tag>,
        },
        {
          title: "旧版属性",
          dataIndex: "old_variants",
          width: 400,
          render: (value) => <pre className="bom-variant-json">{compact(value)}</pre>,
        },
        {
          title: "新版属性",
          dataIndex: "new_variants",
          width: 400,
          render: (value) => <pre className="bom-variant-json">{compact(value)}</pre>,
        },
        {
          title: "影响",
          width: 140,
          render: () => <Tag color="default">非贴装字段</Tag>,
        },
      ]}
    />
  );
}

