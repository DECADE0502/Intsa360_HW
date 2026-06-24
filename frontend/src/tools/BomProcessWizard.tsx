import { useMemo, useState } from "react";
import { Alert, Button, Card, Checkbox, Input, Space, Steps, Table, Tag, Typography } from "antd";
import { Copy, Play } from "lucide-react";
import { runTool } from "../api/client";
import { ResultPanel } from "../components/ResultPanel";

const CAPTURE_CONFIG =
  "{Item}\\t{Quantity}\\t{Reference}\\t{Part Number}\\t{Value}\\t{规格型号}\\t{器件描述（新整理）}\\t{物料名称}\\t{等级}\\t{PCB Footprint}\\t{PCB封装}\\t{Part Type}\\t{Part Reference}\\t{Source Package}\\t{Source Part}";

type Props = {
  onResult?: (result: unknown) => void;
};

export function BomProcessWizard({ onResult }: Props) {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const presetSource = params.get("source") || "";
  const presetName = params.get("name") || "";
  const [name, setName] = useState(presetName);
  const [parentCode, setParentCode] = useState("");
  const [parentDesc, setParentDesc] = useState("");
  const [formats, setFormats] = useState<string[]>(["plm", "oa"]);
  const [conflictChoices, setConflictChoices] = useState<Record<string, number>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function handleRun(extra: Record<string, unknown> = {}) {
    if (!presetSource) {
      setResult({ status: "error", error: "未收到 Cadence 导出的 BOM 文件路径，请从 Capture 点击导出并处理。" });
      return;
    }
    setRunning(true);
    try {
      const payload = await runTool("bom_process", {
        source_bom: presetSource,
        formats,
        name,
        parent_code: parentCode,
        parent_desc: parentDesc,
        ...extra,
      });
      setResult(payload);
      onResult?.(payload);
    } catch (err: any) {
      setResult({ status: "error", error: err.message || "处理失败" });
    } finally {
      setRunning(false);
    }
  }

  const needsConfirm = result?.status === "needs_confirmation";

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Steps current={presetSource ? 1 : 0} items={[{ title: "导出配置" }, { title: "自动处理" }, { title: "复核打包" }]} />

      <Card title="Capture BOM 导出配置">
        <Typography.Paragraph>表头和组合属性字符串都填入下列字段。</Typography.Paragraph>
        <Input.TextArea readOnly value={CAPTURE_CONFIG} autoSize />
        <Button type="primary" icon={<Copy size={16} />} onClick={() => navigator.clipboard.writeText(CAPTURE_CONFIG)} style={{ marginTop: 12 }}>
          复制配置
        </Button>
      </Card>

      <Card title="Cadence 已导出文件">
        {presetSource ? (
          <Alert type="success" showIcon message="已接收到 Capture 导出的 BOM" description={presetSource} />
        ) : (
          <Alert type="warning" showIcon message="未检测到自动导出的 BOM" description="请从 OrCAD Capture 菜单点击“导出并处理 BOM”。" />
        )}
        <Space direction="vertical" size="middle" style={{ width: "100%", marginTop: 16 }}>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="成品名称" />
          <Input value={parentCode} onChange={(event) => setParentCode(event.target.value)} placeholder="父项编码" />
          <Input value={parentDesc} onChange={(event) => setParentDesc(event.target.value)} placeholder="父项描述" />
          <Checkbox.Group value={formats} onChange={(value) => setFormats(value.map(String))}>
            <Checkbox value="plm">PLM</Checkbox>
            <Checkbox value="oa">OA</Checkbox>
          </Checkbox.Group>
          <Button type="primary" icon={<Play size={16} />} loading={running} onClick={() => handleRun()}>
            开始处理
          </Button>
        </Space>
      </Card>

      {needsConfirm ? (
        <Card title="物料编码冲突确认">
          <Typography.Paragraph>{result.message}</Typography.Paragraph>
          <Space direction="vertical" size="middle" style={{ width: "100%", marginBottom: 12 }}>
            {(result.conflicts || []).map((conflict: any) => (
              <Card key={conflict.code} size="small" title={`物料编码 ${conflict.code}`}>
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(_, index) => `${conflict.code}-${index}`}
                  dataSource={(conflict.variants || []).map((variant: any, index: number) => ({ ...variant, index }))}
                  columns={[
                    {
                      title: "选择",
                      dataIndex: "index",
                      width: 96,
                      render: (index: number) =>
                        conflictChoices[conflict.code] === index ? (
                          <Tag color="blue">已保留</Tag>
                        ) : (
                          <Button size="small" onClick={() => setConflictChoices((prev) => ({ ...prev, [conflict.code]: index }))}>
                            保留此项
                          </Button>
                        ),
                    },
                    { title: "物料名称", dataIndex: "name" },
                    { title: "型号", dataIndex: "model" },
                    { title: "描述", dataIndex: "desc" },
                    { title: "等级", dataIndex: "grade" },
                    {
                      title: "受影响位号",
                      dataIndex: "refs",
                      render: (refs: string[]) => (refs || []).join(", "),
                    },
                    { title: "数量", dataIndex: "count" },
                  ]}
                />
              </Card>
            ))}
          </Space>
          <Space>
            <Button type="primary" loading={running} onClick={() => handleRun({ merge_conflicts: true, conflict_choices: conflictChoices })}>
              按所选项合并
            </Button>
            <Button loading={running} onClick={() => handleRun({ merge_conflicts: false })}>
              不合并
            </Button>
          </Space>
        </Card>
      ) : null}

      <ResultPanel result={result} />
    </Space>
  );
}
