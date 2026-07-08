#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b8: Summarize likely causes of SonarQube differences
# ============================================================
# Purpose:
#   Combine diagnostics from run-py-2b5, run-py-2b6, and run-py-2b7
#   to quantify likely causes of paper-vs-pyv2 SonarQube metric differences.
#
# Cause categories:
#   - commit_selection_difference
#   - source_scope_difference_or_mixed
#   - rule_config_analyzer_profile_signal
#   - paper_commit_missing
#   - other/unclassified categories
#
# Inputs:
#   COMMIT_DIFF_LONG
#     - Long-format metric difference file from run-py-2b5.
#
#   EXACT_ROW_CLASSIFICATION
#     - Exact-commit row classification file from run-py-2b6.
#
# Outputs:
#   OUTPUT_DIR/sonarqube_difference_cause_summary.csv
#   OUTPUT_DIR/sonarqube_difference_cause_summary_by_metric.csv
#   OUTPUT_DIR/sonarqube_difference_cause_rule_config_signal.csv
#   OUTPUT_DIR/sonarqube_difference_cause_top_repos.csv
#   OUTPUT_DIR/sonarqube_difference_cause_negative_outliers.csv
#   OUTPUT_DIR/sonarqube_difference_cause_positive_outliers.csv
#   OUTPUT_DIR/sonarqube_difference_cause_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b8-summarize-sonarqube-difference-causes.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b8_summarize_sonarqube_difference_causes_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/summarize_sonarqube_difference_causes.py}"

COMMIT_DIFF_LONG="${COMMIT_DIFF_LONG:-${OUTPUT_DIR}/sonarqube_commit_hash_metric_differences_long.csv}"
EXACT_ROW_CLASSIFICATION="${EXACT_ROW_CLASSIFICATION:-${OUTPUT_DIR}/sonarqube_exact_commit_row_classification.csv}"
RULE_CONFIG_SUBSET="${RULE_CONFIG_SUBSET:-${OUTPUT_DIR}/sonarqube_rule_config_row_subset.csv}"

TOP_N="${TOP_N:-500}"
TOLERANCE="${TOLERANCE:-1e-9}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b8: Summarize likely causes of SonarQube differences"
  echo "Started:                  $(date)"
  echo "Project root:             $(pwd)"
  echo "Panel variant:            ${PANEL_VARIANT}"
  echo "Scan suffix:              ${SCAN_SUFFIX}"
  echo "Commit diff long:         ${COMMIT_DIFF_LONG}"
  echo "Exact row classification: ${EXACT_ROW_CLASSIFICATION}"
  echo "Rule config subset:       ${RULE_CONFIG_SUBSET}"
  echo "Python script:            ${PY_SCRIPT}"
  echo "Output dir:               ${OUTPUT_DIR}"
  echo "Top N:                    ${TOP_N}"
  echo "Tolerance:                ${TOLERANCE}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

for required_file in \
  "${PY_SCRIPT}" \
  "${COMMIT_DIFF_LONG}" \
  "${EXACT_ROW_CLASSIFICATION}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

CMD=(
  python "${PY_SCRIPT}"
  --commit-diff-long "${COMMIT_DIFF_LONG}"
  --exact-row-classification "${EXACT_ROW_CLASSIFICATION}"
  --output-dir "${OUTPUT_DIR}"
  --top-n "${TOP_N}"
  --tolerance "${TOLERANCE}"
)

if [[ -f "${RULE_CONFIG_SUBSET}" ]]; then
  CMD+=(--rule-config-subset "${RULE_CONFIG_SUBSET}")
fi

set +e
"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b8 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Completed:  $(date)" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:   ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for output_file in \
  "${OUTPUT_DIR}/sonarqube_difference_cause_summary.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_summary_by_metric.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_summary_by_source_group.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_rule_config_signal.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_top_repos.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_negative_outliers.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_positive_outliers.csv" \
  "${OUTPUT_DIR}/sonarqube_difference_cause_notes.md"
do
  if [[ -f "${output_file}" ]]; then
    echo "File: ${output_file}" | tee -a "${LOG_FILE}"
    wc -l "${output_file}" | tee -a "${LOG_FILE}"
  else
    echo "WARNING: expected output file not found: ${output_file}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "run-py-2b8 completed successfully." | tee -a "${LOG_FILE}"
