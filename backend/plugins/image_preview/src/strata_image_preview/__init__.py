"""Image preview plugin for Strata.

A hybrid plugin that contributes three capabilities:

- :class:`~strata.plugins.protocols.RouteProvider`: exposes a
  ``GET /api/plugins/image_preview/thumbnail`` endpoint.
- :class:`~strata.plugins.protocols.FileHandler`: registers a frontend JS
  module that renders images in the preview modal.
- :class:`~strata.plugins.protocols.ThumbProvider`: generates resized JPEG
  thumbnails from common raster image formats using Pillow.

Handled extensions:
    ``.bmp``, ``.gif``, ``.jpeg``, ``.jpg``, ``.png``, ``.svg``, ``.webp``

Entry point::

    [project.entry-points."strata.plugins"]
    image_preview = "strata_image_preview:plugin"
"""

import io
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry

_HANDLED: list[str] = [".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"]
_THUMB_MIMES: frozenset[str] = frozenset(
    {"image/bmp", "image/gif", "image/jpeg", "image/png", "image/webp"}
)
_ROOT: Path = Path(os.environ.get("STRATA_LOCAL_ROOT", Path.home())).resolve()

# ── API routes ────────────────────────────────────────────────────────────────

_router = APIRouter(prefix="/api/plugins/image_preview", tags=["image_preview"])


@_router.get("/thumbnail")
async def thumbnail(
    path: str = Query(..., description="Backend-relative image path"),
    width: int = Query(default=256, ge=16, le=2048),
    height: int = Query(default=256, ge=16, le=2048),
) -> Response:
    """Return a resized JPEG thumbnail for the given image file.

    Args:
        path: Backend-relative path to the source image.
        width: Maximum thumbnail width in pixels.
        height: Maximum thumbnail height in pixels.

    Returns:
        A JPEG :class:`~fastapi.responses.Response` containing the thumbnail.

    Raises:
        HTTPException: 403 if *path* escapes the storage root; 404 if the
            file does not exist or is not a handled image type.
    """
    target = (_ROOT / path.lstrip("/")).resolve()
    if not target.is_relative_to(_ROOT):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.is_file() or target.suffix.lower() not in _HANDLED:
        raise HTTPException(status_code=404, detail="Not a supported image")

    with Image.open(target) as img:
        img.thumbnail((width, height))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)

    return Response(content=buf.getvalue(), media_type="image/jpeg")


# ── Capability implementations ────────────────────────────────────────────────


class ImageRouteProvider:
    """Contributes the ``/thumbnail`` API route.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the image preview API router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return _router


class ImageFileHandler:
    """Registers the frontend image viewer for common image extensions.

    Implements :class:`~strata.plugins.protocols.FileHandler`.

    Attributes:
        handles: Image extensions this handler covers.
        frontend_module: URL of the JS ES module served at startup.
    """

    handles: list[str] = _HANDLED
    frontend_module: str = "/api/plugins/image_preview/assets/main.js"


class ImageThumbProvider:
    """Generates JPEG thumbnails from raster images using Pillow.

    Implements :class:`~strata.plugins.protocols.ThumbProvider`.
    """

    def can_handle(self, mime: str) -> bool:
        """Return ``True`` for supported raster image MIME types.

        Args:
            mime: MIME type string to check.

        Returns:
            ``True`` if Pillow can decode files of this type.
        """
        return mime in _THUMB_MIMES

    async def generate(
        self,
        stream: AsyncIterator[bytes],
        *,
        width: int = 256,
        height: int = 256,
    ) -> bytes:
        """Generate a JPEG thumbnail from a raster image byte-stream.

        Args:
            stream: Async generator providing the source image bytes.
            width: Maximum thumbnail width in pixels.
            height: Maximum thumbnail height in pixels.

        Returns:
            Raw JPEG bytes of the generated thumbnail.
        """
        data = b"".join([chunk async for chunk in stream])
        with Image.open(io.BytesIO(data)) as img:
            img.thumbnail((width, height))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()


# ── Plugin ────────────────────────────────────────────────────────────────────


class ImagePreviewPlugin(BackendPlugin):
    """Hybrid plugin providing image thumbnails and frontend preview.

    Capabilities contributed:

    - ``registry.routes``: :class:`ImageRouteProvider`
    - ``registry.file_handlers``: :class:`ImageFileHandler`
    - ``registry.thumbs``: :class:`ImageThumbProvider`
    """

    id = "image_preview"
    name = "Image Preview"
    version = "0.1.0"
    description = "Thumbnails and in-browser preview for common image formats."

    def register(self, registry: PluginRegistry) -> None:
        """Contribute image preview capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.routes.add(ImageRouteProvider())
        registry.file_handlers.add(ImageFileHandler())
        registry.thumbs.add(ImageThumbProvider())


plugin = ImagePreviewPlugin()
