from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def runtime_log_dir(self) -> Path:
        return self.data_dir / "reports" / "runtime"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.inbox_dir,
            self.outputs_dir,
            self.runtime_log_dir,
            self.uploads_dir,
            self.history_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
