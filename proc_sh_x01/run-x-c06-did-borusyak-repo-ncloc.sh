#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c06 v2: Run Borusyak DiD for four repository-NCLOC specs
# ============================================================
#
# Purpose:
#   Estimate static and dynamic effects of Cursor adoption on monthly commits
#   and lines added under four NCLOC specifications prepared by run-x-c05.
#
# Specifications:
#   1. Paper SonarQube NCLOC on the full Borusyak-estimable sample.
#   2. Paper SonarQube NCLOC on the exact paper/local common sample.
#   3. Local cloc paper-taxonomy NCLOC on the same exact common sample.
#   4. Local cloc all-recognized NCLOC on the same exact common sample.
#
# Model:
#   Outcomes: log_commits and log_lines_added.
#   First stage: log_age + ncloc + log_contributors + log_stars + log_issues,
#                with repository and calendar-month fixed effects.
#   Dynamic horizon: event months -6 through +6.
#   Event time -1 is the omitted normalization reference, so each dynamic
#   model returns 12 estimated coefficients rather than 13 rows.
#   Pretrend terms: event months -6 through -2.
#
# Inputs:
#   Four run-x-c05 Borusyak-estimable CSV files.
#
# Outputs:
#   Static effects, dynamic effects, pretrend checks, descriptive
#   cross-specification comparisons, model audit, QC, and PDF plots.
#
# This wrapper is self-contained and does not call another experiment wrapper.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-c06"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-repo-ncloc-${RUN_TS}.log}"

R_BIN="${R_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_repo_ncloc_four_specifications.R}"

PAPER_FULL_INPUT="${PAPER_FULL_INPUT:-repo_x01/run-x-c05/velocity_did_panel_paper_ncloc_full_borusyak_estimable.csv}"
PAPER_COMMON_INPUT="${PAPER_COMMON_INPUT:-repo_x01/run-x-c05/velocity_did_panel_paper_ncloc_common_borusyak_estimable.csv}"
LOCAL_TAXONOMY_COMMON_INPUT="${LOCAL_TAXONOMY_COMMON_INPUT:-repo_x01/run-x-c05/velocity_did_panel_local_cloc_paper_taxonomy_common_borusyak_estimable.csv}"
LOCAL_ALL_COMMON_INPUT="${LOCAL_ALL_COMMON_INPUT:-repo_x01/run-x-c05/velocity_did_panel_local_cloc_all_recognized_common_borusyak_estimable.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
PLOT_DIR="${PLOT_DIR:-${MAIN_OUTPUT_DIR}/plots}"

STATIC_OUTPUT="${STATIC_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_static_effects_four_specifications.csv}"
DYNAMIC_OUTPUT="${DYNAMIC_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_dynamic_effects_four_specifications.csv}"
PRETREND_OUTPUT="${PRETREND_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_pretrend_checks_four_specifications.csv}"
PRETREND_SUMMARY_OUTPUT="${PRETREND_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_pretrend_summary_four_specifications.csv}"
STATIC_COMPARISON_OUTPUT="${STATIC_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_static_comparisons_four_specifications.csv}"
DYNAMIC_COMPARISON_OUTPUT="${DYNAMIC_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_dynamic_comparisons_four_specifications.csv}"
SPECIFICATION_SUMMARY_OUTPUT="${SPECIFICATION_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_specification_summary.csv}"
MODEL_AUDIT_OUTPUT="${MODEL_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_model_audit.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_qc.csv}"
SESSION_INFO_OUTPUT="${SESSION_INFO_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_session_info.txt}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_did_summary.csv}"
DYNAMIC_PLOT_OUTPUT="${DYNAMIC_PLOT_OUTPUT:-${PLOT_DIR}/velocity_did_dynamic_four_specifications.pdf}"
PRIMARY_COMPARISON_PLOT_OUTPUT="${PRIMARY_COMPARISON_PLOT_OUTPUT:-${PLOT_DIR}/velocity_did_dynamic_primary_backend_comparison.pdf}"
STATIC_PLOT_OUTPUT="${STATIC_PLOT_OUTPUT:-${PLOT_DIR}/velocity_did_static_four_specifications.pdf}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_PAPER_FULL_ROWS="${EXPECTED_PAPER_FULL_ROWS:-2127}"
EXPECTED_PAPER_FULL_REPOSITORIES="${EXPECTED_PAPER_FULL_REPOSITORIES:-198}"
EXPECTED_PAPER_FULL_TREATMENT_REPOSITORIES="${EXPECTED_PAPER_FULL_TREATMENT_REPOSITORIES:-72}"
EXPECTED_PAPER_FULL_CONTROL_REPOSITORIES="${EXPECTED_PAPER_FULL_CONTROL_REPOSITORIES:-126}"
EXPECTED_COMMON_ROWS="${EXPECTED_COMMON_ROWS:-2090}"
EXPECTED_COMMON_REPOSITORIES="${EXPECTED_COMMON_REPOSITORIES:-194}"
EXPECTED_COMMON_TREATMENT_REPOSITORIES="${EXPECTED_COMMON_TREATMENT_REPOSITORIES:-69}"
EXPECTED_COMMON_CONTROL_REPOSITORIES="${EXPECTED_COMMON_CONTROL_REPOSITORIES:-125}"
EXPECTED_STATIC_ROWS="${EXPECTED_STATIC_ROWS:-8}"
EXPECTED_DYNAMIC_ROWS="${EXPECTED_DYNAMIC_ROWS:-96}"
EXPECTED_PRETREND_ROWS="${EXPECTED_PRETREND_ROWS:-40}"
EXPECTED_MODEL_AUDIT_ROWS="${EXPECTED_MODEL_AUDIT_ROWS:-16}"
EXPECTED_STATIC_COMPARISON_ROWS="${EXPECTED_STATIC_COMPARISON_ROWS:-6}"
EXPECTED_DYNAMIC_COMPARISON_ROWS="${EXPECTED_DYNAMIC_COMPARISON_ROWS:-72}"
HORIZON_MIN="${HORIZON_MIN:--6}"
HORIZON_MAX="${HORIZON_MAX:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
# didimputation uses event time -1 as the omitted reference period.
REFERENCE_EVENT_TIME="${REFERENCE_EVENT_TIME:--1}"
RANDOM_SEED="${RANDOM_SEED:-20260804}"

if ! command -v "${R_BIN}" >/dev/null 2>&1; then
  echo "ERROR: R executable not found: ${R_BIN}" >&2
  exit 1
fi
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" \
  "${PAPER_FULL_INPUT}" \
  "${PAPER_COMMON_INPUT}" \
  "${LOCAL_TAXONOMY_COMMON_INPUT}" \
  "${LOCAL_ALL_COMMON_INPUT}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! "${R_BIN}" -e 'required <- c("didimputation", "data.table", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", ")))' >/dev/null 2>&1; then
  echo "ERROR: R packages didimputation, data.table, and ggplot2 are required." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${PLOT_DIR}"

R_VERSION="$("${R_BIN}" --version 2>&1 | head -n 1)"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
PAPER_FULL_SHA256="$(sha256sum "${PAPER_FULL_INPUT}" | awk '{print $1}')"
PAPER_COMMON_SHA256="$(sha256sum "${PAPER_COMMON_INPUT}" | awk '{print $1}')"
LOCAL_TAXONOMY_SHA256="$(sha256sum "${LOCAL_TAXONOMY_COMMON_INPUT}" | awk '{print $1}')"
LOCAL_ALL_SHA256="$(sha256sum "${LOCAL_ALL_COMMON_INPUT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Borusyak DiD with four repository-NCLOC specifications"
  printf "%-46s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-46s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-46s %s\n" "R:" "${R_BIN} (${R_VERSION})"
  printf "%-46s %s\n" "Implementation version:" "${IMPLEMENTATION_VERSION}"
  printf "%-46s %s\n" "R analysis script:" "${R_SCRIPT}"
  printf "%-46s %s\n" "R script SHA256:" "${R_SCRIPT_SHA256}"
  printf "%-46s %s\n" "Paper full input:" "${PAPER_FULL_INPUT}"
  printf "%-46s %s\n" "Paper full SHA256:" "${PAPER_FULL_SHA256}"
  printf "%-46s %s\n" "Paper common input:" "${PAPER_COMMON_INPUT}"
  printf "%-46s %s\n" "Paper common SHA256:" "${PAPER_COMMON_SHA256}"
  printf "%-46s %s\n" "Local taxonomy common input:" "${LOCAL_TAXONOMY_COMMON_INPUT}"
  printf "%-46s %s\n" "Local taxonomy SHA256:" "${LOCAL_TAXONOMY_SHA256}"
  printf "%-46s %s\n" "Local all-recognized input:" "${LOCAL_ALL_COMMON_INPUT}"
  printf "%-46s %s\n" "Local all-recognized SHA256:" "${LOCAL_ALL_SHA256}"
  printf "%-46s %s\n" "Outcomes:" "log_commits, log_lines_added"
  printf "%-46s %s\n" "Dynamic horizon:" "${HORIZON_MIN}:${HORIZON_MAX}"
  printf "%-46s %s\n" "Pretrend window:" "${PRETREND_MIN}:${PRETREND_MAX}"
  printf "%-46s %s\n" "Omitted reference event time:" "${REFERENCE_EVENT_TIME}"
  printf "%-46s %s\n" "Expected dynamic rows:" "${EXPECTED_DYNAMIC_ROWS}"
  printf "%-46s %s\n" "Expected dynamic comparison rows:" "${EXPECTED_DYNAMIC_COMPARISON_ROWS}"
  printf "%-46s %s\n" "Strict expected counts:" "${STRICT_EXPECTED_COUNTS}"
  printf "%-46s %s\n" "Static effects output:" "${STATIC_OUTPUT}"
  printf "%-46s %s\n" "Dynamic effects output:" "${DYNAMIC_OUTPUT}"
  printf "%-46s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-46s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Run static and dynamic Borusyak DiD models"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${R_BIN}" "${R_SCRIPT}" \
  --paper-full-input "${PAPER_FULL_INPUT}" \
  --paper-common-input "${PAPER_COMMON_INPUT}" \
  --local-taxonomy-common-input "${LOCAL_TAXONOMY_COMMON_INPUT}" \
  --local-all-common-input "${LOCAL_ALL_COMMON_INPUT}" \
  --static-output "${STATIC_OUTPUT}" \
  --dynamic-output "${DYNAMIC_OUTPUT}" \
  --pretrend-output "${PRETREND_OUTPUT}" \
  --pretrend-summary-output "${PRETREND_SUMMARY_OUTPUT}" \
  --static-comparison-output "${STATIC_COMPARISON_OUTPUT}" \
  --dynamic-comparison-output "${DYNAMIC_COMPARISON_OUTPUT}" \
  --specification-summary-output "${SPECIFICATION_SUMMARY_OUTPUT}" \
  --model-audit-output "${MODEL_AUDIT_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --session-info-output "${SESSION_INFO_OUTPUT}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --dynamic-plot-output "${DYNAMIC_PLOT_OUTPUT}" \
  --primary-comparison-plot-output "${PRIMARY_COMPARISON_PLOT_OUTPUT}" \
  --static-plot-output "${STATIC_PLOT_OUTPUT}" \
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
  --expected-paper-full-rows "${EXPECTED_PAPER_FULL_ROWS}" \
  --expected-paper-full-repositories "${EXPECTED_PAPER_FULL_REPOSITORIES}" \
  --expected-paper-full-treatment-repositories "${EXPECTED_PAPER_FULL_TREATMENT_REPOSITORIES}" \
  --expected-paper-full-control-repositories "${EXPECTED_PAPER_FULL_CONTROL_REPOSITORIES}" \
  --expected-common-rows "${EXPECTED_COMMON_ROWS}" \
  --expected-common-repositories "${EXPECTED_COMMON_REPOSITORIES}" \
  --expected-common-treatment-repositories "${EXPECTED_COMMON_TREATMENT_REPOSITORIES}" \
  --expected-common-control-repositories "${EXPECTED_COMMON_CONTROL_REPOSITORIES}" \
  --expected-static-rows "${EXPECTED_STATIC_ROWS}" \
  --expected-dynamic-rows "${EXPECTED_DYNAMIC_ROWS}" \
  --expected-pretrend-rows "${EXPECTED_PRETREND_ROWS}" \
  --expected-model-audit-rows "${EXPECTED_MODEL_AUDIT_ROWS}" \
  --expected-static-comparison-rows "${EXPECTED_STATIC_COMPARISON_ROWS}" \
  --expected-dynamic-comparison-rows "${EXPECTED_DYNAMIC_COMPARISON_ROWS}" \
  --horizon-min "${HORIZON_MIN}" \
  --horizon-max "${HORIZON_MAX}" \
  --pretrend-min "${PRETREND_MIN}" \
  --pretrend-max "${PRETREND_MAX}" \
  --reference-event-time "${REFERENCE_EVENT_TIME}" \
  --random-seed "${RANDOM_SEED}" \
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
  printf "%-46s %s\n" "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-46s %s\n" "Static effects:" "${STATIC_OUTPUT}"
  printf "%-46s %s\n" "Dynamic effects:" "${DYNAMIC_OUTPUT}"
  printf "%-46s %s\n" "Pretrend checks:" "${PRETREND_OUTPUT}"
  printf "%-46s %s\n" "Static comparisons:" "${STATIC_COMPARISON_OUTPUT}"
  printf "%-46s %s\n" "Dynamic comparisons:" "${DYNAMIC_COMPARISON_OUTPUT}"
  printf "%-46s %s\n" "Specification summary:" "${SPECIFICATION_SUMMARY_OUTPUT}"
  printf "%-46s %s\n" "Model audit:" "${MODEL_AUDIT_OUTPUT}"
  printf "%-46s %s\n" "Dynamic plot:" "${DYNAMIC_PLOT_OUTPUT}"
  printf "%-46s %s\n" "Primary backend plot:" "${PRIMARY_COMPARISON_PLOT_OUTPUT}"
  printf "%-46s %s\n" "Static plot:" "${STATIC_PLOT_OUTPUT}"
  printf "%-46s %s\n" "QC:" "${QC_OUTPUT}"
  printf "%-46s %s\n" "Summary:" "${SUMMARY_OUTPUT}"
  printf "%-46s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: inspect the four static results, event studies, and pretrend checks."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
