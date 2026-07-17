#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-3c: Validate repository-month AGC DiD input
# -----------------------------------------------------------------------------
# Purpose:
#   Independently validate the strict AGC DiD input produced by run-py-3b.
#   The validator checks panel dimensions, event-time indicators, block-count
#   arithmetic, ratio consistency, NCLOC readiness, detector provenance, and
#   the mismatch/error artifacts created during preparation.
#
# Inputs:
#   repo_python/run-py-3b/strict/panel_event_monthly_agc_py.csv
#   repo_python/run-py-3b/strict/repo_commit_python_snapshot_ncloc.csv
#   repo_python/run-py-3b/strict/repo_month_agc_outcomes_py.csv
#   repo_python/tmp/run-py-3b/strict/
#   detector run metadata and combined run1c validation JSON
#
# Outputs:
#   repo_python/tmp/run-py-3c/strict/
#
# Usage:
#   PANEL_VARIANT=strict AUDIT_FALLBACK_FILES=1 bash proc_sh/run-py-3c-validate-agc-did-input.sh
# 
# Notes:
#   This wrapper is independent and does not call run-py-3b or another shell
#   wrapper. It reuses the logging and output-checking structure of nearby
#   Python experiment wrappers.
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
  echo "ERROR: run-py-3c currently supports PANEL_VARIANT=strict only." >&2
  echo "Got: ${PANEL_VARIANT}" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/validate_agc_did_input.py}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_validate_agc_did_input_${PANEL_VARIANT}_${RUN_TS}.log}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
RUN3B_DIR="${RUN3B_DIR:-${OUTPUT_BASE_DIR}/run-py-3b/${PANEL_VARIANT}}"
RUN3B_QC_DIR="${RUN3B_QC_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-3b/${PANEL_VARIANT}}"
INPUT_PANEL="${INPUT_PANEL:-${RUN3B_DIR}/panel_event_monthly_agc_py.csv}"
REPO_COMMIT_NCLOC="${REPO_COMMIT_NCLOC:-${RUN3B_DIR}/repo_commit_python_snapshot_ncloc.csv}"
REPO_MONTH_OUTCOMES="${REPO_MONTH_OUTCOMES:-${RUN3B_DIR}/repo_month_agc_outcomes_py.csv}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-${OUTPUT_BASE_DIR}/run-py-3a/strict/python_snapshots}"

DETECTOR_PROFILE="${DETECTOR_PROFILE:-codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast}"
DETECTOR_ROOT="${DETECTOR_ROOT:-../python_snapshots_detect/${DETECTOR_PROFILE}/strict}"
RUN_METADATA_TREATMENT="${RUN_METADATA_TREATMENT:-${DETECTOR_ROOT}/run_metadata_treatment.json}"
RUN_METADATA_CONTROL="${RUN_METADATA_CONTROL:-${DETECTOR_ROOT}/run_metadata_control.json}"
COMBINED_VALIDATION="${COMBINED_VALIDATION:-${DETECTOR_ROOT}/qc/run1c/combined_validation_summary.json}"

VALIDATION_DIR="${VALIDATION_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}/${PANEL_VARIANT}}"
SUMMARY_FILE="${SUMMARY_FILE:-${VALIDATION_DIR}/agc_did_input_validation_summary.json}"
AUDIT_FALLBACK_FILES="${AUDIT_FALLBACK_FILES:-1}"

EXPECTED_ROWS="${EXPECTED_ROWS:-1633}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-220}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-853}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-780}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-100}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-120}"
EXPECTED_POST_ROWS="${EXPECTED_POST_ROWS:-432}"
EXPECTED_MIN_TIME="${EXPECTED_MIN_TIME:-2024-01}"
EXPECTED_MAX_TIME="${EXPECTED_MAX_TIME:-2025-08}"
EXPECTED_COMMIT_ROWS="${EXPECTED_COMMIT_ROWS:-1663}"
EXPECTED_REPO_MONTH_OUTCOME_ROWS="${EXPECTED_REPO_MONTH_OUTCOME_ROWS:-3043}"
EXPECTED_PAPER_READY_ROWS="${EXPECTED_PAPER_READY_ROWS:-1568}"
EXPECTED_SNAPSHOT_READY_ROWS="${EXPECTED_SNAPSHOT_READY_ROWS:-1568}"
EXPECTED_TOP_LEVEL_NONMISSING="${EXPECTED_TOP_LEVEL_NONMISSING:-1581}"
EXPECTED_FUNCTION_NONMISSING="${EXPECTED_FUNCTION_NONMISSING:-1566}"
EXPECTED_CLASS_NONMISSING="${EXPECTED_CLASS_NONMISSING:-1475}"

EXPECTED_EXPERIMENT="${EXPECTED_EXPERIMENT:-codellama-7b_4500_complexity_stratified_maxlen2048}"
EXPECTED_CLASSIFIER="${EXPECTED_CLASSIFIER:-svm}"
EXPECTED_REPRESENTATION="${EXPECTED_REPRESENTATION:-ast}"
EXPECTED_SCORE_MODE="${EXPECTED_SCORE_MODE:-decision}"
EXPECTED_MODEL_KEY="${EXPECTED_MODEL_KEY:-codesearchnet_codellama-7b_python_merged_4500ast_}"

mkdir -p "${LOG_DIR}" "${VALIDATION_DIR}"
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
  echo "Validation dir: ${VALIDATION_DIR}"
  echo "Summary:        ${SUMMARY_FILE}"
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

require_positive_integer() {
  local label="$1"
  local value="$2"
  if ! [[ "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: ${label} must be a positive integer. Got: ${value}" >&2
    exit 2
  fi
}

if [[ "${AUDIT_FALLBACK_FILES}" != "0" && "${AUDIT_FALLBACK_FILES}" != "1" ]]; then
  echo "ERROR: AUDIT_FALLBACK_FILES must be 0 or 1. Got: ${AUDIT_FALLBACK_FILES}" >&2
  exit 2
fi

for pair in \
  "EXPECTED_ROWS:${EXPECTED_ROWS}" \
  "EXPECTED_REPOSITORIES:${EXPECTED_REPOSITORIES}" \
  "EXPECTED_TREATMENT_ROWS:${EXPECTED_TREATMENT_ROWS}" \
  "EXPECTED_CONTROL_ROWS:${EXPECTED_CONTROL_ROWS}" \
  "EXPECTED_TREATMENT_REPOSITORIES:${EXPECTED_TREATMENT_REPOSITORIES}" \
  "EXPECTED_CONTROL_REPOSITORIES:${EXPECTED_CONTROL_REPOSITORIES}" \
  "EXPECTED_POST_ROWS:${EXPECTED_POST_ROWS}" \
  "EXPECTED_COMMIT_ROWS:${EXPECTED_COMMIT_ROWS}" \
  "EXPECTED_REPO_MONTH_OUTCOME_ROWS:${EXPECTED_REPO_MONTH_OUTCOME_ROWS}" \
  "EXPECTED_PAPER_READY_ROWS:${EXPECTED_PAPER_READY_ROWS}" \
  "EXPECTED_SNAPSHOT_READY_ROWS:${EXPECTED_SNAPSHOT_READY_ROWS}" \
  "EXPECTED_TOP_LEVEL_NONMISSING:${EXPECTED_TOP_LEVEL_NONMISSING}" \
  "EXPECTED_FUNCTION_NONMISSING:${EXPECTED_FUNCTION_NONMISSING}" \
  "EXPECTED_CLASS_NONMISSING:${EXPECTED_CLASS_NONMISSING}"
do
  label="${pair%%:*}"
  value="${pair#*:}"
  require_positive_integer "${label}" "${value}"
done

echo "============================================================"
echo "${RUN_PREFIX}: validate repository-month AGC DiD input"
echo "Started:                       ${START_TEXT}"
echo "Script name:                   ${SCRIPT_NAME}"
echo "Project root:                  ${PROJECT_ROOT}"
echo "Panel variant:                 ${PANEL_VARIANT}"
echo "Python script:                 ${PY_SCRIPT}"
echo "Input panel:                   ${INPUT_PANEL}"
echo "Repository-commit NCLOC:       ${REPO_COMMIT_NCLOC}"
echo "Repository-month outcomes:     ${REPO_MONTH_OUTCOMES}"
echo "run-py-3b QC directory:        ${RUN3B_QC_DIR}"
echo "Python snapshot root:          ${SNAPSHOT_ROOT}"
echo "Detector profile:              ${DETECTOR_PROFILE}"
echo "Detector root:                 ${DETECTOR_ROOT}"
echo "Treatment metadata:            ${RUN_METADATA_TREATMENT}"
echo "Control metadata:              ${RUN_METADATA_CONTROL}"
echo "Combined detector validation:  ${COMBINED_VALIDATION}"
echo "Audit fallback files:          ${AUDIT_FALLBACK_FILES}"
echo "Validation output:             ${VALIDATION_DIR}"
echo "Log file:                      ${LOG_FILE}"
echo "============================================================"

require_file "Python script" "${PY_SCRIPT}"
require_file "AGC DiD input panel" "${INPUT_PANEL}"
require_file "repository-commit snapshot NCLOC" "${REPO_COMMIT_NCLOC}"
require_file "repository-month AGC outcomes" "${REPO_MONTH_OUTCOMES}"
require_file "treatment run metadata" "${RUN_METADATA_TREATMENT}"
require_file "control run metadata" "${RUN_METADATA_CONTROL}"
require_file "combined detector validation" "${COMBINED_VALIDATION}"
if [[ ! -d "${RUN3B_QC_DIR}" ]]; then
  echo "ERROR: run-py-3b QC directory not found: ${RUN3B_QC_DIR}" >&2
  exit 2
fi
if [[ "${AUDIT_FALLBACK_FILES}" == "1" && ! -d "${SNAPSHOT_ROOT}" ]]; then
  echo "ERROR: Python snapshot root not found: ${SNAPSHOT_ROOT}" >&2
  exit 2
fi

"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

FALLBACK_ARGS=()
if [[ "${AUDIT_FALLBACK_FILES}" == "1" ]]; then
  FALLBACK_ARGS+=(--audit-fallback-files)
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PY_SCRIPT}" \
  --input-panel "${INPUT_PANEL}" \
  --repo-commit-ncloc "${REPO_COMMIT_NCLOC}" \
  --repo-month-outcomes "${REPO_MONTH_OUTCOMES}" \
  --prepare-qc-dir "${RUN3B_QC_DIR}" \
  --snapshot-root "${SNAPSHOT_ROOT}" \
  --run-metadata-treatment "${RUN_METADATA_TREATMENT}" \
  --run-metadata-control "${RUN_METADATA_CONTROL}" \
  --combined-validation "${COMBINED_VALIDATION}" \
  --output-dir "${VALIDATION_DIR}" \
  --panel-label "${PANEL_VARIANT}" \
  --expected-rows "${EXPECTED_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}" \
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-post-rows "${EXPECTED_POST_ROWS}" \
  --expected-min-time "${EXPECTED_MIN_TIME}" \
  --expected-max-time "${EXPECTED_MAX_TIME}" \
  --expected-commit-rows "${EXPECTED_COMMIT_ROWS}" \
  --expected-repo-month-outcome-rows "${EXPECTED_REPO_MONTH_OUTCOME_ROWS}" \
  --expected-paper-ready-rows "${EXPECTED_PAPER_READY_ROWS}" \
  --expected-snapshot-ready-rows "${EXPECTED_SNAPSHOT_READY_ROWS}" \
  --expected-top-level-nonmissing "${EXPECTED_TOP_LEVEL_NONMISSING}" \
  --expected-function-nonmissing "${EXPECTED_FUNCTION_NONMISSING}" \
  --expected-class-nonmissing "${EXPECTED_CLASS_NONMISSING}" \
  --expected-experiment "${EXPECTED_EXPERIMENT}" \
  --expected-classifier "${EXPECTED_CLASSIFIER}" \
  --expected-representation "${EXPECTED_REPRESENTATION}" \
  --expected-score-mode "${EXPECTED_SCORE_MODE}" \
  --expected-model-key "${EXPECTED_MODEL_KEY}" \
  "${FALLBACK_ARGS[@]}"

EXPECTED_OUTPUTS=(
  "${SUMMARY_FILE}"
  "${VALIDATION_DIR}/agc_did_input_validation_checks.csv"
  "${VALIDATION_DIR}/agc_did_input_validation_errors.csv"
  "${VALIDATION_DIR}/agc_did_input_validation_by_source.csv"
  "${VALIDATION_DIR}/agc_did_input_outcome_coverage.csv"
  "${VALIDATION_DIR}/agc_python_snapshot_ncloc_validation_summary.csv"
  "${VALIDATION_DIR}/agc_detector_provenance_validation.csv"
  "${VALIDATION_DIR}/agc_prepare_qc_file_validation.csv"
  "${VALIDATION_DIR}/agc_python_snapshot_fallback_files.csv"
)

for output_path in "${EXPECTED_OUTPUTS[@]}"; do
  require_file "expected validation output" "${output_path}"
done

"${PYTHON_BIN}" - "${SUMMARY_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("r", encoding="utf-8") as handle:
    summary = json.load(handle)
if summary.get("status") != "PASS":
    raise SystemExit(f"Validation summary is not PASS: {path}")
print("Validation status:", summary["status"])
print("Checks passed:", f"{summary['checks_passed']}/{summary['checks_total']}")
print("Fallback files located:", summary["fallback_files_located"])
PY

echo
echo "============================================================"
echo "${RUN_PREFIX} completed successfully."
echo "Validation summary: ${SUMMARY_FILE}"
echo "Validation checks:  ${VALIDATION_DIR}/agc_did_input_validation_checks.csv"
echo "Fallback audit:     ${VALIDATION_DIR}/agc_python_snapshot_fallback_files.csv"
echo "============================================================"
