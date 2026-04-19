#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_common.sh"
load_pekno_env

echo "Starting Worker service..."
uv run taskiq worker worker.main:broker
