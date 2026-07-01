import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Modal, Progress, Typography, message } from "antd";
import {
  CheckCircleOutlined,
  DisconnectOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { UpdateStatusInfo } from "../api/client";
import {
  checkUninstall,
  checkUpdate,
  fetchUpdateStatus,
  installCadenceIntegration,
  runUninstall,
  startUpdate,
  type UpdateNotice,
} from "../api/client";

const { Text, Paragraph } = Typography;

export function UpdateStatus({ version }: { version: string }) {
  const [detaching, setDetaching] = useState(false);
  const [installingCadence, setInstallingCadence] = useState(false);
  const [checking, setChecking] = useState(false);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [remoteVersion, setRemoteVersion] = useState<string>("");
  const [checkedUpdate, setCheckedUpdate] = useState(false);
  const [updateNotice, setUpdateNotice] = useState<UpdateNotice | null>(null);
  const [integrityVerified, setIntegrityVerified] = useState<boolean | undefined>(undefined);
  const [noticeOpen, setNoticeOpen] = useState(false);

  const [progressOpen, setProgressOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusInfo | null>(null);
  const updatePollRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    checkUpdate()
      .then((info) => {
        if (cancelled) return;
        setHasUpdate(Boolean(info.has_update));
        setRemoteVersion(info.display_remote || info.remote_version || "");
        setUpdateNotice(info.update_notice && Object.keys(info.update_notice).length ? info.update_notice : null);
        setIntegrityVerified(info.integrity_verified);
        if (info.has_update && info.update_notice && Object.keys(info.update_notice).length) setNoticeOpen(true);
        setCheckedUpdate(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!progressOpen) {
      if (updatePollRef.current) window.clearInterval(updatePollRef.current);
      return;
    }
    const poll = () => {
      fetchUpdateStatus().then(setUpdateStatus).catch(() => {});
    };
    poll();
    updatePollRef.current = window.setInterval(poll, 1000);
    return () => {
      if (updatePollRef.current) window.clearInterval(updatePollRef.current);
    };
  }, [progressOpen]);

  const updateFinished = updateStatus?.done || updateStatus?.failed;

  async function onCheckUpdate() {
    setChecking(true);
    try {
      const info = await checkUpdate();
      setHasUpdate(Boolean(info.has_update));
      setRemoteVersion(info.display_remote || info.remote_version || "");
      setUpdateNotice(info.update_notice && Object.keys(info.update_notice).length ? info.update_notice : null);
      setIntegrityVerified(info.integrity_verified);
      setCheckedUpdate(true);
      if (info.has_update) {
        if (info.update_notice && Object.keys(info.update_notice).length) setNoticeOpen(true);
        message.info(`发现新版本 ${info.display_remote || info.remote_version}`);
      } else {
        message.success(info.display_remote || info.remote_version ? `已是最新版本 ${info.display_remote || info.remote_version}` : "已是最新版本");
      }
    } catch (e) {
      message.error((e as Error).message || "更新检查失败");
    } finally {
      setChecking(false);
    }
  }

  async function onUpdate() {
    setProgressOpen(true);
    setUpdateStatus(null);
    try {
      await startUpdate();
    } catch (e) {
      message.error((e as Error).message || "更新启动失败");
      setProgressOpen(false);
    }
  }

  async function onDetach() {
    setDetaching(true);
    try {
      const check = await checkUninstall();
      if (!check.can_uninstall) {
        message.error("未找到卸载脚本，无法移除集成");
        return;
      }
      await runUninstall("detach");
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
        <Button className="maint-btn" size="small" type={hasUpdate ? "primary" : "default"} onClick={onUpdate}>
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

      <div className="maint-danger">
        <Text type="secondary">请通过 Windows 设置或 Insta360_HW_Setup.exe 卸载平台。</Text>
      </div>

      <UpdateNoticeModal
        open={noticeOpen}
        notice={updateNotice}
        remoteVersion={remoteVersion}
        integrityVerified={integrityVerified}
        onClose={() => setNoticeOpen(false)}
        onUpdate={onUpdate}
      />

      <Modal
        open={progressOpen}
        title="正在更新平台"
        footer={null}
        width={620}
        closable={false}
        onCancel={() => setProgressOpen(false)}
      >
        <div style={{ marginBottom: 12 }}>
          <Progress
            percent={updateStatus?.progress ?? 0}
            status={updateStatus?.failed ? "exception" : updateStatus?.done ? "success" : "active"}
          />
        </div>
        <Paragraph style={{ marginBottom: 8, minHeight: 22 }}>
          {updateStatus?.failed ? (
            <Text type="danger">{updateStatus.message}</Text>
          ) : updateStatus?.done ? (
            <Text type="success">{updateStatus.message}</Text>
          ) : (
            <Text type="secondary">{updateStatus?.step || updateStatus?.message || "准备中..."}</Text>
          )}
        </Paragraph>
        <pre className="update-log">{(updateStatus?.log_tail || []).join("\n") || "等待日志输出..."}</pre>
        <div style={{ textAlign: "right", marginTop: 12 }}>
          {updateFinished ? (
            <Button
              type="primary"
              onClick={() => {
                setProgressOpen(false);
                if (updateStatus?.done) {
                  message.success("更新完成，页面将在 3 秒后刷新");
                  setTimeout(() => window.location.reload(), 3000);
                }
              }}
            >
              {updateStatus?.done ? "完成并刷新" : "关闭"}
            </Button>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              更新进行中，请勿关闭窗口
            </Text>
          )}
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
  onClose,
  onUpdate,
}: {
  open: boolean;
  notice: UpdateNotice | null;
  remoteVersion: string;
  integrityVerified?: boolean;
  onClose: () => void;
  onUpdate: () => void;
}) {
  if (!notice) return null;
  const highlights = notice.highlights || [];
  const trace = notice.trace || {};
  return (
    <Modal
      open={open}
      title={notice.title || "更新公告"}
      width={640}
      okText={remoteVersion ? `更新到 ${remoteVersion}` : "立即更新"}
      cancelText="稍后再说"
      onCancel={onClose}
      onOk={onUpdate}
    >
      <div className="update-notice-meta">
        {notice.version ? <Text>版本：{notice.version}</Text> : null}
        {notice.target_revision ? <Text>修订：{notice.target_revision}</Text> : null}
        {notice.date ? <Text>发布日期：{notice.date}</Text> : null}
      </div>
      {notice.summary ? <Paragraph>{notice.summary}</Paragraph> : null}
      {integrityVerified === false && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="此更新包未经 SHA256 校验"
          description="服务端未提供完整性元数据，下载文件可能被篡改。建议手工核对发布来源后再点立即更新。"
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
          溯源：{String(trace.repo || "-")} / {String(trace.branch || "-")}
        </Paragraph>
      ) : null}
    </Modal>
  );
}
