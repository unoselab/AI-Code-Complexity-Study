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
