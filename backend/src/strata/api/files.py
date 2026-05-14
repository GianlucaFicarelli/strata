"""Generic file API for Strata.

Every endpoint accepts a ``?backend=<id>`` query parameter.  All storage
logic is delegated to the selected ``StorageBackend`` — this module only
handles HTTP concerns.

Authentication
--------------
All endpoints require a valid bearer token when at least one
``AuthProvider`` is registered (i.e. an auth plugin is loaded).  When no
auth plugin is active the ``current_user`` parameter is ``None`` and
requests proceed unauthenticated — useful for local/dev deployments.

The dependency used here is ``OptionalCurrentUserDep``: it resolves to the
authenticated user when a token is present and valid, or ``None`` when no
token is provided *and* the endpoint allows anonymous access.

To switch to mandatory authentication, replace ``OptionalCurrentUserDep``
with ``CurrentUserDep`` or check ``current_user is None`` inside each
handler and raise 401.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from strata.dependencies.auth import OptionalCurrentUserDep
from strata.dependencies.registry import StorageRegistryDep
from strata.dependencies.storage import StorageBackendDep
from strata.schemas.files import (
    DirectoryCreateResult,
    FileDeleteResult,
    FileEntry,
    FileMoveRequest,
    FileMoveResult,
    FileUploadResult,
)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/list")
async def list_dir(
    path: Annotated[str, Query(description="Directory path to list")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> list[FileEntry]:
    """List the contents of a directory on the selected backend."""
    return await storage.list(path)


@router.get("/download")
async def download_file(
    path: Annotated[str, Query(description="File path to download")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> StreamingResponse:
    """Stream a file from the selected backend as an octet-stream."""
    stream = await storage.read(path)
    filename = path.rstrip("/").split("/")[-1]
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload")
async def upload_file(
    path: Annotated[str, Query(description="Directory to upload into")],
    file: Annotated[UploadFile, File()],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> FileUploadResult:
    """Upload a file to the selected backend."""
    dest = str(Path(path) / (file.filename or "noname"))

    async def _stream() -> AsyncIterator[bytes]:
        while chunk := await file.read(64 * 1024):
            yield chunk

    await storage.write(dest, _stream())
    return FileUploadResult.model_validate(
        {
            "status": "ok",
            "path": dest,
            "backend": storage.id,
        }
    )


@router.delete("/delete")
async def delete_path(
    path: Annotated[str, Query(description="Path to delete")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> FileDeleteResult:
    """Delete a file or directory on the selected backend."""
    await storage.delete(path)
    return FileDeleteResult.model_validate({"status": "ok"})


@router.post("/mkdir")
async def make_dir(
    path: Annotated[str, Query(description="Directory path to create")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> DirectoryCreateResult:
    """Create a directory on the selected backend."""
    await storage.mkdir(path)
    return DirectoryCreateResult.model_validate({"status": "ok"})


@router.post("/move")
async def move_path(
    storage_registry: StorageRegistryDep,
    req: FileMoveRequest,
    current_user: OptionalCurrentUserDep,
) -> FileMoveResult:
    """Move or rename a path on the selected backend."""
    storage = storage_registry.get(req.backend)
    await storage.move(req.src, req.dst)
    return FileMoveResult.model_validate({"status": "ok"})
