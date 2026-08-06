#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b02 v1: Prepare Python-NCLOC velocity DiD panels
# ============================================================
#
# Purpose:
#   Join the completed Python-only NCLOC measurements from SonarQube and cloc
#   to the final 1,954-row run-x-a05 velocity panel.
#
# Analysis design:
#   - preserve all Model A outcomes, controls, repository identifiers, calendar
#     timing, and treatment timing;
#   - preserve the original Model A NCLOC as ncloc_model_a;
#   - create one SonarQube panel whose generic ncloc column uses
#     ncloc_py_sonarqube;
#   - create one cloc panel whose generic ncloc column uses ncloc_py_cloc;
#   - never average or calibrate the two Python-NCLOC backends;
#   - create a common-sample panel and backend comparison for measurement QC.
#
# Required inputs:
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#   repo_x01/run-x-b01/model_c_ncloc_py_snapshot_results.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_results.csv
#
# Main outputs:
#   repo_x01/run-x-b02/velocity_did_panel_python_ncloc_combined.csv
#   repo_x01/run-x-b02/velocity_did_panel_python_ncloc_sonarqube.csv
#   repo_x01/run-x-b02/velocity_did_panel_python_ncloc_cloc.csv
#   repo_x01/run-x-b02/velocity_did_panel_python_ncloc_common_sample.csv
#   repo_x01/run-x-b02/python_ncloc_snapshot_backend_comparison.csv
#   repo_x01/run-x-b02/python_ncloc_panel_unresolved.csv
#   repo_x01/run-x-b02/python_ncloc_panel_qc.csv
#
# Summary output:
#   repo_x01/tmp/run-x-b02/python_ncloc_panel_summary.csv
#
# Run:
#   bash proc_sh_x01/run-x-b02-prepare-python-ncloc-panels.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   BASE_PANEL_FILE=...
#   SNAPSHOT_MANIFEST_FILE=...
#   LOCAL_RESULTS_FILE=...
#   SONARQUBE_RESULTS_FILE=...
#   STRICT_EXPECTED_COUNTS=1
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b02"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-python-ncloc-panels-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_python_ncloc_panels.py}"

BASE_PANEL_FILE="${BASE_PANEL_FILE:-repo_x01/run-x-a05/velocity_did_panel_model_a.csv}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"
LOCAL_RESULTS_FILE="${LOCAL_RESULTS_FILE:-repo_x01/run-x-b01/model_c_ncloc_py_snapshot_results.csv}"
SONARQUBE_RESULTS_FILE="${SONARQUBE_RESULTS_FILE:-repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_results.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

COMBINED_PANEL_OUTPUT="${COMBINED_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_python_ncloc_combined.csv}"
SONARQUBE_PANEL_OUTPUT="${SONARQUBE_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_python_ncloc_sonarqube.csv}"
CLOC_PANEL_OUTPUT="${CLOC_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_python_ncloc_cloc.csv}"
COMMON_SAMPLE_OUTPUT="${COMMON_SAMPLE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_python_ncloc_common_sample.csv}"
SNAPSHOT_COMPARISON_OUTPUT="${SNAPSHOT_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/python_ncloc_snapshot_backend_comparison.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/python_ncloc_panel_unresolved.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_ncloc_panel_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_ncloc_panel_summary.csv}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1954}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_TREATMENT_PANEL_ROWS="${EXPECTED_TREATMENT_PANEL_ROWS:-914}"
EXPECTED_CONTROL_PANEL_ROWS="${EXPECTED_CONTROL_PANEL_ROWS:-1040}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-706}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import numpy, pandas' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy and pandas." >&2
  exit 1
fi

for numeric_value in \
  "${EXPECTED_PANEL_ROWS}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_PANEL_ROWS}" \
  "${EXPECTED_CONTROL_PANEL_ROWS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: expected-count options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${BASE_PANEL_FILE}" \
  "${SNAPSHOT_MANIFEST_FILE}" \
  "${LOCAL_RESULTS_FILE}" \
  "${SONARQUBE_RESULTS_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
BASE_PANEL_SHA256="$(sha256sum "${BASE_PANEL_FILE}" | awk '{print $1}')"
SNAPSHOT_MANIFEST_SHA256="$(sha256sum "${SNAPSHOT_MANIFEST_FILE}" | awk '{print $1}')"
LOCAL_RESULTS_SHA256="$(sha256sum "${LOCAL_RESULTS_FILE}" | awk '{print $1}')"
SONARQUBE_RESULTS_SHA256="$(sha256sum "${SONARQUBE_RESULTS_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare Python-NCLOC velocity DiD panels"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Base Model A panel:              ${BASE_PANEL_FILE}"
  echo "Base panel SHA256:               ${BASE_PANEL_SHA256}"
  echo "Snapshot manifest:               ${SNAPSHOT_MANIFEST_FILE}"
  echo "Snapshot manifest SHA256:        ${SNAPSHOT_MANIFEST_SHA256}"
  echo "Local cloc results:              ${LOCAL_RESULTS_FILE}"
  echo "Local cloc SHA256:               ${LOCAL_RESULTS_SHA256}"
  echo "SonarQube results:               ${SONARQUBE_RESULTS_FILE}"
  echo "SonarQube SHA256:                ${SONARQUBE_RESULTS_SHA256}"
  echo "Combined panel output:           ${COMBINED_PANEL_OUTPUT}"
  echo "SonarQube panel output:          ${SONARQUBE_PANEL_OUTPUT}"
  echo "cloc panel output:               ${CLOC_PANEL_OUTPUT}"
  echo "Common-sample output:            ${COMMON_SAMPLE_OUTPUT}"
  echo "Snapshot comparison output:      ${SNAPSHOT_COMPARISON_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Expected panel rows:             ${EXPECTED_PANEL_ROWS}"
  echo "Expected snapshots:              ${EXPECTED_SNAPSHOTS}"
  echo "Expected treatment/control rows: ${EXPECTED_TREATMENT_PANEL_ROWS}/${EXPECTED_CONTROL_PANEL_ROWS}"
  echo "Expected treatment/control snaps:${EXPECTED_TREATMENT_SNAPSHOTS}/${EXPECTED_CONTROL_SNAPSHOTS}"
  echo "Expected repositories:           ${EXPECTED_REPOSITORIES}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --base-panel-file "${BASE_PANEL_FILE}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --local-results-file "${LOCAL_RESULTS_FILE}"
  --sonarqube-results-file "${SONARQUBE_RESULTS_FILE}"
  --combined-panel-output "${COMBINED_PANEL_OUTPUT}"
  --sonarqube-panel-output "${SONARQUBE_PANEL_OUTPUT}"
  --cloc-panel-output "${CLOC_PANEL_OUTPUT}"
  --common-sample-output "${COMMON_SAMPLE_OUTPUT}"
  --snapshot-comparison-output "${SNAPSHOT_COMPARISON_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-treatment-panel-rows "${EXPECTED_TREATMENT_PANEL_ROWS}"
  --expected-control-panel-rows "${EXPECTED_CONTROL_PANEL_ROWS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 1: Join SonarQube and cloc NCLOC to the velocity panel"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${COMBINED_PANEL_OUTPUT}"
  "${SONARQUBE_PANEL_OUTPUT}"
  "${CLOC_PANEL_OUTPUT}"
  "${COMMON_SAMPLE_OUTPUT}"
  "${SNAPSHOT_COMPARISON_OUTPUT}"
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
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${COMBINED_PANEL_OUTPUT}" \
    "${SONARQUBE_PANEL_OUTPUT}" \
    "${CLOC_PANEL_OUTPUT}" \
    "${COMMON_SAMPLE_OUTPUT}" \
    "${SNAPSHOT_COMPARISON_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Snapshot comparison preview:"
  head -n 11 "${SNAPSHOT_COMPARISON_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Combined panel:                  ${COMBINED_PANEL_OUTPUT}"
  echo "SonarQube DiD panel:             ${SONARQUBE_PANEL_OUTPUT}"
  echo "cloc DiD panel:                  ${CLOC_PANEL_OUTPUT}"
  echo "Common-sample panel:             ${COMMON_SAMPLE_OUTPUT}"
  echo "Snapshot comparison:             ${SNAPSHOT_COMPARISON_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       run run-x-b03 Borusyak DiD for both Python-NCLOC panels"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
