#!/usr/bin/env bash
set -euo pipefail

# Generic one-repo SonarQube smoke test.
#
# Default repo:
#   ericzakariasson/uber-eats-mcp-server
#
# Example:
#   ./run2a-sonarqube-smoke-test.sh
#   ./run2a-sonarqube-smoke-test.sh --repo OWNER/REPO
#   ./run2a-sonarqube-smoke-test.sh --repo OWNER/REPO --month 2025-03
#
# This script does NOT modify the original data/ts_repos_monthly.csv.
# It writes a temporary one-repo input to:
#   tmp_sonar_one_repo/data/ts_repos_monthly.csv
#
# It also creates a safe patched copy:
#   proc_scripts/run_sonarqube_one_repo_test.py

REPO_NAME="ericzakariasson/uber-eats-mcp-server"
AGGREGATION="month"
TIME_PERIOD=""
CLONE_ROOT="../CursorRepos"
RUN_INFRA_TESTS="1"

usage() {
  cat <<'USAGE'
Usage:
  ./run2a-sonarqube-smoke-test.sh [options]

Options:
  --repo OWNER/REPO       GitHub repository name. Default: ericzakariasson/uber-eats-mcp-server
  --aggregation month     Aggregation level. Default: month
  --month YYYY-MM         Optional month to select from ts_repos_monthly.csv
  --clone-root PATH       Clone root directory. Default: ../CursorRepos
  --run-infra-tests       Also run connection, tiny scan, metrics, and issues tests
  -h, --help              Show this help

Examples:
  ./run2a-sonarqube-smoke-test.sh
  ./run2a-sonarqube-smoke-test.sh --repo ericzakariasson/uber-eats-mcp-server
  ./run2a-sonarqube-smoke-test.sh --repo OWNER/REPO --month 2025-03
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_NAME="$2"
      shift 2
      ;;
    --aggregation)
      AGGREGATION="$2"
      shift 2
      ;;
    --month)
      TIME_PERIOD="$2"
      shift 2
      ;;
    --clone-root)
      CLONE_ROOT="$2"
      shift 2
      ;;
    --run-infra-tests)
      RUN_INFRA_TESTS="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "${AGGREGATION}" != "month" ]]; then
  echo "ERROR: This smoke-test wrapper currently supports --aggregation month only."
  exit 1
fi

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

PROJECT_KEY="${REPO_NAME//\//_}"
REPO_PATH="${CLONE_ROOT}/${PROJECT_KEY}"

echo "============================================================"
echo "SonarQube one-repo smoke test"
echo "Repo name:      ${REPO_NAME}"
echo "Project key:    ${PROJECT_KEY}"
echo "Repo path:      ${REPO_PATH}"
echo "Aggregation:    ${AGGREGATION}"
echo "Month filter:   ${TIME_PERIOD:-latest available month}"
echo "SONAR_HOST:     ${SONAR_HOST}"
echo "Scanner path:   ${SONAR_SCANNER_PATH}"
echo "============================================================"
echo

if [[ "${RUN_INFRA_TESTS}" == "1" ]]; then
  echo "Step 1: SonarQube connection test"
  python proc_scripts/test_sonarqube_connection.py
  echo

  echo "Step 2: Tiny project scan test"
  python proc_scripts/test_sonarqube_scan.py
  echo

  echo "Step 3: Tiny project metrics API test"
  python proc_scripts/test_sonarqube_metrics.py
  echo

  echo "Step 4: Tiny project issues API test"
  python proc_scripts/test_sonarqube_tiny_issues.py
  echo

  echo "TEST: RUN_INFRA_TESTS"
  exit 0

fi

echo "Step 5: Check or clone repository"
mkdir -p "${CLONE_ROOT}"

if [[ -d "${REPO_PATH}/.git" ]]; then
  echo "Repository already exists: ${REPO_PATH}"
else
  echo "Cloning repository..."
  git clone "https://github.com/${REPO_NAME}.git" "${REPO_PATH}"
fi

echo
echo "Repository size:"
du -sh "${REPO_PATH}" || true

echo
echo "Latest commits:"
git -C "${REPO_PATH}" log --oneline -5 || true
echo

# proc_scripts/test_create_tmp_repo_timeseries_input.py
echo "Step 6: Create temporary one-repo time-series input"
python proc_scripts/test_create_tmp_repo_timeseries_input.py "${REPO_NAME}" "${AGGREGATION}" "${TIME_PERIOD}"
echo

echo "Step 7: Create patched one-repo copy of run_sonarqube.py"
# cp scripts/run_sonarqube.py proc_scripts/run_sonarqube_one_repo_test.py

# python - <<'PY'
# from pathlib import Path
# import re

# p = Path("proc_scripts/run_sonarqube_one_repo_test.py")
# s = p.read_text()

# # Use temporary one-repo data directory instead of the full data directory.
# s = re.sub(
#     r'DATA_DIR\s*=\s*SCRIPT_DIR\.parent\s*/\s*"data"',
#     'DATA_DIR = SCRIPT_DIR.parent / "tmp_sonar_one_repo" / "data"',
#     s,
# )

# # Use one process for the smoke test.
# s = re.sub(
#     r'NUM_PROCESSES\s*=\s*\d+.*',
#     'NUM_PROCESSES = 1  # one-repo smoke test',
#     s,
# )

# # Use SonarQube token basic authentication for API requests.
# s = s.replace(
#     'headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}',
#     'auth = (SONAR_TOKEN, "")',
# )

# s = s.replace(
#     'requests.get(url, headers=headers, params=params)',
#     'requests.get(url, auth=auth, params=params)',
# )

# p.write_text(s)

# print("Patched:", p)
# PY

echo
echo "Patch check:"
grep -n "DATA_DIR\|NUM_PROCESSES\|Authorization\|auth =\|requests.get" proc_scripts/run_sonarqube_one_repo_test.py
echo

echo "Step 8: Run one-repo SonarQube pipeline"
python proc_scripts/run_sonarqube_one_repo_test.py --aggregation "${AGGREGATION}"
echo

echo "Step 9: Show resulting metrics"
python - "${AGGREGATION}" <<'PY'
import sys
from pathlib import Path
import pandas as pd

aggregation = sys.argv[1]
path = Path("tmp_sonar_one_repo/data") / f"ts_repos_{aggregation}ly.csv"

df = pd.read_csv(path)

if {"bugs", "vulnerabilities", "code_smells"}.issubset(df.columns):
    df["static_analysis_warnings"] = (
        df["bugs"].fillna(0)
        + df["vulnerabilities"].fillna(0)
        + df["code_smells"].fillna(0)
    )

cols = [
    "repo_name",
    aggregation,
    "latest_commit",
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "static_analysis_warnings",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "software_quality_maintainability_remediation_effort",
    "technical_debt",
]

cols = [c for c in cols if c in df.columns]
print(df[cols].to_string(index=False))
PY

echo
echo "SonarQube one-repo smoke test completed successfully."
