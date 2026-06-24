import { Upload } from "antd";
import type { UploadFile } from "antd";
import { uiText } from "../i18n/zhCN";

type Props = {
  label: string;
  accept?: string;
  multiple?: boolean;
  value: File[];
  onChange: (files: File[]) => void;
};

export function FileInputField({ label, accept, multiple, value, onChange }: Props) {
  const fileList: UploadFile[] = value.map((file, index) => ({ uid: `${index}`, name: file.name, status: "done" }));
  return (
    <Upload.Dragger
      multiple={multiple}
      accept={accept}
      beforeUpload={(file) => {
        onChange(multiple ? [...value, file] : [file]);
        return false;
      }}
      onRemove={(file) => {
        onChange(value.filter((item) => item.name !== file.name));
      }}
      fileList={fileList}
    >
      <p>{label}</p>
      <p className="ant-upload-hint">{uiText.uploadHint}</p>
    </Upload.Dragger>
  );
}
