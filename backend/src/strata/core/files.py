"""Generic file API for Strata.

Every endpoint accepts a ``?backend=<id>`` query parameter (default:
``"local"``).  All storage logic is delegated to the selected
``StorageBackend`` — this module only handles HTTP concerns.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from strata.core.storage import FileEntry, StorageBackend, backend_dep, get

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/api/files", tags=["files"])


class MoveRequest(BaseModel):
    """Request body for the move / rename endpoint.

    Attributes:
        src: Backend-relative source path.
        dst: Backend-relative destination path.
        backend: ID of the storage backend that owns both paths.

    """

    src: str
    dst: str
    backend: str = "local"


# ── Read operations ───────────────────────────────────────────────────────────


@router.get("/list", response_model=list[FileEntry])
async def list_dir(
    path: Annotated[str, Query(description="Directory path to list")],
    storage: Annotated[StorageBackend, Depends(backend_dep)],
) -> list[FileEntry]:
    """List the contents of a directory on the selected backend.

    Args:
        path: Backend-relative directory path.
        storage: Resolved storage backend (injected by ``backend_dep``).

    Returns:
        A list of ``FileEntry`` objects.

    """
    return await storage.list(path)


@router.get("/download")
async def download_file(
    path: Annotated[str, Query(description="File path to download")],
    storage: Annotated[StorageBackend, Depends(backend_dep)],
) -> StreamingResponse:
    """Stream a file from the selected backend as an octet-stream.

    Args:
        path: Backend-relative file path.
        storage: Resolved storage backend.

    Returns:
        A ``StreamingResponse`` with ``Content-Disposition: attachment``.

    """
    stream = await storage.read(path)
    filename = path.rstrip("/").split("/")[-1]
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Write operations ──────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_file(
    path: Annotated[str, Query(description="Directory to upload into")],
    file: Annotated[UploadFile, File()],
    storage: Annotated[StorageBackend, Depends(backend_dep)],
) -> dict:
    """Upload a file to the selected backend.

    Args:
        path: Backend-relative target directory.
        file: The uploaded file provided as multipart form data.
        storage: Resolved storage backend.

    Returns:
        A dict with ``status``, ``path``, and ``backend`` keys.

    """
    dest = str(Path(path) / (file.filename or "noname"))

    async def _stream() -> AsyncIterator[bytes]:
        while chunk := await file.read(64 * 1024):
            yield chunk

    await storage.write(dest, _stream())
    return {"status": "ok", "path": dest, "backend": storage.id}


@router.delete("/delete")
async def delete_path(
    path: Annotated[str, Query(description="Path to delete")],
    storage: Annotated[StorageBackend, Depends(backend_dep)],
) -> dict:
    """Delete a file or directory on the selected backend.

    Args:
        path: Backend-relative path to remove.
        storage: Resolved storage backend.

    Returns:
        A dict with a ``"status": "ok"`` key.

    """
    await storage.delete(path)
    return {"status": "ok"}


@router.post("/mkdir")
async def make_dir(
    path: Annotated[str, Query(description="Directory path to create")],
    storage: Annotated[StorageBackend, Depends(backend_dep)],
) -> dict:
    """Create a directory on the selected backend.

    Args:
        path: Backend-relative path of the new directory.
        storage: Resolved storage backend.

    Returns:
        A dict with a ``"status": "ok"`` key.

    """
    await storage.mkdir(path)
    return {"status": "ok"}


@router.post("/move")
async def move_path(req: MoveRequest) -> dict:
    """Move or rename a path on the selected backend.

    Source and destination must reside on the same backend.

    Args:
        req: Move request specifying ``src``, ``dst``, and ``backend``.

    Returns:
        A dict with a ``"status": "ok"`` key.

    """
    storage = get(req.backend)
    await storage.move(req.src, req.dst)
    return {"status": "ok"}
