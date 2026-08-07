#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b03 v3: covariate sensitivity for Python velocity DiD
# ============================================================
#
# Purpose:
#   Reuse the established run-x-b03 Borusyak DiD design while testing whether
#   contemporaneous Python-NCLOC/project covariates materially affect the
#   Python added-lines treatment effects or the event -2 pretrend finding.
#
# Input panels:
#   - SonarQube Python-NCLOC backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   - cloc Python-NCLOC backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv
#
# Outcome specifications from run-x-b02-v4:
#   - Primary:    log_lines_added_py_source
#   - Robustness: log_lines_added_py_no_merge
#   - Robustness: log_lines_added_py_source_no_tests
#   - Robustness: log_lines_added_py_all
#
# First-stage sensitivity specifications:
#   1. python_ncloc_adjusted
#      ~ log_age + ncloc + log_contributors + log_stars + log_issues
#        | repo_id + time_index
#   2. no_covariates
#      ~ 1 | repo_id + time_index
#
# Why the immediate sensitivity uses these two specifications:
#   The adjusted specification preserves the established Python-focused b03
#   model. The no-covariate specification avoids conditioning on variables that
#   can change after Cursor adoption. A repository-fixed baseline NCLOC level is
#   not added because repository fixed effects absorb time-invariant repository
#   covariates; a baseline-size trend interaction would be a different model.
#
# Estimator kept unchanged across specifications:
#   - absorbing treatment from first observed Cursor adoption;
#   - repository and calendar-month fixed effects;
#   - repository-clustered standard errors;
#   - static ATT over all post-adoption rows;
#   - post-adoption event effects 0 through +6;
#   - package-native placebo effects -6 through -2;
#   - event month -1 omitted as the reference.
#
# Output layout:
#   repo_x01/run-x-b03/specs/python_ncloc_adjusted/{sonarqube,cloc}/
#   repo_x01/run-x-b03/specs/no_covariates/{sonarqube,cloc}/
#   repo_x01/run-x-b03/comparison/python_ncloc_adjusted/
#   repo_x01/run-x-b03/comparison/no_covariates/
#   repo_x01/run-x-b03/comparison/covariate_sensitivity/
#   repo_x01/tmp/run-x-b03/v3/
#
# This wrapper is self-contained. It was derived from the prior b03 shell logic
# but does not call any previous shell script.
#
# Run:
#   bash proc_sh_x01/run-x-b03-did-borusyak-python-velocity.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b03"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-python-velocity-covariate-sensitivity-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_python_added_lines.R}"
SONARQUBE_INPUT_FILE="${SONARQUBE_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
CLOC_INPUT_FILE="${CLOC_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01/${RUN_PREFIX}}"
SPEC_ROOT="${SPEC_ROOT:-${OUTPUT_BASE_DIR}/specs}"
ADJUSTED_ROOT="${ADJUSTED_ROOT:-${SPEC_ROOT}/python_ncloc_adjusted}"
NO_COVARIATES_ROOT="${NO_COVARIATES_ROOT:-${SPEC_ROOT}/no_covariates}"
ADJUSTED_SONARQUBE_OUTPUT_DIR="${ADJUSTED_SONARQUBE_OUTPUT_DIR:-${ADJUSTED_ROOT}/sonarqube}"
ADJUSTED_CLOC_OUTPUT_DIR="${ADJUSTED_CLOC_OUTPUT_DIR:-${ADJUSTED_ROOT}/cloc}"
NO_COVARIATES_SONARQUBE_OUTPUT_DIR="${NO_COVARIATES_SONARQUBE_OUTPUT_DIR:-${NO_COVARIATES_ROOT}/sonarqube}"
NO_COVARIATES_CLOC_OUTPUT_DIR="${NO_COVARIATES_CLOC_OUTPUT_DIR:-${NO_COVARIATES_ROOT}/cloc}"

COMPARISON_ROOT="${COMPARISON_ROOT:-${OUTPUT_BASE_DIR}/comparison}"
ADJUSTED_BACKEND_COMPARISON_DIR="${ADJUSTED_BACKEND_COMPARISON_DIR:-${COMPARISON_ROOT}/python_ncloc_adjusted}"
NO_COVARIATES_BACKEND_COMPARISON_DIR="${NO_COVARIATES_BACKEND_COMPARISON_DIR:-${COMPARISON_ROOT}/no_covariates}"
COVARIATE_COMPARISON_DIR="${COVARIATE_COMPARISON_DIR:-${COMPARISON_ROOT}/covariate_sensitivity}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-repo_x01/tmp/${RUN_PREFIX}/v3}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
BACKEND_EQUIVALENCE_TOLERANCE="${BACKEND_EQUIVALENCE_TOLERANCE:-1e-8}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-63}"
EXPECTED_CONTROL_REPOS="${EXPECTED_CONTROL_REPOS:-104}"
EXPECTED_UNTREATED_ROWS="${EXPECTED_UNTREATED_ROWS:-1591}"
EXPECTED_TREATED_ROWS="${EXPECTED_TREATED_ROWS:-363}"
EXPECTED_DYNAMIC_TREATED_ROWS="${EXPECTED_DYNAMIC_TREATED_ROWS:-343}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-3}"

PRIMARY_OUTCOME="log_lines_added_py_source"
ROBUSTNESS_OUTCOMES="log_lines_added_py_no_merge|log_lines_added_py_source_no_tests|log_lines_added_py_all"
EXPECTED_VELOCITY_VERSION="v4"

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
  exit 1
fi

for required_file in "${R_SCRIPT}" "${SONARQUBE_INPUT_FILE}" "${CLOC_INPUT_FILE}"; do
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

mkdir -p \
  "${LOG_DIR}" \
  "${ADJUSTED_SONARQUBE_OUTPUT_DIR}" \
  "${ADJUSTED_CLOC_OUTPUT_DIR}" \
  "${NO_COVARIATES_SONARQUBE_OUTPUT_DIR}" \
  "${NO_COVARIATES_CLOC_OUTPUT_DIR}" \
  "${ADJUSTED_BACKEND_COMPARISON_DIR}" \
  "${NO_COVARIATES_BACKEND_COMPARISON_DIR}" \
  "${COVARIATE_COMPARISON_DIR}" \
  "${TMP_OUTPUT_DIR}"

PACKAGE_CHECK=(
  "${RSCRIPT_BIN}"
  -e
  'required <- c("data.table", "didimputation", "fixest", "ggplot2", "rmarkdown", "knitr"); missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); if (!rmarkdown::pandoc_available()) stop("Pandoc is required for HTML rendering"); cat(paste(vapply(required, function(p) paste0(p, "=", as.character(packageVersion(p))), character(1)), collapse="; "), "\n")'
)

PACKAGE_VERSIONS="$("${PACKAGE_CHECK[@]}")"
R_VERSION="$(${RSCRIPT_BIN} -e 'cat(R.version.string)')"
PANDOC_VERSION="$(${RSCRIPT_BIN} -e 'cat(as.character(rmarkdown::pandoc_version()))')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
SONARQUBE_INPUT_SHA256="$(sha256sum "${SONARQUBE_INPUT_FILE}" | awk '{print $1}')"
CLOC_INPUT_SHA256="$(sha256sum "${CLOC_INPUT_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: Python velocity DiD covariate sensitivity"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Rscript:                         ${RSCRIPT_BIN}"
  echo "R version:                       ${R_VERSION}"
  echo "R packages:                      ${PACKAGE_VERSIONS}"
  echo "Pandoc version:                  ${PANDOC_VERSION}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "R analysis script:               ${R_SCRIPT}"
  echo "R script SHA256:                 ${R_SCRIPT_SHA256}"
  echo "SonarQube input panel:           ${SONARQUBE_INPUT_FILE}"
  echo "SonarQube input SHA256:          ${SONARQUBE_INPUT_SHA256}"
  echo "cloc input panel:                ${CLOC_INPUT_FILE}"
  echo "cloc input SHA256:               ${CLOC_INPUT_SHA256}"
  echo "Primary outcome:                 ${PRIMARY_OUTCOME}"
  echo "Robustness outcomes:             ${ROBUSTNESS_OUTCOMES}"
  echo "Expected velocity version:       ${EXPECTED_VELOCITY_VERSION}"
  echo "First-stage spec 1:              python_ncloc_adjusted"
  echo "First-stage spec 2:              no_covariates"
  echo "Output base:                     ${OUTPUT_BASE_DIR}"
  echo "Temporary output:                ${TMP_OUTPUT_DIR}"
  echo "Dynamic horizon argument:        ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Confidence level:                ${CONFIDENCE_LEVEL}"
  echo "Backend equivalence tolerance:   ${BACKEND_EQUIVALENCE_TOLERANCE}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

run_command_logged() {
  local step_title="$1"
  shift
  local -a command=("$@")
  {
    echo
    echo "** ${step_title}"
    echo "------------------------------------------------------------"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"
  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

build_backend_command() {
  local backend="$1"
  local covariate_spec="$2"
  local input_file="$3"
  local output_dir="$4"
  local summary_output="$5"
  local html_output="$6"

  BACKEND_COMMAND=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --mode backend
    --backend "${backend}"
    --covariate-spec "${covariate_spec}"
    --input-file "${input_file}"
    --output-dir "${output_dir}"
    --summary-output "${summary_output}"
    --html-output "${html_output}"
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
}

build_backend_compare_command() {
  local covariate_spec="$1"
  local sonarqube_dir="$2"
  local cloc_dir="$3"
  local comparison_dir="$4"
  local summary_output="$5"

  BACKEND_COMPARE_COMMAND=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --mode compare
    --covariate-spec "${covariate_spec}"
    --sonarqube-input-file "${SONARQUBE_INPUT_FILE}"
    --cloc-input-file "${CLOC_INPUT_FILE}"
    --sonarqube-output-dir "${sonarqube_dir}"
    --cloc-output-dir "${cloc_dir}"
    --comparison-output-dir "${comparison_dir}"
    --comparison-summary-output "${summary_output}"
    --expected-rows "${EXPECTED_ROWS}"
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  )
}

ADJ_SQ_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_python_ncloc_adjusted_summary.csv"
ADJ_CLOC_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_cloc_python_ncloc_adjusted_summary.csv"
NO_SQ_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_no_covariates_summary.csv"
NO_CLOC_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_cloc_no_covariates_summary.csv"
ADJ_BACKEND_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_backend_python_ncloc_adjusted_summary.csv"
NO_BACKEND_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_backend_no_covariates_summary.csv"
COVARIATE_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_covariate_sensitivity_summary.csv"

ADJ_SQ_HTML="${ADJUSTED_SONARQUBE_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_python_ncloc_adjusted_report.html"
ADJ_CLOC_HTML="${ADJUSTED_CLOC_OUTPUT_DIR}/velocity_python_added_lines_cloc_python_ncloc_adjusted_report.html"
NO_SQ_HTML="${NO_COVARIATES_SONARQUBE_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_no_covariates_report.html"
NO_CLOC_HTML="${NO_COVARIATES_CLOC_OUTPUT_DIR}/velocity_python_added_lines_cloc_no_covariates_report.html"

build_backend_command "sonarqube" "python_ncloc_adjusted" "${SONARQUBE_INPUT_FILE}" "${ADJUSTED_SONARQUBE_OUTPUT_DIR}" "${ADJ_SQ_SUMMARY}" "${ADJ_SQ_HTML}"
run_command_logged "Step 1: SonarQube backend with contemporaneous Python-NCLOC covariates" "${BACKEND_COMMAND[@]}"

build_backend_command "cloc" "python_ncloc_adjusted" "${CLOC_INPUT_FILE}" "${ADJUSTED_CLOC_OUTPUT_DIR}" "${ADJ_CLOC_SUMMARY}" "${ADJ_CLOC_HTML}"
run_command_logged "Step 2: cloc backend with contemporaneous Python-NCLOC covariates" "${BACKEND_COMMAND[@]}"

build_backend_compare_command "python_ncloc_adjusted" "${ADJUSTED_SONARQUBE_OUTPUT_DIR}" "${ADJUSTED_CLOC_OUTPUT_DIR}" "${ADJUSTED_BACKEND_COMPARISON_DIR}" "${ADJ_BACKEND_SUMMARY}"
run_command_logged "Step 3: Compare NCLOC backends for adjusted specification" "${BACKEND_COMPARE_COMMAND[@]}"

build_backend_command "sonarqube" "no_covariates" "${SONARQUBE_INPUT_FILE}" "${NO_COVARIATES_SONARQUBE_OUTPUT_DIR}" "${NO_SQ_SUMMARY}" "${NO_SQ_HTML}"
run_command_logged "Step 4: SonarQube backend with no contemporaneous covariates" "${BACKEND_COMMAND[@]}"

build_backend_command "cloc" "no_covariates" "${CLOC_INPUT_FILE}" "${NO_COVARIATES_CLOC_OUTPUT_DIR}" "${NO_CLOC_SUMMARY}" "${NO_CLOC_HTML}"
run_command_logged "Step 5: cloc backend with no contemporaneous covariates" "${BACKEND_COMMAND[@]}"

build_backend_compare_command "no_covariates" "${NO_COVARIATES_SONARQUBE_OUTPUT_DIR}" "${NO_COVARIATES_CLOC_OUTPUT_DIR}" "${NO_COVARIATES_BACKEND_COMPARISON_DIR}" "${NO_BACKEND_SUMMARY}"
run_command_logged "Step 6: Verify backend equivalence when NCLOC is not used" "${BACKEND_COMPARE_COMMAND[@]}"

COVARIATE_COMPARE_COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --mode covariate_compare
  --adjusted-sonarqube-output-dir "${ADJUSTED_SONARQUBE_OUTPUT_DIR}"
  --adjusted-cloc-output-dir "${ADJUSTED_CLOC_OUTPUT_DIR}"
  --no-covariates-sonarqube-output-dir "${NO_COVARIATES_SONARQUBE_OUTPUT_DIR}"
  --no-covariates-cloc-output-dir "${NO_COVARIATES_CLOC_OUTPUT_DIR}"
  --comparison-output-dir "${COVARIATE_COMPARISON_DIR}"
  --comparison-summary-output "${COVARIATE_SUMMARY}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --backend-equivalence-tolerance "${BACKEND_EQUIVALENCE_TOLERANCE}"
)
run_command_logged "Step 7: Compare adjusted versus no-covariate specifications" "${COVARIATE_COMPARE_COMMAND[@]}"

COVARIATE_PREFIX="velocity_python_added_lines_covariate_sensitivity"
PRIMARY_SUMMARY_FILE="${COVARIATE_COMPARISON_DIR}/${COVARIATE_PREFIX}_primary_summary.csv"
EVENT_MINUS2_FILE="${COVARIATE_COMPARISON_DIR}/${COVARIATE_PREFIX}_primary_event_minus2.csv"
COVARIATE_QC_FILE="${COVARIATE_COMPARISON_DIR}/${COVARIATE_PREFIX}_qc.csv"
STATIC_DIFF_FILE="${COVARIATE_COMPARISON_DIR}/${COVARIATE_PREFIX}_static_differences.csv"
DYNAMIC_DIFF_FILE="${COVARIATE_COMPARISON_DIR}/${COVARIATE_PREFIX}_dynamic_differences.csv"
PRIMARY_PLOT_PDF="${COVARIATE_COMPARISON_DIR}/plots/${COVARIATE_PREFIX}_primary_dynamic_effects.pdf"
PRIMARY_PLOT_PNG="${COVARIATE_COMPARISON_DIR}/plots/${COVARIATE_PREFIX}_primary_dynamic_effects.png"

EXPECTED_OUTPUTS=(
  "${PRIMARY_SUMMARY_FILE}"
  "${EVENT_MINUS2_FILE}"
  "${COVARIATE_QC_FILE}"
  "${STATIC_DIFF_FILE}"
  "${DYNAMIC_DIFF_FILE}"
  "${PRIMARY_PLOT_PDF}"
  "${PRIMARY_PLOT_PNG}"
  "${ADJ_SQ_SUMMARY}"
  "${ADJ_CLOC_SUMMARY}"
  "${NO_SQ_SUMMARY}"
  "${NO_CLOC_SUMMARY}"
  "${ADJ_BACKEND_SUMMARY}"
  "${NO_BACKEND_SUMMARY}"
  "${COVARIATE_SUMMARY}"
  "${ADJ_SQ_HTML}"
  "${ADJ_CLOC_HTML}"
  "${NO_SQ_HTML}"
  "${NO_CLOC_HTML}"
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
  echo "** Step 8: Output checks"
  echo "------------------------------------------------------------"
  wc -l "${PRIMARY_SUMMARY_FILE}" "${EVENT_MINUS2_FILE}" "${COVARIATE_QC_FILE}" "${STATIC_DIFF_FILE}" "${DYNAMIC_DIFF_FILE}" "${COVARIATE_SUMMARY}"
  echo
  echo "Primary static/pretrend summary across backend and covariate specifications:"
  cat "${PRIMARY_SUMMARY_FILE}"
  echo
  echo "Primary event -2 comparison:"
  cat "${EVENT_MINUS2_FILE}"
  echo
  echo "Covariate sensitivity QC:"
  cat "${COVARIATE_QC_FILE}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary outcome:                 ${PRIMARY_OUTCOME}"
  echo "Adjusted spec:                   python_ncloc_adjusted"
  echo "No-covariate spec:               no_covariates"
  echo "Primary comparison summary:      ${PRIMARY_SUMMARY_FILE}"
  echo "Primary event -2 comparison:     ${EVENT_MINUS2_FILE}"
  echo "Static specification differences:${STATIC_DIFF_FILE}"
  echo "Dynamic specification differences:${DYNAMIC_DIFF_FILE}"
  echo "Covariate sensitivity plot:      ${PRIMARY_PLOT_PDF}"
  echo "Covariate sensitivity QC:        ${COVARIATE_QC_FILE}"
  echo "Comparison summary:              ${COVARIATE_SUMMARY}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next decision:                   does event -2 persist without contemporaneous covariates?"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
