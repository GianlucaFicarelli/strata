"""Generic file API for Strata.

Every endpoint accepts a ``?backend=<id>`` query parameter.  All storage
logic is delegated to the selected ``StorageBackend`` — this module only
handles HTTP concerns.

The ``move`` endpoint is the sole exception: it accepts ``backend`` in the
request body (alongside ``src`` and ``dst``) and resolves the backend itself
so the schema stays consistent with the frontend expectation.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from strata.dependencies.auth import OptionalCurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageRegistryDep, StorageTemplateRegistryDep
from strata.dependencies.storage import StorageBackendDep
from strata.schemas.files import (
    DirectoryCreateResult,
    FileDeleteResult,
    FileEntry,
    FileMoveRequest,
    FileMoveResult,
    FileUploadResult,
)
from strata.storage import service as storage_service

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
    return FileUploadResult(status="ok", path=dest, backend=storage.id)


@router.delete("/delete")
async def delete_path(
    path: Annotated[str, Query(description="Path to delete")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> FileDeleteResult:
    """Delete a file or directory on the selected backend."""
    await storage.delete(path)
    return FileDeleteResult(status="ok")


@router.post("/mkdir")
async def make_dir(
    path: Annotated[str, Query(description="Directory path to create")],
    storage: StorageBackendDep,
    current_user: OptionalCurrentUserDep,
) -> DirectoryCreateResult:
    """Create a directory on the selected backend."""
    await storage.mkdir(path)
    return DirectoryCreateResult(status="ok")


@router.post("/move")
async def move_path(
    req: FileMoveRequest,
    current_user: OptionalCurrentUserDep,
    session: AsyncSessionDep,
    storage_registry: StorageRegistryDep,
    template_registry: StorageTemplateRegistryDep,
) -> FileMoveResult:
    """Move or rename a path on the selected backend.

    The backend is resolved from ``req.backend`` with the same two-step
    logic as ``StorageBackendDep`` (static registry first, then instance lookup).
    """
    # Static registry first
    if storage_registry._backends.get(req.backend):
        backend = storage_registry.get(backend_id=req.backend)
    else:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access storage instances",
            )
        backend = await storage_service.resolve_backend_for_user(
            session,
            instance_id=req.backend,
            user_id=current_user.id,
            username=current_user.username,
            template_registry=template_registry,
        )
        if backend is None:
            raise HTTPException(
                status_code=400,
                detail=f"Backend {req.backend!r} not found or not available for this user",
            )
    await backend.move(req.src, req.dst)
    return FileMoveResult(status="ok")
