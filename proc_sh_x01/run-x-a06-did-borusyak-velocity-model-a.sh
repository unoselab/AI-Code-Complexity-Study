#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a06 v7: Borusyak velocity DiD, Model A
# ============================================================
#
# Purpose:
#   Run the original-style pooled Borusyak imputation DiD on the final
#   run-x-a05-v3 Python velocity panel.
#
# Outcomes:
#   - log_commits
#   - log_lines_added
#
# Model A first-stage covariates:
#   - log_age
#   - ncloc
#   - log_contributors
#   - log_stars
#   - log_issues
#
# Fixed effects and clustering:
#   - repository fixed effects: repo_id
#   - calendar-month fixed effects: time_index
#   - clustered standard errors: repo_id
#
# Treatment timing:
#   The R analysis reconstructs an absorbing intent-to-treat indicator from
#   event_index and time_index. Legacy cursor, is_treatment, post_event,
#   lead_*, and lag_* columns are retained only for audit and are not used to
#   define treatment.
#
# Estimands:
#   - static ATT across every post-adoption observation;
#   - dynamic ATT for event times 0 through +6;
#   - placebo pretrend coefficients for event times -6 through -2;
#   - event time -1 is the omitted reference and has no synthetic coefficient.
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#
# Main outputs:
#   repo_x01/run-x-a06/model-a/velocity_model_a_static_effects.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_dynamic_effects.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_pretrend_checks.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_pretrend_summary.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_event_support.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_cohort_support.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_sample_summary.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_legacy_flag_audit.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_diagnostics.csv
#   repo_x01/run-x-a06/model-a/velocity_model_a_run_metadata.csv
#   repo_x01/run-x-a06/model-a/plots/velocity_model_a_dynamic_effects.pdf
#   repo_x01/run-x-a06/model-a/plots/velocity_model_a_dynamic_effects.png
#   repo_x01/run-x-a06/model-a/velocity_model_a_report.html
#
# Reproducibility objects:
#   repo_x01/run-x-a06/model-a/velocity_model_a_static_results.rds
#   repo_x01/run-x-a06/model-a/velocity_model_a_dynamic_results.rds
#   repo_x01/run-x-a06/model-a/velocity_model_a_first_stage_models.rds
# #
# QC summary:
#   repo_x01/tmp/run-x-a06/velocity_model_a_summary.csv
#
# Run:
#   bash proc_sh_x01/run-x-a06-did-borusyak-velocity-model-a.sh
#
# Optional overrides:
#   RSCRIPT_BIN=/path/to/Rscript
#   INPUT_FILE=...
#   OUTPUT_DIR=...
#   PLOT_MIN_EVENT=-6
#   PLOT_MAX_EVENT=6
#   PRETREND_MIN=-6
#   PRETREND_MAX=-2
#   STRICT_EXPECTED_COUNTS=1
#   HTML_OUTPUT=repo_x01/run-x-a06/model-a/velocity_model_a_report.html
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a06"
IMPLEMENTATION_VERSION="v7"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-velocity-model-a-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_model_a.R}"
INPUT_FILE="${INPUT_FILE:-repo_x01/run-x-a05/velocity_did_panel_model_a.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/model-a}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_model_a_summary.csv}"
HTML_OUTPUT="${HTML_OUTPUT:-${OUTPUT_DIR}/velocity_model_a_report.html}"

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

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PACKAGE_CHECK=(
  "${RSCRIPT_BIN}"
  -e
  'required <- c("data.table", "didimputation", "fixest", "ggplot2", "rmarkdown", "knitr"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); if (!rmarkdown::pandoc_available()) stop("Pandoc is required for HTML rendering"); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")'
)

PACKAGE_VERSIONS="$("${PACKAGE_CHECK[@]}")"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PANDOC_VERSION="$(${RSCRIPT_BIN} -e 'cat(as.character(rmarkdown::pandoc_version()))')"
INPUT_SHA256="$(sha256sum "${INPUT_FILE}" | awk '{print $1}')"
SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Borusyak velocity DiD, Model A"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Rscript:                     ${RSCRIPT_BIN}"
  echo "R version:                   ${R_VERSION}"
  echo "R packages:                  ${PACKAGE_VERSIONS}"
  echo "Pandoc version:              ${PANDOC_VERSION}"
  echo "Implementation version:      ${IMPLEMENTATION_VERSION}"
  echo "R analysis script:           ${R_SCRIPT}"
  echo "R script SHA256:             ${SCRIPT_SHA256}"
  echo "Input panel:                 ${INPUT_FILE}"
  echo "Input SHA256:                ${INPUT_SHA256}"
  echo "Output directory:            ${OUTPUT_DIR}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "HTML report:                 ${HTML_OUTPUT}"
  echo "Dynamic horizon argument:    ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Displayed event window:      ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:             ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:        -1"
  echo "Confidence level:            ${CONFIDENCE_LEVEL}"
  echo "Expected rows:               ${EXPECTED_ROWS}"
  echo "Expected treatment repos:    ${EXPECTED_TREATMENT_REPOS}"
  echo "Expected control repos:      ${EXPECTED_CONTROL_REPOS}"
  echo "Expected untreated rows:     ${EXPECTED_UNTREATED_ROWS}"
  echo "Expected treated rows:       ${EXPECTED_TREATED_ROWS}"
  echo "Expected dynamic rows:       ${EXPECTED_DYNAMIC_TREATED_ROWS}"
  echo "Expected legacy mismatches:  ${EXPECTED_LEGACY_MISMATCH_ROWS} rows / ${EXPECTED_LEGACY_MISMATCH_REPOS} repos"
  echo "Strict expected counts:      ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --input-file "${INPUT_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --summary-output "${SUMMARY_OUTPUT}"
  --html-output "${HTML_OUTPUT}"
  --script-path "${R_SCRIPT}"
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
  echo "** Step 1: Validate the panel, run Borusyak DiD, and render HTML"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/velocity_model_a_static_effects.csv"
  "${OUTPUT_DIR}/velocity_model_a_dynamic_effects.csv"
  "${OUTPUT_DIR}/velocity_model_a_pretrend_checks.csv"
  "${OUTPUT_DIR}/velocity_model_a_pretrend_summary.csv"
  "${OUTPUT_DIR}/velocity_model_a_event_support.csv"
  "${OUTPUT_DIR}/velocity_model_a_cohort_support.csv"
  "${OUTPUT_DIR}/velocity_model_a_sample_summary.csv"
  "${OUTPUT_DIR}/velocity_model_a_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/velocity_model_a_diagnostics.csv"
  "${OUTPUT_DIR}/velocity_model_a_run_metadata.csv"
  "${OUTPUT_DIR}/velocity_model_a_static_results.rds"
  "${OUTPUT_DIR}/velocity_model_a_dynamic_results.rds"
  "${OUTPUT_DIR}/velocity_model_a_first_stage_models.rds"
  "${OUTPUT_DIR}/plots/velocity_model_a_dynamic_effects.pdf"
  "${OUTPUT_DIR}/plots/velocity_model_a_dynamic_effects.png"
  "${HTML_OUTPUT}"
  "${SUMMARY_OUTPUT}"
)

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${OUTPUT_DIR}/velocity_model_a_static_effects.csv" \
    "${OUTPUT_DIR}/velocity_model_a_dynamic_effects.csv" \
    "${OUTPUT_DIR}/velocity_model_a_pretrend_checks.csv" \
    "${OUTPUT_DIR}/velocity_model_a_pretrend_summary.csv" \
    "${OUTPUT_DIR}/velocity_model_a_event_support.csv" \
    "${OUTPUT_DIR}/velocity_model_a_cohort_support.csv" \
    "${OUTPUT_DIR}/velocity_model_a_sample_summary.csv" \
    "${OUTPUT_DIR}/velocity_model_a_legacy_flag_audit.csv" \
    "${OUTPUT_DIR}/velocity_model_a_diagnostics.csv" \
    "${OUTPUT_DIR}/velocity_model_a_run_metadata.csv" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Static effects:"
  cat "${OUTPUT_DIR}/velocity_model_a_static_effects.csv"
  echo
  echo "Pretrend checks:"
  cat "${OUTPUT_DIR}/velocity_model_a_pretrend_checks.csv"
  echo
  echo "Pretrend summary:"
  cat "${OUTPUT_DIR}/velocity_model_a_pretrend_summary.csv"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "HTML report file:"
  ls -lh "${HTML_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Static effects:              ${OUTPUT_DIR}/velocity_model_a_static_effects.csv"
  echo "Dynamic effects:             ${OUTPUT_DIR}/velocity_model_a_dynamic_effects.csv"
  echo "Pretrend checks:             ${OUTPUT_DIR}/velocity_model_a_pretrend_checks.csv"
  echo "Pretrend summary:            ${OUTPUT_DIR}/velocity_model_a_pretrend_summary.csv"
  echo "Dynamic plot:                ${OUTPUT_DIR}/plots/velocity_model_a_dynamic_effects.pdf"
  echo "HTML report:                 ${HTML_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "Next step:                   review the integrated HTML report and archived Model A outputs"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
