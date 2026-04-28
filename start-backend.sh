#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
# Optional: set the root directory the file browser exposes
export STRATA_ROOT="${STRATA_ROOT:-$HOME}"
echo "→ Serving files from: $STRATA_ROOT"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
