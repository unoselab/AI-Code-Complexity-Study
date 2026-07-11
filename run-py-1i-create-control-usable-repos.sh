#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1i: Create clone-usable control repository sample
# ============================================================
#
#   repo_python/run-py-1h/python_control_clone_status_main_<N>.csv
#   repo_python/run-py-1g/python_matched_control_pairs_main_<N>.csv
#   repo_python/run-py-1g/python_control_repos_to_clone_main_<N>.csv
#
# Main outputs:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#   repo_python/run-py-1i/python_matched_control_pairs_main_clone_usable.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1i/python_control_clone_failed_repos_main.csv
#   repo_python/tmp/run-py-1i/python_matched_control_pairs_main_clone_failed.csv
#   repo_python/tmp/run-py-1i/python_control_pair_coverage_main_clone_usable.csv
#   repo_python/tmp/run-py-1i/python_treatment_lost_all_controls_main.csv
#   repo_python/tmp/run-py-1i/python_control_clone_usable_summary_main.csv
# 
# Usage:
#   bash run-py-1i-create-control-usable-repos.sh
# ============================================================
 
SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi


LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
SAMPLE_VARIANT="${SAMPLE_VARIANT:-main}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()
  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

CLONE_STATUS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1h/python_control_clone_status_${SAMPLE_VARIANT}_[0-9]*.csv"
PAIR_FILE_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_matched_control_pairs_${SAMPLE_VARIANT}_[0-9]*.csv"
CONTROL_REPOS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_control_repos_to_clone_${SAMPLE_VARIANT}_[0-9]*.csv"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-$(resolve_single_input "${CLONE_STATUS_PATTERN}" "clone-status file")}"
PAIR_FILE="${PAIR_FILE:-$(resolve_single_input "${PAIR_FILE_PATTERN}" "matched-pair file")}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-$(resolve_single_input "${CONTROL_REPOS_PATTERN}" "control-repository file")}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_usable_repos_${SAMPLE_VARIANT}.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_usable.csv}"

FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${TMP_DIR}/python_control_clone_failed_repos_${SAMPLE_VARIANT}.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_${SAMPLE_VARIANT}_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${TMP_DIR}/python_treatment_lost_all_controls_${SAMPLE_VARIANT}.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_clone_usable_summary_${SAMPLE_VARIANT}.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated_existing}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: create clone-usable control repository sample" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                  ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                   ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Sample variant:               ${SAMPLE_VARIANT}" | tee -a "${LOG_FILE}"
echo "Main output dir:              ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:             ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:    ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:       ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:        ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:     ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:    ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8c-create-control-usable-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
