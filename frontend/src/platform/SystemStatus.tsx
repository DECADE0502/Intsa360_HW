import { Card, Descriptions } from "antd";

export function SystemStatus({ status }: { status: any }) {
  return (
    <Card title="系统状态">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="平台">{status?.platform || "Insta360硬件提效平台"}</Descriptions.Item>
        <Descriptions.Item label="工具数量">{status?.tools ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="Cadence 脚本">{status?.cadence_scripts ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="可挂载脚本">{status?.enableable_scripts ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="已挂载脚本">{status?.enabled_scripts ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="待拆分脚本">{status?.pending_scripts ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="安装目录">{status?.root || "-"}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
