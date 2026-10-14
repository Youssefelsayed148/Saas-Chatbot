"""Storage interface for uploaded source files (P2-02, docs/06).

Files are stored under generated, tenant/bot-namespaced names — never the
user-supplied filename — and are never served raw. The interface keeps the
door open for object storage later (ADR-007 is OPEN); the MVP ships a
local-disk implementation.
"""

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID

from app.core.config import Settings

_EXTENSION_BY_KIND = {"pdf": ".pdf", "docx": ".docx", "txt": ".txt", "md": ".md", "qa_csv": ".csv"}


class Storage(ABC):
    """Byte-store for uploaded source files keyed by opaque storage keys."""

    @abstractmethod
    def save(self, tenant_id: UUID, bot_id: UUID, kind: str, data: bytes) -> str:
        """Persist bytes under a generated key and return it."""

    @abstractmethod
    def open(self, storage_key: str) -> bytes:
        """Read the full object (files are ≤10 MB, so a full read is fine)."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Best-effort delete."""


def storage_key_name(tenant_id: UUID, bot_id: UUID, kind: str) -> str:
    """Generated, namespaced key: no user input ever reaches the path."""
    extension = _EXTENSION_BY_KIND[kind]
    return f"{tenant_id}/{bot_id}/{uuid.uuid4().hex}{extension}"


class LocalStorage(Storage):
    """Local-disk implementation rooted at ``settings.storage_root``."""

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.storage_root)

    def _path_for(self, storage_key: str) -> Path:
        # Defence in depth: the key is generated, but refuse anything that
        # would escape the root if it ever contained path operators.
        if ".." in storage_key or storage_key.startswith("/") or "\\" in storage_key:
            raise ValueError("Invalid storage key.")
        return self.root / storage_key

    def save(self, tenant_id: UUID, bot_id: UUID, kind: str, data: bytes) -> str:
        key = storage_key_name(tenant_id, bot_id, kind)
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 0o600: uploaded files may contain client-confidential content.
        # O_BINARY keeps Windows from translating line endings.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return key

    def open(self, storage_key: str) -> bytes:
        return self._path_for(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # Best effort; a stray file never blocks the application.
            pass


_storage: Storage | None = None


def get_storage(settings: Settings | None = None) -> Storage:
    """Resolve the configured storage adapter.

    Request-scoped settings are respected by API routes and tests. The worker
    can omit settings and reuse its process-wide adapter.
    """
    if settings is not None:
        return LocalStorage(settings)
    global _storage
    if _storage is None:
        from app.core.config import get_settings

        _storage = LocalStorage(get_settings())
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Swap the storage implementation (tests)."""
    global _storage
    _storage = storage
