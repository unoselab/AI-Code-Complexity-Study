#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f14-prepare-class-method-role-group-did-inputs.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Prepare four zero-inclusive DiD input panels on one identical locked
#   repository-month model sample:
#
#   Category 4: all synchronous class methods;
#   Category 5: testing-related synchronous class methods;
#   Category 6: boilerplate synchronous class methods;
#   Category 7: other methods excluding Categories 5 and 6.
#
# Independent implementation:
#   - This wrapper follows the logging and validation structure of run-py-7f08.
#   - It does not call run-py-7e, run-py-7f13, or another shell wrapper.
#   - It reads completed run-py-7e and run-py-7f13 artifacts as immutable inputs.
#   - It executes only prepare_class_method_role_group_did_inputs.py.
#
# Construction contract:
#   - Retain exactly 1,521 Python-snapshot-NCLOC model-ready rows.
#   - Aggregate frozen run-py-7f13 assignments by repository-month and group.
#   - Left join group counts and replace missing counts with zero.
#   - Require Category 5 + Category 6 + Category 7 = Category 4 on all rows.
#   - Do not estimate ATT, standard errors, confidence intervals, or p-values.
#
# Inputs:
#   repo_python/run-py-7e/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv
#
#   repo_python/run-py-7f13/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f13-primary-body-month-role-group-assignments.csv
#       run-py-7f13-role-taxonomy.json
#       run-py-7f13-role-taxonomy-qc.csv
#       run-py-7f13-role-taxonomy-metadata.json
#
# Outputs:
#   repo_python/run-py-7f14/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f14-did-input-all-class-methods.csv
#       run-py-7f14-did-input-testing-class-methods.csv
#       run-py-7f14-did-input-boilerplate-class-methods.csv
#       run-py-7f14-did-input-other-class-methods.csv
#       run-py-7f14-zero-inclusive-class-method-outcomes-wide.csv
#       run-py-7f14-outcome-summary.csv
#       run-py-7f14-did-input-qc.csv
#       run-py-7f14-did-input-metadata.json
#
# Server files are versionless:
#   proc_scripts/prepare_class_method_role_group_did_inputs.py
#   proc_sh_v2/run-py-7f14-prepare-class-method-role-group-did-inputs.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f14-prepare-class-method-role-group-did-inputs.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f14-prepare-class-method-role-group-did-inputs.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f14 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/aicomplexity/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_class_method_role_group_did_inputs.py}"

SPECIFICATION="${SPECIFICATION:-range100_200}"
SNAPSHOT_METRIC="${SNAPSHOT_METRIC:-python_snapshot_ncloc}"
TIME_AGGREGATION="${TIME_AGGREGATION:-calendar_month}"
PARSER_SCOPE="${PARSER_SCOPE:-parse_clean}"
ANALYSIS_SUFFIX="specifications/${SPECIFICATION}/${SNAPSHOT_METRIC}/${TIME_AGGREGATION}/${PARSER_SCOPE}"

RUN7E_DIR="${RUN7E_DIR:-repo_python/run-py-7e/${PANEL_VARIANT}/specifications/${SPECIFICATION}}"
BASE_PANEL="${BASE_PANEL:-${RUN7E_DIR}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"

RUN7F13_DIR="${RUN7F13_DIR:-repo_python/run-py-7f13/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
PRIMARY_ASSIGNMENTS="${PRIMARY_ASSIGNMENTS:-${RUN7F13_DIR}/run-py-7f13-primary-body-month-role-group-assignments.csv}"
TAXONOMY_METADATA="${TAXONOMY_METADATA:-${RUN7F13_DIR}/run-py-7f13-role-taxonomy-metadata.json}"
TAXONOMY_QC="${TAXONOMY_QC:-${RUN7F13_DIR}/run-py-7f13-role-taxonomy-qc.csv}"
ROLE_TAXONOMY="${ROLE_TAXONOMY:-${RUN7F13_DIR}/run-py-7f13-role-taxonomy.json}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f14/${PANEL_VARIANT}/${ANALYSIS_SUFFIX}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f14}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f14-prepare-class-method-role-group-did-inputs-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_BASE_PANEL_ROWS="${EXPECTED_BASE_PANEL_ROWS:-1536}"
EXPECTED_MODEL_READY_ROWS="${EXPECTED_MODEL_READY_ROWS:-1521}"
EXPECTED_BODY_MONTHS="${EXPECTED_BODY_MONTHS:-3925}"
EXPECTED_TESTING="${EXPECTED_TESTING:-1201}"
EXPECTED_ALL_POSITIVE_ROWS="${EXPECTED_ALL_POSITIVE_ROWS:-497}"
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
    EXPECTED_ALL_POSITIVE_ROWS; do
    require_positive_integer "${!integer_name}" "${integer_name}"
done
if [[ "${PYTHON_BIN}" == */* ]]; then
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "ERROR: Python executable is missing or not executable: ${PYTHON_BIN}" >&2
        exit 2
    fi
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python class-method DiD-input script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${BASE_PANEL}" "run-py-7e parse-clean base panel"
    require_file "${PRIMARY_ASSIGNMENTS}" "run-py-7f13 assignments"
    require_file "${TAXONOMY_METADATA}" "run-py-7f13 taxonomy metadata"
    require_file "${TAXONOMY_QC}" "run-py-7f13 taxonomy QC"
    require_file "${ROLE_TAXONOMY}" "run-py-7f13 role taxonomy"
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
    echo "run-py-7f14 execution summary"
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
echo "run-py-7f14: prepare zero-inclusive class-method DiD inputs"
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
echo "run-py-7f13 assignments:         ${PRIMARY_ASSIGNMENTS}"
echo "run-py-7f13 taxonomy metadata:   ${TAXONOMY_METADATA}"
echo "run-py-7f13 taxonomy QC:         ${TAXONOMY_QC}"
echo "run-py-7f13 role taxonomy:       ${ROLE_TAXONOMY}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Expected base-panel rows:        ${EXPECTED_BASE_PANEL_ROWS}"
echo "Expected model-ready rows:       ${EXPECTED_MODEL_READY_ROWS}"
echo "Expected body-month units:       ${EXPECTED_BODY_MONTHS}"
echo "Expected testing units:          ${EXPECTED_TESTING}"
echo "Expected Category 4 positive:    ${EXPECTED_ALL_POSITIVE_ROWS}"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Zero-inclusive categories:       4=all, 5=testing, 6=boilerplate, 7=other"
echo "Category identity:               Cat 4 = Cat 5 + Cat 6 + Cat 7"
echo "ATT/uncertainty estimation:      NONE"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi
if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "run-py-7f14 self-test-only execution complete."
    exit 0
fi

PYTHON_ARGS=(
    --base-panel "${BASE_PANEL}"
    --assignments "${PRIMARY_ASSIGNMENTS}"
    --taxonomy-metadata "${TAXONOMY_METADATA}"
    --taxonomy-qc "${TAXONOMY_QC}"
    --role-taxonomy "${ROLE_TAXONOMY}"
    --output-dir "${OUTPUT_DIR}"
    --expected-base-panel-rows "${EXPECTED_BASE_PANEL_ROWS}"
    --expected-model-ready-rows "${EXPECTED_MODEL_READY_ROWS}"
    --expected-body-months "${EXPECTED_BODY_MONTHS}"
    --expected-testing "${EXPECTED_TESTING}"
    --expected-all-positive-rows "${EXPECTED_ALL_POSITIVE_ROWS}"
)
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite)
fi

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

OUTPUT_ALL="${OUTPUT_DIR}/run-py-7f14-did-input-all-class-methods.csv"
OUTPUT_TESTING="${OUTPUT_DIR}/run-py-7f14-did-input-testing-class-methods.csv"
OUTPUT_BOILERPLATE="${OUTPUT_DIR}/run-py-7f14-did-input-boilerplate-class-methods.csv"
OUTPUT_OTHER="${OUTPUT_DIR}/run-py-7f14-did-input-other-class-methods.csv"
OUTPUT_WIDE="${OUTPUT_DIR}/run-py-7f14-zero-inclusive-class-method-outcomes-wide.csv"
OUTPUT_SUMMARY="${OUTPUT_DIR}/run-py-7f14-outcome-summary.csv"
OUTPUT_QC="${OUTPUT_DIR}/run-py-7f14-did-input-qc.csv"
OUTPUT_METADATA="${OUTPUT_DIR}/run-py-7f14-did-input-metadata.json"
for output_file in \
    "${OUTPUT_ALL}" \
    "${OUTPUT_TESTING}" \
    "${OUTPUT_BOILERPLATE}" \
    "${OUTPUT_OTHER}" \
    "${OUTPUT_WIDE}" \
    "${OUTPUT_SUMMARY}" \
    "${OUTPUT_QC}" \
    "${OUTPUT_METADATA}"; do
    require_file "${output_file}" "run-py-7f14 output"
done

"${PYTHON_BIN}" - \
    "${OUTPUT_ALL}" \
    "${OUTPUT_TESTING}" \
    "${OUTPUT_BOILERPLATE}" \
    "${OUTPUT_OTHER}" \
    "${OUTPUT_WIDE}" \
    "${OUTPUT_SUMMARY}" \
    "${OUTPUT_QC}" \
    "${EXPECTED_MODEL_READY_ROWS}" \
    "${EXPECTED_BODY_MONTHS}" \
    "${EXPECTED_TESTING}" \
    "${EXPECTED_ALL_POSITIVE_ROWS}" <<'PY'
import csv
import sys

(
    all_path,
    testing_path,
    boilerplate_path,
    other_path,
    wide_path,
    summary_path,
    qc_path,
    expected_rows_text,
    expected_body_text,
    expected_testing_text,
    expected_all_positive_text,
) = sys.argv[1:]
expected_rows = int(expected_rows_text)
expected_body = int(expected_body_text)
expected_testing = int(expected_testing_text)
expected_all_positive = int(expected_all_positive_text)
count_column = "npr_agc_class_method_unique_bodies"
observed_by_path = {}
for path in [all_path, testing_path, boilerplate_path, other_path]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts = [int(row[count_column]) for row in rows]
    observed = (sum(counts), sum(value > 0 for value in counts), sum(value == 0 for value in counts))
    if len(rows) != expected_rows or observed[1] + observed[2] != expected_rows:
        raise SystemExit(f"run-py-7f14 panel verification failed: {path}, rows={len(rows)}, observed={observed}")
    observed_by_path[path] = observed
if observed_by_path[all_path] != (
    expected_body,
    expected_all_positive,
    expected_rows - expected_all_positive,
):
    raise SystemExit(f"Unexpected Category 4 summary: {observed_by_path[all_path]}")
if observed_by_path[testing_path][0] != expected_testing:
    raise SystemExit(f"Unexpected Category 5 total: {observed_by_path[testing_path]}")
if (
    observed_by_path[boilerplate_path][0] + observed_by_path[other_path][0]
    != expected_body - expected_testing
):
    raise SystemExit("Categories 6 and 7 do not partition all non-testing units")
with open(wide_path, newline="", encoding="utf-8") as handle:
    wide_rows = list(csv.DictReader(handle))
if len(wide_rows) != expected_rows or any(int(row["all_minus_role_group_sum"]) != 0 for row in wide_rows):
    raise SystemExit("run-py-7f14 wide reconciliation failed")
with open(qc_path, newline="", encoding="utf-8") as handle:
    qc_rows = list(csv.DictReader(handle))
failed = [row["check_name"] for row in qc_rows if row["passed"].lower() != "true"]
if failed:
    raise SystemExit(f"run-py-7f14 QC failed: {failed}")
print("run-py-7f14 output verification PASS")
print(f"Rows per category:       {expected_rows:,}")
with open(summary_path, newline="", encoding="utf-8") as handle:
    summary_rows = list(csv.DictReader(handle))
by_category = {row["outcome_category"]: row for row in summary_rows if row["dataset_source"] == "all"}
for category in ["4", "5", "6", "7"]:
    row = by_category[category]
    print(
        f"Category {category} total/pos/0:  "
        f"{row['total_unique_bodies']}/{row['positive_rows']}/{row['zero_rows']}"
    )
print("Reconciliation errors:   0")
print(f"Failed QC checks:        {len(failed):,}")
PY

echo "run-py-7f14 completed successfully."
