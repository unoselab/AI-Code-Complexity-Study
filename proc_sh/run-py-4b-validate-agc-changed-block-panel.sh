#!/usr/bin/env bash
# Validate the AGC changed-block repository-month panel produced by run-py-4a.
#
# Inputs:
#   - The strict changed-block panel and its original run-py-3b base panel.
#   - Repository-month changed-block outcomes.
#   - Block-level classifications.
#   - Preparation QC files produced by run-py-4a.
#
# Outputs:
#   - Validation summary, checks, and errors.
#   - Independent block reaggregation diagnostics.
#   - Ratio-coverage tables by analysis group, event time, and month.
#
# This wrapper is independent. It does not call another experiment wrapper.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-4b currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/validate_agc_changed_block_panel.py}"
RUN4A_DIR="${RUN4A_DIR:-repo_python/run-py-4a/${PANEL_VARIANT}}"
RUN4A_QC_DIR="${RUN4A_QC_DIR:-repo_python/tmp/run-py-4a/${PANEL_VARIANT}}"
BASE_PANEL="${BASE_PANEL:-repo_python/run-py-3b/${PANEL_VARIANT}/panel_event_monthly_agc_py.csv}"
INPUT_PANEL="${INPUT_PANEL:-${RUN4A_DIR}/panel_event_monthly_agc_changed_block_py.csv}"
OUTCOMES="${OUTCOMES:-${RUN4A_DIR}/repo_month_agc_changed_block_outcomes_py.csv}"
CLASSIFICATIONS="${CLASSIFICATIONS:-${RUN4A_DIR}/changed_block_classifications_py.csv}"
VALIDATION_DIR="${VALIDATION_DIR:-repo_python/tmp/run-py-4b/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-4b_validate_agc_changed_block_panel_${PANEL_VARIANT}_${TIMESTAMP}.log}"
SUMMARY_FILE="${VALIDATION_DIR}/agc_changed_block_panel_validation_summary.json"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1633}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-220}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-853}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-780}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-100}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-120}"
EXPECTED_POST_ROWS="${EXPECTED_POST_ROWS:-432}"
EXPECTED_MIN_TIME="${EXPECTED_MIN_TIME:-2024-01}"
EXPECTED_MAX_TIME="${EXPECTED_MAX_TIME:-2025-08}"
EXPECTED_OUTCOME_ROWS="${EXPECTED_OUTCOME_ROWS:-3043}"
EXPECTED_CHANGED_BLOCKS="${EXPECTED_CHANGED_BLOCKS:-163540}"
EXPECTED_CHANGED_AGC_BLOCKS="${EXPECTED_CHANGED_AGC_BLOCKS:-23595}"
EXPECTED_CHANGED_HWC_BLOCKS="${EXPECTED_CHANGED_HWC_BLOCKS:-139945}"
EXPECTED_RATIO_ROWS="${EXPECTED_RATIO_ROWS:-1127}"
CHUNKSIZE="${CHUNKSIZE:-100000}"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "${path}" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
        exit 2
    fi
}

require_file "${PYTHON_SCRIPT}" "Python validator"
require_file "${BASE_PANEL}" "base AGC panel"
require_file "${INPUT_PANEL}" "changed-block panel"
require_file "${OUTCOMES}" "repository-month outcomes"
require_file "${CLASSIFICATIONS}" "block classifications"
require_file "${RUN4A_QC_DIR}/agc_changed_block_prepare_summary.json" "run-py-4a summary"
require_file "${RUN4A_QC_DIR}/agc_changed_block_prepare_checks.csv" "run-py-4a checks"
require_file "${RUN4A_QC_DIR}/agc_changed_block_pair_qc.csv" "run-py-4a pair QC"
require_file "${RUN4A_QC_DIR}/agc_changed_block_prediction_mismatches.csv" "prediction mismatch file"
require_file "${RUN4A_QC_DIR}/agc_changed_block_errors.csv" "preparation error file"

mkdir -p "${VALIDATION_DIR}" "${LOG_DIR}"

START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

cat <<EOF
============================================================
run-py-4b: validate AGC changed-block repository-month panel
Started:                  ${START_TEXT}
Panel variant:            ${PANEL_VARIANT}
Conda environment:        ${CONDA_DEFAULT_ENV:-<none>}
Python:                   ${PYTHON_BIN}
Python script:            ${PYTHON_SCRIPT}
Input panel:              ${INPUT_PANEL}
Base panel:               ${BASE_PANEL}
Outcome table:            ${OUTCOMES}
Block classifications:    ${CLASSIFICATIONS}
Preparation QC:           ${RUN4A_QC_DIR}
Validation directory:     ${VALIDATION_DIR}
Log file:                 ${LOG_FILE}
============================================================
EOF

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --input-panel "${INPUT_PANEL}" \
    --base-panel "${BASE_PANEL}" \
    --repo-month-outcomes "${OUTCOMES}" \
    --block-classifications "${CLASSIFICATIONS}" \
    --prepare-qc-dir "${RUN4A_QC_DIR}" \
    --output-dir "${VALIDATION_DIR}" \
    --panel-label "${PANEL_VARIANT}" \
    --chunksize "${CHUNKSIZE}" \
    --expected-panel-rows "${EXPECTED_PANEL_ROWS}" \
    --expected-repositories "${EXPECTED_REPOSITORIES}" \
    --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}" \
    --expected-control-rows "${EXPECTED_CONTROL_ROWS}" \
    --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
    --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
    --expected-post-rows "${EXPECTED_POST_ROWS}" \
    --expected-min-time "${EXPECTED_MIN_TIME}" \
    --expected-max-time "${EXPECTED_MAX_TIME}" \
    --expected-outcome-rows "${EXPECTED_OUTCOME_ROWS}" \
    --expected-changed-blocks "${EXPECTED_CHANGED_BLOCKS}" \
    --expected-changed-agc-blocks "${EXPECTED_CHANGED_AGC_BLOCKS}" \
    --expected-changed-hwc-blocks "${EXPECTED_CHANGED_HWC_BLOCKS}" \
    --expected-ratio-rows "${EXPECTED_RATIO_ROWS}" \
    2>&1 | tee "${LOG_FILE}"

REQUIRED_OUTPUTS=(
    "${SUMMARY_FILE}"
    "${VALIDATION_DIR}/agc_changed_block_panel_validation_checks.csv"
    "${VALIDATION_DIR}/agc_changed_block_panel_validation_errors.csv"
    "${VALIDATION_DIR}/agc_changed_block_reaggregation_mismatches.csv"
    "${VALIDATION_DIR}/agc_changed_block_outcome_coverage.csv"
    "${VALIDATION_DIR}/agc_changed_block_ratio_coverage_by_group.csv"
    "${VALIDATION_DIR}/agc_changed_block_ratio_coverage_by_event_time.csv"
    "${VALIDATION_DIR}/agc_changed_block_ratio_coverage_by_month.csv"
    "${VALIDATION_DIR}/agc_changed_block_denominator_distribution.csv"
)

for output_path in "${REQUIRED_OUTPUTS[@]}"; do
    require_file "${output_path}" "validation output"
done

"${PYTHON_BIN}" -c \
    'import json, sys; data=json.load(open(sys.argv[1])); raise SystemExit(0 if data.get("status") == "PASS" else 1)' \
    "${SUMMARY_FILE}"

END_EPOCH="$(date +%s)"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_TEXT '%02d:%02d:%02d' \
    "$((ELAPSED_SECONDS / 3600))" \
    "$(((ELAPSED_SECONDS % 3600) / 60))" \
    "$((ELAPSED_SECONDS % 60))"

cat <<EOF

============================================================
run-py-4b completed successfully.
Completed:                $(date)
Elapsed:                  ${ELAPSED_TEXT}
Validation summary:       ${SUMMARY_FILE}
Validation checks:        ${VALIDATION_DIR}/agc_changed_block_panel_validation_checks.csv
Ratio coverage by group:  ${VALIDATION_DIR}/agc_changed_block_ratio_coverage_by_group.csv
Log file:                 ${LOG_FILE}
============================================================
EOF
