from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


ToolRunner = Callable[[Optional[dict[str, object]]], dict[str, object]]


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    description: str
    status: str
    category: str
    runner: Optional[ToolRunner] = None

    def metadata(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "category": self.category,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.id: tool for tool in tools}

    def list_tools(self) -> list[dict[str, str]]:
        return [tool.metadata() for tool in self._tools.values()]

    def get_tool(self, tool_id: str) -> dict[str, str]:
        if tool_id not in self._tools:
            raise KeyError(tool_id)
        return self._tools[tool_id].metadata()

    def run_tool(self, tool_id: str, params: dict[str, object] | None = None) -> dict[str, object]:
        if tool_id not in self._tools:
            raise KeyError(tool_id)
        tool = self._tools[tool_id]
        if tool.runner is None:
            return {
                "status": "planned",
                "message": f"{tool.name} is registered but not implemented yet.",
                "tool": tool.metadata(),
            }
        return tool.runner(params or {})


def build_registry(root: Path) -> ToolRegistry:
    from app.backend.capabilities import load_capabilities
    from app.backend.tools.analysis_tools import create_analysis_tools

    runners = {tool.id: tool.runner for tool in create_analysis_tools(root)}
    tools: list[Tool] = []
    for item in load_capabilities(root)["capabilities"]:
        if item["type"] != "web_tool":
            continue
        tools.append(
            Tool(
                id=str(item["id"]),
                name=str(item["name"]),
                description=str(item["description"]),
                status=str(item["status"]),
                category=str(item["category"]),
                runner=runners.get(str(item["id"])),
            )
        )
    return ToolRegistry(tools)
