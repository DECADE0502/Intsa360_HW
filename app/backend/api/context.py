from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Request

from app.backend.paths import AppPaths
from app.backend.tool_registry import ToolRegistry, build_registry


@dataclass
class AppContext:
    root: Path
    paths: AppPaths
    _registry: ToolRegistry | None = None
    _registry_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def registry(self) -> ToolRegistry:
        if self._registry is None:
            with self._registry_lock:
                if self._registry is None:
                    self._registry = build_registry(self.root)
        return self._registry


def build_context(root: Path) -> AppContext:
    runtime_root = Path(os.path.abspath(root))
    paths = AppPaths(runtime_root)
    return AppContext(root=runtime_root, paths=paths)


def get_context(request: Request) -> AppContext:
    context = getattr(request.app.state, "context", None)
    if not isinstance(context, AppContext):
        raise RuntimeError("FastAPI application context is unavailable")
    return context
