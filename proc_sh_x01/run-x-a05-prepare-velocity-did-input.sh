#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a05 v2: Prepare pooled Python velocity DiD input
# ============================================================
#
# Purpose:
#   Build the original-style pooled repository-month panel used for the
#   velocity DiD analysis. The original matching assignments define the unique
#   control pool, but reused controls are not duplicated in the pooled panel.
#
# Treatment rows:
#   - valid Cursor adoption event;
#   - Python-eligible repository-month.
#
# Control rows:
#   - repository belongs to the unique controls connected to valid-event
#     candidate treatments in run-x-a04;
#   - repository-month exists in the original panel window;
#   - Python-eligible repository-month.
#
# Model A variables:
#   Outcomes:
#     log1p(commits), log1p(lines_added)
#   Covariates:
#     log1p(age), ncloc, log1p(contributors), log1p(stars), log1p(issues)
#   Fixed effects will be applied later in run-x-a06 using repo_id and
#   time_index.
#
# Control-adoption protection:
#   If an original candidate control later adopts Cursor, only rows strictly
#   before its adoption month are retained. Rows at or after adoption are
#   censored and written to the exclusion/QC outputs.
#
# Important:
#   run-x-a04 pairwise coverage is merged into treatment rows for QC only.
#   A treatment row is not removed merely because its own three matched
#   controls have zero usable Python slots in that month.
#
# Required inputs:
#   repo_x01/run-x-a01/clonedrepo_matching_pairs.csv
#   repo_x01/run-x-a03/panel_event_monthly_python_eligibility.csv
#   repo_x01/run-x-a04/control_reuse_summary.csv
#   repo_x01/run-x-a04/treatment_month_control_python_coverage.csv
#
# Main outputs:
#   repo_x01/run-x-a05/velocity_did_panel_python_pooled.csv
#   repo_x01/run-x-a05/velocity_did_panel_model_a_complete_case.csv
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#   repo_x01/run-x-a05/velocity_did_treatment_estimability_audit.csv
#   repo_x01/run-x-a05/velocity_did_row_exclusions.csv
#   repo_x01/run-x-a05/velocity_did_control_pool_audit.csv
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#
# QC output:
#   repo_x01/tmp/run-x-a05/velocity_did_input_summary.csv
#
# Run:
#   bash proc_sh_x01/run-x-a05-prepare-velocity-did-input.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   START_MONTH=2024-01
#   END_MONTH=2025-08
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a05"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-velocity-did-input-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_velocity_did_input.py}"

MATCHING_PAIRS_FILE="${MATCHING_PAIRS_FILE:-repo_x01/run-x-a01/clonedrepo_matching_pairs.csv}"
PANEL_FILE="${PANEL_FILE:-repo_x01/run-x-a03/panel_event_monthly_python_eligibility.csv}"
CONTROL_REUSE_FILE="${CONTROL_REUSE_FILE:-repo_x01/run-x-a04/control_reuse_summary.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-repo_x01/run-x-a04/treatment_month_control_python_coverage.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

POOLED_PANEL_OUTPUT="${POOLED_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_python_pooled.csv}"
MODEL_A_COMPLETE_CASE_OUTPUT="${MODEL_A_COMPLETE_CASE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_model_a_complete_case.csv}"
MODEL_A_PANEL_OUTPUT="${MODEL_A_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_model_a.csv}"
TREATMENT_ESTIMABILITY_AUDIT_OUTPUT="${TREATMENT_ESTIMABILITY_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_treatment_estimability_audit.csv}"
ROW_EXCLUSIONS_OUTPUT="${ROW_EXCLUSIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_row_exclusions.csv}"
CONTROL_POOL_AUDIT_OUTPUT="${CONTROL_POOL_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_control_pool_audit.csv}"
MODEL_C_SNAPSHOT_MANIFEST_OUTPUT="${MODEL_C_SNAPSHOT_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_model_c_snapshot_manifest.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_did_input_summary.csv}"

START_MONTH="${START_MONTH:-2024-01}"
END_MONTH="${END_MONTH:-2025-08}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

if ! [[ "${START_MONTH}" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
  echo "ERROR: START_MONTH must use YYYY-MM format." >&2
  exit 1
fi

if ! [[ "${END_MONTH}" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
  echo "ERROR: END_MONTH must use YYYY-MM format." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${MATCHING_PAIRS_FILE}" \
  "${PANEL_FILE}" \
  "${CONTROL_REUSE_FILE}" \
  "${COVERAGE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare pooled Python velocity DiD input"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Matching pairs input:        ${MATCHING_PAIRS_FILE}"
  echo "Enriched panel input:        ${PANEL_FILE}"
  echo "Control reuse input:         ${CONTROL_REUSE_FILE}"
  echo "Coverage input:              ${COVERAGE_FILE}"
  echo "Pooled panel output:         ${POOLED_PANEL_OUTPUT}"
  echo "Model A complete-case:       ${MODEL_A_COMPLETE_CASE_OUTPUT}"
  echo "Model A estimable panel:     ${MODEL_A_PANEL_OUTPUT}"
  echo "Treatment estimability:      ${TREATMENT_ESTIMABILITY_AUDIT_OUTPUT}"
  echo "Row exclusions output:       ${ROW_EXCLUSIONS_OUTPUT}"
  echo "Control pool audit output:   ${CONTROL_POOL_AUDIT_OUTPUT}"
  echo "Model C snapshot manifest:   ${MODEL_C_SNAPSHOT_MANIFEST_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Analysis window:             ${START_MONTH}:${END_MONTH}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --matching-pairs-file "${MATCHING_PAIRS_FILE}"
  --panel-file "${PANEL_FILE}"
  --control-reuse-file "${CONTROL_REUSE_FILE}"
  --coverage-file "${COVERAGE_FILE}"
  --pooled-panel-output "${POOLED_PANEL_OUTPUT}"
  --model-a-complete-case-output "${MODEL_A_COMPLETE_CASE_OUTPUT}"
  --model-a-panel-output "${MODEL_A_PANEL_OUTPUT}"
  --treatment-estimability-audit-output "${TREATMENT_ESTIMABILITY_AUDIT_OUTPUT}"
  --row-exclusions-output "${ROW_EXCLUSIONS_OUTPUT}"
  --control-pool-audit-output "${CONTROL_POOL_AUDIT_OUTPUT}"
  --model-c-snapshot-manifest-output "${MODEL_C_SNAPSHOT_MANIFEST_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --start-month "${START_MONTH}"
  --end-month "${END_MONTH}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 1: Build unique repository-month Python velocity panel"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${POOLED_PANEL_OUTPUT}" \
  "${MODEL_A_COMPLETE_CASE_OUTPUT}" \
  "${MODEL_A_PANEL_OUTPUT}" \
  "${TREATMENT_ESTIMABILITY_AUDIT_OUTPUT}" \
  "${ROW_EXCLUSIONS_OUTPUT}" \
  "${CONTROL_POOL_AUDIT_OUTPUT}" \
  "${MODEL_C_SNAPSHOT_MANIFEST_OUTPUT}" \
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
    "${POOLED_PANEL_OUTPUT}" \
    "${MODEL_A_COMPLETE_CASE_OUTPUT}" \
    "${MODEL_A_PANEL_OUTPUT}" \
    "${TREATMENT_ESTIMABILITY_AUDIT_OUTPUT}" \
    "${ROW_EXCLUSIONS_OUTPUT}" \
    "${CONTROL_POOL_AUDIT_OUTPUT}" \
    "${MODEL_C_SNAPSHOT_MANIFEST_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Pooled panel output:         ${POOLED_PANEL_OUTPUT}"
  echo "Model A complete-case:       ${MODEL_A_COMPLETE_CASE_OUTPUT}"
  echo "Model A estimable panel:     ${MODEL_A_PANEL_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   review Model A sample before run-x-a06 Borusyak DiD"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
