import type { Dispatch, SetStateAction } from "react";
import { Alert, Button, Space, Typography, Upload } from "antd";
import {
  ApartmentOutlined,
  DeleteOutlined,
  FileExcelOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";

import { HistoryBomPicker } from "../../components/HistoryBomPicker";
import styles from "./SmtAnalysisPane.module.css";


type SourceStepProps = {
  smtFiles: File[];
  bomFile?: File;
  netlistFiles: File[];
  historyBom: string;
  historyDecisionManifest: string;
  historySemanticManifest: string;
  busy: boolean;
  error: string;
  onSmtFiles: Dispatch<SetStateAction<File[]>>;
  onBomFile: (file?: File) => void;
  onNetlistFiles: Dispatch<SetStateAction<File[]>>;
  onHistoryBom: (
    path: string,
    decisionManifest?: string,
    semanticManifest?: string,
  ) => void;
  onStart: () => void;
  onClear: () => void;
};

function relativeName(file: File) {
  return (
    (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
    file.name
  ).replaceAll("\\", "/");
}

function addFile(current: File[], file: File) {
  const key = relativeName(file).toLocaleLowerCase();
  if (
    current.some(
      (item) =>
        relativeName(item).toLocaleLowerCase() === key &&
        item.size === file.size &&
        item.lastModified === file.lastModified,
    )
  ) {
    return current;
  }
  return [...current, file];
}

function directoryLabel(files: File[]) {
  if (!files.length) return "未选择";
  const first = relativeName(files[0]).split("/").filter(Boolean);
  const root = first.length > 1 ? first[0] : "";
  return `${root ? `${root} · ` : ""}${files.length} 个文件`;
}

function DirectoryInput({
  title,
  hint,
  button,
  files,
  optional,
  onFiles,
}: {
  title: string;
  hint: string;
  button: string;
  files: File[];
  optional?: boolean;
  onFiles: Dispatch<SetStateAction<File[]>>;
}) {
  return (
    <section className={styles.sourceField}>
      <div className={styles.sourceFieldHeader}>
        <div>
          <Typography.Text strong>{title}</Typography.Text>
          {optional ? (
            <Typography.Text type="secondary">（可选）</Typography.Text>
          ) : null}
          <Typography.Paragraph type="secondary" className={styles.fieldHint}>
            {hint}
          </Typography.Paragraph>
        </div>
        <Typography.Text
          type={files.length ? "success" : "secondary"}
          ellipsis={{ tooltip: directoryLabel(files) }}
        >
          {directoryLabel(files)}
        </Typography.Text>
      </div>
      <Space wrap>
        <Upload
          directory
          multiple
          fileList={[]}
          showUploadList={false}
          beforeUpload={(file) => {
            onFiles((current) => addFile(current, file));
            return false;
          }}
        >
          <Button
            aria-label={button}
            icon={title.startsWith("Cadence") ? <ApartmentOutlined /> : <FolderOpenOutlined />}
          >
            {button}
          </Button>
        </Upload>
        {files.length ? (
          <Button
            aria-label={`清除${title}`}
            icon={<DeleteOutlined />}
            onClick={() => onFiles([])}
          >
            清除
          </Button>
        ) : null}
      </Space>
    </section>
  );
}

export function SourceStep({
  smtFiles,
  bomFile,
  netlistFiles,
  historyBom,
  historyDecisionManifest,
  historySemanticManifest,
  busy,
  error,
  onSmtFiles,
  onBomFile,
  onNetlistFiles,
  onHistoryBom,
  onStart,
  onClear,
}: SourceStepProps) {
  const linked = Boolean(
    historyBom && (historyDecisionManifest || historySemanticManifest),
  );
  return (
    <div className={styles.sourceStep}>
      <DirectoryInput
        title="SMT 贴片资料目录"
        hint="完整选择供应商资料目录，平台会识别位号图、坐标、板框及其它制造资料。"
        button="选择 SMT 资料目录"
        files={smtFiles}
        onFiles={onSmtFiles}
      />

      <section className={styles.sourceField}>
        <div className={styles.sourceFieldHeader}>
          <div>
            <Typography.Text strong>处理后的 PLM/OA 成品 BOM</Typography.Text>
            <Typography.Paragraph type="secondary" className={styles.fieldHint}>
              选择实际装机 BOM；历史 BOM 会自动关联同次处理记录。
            </Typography.Paragraph>
          </div>
          <Typography.Text
            type={historyBom || bomFile ? "success" : "secondary"}
            ellipsis={{ tooltip: historyBom || bomFile?.name || "未选择" }}
          >
            {historyBom ? "历史 BOM" : bomFile?.name || "未选择"}
          </Typography.Text>
        </div>
        <Space wrap>
          <HistoryBomPicker
            value={historyBom}
            onChange={(path, asset) => {
              onHistoryBom(
                path,
                asset?.decision_manifest || "",
                asset?.semantic_manifest || "",
              );
              if (path) onBomFile(undefined);
            }}
          />
          <Upload
            accept=".xlsx,.xls"
            maxCount={1}
            fileList={
              bomFile
                ? [{ uid: "bom", name: bomFile.name, status: "done" as const }]
                : []
            }
            beforeUpload={(file) => {
              onBomFile(file);
              onHistoryBom("", "", "");
              return false;
            }}
            onRemove={() => {
              onBomFile(undefined);
              return true;
            }}
          >
            <Button
              aria-label="选择 PLM/OA BOM"
              icon={<FileExcelOutlined />}
            >
              选择本地 BOM
            </Button>
          </Upload>
        </Space>
        {linked ? (
          <Typography.Text type="success">
            已自动关联该 BOM 的处理记录
          </Typography.Text>
        ) : null}
      </section>

      <DirectoryInput
        title="Cadence 网表目录"
        hint="用于增强器件、电气连接和封装一致性证据，不单独决定装机或 NC。"
        button="选择网表目录"
        files={netlistFiles}
        optional
        onFiles={onNetlistFiles}
      />

      {error ? <Alert type="error" showIcon message={error} /> : null}
      <div className={styles.sourceActions}>
        <Button
          aria-label="扫描并识别资料"
          type="primary"
          size="large"
          icon={<PlayCircleOutlined />}
          loading={busy}
          onClick={onStart}
        >
          扫描并识别资料
        </Button>
        <Button icon={<DeleteOutlined />} disabled={busy} onClick={onClear}>
          清空
        </Button>
      </div>
    </div>
  );
}
