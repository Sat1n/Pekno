#!/usr/bin/env bash

set -euo pipefail

load_pekno_env() {
  local env_file="${1:-.env}"

  export PYTHONPATH="."

  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
    echo "✓ Loaded .env configuration file"
  fi
}

enable_hub_dev_reload() {
  export UVICORN_RELOAD="${UVICORN_RELOAD:-true}"
  echo "✓ UVICORN_RELOAD=${UVICORN_RELOAD}"
}
