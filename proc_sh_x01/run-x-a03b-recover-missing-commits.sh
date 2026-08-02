#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a03b: Recover historical commits missing from local clones
# ============================================================
#
# Purpose:
#   Read run-x-a03-v2 rows marked commit_not_found, audit the affected local
#   repositories and origin remotes, and attempt to recover the referenced Git
#   objects without checking out branches or changing working-tree files.
#
# Recovery order:
#   1. Check whether each missing SHA is already available.
#   2. Unshallow the clone when needed.
#   3. Fetch all configured remotes and tags without pruning existing refs.
#   4. Fetch all origin branch and tag refs explicitly.
#   5. Attempt a direct fetch of each still-missing SHA.
#   6. Optionally fetch GitHub pull-request head refs.
#
# Safety:
#   - No checkout, reset, clean, prune, gc, or ref deletion is performed.
#   - DRY_RUN=1 performs the audit and writes outputs but runs no fetch command.
#   - Pull-request refs are disabled by default because large repositories may
#     expose many such refs.
#
# Required input:
#   repo_x01/run-x-a03/repo_month_python_eligibility.csv
#
# Main outputs:
#   repo_x01/run-x-a03b/missing_commit_recovery_status.csv
#   repo_x01/run-x-a03b/repository_recovery_audit.csv
#   repo_x01/run-x-a03b/unresolved_repo_months.csv
#
# QC output:
#   repo_x01/tmp/run-x-a03b/missing_commit_recovery_summary.csv
#
# Preview only:
#   DRY_RUN=1 bash proc_sh_x01/run-x-a03b-recover-missing-commits.sh
#
# Actual recovery:
#   DRY_RUN=0 bash proc_sh_x01/run-x-a03b-recover-missing-commits.sh
#
# Optional pull-request ref recovery:
#   DRY_RUN=0 FETCH_PR_REFS=1 \
#     bash proc_sh_x01/run-x-a03b-recover-missing-commits.sh
#
# Strict run that returns exit code 2 when any commit remains unresolved:
#   DRY_RUN=0 FAIL_ON_UNRESOLVED=1 \
#     bash proc_sh_x01/run-x-a03b-recover-missing-commits.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a03b"
IMPLEMENTATION_VERSION="v1"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-recover-missing-commits-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/recover_missing_commits.py}"

ELIGIBILITY_FILE="${ELIGIBILITY_FILE:-repo_x01/run-x-a03/repo_month_python_eligibility.csv}"
OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

RECOVERY_STATUS_OUTPUT="${RECOVERY_STATUS_OUTPUT:-${MAIN_OUTPUT_DIR}/missing_commit_recovery_status.csv}"
REPOSITORY_OUTPUT="${REPOSITORY_OUTPUT:-${MAIN_OUTPUT_DIR}/repository_recovery_audit.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/unresolved_repo_months.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/missing_commit_recovery_summary.csv}"

DRY_RUN="${DRY_RUN:-1}"
FETCH_PR_REFS="${FETCH_PR_REFS:-0}"
SKIP_DIRECT_SHA_FETCH="${SKIP_DIRECT_SHA_FETCH:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-600}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for boolean_value in \
  "${DRY_RUN}" \
  "${FETCH_PR_REFS}" \
  "${SKIP_DIRECT_SHA_FETCH}" \
  "${FAIL_ON_UNRESOLVED}"; do
  case "${boolean_value}" in
    0|1)
      ;;
    *)
      echo "ERROR: boolean options must be 0 or 1. Got: ${boolean_value}" >&2
      exit 1
      ;;
  esac
done

if ! [[ "${GIT_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: GIT_TIMEOUT_SECONDS must be a positive integer." >&2
  exit 1
fi

for required_file in "${PY_SCRIPT}" "${ELIGIBILITY_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: recover historical commits missing from local clones"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Eligibility input:           ${ELIGIBILITY_FILE}"
  echo "Recovery status output:      ${RECOVERY_STATUS_OUTPUT}"
  echo "Repository audit output:     ${REPOSITORY_OUTPUT}"
  echo "Unresolved rows output:      ${UNRESOLVED_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Dry run:                     ${DRY_RUN}"
  echo "Fetch PR refs:                ${FETCH_PR_REFS}"
  echo "Skip direct SHA fetch:       ${SKIP_DIRECT_SHA_FETCH}"
  echo "Fail on unresolved:          ${FAIL_ON_UNRESOLVED}"
  echo "Git timeout:                 ${GIT_TIMEOUT_SECONDS} seconds"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --eligibility-file "${ELIGIBILITY_FILE}"
  --recovery-status-output "${RECOVERY_STATUS_OUTPUT}"
  --repository-output "${REPOSITORY_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --log-level "${LOG_LEVEL}"
)

if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FETCH_PR_REFS}" == "1" ]]; then
  COMMAND+=(--fetch-pr-refs)
fi
if [[ "${SKIP_DIRECT_SHA_FETCH}" == "1" ]]; then
  COMMAND+=(--skip-direct-sha-fetch)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi

{
  echo
  echo "** Step 1: Audit and recover missing historical commits"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

set +e
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"
PIPE_STATUS=("${PIPESTATUS[@]}")
set -e
PYTHON_STATUS="${PIPE_STATUS[0]}"

if [[ "${PYTHON_STATUS}" -ne 0 && "${PYTHON_STATUS}" -ne 2 ]]; then
  echo "ERROR: recovery program failed with exit code ${PYTHON_STATUS}." \
    | tee -a "${LOG_FILE}" >&2
  exit "${PYTHON_STATUS}"
fi

for output_file in \
  "${RECOVERY_STATUS_OUTPUT}" \
  "${REPOSITORY_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

for nonempty_output in \
  "${RECOVERY_STATUS_OUTPUT}" \
  "${REPOSITORY_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -s "${nonempty_output}" ]]; then
    echo "ERROR: expected non-empty output was not created: ${nonempty_output}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${RECOVERY_STATUS_OUTPUT}" \
    "${REPOSITORY_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Recovery status output:      ${RECOVERY_STATUS_OUTPUT}"
  echo "Repository audit output:     ${REPOSITORY_OUTPUT}"
  echo "Unresolved rows output:      ${UNRESOLVED_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   rerun run-x-a03-v2 after recovered commits are available"
  echo "============================================================"
} | tee -a "${LOG_FILE}"

if [[ "${PYTHON_STATUS}" -eq 2 ]]; then
  exit 2
fi
