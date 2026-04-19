#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Pekno development startup

Run these commands in separate terminals:
  ./scripts/start-hub-with-migrate.sh
  ./scripts/start-worker.sh
  ./scripts/start-scheduler.sh
  ./scripts/start-web.sh
EOF
