#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b6: Diagnose exact-commit SonarQube metric differences
# ============================================================
# Purpose:
#   Diagnose why paper SonarQube metrics and our pyv2 SonarQube metrics
#   differ even when the same repo-month uses the exact same latest_commit.
#
#   This is a comparison/inspection script. It does not rerun SonarQube.
#
# Inputs:
#   COMMIT_COMPARISON
#     - Output from run-py-2b5.
#     - Default:
#       repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_commit_hash_comparison.csv
#
# Outputs:
#   OUTPUT_DIR/sonarqube_exact_commit_metric_summary.csv
#   OUTPUT_DIR/sonarqube_exact_commit_metric_summary_by_ncloc_status.csv
#   OUTPUT_DIR/sonarqube_exact_commit_differences_long.csv
#   OUTPUT_DIR/sonarqube_exact_commit_row_classification.csv
#   OUTPUT_DIR/sonarqube_exact_commit_large_static_warning_diffs.csv
#   OUTPUT_DIR/sonarqube_exact_commit_large_code_smell_diffs.csv
#   OUTPUT_DIR/sonarqube_exact_commit_large_ncloc_diffs.csv
#   OUTPUT_DIR/sonarqube_exact_commit_large_cognitive_complexity_diffs.csv
#   OUTPUT_DIR/sonarqube_exact_commit_diff_by_repo.csv
#   OUTPUT_DIR/sonarqube_exact_commit_diff_by_month.csv
#   OUTPUT_DIR/sonarqube_exact_commit_diff_by_source_group.csv
#   OUTPUT_DIR/sonarqube_exact_commit_diagnosis_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b6-diagnose-sonarqube-exact-commit-differences.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b6_diagnose_sonarqube_exact_commit_differences_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
COMMIT_COMPARISON="${COMMIT_COMPARISON:-${OUTPUT_DIR}/sonarqube_commit_hash_comparison.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/diagnose_sonarqube_exact_commit_differences.py}"

TOLERANCE="${TOLERANCE:-1e-9}"
NCLOC_CLOSE_ABS="${NCLOC_CLOSE_ABS:-10}"
NCLOC_CLOSE_REL="${NCLOC_CLOSE_REL:-0.01}"
TOP_N="${TOP_N:-500}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b6: Diagnose exact-commit SonarQube differences"
  echo "Started:           $(date)"
  echo "Project root:      $(pwd)"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Scan suffix:       ${SCAN_SUFFIX}"
  echo "Commit comparison: ${COMMIT_COMPARISON}"
  echo "Python script:     ${PY_SCRIPT}"
  echo "Output dir:        ${OUTPUT_DIR}"
  echo "Tolerance:         ${TOLERANCE}"
  echo "Ncloc close abs:   ${NCLOC_CLOSE_ABS}"
  echo "Ncloc close rel:   ${NCLOC_CLOSE_REL}"
  echo "Top N:             ${TOP_N}"
  echo "Log file:          ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

for required_file in "${COMMIT_COMPARISON}" "${PY_SCRIPT}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

set +e
python "${PY_SCRIPT}" \
  --commit-comparison "${COMMIT_COMPARISON}" \
  --output-dir "${OUTPUT_DIR}" \
  --tolerance "${TOLERANCE}" \
  --ncloc-close-abs "${NCLOC_CLOSE_ABS}" \
  --ncloc-close-rel "${NCLOC_CLOSE_REL}" \
  --top-n "${TOP_N}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b6 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Completed:         $(date)" | tee -a "${LOG_FILE}"
echo "Output dir:        ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for output_file in \
  "${OUTPUT_DIR}/sonarqube_exact_commit_metric_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_metric_summary_by_ncloc_status.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_differences_long.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_row_classification.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_large_static_warning_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_large_code_smell_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_large_ncloc_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_large_cognitive_complexity_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_diff_by_repo.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_diff_by_month.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_diff_by_source_group.csv" \
  "${OUTPUT_DIR}/sonarqube_exact_commit_diagnosis_notes.md"
do
  if [[ -f "${output_file}" ]]; then
    echo "File: ${output_file}" | tee -a "${LOG_FILE}"
    wc -l "${output_file}" | tee -a "${LOG_FILE}"
  else
    echo "WARNING: expected output file not found: ${output_file}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "run-py-2b6 completed successfully." | tee -a "${LOG_FILE}"
