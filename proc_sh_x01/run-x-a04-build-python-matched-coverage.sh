#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a04 v1: Build matched-control Python coverage
# ============================================================
#
# Purpose:
#   Preserve the original 1:3 treatment-control assignments and determine how
#   many of the three matched controls provide a Python-eligible code state for
#   each valid-event, Python-eligible treatment repo-month.
#
# Control snapshot rule:
#   Use the control eligibility row from the same calendar month when present.
#   Otherwise use the latest eligibility row before the treatment month. Never
#   use a future snapshot. This prior-only as-of lookup is used only for code
#   state and Python eligibility; it does not copy historical activity values.
#
# Main treatment candidates:
#   - dataset_source = treatment
#   - valid event month
#   - python_eligible = 1
#
# Required inputs:
#   repo_x01/run-x-a01/clonedrepo_matching_pairs.csv
#   repo_x01/run-x-a03/repo_month_python_eligibility.csv
#   repo_x01/run-x-a03/panel_event_monthly_python_eligibility.csv
#
# Main outputs:
#   repo_x01/run-x-a04/treatment_month_control_slot_details.csv
#   repo_x01/run-x-a04/treatment_month_control_python_coverage.csv
#   repo_x01/run-x-a04/matched_unique_control_repo_months.csv
#   repo_x01/run-x-a04/control_reuse_summary.csv
#   repo_x01/run-x-a04/stable_event_window_control_coverage.csv
#   repo_x01/run-x-a04/excluded_treatment_months.csv
#   repo_x01/run-x-a04/treatment_month_control_coverage_anomalies.csv
#
# QC output:
#   repo_x01/tmp/run-x-a04/treatment_month_control_coverage_summary.csv
#
# Run:
#   bash proc_sh_x01/run-x-a04-build-python-matched-coverage.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   EVENT_WINDOW_MIN=-6
#   EVENT_WINDOW_MAX=6
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a04"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-python-matched-coverage-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/build_python_matched_coverage.py}"

MATCHING_PAIRS_FILE="${MATCHING_PAIRS_FILE:-repo_x01/run-x-a01/clonedrepo_matching_pairs.csv}"
ELIGIBILITY_FILE="${ELIGIBILITY_FILE:-repo_x01/run-x-a03/repo_month_python_eligibility.csv}"
PANEL_FILE="${PANEL_FILE:-repo_x01/run-x-a03/panel_event_monthly_python_eligibility.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

SLOT_DETAILS_OUTPUT="${SLOT_DETAILS_OUTPUT:-${MAIN_OUTPUT_DIR}/treatment_month_control_slot_details.csv}"
COVERAGE_OUTPUT="${COVERAGE_OUTPUT:-${MAIN_OUTPUT_DIR}/treatment_month_control_python_coverage.csv}"
MATCHED_CONTROL_MONTHS_OUTPUT="${MATCHED_CONTROL_MONTHS_OUTPUT:-${MAIN_OUTPUT_DIR}/matched_unique_control_repo_months.csv}"
CONTROL_REUSE_OUTPUT="${CONTROL_REUSE_OUTPUT:-${MAIN_OUTPUT_DIR}/control_reuse_summary.csv}"
STABLE_COVERAGE_OUTPUT="${STABLE_COVERAGE_OUTPUT:-${MAIN_OUTPUT_DIR}/stable_event_window_control_coverage.csv}"
EXCLUDED_TREATMENT_OUTPUT="${EXCLUDED_TREATMENT_OUTPUT:-${MAIN_OUTPUT_DIR}/excluded_treatment_months.csv}"
ANOMALY_OUTPUT="${ANOMALY_OUTPUT:-${MAIN_OUTPUT_DIR}/treatment_month_control_coverage_anomalies.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/treatment_month_control_coverage_summary.csv}"

EVENT_WINDOW_MIN="${EVENT_WINDOW_MIN:--6}"
EVENT_WINDOW_MAX="${EVENT_WINDOW_MAX:-6}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for integer_value in "${EVENT_WINDOW_MIN}" "${EVENT_WINDOW_MAX}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: EVENT_WINDOW_MIN and EVENT_WINDOW_MAX must be integers." >&2
    exit 1
  fi
done

if (( EVENT_WINDOW_MIN > EVENT_WINDOW_MAX )); then
  echo "ERROR: EVENT_WINDOW_MIN cannot be greater than EVENT_WINDOW_MAX." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${MATCHING_PAIRS_FILE}" \
  "${ELIGIBILITY_FILE}" \
  "${PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_LABEL}: build matched-control Python coverage"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Matching pairs:              ${MATCHING_PAIRS_FILE}"
  echo "Eligibility input:           ${ELIGIBILITY_FILE}"
  echo "Enriched panel input:        ${PANEL_FILE}"
  echo "Slot details output:         ${SLOT_DETAILS_OUTPUT}"
  echo "Coverage output:             ${COVERAGE_OUTPUT}"
  echo "Matched control months:      ${MATCHED_CONTROL_MONTHS_OUTPUT}"
  echo "Control reuse output:        ${CONTROL_REUSE_OUTPUT}"
  echo "Stable coverage output:      ${STABLE_COVERAGE_OUTPUT}"
  echo "Excluded treatment output:   ${EXCLUDED_TREATMENT_OUTPUT}"
  echo "Anomaly output:              ${ANOMALY_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Event window:                ${EVENT_WINDOW_MIN}:${EVENT_WINDOW_MAX}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --matching-pairs-file "${MATCHING_PAIRS_FILE}"
  --eligibility-file "${ELIGIBILITY_FILE}"
  --panel-file "${PANEL_FILE}"
  --slot-details-output "${SLOT_DETAILS_OUTPUT}"
  --coverage-output "${COVERAGE_OUTPUT}"
  --matched-control-months-output "${MATCHED_CONTROL_MONTHS_OUTPUT}"
  --control-reuse-output "${CONTROL_REUSE_OUTPUT}"
  --stable-coverage-output "${STABLE_COVERAGE_OUTPUT}"
  --excluded-treatment-output "${EXCLUDED_TREATMENT_OUTPUT}"
  --anomaly-output "${ANOMALY_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --event-window-min "${EVENT_WINDOW_MIN}"
  --event-window-max "${EVENT_WINDOW_MAX}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 1: Build original-matching Python coverage"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${SLOT_DETAILS_OUTPUT}" \
  "${COVERAGE_OUTPUT}" \
  "${MATCHED_CONTROL_MONTHS_OUTPUT}" \
  "${CONTROL_REUSE_OUTPUT}" \
  "${STABLE_COVERAGE_OUTPUT}" \
  "${EXCLUDED_TREATMENT_OUTPUT}" \
  "${ANOMALY_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

for nonempty_output in \
  "${SLOT_DETAILS_OUTPUT}" \
  "${COVERAGE_OUTPUT}" \
  "${MATCHED_CONTROL_MONTHS_OUTPUT}" \
  "${CONTROL_REUSE_OUTPUT}" \
  "${STABLE_COVERAGE_OUTPUT}" \
  "${EXCLUDED_TREATMENT_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -s "${nonempty_output}" ]]; then
    echo "ERROR: expected non-empty output was not created: ${nonempty_output}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SLOT_DETAILS_OUTPUT}" \
    "${COVERAGE_OUTPUT}" \
    "${MATCHED_CONTROL_MONTHS_OUTPUT}" \
    "${CONTROL_REUSE_OUTPUT}" \
    "${STABLE_COVERAGE_OUTPUT}" \
    "${EXCLUDED_TREATMENT_OUTPUT}" \
    "${ANOMALY_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Coverage output:             ${COVERAGE_OUTPUT}"
  echo "Slot details output:         ${SLOT_DETAILS_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   review coverage before building run-x-a05 velocity DiD input"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
