import { useEffect, useMemo, useState } from "react";
import { Button, Empty, Modal, Select, Space, Tag, Typography } from "antd";
import { DatabaseOutlined, ReloadOutlined } from "@ant-design/icons";
import { fetchAssets, type AssetItem } from "../api/client";

type Props = {
  value?: string;
  onChange: (path: string) => void;
  placeholder?: string;
  disabled?: boolean;
};

function labelOf(asset: AssetItem) {
  return (
    <Space size={8}>
      <Tag color={asset.format === "PLM" ? "blue" : asset.format === "OA" ? "green" : "default"}>{asset.format || "BOM"}</Tag>
      <span>{asset.name}</span>
      {asset.time ? <Typography.Text type="secondary">{asset.time}</Typography.Text> : null}
    </Space>
  );
}

export function HistoryBomPicker({ value, onChange, placeholder = "从历史记录选择已处理 BOM", disabled }: Props) {
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const payload = await fetchAssets();
      setAssets(payload.groups?.processed_bom || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const onAssetsUpdated = () => load();
    window.addEventListener("insta360_hw:assets-updated", onAssetsUpdated);
    return () => window.removeEventListener("insta360_hw:assets-updated", onAssetsUpdated);
  }, []);

  const options = useMemo(
    () =>
      assets.map((asset) => ({
        value: asset.path,
        label: labelOf(asset),
        search: `${asset.name} ${asset.format} ${asset.time} ${asset.path}`.toLowerCase(),
      })),
    [assets],
  );
  const selected = assets.find((asset) => asset.path === value);

  return (
    <>
      <Space.Compact style={{ width: "100%" }}>
        <Button
          icon={<DatabaseOutlined />}
          disabled={disabled}
          loading={loading}
          onClick={() => setOpen(true)}
          style={{ width: "100%" }}
        >
          {selected ? `历史 BOM：${selected.name}` : "选择历史 BOM"}
        </Button>
        {value ? <Button onClick={() => onChange("")}>清除</Button> : null}
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load} />
      </Space.Compact>
      <Modal
        title="选择历史 BOM"
        open={open}
        okText="使用所选 BOM"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={() => setOpen(false)}
      >
        <Typography.Paragraph type="secondary">
          这里列出 BOM 处理工具生成过的 PLM/OA 成品 BOM，可直接用于对比、风险检查和封装检查。
        </Typography.Paragraph>
        <Select
          allowClear
          showSearch
          disabled={disabled}
          loading={loading}
          value={value || undefined}
          placeholder={placeholder}
          options={options}
          optionFilterProp="search"
          notFoundContent={<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可复用的历史 BOM" />}
          onChange={(next) => onChange(next || "")}
          style={{ width: "100%" }}
        />
      </Modal>
    </>
  );
}
