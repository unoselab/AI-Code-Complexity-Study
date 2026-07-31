#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-9b-audit-snapshot-parse-completeness.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Audit the run-py-9a Python AST parse failures before defining a
#   class-method taxonomy or preparing any DiD outcome.
#
# Independent new approach:
#   - Read only raw run-py-9a history-scan outputs.
#   - Classify every Python path with deterministic, outcome-blind rules.
#   - Expand repository-commit failures to the exact repository-month history.
#   - Separate all-file completeness from source-candidate completeness.
#   - Export every unmatched failed path for manual review.
#   - Do not read run-py-7 or run-py-8 output CSV files.
#   - Do not inspect AGC/HWC labels, treatment effects, or confidence intervals.
#
# Inputs:
#   repo_python/run-py-9a/strict/
#     run-py-9a-history-snapshot-manifest.csv
#     run-py-9a-parse-failures.csv
#     run-py-9a-python-file-inventory.csv
#
# Outputs:
#   repo_python/run-py-9b/strict/
#     run-py-9b-parse-failure-classification.csv
#     run-py-9b-unique-failed-blobs.csv
#     run-py-9b-snapshot-completeness.csv
#     run-py-9b-repository-completeness.csv
#     run-py-9b-path-category-summary.csv
#     run-py-9b-failure-category-summary.csv
#     run-py-9b-source-candidate-manual-review.csv
#     run-py-9b-path-classification-rules.csv
#     run-py-9b-audit-qc.csv
#     run-py-9b-audit-metadata.json
#
# Server filenames:
#   proc_scripts/audit_snapshot_parse_completeness.py
#   proc_sh/run-py-9b-audit-snapshot-parse-completeness.sh
#
# Full run:
#   bash proc_sh/run-py-9b-audit-snapshot-parse-completeness.sh
#
# Re-run after reviewing or changing implementation:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh/run-py-9b-audit-snapshot-parse-completeness.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-9b currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/audit_snapshot_parse_completeness.py}"

RUN9A_DIR="${RUN9A_DIR:-repo_python/run-py-9a/${PANEL_VARIANT}}"
HISTORY_SNAPSHOT_MANIFEST="${HISTORY_SNAPSHOT_MANIFEST:-${RUN9A_DIR}/run-py-9a-history-snapshot-manifest.csv}"
PARSE_FAILURES="${PARSE_FAILURES:-${RUN9A_DIR}/run-py-9a-parse-failures.csv}"
PYTHON_FILE_INVENTORY="${PYTHON_FILE_INVENTORY:-${RUN9A_DIR}/run-py-9a-python-file-inventory.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-9b/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs/run-py-9b}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-9b-audit-snapshot-parse-completeness-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: Missing or empty ${label}: ${path}" >&2
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

case "${OVERWRITE_OUTPUT}" in
    0|1) ;;
    *)
        echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
        exit 2
        ;;
esac

if [[ "${PYTHON_BIN}" == */* ]]; then
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "ERROR: Python executable is missing or not executable: ${PYTHON_BIN}" >&2
        exit 2
    fi
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python audit script"
require_file "${HISTORY_SNAPSHOT_MANIFEST}" "run-py-9a history snapshot manifest"
require_file "${PARSE_FAILURES}" "run-py-9a parse-failure inventory"
require_file "${PYTHON_FILE_INVENTORY}" "run-py-9a Python file inventory"

read -r PYTHON_MAJOR PYTHON_MINOR PYTHON_MICRO < <(
    "${PYTHON_BIN}" -c \
        'import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)'
)
PYTHON_VERSION="${PYTHON_MAJOR}.${PYTHON_MINOR}.${PYTHON_MICRO}"
if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 10) )); then
    echo "ERROR: Python 3.10 or newer is required; found ${PYTHON_VERSION}." >&2
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
    echo "run-py-9b execution summary"
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
echo "run-py-9b: outcome-blind snapshot parse-completeness audit"
echo "Started:                    ${START_TIME}"
echo "Project root:               ${PROJECT_ROOT}"
echo "Panel variant:              ${PANEL_VARIANT}"
echo "Python:                     $(command -v "${PYTHON_BIN}")"
echo "Python version:             ${PYTHON_VERSION}"
echo "Python script:              ${PYTHON_SCRIPT}"
echo "Python script SHA:          $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "run-py-9a input directory:  ${RUN9A_DIR}"
echo "Snapshot manifest:          ${HISTORY_SNAPSHOT_MANIFEST}"
echo "Parse failures:             ${PARSE_FAILURES}"
echo "Python file inventory:      ${PYTHON_FILE_INVENTORY}"
echo "Output directory:           ${OUTPUT_DIR}"
echo "Run self-test:              ${RUN_SELF_TEST}"
echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
echo "Prior run-py-7/8 inputs:    NONE"
echo "AGC/HWC outcome inputs:     NONE"
echo "Method taxonomy applied:    NONE"
echo "Log file:                   ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi

python_args=(
    "${PYTHON_SCRIPT}"
    --history-snapshot-manifest "${HISTORY_SNAPSHOT_MANIFEST}"
    --parse-failures "${PARSE_FAILURES}"
    --python-file-inventory "${PYTHON_FILE_INVENTORY}"
    --output-dir "${OUTPUT_DIR}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    python_args+=(--overwrite-output)
fi

"${PYTHON_BIN}" "${python_args[@]}"

expected_outputs=(
    "run-py-9b-parse-failure-classification.csv"
    "run-py-9b-unique-failed-blobs.csv"
    "run-py-9b-snapshot-completeness.csv"
    "run-py-9b-repository-completeness.csv"
    "run-py-9b-path-category-summary.csv"
    "run-py-9b-failure-category-summary.csv"
    "run-py-9b-source-candidate-manual-review.csv"
    "run-py-9b-path-classification-rules.csv"
    "run-py-9b-audit-qc.csv"
    "run-py-9b-audit-metadata.json"
)

for output_name in "${expected_outputs[@]}"; do
    require_file "${OUTPUT_DIR}/${output_name}" "run-py-9b output"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}" <<'PY'
import csv
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
metadata_path = output_dir / "run-py-9b-audit-metadata.json"
qc_path = output_dir / "run-py-9b-audit-qc.csv"

with metadata_path.open("r", encoding="utf-8") as handle:
    metadata = json.load(handle)

with qc_path.open("r", encoding="utf-8", newline="") as handle:
    qc_rows = list(csv.DictReader(handle))

critical_failures = [
    row
    for row in qc_rows
    if row["severity"] == "critical" and row["passed"] != "True"
]
if critical_failures:
    names = ", ".join(row["check_name"] for row in critical_failures)
    raise SystemExit(f"Critical QC failures: {names}")

counts = metadata["counts"]
print("Verified run-py-9b outputs:")
print(f"  status: {metadata['status']}")
print(f"  repository months: {counts['repository_months']}")
print(f"  repositories: {counts['repositories']}")
print(
    "  failure repository-commit files: "
    f"{counts['parse_failure_repository_commit_file_occurrences']}"
)
print(
    "  failure repository-month files: "
    f"{counts['parse_failure_repository_month_file_occurrences']}"
)
print(f"  unique failed blobs: {counts['unique_failed_blobs']}")
print(
    "  source-candidate manual-review rows: "
    f"{counts['source_candidate_manual_review_rows']}"
)
print(f"  critical QC failures: {len(critical_failures)}")
PY
