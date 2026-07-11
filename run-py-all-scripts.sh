#!/bin/bash
# Consolidated execution script generated on Sat Jul 11 02:28:01 PM CDT 2026

###############################################################################
# FILE: run-py-1a-count-repo.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1a: Count Python Cursor-adopting treatment repositories
# ============================================================
#
# Goal:
#   Prepare the first Python treatment-repository input file for
#   reproducing the paper's language-specific Appendix result.
#
# Main output policy:
#   repo_python/
#     - Keep only the analysis input needed by later pipeline steps.
#
# Extra output policy:
#   repo_python/tmp/
#     - Keep diagnostic subsets, logs, and verification artifacts.
#
# Main output:
#   repo_python/treatment_python_repos.csv
#
# Extra outputs:
#   repo_python/tmp/treatment_python_repos_bw6.csv
#   repo_python/tmp/run-py-1a_count_repo_<timestamp>.log
#
# Important:
#   This step reads the frozen baseline data and does not require Git cloning
#   or SonarQube scanning. Expensive cached artifacts under bak/repo_python
#   are not needed for run-py-1a and will be reused by later wrappers.
#
# Typical usage:
#   bash run-py-1a-count-repo.sh
#
# Optional overrides:
#   MIN_BALANCED_WINDOW=5 bash run-py-1a-count-repo.sh
#   OUTPUT_DIR=repo_python_test bash run-py-1a-count-repo.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"

# ------------------------------------------------------------
# Inputs and executable
# ------------------------------------------------------------
DATA_DIR="${DATA_DIR:-data_baseline_backup}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/count_repo_lang.py}"
PYTHON_BIN="${PYTHON_BIN:-python}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
GROUP_NAME="${GROUP_NAME:-Python}"
LANGUAGE="${LANGUAGE:-Python}"

# ------------------------------------------------------------
# Output directories
# ------------------------------------------------------------
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp}"

MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"
TOP_PRINT="${TOP_PRINT:-30}"

# Keep the main pipeline input in repo_python/.
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Keep the balanced-window diagnostic subset in repo_python/tmp/.
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-${TMP_DIR}/treatment_python_repos_bw${MIN_BALANCED_WINDOW}.csv}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1a_count_repo_${RUN_TS}.log}"

PANEL_FILE="${PANEL_FILE:-${DATA_DIR}/panel_event_monthly.csv}"
REPOS_FILE="${REPOS_FILE:-${DATA_DIR}/repos.csv}"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}"

# Remove stale files so a failed run cannot be mistaken for a fresh result.
rm -f "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"

{
  echo "============================================================"
  echo "run-py-1a: Count Python Cursor-adopting treatment repositories"
  echo "Started:                    $(date)"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Baseline panel:             ${PANEL_FILE}"
  echo "Repository metadata:        ${REPOS_FILE}"
  echo "Dataset source:             ${DATASET_SOURCE}"
  echo "Language:                   ${LANGUAGE}"
  echo "Group name:                 ${GROUP_NAME}"
  echo "Main output directory:      ${OUTPUT_DIR}"
  echo "Extra output directory:     ${TMP_DIR}"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Balanced-window diagnostic: ${WINDOW_OUTPUT_FILE}"
  echo "Minimum balanced window:    ${MIN_BALANCED_WINDOW}"
  echo "Top print:                  ${TOP_PRINT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${PANEL_FILE}" ]]; then
    echo "ERROR: Baseline panel not found: ${PANEL_FILE}"
    exit 1
  fi

  if [[ ! -f "${REPOS_FILE}" ]]; then
    echo "ERROR: Repository metadata not found: ${REPOS_FILE}"
    exit 1
  fi

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --data-dir "${DATA_DIR}" \
    --panel-file "${PANEL_FILE}" \
    --repos-file "${REPOS_FILE}" \
    --dataset-source "${DATASET_SOURCE}" \
    --language "${LANGUAGE}" \
    --group-name "${GROUP_NAME}" \
    --output-file "${OUTPUT_FILE}" \
    --window-output-file "${WINDOW_OUTPUT_FILE}" \
    --min-balanced-window "${MIN_BALANCED_WINDOW}" \
    --top-print "${TOP_PRINT}"

  for expected_file in "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}"
      exit 1
    fi
  done

  MAIN_ROWS=$(( $(wc -l < "${OUTPUT_FILE}") - 1 ))
  WINDOW_ROWS=$(( $(wc -l < "${WINDOW_OUTPUT_FILE}") - 1 ))

  echo
  echo "============================================================"
  echo "run-py-1a output verification"
  echo "============================================================"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Main repository rows:       ${MAIN_ROWS}"
  echo "Diagnostic output:          ${WINDOW_OUTPUT_FILE}"
  echo "Diagnostic repository rows: ${WINDOW_ROWS}"
  echo
  echo "Main output preview:"
  head "${OUTPUT_FILE}"
  echo
  echo "Diagnostic output preview:"
  head "${WINDOW_OUTPUT_FILE}"
  echo
  echo "============================================================"
  echo "run-py-1a completed successfully."
  echo "Completed:                  $(date)"
  echo "Main pipeline input:        ${OUTPUT_FILE}"
  echo "Extra diagnostic output:    ${WINDOW_OUTPUT_FILE}"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
# 
# This wrapper is the Python version of run7a-count-repo.sh.
# It reuses the original selection logic without calling the old wrapper.


###############################################################################
# FILE: run-py-1b-detect-ai-adoption-repo.sh
###############################################################################

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


###############################################################################
# FILE: run-py-1c-create-treatment-usable-repos.sh
###############################################################################

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
#   repo_python/tmp/run-py-1c/treatment_python_clone_failed_repos.csv
#     - Failed Python treatment repos.
#
# Typical usage:
#   bash run-py-1c-create-treatment-usable-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1c_create_treatment_usable_repos_${RUN_TS}.log}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1c}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event.csv}"
# FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_failed_repos.csv}"
FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-${TMP_DIR}/treatment_python_clone_failed_repos.csv}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
TOP_PRINT="${TOP_PRINT:-50}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_clone_usable_repos_with_event.py}"

# mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1c: create usable Python treatment repo list with event metadata" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:        ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Clone status file:    ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Panel file:           ${PANEL_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:      ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:     ${TMP_DIR}" | tee -a "${LOG_FILE}"
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


###############################################################################
# FILE: run-py-1d-split-valid-event-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1d: Split usable Python treatment repos by event_month
# ============================================================
# 
# Usage:
#   bash run-py-1d-split-valid-event-repos.sh
# 
# Input:
#   repo_python/treatment_python_clone_usable_repos_with_event.csv
#     - Created by run-py-1c.
#     - Contains clone-usable Python treatment repositories.
#     - Contains event metadata merged from panel_event_monthly.csv.
#
# Outputs:
#   repo_python/treatment_python_clone_usable_repos_with_event_valid.csv
#     - Repositories with non-missing event_month.
#     - This file should be used as the next treatment input for
#       repository-history/adoption-month analysis.
#
#   repo_python/tmp/run-py-1d/treatment_python_clone_usable_missing_event_month.csv
#     - Diagnostic file.
#     - Repositories cloned successfully but missing event_month in
#       the baseline panel.
#
# Expected current result:
#   Input rows: 123
#   Valid rows with event_month: 118
#   Missing event_month rows: 5
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1d_split_valid_event_repos_${RUN_TS}.log}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1d}"

INPUT_FILE="${INPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event.csv}"
VALID_OUTPUT_FILE="${VALID_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event_valid.csv}"
MISSING_OUTPUT_FILE="${MISSING_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_missing_event_month.csv}"
MISSING_OUTPUT_FILE="${MISSING_OUTPUT_FILE:-${TMP_DIR}/treatment_python_clone_usable_missing_event_month.csv}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1d: split usable Python treatment repos by event_month" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Input file:           ${INPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:      ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:     ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Valid output file:    ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Missing output file:  ${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:             ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "ERROR: input file not found: ${INPUT_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1c-create-treatment-usable-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

set +e
python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

input_path = Path("${INPUT_FILE}")
valid_output_path = Path("${VALID_OUTPUT_FILE}")
missing_output_path = Path("${MISSING_OUTPUT_FILE}")

# Read the usable cloned Python treatment repository file.
df = pd.read_csv(input_path)

# event_month is required for event-study and DiD organization.
# Repositories without event_month cannot be used in the next
# treatment-history analysis step.
if "event_month" not in df.columns:
    raise SystemExit("ERROR: input file must contain event_month column.")

if "repo_name" not in df.columns:
    raise SystemExit("ERROR: input file must contain repo_name column.")

# Split rows:
#   valid   = usable cloned repos with event_month
#   missing = usable cloned repos without event_month
valid = df[df["event_month"].notna()].copy()
missing = df[df["event_month"].isna()].copy()

valid_output_path.parent.mkdir(parents=True, exist_ok=True)
missing_output_path.parent.mkdir(parents=True, exist_ok=True)

valid.to_csv(valid_output_path, index=False)
missing.to_csv(missing_output_path, index=False)

print("Input file:", input_path)
print("Input rows:", len(df))
print("Unique input repos:", df["repo_name"].nunique())
print()
print("Valid rows with event_month:", len(valid))
print("Unique valid repos:", valid["repo_name"].nunique())
print()
print("Missing event_month rows:", len(missing))
print("Unique missing-event repos:", missing["repo_name"].nunique())
print()

print("Saved valid file:", valid_output_path)
print("Saved missing-event file:", missing_output_path)
print()

print("Valid language counts:")
if "repo_primary_language" in valid.columns:
    print(valid["repo_primary_language"].fillna("(missing)").value_counts().to_string())
else:
    print("(repo_primary_language column not found)")
print()

print("Missing event_month language counts:")
if "repo_primary_language" in missing.columns:
    print(missing["repo_primary_language"].fillna("(missing)").value_counts().to_string())
else:
    print("(repo_primary_language column not found)")
print()

print("Missing event_month repos:")
cols = [
    "repo_name",
    "repo_primary_language",
    "status",
    "target_dir",
    "panel_first_month",
    "panel_latest_month",
    "balanced_window",
]
cols = [c for c in cols if c in missing.columns]

if len(missing) == 0:
    print("(No missing event_month repos.)")
else:
    print(missing[cols].to_string(index=False))
PY

run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1d finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Valid output file: ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Missing output file: ${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

if [[ "${run_status}" -ne 0 ]]; then
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

echo "Command: wc -l ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
wc -l "${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Command: wc -l ${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
wc -l "${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Command: head ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
head "${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

exit "${run_status}"

#
# This wrapper is adapted from the logic of run7c3-split-valid-event-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Design rule for the Python experiment:
#   - Reuse simple logic from existing wrappers.
#   - Do not depend on existing shell wrappers.
#   - Keep Python experiment file names explicit and separate.


###############################################################################
# FILE: run-py-1e-analyze-treatment-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1e: Analyze Python treatment repos and validate adoption month
# ============================================================
#
# Main Python scripts reused here:
#   1. proc_scripts/analyze_repos_v2.py
#      - Analyzes cloned git repositories.
#      - Produces monthly repository/contributor time series.
#      - Detects Cursor-related commits.
#      - Creates ai_adoption_dates.csv from earliest Cursor-related commit.
#
#   2. proc_scripts/check_time_of_event_and_adoption.py
#      - Compares baseline event_month with git-detected adoption_month.
#      - Produces adoption_month_check.csv.
#
#   3. proc_scripts/check_cache_control_repos.py
#      - Generic cache checker.
#      - Despite the file name, it only checks whether requested repo_name
#        values are already covered by existing analysis outputs.
#
# Cache behavior:
#   1. If output files already cover all requested repos, skip git analysis.
#   2. If output files exist but some repos are missing, analyze only missing repos.
#   3. Merge missing-repo outputs into the main output directory.
#   4. Use FORCE_RERUN=true to ignore cache.
#
# Smoke test:
#   MAX_REPOS=5 NUM_PROCESSES=1 bash run-py-1e-analyze-treatment-repos.sh
#
# Full run:
#   MAX_REPOS=0 NUM_PROCESSES=2 bash run-py-1e-analyze-treatment-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1e_analyze_treatment_repos_${RUN_TS}.log}"

PY_ANALYZER="${PY_ANALYZER:-proc_scripts/analyze_repos_v2.py}"
PY_ADOPTION_CHECK="${PY_ADOPTION_CHECK:-proc_scripts/check_time_of_event_and_adoption.py}"
CACHE_CHECK_SCRIPT="${CACHE_CHECK_SCRIPT:-proc_scripts/check_cache_control_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
TMP_BASE_DIR="${TMP_BASE_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1e}"

REPOS_FILE="${REPOS_FILE:-${OUTPUT_BASE_DIR}/treatment_python_clone_usable_repos_with_event_valid.csv}"
CLONE_DIR="${CLONE_DIR:-../treatment-repos}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"

# Default is smoke test. Use MAX_REPOS=0 for full run.
MAX_REPOS="${MAX_REPOS:-5}"

# Fixed output directories:
#   - Full-run main outputs use repo_python/treatment_python_did
#   - Smoke-test outputs use repo_python/tmp/run-py-1e/smoke/output
#   - Cache, manifest, missing-repo, and incremental files use
#     repo_python/tmp/run-py-1e
#
# This is important because timestamped smoke directories cannot use cache.
FULL_OUTPUT_DIR="${FULL_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did}"
# SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did_smoke}"
SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${TMP_BASE_DIR}/smoke/output}"


if [[ "${MAX_REPOS}" == "0" ]]; then
  OUTPUT_DIR="${OUTPUT_DIR:-${FULL_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_BASE_DIR}/full}"
else
  OUTPUT_DIR="${OUTPUT_DIR:-${SMOKE_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_BASE_DIR}/smoke}"
fi

REQUIRE_EVENT_MONTH="${REQUIRE_EVENT_MONTH:-true}"
SKIP_HISTORY_ANALYSIS="${SKIP_HISTORY_ANALYSIS:-false}"
SKIP_ADOPTION_CHECK="${SKIP_ADOPTION_CHECK:-false}"

SKIP_IF_COMPLETE="${SKIP_IF_COMPLETE:-true}"
INCREMENTAL_IF_PARTIAL="${INCREMENTAL_IF_PARTIAL:-true}"
FORCE_RERUN="${FORCE_RERUN:-false}"

REPO_TS_FILE="${OUTPUT_DIR}/ts_repos_${AGGREGATION}ly.csv"
CONTRIB_TS_FILE="${OUTPUT_DIR}/ts_contributors_${AGGREGATION}ly.csv"
CURSOR_COMMITS_FILE="${OUTPUT_DIR}/cursor_commits.csv"
ADOPTION_FILE="${ADOPTION_FILE:-${OUTPUT_DIR}/ai_adoption_dates.csv}"
ADOPTION_MATCH_FILE="${ADOPTION_MATCH_FILE:-${OUTPUT_DIR}/adoption_month_check.csv}"

# MANIFEST_FILE="${OUTPUT_DIR}/run-py-1e_analyzed_repos_manifest.csv"
MANIFEST_FILE="${EXTRA_DIR}/run-py-1e_analyzed_repos_manifest.csv"

# SMOKE_REPOS_FILE="${OUTPUT_DIR}/treatment_python_repos_smoke_max${MAX_REPOS}.csv"
# MISSING_REPOS_FILE="${OUTPUT_DIR}/run-py-1e_missing_repos_${RUN_TS}.csv"
# TMP_OUTPUT_DIR="${OUTPUT_DIR}/_incremental_${RUN_TS}"
SMOKE_REPOS_FILE="${EXTRA_DIR}/treatment_python_repos_smoke_max${MAX_REPOS}.csv"
MISSING_REPOS_FILE="${EXTRA_DIR}/run-py-1e_missing_repos_${RUN_TS}.csv"
TMP_OUTPUT_DIR="${EXTRA_DIR}/incremental_${RUN_TS}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${EXTRA_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1e: analyze Python treatment repos and validate adoption month" | tee -a "${LOG_FILE}"
echo "Timestamp:                 ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python analyzer:           ${PY_ANALYZER}" | tee -a "${LOG_FILE}"
echo "Adoption check script:     ${PY_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
echo "Cache check script:        ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:                ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:                 ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Main output dir:           ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:          ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:               ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:             ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:                 ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Require event_month:       ${REQUIRE_EVENT_MONTH}" | tee -a "${LOG_FILE}"
echo "Skip history analysis:     ${SKIP_HISTORY_ANALYSIS}" | tee -a "${LOG_FILE}"
echo "Skip adoption check:       ${SKIP_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
echo "Skip if complete:          ${SKIP_IF_COMPLETE}" | tee -a "${LOG_FILE}"
echo "Incremental if partial:    ${INCREMENTAL_IF_PARTIAL}" | tee -a "${LOG_FILE}"
echo "Force rerun:               ${FORCE_RERUN}" | tee -a "${LOG_FILE}"
echo "Adoption file:             ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption match file:       ${ADOPTION_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Manifest file:             ${MANIFEST_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:                  ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${REPOS_FILE}" ]]; then
  echo "ERROR: repos file not found: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1d-split-valid-event-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1b-detect-ai-adoption-repo.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PY_ANALYZER}" ]]; then
  echo "ERROR: Python analyzer not found: ${PY_ANALYZER}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ "${SKIP_ADOPTION_CHECK}" != "true" && ! -f "${PY_ADOPTION_CHECK}" ]]; then
  echo "ERROR: adoption check script not found: ${PY_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${CACHE_CHECK_SCRIPT}" ]]; then
  echo "ERROR: cache check script not found: ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Step 0: Validate Python treatment repo input" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
from pathlib import Path
import pandas as pd

path = Path("${REPOS_FILE}")
require_event_month = "${REQUIRE_EVENT_MONTH}".lower() == "true"

df = pd.read_csv(path)

print("Repos file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique() if "repo_name" in df.columns else "(repo_name column missing)")
print("Columns:", ", ".join(df.columns.tolist()))
print()

if "repo_name" not in df.columns:
    raise SystemExit("ERROR: repos file must contain repo_name column.")

if "repo_primary_language" in df.columns:
    print("Language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().to_string())
    print()

if "status" in df.columns:
    print("Clone status counts:")
    print(df["status"].fillna("(missing)").value_counts().to_string())
    print()

if "event_month" in df.columns:
    missing_event = int(df["event_month"].isna().sum())
    print("Rows with event_month:", int(df["event_month"].notna().sum()))
    print("Rows missing event_month:", missing_event)
    print()

    if require_event_month and missing_event > 0:
        raise SystemExit(
            f"ERROR: event_month is required, but {missing_event} rows are missing it."
        )
else:
    print("event_month column: missing")
    print()
    if require_event_month:
        raise SystemExit("ERROR: event_month column is required but missing.")

if len(df) == 0:
    raise SystemExit("ERROR: repos file has zero rows.")
PY

# ------------------------------------------------------------
# Step 0b: Build requested repos file for this run.
# Full run:
#   use all repos from REPOS_FILE.
# Smoke run:
#   use first MAX_REPOS rows and write to a fixed smoke file so cache works.
# ------------------------------------------------------------
REQUESTED_REPOS_FILE="${REPOS_FILE}"

if [[ "${MAX_REPOS}" != "0" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 0b: Create or refresh fixed smoke-test repo file" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

input_path = Path("${REPOS_FILE}")
output_path = Path("${SMOKE_REPOS_FILE}")
max_repos = int("${MAX_REPOS}")

df = pd.read_csv(input_path)
smoke = df.head(max_repos).copy()

output_path.parent.mkdir(parents=True, exist_ok=True)
smoke.to_csv(output_path, index=False)

print("Input repos:", len(df))
print("Smoke repos:", len(smoke))
print("Saved smoke repos file:", output_path)
print()

cols = ["repo_name", "repo_primary_language", "event_month"]
cols = [c for c in cols if c in smoke.columns]
print(smoke[cols].to_string(index=False))
PY

  REQUESTED_REPOS_FILE="${SMOKE_REPOS_FILE}"
fi

RUN_REPOS_FILE="${REQUESTED_REPOS_FILE}"
RUN_OUTPUT_DIR="${OUTPUT_DIR}"
CACHE_STATUS="run_full"

# ------------------------------------------------------------
# Step 1: Cache check.
# ------------------------------------------------------------
if [[ "${SKIP_HISTORY_ANALYSIS}" != "true" && "${FORCE_RERUN}" != "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 1: Cache check for existing repository analysis outputs" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  # CACHE_REPORT="${OUTPUT_DIR}/run-py-1e_cache_check_${RUN_TS}.txt"
  CACHE_REPORT="${EXTRA_DIR}/run-py-1e_cache_check_${RUN_TS}.txt"

  python "${CACHE_CHECK_SCRIPT}" \
    "${REQUESTED_REPOS_FILE}" \
    "${REPO_TS_FILE}" \
    "${CONTRIB_TS_FILE}" \
    "${CURSOR_COMMITS_FILE}" \
    "${ADOPTION_FILE}" \
    "${MANIFEST_FILE}" \
    "${MISSING_REPOS_FILE}" \
    > "${CACHE_REPORT}"

  cat "${CACHE_REPORT}" | tee -a "${LOG_FILE}"

  CACHE_STATUS="$(grep '^CACHE_STATUS=' "${CACHE_REPORT}" | head -1 | cut -d= -f2 || true)"

  if [[ "${CACHE_STATUS}" == "complete" && "${SKIP_IF_COMPLETE}" == "true" ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "Existing outputs are complete for the requested Python treatment repos." | tee -a "${LOG_FILE}"
    echo "Skipping expensive git-history analysis." | tee -a "${LOG_FILE}"
  elif [[ "${CACHE_STATUS}" == "partial" && "${INCREMENTAL_IF_PARTIAL}" == "true" ]]; then
    RUN_REPOS_FILE="${MISSING_REPOS_FILE}"
    RUN_OUTPUT_DIR="${TMP_OUTPUT_DIR}"
    mkdir -p "${RUN_OUTPUT_DIR}"

    echo | tee -a "${LOG_FILE}"
    echo "Existing outputs are partial." | tee -a "${LOG_FILE}"
    echo "Running analyzer only for missing repos." | tee -a "${LOG_FILE}"
    echo "Missing repos file: ${RUN_REPOS_FILE}" | tee -a "${LOG_FILE}"
    echo "Temporary output dir: ${RUN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
  fi
fi

# ------------------------------------------------------------
# Step 2: Run repository history analysis, unless cache is complete.
# ------------------------------------------------------------
if [[ "${SKIP_HISTORY_ANALYSIS}" == "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Repository history analysis skipped by user" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
  echo "Using existing adoption file: ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"

  if [[ ! -f "${ADOPTION_FILE}" ]]; then
    echo "ERROR: SKIP_HISTORY_ANALYSIS=true but adoption file not found: ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
    exit 1
  fi

elif [[ "${CACHE_STATUS}" == "complete" && "${SKIP_IF_COMPLETE}" == "true" && "${FORCE_RERUN}" != "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Repository history analysis skipped by cache" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

else
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Run Python treatment repository history analysis" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  cmd=(
    python "${PY_ANALYZER}"
    --repos-file "${RUN_REPOS_FILE}"
    --clone-dir "${CLONE_DIR}"
    --output-dir "${RUN_OUTPUT_DIR}"
    --aggregation "${AGGREGATION}"
    --num-processes "${NUM_PROCESSES}"
  )

  printf "Command:" | tee -a "${LOG_FILE}"
  printf " %q" "${cmd[@]}" | tee -a "${LOG_FILE}"
  echo | tee -a "${LOG_FILE}"
  echo | tee -a "${LOG_FILE}"

  set +e
  "${cmd[@]}" 2>&1 | tee -a "${LOG_FILE}"
  analyze_status=${PIPESTATUS[0]}
  set -e

  if [[ "${analyze_status}" -ne 0 ]]; then
    echo "ERROR: repository history analysis failed with exit code ${analyze_status}" | tee -a "${LOG_FILE}"
    exit "${analyze_status}"
  fi

  # If we analyzed only missing repos into a temporary directory, merge them
  # into the main output directory.
  if [[ "${RUN_OUTPUT_DIR}" != "${OUTPUT_DIR}" ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "** Step 2b: Merge incremental analysis outputs" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

    python - \
      "${OUTPUT_DIR}" \
      "${RUN_OUTPUT_DIR}" \
      "${AGGREGATION}" \
      "${REQUESTED_REPOS_FILE}" \
      "${MANIFEST_FILE}" \
      <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path
import pandas as pd

main_dir = Path(sys.argv[1])
tmp_dir = Path(sys.argv[2])
aggregation = sys.argv[3]
repos_file = Path(sys.argv[4])
manifest_file = Path(sys.argv[5])

time_col = "month" if aggregation == "month" else "week"

specs = [
    (f"ts_repos_{aggregation}ly.csv", ["repo_name", time_col]),
    (f"ts_contributors_{aggregation}ly.csv", ["repo_name", time_col, "author"]),
    ("cursor_commits.csv", None),
    ("ai_adoption_dates.csv", ["repo_name"]),
]

for filename, keys in specs:
    main_file = main_dir / filename
    tmp_file = tmp_dir / filename

    frames = []

    if main_file.exists():
        frames.append(pd.read_csv(main_file))

    if tmp_file.exists():
        frames.append(pd.read_csv(tmp_file))

    if not frames:
        print(f"MISSING after incremental merge: {main_file}")
        continue

    merged = pd.concat(frames, ignore_index=True)

    if keys and all(k in merged.columns for k in keys):
        merged = merged.drop_duplicates(keys, keep="first")
    else:
        merged = merged.drop_duplicates(keep="first")

    merged.to_csv(main_file, index=False)

    print(filename)
    print(f"  saved: {main_file}")
    print(f"  rows: {len(merged)}")
    if "repo_name" in merged.columns:
        print(f"  unique repos: {merged['repo_name'].nunique()}")

repos = pd.read_csv(repos_file)
if "repo_name" in repos.columns:
    repos[["repo_name"]].drop_duplicates("repo_name").to_csv(manifest_file, index=False)
    print(f"Manifest saved: {manifest_file}")
PY

  else
    echo | tee -a "${LOG_FILE}"
    echo "** Step 2b: Save analysis manifest" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

    python - "${REQUESTED_REPOS_FILE}" "${MANIFEST_FILE}" <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path
import pandas as pd

repos_file = Path(sys.argv[1])
manifest_file = Path(sys.argv[2])

repos = pd.read_csv(repos_file)

if "repo_name" not in repos.columns:
    print(f"WARNING: repo_name column missing in {repos_file}; manifest not saved")
else:
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    (
        repos[["repo_name"]]
        .assign(repo_name=lambda d: d["repo_name"].astype(str).str.strip())
        .query("repo_name != '' and repo_name != 'nan'")
        .drop_duplicates("repo_name")
        .to_csv(manifest_file, index=False)
    )
    print(f"Manifest saved: {manifest_file}")
PY
  fi
fi

# ------------------------------------------------------------
# Step 3: Compare event_month and detected adoption_month.
# This is cheap, so rerun it even when git-history analysis was skipped.
# ------------------------------------------------------------
if [[ "${SKIP_ADOPTION_CHECK}" == "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 3: Adoption month check skipped" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
else
  echo | tee -a "${LOG_FILE}"
  echo "** Step 3: Compare event_month and git-detected adoption_month" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  if [[ ! -f "${ADOPTION_FILE}" ]]; then
    echo "ERROR: adoption file not found: ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
    exit 1
  fi

  set +e
  python "${PY_ADOPTION_CHECK}" \
    --candidate-file "${REQUESTED_REPOS_FILE}" \
    --adoption-file "${ADOPTION_FILE}" \
    --output-match-file "${ADOPTION_MATCH_FILE}" \
    2>&1 | tee -a "${LOG_FILE}"

  check_status=${PIPESTATUS[0]}
  set -e

  if [[ "${check_status}" -ne 0 ]]; then
    echo "ERROR: adoption month check failed with exit code ${check_status}" | tee -a "${LOG_FILE}"
    exit "${check_status}"
  fi
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_DIR}/ts_repos_monthly.csv" \
  "${OUTPUT_DIR}/ts_contributors_monthly.csv" \
  "${OUTPUT_DIR}/cursor_commits.csv" \
  "${OUTPUT_DIR}/ai_adoption_dates.csv" \
  "${OUTPUT_DIR}/adoption_month_check.csv" \
  "${MANIFEST_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1e completed successfully." | tee -a "${LOG_FILE}"
echo "Requested repos file: ${REQUESTED_REPOS_FILE}" | tee -a "${LOG_FILE}"
# echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Main output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run7d1 and run8d, but it does
# NOT call existing shell wrappers.
#
# Design rule for the Python experiment:
#   - Reuse existing Python scripts.
#   - Do not depend on existing shell wrappers.
#   - Keep Python experiment paths and filenames explicit.


###############################################################################
# FILE: run-py-1f-save-treatment-options.sh
###############################################################################

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
#   repo_python/run-py-1f/treatment_python_sample_main_<N>.csv
#     - Primary treatment sample used by run-py-1g.
#
#   repo_python/tmp/run-py-1f/treatment_python_sample_exact_match_<N>.csv
#   repo_python/tmp/run-py-1f/treatment_python_sample_within1_month_<N>.csv
#   repo_python/tmp/run-py-1f/treatment_python_sample_diagnostic_<N>.csv
#     - Alternative and diagnostic treatment samples.
#
# Expected current Python result:
#   main       = 118
#   exact      = 118
#   within1    = 118
#   diagnostic = 0
# 
# Usage:
#   bash run-py-1f-save-treatment-options.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1f_save_treatment_options_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/save_treatment_options.py}"

# OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
# TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1f}"
# CHECK_FILE="${CHECK_FILE:-${OUTPUT_DIR}/treatment_python_did/adoption_month_check.csv}"
OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1f}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1f}"
CHECK_FILE="${CHECK_FILE:-${OUTPUT_BASE_DIR}/treatment_python_did/adoption_month_check.csv}"

PREFIX="${PREFIX:-treatment_python_sample}"
TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1f: save Python treatment sample options" | tee -a "${LOG_FILE}"
echo "Timestamp:        ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:    ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Check file:       ${CHECK_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:  ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
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

# Remove stale option files from the extra-output directory.
find "${TMP_DIR}" \
  -maxdepth 1 \
  -type f \
  -name "${PREFIX}_*.csv" \
  -delete

set +e
python "${PY_SCRIPT}" \
  --check-file "${CHECK_FILE}" \
  --output-dir "${TMP_DIR}" \
  --prefix "${PREFIX}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: treatment option saving failed with exit code ${run_status}" | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi


# Move the primary treatment sample into the main output directory.
MAIN_SAMPLE_FILE="$(
  find "${TMP_DIR}" \
    -maxdepth 1 \
    -type f \
    -name "${PREFIX}_main_*.csv" \
    -print
)"

if [[ -z "${MAIN_SAMPLE_FILE}" ]]; then
  echo "ERROR: primary treatment sample was not generated in ${TMP_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

MAIN_SAMPLE_COUNT="$(printf '%s\n' "${MAIN_SAMPLE_FILE}" | sed '/^$/d' | wc -l)"
if [[ "${MAIN_SAMPLE_COUNT}" -ne 1 ]]; then
  echo "ERROR: expected one primary treatment sample, found ${MAIN_SAMPLE_COUNT}" | tee -a "${LOG_FILE}"
  printf '%s\n' "${MAIN_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

MAIN_OUTPUT_FILE="${OUTPUT_DIR}/$(basename "${MAIN_SAMPLE_FILE}")"
mv -f "${MAIN_SAMPLE_FILE}" "${MAIN_OUTPUT_FILE}"

# Remove stale primary files with a different row-count suffix.
find "${OUTPUT_DIR}" \
  -maxdepth 1 \
  -type f \
  -name "${PREFIX}_main_*.csv" \
  ! -name "$(basename "${MAIN_OUTPUT_FILE}")" \
  -delete

echo "Primary treatment sample: ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_DIR}"/"${PREFIX}"_main_*.csv \
  "${TMP_DIR}"/"${PREFIX}"_*.csv
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1f completed successfully." | tee -a "${LOG_FILE}"
echo "Main output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
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


###############################################################################
# FILE: run-py-1g-extract-control-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1g: Extract matched Python control repositories
# ============================================================
#
# This wrapper is adapted from the logic of run8a-extract-jsts-control-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Design rule for the Python experiment:
#   - Reuse existing Python processing logic.
#   - Do not depend on existing shell wrappers.
#   - Keep Python experiment paths and filenames explicit.
#
# Main Python script:
#   proc_scripts/extract_matched_control_repos.py
#
# Input:
#   repo_python/run-py-1f/treatment_python_sample_main_118.csv
#     - Primary Python treatment sample created by run-py-1f.
#     - For the current Python run, main/exact/within1 are all identical,
#       but main is the primary replication input.
#
#   data_baseline_backup/matching.csv
#     - Matching file from the paper replication data.
#     - Expected columns:
#         repo_name
#         matched_control_1
#         matched_control_2
#         matched_control_3
#
# Main outputs:
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#     - Clean treatment-control pair file after overlap removal.
#
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#     - Unique clean control repos to clone in the next step.
#
# Extra outputs:
#   repo_python/tmp/run-py-1g/python_treatment_missing_matching_main_118.csv
#     - Treatment repos without matching rows.
#
#   repo_python/tmp/run-py-1g/python_control_extract_summary_main_118.csv
#     - Summary metrics for audit.
#
#   Raw pairs, raw controls, overlap diagnostics, and coverage files
#   are also stored under repo_python/tmp/run-py-1g.
# 
# Usage:
#   bash run-py-1g-extract-control-repos.sh
# 
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1g_extract_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/extract_matched_control_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1g}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1g}"

SAMPLE_NAME="${SAMPLE_NAME:-main_118}"

TREATMENT_SAMPLE_FILE="${TREATMENT_SAMPLE_FILE:-${OUTPUT_BASE_DIR}/run-py-1f/treatment_python_sample_${SAMPLE_NAME}.csv}"
MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"

PAIR_OUTPUT_FILE="${PAIR_OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_${SAMPLE_NAME}.csv}"
CONTROL_CLONE_FILE="${CONTROL_CLONE_FILE:-${MAIN_OUTPUT_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}.csv}"

MISSING_MATCH_FILE="${MISSING_MATCH_FILE:-${TMP_DIR}/python_treatment_missing_matching_${SAMPLE_NAME}.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_extract_summary_${SAMPLE_NAME}.csv}"

RAW_PAIR_OUTPUT_FILE="${RAW_PAIR_OUTPUT_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_raw.csv}"
RAW_CONTROL_CLONE_FILE="${RAW_CONTROL_CLONE_FILE:-${TMP_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}_raw.csv}"
OVERLAP_PAIR_FILE="${OVERLAP_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_overlap_pairs.csv}"
OVERLAP_REPO_FILE="${OVERLAP_REPO_FILE:-${TMP_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}_overlap_repos.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_coverage.csv}"

FULL_ADOPTER_FILE="${FULL_ADOPTER_FILE:-data_baseline_backup/panel_event_monthly.csv}"
FULL_ADOPTER_FILTER_COLUMN="${FULL_ADOPTER_FILTER_COLUMN:-is_treatment}"
FULL_ADOPTER_FILTER_VALUE="${FULL_ADOPTER_FILTER_VALUE:-1}"

TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"


echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1g: extract matched Python control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                     ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                 ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment sample file:         ${TREATMENT_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
echo "Matching file:                 ${MATCHING_FILE}" | tee -a "${LOG_FILE}"
echo "Sample name:                   ${SAMPLE_NAME}" | tee -a "${LOG_FILE}"
echo "Main output dir:               ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:              ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Pair output file:              ${PAIR_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Control clone file:            ${CONTROL_CLONE_FILE}" | tee -a "${LOG_FILE}"
echo "Missing match file:            ${MISSING_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:                  ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:                 ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Full adopter file:             ${FULL_ADOPTER_FILE}" | tee -a "${LOG_FILE}"
echo "Full adopter filter column:    ${FULL_ADOPTER_FILTER_COLUMN}" | tee -a "${LOG_FILE}"
echo "Full adopter filter value:     ${FULL_ADOPTER_FILTER_VALUE}" | tee -a "${LOG_FILE}"
echo "Top print:                     ${TOP_PRINT}" | tee -a "${LOG_FILE}"
echo "Log file:                      ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  echo "Create it first, for example:" | tee -a "${LOG_FILE}"
  echo "  cp proc_scripts/extract-jsts-control-repos.py proc_scripts/extract_matched_control_repos.py" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${TREATMENT_SAMPLE_FILE}" ]]; then
  echo "ERROR: treatment sample file not found: ${TREATMENT_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1f-save-treatment-options.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${MATCHING_FILE}" ]]; then
  echo "ERROR: matching file not found: ${MATCHING_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Input treatment sample summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${TREATMENT_SAMPLE_FILE}")
df = pd.read_csv(path)

if "repo_name" not in df.columns:
    raise SystemExit("ERROR: treatment sample must contain repo_name column.")

print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

if "repo_primary_language" in df.columns:
    print()
    print("Primary language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().to_string())

if "match_status" in df.columns:
    print()
    print("Treatment adoption match-status counts:")
    print(df["match_status"].fillna("(missing)").value_counts().to_string())

print()
print(df.head(20).to_string(index=False))
PY

echo | tee -a "${LOG_FILE}"
echo "** Extract matched Python controls" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

set +e
python "${PY_SCRIPT}" \
  --treatment-sample-file "${TREATMENT_SAMPLE_FILE}" \
  --matching-file "${MATCHING_FILE}" \
  --pair-output-file "${PAIR_OUTPUT_FILE}" \
  --control-clone-file "${CONTROL_CLONE_FILE}" \
  --missing-match-file "${MISSING_MATCH_FILE}" \
  --summary-file "${SUMMARY_FILE}" \
  --full-adopter-file "${FULL_ADOPTER_FILE}" \
  --full-adopter-filter-column "${FULL_ADOPTER_FILTER_COLUMN}" \
  --full-adopter-filter-value "${FULL_ADOPTER_FILTER_VALUE}" \
  --raw-pair-output-file "${RAW_PAIR_OUTPUT_FILE}" \
  --raw-control-clone-file "${RAW_CONTROL_CLONE_FILE}" \
  --overlap-pair-file "${OVERLAP_PAIR_FILE}" \
  --overlap-repo-file "${OVERLAP_REPO_FILE}" \
  --coverage-file "${COVERAGE_FILE}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: control extraction failed with exit code ${run_status}" | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${PAIR_OUTPUT_FILE}" \
  "${CONTROL_CLONE_FILE}" \
  "${MISSING_MATCH_FILE}" \
  "${SUMMARY_FILE}" \
  "${RAW_PAIR_OUTPUT_FILE}" \
  "${RAW_CONTROL_CLONE_FILE}" \
  "${OVERLAP_PAIR_FILE}" \
  "${OVERLAP_REPO_FILE}" \
  "${COVERAGE_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1g completed successfully." | tee -a "${LOG_FILE}"
echo "Pair output file: ${PAIR_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Control clone file: ${CONTROL_CLONE_FILE}" | tee -a "${LOG_FILE}"
echo "Missing match file: ${MISSING_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir: ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"


###############################################################################
# FILE: run-py-1h-clone-control-repos.sh
###############################################################################

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


###############################################################################
# FILE: run-py-1i-create-control-usable-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1i: Create clone-usable control repository sample
# ============================================================
#
#   repo_python/run-py-1h/python_control_clone_status_main_<N>.csv
#   repo_python/run-py-1g/python_matched_control_pairs_main_<N>.csv
#   repo_python/run-py-1g/python_control_repos_to_clone_main_<N>.csv
#
# Main outputs:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#   repo_python/run-py-1i/python_matched_control_pairs_main_clone_usable.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1i/python_control_clone_failed_repos_main.csv
#   repo_python/tmp/run-py-1i/python_matched_control_pairs_main_clone_failed.csv
#   repo_python/tmp/run-py-1i/python_control_pair_coverage_main_clone_usable.csv
#   repo_python/tmp/run-py-1i/python_treatment_lost_all_controls_main.csv
#   repo_python/tmp/run-py-1i/python_control_clone_usable_summary_main.csv
# 
# Usage:
#   bash run-py-1i-create-control-usable-repos.sh
# ============================================================
 
SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi


LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
SAMPLE_VARIANT="${SAMPLE_VARIANT:-main}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()
  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

CLONE_STATUS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1h/python_control_clone_status_${SAMPLE_VARIANT}_[0-9]*.csv"
PAIR_FILE_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_matched_control_pairs_${SAMPLE_VARIANT}_[0-9]*.csv"
CONTROL_REPOS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_control_repos_to_clone_${SAMPLE_VARIANT}_[0-9]*.csv"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-$(resolve_single_input "${CLONE_STATUS_PATTERN}" "clone-status file")}"
PAIR_FILE="${PAIR_FILE:-$(resolve_single_input "${PAIR_FILE_PATTERN}" "matched-pair file")}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-$(resolve_single_input "${CONTROL_REPOS_PATTERN}" "control-repository file")}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_usable_repos_${SAMPLE_VARIANT}.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_usable.csv}"

FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${TMP_DIR}/python_control_clone_failed_repos_${SAMPLE_VARIANT}.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_${SAMPLE_VARIANT}_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${TMP_DIR}/python_treatment_lost_all_controls_${SAMPLE_VARIANT}.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_clone_usable_summary_${SAMPLE_VARIANT}.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated_existing}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: create clone-usable control repository sample" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                  ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                   ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Sample variant:               ${SAMPLE_VARIANT}" | tee -a "${LOG_FILE}"
echo "Main output dir:              ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:             ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Clone status file:            ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Pair file:                    ${PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Control repos file:           ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Usable statuses:              ${USABLE_STATUSES}" | tee -a "${LOG_FILE}"
echo "Usable control file:          ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Failed control file:          ${FAILED_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:             ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Dropped pair file:            ${DROPPED_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:                ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Zero-control treatment file:  ${ZERO_CONTROL_TREATMENT_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:                 ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Fail if zero control:         ${FAIL_IF_ZERO_CONTROL}" | tee -a "${LOG_FILE}"
echo "Log file:                     ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in "${PY_SCRIPT}" "${CLONE_STATUS_FILE}" "${PAIR_FILE}" "${CONTROL_REPOS_FILE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

CMD=(
  python "${PY_SCRIPT}"
  --clone-status-file "${CLONE_STATUS_FILE}"
  --pair-file "${PAIR_FILE}"
  --control-repos-file "${CONTROL_REPOS_FILE}"
  --usable-control-file "${USABLE_CONTROL_FILE}"
  --failed-control-file "${FAILED_CONTROL_FILE}"
  --usable-pair-file "${USABLE_PAIR_FILE}"
  --dropped-pair-file "${DROPPED_PAIR_FILE}"
  --coverage-file "${COVERAGE_FILE}"
  --zero-control-treatment-file "${ZERO_CONTROL_TREATMENT_FILE}"
  --summary-file "${SUMMARY_FILE}"
  --usable-statuses "${USABLE_STATUSES}"
)

if [[ "${FAIL_IF_ZERO_CONTROL}" == "true" ]]; then
  CMD+=(--fail-if-zero-control)
fi

echo "** Running Python script" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${USABLE_CONTROL_FILE}" \
  "${FAILED_CONTROL_FILE}" \
  "${USABLE_PAIR_FILE}" \
  "${DROPPED_PAIR_FILE}" \
  "${COVERAGE_FILE}" \
  "${ZERO_CONTROL_TREATMENT_FILE}" \
  "${SUMMARY_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:    ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:       ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:        ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:     ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:    ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8c-create-control-usable-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-1j-analyze-control-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1j: Analyze clone-usable control repositories
# ============================================================
#
# Purpose:
#   Analyze git history for clone-usable Python matched control repos.
#
# Input:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#
# Clone dir:
#   ../control-repos
#
# Full-run main outputs:
#   repo_python/run-py-1j/ts_repos_monthly.csv
#   repo_python/run-py-1j/ts_contributors_monthly.csv
#   repo_python/run-py-1j/cursor_commits.csv
#   repo_python/run-py-1j/ai_adoption_dates.csv
#
# Full-run extra outputs:
#   repo_python/tmp/run-py-1j/full/
#
# Smoke-run outputs:
#   repo_python/tmp/run-py-1j/smoke/
#
# Usage:
#   Smoke test:
#     MAX_REPOS=5 NUM_PROCESSES=1 bash run-py-1j-analyze-control-repos.sh
#
#   Full run:
#     MAX_REPOS=0 NUM_PROCESSES=2 bash run-py-1j-analyze-control-repos.sh
# ============================================================
SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi


LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_analyze_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_repos_v2.py}"
CACHE_CHECK_SCRIPT="${CACHE_CHECK_SCRIPT:-proc_scripts/check_cache_control_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

REPOS_FILE="${REPOS_FILE:-${OUTPUT_BASE_DIR}/run-py-1i/python_control_clone_usable_repos_main.csv}"
CLONE_DIR="${CLONE_DIR:-../control-repos}"

FULL_OUTPUT_DIR="${FULL_OUTPUT_DIR:-${MAIN_OUTPUT_DIR}}"
SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${TMP_DIR}/smoke/output}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-2}"
MAX_REPOS="${MAX_REPOS:-5}"

SKIP_IF_COMPLETE="${SKIP_IF_COMPLETE:-true}"
INCREMENTAL_IF_PARTIAL="${INCREMENTAL_IF_PARTIAL:-true}"
FORCE_RERUN="${FORCE_RERUN:-false}"

if [[ "${MAX_REPOS}" -gt 0 ]]; then
  OUTPUT_DIR="${OUTPUT_DIR:-${SMOKE_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_DIR}/smoke}"
else
  OUTPUT_DIR="${OUTPUT_DIR:-${FULL_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_DIR}/full}"
fi

REPO_TS_FILE="${OUTPUT_DIR}/ts_repos_${AGGREGATION}ly.csv"
CONTRIB_TS_FILE="${OUTPUT_DIR}/ts_contributors_${AGGREGATION}ly.csv"
CURSOR_COMMITS_FILE="${OUTPUT_DIR}/cursor_commits.csv"
ADOPTION_FILE="${OUTPUT_DIR}/ai_adoption_dates.csv"
MANIFEST_FILE="${MANIFEST_FILE:-${EXTRA_DIR}/${RUN_PREFIX}_analyzed_repos_manifest.csv}"

MISSING_REPOS_FILE="${MISSING_REPOS_FILE:-${EXTRA_DIR}/${RUN_PREFIX}_missing_repos_${RUN_TS}.csv}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${EXTRA_DIR}/incremental_${RUN_TS}}"
CACHE_REPORT="${CACHE_REPORT:-${EXTRA_DIR}/${RUN_PREFIX}_cache_check_${RUN_TS}.txt}"
 
mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${EXTRA_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: analyze clone-usable control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:              ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:            ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:             ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:          ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Cache check script:     ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:             ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:              ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Analysis output dir:    ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:       ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:            ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:          ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:              ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Skip if complete:       ${SKIP_IF_COMPLETE}" | tee -a "${LOG_FILE}"
echo "Incremental if partial: ${INCREMENTAL_IF_PARTIAL}" | tee -a "${LOG_FILE}"
echo "Force rerun:            ${FORCE_RERUN}" | tee -a "${LOG_FILE}"
echo "Repo time series:       ${REPO_TS_FILE}" | tee -a "${LOG_FILE}"
echo "Contributor time series:${CONTRIB_TS_FILE}" | tee -a "${LOG_FILE}"
echo "Cursor commits:         ${CURSOR_COMMITS_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption file:          ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Manifest file:          ${MANIFEST_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:               ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in "${PY_SCRIPT}" "${CACHE_CHECK_SCRIPT}" "${REPOS_FILE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Step 0: Input control repo summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

path = Path("${REPOS_FILE}")
df = pd.read_csv(path)

if "repo_name" not in df.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {path}")

print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

if "status" in df.columns:
    print()
    print("Clone status counts:")
    print(df["status"].fillna("(missing)").value_counts().to_string())

print()
print(df.head(20).to_string(index=False))
PY

RUN_REPOS_FILE="${REPOS_FILE}"
RUN_OUTPUT_DIR="${OUTPUT_DIR}"
RUN_MAX_REPOS="${MAX_REPOS}"
CACHE_STATUS="run_full"

if [[ "${MAX_REPOS}" -gt 0 ]]; then
  RUN_REPOS_FILE="${EXTRA_DIR}/control_repos_smoke_max${MAX_REPOS}.csv"
  RUN_MAX_REPOS="0"

  echo | tee -a "${LOG_FILE}"
  echo "** Step 0b: Create fixed smoke repo file" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

src = Path("${REPOS_FILE}")
dst = Path("${RUN_REPOS_FILE}")
n = int("${MAX_REPOS}")

df = pd.read_csv(src)
df = df.drop_duplicates("repo_name").head(n).copy()
dst.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(dst, index=False)

print("Smoke repos:", len(df))
print("Saved:", dst)
print()
print(df[["repo_name"]].to_string(index=False))
PY
fi

if [[ "${FORCE_RERUN}" != "true" && "${SKIP_IF_COMPLETE}" == "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 1: Cache check" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  python "${CACHE_CHECK_SCRIPT}" \
    "${RUN_REPOS_FILE}" \
    "${REPO_TS_FILE}" \
    "${CONTRIB_TS_FILE}" \
    "${CURSOR_COMMITS_FILE}" \
    "${ADOPTION_FILE}" \
    "${MANIFEST_FILE}" \
    "${MISSING_REPOS_FILE}" \
    2>&1 | tee "${CACHE_REPORT}" | tee -a "${LOG_FILE}"

  CACHE_STATUS="$(grep '^CACHE_STATUS=' "${CACHE_REPORT}" | tail -1 | cut -d= -f2 || true)"

  if [[ "${CACHE_STATUS}" == "complete" ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "Existing outputs are complete for requested control repos." | tee -a "${LOG_FILE}"
    echo "Skipping expensive git-history analysis." | tee -a "${LOG_FILE}"
  elif [[ "${CACHE_STATUS}" == "partial" && "${INCREMENTAL_IF_PARTIAL}" == "true" ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "Partial cache detected. Analyzing only missing control repos." | tee -a "${LOG_FILE}"
    RUN_REPOS_FILE="${MISSING_REPOS_FILE}"
    RUN_OUTPUT_DIR="${TMP_OUTPUT_DIR}"
    RUN_MAX_REPOS="0"
    mkdir -p "${RUN_OUTPUT_DIR}"
  else
    echo | tee -a "${LOG_FILE}"
    echo "Cache status requires full analysis: ${CACHE_STATUS}" | tee -a "${LOG_FILE}"
  fi
fi

if [[ "${CACHE_STATUS}" != "complete" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Step 2: Run control repository history analysis" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
  echo "Command: python ${PY_SCRIPT} --repos-file ${RUN_REPOS_FILE} --clone-dir ${CLONE_DIR} --output-dir ${RUN_OUTPUT_DIR} --aggregation ${AGGREGATION} --num-processes ${NUM_PROCESSES} --max-repos ${RUN_MAX_REPOS}" | tee -a "${LOG_FILE}"
  echo | tee -a "${LOG_FILE}"

  python "${PY_SCRIPT}" \
    --repos-file "${RUN_REPOS_FILE}" \
    --clone-dir "${CLONE_DIR}" \
    --output-dir "${RUN_OUTPUT_DIR}" \
    --aggregation "${AGGREGATION}" \
    --num-processes "${NUM_PROCESSES}" \
    --max-repos "${RUN_MAX_REPOS}" \
    2>&1 | tee -a "${LOG_FILE}"

  # Some control samples may have no local Cursor commits.
  # The analyzer may skip writing cursor_commits.csv when it is empty.
  # Create an empty file so cache checks do not force unnecessary reruns.
  if [[ ! -f "${RUN_OUTPUT_DIR}/cursor_commits.csv" ]]; then
    echo "repo_name,commit_hash,authored_at,committed_at,paths,message" > "${RUN_OUTPUT_DIR}/cursor_commits.csv"
  fi

  if [[ "${RUN_OUTPUT_DIR}" == "${TMP_OUTPUT_DIR}" ]]; then
    echo | tee -a "${LOG_FILE}"
    echo "** Step 2b: Merge incremental outputs" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

    python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

base = Path("${OUTPUT_DIR}")
inc = Path("${TMP_OUTPUT_DIR}")

def merge_csv(name, keys):
    base_path = base / name
    inc_path = inc / name

    if not inc_path.exists():
        print(f"Incremental file missing, skip: {inc_path}")
        return

    inc_df = pd.read_csv(inc_path)

    if base_path.exists():
        base_df = pd.read_csv(base_path)
        out = pd.concat([base_df, inc_df], ignore_index=True)
    else:
        out = inc_df

    available_keys = [k for k in keys if k in out.columns]
    if available_keys:
        out = out.drop_duplicates(available_keys, keep="last")
    else:
        out = out.drop_duplicates()

    out.to_csv(base_path, index=False)
    print(f"Merged {name}: {len(out)} rows")

merge_csv("ts_repos_${AGGREGATION}ly.csv", ["repo_name", "time"])
merge_csv("ts_contributors_${AGGREGATION}ly.csv", ["repo_name", "time", "author"])
merge_csv("cursor_commits.csv", ["repo_name", "commit_hash"])
merge_csv("ai_adoption_dates.csv", ["repo_name"])
PY
  fi
fi

# Ensure canonical cursor_commits.csv exists even if there is no local Cursor evidence.
if [[ ! -f "${CURSOR_COMMITS_FILE}" ]]; then
  echo "repo_name,commit_hash,authored_at,committed_at,paths,message" > "${CURSOR_COMMITS_FILE}"
fi

echo | tee -a "${LOG_FILE}"
echo "** Step 3: Save analysis manifest" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

repos_path = Path("${RUN_REPOS_FILE}")
manifest_path = Path("${MANIFEST_FILE}")

# For complete cache, use the requested repo file.
if "${CACHE_STATUS}" == "complete":
    repos_path = Path("${RUN_REPOS_FILE}")

df = pd.read_csv(repos_path)
if "repo_name" not in df.columns:
    raise SystemExit("ERROR: repo_name column missing while saving manifest.")

df = df[["repo_name"]].drop_duplicates().copy()
df["analyzed_at"] = "${RUN_TS}"
manifest_path.parent.mkdir(parents=True, exist_ok=True)

if manifest_path.exists() and "${CACHE_STATUS}" != "complete":
    old = pd.read_csv(manifest_path)
    if "repo_name" in old.columns:
        old = old[["repo_name"]].drop_duplicates()
        old["analyzed_at"] = old.get("analyzed_at", "${RUN_TS}")
        df = pd.concat([old, df], ignore_index=True).drop_duplicates("repo_name", keep="last")

df.to_csv(manifest_path, index=False)
print("Manifest saved:", manifest_path)
print("Manifest rows:", len(df))
PY

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${REPO_TS_FILE}" \
  "${CONTRIB_TS_FILE}" \
  "${CURSOR_COMMITS_FILE}" \
  "${ADOPTION_FILE}" \
  "${MANIFEST_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Requested repos file: ${RUN_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Analysis output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8d-analyze-control-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-1k-filter-local-cursor-controls.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1k: Filter controls with local Cursor evidence
# ============================================================
#
# Purpose:
#   Remove clone-usable control repositories that contain local Cursor
#   evidence within the analysis window and recompute final matched
#   control-pair coverage.
#
# Inputs:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#   repo_python/run-py-1i/python_matched_control_pairs_main_clone_usable.csv
#   repo_python/run-py-1j/ai_adoption_dates.csv
#   repo_python/run-py-1j/ts_repos_monthly.csv
#   repo_python/run-py-1j/ts_contributors_monthly.csv
#
# Main outputs:
#   repo_python/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv
#   repo_python/run-py-1k/python_matched_control_pairs_main_final_clean.csv
#   repo_python/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv
#   repo_python/run-py-1k/ts_repos_monthly_final_clean.csv
#   repo_python/run-py-1k/ts_contributors_monthly_final_clean.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1k/python_control_local_cursor_evidence_in_window.csv
#   repo_python/tmp/run-py-1k/python_control_local_cursor_evidence_post_window.csv
#   repo_python/tmp/run-py-1k/python_matched_control_pairs_main_local_cursor_dropped.csv
#   repo_python/tmp/run-py-1k/python_control_pair_coverage_main_final_clean.csv
#   repo_python/tmp/run-py-1k/python_treatment_lost_all_controls_main_final_clean.csv
#   repo_python/tmp/run-py-1k/python_control_local_cursor_filter_summary_main.csv
#   repo_python/tmp/run-py-1k/python_control_pair_coverage_main_final_clean_1to3_only.csv
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_filter_local_cursor_controls_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/filter_controls_by_local_cursor_evidence.py}"

ANALYSIS_END="${ANALYSIS_END:-2025-08}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CONTROL_ANALYSIS_DIR="${CONTROL_ANALYSIS_DIR:-${OUTPUT_BASE_DIR}/run-py-1j}"
CONTROL_FILE="${CONTROL_FILE:-${OUTPUT_BASE_DIR}/run-py-1i/python_control_clone_usable_repos_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_BASE_DIR}/run-py-1i/python_matched_control_pairs_main_clone_usable.csv}"
ADOPTION_FILE="${ADOPTION_FILE:-${CONTROL_ANALYSIS_DIR}/ai_adoption_dates.csv}"

CONTROL_TS_REPOS_FILE="${CONTROL_TS_REPOS_FILE:-${CONTROL_ANALYSIS_DIR}/ts_repos_monthly.csv}"
CONTROL_TS_CONTRIBUTORS_FILE="${CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_ANALYSIS_DIR}/ts_contributors_monthly.csv}"

IN_WINDOW_EVIDENCE_FILE="${IN_WINDOW_EVIDENCE_FILE:-${TMP_DIR}/python_control_local_cursor_evidence_in_window.csv}"
POST_WINDOW_EVIDENCE_FILE="${POST_WINDOW_EVIDENCE_FILE:-${TMP_DIR}/python_control_local_cursor_evidence_post_window.csv}"

FINAL_CONTROL_FILE="${FINAL_CONTROL_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_usable_repos_main_final_clean.csv}"
FINAL_PAIR_FILE="${FINAL_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_main_final_clean.csv}"

DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_main_local_cursor_dropped.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_main_final_clean.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${TMP_DIR}/python_treatment_lost_all_controls_main_final_clean.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_local_cursor_filter_summary_main.csv}"

STRICT_1TO3_PAIR_FILE="${STRICT_1TO3_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_main_final_clean_1to3_only.csv}"
STRICT_1TO3_COVERAGE_FILE="${STRICT_1TO3_COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_main_final_clean_1to3_only.csv}"

FINAL_CONTROL_TS_REPOS_FILE="${FINAL_CONTROL_TS_REPOS_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_final_clean.csv}"
FINAL_CONTROL_TS_CONTRIBUTORS_FILE="${FINAL_CONTROL_TS_CONTRIBUTORS_FILE:-${MAIN_OUTPUT_DIR}/ts_contributors_monthly_final_clean.csv}"
 
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"
 
mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: filter controls with local Cursor evidence" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                       ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                        ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:                     ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Analysis end:                      ${ANALYSIS_END}" | tee -a "${LOG_FILE}"
echo "Main output dir:                   ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:                  ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Control file:                      ${CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Pair file:                         ${PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption file:                     ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Control repo time-series file:     ${CONTROL_TS_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Control contributor time-series:   ${CONTROL_TS_CONTRIBUTORS_FILE}" | tee -a "${LOG_FILE}"
echo "Final control file:                ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file:                   ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file:               ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pair file:              ${STRICT_1TO3_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 coverage file:          ${STRICT_1TO3_COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Final control repo time-series:    ${FINAL_CONTROL_TS_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Final control contributor series:  ${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:                      ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Fail if zero control:              ${FAIL_IF_ZERO_CONTROL}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${CONTROL_FILE}" \
  "${PAIR_FILE}" \
  "${ADOPTION_FILE}" \
  "${CONTROL_TS_REPOS_FILE}" \
  "${CONTROL_TS_CONTRIBUTORS_FILE}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

CMD=(
  python "${PY_SCRIPT}"
  --analysis-end "${ANALYSIS_END}"
  --control-file "${CONTROL_FILE}"
  --pair-file "${PAIR_FILE}"
  --adoption-file "${ADOPTION_FILE}"
  --control-ts-repos-file "${CONTROL_TS_REPOS_FILE}"
  --control-ts-contributors-file "${CONTROL_TS_CONTRIBUTORS_FILE}"
  --in-window-evidence-file "${IN_WINDOW_EVIDENCE_FILE}"
  --post-window-evidence-file "${POST_WINDOW_EVIDENCE_FILE}"
  --final-control-file "${FINAL_CONTROL_FILE}"
  --final-pair-file "${FINAL_PAIR_FILE}"
  --dropped-pair-file "${DROPPED_PAIR_FILE}"
  --coverage-file "${COVERAGE_FILE}"
  --zero-control-treatment-file "${ZERO_CONTROL_TREATMENT_FILE}"
  --summary-file "${SUMMARY_FILE}"
  --strict-1to3-pair-file "${STRICT_1TO3_PAIR_FILE}"
  --strict-1to3-coverage-file "${STRICT_1TO3_COVERAGE_FILE}"
  --final-control-ts-repos-file "${FINAL_CONTROL_TS_REPOS_FILE}"
  --final-control-ts-contributors-file "${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}"
)

if [[ "${FAIL_IF_ZERO_CONTROL}" == "true" ]]; then
  CMD+=(--fail-if-zero-control)
fi

echo "** Running local Cursor evidence filter" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${IN_WINDOW_EVIDENCE_FILE}" \
  "${POST_WINDOW_EVIDENCE_FILE}" \
  "${FINAL_CONTROL_FILE}" \
  "${FINAL_PAIR_FILE}" \
  "${DROPPED_PAIR_FILE}" \
  "${COVERAGE_FILE}" \
  "${ZERO_CONTROL_TREATMENT_FILE}" \
  "${SUMMARY_FILE}" \
  "${STRICT_1TO3_PAIR_FILE}" \
  "${STRICT_1TO3_COVERAGE_FILE}" \
  "${FINAL_CONTROL_TS_REPOS_FILE}" \
  "${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Final control file: ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file: ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file: ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir: ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
# 
# This wrapper is adapted from the logic of run8d2-filter-local-cursor-controls.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# FILE: run-py-1l-build-matched-panel.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1l: Build and summarize final matched Python DiD panels
# ============================================================
#
# Purpose:
#   1. Build flexible and strict matched Python DiD panels.
#   2. Build window-driven versions of both panels.
#   3. Summarize the panels and compare them with paper counts.
#
# Reused Python scripts:
#   proc_scripts/prepare_panel_event_v2.py
#   proc_scripts/summarize_matched_panels.py
#
# Main outputs:
#   repo_python/run-py-1l/panel_event_matched_flexible.csv
#   repo_python/run-py-1l/panel_event_matched_flexible_window_driven.csv
#   repo_python/run-py-1l/panel_event_matched_strict.csv
#   repo_python/run-py-1l/panel_event_matched_strict_window_driven.csv
#
# Extra QC outputs:
#   repo_python/tmp/run-py-1l/qc/panel_qc_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_by_source.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_paper_comparison.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_attrition_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_dropped_by_strict.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_notes.md
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are kept as provenance, not as pseudo-event assignments.
#   - Normalized time-series inputs are removed after the run by default.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_build_and_summarize_matched_panels_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"
SUMMARY_SCRIPT="${SUMMARY_SCRIPT:-proc_scripts/summarize_matched_panels.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
QC_TMP_DIR="${QC_TMP_DIR:-${TMP_DIR}/qc}"
DID_DIR="${DID_DIR:-${MAIN_OUTPUT_DIR}}"
NORMALIZED_DIR="${NORMALIZED_DIR:-${TMP_DIR}/normalized_inputs_${RUN_TS}}"
KEEP_NORMALIZED_INPUTS="${KEEP_NORMALIZED_INPUTS:-false}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()

  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

TREATMENT_META_PATTERN="${OUTPUT_BASE_DIR}/run-py-1f/treatment_python_sample_main_[0-9]*.csv"
TREATMENT_MISSING_MATCHING_PATTERN="${OUTPUT_BASE_DIR}/tmp/run-py-1g/python_treatment_missing_matching_main_[0-9]*.csv"

TREATMENT_META="${TREATMENT_META:-$(resolve_single_input "${TREATMENT_META_PATTERN}" "treatment metadata file")}"
TREATMENT_MISSING_MATCHING="${TREATMENT_MISSING_MATCHING:-$(resolve_single_input "${TREATMENT_MISSING_MATCHING_PATTERN}" "missing-matching file")}"

MAIN_PAIRS_FILE="${MAIN_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean.csv}"
STRICT_PAIRS_FILE="${STRICT_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv}"

TREATMENT_TS_RAW="${TREATMENT_TS_RAW:-${OUTPUT_BASE_DIR}/treatment_python_did/ts_repos_monthly.csv}"
CONTROL_TS_RAW="${CONTROL_TS_RAW:-${OUTPUT_BASE_DIR}/run-py-1k/ts_repos_monthly_final_clean.csv}"

TREATMENT_TS="${TREATMENT_TS:-${NORMALIZED_DIR}/treatment_ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-${NORMALIZED_DIR}/control_ts_repos_monthly.csv}"

MAIN_OUTPUT_FILE="${MAIN_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
MAIN_BALANCED_OUTPUT_FILE="${MAIN_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_OUTPUT_FILE="${STRICT_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
STRICT_BALANCED_OUTPUT_FILE="${STRICT_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

OUTPUT_SUMMARY="${OUTPUT_SUMMARY:-${QC_TMP_DIR}/panel_qc_summary.csv}"
OUTPUT_BY_SOURCE="${OUTPUT_BY_SOURCE:-${QC_TMP_DIR}/panel_qc_by_source.csv}"
OUTPUT_PAPER_COMPARISON="${OUTPUT_PAPER_COMPARISON:-${QC_TMP_DIR}/panel_qc_paper_comparison.csv}"
OUTPUT_ATTRITION="${OUTPUT_ATTRITION:-${QC_TMP_DIR}/panel_qc_attrition_summary.csv}"
OUTPUT_DROPPED_BY_STRICT="${OUTPUT_DROPPED_BY_STRICT:-${QC_TMP_DIR}/panel_qc_dropped_by_strict.csv}"
OUTPUT_NOTES="${OUTPUT_NOTES:-${QC_TMP_DIR}/panel_qc_notes.md}"

FINAL_COVERAGE="${FINAL_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean.csv}"
STRICT_COVERAGE="${STRICT_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean_1to3_only.csv}"
FINAL_CONTROLS="${FINAL_CONTROLS:-${OUTPUT_BASE_DIR}/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv}"

PAPER_TREATMENT_REPOS="${PAPER_TREATMENT_REPOS:-121}"
PAPER_CONTROL_REPOS="${PAPER_CONTROL_REPOS:-127}"
PAPER_TOTAL_OBSERVATIONS="${PAPER_TOTAL_OBSERVATIONS:-2461}"
PAPER_POST_TREATMENT_OBSERVATIONS="${PAPER_POST_TREATMENT_OBSERVATIONS:-582}"

cleanup_normalized_inputs() {
  if [[ "${KEEP_NORMALIZED_INPUTS}" != "true" ]]; then
    rm -rf "${NORMALIZED_DIR}"
  fi
}
trap cleanup_normalized_inputs EXIT

mkdir -p "${LOG_DIR}" "${DID_DIR}" "${QC_TMP_DIR}" "${NORMALIZED_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: build and summarize final matched Python DiD panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                       ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                        ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Panel script:                      ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Summary script:                    ${SUMMARY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Main output dir:                   ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Extra QC dir:                      ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:                ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Treatment missing matching:        ${TREATMENT_MISSING_MATCHING}" | tee -a "${LOG_FILE}"
echo "Main pairs file:                   ${MAIN_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pairs file:             ${STRICT_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series raw:         ${TREATMENT_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Control time series raw:           ${CONTROL_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Flexible panel:                    ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:                      ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC output dir:                     ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "QC summary:                        ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison:                  ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:                          ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Keep normalized inputs:            ${KEEP_NORMALIZED_INPUTS}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${SUMMARY_SCRIPT}" \
  "${TREATMENT_META}" \
  "${TREATMENT_MISSING_MATCHING}" \
  "${MAIN_PAIRS_FILE}" \
  "${STRICT_PAIRS_FILE}" \
  "${TREATMENT_TS_RAW}" \
  "${CONTROL_TS_RAW}" \
  "${FINAL_COVERAGE}" \
  "${STRICT_COVERAGE}" \
  "${FINAL_CONTROLS}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Step 0: Compile Python scripts" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}" "${SUMMARY_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 1: Normalize time-series input columns" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

def normalize_ts(src_text, dst_text, label):
    src = Path(src_text)
    dst = Path(dst_text)
    df = pd.read_csv(src)

    if "repo_name" not in df.columns:
        raise SystemExit(f"ERROR: {label} is missing repo_name column: {src}")

    # prepare_panel_event_v2.py expects a month column in the JS/TS wrapper.
    # Some analyzer versions write time instead of month, so create month safely.
    if "month" not in df.columns:
        if "time" in df.columns:
            df["month"] = df["time"].astype(str).str[:7]
        else:
            raise SystemExit(
                f"ERROR: {label} must contain either month or time column. "
                f"Columns: {list(df.columns)}"
            )

    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["month"] = df["month"].astype(str).str.strip().str[:7]

    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False)

    print(f"{label}:")
    print(f"  input:  {src}")
    print(f"  output: {dst}")
    print(f"  rows:   {len(df)}")
    print(f"  repos:  {df['repo_name'].nunique()}")
    print(f"  month range: {df['month'].min()} to {df['month'].max()}")
    print(f"  columns: {list(df.columns)}")
    print()

normalize_ts("${TREATMENT_TS_RAW}", "${TREATMENT_TS}", "treatment_ts")
normalize_ts("${CONTROL_TS_RAW}", "${CONTROL_TS}", "control_ts")
PY

echo | tee -a "${LOG_FILE}"
echo "** Step 2: Check input schemas" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

files = {
    "treatment_meta": Path("${TREATMENT_META}"),
    "main_pairs": Path("${MAIN_PAIRS_FILE}"),
    "strict_pairs": Path("${STRICT_PAIRS_FILE}"),
    "treatment_ts": Path("${TREATMENT_TS}"),
    "control_ts": Path("${CONTROL_TS}"),
}

required = {
    "treatment_meta": {"repo_name", "event_month"},
    "main_pairs": {"treatment_repo", "control_repo"},
    "strict_pairs": {"treatment_repo", "control_repo"},
    "treatment_ts": {"repo_name", "month"},
    "control_ts": {"repo_name", "month"},
}

for name, path in files.items():
    cols = set(pd.read_csv(path, nrows=0).columns)
    missing = required[name] - cols
    print(f"{name}: {path}")
    print("  required:", sorted(required[name]))
    print("  columns:", sorted(cols))
    if missing:
        raise SystemExit(f"ERROR: {name} missing columns: {sorted(missing)}")
    print("  status: OK")
    print()

print("Schema check passed.")
PY

run_panel_builder() {
  local label="$1"
  local pairs_file="$2"
  local output_file="$3"
  local balanced_output_file="$4"

  echo | tee -a "${LOG_FILE}"
  echo "** Step 3: Build ${label} panel" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  CMD=(
    python "${PY_SCRIPT}"
    --treatment-meta "${TREATMENT_META}"
    --pairs "${pairs_file}"
    --treatment-ts "${TREATMENT_TS}"
    --control-ts "${CONTROL_TS}"
    --output "${output_file}"
    --balanced-output "${balanced_output_file}"
  )

  echo "${CMD[*]}" | tee -a "${LOG_FILE}"
  echo | tee -a "${LOG_FILE}"

  "${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

run_panel_builder \
  "main final-clean" \
  "${MAIN_PAIRS_FILE}" \
  "${MAIN_OUTPUT_FILE}" \
  "${MAIN_BALANCED_OUTPUT_FILE}"

run_panel_builder \
  "strict 1:3 final-clean" \
  "${STRICT_PAIRS_FILE}" \
  "${STRICT_OUTPUT_FILE}" \
  "${STRICT_BALANCED_OUTPUT_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 4: Summarize matched panels" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

SUMMARY_CMD=(
  python "${SUMMARY_SCRIPT}"
  --flexible-panel "${MAIN_OUTPUT_FILE}"
  --strict-panel "${STRICT_OUTPUT_FILE}"
  --flexible-window-driven-panel "${MAIN_BALANCED_OUTPUT_FILE}"
  --strict-window-driven-panel "${STRICT_BALANCED_OUTPUT_FILE}"
  --output-summary "${OUTPUT_SUMMARY}"
  --output-by-source "${OUTPUT_BY_SOURCE}"
  --output-paper-comparison "${OUTPUT_PAPER_COMPARISON}"
  --output-attrition "${OUTPUT_ATTRITION}"
  --output-dropped-by-strict "${OUTPUT_DROPPED_BY_STRICT}"
  --output-notes "${OUTPUT_NOTES}"
  --treatment-sample "${TREATMENT_META}"
  --treatment-missing-matching "${TREATMENT_MISSING_MATCHING}"
  --final-coverage "${FINAL_COVERAGE}"
  --strict-coverage "${STRICT_COVERAGE}"
  --final-controls "${FINAL_CONTROLS}"
  --paper-treatment-repos "${PAPER_TREATMENT_REPOS}"
  --paper-control-repos "${PAPER_CONTROL_REPOS}"
  --paper-total-observations "${PAPER_TOTAL_OBSERVATIONS}"
  --paper-post-treatment-observations "${PAPER_POST_TREATMENT_OBSERVATIONS}"
)

echo "${SUMMARY_CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"
"${SUMMARY_CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 5: Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${MAIN_OUTPUT_FILE}" \
  "${MAIN_BALANCED_OUTPUT_FILE}" \
  "${STRICT_OUTPUT_FILE}" \
  "${STRICT_BALANCED_OUTPUT_FILE}" \
  "${OUTPUT_SUMMARY}" \
  "${OUTPUT_PAPER_COMPARISON}" \
  "${OUTPUT_NOTES}" \
  "${OUTPUT_BY_SOURCE}" \
  "${OUTPUT_ATTRITION}" \
  "${OUTPUT_DROPPED_BY_STRICT}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Flexible panel:   ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:     ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC summary:       ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison: ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:         ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Main output dir:  ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "QC output dir:    ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:         ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e-build-jsts-matched-panel.sh,
# and run8e2-summarize-jsts-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2a-create-sonarqube-input.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2a: Create Python SonarQube scan inputs
# ============================================================
#
# Purpose:
#   Create treatment/control SonarQube scan input files from the
#   final Python matched DiD panels.
#
# Panel inputs:
#   flexible:
#     repo_python/run-py-1l/panel_event_matched_flexible.csv
#
#   strict:
#     repo_python/run-py-1l/panel_event_matched_strict.csv
#
# Full-run main outputs:
#   repo_python/run-py-2a/<variant>/treatment/data/ts_repos_monthly.csv
#   repo_python/run-py-2a/<variant>/control/data/ts_repos_monthly.csv
#
# Full-run extra outputs:
#   repo_python/tmp/run-py-2a/<variant>/months.txt
#   repo_python/tmp/run-py-2a/<variant>/treatment_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/control_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/sonarqube_input_summary.csv
#
# Smoke outputs:
#   repo_python/tmp/run-py-2a/smoke/<variant>/
#
# Usage:
#   Smoke:
#     PANEL_VARIANT=flexible MAX_TREATMENT_REPOS=2 MAX_CONTROL_REPOS=2 bash run-py-2a-create-sonarqube-input.sh
#     PANEL_VARIANT=strict   MAX_TREATMENT_REPOS=2 MAX_CONTROL_REPOS=2 bash run-py-2a-create-sonarqube-input.sh
#
#   Full:
#     PANEL_VARIANT=flexible MAX_TREATMENT_REPOS=0 MAX_CONTROL_REPOS=0 bash run-py-2a-create-sonarqube-input.sh
#     PANEL_VARIANT=strict   MAX_TREATMENT_REPOS=0 MAX_CONTROL_REPOS=0 bash run-py-2a-create-sonarqube-input.sh
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_sonarqube_input.py}"
HISTORY_SCRIPT="${HISTORY_SCRIPT:-proc_scripts/create_tmp_repo_timeseries_history.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

DID_DIR="${DID_DIR:-${OUTPUT_BASE_DIR}/run-py-1l}"
PANEL_VARIANT="${PANEL_VARIANT:-flexible}"

case "${PANEL_VARIANT}" in
  flexible)
    PANEL_FILE="${PANEL_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
    ;;
  strict)
    PANEL_FILE="${PANEL_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
    ;;
  *)
    echo "ERROR: unsupported PANEL_VARIANT=${PANEL_VARIANT}"
    echo "Supported values: flexible, strict"
    exit 1
    ;;
esac

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

MAX_TREATMENT_REPOS="${MAX_TREATMENT_REPOS:-0}"
MAX_CONTROL_REPOS="${MAX_CONTROL_REPOS:-0}"
ALLOW_MISSING_LATEST_COMMIT="${ALLOW_MISSING_LATEST_COMMIT:-false}"

if [[ "${MAX_TREATMENT_REPOS}" -gt 0 || "${MAX_CONTROL_REPOS}" -gt 0 ]]; then
  RUN_MODE="smoke"
  DEFAULT_SONAR_ROOT="${TMP_DIR}/smoke/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${DEFAULT_SONAR_ROOT}/meta"
else
  RUN_MODE="full"
  DEFAULT_SONAR_ROOT="${MAIN_OUTPUT_DIR}/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${TMP_DIR}/${PANEL_VARIANT}"
fi

SONAR_ROOT="${SONAR_ROOT:-${DEFAULT_SONAR_ROOT}}"
META_DIR="${META_DIR:-${DEFAULT_META_DIR}}"

TREATMENT_TS_FILE="${TREATMENT_TS_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_TS_FILE="${CONTROL_TS_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"

MONTHS_FILE="${MONTHS_FILE:-${META_DIR}/months.txt}"
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${META_DIR}/treatment_repos.txt}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${META_DIR}/control_repos.txt}"
SUMMARY_FILE="${SUMMARY_FILE:-${META_DIR}/sonarqube_input_summary.csv}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_sonarqube_input_${PANEL_VARIANT}_${RUN_TS}.log}"

mkdir -p \
  "${LOG_DIR}" \
  "${SONAR_ROOT}" \
  "${META_DIR}" \
  "$(dirname "${TREATMENT_TS_FILE}")" \
  "$(dirname "${CONTROL_TS_FILE}")"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: create Python SonarQube scan inputs"
  echo "Timestamp:                    ${RUN_TS}"
  echo "Script name:                  ${SCRIPT_NAME}"
  echo "Run prefix:                   ${RUN_PREFIX}"
  echo "Run mode:                     ${RUN_MODE}"
  echo "Panel variant:                ${PANEL_VARIANT}"
  echo "Python script:                ${PY_SCRIPT}"
  echo "History script:               ${HISTORY_SCRIPT}"
  echo "Panel file:                   ${PANEL_FILE}"
  echo "Sonar root:                   ${SONAR_ROOT}"
  echo "Metadata dir:                 ${META_DIR}"
  echo "Main output dir:              ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:             ${TMP_DIR}"
  echo "Treatment clone root:         ${TREATMENT_CLONE_ROOT}"
  echo "Control clone root:           ${CONTROL_CLONE_ROOT}"
  echo "Treatment output:             ${TREATMENT_TS_FILE}"
  echo "Control output:               ${CONTROL_TS_FILE}"
  echo "Months file:                  ${MONTHS_FILE}"
  echo "Treatment repos file:         ${TREATMENT_REPOS_FILE}"
  echo "Control repos file:           ${CONTROL_REPOS_FILE}"
  echo "Summary file:                 ${SUMMARY_FILE}"
  echo "Max treatment repos:          ${MAX_TREATMENT_REPOS}"
  echo "Max control repos:            ${MAX_CONTROL_REPOS}"
  echo "Allow missing latest_commit:  ${ALLOW_MISSING_LATEST_COMMIT}"
  echo "Log file:                     ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in "${PY_SCRIPT}" "${HISTORY_SCRIPT}" "${PANEL_FILE}"; do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      exit 1
    fi
  done

  for d in "${TREATMENT_CLONE_ROOT}" "${CONTROL_CLONE_ROOT}"; do
    if [[ ! -d "${d}" ]]; then
      echo "ERROR: required clone directory not found: ${d}"
      exit 1
    fi
  done

  echo "** Compile Python scripts"
  echo "------------------------------------------------------------"
  python -m py_compile "${PY_SCRIPT}"
  python -m py_compile "${HISTORY_SCRIPT}"
  echo

  echo "** Input panel summary"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

path = Path("${PANEL_FILE}")
df = pd.read_csv(path)

print("Panel file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

if "dataset_source" in df.columns:
    print()
    print("Rows by dataset_source:")
    print(df["dataset_source"].value_counts(dropna=False).to_string())

    print()
    print("Repos by dataset_source:")
    print(df.groupby("dataset_source")["repo_name"].nunique().to_string())

time_col = "time" if "time" in df.columns else "month" if "month" in df.columns else None
if time_col:
    print()
    print("Time range:", df[time_col].min(), "to", df[time_col].max())
PY
  echo

  CMD=(
    python "${PY_SCRIPT}"
    --panel-file "${PANEL_FILE}"
    --sonar-root "${SONAR_ROOT}"
    --treatment-clone-root "${TREATMENT_CLONE_ROOT}"
    --control-clone-root "${CONTROL_CLONE_ROOT}"
    --history-script "${HISTORY_SCRIPT}"
    --treatment-output "${TREATMENT_TS_FILE}"
    --control-output "${CONTROL_TS_FILE}"
    --months-file "${MONTHS_FILE}"
    --treatment-repos-file "${TREATMENT_REPOS_FILE}"
    --control-repos-file "${CONTROL_REPOS_FILE}"
    --summary-file "${SUMMARY_FILE}"
    --max-treatment-repos "${MAX_TREATMENT_REPOS}"
    --max-control-repos "${MAX_CONTROL_REPOS}"
  )

  if [[ "${ALLOW_MISSING_LATEST_COMMIT}" == "true" ]]; then
    CMD+=(--allow-missing-latest-commit)
  fi

  echo "** Running SonarQube input preparation"
  echo "------------------------------------------------------------"
  echo "${CMD[*]}"
  echo

  "${CMD[@]}"

  echo
  echo "** Output file check"
  echo "------------------------------------------------------------"
  for f in \
    "${TREATMENT_TS_FILE}" \
    "${CONTROL_TS_FILE}" \
    "${MONTHS_FILE}" \
    "${TREATMENT_REPOS_FILE}" \
    "${CONTROL_REPOS_FILE}" \
    "${SUMMARY_FILE}"
  do
    if [[ -f "${f}" ]]; then
      echo "Command: wc -l ${f}"
      wc -l "${f}"
    else
      echo "MISSING: ${f}"
    fi
  done

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Run mode:        ${RUN_MODE}"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Treatment input: ${TREATMENT_TS_FILE}"
  echo "Control input:   ${CONTROL_TS_FILE}"
  echo "Summary file:    ${SUMMARY_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:${TMP_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9a-create-jsts-sonarqube-input.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2b-sonarqube-scan.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b: Run SonarQube scan for Python repo-month inputs
# ============================================================
#
# Purpose:
#   Run SonarQube scans for Python treatment/control repo-month
#   input files generated by run-py-2a-create-sonarqube-input.sh.
#
# Inputs:
#   repo_python/run-py-2a/<variant>/<target>/data/ts_repos_monthly.csv
#
# Target:
#   TARGET=treatment
#   TARGET=control
#
# Main output:
#   repo_python/run-py-2b/<variant>/<target>/ts_repos_monthly_scanned.csv
#
# Reuse:
#   Copy a previously verified scanned CSV to the main output path,
#   then run with SKIP_SCAN=true to validate and reuse it.
#
# Usage:
#   Smoke or full depends on the input generated by run-py-2a.
#
#   PANEL_VARIANT=strict   TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=strict   TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=flexible TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=flexible TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# 
#   SKIP_SCAN=true PANEL_VARIANT=strict TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=strict TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=flexible TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=flexible TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# ============================================================

TARGET="${TARGET:-treatment}"
PANEL_VARIANT="${PANEL_VARIANT:-flexible}"
LANGUAGE_PROFILE="${LANGUAGE_PROFILE:-python}"
PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"
SKIP_SCAN="${SKIP_SCAN:-false}"

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

if [[ "${TARGET}" != "treatment" && "${TARGET}" != "control" ]]; then
  echo "ERROR: TARGET must be either 'treatment' or 'control'. Got: ${TARGET}"
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either 'flexible' or 'strict'. Got: ${PANEL_VARIANT}"
  exit 1
fi

if [[ "${SKIP_SCAN}" != "true" && "${SKIP_SCAN}" != "false" ]]; then
  echo "ERROR: SKIP_SCAN must be true or false. Got: ${SKIP_SCAN}"
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_sonarqube_${PANEL_VARIANT}_${TARGET}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/run_sonarqube_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
INPUT_ROOT="${INPUT_ROOT:-${OUTPUT_BASE_DIR}/run-py-2a/${PANEL_VARIANT}}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/${PANEL_VARIANT}/${TARGET}}"

NUM_PROCESSES="${NUM_PROCESSES:-1}"
AGGREGATION="${AGGREGATION:-month}"

INPUT_FILE="${INPUT_FILE:-${INPUT_ROOT}/${TARGET}/data/ts_repos_monthly.csv}"

if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_scanned_${OUTPUT_SUFFIX}.csv}"
else
  OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_scanned.csv}"
fi

if [[ "${TARGET}" == "treatment" ]]; then
  CLONE_DIR="${CLONE_DIR:-../treatment-repos}"
else
  CLONE_DIR="${CLONE_DIR:-../control-repos}"
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: Python SonarQube scan"
  echo "Started:         $(date)"
  echo "Script name:     ${SCRIPT_NAME}"
  echo "Run prefix:      ${RUN_PREFIX}"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Target:          ${TARGET}"
  echo "Python script:   ${PY_SCRIPT}"
  echo "Aggregation:     ${AGGREGATION}"
  echo "Input root:      ${INPUT_ROOT}"
  echo "Input file:      ${INPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "Clone dir:       ${CLONE_DIR}"
  echo "Language:        ${LANGUAGE_PROFILE}"
  echo "Project prefix:  ${PROJECT_KEY_PREFIX}"
  echo "Output suffix:   ${OUTPUT_SUFFIX}"
  echo "Skip scan:       ${SKIP_SCAN}"
  echo "Num processes:   ${NUM_PROCESSES}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${INPUT_FILE}" ]]; then
    echo "ERROR: input file not found: ${INPUT_FILE}"
    exit 1
  fi

  if [[ ! -d "${CLONE_DIR}" ]]; then
    echo "ERROR: clone dir not found: ${CLONE_DIR}"
    exit 1
  fi

  echo "** Compile Python script"
  echo "------------------------------------------------------------"
  python -m py_compile "${PY_SCRIPT}"
  echo

  echo "** Input summary before scan"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

path = Path("${INPUT_FILE}")
df = pd.read_csv(path)

required = {"repo_name", "month", "latest_commit"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"ERROR: missing required columns: {sorted(missing)}")

print("file:", path)
print("rows:", len(df))
print("repos:", df["repo_name"].nunique())
print("months:", df["month"].min(), "to", df["month"].max())
print("missing latest_commit:", df["latest_commit"].isna().sum())
print("duplicate repo-month rows:", df.duplicated(["repo_name", "month"]).sum())
PY

  echo
  if [[ "${SKIP_SCAN}" == "true" ]]; then
    echo "** Validate and reuse existing scanned output"
    echo "------------------------------------------------------------"

    if [[ ! -f "${OUTPUT_FILE}" ]]; then
      echo "ERROR: SKIP_SCAN=true but output file not found: ${OUTPUT_FILE}"
      exit 1
    fi

    python - <<PY
import pandas as pd
from pathlib import Path

input_path = Path("${INPUT_FILE}")
output_path = Path("${OUTPUT_FILE}")

input_df = pd.read_csv(input_path)
output_df = pd.read_csv(output_path)

repo_month_cols = ["repo_name", "month"]
match_cols = ["repo_name", "month", "latest_commit"]
required_input = set(match_cols)
missing_input_cols = required_input - set(input_df.columns)
if missing_input_cols:
    raise SystemExit(
        f"ERROR: input missing required columns: {sorted(missing_input_cols)}"
    )

missing_output_cols = set(match_cols) - set(output_df.columns)
if missing_output_cols:
    raise SystemExit(
        f"ERROR: reused output missing matching columns: {sorted(missing_output_cols)}"
    )

metric_candidates = {
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "software_quality_maintainability_remediation_effort",
}

if not metric_candidates.intersection(output_df.columns):
    raise SystemExit("ERROR: reused output contains no SonarQube metric columns.")

input_keys = input_df[match_cols].drop_duplicates()
output_keys = output_df[match_cols].drop_duplicates()

missing_keys = (
    input_keys.merge(output_keys, on=match_cols, how="left", indicator=True)
    .query("_merge == 'left_only'")
)
extra_keys = (
    output_keys.merge(input_keys, on=match_cols, how="left", indicator=True)
    .query("_merge == 'left_only'")
)

duplicate_output_keys = int(output_df.duplicated(repo_month_cols).sum())

print("Input rows:", len(input_df))
print("Output rows:", len(output_df))
print("Input unique repo-month-commit keys:", len(input_keys))
print("Output unique repo-month-commit keys:", len(output_keys))
print("Missing input repo-month-commit keys in output:", len(missing_keys))
print("Extra output repo-month-commit keys:", len(extra_keys))
print("Duplicate output repo-month rows:", duplicate_output_keys)

if len(missing_keys) > 0 or len(extra_keys) > 0 or duplicate_output_keys > 0:
    raise SystemExit(
        "ERROR: reused output does not exactly match the current repo-month-commit input."
    )

print("Existing scanned output is complete for the current input.")
PY

  else
    # Load SonarQube configuration only when an actual scan/API run is needed.
    if [[ -f ".env" ]]; then
      set -a
      source ".env"
      set +a
    fi

    if [[ -z "${SONAR_PATH:-}" && -n "${SONAR_SCANNER_PATH:-}" ]]; then
      export SONAR_PATH="${SONAR_SCANNER_PATH}"
    fi

    if [[ -n "${SONAR_PATH:-}" && -d "${SONAR_PATH}" && -x "${SONAR_PATH}/bin/sonar-scanner" ]]; then
      export SONAR_PATH="${SONAR_PATH}/bin/sonar-scanner"
    fi

    if [[ -z "${SONAR_PATH:-}" ]]; then
      echo "ERROR: SONAR_PATH is not set."
      exit 1
    fi

    if [[ -z "${SONAR_TOKEN:-}" ]]; then
      echo "ERROR: SONAR_TOKEN is not set."
      exit 1
    fi

    if [[ ! -x "${SONAR_PATH}" ]]; then
      echo "ERROR: SONAR_PATH is not executable: ${SONAR_PATH}"
      exit 1
    fi

    export SONAR_PATH
    export SONAR_SCANNER_PATH="${SONAR_PATH}"

    echo "Sonar scanner: ${SONAR_PATH}"
    echo "Sonar token:   set"
    echo
    echo "** Running SonarQube scanner"
    echo "------------------------------------------------------------"

    CMD=(
      python "${PY_SCRIPT}"
      --aggregation "${AGGREGATION}"
      --input-file "${INPUT_FILE}"
      --output-file "${OUTPUT_FILE}"
      --clone-dir "${CLONE_DIR}"
      --num-processes "${NUM_PROCESSES}"
      --language-profile "${LANGUAGE_PROFILE}"
      --project-key-prefix "${PROJECT_KEY_PREFIX}"
      --incremental-save
    )

    echo "${CMD[*]}"
    echo
    "${CMD[@]}"
  fi

  echo
  echo "** Output metric coverage"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

path = Path("${OUTPUT_FILE}")
if not path.exists():
    raise SystemExit(f"Missing output file: {path}")

df = pd.read_csv(path)

metric_cols = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]

print("file:", path)
print("rows:", len(df))
print("repos:", df["repo_name"].nunique())
print("months:", df["month"].min(), "to", df["month"].max())
print("missing latest_commit:", df["latest_commit"].isna().sum())
print("duplicate repo-month rows:", df.duplicated(["repo_name", "month"]).sum())
print()

for col in metric_cols:
    if col in df.columns:
        print(f"{col}: {df[col].notna().sum()} / {len(df)} non-null")
    else:
        print(f"{col}: MISSING")
PY

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:       $(date)"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Target:          ${TARGET}"
  echo "Skip scan:       ${SKIP_SCAN}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9b-sonarqube-jsts.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2c-merge-sonarqube-panel.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2c: Merge Python SonarQube metrics into matched DiD panels
# ============================================================
#
# Purpose:
#   Merge treatment/control SonarQube metrics generated by run-py-2b
#   into the final Python matched event panels generated by run-py-1l.
#
# Inputs:
#   repo_python/run-py-1l/panel_event_matched_<variant>.csv
#   repo_python/run-py-2b/<variant>/treatment/ts_repos_monthly_scanned.csv
#   repo_python/run-py-2b/<variant>/control/ts_repos_monthly_scanned.csv
#
# Main output:
#   repo_python/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube.csv
#
# Extra QC output:
#   repo_python/tmp/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube_qc.csv
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2c-merge-sonarqube-panel.sh
#   PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either flexible or strict. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_merge_sonarqube_panel_${PANEL_VARIANT}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/merge_sonarqube_panel_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1l}"
SONAR_ROOT="${SONAR_ROOT:-${OUTPUT_BASE_DIR}/run-py-2b/${PANEL_VARIANT}}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/${PANEL_VARIANT}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}/${PANEL_VARIANT}}"

PANEL_FILE="${PANEL_FILE:-${PANEL_INPUT_DIR}/panel_event_matched_${PANEL_VARIANT}.csv}"

TREATMENT_METRICS="${TREATMENT_METRICS:-${SONAR_ROOT}/treatment/ts_repos_monthly_scanned.csv}"
CONTROL_METRICS="${CONTROL_METRICS:-${SONAR_ROOT}/control/ts_repos_monthly_scanned.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube.csv}"
QC_OUTPUT_FILE="${QC_OUTPUT_FILE:-${TMP_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube_qc.csv}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: merge Python SonarQube metrics into matched panel"
  echo "Started:           $(date)"
  echo "Script name:       ${SCRIPT_NAME}"
  echo "Run prefix:        ${RUN_PREFIX}"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Python script:     ${PY_SCRIPT}"
  echo "Panel input dir:   ${PANEL_INPUT_DIR}"
  echo "Sonar root:        ${SONAR_ROOT}"
  echo "Main output dir:   ${MAIN_OUTPUT_DIR}"
  echo "Extra QC dir:      ${TMP_DIR}"
  echo "Panel file:        ${PANEL_FILE}"
  echo "Treatment metrics: ${TREATMENT_METRICS}"
  echo "Control metrics:   ${CONTROL_METRICS}"
  echo "Output file:       ${OUTPUT_FILE}"
  echo "QC output file:    ${QC_OUTPUT_FILE}"
  echo "Log file:          ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in "${PY_SCRIPT}" "${PANEL_FILE}" "${TREATMENT_METRICS}" "${CONTROL_METRICS}"; do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      echo
      echo "Make sure run-py-1l and both run-py-2b scans are complete"
      echo "for PANEL_VARIANT=${PANEL_VARIANT}."
      exit 1
    fi
  done

  echo "** Compile Python script"
  echo "------------------------------------------------------------"
  python -m py_compile "${PY_SCRIPT}"
  echo

  echo "** Input file summary before merge"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

panel_path = Path("${PANEL_FILE}")
treat_path = Path("${TREATMENT_METRICS}")
control_path = Path("${CONTROL_METRICS}")

panel = pd.read_csv(panel_path)
treat = pd.read_csv(treat_path)
control = pd.read_csv(control_path)

print("Panel:", panel_path)
print("  rows:", len(panel))
print("  repos:", panel["repo_name"].nunique())
print("  sources:")
print(panel["dataset_source"].value_counts(dropna=False).to_string())
print()

for label, df, path in [
    ("treatment_metrics", treat, treat_path),
    ("control_metrics", control, control_path),
]:
    print(label + ":", path)
    print("  rows:", len(df))
    print("  repos:", df["repo_name"].nunique())
    print("  months:", df["month"].min(), "to", df["month"].max())
    print("  missing latest_commit:", df["latest_commit"].isna().sum())
    print("  duplicate repo-month rows:", df.duplicated(["repo_name", "month"]).sum())
    print()
PY

  echo "** Merge SonarQube metrics"
  echo "------------------------------------------------------------"
  python "${PY_SCRIPT}" \
    --panel "${PANEL_FILE}" \
    --treatment-metrics "${TREATMENT_METRICS}" \
    --control-metrics "${CONTROL_METRICS}" \
    --output "${OUTPUT_FILE}" \
    --qc-output "${QC_OUTPUT_FILE}"

  echo
  echo "** Add Python run-py-2c QC flags"
  echo "------------------------------------------------------------"

  python - <<PY
import pandas as pd
from pathlib import Path

output = Path("${OUTPUT_FILE}")
qc_output = Path("${QC_OUTPUT_FILE}")
panel_variant = "${PANEL_VARIANT}"

df = pd.read_csv(output)

raw_metric_cols = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

required = {"repo_name", "time", "dataset_source"} | set(raw_metric_cols)
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns in merged output: {sorted(missing)}")

df["sonarqube_all_raw_metrics_missing"] = df[raw_metric_cols].isna().all(axis=1).astype(int)

df["sonarqube_ncloc_zero"] = (
    df["ncloc_raw"].notna() & (df["ncloc_raw"] == 0)
).astype(int)

df["sonarqube_static_warnings_missing"] = (
    df[["bugs_raw", "vulnerabilities_raw", "code_smells_raw"]].isna().any(axis=1)
).astype(int)

df["sonarqube_duplicate_density_missing"] = df["duplicated_lines_density_raw"].isna().astype(int)
df["sonarqube_cognitive_complexity_missing"] = df["cognitive_complexity_raw"].isna().astype(int)

df["sonarqube_quality_outcomes_complete"] = (
    (df["sonarqube_static_warnings_missing"] == 0)
    & (df["sonarqube_duplicate_density_missing"] == 0)
    & (df["sonarqube_cognitive_complexity_missing"] == 0)
).astype(int)

df.to_csv(output, index=False)

qc = pd.read_csv(qc_output)

new_checks = pd.DataFrame([
    {"check": "run_py_2c_panel_variant", "value": panel_variant},
    {"check": "run_py_2c_rows", "value": len(df)},
    {"check": "run_py_2c_repos", "value": df["repo_name"].nunique()},
    {"check": "run_py_2c_treatment_rows", "value": int((df["dataset_source"] == "treatment").sum())},
    {"check": "run_py_2c_control_rows", "value": int((df["dataset_source"] == "control").sum())},
    {"check": "run_py_2c_treatment_repos", "value": df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique()},
    {"check": "run_py_2c_control_repos", "value": df.loc[df["dataset_source"] == "control", "repo_name"].nunique()},
    {"check": "run_py_2c_sonarqube_all_raw_metrics_missing_rows", "value": int(df["sonarqube_all_raw_metrics_missing"].sum())},
    {"check": "run_py_2c_sonarqube_ncloc_zero_rows", "value": int(df["sonarqube_ncloc_zero"].sum())},
    {"check": "run_py_2c_static_warnings_missing_rows", "value": int(df["sonarqube_static_warnings_missing"].sum())},
    {"check": "run_py_2c_duplicate_density_missing_rows", "value": int(df["sonarqube_duplicate_density_missing"].sum())},
    {"check": "run_py_2c_cognitive_complexity_missing_rows", "value": int(df["sonarqube_cognitive_complexity_missing"].sum())},
    {"check": "run_py_2c_quality_outcomes_complete_rows", "value": int(df["sonarqube_quality_outcomes_complete"].sum())},
])

qc = qc[~qc["check"].isin(new_checks["check"])]
qc = pd.concat([qc, new_checks], ignore_index=True)
qc.to_csv(qc_output, index=False)

print("Updated output:", output)
print("Updated QC:", qc_output)
print()
print(new_checks.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:       $(date)"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "QC output file:  ${QC_OUTPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Extra QC dir:    ${TMP_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9c-merge-sonarqube-panel.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2d-check-sonarqube-panels.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2d: Check Python merged SonarQube matched panels
# ============================================================
#
# Purpose:
#   Check merged Python SonarQube panels created by run-py-2c.
#
# Inputs:
#   strict:
#     repo_python/run-py-2c/strict/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/run-py-2c/flexible/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=all bash run-py-2d-check-sonarqube-panels.sh
#
# Persistent output:
#   logs/run-py-2d_check_sonarqube_panels_<variant>_<timestamp>.log
#
# Temporary outputs:
#   check_sonarqube_panel.py requires summary and missing-row files.
#   They are created under repo_python/tmp/run-py-2d during validation
#   and removed automatically when the wrapper exits.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_check_sonarqube_panels_${PANEL_VARIANT}_${RUN_TS}.log}"

CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
TMP_PARENT_DIR="${TMP_PARENT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
TMP_WORK_DIR="${TMP_WORK_DIR:-${TMP_PARENT_DIR}/${PANEL_VARIANT}_${RUN_TS}}"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube.csv")
fi

cleanup_tmp_work_dir() {
  rm -rf "${TMP_WORK_DIR}"
  rmdir "${TMP_PARENT_DIR}" 2>/dev/null || true
}
trap cleanup_tmp_work_dir EXIT

mkdir -p "${LOG_DIR}" "${TMP_WORK_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: check Python merged SonarQube panels"
  echo "Started:          $(date)"
  echo "Script name:      ${SCRIPT_NAME}"
  echo "Run prefix:       ${RUN_PREFIX}"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "Panel input dir:  ${PANEL_INPUT_DIR}"
  echo "Temporary dir:    ${TMP_WORK_DIR}"
  echo "Persistent files: log only"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${CHECK_SCRIPT}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "Complete run-py-2c first for PANEL_VARIANT=${PANEL_LABEL}."
      exit 1
    fi

    SUMMARY_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_check_summary.csv"
    MISSING_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_missing_analysis_outcomes.csv"

    echo
    echo "============================================================"
    echo "Checking panel: ${PANEL_LABEL}"
    echo "Input:          ${INPUT_FILE}"
    echo "Temporary summary: ${SUMMARY_OUTPUT}"
    echo "Temporary missing: ${MISSING_OUTPUT}"
    echo "============================================================"

    python "${CHECK_SCRIPT}" \
      --input "${INPUT_FILE}" \
      --summary-output "${SUMMARY_OUTPUT}" \
      --missing-output "${MISSING_OUTPUT}"

    echo
    echo "Validation completed for ${PANEL_LABEL}."
    echo "Temporary checker outputs will be removed when the wrapper exits."
  done

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:         $(date)"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Persistent output: ${LOG_FILE}"
  echo "Temporary outputs: removed automatically"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9d-check-sonarqube-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2e-prepare-quality-did-input.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2e: Prepare Python quality DiD input
# ============================================================
# Purpose:
#   Convert merged Python SonarQube panels into quality DiD inputs.
#   Optionally create a paper-schema diagnostic output without calling
#   compare/run-py-2b15-create-paper-structure-panel.sh.
#
# Input:
#   repo_python/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube.csv
#
# Main output for the strict paper-overlap run:
#   repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv
#
# Main output for flexible or non-paper runs:
#   repo_python/run-py-2e/<variant>/
#     panel_event_matched_<variant>_with_sonarqube_quality_did_input_complete.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-2e/<variant>/quality_did_input_qc.csv
#   repo_python/tmp/run-py-2e/<variant>/paper_audit/
#
# Temporary outputs:
#   Full inputs, missing-row outputs, manifest, and combined QC files are
#   created under a timestamped work directory and removed after success.
#
# Paper-comparable strict run:
#   PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE
#
# Important:
#   The paper-schema output preserves regenerated Python SonarQube metrics.
#   Selected unavailable covariates are filled from the frozen paper panel
#   only on exact repo-month matches.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Usage:
  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh [options]

Options:
  --convert-paper-same-column TRUE|FALSE
  --keep-overlap-paper-same-column TRUE|FALSE
  --paper-panel-file PATH
  --paper-audit-dir PATH
  --fill-from-paper-columns CSV_LIST
  --metric-compare-columns CSV_LIST
  --top-print INTEGER
  --help
EOF
}

normalize_bool() {
  local value
  value="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
  case "${value}" in
    TRUE|FALSE)
      printf '%s' "${value}"
      ;;
    *)
      echo "ERROR: expected TRUE or FALSE, got: $1" >&2
      exit 1
      ;;
  esac
}

require_option_value() {
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "${option_value}" ]]; then
    echo "ERROR: ${option_name} requires a value." >&2
    exit 1
  fi
}

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
WORK_ROOT="${WORK_ROOT:-${TMP_DIR}/work_${RUN_TS}}"

CONVERT_PAPER_SAME_COLUMN="${CONVERT_PAPER_SAME_COLUMN:-FALSE}"
KEEP_OVERLAP_PAPER_SAME_COLUMN="${KEEP_OVERLAP_PAPER_SAME_COLUMN:-FALSE}"
PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-data/panel_event_monthly.csv}"
PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR:-${TMP_DIR}}"
FILL_FROM_PAPER_COLUMNS="${FILL_FROM_PAPER_COLUMNS:-stars,issues,issue_comments,age,num_dependencies_total,num_vulnerable_dependencies,average_technical_lag,other_agents,high_confidence}"
METRIC_COMPARE_COLUMNS="${METRIC_COMPARE_COLUMNS:-ncloc,bugs,vulnerabilities,code_smells,duplicated_lines_density,comment_lines_density,cognitive_complexity,technical_debt}"
TOP_PRINT="${TOP_PRINT:-20}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --convert-paper-same-column)
      require_option_value "$1" "${2:-}"
      CONVERT_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --keep-overlap-paper-same-column)
      require_option_value "$1" "${2:-}"
      KEEP_OVERLAP_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --paper-panel-file)
      require_option_value "$1" "${2:-}"
      PAPER_PANEL_FILE="$2"
      shift 2
      ;;
    --paper-audit-dir)
      require_option_value "$1" "${2:-}"
      PAPER_AUDIT_DIR="$2"
      shift 2
      ;;
    --fill-from-paper-columns)
      require_option_value "$1" "${2:-}"
      FILL_FROM_PAPER_COLUMNS="$2"
      shift 2
      ;;
    --metric-compare-columns)
      require_option_value "$1" "${2:-}"
      METRIC_COMPARE_COLUMNS="$2"
      shift 2
      ;;
    --top-print)
      require_option_value "$1" "${2:-}"
      TOP_PRINT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

CONVERT_PAPER_SAME_COLUMN="$(normalize_bool "${CONVERT_PAPER_SAME_COLUMN}")"
KEEP_OVERLAP_PAPER_SAME_COLUMN="$(normalize_bool "${KEEP_OVERLAP_PAPER_SAME_COLUMN}")"

if [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" && "${CONVERT_PAPER_SAME_COLUMN}" != "TRUE" ]]; then
  echo "ERROR: --keep-overlap-paper-same-column TRUE requires --convert-paper-same-column TRUE."
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

if ! [[ "${TOP_PRINT}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --top-print must be a non-negative integer. Got: ${TOP_PRINT}"
  exit 1
fi

if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && ! -f "${PAPER_PANEL_FILE}" ]]; then
  echo "ERROR: paper panel file not found: ${PAPER_PANEL_FILE}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_prepare_quality_did_input_${PANEL_VARIANT}_${RUN_TS}.log}"
MANIFEST_FILE="${WORK_ROOT}/quality_did_input_manifest_${PANEL_VARIANT}.csv"
COMBINED_QC_LONG="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}_long.csv"
COMBINED_QC_WIDE="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}_wide.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube.csv")
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}" "${WORK_ROOT}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: prepare Python quality DiD input"
  echo "Started:                           $(date)"
  echo "Script name:                       ${SCRIPT_NAME}"
  echo "Run prefix:                        ${RUN_PREFIX}"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Python script:                     ${PY_SCRIPT}"
  echo "Panel input dir:                   ${PANEL_INPUT_DIR}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Paper panel file:                  ${PAPER_PANEL_FILE}"
  echo "Paper audit root:                   ${PAPER_AUDIT_DIR}"
  echo "Fill from paper columns:           ${FILL_FROM_PAPER_COLUMNS}"
  echo "Metric compare columns:            ${METRIC_COMPARE_COLUMNS}"
  echo "Top print:                         ${TOP_PRINT}"
  echo "Temporary manifest:                ${MANIFEST_FILE}"
  echo "Temporary combined QC long:        ${COMBINED_QC_LONG}"
  echo "Temporary combined QC wide:        ${COMBINED_QC_WIDE}"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  echo "panel,input,output,complete_output,qc_output,missing_output,paper_same_column_output,paper_key_summary,paper_unmatched_output" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input merged SonarQube panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control SonarQube scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      echo "  3. PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh"
      exit 1
    fi

    PANEL_MAIN_DIR="${MAIN_OUTPUT_DIR}/${PANEL_LABEL}"
    PANEL_TMP_DIR="${TMP_DIR}/${PANEL_LABEL}"
    PANEL_WORK_DIR="${WORK_ROOT}/${PANEL_LABEL}"
    CURRENT_PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR}/${PANEL_LABEL}/paper_audit"

    mkdir -p "${PANEL_MAIN_DIR}" "${PANEL_TMP_DIR}" "${PANEL_WORK_DIR}" "${CURRENT_PAPER_AUDIT_DIR}"

    OUTPUT_FILE="${PANEL_WORK_DIR}/quality_did_input_full.csv"
    MISSING_OUTPUT_FILE="${PANEL_WORK_DIR}/missing_core_quality.csv"
    QC_OUTPUT_FILE="${PANEL_TMP_DIR}/quality_did_input_qc.csv"

    if [[ "${PANEL_LABEL}" == "strict" && "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      COMPLETE_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv"
    else
      COMPLETE_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_matched_${PANEL_LABEL}_with_sonarqube_quality_did_input_complete.csv"
    fi

    PAPER_SAME_COLUMN_OUTPUT_FILE=""
    PAPER_KEY_SUMMARY_FILE=""
    PAPER_UNMATCHED_OUTPUT_FILE=""

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      if [[ "${PANEL_LABEL}" == "strict" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_monthly_quality_py.csv"
      elif [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}.csv"
      else
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}_with_unmatched.csv"
      fi
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      PAPER_KEY_SUMMARY_FILE="${PAPER_AUDIT_BASE}_key_match_summary.csv"
      PAPER_UNMATCHED_OUTPUT_FILE="${PAPER_AUDIT_BASE}_unmatched_repo_months.csv"
    fi

    echo
    echo "============================================================"
    echo "Preparing quality DiD input for panel: ${PANEL_LABEL}"
    echo "Input:                         ${INPUT_FILE}"
    echo "Output:                        ${OUTPUT_FILE}"
    echo "Complete output:               ${COMPLETE_OUTPUT_FILE}"
    echo "QC output:                     ${QC_OUTPUT_FILE}"
    echo "Missing output:                ${MISSING_OUTPUT_FILE}"
    echo "Paper same-column output:      ${PAPER_SAME_COLUMN_OUTPUT_FILE:-<disabled>}"
    echo "Paper audit directory:         ${CURRENT_PAPER_AUDIT_DIR}"
    echo "Paper overlap-only:            ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
    echo "============================================================"

    PY_ARGS=(
      --panel-label "${PANEL_LABEL}"
      --input "${INPUT_FILE}"
      --output "${OUTPUT_FILE}"
      --complete-output "${COMPLETE_OUTPUT_FILE}"
      --qc-output "${QC_OUTPUT_FILE}"
      --missing-output "${MISSING_OUTPUT_FILE}"
      --convert-paper-same-column "${CONVERT_PAPER_SAME_COLUMN}"
      --keep-overlap-paper-same-column "${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
      --paper-panel-file "${PAPER_PANEL_FILE}"
      --paper-audit-dir "${CURRENT_PAPER_AUDIT_DIR}"
      --fill-from-paper-columns "${FILL_FROM_PAPER_COLUMNS}"
      --metric-compare-columns "${METRIC_COMPARE_COLUMNS}"
      --top-print "${TOP_PRINT}"
    )

    if [[ -n "${PAPER_SAME_COLUMN_OUTPUT_FILE}" ]]; then
      PY_ARGS+=(--paper-same-column-output "${PAPER_SAME_COLUMN_OUTPUT_FILE}")
    fi

    python "${PY_SCRIPT}" "${PY_ARGS[@]}"

    for expected_file in \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}"; do
      if [[ ! -f "${expected_file}" ]]; then
        echo "ERROR: missing expected output: ${expected_file}"
        exit 1
      fi
    done

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      for expected_file in \
        "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
        "${PAPER_AUDIT_BASE}_column_sources.csv" \
        "${PAPER_AUDIT_BASE}_key_match_summary.csv" \
        "${PAPER_AUDIT_BASE}_metric_comparison.csv" \
        "${PAPER_AUDIT_BASE}_unmatched_repo_months.csv" \
        "${PAPER_AUDIT_BASE}_notes.md"; do
        if [[ ! -f "${expected_file}" ]]; then
          echo "ERROR: missing expected paper-schema output: ${expected_file}"
          exit 1
        fi
      done

      echo "Paper-schema key match summary:"
      cat "${PAPER_KEY_SUMMARY_FILE}"
      rm -f "${PAPER_AUDIT_BASE}_notes.md"
    fi

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}" \
      "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
      "${PAPER_KEY_SUMMARY_FILE}" \
      "${PAPER_UNMATCHED_OUTPUT_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined quality DiD input QC"
  echo "------------------------------------------------------------"

  python - <<PY
from pathlib import Path
import pandas as pd

manifest_path = Path("${MANIFEST_FILE}")
combined_long_path = Path("${COMBINED_QC_LONG}")
combined_wide_path = Path("${COMBINED_QC_WIDE}")

manifest = pd.read_csv(manifest_path).fillna("")

qc_frames = []
wide_rows = []

def read_csv_if_possible(path_value):
    if not path_value:
        return pd.DataFrame()
    path = Path(path_value)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    qc = read_csv_if_possible(row["qc_output"])
    if not qc.empty:
        qc.insert(0, "panel", panel)
        qc_frames.append(qc)

    output_df = read_csv_if_possible(row["output"])
    complete_df = read_csv_if_possible(row["complete_output"])
    missing_df = read_csv_if_possible(row["missing_output"])
    paper_df = read_csv_if_possible(row["paper_same_column_output"])
    paper_key_summary = read_csv_if_possible(row["paper_key_summary"])

    wide_row = {
        "panel": panel,
        "output_file": row["output"],
        "complete_output_file": row["complete_output"],
        "missing_output_file": row["missing_output"],
        "paper_same_column_output_file": row["paper_same_column_output"],
        "output_rows": len(output_df),
        "complete_rows": len(complete_df),
        "missing_core_quality_rows": len(missing_df),
        "paper_same_column_output_rows": len(paper_df) if row["paper_same_column_output"] else None,
        "output_repos": output_df["repo_name"].nunique() if "repo_name" in output_df.columns else None,
        "complete_repos": complete_df["repo_name"].nunique() if "repo_name" in complete_df.columns else None,
        "paper_same_column_repos": paper_df["repo_name"].nunique() if "repo_name" in paper_df.columns else None,
    }

    if not paper_key_summary.empty:
        summary = paper_key_summary.iloc[0]
        wide_row.update({
            "paper_repo_month_rows_matched": summary.get("repo_month_rows_matched_to_paper"),
            "paper_repo_month_rows_unmatched": summary.get("repo_month_rows_not_matched_to_paper"),
            "keep_overlap_paper_same_column": summary.get("keep_overlap_paper_same_column"),
            "paper_duplicate_repo_month_rows": summary.get("paper_duplicate_repo_month_rows"),
        })
    else:
        wide_row.update({
            "paper_repo_month_rows_matched": None,
            "paper_repo_month_rows_unmatched": None,
            "keep_overlap_paper_same_column": None,
            "paper_duplicate_repo_month_rows": None,
        })

    wide_rows.append(wide_row)

combined_long = pd.concat(qc_frames, ignore_index=True) if qc_frames else pd.DataFrame()
combined_wide = pd.DataFrame(wide_rows)

combined_long_path.parent.mkdir(parents=True, exist_ok=True)
combined_wide_path.parent.mkdir(parents=True, exist_ok=True)

combined_long.to_csv(combined_long_path, index=False)
combined_wide.to_csv(combined_wide_path, index=False)

print("Saved combined QC long:", combined_long_path)
print("Saved combined QC wide:", combined_wide_path)
print()
print("Combined QC wide:")
print(combined_wide.to_string(index=False))
PY

  rm -rf "${WORK_ROOT}"

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:                         $(date)"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Temporary work files:              removed"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

# This wrapper reuses the logic of the previous run-py-2e and run-py-2b15
# workflows without directly calling either existing wrapper.


###############################################################################
# FILE: run-py-2f1-did-borusyak-quality.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd')"
Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd', params = list(panel_file = '../repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv'))"


###############################################################################
# FILE: run-py-2f-did-borusyak-quality.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2f: Borusyak DiD for Python SonarQube quality outcomes
# ============================================================
# Purpose:
#   Run Borusyak DiD estimation for Python quality outcomes.
#
# Inputs:
#   strict:
#     repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv
#
#   flexible:
#     repo_python/run-py-2e/flexible/
#       panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv
#
# Main presentation outputs:
#   repo_python/run-py-2f/<variant>/DiffInDiffBorusyak_quality_python_v2.html
#   repo_python/run-py-2f/<variant>/dynamic_effects_borusyak_quality_python_v2.pdf
#
# Extra analysis outputs:
#   repo_python/tmp/run-py-2f/<variant>/
#
# Temporary combined outputs:
#   repo_python/tmp/run-py-2f/work_<timestamp>/
#   Removed automatically after a successful run.
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
#
# Notes:
#   This wrapper reuses the analysis flow of the existing run-py-2f
#   implementation, but it is independent and does not call another wrapper.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_did_borusyak_quality_${PANEL_VARIANT}_${RUN_TS}.log}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_ROOT="${MAIN_OUTPUT_ROOT:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_ROOT="${TMP_ROOT:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
WORK_DIR="${WORK_DIR:-${TMP_ROOT}/work_${RUN_TS}}"
PROC_R_DIR="${PROC_R_DIR:-proc_r}"

RMD_FILE="${RMD_FILE:-${PROC_R_DIR}/DiffInDiffBorusyak_quality_python_v2.Rmd}"
HELPER_FILE="${HELPER_FILE:-${PROC_R_DIR}/diff_in_diff_borusyak_helpers.R}"
OUT_ROOT="${OUT_ROOT:-${TMP_ROOT}}"

STRICT_PANEL_FILE="${STRICT_PANEL_FILE:-${OUTPUT_BASE_DIR}/run-py-2e/strict/panel_event_monthly_quality_py.csv}"
FLEXIBLE_PANEL_FILE="${FLEXIBLE_PANEL_FILE:-${OUTPUT_BASE_DIR}/run-py-2e/flexible/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv}"

STRICT_HTML_FILE="${STRICT_HTML_FILE:-${MAIN_OUTPUT_ROOT}/strict/DiffInDiffBorusyak_quality_python_v2.html}"
STRICT_PDF_FILE="${STRICT_PDF_FILE:-${MAIN_OUTPUT_ROOT}/strict/dynamic_effects_borusyak_quality_python_v2.pdf}"
FLEXIBLE_HTML_FILE="${FLEXIBLE_HTML_FILE:-${MAIN_OUTPUT_ROOT}/flexible/DiffInDiffBorusyak_quality_python_v2.html}"
FLEXIBLE_PDF_FILE="${FLEXIBLE_PDF_FILE:-${MAIN_OUTPUT_ROOT}/flexible/dynamic_effects_borusyak_quality_python_v2.pdf}"

MANIFEST_FILE="${WORK_DIR}/borusyak_quality_manifest_${PANEL_VARIANT}.csv"
COMBINED_STATIC="${WORK_DIR}/borusyak_quality_static_effects_${PANEL_VARIANT}.csv"
COMBINED_DYNAMIC="${WORK_DIR}/borusyak_quality_dynamic_effects_${PANEL_VARIANT}.csv"
COMBINED_CHECKS="${WORK_DIR}/borusyak_quality_panel_checks_${PANEL_VARIANT}.csv"
COMBINED_INPUT_SUMMARY="${WORK_DIR}/borusyak_quality_input_summary_${PANEL_VARIANT}.csv"
COMBINED_ERRORS="${WORK_DIR}/borusyak_quality_errors_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${STRICT_PANEL_FILE}")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${FLEXIBLE_PANEL_FILE}")
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_ROOT}" "${TMP_ROOT}" "${WORK_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: Python Borusyak DiD for SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "Script name:            ${SCRIPT_NAME}"
  echo "Run prefix:             ${RUN_PREFIX}"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Project root:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "Helper file:            ${HELPER_FILE}"
  echo "Strict input:           ${STRICT_PANEL_FILE}"
  echo "Flexible input:         ${FLEXIBLE_PANEL_FILE}"
  echo "Main output root:       ${MAIN_OUTPUT_ROOT}"
  echo "Extra output root:      ${TMP_ROOT}"
  echo "Temporary work dir:     ${WORK_DIR}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD_FILE}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD_FILE}"
    exit 1
  fi

  if [[ ! -f "${HELPER_FILE}" ]]; then
    echo "ERROR: Helper file not found: ${HELPER_FILE}"
    exit 1
  fi

  if ! command -v Rscript >/dev/null 2>&1; then
    echo "ERROR: Rscript was not found in PATH."
    exit 1
  fi

  echo "panel,input,out_dir,html,pdf,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      if [[ "${PANEL_LABEL}" == "strict" ]]; then
        echo "Create the strict paper-schema input first:"
        echo "  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE"
      else
        echo "Create the flexible complete-case quality input first."
      fi
      exit 1
    fi

    rm -rf "${PANEL_OUT_DIR}"
    mkdir -p "${PANEL_OUT_DIR}"

    GENERATED_PDF_FILE="${PANEL_OUT_DIR}/dynamic_effects_borusyak_quality.pdf"
    STATIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv"
    DYNAMIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv"
    CHECKS_FILE="${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv"
    INPUT_SUMMARY_FILE="${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv"
    METADATA_FILE="${PANEL_OUT_DIR}/borusyak_quality_metadata.csv"
    GENERATED_STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv"
    GENERATED_DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv"

    rm -f \
      "${GENERATED_PDF_FILE}" \
      "${GENERATED_STATIC_ERRORS_FILE}" \
      "${GENERATED_DYNAMIC_ERRORS_FILE}"

    if [[ "${PANEL_LABEL}" == "strict" ]]; then
      HTML_FILE="${STRICT_HTML_FILE}"
      PDF_FILE="${STRICT_PDF_FILE}"
      RENDER_OUTPUT_DIR="$(dirname "${HTML_FILE}")"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors_${RUN_TS}.csv"
    else
      HTML_FILE="${FLEXIBLE_HTML_FILE}"
      PDF_FILE="${FLEXIBLE_PDF_FILE}"
      RENDER_OUTPUT_DIR="$(dirname "${HTML_FILE}")"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors_${RUN_TS}.csv"
    fi

    mkdir -p "${RENDER_OUTPUT_DIR}" "$(dirname "${PDF_FILE}")"
    rm -f "${HTML_FILE}" "${PDF_FILE}" "${STATIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"

    echo
    echo "============================================================"
    echo "Running panel: ${PANEL_LABEL}"
    echo "Input:         ${INPUT_FILE}"
    echo "Main HTML:     ${HTML_FILE}"
    echo "Main PDF:      ${PDF_FILE}"
    echo "Extra outputs: ${PANEL_OUT_DIR}"
    echo "============================================================"

    export PANEL_LABEL
    export PANEL_PATH="${INPUT_FILE}"
    export OUT_DIR="${PANEL_OUT_DIR}"
    export RMD_FILE
    export RENDER_OUTPUT_DIR
    export RENDER_OUTPUT_FILE

    Rscript - <<'RS'
rmd <- Sys.getenv("RMD_FILE")
render_output_dir <- Sys.getenv("RENDER_OUTPUT_DIR")
render_output_file <- Sys.getenv("RENDER_OUTPUT_FILE")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = render_output_file,
  output_dir = render_output_dir,
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS

    if [[ ! -f "${HTML_FILE}" ]]; then
      echo "ERROR: Expected HTML output was not created: ${HTML_FILE}"
      exit 1
    fi

    if [[ ! -f "${GENERATED_PDF_FILE}" ]]; then
      echo "ERROR: Expected PDF output was not created: ${GENERATED_PDF_FILE}"
      exit 1
    fi
    mv -f "${GENERATED_PDF_FILE}" "${PDF_FILE}"

    if [[ -f "${GENERATED_STATIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_STATIC_ERRORS_FILE}" "${STATIC_ERRORS_FILE}"
    fi

    if [[ -f "${GENERATED_DYNAMIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_DYNAMIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"
    fi

    for required_output in \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}"; do
      if [[ ! -f "${required_output}" ]]; then
        echo "ERROR: Expected core output was not created: ${required_output}"
        exit 1
      fi
    done

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${PDF_FILE}" \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}" \
      "${STATIC_ERRORS_FILE}" \
      "${DYNAMIC_ERRORS_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined diagnostic outputs"
  echo "------------------------------------------------------------"

  python - "${MANIFEST_FILE}" \
    "${COMBINED_STATIC}" \
    "${COMBINED_DYNAMIC}" \
    "${COMBINED_CHECKS}" \
    "${COMBINED_INPUT_SUMMARY}" \
    "${COMBINED_ERRORS}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

manifest_path = Path(sys.argv[1])
combined_static_path = Path(sys.argv[2])
combined_dynamic_path = Path(sys.argv[3])
combined_checks_path = Path(sys.argv[4])
combined_input_summary_path = Path(sys.argv[5])
combined_errors_path = Path(sys.argv[6])

manifest = pd.read_csv(manifest_path)


def read_required_csv(path: str, panel: str, kind: str) -> pd.DataFrame:
    """Read a required core output and attach panel metadata when needed."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {kind} output for {panel}: {csv_path}")

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        frame = pd.DataFrame()

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)

    return frame


def read_error_csv(path: str, panel: str, model_type: str) -> pd.DataFrame | None:
    """Read an optional model error file."""
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return None

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return None

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)
    if "model_type" not in frame.columns:
        insert_pos = 1 if "panel" in frame.columns else 0
        frame.insert(insert_pos, "model_type", model_type)

    return frame


static_frames = []
dynamic_frames = []
checks_frames = []
summary_frames = []
error_frames = []

for _, row in manifest.iterrows():
    panel = str(row["panel"])

    static_frames.append(read_required_csv(row["static"], panel, "static"))
    dynamic_frames.append(read_required_csv(row["dynamic"], panel, "dynamic"))
    checks_frames.append(read_required_csv(row["checks"], panel, "checks"))
    summary_frames.append(read_required_csv(row["input_summary"], panel, "input summary"))

    for error_column, model_type in (
        ("static_errors", "static"),
        ("dynamic_errors", "dynamic"),
    ):
        error_frame = read_error_csv(row[error_column], panel, model_type)
        if error_frame is not None:
            error_frames.append(error_frame)

combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = (
    pd.concat(error_frames, ignore_index=True)
    if error_frames
    else pd.DataFrame(columns=["panel", "model_type", "outcome", "error"])
)

for output_path in (
    combined_static_path,
    combined_dynamic_path,
    combined_checks_path,
    combined_input_summary_path,
    combined_errors_path,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)

combined_static.to_csv(combined_static_path, index=False)
combined_dynamic.to_csv(combined_dynamic_path, index=False)
combined_checks.to_csv(combined_checks_path, index=False)
combined_input_summary.to_csv(combined_input_summary_path, index=False)
combined_errors.to_csv(combined_errors_path, index=False)

print("Combined static effects rows:", len(combined_static))
print("Combined dynamic effects rows:", len(combined_dynamic))
print("Combined panel checks rows:", len(combined_checks))
print("Combined input summary rows:", len(combined_input_summary))
print("Combined error rows:", len(combined_errors))
print()
print("Saved combined static effects:", combined_static_path)
print("Saved combined dynamic effects:", combined_dynamic_path)
print("Saved combined panel checks:", combined_checks_path)
print("Saved combined input summary:", combined_input_summary_path)
print("Saved combined errors:", combined_errors_path)
PY

  rm -rf "${WORK_DIR}"

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:              $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
  echo "Main output root:       ${MAIN_OUTPUT_ROOT}"
  echo "Extra output root:      ${TMP_ROOT}"
  echo "Temporary outputs:      removed"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

