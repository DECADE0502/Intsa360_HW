import { Alert, Button, Space, Table, Typography } from "antd";
import { uiText } from "../i18n/zhCN";

function outputHref(path: string) {
  const normalized = path.replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const index = normalized.indexOf(marker);
  const rel = index >= 0 ? normalized.slice(index + marker.length) : normalized.replace(/^data\/outputs\//, "");
  return `/outputs/${encodeURI(rel)}`;
}

export function ResultPanel({ result }: { result: any }) {
  if (!result) return <Alert type="info" message={uiText.noResult} />;
  if (result.status !== "ok") return <Alert type="error" message={result.error || result.message || "运行失败"} />;
  const table = result.table;
  const columns = table?.headers?.map((header: string, index: number) => ({ title: header, dataIndex: String(index), key: String(index) })) || [];
  const data = table?.rows?.map((row: unknown[], index: number) => ({ key: index, ...Object.fromEntries(row.map((value, i) => [String(i), value])) })) || [];
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Text type="success">{uiText.runFinished}</Typography.Text>
      {result.outputs?.length ? (
        <Space wrap>
          {result.outputs.map((path: string) => (
            <Button key={path} href={outputHref(path)}>
              {uiText.downloadReport}
            </Button>
          ))}
        </Space>
      ) : null}
      {table ? <Table size="small" columns={columns} dataSource={data} scroll={{ x: true }} /> : null}
    </Space>
  );
}
