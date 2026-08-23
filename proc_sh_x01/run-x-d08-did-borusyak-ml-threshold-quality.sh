#!/usr/bin/env bash
set -euo pipefail

# ====================================================================
# run-x-d08 v2: Borusyak DiD across ML file-composition thresholds
# ====================================================================
#
# Purpose:
#   Estimate static and dynamic Cursor-adoption effects for the 21 ML
#   file-composition thresholds prepared by run-x-d07.
#
# Authoritative D07 input:
#   repo_x01/run-x-d07/quality_ml_threshold_repo_month_panel.csv.gz
#
# Supporting D07 provenance/QC inputs:
#   quality_ml_threshold_summary.csv
#   quality_ml_threshold_checks.csv
#   quality_ml_threshold_sample_summary.csv
#   quality_ml_threshold_global_audit.csv
#
# D06 reproduction references:
#   quality_ml_primary_total_static.csv
#   quality_ml_primary_total_dynamic.csv
#
# Threshold contract:
#   0.10, 0.14, ..., 0.50, ..., 0.86, 0.90 (21 thresholds)
#   strict rule: file_ml_agc_share_space_by_token_weighted > threshold
#   primary threshold: > 0.50
#
# Estimation contract:
#   - two samples: full_sample and exclude_scope_mismatch_repos
#   - two burden specifications: adjusted_burden and fe_only_burden
#   - eight selected-file SonarQube issue-stock outcomes
#   - didimputation::did_imputation with repository-clustered SE
#   - static ATT over all post-adoption observations
#   - dynamic event 0:+6 and placebo/pretrend event -6:-2
#   - event -1 omitted reference
#   - no density outcome
#
# This wrapper was copied from the established standalone Borusyak wrapper
# structure and adapted for D08. It does not call any previous shell wrapper.
#
# Deployment convention:
#   Distributed source:
#     proc_script_x01/did_borusyak_ml_threshold_quality-v2.R
#     proc_sh_x01/run-x-d08-did-borusyak-ml-threshold-quality-v2.sh
#   Canonical server names:
#     proc_script_x01/did_borusyak_ml_threshold_quality.R
#     proc_sh_x01/run-x-d08-did-borusyak-ml-threshold-quality.sh
# ====================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d08"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-ml-threshold-quality-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_ml_threshold_quality.R}"
D07_ROOT="${D07_ROOT:-repo_x01/run-x-d07}"
D06_ROOT="${D06_ROOT:-repo_x01/run-x-d06}"
INPUT_FILE="${INPUT_FILE:-${D07_ROOT}/quality_ml_threshold_repo_month_panel.csv.gz}"
D07_SUMMARY_FILE="${D07_SUMMARY_FILE:-${D07_ROOT}/quality_ml_threshold_summary.csv}"
D07_CHECKS_FILE="${D07_CHECKS_FILE:-${D07_ROOT}/quality_ml_threshold_checks.csv}"
D07_SAMPLE_SUMMARY_FILE="${D07_SAMPLE_SUMMARY_FILE:-${D07_ROOT}/quality_ml_threshold_sample_summary.csv}"
D07_GLOBAL_AUDIT_FILE="${D07_GLOBAL_AUDIT_FILE:-${D07_ROOT}/quality_ml_threshold_global_audit.csv}"
D06_STATIC_REFERENCE_FILE="${D06_STATIC_REFERENCE_FILE:-${D06_ROOT}/quality_ml_primary_total_static.csv}"
D06_DYNAMIC_REFERENCE_FILE="${D06_DYNAMIC_REFERENCE_FILE:-${D06_ROOT}/quality_ml_primary_total_dynamic.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-d08}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_LONG_ROWS="${EXPECTED_LONG_ROWS:-81249}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-21}"
EXPECTED_SAMPLE_SPECS="${EXPECTED_SAMPLE_SPECS:-2}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
D06_REPRODUCTION_TOLERANCE="${D06_REPRODUCTION_TOLERANCE:-1e-10}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

EXPECTED_STATIC_ROWS=672
EXPECTED_DYNAMIC_ROWS=8064
EXPECTED_PRETREND_ROWS=3360
EXPECTED_PRETREND_SUMMARY_ROWS=672
EXPECTED_PRIMARY_THRESHOLD_STATIC_ROWS=32
EXPECTED_PRIMARY_TOTAL_STATIC_ROWS=4
EXPECTED_PRIMARY_TOTAL_DYNAMIC_ROWS=48
EXPECTED_TOTAL_THRESHOLD_STATIC_ROWS=84
EXPECTED_TOTAL_THRESHOLD_DYNAMIC_ROWS=1008
EXPECTED_THRESHOLD_SUPPORT_ROWS=42
EXPECTED_EVENT_SUPPORT_ROWS=546
EXPECTED_D06_REPRODUCTION_ROWS=130

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

REQUIRED_FILES=(
  "${R_SCRIPT}"
  "${INPUT_FILE}"
  "${D07_SUMMARY_FILE}"
  "${D07_CHECKS_FILE}"
  "${D07_SAMPLE_SUMMARY_FILE}"
  "${D07_GLOBAL_AUDIT_FILE}"
  "${D06_STATIC_REFERENCE_FILE}"
  "${D06_DYNAMIC_REFERENCE_FILE}"
)
for required_file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for integer_value in \
  "${PLOT_MIN_EVENT}" "${PLOT_MAX_EVENT}" "${PRETREND_MIN}" "${PRETREND_MAX}" \
  "${EXPECTED_LONG_ROWS}" "${EXPECTED_THRESHOLDS}" "${EXPECTED_SAMPLE_SPECS}" \
  "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}" "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi
if [[ "${SELF_TEST_ONLY}" != "0" && "${SELF_TEST_ONLY}" != "1" ]]; then
  echo "ERROR: SELF_TEST_ONLY must be 0 or 1." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
D07_SUMMARY_SHA256="$(sha256sum "${D07_SUMMARY_FILE}" | awk '{print $1}')"
D07_CHECKS_SHA256="$(sha256sum "${D07_CHECKS_FILE}" | awk '{print $1}')"
D07_SAMPLE_SUMMARY_SHA256="$(sha256sum "${D07_SAMPLE_SUMMARY_FILE}" | awk '{print $1}')"
D07_GLOBAL_AUDIT_SHA256="$(sha256sum "${D07_GLOBAL_AUDIT_FILE}" | awk '{print $1}')"
D06_STATIC_SHA256="$(sha256sum "${D06_STATIC_REFERENCE_FILE}" | awk '{print $1}')"
D06_DYNAMIC_SHA256="$(sha256sum "${D06_DYNAMIC_REFERENCE_FILE}" | awk '{print $1}')"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: ML-threshold SonarQube quality Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Experiment role:                 D07 threshold panel -> Borusyak DiD"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "D07 long panel:                  ${INPUT_FILE}"
  echo "D07 long panel SHA256:           ${INPUT_SHA256}"
  echo "D07 summary SHA256:              ${D07_SUMMARY_SHA256}"
  echo "D07 checks SHA256:               ${D07_CHECKS_SHA256}"
  echo "D07 sample summary SHA256:       ${D07_SAMPLE_SUMMARY_SHA256}"
  echo "D07 global audit SHA256:         ${D07_GLOBAL_AUDIT_SHA256}"
  echo "D06 static reference SHA256:     ${D06_STATIC_SHA256}"
  echo "D06 dynamic reference SHA256:    ${D06_DYNAMIC_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "ML metric:                       file_ml_agc_share_space_by_token_weighted"
  echo "Threshold rule:                  strict > cutoff"
  echo "Threshold grid:                  0.10:0.90 by 0.04 (21 points)"
  echo "Primary threshold:               0.50"
  echo "Samples:                         full_sample + exclude_scope_mismatch_repos"
  echo "Mapping:                         all_ml_files"
  echo "Model specs:                     adjusted_burden + fe_only_burden"
  echo "Burden outcomes:                 8"
  echo "Model jobs:                      672"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Density:                         not computed"
  echo "D06 reproduction tolerance:      ${D06_REPRODUCTION_TOLERANCE}"
  echo "Expected D07 long rows:          ${EXPECTED_LONG_ROWS}"
  echo "Expected static/dynamic rows:    ${EXPECTED_STATIC_ROWS}/${EXPECTED_DYNAMIC_ROWS}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run D08 structural self-test"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse D08 R program"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}')" >/dev/null 2>>"${LOG_FILE}"
echo "R parse: PASS" | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  {
    echo
    echo "SELF_TEST_ONLY=1: stopping after package, self-test, and R parse checks."
    echo "${RUN_LABEL}: SELF-TEST PASS"
  } | tee -a "${LOG_FILE}"
  exit 0
fi

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --d07-summary-file "${D07_SUMMARY_FILE}"
  --d07-checks-file "${D07_CHECKS_FILE}"
  --d07-sample-summary-file "${D07_SAMPLE_SUMMARY_FILE}"
  --d07-global-audit-file "${D07_GLOBAL_AUDIT_FILE}"
  --d06-static-reference-file "${D06_STATIC_REFERENCE_FILE}"
  --d06-dynamic-reference-file "${D06_DYNAMIC_REFERENCE_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-long-rows "${EXPECTED_LONG_ROWS}"
  --expected-thresholds "${EXPECTED_THRESHOLDS}"
  --expected-sample-specs "${EXPECTED_SAMPLE_SPECS}"
  --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
  --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  --d06-reproduction-tolerance "${D06_REPRODUCTION_TOLERANCE}"
)

{
  echo
  echo "** Step 3: Run 21-threshold ML-quality Borusyak DiD"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_ml_threshold_static_effects.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_dynamic_effects.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_pretrend_checks.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_pretrend_summary.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_model_diagnostics.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_model_failures.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_support.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_event_support.csv"
  "${OUTPUT_DIR}/quality_ml_support_policy.csv"
  "${OUTPUT_DIR}/quality_ml_primary_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_primary_total_static.csv"
  "${OUTPUT_DIR}/quality_ml_primary_total_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_total_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_total_threshold_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_d06_reproduction.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_qc.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_summary.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_run_metadata.csv"
)

{
  echo
  echo "** Step 4: Verify D08 artifacts and hard QC"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/quality_ml_threshold_qc.csv"
if grep -Eiq '(^|,)fail(,|$)' "${QC_FILE}"; then
  echo "ERROR: D08 QC contains one or more failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${QC_FILE}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

REPRO_FILE="${OUTPUT_DIR}/quality_ml_d06_reproduction.csv"
if grep -Eiq '(^|,)fail(,|$)' "${REPRO_FILE}"; then
  echo "ERROR: D08 does not reproduce D06 at the primary 0.50 threshold." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

count_rows() {
  local path="$1"
  echo $(( $(wc -l < "${path}") - 1 ))
}

STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_static_effects.csv")"
DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_dynamic_effects.csv")"
PRETREND_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_pretrend_checks.csv")"
PRETREND_SUMMARY_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_pretrend_summary.csv")"
PRIMARY_THRESHOLD_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_primary_threshold_static.csv")"
PRIMARY_TOTAL_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_primary_total_static.csv")"
PRIMARY_TOTAL_DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_primary_total_dynamic.csv")"
TOTAL_THRESHOLD_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_total_threshold_static.csv")"
TOTAL_THRESHOLD_DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_total_threshold_dynamic.csv")"
THRESHOLD_SUPPORT_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_support.csv")"
EVENT_SUPPORT_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_threshold_event_support.csv")"
D06_REPRODUCTION_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_d06_reproduction.csv")"

EXPECTED_ACTUAL_PAIRS=(
  "static:${STATIC_ROWS}:${EXPECTED_STATIC_ROWS}"
  "dynamic:${DYNAMIC_ROWS}:${EXPECTED_DYNAMIC_ROWS}"
  "pretrend:${PRETREND_ROWS}:${EXPECTED_PRETREND_ROWS}"
  "pretrend_summary:${PRETREND_SUMMARY_ROWS}:${EXPECTED_PRETREND_SUMMARY_ROWS}"
  "primary_threshold_static:${PRIMARY_THRESHOLD_STATIC_ROWS}:${EXPECTED_PRIMARY_THRESHOLD_STATIC_ROWS}"
  "primary_total_static:${PRIMARY_TOTAL_STATIC_ROWS}:${EXPECTED_PRIMARY_TOTAL_STATIC_ROWS}"
  "primary_total_dynamic:${PRIMARY_TOTAL_DYNAMIC_ROWS}:${EXPECTED_PRIMARY_TOTAL_DYNAMIC_ROWS}"
  "total_threshold_static:${TOTAL_THRESHOLD_STATIC_ROWS}:${EXPECTED_TOTAL_THRESHOLD_STATIC_ROWS}"
  "total_threshold_dynamic:${TOTAL_THRESHOLD_DYNAMIC_ROWS}:${EXPECTED_TOTAL_THRESHOLD_DYNAMIC_ROWS}"
  "threshold_support:${THRESHOLD_SUPPORT_ROWS}:${EXPECTED_THRESHOLD_SUPPORT_ROWS}"
  "event_support:${EVENT_SUPPORT_ROWS}:${EXPECTED_EVENT_SUPPORT_ROWS}"
  "d06_reproduction:${D06_REPRODUCTION_ROWS}:${EXPECTED_D06_REPRODUCTION_ROWS}"
)
for triple in "${EXPECTED_ACTUAL_PAIRS[@]}"; do
  name="${triple%%:*}"
  rest="${triple#*:}"
  actual="${rest%%:*}"
  expected="${rest##*:}"
  if [[ "${actual}" -ne "${expected}" ]]; then
    echo "ERROR: D08 ${name} row count expected ${expected}, observed ${actual}." | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

SPARSE_ROWS="$(awk -F',' 'NR==1 {for (i=1; i<=NF; i++) if ($i=="sparse_support_flag") col=i; next} col>0 && $col==1 {n++} END {print n+0}' "${OUTPUT_DIR}/quality_ml_threshold_support.csv")"

{
  echo "D06 primary reproduction:        PASS"
  echo "D08 hard QC:                     PASS"
  echo "Static effect rows:              ${STATIC_ROWS}"
  echo "Dynamic/placebo rows:            ${DYNAMIC_ROWS}"
  echo "Total-threshold dynamic rows:    ${TOTAL_THRESHOLD_DYNAMIC_ROWS}"
  echo "Threshold support rows:          ${THRESHOLD_SUPPORT_ROWS}"
  echo "Sparse threshold-sample rows:    ${SPARSE_ROWS}"
  echo "================================================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Thresholds:                      21"
  echo "Sample specifications:           2"
  echo "Model jobs:                      672"
  echo "Primary cutoff:                  > 0.50"
  echo "D06 0.50 reproduction:           PASS"
  echo "QC status:                       PASS"
  echo "Threshold static results:        ${OUTPUT_DIR}/quality_ml_total_threshold_static.csv"
  echo "Threshold dynamic results:       ${OUTPUT_DIR}/quality_ml_total_threshold_dynamic.csv"
  echo "Primary dynamic results:         ${OUTPUT_DIR}/quality_ml_primary_total_dynamic.csv"
  echo "Threshold support:               ${OUTPUT_DIR}/quality_ml_threshold_support.csv"
  echo "QC:                              ${OUTPUT_DIR}/quality_ml_threshold_qc.csv"
  echo "Metadata:                        ${OUTPUT_DIR}/quality_ml_threshold_run_metadata.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
