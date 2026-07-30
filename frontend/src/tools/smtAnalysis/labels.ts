import type {
  SmtAssemblyState,
  SmtPlacementRole,
} from "./types";


export const SMT_STATE_LABELS: Record<SmtAssemblyState, string> = {
  installed: "已装机",
  confirmed_nc: "确认 NC",
  candidate_nc: "候选 NC",
  non_smt: "非 SMT",
  bom_only: "BOM 有 / 坐标无",
  coordinate_only: "坐标有 / BOM 无",
  conflicting: "数据冲突",
  unresolved: "待确认",
};

export const SMT_ROLE_LABELS: Record<SmtPlacementRole, string> = {
  smt_component: "SMT 器件",
  tht_component: "插件器件",
  manual_assembly: "手工装配",
  mechanical: "机械件",
  test_point: "测试点",
  fiducial: "Mark / Fiducial",
  mounting_hole: "安装孔",
  tooling_hole: "工艺孔",
  panel_object: "拼板工艺对象",
  unknown: "角色未确认",
};

export const SMT_EVIDENCE_KIND_LABELS: Record<string, string> = {
  coordinate_membership: "坐标记录",
  bom_membership: "成品 BOM",
  bom_process_decision: "BOM 处理结论",
  netlist_membership: "Cadence 网表",
  drawing_membership: "位号图",
  duplicate_coordinate: "重复坐标",
  role_ref_prefix: "位号角色",
  role_footprint: "封装角色",
  role_explicit: "人工角色",
};
