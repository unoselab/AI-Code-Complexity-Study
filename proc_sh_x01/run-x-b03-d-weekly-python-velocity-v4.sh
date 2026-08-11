#!/usr/bin/env bash
# run-x-b03-d v4: weekly Python velocity with Adjusted and FE-only specifications.
#
# This wrapper preserves the existing weekly-panel preparation logic while
# remaining self-contained: it does not call an older shell wrapper.
#
# Inputs
# ------
# 1. run-x-b02 SonarQube Python velocity panel.
#    - Supplies the fixed 167-repository monthly support.
#    - Supplies the exact monthly covariates used by the monthly run-x-b03
#      adjusted specification: log_age, ncloc, log_contributors, log_stars,
#      and log_issues.
# 2. run-x-b02-v4 commit-level Python added-lines output.
#    - Re-aggregated to Monday-start weeks by the existing Python panel builder.
# 3. run-x-b03-c treatment-history summary.
#    - Supplies the exact first observable Cursor-related commit timestamp.
#
# Outputs
# -------
# - New York and Chicago weekly panels plus timezone/support QC from the
#   existing Python panel builder.
# - Chicago weekly Adjusted and FE-only Borusyak static/dynamic results on one
#   common repository-week support. Rows missing any adjusted monthly covariate
#   are dropped from BOTH specifications rather than imputed.
# - Common-support dropped-row and event-support audit CSVs.
# - A manuscript figure comparing Adjusted and FE-only weekly event effects.
#
# The figure uses Chicago only. The separate New York/Chicago timing robustness
# experiment remains a textual robustness result and is not duplicated in the
# manuscript figure.
# 
# Run:
# bash proc_sh_x01/run-x-b03-d-weekly-python-velocity-v4.sh
# 

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
IMPLEMENTATION_VERSION="v4"

PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_weekly_python_velocity_panel.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_python_added_lines_weekly-v4.R}"
PLOT_SCRIPT="${PLOT_SCRIPT:-proc_script_x01/plot_did_velocity_python_weekly-v4.py}"

MONTHLY_PANEL_FILE="${MONTHLY_PANEL_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
COMMIT_FILE="${COMMIT_FILE:-repo_x01/run-x-b02/python-added-lines/python_added_lines_commit.csv}"
TREATMENT_HISTORY_FILE="${TREATMENT_HISTORY_FILE:-repo_x01/run-x-b03-c/cursor_treatment_history_repo_summary.csv}"

OUTPUT_BASE="${OUTPUT_BASE:-repo_x01/run-x-b03-d-v4}"
PANEL_DIR="${PANEL_DIR:-${OUTPUT_BASE}/panels}"
AUDIT_DIR="${AUDIT_DIR:-${OUTPUT_BASE}/audit}"
DID_DIR="${DID_DIR:-${OUTPUT_BASE}/weekly_did}"
PLOT_DIR="${PLOT_DIR:-${DID_DIR}/plots}"
TMP_DIR="${TMP_DIR:-repo_x01/tmp/run-x-b03-d-v4}"

NEW_YORK_PANEL="${NEW_YORK_PANEL:-${PANEL_DIR}/velocity_did_panel_python_added_lines_weekly_new_york.csv}"
CHICAGO_PANEL="${CHICAGO_PANEL:-${PANEL_DIR}/velocity_did_panel_python_added_lines_weekly_chicago.csv}"
EVENT_TIMEZONE_AUDIT="${EVENT_TIMEZONE_AUDIT:-${AUDIT_DIR}/weekly_treatment_event_timezone_audit.csv}"
INTERNAL_GAP_AUDIT="${INTERNAL_GAP_AUDIT:-${AUDIT_DIR}/weekly_internal_month_gap_audit.csv}"
CALENDAR_OUTCOME_COMPARISON="${CALENDAR_OUTCOME_COMPARISON:-${AUDIT_DIR}/weekly_calendar_outcome_comparison.csv}"
PANEL_QC="${PANEL_QC:-${AUDIT_DIR}/weekly_panel_qc.csv}"
PANEL_SUMMARY="${PANEL_SUMMARY:-${TMP_DIR}/weekly_panel_summary.csv}"

DYNAMIC_CSV="${DYNAMIC_CSV:-${DID_DIR}/velocity_python_added_lines_weekly_v4_dynamic_effects.csv}"
FIGURE_PREFIX="${FIGURE_PREFIX:-${PLOT_DIR}/fig_did_velocity_python_weekly-v4}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_MONTHLY_ROWS="${EXPECTED_MONTHLY_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_WEEKLY_ROWS="${EXPECTED_WEEKLY_ROWS:-8599}"
EXPECTED_COMMON_SUPPORT_ROWS="${EXPECTED_COMMON_SUPPORT_ROWS:-8595}"
EXPECTED_COMMON_SUPPORT_DROPPED_ROWS="${EXPECTED_COMMON_SUPPORT_DROPPED_ROWS:-4}"
EXPECTED_EVENT_ZERO_SUPPORT="${EXPECTED_EVENT_ZERO_SUPPORT:-62}"
EXPECTED_INTERNAL_GAP_MONTHS="${EXPECTED_INTERNAL_GAP_MONTHS:-1}"
EXPECTED_EVENT_WEEK_TIMEZONE_MISMATCHES="${EXPECTED_EVENT_WEEK_TIMEZONE_MISMATCHES:-1}"
EXPECTED_REPOSITORIES_WITHOUT_COMMIT_ROWS="${EXPECTED_REPOSITORIES_WITHOUT_COMMIT_ROWS:-1}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--12}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-12}"
PRETREND_MIN="${PRETREND_MIN:--12}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

mkdir -p logs "${PANEL_DIR}" "${AUDIT_DIR}" "${DID_DIR}" "${PLOT_DIR}" "${TMP_DIR}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run-x-b03-d-v4-weekly-python-velocity-${TIMESTAMP}.log}"

sha256_or_na() {
  if [[ -f "$1" ]]; then
    sha256sum "$1" | awk '{print $1}'
  else
    printf 'NA'
  fi
}

{
  echo "============================================================"
  echo "run-x-b03-d-v4: weekly Python velocity Adjusted + FE-only"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python panel script:              ${PY_SCRIPT}"
  echo "Python panel SHA256:              $(sha256_or_na "${PY_SCRIPT}")"
  echo "R analysis script:                ${R_SCRIPT}"
  echo "R script SHA256:                  $(sha256_or_na "${R_SCRIPT}")"
  echo "Python plot script:               ${PLOT_SCRIPT}"
  echo "Plot script SHA256:               $(sha256_or_na "${PLOT_SCRIPT}")"
  echo "run-x-b02 SonarQube panel:        ${MONTHLY_PANEL_FILE}"
  echo "b02 commit-level outcome file:    ${COMMIT_FILE}"
  echo "b03-c treatment-history summary:  ${TREATMENT_HISTORY_FILE}"
  echo "Primary weekly outcome:           log_lines_added_py_source"
  echo "Figure calendar:                  America/Chicago"
  echo "Weekly adjusted first stage:      ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
  echo "Weekly FE-only first stage:       ~ 1 | repo_id + time_index"
  echo "Covariate source:                 exact columns from run-x-b02 SonarQube panel"
  echo "Covariate month mapping:          week midpoint month, clipped to retained monthly support"
  echo "Common-support policy:            same covariate-complete rows for Adjusted and FE-only"
  echo "Dynamic window:                   ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT} weeks"
  echo "Pretrend window:                  ${PRETREND_MIN}:${PRETREND_MAX} weeks"
  echo "Reference event week:             -1"
  echo "Output base:                      ${OUTPUT_BASE}"
  echo "Log file:                         ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Validate reused weekly Python panel builder"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
  echo
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${PY_SCRIPT}" --self-test --log-level "${LOG_LEVEL}" 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Compile Python programs"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT} ${PLOT_SCRIPT}"
  echo
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}" "${PLOT_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "Self-test-only run completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_file in "${MONTHLY_PANEL_FILE}" "${COMMIT_FILE}" "${TREATMENT_HISTORY_FILE}" "${R_SCRIPT}" "${PLOT_SCRIPT}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}" >&2
    exit 2
  fi
done

PANEL_COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --monthly-panel-file "${MONTHLY_PANEL_FILE}"
  --commit-file "${COMMIT_FILE}"
  --treatment-history-file "${TREATMENT_HISTORY_FILE}"
  --new-york-panel-output "${NEW_YORK_PANEL}"
  --chicago-panel-output "${CHICAGO_PANEL}"
  --event-timezone-audit-output "${EVENT_TIMEZONE_AUDIT}"
  --internal-gap-audit-output "${INTERNAL_GAP_AUDIT}"
  --calendar-outcome-comparison-output "${CALENDAR_OUTCOME_COMPARISON}"
  --qc-output "${PANEL_QC}"
  --summary-output "${PANEL_SUMMARY}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-monthly-rows "${EXPECTED_MONTHLY_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-weekly-rows "${EXPECTED_WEEKLY_ROWS}"
  --expected-internal-gap-months "${EXPECTED_INTERNAL_GAP_MONTHS}"
  --expected-event-week-timezone-mismatches "${EXPECTED_EVENT_WEEK_TIMEZONE_MISMATCHES}"
  --expected-repositories-without-commit-rows "${EXPECTED_REPOSITORIES_WITHOUT_COMMIT_ROWS}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 3: Rebuild weekly panels and timezone audits"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${PANEL_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${PANEL_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

DID_COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --weekly-panel "${CHICAGO_PANEL}"
  --monthly-panel "${MONTHLY_PANEL_FILE}"
  --output-dir "${DID_DIR}"
  --calendar-key chicago
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-weekly-rows "${EXPECTED_WEEKLY_ROWS}"
  --expected-monthly-rows "${EXPECTED_MONTHLY_ROWS}"
  --expected-treatment-repos "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repos "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-common-support-rows "${EXPECTED_COMMON_SUPPORT_ROWS}"
  --expected-dropped-rows "${EXPECTED_COMMON_SUPPORT_DROPPED_ROWS}"
  --expected-event-zero-support "${EXPECTED_EVENT_ZERO_SUPPORT}"
)

{
  echo
  echo "** Step 4: Run Chicago Adjusted + FE-only weekly Borusyak DiD"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${DID_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${DID_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

PLOT_COMMAND=(
  "${PYTHON_BIN}"
  "${PLOT_SCRIPT}"
  "${DYNAMIC_CSV}"
  --output-prefix "${FIGURE_PREFIX}"
)

{
  echo
  echo "** Step 5: Create Adjusted + FE-only weekly manuscript figure"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${PLOT_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${PLOT_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${NEW_YORK_PANEL}"
  "${CHICAGO_PANEL}"
  "${EVENT_TIMEZONE_AUDIT}"
  "${INTERNAL_GAP_AUDIT}"
  "${CALENDAR_OUTCOME_COMPARISON}"
  "${PANEL_QC}"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_static_effects.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_dynamic_effects.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_pretrend_checks.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_pretrend_summary.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_sample_summary.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_diagnostics.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_covariate_mapping_audit.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_common_support_dropped_rows.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_event_support.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_cross_spec_support_check.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_v4_qc.csv"
  "${FIGURE_PREFIX}.pdf"
  "${FIGURE_PREFIX}.png"
)

{
  echo
  echo "** Step 6: Output checks"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 3
  fi
done

{
  echo "Weekly panel QC:"
  cat "${PANEL_QC}"
  echo
  echo "Weekly v4 DiD QC:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_v4_qc.csv"
  echo
  echo "Weekly v4 sample summary:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_v4_sample_summary.csv"
  echo
  echo "Weekly v4 covariate mapping audit:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_v4_covariate_mapping_audit.csv"
  echo
  echo "Weekly v4 common-support dropped rows:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_v4_common_support_dropped_rows.csv"
  echo
  echo "Weekly v4 event support:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_v4_event_support.csv"
  echo
  echo "============================================================"
  echo "run-x-b03-d-v4 completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Dynamic effects:                 ${DYNAMIC_CSV}"
  echo "Weekly figure PDF:               ${FIGURE_PREFIX}.pdf"
  echo "Weekly figure PNG:               ${FIGURE_PREFIX}.png"
  echo "Timezone audit:                  ${EVENT_TIMEZONE_AUDIT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
