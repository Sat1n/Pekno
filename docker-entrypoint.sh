#!/bin/sh
set -e

echo "[Pekno] Running database migrations..."
python scripts/smart_migrate.py

echo "[Pekno] Starting application..."
exec "$@"
