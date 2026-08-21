#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-e03 v7: low-range ML threshold sensitivity dynamic-panel GMM
# ============================================================
#
# Purpose:
#   Recheck E03 across strict file-level ML AGC composition thresholds
#   0.10 through 0.50 in 0.05 increments while keeping 0.50 as the frozen primary.
#
# Pipeline:
#   1. Reaggregate canonical D02 SonarQube file burden using continuous A04
#      file-level ML scores at all nine thresholds.
#   2. Require threshold 0.50 to reproduce frozen D05 repo-month quality
#      outcomes exactly.
#   3. Fit the exact same E03-v2 two-step difference-GMM at every threshold.
#   4. Require the 0.50 GMM coefficient/SE/p-value to reproduce E03-v2.
#
# This wrapper is self-contained and does not invoke any previous shell script.
# It reuses frozen upstream data artifacts and the validated E03 GMM logic.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-e03"
IMPLEMENTATION_VERSION="v7"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}-threshold-sensitivity-low"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
BUILDER_SCRIPT="${BUILDER_SCRIPT:-proc_script_x01/build_ml_gmm_threshold_panel.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml_threshold_sensitivity.R}"

A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
E03_REFERENCE_COEFFICIENTS="${E03_REFERENCE_COEFFICIENTS:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_coefficients.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-e03-threshold-sensitivity-low}"
THRESHOLD_PANEL="${OUTPUT_DIR}/ml_gmm_threshold_repo_month_panel.csv.gz"
THRESHOLDS="${THRESHOLDS:-0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"

EXPECTED_A04_ROWS="${EXPECTED_A04_ROWS:-494592}"
EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"

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

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

# Compile the new Python builder before touching outputs.
"${PYTHON_BIN}" -m py_compile "${BUILDER_SCRIPT}"

# Verify R dependencies and explicitly attach plm. pgmm internally evaluates a
# bare plm() call, so requireNamespace alone is not sufficient.
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "plm"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); suppressPackageStartupMessages(library(plm)); if (!exists("plm", mode="function", inherits=TRUE)) stop("plm() is not visible after package attachment"); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"

{
  echo "============================================================"
  echo "${RUN_LABEL}: ML threshold sensitivity GMM"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
  echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Thresholds:                      ${THRESHOLDS}"
  echo "Frozen primary threshold:        0.50"
  echo "Comparison operator:             strict >"
  echo "Threshold selection by p-value:  NO"
  echo "A04 continuous ML file scores:   ${A04_FILE}"
  echo "A04 SHA256:                      $(sha256sum "${A04_FILE}" | awk '{print $1}')"
  echo "D02 file-level Sonar burden:     ${D02_FILE}"
  echo "D02 SHA256:                      $(sha256sum "${D02_FILE}" | awk '{print $1}')"
  echo "B06 panel:                       ${B06_FILE}"
  echo "B06 SHA256:                      $(sha256sum "${B06_FILE}" | awk '{print $1}')"
  echo "D05 0.50 reproduction reference:${D05_REFERENCE_FILE}"
  echo "E03-v2 GMM reference:            ${E03_REFERENCE_COEFFICIENTS}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Estimator:                       two-step difference GMM, two-way effects"
  echo "Instrument:                      lag(velocity,2); collapse=FALSE"
  echo "Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}"
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
  --expected-b06-rows "${EXPECTED_B06_ROWS}"
)

{
  echo
  echo "** Step 1: Reaggregate ML-localized quality at nine thresholds"
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
  echo "** Step 2: Fit identical E03 GMM at every threshold"
  echo "------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${R_COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${R_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/ml_gmm_threshold_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/ml_gmm_threshold_support.csv"
  "${OUTPUT_DIR}/ml_gmm_threshold_reproduction_audit.csv"
  "${OUTPUT_DIR}/ml_gmm_threshold_join_audit.csv"
  "${OUTPUT_DIR}/ml_gmm_threshold_issue_column_audit.csv"
  "${OUTPUT_DIR}/ml_gmm_threshold_metadata.csv"
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
  echo "** Step 3: Verify artifacts"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_qc.csv"
if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: threshold-sensitivity QC contains failed checks." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 4: Threshold sensitivity results"
  echo "------------------------------------------------------------"
  echo "Primary lagged ML-quality coefficient at each strict threshold:"
} | tee -a "${LOG_FILE}"

# Use Python's CSV parser rather than awk -F',' because GMM term names contain
# quoted commas such as lag(log1p_selected_issue_total, 1).
"${PYTHON_BIN}" - "${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_primary_summary.csv" <<'PY' | tee -a "${LOG_FILE}"
import csv
import sys
path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
print("threshold,estimate,std_error,conf_low,conf_high,p_value,significant,primary_analysis")
for row in rows:
    print(",".join(row[k] for k in ["threshold","estimate","std_error","conf_low","conf_high","p_value","significant","primary_analysis"]))
PY

CAUTION_ROWS="$(${PYTHON_BIN} - "${QC_FILE}" <<'PY'
import csv, sys
with open(sys.argv[1], newline="", encoding="utf-8") as f:
    print(sum(1 for row in csv.DictReader(f) if row.get("status") == "caution"))
PY
)"

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Thresholds reported:             ${THRESHOLDS}"
  echo "Frozen primary:                  0.50"
  echo "D05 0.50 reproduction:           PASS"
  echo "E03-v2 0.50 GMM reproduction:    PASS"
  echo "QC caution rows:                 ${CAUTION_ROWS}"
  echo "Primary summary:                 ${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_primary_summary.csv"
  echo "Threshold support:               ${OUTPUT_DIR}/ml_gmm_threshold_support.csv"
  echo "GMM diagnostics:                 ${OUTPUT_DIR}/dynamic_panel_gmm_ml_threshold_diagnostics.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
