from __future__ import annotations

import importlib.util
from pathlib import Path

from app.backend.tool_registry import Tool


def _load_converter(root: Path):
    path = root / "tools" / "bom" / "convert_iac4_bom.py"
    spec = importlib.util.spec_from_file_location("convert_iac4_bom", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_bom_import_tool(root: Path) -> Tool:
    def run(params: dict[str, object] | None = None) -> dict[str, object]:
        params = params or {}
        if params.get("source_bom"):
            from app.backend.tools.analysis_tools import run_generic_bom_import

            result = run_generic_bom_import(root, params)
            result["next_step"] = "完整 BOM 输出后，继续走 OA YF25 备料，并在对应 PCBA 下上传处理好的 BOM。"
            return result
        converter = _load_converter(root)
        result = converter.run_conversion()
        return {
            "status": "ok",
            "tool": "bom_import",
            "result": result,
            "next_step": "完整 BOM 输出后，继续走 OA YF25 备料，并在对应 PCBA 下上传处理好的 BOM。",
        }

    return Tool(
        id="bom_import",
        name="BOM 导入处理",
        description="将原始 BOM 转换为可导入主 BOM，并生成 NC/未贴器件汇总。",
        status="available",
        category="BOM",
        runner=run,
    )
