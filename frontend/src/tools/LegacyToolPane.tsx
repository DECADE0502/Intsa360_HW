import { useState } from "react";
import { Button, Card, Space, Typography, Upload } from "antd";
import { PlayCircleOutlined, DeleteOutlined } from "@ant-design/icons";
import { runTool, uploadFiles, type ToolInfo } from "../api/client";
import { toolInputs } from "./toolConfig";
import { ResultPanel } from "../components/ResultPanel";
import { BomComparePane } from "./BomComparePane";

export function LegacyToolPane({ tool }: { tool: ToolInfo }) {
  if (tool.id === "bom_compare") return <BomComparePane tool={tool} />;

  const inputs = toolInputs[tool.id] || [];
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function handleRun() {
    setRunning(true);
    try {
      const params: Record<string, unknown> = {};
      for (const input of inputs) {
        const selected = files[input.key] || [];
        if (!selected.length) continue;
        const uploaded = await uploadFiles(selected);
        params[input.key] = input.multiple ? uploaded.files.map((f) => f.path) : uploaded.files[0]?.path;
      }
      setResult(await runTool(tool.id, params));
    } catch (err: any) { setResult({ status: "error", error: err.message }); }
    finally { setRunning(false); }
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Typography.Title level={4} style={{ marginBottom: 8 }}>{tool.name}</Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 28 }}>{tool.description}</Typography.Paragraph>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        {inputs.map((input) => (
          <Card key={input.key} size="small">
            <Typography.Text style={{ display: "block", marginBottom: 8, fontSize: 13, color: "#8a8f98" }}>{input.label}</Typography.Text>
            <Upload accept={input.accept} multiple={!!input.multiple}
              fileList={(files[input.key] || []).map((f, i) => ({ uid: String(i), name: f.name, status: "done" as const }))}
              beforeUpload={(file) => {
                setFiles((prev) => ({ ...prev, [input.key]: [...(prev[input.key] || []), file] }));
                return false;
              }}
              onRemove={(f) => setFiles((prev) => ({ ...prev, [input.key]: (prev[input.key] || []).filter((_, i) => String(i) !== f.uid) }))}>
              <Button>选择文件</Button>
            </Upload>
          </Card>
        ))}
        <Space>
          <Button type="primary" loading={running} onClick={handleRun} icon={<PlayCircleOutlined />}>开始运行</Button>
          <Button onClick={() => setFiles({})} icon={<DeleteOutlined />}>清空</Button>
        </Space>
        <ResultPanel result={result} />
      </Space>
    </div>
  );
}
