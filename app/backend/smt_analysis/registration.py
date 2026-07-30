from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from app.backend.contracts.smt_analysis import (
    RegistrationModel,
    SmtRegistration,
    SmtRegistrationAnchor,
    SmtRegistrationValidation,
)
from app.backend.smt_analysis.registration_validation import (
    RegistrationPolicy,
    classify_validation,
)


Transform = tuple[float, float, float, float, float, float]
Bounds = tuple[float, float, float, float]


class RegistrationError(ValueError):
    pass


@dataclass(frozen=True)
class RegistrationCandidate:
    model: RegistrationModel
    transform: Transform
    median_error: float
    p95_error: float


def apply_transform(transform: Transform, x: float, y: float) -> tuple[float, float]:
    m00, m01, m10, m11, tx, ty = transform
    return (m00 * x + m01 * y + tx, m10 * x + m11 * y + ty)


def _points(anchors: Sequence[SmtRegistrationAnchor]) -> tuple[np.ndarray, np.ndarray]:
    coordinate = np.asarray(
        [(anchor.coordinate_x, anchor.coordinate_y) for anchor in anchors],
        dtype=float,
    )
    image = np.asarray(
        [(anchor.image_x, anchor.image_y) for anchor in anchors],
        dtype=float,
    )
    return coordinate, image


def _validate_anchor_geometry(
    anchors: Sequence[SmtRegistrationAnchor],
    model: RegistrationModel,
) -> None:
    minimum = 3
    if len(anchors) < minimum:
        raise RegistrationError("至少需要三个分散锚点才能建立可审核配准")
    coordinate, image = _points(anchors)
    if len({tuple(point) for point in coordinate.tolist()}) != len(anchors):
        raise RegistrationError("坐标锚点存在重复位置")
    if len({tuple(point) for point in image.tolist()}) != len(anchors):
        raise RegistrationError("图像锚点存在重复位置")
    coordinate_rank = np.linalg.matrix_rank(
        np.column_stack((coordinate, np.ones(len(coordinate))))
    )
    image_rank = np.linalg.matrix_rank(np.column_stack((image, np.ones(len(image)))))
    required_rank = 3
    if coordinate_rank < required_rank or image_rank < required_rank:
        raise RegistrationError("锚点共线或空间分布无效")
    if model == "affine" and len(anchors) < 3:
        raise RegistrationError("仿射配准至少需要三个锚点")


def _solve_matrix(
    anchors: Sequence[SmtRegistrationAnchor],
    model: RegistrationModel,
) -> Transform:
    coordinate, image = _points(anchors)
    rows: list[list[float]] = []
    values: list[float] = []
    if model == "similarity":
        for (x, y), (u, v) in zip(coordinate, image):
            rows.extend(([x, -y, 1.0, 0.0], [y, x, 0.0, 1.0]))
            values.extend((u, v))
        solution, _, rank, _ = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)
        if rank < 4:
            raise RegistrationError("相似变换锚点矩阵秩不足")
        a, b, tx, ty = (float(value) for value in solution)
        transform = (a, -b, b, a, tx, ty)
    elif model == "similarity_with_mirror":
        for (x, y), (u, v) in zip(coordinate, image):
            rows.extend(([x, y, 1.0, 0.0], [-y, x, 0.0, 1.0]))
            values.extend((u, v))
        solution, _, rank, _ = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)
        if rank < 4:
            raise RegistrationError("镜像相似变换锚点矩阵秩不足")
        a, b, tx, ty = (float(value) for value in solution)
        transform = (a, b, b, -a, tx, ty)
    elif model == "affine":
        for (x, y), (u, v) in zip(coordinate, image):
            rows.extend(
                (
                    [x, y, 0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, x, y, 0.0, 1.0],
                )
            )
            values.extend((u, v))
        solution, _, rank, _ = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)
        if rank < 6:
            raise RegistrationError("仿射变换锚点矩阵秩不足")
        a, b, d, e, tx, ty = (float(value) for value in solution)
        transform = (a, b, d, e, tx, ty)
    else:
        raise RegistrationError(f"不支持的配准模型：{model}")
    if not all(math.isfinite(value) for value in transform):
        raise RegistrationError("配准变换包含非有限数值")
    return transform


def _errors(transform: Transform, anchors: Sequence[SmtRegistrationAnchor]) -> np.ndarray:
    values = []
    for anchor in anchors:
        x, y = apply_transform(transform, anchor.coordinate_x, anchor.coordinate_y)
        values.append(math.hypot(x - anchor.image_x, y - anchor.image_y))
    return np.asarray(values, dtype=float)


def _spatial_coverage(
    anchors: Sequence[SmtRegistrationAnchor],
    coordinate_bounds: Bounds | None,
) -> float | None:
    if coordinate_bounds is None:
        return None
    min_x, min_y, max_x, max_y = coordinate_bounds
    denominator = (max_x - min_x) * (max_y - min_y)
    if denominator <= 0:
        return None
    xs = [anchor.coordinate_x for anchor in anchors]
    ys = [anchor.coordinate_y for anchor in anchors]
    area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    return min(1.0, max(0.0, area / denominator))


def _inside_ratio(
    transform: Transform,
    points: Iterable[tuple[float, float]],
    image_bounds: Bounds | None,
) -> float | None:
    if image_bounds is None:
        return None
    values = list(points)
    if not values:
        return None
    min_x, min_y, max_x, max_y = image_bounds
    inside = 0
    for x, y in values:
        image_x, image_y = apply_transform(transform, x, y)
        inside += min_x <= image_x <= max_x and min_y <= image_y <= max_y
    return inside / len(values)


def registration_candidates(
    anchors: Sequence[SmtRegistrationAnchor],
) -> list[RegistrationCandidate]:
    candidates: list[RegistrationCandidate] = []
    for model in ("similarity", "similarity_with_mirror", "affine"):
        typed_model: RegistrationModel = model
        try:
            _validate_anchor_geometry(anchors, typed_model)
            transform = _solve_matrix(anchors, typed_model)
        except RegistrationError:
            continue
        errors = _errors(transform, anchors)
        candidates.append(
            RegistrationCandidate(
                model=typed_model,
                transform=transform,
                median_error=float(np.median(errors)),
                p95_error=float(np.percentile(errors, 95)),
            )
        )
    complexity = {"similarity": 0, "similarity_with_mirror": 0, "affine": 1}
    return sorted(
        candidates,
        key=lambda item: (
            round(item.median_error, 12),
            round(item.p95_error, 12),
            complexity[item.model],
            item.model,
        ),
    )


def solve_registration(
    *,
    coordinate_set_id: str,
    page_id: str,
    side: str,
    model: RegistrationModel,
    anchors: Sequence[SmtRegistrationAnchor],
    coordinate_bounds: Bounds | None = None,
    image_bounds: Bounds | None = None,
    validation_points: Iterable[tuple[float, float]] | None = None,
    decision_source: str = "user_calibrated",
    policy: RegistrationPolicy | None = None,
    runner_up_gap: float | None = None,
    mirror_ambiguous: bool = False,
) -> SmtRegistration:
    if side not in {"top", "bottom"}:
        raise RegistrationError("配准面别必须为 top 或 bottom")
    if decision_source not in {"automatic", "user_confirmed", "user_calibrated"}:
        raise RegistrationError("配准决策来源无效")
    _validate_anchor_geometry(anchors, model)
    transform = _solve_matrix(anchors, model)
    errors = _errors(transform, anchors)
    points = list(validation_points or ((item.coordinate_x, item.coordinate_y) for item in anchors))
    validation = SmtRegistrationValidation(
        anchor_count=len(anchors),
        inlier_ratio=sum(anchor.inlier for anchor in anchors) / len(anchors),
        spatial_coverage=_spatial_coverage(anchors, coordinate_bounds),
        median_error=float(np.median(errors)),
        p95_error=float(np.percentile(errors, 95)),
        inside_ratio=_inside_ratio(transform, points, image_bounds),
        runner_up_gap=runner_up_gap,
        mirror_ambiguous=mirror_ambiguous,
        blocking_reasons=[],
    )
    confidence, reasons = classify_validation(
        validation,
        decision_source=decision_source,
        policy=policy,
    )
    validation = validation.model_copy(update={"blocking_reasons": reasons})
    digest = hashlib.sha256(
        (
            f"{coordinate_set_id}|{page_id}|{side}|{model}|"
            + "|".join(
                f"{anchor.coordinate_x},{anchor.coordinate_y},{anchor.image_x},{anchor.image_y}"
                for anchor in anchors
            )
        ).encode("utf-8")
    ).hexdigest()
    return SmtRegistration(
        registration_id=f"registration-{digest[:24]}",
        coordinate_set_id=coordinate_set_id,
        page_id=page_id,
        side=side,
        model=model,
        transform=transform,
        anchors=list(anchors),
        validation=validation,
        confidence_state=confidence,
        decision_source=decision_source,
    )
