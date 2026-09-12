#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-k11 v2: Dynamic-panel GMM for NPR localization scopes
# ============================================================
#
# Purpose:
#   Estimate the association between lagged NPR-localized issue burden and
#   subsequent whole-Python development velocity for RF, CM, and RF+CM.
#
# Inputs:
#   RF and CM:
#     repo_x01/run-x-l03/npr-rf-cm-threshold-quality-burden-v1/
#   RF+CM:
#     repo_x01/run-x-l01/threshold-quality-burden-v2/
#   Velocity and covariates:
#     repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Outputs:
#   Scope-specific coefficients, diagnostics, sample checks, instrument checks,
#   provenance records, and fitted models under repo_x01/run-x-k11/.
#   Combined coefficient and diagnostic tables are also created.
#
# Versioning:
#   The distributed files use -v2. Before execution on the server, remove the
#   version suffix from this wrapper and the R script.
#
# Run:
#   bash proc_sh_x01/run-x-k11-dynamic-panel-gmm-npr-localization.sh
#
# This wrapper is self-contained and does not invoke earlier experiment
# wrappers. The R analysis preserves the validated K02/K04 GMM specification.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-k11"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

LOG_DIR="${LOG_DIR:-logs/${RUN_PREFIX}}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-npr-localization-${RUN_TS}.log}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/${RUN_PREFIX}/npr-localization-gmm-v2}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_npr_localization.R}"

L03_ROOT="${L03_ROOT:-repo_x01/run-x-l03/npr-rf-cm-threshold-quality-burden-v1}"
L03_PANEL_FILE="${L03_PANEL_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_repo_month_panel.csv.gz}"
L03_SUMMARY_FILE="${L03_SUMMARY_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_summary.csv}"
L03_SAMPLE_SUMMARY_FILE="${L03_SAMPLE_SUMMARY_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_sample_summary.csv}"
L03_GLOBAL_AUDIT_FILE="${L03_GLOBAL_AUDIT_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_global_audit.csv}"

L01_ROOT="${L01_ROOT:-repo_x01/run-x-l01/threshold-quality-burden-v2}"
L01_PANEL_FILE="${L01_PANEL_FILE:-${L01_ROOT}/quality_fun_cfun_npr_threshold_repo_month_panel.csv.gz}"
L01_SUMMARY_FILE="${L01_SUMMARY_FILE:-${L01_ROOT}/quality_fun_cfun_npr_threshold_summary.csv}"
L01_SAMPLE_SUMMARY_FILE="${L01_SAMPLE_SUMMARY_FILE:-${L01_ROOT}/quality_fun_cfun_npr_threshold_sample_summary.csv}"
L01_GLOBAL_AUDIT_FILE="${L01_GLOBAL_AUDIT_FILE:-${L01_ROOT}/quality_fun_cfun_npr_threshold_global_audit.csv}"

B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.515059}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_LONG_ROWS_PER_SCOPE="${EXPECTED_LONG_ROWS_PER_SCOPE:-88987}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-23}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"

EXPECTED_FULL_ROWS="${EXPECTED_FULL_ROWS:-1954}"
EXPECTED_FULL_REPOSITORIES="${EXPECTED_FULL_REPOSITORIES:-167}"
EXPECTED_FULL_TREATMENT_REPOS="${EXPECTED_FULL_TREATMENT_REPOS:-63}"
EXPECTED_FULL_CONTROL_REPOS="${EXPECTED_FULL_CONTROL_REPOS:-104}"

EXPECTED_SENSITIVITY_ROWS="${EXPECTED_SENSITIVITY_ROWS:-1915}"
EXPECTED_SENSITIVITY_REPOSITORIES="${EXPECTED_SENSITIVITY_REPOSITORIES:-165}"
EXPECTED_SENSITIVITY_TREATMENT_REPOS="${EXPECTED_SENSITIVITY_TREATMENT_REPOS:-62}"
EXPECTED_SENSITIVITY_CONTROL_REPOS="${EXPECTED_SENSITIVITY_CONTROL_REPOS:-103}"

EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-3}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" \
  "${L03_PANEL_FILE}" "${L03_SUMMARY_FILE}" "${L03_SAMPLE_SUMMARY_FILE}" "${L03_GLOBAL_AUDIT_FILE}" \
  "${L01_PANEL_FILE}" "${L01_SUMMARY_FILE}" "${L01_SAMPLE_SUMMARY_FILE}" "${L01_GLOBAL_AUDIT_FILE}" \
  "${B06_PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for boolean_name in STRICT_EXPECTED_COUNTS; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1; observed ${boolean_value}." >&2
    exit 1
  fi
done

if [[ ! "${PRIMARY_THRESHOLD}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: PRIMARY_THRESHOLD must be numeric; observed ${PRIMARY_THRESHOLD}." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_ROOT}"

PACKAGE_VERSIONS="$("${RSCRIPT_BIN}" -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "))')"
R_VERSION="$("${RSCRIPT_BIN}" -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: NPR-localized quality -> subsequent velocity GMM"
  echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                  ${PROJECT_ROOT}"
  echo "R version:                     ${R_VERSION}"
  echo "R packages:                    ${PACKAGE_VERSIONS}"
  echo "R script:                      ${R_SCRIPT}"
  echo "R script SHA256:               ${R_SCRIPT_SHA256}"
  echo "L03 RF/CM panel:               ${L03_PANEL_FILE}"
  echo "L01 RF+CM panel:               ${L01_PANEL_FILE}"
  echo "B06 velocity panel:            ${B06_PANEL_FILE}"
  echo "Primary threshold:             ${PRIMARY_THRESHOLD}"
  echo "Comparison operator:           strict >"
  echo "Confidence level:              ${CONFIDENCE_LEVEL}"
  echo "Strict expected counts:        ${STRICT_EXPECTED_COUNTS}"
  echo "Output root:                   ${OUTPUT_ROOT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

run_scope() {
  local scope_id="$1"
  local scope_label="$2"
  local npr_metric="$3"
  local source_label="$4"
  local input_file="$5"
  local summary_file="$6"
  local sample_summary_file="$7"
  local global_audit_file="$8"
  local expected_full_files="$9"
  local expected_full_issues="${10}"
  local expected_sensitivity_files="${11}"
  local expected_sensitivity_issues="${12}"

  local scope_output="${OUTPUT_ROOT}/${scope_id}"
  mkdir -p "${scope_output}"

  local command=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --input-file "${input_file}"
    --b06-panel-file "${B06_PANEL_FILE}"
    --source-summary-file "${summary_file}"
    --source-sample-summary-file "${sample_summary_file}"
    --source-global-audit-file "${global_audit_file}"
    --output-dir "${scope_output}"
    --scope-id "${scope_id}"
    --scope-label "${scope_label}"
    --npr-metric "${npr_metric}"
    --source-label "${source_label}"
    --script-path "${R_SCRIPT}"
    --implementation-version "${IMPLEMENTATION_VERSION}"
    --confidence-level "${CONFIDENCE_LEVEL}"
    --primary-threshold "${PRIMARY_THRESHOLD}"
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
    --expected-long-rows "${EXPECTED_LONG_ROWS_PER_SCOPE}"
    --expected-thresholds "${EXPECTED_THRESHOLDS}"
    --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
    --expected-full-rows "${EXPECTED_FULL_ROWS}"
    --expected-full-repositories "${EXPECTED_FULL_REPOSITORIES}"
    --expected-full-treatment-repos "${EXPECTED_FULL_TREATMENT_REPOS}"
    --expected-full-control-repos "${EXPECTED_FULL_CONTROL_REPOS}"
    --expected-sensitivity-rows "${EXPECTED_SENSITIVITY_ROWS}"
    --expected-sensitivity-repositories "${EXPECTED_SENSITIVITY_REPOSITORIES}"
    --expected-sensitivity-treatment-repos "${EXPECTED_SENSITIVITY_TREATMENT_REPOS}"
    --expected-sensitivity-control-repos "${EXPECTED_SENSITIVITY_CONTROL_REPOS}"
    --expected-primary-full-selected-files "${expected_full_files}"
    --expected-primary-full-issue-stock "${expected_full_issues}"
    --expected-primary-sensitivity-selected-files "${expected_sensitivity_files}"
    --expected-primary-sensitivity-issue-stock "${expected_sensitivity_issues}"
    --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
    --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
  )

  {
    echo
    echo "** Scope: ${scope_label}"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"

  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"

  local qc_file="${scope_output}/dynamic_panel_gmm_npr_${scope_id}_qc.csv"
  local coefficient_file="${scope_output}/dynamic_panel_gmm_npr_${scope_id}_coefficients.csv"
  local diagnostic_file="${scope_output}/dynamic_panel_gmm_npr_${scope_id}_diagnostics.csv"

  for output_file in "${qc_file}" "${coefficient_file}" "${diagnostic_file}"; do
    if [[ ! -s "${output_file}" ]]; then
      echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
      exit 1
    fi
  done

  if grep -Eq ',fail(,|$)' "${qc_file}"; then
    echo "ERROR: QC failure detected for scope ${scope_label}." | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
}

run_scope \
  rf RF file_npr_fun_space_by_token_weighted run-x-l03 \
  "${L03_PANEL_FILE}" "${L03_SUMMARY_FILE}" "${L03_SAMPLE_SUMMARY_FILE}" "${L03_GLOBAL_AUDIT_FILE}" \
  20388 31252 20236 31030

run_scope \
  cm CM file_npr_cfun_space_by_token_weighted run-x-l03 \
  "${L03_PANEL_FILE}" "${L03_SUMMARY_FILE}" "${L03_SAMPLE_SUMMARY_FILE}" "${L03_GLOBAL_AUDIT_FILE}" \
  13357 17806 13106 17710

run_scope \
  rf_cm RF+CM file_npr_fun_cfun_space_by_token_weighted run-x-l01-v2 \
  "${L01_PANEL_FILE}" "${L01_SUMMARY_FILE}" "${L01_SAMPLE_SUMMARY_FILE}" "${L01_GLOBAL_AUDIT_FILE}" \
  28385 28442 28049 28305

combine_csv() {
  local output_file="$1"
  shift
  awk 'FNR == 1 && NR != 1 {next} {print}' "$@" > "${output_file}"
}

combine_csv \
  "${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_coefficients.csv" \
  "${OUTPUT_ROOT}/rf/dynamic_panel_gmm_npr_rf_coefficients.csv" \
  "${OUTPUT_ROOT}/cm/dynamic_panel_gmm_npr_cm_coefficients.csv" \
  "${OUTPUT_ROOT}/rf_cm/dynamic_panel_gmm_npr_rf_cm_coefficients.csv"

combine_csv \
  "${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_diagnostics.csv" \
  "${OUTPUT_ROOT}/rf/dynamic_panel_gmm_npr_rf_diagnostics.csv" \
  "${OUTPUT_ROOT}/cm/dynamic_panel_gmm_npr_cm_diagnostics.csv" \
  "${OUTPUT_ROOT}/rf_cm/dynamic_panel_gmm_npr_rf_cm_diagnostics.csv"

combine_csv \
  "${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_instrument_qc.csv" \
  "${OUTPUT_ROOT}/rf/dynamic_panel_gmm_npr_rf_instrument_qc.csv" \
  "${OUTPUT_ROOT}/cm/dynamic_panel_gmm_npr_cm_instrument_qc.csv" \
  "${OUTPUT_ROOT}/rf_cm/dynamic_panel_gmm_npr_rf_cm_instrument_qc.csv"

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Scopes:                        RF, CM, RF+CM"
  echo "Primary threshold:             ${PRIMARY_THRESHOLD}"
  echo "Combined coefficients:         ${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_coefficients.csv"
  echo "Combined diagnostics:          ${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_diagnostics.csv"
  echo "Combined instrument QC:        ${OUTPUT_ROOT}/dynamic_panel_gmm_npr_localization_instrument_qc.csv"
  echo "Output root:                   ${OUTPUT_ROOT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
