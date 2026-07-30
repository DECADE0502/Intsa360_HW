from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.backend.contracts.smt_analysis import (
    RegistrationConfidence,
    SmtRegistrationValidation,
)


@dataclass(frozen=True)
class RegistrationPolicy:
    """Explicitly calibrated acceptance policy.

    No numeric defaults are supplied. Automatic verification is disabled until
    all project-appropriate thresholds are provided by configuration.
    """

    minimum_anchor_count: int | None = None
    minimum_spatial_coverage: float | None = None
    maximum_median_error: float | None = None
    maximum_p95_error: float | None = None
    minimum_inside_ratio: float | None = None

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.minimum_anchor_count,
                self.minimum_spatial_coverage,
                self.maximum_median_error,
                self.maximum_p95_error,
                self.minimum_inside_ratio,
            )
        )


def classify_validation(
    validation: SmtRegistrationValidation,
    *,
    decision_source: str,
    policy: RegistrationPolicy | None,
    structural_reasons: Iterable[str] = (),
) -> tuple[RegistrationConfidence, list[str]]:
    reasons = list(dict.fromkeys(str(item) for item in structural_reasons if str(item)))
    if reasons:
        return "rejected", reasons

    if decision_source == "user_confirmed":
        return "verified", []

    if policy is None or not policy.complete:
        return "needs_confirmation", [
            "registration_policy_unconfigured",
            "需要用户确认叠加结果；当前没有经过样本校准的自动通过阈值。",
        ]

    assert policy.minimum_anchor_count is not None
    assert policy.minimum_spatial_coverage is not None
    assert policy.maximum_median_error is not None
    assert policy.maximum_p95_error is not None
    assert policy.minimum_inside_ratio is not None
    checks = (
        (validation.anchor_count >= policy.minimum_anchor_count, "anchor_count_below_policy"),
        (
            validation.spatial_coverage is not None
            and validation.spatial_coverage >= policy.minimum_spatial_coverage,
            "spatial_coverage_below_policy",
        ),
        (
            validation.median_error is not None
            and validation.median_error <= policy.maximum_median_error,
            "median_error_above_policy",
        ),
        (
            validation.p95_error is not None
            and validation.p95_error <= policy.maximum_p95_error,
            "p95_error_above_policy",
        ),
        (
            validation.inside_ratio is not None
            and validation.inside_ratio >= policy.minimum_inside_ratio,
            "inside_ratio_below_policy",
        ),
    )
    failed = [code for passed, code in checks if not passed]
    if failed:
        return "rejected", failed
    if validation.mirror_ambiguous:
        return "needs_confirmation", ["mirror_candidate_ambiguous"]
    return "verified", []
