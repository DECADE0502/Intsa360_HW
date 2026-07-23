from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Mapping, Sequence

from app.backend.bom_semantics.references import natural_reference_key, parse_references


class OAChangeType(str, Enum):
    """OA/ECR form change types derived from semantic change events."""

    ADD = "新增"
    DELETE = "删除"
    REPLACE = "更换(A换成B)"
    SUBSTITUTE = "替代(AB共存)"
    QUANTITY_REFERENCE_MODIFIED = "数量(位号)修改"


@dataclass(frozen=True)
class OAChangeRow:
    """One logical OA form row, independent of a particular workbook template."""

    side: str
    parent_code: str
    material_code: str
    quantity: Decimal | None
    references: tuple[str, ...]
    substitute_group_code: str = ""
    substitute_priority: int | None = None
    name: str = ""
    model: str = ""
    description: str = ""
    unit: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "side": self.side,
            "parent_code": self.parent_code,
            "material_code": self.material_code,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "references": list(self.references),
            "substitute_group_code": self.substitute_group_code,
            "substitute_priority": self.substitute_priority,
            "name": self.name,
            "model": self.model,
            "description": self.description,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class OAChangeItem:
    """A single OA/ECR change item, containing one or two form rows."""

    change_id: str
    event_id: str
    change_type: OAChangeType
    parent_code: str
    title: str
    rows: tuple[OAChangeRow, ...]
    substitute_group_code: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "change_id": self.change_id,
            "event_id": self.event_id,
            "change_type": self.change_type.value,
            "parent_code": self.parent_code,
            "title": self.title,
            "rows": [row.payload() for row in self.rows],
            "substitute_group_code": self.substitute_group_code,
        }


@dataclass(frozen=True)
class OAExportIssue:
    """A semantic export gate; callers must not silently drop malformed changes."""

    code: str
    message: str
    event_id: str = ""
    parent_code: str = ""
    group_code: str = ""
    details: Mapping[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "event_id": self.event_id,
            "parent_code": self.parent_code,
            "group_code": self.group_code,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class OAExportResult:
    """Template-neutral OA/ECR payload for a later workbook adapter."""

    change_items: tuple[OAChangeItem, ...]
    issues: tuple[OAExportIssue, ...] = ()

    @property
    def rows(self) -> tuple[OAChangeRow, ...]:
        return tuple(row for item in self.change_items for row in item.rows)

    @property
    def can_export(self) -> bool:
        return not self.issues

    def payload(self) -> dict[str, object]:
        return {
            "change_items": [item.payload() for item in self.change_items],
            "issues": [issue.payload() for issue in self.issues],
            "can_export": self.can_export,
        }


@dataclass(frozen=True)
class _ItemView:
    parent_code: str
    material_code: str
    quantity: Decimal | None
    references: tuple[str, ...]
    substitute_group_code: str = ""
    substitute_priority: int | None = None
    name: str = ""
    model: str = ""
    description: str = ""
    unit: str = ""


def _read(value: object, *names: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]
        return default
    for name in names:
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return default


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal(value: object) -> Decimal | None:
    if value is None or _text(value) == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _priority(value: object) -> int | None:
    if value is None or _text(value) == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _references(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return parse_references(value).references
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        normalized: set[str] = set()
        for member in value:
            normalized.update(parse_references(member).references)
        return tuple(sorted(normalized, key=natural_reference_key))
    return parse_references(value).references


def _first_variant(value: object) -> object | None:
    variants = _read(value, "variants", default=())
    if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes, bytearray)):
        return variants[0] if variants else None
    return None


def _snapshot_item(value: object, parent_code: str = "") -> _ItemView | None:
    if value is None:
        return None
    nested = _read(value, "item", "material", "material_item", "record")
    if nested is not None and nested is not value:
        candidate = _snapshot_item(nested, parent_code)
        if candidate is not None:
            return candidate

    material_code = _text(
        _read(value, "material_code", "part_number", "child_code", "sub_item_code", "code")
    )
    if not material_code:
        return None
    variant = _first_variant(value)
    return _ItemView(
        parent_code=_text(_read(value, "parent_code", "parent", default=parent_code)) or parent_code,
        material_code=material_code,
        quantity=_decimal(_read(value, "quantity", "qty", "amount")),
        references=_references(_read(value, "references", "reference", "refdes", "designators")),
        substitute_group_code=_text(_read(value, "substitute_group_code", "group_code", "substitute_group")),
        substitute_priority=_priority(_read(value, "substitute_priority", "priority")),
        name=_text(_read(value, "name", default=_read(variant, "name"))),
        model=_text(_read(value, "model", "mpn", default=_read(variant, "model"))),
        description=_text(_read(value, "description", "material_description", default=_read(variant, "description"))),
        unit=_text(_read(value, "unit", default=_read(variant, "unit"))),
    )


def _row(item: _ItemView, side: str, *, group_code: str = "", references: tuple[str, ...] | None = None) -> OAChangeRow:
    return OAChangeRow(
        side=side,
        parent_code=item.parent_code,
        material_code=item.material_code,
        quantity=item.quantity,
        references=item.references if references is None else references,
        substitute_group_code=group_code or item.substitute_group_code,
        substitute_priority=item.substitute_priority,
        name=item.name,
        model=item.model,
        description=item.description,
        unit=item.unit,
    )


def _event_id(event: object, index: int) -> str:
    return _text(_read(event, "event_id", "id")) or f"event-{index + 1}"


def _event_parent(event: object) -> str:
    return _text(_read(event, "parent_code", "parent"))


def _event_title(event: object) -> str:
    return _text(_read(event, "title", "name"))


def _event_snapshot(event: object, side: str) -> object:
    return _read(event, f"{side}_snapshot", side, f"{side}_item")


def _normalized_kind(event: object) -> str:
    explicit = _read(event, "oa_change_type")
    raw = explicit if explicit not in (None, "") else _read(event, "kind", "change_kind", "type")
    return _text(_read(raw, "value", default=raw)).casefold()


def _change_type(event: object) -> OAChangeType | None:
    kind = _normalized_kind(event)
    if kind in {"新增", "add", "added", "material_added"}:
        return OAChangeType.ADD
    if kind in {"删除", "delete", "deleted", "material_removed", "alternative_removed"}:
        return OAChangeType.DELETE
    if kind in {"更换", "更换(a换成b)", "replace", "replacement"}:
        return OAChangeType.REPLACE
    if kind in {
        "替代",
        "替代(ab共存)",
        "substitute",
        "alternative_added",
        "substitute_priority_only",
        "substitute_configuration_changed",
        "main_changed_refs_migrated",
    }:
        return OAChangeType.SUBSTITUTE
    if kind in {
        "数量(位号)修改",
        "quantity_reference_modified",
        "quantity_changed",
        "reference_added",
        "reference_removed",
        "reference_migrated",
        "reference_set_changed",
    }:
        return OAChangeType.QUANTITY_REFERENCE_MODIFIED
    return None


def _group_key(group: object, parent_code: str = "") -> tuple[str, str]:
    return (
        _text(_read(group, "parent_code", "parent", default=parent_code)) or parent_code,
        _text(_read(group, "group_code", "substitute_group_code")),
    )


def _as_object_sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return (value,)


def _groups_from_snapshot(snapshot: object) -> tuple[object, ...]:
    if snapshot is None:
        return ()
    if _read(snapshot, "main_item", "alternative_items") is not None:
        return (snapshot,)
    groups: list[object] = []
    for name in ("substitute_group", "group", "substitute_groups", "groups"):
        groups.extend(_as_object_sequence(_read(snapshot, name)))
    return tuple(groups)


def _event_group_codes(event: object) -> tuple[str, ...]:
    value = _read(event, "group_codes", "substitute_group_codes")
    if value is None:
        value = _read(_event_snapshot(event, "new"), "group_code", "substitute_group_code")
    if value is None:
        value = _read(_event_snapshot(event, "old"), "group_code", "substitute_group_code")
    return tuple(code for code in (_text(item) for item in _as_object_sequence(value)) if code)


def _groups_for_event(event: object, indexed_groups: Mapping[tuple[str, str], object]) -> tuple[object, ...]:
    parent_code = _event_parent(event)
    groups: list[object] = []
    for snapshot in (_event_snapshot(event, "new"), _event_snapshot(event, "old")):
        groups.extend(_groups_from_snapshot(snapshot))
    for group_code in _event_group_codes(event):
        group = indexed_groups.get((parent_code, group_code))
        if group is not None:
            groups.append(group)
    unique: dict[tuple[str, str], object] = {}
    for group in groups:
        key = _group_key(group, parent_code)
        if key[1]:
            unique[key] = group
    return tuple(unique[key] for key in sorted(unique))


def _expand_substitute_group(
    group: object,
    *,
    event_id: str,
    title: str = "",
) -> tuple[tuple[OAChangeItem, ...], tuple[OAExportIssue, ...]]:
    parent_code, declared_group_code = _group_key(group)
    main = _snapshot_item(_read(group, "main_item"), parent_code)
    alternatives = tuple(
        item
        for item in (
            _snapshot_item(candidate, parent_code)
            for candidate in _as_object_sequence(_read(group, "alternative_items", "alternatives"))
        )
        if item is not None
    )
    if main is None:
        return (), (
            OAExportIssue(
                code="substitute_main_missing",
                message="Substitute group has no unique main material for OA export.",
                event_id=event_id,
                parent_code=parent_code,
                group_code=declared_group_code,
            ),
        )
    if not alternatives:
        return (), (
            OAExportIssue(
                code="substitute_alternative_missing",
                message="Substitute group has no alternative material for OA export.",
                event_id=event_id,
                parent_code=parent_code,
                group_code=declared_group_code,
            ),
        )
    if declared_group_code and declared_group_code != main.material_code:
        return (), (
            OAExportIssue(
                code="substitute_group_code_not_main",
                message="Substitute group code must equal the priority-0 main material code.",
                event_id=event_id,
                parent_code=parent_code,
                group_code=declared_group_code,
                details={"main_material_code": main.material_code},
            ),
        )

    invalid_alternatives = tuple(
        alternative
        for alternative in alternatives
        if alternative.references
    )
    if invalid_alternatives:
        return (), (
            OAExportIssue(
                code="substitute_alternative_has_references",
                message="Alternative materials must not own physical references in an OA substitute pair.",
                event_id=event_id,
                parent_code=parent_code,
                group_code=declared_group_code,
                details={
                    "material_codes": [alternative.material_code for alternative in invalid_alternatives],
                    "references": {
                        alternative.material_code: list(alternative.references)
                        for alternative in invalid_alternatives
                    },
                },
            ),
        )
    inconsistent_quantities = tuple(
        alternative
        for alternative in alternatives
        if main.quantity is not None
        and alternative.quantity is not None
        and alternative.quantity != main.quantity
    )
    if inconsistent_quantities:
        return (), (
            OAExportIssue(
                code="substitute_quantity_mismatch",
                message="All members of an OA substitute group must use the main material quantity.",
                event_id=event_id,
                parent_code=parent_code,
                group_code=declared_group_code,
                details={
                    "main_quantity": str(main.quantity),
                    "material_codes": [alternative.material_code for alternative in inconsistent_quantities],
                },
            ),
        )

    group_code = main.material_code
    physical_references = _references(_read(group, "physical_references")) or main.references
    main = _ItemView(
        parent_code=main.parent_code or parent_code,
        material_code=main.material_code,
        quantity=main.quantity,
        references=physical_references,
        substitute_group_code=group_code,
        substitute_priority=0,
        name=main.name,
        model=main.model,
        description=main.description,
        unit=main.unit,
    )
    ordered_alternatives = tuple(
        sorted(
            alternatives,
            key=lambda item: (
                item.substitute_priority if item.substitute_priority is not None else 10**9,
                item.material_code,
            ),
        )
    )
    items = tuple(
        OAChangeItem(
            change_id=f"{event_id}:substitute:{group_code}:{index}",
            event_id=event_id,
            change_type=OAChangeType.SUBSTITUTE,
            parent_code=main.parent_code,
            title=title or "Substitute relation",
            rows=(
                _row(main, "before", group_code=group_code, references=physical_references),
                _row(alternative, "after", group_code=group_code, references=()),
            ),
            substitute_group_code=group_code,
        )
        for index, alternative in enumerate(ordered_alternatives, start=1)
    )
    return items, ()


def expand_substitute_group(group: object, *, event_id: str = "substitute") -> tuple[OAChangeItem, ...]:
    """Expand a semantic substitute group into one OA item per main/alternative pair.

    A three-member group becomes exactly two two-row OA items.  Invalid groups return
    no items; callers that need diagnostics should use :func:`build_oa_ecr_export`.
    """

    items, _ = _expand_substitute_group(group, event_id=event_id)
    return items


def _single_event_item(
    event: object,
    index: int,
    change_type: OAChangeType,
) -> tuple[OAChangeItem | None, OAExportIssue | None]:
    event_id = _event_id(event, index)
    parent_code = _event_parent(event)
    title = _event_title(event)
    old_item = _snapshot_item(_event_snapshot(event, "old"), parent_code)
    new_item = _snapshot_item(_event_snapshot(event, "new"), parent_code)

    if change_type == OAChangeType.ADD:
        rows = (_row(new_item, "after"),) if new_item else ()
    elif change_type == OAChangeType.DELETE:
        rows = (_row(old_item, "before"),) if old_item else ()
    else:
        rows = tuple(
            row
            for row in (
                _row(old_item, "before") if old_item else None,
                _row(new_item, "after") if new_item else None,
            )
            if row is not None
        )

    if not rows:
        return None, OAExportIssue(
            code="event_snapshot_missing",
            message="OA/ECR change event does not contain the required material snapshot.",
            event_id=event_id,
            parent_code=parent_code,
            details={"change_type": change_type.value},
        )
    resolved_parent = parent_code or rows[0].parent_code
    return OAChangeItem(
        change_id=f"{event_id}:{change_type.name.casefold()}",
        event_id=event_id,
        change_type=change_type,
        parent_code=resolved_parent,
        title=title or change_type.value,
        rows=rows,
    ), None


def build_oa_ecr_export(
    events: Iterable[object],
    *,
    substitute_groups: Iterable[object] = (),
) -> OAExportResult:
    """Convert semantic events and groups into template-neutral OA/ECR change items.

    Inputs intentionally use duck typing so the exporter can be developed before the
    diff engine is finalized.  It accepts model dataclasses or the corresponding
    payload dictionaries.  No project-specific material-prefix policy is inferred.
    """

    indexed_groups = {
        _group_key(group): group
        for group in substitute_groups
        if _group_key(group)[1]
    }
    change_items: list[OAChangeItem] = []
    issues: list[OAExportIssue] = []
    for index, event in enumerate(events):
        event_id = _event_id(event, index)
        change_type = _change_type(event)
        if change_type is None:
            issues.append(
                OAExportIssue(
                    code="event_not_exportable",
                    message="Semantic event has no supported OA/ECR change type.",
                    event_id=event_id,
                    parent_code=_event_parent(event),
                    details={"kind": _normalized_kind(event)},
                )
            )
            continue
        if change_type == OAChangeType.SUBSTITUTE:
            groups = _groups_for_event(event, indexed_groups)
            if not groups:
                issues.append(
                    OAExportIssue(
                        code="substitute_group_missing",
                        message="Substitute event does not resolve to a semantic substitute group.",
                        event_id=event_id,
                        parent_code=_event_parent(event),
                    )
                )
                continue
            for group in groups:
                items, group_issues = _expand_substitute_group(
                    group,
                    event_id=event_id,
                    title=_event_title(event),
                )
                change_items.extend(items)
                issues.extend(group_issues)
            continue
        item, issue = _single_event_item(event, index, change_type)
        if item is not None:
            change_items.append(item)
        if issue is not None:
            issues.append(issue)
    return OAExportResult(change_items=tuple(change_items), issues=tuple(issues))


def export_oa_ecr(
    events: Iterable[object],
    *,
    substitute_groups: Iterable[object] = (),
) -> OAExportResult:
    """Alias kept for callers that use export-oriented naming."""

    return build_oa_ecr_export(events, substitute_groups=substitute_groups)
