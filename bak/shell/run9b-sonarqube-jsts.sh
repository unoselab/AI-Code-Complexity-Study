#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run9b: Run SonarQube scan for JS/TS repo-month inputs
# ============================================================
# Usage:
#   TARGET=treatment NUM_PROCESSES=1 ./run9b-sonarqube-jsts.sh
#   TARGET=control   NUM_PROCESSES=1 ./run9b-sonarqube-jsts.sh
#
# This wrapper reuses proc_scripts/run_sonarqube_v2.py.
# It scans each repo-month latest_commit and collects SonarQube
# metrics such as ncloc, bugs, vulnerabilities, code_smells,
# duplicated_lines_density, cognitive_complexity, and technical_debt.
# ============================================================

TARGET="${TARGET:-treatment}"

if [[ "${TARGET}" != "treatment" && "${TARGET}" != "control" ]]; then
  echo "ERROR: TARGET must be either 'treatment' or 'control'. Got: ${TARGET}"
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run9b_sonarqube_jsts_${TARGET}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/run_sonarqube_v2.py}"
SONAR_ROOT="${SONAR_ROOT:-tmp_jsts_test/data/jsts_sonarqube_main}"

NUM_PROCESSES="${NUM_PROCESSES:-1}"
AGGREGATION="${AGGREGATION:-month}"

if [[ "${TARGET}" == "treatment" ]]; then
  INPUT_FILE="${INPUT_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
  OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly_scanned.csv}"
  CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_repo_dataset}"
else
  INPUT_FILE="${INPUT_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"
  OUTPUT_FILE="${OUTPUT_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly_scanned.csv}"
  CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_control_repo_dataset}"
fi

mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_FILE}")"

{
  echo "============================================================"
  echo "run9b: JS/TS SonarQube scan"
  echo "Started:       $(date)"
  echo "Target:        ${TARGET}"
  echo "Python script: ${PY_SCRIPT}"
  echo "Aggregation:   ${AGGREGATION}"
  echo "Input file:    ${INPUT_FILE}"
  echo "Output file:   ${OUTPUT_FILE}"
  echo "Clone dir:     ${CLONE_DIR}"
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

  if [[ -z "${SONAR_SCANNER_PATH:-}" ]]; then
    echo "WARNING: SONAR_SCANNER_PATH is not set in current shell. The Python script may load it from .env."
  fi

  if [[ -z "${SONAR_TOKEN:-}" ]]; then
    echo "WARNING: SONAR_TOKEN is not set in current shell. The Python script may load it from .env."
  fi

  if [[ -z "${SONAR_HOST:-}" ]]; then
    echo "WARNING: SONAR_HOST is not set in current shell. The Python script may load it from .env."
  fi

  echo "** Input summary before scan"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

path = Path("${INPUT_FILE}")
df = pd.read_csv(path)

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
print()

for col in metric_cols:
    if col in df.columns:
        print(f"{col}: {df[col].notna().sum()} / {len(df)} non-null")
    else:
        print(f"{col}: MISSING")
PY

  echo
  echo "============================================================"
  echo "run9b completed successfully."
  echo "Completed:   $(date)"
  echo "Target:      ${TARGET}"
  echo "Output file: ${OUTPUT_FILE}"
  echo "Log file:    ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
