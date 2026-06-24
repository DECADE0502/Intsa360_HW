import { App, Popconfirm, Switch, Table, Tag } from "antd";
import { useState } from "react";
import { setCadenceMenuVisibility, type Capability } from "../api/client";

const dangerText: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

export function ScriptManager({
  capabilities,
  onCapabilityChange,
}: {
  capabilities: Capability[];
  onCapabilityChange: (capability: Capability) => void;
}) {
  const { message } = App.useApp();
  const [updating, setUpdating] = useState<Record<string, boolean>>({});
  const scripts = capabilities.filter((item) => item.type === "cadence_tcl");

  async function updateMenu(item: Capability, checked: boolean) {
    setUpdating((prev) => ({ ...prev, [item.id]: true }));
    try {
      const updated = await setCadenceMenuVisibility(item.id, checked);
      onCapabilityChange(updated);
      message.success(checked ? "已挂载到 Cadence 菜单" : "已从 Cadence 菜单移除");
    } catch (err: any) {
      message.error(err.message || "菜单状态更新失败");
    } finally {
      setUpdating((prev) => ({ ...prev, [item.id]: false }));
    }
  }

  return (
    <Table
      size="middle"
      rowKey="id"
      dataSource={scripts}
      pagination={{ pageSize: 8 }}
      columns={[
        { title: "脚本名称", dataIndex: "name" },
        { title: "说明", dataIndex: "description" },
        { title: "命令", dataIndex: "command" },
        {
          title: "风险",
          dataIndex: "danger_level",
          render: (value: string) => (
            <Tag color={value === "high" ? "red" : value === "medium" ? "gold" : "green"}>{dangerText[value] || "未分级"}</Tag>
          ),
        },
        {
          title: "菜单状态",
          dataIndex: "show_in_cadence",
          render: (value: boolean) => (value ? <Tag color="blue">已挂载</Tag> : <Tag>未挂载</Tag>),
        },
        {
          title: "操作",
          render: (_: unknown, item: Capability) =>
            item.can_enable === false ? (
              <Tag>待拆分</Tag>
            ) : item.requires_confirmation && !item.show_in_cadence ? (
              <Popconfirm
                title="确认挂载脚本"
                description="该脚本会进入 Cadence 菜单，请确认已完成验证。"
                okText="挂载"
                cancelText="取消"
                onConfirm={() => updateMenu(item, true)}
              >
                <Switch checked={item.show_in_cadence} loading={!!updating[item.id]} />
              </Popconfirm>
            ) : (
              <Switch
                checked={item.show_in_cadence}
                loading={!!updating[item.id]}
                onChange={(checked) => updateMenu(item, checked)}
              />
            ),
        },
      ]}
    />
  );
}
