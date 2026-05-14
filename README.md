# Strata

A self-hosted, plugin-based file browser with swappable storage backends.

## Repository layout

```
strata/                              ← repo root (WORKDIR in Docker: /strata)
├── backend/
│   ├── pyproject.toml               ← core package + uv workspace root
│   ├── uv.lock                      ← committed; used for reproducible installs
│   ├── plugins/                     ← installable plugin packages (workspace members)
│   │   ├── storage_local/           ← strata-storage-local
│   │   ├── s3_storage/              ← strata-s3-storage
│   │   ├── storage_smb/             ← strata-storage-smb
│   │   ├── image_preview/           ← strata-image-preview
│   │   ├── search_fulltext/         ← strata-search-fulltext
│   │   ├── collabora/               ← strata-collabora
│   │   └── auth_jwt/                ← strata-auth-jwt
│   └── src/strata/
│       ├── config.py                ← Settings (pydantic-settings, STRATA_ prefix)
│       ├── main.py                  ← FastAPI app, lifespan, /api/backends, /api/plugins
│       ├── dependencies.py          ← FastAPI Depends helpers (storage, plugin registry)
│       ├── api/
│       │   └── files.py             ← Generic file API routes (/api/files/*)
│       └── plugins/
│           ├── base.py              ← BackendPlugin base class
│           ├── protocols.py         ← Capability protocols (6 extension points)
│           ├── registry.py          ← PluginRegistry + typed sub-registries
│           └── loader.py            ← PluginLoader: entry-point discovery + lifecycle
├── frontend/
│   ├── package.json
│   ├── vite.config.js               ← Dev proxy /api → :8000
│   └── src/
│       ├── App.jsx                  ← Shell: layout + plugin loader
│       ├── plugin-api/
│       │   ├── registry.js          ← Extension point registry + loadPlugins()
│       │   └── hooks.js             ← React hooks: usePreviewer, useFileActions, …
│       ├── shell/
│       │   ├── FileBrowser.jsx      ← File list with backend picker
│       │   ├── FilePreview.jsx      ← Preview modal (plugin-aware)
│       │   └── Sidebar.jsx
│       └── core-plugins/api.js      ← fetch wrappers — all pass ?backend=<id>
├── Dockerfile                       ← Multi-stage: Node → uv → slim runtime
├── docker-compose.yaml              ← Strata + optional Collabora Online profile
├── Makefile
└── .env.example
```

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env          # edit STRATA_LOCAL_ROOT and other settings
make docker-build
make docker-up                # Strata at http://localhost:8000

# To include Collabora Online:
make docker-up-collabora
```

### Local development

```bash
make install                  # uv sync --extra all + npm install

# Run both servers in parallel:
make dev

# Or separately:
make dev-backend              # FastAPI on :8000 with --reload
make dev-frontend             # Vite on :5173, proxies /api → :8000
```

Open http://localhost:5173.

## Plugin system

### Discovery

Plugins are separate Python packages installed into the same virtualenv as the core.
Discovery uses `importlib.metadata` entry points — no folder scanning, no `sys.path` hacks.

Each plugin declares itself in its `pyproject.toml`:

```toml
[project.entry-points."strata.plugins"]
storage_local = "strata_storage_local:plugin"
```

The entry point group name (`strata.plugins`) is configured by `STRATA_ENTRY_POINT_GROUP`.

### Enabling plugins

Set `STRATA_ENABLED_PLUGINS` in `.env` or the environment (comma-separated):

```bash
STRATA_ENABLED_PLUGINS=storage_local,image_preview,auth_jwt
```

The default (in `config.py`) enables `storage_local`, `storage_smb`, and `s3_storage`.
Only plugins whose entry point name appears in this list are loaded.

### Lifecycle

For each enabled plugin, startup runs in this order:

1. `plugin.register(registry)` — synchronous; plugin calls typed `add()` methods on sub-registries.
2. `await plugin.on_startup()` — async init (connection pools, caches, etc.).

Shutdown calls `await plugin.on_shutdown()` on every loaded plugin in reverse order.

Both `PluginRegistry` and `PluginLoader` are stored in `request.state` and accessed
via FastAPI `Depends` helpers in `dependencies.py`.

### Extension points

| Sub-registry | Protocol | Purpose |
|---|---|---|
| `registry.storage` | `StorageBackend` | Storage system (filesystem, S3, SMB, …) |
| `registry.routes` | `RouteProvider` | Contribute FastAPI routes |
| `registry.file_handlers` | `FileHandler` | Frontend viewer/editor for file extensions |
| `registry.auth` | `AuthProvider` | Authentication (password, OAuth, LDAP, …) |
| `registry.search` | `SearchProvider` | Full-text or metadata search |
| `registry.thumbs` | `ThumbProvider` | Thumbnail generation |

Protocols are used for **static type-checking only** (pyright). There are no `isinstance`
chains in the core — the registry's typed `add()` methods are the only dispatch point.

### Bundled plugins

| Package | Entry point | Provides |
|---|---|---|
| `strata-storage-local` | `storage_local` | `StorageBackend` — local filesystem |
| `strata-s3-storage` | `s3_storage` | `StorageBackend` — S3-compatible stores |
| `strata-storage-smb` | `storage_smb` | `StorageBackend` — SMB/CIFS shares |
| `strata-image-preview` | `image_preview` | `ThumbProvider` + `FileHandler` for images |
| `strata-search-fulltext` | `search_fulltext` | `SearchProvider` — full-text indexing |
| `strata-collabora` | `collabora` | `RouteProvider` (WOPI host) + `FileHandler` (iframe editor) |
| `strata-auth-jwt` | `auth_jwt` | `AuthProvider` + `RouteProvider` (login/refresh endpoints) |

## Writing a plugin

### 1. Create a package under `backend/plugins/myplugin/`

```
backend/plugins/myplugin/
├── pyproject.toml
└── src/strata_myplugin/
    └── __init__.py
```

```toml
# backend/plugins/myplugin/pyproject.toml
[project]
name = "strata-myplugin"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["strata>=0.1.0"]

[project.entry-points."strata.plugins"]
myplugin = "strata_myplugin:plugin"

[tool.uv.sources]
strata = { workspace = true }
```

```python
# src/strata_myplugin/__init__.py
from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry

class MyPlugin(BackendPlugin):
    id = "myplugin"
    name = "My Plugin"
    version = "0.1.0"
    description = "One-line description."

    def register(self, registry: PluginRegistry) -> None:
        registry.storage.add(MyStorageBackend())    # optional
        registry.routes.add(MyRouteProvider())      # optional
        registry.file_handlers.add(MyFileHandler()) # optional

    async def on_startup(self) -> None: ...
    async def on_shutdown(self) -> None: ...

plugin = MyPlugin()
```

### 2. Run `uv sync`

The workspace in `backend/pyproject.toml` picks up all packages under `backend/plugins/*`
automatically. After creating your package, run:

```bash
cd backend && uv sync --extra all
```

### 3. Enable the plugin

```bash
# .env
STRATA_ENABLED_PLUGINS=storage_local,myplugin
```

## Storage backend request pattern

All file routes live under `/api/files/*`. The backend is selected per-request via
`?backend=<id>`.

```
GET    /api/files/list?backend=storage_local&path=/docs
GET    /api/files/download?backend=s3_storage&path=/report.pdf
POST   /api/files/upload?backend=storage_local&path=/uploads
DELETE /api/files/delete?backend=storage_local&path=/tmp/old.txt
POST   /api/files/mkdir?backend=storage_local&path=/new-dir
POST   /api/files/move   body: {"src": "/a", "dst": "/b", "backend": "storage_local"}
```

`GET /api/backends` returns metadata for all registered backends. The frontend uses this
to populate the backend picker.

## Configuration

All settings are read from environment variables (prefix `STRATA_`) or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `STRATA_ENABLED_PLUGINS` | see `config.py` | Comma-separated plugin entry point names to load |
| `STRATA_DB_URL` | `sqlite+aiosqlite:///$HOME/.strata/strata.db` | Shared async database URL (use `postgresql+asyncpg://…` in production) |
| `STRATA_DB_ECHO` | `false` | Log all SQL statements when `true` |
| `STRATA_LOCAL_ROOT` | `$HOME` | Root directory for `storage_local` |
| `STRATA_COLLABORA_URL` | `http://collabora:9980` | Collabora Online base URL |
| `STRATA_COLLABORA_SECRET` | `change-me` | WOPI shared secret |
| `STRATA_S3_BUCKET` | `""` | S3 bucket name |
| `STRATA_AWS_REGION` | `us-east-1` | AWS region |
| `STRATA_JWT_SECRET` | `change-me-in-production` | JWT signing secret (`auth_jwt` plugin) |
| `STRATA_JWT_ALGORITHM` | `HS256` | JWT signing algorithm (`auth_jwt` plugin) |
| `STRATA_JWT_EXPIRE_MINUTES` | `15` | Access token lifetime in minutes (`auth_jwt` plugin) |
| `STRATA_JWT_REFRESH_EXPIRE_DAYS` | `30` | Refresh token lifetime in days (`auth_jwt` plugin) |
| `STRATA_ENTRY_POINT_GROUP` | `strata.plugins` | Entry point group for plugin discovery |

## Makefile targets

```
make help                Show all targets
make install             uv sync --extra all + npm install
make install-backend     Python dependencies only
make install-frontend    Node dependencies only
make dev                 Run backend and frontend dev servers in parallel
make dev-backend         FastAPI on :8000 with --reload
make dev-frontend        Vite on :5173, proxies /api → :8000
make build               Build the frontend for production
make compile-deps        Update uv.lock without upgrading versions
make upgrade-deps        Update uv.lock upgrading all dependencies
make check-deps          Verify uv.lock is consistent
make format              Run ruff format + ruff check --fix
make lint                Run ruff format --check + ruff check + pyright
make typecheck           Run pyright only
make test                Run all tests (backend + frontend)
make test-backend        Run pytest for the backend only
make test-frontend       Run vitest for the frontend only
make docker-build        Build the Docker image
make docker-up           Start Strata only
make docker-up-collabora Start Strata + Collabora Online
make docker-down         Stop all services
make docker-logs         Tail logs
make clean               Remove build artefacts and caches
```
