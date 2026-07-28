#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-7g-leave-one-repository-out-regular-module-function-agc-unique-body.sh
# -----------------------------------------------------------------------------
# Diagnose repository-level influence on the event-month 1 dynamic Borusyak
# estimate for the focused run-py-7f outcome.
#
# The wrapper follows the input validation, logging, provenance, and output
# verification structure of run-py-7f. It is standalone and does not call or
# depend on the old shell wrapper.
#
# Scientific scope:
#   - Outcome: distinct AGC-like regular module-function bodies per repo-month
#   - Function scope: function_kind == module_function
#   - NCLOC specification: python_snapshot by default
#   - Time encoding: calendar_month by default
#   - Dynamic horizon: -6 through +6
#   - Pretrends: -6 through -2
#   - Influence unit: one repository removed per model re-estimation
#   - Primary diagnostic: change in the month-1 95% CI lower bound
#
# Inputs:
#   1. run-py-7e parse-clean focused panel
#   2. shared Borusyak helper functions
#   3. run-py-7f dynamic-effects CSV for exact full-model reproduction
#
# Outputs:
#   repo_python/run-py-7g/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#
# Default execution:
#   OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7g-leave-one-repository-out-regular-module-function-agc-unique-body.sh
#
# Important interpretation:
#   A positive lower_bound_increase means that removing the repository moves
#   the month-1 lower confidence bound upward. Such a repository contributes to
#   keeping the full-model lower bound at or below zero when it is included.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_r/leave_one_repository_out_regular_module_function_agc_unique_body.R}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"
TARGET_EVENT_MONTH="${TARGET_EVENT_MONTH:-1}"
MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT:-202408}"
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT:-202503}"
PROGRESS_EVERY="${PROGRESS_EVERY:-10}"
TOP_N="${TOP_N:-20}"
REPRODUCTION_TOLERANCE="${REPRODUCTION_TOLERANCE:-0.000001}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}}"
PANEL_PATH="${PANEL_PATH:-${INPUT_ROOT}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"
REFERENCE_ROOT="${REFERENCE_ROOT:-repo_python/run-py-7f/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"
REFERENCE_DYNAMIC_PATH="${REFERENCE_DYNAMIC_PATH:-${REFERENCE_ROOT}/borusyak_regular_module_function_agc_unique_body_dynamic_effects.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7g/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7g}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7g-loo-regular-function-agc-unique-body-${SPECIFICATION_NAME}-month${TARGET_EVENT_MONTH}-${RUN_TS}.log}"

case "${NCLOC_SPEC}" in
    paper|python_snapshot) ;;
    *)
        echo "ERROR: NCLOC_SPEC must be paper or python_snapshot: ${NCLOC_SPEC}" >&2
        exit 2
        ;;
esac

case "${TIME_MODE}" in
    original_yyyymm|calendar_month) ;;
    *)
        echo "ERROR: TIME_MODE must be original_yyyymm or calendar_month: ${TIME_MODE}" >&2
        exit 2
        ;;
esac

if [[ "${PARSE_EXCLUSION_MODE}" != "parse_clean" ]]; then
    echo "ERROR: run-py-7g currently requires PARSE_EXCLUSION_MODE=parse_clean." >&2
    exit 2
fi

case "${OVERWRITE_OUTPUT}" in
    0|1) ;;
    *)
        echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
        exit 2
        ;;
esac

if ! [[ "${TARGET_EVENT_MONTH}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: TARGET_EVENT_MONTH must be an integer." >&2
    exit 2
fi
if ! [[ "${PROGRESS_EVERY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PROGRESS_EVERY must be a positive integer." >&2
    exit 2
fi
if ! [[ "${TOP_N}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: TOP_N must be a positive integer." >&2
    exit 2
fi

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
    exit 2
fi

for required_file in \
    "${R_SCRIPT}" \
    "${HELPER_FILE}" \
    "${PANEL_PATH}" \
    "${REFERENCE_DYNAMIC_PATH}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty: ${required_file}" >&2
        exit 2
    fi
done

mkdir -p "${OUT_DIR}" "${LOG_DIR}"

PREFIX="borusyak_regular_module_function_agc_unique_body_month${TARGET_EVENT_MONTH}_leave_one_repository_out"
EXPECTED_OUTPUTS=(
    "${OUT_DIR}/${PREFIX}_full_model.csv"
    "${OUT_DIR}/${PREFIX}_all_repositories.csv"
    "${OUT_DIR}/${PREFIX}_top_lower_bound_increase.csv"
    "${OUT_DIR}/${PREFIX}_top_lower_bound_decrease.csv"
    "${OUT_DIR}/${PREFIX}_significance_flips.csv"
    "${OUT_DIR}/${PREFIX}_top_absolute_estimate_change.csv"
    "${OUT_DIR}/${PREFIX}_validation.csv"
    "${OUT_DIR}/${PREFIX}_metadata.csv"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    rm -f "${EXPECTED_OUTPUTS[@]}"
else
    for expected_file in "${EXPECTED_OUTPUTS[@]}"; do
        if [[ -e "${expected_file}" ]]; then
            echo "ERROR: Output exists and OVERWRITE_OUTPUT=0: ${expected_file}" >&2
            exit 2
        fi
    done
fi

START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"

finish() {
    local exit_code=$?
    local end_epoch elapsed hours minutes seconds

    end_epoch="$(date +%s)"
    elapsed=$((end_epoch - START_EPOCH))
    hours=$((elapsed / 3600))
    minutes=$(((elapsed % 3600) / 60))
    seconds=$((elapsed % 60))

    echo
    echo "================================================================================"
    echo "run-py-7g execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Specification:       ${SPECIFICATION_NAME}"
    echo "NCLOC specification: ${NCLOC_SPEC}"
    echo "Time mode:           ${TIME_MODE}"
    echo "Target event month:  ${TARGET_EVENT_MONTH}"
    echo "Exit code:           ${exit_code}"
    echo "Log file:            ${LOG_FILE}"
    echo "================================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

R_SCRIPT_SHA="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"
PANEL_SHA="$(sha256sum "${PANEL_PATH}" | awk '{print $1}')"
REFERENCE_SHA="$(sha256sum "${REFERENCE_DYNAMIC_PATH}" | awk '{print $1}')"

MODEL_REPOSITORIES="$(${RSCRIPT_BIN} -e "suppressPackageStartupMessages(library(data.table)); x <- fread('${PANEL_PATH}'); ready <- if ('${NCLOC_SPEC}' == 'paper') 'analysis_ready_regular_module_function_agc_unique_body_paper_ncloc' else 'analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc'; x <- x[get(ready) == 1 & has_parse_exclusion == 0]; cat(uniqueN(x\$repo_name))")"

if ! [[ "${MODEL_REPOSITORIES}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Could not determine model repository count." >&2
    exit 3
fi

ROUGH_MODEL_RUNS=$((MODEL_REPOSITORIES + 1))

echo "================================================================================"
echo "run-py-7g: leave-one-repository-out influence analysis"
echo "Started:                  ${START_TIME}"
echo "Project root:             ${PROJECT_ROOT}"
echo "Rscript:                  $(command -v "${RSCRIPT_BIN}")"
echo "R version:                $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
echo "R analysis script:        ${R_SCRIPT}"
echo "R analysis script SHA:    ${R_SCRIPT_SHA}"
echo "Helper:                   ${HELPER_FILE}"
echo "Helper SHA:               ${HELPER_SHA}"
echo "Input panel:              ${PANEL_PATH}"
echo "Input panel SHA:          ${PANEL_SHA}"
echo "Reference dynamic result: ${REFERENCE_DYNAMIC_PATH}"
echo "Reference SHA:            ${REFERENCE_SHA}"
echo "Output directory:         ${OUT_DIR}"
echo "Specification:            ${SPECIFICATION_NAME}"
echo "NCLOC specification:      ${NCLOC_SPEC}"
echo "Time mode:                ${TIME_MODE}"
echo "Parse mode:               ${PARSE_EXCLUSION_MODE}"
echo "Target event month:       ${TARGET_EVENT_MONTH}"
echo "Treatment cohort range:   ${MIN_TREATMENT_COHORT}-${MAX_TREATMENT_COHORT}"
echo "Model repositories:       ${MODEL_REPOSITORIES}"
echo "Planned model fits:       approximately ${ROUGH_MODEL_RUNS}"
echo "Progress interval:        ${PROGRESS_EVERY} repositories"
echo "Top rows per report:      ${TOP_N}"
echo "Reproduction tolerance:   ${REPRODUCTION_TOLERANCE}"
echo "Overwrite output:         ${OVERWRITE_OUTPUT}"
echo "Log file:                 ${LOG_FILE}"
echo "================================================================================"

PROJECT_ROOT="${PROJECT_ROOT}" \
PANEL_PATH="${PROJECT_ROOT}/${PANEL_PATH}" \
HELPER_FILE="${PROJECT_ROOT}/${HELPER_FILE}" \
REFERENCE_DYNAMIC_PATH="${PROJECT_ROOT}/${REFERENCE_DYNAMIC_PATH}" \
OUT_DIR="${PROJECT_ROOT}/${OUT_DIR}" \
NCLOC_SPEC="${NCLOC_SPEC}" \
TIME_MODE="${TIME_MODE}" \
TARGET_EVENT_MONTH="${TARGET_EVENT_MONTH}" \
MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT}" \
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT}" \
PROGRESS_EVERY="${PROGRESS_EVERY}" \
TOP_N="${TOP_N}" \
REPRODUCTION_TOLERANCE="${REPRODUCTION_TOLERANCE}" \
    "${RSCRIPT_BIN}" "${R_SCRIPT}"

for expected_file in "${EXPECTED_OUTPUTS[@]}"; do
    if [[ ! -s "${expected_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
        exit 3
    fi
done

validation_file="${OUT_DIR}/${PREFIX}_validation.csv"
loo_rows="$(awk -F, '$1 == "loo_result_rows" {gsub(/\r/, "", $2); print $2}' "${validation_file}")"
loo_expected="$(awk -F, '$1 == "loo_expected_repositories" {gsub(/\r/, "", $2); print $2}' "${validation_file}")"
model_errors="$(awk -F, '$1 == "loo_model_error_count" {gsub(/\r/, "", $2); print $2}' "${validation_file}")"
reproduction_pass="$(awk -F, '$1 == "full_model_reproduction_within_tolerance" {gsub(/\r/, "", $2); print $2}' "${validation_file}")"
flip_count="$(awk -F, '$1 == "significance_flip_to_positive_count" {gsub(/\r/, "", $2); print $2}' "${validation_file}")"

if [[ -z "${loo_rows}" || -z "${loo_expected}" || "${loo_rows}" != "${loo_expected}" ]]; then
    echo "ERROR: LOO row-count validation failed: rows=${loo_rows:-missing} expected=${loo_expected:-missing}" >&2
    exit 4
fi
if [[ "${model_errors}" != "0" ]]; then
    echo "ERROR: One or more leave-one-out models failed: ${model_errors:-missing}" >&2
    exit 4
fi
if [[ "${reproduction_pass}" != "TRUE" ]]; then
    echo "ERROR: Full model did not reproduce the run-py-7f reference within tolerance." >&2
    exit 4
fi

echo
echo "================================================================================"
echo "run-py-7g PASS"
echo "Full-model reproduction: PASS"
echo "LOO repository rows:     ${loo_rows}"
echo "LOO model errors:        ${model_errors}"
echo "Significance flips:      ${flip_count:-unknown}"
echo "Primary ranked output:   ${OUT_DIR}/${PREFIX}_top_lower_bound_increase.csv"
echo "All-repository output:   ${OUT_DIR}/${PREFIX}_all_repositories.csv"
echo "================================================================================"
