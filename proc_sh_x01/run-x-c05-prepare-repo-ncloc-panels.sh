#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c05 v1: Prepare paper/local repository-NCLOC DiD panels
# ============================================================
#
# Purpose:
#   Join the C03 Python-primary paper panel to the completed C04b local
#   whole-repository NCLOC measurements and create auditable DiD inputs.
#
# Primary specifications:
#   1. Paper SonarQube NCLOC on the paper complete-case sample.
#   2. Paper SonarQube NCLOC on the exact paper/local common sample.
#   3. Local cloc paper-taxonomy NCLOC on the same exact common sample.
#
# Robustness specification:
#   - Local cloc all-recognized NCLOC on the exact common sample.
#
# Important sample rule:
#   Complete-case panels and Borusyak-estimable panels are written separately.
#   A treated repository is Borusyak-estimable only when the selected sample
#   contains at least one untreated pre-adoption row and at least one treated
#   row. The corresponding control pool is retained unchanged.
#
# Inputs:
#   repo_x01/run-x-c03/python_primary_repo_month_panel.csv
#   repo_x01/run-x-c04b/python_primary_whole_repo_cloc_repo_month_results_paper_taxonomy.csv
#
# This wrapper is self-contained and does not call another experiment wrapper.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-c05"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-repo-ncloc-panels-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_repo_ncloc_panels.py}"

PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-repo_x01/run-x-c03/python_primary_repo_month_panel.csv}"
LOCAL_REPO_MONTH_FILE="${LOCAL_REPO_MONTH_FILE:-repo_x01/run-x-c04b/python_primary_whole_repo_cloc_repo_month_results_paper_taxonomy.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

COMBINED_PANEL_OUTPUT="${COMBINED_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_panel_combined.csv}"
PAPER_FULL_COMPLETE_OUTPUT="${PAPER_FULL_COMPLETE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_paper_ncloc_full_complete_case.csv}"
PAPER_FULL_ESTIMABLE_OUTPUT="${PAPER_FULL_ESTIMABLE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_paper_ncloc_full_borusyak_estimable.csv}"
PAPER_COMMON_COMPLETE_OUTPUT="${PAPER_COMMON_COMPLETE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_paper_ncloc_common_complete_case.csv}"
PAPER_COMMON_ESTIMABLE_OUTPUT="${PAPER_COMMON_ESTIMABLE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_paper_ncloc_common_borusyak_estimable.csv}"
LOCAL_TAXONOMY_COMMON_COMPLETE_OUTPUT="${LOCAL_TAXONOMY_COMMON_COMPLETE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_local_cloc_paper_taxonomy_common_complete_case.csv}"
LOCAL_TAXONOMY_COMMON_ESTIMABLE_OUTPUT="${LOCAL_TAXONOMY_COMMON_ESTIMABLE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_local_cloc_paper_taxonomy_common_borusyak_estimable.csv}"
LOCAL_ALL_COMMON_COMPLETE_OUTPUT="${LOCAL_ALL_COMMON_COMPLETE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_local_cloc_all_recognized_common_complete_case.csv}"
LOCAL_ALL_COMMON_ESTIMABLE_OUTPUT="${LOCAL_ALL_COMMON_ESTIMABLE_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_local_cloc_all_recognized_common_borusyak_estimable.csv}"
BACKEND_COMPARISON_OUTPUT="${BACKEND_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_backend_comparison_common.csv}"
TREATMENT_ESTIMABILITY_OUTPUT="${TREATMENT_ESTIMABILITY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_treatment_estimability_audit.csv}"
LEGACY_TIMING_AUDIT_OUTPUT="${LEGACY_TIMING_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_legacy_timing_audit.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_sample_summary.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_primary_repo_ncloc_panel_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_primary_repo_ncloc_panel_summary.csv}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_PAPER_PANEL_ROWS="${EXPECTED_PAPER_PANEL_ROWS:-2461}"
EXPECTED_TREATMENT_PAPER_ROWS="${EXPECTED_TREATMENT_PAPER_ROWS:-1223}"
EXPECTED_CONTROL_PAPER_ROWS="${EXPECTED_CONTROL_PAPER_ROWS:-1238}"
EXPECTED_PAPER_REPOSITORIES="${EXPECTED_PAPER_REPOSITORIES:-248}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-121}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-127}"
EXPECTED_LOCAL_ROWS="${EXPECTED_LOCAL_ROWS:-2411}"
EXPECTED_LOCAL_REPOSITORIES="${EXPECTED_LOCAL_REPOSITORIES:-242}"
EXPECTED_PAPER_NCLOC_MISSING="${EXPECTED_PAPER_NCLOC_MISSING:-168}"
EXPECTED_PAPER_FULL_COMPLETE_ROWS="${EXPECTED_PAPER_FULL_COMPLETE_ROWS:-2293}"
EXPECTED_COMMON_ROWS="${EXPECTED_COMMON_ROWS:-2250}"
EXPECTED_PAPER_FULL_ESTIMABLE_ROWS="${EXPECTED_PAPER_FULL_ESTIMABLE_ROWS:-2127}"
EXPECTED_COMMON_ESTIMABLE_ROWS="${EXPECTED_COMMON_ESTIMABLE_ROWS:-2090}"
EXPECTED_PAPER_FULL_ESTIMABLE_TREATMENT_REPOSITORIES="${EXPECTED_PAPER_FULL_ESTIMABLE_TREATMENT_REPOSITORIES:-72}"
EXPECTED_COMMON_ESTIMABLE_TREATMENT_REPOSITORIES="${EXPECTED_COMMON_ESTIMABLE_TREATMENT_REPOSITORIES:-69}"
EXPECTED_LEGACY_TIMING_MISMATCH_ROWS="${EXPECTED_LEGACY_TIMING_MISMATCH_ROWS:-19}"
EXPECTED_LEGACY_TIMING_MISMATCH_REPOSITORIES="${EXPECTED_LEGACY_TIMING_MISMATCH_REPOSITORIES:-5}"
EXPECTED_MONTHS="${EXPECTED_MONTHS:-20}"
START_MONTH="${START_MONTH:-2024-01}"
END_MONTH="${END_MONTH:-2025-08}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if ! "${PYTHON_BIN}" -c 'import numpy, pandas' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy and pandas." >&2
  exit 1
fi
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

for required_file in "${PY_SCRIPT}" "${PAPER_PANEL_FILE}" "${LOCAL_REPO_MONTH_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
PAPER_PANEL_SHA256="$(sha256sum "${PAPER_PANEL_FILE}" | awk '{print $1}')"
LOCAL_PANEL_SHA256="$(sha256sum "${LOCAL_REPO_MONTH_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare paper/local repository-NCLOC DiD panels"
  printf "%-42s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-42s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-42s %s\n" "Python:" "${PYTHON_BIN} (${PYTHON_VERSION})"
  printf "%-42s %s\n" "Implementation version:" "${IMPLEMENTATION_VERSION}"
  printf "%-42s %s\n" "Python analysis script:" "${PY_SCRIPT}"
  printf "%-42s %s\n" "Python script SHA256:" "${PY_SCRIPT_SHA256}"
  printf "%-42s %s\n" "C03 paper panel:" "${PAPER_PANEL_FILE}"
  printf "%-42s %s\n" "C03 panel SHA256:" "${PAPER_PANEL_SHA256}"
  printf "%-42s %s\n" "C04b local repo-month panel:" "${LOCAL_REPO_MONTH_FILE}"
  printf "%-42s %s\n" "C04b panel SHA256:" "${LOCAL_PANEL_SHA256}"
  printf "%-42s %s\n" "Expected paper/common rows:" "${EXPECTED_PAPER_FULL_COMPLETE_ROWS}/${EXPECTED_COMMON_ROWS}"
  printf "%-42s %s\n" "Expected estimable paper/common rows:" "${EXPECTED_PAPER_FULL_ESTIMABLE_ROWS}/${EXPECTED_COMMON_ESTIMABLE_ROWS}"
  printf "%-42s %s\n" "Expected estimable treatment repos:" "${EXPECTED_PAPER_FULL_ESTIMABLE_TREATMENT_REPOSITORIES}/${EXPECTED_COMMON_ESTIMABLE_TREATMENT_REPOSITORIES}"
  printf "%-42s %s\n" "Strict expected counts:" "${STRICT_EXPECTED_COUNTS}"
  printf "%-42s %s\n" "Combined panel:" "${COMBINED_PANEL_OUTPUT}"
  printf "%-42s %s\n" "Paper full estimable panel:" "${PAPER_FULL_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Paper common estimable panel:" "${PAPER_COMMON_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Local taxonomy common estimable panel:" "${LOCAL_TAXONOMY_COMMON_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-42s %s\n" "Summary output:" "${SUMMARY_OUTPUT}"
  printf "%-42s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Join C03 and C04b, derive timing, and prepare DiD inputs"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --paper-panel-file "${PAPER_PANEL_FILE}" \
  --local-repo-month-file "${LOCAL_REPO_MONTH_FILE}" \
  --combined-panel-output "${COMBINED_PANEL_OUTPUT}" \
  --paper-full-complete-output "${PAPER_FULL_COMPLETE_OUTPUT}" \
  --paper-full-estimable-output "${PAPER_FULL_ESTIMABLE_OUTPUT}" \
  --paper-common-complete-output "${PAPER_COMMON_COMPLETE_OUTPUT}" \
  --paper-common-estimable-output "${PAPER_COMMON_ESTIMABLE_OUTPUT}" \
  --local-taxonomy-common-complete-output "${LOCAL_TAXONOMY_COMMON_COMPLETE_OUTPUT}" \
  --local-taxonomy-common-estimable-output "${LOCAL_TAXONOMY_COMMON_ESTIMABLE_OUTPUT}" \
  --local-all-common-complete-output "${LOCAL_ALL_COMMON_COMPLETE_OUTPUT}" \
  --local-all-common-estimable-output "${LOCAL_ALL_COMMON_ESTIMABLE_OUTPUT}" \
  --backend-comparison-output "${BACKEND_COMPARISON_OUTPUT}" \
  --treatment-estimability-output "${TREATMENT_ESTIMABILITY_OUTPUT}" \
  --legacy-timing-audit-output "${LEGACY_TIMING_AUDIT_OUTPUT}" \
  --sample-summary-output "${SAMPLE_SUMMARY_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
  --expected-paper-panel-rows "${EXPECTED_PAPER_PANEL_ROWS}" \
  --expected-treatment-paper-rows "${EXPECTED_TREATMENT_PAPER_ROWS}" \
  --expected-control-paper-rows "${EXPECTED_CONTROL_PAPER_ROWS}" \
  --expected-paper-repositories "${EXPECTED_PAPER_REPOSITORIES}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-local-rows "${EXPECTED_LOCAL_ROWS}" \
  --expected-local-repositories "${EXPECTED_LOCAL_REPOSITORIES}" \
  --expected-paper-ncloc-missing "${EXPECTED_PAPER_NCLOC_MISSING}" \
  --expected-paper-full-complete-rows "${EXPECTED_PAPER_FULL_COMPLETE_ROWS}" \
  --expected-common-rows "${EXPECTED_COMMON_ROWS}" \
  --expected-paper-full-estimable-rows "${EXPECTED_PAPER_FULL_ESTIMABLE_ROWS}" \
  --expected-common-estimable-rows "${EXPECTED_COMMON_ESTIMABLE_ROWS}" \
  --expected-paper-full-estimable-treatment-repositories "${EXPECTED_PAPER_FULL_ESTIMABLE_TREATMENT_REPOSITORIES}" \
  --expected-common-estimable-treatment-repositories "${EXPECTED_COMMON_ESTIMABLE_TREATMENT_REPOSITORIES}" \
  --expected-legacy-timing-mismatch-rows "${EXPECTED_LEGACY_TIMING_MISMATCH_ROWS}" \
  --expected-legacy-timing-mismatch-repositories "${EXPECTED_LEGACY_TIMING_MISMATCH_REPOSITORIES}" \
  --expected-months "${EXPECTED_MONTHS}" \
  --start-month "${START_MONTH}" \
  --end-month "${END_MONTH}" \
  --log-level "${LOG_LEVEL}" \
  2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: ${RUN_LABEL} failed with status ${run_status}." | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  printf "%-42s %s\n" "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-42s %s\n" "Combined panel:" "${COMBINED_PANEL_OUTPUT}"
  printf "%-42s %s\n" "Paper full complete-case panel:" "${PAPER_FULL_COMPLETE_OUTPUT}"
  printf "%-42s %s\n" "Paper full estimable panel:" "${PAPER_FULL_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Paper common estimable panel:" "${PAPER_COMMON_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Local taxonomy common estimable:" "${LOCAL_TAXONOMY_COMMON_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Local all-recognized robustness:" "${LOCAL_ALL_COMMON_ESTIMABLE_OUTPUT}"
  printf "%-42s %s\n" "Treatment estimability audit:" "${TREATMENT_ESTIMABILITY_OUTPUT}"
  printf "%-42s %s\n" "Legacy timing audit:" "${LEGACY_TIMING_AUDIT_OUTPUT}"
  printf "%-42s %s\n" "QC:" "${QC_OUTPUT}"
  printf "%-42s %s\n" "Summary:" "${SUMMARY_OUTPUT}"
  printf "%-42s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: review C05 sample attrition and treatment estimability before C06 DiD."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
