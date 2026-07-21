import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Input, Segmented, Space, Switch, Tabs, Tag, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
  DeleteOutlined,
  FileExcelOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import { runSmtLayout, type SmtComponent, type SmtLayoutResponse } from "../api/client";
import { toUserMessage } from "../api/errors";
import { PcbCanvas } from "../components/PcbCanvas";
import { RefdesVirtualList, type RefdesListItem } from "../components/RefdesVirtualList";
import { useToolWorkspace } from "../state/toolWorkspace";


type SmtLayoutWorkspace = {
  smt: string;
  bom: string;
  netlist: string;
  result: SmtLayoutResponse | null;
  activeTab: string;
};


function NcLayoutTab({
  result,
  selectedRef,
  onSelectedRef,
}: {
  result: SmtLayoutResponse | null;
  selectedRef: string;
  onSelectedRef: (ref: string) => void;
}) {
  const [side, setSide] = useState<"top" | "bottom" | "both">("both");
  const [shOnly, setShOnly] = useState(false);
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [hoveredRef, setHoveredRef] = useState("");
  const [frameSelectedRefs, setFrameSelectedRefs] = useState<string[] | null>(null);
  const [canvasKey, setCanvasKey] = useState(0);
  const components = result?.components || [];
  const componentByRef = useMemo(
    () => new Map(components.map((component) => [component.ref.toUpperCase(), component])),
    [components],
  );
  const layerComponents = useMemo(
    () =>
      components.filter((component) => {
        if (shOnly && !/^SH/i.test(component.ref)) return false;
        if (highRiskOnly && !component.high_risk) return false;
        return true;
      }),
    [components, shOnly, highRiskOnly],
  );
  const ncItems = useMemo<RefdesListItem[]>(
    () =>
      (result?.nc_summary?.refs || []).map((ref) => {
        const component = componentByRef.get(ref.toUpperCase());
        return {
          ref,
          part_number: component?.part_number || "",
          description: component?.description || "",
          side: component?.side || "top",
          high_risk: component?.high_risk || false,
        };
      }),
    [result?.nc_summary?.refs, componentByRef],
  );
  const visibleNcItems = useMemo(() => {
    const frameRefs = frameSelectedRefs ? new Set(frameSelectedRefs.map((ref) => ref.toUpperCase())) : null;
    return ncItems.filter((item) => {
      if (side !== "both" && item.side !== side) return false;
      if (shOnly && !/^SH/i.test(item.ref)) return false;
      if (highRiskOnly && !item.high_risk) return false;
      if (frameRefs && !frameRefs.has(item.ref.toUpperCase())) return false;
      return true;
    });
  }, [ncItems, side, shOnly, highRiskOnly, frameSelectedRefs]);
  const highlightedRefs = useMemo(
    () => new Set([hoveredRef, selectedRef].filter(Boolean)),
    [hoveredRef, selectedRef],
  );

  if (!result) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此查看 NC 布局" />;
  }
  if (!result.board) {
    return <Alert type="warning" showIcon message="结果中没有可用板框，请重新选择正确的 SMT 资料目录。" />;
  }

  function resetScopedFilters() {
    setFrameSelectedRefs(null);
    setShOnly(false);
    setHighRiskOnly(false);
  }

  return (
    <div className="smt-nc-tab">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 12,
        }}
      >
        <Space wrap>
          <Segmented
            aria-label="板面筛选"
            value={side}
            options={[
              { label: "正面", value: "top" },
              { label: "背面", value: "bottom" },
              { label: "全部", value: "both" },
            ]}
            onChange={(value) => setSide(value as "top" | "bottom" | "both")}
          />
          <Space size={6}>
            <Switch
              size="small"
              aria-label="仅显示 SH 位号"
              checked={shOnly}
              onChange={(checked) => {
                setShOnly(checked);
                setFrameSelectedRefs(null);
              }}
            />
            <Typography.Text>SH 图层</Typography.Text>
          </Space>
          <Space size={6}>
            <Switch
              size="small"
              aria-label="仅显示高风险器件"
              checked={highRiskOnly}
              onChange={(checked) => {
                setHighRiskOnly(checked);
                setFrameSelectedRefs(null);
              }}
            />
            <Typography.Text>高风险图层</Typography.Text>
          </Space>
          {frameSelectedRefs ? (
            <Tag
              closable
              color="blue"
              onClose={(event) => {
                event.preventDefault();
                setFrameSelectedRefs(null);
              }}
            >
              框选 {frameSelectedRefs.length} 项
            </Tag>
          ) : null}
        </Space>
        <Space>
          {(frameSelectedRefs || shOnly || highRiskOnly) ? (
            <Button size="small" onClick={resetScopedFilters}>
              重置筛选
            </Button>
          ) : null}
          <Tooltip title="重置板图缩放与位置">
            <Button
              size="small"
              aria-label="重置板图视图"
              icon={<ReloadOutlined />}
              onClick={() => setCanvasKey((value) => value + 1)}
            />
          </Tooltip>
        </Space>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px minmax(0, 1fr)", gap: 12, minHeight: 520 }}>
        <section style={{ border: "1px solid #e2e5e9", borderRadius: 6, padding: 10, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <Typography.Text strong>NC 位号</Typography.Text>
            <Typography.Text type="secondary">{visibleNcItems.length} / {ncItems.length}</Typography.Text>
          </div>
          <RefdesVirtualList
            items={visibleNcItems}
            selectedRef={selectedRef}
            onHover={(ref) => setHoveredRef(ref || "")}
            onSelect={onSelectedRef}
          />
        </section>
        <section style={{ minWidth: 0, height: 520 }}>
          <PcbCanvas
            key={canvasKey}
            outline={result.board.outline_rings}
            components={layerComponents}
            side={side}
            highlightedRefs={highlightedRefs}
            onHover={(ref) => setHoveredRef(ref || "")}
            onSelect={onSelectedRef}
            onFrameSelect={(refs) => setFrameSelectedRefs(refs)}
            colorScheme="nc-emphasis"
          />
        </section>
      </div>
    </div>
  );
}


export function SmtLayoutPane() {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace<SmtLayoutWorkspace>(
    "smt_layout",
    {
      smt: "",
      bom: "",
      netlist: "",
      result: null,
      activeTab: "nc",
    },
    { heavyKeys: ["result"] },
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [selectedRef, setSelectedRef] = useState("");

  useEffect(() => {
    if (!workspace.netlist && workspace.activeTab === "sanity") {
      setWorkspace((current) => ({ ...current, activeTab: "nc" }));
    }
  }, [workspace.netlist, workspace.activeTab, setWorkspace]);

  function updateField(field: "smt" | "bom" | "netlist", value: string) {
    setWorkspace((current) => ({ ...current, [field]: value }));
  }

  async function handleRun() {
    if (!workspace.smt.trim() || !workspace.bom.trim()) {
      setError("请选择 SMT 资料文件夹和处理后的 BOM。 ");
      return;
    }
    setRunning(true);
    setError("");
    try {
      const result = await runSmtLayout({
        smt_folder: workspace.smt.trim(),
        processed_bom: workspace.bom.trim(),
        ...(workspace.netlist.trim() ? { netlist_folder: workspace.netlist.trim() } : {}),
      });
      setWorkspace((current) => ({ ...current, result }));
    } catch (runError) {
      setError(toUserMessage(runError));
    } finally {
      setRunning(false);
    }
  }

  function handleClear() {
    setError("");
    setSelectedRef("");
    resetWorkspace();
  }

  const pending = <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成分析后在此查看结果" />;
  const tabs = [
    {
      key: "nc",
      label: "NC 布局对照",
      children: <NcLayoutTab result={workspace.result} selectedRef={selectedRef} onSelectedRef={setSelectedRef} />,
    },
    { key: "fai", label: "首件核对表", children: pending },
    {
      key: "sanity",
      label: workspace.netlist ? (
        "三向一致性"
      ) : (
        <Tooltip title="需网表文件夹">
          <span>三向一致性</span>
        </Tooltip>
      ),
      disabled: !workspace.netlist,
      children: pending,
    },
  ];

  return (
    <div className="smt-layout-pane">
      <div style={{ marginBottom: 18 }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          SMT 布局分析
        </Typography.Title>
        <Typography.Text type="secondary">
          对照贴片坐标、处理后 BOM 与 Cadence 网表，生成 NC 布局、首件核对表和三向一致性结果。
        </Typography.Text>
      </div>

      <div
        className="smt-layout-inputs"
        style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1fr) minmax(220px, 1fr) minmax(220px, 1fr)", gap: 10 }}
      >
        <Input
          aria-label="SMT 资料文件夹"
          prefix={<FolderOpenOutlined />}
          placeholder="SMT 资料文件夹路径（含 XY.txt）"
          value={workspace.smt}
          onChange={(event) => updateField("smt", event.target.value)}
          allowClear
        />
        <Input
          aria-label="处理后的 BOM"
          prefix={<FileExcelOutlined />}
          placeholder="处理后的 PLM 或 OA BOM 路径"
          value={workspace.bom}
          onChange={(event) => updateField("bom", event.target.value)}
          allowClear
        />
        <Input
          aria-label="网表文件夹"
          prefix={<ApartmentOutlined />}
          placeholder="网表文件夹路径（可选）"
          value={workspace.netlist}
          onChange={(event) => updateField("netlist", event.target.value)}
          allowClear
        />
      </div>

      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={handleRun}>
          开始分析
        </Button>
        <Button icon={<DeleteOutlined />} onClick={handleClear}>
          清空
        </Button>
      </Space>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
      <Tabs
        activeKey={workspace.activeTab}
        onChange={(activeTab) => setWorkspace((current) => ({ ...current, activeTab }))}
        items={tabs}
      />
    </div>
  );
}
