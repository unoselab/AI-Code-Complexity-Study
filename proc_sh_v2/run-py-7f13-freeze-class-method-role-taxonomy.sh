#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f13-freeze-class-method-role-taxonomy.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Freeze Category 5 testing-related, Category 6 boilerplate, and Category 7
#   other synchronous class-method assignments. Category 4 is their union.
#
# Independent implementation:
#   - This wrapper follows the logging and validation structure of run-py-7f07.
#   - It does not call run-py-7f07, run-py-7f12, or another shell wrapper.
#   - It reads completed run-py-7f12 outputs as immutable inputs.
#   - It executes only freeze_class_method_role_taxonomy.py.
#   - It rereads exact Git sources to apply conservative boilerplate AST rules.
#
# Frozen testing rule:
#   Preserve the regular-function test-oriented method-name/source-path rule.
#   Add only strong class-specific evidence: a Test-prefixed/suffixed class,
#   exact setup/teardown lifecycle name, *TestCase base, or pytest/unittest
#   decorator. Generic *TestMixin class-base tokens are not testing evidence.
#
# Category identity and scope rule:
#   Category 4 = Category 5 + Category 6 + Category 7.
#   Testing has first priority; boilerplate has second priority; other is the
#   remainder. Category 7 therefore excludes Categories 5 and 6, not Category 4.
#
#   Exclude the six lexically nested/local-class method event contexts before
#   freezing the taxonomy. Retain exactly 3,925 body-month units, partitioned
#   into 1,201 testing plus empirically observed boilerplate and other units.
#
# Inputs:
#   repo_python/run-py-7f12/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f12-class-method-event-context-inventory.csv
#       run-py-7f12-class-method-body-month-unit-inventory.csv
#       qc/run-py-7f12-role-inventory-metadata.json
#       qc/run-py-7f12-role-inventory-checks.csv
#
# Outputs:
#   repo_python/run-py-7f13/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f13-primary-body-month-role-group-assignments.csv
#       run-py-7f13-role-group-summary.csv
#       run-py-7f13-testing-signal-support.csv
#       run-py-7f13-boilerplate-rule-support.csv
#       run-py-7f13-boilerplate-event-contexts.csv
#       run-py-7f13-boilerplate-deterministic-audit.csv
#       run-py-7f13-body-month-context-disagreements.csv
#       run-py-7f13-role-taxonomy-rules.csv
#       run-py-7f13-excluded-lexically-nested-methods.csv
#       run-py-7f13-excluded-broad-test-base-candidates.csv
#       run-py-7f13-role-taxonomy.json
#       run-py-7f13-role-taxonomy-qc.csv
#       run-py-7f13-role-taxonomy-metadata.json
#
# Server files are versionless:
#   proc_scripts/freeze_class_method_role_taxonomy.py
#   proc_sh_v2/run-py-7f13-freeze-class-method-role-taxonomy.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f13-freeze-class-method-role-taxonomy.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f13-freeze-class-method-role-taxonomy.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f13 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/freeze_class_method_role_taxonomy.py}"

SPECIFICATION="${SPECIFICATION:-range100_200}"
SNAPSHOT_METRIC="${SNAPSHOT_METRIC:-python_snapshot_ncloc}"
TIME_AGGREGATION="${TIME_AGGREGATION:-calendar_month}"
PARSER_SCOPE="${PARSER_SCOPE:-parse_clean}"
ANALYSIS_SUFFIX="specifications/${SPECIFICATION}/${SNAPSHOT_METRIC}/${TIME_AGGREGATION}/${PARSER_SCOPE}"

RUN7F12_DIR="${RUN7F12_DIR:-repo_python/run-py-7f12/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
EVENT_INVENTORY="${EVENT_INVENTORY:-${RUN7F12_DIR}/run-py-7f12-class-method-event-context-inventory.csv}"
BODY_MONTH_INVENTORY="${BODY_MONTH_INVENTORY:-${RUN7F12_DIR}/run-py-7f12-class-method-body-month-unit-inventory.csv}"
UPSTREAM_METADATA="${UPSTREAM_METADATA:-${RUN7F12_DIR}/qc/run-py-7f12-role-inventory-metadata.json}"
UPSTREAM_QC="${UPSTREAM_QC:-${RUN7F12_DIR}/qc/run-py-7f12-role-inventory-checks.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f13/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f13}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f13-freeze-class-method-role-taxonomy-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_EVENT_CONTEXTS="${EXPECTED_EVENT_CONTEXTS:-4364}"
EXPECTED_INPUT_BODY_MONTHS="${EXPECTED_INPUT_BODY_MONTHS:-3931}"
EXPECTED_NESTED_EVENTS="${EXPECTED_NESTED_EVENTS:-6}"
EXPECTED_RETAINED_BODY_MONTHS="${EXPECTED_RETAINED_BODY_MONTHS:-3925}"
EXPECTED_TESTING="${EXPECTED_TESTING:-1201}"
EXPECTED_CONTEXT_DISAGREEMENTS="${EXPECTED_CONTEXT_DISAGREEMENTS:-0}"
AUDIT_SAMPLE_SIZE="${AUDIT_SAMPLE_SIZE:-240}"
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

require_nonnegative_integer() {
    local value="$1"
    local label="$2"
    if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${label} must be a nonnegative integer: ${value}" >&2
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
    EXPECTED_EVENT_CONTEXTS \
    EXPECTED_INPUT_BODY_MONTHS \
    EXPECTED_NESTED_EVENTS \
    EXPECTED_RETAINED_BODY_MONTHS \
    EXPECTED_TESTING \
    EXPECTED_CONTEXT_DISAGREEMENTS \
    AUDIT_SAMPLE_SIZE; do
    require_nonnegative_integer "${!integer_name}" "${integer_name}"
done
if (( EXPECTED_INPUT_BODY_MONTHS - EXPECTED_NESTED_EVENTS != EXPECTED_RETAINED_BODY_MONTHS )); then
    echo "ERROR: input body-months minus nested events must equal retained body-months." >&2
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

require_file "${PYTHON_SCRIPT}" "Python class-method taxonomy script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${EVENT_INVENTORY}" "run-py-7f12 event inventory"
    require_file "${BODY_MONTH_INVENTORY}" "run-py-7f12 body-month inventory"
    require_file "${UPSTREAM_METADATA}" "run-py-7f12 metadata"
    require_file "${UPSTREAM_QC}" "run-py-7f12 QC"
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
    echo "run-py-7f13 execution summary"
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
echo "run-py-7f13: freeze testing/boilerplate/other class-method taxonomy"
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
echo "run-py-7f12 event inventory:     ${EVENT_INVENTORY}"
echo "run-py-7f12 body inventory:      ${BODY_MONTH_INVENTORY}"
echo "run-py-7f12 metadata:            ${UPSTREAM_METADATA}"
echo "run-py-7f12 QC:                  ${UPSTREAM_QC}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Expected event contexts:         ${EXPECTED_EVENT_CONTEXTS}"
echo "Expected input body-months:      ${EXPECTED_INPUT_BODY_MONTHS}"
echo "Expected nested exclusions:      ${EXPECTED_NESTED_EVENTS}"
echo "Expected retained body-months:   ${EXPECTED_RETAINED_BODY_MONTHS}"
echo "Expected testing units:          ${EXPECTED_TESTING}"
echo "Expected context disagreements:  ${EXPECTED_CONTEXT_DISAGREEMENTS}"
echo "Audit sample size:                ${AUDIT_SAMPLE_SIZE}"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Taxonomy status:                 FROZEN_PARTITION"
echo "Category identity:               Cat 4 = Cat 5 + Cat 6 + Cat 7"
echo "Repository-month outcomes:       NONE"
echo "ATT/uncertainty estimation:      NONE"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi
if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "run-py-7f13 self-test-only execution complete."
    exit 0
fi

PYTHON_ARGS=(
    --event-inventory "${EVENT_INVENTORY}"
    --body-month-inventory "${BODY_MONTH_INVENTORY}"
    --upstream-metadata "${UPSTREAM_METADATA}"
    --upstream-qc "${UPSTREAM_QC}"
    --output-dir "${OUTPUT_DIR}"
    --expected-event-contexts "${EXPECTED_EVENT_CONTEXTS}"
    --expected-input-body-months "${EXPECTED_INPUT_BODY_MONTHS}"
    --expected-nested-events "${EXPECTED_NESTED_EVENTS}"
    --expected-retained-body-months "${EXPECTED_RETAINED_BODY_MONTHS}"
    --expected-testing "${EXPECTED_TESTING}"
    --expected-context-disagreements "${EXPECTED_CONTEXT_DISAGREEMENTS}"
    --audit-sample-size "${AUDIT_SAMPLE_SIZE}"
)
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite)
fi

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

OUTPUT_ASSIGNMENTS="${OUTPUT_DIR}/run-py-7f13-primary-body-month-role-group-assignments.csv"
OUTPUT_TAXONOMY="${OUTPUT_DIR}/run-py-7f13-role-taxonomy.json"
OUTPUT_QC="${OUTPUT_DIR}/run-py-7f13-role-taxonomy-qc.csv"
OUTPUT_METADATA="${OUTPUT_DIR}/run-py-7f13-role-taxonomy-metadata.json"
for output_file in "${OUTPUT_ASSIGNMENTS}" "${OUTPUT_TAXONOMY}" "${OUTPUT_QC}" "${OUTPUT_METADATA}"; do
    require_file "${output_file}" "run-py-7f13 output"
done

"${PYTHON_BIN}" - \
    "${OUTPUT_ASSIGNMENTS}" \
    "${OUTPUT_QC}" \
    "${EXPECTED_RETAINED_BODY_MONTHS}" \
    "${EXPECTED_TESTING}" <<'PY'
import csv
import sys

assignments_path, qc_path, expected_rows_text, expected_testing_text = sys.argv[1:]
expected_rows = int(expected_rows_text)
expected_testing = int(expected_testing_text)
with open(assignments_path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
counts = {"testing": 0, "boilerplate": 0, "other": 0}
for row in rows:
    group = row["class_method_group"]
    if group not in counts:
        raise SystemExit(f"Unexpected class_method_group: {group!r}")
    counts[group] += 1
with open(qc_path, newline="", encoding="utf-8") as handle:
    qc_rows = list(csv.DictReader(handle))
failed = [row["check_name"] for row in qc_rows if row["passed"].lower() != "true"]
if (
    len(rows) != expected_rows
    or counts["testing"] != expected_testing
    or sum(counts.values()) != expected_rows
    or failed
):
    raise SystemExit(
        f"run-py-7f13 verification failed: rows={len(rows)}, counts={counts}, failed={failed}"
    )
print("run-py-7f13 output verification PASS")
print(f"Retained assignments: {len(rows):,}")
print(f"Testing:             {counts['testing']:,}")
print(f"Boilerplate:         {counts['boilerplate']:,}")
print(f"Other:               {counts['other']:,}")
print(f"Partition identity:  {sum(counts.values()):,} = "
      f"{counts['testing']:,} + {counts['boilerplate']:,} + {counts['other']:,}")
print(f"Failed QC checks:    {len(failed):,}")
PY

echo "run-py-7f13 completed successfully."
