#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7c: Clone JavaScript/TypeScript AI-adopting treatment repos
# ============================================================
# This wrapper calls run7b-detect-ai-adoption-repo.sh in clone mode.
# It writes a timestamped wrapper log under ./logs/.
#
# Typical usage:
#   MAX_CLONES=10 bash run7c-clone-ai-adoption-repo.sh
#   MAX_CLONES=0  bash run7c-clone-ai-adoption-repo.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run7c_clone_ai_adoption_repo_${RUN_TS}.log}"

mkdir -p "${LOG_DIR}"

SKIP_CANDIDATE_SELECTION="${SKIP_CANDIDATE_SELECTION:-true}"
INSPECT_ONLY="${INSPECT_ONLY:-false}"
INSPECT_CLONE="${INSPECT_CLONE:-true}"

OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data}"
OUTPUT_FILE="${OUTPUT_FILE:-tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv}"

CLONE_ROOT="${CLONE_ROOT:-../ai_code_complexity_study_jsts_repo_dataset}"
MAX_CLONES="${MAX_CLONES:-10}"

CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV:-TypeScript,JavaScript}"
CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_status.csv}"
CHECK_OUTPUT_BACKUP="${CHECK_OUTPUT_BACKUP:-${CHECK_OUTPUT_FILE%.csv}_${RUN_TS}.csv}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7c: clone JS/TS AI-adopting treatment repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                 ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Log file:                  ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Skip candidate selection:  ${SKIP_CANDIDATE_SELECTION}" | tee -a "${LOG_FILE}"
echo "Inspect only:              ${INSPECT_ONLY}" | tee -a "${LOG_FILE}"
echo "Inspect clone:             ${INSPECT_CLONE}" | tee -a "${LOG_FILE}"
echo "Output dir:                ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Candidate file:            ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Clone root:                ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Max clones:                ${MAX_CLONES}" | tee -a "${LOG_FILE}"
echo "Check languages CSV:       ${CHECK_LANGUAGES_CSV}" | tee -a "${LOG_FILE}"
echo "Check output file:         ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Check output backup:       ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${OUTPUT_FILE}" ]]; then
  echo "ERROR: candidate file not found: ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "run7b-detect-ai-adoption-repo.sh" ]]; then
  echo "ERROR: run7b-detect-ai-adoption-repo.sh not found." | tee -a "${LOG_FILE}"
  exit 1
fi

set +e
env \
  RUN_TS="${RUN_TS}" \
  LOG_DIR="${LOG_DIR}" \
  SKIP_CANDIDATE_SELECTION="${SKIP_CANDIDATE_SELECTION}" \
  INSPECT_ONLY="${INSPECT_ONLY}" \
  INSPECT_CLONE="${INSPECT_CLONE}" \
  OUTPUT_DIR="${OUTPUT_DIR}" \
  OUTPUT_FILE="${OUTPUT_FILE}" \
  CLONE_ROOT="${CLONE_ROOT}" \
  MAX_CLONES="${MAX_CLONES}" \
  CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV}" \
  CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE}" \
  bash run7b-detect-ai-adoption-repo.sh 2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run7c finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Main log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

if [[ -f "${CHECK_OUTPUT_FILE}" ]]; then
  cp "${CHECK_OUTPUT_FILE}" "${CHECK_OUTPUT_BACKUP}"
  echo "Clone status file: ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
  echo "Clone status backup: ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
fi

echo "============================================================" | tee -a "${LOG_FILE}"

exit "${run_status}"
