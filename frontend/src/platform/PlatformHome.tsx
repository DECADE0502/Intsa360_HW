import { Card, Col, Row, Typography } from "antd";
import type { Capability, PluginInfo, ToolInfo } from "../api/client";

export function PlatformHome({
  caps,
  tools,
  plugins,
}: {
  caps: Capability[];
  tools: ToolInfo[];
  plugins: { system: PluginInfo[]; platform: PluginInfo[]; user: PluginInfo[] };
}) {
  const scripts = caps.filter((c) => c.type === "cadence_tcl");
  const enabledPlugins = [...plugins.platform, ...plugins.user].filter((item) => item.show_in_cadence);

  return (
    <>
      <Typography.Title level={3}>Insta360硬件提效平台</Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 32 }}>
        BOM 处理 · 差异对比 · 风险检查 · 网表分析 · 插件管理 · OTA 更新
      </Typography.Paragraph>

      <Row gutter={[12, 12]} style={{ marginBottom: 40 }}>
        {[
          { label: "Web 工具", value: tools.length },
          { label: "Cadence 系统脚本", value: plugins.system.length },
          { label: "平台脚本", value: plugins.platform.length || scripts.length },
          { label: "自定义脚本", value: plugins.user.length },
          { label: "已挂载到 Cadence", value: enabledPlugins.length },
        ].map((s) => (
          <Col xs={12} md={8} xl={4} key={s.label}>
            <div style={{ padding: "18px 20px", background: "#fafafa", borderRadius: 8, border: "1px solid #f0f0f0" }}>
              <div style={{ fontSize: 12, color: "#888", marginBottom: 6 }}>{s.label}</div>
              <span style={{ fontSize: 28, fontWeight: 700, color: "#1d1d1f" }}>{s.value}</span>
            </div>
          </Col>
        ))}
      </Row>

      <Typography.Title level={5} style={{ marginBottom: 12 }}>
        Web 工具
      </Typography.Title>
      <Row gutter={[12, 12]} style={{ marginBottom: 36 }}>
        {tools.map((t) => (
          <Col xs={24} sm={12} key={t.id}>
            <Card hoverable size="small" title={t.name} style={{ height: "100%" }}>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                {t.description}
              </Typography.Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Typography.Title level={5} style={{ marginBottom: 8 }}>
        Cadence 插件
      </Typography.Title>
      <Typography.Text type="secondary">
        Cadence 官方脚本 {plugins.system.length} 个只读展示；平台脚本 {plugins.platform.length || scripts.length} 个、自定义脚本 {plugins.user.length} 个可管理。启用后统一挂载到 Capture 的 insta360_HW 菜单。
      </Typography.Text>
    </>
  );
}
