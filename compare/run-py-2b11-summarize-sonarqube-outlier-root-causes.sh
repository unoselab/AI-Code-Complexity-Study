#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b11: Summarize SonarQube outlier root causes
# ============================================================
# Purpose:
#   Create repo-level root cause tables for the largest differences between
#   the paper SonarQube data and the new Python pyv2 SonarQube scan.
#
# Inputs:
#   1. Top final-DiD difference drivers from run-py-2b9.
#   2. Git tree inspection summary from run-py-2b10.
#   3. Top directory summary from run-py-2b10.
#   4. Config-file presence summary from run-py-2b10.
#   5. Optional original and pyv2 SonarQube scanner scripts.
#
# Outputs:
#   sonarqube_outlier_root_cause_by_repo.csv
#   sonarqube_outlier_root_cause_by_metric.csv
#   sonarqube_outlier_root_cause_evidence_table.csv
#   sonarqube_outlier_root_cause_notes.md
#
# This wrapper follows the Python experiment naming convention:
#   - shell wrapper uses hyphens
#   - Python script uses underscores
#
# This wrapper does not call older shell scripts. It only reuses the existing
# project file layout and the new Python diagnostic script.
# 
# Usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash compare/run-py-2b11-summarize-sonarqube-outlier-root-causes.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b11_summarize_sonarqube_outlier_root_causes_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-compare/py/summarize_sonarqube_outlier_root_causes.py}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"

TOP_REPOS_FILE="${TOP_REPOS_FILE:-${OUTPUT_DIR}/sonarqube_main_difference_drivers_top_repos_final_did.csv}"
GIT_TREE_SUMMARY_FILE="${GIT_TREE_SUMMARY_FILE:-${OUTPUT_DIR}/sonarqube_outlier_repo_git_tree_summary.csv}"
TOP_DIRECTORIES_FILE="${TOP_DIRECTORIES_FILE:-${OUTPUT_DIR}/sonarqube_outlier_repo_top_directories.csv}"
CONFIG_PRESENCE_FILE="${CONFIG_PRESENCE_FILE:-${OUTPUT_DIR}/sonarqube_outlier_repo_config_presence.csv}"

ORIGINAL_SONAR_SCRIPT="${ORIGINAL_SONAR_SCRIPT:-scripts/run_sonarqube.py}"
PYV2_SONAR_SCRIPT="${PYV2_SONAR_SCRIPT:-proc_scripts/run_sonarqube_v2.py}"

TOP_DIRS_PER_REPO="${TOP_DIRS_PER_REPO:-8}"
TOP_PRINT="${TOP_PRINT:-30}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b11: Summarize SonarQube outlier root causes"
  echo "Started:                   $(date)"
  echo "Project root:              ${PROJECT_ROOT}"
  echo "Panel variant:             ${PANEL_VARIANT}"
  echo "Scan suffix:               ${SCAN_SUFFIX}"
  echo "Python script:             ${PY_SCRIPT}"
  echo "Output dir:                ${OUTPUT_DIR}"
  echo "Top repos file:            ${TOP_REPOS_FILE}"
  echo "Git tree summary file:     ${GIT_TREE_SUMMARY_FILE}"
  echo "Top directories file:      ${TOP_DIRECTORIES_FILE}"
  echo "Config presence file:      ${CONFIG_PRESENCE_FILE}"
  echo "Original Sonar script:     ${ORIGINAL_SONAR_SCRIPT}"
  echo "pyv2 Sonar script:         ${PYV2_SONAR_SCRIPT}"
  echo "Top dirs per repo:         ${TOP_DIRS_PER_REPO}"
  echo "Top print:                 ${TOP_PRINT}"
  echo "Log file:                  ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  for required_file in \
    "${TOP_REPOS_FILE}" \
    "${GIT_TREE_SUMMARY_FILE}" \
    "${TOP_DIRECTORIES_FILE}" \
    "${CONFIG_PRESENCE_FILE}"
  do
    if [[ ! -f "${required_file}" ]]; then
      echo "ERROR: required input file not found: ${required_file}"
      exit 1
    fi
  done

  if [[ ! -f "${ORIGINAL_SONAR_SCRIPT}" ]]; then
    echo "WARNING: original SonarQube script not found: ${ORIGINAL_SONAR_SCRIPT}"
    echo "The summary will continue, but scanner-config comparison will be incomplete."
  fi

  if [[ ! -f "${PYV2_SONAR_SCRIPT}" ]]; then
    echo "WARNING: pyv2 SonarQube script not found: ${PYV2_SONAR_SCRIPT}"
    echo "The summary will continue, but scanner-config comparison will be incomplete."
  fi

  echo "** Syntax check"
  echo "------------------------------------------------------------"
  python -m py_compile "${PY_SCRIPT}"
  echo "Python syntax check: OK"
  echo

  echo "** Build root cause report"
  echo "------------------------------------------------------------"
  python "${PY_SCRIPT}" \
    --top-repos-file "${TOP_REPOS_FILE}" \
    --git-tree-summary-file "${GIT_TREE_SUMMARY_FILE}" \
    --top-directories-file "${TOP_DIRECTORIES_FILE}" \
    --config-presence-file "${CONFIG_PRESENCE_FILE}" \
    --output-dir "${OUTPUT_DIR}" \
    --original-sonarqube-script "${ORIGINAL_SONAR_SCRIPT}" \
    --pyv2-sonarqube-script "${PYV2_SONAR_SCRIPT}" \
    --top-dirs-per-repo "${TOP_DIRS_PER_REPO}" \
    --top-print "${TOP_PRINT}"

  echo
  echo "** Output file check"
  echo "------------------------------------------------------------"

  OUTPUT_FILES=(
    "${OUTPUT_DIR}/sonarqube_outlier_root_cause_by_repo.csv"
    "${OUTPUT_DIR}/sonarqube_outlier_root_cause_by_metric.csv"
    "${OUTPUT_DIR}/sonarqube_outlier_root_cause_evidence_table.csv"
    "${OUTPUT_DIR}/sonarqube_outlier_root_cause_notes.md"
  )

  for output_file in "${OUTPUT_FILES[@]}"; do
    if [[ ! -f "${output_file}" ]]; then
      echo "ERROR: expected output file not found: ${output_file}"
      exit 1
    fi
    echo "File: ${output_file}"
    wc -l "${output_file}"
  done

  echo
  echo "** Quick preview"
  echo "------------------------------------------------------------"
  echo "Command: head -n 20 ${OUTPUT_DIR}/sonarqube_outlier_root_cause_evidence_table.csv"
  head -n 20 "${OUTPUT_DIR}/sonarqube_outlier_root_cause_evidence_table.csv"

  echo
  echo "============================================================"
  echo "run-py-2b11 finished successfully"
  echo "Completed:  $(date)"
  echo "Output dir: ${OUTPUT_DIR}"
  echo "Log file:   ${LOG_FILE}"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
