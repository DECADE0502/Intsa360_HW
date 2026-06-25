import { useEffect, useState } from "react";
import { Badge, Button, Input, Modal, Typography, message } from "antd";
import {
  CheckCircleOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  checkUninstall,
  checkUpdate,
  runUninstall,
  startUpdate,
} from "../api/client";

const { Text } = Typography;

/**
 * Sidebar footer "维护" card. Groups the platform-level lifecycle actions
 * (OTA update, detach Cadence integration, full uninstall) into one clearly
 * layered block instead of a pile of buttons:
 *   - version row (status readout, with remote-version comparison)
 *   - safe actions (update / detach)
 *   - danger action (full uninstall), visually separated and gated by a
 *     typed DELETE confirmation modal.
 */
export function UpdateStatus({ version }: { version: string }) {
  const [updating, setUpdating] = useState(false);
  const [detaching, setDetaching] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [fulling, setFulling] = useState(false);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [remoteVersion, setRemoteVersion] = useState<string>("");

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

  async function onUpdate() {
    setUpdating(true);
    try {
      await startUpdate();
      message.success("已开始更新，完成后会自动重启服务");
    } catch (e) {
      message.error((e as Error).message || "更新启动失败");
    } finally {
      setUpdating(false);
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
          loading={updating}
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
        <Typography.Paragraph type="danger" strong>
          这将删除整个平台目录及其全部文件（含 data、config、plugins/user）。
          该操作不可恢复。
        </Typography.Paragraph>
        <Typography.Paragraph>
          如只需从 Capture 移除菜单、保留平台，请改用「移除 Cadence 集成」。
        </Typography.Paragraph>
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
