#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b03-a v6: treatment-timing sensitivity for Python velocity DiD
# ============================================================
#
# Purpose:
#   Reuse the established run-x-b03 Borusyak DiD design while testing whether
#   the event -2 pretrend finding is consistent with a one- or two-month lag
#   between behavioral Cursor adoption and the recorded adoption month.
#
# Input panels:
#   - SonarQube Python-NCLOC backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   - cloc Python-NCLOC backend:
#       repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv
#
# Python velocity outcomes from run-x-b02-v4:
#   - Primary:    log_lines_added_py_source
#   - Robustness: log_lines_added_py_no_merge
#   - Robustness: log_lines_added_py_source_no_tests
#   - Robustness: log_lines_added_py_all
#
# First-stage specifications retained from run-x-b03-v3:
#   1. python_ncloc_adjusted
#      ~ log_age + ncloc + log_contributors + log_stars + log_issues
#        | repo_id + time_index
#   2. no_covariates
#      ~ 1 | repo_id + time_index
#
# Common-support rule:
#   Before fitting any timing specification, keep all controls and only those
#   treated repositories that retain at least one untreated observation under
#   the earliest T-2 clock. This yields one fixed comparison sample across
#   recorded T, T-1, and T-2 and prevents undefined repository fixed effects.
#
# Timing sensitivity specifications:
#   1. recorded_t: effective adoption = recorded event_index
#   2. t_minus_1: effective adoption = recorded event_index - 1
#   3. t_minus_2: effective adoption = recorded event_index - 2
#
# Interpretation:
#   T-1 and T-2 are sensitivity definitions, not assertions that the recorded
#   adoption date is wrong. They test whether the event -2 signal moves into
#   the treatment/reference window when the effective adoption clock is moved
#   earlier. The recorded adoption cohort is always retained for provenance.
#
# Estimator kept unchanged within each timing definition:
#   - repository and calendar-month fixed effects;
#   - repository-clustered standard errors;
#   - static ATT over all rows treated under the effective timing;
#   - post-treatment event effects 0 through +6;
#   - package-native placebo effects -6 through -2;
#   - event month -1 omitted as the reference.
#
# Output layout:
#   repo_x01/run-x-b03/specs/{recorded_t,t_minus_1,t_minus_2}/
#       {python_ncloc_adjusted,no_covariates}/{sonarqube,cloc}/
#   repo_x01/run-x-b03/comparison/timing_sensitivity/
#   repo_x01/tmp/run-x-b03/v6/
#
# This wrapper is self-contained. It was copied from the prior b03 wrapper and
# adjusted for the timing-sensitivity experiment; it never calls an older shell
# script.
#
# Run:
#   bash proc_sh_x01/run-x-b03-a-did-borusyak-python-velocity.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b03"
IMPLEMENTATION_VERSION="v6"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-python-velocity-timing-sensitivity-${RUN_TS}.log}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_velocity_python_added_lines_treatmentclock.R}"
SONARQUBE_INPUT_FILE="${SONARQUBE_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
CLOC_INPUT_FILE="${CLOC_INPUT_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_cloc.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01/${RUN_PREFIX}}"
SPEC_ROOT="${SPEC_ROOT:-${OUTPUT_BASE_DIR}/specs}"
COMPARISON_DIR="${COMPARISON_DIR:-${OUTPUT_BASE_DIR}/comparison/timing_sensitivity}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-repo_x01/tmp/${RUN_PREFIX}/v6}"

PLOT_MIN_EVENT="${PLOT_MIN_EVENT:--6}"
PLOT_MAX_EVENT="${PLOT_MAX_EVENT:-6}"
PRETREND_MIN="${PRETREND_MIN:--6}"
PRETREND_MAX="${PRETREND_MAX:--2}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
BACKEND_EQUIVALENCE_TOLERANCE="${BACKEND_EQUIVALENCE_TOLERANCE:-1e-8}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1863}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-49}"
EXPECTED_CONTROL_REPOS="${EXPECTED_CONTROL_REPOS:-104}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-2}"
EXPECTED_LEGACY_MISMATCH_REPOS="${EXPECTED_LEGACY_MISMATCH_REPOS:-1}"

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
  "${EXPECTED_CONTROL_REPOS}" "${EXPECTED_LEGACY_MISMATCH_ROWS}" \
  "${EXPECTED_LEGACY_MISMATCH_REPOS}"; do
  if ! [[ "${integer_value}" =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: expected an integer option, observed: ${integer_value}" >&2
    exit 1
  fi
done

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${SPEC_ROOT}" "${COMPARISON_DIR}" "${TMP_OUTPUT_DIR}"

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
  echo "${RUN_LABEL}: Python velocity DiD treatment-timing sensitivity"
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
  echo "Covariate specs:                 python_ncloc_adjusted | no_covariates"
  echo "Timing specs:                    recorded_t | t_minus_1 | t_minus_2"
  echo "Timing shifts (months):          0 | -1 | -2"
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

expected_counts_for_timing() {
  local timing_spec="$1"
  case "${timing_spec}" in
    recorded_t)
      EXPECTED_UNTREATED_ROWS_TIMING=1574
      EXPECTED_TREATED_ROWS_TIMING=289
      EXPECTED_DYNAMIC_TREATED_ROWS_TIMING=271
      EXPECTED_TIMING_SHIFTED_ROWS=0
      ;;
    t_minus_1)
      EXPECTED_UNTREATED_ROWS_TIMING=1525
      EXPECTED_TREATED_ROWS_TIMING=338
      EXPECTED_DYNAMIC_TREATED_ROWS_TIMING=304
      EXPECTED_TIMING_SHIFTED_ROWS=49
      ;;
    t_minus_2)
      EXPECTED_UNTREATED_ROWS_TIMING=1476
      EXPECTED_TREATED_ROWS_TIMING=387
      EXPECTED_DYNAMIC_TREATED_ROWS_TIMING=321
      EXPECTED_TIMING_SHIFTED_ROWS=98
      ;;
    *)
      echo "ERROR: unknown timing specification: ${timing_spec}" >&2
      exit 1
      ;;
  esac
}

build_backend_command() {
  local timing_spec="$1"
  local backend="$2"
  local covariate_spec="$3"
  local input_file="$4"
  local output_dir="$5"
  local summary_output="$6"
  local html_output="$7"

  expected_counts_for_timing "${timing_spec}"

  BACKEND_COMMAND=(
    "${RSCRIPT_BIN}"
    "${R_SCRIPT}"
    --mode backend
    --backend "${backend}"
    --covariate-spec "${covariate_spec}"
    --timing-spec "${timing_spec}"
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
    --expected-untreated-rows "${EXPECTED_UNTREATED_ROWS_TIMING}"
    --expected-treated-rows "${EXPECTED_TREATED_ROWS_TIMING}"
    --expected-dynamic-treated-rows "${EXPECTED_DYNAMIC_TREATED_ROWS_TIMING}"
    --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}"
    --expected-legacy-mismatch-repos "${EXPECTED_LEGACY_MISMATCH_REPOS}"
    --expected-timing-shifted-rows "${EXPECTED_TIMING_SHIFTED_ROWS}"
  )
}

TIMING_SPECS=(recorded_t t_minus_1 t_minus_2)
COVARIATE_SPECS=(python_ncloc_adjusted no_covariates)
BACKENDS=(sonarqube cloc)

step_number=0
for timing_spec in "${TIMING_SPECS[@]}"; do
  for covariate_spec in "${COVARIATE_SPECS[@]}"; do
    for backend in "${BACKENDS[@]}"; do
      step_number=$((step_number + 1))
      if [[ "${backend}" == "sonarqube" ]]; then
        input_file="${SONARQUBE_INPUT_FILE}"
      else
        input_file="${CLOC_INPUT_FILE}"
      fi
      output_dir="${SPEC_ROOT}/${timing_spec}/${covariate_spec}/${backend}"
      mkdir -p "${output_dir}"
      summary_output="${TMP_OUTPUT_DIR}/${timing_spec}_${covariate_spec}_${backend}_summary.csv"
      html_output="${output_dir}/velocity_python_added_lines_${backend}_${covariate_spec}_report.html"
      build_backend_command "${timing_spec}" "${backend}" "${covariate_spec}" "${input_file}" "${output_dir}" "${summary_output}" "${html_output}"
      run_command_logged \
        "Step ${step_number}: ${timing_spec} / ${covariate_spec} / ${backend}" \
        "${BACKEND_COMMAND[@]}"
    done
  done
done

TIMING_SUMMARY="${TMP_OUTPUT_DIR}/velocity_python_added_lines_timing_sensitivity_summary.csv"
TIMING_COMPARE_COMMAND=(
  "${RSCRIPT_BIN}"
  "${R_SCRIPT}"
  --mode timing_compare
  --spec-root "${SPEC_ROOT}"
  --comparison-output-dir "${COMPARISON_DIR}"
  --comparison-summary-output "${TIMING_SUMMARY}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --backend-equivalence-tolerance "${BACKEND_EQUIVALENCE_TOLERANCE}"
)
step_number=$((step_number + 1))
run_command_logged "Step ${step_number}: Compare recorded T, T-1, and T-2 timing specifications" "${TIMING_COMPARE_COMMAND[@]}"

PREFIX="velocity_python_added_lines_timing_sensitivity"
PRIMARY_SUMMARY_FILE="${COMPARISON_DIR}/${PREFIX}_primary_summary.csv"
PRIMARY_KEY_TERMS_FILE="${COMPARISON_DIR}/${PREFIX}_primary_key_terms.csv"
RECORDED_MINUS2_ANCHOR_FILE="${COMPARISON_DIR}/${PREFIX}_primary_recorded_minus2_anchor.csv"
STATIC_DIFF_FILE="${COMPARISON_DIR}/${PREFIX}_static_differences_vs_recorded.csv"
PRETREND_SUMMARY_FILE="${COMPARISON_DIR}/${PREFIX}_pretrend_summary.csv"
RECORDED_CLOCK_DYNAMIC_FILE="${COMPARISON_DIR}/${PREFIX}_recorded_clock_dynamic_effects.csv"
TIMING_QC_FILE="${COMPARISON_DIR}/${PREFIX}_qc.csv"
PRIMARY_PLOT_PDF="${COMPARISON_DIR}/plots/${PREFIX}_primary_dynamic_effects.pdf"
PRIMARY_RECORDED_PLOT_PDF="${COMPARISON_DIR}/plots/${PREFIX}_primary_recorded_clock_effects.pdf"

EXPECTED_OUTPUTS=(
  "${PRIMARY_SUMMARY_FILE}"
  "${PRIMARY_KEY_TERMS_FILE}"
  "${RECORDED_MINUS2_ANCHOR_FILE}"
  "${STATIC_DIFF_FILE}"
  "${PRETREND_SUMMARY_FILE}"
  "${RECORDED_CLOCK_DYNAMIC_FILE}"
  "${TIMING_QC_FILE}"
  "${PRIMARY_PLOT_PDF}"
  "${PRIMARY_RECORDED_PLOT_PDF}"
  "${TIMING_SUMMARY}"
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
  echo "** Step $((step_number + 1)): Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${PRIMARY_SUMMARY_FILE}" \
    "${PRIMARY_KEY_TERMS_FILE}" \
    "${RECORDED_MINUS2_ANCHOR_FILE}" \
    "${STATIC_DIFF_FILE}" \
    "${PRETREND_SUMMARY_FILE}" \
    "${TIMING_QC_FILE}" \
    "${TIMING_SUMMARY}"
  echo
  echo "Timing-sensitivity QC:"
  cat "${TIMING_QC_FILE}"
  echo
  echo "Primary static/pretrend summary:"
  cat "${PRIMARY_SUMMARY_FILE}"
  echo
  echo "Primary event -2 and event 0 terms under each effective timing:"
  cat "${PRIMARY_KEY_TERMS_FILE}"
  echo
  echo "Recorded event -2 mapped into each timing specification:"
  cat "${RECORDED_MINUS2_ANCHOR_FILE}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary outcome:                 ${PRIMARY_OUTCOME}"
  echo "Timing specs:                    recorded_t | t_minus_1 | t_minus_2"
  echo "Covariate specs:                 python_ncloc_adjusted | no_covariates"
  echo "Primary timing summary:          ${PRIMARY_SUMMARY_FILE}"
  echo "Primary key event terms:         ${PRIMARY_KEY_TERMS_FILE}"
  echo "Recorded -2 anchor map:          ${RECORDED_MINUS2_ANCHOR_FILE}"
  echo "Static timing differences:       ${STATIC_DIFF_FILE}"
  echo "Timing sensitivity plot:         ${PRIMARY_PLOT_PDF}"
  echo "Recorded-clock plot:             ${PRIMARY_RECORDED_PLOT_PDF}"
  echo "Timing QC:                       ${TIMING_QC_FILE}"
  echo "Summary:                         ${TIMING_SUMMARY}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next decision:                   whether the recorded event -2 signal is consistent with adoption-timing lag/anticipation."
  echo "============================================================"
} | tee -a "${LOG_FILE}"
