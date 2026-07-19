#!/usr/bin/env bash
# Prepare commit-function change events for fresh AGC detection.
#
# Workspace:
#   ai-code-complexity-study
#
# Canonical path:
#   proc_sh/run-py-5a-prepare-agc-commit-function-events.sh
#
# Analysis unit:
#   One structurally added or modified named Python function in one commit.
#   Repeated changes to the same function in different commits remain separate
#   commit-function change events. Reverted changes are retained as regular
#   events because each commit is compared with its direct first parent.
#
# Stage 1 inputs:
#   - Validated repository-month panel.
#   - Monthly snapshot manifest.
#   - Treatment and control Git clones.
#
# Stage 1 outputs:
#   - Repository-month commit boundaries.
#   - Direct first-parent pairs X-1 -> X for scan-eligible commits.
#
# Stage 2 inputs:
#   - Commit-parent pairs from Stage 1.
#   - Treatment and control Git clones.
#
# Stage 2 outputs:
#   - One manifest row per commit-function change event.
#   - One standalone Python source artifact per event.
#   - Extraction QC summaries, checks, and errors.
#
# Function scope:
#   - Module-level functions.
#   - Methods defined inside classes.
#   - Nested functions.
#   - Async variants of all function types above.
#
# Exclusions:
#   - Class definitions as a single analysis unit.
#   - Lambda expressions.
#   - Deleted functions without a post-commit version.
#   - Whitespace/comment-only edits whose structural representation is unchanged.
#
# This wrapper is standalone. It calls Python programs directly and does not
# call another experiment shell wrapper.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-5a currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PREPARE_SCRIPT="${PREPARE_SCRIPT:-proc_scripts/prepare_agc_commit_function_scan_manifest.py}"
EXTRACT_SCRIPT="${EXTRACT_SCRIPT:-proc_scripts/extract_agc_commit_function_events.py}"

INPUT_PANEL="${INPUT_PANEL:-repo_python/run-py-4a/${PANEL_VARIANT}/panel_event_monthly_agc_changed_block_py.csv}"
SNAPSHOT_MANIFEST="${SNAPSHOT_MANIFEST:-repo_python/run-py-3a/${PANEL_VARIANT}/repo_month_snapshot_manifest.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-5a/${PANEL_VARIANT}}"
QC_DIR="${QC_DIR:-repo_python/tmp/run-py-5a/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs}"
PROGRESS_EVERY="${PROGRESS_EVERY:-100}"

BOUNDARY_FILE="${OUTPUT_DIR}/repo_month_commit_scan_boundaries.csv"
MONTH_END_PAIR_FILE="${OUTPUT_DIR}/month_end_parent_pairs.csv"
COMMIT_PAIR_FILE="${OUTPUT_DIR}/commit_parent_pairs.csv"
FUNCTION_EVENT_MANIFEST="${OUTPUT_DIR}/commit_function_detection_manifest.csv"
FUNCTION_SOURCE_ROOT="${OUTPUT_DIR}/commit_function_sources"

PREPARE_SUMMARY_FILE="${QC_DIR}/agc_commit_function_scan_prepare_summary.json"
PREPARE_CHECK_FILE="${QC_DIR}/agc_commit_function_scan_prepare_checks.csv"
PREPARE_ERROR_FILE="${QC_DIR}/agc_commit_function_scan_prepare_errors.csv"
EXTRACT_SUMMARY_FILE="${QC_DIR}/agc_commit_function_event_extract_summary.json"
EXTRACT_CHECK_FILE="${QC_DIR}/agc_commit_function_event_extract_checks.csv"
EXTRACT_ERROR_FILE="${QC_DIR}/agc_commit_function_event_extract_errors.csv"

EXTRACT_AUDIT_FILE="${OUTPUT_DIR}/commit_function_event_extraction_audit.csv"
REPO_MONTH_EVENT_COUNT_FILE="${OUTPUT_DIR}/repo_month_function_event_counts.csv"

TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-5a_prepare_agc_commit_function_events_${PANEL_VARIANT}_${TIMESTAMP}.log}"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "${path}" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
        exit 2
    fi
}

require_dir() {
    local path="$1"
    local label="$2"
    if [[ ! -d "${path}" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
        exit 2
    fi
}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PREPARE_SCRIPT}" "commit-parent preparation script"
require_file "${EXTRACT_SCRIPT}" "commit-function extraction script"
require_file "${INPUT_PANEL}" "run-py-4a input panel"
require_file "${SNAPSHOT_MANIFEST}" "run-py-3a snapshot manifest"
require_dir "${TREATMENT_CLONE_DIR}" "treatment clone directory"
require_dir "${CONTROL_CLONE_DIR}" "control clone directory"

mkdir -p "${OUTPUT_DIR}" "${QC_DIR}" "${LOG_DIR}"

START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

finish() {
    local exit_code=$?
    local end_epoch elapsed hours minutes seconds
    end_epoch="$(date +%s)"
    elapsed=$((end_epoch - START_EPOCH))
    hours=$((elapsed / 3600))
    minutes=$(((elapsed % 3600) / 60))
    seconds=$((elapsed % 60))

    echo
    echo "============================================================"
    echo "run-py-5a timing summary"
    echo "Started:                 ${START_TEXT}"
    echo "Completed:               $(date)"
    printf 'Elapsed:                 %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:               ${exit_code}"
    echo "Log file:                ${LOG_FILE}"
    echo "Function event manifest: ${FUNCTION_EVENT_MANIFEST}"
    echo "Function source root:    ${FUNCTION_SOURCE_ROOT}"
    echo "============================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

cat <<INFO
============================================================
run-py-5a: prepare AGC commit-function events
Started:                  ${START_TEXT}
Panel variant:            ${PANEL_VARIANT}
Conda environment:        ${CONDA_DEFAULT_ENV:-<none>}
Python:                   ${PYTHON_BIN}
Prepare script:           ${PREPARE_SCRIPT}
Extract script:           ${EXTRACT_SCRIPT}
Input panel:              ${INPUT_PANEL}
Snapshot manifest:        ${SNAPSHOT_MANIFEST}
Treatment clones:         ${TREATMENT_CLONE_DIR}
Control clones:           ${CONTROL_CLONE_DIR}
Output directory:         ${OUTPUT_DIR}
QC directory:             ${QC_DIR}
Function event manifest:  ${FUNCTION_EVENT_MANIFEST}
Function source root:     ${FUNCTION_SOURCE_ROOT}
Log file:                 ${LOG_FILE}
============================================================
INFO

"${PYTHON_BIN}" -m py_compile "${PREPARE_SCRIPT}" "${EXTRACT_SCRIPT}"

"${PYTHON_BIN}" "${PREPARE_SCRIPT}" --self-test

"${PYTHON_BIN}" "${EXTRACT_SCRIPT}" --self-test

rm -f \
    "${FUNCTION_EVENT_MANIFEST}" \
    "${EXTRACT_AUDIT_FILE}" \
    "${REPO_MONTH_EVENT_COUNT_FILE}" \
    "${EXTRACT_SUMMARY_FILE}" \
    "${EXTRACT_CHECK_FILE}" \
    "${EXTRACT_ERROR_FILE}"

echo
echo "[Stage 1/2] Preparing repository-month commit-parent pairs"
PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PREPARE_SCRIPT}" \
    --input-panel "${INPUT_PANEL}" \
    --snapshot-manifest "${SNAPSHOT_MANIFEST}" \
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}" \
    --control-clone-dir "${CONTROL_CLONE_DIR}" \
    --output-dir "${OUTPUT_DIR}" \
    --qc-dir "${QC_DIR}" \
    --progress-every "${PROGRESS_EVERY}"

require_file "${BOUNDARY_FILE}" "repository-month boundary manifest"
require_file "${MONTH_END_PAIR_FILE}" "month-end parent pair manifest"
require_file "${COMMIT_PAIR_FILE}" "commit-parent pair manifest"
require_file "${PREPARE_SUMMARY_FILE}" "commit-parent preparation summary"
require_file "${PREPARE_CHECK_FILE}" "commit-parent preparation checks"
require_file "${PREPARE_ERROR_FILE}" "commit-parent preparation errors"

echo
echo "[Stage 2/2] Extracting structurally changed named Python functions"
PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${EXTRACT_SCRIPT}" \
    --input-commit-pairs "${COMMIT_PAIR_FILE}" \
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}" \
    --control-clone-dir "${CONTROL_CLONE_DIR}" \
    --output-manifest "${FUNCTION_EVENT_MANIFEST}" \
    --function-source-root "${FUNCTION_SOURCE_ROOT}" \
    --overwrite-source-root \
    --qc-dir "${QC_DIR}" \
    --progress-every "${PROGRESS_EVERY}"

require_file "${FUNCTION_EVENT_MANIFEST}" "commit-function detection manifest"
require_file "${EXTRACT_AUDIT_FILE}" "commit-function extraction audit"
require_file "${REPO_MONTH_EVENT_COUNT_FILE}" "repository-month function-event counts"
require_dir "${FUNCTION_SOURCE_ROOT}" "commit-function source directory"
require_file "${EXTRACT_SUMMARY_FILE}" "commit-function extraction summary"
require_file "${EXTRACT_CHECK_FILE}" "commit-function extraction checks"
require_file "${EXTRACT_ERROR_FILE}" "commit-function extraction errors"

echo
echo "run-py-5a completed successfully."
