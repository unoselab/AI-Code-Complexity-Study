#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a05b v1: Recover missing Model A NCLOC values
# ============================================================
#
# Purpose:
#   Recover missing whole-repository SonarQube NCLOC values for the
#   Python-eligible run-x-a05 pooled panel before running Borusyak DiD.
#
# Target scope:
#   - 128 Python-eligible repo-month rows with missing ncloc;
#   - deduplicated into 28 repository-commit historical snapshots;
#   - 10 treatment snapshots affecting 36 rows;
#   - 18 control snapshots affecting 92 rows.
#
# Safety:
#   The Python implementation creates a detached temporary Git worktree for
#   each historical commit. It does not checkout, reset, or clean the main
#   treatment/control clone working tree.
#
# SonarQube scope:
#   Whole-repository scan for Model A ncloc. This is not the Python-only
#   ncloc_py scan planned for Model C.
#
# Required environment:
#   SONAR_HOST=http://localhost:9000
#   SONAR_TOKEN=<token>
#   SONAR_PATH=/path/to/sonar-scanner
#     or SONAR_SCANNER_PATH=/path/to/sonar-scanner
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_panel_python_pooled.csv
#
# Main outputs:
#   repo_x01/run-x-a05b/missing_ncloc_snapshot_manifest.csv
#   repo_x01/run-x-a05b/missing_ncloc_snapshot_results.csv
#   repo_x01/run-x-a05b/missing_ncloc_repo_month_patch.csv
#   repo_x01/run-x-a05b/missing_ncloc_unresolved.csv
#
# QC output:
#   repo_x01/tmp/run-x-a05b/missing_ncloc_recovery_summary.csv
#
# Run all targets:
#   bash proc_sh_x01/run-x-a05b-recover-missing-ncloc.sh
#
# Manifest-only dry run:
#   DRY_RUN=1 bash proc_sh_x01/run-x-a05b-recover-missing-ncloc.sh
#
# One-target smoke test:
#   LIMIT=1 bash proc_sh_x01/run-x-a05b-recover-missing-ncloc.sh
#
# Resume:
#   Re-run the same command. Previously successful snapshot rows are skipped.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   LIMIT=0
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   KEEP_WORKTREES=0
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=0
#   SERVER_TIMEOUT_SECONDS=300
#   COMPUTE_TIMEOUT_SECONDS=900
#   POLL_INTERVAL_SECONDS=5
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

# Load the same project-level SonarQube environment used by the reference
# runner. Values already exported by the caller remain valid; .env may
# override them to match the project configuration.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

RUN_PREFIX="run-x-a05b"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-recover-missing-ncloc-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/recover_missing_ncloc.py}"

POOLED_PANEL_FILE="${POOLED_PANEL_FILE:-repo_x01/run-x-a05/velocity_did_panel_python_pooled.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
WORKTREE_ROOT="${WORKTREE_ROOT:-${TMP_OUTPUT_DIR}/worktrees}"
SCANNER_LOG_DIR="${SCANNER_LOG_DIR:-${MAIN_OUTPUT_DIR}/scanner_logs}"

SNAPSHOT_MANIFEST_OUTPUT="${SNAPSHOT_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_ncloc_snapshot_manifest.csv}"
SNAPSHOT_RESULTS_OUTPUT="${SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_ncloc_snapshot_results.csv}"
REPO_MONTH_PATCH_OUTPUT="${REPO_MONTH_PATCH_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_ncloc_repo_month_patch.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_ncloc_unresolved.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/missing_ncloc_recovery_summary.csv}"

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
SONAR_SCANNER_BIN="${SONAR_PATH:-${SONAR_SCANNER_PATH:-sonar-scanner}}"
PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-a05b_ncloc_}"
SERVER_TIMEOUT_SECONDS="${SERVER_TIMEOUT_SECONDS:-300}"
COMPUTE_TIMEOUT_SECONDS="${COMPUTE_TIMEOUT_SECONDS:-900}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"
LIMIT="${LIMIT:-0}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
KEEP_WORKTREES="${KEEP_WORKTREES:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for numeric_value in \
  "${SERVER_TIMEOUT_SECONDS}" \
  "${COMPUTE_TIMEOUT_SECONDS}" \
  "${POLL_INTERVAL_SECONDS}" \
  "${LIMIT}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: timeout and LIMIT values must be non-negative integers." >&2
    exit 1
  fi
done

for boolean_name in ANALYSIS_AGAIN KEEP_WORKTREES DRY_RUN FAIL_ON_UNRESOLVED; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for required_file in "${PY_SCRIPT}" "${POOLED_PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p \
  "${LOG_DIR}" \
  "${MAIN_OUTPUT_DIR}" \
  "${TMP_OUTPUT_DIR}" \
  "${WORKTREE_ROOT}" \
  "${SCANNER_LOG_DIR}"

{
  echo "============================================================"
  echo "${RUN_LABEL}: recover missing Model A NCLOC"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Pooled panel input:          ${POOLED_PANEL_FILE}"
  echo "Snapshot manifest:           ${SNAPSHOT_MANIFEST_OUTPUT}"
  echo "Snapshot results:            ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Repo-month patch:            ${REPO_MONTH_PATCH_OUTPUT}"
  echo "Unresolved output:           ${UNRESOLVED_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Worktree root:               ${WORKTREE_ROOT}"
  echo "Scanner log directory:       ${SCANNER_LOG_DIR}"
  echo "SonarQube host:              ${SONAR_HOST}"
  echo "SonarScanner:                ${SONAR_SCANNER_BIN}"
  echo "Project key prefix:          ${PROJECT_KEY_PREFIX}"
  echo "Limit:                       ${LIMIT}"
  echo "Repository filter:           ${REPO_NAME:-<all>}"
  echo "Analysis again:              ${ANALYSIS_AGAIN}"
  echo "Keep worktrees:              ${KEEP_WORKTREES}"
  echo "Dry run:                     ${DRY_RUN}"
  echo "Fail on unresolved:          ${FAIL_ON_UNRESOLVED}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --pooled-panel-file "${POOLED_PANEL_FILE}"
  --snapshot-manifest-output "${SNAPSHOT_MANIFEST_OUTPUT}"
  --snapshot-results-output "${SNAPSHOT_RESULTS_OUTPUT}"
  --repo-month-patch-output "${REPO_MONTH_PATCH_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --worktree-root "${WORKTREE_ROOT}"
  --scanner-log-dir "${SCANNER_LOG_DIR}"
  --sonar-host "${SONAR_HOST}"
  --sonar-scanner "${SONAR_SCANNER_BIN}"
  --project-key-prefix "${PROJECT_KEY_PREFIX}"
  --server-timeout-seconds "${SERVER_TIMEOUT_SECONDS}"
  --compute-timeout-seconds "${COMPUTE_TIMEOUT_SECONDS}"
  --poll-interval-seconds "${POLL_INTERVAL_SECONDS}"
  --limit "${LIMIT}"
  --log-level "${LOG_LEVEL}"
)

if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  COMMAND+=(--analysis-again)
fi
if [[ "${KEEP_WORKTREES}" == "1" ]]; then
  COMMAND+=(--keep-worktrees)
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi

{
  echo
  echo "** Step 1: Recover missing whole-repository NCLOC"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${SNAPSHOT_MANIFEST_OUTPUT}" \
  "${SNAPSHOT_RESULTS_OUTPUT}" \
  "${REPO_MONTH_PATCH_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SNAPSHOT_MANIFEST_OUTPUT}" \
    "${SNAPSHOT_RESULTS_OUTPUT}" \
    "${REPO_MONTH_PATCH_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Snapshot results:            ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Repo-month patch:            ${REPO_MONTH_PATCH_OUTPUT}"
  echo "Unresolved output:           ${UNRESOLVED_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   review recovery, then merge in run-x-a05-v3"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
