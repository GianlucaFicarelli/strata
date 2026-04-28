"""Public re-exports for ``core.storage``."""

from strata.core.storage.base import FileEntry, StorageBackend
from strata.core.storage.local import local_storage
from strata.core.storage.registry import backend_dep, get, get_all, register

__all__: list[str] = [
    "FileEntry",
    "StorageBackend",
    "backend_dep",
    "get",
    "get_all",
    "local_storage",
    "register",
]
