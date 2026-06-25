#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run8d: Analyze usable JS/TS matched control repositories
# ============================================================
# This wrapper calls proc_scripts/analyze_repos_v2.py on the
# usable cloned control repository sample created by run8c.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8d_analyze_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_repos_v2.py}"

REPOS_FILE="${REPOS_FILE:-tmp_jsts_test/data/jsts_control_clone_usable_repos_main_398.csv}"
CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_control_repo_dataset}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data/jsts_did_control}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-2}"
MAX_REPOS="${MAX_REPOS:-5}"
SHUFFLE="${SHUFFLE:-false}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run8d: analyze usable JS/TS matched control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:       ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:   ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:      ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:       ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:      ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:     ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:   ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:       ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Shuffle:         ${SHUFFLE}" | tee -a "${LOG_FILE}"
echo "Log file:        ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${REPOS_FILE}" ]]; then
  echo "ERROR: repos file not found: ${REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run8c-create-control-usable-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -d "${CLONE_DIR}" ]]; then
  echo "ERROR: clone directory not found: ${CLONE_DIR}" | tee -a "${LOG_FILE}"
  echo "Run run8b-clone-jsts-control-repos.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

echo "** Input control repo summary" | tee -a "${LOG_FILE}"
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
    print("Status counts:")
    print(df["status"].value_counts(dropna=False).to_string())

print()
print(df.head(20).to_string(index=False))
PY

CMD=(
  python "${PY_SCRIPT}"
  --repos-file "${REPOS_FILE}"
  --clone-dir "${CLONE_DIR}"
  --output-dir "${OUTPUT_DIR}"
  --aggregation "${AGGREGATION}"
  --num-processes "${NUM_PROCESSES}"
)

if [[ "${MAX_REPOS}" != "0" ]]; then
  CMD+=(--max-repos "${MAX_REPOS}")
fi

if [[ "${SHUFFLE}" == "true" ]]; then
  CMD+=(--shuffle)
fi

echo | tee -a "${LOG_FILE}"
echo "** Running control repository git-history analysis" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output files" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_DIR}/ts_repos_${AGGREGATION}ly.csv" \
  "${OUTPUT_DIR}/ts_contributors_${AGGREGATION}ly.csv" \
  "${OUTPUT_DIR}/cursor_commits.csv" \
  "${OUTPUT_DIR}/ai_adoption_dates.csv"
do
  if [[ -f "${f}" ]]; then
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "** Control Cursor-evidence QC" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
from pathlib import Path
import pandas as pd

adoption_path = Path("${OUTPUT_DIR}/ai_adoption_dates.csv")
cursor_commits_path = Path("${OUTPUT_DIR}/cursor_commits.csv")

if adoption_path.exists():
    ad = pd.read_csv(adoption_path)
    print("AI adoption date rows:", len(ad))
    if len(ad) > 0:
        print()
        print("WARNING: Cursor evidence was detected in control repositories.")
        cols = [c for c in ["repo_name", "adoption_month", "evidence_paths", "confidence"] if c in ad.columns]
        print(ad[cols].head(50).to_string(index=False))
else:
    print("AI adoption date file missing:", adoption_path)

if cursor_commits_path.exists():
    cc = pd.read_csv(cursor_commits_path)
    print()
    print("Cursor commit rows:", len(cc))
else:
    print()
    print("Cursor commit file missing. This is acceptable if no Cursor commits were detected.")
PY

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run8d completed successfully." | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
