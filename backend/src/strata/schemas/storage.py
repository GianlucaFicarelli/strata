"""Schemas for the storage instance / template API."""

from typing import Any

from pydantic import BaseModel


class StorageTemplateSchema(BaseModel):
    """Public metadata for a StorageTemplate registered by a plugin.

    Attributes:
        plugin_id: Unique snake_case id matching the plugin entry point.
        display_name: Human-readable name shown in the admin UI.
        description: One-line description of what this template provides.
        config_schema: JSON Schema dict derived from the template's Pydantic
            config model.  Used by the frontend to auto-render the admin form.
            Secret fields have ``"secret": true`` in their schema extras.
            Template fields have ``"template": true``.
            User-editable fields have ``"user_editable": true``.
    """

    plugin_id: str
    display_name: str
    description: str
    config_schema: dict[str, Any]


class StorageInstanceCreate(BaseModel):
    """Request body for creating a storage instance.

    Attributes:
        plugin_id: The template to instantiate.
        instance_name: Admin-chosen display label.
        config: Admin-level config values keyed by field name.  Secret fields
            are stored encrypted; template fields are stored as-is (expanded
            at request time).
    """

    plugin_id: str
    instance_name: str
    config: dict[str, Any]


class StorageInstanceUpdate(BaseModel):
    """Request body for updating a storage instance.

    All fields are optional; only provided keys are updated.
    """

    instance_name: str | None = None
    config: dict[str, Any] | None = None
    is_enabled: bool | None = None


class StorageInstanceResponse(BaseModel):
    """Public representation of a storage instance.

    Secret fields in ``config`` are replaced with ``"********"``.
    """

    id: str
    plugin_id: str
    instance_name: str
    config: dict[str, Any]
    is_enabled: bool
    created_at: str
    updated_at: str


class UserStorageConfigUpdate(BaseModel):
    """Request body for a user updating their own config for an instance.

    Attributes:
        is_enabled: Whether this instance appears in the user's backend picker.
        config: Only the ``user_editable`` fields; other keys are ignored.
    """

    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class UserStorageConfigResponse(BaseModel):
    """User's personal config state for one instance."""

    instance_id: str
    instance_name: str
    plugin_id: str
    plugin_display_name: str
    is_enabled: bool
    config: dict[str, Any]
    is_ready: bool  # True when all required user_editable fields are filled


class ReadyBackendMeta(BaseModel):
    """Metadata for a fully-ready storage backend, returned by GET /api/storage/backends.

    ``id`` is the instance UUID and is the value the client passes as ``?backend=<id>``.
    ``plugin_id`` identifies which template the instance was created from; the frontend
    uses it to show a human-readable type label next to the instance name.
    """

    id: str
    name: str
    plugin_id: str
