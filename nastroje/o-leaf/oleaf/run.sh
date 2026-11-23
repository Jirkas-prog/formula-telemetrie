#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${OLEAF_CONFIG_DIR:-/config}" "${OLEAF_RUNTIME_DIR:-/data}"
exec node /app/server.js

