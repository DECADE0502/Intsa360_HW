import { Card, Col, Row, Statistic, Typography } from "antd";
import type { Capability } from "../api/client";

export function PlatformHome({ capabilities }: { capabilities: Capability[] }) {
  const webTools = capabilities.filter((item) => item.type === "web_tool");
  const scripts = capabilities.filter((item) => item.type === "cadence_tcl");
  const enabledScripts = scripts.filter((item) => item.show_in_cadence);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="Web 工具" value={webTools.length} />
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="Cadence 脚本" value={scripts.length} />
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="已挂载脚本" value={enabledScripts.length} />
        </Card>
      </Col>
      <Col span={24}>
        <Card title="今日工作台">
          <Typography.Text type="secondary">从左侧选择 BOM、网表、SMT 或脚本管理能力。</Typography.Text>
        </Card>
      </Col>
    </Row>
  );
}
