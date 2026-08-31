#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# run-x-j03 v1: Borusyak DiD for SonarQube cognitive-complexity detector panel
# ============================================================================
#
# This standalone wrapper was copied from the validated run-x-i09 shell design
# and adapted to the run-x-j02 cognitive-complexity panel. It does not call any
# previous experiment wrapper.
#
# Inputs:
#   - J02 repo-month complexity panel: All Python + NPR + ML frozen scopes.
#   - J02 detector-only file audit: defines the pre-specified scope-exclusion
#     sensitivity sample; no path remapping is performed.
#   - J02 QC and summary: upstream provenance gates.
#
# Outputs:
#   - static and dynamic Borusyak effects for 44 scope/threshold specs;
#   - full and scope-exclusion samples;
#   - adjusted and FE-only specifications;
#   - pretrend, support, diagnostics, QC, and compact headline tables.
#
# Distributed source names:
#   proc_script_x01/did_borusyak_sonarqube_complexity_detector_panel-v1.R
#   proc_sh_x01/run-x-j03-did-borusyak-sonarqube-complexity-detector-panel-v1.sh
#
# Canonical server names after removing the delivery version suffix:
#   proc_script_x01/did_borusyak_sonarqube_complexity_detector_panel.R
#   proc_sh_x01/run-x-j03-did-borusyak-sonarqube-complexity-detector-panel.sh
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-j03"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-sonarqube-complexity-detector-panel-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_sonarqube_complexity_detector_panel.R}"
J02_ROOT="${J02_ROOT:-repo_x01/run-x-j02}"
INPUT_FILE="${INPUT_FILE:-${J02_ROOT}/python_sonarqube_complexity_repo_month_panel.csv.gz}"
DETECTOR_MISMATCH_FILE="${DETECTOR_MISMATCH_FILE:-${J02_ROOT}/python_detector_files_without_sonarqube_complexity.csv}"
J02_QC_FILE="${J02_QC_FILE:-${J02_ROOT}/python_sonarqube_complexity_qc.csv}"
J02_SUMMARY_FILE="${J02_SUMMARY_FILE:-${J02_ROOT}/python_sonarqube_complexity_summary.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
SPARSE_MIN_DYNAMIC_POSITIVE_REPOS="${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS:-10}"
SPARSE_MIN_WITHIN_VARIATION_REPOS="${SPARSE_MIN_WITHIN_VARIATION_REPOS:-20}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
OVERWRITE="${OVERWRITE:-0}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

require_file() {
  local path="$1"; local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: missing ${label}: ${path}" >&2
    exit 1
  fi
}

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

require_file "${R_SCRIPT}" "J03 R program"
for binary_value in "${STRICT_EXPECTED_COUNTS}" "${OVERWRITE}" "${SELF_TEST_ONLY}"; do
  if [[ "${binary_value}" != "0" && "${binary_value}" != "1" ]]; then
    echo "ERROR: Boolean options must be 0 or 1: ${binary_value}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: SonarQube cognitive-complexity detector Borusyak DiD"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "J02 complexity panel:            ${INPUT_FILE}"
  echo "J02 detector mismatch audit:     ${DETECTOR_MISMATCH_FILE}"
  echo "J02 QC:                          ${J02_QC_FILE}"
  echo "J02 summary:                     ${J02_SUMMARY_FILE}"
  echo "Primary outcome:                 log1p_selected_cognitive_complexity"
  echo "Scopes:                          All Python + 22 NPR + 21 ML = 44"
  echo "NPR primary:                     > 1.571637"
  echo "ML primary:                      > 0.50"
  echo "Samples:                         full + exclude detector-scope mismatch repos"
  echo "Model specs:                     adjusted_complexity + fe_only_complexity"
  echo "Expected model jobs:             176"
  echo "Expected static/dynamic rows:    176 / 2112"
  echo "Dynamic horizon:                 ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event:                 -1"
  echo "Path remapping:                  none"
  echo "SonarQube rescan:                none"
  echo "Detector rescoring:              none"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run J03 structural self-test"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Parse J03 R program"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${RSCRIPT_BIN}" -e "invisible(parse(file='${R_SCRIPT}')); cat('R parse: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL}: SELF-TEST PASS" | tee -a "${LOG_FILE}"
  exit 0
fi

for input_path in "${INPUT_FILE}" "${DETECTOR_MISMATCH_FILE}" "${J02_QC_FILE}" "${J02_SUMMARY_FILE}"; do
  require_file "${input_path}" "required J02 production input"
done

if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally rebuilding J03." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PACKAGE_VERSIONS="$(${RSCRIPT_BIN} -e 'required <- c("data.table", "didimputation", "fixest"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "))')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
MISMATCH_SHA256="$(sha256sum "${DETECTOR_MISMATCH_FILE}" | awk '{print $1}')"
QC_SHA256="$(sha256sum "${J02_QC_FILE}" | awk '{print $1}')"
SUMMARY_SHA256="$(sha256sum "${J02_SUMMARY_FILE}" | awk '{print $1}')"

{
  echo
  echo "** Step 3: Freeze J02 provenance"
  echo "----------------------------------------------------------------------------"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "J02 panel SHA256:                ${INPUT_SHA256}"
  echo "J02 mismatch SHA256:             ${MISMATCH_SHA256}"
  echo "J02 QC SHA256:                   ${QC_SHA256}"
  echo "J02 summary SHA256:              ${SUMMARY_SHA256}"
} | tee -a "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}" "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --detector-mismatch-file "${DETECTOR_MISMATCH_FILE}"
  --j02-qc-file "${J02_QC_FILE}"
  --j02-summary-file "${J02_SUMMARY_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --script-path "${R_SCRIPT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --plot-min-event "${PLOT_MIN_EVENT}"
  --plot-max-event "${PLOT_MAX_EVENT}"
  --pretrend-min "${PRETREND_MIN}"
  --pretrend-max "${PRETREND_MAX}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --sparse-min-dynamic-positive-repos "${SPARSE_MIN_DYNAMIC_POSITIVE_REPOS}"
  --sparse-min-within-variation-repos "${SPARSE_MIN_WITHIN_VARIATION_REPOS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
)

{
  echo
  echo "** Step 4: Run J03 Borusyak cognitive-complexity analysis"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/complexity_detector_static_effects.csv"
  "${OUTPUT_DIR}/complexity_detector_dynamic_effects.csv"
  "${OUTPUT_DIR}/complexity_detector_pretrend_checks.csv"
  "${OUTPUT_DIR}/complexity_detector_pretrend_summary.csv"
  "${OUTPUT_DIR}/complexity_detector_model_diagnostics.csv"
  "${OUTPUT_DIR}/complexity_detector_model_failures.csv"
  "${OUTPUT_DIR}/complexity_detector_threshold_support.csv"
  "${OUTPUT_DIR}/complexity_detector_event_support.csv"
  "${OUTPUT_DIR}/complexity_detector_sample_summary.csv"
  "${OUTPUT_DIR}/complexity_detector_headline_static.csv"
  "${OUTPUT_DIR}/complexity_detector_headline_dynamic.csv"
  "${OUTPUT_DIR}/complexity_detector_full_sample_headline_static.csv"
  "${OUTPUT_DIR}/complexity_detector_full_sample_headline_dynamic.csv"
  "${OUTPUT_DIR}/complexity_npr_threshold_static.csv"
  "${OUTPUT_DIR}/complexity_ml_threshold_static.csv"
  "${OUTPUT_DIR}/complexity_detector_qc.csv"
  "${OUTPUT_DIR}/complexity_detector_summary.csv"
  "${OUTPUT_DIR}/complexity_detector_run_metadata.csv"
)

{
  echo
  echo "** Step 5: Verify J03 output artifacts"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_path in "${EXPECTED_OUTPUTS[@]}"; do
  require_file "${output_path}" "J03 output artifact"
  echo "OK: ${output_path}" | tee -a "${LOG_FILE}"
done

"${RSCRIPT_BIN}" -e "q<-data.table::fread('${OUTPUT_DIR}/complexity_detector_qc.csv'); if(any(q\$severity=='hard' & q\$status!='pass')) stop('J03 QC failed'); s<-data.table::fread('${OUTPUT_DIR}/complexity_detector_summary.csv'); z<-s[metric=='status',value]; if(length(z)!=1L || z!='PASS') stop(paste('J03 status:',paste(z,collapse='|'))); cat('J03 QC: PASS\nJ03 summary: PASS\n')" 2>&1 | tee -a "${LOG_FILE}"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Model jobs:                      176"
  echo "Static rows:                     176"
  echo "Dynamic/placebo rows:            2112"
  echo "Full headline static:            ${OUTPUT_DIR}/complexity_detector_full_sample_headline_static.csv"
  echo "Full headline dynamic:           ${OUTPUT_DIR}/complexity_detector_full_sample_headline_dynamic.csv"
  echo "NPR threshold sensitivity:       ${OUTPUT_DIR}/complexity_npr_threshold_static.csv"
  echo "ML threshold sensitivity:        ${OUTPUT_DIR}/complexity_ml_threshold_static.csv"
  echo "Scope sensitivity:               ${OUTPUT_DIR}/complexity_detector_headline_static.csv"
  echo "QC:                              ${OUTPUT_DIR}/complexity_detector_qc.csv"
  echo "Summary:                         ${OUTPUT_DIR}/complexity_detector_summary.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            analyze All-Python vs NPR vs ML complexity effects"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
