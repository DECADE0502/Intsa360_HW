import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Empty,
  Input,
  Pagination,
  Progress,
  Radio,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  InfoCircleOutlined,
  RightOutlined,
  WarningOutlined,
} from "@ant-design/icons";

export type PlacementAction = "" | "keep" | "exclude" | "keep_as_is";

export type PlacementEvidence = {
  kind: string;
  field: string;
  value: string;
  polarity: string;
  strength: string;
  display: string;
  shape_id?: string;
};

export type PlacementGroup = {
  key: string;
  row_numbers: number[];
  refs: string[];
  position_count: number;
  state: string;
  category: string;
  confidence: string;
  recommended_action: "keep" | "exclude" | null;
  suggested_code: string;
  sh_review: boolean;
  rule_id: string;
  evidence: PlacementEvidence[];
  original_fields: Record<string, string>;
  inferred_fields: Record<string, string>;
};

export type PlacementResolution = {
  action: PlacementAction;
  part_number: string;
  field_patch: {
    name: string;
    model: string;
    desc: string;
    grade: string;
    unit: string;
  };
  decision_source?: "manual" | "recommendation" | "default";
};

type ReadonlyNc = {
  count: number;
  items: Array<{
    row_number: number;
    refs: string[];
    value: string;
    description: string;
    rule_id: string;
    evidence: PlacementEvidence[];
  }>;
};

const PAGE_SIZE = 8;
const FIELD_LABELS: Record<string, string> = {
  part_number: "子项编码",
  value: "器件值（Value）",
  name: "物料名称",
  model: "型号",
  desc: "描述",
  grade: "优选等级",
  unit: "单位",
  pcb_footprint: "PCB 封装（Footprint）",
  pcb_package: "Capture PCB 封装",
  source_package: "原理图封装",
  source_part: "原理图库器件",
};
const ORIGINAL_FIELDS = [
  "part_number",
  "value",
  "name",
  "model",
  "desc",
  "pcb_footprint",
  "pcb_package",
  "source_package",
  "source_part",
];

const TAB_DEFS = [
  { key: "suspected_material", label: "疑似物料" },
  { key: "suspected_process", label: "疑似工艺件" },
  { key: "shield", label: "屏蔽支架" },
  { key: "conflicting", label: "属性冲突" },
  { key: "insufficient_data", label: "数据不足" },
] as const;

const RESOLUTION_FIELD_KEYS = ["name", "model", "desc", "grade", "unit"] as const;

function invalidPlacementText(value: string | undefined) {
  const text = String(value || "").trim();
  return Boolean(text) && (
    text.startsWith("{")
    || text.includes("\ufffd")
    || text.includes("锟斤拷")
  );
}

function usablePlacementText(value: string | undefined) {
  return invalidPlacementText(value) ? "" : String(value || "");
}

function blankResolution(group: PlacementGroup): PlacementResolution {
  return {
    action: "",
    part_number: usablePlacementText(group.inferred_fields.part_number)
      || usablePlacementText(group.suggested_code),
    field_patch: {
      name: usablePlacementText(group.inferred_fields.name),
      model: usablePlacementText(group.inferred_fields.model),
      desc: usablePlacementText(group.inferred_fields.desc),
      grade: usablePlacementText(group.inferred_fields.grade),
      unit: usablePlacementText(group.inferred_fields.unit),
    },
  };
}

function sanitizeSavedResolution(
  group: PlacementGroup,
  current: PlacementResolution,
): PlacementResolution {
  const fallback = blankResolution(group);
  const partNumber = current.part_number === undefined || invalidPlacementText(current.part_number)
    ? fallback.part_number
    : current.part_number;
  let patchChanged = false;
  const fieldPatch = { ...fallback.field_patch };

  RESOLUTION_FIELD_KEYS.forEach((field) => {
    const savedValue = current.field_patch?.[field];
    const value = savedValue === undefined || invalidPlacementText(savedValue)
      ? fallback.field_patch[field]
      : savedValue;
    fieldPatch[field] = value;
    patchChanged ||= value !== savedValue;
  });

  if (partNumber === current.part_number && !patchChanged) return current;
  return {
    ...current,
    part_number: partNumber,
    field_patch: fieldPatch,
  };
}

export function seedPlacementResolutions(
  groups: PlacementGroup[],
  current: Record<string, PlacementResolution>,
): Record<string, PlacementResolution> {
  const next: Record<string, PlacementResolution> = {};
  groups.forEach((group) => {
    next[group.key] = current[group.key]
      ? sanitizeSavedResolution(group, current[group.key])
      : blankResolution(group);
  });
  const currentKeys = Object.keys(current);
  if (
    currentKeys.length === Object.keys(next).length
    && currentKeys.every((key) => next[key] === current[key])
  ) {
    return current;
  }
  return next;
}

function effectiveText(group: PlacementGroup, resolution: PlacementResolution, field: "name" | "model" | "desc") {
  const invalidOriginal = group.evidence.some((item) => (
    item.field === field && (item.kind === "placeholder_residue" || item.kind === "mojibake")
  ));
  return usablePlacementText(resolution.field_patch[field])
    || usablePlacementText(group.inferred_fields[field])
    || (invalidOriginal ? "" : usablePlacementText(group.original_fields[field]));
}

export function placementResolutionComplete(group: PlacementGroup, resolution?: PlacementResolution) {
  if (!resolution || !resolution.action) return false;
  if (resolution.action === "exclude") return true;
  const code = usablePlacementText(resolution.part_number)
    || usablePlacementText(group.inferred_fields.part_number)
    || usablePlacementText(group.original_fields.part_number);
  if (!code.trim()) return false;
  return (["name", "model", "desc"] as const).some((field) => effectiveText(group, resolution, field).trim());
}

export function placementResolutionsComplete(
  groups: PlacementGroup[],
  resolutions: Record<string, PlacementResolution>,
  visitedTabs: string[],
) {
  const hasInsufficient = groups.some((group) => group.category === "insufficient_data");
  if (hasInsufficient && !visitedTabs.includes("insufficient_data")) return false;
  return groups.every((group) => placementResolutionComplete(group, resolutions[group.key]));
}

function recommendationText(action: PlacementGroup["recommended_action"]) {
  if (action === "keep") return "建议纳入";
  if (action === "exclude") return "建议不装";
  return "需要判断";
}

function compactRefs(refs: string[]) {
  const visible = refs.slice(0, 8);
  return (
    <div className="placement-ref-list">
      {visible.map((ref) => <Tag key={ref}>{ref}</Tag>)}
      {refs.length > visible.length && <Tag>另 {refs.length - visible.length} 个</Tag>}
    </div>
  );
}

function evidenceColor(item: PlacementEvidence) {
  if (item.polarity === "nc") return "red";
  if (item.polarity === "process") return "orange";
  if (item.polarity === "material+") return item.strength === "strong" ? "green" : "blue";
  return "default";
}

function PlacementInput({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="placement-edit-field">
      <span>{label}</span>
      <Input
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function PlacementDetail({
  group,
  resolution,
  onChange,
}: {
  group: PlacementGroup;
  resolution: PlacementResolution;
  onChange: (value: PlacementResolution) => void;
}) {
  const update = (patch: Partial<PlacementResolution>) => {
    onChange({ ...resolution, ...patch, decision_source: "manual" });
  };
  const updateField = (field: keyof PlacementResolution["field_patch"], value: string) => {
    update({ field_patch: { ...resolution.field_patch, [field]: value } });
  };
  const canKeepAsIs = group.state === "conflicting";
  const editing = resolution.action !== "exclude" && resolution.action !== "keep_as_is";
  const residueFields = new Set(
    group.evidence
      .filter((item) => item.kind === "placeholder_residue" || item.kind === "mojibake")
      .map((item) => item.field),
  );

  return (
    <div className="placement-detail" key={group.key}>
      <div className="placement-detail-head">
        <div>
          <div className="placement-detail-title">{compactRefs(group.refs)}</div>
          <Space size={6} wrap>
            <Tooltip title={`分类规则 ${group.rule_id}`}><Tag>{group.rule_id}</Tag></Tooltip>
            <Tag color={group.confidence === "strong" ? "green" : "gold"}>
              {group.confidence === "strong" ? "证据充分" : "证据较弱"}
            </Tag>
            <Tag color={group.recommended_action === "keep" ? "green" : group.recommended_action === "exclude" ? "orange" : "default"}>
              {recommendationText(group.recommended_action)}
            </Tag>
          </Space>
        </div>
        <Radio.Group
          optionType="button"
          buttonStyle="solid"
          value={resolution.action || undefined}
          onChange={(event) => update({ action: event.target.value })}
          options={[
            { label: "纳入 BOM", value: "keep" },
            { label: "确认不装", value: "exclude" },
            ...(canKeepAsIs ? [{ label: "保留现字段", value: "keep_as_is" }] : []),
          ]}
        />
      </div>

      <div className="placement-evidence-row">
        {group.evidence.map((item, index) => (
          <Tag color={evidenceColor(item)} key={`${item.kind}-${item.field}-${index}`}>
            {item.display}
          </Tag>
        ))}
      </div>

      <div className="placement-field-compare">
        <section className="placement-field-panel">
          <Typography.Text strong>原始字段</Typography.Text>
          <div className="placement-raw-grid">
            {ORIGINAL_FIELDS.map((field) => (
              <div className="placement-raw-row" key={field}>
                <span>{FIELD_LABELS[field] || field}</span>
                <Typography.Text className={residueFields.has(field) ? "is-suspicious" : ""}>
                  {group.original_fields[field] || "-"}
                </Typography.Text>
              </div>
            ))}
          </div>
        </section>
        <section className="placement-field-panel">
          <Typography.Text strong>确认后的字段</Typography.Text>
          <div className="placement-edit-grid">
            <PlacementInput
              label="子项编码"
              value={resolution.part_number}
              disabled={!editing}
              onChange={(value) => update({ part_number: value })}
            />
            <PlacementInput label="物料名称" value={resolution.field_patch.name} disabled={!editing} onChange={(value) => updateField("name", value)} />
            <PlacementInput label="型号" value={resolution.field_patch.model} disabled={!editing} onChange={(value) => updateField("model", value)} />
            <PlacementInput label="描述" value={resolution.field_patch.desc} disabled={!editing} onChange={(value) => updateField("desc", value)} />
            <div className="placement-edit-pair">
              <PlacementInput label="优选等级" value={resolution.field_patch.grade} disabled={!editing} onChange={(value) => updateField("grade", value)} />
              <PlacementInput label="单位" value={resolution.field_patch.unit} disabled={!editing} onChange={(value) => updateField("unit", value)} />
            </div>
          </div>
          {resolution.action === "keep" && !placementResolutionComplete(group, resolution) && (
            <Alert type="warning" showIcon message="纳入 BOM 时必须有子项编码，并至少保留名称、型号或描述之一。" />
          )}
        </section>
      </div>
    </div>
  );
}

export function PlacementReview({
  groups,
  readonlyNc,
  resolutions,
  visitedTabs,
  onResolutionsChange,
  onVisitedTabsChange,
  onApply,
  onBack,
  running,
}: {
  groups: PlacementGroup[];
  readonlyNc: ReadonlyNc;
  resolutions: Record<string, PlacementResolution>;
  visitedTabs: string[];
  onResolutionsChange: (value: Record<string, PlacementResolution>) => void;
  onVisitedTabsChange: (value: string[]) => void;
  onApply: () => void;
  onBack: () => void;
  running: boolean;
}) {
  const { modal } = App.useApp();
  const grouped = useMemo(() => {
    const result: Record<string, PlacementGroup[]> = {};
    TAB_DEFS.forEach((tab) => { result[tab.key] = []; });
    groups.forEach((group) => {
      (result[group.category] ||= []).push(group);
    });
    return result;
  }, [groups]);
  const availableTabs = useMemo(() => [
    ...TAB_DEFS.filter((tab) => grouped[tab.key]?.length),
    ...(readonlyNc.count ? [{ key: "readonly_nc", label: "已判 NC" } as const] : []),
  ], [grouped, readonlyNc.count]);
  const [activeTab, setActiveTab] = useState<string>(availableTabs[0]?.key || "suspected_material");
  const [pages, setPages] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!availableTabs.some((tab) => tab.key === activeTab)) {
      setActiveTab(availableTabs[0]?.key || "suspected_material");
    }
  }, [availableTabs, activeTab]);

  useEffect(() => {
    if (!activeTab || visitedTabs.includes(activeTab)) return;
    onVisitedTabsChange([...visitedTabs, activeTab]);
  }, [activeTab, visitedTabs, onVisitedTabsChange]);

  useEffect(() => {
    if (activeTab !== "insufficient_data") return;
    let changed = false;
    const next = { ...resolutions };
    (grouped.insufficient_data || []).forEach((group) => {
      const current = next[group.key] || blankResolution(group);
      if (!current.action) {
        next[group.key] = { ...current, action: "exclude", decision_source: "default" };
        changed = true;
      }
    });
    if (changed) onResolutionsChange(next);
  }, [activeTab, grouped, resolutions, onResolutionsChange]);

  const completed = groups.filter((group) => placementResolutionComplete(group, resolutions[group.key])).length;
  const ready = placementResolutionsComplete(groups, resolutions, visitedTabs);
  const progress = groups.length ? Math.round((completed / groups.length) * 100) : 100;
  const page = pages[activeTab] || 1;
  const currentGroups = grouped[activeTab] || [];
  const pageGroups = currentGroups.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selectedKey = selected[activeTab];
  const activeGroup = pageGroups.find((group) => group.key === selectedKey) || pageGroups[0];
  const recommendations = pageGroups.filter((group) => (
    group.recommended_action
    && !resolutions[group.key]?.action
  ));
  const unresolvedWithoutRecommendation = groups.some((group) => (
    !group.recommended_action
    && !placementResolutionComplete(group, resolutions[group.key])
  ));

  const applyPageRecommendations = () => {
    if (!recommendations.length) return;
    const keepCount = recommendations.filter((group) => group.recommended_action === "keep").length;
    const excludeCount = recommendations.length - keepCount;
    modal.confirm({
      title: "采纳本页建议",
      content: `将纳入 ${keepCount} 组、确认不装 ${excludeCount} 组。无推荐和已人工选择的组不会被改动。`,
      okText: "确认采纳",
      cancelText: "继续核对",
      onOk: () => {
        const next = { ...resolutions };
        recommendations.forEach((group) => {
          const current = next[group.key] || blankResolution(group);
          next[group.key] = {
            ...current,
            action: group.recommended_action || "",
            decision_source: "recommendation",
          };
        });
        onResolutionsChange(next);
      },
    });
  };

  const renderGroupTab = (tabKey: string) => {
    const tabGroups = grouped[tabKey] || [];
    const tabPage = pages[tabKey] || 1;
    const visible = tabGroups.slice((tabPage - 1) * PAGE_SIZE, tabPage * PAGE_SIZE);
    const chosen = selected[tabKey];
    const detail = visible.find((group) => group.key === chosen) || visible[0];
    return (
      <div className="placement-workbench">
        <aside className="placement-index-pane">
          <div className="placement-index-list">
            {visible.map((group, index) => {
              const done = placementResolutionComplete(group, resolutions[group.key]);
              return (
                <button
                  type="button"
                  key={group.key}
                  className={`placement-index-item ${detail?.key === group.key ? "is-active" : ""}`}
                  onClick={() => setSelected((current) => ({ ...current, [tabKey]: group.key }))}
                >
                  <span className="placement-index-title">
                    {done ? <CheckCircleOutlined className="is-done" /> : <WarningOutlined />}
                    {compactRefs(group.refs)}
                  </span>
                  <span className="placement-index-meta">
                    {(tabPage - 1) * PAGE_SIZE + index + 1}. {recommendationText(group.recommended_action)}
                  </span>
                </button>
              );
            })}
          </div>
          {tabGroups.length > PAGE_SIZE && (
            <Pagination
              size="small"
              simple
              current={tabPage}
              pageSize={PAGE_SIZE}
              total={tabGroups.length}
              onChange={(value) => setPages((current) => ({ ...current, [tabKey]: value }))}
            />
          )}
        </aside>
        <main className="placement-detail-pane">
          {detail ? (
            <PlacementDetail
              group={detail}
              resolution={resolutions[detail.key] || blankResolution(detail)}
              onChange={(value) => onResolutionsChange({ ...resolutions, [detail.key]: value })}
            />
          ) : <Empty description="本分类没有待确认项" />}
        </main>
      </div>
    );
  };

  const readonlyColumns = [
    { title: "原始行", dataIndex: "row_number", width: 88 },
    { title: "位号", dataIndex: "refs", render: (refs: string[]) => compactRefs(refs) },
    { title: "Value", dataIndex: "value", width: 160, ellipsis: true },
    { title: "描述", dataIndex: "description", ellipsis: true },
    { title: "依据", dataIndex: "rule_id", width: 90, render: (value: string) => <Tag>{value}</Tag> },
  ];

  return (
    <section className="placement-review-shell">
      <header className="placement-review-head">
        <div>
          <Typography.Title level={4}>装机审查</Typography.Title>
          <Typography.Text type="secondary">逐组确认纳入 BOM 或不装。位号前缀只作提示，最终建议来自字段证据。</Typography.Text>
        </div>
        <div className="placement-progress">
          <span>已确认 {completed}/{groups.length}</span>
          <Progress percent={progress} size="small" status={ready ? "success" : "active"} showInfo={false} />
        </div>
      </header>

      {unresolvedWithoutRecommendation && (
        <Alert
          type="warning"
          showIcon
          message="存在没有明确建议的项目"
          description="请逐组核对字段与证据，并明确选择纳入、确认不装或保留现字段。"
        />
      )}

      <div className="placement-review-toolbar">
        <Space>
          <Button onClick={applyPageRecommendations} disabled={!recommendations.length}>采纳本页建议</Button>
          <Tooltip title="只处理本页未选择且有明确建议的项目">
            <InfoCircleOutlined />
          </Tooltip>
        </Space>
        <Typography.Text type="secondary">当前分类 {currentGroups.length} 组</Typography.Text>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={availableTabs.map((tab) => ({
          key: tab.key,
          label: `${tab.label} (${tab.key === "readonly_nc" ? readonlyNc.count : grouped[tab.key]?.length || 0})`,
          children: tab.key === "readonly_nc" ? (
            <Table
              size="small"
              rowKey={(row) => `${row.row_number}-${row.refs.join(",")}`}
              dataSource={readonlyNc.items}
              columns={readonlyColumns}
              pagination={{ pageSize: PAGE_SIZE }}
              scroll={{ x: 720 }}
            />
          ) : renderGroupTab(tab.key),
        }))}
      />

      <footer className="placement-review-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Space>
          {!ready && <Typography.Text type="secondary">还有 {groups.length - completed} 组未完成</Typography.Text>}
          <Button type="primary" icon={<RightOutlined />} loading={running} disabled={!ready} onClick={onApply}>
            按审查结果继续
          </Button>
        </Space>
      </footer>
    </section>
  );
}
