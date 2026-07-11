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
