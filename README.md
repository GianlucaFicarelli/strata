# Strata

A plugin-based file browser with swappable storage backends.

## Project structure

```
strata/
├── Dockerfile                           # Multi-stage: node → uv → runtime
├── docker-compose.yaml                  # Strata + optional Collabora Online
├── Makefile                             # Dev, build, lint, and Docker targets
├── .env.example                         # Copy to .env and customise
│
├── backend/
│   ├── pyproject.toml                   # Python project metadata + tool config
│   ├── uv.lock                          # Pinned dependency versions (commit this)
│   ├── .venv/                           # Created by `uv sync` (gitignored)
│   └── src/strata/
│       ├── config.py                    # Centralised settings via pydantic-settings
│       ├── main.py                      # FastAPI app entry point
│       ├── core/
│       │   ├── files.py                 # Generic file API — thin HTTP layer only
│       │   └── storage/
│       │       ├── base.py              # StorageBackend ABC + FileEntry model
│       │       ├── local.py             # Built-in local filesystem backend
│       │       └── registry.py         # Backend registry + backend_dep()
│       ├── plugins/
│       │   ├── base.py                  # BackendPlugin base class
│       │   └── loader.py               # Auto-discovery at startup
│       └── plugins_enabled/            # Active plugins — drop new ones here
│           ├── image_preview/          # Hybrid: thumbnail endpoint + image previewer
│           ├── s3_backend/             # Pure storage: S3 via ?backend=s3
│           └── collabora/             # Hybrid: WOPI host + iframe editor
│
└── frontend/
    ├── package.json
    ├── vite.config.js                   # Proxies /api → :8000 in dev
    └── src/
        ├── App.jsx                      # Shell: layout, routing, plugin loader
        ├── core-plugins/api.js          # fetch wrappers — all pass ?backend=<id>
        ├── plugin-api/
        │   ├── registry.js             # Extension point registry + loadPlugins()
        │   └── hooks.js                # React hooks: usePreviewer, useFileActions, …
        └── shell/
            ├── Sidebar.jsx
            ├── FileBrowser.jsx         # File list with backend picker (desktop + mobile)
            └── FilePreview.jsx         # Preview modal (plugin-aware)
```

## Quick start

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 22+
- Docker + Docker Compose (optional, for containerised deployment)

### Local development

```bash
cp .env.example .env       # customise STRATA_LOCAL_ROOT etc.
make install               # uv sync + npm install
```

Then in two terminals:

```bash
make dev-backend           # FastAPI with --reload on http://localhost:8000
make dev-frontend          # Vite HMR on http://localhost:5173
```

The frontend proxies all `/api/*` requests to the backend automatically.

### Docker

```bash
cp .env.example .env
make docker-build
make docker-up             # http://localhost:8000

# With Collabora Online (for .docx/.xlsx editing):
make docker-up-collabora
```

## Architecture

### Storage backends

Every `/api/files/*` endpoint accepts a `?backend=<id>` query parameter.
The request is delegated to the matching `StorageBackend` instance — the
core API contains no storage logic itself.

```
GET /api/files/list?path=/docs&backend=s3
        │
        ▼
   storage registry  →  S3StorageBackend.list("/docs")
```

The `local` backend is always available. Additional backends are registered
by plugins at startup and appear automatically in the frontend picker.

### Plugin system

Plugins are Python packages placed in `backend/src/strata/plugins_enabled/`.
They are discovered automatically at startup — no configuration required.

A plugin may provide any combination of:

| What | How | Example |
|---|---|---|
| Extra API routes | `get_router() → APIRouter` | Collabora WOPI endpoints |
| A storage backend | `get_storage_backend() → StorageBackend` | S3, SFTP |
| A frontend ES module | `get_frontend_assets() → dict` | Image previewer, Collabora iframe |

### Plugin types

| Type | Example | Backend routes | Frontend module |
|---|---|:---:|:---:|
| Pure storage | `s3_backend` | ✗ | ✗ |
| Pure frontend | themes, keyboard shortcuts | ✗ | ✓ |
| Hybrid — preview | `image_preview` | ✓ | ✓ |
| Hybrid — editor | `collabora` | ✓ (WOPI host) | ✓ (iframe) |

### Frontend extension points

| Registry key | Purpose |
|---|---|
| `previewers` | Render file content in the preview modal |
| `fileActions` | Right-click / toolbar actions on files |
| `sidebarItems` | Extra entries in the left navigation sidebar |
| `routes` | Entirely new pages in the frontend app |

## Writing a plugin

### 1. Create a Python package

```
backend/src/strata/plugins_enabled/myplugin/
├── __init__.py
└── frontend/
    └── main.js        # optional — served at /api/plugins/myplugin/assets/main.js
```

```python
# backend/src/strata/plugins_enabled/myplugin/__init__.py
from fastapi import APIRouter
from strata.plugins.base import BackendPlugin

router = APIRouter(prefix="/api/plugins/myplugin")

@router.get("/hello")
def hello() -> dict:
    return {"message": "Hello from myplugin!"}

class MyPlugin(BackendPlugin):
    id = "myplugin"
    name = "My Plugin"
    version = "0.1.0"
    description = "Does something useful."
    handles = [".xyz"]          # file extensions this plugin handles

    def get_router(self):
        return router

    def get_capabilities(self):
        return ["preview"]

plugin = MyPlugin()
```

### 2. Add a frontend module (optional)

```js
// backend/src/strata/plugins_enabled/myplugin/frontend/main.js
export function register(registry) {
  registry.previewers.push({
    id: "myplugin",
    canHandle: (file) => file.name.endsWith(".xyz"),
    component: ({ file, backend }) => { /* React component */ },
  });
}
```

### 3. Restart — the plugin is discovered automatically

No rebuild of the core application required.

## Configuration

All settings are read from environment variables. Copy `.env.example` to `.env`:

| Variable | Default | Description |
|---|---|---|
| `STRATA_LOCAL_ROOT` | `$HOME` | Root directory for the local storage backend |
| `STRATA_COLLABORA_URL` | `http://collabora:9980` | Base URL of your Collabora Online instance |
| `STRATA_COLLABORA_SECRET` | *(required in prod)* | Secret for signing WOPI tokens |
| `STRATA_S3_BUCKET` | — | S3 bucket name (s3_backend plugin) |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials |
| `STRATA_PORT` | `8000` | Host port for the Strata container |
| `COLLABORA_PORT` | `9980` | Host port for the Collabora container |

## Makefile targets

```
make help                 Show all targets with descriptions

make install              Install all dependencies (uv sync + npm install)
make install-backend      Install Python dependencies only
make install-frontend     Install Node dependencies only

make compile-deps         Update uv.lock without upgrading versions
make upgrade-deps         Update uv.lock to latest compatible versions
make check-deps           Verify uv.lock is consistent with pyproject.toml

make dev                  Run backend and frontend in parallel
make dev-backend          FastAPI on :8000 with hot-reload
make dev-frontend         Vite on :5173 with HMR

make build                Build the frontend for production
make build-frontend       Compile React into frontend/dist/

make docker-build         Build the Docker image
make docker-up            Start Strata (without Collabora)
make docker-up-collabora  Start Strata + Collabora Online
make docker-down          Stop all services
make docker-logs          Tail all service logs

make format               Auto-format backend code (ruff)
make lint                 Run ruff + pyright
make typecheck            Run pyright only
make test                 Run pytest

make clean                Remove build artefacts and caches
```
