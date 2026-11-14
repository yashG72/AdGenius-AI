"""Private file storage for uploaded documents.

`FileStorage` is the interface; `LocalFileStorage` keeps files on local disk for
development. A cloud implementation (S3 / GCS / Azure Blob) can be swapped in at
deployment without touching the rest of the code.

Keys are built by the application (org/brand/document-id.ext), never from user input,
so path traversal ("../../etc/passwd" as a filename) is impossible.
"""

import shutil
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class FileStorage(Protocol):
    def save(self, source: Path, key: str) -> None: ...
    def local_path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...
    def temp_dir(self) -> Path: ...


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # defence in depth
            raise ValueError(f"Storage key escapes the storage root: {key!r}")
        return path

    def save(self, source: Path, key: str) -> None:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)

    def local_path(self, key: str) -> Path:
        return self._resolve(key)

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def temp_dir(self) -> Path:
        """Upload staging area on the same disk (so the final move is cheap)."""
        path = self.root / ".incoming"
        path.mkdir(exist_ok=True)
        return path


@lru_cache
def get_storage() -> FileStorage:
    return LocalFileStorage(get_settings().storage_dir)
