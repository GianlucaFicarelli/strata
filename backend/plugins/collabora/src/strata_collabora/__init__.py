"""Collabora Online integration plugin for Strata.

A hybrid plugin that implements the WOPI host protocol so that a self-hosted
Collabora Online instance can open, edit, and save Office-compatible files
stored in any Strata storage backend.

Capabilities contributed:

- :class:`~strata.plugins.protocols.RouteProvider`: WOPI host endpoints and
  an ``editor-url`` helper endpoint.
- :class:`~strata.plugins.protocols.FileHandler`: frontend iframe component
  for Office-compatible file formats.

Entry point::

    [project.entry-points."strata.plugins"]
    collabora = "strata_collabora:plugin"

Configuration:
    STRATA_COLLABORA_URL: Base URL of the Collabora Online instance,
        e.g. ``"https://collabora.example.com"`` (required).
    STRATA_COLLABORA_SECRET: Secret used to sign WOPI access tokens.
        Use a long random string in production.
    STRATA_LOCAL_ROOT: Inherited from the local storage backend.

Security note:
    The WOPI token in this stub is base64-encoded plain text.  A production
    implementation must sign tokens with HMAC-SHA256 and enforce expiry.
"""

import base64
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import FileHandler, RouteProvider  # noqa: F401 # type: ignore
from strata.plugins.registry import PluginRegistry

_COLLABORA_URL: str = os.environ.get(
    "STRATA_COLLABORA_URL", "https://collabora.example.com"
).rstrip("/")
_SECRET: str = os.environ.get("STRATA_COLLABORA_SECRET", "change-me-in-production")
_ROOT: Path = Path(os.environ.get("STRATA_LOCAL_ROOT", Path.home())).resolve()

_HANDLED: list[str] = [
    ".docx",
    ".doc",
    ".odt",
    ".rtf",
    ".xlsx",
    ".xls",
    ".ods",
    ".csv",
    ".pptx",
    ".ppt",
    ".odp",
]

# ── Token helpers ─────────────────────────────────────────────────────────────


def _encode_token(path: str) -> str:
    """Encode a file path as a WOPI access token.

    Args:
        path: Backend-relative file path.

    Returns:
        URL-safe base64 string.  **Not signed — replace with HMAC in prod.**
    """
    return base64.urlsafe_b64encode(path.encode()).decode()


def _decode_token(token: str) -> str:
    """Decode a WOPI access token back to a file path.

    Args:
        token: URL-safe base64 string from :func:`_encode_token`.

    Returns:
        The original backend-relative file path.

    Raises:
        HTTPException: 403 if *token* cannot be decoded.
    """
    try:
        return base64.urlsafe_b64decode(token.encode()).decode()
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid WOPI token") from exc


def _safe(path: str) -> Path:
    """Resolve *path* and assert it stays inside ``_ROOT``.

    Args:
        path: Backend-relative path string.

    Returns:
        Resolved absolute ``Path``.

    Raises:
        HTTPException: 403 if the path escapes ``_ROOT``.
    """
    target = (_ROOT / path.lstrip("/")).resolve()
    if not target.is_relative_to(_ROOT):
        raise HTTPException(status_code=403, detail="Access denied")
    return target


# ── API routes ────────────────────────────────────────────────────────────────

_router = APIRouter(prefix="/api/plugins/collabora", tags=["collabora"])


@_router.get("/editor-url")
async def editor_url(
    path: str = Query(..., description="Backend-relative path of the file to open"),
    backend: str = Query(default="storage_local", description="Storage backend ID"),
) -> dict[str, str]:
    """Return the Collabora iframe URL for the given file.

    The frontend renders the returned URL in an ``<iframe>`` to display the
    Collabora editor.  The URL includes the WOPI source path and access token
    so Collabora can fetch and save the file without browser involvement.

    Args:
        path: Backend-relative path of the file to edit.
        backend: Storage backend that holds the file.

    Returns:
        A dict with a single ``"url"`` key containing the Collabora launch URL.
    """
    token = _encode_token(path)
    wopi_src = f"/api/plugins/collabora/wopi/files/{token}"
    url = f"{_COLLABORA_URL}/browser/dist/cool.html?WOPISrc={wopi_src}&access_token={token}"
    return {"url": url}


@_router.get("/wopi/files/{file_id}")
async def wopi_check_file_info(
    file_id: str,
    access_token: str = Query(...),
) -> JSONResponse:
    """WOPI ``CheckFileInfo`` — describe the file to Collabora.

    Collabora calls this first to learn the filename, size, and edit
    permissions before rendering the editor.

    Args:
        file_id: URL-safe base64-encoded file path (the WOPI file identifier).
        access_token: WOPI access token supplied by Collabora.

    Returns:
        A :class:`~fastapi.responses.JSONResponse` conforming to the WOPI
        ``CheckFileInfo`` schema.

    Raises:
        HTTPException: 404 if the file does not exist.
    """
    path = _decode_token(file_id)
    target = _safe(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    stat = target.stat()
    return JSONResponse(
        {
            "BaseFileName": target.name,
            "Size": stat.st_size,
            "LastModifiedTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
            "UserCanWrite": True,
            "UserFriendlyName": "Strata User",
            "OwnerId": "strata",
            "UserId": "strata-user",
        }
    )


@_router.get("/wopi/files/{file_id}/contents")
async def wopi_get_file(
    file_id: str,
    access_token: str = Query(...),
) -> StreamingResponse:
    """WOPI ``GetFile`` — stream file bytes to Collabora.

    Args:
        file_id: URL-safe base64-encoded file path.
        access_token: WOPI access token.

    Returns:
        A streaming response with the raw file bytes.

    Raises:
        HTTPException: 404 if the file does not exist.
    """
    path = _decode_token(file_id)
    target = _safe(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    async def _gen() -> AsyncIterator[bytes]:
        async with aiofiles.open(target, "rb") as fh:
            while chunk := await fh.read(64 * 1024):
                yield chunk

    return StreamingResponse(_gen(), media_type="application/octet-stream")


@_router.post("/wopi/files/{file_id}/contents")
async def wopi_put_file(
    file_id: str,
    request: Request,
    access_token: str = Query(...),
) -> dict[str, Any]:
    """WOPI ``PutFile`` — receive and persist edited file bytes from Collabora.

    Collabora calls this when the user saves the document.  The raw request
    body contains the updated file content.

    Args:
        file_id: URL-safe base64-encoded file path.
        request: Raw FastAPI request; body contains the new file bytes.
        access_token: WOPI access token.

    Returns:
        An empty JSON object ``{}`` on success, as required by the WOPI spec.
    """
    path = _decode_token(file_id)
    target = _safe(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, "wb") as fh:
        async for chunk in request.stream():
            await fh.write(chunk)
    return {}


# ── Capability implementations ────────────────────────────────────────────────


class CollaboraRouteProvider:
    """Contributes the WOPI host and editor-url API routes.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the Collabora API router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return _router


class CollaboraFileHandler:
    """Registers the frontend Collabora iframe for Office file formats.

    Implements :class:`~strata.plugins.protocols.FileHandler`.

    Attributes:
        handles: Office-compatible extensions this handler covers.
        frontend_module: URL of the JS ES module served at startup.
    """

    handles: list[str] = _HANDLED
    frontend_module: str = "/api/plugins/collabora/assets/main.js"


# ── Plugin ────────────────────────────────────────────────────────────────────


class CollaboraPlugin(BackendPlugin):
    """Hybrid plugin providing Collabora Online editing for Office formats.

    Capabilities contributed:

    - ``registry.routes``: :class:`CollaboraRouteProvider` (WOPI host)
    - ``registry.file_handlers``: :class:`CollaboraFileHandler`
    """

    id = "collabora"
    name = "Collabora Online"
    version = "0.1.0"
    description = (
        "Edit .docx, .xlsx, .odt and other Office formats "
        "via a self-hosted Collabora Online instance."
    )

    def register(self, registry: PluginRegistry) -> None:
        """Contribute Collabora capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.routes.add(CollaboraRouteProvider())
        registry.file_handlers.add(CollaboraFileHandler())


plugin = CollaboraPlugin()
