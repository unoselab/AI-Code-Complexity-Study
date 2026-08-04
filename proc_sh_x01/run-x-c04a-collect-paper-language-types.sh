#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c04a v1: Collect language types recorded in repos.csv
# ============================================================
#
# Purpose:
#   Build the paper-aligned language taxonomy before the C04 full cloc run.
#   The taxonomy is the set of unique labels recorded in repos.csv under
#   repo_languages. The numeric values in that column are GitHub language-byte
#   metadata and are NOT used as NCLOC.
#
# Required input:
#   data_baseline_backup/repos.csv
#     Required columns: repo_name, repo_languages, repo_primary_language.
#
# Main outputs:
#   repo_x01/run-x-c04a/paper_repo_language_types.csv
#     One row per unique label found in repo_languages.
#
#   repo_x01/run-x-c04a/paper_primary_language_types.csv
#     One row per unique repo_primary_language label.
#
#   repo_x01/run-x-c04a/paper_repo_language_membership.csv
#     Repository-to-language membership used to audit the taxonomy.
#
#   repo_x01/run-x-c04a/paper_language_type_qc.csv
#     Structural parsing checks and exact HTML, MDX, and Markdown counts.
#
#   repo_x01/tmp/run-x-c04a/paper_language_type_summary.csv
#     Compact summary used to decide the C04 language allowlist.
#
# This wrapper is independent and does not call another experiment wrapper.

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
REPOS_FILE="${REPOS_FILE:-data_baseline_backup/repos.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-c04a}"
TMP_DIR="${TMP_DIR:-repo_x01/tmp/run-x-c04a}"
STRICT="${STRICT:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

LANGUAGE_TYPES_OUTPUT="${OUTPUT_DIR}/paper_repo_language_types.csv"
PRIMARY_TYPES_OUTPUT="${OUTPUT_DIR}/paper_primary_language_types.csv"
MEMBERSHIP_OUTPUT="${OUTPUT_DIR}/paper_repo_language_membership.csv"
QC_OUTPUT="${OUTPUT_DIR}/paper_language_type_qc.csv"
SUMMARY_OUTPUT="${TMP_DIR}/paper_language_type_summary.csv"
SCRIPT_PATH="proc_script_x01/collect_paper_language_types.py"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}" logs
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/run-x-c04a-v1-collect-paper-language-types-${TIMESTAMP}.log"

{
  echo "============================================================"
  echo "run-x-c04a-v1: collect paper language types"
  printf "%-32s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-32s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-32s %s\n" "Python:" "${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
  printf "%-32s %s\n" "Repository metadata:" "${REPOS_FILE}"
  printf "%-32s %s\n" "Language types output:" "${LANGUAGE_TYPES_OUTPUT}"
  printf "%-32s %s\n" "Primary types output:" "${PRIMARY_TYPES_OUTPUT}"
  printf "%-32s %s\n" "Membership output:" "${MEMBERSHIP_OUTPUT}"
  printf "%-32s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-32s %s\n" "Summary output:" "${SUMMARY_OUTPUT}"
  printf "%-32s %s\n" "Strict parsing:" "${STRICT}"
  printf "%-32s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Extract unique repo_languages labels"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${PYTHON_BIN}" "${SCRIPT_PATH}" \
  --repos-file "${REPOS_FILE}" \
  --language-types-output "${LANGUAGE_TYPES_OUTPUT}" \
  --primary-language-types-output "${PRIMARY_TYPES_OUTPUT}" \
  --membership-output "${MEMBERSHIP_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --strict "${STRICT}" \
  --log-level "${LOG_LEVEL}" \
  2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: run-x-c04a-v1 failed with status ${run_status}." | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

{
  echo
  echo "============================================================"
  echo "run-x-c04a-v1 completed."
  printf "%-32s %s\n" "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-32s %s\n" "Language types:" "${LANGUAGE_TYPES_OUTPUT}"
  printf "%-32s %s\n" "Primary language types:" "${PRIMARY_TYPES_OUTPUT}"
  printf "%-32s %s\n" "QC:" "${QC_OUTPUT}"
  printf "%-32s %s\n" "Summary:" "${SUMMARY_OUTPUT}"
  printf "%-32s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: review exact HTML, MDX, and Markdown labels before C04 full run"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
