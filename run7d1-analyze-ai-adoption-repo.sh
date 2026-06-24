#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7d1: Analyze cloned JS/TS AI-adopting treatment repositories
# ============================================================
# This script runs repository-history analysis on cloned treatment
# repositories and compares git-detected adoption_month with event_month.
#
# For the current Figure 7 JS/TS treatment pipeline, run this with:
#
#   REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
#   USABLE_REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
#   SKIP_USABLE_REPO_CREATION=true \
#   NUM_PROCESSES=2 \
#   bash run7d1-analyze-ai-adoption-repo.sh
# ============================================================

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-tmp_jsts_test/data/jsts_treatment_clone_status.csv}"

USABLE_REPOS_FILE="${USABLE_REPOS_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv}"
REPOS_FILE="${REPOS_FILE:-${USABLE_REPOS_FILE}}"

CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_repo_dataset}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data/jsts_did_test}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
MAX_REPOS="${MAX_REPOS:-0}"

SKIP_USABLE_REPO_CREATION="${SKIP_USABLE_REPO_CREATION:-false}"
REQUIRE_EVENT_MONTH="${REQUIRE_EVENT_MONTH:-true}"
SKIP_ADOPTION_CHECK="${SKIP_ADOPTION_CHECK:-false}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run7d_analyze_repo_${RUN_TS}.log}"

ADOPTION_FILE="${ADOPTION_FILE:-${OUTPUT_DIR}/ai_adoption_dates.csv}"
ADOPTION_MATCH_FILE="${ADOPTION_MATCH_FILE:-${OUTPUT_DIR}/adoption_month_check.csv}"

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7d: analyze cloned JS/TS AI-adopting treatment repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                  ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Clone status file:          ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Usable repos file:          ${USABLE_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Repos file:                 ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:                  ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:                 ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:                ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:              ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:                  ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Skip usable repo creation:  ${SKIP_USABLE_REPO_CREATION}" | tee -a "${LOG_FILE}"
echo "Require event_month:        ${REQUIRE_EVENT_MONTH}" | tee -a "${LOG_FILE}"
echo "Skip adoption check:        ${SKIP_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
echo "Adoption file:              ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption match file:        ${ADOPTION_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:                   ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/analyze_repos_v2.py" ]]; then
  echo "ERROR: script not found: proc_scripts/analyze_repos_v2.py" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ "${SKIP_ADOPTION_CHECK}" != "true" ]]; then
  if [[ ! -f "proc_scripts/check_time_of_event_and_adoption.py" ]]; then
    echo "ERROR: script not found: proc_scripts/check_time_of_event_and_adoption.py" | tee -a "${LOG_FILE}"
    exit 1
  fi
fi

echo "** Step 0: Resolve repository input file" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

if [[ "${SKIP_USABLE_REPO_CREATION}" == "true" ]]; then
  echo "Skipping usable repo creation." | tee -a "${LOG_FILE}"
  echo "Using existing repos file: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
else
  if [[ ! -f "${CLONE_STATUS_FILE}" ]]; then
    echo "ERROR: clone status file not found: ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
    echo "Run run7c1-clone-ai-adoption-repo.sh first." | tee -a "${LOG_FILE}"
    exit 1
  fi

  if [[ ! -f "proc_scripts/create_clone_usable_repos.py" ]]; then
    echo "ERROR: script not found: proc_scripts/create_clone_usable_repos.py" | tee -a "${LOG_FILE}"
    exit 1
  fi

  echo "Creating usable cloned repository list from clone status file." | tee -a "${LOG_FILE}"

  python proc_scripts/create_clone_usable_repos.py \
    --clone-status-file "${CLONE_STATUS_FILE}" \
    --output-file "${USABLE_REPOS_FILE}" \
    --top-print 30 \
    2>&1 | tee -a "${LOG_FILE}"
fi

if [[ ! -f "${REPOS_FILE}" ]]; then
  echo "ERROR: repos file not found: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo | tee -a "${LOG_FILE}"
echo "** Step 0b: Validate repository input file" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python - <<PY 2>&1 | tee -a "${LOG_FILE}"
from pathlib import Path
import pandas as pd

path = Path("${REPOS_FILE}")
require_event_month = "${REQUIRE_EVENT_MONTH}".lower() == "true"

df = pd.read_csv(path)

print("Repos file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique() if "repo_name" in df.columns else "(repo_name column missing)")
print("Columns:", ", ".join(df.columns.tolist()))
print()

if "repo_name" not in df.columns:
    raise SystemExit("ERROR: repos file must contain repo_name column.")

if "repo_primary_language" in df.columns:
    print("Language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().to_string())
    print()

if "status" in df.columns:
    print("Clone status counts:")
    print(df["status"].fillna("(missing)").value_counts().to_string())
    print()

if "event_month" in df.columns:
    missing_event = int(df["event_month"].isna().sum())
    print("Rows with event_month:", int(df["event_month"].notna().sum()))
    print("Rows missing event_month:", missing_event)
    print()

    if require_event_month and missing_event > 0:
        raise SystemExit(f"ERROR: event_month is required, but {missing_event} rows are missing it.")
else:
    print("event_month column: missing")
    print()
    if require_event_month:
        raise SystemExit("ERROR: event_month column is required but missing.")

if len(df) == 0:
    raise SystemExit("ERROR: repos file has zero rows.")
PY

validate_status=${PIPESTATUS[0]}
set -e

if [[ "${validate_status}" -ne 0 ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "run7d failed during input validation with exit code ${validate_status}" | tee -a "${LOG_FILE}"
  echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${validate_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Step 1: Run repository history analysis" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

cmd=(
  python proc_scripts/analyze_repos_v2.py
  --repos-file "${REPOS_FILE}"
  --clone-dir "${CLONE_DIR}"
  --output-dir "${OUTPUT_DIR}"
  --aggregation "${AGGREGATION}"
  --num-processes "${NUM_PROCESSES}"
)

if [[ "${MAX_REPOS}" != "0" ]]; then
  cmd+=(--max-repos "${MAX_REPOS}")
fi

printf "Command:" | tee -a "${LOG_FILE}"
printf " %q" "${cmd[@]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

set +e
"${cmd[@]}" 2>&1 | tee -a "${LOG_FILE}"
analyze_status=${PIPESTATUS[0]}
set -e

if [[ "${analyze_status}" -ne 0 ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "run7d failed during repository history analysis with exit code ${analyze_status}" | tee -a "${LOG_FILE}"
  echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${analyze_status}"
fi

if [[ "${SKIP_ADOPTION_CHECK}" == "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Adoption month check skipped" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
else
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Compare event_month and git-detected adoption_month" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  if [[ ! -f "${ADOPTION_FILE}" ]]; then
    echo "ERROR: adoption file not found after analysis: ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
    exit 1
  fi

  set +e
  python proc_scripts/check_time_of_event_and_adoption.py \
    --candidate-file "${REPOS_FILE}" \
    --adoption-file "${ADOPTION_FILE}" \
    --output-match-file "${ADOPTION_MATCH_FILE}" \
    2>&1 | tee -a "${LOG_FILE}"

  check_status=${PIPESTATUS[0]}
  set -e

  if [[ "${check_status}" -ne 0 ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "run7d failed during event/adoption month check with exit code ${check_status}" | tee -a "${LOG_FILE}"
    echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
    exit "${check_status}"
  fi
fi

echo | tee -a "${LOG_FILE}"
echo "** Output files" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
find "${OUTPUT_DIR}" -maxdepth 1 -type f -printf "%p\n" | sort | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run7d completed successfully." | tee -a "${LOG_FILE}"
echo "Log saved to: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
