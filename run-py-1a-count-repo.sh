#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1a: Count Python Cursor-adopting treatment repositories
# ============================================================
#
# Goal:
#   Prepare the first Python treatment-repository input file for
#   reproducing the paper's language-specific Appendix result.
#
# Main output policy:
#   repo_python/
#     - Keep only the analysis input needed by later pipeline steps.
#
# Extra output policy:
#   repo_python/tmp/
#     - Keep diagnostic subsets, logs, and verification artifacts.
#
# Main output:
#   repo_python/treatment_python_repos.csv
#
# Extra outputs:
#   repo_python/tmp/treatment_python_repos_bw6.csv
#   repo_python/tmp/run-py-1a_count_repo_<timestamp>.log
#
# Important:
#   This step reads the frozen baseline data and does not require Git cloning
#   or SonarQube scanning. Expensive cached artifacts under bak/repo_python
#   are not needed for run-py-1a and will be reused by later wrappers.
#
# Typical usage:
#   bash run-py-1a-count-repo.sh
#
# Optional overrides:
#   MIN_BALANCED_WINDOW=5 bash run-py-1a-count-repo.sh
#   OUTPUT_DIR=repo_python_test bash run-py-1a-count-repo.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"

# ------------------------------------------------------------
# Inputs and executable
# ------------------------------------------------------------
DATA_DIR="${DATA_DIR:-data_baseline_backup}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/count_repo_lang.py}"
PYTHON_BIN="${PYTHON_BIN:-python}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
GROUP_NAME="${GROUP_NAME:-Python}"
LANGUAGE="${LANGUAGE:-Python}"

# ------------------------------------------------------------
# Output directories
# ------------------------------------------------------------
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp}"

MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"
TOP_PRINT="${TOP_PRINT:-30}"

# Keep the main pipeline input in repo_python/.
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Keep the balanced-window diagnostic subset in repo_python/tmp/.
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-${TMP_DIR}/treatment_python_repos_bw${MIN_BALANCED_WINDOW}.csv}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1a_count_repo_${RUN_TS}.log}"

PANEL_FILE="${PANEL_FILE:-${DATA_DIR}/panel_event_monthly.csv}"
REPOS_FILE="${REPOS_FILE:-${DATA_DIR}/repos.csv}"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}"

# Remove stale files so a failed run cannot be mistaken for a fresh result.
rm -f "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"

{
  echo "============================================================"
  echo "run-py-1a: Count Python Cursor-adopting treatment repositories"
  echo "Started:                    $(date)"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Baseline panel:             ${PANEL_FILE}"
  echo "Repository metadata:        ${REPOS_FILE}"
  echo "Dataset source:             ${DATASET_SOURCE}"
  echo "Language:                   ${LANGUAGE}"
  echo "Group name:                 ${GROUP_NAME}"
  echo "Main output directory:      ${OUTPUT_DIR}"
  echo "Extra output directory:     ${TMP_DIR}"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Balanced-window diagnostic: ${WINDOW_OUTPUT_FILE}"
  echo "Minimum balanced window:    ${MIN_BALANCED_WINDOW}"
  echo "Top print:                  ${TOP_PRINT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${PANEL_FILE}" ]]; then
    echo "ERROR: Baseline panel not found: ${PANEL_FILE}"
    exit 1
  fi

  if [[ ! -f "${REPOS_FILE}" ]]; then
    echo "ERROR: Repository metadata not found: ${REPOS_FILE}"
    exit 1
  fi

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --data-dir "${DATA_DIR}" \
    --panel-file "${PANEL_FILE}" \
    --repos-file "${REPOS_FILE}" \
    --dataset-source "${DATASET_SOURCE}" \
    --language "${LANGUAGE}" \
    --group-name "${GROUP_NAME}" \
    --output-file "${OUTPUT_FILE}" \
    --window-output-file "${WINDOW_OUTPUT_FILE}" \
    --min-balanced-window "${MIN_BALANCED_WINDOW}" \
    --top-print "${TOP_PRINT}"

  for expected_file in "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}"
      exit 1
    fi
  done

  MAIN_ROWS=$(( $(wc -l < "${OUTPUT_FILE}") - 1 ))
  WINDOW_ROWS=$(( $(wc -l < "${WINDOW_OUTPUT_FILE}") - 1 ))

  echo
  echo "============================================================"
  echo "run-py-1a output verification"
  echo "============================================================"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Main repository rows:       ${MAIN_ROWS}"
  echo "Diagnostic output:          ${WINDOW_OUTPUT_FILE}"
  echo "Diagnostic repository rows: ${WINDOW_ROWS}"
  echo
  echo "Main output preview:"
  head "${OUTPUT_FILE}"
  echo
  echo "Diagnostic output preview:"
  head "${WINDOW_OUTPUT_FILE}"
  echo
  echo "============================================================"
  echo "run-py-1a completed successfully."
  echo "Completed:                  $(date)"
  echo "Main pipeline input:        ${OUTPUT_FILE}"
  echo "Extra diagnostic output:    ${WINDOW_OUTPUT_FILE}"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
# 
# This wrapper is the Python version of run7a-count-repo.sh.
# It reuses the original selection logic without calling the old wrapper.
