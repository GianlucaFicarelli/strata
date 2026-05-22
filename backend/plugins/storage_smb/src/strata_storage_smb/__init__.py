"""SMB/CIFS network share storage backend plugin for Strata.

Registers a :class:`~strata.plugins.protocols.StorageTemplate` so admins can
create named instances with host/share/credentials configured.  Per-user
credentials (username + password) are declared ``user_editable=True`` so
each user fills them in via the self-service UI.

Entry point::

    [project.entry-points."strata.plugins"]
    storage_smb = "strata_storage_smb:plugin"

The legacy ``storage_smb_credentials`` table and ``SmbStorageDbContributor``
are removed; credentials are now stored in ``core_storage_user_configs``
managed by the core.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from pydantic import BaseModel, Field

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import InstanceContext, StorageBackend
from strata.plugins.registry import PluginRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry

# ── Config schema ─────────────────────────────────────────────────────────────


class SmbStorageConfig(BaseModel):
    """Admin + user configuration for an SMB storage instance.

    Admin-level fields (set once per instance):
        host, share, domain, root_path

    User-editable fields (each user fills these in):
        smb_username, smb_password
    """

    host: Annotated[
        str,
        Field(description="Hostname or IP address of the SMB server"),
    ]
    share: Annotated[
        str,
        Field(description="Share name on the server, e.g. 'documents'"),
    ]
    domain: Annotated[
        str,
        Field(default="", description="Windows domain (leave empty if not applicable)"),
    ]
    root_path: Annotated[
        str,
        Field(
            default="/",
            description=(
                "Base path within the share exposed to users. "
                "Supports {username} and {user_id} placeholders."
            ),
            json_schema_extra={"template": True},
        ),
    ]
    smb_username: Annotated[
        str,
        Field(
            description="Your SMB username",
            json_schema_extra={"user_editable": True},
        ),
    ]
    smb_password: Annotated[
        str,
        Field(
            description="Your SMB password",
            json_schema_extra={"secret": True, "user_editable": True},
        ),
    ]


# ── Backend implementation ────────────────────────────────────────────────────


class SmbStorageBackend:
    """Storage backend that accesses an SMB/CIFS network share.

    Implements the :class:`~strata.plugins.protocols.StorageBackend` protocol.
    The actual smbclient calls are left as TODOs — the structure is complete.
    """

    def __init__(self, instance_id: str, config: SmbStorageConfig) -> None:
        self.id = f"smb:{instance_id}"
        self.name = f"SMB: \\\\{config.host}\\{config.share}"
        self._config = config

    def _unc(self, path: str) -> str:
        parts = (self._config.root_path.rstrip("/") + "/" + path.lstrip("/")).lstrip("/")
        return f"\\\\{self._config.host}\\{self._config.share}\\{parts.replace('/', chr(92))}"

    async def list(self, path: str) -> list[FileEntry]:
        # TODO: smbclient.scandir(self._unc(path))
        return []

    async def read(self, path: str) -> AsyncIterator[bytes]:
        # TODO: smbclient.open_file(self._unc(path), mode="rb")
        async def _stub() -> AsyncIterator[bytes]:
            yield b""

        return _stub()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        # TODO: smbclient.open_file(self._unc(path), mode="wb")
        pass

    async def delete(self, path: str) -> None:
        # TODO: smbclient.remove / smbclient.rmdir
        pass

    async def mkdir(self, path: str) -> None:
        # TODO: smbclient.makedirs(self._unc(path), exist_ok=True)
        pass

    async def move(self, src: str, dst: str) -> None:
        # TODO: smbclient.rename(self._unc(src), self._unc(dst))
        pass

    def describe(self) -> StorageMeta:
        return StorageMeta(id=self.id, name=self.name)


# ── StorageTemplate ───────────────────────────────────────────────────────────


class SmbStorageTemplate:
    """Template for admin-configured SMB instances.

    Admin sets host/share/domain/root_path.  Each user fills in their own
    ``smb_username`` and ``smb_password`` via the self-service UI before
    the instance becomes visible in their backend picker.

    Implements :class:`~strata.plugins.protocols.StorageTemplate`.
    """

    plugin_id: str = "storage_smb"
    display_name: str = "SMB / Network Share"
    description: str = (
        "Samba / Windows network share. "
        "Admin configures host and share; each user provides their own credentials."
    )
    config_schema: type[BaseModel] = SmbStorageConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        assert isinstance(config, SmbStorageConfig)
        return SmbStorageBackend(
            instance_id=f"{config.host}_{config.share}_{context.user_id}",
            config=config,
        )


# ── Plugin ────────────────────────────────────────────────────────────────────


class SmbStoragePlugin(BackendPlugin):
    """Plugin that registers the SMB storage template."""

    id = "storage_smb"
    name = "SMB Storage"
    version = "0.1.0"
    description = "Samba / Windows network share storage with per-user credentials."

    def register(self, registry: PluginRegistry) -> None:
        registry.storage_templates.add(SmbStorageTemplate())


plugin = SmbStoragePlugin()
