#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b17: List modified-panel rows unmatched to the paper panel
# ============================================================
# Goal:
#   Print and save repo-month rows in the 2b15 modified paper-structure
#   panel that cannot be matched to data/panel_event_monthly.csv.
#
# Why this step exists:
#   The 2b15 panel can reuse paper-extra covariates only when the
#   repo_name,time key exists in the frozen paper panel. This script lists
#   the rows that cannot reuse those paper values.
#
# Inputs:
#   repo_python/did_final/panel_event_monthly_modified_structure.csv
#     - Rmd-compatible diagnostic input created by run-py-2b15.
#
#   data/panel_event_monthly.csv
#     - Frozen paper panel used for key matching.
#
# Outputs:
#   repo_python/did_final/panel_event_monthly_modified_structure_unmatched_repo_months.csv
#     - Unmatched repo-month rows with context columns.
#
#   repo_python/did_final/panel_event_monthly_modified_structure_unmatched_summary.csv
#     - Match count and paper-extra missing-value summary.
# 
# Usage:
#   bash compare/run-py-2b17-list-unmatched-paper-panel-repo-months.sh
# 
# cat repo_python/did_final/panel_event_monthly_modified_structure_unmatched_summary.csv
# cat repo_python/did_final/panel_event_monthly_modified_structure_unmatched_repo_months.csv
# 
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PY_SCRIPT="${PY_SCRIPT:-compare/py/list_unmatched_paper_panel_repo_months.py}"
MODIFIED_PANEL_FILE="${MODIFIED_PANEL_FILE:-repo_python/did_final/panel_event_monthly_modified_structure.csv}"
PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-data/panel_event_monthly.csv}"
OUTPUT_FILE="${OUTPUT_FILE:-repo_python/did_final/panel_event_monthly_modified_structure_unmatched_repo_months.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-repo_python/did_final/panel_event_monthly_modified_structure_unmatched_summary.csv}"
TOP_PRINT="${TOP_PRINT:-50}"

PAPER_EXTRA_COLUMNS="${PAPER_EXTRA_COLUMNS:-stars,issues,issue_comments,age,num_dependencies_total,num_vulnerable_dependencies,average_technical_lag,other_agents,high_confidence}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b17_list_unmatched_paper_panel_repo_months_${RUN_TS}.log}"

mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_FILE}")"

{
  echo "============================================================"
  echo "run-py-2b17: List unmatched paper-panel repo-months"
  echo "Started:              $(date)"
  echo "Project root:         ${PROJECT_ROOT}"
  echo "Python script:        ${PY_SCRIPT}"
  echo "Modified panel file:  ${MODIFIED_PANEL_FILE}"
  echo "Paper panel file:     ${PAPER_PANEL_FILE}"
  echo "Output file:          ${OUTPUT_FILE}"
  echo "Summary file:         ${SUMMARY_FILE}"
  echo "Paper-extra columns:  ${PAPER_EXTRA_COLUMNS}"
  echo "Top print:            ${TOP_PRINT}"
  echo "Log file:             ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${MODIFIED_PANEL_FILE}" ]]; then
  echo "ERROR: modified panel file not found: ${MODIFIED_PANEL_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PAPER_PANEL_FILE}" ]]; then
  echo "ERROR: paper panel file not found: ${PAPER_PANEL_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

python -m py_compile "${PY_SCRIPT}"

python "${PY_SCRIPT}" \
  --modified-panel-file "${MODIFIED_PANEL_FILE}" \
  --paper-panel-file "${PAPER_PANEL_FILE}" \
  --output-file "${OUTPUT_FILE}" \
  --summary-file "${SUMMARY_FILE}" \
  --paper-extra-columns "${PAPER_EXTRA_COLUMNS}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

for expected_file in "${OUTPUT_FILE}" "${SUMMARY_FILE}"; do
  if [[ -f "${expected_file}" ]]; then
    echo "OK: ${expected_file}" | tee -a "${LOG_FILE}"
  else
    echo "ERROR: missing expected output ${expected_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "Preview: unmatched rows" | tee -a "${LOG_FILE}"
head -n 20 "${OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo "Preview: summary" | tee -a "${LOG_FILE}"
cat "${SUMMARY_FILE}" | tee -a "${LOG_FILE}"

echo "Finished: $(date)" | tee -a "${LOG_FILE}"
