#!/usr/bin/env bash
set -euo pipefail

# This script does NOT modify the original data/ts_repos_monthly.csv.
# It writes temporary batch input to:
#   tmp_sonar_batch/data/ts_repos_monthly.csv
#
# Target repos:
#   TheSethRose/Agent-Chat
#   utensils/mcp-nixos
#   nextml-code/pytorch-datastream

AGGREGATION="month"
CLONE_ROOT="../CursorRepos"
TMP_ROOT="tmp_sonar_batch"
TMP_DATA_DIR="${TMP_ROOT}/data"
TMP_TS_FILE="${TMP_DATA_DIR}/ts_repos_monthly.csv"
BATCH_SCRIPT="proc_scripts/run_sonarqube_v2.py"

REPOS=(
  "TheSethRose/Agent-Chat"
  "utensils/mcp-nixos"
  "nextml-code/pytorch-datastream"
)

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env file not found. Run this script from the repository root."
  exit 1
fi

if [[ ! -f "scripts/run_sonarqube.py" ]]; then
  echo "ERROR: scripts/run_sonarqube.py not found. Run this script from the repository root."
  exit 1
fi

set -a
source .env
set +a

if [[ -z "${SONAR_HOST:-}" ]]; then
  echo "ERROR: SONAR_HOST is missing in .env"
  exit 1
fi

if [[ -z "${SONAR_TOKEN:-}" ]]; then
  echo "ERROR: SONAR_TOKEN is missing in .env"
  exit 1
fi

if [[ -z "${SONAR_SCANNER_PATH:-}" ]]; then
  echo "ERROR: SONAR_SCANNER_PATH is missing in .env"
  exit 1
fi

echo "============================================================"
echo "SonarQube small-batch smoke test"
echo "Aggregation:    ${AGGREGATION}"
echo "Clone root:     ${CLONE_ROOT}"
echo "Temp data:      ${TMP_TS_FILE}"
echo "SONAR_HOST:     ${SONAR_HOST}"
echo "Scanner path:   ${SONAR_SCANNER_PATH}"
echo "Repositories:"
for repo in "${REPOS[@]}"; do
  echo "  - ${repo}"
done
echo "============================================================"
echo

echo "Step 1: Create temporary batch time-series input"
mkdir -p "${TMP_DATA_DIR}"

# proc_scripts/test_create_tmp_repo_timeseries_input_batch.py
python proc_scripts/test_create_tmp_repo_timeseries_input_batch.py "${TMP_TS_FILE}" "${REPOS[@]}"
echo

echo "Step 2: Clone missing repositories"
mkdir -p "${CLONE_ROOT}"

for repo in "${REPOS[@]}"; do
  project_key="${repo//\//_}"
  repo_path="${CLONE_ROOT}/${project_key}"

  echo "------------------------------------------------------------"
  echo "Repo:       ${repo}"
  echo "Project:    ${project_key}"
  echo "Repo path:  ${repo_path}"

  if [[ -d "${repo_path}/.git" ]]; then
    echo "Repository already exists."
  else
    echo "Cloning repository..."
    git clone "https://github.com/${repo}.git" "${repo_path}"
  fi

  echo "Repository size:"
  du -sh "${repo_path}" || true

  echo "Latest commits:"
  git -C "${repo_path}" log --oneline -3 || true
done

echo

echo "Step 4: Run small-batch SonarQube pipeline"
python "${BATCH_SCRIPT}" --aggregation "${AGGREGATION}"
echo

# proc_scripts/test_display_metrics.py
echo "Step 5: Show resulting metrics"
python proc_scripts/test_display_metrics.py "${TMP_TS_FILE}"

echo
echo "Step 6: SonarQube Docker memory snapshot"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}" sonarqube || true

echo
echo "SonarQube small-batch smoke test completed successfully."
