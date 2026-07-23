import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Input,
  Pagination,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import {
  ArrowLeftRight,
  CheckCircle2,
  FileSpreadsheet,
  GitCompareArrows,
  Play,
  RotateCcw,
  Search,
  ShieldAlert,
} from "lucide-react";
import {
  runBomCompare,
  uploadFiles,
  type ToolInfo,
} from "../api/client";
import { toUserMessage } from "../api/errors";
import { HistoryBomPicker } from "../components/HistoryBomPicker";
import { useToolWorkspace } from "../state/toolWorkspace";
import { ExportPanel } from "./bomCompare/ExportPanel";
import { MetadataDiff } from "./bomCompare/MetadataDiff";
import { PlacementDiff } from "./bomCompare/PlacementDiff";
import { SourceInspection } from "./bomCompare/SourceInspection";
import { SubstituteDiff } from "./bomCompare/SubstituteDiff";
import {
  changeKindLabels,
  type BomCompareResponse,
  type ChangeEvent,
  type ComparisonScope,
  type RawRowDiff,
  type ValidationFinding,
} from "./bomCompare/types";

function SourceSelector({
  label,
  hint,
  file,
  historyPath,
  onFile,
  onHistoryPath,
}: {
  label: string;
  hint: string;
  file?: File;
  historyPath: string;
  onFile: (file?: File) => void;
  onHistoryPath: (path: string) => void;
}) {
  return (
    <section className="bom-source-selector">
      <div className="bom-source-label">
        <span>{label}</span>
        <small>{hint}</small>
      </div>
      <div className="bom-source-pickers">
        <div className="bom-source-history">
          <HistoryBomPicker
            value={historyPath}
            onChange={(path) => {
              onHistoryPath(path);
              if (path) onFile(undefined);
            }}
          />
        </div>
        <div className="bom-source-local">
          <Upload
            accept=".xlsx,.xls"
            maxCount={1}
            fileList={file ? [{ uid: label, name: file.name, status: "done" as const }] : []}
            beforeUpload={(next) => {
              onFile(next);
              onHistoryPath("");
              return false;
            }}
            onRemove={() => {
              onFile(undefined);
              return true;
            }}
          >
            <Button icon={<FileSpreadsheet size={16} />}>选择本地 BOM</Button>
          </Upload>
        </div>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  tone = "plain",
  note,
}: {
  label: string;
  value: number;
  tone?: "plain" | "info" | "warn" | "danger";
  note?: string;
}) {
  return (
    <div className={`bom-semantic-metric is-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
      {note ? <small>{note}</small> : null}
    </div>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return <pre className="bom-json-preview">{JSON.stringify(value, null, 2)}</pre>;
}

function RawRows({ rows }: { rows: RawRowDiff[] }) {
  if (!rows.length) return <Empty description="原始行没有变化" />;
  return (
    <Table
      className="bom-layer-table"
      size="small"
      rowKey={(row) => `${row.parent_code}:${row.material_code}:${row.status}`}
      dataSource={rows}
      pagination={{ pageSize: 12, showSizeChanger: true }}
      scroll={{ x: 1260 }}
      expandable={{
        expandedRowRender: (row) => (
          <div className="bom-raw-row-detail">
            <div><span>旧版行</span><JsonPreview value={row.old_rows} /></div>
            <div><span>新版行</span><JsonPreview value={row.new_rows} /></div>
          </div>
        ),
      }}
      columns={[
        {
          title: "状态",
          dataIndex: "status",
          width: 100,
          fixed: "left",
          render: (value) => (
            <Tag color={value === "added" ? "blue" : value === "removed" ? "orange" : "gold"}>
              {value === "added" ? "新增" : value === "removed" ? "删除" : "变更"}
            </Tag>
          ),
        },
        { title: "父项编码", dataIndex: "parent_code", width: 190 },
        { title: "子项编码", dataIndex: "material_code", width: 210 },
        {
          title: "旧版来源",
          dataIndex: "old_source_ids",
          width: 320,
          render: (value: string[]) => value.join(", ") || "-",
        },
        {
          title: "新版来源",
          dataIndex: "new_source_ids",
          width: 320,
          render: (value: string[]) => value.join(", ") || "-",
        },
      ]}
    />
  );
}

function EventTable({ events }: { events: ChangeEvent[] }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return events.filter((event) => {
      const haystack = `${event.parent_code} ${event.title} ${event.kind} ${(event.references || []).join(" ")} ${(event.group_codes || []).join(" ")}`.toLowerCase();
      return !normalized || haystack.includes(normalized);
    });
  }, [events, query]);
  if (!events.length) return <Empty description="没有业务变化" />;
  return (
    <div className="bom-event-table">
      <Input
        allowClear
        prefix={<Search size={15} />}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="搜索父项、事件、位号或替代组"
      />
      <Table
        size="small"
        rowKey="event_id"
        dataSource={rows}
        pagination={{ pageSize: 12 }}
        scroll={{ x: 1150 }}
        columns={[
          {
            title: "分类",
            dataIndex: "kind",
            width: 190,
            render: (value, row) => (
              <Tag color={row.impact === "blocker" ? "red" : row.impact === "placement" ? "orange" : row.impact === "supply" ? "blue" : "default"}>
                {changeKindLabels[value] || value}
              </Tag>
            ),
          },
          { title: "父项", dataIndex: "parent_code", width: 180 },
          { title: "变化说明", dataIndex: "title", width: 340 },
          {
            title: "位号",
            dataIndex: "references",
            width: 250,
            ellipsis: true,
            render: (value: string[]) => value?.join(", ") || "-",
          },
          {
            title: "替代组",
            dataIndex: "group_codes",
            width: 220,
            render: (value: string[]) => value?.join(" / ") || "-",
          },
          { title: "OA 语义", dataIndex: "oa_change_type", width: 180, render: (value) => value || "-" },
        ]}
      />
    </div>
  );
}

function FindingList({ rows }: { rows: ValidationFinding[] }) {
  const pageSize = 8;
  const [page, setPage] = useState(1);
  const findingSignature = rows
    .map((finding) => `${finding.code}:${finding.parent_code || ""}:${finding.references?.join(",") || ""}`)
    .join("|");
  useEffect(() => setPage(1), [findingSignature]);

  if (!rows.length) return <Empty description="没有阻断或警告" />;
  const visibleRows = rows.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div className="bom-finding-list">
      <div className="bom-finding-page">
        {visibleRows.map((finding, index) => {
          const materialCodes = Array.isArray(finding.details?.material_codes)
            ? finding.details.material_codes.filter((value) => typeof value === "string").join(", ")
            : "";
          const target = [
            finding.details?.material_code,
            materialCodes,
            finding.details?.group_code,
            finding.details?.main_code,
          ]
            .filter((value) => typeof value === "string" && value)
            .join(" / ");
          const sourceParent = typeof finding.details?.source_parent_code === "string"
            ? finding.details.source_parent_code
            : "";
          return (
            <article
              key={`${finding.code}:${finding.parent_code}:${(page - 1) * pageSize + index}`}
              className={`is-${finding.severity}`}
            >
              <Tag color={finding.severity === "blocker" ? "red" : finding.severity === "warning" ? "orange" : "blue"}>
                {finding.severity === "blocker" ? "阻断" : finding.severity === "warning" ? "警告" : "提示"}
              </Tag>
              <div>
                <strong>{finding.message}</strong>
                <span>
                  {finding.parent_code || "全局"} · {finding.code}
                  {sourceParent ? ` · 来源父项 ${sourceParent}` : ""}
                  {target ? ` · ${target}` : ""}
                </span>
                {finding.references?.length ? <p>位号：{finding.references.join(", ")}</p> : null}
              </div>
            </article>
          );
        })}
      </div>
      {rows.length > pageSize ? (
        <Pagination
          className="bom-finding-pagination"
          current={page}
          pageSize={pageSize}
          total={rows.length}
          showSizeChanger={false}
          showTotal={(total) => `共 ${total} 项`}
          onChange={setPage}
        />
      ) : null}
    </div>
  );
}

function ScopeConfirmation({
  scope,
  running,
  onConfirm,
  onReset,
}: {
  scope: ComparisonScope;
  running: boolean;
  onConfirm: () => void;
  onReset: () => void;
}) {
  const pair = scope.pairs.find((item) => item.status === "suggested");
  if (!pair) {
    return (
      <Alert
        type="warning"
        showIcon
        message="无法自动建立板卡对应关系"
        description="当前文件包含多个未匹配父项。请先确认两份文件中的父项编码，或分别导出单板 BOM 后再比较。"
        action={<Button onClick={onReset}>重新选择</Button>}
      />
    );
  }
  const evidence = pair.evidence;
  return (
    <section className="bom-scope-confirmation">
      <div className="bom-scope-heading">
        <div>
          <span className="bom-kicker">比较范围确认</span>
          <h3>这是同一块板的不同版本吗？</h3>
          <p>父项编码不同，平台不会直接把整板判成删除和新增。确认后才按实际位号、料号和替代关系比较。</p>
        </div>
        <Tag color="gold">需要人工确认</Tag>
      </div>
      <div className="bom-scope-route">
        <div>
          <span>旧版父项</span>
          <strong>{pair.old_parent_code}</strong>
          <small>{pair.old_parent_description || "未提供父项描述"}</small>
        </div>
        <ArrowLeftRight aria-hidden size={20} />
        <div>
          <span>新版父项</span>
          <strong>{pair.new_parent_code}</strong>
          <small>{pair.new_parent_description || "未提供父项描述"}</small>
        </div>
      </div>
      <div className="bom-scope-evidence">
        <span>共享位号 <strong>{evidence.shared_reference_count}</strong></span>
        <span>位号重合度 <strong>{Math.round(evidence.reference_overlap * 100)}%</strong></span>
        <span>共享物料 <strong>{evidence.shared_material_count}</strong></span>
        <span>物料重合度 <strong>{Math.round(evidence.material_overlap * 100)}%</strong></span>
      </div>
      <div className="bom-scope-actions">
        <Button onClick={onReset}>不是，重新选择</Button>
        <Button
          type="primary"
          loading={running}
          icon={<CheckCircle2 size={16} />}
          onClick={onConfirm}
        >
          确认按同一板卡不同版本对比
        </Button>
      </div>
    </section>
  );
}

export function BomComparePane({ tool }: { tool: ToolInfo }) {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace(
    "bom_compare",
    {
      historyBom1: "",
      historyBom2: "",
      result: null as BomCompareResponse | null,
      activeTab: "placement",
      selectedReference: "",
    },
    { heavyKeys: ["result"], maxBytes: 3 * 1024 * 1024 },
  );
  const [bom1, setBom1] = useState<File>();
  const [bom2, setBom2] = useState<File>();
  const [historyBom1, setHistoryBom1] = useState(String(workspace.historyBom1 || ""));
  const [historyBom2, setHistoryBom2] = useState(String(workspace.historyBom2 || ""));
  const [result, setResult] = useState<BomCompareResponse | null>(workspace.result || null);
  const [activeTab, setActiveTab] = useState(String(workspace.activeTab || "placement"));
  const [selectedReference, setSelectedReference] = useState(String(workspace.selectedReference || ""));
  const [running, setRunning] = useState(false);
  const [lastPaths, setLastPaths] = useState<{ bom1: string; bom2: string } | null>(null);

  useEffect(() => {
    setWorkspace({ historyBom1, historyBom2, result, activeTab, selectedReference });
  }, [historyBom1, historyBom2, result, activeTab, selectedReference]);

  const semantic = result?.semantic;
  const summary = semantic?.summary;
  const boardMetadataDiff = semantic?.board_metadata_diff || [];

  async function sourcePaths() {
    const [leftUpload, rightUpload] = await Promise.all([
      historyBom1 || !bom1 ? Promise.resolve(null) : uploadFiles([bom1]),
      historyBom2 || !bom2 ? Promise.resolve(null) : uploadFiles([bom2]),
    ]);
    return {
      bom1: historyBom1 || leftUpload?.files[0]?.path || "",
      bom2: historyBom2 || rightUpload?.files[0]?.path || "",
    };
  }

  async function handleRun(scopeConfirmation = false) {
    const canReuseInspectionPaths = Boolean(
      scopeConfirmation
      && result?.source_inspections?.old.envelope.source_path
      && result?.source_inspections?.new.envelope.source_path,
    );
    if (
      !canReuseInspectionPaths
      && ((!historyBom1 && !bom1) || (!historyBom2 && !bom2))
    ) {
      setResult({ status: "error", tool: "bom_compare", error: "请先选择旧版和新版两份 BOM。" });
      return;
    }
    setRunning(true);
    try {
      const inspectionPaths = result?.source_inspections
        ? {
            bom1: result.source_inspections.old.envelope.source_path,
            bom2: result.source_inspections.new.envelope.source_path,
          }
        : null;
      const paths = scopeConfirmation
        ? lastPaths || inspectionPaths || await sourcePaths()
        : await sourcePaths();
      setLastPaths(paths);
      const next = await runBomCompare({
        action: "compare",
        ...paths,
        ...(scopeConfirmation ? { scope_confirmation: true } : {}),
      });
      setResult(next);
      setActiveTab(next.semantic?.blockers?.length ? "delivery" : "placement");
      setSelectedReference(next.semantic?.placement_diff?.[0]?.reference || "");
    } catch (error) {
      setResult({ status: "error", tool: "bom_compare", error: toUserMessage(error) });
    } finally {
      setRunning(false);
    }
  }

  function clearAll() {
    setBom1(undefined);
    setBom2(undefined);
    setHistoryBom1("");
    setHistoryBom2("");
    setResult(null);
    setActiveTab("placement");
    setSelectedReference("");
    setLastPaths(null);
    resetWorkspace();
  }

  function swapSources() {
    setBom1(bom2);
    setBom2(bom1);
    setHistoryBom1(historyBom2);
    setHistoryBom2(historyBom1);
    setResult(null);
    setLastPaths(null);
  }

  return (
    <div className="bom-compare-workbench">
      <header className="bom-compare-header">
        <div>
          <span className="bom-kicker">四层语义对比</span>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">
            分开核对实际贴装、替代关系、原始行和非功能字段，替代料不重复计入整板数量。
          </Typography.Paragraph>
        </div>
        {semantic ? (
          <div className="bom-analysis-id">
            <span>分析指纹</span>
            <code>{semantic.analysis_fingerprint}</code>
          </div>
        ) : null}
      </header>

      <section className="bom-source-band">
        <SourceSelector
          label="旧版 / 基准"
          hint="变更前或已确认版本"
          file={bom1}
          historyPath={historyBom1}
          onFile={setBom1}
          onHistoryPath={setHistoryBom1}
        />
        <Tooltip title="交换新旧版本">
          <Button
            className="bom-swap-button"
            aria-label="交换新旧版本"
            icon={<ArrowLeftRight size={17} />}
            onClick={swapSources}
          />
        </Tooltip>
        <SourceSelector
          label="新版 / 待确认"
          hint="变更后或准备交付版本"
          file={bom2}
          historyPath={historyBom2}
          onFile={setBom2}
          onHistoryPath={setHistoryBom2}
        />
        <div className="bom-source-actions">
          <Button
            type="primary"
            size="large"
            loading={running}
            icon={<Play size={17} fill="currentColor" />}
            onClick={() => void handleRun(false)}
          >
            开始语义对比
          </Button>
          <Button icon={<RotateCcw size={16} />} onClick={clearAll}>清空并重来</Button>
        </div>
      </section>

      {result?.status === "error" ? (
        <Alert type="error" showIcon message="对比失败" description={result.error || result.message} />
      ) : null}
      {!result ? (
        <div className="bom-compare-empty">
          <GitCompareArrows size={30} />
          <strong>选择两份 BOM 开始审查</strong>
          <span>支持 Capture、PLM 单板、多 PCBA 汇总和 OA BOM；纯数字位号会要求确认。</span>
        </div>
      ) : null}

      {result?.status === "ok" && result.source_inspections ? (
        <div className="bom-source-inspection-grid">
          <SourceInspection label="旧版来源" inspection={result.source_inspections.old} />
          <SourceInspection label="新版来源" inspection={result.source_inspections.new} />
        </div>
      ) : null}

      {result?.status === "ok"
        && result.needs_scope_confirmation
        && result.comparison_scope ? (
        <ScopeConfirmation
          scope={result.comparison_scope}
          running={running}
          onConfirm={() => void handleRun(true)}
          onReset={clearAll}
        />
      ) : null}

      {result?.status === "ok" && semantic && summary ? (
        <>
          <section className="bom-summary-strip" aria-label="对比摘要">
            <Metric label="旧版实际位号" value={summary.actual_reference_count_old} />
            <Metric label="新版实际位号" value={summary.actual_reference_count_new} />
            <Metric label="业务变化" value={summary.changed_event_count} tone="info" />
            <Metric label="贴装位号差异" value={semantic.placement_diff.length} tone="warn" />
            <Metric label="替代关系差异" value={semantic.substitute_diff.length} tone="info" />
            <Metric label="阻断项" value={summary.blocker_count} tone={summary.blocker_count ? "danger" : "plain"} />
          </section>

          {semantic.blockers.length ? (
            <Alert
              type="error"
              showIcon
              icon={<ShieldAlert size={18} />}
              message={`发现 ${semantic.blockers.length} 个阻断项`}
              description="报告可以下载用于定位，但正式 PLM / OA 输出必须先解决阻断项。"
            />
          ) : null}

          <Tabs
            className="bom-semantic-tabs"
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "placement",
                label: `实际贴装 ${semantic.placement_diff.length}`,
                children: (
                  <PlacementDiff
                    rows={semantic.placement_diff}
                    events={semantic.events}
                    selectedReference={selectedReference}
                    onSelectedReference={setSelectedReference}
                  />
                ),
              },
              {
                key: "substitute",
                label: `替代关系 ${semantic.substitute_diff.length}`,
                children: <SubstituteDiff rows={semantic.substitute_diff} />,
              },
              {
                key: "events",
                label: `业务事件 ${semantic.events.length}`,
                children: <EventTable events={semantic.events} />,
              },
              {
                key: "raw",
                label: `原始行 ${semantic.raw_row_diff.length}`,
                children: <RawRows rows={semantic.raw_row_diff} />,
              },
              {
                key: "metadata",
                label: `元数据 ${semantic.metadata_diff.length + boardMetadataDiff.length}`,
                children: (
                  <MetadataDiff
                    rows={semantic.metadata_diff}
                    boardRows={boardMetadataDiff}
                  />
                ),
              },
              {
                key: "delivery",
                label: `风险与交付 ${semantic.blockers.length + semantic.warnings.length}`,
                children: (
                  <div className="bom-delivery-grid">
                    <section>
                      <div className="bom-section-heading">
                        <span className="bom-kicker">质量门禁</span>
                        <h3>风险与阻断项</h3>
                      </div>
                      <FindingList rows={[...semantic.blockers, ...semantic.warnings]} />
                    </section>
                    <section>
                      <div className="bom-section-heading">
                        <span className="bom-kicker">交付文件</span>
                        <h3>报告与机器数据</h3>
                      </div>
                      <ExportPanel outputs={result.outputs || []} canExport={semantic.can_export} />
                    </section>
                  </div>
                ),
              },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
