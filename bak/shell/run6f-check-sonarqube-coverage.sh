#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/run6f-check-sonarqube-coverage-${TS}.log"

python proc_scripts/check-sonarqube-coverage.py 2>&1 | tee "${LOG_FILE}"

echo "Saved coverage log to ${LOG_FILE}"
