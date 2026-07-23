import { Button, Empty, Tag } from "antd";
import { Download, FileJson, FileSpreadsheet } from "lucide-react";
import { outputHref } from "../../utils/outputHref";

function outputMeta(path: string) {
  const normalized = path.toLowerCase();
  if (normalized.endsWith(".json")) {
    return { label: "机器可读语义 JSON", icon: <FileJson size={16} />, tag: "JSON" };
  }
  if (normalized.includes("四层")) {
    return { label: "四层差异报告", icon: <FileSpreadsheet size={16} />, tag: "XLSX" };
  }
  return { label: "兼容版差异报告", icon: <FileSpreadsheet size={16} />, tag: "XLSX" };
}

export function ExportPanel({ outputs, canExport }: { outputs: string[]; canExport: boolean }) {
  if (!outputs.length) return <Empty description="尚未生成交付文件" />;
  return (
    <div className="bom-export-list">
      {outputs.map((path) => {
        const meta = outputMeta(path);
        const name = path.split(/[\\/]/).pop() || path;
        return (
          <div className="bom-export-row" key={path}>
            <div className="bom-export-icon">{meta.icon}</div>
            <div>
              <strong>{meta.label}</strong>
              <span>{name}</span>
            </div>
            <Tag>{meta.tag}</Tag>
            <Button
              type="primary"
              ghost
              disabled={!canExport && meta.tag !== "JSON" && !name.includes("四层")}
              href={outputHref(path)}
              icon={<Download size={15} />}
            >
              下载
            </Button>
          </div>
        );
      })}
    </div>
  );
}

