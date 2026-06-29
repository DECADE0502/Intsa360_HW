import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Input,
  List,
  Result,
  Space,
  Steps,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  DownloadOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { runTool, uploadFiles } from "../api/client";

const { Dragger } = Upload;
const CONFIG =
  "{Item}\\t{Quantity}\\t{Reference}\\t{Part Number}\\t{Value}\\t{规格型号}\\t{器件描述（新整理）}\\t{物料名称}\\t{等级}\\t{PCB Footprint}\\t{PCB封装}\\t{Part Type}\\t{Part Reference}\\t{Source Package}\\t{Source Part}";

type Stage = "source" | "review" | "process" | "risk" | "deliver";
type Extra = { code: string; model: string; desc: string; qty: string; refs: string };

function fname(p: string) {
  return p.split(/[\\/]/).pop() || p;
}

function bname(p: string) {
  return fname(p).replace(/\.xlsx?$/i, "");
}

function hasBomConflicts(pres: any) {
  const conflicts = pres?.conflicts || [];
  return pres?.reason === "part_property_conflicts" || (pres?.status !== "ok" && ((pres?.conflict_count || 0) > 0 || conflicts.length > 0));
}

function hasShieldCandidates(pres: any) {
  return pres?.reason === "shield_bracket_candidates" && (pres?.shield_candidates || []).length > 0;
}

function renderFullRefs(refs: string[] = []) {
  if (!refs.length) return <Typography.Text type="secondary">-</Typography.Text>;
  return (
    <div className="ref-wrap">
      {refs.map((ref) => (
        <Tag key={ref}>{ref}</Tag>
      ))}
    </div>
  );
}

export function BomProcessWizard() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const presetSource = params.get("source") || "";
  const presetName = params.get("name") || "";

  const [stage, setStage] = useState<Stage>(presetSource ? "review" : "source");
  const [sp, setSp] = useState(presetSource);
  const [name, setName] = useState(presetName);
  const [pcode, setPcode] = useState("203010100819");
  const [pdesc, setPdesc] = useState("");
  const [fmts, setFmts] = useState(["plm", "oa"]);
  const [extras, setExtras] = useState<Extra[]>([]);
  const [pres, setPres] = useState<any>(null);
  const [rres, setRres] = useState<any>(null);
  const [rrun, setRrun] = useState(false);
  const [running, setRunning] = useState(false);
  const [conflictChoices, setConflictChoices] = useState<Record<string, number>>({});
  const [confirmShields, setConfirmShields] = useState(false);

  const steps = ["来源", "识别", "处理", "审查", "交付"];
  const si = { source: 0, review: 1, process: 2, risk: 3, deliver: 4 }[stage];

  async function onFile(f: File) {
    try {
      const u = await uploadFiles([f]);
      setSp(u.files[0]?.path || "");
      setName((p) => p || bname(f.name));
      message.success("已接收文件");
      setStage("review");
    } catch (e: any) {
      message.error(e.message);
    }
    return false;
  }

  useEffect(() => {
    if (stage !== "process" || pres) return;
    setRunning(true);
    runTool("bom_process", {
      source_bom: sp,
      formats: fmts,
      name,
      parent_code: pcode,
        parent_desc: pdesc,
        extras: extras.filter((e) => e.code),
        confirm_shields: confirmShields ? true : undefined,
      })
      .then((r) => {
        setPres(r);
        if (r.status === "ok" && !hasBomConflicts(r)) setStage("risk");
      })
      .catch((e) => setPres({ status: "error", error: e.message }))
      .finally(() => setRunning(false));
  }, [stage]);

  useEffect(() => {
    if (stage !== "risk" || rres || rrun) return;
    const pf = pres?.process_file || pres?.outputs?.[0];
    if (!pf) {
      setRres({ status: "error", error: "尚未生成成品 BOM，请先完成编码冲突确认和 BOM 处理。" });
      return;
    }
    setRrun(true);
    runTool("bom_risk_check", { bom: pf })
      .then(setRres)
      .catch((e) => setRres({ status: "error", error: e.message }))
      .finally(() => setRrun(false));
  }, [stage]);

  async function applyMerge(merge: boolean) {
    setRunning(true);
    try {
      const r = await runTool("bom_process", {
        source_bom: sp,
        formats: fmts,
        name,
        parent_code: pcode,
        parent_desc: pdesc,
        extras: extras.filter((e) => e.code),
        merge_conflicts: merge,
        conflict_choices: merge ? conflictChoices : {},
        confirm_shields: confirmShields,
      });
      setPres(r);
      setConflictChoices({});
      if (r.status === "ok" && !hasBomConflicts(r)) setStage("risk");
    } catch (e: any) {
      setPres({ status: "error", error: e.message });
    } finally {
      setRunning(false);
    }
  }

  async function applyRecommendedMerge() {
    setRunning(true);
    try {
      const r = await runTool("bom_process", {
        source_bom: sp,
        formats: fmts,
        name,
        parent_code: pcode,
        parent_desc: pdesc,
        extras: extras.filter((e) => e.code),
        merge_conflicts: true,
        conflict_choices: {},
        confirm_shields: confirmShields,
      });
      setPres(r);
      setConflictChoices({});
      if (r.status === "ok" && !hasBomConflicts(r)) setStage("risk");
    } catch (e: any) {
      setPres({ status: "error", error: e.message });
    } finally {
      setRunning(false);
    }
  }

  async function confirmShieldBrackets() {
    setRunning(true);
    try {
      setConfirmShields(true);
      const r = await runTool("bom_process", {
        source_bom: sp,
        formats: fmts,
        name,
        parent_code: pcode,
        parent_desc: pdesc,
        extras: extras.filter((e) => e.code),
        confirm_shields: true,
      });
      setPres(r);
      if (r.status === "ok" && !hasBomConflicts(r) && !hasShieldCandidates(r)) setStage("risk");
    } catch (e: any) {
      setPres({ status: "error", error: e.message });
    } finally {
      setRunning(false);
    }
  }

  async function dl() {
    const all = [...(pres?.outputs || []), ...(rres?.outputs || [])];
    if (!all.length) {
      message.warning("暂无可下载文件");
      return;
    }
    try {
      const r = await fetch("/api/package", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name || "BOM", files: all }),
      });
      if (!r.ok) throw new Error("打包失败");
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u;
      a.download = `${name || "BOM"}.zip`;
      a.click();
      URL.revokeObjectURL(u);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Steps size="small" current={si} items={steps.map((t) => ({ title: t }))} />
      {stage === "source" && <SourceView presetSource={presetSource} onFile={onFile} onUsePreset={() => setStage("review")} />}
      {stage === "review" && (
        <ReviewView
          sp={sp}
          name={name}
          setName={setName}
          pcode={pcode}
          setPcode={setPcode}
          pdesc={pdesc}
          setPdesc={setPdesc}
          fmts={fmts}
          setFmts={setFmts}
          extras={extras}
          setExtras={setExtras}
          onNext={() => setStage("process")}
        />
      )}
      {stage === "process" && (
        <ProcessView
          running={running}
          pres={pres}
          conflictChoices={conflictChoices}
          setConflictChoices={setConflictChoices}
          onRecommendedMerge={applyRecommendedMerge}
          onApply={() => applyMerge(true)}
          onSplit={() => applyMerge(false)}
          onConfirmShields={confirmShieldBrackets}
          onNext={() => setStage("risk")}
          onBack={() => {
            setPres(null);
            setStage("review");
          }}
        />
      )}
      {stage === "risk" && <RiskView rrun={rrun} rres={rres} onNext={() => setStage("deliver")} onBack={() => setStage("process")} />}
      {stage === "deliver" && (
        <DeliverView
          pres={pres}
          rres={rres}
          name={name}
          onDownload={dl}
          onReset={() => {
            setPres(null);
            setRres(null);
            setConflictChoices({});
            setStage("review");
          }}
        />
      )}
    </Space>
  );
}

function SourceView({ presetSource, onFile, onUsePreset }: any) {
  if (presetSource) {
    return (
      <Card>
        <Alert type="success" showIcon message="已从 Cadence 接收 BOM 文件" />
        <Button type="primary" block style={{ marginTop: 16 }} onClick={onUsePreset}>
          使用该文件
        </Button>
      </Card>
    );
  }
  return (
    <>
      <Alert type="info" showIcon message="从 Capture 菜单 insta360_HW → Export and Process BOM 自动导入" style={{ marginBottom: 16 }} />
      <Dragger accept=".xlsx,.xls" maxCount={1} beforeUpload={onFile} showUploadList={false}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p>点击或拖拽 Capture 导出的 BOM 文件</p>
      </Dragger>
    </>
  );
}

function ReviewView(props: any) {
  const { sp, name, setName, pcode, setPcode, pdesc, setPdesc, fmts, setFmts, extras, setExtras, onNext } = props;
  const [copied, setCopied] = useState(false);
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Alert type="success" showIcon message="文件已接收" description={<Typography.Text code>{sp}</Typography.Text>} />
      <Input addonBefore="成品名称" value={name} onChange={(e: any) => setName(e.target.value)} />
      <Space.Compact block>
        <Input addonBefore="父项编码" value={pcode} onChange={(e: any) => setPcode(e.target.value)} />
        <Input value={pdesc} onChange={(e: any) => setPdesc(e.target.value)} placeholder="父项描述，默认使用成品名称" />
      </Space.Compact>
      <Card size="small">
        <Checkbox.Group value={fmts} onChange={(v: any) => setFmts(v)}>
          <Checkbox value="plm">PLM 模板</Checkbox>
          <Checkbox value="oa">OA 模板</Checkbox>
        </Checkbox.Group>
      </Card>
      <Collapse ghost items={[{ key: "extras", label: "附加物料（PCB / 屏蔽罩）", children: <XSection extras={extras} onChange={setExtras} /> }]} />
      <Collapse
        ghost
        items={[
          {
            key: "cfg",
            label: "Capture 导出配置",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Input.TextArea readOnly value={CONFIG} autoSize />
                <Button
                  size="small"
                  onClick={() => {
                    navigator.clipboard.writeText(CONFIG);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                >
                  {copied ? "已复制" : "复制配置"}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Button type="primary" size="large" block onClick={onNext} icon={<RightOutlined />}>
        确认无误，开始处理
      </Button>
    </Space>
  );
}

function ProcessView({ running, pres, conflictChoices, setConflictChoices, onRecommendedMerge, onApply, onSplit, onConfirmShields, onNext, onBack }: any) {
  const [activeConflictCode, setActiveConflictCode] = useState<string>("");
  if (running) return <Result icon={<FileTextOutlined spin />} title="正在处理 BOM…" subTitle="解析字段、过滤 NC 器件、合并位号、生成 PLM/OA" />;
  if (!pres) return null;
  if (pres.status === "error") return <Result status="error" title="处理失败" subTitle={pres.error} extra={<Button onClick={onBack}>返回修改</Button>} />;

  const s = pres.summary || {};
  const conflicts = pres.conflicts || [];
  const hasC = hasBomConflicts(pres);
  const hasS = hasShieldCandidates(pres);
  const shieldCandidates = pres.shield_candidates || [];
  const allDone = !hasC || conflicts.every((c: any) => conflictChoices[c.code] !== undefined);
  const activeConflict = conflicts.find((c: any) => c.code === activeConflictCode) || conflicts[0];
  const selectedCount = conflicts.filter((c: any) => conflictChoices[c.code] !== undefined).length;

  return (
    <div className="process-grid">
      <div className="process-sidebar">
        <Card size="small" title="处理概览">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="料号">{s.records ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="位号">{s.total_positions ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="已过滤">{s.excluded ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="历史冲突">{s.conflicts ?? conflicts.length ?? 0}</Descriptions.Item>
          </Descriptions>
        </Card>
        <Card size="small" title="下一步">
          {hasS ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text type="secondary">请确认 SH 位号是否为屏蔽支架/屏蔽罩。确认后这些物料会进入最终 BOM。</Typography.Text>
              <Button type="primary" block onClick={onConfirmShields}>
                确认作为屏蔽支架进入 BOM
              </Button>
              <Button block onClick={onBack}>
                返回修改附加物料
              </Button>
            </Space>
          ) : hasC ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text type="secondary">可直接按系统推荐合并；需要精修时再逐项选择要保留的描述。</Typography.Text>
              <Button type="primary" block onClick={onRecommendedMerge}>
                按推荐合并
              </Button>
              <Button type="primary" block disabled={!allDone} onClick={onApply}>
                按所选项合并
              </Button>
              <Button block onClick={onSplit}>
                不合并，保留差异
              </Button>
            </Space>
          ) : (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Alert type="success" showIcon message="BOM 已生成，可以进入风险审查" />
              <Button type="primary" block onClick={onNext}>
                进入风险审查 <RightOutlined />
              </Button>
            </Space>
          )}
          <Button style={{ marginTop: 12 }} block onClick={onBack}>
            返回修改
          </Button>
        </Card>
      </div>
      <div className="conflict-main">
        {hasS ? (
          <Card
            size="small"
            title={<><WarningOutlined style={{ color: "#f0a040" }} /> 发现 {shieldCandidates.length} 个 SH 屏蔽支架候选</>}
          >
            <Alert
              type="warning"
              showIcon
              message="SH 位号将作为屏蔽支架/屏蔽罩进入最终 BOM"
              description="请核对物料编码、名称、型号和位号，确认无误后继续。"
              style={{ marginBottom: 12 }}
            />
            <Table
              size="small"
              pagination={false}
              rowKey={(row: any, index) => `${row.code}-${index}`}
              dataSource={shieldCandidates}
              columns={[
                { title: "子项编码", dataIndex: "code", width: 150 },
                { title: "名称", dataIndex: "name", width: 140 },
                { title: "型号", dataIndex: "model", ellipsis: true },
                { title: "描述", dataIndex: "desc", ellipsis: true },
                { title: "位号", dataIndex: "refs", render: (refs: string[]) => renderFullRefs(refs) },
              ]}
            />
          </Card>
        ) : hasC ? (
          <Card
            size="small"
            title={<><WarningOutlined style={{ color: "#f0a040" }} /> 发现 {conflicts.length} 个编码冲突</>}
            extra={<Typography.Text type="secondary">已选择 {selectedCount}/{conflicts.length}</Typography.Text>}
          >
            {conflicts.length === 0 ? (
              <Alert type="warning" showIcon message="后端已完成处理，但页面仍处于冲突确认状态。请刷新页面或重新处理。" />
            ) : (
              <div className="conflict-workbench">
                <div className="conflict-index-list">
                  {conflicts.map((c: any, idx: number) => {
                    const selected = conflictChoices[c.code];
                    const variants = c.variants || [];
                    return (
                      <button
                        key={c.code}
                        type="button"
                        className={`conflict-index-item ${activeConflict?.code === c.code ? "is-active" : ""}`}
                        onClick={() => setActiveConflictCode(c.code)}
                      >
                        <span className="conflict-index-code">{idx + 1}. {c.code}</span>
                        <span className="conflict-index-meta">{variants.length} 项 · {selected === undefined ? "未选择" : `保留第 ${selected + 1} 项`}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="conflict-detail-pane">
                  <CConflict
                    c={activeConflict}
                    selected={conflictChoices[activeConflict?.code]}
                    onSelect={(index: number) => setConflictChoices((p: any) => ({ ...p, [activeConflict.code]: index }))}
                  />
                </div>
              </div>
            )}
          </Card>
        ) : (
          <Card size="small" title="生成结果">
            <List
              size="small"
              dataSource={[...(pres?.outputs || []), pres?.nc_summary].filter(Boolean)}
              renderItem={(p: string) => (
                <List.Item>
                  <FileTextOutlined style={{ marginRight: 8, color: "#1677ff" }} />
                  {fname(p)}
                </List.Item>
              )}
            />
          </Card>
        )}
      </div>
    </div>
  );
}

function RiskView({ rrun, rres, onNext, onBack }: any) {
  if (rrun) return <Result icon={<SafetyCertificateOutlined spin />} title="正在风险审查…" subTitle="检查 PCB、屏蔽罩、NC、等级、位号类型" />;
  if (!rres) return null;
  if (rres.status === "error") return <Result status="warning" title="检查未完成" subTitle={rres.error} extra={<Button type="primary" onClick={onNext}>跳过，直接导出</Button>} />;

  const rep = rres.risk_report || {};
  const findings = rep.findings || [];
  const warns = findings.filter((f: any) => f.status === "warn");
  const grades = rep.grade_flags || [];
  const types = rep.type_flags || [];
  const outputs = rres.outputs || [];
  const findingColumns = [
    { title: "检查项", dataIndex: "name", ellipsis: true },
    { title: "状态", dataIndex: "status", width: 90, render: (v: string) => <Tag color={v === "warn" ? "orange" : v === "ok" ? "green" : "blue"}>{v}</Tag> },
    { title: "说明", dataIndex: "message", ellipsis: true },
  ];
  const gradeColumns = [
    { title: "编号", dataIndex: "code", ellipsis: true },
    { title: "描述", dataIndex: "desc", ellipsis: true },
    { title: "位号", dataIndex: "refs", ellipsis: true },
    { title: "等级", dataIndex: "grade", width: 120, render: (v: string) => <Tag color="orange">{v}</Tag> },
  ];
  const typeColumns = [
    { title: "位号", dataIndex: "ref", width: 120, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
    { title: "编号", dataIndex: "code", ellipsis: true },
    { title: "提示", dataIndex: "note", ellipsis: true, render: (v: string) => <Tag color="orange">{v}</Tag> },
  ];
  const riskTabs = [
    {
      key: "risk-overview",
      label: "审查概览",
      children: (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="检查项">{findings.length}</Descriptions.Item>
            <Descriptions.Item label="通过">{findings.filter((f: any) => f.status === "ok").length}</Descriptions.Item>
            <Descriptions.Item label="警告">{warns.length}</Descriptions.Item>
            <Descriptions.Item label="提示">{findings.filter((f: any) => f.status === "info").length}</Descriptions.Item>
          </Descriptions>
          {warns.length ? (
            <Alert type="warning" showIcon message={`发现 ${warns.length} 个风险项`} description="请按页签逐项核对，确认后再进入导出交付。" />
          ) : (
            <Alert type="success" showIcon message="审查通过，无警告项" />
          )}
        </Space>
      ),
    },
    {
      key: "risk-basic",
      label: `基础检查 ${warns.length ? `(${warns.length})` : ""}`,
      children: <Table size="small" rowKey={(row: any, index) => `${row.name}-${index}`} dataSource={findings} columns={findingColumns} pagination={{ pageSize: 8 }} />,
    },
    {
      key: "risk-grade",
      label: `优选等级 ${grades.length ? `(${grades.length})` : ""}`,
      children: grades.length ? (
        <Table size="small" rowKey={(row: any, index) => `${row.code}-${index}`} dataSource={grades} columns={gradeColumns} pagination={{ pageSize: 8 }} />
      ) : (
        <Alert type="success" showIcon message="未发现非优选等级风险" />
      ),
    },
    {
      key: "risk-type",
      label: `位号类型 ${types.length ? `(${types.length})` : ""}`,
      children: types.length ? (
        <Table size="small" rowKey={(row: any, index) => `${row.ref}-${index}`} dataSource={types} columns={typeColumns} pagination={{ pageSize: 8 }} />
      ) : (
        <Alert type="success" showIcon message="未发现位号类型不符" />
      ),
    },
    {
      key: "risk-outputs",
      label: `审查文件 ${outputs.length ? `(${outputs.length})` : ""}`,
      children: (
        <List
          size="small"
          dataSource={outputs}
          renderItem={(p: string) => (
            <List.Item>
              <FileTextOutlined style={{ marginRight: 8, color: "#1677ff" }} />
              {fname(p)}
            </List.Item>
          )}
        />
      ),
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card size="small" title="风险审查">
        <Tabs items={riskTabs} />
      </Card>
      <Space>
        <Button type="primary" size="large" onClick={onNext}>进入导出交付 <RightOutlined /></Button>
        <Button onClick={onBack}>返回上一步</Button>
      </Space>
    </Space>
  );
}

function BomPreviewTable({ preview }: any) {
  if (!preview) {
    return <Alert type="info" showIcon message="暂无可预览的最终 BOM 数据" />;
  }
  const headers = preview.headers || [];
  const rows = preview.rows || [];
  if (!headers.length || !rows.length) {
    return <Alert type="info" showIcon message="暂无可预览的最终 BOM 数据" />;
  }
  const dataSource = rows.map((row: any[], index: number) => {
    const item: Record<string, any> = { key: index };
    headers.forEach((_: string, col: number) => {
      item[`c${col}`] = row?.[col] ?? "";
    });
    return item;
  });
  const columns = headers.map((header: string, col: number) => ({
    title: header || `列 ${col + 1}`,
    dataIndex: `c${col}`,
    ellipsis: true,
  }));
  return (
    <div className="final-bom-preview">
      <Table size="small" dataSource={dataSource} columns={columns} pagination={{ pageSize: 10 }} scroll={{ x: true }} />
    </div>
  );
}

function DeliverView({ pres, rres, name, onDownload, onReset }: any) {
  const all = [...(pres?.outputs || []), ...(rres?.outputs || [])];
  const s = pres?.summary || {};
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Result status="success" title="处理完成" subTitle={`${s.records || 0} 个料号 · ${s.total_positions || 0} 个位号 · ${all.length} 个文件`} />
      <Card size="small" title="最终 BOM 预览">
        <BomPreviewTable preview={pres?.preview} />
      </Card>
      <Card size="small" title="输出文件">
        <List
          size="small"
          dataSource={all}
          renderItem={(p: string) => (
            <List.Item actions={[<Button key="dl" type="link" icon={<DownloadOutlined />} href={`/outputs/${encodeURIComponent(fname(p))}`}>下载</Button>]}>
              <FileTextOutlined style={{ marginRight: 8, color: "#1677ff" }} />
              {fname(p)}
            </List.Item>
          )}
        />
      </Card>
      <Button type="primary" size="large" block icon={<DownloadOutlined />} onClick={onDownload}>下载全部资源（ZIP）</Button>
      <div style={{ textAlign: "center" }}><Button type="link" icon={<ReloadOutlined />} onClick={onReset}>重新处理</Button></div>
    </Space>
  );
}

function CConflict({ c, selected, onSelect }: any) {
  const variants = c?.variants || [];
  return (
    <div>
      <div className="conflict-detail-head">
        <div>
          <Typography.Text type="secondary">当前编码</Typography.Text>
          <Typography.Title level={4} style={{ margin: 0 }}>{c?.code}</Typography.Title>
        </div>
        <Tag color={selected === undefined ? "orange" : "blue"}>{selected === undefined ? "待选择" : `已保留第 ${selected + 1} 项`}</Tag>
      </div>
      <div className="variant-list">
        {variants.map((v: any, i: number) => (
          <div key={i} className={`variant-card ${selected === i ? "is-selected" : ""}`}>
            <div className="variant-card-title">
              <Space>
                <Tag color={selected === i ? "blue" : "default"}>候选 {i + 1}</Tag>
                <Typography.Text strong>{v.name || "-"}</Typography.Text>
                <Tag>{v.grade || "未分级"}</Tag>
                <Tag color="purple">数量 {v.count ?? "-"}</Tag>
              </Space>
              <Button size="small" type={selected === i ? "primary" : "default"} onClick={() => onSelect(i)}>
                {selected === i ? "已保留" : "保留此项"}
              </Button>
            </div>
            <div className="variant-fields">
              <div className="variant-field variant-field--wide">
                <span>描述</span>
                <p>{v.desc || "-"}</p>
              </div>
              <div className="variant-field">
                <span>型号</span>
                <p>{v.model || "-"}</p>
              </div>
              <div className="variant-field">
                <span>名称</span>
                <p>{v.name || "-"}</p>
              </div>
              <div className="variant-field variant-field--wide">
                <span>受影响位号</span>
                {renderFullRefs(v.refs)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function XSection({ extras, onChange }: { extras: Extra[]; onChange: (v: Extra[]) => void }) {
  const add = () => onChange([...extras, { code: "", model: "", desc: "", qty: "", refs: "" }]);
  const upd = (i: number, k: string, v: string) => {
    const n = [...extras];
    n[i] = { ...n[i], [k]: v };
    onChange(n);
  };
  const del = (i: number) => onChange(extras.filter((_, idx) => idx !== i));
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {extras.map((e, i) => (
        <Space.Compact key={i} block>
          <Input placeholder="编号" value={e.code} onChange={(ev) => upd(i, "code", ev.target.value)} />
          <Input placeholder="型号" value={e.model} onChange={(ev) => upd(i, "model", ev.target.value)} />
          <Input placeholder="描述" value={e.desc} onChange={(ev) => upd(i, "desc", ev.target.value)} />
          <Input placeholder="数量" value={e.qty} onChange={(ev) => upd(i, "qty", ev.target.value)} style={{ width: 72 }} />
          <Input placeholder="位号" value={e.refs} onChange={(ev) => upd(i, "refs", ev.target.value)} />
          <Button danger onClick={() => del(i)}>删除</Button>
        </Space.Compact>
      ))}
      <Button type="dashed" block onClick={add}>添加附加物料</Button>
    </Space>
  );
}
