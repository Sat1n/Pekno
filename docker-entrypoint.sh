#!/bin/sh
set -e

if [ "${RUN_DB_MIGRATIONS:-1}" = "1" ]; then
  echo "[Pekno] Running database migrations..."
  python scripts/smart_migrate.py
else
  echo "[Pekno] Skipping database migrations for this service."
fi

echo "[Pekno] Starting application..."
exec "$@"
