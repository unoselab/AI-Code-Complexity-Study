#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b03 v2: Borusyak DiD for Python added-lines velocity
# ============================================================
#
# Purpose:
#   Run the same staggered-DiD estimator on the four Python velocity outcomes
#   prepared by run-x-b02-v4 while varying only the Python-NCLOC backend.
#
# Input panels:
#   - SonarQube backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   - cloc backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv
#
# Outcome specifications:
#   - Primary:    log_lines_added_py_source
#   - Robustness: log_lines_added_py_no_merge
#   - Robustness: log_lines_added_py_source_no_tests
#   - Robustness: log_lines_added_py_all
#
# Estimator inherited from the previous b03 shell/R implementation:
#   - first stage: log_age + ncloc + log_contributors + log_stars + log_issues;
#   - repository and calendar-month fixed effects;
#   - repository-clustered standard errors;
#   - absorbing treatment beginning at the first observed Cursor adoption;
#   - static ATT over every post-adoption row;
#   - dynamic effects for event months 0 through +6;
#   - package-native placebo coefficients for event months -6 through -2;
#   - event month -1 omitted as the reference.
#
# Output structure:
#   repo_x01/run-x-b03/sonarqube/   backend results for all four outcomes
#   repo_x01/run-x-b03/cloc/        backend results for all four outcomes
#   repo_x01/run-x-b03/comparison/  backend and outcome-robustness comparisons
#   repo_x01/tmp/run-x-b03/         compact run summaries
#
# Important:
#   This wrapper is self-contained. It reuses the logic of the previous b03
#   wrapper but does not call any previous shell script.
#
# Run:
#   bash proc_sh_x01/run-x-b03-did-borusyak-python-velocity.sh
#
# Optional overrides:
#   RSCRIPT_BIN=/path/to/Rscript
#   SONARQUBE_INPUT_FILE=...
#   CLOC_INPUT_FILE=...
#   OUTPUT_BASE_DIR=repo_x01/run-x-b03
#   TMP_OUTPUT_DIR=repo_x01/tmp/run-x-b03
#   PLOT_MIN_EVENT=-6
#   PLOT_MAX_EVENT=6
#   PRETREND_MIN=-6
#   PRETREND_MAX=-2
#   CONFIDENCE_LEVEL=0.95
#   STRICT_EXPECTED_COUNTS=1
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b03"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-python-velocity-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_python_added_lines.R}"
SONARQUBE_INPUT_FILE="${SONARQUBE_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
CLOC_INPUT_FILE="${CLOC_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01/${RUN_PREFIX}}"
SONARQUBE_OUTPUT_DIR="${SONARQUBE_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/sonarqube}"
CLOC_OUTPUT_DIR="${CLOC_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/cloc}"
COMPARISON_OUTPUT_DIR="${COMPARISON_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/comparison}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-repo_x01/tmp/${RUN_PREFIX}}"

SONARQUBE_SUMMARY_OUTPUT="${SONARQUBE_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_summary.csv}"
CLOC_SUMMARY_OUTPUT="${CLOC_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_python_added_lines_cloc_summary.csv}"
COMPARISON_SUMMARY_OUTPUT="${COMPARISON_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/velocity_python_added_lines_comparison_summary.csv}"
SONARQUBE_HTML_OUTPUT="${SONARQUBE_HTML_OUTPUT:-${SONARQUBE_OUTPUT_DIR}/velocity_python_added_lines_sonarqube_report.html}"
CLOC_HTML_OUTPUT="${CLOC_HTML_OUTPUT:-${CLOC_OUTPUT_DIR}/velocity_python_added_lines_cloc_report.html}"

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

if ! [[ "${CONFIDENCE_LEVEL}" =~ ^0([.][0-9]+)?$|^1([.]0+)?$ ]]; then
  echo "ERROR: CONFIDENCE_LEVEL must be numeric between 0 and 1." >&2
  exit 1
fi

mkdir -p \
  "${LOG_DIR}" \
  "${SONARQUBE_OUTPUT_DIR}" \
  "${CLOC_OUTPUT_DIR}" \
  "${COMPARISON_OUTPUT_DIR}" \
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
  echo "${RUN_LABEL}: Borusyak DiD for Python added-lines velocity"
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
  echo "SonarQube output directory:      ${SONARQUBE_OUTPUT_DIR}"
  echo "cloc output directory:           ${CLOC_OUTPUT_DIR}"
  echo "Comparison output directory:     ${COMPARISON_OUTPUT_DIR}"
  echo "Dynamic horizon argument:        ${PLOT_MIN_EVENT}:${PLOT_MAX_EVENT}"
  echo "Pretrend window:                 ${PRETREND_MIN}:${PRETREND_MAX}"
  echo "Reference event time:            -1"
  echo "Confidence level:                ${CONFIDENCE_LEVEL}"
  echo "Expected rows per backend:       ${EXPECTED_ROWS}"
  echo "Expected treatment/control repos:${EXPECTED_TREATMENT_REPOS}/${EXPECTED_CONTROL_REPOS}"
  echo "Expected untreated/treated rows: ${EXPECTED_UNTREATED_ROWS}/${EXPECTED_TREATED_ROWS}"
  echo "Expected dynamic treated rows:   ${EXPECTED_DYNAMIC_TREATED_ROWS}"
  echo "Expected legacy mismatches:      ${EXPECTED_LEGACY_MISMATCH_ROWS} rows / ${EXPECTED_LEGACY_MISMATCH_REPOS} repos"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

build_backend_command() {
  local backend="$1"
  local input_file="$2"
  local output_dir="$3"
  local summary_output="$4"
  local html_output="$5"

  BACKEND_COMMAND=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --mode backend
    --backend "${backend}"
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

build_backend_command \
  "sonarqube" \
  "${SONARQUBE_INPUT_FILE}" \
  "${SONARQUBE_OUTPUT_DIR}" \
  "${SONARQUBE_SUMMARY_OUTPUT}" \
  "${SONARQUBE_HTML_OUTPUT}"
run_command_logged "Step 1: Run SonarQube backend for four Python velocity outcomes" "${BACKEND_COMMAND[@]}"

build_backend_command \
  "cloc" \
  "${CLOC_INPUT_FILE}" \
  "${CLOC_OUTPUT_DIR}" \
  "${CLOC_SUMMARY_OUTPUT}" \
  "${CLOC_HTML_OUTPUT}"
run_command_logged "Step 2: Run cloc backend for four Python velocity outcomes" "${BACKEND_COMMAND[@]}"

COMPARISON_COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --mode compare
  --sonarqube-input-file "${SONARQUBE_INPUT_FILE}"
  --cloc-input-file "${CLOC_INPUT_FILE}"
  --sonarqube-output-dir "${SONARQUBE_OUTPUT_DIR}"
  --cloc-output-dir "${CLOC_OUTPUT_DIR}"
  --comparison-output-dir "${COMPARISON_OUTPUT_DIR}"
  --comparison-summary-output "${COMPARISON_SUMMARY_OUTPUT}"
  --expected-rows "${EXPECTED_ROWS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
)
run_command_logged "Step 3: Build backend and outcome-definition robustness comparisons" "${COMPARISON_COMMAND[@]}"

SONAR_PREFIX="velocity_python_added_lines_sonarqube"
CLOC_PREFIX="velocity_python_added_lines_cloc"
COMPARISON_PREFIX="velocity_python_added_lines_backend"
ROBUSTNESS_PREFIX="velocity_python_added_lines_outcome_robustness"

EXPECTED_OUTPUTS=(
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_static_effects.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_dynamic_effects.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_pretrend_checks.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_pretrend_summary.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_event_support.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_cohort_support.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_sample_summary.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_legacy_flag_audit.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_diagnostics.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_run_metadata.csv"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_static_results.rds"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_dynamic_results.rds"
  "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_first_stage_models.rds"
  "${SONARQUBE_OUTPUT_DIR}/plots/${SONAR_PREFIX}_dynamic_effects.pdf"
  "${SONARQUBE_OUTPUT_DIR}/plots/${SONAR_PREFIX}_dynamic_effects.png"
  "${SONARQUBE_HTML_OUTPUT}"
  "${SONARQUBE_SUMMARY_OUTPUT}"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_static_effects.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_dynamic_effects.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_pretrend_checks.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_pretrend_summary.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_event_support.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_cohort_support.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_sample_summary.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_legacy_flag_audit.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_diagnostics.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_run_metadata.csv"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_static_results.rds"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_dynamic_results.rds"
  "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_first_stage_models.rds"
  "${CLOC_OUTPUT_DIR}/plots/${CLOC_PREFIX}_dynamic_effects.pdf"
  "${CLOC_OUTPUT_DIR}/plots/${CLOC_PREFIX}_dynamic_effects.png"
  "${CLOC_HTML_OUTPUT}"
  "${CLOC_SUMMARY_OUTPUT}"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_effects.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_dynamic_effects.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_pretrend_checks.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_pretrend_summary.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_differences.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_dynamic_differences.csv"
  "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_static_differences.csv"
  "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_dynamic_differences.csv"
  "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_pretrend_summary.csv"
  "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_panel_alignment_qc.csv"
  "${COMPARISON_OUTPUT_DIR}/plots/${COMPARISON_PREFIX}_dynamic_effects.pdf"
  "${COMPARISON_OUTPUT_DIR}/plots/${COMPARISON_PREFIX}_dynamic_effects.png"
  "${COMPARISON_SUMMARY_OUTPUT}"
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
  echo "** Step 4: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_static_effects.csv" \
    "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_dynamic_effects.csv" \
    "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_pretrend_checks.csv" \
    "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_static_effects.csv" \
    "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_dynamic_effects.csv" \
    "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_pretrend_checks.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_effects.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_dynamic_effects.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_pretrend_checks.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_differences.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_dynamic_differences.csv" \
    "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_static_differences.csv" \
    "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_dynamic_differences.csv" \
    "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_pretrend_summary.csv" \
    "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_panel_alignment_qc.csv" \
    "${SONARQUBE_SUMMARY_OUTPUT}" \
    "${CLOC_SUMMARY_OUTPUT}" \
    "${COMPARISON_SUMMARY_OUTPUT}"
  echo
  echo "SonarQube static effects (four outcomes):"
  cat "${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_static_effects.csv"
  echo
  echo "cloc static effects (four outcomes):"
  cat "${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_static_effects.csv"
  echo
  echo "Static backend differences by outcome:"
  cat "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_differences.csv"
  echo
  echo "Static outcome-definition differences versus primary:"
  cat "${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_static_differences.csv"
  echo
  echo "Panel-alignment QC:"
  cat "${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_panel_alignment_qc.csv"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary outcome:                 ${PRIMARY_OUTCOME}"
  echo "SonarQube static effects:        ${SONARQUBE_OUTPUT_DIR}/${SONAR_PREFIX}_static_effects.csv"
  echo "cloc static effects:             ${CLOC_OUTPUT_DIR}/${CLOC_PREFIX}_static_effects.csv"
  echo "Backend static comparison:       ${COMPARISON_OUTPUT_DIR}/${COMPARISON_PREFIX}_static_differences.csv"
  echo "Outcome static robustness:       ${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_static_differences.csv"
  echo "Outcome dynamic robustness:      ${COMPARISON_OUTPUT_DIR}/${ROBUSTNESS_PREFIX}_dynamic_differences.csv"
  echo "Comparison plot:                 ${COMPARISON_OUTPUT_DIR}/plots/${COMPARISON_PREFIX}_dynamic_effects.pdf"
  echo "SonarQube HTML report:           ${SONARQUBE_HTML_OUTPUT}"
  echo "cloc HTML report:                ${CLOC_HTML_OUTPUT}"
  echo "Comparison summary:              ${COMPARISON_SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       review the 2 x 4 backend/outcome specification matrix"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
