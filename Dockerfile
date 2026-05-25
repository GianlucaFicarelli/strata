# ── Stage 1: build frontend ───────────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /strata/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: build backend with uv ───────────────────────────────────────────
FROM python:3.14-slim AS backend-builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.14

WORKDIR /strata/backend
COPY backend/ ./
RUN uv sync --locked --no-editable --extra all

# ── Stage 3: runtime image ────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

LABEL org.opencontainers.image.title="Strata"
LABEL org.opencontainers.image.description="Plugin-based file browser"
LABEL org.opencontainers.image.version="0.1.0"

WORKDIR /strata

# Copy virtualenv from builder
COPY --from=backend-builder /strata/backend/.venv ./backend/.venv

# Copy built frontend into the location FastAPI serves it from
COPY --from=frontend-builder /strata/frontend/dist ./frontend/dist

# Make the venv the default Python
ENV PATH="/strata/backend/.venv/bin:$PATH"

# Runtime configuration — override these in docker-compose.yaml or at runtime.
#
# STRATA_ENCRYPTION_KEY  REQUIRED — 32-byte URL-safe base64 key for AES-256-GCM
#                         field encryption and HMAC download token signing.
#                         Generate: python -c "from cryptography.fernet import Fernet;
#                                   print(Fernet.generate_key().decode())"
#
# STRATA_REDIS_URL       Points to the Redis instance used for session storage.
#                         Default assumes a 'redis' service in the same compose network.
ENV STRATA_LOCAL_ROOT=/data
ENV STRATA_REDIS_URL=redis://redis:6379/0
ENV STRATA_COLLABORA_URL=http://collabora:9980

# Expose data volume
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "strata.main:app", "--host", "0.0.0.0", "--port", "8000"]
