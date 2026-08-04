#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c04b v1: Map C04 cloc labels to the paper taxonomy
# ============================================================
#
# Purpose:
#   Map the 76 cloc language labels observed in the completed C04 historical
#   snapshots to the 252 repository language labels observed in the paper's
#   replication metadata. The repo_languages numeric byte values are not used.
#
# Inputs:
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_language_results.csv
#     Language-level cloc rows from 1,828 completed historical snapshots.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_snapshot_results.csv
#     Snapshot-level C04 results, including five valid zero-NCLOC snapshots.
#
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_repo_month_results.csv
#     C04 results mapped to all 2,411 repository-month observations.
#
#   repo_x01/run-x-c04a/paper_repo_language_types.csv
#     The 252 unique labels observed in repos.csv:repo_languages.
#
# Outputs:
#   repo_x01/run-x-c04b/cloc_to_paper_language_taxonomy_mapping.csv
#     One auditable decision row for every observed cloc language label.
#
#   repo_x01/run-x-c04b/python_primary_whole_repo_cloc_language_results_paper_taxonomy.csv
#     All original language rows with mapping and inclusion fields appended.
#
#   repo_x01/run-x-c04b/python_primary_whole_repo_cloc_snapshot_results_paper_taxonomy.csv
#     Snapshot results with all-recognized, paper-taxonomy, and excluded NCLOC.
#
#   repo_x01/run-x-c04b/python_primary_whole_repo_cloc_repo_month_results_paper_taxonomy.csv
#     DiD-ready repository-month NCLOC columns using the same snapshot mapping.
#
#   repo_x01/run-x-c04b/excluded_cloc_language_summary.csv
#     Unmapped cloc labels ordered by excluded code volume.
#
# This wrapper is independent and does not call another experiment wrapper.

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
C04_DIR="${C04_DIR:-repo_x01/run-x-c04}"
C04A_DIR="${C04A_DIR:-repo_x01/run-x-c04a}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-c04b}"
TMP_DIR="${TMP_DIR:-repo_x01/tmp/run-x-c04b}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

LANGUAGE_RESULTS_FILE="${LANGUAGE_RESULTS_FILE:-${C04_DIR}/python_primary_whole_repo_cloc_language_results.csv}"
SNAPSHOT_RESULTS_FILE="${SNAPSHOT_RESULTS_FILE:-${C04_DIR}/python_primary_whole_repo_cloc_snapshot_results.csv}"
REPO_MONTH_RESULTS_FILE="${REPO_MONTH_RESULTS_FILE:-${C04_DIR}/python_primary_whole_repo_cloc_repo_month_results.csv}"
PAPER_LANGUAGE_TYPES_FILE="${PAPER_LANGUAGE_TYPES_FILE:-${C04A_DIR}/paper_repo_language_types.csv}"

MAPPING_OUTPUT="${OUTPUT_DIR}/cloc_to_paper_language_taxonomy_mapping.csv"
MAPPED_LANGUAGE_RESULTS_OUTPUT="${OUTPUT_DIR}/python_primary_whole_repo_cloc_language_results_paper_taxonomy.csv"
SNAPSHOT_AGGREGATES_OUTPUT="${OUTPUT_DIR}/python_primary_whole_repo_cloc_snapshot_results_paper_taxonomy.csv"
REPO_MONTH_AGGREGATES_OUTPUT="${OUTPUT_DIR}/python_primary_whole_repo_cloc_repo_month_results_paper_taxonomy.csv"
EXCLUDED_LANGUAGE_SUMMARY_OUTPUT="${OUTPUT_DIR}/excluded_cloc_language_summary.csv"
QC_OUTPUT="${OUTPUT_DIR}/paper_taxonomy_mapping_qc.csv"
SUMMARY_OUTPUT="${TMP_DIR}/paper_taxonomy_mapping_summary.csv"
SCRIPT_PATH="proc_script_x01/map_cloc_to_paper_taxonomy.py"

EXPECTED_LANGUAGE_ROWS="${EXPECTED_LANGUAGE_ROWS:-16815}"
EXPECTED_CLOC_LANGUAGE_TYPES="${EXPECTED_CLOC_LANGUAGE_TYPES:-76}"
EXPECTED_PAPER_LANGUAGE_TYPES="${EXPECTED_PAPER_LANGUAGE_TYPES:-252}"
EXPECTED_MAPPED_CLOC_LANGUAGE_TYPES="${EXPECTED_MAPPED_CLOC_LANGUAGE_TYPES:-54}"
EXPECTED_UNMAPPED_CLOC_LANGUAGE_TYPES="${EXPECTED_UNMAPPED_CLOC_LANGUAGE_TYPES:-22}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1828}"
EXPECTED_REPO_MONTH_ROWS="${EXPECTED_REPO_MONTH_ROWS:-2411}"
EXPECTED_ALL_RECOGNIZED_SNAPSHOT_CODE="${EXPECTED_ALL_RECOGNIZED_SNAPSHOT_CODE:-190937444}"
EXPECTED_PAPER_TAXONOMY_SNAPSHOT_CODE="${EXPECTED_PAPER_TAXONOMY_SNAPSHOT_CODE:-117309450}"
EXPECTED_ALL_RECOGNIZED_REPO_MONTH_CODE="${EXPECTED_ALL_RECOGNIZED_REPO_MONTH_CODE:-205349581}"
EXPECTED_PAPER_TAXONOMY_REPO_MONTH_CODE="${EXPECTED_PAPER_TAXONOMY_REPO_MONTH_CODE:-127617394}"
EXPECTED_ZERO_NCLOC_SNAPSHOTS="${EXPECTED_ZERO_NCLOC_SNAPSHOTS:-5}"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}" logs
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/run-x-c04b-v1-map-cloc-to-paper-taxonomy-${TIMESTAMP}.log"

{
  echo "============================================================"
  echo "run-x-c04b-v1: map cloc labels to paper taxonomy"
  printf "%-36s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-36s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-36s %s\n" "Python:" "${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
  printf "%-36s %s\n" "Language results:" "${LANGUAGE_RESULTS_FILE}"
  printf "%-36s %s\n" "Snapshot results:" "${SNAPSHOT_RESULTS_FILE}"
  printf "%-36s %s\n" "Repo-month results:" "${REPO_MONTH_RESULTS_FILE}"
  printf "%-36s %s\n" "Paper taxonomy:" "${PAPER_LANGUAGE_TYPES_FILE}"
  printf "%-36s %s\n" "Expected cloc language types:" "${EXPECTED_CLOC_LANGUAGE_TYPES}"
  printf "%-36s %s\n" "Expected paper language types:" "${EXPECTED_PAPER_LANGUAGE_TYPES}"
  printf "%-36s %s\n" "Expected language rows:" "${EXPECTED_LANGUAGE_ROWS}"
  printf "%-36s %s\n" "Expected snapshots:" "${EXPECTED_SNAPSHOTS}"
  printf "%-36s %s\n" "Expected repo-month rows:" "${EXPECTED_REPO_MONTH_ROWS}"
  printf "%-36s %s\n" "Strict expected counts:" "${STRICT_EXPECTED_COUNTS}"
  printf "%-36s %s\n" "Mapping output:" "${MAPPING_OUTPUT}"
  printf "%-36s %s\n" "Snapshot aggregate output:" "${SNAPSHOT_AGGREGATES_OUTPUT}"
  printf "%-36s %s\n" "Repo-month aggregate output:" "${REPO_MONTH_AGGREGATES_OUTPUT}"
  printf "%-36s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-36s %s\n" "Summary output:" "${SUMMARY_OUTPUT}"
  printf "%-36s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Map cloc labels and compute paper-taxonomy NCLOC"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${PYTHON_BIN}" "${SCRIPT_PATH}" \
  --language-results-file "${LANGUAGE_RESULTS_FILE}" \
  --snapshot-results-file "${SNAPSHOT_RESULTS_FILE}" \
  --repo-month-results-file "${REPO_MONTH_RESULTS_FILE}" \
  --paper-language-types-file "${PAPER_LANGUAGE_TYPES_FILE}" \
  --mapping-output "${MAPPING_OUTPUT}" \
  --mapped-language-results-output "${MAPPED_LANGUAGE_RESULTS_OUTPUT}" \
  --snapshot-aggregates-output "${SNAPSHOT_AGGREGATES_OUTPUT}" \
  --repo-month-aggregates-output "${REPO_MONTH_AGGREGATES_OUTPUT}" \
  --excluded-language-summary-output "${EXCLUDED_LANGUAGE_SUMMARY_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
  --expected-language-rows "${EXPECTED_LANGUAGE_ROWS}" \
  --expected-cloc-language-types "${EXPECTED_CLOC_LANGUAGE_TYPES}" \
  --expected-paper-language-types "${EXPECTED_PAPER_LANGUAGE_TYPES}" \
  --expected-mapped-cloc-language-types "${EXPECTED_MAPPED_CLOC_LANGUAGE_TYPES}" \
  --expected-unmapped-cloc-language-types "${EXPECTED_UNMAPPED_CLOC_LANGUAGE_TYPES}" \
  --expected-snapshots "${EXPECTED_SNAPSHOTS}" \
  --expected-repo-month-rows "${EXPECTED_REPO_MONTH_ROWS}" \
  --expected-all-recognized-snapshot-code "${EXPECTED_ALL_RECOGNIZED_SNAPSHOT_CODE}" \
  --expected-paper-taxonomy-snapshot-code "${EXPECTED_PAPER_TAXONOMY_SNAPSHOT_CODE}" \
  --expected-all-recognized-repo-month-code "${EXPECTED_ALL_RECOGNIZED_REPO_MONTH_CODE}" \
  --expected-paper-taxonomy-repo-month-code "${EXPECTED_PAPER_TAXONOMY_REPO_MONTH_CODE}" \
  --expected-zero-ncloc-snapshots "${EXPECTED_ZERO_NCLOC_SNAPSHOTS}" \
  --log-level "${LOG_LEVEL}" \
  2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: run-x-c04b-v1 failed with status ${run_status}." | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

{
  echo
  echo "============================================================"
  echo "run-x-c04b-v1 completed."
  printf "%-36s %s\n" "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-36s %s\n" "Mapping:" "${MAPPING_OUTPUT}"
  printf "%-36s %s\n" "Mapped language rows:" "${MAPPED_LANGUAGE_RESULTS_OUTPUT}"
  printf "%-36s %s\n" "Snapshot aggregates:" "${SNAPSHOT_AGGREGATES_OUTPUT}"
  printf "%-36s %s\n" "Repo-month aggregates:" "${REPO_MONTH_AGGREGATES_OUTPUT}"
  printf "%-36s %s\n" "Excluded labels:" "${EXCLUDED_LANGUAGE_SUMMARY_OUTPUT}"
  printf "%-36s %s\n" "QC:" "${QC_OUTPUT}"
  printf "%-36s %s\n" "Summary:" "${SUMMARY_OUTPUT}"
  printf "%-36s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: review mapped and excluded labels before using the taxonomy NCLOC in C05 DiD inputs"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
