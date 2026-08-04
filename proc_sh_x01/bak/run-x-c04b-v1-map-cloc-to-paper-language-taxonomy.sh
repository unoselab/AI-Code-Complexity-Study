#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="v1"
RUN_NAME="run-x-c04b-${SCRIPT_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/map_whole_repo_cloc_to_paper_language_taxonomy-v1.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-c04b}"
TMP_DIR="${TMP_DIR:-repo_x01/tmp/run-x-c04b}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_NAME}-map-cloc-to-paper-language-taxonomy-${RUN_TS}.log}"

CLOC_LANGUAGE_RESULTS="${CLOC_LANGUAGE_RESULTS:-repo_x01/run-x-c04/python_primary_whole_repo_cloc_language_results.csv}"
PAPER_LANGUAGE_TYPES="${PAPER_LANGUAGE_TYPES:-repo_x01/run-x-c04a/paper_repo_language_types.csv}"
PAPER_PRIMARY_LANGUAGE_TYPES="${PAPER_PRIMARY_LANGUAGE_TYPES:-repo_x01/run-x-c04a/paper_primary_language_types.csv}"

MAPPING_OUTPUT="${MAPPING_OUTPUT:-${OUTPUT_DIR}/python_primary_cloc_to_paper_language_taxonomy_mapping.csv}"
MAPPED_LANGUAGE_RESULTS_OUTPUT="${MAPPED_LANGUAGE_RESULTS_OUTPUT:-${OUTPUT_DIR}/python_primary_whole_repo_cloc_language_results_paper_mapped.csv}"
PAPER_LANGUAGE_AGGREGATE_OUTPUT="${PAPER_LANGUAGE_AGGREGATE_OUTPUT:-${OUTPUT_DIR}/python_primary_whole_repo_cloc_paper_language_aggregate.csv}"
NEEDS_REVIEW_OUTPUT="${NEEDS_REVIEW_OUTPUT:-${OUTPUT_DIR}/python_primary_cloc_language_mapping_needs_review.csv}"
QC_OUTPUT="${QC_OUTPUT:-${OUTPUT_DIR}/python_primary_c04b_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_DIR}/python_primary_c04b_mapping_summary.csv}"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}" "${LOG_DIR}"

{
  echo "============================================================"
  echo "run-x-c04b-v1: map cloc language labels to paper taxonomy"
  echo "Started:                         $(date)"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
  echo "Python script:                   ${PY_SCRIPT}"
  echo "C04 cloc language results:       ${CLOC_LANGUAGE_RESULTS}"
  echo "C04a paper language types:       ${PAPER_LANGUAGE_TYPES}"
  echo "C04a primary language types:     ${PAPER_PRIMARY_LANGUAGE_TYPES}"
  echo "Mapping output:                  ${MAPPING_OUTPUT}"
  echo "Mapped language results:         ${MAPPED_LANGUAGE_RESULTS_OUTPUT}"
  echo "Paper-language aggregate:        ${PAPER_LANGUAGE_AGGREGATE_OUTPUT}"
  echo "Needs-review output:             ${NEEDS_REVIEW_OUTPUT}"
  echo "QC:                              ${QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
  echo

  for required_file in \
    "${PY_SCRIPT}" \
    "${CLOC_LANGUAGE_RESULTS}" \
    "${PAPER_LANGUAGE_TYPES}" \
    "${PAPER_PRIMARY_LANGUAGE_TYPES}"
  do
    if [[ ! -s "${required_file}" ]]; then
      echo "ERROR: required file missing or empty: ${required_file}"
      exit 1
    fi
  done

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --cloc-language-results "${CLOC_LANGUAGE_RESULTS}" \
    --paper-language-types "${PAPER_LANGUAGE_TYPES}" \
    --paper-primary-language-types "${PAPER_PRIMARY_LANGUAGE_TYPES}" \
    --mapping-output "${MAPPING_OUTPUT}" \
    --mapped-language-results-output "${MAPPED_LANGUAGE_RESULTS_OUTPUT}" \
    --paper-language-aggregate-output "${PAPER_LANGUAGE_AGGREGATE_OUTPUT}" \
    --needs-review-output "${NEEDS_REVIEW_OUTPUT}" \
    --qc-output "${QC_OUTPUT}" \
    --summary-output "${SUMMARY_OUTPUT}"

  for expected_file in \
    "${MAPPING_OUTPUT}" \
    "${MAPPED_LANGUAGE_RESULTS_OUTPUT}" \
    "${PAPER_LANGUAGE_AGGREGATE_OUTPUT}" \
    "${NEEDS_REVIEW_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  do
    if [[ ! -f "${expected_file}" ]]; then
      echo "ERROR: expected output not created: ${expected_file}"
      exit 1
    fi
  done

  echo
  echo "============================================================"
  echo "run-x-c04b-v1 completed."
  echo "Completed:                       $(date)"
  echo "Mapping output:                  ${MAPPING_OUTPUT}"
  echo "Mapped language results:         ${MAPPED_LANGUAGE_RESULTS_OUTPUT}"
  echo "Paper-language aggregate:        ${PAPER_LANGUAGE_AGGREGATE_OUTPUT}"
  echo "Needs-review output:             ${NEEDS_REVIEW_OUTPUT}"
  echo "QC:                              ${QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       inspect needs-review labels before C05 panel construction"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
