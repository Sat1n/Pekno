#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_common.sh"
load_pekno_env

accelerator="${PEKNO_ACCELERATOR:-cpu}"
compose_files=(-f docker-compose.yaml)

case "${accelerator}" in
  cpu)
    ;;
  cuda)
    compose_files+=(-f docker-compose.accel.cuda.yaml)
    ;;
  *)
    echo "Unsupported PEKNO_ACCELERATOR: ${accelerator}" >&2
    echo "Supported values: cpu, cuda" >&2
    exit 1
    ;;
esac

echo "Using accelerator profile: ${accelerator}"
echo "Running: docker compose ${compose_files[*]} $*"

docker compose "${compose_files[@]}" "$@"
