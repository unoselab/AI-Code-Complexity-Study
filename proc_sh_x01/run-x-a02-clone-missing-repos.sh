#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a02: Clone missing matched controls and create skip list
# ============================================================
#
# Purpose:
#   Use the repository-level alignment output from run-x-a01 to:
#   1. Check GitHub availability and attempt a full clone for each matched
#      control repository that is missing from ../control-repos.
#   2. Create CSV and text lists of locally cloned repositories that are
#      outside the matching.csv scope and must be skipped in the next step.
#
# Design:
#   - This wrapper is based on the logging, parameter, and output-check pattern
#     of run-x-a01, but it is independent and does not call another shell script.
#   - All remote checking, cloning, Git verification, and skip-list logic is in
#     proc_script_x01/clonedrepo_clone_missing.py.
#   - A full clone is used because downstream repo-month analysis may require
#     historical commits.
#   - Each repository is cloned into a temporary sibling directory first. The
#     temporary directory is renamed to the final target only after Git
#     verification, preventing failed clones from leaving invalid targets.
#
# Required inputs:
#   repo_x01/run-x-a01/clonedrepo_matching_alignment.csv
#   ../control-repos/
#
# Main outputs:
#   repo_x01/run-x-a02/missing_control_clone_status.csv
#   repo_x01/run-x-a02/repo_skip_extra_repos.csv
#   repo_x01/run-x-a02/repo_skip_extra_repos.txt
#
# QC output:
#   repo_x01/tmp/run-x-a02/clone_missing_repos_summary.csv
#
# Actual clone attempt (default):
#   bash proc_sh_x01/run-x-a02-clone-missing-repos.sh
#
# Preview without creating clone directories:
#   DRY_RUN=1 bash proc_sh_x01/run-x-a02-clone-missing-repos.sh
#
# Strict mode after actual clone attempts:
#   FAIL_ON_CLONE_ERROR=1 bash proc_sh_x01/run-x-a02-clone-missing-repos.sh
#
# Optional overrides:
#   ALIGNMENT_FILE=/path/to/clonedrepo_matching_alignment.csv
#   CONTROL_CLONE_DIR=/path/to/control-repos
#   OUTPUT_BASE_DIR=/path/to/output-root
#   PYTHON_BIN=/path/to/python
#   REMOTE_CHECK_TIMEOUT_SECONDS=120
#   CLONE_TIMEOUT_SECONDS=3600
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a02"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-clone-missing-repos-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/clonedrepo_clone_missing.py}"

ALIGNMENT_FILE="${ALIGNMENT_FILE:-repo_x01/run-x-a01/clonedrepo_matching_alignment.csv}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"
REMOTE_URL_TEMPLATE="${REMOTE_URL_TEMPLATE:-}"
if [[ -z "${REMOTE_URL_TEMPLATE}" ]]; then
  # Do not place a literal `}` inside Bash parameter-expansion defaults.
  # Bash would treat the placeholder's closing brace as the end of `${...}`
  # and corrupt the template into `https://github.com/{repo_name.git}`.
  REMOTE_URL_TEMPLATE='https://github.com/{repo_name}.git'
fi

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CLONE_STATUS_OUTPUT="${CLONE_STATUS_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_control_clone_status.csv}"
SKIP_CSV_OUTPUT="${SKIP_CSV_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_skip_extra_repos.csv}"
SKIP_TXT_OUTPUT="${SKIP_TXT_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_skip_extra_repos.txt}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/clone_missing_repos_summary.csv}"

DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_CLONE_ERROR="${FAIL_ON_CLONE_ERROR:-0}"
REMOTE_CHECK_TIMEOUT_SECONDS="${REMOTE_CHECK_TIMEOUT_SECONDS:-120}"
CLONE_TIMEOUT_SECONDS="${CLONE_TIMEOUT_SECONDS:-3600}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

case "${DRY_RUN}" in
  0|1)
    ;;
  *)
    echo "ERROR: DRY_RUN must be 0 or 1. Got: ${DRY_RUN}" >&2
    exit 1
    ;;
esac

case "${FAIL_ON_CLONE_ERROR}" in
  0|1)
    ;;
  *)
    echo "ERROR: FAIL_ON_CLONE_ERROR must be 0 or 1. Got: ${FAIL_ON_CLONE_ERROR}" >&2
    exit 1
    ;;
esac

for required_file in "${PY_SCRIPT}" "${ALIGNMENT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if [[ ! -d "${CONTROL_CLONE_DIR}" ]]; then
  echo "ERROR: required directory not found: ${CONTROL_CLONE_DIR}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: clone missing controls and create skip list"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Alignment input:             ${ALIGNMENT_FILE}"
  echo "Control clone directory:     ${CONTROL_CLONE_DIR}"
  echo "Remote URL template:         ${REMOTE_URL_TEMPLATE}"
  echo "Clone status output:         ${CLONE_STATUS_OUTPUT}"
  echo "Extra-repo skip CSV:         ${SKIP_CSV_OUTPUT}"
  echo "Extra-repo skip text:        ${SKIP_TXT_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Dry run:                     ${DRY_RUN}"
  echo "Fail on clone error:         ${FAIL_ON_CLONE_ERROR}"
  echo "Remote check timeout:        ${REMOTE_CHECK_TIMEOUT_SECONDS} seconds"
  echo "Clone timeout:               ${CLONE_TIMEOUT_SECONDS} seconds"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --alignment-file "${ALIGNMENT_FILE}"
  --control-clone-dir "${CONTROL_CLONE_DIR}"
  --clone-status-output "${CLONE_STATUS_OUTPUT}"
  --skip-csv-output "${SKIP_CSV_OUTPUT}"
  --skip-txt-output "${SKIP_TXT_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --remote-url-template "${REMOTE_URL_TEMPLATE}"
  --remote-check-timeout-seconds "${REMOTE_CHECK_TIMEOUT_SECONDS}"
  --clone-timeout-seconds "${CLONE_TIMEOUT_SECONDS}"
  --log-level "${LOG_LEVEL}"
)

if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi

if [[ "${FAIL_ON_CLONE_ERROR}" == "1" ]]; then
  COMMAND+=(--fail-on-clone-error)
fi

{
  echo
  echo "** Step 1: Check and clone missing matched controls"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in "${CLONE_STATUS_OUTPUT}" "${SKIP_CSV_OUTPUT}" "${SUMMARY_OUTPUT}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

if [[ ! -f "${SKIP_TXT_OUTPUT}" ]]; then
  echo "ERROR: expected skip text output was not created: ${SKIP_TXT_OUTPUT}" \
    | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l "${CLONE_STATUS_OUTPUT}" "${SKIP_CSV_OUTPUT}" "${SKIP_TXT_OUTPUT}" "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Extra repositories to skip in the next step:"
  cat "${SKIP_TXT_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Clone status output:         ${CLONE_STATUS_OUTPUT}"
  echo "Extra-repo skip CSV:         ${SKIP_CSV_OUTPUT}"
  echo "Extra-repo skip text:        ${SKIP_TXT_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next validation:             bash proc_sh_x01/run-x-a01-repo-matching.sh"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
