#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-g05 v1: fit GMM using the validated G04 ML-below-threshold panel
# ============================================================
#
# Inputs:
#   G04 panel: zero-inclusive repo-month quality burden for files with a finite
#              token-weighted ML AGC share <= 0.50.
#   G04 QC:    hard-QC results from input preparation.
#   G04 meta:  provenance and downstream-contract metadata.
#   B06 panel: authoritative velocity, treatment timing, and covariates.
#
# Outputs:
#   GMM coefficients, primary coefficient, diagnostics, sample/instrument QC,
#   run metadata, and fitted model RDS under repo_x01/run-x-g05/.
#
# This wrapper is self-contained. It does not call the G04 wrapper and does not
# recompute ML threshold selection. It only validates and consumes G04 outputs.
# ============================================================

RUN_PREFIX="run-x-g05"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_ml_below_threshold.R}"

G04_PANEL="${G04_PANEL:-repo_x01/run-x-g04/ml_below_threshold_repo_month_panel.csv.gz}"
G04_QC="${G04_QC:-repo_x01/run-x-g04/ml_below_threshold_qc.csv}"
G04_METADATA="${G04_METADATA:-repo_x01/run-x-g04/ml_below_threshold_metadata.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g05}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"
EXPECTED_SELECTED_FILE_ROWS="${EXPECTED_SELECTED_FILE_ROWS:-161184}"
EXPECTED_SELECTED_ISSUE_STOCK="${EXPECTED_SELECTED_ISSUE_STOCK:-295977}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOSITORIES="${EXPECTED_LEGACY_MISMATCH_REPOSITORIES:-3}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"

# These hashes pin G05 to the successful run-x-g04-v2 outputs and the same B06
# panel used throughout the validated dynamic-panel analyses.
EXPECTED_G04_PANEL_SHA256="${EXPECTED_G04_PANEL_SHA256:-521c330a6e7d14de64458f8c30417cccfc16768068ded2e92600e8edd5354f0a}"
EXPECTED_G04_QC_SHA256="${EXPECTED_G04_QC_SHA256:-d99ca1b175784b18a19781c127afd1163f29014bef2519498aa5d4a048e2f0ac}"
EXPECTED_G04_METADATA_SHA256="${EXPECTED_G04_METADATA_SHA256:-36b45a48bd71a01447f3601a0863718994a361c56c11af236b16f8120fda5906}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"

ML_THRESHOLD="0.50"
PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-ml-below-threshold-${TIMESTAMP}.log"

for required_file in "${R_SCRIPT}" "${G04_PANEL}" "${G04_QC}" "${G04_METADATA}" "${B06_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

R_VERSION="$(${RSCRIPT_BIN} --version 2>&1 | head -n 1)"
R_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
G04_PANEL_SHA256="$(sha256sum "${G04_PANEL}" | awk '{print $1}')"
G04_QC_SHA256="$(sha256sum "${G04_QC}" | awk '{print $1}')"
G04_METADATA_SHA256="$(sha256sum "${G04_METADATA}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"

for hash_pair in \
  "G04_PANEL:${G04_PANEL_SHA256}:${EXPECTED_G04_PANEL_SHA256}" \
  "G04_QC:${G04_QC_SHA256}:${EXPECTED_G04_QC_SHA256}" \
  "G04_METADATA:${G04_METADATA_SHA256}:${EXPECTED_G04_METADATA_SHA256}" \
  "B06:${B06_SHA256}:${EXPECTED_B06_SHA256}"; do
  IFS=':' read -r label observed expected <<< "${hash_pair}"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch: expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
done

cat <<EOF
============================================================
${RUN_LABEL}: ML-below-threshold quality -> velocity GMM
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Rscript:                         $(command -v "${RSCRIPT_BIN}")
R version:                       ${R_VERSION}
Implementation version:          ${IMPLEMENTATION_VERSION}
Experiment role:                 GMM estimation only
Upstream experiment:             run-x-g04-v2
G04 selection rule:              finite weighted ML AGC share <= ${ML_THRESHOLD}
ML share missing/non-finite:     excluded upstream by G04
G04 panel:                       ${G04_PANEL}
G04 panel SHA256:                ${G04_PANEL_SHA256}
G04 QC:                          ${G04_QC}
G04 QC SHA256:                   ${G04_QC_SHA256}
G04 metadata:                    ${G04_METADATA}
G04 metadata SHA256:             ${G04_METADATA_SHA256}
B06 panel:                       ${B06_FILE}
B06 SHA256:                      ${B06_SHA256}
R script SHA256:                 ${R_SHA256}
Output directory:                ${OUTPUT_DIR}
Estimator:                       two-step difference GMM, two-way effects
Instrument:                      lag(velocity,2); collapse=FALSE
Expected selected files/issues:  ${EXPECTED_SELECTED_FILE_ROWS}/${EXPECTED_SELECTED_ISSUE_STOCK}
Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Validate G05 implementation and pinned inputs\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}'); cat('R parse: PASS\\n')"
echo "Pinned G04/B06 SHA256 checks: PASS"

printf '\n** Step 2: Fit ML-below-threshold dynamic panel GMM\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" "${R_SCRIPT}" \
  --input-file "${G04_PANEL}" \
  --input-qc-file "${G04_QC}" \
  --input-metadata-file "${G04_METADATA}" \
  --b06-panel-file "${B06_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --script-path "${R_SCRIPT}" \
  --implementation-version "${IMPLEMENTATION_VERSION}" \
  --confidence-level "${CONFIDENCE_LEVEL}" \
  --expected-rows "${EXPECTED_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-active-rows "${EXPECTED_ACTIVE_ROWS}" \
  --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}" \
  --expected-selected-file-rows "${EXPECTED_SELECTED_FILE_ROWS}" \
  --expected-selected-issue-stock "${EXPECTED_SELECTED_ISSUE_STOCK}" \
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}" \
  --expected-legacy-mismatch-repositories "${EXPECTED_LEGACY_MISMATCH_REPOSITORIES}" \
  --strict-expected-counts 1

printf '\n** Step 3: Verify G05 outputs and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_sample_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_numeric_coercion_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_calendar_gap_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_models.rds"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${RSCRIPT_BIN}" -e "q <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_qc.csv'); f <- q[tolower(status)=='fail']; if (nrow(f)) stop(paste('Hard QC failures:', paste(f[['check']], collapse=', '))); cat('Hard QC: PASS\\n')"

printf '\n** Step 4: Show G05 primary result and diagnostics\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" -e "p <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_primary_summary.csv'); stopifnot(nrow(p)==1); cat(sprintf('beta=%.9f, se=%.9f, ci=[%.9f, %.9f], p=%.9f, significant=%s\\n', p[['estimate']][1], p[['std_error']][1], p[['conf_low']][1], p[['conf_high']][1], p[['p_value']][1], p[['significant']][1])); d <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_diagnostics.csv'); for (i in seq_len(nrow(d))) cat(sprintf('%s: statistic=%s, p=%s, status=%s\\n', d[['diagnostic']][i], d[['statistic']][i], d[['p_value']][i], d[['status']][i]))"

CAUTION_COUNT="$(${RSCRIPT_BIN} -e "q <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_qc.csv'); cat(nrow(q[tolower(status)=='caution']))")"

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
Quality scope:                   finite weighted ML AGC share <= ${ML_THRESHOLD}
Upstream G04 QC:                 PASS and SHA256-pinned
GMM active rows/repos:           ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}
QC caution rows:                  ${CAUTION_COUNT}
Primary result:                  ${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_primary_summary.csv
Diagnostics:                     ${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_diagnostics.csv
Sample QC:                       ${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_sample_qc.csv
Instrument QC:                   ${OUTPUT_DIR}/dynamic_panel_gmm_ml_below_threshold_instrument_qc.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
