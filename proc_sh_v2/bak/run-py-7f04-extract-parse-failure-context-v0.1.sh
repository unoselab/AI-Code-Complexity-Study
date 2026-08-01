#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f04-extract-parse-failure-context.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Extract exact historical Git blobs and parse-error context for the
#   run-py-7f03 source-candidate manual-review inventory.
#
# Independent, outcome-blind approach:
#   - Read only run-py-7f03 parse-audit outputs.
#   - Resolve each historical commit:path in the local treatment/control clone.
#   - Verify the Git mode, object type, and expected blob SHA.
#   - Save each unique raw blob without modifying its bytes.
#   - Reproduce the Python 3.12 parse error and save nearby source lines.
#   - Record diagnostic evidence for LFS pointers, symlinks, conflict markers,
#     template markers, notebook magic, and probable Python 2 syntax.
#   - Leave review_decision and review_note blank for manual review.
#   - Do not read AGC/HWC classifications, function-role outcomes, DiD panels,
#     treatment effects, confidence intervals, or prior model output files.
#
# Inputs:
#   repo_python/run-py-7f03/strict/
#     run-py-7f03-source-candidate-manual-review.csv
#     run-py-7f03-parse-failure-classification.csv
#   ../treatment-repos/<OWNER_REPO>/.git
#   ../control-repos/<OWNER_REPO>/.git
#
# Outputs:
#   repo_python/run-py-7f04/strict/
#     run-py-7f04-commit-path-verification.csv
#     run-py-7f04-manual-review-evidence.csv
#     run-py-7f04-extraction-qc.csv
#     run-py-7f04-extraction-metadata.json
#     blobs/<GIT_BLOB_SHA>.py
#     contexts/<GIT_BLOB_SHA>.txt
#
# Server filenames:
#   proc_scripts/extract_parse_failure_context.py
#   proc_sh_v2/run-py-7f04-extract-parse-failure-context.sh
#
# Full run:
#   bash proc_sh_v2/run-py-7f04-extract-parse-failure-context.sh
#
# Re-run after reviewing or changing the implementation:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f04-extract-parse-failure-context.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-7f04 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/extract_parse_failure_context.py}"

RUN7F03_DIR="${RUN7F03_DIR:-repo_python/run-py-7f03/${PANEL_VARIANT}}"
MANUAL_REVIEW_INPUT="${MANUAL_REVIEW_INPUT:-${RUN7F03_DIR}/run-py-7f03-source-candidate-manual-review.csv}"
FAILURE_CLASSIFICATION_INPUT="${FAILURE_CLASSIFICATION_INPUT:-${RUN7F03_DIR}/run-py-7f03-parse-failure-classification.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f04/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f04}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f04-extract-parse-failure-context-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

CONTEXT_LINES="${CONTEXT_LINES:-8}"
EXPECTED_REVIEW_ROWS="${EXPECTED_REVIEW_ROWS:-20}"
EXPECTED_COMMIT_OCCURRENCES="${EXPECTED_COMMIT_OCCURRENCES:-61}"
EXPECTED_PYTHON_MAJOR_MINOR="${EXPECTED_PYTHON_MAJOR_MINOR:-3.12}"
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

require_directory() {
    local path="$1"
    local label="$2"
    if [[ ! -d "${path}" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
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

case "${RUN_SELF_TEST}" in
    0|1) ;;
    *)
        echo "ERROR: RUN_SELF_TEST must be 0 or 1." >&2
        exit 2
        ;;
esac

case "${SELF_TEST_ONLY}" in
    0|1) ;;
    *)
        echo "ERROR: SELF_TEST_ONLY must be 0 or 1." >&2
        exit 2
        ;;
esac
if [[ "${SELF_TEST_ONLY}" == "1" && "${RUN_SELF_TEST}" != "1" ]]; then
    echo "ERROR: SELF_TEST_ONLY=1 requires RUN_SELF_TEST=1." >&2
    exit 2
fi

case "${OVERWRITE_OUTPUT}" in
    0|1) ;;
    *)
        echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
        exit 2
        ;;
esac

require_nonnegative_integer "${CONTEXT_LINES}" "CONTEXT_LINES"
require_nonnegative_integer "${EXPECTED_REVIEW_ROWS}" "EXPECTED_REVIEW_ROWS"
require_nonnegative_integer "${EXPECTED_COMMIT_OCCURRENCES}" "EXPECTED_COMMIT_OCCURRENCES"
if (( CONTEXT_LINES > 100 )); then
    echo "ERROR: CONTEXT_LINES must be at most 100." >&2
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

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is required for historical blob extraction." >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python extraction script"
require_file "${MANUAL_REVIEW_INPUT}" "run-py-7f03 manual-review input"
require_file "${FAILURE_CLASSIFICATION_INPUT}" "run-py-7f03 failure classification"
require_directory "${TREATMENT_CLONE_DIR}" "treatment clone directory"
require_directory "${CONTROL_CLONE_DIR}" "control clone directory"

read -r PYTHON_MAJOR PYTHON_MINOR PYTHON_MICRO < <(
    "${PYTHON_BIN}" -c \
        'import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)'
)
PYTHON_VERSION="${PYTHON_MAJOR}.${PYTHON_MINOR}.${PYTHON_MICRO}"
PYTHON_MAJOR_MINOR="${PYTHON_MAJOR}.${PYTHON_MINOR}"
if [[ "${PYTHON_MAJOR_MINOR}" != "${EXPECTED_PYTHON_MAJOR_MINOR}" ]]; then
    echo "ERROR: Python ${EXPECTED_PYTHON_MAJOR_MINOR}.x is required to reproduce run-py-7f02 parse errors; found ${PYTHON_VERSION}." >&2
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
    echo "run-py-7f04 execution summary"
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
echo "run-py-7f04: outcome-blind Git blob and parse-error context extraction"
echo "Started:                       ${START_TIME}"
echo "Project root:                  ${PROJECT_ROOT}"
echo "Panel variant:                 ${PANEL_VARIANT}"
echo "Python:                        $(command -v "${PYTHON_BIN}")"
echo "Python version:                ${PYTHON_VERSION}"
echo "Python script:                 ${PYTHON_SCRIPT}"
echo "Python script SHA:             $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Manual-review input:           ${MANUAL_REVIEW_INPUT}"
echo "Failure classification input:  ${FAILURE_CLASSIFICATION_INPUT}"
echo "Treatment clone directory:     ${TREATMENT_CLONE_DIR}"
echo "Control clone directory:       ${CONTROL_CLONE_DIR}"
echo "Output directory:              ${OUTPUT_DIR}"
echo "Context lines each side:       ${CONTEXT_LINES}"
echo "Expected review rows:          ${EXPECTED_REVIEW_ROWS}"
echo "Expected commit occurrences:   ${EXPECTED_COMMIT_OCCURRENCES}"
echo "Run self-test:                 ${RUN_SELF_TEST}"
echo "Self-test only:                ${SELF_TEST_ONLY}"
echo "Overwrite output:              ${OVERWRITE_OUTPUT}"
echo "AGC/HWC outcome inputs:        NONE"
echo "DiD outcome inputs:            NONE"
echo "Function-role taxonomy:        NONE"
echo "Log file:                      ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    echo "SELF_TEST_ONLY=1; production extraction was not run."
    exit 0
fi

python_args=(
    "${PYTHON_SCRIPT}"
    --manual-review-input "${MANUAL_REVIEW_INPUT}"
    --failure-classification-input "${FAILURE_CLASSIFICATION_INPUT}"
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
    --control-clone-dir "${CONTROL_CLONE_DIR}"
    --output-dir "${OUTPUT_DIR}"
    --context-lines "${CONTEXT_LINES}"
    --expected-review-rows "${EXPECTED_REVIEW_ROWS}"
    --expected-commit-occurrences "${EXPECTED_COMMIT_OCCURRENCES}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    python_args+=(--overwrite-output)
fi

"${PYTHON_BIN}" "${python_args[@]}"

expected_outputs=(
    "run-py-7f04-commit-path-verification.csv"
    "run-py-7f04-manual-review-evidence.csv"
    "run-py-7f04-extraction-qc.csv"
    "run-py-7f04-extraction-metadata.json"
)

for output_name in "${expected_outputs[@]}"; do
    require_file "${OUTPUT_DIR}/${output_name}" "run-py-7f04 output"
done
require_directory "${OUTPUT_DIR}/blobs" "raw blob output directory"
require_directory "${OUTPUT_DIR}/contexts" "context output directory"

"${PYTHON_BIN}" - \
    "${OUTPUT_DIR}" \
    "${EXPECTED_REVIEW_ROWS}" \
    "${EXPECTED_COMMIT_OCCURRENCES}" <<'PY'
import csv
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
expected_reviews = int(sys.argv[2])
expected_commits = int(sys.argv[3])

with (output_dir / "run-py-7f04-extraction-metadata.json").open(
    "r", encoding="utf-8"
) as handle:
    metadata = json.load(handle)

with (output_dir / "run-py-7f04-extraction-qc.csv").open(
    "r", encoding="utf-8", newline=""
) as handle:
    qc_rows = list(csv.DictReader(handle))

critical_failures = [
    row
    for row in qc_rows
    if row["severity"] == "critical" and row["passed"] != "True"
]
if critical_failures:
    names = ", ".join(row["check_name"] for row in critical_failures)
    raise SystemExit(f"Critical QC failures: {names}")
if metadata["status"] != "PASS":
    raise SystemExit(f"Unexpected metadata status: {metadata['status']}")

counts = metadata["counts"]
if counts["manual_review_rows"] != expected_reviews:
    raise SystemExit(
        f"Unexpected manual-review rows: {counts['manual_review_rows']} != {expected_reviews}"
    )
if counts["commit_path_occurrences"] != expected_commits:
    raise SystemExit(
        "Unexpected commit-path occurrences: "
        f"{counts['commit_path_occurrences']} != {expected_commits}"
    )

blob_files = list((output_dir / "blobs").glob("*.py"))
context_files = list((output_dir / "contexts").glob("*.txt"))
if len(blob_files) != expected_reviews:
    raise SystemExit(f"Unexpected raw blob files: {len(blob_files)} != {expected_reviews}")
if len(context_files) != expected_reviews:
    raise SystemExit(
        f"Unexpected context files: {len(context_files)} != {expected_reviews}"
    )

print("Verified run-py-7f04 outputs:")
print(f"  status: {metadata['status']}")
print(f"  manual-review rows: {counts['manual_review_rows']}")
print(f"  repositories: {counts['repositories']}")
print(f"  repository paths: {counts['repository_paths']}")
print(f"  commit-path occurrences: {counts['commit_path_occurrences']}")
print(
    "  verified commit-path occurrences: "
    f"{counts['verified_commit_path_occurrences']}"
)
print(f"  extracted blobs: {counts['extracted_blobs']}")
print(f"  parse failures reproduced: {counts['parse_failures_reproduced']}")
print(f"  Git LFS pointers: {counts['git_lfs_pointers']}")
print(f"  symlink-mode blobs: {counts['symlink_mode_blobs']}")
print(f"  probable Python 2 syntax blobs: {counts['probable_python2_syntax_blobs']}")
print(f"  critical QC failures: {counts['critical_qc_failures']}")
PY
