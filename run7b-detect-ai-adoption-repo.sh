#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run7b: Select candidate repos and/or clone existing candidate repos
# ============================================================

export GIT_TERMINAL_PROMPT=0

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M)}"
LOG_DIR="${LOG_DIR:-logs}"
CLONE_LOG="${LOG_DIR}/run7b_clone_log_${RUN_TS}.csv"

DATA_DIR="${DATA_DIR:-data_baseline_backup}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_adoption_test/data}"
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/top_100_clone_candidates.csv}"
ALL_ELIGIBLE_FILE="${OUTPUT_FILE%.csv}_all_eligible.csv"

CLONE_ROOT="${CLONE_ROOT:-../ai_code_complexity_study_repo_dataset}"

TOP_N="${TOP_N:-100}"
MIN_PRE_MONTHS="${MIN_PRE_MONTHS:-3}"
MIN_POST_MONTHS="${MIN_POST_MONTHS:-3}"
RANK_BY="${RANK_BY:-high_contributor}"
REQUIRE_CURSOR_EVIDENCE="${REQUIRE_CURSOR_EVIDENCE:-true}"

# Modes:
# SKIP_CANDIDATE_SELECTION=false:
#   run find_repo_pre_post_ai_adoption.py first.
#
# SKIP_CANDIDATE_SELECTION=true:
#   use existing OUTPUT_FILE directly.
#
# INSPECT_ONLY=true,  INSPECT_CLONE=false:
#   create/check candidate CSV only.
#
# INSPECT_ONLY=false, INSPECT_CLONE=true:
#   clone repos in OUTPUT_FILE.

SKIP_CANDIDATE_SELECTION="${SKIP_CANDIDATE_SELECTION:-false}"
INSPECT_ONLY="${INSPECT_ONLY:-true}"
INSPECT_CLONE="${INSPECT_CLONE:-false}"

# Optional: limit clone count for testing.
# Use 0 to clone all rows in OUTPUT_FILE.
MAX_CLONES="${MAX_CLONES:-0}"

# Generic post-clone status check.
CHECK_CLONE_STATUS="${CHECK_CLONE_STATUS:-true}"
CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV:-}"
CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-${OUTPUT_DIR}/clone_status_merged.csv}"
CHECK_TOP_PRINT="${CHECK_TOP_PRINT:-80}"

is_true() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

print_config() {
  echo "============================================================"
  echo "run7b: candidate selection and repository cloning"
  echo "Data dir:                  ${DATA_DIR}"
  echo "Output dir:                ${OUTPUT_DIR}"
  echo "Candidate file:            ${OUTPUT_FILE}"
  echo "All eligible file:         ${ALL_ELIGIBLE_FILE}"
  echo "Clone root:                ${CLONE_ROOT}"
  echo "Top N:                     ${TOP_N}"
  echo "Min pre months:            ${MIN_PRE_MONTHS}"
  echo "Min post months:           ${MIN_POST_MONTHS}"
  echo "Rank by:                   ${RANK_BY}"
  echo "Require Cursor evidence:   ${REQUIRE_CURSOR_EVIDENCE}"
  echo "Skip candidate selection:  ${SKIP_CANDIDATE_SELECTION}"
  echo "Inspect only:              ${INSPECT_ONLY}"
  echo "Inspect clone:             ${INSPECT_CLONE}"
  echo "Max clones:                ${MAX_CLONES}"
  echo "Clone log:                 ${CLONE_LOG}"
  echo "Check clone status:        ${CHECK_CLONE_STATUS}"
  echo "Check languages CSV:       ${CHECK_LANGUAGES_CSV}"
  echo "Check output file:         ${CHECK_OUTPUT_FILE}"
  echo "============================================================"
  echo
}

validate_mode() {
  if is_true "${INSPECT_ONLY}" && is_true "${INSPECT_CLONE}"; then
    echo "ERROR: INSPECT_ONLY and INSPECT_CLONE cannot both be true."
    exit 1
  fi

  if is_true "${SKIP_CANDIDATE_SELECTION}" && [[ ! -f "${OUTPUT_FILE}" ]]; then
    echo "ERROR: SKIP_CANDIDATE_SELECTION=true but candidate file not found:"
    echo "  ${OUTPUT_FILE}"
    exit 1
  fi
}

run_candidate_selection() {
  if is_true "${SKIP_CANDIDATE_SELECTION}"; then
    echo "** Skip candidate selection"
    echo "------------------------------------------------------------"
    echo "Using existing candidate file:"
    echo "  ${OUTPUT_FILE}"
    echo
    return
  fi

  mkdir -p "${OUTPUT_DIR}"

  echo "** Select candidate repositories"
  echo "------------------------------------------------------------"

  cmd=(
    python proc_scripts/find_repo_pre_post_ai_adoption.py
    --data-dir "${DATA_DIR}"
    --top-n "${TOP_N}"
    --min-pre-months "${MIN_PRE_MONTHS}"
    --min-post-months "${MIN_POST_MONTHS}"
    --rank-by "${RANK_BY}"
    --output "${OUTPUT_FILE}"
  )

  if is_true "${REQUIRE_CURSOR_EVIDENCE}"; then
    cmd+=(--require-cursor-evidence)
  fi

  "${cmd[@]}"
  echo
}

clone_candidates() {
  echo
  echo "** Git-clone candidate repositories"
  echo "------------------------------------------------------------"

  mkdir -p "${LOG_DIR}"

  python proc_scripts/clone_repos_v2.py \
    --repos-file "${OUTPUT_FILE}" \
    --repo-column repo_name \
    --clone-root "${CLONE_ROOT}" \
    --logs-dir "${LOG_DIR}" \
    --log-prefix run7b_clone_log \
    --timestamp "${RUN_TS}" \
    --max-repos "${MAX_CLONES}"
}

check_clone_status() {
  if ! is_true "${CHECK_CLONE_STATUS}"; then
    return
  fi

  echo
  echo "** Check cloned repositories"
  echo "------------------------------------------------------------"

  if [[ ! -f "${OUTPUT_FILE}" ]]; then
    echo "ERROR: candidate file not found: ${OUTPUT_FILE}"
    exit 1
  fi

  if [[ ! -f "${CLONE_LOG}" ]]; then
    echo "ERROR: clone log not found: ${CLONE_LOG}"
    exit 1
  fi

  python - "${OUTPUT_FILE}" "${CLONE_LOG}" "${CHECK_LANGUAGES_CSV}" "${CHECK_OUTPUT_FILE}" "${CHECK_TOP_PRINT}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

candidates_file = sys.argv[1]
clone_log_file = sys.argv[2]
languages_csv = sys.argv[3]
check_output_file = sys.argv[4]
top_print = int(sys.argv[5])

candidates = pd.read_csv(candidates_file)
log = pd.read_csv(clone_log_file)

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

Path(check_output_file).parent.mkdir(parents=True, exist_ok=True)
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

print(f"Top {top_print} cloned/check rows:")
if len(report_df) == 0:
    print("(No rows.)")
else:
    print(report_df[cols].head(top_print).to_string(index=False))
PY
}

main() {
  print_config
  validate_mode
  run_candidate_selection

  if is_true "${INSPECT_CLONE}"; then
    clone_candidates
    check_clone_status
  else
    echo "INSPECT_ONLY mode: candidate CSV was created/checked, but repositories were not cloned."
  fi

  echo
  echo "run7b completed successfully."
}

main "$@"
