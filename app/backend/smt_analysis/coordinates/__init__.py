from .base import CoordinateAdapterRegistry, CoordinateProbe
from .cadence_xy import CadenceXYAdapter
from .tabular import TabularCoordinateAdapter


def default_coordinate_registry() -> CoordinateAdapterRegistry:
    return CoordinateAdapterRegistry(
        [
            CadenceXYAdapter(),
            TabularCoordinateAdapter(),
        ]
    )


__all__ = [
    "CadenceXYAdapter",
    "CoordinateAdapterRegistry",
    "CoordinateProbe",
    "TabularCoordinateAdapter",
    "default_coordinate_registry",
]
