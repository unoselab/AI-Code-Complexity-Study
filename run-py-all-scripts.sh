#!/bin/bash
# Consolidated execution script generated on Tue Jul  7 12:12:05 PM CDT 2026

###############################################################################
# FILE: run-py-1a-count-repo.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1a: Count Python Cursor-adopting treatment repositories
# ============================================================
# This wrapper is the Python version of run7a-count-repo.sh.
#
# Goal:
#   Prepare the first Python treatment-repository input file for
#   reproducing the paper's language-specific Appendix result.
#
# Main purpose:
#   1. Read the paper baseline panel and repository metadata.
#   2. Count treatment repositories by primary language.
#   3. Extract Python treatment repositories.
#   4. Save the full Python treatment sample for the unbalanced-panel pipeline.
#   5. Also save a balanced-window >= K subset for diagnostics/robustness only.
#
# Why main sample is primary:
#   The paper uses an unbalanced panel. Therefore, the full Python
#   treatment sample should be used as the primary sample. The bw6
#   output is stricter and should be used only as a diagnostic or
#   robustness sample.
#
# Paper-replication logic:
#   - Primary language: Python
#   - Dataset source: treatment
#   - Main sample: all Python treatment repos found in the baseline panel
#   - Diagnostic sample: Python treatment repos with balanced_window >= 6
#
# Required input files:
#   DATA_DIR/panel_event_monthly.csv
#     - Monthly panel file from the paper-replication dataset.
#     - Used to identify treatment repositories and event-window coverage.
#
#   DATA_DIR/repos.csv
#     - Repository metadata file.
#     - Used to attach repo_primary_language and other repo-level metadata.
#
# Output files:
#   repo_python/treatment_python_repos.csv
#     - Primary Python treatment repository file.
#     - This should be used for the unbalanced-panel Python replication.
#
#   repo_python/treatment_python_repos_bw6.csv
#     - Diagnostic/robustness Python treatment repository file.
#     - Includes only repos with balanced_window >= MIN_BALANCED_WINDOW.
#     - Do not use this as the primary paper-replication sample.
#
# Typical usage:
#   bash run-py-1a-count-repo.sh
#
# Optional override examples:
#   MIN_BALANCED_WINDOW=5 bash run-py-1a-count-repo.sh
#
#   OUTPUT_DIR=repo_python_test \
#   bash run-py-1a-count-repo.sh
# ============================================================

# ------------------------------------------------------------
# Input dataset location
# ------------------------------------------------------------
# DATA_DIR should contain:
#   - panel_event_monthly.csv
#   - repos.csv
#
# In this project, data_baseline_backup is safer than data because it
# preserves the original baseline files used for replication.
DATA_DIR="${DATA_DIR:-data_baseline_backup}"

# We are extracting Cursor-adopting repositories, so dataset_source
# should be treatment.
DATASET_SOURCE="${DATASET_SOURCE:-treatment}"

# Human-readable group name printed by count_repo_lang.py.
GROUP_NAME="${GROUP_NAME:-Python}"

# ------------------------------------------------------------
# Output file locations
# ------------------------------------------------------------
# All Python-specific repository selection outputs are stored here.
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

# Primary output:
#   Full Python treatment sample.
#   Use this file for the main unbalanced-panel replication pipeline.
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Diagnostic output:
#   Python treatment sample restricted by balanced_window >= K.
#   Use this only for diagnostics or robustness checks.
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos_bw6.csv}"

# ------------------------------------------------------------
# Event-window diagnostic setting
# ------------------------------------------------------------
# balanced_window is the minimum of available pre-event and post-event
# monthly observations. A value of 6 means the repo has at least 6 months
# before and 6 months after the event month in the panel.
#
# This should not define the primary sample because the paper uses an
# unbalanced panel.
MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"

# Number of rows printed by the Python script for quick inspection.
TOP_PRINT="${TOP_PRINT:-30}"

mkdir -p "${OUTPUT_DIR}"

echo "============================================================"
echo "run-py-1a: count Python Cursor-adopting treatment repositories"
echo "Data dir:                    ${DATA_DIR}"
echo "Dataset source:              ${DATASET_SOURCE}"
echo "Group name:                  ${GROUP_NAME}"
echo "Output dir:                  ${OUTPUT_DIR}"
echo "Primary output file:         ${OUTPUT_FILE}"
echo "BW${MIN_BALANCED_WINDOW} diagnostic output: ${WINDOW_OUTPUT_FILE}"
echo "Min balanced window:         ${MIN_BALANCED_WINDOW}"
echo "Top print:                   ${TOP_PRINT}"
echo "============================================================"
echo

# ------------------------------------------------------------
# Run language filtering and event-window summarization
# ------------------------------------------------------------
# count_repo_lang.py will:
#   1. Read DATA_DIR/panel_event_monthly.csv.
#   2. Extract unique treatment repositories.
#   3. Join repository metadata from DATA_DIR/repos.csv.
#   4. Filter repositories whose repo_primary_language is Python.
#   5. Save the full Python treatment file.
#   6. Save the balanced-window diagnostic subset.
python proc_scripts/count_repo_lang.py \
  --data-dir "${DATA_DIR}" \
  --dataset-source "${DATASET_SOURCE}" \
  --language Python \
  --group-name "${GROUP_NAME}" \
  --output-file "${OUTPUT_FILE}" \
  --window-output-file "${WINDOW_OUTPUT_FILE}" \
  --min-balanced-window "${MIN_BALANCED_WINDOW}" \
  --top-print "${TOP_PRINT}"

echo
echo "============================================================"
echo "run-py-1a output check"
echo "============================================================"

# ------------------------------------------------------------
# Check primary Python treatment file
# ------------------------------------------------------------
# wc -l includes the CSV header. Therefore:
#   actual repo rows = wc -l output - 1
echo
echo "===== Main Python treatment file ====="
echo "File: ${OUTPUT_FILE}"
echo "Command: wc -l ${OUTPUT_FILE}"
wc -l "${OUTPUT_FILE}"
echo
echo "Command: head ${OUTPUT_FILE}"
head "${OUTPUT_FILE}"

# ------------------------------------------------------------
# Check balanced-window diagnostic file
# ------------------------------------------------------------
# This file is useful to understand how many Python repos have enough
# symmetric pre/post observations, but it should not replace the main
# unbalanced-panel sample.
echo
echo "===== Balanced-window diagnostic Python file ====="
echo "File: ${WINDOW_OUTPUT_FILE}"
echo "Command: wc -l ${WINDOW_OUTPUT_FILE}"
wc -l "${WINDOW_OUTPUT_FILE}"
echo
echo "Command: head ${WINDOW_OUTPUT_FILE}"
head "${WINDOW_OUTPUT_FILE}"

echo
echo "============================================================"
echo "run-py-1a completed successfully."
echo "Primary file for Python unbalanced-panel pipeline:"
echo "  ${OUTPUT_FILE}"
echo "Diagnostic bw${MIN_BALANCED_WINDOW} file:"
echo "  ${WINDOW_OUTPUT_FILE}"
echo "============================================================"


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

# Input candidate file from run-py-1a.
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Primary clone-status output used by the next step.
CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
CLONE_STATUS_BACKUP="${CLONE_STATUS_BACKUP:-${CLONE_STATUS_FILE%.csv}_${RUN_TS}.csv}"

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
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

# ------------------------------------------------------------
# Clone-status report settings
# ------------------------------------------------------------
CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV:-Python}"
CHECK_TOP_PRINT="${CHECK_TOP_PRINT:-80}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1b: clone Python Cursor-adopting treatment repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                  ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Output dir:                 ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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


###############################################################################
# FILE: run-py-1d-split-valid-event-repos.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1d: Split usable Python treatment repos by event_month
# ============================================================
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
#   repo_python/treatment_python_clone_usable_missing_event_month.csv
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

INPUT_FILE="${INPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event.csv}"
VALID_OUTPUT_FILE="${VALID_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event_valid.csv}"
MISSING_OUTPUT_FILE="${MISSING_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_missing_event_month.csv}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1d: split usable Python treatment repos by event_month" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Input file:           ${INPUT_FILE}" | tee -a "${LOG_FILE}"
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

REPOS_FILE="${REPOS_FILE:-${OUTPUT_BASE_DIR}/treatment_python_clone_usable_repos_with_event_valid.csv}"
CLONE_DIR="${CLONE_DIR:-../treatment-repos}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"

# Default is smoke test. Use MAX_REPOS=0 for full run.
MAX_REPOS="${MAX_REPOS:-5}"

# Fixed output directories:
#   - Smoke tests reuse repo_python/treatment_python_did_smoke
#   - Full run uses repo_python/treatment_python_did
#
# This is important because timestamped smoke directories cannot use cache.
FULL_OUTPUT_DIR="${FULL_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did}"
SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did_smoke}"

if [[ "${MAX_REPOS}" == "0" ]]; then
  OUTPUT_DIR="${OUTPUT_DIR:-${FULL_OUTPUT_DIR}}"
else
  OUTPUT_DIR="${OUTPUT_DIR:-${SMOKE_OUTPUT_DIR}}"
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

MANIFEST_FILE="${OUTPUT_DIR}/run-py-1e_analyzed_repos_manifest.csv"

SMOKE_REPOS_FILE="${OUTPUT_DIR}/treatment_python_repos_smoke_max${MAX_REPOS}.csv"
MISSING_REPOS_FILE="${OUTPUT_DIR}/run-py-1e_missing_repos_${RUN_TS}.csv"
TMP_OUTPUT_DIR="${OUTPUT_DIR}/_incremental_${RUN_TS}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1e: analyze Python treatment repos and validate adoption month" | tee -a "${LOG_FILE}"
echo "Timestamp:                 ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python analyzer:           ${PY_ANALYZER}" | tee -a "${LOG_FILE}"
echo "Adoption check script:     ${PY_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
echo "Cache check script:        ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:                ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:                 ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:                ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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

  CACHE_REPORT="${OUTPUT_DIR}/run-py-1e_cache_check_${RUN_TS}.txt"

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
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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
#   repo_python/treatment_python_sample_main_118.csv
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
# Outputs:
#   repo_python/python_matched_control_pairs_main_118.csv
#     - Clean treatment-control pair file after overlap removal.
#
#   repo_python/python_control_repos_to_clone_main_118.csv
#     - Unique clean control repos to clone in the next step.
#
#   repo_python/python_treatment_missing_matching_main_118.csv
#     - Treatment repos without matching rows.
#
#   repo_python/python_control_extract_summary_main_118.csv
#     - Summary metrics for audit.
#
# Sidecar outputs:
#   Raw pairs, raw controls, overlap diagnostics, and coverage files.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1g_extract_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/extract_matched_control_repos.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

TREATMENT_SAMPLE_FILE="${TREATMENT_SAMPLE_FILE:-${OUTPUT_DIR}/treatment_sample_main.csv}"
MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"

PAIR_OUTPUT_FILE="${PAIR_OUTPUT_FILE:-${OUTPUT_DIR}/matched_control_pairs_main.csv}"
CONTROL_CLONE_FILE="${CONTROL_CLONE_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main.csv}"
MISSING_MATCH_FILE="${MISSING_MATCH_FILE:-${OUTPUT_DIR}/treatment_missing_matching_main.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/control_extract_summary_main.csv}"

RAW_PAIR_OUTPUT_FILE="${RAW_PAIR_OUTPUT_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_raw.csv}"
RAW_CONTROL_CLONE_FILE="${RAW_CONTROL_CLONE_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main_raw.csv}"
OVERLAP_PAIR_FILE="${OVERLAP_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_overlap_pairs.csv}"
OVERLAP_REPO_FILE="${OVERLAP_REPO_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main_overlap_repos.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_coverage.csv}"

FULL_ADOPTER_FILE="${FULL_ADOPTER_FILE:-data_baseline_backup/panel_event_monthly.csv}"
FULL_ADOPTER_FILTER_COLUMN="${FULL_ADOPTER_FILTER_COLUMN:-is_treatment}"
FULL_ADOPTER_FILTER_VALUE="${FULL_ADOPTER_FILTER_VALUE:-1}"

TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1g: extract matched Python control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                     ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                 ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment sample file:         ${TREATMENT_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
echo "Matching file:                 ${MATCHING_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir:                    ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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
#   repo_python/control_repos_to_clone_main.csv
#
# Outputs:
#   repo_python/control_clone_status_main.csv
#   repo_python/control_clone_status_main_<timestamp>.csv
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

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1h_clone_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/clone_repos_v2.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main.csv}"

CLONE_ROOT="${CLONE_ROOT:-../control-repos}"

MAX_CLONES="${MAX_CLONES:-10}"
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-run-py-1h_control_clone_log}"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-${OUTPUT_DIR}/control_clone_status_main.csv}"
CHECK_OUTPUT_BACKUP="${CHECK_OUTPUT_BACKUP:-${CHECK_OUTPUT_FILE%.csv}_${RUN_TS}.csv}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1h: clone matched control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:             ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:         ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Control repos file:    ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
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
# Input:
#   repo_python/control_clone_status_main.csv
#   repo_python/matched_control_pairs_main.csv
#   repo_python/control_repos_to_clone_main.csv
#
# Outputs:
#   repo_python/control_clone_usable_repos_main.csv
#   repo_python/control_clone_failed_repos_main.csv
#   repo_python/matched_control_pairs_main_clone_usable.csv
#   repo_python/matched_control_pairs_main_clone_failed.csv
#   repo_python/control_pair_coverage_main_clone_usable.csv
#   repo_python/treatment_lost_all_controls_main.csv
#   repo_python/control_clone_usable_summary_main.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1i_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/control_clone_status_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main.csv}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${OUTPUT_DIR}/control_repos_to_clone_main.csv}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main.csv}"
FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_failed_repos_main.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_usable.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${OUTPUT_DIR}/treatment_lost_all_controls_main.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/control_clone_usable_summary_main.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated_existing}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1i: create clone-usable control repository sample" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
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
echo "run-py-1i completed successfully." | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:    ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:       ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:        ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
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
#   repo_python/control_clone_usable_repos_main.csv
#
# Clone dir:
#   ../control-repos
#
# Full-run outputs:
#   repo_python/control_did/ts_repos_monthly.csv
#   repo_python/control_did/ts_contributors_monthly.csv
#   repo_python/control_did/cursor_commits.csv
#   repo_python/control_did/ai_adoption_dates.csv
#   repo_python/control_did/run-py-1j_analyzed_repos_manifest.csv
#
# Smoke-run outputs:
#   repo_python/control_did_smoke/
#
# Usage:
#   Smoke test:
#     MAX_REPOS=5 NUM_PROCESSES=1 bash run-py-1j-analyze-control-repos.sh
#
#   Full run:
#     MAX_REPOS=0 NUM_PROCESSES=2 bash run-py-1j-analyze-control-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1j_analyze_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_repos_v2.py}"
CACHE_CHECK_SCRIPT="${CACHE_CHECK_SCRIPT:-proc_scripts/check_cache_control_repos.py}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python}"

REPOS_FILE="${REPOS_FILE:-${OUTPUT_ROOT}/control_clone_usable_repos_main.csv}"
CLONE_DIR="${CLONE_DIR:-../control-repos}"

FULL_OUTPUT_DIR="${FULL_OUTPUT_DIR:-${OUTPUT_ROOT}/control_did}"
SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${OUTPUT_ROOT}/control_did_smoke}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-2}"
MAX_REPOS="${MAX_REPOS:-5}"

SKIP_IF_COMPLETE="${SKIP_IF_COMPLETE:-true}"
INCREMENTAL_IF_PARTIAL="${INCREMENTAL_IF_PARTIAL:-true}"
FORCE_RERUN="${FORCE_RERUN:-false}"

if [[ "${MAX_REPOS}" -gt 0 ]]; then
  OUTPUT_DIR="${SMOKE_OUTPUT_DIR}"
else
  OUTPUT_DIR="${FULL_OUTPUT_DIR}"
fi

REPO_TS_FILE="${OUTPUT_DIR}/ts_repos_${AGGREGATION}ly.csv"
CONTRIB_TS_FILE="${OUTPUT_DIR}/ts_contributors_${AGGREGATION}ly.csv"
CURSOR_COMMITS_FILE="${OUTPUT_DIR}/cursor_commits.csv"
ADOPTION_FILE="${OUTPUT_DIR}/ai_adoption_dates.csv"
MANIFEST_FILE="${OUTPUT_DIR}/run-py-1j_analyzed_repos_manifest.csv"

MISSING_REPOS_FILE="${OUTPUT_DIR}/run-py-1j_missing_repos_${RUN_TS}.csv"
TMP_OUTPUT_DIR="${OUTPUT_DIR}/_incremental_${RUN_TS}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1j: analyze clone-usable control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:              ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:          ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Cache check script:     ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:             ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:              ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:             ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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
  RUN_REPOS_FILE="${OUTPUT_DIR}/control_repos_smoke_max${MAX_REPOS}.csv"
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
    2>&1 | tee "${OUTPUT_DIR}/run-py-1j_cache_check_${RUN_TS}.txt" | tee -a "${LOG_FILE}"

  CACHE_STATUS="$(grep '^CACHE_STATUS=' "${OUTPUT_DIR}/run-py-1j_cache_check_${RUN_TS}.txt" | tail -1 | cut -d= -f2 || true)"

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
echo "run-py-1j completed successfully." | tee -a "${LOG_FILE}"
echo "Requested repos file: ${RUN_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
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
# Input:
#   repo_python/control_clone_usable_repos_main.csv
#   repo_python/matched_control_pairs_main_clone_usable.csv
#   repo_python/control_did/ai_adoption_dates.csv
#   repo_python/control_did/ts_repos_monthly.csv
#   repo_python/control_did/ts_contributors_monthly.csv
#
# Outputs:
#   repo_python/control_local_cursor_evidence_in_window.csv
#   repo_python/control_local_cursor_evidence_post_window.csv
#   repo_python/control_clone_usable_repos_main_final_clean.csv
#   repo_python/matched_control_pairs_main_final_clean.csv
#   repo_python/matched_control_pairs_main_local_cursor_dropped.csv
#   repo_python/control_pair_coverage_main_final_clean.csv
#   repo_python/treatment_lost_all_controls_main_final_clean.csv
#   repo_python/control_local_cursor_filter_summary_main.csv
#   repo_python/matched_control_pairs_main_final_clean_1to3_only.csv
#   repo_python/control_pair_coverage_main_final_clean_1to3_only.csv
#   repo_python/control_did/ts_repos_monthly_final_clean.csv
#   repo_python/control_did/ts_contributors_monthly_final_clean.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1k_filter_local_cursor_controls_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/filter_controls_by_local_cursor_evidence.py}"

ANALYSIS_END="${ANALYSIS_END:-2025-08}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
CONTROL_OUTPUT_DIR="${CONTROL_OUTPUT_DIR:-${OUTPUT_DIR}/control_did}"

CONTROL_FILE="${CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_usable.csv}"
ADOPTION_FILE="${ADOPTION_FILE:-${CONTROL_OUTPUT_DIR}/ai_adoption_dates.csv}"

CONTROL_TS_REPOS_FILE="${CONTROL_TS_REPOS_FILE:-${CONTROL_OUTPUT_DIR}/ts_repos_monthly.csv}"
CONTROL_TS_CONTRIBUTORS_FILE="${CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_OUTPUT_DIR}/ts_contributors_monthly.csv}"

IN_WINDOW_EVIDENCE_FILE="${IN_WINDOW_EVIDENCE_FILE:-${OUTPUT_DIR}/control_local_cursor_evidence_in_window.csv}"
POST_WINDOW_EVIDENCE_FILE="${POST_WINDOW_EVIDENCE_FILE:-${OUTPUT_DIR}/control_local_cursor_evidence_post_window.csv}"

FINAL_CONTROL_FILE="${FINAL_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main_final_clean.csv}"
FINAL_PAIR_FILE="${FINAL_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_local_cursor_dropped.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_final_clean.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${OUTPUT_DIR}/treatment_lost_all_controls_main_final_clean.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/control_local_cursor_filter_summary_main.csv}"

STRICT_1TO3_PAIR_FILE="${STRICT_1TO3_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean_1to3_only.csv}"
STRICT_1TO3_COVERAGE_FILE="${STRICT_1TO3_COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_final_clean_1to3_only.csv}"

FINAL_CONTROL_TS_REPOS_FILE="${FINAL_CONTROL_TS_REPOS_FILE:-${CONTROL_OUTPUT_DIR}/ts_repos_monthly_final_clean.csv}"
FINAL_CONTROL_TS_CONTRIBUTORS_FILE="${FINAL_CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_OUTPUT_DIR}/ts_contributors_monthly_final_clean.csv}"

FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${CONTROL_OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1k: filter controls with local Cursor evidence" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                     ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Analysis end:                      ${ANALYSIS_END}" | tee -a "${LOG_FILE}"
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
echo "run-py-1k completed successfully." | tee -a "${LOG_FILE}"
echo "Final control file: ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file: ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file: ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
# This wrapper is adapted from the logic of run8d2-filter-local-cursor-controls.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# FILE: run-py-1l-build-matched-panel.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1l: Build final matched Python DiD event panels
# ============================================================
#
# Purpose:
#   Build final matched DiD panels for the Python experiment.
#
# Reused Python script:
#   proc_scripts/prepare_panel_event_v2.py
#
# Inputs:
#   1. Treatment metadata with event_month:
#        repo_python/treatment_sample_main.csv
#
#   2. Final clean treatment-control matched pairs:
#        repo_python/matched_control_pairs_main_final_clean.csv
#
#   3. Strict 1:3 final clean treatment-control matched pairs:
#        repo_python/matched_control_pairs_main_final_clean_1to3_only.csv
#
#   4. Treatment monthly git-history time series:
#        repo_python/treatment_python_did/ts_repos_monthly.csv
#
#   5. Final clean control monthly git-history time series:
#        repo_python/control_did/ts_repos_monthly_final_clean.csv
#
# Outputs:
#   Main final-clean panels:
#        repo_python/did_final/panel_event_matched_flexible.csv
#        repo_python/did_final/panel_event_matched_flexible_window_driven.csv
#
#   Strict 1:3 final-clean panels:
#        repo_python/did_final/panel_event_matched_strict.csv
#        repo_python/did_final/panel_event_matched_strict_window_driven.csv
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are kept as provenance, not as pseudo-event assignments.
#   - The balanced panel is window-completed by the panel builder.
#   - This wrapper normalizes time-series columns if the analyzer writes
#     "time" instead of "month".
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1l_build_matched_panel_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
DID_DIR="${DID_DIR:-${OUTPUT_DIR}/did_final}"
NORMALIZED_DIR="${NORMALIZED_DIR:-${DID_DIR}/_normalized_inputs_${RUN_TS}}"

TREATMENT_META="${TREATMENT_META:-${OUTPUT_DIR}/treatment_sample_main.csv}"

MAIN_PAIRS_FILE="${MAIN_PAIRS_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean.csv}"
STRICT_PAIRS_FILE="${STRICT_PAIRS_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean_1to3_only.csv}"

TREATMENT_TS_RAW="${TREATMENT_TS_RAW:-${OUTPUT_DIR}/treatment_python_did/ts_repos_monthly.csv}"
CONTROL_TS_RAW="${CONTROL_TS_RAW:-${OUTPUT_DIR}/control_did/ts_repos_monthly_final_clean.csv}"

TREATMENT_TS="${TREATMENT_TS:-${NORMALIZED_DIR}/treatment_ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-${NORMALIZED_DIR}/control_ts_repos_monthly.csv}"

MAIN_OUTPUT_FILE="${MAIN_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
MAIN_BALANCED_OUTPUT_FILE="${MAIN_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"

STRICT_OUTPUT_FILE="${STRICT_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
STRICT_BALANCED_OUTPUT_FILE="${STRICT_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

mkdir -p "${LOG_DIR}" "${DID_DIR}" "${NORMALIZED_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1l: build final matched Python DiD event panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:           ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Main pairs file:              ${MAIN_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pairs file:        ${STRICT_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series raw:    ${TREATMENT_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Control time series raw:      ${CONTROL_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Treatment time series norm:   ${TREATMENT_TS}" | tee -a "${LOG_FILE}"
echo "Control time series norm:     ${CONTROL_TS}" | tee -a "${LOG_FILE}"
echo "DID output dir:               ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Main output:                  ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Main balanced output:         ${MAIN_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict output:                ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict balanced output:       ${STRICT_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:                     ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${TREATMENT_META}" \
  "${MAIN_PAIRS_FILE}" \
  "${STRICT_PAIRS_FILE}" \
  "${TREATMENT_TS_RAW}" \
  "${CONTROL_TS_RAW}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Step 0: Normalize time-series input columns" | tee -a "${LOG_FILE}"
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

echo "** Step 1: Check input schemas" | tee -a "${LOG_FILE}"
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
  echo "** Step 2: Build ${label} panel" | tee -a "${LOG_FILE}"
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
echo "** Output summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

outputs = [
    ("main_unbalanced", Path("${MAIN_OUTPUT_FILE}")),
    ("main_balanced", Path("${MAIN_BALANCED_OUTPUT_FILE}")),
    ("strict_1to3_unbalanced", Path("${STRICT_OUTPUT_FILE}")),
    ("strict_1to3_balanced", Path("${STRICT_BALANCED_OUTPUT_FILE}")),
]

for label, path in outputs:
    if not path.exists():
        print(f"MISSING: {label}: {path}")
        continue

    df = pd.read_csv(path)

    print(f"{label}: {path}")
    print("  rows:", len(df))
    print("  repos:", df["repo_name"].nunique() if "repo_name" in df.columns else "(missing repo_name)")

    if "ever_treated" in df.columns:
        print("  treated repos:", df.loc[df["ever_treated"].eq(1), "repo_name"].nunique())
        print("  control repos:", df.loc[df["ever_treated"].eq(0), "repo_name"].nunique())

    if "dataset_source" in df.columns:
        print("  dataset_source counts:")
        print(df["dataset_source"].value_counts(dropna=False).to_string())

    if "time" in df.columns:
        print("  time range:", df["time"].min(), "to", df["time"].max())
    elif "month" in df.columns:
        print("  month range:", df["month"].min(), "to", df["month"].max())

    print()
PY

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1l completed successfully." | tee -a "${LOG_FILE}"
echo "DID output dir: ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Main output: ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Main balanced output: ${MAIN_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict output: ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict balanced output: ${STRICT_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e-build-jsts-matched-panel.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# FILE: run-py-1m-summarize-matched-panels.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1m: Summarize final Python matched DiD panels
# ============================================================
#
# Purpose:
#   Summarize the final Python matched DiD panels generated by run-py-1l.
#
# Current naming convention:
#   1. flexible
#      - Keeps treatments with 2 or 3 final controls.
#      - Uses observed repo-month rows only.
#
#   2. strict
#      - Keeps only treatments with exactly 3 final controls.
#      - Uses observed repo-month rows only.
#
#   3. flexible_window_driven
#      - Uses the flexible matched sample.
#      - Completes the Jan 2024-Aug 2025 window.
#
#   4. strict_window_driven
#      - Uses the strict matched sample.
#      - Completes the Jan 2024-Aug 2025 window.
#
# Primary focus:
#   repo_python/did_final/panel_event_matched_flexible.csv
#   repo_python/did_final/panel_event_matched_strict.csv
#
# Diagnostic / downstream focus:
#   repo_python/did_final/panel_event_matched_flexible_window_driven.csv
#   repo_python/did_final/panel_event_matched_strict_window_driven.csv
#
# Outputs:
#   repo_python/did_final/panel_qc_summary.csv
#   repo_python/did_final/panel_qc_by_source.csv
#   repo_python/did_final/panel_qc_paper_comparison.csv
#   repo_python/did_final/panel_qc_attrition_summary.csv
#   repo_python/did_final/panel_qc_dropped_by_strict.csv
#   repo_python/did_final/panel_qc_notes.md
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1m_summarize_matched_panels_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/summarize_matched_panels.py}"

DID_DIR="${DID_DIR:-repo_python/did_final}"

FLEXIBLE_PANEL="${FLEXIBLE_PANEL:-${DID_DIR}/panel_event_matched_flexible.csv}"
STRICT_PANEL="${STRICT_PANEL:-${DID_DIR}/panel_event_matched_strict.csv}"
FLEXIBLE_WINDOW_DRIVEN_PANEL="${FLEXIBLE_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_WINDOW_DRIVEN_PANEL="${STRICT_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

OUTPUT_SUMMARY="${OUTPUT_SUMMARY:-${DID_DIR}/panel_qc_summary.csv}"
OUTPUT_BY_SOURCE="${OUTPUT_BY_SOURCE:-${DID_DIR}/panel_qc_by_source.csv}"
OUTPUT_PAPER_COMPARISON="${OUTPUT_PAPER_COMPARISON:-${DID_DIR}/panel_qc_paper_comparison.csv}"
OUTPUT_ATTRITION="${OUTPUT_ATTRITION:-${DID_DIR}/panel_qc_attrition_summary.csv}"
OUTPUT_DROPPED_BY_STRICT="${OUTPUT_DROPPED_BY_STRICT:-${DID_DIR}/panel_qc_dropped_by_strict.csv}"
OUTPUT_NOTES="${OUTPUT_NOTES:-${DID_DIR}/panel_qc_notes.md}"

TREATMENT_SAMPLE="${TREATMENT_SAMPLE:-repo_python/treatment_sample_main.csv}"
TREATMENT_MISSING_MATCHING="${TREATMENT_MISSING_MATCHING:-repo_python/treatment_missing_matching_main.csv}"
FINAL_COVERAGE="${FINAL_COVERAGE:-repo_python/control_pair_coverage_main_final_clean.csv}"
STRICT_COVERAGE="${STRICT_COVERAGE:-repo_python/control_pair_coverage_main_final_clean_1to3_only.csv}"
FINAL_CONTROLS="${FINAL_CONTROLS:-repo_python/control_clone_usable_repos_main_final_clean.csv}"

PAPER_TREATMENT_REPOS="${PAPER_TREATMENT_REPOS:-121}"
PAPER_CONTROL_REPOS="${PAPER_CONTROL_REPOS:-127}"
PAPER_TOTAL_OBSERVATIONS="${PAPER_TOTAL_OBSERVATIONS:-2461}"
PAPER_POST_TREATMENT_OBSERVATIONS="${PAPER_POST_TREATMENT_OBSERVATIONS:-582}"

mkdir -p "${LOG_DIR}" "${DID_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1m: summarize final Python matched DiD panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                     ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "DID dir:                           ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Flexible panel:                    ${FLEXIBLE_PANEL}" | tee -a "${LOG_FILE}"
echo "Strict panel:                      ${STRICT_PANEL}" | tee -a "${LOG_FILE}"
echo "Flexible window-driven panel:      ${FLEXIBLE_WINDOW_DRIVEN_PANEL}" | tee -a "${LOG_FILE}"
echo "Strict window-driven panel:        ${STRICT_WINDOW_DRIVEN_PANEL}" | tee -a "${LOG_FILE}"
echo "Output summary:                    ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Output by-source:                  ${OUTPUT_BY_SOURCE}" | tee -a "${LOG_FILE}"
echo "Output paper comparison:           ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "Output attrition:                  ${OUTPUT_ATTRITION}" | tee -a "${LOG_FILE}"
echo "Output dropped by strict:          ${OUTPUT_DROPPED_BY_STRICT}" | tee -a "${LOG_FILE}"
echo "Output notes:                      ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Paper treatment repos:             ${PAPER_TREATMENT_REPOS}" | tee -a "${LOG_FILE}"
echo "Paper control repos:               ${PAPER_CONTROL_REPOS}" | tee -a "${LOG_FILE}"
echo "Paper total observations:          ${PAPER_TOTAL_OBSERVATIONS}" | tee -a "${LOG_FILE}"
echo "Paper post-treatment observations: ${PAPER_POST_TREATMENT_OBSERVATIONS}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${FLEXIBLE_PANEL}" \
  "${STRICT_PANEL}" \
  "${FLEXIBLE_WINDOW_DRIVEN_PANEL}" \
  "${STRICT_WINDOW_DRIVEN_PANEL}" \
  "${TREATMENT_SAMPLE}" \
  "${FINAL_COVERAGE}" \
  "${STRICT_COVERAGE}" \
  "${FINAL_CONTROLS}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Compile Python script" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Run panel summarizer" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

CMD=(
  python "${PY_SCRIPT}"
  --flexible-panel "${FLEXIBLE_PANEL}"
  --strict-panel "${STRICT_PANEL}"
  --flexible-window-driven-panel "${FLEXIBLE_WINDOW_DRIVEN_PANEL}"
  --strict-window-driven-panel "${STRICT_WINDOW_DRIVEN_PANEL}"
  --output-summary "${OUTPUT_SUMMARY}"
  --output-by-source "${OUTPUT_BY_SOURCE}"
  --output-paper-comparison "${OUTPUT_PAPER_COMPARISON}"
  --output-attrition "${OUTPUT_ATTRITION}"
  --output-dropped-by-strict "${OUTPUT_DROPPED_BY_STRICT}"
  --output-notes "${OUTPUT_NOTES}"
  --treatment-sample "${TREATMENT_SAMPLE}"
  --treatment-missing-matching "${TREATMENT_MISSING_MATCHING}"
  --final-coverage "${FINAL_COVERAGE}"
  --strict-coverage "${STRICT_COVERAGE}"
  --final-controls "${FINAL_CONTROLS}"
  --paper-treatment-repos "${PAPER_TREATMENT_REPOS}"
  --paper-control-repos "${PAPER_CONTROL_REPOS}"
  --paper-total-observations "${PAPER_TOTAL_OBSERVATIONS}"
  --paper-post-treatment-observations "${PAPER_POST_TREATMENT_OBSERVATIONS}"
)

echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_SUMMARY}" \
  "${OUTPUT_BY_SOURCE}" \
  "${OUTPUT_PAPER_COMPARISON}" \
  "${OUTPUT_ATTRITION}" \
  "${OUTPUT_DROPPED_BY_STRICT}" \
  "${OUTPUT_NOTES}"
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
echo "run-py-1m completed successfully." | tee -a "${LOG_FILE}"
echo "Summary file:          ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison file: ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "Notes file:            ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Log file:              ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e2-summarize-jsts-panels.sh,
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
# Current naming convention:
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible.csv
#
#   strict:
#     repo_python/did_final/panel_event_matched_strict.csv
#
# Primary focus:
#   PANEL_VARIANT=flexible
#   PANEL_VARIANT=strict
#
# Outputs:
#   repo_python/sonarqube_input/<variant>/treatment/data/ts_repos_monthly.csv
#   repo_python/sonarqube_input/<variant>/control/data/ts_repos_monthly.csv
#   repo_python/sonarqube_input/<variant>/months.txt
#   repo_python/sonarqube_input/<variant>/treatment_repos.txt
#   repo_python/sonarqube_input/<variant>/control_repos.txt
#   repo_python/sonarqube_input/<variant>/sonarqube_input_summary.csv
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

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_sonarqube_input.py}"
HISTORY_SCRIPT="${HISTORY_SCRIPT:-proc_scripts/create_tmp_repo_timeseries_history.py}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
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

SONAR_ROOT="${SONAR_ROOT:-repo_python/sonarqube_input/${PANEL_VARIANT}}"

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

TREATMENT_TS_FILE="${TREATMENT_TS_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_TS_FILE="${CONTROL_TS_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"

MONTHS_FILE="${MONTHS_FILE:-${SONAR_ROOT}/months.txt}"
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${SONAR_ROOT}/treatment_repos.txt}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${SONAR_ROOT}/control_repos.txt}"
SUMMARY_FILE="${SUMMARY_FILE:-${SONAR_ROOT}/sonarqube_input_summary.csv}"

MAX_TREATMENT_REPOS="${MAX_TREATMENT_REPOS:-0}"
MAX_CONTROL_REPOS="${MAX_CONTROL_REPOS:-0}"
ALLOW_MISSING_LATEST_COMMIT="${ALLOW_MISSING_LATEST_COMMIT:-false}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2a_create_sonarqube_input_${PANEL_VARIANT}_${RUN_TS}.log}"

mkdir -p \
  "${LOG_DIR}" \
  "${SONAR_ROOT}" \
  "$(dirname "${TREATMENT_TS_FILE}")" \
  "$(dirname "${CONTROL_TS_FILE}")"

{
  echo "============================================================"
  echo "run-py-2a: create Python SonarQube scan inputs"
  echo "Timestamp:                    ${RUN_TS}"
  echo "Panel variant:                ${PANEL_VARIANT}"
  echo "Python script:                ${PY_SCRIPT}"
  echo "History script:               ${HISTORY_SCRIPT}"
  echo "Panel file:                   ${PANEL_FILE}"
  echo "Sonar root:                   ${SONAR_ROOT}"
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
  echo "run-py-2a completed successfully."
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Treatment input: ${TREATMENT_TS_FILE}"
  echo "Control input:   ${CONTROL_TS_FILE}"
  echo "Summary file:    ${SUMMARY_FILE}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9a-create-jsts-sonarqube-input.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# FILE: run-py-2b1-sonarqube-treatment.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# Run Python SonarQube scan for treatment repo-month inputs.
# Use PANEL_VARIANT=flexible or PANEL_VARIANT=strict.
# Usage:
#    PANEL_VARIANT=strict   NUM_PROCESSES=1 bash run-py-2b1-sonarqube-treatment.sh
#    PANEL_VARIANT=flexible NUM_PROCESSES=1 bash run-py-2b1-sonarqube-treatment.sh

LANGUAGE_PROFILE=python TARGET=treatment bash ./run-py-2b-sonarqube-scan.sh


###############################################################################
# FILE: run-py-2b2-sonarqube-control.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# Run Python SonarQube scan for control repo-month inputs.
# Use PANEL_VARIANT=flexible or PANEL_VARIANT=strict.
# Usage:
#       PANEL_VARIANT=strict    NUM_PROCESSES=1 bash run-py-2b2-sonarqube-control.sh
#       PANEL_VARIANT=flexible  NUM_PROCESSES=1 bash run-py-2b2-sonarqube-control.sh
# 
LANGUAGE_PROFILE=python TARGET=control bash ./run-py-2b-sonarqube-scan.sh


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
# Current naming convention:
#   PANEL_VARIANT=flexible
#     repo_python/sonarqube_input/flexible/
#
#   PANEL_VARIANT=strict
#     repo_python/sonarqube_input/strict/
#
# Target:
#   TARGET=treatment
#   TARGET=control
#
# Outputs:
#   repo_python/sonarqube_input/<variant>/<target>/data/ts_repos_monthly_scanned.csv
#
# Usage:
#   Smoke or full depends on the input generated by run-py-2a.
#
#   PANEL_VARIANT=flexible TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=flexible TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=strict   TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=strict   TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# ============================================================

TARGET="${TARGET:-treatment}"
PANEL_VARIANT="${PANEL_VARIANT:-flexible}"
LANGUAGE_PROFILE="${LANGUAGE_PROFILE:-python}"
PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"

if [[ "${TARGET}" != "treatment" && "${TARGET}" != "control" ]]; then
  echo "ERROR: TARGET must be either 'treatment' or 'control'. Got: ${TARGET}"
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either 'flexible' or 'strict'. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b_sonarqube_${PANEL_VARIANT}_${TARGET}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/run_sonarqube_v2.py}"

SONAR_ROOT="${SONAR_ROOT:-repo_python/sonarqube_input/${PANEL_VARIANT}}"

NUM_PROCESSES="${NUM_PROCESSES:-1}"
AGGREGATION="${AGGREGATION:-month}"

if [[ "${TARGET}" == "treatment" ]]; then
  INPUT_FILE="${INPUT_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
  if [[ -n "${OUTPUT_SUFFIX}" ]]; then
    OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly_scanned_${OUTPUT_SUFFIX}.csv}"
  else
    OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly_scanned.csv}"
  fi
  CLONE_DIR="${CLONE_DIR:-../treatment-repos}"
else
  INPUT_FILE="${INPUT_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"
  if [[ -n "${OUTPUT_SUFFIX}" ]]; then
    OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly_scanned_${OUTPUT_SUFFIX}.csv}"
  else
    OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly_scanned.csv}"
  fi
  CLONE_DIR="${CLONE_DIR:-../control-repos}"
fi

mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_FILE}")"

# Load SonarQube configuration from .env when available.
# run_sonarqube_v2.py expects SONAR_PATH and SONAR_TOKEN.
# For backward compatibility, map SONAR_SCANNER_PATH to SONAR_PATH.
if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

if [[ -z "${SONAR_PATH:-}" && -n "${SONAR_SCANNER_PATH:-}" ]]; then
  export SONAR_PATH="${SONAR_SCANNER_PATH}"
fi

# If SONAR_PATH points to the scanner installation directory,
# normalize it to the sonar-scanner executable.
if [[ -n "${SONAR_PATH:-}" && -d "${SONAR_PATH}" && -x "${SONAR_PATH}/bin/sonar-scanner" ]]; then
  export SONAR_PATH="${SONAR_PATH}/bin/sonar-scanner"
fi

# Keep both variable names synchronized because older/newer scripts may read either one.
export SONAR_PATH
export SONAR_SCANNER_PATH="${SONAR_PATH}"

{
  echo "============================================================"
  echo "run-py-2b: Python SonarQube scan"
  echo "Started:       $(date)"
  echo "Panel variant: ${PANEL_VARIANT}"
  echo "Target:        ${TARGET}"
  echo "Python script: ${PY_SCRIPT}"
  echo "Aggregation:   ${AGGREGATION}"
  echo "Input file:    ${INPUT_FILE}"
  echo "Output file:   ${OUTPUT_FILE}"
  echo "Clone dir:     ${CLONE_DIR}"
  echo "Language:      ${LANGUAGE_PROFILE}"
  echo "Project prefix:${PROJECT_KEY_PREFIX}"
  echo "Output suffix: ${OUTPUT_SUFFIX}"
  echo "Num processes: ${NUM_PROCESSES}"
  echo "Log file:      ${LOG_FILE}"
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

  if [[ -z "${SONAR_PATH:-}" ]]; then
    echo "ERROR: SONAR_PATH is not set."
    echo "       Add SONAR_PATH=/path/to/sonar-scanner to .env,"
    echo "       or set SONAR_SCANNER_PATH and let this wrapper map it to SONAR_PATH."
    exit 1
  fi

  if [[ -z "${SONAR_TOKEN:-}" ]]; then
    echo "ERROR: SONAR_TOKEN is not set."
    echo "       Add SONAR_TOKEN to .env or export it in the shell."
    exit 1
  fi

  if [[ ! -x "${SONAR_PATH}" ]]; then
    echo "ERROR: SONAR_PATH is not executable: ${SONAR_PATH}"
    echo "       It should point to the sonar-scanner executable, for example:"
    echo "       /path/to/sonar-scanner/bin/sonar-scanner"
    exit 1
  fi

  echo "Sonar scanner: ${SONAR_PATH}"
  echo "Sonar token:   set"

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
  echo "run-py-2b completed successfully."
  echo "Completed:     $(date)"
  echo "Panel variant: ${PANEL_VARIANT}"
  echo "Target:        ${TARGET}"
  echo "Output file:   ${OUTPUT_FILE}"
  echo "Log file:      ${LOG_FILE}"
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
# Current naming convention:
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible.csv
#     repo_python/sonarqube_input/flexible/
#
#   strict:
#     repo_python/did_final/panel_event_matched_strict.csv
#     repo_python/sonarqube_input/strict/
#
# Primary focus:
#   PANEL_VARIANT=strict
#   PANEL_VARIANT=flexible
#
# Outputs:
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_qc.csv
#   repo_python/did_final/sonarqube_panel_merge_summary_<variant>.csv
#
# Usage:
#   Strict, now available:
#     PANEL_VARIANT=strict bash run-py-2c-merge-sonarqube-panel.sh
#
#   Flexible, after scanned files are available:
#     PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either flexible or strict. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2c_merge_sonarqube_panel_${PANEL_VARIANT}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/merge_sonarqube_panel_v2.py}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
SONAR_ROOT="${SONAR_ROOT:-repo_python/sonarqube_input/${PANEL_VARIANT}}"

PANEL_FILE="${PANEL_FILE:-${DID_DIR}/panel_event_matched_${PANEL_VARIANT}.csv}"

TREATMENT_METRICS="${TREATMENT_METRICS:-${SONAR_ROOT}/treatment/data/ts_repos_monthly_scanned.csv}"
CONTROL_METRICS="${CONTROL_METRICS:-${SONAR_ROOT}/control/data/ts_repos_monthly_scanned.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${DID_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube.csv}"
QC_OUTPUT_FILE="${QC_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube_qc.csv}"

MERGE_SUMMARY="${MERGE_SUMMARY:-${DID_DIR}/sonarqube_panel_merge_summary_${PANEL_VARIANT}.csv}"

mkdir -p "${LOG_DIR}" "${DID_DIR}"

{
  echo "============================================================"
  echo "run-py-2c: merge Python SonarQube metrics into matched panel"
  echo "Started:           $(date)"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Python script:     ${PY_SCRIPT}"
  echo "DID dir:           ${DID_DIR}"
  echo "Sonar root:        ${SONAR_ROOT}"
  echo "Panel file:        ${PANEL_FILE}"
  echo "Treatment metrics: ${TREATMENT_METRICS}"
  echo "Control metrics:   ${CONTROL_METRICS}"
  echo "Output file:       ${OUTPUT_FILE}"
  echo "QC output file:    ${QC_OUTPUT_FILE}"
  echo "Merge summary:     ${MERGE_SUMMARY}"
  echo "Log file:          ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in "${PY_SCRIPT}" "${PANEL_FILE}" "${TREATMENT_METRICS}" "${CONTROL_METRICS}"; do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      echo
      echo "If PANEL_VARIANT=flexible, make sure flexible treatment/control scans are complete"
      echo "and copied into repo_python/sonarqube_input/flexible/ first."
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
summary_output = Path("${MERGE_SUMMARY}")
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

metric_cols = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "static_analysis_warnings",
]

summary = {
    "panel": panel_variant,
    "file": str(output),
    "rows": len(df),
    "repos": df["repo_name"].nunique(),
    "treatment_rows": int((df["dataset_source"] == "treatment").sum()),
    "control_rows": int((df["dataset_source"] == "control").sum()),
    "treatment_repos": df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique(),
    "control_repos": df.loc[df["dataset_source"] == "control", "repo_name"].nunique(),
    "months_min": df["time"].min(),
    "months_max": df["time"].max(),
    "all_raw_metrics_missing_rows": int(df["sonarqube_all_raw_metrics_missing"].sum()),
    "ncloc_zero_rows": int(df["sonarqube_ncloc_zero"].sum()),
    "quality_outcomes_complete_rows": int(df["sonarqube_quality_outcomes_complete"].sum()),
}

for col in metric_cols:
    if col in df.columns:
        summary[f"{col}_nonmissing"] = int(df[col].notna().sum())

summary_df = pd.DataFrame([summary])
summary_output.parent.mkdir(parents=True, exist_ok=True)
summary_df.to_csv(summary_output, index=False)

print("Updated output:", output)
print("Updated QC:", qc_output)
print("Saved summary:", summary_output)
print()
print(summary_df.to_string(index=False))
print()
print(new_checks.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "run-py-2c completed successfully."
  echo "Completed:      $(date)"
  echo "Panel variant:  ${PANEL_VARIANT}"
  echo "Output file:    ${OUTPUT_FILE}"
  echo "QC output file: ${QC_OUTPUT_FILE}"
  echo "Merge summary:  ${MERGE_SUMMARY}"
  echo "Log file:       ${LOG_FILE}"
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
# Current naming convention:
#   strict:
#     repo_python/did_final/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=all      bash run-py-2d-check-sonarqube-panels.sh
#
# Outputs:
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_check_summary.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_missing_analysis_outcomes.csv
#   repo_python/did_final/sonarqube_panel_check_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/sonarqube_panel_check_summary_<variant>.csv
#   repo_python/did_final/sonarqube_panel_check_qc_<variant>.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2d_check_sonarqube_panels_${PANEL_VARIANT}_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

MANIFEST_FILE="${DID_DIR}/sonarqube_panel_check_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_SUMMARY="${DID_DIR}/sonarqube_panel_check_summary_${PANEL_VARIANT}.csv"
COMBINED_QC="${DID_DIR}/sonarqube_panel_check_qc_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${DID_DIR}/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${DID_DIR}/panel_event_matched_flexible_with_sonarqube.csv")
fi

mkdir -p "${LOG_DIR}" "${DID_DIR}"

{
  echo "============================================================"
  echo "run-py-2d: check Python merged SonarQube panels"
  echo "Started:          $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "DID dir:          ${DID_DIR}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${CHECK_SCRIPT}"

  echo "panel,input,summary,missing" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control SonarQube scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      exit 1
    fi

    BASE_FILE="${INPUT_FILE%.csv}"
    SUMMARY_OUTPUT="${BASE_FILE}_check_summary.csv"
    MISSING_OUTPUT="${BASE_FILE}_missing_analysis_outcomes.csv"

    echo
    echo "============================================================"
    echo "Checking panel: ${PANEL_LABEL}"
    echo "Input:          ${INPUT_FILE}"
    echo "Summary output: ${SUMMARY_OUTPUT}"
    echo "Missing output: ${MISSING_OUTPUT}"
    echo "============================================================"

    python "${CHECK_SCRIPT}" \
      --input "${INPUT_FILE}" \
      --summary-output "${SUMMARY_OUTPUT}" \
      --missing-output "${MISSING_OUTPUT}"

    printf '%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${SUMMARY_OUTPUT}" \
      "${MISSING_OUTPUT}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined run-py-2d summaries"
  echo "------------------------------------------------------------"

  python - <<PY
from pathlib import Path
import pandas as pd

manifest_path = Path("${MANIFEST_FILE}")
combined_summary_path = Path("${COMBINED_SUMMARY}")
combined_qc_path = Path("${COMBINED_QC}")

manifest = pd.read_csv(manifest_path)

summary_frames = []
qc_rows = []

def read_csv_if_possible(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    input_file = Path(row["input"])
    summary_file = Path(row["summary"])
    missing_file = Path(row["missing"])

    summary = read_csv_if_possible(summary_file)
    if not summary.empty:
        summary.insert(0, "panel", panel)
        summary_frames.append(summary)

    missing = read_csv_if_possible(missing_file)

    input_df = pd.read_csv(input_file)
    qc_rows.append({
        "panel": panel,
        "input_file": str(input_file),
        "rows": len(input_df),
        "repos": input_df["repo_name"].nunique() if "repo_name" in input_df.columns else None,
        "treatment_rows": int((input_df["dataset_source"] == "treatment").sum()) if "dataset_source" in input_df.columns else None,
        "control_rows": int((input_df["dataset_source"] == "control").sum()) if "dataset_source" in input_df.columns else None,
        "missing_analysis_rows": len(missing),
        "missing_analysis_repos": missing["repo_name"].nunique() if "repo_name" in missing.columns else 0,
        "missing_output_file": str(missing_file),
    })

if summary_frames:
    combined_summary = pd.concat(summary_frames, ignore_index=True)
else:
    combined_summary = pd.DataFrame()

combined_qc = pd.DataFrame(qc_rows)

combined_summary_path.parent.mkdir(parents=True, exist_ok=True)
combined_qc_path.parent.mkdir(parents=True, exist_ok=True)

combined_summary.to_csv(combined_summary_path, index=False)
combined_qc.to_csv(combined_qc_path, index=False)

print("Saved combined summary:", combined_summary_path)
print("Saved combined QC:", combined_qc_path)
print()
print("Combined QC:")
print(combined_qc.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "run-py-2d completed successfully."
  echo "Completed:        $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
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
#   Convert merged Python SonarQube panels into quality DiD input files.
#
# Current naming convention:
#   strict:
#     repo_python/did_final/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh
#   PANEL_VARIANT=flexible bash run-py-2e-prepare-quality-did-input.sh
#   PANEL_VARIANT=all      bash run-py-2e-prepare-quality-did-input.sh
#
# Outputs for each variant:
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_complete.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_qc.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_missing_core_quality.csv
#
# Combined outputs:
#   repo_python/did_final/quality_did_input_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/quality_did_input_qc_<variant>_long.csv
#   repo_python/did_final/quality_did_input_qc_<variant>_wide.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2e_prepare_quality_did_input_${PANEL_VARIANT}_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

MANIFEST_FILE="${DID_DIR}/quality_did_input_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_QC_LONG="${DID_DIR}/quality_did_input_qc_${PANEL_VARIANT}_long.csv"
COMBINED_QC_WIDE="${DID_DIR}/quality_did_input_qc_${PANEL_VARIANT}_wide.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${DID_DIR}/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${DID_DIR}/panel_event_matched_flexible_with_sonarqube.csv")
fi

mkdir -p "${LOG_DIR}" "${DID_DIR}"

{
  echo "============================================================"
  echo "run-py-2e: prepare Python quality DiD input"
  echo "Started:          $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Python script:    ${PY_SCRIPT}"
  echo "DID dir:          ${DID_DIR}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined QC long: ${COMBINED_QC_LONG}"
  echo "Combined QC wide: ${COMBINED_QC_WIDE}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  echo "panel,input,output,complete_output,qc_output,missing_output" > "${MANIFEST_FILE}"

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

    BASE_FILE="${INPUT_FILE%.csv}"
    OUTPUT_FILE="${BASE_FILE}_quality_did_input.csv"
    COMPLETE_OUTPUT_FILE="${BASE_FILE}_quality_did_input_complete.csv"
    QC_OUTPUT_FILE="${BASE_FILE}_quality_did_input_qc.csv"
    MISSING_OUTPUT_FILE="${BASE_FILE}_quality_did_input_missing_core_quality.csv"

    echo
    echo "============================================================"
    echo "Preparing quality DiD input for panel: ${PANEL_LABEL}"
    echo "Input:           ${INPUT_FILE}"
    echo "Output:          ${OUTPUT_FILE}"
    echo "Complete output: ${COMPLETE_OUTPUT_FILE}"
    echo "QC output:       ${QC_OUTPUT_FILE}"
    echo "Missing output:  ${MISSING_OUTPUT_FILE}"
    echo "============================================================"

    python "${PY_SCRIPT}" \
      --panel-label "${PANEL_LABEL}" \
      --input "${INPUT_FILE}" \
      --output "${OUTPUT_FILE}" \
      --complete-output "${COMPLETE_OUTPUT_FILE}" \
      --qc-output "${QC_OUTPUT_FILE}" \
      --missing-output "${MISSING_OUTPUT_FILE}"

    printf '%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}" >> "${MANIFEST_FILE}"
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

manifest = pd.read_csv(manifest_path)

qc_frames = []
wide_rows = []

def read_csv_if_possible(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    qc_file = Path(row["qc_output"])
    missing_file = Path(row["missing_output"])
    output_file = Path(row["output"])
    complete_file = Path(row["complete_output"])

    qc = read_csv_if_possible(qc_file)
    if not qc.empty:
        qc.insert(0, "panel", panel)
        qc_frames.append(qc)

    output_df = pd.read_csv(output_file) if output_file.exists() else pd.DataFrame()
    complete_df = pd.read_csv(complete_file) if complete_file.exists() else pd.DataFrame()
    missing_df = read_csv_if_possible(missing_file)

    wide_rows.append({
        "panel": panel,
        "output_file": str(output_file),
        "complete_output_file": str(complete_file),
        "missing_output_file": str(missing_file),
        "output_rows": len(output_df),
        "complete_rows": len(complete_df),
        "missing_core_quality_rows": len(missing_df),
        "output_repos": output_df["repo_name"].nunique() if "repo_name" in output_df.columns else None,
        "complete_repos": complete_df["repo_name"].nunique() if "repo_name" in complete_df.columns else None,
        "missing_core_quality_repos": missing_df["repo_name"].nunique() if "repo_name" in missing_df.columns else 0,
    })

if qc_frames:
    combined_long = pd.concat(qc_frames, ignore_index=True)
else:
    combined_long = pd.DataFrame()

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

  echo
  echo "============================================================"
  echo "run-py-2e completed successfully."
  echo "Completed:        $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined QC long: ${COMBINED_QC_LONG}"
  echo "Combined QC wide: ${COMBINED_QC_WIDE}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9e_prepare_quality_did_input.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# FILE: run-py-2f-did-borusyak-quality.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2f: Borusyak DiD for Python SonarQube quality outcomes
# ============================================================
# Purpose:
#   Run Borusyak DiD estimation for Python quality outcomes
#   using complete-case quality DiD input files from run-py-2e.
#
# Current naming convention:
#   strict:
#     repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv
#
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
#   PANEL_VARIANT=flexible bash run-py-2f-did-borusyak-quality.sh
#   PANEL_VARIANT=all      bash run-py-2f-did-borusyak-quality.sh
#
# Outputs:
#   repo_python/did_final/quality_did_borusyak/<variant>/
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_static_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_dynamic_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_panel_checks_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_input_summary_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_errors_<variant>.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2f_did_borusyak_quality_${PANEL_VARIANT}_${RUN_TS}.log}"

export PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_quality_python_v2.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/quality_did_borusyak}"

MANIFEST_FILE="${OUT_ROOT}/borusyak_quality_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_STATIC="${OUT_ROOT}/borusyak_quality_static_effects_${PANEL_VARIANT}.csv"
COMBINED_DYNAMIC="${OUT_ROOT}/borusyak_quality_dynamic_effects_${PANEL_VARIANT}.csv"
COMBINED_CHECKS="${OUT_ROOT}/borusyak_quality_panel_checks_${PANEL_VARIANT}.csv"
COMBINED_INPUT_SUMMARY="${OUT_ROOT}/borusyak_quality_input_summary_${PANEL_VARIANT}.csv"
COMBINED_ERRORS="${OUT_ROOT}/borusyak_quality_errors_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${DID_DIR}/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${DID_DIR}/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv")
fi

mkdir -p "${LOG_DIR}" "${OUT_ROOT}"

{
  echo "============================================================"
  echo "run-py-2f: Python Borusyak DiD for SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "PROJECT_ROOT:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "Helper file:            ${HELPER_FILE}"
  echo "DID dir:                ${DID_DIR}"
  echo "Output root:            ${OUT_ROOT}"
  echo "Manifest:               ${MANIFEST_FILE}"
  echo "Combined static:        ${COMBINED_STATIC}"
  echo "Combined dynamic:       ${COMBINED_DYNAMIC}"
  echo "Combined checks:        ${COMBINED_CHECKS}"
  echo "Combined input summary: ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:        ${COMBINED_ERRORS}"
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

  echo "panel,input,out_dir,html,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}"
    HTML_FILE="${PANEL_OUT_DIR}/borusyak_quality_${PANEL_LABEL}.html"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input complete-case panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      echo "  3. PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh"
      echo "  4. PANEL_VARIANT=flexible bash run-py-2e-prepare-quality-did-input.sh"
      exit 1
    fi

    mkdir -p "${PANEL_OUT_DIR}"

    echo
    echo "============================================================"
    echo "Running panel: ${PANEL_LABEL}"
    echo "Input:         ${INPUT_FILE}"
    echo "Output dir:    ${PANEL_OUT_DIR}"
    echo "HTML:          ${HTML_FILE}"
    echo "============================================================"

    export PANEL_LABEL
    export PANEL_PATH="${INPUT_FILE}"
    export OUT_DIR="${PANEL_OUT_DIR}"
    export RMD_FILE

    Rscript -e "rmarkdown::render(
      input = Sys.getenv('RMD_FILE'),
      output_file = paste0('borusyak_quality_', Sys.getenv('PANEL_LABEL'), '.html'),
      output_dir = Sys.getenv('OUT_DIR'),
      params = list(
        panel_label = Sys.getenv('PANEL_LABEL'),
        panel_path = Sys.getenv('PANEL_PATH'),
        out_dir = Sys.getenv('OUT_DIR')
      ),
      knit_root_dir = getwd(),
      envir = new.env(parent = globalenv()),
      quiet = FALSE
    )"

    STATIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv"
    DYNAMIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv"
    CHECKS_FILE="${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv"
    INPUT_SUMMARY_FILE="${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv"
    METADATA_FILE="${PANEL_OUT_DIR}/borusyak_quality_metadata.csv"
    STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv"
    DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv"

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}" \
      "${STATIC_ERRORS_FILE}" \
      "${DYNAMIC_ERRORS_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Combining Borusyak quality outputs"
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


def read_optional_csv(path, panel, kind):
    """Read one output CSV and add panel/kind only when missing."""
    path = Path(path)

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame([{
            "panel": panel,
            "kind": kind,
            "missing_file": str(path),
        }])

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame([{
            "panel": panel,
            "kind": kind,
            "empty_file": str(path),
        }])

    if "panel" not in df.columns:
        df.insert(0, "panel", panel)

    return df


static_frames = []
dynamic_frames = []
checks_frames = []
summary_frames = []
error_frames = []

for _, row in manifest.iterrows():
    panel = row["panel"]

    static_frames.append(read_optional_csv(row["static"], panel, "static"))
    dynamic_frames.append(read_optional_csv(row["dynamic"], panel, "dynamic"))
    checks_frames.append(read_optional_csv(row["checks"], panel, "checks"))
    summary_frames.append(read_optional_csv(row["input_summary"], panel, "input_summary"))

    for error_col, model_type in [
        ("static_errors", "static"),
        ("dynamic_errors", "dynamic"),
    ]:
        error_path = Path(row[error_col])

        if not error_path.exists() or error_path.stat().st_size == 0:
            continue

        try:
            err = pd.read_csv(error_path)
        except pd.errors.EmptyDataError:
            continue

        if "panel" not in err.columns:
            err.insert(0, "panel", panel)

        if "model_type" not in err.columns:
            insert_pos = 1 if "panel" in err.columns else 0
            err.insert(insert_pos, "model_type", model_type)

        error_frames.append(err)


combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = pd.concat(error_frames, ignore_index=True) if error_frames else pd.DataFrame(
    columns=["panel", "model_type", "outcome", "error"]
)

combined_static_path.parent.mkdir(parents=True, exist_ok=True)

combined_static.to_csv(combined_static_path, index=False)
combined_dynamic.to_csv(combined_dynamic_path, index=False)
combined_checks.to_csv(combined_checks_path, index=False)
combined_input_summary.to_csv(combined_input_summary_path, index=False)
combined_errors.to_csv(combined_errors_path, index=False)

print("Combined static effects:")
print(combined_static.to_string(index=False))
print()

print("Combined dynamic effects rows:", len(combined_dynamic))
print("Combined panel checks rows:", len(combined_checks))
print("Combined input summary rows:", len(combined_input_summary))
print("Combined error rows:", len(combined_errors))
print()

print(f"Saved combined static effects: {combined_static_path}")
print(f"Saved combined dynamic effects: {combined_dynamic_path}")
print(f"Saved combined panel checks: {combined_checks_path}")
print(f"Saved combined input summary: {combined_input_summary_path}")
print(f"Saved combined errors: {combined_errors_path}")
PY

  echo
  echo "============================================================"
  echo "run-py-2f completed successfully."
  echo "Completed:              $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Manifest:               ${MANIFEST_FILE}"
  echo "Combined static:        ${COMBINED_STATIC}"
  echo "Combined dynamic:       ${COMBINED_DYNAMIC}"
  echo "Combined checks:        ${COMBINED_CHECKS}"
  echo "Combined input summary: ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:        ${COMBINED_ERRORS}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9f_did_borusyak_quality.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# FILE: run-py-2g-summarize-borusyak-quality.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2g: Summarize Python Borusyak quality DiD outputs
# ============================================================
#
# Purpose:
#   Summarize Python Borusyak quality DiD outputs generated by
#   run-py-2f-did-borusyak-quality.sh.
# Inputs:
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_static_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_dynamic_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_panel_checks_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_input_summary_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_errors_<variant>.csv
#
# Supported variants:
#   flexible
#   strict
#
# Outputs:
#   repo_python/did_final/quality_did_borusyak/summary/
#     - borusyak_quality_static_effects_paper_ready.csv
#     - borusyak_quality_static_effects_wide.csv
#     - borusyak_quality_main_panel_table.csv
#     - borusyak_quality_main_panel_table.md
#     - borusyak_quality_dynamic_effects_percent.csv
#     - borusyak_quality_dynamic_effects_plot_ready.csv
#     - borusyak_quality_summary_notes.txt
#
# Usage:
#   MAIN_PANEL=strict bash run-py-2g-summarize-borusyak-quality.sh
#   MAIN_PANEL=flexible bash run-py-2g-summarize-borusyak-quality.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2g_summarize_borusyak_quality_${RUN_TS}.log}"

INPUT_DIR="${INPUT_DIR:-repo_python/did_final/quality_did_borusyak}"
OUTPUT_DIR="${OUTPUT_DIR:-${INPUT_DIR}/summary}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/summarize_borusyak_quality_outputs_python.py}"

MAIN_PANEL="${MAIN_PANEL:-strict}"
PANEL_VARIANTS="${PANEL_VARIANTS:-flexible strict}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2g: summarize Python Borusyak quality DiD outputs"
  echo "Started:        $(date)"
  echo "Python script:  ${PY_SCRIPT}"
  echo "Input dir:      ${INPUT_DIR}"
  echo "Output dir:     ${OUTPUT_DIR}"
  echo "Main panel:     ${MAIN_PANEL}"
  echo "Panel variants: ${PANEL_VARIANTS}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "ERROR: Input directory not found: ${INPUT_DIR}"
    exit 1
  fi

  case "${MAIN_PANEL}" in
    flexible|strict)
      ;;
    *)
      echo "ERROR: MAIN_PANEL must be flexible or strict. Got: ${MAIN_PANEL}"
      exit 1
      ;;
  esac

  python -m py_compile "${PY_SCRIPT}"

  echo "** Build combined Python quality outputs"
  echo "------------------------------------------------------------"

  variant_args=()
  for variant in ${PANEL_VARIANTS}; do
    variant_args+=("${variant}")
  done

  python - "${INPUT_DIR}" "${variant_args[@]}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

input_dir = Path(sys.argv[1])
variants = sys.argv[2:]

if not variants:
    raise SystemExit("ERROR: no panel variants provided.")

specs = [
    ("static_effects", True),
    ("dynamic_effects", True),
    ("panel_checks", False),
    ("input_summary", False),
    ("errors", False),
]

for stem, required in specs:
    frames = []

    for variant in variants:
        path = input_dir / f"borusyak_quality_{stem}_{variant}.csv"
        if not path.exists():
            print(f"Missing optional input: {path}")
            continue

        df = pd.read_csv(path)

        if "panel" not in df.columns:
            df.insert(0, "panel", variant)
        else:
            df["panel"] = df["panel"].fillna(variant)
            df.loc[df["panel"].astype(str).str.strip().eq(""), "panel"] = variant

        frames.append(df)
        print(f"Loaded {variant}: {path} rows={len(df)}")

    out_path = input_dir / f"borusyak_quality_{stem}_all.csv"

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(out_path, index=False)
        print(f"Saved combined file: {out_path} rows={len(combined)}")
    elif required:
        raise SystemExit(f"ERROR: required combined input could not be built for {stem}")
    else:
        empty = pd.DataFrame(columns=["panel"])
        empty.to_csv(out_path, index=False)
        print(f"Saved empty optional combined file: {out_path}")
PY

  echo
  echo "** Summarize Python quality DiD outputs"
  echo "------------------------------------------------------------"

  python "${PY_SCRIPT}" \
    --input-dir "${INPUT_DIR}" \
    --output-dir "${OUTPUT_DIR}" \
    --main-panel "${MAIN_PANEL}"

  echo
  echo "============================================================"
  echo "run-py-2g completed successfully."
  echo "Completed:   $(date)"
  echo "Output dir:  ${OUTPUT_DIR}"
  echo "Log file:    ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
#
# Reused logic:
#   This wrapper follows the structure of run9g_summarize_borusyak_quality.sh,
#   but it uses Python-specific paths, labels, and panel variants.
#


###############################################################################
# FILE: run-py-2h-did-borusyak-velocity.sh
###############################################################################

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2h: Borusyak DiD for Python development velocity outcomes
# ============================================================
#
# Purpose:
#   Run Borusyak imputation DiD for Python development velocity
#   outcomes using the final matched Python panels.
#
# Outcomes handled inside the Rmd:
#   - commits
#   - lines_added
#
# Current Python panel naming convention:
#   flexible
#     - Sample-coverage panel.
#     - Keeps treatments with 2 or 3 final controls.
#     - Primary analysis candidate.
#
#   strict
#     - 1:3 matching-rule panel.
#     - Keeps only treatments with exactly 3 final controls.
#     - Primary robustness / matching-rule panel.
#
#   flexible_window_driven
#     - Diagnostic window-completed version of flexible.
#
#   strict_window_driven
#     - Diagnostic window-completed version of strict.
#
# Default run:
#   PANEL_VARIANTS="flexible strict"
#
# Optional diagnostic run:
#   PANEL_VARIANTS="flexible strict flexible_window_driven strict_window_driven"
#
# Inputs:
#   repo_python/did_final/panel_event_matched_flexible.csv
#   repo_python/did_final/panel_event_matched_strict.csv
#   repo_python/did_final/panel_event_matched_flexible_window_driven.csv
#   repo_python/did_final/panel_event_matched_strict_window_driven.csv
#
# Outputs:
#   repo_python/did_final/velocity_did_borusyak/<variant>/borusyak_velocity_<variant>.html
#   repo_python/did_final/velocity_did_borusyak/borusyak_velocity_static_effects_all.csv
#   repo_python/did_final/velocity_did_borusyak/borusyak_velocity_dynamic_effects_all.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_static_effects_paper_ready.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_static_effects_wide.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_dynamic_effects_percent.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_dynamic_effects_plot_ready.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_summary_notes.txt
#
# Usage:
#   bash run-py-2h-did-borusyak-velocity.sh
#
#   PANEL_VARIANTS="flexible strict flexible_window_driven strict_window_driven" \
#   bash run-py-2h-did-borusyak-velocity.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2h_did_borusyak_velocity_${RUN_TS}.log}"

RMD="${RMD:-proc_r/DiffInDiffBorusyak_velocity_python_v2.Rmd}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/velocity_did_borusyak}"
SUMMARY_DIR="${SUMMARY_DIR:-${OUT_ROOT}/summary}"

PANEL_VARIANTS="${PANEL_VARIANTS:-flexible strict}"

FLEXIBLE_PANEL="${FLEXIBLE_PANEL:-${DID_DIR}/panel_event_matched_flexible.csv}"
STRICT_PANEL="${STRICT_PANEL:-${DID_DIR}/panel_event_matched_strict.csv}"
FLEXIBLE_WINDOW_DRIVEN_PANEL="${FLEXIBLE_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_WINDOW_DRIVEN_PANEL="${STRICT_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

mkdir -p "${LOG_DIR}" "${OUT_ROOT}" "${SUMMARY_DIR}"

resolve_panel_path() {
  local label="$1"

  case "${label}" in
    flexible)
      echo "${FLEXIBLE_PANEL}"
      ;;
    strict)
      echo "${STRICT_PANEL}"
      ;;
    flexible_window_driven)
      echo "${FLEXIBLE_WINDOW_DRIVEN_PANEL}"
      ;;
    strict_window_driven)
      echo "${STRICT_WINDOW_DRIVEN_PANEL}"
      ;;
    *)
      echo "ERROR: unsupported panel variant: ${label}" >&2
      echo "Supported variants: flexible strict flexible_window_driven strict_window_driven" >&2
      exit 1
      ;;
  esac
}

render_one_panel() {
  local label="$1"
  local panel="$2"
  local out_dir="${OUT_ROOT}/${label}"

  echo
  echo "============================================================"
  echo "Rendering Python velocity Borusyak panel: ${label}"
  echo "Panel:      ${panel}"
  echo "Output dir: ${out_dir}"
  echo "============================================================"

  if [[ ! -f "${panel}" ]]; then
    echo "ERROR: panel file not found: ${panel}"
    exit 1
  fi

  mkdir -p "${out_dir}"

  PANEL_LABEL="${label}" \
  PANEL_PATH="${panel}" \
  OUT_DIR="${out_dir}" \
  RMD_PATH="${RMD}" \
  Rscript - <<'RS'
rmd <- Sys.getenv("RMD_PATH")
panel_label <- Sys.getenv("PANEL_LABEL")
panel_path <- Sys.getenv("PANEL_PATH")
out_dir <- Sys.getenv("OUT_DIR")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = paste0("borusyak_velocity_", panel_label, ".html"),
  output_dir = out_dir,
  params = list(
    panel_label = panel_label,
    panel_path = panel_path,
    out_dir = out_dir
  ),
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS
}

{
  echo "============================================================"
  echo "run-py-2h: Python development velocity Borusyak DiD"
  echo "Started:        $(date)"
  echo "Rmd:            ${RMD}"
  echo "DID dir:        ${DID_DIR}"
  echo "Output root:    ${OUT_ROOT}"
  echo "Summary dir:    ${SUMMARY_DIR}"
  echo "Panel variants: ${PANEL_VARIANTS}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD}"
    echo "Create it first from proc_r/DiffInDiffBorusyak_velocity_v2.Rmd."
    exit 1
  fi

  for label in ${PANEL_VARIANTS}; do
    panel_path="$(resolve_panel_path "${label}")"
    render_one_panel "${label}" "${panel_path}"
  done

  echo
  echo "** Building combined Python velocity summaries"
  echo "------------------------------------------------------------"

  python - "${OUT_ROOT}" "${SUMMARY_DIR}" "${PANEL_VARIANTS}" <<'PY'
import math
import sys
from pathlib import Path

import pandas as pd

out_root = Path(sys.argv[1])
summary_dir = Path(sys.argv[2])
labels = sys.argv[3].split()

summary_dir.mkdir(parents=True, exist_ok=True)

def read_if_exists(label: str, filename: str) -> pd.DataFrame | None:
    path = out_root / label / filename
    if not path.exists():
        print(f"MISSING: {path}")
        return None

    df = pd.read_csv(path)

    if "panel" not in df.columns:
        df.insert(0, "panel", label)
    else:
        df["panel"] = df["panel"].fillna(label)
        df.loc[df["panel"].astype(str).str.strip().eq(""), "panel"] = label

    return df

combined_specs = [
    ("borusyak_velocity_static_effects.csv", "borusyak_velocity_static_effects_all.csv"),
    ("borusyak_velocity_dynamic_effects.csv", "borusyak_velocity_dynamic_effects_all.csv"),
    ("borusyak_velocity_input_summary.csv", "borusyak_velocity_input_summary_all.csv"),
    ("borusyak_velocity_panel_checks.csv", "borusyak_velocity_panel_checks_all.csv"),
]

for src_name, out_name in combined_specs:
    parts = []

    for label in labels:
        df = read_if_exists(label, src_name)
        if df is not None:
            parts.append(df)

    if parts:
        combined = pd.concat(parts, ignore_index=True)
        out = out_root / out_name
        combined.to_csv(out, index=False)
        print(f"Saved: {out}")
    else:
        print(f"WARNING: no input files found for {src_name}")

static_path = out_root / "borusyak_velocity_static_effects_all.csv"
if static_path.exists():
    static = pd.read_csv(static_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in static.columns:
            static[f"{col}_pct"] = static[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(float(x)) - 1.0) * 100.0
            )

    paper_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "estimate",
        "estimate_pct",
        "conf_low",
        "conf_low_pct",
        "conf_high",
        "conf_high_pct",
        "std_error",
        "p_value",
        "note",
    ]
    paper_cols = [c for c in paper_cols if c in static.columns]

    paper = static[paper_cols].copy()
    out = summary_dir / "borusyak_velocity_static_effects_paper_ready.csv"
    paper.to_csv(out, index=False)
    print(f"Saved: {out}")

    if {"panel", "outcome", "estimate_pct"}.issubset(paper.columns):
        wide = paper.pivot_table(
            index=["panel"],
            columns=["outcome"],
            values=["estimate_pct", "conf_low_pct", "conf_high_pct"],
            aggfunc="first",
        )
        wide.columns = ["_".join([str(x) for x in col if str(x) != ""]) for col in wide.columns]
        wide = wide.reset_index()
        out = summary_dir / "borusyak_velocity_static_effects_wide.csv"
        wide.to_csv(out, index=False)
        print(f"Saved: {out}")

dynamic_path = out_root / "borusyak_velocity_dynamic_effects_all.csv"
if dynamic_path.exists():
    dynamic = pd.read_csv(dynamic_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in dynamic.columns:
            dynamic[f"{col}_pct"] = dynamic[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(float(x)) - 1.0) * 100.0
            )

    out = summary_dir / "borusyak_velocity_dynamic_effects_percent.csv"
    dynamic.to_csv(out, index=False)
    print(f"Saved: {out}")

    plot_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "time",
        "estimate",
        "conf_low",
        "conf_high",
        "estimate_pct",
        "conf_low_pct",
        "conf_high_pct",
        "significant",
    ]
    plot_cols = [c for c in plot_cols if c in dynamic.columns]

    out = summary_dir / "borusyak_velocity_dynamic_effects_plot_ready.csv"
    dynamic[plot_cols].to_csv(out, index=False)
    print(f"Saved: {out}")

notes = summary_dir / "borusyak_velocity_summary_notes.txt"
notes.write_text(
    "Python velocity Borusyak DiD completed for panel variants: "
    + ", ".join(labels)
    + ". Outcomes are log_commits and log_lines_added. "
    + "Static effects summarize average post-adoption treatment effects. "
    + "Dynamic effects use event-time horizons -6 to 6 with pretrend horizons -6 to -2. "
    + "Primary Python panels are flexible and strict; window-driven panels are diagnostic if included.\\n",
    encoding="utf-8",
)
print(f"Saved: {notes}")
PY

  echo
  echo "============================================================"
  echo "run-py-2h completed successfully."
  echo "Completed:       $(date)"
  echo "Output root:     ${OUT_ROOT}"
  echo "Summary dir:     ${SUMMARY_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
#
# Reused logic:
#   This wrapper is adapted from run9h-did-velocity-borusyak.sh.
#   It does not call the old JS/TS shell wrapper.


