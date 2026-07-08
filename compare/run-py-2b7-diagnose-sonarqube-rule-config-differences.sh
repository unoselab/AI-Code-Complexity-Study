#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b7: Diagnose SonarQube rule/config/analyzer differences
# ============================================================
# Purpose:
#   Diagnose whether paper and our Python pyv2 SonarQube warning metrics differ
#   even when repo-month, latest_commit, and ncloc are identical.
#
#   This is the strongest diagnostic subset for rule/config/analyzer differences:
#     - same repo_name
#     - same month
#     - same latest_commit
#     - same ncloc
#
# Inputs:
#   EXACT_COMMIT_CLASSIFICATION
#     - Output from run-py-2b6.
#     - Default:
#       repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_exact_commit_row_classification.csv
#
# Outputs:
#   OUTPUT_DIR/sonarqube_rule_config_signal_summary.csv
#   OUTPUT_DIR/sonarqube_rule_config_warning_metric_summary.csv
#   OUTPUT_DIR/sonarqube_rule_config_all_metric_summary.csv
#   OUTPUT_DIR/sonarqube_rule_config_diff_by_repo.csv
#   OUTPUT_DIR/sonarqube_rule_config_diff_by_month.csv
#   OUTPUT_DIR/sonarqube_rule_config_diff_by_source_group.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_static_warning_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_static_warning_negative_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_static_warning_positive_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_code_smell_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_code_smell_negative_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_large_code_smell_positive_diffs.csv
#   OUTPUT_DIR/sonarqube_rule_config_row_subset.csv
#   OUTPUT_DIR/sonarqube_rule_config_diagnosis_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b7-diagnose-sonarqube-rule-config-differences.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b7_diagnose_sonarqube_rule_config_differences_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
EXACT_COMMIT_CLASSIFICATION="${EXACT_COMMIT_CLASSIFICATION:-${OUTPUT_DIR}/sonarqube_exact_commit_row_classification.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/diagnose_sonarqube_rule_config_differences.py}"

TOLERANCE="${TOLERANCE:-1e-9}"
TOP_N="${TOP_N:-500}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b7: Diagnose SonarQube rule/config/analyzer differences"
  echo "Started:                     $(date)"
  echo "Project root:                $(pwd)"
  echo "Panel variant:               ${PANEL_VARIANT}"
  echo "Scan suffix:                 ${SCAN_SUFFIX}"
  echo "Exact commit classification: ${EXACT_COMMIT_CLASSIFICATION}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Output dir:                  ${OUTPUT_DIR}"
  echo "Tolerance:                   ${TOLERANCE}"
  echo "Top N:                       ${TOP_N}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

for required_file in \
  "${EXACT_COMMIT_CLASSIFICATION}" \
  "${PY_SCRIPT}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

set +e
python "${PY_SCRIPT}" \
  --exact-commit-classification "${EXACT_COMMIT_CLASSIFICATION}" \
  --output-dir "${OUTPUT_DIR}" \
  --tolerance "${TOLERANCE}" \
  --top-n "${TOP_N}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b7 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Completed:    $(date)" | tee -a "${LOG_FILE}"
echo "Output dir:   ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:     ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for output_file in \
  "${OUTPUT_DIR}/sonarqube_rule_config_signal_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_warning_metric_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_all_metric_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_diff_by_repo.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_diff_by_month.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_diff_by_source_group.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_static_warning_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_static_warning_negative_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_static_warning_positive_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_code_smell_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_code_smell_negative_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_large_code_smell_positive_diffs.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_row_subset.csv" \
  "${OUTPUT_DIR}/sonarqube_rule_config_diagnosis_notes.md"
do
  if [[ -f "${output_file}" ]]; then
    echo "File: ${output_file}" | tee -a "${LOG_FILE}"
    wc -l "${output_file}" | tee -a "${LOG_FILE}"
  else
    echo "WARNING: expected output file not found: ${output_file}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "run-py-2b7 completed successfully." | tee -a "${LOG_FILE}"
