#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-e03 v1: ML-localized quality -> future Python velocity GMM
# ============================================================
#
# Purpose:
#   Apply the validated E02 reverse-direction difference-GMM design to the
#   frozen D05 ML-localized quality burden. E03 estimates whether lagged issue
#   burden in ML-selected Python files predicts subsequent whole-Python
#   development velocity.
#
# Inputs:
#   - D05 frozen ML-localized repo-month panel:
#       repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz
#   - B06 authoritative whole-Python velocity/covariate panel:
#       repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Frozen ML contract:
#   - metric: file_ml_agc_share_space_by_token_weighted
#   - selection: strict metric > 0.50
#   - localized quality: log1p_selected_issue_total
#
# Analysis configurations:
#   - full_sample + all_ml_files (primary)
#   - full_sample + exclude_mapping_warning_files
#   - exclude_scope_mismatch_repos + all_ml_files
#   - exclude_scope_mismatch_repos + exclude_mapping_warning_files
#
# GMM model:
#   Velocity_t ~ Velocity_{t-1} + MLQuality_{t-1} + treatment_t + controls_t
#   Instrument: lag(Velocity, 2)
#   effect=twoways, model=twosteps, transformation=d, collapse=FALSE
#
# This wrapper was created from the validated E02 wrapper logic but is fully
# standalone and does not call any previous experiment shell wrapper.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-e03"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-0.50}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_INPUT_ROWS="${EXPECTED_INPUT_ROWS:-7738}"
EXPECTED_CONFIGURATIONS="${EXPECTED_CONFIGURATIONS:-4}"
EXPECTED_FULL_ROWS="${EXPECTED_FULL_ROWS:-1954}"
EXPECTED_FULL_REPOSITORIES="${EXPECTED_FULL_REPOSITORIES:-167}"
EXPECTED_FULL_TREATMENT_REPOS="${EXPECTED_FULL_TREATMENT_REPOS:-63}"
EXPECTED_FULL_CONTROL_REPOS="${EXPECTED_FULL_CONTROL_REPOS:-104}"
EXPECTED_SENSITIVITY_ROWS="${EXPECTED_SENSITIVITY_ROWS:-1915}"
EXPECTED_SENSITIVITY_REPOSITORIES="${EXPECTED_SENSITIVITY_REPOSITORIES:-165}"
EXPECTED_SENSITIVITY_TREATMENT_REPOS="${EXPECTED_SENSITIVITY_TREATMENT_REPOS:-62}"
EXPECTED_SENSITIVITY_CONTROL_REPOS="${EXPECTED_SENSITIVITY_CONTROL_REPOS:-103}"
EXPECTED_PRIMARY_SELECTED_FILE_ROWS="${EXPECTED_PRIMARY_SELECTED_FILE_ROWS:-43325}"
EXPECTED_PRIMARY_ISSUE_STOCK="${EXPECTED_PRIMARY_ISSUE_STOCK:-48478}"
EXPECTED_MAPPING_ISSUE_STOCK="${EXPECTED_MAPPING_ISSUE_STOCK:-45495}"
EXPECTED_SCOPE_SELECTED_FILE_ROWS="${EXPECTED_SCOPE_SELECTED_FILE_ROWS:-42999}"
EXPECTED_SCOPE_ISSUE_STOCK="${EXPECTED_SCOPE_ISSUE_STOCK:-47118}"
EXPECTED_FULL_ACTIVE_ROWS="${EXPECTED_FULL_ACTIVE_ROWS:-1631}"
EXPECTED_SENSITIVITY_ACTIVE_ROWS="${EXPECTED_SENSITIVITY_ACTIVE_ROWS:-1596}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-3}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in "${R_SCRIPT}" "${INPUT_FILE}" "${B06_PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${EXPECTED_INPUT_ROWS}" "${EXPECTED_CONFIGURATIONS}" \
  "${EXPECTED_FULL_ROWS}" "${EXPECTED_FULL_REPOSITORIES}" \
  "${EXPECTED_FULL_TREATMENT_REPOS}" "${EXPECTED_FULL_CONTROL_REPOS}" \
  "${EXPECTED_SENSITIVITY_ROWS}" "${EXPECTED_SENSITIVITY_REPOSITORIES}" \
  "${EXPECTED_SENSITIVITY_TREATMENT_REPOS}" "${EXPECTED_SENSITIVITY_CONTROL_REPOS}" \
  "${EXPECTED_PRIMARY_SELECTED_FILE_ROWS}" "${EXPECTED_PRIMARY_ISSUE_STOCK}" \
  "${EXPECTED_MAPPING_ISSUE_STOCK}" "${EXPECTED_SCOPE_SELECTED_FILE_ROWS}" \
  "${EXPECTED_SCOPE_ISSUE_STOCK}" "${EXPECTED_FULL_ACTIVE_ROWS}" \
  "${EXPECTED_SENSITIVITY_ACTIVE_ROWS}" "${EXPECTED_LEGACY_MISMATCH_ROWS}" \
  "${EXPECTED_LEGACY_MISMATCH_REPOS}"; do
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

{
  echo "============================================================"
  echo "${RUN_LABEL}: ML-localized quality -> future velocity GMM"
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
  echo "B06 velocity panel:              ${B06_PANEL_FILE}"
  echo "B06 velocity panel SHA256:       ${B06_PANEL_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Analysis scope:                  AGCDetector_ML localized quality"
  echo "ML metric:                       file_ml_agc_share_space_by_token_weighted"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Comparison operator:             strict >"
  echo "Localized quality:               log1p_selected_issue_total"
  echo "Velocity:                        log_lines_added_py_source"
  echo "Configurations:                  4 (primary + mapping + scope + combined)"
  echo "Treatment:                       normalized absorbing treatment"
  echo "Size control:                    log1p(ncloc_py_sonarqube)"
  echo "Estimator:                       two-step difference GMM, two-way effects"
  echo "Instrument:                      lag(velocity,2); collapse=FALSE"
  echo "Expected D05 rows:               ${EXPECTED_INPUT_ROWS}"
  echo "Expected full rows/repos:        ${EXPECTED_FULL_ROWS}/${EXPECTED_FULL_REPOSITORIES}"
  echo "Expected sensitivity rows/repos: ${EXPECTED_SENSITIVITY_ROWS}/${EXPECTED_SENSITIVITY_REPOSITORIES}"
  echo "Expected primary files/issues:   ${EXPECTED_PRIMARY_SELECTED_FILE_ROWS}/${EXPECTED_PRIMARY_ISSUE_STOCK}"
  echo "Confidence level:                ${CONFIDENCE_LEVEL}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --b06-panel-file "${B06_PANEL_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-input-rows "${EXPECTED_INPUT_ROWS}"
  --expected-configurations "${EXPECTED_CONFIGURATIONS}"
  --expected-full-rows "${EXPECTED_FULL_ROWS}"
  --expected-full-repositories "${EXPECTED_FULL_REPOSITORIES}"
  --expected-full-treatment-repos "${EXPECTED_FULL_TREATMENT_REPOS}"
  --expected-full-control-repos "${EXPECTED_FULL_CONTROL_REPOS}"
  --expected-sensitivity-rows "${EXPECTED_SENSITIVITY_ROWS}"
  --expected-sensitivity-repositories "${EXPECTED_SENSITIVITY_REPOSITORIES}"
  --expected-sensitivity-treatment-repos "${EXPECTED_SENSITIVITY_TREATMENT_REPOS}"
  --expected-sensitivity-control-repos "${EXPECTED_SENSITIVITY_CONTROL_REPOS}"
  --expected-primary-selected-file-rows "${EXPECTED_PRIMARY_SELECTED_FILE_ROWS}"
  --expected-primary-issue-stock "${EXPECTED_PRIMARY_ISSUE_STOCK}"
  --expected-mapping-issue-stock "${EXPECTED_MAPPING_ISSUE_STOCK}"
  --expected-scope-selected-file-rows "${EXPECTED_SCOPE_SELECTED_FILE_ROWS}"
  --expected-scope-issue-stock "${EXPECTED_SCOPE_ISSUE_STOCK}"
  --expected-full-active-rows "${EXPECTED_FULL_ACTIVE_ROWS}"
  --expected-sensitivity-active-rows "${EXPECTED_SENSITIVITY_ACTIVE_ROWS}"
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
  --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
)

{
  echo
  echo "** Step 1: Run ML-localized dynamic panel GMM"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_sample_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_model_specifications.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_configuration_input_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_numeric_coercion_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_calendar_gap_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_models.rds"
)

{
  echo
  echo "** Step 2: Verify output artifacts"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_qc.csv"
if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: E03 QC file contains one or more failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

COEFFICIENT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_coefficients.csv"
DIAGNOSTIC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_diagnostics.csv"
INSTRUMENT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_instrument_qc.csv"
SAMPLE_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_sample_qc.csv"
METADATA_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_run_metadata.csv"
MODEL_RDS="${OUTPUT_DIR}/dynamic_panel_gmm_ml_models.rds"

COEFFICIENT_ROWS="$(( $(wc -l < "${COEFFICIENT_FILE}") - 1 ))"
DIAGNOSTIC_ROWS="$(( $(wc -l < "${DIAGNOSTIC_FILE}") - 1 ))"
INSTRUMENT_ROWS="$(( $(wc -l < "${INSTRUMENT_FILE}") - 1 ))"
CAUTION_ROWS="$(awk -F',' 'NR>1 && $7=="caution" {n++} END {print n+0}' "${QC_FILE}")"

{
  echo
  echo "** Step 3: ML GMM primary/sensitivity results and diagnostics"
  echo "------------------------------------------------------------"
  echo "Lagged ML-quality coefficients:"
  awk -F',' 'NR==1 || $11=="TRUE" {print}' "${COEFFICIENT_FILE}"
  echo
  echo "GMM diagnostics:"
  cat "${DIAGNOSTIC_FILE}"
  echo
  echo "Instrument/sample accounting:"
  cat "${INSTRUMENT_FILE}"
  echo
  echo "QC:"
  cat "${QC_FILE}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Analysis scope:                  AGCDetector_ML localized quality -> velocity"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Coefficient rows:                ${COEFFICIENT_ROWS}"
  echo "Diagnostic rows:                 ${DIAGNOSTIC_ROWS}"
  echo "Instrument QC rows:              ${INSTRUMENT_ROWS}"
  echo "QC caution rows:                 ${CAUTION_ROWS}"
  echo "QC status:                       PASS (caution/informational rows may remain for review)"
  echo "Coefficients:                    ${COEFFICIENT_FILE}"
  echo "Diagnostics:                     ${DIAGNOSTIC_FILE}"
  echo "Sample QC:                       ${SAMPLE_FILE}"
  echo "Instrument QC:                   ${INSTRUMENT_FILE}"
  echo "Run metadata:                    ${METADATA_FILE}"
  echo "Models RDS:                      ${MODEL_RDS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
