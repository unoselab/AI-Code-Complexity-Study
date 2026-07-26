#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-5g1: Analyze source-line-span distributions for AGC function events.
#
# This wrapper is diagnostic only. It reads existing event-level classifier
# predictions and does not rerun the classifier or modify run-py-5d/5e/5f.
#
# Input:
#   ../python_commit_function_detect/.../function_event_predictions_all.csv
#   repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv
#
# Main outputs:
#   repo_python/run-py-5g1/strict/*.csv
#   repo_python/run-py-5g1/strict/plots/*.{png,pdf}
#
# QC outputs:
#   repo_python/tmp/run-py-5g1/strict/*.{csv,json}
#
# Threshold semantics:
#   MIN_FUNCTION_LINES=6 retains functions spanning at least 6 lines and
#   therefore excludes functions spanning 1-5 lines.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/analyze_agc_commit_function_line_size.py}"

PREDICTIONS="${PREDICTIONS:-../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/function_event_predictions_all.csv}"
PANEL="${PANEL:-repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-5g1/strict}"
QC_DIR="${QC_DIR:-repo_python/tmp/run-py-5g1/strict}"
PLOT_DIR="${PLOT_DIR:-${OUTPUT_DIR}/plots}"
PLOT_FORMATS="${PLOT_FORMATS:-png pdf}"
PLOT_DPI="${PLOT_DPI:-160}"
PRIMARY_MIN_LINES="${PRIMARY_MIN_LINES:-6}"
LINE_THRESHOLDS="${LINE_THRESHOLDS:-1 2 3 4 5 6 10 20}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-5g1}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-5g1-analyze-agc-commit-function-line-size-${RUN_TS}.log}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

for required_file in "${PYTHON_SCRIPT}" "${PREDICTIONS}" "${PANEL}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty: ${required_file}" >&2
        exit 2
    fi
done

if [[ ! "${PRIMARY_MIN_LINES}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PRIMARY_MIN_LINES must be a positive integer: ${PRIMARY_MIN_LINES}" >&2
    exit 2
fi

read -r -a THRESHOLD_ARGS <<< "${LINE_THRESHOLDS}"
if (( ${#THRESHOLD_ARGS[@]} == 0 )); then
    echo "ERROR: LINE_THRESHOLDS must contain at least one positive integer" >&2
    exit 2
fi
for threshold in "${THRESHOLD_ARGS[@]}"; do
    if [[ ! "${threshold}" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: Invalid value in LINE_THRESHOLDS: ${threshold}" >&2
        exit 2
    fi
done

read -r -a PLOT_FORMAT_ARGS <<< "${PLOT_FORMATS}"
if (( ${#PLOT_FORMAT_ARGS[@]} == 0 )); then
    echo "ERROR: PLOT_FORMATS must contain png, pdf, or both" >&2
    exit 2
fi
for plot_format in "${PLOT_FORMAT_ARGS[@]}"; do
    if [[ "${plot_format}" != "png" && "${plot_format}" != "pdf" ]]; then
        echo "ERROR: Invalid plot format: ${plot_format}" >&2
        exit 2
    fi
done

if [[ ! "${PLOT_DPI}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PLOT_DPI must be a positive integer: ${PLOT_DPI}" >&2
    exit 2
fi

mkdir -p "${OUTPUT_DIR}" "${QC_DIR}" "${PLOT_DIR}" "${LOG_DIR}"

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
    echo "run-py-5g1 execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' \
        "${hours}" "${minutes}" "${seconds}"
    echo "Primary min lines:   ${PRIMARY_MIN_LINES}"
    echo "Line thresholds:     ${LINE_THRESHOLDS}"
    echo "Exit code:           ${exit_code}"
    echo "Output directory:    ${OUTPUT_DIR}"
    echo "QC directory:        ${QC_DIR}"
    echo "Plot directory:      ${PLOT_DIR}"
    echo "Plot formats:        ${PLOT_FORMATS}"
    echo "Plot DPI:            ${PLOT_DPI}"
    echo "Log file:            ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "============================================================================"
echo "run-py-5g1: AGC commit-function source-line-span diagnostic"
echo "Started:             ${START_TIME}"
echo "Project root:        ${PROJECT_ROOT}"
echo "Python:              $(command -v "${PYTHON_BIN}")"
echo "Python script:       ${PYTHON_SCRIPT}"
echo "Predictions:         ${PREDICTIONS}"
echo "Panel:               ${PANEL}"
echo "Output directory:    ${OUTPUT_DIR}"
echo "QC directory:        ${QC_DIR}"
echo "Plot directory:      ${PLOT_DIR}"
echo "Plot formats:        ${PLOT_FORMATS}"
echo "Plot DPI:            ${PLOT_DPI}"
echo "Primary min lines:   ${PRIMARY_MIN_LINES}"
echo "Line thresholds:     ${LINE_THRESHOLDS}"
echo "Log file:            ${LOG_FILE}"
echo "============================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --predictions "${PREDICTIONS}" \
    --panel "${PANEL}" \
    --output-dir "${OUTPUT_DIR}" \
    --qc-dir "${QC_DIR}" \
    --plot-dir "${PLOT_DIR}" \
    --plot-formats "${PLOT_FORMAT_ARGS[@]}" \
    --plot-dpi "${PLOT_DPI}" \
    --primary-min-lines "${PRIMARY_MIN_LINES}" \
    --thresholds "${THRESHOLD_ARGS[@]}"

EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/agc_function_event_line_size_descriptive_summary.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_exact_distribution.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_grouped_distribution.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_threshold_summary.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_by_treatment.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_by_period.csv"
    "${OUTPUT_DIR}/agc_function_event_line_size_repo_month_impact_preview.csv"
    "${QC_DIR}/agc_function_event_line_size_qc.csv"
    "${QC_DIR}/agc_function_event_line_size_summary.json"
)

PLOT_STEMS=(
    "agc_function_event_line_size_descriptive_summary"
    "agc_function_event_line_size_exact_distribution"
    "agc_function_event_line_size_grouped_distribution"
    "agc_function_event_line_size_threshold_summary"
    "agc_function_event_line_size_by_treatment"
    "agc_function_event_line_size_by_period"
    "agc_function_event_line_size_repo_month_impact_preview"
)

for plot_stem in "${PLOT_STEMS[@]}"; do
    for plot_format in "${PLOT_FORMAT_ARGS[@]}"; do
        EXPECTED_OUTPUTS+=("${PLOT_DIR}/${plot_stem}.${plot_format}")
    done
done

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
    if [[ ! -s "${output_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${output_file}" >&2
        exit 1
    fi
done

if ! awk -F',' 'NR > 1 && $2 != "True" && $2 != "true" && $2 != "1" {exit 1}' \
    "${QC_DIR}/agc_function_event_line_size_qc.csv"; then
    echo "ERROR: One or more line-size QC checks failed" >&2
    cat "${QC_DIR}/agc_function_event_line_size_qc.csv" >&2
    exit 1
fi

echo
echo "All expected line-size diagnostic outputs were created successfully."
echo "Plot files:"
find "${PLOT_DIR}" -maxdepth 1 -type f \( -name '*.png' -o -name '*.pdf' \) | sort
echo "Threshold summary:"
cat "${OUTPUT_DIR}/agc_function_event_line_size_threshold_summary.csv"
