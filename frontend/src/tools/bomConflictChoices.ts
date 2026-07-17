export type BomConflict = {
  code?: unknown;
  recommended_index?: unknown;
  variants?: unknown[];
};

export function buildRecommendedConflictChoices(
  conflicts: BomConflict[],
  existing: Record<string, number> = {},
): Record<string, number> {
  const choices: Record<string, number> = {};
  for (const conflict of conflicts) {
    const code = typeof conflict.code === "string" ? conflict.code.trim() : "";
    const variants = Array.isArray(conflict.variants) ? conflict.variants : [];
    if (!code || variants.length === 0) continue;

    const current = existing[code];
    if (Number.isInteger(current) && current >= 0 && current < variants.length) {
      choices[code] = current;
      continue;
    }

    const recommended = conflict.recommended_index;
    choices[code] =
      typeof recommended === "number" &&
      Number.isInteger(recommended) &&
      recommended >= 0 &&
      recommended < variants.length
        ? recommended
        : 0;
  }
  return choices;
}
