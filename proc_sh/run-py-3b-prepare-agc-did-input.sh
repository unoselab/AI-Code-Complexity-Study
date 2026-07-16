#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-3b: Prepare repository-month AGC DiD input
# -----------------------------------------------------------------------------
# Purpose:
#   Aggregate validated AI-generated-like code block predictions to exact
#   repository-month outcomes and merge them into the strict matched Python
#   DiD panel.
#
# Inputs:
#   - Strict matched DiD panel from run-py-1l.
#   - Frozen paper panel for stars, issues, age, and paper NCLOC.
#   - Historical Python snapshots and repository-month manifest from run-py-3a.
#   - Treatment/control detector outputs and validation metadata.
#
# NCLOC specifications:
#   - ncloc_paper: frozen paper value joined by exact repository-month key.
#   - ncloc_python_snapshot: nonblank, non-comment physical lines counted
#     directly from regular Python files in the exported historical snapshot.
#     Docstring lines are retained. No SonarQube input is used.
#
# Main output:
#   repo_python/run-py-3b/strict/panel_event_monthly_agc_py.csv
# 
# Usage: 
#   PANEL_VARIANT=strict bash proc_sh/run-py-3b-prepare-agc-did-input.sh
#
# QC outputs:
#   repo_python/tmp/run-py-3b/strict/
#
# Notes:
#   This wrapper follows the validation and logging structure of existing
#   Python experiment wrappers, but it is independent and does not call any
#   existing shell wrapper.
# =============================================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
if [[ "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: run-py-3b currently supports PANEL_VARIANT=strict only." >&2
  echo "Got: ${PANEL_VARIANT}" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_agc_did_input.py}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_prepare_agc_did_input_${PANEL_VARIANT}_${RUN_TS}.log}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
BASE_PANEL="${BASE_PANEL:-${OUTPUT_BASE_DIR}/run-py-1l/panel_event_matched_strict.csv}"
PAPER_PANEL="${PAPER_PANEL:-data/panel_event_monthly.csv}"
SNAPSHOT_MANIFEST="${SNAPSHOT_MANIFEST:-${OUTPUT_BASE_DIR}/run-py-3a/strict/repo_month_snapshot_manifest.csv}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-${OUTPUT_BASE_DIR}/run-py-3a/strict/python_snapshots}"

DETECTOR_PROFILE="${DETECTOR_PROFILE:-codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast}"
DETECTOR_ROOT="${DETECTOR_ROOT:-../python_snapshots_detect/${DETECTOR_PROFILE}/strict}"

BLOCK_TREATMENT="${BLOCK_TREATMENT:-${DETECTOR_ROOT}/block_predictions_treatment.csv}"
BLOCK_CONTROL="${BLOCK_CONTROL:-${DETECTOR_ROOT}/block_predictions_control.csv}"
REPO_MONTH_TREATMENT="${REPO_MONTH_TREATMENT:-${DETECTOR_ROOT}/repo_month_agc_panel_treatment.csv}"
REPO_MONTH_CONTROL="${REPO_MONTH_CONTROL:-${DETECTOR_ROOT}/repo_month_agc_panel_control.csv}"
RUN_METADATA_TREATMENT="${RUN_METADATA_TREATMENT:-${DETECTOR_ROOT}/run_metadata_treatment.json}"
RUN_METADATA_CONTROL="${RUN_METADATA_CONTROL:-${DETECTOR_ROOT}/run_metadata_control.json}"
COMBINED_VALIDATION="${COMBINED_VALIDATION:-${DETECTOR_ROOT}/qc/run1c/combined_validation_summary.json}"

MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/${PANEL_VARIANT}}"
QC_DIR="${QC_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}/${PANEL_VARIANT}}"
OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/panel_event_monthly_agc_py.csv}"
REPO_COMMIT_NCLOC_OUTPUT="${REPO_COMMIT_NCLOC_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_commit_python_snapshot_ncloc.csv}"
REPO_MONTH_OUTCOMES_OUTPUT="${REPO_MONTH_OUTCOMES_OUTPUT:-${MAIN_OUTPUT_DIR}/repo_month_agc_outcomes_py.csv}"
CHUNKSIZE="${CHUNKSIZE:-250000}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${QC_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

finish() {
  status=$?
  end_epoch="$(date +%s)"
  elapsed=$((end_epoch - START_EPOCH))
  printf -v elapsed_text '%02d:%02d:%02d' \
    $((elapsed / 3600)) \
    $(((elapsed % 3600) / 60)) \
    $((elapsed % 60))

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} timing summary"
  echo "Started:        ${START_TEXT}"
  echo "Completed:      $(date)"
  echo "Elapsed:        ${elapsed_text}"
  echo "Exit code:      ${status}"
  echo "Log file:       ${LOG_FILE}"
  echo "Main output:    ${OUTPUT_FILE}"
  echo "QC directory:   ${QC_DIR}"
  echo "============================================================"

  trap - EXIT
  exit "${status}"
}
trap finish EXIT

require_file() {
  local label="$1"
  local path="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}" >&2
    exit 2
  fi
}

echo "============================================================"
echo "${RUN_PREFIX}: prepare repository-month AGC DiD input"
echo "Started:                    ${START_TEXT}"
echo "Script name:                ${SCRIPT_NAME}"
echo "Project root:               ${PROJECT_ROOT}"
echo "Panel variant:              ${PANEL_VARIANT}"
echo "Python script:              ${PY_SCRIPT}"
echo "Base panel:                 ${BASE_PANEL}"
echo "Frozen paper panel:         ${PAPER_PANEL}"
echo "Snapshot manifest:          ${SNAPSHOT_MANIFEST}"
echo "Python snapshot root:       ${SNAPSHOT_ROOT}"
echo "Detector profile:           ${DETECTOR_PROFILE}"
echo "Detector root:              ${DETECTOR_ROOT}"
echo "Treatment block input:      ${BLOCK_TREATMENT}"
echo "Control block input:        ${BLOCK_CONTROL}"
echo "Treatment repo-month input: ${REPO_MONTH_TREATMENT}"
echo "Control repo-month input:   ${REPO_MONTH_CONTROL}"
echo "Combined validation:        ${COMBINED_VALIDATION}"
echo "Chunk size:                 ${CHUNKSIZE}"
echo "Main output:                ${OUTPUT_FILE}"
echo "Commit NCLOC output:        ${REPO_COMMIT_NCLOC_OUTPUT}"
echo "Repo-month outcomes:        ${REPO_MONTH_OUTCOMES_OUTPUT}"
echo "QC directory:               ${QC_DIR}"
echo "Log file:                   ${LOG_FILE}"
echo "============================================================"

require_file "Python script" "${PY_SCRIPT}"
require_file "strict base panel" "${BASE_PANEL}"
require_file "frozen paper panel" "${PAPER_PANEL}"
require_file "snapshot manifest" "${SNAPSHOT_MANIFEST}"
if [[ ! -d "${SNAPSHOT_ROOT}" ]]; then
  echo "ERROR: Python snapshot root not found: ${SNAPSHOT_ROOT}" >&2
  exit 2
fi
require_file "treatment block predictions" "${BLOCK_TREATMENT}"
require_file "control block predictions" "${BLOCK_CONTROL}"
require_file "treatment repo-month AGC panel" "${REPO_MONTH_TREATMENT}"
require_file "control repo-month AGC panel" "${REPO_MONTH_CONTROL}"
require_file "treatment run metadata" "${RUN_METADATA_TREATMENT}"
require_file "control run metadata" "${RUN_METADATA_CONTROL}"
require_file "combined detector validation" "${COMBINED_VALIDATION}"

if ! [[ "${CHUNKSIZE}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: CHUNKSIZE must be a positive integer. Got: ${CHUNKSIZE}" >&2
  exit 2
fi

"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PY_SCRIPT}" \
  --base-panel "${BASE_PANEL}" \
  --paper-panel "${PAPER_PANEL}" \
  --snapshot-manifest "${SNAPSHOT_MANIFEST}" \
  --snapshot-root "${SNAPSHOT_ROOT}" \
  --block-treatment "${BLOCK_TREATMENT}" \
  --block-control "${BLOCK_CONTROL}" \
  --repo-month-treatment "${REPO_MONTH_TREATMENT}" \
  --repo-month-control "${REPO_MONTH_CONTROL}" \
  --run-metadata-treatment "${RUN_METADATA_TREATMENT}" \
  --run-metadata-control "${RUN_METADATA_CONTROL}" \
  --combined-validation "${COMBINED_VALIDATION}" \
  --output "${OUTPUT_FILE}" \
  --repo-commit-ncloc-output "${REPO_COMMIT_NCLOC_OUTPUT}" \
  --repo-month-outcomes-output "${REPO_MONTH_OUTCOMES_OUTPUT}" \
  --qc-dir "${QC_DIR}" \
  --panel-label "${PANEL_VARIANT}" \
  --chunksize "${CHUNKSIZE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_FILE}"
  "${REPO_COMMIT_NCLOC_OUTPUT}"
  "${REPO_MONTH_OUTCOMES_OUTPUT}"
  "${QC_DIR}/agc_did_input_qc.csv"
  "${QC_DIR}/agc_repo_month_match_summary.csv"
  "${QC_DIR}/agc_unmatched_base_repo_months.csv"
  "${QC_DIR}/agc_unmatched_detector_repo_months.csv"
  "${QC_DIR}/agc_detector_metadata_comparison.csv"
  "${QC_DIR}/agc_outcome_descriptive_summary.csv"
  "${QC_DIR}/agc_block_kind_aggregation_qc.csv"
  "${QC_DIR}/agc_block_kind_aggregation_mismatches.csv"
  "${QC_DIR}/agc_output_column_manifest.csv"
  "${QC_DIR}/agc_paper_covariate_match_summary.csv"
  "${QC_DIR}/agc_unmatched_paper_covariate_repo_months.csv"
  "${QC_DIR}/agc_paper_covariate_missingness.csv"
  "${QC_DIR}/agc_paper_duplicate_key_summary.csv"
  "${QC_DIR}/agc_paper_duplicate_key_conflicts.csv"
  "${QC_DIR}/agc_python_snapshot_ncloc_summary.csv"
  "${QC_DIR}/agc_python_snapshot_ncloc_failures.csv"
  "${QC_DIR}/agc_unmatched_python_snapshot_ncloc_rows.csv"
  "${QC_DIR}/agc_ncloc_comparison_summary.csv"
)

for output_path in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_path}" ]]; then
    echo "ERROR: expected output not found: ${output_path}" >&2
    exit 3
  fi
done

echo
echo "============================================================"
echo "${RUN_PREFIX} completed successfully."
echo "Main output rows: $(( $(wc -l < "${OUTPUT_FILE}") - 1 ))"
echo "Main output:      ${OUTPUT_FILE}"
echo "Commit NCLOC:     ${REPO_COMMIT_NCLOC_OUTPUT}"
echo "Repo-month data:  ${REPO_MONTH_OUTCOMES_OUTPUT}"
echo "QC summary:       ${QC_DIR}/agc_did_input_qc.csv"
echo "Match summary:    ${QC_DIR}/agc_repo_month_match_summary.csv"
echo "============================================================"
