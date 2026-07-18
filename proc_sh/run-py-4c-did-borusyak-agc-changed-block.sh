#!/usr/bin/env bash
set -euo pipefail

# Run the Borusyak DiD analysis for AGC changed-block outcomes.
#
# Inputs:
#   - Validated run-py-4a changed-block panel
#   - PASS summary from run-py-4b
#   - Shared Borusyak helper functions
#
# Outputs:
#   - HTML analysis report
#   - Static and dynamic effect CSV files
#   - Dynamic event-study PDF
#   - Sample, coverage, pretrend, panel-check, metadata, and error CSV files
#
# Usage:
#   PANEL_VARIANT=strict bash proc_sh/run-py-4c-did-borusyak-agc-changed-block.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: only PANEL_VARIANT=strict is supported." >&2
  exit 1
fi

RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_AGC_ChangedBlock.Rmd}"
PANEL_FILE="${PANEL_FILE:-repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv}"
VALIDATION_FILE="${VALIDATION_FILE:-repo_python/tmp/run-py-4b/strict/agc_changed_block_panel_validation_summary.json}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
OUT_DIR="${OUT_DIR:-repo_python/run-py-4c/strict}"
HTML_NAME="${HTML_NAME:-DiffInDiffBorusyak_AGC_ChangedBlock.html}"

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-4c_did_borusyak_agc_changed_block_${RUN_TS}.log}"

HTML_FILE="${OUT_DIR}/${HTML_NAME}"
STATIC_FILE="${OUT_DIR}/borusyak_agc_changed_block_static_effects.csv"
DYNAMIC_FILE="${OUT_DIR}/borusyak_agc_changed_block_dynamic_effects.csv"
PDF_FILE="${OUT_DIR}/dynamic_effects_borusyak_agc_changed_block.pdf"
SAMPLE_FILE="${OUT_DIR}/borusyak_agc_changed_block_sample_by_outcome.csv"
PANEL_CHECK_FILE="${OUT_DIR}/borusyak_agc_changed_block_panel_checks.csv"
MODEL_ERROR_FILE="${OUT_DIR}/borusyak_agc_changed_block_model_errors.csv"

mkdir -p "${LOG_DIR}" "${OUT_DIR}"

for file in "${RMD_FILE}" "${PANEL_FILE}" "${VALIDATION_FILE}" "${HELPER_FILE}"; do
  if [[ ! -f "${file}" ]]; then
    echo "ERROR: required file not found: ${file}" >&2
    exit 1
  fi
done

if ! command -v Rscript >/dev/null 2>&1; then
  echo "ERROR: Rscript was not found in PATH." >&2
  exit 1
fi

rm -f \
  "${HTML_FILE}" \
  "${STATIC_FILE}" \
  "${DYNAMIC_FILE}" \
  "${PDF_FILE}" \
  "${SAMPLE_FILE}" \
  "${PANEL_CHECK_FILE}" \
  "${MODEL_ERROR_FILE}"

export RMD_FILE PANEL_FILE VALIDATION_FILE HELPER_FILE OUT_DIR HTML_NAME PANEL_VARIANT

START_EPOCH="$(date +%s)"

{
  echo "============================================================"
  echo "run-py-4c: Borusyak DiD for AGC changed-block outcomes"
  echo "Started:                  $(date)"
  echo "Panel variant:            ${PANEL_VARIANT}"
  echo "Rmd file:                 ${RMD_FILE}"
  echo "Input panel:              ${PANEL_FILE}"
  echo "Validation summary:       ${VALIDATION_FILE}"
  echo "Helper file:              ${HELPER_FILE}"
  echo "Output directory:         ${OUT_DIR}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"

  Rscript -e "rmarkdown::render(
    input = Sys.getenv('RMD_FILE'),
    output_file = Sys.getenv('HTML_NAME'),
    output_dir = Sys.getenv('OUT_DIR'),
    params = list(
      panel_file = Sys.getenv('PANEL_FILE'),
      validation_summary_file = Sys.getenv('VALIDATION_FILE'),
      helper_file = Sys.getenv('HELPER_FILE'),
      out_dir = Sys.getenv('OUT_DIR'),
      panel_label = Sys.getenv('PANEL_VARIANT')
    ),
    knit_root_dir = Sys.getenv('PROJECT_ROOT'),
    envir = new.env(parent = globalenv()),
    quiet = FALSE
  )"

  for file in \
    "${HTML_FILE}" \
    "${STATIC_FILE}" \
    "${DYNAMIC_FILE}" \
    "${PDF_FILE}" \
    "${SAMPLE_FILE}" \
    "${PANEL_CHECK_FILE}" \
    "${MODEL_ERROR_FILE}"; do
    if [[ ! -s "${file}" ]]; then
      echo "ERROR: expected non-empty output was not created: ${file}" >&2
      exit 1
    fi
  done

  END_EPOCH="$(date +%s)"
  ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
  printf -v ELAPSED_TIME '%02d:%02d:%02d' \
    "$((ELAPSED_SECONDS / 3600))" \
    "$(((ELAPSED_SECONDS % 3600) / 60))" \
    "$((ELAPSED_SECONDS % 60))"

  echo
  echo "============================================================"
  echo "run-py-4c completed successfully."
  echo "Completed:                $(date)"
  echo "Elapsed:                  ${ELAPSED_TIME}"
  echo "HTML report:              ${HTML_FILE}"
  echo "Static effects:           ${STATIC_FILE}"
  echo "Dynamic effects:          ${DYNAMIC_FILE}"
  echo "Dynamic figure:           ${PDF_FILE}"
  echo "Sample summary:           ${SAMPLE_FILE}"
  echo "Panel checks:             ${PANEL_CHECK_FILE}"
  echo "Model errors:             ${MODEL_ERROR_FILE}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
