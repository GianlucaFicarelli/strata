"""Amazon S3 storage backend plugin for Strata.

A pure storage plugin — no frontend assets.  Once registered, the
frontend can pass ``?backend=s3`` to any ``/api/files/*`` endpoint to
browse S3 objects as if they were local files.

Configuration (environment variables):
    STRATA_S3_BUCKET: Name of the S3 bucket to expose.
    AWS_REGION: AWS region, e.g. ``"eu-central-1"``.
    AWS_ACCESS_KEY_ID: AWS access key (or use an instance profile).
    AWS_SECRET_ACCESS_KEY: AWS secret key.

To activate::

    pip install boto3
    export STRATA_S3_BUCKET=my-bucket
    # Drop this package into plugins_enabled/ and restart Strata.
"""

from typing import TYPE_CHECKING

from strata.config import settings
from strata.core.storage.base import FileEntry, StorageBackend
from strata.plugins.base import BackendPlugin

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class S3StorageBackend(StorageBackend):
    """``StorageBackend`` implementation backed by an Amazon S3 bucket.

    All objects inside the configured bucket are exposed under a virtual
    directory hierarchy derived from the ``/``-delimited key structure.

    Attributes:
        id: ``"s3"``
        name: ``"Amazon S3"``
        bucket: Name of the S3 bucket, read from ``STRATA_S3_BUCKET``.
        region: AWS region, read from ``AWS_REGION``.

    """

    id: str = "s3"
    name: str = "Amazon S3"

    def __init__(self) -> None:
        self.bucket: str = settings.S3_BUCKET
        self.region: str = settings.AWS_REGION
        # Production: self._client = boto3.client("s3", region_name=self.region)

    async def list(self, path: str) -> list[FileEntry]:
        """List S3 objects under the given key prefix.

        Args:
            path: Virtual directory path, e.g. ``"/photos/2024/"``.

        Returns:
            A list of ``FileEntry`` objects representing common prefixes
            (directories) and object keys (files).

        Todo:
            Replace the stub with::

                resp = self._client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=path.lstrip("/"),
                    Delimiter="/",
                )

        """
        return [
            FileEntry(
                name="(S3 not configured — set STRATA_S3_BUCKET)",
                path=path.rstrip("/") + "/(not configured)",
                is_dir=False,
            ),
        ]

    async def read(self, path: str) -> AsyncIterator[bytes]:  # noqa: ARG002
        """Stream an S3 object as async byte chunks.

        Args:
            path: Virtual file path mapping to an S3 object key.

        Returns:
            An async generator yielding ``bytes`` chunks.

        Todo:
            Replace the stub with streaming from
            ``self._client.get_object(...)["Body"]``.

        """

        async def _empty() -> AsyncIterator[bytes]:
            yield b""

        return _empty()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Upload a byte stream as an S3 object.

        Args:
            path: Virtual destination path / S3 key.
            stream: Async generator providing file bytes.

        Todo:
            Accumulate *stream* and call
            ``self._client.put_object(Bucket=self.bucket, Key=..., Body=...)``.
            For large files use multipart upload instead.

        """

    async def delete(self, path: str) -> None:
        """Delete an S3 object.

        Args:
            path: Virtual file path / S3 key to delete.

        Todo:
            Call
            ``self._client.delete_object(Bucket=self.bucket, Key=path.lstrip("/"))``.

        """

    async def mkdir(self, path: str) -> None:
        """Create a virtual S3 directory by writing a zero-byte sentinel object.

        S3 has no real directory concept.  The convention is to create a
        zero-byte object whose key ends with ``"/"`` to make the prefix
        visible in listing results.

        Args:
            path: Virtual directory path to create.

        Todo:
            Call ``self._client.put_object(Bucket=..., Key=.../,  Body=b"")``.

        """

    async def move(self, src: str, dst: str) -> None:
        """Copy an S3 object then delete the source.

        Args:
            src: Source virtual path / S3 key.
            dst: Destination virtual path / S3 key.

        Todo:
            Call ``copy_object`` followed by ``delete_object``.

        """

    def describe(self) -> dict:
        """Return backend metadata including bucket and region.

        Returns:
            A dict with ``id``, ``name``, ``bucket``, and ``region``.

        """
        return {
            "id": self.id,
            "name": self.name,
            "bucket": self.bucket,
            "region": self.region,
        }


class S3BackendPlugin(BackendPlugin):
    """Plugin that registers the S3 storage backend with Strata.

    This is a pure storage plugin — it contributes no API routes and
    no frontend assets beyond what the generic file browser already
    provides.

    Capabilities:
        storage: Registers a ``StorageBackend`` accessible via
            ``?backend=s3``.
    """

    id: str = "s3_backend"
    name: str = "S3 Storage Backend"
    version: str = "0.1.0"
    description: str = "Browse Amazon S3 buckets alongside other backends."
    handles: list[str] = []  # noqa: RUF012

    def get_storage_backend(self) -> S3StorageBackend:
        """Return the ``S3StorageBackend`` singleton for this plugin."""
        return S3StorageBackend()

    def get_capabilities(self) -> list[str]:
        """Return ``["storage"]``."""
        return ["storage"]

    def get_frontend_assets(self) -> dict[str, str]:
        """Return an empty assets dict — this plugin has no frontend module."""
        return {}


plugin = S3BackendPlugin()
