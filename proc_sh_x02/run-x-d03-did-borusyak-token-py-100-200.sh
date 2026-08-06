#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-d03 v1: Borusyak DiD for 100-200 literal-space tokens
# ============================================================
#
# Purpose:
#   Estimate the static and dynamic effect of Cursor adoption on the
#   repository-month stock of tokens contained in Python function bodies
#   whose literal-space token count is between 100 and 200, inclusive.
#
# Input:
#   The usable 1,953-row repo-month panel produced by run-x-d02.
#
# Model:
#   Outcome: log_token_py_100_200 = log1p(token_py_100_200)
#   First stage:
#     log_age + ncloc + log_contributors + log_stars + log_issues
#     with repository and calendar-month fixed effects.
#   Treatment timing is absorbing and uses event_index/time_index only.
#   Dynamic event window: -6 through +6, with -1 omitted.
#   Placebo pretrend periods: -6 through -2.
#
# Outputs:
#   Static effect, dynamic effects, individual pretrend checks, joint
#   pretrend test, sample/event support, model diagnostics, QC, plots,
#   model RDS files, session information, and a compact summary.
#
# This wrapper is independent and does not call an older experiment wrapper.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d03"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

R_BIN="${R_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x02/did_borusyak_token_py_100_200.R}"
INPUT_FILE="${INPUT_FILE:-repo_x02/run-x-d02/velocity_did_panel_token_py_100_200.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
PLOT_DIR="${PLOT_DIR:-${OUTPUT_DIR}/plots}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-token-py-100-200-${RUN_TS}.log}"

STATIC_OUTPUT="${STATIC_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_static_effect.csv}"
DYNAMIC_OUTPUT="${DYNAMIC_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_dynamic_effects.csv}"
PRETREND_OUTPUT="${PRETREND_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_pretrend_checks.csv}"
PRETREND_JOINT_OUTPUT="${PRETREND_JOINT_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_pretrend_joint_test.csv}"
EVENT_SUPPORT_OUTPUT="${EVENT_SUPPORT_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_event_support.csv}"
COHORT_SUPPORT_OUTPUT="${COHORT_SUPPORT_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_cohort_support.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_sample_summary.csv}"
LEGACY_AUDIT_OUTPUT="${LEGACY_AUDIT_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_legacy_flag_audit.csv}"
MODEL_DIAGNOSTICS_OUTPUT="${MODEL_DIAGNOSTICS_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_model_diagnostics.csv}"
QC_OUTPUT="${QC_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_did_qc.csv}"
STATIC_MODEL_RDS="${STATIC_MODEL_RDS:-${OUTPUT_DIR}/token_py_100_200_static_model.rds}"
DYNAMIC_MODEL_RDS="${DYNAMIC_MODEL_RDS:-${OUTPUT_DIR}/token_py_100_200_dynamic_model.rds}"
PRETREND_MODEL_RDS="${PRETREND_MODEL_RDS:-${OUTPUT_DIR}/token_py_100_200_pretrend_model.rds}"
SESSION_INFO_OUTPUT="${SESSION_INFO_OUTPUT:-${OUTPUT_DIR}/token_py_100_200_session_info.txt}"
DYNAMIC_PDF="${DYNAMIC_PDF:-${PLOT_DIR}/token_py_100_200_dynamic_effects.pdf}"
DYNAMIC_PNG="${DYNAMIC_PNG:-${PLOT_DIR}/token_py_100_200_dynamic_effects.png}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/token_py_100_200_did_summary.csv}"

HORIZON_MIN="${HORIZON_MIN:--6}"
HORIZON_MAX="${HORIZON_MAX:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
REFERENCE_EVENT_TIME="${REFERENCE_EVENT_TIME:--1}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
RANDOM_SEED="${RANDOM_SEED:-20260805}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1953}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-913}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-1040}"
EXPECTED_UNTREATED_ROWS="${EXPECTED_UNTREATED_ROWS:-1591}"
EXPECTED_TREATED_ROWS="${EXPECTED_TREATED_ROWS:-362}"
EXPECTED_DYNAMIC_TREATED_ROWS="${EXPECTED_DYNAMIC_TREATED_ROWS:-342}"
EXPECTED_STATIC_ROWS="${EXPECTED_STATIC_ROWS:-1}"
EXPECTED_DYNAMIC_ROWS="${EXPECTED_DYNAMIC_ROWS:-12}"
EXPECTED_PRETREND_ROWS="${EXPECTED_PRETREND_ROWS:-5}"
EXPECTED_EXPLICIT_EXCLUSIONS="${EXPECTED_EXPLICIT_EXCLUSIONS:-1}"

if ! command -v "${R_BIN}" >/dev/null 2>&1; then
  echo "ERROR: R executable not found: ${R_BIN}" >&2
  exit 1
fi
for required_file in "${R_SCRIPT}" "${INPUT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi
if ! "${R_BIN}" -e 'required <- c("didimputation", "data.table", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", ")))' >/dev/null 2>&1; then
  echo "ERROR: R packages didimputation, data.table, fixest, and ggplot2 are required." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${PLOT_DIR}" "${LOG_DIR}"

R_VERSION="$("${R_BIN}" --version 2>&1 | head -n 1)"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
R_PACKAGE_VERSIONS="$("${R_BIN}" -e 'p <- c("data.table","didimputation","fixest","ggplot2"); cat(paste(sprintf("%s=%s", p, vapply(p, function(x) as.character(packageVersion(x)), character(1))), collapse="; "))' 2>/dev/null)"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Borusyak DiD for Python 100-200 token bodies"
  printf "%-42s %s\n" "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-42s %s\n" "Project root:" "${PROJECT_ROOT}"
  printf "%-42s %s\n" "R:" "${R_BIN} (${R_VERSION})"
  printf "%-42s %s\n" "R packages:" "${R_PACKAGE_VERSIONS}"
  printf "%-42s %s\n" "Implementation version:" "${IMPLEMENTATION_VERSION}"
  printf "%-42s %s\n" "R analysis script:" "${R_SCRIPT}"
  printf "%-42s %s\n" "R script SHA256:" "${R_SCRIPT_SHA256}"
  printf "%-42s %s\n" "Input panel:" "${INPUT_FILE}"
  printf "%-42s %s\n" "Input SHA256:" "${INPUT_SHA256}"
  printf "%-42s %s\n" "Outcome:" "log_token_py_100_200"
  printf "%-42s %s\n" "Dynamic horizon:" "${HORIZON_MIN}:${HORIZON_MAX}"
  printf "%-42s %s\n" "Pretrend window:" "${PRETREND_MIN}:${PRETREND_MAX}"
  printf "%-42s %s\n" "Reference event time:" "${REFERENCE_EVENT_TIME}"
  printf "%-42s %s\n" "Expected rows:" "${EXPECTED_ROWS}"
  printf "%-42s %s\n" "Expected treated/untreated rows:" "${EXPECTED_TREATED_ROWS}/${EXPECTED_UNTREATED_ROWS}"
  printf "%-42s %s\n" "Strict expected counts:" "${STRICT_EXPECTED_COUNTS}"
  printf "%-42s %s\n" "Output directory:" "${OUTPUT_DIR}"
  printf "%-42s %s\n" "Log file:" "${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Validate the D02 panel and run Borusyak DiD"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

set +e
"${R_BIN}" "${R_SCRIPT}" \
  --input-file "${INPUT_FILE}" \
  --static-output "${STATIC_OUTPUT}" \
  --dynamic-output "${DYNAMIC_OUTPUT}" \
  --pretrend-output "${PRETREND_OUTPUT}" \
  --pretrend-joint-output "${PRETREND_JOINT_OUTPUT}" \
  --event-support-output "${EVENT_SUPPORT_OUTPUT}" \
  --cohort-support-output "${COHORT_SUPPORT_OUTPUT}" \
  --sample-summary-output "${SAMPLE_SUMMARY_OUTPUT}" \
  --legacy-audit-output "${LEGACY_AUDIT_OUTPUT}" \
  --model-diagnostics-output "${MODEL_DIAGNOSTICS_OUTPUT}" \
  --qc-output "${QC_OUTPUT}" \
  --static-model-rds "${STATIC_MODEL_RDS}" \
  --dynamic-model-rds "${DYNAMIC_MODEL_RDS}" \
  --pretrend-model-rds "${PRETREND_MODEL_RDS}" \
  --session-info-output "${SESSION_INFO_OUTPUT}" \
  --dynamic-pdf "${DYNAMIC_PDF}" \
  --dynamic-png "${DYNAMIC_PNG}" \
  --summary-output "${SUMMARY_OUTPUT}" \
  --horizon-min "${HORIZON_MIN}" \
  --horizon-max "${HORIZON_MAX}" \
  --pretrend-min "${PRETREND_MIN}" \
  --pretrend-max "${PRETREND_MAX}" \
  --reference-event-time "${REFERENCE_EVENT_TIME}" \
  --confidence-level "${CONFIDENCE_LEVEL}" \
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
  --expected-rows "${EXPECTED_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}" \
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}" \
  --expected-untreated-rows "${EXPECTED_UNTREATED_ROWS}" \
  --expected-treated-rows "${EXPECTED_TREATED_ROWS}" \
  --expected-dynamic-treated-rows "${EXPECTED_DYNAMIC_TREATED_ROWS}" \
  --expected-static-rows "${EXPECTED_STATIC_ROWS}" \
  --expected-dynamic-rows "${EXPECTED_DYNAMIC_ROWS}" \
  --expected-pretrend-rows "${EXPECTED_PRETREND_ROWS}" \
  --expected-explicit-exclusions "${EXPECTED_EXPLICIT_EXCLUSIONS}" \
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
  printf "%-42s %s\n" "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf "%-42s %s\n" "Static effect:" "${STATIC_OUTPUT}"
  printf "%-42s %s\n" "Dynamic effects:" "${DYNAMIC_OUTPUT}"
  printf "%-42s %s\n" "Pretrend checks:" "${PRETREND_OUTPUT}"
  printf "%-42s %s\n" "Joint pretrend test:" "${PRETREND_JOINT_OUTPUT}"
  printf "%-42s %s\n" "Event support:" "${EVENT_SUPPORT_OUTPUT}"
  printf "%-42s %s\n" "Sample summary:" "${SAMPLE_SUMMARY_OUTPUT}"
  printf "%-42s %s\n" "Dynamic plot:" "${DYNAMIC_PDF}"
  printf "%-42s %s\n" "QC output:" "${QC_OUTPUT}"
  printf "%-42s %s\n" "Summary output:" "${SUMMARY_OUTPUT}"
  printf "%-42s %s\n" "Log file:" "${LOG_FILE}"
  echo "Next step: review the static ATT, event-study pattern, and pretrend diagnostics."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
