from pathlib import Path

from sqlalchemy import MetaData

from strata.db.base import Base


class CoreUsersDbContributor:
    """Registers the core ``core_users`` table and its Alembic migrations.

    This contributor is always added to :class:`~strata.plugins.registry.DbRegistry`
    first, before any plugin's ``register()`` is called.  This guarantees
    that the ``core_users`` table is created before any plugin migration
    that declares a FK to it.

    Attributes:
        metadata: The SQLAlchemy :class:`~sqlalchemy.MetaData` for
            ``core_users``.
        migrations_dir: Absolute path to ``strata/db/migrations/`` inside
            the installed ``strata`` package.
    """

    metadata: MetaData = Base.metadata
    migrations_dir: Path = Path(__file__).parent / "migrations"
