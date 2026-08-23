#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-g03 v1: fit GMM using the validated G02 NPR-below-threshold panel
# ============================================================
#
# Inputs:
#   G02 panel: zero-inclusive repo-month quality burden for finite-NPR files
#              with file NPR <= 1.571637.
#   G02 QC:    hard-QC results from input preparation.
#   G02 meta:  provenance and downstream-contract metadata.
#   B06 panel: authoritative velocity, treatment timing, and covariates.
#
# Outputs:
#   GMM coefficients, primary coefficient, diagnostics, sample/instrument QC,
#   run metadata, and fitted model RDS under repo_x01/run-x-g03/.
#
# This wrapper is self-contained. It does not call the G02 wrapper and does not
# recompute NPR threshold selection. It only validates and consumes G02 outputs.
# ============================================================

RUN_PREFIX="run-x-g03"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_npr_below_threshold.R}"

G02_PANEL="${G02_PANEL:-repo_x01/run-x-g02/npr_below_threshold_repo_month_panel.csv.gz}"
G02_QC="${G02_QC:-repo_x01/run-x-g02/npr_below_threshold_qc.csv}"
G02_METADATA="${G02_METADATA:-repo_x01/run-x-g02/npr_below_threshold_metadata.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g03}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"
EXPECTED_SELECTED_FILE_ROWS="${EXPECTED_SELECTED_FILE_ROWS:-190769}"
EXPECTED_SELECTED_ISSUE_STOCK="${EXPECTED_SELECTED_ISSUE_STOCK:-324149}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOSITORIES="${EXPECTED_LEGACY_MISMATCH_REPOSITORIES:-3}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"

# These hashes pin G03 to the successful run-x-g02-v2 outputs and the same B06
# panel used throughout the validated dynamic-panel analyses.
EXPECTED_G02_PANEL_SHA256="${EXPECTED_G02_PANEL_SHA256:-6ff49668da198913cbc2f001f0f1a577b0ab16d88fff0c1b608dd900c8c5450d}"
EXPECTED_G02_QC_SHA256="${EXPECTED_G02_QC_SHA256:-c22ac259de35597cd2a5bbb0efa4556f6e3bf1187dcfa356eb70cd8a72f40478}"
EXPECTED_G02_METADATA_SHA256="${EXPECTED_G02_METADATA_SHA256:-7be9c139de967990e1dc7fe37736c3b216d996e7a552bc017e542ebdd9d31900}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"

NPR_THRESHOLD="1.571637"
PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-npr-below-threshold-${TIMESTAMP}.log"

for required_file in "${R_SCRIPT}" "${G02_PANEL}" "${G02_QC}" "${G02_METADATA}" "${B06_FILE}"; do
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
G02_PANEL_SHA256="$(sha256sum "${G02_PANEL}" | awk '{print $1}')"
G02_QC_SHA256="$(sha256sum "${G02_QC}" | awk '{print $1}')"
G02_METADATA_SHA256="$(sha256sum "${G02_METADATA}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"

for hash_pair in \
  "G02_PANEL:${G02_PANEL_SHA256}:${EXPECTED_G02_PANEL_SHA256}" \
  "G02_QC:${G02_QC_SHA256}:${EXPECTED_G02_QC_SHA256}" \
  "G02_METADATA:${G02_METADATA_SHA256}:${EXPECTED_G02_METADATA_SHA256}" \
  "B06:${B06_SHA256}:${EXPECTED_B06_SHA256}"; do
  IFS=':' read -r label observed expected <<< "${hash_pair}"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch: expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
done

cat <<EOF
============================================================
${RUN_LABEL}: NPR-below-threshold quality -> velocity GMM
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Rscript:                         $(command -v "${RSCRIPT_BIN}")
R version:                       ${R_VERSION}
Implementation version:          ${IMPLEMENTATION_VERSION}
Experiment role:                 GMM estimation only
Upstream experiment:             run-x-g02-v2
G02 selection rule:              finite NPR <= ${NPR_THRESHOLD}
NPR missing/non-finite files:    excluded upstream by G02
G02 panel:                       ${G02_PANEL}
G02 panel SHA256:                ${G02_PANEL_SHA256}
G02 QC:                          ${G02_QC}
G02 QC SHA256:                   ${G02_QC_SHA256}
G02 metadata:                    ${G02_METADATA}
G02 metadata SHA256:             ${G02_METADATA_SHA256}
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

printf '\n** Step 1: Validate G03 implementation and pinned inputs\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}'); cat('R parse: PASS\\n')"
echo "Pinned G02/B06 SHA256 checks: PASS"

printf '\n** Step 2: Fit NPR-below-threshold dynamic panel GMM\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" "${R_SCRIPT}" \
  --input-file "${G02_PANEL}" \
  --input-qc-file "${G02_QC}" \
  --input-metadata-file "${G02_METADATA}" \
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

printf '\n** Step 3: Verify G03 outputs and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_sample_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_numeric_coercion_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_calendar_gap_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_models.rds"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${RSCRIPT_BIN}" -e "q <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_qc.csv'); f <- q[tolower(status)=='fail']; if (nrow(f)) stop(paste('Hard QC failures:', paste(f[['check']], collapse=', '))); cat('Hard QC: PASS\\n')"

printf '\n** Step 4: Show G03 primary result and diagnostics\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" -e "p <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_primary_summary.csv'); stopifnot(nrow(p)==1); cat(sprintf('beta=%.9f, se=%.9f, ci=[%.9f, %.9f], p=%.9f, significant=%s\\n', p[['estimate']][1], p[['std_error']][1], p[['conf_low']][1], p[['conf_high']][1], p[['p_value']][1], p[['significant']][1])); d <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_diagnostics.csv'); for (i in seq_len(nrow(d))) cat(sprintf('%s: statistic=%s, p=%s, status=%s\\n', d[['diagnostic']][i], d[['statistic']][i], d[['p_value']][i], d[['status']][i]))"

CAUTION_COUNT="$(${RSCRIPT_BIN} -e "q <- data.table::fread('${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_qc.csv'); cat(nrow(q[tolower(status)=='caution']))")"

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
Quality scope:                   finite NPR <= ${NPR_THRESHOLD}
Upstream G02 QC:                PASS and SHA256-pinned
GMM active rows/repos:          ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}
QC caution rows:                 ${CAUTION_COUNT}
Primary result:                  ${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_primary_summary.csv
Diagnostics:                     ${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_diagnostics.csv
Sample QC:                       ${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_sample_qc.csv
Instrument QC:                   ${OUTPUT_DIR}/dynamic_panel_gmm_npr_below_threshold_instrument_qc.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
