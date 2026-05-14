"""Amazon S3 storage backend plugin for Strata.

Registers an :class:`~strata.plugins.protocols.StorageBackend` that exposes
an S3 bucket as a virtual filesystem.  Object keys are mapped to
``"/"``-delimited virtual paths; common prefixes become virtual directories.

Entry point::

    [project.entry-points."strata.plugins"]
    s3_storage = "strata_s3_storage:plugin"

Configuration:
    STRATA_S3_BUCKET: S3 bucket name (required).
    AWS_REGION: AWS region, e.g. ``"eu-west-1"`` (default: ``"us-east-1"``).
    AWS_ACCESS_KEY_ID: AWS access key (or use an instance/task IAM role).
    AWS_SECRET_ACCESS_KEY: AWS secret key.

To activate, install this package and add ``s3_storage`` to
``STRATA_ENABLED_PLUGINS``.
"""

import os
from collections.abc import AsyncIterator

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry


class S3StorageBackend:
    """Storage backend backed by an Amazon S3 bucket.

    Implements the :class:`~strata.plugins.protocols.StorageBackend` protocol.

    Attributes:
        id: ``"s3_storage"``
        name: ``"Amazon S3"``
        bucket: Name of the S3 bucket, from ``STRATA_S3_BUCKET``.
        region: AWS region, from ``AWS_REGION``.
    """

    id: str = "s3_storage"
    name: str = "Amazon S3"

    def __init__(self) -> None:
        self.bucket: str = os.environ.get("STRATA_S3_BUCKET", "")
        self.region: str = os.environ.get("AWS_REGION", "us-east-1")
        # Production: import boto3; self._client = boto3.client("s3", region_name=self.region)

    async def list(self, path: str) -> list[FileEntry]:
        """List S3 objects under the given virtual directory path.

        Args:
            path: Virtual directory path, e.g. ``"/photos/2024/"``.

        Returns:
            File entries for common prefixes (virtual dirs) and object keys.

        Todo:
            ``self._client.list_objects_v2(Bucket=self.bucket,
            Prefix=path.lstrip("/"), Delimiter="/")``
        """
        return []  # TODO: implement with boto3

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream an S3 object as async byte chunks.

        Args:
            path: Virtual file path mapped to an S3 object key.

        Returns:
            Async generator yielding ``bytes`` chunks.

        Todo:
            Stream from ``self._client.get_object(...)["Body"]``.
        """

        async def _stub() -> AsyncIterator[bytes]:
            yield b""  # TODO: implement with boto3

        return _stub()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Upload an async byte-stream as an S3 object.

        Args:
            path: Virtual destination path / S3 key.
            stream: Async generator providing file bytes.

        Todo:
            Buffer *stream* and call ``self._client.put_object(...)``, or use
            multipart upload for large files.
        """

    async def delete(self, path: str) -> None:
        """Delete an S3 object.

        Args:
            path: Virtual path / S3 key to delete.

        Todo:
            ``self._client.delete_object(Bucket=self.bucket, Key=path.lstrip("/"))``
        """

    async def mkdir(self, path: str) -> None:
        """Create a virtual directory by writing a zero-byte sentinel object.

        S3 has no native directory concept.  The convention is a zero-byte
        object whose key ends with ``"/"`` to make the prefix visible in
        listing responses.

        Args:
            path: Virtual directory path to create.

        Todo:
            ``self._client.put_object(Bucket=..., Key=.../,  Body=b"")``
        """

    async def move(self, src: str, dst: str) -> None:
        """Copy an S3 object then delete the source key.

        Args:
            src: Source virtual path / S3 key.
            dst: Destination virtual path / S3 key.

        Todo:
            ``copy_object`` followed by ``delete_object``.
        """

    def describe(self) -> StorageMeta:
        """Return backend metadata including bucket and region.

        Returns:
            A dict with ``id``, ``name``, ``bucket``, and ``region`` keys.
        """
        return StorageMeta(
            id=self.id,
            name=self.name,
            # bucket=self.bucket,
            # region=self.region,
        )


class S3StoragePlugin(BackendPlugin):
    """Plugin that registers the Amazon S3 storage backend.

    Capabilities contributed:

    - ``registry.storage``: :class:`S3StorageBackend`
    """

    id = "s3_storage"
    name = "S3 Storage"
    version = "0.1.0"
    description = "Exposes an Amazon S3 bucket as a storage backend."

    def register(self, registry: PluginRegistry) -> None:
        """Register the S3 storage backend.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.storage.add(S3StorageBackend())


plugin = S3StoragePlugin()
