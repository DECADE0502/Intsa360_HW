import { useEffect, useMemo, useState } from "react";
import { Button, Empty, Select, Space, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
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

  const options = useMemo(
    () =>
      assets.map((asset) => ({
        value: asset.path,
        label: labelOf(asset),
        search: `${asset.name} ${asset.format} ${asset.time} ${asset.path}`.toLowerCase(),
      })),
    [assets],
  );

  return (
    <Space.Compact style={{ width: "100%" }}>
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
      <Button icon={<ReloadOutlined />} loading={loading} onClick={load} />
    </Space.Compact>
  );
}
