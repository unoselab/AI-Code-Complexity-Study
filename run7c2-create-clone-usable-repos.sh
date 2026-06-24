#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7c2: Create usable JS/TS treatment repo list with event metadata
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run7c2_create_clone_usable_repos_${RUN_TS}.log}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-tmp_jsts_test/data/jsts_treatment_clone_status.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event.csv}"
FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_failed_repos.csv}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7c2: create usable JS/TS treatment repo list with event metadata" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Log file:             ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status file:    ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Panel file:           ${PANEL_FILE}" | tee -a "${LOG_FILE}"
echo "Output file:          ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Failed output file:   ${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Dataset source:       ${DATASET_SOURCE}" | tee -a "${LOG_FILE}"
echo "Top print:            ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CLONE_STATUS_FILE}" ]]; then
  echo "ERROR: clone status file not found: ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PANEL_FILE}" ]]; then
  echo "ERROR: panel file not found: ${PANEL_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/create_clone_usable_repos_with_event.py" ]]; then
  echo "ERROR: script not found: proc_scripts/create_clone_usable_repos_with_event.py" | tee -a "${LOG_FILE}"
  exit 1
fi

set +e
python proc_scripts/create_clone_usable_repos_with_event.py \
  --clone-status-file "${CLONE_STATUS_FILE}" \
  --panel-file "${PANEL_FILE}" \
  --output-file "${OUTPUT_FILE}" \
  --failed-output-file "${FAILED_OUTPUT_FILE}" \
  --dataset-source "${DATASET_SOURCE}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run7c2 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Output file: ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Failed output file: ${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

exit "${run_status}"
