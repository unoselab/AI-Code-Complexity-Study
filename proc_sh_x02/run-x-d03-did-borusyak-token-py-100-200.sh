#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-d03 v1: Borusyak DiD for 100-200 literal-space tokens
# ============================================================
#
# Purpose:
#   Estimate the static and dynamic effects of Cursor adoption on the
#   log-transformed snapshot stock of Python function-body tokens whose
#   literal-space token counts are between 100 and 200, inclusive.
#
# Input:
#   repo_x02/run-x-d02/velocity_did_panel_token_py_100_200.csv
#
# Primary outcome:
#   log_token_py_100_200 = log1p(token_py_100_200)
#
# First-stage specification:
#   log_age + ncloc + log_contributors + log_stars + log_issues
#   with repository and calendar-month fixed effects.
#
# Treatment definition:
#   Absorbing treatment based only on event_index and time_index.
#   Legacy cursor, is_treatment, post_event, lead_*, and lag_* fields
#   are retained for audit only and are not used by the estimator.
#
# Outputs:
#   Static ATT, dynamic effects, placebo pretrend coefficients and joint
#   test, support tables, model diagnostics, metadata, QC, RDS objects,
#   and event-study plots.
#
# This wrapper is independent and does not call an earlier experiment wrapper.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d03"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

R_BIN="${R_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x02/did_borusyak_token_py_100_200-v1.R}"
INPUT_FILE="${INPUT_FILE:-repo_x02/run-x-d02/velocity_did_panel_token_py_100_200.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
PLOT_DIR="${PLOT_DIR:-${MAIN_OUTPUT_DIR}/plots}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-token-py-100-200-${RUN_TS}.log}"

STATIC_OUTPUT="${STATIC_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_static_effects.csv}"
DYNAMIC_OUTPUT="${DYNAMIC_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_dynamic_effects.csv}"
PRETREND_OUTPUT="${PRETREND_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_pretrend_checks.csv}"
PRETREND_SUMMARY_OUTPUT="${PRETREND_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_pretrend_summary.csv}"
EVENT_SUPPORT_OUTPUT="${EVENT_SUPPORT_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_event_support.csv}"
COHORT_SUPPORT_OUTPUT="${COHORT_SUPPORT_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_cohort_support.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_sample_summary.csv}"
LEGACY_AUDIT_OUTPUT="${LEGACY_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_legacy_flag_audit.csv}"
MODEL_DIAGNOSTICS_OUTPUT="${MODEL_DIAGNOSTICS_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_model_diagnostics.csv}"
RUN_METADATA_OUTPUT="${RUN_METADATA_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_run_metadata.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_did_qc.csv}"
SESSION_INFO_OUTPUT="${SESSION_INFO_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_session_info.txt}"
STATIC_MODEL_OUTPUT="${STATIC_MODEL_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_static_model.rds}"
DYNAMIC_MODEL_OUTPUT="${DYNAMIC_MODEL_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_dynamic_model.rds}"
PRETREND_MODEL_OUTPUT="${PRETREND_MODEL_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_pretrend_model.rds}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/token_py_100_200_did_summary.csv}"
DYNAMIC_PDF_OUTPUT="${DYNAMIC_PDF_OUTPUT:-${PLOT_DIR}/token_py_100_200_dynamic_effects.pdf}"
DYNAMIC_PNG_OUTPUT="${DYNAMIC_PNG_OUTPUT:-${PLOT_DIR}/token_py_100_200_dynamic_effects.png}"
STATIC_PDF_OUTPUT="${STATIC_PDF_OUTPUT:-${PLOT_DIR}/token_py_100_200_static_effect.pdf}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_ROWS="${EXPECTED_ROWS:-1953}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-913}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-1040}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_UNTREATED_ROWS="${EXPECTED_UNTREATED_ROWS:-1591}"
EXPECTED_STATIC_TREATED_ROWS="${EXPECTED_STATIC_TREATED_ROWS:-362}"
EXPECTED_DYNAMIC_POST_ROWS="${EXPECTED_DYNAMIC_POST_ROWS:-342}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
HORIZON_MIN="${HORIZON_MIN:--6}"
HORIZON_MAX="${HORIZON_MAX:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
REFERENCE_EVENT_TIME="${REFERENCE_EVENT_TIME:--1}"
RANDOM_SEED="${RANDOM_SEED:-20260805}"

if ! command -v "${R_BIN}" >/dev/null 2>&1; then
  echo "ERROR: R executable not found: ${R_BIN}" >&2
  exit 1
fi
if [[ ! -f "${R_SCRIPT}" ]]; then
  echo "ERROR: R analysis script not found: ${R_SCRIPT}" >&2
  exit 1
fi
if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "ERROR: D02 input panel not found: ${INPUT_FILE}" >&2
  exit 1
fi
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi
if (( HORIZON_MIN > HORIZON_MAX )); then
  echo "ERROR: HORIZON_MIN must not exceed HORIZON_MAX." >&2
  exit 1
fi
if (( PRETREND_MIN > PRETREND_MAX || PRETREND_MAX >= 0 )); then
  echo "ERROR: PRETREND_MIN:PRETREND_MAX must be a negative interval." >&2
  exit 1
fi
if (( REFERENCE_EVENT_TIME >= PRETREND_MIN && REFERENCE_EVENT_TIME <= PRETREND_MAX )); then
  echo "ERROR: REFERENCE_EVENT_TIME must not be inside the placebo interval." >&2
  exit 1
fi

if ! "${R_BIN}" -e 'required <- c("didimputation", "data.table", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", ")))' >/dev/null 2>&1; then
  echo "ERROR: Required R packages: didimputation, data.table, fixest, ggplot2." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${PLOT_DIR}"

R_VERSION="$("${R_BIN}" --version 2>&1 | head -n 1)"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Borusyak DiD for Python 100-200 token bodies"
  printf "%-46s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-46s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-46s %s\n" "R:" "${R_BIN} (${R_VERSION})"
  printf "%-46s %s\n" "Implementation version:" "${IMPLEMENTATION_VERSION}"
  printf "%-46s %s\n" "R analysis script:" "${R_SCRIPT}"
  printf "%-46s %s\n" "R script SHA256:" "${R_SCRIPT_SHA256}"
  printf "%-46s %s\n" "Input panel:" "${INPUT_FILE}"
  printf "%-46s %s\n" "Input SHA256:" "${INPUT_SHA256}"
  printf "%-46s %s\n" "Primary outcome:" "log_token_py_100_200"
  printf "%-46s %s\n" "Dynamic horizon:" "${HORIZON_MIN}:${HORIZON_MAX}"
  printf "%-46s %s\n" "Pretrend window:" "${PRETREND_MIN}:${PRETREND_MAX}"
  printf "%-46s %s\n" "Omitted reference event time:" "${REFERENCE_EVENT_TIME}"
  printf "%-46s %s\n" "Cluster variable:" "repo_id"
  printf "%-46s %s\n" "Strict expected counts:" "${STRICT_EXPECTED_COUNTS}"
  printf "%-46s %s\n" "Static effects output:" "${STATIC_OUTPUT}"
  printf "%-46s %s\n" "Dynamic effects output:" "${DYNAMIC_OUTPUT}"
  printf "%-46s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-46s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Run static, dynamic, and pretrend models"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${R_BIN}" "${R_SCRIPT}" \
  --input "${INPUT_FILE}" \
  --static-output "${STATIC_OUTPUT}" \
  --dynamic-output "${DYNAMIC_OUTPUT}" \
  --pretrend-output "${PRETREND_OUTPUT}" \
  --pretrend-summary-output "${PRETREND_SUMMARY_OUTPUT}" \
  --event-support-output "${EVENT_SUPPORT_OUTPUT}" \
  --cohort-support-output "${COHORT_SUPPORT_OUTPUT}" \
  --sample-summary-output "${SAMPLE_SUMMARY_OUTPUT}" \
  --legacy-audit-output "${LEGACY_AUDIT_OUTPUT}" \
  --model-diagnostics-output "${MODEL_DIAGNOSTICS_OUTPUT}" \
  --run-metadata-output "${RUN_METADATA_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --session-info-output "${SESSION_INFO_OUTPUT}" \
  --static-model-output "${STATIC_MODEL_OUTPUT}" \
  --dynamic-model-output "${DYNAMIC_MODEL_OUTPUT}" \
  --pretrend-model-output "${PRETREND_MODEL_OUTPUT}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --dynamic-pdf-output "${DYNAMIC_PDF_OUTPUT}" \
  --dynamic-png-output "${DYNAMIC_PNG_OUTPUT}" \
  --static-pdf-output "${STATIC_PDF_OUTPUT}" \
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
  --expected-rows "${EXPECTED_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}" \
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-untreated-rows "${EXPECTED_UNTREATED_ROWS}" \
  --expected-static-treated-rows "${EXPECTED_STATIC_TREATED_ROWS}" \
  --expected-dynamic-post-rows "${EXPECTED_DYNAMIC_POST_ROWS}" \
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}" \
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
  printf "%-46s %s\n" "Pretrend coefficients:" "${PRETREND_OUTPUT}"
  printf "%-46s %s\n" "Pretrend joint test:" "${PRETREND_SUMMARY_OUTPUT}"
  printf "%-46s %s\n" "Event support:" "${EVENT_SUPPORT_OUTPUT}"
  printf "%-46s %s\n" "Cohort support:" "${COHORT_SUPPORT_OUTPUT}"
  printf "%-46s %s\n" "Sample summary:" "${SAMPLE_SUMMARY_OUTPUT}"
  printf "%-46s %s\n" "Legacy flag audit:" "${LEGACY_AUDIT_OUTPUT}"
  printf "%-46s %s\n" "Model diagnostics:" "${MODEL_DIAGNOSTICS_OUTPUT}"
  printf "%-46s %s\n" "Dynamic PDF:" "${DYNAMIC_PDF_OUTPUT}"
  printf "%-46s %s\n" "Dynamic PNG:" "${DYNAMIC_PNG_OUTPUT}"
  printf "%-46s %s\n" "QC:" "${QC_OUTPUT}"
  printf "%-46s %s\n" "Summary:" "${SUMMARY_OUTPUT}"
  printf "%-46s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: inspect static ATT, dynamic effects, and the joint pretrend test."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
