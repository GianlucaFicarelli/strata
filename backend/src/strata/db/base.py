from sqlalchemy.orm import DeclarativeBase


def plugin_base(plugin_name: str) -> type[DeclarativeBase]:
    """Return a fresh ``DeclarativeBase`` subclass for a plugin.

    Each plugin should call this **once at module level** to obtain its own
    ``Base``, then define all ORM models as subclasses of that ``Base``.
    Using a per-plugin base keeps metadata namespaced and allows the
    :class:`~strata.plugins.registry.DbRegistry` to collect each plugin's
    tables separately.

    The resulting class carries a ``__plugin_name__`` class attribute that
    is used for logging.

    Args:
        plugin_name: Unique plugin identifier, e.g. ``"strata_jwt_auth"``.
            Used only for diagnostics.

    Returns:
        A :class:`~sqlalchemy.orm.DeclarativeBase` subclass whose
        ``metadata`` covers only this plugin's tables.

    Example::

        # strata_myplugin/models.py
        from sqlalchemy.orm import Mapped, mapped_column
        from strata.db.plugin import plugin_base

        Base = plugin_base("strata_myplugin")

        class Widget(Base):
            __tablename__ = "myplugin_widget"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str]
    """

    class _Base(DeclarativeBase):
        __plugin_name__: str = plugin_name

    _Base.__name__ = f"{plugin_name}Base"
    _Base.__qualname__ = f"{plugin_name}Base"
    return _Base


# The core Base is produced via plugin_base() like any other contributor so
# that its MetaData object is self-contained and registerable independently.
Base = plugin_base("strata_core")
