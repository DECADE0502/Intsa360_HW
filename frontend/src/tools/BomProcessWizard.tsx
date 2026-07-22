import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Input,
  List,
  Result,
  Select,
  Space,
  Steps,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from "antd";
import {
  CopyOutlined,
  DownloadOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  RollbackOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { runTool, secureFetch, uploadFiles } from "../api/client";
import { ApiError, toUserMessage } from "../api/errors";
import { useToolWorkspace } from "../state/toolWorkspace";
import { packageDownloadName } from "../utils/downloadName";
import { outputHref } from "../utils/outputHref";
import { riskStatusText } from "../utils/statusText";
import {
  buildRecommendedConflictChoices,
  conflictChoiceComplete,
  normalizeConflictChoice,
  type ConflictChoice,
} from "./bomConflictChoices";
import {
  PlacementReview,
  seedPlacementResolutions,
  type PlacementResolution,
} from "./PlacementReview";

export { PlacementReview } from "./PlacementReview";
export type { PlacementResolution } from "./PlacementReview";

const { Dragger } = Upload;
const ASSETS_UPDATED_EVENT = "insta360_hw:assets-updated";
const CONFIG =
  "{Item}\\t{Quantity}\\t{Reference}\\t{Part Number}\\t{Value}\\t{规格型号}\\t{器件描述（新整理）}\\t{器件描述（旧）}\\t{物料名称}\\t{等级}\\t{等级备注}\\t{制造商}\\t{datasheet}\\t{PCB Footprint}\\t{PCB封装}\\t{Part Type}\\t{Part Reference}\\t{Name}\\t{Designator}\\t{Color}\\t{Source Library}\\t{Source Package}\\t{Source Part}\\t{Implementation}\\t{Implementation Path}\\t{Implementation Type}\\t{Primitive}\\t{Graphic}\\t{ID}\\t{OriginalSymbolOrigin}\\t{Power Pins Visible}\\t{Location X-Coordinate}\\t{Location Y-Coordinate}\\t{SPLIT_INST}\\t{SWAP_INFO}";

function notifyAssetsUpdated() {
  window.dispatchEvent(new Event(ASSETS_UPDATED_EVENT));
}

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
  const { message } = App.useApp();
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const presetSource = params.get("source") || "";
  const presetName = params.get("name") || "";
  const [presetConsumed, setPresetConsumed] = useState(false);
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace(
    "bom_process",
    {
      stage: presetSource ? "review" : "source",
      sp: presetSource,
      name: presetName,
      pcode: "203010100819",
      pdesc: "",
      fmts: ["plm", "oa"],
      extras: [] as Extra[],
      pres: null as any,
      rres: null as any,
      conflictChoices: {} as Record<string, ConflictChoice | number>,
      placementResolutions: {} as Record<string, PlacementResolution>,
    },
    { heavyKeys: ["pres", "rres"] },
  );
  const activePresetSource = presetConsumed ? "" : presetSource;
  const activePresetName = presetConsumed ? "" : presetName;
  // Cadence commonly overwrites the same inbox path. Every explicit source= launch is
  // therefore a new processing session even when the path matches the saved workspace.
  const hasPresetInvocation = Boolean(activePresetSource);

  const [stage, setStage] = useState<Stage>(activePresetSource ? "review" : (String(workspace.stage || "source") as Stage));
  const [sp, setSp] = useState(String(activePresetSource || workspace.sp || ""));
  const [name, setName] = useState(String(activePresetName || workspace.name || ""));
  const [pcode, setPcode] = useState(String(workspace.pcode || "203010100819"));
  const [pdesc, setPdesc] = useState(String(workspace.pdesc || ""));
  const [fmts, setFmts] = useState<string[]>(Array.isArray(workspace.fmts) ? (workspace.fmts as string[]) : ["plm", "oa"]);
  const [extras, setExtras] = useState<Extra[]>(hasPresetInvocation || !Array.isArray(workspace.extras) ? [] : (workspace.extras as Extra[]));
  const [pres, setPres] = useState<any>(hasPresetInvocation ? null : workspace.pres || null);
  const [rres, setRres] = useState<any>(hasPresetInvocation ? null : workspace.rres || null);
  const [rrun, setRrun] = useState(false);
  const [running, setRunning] = useState(false);
  const [conflictChoices, setConflictChoices] = useState<Record<string, ConflictChoice | number>>(
    hasPresetInvocation ? {} : (workspace.conflictChoices as Record<string, ConflictChoice | number>) || {},
  );
  const [placementResolutions, setPlacementResolutions] = useState<Record<string, PlacementResolution>>(
    hasPresetInvocation ? {} : (workspace.placementResolutions as Record<string, PlacementResolution>) || {},
  );

  useEffect(() => {
    setWorkspace({
      stage,
      sp,
      name,
      pcode,
      pdesc,
      fmts,
      extras,
      pres,
      rres,
      conflictChoices,
      placementResolutions,
    });
  }, [stage, sp, name, pcode, pdesc, fmts, extras, pres, rres, conflictChoices, placementResolutions]);

  useEffect(() => {
    if (pres?.reason !== "placement_review") return;
    setPlacementResolutions((current) => seedPlacementResolutions(pres.groups || [], current));
  }, [pres]);

  const steps = ["来源", "识别", "处理", "审查", "交付"];
  const si = { source: 0, review: 1, process: 2, risk: 3, deliver: 4 }[stage];

  async function onFile(f: File) {
    if (running) return Upload.LIST_IGNORE;
    try {
      const u = await uploadFiles([f]);
      setSp(u.files[0]?.path || "");
      setName((p) => p || bname(f.name));
      setPres(null);
      setRres(null);
      setConflictChoices({});
      setPlacementResolutions({});
      message.success("已接收文件");
      setStage("review");
    } catch (e: any) {
      message.error(toUserMessage(e));
    }
    return false;
  }

  useEffect(() => {
    if (stage !== "process" || pres) return;
    setRres(null);
    setRrun(false);
    setRunning(true);
    runTool("bom_process", {
      source_bom: sp,
      formats: fmts,
      name,
      parent_code: pcode,
      parent_desc: pdesc,
      extras: extras.filter((e) => e.code),
      placement_resolutions: placementResolutions,
    })
      .then((r) => {
        setPres(r);
        if (r.status === "ok") notifyAssetsUpdated();
        if (r.status === "ok" && !hasBomConflicts(r)) setStage("risk");
      })
      .catch((e) => setPres({ status: "error", error: toUserMessage(e) }))
      .finally(() => setRunning(false));
  }, [stage]);

  const riskSource = String(pres?.process_file || pres?.outputs?.[0] || "");

  useEffect(() => {
    if (stage !== "risk" || rrun) return;
    if (!riskSource) {
      setRres({
        status: "error",
        error: "尚未生成成品 BOM，请先完成编码冲突确认和 BOM 处理。",
        source_file: "",
      });
      return;
    }
    if (rres?.source_file === riskSource) return;
    setRres(null);
    setRrun(true);
    runTool("bom_risk_check", {
      bom: riskSource,
      decision_manifest: pres?.decision_manifest || "",
      review_summary: pres?.summary?.placement_review,
    })
      .then((result) => setRres({ ...result, source_file: result?.source_file || riskSource }))
      .catch((e) => setRres({ status: "error", error: toUserMessage(e), source_file: riskSource }))
      .finally(() => setRrun(false));
  }, [stage, riskSource, rres?.source_file, rrun]);

  async function applyMerge(merge: boolean) {
    const conflicts = Array.isArray(pres?.conflicts) ? pres.conflicts : [];
    if (merge && !conflicts.every((conflict: any) => conflictChoiceComplete(conflict, conflictChoices[conflict.code]))) {
      message.warning("仍有编码冲突未完成决议，请逐项确认后继续。");
      return;
    }
    setRres(null);
    setRrun(false);
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
        placement_resolutions: placementResolutions,
      });
      setPres(r);
      if (r.status === "ok") notifyAssetsUpdated();
      if (r.status === "ok" && !hasBomConflicts(r)) {
        setStage("risk");
      }
    } catch (e: any) {
      setPres({ status: "error", error: toUserMessage(e) });
    } finally {
      setRunning(false);
    }
  }

  async function applyRecommendedMerge() {
    const conflicts = Array.isArray(pres?.conflicts) ? pres.conflicts : [];
    const choices = buildRecommendedConflictChoices(conflicts, conflictChoices);
    const unresolved = conflicts.filter((conflict: any) => !conflictChoiceComplete(conflict, choices[conflict.code]));
    setConflictChoices(choices);
    if (unresolved.length) {
      const adopted = conflicts.length - unresolved.length;
      message.info(`已采纳 ${adopted} 项高置信决议，剩余 ${unresolved.length} 项需要人工处理。`);
      return;
    }
    setRres(null);
    setRrun(false);
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
        conflict_choices: choices,
        placement_resolutions: placementResolutions,
      });
      setPres(r);
      if (r.status === "ok") notifyAssetsUpdated();
      if (r.status === "ok" && !hasBomConflicts(r)) {
        setStage("risk");
      }
    } catch (e: any) {
      setPres({ status: "error", error: toUserMessage(e) });
    } finally {
      setRunning(false);
    }
  }

  async function applyPlacementReview() {
    setRres(null);
    setRrun(false);
    setRunning(true);
    try {
      const r = await runTool("bom_process", {
        source_bom: sp,
        formats: fmts,
        name,
        parent_code: pcode,
        parent_desc: pdesc,
        extras: extras.filter((e) => e.code),
        placement_resolutions: placementResolutions,
      });
      setPres(r);
      if (r.status === "ok") notifyAssetsUpdated();
      if (r.status === "ok" && !hasBomConflicts(r)) setStage("risk");
    } catch (e: any) {
      setPres({ status: "error", error: toUserMessage(e) });
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
      const r = await secureFetch("/api/package", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name || "BOM", files: all }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new ApiError(
          payload?.error_kind || "PackageError",
          payload?.user_message || payload?.error || `打包失败（HTTP ${r.status}）`,
          r.status,
          payload,
        );
      }
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u;
      a.download = packageDownloadName(r.headers.get("Content-Disposition"), name || "BOM");
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(u);
        a.remove();
      }, 4000);
    } catch (e: any) {
      message.error(toUserMessage(e));
    }
  }

  function clearBomWorkflow(options: { notifyHistory?: boolean; successMessage?: string } = {}) {
    if (options.notifyHistory) notifyAssetsUpdated();
    resetWorkspace();
    setPresetConsumed(true);
    setStage("source");
    setSp("");
    setName("");
    setPcode("203010100819");
    setPdesc("");
    setFmts(["plm", "oa"]);
    setExtras([]);
    setPres(null);
    setRres(null);
    setRrun(false);
    setRunning(false);
    setConflictChoices({});
    setPlacementResolutions({});
    const cleanUrl = `${window.location.pathname}?tool=bom_process`;
    window.history.replaceState({}, "", cleanUrl);
    if (options.successMessage) message.success(options.successMessage);
  }

  function clearAndReturnToSource() {
    clearBomWorkflow({ successMessage: "已清空当前 BOM" });
  }

  function finishAndStartNewBom() {
    clearBomWorkflow({
      notifyHistory: true,
      successMessage: "已同步历史 BOM，可以处理新的 BOM",
    });
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Steps size="small" current={si} items={steps.map((t) => ({ title: t }))} />
      {stage === "source" && <SourceView presetSource={activePresetSource} onFile={onFile} onUsePreset={() => setStage("review")} />}
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
          onClear={clearAndReturnToSource}
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
          placementResolutions={placementResolutions}
          setPlacementResolutions={setPlacementResolutions}
          onApplyPlacementReview={applyPlacementReview}
          onNext={() => setStage("risk")}
          onBack={() => {
            setPres(null);
            setRres(null);
            setRrun(false);
            setStage("review");
          }}
        />
      )}
      {stage === "risk" && <RiskView rrun={rrun} rres={rres} pres={pres} onNext={() => setStage("deliver")} onBack={() => setStage("process")} />}
      {stage === "deliver" && (
        <DeliverView
          pres={pres}
          rres={rres}
          name={name}
          onDownload={dl}
          onFinish={finishAndStartNewBom}
          onReset={() => {
            setPres(null);
            setRres(null);
            setConflictChoices({});
            setPlacementResolutions({});
            resetWorkspace();
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
      <CaptureExportConfig />
    </>
  );
}

function CaptureExportConfig() {
  const { message } = App.useApp();
  const [copied, setCopied] = useState(false);

  async function copyConfig() {
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) {
        copied = await Promise.race<boolean>([
          navigator.clipboard.writeText(CONFIG).then(() => true),
          new Promise((resolve) => window.setTimeout(() => resolve(false), 500)),
        ]);
      }
    } catch {
      copied = false;
    }
    if (!copied) {
      const fallback = document.createElement("textarea");
      fallback.value = CONFIG;
      fallback.setAttribute("readonly", "");
      fallback.style.position = "fixed";
      fallback.style.opacity = "0";
      document.body.appendChild(fallback);
      fallback.select();
      copied = typeof document.execCommand === "function" && document.execCommand("copy");
      fallback.remove();
    }
    if (copied) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } else {
      message.error("复制失败，请选中文本后手动复制。");
    }
  }

  return (
    <div className="capture-export-config">
      <div className="capture-export-config-head">
        <div>
          <Typography.Text strong>Capture 手动导出字段</Typography.Text>
          <Typography.Text type="secondary">粘贴到 Header 和 Combined property string</Typography.Text>
        </div>
        <Button icon={<CopyOutlined />} onClick={() => void copyConfig()}>
          {copied ? "已复制" : "复制字段"}
        </Button>
      </div>
      <Input.TextArea readOnly value={CONFIG} autoSize={{ minRows: 3, maxRows: 5 }} />
    </div>
  );
}

function ReviewView(props: any) {
  const { sp, name, setName, pcode, setPcode, pdesc, setPdesc, fmts, setFmts, extras, setExtras, onClear, onNext } = props;
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
      <Collapse ghost items={[{ key: "extras", label: "附加物料（PCB / 屏蔽支架）", children: <XSection extras={extras} onChange={setExtras} /> }]} />
      <Collapse
        ghost
        items={[
          {
            key: "cfg",
            label: "Capture 导出配置",
            children: <CaptureExportConfig />,
          },
        ]}
      />
      <div className="bom-review-actions">
        <Button danger size="large" onClick={onClear} icon={<RollbackOutlined />}>
          返回并清空
        </Button>
        <Button type="primary" size="large" onClick={onNext} icon={<RightOutlined />}>
          确认无误，开始处理
        </Button>
      </div>
    </Space>
  );
}

function ProcessView({
  running,
  pres,
  conflictChoices,
  setConflictChoices,
  onRecommendedMerge,
  onApply,
  placementResolutions,
  setPlacementResolutions,
  onApplyPlacementReview,
  onNext,
  onBack,
}: any) {
  const [activeConflictCode, setActiveConflictCode] = useState<string>("");
  if (running) return <Result icon={<FileTextOutlined spin />} title="正在处理 BOM…" subTitle="解析字段、过滤 NC 器件、合并位号、生成 PLM/OA" />;
  if (!pres) return null;
  if (pres.status === "error") return <Result status="error" title="处理失败" subTitle={pres.error} extra={<Button onClick={onBack}>返回修改</Button>} />;
  if (pres.reason === "placement_review") {
    return (
      <PlacementReview
        groups={pres.groups || []}
        readonlyNc={pres.readonly_nc || { count: 0, items: [] }}
        readonlyGroups={pres.readonly_groups || []}
        qualityReport={pres.quality_report}
        resolutions={placementResolutions}
        onResolutionsChange={setPlacementResolutions}
        onApply={onApplyPlacementReview}
        onBack={onBack}
        running={running}
      />
    );
  }

  const s = pres.summary || {};
  const conflicts = pres.conflicts || [];
  const hasC = hasBomConflicts(pres);
  const allDone = !hasC || conflicts.every((c: any) => conflictChoiceComplete(c, conflictChoices[c.code]));
  const activeConflict = conflicts.find((c: any) => c.code === activeConflictCode) || conflicts[0];
  const selectedCount = conflicts.filter((c: any) => conflictChoiceComplete(c, conflictChoices[c.code])).length;
  const lowConfidenceCount = conflicts.filter((c: any) => !c.high_confidence).length;
  const highConfidenceCount = conflicts.length - lowConfidenceCount;

  return (
    <div className="process-grid">
      <div className="process-sidebar">
        <Card size="small" title="处理概览">
          <Descriptions size="small" column={1}>
            {hasC ? (
              <>
                <Descriptions.Item label="编码冲突">{conflicts.length}</Descriptions.Item>
                <Descriptions.Item label="低置信推荐">{lowConfidenceCount}</Descriptions.Item>
                <Descriptions.Item label="已选择">{selectedCount}/{conflicts.length}</Descriptions.Item>
              </>
            ) : (
              <>
                <Descriptions.Item label="料号">{s.records ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="位号">{s.total_positions ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="已过滤">{s.excluded ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="编码冲突">{s.conflicts ?? conflicts.length ?? 0}</Descriptions.Item>
              </>
            )}
          </Descriptions>
        </Card>
        <Card size="small" title="下一步">
          {hasC ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text type="secondary">
                仅有 {highConfidenceCount} 项满足安全合并条件，可批量采纳；其余 {lowConfidenceCount} 项必须逐项处理。
              </Typography.Text>
              <Button block disabled={!highConfidenceCount} onClick={onRecommendedMerge}>
                采纳高置信推荐
              </Button>
              <Button type="primary" block disabled={!allDone} onClick={onApply}>
                按全部决议继续处理
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
        {hasC ? (
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
                    const choice = normalizeConflictChoice(c, conflictChoices[c.code]);
                    const variants = c.variants || [];
                    return (
                      <button
                        key={c.code}
                        type="button"
                        className={`conflict-index-item ${activeConflict?.code === c.code ? "is-active" : ""}`}
                        onClick={() => setActiveConflictCode(c.code)}
                      >
                        <span className="conflict-index-code">{idx + 1}. {c.code}</span>
                        <span className="conflict-index-meta">{variants.length} 项 · {conflictChoiceLabel(c, choice)}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="conflict-detail-pane">
                  <CConflict
                    c={activeConflict}
                    choice={normalizeConflictChoice(activeConflict || {}, conflictChoices[activeConflict?.code])}
                    onChange={(choice: ConflictChoice) => setConflictChoices((current: Record<string, ConflictChoice | number>) => ({
                      ...current,
                      [activeConflict.code]: choice,
                    }))}
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

function RiskView({ rrun, rres, pres, onNext, onBack }: any) {
  if (rrun) return <Result icon={<SafetyCertificateOutlined spin />} title="正在风险审查…" subTitle="检查 PCB、屏蔽支架、NC、等级、位号类型、硬件版本敏感物料" />;
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
    { title: "状态", dataIndex: "status", width: 90, render: (v: string) => <Tag color={v === "warn" ? "orange" : v === "ok" ? "green" : "blue"}>{riskStatusText(v)}</Tag> },
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
      key: "risk-final-preview",
      label: "最终 BOM 预览",
      children: <BomPreviewTable preview={pres?.preview} />,
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

function DeliverView({ pres, rres, name, onDownload, onFinish, onReset }: any) {
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
            <List.Item actions={[<Button key="dl" type="link" icon={<DownloadOutlined />} href={outputHref(p)}>下载</Button>]}>
              <FileTextOutlined style={{ marginRight: 8, color: "#1677ff" }} />
              {fname(p)}
            </List.Item>
          )}
        />
      </Card>
      <div className="deliver-actions">
        <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={onDownload}>
          下载全部资源（ZIP）
        </Button>
        <Button size="large" type="primary" ghost icon={<RightOutlined />} onClick={onFinish}>
          完成并处理新的 BOM
        </Button>
      </div>
      <div style={{ textAlign: "center" }}><Button type="link" icon={<ReloadOutlined />} onClick={onReset}>返回修改并重新处理</Button></div>
    </Space>
  );
}

function conflictChoiceLabel(c: any, choice?: ConflictChoice) {
  if (!choice) return "未决议";
  if (choice.action === "select_variant") return `采用候选 ${choice.variant_index + 1}`;
  if (choice.action === "split_refs") {
    return conflictChoiceComplete(c, choice) ? "已拆组改码" : "拆组待填写";
  }
  if (choice.action === "move_non_smt") {
    return conflictChoiceComplete(c, choice) ? `移出 ${choice.variant_indices.length} 项` : "移出项待选择";
  }
  return "返回 Capture 修正";
}

function CConflict({ c, choice, onChange }: { c: any; choice?: ConflictChoice; onChange: (choice: ConflictChoice) => void }) {
  const variants = c?.variants || [];
  const selected = choice?.action === "select_variant" ? choice.variant_index : undefined;
  const splitAssignments = choice?.action === "split_refs" ? choice.assignments : [];
  const moved = choice?.action === "move_non_smt" ? choice.variant_indices : [];

  function beginSplit() {
    const existing = new Map(splitAssignments.map((item) => [item.variant_index, item.part_number]));
    onChange({
      action: "split_refs",
      assignments: variants.map((_: any, index: number) => ({
        variant_index: index,
        part_number: existing.get(index) || "",
      })),
    });
  }

  function updateSplitCode(index: number, partNumber: string) {
    const existing = new Map(splitAssignments.map((item) => [item.variant_index, item.part_number]));
    existing.set(index, partNumber);
    onChange({
      action: "split_refs",
      assignments: variants.map((_: any, variantIndex: number) => ({
        variant_index: variantIndex,
        part_number: existing.get(variantIndex) || "",
      })),
    });
  }

  function toggleMoved(index: number, checked: boolean) {
    const next = checked ? [...moved, index] : moved.filter((value) => value !== index);
    onChange({
      action: "move_non_smt",
      variant_indices: Array.from(new Set(next)).sort((left, right) => left - right),
      exclusion_kind: choice?.action === "move_non_smt" ? choice.exclusion_kind : "scope_excluded",
    });
  }

  return (
    <div>
      <div className="conflict-detail-head">
        <div>
          <Typography.Text type="secondary">当前编码</Typography.Text>
          <Typography.Title level={4} style={{ margin: 0 }}>{c?.code}</Typography.Title>
        </div>
        <Tag color={conflictChoiceComplete(c, choice) ? "blue" : "orange"}>{conflictChoiceLabel(c, choice)}</Tag>
      </div>
      <Alert
        type={c?.high_confidence ? "info" : "warning"}
        showIcon
        message={c?.high_confidence ? "该冲突满足安全合并规则，可采用推荐候选。" : "该冲突涉及关键属性差异，必须由用户明确处理。"}
        description={c?.reason ? `判定原因：${c.reason}` : undefined}
      />
      <div className="conflict-action-toolbar">
        <Button onClick={beginSplit} type={choice?.action === "split_refs" ? "primary" : "default"}>按位号拆组并改码</Button>
        <Button
          onClick={() => onChange({ action: "move_non_smt", variant_indices: [], exclusion_kind: "scope_excluded" })}
          type={choice?.action === "move_non_smt" ? "primary" : "default"}
        >
          移到非贴片区
        </Button>
        <Button danger onClick={() => onChange({ action: "return_to_capture" })}>返回 Capture 修正</Button>
      </div>
      {choice?.action === "split_refs" ? (
        <div className="conflict-action-panel">
          <Typography.Text strong>为每组位号填写唯一的新料号</Typography.Text>
          {variants.map((variant: any, index: number) => (
            <label key={index} className="conflict-split-row">
              <span>候选 {index + 1} · {(variant.refs || []).join("、") || "无位号"}</span>
              <Input
                aria-label={`候选 ${index + 1} 新料号`}
                value={splitAssignments.find((item) => item.variant_index === index)?.part_number || ""}
                onChange={(event) => updateSplitCode(index, event.target.value)}
                placeholder="填写新的内部料号"
              />
            </label>
          ))}
        </div>
      ) : null}
      {choice?.action === "move_non_smt" ? (
        <div className="conflict-action-panel">
          <div className="conflict-exclusion-row">
            <Typography.Text strong>选择需要移出的变体</Typography.Text>
            <Select
              aria-label="移出原因"
              value={choice.exclusion_kind}
              options={[
                { value: "scope_excluded", label: "不属于当前 PCBA / SMT 范围" },
                { value: "user_excluded", label: "用户确认排除" },
              ]}
              onChange={(exclusion_kind) => onChange({ ...choice, exclusion_kind })}
            />
          </div>
          <Typography.Text type="secondary">至少保留一个完整候选，或明确将全部变体移出贴片区。</Typography.Text>
        </div>
      ) : null}
      {choice?.action === "return_to_capture" ? (
        <Alert type="warning" showIcon message="该项不会在平台内合并" description="请返回 Capture 修正属性并重新导出，当前流程不能继续交付。" />
      ) : null}
      <div className="variant-list">
        {variants.map((v: any, i: number) => (
          <div key={i} className={`variant-card ${selected === i ? "is-selected" : ""}`}>
            <div className="variant-card-title">
              <Space>
                <Tag color={selected === i ? "blue" : "default"}>候选 {i + 1}</Tag>
                {c?.recommended_index === i ? (
                  <Tag color={c?.high_confidence ? "green" : "gold"}>
                    {c?.high_confidence ? "高置信推荐" : "低置信推荐"}
                  </Tag>
                ) : null}
                <Typography.Text strong>{v.name || "-"}</Typography.Text>
                <Tag>{v.grade || "未分级"}</Tag>
                <Tag color="purple">数量 {v.count ?? "-"}</Tag>
              </Space>
              <Space>
                {choice?.action === "move_non_smt" ? (
                  <Checkbox checked={moved.includes(i)} onChange={(event) => toggleMoved(i, event.target.checked)}>移出贴片区</Checkbox>
                ) : null}
                <Button size="small" type={selected === i ? "primary" : "default"} onClick={() => onChange({ action: "select_variant", variant_index: i })}>
                  {selected === i ? "已采用完整候选" : "采用此完整候选"}
                </Button>
              </Space>
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
