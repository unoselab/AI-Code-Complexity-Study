#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-k10 v1: ML RF+CM threshold-sensitivity dynamic-panel GMM
# ============================================================
#
# Purpose:
#   Fit the same reverse-direction quality -> velocity GMM at every threshold
#   in the prespecified I08 21-point ML grid.
#
# Inputs:
#   - I08 long threshold quality panel and provenance/QC summaries
#   - B06 authoritative velocity/covariate panel
#   - K08 coefficient output for exact primary-threshold reproduction
#
# Outputs:
#   - One-row-per-threshold coefficient summary for G07 plotting
#   - Full coefficient, diagnostic, instrument, support, QC, and provenance data
#   - RDS models for all thresholds that fit successfully
#
# Important:
#   This wrapper is derived from the validated K08 ML GMM and E03 threshold-
#   sensitivity wrappers, but it is self-contained and does not call them.
#   The I08 prespecified 0.10--0.90 ML threshold grid is not part of the 21-point main sweep.
#
# Versioned delivery files:
#   proc_script_x01/dynamic_panel_gmm_ml_rf_cm_threshold_sensitivity-v1.R
#   proc_sh_x01/run-x-k10-dynamic-panel-gmm-ml-rf-cm-threshold-sensitivity-v1.sh
#
# Canonical server filenames after deployment:
#   proc_script_x01/dynamic_panel_gmm_ml_rf_cm_threshold_sensitivity.R
#   proc_sh_x01/run-x-k10-dynamic-panel-gmm-ml-rf-cm-threshold-sensitivity.sh
#
# Run:
#   bash proc_sh_x01/run-x-k10-dynamic-panel-gmm-ml-rf-cm-threshold-sensitivity.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-k10"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-rf-cm-threshold-sensitivity-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml_rf_cm_threshold_sensitivity.R}"
I08_PANEL="${I08_PANEL:-repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_panel.csv.gz}"
I08_SUMMARY="${I08_SUMMARY:-repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_summary.csv}"
I08_SAMPLE_SUMMARY="${I08_SAMPLE_SUMMARY:-repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_sample_summary.csv}"
I08_GLOBAL_AUDIT="${I08_GLOBAL_AUDIT:-repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_global_audit.csv}"
B06_PANEL="${B06_PANEL:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
K08_REFERENCE_COEFFICIENTS="${K08_REFERENCE_COEFFICIENTS:-repo_x01/run-x-k08/dynamic_panel_gmm_ml_rf_cm_coefficients.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-k10}"

PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-0.50}"
THRESHOLD_MIN="${THRESHOLD_MIN:-0.10}"
THRESHOLD_MAX="${THRESHOLD_MAX:-0.90}"
THRESHOLD_STEP="${THRESHOLD_STEP:-0.04}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_I08_SHA256="${EXPECTED_I08_SHA256:-}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_LONG_ROWS="${EXPECTED_LONG_ROWS:-81249}"
EXPECTED_I08_THRESHOLDS="${EXPECTED_I08_THRESHOLDS:-21}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
EXPECTED_MAIN_THRESHOLDS="${EXPECTED_MAIN_THRESHOLDS:-21}"
EXPECTED_ROWS_PER_THRESHOLD="${EXPECTED_ROWS_PER_THRESHOLD:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"
EXPECTED_ACTIVE_TREATMENT_REPOSITORIES="${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES:-61}"
EXPECTED_ACTIVE_CONTROL_REPOSITORIES="${EXPECTED_ACTIVE_CONTROL_REPOSITORIES:-85}"
EXPECTED_PRIMARY_SELECTED_FILES="${EXPECTED_PRIMARY_SELECTED_FILES:-64153}"
EXPECTED_PRIMARY_ISSUE_STOCK="${EXPECTED_PRIMARY_ISSUE_STOCK:-35765}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOSITORIES="${EXPECTED_LEGACY_MISMATCH_REPOSITORIES:-3}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  echo "ERROR: sha256sum is required." >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" "${I08_PANEL}" "${I08_SUMMARY}" "${I08_SAMPLE_SUMMARY}" \
  "${I08_GLOBAL_AUDIT}" "${B06_PANEL}" "${K08_REFERENCE_COEFFICIENTS}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

I08_SHA256="$(sha256sum "${I08_PANEL}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_PANEL}" | awk '{print $1}')"
if [[ -n "${EXPECTED_I08_SHA256}" && "${I08_SHA256}" != "${EXPECTED_I08_SHA256}" ]]; then
  echo "ERROR: I08 SHA256 mismatch." >&2
  echo "Expected: ${EXPECTED_I08_SHA256}" >&2
  echo "Observed: ${I08_SHA256}" >&2
  exit 1
fi
if [[ "${B06_SHA256}" != "${EXPECTED_B06_SHA256}" ]]; then
  echo "ERROR: B06 SHA256 mismatch." >&2
  echo "Expected: ${EXPECTED_B06_SHA256}" >&2
  echo "Observed: ${B06_SHA256}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

# Parse the new R source before estimation. This catches syntax errors before
# any output is overwritten.
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}'); cat('R parse: PASS\\n')"

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); suppressPackageStartupMessages(library(plm)); if (!exists("plm", mode="function", inherits=TRUE)) stop("plm() is not visible after package attachment"); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
I08_SUMMARY_SHA256="$(sha256sum "${I08_SUMMARY}" | awk '{print $1}')"
I08_SAMPLE_SUMMARY_SHA256="$(sha256sum "${I08_SAMPLE_SUMMARY}" | awk '{print $1}')"
I08_GLOBAL_AUDIT_SHA256="$(sha256sum "${I08_GLOBAL_AUDIT}" | awk '{print $1}')"
K08_REFERENCE_SHA256="$(sha256sum "${K08_REFERENCE_COEFFICIENTS}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: ML RF+CM threshold-sensitivity quality -> velocity GMM"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Experiment role:                 21-threshold ML RF+CM GMM sweep"
  echo "Localization scope:              RF+CM (jointly recomputed)"
  echo "Sample:                          full_sample only"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Main threshold range:            1.071637 to 2.071637"
  echo "Threshold increment:             ${THRESHOLD_STEP}"
  echo "Main thresholds:                 ${EXPECTED_MAIN_THRESHOLDS}"
  echo "Threshold selection by p-value:  NO"
  echo "Comparison operator:             strict >"
  echo "Threshold selection by p-value:  NO"
  echo "I08 threshold panel:             ${I08_PANEL}"
  echo "I08 SHA256:                      ${I08_SHA256}"
  echo "B06 panel:                       ${B06_PANEL}"
  echo "B06 SHA256:                      ${B06_SHA256}"
  echo "I08 summary SHA256:              ${I08_SUMMARY_SHA256}"
  echo "I08 sample summary SHA256:       ${I08_SAMPLE_SUMMARY_SHA256}"
  echo "I08 global audit SHA256:         ${I08_GLOBAL_AUDIT_SHA256}"
  echo "K08 primary reproduction ref:    ${K08_REFERENCE_COEFFICIENTS}"
  echo "K08 reference SHA256:            ${K08_REFERENCE_SHA256}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Estimator:                       two-step difference GMM, two-way effects"
  echo "Instrument:                      lag(velocity,2); collapse=FALSE"
  echo "Expected source rows/threshold:  ${EXPECTED_ROWS_PER_THRESHOLD}"
  echo "Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}"
  echo "Primary selected files/issues:   ${EXPECTED_PRIMARY_SELECTED_FILES}/${EXPECTED_PRIMARY_ISSUE_STOCK}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --input-file "${I08_PANEL}"
  --b06-panel-file "${B06_PANEL}"
  --i08-summary-file "${I08_SUMMARY}"
  --i08-sample-summary-file "${I08_SAMPLE_SUMMARY}"
  --i08-global-audit-file "${I08_GLOBAL_AUDIT}"
  --k08-reference-coefficients-file "${K08_REFERENCE_COEFFICIENTS}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --threshold-min "${THRESHOLD_MIN}"
  --threshold-max "${THRESHOLD_MAX}"
  --threshold-step "${THRESHOLD_STEP}"
  --reference-tolerance "${REFERENCE_TOLERANCE}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-long-rows "${EXPECTED_LONG_ROWS}"
  --expected-i08-thresholds "${EXPECTED_I08_THRESHOLDS}"
  --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
  --expected-main-thresholds "${EXPECTED_MAIN_THRESHOLDS}"
  --expected-rows-per-threshold "${EXPECTED_ROWS_PER_THRESHOLD}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-active-rows "${EXPECTED_ACTIVE_ROWS}"
  --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}"
  --expected-active-treatment-repositories "${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES}"
  --expected-active-control-repositories "${EXPECTED_ACTIVE_CONTROL_REPOSITORIES}"
  --expected-primary-selected-files "${EXPECTED_PRIMARY_SELECTED_FILES}"
  --expected-primary-issue-stock "${EXPECTED_PRIMARY_ISSUE_STOCK}"
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
  --expected-legacy-mismatch-repositories "${EXPECTED_LEGACY_MISMATCH_REPOSITORIES}"
)

{
  echo
  echo "** Step 1: Fit identical reverse GMM across the 21-point ML grid"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_support_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_input_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_calendar_gap_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_k08_reproduction.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_model_failures.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_models.rds"
)

{
  echo
  echo "** Step 2: Verify K10 artifacts and hard QC"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_qc.csv"
REPRO_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_k08_reproduction.csv"
SUMMARY_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_primary_summary.csv"
FAILURE_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_model_failures.csv"

if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: K10 QC contains one or more hard failures." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if grep -q ',fail$' "${REPRO_FILE}" || grep -q ',fail,' "${REPRO_FILE}"; then
  echo "ERROR: K10 primary threshold does not reproduce K08." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

SUMMARY_ROWS="$(${RSCRIPT_BIN} -e 'x <- data.table::fread(commandArgs(trailingOnly=TRUE)[1]); cat(nrow(x))' "${SUMMARY_FILE}")"
if [[ "${SUMMARY_ROWS}" != "${EXPECTED_MAIN_THRESHOLDS}" ]]; then
  echo "ERROR: expected ${EXPECTED_MAIN_THRESHOLDS} K10 threshold-summary rows; observed ${SUMMARY_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 3: Show threshold GMM summary"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

"${RSCRIPT_BIN}" -e '
  args <- commandArgs(trailingOnly=TRUE)
  x <- data.table::fread(args[[1]])
  cols <- c("threshold","primary_analysis","fit_status","estimate","std_error","conf_low","conf_high","p_value","selected_file_rows","selected_issue_total","zero_issue_share_active","repositories_with_within_quality_variation_active")
  print(x[, ..cols])
' "${SUMMARY_FILE}" 2>&1 | tee -a "${LOG_FILE}"

CAUTION_ROWS="$(${RSCRIPT_BIN} -e 'x <- data.table::fread(commandArgs(trailingOnly=TRUE)[1]); cat(sum(x$status=="caution", na.rm=TRUE))' "${QC_FILE}")"
FAILED_MODELS="$(${RSCRIPT_BIN} -e 'x <- data.table::fread(commandArgs(trailingOnly=TRUE)[1]); cat(nrow(x))' "${FAILURE_FILE}")"
SUCCESSFUL_MODELS="$(${RSCRIPT_BIN} -e 'x <- data.table::fread(commandArgs(trailingOnly=TRUE)[1]); cat(sum(x$fit_status=="success", na.rm=TRUE))' "${SUMMARY_FILE}")"

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Main thresholds reported:        ${SUMMARY_ROWS}"
  echo "Successful GMM models:           ${SUCCESSFUL_MODELS}"
  echo "Non-primary model failures:      ${FAILED_MODELS}"
  echo "QC caution rows:                 ${CAUTION_ROWS}"
  echo "Primary K08 reproduction:        PASS"
  echo "Primary summary:                 ${SUMMARY_FILE}"
  echo "Support diagnostics:             ${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_support_diagnostics.csv"
  echo "GMM diagnostics:                 ${OUTPUT_DIR}/dynamic_panel_gmm_ml_rf_cm_threshold_diagnostics.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
