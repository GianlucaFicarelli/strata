from pydantic import BaseModel

from strata.schemas.files import FileEntry


class SearchResult(BaseModel):
    """A single result returned by a search provider.

    Attributes:
        entry: The matching file entry.
        score: Relevance score in the range ``[0.0, 1.0]``.  Higher is more
            relevant.  ``None`` if the provider does not score results.
        snippet: A short excerpt from the file showing the match in context.
            ``None`` if the provider does not support snippets.
    """

    entry: FileEntry
    score: float | None = None
    snippet: str | None = None
