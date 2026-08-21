#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-e03 v3: Recheck ML-localized quality -> future velocity
# ============================================================
#
# Purpose:
#   Recheck the E03-v2 null result without changing the frozen ML detector or
#   file-level selection threshold. This wrapper preserves E03-v2 outputs and
#   writes all recheck artifacts to repo_x01/run-x-e03-recheck.
#
# Inputs:
#   - D05 frozen ML-localized quality panel
#   - B06 authoritative whole-Python panel
#   - Frozen E03-v2 coefficient CSV for exact reference reproduction
#
# Rechecks:
#   R0 exact E03-v2 primary specification
#   R1 collapsed-instrument sensitivity
#   R2 one-step estimator sensitivity
#   R3 compact lag-2:3 instrument sensitivity
#   R4 no-contemporaneous-controls sensitivity
#
# Important:
#   The ML file rule remains strict weighted AGC share > 0.50. The recheck does
#   not sweep thresholds or select a specification based on statistical
#   significance.
#
# This wrapper is standalone. It was created from the validated E03-v2 wrapper
# structure but does not call any prior experiment shell wrapper.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-e03"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}-recheck"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml_recheck.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
REFERENCE_COEFFICIENTS_FILE="${REFERENCE_COEFFICIENTS_FILE:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_coefficients.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-e03-recheck}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-0.50}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_INPUT_ROWS="${EXPECTED_INPUT_ROWS:-7738}"
EXPECTED_FULL_ROWS="${EXPECTED_FULL_ROWS:-1954}"
EXPECTED_FULL_REPOSITORIES="${EXPECTED_FULL_REPOSITORIES:-167}"
EXPECTED_FULL_TREATMENT_REPOS="${EXPECTED_FULL_TREATMENT_REPOS:-63}"
EXPECTED_FULL_CONTROL_REPOS="${EXPECTED_FULL_CONTROL_REPOS:-104}"
EXPECTED_PRIMARY_SELECTED_FILE_ROWS="${EXPECTED_PRIMARY_SELECTED_FILE_ROWS:-43325}"
EXPECTED_PRIMARY_ISSUE_STOCK="${EXPECTED_PRIMARY_ISSUE_STOCK:-48478}"
EXPECTED_FULL_ACTIVE_ROWS="${EXPECTED_FULL_ACTIVE_ROWS:-1631}"
EXPECTED_FULL_ACTIVE_REPOSITORIES="${EXPECTED_FULL_ACTIVE_REPOSITORIES:-146}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-3}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in "${R_SCRIPT}" "${INPUT_FILE}" "${B06_PANEL_FILE}" "${REFERENCE_COEFFICIENTS_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${EXPECTED_INPUT_ROWS}" "${EXPECTED_FULL_ROWS}" "${EXPECTED_FULL_REPOSITORIES}" \
  "${EXPECTED_FULL_TREATMENT_REPOS}" "${EXPECTED_FULL_CONTROL_REPOS}" \
  "${EXPECTED_PRIMARY_SELECTED_FILE_ROWS}" "${EXPECTED_PRIMARY_ISSUE_STOCK}" \
  "${EXPECTED_FULL_ACTIVE_ROWS}" "${EXPECTED_FULL_ACTIVE_REPOSITORIES}" \
  "${EXPECTED_LEGACY_MISMATCH_ROWS}" "${EXPECTED_LEGACY_MISMATCH_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: expected a non-negative integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); suppressPackageStartupMessages(library(plm)); if (!exists("plm", mode="function", inherits=TRUE)) stop("plm() is not visible after package attachment"); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
B06_PANEL_SHA256="$(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"
REFERENCE_SHA256="$(sha256sum "${REFERENCE_COEFFICIENTS_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: ML GMM null-result recheck"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "D05 ML quality panel:            ${INPUT_FILE}"
  echo "D05 panel SHA256:                ${INPUT_SHA256}"
  echo "B06 panel:                       ${B06_PANEL_FILE}"
  echo "B06 panel SHA256:                ${B06_PANEL_SHA256}"
  echo "Reference E03-v2 coefficients:   ${REFERENCE_COEFFICIENTS_FILE}"
  echo "Reference SHA256:                ${REFERENCE_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Primary sample:                  full_sample + all_ml_files"
  echo "Frozen ML threshold:             strict > ${PRIMARY_THRESHOLD}"
  echo "Recheck specifications:          5"
  echo "Threshold sweep:                 NO"
  echo "Significance-based selection:    NO"
  echo "Expected source rows/repos:      ${EXPECTED_FULL_ROWS}/${EXPECTED_FULL_REPOSITORIES}"
  echo "Expected active rows/repos:      ${EXPECTED_FULL_ACTIVE_ROWS}/${EXPECTED_FULL_ACTIVE_REPOSITORIES}"
  echo "Reference tolerance:             ${REFERENCE_TOLERANCE}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --b06-panel-file "${B06_PANEL_FILE}"
  --reference-coefficients-file "${REFERENCE_COEFFICIENTS_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --reference-tolerance "${REFERENCE_TOLERANCE}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-input-rows "${EXPECTED_INPUT_ROWS}"
  --expected-full-rows "${EXPECTED_FULL_ROWS}"
  --expected-full-repositories "${EXPECTED_FULL_REPOSITORIES}"
  --expected-full-treatment-repos "${EXPECTED_FULL_TREATMENT_REPOS}"
  --expected-full-control-repos "${EXPECTED_FULL_CONTROL_REPOS}"
  --expected-primary-selected-file-rows "${EXPECTED_PRIMARY_SELECTED_FILE_ROWS}"
  --expected-primary-issue-stock "${EXPECTED_PRIMARY_ISSUE_STOCK}"
  --expected-full-active-rows "${EXPECTED_FULL_ACTIVE_ROWS}"
  --expected-full-active-repositories "${EXPECTED_FULL_ACTIVE_REPOSITORIES}"
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
  --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
)

{
  echo
  echo "** Step 1: Run E03 null-result robustness recheck"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_support_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_reference_reproduction.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_model_specifications.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_models.rds"
)

{
  echo
  echo "** Step 2: Verify recheck artifacts"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_qc.csv"
REFERENCE_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_reference_reproduction.csv"
PRIMARY_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_primary_summary.csv"
DIAGNOSTIC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_diagnostics.csv"
INSTRUMENT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_instrument_qc.csv"
SUPPORT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_support_diagnostics.csv"
METADATA_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_run_metadata.csv"
MODEL_RDS="${OUTPUT_DIR}/dynamic_panel_gmm_ml_recheck_models.rds"

FAILED_QC="$(${RSCRIPT_BIN} -e 'library(data.table); x<-fread(commandArgs(TRUE)[1]); cat(sum(x$status=="fail", na.rm=TRUE))' "${QC_FILE}")"
FAILED_REFERENCE="$(${RSCRIPT_BIN} -e 'library(data.table); x<-fread(commandArgs(TRUE)[1]); cat(sum(x$status!="pass", na.rm=TRUE))' "${REFERENCE_FILE}")"
if [[ "${FAILED_QC}" != "0" || "${FAILED_REFERENCE}" != "0" ]]; then
  echo "ERROR: E03 recheck verification failed: qc=${FAILED_QC}, reference=${FAILED_REFERENCE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 3: Recheck results"
  echo "------------------------------------------------------------"
  echo "Primary ML-quality coefficient across every prespecified recheck:"
  "${RSCRIPT_BIN}" -e 'library(data.table); x<-fread(commandArgs(TRUE)[1]); print(x)' "${PRIMARY_FILE}"
  echo
  echo "Support / variation diagnostics:"
  cat "${SUPPORT_FILE}"
  echo
  echo "GMM diagnostics:"
  cat "${DIAGNOSTIC_FILE}"
  echo
  echo "Instrument accounting:"
  cat "${INSTRUMENT_FILE}"
  echo
  echo "QC:"
  cat "${QC_FILE}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Interpretation policy:           report all 5 rechecks; do not select by p-value"
  echo "Frozen threshold:                ${PRIMARY_THRESHOLD} (unchanged)"
  echo "Primary summary:                 ${PRIMARY_FILE}"
  echo "Support diagnostics:             ${SUPPORT_FILE}"
  echo "Diagnostics:                     ${DIAGNOSTIC_FILE}"
  echo "Instrument QC:                   ${INSTRUMENT_FILE}"
  echo "Run metadata:                    ${METADATA_FILE}"
  echo "Models RDS:                      ${MODEL_RDS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
