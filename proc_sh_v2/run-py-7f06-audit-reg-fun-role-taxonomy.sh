#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f06-audit-reg-fun-role-taxonomy.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Audit candidate mutually exclusive semantic roles for synchronous regular
#   module functions before freezing role-specific outcomes or estimating ATT.
#
# Independent audit approach:
#   - Use run-py-7f02 v2 as the outcome-blind full-history structure universe.
#   - Restrict that universe to synchronous module-level functions.
#   - Apply candidate name, path, and decorator signals fixed in the Python
#     source before execution.
#   - Extract 240 deterministic source samples from immutable Git blobs for
#     manual rule review.
#   - Apply the same fixed signals to the locked run-py-7f01 inventory only to
#     verify exhaustive, one-to-one assignment of all 2,249 body-month units.
#   - Require the completed run-py-7f05 residual-source adjudication as a gate.
#   - Keep decorator use as a structural flag, never as a primary role.
#   - Do not create role-specific zero-inclusive repository-month outcomes.
#   - Do not read or estimate ATT, standard errors, confidence intervals, or
#     p-values.
#
# Inputs:
#   repo_python/run-py-7f02/strict/
#     run-py-7f02-python-function-inventory.csv
#     run-py-7f02-scan-metadata.json
#   repo_python/run-py-7f01/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f01-function-event-context-inventory.csv
#       run-py-7f01-body-month-outcome-unit-inventory.csv
#       qc/run-py-7f01-role-inventory-metadata.json
#   repo_python/run-py-7f05/strict/
#     run-py-7f05-adjudication-metadata.json
#   ../treatment-repos and ../control-repos local Git clones
#
# Outputs:
#   repo_python/run-py-7f06/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f06-candidate-role-rules.csv
#       run-py-7f06-candidate-taxonomy.json
#       run-py-7f06-full-history-candidate-role-summary.csv
#       run-py-7f06-full-history-candidate-role-by-source.csv
#       run-py-7f06-full-history-signal-summary.csv
#       run-py-7f06-full-history-signal-overlaps.csv
#       run-py-7f06-outcome-blind-source-audit-samples.csv
#       run-py-7f06-primary-body-month-candidate-assignments.csv
#       run-py-7f06-primary-candidate-role-summary.csv
#       run-py-7f06-primary-candidate-role-support.csv
#       run-py-7f06-primary-signal-summary.csv
#       run-py-7f06-primary-signal-overlaps.csv
#       run-py-7f06-taxonomy-audit-qc.csv
#       run-py-7f06-taxonomy-audit-metadata.json
#
# Server files are versionless:
#   proc_scripts/audit_reg_fun_role_taxonomy.py
#   proc_sh_v2/run-py-7f06-audit-reg-fun-role-taxonomy.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f06-audit-reg-fun-role-taxonomy.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f06-audit-reg-fun-role-taxonomy.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f06 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse313/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/audit_reg_fun_role_taxonomy.py}"

RUN7F02_DIR="${RUN7F02_DIR:-repo_python/run-py-7f02/${PANEL_VARIANT}}"
FULL_HISTORY_FUNCTION_INVENTORY="${FULL_HISTORY_FUNCTION_INVENTORY:-${RUN7F02_DIR}/run-py-7f02-python-function-inventory.csv}"
FULL_HISTORY_METADATA="${FULL_HISTORY_METADATA:-${RUN7F02_DIR}/run-py-7f02-scan-metadata.json}"

RUN7F01_DIR="${RUN7F01_DIR:-repo_python/run-py-7f01/${PANEL_VARIANT}/specifications/range100_200/python_snapshot_ncloc/calendar_month/parse_clean}"
PRIMARY_EVENT_INVENTORY="${PRIMARY_EVENT_INVENTORY:-${RUN7F01_DIR}/run-py-7f01-function-event-context-inventory.csv}"
PRIMARY_BODY_MONTH_INVENTORY="${PRIMARY_BODY_MONTH_INVENTORY:-${RUN7F01_DIR}/run-py-7f01-body-month-outcome-unit-inventory.csv}"
PRIMARY_METADATA="${PRIMARY_METADATA:-${RUN7F01_DIR}/qc/run-py-7f01-role-inventory-metadata.json}"

RUN7F05_DIR="${RUN7F05_DIR:-repo_python/run-py-7f05/${PANEL_VARIANT}}"
ADJUDICATION_METADATA="${ADJUDICATION_METADATA:-${RUN7F05_DIR}/run-py-7f05-adjudication-metadata.json}"

TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f06/${PANEL_VARIANT}/specifications/range100_200/python_snapshot_ncloc/calendar_month/parse_clean}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f06}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f06-audit-reg-fun-role-taxonomy-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_FULL_HISTORY_FUNCTION_ROWS="${EXPECTED_FULL_HISTORY_FUNCTION_ROWS:-2899926}"
EXPECTED_PRIMARY_EVENT_CONTEXTS="${EXPECTED_PRIMARY_EVENT_CONTEXTS:-2569}"
EXPECTED_PRIMARY_BODY_MONTHS="${EXPECTED_PRIMARY_BODY_MONTHS:-2249}"
EXPECTED_AUDIT_SAMPLES="${EXPECTED_AUDIT_SAMPLES:-240}"
AUDIT_SOURCE_MAX_CHARACTERS="${AUDIT_SOURCE_MAX_CHARACTERS:-20000}"
PROGRESS_EVERY="${PROGRESS_EVERY:-250000}"
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

require_dir() {
    local path="$1"
    local label="$2"
    if [[ ! -d "${path}" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
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

require_positive_integer "${EXPECTED_FULL_HISTORY_FUNCTION_ROWS}" "EXPECTED_FULL_HISTORY_FUNCTION_ROWS"
require_positive_integer "${EXPECTED_PRIMARY_EVENT_CONTEXTS}" "EXPECTED_PRIMARY_EVENT_CONTEXTS"
require_positive_integer "${EXPECTED_PRIMARY_BODY_MONTHS}" "EXPECTED_PRIMARY_BODY_MONTHS"
require_positive_integer "${EXPECTED_AUDIT_SAMPLES}" "EXPECTED_AUDIT_SAMPLES"
require_positive_integer "${AUDIT_SOURCE_MAX_CHARACTERS}" "AUDIT_SOURCE_MAX_CHARACTERS"
require_positive_integer "${PROGRESS_EVERY}" "PROGRESS_EVERY"

if [[ "${PYTHON_BIN}" == */* ]]; then
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "ERROR: Python executable is missing or not executable: ${PYTHON_BIN}" >&2
        exit 2
    fi
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python taxonomy-audit script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${FULL_HISTORY_FUNCTION_INVENTORY}" "run-py-7f02 function inventory"
    require_file "${FULL_HISTORY_METADATA}" "run-py-7f02 metadata"
    require_file "${PRIMARY_EVENT_INVENTORY}" "run-py-7f01 event inventory"
    require_file "${PRIMARY_BODY_MONTH_INVENTORY}" "run-py-7f01 body-month inventory"
    require_file "${PRIMARY_METADATA}" "run-py-7f01 metadata"
    require_file "${ADJUDICATION_METADATA}" "run-py-7f05 adjudication metadata"
    require_dir "${TREATMENT_CLONE_DIR}" "treatment clone directory"
    require_dir "${CONTROL_CLONE_DIR}" "control clone directory"
fi

read -r PYTHON_MAJOR PYTHON_MINOR PYTHON_MICRO < <(
    "${PYTHON_BIN}" -c \
        'import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)'
)
PYTHON_VERSION="${PYTHON_MAJOR}.${PYTHON_MINOR}.${PYTHON_MICRO}"
if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 13) )); then
    echo "ERROR: Python 3.13 or newer is required; found ${PYTHON_VERSION}." >&2
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
    echo "run-py-7f06 execution summary"
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
echo "run-py-7f06: outcome-blind function-role taxonomy audit"
echo "Started:                                ${START_TIME}"
echo "Project root:                           ${PROJECT_ROOT}"
echo "Panel variant:                          ${PANEL_VARIANT}"
echo "Python:                                 $(command -v "${PYTHON_BIN}")"
echo "Python version:                         ${PYTHON_VERSION}"
echo "Python script:                          ${PYTHON_SCRIPT}"
echo "Python script SHA:                      $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Full-history function inventory:        ${FULL_HISTORY_FUNCTION_INVENTORY}"
echo "Full-history metadata:                  ${FULL_HISTORY_METADATA}"
echo "Primary event inventory:                ${PRIMARY_EVENT_INVENTORY}"
echo "Primary body-month inventory:           ${PRIMARY_BODY_MONTH_INVENTORY}"
echo "Primary inventory metadata:             ${PRIMARY_METADATA}"
echo "Residual-source adjudication metadata:  ${ADJUDICATION_METADATA}"
echo "Treatment clones:                       ${TREATMENT_CLONE_DIR}"
echo "Control clones:                         ${CONTROL_CLONE_DIR}"
echo "Output directory:                       ${OUTPUT_DIR}"
echo "Expected full-history function rows:    ${EXPECTED_FULL_HISTORY_FUNCTION_ROWS}"
echo "Expected primary event contexts:        ${EXPECTED_PRIMARY_EVENT_CONTEXTS}"
echo "Expected primary body-month units:      ${EXPECTED_PRIMARY_BODY_MONTHS}"
echo "Expected source audit samples:          ${EXPECTED_AUDIT_SAMPLES}"
echo "Audit source maximum characters:        ${AUDIT_SOURCE_MAX_CHARACTERS}"
echo "Progress interval:                      ${PROGRESS_EVERY}"
echo "Run self-test:                          ${RUN_SELF_TEST}"
echo "Self-test only:                         ${SELF_TEST_ONLY}"
echo "Overwrite output:                       ${OVERWRITE_OUTPUT}"
echo "Role taxonomy status:                   CANDIDATE_NOT_FROZEN"
echo "Role-specific monthly outcomes:         NONE"
echo "ATT/uncertainty inputs:                  NONE"
echo "Log file:                               ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "SELF_TEST_ONLY=1; production taxonomy audit was not run."
    exit 0
fi

python_args=(
    "${PYTHON_SCRIPT}"
    --full-history-function-inventory "${FULL_HISTORY_FUNCTION_INVENTORY}"
    --full-history-metadata "${FULL_HISTORY_METADATA}"
    --primary-event-inventory "${PRIMARY_EVENT_INVENTORY}"
    --primary-body-month-inventory "${PRIMARY_BODY_MONTH_INVENTORY}"
    --primary-metadata "${PRIMARY_METADATA}"
    --adjudication-metadata "${ADJUDICATION_METADATA}"
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
    --control-clone-dir "${CONTROL_CLONE_DIR}"
    --project-root "${PROJECT_ROOT}"
    --output-dir "${OUTPUT_DIR}"
    --expected-full-history-function-rows "${EXPECTED_FULL_HISTORY_FUNCTION_ROWS}"
    --expected-primary-event-contexts "${EXPECTED_PRIMARY_EVENT_CONTEXTS}"
    --expected-primary-body-months "${EXPECTED_PRIMARY_BODY_MONTHS}"
    --expected-audit-samples "${EXPECTED_AUDIT_SAMPLES}"
    --audit-source-max-characters "${AUDIT_SOURCE_MAX_CHARACTERS}"
    --progress-every "${PROGRESS_EVERY}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    python_args+=(--overwrite-output)
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${python_args[@]}"

expected_outputs=(
    "run-py-7f06-candidate-role-rules.csv"
    "run-py-7f06-candidate-taxonomy.json"
    "run-py-7f06-full-history-candidate-role-summary.csv"
    "run-py-7f06-full-history-candidate-role-by-source.csv"
    "run-py-7f06-full-history-signal-summary.csv"
    "run-py-7f06-full-history-signal-overlaps.csv"
    "run-py-7f06-outcome-blind-source-audit-samples.csv"
    "run-py-7f06-primary-body-month-candidate-assignments.csv"
    "run-py-7f06-primary-candidate-role-summary.csv"
    "run-py-7f06-primary-candidate-role-support.csv"
    "run-py-7f06-primary-signal-summary.csv"
    "run-py-7f06-primary-signal-overlaps.csv"
    "run-py-7f06-taxonomy-audit-qc.csv"
    "run-py-7f06-taxonomy-audit-metadata.json"
)

for output_name in "${expected_outputs[@]}"; do
    require_file "${OUTPUT_DIR}/${output_name}" "run-py-7f06 output"
done

"${PYTHON_BIN}" - \
    "${OUTPUT_DIR}" \
    "${EXPECTED_FULL_HISTORY_FUNCTION_ROWS}" \
    "${EXPECTED_PRIMARY_BODY_MONTHS}" \
    "${EXPECTED_AUDIT_SAMPLES}" <<'PY'
import csv
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
expected_full_rows = int(sys.argv[2])
expected_primary_units = int(sys.argv[3])
expected_audit_samples = int(sys.argv[4])

metadata = json.loads(
    (output_dir / "run-py-7f06-taxonomy-audit-metadata.json").read_text(
        encoding="utf-8"
    )
)
with (output_dir / "run-py-7f06-taxonomy-audit-qc.csv").open(
    "r", encoding="utf-8", newline=""
) as handle:
    qc_rows = list(csv.DictReader(handle))
with (output_dir / "run-py-7f06-primary-candidate-role-summary.csv").open(
    "r", encoding="utf-8", newline=""
) as handle:
    role_rows = list(csv.DictReader(handle))

if metadata.get("schema_version") != "run-py-7f06-v1":
    raise SystemExit("Unexpected run-py-7f06 metadata schema version")
if metadata.get("status") != "PASS":
    raise SystemExit("run-py-7f06 metadata status is not PASS")
if metadata.get("taxonomy_status") != "CANDIDATE_NOT_FROZEN":
    raise SystemExit("run-py-7f06 taxonomy was incorrectly marked frozen")

counts = metadata.get("counts", {})
expected = {
    "full_history_function_rows": expected_full_rows,
    "audit_samples": expected_audit_samples,
    "primary_body_month_units": expected_primary_units,
    "primary_category_sum": expected_primary_units,
    "critical_qc_failures": 0,
}
for key, expected_value in expected.items():
    if int(counts.get(key, -1)) != expected_value:
        raise SystemExit(
            f"run-py-7f06 metadata count mismatch for {key}: "
            f"{counts.get(key)!r} != {expected_value}"
        )

failed = [
    row["check_name"]
    for row in qc_rows
    if row.get("severity") == "critical" and row.get("passed") != "True"
]
if failed:
    raise SystemExit(f"Critical run-py-7f06 QC failures: {failed}")

role_total = sum(int(row["body_month_units"]) for row in role_rows)
if role_total != expected_primary_units:
    raise SystemExit(
        f"Primary candidate role sum mismatch: {role_total} != {expected_primary_units}"
    )

print("Verified run-py-7f06 outputs:")
print(f"  full_history_function_rows: {expected_full_rows}")
print(
    "  full_history_synchronous_module_functions: "
    f"{counts['full_history_synchronous_module_functions']}"
)
print(f"  audit_samples: {expected_audit_samples}")
print(f"  primary_body_month_units: {expected_primary_units}")
print(f"  primary_category_sum: {role_total}")
print("  duplicate_assignments: 0")
print("  unassigned_units: 0")
print("  taxonomy_status: CANDIDATE_NOT_FROZEN")
print("  status: PASS")
print("Candidate primary-role counts (audit only):")
for row in role_rows:
    print(
        f"  {row['candidate_primary_role']}: "
        f"{row['body_month_units']}"
    )
PY

echo "run-py-7f06 PASS: candidate rules and outcome-blind audit samples are ready for manual taxonomy review."
