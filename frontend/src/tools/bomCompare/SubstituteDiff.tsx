import { Empty, Table, Tag, Tooltip } from "antd";
import type { SubstituteDiff as SubstituteDiffType, SubstituteSnapshot } from "./types";

function groupCode(row: SubstituteDiffType) {
  return row.new.group_code || row.old.group_code || "";
}

function relation(snapshot: SubstituteSnapshot) {
  const main = snapshot.main_material_code || "无主料";
  const alternatives = snapshot.alternative_material_codes || [];
  return (
    <div className="bom-substitute-relation">
      <span>主料</span>
      <strong>{main}</strong>
      {alternatives.length ? (
        <div>
          <span>替代</span>
          {alternatives.map((code) => <Tag key={code}>{code}</Tag>)}
        </div>
      ) : <small>没有替代料</small>}
    </div>
  );
}

function priorities(snapshot: SubstituteSnapshot) {
  return Object.entries(snapshot.priorities || {})
    .sort((left, right) => Number(left[1]) - Number(right[1]))
    .map(([code, priority]) => `${priority}:${code}`)
    .join(" · ");
}

export function SubstituteDiff({ rows }: { rows: SubstituteDiffType[] }) {
  if (!rows.length) return <Empty description="替代关系没有变化" />;
  const added = rows.filter((row) => row.status === "added").length;
  const changed = rows.filter((row) => row.status === "changed").length;
  const removed = rows.filter((row) => row.status === "removed").length;
  return (
    <div className="bom-substitute-layer">
      <div className="bom-layer-summary">
        <span><strong>{added}</strong> 新增替代组</span>
        <span><strong>{changed}</strong> 关系或优先级调整</span>
        <span><strong>{removed}</strong> 删除替代组</span>
        <p>这里只统计替代关系变化，替代料不会重复计入实际贴装数量。</p>
      </div>
      <Table
        className="bom-layer-table"
        size="small"
        rowKey={(row) => `${row.status}:${groupCode(row)}`}
        dataSource={rows}
        pagination={{ pageSize: 12, showSizeChanger: true }}
        scroll={{ x: 1120 }}
        columns={[
          {
            title: "状态",
            dataIndex: "status",
            width: 96,
            fixed: "left",
            render: (value: SubstituteDiffType["status"]) => (
              <Tag color={value === "added" ? "blue" : value === "removed" ? "orange" : "gold"}>
                {value === "added" ? "新增" : value === "removed" ? "删除" : "调整"}
              </Tag>
            ),
          },
          {
            title: "替代组",
            width: 200,
            fixed: "left",
            render: (_, row) => (
              <div className="bom-substitute-code">
                <strong>{groupCode(row)}</strong>
                <span>{row.new.parent_code || row.old.parent_code}</span>
              </div>
            ),
          },
          { title: "旧版关系", width: 280, render: (_, row) => relation(row.old) },
          { title: "新版关系", width: 280, render: (_, row) => relation(row.new) },
          {
            title: "优先级变化",
            width: 260,
            render: (_, row) => (
              <div className="bom-priority-transition">
                <span>{priorities(row.old) || "无"}</span>
                <b>→</b>
                <span>{priorities(row.new) || "无"}</span>
              </div>
            ),
          },
          {
            title: "实际位号",
            width: 240,
            render: (_, row) => {
              const refs = (row.new.references || row.old.references || []).join(", ");
              return refs ? (
                <Tooltip title={refs}>
                  <span className="bom-reference-preview">{refs}</span>
                </Tooltip>
              ) : "-";
            },
          },
        ]}
      />
    </div>
  );
}
