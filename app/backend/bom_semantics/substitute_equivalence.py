from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol, Sequence
import unicodedata

from app.backend.bom_semantics.models import MaterialItem, SubstituteGroup


SUBSTITUTE_CONFIGURATION_FINDING_CODES = frozenset(
    {
        "substitute_strategy_missing",
        "substitute_mode_missing",
    }
)


def _normalized_text(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _quantity(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    return format(normalized, "f")


def _member_rows(item: MaterialItem, field: str) -> tuple[str, ...]:
    values = {
        _normalized_text(getattr(row, field, ""))
        for row in item.source_rows
        if _normalized_text(getattr(row, field, ""))
    }
    return tuple(sorted(values))


def _known_configuration(
    group: SubstituteGroup,
    field: str,
) -> Mapping[str, tuple[str, ...]]:
    return {
        item.material_code: _member_rows(item, field)
        for item in group.members
    }


def _configuration_conflicts(
    old: Mapping[str, tuple[str, ...]],
    new: Mapping[str, tuple[str, ...]],
) -> bool:
    """Unknown values do not assert a change; two known unequal values do."""
    for material_code in set(old) & set(new):
        old_values = old[material_code]
        new_values = new[material_code]
        if old_values and new_values and old_values != new_values:
            return True
    return False


def _member_priorities(group: SubstituteGroup) -> tuple[tuple[str, int | None], ...]:
    return tuple(
        sorted(
            (item.material_code, item.substitute_priority)
            for item in group.members
        )
    )


def _member_quantities(group: SubstituteGroup) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (item.material_code, _quantity(item.quantity))
            for item in group.members
        )
    )


@dataclass(frozen=True)
class SubstituteGroupDelta:
    changed_dimensions: tuple[str, ...]
    old_strategies: Mapping[str, tuple[str, ...]]
    new_strategies: Mapping[str, tuple[str, ...]]
    old_modes: Mapping[str, tuple[str, ...]]
    new_modes: Mapping[str, tuple[str, ...]]

    @property
    def changed(self) -> bool:
        return bool(self.changed_dimensions)

    @property
    def configuration_changed(self) -> bool:
        return bool({"strategies", "modes"} & set(self.changed_dimensions))


def compare_substitute_groups(
    old: SubstituteGroup,
    new: SubstituteGroup,
) -> SubstituteGroupDelta:
    """Compare substitute groups by business meaning, not workbook completeness."""
    dimensions: list[str] = []
    old_main = old.main_item.material_code if old.main_item else ""
    new_main = new.main_item.material_code if new.main_item else ""
    old_members = tuple(sorted(item.material_code for item in old.members))
    new_members = tuple(sorted(item.material_code for item in new.members))

    if old.parent_code != new.parent_code:
        dimensions.append("parent_code")
    if old.group_code != new.group_code:
        dimensions.append("group_code")
    if old_main != new_main:
        dimensions.append("main_material")
    if old_members != new_members:
        dimensions.append("members")
    if _member_priorities(old) != _member_priorities(new):
        dimensions.append("priorities")
    if _member_quantities(old) != _member_quantities(new):
        dimensions.append("quantities")
    if tuple(old.physical_references) != tuple(new.physical_references):
        dimensions.append("references")

    old_strategies = _known_configuration(old, "substitute_strategy")
    new_strategies = _known_configuration(new, "substitute_strategy")
    old_modes = _known_configuration(old, "substitute_mode")
    new_modes = _known_configuration(new, "substitute_mode")
    if _configuration_conflicts(old_strategies, new_strategies):
        dimensions.append("strategies")
    if _configuration_conflicts(old_modes, new_modes):
        dimensions.append("modes")

    return SubstituteGroupDelta(
        changed_dimensions=tuple(dimensions),
        old_strategies=old_strategies,
        new_strategies=new_strategies,
        old_modes=old_modes,
        new_modes=new_modes,
    )


class SubstituteGroupMatch(Protocol):
    old: SubstituteGroup
    new: SubstituteGroup


def structurally_changed_group_keys(
    matches: Sequence[SubstituteGroupMatch],
    unmatched_old: Sequence[SubstituteGroup],
    unmatched_new: Sequence[SubstituteGroup],
) -> set[tuple[str, str]]:
    keys = {
        (group.parent_code, group.group_code)
        for group in (*unmatched_old, *unmatched_new)
    }
    for match in matches:
        old = match.old
        new = match.new
        if compare_substitute_groups(old, new).changed:
            keys.add((old.parent_code, old.group_code))
            keys.add((new.parent_code, new.group_code))
    return keys
