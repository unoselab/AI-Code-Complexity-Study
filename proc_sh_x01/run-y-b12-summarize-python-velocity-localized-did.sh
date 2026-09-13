#!/usr/bin/env bash
set -euo pipefail

# run-y-b12 v1: summarize whole-Python and detector-localized velocity effects.
#
# This wrapper follows the established run-y summary-script structure while
# remaining independent of earlier wrappers. It passes explicit inputs and
# validation expectations to the corresponding Python script.
#
# Inputs
# ------
# OVERALL_SUMMARY_FILE
#   run-y-b02 summary containing the four whole-Python velocity outcomes. Only
#   O1, Python source additions, is retained for the replacement table.
# LOCALIZED_STATIC_FILE
#   run-x-b08 static effects for NPR and ML localization under RF, CM, and
#   RF+CM scopes and the FECS and FEOS specifications.
#
# Outputs
# -------
# TABLE_OUTPUT
#   Replacement LaTeX table for tb:did-velocity-python.
# OUTPUT_DIR
#   Long-form summary, reconciliation checks, and run metadata.

RUN_PREFIX="run-y-b12"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/summarize_python_velocity_localized_did.py}"
if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
  PYTHON_SCRIPT="proc_script_x01/summarize_python_velocity_localized_did-v1.py"
fi

OVERALL_SUMMARY_FILE="${OVERALL_SUMMARY_FILE:-repo_x01/run-y-b02/python-velocity-did-table-v1/python_velocity_did_summary.csv}"
LOCALIZED_STATIC_FILE="${LOCALIZED_STATIC_FILE:-repo_x01/run-x-b08/detector-localized-python-velocity-v4/detector_localized_python_velocity_static_effects.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/${RUN_PREFIX}/python-velocity-localized-did-table-v1}"
TABLE_OUTPUT="${TABLE_OUTPUT:-tex/tb_did_velocity_python_localized-v1.tex}"
LOG_DIR="${LOG_DIR:-logs/${RUN_PREFIX}}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_OVERALL_ROWS="${EXPECTED_OVERALL_ROWS:-8}"
EXPECTED_LOCALIZED_ROWS="${EXPECTED_LOCALIZED_ROWS:-12}"
EXPECTED_TREATED_OBSERVATIONS="${EXPECTED_TREATED_OBSERVATIONS:-363}"
EXPECTED_FIRST_STAGE_OBSERVATIONS="${EXPECTED_FIRST_STAGE_OBSERVATIONS:-1591}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --help
fi

if [[ "${1:-}" == "--self-test" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

for required_file in "${PYTHON_SCRIPT}" "${OVERALL_SUMMARY_FILE}" "${LOCALIZED_STATIC_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file not found: %s\n' "${required_file}" >&2
    exit 2
  fi
done

SCRIPT_VERSION_RAW="$("${PYTHON_BIN}" "${PYTHON_SCRIPT}" --version)"
SCRIPT_VERSION="$(printf '%s' "${SCRIPT_VERSION_RAW}" | tr -d '\r' | awk '{$1=$1; print}')"
if [[ "${SCRIPT_VERSION}" != "${RUN_LABEL}" ]]; then
  printf 'ERROR: wrapper/Python version mismatch. Expected %s; observed %s.\n' \
    "${RUN_LABEL}" "${SCRIPT_VERSION}" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}" "$(dirname -- "${TABLE_OUTPUT}")" "${LOG_DIR}"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-${IMPLEMENTATION_VERSION}-${RUN_STAMP}-$$.log}"
PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PYTHON_SCRIPT_SHA256="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

ARGS=(
  --overall-summary-file "${OVERALL_SUMMARY_FILE}"
  --localized-static-file "${LOCALIZED_STATIC_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --table-output "${TABLE_OUTPUT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-overall-rows "${EXPECTED_OVERALL_ROWS}"
  --expected-localized-rows "${EXPECTED_LOCALIZED_ROWS}"
  --expected-treated-observations "${EXPECTED_TREATED_OBSERVATIONS}"
  --expected-first-stage-observations "${EXPECTED_FIRST_STAGE_OBSERVATIONS}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
)

if [[ "${OVERWRITE}" == "1" || "${1:-}" == "--overwrite" ]]; then
  ARGS+=(--overwrite)
  if [[ "${1:-}" == "--overwrite" ]]; then
    shift
  fi
fi

{
  echo "============================================================"
  echo "${RUN_LABEL}: Python velocity DiD table summary"
  echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                  ${PROJECT_ROOT}"
  echo "Python:                        ${PYTHON_VERSION}"
  echo "Python script:                 ${PYTHON_SCRIPT}"
  echo "Python script SHA256:          ${PYTHON_SCRIPT_SHA256}"
  echo "Whole-Python source:           ${OVERALL_SUMMARY_FILE}"
  echo "Detector-localized source:     ${LOCALIZED_STATIC_FILE}"
  echo "Output table:                  ${TABLE_OUTPUT}"
  echo "Output root:                   ${OUTPUT_DIR}"
  echo "Log file:                      ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${ARGS[@]}" "$@" 2>&1 | tee -a "${LOG_FILE}"

{
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Table:                         ${TABLE_OUTPUT}"
  echo "Summary:                       ${OUTPUT_DIR}/python_velocity_localized_did_summary.csv"
  echo "Checks:                        ${OUTPUT_DIR}/python_velocity_localized_did_reconciliation_checks.csv"
  echo "Metadata:                      ${OUTPUT_DIR}/python_velocity_localized_did_run_metadata.csv"
  echo "Log:                           ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
