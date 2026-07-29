#!/usr/bin/env bash
set -euo pipefail

# run-py-7k: Borusyak DiD sensitivity analysis for positive repository-months
# containing AGC-like regular module functions and/or synchronous class methods.
#
# This wrapper was adapted from the run-py-7h wrapper. It is independent and
# does not call run-py-7h or another analysis wrapper.
#
# Inputs:
#   repo_python/run-py-7j/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_and_class_method_agc_unique_body_positive_outcome_parse_clean.csv
#     regular_module_function_and_class_method_agc_unique_body_rankify_audit.csv
#     qc/regular_module_function_and_class_method_agc_unique_body_did_input_checks.csv
#   proc_r/diff_in_diff_borusyak_helpers.R
#   proc_r/did_regfun_classmethod_agc_uniquebody_positive_months.R
#
# Outputs:
#   repo_python/run-py-7k/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#     positive_outcome_months_only/
#
# Important interpretation:
#   The run-py-7j input excludes repository-months with a realized combined
#   outcome of zero. This is a selected-sample sensitivity analysis and must
#   not replace a zero-inclusive causal DiD model.
#
# Usage:
#   OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7k-did-regfun-classmethod-agc-uniquebody-positive-months-borusyak.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_r/did_regfun_classmethod_agc_uniquebody_positive_months.R}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"

RUN7J_ROOT="${RUN7J_ROOT:-repo_python/run-py-7j/strict/specifications/${SPECIFICATION_NAME}}"
PANEL_PATH="${PANEL_PATH:-${RUN7J_ROOT}/panel_event_monthly_regular_module_function_and_class_method_agc_unique_body_positive_outcome_parse_clean.csv}"
RANKIFY_AUDIT_PATH="${RANKIFY_AUDIT_PATH:-${RUN7J_ROOT}/regular_module_function_and_class_method_agc_unique_body_rankify_audit.csv}"
RUN7J_CHECKS_PATH="${RUN7J_CHECKS_PATH:-${RUN7J_ROOT}/qc/regular_module_function_and_class_method_agc_unique_body_did_input_checks.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7k/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/positive_outcome_months_only}"

MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT:-202408}"
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT:-202503}"
HORIZON_MIN="${HORIZON_MIN:--6}"
HORIZON_MAX="${HORIZON_MAX:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-7k}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7k-regfun-classmethod-positive-agc-months-${SPECIFICATION_NAME}-${RUN_TS}.log}"

PREFIX="borusyak_regfun_classmethod_agc_uniquebody_positive_months"
STATIC_FILE="${OUT_DIR}/${PREFIX}_static_effects.csv"
DYNAMIC_FILE="${OUT_DIR}/${PREFIX}_dynamic_effects.csv"
SAMPLE_FILE="${OUT_DIR}/${PREFIX}_sample_summary.csv"
FILTER_FILE="${OUT_DIR}/${PREFIX}_filter_summary.csv"
EVENT_TIME_FILE="${OUT_DIR}/${PREFIX}_event_time_counts.csv"
RANKIFY_FILE="${OUT_DIR}/${PREFIX}_rankify_audit.csv"
VALIDATION_FILE="${OUT_DIR}/${PREFIX}_validation.csv"
METADATA_FILE="${OUT_DIR}/${PREFIX}_metadata.csv"
ERROR_FILE="${OUT_DIR}/${PREFIX}_model_errors.csv"
STATUS_FILE="${OUT_DIR}/${PREFIX}_status.txt"

case "${OVERWRITE_OUTPUT}" in
  0|1) ;;
  *)
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
    exit 1
    ;;
esac

for required_file in \
  "${R_SCRIPT}" \
  "${HELPER_FILE}" \
  "${PANEL_PATH}" \
  "${RANKIFY_AUDIT_PATH}" \
  "${RUN7J_CHECKS_PATH}"; do
  if [[ ! -s "${required_file}" ]]; then
    echo "ERROR: Required file is missing or empty: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript command not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

if [[ -d "${OUT_DIR}" ]]; then
  if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    rm -rf "${OUT_DIR}"
  else
    echo "ERROR: Output directory exists and OVERWRITE_OUTPUT=0: ${OUT_DIR}" >&2
    exit 1
  fi
fi

mkdir -p "${OUT_DIR}" "${LOG_DIR}"

start_epoch="$(date +%s)"
start_display="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-7k: module-function + class-method positive-outcome DiD sensitivity"
  echo "Started:                    ${start_display}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Rscript:                    $(command -v "${RSCRIPT_BIN}")"
  echo "R version:                  $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
  echo "R script:                   ${R_SCRIPT}"
  echo "R script SHA:               $(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
  echo "Helper:                     ${HELPER_FILE}"
  echo "Helper SHA:                 $(sha256sum "${HELPER_FILE}" | awk '{print $1}')"
  echo "Input panel:                ${PANEL_PATH}"
  echo "Input panel SHA:            $(sha256sum "${PANEL_PATH}" | awk '{print $1}')"
  echo "Rankify audit:              ${RANKIFY_AUDIT_PATH}"
  echo "run-py-7j checks:           ${RUN7J_CHECKS_PATH}"
  echo "Output directory:           ${OUT_DIR}"
  echo "Included function kinds:    module_function, method"
  echo "Excluded function kinds:    async and nested variants"
  echo "Sample restriction:         outcome > 0"
  echo "Interpretation:             supplementary selected-sample sensitivity"
  echo "Causal primary use:         NO"
  echo "NCLOC specification:        ${NCLOC_SPEC}"
  echo "Time mode:                  ${TIME_MODE}"
  echo "Treatment cohorts:          ${MIN_TREATMENT_COHORT}-${MAX_TREATMENT_COHORT}"
  echo "Dynamic horizon:            ${HORIZON_MIN}:${HORIZON_MAX}"
  echo "Pretrend periods:           ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"
  echo

  PROJECT_ROOT="${PROJECT_ROOT}" \
  PANEL_PATH="${PANEL_PATH}" \
  RANKIFY_AUDIT_PATH="${RANKIFY_AUDIT_PATH}" \
  RUN7J_CHECKS_PATH="${RUN7J_CHECKS_PATH}" \
  HELPER_FILE="${HELPER_FILE}" \
  OUT_DIR="${OUT_DIR}" \
  NCLOC_SPEC="${NCLOC_SPEC}" \
  TIME_MODE="${TIME_MODE}" \
  MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT}" \
  MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT}" \
  HORIZON_MIN="${HORIZON_MIN}" \
  HORIZON_MAX="${HORIZON_MAX}" \
  PRETREND_MIN="${PRETREND_MIN}" \
  PRETREND_MAX="${PRETREND_MAX}" \
  "${RSCRIPT_BIN}" "${R_SCRIPT}"

  for expected_file in \
    "${STATIC_FILE}" \
    "${DYNAMIC_FILE}" \
    "${SAMPLE_FILE}" \
    "${FILTER_FILE}" \
    "${EVENT_TIME_FILE}" \
    "${RANKIFY_FILE}" \
    "${VALIDATION_FILE}" \
    "${METADATA_FILE}" \
    "${ERROR_FILE}" \
    "${STATUS_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
      exit 1
    fi
  done

  if ! grep -Fxq "status=PASS" "${STATUS_FILE}"; then
    echo "ERROR: Analysis status is not PASS: ${STATUS_FILE}" >&2
    cat "${STATUS_FILE}" >&2
    exit 1
  fi

  if ! grep -Fxq "included_function_kinds=module_function;method" "${STATUS_FILE}"; then
    echo "ERROR: Combined function-scope guard is missing." >&2
    exit 1
  fi

  if ! grep -Fxq "causal_interpretation_allowed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Selected-sample interpretation guard is missing." >&2
    exit 1
  fi

  echo
  echo "================================================================================"
  echo "run-py-7k PASS"
  echo "Static result:              ${STATIC_FILE}"
  echo "Dynamic result:             ${DYNAMIC_FILE}"
  echo "Sample summary:             ${SAMPLE_FILE}"
  echo "Filter summary:             ${FILTER_FILE}"
  echo "Event-time counts:          ${EVENT_TIME_FILE}"
  echo "Rankify audit:              ${RANKIFY_FILE}"
  echo "Validation:                 ${VALIDATION_FILE}"
  echo "Metadata:                   ${METADATA_FILE}"
  echo "Model errors:               ${ERROR_FILE}"
  echo "Status:                     ${STATUS_FILE}"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

end_epoch="$(date +%s)"
elapsed="$((end_epoch - start_epoch))"
printf -v elapsed_display '%02d:%02d:%02d' \
  "$((elapsed / 3600))" \
  "$(((elapsed % 3600) / 60))" \
  "$((elapsed % 60))"

cat <<EOF

================================================================================
run-py-7k execution summary
Started:              ${start_display}
Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')
Elapsed:              ${elapsed_display}
Exit code:            0
Output directory:     ${OUT_DIR}
Log file:             ${LOG_FILE}
================================================================================
EOF
