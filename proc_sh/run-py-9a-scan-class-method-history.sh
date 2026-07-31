#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-9a-scan-class-method-history.sh
# -----------------------------------------------------------------------------
# Purpose:
#   Scan the exact Python repository-month Git snapshots for the matched
#   treatment and control repositories before defining class-method groups.
#
# New approach:
#   - Read repository-month history inputs from run-py-2a only.
#   - Resolve every latest_commit directly in the local Git clones.
#   - Parse each distinct tracked Python Git blob once through a reusable cache.
#   - Record raw AST parents, lexical scopes, nesting depth, names, parameters,
#     and decorators without assigning a method taxonomy.
#   - Do not read run-py-7 or run-py-8 output CSV files.
#   - Do not inspect AGC/HWC classifications, ATT estimates, or confidence
#     intervals.
#
# Inputs:
#   repo_python/run-py-2a/strict/treatment/data/ts_repos_monthly.csv
#   repo_python/run-py-2a/strict/control/data/ts_repos_monthly.csv
#   ../treatment-repos/<owner_repo> local Git clones
#   ../control-repos/<owner_repo> local Git clones
#
# Primary outputs:
#   repo_python/run-py-9a/strict/
#     run-py-9a-history-snapshot-manifest.csv
#     run-py-9a-python-file-inventory.csv
#     run-py-9a-python-function-inventory.csv
#     run-py-9a-decorator-inventory.csv
#     run-py-9a-decorator-structure-counts.csv
#     run-py-9a-ast-parent-patterns.csv
#     run-py-9a-function-structure-counts.csv
#     run-py-9a-parse-failures.csv
#     run-py-9a-repository-scan-qc.csv
#     run-py-9a-scan-metadata.json
#
# Reusable cache:
#   repo_python/tmp/run-py-9a/strict/
#     run-py-9a-blob-parse-cache-v1.sqlite3
#
# Full run:
#   RUN_SELF_TEST=1 bash proc_sh/run-py-9a-scan-class-method-history.sh
#
# Targeted smoke run:
#   REPOSITORIES="owner/repo" \
#   MAX_UNIQUE_COMMITS=2 \
#   OUTPUT_DIR="repo_python/tmp/run-py-9a/smoke/strict" \
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh/run-py-9a-scan-class-method-history.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
    echo "ERROR: run-py-9a-v1 currently supports PANEL_VARIANT=strict only." >&2
    exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/scan_class_method_history.py}"

TREATMENT_INPUT="${TREATMENT_INPUT:-repo_python/run-py-2a/${PANEL_VARIANT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_INPUT="${CONTROL_INPUT:-repo_python/run-py-2a/${PANEL_VARIANT}/control/data/ts_repos_monthly.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-9a/${PANEL_VARIANT}}"
CACHE_DB="${CACHE_DB:-repo_python/tmp/run-py-9a/${PANEL_VARIANT}/run-py-9a-blob-parse-cache-v1.sqlite3}"
LOG_DIR="${LOG_DIR:-logs/run-py-9a}"
RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-9a-scan-class-method-history-v1-${PANEL_VARIANT}-${RUN_TIMESTAMP}.log}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
MAX_UNIQUE_COMMITS="${MAX_UNIQUE_COMMITS:-0}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
REPOSITORIES="${REPOSITORIES:-}"

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

if ! [[ "${MAX_UNIQUE_COMMITS}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: MAX_UNIQUE_COMMITS must be a nonnegative integer." >&2
    exit 2
fi

if ! [[ "${PROGRESS_EVERY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PROGRESS_EVERY must be a positive integer." >&2
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

require_file "${PYTHON_SCRIPT}" "Python scanner"
require_file "${TREATMENT_INPUT}" "treatment repository-month input"
require_file "${CONTROL_INPUT}" "control repository-month input"
require_dir "${TREATMENT_CLONE_DIR}" "treatment clone directory"
require_dir "${CONTROL_CLONE_DIR}" "control clone directory"

read -r PYTHON_MAJOR PYTHON_MINOR PYTHON_MICRO < <(
    "${PYTHON_BIN}" -c \
        'import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)'
)
PYTHON_VERSION="${PYTHON_MAJOR}.${PYTHON_MINOR}.${PYTHON_MICRO}"
if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 12) )); then
    echo "ERROR: Python 3.12 or newer is required; found ${PYTHON_VERSION}." >&2
    exit 2
fi

mkdir -p "${LOG_DIR}" "$(dirname "${CACHE_DB}")"
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
    echo "run-py-9a-v1 execution summary"
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
echo "run-py-9a-v1: outcome-blind class-method history scan"
echo "Started:                  ${START_TIME}"
echo "Project root:             ${PROJECT_ROOT}"
echo "Panel variant:            ${PANEL_VARIANT}"
echo "Python:                   $(command -v "${PYTHON_BIN}")"
echo "Python version:           ${PYTHON_VERSION}"
echo "Python script:            ${PYTHON_SCRIPT}"
echo "Python script SHA:        $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Treatment history input:  ${TREATMENT_INPUT}"
echo "Control history input:    ${CONTROL_INPUT}"
echo "Treatment clones:         ${TREATMENT_CLONE_DIR}"
echo "Control clones:           ${CONTROL_CLONE_DIR}"
echo "Output directory:         ${OUTPUT_DIR}"
echo "Blob parse cache:         ${CACHE_DB}"
echo "Repository filter:        ${REPOSITORIES:-<all>}"
echo "Maximum unique commits:   ${MAX_UNIQUE_COMMITS:-0}"
echo "Progress interval:        ${PROGRESS_EVERY}"
echo "Run self-test:            ${RUN_SELF_TEST}"
echo "Overwrite output:         ${OVERWRITE_OUTPUT}"
echo "Prior outcome CSV inputs: NONE"
echo "Method taxonomy applied:  NONE"
echo "Log file:                 ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test-only
fi

python_args=(
    "${PYTHON_SCRIPT}"
    --treatment-input "${TREATMENT_INPUT}"
    --control-input "${CONTROL_INPUT}"
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
    --control-clone-dir "${CONTROL_CLONE_DIR}"
    --output-dir "${OUTPUT_DIR}"
    --cache-db "${CACHE_DB}"
    --max-unique-commits "${MAX_UNIQUE_COMMITS}"
    --progress-every "${PROGRESS_EVERY}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    python_args+=(--overwrite-output)
fi

if [[ -n "${REPOSITORIES}" ]]; then
    IFS=',' read -r -a repository_array <<< "${REPOSITORIES}"
    for repository in "${repository_array[@]}"; do
        repository="${repository#"${repository%%[![:space:]]*}"}"
        repository="${repository%"${repository##*[![:space:]]}"}"
        if [[ -n "${repository}" ]]; then
            python_args+=(--repo "${repository}")
        fi
    done
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${python_args[@]}"

expected_outputs=(
    "${OUTPUT_DIR}/run-py-9a-history-snapshot-manifest.csv"
    "${OUTPUT_DIR}/run-py-9a-python-file-inventory.csv"
    "${OUTPUT_DIR}/run-py-9a-python-function-inventory.csv"
    "${OUTPUT_DIR}/run-py-9a-decorator-inventory.csv"
    "${OUTPUT_DIR}/run-py-9a-decorator-structure-counts.csv"
    "${OUTPUT_DIR}/run-py-9a-ast-parent-patterns.csv"
    "${OUTPUT_DIR}/run-py-9a-function-structure-counts.csv"
    "${OUTPUT_DIR}/run-py-9a-parse-failures.csv"
    "${OUTPUT_DIR}/run-py-9a-repository-scan-qc.csv"
    "${OUTPUT_DIR}/run-py-9a-scan-metadata.json"
)

for expected_file in "${expected_outputs[@]}"; do
    require_file "${expected_file}" "expected run-py-9a output"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}/run-py-9a-scan-metadata.json" \
    "${OUTPUT_DIR}/run-py-9a-repository-scan-qc.csv" <<'PY'
import csv
import json
import sys
from pathlib import Path

metadata_path = Path(sys.argv[1])
checks_path = Path(sys.argv[2])

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
with checks_path.open("r", encoding="utf-8", newline="") as handle:
    checks = list(csv.DictReader(handle))

failed_critical = [
    row
    for row in checks
    if row["severity"] == "critical"
    and row["passed"].strip().lower() != "true"
]
if not str(metadata.get("status", "")).startswith("PASS"):
    raise SystemExit(f"run-py-9a metadata status is not PASS: {metadata.get('status')}")
if failed_critical:
    raise SystemExit(
        "run-py-9a has failed critical checks:\n"
        + "\n".join(str(row) for row in failed_critical)
    )

print("================================================================================")
print("run-py-9a-v1 output verification")
print(f"Status:                    {metadata['status']}")
print(f"Repository-month rows:     {metadata['counts']['repository_month_rows']}")
print(f"Repositories:              {metadata['counts']['repositories']}")
print(f"Unique repository commits: {metadata['counts']['unique_repository_commits']}")
print(f"Function inventory rows:   {metadata['counts']['function_inventory_rows']}")
print(f"Decorator inventory rows:  {metadata['counts']['decorator_inventory_rows']}")
print(f"Parse-failure rows:         {metadata['counts']['parse_failure_rows']}")
print(f"Critical failed checks:     {metadata['counts']['critical_failed_checks']}")
print("================================================================================")
PY

echo "run-py-9a-v1 PASS: raw history inventories are ready for taxonomy review."
