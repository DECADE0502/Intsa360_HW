import { useEffect, useState } from "react";
import { Alert, Button, Empty, Input, Space, Tabs, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
  DeleteOutlined,
  FileExcelOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";

import { runSmtLayout, type SmtLayoutResponse } from "../api/client";
import { toUserMessage } from "../api/errors";
import { useToolWorkspace } from "../state/toolWorkspace";


type SmtLayoutWorkspace = {
  smt: string;
  bom: string;
  netlist: string;
  result: SmtLayoutResponse | null;
  activeTab: string;
};


export function SmtLayoutPane() {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace<SmtLayoutWorkspace>(
    "smt_layout",
    {
      smt: "",
      bom: "",
      netlist: "",
      result: null,
      activeTab: "nc",
    },
    { heavyKeys: ["result"] },
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!workspace.netlist && workspace.activeTab === "sanity") {
      setWorkspace((current) => ({ ...current, activeTab: "nc" }));
    }
  }, [workspace.netlist, workspace.activeTab, setWorkspace]);

  function updateField(field: "smt" | "bom" | "netlist", value: string) {
    setWorkspace((current) => ({ ...current, [field]: value }));
  }

  async function handleRun() {
    if (!workspace.smt.trim() || !workspace.bom.trim()) {
      setError("请选择 SMT 资料文件夹和处理后的 BOM。 ");
      return;
    }
    setRunning(true);
    setError("");
    try {
      const result = await runSmtLayout({
        smt_folder: workspace.smt.trim(),
        processed_bom: workspace.bom.trim(),
        ...(workspace.netlist.trim() ? { netlist_folder: workspace.netlist.trim() } : {}),
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
    resetWorkspace();
  }

  const pending = <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此查看结果" />;
  const tabs = [
    { key: "nc", label: "NC 布局对照", children: pending },
    { key: "fai", label: "首件核对表", children: pending },
    {
      key: "sanity",
      label: workspace.netlist ? (
        "三向一致性"
      ) : (
        <Tooltip title="需网表文件夹">
          <span>三向一致性</span>
        </Tooltip>
      ),
      disabled: !workspace.netlist,
      children: pending,
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
        <Input
          aria-label="SMT 资料文件夹"
          prefix={<FolderOpenOutlined />}
          placeholder="SMT 资料文件夹路径（含 XY.txt）"
          value={workspace.smt}
          onChange={(event) => updateField("smt", event.target.value)}
          allowClear
        />
        <Input
          aria-label="处理后的 BOM"
          prefix={<FileExcelOutlined />}
          placeholder="处理后的 PLM 或 OA BOM 路径"
          value={workspace.bom}
          onChange={(event) => updateField("bom", event.target.value)}
          allowClear
        />
        <Input
          aria-label="网表文件夹"
          prefix={<ApartmentOutlined />}
          placeholder="网表文件夹路径（可选）"
          value={workspace.netlist}
          onChange={(event) => updateField("netlist", event.target.value)}
          allowClear
        />
      </div>

      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={handleRun}>
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
