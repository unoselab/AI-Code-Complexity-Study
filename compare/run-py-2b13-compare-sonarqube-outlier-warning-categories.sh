#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b13: Compare SonarQube warning categories for outliers
# ============================================================
# Goal:
#   Compare paper issue-level SonarQube warnings with the issue-level warnings
#   collected from the run-py-2b12 targeted sensitivity scan.
#
# Why this step exists:
#   run-py-2b12 showed that a paper-like scanner flag set did not move the
#   top outlier metrics close to the paper values. Therefore, this step checks
#   whether the remaining difference is driven by quality profile, active rules,
#   analyzer/plugin version, or source-scope/path differences.
#
# Required inputs:
#   data_baseline_backup/sonarqube_warnings.csv
#     - Paper frozen issue-level warning rows.
#
#   data_baseline_backup/sonarqube_warning_definitions.csv
#     - Paper warning rule metadata: type, severity, effort, category.
#
#   repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_paper_like_sensitivity_targets.csv
#   repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_paper_like_sensitivity_plan.csv
#   repo_python/sonarqube_compare_paper/<panel>_<suffix>/sonarqube_paper_like_sensitivity_results.csv
#     - Outputs from run-py-2b12.
#
#   SONAR_HOST and SONAR_TOKEN
#     - Used to fetch issue-level rows for the 2b12 sensitivity-scan projects.
#
# Outputs:
#   sonarqube_outlier_warning_type_severity_comparison.csv
#   sonarqube_outlier_warning_category_comparison.csv
#   sonarqube_outlier_warning_rule_comparison.csv
#   sonarqube_outlier_warning_component_path_comparison.csv
#   sonarqube_outlier_warning_missing_paper_rules.csv
#   sonarqube_outlier_warning_extra_our_rules.csv
#   sonarqube_outlier_warning_category_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 VARIANT=paper_like bash compare/run-py-2b13-compare-sonarqube-outlier-warning-categories.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
# ------------------------------------------------------------
# Load local environment variables before shell-level checks.
# ------------------------------------------------------------
# The Python scripts can read .env by themselves, but this wrapper
# checks SONAR_HOST and SONAR_TOKEN before launching Python.
# Therefore, load .env here as well.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"
VARIANT="${VARIANT:-paper_like}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/compare_sonarqube_outlier_warning_categories.py}"

PAPER_WARNINGS_FILE="${PAPER_WARNINGS_FILE:-data_baseline_backup/sonarqube_warnings.csv}"
PAPER_DEFINITIONS_FILE="${PAPER_DEFINITIONS_FILE:-data_baseline_backup/sonarqube_warning_definitions.csv}"

TARGETS_FILE="${TARGETS_FILE:-${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_targets.csv}"
PLAN_FILE="${PLAN_FILE:-${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_plan.csv}"
RESULTS_FILE="${RESULTS_FILE:-${OUTPUT_DIR}/sonarqube_paper_like_sensitivity_results.csv}"

MAX_ISSUES_PER_PROJECT="${MAX_ISSUES_PER_PROJECT:-0}"
PAGE_SIZE="${PAGE_SIZE:-500}"
API_SLEEP="${API_SLEEP:-0}"
TOP_PRINT="${TOP_PRINT:-30}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b13_compare_sonarqube_outlier_warning_categories_${RUN_TS}.log}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-2b13: Compare SonarQube outlier warning categories" | tee -a "${LOG_FILE}"
echo "Started:                   $(date)" | tee -a "${LOG_FILE}"
echo "Project root:              ${PROJECT_ROOT}" | tee -a "${LOG_FILE}"
echo "Panel variant:             ${PANEL_VARIANT}" | tee -a "${LOG_FILE}"
echo "Scan suffix:               ${SCAN_SUFFIX}" | tee -a "${LOG_FILE}"
echo "Variant:                   ${VARIANT}" | tee -a "${LOG_FILE}"
echo "Python script:             ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Output dir:                ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Paper warnings file:       ${PAPER_WARNINGS_FILE}" | tee -a "${LOG_FILE}"
echo "Paper definitions file:    ${PAPER_DEFINITIONS_FILE}" | tee -a "${LOG_FILE}"
echo "Targets file:              ${TARGETS_FILE}" | tee -a "${LOG_FILE}"
echo "Plan file:                 ${PLAN_FILE}" | tee -a "${LOG_FILE}"
echo "Results file:              ${RESULTS_FILE}" | tee -a "${LOG_FILE}"
echo "Max issues per project:    ${MAX_ISSUES_PER_PROJECT}" | tee -a "${LOG_FILE}"
echo "Page size:                 ${PAGE_SIZE}" | tee -a "${LOG_FILE}"
echo "API sleep:                 ${API_SLEEP}" | tee -a "${LOG_FILE}"
echo "Top print:                 ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "Log file:                  ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

for f in \
  "${PAPER_WARNINGS_FILE}" \
  "${PAPER_DEFINITIONS_FILE}" \
  "${TARGETS_FILE}" \
  "${PLAN_FILE}" \
  "${RESULTS_FILE}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required input file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

if [[ -z "${SONAR_HOST:-}" ]]; then
  echo "ERROR: SONAR_HOST is not set." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ -z "${SONAR_TOKEN:-}" ]]; then
  echo "ERROR: SONAR_TOKEN is not set." | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Syntax check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}"
echo "Python syntax check: OK" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

echo "** Compare warning categories and rules" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python "${PY_SCRIPT}" \
  --paper-warnings-file "${PAPER_WARNINGS_FILE}" \
  --paper-definitions-file "${PAPER_DEFINITIONS_FILE}" \
  --targets-file "${TARGETS_FILE}" \
  --plan-file "${PLAN_FILE}" \
  --results-file "${RESULTS_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --variant "${VARIANT}" \
  --max-issues-per-project "${MAX_ISSUES_PER_PROJECT}" \
  --page-size "${PAGE_SIZE}" \
  --api-sleep "${API_SLEEP}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

status=${PIPESTATUS[0]}
if [[ "${status}" -ne 0 ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "ERROR: 2b13 Python script failed with exit code ${status}" | tee -a "${LOG_FILE}"
  exit "${status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

OUTPUT_FILES=(
  "${OUTPUT_DIR}/sonarqube_outlier_warning_paper_enriched.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_our_issues_enriched.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_type_severity_comparison.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_category_comparison.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_rule_comparison.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_component_path_comparison.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_missing_paper_rules.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_extra_our_rules.csv"
  "${OUTPUT_DIR}/sonarqube_outlier_warning_category_notes.md"
)

for f in "${OUTPUT_FILES[@]}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: expected output file missing: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
  echo "File: ${f}" | tee -a "${LOG_FILE}"
  wc -l "${f}" | tee -a "${LOG_FILE}"
done

echo | tee -a "${LOG_FILE}"
echo "** Quick preview" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "Command: head -n 20 ${OUTPUT_DIR}/sonarqube_outlier_warning_missing_paper_rules.csv" | tee -a "${LOG_FILE}"
head -n 20 "${OUTPUT_DIR}/sonarqube_outlier_warning_missing_paper_rules.csv" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-2b13 finished successfully" | tee -a "${LOG_FILE}"
echo "Completed:  $(date)" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:   ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
