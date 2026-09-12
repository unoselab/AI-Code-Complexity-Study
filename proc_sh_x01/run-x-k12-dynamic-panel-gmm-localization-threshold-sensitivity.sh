#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-k12 v2: Detector-localized threshold sweeps for dynamic-panel GMM
# ============================================================
#
# Purpose:
#   Estimate the association between lagged detector-localized issue burden
#   and subsequent whole-Python development velocity across prespecified
#   thresholds for both detectors and all three localization scopes:
#     NPR: RF, CM, RF+CM
#     ML:  RF, CM, RF+CM
#
# Inputs:
#   NPR threshold panels:
#     RF/CM  <- run-x-l03
#     RF+CM  <- run-x-l01-v2
#   ML threshold panels:
#     RF     <- run-x-d07
#     CM     <- run-x-h07
#     RF+CM  <- run-x-i08
#   Whole-Python velocity and covariates:
#     run-x-b06
#   Primary-threshold GMM references:
#     NPR    <- run-x-k11-v2
#     ML     <- run-x-e03, run-x-k06, and run-x-k08
#
# Outputs:
#   Detector/scope-specific coefficients, threshold summaries, GMM
#   diagnostics, instrument checks, support diagnostics, reproduction checks,
#   QC records, metadata, and fitted models. Combined CSV files are written at
#   the output root for subsequent table and figure generation.
#
# Statistical specification:
#   FECS only; two-step difference GMM with two-way effects,
#   lag(velocity, 2) instruments, and collapse=FALSE.
#
# Versioning:
#   The delivery files use -v2. Before running on the server, remove -v2 from
#   this wrapper and the R script, preserving the canonical paths below.
#
# Run:
#   bash proc_sh_x01/run-x-k12-dynamic-panel-gmm-localization-threshold-sensitivity.sh
#
# This wrapper is self-contained and does not invoke earlier experiment
# wrappers. It reuses their validated model specification and input artifacts.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-k12"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

LOG_DIR="${LOG_DIR:-logs/${RUN_PREFIX}}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-localization-threshold-sensitivity-${RUN_TS}.log}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/${RUN_PREFIX}/localization-threshold-gmm-v2}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_localization_threshold_sensitivity.R}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

# NPR RF and CM threshold inputs.
NPR_L03_ROOT="${NPR_L03_ROOT:-repo_x01/run-x-l03/npr-rf-cm-threshold-quality-burden-v1}"
NPR_L03_PANEL="${NPR_L03_PANEL:-${NPR_L03_ROOT}/quality_npr_rf_cm_threshold_repo_month_panel.csv.gz}"
NPR_L03_SUMMARY="${NPR_L03_SUMMARY:-${NPR_L03_ROOT}/quality_npr_rf_cm_threshold_summary.csv}"
NPR_L03_SAMPLE_SUMMARY="${NPR_L03_SAMPLE_SUMMARY:-${NPR_L03_ROOT}/quality_npr_rf_cm_threshold_sample_summary.csv}"
NPR_L03_GLOBAL_AUDIT="${NPR_L03_GLOBAL_AUDIT:-${NPR_L03_ROOT}/quality_npr_rf_cm_threshold_global_audit.csv}"

# NPR RF+CM threshold input.
NPR_L01_ROOT="${NPR_L01_ROOT:-repo_x01/run-x-l01/threshold-quality-burden-v2}"
NPR_L01_PANEL="${NPR_L01_PANEL:-${NPR_L01_ROOT}/quality_fun_cfun_npr_threshold_repo_month_panel.csv.gz}"
NPR_L01_SUMMARY="${NPR_L01_SUMMARY:-${NPR_L01_ROOT}/quality_fun_cfun_npr_threshold_summary.csv}"
NPR_L01_SAMPLE_SUMMARY="${NPR_L01_SAMPLE_SUMMARY:-${NPR_L01_ROOT}/quality_fun_cfun_npr_threshold_sample_summary.csv}"
NPR_L01_GLOBAL_AUDIT="${NPR_L01_GLOBAL_AUDIT:-${NPR_L01_ROOT}/quality_fun_cfun_npr_threshold_global_audit.csv}"

# ML RF threshold input.
ML_D07_ROOT="${ML_D07_ROOT:-repo_x01/run-x-d07}"
ML_D07_PANEL="${ML_D07_PANEL:-${ML_D07_ROOT}/quality_ml_threshold_repo_month_panel.csv.gz}"
ML_D07_SUMMARY="${ML_D07_SUMMARY:-${ML_D07_ROOT}/quality_ml_threshold_summary.csv}"
ML_D07_SAMPLE_SUMMARY="${ML_D07_SAMPLE_SUMMARY:-${ML_D07_ROOT}/quality_ml_threshold_sample_summary.csv}"
ML_D07_GLOBAL_AUDIT="${ML_D07_GLOBAL_AUDIT:-${ML_D07_ROOT}/quality_ml_threshold_global_audit.csv}"

# ML CM threshold input.
ML_H07_ROOT="${ML_H07_ROOT:-repo_x01/run-x-h07}"
ML_H07_PANEL="${ML_H07_PANEL:-${ML_H07_ROOT}/quality_ml_cfun_threshold_input_panel.csv.gz}"
ML_H07_SUMMARY="${ML_H07_SUMMARY:-${ML_H07_ROOT}/quality_ml_cfun_threshold_input_summary.csv}"
ML_H07_SAMPLE_SUMMARY="${ML_H07_SAMPLE_SUMMARY:-${ML_H07_ROOT}/quality_ml_cfun_threshold_input_sample_summary.csv}"
ML_H07_GLOBAL_AUDIT="${ML_H07_GLOBAL_AUDIT:-${ML_H07_ROOT}/quality_ml_cfun_threshold_input_global_audit.csv}"

# ML RF+CM threshold input.
ML_I08_ROOT="${ML_I08_ROOT:-repo_x01/run-x-i08}"
ML_I08_PANEL="${ML_I08_PANEL:-${ML_I08_ROOT}/quality_ml_fun_cfun_threshold_input_panel.csv.gz}"
ML_I08_SUMMARY="${ML_I08_SUMMARY:-${ML_I08_ROOT}/quality_ml_fun_cfun_threshold_input_summary.csv}"
ML_I08_SAMPLE_SUMMARY="${ML_I08_SAMPLE_SUMMARY:-${ML_I08_ROOT}/quality_ml_fun_cfun_threshold_input_sample_summary.csv}"
ML_I08_GLOBAL_AUDIT="${ML_I08_GLOBAL_AUDIT:-${ML_I08_ROOT}/quality_ml_fun_cfun_threshold_input_global_audit.csv}"

# Primary-threshold GMM references used for exact reproduction checks.
NPR_RF_REFERENCE="${NPR_RF_REFERENCE:-repo_x01/run-x-k11/npr-localization-gmm-v2/rf/dynamic_panel_gmm_npr_rf_coefficients.csv}"
NPR_CM_REFERENCE="${NPR_CM_REFERENCE:-repo_x01/run-x-k11/npr-localization-gmm-v2/cm/dynamic_panel_gmm_npr_cm_coefficients.csv}"
NPR_RF_CM_REFERENCE="${NPR_RF_CM_REFERENCE:-repo_x01/run-x-k11/npr-localization-gmm-v2/rf_cm/dynamic_panel_gmm_npr_rf_cm_coefficients.csv}"
ML_RF_REFERENCE="${ML_RF_REFERENCE:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_coefficients.csv}"
ML_CM_REFERENCE="${ML_CM_REFERENCE:-repo_x01/run-x-k06/dynamic_panel_gmm_ml_cm_coefficients.csv}"
ML_RF_CM_REFERENCE="${ML_RF_CM_REFERENCE:-repo_x01/run-x-k08/dynamic_panel_gmm_ml_rf_cm_coefficients.csv}"

NPR_PRIMARY_THRESHOLD="${NPR_PRIMARY_THRESHOLD:-1.515059}"
NPR_THRESHOLD_MIN="${NPR_THRESHOLD_MIN:-1.015059}"
NPR_THRESHOLD_MAX="${NPR_THRESHOLD_MAX:-2.015059}"
NPR_THRESHOLD_STEP="${NPR_THRESHOLD_STEP:-0.05}"
ML_PRIMARY_THRESHOLD="${ML_PRIMARY_THRESHOLD:-0.50}"
ML_THRESHOLD_MIN="${ML_THRESHOLD_MIN:-0.10}"
ML_THRESHOLD_MAX="${ML_THRESHOLD_MAX:-0.90}"
ML_THRESHOLD_STEP="${ML_THRESHOLD_STEP:-0.04}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_ROWS_PER_THRESHOLD="${EXPECTED_ROWS_PER_THRESHOLD:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"
EXPECTED_ACTIVE_TREATMENT_REPOSITORIES="${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES:-61}"
EXPECTED_ACTIVE_CONTROL_REPOSITORIES="${EXPECTED_ACTIVE_CONTROL_REPOSITORIES:-85}"
EXPECTED_MAIN_THRESHOLDS="${EXPECTED_MAIN_THRESHOLDS:-21}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  echo "ERROR: sha256sum is required." >&2
  exit 1
fi
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

REQUIRED_FILES=(
  "${R_SCRIPT}" "${B06_PANEL_FILE}"
  "${NPR_L03_PANEL}" "${NPR_L03_SUMMARY}" "${NPR_L03_SAMPLE_SUMMARY}" "${NPR_L03_GLOBAL_AUDIT}"
  "${NPR_L01_PANEL}" "${NPR_L01_SUMMARY}" "${NPR_L01_SAMPLE_SUMMARY}" "${NPR_L01_GLOBAL_AUDIT}"
  "${ML_D07_PANEL}" "${ML_D07_SUMMARY}" "${ML_D07_SAMPLE_SUMMARY}" "${ML_D07_GLOBAL_AUDIT}"
  "${ML_H07_PANEL}" "${ML_H07_SUMMARY}" "${ML_H07_SAMPLE_SUMMARY}" "${ML_H07_GLOBAL_AUDIT}"
  "${ML_I08_PANEL}" "${ML_I08_SUMMARY}" "${ML_I08_SAMPLE_SUMMARY}" "${ML_I08_GLOBAL_AUDIT}"
  "${NPR_RF_REFERENCE}" "${NPR_CM_REFERENCE}" "${NPR_RF_CM_REFERENCE}"
  "${ML_RF_REFERENCE}" "${ML_CM_REFERENCE}" "${ML_RF_CM_REFERENCE}"
)
for required_file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_ROOT}"

"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}'); cat('R parse: PASS\\n')"
PACKAGE_VERSIONS="$("${RSCRIPT_BIN}" -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "))')"
R_VERSION="$("${RSCRIPT_BIN}" -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: detector-localized GMM threshold sweeps"
  echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                  ${PROJECT_ROOT}"
  echo "R version:                     ${R_VERSION}"
  echo "R packages:                    ${PACKAGE_VERSIONS}"
  echo "R script:                      ${R_SCRIPT}"
  echo "R script SHA256:               ${R_SCRIPT_SHA256}"
  echo "B06 panel:                     ${B06_PANEL_FILE}"
  echo "NPR grid:                      ${NPR_THRESHOLD_MIN} to ${NPR_THRESHOLD_MAX} by ${NPR_THRESHOLD_STEP}"
  echo "ML grid:                       ${ML_THRESHOLD_MIN} to ${ML_THRESHOLD_MAX} by ${ML_THRESHOLD_STEP}"
  echo "Scopes:                        RF, CM, RF+CM"
  echo "Specification:                 FECS; two-step difference GMM; two-way effects"
  echo "Instrument:                    lag(velocity, 2); collapse=FALSE"
  echo "Output root:                   ${OUTPUT_ROOT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

run_sweep() {
  local detector="$1"
  local scope_id="$2"
  local scope_label="$3"
  local source_label="$4"
  local input_file="$5"
  local summary_file="$6"
  local sample_summary_file="$7"
  local global_audit_file="$8"
  local reference_file="$9"
  local primary_threshold="${10}"
  local threshold_min="${11}"
  local threshold_max="${12}"
  local threshold_step="${13}"
  local expected_long_rows="${14}"
  local expected_source_thresholds="${15}"
  local expected_primary_files="${16}"
  local expected_primary_issues="${17}"

  local scope_output="${OUTPUT_ROOT}/${detector}/${scope_id}"
  mkdir -p "${scope_output}"

  local command=(
    "${RSCRIPT_BIN}" "${R_SCRIPT}"
    --mode fit
    --detector "${detector}"
    --scope-id "${scope_id}"
    --scope-label "${scope_label}"
    --source-label "${source_label}"
    --input-file "${input_file}"
    --b06-panel-file "${B06_PANEL_FILE}"
    --source-summary-file "${summary_file}"
    --source-sample-summary-file "${sample_summary_file}"
    --source-global-audit-file "${global_audit_file}"
    --reference-coefficients-file "${reference_file}"
    --output-dir "${scope_output}"
    --script-path "${R_SCRIPT}"
    --implementation-version "${IMPLEMENTATION_VERSION}"
    --confidence-level "${CONFIDENCE_LEVEL}"
    --primary-threshold "${primary_threshold}"
    --threshold-min "${threshold_min}"
    --threshold-max "${threshold_max}"
    --threshold-step "${threshold_step}"
    --reference-tolerance "${REFERENCE_TOLERANCE}"
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
    --expected-long-rows "${expected_long_rows}"
    --expected-source-thresholds "${expected_source_thresholds}"
    --expected-sample-specs 2
    --expected-main-thresholds "${EXPECTED_MAIN_THRESHOLDS}"
    --expected-rows-per-threshold "${EXPECTED_ROWS_PER_THRESHOLD}"
    --expected-repositories "${EXPECTED_REPOSITORIES}"
    --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
    --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
    --expected-active-rows "${EXPECTED_ACTIVE_ROWS}"
    --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}"
    --expected-active-treatment-repositories "${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES}"
    --expected-active-control-repositories "${EXPECTED_ACTIVE_CONTROL_REPOSITORIES}"
    --expected-primary-selected-files "${expected_primary_files}"
    --expected-primary-issue-stock "${expected_primary_issues}"
  )

  {
    echo
    echo "** Detector/scope: ${detector^^} ${scope_label}"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"

  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"

  local prefix="dynamic_panel_gmm_${detector}_${scope_id}_threshold"
  local summary_output="${scope_output}/${prefix}_primary_summary.csv"
  local qc_output="${scope_output}/${prefix}_qc.csv"
  local reproduction_output="${scope_output}/${prefix}_primary_reproduction.csv"
  for output_file in "${summary_output}" "${qc_output}" "${reproduction_output}"; do
    if [[ ! -s "${output_file}" ]]; then
      echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
      exit 1
    fi
  done
  if grep -Eq ',fail(,|$)' "${qc_output}" || grep -Eq ',fail(,|$)' "${reproduction_output}"; then
    echo "ERROR: hard QC failure for ${detector^^} ${scope_label}." | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
}

# NPR uses the updated 1.515059 primary threshold and the prespecified
# primary +/- 0.50 grid in 0.05 increments. The two additional source-panel
# thresholds are retained upstream but excluded from the 21-point sweep.
run_sweep npr rf RF run-x-l03 \
  "${NPR_L03_PANEL}" "${NPR_L03_SUMMARY}" "${NPR_L03_SAMPLE_SUMMARY}" "${NPR_L03_GLOBAL_AUDIT}" \
  "${NPR_RF_REFERENCE}" "${NPR_PRIMARY_THRESHOLD}" "${NPR_THRESHOLD_MIN}" "${NPR_THRESHOLD_MAX}" "${NPR_THRESHOLD_STEP}" \
  88987 23 20388 31252

run_sweep npr cm CM run-x-l03 \
  "${NPR_L03_PANEL}" "${NPR_L03_SUMMARY}" "${NPR_L03_SAMPLE_SUMMARY}" "${NPR_L03_GLOBAL_AUDIT}" \
  "${NPR_CM_REFERENCE}" "${NPR_PRIMARY_THRESHOLD}" "${NPR_THRESHOLD_MIN}" "${NPR_THRESHOLD_MAX}" "${NPR_THRESHOLD_STEP}" \
  88987 23 13357 17806

run_sweep npr rf_cm RF+CM run-x-l01-v2 \
  "${NPR_L01_PANEL}" "${NPR_L01_SUMMARY}" "${NPR_L01_SAMPLE_SUMMARY}" "${NPR_L01_GLOBAL_AUDIT}" \
  "${NPR_RF_CM_REFERENCE}" "${NPR_PRIMARY_THRESHOLD}" "${NPR_THRESHOLD_MIN}" "${NPR_THRESHOLD_MAX}" "${NPR_THRESHOLD_STEP}" \
  88987 23 28385 28442

# ML uses the prespecified composition-threshold grid from 0.10 to 0.90 in
# 0.04 increments, including the primary threshold of 0.50.
run_sweep ml rf RF run-x-d07 \
  "${ML_D07_PANEL}" "${ML_D07_SUMMARY}" "${ML_D07_SAMPLE_SUMMARY}" "${ML_D07_GLOBAL_AUDIT}" \
  "${ML_RF_REFERENCE}" "${ML_PRIMARY_THRESHOLD}" "${ML_THRESHOLD_MIN}" "${ML_THRESHOLD_MAX}" "${ML_THRESHOLD_STEP}" \
  81249 21 43325 48478

run_sweep ml cm CM run-x-h07 \
  "${ML_H07_PANEL}" "${ML_H07_SUMMARY}" "${ML_H07_SAMPLE_SUMMARY}" "${ML_H07_GLOBAL_AUDIT}" \
  "${ML_CM_REFERENCE}" "${ML_PRIMARY_THRESHOLD}" "${ML_THRESHOLD_MIN}" "${ML_THRESHOLD_MAX}" "${ML_THRESHOLD_STEP}" \
  81249 21 37757 36432

run_sweep ml rf_cm RF+CM run-x-i08 \
  "${ML_I08_PANEL}" "${ML_I08_SUMMARY}" "${ML_I08_SAMPLE_SUMMARY}" "${ML_I08_GLOBAL_AUDIT}" \
  "${ML_RF_CM_REFERENCE}" "${ML_PRIMARY_THRESHOLD}" "${ML_THRESHOLD_MIN}" "${ML_THRESHOLD_MAX}" "${ML_THRESHOLD_STEP}" \
  81249 21 64153 35765

INPUT_DIRS="${OUTPUT_ROOT}/npr/rf;${OUTPUT_ROOT}/npr/cm;${OUTPUT_ROOT}/npr/rf_cm;${OUTPUT_ROOT}/ml/rf;${OUTPUT_ROOT}/ml/cm;${OUTPUT_ROOT}/ml/rf_cm"
COMBINE_COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --mode combine
  --input-dirs "${INPUT_DIRS}"
  --output-dir "${OUTPUT_ROOT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
)

{
  echo
  echo "** Combine detector/scope outputs"
  printf 'Command:'
  printf ' %q' "${COMBINE_COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMBINE_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

COMBINED_SUMMARY="${OUTPUT_ROOT}/dynamic_panel_gmm_localization_threshold_summary.csv"
COMBINED_QC="${OUTPUT_ROOT}/dynamic_panel_gmm_localization_threshold_qc.csv"
COMBINED_REPRODUCTION="${OUTPUT_ROOT}/dynamic_panel_gmm_localization_threshold_primary_reproduction.csv"
for output_file in "${COMBINED_SUMMARY}" "${COMBINED_QC}" "${COMBINED_REPRODUCTION}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected combined output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done
if grep -Eq ',fail(,|$)' "${COMBINED_QC}" || grep -Eq ',fail(,|$)' "${COMBINED_REPRODUCTION}"; then
  echo "ERROR: combined output contains a hard QC failure." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

SUMMARY_ROWS="$("${RSCRIPT_BIN}" -e 'x <- data.table::fread(commandArgs(TRUE)[1]); cat(nrow(x))' "${COMBINED_SUMMARY}")"
SUCCESSFUL_MODELS="$("${RSCRIPT_BIN}" -e 'x <- data.table::fread(commandArgs(TRUE)[1]); cat(sum(x$fit_status == "success", na.rm=TRUE))' "${COMBINED_SUMMARY}")"
FAILED_MODELS="$("${RSCRIPT_BIN}" -e 'x <- data.table::fread(commandArgs(TRUE)[1]); cat(sum(x$fit_status != "success", na.rm=TRUE))' "${COMBINED_SUMMARY}")"
CAUTION_ROWS="$("${RSCRIPT_BIN}" -e 'x <- data.table::fread(commandArgs(TRUE)[1]); cat(sum(x$status == "caution", na.rm=TRUE))' "${COMBINED_QC}")"

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Detector/scope sweeps:         6"
  echo "Threshold-summary rows:        ${SUMMARY_ROWS}"
  echo "Successful GMM models:         ${SUCCESSFUL_MODELS}"
  echo "Non-primary model failures:    ${FAILED_MODELS}"
  echo "QC caution rows:               ${CAUTION_ROWS}"
  echo "Combined summary:              ${COMBINED_SUMMARY}"
  echo "Combined diagnostics:          ${OUTPUT_ROOT}/dynamic_panel_gmm_localization_threshold_diagnostics.csv"
  echo "Combined support:              ${OUTPUT_ROOT}/dynamic_panel_gmm_localization_threshold_support_diagnostics.csv"
  echo "Combined QC:                   ${COMBINED_QC}"
  echo "Output root:                   ${OUTPUT_ROOT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
