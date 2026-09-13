#!/usr/bin/env bash
set -euo pipefail

# run-x-b09 v2: detector-localized Python velocity timing sensitivity
#
# This wrapper is based on the run-x-b08 execution structure but is independent
# of that wrapper. It performs two complementary analyses:
#
#   1. Monthly treatment-timing sensitivity under recorded T, T-1, and T-2.
#   2. Weekly event-time analysis using the exact first observable Cursor-related
#      commit encoded in the established America/Chicago weekly panel.
#
# Required inputs
# ---------------
# MONTHLY_LOCALIZED_PANEL
#   run-x-b08-v4 repository-month panel containing the six localized velocity
#   outcomes and FECS covariates.
#
# MONTHLY_STATIC_REFERENCE
#   run-x-b08-v4 static estimates. The recorded-T models must reproduce these
#   estimates and standard errors within REFERENCE_TOLERANCE.
#
# WEEKLY_PANEL_FILE
#   run-x-b03-d-v4 America/Chicago repository-week panel. Its treatment week is
#   based on the exact first observable Cursor-related commit.
#
# B02_FILE_ADDITIONS
#   run-x-b02 file-change records. Only valid source-included records contribute
#   to localized velocity; excluded binary records are audited but not recoded.
#
# B02_COMMIT_FILE
#   run-x-b02 commit-level records supplying exact commit timestamps.
#
# NPR_FILE and ML_FILE
#   File-level detector measurements for RF, CM, and RF+CM.
#
# Outputs
# -------
# OUTPUT_DIR contains monthly timing comparisons, weekly localized estimates,
# pre-adoption summaries, common-support diagnostics, and reconciliation tables.

RUN_PREFIX="run-x-b09"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_detector_localized_python_velocity_sensitivity.R}"
if [[ ! -f "${R_SCRIPT}" ]]; then
  R_SCRIPT="proc_script_x01/did_borusyak_detector_localized_python_velocity_sensitivity-v2.R"
fi

MONTHLY_LOCALIZED_PANEL="${MONTHLY_LOCALIZED_PANEL:-repo_x01/run-x-b08/detector-localized-python-velocity-v4/detector_localized_python_velocity_panel.csv.gz}"
MONTHLY_STATIC_REFERENCE="${MONTHLY_STATIC_REFERENCE:-repo_x01/run-x-b08/detector-localized-python-velocity-v4/detector_localized_python_velocity_static_effects.csv}"
WEEKLY_PANEL_FILE="${WEEKLY_PANEL_FILE:-repo_x01/run-x-b03-d-v4/panels/velocity_did_panel_python_added_lines_weekly_chicago.csv}"
B02_FILE_ADDITIONS="${B02_FILE_ADDITIONS:-repo_x01/run-x-b02/python-added-lines/python_added_lines_file.csv}"
B02_COMMIT_FILE="${B02_COMMIT_FILE:-repo_x01/run-x-b02/python-added-lines/python_added_lines_commit.csv}"
NPR_FILE="${NPR_FILE:-../../detect_code_gpt/output/snapshot_npr/run-x-c05/file-quality-burden-v1/python_fun_cfun_file_quality_burden.csv.gz}"
ML_FILE="${ML_FILE:-repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv}"

NPR_THRESHOLD="${NPR_THRESHOLD:-1.515059}"
ML_THRESHOLD="${ML_THRESHOLD:-0.50}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
MONTHLY_PRE_MIN="${MONTHLY_PRE_MIN:--6}"
MONTHLY_POST_MAX="${MONTHLY_POST_MAX:-6}"
WEEKLY_PRE_MIN="${WEEKLY_PRE_MIN:--12}"
WEEKLY_POST_MAX="${WEEKLY_POST_MAX:-12}"
REFERENCE_TOLERANCE="${REFERENCE_TOLERANCE:-1e-10}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_MONTHLY_ROWS="${EXPECTED_MONTHLY_ROWS:-1954}"
EXPECTED_WEEKLY_ROWS="${EXPECTED_WEEKLY_ROWS:-8599}"
EXPECTED_COMMON_WEEKLY_ROWS="${EXPECTED_COMMON_WEEKLY_ROWS:-8595}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_EVENT_ZERO_SUPPORT="${EXPECTED_EVENT_ZERO_SUPPORT:-62}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}/detector-localized-python-velocity-sensitivity-v2}"
LOG_DIR="${LOG_DIR:-logs/${RUN_PREFIX}}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-detector-localized-python-velocity-sensitivity-${RUN_TS}.log}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

if ! command -v Rscript >/dev/null 2>&1; then
  echo "ERROR: Rscript was not found." >&2
  exit 1
fi
if [[ ! -f "${R_SCRIPT}" ]]; then
  echo "ERROR: R script not found: ${R_SCRIPT}" >&2
  exit 1
fi
if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi
if [[ "${SELF_TEST_ONLY}" != "0" && "${SELF_TEST_ONLY}" != "1" ]]; then
  echo "ERROR: SELF_TEST_ONLY must be 0 or 1." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

SCRIPT_VERSION_RAW="$(Rscript "${R_SCRIPT}" --version)"
# Normalize line endings and surrounding whitespace before exact comparison.
SCRIPT_VERSION="$(printf '%s' "${SCRIPT_VERSION_RAW}" | tr -d '\r' | awk '{$1=$1; print}')"
if [[ "${SCRIPT_VERSION}" != "${RUN_LABEL}" ]]; then
  echo "ERROR: wrapper/R version mismatch. Expected ${RUN_LABEL}; observed ${SCRIPT_VERSION}." >&2
  exit 1
fi

R_VERSION="$(Rscript --version 2>&1 | head -1)"
PACKAGE_VERSIONS="$(Rscript -e 'p <- c("data.table", "didimputation", "fixest"); cat(paste(paste(p, vapply(p, function(x) as.character(utils::packageVersion(x)), character(1)), sep="="), collapse="; "))')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: detector-localized Python velocity sensitivity"
  echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                  ${PROJECT_ROOT}"
  echo "R version:                     ${R_VERSION}"
  echo "R packages:                    ${PACKAGE_VERSIONS}"
  echo "R script:                      ${R_SCRIPT}"
  echo "R script SHA256:               ${R_SCRIPT_SHA256}"
  echo "Monthly localized panel:       ${MONTHLY_LOCALIZED_PANEL}"
  echo "Monthly static reference:      ${MONTHLY_STATIC_REFERENCE}"
  echo "Weekly exact-date panel:       ${WEEKLY_PANEL_FILE}"
  echo "B02 file additions:            ${B02_FILE_ADDITIONS}"
  echo "B02 commit timestamps:         ${B02_COMMIT_FILE}"
  echo "C05 NPR file scores:           ${NPR_FILE}"
  echo "I06 ML file scores:            ${ML_FILE}"
  echo "NPR threshold:                 ${NPR_THRESHOLD} (strict >)"
  echo "ML threshold:                  ${ML_THRESHOLD} (strict >)"
  echo "Monthly timing specifications: T, T-1, T-2"
  echo "Weekly calendar:               America/Chicago; Monday-start weeks"
  echo "Specifications:                FECS, FEOS"
  echo "Monthly event window:          ${MONTHLY_PRE_MIN}:${MONTHLY_POST_MAX}; -1 omitted"
  echo "Weekly event window:           ${WEEKLY_PRE_MIN}:${WEEKLY_POST_MAX}; -1 omitted"
  echo "Output directory:              ${OUTPUT_DIR}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Parse and structural self-test"
  echo "Command: Rscript ${R_SCRIPT} --self-test"
} | tee -a "${LOG_FILE}"
Rscript -e 'invisible(parse(file=commandArgs(trailingOnly=TRUE)[[1L]])); cat("R parse: PASS\n")' "${R_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"
Rscript "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL}: SELF-TEST-ONLY SUCCESS" | tee -a "${LOG_FILE}"
  exit 0
fi

for required_file in \
  "${MONTHLY_LOCALIZED_PANEL}" \
  "${MONTHLY_STATIC_REFERENCE}" \
  "${WEEKLY_PANEL_FILE}" \
  "${B02_FILE_ADDITIONS}" \
  "${B02_COMMIT_FILE}" \
  "${NPR_FILE}" \
  "${ML_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required input not found: ${required_file}" | tee -a "${LOG_FILE}" >&2
    exit 2
  fi
done

COMMAND=(
  Rscript "${R_SCRIPT}"
  --monthly-panel-file "${MONTHLY_LOCALIZED_PANEL}"
  --monthly-static-reference "${MONTHLY_STATIC_REFERENCE}"
  --weekly-panel-file "${WEEKLY_PANEL_FILE}"
  --file-additions-file "${B02_FILE_ADDITIONS}"
  --commit-file "${B02_COMMIT_FILE}"
  --npr-file "${NPR_FILE}"
  --ml-file "${ML_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --npr-threshold "${NPR_THRESHOLD}"
  --ml-threshold "${ML_THRESHOLD}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --monthly-pre-min "${MONTHLY_PRE_MIN}"
  --monthly-post-max "${MONTHLY_POST_MAX}"
  --weekly-pre-min "${WEEKLY_PRE_MIN}"
  --weekly-post-max "${WEEKLY_POST_MAX}"
  --reference-tolerance "${REFERENCE_TOLERANCE}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-monthly-rows "${EXPECTED_MONTHLY_ROWS}"
  --expected-weekly-rows "${EXPECTED_WEEKLY_ROWS}"
  --expected-common-weekly-rows "${EXPECTED_COMMON_WEEKLY_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-event-zero-support "${EXPECTED_EVENT_ZERO_SUPPORT}"
)

{
  echo
  echo "** Step 2: Estimate monthly treatment-clock sensitivity and weekly exact-date effects"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n'
} | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_static_effects.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_dynamic_effects.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_recorded_clock_effects.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_pretrend_summary.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_event_support.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_recorded_t_reproduction.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_monthly_recorded_minus2_anchor.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_panel.csv.gz"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_static_effects.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_dynamic_effects.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_pretrend_summary.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_event_support.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_key_event_times.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_weekly_monthly_reconciliation.csv"
  "${OUTPUT_DIR}/detector_localized_velocity_sensitivity_qc.csv"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected nonempty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 3
  fi
done

{
  echo
  echo "Monthly timing pre-adoption summary:"
  cat "${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_pretrend_summary.csv"
  echo
  echo "Weekly pre-adoption summary:"
  cat "${OUTPUT_DIR}/detector_localized_velocity_weekly_pretrend_summary.csv"
  echo
  echo "QC:"
  cat "${OUTPUT_DIR}/detector_localized_velocity_sensitivity_qc.csv"
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Monthly timing estimates:      ${OUTPUT_DIR}/detector_localized_velocity_monthly_timing_dynamic_effects.csv"
  echo "Weekly dynamic estimates:      ${OUTPUT_DIR}/detector_localized_velocity_weekly_dynamic_effects.csv"
  echo "QC:                            ${OUTPUT_DIR}/detector_localized_velocity_sensitivity_qc.csv"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
