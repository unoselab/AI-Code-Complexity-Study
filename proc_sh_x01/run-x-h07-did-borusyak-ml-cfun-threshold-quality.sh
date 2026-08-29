#!/usr/bin/env bash
set -euo pipefail

# ====================================================================
# run-x-h07 v1: C_FUN ML-threshold quality burden + Borusyak DiD
# ====================================================================
#
# Purpose:
#   Build the 21-threshold C_FUN ML quality-burden panel and estimate the
#   corresponding Borusyak static/dynamic treatment effects before plotting.
#
# Scientific lineage:
#   A07  continuous C_FUN ML file score
#     + D02 canonical historical Python SonarQube file burden
#     + B06 matched repo-month panel
#     + H05 primary C_FUN ML burden reference
#       -> H07 threshold x sample repo-month input
#       -> H07 Borusyak threshold-sensitivity DiD
#
# Threshold contract:
#   - metric: file_ml_cfun_agc_share_space_by_token_weighted
#   - strict selection rule: metric > threshold
#   - grid: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90 (21 thresholds)
#   - frozen primary threshold: > 0.50
#   - mapping specification: all_ml_files
#   - samples: full_sample and exclude_scope_mismatch_repos
#
# Reproduction gates:
#   1. The threshold-input stage must reproduce H05 at >0.50 for both samples.
#   2. The DiD stage must numerically reproduce H06 full-sample primary total
#      static and dynamic estimates at >0.50.
#
# Estimation contract:
#   - adjusted_burden and fe_only_burden
#   - 8 unresolved SonarQube issue-stock burden outcomes
#   - didimputation::did_imputation with repository-clustered SE
#   - static ATT over all post-adoption observations
#   - event 0:+6 and placebo/pretrend -6:-2; event -1 omitted
#   - no density outcome
#
# This wrapper is standalone. It was adapted from the validated D08/H06 shell
# structures and does not call any previous experiment wrapper.
#
# Distributed versioned files:
#   proc_script_x01/build_ml_cfun_threshold_quality_burden_panel-v1.py
#   proc_script_x01/did_borusyak_ml_cfun_threshold_quality-v1.R
#   proc_sh_x01/run-x-h07-did-borusyak-ml-cfun-threshold-quality-v1.sh
#
# Canonical server names:
#   proc_script_x01/build_ml_cfun_threshold_quality_burden_panel.py
#   proc_script_x01/did_borusyak_ml_cfun_threshold_quality.R
#   proc_sh_x01/run-x-h07-did-borusyak-ml-cfun-threshold-quality.sh
# ====================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-h07"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-ml-cfun-threshold-quality-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PREP_SCRIPT="${PREP_SCRIPT:-proc_script_x01/build_ml_cfun_threshold_quality_burden_panel.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_ml_cfun_threshold_quality.R}"

# Frozen A07 C_FUN ML file-score source from the sibling ai_detector workspace.
A07_ROOT="${A07_ROOT:-${PROJECT_ROOT}/../../ai_detector/src/app/data_did_agc_analysis/run-x-a07}"
A07_FILE="${A07_FILE:-${A07_ROOT}/python_ml_cfun_file_scores.csv}"

# Detector-neutral historical SonarQube burden and B06 panel used by H05.
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

# H05 is the authoritative >0.50 C_FUN ML burden reference.
H05_ROOT="${H05_ROOT:-repo_x01/run-x-h05}"
H05_REFERENCE_FILE="${H05_REFERENCE_FILE:-${H05_ROOT}/quality_ml_cfun_repo_month_panel.csv.gz}"
H05_SUMMARY_FILE="${H05_SUMMARY_FILE:-${H05_ROOT}/quality_ml_cfun_summary.csv}"
H05_CHECKS_FILE="${H05_CHECKS_FILE:-${H05_ROOT}/quality_ml_cfun_checks.csv}"

# H06 is the authoritative primary DiD reference at >0.50.
H06_ROOT="${H06_ROOT:-repo_x01/run-x-h06}"
H06_STATIC_REFERENCE_FILE="${H06_STATIC_REFERENCE_FILE:-${H06_ROOT}/quality_ml_cfun_primary_total_static.csv}"
H06_DYNAMIC_REFERENCE_FILE="${H06_DYNAMIC_REFERENCE_FILE:-${H06_ROOT}/quality_ml_cfun_primary_total_dynamic.csv}"
H06_QC_FILE="${H06_QC_FILE:-${H06_ROOT}/quality_ml_cfun_qc.csv}"
H06_SUMMARY_FILE="${H06_SUMMARY_FILE:-${H06_ROOT}/quality_ml_cfun_summary.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-h07}"
OVERWRITE="${OVERWRITE:-0}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

# H07 threshold-input artifacts.
INPUT_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_panel.csv.gz"
INPUT_SUMMARY_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_summary.csv"
INPUT_CHECKS_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_checks.csv"
INPUT_SAMPLE_SUMMARY_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_sample_summary.csv"
INPUT_GLOBAL_AUDIT_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_global_audit.csv"
INPUT_REPRODUCTION_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_h05_reproduction.csv"
INPUT_METADATA_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_input_metadata.json"

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
H06_REPRODUCTION_TOLERANCE="${H06_REPRODUCTION_TOLERANCE:-1e-10}"

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
EXPECTED_H06_REPRODUCTION_ROWS=130

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: missing ${label}: ${path}" >&2
    exit 1
  fi
}

count_rows() {
  local path="$1"
  echo $(( $(wc -l < "${path}") - 1 ))
}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi
require_file "${PREP_SCRIPT}" "H07 threshold-input Python program"
require_file "${R_SCRIPT}" "H07 Borusyak R program"

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

# Run structural checks before touching production outputs.
{
  echo "================================================================================"
  echo "${RUN_LABEL}: C_FUN ML-threshold quality burden + Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python script:                   ${PREP_SCRIPT}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "Threshold grid:                  0.10:0.90 by 0.04 (21 points)"
  echo "Primary rule:                    file_ml_cfun_agc_share_space_by_token_weighted > 0.50"
  echo "Samples:                         full_sample + exclude_scope_mismatch_repos"
  echo "Mapping:                         all_ml_files"
  echo "Expected threshold-panel rows:   ${EXPECTED_LONG_ROWS}"
  echo "Expected model jobs:             ${EXPECTED_STATIC_ROWS}"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run H07 structural self-tests"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${PREP_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Compile/parse H07 programs"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" -m py_compile "${PREP_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}')" >/dev/null 2>>"${LOG_FILE}"
echo "Python compile: PASS" | tee -a "${LOG_FILE}"
echo "R parse: PASS" | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL}: SELF-TEST PASS" | tee -a "${LOG_FILE}"
  exit 0
fi

# Production inputs are required only after structural self-tests pass.
for input_path in \
  "${A07_FILE}" "${D02_FILE}" "${B06_PANEL_FILE}" \
  "${H05_REFERENCE_FILE}" "${H05_SUMMARY_FILE}" "${H05_CHECKS_FILE}" \
  "${H06_STATIC_REFERENCE_FILE}" "${H06_DYNAMIC_REFERENCE_FILE}" \
  "${H06_QC_FILE}" "${H06_SUMMARY_FILE}"; do
  require_file "${input_path}" "required H07 production input"
done

# Refuse to build on failed H05/H06 upstream analyses.
if grep -Eiq '(^|,)fail(,|$)' "${H05_CHECKS_FILE}"; then
  echo "ERROR: H05 checks contain a failed row." >&2
  exit 1
fi
if grep -Eiq '(^|,)fail(,|$)' "${H06_QC_FILE}"; then
  echo "ERROR: H06 QC contains a failed row." >&2
  exit 1
fi
if ! grep -Eq '^status,PASS$|^status,PASS\r$' "${H05_SUMMARY_FILE}"; then
  echo "ERROR: H05 summary does not report status,PASS." >&2
  exit 1
fi
if ! grep -Eq '^run,status,PASS(,|$)' "${H06_SUMMARY_FILE}"; then
  echo "ERROR: H06 summary does not report PASS." >&2
  exit 1
fi

if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally rebuilding H07." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")')"
PREP_SHA256="$(sha256sum "${PREP_SCRIPT}" | awk '{print $1}')"
R_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo
  echo "** Step 3: Record H07 frozen provenance"
  echo "----------------------------------------------------------------------------"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Prep script SHA256:              ${PREP_SHA256}"
  echo "R script SHA256:                 ${R_SHA256}"
  echo "A07 file SHA256:                 $(sha256sum "${A07_FILE}" | awk '{print $1}')"
  echo "D02 file SHA256:                 $(sha256sum "${D02_FILE}" | awk '{print $1}')"
  echo "B06 panel SHA256:                $(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"
  echo "H05 panel SHA256:                $(sha256sum "${H05_REFERENCE_FILE}" | awk '{print $1}')"
  echo "H06 static reference SHA256:     $(sha256sum "${H06_STATIC_REFERENCE_FILE}" | awk '{print $1}')"
  echo "H06 dynamic reference SHA256:    $(sha256sum "${H06_DYNAMIC_REFERENCE_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 4: Build 21-threshold C_FUN ML quality-burden panel"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

PREP_COMMAND=(
  "${PYTHON_BIN}" "${PREP_SCRIPT}"
  --a07-file "${A07_FILE}"
  --d02-file "${D02_FILE}"
  --b06-file "${B06_PANEL_FILE}"
  --h05-reference-file "${H05_REFERENCE_FILE}"
  --output-dir "${OUTPUT_DIR}"
)
printf 'Command:' | tee -a "${LOG_FILE}"
printf ' %q' "${PREP_COMMAND[@]}" | tee -a "${LOG_FILE}"
printf '\n\n' | tee -a "${LOG_FILE}"
"${PREP_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for prep_output in \
  "${INPUT_FILE}" "${INPUT_SUMMARY_FILE}" "${INPUT_CHECKS_FILE}" \
  "${INPUT_SAMPLE_SUMMARY_FILE}" "${INPUT_GLOBAL_AUDIT_FILE}" \
  "${INPUT_REPRODUCTION_FILE}" "${INPUT_METADATA_FILE}"; do
  if [[ ! -s "${prep_output}" ]]; then
    echo "ERROR: missing or empty H07 threshold-input artifact: ${prep_output}" >&2
    exit 1
  fi
done
if grep -Eiq '(^|,)fail(,|$)' "${INPUT_CHECKS_FILE}"; then
  echo "ERROR: H07 threshold-input QC contains a failed row." >&2
  exit 1
fi
if grep -Eiq '(^|,)fail(,|$)' "${INPUT_REPRODUCTION_FILE}"; then
  echo "ERROR: H07 threshold-input does not reproduce H05 at >0.50." >&2
  exit 1
fi

LONG_ROWS="$(${PYTHON_BIN} - "${INPUT_FILE}" <<'PY'
import pandas as pd
import sys
print(len(pd.read_csv(sys.argv[1], usecols=["repo_id"])))
PY
)"
if [[ "${LONG_ROWS}" -ne "${EXPECTED_LONG_ROWS}" ]]; then
  echo "ERROR: expected ${EXPECTED_LONG_ROWS} H07 threshold-input rows, observed ${LONG_ROWS}." >&2
  exit 1
fi

echo "H05 primary reproduction:        PASS" | tee -a "${LOG_FILE}"
echo "Threshold-input hard QC:         PASS" | tee -a "${LOG_FILE}"
echo "Threshold-input rows:            ${LONG_ROWS}" | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 5: Run H07 21-threshold Borusyak DiD"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

R_COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --input-summary-file "${INPUT_SUMMARY_FILE}"
  --input-checks-file "${INPUT_CHECKS_FILE}"
  --input-sample-summary-file "${INPUT_SAMPLE_SUMMARY_FILE}"
  --input-global-audit-file "${INPUT_GLOBAL_AUDIT_FILE}"
  --h06-static-reference-file "${H06_STATIC_REFERENCE_FILE}"
  --h06-dynamic-reference-file "${H06_DYNAMIC_REFERENCE_FILE}"
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
  --h06-reproduction-tolerance "${H06_REPRODUCTION_TOLERANCE}"
)
printf 'Command:' | tee -a "${LOG_FILE}"
printf ' %q' "${R_COMMAND[@]}" | tee -a "${LOG_FILE}"
printf '\n\n' | tee -a "${LOG_FILE}"
"${R_COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_static_effects.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_dynamic_effects.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_pretrend_checks.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_pretrend_summary.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_model_diagnostics.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_model_failures.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_support.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_event_support.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_support_policy.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_total_static.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_total_threshold_static.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_total_threshold_dynamic.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_h06_reproduction.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_qc.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_summary.csv"
  "${OUTPUT_DIR}/quality_ml_cfun_threshold_run_metadata.csv"
)

{
  echo
  echo "** Step 6: Verify H07 DiD artifacts and hard QC"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_qc.csv"
REPRO_FILE="${OUTPUT_DIR}/quality_ml_cfun_h06_reproduction.csv"
RESULT_SUMMARY_FILE="${OUTPUT_DIR}/quality_ml_cfun_threshold_summary.csv"
if grep -Eiq '(^|,)fail(,|$)' "${QC_FILE}"; then
  echo "ERROR: H07 QC contains a failed check." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if grep -Eiq '(^|,)fail(,|$)' "${REPRO_FILE}"; then
  echo "ERROR: H07 does not reproduce H06 at the primary 0.50 threshold." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if ! grep -Eq '^status,PASS$|^status,PASS\r$' "${RESULT_SUMMARY_FILE}"; then
  echo "ERROR: H07 result summary does not report PASS." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_static_effects.csv")"
DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_dynamic_effects.csv")"
PRETREND_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_pretrend_checks.csv")"
PRETREND_SUMMARY_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_pretrend_summary.csv")"
PRIMARY_THRESHOLD_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_primary_threshold_static.csv")"
PRIMARY_TOTAL_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_primary_total_static.csv")"
PRIMARY_TOTAL_DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv")"
TOTAL_THRESHOLD_STATIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_total_threshold_static.csv")"
TOTAL_THRESHOLD_DYNAMIC_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_total_threshold_dynamic.csv")"
THRESHOLD_SUPPORT_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_support.csv")"
EVENT_SUPPORT_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_threshold_event_support.csv")"
H06_REPRODUCTION_ROWS="$(count_rows "${OUTPUT_DIR}/quality_ml_cfun_h06_reproduction.csv")"

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
  "h06_reproduction:${H06_REPRODUCTION_ROWS}:${EXPECTED_H06_REPRODUCTION_ROWS}"
)
for triple in "${EXPECTED_ACTUAL_PAIRS[@]}"; do
  name="${triple%%:*}"
  rest="${triple#*:}"
  actual="${rest%%:*}"
  expected="${rest##*:}"
  if [[ "${actual}" -ne "${expected}" ]]; then
    echo "ERROR: H07 ${name} row count expected ${expected}, observed ${actual}." | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

SPARSE_ROWS="$(awk -F',' 'NR==1 {for (i=1; i<=NF; i++) if ($i=="sparse_support_flag") col=i; next} col>0 && $col==1 {n++} END {print n+0}' "${OUTPUT_DIR}/quality_ml_cfun_threshold_support.csv")"

{
  echo "H05 primary reproduction:        PASS"
  echo "H06 primary DiD reproduction:    PASS"
  echo "H07 hard QC:                     PASS"
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
  echo "Threshold dynamic results:       ${OUTPUT_DIR}/quality_ml_cfun_total_threshold_dynamic.csv"
  echo "Primary dynamic results:         ${OUTPUT_DIR}/quality_ml_cfun_primary_total_dynamic.csv"
  echo "Threshold support:               ${OUTPUT_DIR}/quality_ml_cfun_threshold_support.csv"
  echo "QC:                              ${OUTPUT_DIR}/quality_ml_cfun_threshold_qc.csv"
  echo "Metadata:                        ${OUTPUT_DIR}/quality_ml_cfun_threshold_run_metadata.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
