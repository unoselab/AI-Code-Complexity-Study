#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-g08 v2: ML file-composition threshold sensitivity GMM
# ============================================================
#
# Purpose:
#   Re-estimate the reverse quality -> velocity dynamic-panel GMM across 21
#   strict file-level ML AGC composition cutoffs from 0.10 to 0.90 by 0.04.
#
# Important distinction:
#   This experiment does NOT change the frozen function-level SVM decision
#   boundary. It varies only the downstream file-level token-weighted AGC-share
#   cutoff used to define the selected Python-file quality burden.
#
# Pipeline:
#   1. Copy the validated A04/D02/D05 aggregation logic into a standalone G08
#      input builder and construct zero-inclusive repo-month burdens at all 21
#      file-composition cutoffs.
#   2. Require strict >0.50 to reproduce D05 exactly.
#   3. Fit the same E03-v2 two-step difference GMM at every cutoff.
#   4. Require the 0.50 coefficient/SE/p-value to reproduce E03-v2 exactly.
#
# Inputs:
#   A04 continuous file-level ML AGC share
#   D02 canonical file-level SonarQube issue burden
#   B06 authoritative repo-month velocity/covariate panel
#   D05 primary >0.50 localized-quality reference
#   E03-v2 primary ML GMM coefficient reference
#
# Outputs:
#   repo_x01/run-x-g08/
#
# This wrapper is self-contained and does not invoke any prior shell wrapper.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-g08"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-threshold-sensitivity-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
BUILDER_SCRIPT="${BUILDER_SCRIPT:-proc_script_x01/prepare_ml_threshold_sensitivity_gmm_input.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml_threshold_sensitivity.R}"

A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
E03_REFERENCE_COEFFICIENTS="${E03_REFERENCE_COEFFICIENTS:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_coefficients.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g08}"
THRESHOLD_PANEL="${OUTPUT_DIR}/ml_threshold_repo_month_panel.csv.gz"
THRESHOLDS="${THRESHOLDS:-0.10,0.14,0.18,0.22,0.26,0.30,0.34,0.38,0.42,0.46,0.50,0.54,0.58,0.62,0.66,0.70,0.74,0.78,0.82,0.86,0.90}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"

EXPECTED_A04_ROWS="${EXPECTED_A04_ROWS:-494592}"
EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_D02_UNIQUE_FILES="${EXPECTED_D02_UNIQUE_FILES:-494592}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"
EXPECTED_ELIGIBLE_ROWS="${EXPECTED_ELIGIBLE_ROWS:-204509}"
EXPECTED_ELIGIBLE_UNIQUE_FILES="${EXPECTED_ELIGIBLE_UNIQUE_FILES:-196644}"
EXPECTED_PRIMARY_SELECTED_ROWS="${EXPECTED_PRIMARY_SELECTED_ROWS:-43325}"
EXPECTED_PRIMARY_SELECTED_UNIQUE_FILES="${EXPECTED_PRIMARY_SELECTED_UNIQUE_FILES:-41905}"
EXPECTED_PRIMARY_ISSUE_STOCK="${EXPECTED_PRIMARY_ISSUE_STOCK:-48478}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"

EXPECTED_A04_SHA256="b04db6462e74dfd3161d1680425a0335361e86093754ee2341f5c9e0e84e6518"
EXPECTED_D02_SHA256="443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df"
EXPECTED_B06_SHA256="e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027"
EXPECTED_D05_SHA256="970919c66c06c9e0c0eb88d459a9fcd916728ff4483ae7a9af559702785ebbd1"
EXPECTED_E03_COEF_SHA256="bba73508e36acccc739b679b7419080797f63241f152bce97437ff597b2cfaa9"

for tool in "${PYTHON_BIN}" "${RSCRIPT_BIN}" sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "ERROR: required executable not found: ${tool}" >&2
    exit 1
  fi
done

for required_file in \
  "${BUILDER_SCRIPT}" "${R_SCRIPT}" "${A04_FILE}" "${D02_FILE}" \
  "${B06_FILE}" "${D05_REFERENCE_FILE}" "${E03_REFERENCE_COEFFICIENTS}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

check_sha256() {
  local path="$1"
  local expected="$2"
  local label="$3"
  local observed
  observed="$(sha256sum "${path}" | awk '{print $1}')"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch" >&2
    echo "  expected: ${expected}" >&2
    echo "  observed: ${observed}" >&2
    echo "  file:     ${path}" >&2
    exit 1
  fi
}

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

"${PYTHON_BIN}" -m py_compile "${BUILDER_SCRIPT}"
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}')" >/dev/null

check_sha256 "${A04_FILE}" "${EXPECTED_A04_SHA256}" "A04"
check_sha256 "${D02_FILE}" "${EXPECTED_D02_SHA256}" "D02"
check_sha256 "${B06_FILE}" "${EXPECTED_B06_SHA256}" "B06"
check_sha256 "${D05_REFERENCE_FILE}" "${EXPECTED_D05_SHA256}" "D05"
check_sha256 "${E03_REFERENCE_COEFFICIENTS}" "${EXPECTED_E03_COEF_SHA256}" "E03 coefficients"

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); suppressPackageStartupMessages(library(plm)); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"

{
  echo "============================================================"
  echo "${RUN_LABEL}: ML file-composition threshold sensitivity GMM"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
  echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Threshold grid:                  ${THRESHOLDS}"
  echo "Primary file cutoff:             strict > 0.50"
  echo "Function SVM boundary:           unchanged"
  echo "Threshold selection by p-value:  NO"
  echo "A04 ML file scores:              ${A04_FILE}"
  echo "A04 SHA256:                      ${EXPECTED_A04_SHA256}"
  echo "D02 file burden:                 ${D02_FILE}"
  echo "D02 SHA256:                      ${EXPECTED_D02_SHA256}"
  echo "B06 panel:                       ${B06_FILE}"
  echo "B06 SHA256:                      ${EXPECTED_B06_SHA256}"
  echo "D05 primary reference:           ${D05_REFERENCE_FILE}"
  echo "D05 SHA256:                      ${EXPECTED_D05_SHA256}"
  echo "E03-v2 coefficient reference:    ${E03_REFERENCE_COEFFICIENTS}"
  echo "E03 coefficient SHA256:          ${EXPECTED_E03_COEF_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Estimator:                       two-step difference GMM, two-way effects"
  echo "Instrument:                      lag(velocity,2); collapse=FALSE"
  echo "Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}"
  echo "R parse:                         PASS"
  echo "Pinned upstream SHA256:          PASS"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

BUILD_COMMAND=(
  "${PYTHON_BIN}" "${BUILDER_SCRIPT}"
  --a04-file "${A04_FILE}"
  --d02-file "${D02_FILE}"
  --b06-file "${B06_FILE}"
  --d05-reference-file "${D05_REFERENCE_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --thresholds "${THRESHOLDS}"
  --expected-a04-rows "${EXPECTED_A04_ROWS}"
  --expected-d02-rows "${EXPECTED_D02_ROWS}"
  --expected-d02-unique-files "${EXPECTED_D02_UNIQUE_FILES}"
  --expected-b06-rows "${EXPECTED_B06_ROWS}"
  --expected-eligible-rows "${EXPECTED_ELIGIBLE_ROWS}"
  --expected-eligible-unique-files "${EXPECTED_ELIGIBLE_UNIQUE_FILES}"
  --expected-primary-selected-rows "${EXPECTED_PRIMARY_SELECTED_ROWS}"
  --expected-primary-selected-unique-files "${EXPECTED_PRIMARY_SELECTED_UNIQUE_FILES}"
  --expected-primary-issue-stock "${EXPECTED_PRIMARY_ISSUE_STOCK}"
)

{
  echo
  echo "** Step 1: Build ML threshold-sensitivity repo-month panel"
  echo "------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${BUILD_COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${BUILD_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

R_COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --input-file "${THRESHOLD_PANEL}"
  --reference-coefficients-file "${E03_REFERENCE_COEFFICIENTS}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --expected-rows-per-threshold "${EXPECTED_B06_ROWS}"
  --expected-active-rows "${EXPECTED_ACTIVE_ROWS}"
  --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}"
  --reference-tolerance "${REFERENCE_TOLERANCE}"
)

{
  echo
  echo "** Step 2: Fit identical reverse GMM at 21 ML file cutoffs"
  echo "------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${R_COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${R_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/ml_threshold_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/ml_threshold_support.csv"
  "${OUTPUT_DIR}/ml_threshold_reproduction_audit.csv"
  "${OUTPUT_DIR}/ml_threshold_qc.csv"
  "${OUTPUT_DIR}/ml_threshold_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_support_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_e03_reproduction.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_models.rds"
)

{
  echo
  echo "** Step 3: Verify G08 artifacts and hard QC"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

for qc_file in "${OUTPUT_DIR}/ml_threshold_qc.csv" "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_qc.csv"; do
  if grep -q ',fail,' "${qc_file}" || grep -q ',fail$' "${qc_file}"; then
    echo "ERROR: hard QC failure in ${qc_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 4: ML threshold sensitivity results"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

"${PYTHON_BIN}" - "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_primary_summary.csv" \
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_support_diagnostics.csv" <<'PY' | tee -a "${LOG_FILE}"
import csv
import sys
summary_path, support_path = sys.argv[1:3]
with open(summary_path, newline="", encoding="utf-8") as handle:
    summary = {round(float(row["threshold"]), 10): row for row in csv.DictReader(handle)}
with open(support_path, newline="", encoding="utf-8") as handle:
    support = {round(float(row["threshold"]), 10): row for row in csv.DictReader(handle)}
print("threshold,estimate,std_error,conf_low,conf_high,p_value,selected_file_rows,selected_issue_total,zero_issue_share_active,variation_repos_active,primary")
for threshold in sorted(summary):
    row = summary[threshold]
    sup = support[threshold]
    print(",".join([
        row["threshold"], row["estimate"], row["std_error"], row["conf_low"], row["conf_high"], row["p_value"],
        sup["selected_file_rows"], sup["selected_issue_total"], sup["zero_issue_share_active"],
        sup["repositories_with_within_quality_variation_active"], row["primary_analysis"],
    ]))
PY

CAUTION_ROWS="$(${PYTHON_BIN} - "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_qc.csv" <<'PY'
import csv
import sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    print(sum(1 for row in csv.DictReader(handle) if row.get("status") == "caution"))
PY
)"

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Thresholds reported:             21"
  echo "Grid:                            ${THRESHOLDS}"
  echo "Primary cutoff:                  > 0.50"
  echo "D05 0.50 reproduction:           PASS"
  echo "E03-v2 0.50 GMM reproduction:    PASS"
  echo "GMM QC caution rows:             ${CAUTION_ROWS}"
  echo "Primary summary:                 ${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_primary_summary.csv"
  echo "Threshold support:               ${OUTPUT_DIR}/ml_threshold_support.csv"
  echo "GMM diagnostics:                 ${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_diagnostics.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
