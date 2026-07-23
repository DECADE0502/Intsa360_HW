import { type Dispatch, type SetStateAction, useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Empty, Segmented, Space, Switch, Table, Tabs, Tag, Tooltip, Typography, Upload } from "antd";
import {
  ApartmentOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  PrinterOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import { runSmtLayout, uploadFiles, type SmtComponent, type SmtLayoutResponse, type SmtSanity } from "../api/client";
import { toUserMessage } from "../api/errors";
import { HistoryBomPicker } from "../components/HistoryBomPicker";
import { PcbCanvas } from "../components/PcbCanvas";
import { RefdesVirtualList, type RefdesListItem } from "../components/RefdesVirtualList";
import { useToolWorkspace } from "../state/toolWorkspace";
import { outputHref } from "../utils/outputHref";
import styles from "./SmtLayoutPane.module.css";


type SmtLayoutWorkspace = {
  historyBom: string;
  historyDecisionManifest: string;
  historySemanticManifest: string;
  result: SmtLayoutResponse | null;
  activeTab: string;
};

type DirectorySourceProps = {
  kind: "smt" | "netlist";
  title: string;
  buttonLabel: string;
  files: File[];
  onFiles: Dispatch<SetStateAction<File[]>>;
};

const SMT_SOURCE_EXTENSIONS = new Set([".dxf", ".art", ".gbr", ".ger"]);

function fileExtension(name: string) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function acceptsDirectoryFile(kind: DirectorySourceProps["kind"], file: File) {
  const name = file.name.toLowerCase();
  if (kind === "netlist") return name === "pstxnet.dat" || name === "pstxprt.dat";
  return name === "xy.txt" || SMT_SOURCE_EXTENSIONS.has(fileExtension(name));
}

function addUniqueFile(files: File[], next: File) {
  if (files.some((item) => item.name === next.name && item.size === next.size && item.lastModified === next.lastModified)) {
    return files;
  }
  return [...files, next];
}

function selectedDirectoryLabel(files: File[]) {
  if (!files.length) return "未选择";
  const relative = (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath || "";
  const folder = relative.split("/").filter(Boolean)[0];
  return folder ? `${folder} · ${files.length} 个有效文件` : `已选择 ${files.length} 个有效文件`;
}

function DirectorySource({ kind, title, buttonLabel, files, onFiles }: DirectorySourceProps) {
  const icon = kind === "smt" ? <FolderOpenOutlined /> : <ApartmentOutlined />;
  return (
    <Card size="small" className="smt-layout-source-card">
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Typography.Text strong>{title}</Typography.Text>
        <Space wrap>
          <Upload
            directory
            multiple
            accept={kind === "smt" ? ".txt,.dxf,.art,.gbr,.ger" : ".dat"}
            fileList={[]}
            showUploadList={false}
            beforeUpload={(file) => {
              if (acceptsDirectoryFile(kind, file)) onFiles((current) => addUniqueFile(current, file));
              return false;
            }}
          >
            <Button aria-label={buttonLabel} icon={icon}>{buttonLabel}</Button>
          </Upload>
          {files.length ? <Button onClick={() => onFiles([])}>清除</Button> : null}
        </Space>
        <Typography.Text type={files.length ? "success" : "secondary"} ellipsis={{ tooltip: selectedDirectoryLabel(files) }}>
          {selectedDirectoryLabel(files)}
        </Typography.Text>
      </Space>
    </Card>
  );
}

function BomSource({
  file,
  decisionFile,
  semanticFile,
  historyBom,
  historyDecisionManifest,
  historySemanticManifest,
  onFile,
  onDecisionFile,
  onSemanticFile,
  onHistoryBom,
}: {
  file?: File;
  decisionFile?: File;
  semanticFile?: File;
  historyBom: string;
  historyDecisionManifest: string;
  historySemanticManifest: string;
  onFile: (file?: File) => void;
  onDecisionFile: (file?: File) => void;
  onSemanticFile: (file?: File) => void;
  onHistoryBom: (path: string, decisionManifest?: string, semanticManifest?: string) => void;
}) {
  return (
    <Card size="small" className="smt-layout-source-card">
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Typography.Text strong>可导入 PLM/OA 的成品 BOM（不含 NC）</Typography.Text>
        <HistoryBomPicker
          value={historyBom}
          onChange={(path, asset) => {
            onHistoryBom(
              path,
              asset?.decision_manifest || "",
              asset?.semantic_manifest || "",
            );
            if (path) {
              onFile(undefined);
              onDecisionFile(undefined);
              onSemanticFile(undefined);
            }
          }}
        />
        <Upload
          accept=".xlsx,.xls"
          maxCount={1}
          fileList={file ? [{ uid: "bom", name: file.name, status: "done" as const }] : []}
          beforeUpload={(next) => {
            onFile(next);
            onDecisionFile(undefined);
            onSemanticFile(undefined);
            onHistoryBom("", "", "");
            return false;
          }}
          onRemove={() => {
            onFile(undefined);
            return true;
          }}
        >
          <Button aria-label="选择 PLM/OA BOM" icon={<FileExcelOutlined />}>选择 PLM/OA BOM</Button>
        </Upload>
        <Upload
          accept=".json"
          maxCount={1}
          fileList={decisionFile ? [{ uid: "decision", name: decisionFile.name, status: "done" as const }] : []}
          beforeUpload={(next) => {
            onDecisionFile(next);
            return false;
          }}
          onRemove={() => {
            onDecisionFile(undefined);
            return true;
          }}
        >
          <Button aria-label="选择 BOM 决策清单" icon={<FileTextOutlined />}>选择决策清单（推荐）</Button>
        </Upload>
        <Upload
          accept=".json"
          maxCount={1}
          fileList={semanticFile ? [{ uid: "semantic", name: semanticFile.name, status: "done" as const }] : []}
          beforeUpload={(next) => {
            onSemanticFile(next);
            return false;
          }}
          onRemove={() => {
            onSemanticFile(undefined);
            return true;
          }}
        >
          <Button aria-label="选择 BOM 语义清单" icon={<FileTextOutlined />}>
            选择语义清单（推荐）
          </Button>
        </Upload>
        {historyBom ? (
          <Typography.Text type={historySemanticManifest || historyDecisionManifest ? "success" : "secondary"}>
            {historySemanticManifest
              ? "已自动关联同次处理的 BOM 语义清单"
              : historyDecisionManifest
                ? "已自动关联同次处理的决策清单"
                : "该历史记录没有语义清单，将使用兼容推理模式"}
          </Typography.Text>
        ) : null}
      </Space>
    </Card>
  );
}


function FaiChecklistTab({ result }: { result: SmtLayoutResponse | null }) {
  const [side, setSide] = useState<"top" | "bottom" | "both">("both");
  const headers = result?.fai_table?.headers || [];
  const rows = result?.fai_table?.rows || [];
  const visibleRows = useMemo(
    () =>
      rows.filter((row) => {
        if (side === "both") return true;
        const rowSide = String(row[1] || "").trim().toLowerCase();
        return side === "top" ? rowSide === "正面" || rowSide === "top" : rowSide === "背面" || rowSide === "bottom";
      }),
    [rows, side],
  );
  const dataSource = visibleRows.map((values, index) => ({ key: `${String(values[0] || "row")}-${index}`, values, index }));
  const columns = headers.map((header, index) => ({
    title: header,
    key: String(index),
    width: index === 7 ? 280 : index === 0 ? 90 : index === 10 ? 140 : 120,
    ellipsis: index !== 7,
    render: (_: unknown, record: { values: unknown[] }) => String(record.values[index] ?? ""),
  }));
  const downloadPath = result?.outputs.find((path) => path.toLowerCase().endsWith(".xlsx"));

  if (!result?.fai_table) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此预览首件核对表" />;
  }

  return (
    <div className={styles.printRoot}>
      <div className={`${styles.faiToolbar} ${styles.noPrint}`}>
        <Space wrap>
          <Segmented
            aria-label="首件表面别筛选"
            value={side}
            options={[
              { label: "正面", value: "top" },
              { label: "背面", value: "bottom" },
              { label: "全部", value: "both" },
            ]}
            onChange={(value) => setSide(value as "top" | "bottom" | "both")}
          />
          <Typography.Text type="secondary">当前 {visibleRows.length} / {rows.length} 项</Typography.Text>
        </Space>
        <Space>
          <Button aria-label="打印视图" icon={<PrinterOutlined />} onClick={() => window.print()}>
            打印视图
          </Button>
          {downloadPath ? (
            <Button
              aria-label="下载 XLSX"
              type="primary"
              icon={<DownloadOutlined />}
              href={outputHref(downloadPath)}
            >
              下载 XLSX
            </Button>
          ) : null}
        </Space>
      </div>
      <Table
        className={styles.faiTable}
        size="small"
        columns={columns}
        dataSource={dataSource}
        pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false }}
        scroll={{ x: "max-content" }}
        rowClassName={(record) => {
          const partNumber = String(record.values[5] || "");
          const note = String(record.values[10] || "");
          return partNumber.startsWith("⚠") || note ? `smt-fai-row--warn ${styles.faiWarn}` : "";
        }}
        onRow={(record) => ({
          "data-testid": `fai-row-${record.index}`,
          "data-row-ref": String(record.values[0] || ""),
        } as React.HTMLAttributes<HTMLTableRowElement>)}
      />
    </div>
  );
}


type SanityGroupKey = keyof SmtSanity;
type SanityDisplayItem = {
  ref: string;
  note: string;
  severity: "high" | "medium" | "low";
};

const SANITY_SEVERITY_ORDER = { high: 0, medium: 1, low: 2 } as const;

type NcEvidenceFilter = "actionable" | "confirmed" | "candidate" | "unverified" | "all";

function evidenceKind(status: SmtComponent["status"]): RefdesListItem["evidence_kind"] | undefined {
  if (status === "nc") return "confirmed";
  if (status === "candidate_nc") return "candidate";
  if (status === "unverified" || status === "missing_bom") return "unverified";
  return undefined;
}

function evidenceLabel(kind: RefdesListItem["evidence_kind"]) {
  if (kind === "confirmed") return "确定 NC";
  if (kind === "candidate") return "候选 NC";
  return "待确认";
}

function matchesEvidenceFilter(kind: RefdesListItem["evidence_kind"], filter: NcEvidenceFilter) {
  if (!kind) return false;
  if (filter === "all") return true;
  if (filter === "actionable") return kind === "confirmed" || kind === "candidate";
  return kind === filter;
}

function SanityReportTab({
  result,
  onDrillDown,
}: {
  result: SmtLayoutResponse | null;
  onDrillDown: (ref: string) => void;
}) {
  if (!result) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此查看三向一致性" />;
  }
  if (!result.sanity || "status" in result.sanity) {
    return <Alert type="info" showIcon message="未执行三向一致性检查" description="请选择包含 pstxprt.dat 的网表文件夹后重新分析。" />;
  }

  const sanity = result.sanity;
  const rawGroups: Array<{
    key: SanityGroupKey;
    label: string;
    items: SanityDisplayItem[];
    canvas: boolean;
  }> = [
    {
      key: "missing_layout",
      label: "布局缺失",
      items: sanity.missing_layout,
      canvas: true,
    },
    {
      key: "missing_bom",
      label: "BOM 缺失",
      items: sanity.missing_bom,
      canvas: true,
    },
    {
      key: "missing_netlist",
      label: "网表缺失",
      items: sanity.missing_netlist,
      canvas: false,
    },
    {
      key: "footprint_conflicts",
      label: "封装冲突",
      items: sanity.footprint_conflicts.map((item) => ({ ref: item.ref, note: item.note, severity: "high" as const })),
      canvas: true,
    },
  ];
  const groups = rawGroups.map((group) => ({
    ...group,
    items: [...group.items].sort(
      (left, right) =>
        SANITY_SEVERITY_ORDER[left.severity] - SANITY_SEVERITY_ORDER[right.severity] ||
        left.ref.localeCompare(right.ref, undefined, { numeric: true }),
    ),
  }));
  const total = groups.reduce((count, group) => count + group.items.length, 0);

  if (!total) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="三方一致，无发现问题" />;
  }

  const columns = [
    { title: "位号", dataIndex: "ref", key: "ref", width: 90 },
    {
      title: "等级",
      dataIndex: "severity",
      key: "severity",
      width: 76,
      render: (severity: SanityDisplayItem["severity"]) => (
        <Tag color={severity === "high" ? "red" : severity === "medium" ? "gold" : "default"}>
          {severity === "high" ? "高" : severity === "medium" ? "中" : "低"}
        </Tag>
      ),
    },
    { title: "说明", dataIndex: "note", key: "note", ellipsis: true },
  ];

  return (
    <div className={styles.sanityGrid}>
      {groups.map((group) => (
        <section key={group.key} data-testid={`sanity-group-${group.key}`} className={styles.sanityGroup}>
          <Card
            size="small"
            title={
              <Space>
                <span>{group.label}</span>
                <Tag>{group.items.length}</Tag>
              </Space>
            }
          >
            {group.canvas && result.board ? (
              <div data-testid={`sanity-canvas-${group.key}`} className={styles.sanityMiniCanvas}>
                <PcbCanvas
                  outline={result.board.outline_rings}
                  components={result.components}
                  side="both"
                  highlightedRefs={new Set(group.items.map((item) => item.ref))}
                  onSelect={onDrillDown}
                  colorScheme="sanity-emphasis"
                />
              </div>
            ) : null}
            <Table
              size="small"
              columns={columns}
              dataSource={group.items.map((item) => ({ ...item, key: item.ref }))}
              pagination={false}
              scroll={{ y: group.canvas ? 150 : 330 }}
              locale={{ emptyText: "本项无问题" }}
              onRow={(item) => ({
                role: "button",
                tabIndex: 0,
                "data-testid": `sanity-row-${group.key}-${item.ref}`,
                "data-sanity-group": group.key,
                "data-ref": item.ref,
                onClick: () => onDrillDown(item.ref),
                onKeyDown: (event) => {
                  if (event.key === "Enter" || event.key === " ") onDrillDown(item.ref);
                },
              } as React.HTMLAttributes<HTMLTableRowElement>)}
            />
          </Card>
        </section>
      ))}
    </div>
  );
}


function NcLayoutTab({
  result,
  selectedRef,
  onSelectedRef,
}: {
  result: SmtLayoutResponse | null;
  selectedRef: string;
  onSelectedRef: (ref: string) => void;
}) {
  const [side, setSide] = useState<"top" | "bottom" | "both">("both");
  const [evidenceFilter, setEvidenceFilter] = useState<NcEvidenceFilter>("actionable");
  const [shOnly, setShOnly] = useState(false);
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [hoveredRef, setHoveredRef] = useState("");
  const [frameSelectedRefs, setFrameSelectedRefs] = useState<string[] | null>(null);
  const [canvasKey, setCanvasKey] = useState(0);
  const components = result?.components || [];
  const layerComponents = useMemo(
    () =>
      components.filter((component) => {
        const kind = evidenceKind(component.status);
        if (kind && !matchesEvidenceFilter(kind, evidenceFilter) && component.ref !== selectedRef) return false;
        if (shOnly && !/^SH/i.test(component.ref)) return false;
        if (highRiskOnly && !component.high_risk) return false;
        return true;
      }),
    [components, evidenceFilter, selectedRef, shOnly, highRiskOnly],
  );
  const ncItems = useMemo<RefdesListItem[]>(
    () =>
      components.flatMap((component) => {
        const kind = evidenceKind(component.status);
        if (!kind) return [];
        return [{
          ref: component.ref,
          part_number: component.part_number,
          description: component.description,
          side: component.side,
          high_risk: component.high_risk,
          status_label: evidenceLabel(kind),
          evidence_kind: kind,
        }];
      }),
    [components],
  );
  const visibleNcItems = useMemo(() => {
    const frameRefs = frameSelectedRefs ? new Set(frameSelectedRefs.map((ref) => ref.toUpperCase())) : null;
    return ncItems.filter((item) => {
      if (!matchesEvidenceFilter(item.evidence_kind, evidenceFilter) && item.ref !== selectedRef) return false;
      if (side !== "both" && item.side !== side) return false;
      if (shOnly && !/^SH/i.test(item.ref)) return false;
      if (highRiskOnly && !item.high_risk) return false;
      if (frameRefs && !frameRefs.has(item.ref.toUpperCase())) return false;
      return true;
    });
  }, [ncItems, evidenceFilter, selectedRef, side, shOnly, highRiskOnly, frameSelectedRefs]);
  const highlightedRefs = useMemo(
    () => new Set([hoveredRef, selectedRef].filter(Boolean)),
    [hoveredRef, selectedRef],
  );

  if (!result) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此查看 NC 布局" />;
  }
  if (!result.board) {
    return <Alert type="warning" showIcon message="结果中没有可用板框，请重新选择正确的 SMT 资料目录。" />;
  }

  function resetScopedFilters() {
    setFrameSelectedRefs(null);
    setEvidenceFilter("actionable");
    setShOnly(false);
    setHighRiskOnly(false);
  }

  const ncSummary = result.nc_summary;
  const confirmedCount = ncSummary?.confirmed_refs?.length ?? ncSummary?.refs?.length ?? 0;
  const candidateCount = ncSummary?.candidate_refs?.length ?? 0;
  const unverifiedCount = ncSummary?.unverified_refs?.length ?? 0;
  const nonNcCount = ncSummary?.non_nc_refs?.length ?? 0;
  const conflictRefs = ncSummary?.conflict_refs ?? [];
  const hasNetlistEvidence = ncSummary?.inference_mode === "with_netlist";
  const usedDecisionManifest = Boolean(ncSummary?.decision_manifest_used);

  return (
    <div className="smt-nc-tab">
      <Space direction="vertical" size={8} style={{ width: "100%", marginBottom: 12 }}>
        <Alert
          type={unverifiedCount ? "warning" : "info"}
          showIcon
          message={usedDecisionManifest ? "已使用 BOM 决策清单" : hasNetlistEvidence ? "网表已交叉验证" : "未提供决策清单和网表，当前结果为候选 NC"}
          description={(
            <Space wrap>
              <Tag color="red">确定 NC {confirmedCount}</Tag>
              <Tag color="gold">候选 NC {candidateCount}</Tag>
              <Tag color="blue">待确认 {unverifiedCount}</Tag>
              {nonNcCount ? <Tag>已确认其他非贴片项 {nonNcCount}</Tag> : null}
            </Space>
          )}
        />
        {conflictRefs.length ? (
          <Alert
            type="warning"
            showIcon
            message="成品 BOM 与 NC 汇总冲突"
            description={`${conflictRefs.join("、")} 已按成品 BOM 保留为贴装器件。`}
          />
        ) : null}
      </Space>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 12,
        }}
      >
        <Space wrap>
          <Segmented
            aria-label="板面筛选"
            value={side}
            options={[
              { label: "正面", value: "top" },
              { label: "背面", value: "bottom" },
              { label: "全部", value: "both" },
            ]}
            onChange={(value) => setSide(value as "top" | "bottom" | "both")}
          />
          <Segmented
            aria-label="NC 证据筛选"
            value={evidenceFilter}
            options={[
              { label: "需处理", value: "actionable" },
              { label: "确定 NC", value: "confirmed" },
              { label: "候选 NC", value: "candidate" },
              { label: "待确认", value: "unverified" },
              { label: "全部", value: "all" },
            ]}
            onChange={(value) => {
              setEvidenceFilter(value as NcEvidenceFilter);
              setFrameSelectedRefs(null);
            }}
          />
          <Space size={6}>
            <Switch
              size="small"
              aria-label="仅显示 SH 位号"
              checked={shOnly}
              onChange={(checked) => {
                setShOnly(checked);
                setFrameSelectedRefs(null);
              }}
            />
            <Typography.Text>SH 图层</Typography.Text>
          </Space>
          <Space size={6}>
            <Switch
              size="small"
              aria-label="仅显示高风险器件"
              checked={highRiskOnly}
              onChange={(checked) => {
                setHighRiskOnly(checked);
                setFrameSelectedRefs(null);
              }}
            />
            <Typography.Text>高风险图层</Typography.Text>
          </Space>
          {frameSelectedRefs ? (
            <Tag
              closable
              color="blue"
              onClose={(event) => {
                event.preventDefault();
                setFrameSelectedRefs(null);
              }}
            >
              框选 {frameSelectedRefs.length} 项
            </Tag>
          ) : null}
        </Space>
        <Space>
          {(frameSelectedRefs || evidenceFilter !== "actionable" || shOnly || highRiskOnly) ? (
            <Button size="small" onClick={resetScopedFilters}>
              重置筛选
            </Button>
          ) : null}
          <Tooltip title="重置板图缩放与位置">
            <Button
              size="small"
              aria-label="重置板图视图"
              icon={<ReloadOutlined />}
              onClick={() => setCanvasKey((value) => value + 1)}
            />
          </Tooltip>
        </Space>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px minmax(0, 1fr)", gap: 12, minHeight: 520 }}>
        <section style={{ border: "1px solid #e2e5e9", borderRadius: 6, padding: 10, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <Typography.Text strong>NC 与待确认位号</Typography.Text>
            <Typography.Text type="secondary">{visibleNcItems.length} / {ncItems.length}</Typography.Text>
          </div>
          <RefdesVirtualList
            items={visibleNcItems}
            selectedRef={selectedRef}
            onHover={(ref) => setHoveredRef(ref || "")}
            onSelect={onSelectedRef}
          />
        </section>
        <section style={{ minWidth: 0, height: 520 }}>
          <PcbCanvas
            key={canvasKey}
            outline={result.board.outline_rings}
            components={layerComponents}
            side={side}
            highlightedRefs={highlightedRefs}
            onHover={(ref) => setHoveredRef(ref || "")}
            onSelect={onSelectedRef}
            onFrameSelect={(refs) => setFrameSelectedRefs(refs)}
            colorScheme="nc-emphasis"
          />
        </section>
      </div>
    </div>
  );
}


export function SmtLayoutPane() {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace<SmtLayoutWorkspace>(
    "smt_layout",
    {
      historyBom: "",
      historyDecisionManifest: "",
      historySemanticManifest: "",
      result: null,
      activeTab: "nc",
    },
    { heavyKeys: ["result"] },
  );
  const [smtFiles, setSmtFiles] = useState<File[]>([]);
  const [bomFile, setBomFile] = useState<File | undefined>();
  const [decisionFile, setDecisionFile] = useState<File | undefined>();
  const [semanticFile, setSemanticFile] = useState<File | undefined>();
  const [netlistFiles, setNetlistFiles] = useState<File[]>([]);
  const [historyBom, setHistoryBom] = useState(workspace.historyBom || "");
  const [historyDecisionManifest, setHistoryDecisionManifest] = useState(workspace.historyDecisionManifest || "");
  const [historySemanticManifest, setHistorySemanticManifest] = useState(workspace.historySemanticManifest || "");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [selectedRef, setSelectedRef] = useState("");
  const sanityAvailable = Boolean(
    netlistFiles.length || (workspace.result?.sanity && !("status" in workspace.result.sanity)),
  );

  useEffect(() => {
    setWorkspace((current) => ({
      ...current,
      historyBom,
      historyDecisionManifest,
      historySemanticManifest,
    }));
  }, [historyBom, historyDecisionManifest, historySemanticManifest, setWorkspace]);

  useEffect(() => {
    if (!sanityAvailable && workspace.activeTab === "sanity") {
      setWorkspace((current) => ({ ...current, activeTab: "nc" }));
    }
  }, [sanityAvailable, workspace.activeTab, setWorkspace]);

  async function handleRun() {
    if (!smtFiles.some((file) => file.name.toLowerCase() === "xy.txt")) {
      setError("请选择包含 XY.txt 的 SMT 资料目录。");
      return;
    }
    if (!historyBom && !bomFile) {
      setError("请选择 BOM 处理后生成的 PLM 或 OA 成品 BOM。");
      return;
    }
    if (netlistFiles.length && !netlistFiles.some((file) => file.name.toLowerCase() === "pstxnet.dat")) {
      setError("所选网表目录缺少 pstxnet.dat，请重新选择正确目录。");
      return;
    }
    if (netlistFiles.length && !netlistFiles.some((file) => file.name.toLowerCase() === "pstxprt.dat")) {
      setError("所选网表目录缺少 pstxprt.dat，请重新选择正确目录。");
      return;
    }
    setRunning(true);
    setError("");
    try {
      const [smtUpload, bomUpload, decisionUpload, semanticUpload, netlistUpload] = await Promise.all([
        uploadFiles(smtFiles),
        historyBom || !bomFile ? Promise.resolve(null) : uploadFiles([bomFile]),
        historyDecisionManifest || !decisionFile ? Promise.resolve(null) : uploadFiles([decisionFile]),
        historySemanticManifest || !semanticFile ? Promise.resolve(null) : uploadFiles([semanticFile]),
        netlistFiles.length ? uploadFiles(netlistFiles) : Promise.resolve(null),
      ]);
      const result = await runSmtLayout({
        smt_folder: smtUpload.folder,
        processed_bom: historyBom || bomUpload?.files[0]?.path || "",
        ...((historyDecisionManifest || decisionUpload?.files[0]?.path) ? {
          decision_manifest: historyDecisionManifest || decisionUpload?.files[0]?.path || "",
        } : {}),
        ...((historySemanticManifest || semanticUpload?.files[0]?.path) ? {
          semantic_manifest: historySemanticManifest || semanticUpload?.files[0]?.path || "",
        } : {}),
        ...(netlistUpload ? { netlist_folder: netlistUpload.folder } : {}),
      });
      setWorkspace((current) => ({ ...current, result }));
    } catch (runError) {
      setError(toUserMessage(runError));
    } finally {
      setRunning(false);
    }
  }

  function handleClear() {
    setError("");
    setSelectedRef("");
    setSmtFiles([]);
    setBomFile(undefined);
    setDecisionFile(undefined);
    setSemanticFile(undefined);
    setNetlistFiles([]);
    setHistoryBom("");
    setHistoryDecisionManifest("");
    setHistorySemanticManifest("");
    resetWorkspace();
  }

  const tabs = [
    {
      key: "nc",
      label: "NC 布局对照",
      children: <NcLayoutTab result={workspace.result} selectedRef={selectedRef} onSelectedRef={setSelectedRef} />,
    },
    { key: "fai", label: "首件核对表", children: <FaiChecklistTab result={workspace.result} /> },
    {
      key: "sanity",
      label: sanityAvailable ? (
        "三向一致性"
      ) : (
        <Tooltip title="需网表文件夹">
          <span>三向一致性</span>
        </Tooltip>
      ),
      disabled: !sanityAvailable,
      children: (
        <SanityReportTab
          result={workspace.result}
          onDrillDown={(ref) => {
            setSelectedRef(ref);
            setWorkspace((current) => ({ ...current, activeTab: "nc" }));
          }}
        />
      ),
    },
  ];

  return (
    <div className="smt-layout-pane">
      <div style={{ marginBottom: 18 }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          SMT 布局分析
        </Typography.Title>
        <Typography.Text type="secondary">
          对照贴片坐标、处理后 BOM 与 Cadence 网表，生成 NC 布局、首件核对表和三向一致性结果。
        </Typography.Text>
      </div>

      <div
        className="smt-layout-inputs"
        style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1fr) minmax(220px, 1fr) minmax(220px, 1fr)", gap: 10 }}
      >
        <DirectorySource
          kind="smt"
          title="SMT 资料目录"
          buttonLabel="选择 SMT 资料目录"
          files={smtFiles}
          onFiles={setSmtFiles}
        />
        <BomSource
          file={bomFile}
          decisionFile={decisionFile}
          semanticFile={semanticFile}
          historyBom={historyBom}
          historyDecisionManifest={historyDecisionManifest}
          historySemanticManifest={historySemanticManifest}
          onFile={setBomFile}
          onDecisionFile={setDecisionFile}
          onSemanticFile={setSemanticFile}
          onHistoryBom={(path, decisionManifest, semanticManifest) => {
            setHistoryBom(path);
            setHistoryDecisionManifest(decisionManifest || "");
            setHistorySemanticManifest(semanticManifest || "");
          }}
        />
        <DirectorySource
          kind="netlist"
          title="Cadence 网表目录（可选）"
          buttonLabel="选择网表目录"
          files={netlistFiles}
          onFiles={setNetlistFiles}
        />
      </div>

      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Button aria-label="开始分析" type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={handleRun}>
          开始分析
        </Button>
        <Button icon={<DeleteOutlined />} onClick={handleClear}>
          清空
        </Button>
      </Space>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
      <Tabs
        activeKey={workspace.activeTab}
        onChange={(activeTab) => setWorkspace((current) => ({ ...current, activeTab }))}
        items={tabs}
      />
    </div>
  );
}
