"""Generic file API for Strata.

Every endpoint except ``download`` and ``download-token`` requires an active
session (cookie auth) and accepts a ``?backend=<id>`` query parameter.  All
storage logic is delegated to the selected ``StorageBackend`` — this module
only handles HTTP concerns.

Download flow
-------------
1. Authenticated client calls ``GET /api/files/download-token?backend=<id>``
   while its session cookie is present.  The server issues a short-lived
   HMAC-signed token encoding ``(user_id, backend_id, exp)``.

2. Client constructs a plain ``<a href="/api/files/download?path=...&token=...">``
   link.  No JavaScript or credentials needed for the actual download.

3. ``GET /api/files/download`` verifies the HMAC token (no Redis lookup) and
   streams the file.

This avoids embedding session cookies in download URLs (which would appear in
server logs, browser history, and Referer headers).
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from strata.config import settings
from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageTemplateRegistryDep
from strata.dependencies.storage import StorageBackendDep, resolve_backend_by_ids
from strata.schemas.files import (
    DirectoryCreateResult,
    DownloadTokenResponse,
    FileDeleteResult,
    FileEntry,
    FileMoveRequest,
    FileMoveResult,
    FileUploadResult,
)
from strata.tokens import issue_download_token, verify_download_token

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/list")
async def list_dir(
    path: Annotated[str, Query(description="Directory path to list")],
    storage: StorageBackendDep,
) -> list[FileEntry]:
    """List the contents of a directory on the selected backend."""
    return await storage.list(path)


@router.get("/download-token")
async def get_download_token(
    backend: Annotated[str, Query(description="Backend instance UUID")],
    current_user: CurrentUserDep,
) -> DownloadTokenResponse:
    """Issue a short-lived HMAC-signed download token for a backend.

    The token encodes ``(user_id, backend_id, exp)`` and is verified by
    ``GET /api/files/download`` without any storage lookup.

    The client should call this endpoint once and embed the returned token in
    the ``?token=`` query parameter of the download URL.

    Args:
        backend: ``core_storage_instances.id`` UUID of the target backend.
        current_user: Authenticated user from the session cookie.

    Returns:
        A :class:`~strata.schemas.files.DownloadTokenResponse` containing the
        token string and its TTL in seconds.
    """
    token = issue_download_token(user_id=current_user.id, backend_id=backend)
    return DownloadTokenResponse(
        token=token,
        expires_in=settings.DOWNLOAD_TOKEN_TTL_SECONDS,
    )


@router.get("/download")
async def download_file(
    path: Annotated[str, Query(description="File path to download")],
    token: Annotated[str, Query(description="HMAC download token from /download-token")],
    db_session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> StreamingResponse:
    """Stream a file using a pre-issued HMAC download token.

    The token is verified without any Redis or DB lookup.  The backend is then
    resolved using the ``user_id`` and ``backend_id`` embedded in the token.

    Args:
        path: File path to stream from the resolved backend.
        token: HMAC-signed download token from ``GET /api/files/download-token``.
        db_session: Async DB session for backend resolution.
        template_registry: Storage template registry for backend construction.

    Returns:
        A streaming octet-stream response.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
        HTTPException: 400 if the backend is not available for this user.
    """
    user_id, backend_id = verify_download_token(token)

    storage = await resolve_backend_by_ids(
        db_session,
        instance_id=backend_id,
        user_id=user_id,
        template_registry=template_registry,
    )
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backend {backend_id!r} not found or not available for this user",
        )

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
) -> FileDeleteResult:
    """Delete a file or directory on the selected backend."""
    await storage.delete(path)
    return FileDeleteResult(status="ok")


@router.post("/mkdir")
async def make_dir(
    path: Annotated[str, Query(description="Directory path to create")],
    storage: StorageBackendDep,
) -> DirectoryCreateResult:
    """Create a directory on the selected backend."""
    await storage.mkdir(path)
    return DirectoryCreateResult(status="ok")


@router.post("/move")
async def move_path(
    req: FileMoveRequest,
    storage: StorageBackendDep,
) -> FileMoveResult:
    """Move or rename a path on the selected backend."""
    await storage.move(req.src, req.dst)
    return FileMoveResult(status="ok")
