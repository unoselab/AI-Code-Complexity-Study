#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1i: Create clone-usable control repository sample
# ============================================================
#
# Input:
#   repo_python/control_clone_status_main.csv
#   repo_python/matched_control_pairs_main.csv
#   repo_python/control_repos_to_clone_main.csv
#
# Outputs:
#   repo_python/control_clone_usable_repos_main.csv
#   repo_python/control_clone_failed_repos_main.csv
#   repo_python/matched_control_pairs_main_clone_usable.csv
#   repo_python/matched_control_pairs_main_clone_failed.csv
#   repo_python/control_pair_coverage_main_clone_usable.csv
#   repo_python/treatment_lost_all_controls_main.csv
#   repo_python/control_clone_usable_summary_main.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1i_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/control_clone_status_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main.csv}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main.csv}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main.csv}"
FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_failed_repos_main.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_usable.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${OUTPUT_DIR}/treatment_lost_all_controls_main.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/control_clone_usable_summary_main.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated_existing}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1i: create clone-usable control repository sample" | tee -a "${LOG_FILE}"
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
echo "Log file:                     ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in "${PY_SCRIPT}" "${CLONE_STATUS_FILE}" "${PAIR_FILE}" "${CONTROL_REPOS_FILE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

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
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${USABLE_CONTROL_FILE}" \
  "${FAILED_CONTROL_FILE}" \
  "${USABLE_PAIR_FILE}" \
  "${DROPPED_PAIR_FILE}" \
  "${COVERAGE_FILE}" \
  "${ZERO_CONTROL_TREATMENT_FILE}" \
  "${SUMMARY_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1i completed successfully." | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:    ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:       ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:        ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8c-create-control-usable-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
