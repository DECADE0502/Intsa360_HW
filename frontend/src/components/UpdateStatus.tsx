import { useEffect, useRef, useState } from "react";
import { Badge, Button, Input, Modal, Progress, Typography, message } from "antd";
import {
  CheckCircleOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { UpdateStatusInfo } from "../api/client";
import {
  checkUninstall,
  checkUpdate,
  fetchUpdateStatus,
  runUninstall,
  startUpdate,
} from "../api/client";

const { Text, Paragraph } = Typography;

/**
 * Sidebar footer "维护" card. Groups the platform-level lifecycle actions
 * (OTA update, detach Cadence integration, full uninstall) into one clearly
 * layered block instead of a pile of buttons.
 *
 * The update flow opens a progress modal that polls /api/update/status and
 * shows a live progress bar + scrolling log, so the user always knows whether
 * an update is running and how far along it is.
 */
export function UpdateStatus({ version }: { version: string }) {
  const [detaching, setDetaching] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [fulling, setFulling] = useState(false);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [remoteVersion, setRemoteVersion] = useState<string>("");

  // Update progress modal state.
  const [progressOpen, setProgressOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusInfo | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    checkUpdate()
      .then((info) => {
        if (cancelled) return;
        setHasUpdate(Boolean(info.has_update));
        setRemoteVersion(info.remote_version || "");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll update status every 1s while the progress modal is open.
  useEffect(() => {
    if (!progressOpen) {
      if (pollRef.current) window.clearInterval(pollRef.current);
      return;
    }
    const poll = () => {
      fetchUpdateStatus()
        .then(setUpdateStatus)
        .catch(() => {});
    };
    poll();
    pollRef.current = window.setInterval(poll, 1000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [progressOpen]);

  const finished = updateStatus?.done || updateStatus?.failed;

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
      message.success("已移除 Cadence 集成，平台文件已保留");
    } catch (e) {
      message.error((e as Error).message || "移除失败");
    } finally {
      setDetaching(false);
    }
  }

  async function onFull() {
    setFulling(true);
    try {
      await runUninstall("full");
      message.success("完整卸载已启动，本窗口将在稍后关闭");
      setTimeout(() => window.close(), 2500);
    } catch (e) {
      message.error((e as Error).message || "卸载启动失败");
    } finally {
      setFulling(false);
      setFullOpen(false);
    }
  }

  return (
    <div className="maint-card">
      <div className="maint-version">
        <CheckCircleOutlined className="maint-version-dot" />
        <Text className="maint-version-text">
          版本 {version || "-"}
          {hasUpdate && remoteVersion ? (
            <Text className="maint-version-remote">（最新 {remoteVersion}）</Text>
          ) : null}
        </Text>
        {hasUpdate ? <Badge status="processing" /> : null}
      </div>

      <div className="maint-actions">
        <Button
          className="maint-btn"
          size="small"
          icon={<SyncOutlined />}
          onClick={onUpdate}
        >
          {hasUpdate ? `一键更新到 ${remoteVersion}` : "一键更新"}
        </Button>
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
        <Button
          className="maint-btn-danger"
          size="small"
          block
          danger
          icon={<DeleteOutlined />}
          onClick={() => setFullOpen(true)}
        >
          完整卸载
        </Button>
      </div>

      {/* Update progress modal: live progress bar + scrolling log. */}
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
            status={
              updateStatus?.failed
                ? "exception"
                : updateStatus?.done
                ? "success"
                : "active"
            }
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
        <pre className="update-log">
          {(updateStatus?.log_tail || []).join("\n") || "等待日志输出..."}
        </pre>
        <div style={{ textAlign: "right", marginTop: 12 }}>
          {finished ? (
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
          这将删除整个平台目录及其全部文件（含 data、config、plugins/user）。
          该操作不可恢复。
        </Paragraph>
        <Paragraph>
          如只需从 Capture 移除菜单、保留平台，请改用「移除 Cadence 集成」。
        </Paragraph>
        <Text>请输入 </Text>
        <Text code>DELETE</Text>
        <Text> 以确认：</Text>
        <Input
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="DELETE"
          style={{ marginTop: 8 }}
        />
      </Modal>
    </div>
  );
}
