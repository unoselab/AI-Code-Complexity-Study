#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f05-adjudicate-parse-failure-sources.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Freeze the outcome-blind manual adjudications for the 11 residual
#   source-candidate blobs verified by run-py-7f04 v2.
#
# Independent, outcome-blind approach:
#   - Read only run-py-7f04-manual-review-evidence.csv.
#   - Require exact review ID, repository, path, and Git blob SHA identities.
#   - Record the locked 2026-07-31 manual source classifications.
#   - Expand each blob's audited months and deduplicate repository-month keys.
#   - Preserve an explicit conservative exclusion policy for later robustness.
#   - Do not rewrite Python 2 or IPython-style source.
#   - Do not repair malformed or incomplete source.
#   - Do not read AGC/HWC classifications, function-role outcomes, DiD panels,
#     treatment effects, confidence intervals, or prior model results.
#
# Input:
#   repo_python/run-py-7f04/strict/
#     run-py-7f04-manual-review-evidence.csv
#
# Outputs:
#   repo_python/run-py-7f05/strict/
#     run-py-7f05-manual-adjudication.csv
#     run-py-7f05-affected-repository-months.csv
#     run-py-7f05-affected-repositories.csv
#     run-py-7f05-adjudication-summary.csv
#     run-py-7f05-adjudication-qc.csv
#     run-py-7f05-adjudication-metadata.json
#
# Full run:
#   bash proc_sh_v2/run-py-7f05-adjudicate-parse-failure-sources.sh
#
# Re-run after reviewing the implementation:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f05-adjudicate-parse-failure-sources.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f05 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/adjudicate_parse_failure_sources.py}"

RUN7F04_DIR="${RUN7F04_DIR:-repo_python/run-py-7f04/${PANEL_VARIANT}}"
MANUAL_REVIEW_EVIDENCE="${MANUAL_REVIEW_EVIDENCE:-${RUN7F04_DIR}/run-py-7f04-manual-review-evidence.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f05/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f05}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f05-adjudicate-parse-failure-sources-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

EXPECTED_REVIEW_ROWS="${EXPECTED_REVIEW_ROWS:-11}"
EXPECTED_COMMIT_OCCURRENCES="${EXPECTED_COMMIT_OCCURRENCES:-51}"
EXPECTED_AFFECTED_REPOSITORY_MONTHS="${EXPECTED_AFFECTED_REPOSITORY_MONTHS:-66}"
EXPECTED_AFFECTED_REPOSITORIES="${EXPECTED_AFFECTED_REPOSITORIES:-6}"
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
        echo "ERROR: ${label} must be a non-negative integer: ${value}" >&2
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

require_nonnegative_integer "${EXPECTED_REVIEW_ROWS}" "EXPECTED_REVIEW_ROWS"
require_nonnegative_integer "${EXPECTED_COMMIT_OCCURRENCES}" "EXPECTED_COMMIT_OCCURRENCES"
require_nonnegative_integer "${EXPECTED_AFFECTED_REPOSITORY_MONTHS}" "EXPECTED_AFFECTED_REPOSITORY_MONTHS"
require_nonnegative_integer "${EXPECTED_AFFECTED_REPOSITORIES}" "EXPECTED_AFFECTED_REPOSITORIES"

if [[ "${PYTHON_BIN}" == */* ]]; then
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "ERROR: Python executable is missing or not executable: ${PYTHON_BIN}" >&2
        exit 2
    fi
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python adjudication script"
if [[ "${SELF_TEST_ONLY}" != "1" ]]; then
    require_file "${MANUAL_REVIEW_EVIDENCE}" "run-py-7f04 manual-review evidence"
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
    echo "run-py-7f05 execution summary"
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

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(sys.version.split()[0])')"

echo "================================================================================"
echo "run-py-7f05: outcome-blind residual-source manual adjudication"
echo "Started:                                ${START_TIME}"
echo "Project root:                           ${PROJECT_ROOT}"
echo "Panel variant:                          ${PANEL_VARIANT}"
echo "Python:                                 $(command -v "${PYTHON_BIN}")"
echo "Python version:                         ${PYTHON_VERSION}"
echo "Python script:                          ${PYTHON_SCRIPT}"
echo "Python script SHA:                      $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Manual-review evidence:                 ${MANUAL_REVIEW_EVIDENCE}"
echo "Output directory:                       ${OUTPUT_DIR}"
echo "Expected review rows:                   ${EXPECTED_REVIEW_ROWS}"
echo "Expected commit occurrences:            ${EXPECTED_COMMIT_OCCURRENCES}"
echo "Expected affected repository-months:    ${EXPECTED_AFFECTED_REPOSITORY_MONTHS}"
echo "Expected affected repositories:         ${EXPECTED_AFFECTED_REPOSITORIES}"
echo "Run self-test:                          ${RUN_SELF_TEST}"
echo "Self-test only:                         ${SELF_TEST_ONLY}"
echo "Overwrite output:                       ${OVERWRITE_OUTPUT}"
echo "AGC/HWC outcome inputs:                 NONE"
echo "Function-role outcome inputs:           NONE"
echo "DiD panel inputs:                       NONE"
echo "ATT/confidence-interval inputs:          NONE"
echo "Log file:                               ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "SELF_TEST_ONLY=1; production adjudication was not run."
    exit 0
fi

python_args=(
    "${PYTHON_SCRIPT}"
    --manual-review-evidence "${MANUAL_REVIEW_EVIDENCE}"
    --output-dir "${OUTPUT_DIR}"
    --expected-review-rows "${EXPECTED_REVIEW_ROWS}"
    --expected-commit-occurrences "${EXPECTED_COMMIT_OCCURRENCES}"
    --expected-affected-repository-months "${EXPECTED_AFFECTED_REPOSITORY_MONTHS}"
    --expected-affected-repositories "${EXPECTED_AFFECTED_REPOSITORIES}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    python_args+=(--overwrite-output)
fi

"${PYTHON_BIN}" "${python_args[@]}"

expected_outputs=(
    "run-py-7f05-manual-adjudication.csv"
    "run-py-7f05-affected-repository-months.csv"
    "run-py-7f05-affected-repositories.csv"
    "run-py-7f05-adjudication-summary.csv"
    "run-py-7f05-adjudication-qc.csv"
    "run-py-7f05-adjudication-metadata.json"
)

for output_name in "${expected_outputs[@]}"; do
    require_file "${OUTPUT_DIR}/${output_name}" "run-py-7f05 output"
done

"${PYTHON_BIN}" - \
    "${OUTPUT_DIR}" \
    "${EXPECTED_REVIEW_ROWS}" \
    "${EXPECTED_AFFECTED_REPOSITORY_MONTHS}" \
    "${EXPECTED_AFFECTED_REPOSITORIES}" <<'PY'
import csv
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
expected_reviews = int(sys.argv[2])
expected_months = int(sys.argv[3])
expected_repositories = int(sys.argv[4])

with (output_dir / "run-py-7f05-adjudication-metadata.json").open(
    "r", encoding="utf-8"
) as handle:
    metadata = json.load(handle)
with (output_dir / "run-py-7f05-adjudication-qc.csv").open(
    "r", encoding="utf-8", newline=""
) as handle:
    qc_rows = list(csv.DictReader(handle))

if metadata.get("schema_version") != "run-py-7f05-v1":
    raise SystemExit("Unexpected run-py-7f05 metadata schema version")
if metadata.get("status") != "PASS":
    raise SystemExit("run-py-7f05 metadata status is not PASS")
counts = metadata.get("counts", {})
expected = {
    "adjudicated_blobs": expected_reviews,
    "unique_affected_repository_months": expected_months,
    "unique_affected_repositories": expected_repositories,
    "critical_qc_failures": 0,
}
for key, expected_value in expected.items():
    if int(counts.get(key, -1)) != expected_value:
        raise SystemExit(
            f"run-py-7f05 metadata count mismatch for {key}: "
            f"{counts.get(key)!r} != {expected_value}"
        )
failed = [
    row["check_name"]
    for row in qc_rows
    if row.get("severity") == "critical" and row.get("passed") != "True"
]
if failed:
    raise SystemExit(f"Critical run-py-7f05 QC failures: {failed}")

print("Verified run-py-7f05 outputs:")
for key, expected_value in expected.items():
    print(f"  {key}: {expected_value}")
print("  status: PASS")
PY
