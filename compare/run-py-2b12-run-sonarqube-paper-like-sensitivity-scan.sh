#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b12: run paper-like SonarQube sensitivity scan
# ============================================================
# Purpose:
#   Test whether paper-like SonarScanner flags can reproduce or move our
#   pyv2 SonarQube metrics closer to the paper metrics for the highest-impact
#   outlier repo-month-commit rows.
#
# This wrapper reuses the logic of the original scripts/run_sonarqube.py and
# the current proc_scripts/run_sonarqube_v2.py, but it does not call any
# existing shell wrapper.
#
# Required inputs:
#   repo_python/sonarqube_compare_paper/<variant_suffix>/sonarqube_outlier_root_cause_evidence_table.csv
#     - Created by run-py-2b11.
#     - Used to select highest-impact repositories and root-cause labels.
#
#   repo_python/sonarqube_compare_paper/<variant_suffix>/sonarqube_commit_hash_comparison.csv
#     - Created by run-py-2b5.
#     - Used to select exact/prefix commit-match repo-month rows and paper metrics.
#
# Local clone inputs:
#   ../treatment-repos
#   ../control-repos
#
# Main output files:
#   sonarqube_paper_like_sensitivity_targets.csv
#   sonarqube_paper_like_sensitivity_plan.csv
#   sonarqube_paper_like_sensitivity_results.csv
#   sonarqube_paper_like_sensitivity_metric_differences.csv
#   sonarqube_paper_like_sensitivity_by_variant_metric.csv
#   sonarqube_paper_like_sensitivity_failures.csv
#   sonarqube_paper_like_sensitivity_notes.md
#
# Typical smoke test:
#   DRY_RUN=true MAX_REPOS=3 MAX_ROWS_PER_REPO=1 \
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 \
#   bash compare/run-py-2b12-run-sonarqube-paper-like-sensitivity-scan.sh
#
# Actual small scan:
#   MAX_REPOS=3 MAX_ROWS_PER_REPO=1 \
#   VARIANTS=paper_like,scope_exclude_common \
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 \
#   bash compare/run-py-2b12-run-sonarqube-paper-like-sensitivity-scan.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b12_run_sonarqube_paper_like_sensitivity_scan_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"

EVIDENCE_FILE="${EVIDENCE_FILE:-${OUTPUT_DIR}/sonarqube_outlier_root_cause_evidence_table.csv}"
COMPARISON_FILE="${COMPARISON_FILE:-${OUTPUT_DIR}/sonarqube_commit_hash_comparison.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/run_sonarqube_paper_like_sensitivity_scan.py}"

TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-py2b12_}"
MAX_REPOS="${MAX_REPOS:-5}"
MAX_ROWS_PER_REPO="${MAX_ROWS_PER_REPO:-1}"
TOP_PRINT="${TOP_PRINT:-30}"
VARIANTS="${VARIANTS:-paper_like,scope_exclude_common}"
COMMIT_STATUSES="${COMMIT_STATUSES:-exact_match,prefix_match}"
RANK_METRICS="${RANK_METRICS:-static_analysis_warnings,code_smells,technical_debt,ncloc}"
DRY_RUN="${DRY_RUN:-false}"
RESCAN_EXISTING="${RESCAN_EXISTING:-false}"
METRIC_RETRY_ATTEMPTS="${METRIC_RETRY_ATTEMPTS:-5}"
METRIC_RETRY_SLEEP="${METRIC_RETRY_SLEEP:-20}"
SONAR_TIMEOUT="${SONAR_TIMEOUT:-1800}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b12: Run SonarQube paper-like sensitivity scan"
  echo "Started:                   $(date)"
  echo "Project root:              ${PROJECT_ROOT}"
  echo "Panel variant:             ${PANEL_VARIANT}"
  echo "Scan suffix:               ${SCAN_SUFFIX}"
  echo "Python script:             ${PY_SCRIPT}"
  echo "Output dir:                ${OUTPUT_DIR}"
  echo "Evidence file:             ${EVIDENCE_FILE}"
  echo "Comparison file:           ${COMPARISON_FILE}"
  echo "Treatment clone dir:       ${TREATMENT_CLONE_DIR}"
  echo "Control clone dir:         ${CONTROL_CLONE_DIR}"
  echo "Project key prefix:        ${PROJECT_KEY_PREFIX}"
  echo "Max repos:                 ${MAX_REPOS}"
  echo "Max rows per repo:         ${MAX_ROWS_PER_REPO}"
  echo "Variants:                  ${VARIANTS}"
  echo "Commit statuses:           ${COMMIT_STATUSES}"
  echo "Rank metrics:              ${RANK_METRICS}"
  echo "Dry run:                   ${DRY_RUN}"
  echo "Rescan existing:           ${RESCAN_EXISTING}"
  echo "Metric retry attempts:     ${METRIC_RETRY_ATTEMPTS}"
  echo "Metric retry sleep:        ${METRIC_RETRY_SLEEP}"
  echo "Sonar timeout:             ${SONAR_TIMEOUT}"
  echo "Log file:                  ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${EVIDENCE_FILE}" ]]; then
  echo "ERROR: evidence file not found: ${EVIDENCE_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-2b11 first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${COMPARISON_FILE}" ]]; then
  echo "ERROR: comparison file not found: ${COMPARISON_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-2b5 first." | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Syntax check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}"
echo "Python syntax check: OK" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

args=(
  --evidence-file "${EVIDENCE_FILE}"
  --comparison-file "${COMPARISON_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
  --control-clone-dir "${CONTROL_CLONE_DIR}"
  --project-key-prefix "${PROJECT_KEY_PREFIX}"
  --max-repos "${MAX_REPOS}"
  --max-rows-per-repo "${MAX_ROWS_PER_REPO}"
  --top-print "${TOP_PRINT}"
  --variants "${VARIANTS}"
  --commit-statuses "${COMMIT_STATUSES}"
  --rank-metrics "${RANK_METRICS}"
  --metric-retry-attempts "${METRIC_RETRY_ATTEMPTS}"
  --metric-retry-sleep "${METRIC_RETRY_SLEEP}"
  --sonar-timeout "${SONAR_TIMEOUT}"
)

if [[ "${DRY_RUN}" == "true" ]]; then
  args+=(--dry-run)
fi

if [[ "${RESCAN_EXISTING}" == "true" ]]; then
  args+=(--rescan-existing)
fi

echo "** Run paper-like sensitivity scan" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
set +e
python "${PY_SCRIPT}" "${args[@]}" 2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "ERROR: 2b12 sensitivity scan failed with exit code ${run_status}" | tee -a "${LOG_FILE}"
  echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_targets.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_plan.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_results.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_metric_differences.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_by_variant_metric.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_failures.csv" \
  "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_notes.md"; do
  echo "File: ${f}" | tee -a "${LOG_FILE}"
  if [[ -f "${f}" ]]; then
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo | tee -a "${LOG_FILE}"
echo "** Quick preview" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "Command: head -n 20 ${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_by_variant_metric.csv" | tee -a "${LOG_FILE}"
head -n 20 "${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_by_variant_metric.csv" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b12 finished successfully" | tee -a "${LOG_FILE}"
echo "Completed:  $(date)" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:   ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
