#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export npm_config_cache="${npm_config_cache:-/workspace/.cache/npm}"
export DOCKER_CONFIG="${DOCKER_CONFIG:-$PWD/.local/docker}"
mkdir -p "$DOCKER_CONFIG"
uv venv --allow-existing .venv
uv pip sync --python .venv/bin/python backend/requirements-dev.lock --require-hashes
uv pip install --python .venv/bin/python --no-deps --no-build-isolation -e backend
npm --prefix frontend ci --no-audit --no-fund
python3 scripts/dev_env.py
docker compose up -d --wait db redis
.venv/bin/alembic -c backend/alembic.ini upgrade head
.venv/bin/python -m atlasops.cli seed
npm --prefix frontend run build
