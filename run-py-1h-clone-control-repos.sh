#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1h: Clone matched control repositories
# ============================================================
#
# This wrapper is adapted from the logic of run8b-clone-jsts-control-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Input:
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#
# Main output:
#   repo_python/run-py-1h/python_control_clone_status_main_118.csv
#
# Extra output:
#   repo_python/tmp/run-py-1h/python_control_clone_status_main_118_<timestamp>.csv
#
# Clone root:
#   ../control-repos
#
# Typical usage:
#   Smoke test:
#     MAX_CLONES=5 bash run-py-1h-clone-control-repos.sh
#
#   Full run:
#     MAX_CLONES=0 bash run-py-1h-clone-control-repos.sh
# ============================================================

export GIT_TERMINAL_PROMPT=0

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_clone_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/clone_repos_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

SAMPLE_NAME="${SAMPLE_NAME:-main_118}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${OUTPUT_BASE_DIR}/run-py-1g/python_control_repos_to_clone_${SAMPLE_NAME}.csv}"

CLONE_ROOT="${CLONE_ROOT:-../control-repos}"

MAX_CLONES="${MAX_CLONES:-10}"
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-${RUN_PREFIX}_control_clone_log}"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_status_${SAMPLE_NAME}.csv}"
CHECK_OUTPUT_BACKUP="${CHECK_OUTPUT_BACKUP:-${TMP_DIR}/python_control_clone_status_${SAMPLE_NAME}_${RUN_TS}.csv}"
 
mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1h: clone matched control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:             ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:           ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:            ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:         ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Control repos file:    ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Sample name:           ${SAMPLE_NAME}" | tee -a "${LOG_FILE}"
echo "Main output dir:       ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:      ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Clone root:            ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Max clones:            ${MAX_CLONES}" | tee -a "${LOG_FILE}"
echo "Existing action:       ${EXISTING_ACTION}" | tee -a "${LOG_FILE}"
echo "Clone log CSV:         ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
echo "Check output file:     ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Check output backup:   ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
echo "Log file:              ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CONTROL_REPOS_FILE}" ]]; then
  echo "ERROR: control repos file not found: ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1g-extract-control-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Control repo list summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${CONTROL_REPOS_FILE}")
df = pd.read_csv(path)

if "repo_name" not in df.columns:
    raise SystemExit("ERROR: control repo file must contain repo_name column.")

print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())
print()
print(df.head(20).to_string(index=False))
PY

echo | tee -a "${LOG_FILE}"
echo "** Clone matched control repositories" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python "${PY_SCRIPT}" \
  --repos-file "${CONTROL_REPOS_FILE}" \
  --repo-column repo_name \
  --clone-root "${CLONE_ROOT}" \
  --logs-dir "${LOG_DIR}" \
  --log-prefix "${CLONE_LOG_PREFIX}" \
  --timestamp "${RUN_TS}" \
  --max-repos "${MAX_CLONES}" \
  --existing-action "${EXISTING_ACTION}" \
  2>&1 | tee -a "${LOG_FILE}"

clone_status=${PIPESTATUS[0]}
set -e

if [[ "${clone_status}" -ne 0 ]]; then
  echo "ERROR: control cloning failed with exit code ${clone_status}" | tee -a "${LOG_FILE}"
  exit "${clone_status}"
fi

if [[ ! -f "${CLONE_LOG_CSV}" ]]; then
  echo "ERROR: expected clone log CSV not found: ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
  exit 1
fi

cp "${CLONE_LOG_CSV}" "${CHECK_OUTPUT_FILE}"
cp "${CLONE_LOG_CSV}" "${CHECK_OUTPUT_BACKUP}"

echo | tee -a "${LOG_FILE}"
echo "** Control clone status summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${CHECK_OUTPUT_FILE}")
df = pd.read_csv(path)

print("Clone status file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())
print()

print("Status counts:")
print(df["status"].fillna("(missing)").value_counts().to_string())
print()

usable_statuses = {"cloned", "skipped_existing", "updated_existing"}
print("Usable repos:", int(df["status"].isin(usable_statuses).sum()))
print("Failed repos:", int(df["status"].eq("failed").sum()))
print()

failed = df[df["status"].eq("failed")].copy()
if len(failed) > 0:
    print("Failed repos:")
    cols = ["repo_name", "status", "target_dir", "note"]
    print(failed[cols].to_string(index=False))
PY

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

wc -l "${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
head "${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1h completed successfully." | tee -a "${LOG_FILE}"
echo "Clone status file:   ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status backup: ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
echo "Main output dir:     ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:    ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Control clone root:  ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
