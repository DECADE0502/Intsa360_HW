import { useEffect, useRef, useState } from "react";
import { Badge, Button, Input, Modal, Progress, Typography, message } from "antd";
import {
  CheckCircleOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { UninstallStatusInfo, UpdateStatusInfo } from "../api/client";
import {
  checkUninstall,
  checkUpdate,
  fetchUninstallStatus,
  fetchUpdateStatus,
  runUninstall,
  startUpdate,
  type UpdateNotice,
} from "../api/client";

const { Text, Paragraph } = Typography;

export function UpdateStatus({ version }: { version: string }) {
  const [detaching, setDetaching] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [fulling, setFulling] = useState(false);
  const [checking, setChecking] = useState(false);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [remoteVersion, setRemoteVersion] = useState<string>("");
  const [checkedUpdate, setCheckedUpdate] = useState(false);
  const [updateNotice, setUpdateNotice] = useState<UpdateNotice | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);

  const [progressOpen, setProgressOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusInfo | null>(null);
  const [uninstallOpen, setUninstallOpen] = useState(false);
  const [uninstallStatus, setUninstallStatus] = useState<UninstallStatusInfo | null>(null);
  const [uninstallClosing, setUninstallClosing] = useState(false);
  const updatePollRef = useRef<number | null>(null);
  const uninstallPollRef = useRef<number | null>(null);
  const uninstallFailuresRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    checkUpdate()
      .then((info) => {
        if (cancelled) return;
        setHasUpdate(Boolean(info.has_update));
        setRemoteVersion(info.display_remote || info.remote_version || "");
        setUpdateNotice(info.update_notice && Object.keys(info.update_notice).length ? info.update_notice : null);
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

  useEffect(() => {
    if (!uninstallOpen) {
      if (uninstallPollRef.current) window.clearInterval(uninstallPollRef.current);
      return;
    }
    const poll = () => {
      fetchUninstallStatus()
        .then((status) => {
          uninstallFailuresRef.current = 0;
          setUninstallStatus(status);
          if (status.done || status.failed) {
            if (uninstallPollRef.current) window.clearInterval(uninstallPollRef.current);
          }
        })
        .catch(() => {
          uninstallFailuresRef.current += 1;
          if (uninstallFailuresRef.current >= 2) {
            setUninstallClosing(true);
            setUninstallStatus((current) => ({
              running: false,
              done: true,
              failed: false,
              progress: 100,
              step: "平台服务已关闭，本地卸载已完成",
              message: "卸载完成",
              log_tail: current?.log_tail ?? [],
            }));
            if (uninstallPollRef.current) window.clearInterval(uninstallPollRef.current);
          }
        });
    };
    poll();
    uninstallPollRef.current = window.setInterval(poll, 800);
    return () => {
      if (uninstallPollRef.current) window.clearInterval(uninstallPollRef.current);
    };
  }, [uninstallOpen]);

  const updateFinished = updateStatus?.done || updateStatus?.failed;
  const uninstallFinished = uninstallStatus?.done || uninstallStatus?.failed || uninstallClosing;

  async function onCheckUpdate() {
    setChecking(true);
    try {
      const info = await checkUpdate();
      setHasUpdate(Boolean(info.has_update));
      setRemoteVersion(info.display_remote || info.remote_version || "");
      setUpdateNotice(info.update_notice && Object.keys(info.update_notice).length ? info.update_notice : null);
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

  async function onFull() {
    setFulling(true);
    setUninstallOpen(true);
    setUninstallStatus(null);
    setUninstallClosing(false);
    uninstallFailuresRef.current = 0;
    try {
      await runUninstall("full");
      setFullOpen(false);
      setConfirmText("");
    } catch (e) {
      message.error((e as Error).message || "卸载启动失败");
      setUninstallOpen(false);
    } finally {
      setFulling(false);
    }
  }

  function onCloseUninstallProgress() {
    setUninstallOpen(false);
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
      </div>

      <div className="maint-danger">
        <Button className="maint-btn-danger" size="small" block danger icon={<DeleteOutlined />} onClick={() => setFullOpen(true)}>
          完整卸载
        </Button>
      </div>

      <UpdateNoticeModal
        open={noticeOpen}
        notice={updateNotice}
        remoteVersion={remoteVersion}
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

      <Modal
        open={uninstallOpen}
        title="正在卸载平台"
        footer={null}
        width={620}
        closable={false}
      >
        <div style={{ marginBottom: 12 }}>
          <Progress
            percent={uninstallStatus?.progress ?? 0}
            status={uninstallStatus?.failed ? "exception" : uninstallStatus?.done ? "success" : "active"}
          />
        </div>
        <Paragraph style={{ marginBottom: 8, minHeight: 22 }}>
          {uninstallStatus?.failed ? (
            <Text type="danger">{uninstallStatus.message}</Text>
          ) : uninstallStatus?.done ? (
            <Text type="success">{uninstallStatus.message}</Text>
          ) : (
            <Text type="secondary">{uninstallStatus?.step || uninstallStatus?.message || "准备卸载..."}</Text>
          )}
        </Paragraph>
        <pre className="update-log">{(uninstallStatus?.log_tail || []).join("\n") || "等待卸载日志输出..."}</pre>
        <div style={{ textAlign: "right", marginTop: 12 }}>
          {uninstallFinished ? (
            <Button type="primary" danger={Boolean(uninstallStatus?.failed)} onClick={onCloseUninstallProgress}>
              {uninstallStatus?.failed ? "关闭" : "卸载完成，关闭"}
            </Button>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              卸载过程中会关闭本地服务，请勿重复操作
            </Text>
          )}
        </div>
      </Modal>

      <Modal
        open={fullOpen}
        title="完整卸载平台"
        okText="确认卸载"
        okButtonProps={{ danger: true, disabled: confirmText !== "DELETE", loading: fulling }}
        cancelText="取消"
        onCancel={() => {
          setFullOpen(false);
          setConfirmText("");
        }}
        onOk={onFull}
      >
        <Paragraph type="danger" strong>
          这会删除整个平台目录及其全部文件，包括 data、config 和 plugins/user。该操作不可恢复。
        </Paragraph>
        <Paragraph>
          如果只需要从 Capture 移除菜单并保留平台，请使用“移除 Cadence 集成”。
        </Paragraph>
        <Text>请输入 </Text>
        <Text code>DELETE</Text>
        <Text> 以确认：</Text>
        <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="DELETE" style={{ marginTop: 8 }} />
      </Modal>
    </div>
  );
}

function UpdateNoticeModal({
  open,
  notice,
  remoteVersion,
  onClose,
  onUpdate,
}: {
  open: boolean;
  notice: UpdateNotice | null;
  remoteVersion: string;
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
