#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_common.sh"
load_pekno_env
enable_hub_dev_reload

echo "Running smart database migrations..."
uv run python scripts/smart_migrate.py

echo "Starting Hub service..."
uv run python hub/main.py
