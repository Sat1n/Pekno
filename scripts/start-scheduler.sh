#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_common.sh"
load_pekno_env

echo "Running scheduler bootstrap..."
uv run python scripts/scheduler_bootstrap.py

echo "Starting TaskIQ Scheduler..."
uv run taskiq scheduler worker.main:scheduler
