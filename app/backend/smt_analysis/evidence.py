from __future__ import annotations

from app.backend.contracts.smt_analysis import SmtEvidence


def evidence(
    kind: str,
    message: str,
    *,
    weight: str,
    source_id: str | None = None,
    source_location: str | None = None,
    value: str | None = None,
) -> SmtEvidence:
    return SmtEvidence(
        kind=kind,
        source_id=source_id,
        source_location=source_location,
        value=value,
        weight=weight,
        message=message,
    )
