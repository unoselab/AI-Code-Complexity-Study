#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f10-prepare-reg-fun-count-contrast-input-v1.sh
# -----------------------------------------------------------------------------
# Prepare one covariance-aware absolute-count contrast panel:
#
#   other_functions count - testing count
#
# The subtraction is performed within each identical repository-month before
# DiD estimation. The contrast may be negative, so it remains on the raw scale
# and must not be transformed with log1p.
#
# Independent implementation:
#   - This wrapper copies the execution pattern of run-py-7f08.
#   - It does not call run-py-7f08, run-py-7f09, or another shell wrapper.
#   - It reads the three completed run-py-7f08 panels as immutable inputs.
#   - It executes only prepare_reg_fun_count_contrast_input.py.
#   - It does not estimate ATT or uncertainty.
#
# Inputs:
#   repo_python/run-py-7f08/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f08-did-input-testing-regular-functions.csv
#       run-py-7f08-did-input-other-regular-functions.csv
#       run-py-7f08-did-input-all-regular-functions.csv
#
# Outputs:
#   repo_python/run-py-7f10/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f10-did-input-other-minus-testing-count-contrast.csv
#       run-py-7f10-count-contrast-summary.csv
#       run-py-7f10-count-contrast-input-qc.csv
#       run-py-7f10-count-contrast-input-metadata.json
#
# Server files are versionless:
#   proc_scripts/prepare_reg_fun_count_contrast_input.py
#   proc_sh_v2/run-py-7f10-prepare-reg-fun-count-contrast-input.sh
#
# Default execution:
#   bash proc_sh_v2/run-py-7f10-prepare-reg-fun-count-contrast-input.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f10-prepare-reg-fun-count-contrast-input.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SPECIFICATION="${SPECIFICATION:-range100_200}"
SNAPSHOT_METRIC="${SNAPSHOT_METRIC:-python_snapshot_ncloc}"
TIME_AGGREGATION="${TIME_AGGREGATION:-calendar_month}"
PARSER_SCOPE="${PARSER_SCOPE:-parse_clean}"
ANALYSIS_SUFFIX="specifications/${SPECIFICATION}/${SNAPSHOT_METRIC}/${TIME_AGGREGATION}/${PARSER_SCOPE}"

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/aicomplexity/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_reg_fun_count_contrast_input.py}"

INPUT_DIR="${INPUT_DIR:-repo_python/run-py-7f08/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
TESTING_PANEL="${TESTING_PANEL:-${INPUT_DIR}/run-py-7f08-did-input-testing-regular-functions.csv}"
OTHER_PANEL="${OTHER_PANEL:-${INPUT_DIR}/run-py-7f08-did-input-other-regular-functions.csv}"
ALL_PANEL="${ALL_PANEL:-${INPUT_DIR}/run-py-7f08-did-input-all-regular-functions.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f10/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f10}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f10-prepare-reg-fun-count-contrast-input-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1521}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-218}"
EXPECTED_TESTING_TOTAL="${EXPECTED_TESTING_TOTAL:-627}"
EXPECTED_OTHER_TOTAL="${EXPECTED_OTHER_TOTAL:-1622}"
EXPECTED_ALL_TOTAL="${EXPECTED_ALL_TOTAL:-2249}"
EXPECTED_CONTRAST_TOTAL="${EXPECTED_CONTRAST_TOTAL:-995}"
EXPECTED_NEGATIVE_ROWS="${EXPECTED_NEGATIVE_ROWS:-112}"
EXPECTED_ZERO_ROWS="${EXPECTED_ZERO_ROWS:-1064}"
EXPECTED_POSITIVE_ROWS="${EXPECTED_POSITIVE_ROWS:-345}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: Missing or empty ${label}: ${path}" >&2
        exit 2
    fi
}

require_positive_integer() {
    local value="$1"
    local label="$2"
    if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: ${label} must be a positive integer: ${value}" >&2
        exit 2
    fi
}

if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f10 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi
if [[ "${SNAPSHOT_METRIC}" != "python_snapshot_ncloc" ]]; then
    echo "ERROR: run-py-7f10 requires SNAPSHOT_METRIC=python_snapshot_ncloc." >&2
    exit 2
fi
if [[ "${TIME_AGGREGATION}" != "calendar_month" ]]; then
    echo "ERROR: run-py-7f10 requires TIME_AGGREGATION=calendar_month." >&2
    exit 2
fi
if [[ "${PARSER_SCOPE}" != "parse_clean" ]]; then
    echo "ERROR: run-py-7f10 requires PARSER_SCOPE=parse_clean." >&2
    exit 2
fi

for flag_name in RUN_SELF_TEST SELF_TEST_ONLY OVERWRITE_OUTPUT; do
    flag_value="${!flag_name}"
    case "${flag_value}" in
        0|1) ;;
        *)
            echo "ERROR: ${flag_name} must be 0 or 1." >&2
            exit 2
            ;;
    esac
done
if [[ "${SELF_TEST_ONLY}" == "1" && "${RUN_SELF_TEST}" != "1" ]]; then
    echo "ERROR: SELF_TEST_ONLY=1 requires RUN_SELF_TEST=1." >&2
    exit 2
fi

for integer_name in \
    EXPECTED_ROWS \
    EXPECTED_REPOSITORIES \
    EXPECTED_TESTING_TOTAL \
    EXPECTED_OTHER_TOTAL \
    EXPECTED_ALL_TOTAL \
    EXPECTED_CONTRAST_TOTAL \
    EXPECTED_NEGATIVE_ROWS \
    EXPECTED_ZERO_ROWS \
    EXPECTED_POSITIVE_ROWS; do
    require_positive_integer "${!integer_name}" "${integer_name}"
done

if (( EXPECTED_TESTING_TOTAL + EXPECTED_OTHER_TOTAL != EXPECTED_ALL_TOTAL )); then
    echo "ERROR: Expected testing + other totals must equal all total." >&2
    exit 2
fi
if (( EXPECTED_OTHER_TOTAL - EXPECTED_TESTING_TOTAL != EXPECTED_CONTRAST_TOTAL )); then
    echo "ERROR: Expected other - testing total must equal contrast total." >&2
    exit 2
fi
if (( EXPECTED_NEGATIVE_ROWS + EXPECTED_ZERO_ROWS + EXPECTED_POSITIVE_ROWS != EXPECTED_ROWS )); then
    echo "ERROR: Expected contrast sign rows must sum to expected rows." >&2
    exit 2
fi

if [[ "${PYTHON_BIN}" == */* ]]; then
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "ERROR: Python executable is missing or not executable: ${PYTHON_BIN}" >&2
        exit 2
    fi
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python contrast-input preparation script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${TESTING_PANEL}" "run-py-7f08 testing panel"
    require_file "${OTHER_PANEL}" "run-py-7f08 other-functions panel"
    require_file "${ALL_PANEL}" "run-py-7f08 all-functions panel"
fi

read -r PYTHON_MAJOR PYTHON_MINOR PYTHON_MICRO < <(
    "${PYTHON_BIN}" -c \
        'import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)'
)
PYTHON_VERSION="${PYTHON_MAJOR}.${PYTHON_MINOR}.${PYTHON_MICRO}"
if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 11) )); then
    echo "ERROR: Python 3.11 or newer is required; found ${PYTHON_VERSION}." >&2
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
    echo "run-py-7f10 execution summary"
    echo "Started:          ${START_TIME}"
    echo "Completed:        $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:          %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:        ${exit_code}"
    echo "Output directory: ${OUTPUT_DIR}"
    echo "Log file:         ${LOG_FILE}"
    echo "================================================================================"
    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "================================================================================"
echo "run-py-7f10: prepare regular-function count contrast input"
echo "Started:                         ${START_TIME}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Panel variant:                   ${PANEL_VARIANT}"
echo "Specification:                   ${SPECIFICATION}"
echo "Snapshot metric:                 ${SNAPSHOT_METRIC}"
echo "Time aggregation:                ${TIME_AGGREGATION}"
echo "Parser scope:                    ${PARSER_SCOPE}"
echo "Python:                          $(command -v "${PYTHON_BIN}")"
echo "Python version:                  ${PYTHON_VERSION}"
echo "Python script:                   ${PYTHON_SCRIPT}"
echo "Python script SHA:               $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Testing input:                   ${TESTING_PANEL}"
echo "Other-functions input:           ${OTHER_PANEL}"
echo "All-functions reconciliation:    ${ALL_PANEL}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Contrast:                        other_functions - testing"
echo "Outcome scale:                   raw_count_difference"
echo "Negative values:                 allowed"
echo "log1p transformation:            NONE"
echo "Expected rows/repositories:      ${EXPECTED_ROWS}/${EXPECTED_REPOSITORIES}"
echo "Expected component totals T/O/A: ${EXPECTED_TESTING_TOTAL}/${EXPECTED_OTHER_TOTAL}/${EXPECTED_ALL_TOTAL}"
echo "Expected contrast total:         ${EXPECTED_CONTRAST_TOTAL}"
echo "Expected sign rows N/Z/P:        ${EXPECTED_NEGATIVE_ROWS}/${EXPECTED_ZERO_ROWS}/${EXPECTED_POSITIVE_ROWS}"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "ATT/uncertainty estimation:      NONE"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi
if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "run-py-7f10 self-test-only execution complete."
    exit 0
fi

PYTHON_ARGS=(
    --testing-panel "${TESTING_PANEL}"
    --other-panel "${OTHER_PANEL}"
    --all-panel "${ALL_PANEL}"
    --output-dir "${OUTPUT_DIR}"
    --expected-rows "${EXPECTED_ROWS}"
    --expected-repositories "${EXPECTED_REPOSITORIES}"
    --expected-testing-total "${EXPECTED_TESTING_TOTAL}"
    --expected-other-total "${EXPECTED_OTHER_TOTAL}"
    --expected-all-total "${EXPECTED_ALL_TOTAL}"
    --expected-contrast-total "${EXPECTED_CONTRAST_TOTAL}"
    --expected-negative-rows "${EXPECTED_NEGATIVE_ROWS}"
    --expected-zero-rows "${EXPECTED_ZERO_ROWS}"
    --expected-positive-rows "${EXPECTED_POSITIVE_ROWS}"
)
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite)
fi

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/run-py-7f10-did-input-other-minus-testing-count-contrast.csv"
    "${OUTPUT_DIR}/run-py-7f10-count-contrast-summary.csv"
    "${OUTPUT_DIR}/run-py-7f10-count-contrast-input-qc.csv"
    "${OUTPUT_DIR}/run-py-7f10-count-contrast-input-metadata.json"
)
for output_path in "${EXPECTED_OUTPUTS[@]}"; do
    require_file "${output_path}" "run-py-7f10 output"
done

echo
echo "run-py-7f10 PASS: covariance-aware contrast input prepared."
echo "DiD input: ${EXPECTED_OUTPUTS[0]}"
echo "Input SHA: $(sha256sum "${EXPECTED_OUTPUTS[0]}" | awk '{print $1}')"
