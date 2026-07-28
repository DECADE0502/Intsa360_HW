import type {
  SemanticCompare,
  ValidationFinding,
} from "./types";

export type FindingGroup = {
  key: string;
  severity: ValidationFinding["severity"];
  parentCode: string;
  sourceId: string;
  target: string;
  references: string[];
  messages: string[];
  codes: string[];
};

function findingTarget(finding: ValidationFinding) {
  const materialCodes = Array.isArray(finding.details?.material_codes)
    ? finding.details.material_codes.filter((value) => typeof value === "string").join(", ")
    : "";
  return [
    finding.details?.material_code,
    materialCodes,
    finding.details?.group_code,
    finding.details?.main_code,
  ]
    .filter((value) => typeof value === "string" && value)
    .join(" / ");
}

function fallbackFindingKey(finding: ValidationFinding) {
  return [
    finding.parent_code || "全局",
    findingTarget(finding),
    [...(finding.references || [])].sort().join(","),
  ].join("|");
}

export function sourceRecordLabel(sourceId: string) {
  if (!sourceId) return "";
  const parts = sourceId.split(":");
  const row = parts[parts.length - 1];
  const sheet = parts[parts.length - 2];
  if (row && /^\d+$/.test(row) && sheet) {
    return `${sheet} 第 ${row} 行`;
  }
  return sourceId;
}

export function groupFindingsByRecord(rows: ValidationFinding[]): FindingGroup[] {
  const groups = new Map<string, FindingGroup>();
  rows.forEach((finding) => {
    const sourceIds = finding.source_ids?.length
      ? finding.source_ids
      : [""];
    sourceIds.forEach((sourceId) => {
      const key = sourceId ? `source:${sourceId}` : `target:${fallbackFindingKey(finding)}`;
      const current = groups.get(key) || {
        key,
        severity: finding.severity,
        parentCode: finding.parent_code || "全局",
        sourceId,
        target: findingTarget(finding),
        references: [],
        messages: [],
        codes: [],
      };
      if (finding.severity === "blocker") current.severity = "blocker";
      else if (finding.severity === "warning" && current.severity !== "blocker") {
        current.severity = "warning";
      }
      current.references = Array.from(new Set([
        ...current.references,
        ...(finding.references || []),
      ]));
      current.messages = Array.from(new Set([...current.messages, finding.message]));
      current.codes = Array.from(new Set([...current.codes, finding.code]));
      if (!current.target) current.target = findingTarget(finding);
      groups.set(key, current);
    });
  });
  return Array.from(groups.values());
}

export function summarizeCompare(semantic: SemanticCompare) {
  const placement = {
    migrated: semantic.placement_diff.filter((row) => row.status === "migrated").length,
    added: semantic.placement_diff.filter((row) => row.status === "added").length,
    removed: semantic.placement_diff.filter((row) => row.status === "removed").length,
  };
  const substitute = {
    added: semantic.substitute_diff.filter((row) => row.status === "added").length,
    changed: semantic.substitute_diff.filter((row) => row.status === "changed").length,
    removed: semantic.substitute_diff.filter((row) => row.status === "removed").length,
  };
  const metadataEventCount = semantic.summary.metadata_event_count
    ?? semantic.events.filter((event) => event.impact === "metadata").length;
  const reviewEvents = semantic.events.filter((event) => event.impact !== "metadata");
  const reviewEventCount = semantic.summary.review_event_count ?? reviewEvents.length;
  const metadataChangeCount = semantic.summary.metadata_change_count
    ?? semantic.metadata_diff.length + semantic.board_metadata_diff.length;
  const metadataFieldCount = semantic.summary.metadata_field_count
    ?? [...semantic.metadata_diff, ...semantic.board_metadata_diff]
      .reduce((total, row) => total + (row.changed_fields?.length || 0), 0);
  const findingGroups = groupFindingsByRecord([
    ...semantic.blockers,
    ...semantic.warnings,
  ]);
  const blockingRecordCount = semantic.summary.blocking_record_count
    ?? groupFindingsByRecord(semantic.blockers).length;
  return {
    placement,
    substitute,
    metadataEventCount,
    metadataChangeCount,
    metadataFieldCount,
    reviewEvents,
    reviewEventCount,
    findingGroups,
    blockingRecordCount,
    referenceDelta:
      semantic.summary.actual_reference_count_new
      - semantic.summary.actual_reference_count_old,
  };
}
