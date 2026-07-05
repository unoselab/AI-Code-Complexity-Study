#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1c: Create usable Python treatment repo list with event metadata
# ============================================================
#
# Main Python script reused here:
#   proc_scripts/create_clone_usable_repos_with_event.py
#
# Inputs:
#   repo_python/treatment_python_clone_status.csv
#     - Created by run-py-1b.
#     - Contains all Python treatment candidates plus clone status.
#     - Usable statuses are cloned, skipped_existing, updated_existing.
#
#   data_baseline_backup/panel_event_monthly.csv
#     - Original paper-replication panel.
#     - Used to attach event_month and event-window metadata.
#
# Outputs:
#   repo_python/treatment_python_clone_usable_repos_with_event.csv
#     - Usable cloned Python treatment repos with event metadata.
#
#   repo_python/treatment_python_clone_failed_repos.csv
#     - Failed Python treatment repos.
#
# Typical usage:
#   bash run-py-1c-create-treatment-usable-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1c_create_treatment_usable_repos_${RUN_TS}.log}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event.csv}"
FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_failed_repos.csv}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
TOP_PRINT="${TOP_PRINT:-50}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_clone_usable_repos_with_event.py}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1c: create usable Python treatment repo list with event metadata" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:        ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Clone status file:    ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Panel file:           ${PANEL_FILE}" | tee -a "${LOG_FILE}"
echo "Output file:          ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Failed output file:   ${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Dataset source:       ${DATASET_SOURCE}" | tee -a "${LOG_FILE}"
echo "Top print:            ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "Log file:             ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CLONE_STATUS_FILE}" ]]; then
  echo "ERROR: clone status file not found: ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1b-detect-ai-adoption-repo.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PANEL_FILE}" ]]; then
  echo "ERROR: panel file not found: ${PANEL_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Input clone-status summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${CLONE_STATUS_FILE}")
df = pd.read_csv(path)

print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

print()
print("Status counts:")
print(df["status"].fillna("(missing)").value_counts(dropna=False).to_string())

if "repo_primary_language" in df.columns:
    print()
    print("Primary language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().to_string())
PY

echo | tee -a "${LOG_FILE}"
echo "** Create usable Python treatment repo list with event metadata" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python "${PY_SCRIPT}" \
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
echo "run-py-1c finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Output file: ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Failed output file: ${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

echo "Command: wc -l ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
wc -l "${OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Command: wc -l ${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
wc -l "${FAILED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Command: head ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
head "${OUTPUT_FILE}" | tee -a "${LOG_FILE}"

exit "${run_status}"

# This wrapper is adapted from the logic of run7c2-create-clone-usable-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Design rule for the Python experiment:
#   - Reuse existing Python scripts.
#   - Do not depend on existing shell wrappers.
#   - Keep Python experiment file names explicit and separate.
