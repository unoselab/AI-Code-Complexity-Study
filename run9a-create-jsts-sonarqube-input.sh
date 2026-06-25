#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run9a: Create JS/TS SonarQube scan inputs from final panel
# ============================================================
# This script creates treatment/control SonarQube input files from
# the main window-completed matched DiD panel.
#
# The Python script:
#   1. extracts treatment/control repo lists and analysis months,
#   2. finds the latest commit at or before each month-end,
#   3. writes SonarQube-ready repo-month input files.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run9a_create_jsts_sonarqube_input_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_sonarqube_input.py}"
HISTORY_SCRIPT="${HISTORY_SCRIPT:-proc_scripts/create_tmp_repo_timeseries_history.py}"

PANEL_FILE="${PANEL_FILE:-tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv}"

SONAR_ROOT="${SONAR_ROOT:-tmp_jsts_test/data/jsts_sonarqube_main}"

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../ai_code_complexity_study_jsts_repo_dataset}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../ai_code_complexity_study_jsts_control_repo_dataset}"

TREATMENT_TS_FILE="${TREATMENT_TS_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_TS_FILE="${CONTROL_TS_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"

MONTHS_FILE="${MONTHS_FILE:-${SONAR_ROOT}/months.txt}"
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${SONAR_ROOT}/treatment_repos.txt}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${SONAR_ROOT}/control_repos.txt}"
SUMMARY_FILE="${SUMMARY_FILE:-${SONAR_ROOT}/sonarqube_input_summary.csv}"

MAX_TREATMENT_REPOS="${MAX_TREATMENT_REPOS:-0}"
MAX_CONTROL_REPOS="${MAX_CONTROL_REPOS:-0}"
ALLOW_MISSING_LATEST_COMMIT="${ALLOW_MISSING_LATEST_COMMIT:-false}"

mkdir -p "${LOG_DIR}" "${SONAR_ROOT}" "$(dirname "${TREATMENT_TS_FILE}")" "$(dirname "${CONTROL_TS_FILE}")"

{
  echo "============================================================"
  echo "run9a: create JS/TS SonarQube scan inputs"
  echo "Timestamp:                    ${RUN_TS}"
  echo "Python script:                ${PY_SCRIPT}"
  echo "History script:               ${HISTORY_SCRIPT}"
  echo "Panel file:                   ${PANEL_FILE}"
  echo "Sonar root:                   ${SONAR_ROOT}"
  echo "Treatment clone root:         ${TREATMENT_CLONE_ROOT}"
  echo "Control clone root:           ${CONTROL_CLONE_ROOT}"
  echo "Treatment output:             ${TREATMENT_TS_FILE}"
  echo "Control output:               ${CONTROL_TS_FILE}"
  echo "Months file:                  ${MONTHS_FILE}"
  echo "Treatment repos file:         ${TREATMENT_REPOS_FILE}"
  echo "Control repos file:           ${CONTROL_REPOS_FILE}"
  echo "Summary file:                 ${SUMMARY_FILE}"
  echo "Max treatment repos:          ${MAX_TREATMENT_REPOS}"
  echo "Max control repos:            ${MAX_CONTROL_REPOS}"
  echo "Allow missing latest_commit:  ${ALLOW_MISSING_LATEST_COMMIT}"
  echo "Log file:                     ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${HISTORY_SCRIPT}" ]]; then
    echo "ERROR: history script not found: ${HISTORY_SCRIPT}"
    exit 1
  fi

  CMD=(
    python "${PY_SCRIPT}"
    --panel-file "${PANEL_FILE}"
    --sonar-root "${SONAR_ROOT}"
    --treatment-clone-root "${TREATMENT_CLONE_ROOT}"
    --control-clone-root "${CONTROL_CLONE_ROOT}"
    --history-script "${HISTORY_SCRIPT}"
    --treatment-output "${TREATMENT_TS_FILE}"
    --control-output "${CONTROL_TS_FILE}"
    --months-file "${MONTHS_FILE}"
    --treatment-repos-file "${TREATMENT_REPOS_FILE}"
    --control-repos-file "${CONTROL_REPOS_FILE}"
    --summary-file "${SUMMARY_FILE}"
    --max-treatment-repos "${MAX_TREATMENT_REPOS}"
    --max-control-repos "${MAX_CONTROL_REPOS}"
  )

  if [[ "${ALLOW_MISSING_LATEST_COMMIT}" == "true" ]]; then
    CMD+=(--allow-missing-latest-commit)
  fi

  echo "** Running SonarQube input preparation"
  echo "------------------------------------------------------------"
  echo "${CMD[*]}"
  echo

  "${CMD[@]}"

  echo
  echo "============================================================"
  echo "run9a completed successfully."
  echo "Treatment input: ${TREATMENT_TS_FILE}"
  echo "Control input:   ${CONTROL_TS_FILE}"
  echo "Summary file:    ${SUMMARY_FILE}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
