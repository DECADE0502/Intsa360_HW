import { type Dispatch, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FileOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { runTool, uploadFiles, type ToolInfo } from "../api/client";
import { HistoryBomPicker } from "../components/HistoryBomPicker";
import { useToolWorkspace } from "../state/toolWorkspace";

type SmtReviewItem = {
  key: string;
  ref: string;
  status: string;
  kind: string;
  severity?: string;
  part_number?: string;
  net_package?: string;
  bom_package?: string;
  model?: string;
  description?: string;
  name?: string;
  grade?: string;
  note?: string;
  refs?: string[];
};

function outputHref(path: string) {
  const normalized = path.replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const index = normalized.indexOf(marker);
  const rel = index >= 0 ? normalized.slice(index + marker.length) : normalized.replace(/^data\/outputs\//, "");
  return `/outputs/${encodeURI(rel)}`;
}

function textOf(value: unknown) {
  return String(value ?? "");
}

function statusColor(status: string) {
  if (status === "BOM 缺位号" || status === "同料多封装") return "red";
  if (status === "需要确认" || status === "BOM 多余位号") return "orange";
  if (status === "高风险封装") return "purple";
  if (status === "近似通过") return "cyan";
  if (status === "通过") return "green";
  return "gold";
}

function SmtUploadSlot({
  title,
  files,
  onFiles,
}: {
  title: string;
  files: File[];
  onFiles: Dispatch<SetStateAction<File[]>>;
}) {
  return (
    <Card className="smt-upload-card" size="small">
      <Typography.Text className="smt-upload-title">{title}</Typography.Text>
      <Upload
        accept=".dat"
        directory="true"
        webkitdirectory="true"
        multiple
        fileList={files.map((file, index) => ({ uid: String(index), name: file.name, status: "done" as const }))}
        beforeUpload={(file) => {
          if (file.name.toLowerCase().endsWith(".dat")) {
            onFiles((prev) => {
              if (prev.some((item) => item.name === file.name && item.size === file.size)) return prev;
              return [...prev, file];
            });
          }
          return false;
        }}
        onRemove={(file) => {
          onFiles((prev) => prev.filter((_, index) => String(index) !== file.uid));
          return true;
        }}
      >
        <Button icon={<FileOutlined />}>选择 Allegro 目录</Button>
      </Upload>
    </Card>
  );
}

function BomUploadSlot({ file, onFile }: { file?: File; onFile: (file?: File) => void }) {
  return (
    <Card className="smt-upload-card" size="small">
      <Typography.Text className="smt-upload-title">已处理 PLM/OA 成品 BOM</Typography.Text>
      <Upload
        accept=".xlsx,.xls"
        maxCount={1}
        fileList={file ? [{ uid: "0", name: file.name, status: "done" as const }] : []}
        beforeUpload={(next) => {
          onFile(next);
          return false;
        }}
        onRemove={() => {
          onFile(undefined);
          return true;
        }}
      >
        <Button icon={<FileExcelOutlined />}>选择 PLM/OA BOM</Button>
      </Upload>
    </Card>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`smt-metric smt-metric-${tone || "plain"}`}>
      <div className="smt-metric-value">{value}</div>
      <div className="smt-metric-label">{label}</div>
    </div>
  );
}

function SmtField({ label, value }: { label: string; value?: unknown }) {
  return (
    <div className="smt-field">
      <span>{label}</span>
      <p>{textOf(value) || "-"}</p>
    </div>
  );
}

function SimpleTable({ table }: { table?: any }) {
  const columns =
    table?.headers?.map((header: string, index: number) => ({
      title: header,
      dataIndex: String(index),
      key: String(index),
      ellipsis: true,
      width: index === 0 ? 140 : index === 3 ? 280 : undefined,
    })) || [];
  const data =
    table?.rows?.map((row: unknown[], index: number) => ({
      key: index,
      ...Object.fromEntries(row.map((value, i) => [String(i), value])),
    })) || [];
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
  return <Table size="small" columns={columns} dataSource={data} pagination={{ pageSize: 12 }} scroll={{ x: true }} />;
}

function filterOf(item: SmtReviewItem) {
  if (item.status === "BOM 缺位号") return "missing_bom";
  if (item.status === "BOM 多余位号") return "extra_bom";
  if (item.status === "同料多封装") return "multi_package";
  if (item.status === "高风险封装") return "high_risk";
  if (item.status === "NC 未贴跳过" || item.status === "非贴片对象跳过") return "skipped";
  if (item.status === "需要确认") return "manual";
  return item.kind || "all";
}

export function SmtPackageCheckPane({ tool }: { tool: ToolInfo }) {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace("smt_package_check", {
    historyBom: "",
    result: null as any,
    filter: "focus",
    query: "",
    selectedKey: "",
  });
  const [netlistFiles, setNetlistFiles] = useState<File[]>([]);
  const [bomFile, setBomFile] = useState<File | undefined>();
  const [historyBom, setHistoryBom] = useState<string>(() => String(workspace.historyBom || ""));
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(workspace.result || null);
  const [filter, setFilter] = useState(String(workspace.filter || "focus"));
  const [query, setQuery] = useState(String(workspace.query || ""));
  const [selectedKey, setSelectedKey] = useState(String(workspace.selectedKey || ""));

  useEffect(() => {
    setWorkspace({ historyBom, result, filter, query, selectedKey });
  }, [historyBom, result, filter, query, selectedKey]);

  const review = result?.smt_package_review;
  const items: SmtReviewItem[] = review?.items || [];
  const focusItems: SmtReviewItem[] = review?.focus_items || [];
  const visibleItems = useMemo(() => {
    const source = filter === "focus" ? focusItems : items;
    const q = query.trim().toLowerCase();
    return source.filter((item) => {
      const byFilter = filter === "focus" || filter === "all" || filterOf(item) === filter;
      const hay = `${item.ref} ${item.status} ${item.part_number} ${item.net_package} ${item.bom_package} ${item.model} ${item.description} ${item.name} ${item.note}`.toLowerCase();
      return byFilter && (!q || hay.includes(q));
    });
  }, [items, focusItems, filter, query]);
  const selected = items.find((item) => item.key === selectedKey) || visibleItems[0] || items[0];
  const counts = review?.status_counts || {};
  const filterOptions = [
    { label: "重点", value: "focus", count: focusItems.length },
    { label: "需确认", value: "manual", count: counts.manual || 0 },
    { label: "缺位号", value: "missing_bom", count: counts.missing_bom || 0 },
    { label: "多余", value: "extra_bom", count: counts.extra_bom || 0 },
    { label: "多封装", value: "multi_package", count: counts.multi_package || 0 },
    { label: "高风险", value: "high_risk", count: counts.high_risk || 0 },
    { label: "已跳过", value: "skipped", count: (counts.nc_skipped || 0) + (counts.non_smt_skipped || 0) },
    { label: "全部", value: "all", count: items.length },
  ];

  useEffect(() => {
    if (review) setSelectedKey(review.focus_items?.[0]?.key || review.items?.[0]?.key || "");
  }, [review]);

  async function handleRun() {
    if (!netlistFiles.some((file) => file.name.toLowerCase() === "pstxprt.dat")) {
      setResult({ status: "error", error: "请选择包含 pstxprt.dat 的 Allegro 目录。" });
      return;
    }
    if (!historyBom && !bomFile) {
      setResult({ status: "error", error: "请选择 BOM 处理后生成的 PLM 或 OA 成品 BOM，不要选择 Capture 原始 BOM。" });
      return;
    }
    setRunning(true);
    try {
      const [netlistUpload, bomUpload] = await Promise.all([
        uploadFiles(netlistFiles),
        historyBom || !bomFile ? Promise.resolve(null) : uploadFiles([bomFile]),
      ]);
      const next = await runTool("smt_package_check", {
        netlist: netlistUpload.files.map((file) => file.path),
        bom: historyBom || bomUpload?.files[0]?.path,
      });
      setResult(next);
      setFilter("focus");
      setQuery("");
    } catch (err: any) {
      setResult({ status: "error", error: err.message || "运行失败" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="smt-workbench">
      <div className="smt-head">
        <div>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{tool.description}</Typography.Paragraph>
        </div>
        {result?.outputs?.length ? (
          <Space wrap>
            {result.outputs.map((path: string) => (
              <Button key={path} href={outputHref(path)} icon={<DownloadOutlined />}>
                下载封装检查报告
              </Button>
            ))}
          </Space>
        ) : null}
      </div>

      <div className="smt-upload-grid">
        <SmtUploadSlot title="Allegro 网表目录" files={netlistFiles} onFiles={setNetlistFiles} />
        <Card className="smt-upload-card" size="small">
          <Typography.Text className="smt-upload-title">已处理 PLM/OA 成品 BOM</Typography.Text>
          <Space direction="vertical" style={{ width: "100%" }}>
            <HistoryBomPicker value={historyBom} onChange={setHistoryBom} />
            <BomUploadSlot file={bomFile} onFile={setBomFile} />
          </Space>
        </Card>
        <Card size="small" className="smt-run-card">
          <Space wrap>
            <Button type="primary" loading={running} onClick={handleRun} icon={<PlayCircleOutlined />}>
              开始检查
            </Button>
            <Button
              onClick={() => {
                setNetlistFiles([]);
                setBomFile(undefined);
                setHistoryBom("");
                setResult(null);
                resetWorkspace();
              }}
              icon={<DeleteOutlined />}
            >
              清空
            </Button>
          </Space>
        </Card>
      </div>

      {!result ? (
        <Alert
          type="info"
          showIcon
          message="选择 Allegro 目录和已处理后的 PLM/OA BOM 后开始检查"
          description="请使用 BOM 处理工具生成的 PLM 或 OA 成品 BOM，不要选择 Capture 原始 BOM；目录中必须包含 pstxprt.dat，系统会自动跳过 NC 未贴、测试点、短接和安装孔等非贴片对象。"
        />
      ) : null}
      {result?.status && result.status !== "ok" ? <Alert type="error" showIcon message={result.error || result.message || "运行失败"} /> : null}

      {result?.status === "ok" ? (
        <>
          <div className="smt-summary-grid">
            <Metric label="网表位号" value={result.summary?.total || 0} tone="plain" />
            <Metric label="通过" value={counts.passed || 0} tone="passed" />
            <Metric label="需要确认" value={counts.manual || 0} tone="manual" />
            <Metric label="BOM 缺位号" value={counts.missing_bom || 0} tone="danger" />
            <Metric label="BOM 多余位号" value={counts.extra_bom || 0} tone="warn" />
            <Metric label="同料多封装" value={counts.multi_package || 0} tone="danger" />
            <Metric label="高风险封装" value={counts.high_risk || 0} tone="risk" />
            <Metric label="跳过未贴/工艺" value={(counts.nc_skipped || 0) + (counts.non_smt_skipped || 0)} tone="skip" />
          </div>

          <Tabs
            className="smt-tabs"
            items={[
              {
                key: "review",
                label: "封装审查",
                children: (
                  <div className="smt-shell">
                    <aside className="smt-rail">
                      <div className="smt-filter-grid">
                        {filterOptions.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={`smt-filter-chip ${filter === option.value ? "is-active" : ""}`}
                            onClick={() => setFilter(option.value)}
                          >
                            <span>{option.label}</span>
                            <b>{option.count}</b>
                          </button>
                        ))}
                      </div>
                      <Input allowClear prefix={<SearchOutlined />} placeholder="搜索位号 / 编码 / 封装 / 描述" value={query} onChange={(event) => setQuery(event.target.value)} />
                      <div className="smt-focus-list">
                        {visibleItems.map((item) => (
                          <button
                            type="button"
                            key={item.key}
                            className={`smt-focus-item ${selected?.key === item.key ? "is-active" : ""}`}
                            onClick={() => setSelectedKey(item.key)}
                          >
                            <span className="smt-focus-top">
                              <span className="smt-focus-ref">{item.ref}</span>
                              <Tag color={statusColor(item.status)}>{item.status}</Tag>
                            </span>
                            <span className="smt-focus-code">{item.part_number || "-"}</span>
                            <span className="smt-focus-package">{item.net_package || item.bom_package || "-"}</span>
                            <span className="smt-focus-msg">{item.note}</span>
                          </button>
                        ))}
                      </div>
                    </aside>

                    <main className="smt-detail">
                      {selected ? (
                        <>
                          <div className="smt-detail-head">
                            <div>
                              <Typography.Title level={5}>{selected.ref}</Typography.Title>
                              <Typography.Text type="secondary">{review?.review_guide?.[selected.status] || selected.note}</Typography.Text>
                            </div>
                            <Tag color={statusColor(selected.status)}>{selected.status}</Tag>
                          </div>
                          <div className="smt-field-grid">
                            <SmtField label="网表封装" value={selected.net_package} />
                            <SmtField label="BOM 封装" value={selected.bom_package} />
                            <SmtField label="物料编码" value={selected.part_number} />
                            <SmtField label="规格型号" value={selected.model} />
                            <SmtField label="物料名称" value={selected.name} />
                            <SmtField label="优选等级" value={selected.grade} />
                            <SmtField label="描述" value={selected.description} />
                            <SmtField label="说明" value={selected.note} />
                          </div>
                          <Typography.Title level={5} className="smt-section-title">
                            当前筛选结果
                          </Typography.Title>
                          <Table
                            size="small"
                            dataSource={visibleItems.map((item) => ({ ...item, key: item.key }))}
                            pagination={{ pageSize: 10 }}
                            scroll={{ x: true }}
                            onRow={(record) => ({ onClick: () => setSelectedKey(record.key) })}
                            columns={[
                              { title: "位号", dataIndex: "ref", key: "ref", ellipsis: true },
                              { title: "状态", dataIndex: "status", key: "status", render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag> },
                              { title: "编码", dataIndex: "part_number", key: "part_number", ellipsis: true },
                              { title: "网表封装", dataIndex: "net_package", key: "net_package", ellipsis: true },
                              { title: "BOM 封装", dataIndex: "bom_package", key: "bom_package", ellipsis: true },
                            ]}
                          />
                        </>
                      ) : (
                        <Empty description="暂无封装审查项" />
                      )}
                    </main>

                    <aside className="smt-inspector">
                      <Typography.Title level={5}>复核规则</Typography.Title>
                      <div className="smt-guide-list">
                        {["BOM 缺位号", "BOM 多余位号", "同料多封装", "高风险封装", "NC 未贴跳过", "非贴片对象跳过", "需要确认"].map((key) => (
                          <div key={key} className="smt-guide-item">
                            <Tag color={statusColor(key)}>{key}</Tag>
                            <Typography.Paragraph type="secondary">{review?.review_guide?.[key]}</Typography.Paragraph>
                          </div>
                        ))}
                      </div>
                    </aside>
                  </div>
                ),
              },
              { key: "table", label: "完整表格", children: <SimpleTable table={result.table} /> },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
