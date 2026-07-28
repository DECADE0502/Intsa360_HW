import {
  groupByBusinessOutcome,
  type BusinessResultGroup,
} from "../../utils/businessResultGroups";

export type SmtReviewItem = {
  key: string;
  ref: string;
  status: string;
  kind: string;
  severity?: string;
  part_number?: string;
  net_package?: string;
  bom_package?: string;
  model?: string;
  description?: string;
  name?: string;
  grade?: string;
  note?: string;
  refs?: string[];
};

function smtOutcomeKey(item: SmtReviewItem) {
  return JSON.stringify([
    item.status,
    item.kind,
    item.severity || "",
    item.part_number || "",
    item.net_package || "",
    item.bom_package || "",
    item.model || "",
    item.description || "",
    item.name || "",
    item.grade || "",
    item.note || "",
  ]);
}

export function groupSmtItems(
  items: SmtReviewItem[],
): BusinessResultGroup<SmtReviewItem>[] {
  return groupByBusinessOutcome(
    items,
    smtOutcomeKey,
    (item) => [item.ref, ...(item.refs || [])].filter(Boolean),
  );
}
