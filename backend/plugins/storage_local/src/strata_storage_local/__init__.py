"""Local filesystem storage backend plugin for Strata.

Registers both a raw :class:`~strata.plugins.protocols.StorageBackend`
(for simple deployments using ``STRATA_LOCAL_ROOT``) and a
:class:`~strata.plugins.protocols.StorageTemplate` (for admin-configured
instances with per-user path expansion).

Entry point::

    [project.entry-points."strata.plugins"]
    storage_local = "strata_storage_local:plugin"
"""

import mimetypes
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import HTTPException
from pydantic import BaseModel, Field

from strata.config import settings
from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import InstanceContext, StorageBackend
from strata.plugins.registry import PluginRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry

_CHUNK: int = 64 * 1024


# ── Config schema ─────────────────────────────────────────────────────────────


class LocalStorageConfig(BaseModel):
    """Admin-level configuration for a local filesystem instance.

    Attributes:
        root: Absolute path on the server exposed to users.  Supports
            ``{username}`` and ``{user_id}`` placeholders which are expanded
            per-request from the authenticated user's identity.
        instance_name: Display label shown in the backend picker.
    """

    root: Annotated[
        str,
        Field(
            default="/home/{username}",
            description="Root path exposed to the user. Supports {username} and {user_id}.",
            json_schema_extra={"template": True},
        ),
    ]


# ── Shared backend implementation ─────────────────────────────────────────────


def _make_safe_resolver(root: Path):  # type: ignore[no-untyped-def]
    """Return a path resolver that rejects traversal outside *root*."""

    def _safe(rel: str) -> Path:
        target = (root / rel.lstrip("/")).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status_code=403, detail="Path escapes storage root")
        return target

    return _safe


def _to_entry(p: Path, root: Path) -> FileEntry:
    stat = p.stat()
    mime: str | None = None
    if p.is_file():
        mime, _ = mimetypes.guess_type(p.name)
    return FileEntry(
        name=p.name,
        path="/" + str(p.relative_to(root)),
        is_dir=p.is_dir(),
        size=stat.st_size if p.is_file() else None,
        modified=stat.st_mtime,
        mime=mime,
    )


class _LocalBackend:
    """Shared implementation for both singleton and instance-backed local backends."""

    def __init__(self, backend_id: str, backend_name: str, root: Path) -> None:
        self.id = backend_id
        self.name = backend_name
        self._root = root
        self._safe = _make_safe_resolver(root)

    async def list(self, path: str) -> list[FileEntry]:
        target = self._safe(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail="Not a directory")
        entries: list[FileEntry] = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                entries.append(_to_entry(child, self._root))
            except PermissionError:
                pass
        return entries

    async def read(self, path: str) -> AsyncIterator[bytes]:
        target = self._safe(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        async def _gen() -> AsyncIterator[bytes]:
            async with aiofiles.open(target, "rb") as fh:
                while chunk := await fh.read(_CHUNK):
                    yield chunk

        return _gen()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        target = self._safe(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as fh:
            async for chunk in stream:
                await fh.write(chunk)

    async def delete(self, path: str) -> None:
        target = self._safe(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Not found")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    async def mkdir(self, path: str) -> None:
        self._safe(path).mkdir(parents=True, exist_ok=True)

    async def move(self, src: str, dst: str) -> None:
        shutil.move(str(self._safe(src)), str(self._safe(dst)))

    def describe(self) -> StorageMeta:
        return StorageMeta(id=self.id, name=self.name)


# ── Singleton backend (env-var configured) ────────────────────────────────────


class LocalStorageBackend(_LocalBackend):
    """Singleton local filesystem backend using STRATA_LOCAL_ROOT."""

    def __init__(self) -> None:
        root = Path(str(settings.LOCAL_ROOT)).resolve()
        super().__init__("storage_local", "Local Filesystem", root)


# ── StorageTemplate ───────────────────────────────────────────────────────────


class LocalStorageTemplate:
    """Template for admin-configured local filesystem instances.

    The admin sets a ``root`` path (possibly with ``{username}`` placeholder).
    At request time the core expands the placeholder and constructs a backend
    scoped to that resolved path.

    Implements :class:`~strata.plugins.protocols.StorageTemplate`.
    """

    plugin_id: str = "storage_local"
    display_name: str = "Local Filesystem"
    description: str = (
        "Exposes a local directory as a storage backend. "
        "The root path supports {username} and {user_id} placeholders."
    )
    config_schema: type[BaseModel] = LocalStorageConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        assert isinstance(config, LocalStorageConfig)
        # Template expansion already done by the service layer before calling create().
        root = Path(config.root).resolve()
        # Use instance_id from context is not available here; use a stable id
        # based on the resolved root so the backend id is deterministic.
        backend_id = f"local:{root}"
        return _LocalBackend(
            backend_id=backend_id,
            backend_name=f"Local ({root})",
            root=root,
        )


# ── Plugin ────────────────────────────────────────────────────────────────────


class LocalStoragePlugin(BackendPlugin):
    """Registers the local filesystem backend and template."""

    id = "storage_local"
    name = "Local Storage"
    version = "0.1.0"
    description = "Exposes the local filesystem as a storage backend."

    def register(self, registry: PluginRegistry) -> None:
        registry.storage.add(LocalStorageBackend())
        registry.storage_templates.add(LocalStorageTemplate())


plugin = LocalStoragePlugin()
