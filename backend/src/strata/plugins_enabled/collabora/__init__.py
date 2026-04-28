"""Collabora Online integration plugin for Strata.

A hybrid plugin that implements the WOPI (Web Application Open Platform
Interface) host protocol so that a self-hosted Collabora Online instance
can open, display, and save ``.docx``, ``.xlsx``, ``.odt``, and related
files directly from any Strata storage backend.

Architecture::

    Browser                  Strata (WOPI host)          Collabora Online
       │                           │                            │
       │  GET /files/list          │                            │
       │──────────────────────────►│                            │
       │  ◄──────────────────────── file list                   │
       │                           │                            │
       │  click .docx → GET        │                            │
       │  /plugins/collabora/      │                            │
       │  editor-url?path=...      │                            │
       │──────────────────────────►│                            │
       │  ◄── {url: "https://collabora/loleaflet/...&WOPISrc=...&access_token=..."} │
       │                           │                            │
       │  render <iframe src=url>  │                            │
       │                           │                            │
       │                           │  GET /wopi/files/{id}      │
       │                           │◄───────────────────────────│
       │                           │  → CheckFileInfo JSON      │
       │                           │──────────────────────────► │
       │                           │                            │
       │                           │  GET /wopi/files/{id}/contents
       │                           │◄───────────────────────────│
       │                           │  → raw file bytes          │
       │                           │──────────────────────────► │
       │                           │                            │
       │                           │  POST /wopi/files/{id}/contents (save)
       │                           │◄───────────────────────────│
       │                           │  write back to storage     │

Configuration (environment variables):
    STRATA_COLLABORA_URL: Base URL of your Collabora Online instance,
        e.g. ``"https://collabora.example.com"``.
    STRATA_COLLABORA_SECRET: Shared secret used to sign WOPI access
        tokens (use a long random string in production).
    STRATA_LOCAL_ROOT: Inherited from the local storage backend.

Security note:
    The WOPI access token in this stub is a base64-encoded plain-text
    path.  A production implementation must sign the token with HMAC
    and enforce expiry.
"""

import base64
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from strata.plugins.base import BackendPlugin

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ── Configuration ─────────────────────────────────────────────────────────────

_COLLABORA_URL: str = os.environ.get(
    "STRATA_COLLABORA_URL",
    "https://collabora.example.com",
).rstrip("/")

_SECRET: str = os.environ.get("STRATA_COLLABORA_SECRET", "change-me-in-production")

_ROOT: Path = Path(os.environ.get("STRATA_LOCAL_ROOT", Path.home())).resolve()

_HANDLED_EXTS: list[str] = [
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
        path: Backend-relative file path, e.g. ``"/docs/report.docx"``.

    Returns:
        A URL-safe base64 string.  **Not signed — replace with HMAC in
        production.**

    """
    return base64.urlsafe_b64encode(path.encode()).decode()


def _decode_token(token: str) -> str:
    """Decode a WOPI access token back to a file path.

    Args:
        token: URL-safe base64 string produced by ``_encode_token``.

    Returns:
        The original backend-relative file path.

    Raises:
        HTTPException: 403 if the token cannot be decoded.

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


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/plugins/collabora", tags=["collabora"])


@router.get("/editor-url")
async def editor_url(
    path: Annotated[str, Query(description="Backend-relative path of the file to edit")],
    backend: Annotated[str, Query(description="Storage backend ID")] = "local",  # noqa: ARG001
) -> dict:
    """Return the Collabora iframe URL for the given file.

    The frontend renders this URL in an ``<iframe>`` to display the
    Collabora editor.

    Args:
        path: Backend-relative path of the file to open.
        backend: Storage backend that holds the file.

    Returns:
        A dict with a single ``"url"`` key containing the fully-formed
        Collabora launch URL, including ``WOPISrc`` and ``access_token``
        query parameters.

    """
    token = _encode_token(path)
    wopi_src = f"/api/plugins/collabora/wopi/files/{token}"
    url = f"{_COLLABORA_URL}/browser/dist/cool.html?WOPISrc={wopi_src}&access_token={token}"
    return {"url": url}


# ── WOPI host endpoints ───────────────────────────────────────────────────────


@router.get("/wopi/files/{file_id}")
async def wopi_check_file_info(
    file_id: str,
    access_token: str,  # noqa: ARG001
) -> JSONResponse:
    """WOPI ``CheckFileInfo`` — describe the file to Collabora.

    Collabora calls this endpoint first to learn the file's name, size,
    and the user's edit permissions before rendering the editor.

    Args:
        file_id: URL-safe base64-encoded file path (used as the WOPI
            file identifier).
        access_token: WOPI access token supplied by Collabora.

    Returns:
        A ``JSONResponse`` conforming to the WOPI ``CheckFileInfo``
        schema.

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
        },
    )


@router.get("/wopi/files/{file_id}/contents")
async def wopi_get_file(
    file_id: str,
    access_token: str,  # noqa: ARG001
) -> StreamingResponse:
    """WOPI ``GetFile`` — stream file bytes to Collabora.

    Collabora calls this to retrieve the raw file content after
    ``CheckFileInfo`` succeeds.

    Args:
        file_id: URL-safe base64-encoded file path.
        access_token: WOPI access token.

    Returns:
        A ``StreamingResponse`` with the file's bytes.

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


@router.post("/wopi/files/{file_id}/contents")
async def wopi_put_file(
    file_id: str,
    request: Request,
    access_token: str,  # noqa: ARG001
) -> dict:
    """WOPI ``PutFile`` — receive and save edited file bytes from Collabora.

    Collabora calls this when the user saves the document.  The raw
    request body contains the updated file content.

    Args:
        file_id: URL-safe base64-encoded file path.
        request: Raw FastAPI request (body contains the new file bytes).
        access_token: WOPI access token.

    Returns:
        An empty JSON object ``{}`` on success, as required by the WOPI
        spec.

    Raises:
        HTTPException: 403 if the path is invalid.

    """
    path = _decode_token(file_id)
    target = _safe(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, "wb") as fh:
        async for chunk in request.stream():
            await fh.write(chunk)
    return {}


# ── Plugin class ──────────────────────────────────────────────────────────────


class CollaboraPlugin(BackendPlugin):
    """Hybrid plugin that adds Collabora Online editing to Strata.

    **Backend part**: implements the WOPI host protocol so Collabora can
    read and write files stored in any Strata backend.

    **Frontend part**: registers a previewer for Office-compatible
    formats that renders a full-screen ``<iframe>`` pointing at the
    Collabora Online instance.

    Capabilities:
        preview: Registers a frontend previewer (iframe-based editor).
        editor: Indicates this plugin provides in-browser editing, not
            just read-only preview.

    Configuration:
        Set ``STRATA_COLLABORA_URL`` to the base URL of your Collabora
        Online container before starting Strata.
    """

    id: str = "collabora"
    name: str = "Collabora Online"
    version: str = "0.1.0"
    description: str = (
        "Edit .docx, .xlsx, .odt and other Office formats "
        "via a self-hosted Collabora Online instance."
    )
    handles: list[str] = _HANDLED_EXTS

    def get_router(self) -> APIRouter:
        """Return the router exposing WOPI host and editor-url endpoints."""
        return router

    def get_capabilities(self) -> list[str]:
        """Return ``["preview", "editor"]``."""
        return ["preview", "editor"]


plugin = CollaboraPlugin()
