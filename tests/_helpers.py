"""Reusable test fixture helpers.

Kept intentionally minimal — only helpers that consolidate patterns already
duplicated across two or more test files belong here. Do not add speculative
helpers; extract from real duplication instead.
"""
from __future__ import annotations

from pathlib import Path


def write_netlist(folder: Path, nets: str = "", parts: str = "") -> None:
    """Write a minimal ``pstxnet.dat`` / ``pstxprt.dat`` pair.

    Consolidates the identical helper found in three existing test files
    (``test_cadence_pst_parser``, ``test_netlist_analysis``,
    ``test_netlist_compare_workbench``). New netlist tests should prefer
    this helper; existing tests keep their local copies to minimise churn.
    """
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pstxnet.dat").write_text(nets, encoding="utf-8")
    (folder / "pstxprt.dat").write_text(parts, encoding="utf-8")
