import { useEffect, useRef, useState } from "react";
import { Alert, App, Badge, Button, Modal, Progress, Space, Steps, Typography } from "antd";
import {
  CheckCircleOutlined,
  DisconnectOutlined,
  SettingOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { UpdateCheck, UpdateStatusInfo } from "../api/client";
import {
  checkUninstall,
  checkUpdate,
  cancelUpdate,
  fetchUpdateStatus,
  installCadenceIntegration,
  runUninstall,
  startUpdate,
  type UpdateNotice,
} from "../api/client";

const { Text, Paragraph } = Typography;
const UPDATE_ACK_KEY = "insta360_hw:update-acknowledged-job";
const UPDATE_CHECK_MESSAGE_KEY = "insta360_hw:update-check-message";
const UPDATE_PHASES = [
  ["downloading", "下载"],
  ["verifying", "校验"],
  ["staging", "暂存"],
  ["awaiting_elevation", "授权"],
  ["committing", "提交"],
  ["switching", "切换"],
  ["integrating", "集成"],
  ["verifying_runtime", "验证"],
] as const;

function phaseIndex(phase?: string) {
  const index = UPDATE_PHASES.findIndex(([value]) => value === phase);
  if (phase === "completed") return UPDATE_PHASES.length;
  return Math.max(index, 0);
}

function formatBytes(value?: number) {
  if (!value || value <= 0) return "0 MB";
  return `${(value / 1024 / 1024).toFixed(value >= 100 * 1024 * 1024 ? 0 : 1)} MB`;
}

export function UpdateStatus({ version }: { version: string }) {
  const { message } = App.useApp();
  const [detaching, setDetaching] = useState(false);
  const [installingCadence, setInstallingCadence] = useState(false);
  const [checking, setChecking] = useState(false);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [canUpdate, setCanUpdate] = useState(false);
  const [updateReason, setUpdateReason] = useState("");
  const [checkMessage, setCheckMessage] = useState("");
  const [remoteStatus, setRemoteStatus] = useState("unknown");
  const [remoteVersion, setRemoteVersion] = useState<string>("");
  const [checkedUpdate, setCheckedUpdate] = useState(false);
  const [updateNotice, setUpdateNotice] = useState<UpdateNotice | null>(null);
  const [integrityVerified, setIntegrityVerified] = useState<boolean | undefined>(undefined);
  const [integrityStatus, setIntegrityStatus] = useState<string>("");
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [startingUpdate, setStartingUpdate] = useState(false);

  const [progressOpen, setProgressOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusInfo | null>(null);
  const updatePollRef = useRef<number | null>(null);

  function applyCheckResult(info: UpdateCheck, openNotice: boolean) {
    const notice = info.update_notice && Object.keys(info.update_notice).length ? info.update_notice : null;
    setHasUpdate(Boolean(info.has_update));
    setCanUpdate(Boolean(info.can_update));
    setUpdateReason(info.update_reason || "");
    setCheckMessage(info.remote_status === "ok" ? (info.can_update ? "" : info.message || "") : info.message || info.error || "更新检查失败");
    setRemoteStatus(info.remote_status || "error");
    setRemoteVersion(info.display_remote || info.remote_version || "");
    setUpdateNotice(notice);
    setIntegrityVerified(info.integrity_verified);
    setIntegrityStatus(info.integrity_status || "");
    if (openNotice && info.has_update && notice) setNoticeOpen(true);
    setCheckedUpdate(true);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([checkUpdate(), fetchUpdateStatus()]).then(([checkResult, statusResult]) => {
      if (cancelled) return;
      if (checkResult.status === "fulfilled") applyCheckResult(checkResult.value, true);
      else {
        setCheckedUpdate(true);
        setRemoteStatus("error");
        setCheckMessage(checkResult.reason instanceof Error ? checkResult.reason.message : "更新检查失败");
      }
      if (statusResult.status === "fulfilled") {
        const status = statusResult.value;
        const acknowledged = window.localStorage.getItem(UPDATE_ACK_KEY);
        const unacknowledgedTerminal = Boolean(status.job_id && status.job_id !== acknowledged && status.phase !== "idle");
        if (status.running || unacknowledgedTerminal) {
          setUpdateStatus(status);
          setNoticeOpen(false);
          setProgressOpen(true);
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const [pollErrorStreak, setPollErrorStreak] = useState(0);

  useEffect(() => {
    if (!progressOpen) return;
    const ctrl = new AbortController();
    let stopped = false;
    const tick = async () => {
      let shouldContinue = true;
      try {
        const s = await fetchUpdateStatus({ signal: ctrl.signal });
        if (!ctrl.signal.aborted) {
          setUpdateStatus(s);
          setPollErrorStreak(0);
          shouldContinue = s.running;
        }
      } catch (e: any) {
        if (!ctrl.signal.aborted) {
          setPollErrorStreak((n) => n + 1);
        }
      } finally {
        if (shouldContinue && !stopped && !ctrl.signal.aborted) {
          updatePollRef.current = window.setTimeout(() => void tick(), 1000);
        } else {
          updatePollRef.current = null;
        }
      }
    };
    void tick();
    return () => {
      stopped = true;
      ctrl.abort();
      if (updatePollRef.current) window.clearTimeout(updatePollRef.current);
      updatePollRef.current = null;
      setPollErrorStreak(0);
    };
  }, [progressOpen]);

  const updateFinished = updateStatus?.done || updateStatus?.failed || updateStatus?.phase === "cancelled";

  async function onCheckUpdate() {
    setChecking(true);
    try {
      const info = await checkUpdate();
      applyCheckResult(info, true);
      if (info.remote_status === "not_published") {
        message.info({ key: UPDATE_CHECK_MESSAGE_KEY, content: info.message || "仓库尚未发布可用的更新包。" });
      } else if (info.remote_status !== "ok") {
        message.error({ key: UPDATE_CHECK_MESSAGE_KEY, content: info.message || info.error || "更新检查失败" });
      } else if (info.has_update && info.can_update) {
        if (info.update_notice && Object.keys(info.update_notice).length) setNoticeOpen(true);
        message.info({ key: UPDATE_CHECK_MESSAGE_KEY, content: `发现新版本 ${info.display_remote || info.remote_version}` });
      } else if (info.has_update) {
        message.warning({ key: UPDATE_CHECK_MESSAGE_KEY, content: info.message || "发现新版本，但当前环境需要使用 Setup 安装包升级。" });
      } else {
        message.success({
          key: UPDATE_CHECK_MESSAGE_KEY,
          content: info.display_remote || info.remote_version ? `已是最新版本 ${info.display_remote || info.remote_version}` : "已是最新版本",
        });
      }
    } catch (e) {
      message.error({ key: UPDATE_CHECK_MESSAGE_KEY, content: (e as Error).message || "更新检查失败" });
    } finally {
      setChecking(false);
    }
  }

  async function onUpdate() {
    if (!canUpdate) {
      message.info(checkMessage || (hasUpdate ? "当前版本需要使用 Setup 安装包升级。" : "请先检查更新；只有检测到更高版本后才能安装。"));
      return;
    }
    setStartingUpdate(true);
    setNoticeOpen(false);
    setUpdateStatus(null);
    try {
      const started = await startUpdate();
      window.localStorage.removeItem(UPDATE_ACK_KEY);
      setUpdateStatus({
        status: "ok",
        job_id: started.job_id,
        running: true,
        done: false,
        failed: false,
        cancelled: false,
        phase: "queued",
        progress: 0,
        step: "queued",
        message: started.message || "更新任务已创建。",
        log_tail: [],
        cancellable: true,
        bytes_total: 0,
        bytes_downloaded: 0,
        bytes_per_second: 0,
        rolled_back: false,
        rollback_error: "",
        cleanup_pending: false,
        cleanup_warning: "",
        interrupted: false,
        recovery_required: false,
        error: "",
      });
      setProgressOpen(true);
    } catch (e) {
      message.error((e as Error).message || "更新启动失败");
      setProgressOpen(false);
    } finally {
      setStartingUpdate(false);
    }
  }

  async function onCancelUpdate() {
    try {
      await cancelUpdate(updateStatus?.job_id);
      message.info("正在安全取消提交前的更新，请稍候。");
    } catch (e) {
      message.error((e as Error).message || "取消更新失败");
    }
  }

  function closeProgress() {
    if (updateStatus?.job_id) window.localStorage.setItem(UPDATE_ACK_KEY, updateStatus.job_id);
    setProgressOpen(false);
    if (updateStatus?.done) window.location.reload();
  }

  function openWindowsApps() {
    window.location.href = "ms-settings:appsfeatures";
  }

  async function onDetach() {
    setDetaching(true);
    try {
      const check = await checkUninstall();
      // cadence_only invokes a standalone script that does NOT stop the
      // platform's own python.exe on 8765 — the legacy "detach" mode called
      // uninstall.ps1 which killed the very service that spawned it.
      const supportsCadenceOnly = check.modes?.includes("cadence_only");
      if (!supportsCadenceOnly) {
        message.error("未找到卸载脚本，无法移除集成");
        return;
      }
      await runUninstall("cadence_only");
      message.success("已开始移除 Cadence 集成");
    } catch (e) {
      message.error((e as Error).message || "移除失败");
    } finally {
      setDetaching(false);
    }
  }

  async function onInstallCadence() {
    setInstallingCadence(true);
    try {
      const result = await installCadenceIntegration();
      message.success(result.message || "Cadence 集成已重新安装");
      if (result.hot_reload_command) {
        message.info("Capture 已打开时，请执行热更新指令或重启 Capture。");
      }
    } catch (e) {
      message.error((e as Error).message || "Cadence 集成安装失败");
    } finally {
      setInstallingCadence(false);
    }
  }

  return (
    <div className="maint-card">
      <div className="maint-version">
        <CheckCircleOutlined className="maint-version-dot" />
        <Text className="maint-version-text">
          版本 {version || "-"}
          {hasUpdate && remoteVersion ? <Text className="maint-version-remote">（最新 {remoteVersion}）</Text> : null}
          {!hasUpdate && checkedUpdate && remoteVersion ? <Text className="maint-version-remote">（已检查 {remoteVersion}）</Text> : null}
        </Text>
        {hasUpdate ? <Badge status="processing" /> : null}
      </div>

      <div className="maint-actions">
        <Button className="maint-btn" size="small" icon={<SyncOutlined />} loading={checking} onClick={onCheckUpdate}>
          检查更新
        </Button>
        <Button className="maint-btn" size="small" type={canUpdate ? "primary" : "default"} disabled={!canUpdate} loading={startingUpdate} onClick={onUpdate}>
          {hasUpdate && remoteVersion ? `更新到 ${remoteVersion}` : "立即更新"}
        </Button>
        {hasUpdate && updateNotice ? (
          <Button className="maint-btn" size="small" onClick={() => setNoticeOpen(true)}>
            查看更新公告
          </Button>
        ) : null}
        <Button
          className="maint-btn"
          size="small"
          icon={<DisconnectOutlined />}
          loading={detaching}
          onClick={onDetach}
        >
          移除 Cadence 集成
        </Button>
        <Button className="maint-btn" size="small" loading={installingCadence} onClick={onInstallCadence}>
          修复 Cadence 集成
        </Button>
      </div>

      {checkMessage ? (
        <Alert
          className="maint-check-result"
          type={remoteStatus === "error" ? "error" : "info"}
          showIcon
          message={checkMessage}
        />
      ) : null}

      <div className="maint-uninstall">
        <Text type="secondary">请通过 Windows 设置或 Insta360_HW_Setup.exe 卸载平台。</Text>
        <Button className="maint-btn" size="small" icon={<SettingOutlined />} onClick={openWindowsApps}>
          打开 Windows 应用列表
        </Button>
      </div>

      <UpdateNoticeModal
        open={noticeOpen}
        notice={updateNotice}
        remoteVersion={remoteVersion}
        integrityVerified={integrityVerified}
        integrityStatus={integrityStatus}
        canUpdate={canUpdate}
        updateReason={updateReason}
        updateMessage={checkMessage}
        onClose={() => setNoticeOpen(false)}
        onUpdate={onUpdate}
      />

      <Modal
        open={progressOpen}
        title={updateStatus?.done ? "更新完成" : updateStatus?.failed ? "更新失败" : updateStatus?.phase === "cancelled" ? "更新已取消" : "正在更新平台"}
        footer={null}
        width={620}
        closable={Boolean(updateFinished)}
        maskClosable={false}
        onCancel={() => {
          if (updateFinished) closeProgress();
        }}
      >
        <div style={{ marginBottom: 12 }}>
          <Progress
            percent={updateStatus?.progress ?? 0}
            status={updateStatus?.failed ? "exception" : updateStatus?.done ? "success" : updateStatus?.phase === "cancelled" ? "normal" : "active"}
          />
        </div>
        <Steps
          size="small"
          current={phaseIndex(updateStatus?.phase)}
          status={updateStatus?.failed ? "error" : updateStatus?.done ? "finish" : "process"}
          items={UPDATE_PHASES.map(([, title]) => ({ title }))}
          responsive
          style={{ marginBottom: 18 }}
        />
        <Paragraph style={{ marginBottom: 8, minHeight: 22 }}>
          {updateStatus?.failed ? (
            <Text type="danger">{updateStatus.message}</Text>
          ) : updateStatus?.done ? (
            <Text type="success">{updateStatus.message}</Text>
          ) : updateStatus?.phase === "cancelled" ? (
            <Text>更新已在修改已安装版本前安全取消。</Text>
          ) : pollErrorStreak >= 5 ? (
            <Text type="warning">
              正在切换并重启后端，连接会短暂中断。页面正在自动重连，请不要重复启动更新。
            </Text>
          ) : (
            <Text type="secondary">{updateStatus?.message || "准备中..."}</Text>
          )}
        </Paragraph>
        {updateStatus?.phase === "downloading" ? (
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {formatBytes(updateStatus.bytes_downloaded)} / {formatBytes(updateStatus.bytes_total)}
            {updateStatus.bytes_per_second ? ` · ${formatBytes(updateStatus.bytes_per_second)}/s` : ""}
          </Paragraph>
        ) : null}
        {updateStatus?.failed && updateStatus.rolled_back ? (
          <Alert type="warning" showIcon message="新版本未生效，平台已恢复到更新前版本。" />
        ) : null}
        {updateStatus?.failed && updateStatus.rollback_error ? (
          <Alert type="error" showIcon message="自动回滚失败" description={updateStatus.rollback_error} />
        ) : null}
        {updateStatus?.failed && updateStatus.recovery_required ? (
          <Alert
            type="error"
            showIcon
            message="需要恢复更新事务"
            description="请从桌面重新启动 Insta360_HW。启动器会在打开平台前自动恢复上一版本。"
          />
        ) : null}
        {updateStatus?.done && updateStatus.cleanup_pending ? (
          <Alert
            type="warning"
            showIcon
            message="新版本已生效，旧版本清理将在后续自动重试"
            description={updateStatus.cleanup_warning || undefined}
          />
        ) : null}
        <div style={{ textAlign: "right", marginTop: 12 }}>
          {updateFinished ? (
            <Button
              type="primary"
              onClick={closeProgress}
            >
              {updateStatus?.done ? "完成并刷新" : "关闭"}
            </Button>
          ) : updateStatus?.cancellable ? (
            <Space>
              <Text type="secondary" style={{ fontSize: 12 }}>提交前可安全取消</Text>
              <Button onClick={onCancelUpdate}>取消更新</Button>
            </Space>
          ) : <Text type="secondary" style={{ fontSize: 12 }}>正在提交完整版本，此阶段不可取消</Text>}
        </div>
      </Modal>

    </div>
  );
}

function UpdateNoticeModal({
  open,
  notice,
  remoteVersion,
  integrityVerified,
  integrityStatus,
  canUpdate,
  updateReason,
  updateMessage,
  onClose,
  onUpdate,
}: {
  open: boolean;
  notice: UpdateNotice | null;
  remoteVersion: string;
  integrityVerified?: boolean;
  integrityStatus?: string;
  canUpdate: boolean;
  updateReason: string;
  updateMessage: string;
  onClose: () => void;
  onUpdate: () => void;
}) {
  if (!notice) return null;
  const highlights = notice.highlights || [];
  const trace = notice.trace || {};
  const integrityAlert = integrityStatus === "manifest_invalid"
    ? { type: "error" as const, message: "更新清单无效", description: "平台不会安装缺少完整性校验的运行包。" }
    : null;
  return (
    <Modal
      open={open}
      title={notice.title || "更新公告"}
      width={640}
      okText={remoteVersion ? `更新到 ${remoteVersion}` : "立即更新"}
      cancelText="稍后再说"
      okButtonProps={{ disabled: !canUpdate }}
      onCancel={onClose}
      onOk={onUpdate}
    >
      <div className="update-notice-meta">
        {notice.version ? <Text>版本：{notice.version}</Text> : null}
        {notice.target_revision ? <Text>修订：{notice.target_revision}</Text> : null}
        {notice.date ? <Text>发布日期：{notice.date}</Text> : null}
      </div>
      {notice.summary ? <Paragraph>{notice.summary}</Paragraph> : null}
      {!canUpdate ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={updateReason === "updater_too_old" ? "需要使用 Setup 安装包升级" : "当前环境不能应用内更新"}
          description={updateMessage || "请使用最新 Insta360_HW_Setup.exe 完成升级。"}
        />
      ) : null}
      {integrityStatus === "manifest_sha256_required" ? (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message="完整运行包已启用 SHA256 与文件大小校验"
        />
      ) : null}
      {integrityVerified === false && integrityAlert ? (
        <Alert
          type={integrityAlert.type}
          showIcon
          style={{ marginBottom: 12 }}
          message={integrityAlert.message}
          description={integrityAlert.description}
        />
      ) : null}
      {integrityVerified === false && !integrityAlert && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="此更新包未经 SHA256 校验"
          description="平台已拒绝该更新。请等待维护人员重新发布带 SHA256 和文件大小的完整运行包。"
        />
      )}
      {highlights.length ? (
        <>
          <Text strong>本次更新要点</Text>
          <ul className="update-notice-list">
            {highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
      {notice.compatibility ? <Paragraph type="secondary">{notice.compatibility}</Paragraph> : null}
      {Object.keys(trace).length ? (
        <Paragraph type="secondary" className="update-notice-trace">
          溯源：{String(trace.source || "github_release_manifest")} / {String(trace.channel || "stable")}
        </Paragraph>
      ) : null}
    </Modal>
  );
}
