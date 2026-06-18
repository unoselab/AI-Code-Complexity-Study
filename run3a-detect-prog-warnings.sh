#!/usr/bin/env bash
set -euo pipefail

AGGREGATION="month"
CLONE_ROOT="../CursorRepos"
DATA_DIR="tmp_sonar_batch/data"
TS_FILE="${DATA_DIR}/ts_repos_monthly.csv"
MONTHS="${MONTHS:-2026-03,2026-04,2026-05}"

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
echo "Step 2: Run SonarQube on the multi-month input"
echo "------------------------------------------------------------"
python proc_scripts/run_sonarqube_v2.py \
  --aggregation "${AGGREGATION}" \
  --data-dir "${DATA_DIR}"

echo
echo "Step 3: Display results"
echo "------------------------------------------------------------"
python proc_scripts/test_display_metrics.py "${TS_FILE}"

echo
echo "Step 4: SonarQube Docker memory snapshot"
echo "------------------------------------------------------------"
docker stats sonarqube --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}" || true

echo
echo "run3a completed successfully."
