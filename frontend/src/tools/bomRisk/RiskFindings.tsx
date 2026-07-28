import type { ReactNode } from "react";
import { Alert, Button, Descriptions, Empty, Space, Table, Tabs, Tag, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { outputHref } from "../../utils/outputHref";

export type RiskLevel = "blocker" | "warn" | "info" | "ok";

export type RiskFinding = {
  code: string;
  name: string;
  level?: RiskLevel;
  status?: string;
  message: string;
  detail_count?: number;
  details?: Array<Record<string, unknown>>;
  applicable?: boolean;
};

export type RiskReport = {
  profile?: string;
  stats?: Record<string, number>;
  findings?: RiskFinding[];
  counts_by_level?: Record<RiskLevel, number>;
  grade_flags?: Array<Record<string, unknown>>;
  type_flags?: Array<Record<string, unknown>>;
  substitute_groups?: Array<Record<string, unknown>>;
  shield_items?: Array<Record<string, unknown>>;
  mechanical_items?: Array<Record<string, unknown>>;
  process_items?: Array<Record<string, unknown>>;
  nc_items?: Array<Record<string, unknown>>;
  issue_method_dist?: Record<string, number>;
  version_sensitive?: Array<Record<string, unknown>>;
};

const levelMeta: Record<RiskLevel, { label: string; color: string }> = {
  blocker: { label: "阻断", color: "red" },
  warn: { label: "警告", color: "orange" },
  info: { label: "提示", color: "blue" },
  ok: { label: "通过", color: "green" },
};

function findingLevel(item: RiskFinding): RiskLevel {
  if (item.level && item.level in levelMeta) return item.level;
  if (item.status === "warn") return "warn";
  if (item.status === "ok") return "ok";
  return "info";
}

function valueText(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function GenericTable({ rows, preferred }: { rows: Array<Record<string, unknown>>; preferred: Array<[string, string]> }) {
  if (!rows.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有相关明细" />;
  const keys = [
    ...preferred.filter(([key]) => rows.some((row) => row[key] !== undefined)),
    ...Object.keys(rows[0] || {})
      .filter((key) => !preferred.some(([preferredKey]) => preferredKey === key))
      .map((key) => [key, key] as [string, string]),
  ].slice(0, 10);
  return (
    <Table
      size="small"
      rowKey={(row, index) => `${valueText(row.code || row.group_code || row.ref || row.source_row)}-${index}`}
      dataSource={rows}
      pagination={{ pageSize: 10, showSizeChanger: true }}
      scroll={{ x: Math.max(720, keys.length * 140) }}
      columns={keys.map(([key, label]) => ({
        title: label,
        dataIndex: key,
        ellipsis: true,
        render: (value: unknown) => valueText(value) || "-",
      }))}
    />
  );
}

export function RiskFindings({
  report,
  outputs = [],
  preview,
}: {
  report?: RiskReport | null;
  outputs?: string[];
  preview?: ReactNode;
}) {
  if (!report) return <Empty description="尚未运行风险检查" />;
  const findings = report.findings || [];
  const counts = report.counts_by_level || ({ blocker: 0, warn: 0, info: 0, ok: 0 } as Record<RiskLevel, number>);
  const blockers = findings.filter((item) => findingLevel(item) === "blocker");
  const warnings = findings.filter((item) => findingLevel(item) === "warn");
  const categories = [
    ...(report.shield_items || []).map((item) => ({ ...item, category: "屏蔽类" })),
    ...(report.mechanical_items || []).map((item) => ({ ...item, category: "机构件" })),
    ...(report.process_items || []).map((item) => ({ ...item, category: "工艺项" })),
    ...(report.nc_items || []).map((item) => ({ ...item, category: "NC/未贴" })),
  ];
  const findingColumns = [
    {
      title: "级别",
      width: 84,
      render: (_: unknown, row: RiskFinding) => {
        const level = findingLevel(row);
        return <Tag color={levelMeta[level].color}>{levelMeta[level].label}</Tag>;
      },
    },
    { title: "检查项", dataIndex: "name", width: 190 },
    { title: "结论", dataIndex: "message", ellipsis: true },
    { title: "明细", dataIndex: "detail_count", width: 72, render: (value: number) => value || 0 },
  ];

  return (
    <div className="risk-findings">
      <div className="risk-summary-strip">
        <div><span>阻断</span><strong className="risk-count-blocker">{counts.blocker || 0}</strong></div>
        <div><span>警告</span><strong className="risk-count-warn">{counts.warn || 0}</strong></div>
        <div><span>提示</span><strong>{counts.info || 0}</strong></div>
        <div><span>通过</span><strong className="risk-count-ok">{counts.ok || 0}</strong></div>
        <div><span>格式</span><strong className="risk-profile">{report.profile || "未知"}</strong></div>
      </div>

      {blockers.length ? (
        <Alert type="error" showIcon message={`存在 ${blockers.length} 个阻断项，当前 BOM 不应交付`} />
      ) : warnings.length ? (
        <Alert type="warning" showIcon message={`没有阻断项，仍有 ${warnings.length} 个风险需要确认`} />
      ) : (
        <Alert type="success" showIcon message="风险检查通过" />
      )}

      <Descriptions size="small" column={{ xs: 2, sm: 3, lg: 6 }} className="risk-stats">
        {Object.entries(report.stats || {}).map(([key, value]) => (
          <Descriptions.Item key={key} label={key}>{value}</Descriptions.Item>
        ))}
      </Descriptions>

      <Tabs
        items={[
          {
            key: "findings",
            label: `检查结论 ${findings.length}`,
            children: (
              <Table
                size="small"
                rowKey={(row) => row.code}
                dataSource={findings}
                columns={findingColumns}
                pagination={{ pageSize: 10 }}
                expandable={{
                  rowExpandable: (row) => Boolean(row.details?.length),
                  expandedRowRender: (row) => (
                    <GenericTable
                      rows={row.details || []}
                      preferred={[["source_row", "源行"], ["code", "子项编码"], ["refs", "位号"], ["message", "说明"]]}
                    />
                  ),
                }}
              />
            ),
          },
          {
            key: "grades",
            label: `优选等级 ${(report.grade_flags || []).length}`,
            children: <GenericTable rows={report.grade_flags || []} preferred={[["code", "子项编码"], ["name", "名称"], ["desc", "描述"], ["refs", "位号"], ["grade", "等级"]]} />,
          },
          {
            key: "types",
            label: `位号类型 ${(report.type_flags || []).length}`,
            children: <GenericTable rows={report.type_flags || []} preferred={[["ref", "位号"], ["code", "子项编码"], ["expected", "位号期望"], ["actual", "识别类型"], ["note", "说明"]]} />,
          },
          {
            key: "substitutes",
            label: `替代组 ${(report.substitute_groups || []).length}`,
            children: <GenericTable rows={report.substitute_groups || []} preferred={[["group_code", "替代组"], ["main_code", "主料"], ["alternative_codes", "替代料"], ["priorities", "优先级"], ["refs", "实际位号"], ["issues", "问题"]]} />,
          },
          {
            key: "categories",
            label: `专项物料 ${categories.length}`,
            children: <GenericTable rows={categories} preferred={[["category", "类别"], ["subtype", "子类型"], ["code", "子项编码"], ["name", "名称"], ["desc", "描述"], ["refs", "位号"]]} />,
          },
          {
            key: "versions",
            label: `版本敏感 ${(report.version_sensitive || []).length}`,
            children: <GenericTable rows={report.version_sensitive || []} preferred={[["code", "子项编码"], ["name", "名称"], ["model", "型号"], ["desc", "描述"], ["refs", "位号"]]} />,
          },
          ...(preview ? [{ key: "preview", label: "最终 BOM 预览", children: preview }] : []),
          {
            key: "outputs",
            label: `报告文件 ${outputs.length}`,
            children: outputs.length ? (
              <Space wrap>
                {outputs.map((path) => (
                  <Button key={path} icon={<DownloadOutlined />} href={outputHref(path)}>
                    下载 {path.split(/[\\/]/).pop()}
                  </Button>
                ))}
              </Space>
            ) : <Typography.Text type="secondary">没有输出文件</Typography.Text>,
          },
        ]}
      />
    </div>
  );
}
