#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1b: Prepare Python treatment repository clone status
# ============================================================
# Purpose:
#   Prepare the clone-status input required by the next Python treatment
#   pipeline step without repeating an expensive Git clone operation.
#
# Default behavior:
#   - Reuse the previous clone-status file from bak/repo_python.
#   - Verify that each referenced repository still has a local .git directory.
#   - Write one current main clone-status file under repo_python.
#   - Write logs, snapshots, QC, and missing-clone diagnostics under
#     repo_python/tmp/run-py-1b.
#
# Main input:
#   repo_python/treatment_python_repos.csv
#
# Reuse input:
#   bak/repo_python/treatment_python_clone_status.csv
#
# Existing clone root:
#   ../treatment-repos
#
# Main output:
#   repo_python/treatment_python_clone_status.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1b/
#     - run log
#     - timestamped clone-status snapshot
#     - reuse QC summary
#     - missing or invalid clone rows
#     - clone log CSV only when cloning is explicitly enabled
#
# Typical reuse run:
#   bash run-py-1b-detect-ai-adoption-repo.sh
#
# Explicit clone run:
#   bash run-py-1b-detect-ai-adoption-repo.sh \
#     --reuse-existing-clones FALSE \
#     --max-clones 0
#
# Important:
#   The default mode never runs git clone or git pull.
# ============================================================

export GIT_TERMINAL_PROMPT=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"

# ------------------------------------------------------------
# Default configuration
# ------------------------------------------------------------
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PYTHON_BIN="${PYTHON_BIN:-python}"

MAIN_DIR="${MAIN_DIR:-repo_python}"
TMP_ROOT="${TMP_ROOT:-${MAIN_DIR}/tmp}"
TMP_DIR="${TMP_DIR:-${TMP_ROOT}/run-py-1b}"
BACKUP_REPO_DIR="${BACKUP_REPO_DIR:-bak/repo_python}"

TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${MAIN_DIR}/treatment_python_repos.csv}"
CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${MAIN_DIR}/treatment_python_clone_status.csv}"
BACKUP_CLONE_STATUS_FILE="${BACKUP_CLONE_STATUS_FILE:-${BACKUP_REPO_DIR}/treatment_python_clone_status.csv}"

CLONE_ROOT="${CLONE_ROOT:-../treatment-repos}"
REUSE_EXISTING_CLONES="${REUSE_EXISTING_CLONES:-TRUE}"
MAX_CLONES="${MAX_CLONES:-0}"
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-run-py-1b_treatment_clone_log}"
CLONE_LOG_CSV="${TMP_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

CLONE_STATUS_SNAPSHOT="${TMP_DIR}/treatment_python_clone_status_${RUN_TS}.csv"
REUSE_QC_FILE="${TMP_DIR}/treatment_python_clone_reuse_qc_${RUN_TS}.csv"
MISSING_CLONES_FILE="${TMP_DIR}/treatment_python_clone_missing_${RUN_TS}.csv"
LOG_FILE="${LOG_FILE:-}"

CHECK_TOP_PRINT="${CHECK_TOP_PRINT:-30}"

usage() {
  cat <<'USAGE'
Usage:
  bash run-py-1b-detect-ai-adoption-repo.sh [options]

Options:
  --reuse-existing-clones TRUE|FALSE
  --backup-repo-dir PATH
  --backup-clone-status-file PATH
  --clone-root PATH
  --max-clones N
  --existing-action skip|pull
  --main-dir PATH
  --tmp-dir PATH
  --help
USAGE
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
      exit 2
      ;;
  esac
}

# ------------------------------------------------------------
# CLI overrides
# ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse-existing-clones)
      REUSE_EXISTING_CLONES="$(normalize_bool "${2:-}")"
      shift 2
      ;;
    --backup-repo-dir)
      BACKUP_REPO_DIR="${2:-}"
      BACKUP_CLONE_STATUS_FILE="${BACKUP_REPO_DIR}/treatment_python_clone_status.csv"
      shift 2
      ;;
    --backup-clone-status-file)
      BACKUP_CLONE_STATUS_FILE="${2:-}"
      shift 2
      ;;
    --clone-root)
      CLONE_ROOT="${2:-}"
      shift 2
      ;;
    --max-clones)
      MAX_CLONES="${2:-}"
      shift 2
      ;;
    --existing-action)
      EXISTING_ACTION="${2:-}"
      shift 2
      ;;
    --main-dir)
      MAIN_DIR="${2:-}"
      TREATMENT_REPOS_FILE="${MAIN_DIR}/treatment_python_repos.csv"
      CLONE_STATUS_FILE="${MAIN_DIR}/treatment_python_clone_status.csv"
      shift 2
      ;;
    --tmp-dir)
      TMP_DIR="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REUSE_EXISTING_CLONES="$(normalize_bool "${REUSE_EXISTING_CLONES}")"

if [[ ! "${MAX_CLONES}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --max-clones must be a non-negative integer. Got: ${MAX_CLONES}" >&2
  exit 2
fi

if [[ "${EXISTING_ACTION}" != "skip" && "${EXISTING_ACTION}" != "pull" ]]; then
  echo "ERROR: --existing-action must be skip or pull. Got: ${EXISTING_ACTION}" >&2
  exit 2
fi

# Recompute dependent extra-output paths after CLI parsing.
CLONE_LOG_CSV="${TMP_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"
CLONE_STATUS_SNAPSHOT="${TMP_DIR}/treatment_python_clone_status_${RUN_TS}.csv"
REUSE_QC_FILE="${TMP_DIR}/treatment_python_clone_reuse_qc_${RUN_TS}.csv"
MISSING_CLONES_FILE="${TMP_DIR}/treatment_python_clone_missing_${RUN_TS}.csv"
if [[ -z "${LOG_FILE}" ]]; then
  LOG_FILE="${TMP_DIR}/run-py-1b_detect_ai_adoption_repo_${RUN_TS}.log"
fi

mkdir -p "${MAIN_DIR}" "${TMP_DIR}"

{
  echo "============================================================"
  echo "run-py-1b: Prepare Python treatment repository clone status"
  echo "Started:                    $(date)"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Reuse existing clones:      ${REUSE_EXISTING_CLONES}"
  echo "Main input:                 ${TREATMENT_REPOS_FILE}"
  echo "Backup repo directory:      ${BACKUP_REPO_DIR}"
  echo "Backup clone status:        ${BACKUP_CLONE_STATUS_FILE}"
  echo "Existing clone root:        ${CLONE_ROOT}"
  echo "Main output:                ${CLONE_STATUS_FILE}"
  echo "Extra output directory:     ${TMP_DIR}"
  echo "Status snapshot:            ${CLONE_STATUS_SNAPSHOT}"
  echo "Reuse QC:                   ${REUSE_QC_FILE}"
  echo "Missing clone diagnostics:  ${MISSING_CLONES_FILE}"
  echo "Clone log CSV:              ${CLONE_LOG_CSV}"
  echo "Max clones:                 ${MAX_CLONES}"
  echo "Existing action:            ${EXISTING_ACTION}"
  echo "Log file:                   ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

# ------------------------------------------------------------
# Validate common input
# ------------------------------------------------------------
if [[ ! -s "${TREATMENT_REPOS_FILE}" ]]; then
  echo "ERROR: treatment repository input not found or empty: ${TREATMENT_REPOS_FILE}" | tee -a "${LOG_FILE}"
  echo "Run run-py-1a-count-repo.sh first." | tee -a "${LOG_FILE}"
  exit 1
fi

# Remove only current-run main and diagnostic outputs.
rm -f \
  "${CLONE_STATUS_FILE}" \
  "${CLONE_STATUS_SNAPSHOT}" \
  "${REUSE_QC_FILE}" \
  "${MISSING_CLONES_FILE}" \
  "${CLONE_LOG_CSV}"

# ------------------------------------------------------------
# Default path: reuse and verify existing clone results
# ------------------------------------------------------------
if [[ "${REUSE_EXISTING_CLONES}" == "TRUE" ]]; then
  if [[ ! -s "${BACKUP_CLONE_STATUS_FILE}" ]]; then
    echo "ERROR: backup clone-status file not found or empty: ${BACKUP_CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
    echo "The default mode does not clone repositories." | tee -a "${LOG_FILE}"
    echo "Provide the correct backup file or explicitly use --reuse-existing-clones FALSE." | tee -a "${LOG_FILE}"
    exit 1
  fi

  echo | tee -a "${LOG_FILE}"
  echo "** Reuse and verify existing Python treatment clones" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  "${PYTHON_BIN}" - \
    "${TREATMENT_REPOS_FILE}" \
    "${BACKUP_CLONE_STATUS_FILE}" \
    "${CLONE_ROOT}" \
    "${CLONE_STATUS_FILE}" \
    "${REUSE_QC_FILE}" \
    "${MISSING_CLONES_FILE}" \
    "${CHECK_TOP_PRINT}" \
    <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path

import pandas as pd

candidates_file = Path(sys.argv[1])
backup_status_file = Path(sys.argv[2])
clone_root = Path(sys.argv[3]).expanduser().resolve()
output_file = Path(sys.argv[4])
qc_file = Path(sys.argv[5])
missing_file = Path(sys.argv[6])
top_print = int(sys.argv[7])
project_root = Path.cwd().resolve()

candidates = pd.read_csv(candidates_file)
backup = pd.read_csv(backup_status_file)

if "repo_name" not in candidates.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {candidates_file}")
if "repo_name" not in backup.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {backup_status_file}")

candidates = candidates.copy()
backup = backup.copy()

candidates["repo_name"] = candidates["repo_name"].astype(str).str.strip()
backup["repo_name"] = backup["repo_name"].astype(str).str.strip()

candidate_duplicate_rows = int(candidates.duplicated("repo_name", keep=False).sum())
backup_duplicate_rows = int(backup.duplicated("repo_name", keep=False).sum())

if candidate_duplicate_rows:
    raise SystemExit(
        f"ERROR: duplicate repo_name rows in current candidate file: {candidate_duplicate_rows}"
    )

backup = backup.drop_duplicates("repo_name", keep="last")
backup_columns = [c for c in ["repo_name", "status", "target_dir", "note"] if c in backup.columns]
backup_small = backup[backup_columns].copy()
backup_small = backup_small.rename(
    columns={
        "status": "backup_status",
        "target_dir": "backup_target_dir",
        "note": "backup_note",
    }
)

merged = candidates.merge(backup_small, on="repo_name", how="left", validate="one_to_one")


def choose_target_dir(repo_name: str, backup_target: object) -> Path:
    value = "" if pd.isna(backup_target) else str(backup_target).strip()
    if value:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if candidate.exists():
            return candidate
    return (clone_root / repo_name.replace("/", "_")).resolve()


rows = []
for row in merged.to_dict(orient="records"):
    repo_name = row["repo_name"]
    target_dir = choose_target_dir(repo_name, row.get("backup_target_dir"))
    git_dir = target_dir / ".git"
    verified = target_dir.is_dir() and git_dir.exists()

    backup_status = row.get("backup_status")
    backup_status_text = "missing" if pd.isna(backup_status) else str(backup_status)

    if verified:
        status = "skipped_existing"
        note = (
            "reused_backup_clone_status="
            f"{backup_status_text};verified_existing_git_repo"
        )
    else:
        status = "failed"
        note = (
            "reused_backup_clone_status="
            f"{backup_status_text};local_git_repo_not_found"
        )

    output_row = {
        key: value
        for key, value in row.items()
        if key not in {"backup_status", "backup_target_dir", "backup_note"}
    }
    output_row.update(
        {
            "status": status,
            "target_dir": str(target_dir),
            "note": note,
        }
    )
    rows.append(output_row)

result = pd.DataFrame(rows)
missing = result[result["status"] == "failed"].copy()

matched_backup_rows = int(merged["backup_status"].notna().sum()) if "backup_status" in merged else 0
verified_rows = int(result["status"].eq("skipped_existing").sum())
missing_rows = int(result["status"].eq("failed").sum())

qc = pd.DataFrame(
    [
        {"check": "current_candidate_rows", "value": len(candidates)},
        {"check": "current_candidate_unique_repos", "value": candidates["repo_name"].nunique()},
        {"check": "current_candidate_duplicate_rows", "value": candidate_duplicate_rows},
        {"check": "backup_status_rows", "value": len(pd.read_csv(backup_status_file))},
        {"check": "backup_status_unique_repos", "value": backup["repo_name"].nunique()},
        {"check": "backup_status_duplicate_rows", "value": backup_duplicate_rows},
        {"check": "candidate_rows_matched_to_backup_status", "value": matched_backup_rows},
        {"check": "verified_existing_git_repos", "value": verified_rows},
        {"check": "missing_or_invalid_git_repos", "value": missing_rows},
        {"check": "main_output_rows", "value": len(result)},
        {"check": "main_output_unique_repos", "value": result["repo_name"].nunique()},
        {"check": "row_count_preserved", "value": int(len(result) == len(candidates))},
    ]
)

output_file.parent.mkdir(parents=True, exist_ok=True)
qc_file.parent.mkdir(parents=True, exist_ok=True)
missing_file.parent.mkdir(parents=True, exist_ok=True)

result.to_csv(output_file, index=False)
qc.to_csv(qc_file, index=False)
missing.to_csv(missing_file, index=False)

print("Current candidate rows:", len(candidates))
print("Backup status rows after deduplication:", len(backup))
print("Candidate rows matched to backup status:", matched_backup_rows)
print("Verified existing Git repositories:", verified_rows)
print("Missing or invalid Git repositories:", missing_rows)
print("Saved main clone status:", output_file)
print("Saved reuse QC:", qc_file)
print("Saved missing-clone diagnostics:", missing_file)
print()
print("Status counts:")
print(result["status"].value_counts(dropna=False).to_string())
print()
print(f"Top {top_print} output rows:")
preview_columns = [
    c
    for c in ["repo_name", "repo_primary_language", "status", "target_dir", "note"]
    if c in result.columns
]
print(result[preview_columns].head(top_print).to_string(index=False))
PY

# ------------------------------------------------------------
# Optional path: explicitly run the reusable clone script
# ------------------------------------------------------------
else
  PY_SCRIPT="proc_scripts/clone_repos_v2.py"

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python clone script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
    exit 1
  fi

  mkdir -p "${CLONE_ROOT}"
  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  echo | tee -a "${LOG_FILE}"
  echo "** Explicit Git clone mode" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  set +e
  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --repos-file "${TREATMENT_REPOS_FILE}" \
    --repo-column repo_name \
    --clone-root "${CLONE_ROOT}" \
    --logs-dir "${TMP_DIR}" \
    --log-prefix "${CLONE_LOG_PREFIX}" \
    --timestamp "${RUN_TS}" \
    --max-repos "${MAX_CLONES}" \
    --existing-action "${EXISTING_ACTION}" \
    2>&1 | tee -a "${LOG_FILE}"
  clone_exit=${PIPESTATUS[0]}
  set -e

  if [[ "${clone_exit}" -ne 0 ]]; then
    echo "ERROR: clone script failed with exit code ${clone_exit}" | tee -a "${LOG_FILE}"
    exit "${clone_exit}"
  fi

  if [[ ! -s "${CLONE_LOG_CSV}" ]]; then
    echo "ERROR: expected clone log was not created: ${CLONE_LOG_CSV}" | tee -a "${LOG_FILE}"
    exit 1
  fi

  "${PYTHON_BIN}" - \
    "${TREATMENT_REPOS_FILE}" \
    "${CLONE_LOG_CSV}" \
    "${CLONE_STATUS_FILE}" \
    "${REUSE_QC_FILE}" \
    "${MISSING_CLONES_FILE}" \
    "${CHECK_TOP_PRINT}" \
    <<'PY' 2>&1 | tee -a "${LOG_FILE}"
import sys
from pathlib import Path

import pandas as pd

candidates_file = Path(sys.argv[1])
clone_log_file = Path(sys.argv[2])
output_file = Path(sys.argv[3])
qc_file = Path(sys.argv[4])
missing_file = Path(sys.argv[5])
top_print = int(sys.argv[6])

candidates = pd.read_csv(candidates_file)
clone_log = pd.read_csv(clone_log_file)

if "repo_name" not in candidates.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {candidates_file}")
if "repo_name" not in clone_log.columns:
    raise SystemExit(f"ERROR: repo_name column missing in {clone_log_file}")

candidates["repo_name"] = candidates["repo_name"].astype(str).str.strip()
clone_log["repo_name"] = clone_log["repo_name"].astype(str).str.strip()
clone_log = clone_log.drop_duplicates("repo_name", keep="last")

result = candidates.merge(clone_log, on="repo_name", how="left", validate="one_to_one")
missing = result[~result["status"].isin({"cloned", "skipped_existing", "updated_existing"})].copy()

qc = pd.DataFrame(
    [
        {"check": "current_candidate_rows", "value": len(candidates)},
        {"check": "clone_log_rows", "value": len(clone_log)},
        {"check": "usable_clone_rows", "value": int(result["status"].isin({"cloned", "skipped_existing", "updated_existing"}).sum())},
        {"check": "missing_or_failed_clone_rows", "value": len(missing)},
        {"check": "main_output_rows", "value": len(result)},
        {"check": "row_count_preserved", "value": int(len(result) == len(candidates))},
    ]
)

output_file.parent.mkdir(parents=True, exist_ok=True)
qc_file.parent.mkdir(parents=True, exist_ok=True)
missing_file.parent.mkdir(parents=True, exist_ok=True)

result.to_csv(output_file, index=False)
qc.to_csv(qc_file, index=False)
missing.to_csv(missing_file, index=False)

print("Saved main clone status:", output_file)
print("Saved clone QC:", qc_file)
print("Saved missing or failed rows:", missing_file)
print()
print("Status counts:")
print(result["status"].fillna("(missing)").value_counts().to_string())
print()
print(f"Top {top_print} output rows:")
preview_columns = [
    c
    for c in ["repo_name", "repo_primary_language", "status", "target_dir", "note"]
    if c in result.columns
]
print(result[preview_columns].head(top_print).to_string(index=False))
PY
fi

# ------------------------------------------------------------
# Verify and snapshot main output
# ------------------------------------------------------------
if [[ ! -s "${CLONE_STATUS_FILE}" ]]; then
  echo "ERROR: main clone-status output was not created: ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

cp "${CLONE_STATUS_FILE}" "${CLONE_STATUS_SNAPSHOT}"

MAIN_ROWS="$(awk 'END {if (NR > 0) print NR - 1; else print 0}' "${CLONE_STATUS_FILE}")"
MISSING_ROWS="$(awk 'END {if (NR > 0) print NR - 1; else print 0}' "${MISSING_CLONES_FILE}")"

{
  echo
  echo "============================================================"
  echo "run-py-1b output verification"
  echo "============================================================"
  echo "Main clone-status output:   ${CLONE_STATUS_FILE}"
  echo "Main repository rows:       ${MAIN_ROWS}"
  echo "Timestamped snapshot:       ${CLONE_STATUS_SNAPSHOT}"
  echo "QC output:                  ${REUSE_QC_FILE}"
  echo "Missing clone output:       ${MISSING_CLONES_FILE}"
  echo "Missing clone rows:         ${MISSING_ROWS}"
  echo
  echo "Main output preview:"
  head "${CLONE_STATUS_FILE}"
  echo
  echo "============================================================"
  echo "run-py-1b completed successfully."
  echo "Completed:                  $(date)"
  echo "Main pipeline input:        ${CLONE_STATUS_FILE}"
  echo "Extra outputs:              ${TMP_DIR}"
  echo "Git clone executed:         $([[ "${REUSE_EXISTING_CLONES}" == "TRUE" ]] && echo FALSE || echo TRUE)"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
