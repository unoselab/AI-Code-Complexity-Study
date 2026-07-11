#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run8c: Create usable JS/TS control repository sample
# ============================================================
# This wrapper calls proc_scripts/create_control_usable_repos.py.
# The Python script performs all data processing.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8c_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-tmp_jsts_test/data/jsts_control_clone_status_main_398.csv}"
PAIR_FILE="${PAIR_FILE:-tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${OUTPUT_DIR}/jsts_control_clone_usable_repos_main_398.csv}"
FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${OUTPUT_DIR}/jsts_control_clone_failed_repos_main_398.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${OUTPUT_DIR}/jsts_matched_control_pairs_main_398_clone_usable.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${OUTPUT_DIR}/jsts_matched_control_pairs_main_398_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/jsts_control_pair_coverage_main_398_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${OUTPUT_DIR}/jsts_treatment_repos_lost_all_controls_main_398.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/jsts_control_clone_usable_summary_main_398.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run8c: create usable JS/TS control repository sample" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Clone status file:            ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Pair file:                    ${PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Control repos file:           ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Usable statuses:              ${USABLE_STATUSES}" | tee -a "${LOG_FILE}"
echo "Usable control file:          ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Failed control file:          ${FAILED_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:             ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Dropped pair file:            ${DROPPED_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:                ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Zero-control treatment file:  ${ZERO_CONTROL_TREATMENT_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:                 ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Fail if zero control:         ${FAIL_IF_ZERO_CONTROL}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

CMD=(
  python "${PY_SCRIPT}"
  --clone-status-file "${CLONE_STATUS_FILE}"
  --pair-file "${PAIR_FILE}"
  --control-repos-file "${CONTROL_REPOS_FILE}"
  --usable-control-file "${USABLE_CONTROL_FILE}"
  --failed-control-file "${FAILED_CONTROL_FILE}"
  --usable-pair-file "${USABLE_PAIR_FILE}"
  --dropped-pair-file "${DROPPED_PAIR_FILE}"
  --coverage-file "${COVERAGE_FILE}"
  --zero-control-treatment-file "${ZERO_CONTROL_TREATMENT_FILE}"
  --summary-file "${SUMMARY_FILE}"
  --usable-statuses "${USABLE_STATUSES}"
)

if [[ "${FAIL_IF_ZERO_CONTROL}" == "true" ]]; then
  CMD+=(--fail-if-zero-control)
fi

echo "** Running Python script" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run8c completed successfully." | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file: ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file: ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
