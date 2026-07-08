#!/usr/bin/env bash
set -euo pipefail

# run-py-2b9: Identify the main drivers of SonarQube paper-vs-pyv2 differences.
#
# Inputs:
#   1. Commit-level metric-difference file from run-py-2b5:
#      repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_commit_hash_metric_differences_long.csv
#   2. Exact-commit row classification file from run-py-2b6:
#      repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_exact_commit_row_classification.csv
#   3. Rule/config subset file from run-py-2b7:
#      repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_rule_config_row_subset.csv
#   4. Final quality DiD input file:
#      repo_python/did_final_<suffix>/panel_event_matched_<panel>_with_sonarqube_quality_did_input_complete.csv
#
# Outputs:
#   - Cause summaries for all overlap rows.
#   - Cause summaries restricted to final DiD input rows.
#   - Treatment/post and event-time summaries for final DiD input rows.
#   - Final-DiD outlier repositories and positive/negative outlier rows.
#
# This wrapper does not call earlier shell wrappers. It only reuses their CSV
# outputs as static inputs for the new diagnostic analysis.
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b9-identify-sonarqube-main-difference-drivers.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"
COMPARE_DIR="${COMPARE_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/identify_sonarqube_main_difference_drivers.py}"

COMMIT_DIFF_LONG="${COMMIT_DIFF_LONG:-${COMPARE_DIR}/sonarqube_commit_hash_metric_differences_long.csv}"
EXACT_ROW_CLASSIFICATION="${EXACT_ROW_CLASSIFICATION:-${COMPARE_DIR}/sonarqube_exact_commit_row_classification.csv}"
RULE_CONFIG_SUBSET="${RULE_CONFIG_SUBSET:-${COMPARE_DIR}/sonarqube_rule_config_row_subset.csv}"
FINAL_DID_INPUT="${FINAL_DID_INPUT:-repo_python/did_final_${SCAN_SUFFIX}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube_quality_did_input_complete.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-${COMPARE_DIR}}"
TOP_N="${TOP_N:-500}"
TOLERANCE="${TOLERANCE:-1e-9}"

mkdir -p logs "${OUTPUT_DIR}"
LOG_FILE="logs/run-py-2b9_identify_sonarqube_main_difference_drivers_$(date +%Y%m%d-%H%M%S).log"

required_files=(
  "${PY_SCRIPT}"
  "${COMMIT_DIFF_LONG}"
  "${EXACT_ROW_CLASSIFICATION}"
  "${RULE_CONFIG_SUBSET}"
  "${FINAL_DID_INPUT}"
)

for file_path in "${required_files[@]}"; do
  if [[ ! -f "${file_path}" ]]; then
    echo "ERROR: Required file does not exist: ${file_path}" >&2
    exit 1
  fi
done

{
  echo "============================================================"
  echo "run-py-2b9: Identify SonarQube main difference drivers"
  echo "Started:                  $(date)"
  echo "Project root:             ${PROJECT_ROOT}"
  echo "Panel variant:            ${PANEL_VARIANT}"
  echo "Scan suffix:              ${SCAN_SUFFIX}"
  echo "Commit diff long:         ${COMMIT_DIFF_LONG}"
  echo "Exact row classification: ${EXACT_ROW_CLASSIFICATION}"
  echo "Rule config subset:       ${RULE_CONFIG_SUBSET}"
  echo "Final DiD input:          ${FINAL_DID_INPUT}"
  echo "Python script:            ${PY_SCRIPT}"
  echo "Output dir:               ${OUTPUT_DIR}"
  echo "Top N:                    ${TOP_N}"
  echo "Tolerance:                ${TOLERANCE}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"

  python "${PY_SCRIPT}" \
    --commit-diff-long "${COMMIT_DIFF_LONG}" \
    --exact-row-classification "${EXACT_ROW_CLASSIFICATION}" \
    --rule-config-subset "${RULE_CONFIG_SUBSET}" \
    --final-did-input "${FINAL_DID_INPUT}" \
    --output-dir "${OUTPUT_DIR}" \
    --top-n "${TOP_N}" \
    --tolerance "${TOLERANCE}"

  echo ""
  echo "============================================================"
  echo "run-py-2b9 finished with exit code: 0"
  echo "Completed:  $(date)"
  echo "Output dir: ${OUTPUT_DIR}"
  echo "Log file:   ${LOG_FILE}"
  echo "============================================================"
  echo ""
  echo "** Output file check"
  echo "------------------------------------------------------------"

  output_files=(
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_coverage_summary.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_overall_by_cause.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_overall_by_metric.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_final_did_by_cause.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_final_did_by_metric.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_warning_metrics_final_did.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_final_did_by_treatment_post.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_final_did_by_event_time.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_top_repos_final_did.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_negative_outliers_final_did.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_positive_outliers_final_did.csv"
    "${OUTPUT_DIR}/sonarqube_main_difference_drivers_notes.md"
  )

  for output_file in "${output_files[@]}"; do
    if [[ -f "${output_file}" ]]; then
      echo "File: ${output_file}"
      wc -l "${output_file}"
    else
      echo "MISSING: ${output_file}"
    fi
  done

  echo ""
  echo "run-py-2b9 completed successfully."
} 2>&1 | tee "${LOG_FILE}"
