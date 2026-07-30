from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from app.backend.contracts.smt_analysis import SmtCoordinateSet


@dataclass(frozen=True)
class CoordinateProbe:
    adapter_id: str
    confidence: int
    reasons: tuple[str, ...]
    sheet_or_section: str = ""

    def __post_init__(self) -> None:
        if self.confidence < 0 or self.confidence > 100:
            raise ValueError("coordinate probe confidence must be between 0 and 100")


class CoordinateAdapter(Protocol):
    adapter_id: str

    def probe(self, path: Path) -> list[CoordinateProbe]:
        ...

    def parse(self, path: Path, probe: CoordinateProbe) -> SmtCoordinateSet:
        ...


class CoordinateAdapterRegistry:
    def __init__(self, adapters: Sequence[CoordinateAdapter]) -> None:
        identifiers = [adapter.adapter_id for adapter in adapters]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("coordinate adapter identifiers must be unique")
        self._adapters = tuple(adapters)

    def probes(self, path: Path) -> list[CoordinateProbe]:
        results = [
            probe
            for adapter in self._adapters
            for probe in adapter.probe(Path(path))
            if probe.confidence > 0
        ]
        return sorted(
            results,
            key=lambda item: (-item.confidence, item.adapter_id, item.sheet_or_section),
        )

    def parse(self, path: Path, probe: CoordinateProbe) -> SmtCoordinateSet:
        for adapter in self._adapters:
            if adapter.adapter_id == probe.adapter_id:
                return adapter.parse(Path(path), probe)
        raise KeyError(f"coordinate adapter not found: {probe.adapter_id}")

    def parse_best(self, path: Path, *, minimum_confidence: int = 70) -> SmtCoordinateSet:
        probes = self.probes(path)
        if not probes or probes[0].confidence < minimum_confidence:
            raise ValueError("未找到可信的坐标数据格式，请确认文件和字段映射")
        if len(probes) > 1 and probes[0].confidence == probes[1].confidence:
            raise ValueError("发现多个同等可信的坐标数据候选，请先选择工作表或格式")
        return self.parse(path, probes[0])
