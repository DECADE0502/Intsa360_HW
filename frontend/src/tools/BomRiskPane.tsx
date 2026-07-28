import { useEffect, useState } from "react";
import { Alert, Button, Space, Typography, Upload } from "antd";
import { DeleteOutlined, InboxOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { runTool, uploadFiles, type ToolInfo } from "../api/client";
import { toUserMessage } from "../api/errors";
import { HistoryBomPicker } from "../components/HistoryBomPicker";
import { useToolWorkspace } from "../state/toolWorkspace";
import { RiskFindings, type RiskReport } from "./bomRisk/RiskFindings";

type RiskResult = {
  status: string;
  error?: string;
  message?: string;
  outputs?: string[];
  risk_report?: RiskReport;
};

export function BomRiskPane({ tool }: { tool: ToolInfo }) {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace(
    "bom_risk_check_v2",
    { historyBom: "", result: null as RiskResult | null },
    { heavyKeys: ["result"] },
  );
  const [file, setFile] = useState<File | null>(null);
  const [historyBom, setHistoryBom] = useState(String(workspace.historyBom || ""));
  const [result, setResult] = useState<RiskResult | null>(workspace.result || null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    setWorkspace({ historyBom, result });
  }, [historyBom, result, setWorkspace]);

  async function inspect() {
    if (!file && !historyBom) return;
    setRunning(true);
    try {
      const bom = file ? (await uploadFiles([file])).files[0]?.path : historyBom;
      setResult(await runTool(tool.id, { bom }));
    } catch (error) {
      setResult({ status: "error", error: toUserMessage(error) });
    } finally {
      setRunning(false);
    }
  }

  function clear() {
    setFile(null);
    setHistoryBom("");
    setResult(null);
    resetWorkspace();
  }

  return (
    <div className="bom-risk-pane">
      <div className="tool-heading">
        <div>
          <Typography.Text type="secondary">单份 BOM 导入前体检</Typography.Text>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{tool.description}</Typography.Paragraph>
        </div>
        <Space>
          <Button
            type="primary"
            size="large"
            icon={<SafetyCertificateOutlined />}
            loading={running}
            disabled={!file && !historyBom}
            onClick={() => void inspect()}
          >
            开始风险检查
          </Button>
          <Button icon={<DeleteOutlined />} onClick={clear}>清空并重来</Button>
        </Space>
      </div>

      <div className="bom-risk-source">
        <div>
          <Typography.Text strong>从历史记录选择</Typography.Text>
          <HistoryBomPicker value={historyBom} onChange={(value) => { setHistoryBom(value); setFile(null); }} />
        </div>
        <span className="bom-risk-source-divider">或</span>
        <Upload.Dragger
          accept=".xlsx,.xls"
          maxCount={1}
          fileList={file ? [{ uid: "risk-bom", name: file.name, status: "done" }] : []}
          beforeUpload={(selected) => {
            setFile(selected);
            setHistoryBom("");
            return false;
          }}
          onRemove={() => {
            setFile(null);
          }}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">选择或拖入待检查的 BOM</p>
          <p className="ant-upload-hint">支持 Capture、PLM 单板和 OA BOM 格式</p>
        </Upload.Dragger>
      </div>

      {result?.status === "error" ? (
        <Alert type="error" showIcon message="风险检查失败" description={result.error || result.message} />
      ) : (
        <RiskFindings report={result?.risk_report} outputs={result?.outputs || []} />
      )}
    </div>
  );
}
