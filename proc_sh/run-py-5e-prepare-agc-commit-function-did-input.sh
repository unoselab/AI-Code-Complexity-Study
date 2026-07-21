#!/usr/bin/env bash
#
# Prepare Borusyak DiD input panels for Python commit-function AGC outcomes.
#
# Input:
#   repo_python/run-py-5d/strict/
#     repo_month_agc_function_event_analysis_complete.csv
#
# Outputs:
#   repo_python/run-py-5e/strict/
#     panel_event_monthly_agc_commit_function.csv
#     panel_event_monthly_agc_commit_function_ratio_positive.csv
#     panel_event_monthly_agc_commit_function_parse_clean.csv
#     panel_event_monthly_agc_commit_function_ratio_positive_parse_clean.csv
#     agc_commit_function_event_time_support.csv
#     agc_commit_function_outcome_completeness.csv
#     agc_commit_function_sample_summary.csv
#     agc_commit_function_did_input_checks.csv
#     agc_commit_function_did_input_summary.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${REPO_ROOT}/proc_scripts/prepare_agc_commit_function_did_input.py"

INPUT_TABLE="${REPO_ROOT}/repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv"
OUTPUT_DIR="${REPO_ROOT}/repo_python/run-py-5e/strict"

if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PYTHON_SCRIPT}" >&2
    exit 1
fi

if [[ ! -f "${INPUT_TABLE}" ]]; then
    echo "ERROR: Input table not found: ${INPUT_TABLE}" >&2
    exit 1
fi

echo "============================================================================"
echo "run-py-5e: prepare commit-function AGC Borusyak DiD inputs"
echo "Started:        $(date)"
echo "Python:         ${PYTHON_BIN}"
echo "Python script:  ${PYTHON_SCRIPT}"
echo "Input table:    ${INPUT_TABLE}"
echo "Output dir:     ${OUTPUT_DIR}"
echo "============================================================================"

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --input-table "${INPUT_TABLE}" \
    --covariate-panel "${REPO_ROOT}/repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv" \
    --output-dir "${OUTPUT_DIR}" \
    --expected-rows 1633 \
    --expected-positive-event-rows 1289 \
    --expected-zero-event-rows 344 \
    --expected-control-rows 780 \
    --expected-treatment-rows 853 \
    --expected-parse-exclusion-months 97

echo "============================================================================"
echo "run-py-5e completed successfully"
echo "Completed:      $(date)"
echo "============================================================================"
