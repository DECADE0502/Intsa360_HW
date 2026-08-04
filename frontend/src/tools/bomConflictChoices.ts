export type SelectVariantChoice = {
  action: "select_variant";
  variant_index: number;
};

export type SplitRefsChoice = {
  action: "split_refs";
  assignments: Array<{ variant_index: number; part_number: string }>;
};

export type MoveNonSmtChoice = {
  action: "move_non_smt";
  variant_indices: number[];
  exclusion_kind: "scope_excluded" | "user_excluded";
};

export type ReturnToCaptureChoice = {
  action: "return_to_capture";
};

export type ConflictChoice =
  | SelectVariantChoice
  | SplitRefsChoice
  | MoveNonSmtChoice
  | ReturnToCaptureChoice;

export type BomConflict = {
  code?: unknown;
  recommended_index?: unknown;
  high_confidence?: unknown;
  variants?: unknown[];
};

function validVariantIndex(value: unknown, count: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value < count;
}

export function normalizeConflictChoice(
  conflict: BomConflict,
  raw: ConflictChoice | number | undefined,
): ConflictChoice | undefined {
  const count = Array.isArray(conflict.variants) ? conflict.variants.length : 0;
  if (validVariantIndex(raw, count)) {
    return { action: "select_variant", variant_index: raw };
  }
  if (!raw || typeof raw !== "object" || !("action" in raw)) return undefined;
  if (raw.action === "select_variant") {
    return validVariantIndex(raw.variant_index, count) ? raw : undefined;
  }
  if (raw.action === "split_refs") {
    const assignments = Array.isArray(raw.assignments) ? raw.assignments : [];
    return {
      action: "split_refs",
      assignments: assignments
        .filter((item) => validVariantIndex(item?.variant_index, count))
        .map((item) => ({ variant_index: item.variant_index, part_number: String(item.part_number || "") })),
    };
  }
  if (raw.action === "move_non_smt") {
    const variant_indices = Array.from(new Set(
      (Array.isArray(raw.variant_indices) ? raw.variant_indices : []).filter((value) => validVariantIndex(value, count)),
    ));
    return {
      action: "move_non_smt",
      variant_indices,
      exclusion_kind: raw.exclusion_kind === "scope_excluded" ? "scope_excluded" : "user_excluded",
    };
  }
  return raw.action === "return_to_capture" ? raw : undefined;
}

export function conflictChoiceComplete(conflict: BomConflict, raw: ConflictChoice | number | undefined): boolean {
  const count = Array.isArray(conflict.variants) ? conflict.variants.length : 0;
  const choice = normalizeConflictChoice(conflict, raw);
  if (!choice || count === 0 || choice.action === "return_to_capture") return false;
  if (choice.action === "select_variant") return true;
  if (choice.action === "move_non_smt") {
    return choice.variant_indices.length > 0 && choice.variant_indices.length >= count - 1;
  }
  const byIndex = new Map(
    choice.assignments.map((item) => [item.variant_index, item.part_number.trim()]),
  );
  if (byIndex.size !== count || [...byIndex.values()].some((code) => !code)) return false;
  return new Set(byIndex.values()).size === count;
}

export function buildRecommendedConflictChoices(
  conflicts: BomConflict[],
  existing: Record<string, ConflictChoice | number> = {},
): Record<string, ConflictChoice> {
  const choices: Record<string, ConflictChoice> = {};
  for (const conflict of conflicts) {
    const code = typeof conflict.code === "string" ? conflict.code.trim() : "";
    const variants = Array.isArray(conflict.variants) ? conflict.variants : [];
    if (!code || variants.length === 0) continue;

    const current = normalizeConflictChoice(conflict, existing[code]);
    if (current) {
      choices[code] = current;
      continue;
    }

    if (conflict.high_confidence === true && validVariantIndex(conflict.recommended_index, variants.length)) {
      choices[code] = { action: "select_variant", variant_index: conflict.recommended_index };
    }
  }
  return choices;
}

export function buildFirstVariantConflictChoices(
  conflicts: BomConflict[],
): Record<string, ConflictChoice> {
  const choices: Record<string, ConflictChoice> = {};
  for (const conflict of conflicts) {
    const code = typeof conflict.code === "string" ? conflict.code.trim() : "";
    const variants = Array.isArray(conflict.variants) ? conflict.variants : [];
    if (!code || variants.length === 0) continue;
    choices[code] = { action: "select_variant", variant_index: 0 };
  }
  return choices;
}
