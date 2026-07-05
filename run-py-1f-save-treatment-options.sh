#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1f: Save Python treatment sample options
# ============================================================
#
# Input:
#   repo_python/treatment_python_did/adoption_month_check.csv
#
# Outputs:
#   repo_python/treatment_python_sample_main_<N>.csv
#   repo_python/treatment_python_sample_exact_match_<N>.csv
#   repo_python/treatment_python_sample_within1_month_<N>.csv
#   repo_python/treatment_python_sample_diagnostic_<N>.csv
#
# Expected current Python result:
#   main       = 118
#   exact      = 118
#   within1    = 118
#   diagnostic = 0
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1f_save_treatment_options_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/save_treatment_options.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
CHECK_FILE="${CHECK_FILE:-${OUTPUT_DIR}/treatment_python_did/adoption_month_check.csv}"
PREFIX="${PREFIX:-treatment_python_sample}"
TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1f: save Python treatment sample options" | tee -a "${LOG_FILE}"
echo "Timestamp:        ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:    ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Check file:       ${CHECK_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir:       ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Prefix:           ${PREFIX}" | tee -a "${LOG_FILE}"
echo "Top print:        ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "Log file:         ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${CHECK_FILE}" ]]; then
  echo "ERROR: adoption-month check file not found: ${CHECK_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1e-analyze-treatment-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Save treatment sample options" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python "${PY_SCRIPT}" \
  --check-file "${CHECK_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --prefix "${PREFIX}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: treatment option saving failed with exit code ${run_status}" | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in "${OUTPUT_DIR}"/"${PREFIX}"_*.csv; do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1f completed successfully." | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run7d3-save-treatment-options.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Design rule for the Python experiment:
#   - Reuse the treatment-option logic.
#   - Put the reusable logic in proc_scripts/save_treatment_options.py.
#   - Keep Python experiment paths and filenames explicit.
