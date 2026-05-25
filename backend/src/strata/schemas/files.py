from pydantic import BaseModel


class FileEntry(BaseModel):
    """Metadata for a single file or directory entry.

    Attributes:
        name: Bare filename, e.g. ``"report.docx"``.
        path: Backend-relative path, e.g. ``"/docs/report.docx"``.
        is_dir: ``True`` if this entry represents a directory.
        size: File size in bytes.  ``None`` for directories or when unknown.
        modified: Last-modified time as a POSIX timestamp.  ``None`` if the
            backend does not expose modification times.
        mime: MIME type string, e.g. ``"image/png"``.  ``None`` if unknown.
    """

    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified: float | None = None
    mime: str | None = None


class FileMoveRequest(BaseModel):
    """Request body for the move / rename endpoint.

    Attributes:
        src: Backend-relative source path.
        dst: Backend-relative destination path.
    """

    src: str
    dst: str


class FileUploadResult(BaseModel):
    status: str
    path: str
    backend: str


class FileDeleteResult(BaseModel):
    status: str


class FileMoveResult(BaseModel):
    status: str


class DirectoryCreateResult(BaseModel):
    status: str


class DownloadTokenResponse(BaseModel):
    """Response from ``GET /api/files/download-token``.

    Attributes:
        token: HMAC-signed opaque token for use as ``?token=`` in the
            download URL.  Valid for ``expires_in`` seconds.
        expires_in: Token lifetime in seconds.
    """

    token: str
    expires_in: int
