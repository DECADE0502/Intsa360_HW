import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Grid,
  Input,
  Pagination,
  Progress,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  InfoCircleOutlined,
  LeftOutlined,
  RightOutlined,
  WarningOutlined,
} from "@ant-design/icons";

export type PlacementDestination = "" | "smt" | "non_smt";
export type PlacementExclusion = "" | "nc" | "process_only" | "scope_excluded" | "user_excluded";
export type PlacementRole =
  | "electronic"
  | "smt_mechanical"
  | "shield"
  | "test_point"
  | "short_symbol"
  | "mounting_hole"
  | "fiducial"
  | "unknown";
export type ShieldSubtype = "" | "bracket" | "cover" | "other";

export type PlacementEvidence = {
  kind: string;
  field: string;
  value: string;
  polarity: string;
  strength: string;
  display: string;
  priority?: number;
  shape_id?: string;
};

export type PlacementResolution = {
  destination: PlacementDestination;
  exclusion_kind: PlacementExclusion;
  role: PlacementRole;
  subtype: ShieldSubtype;
  part_number_override: string;
  field_patch: {
    name: string;
    model: string;
    desc: string;
    grade: string;
    unit: string;
    manufacturer: string;
    pcb_footprint: string;
    pcb_package: string;
  };
  decision_source: "rule" | "history_exact" | "user";
};

export type PlacementGroup = {
  key: string;
  group_id?: string;
  row_numbers: number[];
  source_rows?: number[];
  refs: string[];
  physical_refs?: string[];
  position_count: number;
  state: string;
  category: string;
  confidence: string;
  recommended_action: "keep" | "exclude" | null;
  suggested_destination?: "smt" | "non_smt" | null;
  exclusion_kind?: PlacementExclusion;
  shield_subtype?: ShieldSubtype;
  suggested_code: string;
  suggested_mpn?: string;
  sh_review: boolean;
  rule_id: string;
  rule_version?: string;
  identity_status?: string;
  role: PlacementRole;
  role_confidence?: string;
  blocking_reasons?: string[];
  decision_fingerprint?: string;
  evidence: PlacementEvidence[];
  original_fields: Record<string, string>;
  inferred_fields: Record<string, string>;
  history_exact_resolution?: Partial<PlacementResolution>;
  history_hint?: { message?: string; previous_destination?: string; previous_role?: string };
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

type ReadonlyGroup = {
  group_id: string;
  physical_refs: string[];
  position_count: number;
  state: string;
  role: PlacementRole;
  suggested_destination?: "smt" | "non_smt";
  rule_id: string;
};

type QualityReport = {
  physical_part_count?: number;
  issue_count?: number;
  severity_counts?: Record<string, number>;
  issues?: Array<{ code: string; severity: string; message: string; refs?: string[] }>;
};

export type CodeVerification = {
  part_number: string;
  keyword: string;
  reason: string;
  description: string;
  refs: string[];
  row_numbers: number[];
};

const PAGE_SIZE = 10;
const FIELD_KEYS = ["name", "model", "desc", "grade", "unit", "manufacturer", "pcb_footprint", "pcb_package"] as const;
const FIELD_LABELS: Record<string, string> = {
  part_number: "子项编码",
  value: "Value",
  name: "物料名称",
  model: "型号 / MPN",
  desc: "描述",
  grade: "优选等级",
  unit: "单位",
  manufacturer: "制造商",
  pcb_footprint: "PCB Footprint",
  pcb_package: "PCB 封装",
  source_package: "Source Package",
  source_part: "Source Part",
  source_library: "Source Library",
};
const ORIGINAL_FIELDS = [
  "part_number",
  "value",
  "name",
  "model",
  "desc",
  "manufacturer",
  "grade",
  "unit",
  "pcb_footprint",
  "pcb_package",
  "source_package",
  "source_part",
];
const ROLE_LABELS: Record<PlacementRole, string> = {
  electronic: "普通电子料",
  smt_mechanical: "贴片机械件",
  shield: "屏蔽类",
  test_point: "测试点",
  short_symbol: "短接图元",
  mounting_hole: "安装孔",
  fiducial: "Mark / Fiducial",
  unknown: "未知",
};
const EXCLUSION_LABELS: Record<Exclude<PlacementExclusion, "">, string> = {
  nc: "明确 NC",
  process_only: "工艺项",
  scope_excluded: "范围排除",
  user_excluded: "用户排除",
};
const BLOCKING_LABELS: Record<string, string> = {
  shield_type_and_destination_required: "必须确认屏蔽类型和装机区域",
  same_physical_ref_multiple_part_numbers: "同一物理位号存在不同料号",
  business_field_contains_path: "物料业务字段中出现路径",
};
const FILTERS = [
  { label: "待确认", value: "pending" },
  { label: "全部", value: "all" },
  { label: "普通器件", value: "electronic" },
  { label: "机械件", value: "mechanical" },
  { label: "屏蔽类", value: "shield" },
  { label: "工艺项", value: "process" },
  { label: "NC", value: "nc" },
  { label: "数据不足", value: "insufficient" },
];

function invalidText(value: string | undefined) {
  const text = String(value || "").trim();
  return Boolean(text) && (text.startsWith("{") || text.includes("\ufffd") || text.includes("锟斤拷"));
}

function usableText(value: string | undefined) {
  return invalidText(value) ? "" : String(value || "");
}

function blankResolution(group: PlacementGroup): PlacementResolution {
  const patch = Object.fromEntries(
    FIELD_KEYS.map((field) => [field, usableText(group.inferred_fields[field])]),
  ) as PlacementResolution["field_patch"];
  return {
    destination: "",
    exclusion_kind: "",
    role: group.role || "unknown",
    // The backend supplies the default shield type, so a shield never arrives as
    // a form the operator cannot answer.
    subtype: group.role === "shield" ? group.shield_subtype || "" : "",
    part_number_override: usableText(group.inferred_fields.part_number) || usableText(group.suggested_code),
    field_patch: patch,
    decision_source: "user",
  };
}

function normalizeResolution(group: PlacementGroup, raw: Partial<PlacementResolution> | undefined): PlacementResolution {
  const fallback = blankResolution(group);
  if (!raw || ("action" in raw && !("destination" in raw))) return fallback;
  const destination = raw.destination === "smt" || raw.destination === "non_smt" ? raw.destination : "";
  const exclusion = ["nc", "process_only", "scope_excluded", "user_excluded"].includes(String(raw.exclusion_kind))
    ? raw.exclusion_kind as PlacementExclusion
    : "";
  const rawRole = String(raw.role || "");
  const role = Object.prototype.hasOwnProperty.call(ROLE_LABELS, rawRole) ? rawRole as PlacementRole : fallback.role;
  const subtype = ["bracket", "cover", "other"].includes(String(raw.subtype))
    ? raw.subtype as ShieldSubtype
    : fallback.subtype;
  const patch = { ...fallback.field_patch };
  FIELD_KEYS.forEach((field) => {
    const value = raw.field_patch?.[field];
    patch[field] = value === undefined || invalidText(value) ? fallback.field_patch[field] : value;
  });
  const override = raw.part_number_override === undefined || invalidText(raw.part_number_override)
    ? fallback.part_number_override
    : raw.part_number_override;
  return {
    destination,
    exclusion_kind: destination === "smt" ? "" : exclusion,
    role,
    subtype: role === "shield" ? subtype : "",
    part_number_override: override,
    field_patch: patch,
    decision_source: raw.decision_source === "history_exact" || raw.decision_source === "rule" ? raw.decision_source : "user",
  };
}

export function seedPlacementResolutions(
  groups: PlacementGroup[],
  current: Record<string, PlacementResolution>,
): Record<string, PlacementResolution> {
  const next: Record<string, PlacementResolution> = {};
  groups.forEach((group) => {
    const saved = current[group.key];
    const history = group.history_exact_resolution;
    next[group.key] = normalizeResolution(group, saved || (history ? { ...history, decision_source: "history_exact" } : undefined));
  });
  return JSON.stringify(next) === JSON.stringify(current) ? current : next;
}

function effectiveField(group: PlacementGroup, resolution: PlacementResolution, field: keyof PlacementResolution["field_patch"]) {
  const invalidOriginal = group.evidence.some((item) => (
    item.field === field && (item.kind === "placeholder_residue" || item.kind === "mojibake")
  ));
  return usableText(resolution.field_patch[field])
    || usableText(group.inferred_fields[field])
    || (invalidOriginal ? "" : usableText(group.original_fields[field]));
}

export function placementResolutionComplete(group: PlacementGroup, resolution?: PlacementResolution) {
  if (!resolution?.destination) return false;
  if (resolution.destination === "non_smt") return true;
  const code = usableText(resolution.part_number_override)
    || usableText(group.inferred_fields.part_number)
    || usableText(group.original_fields.part_number);
  if (!code.trim()) return false;
  return (["name", "model", "desc"] as const).some((field) => effectiveField(group, resolution, field).trim());
}

export function placementResolutionIssue(group: PlacementGroup, resolution?: PlacementResolution) {
  if (!resolution?.destination) return "请选择纳入贴片 BOM 或移到非贴片区。";
  if (resolution.destination === "non_smt") return "";
  const code = usableText(resolution.part_number_override)
    || usableText(group.inferred_fields.part_number)
    || usableText(group.original_fields.part_number);
  if (!code.trim()) return "纳入贴片 BOM 时必须填写内部子项编码。";
  if (!(["name", "model", "desc"] as const).some((field) => effectiveField(group, resolution, field).trim())) {
    return "纳入贴片 BOM 时至少需要保留物料名称、型号或描述之一。";
  }
  return "";
}

export function placementResolutionsComplete(
  groups: PlacementGroup[],
  resolutions: Record<string, PlacementResolution>,
) {
  return groups.every((group) => placementResolutionComplete(group, resolutions[group.key]));
}

function roleBucket(group: PlacementGroup) {
  if (group.role === "shield") return "shield";
  if (group.role === "smt_mechanical" || group.role === "mounting_hole") return "mechanical";
  if (["test_point", "short_symbol", "fiducial"].includes(group.role)) return "process";
  if (group.state === "confirmed_nc") return "nc";
  if (group.state === "insufficient_data") return "insufficient";
  return "electronic";
}

function displayDestination(group: PlacementGroup, resolution: PlacementResolution): "smt" | "non_smt" {
  if (resolution.destination) return resolution.destination;
  if (group.suggested_destination) return group.suggested_destination;
  return group.state === "suspected_process" ? "non_smt" : "smt";
}

function compactRefs(refs: string[]) {
  const visible = refs.slice(0, 4);
  return (
    <span className="placement-ref-list">
      {visible.join("、") || "无位号"}
      {refs.length > visible.length ? ` 等 ${refs.length} 个` : ""}
    </span>
  );
}

function evidenceColor(item: PlacementEvidence) {
  if (item.polarity === "nc") return "red";
  if (item.polarity === "process") return "orange";
  if (item.polarity === "material+") return item.strength === "strong" ? "green" : "blue";
  return "default";
}

function suggestedText(group: PlacementGroup) {
  if (group.suggested_destination === "smt") return "建议贴片";
  if (group.suggested_destination === "non_smt") return "建议非贴片";
  return "无自动建议";
}

function defaultExclusion(group: PlacementGroup, role: PlacementRole): PlacementExclusion {
  if (group.exclusion_kind) return group.exclusion_kind;
  if (["test_point", "short_symbol", "mounting_hole", "fiducial"].includes(role)) return "process_only";
  return "user_excluded";
}

function PlacementInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="placement-edit-field">
      <span>{label}</span>
      <Input aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} />
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
  onChange: (resolution: PlacementResolution) => void;
}) {
  const update = (patch: Partial<PlacementResolution>) => onChange({ ...resolution, ...patch, decision_source: "user" });
  const updateField = (field: keyof PlacementResolution["field_patch"], value: string) => {
    update({ field_patch: { ...resolution.field_patch, [field]: value } });
  };
  const sortedEvidence = [...group.evidence].sort((left, right) => (left.priority ?? 99) - (right.priority ?? 99));
  const blocking = group.blocking_reasons || [];
  const resolutionIssue = placementResolutionIssue(group, resolution);

  function chooseShieldSubtype(subtype: ShieldSubtype) {
    if (subtype === "bracket") {
      update({ subtype, destination: "smt", exclusion_kind: "", role: "shield" });
    } else if (subtype === "cover") {
      update({ subtype, destination: "non_smt", exclusion_kind: "scope_excluded", role: "shield" });
    } else {
      update({ subtype, role: "shield" });
    }
  }

  return (
    <div className="placement-detail">
      <header className="placement-detail-head">
        <div>
          <Typography.Text type="secondary">当前审查组</Typography.Text>
          <Typography.Title level={5}>{compactRefs(group.refs)}</Typography.Title>
        </div>
        <Space size={4} wrap>
          <Tag>{group.rule_id}</Tag>
          <Tag color={group.identity_status === "identity_confirmed" ? "green" : "gold"}>
            {group.identity_status === "identity_confirmed" ? "料号身份成立" : "料号待确认"}
          </Tag>
          <Tag color={resolution.destination ? "blue" : "orange"}>
            {resolution.destination === "smt" ? "贴片区" : resolution.destination === "non_smt" ? "非贴片区" : "尚未确认"}
          </Tag>
        </Space>
      </header>

      {group.history_hint?.message ? <Alert type="info" showIcon message={group.history_hint.message} /> : null}
      {resolution.decision_source === "history_exact" ? <Alert type="success" showIcon message="已精确复用历史决议，可继续修改。" /> : null}
      {resolutionIssue ? <Alert type="warning" showIcon message={resolutionIssue} /> : null}
      {blocking.length ? (
        <Alert
          type="warning"
          showIcon
          message="本组存在阻断原因"
          description={blocking.map((reason) => BLOCKING_LABELS[reason] || reason).join("；")}
        />
      ) : null}

      <section className="placement-detail-section">
        <Typography.Text strong>器件角色与区域</Typography.Text>
        <div className="placement-role-controls">
          <label>
            <span>器件角色</span>
            <Select
              aria-label="器件角色"
              value={resolution.role}
              disabled={group.sh_review}
              options={(Object.keys(ROLE_LABELS) as PlacementRole[]).map((value) => ({ value, label: ROLE_LABELS[value] }))}
              onChange={(role) => update({ role, subtype: role === "shield" ? resolution.subtype : "" })}
            />
          </label>
          {resolution.destination === "non_smt" ? (
            <label>
              <span>排除类型</span>
              <Select
                aria-label="排除类型"
                value={resolution.exclusion_kind || undefined}
                options={(Object.keys(EXCLUSION_LABELS) as Array<Exclude<PlacementExclusion, "">>).map((value) => ({
                  value,
                  label: EXCLUSION_LABELS[value],
                }))}
                onChange={(exclusion_kind) => update({ exclusion_kind })}
              />
            </label>
          ) : null}
        </div>
        {resolution.role === "shield" || group.sh_review ? (
          <div className="placement-shield-choice">
            <Typography.Text strong>屏蔽类型</Typography.Text>
            <Segmented
              aria-label="屏蔽类型"
              value={resolution.subtype}
              options={[
                { label: "屏蔽支架", value: "bracket" },
                { label: "屏蔽罩", value: "cover" },
                { label: "其他", value: "other" },
              ]}
              onChange={(value) => chooseShieldSubtype(value as ShieldSubtype)}
            />
            <Typography.Text type="secondary">
              支架自动进入贴片区；屏蔽罩自动作为范围排除；其他类型仍需用左右箭头确认区域。
            </Typography.Text>
          </div>
        ) : null}
      </section>

      <section className="placement-detail-section">
        <Typography.Text strong>证据链（高优先级在前）</Typography.Text>
        <div className="placement-evidence-list">
          {sortedEvidence.length ? sortedEvidence.map((item, index) => (
            <div className="placement-evidence-item" key={`${item.kind}-${item.field}-${index}`}>
              <Tag color={evidenceColor(item)}>P{item.priority ?? "-"}</Tag>
              <span>{item.display}</span>
            </div>
          )) : <Typography.Text type="secondary">没有可用证据</Typography.Text>}
        </div>
      </section>

      <section className="placement-detail-section">
        <Typography.Text strong>原始字段</Typography.Text>
        <div className="placement-raw-grid">
          {ORIGINAL_FIELDS.map((field) => (
            <div className="placement-raw-row" key={field}>
              <span>{FIELD_LABELS[field] || field}</span>
              <Typography.Text ellipsis={{ tooltip: group.original_fields[field] || "-" }}>
                {group.original_fields[field] || "-"}
              </Typography.Text>
            </div>
          ))}
        </div>
      </section>

      <section className="placement-detail-section">
        <Typography.Text strong>确认后的物料字段</Typography.Text>
        <div className="placement-edit-grid">
          <PlacementInput label="子项编码" value={resolution.part_number_override} onChange={(value) => update({ part_number_override: value })} />
          <PlacementInput label="物料名称" value={resolution.field_patch.name} onChange={(value) => updateField("name", value)} />
          <PlacementInput label="型号 / MPN" value={resolution.field_patch.model} onChange={(value) => updateField("model", value)} />
          <PlacementInput label="描述" value={resolution.field_patch.desc} onChange={(value) => updateField("desc", value)} />
          <PlacementInput label="制造商" value={resolution.field_patch.manufacturer} onChange={(value) => updateField("manufacturer", value)} />
          <PlacementInput label="PCB Footprint" value={resolution.field_patch.pcb_footprint} onChange={(value) => updateField("pcb_footprint", value)} />
          <PlacementInput label="PCB 封装" value={resolution.field_patch.pcb_package} onChange={(value) => updateField("pcb_package", value)} />
          <PlacementInput label="优选等级" value={resolution.field_patch.grade} onChange={(value) => updateField("grade", value)} />
          <PlacementInput label="单位" value={resolution.field_patch.unit} onChange={(value) => updateField("unit", value)} />
        </div>
      </section>
    </div>
  );
}

function ZoneList({
  title,
  destination,
  groups,
  page,
  activeKey,
  resolutions,
  onPage,
  onSelect,
  onMove,
}: {
  title: string;
  destination: "smt" | "non_smt";
  groups: PlacementGroup[];
  page: number;
  activeKey: string;
  resolutions: Record<string, PlacementResolution>;
  onPage: (page: number) => void;
  onSelect: (group: PlacementGroup) => void;
  onMove: (group: PlacementGroup, destination: "smt" | "non_smt") => void;
}) {
  const visible = groups.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const target = destination === "smt" ? "non_smt" : "smt";
  return (
    <section className={`placement-zone placement-zone-${destination}`}>
      <header>
        <div>
          <Typography.Text strong>{title}</Typography.Text>
          <Typography.Text type="secondary">{groups.length} 组</Typography.Text>
        </div>
        <Tag color={destination === "smt" ? "green" : "default"}>{destination === "smt" ? "生产贴装" : "不进入贴片 BOM"}</Tag>
      </header>
      <div className="placement-zone-list">
        {visible.length ? visible.map((group) => {
          const resolution = resolutions[group.key] || blankResolution(group);
          const complete = placementResolutionComplete(group, resolution);
          return (
            <div
              role="button"
              tabIndex={0}
              key={group.key}
              className={`placement-zone-row ${activeKey === group.key ? "is-active" : ""} ${complete ? "is-complete" : "is-pending"}`}
              onClick={() => onSelect(group)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(group);
                if (event.key === "ArrowLeft") onMove(group, "smt");
                if (event.key === "ArrowRight") onMove(group, "non_smt");
              }}
            >
              <div className="placement-zone-row-main">
                <span className="placement-zone-status">
                  {complete ? <CheckCircleOutlined /> : <WarningOutlined />}
                </span>
                <div>
                  <Typography.Text strong>{compactRefs(group.refs)}</Typography.Text>
                  <div className="placement-zone-row-meta">
                    <span>{ROLE_LABELS[resolution.role || group.role]}</span>
                    <span>{group.original_fields.part_number || group.suggested_code || "无内部编码"}</span>
                  </div>
                </div>
              </div>
              <div className="placement-zone-row-actions">
                {!complete ? <Tag color="orange">待确认</Tag> : null}
                <Tag>{suggestedText(group)}</Tag>
                {!complete ? (
                  <Tooltip title={`确认保留在${destination === "smt" ? "贴片区" : "非贴片区"}`}>
                    <Button
                      size="small"
                      type="text"
                      aria-label={`确认 ${group.refs.join("、")} 保留在${destination === "smt" ? "贴片区" : "非贴片区"}`}
                      icon={<CheckCircleOutlined />}
                      onClick={(event) => {
                        event.stopPropagation();
                        onMove(group, destination);
                      }}
                    />
                  </Tooltip>
                ) : null}
                <Tooltip title={target === "smt" ? "移到贴片区（←）" : "移到非贴片区（→）"}>
                  <Button
                    size="small"
                    type="text"
                    aria-label={`将 ${group.refs.join("、")} 移到${target === "smt" ? "贴片区" : "非贴片区"}`}
                    icon={target === "smt" ? <LeftOutlined /> : <RightOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      onMove(group, target);
                    }}
                  />
                </Tooltip>
              </div>
            </div>
          );
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有项目" />}
      </div>
      <footer>
        <Pagination
          simple
          size="small"
          current={Math.min(page, Math.max(1, Math.ceil(groups.length / PAGE_SIZE)))}
          pageSize={PAGE_SIZE}
          total={groups.length}
          onChange={onPage}
        />
      </footer>
    </section>
  );
}

export function PlacementReview({
  groups,
  readonlyNc,
  readonlyGroups = [],
  codeVerification = [],
  qualityReport,
  resolutions,
  onResolutionsChange,
  onApply,
  onBack,
  running,
}: {
  groups: PlacementGroup[];
  readonlyNc: ReadonlyNc;
  readonlyGroups?: ReadonlyGroup[];
  codeVerification?: CodeVerification[];
  qualityReport?: QualityReport;
  resolutions: Record<string, PlacementResolution>;
  onResolutionsChange: (value: Record<string, PlacementResolution>) => void;
  onApply: () => void;
  onBack: () => void;
  running: boolean;
}) {
  const { modal } = App.useApp();
  const screens = Grid.useBreakpoint();
  const [filter, setFilter] = useState("pending");
  const [pages, setPages] = useState({ smt: 1, non_smt: 1 });
  const [activeKey, setActiveKey] = useState(groups[0]?.key || "");
  const [drawerOpen, setDrawerOpen] = useState(false);

  const completed = groups.filter((group) => placementResolutionComplete(group, resolutions[group.key])).length;
  const ready = placementResolutionsComplete(groups, resolutions);
  const progress = groups.length ? Math.round((completed / groups.length) * 100) : 100;
  const filtered = useMemo(() => groups.filter((group) => {
    if (filter === "all") return true;
    if (filter === "pending") return !placementResolutionComplete(group, resolutions[group.key]);
    return roleBucket(group) === filter;
  }), [groups, filter, resolutions]);
  const smtGroups = filtered.filter((group) => displayDestination(group, resolutions[group.key] || blankResolution(group)) === "smt");
  const nonSmtGroups = filtered.filter((group) => displayDestination(group, resolutions[group.key] || blankResolution(group)) === "non_smt");
  const visibleGroups = [
    ...smtGroups.slice((pages.smt - 1) * PAGE_SIZE, pages.smt * PAGE_SIZE),
    ...nonSmtGroups.slice((pages.non_smt - 1) * PAGE_SIZE, pages.non_smt * PAGE_SIZE),
  ];
  const activeGroup = groups.find((group) => group.key === activeKey) || visibleGroups[0] || groups[0];
  const safeRecommendations = visibleGroups.filter((group) => {
    const resolution = resolutions[group.key] || blankResolution(group);
    return !resolution.destination
      && Boolean(group.suggested_destination)
      && group.confidence === "strong"
      && group.state !== "conflicting"
      && group.role !== "shield";
  });

  useEffect(() => {
    if (activeGroup && activeGroup.key !== activeKey) setActiveKey(activeGroup.key);
  }, [activeGroup, activeKey]);

  useEffect(() => {
    setPages({ smt: 1, non_smt: 1 });
  }, [filter]);

  function selectGroup(group: PlacementGroup) {
    setActiveKey(group.key);
    if (!screens.lg) setDrawerOpen(true);
  }

  function moveGroup(group: PlacementGroup, destination: "smt" | "non_smt", source: "rule" | "user" = "user") {
    const current = resolutions[group.key] || blankResolution(group);
    let subtype = current.subtype;
    // Zone and shield type are two views of one fact: a bracket is placed, a cover
    // is not. Follow the zone the operator picked instead of clearing the type and
    // leaving the group unanswerable. An explicit "other" is preserved.
    if (current.role === "shield" && subtype !== "other") {
      subtype = destination === "smt" ? "bracket" : "cover";
    }
    const exclusion_kind = destination === "smt"
      ? ""
      : subtype === "cover"
        ? "scope_excluded"
        : defaultExclusion(group, current.role);
    onResolutionsChange({
      ...resolutions,
      [group.key]: {
        ...current,
        destination,
        exclusion_kind,
        subtype,
        decision_source: source,
      },
    });
    setActiveKey(group.key);
  }

  function applyVisibleRecommendations() {
    if (!safeRecommendations.length) return;
    const smtCount = safeRecommendations.filter((group) => group.suggested_destination === "smt").length;
    modal.confirm({
      title: "采纳当前页安全建议",
      content: `将确认 ${smtCount} 组进入贴片区、${safeRecommendations.length - smtCount} 组进入非贴片区。冲突项、SH 和弱证据项不会被批量处理。`,
      okText: "确认采纳",
      cancelText: "继续核对",
      onOk: () => {
        const next = { ...resolutions };
        safeRecommendations.forEach((group) => {
          const current = next[group.key] || blankResolution(group);
          const destination = group.suggested_destination as "smt" | "non_smt";
          next[group.key] = {
            ...current,
            destination,
            exclusion_kind: destination === "smt" ? "" : defaultExclusion(group, current.role),
            decision_source: "rule",
          };
        });
        onResolutionsChange(next);
      },
    });
  }

  const detail = activeGroup ? (
    <PlacementDetail
      group={activeGroup}
      resolution={resolutions[activeGroup.key] || blankResolution(activeGroup)}
      onChange={(resolution) => onResolutionsChange({ ...resolutions, [activeGroup.key]: resolution })}
    />
  ) : <Empty description="没有待审查项目" />;

  const readonlyColumns = [
    { title: "位号", dataIndex: "physical_refs", render: (refs: string[]) => compactRefs(refs || []) },
    { title: "角色", dataIndex: "role", width: 130, render: (role: PlacementRole) => ROLE_LABELS[role] || role },
    { title: "区域", dataIndex: "suggested_destination", width: 110, render: (value: string) => value === "smt" ? "贴片区" : "非贴片区" },
    { title: "规则", dataIndex: "rule_id", width: 80 },
  ];
  const ncColumns = [
    { title: "原始行", dataIndex: "row_number", width: 80 },
    { title: "位号", dataIndex: "refs", render: (refs: string[]) => compactRefs(refs) },
    { title: "Value", dataIndex: "value", width: 150, ellipsis: true },
    { title: "描述", dataIndex: "description", ellipsis: true },
    { title: "规则", dataIndex: "rule_id", width: 80 },
  ];
  const verificationColumns = [
    { title: "编码", dataIndex: "part_number", width: 170, ellipsis: true },
    { title: "工艺词", dataIndex: "keyword", width: 120, ellipsis: true },
    { title: "位号", dataIndex: "refs", width: 180, render: (refs: string[]) => compactRefs(refs || []) },
    { title: "描述", dataIndex: "description", ellipsis: true },
    { title: "查验原因", dataIndex: "reason", ellipsis: true },
  ];

  return (
    <section className="placement-review-shell">
      <header className="placement-review-head">
        <div>
          <Typography.Title level={4}>装机归类审查</Typography.Title>
          <Typography.Text type="secondary">判断优先级：料号身份 → 位号角色 → 封装/库信息 → Value/型号/名称 → 描述。</Typography.Text>
        </div>
        <div className="placement-progress">
          <span>已确认 {completed}/{groups.length}</span>
          <Progress percent={progress} size="small" status={ready ? "success" : "active"} showInfo={false} />
        </div>
      </header>

      {qualityReport?.issue_count ? (
        <Alert
          type={(qualityReport.severity_counts?.error || qualityReport.severity_counts?.blocking) ? "warning" : "info"}
          showIcon
          message={`源 BOM 有 ${qualityReport.issue_count} 项质量提示`}
          description={(qualityReport.issues || []).slice(0, 3).map((issue) => issue.message).join("；")}
        />
      ) : null}

      <div className="placement-review-toolbar">
        <Segmented
          aria-label="审查筛选"
          value={filter}
          options={FILTERS}
          onChange={(value) => setFilter(String(value))}
        />
        <Space>
          <Button onClick={applyVisibleRecommendations} disabled={!safeRecommendations.length}>采纳当前页安全建议</Button>
          <Tooltip title="仅处理当前两区可见页中，强证据、非冲突、非 SH 且尚未确认的建议。"><InfoCircleOutlined /></Tooltip>
        </Space>
      </div>

      <div className="placement-dual-workbench">
        <ZoneList
          title="纳入贴片 BOM"
          destination="smt"
          groups={smtGroups}
          page={pages.smt}
          activeKey={activeGroup?.key || ""}
          resolutions={resolutions}
          onPage={(page) => setPages((current) => ({ ...current, smt: page }))}
          onSelect={selectGroup}
          onMove={moveGroup}
        />
        <ZoneList
          title="非贴片区"
          destination="non_smt"
          groups={nonSmtGroups}
          page={pages.non_smt}
          activeKey={activeGroup?.key || ""}
          resolutions={resolutions}
          onPage={(page) => setPages((current) => ({ ...current, non_smt: page }))}
          onSelect={selectGroup}
          onMove={moveGroup}
        />
        {screens.lg ? <aside className="placement-evidence-pane">{detail}</aside> : null}
      </div>

      <Collapse
        className="placement-auto-collapse"
        items={[
          {
            key: "auto",
            label: `自动判定项 ${readonlyGroups.length} 组（只读）`,
            children: <Table size="small" rowKey="group_id" dataSource={readonlyGroups} columns={readonlyColumns} pagination={{ pageSize: 8 }} scroll={{ x: 620 }} />,
          },
          {
            key: "nc",
            label: `明确 NC ${readonlyNc.count} 组（只读）`,
            children: <Table size="small" rowKey={(row) => `${row.row_number}-${row.refs.join(",")}`} dataSource={readonlyNc.items} columns={ncColumns} pagination={{ pageSize: 8 }} scroll={{ x: 620 }} />,
          },
          {
            key: "verification",
            label: `编码与描述查验 ${codeVerification.length} 项（只读，不阻断）`,
            children: (
              <>
                <Alert
                  type="info"
                  showIcon
                  message="这些行已按有编码物料纳入。若编码实际是库占位名，请返回 Capture 修正；本清单不会阻止继续处理。"
                />
                <Table
                  size="small"
                  rowKey={(row) => `${row.part_number}-${row.keyword}`}
                  dataSource={codeVerification}
                  columns={verificationColumns}
                  pagination={{ pageSize: 8 }}
                  scroll={{ x: 780 }}
                />
              </>
            ),
          },
        ]}
      />

      <footer className="placement-review-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Space>
          {!ready ? <Typography.Text type="secondary">还有 {groups.length - completed} 组未完成</Typography.Text> : null}
          <Button type="primary" icon={<RightOutlined />} loading={running} disabled={!ready} onClick={onApply}>
            按审查结果继续
          </Button>
        </Space>
      </footer>

      <Drawer title="装机证据与字段" width="min(92vw, 560px)" open={drawerOpen && !screens.lg} onClose={() => setDrawerOpen(false)}>
        {detail}
      </Drawer>
    </section>
  );
}
