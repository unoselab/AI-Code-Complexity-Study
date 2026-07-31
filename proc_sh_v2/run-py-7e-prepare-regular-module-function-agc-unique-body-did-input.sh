#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-7e-prepare-regular-module-function-agc-unique-body-did-input.sh
# -----------------------------------------------------------------------------
# Prepare a focused repository-month DiD panel for AGC-like regular functions.
#
# Scientific scope:
#   - Include only synchronous module-level functions:
#       function_kind == "module_function"
#   - Include only AGC-like classifications from the frozen NPR detector.
#   - Count distinct function_body_sha256 values within each repository-month.
#   - Retain every matched repository-month, including zero-count months.
#   - Do not create or carry HWC outcomes.
#   - Do not create or carry AGC/HWC ratio outcomes.
#
# Inputs:
#   1. Event-level frozen NPR classifications from run-py-7a.
#   2. The existing zero-inclusive matched panel from run-py-7b, used only for
#      panel membership, treatment timing, covariates, parse flags, and frozen
#      detector metadata. Its old all-function outcomes are not copied.
#
# Outputs:
#   repo_python/run-py-7e/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_agc_unique_body.csv
#     panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv
#     regular_module_function_agc_unique_body_repo_month_counts.csv
#     qc/regular_module_function_agc_unique_body_did_input_checks.csv
#     qc/regular_module_function_agc_unique_body_did_input_summary.json
#
# Usage:
#   OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7e-prepare-regular-module-function-agc-unique-body-did-input.sh
#
# Optional validation-only run:
#   RUN_SELF_TEST=1 bash proc_sh_v2/run-py-7e-prepare-regular-module-function-agc-unique-body-did-input.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_regular_module_function_agc_unique_body_did_input.py}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
EVENT_CLASSIFICATIONS="${EVENT_CLASSIFICATIONS:-repo_python/run-py-7a/strict/specifications/${SPECIFICATION_NAME}/agc_commit_function_npr_event_classifications.csv}"
BASE_PANEL="${BASE_PANEL:-repo_python/run-py-7b/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_agc_commit_function_npr.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7e}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7e-prepare-regular-function-agc-unique-body-${SPECIFICATION_NAME}-${RUN_TS}.log}"

case "${OVERWRITE_OUTPUT}" in
    0|1) ;;
    *)
        echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
        exit 2
        ;;
esac

case "${RUN_SELF_TEST}" in
    0|1) ;;
    *)
        echo "ERROR: RUN_SELF_TEST must be 0 or 1." >&2
        exit 2
        ;;
esac

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

if [[ ! -s "${PYTHON_SCRIPT}" ]]; then
    echo "ERROR: Python script is missing or empty: ${PYTHON_SCRIPT}" >&2
    exit 2
fi

mkdir -p "${LOG_DIR}"
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
    echo "run-py-7e execution summary"
    echo "Started:              ${START_TIME}"
    echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:              %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Specification:        ${SPECIFICATION_NAME}"
    echo "Exit code:            ${exit_code}"
    echo "Log file:             ${LOG_FILE}"
    echo "================================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_SCRIPT_SHA="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7e: prepare regular-function AGC unique-body DiD input"
echo "Started:              ${START_TIME}"
echo "Project root:         ${PROJECT_ROOT}"
echo "Python:               $(command -v "${PYTHON_BIN}")"
echo "Python version:       $("${PYTHON_BIN}" --version 2>&1)"
echo "Python script:        ${PYTHON_SCRIPT}"
echo "Python script SHA:    ${PYTHON_SCRIPT_SHA}"
echo "Specification:        ${SPECIFICATION_NAME}"
echo "Function kind:        module_function"
echo "Classification:       AGC-like only"
echo "Count unit:           distinct body SHA per repository-month"
echo "Event classifications:${EVENT_CLASSIFICATIONS}"
echo "Base panel:           ${BASE_PANEL}"
echo "Output directory:     ${OUTPUT_DIR}"
echo "Overwrite output:     ${OVERWRITE_OUTPUT}"
echo "Run self-test:        ${RUN_SELF_TEST}"
echo "Log file:             ${LOG_FILE}"
echo "================================================================================"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

for required_input in "${EVENT_CLASSIFICATIONS}" "${BASE_PANEL}"; do
    if [[ ! -s "${required_input}" ]]; then
        echo "ERROR: Required input is missing or empty: ${required_input}" >&2
        exit 2
    fi
done

args=(
    "${PYTHON_SCRIPT}"
    --event-classifications "${EVENT_CLASSIFICATIONS}"
    --base-panel "${BASE_PANEL}"
    --output-dir "${OUTPUT_DIR}"
    --specification-name "${SPECIFICATION_NAME}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    args+=(--overwrite-output)
fi

"${PYTHON_BIN}" "${args[@]}"

expected_outputs=(
    "${OUTPUT_DIR}/panel_event_monthly_regular_module_function_agc_unique_body.csv"
    "${OUTPUT_DIR}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv"
    "${OUTPUT_DIR}/regular_module_function_agc_unique_body_repo_month_counts.csv"
    "${OUTPUT_DIR}/qc/regular_module_function_agc_unique_body_did_input_checks.csv"
    "${OUTPUT_DIR}/qc/regular_module_function_agc_unique_body_did_input_summary.json"
)

for expected_file in "${expected_outputs[@]}"; do
    if [[ ! -s "${expected_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
        exit 3
    fi
done

failed_checks="$(awk -F, 'NR > 1 && tolower($2) != "true" {count++} END {print count + 0}' \
    "${OUTPUT_DIR}/qc/regular_module_function_agc_unique_body_did_input_checks.csv")"
if [[ "${failed_checks}" != "0" ]]; then
    echo "ERROR: DiD input validation contains ${failed_checks} failed checks." >&2
    exit 4
fi

echo "run-py-7e PASS: focused DiD input panel and QC artifacts were created."
