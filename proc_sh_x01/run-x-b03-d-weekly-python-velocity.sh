#!/usr/bin/env bash
# run-x-b03-d: weekly Python velocity timing-resolution robustness analysis.
#
# Inputs:
#   1. run-x-b02-v4 final common monthly panel for the fixed repository roster
#      and per-repository support range.
#   2. run-x-b02-v4 commit-level Python added-lines output. The Python panel
#      builder re-aggregates these validated commit outcomes to weeks; it does
#      not call or depend on the previous b02 shell script.
#   3. run-x-b03-c treatment-history summary with the exact first observable
#      Cursor-related commit timestamp for every treated repository.
#
# Outputs:
#   - Two compact weekly panels: America/New_York and America/Chicago.
#   - Timezone/support/reaggregation audits and QC CSVs.
#   - FE-only Borusyak weekly static/dynamic/pretrend CSVs.
#   - One compact PDF plot for the primary weekly event study.
#
# This wrapper is self-contained. It reuses the established project execution
# pattern but never invokes an older experiment shell script.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
IMPLEMENTATION_VERSION="v1"

PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_weekly_python_velocity_panel.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_python_added_lines_weekly.R}"

MONTHLY_PANEL_FILE="${MONTHLY_PANEL_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_common_sample.csv}"
COMMIT_FILE="${COMMIT_FILE:-repo_x01/run-x-b02/python-added-lines/python_added_lines_commit.csv}"
TREATMENT_HISTORY_FILE="${TREATMENT_HISTORY_FILE:-repo_x01/run-x-b03-c/cursor_treatment_history_repo_summary.csv}"

OUTPUT_BASE="${OUTPUT_BASE:-repo_x01/run-x-b03-d}"
PANEL_DIR="${PANEL_DIR:-${OUTPUT_BASE}/panels}"
AUDIT_DIR="${AUDIT_DIR:-${OUTPUT_BASE}/audit}"
DID_DIR="${DID_DIR:-${OUTPUT_BASE}/weekly_did}"
TMP_DIR="${TMP_DIR:-repo_x01/tmp/run-x-b03-d/v1}"

NEW_YORK_PANEL="${NEW_YORK_PANEL:-${PANEL_DIR}/velocity_did_panel_python_added_lines_weekly_new_york.csv}"
CHICAGO_PANEL="${CHICAGO_PANEL:-${PANEL_DIR}/velocity_did_panel_python_added_lines_weekly_chicago.csv}"
EVENT_TIMEZONE_AUDIT="${EVENT_TIMEZONE_AUDIT:-${AUDIT_DIR}/weekly_treatment_event_timezone_audit.csv}"
INTERNAL_GAP_AUDIT="${INTERNAL_GAP_AUDIT:-${AUDIT_DIR}/weekly_internal_month_gap_audit.csv}"
CALENDAR_OUTCOME_COMPARISON="${CALENDAR_OUTCOME_COMPARISON:-${AUDIT_DIR}/weekly_calendar_outcome_comparison.csv}"
PANEL_QC="${PANEL_QC:-${AUDIT_DIR}/weekly_panel_qc.csv}"
PANEL_SUMMARY="${PANEL_SUMMARY:-${TMP_DIR}/weekly_panel_summary.csv}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_MONTHLY_ROWS="${EXPECTED_MONTHLY_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_WEEKLY_ROWS="${EXPECTED_WEEKLY_ROWS:-8599}"
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

mkdir -p logs "${PANEL_DIR}" "${AUDIT_DIR}" "${DID_DIR}" "${TMP_DIR}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run-x-b03-d-v1-weekly-python-velocity-${TIMESTAMP}.log}"

sha256_or_na() {
  if [[ -f "$1" ]]; then
    sha256sum "$1" | awk '{print $1}'
  else
    printf 'NA'
  fi
}

{
  echo "============================================================"
  echo "run-x-b03-d-v1: weekly Python velocity timing robustness"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python panel script:              ${PY_SCRIPT}"
  echo "Python script SHA256:             $(sha256_or_na "${PY_SCRIPT}")"
  echo "R analysis script:                ${R_SCRIPT}"
  echo "R script SHA256:                  $(sha256_or_na "${R_SCRIPT}")"
  echo "Monthly b02 common panel:         ${MONTHLY_PANEL_FILE}"
  echo "b02 commit-level outcome file:    ${COMMIT_FILE}"
  echo "b03-c treatment-history summary:  ${TREATMENT_HISTORY_FILE}"
  echo "Primary weekly outcome:           log_lines_added_py_source"
  echo "Calendar variants:                America/New_York | America/Chicago"
  echo "Week definition:                  Monday-start"
  echo "Weekly first stage:               ~ 1 | repo_id + time_index"
  echo "Dynamic window:                   ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT} weeks"
  echo "Pretrend window:                  ${PRETREND_MIN}:${PRETREND_MAX} weeks"
  echo "Reference event week:             -1"
  echo "Expected weekly rows/calendar:    ${EXPECTED_WEEKLY_ROWS}"
  echo "Expected treatment/control repos: ${EXPECTED_TREATMENT_REPOSITORIES}/${EXPECTED_CONTROL_REPOSITORIES}"
  echo "Output base:                      ${OUTPUT_BASE}"
  echo "Log file:                         ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Validate weekly Python panel builder"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
  echo
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${PY_SCRIPT}" --self-test --log-level "${LOG_LEVEL}" 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Compile weekly Python panel builder"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
  echo
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "Self-test-only run completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_file in "${MONTHLY_PANEL_FILE}" "${COMMIT_FILE}" "${TREATMENT_HISTORY_FILE}" "${R_SCRIPT}"; do
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
  echo "** Step 3: Re-aggregate validated b02-v4 commit outcomes to weekly panels"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${PANEL_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${PANEL_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

DID_COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --new-york-panel "${NEW_YORK_PANEL}"
  --chicago-panel "${CHICAGO_PANEL}"
  --output-dir "${DID_DIR}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-rows "${EXPECTED_WEEKLY_ROWS}"
  --expected-treatment-repos "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repos "${EXPECTED_CONTROL_REPOSITORIES}"
)

{
  echo
  echo "** Step 4: Run FE-only Borusyak weekly event study"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${DID_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${DID_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${NEW_YORK_PANEL}"
  "${CHICAGO_PANEL}"
  "${EVENT_TIMEZONE_AUDIT}"
  "${INTERNAL_GAP_AUDIT}"
  "${CALENDAR_OUTCOME_COMPARISON}"
  "${PANEL_QC}"
  "${PANEL_SUMMARY}"
  "${DID_DIR}/velocity_python_added_lines_weekly_static_effects.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_dynamic_effects.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_pretrend_checks.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_pretrend_summary.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_primary_key_window.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_calendar_static_differences.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_calendar_dynamic_differences.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_event_support.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_sample_summary.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_diagnostics.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_qc.csv"
  "${DID_DIR}/velocity_python_added_lines_weekly_summary.csv"
  "${DID_DIR}/plots/velocity_python_added_lines_weekly_primary_dynamic_effects.pdf"
)

{
  echo
  echo "** Step 5: Output checks"
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
  echo "Weekly DiD QC:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_qc.csv"
  echo
  echo "Primary weekly key window:"
  cat "${DID_DIR}/velocity_python_added_lines_weekly_primary_key_window.csv"
  echo
  echo "============================================================"
  echo "run-x-b03-d-v1 completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary outcome:                 log_lines_added_py_source"
  echo "Weekly panels:                   ${NEW_YORK_PANEL} | ${CHICAGO_PANEL}"
  echo "Treatment-week timezone audit:   ${EVENT_TIMEZONE_AUDIT}"
  echo "Primary weekly key window:       ${DID_DIR}/velocity_python_added_lines_weekly_primary_key_window.csv"
  echo "Weekly pretrend summary:         ${DID_DIR}/velocity_python_added_lines_weekly_pretrend_summary.csv"
  echo "Weekly dynamic effects:          ${DID_DIR}/velocity_python_added_lines_weekly_dynamic_effects.csv"
  echo "Weekly timing plot:              ${DID_DIR}/plots/velocity_python_added_lines_weekly_primary_dynamic_effects.pdf"
  echo "Panel QC:                        ${PANEL_QC}"
  echo "DiD QC:                          ${DID_DIR}/velocity_python_added_lines_weekly_qc.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next decision:                   whether activity rises specifically 1-4 weeks before the first observable Cursor evidence."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
