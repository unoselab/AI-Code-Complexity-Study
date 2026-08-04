#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-c04 v3: Compute whole-repository NCLOC with cloc
# ============================================================
#
# Purpose:
#   Measure historical repository snapshots selected by run-x-c03.
#   The repository sample is the paper's Python-primary treatment setting,
#   but the metric covers the entire repository rather than Python files only.
#
# Metric definition:
#   For every historical repository-commit snapshot:
#     1. materialize all tracked regular files without changing the clone;
#     2. run cloc across all cloc-recognized language/file types;
#     3. preserve one normalized CSV row per language; and
#     4. sum the language-level `code` values into
#        ncloc_local_cloc_whole_repo.
#
# Important distinction:
#   - data_baseline_backup/repos.csv is used only for the C01 sample scope.
#   - C04 does not sum repos.csv:repo_languages metadata.
#   - C04 generates a new cloc CSV for each historical Git snapshot.
#
# Historical Git safety:
#   - git archive reads the requested commit into a temporary directory;
#   - the main clone checkout is never changed;
#   - no git checkout, fetch, pull, reset, clean, or worktree command is used;
#   - symlinks are audited but are not materialized;
#   - submodule contents are not recursively downloaded or counted.
#
# Required inputs:
#   repo_x01/run-x-c03/python_primary_unique_snapshot_manifest.csv
#     One row per unique repository-commit snapshot. Expected: 1,828 rows.
#
#   repo_x01/run-x-c03/python_primary_repo_month_history_manifest.csv
#     Mapping from the unique snapshots back to 2,411 repository-month rows.
#
# Main outputs:
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_snapshot_results.csv
#     One row per processed unique snapshot.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_language_results.csv
#     One row per snapshot and cloc-recognized language/file type.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_repo_month_results.csv
#     Snapshot metrics mapped back to all 2,411 clone/history-available rows.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_completed_manifest.csv
#     Full C03 unique-snapshot manifest with current C04 status and metrics.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_failures.csv
#     Snapshot-level scan failures and diagnostics.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_scan_qc.csv
#     Input, aggregation, mapping, and output integrity checks.
#
#   repo_x01/tmp/run-x-c04/python_primary_whole_repo_cloc_summary.csv
#     Compact run summary.
#
# Full run:
#   bash proc_sh_x01/run-x-c04-compute-whole-repo-ncloc-cloc.sh
#
# Structural dry run:
#   DRY_RUN=1 bash proc_sh_x01/run-x-c04-compute-whole-repo-ncloc-cloc.sh
#
# One-snapshot smoke test:
#   LIMIT=1 bash proc_sh_x01/run-x-c04-compute-whole-repo-ncloc-cloc.sh
#
# Resume:
#   Re-run the same command. Prior snapshots with a complete successful
#   snapshot row and the expected number of language rows are skipped unless
#   ANALYSIS_AGAIN=1.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   CLOC_BIN=/path/to/cloc
#   WORKERS=2
#   GIT_TIMEOUT_SECONDS=600
#   CLOC_TIMEOUT_SECONDS=900
#   SAVE_EVERY=10
#   PROGRESS_EVERY=25
#   START_ORDER=1
#   LIMIT=0
#   SCOPE_ROLE=treatment|control
#   REPO_NAME=owner/repository
#   EXCLUDE_DIRS=""
#   ANALYSIS_AGAIN=0
#   DRY_RUN=0
#   KEEP_TEMP=0
#   KEEP_RAW_CLOC_CSV=0
#   FAIL_ON_UNRESOLVED=1
#   STRICT_EXPECTED_COUNTS=1
#   REQUIRE_COMPLETE_OUTPUT=auto|0|1
#   LOG_LEVEL=INFO
#   EXPECTED_ZERO_NCLOC_SNAPSHOTS=5
#   EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS=1
#   EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS=4
#   EXPECTED_PRESERVED_V2_SUCCESSES=1823
#   EXPECTED_V3_SUCCESSES=5
#
# C04 v3 corrections:
#   - preserves all 1,823 successful v2 snapshot rows during resume;
#   - detects an empty Git tree before archive extraction and records NCLOC=0;
#   - treats cloc return code 0 with no CSV/stdout/stderr as a valid
#     no-recognized-language snapshot with NCLOC=0;
#   - records explicit Git-tree, cloc return-code, and zero-NCLOC diagnostics;
#   - requires the five C04d-confirmed zero snapshots in the full-run QC; and
#   - full runs require 1,828 successful snapshots and 2,411 repo-month rows.
#
# Exclusion policy:
#   EXCLUDE_DIRS is empty by default. Therefore, all tracked regular files are
#   presented to cloc. cloc itself ignores unsupported or binary file types.
#   Set EXCLUDE_DIRS only for an explicitly documented robustness run.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-c04"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-compute-whole-repo-ncloc-cloc-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
CLOC_BIN="${CLOC_BIN:-cloc}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/compute_whole_repo_ncloc_cloc.py}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-repo_x01/run-x-c03/python_primary_unique_snapshot_manifest.csv}"
HISTORY_MANIFEST_FILE="${HISTORY_MANIFEST_FILE:-repo_x01/run-x-c03/python_primary_repo_month_history_manifest.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
CLOC_TEMP_ROOT="${CLOC_TEMP_ROOT:-${TMP_OUTPUT_DIR}/cloc-work}"
RAW_CLOC_CSV_ROOT="${RAW_CLOC_CSV_ROOT:-${MAIN_OUTPUT_DIR}/raw-cloc-csv}"

SNAPSHOT_RESULTS_OUTPUT="${SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_snapshot_results.csv}"
LANGUAGE_RESULTS_OUTPUT="${LANGUAGE_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_language_results.csv}"
REPO_MONTH_RESULTS_OUTPUT="${REPO_MONTH_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_repo_month_results.csv}"
COMPLETED_MANIFEST_OUTPUT="${COMPLETED_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_completed_manifest.csv}"
FAILURES_OUTPUT="${FAILURES_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_failures.csv}"
SCAN_QC_OUTPUT="${SCAN_QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_whole_repo_cloc_scan_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_primary_whole_repo_cloc_summary.csv}"

WORKERS="${WORKERS:-2}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-600}"
CLOC_TIMEOUT_SECONDS="${CLOC_TIMEOUT_SECONDS:-900}"
SAVE_EVERY="${SAVE_EVERY:-10}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
SCOPE_ROLE="${SCOPE_ROLE:-}"
REPO_NAME="${REPO_NAME:-}"
EXCLUDE_DIRS="${EXCLUDE_DIRS:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
DRY_RUN="${DRY_RUN:-0}"
KEEP_TEMP="${KEEP_TEMP:-0}"
KEEP_RAW_CLOC_CSV="${KEEP_RAW_CLOC_CSV:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
REQUIRE_COMPLETE_OUTPUT="${REQUIRE_COMPLETE_OUTPUT:-auto}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_UNIQUE_SNAPSHOTS="${EXPECTED_UNIQUE_SNAPSHOTS:-1828}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-1004}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-824}"
EXPECTED_REPO_MONTH_ROWS="${EXPECTED_REPO_MONTH_ROWS:-2411}"
EXPECTED_TREATMENT_REPO_MONTH_ROWS="${EXPECTED_TREATMENT_REPO_MONTH_ROWS:-1174}"
EXPECTED_CONTROL_REPO_MONTH_ROWS="${EXPECTED_CONTROL_REPO_MONTH_ROWS:-1237}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-242}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-116}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-126}"
EXPECTED_ZERO_NCLOC_SNAPSHOTS="${EXPECTED_ZERO_NCLOC_SNAPSHOTS:-5}"
EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS="${EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS:-1}"
EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS="${EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS:-4}"
EXPECTED_PRESERVED_V2_SUCCESSES="${EXPECTED_PRESERVED_V2_SUCCESSES:-1823}"
EXPECTED_V3_SUCCESSES="${EXPECTED_V3_SUCCESSES:-5}"

for numeric_value in \
  "${WORKERS}" \
  "${GIT_TIMEOUT_SECONDS}" \
  "${CLOC_TIMEOUT_SECONDS}" \
  "${SAVE_EVERY}" \
  "${PROGRESS_EVERY}" \
  "${START_ORDER}" \
  "${LIMIT}" \
  "${EXPECTED_UNIQUE_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPO_MONTH_ROWS}" \
  "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}" \
  "${EXPECTED_CONTROL_REPO_MONTH_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}" \
  "${EXPECTED_ZERO_NCLOC_SNAPSHOTS}" \
  "${EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS}" \
  "${EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS}" \
  "${EXPECTED_PRESERVED_V2_SUCCESSES}" \
  "${EXPECTED_V3_SUCCESSES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

for positive_name in WORKERS GIT_TIMEOUT_SECONDS CLOC_TIMEOUT_SECONDS SAVE_EVERY PROGRESS_EVERY START_ORDER; do
  if [[ "${!positive_name}" -lt 1 ]]; then
    echo "ERROR: ${positive_name} must be at least 1." >&2
    exit 1
  fi
done

for boolean_name in \
  ANALYSIS_AGAIN \
  DRY_RUN \
  KEEP_TEMP \
  KEEP_RAW_CLOC_CSV \
  FAIL_ON_UNRESOLVED \
  STRICT_EXPECTED_COUNTS; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ -n "${SCOPE_ROLE}" && "${SCOPE_ROLE}" != "treatment" && "${SCOPE_ROLE}" != "control" ]]; then
  echo "ERROR: SCOPE_ROLE must be treatment, control, or empty." >&2
  exit 1
fi

if [[ "${REQUIRE_COMPLETE_OUTPUT}" == "auto" ]]; then
  if [[ "${DRY_RUN}" == "0" && "${LIMIT}" == "0" && "${START_ORDER}" == "1" && -z "${SCOPE_ROLE}" && -z "${REPO_NAME}" ]]; then
    REQUIRE_COMPLETE_OUTPUT="1"
  else
    REQUIRE_COMPLETE_OUTPUT="0"
  fi
fi
if [[ "${REQUIRE_COMPLETE_OUTPUT}" != "0" && "${REQUIRE_COMPLETE_OUTPUT}" != "1" ]]; then
  echo "ERROR: REQUIRE_COMPLETE_OUTPUT must be auto, 0, or 1." >&2
  exit 1
fi

# A filtered smoke test validates only the selected snapshots. A full run must
# fail if any snapshot or repo-month remains unresolved.
if [[ "${REQUIRE_COMPLETE_OUTPUT}" == "0" ]]; then
  FAIL_ON_UNRESOLVED="0"
fi

for required_file in "${PY_SCRIPT}" "${SNAPSHOT_MANIFEST_FILE}" "${HISTORY_MANIFEST_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v "${CLOC_BIN}" >/dev/null 2>&1; then
  echo "ERROR: cloc is required but was not found: ${CLOC_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${CLOC_TEMP_ROOT}"
if [[ "${KEEP_RAW_CLOC_CSV}" == "1" ]]; then
  mkdir -p "${RAW_CLOC_CSV_ROOT}"
fi

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
CLOC_VERSION="$("${CLOC_BIN}" --version 2>&1 | head -n 1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
SNAPSHOT_MANIFEST_SHA256="$(sha256sum "${SNAPSHOT_MANIFEST_FILE}" | awk '{print $1}')"
HISTORY_MANIFEST_SHA256="$(sha256sum "${HISTORY_MANIFEST_FILE}" | awk '{print $1}')"

mkdir -p "$(dirname "${LOG_FILE}")"
exec > >(tee -a "${LOG_FILE}") 2>&1

{
  echo "============================================================"
  echo "${RUN_LABEL}: compute whole-repository NCLOC with cloc"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "cloc:                            ${CLOC_BIN} (${CLOC_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Unique snapshot manifest:        ${SNAPSHOT_MANIFEST_FILE}"
  echo "Unique manifest SHA256:          ${SNAPSHOT_MANIFEST_SHA256}"
  echo "Repo-month history manifest:     ${HISTORY_MANIFEST_FILE}"
  echo "History manifest SHA256:         ${HISTORY_MANIFEST_SHA256}"
  echo "Workers:                         ${WORKERS}"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "cloc timeout seconds:            ${CLOC_TIMEOUT_SECONDS}"
  echo "Custom excluded directories:     ${EXCLUDE_DIRS:-none}"
  echo "Keep raw cloc CSV:               ${KEEP_RAW_CLOC_CSV}"
  echo "Expected unique snapshots:       ${EXPECTED_UNIQUE_SNAPSHOTS}"
  echo "Expected repo-month rows:        ${EXPECTED_REPO_MONTH_ROWS}"
  echo "Expected zero-NCLOC snapshots:   ${EXPECTED_ZERO_NCLOC_SNAPSHOTS}"
  echo "Expected empty Git trees:        ${EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS}"
  echo "Expected no-language snapshots:  ${EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS}"
  echo "Expected preserved v2 successes: ${EXPECTED_PRESERVED_V2_SUCCESSES}"
  echo "Expected v3 repaired successes:   ${EXPECTED_V3_SUCCESSES}"
  echo "Require complete output:          ${REQUIRE_COMPLETE_OUTPUT}"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Language results:                ${LANGUAGE_RESULTS_OUTPUT}"
  echo "Repo-month results:              ${REPO_MONTH_RESULTS_OUTPUT}"
  echo "Completed manifest:              ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Failures:                        ${FAILURES_OUTPUT}"
  echo "QC:                              ${SCAN_QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Materialize historical snapshots and run whole-repository cloc"
  echo "------------------------------------------------------------"
}

COMMAND=(
  "${PYTHON_BIN}" "${PY_SCRIPT}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --history-manifest-file "${HISTORY_MANIFEST_FILE}"
  --snapshot-results-output "${SNAPSHOT_RESULTS_OUTPUT}"
  --language-results-output "${LANGUAGE_RESULTS_OUTPUT}"
  --repo-month-results-output "${REPO_MONTH_RESULTS_OUTPUT}"
  --completed-manifest-output "${COMPLETED_MANIFEST_OUTPUT}"
  --failures-output "${FAILURES_OUTPUT}"
  --qc-output "${SCAN_QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --temp-root "${CLOC_TEMP_ROOT}"
  --raw-cloc-csv-root "${RAW_CLOC_CSV_ROOT}"
  --cloc-bin "${CLOC_BIN}"
  --workers "${WORKERS}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --cloc-timeout-seconds "${CLOC_TIMEOUT_SECONDS}"
  --save-every "${SAVE_EVERY}"
  --progress-every "${PROGRESS_EVERY}"
  --start-order "${START_ORDER}"
  --limit "${LIMIT}"
  --scope-role "${SCOPE_ROLE}"
  --repo-name "${REPO_NAME}"
  --exclude-dirs "${EXCLUDE_DIRS}"
  --analysis-again "${ANALYSIS_AGAIN}"
  --dry-run "${DRY_RUN}"
  --keep-temp "${KEEP_TEMP}"
  --keep-raw-cloc-csv "${KEEP_RAW_CLOC_CSV}"
  --fail-on-unresolved "${FAIL_ON_UNRESOLVED}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --require-complete-output "${REQUIRE_COMPLETE_OUTPUT}"
  --expected-unique-snapshots "${EXPECTED_UNIQUE_SNAPSHOTS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --expected-repo-month-rows "${EXPECTED_REPO_MONTH_ROWS}"
  --expected-treatment-repo-month-rows "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}"
  --expected-control-repo-month-rows "${EXPECTED_CONTROL_REPO_MONTH_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-zero-ncloc-snapshots "${EXPECTED_ZERO_NCLOC_SNAPSHOTS}"
  --expected-empty-git-tree-snapshots "${EXPECTED_EMPTY_GIT_TREE_SNAPSHOTS}"
  --expected-no-recognized-language-snapshots "${EXPECTED_NO_RECOGNIZED_LANGUAGE_SNAPSHOTS}"
  --expected-preserved-v2-successes "${EXPECTED_PRESERVED_V2_SUCCESSES}"
  --expected-v3-successes "${EXPECTED_V3_SUCCESSES}"
  --log-level "${LOG_LEVEL}"
)

printf 'Command:'
printf ' %q' "${COMMAND[@]}"
printf '\n\n'

set +e
"${COMMAND[@]}"
STATUS=$?
set -e

if [[ "${STATUS}" -ne 0 ]]; then
  echo "ERROR: ${RUN_LABEL} failed with status ${STATUS}." >&2
  exit "${STATUS}"
fi

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Language results:                ${LANGUAGE_RESULTS_OUTPUT}"
  echo "Repo-month results:              ${REPO_MONTH_RESULTS_OUTPUT}"
  echo "Completed manifest:              ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Failures:                        ${FAILURES_OUTPUT}"
  echo "QC:                              ${SCAN_QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       confirm 1,828/1,828 coverage, then prepare C04b paper-taxonomy mapping"
  echo "============================================================"
}
