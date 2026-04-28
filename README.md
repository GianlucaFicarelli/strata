# Strata

A plugin-based file browser with swappable storage backends.

## Architecture

```
strata/
├── backend/
│   ├── main.py                          # FastAPI app — wires everything together
│   ├── pyproject.toml                   # Python dependencies (managed by uv)
│   ├── core/
│   │   ├── files.py                     # Generic file API (thin HTTP layer only)
│   │   └── storage/
│   │       ├── base.py                  # StorageBackend ABC + FileEntry model
│   │       ├── local.py                 # Built-in local filesystem backend
│   │       └── registry.py             # Backend registry + backend_dep()
│   ├── plugins/
│   │   ├── base.py                      # BackendPlugin ABC
│   │   └── loader.py                    # Auto-discovery at startup
│   └── plugins_enabled/                 # Drop plugins here
│       ├── image_preview/               # Hybrid: thumbnail endpoint + frontend previewer
│       ├── s3_backend/                  # Pure storage: S3 via ?backend=s3
│       └── collabora/                   # Hybrid: WOPI host + iframe editor frontend
├── frontend/
│   └── src/
│       ├── App.jsx                      # Shell: layout, routing, plugin loader
│       ├── plugin-api/
│       │   ├── registry.js              # Extension point registry + loadPlugins()
│       │   └── hooks.js                 # React hooks: usePreviewer, useFileActions, …
│       ├── shell/
│       │   ├── Sidebar.jsx
│       │   ├── FileBrowser.jsx          # File list with backend picker
│       │   └── FilePreview.jsx          # Preview modal (plugin-aware)
│       └── core-plugins/api.js          # fetch wrappers — all pass ?backend=<id>
├── Dockerfile                           # Multi-stage: node build → uv install → runtime
├── docker-compose.yaml                  # Strata + optional Collabora Online
├── Makefile                             # Dev, build, and Docker targets
└── .env.example                         # Copy to .env and fill in values
```

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env          # edit STRATA_LOCAL_ROOT etc.
make docker-build
make docker-up                # Strata at http://localhost:8000

# To include Collabora Online:
make docker-up-collabora      # also starts collabora at :9980
```

### Local development (two terminals)

```bash
make install                  # uv venv + npm install

# Terminal 1
make dev-backend              # FastAPI on :8000 with --reload

# Terminal 2
make dev-frontend             # Vite on :5173, proxies /api → :8000
```

Open http://localhost:5173

## Plugin types

| Type | Example plugins | Has backend routes? | Has frontend module? |
|---|---|:---:|:---:|
| Pure storage | `s3_backend` | ✗ | ✗ |
| Pure frontend | themes, keyboard shortcuts | ✗ | ✓ |
| Hybrid — preview | `image_preview` | ✓ | ✓ |
| Hybrid — editor | `collabora` | ✓ (WOPI host) | ✓ (iframe) |

## Writing a plugin

### 1. Create a Python package under `backend/plugins_enabled/myplugin/`

```python
# backend/plugins_enabled/myplugin/__init__.py
from fastapi import APIRouter
from plugins.base import BackendPlugin

router = APIRouter(prefix="/api/plugins/myplugin")

@router.get("/hello")
def hello() -> dict:
    return {"message": "Hello from myplugin!"}

class MyPlugin(BackendPlugin):
    id = "myplugin"
    name = "My Plugin"
    version = "0.1.0"
    description = "Does something useful."
    handles = [".xyz"]           # file extensions this plugin handles

    def get_router(self):
        return router

    def get_capabilities(self):
        return ["preview"]

plugin = MyPlugin()
```

### 2. Add a frontend ES module (optional)

```
backend/plugins_enabled/myplugin/frontend/main.js
```

FastAPI serves this at `/api/plugins/myplugin/assets/main.js`.

```js
export function register(registry) {
  registry.previewers.push({
    id: "myplugin",
    canHandle: (file) => file.name.endsWith(".xyz"),
    component: ({ file, backend }) => { /* React component */ },
  });
}
```

### 3. Restart — plugin is auto-discovered

No rebuild of the core app required.

## Extension points

| Registry key | Purpose |
|---|---|
| `previewers` | Render file content in the preview modal |
| `fileActions` | Right-click / toolbar actions on files |
| `sidebarItems` | Extra entries in the left navigation sidebar |
| `routes` | Entirely new pages in the frontend app |
| `storageBackends` | (Informational) list of storage backends |

## Makefile targets

```
make help               Show all targets
make install            Install Python + Node dependencies
make dev                Run both servers in parallel
make build              Build the frontend for production
make docker-build       Build the Docker image
make docker-up          Start Strata only
make docker-up-collabora Start Strata + Collabora Online
make lint               Run ruff linter
make typecheck          Run pyright
make test               Run pytest
make clean              Remove build artefacts
```
