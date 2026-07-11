#!/usr/bin/env bash
set -euo pipefail

AGGREGATION="month"
CLONE_ROOT="../CursorRepos"
DATA_DIR="tmp_sonar_batch/data"
TS_FILE="${DATA_DIR}/ts_repos_monthly.csv"
MONTHS="${MONTHS:-2026-03,2026-04,2026-05}"

WARNINGS_FILE="${DATA_DIR}/sonarqube_warnings.csv"
WARNING_DEFINITIONS_FILE="${DATA_DIR}/sonarqube_warning_definitions.csv"

REPOS=(
  "TheSethRose/Agent-Chat"
  "utensils/mcp-nixos"
  "nextml-code/pytorch-datastream"
)

echo "============================================================"
echo "run3a: multi-month SonarQube smoke test with real Git history"
echo "Aggregation: ${AGGREGATION}"
echo "Clone root:  ${CLONE_ROOT}"
echo "Data dir:    ${DATA_DIR}"
echo "Input CSV:   ${TS_FILE}"
echo "Months:      ${MONTHS}"
echo "Warnings:    ${WARNINGS_FILE}"
echo "Definitions: ${WARNING_DEFINITIONS_FILE}"
echo "Repositories:"
printf '  - %s\n' "${REPOS[@]}"
echo "============================================================"
echo

mkdir -p "${DATA_DIR}"

echo "Step 1: Create historical month input"
echo "------------------------------------------------------------"
python proc_scripts/create_tmp_repo_timeseries_history.py \
  --output "${TS_FILE}" \
  --clone-root "${CLONE_ROOT}" \
  --months "${MONTHS}" \
  "${REPOS[@]}"

echo
echo "Step 2: Run SonarQube aggregate metrics on the multi-month input"
echo "------------------------------------------------------------"
python proc_scripts/run_sonarqube_v2.py \
  --aggregation "${AGGREGATION}" \
  --data-dir "${DATA_DIR}"

echo
echo "Step 3: Collect detailed SonarQube warning records"
echo "------------------------------------------------------------"
python proc_scripts/collect_sonarqube_warnings_v2.py \
  --mode timeseries \
  --data-dir "${DATA_DIR}" \
  --timeseries-file "${TS_FILE}" \
  --warnings-output "${WARNINGS_FILE}" \
  --definitions-output "${WARNING_DEFINITIONS_FILE}" \
  --repos "${REPOS[@]}"

echo
echo "Step 4: Display aggregate metric results"
echo "------------------------------------------------------------"
python proc_scripts/test_display_metrics.py "${TS_FILE}"

echo
echo "Step 5: Show warning output files"
echo "------------------------------------------------------------"
ls -lh "${WARNINGS_FILE}" "${WARNING_DEFINITIONS_FILE}" || true

echo
echo "Step 6: SonarQube Docker memory snapshot"
echo "------------------------------------------------------------"
docker stats sonarqube --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}" || true

echo
echo "run3a completed successfully."
