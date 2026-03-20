from __future__ import annotations

from pathlib import Path


class FileWatcher:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._last_mtime_ns: int | None = None
        self._last_size: int | None = None

    def changed(self) -> bool:
        stat = self.path.stat()
        current_mtime_ns = stat.st_mtime_ns
        current_size = stat.st_size

        if self._last_mtime_ns is None or self._last_size is None:
            self._last_mtime_ns = current_mtime_ns
            self._last_size = current_size
            return True

        if current_mtime_ns != self._last_mtime_ns or current_size != self._last_size:
            self._last_mtime_ns = current_mtime_ns
            self._last_size = current_size
            return True

        return False
