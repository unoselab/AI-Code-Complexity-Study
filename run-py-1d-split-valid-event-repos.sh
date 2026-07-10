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
