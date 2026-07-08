#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b4: Check paper-overlap usage in Python pyv2 SonarQube/DiD inputs
# ============================================================
# Purpose:
#   Diagnose whether extra SonarQube scan rows that are not present in the
#   paper panel were actually used in the final Python quality DiD input.
#
#   This script also creates paper-overlap-only SonarQube scan files so that
#   we can later run a paper-compatible pyv2 branch.
#
# Inputs:
#   PAPER_PANEL
#     - Frozen paper monthly panel.
#     - Default: data/panel_event_monthly.csv
#
#   TREATMENT_SCAN
#     - Our treatment SonarQube scan output.
#     - Default:
#       repo_python/sonarqube_input/strict/treatment/data/ts_repos_monthly_scanned_pyv2.csv
#
#   CONTROL_SCAN
#     - Our control SonarQube scan output.
#     - Default:
#       repo_python/sonarqube_input/strict/control/data/ts_repos_monthly_scanned_pyv2.csv
#
#   FINAL_DID_INPUT
#     - Our final complete-case quality DiD input.
#     - Default:
#       repo_python/did_final_pyv2/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv
#
# Outputs:
#   OUTPUT_DIR/sonarqube_paper_overlap_usage_summary.csv
#   OUTPUT_DIR/final_did_rows_missing_in_paper.csv
#   OUTPUT_DIR/final_did_rows_overlap_with_paper.csv
#   OUTPUT_DIR/final_did_rows_missing_in_scan.csv
#   OUTPUT_DIR/final_did_rows_overlap_with_scan.csv
#
#   TREATMENT_OVERLAP_OUTPUT
#     - Treatment scan rows restricted to repo-months present in the paper panel.
#
#   CONTROL_OVERLAP_OUTPUT
#     - Control scan rows restricted to repo-months present in the paper panel.
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b4-check-sonarqube-paper-overlap-usage.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b4_check_sonarqube_paper_overlap_usage_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

PAPER_PANEL="${PAPER_PANEL:-data/panel_event_monthly.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/check_sonarqube_paper_overlap_usage.py}"

TREATMENT_SCAN="${TREATMENT_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/treatment/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"
CONTROL_SCAN="${CONTROL_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/control/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"

DID_FINAL_DIR="${DID_FINAL_DIR:-repo_python/did_final_${SCAN_SUFFIX}}"
FINAL_DID_INPUT="${FINAL_DID_INPUT:-${DID_FINAL_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube_quality_did_input_complete.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"

TREATMENT_OVERLAP_OUTPUT="${TREATMENT_OVERLAP_OUTPUT:-repo_python/sonarqube_input/${PANEL_VARIANT}/treatment/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}_paper_overlap.csv}"
CONTROL_OVERLAP_OUTPUT="${CONTROL_OVERLAP_OUTPUT:-repo_python/sonarqube_input/${PANEL_VARIANT}/control/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}_paper_overlap.csv}"

TOP_PRINT="${TOP_PRINT:-30}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
mkdir -p "$(dirname "${TREATMENT_OVERLAP_OUTPUT}")"
mkdir -p "$(dirname "${CONTROL_OVERLAP_OUTPUT}")"

{
  echo "============================================================"
  echo "run-py-2b4: Check Python pyv2 SonarQube paper-overlap usage"
  echo "Started:                  $(date)"
  echo "Project root:             $(pwd)"
  echo "Panel variant:            ${PANEL_VARIANT}"
  echo "Scan suffix:              ${SCAN_SUFFIX}"
  echo "Paper panel:              ${PAPER_PANEL}"
  echo "Treatment scan:           ${TREATMENT_SCAN}"
  echo "Control scan:             ${CONTROL_SCAN}"
  echo "Final DiD input:          ${FINAL_DID_INPUT}"
  echo "Python script:            ${PY_SCRIPT}"
  echo "Output dir:               ${OUTPUT_DIR}"
  echo "Treatment overlap output: ${TREATMENT_OVERLAP_OUTPUT}"
  echo "Control overlap output:   ${CONTROL_OVERLAP_OUTPUT}"
  echo "Top print:                ${TOP_PRINT}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

for required_file in \
  "${PAPER_PANEL}" \
  "${TREATMENT_SCAN}" \
  "${CONTROL_SCAN}" \
  "${FINAL_DID_INPUT}" \
  "${PY_SCRIPT}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

set +e
python "${PY_SCRIPT}" \
  --paper-panel "${PAPER_PANEL}" \
  --treatment-scan "${TREATMENT_SCAN}" \
  --control-scan "${CONTROL_SCAN}" \
  --final-did-input "${FINAL_DID_INPUT}" \
  --output-dir "${OUTPUT_DIR}" \
  --treatment-overlap-output "${TREATMENT_OVERLAP_OUTPUT}" \
  --control-overlap-output "${CONTROL_OVERLAP_OUTPUT}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b4 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Completed:                $(date)" | tee -a "${LOG_FILE}"
echo "Output dir:               ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Treatment overlap output: ${TREATMENT_OVERLAP_OUTPUT}" | tee -a "${LOG_FILE}"
echo "Control overlap output:   ${CONTROL_OVERLAP_OUTPUT}" | tee -a "${LOG_FILE}"
echo "Log file:                 ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for output_file in \
  "${OUTPUT_DIR}/sonarqube_paper_overlap_usage_summary.csv" \
  "${OUTPUT_DIR}/final_did_rows_missing_in_paper.csv" \
  "${OUTPUT_DIR}/final_did_rows_overlap_with_paper.csv" \
  "${OUTPUT_DIR}/final_did_rows_missing_in_scan.csv" \
  "${OUTPUT_DIR}/final_did_rows_overlap_with_scan.csv" \
  "${TREATMENT_OVERLAP_OUTPUT}" \
  "${CONTROL_OVERLAP_OUTPUT}"
do
  if [[ -f "${output_file}" ]]; then
    echo "File: ${output_file}" | tee -a "${LOG_FILE}"
    wc -l "${output_file}" | tee -a "${LOG_FILE}"
  else
    echo "WARNING: expected output file not found: ${output_file}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "run-py-2b4 completed successfully." | tee -a "${LOG_FILE}"
