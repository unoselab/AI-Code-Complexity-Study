#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f07-freeze-reg-fun-binary-taxonomy.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Freeze exactly two mutually exclusive groups for regular synchronous module
#   functions: testing and other_functions.
#
# Independent implementation:
#   - This wrapper was derived from the run-py-7f06 wrapper structure.
#   - It does not call run-py-7f06 or any earlier shell wrapper.
#   - It reads the completed run-py-7f06 outputs as immutable provenance inputs.
#   - It executes only freeze_reg_fun_binary_taxonomy.py.
#
# Binary grouping rule:
#   testing:
#     A body-month unit with the locked run-py-7f06 testing signal, which is
#     produced by a test-oriented function name or source path. The group
#     includes test cases, fixtures, and test-support helpers.
#   other_functions:
#     Every body-month unit without the testing signal. This intentionally
#     combines the former main, web/API, CLI, validation, and other_general
#     candidate roles.
#
# Scientific boundaries:
#   - Preserve all 2,249 locked run-py-7f01 body-month units.
#   - Require exactly 627 testing and 1,622 other_functions units.
#   - Require duplicate assignments = 0 and unassigned units = 0.
#   - Freeze the binary taxonomy only.
#   - Do not create group-specific repository-month outcomes.
#   - Do not read or estimate ATT, standard errors, confidence intervals, or
#     p-values.
#
# Inputs:
#   repo_python/run-py-7f06/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f06-primary-body-month-candidate-assignments.csv
#       run-py-7f06-candidate-taxonomy.json
#       run-py-7f06-taxonomy-audit-qc.csv
#       run-py-7f06-taxonomy-audit-metadata.json
#
# Outputs:
#   repo_python/run-py-7f07/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f07-primary-body-month-binary-group-assignments.csv
#       run-py-7f07-binary-group-summary.csv
#       run-py-7f07-binary-group-support.csv
#       run-py-7f07-binary-taxonomy.json
#       run-py-7f07-binary-taxonomy-qc.csv
#       run-py-7f07-binary-taxonomy-metadata.json
#
# Server files are versionless:
#   proc_scripts/freeze_reg_fun_binary_taxonomy.py
#   proc_sh_v2/run-py-7f07-freeze-reg-fun-binary-taxonomy.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f07-freeze-reg-fun-binary-taxonomy.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f07-freeze-reg-fun-binary-taxonomy.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f07 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/aicomplexity/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/freeze_reg_fun_binary_taxonomy.py}"

SPECIFICATION="${SPECIFICATION:-range100_200}"
SNAPSHOT_METRIC="${SNAPSHOT_METRIC:-python_snapshot_ncloc}"
TIME_AGGREGATION="${TIME_AGGREGATION:-calendar_month}"
PARSER_SCOPE="${PARSER_SCOPE:-parse_clean}"
ANALYSIS_SUFFIX="specifications/${SPECIFICATION}/${SNAPSHOT_METRIC}/${TIME_AGGREGATION}/${PARSER_SCOPE}"

RUN7F06_DIR="${RUN7F06_DIR:-repo_python/run-py-7f06/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
PRIMARY_ASSIGNMENTS="${PRIMARY_ASSIGNMENTS:-${RUN7F06_DIR}/run-py-7f06-primary-body-month-candidate-assignments.csv}"
AUDIT_METADATA="${AUDIT_METADATA:-${RUN7F06_DIR}/run-py-7f06-taxonomy-audit-metadata.json}"
AUDIT_QC="${AUDIT_QC:-${RUN7F06_DIR}/run-py-7f06-taxonomy-audit-qc.csv}"
CANDIDATE_TAXONOMY="${CANDIDATE_TAXONOMY:-${RUN7F06_DIR}/run-py-7f06-candidate-taxonomy.json}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f07/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f07}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f07-freeze-reg-fun-binary-taxonomy-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_BODY_MONTHS="${EXPECTED_BODY_MONTHS:-2249}"
EXPECTED_TESTING="${EXPECTED_TESTING:-627}"
EXPECTED_OTHER_FUNCTIONS="${EXPECTED_OTHER_FUNCTIONS:-1622}"
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

require_positive_integer "${EXPECTED_BODY_MONTHS}" "EXPECTED_BODY_MONTHS"
require_positive_integer "${EXPECTED_TESTING}" "EXPECTED_TESTING"
require_positive_integer "${EXPECTED_OTHER_FUNCTIONS}" "EXPECTED_OTHER_FUNCTIONS"
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

require_file "${PYTHON_SCRIPT}" "Python binary-taxonomy script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${PRIMARY_ASSIGNMENTS}" "run-py-7f06 primary assignments"
    require_file "${AUDIT_METADATA}" "run-py-7f06 audit metadata"
    require_file "${AUDIT_QC}" "run-py-7f06 audit QC"
    require_file "${CANDIDATE_TAXONOMY}" "run-py-7f06 candidate taxonomy"
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
    echo "run-py-7f07 execution summary"
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
echo "run-py-7f07: freeze binary regular-function taxonomy"
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
echo "run-py-7f06 assignments:         ${PRIMARY_ASSIGNMENTS}"
echo "run-py-7f06 audit metadata:      ${AUDIT_METADATA}"
echo "run-py-7f06 audit QC:            ${AUDIT_QC}"
echo "run-py-7f06 candidate taxonomy:  ${CANDIDATE_TAXONOMY}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Expected body-month units:       ${EXPECTED_BODY_MONTHS}"
echo "Expected testing units:          ${EXPECTED_TESTING}"
echo "Expected other-function units:   ${EXPECTED_OTHER_FUNCTIONS}"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Taxonomy status:                 FROZEN_BINARY"
echo "Group-specific monthly outcomes: NONE"
echo "ATT/uncertainty inputs:          NONE"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi
if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "run-py-7f07 self-test-only execution complete."
    exit 0
fi

PYTHON_ARGS=(
    --assignments "${PRIMARY_ASSIGNMENTS}"
    --audit-metadata "${AUDIT_METADATA}"
    --audit-qc "${AUDIT_QC}"
    --candidate-taxonomy "${CANDIDATE_TAXONOMY}"
    --output-dir "${OUTPUT_DIR}"
    --expected-body-months "${EXPECTED_BODY_MONTHS}"
    --expected-testing "${EXPECTED_TESTING}"
    --expected-other-functions "${EXPECTED_OTHER_FUNCTIONS}"
)
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite)
fi

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

OUTPUT_ASSIGNMENTS="${OUTPUT_DIR}/run-py-7f07-primary-body-month-binary-group-assignments.csv"
OUTPUT_SUMMARY="${OUTPUT_DIR}/run-py-7f07-binary-group-summary.csv"
OUTPUT_SUPPORT="${OUTPUT_DIR}/run-py-7f07-binary-group-support.csv"
OUTPUT_TAXONOMY="${OUTPUT_DIR}/run-py-7f07-binary-taxonomy.json"
OUTPUT_QC="${OUTPUT_DIR}/run-py-7f07-binary-taxonomy-qc.csv"
OUTPUT_METADATA="${OUTPUT_DIR}/run-py-7f07-binary-taxonomy-metadata.json"

require_file "${OUTPUT_ASSIGNMENTS}" "binary group assignments output"
require_file "${OUTPUT_SUMMARY}" "binary group summary output"
require_file "${OUTPUT_SUPPORT}" "binary group support output"
require_file "${OUTPUT_TAXONOMY}" "frozen binary taxonomy output"
require_file "${OUTPUT_QC}" "binary taxonomy QC output"
require_file "${OUTPUT_METADATA}" "binary taxonomy metadata output"

"${PYTHON_BIN}" - \
    "${OUTPUT_METADATA}" \
    "${EXPECTED_BODY_MONTHS}" \
    "${EXPECTED_TESTING}" \
    "${EXPECTED_OTHER_FUNCTIONS}" <<'PY'
import json
import sys
from pathlib import Path

metadata_path = Path(sys.argv[1])
expected_total = int(sys.argv[2])
expected_testing = int(sys.argv[3])
expected_other = int(sys.argv[4])
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

if metadata.get("schema_version") != "run-py-7f07-v1":
    raise SystemExit("Unexpected run-py-7f07 metadata schema version")
if metadata.get("status") != "PASS":
    raise SystemExit("run-py-7f07 metadata status is not PASS")
if metadata.get("taxonomy_status") != "FROZEN_BINARY":
    raise SystemExit("run-py-7f07 taxonomy is not frozen")

counts = metadata.get("counts", {})
expected = {
    "primary_body_month_units": expected_total,
    "testing_units": expected_testing,
    "other_function_units": expected_other,
    "binary_group_sum": expected_total,
    "duplicate_assignments": 0,
    "unassigned_units": 0,
    "critical_qc_failures": 0,
}
for key, expected_value in expected.items():
    observed = counts.get(key)
    if observed != expected_value:
        raise SystemExit(
            f"run-py-7f07 metadata mismatch for {key}: "
            f"observed={observed!r}, expected={expected_value!r}"
        )

scope = metadata.get("scientific_scope", {})
if scope.get("binary_taxonomy_frozen") is not True:
    raise SystemExit("run-py-7f07 did not record a frozen binary taxonomy")
if scope.get("outcome_inputs_read") is not False:
    raise SystemExit("run-py-7f07 unexpectedly read outcome inputs")
if scope.get("group_specific_monthly_outcomes_created") is not False:
    raise SystemExit("run-py-7f07 unexpectedly created monthly outcomes")
if scope.get("att_or_uncertainty_computed") is not False:
    raise SystemExit("run-py-7f07 unexpectedly computed ATT or uncertainty")

print("Verified run-py-7f07 outputs:")
print(f"  primary_body_month_units: {counts['primary_body_month_units']}")
print(f"  testing_units: {counts['testing_units']}")
print(f"  other_function_units: {counts['other_function_units']}")
print(f"  binary_group_sum: {counts['binary_group_sum']}")
print(f"  duplicate_assignments: {counts['duplicate_assignments']}")
print(f"  unassigned_units: {counts['unassigned_units']}")
print(f"  critical_qc_failures: {counts['critical_qc_failures']}")
print(f"  taxonomy_status: {metadata['taxonomy_status']}")
print(f"  status: {metadata['status']}")
PY

echo "run-py-7f07 PASS: binary testing versus other_functions taxonomy is frozen."
