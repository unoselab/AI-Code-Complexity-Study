#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b10: Inspect SonarQube outlier repositories
# ============================================================
#
# Purpose:
#   Inspect actual local Git clones for the largest SonarQube metric
#   differences between the paper data and the new Python pyv2 scan.
#
#   This wrapper does not rerun SonarQube and does not modify the Git
#   working tree. The Python script uses git ls-tree and git show at the
#   recorded commits to collect source-scope and configuration clues.
#
# Inputs:
#   repo_python/sonarqube_compare_paper/<variant>_<suffix>/
#     sonarqube_main_difference_drivers_top_repos_final_did.csv
#     sonarqube_main_difference_drivers_negative_outliers_final_did.csv
#     sonarqube_main_difference_drivers_positive_outliers_final_did.csv
#
# Clone roots:
#   ../treatment-repos
#   ../control-repos
#
# Outputs:
#   repo_python/sonarqube_compare_paper/<variant>_<suffix>/
#     sonarqube_outlier_repo_inspection_selected_rows.csv
#     sonarqube_outlier_repo_git_tree_summary.csv
#     sonarqube_outlier_repo_top_directories.csv
#     sonarqube_outlier_repo_config_presence.csv
#     sonarqube_outlier_repo_config_snippets.md
#     sonarqube_outlier_repo_manual_commands.sh
#     sonarqube_outlier_repo_inspection_notes.md
#
# Usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b10-inspect-sonarqube-outlier-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PY_SCRIPT="${PY_SCRIPT:-compare/py/inspect_sonarqube_outlier_repos.py}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"

TOP_REPOS_FILE="${TOP_REPOS_FILE:-${OUTPUT_DIR}/sonarqube_main_difference_drivers_top_repos_final_did.csv}"
NEGATIVE_OUTLIERS_FILE="${NEGATIVE_OUTLIERS_FILE:-${OUTPUT_DIR}/sonarqube_main_difference_drivers_negative_outliers_final_did.csv}"
POSITIVE_OUTLIERS_FILE="${POSITIVE_OUTLIERS_FILE:-${OUTPUT_DIR}/sonarqube_main_difference_drivers_positive_outliers_final_did.csv}"

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

TOP_N="${TOP_N:-500}"
MAX_REPOS="${MAX_REPOS:-12}"
MAX_CONFIG_CHARS="${MAX_CONFIG_CHARS:-12000}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b10_inspect_sonarqube_outlier_repos_${RUN_TS}.log}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b10: Inspect SonarQube outlier repositories"
  echo "Started:                $(date)"
  echo "Project root:           ${PROJECT_ROOT}"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Scan suffix:            ${SCAN_SUFFIX}"
  echo "Python script:          ${PY_SCRIPT}"
  echo "Output dir:             ${OUTPUT_DIR}"
  echo "Top repos file:         ${TOP_REPOS_FILE}"
  echo "Negative outliers file: ${NEGATIVE_OUTLIERS_FILE}"
  echo "Positive outliers file: ${POSITIVE_OUTLIERS_FILE}"
  echo "Treatment clone root:   ${TREATMENT_CLONE_ROOT}"
  echo "Control clone root:     ${CONTROL_CLONE_ROOT}"
  echo "Top N:                  ${TOP_N}"
  echo "Max repos:              ${MAX_REPOS}"
  echo "Max config chars:       ${MAX_CONFIG_CHARS}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in \
    "${PY_SCRIPT}" \
    "${TOP_REPOS_FILE}" \
    "${NEGATIVE_OUTLIERS_FILE}" \
    "${POSITIVE_OUTLIERS_FILE}"
  do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      exit 1
    fi
  done

  for d in "${TREATMENT_CLONE_ROOT}" "${CONTROL_CLONE_ROOT}"; do
    if [[ ! -d "${d}" ]]; then
      echo "ERROR: required clone directory not found: ${d}"
      exit 1
    fi
  done

  python -m py_compile "${PY_SCRIPT}"

  python "${PY_SCRIPT}" \
    --top-repos-file "${TOP_REPOS_FILE}" \
    --negative-outliers-file "${NEGATIVE_OUTLIERS_FILE}" \
    --positive-outliers-file "${POSITIVE_OUTLIERS_FILE}" \
    --treatment-clone-root "${TREATMENT_CLONE_ROOT}" \
    --control-clone-root "${CONTROL_CLONE_ROOT}" \
    --output-dir "${OUTPUT_DIR}" \
    --top-n "${TOP_N}" \
    --max-repos "${MAX_REPOS}" \
    --max-config-chars "${MAX_CONFIG_CHARS}"

  echo
  echo "============================================================"
  echo "run-py-2b10 finished successfully"
  echo "Completed:  $(date)"
  echo "Output dir: ${OUTPUT_DIR}"
  echo "Log file:   ${LOG_FILE}"
  echo "============================================================"
  echo

  echo "** Output file check"
  echo "------------------------------------------------------------"
  for f in \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_inspection_selected_rows.csv" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_git_tree_summary.csv" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_top_directories.csv" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_config_presence.csv" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_config_snippets.md" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_manual_commands.sh" \
    "${OUTPUT_DIR}/sonarqube_outlier_repo_inspection_notes.md"
  do
    if [[ -f "${f}" ]]; then
      echo "File: ${f}"
      wc -l "${f}"
    else
      echo "MISSING: ${f}"
    fi
  done
} 2>&1 | tee "${LOG_FILE}"
