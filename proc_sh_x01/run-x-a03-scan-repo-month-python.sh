#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a03 v2: Resolve and scan historical repo-month commits for Python files
# ============================================================
#
# Purpose:
#   Resolve each in-scope treatment and matched-control repository-month to an
#   effective historical commit. Months with an empty latest_commit carry forward
#   the most recent observed commit from the same repository. The scan uses
#   `git ls-tree` and therefore does not checkout or modify cloned repositories.
#
# Scope inputs:
#   - run-x-a01 pair output defines the 115 treatment repositories and their
#     expected matched controls.
#   - run-x-a02 skip output excludes local treatment clones that are outside the
#     original matching.csv treatment scope.
#
# Primary Python eligibility:
#   A repository-month is Python-eligible when its effective historical Git tree
#   contains at least one tracked path ending in `.py`. Unresolved snapshots keep
#   eligibility and file counts blank rather than incorrectly encoding zero.
#
# Secondary Python source count:
#   Common dependency, cache, virtual-environment, build, and generated-code
#   directories are excluded only from a secondary source-oriented count. They
#   do not change the primary broad eligibility result.
#
# Required inputs:
#   repo_x01/run-x-a01/clonedrepo_matching_pairs.csv
#   repo_x01/run-x-a02/repo_skip_extra_repos.csv
#   data_baseline_backup/ts_repos_monthly.csv
#   data_baseline_backup/ts_repos_control_monthly.csv
#   data_baseline_backup/panel_event_monthly.csv
#   ../treatment-repos/
#   ../control-repos/
#
# Main outputs:
#   repo_x01/run-x-a03/repo_month_python_eligibility.csv
#   repo_x01/run-x-a03/panel_event_monthly_python_eligibility.csv
#   repo_x01/run-x-a03/repo_month_python_anomalies.csv
#
# QC output:
#   repo_x01/tmp/run-x-a03/repo_month_python_summary.csv
#
# Run:
#   bash proc_sh_x01/run-x-a03-scan-repo-month-python.sh
#
# Strict run that fails when any repository-month cannot be inspected:
#   FAIL_ON_SCAN_ERROR=1 bash proc_sh_x01/run-x-a03-scan-repo-month-python.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   WORKERS=8
#   GIT_TIMEOUT_SECONDS=120
#   SAMPLE_PATH_LIMIT=5
#   EXCLUDED_DIR_NAMES='.venv,venv,env,site-packages,...'
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a03"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-scan-repo-month-python-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/repo_month_python_eligibility.py}"

MATCHING_PAIRS_FILE="${MATCHING_PAIRS_FILE:-repo_x01/run-x-a01/clonedrepo_matching_pairs.csv}"
SKIP_REPOS_FILE="${SKIP_REPOS_FILE:-repo_x01/run-x-a02/repo_skip_extra_repos.csv}"
TREATMENT_MONTHLY_FILE="${TREATMENT_MONTHLY_FILE:-data_baseline_backup/ts_repos_monthly.csv}"
CONTROL_MONTHLY_FILE="${CONTROL_MONTHLY_FILE:-data_baseline_backup/ts_repos_control_monthly.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

ELIGIBILITY_OUTPUT="${ELIGIBILITY_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_month_python_eligibility.csv}"
PANEL_OUTPUT="${PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/panel_event_monthly_python_eligibility.csv}"
ANOMALY_OUTPUT="${ANOMALY_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_month_python_anomalies.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/repo_month_python_summary.csv}"

WORKERS="${WORKERS:-8}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-120}"
SAMPLE_PATH_LIMIT="${SAMPLE_PATH_LIMIT:-5}"
EXCLUDED_DIR_NAMES="${EXCLUDED_DIR_NAMES:-.eggs,.nox,.tox,.venv,__pycache__,build,dist,env,generated,node_modules,site-packages,third-party,third_party,vendor,venv}"
FAIL_ON_SCAN_ERROR="${FAIL_ON_SCAN_ERROR:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

case "${FAIL_ON_SCAN_ERROR}" in
  0|1)
    ;;
  *)
    echo "ERROR: FAIL_ON_SCAN_ERROR must be 0 or 1. Got: ${FAIL_ON_SCAN_ERROR}" >&2
    exit 1
    ;;
esac

for integer_value in "${WORKERS}" "${GIT_TIMEOUT_SECONDS}"; do
  if ! [[ "${integer_value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: WORKERS and GIT_TIMEOUT_SECONDS must be positive integers." >&2
    exit 1
  fi
done

if ! [[ "${SAMPLE_PATH_LIMIT}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: SAMPLE_PATH_LIMIT must be a non-negative integer." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${MATCHING_PAIRS_FILE}" \
  "${SKIP_REPOS_FILE}" \
  "${TREATMENT_MONTHLY_FILE}" \
  "${CONTROL_MONTHLY_FILE}" \
  "${PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for required_dir in "${TREATMENT_CLONE_DIR}" "${CONTROL_CLONE_DIR}"; do
  if [[ ! -d "${required_dir}" ]]; then
    echo "ERROR: required directory not found: ${required_dir}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_LABEL}: resolve and scan historical repo-month commits for Python files"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Matching pairs:              ${MATCHING_PAIRS_FILE}"
  echo "Skip repositories:           ${SKIP_REPOS_FILE}"
  echo "Treatment monthly input:     ${TREATMENT_MONTHLY_FILE}"
  echo "Control monthly input:       ${CONTROL_MONTHLY_FILE}"
  echo "Panel input:                 ${PANEL_FILE}"
  echo "Treatment clone directory:   ${TREATMENT_CLONE_DIR}"
  echo "Control clone directory:     ${CONTROL_CLONE_DIR}"
  echo "Eligibility output:          ${ELIGIBILITY_OUTPUT}"
  echo "Enriched panel output:       ${PANEL_OUTPUT}"
  echo "Anomaly output:              ${ANOMALY_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Workers:                     ${WORKERS}"
  echo "Git timeout:                 ${GIT_TIMEOUT_SECONDS} seconds"
  echo "Sample path limit:           ${SAMPLE_PATH_LIMIT}"
  echo "Fail on scan error:          ${FAIL_ON_SCAN_ERROR}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --matching-pairs-file "${MATCHING_PAIRS_FILE}"
  --skip-repos-file "${SKIP_REPOS_FILE}"
  --treatment-monthly-file "${TREATMENT_MONTHLY_FILE}"
  --control-monthly-file "${CONTROL_MONTHLY_FILE}"
  --panel-file "${PANEL_FILE}"
  --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
  --control-clone-dir "${CONTROL_CLONE_DIR}"
  --eligibility-output "${ELIGIBILITY_OUTPUT}"
  --panel-output "${PANEL_OUTPUT}"
  --anomaly-output "${ANOMALY_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --workers "${WORKERS}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --sample-path-limit "${SAMPLE_PATH_LIMIT}"
  --excluded-dir-names "${EXCLUDED_DIR_NAMES}"
  --log-level "${LOG_LEVEL}"
)

if [[ "${FAIL_ON_SCAN_ERROR}" == "1" ]]; then
  COMMAND+=(--fail-on-scan-error)
fi

{
  echo
  echo "** Step 1: Resolve and scan in-scope historical repository-month commits"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${ELIGIBILITY_OUTPUT}" \
  "${PANEL_OUTPUT}" \
  "${ANOMALY_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

for nonempty_output in "${ELIGIBILITY_OUTPUT}" "${PANEL_OUTPUT}" "${SUMMARY_OUTPUT}"; do
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
  wc -l "${ELIGIBILITY_OUTPUT}" "${PANEL_OUTPUT}" "${ANOMALY_OUTPUT}" "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Eligibility output:          ${ELIGIBILITY_OUTPUT}"
  echo "Enriched panel output:       ${PANEL_OUTPUT}"
  echo "Anomaly output:              ${ANOMALY_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   review unresolved snapshots before matched-control coverage"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
