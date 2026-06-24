#!/usr/bin/env bash
set -euo pipefail

# Analyze cloned JavaScript/TypeScript AI-adopting repositories
# and verify adoption timing against event_month.

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-tmp_jsts_test/data/jsts_treatment_clone_status.csv}"
USABLE_REPOS_FILE="${USABLE_REPOS_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_repos.csv}"

REPOS_FILE="${REPOS_FILE:-${USABLE_REPOS_FILE}}"
CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_repo_dataset}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data/jsts_did_test}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
MAX_REPOS="${MAX_REPOS:-0}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M)}"
LOG_FILE="${LOG_DIR}/run7d_analyze_repo_${RUN_TS}.log"

ADOPTION_FILE="${ADOPTION_FILE:-${OUTPUT_DIR}/ai_adoption_dates.csv}"
ADOPTION_MATCH_FILE="${ADOPTION_MATCH_FILE:-${OUTPUT_DIR}/adoption_month_check.csv}"

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7d: analyze cloned JS/TS AI-adopting repositories" | tee -a "${LOG_FILE}"
echo "Clone status file:     ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Usable repos file:     ${USABLE_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Repos file:            ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:             ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:            ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:           ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:         ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:             ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Adoption file:         ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption match file:   ${ADOPTION_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:              ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CLONE_STATUS_FILE}" ]]; then
  echo "ERROR: clone status file not found: ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run7c-clone-ai-adoption-repo.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/create_clone_usable_repos.py" ]]; then
  echo "ERROR: script not found: proc_scripts/create_clone_usable_repos.py" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/analyze_repos_v2.py" ]]; then
  echo "ERROR: script not found: proc_scripts/analyze_repos_v2.py" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/check_time_of_event_and_adoption.py" ]]; then
  echo "ERROR: script not found: proc_scripts/check_time_of_event_and_adoption.py" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Step 0: Create usable cloned repository list" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python proc_scripts/create_clone_usable_repos.py \
  --clone-status-file "${CLONE_STATUS_FILE}" \
  --output-file "${USABLE_REPOS_FILE}" \
  --top-print 30 \
  2>&1 | tee -a "${LOG_FILE}"

if [[ ! -f "${REPOS_FILE}" ]]; then
  echo "ERROR: repos file not found after usable-list creation: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
  exit 1
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

echo | tee -a "${LOG_FILE}"
echo "** Output files" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
find "${OUTPUT_DIR}" -maxdepth 1 -type f -printf "%p\n" | sort | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "run7d completed successfully." | tee -a "${LOG_FILE}"
echo "Log saved to: ${LOG_FILE}" | tee -a "${LOG_FILE}"
