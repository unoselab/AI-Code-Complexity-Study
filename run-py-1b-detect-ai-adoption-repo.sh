#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1b: Clone Python Cursor-adopting treatment repositories
# ============================================================
#
# This wrapper is adapted from the logic of run7b-detect-ai-adoption-repo.sh,
# but it does NOT call run7b-detect-ai-adoption-repo.sh.
#
# Design rule for the Python experiment:
#   - Reuse existing Python scripts.
#   - Do not depend on existing shell wrappers.
#   - Keep Python experiment file names explicit and separate.
#
# Main Python script reused here:
#   proc_scripts/clone_repos_v2.py
#
# Input:
#   repo_python/treatment_python_repos.csv
#     - Created by run-py-1a-count-repo.sh.
#     - Contains Python Cursor-adopting treatment repositories.
#     - Required column: repo_name.
#     - Expected language column: repo_primary_language.
#
# Clone output directory:
#   ../treatment-repos
#     - Repositories are cloned outside the code workspace.
#     - Full git history is required for later adoption-month and
#       monthly time-series analysis, so do NOT use shallow clone.
#
# Main output:
#   repo_python/treatment_python_clone_status.csv
#     - Candidate file merged with clone log.
#     - Contains repo metadata plus clone status, target_dir, and note.
#     - Later used by run-py-1c to create usable treatment repos
#       with event metadata.
#
# Backup output:
#   repo_python/treatment_python_clone_status_<timestamp>.csv
#
# Log outputs:
#   logs/run-py-1b_detect_ai_adoption_repo_<timestamp>.log
#   logs/run-py-1b_treatment_clone_log_<timestamp>.csv
#
# Typical usage:
#   Smoke test:
#     MAX_CLONES=5 bash run-py-1b-detect-ai-adoption-repo.sh
#
#   Full run:
#     MAX_CLONES=0 bash run-py-1b-detect-ai-adoption-repo.sh
# ============================================================

export GIT_TERMINAL_PROMPT=0

# ------------------------------------------------------------
# General logging
# ------------------------------------------------------------
LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1b_detect_ai_adoption_repo_${RUN_TS}.log}"

# ------------------------------------------------------------
# Python experiment naming convention
# ------------------------------------------------------------
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1b}"

# Input candidate file from run-py-1a.
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Primary clone-status output used by the next step.
CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
CLONE_STATUS_BACKUP="${CLONE_STATUS_BACKUP:-${TMP_DIR}/treatment_python_clone_status_${RUN_TS}.csv}"

# ------------------------------------------------------------
# Clone settings
# ------------------------------------------------------------
# Clone root is outside the source-code workspace:
#   ai_code_complexity_study_python/treatment-repos
CLONE_ROOT="${CLONE_ROOT:-../treatment-repos}"

# Use 0 for all repositories. Use a small number for smoke testing.
MAX_CLONES="${MAX_CLONES:-10}"

# Existing repository behavior:
#   skip = do not pull/update existing local clones
#   pull = pull latest changes in existing local clones
#
# For reproducibility, skip is safer.
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

# ------------------------------------------------------------
# Clone log naming
# ------------------------------------------------------------
CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-run-py-1b_treatment_clone_log}"
# CLONE_LOG_CSV="${TMP_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

# ------------------------------------------------------------
# Clone-status report settings
# ------------------------------------------------------------
CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV:-Python}"
CHECK_TOP_PRINT="${CHECK_TOP_PRINT:-80}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1b: clone Python Cursor-adopting treatment repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                  ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Main output dir:            ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:           ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Treatment repos file:       ${TREATMENT_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone root:                 ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Max clones:                 ${MAX_CLONES}" | tee -a "${LOG_FILE}"
echo "Existing action:            ${EXISTING_ACTION}" | tee -a "${LOG_FILE}"
echo "Clone log CSV:              ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
echo "Clone status file:          ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status backup:        ${CLONE_STATUS_BACKUP}" | tee -a "${LOG_FILE}"
echo "Check languages CSV:        ${CHECK_LANGUAGES_CSV}" | tee -a "${LOG_FILE}"
echo "Wrapper log:                ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

# ------------------------------------------------------------
# Validate required input and Python script
# ------------------------------------------------------------
if [[ ! -f "${TREATMENT_REPOS_FILE}" ]]; then
  echo "ERROR: treatment repo file not found: ${TREATMENT_REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1a-count-repo.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "proc_scripts/clone_repos_v2.py" ]]; then
  echo "ERROR: Python script not found: proc_scripts/clone_repos_v2.py" | tee -a "${LOG_FILE}"
  exit 1
fi

# ------------------------------------------------------------
# Print input candidate summary
# ------------------------------------------------------------
echo "** Python treatment candidate summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${TREATMENT_REPOS_FILE}")
df = pd.read_csv(path)

if "repo_name" not in df.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {path}")

print("Input file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

if "repo_primary_language" in df.columns:
    print()
    print("Primary language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().to_string())

print()
print("Top rows:")
print(df.head(20).to_string(index=False))
PY

# ------------------------------------------------------------
# Clone repositories using the reusable Python script
# ------------------------------------------------------------
# This is the key step copied from the logic of run7b, but without
# calling run7b itself.
#
# Important:
#   clone_repos_v2.py writes a timestamped clone log CSV.
#   The next inline Python block merges this log with the candidate file.
echo | tee -a "${LOG_FILE}"
echo "** Git-clone Python treatment repositories" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python proc_scripts/clone_repos_v2.py \
  --repos-file "${TREATMENT_REPOS_FILE}" \
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
  echo "ERROR: clone_repos_v2.py failed with exit code ${clone_status}" | tee -a "${LOG_FILE}"
  echo "See log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  exit "${clone_status}"
fi

if [[ ! -f "${CLONE_LOG_CSV}" ]]; then
  echo "ERROR: expected clone log CSV not found: ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
  exit 1
fi

# ------------------------------------------------------------
# Create clone-status file by merging candidate metadata and clone log
# ------------------------------------------------------------
# Output:
#   repo_python/treatment_python_clone_status.csv
#
# This file is the bridge between clone execution and the next
# event-metadata step.
echo | tee -a "${LOG_FILE}"
echo "** Create Python treatment clone-status file" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - "${TREATMENT_REPOS_FILE}" "${CLONE_LOG_CSV}" "${CHECK_LANGUAGES_CSV}" "${CLONE_STATUS_FILE}" "${CHECK_TOP_PRINT}" <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path

import pandas as pd

candidates_file = Path(sys.argv[1])
clone_log_file = Path(sys.argv[2])
languages_csv = sys.argv[3]
check_output_file = Path(sys.argv[4])
top_print = int(sys.argv[5])

candidates = pd.read_csv(candidates_file)
log = pd.read_csv(clone_log_file)

if "repo_name" not in candidates.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {candidates_file}")

if "repo_name" not in log.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {clone_log_file}")

candidates["repo_name"] = candidates["repo_name"].astype(str).str.strip()
log["repo_name"] = log["repo_name"].astype(str).str.strip()

df = candidates.merge(log, on="repo_name", how="left")

languages = [x.strip() for x in languages_csv.split(",") if x.strip()]
if languages and "repo_primary_language" in df.columns:
    report_df = df[df["repo_primary_language"].isin(languages)].copy()
else:
    report_df = df.copy()

usable_statuses = {"cloned", "skipped_existing", "updated_existing"}

print("Candidate rows:", len(candidates))
print("Clone log rows:", len(log))
print("Report rows:", len(report_df))
print("Unique report repos:", report_df["repo_name"].nunique())
print()

if "repo_primary_language" in report_df.columns:
    print("Primary language counts:")
    print(report_df["repo_primary_language"].fillna("(missing)").value_counts().to_string())
    print()

print("Clone status counts:")
print(report_df["status"].fillna("(missing)").value_counts().to_string())
print()

usable = report_df["status"].isin(usable_statuses).sum()
failed = report_df["status"].eq("failed").sum()
missing = report_df["status"].isna().sum()

print("Usable repos:", usable)
print("Failed repos:", failed)
print("Missing log rows:", missing)
print()

check_output_file.parent.mkdir(parents=True, exist_ok=True)
report_df.to_csv(check_output_file, index=False)
print("Saved merged clone status:", check_output_file)
print()

cols = [
    "repo_name",
    "repo_primary_language",
    "event_month",
    "pre_panel_months",
    "post_panel_months",
    "balanced_window",
    "status",
    "target_dir",
    "note",
]
cols = [c for c in cols if c in report_df.columns]

print(f"Top {top_print} clone-status rows:")
if len(report_df) == 0:
    print("(No rows.)")
else:
    print(report_df[cols].head(top_print).to_string(index=False))
PY

cp "${CLONE_STATUS_FILE}" "${CLONE_STATUS_BACKUP}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

echo "Command: wc -l ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
wc -l "${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Command: head ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
head "${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1b completed successfully." | tee -a "${LOG_FILE}"
echo "Clone status file:" | tee -a "${LOG_FILE}"
echo "  ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone status backup:" | tee -a "${LOG_FILE}"
echo "  ${CLONE_STATUS_BACKUP}" | tee -a "${LOG_FILE}"
echo "Treatment clone root:" | tee -a "${LOG_FILE}"
echo "  ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
