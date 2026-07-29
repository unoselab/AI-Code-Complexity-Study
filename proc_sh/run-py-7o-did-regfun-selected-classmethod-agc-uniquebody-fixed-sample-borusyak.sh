#!/usr/bin/env bash
set -euo pipefail

# run-py-7o: compare the original regular-module-function static Borusyak DiD
# result with a fixed-sample hybrid outcome that appends synchronous class
# methods only for five repositories selected by run-py-7m influence analysis.
#
# This wrapper is independent. It reuses the run-py-7k/run-py-7h execution
# structure but does not call either wrapper.
#
# Inputs:
#   repo_python/run-py-7n/strict/specifications/range100_200/
#     panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv
#     qc/regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv
#   repo_python/run-py-7h/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/positive_outcome_months_only/
#     borusyak_regular_module_function_agc_unique_body_positive_months_static_effects.csv
#   proc_r/diff_in_diff_borusyak_helpers.R
#   proc_r/did_regfun_selected_classmethod_agc_uniquebody_fixed_sample.R
#
# Outputs:
#   repo_python/run-py-7o/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#     original_positive_sample_fixed/
#
# Important interpretation:
#   Sample membership remains fixed to the original run-py-7h positive-month
#   sample. This is supplementary influence debugging, not a primary causal
#   analysis.
#
# Usage:
#   OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7o-did-regfun-selected-classmethod-agc-uniquebody-fixed-sample-borusyak.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_r/did_regfun_selected_classmethod_agc_uniquebody_fixed_sample.R}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"

RUN7N_ROOT="${RUN7N_ROOT:-repo_python/run-py-7n/strict/specifications/${SPECIFICATION_NAME}}"
PANEL_PATH="${PANEL_PATH:-${RUN7N_ROOT}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv}"
RUN7N_CHECKS_PATH="${RUN7N_CHECKS_PATH:-${RUN7N_ROOT}/qc/regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv}"

RUN7H_OUT_DIR="${RUN7H_OUT_DIR:-repo_python/run-py-7h/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/positive_outcome_months_only}"
REFERENCE_STATIC_PATH="${REFERENCE_STATIC_PATH:-${RUN7H_OUT_DIR}/borusyak_regular_module_function_agc_unique_body_positive_months_static_effects.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7o/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed}"

MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT:-202408}"
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT:-202503}"
REPRO_TOLERANCE="${REPRO_TOLERANCE:-0.000001}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-7o}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7o-regfun-selected-classmethod-fixed-sample-${SPECIFICATION_NAME}-${RUN_TS}.log}"

PREFIX="borusyak_regfun_selected_classmethod_agc_uniquebody_fixed_sample"
BASELINE_FILE="${OUT_DIR}/${PREFIX}_baseline_static_effects.csv"
HYBRID_FILE="${OUT_DIR}/${PREFIX}_hybrid_static_effects.csv"
COMPARISON_FILE="${OUT_DIR}/${PREFIX}_static_comparison.csv"
SELECTED_SUMMARY_FILE="${OUT_DIR}/${PREFIX}_selected_repo_summary.csv"
FILTER_FILE="${OUT_DIR}/${PREFIX}_filter_summary.csv"
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
  "${RUN7N_CHECKS_PATH}" \
  "${REFERENCE_STATIC_PATH}"; do
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
  echo "run-py-7o: fixed-sample selected class-method static DiD comparison"
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
  echo "run-py-7n checks:           ${RUN7N_CHECKS_PATH}"
  echo "Reference baseline static:  ${REFERENCE_STATIC_PATH}"
  echo "Reference SHA:              $(sha256sum "${REFERENCE_STATIC_PATH}" | awk '{print $1}')"
  echo "Output directory:           ${OUT_DIR}"
  echo "Baseline outcome:           regular module functions"
  echo "Hybrid outcome:             baseline + selected-repo class methods"
  echo "Selected repositories:      5"
  echo "Sample membership:          fixed to original module-function outcome > 0"
  echo "Method-only positive rows:  excluded upstream by run-py-7n"
  echo "Interpretation:             supplementary fixed-sample influence debugging"
  echo "Causal primary use:         NO"
  echo "NCLOC specification:        ${NCLOC_SPEC}"
  echo "Time mode:                  ${TIME_MODE}"
  echo "Treatment cohorts:          ${MIN_TREATMENT_COHORT}-${MAX_TREATMENT_COHORT}"
  echo "Reproduction tolerance:     ${REPRO_TOLERANCE}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"
  echo

  PROJECT_ROOT="${PROJECT_ROOT}" \
  PANEL_PATH="${PANEL_PATH}" \
  RUN7N_CHECKS_PATH="${RUN7N_CHECKS_PATH}" \
  REFERENCE_STATIC_PATH="${REFERENCE_STATIC_PATH}" \
  HELPER_FILE="${HELPER_FILE}" \
  OUT_DIR="${OUT_DIR}" \
  NCLOC_SPEC="${NCLOC_SPEC}" \
  TIME_MODE="${TIME_MODE}" \
  MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT}" \
  MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT}" \
  REPRO_TOLERANCE="${REPRO_TOLERANCE}" \
  "${RSCRIPT_BIN}" "${R_SCRIPT}"

  for expected_file in \
    "${BASELINE_FILE}" \
    "${HYBRID_FILE}" \
    "${COMPARISON_FILE}" \
    "${SELECTED_SUMMARY_FILE}" \
    "${FILTER_FILE}" \
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

  if ! grep -Fxq "sample_membership_fixed_to_run_py_7h=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: Fixed-sample guard is missing." >&2
    exit 1
  fi

  if ! grep -Fxq "causal_interpretation_allowed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Noncausal debugging guard is missing." >&2
    exit 1
  fi

  echo
  echo "================================================================================"
  echo "run-py-7o PASS"
  echo "Baseline static:            ${BASELINE_FILE}"
  echo "Hybrid static:              ${HYBRID_FILE}"
  echo "Static comparison:          ${COMPARISON_FILE}"
  echo "Selected-repo summary:      ${SELECTED_SUMMARY_FILE}"
  echo "Validation:                 ${VALIDATION_FILE}"
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
run-py-7o execution summary
Started:              ${start_display}
Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')
Elapsed:              ${elapsed_display}
Exit code:            0
Output directory:     ${OUT_DIR}
Log file:             ${LOG_FILE}
================================================================================
EOF
