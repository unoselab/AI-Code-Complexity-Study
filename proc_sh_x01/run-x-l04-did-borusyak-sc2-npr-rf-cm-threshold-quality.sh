#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-l04 v2: Borusyak DiD for frozen SC2-7B NPR RF/CM quality burden
# ============================================================
#
# Purpose:
#   Estimate the same frozen-threshold Borusyak DiD design used by run-x-l02,
#   separately for the RF and CM localization scopes prepared by run-x-l03.
#   The wrapper executes one standalone R implementation twice, once per scope.
#   It does not call run-x-d04, run-x-h04, run-x-l02, or any earlier wrapper.
#
# Primary input:
#   repo_x01/run-x-l03/npr-rf-cm-threshold-quality-burden-v1/
#     quality_npr_rf_cm_threshold_repo_month_panel.csv.gz
#
# Upstream provenance/QC inputs:
#   quality_npr_rf_cm_threshold_summary.csv
#   quality_npr_rf_cm_threshold_sample_summary.csv
#   quality_npr_rf_cm_threshold_global_audit.csv
#
# Analysis dimensions per localization scope:
#   - 23 frozen NPR thresholds: 21 grid + legacy + prior-primary.
#   - 2 samples: full and pre-specified two-repository exclusion sensitivity.
#   - 2 model specifications: adjusted burden and FE-only burden.
#   - 8 selected-file unresolved SonarQube burden outcomes.
#   - RF and CM are estimated separately so their frozen file populations remain
#     semantically distinct. The combined RF+CM analysis remains frozen in l02.
#
# Estimation:
#   - Borusyak did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic effects at event 0:+6.
#   - Placebo/pretrend terms at event -6:-2.
#   - Event -1 omitted.
#
# Sparse-support policy:
#   All frozen thresholds remain in the analysis. Support flags are descriptive;
#   they never remove a threshold after causal estimates are observed.
#
# Versioned delivery files:
#   proc_script_x01/did_borusyak_sc2_npr_rf_cm_threshold_quality-v2.R
#   proc_sh_x01/run-x-l04-did-borusyak-sc2-npr-rf-cm-threshold-quality-v2.sh
#
# Canonical server paths after removing the delivery version suffix:
#   proc_script_x01/did_borusyak_sc2_npr_rf_cm_threshold_quality.R
#   proc_sh_x01/run-x-l04-did-borusyak-sc2-npr-rf-cm-threshold-quality.sh
#
# Output:
#   repo_x01/run-x-l04/borusyak-rf-cm-threshold-quality-v2/rf/
#   repo_x01/run-x-l04/borusyak-rf-cm-threshold-quality-v2/cm/
#
# Run after deploying canonical script names:
#   bash proc_sh_x01/run-x-l04-did-borusyak-sc2-npr-rf-cm-threshold-quality.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-l04"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-x-l04}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-npr-rf-cm-threshold-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_sc2_npr_rf_cm_threshold_quality.R}"
L03_ROOT="${L03_ROOT:-repo_x01/run-x-l03/npr-rf-cm-threshold-quality-burden-v1}"
INPUT_FILE="${INPUT_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_repo_month_panel.csv.gz}"
L03_SUMMARY_FILE="${L03_SUMMARY_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_summary.csv}"
L03_SAMPLE_SUMMARY_FILE="${L03_SAMPLE_SUMMARY_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_sample_summary.csv}"
L03_GLOBAL_AUDIT_FILE="${L03_GLOBAL_AUDIT_FILE:-${L03_ROOT}/quality_npr_rf_cm_threshold_global_audit.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/${RUN_PREFIX}/borusyak-rf-cm-threshold-quality-v2}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.515059}"
PRIOR_PRIMARY_THRESHOLD="${PRIOR_PRIMARY_THRESHOLD:-1.571637}"
EXPECTED_SCOPES="${EXPECTED_SCOPES:-2}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-23}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
EXPECTED_TOTAL_LONG_ROWS="${EXPECTED_TOTAL_LONG_ROWS:-177974}"
EXPECTED_SCOPE_LONG_ROWS="${EXPECTED_SCOPE_LONG_ROWS:-88987}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
STRICT_PRIMARY_WARNINGS="${STRICT_PRIMARY_WARNINGS:-1}"
ALLOW_EXISTING_OUTPUT="${ALLOW_EXISTING_OUTPUT:-0}"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in \
  "${R_SCRIPT}" \
  "${INPUT_FILE}" \
  "${L03_SUMMARY_FILE}" \
  "${L03_SAMPLE_SUMMARY_FILE}" \
  "${L03_GLOBAL_AUDIT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" \
  "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_SCOPES}" "${EXPECTED_THRESHOLDS}" "${EXPECTED_SAMPLE_SPECS}" \
  "${EXPECTED_TOTAL_LONG_ROWS}" "${EXPECTED_SCOPE_LONG_ROWS}" \
  "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}" "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

for boolean_value in "${STRICT_EXPECTED_COUNTS}" "${STRICT_PRIMARY_WARNINGS}" "${ALLOW_EXISTING_OUTPUT}"; do
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: boolean options must be 0 or 1; observed: ${boolean_value}" >&2
    exit 1
  fi
done

if [[ "${ALLOW_EXISTING_OUTPUT}" == "0" && -d "${OUTPUT_ROOT}" ]] && find "${OUTPUT_ROOT}" -mindepth 1 -print -quit | grep -q .; then
  echo "ERROR: output root already contains files: ${OUTPUT_ROOT}" >&2
  echo "Use a new versioned experiment instead of overwriting prior outputs." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_ROOT}"

# Validate required R packages before the two scope-specific analyses begin.
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest", "ggplot2"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
L03_SUMMARY_SHA256="$(sha256sum "${L03_SUMMARY_FILE}" | awk '{print $1}')"
L03_SAMPLE_SUMMARY_SHA256="$(sha256sum "${L03_SAMPLE_SUMMARY_FILE}" | awk '{print $1}')"
L03_GLOBAL_AUDIT_SHA256="$(sha256sum "${L03_GLOBAL_AUDIT_FILE}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: frozen-threshold Quality x NPR RF/CM Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "l03 long panel:                  ${INPUT_FILE}"
  echo "l03 long panel SHA256:           ${INPUT_SHA256}"
  echo "l03 summary SHA256:              ${L03_SUMMARY_SHA256}"
  echo "l03 sample summary SHA256:       ${L03_SAMPLE_SUMMARY_SHA256}"
  echo "l03 global audit SHA256:         ${L03_GLOBAL_AUDIT_SHA256}"
  echo "Output root:                     ${OUTPUT_ROOT}"
  echo "Localization scopes:             RF + CM"
  echo "Combined RF+CM:                  retained from frozen run-x-l02-v1"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Prior-primary anchor:            ${PRIOR_PRIMARY_THRESHOLD}"
  echo "Threshold specifications/scope:  ${EXPECTED_THRESHOLDS}"
  echo "Sample specifications/scope:     ${EXPECTED_SAMPLE_SPECS}"
  echo "Expected l03 total rows:         ${EXPECTED_TOTAL_LONG_ROWS}"
  echo "Expected rows/scope:             ${EXPECTED_SCOPE_LONG_ROWS}"
  echo "Model specs:                     adjusted_burden + fe_only_burden"
  echo "Burden outcomes:                 8"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Reported post-treatment terms:   0:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Sparse threshold omission:       none"
  echo "Density:                         not computed"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Strict primary warnings:         ${STRICT_PRIMARY_WARNINGS}"
  echo "Allow existing output:           ${ALLOW_EXISTING_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run l04 structural self-test"
  echo "----------------------------------------------------------------------------"
  echo "Command: ${RSCRIPT_BIN} ${R_SCRIPT} --self-test"
  echo
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse l04 R program"
  echo "----------------------------------------------------------------------------"
  echo "Command: ${RSCRIPT_BIN} -e parse(file=...)"
  echo
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "invisible(parse(file='${R_SCRIPT}')); cat('R parse: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

qc_observed_count() {
  local qc_file="$1"
  local check_name="$2"
  local value
  if ! value="$(awk -F, -v check_name="${check_name}" '
      $1 == check_name {
        gsub(/[\r\"]/, "", $2)
        printf "%.0f\n", $2
        found = 1
        exit
      }
      END { if (!found) exit 1 }
    ' "${qc_file}")"; then
    echo "ERROR: required QC count not found: ${check_name} in ${qc_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if ! [[ "${value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: invalid QC count for ${check_name}: ${value}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  printf '%s\n' "${value}"
}

run_scope() {
  local scope="$1"
  local scope_id
  scope_id="$(printf '%s' "${scope}" | tr '[:upper:]' '[:lower:]')"
  local output_dir="${OUTPUT_ROOT}/${scope_id}"
  local prefix="quality_npr_${scope_id}"

  mkdir -p "${output_dir}"

  local -a command=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --input-file "${INPUT_FILE}"
    --l03-summary-file "${L03_SUMMARY_FILE}"
    --l03-sample-summary-file "${L03_SAMPLE_SUMMARY_FILE}"
    --l03-global-audit-file "${L03_GLOBAL_AUDIT_FILE}"
    --localization-scope "${scope}"
    --output-dir "${output_dir}"
    --script-path "${R_SCRIPT}"
    --implementation-version "${IMPLEMENTATION_VERSION}"
    --plot-min-event "${PLOT_MIN_EVENT}"
    --plot-max-event "${PLOT_MAX_EVENT}"
    --pretrend-min "${PRETREND_MIN}"
    --pretrend-max "${PRETREND_MAX}"
    --confidence-level "${CONFIDENCE_LEVEL}"
    --primary-threshold "${PRIMARY_THRESHOLD}"
    --prior-primary-threshold "${PRIOR_PRIMARY_THRESHOLD}"
    --expected-scopes "${EXPECTED_SCOPES}"
    --expected-thresholds "${EXPECTED_THRESHOLDS}"
    --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
    --expected-total-long-rows "${EXPECTED_TOTAL_LONG_ROWS}"
    --expected-scope-long-rows "${EXPECTED_SCOPE_LONG_ROWS}"
    --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
    --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
    --strict-primary-warnings "${STRICT_PRIMARY_WARNINGS}"
  )

  {
    echo
    echo "** Step 3.${scope_id}: Run l04 Borusyak DiD for ${scope}"
    echo "----------------------------------------------------------------------------"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"

  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"

  local -a expected_outputs=(
    "${output_dir}/${prefix}_static_effects.csv"
    "${output_dir}/${prefix}_dynamic_effects.csv"
    "${output_dir}/${prefix}_pretrend_checks.csv"
    "${output_dir}/${prefix}_pretrend_summary.csv"
    "${output_dir}/${prefix}_model_diagnostics.csv"
    "${output_dir}/${prefix}_model_failures.csv"
    "${output_dir}/${prefix}_threshold_support.csv"
    "${output_dir}/${prefix}_event_support.csv"
    "${output_dir}/${prefix}_support_policy.csv"
    "${output_dir}/${prefix}_primary_threshold_static.csv"
    "${output_dir}/${prefix}_primary_total_static.csv"
    "${output_dir}/${prefix}_primary_total_dynamic.csv"
    "${output_dir}/${prefix}_total_threshold_static.csv"
    "${output_dir}/${prefix}_total_threshold_dynamic.csv"
    "${output_dir}/${prefix}_qc.csv"
    "${output_dir}/${prefix}_summary.csv"
    "${output_dir}/${prefix}_run_metadata.csv"
    "${output_dir}/plots/${prefix}_total_static_across_thresholds.pdf"
    "${output_dir}/plots/${prefix}_total_static_across_thresholds.png"
    "${output_dir}/plots/${prefix}_primary_total_dynamic.pdf"
    "${output_dir}/plots/${prefix}_primary_total_dynamic.png"
  )

  {
    echo
    echo "** Step 4.${scope_id}: Verify ${scope} output artifacts"
    echo "----------------------------------------------------------------------------"
  } | tee -a "${LOG_FILE}"

  local output_file
  for output_file in "${expected_outputs[@]}"; do
    if [[ ! -s "${output_file}" ]]; then
      echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
      exit 1
    fi
    echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
  done

  local qc_file="${output_dir}/${prefix}_qc.csv"
  if grep -q ',fail,' "${qc_file}" || grep -q ',fail$' "${qc_file}"; then
    echo "ERROR: ${scope} QC file contains one or more hard failed checks." | tee -a "${LOG_FILE}" >&2
    cat "${qc_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi

  local static_rows dynamic_rows pretrend_rows primary_static_rows
  local primary_total_static_rows primary_total_dynamic_rows threshold_support_rows
  local event_support_rows total_threshold_static_rows total_threshold_dynamic_rows
  static_rows="$(qc_observed_count "${qc_file}" static_effect_rows)"
  dynamic_rows="$(qc_observed_count "${qc_file}" dynamic_effect_rows)"
  pretrend_rows="$(qc_observed_count "${qc_file}" pretrend_check_rows)"
  primary_static_rows="$(qc_observed_count "${qc_file}" primary_threshold_static_rows)"
  primary_total_static_rows="$(qc_observed_count "${qc_file}" primary_total_static_rows)"
  primary_total_dynamic_rows="$(qc_observed_count "${qc_file}" primary_total_dynamic_rows)"
  threshold_support_rows="$(qc_observed_count "${qc_file}" threshold_support_rows)"
  event_support_rows="$(qc_observed_count "${qc_file}" event_support_rows)"
  total_threshold_static_rows="$(qc_observed_count "${qc_file}" total_threshold_static_rows)"
  total_threshold_dynamic_rows="$(qc_observed_count "${qc_file}" total_threshold_dynamic_rows)"

  if [[ "${static_rows}" -ne 736 || \
        "${dynamic_rows}" -ne 8832 || \
        "${pretrend_rows}" -ne 3680 || \
        "${primary_static_rows}" -ne 32 || \
        "${primary_total_static_rows}" -ne 4 || \
        "${primary_total_dynamic_rows}" -ne 48 || \
        "${threshold_support_rows}" -ne 46 || \
        "${event_support_rows}" -ne 598 || \
        "${total_threshold_static_rows}" -ne 92 || \
        "${total_threshold_dynamic_rows}" -ne 1104 ]]; then
    echo "ERROR: unexpected ${scope} output row counts: static=${static_rows}, dynamic=${dynamic_rows}, pretrend=${pretrend_rows}, primary_static=${primary_static_rows}, primary_total_static=${primary_total_static_rows}, primary_total_dynamic=${primary_total_dynamic_rows}, threshold_support=${threshold_support_rows}, event_support=${event_support_rows}, total_threshold_static=${total_threshold_static_rows}, total_threshold_dynamic=${total_threshold_dynamic_rows}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi

  local summary_file="${output_dir}/${prefix}_summary.csv"
  local run_status nonprimary_failures sparse_threshold_rows
  run_status="$(awk -F, '$1=="run" && $2=="status" {print $3}' "${summary_file}" | tr -d '\r\"')"
  if [[ "${run_status}" != "PASS" && "${run_status}" != "PASS_WITH_SPARSE_MODEL_FAILURES" ]]; then
    echo "ERROR: unexpected ${scope} run status: ${run_status}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  nonprimary_failures="$(awk -F, '$1=="models" && $2=="nonprimary_failure_jobs" {print $3}' "${summary_file}" | tr -d '\r\"')"
  sparse_threshold_rows="$(awk -F, '$1=="support" && $2=="sparse_threshold_rows" {print $3}' "${summary_file}" | tr -d '\r\"')"

  {
    echo "${scope} status:                     ${run_status}"
    echo "${scope} static effect rows:         ${static_rows}"
    echo "${scope} dynamic/placebo rows:       ${dynamic_rows}"
    echo "${scope} primary static rows:        ${primary_static_rows}"
    echo "${scope} primary total static rows:  ${primary_total_static_rows}"
    echo "${scope} primary total dynamic rows: ${primary_total_dynamic_rows}"
    echo "${scope} sparse support rows:        ${sparse_threshold_rows}"
    echo "${scope} non-primary failures:       ${nonprimary_failures}"
    echo "${scope} QC status:                  PASS"
  } | tee -a "${LOG_FILE}"
}

run_scope "RF"
run_scope "CM"

{
  echo
  echo "============================================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Status:                          PASS"
  echo "Localization scopes:             RF + CM"
  echo "Total model jobs:                1472 (736 per scope)"
  echo "Total static effect rows:        1472"
  echo "Total dynamic/placebo rows:      17664"
  echo "RF primary static results:       ${OUTPUT_ROOT}/rf/quality_npr_rf_primary_total_static.csv"
  echo "RF primary dynamic results:      ${OUTPUT_ROOT}/rf/quality_npr_rf_primary_total_dynamic.csv"
  echo "CM primary static results:       ${OUTPUT_ROOT}/cm/quality_npr_cm_primary_total_static.csv"
  echo "CM primary dynamic results:      ${OUTPUT_ROOT}/cm/quality_npr_cm_primary_total_dynamic.csv"
  echo "Combined RF+CM reference:        repo_x01/run-x-l02/borusyak-threshold-quality-v1"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            compare RF, CM, and frozen RF+CM primary estimates and pretrends"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
