#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b15: Create a paper-structure panel from Python quality input
# ============================================================
# Goal:
#   Convert the regenerated Python strict quality DiD input into the same
#   column order as the paper's data/panel_event_monthly.csv.
#
# Why this step exists:
#   This is a diagnostic test for original Rmd compatibility. It preserves
#   our regenerated SonarQube metrics, while filling unavailable paper
#   covariates from the frozen paper panel when repo-month keys match.
#
# Inputs:
#   repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv
#     - Our regenerated Python quality DiD input.
#
#   data/panel_event_monthly.csv
#     - Paper frozen panel used as schema and source for unavailable covariates.
#
# Output:
#   repo_python/did_final/panel_event_monthly_modified_structure.csv
#     - Diagnostic paper-schema panel for original Rmd compatibility checks.
#
# Important:
#   This output is not a full reproduction dataset. It mixes regenerated
#   SonarQube metrics with selected frozen paper covariates.
# 
# Usage:
#   bash compare/run-py-2b15-create-paper-structure-panel.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PY_SCRIPT="${PY_SCRIPT:-compare/py/create_paper_structure_panel_from_python_quality.py}"
INPUT_FILE="${INPUT_FILE:-repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv}"
PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-data/panel_event_monthly.csv}"
OUTPUT_FILE="${OUTPUT_FILE:-repo_python/did_final/panel_event_monthly_modified_structure.csv}"

FILL_FROM_PAPER_COLUMNS="${FILL_FROM_PAPER_COLUMNS:-stars,issues,issue_comments,age,num_dependencies_total,num_vulnerable_dependencies,average_technical_lag,other_agents,high_confidence}"
METRIC_COMPARE_COLUMNS="${METRIC_COMPARE_COLUMNS:-ncloc,bugs,vulnerabilities,code_smells,duplicated_lines_density,comment_lines_density,cognitive_complexity,technical_debt}"
TOP_PRINT="${TOP_PRINT:-20}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b15_create_paper_structure_panel_${RUN_TS}.log}"

mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_FILE}")"

{
  echo "============================================================"
  echo "run-py-2b15: Create paper-structure panel"
  echo "Started:                   $(date)"
  echo "Project root:              ${PROJECT_ROOT}"
  echo "Python script:             ${PY_SCRIPT}"
  echo "Input file:                ${INPUT_FILE}"
  echo "Paper panel file:          ${PAPER_PANEL_FILE}"
  echo "Output file:               ${OUTPUT_FILE}"
  echo "Fill from paper columns:   ${FILL_FROM_PAPER_COLUMNS}"
  echo "Metric compare columns:    ${METRIC_COMPARE_COLUMNS}"
  echo "Top print:                 ${TOP_PRINT}"
  echo "Log file:                  ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "ERROR: Input file not found: ${INPUT_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PAPER_PANEL_FILE}" ]]; then
  echo "ERROR: Paper panel file not found: ${PAPER_PANEL_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

python -m py_compile "${PY_SCRIPT}"

python "${PY_SCRIPT}" \
  --input-file "${INPUT_FILE}" \
  --paper-panel-file "${PAPER_PANEL_FILE}" \
  --output-file "${OUTPUT_FILE}" \
  --fill-from-paper-columns "${FILL_FROM_PAPER_COLUMNS}" \
  --metric-compare-columns "${METRIC_COMPARE_COLUMNS}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

BASE="${OUTPUT_FILE%.csv}"

for expected_file in \
  "${OUTPUT_FILE}" \
  "${BASE}_column_sources.csv" \
  "${BASE}_key_match_summary.csv" \
  "${BASE}_metric_comparison.csv" \
  "${BASE}_notes.md"; do
  if [[ -f "${expected_file}" ]]; then
    echo "OK: ${expected_file}" | tee -a "${LOG_FILE}"
  else
    echo "ERROR: missing expected output ${expected_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "Preview: output header" | tee -a "${LOG_FILE}"
head -1 "${OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo "Preview: key match summary" | tee -a "${LOG_FILE}"
cat "${BASE}_key_match_summary.csv" | tee -a "${LOG_FILE}"

echo "Finished: $(date)" | tee -a "${LOG_FILE}"
