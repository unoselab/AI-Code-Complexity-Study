#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b06 v1: Prepare Python-only SonarQube quality DiD panel
# ============================================================
#
# Purpose:
#   1. Reuse the exact monthly Python panel validated by run-x-b02.
#   2. Join the full run-x-b05 Python-only SonarQube issue stock for each
#      historical snapshot without rescanning source code or querying SonarQube.
#   3. Build burden and density quality outcomes for run-x-b07 DiD analysis.
#   4. Enforce snapshot identity, Python NCLOC, snapshot-reuse, and issue-count
#      reconciliation checks before the quality panel is accepted.
#
# Primary outcome prepared for run-x-b07:
#   log_issue_total_py_sonarqube
#
# Primary density robustness outcome:
#   log_issues_per_kloc_py_sonarqube
#
# Additional robustness outcomes include Python code-smell, bug,
# vulnerability, software-quality-impact, and high-severity issue stocks.
#
# Important semantics:
#   - The quality metric is the unresolved SonarQube issue stock present in the
#     historical Python-only source snapshot.
#   - It is not the number of issues newly introduced in that calendar month.
#   - One run-x-b01 SonarQube project represents one historical snapshot.
#   - A historical snapshot can represent more than one repo-month when no new
#     commit occurred; run-x-b06 verifies this reuse against run-x-b05 metadata.
#
# Required inputs:
#   repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv
#
# Python program:
#   proc_script_x01/prepare_python_quality_did_panel.py
#
# Outputs:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#   repo_x01/run-x-b06/python_quality_snapshot_join_audit.csv
#   repo_x01/run-x-b06/python_quality_panel_distribution_summary.csv
#   repo_x01/run-x-b06/python_quality_outcome_manifest.csv
#   repo_x01/run-x-b06/python_quality_panel_unresolved.csv
#   repo_x01/run-x-b06/python_quality_panel_qc.csv
#   repo_x01/run-x-b06/python_quality_panel_summary.csv
#
# Full run:
#   bash proc_sh_x01/run-x-b06-prepare-python-quality-did-panel.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-b06-prepare-python-quality-did-panel.sh
#
# Useful overrides:
#   PYTHON_BIN=/path/to/python
#   BASE_PANEL_FILE=...
#   B05_SNAPSHOT_COUNTS_FILE=...
#   OUTPUT_BASE_DIR=repo_x01
#   STRICT_EXPECTED_COUNTS=1
#   SELF_TEST_ONLY=0
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b06"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-python-quality-did-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PANEL_SCRIPT="${PANEL_SCRIPT:-proc_script_x01/prepare_python_quality_did_panel.py}"

# Reuse the exact SonarQube-backend Python velocity panel so treatment timing,
# covariates, Python NCLOC, and snapshot identity remain identical to run-x-b03.
BASE_PANEL_FILE="${BASE_PANEL_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
B05_SNAPSHOT_COUNTS_FILE="${B05_SNAPSHOT_COUNTS_FILE:-repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
PANEL_OUTPUT_DIR="${PANEL_OUTPUT_DIR:-${MAIN_OUTPUT_DIR}/panels}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

QUALITY_PANEL_OUTPUT="${QUALITY_PANEL_OUTPUT:-${PANEL_OUTPUT_DIR}/quality_did_panel_python_sonarqube.csv}"
SNAPSHOT_JOIN_AUDIT_OUTPUT="${SNAPSHOT_JOIN_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_snapshot_join_audit.csv}"
DISTRIBUTION_SUMMARY_OUTPUT="${DISTRIBUTION_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_panel_distribution_summary.csv}"
OUTCOME_MANIFEST_OUTPUT="${OUTCOME_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_outcome_manifest.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_panel_unresolved.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_panel_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_quality_panel_summary.csv}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-914}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-1040}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"

for boolean_name in STRICT_EXPECTED_COUNTS SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${EXPECTED_PANEL_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_ROWS}" \
  "${EXPECTED_CONTROL_ROWS}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}" \
  "${EXPECTED_SNAPSHOTS}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: expected-count options must contain non-negative integers." >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -f "${PANEL_SCRIPT}" ]]; then
  echo "ERROR: required analysis program not found: ${PANEL_SCRIPT}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import numpy, pandas' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy and pandas." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${PANEL_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PANEL_SCRIPT_SHA256="$(sha256sum "${PANEL_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare Python-only SonarQube quality DiD panel"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Panel builder:                   ${PANEL_SCRIPT}"
  echo "Panel builder SHA256:            ${PANEL_SCRIPT_SHA256}"
  echo "Base monthly Python panel:       ${BASE_PANEL_FILE}"
  echo "B05 snapshot issue counts:       ${B05_SNAPSHOT_COUNTS_FILE}"
  echo "Primary quality outcome:         log_issue_total_py_sonarqube"
  echo "Primary density outcome:         log_issues_per_kloc_py_sonarqube"
  echo "Quality scope:                   Python-only SonarQube snapshots"
  echo "Quality count semantics:         unresolved issue stock at historical snapshot"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Self-test only:                  ${SELF_TEST_ONLY}"
  echo "Expected rows/repositories:      ${EXPECTED_PANEL_ROWS}/${EXPECTED_REPOSITORIES}"
  echo "Expected treatment/control rows: ${EXPECTED_TREATMENT_ROWS}/${EXPECTED_CONTROL_ROWS}"
  echo "Expected treatment/control repos:${EXPECTED_TREATMENT_REPOSITORIES}/${EXPECTED_CONTROL_REPOSITORIES}"
  echo "Expected snapshots:              ${EXPECTED_SNAPSHOTS}"
  echo "Quality DiD panel:               ${QUALITY_PANEL_OUTPUT}"
  echo "Snapshot join audit:             ${SNAPSHOT_JOIN_AUDIT_OUTPUT}"
  echo "Distribution summary:            ${DISTRIBUTION_SUMMARY_OUTPUT}"
  echo "Outcome manifest:                ${OUTCOME_MANIFEST_OUTPUT}"
  echo "Unresolved audit:                ${UNRESOLVED_OUTPUT}"
  echo "Panel QC:                        ${QC_OUTPUT}"
  echo "Panel summary:                   ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

run_command_logged() {
  local step_title="$1"
  shift
  local -a command=("$@")
  {
    echo
    echo "** ${step_title}"
    echo "------------------------------------------------------------"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"
  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

run_command_logged \
  "Step 1: Run panel-builder structural self-test" \
  "${PYTHON_BIN}" "${PANEL_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile panel builder" \
  "${PYTHON_BIN}" -m py_compile "${PANEL_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_input in "${BASE_PANEL_FILE}" "${B05_SNAPSHOT_COUNTS_FILE}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

PANEL_COMMAND=(
  "${PYTHON_BIN}"
  "${PANEL_SCRIPT}"
  --base-panel-file "${BASE_PANEL_FILE}"
  --b05-snapshot-counts-file "${B05_SNAPSHOT_COUNTS_FILE}"
  --panel-output "${QUALITY_PANEL_OUTPUT}"
  --snapshot-join-audit-output "${SNAPSHOT_JOIN_AUDIT_OUTPUT}"
  --distribution-summary-output "${DISTRIBUTION_SUMMARY_OUTPUT}"
  --outcome-manifest-output "${OUTCOME_MANIFEST_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}"
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --log-level "${LOG_LEVEL}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  PANEL_COMMAND+=(--strict-expected-counts)
fi
run_command_logged "Step 3: Build Python quality DiD panel" "${PANEL_COMMAND[@]}"

EXPECTED_OUTPUTS=(
  "${QUALITY_PANEL_OUTPUT}"
  "${SNAPSHOT_JOIN_AUDIT_OUTPUT}"
  "${DISTRIBUTION_SUMMARY_OUTPUT}"
  "${OUTCOME_MANIFEST_OUTPUT}"
  "${UNRESOLVED_OUTPUT}"
  "${QC_OUTPUT}"
  "${SUMMARY_OUTPUT}"
)

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 4: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${QUALITY_PANEL_OUTPUT}" \
    "${SNAPSHOT_JOIN_AUDIT_OUTPUT}" \
    "${DISTRIBUTION_SUMMARY_OUTPUT}" \
    "${OUTCOME_MANIFEST_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Panel QC:"
  cat "${QC_OUTPUT}"
  echo
  echo "Panel summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Outcome manifest:"
  cat "${OUTCOME_MANIFEST_OUTPUT}"
  echo
  echo "Snapshot join audit preview:"
  head -n 11 "${SNAPSHOT_JOIN_AUDIT_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Quality DiD panel:               ${QUALITY_PANEL_OUTPUT}"
  echo "Snapshot join audit:             ${SNAPSHOT_JOIN_AUDIT_OUTPUT}"
  echo "Distribution summary:            ${DISTRIBUTION_SUMMARY_OUTPUT}"
  echo "Outcome manifest:                ${OUTCOME_MANIFEST_OUTPUT}"
  echo "Panel QC:                        ${QC_OUTPUT}"
  echo "Panel summary:                   ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       run-x-b07 Borusyak Python quality DiD"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
