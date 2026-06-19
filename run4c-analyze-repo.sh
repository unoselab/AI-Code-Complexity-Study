#!/usr/bin/env bash
set -euo pipefail

# Analyze cloned Python AI-adopting repositories and save a timestamped log.

REPOS_FILE="${REPOS_FILE:-tmp_adoption_test/data/ai_adopt_repo_python.csv}"
CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_repo_dataset}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_adoption_test/data/python_did_test}"
AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M)}"
LOG_FILE="${LOG_DIR}/run4c_analyze_repo_${RUN_TS}.log"

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run4c: analyze cloned Python AI-adopting repositories" | tee -a "${LOG_FILE}"
echo "Repos file:      ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:       ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:      ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:     ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:   ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Log file:        ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${REPOS_FILE}" ]]; then
  echo "ERROR: repos file not found: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/analyze_repos_v2.py" ]]; then
  echo "ERROR: script not found: proc_scripts/analyze_repos_v2.py" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Run repository history analysis" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python proc_scripts/analyze_repos_v2.py \
  --repos-file "${REPOS_FILE}" \
  --clone-dir "${CLONE_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --aggregation "${AGGREGATION}" \
  --num-processes "${NUM_PROCESSES}" \
  2>&1 | tee -a "${LOG_FILE}"

status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "** Output files" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
find "${OUTPUT_DIR}" -maxdepth 1 -type f -printf "%p\n" | sort | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"

if [[ "${status}" -ne 0 ]]; then
  echo "run4c failed with exit code ${status}" | tee -a "${LOG_FILE}"
  echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${status}"
fi

echo "run4c completed successfully." | tee -a "${LOG_FILE}"
echo "Log saved to: ${LOG_FILE}" | tee -a "${LOG_FILE}"
