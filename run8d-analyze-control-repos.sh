#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run8d: Analyze usable JS/TS matched control repositories
# ============================================================
# This wrapper calls proc_scripts/analyze_repos_v2.py on the
# usable cloned control repository sample created by run8c.
#
# Cache behavior:
#   1. If all required output files exist and cover all repos in
#      REPOS_FILE, skip the expensive analysis.
#   2. If output files exist but some repos are missing, analyze
#      only the missing repos and merge the new outputs.
#   3. Use FORCE_RERUN=true to ignore existing outputs.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8d_analyze_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_repos_v2.py}"

CACHE_CHECK_SCRIPT="${CACHE_CHECK_SCRIPT:-proc_scripts/check_cache_control_repos.py}"

REPOS_FILE="${REPOS_FILE:-tmp_jsts_test/data/jsts_control_clone_usable_repos_main_398.csv}"
CLONE_DIR="${CLONE_DIR:-../ai_code_complexity_study_jsts_control_repo_dataset}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data/jsts_did_control}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-2}"
MAX_REPOS="${MAX_REPOS:-5}"
SHUFFLE="${SHUFFLE:-false}"

# Cache controls.
SKIP_IF_COMPLETE="${SKIP_IF_COMPLETE:-true}"
INCREMENTAL_IF_PARTIAL="${INCREMENTAL_IF_PARTIAL:-true}"
FORCE_RERUN="${FORCE_RERUN:-false}"

REPO_TS_FILE="${OUTPUT_DIR}/ts_repos_${AGGREGATION}ly.csv"
CONTRIB_TS_FILE="${OUTPUT_DIR}/ts_contributors_${AGGREGATION}ly.csv"
CURSOR_COMMITS_FILE="${OUTPUT_DIR}/cursor_commits.csv"
ADOPTION_FILE="${OUTPUT_DIR}/ai_adoption_dates.csv"
MANIFEST_FILE="${OUTPUT_DIR}/run8d_analyzed_repos_manifest.csv"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" bak

echo "============================================================" | tee "${LOG_FILE}"
echo "run8d: analyze usable JS/TS matched control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:              ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:          ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Cache check script:     ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:             ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:              ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Output dir:             ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Aggregation:            ${AGGREGATION}" | tee -a "${LOG_FILE}"
echo "Num processes:          ${NUM_PROCESSES}" | tee -a "${LOG_FILE}"
echo "Max repos:              ${MAX_REPOS}" | tee -a "${LOG_FILE}"
echo "Shuffle:                ${SHUFFLE}" | tee -a "${LOG_FILE}"
echo "Skip if complete:       ${SKIP_IF_COMPLETE}" | tee -a "${LOG_FILE}"
echo "Incremental if partial: ${INCREMENTAL_IF_PARTIAL}" | tee -a "${LOG_FILE}"
echo "Force rerun:            ${FORCE_RERUN}" | tee -a "${LOG_FILE}"
echo "Log file:               ${LOG_FILE}" | tee -a "${LOG_FILE}"
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

CACHE_STATUS="run_full"
RUN_REPOS_FILE="${REPOS_FILE}"
RUN_OUTPUT_DIR="${OUTPUT_DIR}"
MISSING_REPOS_FILE="${OUTPUT_DIR}/run8d_missing_repos_${RUN_TS}.csv"
TMP_OUTPUT_DIR="${OUTPUT_DIR}/_incremental_${RUN_TS}"

# Cache checking is meaningful only for full runs.
# For smoke tests with MAX_REPOS != 0, run normally.
if [[ "${MAX_REPOS}" == "0" && "${FORCE_RERUN}" != "true" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Cache check" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  if [[ ! -f "${CACHE_CHECK_SCRIPT}" ]]; then
    echo "ERROR: cache check script not found: ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
    exit 1
  fi

  CACHE_REPORT="${OUTPUT_DIR}/run8d_cache_check_${RUN_TS}.txt"

  python "${CACHE_CHECK_SCRIPT}" \
    "${REPOS_FILE}" \
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
    echo "Existing run8d outputs are complete for the current REPOS_FILE." | tee -a "${LOG_FILE}"
    echo "Skipping expensive repository-history analysis." | tee -a "${LOG_FILE}"
    echo | tee -a "${LOG_FILE}"

    echo "** Output files" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
    for f in "${REPO_TS_FILE}" "${CONTRIB_TS_FILE}" "${CURSOR_COMMITS_FILE}" "${ADOPTION_FILE}"; do
      wc -l "${f}" | tee -a "${LOG_FILE}"
    done

    echo | tee -a "${LOG_FILE}"
    echo "============================================================" | tee -a "${LOG_FILE}"
    echo "run8d skipped because outputs already exist and are complete." | tee -a "${LOG_FILE}"
    echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
    echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
    echo "============================================================" | tee -a "${LOG_FILE}"
    exit 0
  fi

  if [[ "${CACHE_STATUS}" == "partial" && "${INCREMENTAL_IF_PARTIAL}" == "true" ]]; then
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

CMD=(
  python "${PY_SCRIPT}"
  --repos-file "${RUN_REPOS_FILE}"
  --clone-dir "${CLONE_DIR}"
  --output-dir "${RUN_OUTPUT_DIR}"
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

# If we ran only missing repos, merge temporary outputs into main outputs.
if [[ "${RUN_OUTPUT_DIR}" != "${OUTPUT_DIR}" ]]; then
  echo | tee -a "${LOG_FILE}"
  echo "** Merge incremental run8d outputs" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  python - \
    "${OUTPUT_DIR}" \
    "${RUN_OUTPUT_DIR}" \
    "${AGGREGATION}" \
    "${REPOS_FILE}" \
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
  # Save the manifest only after a full run.
  # Do not save a full manifest after a smoke run such as MAX_REPOS=5.
  if [[ "${MAX_REPOS}" == "0" ]]; then
    python - "${REPOS_FILE}" "${MANIFEST_FILE}" <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path
import pandas as pd

repos_file = Path(sys.argv[1])
manifest_file = Path(sys.argv[2])

repos = pd.read_csv(repos_file)

if "repo_name" in repos.columns:
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    (
        repos[["repo_name"]]
        .assign(repo_name=lambda d: d["repo_name"].astype(str).str.strip())
        .query("repo_name != '' and repo_name != 'nan'")
        .drop_duplicates("repo_name")
        .to_csv(manifest_file, index=False)
    )
    print(f"Manifest saved: {manifest_file}")
else:
    print(f"WARNING: repo_name column missing in {repos_file}; manifest not saved")
PY
  else
    echo "Smoke run detected because MAX_REPOS=${MAX_REPOS}; manifest not saved." | tee -a "${LOG_FILE}"
  fi
fi

echo | tee -a "${LOG_FILE}"
echo "** Output files" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in "${REPO_TS_FILE}" "${CONTRIB_TS_FILE}" "${CURSOR_COMMITS_FILE}" "${ADOPTION_FILE}"; do
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

adoption_path = Path("${ADOPTION_FILE}")
cursor_commits_path = Path("${CURSOR_COMMITS_FILE}")

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
