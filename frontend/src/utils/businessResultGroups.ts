const referenceCollator = new Intl.Collator("zh-CN", {
  numeric: true,
  sensitivity: "base",
});

export type BusinessResultGroup<T> = {
  groupKey: string;
  items: T[];
  references: string[];
};

export function naturalReferenceSort(values: Iterable<string>) {
  return Array.from(
    new Set(Array.from(values).filter((value): value is string => Boolean(value))),
  ).sort((left, right) => referenceCollator.compare(left, right));
}

export function groupByBusinessOutcome<T>(
  items: T[],
  outcomeKey: (item: T) => string,
  referencesOf: (item: T) => string[],
): BusinessResultGroup<T>[] {
  const groups = new Map<string, BusinessResultGroup<T>>();
  items.forEach((item) => {
    const groupKey = outcomeKey(item);
    const current = groups.get(groupKey) || {
      groupKey,
      items: [],
      references: [],
    };
    current.items.push(item);
    current.references.push(...referencesOf(item));
    groups.set(groupKey, current);
  });
  return Array.from(groups.values()).map((group) => ({
    ...group,
    references: naturalReferenceSort(group.references),
  }));
}

export function referenceSummary(references: string[], previewCount = 4) {
  if (!references.length) return "无位号";
  if (references.length <= previewCount) return references.join(", ");
  return `${references.slice(0, previewCount).join(", ")} 等 ${references.length} 个`;
}
