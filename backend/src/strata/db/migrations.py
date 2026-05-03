"""Alembic migration helpers for Strata.

:func:`run_migrations` provides a programmatic way to run Alembic ``upgrade
head`` without invoking the CLI.  Each plugin that contributes DB tables
calls this from its ``on_startup()`` hook.

Design constraints
------------------
- Each plugin owns its own Alembic environment (``migrations/`` directory
  inside the plugin package).  This keeps migrations self-contained and
  avoids a central migrations repo that every plugin would need to touch.
- The ``env.py`` in each plugin's ``migrations/`` directory imports the
  plugin's ``Base.metadata`` so that ``autogenerate`` only sees that
  plugin's tables.
- The application engine URL is injected at runtime via
  :func:`run_migrations`, so plugins never hard-code connection strings.

Typical ``env.py`` for a plugin::

    # strata_myplugin/migrations/env.py
    from alembic import context
    from strata_myplugin.models import Base

    def run_migrations_online() -> None:
        connectable = context.config.attributes["engine"]

        async def do_run(conn):
            context.configure(connection=conn, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            connectable.run_sync(do_run)  # run_sync gives a sync conn
        )

    run_migrations_online()
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncEngine

L = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine, migrations_dir: Path) -> None:
    """Run ``alembic upgrade head`` programmatically for a plugin.

    The engine is injected into the Alembic ``config.attributes`` dict so
    that the plugin's ``env.py`` can retrieve it without reading a URL from
    ``alembic.ini``.

    Args:
        engine: The application async engine.
        migrations_dir: Absolute path to the plugin's ``migrations/``
            directory (the one containing ``env.py`` and ``versions/``).

    Raises:
        Exception: Propagates any Alembic or SQLAlchemy error so that the
            plugin loader can catch it and skip the plugin.
    """
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_dir))
    # Disable the default URL so env.py uses the injected engine instead.
    alembic_cfg.set_main_option("sqlalchemy.url", "")
    alembic_cfg.attributes["engine"] = engine

    L.info("Running Alembic migrations from %s", migrations_dir)

    # Alembic's command API is synchronous; it runs fine in a thread because
    # the actual DB work happens via run_sync inside env.py.
    await to_thread.run_sync(lambda: command.upgrade(alembic_cfg, "head"))
    L.info("Migrations complete for %s", migrations_dir.parent.name)
