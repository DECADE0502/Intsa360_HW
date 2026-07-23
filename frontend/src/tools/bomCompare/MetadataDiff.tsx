import { Empty, Table, Tag } from "antd";
import type {
  BoardMetadataDiff,
  MetadataDiff as MetadataDiffType,
} from "./types";

function compact(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const fieldLabels: Record<string, string> = {
  parent_code: "父项编码",
  parent_description: "父项描述",
  hardware_version: "硬件版本",
  name: "名称",
  value: "Value",
  model: "型号",
  description: "物料描述",
  unit: "单位",
  remark: "备注",
  grade: "物料优选等级",
  grade_remark: "优选等级备注",
  issue_method: "发料方式",
  mrp: "参与 MRP",
  jump_level: "是否跳层",
  extra_fields: "扩展字段",
};

function fieldTags(fields: string[] = []) {
  return fields.length
    ? fields.map((field) => <Tag key={field}>{fieldLabels[field] || field}</Tag>)
    : <span>-</span>;
}

export function MetadataDiff({
  rows,
  boardRows = [],
}: {
  rows: MetadataDiffType[];
  boardRows?: BoardMetadataDiff[];
}) {
  if (!rows.length && !boardRows.length) {
    return <Empty description="板级信息和普通字段没有变化" />;
  }
  return (
    <div className="bom-metadata-layers">
      {boardRows.length ? (
        <section>
          <h3>板级信息</h3>
          <Table
            className="bom-layer-table"
            size="small"
            rowKey="comparison_parent_code"
            dataSource={boardRows}
            pagination={false}
            scroll={{ x: 980 }}
            columns={[
              { title: "比较范围", dataIndex: "comparison_parent_code", width: 190 },
              {
                title: "变化字段",
                dataIndex: "changed_fields",
                width: 260,
                render: fieldTags,
              },
              {
                title: "旧版",
                dataIndex: "old",
                width: 260,
                render: (value) => <pre className="bom-variant-json">{compact(value)}</pre>,
              },
              {
                title: "新版",
                dataIndex: "new",
                width: 260,
                render: (value) => <pre className="bom-variant-json">{compact(value)}</pre>,
              },
            ]}
          />
        </section>
      ) : null}
      {rows.length ? (
        <section>
          <h3>物料普通字段</h3>
          <Table
            className="bom-layer-table"
            size="small"
            rowKey={(row) => `${row.parent_code}:${row.material_code}`}
            dataSource={rows}
            pagination={{ pageSize: 12 }}
            scroll={{ x: 1500 }}
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
                title: "变化字段",
                dataIndex: "changed_fields",
                width: 260,
                render: fieldTags,
              },
              {
                title: "旧版属性",
                width: 400,
                render: (_, row) => (
                  <pre className="bom-variant-json">
                    {compact({
                      variants: row.old_variants,
                      metadata: row.old_metadata,
                    })}
                  </pre>
                ),
              },
              {
                title: "新版属性",
                width: 400,
                render: (_, row) => (
                  <pre className="bom-variant-json">
                    {compact({
                      variants: row.new_variants,
                      metadata: row.new_metadata,
                    })}
                  </pre>
                ),
              },
              {
                title: "影响",
                width: 140,
                render: () => <Tag color="default">非贴装字段</Tag>,
              },
            ]}
          />
        </section>
      ) : null}
    </div>
  );
}
