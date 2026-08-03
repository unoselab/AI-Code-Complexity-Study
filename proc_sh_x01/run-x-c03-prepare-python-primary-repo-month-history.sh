#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-c03 v3: Prepare Python-primary repository-month history
# ============================================================
#
# Purpose:
#   Combine the paper Appendix Python repository scope from run-x-c01 with
#   clone availability from run-x-c02. For every paper repository-month, join
#   the replication-package latest_commit value and resolve a historical Git
#   commit using read-only Git commands.
#
# Repository scope:
#   - 121 Appendix Python treatment repositories from run-x-c01;
#   - 127 paper-selected control repositories from run-x-c01;
#   - 116 treatment and 126 control repositories successfully cloned by C02;
#   - clone-unavailable repositories remain in the paper audit panel but are
#     excluded from historical snapshot resolution.
#
# Commit-resolution order:
#   1. exact latest_commit from the monthly replication CSV;
#   2. prior observed monthly latest_commit carried forward;
#   3. latest commit reachable from current HEAD before month end;
#   4. unresolved, retained in audit output.
#
# Required inputs:
#   repo_x01/run-x-c01/python_primary_treatment_repos.csv
#   repo_x01/run-x-c01/python_primary_matched_control_repos.csv
#   repo_x01/run-x-c01/python_primary_clone_manifest.csv
#   repo_x01/run-x-c02/python_primary_clone_status.csv
#   data_baseline_backup/panel_event_monthly.csv
#   data_baseline_backup/ts_repos_monthly.csv
#   data_baseline_backup/ts_repos_control_monthly.csv
#
# Main outputs:
#   repo_x01/run-x-c03/python_primary_repo_month_panel.csv
#     All 2,461 paper Appendix repo-month rows with clone and history status.
#   repo_x01/run-x-c03/python_primary_repo_month_history_manifest.csv
#     One history-resolution row for each clone-available repo-month.
#   repo_x01/run-x-c03/python_primary_unique_snapshot_manifest.csv
#     One row per unique resolved repository commit for the later cloc scan.
#   repo_x01/run-x-c03/python_primary_repo_month_commit_resolution_audit.csv
#   repo_x01/run-x-c03/python_primary_repo_month_unresolved.csv
#   repo_x01/run-x-c03/python_primary_clone_unavailable_repo_months.csv
#   repo_x01/run-x-c03/python_primary_repo_month_support.csv
#   repo_x01/run-x-c03/python_primary_c03_qc.csv
#
# Summary output:
#   repo_x01/tmp/run-x-c03/python_primary_repo_month_history_summary.csv
#
# Safety:
#   This stage does not checkout, reset, clean, pull, or fetch repositories.
#   It uses only read-only Git inspection commands.
#
# Run:
#   bash proc_sh_x01/run-x-c03-prepare-python-primary-repo-month-history.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   WORKERS=8
#   GIT_TIMEOUT_SECONDS=120
#   HISTORY_TIMEZONE=America/Chicago
#   ALLOW_CARRY_FORWARD=1
#   ALLOW_GIT_HEAD_FALLBACK=1
#   FAIL_ON_UNRESOLVED=0
#   STRICT_EXPECTED_COUNTS=1
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-c03"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-python-primary-repo-month-history-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_python_primary_repo_month_history.py}"

TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-repo_x01/run-x-c01/python_primary_treatment_repos.csv}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-repo_x01/run-x-c01/python_primary_matched_control_repos.csv}"
CLONE_MANIFEST_FILE="${CLONE_MANIFEST_FILE:-repo_x01/run-x-c01/python_primary_clone_manifest.csv}"
CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-repo_x01/run-x-c02/python_primary_clone_status.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"
TREATMENT_MONTHLY_FILE="${TREATMENT_MONTHLY_FILE:-data_baseline_backup/ts_repos_monthly.csv}"
CONTROL_MONTHLY_FILE="${CONTROL_MONTHLY_FILE:-data_baseline_backup/ts_repos_control_monthly.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

PAPER_PANEL_OUTPUT="${PAPER_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_month_panel.csv}"
HISTORY_OUTPUT="${HISTORY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_month_history_manifest.csv}"
UNIQUE_SNAPSHOT_OUTPUT="${UNIQUE_SNAPSHOT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_unique_snapshot_manifest.csv}"
RESOLUTION_AUDIT_OUTPUT="${RESOLUTION_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_month_commit_resolution_audit.csv}"
TIMEZONE_AUDIT_OUTPUT="${TIMEZONE_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_timezone_alignment_audit.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_month_unresolved.csv}"
CLONE_UNAVAILABLE_OUTPUT="${CLONE_UNAVAILABLE_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_clone_unavailable_repo_months.csv}"
SUPPORT_OUTPUT="${SUPPORT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_month_support.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_c03_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_primary_repo_month_history_summary.csv}"

WORKERS="${WORKERS:-8}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-120}"
HISTORY_TIMEZONE="${HISTORY_TIMEZONE:-America/Chicago}"
ALLOW_CARRY_FORWARD="${ALLOW_CARRY_FORWARD:-1}"
ALLOW_GIT_HEAD_FALLBACK="${ALLOW_GIT_HEAD_FALLBACK:-1}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_PAPER_TREATMENT_REPOS="${EXPECTED_PAPER_TREATMENT_REPOS:-121}"
EXPECTED_PAPER_CONTROL_REPOS="${EXPECTED_PAPER_CONTROL_REPOS:-127}"
EXPECTED_PAPER_TREATMENT_ROWS="${EXPECTED_PAPER_TREATMENT_ROWS:-1223}"
EXPECTED_PAPER_CONTROL_ROWS="${EXPECTED_PAPER_CONTROL_ROWS:-1238}"
EXPECTED_PAPER_PANEL_ROWS="${EXPECTED_PAPER_PANEL_ROWS:-2461}"
EXPECTED_CLONE_AVAILABLE_TREATMENT_REPOS="${EXPECTED_CLONE_AVAILABLE_TREATMENT_REPOS:-116}"
EXPECTED_CLONE_AVAILABLE_CONTROL_REPOS="${EXPECTED_CLONE_AVAILABLE_CONTROL_REPOS:-126}"
EXPECTED_CLONE_AVAILABLE_REPOS="${EXPECTED_CLONE_AVAILABLE_REPOS:-242}"
EXPECTED_CLONE_UNAVAILABLE_REPOS="${EXPECTED_CLONE_UNAVAILABLE_REPOS:-6}"
EXPECTED_CLONE_UNAVAILABLE_ROWS="${EXPECTED_CLONE_UNAVAILABLE_ROWS:-50}"
EXPECTED_HISTORY_CANDIDATE_ROWS="${EXPECTED_HISTORY_CANDIDATE_ROWS:-2411}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import pandas' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide pandas." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c "from zoneinfo import ZoneInfo; ZoneInfo('${HISTORY_TIMEZONE}')" >/dev/null 2>&1; then
  echo "ERROR: invalid HISTORY_TIMEZONE: ${HISTORY_TIMEZONE}" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required for read-only history inspection." >&2
  exit 1
fi

for binary_value in \
  "${ALLOW_CARRY_FORWARD}" \
  "${ALLOW_GIT_HEAD_FALLBACK}" \
  "${FAIL_ON_UNRESOLVED}" \
  "${STRICT_EXPECTED_COUNTS}"; do
  if [[ "${binary_value}" != "0" && "${binary_value}" != "1" ]]; then
    echo "ERROR: Boolean options must be 0 or 1." >&2
    exit 1
  fi
done

for positive_value in "${WORKERS}" "${GIT_TIMEOUT_SECONDS}"; do
  if ! [[ "${positive_value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: WORKERS and GIT_TIMEOUT_SECONDS must be positive integers." >&2
    exit 1
  fi
done

for count_value in \
  "${EXPECTED_PAPER_TREATMENT_REPOS}" \
  "${EXPECTED_PAPER_CONTROL_REPOS}" \
  "${EXPECTED_PAPER_TREATMENT_ROWS}" \
  "${EXPECTED_PAPER_CONTROL_ROWS}" \
  "${EXPECTED_PAPER_PANEL_ROWS}" \
  "${EXPECTED_CLONE_AVAILABLE_TREATMENT_REPOS}" \
  "${EXPECTED_CLONE_AVAILABLE_CONTROL_REPOS}" \
  "${EXPECTED_CLONE_AVAILABLE_REPOS}" \
  "${EXPECTED_CLONE_UNAVAILABLE_REPOS}" \
  "${EXPECTED_CLONE_UNAVAILABLE_ROWS}" \
  "${EXPECTED_HISTORY_CANDIDATE_ROWS}"; do
  if ! [[ "${count_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Expected-count options must be non-negative integers." >&2
    exit 1
  fi
done

for required_file in \
  "${PY_SCRIPT}" \
  "${TREATMENT_REPOS_FILE}" \
  "${CONTROL_REPOS_FILE}" \
  "${CLONE_MANIFEST_FILE}" \
  "${CLONE_STATUS_FILE}" \
  "${PANEL_FILE}" \
  "${TREATMENT_MONTHLY_FILE}" \
  "${CONTROL_MONTHLY_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
TREATMENT_REPOS_SHA256="$(sha256sum "${TREATMENT_REPOS_FILE}" | awk '{print $1}')"
CONTROL_REPOS_SHA256="$(sha256sum "${CONTROL_REPOS_FILE}" | awk '{print $1}')"
CLONE_MANIFEST_SHA256="$(sha256sum "${CLONE_MANIFEST_FILE}" | awk '{print $1}')"
CLONE_STATUS_SHA256="$(sha256sum "${CLONE_STATUS_FILE}" | awk '{print $1}')"
PANEL_SHA256="$(sha256sum "${PANEL_FILE}" | awk '{print $1}')"
TREATMENT_MONTHLY_SHA256="$(sha256sum "${TREATMENT_MONTHLY_FILE}" | awk '{print $1}')"
CONTROL_MONTHLY_SHA256="$(sha256sum "${CONTROL_MONTHLY_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare Python-primary repository-month history"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Treatment scope:                 ${TREATMENT_REPOS_FILE}"
  echo "Treatment scope SHA256:          ${TREATMENT_REPOS_SHA256}"
  echo "Control scope:                   ${CONTROL_REPOS_FILE}"
  echo "Control scope SHA256:            ${CONTROL_REPOS_SHA256}"
  echo "C01 clone manifest:              ${CLONE_MANIFEST_FILE}"
  echo "C01 clone manifest SHA256:       ${CLONE_MANIFEST_SHA256}"
  echo "C02 clone status:                ${CLONE_STATUS_FILE}"
  echo "C02 clone status SHA256:         ${CLONE_STATUS_SHA256}"
  echo "Paper event panel:               ${PANEL_FILE}"
  echo "Paper event panel SHA256:        ${PANEL_SHA256}"
  echo "Treatment monthly input:         ${TREATMENT_MONTHLY_FILE}"
  echo "Treatment monthly SHA256:        ${TREATMENT_MONTHLY_SHA256}"
  echo "Control monthly input:           ${CONTROL_MONTHLY_FILE}"
  echo "Control monthly SHA256:          ${CONTROL_MONTHLY_SHA256}"
  echo "Workers:                         ${WORKERS}"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "History timezone:                ${HISTORY_TIMEZONE}"
  echo "Allow carry-forward:             ${ALLOW_CARRY_FORWARD}"
  echo "Allow Git HEAD fallback:         ${ALLOW_GIT_HEAD_FALLBACK}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Expected paper rows:             ${EXPECTED_PAPER_PANEL_ROWS}"
  echo "Expected clone-available rows:   ${EXPECTED_HISTORY_CANDIDATE_ROWS}"
  echo "Paper panel output:              ${PAPER_PANEL_OUTPUT}"
  echo "History manifest output:         ${HISTORY_OUTPUT}"
  echo "Unique snapshot output:          ${UNIQUE_SNAPSHOT_OUTPUT}"
  echo "Resolution audit output:         ${RESOLUTION_AUDIT_OUTPUT}"
  echo "Timezone audit output:           ${TIMEZONE_AUDIT_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "Clone-unavailable output:        ${CLONE_UNAVAILABLE_OUTPUT}"
  echo "Support output:                  ${SUPPORT_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --treatment-repos-file "${TREATMENT_REPOS_FILE}"
  --control-repos-file "${CONTROL_REPOS_FILE}"
  --clone-manifest-file "${CLONE_MANIFEST_FILE}"
  --clone-status-file "${CLONE_STATUS_FILE}"
  --panel-file "${PANEL_FILE}"
  --treatment-monthly-file "${TREATMENT_MONTHLY_FILE}"
  --control-monthly-file "${CONTROL_MONTHLY_FILE}"
  --paper-panel-output "${PAPER_PANEL_OUTPUT}"
  --history-output "${HISTORY_OUTPUT}"
  --unique-snapshot-output "${UNIQUE_SNAPSHOT_OUTPUT}"
  --resolution-audit-output "${RESOLUTION_AUDIT_OUTPUT}"
  --timezone-audit-output "${TIMEZONE_AUDIT_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --clone-unavailable-output "${CLONE_UNAVAILABLE_OUTPUT}"
  --support-output "${SUPPORT_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --workers "${WORKERS}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --history-timezone "${HISTORY_TIMEZONE}"
  --allow-carry-forward "${ALLOW_CARRY_FORWARD}"
  --allow-git-head-fallback "${ALLOW_GIT_HEAD_FALLBACK}"
  --fail-on-unresolved "${FAIL_ON_UNRESOLVED}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-paper-treatment-repos "${EXPECTED_PAPER_TREATMENT_REPOS}"
  --expected-paper-control-repos "${EXPECTED_PAPER_CONTROL_REPOS}"
  --expected-paper-treatment-rows "${EXPECTED_PAPER_TREATMENT_ROWS}"
  --expected-paper-control-rows "${EXPECTED_PAPER_CONTROL_ROWS}"
  --expected-paper-panel-rows "${EXPECTED_PAPER_PANEL_ROWS}"
  --expected-clone-available-treatment-repos "${EXPECTED_CLONE_AVAILABLE_TREATMENT_REPOS}"
  --expected-clone-available-control-repos "${EXPECTED_CLONE_AVAILABLE_CONTROL_REPOS}"
  --expected-clone-available-repos "${EXPECTED_CLONE_AVAILABLE_REPOS}"
  --expected-clone-unavailable-repos "${EXPECTED_CLONE_UNAVAILABLE_REPOS}"
  --expected-clone-unavailable-rows "${EXPECTED_CLONE_UNAVAILABLE_ROWS}"
  --expected-history-candidate-rows "${EXPECTED_HISTORY_CANDIDATE_ROWS}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 1: Build the paper repo-month panel and resolve historical commits"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

set +e
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"
COMMAND_STATUS=${PIPESTATUS[0]}
set -e

if [[ "${COMMAND_STATUS}" -ne 0 ]]; then
  echo "ERROR: ${RUN_LABEL} failed with status ${COMMAND_STATUS}." | tee -a "${LOG_FILE}" >&2
  exit "${COMMAND_STATUS}"
fi

for output_file in \
  "${PAPER_PANEL_OUTPUT}" \
  "${HISTORY_OUTPUT}" \
  "${UNIQUE_SNAPSHOT_OUTPUT}" \
  "${RESOLUTION_AUDIT_OUTPUT}" \
  "${TIMEZONE_AUDIT_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${CLONE_UNAVAILABLE_OUTPUT}" \
  "${SUPPORT_OUTPUT}" \
  "${QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

for nonempty_output in \
  "${PAPER_PANEL_OUTPUT}" \
  "${HISTORY_OUTPUT}" \
  "${UNIQUE_SNAPSHOT_OUTPUT}" \
  "${RESOLUTION_AUDIT_OUTPUT}" \
  "${TIMEZONE_AUDIT_OUTPUT}" \
  "${CLONE_UNAVAILABLE_OUTPUT}" \
  "${SUPPORT_OUTPUT}" \
  "${QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -s "${nonempty_output}" ]]; then
    echo "ERROR: expected non-empty output was not created: ${nonempty_output}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${PAPER_PANEL_OUTPUT}" \
    "${HISTORY_OUTPUT}" \
    "${UNIQUE_SNAPSHOT_OUTPUT}" \
    "${RESOLUTION_AUDIT_OUTPUT}" \
    "${TIMEZONE_AUDIT_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${CLONE_UNAVAILABLE_OUTPUT}" \
    "${SUPPORT_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "QC:"
  cat "${QC_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Paper panel:                     ${PAPER_PANEL_OUTPUT}"
  echo "History manifest:                ${HISTORY_OUTPUT}"
  echo "Unique snapshot manifest:        ${UNIQUE_SNAPSHOT_OUTPUT}"
  echo "Resolution audit:                ${RESOLUTION_AUDIT_OUTPUT}"
  echo "Timezone audit:                  ${TIMEZONE_AUDIT_OUTPUT}"
  echo "Unresolved rows:                 ${UNRESOLVED_OUTPUT}"
  echo "Clone-unavailable rows:          ${CLONE_UNAVAILABLE_OUTPUT}"
  echo "Support table:                   ${SUPPORT_OUTPUT}"
  echo "QC:                              ${QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       review unresolved rows, then run C04 whole-repository cloc"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
