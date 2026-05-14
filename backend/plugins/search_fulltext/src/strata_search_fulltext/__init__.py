"""Full-text search plugin for Strata.

Contributes a :class:`~strata.plugins.protocols.SearchProvider` that indexes
plain-text file content using Whoosh (a pure-Python search library) and a
:class:`~strata.plugins.protocols.RouteProvider` that exposes a
``GET /api/plugins/search_fulltext/search`` endpoint.

Entry point::

    [project.entry-points."strata.plugins"]
    search_fulltext = "strata_search_fulltext:plugin"

Configuration:
    STRATA_SEARCH_INDEX_DIR: Directory where the Whoosh index is stored.
        Defaults to ``~/.strata/search_index``.
    STRATA_SEARCH_BACKEND_ID: ID of the storage backend to index.
        Defaults to ``"storage_local"``.

Note:
    This is a stub implementation.  The Whoosh index calls are marked with
    ``TODO`` comments.  A production implementation would also integrate with
    the file write/delete pipeline to keep the index up to date automatically.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import SearchProvider  # noqa: F401 # type: ignore
from strata.plugins.registry import PluginRegistry
from strata.schemas.files import FileEntry
from strata.schemas.search import SearchResult

_INDEX_DIR: Path = Path(
    os.environ.get("STRATA_SEARCH_INDEX_DIR", Path.home() / ".strata" / "search_index")
)
_BACKEND_ID: str = os.environ.get("STRATA_SEARCH_BACKEND_ID", "storage_local")

# ── API routes ────────────────────────────────────────────────────────────────

_router = APIRouter(prefix="/api/plugins/search_fulltext", tags=["search"])


@_router.get("/search")
async def search_endpoint(
    q: str = Query(..., description="Search query string"),
    path: str = Query(default="/", description="Directory to restrict search to"),
    backend: str = Query(default=_BACKEND_ID, description="Storage backend to search"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Search for files matching the given query.

    Args:
        q: Free-text search query.
        path: Backend-relative directory to restrict results to.
        backend: Storage backend ID to search.
        limit: Maximum number of results to return.

    Returns:
        A list of search result dicts, each with ``entry``, ``score``, and
        ``snippet`` fields.

    Todo:
        Wire up to ``FullTextSearchProvider.search()``.
    """
    return []  # TODO: implement with Whoosh


# ── Capability implementation ─────────────────────────────────────────────────


class FullTextSearchProvider:
    """Full-text search provider backed by a Whoosh index.

    Implements :class:`~strata.plugins.protocols.SearchProvider`.

    Attributes:
        backend_id: ID of the storage backend this provider searches.
    """

    backend_id: str = _BACKEND_ID

    async def search(
        self,
        query: str,
        path: str = "/",
        *,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search the Whoosh index for files matching *query*.

        Args:
            query: Free-text query string.
            path: Backend-relative directory to restrict the search to.
            limit: Maximum number of results to return.

        Returns:
            Search results sorted by descending relevance score.

        Todo:
            Open the Whoosh index from ``_INDEX_DIR``, run the query with
            a ``MultifieldParser``, and convert hits to :class:`SearchResult`
            objects.
        """
        return []  # TODO: implement with Whoosh

    async def index(self, entry: FileEntry, content: AsyncIterator[bytes]) -> None:
        """Add or update a file in the Whoosh index.

        Args:
            entry: File metadata.
            content: Async byte-stream of the file's content.

        Todo:
            Decode *content* as UTF-8 (best-effort), extract text, and call
            ``writer.update_document(path=entry.path, content=text, ...)``.
        """

    async def deindex(self, path: str) -> None:
        """Remove a file from the Whoosh index.

        Args:
            path: Backend-relative path to remove.

        Todo:
            Call ``writer.delete_by_term("path", path)``.
        """


class SearchRouteProvider:
    """Contributes the full-text search API route.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the search API router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return _router


# ── Plugin ────────────────────────────────────────────────────────────────────


class FullTextSearchPlugin(BackendPlugin):
    """Plugin providing full-text search over a local storage backend.

    Capabilities contributed:

    - ``registry.search``: :class:`FullTextSearchProvider`
    - ``registry.routes``: :class:`SearchRouteProvider`
    """

    id = "search_fulltext"
    name = "Full-Text Search"
    version = "0.1.0"
    description = "Indexes and searches file content using Whoosh."

    def register(self, registry: PluginRegistry) -> None:
        """Contribute search capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.search.add(FullTextSearchProvider())
        registry.routes.add(SearchRouteProvider())

    async def on_startup(self) -> None:
        """Ensure the Whoosh index directory exists."""
        _INDEX_DIR.mkdir(parents=True, exist_ok=True)
