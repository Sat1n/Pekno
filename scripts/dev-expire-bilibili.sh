#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found. Please make sure Docker is installed and running." >&2
  exit 1
fi

container_name="pekno-postgres"
db_user="pekno"
db_name="pekno_iris"

read -r -d '' sql <<'EOF' || true
WITH updated AS (
    UPDATE items
    SET
        retention_days = 1,
        created_at = NOW() - INTERVAL '2 hours',
        updated_at = NOW()
    WHERE source_type = 'bilibili'
    RETURNING id
)
SELECT COUNT(*) AS updated_count FROM updated;
EOF

echo "Marking Bilibili data as immediately expirable..."
docker exec -i "${container_name}" psql -U "${db_user}" -d "${db_name}" -c "${sql}"

echo "Done. Wait for the next TTL heartbeat, or trigger cleanup manually to verify."
