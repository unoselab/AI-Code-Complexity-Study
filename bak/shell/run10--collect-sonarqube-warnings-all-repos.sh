#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs data

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run10b_collect_sonarqube_warnings_all_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/collect_sonarqube_warnings_all_repos.py}"

TREATMENT_SCANNED="${TREATMENT_SCANNED:-tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/ts_repos_monthly_scanned.csv}"
CONTROL_SCANNED="${CONTROL_SCANNED:-tmp_jsts_test/data/jsts_sonarqube_main/control/data/ts_repos_monthly_scanned.csv}"

PANEL_FILE="${PANEL_FILE:-tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input.csv}"

WARNING_DEFINITIONS="${WARNING_DEFINITIONS:-data/sonarqube_warning_definitions.csv}"

ISSUES_OUTPUT="${ISSUES_OUTPUT:-data/sonarqube_warnings_all_repos.csv}"
COUNTS_OUTPUT="${COUNTS_OUTPUT:-data/sonarqube_warning_category_counts_all_repos.csv}"
QC_OUTPUT="${QC_OUTPUT:-data/sonarqube_warnings_all_repos_collection_qc.csv}"

MAX_REPOS_PER_SOURCE="${MAX_REPOS_PER_SOURCE:-0}"
MAX_MONTHS_PER_REPO="${MAX_MONTHS_PER_REPO:-0}"
MAX_ISSUES_PER_REPO_MONTH="${MAX_ISSUES_PER_REPO_MONTH:-0}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"

RESUME="${RESUME:-1}"
OVERWRITE="${OVERWRITE:-0}"
DRY_RUN="${DRY_RUN:-0}"

{
  echo "============================================================"
  echo "run10b: collect SonarQube warnings for all JS/TS repos"
  echo "Started:                    $(date)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Treatment scanned:          ${TREATMENT_SCANNED}"
  echo "Control scanned:            ${CONTROL_SCANNED}"
  echo "Panel file:                 ${PANEL_FILE}"
  echo "Warning definitions:        ${WARNING_DEFINITIONS}"
  echo "Issues output:              ${ISSUES_OUTPUT}"
  echo "Counts output:              ${COUNTS_OUTPUT}"
  echo "QC output:                  ${QC_OUTPUT}"
  echo "MAX_REPOS_PER_SOURCE:       ${MAX_REPOS_PER_SOURCE}"
  echo "MAX_MONTHS_PER_REPO:        ${MAX_MONTHS_PER_REPO}"
  echo "MAX_ISSUES_PER_REPO_MONTH:  ${MAX_ISSUES_PER_REPO_MONTH}"
  echo "SLEEP_SECONDS:              ${SLEEP_SECONDS}"
  echo "RESUME:                     ${RESUME}"
  echo "OVERWRITE:                  ${OVERWRITE}"
  echo "DRY_RUN:                    ${DRY_RUN}"
  echo "Log file:                   ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${TREATMENT_SCANNED}" ]]; then
    echo "ERROR: treatment scanned file not found: ${TREATMENT_SCANNED}"
    exit 1
  fi

  if [[ ! -f "${CONTROL_SCANNED}" ]]; then
    echo "ERROR: control scanned file not found: ${CONTROL_SCANNED}"
    exit 1
  fi

  if [[ ! -f "${WARNING_DEFINITIONS}" ]]; then
    echo "ERROR: warning definitions file not found: ${WARNING_DEFINITIONS}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  CMD=(
    python "${PY_SCRIPT}"
    --treatment-scanned "${TREATMENT_SCANNED}"
    --control-scanned "${CONTROL_SCANNED}"
    --panel "${PANEL_FILE}"
    --warning-definitions "${WARNING_DEFINITIONS}"
    --issues-output "${ISSUES_OUTPUT}"
    --counts-output "${COUNTS_OUTPUT}"
    --qc-output "${QC_OUTPUT}"
    --max-repos-per-source "${MAX_REPOS_PER_SOURCE}"
    --max-months-per-repo "${MAX_MONTHS_PER_REPO}"
    --max-issues-per-repo-month "${MAX_ISSUES_PER_REPO_MONTH}"
    --sleep-seconds "${SLEEP_SECONDS}"
  )

  if [[ "${RESUME}" == "1" ]]; then
    CMD+=(--resume)
  fi

  if [[ "${OVERWRITE}" == "1" ]]; then
    CMD+=(--overwrite)
  fi

  if [[ "${DRY_RUN}" == "1" ]]; then
    CMD+=(--dry-run)
  fi

  echo "Command:"
  printf ' %q' "${CMD[@]}"
  echo
  echo

  "${CMD[@]}"

  echo
  echo "============================================================"
  echo "run10b completed."
  echo "Completed:     $(date)"
  echo "Issues output: ${ISSUES_OUTPUT}"
  echo "Counts output: ${COUNTS_OUTPUT}"
  echo "QC output:     ${QC_OUTPUT}"
  echo "Log file:      ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
