#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f08-prepare-reg-fun-binary-group-did-inputs.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Prepare three zero-inclusive DiD input panels on one identical locked
#   repository-month model sample:
#
#   1. testing regular functions;
#   2. other (non-testing) regular functions;
#   3. all regular functions.
#
# Independent implementation:
#   - This wrapper follows the logging and validation structure of run-py-7f07.
#   - It does not call run-py-7e, run-py-7f07, or any earlier shell wrapper.
#   - It reads completed run-py-7e and run-py-7f07 artifacts as immutable inputs.
#   - It executes only prepare_reg_fun_binary_group_did_inputs.py.
#
# Construction contract:
#   - Retain exactly the 1,521 Python-snapshot-NCLOC model-ready rows.
#   - Aggregate frozen run-py-7f07 assignments by repository-month and group.
#   - Left join each group count to the locked panel and replace missing counts
#     with zero.
#   - Require testing + other_functions to equal the original run-py-7e total
#     outcome on every repository-month.
#   - Create one DiD input per outcome plus a wide reconciliation panel.
#   - Do not estimate ATT, standard errors, confidence intervals, or p-values.
#
# Inputs:
#   repo_python/run-py-7e/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv
#
#   repo_python/run-py-7f07/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f07-primary-body-month-binary-group-assignments.csv
#       run-py-7f07-binary-taxonomy.json
#       run-py-7f07-binary-taxonomy-qc.csv
#       run-py-7f07-binary-taxonomy-metadata.json
#
# Outputs:
#   repo_python/run-py-7f08/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f08-did-input-testing-regular-functions.csv
#       run-py-7f08-did-input-other-regular-functions.csv
#       run-py-7f08-did-input-all-regular-functions.csv
#       run-py-7f08-zero-inclusive-binary-outcomes-wide.csv
#       run-py-7f08-outcome-summary.csv
#       run-py-7f08-did-input-qc.csv
#       run-py-7f08-did-input-metadata.json
#
# Server files are versionless:
#   proc_scripts/prepare_reg_fun_binary_group_did_inputs.py
#   proc_sh_v2/run-py-7f08-prepare-reg-fun-binary-group-did-inputs.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f08-prepare-reg-fun-binary-group-did-inputs.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f08-prepare-reg-fun-binary-group-did-inputs.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f08 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/aicomplexity/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_reg_fun_binary_group_did_inputs.py}"

SPECIFICATION="${SPECIFICATION:-range100_200}"
SNAPSHOT_METRIC="${SNAPSHOT_METRIC:-python_snapshot_ncloc}"
TIME_AGGREGATION="${TIME_AGGREGATION:-calendar_month}"
PARSER_SCOPE="${PARSER_SCOPE:-parse_clean}"
ANALYSIS_SUFFIX="specifications/${SPECIFICATION}/${SNAPSHOT_METRIC}/${TIME_AGGREGATION}/${PARSER_SCOPE}"

RUN7E_DIR="${RUN7E_DIR:-repo_python/run-py-7e/${PANEL_VARIANT}/specifications/${SPECIFICATION}}"
BASE_PANEL="${BASE_PANEL:-${RUN7E_DIR}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"

RUN7F07_DIR="${RUN7F07_DIR:-repo_python/run-py-7f07/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
PRIMARY_ASSIGNMENTS="${PRIMARY_ASSIGNMENTS:-${RUN7F07_DIR}/run-py-7f07-primary-body-month-binary-group-assignments.csv}"
TAXONOMY_METADATA="${TAXONOMY_METADATA:-${RUN7F07_DIR}/run-py-7f07-binary-taxonomy-metadata.json}"
TAXONOMY_QC="${TAXONOMY_QC:-${RUN7F07_DIR}/run-py-7f07-binary-taxonomy-qc.csv}"
BINARY_TAXONOMY="${BINARY_TAXONOMY:-${RUN7F07_DIR}/run-py-7f07-binary-taxonomy.json}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f08/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f08}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f08-prepare-reg-fun-binary-group-did-inputs-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_BASE_PANEL_ROWS="${EXPECTED_BASE_PANEL_ROWS:-1536}"
EXPECTED_MODEL_READY_ROWS="${EXPECTED_MODEL_READY_ROWS:-1521}"
EXPECTED_BODY_MONTHS="${EXPECTED_BODY_MONTHS:-2249}"
EXPECTED_TESTING="${EXPECTED_TESTING:-627}"
EXPECTED_OTHER_FUNCTIONS="${EXPECTED_OTHER_FUNCTIONS:-1622}"
EXPECTED_TESTING_POSITIVE_ROWS="${EXPECTED_TESTING_POSITIVE_ROWS:-198}"
EXPECTED_OTHER_POSITIVE_ROWS="${EXPECTED_OTHER_POSITIVE_ROWS:-417}"
EXPECTED_ALL_POSITIVE_ROWS="${EXPECTED_ALL_POSITIVE_ROWS:-486}"
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
    EXPECTED_BASE_PANEL_ROWS \
    EXPECTED_MODEL_READY_ROWS \
    EXPECTED_BODY_MONTHS \
    EXPECTED_TESTING \
    EXPECTED_OTHER_FUNCTIONS \
    EXPECTED_TESTING_POSITIVE_ROWS \
    EXPECTED_OTHER_POSITIVE_ROWS \
    EXPECTED_ALL_POSITIVE_ROWS; do
    require_positive_integer "${!integer_name}" "${integer_name}"
done
if (( EXPECTED_TESTING + EXPECTED_OTHER_FUNCTIONS != EXPECTED_BODY_MONTHS )); then
    echo "ERROR: EXPECTED_TESTING + EXPECTED_OTHER_FUNCTIONS must equal EXPECTED_BODY_MONTHS." >&2
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

require_file "${PYTHON_SCRIPT}" "Python DiD-input preparation script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${BASE_PANEL}" "run-py-7e parse-clean base panel"
    require_file "${PRIMARY_ASSIGNMENTS}" "run-py-7f07 primary assignments"
    require_file "${TAXONOMY_METADATA}" "run-py-7f07 taxonomy metadata"
    require_file "${TAXONOMY_QC}" "run-py-7f07 taxonomy QC"
    require_file "${BINARY_TAXONOMY}" "run-py-7f07 binary taxonomy"
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
    echo "run-py-7f08 execution summary"
    echo "Started:              ${START_TIME}"
    echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:              %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:            ${exit_code}"
    echo "Output directory:     ${OUTPUT_DIR}"
    echo "Log file:             ${LOG_FILE}"
    echo "================================================================================"
    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "================================================================================"
echo "run-py-7f08: prepare binary-group regular-function DiD inputs"
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
echo "run-py-7e base panel:            ${BASE_PANEL}"
echo "run-py-7f07 assignments:         ${PRIMARY_ASSIGNMENTS}"
echo "run-py-7f07 taxonomy metadata:   ${TAXONOMY_METADATA}"
echo "run-py-7f07 taxonomy QC:         ${TAXONOMY_QC}"
echo "run-py-7f07 binary taxonomy:     ${BINARY_TAXONOMY}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Expected base-panel rows:        ${EXPECTED_BASE_PANEL_ROWS}"
echo "Expected model-ready rows:       ${EXPECTED_MODEL_READY_ROWS}"
echo "Expected body-month units:       ${EXPECTED_BODY_MONTHS}"
echo "Expected testing units:          ${EXPECTED_TESTING}"
echo "Expected other-function units:   ${EXPECTED_OTHER_FUNCTIONS}"
echo "Expected positive rows (T/O/A):  ${EXPECTED_TESTING_POSITIVE_ROWS}/${EXPECTED_OTHER_POSITIVE_ROWS}/${EXPECTED_ALL_POSITIVE_ROWS}"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Zero-inclusive outcomes:         testing, other_functions, all_regular_functions"
echo "ATT/uncertainty estimation:      NONE"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi
if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "run-py-7f08 self-test-only execution complete."
    exit 0
fi

PYTHON_ARGS=(
    --base-panel "${BASE_PANEL}"
    --assignments "${PRIMARY_ASSIGNMENTS}"
    --taxonomy-metadata "${TAXONOMY_METADATA}"
    --taxonomy-qc "${TAXONOMY_QC}"
    --binary-taxonomy "${BINARY_TAXONOMY}"
    --output-dir "${OUTPUT_DIR}"
    --expected-base-panel-rows "${EXPECTED_BASE_PANEL_ROWS}"
    --expected-model-ready-rows "${EXPECTED_MODEL_READY_ROWS}"
    --expected-body-months "${EXPECTED_BODY_MONTHS}"
    --expected-testing "${EXPECTED_TESTING}"
    --expected-other-functions "${EXPECTED_OTHER_FUNCTIONS}"
    --expected-testing-positive-rows "${EXPECTED_TESTING_POSITIVE_ROWS}"
    --expected-other-positive-rows "${EXPECTED_OTHER_POSITIVE_ROWS}"
    --expected-all-positive-rows "${EXPECTED_ALL_POSITIVE_ROWS}"
)
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite)
fi

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

OUTPUT_TESTING="${OUTPUT_DIR}/run-py-7f08-did-input-testing-regular-functions.csv"
OUTPUT_OTHER="${OUTPUT_DIR}/run-py-7f08-did-input-other-regular-functions.csv"
OUTPUT_ALL="${OUTPUT_DIR}/run-py-7f08-did-input-all-regular-functions.csv"
OUTPUT_WIDE="${OUTPUT_DIR}/run-py-7f08-zero-inclusive-binary-outcomes-wide.csv"
OUTPUT_SUMMARY="${OUTPUT_DIR}/run-py-7f08-outcome-summary.csv"
OUTPUT_QC="${OUTPUT_DIR}/run-py-7f08-did-input-qc.csv"
OUTPUT_METADATA="${OUTPUT_DIR}/run-py-7f08-did-input-metadata.json"

require_file "${OUTPUT_TESTING}" "testing DiD input"
require_file "${OUTPUT_OTHER}" "other-functions DiD input"
require_file "${OUTPUT_ALL}" "all-functions DiD input"
require_file "${OUTPUT_WIDE}" "wide reconciliation panel"
require_file "${OUTPUT_SUMMARY}" "outcome summary"
require_file "${OUTPUT_QC}" "DiD-input QC"
require_file "${OUTPUT_METADATA}" "DiD-input metadata"

"${PYTHON_BIN}" - \
    "${OUTPUT_METADATA}" \
    "${EXPECTED_MODEL_READY_ROWS}" \
    "${EXPECTED_BODY_MONTHS}" \
    "${EXPECTED_TESTING}" \
    "${EXPECTED_OTHER_FUNCTIONS}" \
    "${EXPECTED_TESTING_POSITIVE_ROWS}" \
    "${EXPECTED_OTHER_POSITIVE_ROWS}" \
    "${EXPECTED_ALL_POSITIVE_ROWS}" <<'PY'
import json
import sys
from pathlib import Path

metadata = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_rows = int(sys.argv[2])
expected_total = int(sys.argv[3])
expected_testing = int(sys.argv[4])
expected_other = int(sys.argv[5])
expected_testing_positive = int(sys.argv[6])
expected_other_positive = int(sys.argv[7])
expected_all_positive = int(sys.argv[8])

if metadata.get("schema_version") != "run-py-7f08-v1":
    raise SystemExit("Unexpected run-py-7f08 metadata schema version")
if metadata.get("status") != "PASS":
    raise SystemExit("run-py-7f08 metadata status is not PASS")

counts = metadata.get("counts", {})
expected = {
    "model_ready_repository_month_rows": expected_rows,
    "body_month_assignments": expected_total,
    "testing_total_unique_bodies": expected_testing,
    "other_functions_total_unique_bodies": expected_other,
    "all_regular_functions_total_unique_bodies": expected_total,
    "testing_positive_rows": expected_testing_positive,
    "testing_zero_rows": expected_rows - expected_testing_positive,
    "other_functions_positive_rows": expected_other_positive,
    "other_functions_zero_rows": expected_rows - expected_other_positive,
    "all_regular_functions_positive_rows": expected_all_positive,
    "all_regular_functions_zero_rows": expected_rows - expected_all_positive,
    "assignments_outside_model_ready_panel": 0,
    "row_level_reconciliation_mismatches": 0,
    "critical_qc_failures": 0,
}
for key, expected_value in expected.items():
    observed = counts.get(key)
    if observed != expected_value:
        raise SystemExit(
            f"run-py-7f08 metadata mismatch for {key}: "
            f"observed={observed!r}, expected={expected_value!r}"
        )

scope = metadata.get("scientific_scope", {})
if scope.get("same_repository_month_sample_for_all_outcomes") is not True:
    raise SystemExit("run-py-7f08 did not preserve one shared model sample")
if scope.get("binary_group_counts_left_joined_and_zero_filled") is not True:
    raise SystemExit("run-py-7f08 did not record zero-inclusive left joins")
if scope.get("binary_decomposition_verified_row_by_row") is not True:
    raise SystemExit("run-py-7f08 did not verify the binary decomposition")
if scope.get("att_or_uncertainty_computed") is not False:
    raise SystemExit("run-py-7f08 unexpectedly computed ATT or uncertainty")

print("Verified run-py-7f08 outputs:")
for key, expected_value in expected.items():
    print(f"  {key}: {expected_value}")
print("  status: PASS")
PY

echo "run-py-7f08 PASS: three zero-inclusive DiD inputs are ready; ATT was not estimated."
