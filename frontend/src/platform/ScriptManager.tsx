import { App, Button, Collapse, Empty, Popconfirm, Space, Switch, Table, Tabs, Tag, Typography } from "antd";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { setPluginCadenceMenuVisibility, type PluginInfo } from "../api/client";

const dangerText: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

const captureReloadCommand =
  'source [file join $env(HOME) "cdssetup/OrCAD_Capture/tclscripts/capAutoLoad/iac_bom_tool.tcl"]';

function dangerColor(value?: string) {
  if (value === "high") return "red";
  if (value === "medium") return "gold";
  return "green";
}

function sourceTag(value: string) {
  if (value === "system") return <Tag>Cadence 系统</Tag>;
  if (value === "platform") return <Tag color="geekblue">平台自带</Tag>;
  return <Tag color="blue">自定义</Tag>;
}

export function ScriptManager({
  plugins,
  onPluginChange,
  onRefresh,
}: {
  plugins: { system: PluginInfo[]; platform: PluginInfo[]; user: PluginInfo[] };
  onPluginChange: (plugin: PluginInfo) => void;
  onRefresh: () => Promise<unknown>;
}) {
  const { message } = App.useApp();
  const [updating, setUpdating] = useState<Record<string, boolean>>({});
  const [refreshing, setRefreshing] = useState(false);

  const manageable = useMemo(() => [...plugins.platform, ...plugins.user], [plugins.platform, plugins.user]);
  const mounted = manageable.filter((item) => item.show_in_cadence);
  const unmounted = manageable.filter((item) => !item.show_in_cadence);

  async function refreshList(showToast = true) {
    setRefreshing(true);
    try {
      await onRefresh();
      if (showToast) message.success("插件状态已刷新");
    } catch (err: any) {
      message.error(err.message || "插件状态刷新失败");
    } finally {
      setRefreshing(false);
    }
  }

  async function copyCaptureReloadCommand() {
    try {
      await navigator.clipboard.writeText(captureReloadCommand);
      message.success("热更新指令已复制");
    } catch {
      message.error("复制失败，请手动选择指令");
    }
  }

  async function updatePluginMenu(item: PluginInfo, checked: boolean) {
    setUpdating((prev) => ({ ...prev, [item.id]: true }));
    try {
      const updated = await setPluginCadenceMenuVisibility(item.id, checked);
      onPluginChange(updated);
      await refreshList(false);
      message.success(checked ? "已挂载到 Cadence 菜单" : "已从 Cadence 菜单移除");
    } catch (err: any) {
      message.error(err.message || "菜单状态更新失败");
    } finally {
      setUpdating((prev) => ({ ...prev, [item.id]: false }));
    }
  }

  const columns = [
    { title: "脚本名称", dataIndex: "name", width: 210 },
    { title: "说明", dataIndex: "description", ellipsis: true },
    { title: "命令", dataIndex: "command", ellipsis: true },
    {
      title: "来源",
      dataIndex: "source",
      width: 110,
      render: sourceTag,
    },
    {
      title: "风险",
      dataIndex: "danger_level",
      width: 90,
      render: (value: string) => <Tag color={dangerColor(value)}>{dangerText[value] || "未分级"}</Tag>,
    },
    {
      title: "菜单状态",
      dataIndex: "show_in_cadence",
      width: 100,
      render: (value: boolean) => (value ? <Tag color="blue">已挂载</Tag> : <Tag>未挂载</Tag>),
    },
    {
      title: "操作",
      width: 110,
      render: (_: unknown, item: PluginInfo) => {
        if (item.readonly) return <Tag>只读</Tag>;
        if (item.can_enable === false) return <Tag>待拆分</Tag>;
        const control = (
          <Switch
            checked={item.show_in_cadence}
            loading={!!updating[item.id]}
            onChange={(checked) => updatePluginMenu(item, checked)}
          />
        );
        if (item.requires_confirmation && !item.show_in_cadence) {
          return (
            <Popconfirm
              title="确认挂载脚本"
              description="该脚本会进入 Cadence 菜单，请确认已经验证。"
              okText="挂载"
              cancelText="取消"
              onConfirm={() => updatePluginMenu(item, true)}
            >
              {control}
            </Popconfirm>
          );
        }
        return control;
      },
    },
  ];

  function renderTable(data: PluginInfo[], emptyText: string) {
    return data.length > 0 ? (
      <Table size="middle" rowKey="id" dataSource={data} pagination={{ pageSize: 10 }} columns={columns} />
    ) : (
      <Empty description={emptyText} />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="script-manager-head">
        <div>
          <Typography.Title level={3}>插件管理</Typography.Title>
          <Typography.Text type="secondary">
            Cadence 官方脚本只做识别和查看；平台自带脚本与自定义脚本可管理，启用后统一挂载到 Capture 的 insta360_HW 菜单。
          </Typography.Text>
        </div>
        <Button icon={<RefreshCw size={16} />} loading={refreshing} onClick={() => refreshList()}>
          刷新
        </Button>
      </div>

      <Tabs
        items={[
          {
            key: "mounted",
            label: `已挂载（${mounted.length}）`,
            children: renderTable(mounted, "暂无已挂载脚本。打开未挂载脚本的开关后，会出现在这里。"),
          },
          {
            key: "unmounted",
            label: `未挂载（${unmounted.length}）`,
            children: renderTable(unmounted, "暂无未挂载脚本。"),
          },
        ]}
      />

      <Collapse
        items={[
          {
            key: "system",
            label: `Cadence 系统脚本（只读，${plugins.system.length} 个）`,
            children: renderTable(plugins.system, "未识别到 Cadence 系统脚本。"),
          },
        ]}
      />

      <div className="capture-reload-tip">
        <div>
          <Typography.Text strong>Capture 热更新指令</Typography.Text>
          <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            在 Capture 的 Command Window 粘贴执行，可重新加载当前菜单脚本，避免每次挂载后都重启 Capture。
          </Typography.Paragraph>
          <Typography.Text code copyable={false}>
            {captureReloadCommand}
          </Typography.Text>
        </div>
        <Button onClick={copyCaptureReloadCommand}>复制指令</Button>
      </div>
    </Space>
  );
}
