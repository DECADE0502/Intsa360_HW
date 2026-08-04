from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RegistrationAnchor:
    ref: str
    xy_x: float
    xy_y: float
    pdf_x: float
    pdf_y: float


@dataclass(frozen=True)
class AffineRegistration:
    coefficients: tuple[float, float, float, float, float, float]
    anchor_count: int
    rejected_count: int
    median_mm: float
    p90_mm: float
    max_mm: float
    trusted: bool

    def transform(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.coefficients
        return a * x + b * y + c, d * x + e * y + f


def _fit(anchors: list[RegistrationAnchor]) -> tuple[object, object]:
    import numpy as np

    source = np.asarray([[item.xy_x, item.xy_y, 1.0] for item in anchors], dtype=float)
    target = np.asarray([[item.pdf_x, item.pdf_y] for item in anchors], dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(source, target, rcond=None)
    if rank < 3:
        raise ValueError("位号图配准锚点共线，无法确定二维变换。")
    return coefficients, source @ coefficients


def _residuals_mm(
    anchors: list[RegistrationAnchor],
    coefficients: object,
    predicted: object,
) -> object:
    import numpy as np

    linear = coefficients[:2, :].T
    determinant = float(np.linalg.det(linear))
    if abs(determinant) < 1e-12:
        raise ValueError("位号图配准变换不可逆。")
    inverse = np.linalg.inv(linear)
    target = np.asarray([[item.pdf_x, item.pdf_y] for item in anchors], dtype=float)
    delta_mm = (predicted - target) @ inverse.T
    return np.linalg.norm(delta_mm, axis=1)


def fit_affine_registration(
    values: Iterable[RegistrationAnchor],
    *,
    minimum_anchors: int = 20,
    maximum_median_mm: float = 0.5,
) -> AffineRegistration:
    import numpy as np

    anchors = list(values)
    if len(anchors) < minimum_anchors:
        raise ValueError(f"位号图配准锚点不足：{len(anchors)} 个，至少需要 {minimum_anchors} 个。")

    first_coefficients, first_predicted = _fit(anchors)
    first_residuals = _residuals_mm(anchors, first_coefficients, first_predicted)
    first_median = float(np.median(first_residuals))
    threshold = max(1e-6, first_median * 3.0)
    kept = [item for item, residual in zip(anchors, first_residuals) if float(residual) <= threshold]
    if len(kept) < minimum_anchors:
        kept = anchors

    coefficients, predicted = _fit(kept)
    residuals = _residuals_mm(kept, coefficients, predicted)
    median = float(np.median(residuals))
    p90 = float(np.percentile(residuals, 90))
    maximum = float(np.max(residuals))
    packed = (
        float(coefficients[0, 0]),
        float(coefficients[1, 0]),
        float(coefficients[2, 0]),
        float(coefficients[0, 1]),
        float(coefficients[1, 1]),
        float(coefficients[2, 1]),
    )
    return AffineRegistration(
        coefficients=packed,
        anchor_count=len(kept),
        rejected_count=len(anchors) - len(kept),
        median_mm=median,
        p90_mm=p90,
        max_mm=maximum,
        trusted=len(kept) >= minimum_anchors and median <= maximum_median_mm,
    )
