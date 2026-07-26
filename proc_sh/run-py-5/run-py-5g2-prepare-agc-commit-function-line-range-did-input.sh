#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-5g2-prepare-agc-commit-function-line-range-did-input.sh
# -----------------------------------------------------------------------------
# Prepare repository-month DiD inputs for one inclusive function source-line
# range by re-aggregating the existing event-level ML classifier predictions.
#
# Default research specification:
#   3 <= function_line_count <= 8
#
# The wrapper does not rerun the classifier and does not call an existing shell
# wrapper. It directly invokes the new Python preparation script.
#
# Inputs:
#   1. Event-level classifier predictions containing start_line/end_line.
#   2. The covariate-complete run-py-5e full repository-month panel.
#
# Main outputs:
#   repo_python/run-py-5g2/strict/function_lines_3_8/
#     panel_event_monthly_agc_commit_function_lines_3_8.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_ratio_positive.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_parse_clean.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_ratio_positive_parse_clean.csv
#     agc_commit_function_line_range_support.csv
#     agc_commit_function_line_range_support_by_group.csv
#     agc_commit_function_line_range_event_time_support.csv
#     agc_commit_function_line_range_sample_summary.csv
#
# QC outputs:
#   repo_python/tmp/run-py-5g2/strict/function_lines_3_8/
#     agc_commit_function_line_range_checks.csv
#     agc_commit_function_line_range_summary.json
#
# Optional overrides:
#   MIN_FUNCTION_LINES=3
#   MAX_FUNCTION_LINES=8
#   EXPECTED_BASE_ROWS=1633
#   PYTHON_BIN=python
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_agc_commit_function_line_range_did_input.py}"

PREDICTIONS="${PREDICTIONS:-../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/function_event_predictions_all.csv}"
BASE_DID_PANEL="${BASE_DID_PANEL:-repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function.csv}"

MIN_FUNCTION_LINES="${MIN_FUNCTION_LINES:-3}"
MAX_FUNCTION_LINES="${MAX_FUNCTION_LINES:-8}"
EXPECTED_BASE_ROWS="${EXPECTED_BASE_ROWS:-1633}"

if [[ ! "${MIN_FUNCTION_LINES}" =~ ^[0-9]+$ ]] || (( MIN_FUNCTION_LINES < 1 )); then
    echo "ERROR: MIN_FUNCTION_LINES must be a positive integer." >&2
    exit 2
fi
if [[ ! "${MAX_FUNCTION_LINES}" =~ ^[0-9]+$ ]] || (( MAX_FUNCTION_LINES < MIN_FUNCTION_LINES )); then
    echo "ERROR: MAX_FUNCTION_LINES must be an integer >= MIN_FUNCTION_LINES." >&2
    exit 2
fi
if [[ ! "${EXPECTED_BASE_ROWS}" =~ ^[0-9]+$ ]] || (( EXPECTED_BASE_ROWS < 1 )); then
    echo "ERROR: EXPECTED_BASE_ROWS must be a positive integer." >&2
    exit 2
fi

SPEC_SLUG="function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-5g2/strict/${SPEC_SLUG}}"
QC_DIR="${QC_DIR:-repo_python/tmp/run-py-5g2/strict/${SPEC_SLUG}}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-5g2}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-5g2-prepare-agc-commit-function-line-range-${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES}-${RUN_TS}.log}"

sha256_file() {
    local file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${file}" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${file}" | awk '{print $1}'
    else
        echo "unavailable"
    fi
}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

for required_file in \
    "${PYTHON_SCRIPT}" \
    "${PREDICTIONS}" \
    "${BASE_DID_PANEL}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty: ${required_file}" >&2
        exit 2
    fi
done

mkdir -p "${OUTPUT_DIR}" "${QC_DIR}" "${LOG_DIR}"

RANGE_SLUG="${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}"
EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_lines_${RANGE_SLUG}.csv"
    "${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_lines_${RANGE_SLUG}_ratio_positive.csv"
    "${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_lines_${RANGE_SLUG}_parse_clean.csv"
    "${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_lines_${RANGE_SLUG}_ratio_positive_parse_clean.csv"
    "${OUTPUT_DIR}/agc_commit_function_line_range_support.csv"
    "${OUTPUT_DIR}/agc_commit_function_line_range_support_by_group.csv"
    "${OUTPUT_DIR}/agc_commit_function_line_range_event_time_support.csv"
    "${OUTPUT_DIR}/agc_commit_function_line_range_sample_summary.csv"
    "${QC_DIR}/agc_commit_function_line_range_checks.csv"
    "${QC_DIR}/agc_commit_function_line_range_summary.json"
)

# Remove only outputs owned by this specification. A failed run therefore
# cannot be mistaken for a successful current run.
rm -f "${EXPECTED_OUTPUTS[@]}"

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
    echo "============================================================================"
    echo "run-py-5g2 execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' \
        "${hours}" "${minutes}" "${seconds}"
    echo "Function line range: ${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES} inclusive"
    echo "Exit code:           ${exit_code}"
    echo "Output directory:    ${OUTPUT_DIR}"
    echo "QC directory:        ${QC_DIR}"
    echo "Log file:            ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_PATH="$(command -v "${PYTHON_BIN}")"
PYTHON_SCRIPT_SHA256="$(sha256_file "${PYTHON_SCRIPT}")"
PREDICTIONS_SHA256="$(sha256_file "${PREDICTIONS}")"
BASE_PANEL_SHA256="$(sha256_file "${BASE_DID_PANEL}")"

printf '%s\n' "============================================================================"
echo "run-py-5g2: prepare AGC commit-function line-range DiD inputs"
echo "Started:             ${START_TIME}"
echo "Project root:        ${PROJECT_ROOT}"
echo "Python path:         ${PYTHON_PATH}"
echo "Python script:       ${PYTHON_SCRIPT}"
echo "Python script SHA:   ${PYTHON_SCRIPT_SHA256}"
echo "Predictions:         ${PREDICTIONS}"
echo "Predictions SHA:     ${PREDICTIONS_SHA256}"
echo "Base DiD panel:      ${BASE_DID_PANEL}"
echo "Base panel SHA:      ${BASE_PANEL_SHA256}"
echo "Minimum lines:       ${MIN_FUNCTION_LINES} inclusive"
echo "Maximum lines:       ${MAX_FUNCTION_LINES} inclusive"
echo "Expected base rows:  ${EXPECTED_BASE_ROWS}"
echo "Output directory:    ${OUTPUT_DIR}"
echo "QC directory:        ${QC_DIR}"
echo "Log file:            ${LOG_FILE}"
printf '%s\n' "============================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --predictions "${PREDICTIONS}" \
    --base-did-panel "${BASE_DID_PANEL}" \
    --output-dir "${OUTPUT_DIR}" \
    --qc-dir "${QC_DIR}" \
    --min-function-lines "${MIN_FUNCTION_LINES}" \
    --max-function-lines "${MAX_FUNCTION_LINES}" \
    --expected-base-rows "${EXPECTED_BASE_ROWS}"

for expected_file in "${EXPECTED_OUTPUTS[@]}"; do
    if [[ ! -s "${expected_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
        exit 3
    fi
done

failed_checks="$(awk -F, 'NR > 1 && tolower($2) != "true" {count++} END {print count+0}' \
    "${QC_DIR}/agc_commit_function_line_range_checks.csv")"
if [[ "${failed_checks}" != "0" ]]; then
    echo "ERROR: QC reported ${failed_checks} failed checks." >&2
    exit 4
fi

summary_status="$(${PYTHON_BIN} -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' \
    "${QC_DIR}/agc_commit_function_line_range_summary.json")"
if [[ "${summary_status}" != "PASS" ]]; then
    echo "ERROR: Summary status is not PASS: ${summary_status}" >&2
    exit 4
fi

echo
echo "All expected line-range DiD input outputs were created successfully."
echo "Support summary:"
cat "${OUTPUT_DIR}/agc_commit_function_line_range_support.csv"
echo
echo "Sample summary:"
cat "${OUTPUT_DIR}/agc_commit_function_line_range_sample_summary.csv"
