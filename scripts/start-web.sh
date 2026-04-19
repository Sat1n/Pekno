#!/usr/bin/env bash
set -euo pipefail

web_dir="web"

if [[ ! -d "${web_dir}" ]]; then
  echo "Error: web directory not found" >&2
  exit 1
fi

cd "${web_dir}"

echo "Starting Vue development server..."
npm run dev
