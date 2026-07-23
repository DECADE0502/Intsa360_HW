from __future__ import annotations

from app.backend.bom_semantics.references import parse_references


def test_references_support_chinese_separators_and_natural_order() -> None:
    result = parse_references("C10，C2; C1\nC2")
    assert result.references == ("C1", "C2", "C10")
    assert result.flags == ()


def test_only_exact_60_is_an_empty_placeholder() -> None:
    assert parse_references("60").references == ()
    assert parse_references("R60").references == ("R60",)


def test_other_numeric_reference_requires_resolution() -> None:
    unresolved = parse_references("72")
    assert unresolved.references == ("72",)
    assert unresolved.flags == ("numeric_reference_suspected",)
    assert parse_references("72", "empty").references == ()
    assert parse_references("72", "keep").references == ("72",)
