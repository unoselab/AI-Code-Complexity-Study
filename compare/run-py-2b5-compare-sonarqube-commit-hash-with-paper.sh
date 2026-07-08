#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b5: Compare Python pyv2 SonarQube commit hashes with paper data
# ============================================================
# Purpose:
#   Diagnose whether differences between our Python strict quality DiD result
#   and the paper result come from different checked-out commits or from
#   SonarQube configuration/version differences.
#
# Inputs:
#   PAPER_TREATMENT_TS
#     - Paper treatment monthly time series with latest_commit and metrics.
#     - Default: data/ts_repos_monthly.csv
#
#   PAPER_CONTROL_TS
#     - Paper control monthly time series with latest_commit and metrics.
#     - Default: data/ts_repos_control_monthly.csv
#
#   TREATMENT_SCAN
#     - Our treatment SonarQube scan output.
#     - Default: repo_python/sonarqube_input/strict/treatment/data/ts_repos_monthly_scanned_pyv2.csv
#
#   CONTROL_SCAN
#     - Our control SonarQube scan output.
#     - Default: repo_python/sonarqube_input/strict/control/data/ts_repos_monthly_scanned_pyv2.csv
#
# Outputs:
#   OUTPUT_DIR/sonarqube_commit_overlap_summary.csv
#   OUTPUT_DIR/sonarqube_commit_hash_comparison.csv
#   OUTPUT_DIR/sonarqube_commit_hash_mismatch.csv
#   OUTPUT_DIR/sonarqube_commit_hash_match.csv
#   OUTPUT_DIR/sonarqube_commit_paper_only_repo_months.csv
#   OUTPUT_DIR/sonarqube_commit_our_only_repo_months.csv
#   OUTPUT_DIR/sonarqube_metric_diff_by_commit_match_status.csv
#   OUTPUT_DIR/sonarqube_commit_hash_metric_differences_long.csv
#   OUTPUT_DIR/sonarqube_commit_hash_large_metric_differences.csv
#   OUTPUT_DIR/sonarqube_commit_hash_compare_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b5-compare-sonarqube-commit-hash-with-paper.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b5_compare_sonarqube_commit_hash_with_paper_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

PAPER_TREATMENT_TS="${PAPER_TREATMENT_TS:-data/ts_repos_monthly.csv}"
PAPER_CONTROL_TS="${PAPER_CONTROL_TS:-data/ts_repos_control_monthly.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/compare_sonarqube_commit_hash_with_paper.py}"

TREATMENT_SCAN="${TREATMENT_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/treatment/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"
CONTROL_SCAN="${CONTROL_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/control/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
TOLERANCE="${TOLERANCE:-1e-9}"
TOP_PRINT="${TOP_PRINT:-500}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b5: Compare Python pyv2 SonarQube commit hashes with paper data"
  echo "Started:             $(date)"
  echo "Project root:        $(pwd)"
  echo "Panel variant:       ${PANEL_VARIANT}"
  echo "Scan suffix:         ${SCAN_SUFFIX}"
  echo "Paper treatment TS:  ${PAPER_TREATMENT_TS}"
  echo "Paper control TS:    ${PAPER_CONTROL_TS}"
  echo "Treatment scan:      ${TREATMENT_SCAN}"
  echo "Control scan:        ${CONTROL_SCAN}"
  echo "Python script:       ${PY_SCRIPT}"
  echo "Output dir:          ${OUTPUT_DIR}"
  echo "Tolerance:           ${TOLERANCE}"
  echo "Top print:           ${TOP_PRINT}"
  echo "Log file:            ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

for required_file in \
  "${PAPER_TREATMENT_TS}" \
  "${PAPER_CONTROL_TS}" \
  "${TREATMENT_SCAN}" \
  "${CONTROL_SCAN}" \
  "${PY_SCRIPT}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

set +e
python "${PY_SCRIPT}" \
  --paper-treatment-ts "${PAPER_TREATMENT_TS}" \
  --paper-control-ts "${PAPER_CONTROL_TS}" \
  --treatment-scan "${TREATMENT_SCAN}" \
  --control-scan "${CONTROL_SCAN}" \
  --output-dir "${OUTPUT_DIR}" \
  --tolerance "${TOLERANCE}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b5 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Completed:           $(date)" | tee -a "${LOG_FILE}"
echo "Output dir:          ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for output_file in \
  "${OUTPUT_DIR}/sonarqube_commit_overlap_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_commit_hash_comparison.csv" \
  "${OUTPUT_DIR}/sonarqube_commit_hash_mismatch.csv" \
  "${OUTPUT_DIR}/sonarqube_commit_hash_match.csv" \
  "${OUTPUT_DIR}/sonarqube_metric_diff_by_commit_match_status.csv" \
  "${OUTPUT_DIR}/sonarqube_commit_hash_large_metric_differences.csv" \
  "${OUTPUT_DIR}/sonarqube_commit_hash_compare_notes.md"
do
  if [[ -f "${output_file}" ]]; then
    echo "File: ${output_file}" | tee -a "${LOG_FILE}"
    wc -l "${output_file}" | tee -a "${LOG_FILE}"
  else
    echo "WARNING: expected output file not found: ${output_file}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "run-py-2b5 completed successfully." | tee -a "${LOG_FILE}"
