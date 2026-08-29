#!/usr/bin/env bash

set -euo pipefail

# ================================================================
# run-x-i09 v1: Borusyak DiD for frozen combined-ML quality burden
# ================================================================
#
# Purpose:
#   Estimate the causal effect of Cursor adoption on unresolved SonarQube issue
#   burden among Python files selected by the frozen combined regular-function +
#   class-method ML threshold grid prepared by run-x-i08.
#
# Primary input:
#   repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_panel.csv.gz
#
# Upstream provenance/QC inputs:
#   repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_summary.csv
#   repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_checks.csv
#   repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_sample_summary.csv
#   repo_x01/run-x-i08/quality_ml_fun_cfun_threshold_input_global_audit.csv
#
# Frozen analysis dimensions:
#   - 21 strict ML thresholds: 0.10:0.90 by 0.04.
#   - Primary threshold: > 0.50.
#   - 2 samples: full_sample and exclude_scope_mismatch_repos.
#   - 2 model specifications: adjusted_burden and fe_only_burden.
#   - 8 selected-file unresolved SonarQube burden outcomes.
#
# Estimation:
#   - didimputation::did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic effects at event 0:+6.
#   - Placebo/pretrend terms at event -6:-2.
#   - Event -1 omitted.
#
# Treatment timing:
#   The R program reconstructs treatment only from event_index and time_index.
#   Legacy post_event/time_to_event fields never define treatment status.
#
# This wrapper is standalone. It was copied from the validated run-x-i05 shell
# structure and adapted for run-x-i08 combined-ML inputs. It does not call any
# previous experiment wrapper.
#
# Distributed versioned files:
#   proc_script_x01/did_borusyak_ml_fun_cfun_threshold_quality-v1.R
#   proc_sh_x01/run-x-i09-did-borusyak-ml-fun-cfun-threshold-quality-v1.sh
#
# Canonical server names:
#   proc_script_x01/did_borusyak_ml_fun_cfun_threshold_quality.R
#   proc_sh_x01/run-x-i09-did-borusyak-ml-fun-cfun-threshold-quality.sh
# ================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i09"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-ml-fun-cfun-threshold-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_ml_fun_cfun_threshold_quality.R}"
I08_ROOT="${I08_ROOT:-repo_x01/run-x-i08}"
INPUT_FILE="${INPUT_FILE:-${I08_ROOT}/quality_ml_fun_cfun_threshold_input_panel.csv.gz}"
INPUT_SUMMARY_FILE="${INPUT_SUMMARY_FILE:-${I08_ROOT}/quality_ml_fun_cfun_threshold_input_summary.csv}"
INPUT_CHECKS_FILE="${INPUT_CHECKS_FILE:-${I08_ROOT}/quality_ml_fun_cfun_threshold_input_checks.csv}"
INPUT_SAMPLE_SUMMARY_FILE="${INPUT_SAMPLE_SUMMARY_FILE:-${I08_ROOT}/quality_ml_fun_cfun_threshold_input_sample_summary.csv}"
INPUT_GLOBAL_AUDIT_FILE="${INPUT_GLOBAL_AUDIT_FILE:-${I08_ROOT}/quality_ml_fun_cfun_threshold_input_global_audit.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
EXPECTED_LONG_ROWS="${EXPECTED_LONG_ROWS:-81249}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-21}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
OVERWRITE="${OVERWRITE:-0}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

EXPECTED_STATIC_ROWS=672
EXPECTED_DYNAMIC_ROWS=8064
EXPECTED_PRETREND_ROWS=3360
EXPECTED_PRETREND_SUMMARY_ROWS=672
EXPECTED_DIAGNOSTIC_ROWS=2016
EXPECTED_FAILURE_ROWS=0
EXPECTED_THRESHOLD_SUPPORT_ROWS=42
EXPECTED_EVENT_SUPPORT_ROWS=546
EXPECTED_SUPPORT_POLICY_ROWS=1
EXPECTED_PRIMARY_THRESHOLD_STATIC_ROWS=32
EXPECTED_PRIMARY_TOTAL_STATIC_ROWS=4
EXPECTED_PRIMARY_TOTAL_DYNAMIC_ROWS=48
EXPECTED_TOTAL_THRESHOLD_STATIC_ROWS=84
EXPECTED_TOTAL_THRESHOLD_DYNAMIC_ROWS=1008
EXPECTED_QC_ROWS=20
EXPECTED_SUMMARY_ROWS=23
EXPECTED_METADATA_ROWS=32

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: missing ${label}: ${path}" >&2
    exit 1
  fi
}

count_csv_rows() {
  local path="$1"
  echo $(( $(wc -l < "${path}") - 1 ))
}

check_csv_rows() {
  local path="$1"
  local expected="$2"
  local label="$3"
  local observed
  observed="$(count_csv_rows "${path}")"
  if [[ "${observed}" -ne "${expected}" ]]; then
    echo "ERROR: ${label} row count mismatch: expected ${expected}, observed ${observed}: ${path}" >&2
    exit 1
  fi
  echo "OK: ${label}: ${observed} rows"
}

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

require_file "${R_SCRIPT}" "I09 Borusyak R program"

for integer_value in \
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_LONG_ROWS}" "${EXPECTED_THRESHOLDS}" "${EXPECTED_SAMPLE_SPECS}" \
  "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}" "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

for binary_value in "${STRICT_EXPECTED_COUNTS}" "${OVERWRITE}" "${SELF_TEST_ONLY}"; do
  if [[ "${binary_value}" != "0" && "${binary_value}" != "1" ]]; then
    echo "ERROR: Boolean options must be 0 or 1; observed ${binary_value}." >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: combined-ML threshold quality-burden Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "I08 input panel:                 ${INPUT_FILE}"
  echo "I08 summary:                     ${INPUT_SUMMARY_FILE}"
  echo "I08 checks:                      ${INPUT_CHECKS_FILE}"
  echo "I08 sample summary:              ${INPUT_SAMPLE_SUMMARY_FILE}"
  echo "I08 global audit:                ${INPUT_GLOBAL_AUDIT_FILE}"
  echo "Threshold grid:                  0.10:0.90 by 0.04 (21 points)"
  echo "Primary rule:                    file_ml_fun_cfun_agc_share_space_by_token_weighted > 0.50"
  echo "Samples:                         full_sample + exclude_scope_mismatch_repos"
  echo "Expected long rows:              ${EXPECTED_LONG_ROWS}"
  echo "Expected model jobs:             ${EXPECTED_STATIC_ROWS}"
  echo "Model specs:                     adjusted_burden + fe_only_burden"
  echo "Burden outcomes:                 8"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event:                 -1"
  echo "Threshold recalibration:         none"
  echo "Density:                         not computed"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run I09 structural self-test"
  echo "----------------------------------------------------------------------------"
  echo "Command: ${RSCRIPT_BIN} ${R_SCRIPT} --self-test"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse I09 R program"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "invisible(parse(file='${R_SCRIPT}')); cat('R parse: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL}: SELF-TEST PASS" | tee -a "${LOG_FILE}"
  exit 0
fi

for input_path in \
  "${INPUT_FILE}" "${INPUT_SUMMARY_FILE}" "${INPUT_CHECKS_FILE}" \
  "${INPUT_SAMPLE_SUMMARY_FILE}" "${INPUT_GLOBAL_AUDIT_FILE}"; do
  require_file "${input_path}" "required I08 production input"
done

# Exact-column preflight checks avoid the bare-zero grep bug fixed in I08.
I08_STATUS="$(awk -F, '$1=="status" {gsub(/\r/,"",$2); print $2}' "${INPUT_SUMMARY_FILE}")"
I08_HARD_QC="$(awk -F, '$1=="hard_qc_failures" {gsub(/\r/,"",$2); print $2}' "${INPUT_SUMMARY_FILE}")"
I08_I07_MISMATCH="$(awk -F, '$1=="i07_threshold_reproduction_mismatches" {gsub(/\r/,"",$2); print $2}' "${INPUT_SUMMARY_FILE}")"
if [[ "${I08_STATUS}" != "PASS" ]]; then
  echo "ERROR: I08 summary status is not PASS: ${I08_STATUS}" >&2
  exit 1
fi
if [[ "${I08_HARD_QC}" != "0" ]]; then
  echo "ERROR: I08 hard_qc_failures is not zero: ${I08_HARD_QC}" >&2
  exit 1
fi
if [[ "${I08_I07_MISMATCH}" != "0" ]]; then
  echo "ERROR: I08 does not exactly reproduce I07-v2 thresholds: ${I08_I07_MISMATCH}" >&2
  exit 1
fi

if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally rebuilding I09." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
SUMMARY_SHA256="$(sha256sum "${INPUT_SUMMARY_FILE}" | awk '{print $1}')"
CHECKS_SHA256="$(sha256sum "${INPUT_CHECKS_FILE}" | awk '{print $1}')"
SAMPLE_SUMMARY_SHA256="$(sha256sum "${INPUT_SAMPLE_SUMMARY_FILE}" | awk '{print $1}')"
GLOBAL_AUDIT_SHA256="$(sha256sum "${INPUT_GLOBAL_AUDIT_FILE}" | awk '{print $1}')"

{
  echo
  echo "** Step 3: Freeze I08 provenance"
  echo "----------------------------------------------------------------------------"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "I08 panel SHA256:                ${INPUT_SHA256}"
  echo "I08 summary SHA256:              ${SUMMARY_SHA256}"
  echo "I08 checks SHA256:               ${CHECKS_SHA256}"
  echo "I08 sample summary SHA256:       ${SAMPLE_SUMMARY_SHA256}"
  echo "I08 global audit SHA256:         ${GLOBAL_AUDIT_SHA256}"
  echo "I08 upstream status:             ${I08_STATUS}"
  echo "I08 hard QC failures:            ${I08_HARD_QC}"
  echo "I07-v2 reproduction mismatches:  ${I08_I07_MISMATCH}"
} | tee -a "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --input-summary-file "${INPUT_SUMMARY_FILE}"
  --input-checks-file "${INPUT_CHECKS_FILE}"
  --input-sample-summary-file "${INPUT_SAMPLE_SUMMARY_FILE}"
  --input-global-audit-file "${INPUT_GLOBAL_AUDIT_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --expected-long-rows "${EXPECTED_LONG_ROWS}"
  --expected-thresholds "${EXPECTED_THRESHOLDS}"
  --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
  --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
  --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
)

{
  echo
  echo "** Step 4: Run I09 frozen-threshold Borusyak DiD"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_static_effects.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_dynamic_effects.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_pretrend_checks.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_pretrend_summary.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_model_diagnostics.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_model_failures.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_support.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_event_support.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_support_policy.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_static.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_total_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_total_threshold_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_qc.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_summary.csv"
  "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_run_metadata.csv"
)

{
  echo
  echo "** Step 5: Verify I09 output artifacts and exact row contracts"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_path in "${EXPECTED_OUTPUTS[@]}"; do
  require_file "${output_path}" "I09 output artifact"
  echo "OK: ${output_path}" | tee -a "${LOG_FILE}"
done

{
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_static_effects.csv" "${EXPECTED_STATIC_ROWS}" "static effects"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_dynamic_effects.csv" "${EXPECTED_DYNAMIC_ROWS}" "dynamic effects"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_pretrend_checks.csv" "${EXPECTED_PRETREND_ROWS}" "pretrend checks"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_pretrend_summary.csv" "${EXPECTED_PRETREND_SUMMARY_ROWS}" "pretrend summary"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_model_diagnostics.csv" "${EXPECTED_DIAGNOSTIC_ROWS}" "model diagnostics"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_model_failures.csv" "${EXPECTED_FAILURE_ROWS}" "model failures"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_support.csv" "${EXPECTED_THRESHOLD_SUPPORT_ROWS}" "threshold support"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_event_support.csv" "${EXPECTED_EVENT_SUPPORT_ROWS}" "event support"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_support_policy.csv" "${EXPECTED_SUPPORT_POLICY_ROWS}" "support policy"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_threshold_static.csv" "${EXPECTED_PRIMARY_THRESHOLD_STATIC_ROWS}" "primary threshold static"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_static.csv" "${EXPECTED_PRIMARY_TOTAL_STATIC_ROWS}" "primary total static"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_dynamic.csv" "${EXPECTED_PRIMARY_TOTAL_DYNAMIC_ROWS}" "primary total dynamic"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_total_threshold_static.csv" "${EXPECTED_TOTAL_THRESHOLD_STATIC_ROWS}" "total threshold static"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_total_threshold_dynamic.csv" "${EXPECTED_TOTAL_THRESHOLD_DYNAMIC_ROWS}" "total threshold dynamic"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_qc.csv" "${EXPECTED_QC_ROWS}" "QC"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_summary.csv" "${EXPECTED_SUMMARY_ROWS}" "summary"
  check_csv_rows "${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_run_metadata.csv" "${EXPECTED_METADATA_ROWS}" "metadata"
} 2>&1 | tee -a "${LOG_FILE}"

"${RSCRIPT_BIN}" -e "qc<-data.table::fread('${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_qc.csv'); if(any(qc\$status!='pass')) stop(paste('I09 QC failed:', paste(qc\$check[qc\$status!='pass'], collapse=', '))); s<-data.table::fread('${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_summary.csv'); status<-s\$value[s\$metric=='status']; if(length(status)!=1L || status!='PASS') stop(paste('I09 summary status:', paste(status, collapse='|'))); cat('I09 QC: PASS\nI09 summary: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

FINISHED_AT="$(date '+%Y-%m-%d %H:%M:%S %Z')"
{
  echo "================================================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        ${FINISHED_AT}"
  echo "Thresholds:                      21"
  echo "Sample specifications:           2"
  echo "Model jobs:                      ${EXPECTED_STATIC_ROWS}"
  echo "Static rows:                     ${EXPECTED_STATIC_ROWS}"
  echo "Dynamic rows:                    ${EXPECTED_DYNAMIC_ROWS}"
  echo "Primary cutoff:                  > 0.50"
  echo "Primary static:                  ${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_static.csv"
  echo "Primary dynamic:                 ${OUTPUT_DIR}/quality_ml_fun_cfun_primary_total_dynamic.csv"
  echo "Threshold sensitivity:           ${OUTPUT_DIR}/quality_ml_fun_cfun_total_threshold_static.csv"
  echo "QC:                              ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_qc.csv"
  echo "Summary:                         ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_summary.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            analyze I09 primary and threshold-sensitivity effects"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
