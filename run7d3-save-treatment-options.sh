#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7d3: Save JS/TS treatment sample options
# ============================================================
# This wrapper calls proc_scripts/save_treatment_options.py.
#
# Input:
#   tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv
#
# Outputs:
#   tmp_jsts_test/data/jsts_treatment_sample_main_<N>.csv
#   tmp_jsts_test/data/jsts_treatment_sample_exact_match_<N>.csv
#   tmp_jsts_test/data/jsts_treatment_sample_within1_month_<N>.csv
#   tmp_jsts_test/data/jsts_treatment_sample_diagnostic_<N>.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run7d3_save_treatment_options_${RUN_TS}.log}"

CHECK_FILE="${CHECK_FILE:-tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data}"
PREFIX="${PREFIX:-jsts_treatment_sample}"
WITHIN_MONTH_TOLERANCE="${WITHIN_MONTH_TOLERANCE:-1}"
TOP_PRINT="${TOP_PRINT:-50}"

SCRIPT_FILE="proc_scripts/save_treatment_options.py"

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7d3: save JS/TS treatment sample options" | tee -a "${LOG_FILE}"
echo "Timestamp:                 ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Check file:                ${CHECK_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir:                ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Output prefix:             ${PREFIX}" | tee -a "${LOG_FILE}"
echo "Within-month tolerance:    ${WITHIN_MONTH_TOLERANCE}" | tee -a "${LOG_FILE}"
echo "Top print:                 ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "Script file:               ${SCRIPT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:                  ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CHECK_FILE}" ]]; then
  echo "ERROR: check file not found: ${CHECK_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run7d1/run7d2 first to create adoption_month_check.csv." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${SCRIPT_FILE}" ]]; then
  echo "ERROR: script file not found: ${SCRIPT_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

set +e
python "${SCRIPT_FILE}" \
  --check-file "${CHECK_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --prefix "${PREFIX}" \
  --within-month-tolerance "${WITHIN_MONTH_TOLERANCE}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run7d3 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

exit "${run_status}"
