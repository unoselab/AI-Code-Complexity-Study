#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-6a-prepare-AGC-commitFunc-ASTseq-band-DiD-input.sh
# -----------------------------------------------------------------------------
# Prepare repository-month DiD inputs for pre-specified AST sequence token
# bands: 50-59, 60-69, ..., 140-149.
#
# The wrapper is standalone. It calls the new Python preparation script
# directly and does not call an existing experiment wrapper.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="proc_scripts/prepare_agc_commit_function_ast_sequence_band_did_input.py"

PREDICTIONS="../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/function_event_predictions_all.csv"
BASE_DID_PANEL="repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function.csv"
OUTPUT_DIR="repo_python/run-py-6a/strict"
QC_DIR="repo_python/tmp/run-py-6a/strict"
EXPECTED_BASE_ROWS="${EXPECTED_BASE_ROWS:-1633}"

RUN_TS="$(date +'%Y%m%d-%H%M%S')"
LOG_DIR="logs/run-py-6a"
LOG_FILE="${LOG_DIR}/run-py-6a-prepare-AGC-commitFunc-ASTseq-band-DiD-input-${RUN_TS}.log"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

for required_file in \
    "${PYTHON_SCRIPT}" \
    "${PREDICTIONS}" \
    "${BASE_DID_PANEL}"; do
    if [[ ! -f "${required_file}" ]]; then
        echo "ERROR: Required file not found: ${required_file}" >&2
        exit 2
    fi
done

if [[ ! "${EXPECTED_BASE_ROWS}" =~ ^[0-9]+$ ]] || (( EXPECTED_BASE_ROWS <= 0 )); then
    echo "ERROR: EXPECTED_BASE_ROWS must be a positive integer." >&2
    exit 2
fi

mkdir -p "${OUTPUT_DIR}" "${QC_DIR}" "${LOG_DIR}"

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
    echo "run-py-6a execution summary"
    echo "Started:          ${START_TIME}"
    echo "Completed:        $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:          %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:        ${exit_code}"
    echo "Output directory: ${OUTPUT_DIR}"
    echo "QC directory:     ${QC_DIR}"
    echo "Log file:         ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "============================================================================"
echo "run-py-6a: prepare AGC commit-function AST sequence band DiD inputs"
echo "Started:          ${START_TIME}"
echo "Python path:      $(command -v "${PYTHON_BIN}")"
echo "Python script:    ${PYTHON_SCRIPT}"
echo "Predictions:      ${PREDICTIONS}"
echo "Base DiD panel:   ${BASE_DID_PANEL}"
echo "Output directory: ${OUTPUT_DIR}"
echo "QC directory:     ${QC_DIR}"
echo "Log file:         ${LOG_FILE}"
echo "============================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --predictions "${PREDICTIONS}" \
    --base-did-panel "${BASE_DID_PANEL}" \
    --output-dir "${OUTPUT_DIR}" \
    --qc-dir "${QC_DIR}" \
    --expected-base-rows "${EXPECTED_BASE_ROWS}"
