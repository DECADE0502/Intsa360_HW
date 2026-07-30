import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Result, Space, Steps, Tag, Typography } from "antd";
import {
  CheckCircleOutlined,
  DownloadOutlined,
  EditOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import { uploadFiles } from "../../api/client";
import { toUserMessage } from "../../api/errors";
import { useToolWorkspace } from "../../state/toolWorkspace";
import {
  confirmSmtSources,
  createSmtRegistration,
  decideSmtPlacement,
  decideSmtPlacements,
  exportSmtAnalysis,
  fetchSmtAnalysis,
  finalizeSmtAnalysis,
  startSmtAnalysis,
  uploadDirectoryTree,
  type PlacementDecisionInput,
  type RegistrationInput,
  type SmtAnalysisExportResponse,
  type SourceConfirmationInput,
} from "./api";
import { IdentificationStep } from "./IdentificationStep";
import { RegistrationStep } from "./RegistrationStep";
import { ReviewWorkbench } from "./ReviewWorkbench";
import { SourceStep } from "./SourceStep";
import {
  EMPTY_SMT_WORKSPACE,
  invalidateSmtWorkspace,
  migrateSmtWorkspace,
  workspaceWithRun,
  type SmtAnalysisWorkspace,
} from "./state";
import type { SmtAnalysisRunResponse } from "./types";
import { outputHref } from "../../utils/outputHref";
import styles from "./SmtAnalysisPane.module.css";


const STAGES = ["source", "identify", "register", "review", "deliver"] as const;

function oldWorkspaceInputs() {
  if (typeof window === "undefined") return EMPTY_SMT_WORKSPACE;
  try {
    const raw = window.localStorage.getItem(
      "insta360_hw_tool_workspace:smt_layout",
    );
    if (!raw) return EMPTY_SMT_WORKSPACE;
    const parsed = JSON.parse(raw);
    return migrateSmtWorkspace(parsed?.data || parsed);
  } catch {
    return EMPTY_SMT_WORKSPACE;
  }
}

function fileDirectoryLabel(files: File[]) {
  if (!files.length) return "";
  const relative =
    (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath ||
    files[0].name;
  const parts = relative.replaceAll("\\", "/").split("/").filter(Boolean);
  return parts.length > 1 ? parts[0] : `${files.length} 个文件`;
}

export function SmtAnalysisPane() {
  const initialWorkspace = useMemo(oldWorkspaceInputs, []);
  const [workspace, setWorkspace, resetWorkspace] =
    useToolWorkspace<SmtAnalysisWorkspace>(
      "smt_analysis",
      initialWorkspace,
    );
  const [run, setRun] = useState<SmtAnalysisRunResponse | null>(null);
  const [smtFiles, setSmtFiles] = useState<File[]>([]);
  const [bomFile, setBomFile] = useState<File | undefined>();
  const [netlistFiles, setNetlistFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [delivery, setDelivery] =
    useState<SmtAnalysisExportResponse | null>(null);

  useEffect(() => {
    if (!workspace.runId || run?.run_id === workspace.runId) return;
    let cancelled = false;
    setBusy(true);
    fetchSmtAnalysis(workspace.runId)
      .then((restored) => {
        if (cancelled) return;
        setBusy(false);
        setRun(restored);
        setWorkspace((current) => workspaceWithRun(current, restored));
      })
      .catch((restoreError) => {
        if (cancelled) return;
        setBusy(false);
        setError(
          `上次 SMT 分析无法恢复：${toUserMessage(restoreError)}`,
        );
        setWorkspace(invalidateSmtWorkspace);
      });
    return () => {
      cancelled = true;
    };
  }, [workspace.runId, run?.run_id, setWorkspace]);

  function acceptRun(next: SmtAnalysisRunResponse) {
    setRun(next);
    setDelivery(null);
    setWorkspace((current) => workspaceWithRun(current, next));
  }

  function changeInputs() {
    setRun(null);
    setError("");
    setWorkspace(invalidateSmtWorkspace);
  }

  async function start() {
    if (!smtFiles.length) {
      setError("请选择完整的 SMT 贴片资料目录。");
      return;
    }
    if (!workspace.historyBom && !bomFile) {
      setError("请选择处理后的 PLM/OA 成品 BOM。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const [sourceUpload, bomUpload, netlistUpload] = await Promise.all([
        uploadDirectoryTree(smtFiles),
        workspace.historyBom || !bomFile
          ? Promise.resolve(null)
          : uploadFiles([bomFile]),
        netlistFiles.length
          ? uploadDirectoryTree(netlistFiles)
          : Promise.resolve(null),
      ]);
      const next = await startSmtAnalysis({
        smt_folder: sourceUpload.folder,
        processed_bom:
          workspace.historyBom || bomUpload?.files[0]?.path || "",
        ...(netlistUpload ? { netlist_folder: netlistUpload.folder } : {}),
        ...(workspace.historyDecisionManifest
          ? { decision_manifest: workspace.historyDecisionManifest }
          : {}),
        ...(workspace.historySemanticManifest
          ? { semantic_manifest: workspace.historySemanticManifest }
          : {}),
      });
      setWorkspace((current) => ({
        ...workspaceWithRun(current, next),
        sourceLabel: fileDirectoryLabel(smtFiles),
        bomLabel: workspace.historyBom ? "历史 BOM" : bomFile?.name || "",
        netlistLabel: fileDirectoryLabel(netlistFiles),
      }));
      setRun(next);
    } catch (startError) {
      setError(toUserMessage(startError));
    } finally {
      setBusy(false);
    }
  }

  async function confirmSources(input: SourceConfirmationInput) {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      acceptRun(await confirmSmtSources(run.run_id, input));
    } catch (confirmError) {
      setError(toUserMessage(confirmError));
    } finally {
      setBusy(false);
    }
  }

  async function register(input: RegistrationInput) {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      acceptRun(await createSmtRegistration(run.run_id, input));
    } catch (registrationError) {
      setError(toUserMessage(registrationError));
    } finally {
      setBusy(false);
    }
  }

  async function decide(
    placementId: string,
    input: PlacementDecisionInput,
  ) {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      acceptRun(
        await decideSmtPlacement(run.run_id, placementId, input),
      );
    } catch (decisionError) {
      setError(toUserMessage(decisionError));
    } finally {
      setBusy(false);
    }
  }

  async function decideBatch(
    placementIds: string[],
    input: PlacementDecisionInput,
  ) {
    if (!run || !placementIds.length) return;
    setBusy(true);
    setError("");
    try {
      acceptRun(
        await decideSmtPlacements(run.run_id, placementIds, input),
      );
    } catch (decisionError) {
      setError(toUserMessage(decisionError));
    } finally {
      setBusy(false);
    }
  }

  async function finalize() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      acceptRun(await finalizeSmtAnalysis(run.run_id));
    } catch (finalizeError) {
      setError(toUserMessage(finalizeError));
    } finally {
      setBusy(false);
    }
  }

  async function generateDelivery() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      setDelivery(await exportSmtAnalysis(run.run_id));
    } catch (exportError) {
      setError(toUserMessage(exportError));
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setSmtFiles([]);
    setBomFile(undefined);
    setNetlistFiles([]);
    setRun(null);
    setDelivery(null);
    setError("");
    resetWorkspace();
  }

  const activeStage = STAGES.indexOf(workspace.stage);
  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={4} className={styles.headerTitle}>
            SMT 装配审查
          </Typography.Title>
          <Typography.Text type="secondary">
            在真实位号图上对照坐标、装机 BOM 与网表，优先复核 NC 和数据异常。
          </Typography.Text>
        </div>
        {run ? (
          <Tag
            color={run.summary.blocking_count ? "red" : "green"}
            icon={
              run.summary.blocking_count ? undefined : (
                <CheckCircleOutlined />
              )
            }
          >
            {run.summary.blocking_count
              ? `${run.summary.blocking_count} 个问题`
              : "当前快照已保存"}
          </Tag>
        ) : null}
      </div>
      <Steps
        className={styles.steps}
        size="small"
        current={Math.max(0, activeStage)}
        items={[
          { title: "资料" },
          { title: "识别" },
          { title: "配准" },
          { title: "复核" },
          { title: "交付" },
        ]}
      />

      {workspace.stage !== "source" ? (
        <div className={styles.compactSource}>
          <Space wrap>
            <Typography.Text strong>{workspace.sourceLabel || "SMT 资料"}</Typography.Text>
            <Typography.Text type="secondary">
              {workspace.bomLabel || "成品 BOM"}
            </Typography.Text>
            {workspace.netlistLabel ? (
              <Typography.Text type="secondary">
                {workspace.netlistLabel}
              </Typography.Text>
            ) : null}
          </Space>
          <Button
            icon={<EditOutlined />}
            disabled={busy}
            onClick={changeInputs}
          >
            修改资料
          </Button>
        </div>
      ) : null}

      {workspace.stage === "source" ? (
        <SourceStep
          smtFiles={smtFiles}
          bomFile={bomFile}
          netlistFiles={netlistFiles}
          historyBom={workspace.historyBom}
          historyDecisionManifest={workspace.historyDecisionManifest}
          historySemanticManifest={workspace.historySemanticManifest}
          busy={busy}
          error={error}
          onSmtFiles={(value) => {
            setSmtFiles(value);
            setError("");
          }}
          onBomFile={(file) => {
            setBomFile(file);
            setError("");
          }}
          onNetlistFiles={(value) => {
            setNetlistFiles(value);
            setError("");
          }}
          onHistoryBom={(path, decisionManifest, semanticManifest) =>
            setWorkspace((current) => ({
              ...current,
              historyBom: path,
              historyDecisionManifest: decisionManifest || "",
              historySemanticManifest: semanticManifest || "",
            }))
          }
          onStart={start}
          onClear={clear}
        />
      ) : null}

      {workspace.stage === "identify" && run ? (
        <IdentificationStep
          run={run}
          busy={busy}
          error={error}
          onConfirm={confirmSources}
        />
      ) : null}

      {workspace.stage === "register" && run ? (
        <RegistrationStep
          run={run}
          busy={busy}
          error={error}
          onRegister={register}
        />
      ) : null}

      {workspace.stage === "review" && run ? (
        <>
          {error ? (
            <Alert
              type="error"
              showIcon
              message={error}
              style={{ marginBottom: 10 }}
            />
          ) : null}
          <ReviewWorkbench
            run={run}
            busy={busy}
            onDecide={decide}
            onBatchDecide={decideBatch}
            onComplete={finalize}
          />
        </>
      ) : null}

      {workspace.stage === "deliver" && run ? (
        <div>
          {error ? (
            <Alert
              type="error"
              showIcon
              message={error}
              style={{ marginBottom: 10 }}
            />
          ) : null}
          <Result
            status="success"
            title="装配审查已完成"
            subTitle={`已核对 ${run.summary.placement_count} 个物理位号，其中确认 NC ${run.summary.confirmed_nc_count} 个。交付文件只使用当前确认快照生成。`}
            extra={[
              delivery ? (
                <Button
                  key="download"
                  aria-label="下载交付包"
                  type="primary"
                  icon={<DownloadOutlined />}
                  href={outputHref(delivery.package_path)}
                >
                  下载交付包
                </Button>
              ) : (
                <Button
                  key="generate"
                  aria-label="生成交付包"
                  type="primary"
                  icon={<DownloadOutlined />}
                  loading={busy}
                  onClick={generateDelivery}
                >
                  生成交付包
                </Button>
              ),
              <Button
                key="review"
                icon={<ReloadOutlined />}
                disabled={busy}
                onClick={() =>
                  setWorkspace((current) => ({
                    ...current,
                    stage: "review",
                  }))
                }
              >
                返回复核
              </Button>,
              <Button key="new" disabled={busy} onClick={changeInputs}>
                审查新资料
              </Button>,
            ]}
          />
          {delivery ? (
            <div className={styles.deliveryArtifacts}>
              <Typography.Text strong>交付包内容</Typography.Text>
              <Space wrap>
                {delivery.artifacts.map((artifact) => (
                  <Button
                    key={artifact.path}
                    icon={<DownloadOutlined />}
                    href={outputHref(artifact.path)}
                  >
                    {artifact.label}
                  </Button>
                ))}
              </Space>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
