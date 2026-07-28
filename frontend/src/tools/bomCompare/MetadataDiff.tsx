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

function variantValue(
  row: MetadataDiffType,
  side: "old" | "new",
  field: string,
) {
  const metadata = side === "old" ? row.old_metadata : row.new_metadata;
  if (metadata && field in metadata) return metadata[field];
  const variants = side === "old" ? row.old_variants : row.new_variants;
  return variants?.[0]?.[field];
}

function FieldChanges({
  fields,
  oldValue,
  newValue,
}: {
  fields: string[];
  oldValue: (field: string) => unknown;
  newValue: (field: string) => unknown;
}) {
  return (
    <dl className="bom-field-change-list">
      {fields.map((field) => (
        <div key={field}>
          <dt>{fieldLabels[field] || field}</dt>
          <dd><span>{compact(oldValue(field))}</span><b>→</b><span>{compact(newValue(field))}</span></dd>
        </div>
      ))}
    </dl>
  );
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
  const fieldCounts = new Map<string, number>();
  rows.forEach((row) => {
    (row.changed_fields || []).forEach((field) => {
      fieldCounts.set(field, (fieldCounts.get(field) || 0) + 1);
    });
  });
  boardRows.forEach((row) => {
    row.changed_fields.forEach((field) => {
      fieldCounts.set(field, (fieldCounts.get(field) || 0) + 1);
    });
  });
  return (
    <div className="bom-metadata-layers">
      <div className="bom-layer-summary">
        {Array.from(fieldCounts.entries())
          .sort((left, right) => right[1] - left[1])
          .map(([field, count]) => (
            <span key={field}><strong>{count}</strong> {fieldLabels[field] || field}</span>
          ))}
        <p>这些字段单独复核，不直接改变主料实际位号的贴装结论。</p>
      </div>
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
                title: "字段变化",
                width: 680,
                render: (_, row) => (
                  <FieldChanges
                    fields={row.changed_fields}
                    oldValue={(field) => row.old[field]}
                    newValue={(field) => row.new[field]}
                  />
                ),
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
            scroll={{ x: 980 }}
            expandable={{
              expandedRowRender: (row) => (
                <div className="bom-raw-row-detail">
                  <div>
                    <span>旧版完整属性</span>
                    <pre className="bom-variant-json">
                      {compact({ variants: row.old_variants, metadata: row.old_metadata })}
                    </pre>
                  </div>
                  <div>
                    <span>新版完整属性</span>
                    <pre className="bom-variant-json">
                      {compact({ variants: row.new_variants, metadata: row.new_metadata })}
                    </pre>
                  </div>
                </div>
              ),
            }}
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
                title: "字段",
                dataIndex: "changed_fields",
                width: 220,
                render: fieldTags,
              },
              {
                title: "旧版 → 新版",
                width: 520,
                render: (_, row) => (
                  <FieldChanges
                    fields={row.changed_fields || []}
                    oldValue={(field) => variantValue(row, "old", field)}
                    newValue={(field) => variantValue(row, "new", field)}
                  />
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
