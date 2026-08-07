#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b07 v1: Borusyak DiD for Python-only SonarQube quality
# ============================================================
#
# Purpose:
#   Estimate monthly Cursor-adoption effects on Python-only SonarQube static-
#   analysis issue stock prepared by run-x-b06.
#
# Input:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Model specifications:
#   1. adjusted_burden
#      log1p Python issue-stock outcomes with:
#        log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues
#        | repo_id + time_index
#   2. fe_only_burden
#      The same burden outcomes with repository and calendar-month fixed effects.
#   3. fe_only_density
#      log1p Python issues-per-KLOC outcomes with repository and calendar-month
#      fixed effects. This is the code-size-normalized robustness analysis.
#
# Treatment timing:
#   The R implementation reconstructs absorbing treatment only from event_index
#   and time_index. Legacy cursor/is_treatment/post_event fields are audit-only.
#
# Expected full-sample support:
#   - 1,954 repo-month rows
#   - 63 treatment repositories
#   - 104 control repositories
#   - 1,591 untreated first-stage rows
#   - 363 treated post-adoption rows
#   - 343 treated rows in event 0:+6
#   - 11 legacy-flag mismatch rows in 3 repositories
#
# Estimation:
#   - Borusyak did_imputation
#   - repository-clustered standard errors
#   - static ATT over all post-adoption rows
#   - event 0:+6 dynamic effects
#   - event -6:-2 package-native placebo terms
#   - event -1 omitted reference
#
# This wrapper was derived from the established b03 shell logic but is fully
# self-contained and does not call any previous experiment shell script.
#
# Run:
#   bash proc_sh_x01/run-x-b07-did-borusyak-python-quality.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b07"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-python-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_python_quality.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-63}"
EXPECTED_CONTROL_REPOS="${EXPECTED_CONTROL_REPOS:-104}"
EXPECTED_UNTREATED_ROWS="${EXPECTED_UNTREATED_ROWS:-1591}"
EXPECTED_TREATED_ROWS="${EXPECTED_TREATED_ROWS:-363}"
EXPECTED_DYNAMIC_TREATED_ROWS="${EXPECTED_DYNAMIC_TREATED_ROWS:-343}"
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
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" \
  "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_ROWS}" "${EXPECTED_TREATMENT_REPOS}" \
  "${EXPECTED_CONTROL_REPOS}" "${EXPECTED_UNTREATED_ROWS}" \
  "${EXPECTED_TREATED_ROWS}" "${EXPECTED_DYNAMIC_TREATED_ROWS}" \
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

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Python-only SonarQube quality DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "Input quality panel:              ${INPUT_FILE}"
  echo "Input SHA256:                     ${INPUT_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Primary burden outcome:          log_issue_total_py_sonarqube"
  echo "Primary density outcome:         log_issues_per_kloc_py_sonarqube"
  echo "Spec 1:                          adjusted_burden"
  echo "Spec 2:                          fe_only_burden"
  echo "Spec 3:                          fe_only_density"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Confidence level:                ${CONFIDENCE_LEVEL}"
  echo "Expected rows:                   ${EXPECTED_ROWS}"
  echo "Expected treatment/control repos:${EXPECTED_TREATMENT_REPOS}/${EXPECTED_CONTROL_REPOS}"
  echo "Expected untreated/treated rows: ${EXPECTED_UNTREATED_ROWS}/${EXPECTED_TREATED_ROWS}"
  echo "Expected dynamic treated rows:   ${EXPECTED_DYNAMIC_TREATED_ROWS}"
  echo "Expected legacy mismatches:      ${EXPECTED_LEGACY_MISMATCH_ROWS} rows / ${EXPECTED_LEGACY_MISMATCH_REPOS} repos"
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
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-rows "${EXPECTED_ROWS}"
  --expected-treatment-repos "${EXPECTED_TREATMENT_REPOS}"
  --expected-control-repos "${EXPECTED_CONTROL_REPOS}"
  --expected-untreated-rows "${EXPECTED_UNTREATED_ROWS}"
  --expected-treated-rows "${EXPECTED_TREATED_ROWS}"
  --expected-dynamic-treated-rows "${EXPECTED_DYNAMIC_TREATED_ROWS}"
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
  --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
)

{
  echo
  echo "** Step 1: Run Python-only quality Borusyak DiD"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/python_quality_static_effects.csv"
  "${OUTPUT_DIR}/python_quality_dynamic_effects.csv"
  "${OUTPUT_DIR}/python_quality_pretrend_checks.csv"
  "${OUTPUT_DIR}/python_quality_pretrend_summary.csv"
  "${OUTPUT_DIR}/python_quality_primary_three_spec_summary.csv"
  "${OUTPUT_DIR}/python_quality_primary_key_terms.csv"
  "${OUTPUT_DIR}/python_quality_covariate_sensitivity_static.csv"
  "${OUTPUT_DIR}/python_quality_covariate_sensitivity_dynamic.csv"
  "${OUTPUT_DIR}/python_quality_diagnostics.csv"
  "${OUTPUT_DIR}/python_quality_sample_summary.csv"
  "${OUTPUT_DIR}/python_quality_event_support.csv"
  "${OUTPUT_DIR}/python_quality_cohort_support.csv"
  "${OUTPUT_DIR}/python_quality_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/python_quality_qc.csv"
  "${OUTPUT_DIR}/python_quality_run_metadata.csv"
  "${OUTPUT_DIR}/plots/python_quality_primary_burden_dynamic.pdf"
  "${OUTPUT_DIR}/plots/python_quality_primary_burden_dynamic.png"
  "${OUTPUT_DIR}/plots/python_quality_primary_density_dynamic.pdf"
  "${OUTPUT_DIR}/plots/python_quality_primary_density_dynamic.png"
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

QC_FILE="${OUTPUT_DIR}/python_quality_qc.csv"
if grep -q ',fail,' "${QC_FILE}" || grep -q ',fail$' "${QC_FILE}"; then
  echo "ERROR: B07 QC file contains one or more failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

STATIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/python_quality_static_effects.csv") - 1 ))"
DYNAMIC_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/python_quality_dynamic_effects.csv") - 1 ))"
PRETREND_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/python_quality_pretrend_checks.csv") - 1 ))"
PRIMARY_ROWS="$(( $(wc -l < "${OUTPUT_DIR}/python_quality_primary_three_spec_summary.csv") - 1 ))"

if [[ "${STATIC_ROWS}" -ne 24 || "${DYNAMIC_ROWS}" -ne 288 || "${PRETREND_ROWS}" -ne 120 || "${PRIMARY_ROWS}" -ne 3 ]]; then
  echo "ERROR: unexpected B07 output row counts: static=${STATIC_ROWS}, dynamic=${DYNAMIC_ROWS}, pretrend=${PRETREND_ROWS}, primary=${PRIMARY_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Static effect rows:              ${STATIC_ROWS}"
  echo "Dynamic/placebo rows:            ${DYNAMIC_ROWS}"
  echo "Pretrend check rows:             ${PRETREND_ROWS}"
  echo "Primary three-spec rows:         ${PRIMARY_ROWS}"
  echo "QC status:                       PASS"
  echo "Primary summary:                 ${OUTPUT_DIR}/python_quality_primary_three_spec_summary.csv"
  echo "Primary key terms:               ${OUTPUT_DIR}/python_quality_primary_key_terms.csv"
  echo "Full static effects:             ${OUTPUT_DIR}/python_quality_static_effects.csv"
  echo "Full dynamic effects:            ${OUTPUT_DIR}/python_quality_dynamic_effects.csv"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
