#!/usr/bin/env bash
set -euo pipefail

# run-x-b08 v4: detector-localized Python velocity DiD
#
# This wrapper follows the established run-x-b03 execution structure while
# remaining independent of earlier shell wrappers.
#
# Required inputs:
#   B06_PANEL_FILE        Matched repository-month panel with treatment timing,
#                         FECS covariates, and whole-Python source additions.
#   B02_FILE_ADDITIONS    File-change records produced by the B02 collector.
#   NPR_FILE              C05 file-level NPR measurements for all three scopes.
#   ML_FILE               I06 file-level ML shares for all three scopes.
#
# Primary output:
#   TABLE_OUTPUT          LaTeX table containing FECS and FEOS ATT, SE, and
#                         percentage changes for NPR/ML x RF/CM/RF+CM.
#
# Additional outputs:
#   OUTPUT_DIR contains the constructed panel, static and dynamic estimates,
#   localization support, path-join audits, model diagnostics, and metadata.

RUN_PREFIX="run-x-b08"
IMPLEMENTATION_VERSION="v4"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/did_borusyak_detector_localized_python_velocity.R}"
if [[ ! -f "${R_SCRIPT}" ]]; then
  R_SCRIPT="proc_script_x01/did_borusyak_detector_localized_python_velocity-v4.R"
fi

B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
B02_FILE_ADDITIONS="${B02_FILE_ADDITIONS:-repo_x01/run-x-b02/python-added-lines/python_added_lines_file.csv}"
NPR_FILE="${NPR_FILE:-../../detect_code_gpt/output/snapshot_npr/run-x-c05/file-quality-burden-v1/python_fun_cfun_file_quality_burden.csv.gz}"
ML_FILE="${ML_FILE:-repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv}"

NPR_THRESHOLD="${NPR_THRESHOLD:-1.515059}"
ML_THRESHOLD="${ML_THRESHOLD:-0.50}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
MIN_EVENT="${MIN_EVENT:--6}"
MAX_EVENT="${MAX_EVENT:-6}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_ROWS="${EXPECTED_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}/detector-localized-python-velocity-v4}"
TABLE_OUTPUT="${TABLE_OUTPUT:-tex/tb_did_velocity_python_localized-v4.tex}"
LOG_DIR="${LOG_DIR:-logs/${RUN_PREFIX}}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-did-borusyak-detector-localized-python-velocity-${RUN_TS}.log}"

if ! command -v Rscript >/dev/null 2>&1; then
  echo "ERROR: Rscript was not found." >&2
  exit 1
fi

for required_file in "${R_SCRIPT}" "${B06_PANEL_FILE}" "${B02_FILE_ADDITIONS}" "${NPR_FILE}" "${ML_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}" "$(dirname "${TABLE_OUTPUT}")" "${LOG_DIR}"

SCRIPT_VERSION="$(Rscript "${R_SCRIPT}" --version)"
if [[ "${SCRIPT_VERSION}" != "${RUN_LABEL}" ]]; then
  echo "ERROR: wrapper/R version mismatch. Replace both files with ${IMPLEMENTATION_VERSION}." >&2
  exit 1
fi

R_VERSION="$(Rscript --version 2>&1 | head -1)"
PACKAGE_VERSIONS="$(Rscript -e 'p <- c("data.table", "didimputation", "fixest"); cat(paste(paste(p, vapply(p, function(x) as.character(utils::packageVersion(x)), character(1)), sep="="), collapse="; "))')"
R_SCRIPT_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: detector-localized Python velocity DiD"
  echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                  ${PROJECT_ROOT}"
  echo "R version:                     ${R_VERSION}"
  echo "R packages:                    ${PACKAGE_VERSIONS}"
  echo "R script:                      ${R_SCRIPT}"
  echo "R script SHA256:               ${R_SCRIPT_SHA256}"
  echo "B06 panel:                     ${B06_PANEL_FILE}"
  echo "B02 file additions:            ${B02_FILE_ADDITIONS}"
  echo "C05 NPR file scores:           ${NPR_FILE}"
  echo "I06 ML file scores:            ${ML_FILE}"
  echo "NPR threshold:                 ${NPR_THRESHOLD} (strict >)"
  echo "ML threshold:                  ${ML_THRESHOLD} (strict >)"
  echo "Scopes:                        RF, CM, RF+CM"
  echo "Specifications:                FECS, FEOS"
  echo "Output directory:              ${OUTPUT_DIR}"
  echo "LaTeX table:                   ${TABLE_OUTPUT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 1: Parse and structural self-test" | tee -a "${LOG_FILE}"
Rscript -e 'invisible(parse(file=commandArgs(trailingOnly=TRUE)[[1L]])); cat("R parse: PASS\n")' "${R_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"
Rscript "${R_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 2: Construct outcomes and estimate FECS/FEOS" | tee -a "${LOG_FILE}"
COMMAND=(
  Rscript "${R_SCRIPT}"
  --b06-panel-file "${B06_PANEL_FILE}"
  --file-additions-file "${B02_FILE_ADDITIONS}"
  --npr-file "${NPR_FILE}"
  --ml-file "${ML_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --table-output "${TABLE_OUTPUT}"
  --npr-threshold "${NPR_THRESHOLD}"
  --ml-threshold "${ML_THRESHOLD}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --min-event "${MIN_EVENT}"
  --max-event "${MAX_EVENT}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-rows "${EXPECTED_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
)
printf 'Command:' | tee -a "${LOG_FILE}"
printf ' %q' "${COMMAND[@]}" | tee -a "${LOG_FILE}"
printf '\n' | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/detector_localized_python_velocity_panel.csv.gz"
  "${OUTPUT_DIR}/detector_localized_python_velocity_localization_summary.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_join_audit.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_b02_count_audit.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_b02_monthly_reconciliation.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_reconciliation.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_static_effects.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_dynamic_effects.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_model_diagnostics.csv"
  "${OUTPUT_DIR}/detector_localized_python_velocity_run_metadata.csv"
  "${TABLE_OUTPUT}"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected nonempty output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Static estimates:              ${OUTPUT_DIR}/detector_localized_python_velocity_static_effects.csv"
  echo "Dynamic estimates:             ${OUTPUT_DIR}/detector_localized_python_velocity_dynamic_effects.csv"
  echo "LaTeX table:                   ${TABLE_OUTPUT}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
