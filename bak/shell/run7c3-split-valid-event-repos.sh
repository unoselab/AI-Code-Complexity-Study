#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7c3: Split usable cloned treatment repos by event_month
# ============================================================
# This script reads the usable cloned JS/TS treatment repo file
# created by run7c2 and produces:
#   1. valid repos with event_month
#   2. diagnostic repos missing event_month
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run7c3_split_valid_event_repos_${RUN_TS}.log}"

INPUT_FILE="${INPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event.csv}"
VALID_OUTPUT_FILE="${VALID_OUTPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv}"
MISSING_OUTPUT_FILE="${MISSING_OUTPUT_FILE:-tmp_jsts_test/data/jsts_treatment_clone_usable_missing_event_month.csv}"

mkdir -p "${LOG_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run7c3: split usable cloned repos by event_month" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Log file:             ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Input file:           ${INPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Valid output file:    ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Missing output file:  ${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "ERROR: input file not found: ${INPUT_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run7c2-create-clone-usable-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

set +e
python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

input_path = Path("${INPUT_FILE}")
valid_output_path = Path("${VALID_OUTPUT_FILE}")
missing_output_path = Path("${MISSING_OUTPUT_FILE}")

df = pd.read_csv(input_path)

if "event_month" not in df.columns:
    raise SystemExit("ERROR: input file must contain event_month column.")

valid = df[df["event_month"].notna()].copy()
missing = df[df["event_month"].isna()].copy()

valid_output_path.parent.mkdir(parents=True, exist_ok=True)
missing_output_path.parent.mkdir(parents=True, exist_ok=True)

valid.to_csv(valid_output_path, index=False)
missing.to_csv(missing_output_path, index=False)

print("Input file:", input_path)
print("Input rows:", len(df))
print("Valid rows with event_month:", len(valid))
print("Missing event_month rows:", len(missing))
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
cols = ["repo_name", "repo_primary_language", "status", "target_dir"]
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
echo "run7c3 finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Valid output file: ${VALID_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Missing output file: ${MISSING_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"

exit "${run_status}"
