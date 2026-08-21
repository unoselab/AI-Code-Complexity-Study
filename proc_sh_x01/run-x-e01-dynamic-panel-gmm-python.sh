#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-e01 v3: Dynamic panel GMM for Python velocity-quality interactions
# ============================================================
#
# Purpose:
#   Estimate the whole-Python dynamic interaction between development velocity
#   and Python-only SonarQube issue stock using the original MSR DynamicPanel.Rmd
#   difference-GMM design adapted to the current Python replication panel.
#
# Authoritative input:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Primary variables:
#   - Velocity: log_lines_added_py_source
#   - Quality:  log_issue_total_py_sonarqube
#   - Size:     log1p(ncloc_py_sonarqube), created by the R analysis script
#
# Primary models:
#   1. velocity_to_quality
#      Quality_t <- lag(Quality,1) + Velocity_t + treatment + controls
#      GMM instruments: lag(Quality,2:3) + lag(Velocity,2:3)
#      collapse = TRUE
#
#   2. quality_to_velocity
#      Velocity_t <- lag(Velocity,1) + lag(Quality,1) + treatment + controls
#      GMM instruments: lag(Velocity,2)
#      collapse = FALSE
#
# Shared estimator settings:
#   - plm::pgmm
#   - two-way effects
#   - two-step difference GMM
#   - robust summary
#
# Treatment:
#   Reconstructed in R as normalized absorbing treatment from treatment_group,
#   event_index, and time_index. Legacy cursor/is_treatment/post_event fields
#   are audit-only.
#
# Expected source-panel invariants:
#   - 1,954 repo-month rows
#   - 167 repositories
#   - 63 treatment repositories
#   - 104 control repositories
#   - 11 legacy-flag mismatch rows in 3 repositories
#
# Output:
#   repo_x01/run-x-e01/
#
# This wrapper was derived from the established run-x-b07 shell structure but
# is fully self-contained and does not call any previous experiment shell.
#
# Run:
#   bash proc_sh_x01/run-x-e01-dynamic-panel-gmm-python.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-e01"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-python-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_python.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-63}"
EXPECTED_CONTROL_REPOS="${EXPECTED_CONTROL_REPOS:-104}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-3}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in "${R_SCRIPT}" "${INPUT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${EXPECTED_ROWS}" "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOS}" "${EXPECTED_CONTROL_REPOS}" \
  "${EXPECTED_LEGACY_MISMATCH_ROWS}" "${EXPECTED_LEGACY_MISMATCH_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
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

{
  echo "============================================================"
  echo "${RUN_LABEL}: whole-Python dynamic panel GMM"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "Input panel:                     ${INPUT_FILE}"
  echo "Input SHA256:                    ${INPUT_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Analysis scope:                  whole_python"
  echo "Velocity:                        log_lines_added_py_source"
  echo "Quality:                         log_issue_total_py_sonarqube"
  echo "Size control:                    log1p(ncloc_py_sonarqube)"
  echo "Treatment:                       normalized absorbing treatment"
  echo "Estimator:                       two-step difference GMM, two-way effects"
  echo "Forward instruments:             lag(quality,2:3) + lag(velocity,2:3); collapse=TRUE"
  echo "Reverse instruments:             lag(velocity,2); collapse=FALSE"
  echo "Expected rows/repos:             ${EXPECTED_ROWS}/${EXPECTED_REPOSITORIES}"
  echo "Expected treatment/control repos:${EXPECTED_TREATMENT_REPOS}/${EXPECTED_CONTROL_REPOS}"
  echo "Expected legacy mismatches:      ${EXPECTED_LEGACY_MISMATCH_ROWS} rows / ${EXPECTED_LEGACY_MISMATCH_REPOS} repos"
  echo "Confidence level:                ${CONFIDENCE_LEVEL}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-rows "${EXPECTED_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repos "${EXPECTED_TREATMENT_REPOS}"
  --expected-control-repos "${EXPECTED_CONTROL_REPOS}"
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
  --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
)

{
  echo
  echo "** Step 1: Run whole-Python dynamic panel GMM"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

COEFFICIENTS_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_coefficients.csv"
DIAGNOSTICS_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_diagnostics.csv"
SAMPLE_QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_sample_qc.csv"
INSTRUMENT_QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_instrument_qc.csv"
MODEL_SPECS_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_model_specifications.csv"
LEGACY_AUDIT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_legacy_flag_audit.csv"
COERCION_AUDIT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_numeric_coercion_audit.csv"
CALENDAR_GAP_AUDIT_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_calendar_gap_audit.csv"
RUN_METADATA_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_run_metadata.csv"
QC_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_qc.csv"
MODELS_RDS_FILE="${OUTPUT_DIR}/dynamic_panel_gmm_models.rds"

EXPECTED_OUTPUTS=(
  "${COEFFICIENTS_FILE}"
  "${DIAGNOSTICS_FILE}"
  "${SAMPLE_QC_FILE}"
  "${INSTRUMENT_QC_FILE}"
  "${MODEL_SPECS_FILE}"
  "${LEGACY_AUDIT_FILE}"
  "${COERCION_AUDIT_FILE}"
  "${CALENDAR_GAP_AUDIT_FILE}"
  "${RUN_METADATA_FILE}"
  "${QC_FILE}"
  "${MODELS_RDS_FILE}"
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

if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: run-x-e01 QC contains one or more failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

COEFFICIENT_ROWS="$(( $(wc -l < "${COEFFICIENTS_FILE}") - 1 ))"
DIAGNOSTIC_ROWS="$(( $(wc -l < "${DIAGNOSTICS_FILE}") - 1 ))"
INSTRUMENT_ROWS="$(( $(wc -l < "${INSTRUMENT_QC_FILE}") - 1 ))"
CAUTION_ROWS="$(awk -F, 'NR > 1 && $4 == "caution" { count++ } END { print count + 0 }' "${QC_FILE}")"

if [[ "${COEFFICIENT_ROWS}" -lt 2 || "${DIAGNOSTIC_ROWS}" -ne 6 || "${INSTRUMENT_ROWS}" -ne 2 ]]; then
  echo "ERROR: unexpected run-x-e01 output row counts: coefficients=${COEFFICIENT_ROWS}, diagnostics=${DIAGNOSTIC_ROWS}, instruments=${INSTRUMENT_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 3: Primary GMM results and diagnostics"
  echo "------------------------------------------------------------"
  echo "Primary interaction coefficients:"
  head -n 1 "${COEFFICIENTS_FILE}"
  grep -E ',(TRUE|true)$' "${COEFFICIENTS_FILE}" || true
  echo
  echo "GMM diagnostics:"
  cat "${DIAGNOSTICS_FILE}"
  echo
  echo "Instrument/sample accounting:"
  cat "${INSTRUMENT_QC_FILE}"
  echo
  echo "QC:"
  cat "${QC_FILE}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Analysis scope:                  whole_python"
  echo "Coefficient rows:                ${COEFFICIENT_ROWS}"
  echo "Diagnostic rows:                 ${DIAGNOSTIC_ROWS}"
  echo "Instrument QC rows:              ${INSTRUMENT_ROWS}"
  echo "QC caution rows:                 ${CAUTION_ROWS}"
  echo "QC status:                       PASS (caution/informational rows may remain for review)"
  echo "Coefficients:                    ${COEFFICIENTS_FILE}"
  echo "Diagnostics:                     ${DIAGNOSTICS_FILE}"
  echo "Sample QC:                       ${SAMPLE_QC_FILE}"
  echo "Instrument QC:                   ${INSTRUMENT_QC_FILE}"
  echo "Run metadata:                    ${RUN_METADATA_FILE}"
  echo "Models RDS:                      ${MODELS_RDS_FILE}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
