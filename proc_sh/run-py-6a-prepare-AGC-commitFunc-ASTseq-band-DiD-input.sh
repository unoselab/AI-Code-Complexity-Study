#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-6a-prepare-AGC-commitFunc-ASTseq-band-DiD-input-v2.sh
# -----------------------------------------------------------------------------
# Prepare repository-month DiD inputs for one named AST sequence token band
# set by re-aggregating the event-level AGC detector predictions.
#
# Supported BAND_SET values:
#   width10_50_149  - original 10-token heterogeneity bands
#   width20_80_139  - post hoc exploratory 20-token sensitivity bands
#
# The wrapper is standalone. It calls the Python preparation script directly
# and does not call another experiment wrapper.
#
# Default execution prepares the new width20_80_139 sensitivity inputs.
# Override BAND_SET explicitly to regenerate another supported specification.
# 
# Usage:
# BAND_SET=width20_80_139 bash proc_sh/run-py-6a-prepare-AGC-commitFunc-ASTseq-band-DiD-input.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_agc_commit_function_ast_sequence_band_did_input.py}"

PREDICTIONS="${PREDICTIONS:-../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/function_event_predictions_all.csv}"
BASE_DID_PANEL="${BASE_DID_PANEL:-repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function.csv}"
BAND_SET="${BAND_SET:-width20_80_139}"
EXPECTED_BASE_ROWS="${EXPECTED_BASE_ROWS:-1633}"

case "${BAND_SET}" in
    width10_50_149|width20_80_139)
        ;;
    *)
        echo "ERROR: Unsupported BAND_SET: ${BAND_SET}" >&2
        echo "       Supported values: width10_50_149 width20_80_139" >&2
        exit 2
        ;;
esac

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-6a/strict/specifications/${BAND_SET}}"
QC_DIR="${QC_DIR:-repo_python/tmp/run-py-6a/strict/specifications/${BAND_SET}}"

RUN_TS="$(date +'%Y%m%d-%H%M%S')"
LOG_DIR="${LOG_DIR:-logs/run-py-6a}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-6a-prepare-AGC-commitFunc-ASTseq-band-DiD-input-${BAND_SET}-${RUN_TS}.log}"

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
    printf 'Elapsed:          %02d:%02d:%02d\n' \
        "${hours}" "${minutes}" "${seconds}"
    echo "Band set:         ${BAND_SET}"
    echo "Exit code:        ${exit_code}"
    echo "Output directory: ${OUTPUT_DIR}"
    echo "QC directory:     ${QC_DIR}"
    echo "Log file:         ${LOG_FILE}"
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
echo "run-py-6a: prepare AGC commit-function AST sequence band DiD inputs"
echo "Started:             ${START_TIME}"
echo "Wrapper script:      ${BASH_SOURCE[0]}"
echo "Python path:         ${PYTHON_PATH}"
echo "Python script:       ${PYTHON_SCRIPT}"
echo "Python script SHA:   ${PYTHON_SCRIPT_SHA256}"
echo "Band set:            ${BAND_SET}"
echo "Predictions:         ${PREDICTIONS}"
echo "Predictions SHA:     ${PREDICTIONS_SHA256}"
echo "Base DiD panel:      ${BASE_DID_PANEL}"
echo "Base panel SHA:      ${BASE_PANEL_SHA256}"
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
    --band-set "${BAND_SET}" \
    --expected-base-rows "${EXPECTED_BASE_ROWS}"
