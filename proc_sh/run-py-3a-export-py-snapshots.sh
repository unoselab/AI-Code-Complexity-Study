#!/usr/bin/env bash
set -euo pipefail

RUN_PREFIX="$(basename "$0" | grep -oE '^run-py-[0-9]+[a-z]?')"
LOG_DIR="${LOG_DIR:-logs}"
mkdir -p "${LOG_DIR}"

PYTHONUNBUFFERED=1 python proc_scripts/export_python_snapshots.py "$@" 2>&1 |
  tee "${LOG_DIR}/${RUN_PREFIX}_export_py_snapshots_strict_$(date +%Y%m%d-%H%M%S).log"

