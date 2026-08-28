#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-h06 v1: Borusyak DiD for frozen ML C_FUN-selected quality burden
# ============================================================
#
# Purpose:
#   Apply the validated run-x-d06 Borusyak execution and QC pattern
#   (itself derived from run-x-d04/run-x-b07) to the frozen run-x-h05
#   ML C_FUN-selected quality-burden panel.
#
# This wrapper is standalone. It was derived by copying the established D06
# wrapper structure and adapting it for H05 inputs. It never calls an older
# experiment wrapper.
#
# Inputs:
#   repo_x01/run-x-h05/quality_ml_cfun_repo_month_panel.csv.gz
#   repo_x01/run-x-h05/quality_ml_cfun_summary.csv
#   repo_x01/run-x-h05/quality_ml_cfun_sample_summary.csv
#   repo_x01/run-x-h05/quality_ml_cfun_global_audit.csv
#   repo_x01/run-x-h05/quality_ml_cfun_checks.csv
#   repo_x01/run-x-h05/metadata.json
#
# Frozen analysis dimensions:
#   - 2 sample specifications.
#   - 2 mapping specifications.
#   - 4 sample x mapping configurations.
#   - 2 first-stage model specifications.
#   - 8 selected-file SonarQube burden outcomes.
#
# Primary analysis:
#   full_sample x all_ml_files
#
# Estimation:
#   - Borusyak did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic effects event 0:+6.
#   - Placebo/pretrend terms event -6:-2.
#   - Event -1 omitted.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-h06"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-ml-cfun-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_ml_cfun_quality.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-h05/quality_ml_cfun_repo_month_panel.csv.gz}"
H05_SUMMARY_FILE="${H05_SUMMARY_FILE:-repo_x01/run-x-h05/quality_ml_cfun_summary.csv}"
H05_SAMPLE_SUMMARY_FILE="${H05_SAMPLE_SUMMARY_FILE:-repo_x01/run-x-h05/quality_ml_cfun_sample_summary.csv}"
H05_GLOBAL_AUDIT_FILE="${H05_GLOBAL_AUDIT_FILE:-repo_x01/run-x-h05/quality_ml_cfun_global_audit.csv}"
H05_CHECKS_FILE="${H05_CHECKS_FILE:-repo_x01/run-x-h05/quality_ml_cfun_checks.csv}"
H05_METADATA_FILE="${H05_METADATA_FILE:-repo_x01/run-x-h05/metadata.json}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-0.50}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
EXPECTED_MAPPING_SPECS="${EXPECTED_MAPPING_SPECS:-2}"
EXPECTED_ANALYSIS_SPECS="${EXPECTED_ANALYSIS_SPECS:-4}"
EXPECTED_LONG_ROWS="${EXPECTED_LONG_ROWS:-7738}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
STRICT_PRIMARY_WARNINGS="${STRICT_PRIMARY_WARNINGS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE="${OVERWRITE:-0}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" \
  "${INPUT_FILE}" \
  "${H05_SUMMARY_FILE}" \
  "${H05_SAMPLE_SUMMARY_FILE}" \
  "${H05_GLOBAL_AUDIT_FILE}" \
  "${H05_CHECKS_FILE}" \
  "${H05_METADATA_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

# Refuse to estimate H06 if the frozen H05 construction has any failed hard QC.
if grep -q ',fail,' "${H05_CHECKS_FILE}" || grep -q ',fail$' "${H05_CHECKS_FILE}"; then
  echo "ERROR: H05 checks contain one or more failed QC rows: ${H05_CHECKS_FILE}" >&2
  exit 1
fi

for integer_value in \
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_SAMPLE_SPECS}" "${EXPECTED_MAPPING_SPECS}" "${EXPECTED_ANALYSIS_SPECS}" \
  "${EXPECTED_LONG_ROWS}" "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}" "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

for boolean_value in "${STRICT_EXPECTED_COUNTS}" "${STRICT_PRIMARY_WARNINGS}" "${SELF_TEST_ONLY}" "${OVERWRITE}"; do
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: boolean options must be 0 or 1; observed: ${boolean_value}" >&2
    exit 1
  fi
done

if [[ -d "${OUTPUT_DIR}" && "${OVERWRITE}" != "1" && "${SELF_TEST_ONLY}" != "1" ]]; then
  echo "ERROR: output directory already exists: ${OUTPUT_DIR}" >&2
  echo "Set OVERWRITE=1 to replace the H06 output directory." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
if [[ "${SELF_TEST_ONLY}" != "1" && "${OVERWRITE}" == "1" ]]; then
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
H05_SUMMARY_SHA256="$(sha256sum "${H05_SUMMARY_FILE}" | awk '{print $1}')"
H05_SAMPLE_SUMMARY_SHA256="$(sha256sum "${H05_SAMPLE_SUMMARY_FILE}" | awk '{print $1}')"
H05_GLOBAL_AUDIT_SHA256="$(sha256sum "${H05_GLOBAL_AUDIT_FILE}" | awk '{print $1}')"
H05_CHECKS_SHA256="$(sha256sum "${H05_CHECKS_FILE}" | awk '{print $1}')"
H05_METADATA_SHA256="$(sha256sum "${H05_METADATA_FILE}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: Borusyak DiD for frozen ML C_FUN-selected Python quality burden"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "H05 panel:                       ${INPUT_FILE}"
  echo "H05 panel SHA256:                ${INPUT_SHA256}"
  echo "H05 summary SHA256:              ${H05_SUMMARY_SHA256}"
  echo "H05 sample summary SHA256:       ${H05_SAMPLE_SUMMARY_SHA256}"
  echo "H05 global audit SHA256:         ${H05_GLOBAL_AUDIT_SHA256}"
  echo "H05 checks SHA256:               ${H05_CHECKS_SHA256}"
  echo "H05 metadata SHA256:             ${H05_METADATA_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Primary analysis:                full_sample x all_ml_files"
  echo "Primary ML rule:                 file_ml_cfun_agc_share_space_by_token_weighted > ${PRIMARY_THRESHOLD}"
  echo "Sample specifications:           ${EXPECTED_SAMPLE_SPECS}"
  echo "Mapping specifications:          ${EXPECTED_MAPPING_SPECS}"
  echo "Analysis configurations:         ${EXPECTED_ANALYSIS_SPECS}"
  echo "Expected H05 panel rows:         ${EXPECTED_LONG_ROWS}"
  echo "Model specs:                     adjusted_burden + fe_only_burden"
  echo "Burden outcomes:                 8"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Reported post-treatment terms:   0:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Density:                         not computed"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Strict primary warnings:         ${STRICT_PRIMARY_WARNINGS}"
  echo "Self-test only:                  ${SELF_TEST_ONLY}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run H06 structural self-test"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse H06 R program"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "invisible(parse(file='${R_SCRIPT}')); cat('R parse: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "SELF_TEST_ONLY=1: stopping after self-test and parse checks." | tee -a "${LOG_FILE}"
  exit 0
fi

COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --h05-summary-file "${H05_SUMMARY_FILE}"
  --h05-sample-summary-file "${H05_SAMPLE_SUMMARY_FILE}"
  --h05-global-audit-file "${H05_GLOBAL_AUDIT_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
  --expected-mapping-specs "${EXPECTED_MAPPING_SPECS}"
  --expected-analysis-specs "${EXPECTED_ANALYSIS_SPECS}"
  --expected-long-rows "${EXPECTED_LONG_ROWS}"
  --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
  --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --strict-primary-warnings "${STRICT_PRIMARY_WARNINGS}"
)

{
  echo
  echo "** Step 3: Run H06 Borusyak DiD"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_ml_cfun_static_effects.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_dynamic_effects.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_pretrend_checks.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_pretrend_summary.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_model_diagnostics.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_model_failures.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_analysis_support.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_event_support.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_support_policy.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_static.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_total_static.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_total_static_by_analysis.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_total_dynamic_by_analysis.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_qc.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_summary.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_run_metadata.csv"
  "${OUTPUT_DIR}/plots/quality_ml_cfun_total_static_by_analysis.pdf"
  "${OUTPUT_DIR}/plots/quality_ml_cfun_total_static_by_analysis.png"
  "${OUTPUT_DIR}/plots/quality_ml_cfun_primary_total_dynamic.pdf"
  "${OUTPUT_DIR}/plots/quality_ml_cfun_primary_total_dynamic.png"
)

{
  echo
  echo "** Step 4: Verify H06 output artifacts"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

QC_FILE="${OUTPUT_DIR}/quality_ml_cfun_qc.csv"
if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: H06 QC file contains one or more hard failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_static_effects.csv") - 1 ))"
DYNAMIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_dynamic_effects.csv") - 1 ))"
PRETREND_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_pretrend_checks.csv") - 1 ))"
PRIMARY_STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_primary_static.csv") - 1 ))"
PRIMARY_TOTAL_STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_primary_total_static.csv") - 1 ))"
PRIMARY_TOTAL_DYNAMIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv") - 1 ))"
ANALYSIS_SUPPORT_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_analysis_support.csv") - 1 ))"
EVENT_SUPPORT_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_ml_cfun_event_support.csv") - 1 ))"

if [[ "${STATIC_ROWS}" -ne 64 || \
      "${DYNAMIC_ROWS}" -ne 768 || \
      "${PRETREND_ROWS}" -ne 320 || \
      "${PRIMARY_STATIC_ROWS}" -ne 16 || \
      "${PRIMARY_TOTAL_STATIC_ROWS}" -ne 2 || \
      "${PRIMARY_TOTAL_DYNAMIC_ROWS}" -ne 24 || \
      "${ANALYSIS_SUPPORT_ROWS}" -ne 4 || \
      "${EVENT_SUPPORT_ROWS}" -ne 52 ]]; then
  echo "ERROR: unexpected H06 row counts: static=${STATIC_ROWS}, dynamic=${DYNAMIC_ROWS}, pretrend=${PRETREND_ROWS}, primary_static=${PRIMARY_STATIC_ROWS}, primary_total_static=${PRIMARY_TOTAL_STATIC_ROWS}, primary_total_dynamic=${PRIMARY_TOTAL_DYNAMIC_ROWS}, analysis_support=${ANALYSIS_SUPPORT_ROWS}, event_support=${EVENT_SUPPORT_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

RUN_STATUS="$(awk -F, '$1=="run" && $2=="status" {print $3}' "${OUTPUT_DIR}/quality_ml_cfun_summary.csv" | tr -d '\r\"')"
if [[ "${RUN_STATUS}" != "PASS" && "${RUN_STATUS}" != "PASS_WITH_ROBUSTNESS_MODEL_FAILURES" ]]; then
  echo "ERROR: unexpected H06 run status: ${RUN_STATUS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

ROBUSTNESS_FAILURES="$(awk -F, '$1=="models" && $2=="robustness_failure_jobs" {print $3}' "${OUTPUT_DIR}/quality_ml_cfun_summary.csv" | tr -d '\r\"')"
LOW_SUPPORT_SPECS="$(awk -F, '$1=="support" && $2=="low_support_analysis_specs" {print $3}' "${OUTPUT_DIR}/quality_ml_cfun_summary.csv" | tr -d '\r\"')"

{
  echo
  echo "============================================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Status:                          ${RUN_STATUS}"
  echo "Static effect rows:              ${STATIC_ROWS}"
  echo "Dynamic/placebo rows:            ${DYNAMIC_ROWS}"
  echo "Pretrend check rows:             ${PRETREND_ROWS}"
  echo "Primary static rows:             ${PRIMARY_STATIC_ROWS}"
  echo "Primary total static rows:       ${PRIMARY_TOTAL_STATIC_ROWS}"
  echo "Primary total dynamic rows:      ${PRIMARY_TOTAL_DYNAMIC_ROWS}"
  echo "Low-support configurations:      ${LOW_SUPPORT_SPECS}"
  echo "Robustness failed model jobs:    ${ROBUSTNESS_FAILURES}"
  echo "QC status:                       PASS"
  echo "Primary static results:          ${OUTPUT_DIR}/quality_ml_cfun_primary_total_static.csv"
  echo "Primary dynamic results:         ${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv"
  echo "All robustness static results:   ${OUTPUT_DIR}/quality_ml_cfun_total_static_by_analysis.csv"
  echo "Pretrend summary:                ${OUTPUT_DIR}/quality_ml_cfun_pretrend_summary.csv"
  echo "Model failures:                  ${OUTPUT_DIR}/quality_ml_cfun_model_failures.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
