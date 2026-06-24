from __future__ import annotations

from pathlib import Path


def run_netlist_compare(root: Path, params: dict[str, object]) -> dict[str, object]:
    from app.backend.tools import analysis_tools

    return analysis_tools.run_netlist_compare(root, params)


def run_smt_package_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    from app.backend.tools import analysis_tools

    return analysis_tools.run_smt_package_check(root, params)


def run_single_network_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    from app.backend.tools import analysis_tools

    return analysis_tools.run_single_network_check(root, params)
