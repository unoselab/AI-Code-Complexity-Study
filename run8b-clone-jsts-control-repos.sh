#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run8b: Clone matched JS/TS control repositories
# ============================================================
# This script clones only the matched control repositories extracted
# by run8a. It does not clone all control candidates.
# ============================================================

export GIT_TERMINAL_PROMPT=0

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8b_clone_jsts_control_repos_${RUN_TS}.log}"

CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv}"
CLONE_ROOT="${CLONE_ROOT:-../ai_code_complexity_study_jsts_control_repo_dataset}"

MAX_CLONES="${MAX_CLONES:-10}"
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-run8b_jsts_control_clone_log}"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"
CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-tmp_jsts_test/data/jsts_control_clone_status_main_398.csv}"
CHECK_OUTPUT_BACKUP="${CHECK_OUTPUT_BACKUP:-${CHECK_OUTPUT_FILE%.csv}_${RUN_TS}.csv}"

mkdir -p "${LOG_DIR}"
mkdir -p "$(dirname "${CHECK_OUTPUT_FILE}")"

echo "============================================================" | tee "${LOG_FILE}"
echo "run8b: clone matched JS/TS control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:             ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Control repos file:    ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone root:            ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Max clones:            ${MAX_CLONES}" | tee -a "${LOG_FILE}"
echo "Existing action:       ${EXISTING_ACTION}" | tee -a "${LOG_FILE}"
echo "Clone log CSV:         ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
echo "Check output file:     ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Check output backup:   ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${CONTROL_REPOS_FILE}" ]]; then
  echo "ERROR: control repos file not found: ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run8a-extract-jsts-control-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/clone_repos_v2.py" ]]; then
  echo "ERROR: script not found: proc_scripts/clone_repos_v2.py" | tee -a "${LOG_FILE}"
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
python proc_scripts/clone_repos_v2.py \
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
  echo | tee -a "${LOG_FILE}"
  echo "run8b failed during cloning with exit code ${clone_status}" | tee -a "${LOG_FILE}"
  echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${clone_status}"
fi

if [[ ! -f "${CLONE_LOG_CSV}" ]]; then
  echo "ERROR: expected clone log CSV not found: ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
  exit 1
fi

cp "${CLONE_LOG_CSV}" "${CHECK_OUTPUT_FILE}"
cp "${CLONE_LOG_CSV}" "${CHECK_OUTPUT_BACKUP}"

echo | tee -a "${LOG_FILE}"
echo "** Clone status summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

log_path = Path("${CHECK_OUTPUT_FILE}")
df = pd.read_csv(log_path)

print("Clone status file:", log_path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique() if "repo_name" in df.columns else "(repo_name column missing)")
print()

if "status" in df.columns:
    print("Status counts:")
    print(df["status"].fillna("(missing)").value_counts().to_string())
    print()

    failed = df[df["status"].eq("failed")].copy()
    if len(failed) > 0:
        print("Failed repos:")
        cols = ["repo_name", "status", "target_dir", "note"]
        cols = [c for c in cols if c in failed.columns]
        print(failed[cols].to_string(index=False))
PY

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run8b completed successfully." | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status file: ${CHECK_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status backup: ${CHECK_OUTPUT_BACKUP}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
