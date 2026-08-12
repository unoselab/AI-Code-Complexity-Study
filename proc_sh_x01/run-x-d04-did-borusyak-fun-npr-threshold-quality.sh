#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-d04 v1: Borusyak DiD for frozen FUN-NPR quality burden
# ============================================================
#
# Purpose:
#   Run the threshold-specific Quality x FUN-NPR causal analysis prepared by
#   run-x-d03. The wrapper applies the validated run-x-b07 Borusyak logic to
#   every frozen threshold and both pre-specified sample definitions without
#   invoking any previous experiment wrapper.
#
# Primary input:
#   repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz
#
# Upstream provenance/QC inputs:
#   repo_x01/run-x-d03/quality_fun_npr_threshold_summary.csv
#   repo_x01/run-x-d03/quality_fun_npr_threshold_sample_summary.csv
#   repo_x01/run-x-d03/quality_fun_npr_threshold_global_audit.csv
#
# Analysis dimensions:
#   - 22 frozen FUN-NPR thresholds.
#   - 2 samples: full and pre-specified two-repository exclusion sensitivity.
#   - 2 model specifications: adjusted burden and FE-only burden.
#   - 8 selected-file unresolved SonarQube burden outcomes.
#
# Estimation:
#   - Borusyak did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic effects at event 0:+6.
#   - Placebo/pretrend terms at event -6:-2.
#   - Event -1 omitted.
#
# Sparse-support policy:
#   All frozen thresholds are still estimated. Support flags are descriptive;
#   they never remove a threshold after seeing causal estimates.
#
# Important output:
#   repo_x01/run-x-d04/quality_npr_primary_total_static.csv
#   repo_x01/run-x-d04/quality_npr_primary_total_dynamic.csv
#   repo_x01/run-x-d04/quality_npr_total_threshold_static.csv
#   repo_x01/run-x-d04/quality_npr_threshold_support.csv
#
# This file was derived by copying the validated run-x-b07 v2 shell wrapper and
# adapting its standalone execution/QC structure for the D04 threshold grid.
# It does not call the B07 wrapper.
#
# Run after deploying canonical script names:
#   bash proc_sh_x01/run-x-d04-did-borusyak-fun-npr-threshold-quality.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d04"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-fun-npr-threshold-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_fun_npr_threshold_quality.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz}"
D03_SUMMARY_FILE="${D03_SUMMARY_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_summary.csv}"
D03_SAMPLE_SUMMARY_FILE="${D03_SAMPLE_SUMMARY_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_sample_summary.csv}"
D03_GLOBAL_AUDIT_FILE="${D03_GLOBAL_AUDIT_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_global_audit.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.571637}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-22}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
EXPECTED_LONG_ROWS="${EXPECTED_LONG_ROWS:-85118}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
STRICT_PRIMARY_WARNINGS="${STRICT_PRIMARY_WARNINGS:-1}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" \
  "${INPUT_FILE}" \
  "${D03_SUMMARY_FILE}" \
  "${D03_SAMPLE_SUMMARY_FILE}" \
  "${D03_GLOBAL_AUDIT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" \
  "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_THRESHOLDS}" "${EXPECTED_SAMPLE_SPECS}" "${EXPECTED_LONG_ROWS}" \
  "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}" "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

for boolean_value in "${STRICT_EXPECTED_COUNTS}" "${STRICT_PRIMARY_WARNINGS}"; do
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: strict boolean options must be 0 or 1; observed: ${boolean_value}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

# Validate required R packages before the long threshold-grid analysis begins.
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
D03_SUMMARY_SHA256="$(sha256sum "${D03_SUMMARY_FILE}" | awk '{print $1}')"
D03_SAMPLE_SUMMARY_SHA256="$(sha256sum "${D03_SAMPLE_SUMMARY_FILE}" | awk '{print $1}')"
D03_GLOBAL_AUDIT_SHA256="$(sha256sum "${D03_GLOBAL_AUDIT_FILE}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: frozen-threshold Quality x FUN-NPR Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "D03 long panel:                  ${INPUT_FILE}"
  echo "D03 long panel SHA256:           ${INPUT_SHA256}"
  echo "D03 summary SHA256:              ${D03_SUMMARY_SHA256}"
  echo "D03 sample summary SHA256:       ${D03_SAMPLE_SUMMARY_SHA256}"
  echo "D03 global audit SHA256:         ${D03_GLOBAL_AUDIT_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Threshold specifications:        ${EXPECTED_THRESHOLDS}"
  echo "Sample specifications:           ${EXPECTED_SAMPLE_SPECS}"
  echo "Expected D03 long rows:          ${EXPECTED_LONG_ROWS}"
  echo "Model specs:                     adjusted_burden + fe_only_burden"
  echo "Burden outcomes:                 8"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Reported post-treatment terms:   0:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Sparse support flag:             min dynamic positive repos < ${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS} OR within-variation repos < ${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  echo "Sparse threshold omission:       none"
  echo "Density:                         not computed"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Strict primary warnings:         ${STRICT_PRIMARY_WARNINGS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run D04 structural self-test"
  echo "----------------------------------------------------------------------------"
  echo "Command: ${RSCRIPT_BIN} ${R_SCRIPT} --self-test"
  echo
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse D04 R program"
  echo "----------------------------------------------------------------------------"
  echo "Command: ${RSCRIPT_BIN} -e parse(file=...)"
  echo
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "invisible(parse(file='${R_SCRIPT}')); cat('R parse: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --d03-summary-file "${D03_SUMMARY_FILE}"
  --d03-sample-summary-file "${D03_SAMPLE_SUMMARY_FILE}"
  --d03-global-audit-file "${D03_GLOBAL_AUDIT_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --expected-thresholds "${EXPECTED_THRESHOLDS}"
  --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
  --expected-long-rows "${EXPECTED_LONG_ROWS}"
  --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
  --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --strict-primary-warnings "${STRICT_PRIMARY_WARNINGS}"
)

{
  echo
  echo "** Step 3: Run D04 frozen-threshold Borusyak DiD"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_npr_static_effects.csv"
  "${OUTPUT_DIR}/quality_npr_dynamic_effects.csv"
  "${OUTPUT_DIR}/quality_npr_pretrend_checks.csv"
  "${OUTPUT_DIR}/quality_npr_pretrend_summary.csv"
  "${OUTPUT_DIR}/quality_npr_model_diagnostics.csv"
  "${OUTPUT_DIR}/quality_npr_model_failures.csv"
  "${OUTPUT_DIR}/quality_npr_threshold_support.csv"
  "${OUTPUT_DIR}/quality_npr_event_support.csv"
  "${OUTPUT_DIR}/quality_npr_support_policy.csv"
  "${OUTPUT_DIR}/quality_npr_primary_threshold_static.csv"
  "${OUTPUT_DIR}/quality_npr_primary_total_static.csv"
  "${OUTPUT_DIR}/quality_npr_primary_total_dynamic.csv"
  "${OUTPUT_DIR}/quality_npr_total_threshold_static.csv"
  "${OUTPUT_DIR}/quality_npr_total_threshold_dynamic.csv"
  "${OUTPUT_DIR}/quality_npr_qc.csv"
  "${OUTPUT_DIR}/quality_npr_summary.csv"
  "${OUTPUT_DIR}/quality_npr_run_metadata.csv"
  "${OUTPUT_DIR}/plots/quality_npr_total_static_across_thresholds.pdf"
  "${OUTPUT_DIR}/plots/quality_npr_total_static_across_thresholds.png"
  "${OUTPUT_DIR}/plots/quality_npr_primary_total_dynamic.pdf"
  "${OUTPUT_DIR}/plots/quality_npr_primary_total_dynamic.png"
)

{
  echo
  echo "** Step 4: Verify D04 output artifacts"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/quality_npr_qc.csv"
if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: D04 QC file contains one or more hard failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_static_effects.csv") - 1 ))"
DYNAMIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_dynamic_effects.csv") - 1 ))"
PRETREND_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_pretrend_checks.csv") - 1 ))"
PRIMARY_STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_primary_threshold_static.csv") - 1 ))"
PRIMARY_TOTAL_STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_primary_total_static.csv") - 1 ))"
PRIMARY_TOTAL_DYNAMIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_primary_total_dynamic.csv") - 1 ))"
THRESHOLD_SUPPORT_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_threshold_support.csv") - 1 ))"
EVENT_SUPPORT_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/quality_npr_event_support.csv") - 1 ))"

if [[ "${STATIC_ROWS}" -ne 704 || \
      "${DYNAMIC_ROWS}" -ne 8448 || \
      "${PRETREND_ROWS}" -ne 3520 || \
      "${PRIMARY_STATIC_ROWS}" -ne 32 || \
      "${PRIMARY_TOTAL_STATIC_ROWS}" -ne 4 || \
      "${PRIMARY_TOTAL_DYNAMIC_ROWS}" -ne 48 || \
      "${THRESHOLD_SUPPORT_ROWS}" -ne 44 || \
      "${EVENT_SUPPORT_ROWS}" -ne 572 ]]; then
  echo "ERROR: unexpected D04 output row counts: static=${STATIC_ROWS}, dynamic=${DYNAMIC_ROWS}, pretrend=${PRETREND_ROWS}, primary_static=${PRIMARY_STATIC_ROWS}, primary_total_static=${PRIMARY_TOTAL_STATIC_ROWS}, primary_total_dynamic=${PRIMARY_TOTAL_DYNAMIC_ROWS}, threshold_support=${THRESHOLD_SUPPORT_ROWS}, event_support=${EVENT_SUPPORT_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

RUN_STATUS="$(awk -F, '$1=="run" && $2=="status" {print $3}' "${OUTPUT_DIR}/quality_npr_summary.csv" | tr -d '\r\"')"
if [[ "${RUN_STATUS}" != "PASS" && "${RUN_STATUS}" != "PASS_WITH_SPARSE_MODEL_FAILURES" ]]; then
  echo "ERROR: unexpected D04 run status: ${RUN_STATUS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

NONPRIMARY_FAILURES="$(awk -F, '$1=="models" && $2=="nonprimary_failure_jobs" {print $3}' "${OUTPUT_DIR}/quality_npr_summary.csv" | tr -d '\r\"')"
SPARSE_THRESHOLD_ROWS="$(awk -F, '$1=="support" && $2=="sparse_threshold_rows" {print $3}' "${OUTPUT_DIR}/quality_npr_summary.csv" | tr -d '\r\"')"

{
  echo
  echo "============================================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Status:                          ${RUN_STATUS}"
  echo "Static effect rows:              ${STATIC_ROWS}"
  echo "Dynamic/placebo rows:            ${DYNAMIC_ROWS}"
  echo "Pretrend check rows:             ${PRETREND_ROWS}"
  echo "Primary threshold static rows:   ${PRIMARY_STATIC_ROWS}"
  echo "Primary total static rows:       ${PRIMARY_TOTAL_STATIC_ROWS}"
  echo "Primary total dynamic rows:      ${PRIMARY_TOTAL_DYNAMIC_ROWS}"
  echo "Sparse support rows:             ${SPARSE_THRESHOLD_ROWS}"
  echo "Non-primary failed model jobs:   ${NONPRIMARY_FAILURES}"
  echo "QC status:                       PASS"
  echo "Primary static results:          ${OUTPUT_DIR}/quality_npr_primary_total_static.csv"
  echo "Primary dynamic results:         ${OUTPUT_DIR}/quality_npr_primary_total_dynamic.csv"
  echo "Threshold sensitivity:           ${OUTPUT_DIR}/quality_npr_total_threshold_static.csv"
  echo "Threshold support:               ${OUTPUT_DIR}/quality_npr_threshold_support.csv"
  echo "Model failures:                  ${OUTPUT_DIR}/quality_npr_model_failures.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            review primary/sensitivity estimates, pretrends, and sparse-threshold support"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
