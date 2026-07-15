#!/usr/bin/env bash
# Consolidated shell and Python sources generated on Tue Jul 14 03:30:08 PM CDT 2026

###############################################################################
# -- SHELL SCRIPT: run-py-1a-count-repo.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-1a: Count Python Cursor-adopting treatment repositories
# ============================================================
#
# Goal:
#   Prepare the first Python treatment-repository input file for
#   reproducing the paper's language-specific Appendix result.
#
# Main output policy:
#   repo_python/
#     - Keep only the analysis input needed by later pipeline steps.
#
# Extra output policy:
#   repo_python/tmp/
#     - Keep diagnostic subsets, logs, and verification artifacts.
#
# Main output:
#   repo_python/treatment_python_repos.csv
#
# Extra outputs:
#   repo_python/tmp/treatment_python_repos_bw6.csv
#   repo_python/tmp/run-py-1a_count_repo_<timestamp>.log
#
# Important:
#   This step reads the frozen baseline data and does not require Git cloning
#   or SonarQube scanning. Expensive cached artifacts under bak/repo_python
#   are not needed for run-py-1a and will be reused by later wrappers.
#
# Typical usage:
#   bash run-py-1a-count-repo.sh
#
# Optional overrides:
#   MIN_BALANCED_WINDOW=5 bash run-py-1a-count-repo.sh
#   OUTPUT_DIR=repo_python_test bash run-py-1a-count-repo.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"

# ------------------------------------------------------------
# Inputs and executable
# ------------------------------------------------------------
DATA_DIR="${DATA_DIR:-data_baseline_backup}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/count_repo_lang.py}"
PYTHON_BIN="${PYTHON_BIN:-python}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
GROUP_NAME="${GROUP_NAME:-Python}"
LANGUAGE="${LANGUAGE:-Python}"

# ------------------------------------------------------------
# Output directories
# ------------------------------------------------------------
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp}"

MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"
TOP_PRINT="${TOP_PRINT:-30}"

# Keep the main pipeline input in repo_python/.
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Keep the balanced-window diagnostic subset in repo_python/tmp/.
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-${TMP_DIR}/treatment_python_repos_bw${MIN_BALANCED_WINDOW}.csv}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1a_count_repo_${RUN_TS}.log}"

PANEL_FILE="${PANEL_FILE:-${DATA_DIR}/panel_event_monthly.csv}"
REPOS_FILE="${REPOS_FILE:-${DATA_DIR}/repos.csv}"

mkdir -p "${OUTPUT_DIR}" "${TMP_DIR}"

# Remove stale files so a failed run cannot be mistaken for a fresh result.
rm -f "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"

{
  echo "============================================================"
  echo "run-py-1a: Count Python Cursor-adopting treatment repositories"
  echo "Started:                    $(date)"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Baseline panel:             ${PANEL_FILE}"
  echo "Repository metadata:        ${REPOS_FILE}"
  echo "Dataset source:             ${DATASET_SOURCE}"
  echo "Language:                   ${LANGUAGE}"
  echo "Group name:                 ${GROUP_NAME}"
  echo "Main output directory:      ${OUTPUT_DIR}"
  echo "Extra output directory:     ${TMP_DIR}"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Balanced-window diagnostic: ${WINDOW_OUTPUT_FILE}"
  echo "Minimum balanced window:    ${MIN_BALANCED_WINDOW}"
  echo "Top print:                  ${TOP_PRINT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${PANEL_FILE}" ]]; then
    echo "ERROR: Baseline panel not found: ${PANEL_FILE}"
    exit 1
  fi

  if [[ ! -f "${REPOS_FILE}" ]]; then
    echo "ERROR: Repository metadata not found: ${REPOS_FILE}"
    exit 1
  fi

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --data-dir "${DATA_DIR}" \
    --panel-file "${PANEL_FILE}" \
    --repos-file "${REPOS_FILE}" \
    --dataset-source "${DATASET_SOURCE}" \
    --language "${LANGUAGE}" \
    --group-name "${GROUP_NAME}" \
    --output-file "${OUTPUT_FILE}" \
    --window-output-file "${WINDOW_OUTPUT_FILE}" \
    --min-balanced-window "${MIN_BALANCED_WINDOW}" \
    --top-print "${TOP_PRINT}"

  for expected_file in "${OUTPUT_FILE}" "${WINDOW_OUTPUT_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}"
      exit 1
    fi
  done

  MAIN_ROWS=$(( $(wc -l < "${OUTPUT_FILE}") - 1 ))
  WINDOW_ROWS=$(( $(wc -l < "${WINDOW_OUTPUT_FILE}") - 1 ))

  echo
  echo "============================================================"
  echo "run-py-1a output verification"
  echo "============================================================"
  echo "Main output:                ${OUTPUT_FILE}"
  echo "Main repository rows:       ${MAIN_ROWS}"
  echo "Diagnostic output:          ${WINDOW_OUTPUT_FILE}"
  echo "Diagnostic repository rows: ${WINDOW_ROWS}"
  echo
  echo "Main output preview:"
  head "${OUTPUT_FILE}"
  echo
  echo "Diagnostic output preview:"
  head "${WINDOW_OUTPUT_FILE}"
  echo
  echo "============================================================"
  echo "run-py-1a completed successfully."
  echo "Completed:                  $(date)"
  echo "Main pipeline input:        ${OUTPUT_FILE}"
  echo "Extra diagnostic output:    ${WINDOW_OUTPUT_FILE}"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
# 
# This wrapper is the Python version of run7a-count-repo.sh.
# It reuses the original selection logic without calling the old wrapper.


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/count_repo_lang.py --
###############################################################################

: <<'__MERGED_PYTHON_1__'
#!/usr/bin/env python3
"""
Count repositories by primary language group and summarize event-window coverage.

This script:
1. Reads panel_event_monthly.csv.
2. Extracts unique repositories from a dataset source, usually treatment.
3. Joins repository metadata from repos.csv.
4. Saves the selected language or language-group subset.
5. Computes pre/post event-window coverage from panel_event_monthly.csv.
6. Saves the selected language-group subset with balanced_window >= K.

Examples:
  Single language:
    python proc_scripts/count_repo_lang.py \
      --data-dir data_baseline_backup \
      --dataset-source treatment \
      --language TypeScript \
      --output-file tmp_typescript_test/data/original_paper_treatment_typescript_repos.csv \
      --window-output-file tmp_typescript_test/data/original_paper_treatment_typescript_repos_bw6.csv

  Multiple languages:
    python proc_scripts/count_repo_lang.py \
      --data-dir data_baseline_backup \
      --dataset-source treatment \
      --languages TypeScript JavaScript \
      --group-name JavaScript_TypeScript \
      --output-file tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv \
      --window-output-file tmp_jsts_test/data/original_paper_treatment_jsts_repos_bw6.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_META_COLUMNS = [
    "repo_name",
    "repo_primary_language",
    "repo_stars",
    "repo_commits",
    "repo_contributors",
    "repo_size",
    "repo_languages",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count repositories by language group and summarize balanced event-window coverage."
    )

    parser.add_argument(
        "--data-dir",
        default="data_baseline_backup",
        help="Directory containing panel_event_monthly.csv and repos.csv.",
    )
    parser.add_argument(
        "--panel-file",
        default=None,
        help="Optional explicit path to panel_event_monthly.csv.",
    )
    parser.add_argument(
        "--repos-file",
        default=None,
        help="Optional explicit path to repos.csv.",
    )
    parser.add_argument(
        "--dataset-source",
        default="treatment",
        help='Dataset source to count, usually "treatment" or "control".',
    )
    parser.add_argument(
        "--language",
        default=None,
        help='Single primary language to export, e.g., "TypeScript".',
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help='One or more primary languages to export, e.g., "TypeScript JavaScript".',
    )
    parser.add_argument(
        "--group-name",
        default=None,
        help='Readable group name for reporting, e.g., "JavaScript_TypeScript".',
    )
    parser.add_argument(
        "--language-column",
        default="repo_primary_language",
        help="Column used for language filtering.",
    )
    parser.add_argument(
        "--output-file",
        default="tmp_typescript_test/data/original_paper_treatment_typescript_repos.csv",
        help="Output CSV for the selected language subset.",
    )
    parser.add_argument(
        "--window-output-file",
        default="tmp_typescript_test/data/original_paper_treatment_typescript_repos_bw6.csv",
        help="Output CSV for selected language subset with sufficient balanced_window.",
    )
    parser.add_argument(
        "--min-balanced-window",
        type=int,
        default=6,
        help="Minimum balanced_window threshold for the strict output file.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=30,
        help="Number of selected rows to print.",
    )

    return parser.parse_args()


def resolve_language_group(args: argparse.Namespace) -> tuple[list[str], str]:
    if args.languages:
        languages = args.languages
    elif args.language:
        languages = [args.language]
    else:
        languages = ["TypeScript"]

    languages = [str(x).strip() for x in languages if str(x).strip()]
    if not languages:
        raise SystemExit("ERROR: no valid language was provided.")

    if args.group_name:
        group_name = args.group_name
    else:
        group_name = "_".join(languages)

    return languages, group_name


def read_csv_checked(path: Path, required_columns: list[str], label: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} file not found: {path}")

    df = pd.read_csv(path, dtype=str, low_memory=False)

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: {label} file is missing required columns: {missing}")

    return df


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    data_dir = Path(args.data_dir)

    panel_path = Path(args.panel_file) if args.panel_file else data_dir / "panel_event_monthly.csv"
    repos_path = Path(args.repos_file) if args.repos_file else data_dir / "repos.csv"

    return panel_path, repos_path


def clean_repo_name(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype(str).str.strip().str[:7]
    return out.mask(out.str.lower().isin(["", "nan", "nat", "none"]))


def extract_unique_repos(panel: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    source = dataset_source.lower()

    panel = panel.copy()
    panel["dataset_source_norm"] = panel["dataset_source"].astype(str).str.lower()
    panel["repo_name"] = clean_repo_name(panel["repo_name"])

    selected = (
        panel[panel["dataset_source_norm"].eq(source)]
        [["repo_name"]]
        .drop_duplicates()
        .copy()
    )

    return selected


def get_repo_metadata(repos: pd.DataFrame) -> pd.DataFrame:
    keep_cols = [col for col in DEFAULT_META_COLUMNS if col in repos.columns]

    if "repo_name" not in keep_cols:
        raise SystemExit("ERROR: repos metadata does not contain repo_name.")

    meta = repos[keep_cols].copy()
    meta["repo_name"] = clean_repo_name(meta["repo_name"])
    meta = meta.drop_duplicates("repo_name")

    return meta


def join_repo_metadata(selected: pd.DataFrame, repos: pd.DataFrame) -> pd.DataFrame:
    meta = get_repo_metadata(repos)
    return selected.merge(meta, on="repo_name", how="left")


def filter_language_group(
    df: pd.DataFrame,
    language_column: str,
    languages: list[str],
) -> pd.DataFrame:
    if language_column not in df.columns:
        raise SystemExit(f"ERROR: language column not found: {language_column}")

    return df[df[language_column].isin(languages)].copy()


def summarize_event_windows(panel: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    required = ["repo_name", "dataset_source", "time", "event", "time_to_event"]
    missing = [col for col in required if col not in panel.columns]
    if missing:
        raise SystemExit(f"ERROR: panel file is missing required event-window columns: {missing}")

    source = dataset_source.lower()

    p = panel[panel["dataset_source"].astype(str).str.lower().eq(source)].copy()

    p["repo_name"] = clean_repo_name(p["repo_name"])
    p["time"] = clean_month(p["time"])
    p["event"] = clean_month(p["event"])
    p["time_to_event_num"] = pd.to_numeric(p["time_to_event"], errors="coerce")

    p = p.dropna(subset=["repo_name", "time", "time_to_event_num"])
    p["time_to_event_num"] = p["time_to_event_num"].astype(int)

    before = len(p)
    p = p.sort_values(["repo_name", "time"]).drop_duplicates(
        ["repo_name", "time"],
        keep="first",
    )
    duplicated_repo_month_rows = before - len(p)

    summary = (
        p.groupby("repo_name")
        .agg(
            event_month=("event", "first"),
            panel_first_month=("time", "min"),
            panel_latest_month=("time", "max"),
            panel_month_count=("time", "nunique"),
            min_relative_month=("time_to_event_num", "min"),
            max_relative_month=("time_to_event_num", "max"),
            pre_panel_months=("time_to_event_num", lambda x: int((x < 0).sum())),
            event_months=("time_to_event_num", lambda x: int((x == 0).sum())),
            post_panel_months=("time_to_event_num", lambda x: int((x > 0).sum())),
        )
        .reset_index()
    )

    summary["balanced_window"] = summary[
        ["pre_panel_months", "post_panel_months"]
    ].min(axis=1)

    summary.attrs["duplicated_repo_month_rows"] = duplicated_repo_month_rows

    return summary


def save_csv(df: pd.DataFrame, output_file: str) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def print_language_report(
    panel: pd.DataFrame,
    repos: pd.DataFrame,
    selected: pd.DataFrame,
    selected_meta: pd.DataFrame,
    language_subset: pd.DataFrame,
    args: argparse.Namespace,
    panel_path: Path,
    repos_path: Path,
    languages: list[str],
    group_name: str,
) -> None:
    print("Panel file:", panel_path)
    print("Repos file:", repos_path)
    print("panel rows:", len(panel))
    print("repos rows:", len(repos))
    print()

    print("dataset_source counts:")
    print(panel["dataset_source"].value_counts(dropna=False).to_string())
    print()

    print(f"unique {args.dataset_source} repos from panel:", selected["repo_name"].nunique())
    print("repos after metadata join:", len(selected_meta))

    if args.language_column in selected_meta.columns:
        print("missing primary language:", selected_meta[args.language_column].isna().sum())
    print()

    print(f"Primary language counts among {args.dataset_source} repos:")
    print(selected_meta[args.language_column].fillna("(missing)").value_counts().head(30).to_string())
    print()

    print("Selected languages:", ", ".join(languages))
    print("Group name:", group_name)
    print(f"{group_name} {args.dataset_source} repos:", len(language_subset))
    print("Unique repos:", language_subset["repo_name"].nunique())
    print()

    print("Saved language subset:", args.output_file)
    print()

    print(f"Top {args.top_print} {group_name} repos:")
    cols = [
        "repo_name",
        "repo_primary_language",
        "repo_stars",
        "repo_commits",
        "repo_contributors",
        "repo_size",
    ]
    cols = [col for col in cols if col in language_subset.columns]

    if len(language_subset) == 0:
        print("(No matching rows.)")
    else:
        print(language_subset[cols].head(args.top_print).to_string(index=False))


def print_window_report(
    language_window: pd.DataFrame,
    strict_window: pd.DataFrame,
    args: argparse.Namespace,
    duplicated_repo_month_rows: int,
    group_name: str,
) -> None:
    print()
    print("============================================================")
    print("Event-window coverage among selected language-group repos")
    print("============================================================")
    print("Duplicated repo-month rows collapsed:", duplicated_repo_month_rows)
    print(f"All {group_name} {args.dataset_source} repos with window summary:", len(language_window))
    print("Unique repos:", language_window["repo_name"].nunique())
    print()

    print("Primary language counts in window-summary subset:")
    print(language_window[args.language_column].fillna("(missing)").value_counts().to_string())
    print()

    print("balanced_window counts:")
    print(language_window["balanced_window"].value_counts().sort_index().to_string())
    print()

    for k in [3, 4, 5, 6, 7, 8, 9]:
        n = int((language_window["balanced_window"] >= k).sum())
        print(f"balanced_window >= {k}: {n}")

    print()
    print(
        f"Good-window {group_name} repos, "
        f"balanced_window >= {args.min_balanced_window}: {len(strict_window)}"
    )
    print("Unique good-window repos:", strict_window["repo_name"].nunique())
    print()

    if len(strict_window) > 0 and "event_month" in strict_window.columns:
        print(f"Event month counts for balanced_window >= {args.min_balanced_window}:")
        print(strict_window["event_month"].value_counts().sort_index().to_string())
        print()

    print("Saved good-window subset:", args.window_output_file)
    print()

    cols = [
        "repo_name",
        "event_month",
        "pre_panel_months",
        "post_panel_months",
        "balanced_window",
        "repo_primary_language",
        "repo_stars",
        "repo_commits",
        "repo_contributors",
    ]
    cols = [col for col in cols if col in strict_window.columns]

    print(f"Top {args.top_print} good-window {group_name} repos:")
    if len(strict_window) == 0:
        print("(No matching rows.)")
    else:
        print(strict_window[cols].head(args.top_print).to_string(index=False))


def main() -> None:
    args = parse_args()
    languages, group_name = resolve_language_group(args)

    panel_path, repos_path = resolve_paths(args)

    panel = read_csv_checked(
        panel_path,
        required_columns=["repo_name", "dataset_source"],
        label="panel",
    )
    repos = read_csv_checked(
        repos_path,
        required_columns=["repo_name", args.language_column],
        label="repos",
    )

    selected = extract_unique_repos(panel, args.dataset_source)
    selected_meta = join_repo_metadata(selected, repos)

    language_subset = filter_language_group(
        df=selected_meta,
        language_column=args.language_column,
        languages=languages,
    )
    save_csv(language_subset, args.output_file)

    window_summary = summarize_event_windows(panel, args.dataset_source)
    duplicated_repo_month_rows = int(window_summary.attrs.get("duplicated_repo_month_rows", 0))

    meta = get_repo_metadata(repos)
    window_meta = window_summary.merge(meta, on="repo_name", how="left")

    language_window = filter_language_group(
        df=window_meta,
        language_column=args.language_column,
        languages=languages,
    )
    language_window = language_window.sort_values(["repo_name"]).reset_index(drop=True)

    strict_window = language_window[
        language_window["balanced_window"] >= args.min_balanced_window
    ].copy()
    strict_window = strict_window.sort_values(
        ["balanced_window", "repo_name"],
        ascending=[False, True],
    ).reset_index(drop=True)

    save_csv(strict_window, args.window_output_file)

    print_language_report(
        panel=panel,
        repos=repos,
        selected=selected,
        selected_meta=selected_meta,
        language_subset=language_subset,
        args=args,
        panel_path=panel_path,
        repos_path=repos_path,
        languages=languages,
        group_name=group_name,
    )

    print_window_report(
        language_window=language_window,
        strict_window=strict_window,
        args=args,
        duplicated_repo_month_rows=duplicated_repo_month_rows,
        group_name=group_name,
    )


if __name__ == "__main__":
    main()

__MERGED_PYTHON_1__

###############################################################################
# -- SHELL SCRIPT: run-py-1b-detect-ai-adoption-repo.sh --
###############################################################################

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
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1b}"

# Input candidate file from run-py-1a.
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Primary clone-status output used by the next step.
CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
CLONE_STATUS_BACKUP="${CLONE_STATUS_BACKUP:-${TMP_DIR}/treatment_python_clone_status_${RUN_TS}.csv}"

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
# CLONE_LOG_CSV="${TMP_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

# ------------------------------------------------------------
# Clone-status report settings
# ------------------------------------------------------------
CHECK_LANGUAGES_CSV="${CHECK_LANGUAGES_CSV:-Python}"
CHECK_TOP_PRINT="${CHECK_TOP_PRINT:-80}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1b: clone Python Cursor-adopting treatment repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                  ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Main output dir:            ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:           ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
# -- CALLED PYTHON SCRIPT: proc_scripts/clone_repos_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_2__'
#!/usr/bin/env python3
"""
Clone repositories from a candidate CSV file.

This script extends the original scripts/clone_repos.py behavior without
modifying the original file.

Original reusable logic:
  - ensure_dir()
  - is_git_repo()
  - pull_latest_changes()

New v2 logic:
  - read arbitrary CSV with repo_name column
  - clone into a user-specified clone root
  - save timestamped clone log under ./logs
  - support max clone count for smoke tests
  - skip existing repositories by default
"""

from __future__ import annotations

import os
import argparse
import csv
import importlib.util
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "clone_repos.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original clone script not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location("original_clone_repos", ORIGINAL_SCRIPT)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone repositories from a candidate CSV file."
    )

    parser.add_argument(
        "--repos-file",
        type=Path,
        required=True,
        help="CSV file containing repo_name column, or TXT file with one repo per line.",
    )

    parser.add_argument(
        "--repo-column",
        default="repo_name",
        help="Column containing GitHub repo names. Default: repo_name.",
    )

    parser.add_argument(
        "--clone-root",
        type=Path,
        default=PROJECT_DIR.parent / "ai_code_complexity_study_repo_dataset",
        help="Directory where repositories will be cloned.",
    )

    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=PROJECT_DIR / "logs",
        help="Directory for timestamped clone logs.",
    )

    parser.add_argument(
        "--log-prefix",
        default="run4a_clone_log",
        help="Clone log filename prefix.",
    )

    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional timestamp for log file. Default: current YYYYMMDD-HHMM.",
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=0,
        help="Maximum repos to process. Use 0 for all.",
    )

    parser.add_argument(
        "--existing-action",
        choices=["skip", "pull"],
        default="skip",
        help=(
            "What to do if target repo already exists. "
            "skip is safer for this study; pull refreshes existing clones."
        ),
    )

    parser.add_argument(
        "--git-clone-extra-arg",
        action="append",
        default=[],
        help=(
            "Extra argument passed to git clone. Can be repeated. "
            "Do not use --depth 1 because full history is needed."
        ),
    )

    return parser.parse_args()


def deduplicate_repo_names(repos: list[str]) -> list[str]:
    """Preserve input order while removing duplicate repo names."""
    seen = set()
    unique_repos = []

    for repo in repos:
        repo = str(repo).strip()
        if not repo:
            continue
        if repo not in seen:
            unique_repos.append(repo)
            seen.add(repo)

    return unique_repos


def write_normalized_csv(input_path: Path, repos: list[str], repo_column: str) -> Path:
    """
    Write a normalized CSV next to a TXT input file.

    Example:
      control_repos_to_clone_v2.txt
      -> control_repos_to_clone_v2.csv
    """
    output_path = input_path.with_suffix(".csv")

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[repo_column])
        writer.writeheader()
        for repo in repos:
            writer.writerow({repo_column: repo})

    logging.info("Wrote normalized CSV: %s", output_path)
    logging.info("Normalized CSV repositories: %d", len(repos))

    return output_path


def read_repo_names(repos_path: Path, repo_column: str) -> list[str]:
    """
    Read repository names from either:
      - CSV file with repo_column
      - TXT file with one owner/repo per line

    If a TXT file is provided, also write a normalized sibling CSV.
    """
    if not repos_path.exists():
        raise FileNotFoundError(f"Repos file not found: {repos_path}")

    repos: list[str] = []

    if repos_path.suffix.lower() == ".txt":
        repos = [
            line.strip()
            for line in repos_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        repos = deduplicate_repo_names(repos)
        write_normalized_csv(repos_path, repos, repo_column)
        return repos

    with repos_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None or repo_column not in reader.fieldnames:
            raise ValueError(
                f"Column {repo_column!r} not found in {repos_path}. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            repo = str(row.get(repo_column, "")).strip()
            if repo:
                repos.append(repo)

    return deduplicate_repo_names(repos)


def clone_repository_v2(
    repo_name: str,
    clone_path: Path,
    extra_args: Iterable[str],
) -> tuple[bool, str]:
    repo_url = f"https://github.com/{repo_name}.git"
    cmd = ["git", "clone", *extra_args, repo_url, str(clone_path)]

    try:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        logging.info("Successfully cloned %s", repo_name)
        return True, "ok"
    except subprocess.CalledProcessError as exc:
        note = (exc.stderr or exc.stdout or "git_clone_failed").strip()
        logging.error("Failed to clone %s: %s", repo_name, note)
        return False, note.replace("\n", " ")[:300]
    except Exception as exc:
        logging.error("Failed to clone %s: %s", repo_name, exc)
        return False, str(exc).replace("\n", " ")[:300]


def write_log_row(writer, repo_name: str, status: str, target_dir: Path, note: str) -> None:
    writer.writerow(
        {
            "repo_name": repo_name,
            "status": status,
            "target_dir": str(target_dir),
            "note": note,
        }
    )


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    repos_file = args.repos_file.expanduser().resolve()
    clone_root = args.clone_root.expanduser().resolve()
    logs_dir = args.logs_dir.expanduser().resolve()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d-%H%M")
    log_file = logs_dir / f"{args.log_prefix}_{timestamp}.csv"

    orig.ensure_dir(clone_root)
    orig.ensure_dir(logs_dir)

    repos = read_repo_names(repos_file, args.repo_column)

    if args.max_repos > 0:
        repos = repos[: args.max_repos]

    logging.info("Repos file: %s", repos_file)
    logging.info("Clone root: %s", clone_root)
    logging.info("Log file: %s", log_file)
    logging.info("Existing action: %s", args.existing_action)
    logging.info("Repositories to process: %d", len(repos))

    cloned = 0
    skipped = 0
    updated = 0
    failed = 0

    with log_file.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["repo_name", "status", "target_dir", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, repo_name in enumerate(repos, start=1):
            target_dir = clone_root / repo_name.replace("/", "_")

            logging.info("[%d/%d] %s -> %s", idx, len(repos), repo_name, target_dir)

            if target_dir.exists():
                if orig.is_git_repo(target_dir):
                    if args.existing_action == "skip":
                        logging.info("Already cloned. Skipping %s", repo_name)
                        write_log_row(
                            writer,
                            repo_name,
                            "skipped_existing",
                            target_dir,
                            "already_has_git_dir",
                        )
                        skipped += 1
                        continue

                    if args.existing_action == "pull":
                        ok = orig.pull_latest_changes(target_dir, repo_name)
                        if ok:
                            write_log_row(
                                writer,
                                repo_name,
                                "updated_existing",
                                target_dir,
                                "pulled_latest_changes",
                            )
                            updated += 1
                        else:
                            write_log_row(
                                writer,
                                repo_name,
                                "failed",
                                target_dir,
                                "pull_latest_changes_failed",
                            )
                            failed += 1
                        continue

                logging.warning(
                    "Path exists but is not a valid Git repo: %s",
                    target_dir,
                )
                write_log_row(
                    writer,
                    repo_name,
                    "failed",
                    target_dir,
                    "path_exists_not_git_repo",
                )
                failed += 1
                continue

            ok, note = clone_repository_v2(
                repo_name=repo_name,
                clone_path=target_dir,
                extra_args=args.git_clone_extra_arg,
            )

            if ok:
                write_log_row(writer, repo_name, "cloned", target_dir, note)
                cloned += 1
            else:
                write_log_row(writer, repo_name, "failed", target_dir, note)
                failed += 1

    logging.info("")
    logging.info("Clone summary")
    logging.info("-------------")
    logging.info("processed: %d", len(repos))
    logging.info("cloned:    %d", cloned)
    logging.info("updated:   %d", updated)
    logging.info("skipped:   %d", skipped)
    logging.info("failed:    %d", failed)
    logging.info("clone log: %s", log_file)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_2__

###############################################################################
# -- SHELL SCRIPT: run-py-1c-create-treatment-usable-repos.sh --
###############################################################################

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
#   repo_python/tmp/run-py-1c/treatment_python_clone_failed_repos.csv
#     - Failed Python treatment repos.
#
# Typical usage:
#   bash run-py-1c-create-treatment-usable-repos.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1c_create_treatment_usable_repos_${RUN_TS}.log}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1c}"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-${OUTPUT_DIR}/treatment_python_clone_status.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_usable_repos_with_event.csv}"
# FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_clone_failed_repos.csv}"
FAILED_OUTPUT_FILE="${FAILED_OUTPUT_FILE:-${TMP_DIR}/treatment_python_clone_failed_repos.csv}"

DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
TOP_PRINT="${TOP_PRINT:-50}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_clone_usable_repos_with_event.py}"

# mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1c: create usable Python treatment repo list with event metadata" | tee -a "${LOG_FILE}"
echo "Timestamp:            ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:        ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Clone status file:    ${CLONE_STATUS_FILE}" | tee -a "${LOG_FILE}"
echo "Panel file:           ${PANEL_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:      ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:     ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
# -- CALLED PYTHON SCRIPT: proc_scripts/create_clone_usable_repos_with_event.py --
###############################################################################

: <<'__MERGED_PYTHON_3__'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create usable cloned repo list and attach event-window metadata "
            "from panel_event_monthly.csv."
        )
    )
    parser.add_argument(
        "--clone-status-file",
        required=True,
        help="Clone status CSV generated by run7c/run7b.",
    )
    parser.add_argument(
        "--panel-file",
        default="data_baseline_backup/panel_event_monthly.csv",
        help="Panel event monthly CSV containing repo_name, dataset_source, time, event, time_to_event.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output CSV for usable cloned repositories with event metadata.",
    )
    parser.add_argument(
        "--failed-output-file",
        default=None,
        help="Optional output CSV for failed repositories.",
    )
    parser.add_argument(
        "--usable-statuses",
        nargs="+",
        default=["cloned", "skipped_existing", "updated_existing"],
        help="Clone statuses treated as usable.",
    )
    parser.add_argument(
        "--dataset-source",
        default="treatment",
        help="dataset_source value to use from panel_event_monthly.csv.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of rows to print.",
    )
    return parser.parse_args()


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype(str).str.strip().str[:7]
    return out.mask(out.str.lower().isin(["", "nan", "nat", "none"]))


def summarize_clone_status(
    clone_df: pd.DataFrame,
    usable_statuses: set[str],
    top_print: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    usable = clone_df[clone_df["status"].isin(usable_statuses)].copy()
    failed = clone_df[clone_df["status"].eq("failed")].copy()

    print("Total rows:", len(clone_df))
    print("Unique repos:", clone_df["repo_name"].nunique())
    print()

    print("Status counts:")
    print(clone_df["status"].fillna("(missing)").value_counts().to_string())
    print()

    print("Usable repos:", len(usable))
    print("Failed repos:", len(failed))
    print()

    if "repo_primary_language" in clone_df.columns:
        print("Language counts among all candidates:")
        print(clone_df["repo_primary_language"].fillna("(missing)").value_counts().to_string())
        print()

        print("Language counts among usable repos:")
        print(usable["repo_primary_language"].fillna("(missing)").value_counts().to_string())
        print()

    print("Top failed repos:")
    cols = ["repo_name", "repo_primary_language", "status", "note"]
    cols = [c for c in cols if c in failed.columns]
    if len(failed) == 0:
        print("(No failed repositories.)")
    else:
        print(failed[cols].head(top_print).to_string(index=False))
    print()

    return usable, failed


def build_event_summary(panel: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    required = ["repo_name", "dataset_source", "time", "event", "time_to_event"]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise SystemExit(f"ERROR: panel file is missing required columns: {missing}")

    p = panel.copy()
    p["repo_name"] = p["repo_name"].astype(str).str.strip()
    p["dataset_source_norm"] = p["dataset_source"].astype(str).str.lower()
    p = p[p["dataset_source_norm"].eq(dataset_source.lower())].copy()

    p["time"] = clean_month(p["time"])
    p["event_month"] = clean_month(p["event"])
    p["time_to_event_num"] = pd.to_numeric(p["time_to_event"], errors="coerce")

    p = p.dropna(subset=["repo_name", "time", "event_month", "time_to_event_num"])
    p["time_to_event_num"] = p["time_to_event_num"].astype(int)

    p = p.sort_values(["repo_name", "time"]).drop_duplicates(
        ["repo_name", "time"],
        keep="first",
    )

    summary = (
        p.groupby("repo_name")
        .agg(
            event_month=("event_month", "first"),
            panel_first_month=("time", "min"),
            panel_latest_month=("time", "max"),
            panel_month_count=("time", "nunique"),
            min_relative_month=("time_to_event_num", "min"),
            max_relative_month=("time_to_event_num", "max"),
            pre_panel_months=("time_to_event_num", lambda x: int((x < 0).sum())),
            event_months=("time_to_event_num", lambda x: int((x == 0).sum())),
            post_panel_months=("time_to_event_num", lambda x: int((x > 0).sum())),
        )
        .reset_index()
    )

    summary["balanced_window"] = summary[
        ["pre_panel_months", "post_panel_months"]
    ].min(axis=1)

    return summary


def main() -> None:
    args = parse_args()

    clone_status_path = Path(args.clone_status_file)
    panel_path = Path(args.panel_file)
    output_path = Path(args.output_file)
    failed_output_path = Path(args.failed_output_file) if args.failed_output_file else None

    if not clone_status_path.exists():
        raise SystemExit(f"ERROR: clone status file not found: {clone_status_path}")

    if not panel_path.exists():
        raise SystemExit(f"ERROR: panel file not found: {panel_path}")

    clone_df = pd.read_csv(clone_status_path)
    panel = pd.read_csv(panel_path, dtype=str, low_memory=False)

    if "repo_name" not in clone_df.columns:
        raise SystemExit("ERROR: clone status file must contain repo_name.")

    if "status" not in clone_df.columns:
        raise SystemExit("ERROR: clone status file must contain status.")

    clone_df["repo_name"] = clone_df["repo_name"].astype(str).str.strip()

    print("Clone status file:", clone_status_path)
    print("Panel file:", panel_path)
    print("Output file:", output_path)
    if failed_output_path:
        print("Failed output file:", failed_output_path)
    print()

    usable_statuses = set(args.usable_statuses)

    usable, failed = summarize_clone_status(
        clone_df=clone_df,
        usable_statuses=usable_statuses,
        top_print=args.top_print,
    )

    usable = usable.drop_duplicates("repo_name").reset_index(drop=True)

    event_summary = build_event_summary(panel, args.dataset_source)
    out = usable.merge(event_summary, on="repo_name", how="left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    if failed_output_path:
        failed_output_path.parent.mkdir(parents=True, exist_ok=True)
        failed.to_csv(failed_output_path, index=False)

    print("Event metadata merge summary:")
    print("Usable rows:", len(usable))
    print("Unique usable repos:", usable["repo_name"].nunique())
    print("Rows with event_month:", out["event_month"].notna().sum())
    print("Rows missing event_month:", out["event_month"].isna().sum())
    print()

    if "repo_primary_language" in out.columns:
        print("Usable language counts:")
        print(out["repo_primary_language"].fillna("(missing)").value_counts().to_string())
        print()

    print("Balanced window counts among usable repos:")
    bw = pd.to_numeric(out["balanced_window"], errors="coerce")
    bw_counts = bw.dropna().astype(int).value_counts().sort_index()

    if bw_counts.empty:
        print("(No non-missing balanced_window values.)")
    else:
        print(bw_counts.to_string())

    missing_bw = int(bw.isna().sum())
    if missing_bw > 0:
        print(f"(missing) {missing_bw}")
    print()

    cols = [
        "repo_name",
        "repo_primary_language",
        "event_month",
        "panel_first_month",
        "panel_latest_month",
        "panel_month_count",
        "pre_panel_months",
        "post_panel_months",
        "balanced_window",
        "status",
        "target_dir",
    ]
    cols = [c for c in cols if c in out.columns]

    print(f"Top {args.top_print} usable repos with event metadata:")
    if len(out) == 0:
        print("(No usable repositories.)")
    else:
        print(out[cols].head(args.top_print).to_string(index=False))
    print()

    print("Saved usable repo file:", output_path)
    if failed_output_path:
        print("Saved failed repo file:", failed_output_path)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_3__

###############################################################################
# -- SHELL SCRIPT: run-py-1d-split-valid-event-repos.sh --
###############################################################################

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


###############################################################################
# -- SHELL SCRIPT: run-py-1e-analyze-treatment-repos.sh --
###############################################################################

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
TMP_BASE_DIR="${TMP_BASE_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1e}"

REPOS_FILE="${REPOS_FILE:-${OUTPUT_BASE_DIR}/treatment_python_clone_usable_repos_with_event_valid.csv}"
CLONE_DIR="${CLONE_DIR:-../treatment-repos}"

AGGREGATION="${AGGREGATION:-month}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"

# Default is smoke test. Use MAX_REPOS=0 for full run.
MAX_REPOS="${MAX_REPOS:-5}"

# Fixed output directories:
#   - Full-run main outputs use repo_python/treatment_python_did
#   - Smoke-test outputs use repo_python/tmp/run-py-1e/smoke/output
#   - Cache, manifest, missing-repo, and incremental files use
#     repo_python/tmp/run-py-1e
#
# This is important because timestamped smoke directories cannot use cache.
FULL_OUTPUT_DIR="${FULL_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did}"
# SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/treatment_python_did_smoke}"
SMOKE_OUTPUT_DIR="${SMOKE_OUTPUT_DIR:-${TMP_BASE_DIR}/smoke/output}"


if [[ "${MAX_REPOS}" == "0" ]]; then
  OUTPUT_DIR="${OUTPUT_DIR:-${FULL_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_BASE_DIR}/full}"
else
  OUTPUT_DIR="${OUTPUT_DIR:-${SMOKE_OUTPUT_DIR}}"
  EXTRA_DIR="${EXTRA_DIR:-${TMP_BASE_DIR}/smoke}"
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

# MANIFEST_FILE="${OUTPUT_DIR}/run-py-1e_analyzed_repos_manifest.csv"
MANIFEST_FILE="${EXTRA_DIR}/run-py-1e_analyzed_repos_manifest.csv"

# SMOKE_REPOS_FILE="${OUTPUT_DIR}/treatment_python_repos_smoke_max${MAX_REPOS}.csv"
# MISSING_REPOS_FILE="${OUTPUT_DIR}/run-py-1e_missing_repos_${RUN_TS}.csv"
# TMP_OUTPUT_DIR="${OUTPUT_DIR}/_incremental_${RUN_TS}"
SMOKE_REPOS_FILE="${EXTRA_DIR}/treatment_python_repos_smoke_max${MAX_REPOS}.csv"
MISSING_REPOS_FILE="${EXTRA_DIR}/run-py-1e_missing_repos_${RUN_TS}.csv"
TMP_OUTPUT_DIR="${EXTRA_DIR}/incremental_${RUN_TS}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${EXTRA_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1e: analyze Python treatment repos and validate adoption month" | tee -a "${LOG_FILE}"
echo "Timestamp:                 ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python analyzer:           ${PY_ANALYZER}" | tee -a "${LOG_FILE}"
echo "Adoption check script:     ${PY_ADOPTION_CHECK}" | tee -a "${LOG_FILE}"
echo "Cache check script:        ${CACHE_CHECK_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Repos file:                ${REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Clone dir:                 ${CLONE_DIR}" | tee -a "${LOG_FILE}"
echo "Main output dir:           ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:          ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
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

  # CACHE_REPORT="${OUTPUT_DIR}/run-py-1e_cache_check_${RUN_TS}.txt"
  CACHE_REPORT="${EXTRA_DIR}/run-py-1e_cache_check_${RUN_TS}.txt"

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
# echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Main output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${EXTRA_DIR}" | tee -a "${LOG_FILE}"
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
# -- CALLED PYTHON SCRIPT: proc_scripts/analyze_repos_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_4__'
#!/usr/bin/env python3
"""
Extended repository analyzer for AI code generator adoption-date detection.

This wrapper imports scripts/analyze_repos.py and reuses its original logic:
  - find_cursor_commits()
  - count_cursor_commits_by_time()
  - get_commit_stats()
  - process_repository()

New logic added here:
  - CLI arguments for repos file, clone directory, output directory, aggregation
  - sample testing with --max-repos or --repos
  - ai_adoption_dates.csv generated from earliest Cursor-related commit per repo

The original script is not modified.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import multiprocessing
import random
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "analyze_repos.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original analyzer not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location("original_analyze_repos", ORIGINAL_SCRIPT)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)


def load_repos(
    repos_file: Path,
    repos_filter: Optional[list[str]],
    max_repos: Optional[int],
    random_sample: bool,
    seed: int,
) -> pd.DataFrame:
    """Load repo list and optionally filter/sample it."""
    if not repos_file.exists():
        raise FileNotFoundError(f"Repos file not found: {repos_file}")

    repos_df = pd.read_csv(repos_file)

    if "repo_name" not in repos_df.columns:
        raise ValueError(f"{repos_file} must contain a repo_name column")

    repos_df["repo_name"] = repos_df["repo_name"].astype(str).str.strip()
    repos_df = repos_df[repos_df["repo_name"] != ""].drop_duplicates("repo_name")

    if repos_filter:
        wanted = set(repos_filter)
        repos_df = repos_df[repos_df["repo_name"].isin(wanted)].copy()

    if max_repos is not None and max_repos > 0 and len(repos_df) > max_repos:
        if random_sample:
            repos_df = repos_df.sample(n=max_repos, random_state=seed)
        else:
            repos_df = repos_df.head(max_repos)

    return repos_df.reset_index(drop=True)


def compute_ai_adoption_dates(cursor_commits_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute earliest Cursor-related commit per repo.

    Input rows come from original find_cursor_commits(), with columns:
      repo_name, commit_hash, authored_at, committed_at, paths, message, ...

    Output:
      repo_name, adoption_tool, adoption_commit, adoption_date,
      adoption_month, evidence_paths, evidence_type, confidence
    """
    if cursor_commits_df.empty:
        return pd.DataFrame(
            columns=[
                "repo_name",
                "adoption_tool",
                "adoption_commit",
                "adoption_date",
                "adoption_month",
                "evidence_paths",
                "evidence_type",
                "confidence",
                "message",
            ]
        )

    df = cursor_commits_df.copy()

    # Prefer authored_at because it is closer to when the change was authored.
    # Fall back to committed_at if needed.
    if "authored_at" in df.columns:
        df["adoption_datetime"] = pd.to_datetime(df["authored_at"], errors="coerce")
    else:
        df["adoption_datetime"] = pd.NaT

    if "committed_at" in df.columns:
        committed_dt = pd.to_datetime(df["committed_at"], errors="coerce")
        df["adoption_datetime"] = df["adoption_datetime"].fillna(committed_dt)

    df = df.dropna(subset=["adoption_datetime"])

    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["repo_name", "adoption_datetime", "commit_hash"])
    first_df = df.groupby("repo_name", as_index=False).first()

    first_df["adoption_tool"] = "cursor"
    first_df["adoption_commit"] = first_df["commit_hash"]
    first_df["adoption_date"] = first_df["adoption_datetime"].dt.strftime("%Y-%m-%d")
    first_df["adoption_month"] = first_df["adoption_datetime"].dt.strftime("%Y-%m")
    first_df["evidence_paths"] = first_df.get("paths", "")
    first_df["evidence_type"] = "cursor_related_path"
    first_df["confidence"] = "high"

    cols = [
        "repo_name",
        "adoption_tool",
        "adoption_commit",
        "adoption_date",
        "adoption_month",
        "evidence_paths",
        "evidence_type",
        "confidence",
        "message",
    ]

    available_cols = [c for c in cols if c in first_df.columns]
    return first_df[available_cols].sort_values("repo_name").reset_index(drop=True)


# def process_one_repo(args_tuple):
#     """
#     Process one repo using original process_repository().
# 
#     We keep this wrapper so multiprocessing can call a top-level function
#     from this v2 file while the actual repository logic remains in the original.
#     """
#     idx, repo_dict, total_repos, aggregation = args_tuple
#     return orig.process_repository(idx, repo_dict, total_repos, aggregation)

def process_one_repo(args_tuple):
    idx, repo_dict, total_repos, aggregation = args_tuple
    repo_ts, contrib_ts, cursor_commits = orig.process_repository(
        idx, repo_dict, total_repos, aggregation
    )

    correct_repo_name = str(repo_dict["repo_name"]).strip()

    for rows in (repo_ts, contrib_ts, cursor_commits):
        for row in rows:
            row["repo_name"] = correct_repo_name

    return repo_ts, contrib_ts, cursor_commits



def run_analysis(
    repos_df: pd.DataFrame,
    clone_dir: Path,
    output_dir: Path,
    aggregation: str,
    num_processes: int,
    seed: int,
    shuffle: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Run original analyzer logic and return:
      ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Patch original module globals so original functions use our CLI settings.
    orig.CLONE_DIR = clone_dir
    orig.OUTPUT_DIR = output_dir
    orig.TIME_KEY = aggregation

    total_repos = len(repos_df)

    args_list = [
        (idx, repo.to_dict(), total_repos, aggregation)
        for idx, repo in repos_df.iterrows()
    ]

    if shuffle:
        random.seed(seed)
        random.shuffle(args_list)

    repo_ts = []
    contributor_ts = []
    all_cursor_commits = []

    if total_repos == 0:
        logging.warning("No repositories to process")
    elif num_processes <= 1:
        logging.info("Starting serial processing for %d repos", total_repos)
        for process_args in args_list:
            repo_name = process_args[1]["repo_name"]
            try:
                repo_time_series, repo_contributor_ts, repo_cursor_commits = process_one_repo(
                    process_args
                )
                repo_ts.extend(repo_time_series)
                contributor_ts.extend(repo_contributor_ts)
                all_cursor_commits.extend(repo_cursor_commits)
            except Exception as exc:
                logging.error("Error processing repository %s: %s", repo_name, exc)
    else:
        logging.info(
            "Starting multiprocessing pool with %d workers for %d repos",
            num_processes,
            total_repos,
        )
        with multiprocessing.Pool(processes=num_processes) as pool:
            async_results = [
                pool.apply_async(process_one_repo, (process_args,))
                for process_args in args_list
            ]

            for idx, async_result in enumerate(async_results):
                repo_name = args_list[idx][1]["repo_name"]
                try:
                    repo_time_series, repo_contributor_ts, repo_cursor_commits = (
                        async_result.get(timeout=orig.REPO_TIMEOUT_SECONDS)
                    )
                    repo_ts.extend(repo_time_series)
                    contributor_ts.extend(repo_contributor_ts)
                    all_cursor_commits.extend(repo_cursor_commits)
                except multiprocessing.TimeoutError:
                    logging.error(
                        "Repository %s processing timed out after %d seconds",
                        repo_name,
                        orig.REPO_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    logging.error("Error processing repository %s: %s", repo_name, exc)

    ts_repos_df = pd.DataFrame(repo_ts)
    ts_contributors_df = pd.DataFrame(contributor_ts)
    cursor_commits_df = pd.DataFrame(all_cursor_commits)
    adoption_dates_df = compute_ai_adoption_dates(cursor_commits_df)

    return ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df


def save_outputs(
    ts_repos_df: pd.DataFrame,
    ts_contributors_df: pd.DataFrame,
    cursor_commits_df: pd.DataFrame,
    adoption_dates_df: pd.DataFrame,
    output_dir: Path,
    aggregation: str,
) -> None:
    """Save outputs using original-style filenames plus ai_adoption_dates.csv."""
    output_suffix = "_monthly.csv" if aggregation == "month" else "_weekly.csv"

    ts_repos_file = output_dir / f"ts_repos{output_suffix}"
    ts_contributors_file = output_dir / f"ts_contributors{output_suffix}"
    cursor_commits_file = output_dir / "cursor_commits.csv"
    adoption_dates_file = output_dir / "ai_adoption_dates.csv"

    if not ts_repos_df.empty:
        sort_cols = ["repo_name", aggregation]
        sort_cols = [c for c in sort_cols if c in ts_repos_df.columns]
        if sort_cols:
            ts_repos_df = ts_repos_df.sort_values(sort_cols)
        ts_repos_df.to_csv(ts_repos_file, index=False)
        logging.info("Saved repo time series to %s", ts_repos_file)
    else:
        logging.warning("No repo time-series rows generated")

    if not ts_contributors_df.empty:
        sort_cols = ["repo_name", aggregation, "author"]
        sort_cols = [c for c in sort_cols if c in ts_contributors_df.columns]
        if sort_cols:
            ts_contributors_df = ts_contributors_df.sort_values(sort_cols)
        ts_contributors_df.to_csv(ts_contributors_file, index=False)
        logging.info("Saved contributor time series to %s", ts_contributors_file)
    else:
        logging.warning("No contributor time-series rows generated")

    if not cursor_commits_df.empty:
        cursor_commits_df = cursor_commits_df.sort_values(["repo_name", "authored_at"])
        cursor_commits_df.to_csv(cursor_commits_file, index=False)
        logging.info("Saved Cursor commit data to %s", cursor_commits_file)
    else:
        logging.warning("No Cursor-related commits found")

    adoption_dates_df.to_csv(adoption_dates_file, index=False)
    logging.info("Saved AI adoption dates to %s", adoption_dates_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze cloned repos and detect AI code generator adoption dates."
    )

    parser.add_argument(
        "--repos-file",
        type=Path,
        default=PROJECT_DIR / "data" / "repos.csv",
        help="CSV containing repo_name column. Default: data/repos.csv.",
    )

    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=PROJECT_DIR.parent / "CursorRepos",
        help="Directory containing cloned repos as owner_repo folders.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "data",
        help="Output directory. Default: data.",
    )

    parser.add_argument(
        "--aggregation",
        choices=["week", "month"],
        default="month",
        help="Aggregate by week or month. Default: month.",
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=None,
        help="Limit number of repos for sample testing.",
    )

    parser.add_argument(
        "--repos",
        nargs="*",
        default=None,
        help="Specific repo_name values to process, e.g., owner/repo owner2/repo2.",
    )

    parser.add_argument(
        "--num-processes",
        type=int,
        default=1,
        help="Number of worker processes. Default: 1 for safer smoke tests.",
    )

    parser.add_argument(
        "--random-sample",
        action="store_true",
        help="Use random sampling when --max-repos is set.",
    )

    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle processing order.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=114514,
        help="Random seed for sampling/shuffling.",
    )

    return parser.parse_args()


def main() -> None:
    multiprocessing.freeze_support()
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    repos_file = args.repos_file.expanduser().resolve()
    clone_dir = args.clone_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    logging.info("Original analyzer imported from: %s", ORIGINAL_SCRIPT)
    logging.info("Repos file: %s", repos_file)
    logging.info("Clone dir: %s", clone_dir)
    logging.info("Output dir: %s", output_dir)
    logging.info("Aggregation: %s", args.aggregation)

    if not clone_dir.exists():
        raise SystemExit(f"Clone directory does not exist: {clone_dir}")

    repos_df = load_repos(
        repos_file=repos_file,
        repos_filter=args.repos,
        max_repos=args.max_repos,
        random_sample=args.random_sample,
        seed=args.seed,
    )

    logging.info("Loaded %d repositories for processing", len(repos_df))

    ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df = run_analysis(
        repos_df=repos_df,
        clone_dir=clone_dir,
        output_dir=output_dir,
        aggregation=args.aggregation,
        num_processes=args.num_processes,
        seed=args.seed,
        shuffle=args.shuffle,
    )

    save_outputs(
        ts_repos_df=ts_repos_df,
        ts_contributors_df=ts_contributors_df,
        cursor_commits_df=cursor_commits_df,
        adoption_dates_df=adoption_dates_df,
        output_dir=output_dir,
        aggregation=args.aggregation,
    )

    logging.info("Finished analyze_repos_v2")
    logging.info("Repos with Cursor adoption evidence: %d", len(adoption_dates_df))


if __name__ == "__main__":
    main()

__MERGED_PYTHON_4__

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/check_time_of_event_and_adoption.py --
###############################################################################

: <<'__MERGED_PYTHON_5__'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare candidate event_month with git-detected adoption_month."
    )
    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--adoption-file", required=True)
    parser.add_argument("--output-match-file", required=True)
    parser.add_argument("--top-print", type=int, default=50)
    return parser.parse_args()


def clean_month(series: pd.Series) -> pd.Series:
    """Normalize month-like values to YYYY-MM strings."""
    s = series.astype("string").str.strip()

    # Treat common missing tokens as NA.
    s = s.mask(s.str.lower().isin(["", "nan", "nat", "none", "<na>"]))

    # Convert YYYYMM to YYYY-MM.
    yyyymm = s.str.fullmatch(r"\d{6}", na=False)
    s = s.mask(yyyymm, s.str.slice(0, 4) + "-" + s.str.slice(4, 6))

    # Keep the first 7 characters for YYYY-MM or ISO dates.
    s = s.str.slice(0, 7)

    # Keep only valid-looking YYYY-MM values.
    valid = s.str.fullmatch(r"\d{4}-\d{2}", na=False)
    s = s.mask(~valid)

    return s


def month_to_index(series: pd.Series) -> pd.Series:
    """Convert YYYY-MM strings to integer month index."""
    s = clean_month(series)
    year = pd.to_numeric(s.str.slice(0, 4), errors="coerce")
    month = pd.to_numeric(s.str.slice(5, 7), errors="coerce")
    return year * 12 + month


def pick_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    """Pick the first available column from a candidate list."""
    for col in candidates:
        if col in df.columns:
            return col
    raise SystemExit(
        f"ERROR: cannot find {label} column. Tried: {', '.join(candidates)}"
    )


def main() -> None:
    args = parse_args()

    candidate_path = Path(args.candidate_file)
    adoption_path = Path(args.adoption_file)
    output_path = Path(args.output_match_file)

    if not candidate_path.exists():
        raise SystemExit(f"ERROR: candidate file not found: {candidate_path}")

    if not adoption_path.exists():
        raise SystemExit(f"ERROR: adoption file not found: {adoption_path}")

    candidates = pd.read_csv(candidate_path)
    adoptions = pd.read_csv(adoption_path)

    if "repo_name" not in candidates.columns:
        raise SystemExit("ERROR: candidate file must contain repo_name.")

    if "repo_name" not in adoptions.columns:
        raise SystemExit("ERROR: adoption file must contain repo_name.")

    event_col = pick_column(
        candidates,
        ["event_month", "event", "candidate_event_month"],
        "event month",
    )

    adoption_col = pick_column(
        adoptions,
        ["adoption_month", "cursor_adoption_month", "detected_adoption_month"],
        "adoption month",
    )

    # Keep useful adoption-side columns without duplicating repo_name.
    adoption_keep = ["repo_name", adoption_col]
    for col in [
        "adoption_date",
        "first_cursor_commit",
        "adoption_commit",
        "confidence",
        "evidence_paths",
        "evidence",
    ]:
        if col in adoptions.columns and col not in adoption_keep:
            adoption_keep.append(col)

    adoption_small = adoptions[adoption_keep].drop_duplicates("repo_name").copy()

    if adoption_col != "adoption_month":
        adoption_small = adoption_small.rename(columns={adoption_col: "adoption_month"})

    merged = candidates.merge(adoption_small, on="repo_name", how="left")

    # Preserve the original event column but expose a standard event_month column.
    if event_col != "event_month":
        merged["event_month"] = merged[event_col]

    merged["event_month_clean"] = clean_month(merged["event_month"])
    merged["adoption_month_clean"] = clean_month(merged["adoption_month"])

    event_idx = month_to_index(merged["event_month_clean"])
    adoption_idx = month_to_index(merged["adoption_month_clean"])

    merged["month_difference"] = adoption_idx - event_idx

    # Avoid pd.NA boolean ambiguity by requiring both sides to be non-missing first.
    has_event = merged["event_month_clean"].notna()
    has_adoption = merged["adoption_month_clean"].notna()

    merged["event_month_match"] = (
        has_event
        & has_adoption
        & (merged["event_month_clean"] == merged["adoption_month_clean"])
    )

    merged["match_status"] = "mismatched"
    merged.loc[~has_event, "match_status"] = "missing_event_month"
    merged.loc[has_event & ~has_adoption, "match_status"] = "missing_adoption_month"
    merged.loc[merged["event_month_match"], "match_status"] = "matched"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)

    total = len(merged)
    matched = int(merged["event_month_match"].sum())
    missing_event = int((~has_event).sum())
    missing_adoption = int((has_event & ~has_adoption).sum())
    mismatched = int(
        (has_event & has_adoption & ~merged["event_month_match"]).sum()
    )
    detected = int(has_adoption.sum())

    print("Candidate file:", candidate_path)
    print("Adoption file: ", adoption_path)
    print("Output file:   ", output_path)
    print()

    print("Treatment repos:", total)
    print("Repos with detected adoption month:", detected)
    print("Matched event/adoption month:", matched)
    print("Mismatched event/adoption month:", mismatched)
    print("Missing event month:", missing_event)
    print("Missing adoption month:", missing_adoption)
    print()

    status_counts = merged["match_status"].value_counts(dropna=False)
    print("Match status counts:")
    print(status_counts.to_string())
    print()

    display_cols = [
        "repo_name",
        "event_month",
        "adoption_month",
        "adoption_date",
        "event_month_match",
        "match_status",
        "month_difference",
        "confidence",
        "evidence_paths",
    ]
    display_cols = [c for c in display_cols if c in merged.columns]

    print(f"Event/adoption month check, top {args.top_print}:")
    print(merged[display_cols].head(args.top_print).to_string(index=False))


if __name__ == "__main__":
    main()

__MERGED_PYTHON_5__

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/check_cache_control_repos.py --
###############################################################################

: <<'__MERGED_PYTHON_6__'
#!/usr/bin/env python3
"""Check whether run8d outputs already cover the requested repositories.

This script is intentionally small and shell-friendly: it writes KEY=VALUE lines
on stdout so run8d-analyze-control-repos.sh can tee the report to logs and grep
CACHE_STATUS from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def clean_repo_series(series: pd.Series) -> pd.Series:
    """Normalize repository names and remove empty/nan-like values."""
    out = series.astype("string").str.strip()
    out = out.mask(out.isna() | out.eq("") | out.str.lower().eq("nan"))
    return out


def usage() -> str:
    return (
        "Usage: check_run8d_cache.py "
        "<repos_file> <repo_ts_file> <contrib_ts_file> "
        "<cursor_commits_file> <adoption_file> <manifest_file> "
        "<missing_repos_file>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 8:
        print("CACHE_STATUS=error")
        print("ERROR=bad_arg_count")
        print(usage(), file=sys.stderr)
        return 2

    repos_file = Path(argv[1])
    repo_ts_file = Path(argv[2])
    contrib_ts_file = Path(argv[3])
    cursor_commits_file = Path(argv[4])
    adoption_file = Path(argv[5])
    manifest_file = Path(argv[6])
    missing_repos_file = Path(argv[7])

    required_outputs = [
        repo_ts_file,
        contrib_ts_file,
        cursor_commits_file,
        adoption_file,
    ]

    repos = pd.read_csv(repos_file)
    if "repo_name" not in repos.columns:
        print("CACHE_STATUS=error")
        print("ERROR=repo_name_missing")
        return 1


    repos["repo_name"] = clean_repo_series(repos["repo_name"])
    repos = repos[repos["repo_name"].notna()].drop_duplicates("repo_name")
    requested = set(repos["repo_name"])

    missing_outputs = [str(p) for p in required_outputs if not p.exists()]
    if missing_outputs:
        missing_repos_file.parent.mkdir(parents=True, exist_ok=True)
        repos.to_csv(missing_repos_file, index=False)
        print("CACHE_STATUS=run_full")
        print("CACHE_REASON=missing_required_outputs")
        print("MISSING_OUTPUTS=" + ";".join(missing_outputs))
        print(f"REQUESTED_REPOS={len(requested)}")
        print(f"MISSING_REPOS={len(requested)}")
        print(f"MISSING_REPOS_FILE={missing_repos_file}")
        return 0

    done: set[str] = set()

    # Prefer explicit manifest if it exists.
    if manifest_file.exists():
        try:
            manifest = pd.read_csv(manifest_file)
            if "repo_name" in manifest.columns:
                manifest["repo_name"] = clean_repo_series(manifest["repo_name"])
                done = set(manifest["repo_name"].dropna())

        except Exception:
            done = set()

    # Fallback: infer analyzed repos from ts_repos_<aggregation>ly.csv.
    if not done:
        try:
            ts = pd.read_csv(repo_ts_file, usecols=lambda c: c == "repo_name")
            ts["repo_name"] = clean_repo_series(ts["repo_name"])
            done = set(ts["repo_name"].dropna())

        except Exception:
            done = set()

    missing = sorted(requested - done)
    missing_df = repos[repos["repo_name"].isin(missing)].copy()
    missing_repos_file.parent.mkdir(parents=True, exist_ok=True)
    missing_df.to_csv(missing_repos_file, index=False)

    print(f"REQUESTED_REPOS={len(requested)}")
    print(f"ANALYZED_REPOS_IN_CACHE={len(done)}")
    print(f"MISSING_REPOS={len(missing)}")
    print(f"MISSING_REPOS_FILE={missing_repos_file}")

    if len(missing) == 0:
        print("CACHE_STATUS=complete")
        print("CACHE_REASON=all_requested_repos_already_analyzed")
    else:
        print("CACHE_STATUS=partial")
        print("CACHE_REASON=some_requested_repos_missing_from_existing_outputs")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

__MERGED_PYTHON_6__

###############################################################################
# -- SHELL SCRIPT: run-py-1f-save-treatment-options.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-1f: Save Python treatment sample options
# ============================================================
#
# Input:
#   repo_python/treatment_python_did/adoption_month_check.csv
#
# Outputs:
#   repo_python/run-py-1f/treatment_python_sample_main_<N>.csv
#     - Primary treatment sample used by run-py-1g.
#
#   repo_python/tmp/run-py-1f/treatment_python_sample_exact_match_<N>.csv
#   repo_python/tmp/run-py-1f/treatment_python_sample_within1_month_<N>.csv
#   repo_python/tmp/run-py-1f/treatment_python_sample_diagnostic_<N>.csv
#     - Alternative and diagnostic treatment samples.
#
# Expected current Python result:
#   main       = 118
#   exact      = 118
#   within1    = 118
#   diagnostic = 0
# 
# Usage:
#   bash run-py-1f-save-treatment-options.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1f_save_treatment_options_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/save_treatment_options.py}"

# OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
# TMP_DIR="${TMP_DIR:-${OUTPUT_DIR}/tmp/run-py-1f}"
# CHECK_FILE="${CHECK_FILE:-${OUTPUT_DIR}/treatment_python_did/adoption_month_check.csv}"
OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1f}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1f}"
CHECK_FILE="${CHECK_FILE:-${OUTPUT_BASE_DIR}/treatment_python_did/adoption_month_check.csv}"

PREFIX="${PREFIX:-treatment_python_sample}"
TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1f: save Python treatment sample options" | tee -a "${LOG_FILE}"
echo "Timestamp:        ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:    ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Check file:       ${CHECK_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:  ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
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

# Remove stale option files from the extra-output directory.
find "${TMP_DIR}" \
  -maxdepth 1 \
  -type f \
  -name "${PREFIX}_*.csv" \
  -delete

set +e
python "${PY_SCRIPT}" \
  --check-file "${CHECK_FILE}" \
  --output-dir "${TMP_DIR}" \
  --prefix "${PREFIX}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"

run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: treatment option saving failed with exit code ${run_status}" | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi


# Move the primary treatment sample into the main output directory.
MAIN_SAMPLE_FILE="$(
  find "${TMP_DIR}" \
    -maxdepth 1 \
    -type f \
    -name "${PREFIX}_main_*.csv" \
    -print
)"

if [[ -z "${MAIN_SAMPLE_FILE}" ]]; then
  echo "ERROR: primary treatment sample was not generated in ${TMP_DIR}" | tee -a "${LOG_FILE}"
  exit 1
fi

MAIN_SAMPLE_COUNT="$(printf '%s\n' "${MAIN_SAMPLE_FILE}" | sed '/^$/d' | wc -l)"
if [[ "${MAIN_SAMPLE_COUNT}" -ne 1 ]]; then
  echo "ERROR: expected one primary treatment sample, found ${MAIN_SAMPLE_COUNT}" | tee -a "${LOG_FILE}"
  printf '%s\n' "${MAIN_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
  exit 1
fi

MAIN_OUTPUT_FILE="${OUTPUT_DIR}/$(basename "${MAIN_SAMPLE_FILE}")"
mv -f "${MAIN_SAMPLE_FILE}" "${MAIN_OUTPUT_FILE}"

# Remove stale primary files with a different row-count suffix.
find "${OUTPUT_DIR}" \
  -maxdepth 1 \
  -type f \
  -name "${PREFIX}_main_*.csv" \
  ! -name "$(basename "${MAIN_OUTPUT_FILE}")" \
  -delete

echo "Primary treatment sample: ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${OUTPUT_DIR}"/"${PREFIX}"_main_*.csv \
  "${TMP_DIR}"/"${PREFIX}"_*.csv
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1f completed successfully." | tee -a "${LOG_FILE}"
echo "Main output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
# -- CALLED PYTHON SCRIPT: proc_scripts/save_treatment_options.py --
###############################################################################

: <<'__MERGED_PYTHON_7__'
#!/usr/bin/env python3
"""
Save treatment sample options from adoption-month validation results.

This script reads an adoption_month_check.csv file and creates four
treatment sample files:

1. main
   - All valid event-month treatment repositories.
   - This is the primary sample for the unbalanced-panel replication.

2. exact
   - Repositories where event_month exactly matches git-detected adoption_month.

3. within1
   - Repositories where:
       a) event_month exactly matches adoption_month, or
       b) event_month and adoption_month differ by at most one month.
   - This can be used as a robustness sample.

4. diagnostic
   - Repositories with missing local adoption evidence or large mismatch.
   - This file is for audit/debugging, not for primary analysis.

Expected input columns:
  repo_name
  event_month
  adoption_month
  match_status
  month_difference

Additional columns are preserved in all output files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create main/exact/within1/diagnostic treatment samples."
    )

    parser.add_argument(
        "--check-file",
        required=True,
        help="Input adoption_month_check.csv file.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where treatment sample option files will be saved.",
    )
    parser.add_argument(
        "--prefix",
        default="treatment_sample",
        help="Output filename prefix.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of diagnostic rows to print.",
    )

    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: list[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(
            f"ERROR: {path} is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> int:
    args = parse_args()

    check_path = Path(args.check_file)
    out_dir = Path(args.output_dir)

    if not check_path.exists():
        raise SystemExit(f"ERROR: check file not found: {check_path}")

    df = pd.read_csv(check_path)

    require_columns(
        df,
        required=["repo_name", "event_month", "match_status", "month_difference"],
        path=check_path,
    )

    # Main sample:
    # Keep all validated treatment repositories. This is the primary sample.
    main = df.copy()

    # Exact-match sample:
    # Keep repositories where baseline event_month equals local git adoption_month.
    exact = df[df["match_status"].eq("matched")].copy()

    # Within-one-month sample:
    # Keep exact matches plus small timing differences.
    month_diff = pd.to_numeric(df["month_difference"], errors="coerce")
    within1 = df[
        df["match_status"].eq("matched")
        | (
            df["match_status"].eq("mismatched")
            & month_diff.abs().le(1)
        )
    ].copy()

    # Diagnostic sample:
    # Missing local adoption evidence or mismatch larger than one month.
    diagnostic = df[
        df["match_status"].eq("missing_adoption_month")
        | (
            df["match_status"].eq("mismatched")
            & ~month_diff.abs().le(1)
        )
    ].copy()

    files = {
        "main": out_dir / f"{args.prefix}_main_{len(main)}.csv",
        "exact": out_dir / f"{args.prefix}_exact_match_{len(exact)}.csv",
        "within1": out_dir / f"{args.prefix}_within1_month_{len(within1)}.csv",
        "diagnostic": out_dir / f"{args.prefix}_diagnostic_{len(diagnostic)}.csv",
    }

    save_csv(main, files["main"])
    save_csv(exact, files["exact"])
    save_csv(within1, files["within1"])
    save_csv(diagnostic, files["diagnostic"])

    print("Input file:", check_path)
    print("Input rows:", len(df))
    print("Unique repos:", df["repo_name"].nunique())
    print()

    print("Match status counts:")
    print(df["match_status"].fillna("(missing)").value_counts(dropna=False).to_string())
    print()

    print("Saved treatment sample files:")
    print("Main rows:", len(main), "->", files["main"])
    print("Exact matched rows:", len(exact), "->", files["exact"])
    print("Within-one-month rows:", len(within1), "->", files["within1"])
    print("Diagnostic rows:", len(diagnostic), "->", files["diagnostic"])
    print()

    print("Diagnostic repos:")
    cols = [
        "repo_name",
        "repo_primary_language",
        "event_month",
        "adoption_month",
        "match_status",
        "month_difference",
        "confidence",
        "evidence_paths",
    ]
    cols = [c for c in cols if c in diagnostic.columns]

    if len(diagnostic) == 0:
        print("(No diagnostic repos.)")
    else:
        print(diagnostic[cols].head(args.top_print).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_7__

###############################################################################
# -- SHELL SCRIPT: run-py-1g-extract-control-repos.sh --
###############################################################################

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
#   repo_python/run-py-1f/treatment_python_sample_main_118.csv
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
# Main outputs:
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#     - Clean treatment-control pair file after overlap removal.
#
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#     - Unique clean control repos to clone in the next step.
#
# Extra outputs:
#   repo_python/tmp/run-py-1g/python_treatment_missing_matching_main_118.csv
#     - Treatment repos without matching rows.
#
#   repo_python/tmp/run-py-1g/python_control_extract_summary_main_118.csv
#     - Summary metrics for audit.
#
#   Raw pairs, raw controls, overlap diagnostics, and coverage files
#   are also stored under repo_python/tmp/run-py-1g.
# 
# Usage:
#   bash run-py-1g-extract-control-repos.sh
# 
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1g_extract_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/extract_matched_control_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1g}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/run-py-1g}"

SAMPLE_NAME="${SAMPLE_NAME:-main_118}"

TREATMENT_SAMPLE_FILE="${TREATMENT_SAMPLE_FILE:-${OUTPUT_BASE_DIR}/run-py-1f/treatment_python_sample_${SAMPLE_NAME}.csv}"
MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"

PAIR_OUTPUT_FILE="${PAIR_OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_${SAMPLE_NAME}.csv}"
CONTROL_CLONE_FILE="${CONTROL_CLONE_FILE:-${MAIN_OUTPUT_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}.csv}"

MISSING_MATCH_FILE="${MISSING_MATCH_FILE:-${TMP_DIR}/python_treatment_missing_matching_${SAMPLE_NAME}.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_extract_summary_${SAMPLE_NAME}.csv}"

RAW_PAIR_OUTPUT_FILE="${RAW_PAIR_OUTPUT_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_raw.csv}"
RAW_CONTROL_CLONE_FILE="${RAW_CONTROL_CLONE_FILE:-${TMP_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}_raw.csv}"
OVERLAP_PAIR_FILE="${OVERLAP_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_overlap_pairs.csv}"
OVERLAP_REPO_FILE="${OVERLAP_REPO_FILE:-${TMP_DIR}/python_control_repos_to_clone_${SAMPLE_NAME}_overlap_repos.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_NAME}_coverage.csv}"

FULL_ADOPTER_FILE="${FULL_ADOPTER_FILE:-data_baseline_backup/panel_event_monthly.csv}"
FULL_ADOPTER_FILTER_COLUMN="${FULL_ADOPTER_FILTER_COLUMN:-is_treatment}"
FULL_ADOPTER_FILTER_VALUE="${FULL_ADOPTER_FILTER_VALUE:-1}"

TOP_PRINT="${TOP_PRINT:-50}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"


echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1g: extract matched Python control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:                     ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                 ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment sample file:         ${TREATMENT_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
echo "Matching file:                 ${MATCHING_FILE}" | tee -a "${LOG_FILE}"
echo "Sample name:                   ${SAMPLE_NAME}" | tee -a "${LOG_FILE}"
echo "Main output dir:               ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:              ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
echo "Main output dir: ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/extract_matched_control_repos.py --
###############################################################################

: <<'__MERGED_PYTHON_8__'
#!/usr/bin/env python3
"""
Extract matched control repositories for the JS/TS treatment sample.

Primary outputs are CLEAN outputs:
  - matched controls that overlap with the current treatment sample are removed
  - matched controls that overlap with the full Cursor-adopting population are removed

Raw outputs and overlap diagnostics are preserved for audit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


CONTROL_COLUMNS = ["matched_control_1", "matched_control_2", "matched_control_3"]

TREATMENT_METADATA_COLUMNS = [
    "repo_primary_language",
    "event_month",
    "adoption_month",
    "match_status",
    "month_difference",
    "target_dir",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract clean matched controls for JS/TS treatment repositories."
    )

    parser.add_argument("--treatment-sample-file", type=Path, required=True)
    parser.add_argument("--matching-file", type=Path, required=True)
    parser.add_argument("--pair-output-file", type=Path, required=True)
    parser.add_argument("--control-clone-file", type=Path, required=True)
    parser.add_argument("--missing-match-file", type=Path, required=True)
    parser.add_argument("--summary-file", type=Path, required=True)

    parser.add_argument(
        "--full-adopter-file",
        type=Path,
        default=Path("data_baseline_backup/panel_event_monthly.csv"),
        help="CSV file used to identify the full Cursor-adopting population.",
    )
    parser.add_argument(
        "--full-adopter-filter-column",
        default="is_treatment",
        help="Column used to filter full adopters.",
    )
    parser.add_argument(
        "--full-adopter-filter-value",
        default="1",
        help="Value indicating full adopters in the filter column.",
    )

    parser.add_argument("--raw-pair-output-file", type=Path, default=None)
    parser.add_argument("--raw-control-clone-file", type=Path, default=None)
    parser.add_argument("--overlap-pair-file", type=Path, default=None)
    parser.add_argument("--overlap-repo-file", type=Path, default=None)
    parser.add_argument("--coverage-file", type=Path, default=None)

    parser.add_argument(
        "--keep-full-adopter-overlap",
        action="store_true",
        help="Do not remove controls that overlap with the full adopter population.",
    )
    parser.add_argument(
        "--keep-current-treatment-overlap",
        action="store_true",
        help="Do not remove controls that overlap with the current treatment sample.",
    )
    parser.add_argument(
        "--fail-on-overlap",
        action="store_true",
        help="Fail with exit code 2 if any overlap is detected.",
    )
    parser.add_argument("--top-print", type=int, default=30)

    return parser.parse_args()


def default_sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def normalize_repo_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"ERROR: {label} missing columns: {sorted(missing)}. "
            f"Available columns: {list(df.columns)}"
        )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_treatment_and_matching(
    treatment_path: Path,
    matching_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    require_file(treatment_path, "treatment sample file")
    require_file(matching_path, "matching file")

    treat = pd.read_csv(treatment_path)
    match = pd.read_csv(matching_path)

    require_columns(treat, {"repo_name"}, "treatment sample")
    require_columns(match, {"repo_name", *CONTROL_COLUMNS}, "matching file")

    treat = treat.copy()
    match = match.copy()

    treat["repo_name"] = normalize_repo_series(treat["repo_name"])
    match["repo_name"] = normalize_repo_series(match["repo_name"])

    treat = treat[treat["repo_name"].ne("")]
    match = match[match["repo_name"].ne("")]

    treat = treat.drop_duplicates("repo_name", keep="first").copy()

    return treat, match


def load_full_adopters(
    full_adopter_file: Path,
    filter_column: str,
    filter_value: str,
) -> set[str]:
    if not full_adopter_file.exists():
        print(f"WARNING: full adopter file not found: {full_adopter_file}")
        return set()

    needed_columns = {"repo_name", filter_column}

    try:
        df = pd.read_csv(
            full_adopter_file,
            usecols=lambda c: c in needed_columns,
        )
    except Exception:
        df = pd.read_csv(full_adopter_file)

    if "repo_name" not in df.columns:
        print(f"WARNING: full adopter file has no repo_name column: {full_adopter_file}")
        return set()

    if filter_column not in df.columns:
        print(
            f"WARNING: full adopter file has no {filter_column} column; "
            "not using it as full adopter source."
        )
        return set()

    values = df[filter_column]

    # Numeric comparison first, then string fallback.
    value_numeric = pd.to_numeric(values, errors="coerce")
    try:
        target_numeric = float(filter_value)
        mask = value_numeric.eq(target_numeric)
    except ValueError:
        mask = values.astype(str).str.lower().eq(str(filter_value).lower())

    adopters = set(
        df.loc[mask, "repo_name"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    adopters.discard("")

    return adopters


def subset_matching_rows(treat: pd.DataFrame, match: pd.DataFrame) -> pd.DataFrame:
    treatment_repos = set(treat["repo_name"])
    match_subset = match[match["repo_name"].isin(treatment_repos)].copy()

    # matching.csv can contain both treatment rows and control rows.
    # The treatment rows are the ones carrying matched_control_1/2/3.
    if "group" in match_subset.columns:
        treatment_like = match_subset[
            match_subset["group"].astype(str).str.lower().eq("treatment")
        ].copy()
        if not treatment_like.empty:
            match_subset = treatment_like

    match_subset = match_subset.drop_duplicates("repo_name", keep="first").copy()
    return match_subset


def build_pairs(treat: pd.DataFrame, match_subset: pd.DataFrame) -> pd.DataFrame:
    treat_lookup = treat.set_index("repo_name", drop=False)
    pairs: list[dict] = []

    for _, row in match_subset.iterrows():
        treatment_repo = str(row["repo_name"]).strip()
        if not treatment_repo:
            continue

        for rank, col in enumerate(CONTROL_COLUMNS, start=1):
            control_repo = row.get(col)

            if pd.isna(control_repo):
                continue

            control_repo = str(control_repo).strip()
            if not control_repo:
                continue

            rec = {
                "treatment_repo": treatment_repo,
                "control_repo": control_repo,
                "control_rank": rank,
                "matched_period": row.get("matched_period"),
                "matching_propensity_score": row.get("propensity_score"),
            }

            if treatment_repo in treat_lookup.index:
                trow = treat_lookup.loc[treatment_repo]
                for meta_col in TREATMENT_METADATA_COLUMNS:
                    if meta_col in trow.index:
                        rec[meta_col] = trow[meta_col]

            pairs.append(rec)

    pairs_df = pd.DataFrame(pairs)

    if pairs_df.empty:
        raise SystemExit("ERROR: no matched control pairs were extracted.")

    pairs_df["treatment_repo"] = normalize_repo_series(pairs_df["treatment_repo"])
    pairs_df["control_repo"] = normalize_repo_series(pairs_df["control_repo"])

    return pairs_df


def build_control_clone_list(pairs_df: pd.DataFrame) -> pd.DataFrame:
    return (
        pairs_df[["control_repo"]]
        .drop_duplicates()
        .rename(columns={"control_repo": "repo_name"})
        .sort_values("repo_name")
        .reset_index(drop=True)
    )


def build_coverage(clean_pairs_df: pd.DataFrame) -> pd.DataFrame:
    if clean_pairs_df.empty:
        return pd.DataFrame(columns=["treatment_repo", "num_unique_controls"])

    return (
        clean_pairs_df.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_unique_controls")
        .sort_values(["num_unique_controls", "treatment_repo"])
        .reset_index(drop=True)
    )


def main() -> None:
    args = parse_args()

    pair_output_path = args.pair_output_file
    control_clone_path = args.control_clone_file
    missing_match_path = args.missing_match_file
    summary_path = args.summary_file

    raw_pair_output_path = args.raw_pair_output_file or default_sidecar(
        pair_output_path, "_raw"
    )
    raw_control_clone_path = args.raw_control_clone_file or default_sidecar(
        control_clone_path, "_raw"
    )
    overlap_pair_path = args.overlap_pair_file or default_sidecar(
        pair_output_path, "_overlap_pairs"
    )
    overlap_repo_path = args.overlap_repo_file or default_sidecar(
        control_clone_path, "_overlap_repos"
    )
    coverage_path = args.coverage_file or default_sidecar(
        pair_output_path, "_coverage"
    )

    treat, match = load_treatment_and_matching(
        args.treatment_sample_file,
        args.matching_file,
    )

    current_treatment_repos = set(treat["repo_name"])

    full_adopters = load_full_adopters(
        args.full_adopter_file,
        args.full_adopter_filter_column,
        args.full_adopter_filter_value,
    )

    match_subset = subset_matching_rows(treat, match)
    matched_treatments = set(match_subset["repo_name"])
    missing_treatments = treat[~treat["repo_name"].isin(matched_treatments)].copy()

    raw_pairs_df = build_pairs(treat, match_subset)
    raw_controls_df = build_control_clone_list(raw_pairs_df)

    raw_pairs_df["overlap_current_treatment_sample"] = raw_pairs_df[
        "control_repo"
    ].isin(current_treatment_repos)

    raw_pairs_df["overlap_full_adopter_population"] = raw_pairs_df[
        "control_repo"
    ].isin(full_adopters)

    remove_mask = pd.Series(False, index=raw_pairs_df.index)

    if not args.keep_current_treatment_overlap:
        remove_mask = remove_mask | raw_pairs_df["overlap_current_treatment_sample"]

    if not args.keep_full_adopter_overlap:
        remove_mask = remove_mask | raw_pairs_df["overlap_full_adopter_population"]

    overlap_pairs_df = raw_pairs_df[remove_mask].copy()
    clean_pairs_df = raw_pairs_df[~remove_mask].copy()

    clean_controls_df = build_control_clone_list(clean_pairs_df)
    coverage_df = build_coverage(clean_pairs_df)

    overlap_repos_df = (
        overlap_pairs_df[
            [
                "control_repo",
                "overlap_current_treatment_sample",
                "overlap_full_adopter_population",
            ]
        ]
        .drop_duplicates()
        .rename(columns={"control_repo": "repo_name"})
        .sort_values("repo_name")
        .reset_index(drop=True)
    )

    summary_df = pd.DataFrame(
        [
            {"metric": "treatment_sample_rows", "value": len(treat)},
            {"metric": "full_adopter_population_rows", "value": len(full_adopters)},
            {"metric": "matching_rows_for_treatment_sample", "value": len(match_subset)},
            {"metric": "treatments_missing_matching_row", "value": len(missing_treatments)},
            {"metric": "raw_matched_pair_rows", "value": len(raw_pairs_df)},
            {"metric": "clean_matched_pair_rows", "value": len(clean_pairs_df)},
            {"metric": "removed_overlap_pair_rows", "value": len(overlap_pairs_df)},
            {"metric": "raw_unique_control_repos", "value": raw_controls_df["repo_name"].nunique()},
            {"metric": "clean_unique_control_repos", "value": clean_controls_df["repo_name"].nunique()},
            {"metric": "removed_overlap_unique_control_repos", "value": overlap_repos_df["repo_name"].nunique()},
            {
                "metric": "current_treatment_overlap_unique_control_repos",
                "value": raw_controls_df["repo_name"].isin(current_treatment_repos).sum(),
            },
            {
                "metric": "full_adopter_overlap_unique_control_repos",
                "value": raw_controls_df["repo_name"].isin(full_adopters).sum(),
            },
            {
                "metric": "treatment_repos_with_clean_pairs",
                "value": clean_pairs_df["treatment_repo"].nunique(),
            },
            {
                "metric": "treatment_repos_missing_after_cleaning",
                "value": len(treat) - clean_pairs_df["treatment_repo"].nunique(),
            },
        ]
    )

    save_csv(raw_pairs_df, raw_pair_output_path)
    save_csv(raw_controls_df, raw_control_clone_path)
    save_csv(clean_pairs_df, pair_output_path)
    save_csv(clean_controls_df, control_clone_path)
    save_csv(missing_treatments, missing_match_path)
    save_csv(overlap_pairs_df, overlap_pair_path)
    save_csv(overlap_repos_df, overlap_repo_path)
    save_csv(coverage_df, coverage_path)
    save_csv(summary_df, summary_path)

    print("Treatment sample rows:", len(treat))
    print("Full adopter population size:", len(full_adopters))
    print("Matching rows for treatment sample:", len(match_subset))
    print("Treatments missing matching row:", len(missing_treatments))
    print("Raw matched pair rows:", len(raw_pairs_df))
    print("Clean matched pair rows:", len(clean_pairs_df))
    print("Removed overlap pair rows:", len(overlap_pairs_df))
    print("Raw unique control repos:", raw_controls_df["repo_name"].nunique())
    print("Clean unique control repos:", clean_controls_df["repo_name"].nunique())
    print("Removed overlap unique control repos:", overlap_repos_df["repo_name"].nunique())
    print("Treatment repos with clean pairs:", clean_pairs_df["treatment_repo"].nunique())
    print()

    print("Overlap unique control repos:")
    if overlap_repos_df.empty:
        print("(none)")
    else:
        print(overlap_repos_df.to_string(index=False))
    print()

    print("Control-count distribution after overlap removal:")
    if coverage_df.empty:
        print("(empty)")
    else:
        print(coverage_df["num_unique_controls"].value_counts().sort_index().to_string())
    print()

    print("Saved CLEAN pair output:", pair_output_path)
    print("Saved CLEAN control clone list:", control_clone_path)
    print("Saved missing match file:", missing_match_path)
    print("Saved overlap pair file:", overlap_pair_path)
    print("Saved overlap repo file:", overlap_repo_path)
    print("Saved raw pair output:", raw_pair_output_path)
    print("Saved raw control clone list:", raw_control_clone_path)
    print("Saved coverage file:", coverage_path)
    print("Saved summary file:", summary_path)
    print()

    print(f"Top {args.top_print} CLEAN matched pairs:")
    print(clean_pairs_df.head(args.top_print).to_string(index=False))

    if args.fail_on_overlap and not overlap_pairs_df.empty:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_8__

###############################################################################
# -- SHELL SCRIPT: run-py-1h-clone-control-repos.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-1h: Clone matched control repositories
# ============================================================
#
# This wrapper is adapted from the logic of run8b-clone-jsts-control-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
# Input:
#   repo_python/run-py-1g/python_control_repos_to_clone_main_118.csv
#
# Main output:
#   repo_python/run-py-1h/python_control_clone_status_main_118.csv
#
# Extra output:
#   repo_python/tmp/run-py-1h/python_control_clone_status_main_118_<timestamp>.csv
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

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_clone_control_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/clone_repos_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

SAMPLE_NAME="${SAMPLE_NAME:-main_118}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${OUTPUT_BASE_DIR}/run-py-1g/python_control_repos_to_clone_${SAMPLE_NAME}.csv}"

CLONE_ROOT="${CLONE_ROOT:-../control-repos}"

MAX_CLONES="${MAX_CLONES:-10}"
EXISTING_ACTION="${EXISTING_ACTION:-skip}"

CLONE_LOG_PREFIX="${CLONE_LOG_PREFIX:-${RUN_PREFIX}_control_clone_log}"
CLONE_LOG_CSV="${LOG_DIR}/${CLONE_LOG_PREFIX}_${RUN_TS}.csv"

CHECK_OUTPUT_FILE="${CHECK_OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_status_${SAMPLE_NAME}.csv}"
CHECK_OUTPUT_BACKUP="${CHECK_OUTPUT_BACKUP:-${TMP_DIR}/python_control_clone_status_${SAMPLE_NAME}_${RUN_TS}.csv}"
 
mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}" "${CLONE_ROOT}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1h: clone matched control repositories" | tee -a "${LOG_FILE}"
echo "Timestamp:             ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:           ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:            ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:         ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Control repos file:    ${CONTROL_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Sample name:           ${SAMPLE_NAME}" | tee -a "${LOG_FILE}"
echo "Main output dir:       ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:      ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
echo "Main output dir:     ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:    ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Control clone root:  ${CLONE_ROOT}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/clone_repos_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_9__'
#!/usr/bin/env python3
"""
Clone repositories from a candidate CSV file.

This script extends the original scripts/clone_repos.py behavior without
modifying the original file.

Original reusable logic:
  - ensure_dir()
  - is_git_repo()
  - pull_latest_changes()

New v2 logic:
  - read arbitrary CSV with repo_name column
  - clone into a user-specified clone root
  - save timestamped clone log under ./logs
  - support max clone count for smoke tests
  - skip existing repositories by default
"""

from __future__ import annotations

import os
import argparse
import csv
import importlib.util
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "clone_repos.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original clone script not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location("original_clone_repos", ORIGINAL_SCRIPT)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone repositories from a candidate CSV file."
    )

    parser.add_argument(
        "--repos-file",
        type=Path,
        required=True,
        help="CSV file containing repo_name column, or TXT file with one repo per line.",
    )

    parser.add_argument(
        "--repo-column",
        default="repo_name",
        help="Column containing GitHub repo names. Default: repo_name.",
    )

    parser.add_argument(
        "--clone-root",
        type=Path,
        default=PROJECT_DIR.parent / "ai_code_complexity_study_repo_dataset",
        help="Directory where repositories will be cloned.",
    )

    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=PROJECT_DIR / "logs",
        help="Directory for timestamped clone logs.",
    )

    parser.add_argument(
        "--log-prefix",
        default="run4a_clone_log",
        help="Clone log filename prefix.",
    )

    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional timestamp for log file. Default: current YYYYMMDD-HHMM.",
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=0,
        help="Maximum repos to process. Use 0 for all.",
    )

    parser.add_argument(
        "--existing-action",
        choices=["skip", "pull"],
        default="skip",
        help=(
            "What to do if target repo already exists. "
            "skip is safer for this study; pull refreshes existing clones."
        ),
    )

    parser.add_argument(
        "--git-clone-extra-arg",
        action="append",
        default=[],
        help=(
            "Extra argument passed to git clone. Can be repeated. "
            "Do not use --depth 1 because full history is needed."
        ),
    )

    return parser.parse_args()


def deduplicate_repo_names(repos: list[str]) -> list[str]:
    """Preserve input order while removing duplicate repo names."""
    seen = set()
    unique_repos = []

    for repo in repos:
        repo = str(repo).strip()
        if not repo:
            continue
        if repo not in seen:
            unique_repos.append(repo)
            seen.add(repo)

    return unique_repos


def write_normalized_csv(input_path: Path, repos: list[str], repo_column: str) -> Path:
    """
    Write a normalized CSV next to a TXT input file.

    Example:
      control_repos_to_clone_v2.txt
      -> control_repos_to_clone_v2.csv
    """
    output_path = input_path.with_suffix(".csv")

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[repo_column])
        writer.writeheader()
        for repo in repos:
            writer.writerow({repo_column: repo})

    logging.info("Wrote normalized CSV: %s", output_path)
    logging.info("Normalized CSV repositories: %d", len(repos))

    return output_path


def read_repo_names(repos_path: Path, repo_column: str) -> list[str]:
    """
    Read repository names from either:
      - CSV file with repo_column
      - TXT file with one owner/repo per line

    If a TXT file is provided, also write a normalized sibling CSV.
    """
    if not repos_path.exists():
        raise FileNotFoundError(f"Repos file not found: {repos_path}")

    repos: list[str] = []

    if repos_path.suffix.lower() == ".txt":
        repos = [
            line.strip()
            for line in repos_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        repos = deduplicate_repo_names(repos)
        write_normalized_csv(repos_path, repos, repo_column)
        return repos

    with repos_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None or repo_column not in reader.fieldnames:
            raise ValueError(
                f"Column {repo_column!r} not found in {repos_path}. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            repo = str(row.get(repo_column, "")).strip()
            if repo:
                repos.append(repo)

    return deduplicate_repo_names(repos)


def clone_repository_v2(
    repo_name: str,
    clone_path: Path,
    extra_args: Iterable[str],
) -> tuple[bool, str]:
    repo_url = f"https://github.com/{repo_name}.git"
    cmd = ["git", "clone", *extra_args, repo_url, str(clone_path)]

    try:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        logging.info("Successfully cloned %s", repo_name)
        return True, "ok"
    except subprocess.CalledProcessError as exc:
        note = (exc.stderr or exc.stdout or "git_clone_failed").strip()
        logging.error("Failed to clone %s: %s", repo_name, note)
        return False, note.replace("\n", " ")[:300]
    except Exception as exc:
        logging.error("Failed to clone %s: %s", repo_name, exc)
        return False, str(exc).replace("\n", " ")[:300]


def write_log_row(writer, repo_name: str, status: str, target_dir: Path, note: str) -> None:
    writer.writerow(
        {
            "repo_name": repo_name,
            "status": status,
            "target_dir": str(target_dir),
            "note": note,
        }
    )


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    repos_file = args.repos_file.expanduser().resolve()
    clone_root = args.clone_root.expanduser().resolve()
    logs_dir = args.logs_dir.expanduser().resolve()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d-%H%M")
    log_file = logs_dir / f"{args.log_prefix}_{timestamp}.csv"

    orig.ensure_dir(clone_root)
    orig.ensure_dir(logs_dir)

    repos = read_repo_names(repos_file, args.repo_column)

    if args.max_repos > 0:
        repos = repos[: args.max_repos]

    logging.info("Repos file: %s", repos_file)
    logging.info("Clone root: %s", clone_root)
    logging.info("Log file: %s", log_file)
    logging.info("Existing action: %s", args.existing_action)
    logging.info("Repositories to process: %d", len(repos))

    cloned = 0
    skipped = 0
    updated = 0
    failed = 0

    with log_file.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["repo_name", "status", "target_dir", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, repo_name in enumerate(repos, start=1):
            target_dir = clone_root / repo_name.replace("/", "_")

            logging.info("[%d/%d] %s -> %s", idx, len(repos), repo_name, target_dir)

            if target_dir.exists():
                if orig.is_git_repo(target_dir):
                    if args.existing_action == "skip":
                        logging.info("Already cloned. Skipping %s", repo_name)
                        write_log_row(
                            writer,
                            repo_name,
                            "skipped_existing",
                            target_dir,
                            "already_has_git_dir",
                        )
                        skipped += 1
                        continue

                    if args.existing_action == "pull":
                        ok = orig.pull_latest_changes(target_dir, repo_name)
                        if ok:
                            write_log_row(
                                writer,
                                repo_name,
                                "updated_existing",
                                target_dir,
                                "pulled_latest_changes",
                            )
                            updated += 1
                        else:
                            write_log_row(
                                writer,
                                repo_name,
                                "failed",
                                target_dir,
                                "pull_latest_changes_failed",
                            )
                            failed += 1
                        continue

                logging.warning(
                    "Path exists but is not a valid Git repo: %s",
                    target_dir,
                )
                write_log_row(
                    writer,
                    repo_name,
                    "failed",
                    target_dir,
                    "path_exists_not_git_repo",
                )
                failed += 1
                continue

            ok, note = clone_repository_v2(
                repo_name=repo_name,
                clone_path=target_dir,
                extra_args=args.git_clone_extra_arg,
            )

            if ok:
                write_log_row(writer, repo_name, "cloned", target_dir, note)
                cloned += 1
            else:
                write_log_row(writer, repo_name, "failed", target_dir, note)
                failed += 1

    logging.info("")
    logging.info("Clone summary")
    logging.info("-------------")
    logging.info("processed: %d", len(repos))
    logging.info("cloned:    %d", cloned)
    logging.info("updated:   %d", updated)
    logging.info("skipped:   %d", skipped)
    logging.info("failed:    %d", failed)
    logging.info("clone log: %s", log_file)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_9__

###############################################################################
# -- SHELL SCRIPT: run-py-1i-create-control-usable-repos.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-1i: Create clone-usable control repository sample
# ============================================================
#
#   repo_python/run-py-1h/python_control_clone_status_main_<N>.csv
#   repo_python/run-py-1g/python_matched_control_pairs_main_<N>.csv
#   repo_python/run-py-1g/python_control_repos_to_clone_main_<N>.csv
#
# Main outputs:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#   repo_python/run-py-1i/python_matched_control_pairs_main_clone_usable.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1i/python_control_clone_failed_repos_main.csv
#   repo_python/tmp/run-py-1i/python_matched_control_pairs_main_clone_failed.csv
#   repo_python/tmp/run-py-1i/python_control_pair_coverage_main_clone_usable.csv
#   repo_python/tmp/run-py-1i/python_treatment_lost_all_controls_main.csv
#   repo_python/tmp/run-py-1i/python_control_clone_usable_summary_main.csv
# 
# Usage:
#   bash run-py-1i-create-control-usable-repos.sh
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
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_control_usable_repos_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/create_control_usable_repos.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
SAMPLE_VARIANT="${SAMPLE_VARIANT:-main}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()
  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

CLONE_STATUS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1h/python_control_clone_status_${SAMPLE_VARIANT}_[0-9]*.csv"
PAIR_FILE_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_matched_control_pairs_${SAMPLE_VARIANT}_[0-9]*.csv"
CONTROL_REPOS_PATTERN="${OUTPUT_BASE_DIR}/run-py-1g/python_control_repos_to_clone_${SAMPLE_VARIANT}_[0-9]*.csv"

CLONE_STATUS_FILE="${CLONE_STATUS_FILE:-$(resolve_single_input "${CLONE_STATUS_PATTERN}" "clone-status file")}"
PAIR_FILE="${PAIR_FILE:-$(resolve_single_input "${PAIR_FILE_PATTERN}" "matched-pair file")}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-$(resolve_single_input "${CONTROL_REPOS_PATTERN}" "control-repository file")}"

USABLE_CONTROL_FILE="${USABLE_CONTROL_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_usable_repos_${SAMPLE_VARIANT}.csv}"
USABLE_PAIR_FILE="${USABLE_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_usable.csv}"

FAILED_CONTROL_FILE="${FAILED_CONTROL_FILE:-${TMP_DIR}/python_control_clone_failed_repos_${SAMPLE_VARIANT}.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_${SAMPLE_VARIANT}_clone_failed.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_${SAMPLE_VARIANT}_clone_usable.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${TMP_DIR}/python_treatment_lost_all_controls_${SAMPLE_VARIANT}.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_clone_usable_summary_${SAMPLE_VARIANT}.csv}"

USABLE_STATUSES="${USABLE_STATUSES:-cloned,skipped_existing,updated_existing}"
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: create clone-usable control repository sample" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                  ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                   ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Sample variant:               ${SAMPLE_VARIANT}" | tee -a "${LOG_FILE}"
echo "Main output dir:              ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:             ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Usable control file: ${USABLE_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Usable pair file:    ${USABLE_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Coverage file:       ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:        ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir:     ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:    ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:            ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8c-create-control-usable-repos.sh,
# but it does NOT call the existing JS/TS shell wrapper.


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/create_control_usable_repos.py --
###############################################################################

: <<'__MERGED_PYTHON_10__'
#!/usr/bin/env python3
"""
Create a usable matched-control sample after cloning control repositories.

This script:
1. Reads the clean control repository list.
2. Reads clone status output from run8b.
3. Reads treatment-control matched pair data.
4. Keeps only controls with usable clone status.
5. Removes pair rows whose control repository failed cloning.
6. Saves usable controls, failed controls, usable pairs, dropped pairs,
   treatment-level coverage, zero-control treatments, and a summary table.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_USABLE_STATUSES = ("cloned", "skipped_existing", "updated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create usable JS/TS matched control sample after clone filtering."
    )

    parser.add_argument("--clone-status-file", required=True)
    parser.add_argument("--pair-file", required=True)
    parser.add_argument("--control-repos-file", required=True)

    parser.add_argument("--usable-control-file", required=True)
    parser.add_argument("--failed-control-file", required=True)
    parser.add_argument("--usable-pair-file", required=True)
    parser.add_argument("--dropped-pair-file", required=True)
    parser.add_argument("--coverage-file", required=True)
    parser.add_argument("--zero-control-treatment-file", required=True)
    parser.add_argument("--summary-file", required=True)

    parser.add_argument(
        "--usable-statuses",
        default=",".join(DEFAULT_USABLE_STATUSES),
        help="Comma-separated clone statuses treated as usable.",
    )

    parser.add_argument(
        "--fail-if-zero-control",
        action="store_true",
        help="Exit with code 2 if any treatment repo loses all controls.",
    )

    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {label} missing columns: {sorted(missing)}")


def normalize_repo_name(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def read_csv(path: Path, label: str) -> pd.DataFrame:
    require_file(path, label)
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise SystemExit(f"ERROR: failed to read {label}: {path}\n{exc}") from exc


def prepare_clone_status(clone_df: pd.DataFrame) -> pd.DataFrame:
    require_columns(clone_df, ["repo_name", "status"], "clone status file")

    clone_df = clone_df.copy()
    clone_df["repo_name"] = normalize_repo_name(clone_df["repo_name"])
    clone_df["status"] = clone_df["status"].astype(str).str.strip()
    clone_df["status_norm"] = clone_df["status"].str.lower()

    # Keep the last record if a repository appears multiple times.
    clone_df = clone_df.drop_duplicates(subset=["repo_name"], keep="last")
    return clone_df


def prepare_control_repos(control_df: pd.DataFrame) -> pd.DataFrame:
    require_columns(control_df, ["repo_name"], "control repos file")

    control_df = control_df.copy()
    control_df["repo_name"] = normalize_repo_name(control_df["repo_name"])
    control_df = control_df[control_df["repo_name"].ne("")]
    control_df = control_df.drop_duplicates(subset=["repo_name"], keep="first")
    return control_df


def detect_pair_columns(pair_df: pd.DataFrame) -> tuple[str, str]:
    treatment_candidates = [
        "treatment_repo",
        "treated_repo",
        "treatment_repo_name",
        "repo_name",
    ]
    control_candidates = [
        "control_repo",
        "matched_control",
        "matched_control_repo",
        "control_repo_name",
    ]

    treatment_col = next((c for c in treatment_candidates if c in pair_df.columns), None)
    control_col = next((c for c in control_candidates if c in pair_df.columns), None)

    if treatment_col and control_col:
        return treatment_col, control_col

    wide_control_cols = [
        c for c in pair_df.columns
        if c.startswith("matched_control_")
    ]

    if treatment_col and wide_control_cols:
        # The caller will handle wide format separately.
        return treatment_col, "__wide_matched_controls__"

    raise SystemExit(
        "ERROR: could not detect treatment/control columns in pair file. "
        "Expected long format columns such as treatment_repo/control_repo, "
        "or wide format columns such as repo_name/matched_control_1."
    )


def prepare_pairs(pair_df: pd.DataFrame) -> pd.DataFrame:
    treatment_col, control_col = detect_pair_columns(pair_df)

    pair_df = pair_df.copy()

    if control_col == "__wide_matched_controls__":
        wide_control_cols = [
            c for c in pair_df.columns
            if c.startswith("matched_control_")
        ]
        id_cols = [c for c in pair_df.columns if c not in wide_control_cols]

        pair_df = pair_df.melt(
            id_vars=id_cols,
            value_vars=wide_control_cols,
            var_name="matched_control_slot",
            value_name="control_repo",
        )
        pair_df = pair_df.rename(columns={treatment_col: "treatment_repo"})
    else:
        pair_df = pair_df.rename(
            columns={
                treatment_col: "treatment_repo",
                control_col: "control_repo",
            }
        )

    pair_df["treatment_repo"] = normalize_repo_name(pair_df["treatment_repo"])
    pair_df["control_repo"] = normalize_repo_name(pair_df["control_repo"])

    pair_df = pair_df[
        pair_df["treatment_repo"].ne("")
        & pair_df["control_repo"].ne("")
        & pair_df["control_repo"].str.lower().ne("nan")
    ].copy()

    pair_df = pair_df.drop_duplicates(
        subset=["treatment_repo", "control_repo"],
        keep="first",
    )

    return pair_df


def create_outputs(
    clone_df: pd.DataFrame,
    controls_df: pd.DataFrame,
    pairs_df: pd.DataFrame,
    usable_statuses: set[str],
) -> dict[str, pd.DataFrame]:
    clone_cols = list(clone_df.columns)

    # Merge the intended control list with clone status.
    control_clone = controls_df.merge(
        clone_df,
        on="repo_name",
        how="left",
        suffixes=("", "_clone"),
    )

    control_clone["status_norm"] = control_clone["status_norm"].fillna(
        "missing_clone_status"
    )
    control_clone["status"] = control_clone["status"].fillna("missing_clone_status")

    usable_controls = control_clone[
        control_clone["status_norm"].isin(usable_statuses)
    ].copy()

    failed_controls = control_clone[
        ~control_clone["status_norm"].isin(usable_statuses)
    ].copy()

    usable_control_set = set(usable_controls["repo_name"])

    usable_pairs = pairs_df[pairs_df["control_repo"].isin(usable_control_set)].copy()
    dropped_pairs = pairs_df[~pairs_df["control_repo"].isin(usable_control_set)].copy()

    original_counts = (
        pairs_df.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_original_controls")
    )

    usable_counts = (
        usable_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_usable_controls")
    )

    coverage = original_counts.merge(usable_counts, on="treatment_repo", how="left")
    coverage["num_usable_controls"] = coverage["num_usable_controls"].fillna(0).astype(int)
    coverage["num_dropped_controls"] = (
        coverage["num_original_controls"] - coverage["num_usable_controls"]
    )

    coverage = coverage.sort_values(
        ["num_usable_controls", "num_dropped_controls", "treatment_repo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    zero_control_treatments = coverage[coverage["num_usable_controls"] == 0].copy()

    extra_clone_rows = clone_df[~clone_df["repo_name"].isin(set(controls_df["repo_name"]))]

    summary = pd.DataFrame(
        [
            {
                "metric": "clean_control_repos_before_clone_filter",
                "value": controls_df["repo_name"].nunique(),
            },
            {
                "metric": "clone_status_rows",
                "value": len(clone_df),
            },
            {
                "metric": "clone_status_unique_repos",
                "value": clone_df["repo_name"].nunique(),
            },
            {
                "metric": "extra_clone_status_repos_not_in_control_list",
                "value": extra_clone_rows["repo_name"].nunique(),
            },
            {
                "metric": "usable_control_repos",
                "value": usable_controls["repo_name"].nunique(),
            },
            {
                "metric": "failed_or_missing_control_repos",
                "value": failed_controls["repo_name"].nunique(),
            },
            {
                "metric": "matched_pair_rows_before_clone_filter",
                "value": len(pairs_df),
            },
            {
                "metric": "usable_matched_pair_rows",
                "value": len(usable_pairs),
            },
            {
                "metric": "dropped_pair_rows_due_to_failed_or_missing_clone",
                "value": len(dropped_pairs),
            },
            {
                "metric": "treatment_repos_before_clone_filter",
                "value": pairs_df["treatment_repo"].nunique(),
            },
            {
                "metric": "treatment_repos_with_usable_controls",
                "value": usable_pairs["treatment_repo"].nunique(),
            },
            {
                "metric": "treatment_repos_lost_all_controls",
                "value": len(zero_control_treatments),
            },
        ]
    )

    return {
        "usable_controls": usable_controls,
        "failed_controls": failed_controls,
        "usable_pairs": usable_pairs,
        "dropped_pairs": dropped_pairs,
        "coverage": coverage,
        "zero_control_treatments": zero_control_treatments,
        "summary": summary,
        "extra_clone_rows": extra_clone_rows,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], args: argparse.Namespace) -> None:
    path_map = {
        "usable_controls": Path(args.usable_control_file),
        "failed_controls": Path(args.failed_control_file),
        "usable_pairs": Path(args.usable_pair_file),
        "dropped_pairs": Path(args.dropped_pair_file),
        "coverage": Path(args.coverage_file),
        "zero_control_treatments": Path(args.zero_control_treatment_file),
        "summary": Path(args.summary_file),
    }

    for key, path in path_map.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        outputs[key].to_csv(path, index=False)


def print_report(outputs: dict[str, pd.DataFrame]) -> None:
    usable_controls = outputs["usable_controls"]
    failed_controls = outputs["failed_controls"]
    usable_pairs = outputs["usable_pairs"]
    dropped_pairs = outputs["dropped_pairs"]
    coverage = outputs["coverage"]
    zero_control_treatments = outputs["zero_control_treatments"]
    summary = outputs["summary"]
    extra_clone_rows = outputs["extra_clone_rows"]

    print("Summary:")
    print(summary.to_string(index=False))
    print()

    print("Control clone status counts after merging with intended control list:")
    print(
        pd.concat([usable_controls, failed_controls])["status"]
        .value_counts(dropna=False)
        .to_string()
    )
    print()

    print("Control-count distribution after clone filtering:")
    print(coverage["num_usable_controls"].value_counts().sort_index().to_string())
    print()

    if len(failed_controls) > 0:
        print("Failed or missing control repositories:")
        cols = ["repo_name", "status", "target_dir", "note"]
        cols = [c for c in cols if c in failed_controls.columns]
        print(failed_controls[cols].to_string(index=False))
        print()

    if len(zero_control_treatments) > 0:
        print("Treatment repositories that lost all controls:")
        print(zero_control_treatments.to_string(index=False))
        print()

    if len(extra_clone_rows) > 0:
        print("Extra clone-status rows not present in intended control list:")
        cols = ["repo_name", "status", "target_dir", "note"]
        cols = [c for c in cols if c in extra_clone_rows.columns]
        print(extra_clone_rows[cols].to_string(index=False))
        print()

    print("Usable matched pair rows:", len(usable_pairs))
    print("Dropped matched pair rows:", len(dropped_pairs))
    print("Usable control repos:", usable_controls["repo_name"].nunique())
    print("Failed or missing control repos:", failed_controls["repo_name"].nunique())


def main() -> int:
    args = parse_args()

    clone_status_path = Path(args.clone_status_file)
    pair_path = Path(args.pair_file)
    control_repos_path = Path(args.control_repos_file)

    usable_statuses = {
        status.strip().lower()
        for status in args.usable_statuses.split(",")
        if status.strip()
    }

    clone_df = prepare_clone_status(
        read_csv(clone_status_path, "clone status file")
    )
    controls_df = prepare_control_repos(
        read_csv(control_repos_path, "control repos file")
    )
    pairs_df = prepare_pairs(
        read_csv(pair_path, "matched pair file")
    )

    outputs = create_outputs(
        clone_df=clone_df,
        controls_df=controls_df,
        pairs_df=pairs_df,
        usable_statuses=usable_statuses,
    )

    save_outputs(outputs, args)
    print_report(outputs)

    zero_count = len(outputs["zero_control_treatments"])
    if args.fail_if_zero_control and zero_count > 0:
        print(f"ERROR: {zero_count} treatment repositories lost all controls.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_10__

###############################################################################
# -- SHELL SCRIPT: run-py-1j-analyze-control-repos.sh --
###############################################################################

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


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/analyze_repos_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_11__'
#!/usr/bin/env python3
"""
Extended repository analyzer for AI code generator adoption-date detection.

This wrapper imports scripts/analyze_repos.py and reuses its original logic:
  - find_cursor_commits()
  - count_cursor_commits_by_time()
  - get_commit_stats()
  - process_repository()

New logic added here:
  - CLI arguments for repos file, clone directory, output directory, aggregation
  - sample testing with --max-repos or --repos
  - ai_adoption_dates.csv generated from earliest Cursor-related commit per repo

The original script is not modified.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import multiprocessing
import random
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "analyze_repos.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original analyzer not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location("original_analyze_repos", ORIGINAL_SCRIPT)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)


def load_repos(
    repos_file: Path,
    repos_filter: Optional[list[str]],
    max_repos: Optional[int],
    random_sample: bool,
    seed: int,
) -> pd.DataFrame:
    """Load repo list and optionally filter/sample it."""
    if not repos_file.exists():
        raise FileNotFoundError(f"Repos file not found: {repos_file}")

    repos_df = pd.read_csv(repos_file)

    if "repo_name" not in repos_df.columns:
        raise ValueError(f"{repos_file} must contain a repo_name column")

    repos_df["repo_name"] = repos_df["repo_name"].astype(str).str.strip()
    repos_df = repos_df[repos_df["repo_name"] != ""].drop_duplicates("repo_name")

    if repos_filter:
        wanted = set(repos_filter)
        repos_df = repos_df[repos_df["repo_name"].isin(wanted)].copy()

    if max_repos is not None and max_repos > 0 and len(repos_df) > max_repos:
        if random_sample:
            repos_df = repos_df.sample(n=max_repos, random_state=seed)
        else:
            repos_df = repos_df.head(max_repos)

    return repos_df.reset_index(drop=True)


def compute_ai_adoption_dates(cursor_commits_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute earliest Cursor-related commit per repo.

    Input rows come from original find_cursor_commits(), with columns:
      repo_name, commit_hash, authored_at, committed_at, paths, message, ...

    Output:
      repo_name, adoption_tool, adoption_commit, adoption_date,
      adoption_month, evidence_paths, evidence_type, confidence
    """
    if cursor_commits_df.empty:
        return pd.DataFrame(
            columns=[
                "repo_name",
                "adoption_tool",
                "adoption_commit",
                "adoption_date",
                "adoption_month",
                "evidence_paths",
                "evidence_type",
                "confidence",
                "message",
            ]
        )

    df = cursor_commits_df.copy()

    # Prefer authored_at because it is closer to when the change was authored.
    # Fall back to committed_at if needed.
    if "authored_at" in df.columns:
        df["adoption_datetime"] = pd.to_datetime(df["authored_at"], errors="coerce")
    else:
        df["adoption_datetime"] = pd.NaT

    if "committed_at" in df.columns:
        committed_dt = pd.to_datetime(df["committed_at"], errors="coerce")
        df["adoption_datetime"] = df["adoption_datetime"].fillna(committed_dt)

    df = df.dropna(subset=["adoption_datetime"])

    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["repo_name", "adoption_datetime", "commit_hash"])
    first_df = df.groupby("repo_name", as_index=False).first()

    first_df["adoption_tool"] = "cursor"
    first_df["adoption_commit"] = first_df["commit_hash"]
    first_df["adoption_date"] = first_df["adoption_datetime"].dt.strftime("%Y-%m-%d")
    first_df["adoption_month"] = first_df["adoption_datetime"].dt.strftime("%Y-%m")
    first_df["evidence_paths"] = first_df.get("paths", "")
    first_df["evidence_type"] = "cursor_related_path"
    first_df["confidence"] = "high"

    cols = [
        "repo_name",
        "adoption_tool",
        "adoption_commit",
        "adoption_date",
        "adoption_month",
        "evidence_paths",
        "evidence_type",
        "confidence",
        "message",
    ]

    available_cols = [c for c in cols if c in first_df.columns]
    return first_df[available_cols].sort_values("repo_name").reset_index(drop=True)


# def process_one_repo(args_tuple):
#     """
#     Process one repo using original process_repository().
# 
#     We keep this wrapper so multiprocessing can call a top-level function
#     from this v2 file while the actual repository logic remains in the original.
#     """
#     idx, repo_dict, total_repos, aggregation = args_tuple
#     return orig.process_repository(idx, repo_dict, total_repos, aggregation)

def process_one_repo(args_tuple):
    idx, repo_dict, total_repos, aggregation = args_tuple
    repo_ts, contrib_ts, cursor_commits = orig.process_repository(
        idx, repo_dict, total_repos, aggregation
    )

    correct_repo_name = str(repo_dict["repo_name"]).strip()

    for rows in (repo_ts, contrib_ts, cursor_commits):
        for row in rows:
            row["repo_name"] = correct_repo_name

    return repo_ts, contrib_ts, cursor_commits



def run_analysis(
    repos_df: pd.DataFrame,
    clone_dir: Path,
    output_dir: Path,
    aggregation: str,
    num_processes: int,
    seed: int,
    shuffle: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Run original analyzer logic and return:
      ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Patch original module globals so original functions use our CLI settings.
    orig.CLONE_DIR = clone_dir
    orig.OUTPUT_DIR = output_dir
    orig.TIME_KEY = aggregation

    total_repos = len(repos_df)

    args_list = [
        (idx, repo.to_dict(), total_repos, aggregation)
        for idx, repo in repos_df.iterrows()
    ]

    if shuffle:
        random.seed(seed)
        random.shuffle(args_list)

    repo_ts = []
    contributor_ts = []
    all_cursor_commits = []

    if total_repos == 0:
        logging.warning("No repositories to process")
    elif num_processes <= 1:
        logging.info("Starting serial processing for %d repos", total_repos)
        for process_args in args_list:
            repo_name = process_args[1]["repo_name"]
            try:
                repo_time_series, repo_contributor_ts, repo_cursor_commits = process_one_repo(
                    process_args
                )
                repo_ts.extend(repo_time_series)
                contributor_ts.extend(repo_contributor_ts)
                all_cursor_commits.extend(repo_cursor_commits)
            except Exception as exc:
                logging.error("Error processing repository %s: %s", repo_name, exc)
    else:
        logging.info(
            "Starting multiprocessing pool with %d workers for %d repos",
            num_processes,
            total_repos,
        )
        with multiprocessing.Pool(processes=num_processes) as pool:
            async_results = [
                pool.apply_async(process_one_repo, (process_args,))
                for process_args in args_list
            ]

            for idx, async_result in enumerate(async_results):
                repo_name = args_list[idx][1]["repo_name"]
                try:
                    repo_time_series, repo_contributor_ts, repo_cursor_commits = (
                        async_result.get(timeout=orig.REPO_TIMEOUT_SECONDS)
                    )
                    repo_ts.extend(repo_time_series)
                    contributor_ts.extend(repo_contributor_ts)
                    all_cursor_commits.extend(repo_cursor_commits)
                except multiprocessing.TimeoutError:
                    logging.error(
                        "Repository %s processing timed out after %d seconds",
                        repo_name,
                        orig.REPO_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    logging.error("Error processing repository %s: %s", repo_name, exc)

    ts_repos_df = pd.DataFrame(repo_ts)
    ts_contributors_df = pd.DataFrame(contributor_ts)
    cursor_commits_df = pd.DataFrame(all_cursor_commits)
    adoption_dates_df = compute_ai_adoption_dates(cursor_commits_df)

    return ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df


def save_outputs(
    ts_repos_df: pd.DataFrame,
    ts_contributors_df: pd.DataFrame,
    cursor_commits_df: pd.DataFrame,
    adoption_dates_df: pd.DataFrame,
    output_dir: Path,
    aggregation: str,
) -> None:
    """Save outputs using original-style filenames plus ai_adoption_dates.csv."""
    output_suffix = "_monthly.csv" if aggregation == "month" else "_weekly.csv"

    ts_repos_file = output_dir / f"ts_repos{output_suffix}"
    ts_contributors_file = output_dir / f"ts_contributors{output_suffix}"
    cursor_commits_file = output_dir / "cursor_commits.csv"
    adoption_dates_file = output_dir / "ai_adoption_dates.csv"

    if not ts_repos_df.empty:
        sort_cols = ["repo_name", aggregation]
        sort_cols = [c for c in sort_cols if c in ts_repos_df.columns]
        if sort_cols:
            ts_repos_df = ts_repos_df.sort_values(sort_cols)
        ts_repos_df.to_csv(ts_repos_file, index=False)
        logging.info("Saved repo time series to %s", ts_repos_file)
    else:
        logging.warning("No repo time-series rows generated")

    if not ts_contributors_df.empty:
        sort_cols = ["repo_name", aggregation, "author"]
        sort_cols = [c for c in sort_cols if c in ts_contributors_df.columns]
        if sort_cols:
            ts_contributors_df = ts_contributors_df.sort_values(sort_cols)
        ts_contributors_df.to_csv(ts_contributors_file, index=False)
        logging.info("Saved contributor time series to %s", ts_contributors_file)
    else:
        logging.warning("No contributor time-series rows generated")

    if not cursor_commits_df.empty:
        cursor_commits_df = cursor_commits_df.sort_values(["repo_name", "authored_at"])
        cursor_commits_df.to_csv(cursor_commits_file, index=False)
        logging.info("Saved Cursor commit data to %s", cursor_commits_file)
    else:
        logging.warning("No Cursor-related commits found")

    adoption_dates_df.to_csv(adoption_dates_file, index=False)
    logging.info("Saved AI adoption dates to %s", adoption_dates_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze cloned repos and detect AI code generator adoption dates."
    )

    parser.add_argument(
        "--repos-file",
        type=Path,
        default=PROJECT_DIR / "data" / "repos.csv",
        help="CSV containing repo_name column. Default: data/repos.csv.",
    )

    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=PROJECT_DIR.parent / "CursorRepos",
        help="Directory containing cloned repos as owner_repo folders.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "data",
        help="Output directory. Default: data.",
    )

    parser.add_argument(
        "--aggregation",
        choices=["week", "month"],
        default="month",
        help="Aggregate by week or month. Default: month.",
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=None,
        help="Limit number of repos for sample testing.",
    )

    parser.add_argument(
        "--repos",
        nargs="*",
        default=None,
        help="Specific repo_name values to process, e.g., owner/repo owner2/repo2.",
    )

    parser.add_argument(
        "--num-processes",
        type=int,
        default=1,
        help="Number of worker processes. Default: 1 for safer smoke tests.",
    )

    parser.add_argument(
        "--random-sample",
        action="store_true",
        help="Use random sampling when --max-repos is set.",
    )

    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle processing order.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=114514,
        help="Random seed for sampling/shuffling.",
    )

    return parser.parse_args()


def main() -> None:
    multiprocessing.freeze_support()
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    repos_file = args.repos_file.expanduser().resolve()
    clone_dir = args.clone_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    logging.info("Original analyzer imported from: %s", ORIGINAL_SCRIPT)
    logging.info("Repos file: %s", repos_file)
    logging.info("Clone dir: %s", clone_dir)
    logging.info("Output dir: %s", output_dir)
    logging.info("Aggregation: %s", args.aggregation)

    if not clone_dir.exists():
        raise SystemExit(f"Clone directory does not exist: {clone_dir}")

    repos_df = load_repos(
        repos_file=repos_file,
        repos_filter=args.repos,
        max_repos=args.max_repos,
        random_sample=args.random_sample,
        seed=args.seed,
    )

    logging.info("Loaded %d repositories for processing", len(repos_df))

    ts_repos_df, ts_contributors_df, cursor_commits_df, adoption_dates_df = run_analysis(
        repos_df=repos_df,
        clone_dir=clone_dir,
        output_dir=output_dir,
        aggregation=args.aggregation,
        num_processes=args.num_processes,
        seed=args.seed,
        shuffle=args.shuffle,
    )

    save_outputs(
        ts_repos_df=ts_repos_df,
        ts_contributors_df=ts_contributors_df,
        cursor_commits_df=cursor_commits_df,
        adoption_dates_df=adoption_dates_df,
        output_dir=output_dir,
        aggregation=args.aggregation,
    )

    logging.info("Finished analyze_repos_v2")
    logging.info("Repos with Cursor adoption evidence: %d", len(adoption_dates_df))


if __name__ == "__main__":
    main()

__MERGED_PYTHON_11__

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/check_cache_control_repos.py --
###############################################################################

: <<'__MERGED_PYTHON_12__'
#!/usr/bin/env python3
"""Check whether run8d outputs already cover the requested repositories.

This script is intentionally small and shell-friendly: it writes KEY=VALUE lines
on stdout so run8d-analyze-control-repos.sh can tee the report to logs and grep
CACHE_STATUS from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def clean_repo_series(series: pd.Series) -> pd.Series:
    """Normalize repository names and remove empty/nan-like values."""
    out = series.astype("string").str.strip()
    out = out.mask(out.isna() | out.eq("") | out.str.lower().eq("nan"))
    return out


def usage() -> str:
    return (
        "Usage: check_run8d_cache.py "
        "<repos_file> <repo_ts_file> <contrib_ts_file> "
        "<cursor_commits_file> <adoption_file> <manifest_file> "
        "<missing_repos_file>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 8:
        print("CACHE_STATUS=error")
        print("ERROR=bad_arg_count")
        print(usage(), file=sys.stderr)
        return 2

    repos_file = Path(argv[1])
    repo_ts_file = Path(argv[2])
    contrib_ts_file = Path(argv[3])
    cursor_commits_file = Path(argv[4])
    adoption_file = Path(argv[5])
    manifest_file = Path(argv[6])
    missing_repos_file = Path(argv[7])

    required_outputs = [
        repo_ts_file,
        contrib_ts_file,
        cursor_commits_file,
        adoption_file,
    ]

    repos = pd.read_csv(repos_file)
    if "repo_name" not in repos.columns:
        print("CACHE_STATUS=error")
        print("ERROR=repo_name_missing")
        return 1


    repos["repo_name"] = clean_repo_series(repos["repo_name"])
    repos = repos[repos["repo_name"].notna()].drop_duplicates("repo_name")
    requested = set(repos["repo_name"])

    missing_outputs = [str(p) for p in required_outputs if not p.exists()]
    if missing_outputs:
        missing_repos_file.parent.mkdir(parents=True, exist_ok=True)
        repos.to_csv(missing_repos_file, index=False)
        print("CACHE_STATUS=run_full")
        print("CACHE_REASON=missing_required_outputs")
        print("MISSING_OUTPUTS=" + ";".join(missing_outputs))
        print(f"REQUESTED_REPOS={len(requested)}")
        print(f"MISSING_REPOS={len(requested)}")
        print(f"MISSING_REPOS_FILE={missing_repos_file}")
        return 0

    done: set[str] = set()

    # Prefer explicit manifest if it exists.
    if manifest_file.exists():
        try:
            manifest = pd.read_csv(manifest_file)
            if "repo_name" in manifest.columns:
                manifest["repo_name"] = clean_repo_series(manifest["repo_name"])
                done = set(manifest["repo_name"].dropna())

        except Exception:
            done = set()

    # Fallback: infer analyzed repos from ts_repos_<aggregation>ly.csv.
    if not done:
        try:
            ts = pd.read_csv(repo_ts_file, usecols=lambda c: c == "repo_name")
            ts["repo_name"] = clean_repo_series(ts["repo_name"])
            done = set(ts["repo_name"].dropna())

        except Exception:
            done = set()

    missing = sorted(requested - done)
    missing_df = repos[repos["repo_name"].isin(missing)].copy()
    missing_repos_file.parent.mkdir(parents=True, exist_ok=True)
    missing_df.to_csv(missing_repos_file, index=False)

    print(f"REQUESTED_REPOS={len(requested)}")
    print(f"ANALYZED_REPOS_IN_CACHE={len(done)}")
    print(f"MISSING_REPOS={len(missing)}")
    print(f"MISSING_REPOS_FILE={missing_repos_file}")

    if len(missing) == 0:
        print("CACHE_STATUS=complete")
        print("CACHE_REASON=all_requested_repos_already_analyzed")
    else:
        print("CACHE_STATUS=partial")
        print("CACHE_REASON=some_requested_repos_missing_from_existing_outputs")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

__MERGED_PYTHON_12__

###############################################################################
# -- SHELL SCRIPT: run-py-1k-filter-local-cursor-controls.sh --
###############################################################################

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
# Inputs:
#   repo_python/run-py-1i/python_control_clone_usable_repos_main.csv
#   repo_python/run-py-1i/python_matched_control_pairs_main_clone_usable.csv
#   repo_python/run-py-1j/ai_adoption_dates.csv
#   repo_python/run-py-1j/ts_repos_monthly.csv
#   repo_python/run-py-1j/ts_contributors_monthly.csv
#
# Main outputs:
#   repo_python/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv
#   repo_python/run-py-1k/python_matched_control_pairs_main_final_clean.csv
#   repo_python/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv
#   repo_python/run-py-1k/ts_repos_monthly_final_clean.csv
#   repo_python/run-py-1k/ts_contributors_monthly_final_clean.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-1k/python_control_local_cursor_evidence_in_window.csv
#   repo_python/tmp/run-py-1k/python_control_local_cursor_evidence_post_window.csv
#   repo_python/tmp/run-py-1k/python_matched_control_pairs_main_local_cursor_dropped.csv
#   repo_python/tmp/run-py-1k/python_control_pair_coverage_main_final_clean.csv
#   repo_python/tmp/run-py-1k/python_treatment_lost_all_controls_main_final_clean.csv
#   repo_python/tmp/run-py-1k/python_control_local_cursor_filter_summary_main.csv
#   repo_python/tmp/run-py-1k/python_control_pair_coverage_main_final_clean_1to3_only.csv
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
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_filter_local_cursor_controls_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/filter_controls_by_local_cursor_evidence.py}"

ANALYSIS_END="${ANALYSIS_END:-2025-08}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CONTROL_ANALYSIS_DIR="${CONTROL_ANALYSIS_DIR:-${OUTPUT_BASE_DIR}/run-py-1j}"
CONTROL_FILE="${CONTROL_FILE:-${OUTPUT_BASE_DIR}/run-py-1i/python_control_clone_usable_repos_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_BASE_DIR}/run-py-1i/python_matched_control_pairs_main_clone_usable.csv}"
ADOPTION_FILE="${ADOPTION_FILE:-${CONTROL_ANALYSIS_DIR}/ai_adoption_dates.csv}"

CONTROL_TS_REPOS_FILE="${CONTROL_TS_REPOS_FILE:-${CONTROL_ANALYSIS_DIR}/ts_repos_monthly.csv}"
CONTROL_TS_CONTRIBUTORS_FILE="${CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_ANALYSIS_DIR}/ts_contributors_monthly.csv}"

IN_WINDOW_EVIDENCE_FILE="${IN_WINDOW_EVIDENCE_FILE:-${TMP_DIR}/python_control_local_cursor_evidence_in_window.csv}"
POST_WINDOW_EVIDENCE_FILE="${POST_WINDOW_EVIDENCE_FILE:-${TMP_DIR}/python_control_local_cursor_evidence_post_window.csv}"

FINAL_CONTROL_FILE="${FINAL_CONTROL_FILE:-${MAIN_OUTPUT_DIR}/python_control_clone_usable_repos_main_final_clean.csv}"
FINAL_PAIR_FILE="${FINAL_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_main_final_clean.csv}"

DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${TMP_DIR}/python_matched_control_pairs_main_local_cursor_dropped.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_main_final_clean.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${TMP_DIR}/python_treatment_lost_all_controls_main_final_clean.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${TMP_DIR}/python_control_local_cursor_filter_summary_main.csv}"

STRICT_1TO3_PAIR_FILE="${STRICT_1TO3_PAIR_FILE:-${MAIN_OUTPUT_DIR}/python_matched_control_pairs_main_final_clean_1to3_only.csv}"
STRICT_1TO3_COVERAGE_FILE="${STRICT_1TO3_COVERAGE_FILE:-${TMP_DIR}/python_control_pair_coverage_main_final_clean_1to3_only.csv}"

FINAL_CONTROL_TS_REPOS_FILE="${FINAL_CONTROL_TS_REPOS_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_final_clean.csv}"
FINAL_CONTROL_TS_CONTRIBUTORS_FILE="${FINAL_CONTROL_TS_CONTRIBUTORS_FILE:-${MAIN_OUTPUT_DIR}/ts_contributors_monthly_final_clean.csv}"
 
FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"
 
mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: filter controls with local Cursor evidence" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                       ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                        ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Python script:                     ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Analysis end:                      ${ANALYSIS_END}" | tee -a "${LOG_FILE}"
echo "Main output dir:                   ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir:                  ${TMP_DIR}" | tee -a "${LOG_FILE}"
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
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Final control file: ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file: ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file: ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Main output dir: ${MAIN_OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "Extra output dir: ${TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
# 
# This wrapper is adapted from the logic of run8d2-filter-local-cursor-controls.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/filter_controls_by_local_cursor_evidence.py --
###############################################################################

: <<'__MERGED_PYTHON_13__'
#!/usr/bin/env python3
"""
Filter matched control repositories using local Cursor evidence detected by run8d.

This script:
1. Reads local Cursor adoption evidence from control git-history analysis.
2. Splits evidence into in-window and post-window evidence.
3. Removes controls with Cursor evidence within the analysis window.
4. Keeps controls with Cursor evidence only after the analysis window as diagnostics.
5. Recomputes treatment-control coverage.
6. Optionally filters control monthly time-series files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter controls with local Cursor evidence inside the analysis window."
    )

    parser.add_argument("--analysis-end", default="2025-08")

    parser.add_argument("--control-file", required=True)
    parser.add_argument("--pair-file", required=True)
    parser.add_argument("--adoption-file", required=True)

    parser.add_argument("--control-ts-repos-file", default=None)
    parser.add_argument("--control-ts-contributors-file", default=None)

    parser.add_argument("--in-window-evidence-file", required=True)
    parser.add_argument("--post-window-evidence-file", required=True)
    parser.add_argument("--final-control-file", required=True)
    parser.add_argument("--final-pair-file", required=True)
    parser.add_argument("--dropped-pair-file", required=True)
    parser.add_argument("--coverage-file", required=True)
    parser.add_argument("--zero-control-treatment-file", required=True)
    parser.add_argument("--summary-file", required=True)

    parser.add_argument(
        "--strict-1to3-pair-file",
        default=None,
        help="Optional output path for final-clean pairs that retain exactly three controls.",
    )
    parser.add_argument(
        "--strict-1to3-coverage-file",
        default=None,
        help="Optional output path for final-clean coverage rows that retain exactly three controls.",
    )

    parser.add_argument("--final-control-ts-repos-file", default=None)
    parser.add_argument("--final-control-ts-contributors-file", default=None)

    parser.add_argument(
        "--fail-if-zero-control",
        action="store_true",
        help="Exit with code 2 if any treatment repository loses all controls.",
    )

    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {label} missing columns: {sorted(missing)}")


def normalize_repo(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def read_adoption_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "repo_name",
                "adoption_month",
                "adoption_date",
                "evidence_paths",
                "confidence",
            ]
        )

    df = pd.read_csv(path)

    if df.empty:
        return df

    require_columns(df, {"repo_name", "adoption_month"}, "local Cursor adoption file")

    df = df.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["adoption_month"] = df["adoption_month"].astype(str).str.strip()

    return df[df["repo_name"].ne("")].copy()


def build_coverage(pairs: pd.DataFrame, final_pairs: pd.DataFrame) -> pd.DataFrame:
    original_counts = (
        pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_controls_before_local_cursor_filter")
    )

    final_counts = (
        final_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_final_controls")
    )

    coverage = original_counts.merge(final_counts, on="treatment_repo", how="left")
    coverage["num_final_controls"] = coverage["num_final_controls"].fillna(0).astype(int)
    coverage["num_dropped_controls_local_cursor"] = (
        coverage["num_controls_before_local_cursor_filter"]
        - coverage["num_final_controls"]
    )

    coverage = coverage.sort_values(
        ["num_final_controls", "num_dropped_controls_local_cursor", "treatment_repo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    return coverage


def maybe_filter_time_series(
    input_path_text: str | None,
    output_path_text: str | None,
    removed_controls: set[str],
    label: str,
) -> tuple[int, int]:
    if not input_path_text or not output_path_text:
        return 0, 0

    input_path = Path(input_path_text)
    output_path = Path(output_path_text)

    if not input_path.exists():
        print(f"WARNING: {label} input file not found: {input_path}")
        return 0, 0

    df = pd.read_csv(input_path)

    if "repo_name" not in df.columns:
        print(f"WARNING: {label} has no repo_name column: {input_path}")
        save_csv(df, output_path)
        return len(df), len(df)

    df["repo_name"] = normalize_repo(df["repo_name"])
    filtered = df[~df["repo_name"].isin(removed_controls)].copy()
    save_csv(filtered, output_path)

    return len(df), len(filtered)


def main() -> int:
    args = parse_args()

    control_path = Path(args.control_file)
    pair_path = Path(args.pair_file)
    adoption_path = Path(args.adoption_file)

    require_file(control_path, "control file")
    require_file(pair_path, "pair file")

    controls = pd.read_csv(control_path)
    pairs = pd.read_csv(pair_path)
    adoptions = read_adoption_file(adoption_path)

    require_columns(controls, {"repo_name"}, "control file")
    require_columns(pairs, {"treatment_repo", "control_repo"}, "pair file")

    controls = controls.copy()
    pairs = pairs.copy()

    controls["repo_name"] = normalize_repo(controls["repo_name"])
    pairs["treatment_repo"] = normalize_repo(pairs["treatment_repo"])
    pairs["control_repo"] = normalize_repo(pairs["control_repo"])

    if adoptions.empty:
        in_window = adoptions.copy()
        post_window = adoptions.copy()
    else:
        adoptions["cursor_evidence_in_analysis_window"] = (
            adoptions["adoption_month"] <= args.analysis_end
        )
        in_window = adoptions[adoptions["cursor_evidence_in_analysis_window"]].copy()
        post_window = adoptions[~adoptions["cursor_evidence_in_analysis_window"]].copy()

    remove_controls = set(in_window["repo_name"].astype(str).str.strip())

    final_controls = controls[~controls["repo_name"].isin(remove_controls)].copy()
    dropped_pairs = pairs[pairs["control_repo"].isin(remove_controls)].copy()
    final_pairs = pairs[~pairs["control_repo"].isin(remove_controls)].copy()

    coverage = build_coverage(pairs, final_pairs)
    zero_control_treatments = coverage[coverage["num_final_controls"] == 0].copy()

    strict_1to3_treatments = set(
        coverage.loc[coverage["num_final_controls"] == 3, "treatment_repo"]
    )
    strict_1to3_pairs = final_pairs[
        final_pairs["treatment_repo"].isin(strict_1to3_treatments)
    ].copy()
    strict_1to3_coverage = coverage[
        coverage["treatment_repo"].isin(strict_1to3_treatments)
    ].copy()

    ts_repos_before, ts_repos_after = maybe_filter_time_series(
        args.control_ts_repos_file,
        args.final_control_ts_repos_file,
        remove_controls,
        "control repo time series",
    )

    ts_contrib_before, ts_contrib_after = maybe_filter_time_series(
        args.control_ts_contributors_file,
        args.final_control_ts_contributors_file,
        remove_controls,
        "control contributor time series",
    )

    summary = pd.DataFrame(
        [
            {"metric": "analysis_end", "value": args.analysis_end},
            {"metric": "controls_before_local_cursor_filter", "value": controls["repo_name"].nunique()},
            {"metric": "local_cursor_evidence_controls_total", "value": adoptions["repo_name"].nunique()},
            {"metric": "local_cursor_evidence_controls_in_window_removed", "value": len(remove_controls)},
            {"metric": "local_cursor_evidence_controls_post_window_kept", "value": post_window["repo_name"].nunique()},
            {"metric": "final_controls", "value": final_controls["repo_name"].nunique()},
            {"metric": "pairs_before_local_cursor_filter", "value": len(pairs)},
            {"metric": "final_pairs", "value": len(final_pairs)},
            {"metric": "strict_1to3_treatment_repos", "value": len(strict_1to3_treatments)},
            {"metric": "strict_1to3_pair_rows", "value": len(strict_1to3_pairs)},
            {"metric": "dropped_pairs_local_cursor_in_window", "value": len(dropped_pairs)},
            {"metric": "treatment_repos_before_local_cursor_filter", "value": pairs["treatment_repo"].nunique()},
            {"metric": "treatment_repos_with_final_controls", "value": final_pairs["treatment_repo"].nunique()},
            {"metric": "treatment_repos_lost_all_controls", "value": len(zero_control_treatments)},
            {"metric": "control_ts_repos_rows_before_filter", "value": ts_repos_before},
            {"metric": "control_ts_repos_rows_after_filter", "value": ts_repos_after},
            {"metric": "control_ts_contributors_rows_before_filter", "value": ts_contrib_before},
            {"metric": "control_ts_contributors_rows_after_filter", "value": ts_contrib_after},
        ]
    )

    save_csv(in_window, Path(args.in_window_evidence_file))
    save_csv(post_window, Path(args.post_window_evidence_file))
    save_csv(final_controls, Path(args.final_control_file))
    save_csv(final_pairs, Path(args.final_pair_file))
    save_csv(dropped_pairs, Path(args.dropped_pair_file))
    save_csv(coverage, Path(args.coverage_file))
    save_csv(zero_control_treatments, Path(args.zero_control_treatment_file))
    save_csv(summary, Path(args.summary_file))

    if args.strict_1to3_pair_file:
        save_csv(strict_1to3_pairs, Path(args.strict_1to3_pair_file))
    if args.strict_1to3_coverage_file:
        save_csv(strict_1to3_coverage, Path(args.strict_1to3_coverage_file))

    print("Summary:")
    print(summary.to_string(index=False))
    print()

    print("In-window local Cursor controls removed:")
    if in_window.empty:
        print("(none)")
    else:
        cols = ["repo_name", "adoption_month", "adoption_date", "evidence_paths", "confidence"]
        cols = [c for c in cols if c in in_window.columns]
        print(in_window[cols].to_string(index=False))
    print()

    print("Post-window local Cursor controls kept as diagnostics:")
    if post_window.empty:
        print("(none)")
    else:
        cols = ["repo_name", "adoption_month", "adoption_date", "evidence_paths", "confidence"]
        cols = [c for c in cols if c in post_window.columns]
        print(post_window[cols].to_string(index=False))
    print()

    print("Final control-count distribution:")
    print(coverage["num_final_controls"].value_counts().sort_index().to_string())
    print()

    print("Strict 1:3 robustness subset:")
    print("Strict 1:3 treatment repos:", len(strict_1to3_treatments))
    print("Strict 1:3 pair rows:", len(strict_1to3_pairs))
    if not strict_1to3_coverage.empty:
        print(strict_1to3_coverage["num_final_controls"].value_counts().sort_index().to_string())
    print()

    if len(zero_control_treatments) > 0:
        print("Treatment repositories that lost all controls:")
        print(zero_control_treatments.to_string(index=False))
        print()

    print("Saved final control file:", args.final_control_file)
    print("Saved final pair file:", args.final_pair_file)
    print("Saved final coverage file:", args.coverage_file)
    if args.strict_1to3_pair_file:
        print("Saved strict 1:3 pair file:", args.strict_1to3_pair_file)
    if args.strict_1to3_coverage_file:
        print("Saved strict 1:3 coverage file:", args.strict_1to3_coverage_file)
    print("Saved summary file:", args.summary_file)

    if args.fail_if_zero_control and len(zero_control_treatments) > 0:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_13__

###############################################################################
# -- SHELL SCRIPT: run-py-1l-build-matched-panel.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-1l: Build and summarize final matched Python DiD panels
# ============================================================
#
# Purpose:
#   1. Build flexible and strict matched Python DiD panels.
#   2. Build window-driven versions of both panels.
#   3. Summarize the panels and compare them with paper counts.
#
# Reused Python scripts:
#   proc_scripts/prepare_panel_event_v2.py
#   proc_scripts/summarize_matched_panels.py
#
# Main outputs:
#   repo_python/run-py-1l/panel_event_matched_flexible.csv
#   repo_python/run-py-1l/panel_event_matched_flexible_window_driven.csv
#   repo_python/run-py-1l/panel_event_matched_strict.csv
#   repo_python/run-py-1l/panel_event_matched_strict_window_driven.csv
#
# Extra QC outputs:
#   repo_python/tmp/run-py-1l/qc/panel_qc_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_by_source.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_paper_comparison.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_attrition_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_dropped_by_strict.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_notes.md
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are kept as provenance, not as pseudo-event assignments.
#   - Normalized time-series inputs are removed after the run by default.
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
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_build_and_summarize_matched_panels_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"
SUMMARY_SCRIPT="${SUMMARY_SCRIPT:-proc_scripts/summarize_matched_panels.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
QC_TMP_DIR="${QC_TMP_DIR:-${TMP_DIR}/qc}"
DID_DIR="${DID_DIR:-${MAIN_OUTPUT_DIR}}"
NORMALIZED_DIR="${NORMALIZED_DIR:-${TMP_DIR}/normalized_inputs_${RUN_TS}}"
KEEP_NORMALIZED_INPUTS="${KEEP_NORMALIZED_INPUTS:-false}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()

  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

TREATMENT_META_PATTERN="${OUTPUT_BASE_DIR}/run-py-1f/treatment_python_sample_main_[0-9]*.csv"
TREATMENT_MISSING_MATCHING_PATTERN="${OUTPUT_BASE_DIR}/tmp/run-py-1g/python_treatment_missing_matching_main_[0-9]*.csv"

TREATMENT_META="${TREATMENT_META:-$(resolve_single_input "${TREATMENT_META_PATTERN}" "treatment metadata file")}"
TREATMENT_MISSING_MATCHING="${TREATMENT_MISSING_MATCHING:-$(resolve_single_input "${TREATMENT_MISSING_MATCHING_PATTERN}" "missing-matching file")}"

MAIN_PAIRS_FILE="${MAIN_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean.csv}"
STRICT_PAIRS_FILE="${STRICT_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv}"

TREATMENT_TS_RAW="${TREATMENT_TS_RAW:-${OUTPUT_BASE_DIR}/treatment_python_did/ts_repos_monthly.csv}"
CONTROL_TS_RAW="${CONTROL_TS_RAW:-${OUTPUT_BASE_DIR}/run-py-1k/ts_repos_monthly_final_clean.csv}"

TREATMENT_TS="${TREATMENT_TS:-${NORMALIZED_DIR}/treatment_ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-${NORMALIZED_DIR}/control_ts_repos_monthly.csv}"

MAIN_OUTPUT_FILE="${MAIN_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
MAIN_BALANCED_OUTPUT_FILE="${MAIN_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_OUTPUT_FILE="${STRICT_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
STRICT_BALANCED_OUTPUT_FILE="${STRICT_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

OUTPUT_SUMMARY="${OUTPUT_SUMMARY:-${QC_TMP_DIR}/panel_qc_summary.csv}"
OUTPUT_BY_SOURCE="${OUTPUT_BY_SOURCE:-${QC_TMP_DIR}/panel_qc_by_source.csv}"
OUTPUT_PAPER_COMPARISON="${OUTPUT_PAPER_COMPARISON:-${QC_TMP_DIR}/panel_qc_paper_comparison.csv}"
OUTPUT_ATTRITION="${OUTPUT_ATTRITION:-${QC_TMP_DIR}/panel_qc_attrition_summary.csv}"
OUTPUT_DROPPED_BY_STRICT="${OUTPUT_DROPPED_BY_STRICT:-${QC_TMP_DIR}/panel_qc_dropped_by_strict.csv}"
OUTPUT_NOTES="${OUTPUT_NOTES:-${QC_TMP_DIR}/panel_qc_notes.md}"

FINAL_COVERAGE="${FINAL_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean.csv}"
STRICT_COVERAGE="${STRICT_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean_1to3_only.csv}"
FINAL_CONTROLS="${FINAL_CONTROLS:-${OUTPUT_BASE_DIR}/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv}"

PAPER_TREATMENT_REPOS="${PAPER_TREATMENT_REPOS:-121}"
PAPER_CONTROL_REPOS="${PAPER_CONTROL_REPOS:-127}"
PAPER_TOTAL_OBSERVATIONS="${PAPER_TOTAL_OBSERVATIONS:-2461}"
PAPER_POST_TREATMENT_OBSERVATIONS="${PAPER_POST_TREATMENT_OBSERVATIONS:-582}"

cleanup_normalized_inputs() {
  if [[ "${KEEP_NORMALIZED_INPUTS}" != "true" ]]; then
    rm -rf "${NORMALIZED_DIR}"
  fi
}
trap cleanup_normalized_inputs EXIT

mkdir -p "${LOG_DIR}" "${DID_DIR}" "${QC_TMP_DIR}" "${NORMALIZED_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: build and summarize final matched Python DiD panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                       ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                        ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Panel script:                      ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Summary script:                    ${SUMMARY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Main output dir:                   ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Extra QC dir:                      ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:                ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Treatment missing matching:        ${TREATMENT_MISSING_MATCHING}" | tee -a "${LOG_FILE}"
echo "Main pairs file:                   ${MAIN_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pairs file:             ${STRICT_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series raw:         ${TREATMENT_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Control time series raw:           ${CONTROL_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Flexible panel:                    ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:                      ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC output dir:                     ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "QC summary:                        ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison:                  ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:                          ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Keep normalized inputs:            ${KEEP_NORMALIZED_INPUTS}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${SUMMARY_SCRIPT}" \
  "${TREATMENT_META}" \
  "${TREATMENT_MISSING_MATCHING}" \
  "${MAIN_PAIRS_FILE}" \
  "${STRICT_PAIRS_FILE}" \
  "${TREATMENT_TS_RAW}" \
  "${CONTROL_TS_RAW}" \
  "${FINAL_COVERAGE}" \
  "${STRICT_COVERAGE}" \
  "${FINAL_CONTROLS}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Step 0: Compile Python scripts" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}" "${SUMMARY_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 1: Normalize time-series input columns" | tee -a "${LOG_FILE}"
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

echo | tee -a "${LOG_FILE}"
echo "** Step 2: Check input schemas" | tee -a "${LOG_FILE}"
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
  echo "** Step 3: Build ${label} panel" | tee -a "${LOG_FILE}"
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
echo "** Step 4: Summarize matched panels" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

SUMMARY_CMD=(
  python "${SUMMARY_SCRIPT}"
  --flexible-panel "${MAIN_OUTPUT_FILE}"
  --strict-panel "${STRICT_OUTPUT_FILE}"
  --flexible-window-driven-panel "${MAIN_BALANCED_OUTPUT_FILE}"
  --strict-window-driven-panel "${STRICT_BALANCED_OUTPUT_FILE}"
  --output-summary "${OUTPUT_SUMMARY}"
  --output-by-source "${OUTPUT_BY_SOURCE}"
  --output-paper-comparison "${OUTPUT_PAPER_COMPARISON}"
  --output-attrition "${OUTPUT_ATTRITION}"
  --output-dropped-by-strict "${OUTPUT_DROPPED_BY_STRICT}"
  --output-notes "${OUTPUT_NOTES}"
  --treatment-sample "${TREATMENT_META}"
  --treatment-missing-matching "${TREATMENT_MISSING_MATCHING}"
  --final-coverage "${FINAL_COVERAGE}"
  --strict-coverage "${STRICT_COVERAGE}"
  --final-controls "${FINAL_CONTROLS}"
  --paper-treatment-repos "${PAPER_TREATMENT_REPOS}"
  --paper-control-repos "${PAPER_CONTROL_REPOS}"
  --paper-total-observations "${PAPER_TOTAL_OBSERVATIONS}"
  --paper-post-treatment-observations "${PAPER_POST_TREATMENT_OBSERVATIONS}"
)

echo "${SUMMARY_CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"
"${SUMMARY_CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 5: Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${MAIN_OUTPUT_FILE}" \
  "${MAIN_BALANCED_OUTPUT_FILE}" \
  "${STRICT_OUTPUT_FILE}" \
  "${STRICT_BALANCED_OUTPUT_FILE}" \
  "${OUTPUT_SUMMARY}" \
  "${OUTPUT_PAPER_COMPARISON}" \
  "${OUTPUT_NOTES}" \
  "${OUTPUT_BY_SOURCE}" \
  "${OUTPUT_ATTRITION}" \
  "${OUTPUT_DROPPED_BY_STRICT}"
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
echo "Flexible panel:   ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:     ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC summary:       ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison: ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:         ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Main output dir:  ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "QC output dir:    ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:         ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e-build-jsts-matched-panel.sh,
# and run8e2-summarize-jsts-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/prepare_panel_event_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_14__'
#!/usr/bin/env python3
"""
Build a paper-faithful matched DiD event panel (treatment + PSM-selected
never-treated controls), borrowing event-time logic from
scripts/prepare_panel_event.py WITHOUT modifying or running the original.

Produces TWO outputs in one run:
  --output          : unbalanced panel. Only repo-months present in the
                      git-history time series are kept (months with no commit
                      have no row). Controls whose activity is entirely outside
                      the analysis window disappear after the date filter.
  --balanced-output : window-completed panel. For each repo, missing months in
                      [max(analysis_start, first_commit_month) .. analysis_end]
                      are zero-filled (commits/lines_*/contributors=0,
                      cursor=False). This keeps zero-commit months (paper main
                      setting; the ">0 commits" filter is a separate robustness
                      subset), fills the 28/38 month gaps, restores controls that
                      only had pre-window commits, and zero-fills empty treated
                      pre-adoption windows. Repo-months before a repo's first
                      commit are NOT fabricated.

Key design (both outputs):
  - event_month from metadata (matched_controls_v2_treatment_only.csv), NOT
    re-detected from cursor==True.
  - Treatment post_event is ABSORBING: post_event = (month >= event_month);
    the original cursor-abandonment reset is NOT applied.
  - Controls are PSM-selected never-treated units: no pseudo-event, each unique
    control once; PSM pairing kept only as provenance.
  - ever_treated / is_treatment (absorbing) / is_treatment_dynamic (cursor) /
    cursor are separate columns, supporting both absorbing (Callaway/Borusyak)
    and switching (TWFE) specifications.

NOTE: activity metrics only (commits, lines_added, ...). SonarQube quality
outcomes are merged in a later step.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MONTH_LEAD_AND_LAG = 6
START_DATE = "2024-01-01"
END_DATE = "2025-08-31"

TS_COLUMNS_EXPECTED = [
    "repo_name",
    "month",
    "latest_commit",
    "cursor",
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
]

ACTIVITY_FILL_ZERO = ["commits", "lines_added", "lines_removed", "contributors", "latest_commit"]


def coerce_cursor(series: pd.Series) -> pd.Series:
    """Return a clean boolean cursor series (handles bool, 'True'/'False', NaN).

    Avoids ``.fillna(False)`` on an object-dtype array: after a left-merge the
    cursor column is object (python bools + NaN for filled rows), and fillna on
    object dtype emits pandas' downcasting FutureWarning (a hard error under
    PYTHONWARNINGS=error::FutureWarning). Mapping each value to a python bool
    yields no NaN, so astype(bool) is a clean, warning-free cast.
    """
    if series.dtype == bool:
        return series  # numpy bool cannot hold NaN; nothing to fill
    truthy = {"true", "1"}
    return series.map(lambda v: str(v).strip().lower() in truthy).astype(bool)


def month_diff(month_str: str, event_str: str) -> int:
    """Whole-month difference (month - event), both 'YYYY-MM'."""
    m = pd.to_datetime(month_str + "-01")
    e = pd.to_datetime(event_str + "-01")
    return (m.year - e.year) * 12 + (m.month - e.month)


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' months from start to end."""
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    out: list[str] = []
    p = s
    while p <= e:
        out.append(str(p))
        p += 1
    return out


def complete_repo_months(df: pd.DataFrame, analysis_start: str, analysis_end: str) -> pd.DataFrame:
    """
    Zero-fill missing repo-months within the analysis window.

    For each repo: fill [max(analysis_start, first_observed_month) .. analysis_end].
    Months before the repo's first observed commit are NOT created (no fake
    pre-existence). Months beyond analysis_end are dropped. Activity columns ->
    0, cursor -> False; the merge grid also excludes pre-window rows.
    """
    out = []
    for repo, g in df.groupby("repo_name"):
        source = g["dataset_source"].iloc[0] if "dataset_source" in g.columns else None
        first_observed = g["month"].min()  # zero-padded 'YYYY-MM' -> lexicographic == chronological
        start = max(analysis_start, first_observed)
        grid = pd.DataFrame({"month": month_range(start, analysis_end)})
        merged = grid.merge(
            g.drop(columns=[c for c in ("repo_name", "dataset_source") if c in g.columns]),
            on="month",
            how="left",
        )
        merged.insert(0, "repo_name", repo)
        if source is not None:
            merged["dataset_source"] = source
        for c in ACTIVITY_FILL_ZERO:
            if c in merged.columns:
                merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)
        if "cursor" in merged.columns:
            merged["cursor"] = coerce_cursor(merged["cursor"])
        out.append(merged)
    completed = pd.concat(out, ignore_index=True)
    logging.info(
        "Window completion [%s..%s]: %d -> %d rows (%d repos)",
        analysis_start, analysis_end, len(df), len(completed), completed["repo_name"].nunique(),
    )
    return completed


def load_treatment_meta(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("repo_name", "event_month"):
        if col not in df.columns:
            raise SystemExit(f"{path} missing required column: {col}")
    df = df[["repo_name", "event_month"]].dropna().copy()
    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["event_month"] = pd.to_datetime(df["event_month"].astype(str)).dt.strftime("%Y-%m")
    df = df.drop_duplicates(subset=["repo_name"], keep="first")
    logging.info("Loaded %d treatment repos with event_month", len(df))
    return df


def load_ts(path: Path, source: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in TS_COLUMNS_EXPECTED if c not in df.columns]
    if missing:
        logging.warning("%s missing columns %s (continuing)", path, missing)
    df = df.copy()
    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["month"] = df["month"].astype(str).str.strip()
    df["cursor"] = coerce_cursor(df["cursor"]) if "cursor" in df.columns else False
    df["dataset_source"] = source
    return df


def build_provenance(pairs_path: Path) -> pd.DataFrame:
    """
    One row per control repo with the treatments/ranks/periods it was matched to.

    The recovered matching artifacts may use slightly different column names.
    In particular, run8 final-clean pairs use control_rank, while older
    prepare_panel_event_v2 code expected match_rank. Normalize that here.
    """
    pairs = pd.read_csv(pairs_path)

    required = {"treatment_repo", "control_repo"}
    missing_required = required - set(pairs.columns)
    if missing_required:
        raise SystemExit(
            f"{pairs_path} missing required columns: {sorted(missing_required)}"
        )

    pairs = pairs.dropna(subset=["control_repo"]).copy()
    pairs["treatment_repo"] = pairs["treatment_repo"].astype(str).str.strip()
    pairs["control_repo"] = pairs["control_repo"].astype(str).str.strip()

    if "match_rank" not in pairs.columns:
        if "control_rank" in pairs.columns:
            pairs["match_rank"] = pairs["control_rank"]
        else:
            pairs["match_rank"] = pd.NA

    if "matched_period" not in pairs.columns:
        pairs["matched_period"] = pd.NA

    def join_unique(values: pd.Series) -> str:
        return "; ".join(sorted({str(v) for v in values.dropna()}))

    prov = (
        pairs.groupby("control_repo")
        .agg(
            matched_treatment_repos=("treatment_repo", join_unique),
            match_ranks=("match_rank", join_unique),
            matched_periods=("matched_period", join_unique),
        )
        .reset_index()
        .rename(columns={"control_repo": "repo_name"})
    )
    prov["matched_as_control"] = 1
    return prov

def make_lead_lag(time_to_event: pd.Series) -> pd.DataFrame:
    """lead_1..5 / lag_0..5 exact; lead_6 / lag_6 cumulative (matches original)."""
    out = {}
    for lead in range(1, MONTH_LEAD_AND_LAG):
        out[f"lead_{lead}"] = (time_to_event == -lead).astype(int)
    out[f"lead_{MONTH_LEAD_AND_LAG}"] = (time_to_event <= -MONTH_LEAD_AND_LAG).astype(int)
    for lag in range(0, MONTH_LEAD_AND_LAG):
        out[f"lag_{lag}"] = (time_to_event == lag).astype(int)
    out[f"lag_{MONTH_LEAD_AND_LAG}"] = (time_to_event >= MONTH_LEAD_AND_LAG).astype(int)
    return pd.DataFrame(out, index=time_to_event.index)


def build_treatment_panel(treat_ts: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Treatment rows with absorbing post + event-time indicators (no cursor reset)."""
    event_by_repo = dict(zip(meta["repo_name"], meta["event_month"]))
    frames = []
    for repo, event_month in event_by_repo.items():
        repo_ts = treat_ts[treat_ts["repo_name"] == repo].copy()
        if repo_ts.empty:
            logging.warning("No time series for treatment repo %s; skipping", repo)
            continue
        repo_ts["time_to_event"] = repo_ts["month"].map(lambda m: month_diff(m, event_month))
        repo_ts["event"] = event_month
        repo_ts["post_event"] = (repo_ts["time_to_event"] >= 0).astype(int)  # ABSORBING
        repo_ts["ever_treated"] = 1
        repo_ts["is_treatment"] = repo_ts["post_event"]
        repo_ts["is_treatment_dynamic"] = repo_ts["cursor"].astype(int)
        repo_ts = pd.concat([repo_ts, make_lead_lag(repo_ts["time_to_event"])], axis=1)
        frames.append(repo_ts)

    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)

    for repo, g in panel.groupby("repo_name"):
        pre = g[g["time_to_event"].between(-MONTH_LEAD_AND_LAG, -1)]
        if pre.empty or pre[["commits", "lines_added", "contributors"]].to_numpy().sum() == 0:
            logging.warning("Treated repo %s has empty/zero pre-adoption window", repo)
    return panel


def build_control_panel(control_ts: pd.DataFrame, provenance: pd.DataFrame) -> pd.DataFrame:
    """Control rows as never-treated: no event, no event-time, indicators all 0."""
    panel = control_ts.copy()
    panel["event"] = pd.NA
    panel["time_to_event"] = pd.NA
    panel["post_event"] = 0
    panel["ever_treated"] = 0
    panel["is_treatment"] = 0
    panel["is_treatment_dynamic"] = panel["cursor"].astype(int)

    for lead in range(1, MONTH_LEAD_AND_LAG + 1):
        panel[f"lead_{lead}"] = 0
    for lag in range(0, MONTH_LEAD_AND_LAG + 1):
        panel[f"lag_{lag}"] = 0

    panel = panel.merge(provenance, on="repo_name", how="left")
    panel["matched_as_control"] = (
        pd.to_numeric(panel["matched_as_control"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    analysis_end_month = pd.to_datetime(END_DATE).strftime("%Y-%m")
    in_window_leaked = panel.loc[
        (panel["cursor"] == True) & (panel["month"].astype(str) <= analysis_end_month),
        "repo_name",
    ].unique()

    post_window_cursor = panel.loc[
        (panel["cursor"] == True) & (panel["month"].astype(str) > analysis_end_month),
        "repo_name",
    ].unique()

    if len(in_window_leaked):
        logging.warning(
            "Control repos with in-window Cursor evidence (should be removed before DiD): %s",
            list(in_window_leaked),
        )

    if len(post_window_cursor):
        logging.info(
            "Control repos with post-window Cursor evidence kept as diagnostics: %s",
            list(post_window_cursor),
        )

    no_prov = panel.loc[panel["matched_as_control"] == 0, "repo_name"].unique()
    if len(no_prov):
        logging.warning("Control repos without PSM provenance: %s", list(no_prov))

    return panel

def filter_by_date(panel: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_datetime(panel["month"] + "-01")
    before = len(panel)
    panel = panel[(dt >= pd.to_datetime(START_DATE)) & (dt <= pd.to_datetime(END_DATE))]
    logging.info("Date filter [%s..%s]: %d -> %d rows", START_DATE, END_DATE, before, len(panel))
    return panel


def reorder(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.rename(columns={"month": "time"})
    lead_cols = [f"lead_{k}" for k in range(MONTH_LEAD_AND_LAG, 0, -1)]
    lag_cols = [f"lag_{k}" for k in range(0, MONTH_LEAD_AND_LAG + 1)]
    front = (
        ["repo_name", "time", "dataset_source", "ever_treated", "is_treatment",
         "is_treatment_dynamic", "event", "post_event", "time_to_event"]
        + lead_cols + lag_cols
        + ["cursor", "commits", "lines_added", "lines_removed", "contributors"]
    )
    provenance = ["matched_as_control", "matched_treatment_repos", "match_ranks", "matched_periods"]
    ordered = [c for c in front if c in panel.columns]
    ordered += [c for c in provenance if c in panel.columns]
    ordered += [c for c in panel.columns if c not in ordered and c not in ("latest_commit",)]
    return panel[ordered]


def assemble_panel(treat_ts: pd.DataFrame, control_ts: pd.DataFrame,
                   meta: pd.DataFrame, provenance: pd.DataFrame) -> pd.DataFrame:
    treatment_panel = build_treatment_panel(treat_ts, meta)
    control_panel = build_control_panel(control_ts, provenance)
    if treatment_panel.empty and control_panel.empty:
        raise SystemExit("No panel rows produced.")
    panel = pd.concat([treatment_panel, control_panel], ignore_index=True)
    panel = filter_by_date(panel)
    return reorder(panel)


def log_summary(panel: pd.DataFrame, label: str) -> None:
    logging.info(
        "[%s] Rows: %d | treated repos: %d | control repos: %d",
        label, len(panel),
        panel.loc[panel["ever_treated"] == 1, "repo_name"].nunique(),
        panel.loc[panel["ever_treated"] == 0, "repo_name"].nunique(),
    )
    summary = (
        panel.groupby("dataset_source")
        .agg(repos=("repo_name", "nunique"), rows=("repo_name", "size"), post_rows=("post_event", "sum"))
        .reset_index()
    )
    print(f"\n=== {label} panel summary ===")
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paper-faithful matched DiD event panel(s).")
    parser.add_argument("--treatment-meta", default="tmp_adoption_test/data/matched_controls_v2_treatment_only.csv")
    parser.add_argument("--pairs", default="tmp_adoption_test/data/matched_controls_v2_pairs.csv")
    parser.add_argument("--treatment-ts", default="tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv")
    parser.add_argument("--control-ts", default="tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv")
    parser.add_argument("--output", default="tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv",
                        help="Unbalanced panel (months with commits only).")
    parser.add_argument("--balanced-output", default="tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv",
                        help="Window-completed panel (zero-filled months within analysis window).")
    parser.add_argument("--no-balanced", action="store_true", help="Skip the balanced output.")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    treatment_meta = PROJECT_ROOT / args.treatment_meta
    pairs_path = PROJECT_ROOT / args.pairs
    treatment_ts_path = PROJECT_ROOT / args.treatment_ts
    control_ts_path = PROJECT_ROOT / args.control_ts
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta = load_treatment_meta(treatment_meta)

    pairs_for_meta = pd.read_csv(pairs_path)
    required_pair_cols = {"treatment_repo", "control_repo"}
    missing_pair_cols = required_pair_cols - set(pairs_for_meta.columns)
    if missing_pair_cols:
        raise SystemExit(
            f"{pairs_path} missing required columns: {sorted(missing_pair_cols)}"
        )

    pairs_for_meta["treatment_repo"] = (
        pairs_for_meta["treatment_repo"].dropna().astype(str).str.strip()
    )
    pairs_for_meta["control_repo"] = (
        pairs_for_meta["control_repo"].dropna().astype(str).str.strip()
    )

    paired_treatments = set(pairs_for_meta["treatment_repo"].dropna())
    paired_controls = set(pairs_for_meta["control_repo"].dropna())

    before_meta = len(meta)
    meta = meta[meta["repo_name"].isin(paired_treatments)].copy()
    logging.info(
        "Filtered treatment metadata to treatments present in selected pair file: %d -> %d",
        before_meta,
        len(meta),
    )

    treat_ts = load_ts(treatment_ts_path, "treatment")
    control_ts = load_ts(control_ts_path, "control")

    treatment_ts_repos = set(treat_ts["repo_name"].dropna().astype(str).str.strip())
    control_ts_repos = set(control_ts["repo_name"].dropna().astype(str).str.strip())

    missing_treatment_ts = sorted(paired_treatments - treatment_ts_repos)
    missing_control_ts = sorted(paired_controls - control_ts_repos)

    if missing_treatment_ts:
        logging.warning(
            "Treatment repos in selected pairs but missing treatment time series (%d): %s",
            len(missing_treatment_ts),
            missing_treatment_ts,
        )

    if missing_control_ts:
        logging.warning(
            "Control repos in selected pairs but missing control time series (%d): %s",
            len(missing_control_ts),
            missing_control_ts,
        )

    before_control_rows = len(control_ts)
    before_control_repos = control_ts["repo_name"].nunique()
    control_ts = control_ts[control_ts["repo_name"].isin(paired_controls)].copy()
    logging.info(
        "Filtered control time series to controls present in selected pair file: rows %d -> %d, repos %d -> %d",
        before_control_rows,
        len(control_ts),
        before_control_repos,
        control_ts["repo_name"].nunique(),
    )

    provenance = build_provenance(pairs_path)

    # --- Unbalanced panel (existing behavior: months with commits only) ---
    logging.info("=== Building UNBALANCED panel ===")
    unbalanced = assemble_panel(treat_ts, control_ts, meta, provenance)
    unbalanced.to_csv(output_path, index=False)
    logging.info("Saved unbalanced panel: %s", output_path)
    log_summary(unbalanced, "UNBALANCED")

    # --- Balanced panel (window completion: zero-fill missing months) ---
    if not args.no_balanced:
        astart = pd.to_datetime(START_DATE).strftime("%Y-%m")
        aend = pd.to_datetime(END_DATE).strftime("%Y-%m")
        logging.info("=== Building BALANCED panel (window completion) ===")
        treat_ts_b = complete_repo_months(treat_ts, astart, aend)
        control_ts_b = complete_repo_months(control_ts, astart, aend)
        balanced = assemble_panel(treat_ts_b, control_ts_b, meta, provenance)
        balanced_output_path = PROJECT_ROOT / args.balanced_output
        balanced_output_path.parent.mkdir(parents=True, exist_ok=True)
        balanced.to_csv(balanced_output_path, index=False)
        logging.info("Saved balanced panel: %s", balanced_output_path)
        log_summary(balanced, "BALANCED")


if __name__ == "__main__":
    main()
__MERGED_PYTHON_14__

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/summarize_matched_panels.py --
###############################################################################

: <<'__MERGED_PYTHON_15__'
#!/usr/bin/env python3
"""
Summarize matched Python DiD panels.

This script summarizes four panel variants using the current Python naming convention:

  1. flexible
     - Keeps all final-clean matched treatments, including treatments with 2 or 3 controls.
     - Uses observed repo-month rows only.

  2. strict
     - Keeps only treatments with exactly 3 final controls.
     - Uses observed repo-month rows only.

  3. flexible_window_driven
     - Uses the flexible matched sample.
     - Completes the Jan 2024-Aug 2025 observation window.

  4. strict_window_driven
     - Uses the strict matched sample.
     - Completes the Jan 2024-Aug 2025 observation window.

Inputs:
  - Panel CSV files under repo_python/did_final/
  - Optional treatment/control coverage files for attrition diagnostics

Outputs:
  - panel_qc_summary.csv
  - panel_qc_by_source.csv
  - panel_qc_paper_comparison.csv
  - panel_qc_attrition_summary.csv
  - panel_qc_dropped_by_strict.csv
  - panel_qc_notes.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


def read_csv_required(path: Path) -> pd.DataFrame:
    """Read a required CSV file and raise a clear error when it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path)


def find_time_column(df: pd.DataFrame) -> Optional[str]:
    """Return the panel time column name."""
    for col in ["time", "month"]:
        if col in df.columns:
            return col
    return None


def find_post_column(df: pd.DataFrame) -> Optional[str]:
    """Return the post-treatment indicator column name."""
    for col in ["post_event", "post", "post_treatment"]:
        if col in df.columns:
            return col
    return None


def find_treatment_column(df: pd.DataFrame) -> Optional[str]:
    """Return the treatment indicator column name."""
    for col in ["is_treatment", "ever_treated", "treated"]:
        if col in df.columns:
            return col
    return None


def source_mask(df: pd.DataFrame, source: str) -> pd.Series:
    """Return a boolean mask for treatment or control rows."""
    if "dataset_source" in df.columns:
        return df["dataset_source"].astype(str).str.lower().eq(source)

    treatment_col = find_treatment_column(df)
    if treatment_col is None:
        raise ValueError(
            "Panel must contain dataset_source or a treatment indicator column "
            "(is_treatment, ever_treated, or treated)."
        )

    if source == "treatment":
        return df[treatment_col].eq(1)
    if source == "control":
        return df[treatment_col].eq(0)

    raise ValueError(f"Unknown source: {source}")


def summarize_panel(panel_name: str, path: Path) -> Dict[str, object]:
    """Summarize one panel file."""
    df = read_csv_required(path)

    if "repo_name" not in df.columns:
        raise ValueError(f"{path} is missing repo_name column.")

    time_col = find_time_column(df)
    post_col = find_post_column(df)

    treat_mask = source_mask(df, "treatment")
    control_mask = source_mask(df, "control")

    treatment_df = df.loc[treat_mask].copy()
    control_df = df.loc[control_mask].copy()

    if post_col is not None:
        post_rows = int(treatment_df[post_col].fillna(0).astype(int).sum())
    else:
        post_rows = None

    summary = {
        "panel": panel_name,
        "file": str(path),
        "rows": int(len(df)),
        "repos": int(df["repo_name"].nunique()),
        "treated_repos": int(treatment_df["repo_name"].nunique()),
        "control_repos": int(control_df["repo_name"].nunique()),
        "treatment_rows": int(len(treatment_df)),
        "control_rows": int(len(control_df)),
        "post_treatment_rows": post_rows,
        "avg_rows_per_repo": round(float(len(df) / df["repo_name"].nunique()), 4)
        if df["repo_name"].nunique()
        else 0.0,
        "time_col": time_col or "",
        "time_min": df[time_col].min() if time_col else "",
        "time_max": df[time_col].max() if time_col else "",
    }

    return summary


def summarize_by_source(panel_name: str, path: Path) -> pd.DataFrame:
    """Summarize treatment/control rows inside one panel."""
    df = read_csv_required(path)

    if "repo_name" not in df.columns:
        raise ValueError(f"{path} is missing repo_name column.")

    post_col = find_post_column(df)
    rows: List[Dict[str, object]] = []

    for source in ["treatment", "control"]:
        mask = source_mask(df, source)
        sub = df.loc[mask].copy()

        if post_col is not None:
            post_rows = int(sub[post_col].fillna(0).astype(int).sum())
        else:
            post_rows = None

        rows.append(
            {
                "panel": panel_name,
                "dataset_source": source,
                "repos": int(sub["repo_name"].nunique()),
                "rows": int(len(sub)),
                "post_rows": post_rows,
            }
        )

    return pd.DataFrame(rows)


def build_paper_comparison(summary_df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    """Compare flexible and strict unbalanced panels with paper Table 7."""
    rows = []
    paper = {
        "treatment_repos": args.paper_treatment_repos,
        "control_repos": args.paper_control_repos,
        "total_observations": args.paper_total_observations,
        "post_treatment_observations": args.paper_post_treatment_observations,
    }

    target_panels = ["flexible", "strict"]

    for panel in target_panels:
        match = summary_df.loc[summary_df["panel"].eq(panel)]
        if match.empty:
            continue

        row = match.iloc[0]

        rows.append(
            {
                "panel": panel,
                "comparison_focus": "sample_size" if panel == "flexible" else "matching_rule",
                "paper_treatment_repos": paper["treatment_repos"],
                "current_treatment_repos": int(row["treated_repos"]),
                "treatment_repo_difference": int(row["treated_repos"]) - paper["treatment_repos"],
                "paper_control_repos": paper["control_repos"],
                "current_control_repos": int(row["control_repos"]),
                "control_repo_difference": int(row["control_repos"]) - paper["control_repos"],
                "paper_total_observations": paper["total_observations"],
                "current_total_observations": int(row["rows"]),
                "total_observation_difference": int(row["rows"]) - paper["total_observations"],
                "paper_post_treatment_observations": paper["post_treatment_observations"],
                "current_post_treatment_observations": int(row["post_treatment_rows"]),
                "post_treatment_observation_difference": int(row["post_treatment_rows"])
                - paper["post_treatment_observations"],
            }
        )

    return pd.DataFrame(rows)


def build_attrition_summary(args: argparse.Namespace) -> pd.DataFrame:
    """Build treatment/control attrition summary when supporting files are available."""
    rows: List[Dict[str, object]] = []

    def add(metric: str, value: object, note: str) -> None:
        rows.append({"metric": metric, "value": value, "note": note})

    if args.treatment_sample.exists():
        treatment = pd.read_csv(args.treatment_sample)
        if "repo_name" in treatment.columns:
            add(
                "current_treatment_sample",
                int(treatment["repo_name"].nunique()),
                "Current reproducible Python treatment sample.",
            )

    if args.treatment_missing_matching.exists():
        missing = pd.read_csv(args.treatment_missing_matching)
        repo_col = "repo_name" if "repo_name" in missing.columns else None
        if repo_col:
            add(
                "treatments_missing_matching_rows",
                int(missing[repo_col].nunique()),
                "Treatment repos present in the treatment sample but missing selected matching rows.",
            )

    if args.final_coverage.exists():
        coverage = pd.read_csv(args.final_coverage)
        if "treatment_repo" in coverage.columns:
            add(
                "flexible_final_matched_treatments",
                int(coverage["treatment_repo"].nunique()),
                "Treatments retained by the flexible final-clean matched pair file.",
            )

        if "num_final_controls" in coverage.columns:
            counts = coverage["num_final_controls"].value_counts().sort_index()
            for num_controls, count in counts.items():
                add(
                    f"treatments_with_{int(num_controls)}_final_controls",
                    int(count),
                    "Final control-count distribution after clone and local Cursor filtering.",
                )

    if args.strict_coverage.exists():
        strict_coverage = pd.read_csv(args.strict_coverage)
        if "treatment_repo" in strict_coverage.columns:
            add(
                "strict_1to3_treatments",
                int(strict_coverage["treatment_repo"].nunique()),
                "Treatments retained by the strict 1:3 final-clean matched pair file.",
            )

    if args.final_controls.exists():
        final_controls = pd.read_csv(args.final_controls)
        if "repo_name" in final_controls.columns:
            add(
                "final_clean_controls_before_panel",
                int(final_controls["repo_name"].nunique()),
                "Final clean controls before unbalanced observed-row filtering.",
            )

    return pd.DataFrame(rows)


def build_dropped_by_strict(args: argparse.Namespace) -> pd.DataFrame:
    """Return treatments dropped by strict 1:3 because they do not have exactly 3 controls."""
    if not args.final_coverage.exists():
        return pd.DataFrame(columns=["treatment_repo", "num_final_controls"])

    coverage = pd.read_csv(args.final_coverage)
    needed = {"treatment_repo", "num_final_controls"}
    if not needed.issubset(set(coverage.columns)):
        return pd.DataFrame(columns=["treatment_repo", "num_final_controls"])

    out = coverage.loc[coverage["num_final_controls"].ne(3), ["treatment_repo", "num_final_controls"]].copy()
    out = out.sort_values(["num_final_controls", "treatment_repo"])
    return out


def write_notes(
    path: Path,
    summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    attrition_df: pd.DataFrame,
) -> None:
    """Write a compact Markdown note for human review."""
    lines: List[str] = []
    lines.append("# Python Matched Panel QC Notes")
    lines.append("")
    lines.append("## Panel summary")
    lines.append("")
    lines.append(summary_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Paper comparison")
    lines.append("")
    if comparison_df.empty:
        lines.append("(No paper comparison rows generated.)")
    else:
        lines.append(comparison_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Attrition summary")
    lines.append("")
    if attrition_df.empty:
        lines.append("(No attrition summary rows generated.)")
    else:
        lines.append(attrition_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "- `flexible` is the sample-size / coverage-oriented unbalanced panel. "
        "It keeps all final-clean matched treatments, including treatments with 2 or 3 controls."
    )
    lines.append(
        "- `strict` is the matching-rule-oriented unbalanced panel. "
        "It keeps only treatments with exactly 3 final controls."
    )
    lines.append(
        "- `window_driven` panels complete the Jan 2024-Aug 2025 window and should not be "
        "directly compared with paper Table 7 unbalanced observation counts."
    )
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize matched Python DiD panels.")

    parser.add_argument("--flexible-panel", type=Path, required=True)
    parser.add_argument("--strict-panel", type=Path, required=True)
    parser.add_argument("--flexible-window-driven-panel", type=Path, required=True)
    parser.add_argument("--strict-window-driven-panel", type=Path, required=True)

    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-by-source", type=Path, required=True)
    parser.add_argument("--output-paper-comparison", type=Path, required=True)
    parser.add_argument("--output-attrition", type=Path, required=True)
    parser.add_argument("--output-dropped-by-strict", type=Path, required=True)
    parser.add_argument("--output-notes", type=Path, required=True)

    parser.add_argument("--treatment-sample", type=Path, default=Path("repo_python/treatment_sample_main.csv"))
    parser.add_argument(
        "--treatment-missing-matching",
        type=Path,
        default=Path("repo_python/treatment_missing_matching_main.csv"),
    )
    parser.add_argument(
        "--final-coverage",
        type=Path,
        default=Path("repo_python/control_pair_coverage_main_final_clean.csv"),
    )
    parser.add_argument(
        "--strict-coverage",
        type=Path,
        default=Path("repo_python/control_pair_coverage_main_final_clean_1to3_only.csv"),
    )
    parser.add_argument(
        "--final-controls",
        type=Path,
        default=Path("repo_python/control_clone_usable_repos_main_final_clean.csv"),
    )

    parser.add_argument("--paper-treatment-repos", type=int, default=121)
    parser.add_argument("--paper-control-repos", type=int, default=127)
    parser.add_argument("--paper-total-observations", type=int, default=2461)
    parser.add_argument("--paper-post-treatment-observations", type=int, default=582)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    panel_paths = {
        "flexible": args.flexible_panel,
        "strict": args.strict_panel,
        "flexible_window_driven": args.flexible_window_driven_panel,
        "strict_window_driven": args.strict_window_driven_panel,
    }

    summary_rows = []
    by_source_frames = []

    for panel_name, path in panel_paths.items():
        summary_rows.append(summarize_panel(panel_name, path))
        by_source_frames.append(summarize_by_source(panel_name, path))

    summary_df = pd.DataFrame(summary_rows)
    by_source_df = pd.concat(by_source_frames, ignore_index=True)
    comparison_df = build_paper_comparison(summary_df, args)
    attrition_df = build_attrition_summary(args)
    dropped_df = build_dropped_by_strict(args)

    for path in [
        args.output_summary,
        args.output_by_source,
        args.output_paper_comparison,
        args.output_attrition,
        args.output_dropped_by_strict,
        args.output_notes,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)

    summary_df.to_csv(args.output_summary, index=False)
    by_source_df.to_csv(args.output_by_source, index=False)
    comparison_df.to_csv(args.output_paper_comparison, index=False)
    attrition_df.to_csv(args.output_attrition, index=False)
    dropped_df.to_csv(args.output_dropped_by_strict, index=False)

    write_notes(args.output_notes, summary_df, comparison_df, attrition_df)

    print("Saved panel summary:", args.output_summary)
    print(summary_df.to_string(index=False))
    print()
    print("Saved by-source summary:", args.output_by_source)
    print(by_source_df.to_string(index=False))
    print()
    print("Saved paper comparison:", args.output_paper_comparison)
    print(comparison_df.to_string(index=False))
    print()
    print("Saved attrition summary:", args.output_attrition)
    print(attrition_df.to_string(index=False))
    print()
    print("Saved dropped-by-strict diagnostics:", args.output_dropped_by_strict)
    if len(dropped_df):
        print(dropped_df.to_string(index=False))
    else:
        print("(none)")
    print()
    print("Saved notes:", args.output_notes)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_15__

###############################################################################
# -- SHELL SCRIPT: run-py-2a-create-sonarqube-input.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2a: Create Python SonarQube scan inputs
# ============================================================
#
# Purpose:
#   Create treatment/control SonarQube scan input files from the
#   final Python matched DiD panels.
#
# Panel inputs:
#   flexible:
#     repo_python/run-py-1l/panel_event_matched_flexible.csv
#
#   strict:
#     repo_python/run-py-1l/panel_event_matched_strict.csv
#
# Full-run main outputs:
#   repo_python/run-py-2a/<variant>/treatment/data/ts_repos_monthly.csv
#   repo_python/run-py-2a/<variant>/control/data/ts_repos_monthly.csv
#
# Full-run extra outputs:
#   repo_python/tmp/run-py-2a/<variant>/months.txt
#   repo_python/tmp/run-py-2a/<variant>/treatment_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/control_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/sonarqube_input_summary.csv
#
# Smoke outputs:
#   repo_python/tmp/run-py-2a/smoke/<variant>/
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

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_sonarqube_input.py}"
HISTORY_SCRIPT="${HISTORY_SCRIPT:-proc_scripts/create_tmp_repo_timeseries_history.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

DID_DIR="${DID_DIR:-${OUTPUT_BASE_DIR}/run-py-1l}"
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

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

MAX_TREATMENT_REPOS="${MAX_TREATMENT_REPOS:-0}"
MAX_CONTROL_REPOS="${MAX_CONTROL_REPOS:-0}"
ALLOW_MISSING_LATEST_COMMIT="${ALLOW_MISSING_LATEST_COMMIT:-false}"

if [[ "${MAX_TREATMENT_REPOS}" -gt 0 || "${MAX_CONTROL_REPOS}" -gt 0 ]]; then
  RUN_MODE="smoke"
  DEFAULT_SONAR_ROOT="${TMP_DIR}/smoke/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${DEFAULT_SONAR_ROOT}/meta"
else
  RUN_MODE="full"
  DEFAULT_SONAR_ROOT="${MAIN_OUTPUT_DIR}/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${TMP_DIR}/${PANEL_VARIANT}"
fi

SONAR_ROOT="${SONAR_ROOT:-${DEFAULT_SONAR_ROOT}}"
META_DIR="${META_DIR:-${DEFAULT_META_DIR}}"

TREATMENT_TS_FILE="${TREATMENT_TS_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_TS_FILE="${CONTROL_TS_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"

MONTHS_FILE="${MONTHS_FILE:-${META_DIR}/months.txt}"
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${META_DIR}/treatment_repos.txt}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${META_DIR}/control_repos.txt}"
SUMMARY_FILE="${SUMMARY_FILE:-${META_DIR}/sonarqube_input_summary.csv}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_sonarqube_input_${PANEL_VARIANT}_${RUN_TS}.log}"

mkdir -p \
  "${LOG_DIR}" \
  "${SONAR_ROOT}" \
  "${META_DIR}" \
  "$(dirname "${TREATMENT_TS_FILE}")" \
  "$(dirname "${CONTROL_TS_FILE}")"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: create Python SonarQube scan inputs"
  echo "Timestamp:                    ${RUN_TS}"
  echo "Script name:                  ${SCRIPT_NAME}"
  echo "Run prefix:                   ${RUN_PREFIX}"
  echo "Run mode:                     ${RUN_MODE}"
  echo "Panel variant:                ${PANEL_VARIANT}"
  echo "Python script:                ${PY_SCRIPT}"
  echo "History script:               ${HISTORY_SCRIPT}"
  echo "Panel file:                   ${PANEL_FILE}"
  echo "Sonar root:                   ${SONAR_ROOT}"
  echo "Metadata dir:                 ${META_DIR}"
  echo "Main output dir:              ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:             ${TMP_DIR}"
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
  echo "${RUN_PREFIX} completed successfully."
  echo "Run mode:        ${RUN_MODE}"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Treatment input: ${TREATMENT_TS_FILE}"
  echo "Control input:   ${CONTROL_TS_FILE}"
  echo "Summary file:    ${SUMMARY_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:${TMP_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9a-create-jsts-sonarqube-input.sh,
# but it does NOT call the existing JS/TS shell wrapper.

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/prepare_sonarqube_input.py --
###############################################################################

: <<'__MERGED_PYTHON_16__'
#!/usr/bin/env python3
"""
Prepare JS/TS SonarQube scan inputs from a final matched DiD panel.

This script:
1. Reads the final window-completed matched DiD panel.
2. Extracts treatment/control repository lists and analysis months.
3. Calls create_tmp_repo_timeseries_history.py to find the latest commit
   at or before each month-end for each repository.
4. Writes treatment/control SonarQube input files.
5. Writes repo lists, month list, and a compact summary CSV.

The output files are intended to be consumed by run_sonarqube_v2.py.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare treatment/control SonarQube input files from a final JS/TS DiD panel."
    )

    parser.add_argument(
        "--panel-file",
        default="tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv",
        help="Final window-completed matched DiD panel.",
    )

    parser.add_argument(
        "--sonar-root",
        default="tmp_jsts_test/data/jsts_sonarqube_main",
        help="Root output directory for SonarQube input artifacts.",
    )

    parser.add_argument(
        "--treatment-clone-root",
        default="../ai_code_complexity_study_jsts_repo_dataset",
        help="Clone root for treatment repositories.",
    )

    parser.add_argument(
        "--control-clone-root",
        default="../ai_code_complexity_study_jsts_control_repo_dataset",
        help="Clone root for control repositories.",
    )

    parser.add_argument(
        "--history-script",
        default="proc_scripts/create_tmp_repo_timeseries_history.py",
        help="Script used to create historical repo-month latest_commit input.",
    )

    parser.add_argument(
        "--treatment-output",
        default=None,
        help="Treatment SonarQube input CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--control-output",
        default=None,
        help="Control SonarQube input CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--months-file",
        default=None,
        help="Output text file containing comma-separated months. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--treatment-repos-file",
        default=None,
        help="Output text file containing treatment repos. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--control-repos-file",
        default=None,
        help="Output text file containing control repos. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--summary-file",
        default=None,
        help="Output summary CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--max-treatment-repos",
        type=int,
        default=0,
        help="Optional smoke-test limit for treatment repos. 0 means all.",
    )

    parser.add_argument(
        "--max-control-repos",
        type=int,
        default=0,
        help="Optional smoke-test limit for control repos. 0 means all.",
    )

    parser.add_argument(
        "--allow-missing-latest-commit",
        action="store_true",
        help="Allow rows with missing latest_commit instead of failing.",
    )

    return parser.parse_args()


def require_path(path: Path, label: str, is_dir: bool = False) -> None:
    if is_dir:
        if not path.is_dir():
            raise SystemExit(f"ERROR: {label} not found or not a directory: {path}")
    else:
        if not path.is_file():
            raise SystemExit(f"ERROR: {label} not found: {path}")


def write_lines(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(values) + ("\n" if values else ""))


def summarize_input(path: Path, label: str) -> dict:
    require_path(path, f"{label} output file")

    df = pd.read_csv(path)

    required = {"repo_name", "month", "latest_commit"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")

    duplicate_repo_month_rows = int(df.duplicated(["repo_name", "month"]).sum())
    missing_latest_commit = int(df["latest_commit"].isna().sum())

    return {
        "dataset_source": label,
        "file": str(path),
        "rows": len(df),
        "repos": df["repo_name"].nunique(),
        "min_month": df["month"].min(),
        "max_month": df["month"].max(),
        "missing_latest_commit": missing_latest_commit,
        "duplicate_repo_month_rows": duplicate_repo_month_rows,
    }


def run_history_script(
    history_script: Path,
    output_file: Path,
    clone_root: Path,
    months_csv: str,
    repos: list[str],
    label: str,
) -> None:
    if not repos:
        raise SystemExit(f"ERROR: no {label} repos to process.")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(history_script),
        "--output",
        str(output_file),
        "--clone-root",
        str(clone_root),
        "--months",
        months_csv,
        *repos,
    ]

    print()
    print(f"** Creating {label} historical SonarQube input")
    print("------------------------------------------------------------")
    print("repos:", len(repos))
    print("output:", output_file)
    print("clone root:", clone_root)
    print("command:")
    print(" ".join(cmd[:8]) + f" ... [{len(repos)} repos]")

    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()

    panel_file = Path(args.panel_file)
    sonar_root = Path(args.sonar_root)
    treatment_clone_root = Path(args.treatment_clone_root)
    control_clone_root = Path(args.control_clone_root)
    history_script = Path(args.history_script)

    treatment_output = (
        Path(args.treatment_output)
        if args.treatment_output
        else sonar_root / "treatment" / "data" / "ts_repos_monthly.csv"
    )
    control_output = (
        Path(args.control_output)
        if args.control_output
        else sonar_root / "control" / "data" / "ts_repos_monthly.csv"
    )

    months_file = (
        Path(args.months_file) if args.months_file else sonar_root / "months.txt"
    )
    treatment_repos_file = (
        Path(args.treatment_repos_file)
        if args.treatment_repos_file
        else sonar_root / "treatment_repos.txt"
    )
    control_repos_file = (
        Path(args.control_repos_file)
        if args.control_repos_file
        else sonar_root / "control_repos.txt"
    )
    summary_file = (
        Path(args.summary_file)
        if args.summary_file
        else sonar_root / "sonarqube_input_summary.csv"
    )

    require_path(panel_file, "panel file")
    require_path(history_script, "history script")
    require_path(treatment_clone_root, "treatment clone root", is_dir=True)
    require_path(control_clone_root, "control clone root", is_dir=True)

    sonar_root.mkdir(parents=True, exist_ok=True)
    treatment_output.parent.mkdir(parents=True, exist_ok=True)
    control_output.parent.mkdir(parents=True, exist_ok=True)

    print("** Loading final panel")
    print("------------------------------------------------------------")
    print("panel:", panel_file)

    panel = pd.read_csv(panel_file)

    required = {"repo_name", "time", "dataset_source"}
    missing = required - set(panel.columns)
    if missing:
        raise SystemExit(f"ERROR: panel missing required columns: {sorted(missing)}")

    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["time"] = panel["time"].astype(str).str.strip()
    panel["dataset_source"] = panel["dataset_source"].astype(str).str.strip()

    months = sorted(panel["time"].dropna().unique().tolist())
    treatment_repos = sorted(
        panel.loc[panel["dataset_source"] == "treatment", "repo_name"]
        .dropna()
        .unique()
        .tolist()
    )
    control_repos = sorted(
        panel.loc[panel["dataset_source"] == "control", "repo_name"]
        .dropna()
        .unique()
        .tolist()
    )

    if args.max_treatment_repos > 0:
        treatment_repos = treatment_repos[: args.max_treatment_repos]
    if args.max_control_repos > 0:
        control_repos = control_repos[: args.max_control_repos]

    if not months:
        raise SystemExit("ERROR: no months found in panel.")
    if not treatment_repos:
        raise SystemExit("ERROR: no treatment repos found in panel.")
    if not control_repos:
        raise SystemExit("ERROR: no control repos found in panel.")

    months_csv = ",".join(months)

    months_file.parent.mkdir(parents=True, exist_ok=True)
    months_file.write_text(months_csv + "\n")
    write_lines(treatment_repos_file, treatment_repos)
    write_lines(control_repos_file, control_repos)

    print("months:", months[0], "to", months[-1], "n=", len(months))
    print("treatment repos:", len(treatment_repos))
    print("control repos:", len(control_repos))
    print("wrote:", months_file)
    print("wrote:", treatment_repos_file)
    print("wrote:", control_repos_file)

    run_history_script(
        history_script=history_script,
        output_file=treatment_output,
        clone_root=treatment_clone_root,
        months_csv=months_csv,
        repos=treatment_repos,
        label="treatment",
    )

    run_history_script(
        history_script=history_script,
        output_file=control_output,
        clone_root=control_clone_root,
        months_csv=months_csv,
        repos=control_repos,
        label="control",
    )

    print()
    print("** Input summary")
    print("------------------------------------------------------------")

    summary_rows = [
        summarize_input(treatment_output, "treatment"),
        summarize_input(control_output, "control"),
    ]

    summary = pd.DataFrame(summary_rows)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_file, index=False)

    print(summary.to_string(index=False))
    print()
    print("Saved summary:", summary_file)

    total_missing_latest_commit = int(summary["missing_latest_commit"].sum())
    total_duplicate_rows = int(summary["duplicate_repo_month_rows"].sum())

    if total_duplicate_rows > 0:
        raise SystemExit(
            f"ERROR: duplicate repo-month rows detected: {total_duplicate_rows}"
        )

    if total_missing_latest_commit > 0 and not args.allow_missing_latest_commit:
        raise SystemExit(
            "ERROR: missing latest_commit values detected. "
            "Use --allow-missing-latest-commit only if this is expected."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_16__

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/create_tmp_repo_timeseries_history.py --
###############################################################################

: <<'__MERGED_PYTHON_17__'
#!/usr/bin/env python3
"""
Create a temporary multi-month repository time-series input from actual Git history.

For each repo and month, this script finds the latest commit at or before the
end of that month using:

    git rev-list -n 1 --before <month-end> HEAD

This is closer to the original paper pipeline than repeating current HEAD.
"""

from __future__ import annotations

import argparse
import calendar
import subprocess
from pathlib import Path

import pandas as pd


def repo_to_project_key(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def month_end_timestamp(month: str) -> str:
    year, mon = map(int, month.split("-"))
    last_day = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-{last_day:02d} 23:59:59"


def get_latest_commit_before(repo_path: Path, before_time: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-list", "-n", "1", "--before", before_time, "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )

    commit = result.stdout.strip()
    return commit if commit else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create temporary multi-month SonarQube input from actual Git history."
    )

    parser.add_argument(
        "repo_names",
        nargs="+",
        help="GitHub repositories in OWNER/REPO format.",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path, e.g., tmp_sonar_batch/data/ts_repos_monthly.csv.",
    )

    parser.add_argument(
        "--clone-root",
        default="../CursorRepos",
        help="Directory containing cloned repositories. Default: ../CursorRepos.",
    )

    parser.add_argument(
        "--months",
        required=True,
        help="Comma-separated months, e.g., 2026-03,2026-04,2026-05.",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    clone_root = Path(args.clone_root)
    months = [m.strip() for m in args.months.split(",") if m.strip()]

    rows = []

    for repo_name in args.repo_names:
        project_key = repo_to_project_key(repo_name)
        repo_path = clone_root / project_key

        if not (repo_path / ".git").exists():
            raise SystemExit(f"Missing cloned Git repository: {repo_path}")

        for month in months:
            before_time = month_end_timestamp(month)
            commit = get_latest_commit_before(repo_path, before_time)

            if not commit:
                print(f"WARNING: no commit found for {repo_name} at {month}")
                continue

            rows.append(
                {
                    "repo_name": repo_name,
                    "month": month,
                    "latest_commit": commit,
                }
            )

    df = pd.DataFrame(rows)
    df = df.sort_values(["repo_name", "month"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Wrote:", output_path)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

__MERGED_PYTHON_17__

###############################################################################
# -- SHELL SCRIPT: run-py-2b-sonarqube-scan.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2b: Run SonarQube scan for Python repo-month inputs
# ============================================================
#
# Purpose:
#   Run SonarQube scans for Python treatment/control repo-month
#   input files generated by run-py-2a-create-sonarqube-input.sh.
#
# Inputs:
#   repo_python/run-py-2a/<variant>/<target>/data/ts_repos_monthly.csv
#
# Target:
#   TARGET=treatment
#   TARGET=control
#
# Main output:
#   repo_python/run-py-2b/<variant>/<target>/ts_repos_monthly_scanned.csv
#
# Reuse:
#   Copy a previously verified scanned CSV to the main output path,
#   then run with SKIP_SCAN=true to validate and reuse it.
#
# Usage:
#   Smoke or full depends on the input generated by run-py-2a.
#
#   PANEL_VARIANT=strict   TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=strict   TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=flexible TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   PANEL_VARIANT=flexible TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# 
#   SKIP_SCAN=true PANEL_VARIANT=strict TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=strict TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=flexible TARGET=treatment NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=true PANEL_VARIANT=flexible TARGET=control   NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# 
#   SKIP_SCAN=false PANEL_VARIANT=strict TARGET=treatment LANGUAGE_PROFILE=python-only PROJECT_KEY_PREFIX=pyonly_ OUTPUT_SUFFIX=python_only NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
#   SKIP_SCAN=false PANEL_VARIANT=strict TARGET=control LANGUAGE_PROFILE=python-only PROJECT_KEY_PREFIX=pyonly_ OUTPUT_SUFFIX=python_only NUM_PROCESSES=1 bash run-py-2b-sonarqube-scan.sh
# ============================================================

TARGET="${TARGET:-treatment}"
PANEL_VARIANT="${PANEL_VARIANT:-flexible}"
LANGUAGE_PROFILE="${LANGUAGE_PROFILE:-python}"
PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"
SKIP_SCAN="${SKIP_SCAN:-false}"

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

if [[ "${TARGET}" != "treatment" && "${TARGET}" != "control" ]]; then
  echo "ERROR: TARGET must be either 'treatment' or 'control'. Got: ${TARGET}"
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either 'flexible' or 'strict'. Got: ${PANEL_VARIANT}"
  exit 1
fi

if [[ "${SKIP_SCAN}" != "true" && "${SKIP_SCAN}" != "false" ]]; then
  echo "ERROR: SKIP_SCAN must be true or false. Got: ${SKIP_SCAN}"
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_sonarqube_${PANEL_VARIANT}_${TARGET}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/run_sonarqube_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
INPUT_ROOT="${INPUT_ROOT:-${OUTPUT_BASE_DIR}/run-py-2a/${PANEL_VARIANT}}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/${PANEL_VARIANT}/${TARGET}}"

NUM_PROCESSES="${NUM_PROCESSES:-1}"
AGGREGATION="${AGGREGATION:-month}"

INPUT_FILE="${INPUT_FILE:-${INPUT_ROOT}/${TARGET}/data/ts_repos_monthly.csv}"

if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_scanned_${OUTPUT_SUFFIX}.csv}"
else
  OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/ts_repos_monthly_scanned.csv}"
fi

if [[ "${TARGET}" == "treatment" ]]; then
  CLONE_DIR="${CLONE_DIR:-../treatment-repos}"
else
  CLONE_DIR="${CLONE_DIR:-../control-repos}"
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: Python SonarQube scan"
  echo "Started:         $(date)"
  echo "Script name:     ${SCRIPT_NAME}"
  echo "Run prefix:      ${RUN_PREFIX}"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Target:          ${TARGET}"
  echo "Python script:   ${PY_SCRIPT}"
  echo "Aggregation:     ${AGGREGATION}"
  echo "Input root:      ${INPUT_ROOT}"
  echo "Input file:      ${INPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "Clone dir:       ${CLONE_DIR}"
  echo "Language:        ${LANGUAGE_PROFILE}"
  echo "Project prefix:  ${PROJECT_KEY_PREFIX}"
  echo "Output suffix:   ${OUTPUT_SUFFIX}"
  echo "Skip scan:       ${SKIP_SCAN}"
  echo "Num processes:   ${NUM_PROCESSES}"
  echo "Log file:        ${LOG_FILE}"
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
  if [[ "${SKIP_SCAN}" == "true" ]]; then
    echo "** Validate and reuse existing scanned output"
    echo "------------------------------------------------------------"

    if [[ ! -f "${OUTPUT_FILE}" ]]; then
      echo "ERROR: SKIP_SCAN=true but output file not found: ${OUTPUT_FILE}"
      exit 1
    fi

    python - <<PY
import pandas as pd
from pathlib import Path

input_path = Path("${INPUT_FILE}")
output_path = Path("${OUTPUT_FILE}")

input_df = pd.read_csv(input_path)
output_df = pd.read_csv(output_path)

repo_month_cols = ["repo_name", "month"]
match_cols = ["repo_name", "month", "latest_commit"]
required_input = set(match_cols)
missing_input_cols = required_input - set(input_df.columns)
if missing_input_cols:
    raise SystemExit(
        f"ERROR: input missing required columns: {sorted(missing_input_cols)}"
    )

missing_output_cols = set(match_cols) - set(output_df.columns)
if missing_output_cols:
    raise SystemExit(
        f"ERROR: reused output missing matching columns: {sorted(missing_output_cols)}"
    )

metric_candidates = {
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "software_quality_maintainability_remediation_effort",
}

if not metric_candidates.intersection(output_df.columns):
    raise SystemExit("ERROR: reused output contains no SonarQube metric columns.")

input_keys = input_df[match_cols].drop_duplicates()
output_keys = output_df[match_cols].drop_duplicates()

missing_keys = (
    input_keys.merge(output_keys, on=match_cols, how="left", indicator=True)
    .query("_merge == 'left_only'")
)
extra_keys = (
    output_keys.merge(input_keys, on=match_cols, how="left", indicator=True)
    .query("_merge == 'left_only'")
)

duplicate_output_keys = int(output_df.duplicated(repo_month_cols).sum())

print("Input rows:", len(input_df))
print("Output rows:", len(output_df))
print("Input unique repo-month-commit keys:", len(input_keys))
print("Output unique repo-month-commit keys:", len(output_keys))
print("Missing input repo-month-commit keys in output:", len(missing_keys))
print("Extra output repo-month-commit keys:", len(extra_keys))
print("Duplicate output repo-month rows:", duplicate_output_keys)

if len(missing_keys) > 0 or len(extra_keys) > 0 or duplicate_output_keys > 0:
    raise SystemExit(
        "ERROR: reused output does not exactly match the current repo-month-commit input."
    )

print("Existing scanned output is complete for the current input.")
PY

  else
    # Load SonarQube configuration only when an actual scan/API run is needed.
    if [[ -f ".env" ]]; then
      set -a
      source ".env"
      set +a
    fi

    if [[ -z "${SONAR_PATH:-}" && -n "${SONAR_SCANNER_PATH:-}" ]]; then
      export SONAR_PATH="${SONAR_SCANNER_PATH}"
    fi

    if [[ -n "${SONAR_PATH:-}" && -d "${SONAR_PATH}" && -x "${SONAR_PATH}/bin/sonar-scanner" ]]; then
      export SONAR_PATH="${SONAR_PATH}/bin/sonar-scanner"
    fi

    if [[ -z "${SONAR_PATH:-}" ]]; then
      echo "ERROR: SONAR_PATH is not set."
      exit 1
    fi

    if [[ -z "${SONAR_TOKEN:-}" ]]; then
      echo "ERROR: SONAR_TOKEN is not set."
      exit 1
    fi

    if [[ ! -x "${SONAR_PATH}" ]]; then
      echo "ERROR: SONAR_PATH is not executable: ${SONAR_PATH}"
      exit 1
    fi

    export SONAR_PATH
    export SONAR_SCANNER_PATH="${SONAR_PATH}"

    echo "Sonar scanner: ${SONAR_PATH}"
    echo "Sonar token:   set"
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
  fi

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
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:       $(date)"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Target:          ${TARGET}"
  echo "Skip scan:       ${SKIP_SCAN}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9b-sonarqube-jsts.sh,
# but it does NOT call the existing JS/TS shell wrapper.

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/run_sonarqube_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_18__'
#!/usr/bin/env python3
"""
Script to run SonarQube scanner on the latest commits of each week or month.

This script:
1. Reads the time series repository stats from ts_repos_weekly.csv or ts_repos_monthly.csv
2. Optionally builds a one-row target input from REPO_NAME,MONTH,LATEST_COMMIT
3. For each repository and time period, runs SonarQube scanner on the latest commit
4. Collects and stores the analysis results

NOTE: Sometimes the analysis results are not immediately available in database,
so you may have to run this script twice in order to fetch all available metrics
"""

import argparse
import time
import re
import logging
import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import git
import pandas as pd
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Constants
SONAR_PATH = os.getenv("SONAR_PATH") or os.getenv("SONAR_SCANNER_PATH")
SONAR_TOKEN = os.getenv("SONAR_TOKEN")
SONAR_HOST = os.getenv("SONAR_HOST")

# Time key in the time series dataframe
TIME_KEY = None

# Fixed start date for data collection, 2024-01-01 determined by adoption time analysis
START_DATE = "2024-01-01"
END_DATE = "2025-08-31"

# Metrics to collect from SonarQube
METRICS_OF_INTEREST = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "software_quality_maintainability_remediation_effort",  # technical debt
]

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "tmp_sonar_batch" / "data"
CLONE_DIR = SCRIPT_DIR.parent.parent / "CursorRepos"
CONTROL_CLONE_DIR = SCRIPT_DIR.parent.parent / "ControlRepos"

# Number of processes to use for parallel processing
NUM_PROCESSES = 1  # small-batch smoke test

# Taking too long to analyze
REPO_IGNORE = [
    "meshery/meshery",
    "swc-project/swc",
    "djmonkeyuk/nms-base-builder",
    "Azure/azure-rest-api-specs-examples",
]


def check_analysis_exists(project_key: str, version: str) -> bool:
    """
    Check if SonarQube analysis already exists for a project and version.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis

    Returns:
        bool: True if analysis exists, False otherwise
    """
    try:
        page = 1
        while True:
            url = f"{SONAR_HOST}/api/project_analyses/search"
            auth = (SONAR_TOKEN, "")
            params = {
                "project": project_key,
                "category": "VERSION",
                "p": page,
                "ps": 100,  # Page size of 100 analyses
            }

            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()

            data = response.json()
            if "analyses" not in data or not data["analyses"]:
                # No more analyses to check
                break

            for analysis in data["analyses"]:
                if analysis.get("projectVersion") == version:
                    logging.info(
                        "Analysis already exists for %s version %s",
                        project_key,
                        version,
                    )
                    return True

            # Check if we've reached the last page
            if len(data["analyses"]) < 100:
                break

            page += 1

        return False

    except requests.exceptions.RequestException as e:
        logging.error(
            "Failed to check existing analysis for %s: %s", project_key, str(e)
        )
        return False


def build_language_specific_sonar_args(language_profile: str) -> list[str]:
    """Return language-specific SonarScanner CLI arguments.

    Keep this function conservative because run_sonarqube_v2.py is used for
    multiple programming languages.
    """
    profile = (language_profile or "generic").strip().lower()

    common_args = [
        "-Dsonar.sourceEncoding=UTF-8",
        (
            "-Dsonar.exclusions="
            "**/.git/**,"
            "**/__pycache__/**,"
            "**/.venv/**,"
            "**/venv/**,"
            "**/env/**,"
            "**/node_modules/**,"
            "**/dist/**,"
            "**/build/**,"
            "**/.tox/**,"
            "**/.mypy_cache/**,"
            "**/.pytest_cache/**,"
            "**/coverage/**,"
            "**/.next/**,"
            "**/.nuxt/**"
        ),
    ]

    if profile in {"generic", "auto"}:
        return common_args

    if profile in {"python", "py"}:
        return common_args + [
            "-Dsonar.python.version=3.11",
        ]

    if profile in {"python-only", "py-only"}:
        return common_args + [
            "-Dsonar.python.version=3.11",
            "-Dsonar.inclusions=**/*.py",
        ]

    if profile in {"javascript", "typescript", "js", "ts", "js-ts", "jsts"}:
        return common_args + [
            # Keep JS/TS settings conservative. The scanner can usually find
            # tsconfig.json files automatically.
            # "-Dsonar.javascript.maxFileSize=1000",
        ]

    raise ValueError(
        f"Unsupported language profile: {language_profile}. "
        "Use one of: generic, python, python-only, js-ts."
    )


# def run_sonar_scan(
#     repo_path: Path, commit_hash: str, version: str, project_key: str
# ) -> bool:
def run_sonar_scan(
    repo_path: Path, commit_hash: str, version: str, project_key: str, language_profile: str = "generic",
) -> bool:
    """
    Run SonarQube scanner on a specific commit.

    Args:
        repo_path: Path to the repository
        commit_hash: Git commit hash to analyze
        version: Version identifier for the analysis
        project_key: SonarQube project key

    Returns:
        bool: True if scan was successful, False otherwise
    """
    try:
        # Checkout the specific commit
        repo = git.Repo(str(repo_path))
        current = repo.head.commit

        # Force checkout and clean the working directory
        repo.git.reset("--hard")
        repo.git.clean("-fd")
        repo.git.checkout(commit_hash, force=True)

        try:
            # Run sonar-scanner
            # cmd = [
            #     SONAR_PATH,
            #     f"-Dsonar.projectKey={project_key}",
            #     f"-Dsonar.projectName={project_key}",
            #     f"-Dsonar.projectVersion={version}",
            #     "-Dsonar.sources=.",
            #     f"-Dsonar.java.binaries=.",  # Fix Java errors, hopefully we find some .class here
            #     f"-Dsonar.host.url={SONAR_HOST}",
            #     f"-Dsonar.token={SONAR_TOKEN}",
            #     "-Dsonar.scm.disabled=true",  # Disable SCM to speed up analysis
            # ]
            cmd = [
                SONAR_PATH,
                f"-Dsonar.projectKey={project_key}",
                f"-Dsonar.projectName={project_key}",
                f"-Dsonar.projectVersion={version}",
                "-Dsonar.sources=.",
                *build_language_specific_sonar_args(language_profile),
                "-Dsonar.java.binaries=.",
                f"-Dsonar.host.url={SONAR_HOST}",
                f"-Dsonar.token={SONAR_TOKEN}",
                "-Dsonar.scm.disabled=true",
            ]

            subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, check=True
            )
            logging.info("SonarQube scan completed for %s at %s", project_key, version)
            return True

        finally:
            # Always return to original commit
            repo.git.checkout(current)

    except subprocess.CalledProcessError as e:
        logging.error(
            "SonarQube scan failed for %s at %s: %s", project_key, version, e.stderr
        )
        return False
    except Exception as e:
        logging.error("Error during scan of %s at %s: %s", project_key, version, str(e))
        return False


def _find_analysis_date(project_key: str, version: str) -> Optional[str]:
    """
    Find the analysis date for a project's VERSION analysis.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis

    Returns:
        str: Analysis date if found, None otherwise
    """
    analysis_date = None
    page = 1

    while analysis_date is None:
        url = f"{SONAR_HOST}/api/project_analyses/search"
        auth = (SONAR_TOKEN, "")
        params = {
            "project": project_key,
            "category": "VERSION",
            "ps": 100,  # Page size
            "p": page,  # Page number
        }

        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()

        data = response.json()

        logging.info("Found %d analyses for %s", len(data["analyses"]), project_key)

        # Find the analysis with matching version to get its date
        if "analyses" in data and data["analyses"]:
            for analysis in data["analyses"]:
                if analysis.get("projectVersion") == version:
                    analysis_date = analysis.get("date")
                    break

            # If we haven't found the analysis and there are more pages, continue to the next page
            if analysis_date is None and len(data["analyses"]) == 100:
                page += 1
            else:
                break  # No more results or found the analysis
        else:
            break  # No analyses returned

    return analysis_date


def get_sonar_metrics(project_key: str, version: str) -> Optional[Dict]:
    """
    Get metrics from SonarQube API for a project and specific version.

    Only fetches the metrics listed in METRICS_OF_INTEREST. Use
    get_all_sonar_metrics() to fetch every metric available on the
    SonarQube instance instead.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis

    Returns:
        dict: Metrics data or None if request failed
    """
    try:
        analysis_date = _find_analysis_date(project_key, version)

        if not analysis_date:
            logging.warning("No analysis found for %s version %s", project_key, version)
            return None

        # Now get the measures for this specific date using search_history
        auth = (SONAR_TOKEN, "")
        url = f"{SONAR_HOST}/api/measures/search_history"
        params = {
            "component": project_key,
            "metrics": ",".join(METRICS_OF_INTEREST),
            "from": analysis_date,
            "to": analysis_date,
        }

        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()

        data = response.json()
        metrics = {}

        if "measures" in data:
            for measure in data["measures"]:
                if (
                    measure["history"]
                    and len(measure["history"]) > 0
                    and "value" in measure["history"][0]
                ):
                    metrics[measure["metric"]] = float(measure["history"][0]["value"])

        return metrics if metrics else None

    except requests.exceptions.RequestException as e:
        logging.error(
            "Failed to get metrics for %s version %s: %s", project_key, version, str(e)
        )
        return None


def get_all_metric_keys() -> list[str]:
    """
    Fetch the keys of every metric defined on this SonarQube instance.

    Returns:
        list[str]: Metric keys (empty list if the request failed).
    """
    metric_keys: list[str] = []
    page = 1

    try:
        while True:
            url = f"{SONAR_HOST}/api/metrics/search"
            auth = (SONAR_TOKEN, "")
            params = {"ps": 500, "p": page}  # Max page size for this endpoint

            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()

            data = response.json()
            page_metrics = data.get("metrics", [])
            metric_keys.extend(m["key"] for m in page_metrics if "key" in m)

            total = data.get("total", len(metric_keys))
            if not page_metrics or len(metric_keys) >= total:
                break
            page += 1

        return metric_keys

    except requests.exceptions.RequestException as e:
        logging.error("Failed to fetch SonarQube metric definitions: %s", str(e))
        return []


def get_all_sonar_metrics(
    project_key: str, version: str, batch_size: int = 15
) -> Optional[Dict]:
    """
    Get ALL available metrics from SonarQube API for a project and version,
    regardless of METRICS_OF_INTEREST.

    Unlike get_sonar_metrics(), this discovers every metric key defined on
    the SonarQube instance (via /api/metrics/search) and fetches all of
    them. The measures/search_history endpoint only accepts a limited
    number of metric keys per request, so the keys are fetched in batches
    and merged into a single result.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis
        batch_size: Max number of metric keys to request per API call.
            Keep conservative since search_history limits how many metrics
            can be requested at once.

    Returns:
        dict: Metrics data (metric key -> value) or None if no metrics
        could be retrieved. Non-numeric metric values (e.g. rating letters
        or alert statuses) are kept as their raw string values.
    """
    try:
        analysis_date = _find_analysis_date(project_key, version)

        if not analysis_date:
            logging.warning("No analysis found for %s version %s", project_key, version)
            return None

        metric_keys = get_all_metric_keys()       
        logging.info( "metric_keys (%d):\n%s", len(metric_keys), "\n".join(f"  - {k}" for k in metric_keys), )
        
        if not metric_keys:
            logging.warning("No metric definitions found on %s", SONAR_HOST)
            return None

        auth = (SONAR_TOKEN, "")
        url = f"{SONAR_HOST}/api/measures/search_history"
        metrics: Dict = {}

        for i in range(0, len(metric_keys), batch_size):
            batch = metric_keys[i : i + batch_size]
            params = {
                "component": project_key,
                "metrics": ",".join(batch),
                "from": analysis_date,
                "to": analysis_date,
            }

            try:
                response = requests.get(url, auth=auth, params=params)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logging.error(
                    "Failed to get metrics batch %s for %s version %s: %s",
                    batch,
                    project_key,
                    version,
                    str(e),
                )
                continue

            data = response.json()

            if "measures" in data:
                for measure in data["measures"]:
                    if (
                        measure["history"]
                        and len(measure["history"]) > 0
                        and "value" in measure["history"][0]
                    ):
                        raw_value = measure["history"][0]["value"]
                        try:
                            metrics[measure["metric"]] = float(raw_value)
                        except (TypeError, ValueError):
                            # Some metrics (e.g. alert_status, ratings) aren't numeric.
                            metrics[measure["metric"]] = raw_value

        return metrics if metrics else None

    except requests.exceptions.RequestException as e:
        logging.error(
            "Failed to get all metrics for %s version %s: %s", project_key, version, str(e)
        )
        return None


def wait_for_analysis_ready(
    project_key: str,
    version: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
) -> bool:
    """Wait until a SonarQube VERSION analysis appears for the given project/version."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if check_analysis_exists(project_key, version):
            logging.info(
                "SonarQube analysis is ready for %s version %s",
                project_key,
                version,
            )
            return True

        logging.info(
            "Waiting for SonarQube analysis for %s version %s...",
            project_key,
            version,
        )
        time.sleep(poll_interval_seconds)

    logging.warning(
        "Timed out waiting for SonarQube analysis for %s version %s",
        project_key,
        version,
    )
    return False


def process_repository(
    ts_df: pd.DataFrame,
    repo_name: str,
    aggregation: str,
    clone_dir: Path,
    language_profile: str = "generic",
    project_key_prefix: str = "",
    analysis_again: bool = False,
    all_metrics: bool = False,
) -> pd.DataFrame:
    """
    Process a single repository's SonarQube analysis.

    Args:
        ts_df: Time series dataframe.
        repo_name: Name of the repository to process.
        aggregation: Either "week" or "month".
        clone_dir: Directory containing cloned repositories.
        analysis_again: If True, re-run the scan even if an analysis already
            exists for the project/version, and refresh stored metrics.
        all_metrics: If True, fetch every metric available on the SonarQube
            instance (via get_all_sonar_metrics) instead of only the
            METRICS_OF_INTEREST subset (via get_sonar_metrics).

    Returns:
        pd.DataFrame: Updated time series dataframe for this repository.
    """
    # Setup repository info and data.
    base_project_key = repo_name.replace("/", "_")
    project_key = f"{project_key_prefix}{base_project_key}"
    repo_path = Path(clone_dir) / base_project_key

    if not repo_path.exists():
        logging.warning("Repository %s not found at %s", repo_name, repo_path)
        return ts_df[ts_df["repo_name"] == repo_name]

    # Get repository-specific rows.
    repo_df = ts_df[ts_df["repo_name"] == repo_name].copy()

    # Use a single date format string based on aggregation.
    date_format = "%Y-W%W" if aggregation == "week" else "%Y-%m"

    # Get start and end times using the same format.
    start_time = pd.Timestamp(START_DATE).strftime(date_format)
    end_time = pd.Timestamp(END_DATE).strftime(date_format)

    logging.info("Processing %s from %s to %s", repo_name, start_time, end_time)

    # Process each time period's latest commit in chronological order.
    time_periods = sorted(
        repo_df[
            (repo_df[TIME_KEY].astype(str) >= start_time)
            & (repo_df[TIME_KEY].astype(str) <= end_time)
        ][TIME_KEY].unique()
    )

    for time_period in time_periods:
        row_idx = repo_df[repo_df[TIME_KEY] == time_period].index[0]
        commit_hash = repo_df.loc[row_idx, "latest_commit"]

        # Handle missing or invalid commit hashes robustly.
        if pd.isna(commit_hash) or not str(commit_hash).strip():
            logging.warning("No commit hash for %s at %s", repo_name, time_period)
            continue

        commit_hash = str(commit_hash).strip()
        time_period = str(time_period).strip()

        analysis_exists = check_analysis_exists(project_key, time_period)

        if analysis_exists and analysis_again:
            logging.info(
                "Analysis already exists for %s at %s, but --analysis-again was "
                "set; re-running scan.",
                repo_name,
                time_period,
            )
            analysis_exists = False

        if not analysis_exists:
            logging.info("%s at %s (%s)", repo_name, time_period, commit_hash[:8])

            scan_result = run_sonar_scan(
                repo_path, commit_hash, time_period, project_key, language_profile,
            )

            # Some versions of run_sonar_scan may return None on success.
            # Treat only explicit False as failure.
            if scan_result is False:
                logging.warning(
                    "Skipping metrics because SonarQube scan failed for %s at %s",
                    repo_name,
                    time_period,
                )
                continue

            # SonarScanner returns after uploading the report, but SonarQube's
            # Compute Engine may need time before the VERSION analysis appears.
            ready = wait_for_analysis_ready(
                project_key=project_key,
                version=time_period,
                timeout_seconds=120,
                poll_interval_seconds=5,
            )

            if not ready:
                logging.warning(
                    "Skipping metrics because analysis was not ready for %s at %s",
                    repo_name,
                    time_period,
                )
                continue

        # Get and store metrics.
        # Use get_all_sonar_metrics() when the caller wants every metric
        # available on the SonarQube instance; otherwise fall back to the
        # METRICS_OF_INTEREST-only get_sonar_metrics().
        if all_metrics:
            metrics = get_all_sonar_metrics(project_key, time_period)
        else:
            metrics = get_sonar_metrics(project_key, time_period)

        if metrics:
            for metric, value in metrics.items():
                # New columns (e.g. metrics outside METRICS_OF_INTEREST) are
                # created automatically on assignment if they don't exist yet.
                repo_df.loc[row_idx, metric] = value

            logging.info("Metrics for %s at %s: %s", repo_name, time_period, metrics)
        else:
            logging.warning("No metrics returned for %s at %s", repo_name, time_period)

    return repo_df



def infer_date_range_from_input(ts_df: pd.DataFrame, time_key: str) -> tuple[str, str]:
    """Infer START_DATE and END_DATE from the input time-series file."""
    if time_key not in ts_df.columns:
        raise ValueError(f"Missing time column: {time_key}")

    values = (
        ts_df[time_key]
        .dropna()
        .astype(str)
        .str.strip()
    )

    if values.empty:
        raise ValueError(f"No valid values found in time column: {time_key}")

    # Accept both YYYY-MM and YYYYMM formats, but normalize to YYYY-MM.
    normalized = []
    for value in values:
        if re.fullmatch(r"\d{6}", value):
            normalized.append(f"{value[:4]}-{value[4:]}")
        elif re.fullmatch(r"\d{4}-\d{2}", value):
            normalized.append(value)
        else:
            raise ValueError(
                f"Unsupported time value format in {time_key}: {value}. "
                "Expected YYYY-MM or YYYYMM."
            )

    return min(normalized), max(normalized)



def build_target_timeseries_input(
    target_spec: str,
    aggregation: str,
) -> pd.DataFrame:
    """Build a one-row SonarQube input from a CLI target specification.

    The target format is REPO_NAME,MONTH,LATEST_COMMIT. Repository names may
    use either OWNER/REPO or the local clone-directory form OWNER_REPO. The
    slash form is recommended because it matches the pipeline CSV convention.
    """
    if aggregation != "month":
        raise ValueError(
            "Target mode currently supports monthly analysis only. "
            "Use --aggregation month."
        )

    parts = [part.strip() for part in str(target_spec).split(",", 2)]
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError(
            "Invalid --target value. Expected "
            "REPO_NAME,MONTH,LATEST_COMMIT."
        )

    repo_name, month, latest_commit = parts

    if re.fullmatch(r"\d{6}", month):
        month = f"{month[:4]}-{month[4:]}"

    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError(
            f"Invalid target month: {month}. Expected YYYY-MM or YYYYMM."
        )

    try:
        parsed_month = pd.Period(month, freq="M")
    except ValueError as exc:
        raise ValueError(f"Invalid target month: {month}.") from exc

    normalized_month = str(parsed_month)

    if not re.fullmatch(r"[0-9a-fA-F]{40}", latest_commit):
        raise ValueError(
            "Invalid target commit. Expected a full 40-character Git SHA."
        )

    return pd.DataFrame(
        [
            {
                "repo_name": repo_name,
                "month": normalized_month,
                "latest_commit": latest_commit.lower(),
            }
        ]
    )


def save_progress(
    full_df: pd.DataFrame,
    processed_results: list[pd.DataFrame],
    output_file: Path,
    time_key: str,
) -> None:
    """Save partial SonarQube metrics after completed repositories.

    The saved file contains all original rows. Rows for completed repositories
    are replaced with their updated metric values; rows for unprocessed
    repositories remain present with missing metric values.
    """
    if processed_results:
        processed_df = pd.concat(processed_results, ignore_index=True)
        processed_repos = set(processed_df["repo_name"].unique())
        remaining_df = full_df[~full_df["repo_name"].isin(processed_repos)].copy()
        save_df = pd.concat([processed_df, remaining_df], ignore_index=True)
    else:
        save_df = full_df.copy()

    if "technical_debt" in save_df.columns:
        save_df.drop(columns=["technical_debt"], inplace=True)

    save_df.rename(
        columns={
            "software_quality_maintainability_remediation_effort": "technical_debt"
        },
        inplace=True,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    save_df.sort_values(by=["repo_name", time_key]).to_csv(output_file, index=False)
    logging.info("Progress saved to %s", output_file)



def main() -> None:
    """Main function to run SonarQube analysis on repositories."""
    global TIME_KEY
    parser = argparse.ArgumentParser(
        description="Run SonarQube analysis on repository commits with weekly or monthly aggregation."
    )
    parser.add_argument(
        "--aggregation",
        choices=["week", "month"],
        default="week",
        help="Aggregate data by week or month (default: week)",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="Run analysis on control repositories instead of experimental ones",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=(
            "Directory containing ts_repos_monthly.csv or ts_repos_weekly.csv. "
            "Default: %(default)s"
        ),
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help=(
            "Explicit input time-series CSV. "
            "If provided, this overrides --data-dir and --control file-name selection."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help=(
            "Output CSV path. Default: overwrite the selected input file."
        ),
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing cloned repositories. "
            "Default: treatment clone dir, or control clone dir when --control is used."
        ),
    )
    parser.add_argument(
        "--num-processes",
        type=int,
        default=NUM_PROCESSES,
        help="Number of worker processes. Default: %(default)s",
    )
    parser.add_argument(
        "--incremental-save",
        action="store_true",
        help=(
            "Save the output CSV after each completed repository. "
            "Recommended for long full scans."
        ),
    )
    parser.add_argument(
        "--analysis-again",
        action="store_true",
        help=(
            "Run the SonarQube scan again even if an analysis already exists "
            "for the project/version, and refresh the stored metrics."
        ),
    )
    parser.add_argument(
        "--analysis-all-metrics",
        action="store_true",
        help=("Run the SonarQube scan to get all metrics."),
    )
    parser.add_argument(
        "--language-profile",
        choices=[
            "generic",
            "auto",
            "python",
            "py",
            "python-only",
            "py-only",
            "js-ts",
            "jsts",
            "javascript",
            "typescript",
            "js",
            "ts",
        ],
        default="generic",
        help=(
            "Language-specific SonarQube scanner settings. "
            "Use 'python-only' to scan only **/*.py files, 'python' for the "
            "existing Python-primary whole-repository behavior, 'js-ts' for "
            "JavaScript/TypeScript repos, or 'generic' for language-neutral scans."
        ),
    )

    parser.add_argument(
        "--target",
        default=None,
        metavar="REPO_NAME,MONTH,LATEST_COMMIT",
        help=(
            "Analyze one monthly repo-commit target without an input CSV. "
            "Example: Anemll/Anemll,2025-02,"
            "d3b2e3660c0657ab643b68a0513b4b5ab443c04c. "
            "Target mode uses Python-only scanning and requires --output-file."
        ),
    )

    parser.add_argument(
        "--project-key-prefix",
        default="",
        help=(
            "Optional prefix added to SonarQube project keys. "
            "Use this for from-scratch rescans without deleting existing SonarQube projects, "
            "for example: pyv2_."
        ),
    )

    args = parser.parse_args()

    if args.target is not None:
        if args.aggregation != "month":
            parser.error("--target requires --aggregation month.")
        if args.input_file is not None:
            parser.error("--target cannot be combined with --input-file.")
        if args.output_file is None:
            parser.error("--target requires --output-file.")
        if args.language_profile in {"js-ts", "jsts", "javascript", "typescript", "js", "ts"}:
            parser.error("--target is reserved for Python-only validation.")

        # Keep the previous whole-repository Python profile unchanged.
        args.language_profile = "python-only"

        # Avoid reusing an existing whole-repository project/version analysis.
        if not args.project_key_prefix:
            args.project_key_prefix = "pyonly_"

    TIME_KEY = "week" if args.aggregation == "week" else "month"

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if not SONAR_PATH or not SONAR_TOKEN:
        logging.error("SONAR_PATH and SONAR_TOKEN must be set in .env file")
        return

    # Set input/output file paths.
    data_dir = Path(args.data_dir).expanduser().resolve()

    if args.clone_dir is not None:
        clone_dir = Path(args.clone_dir).expanduser().resolve()
    else:
        clone_dir = CONTROL_CLONE_DIR if args.control else CLONE_DIR

    if args.target is not None:
        ts_repos_file = None
        output_file = Path(args.output_file).expanduser().resolve()
        try:
            ts_df = build_target_timeseries_input(args.target, args.aggregation)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        logging.info("Using data directory: %s", data_dir)

        if args.input_file is not None:
            ts_repos_file = Path(args.input_file).expanduser().resolve()
        else:
            file_prefix = "ts_repos_control_" if args.control else "ts_repos_"
            ts_repos_file = data_dir / f"{file_prefix}{args.aggregation}ly.csv"

        if args.output_file is not None:
            output_file = Path(args.output_file).expanduser().resolve()
        else:
            output_file = ts_repos_file

        try:
            ts_df = pd.read_csv(ts_repos_file)
        except FileNotFoundError as exc:
            logging.error("Required file not found: %s", exc)
            return

    global START_DATE, END_DATE
    START_DATE, END_DATE = infer_date_range_from_input(ts_df, TIME_KEY)

    if ts_repos_file is not None:
        logging.info("Using input file: %s", ts_repos_file)
    else:
        logging.info("Using target specification: %s", args.target)

    logging.info("Using output file: %s", output_file)
    logging.info("Using clone directory: %s", clone_dir)
    logging.info("Using num processes: %s", args.num_processes)
    logging.info("Using language profile: %s", args.language_profile)
    logging.info("Using project key prefix: %s", args.project_key_prefix)
    logging.info("Re-run existing analyses: %s", args.analysis_again)
    logging.info("Fetch all metrics (ignore METRICS_OF_INTEREST): %s", args.analysis_all_metrics)
    logging.info("Using input-derived date range: %s to %s", START_DATE, END_DATE)

    # Create columns for metrics if they don't exist
    for col in METRICS_OF_INTEREST:
        if col not in ts_df.columns:
            ts_df[col] = None

    # Get unique repository names.
    repo_names = sorted(set(ts_df["repo_name"].unique()) - set(REPO_IGNORE))

    args_list = [
        (
            ts_df,
            repo_name,
            args.aggregation,
            clone_dir,
            args.language_profile,
            args.project_key_prefix,
            args.analysis_again,
            args.analysis_all_metrics,
        )
        for repo_name in repo_names
    ]

    results: list[pd.DataFrame] = []

    if args.incremental_save or args.num_processes == 1:
        logging.info("Using repo-level incremental save mode")

        try:
            for i, repo_args in enumerate(args_list, start=1):
                repo_name = repo_args[1]
                logging.info(
                    "Incremental progress: repository %d/%d: %s",
                    i,
                    len(args_list),
                    repo_name,
                )

                repo_result = process_repository(*repo_args)
                results.append(repo_result)

                save_progress(
                    full_df=ts_df,
                    processed_results=results,
                    output_file=output_file,
                    time_key=TIME_KEY,
                )

        except KeyboardInterrupt:
            logging.warning("Interrupted by user; saving partial progress")
            save_progress(
                full_df=ts_df,
                processed_results=results,
                output_file=output_file,
                time_key=TIME_KEY,
            )
            raise

    else:
        logging.info("Using multiprocessing mode without incremental save")

        with mp.Pool(args.num_processes) as pool:
            results = pool.starmap(process_repository, args_list, chunksize=1)

        save_progress(
            full_df=ts_df,
            processed_results=results,
            output_file=output_file,
            time_key=TIME_KEY,
        )

    logging.info("Updated metrics saved to %s", output_file)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_18__


###############################################################################
# -- SHELL SCRIPT: run-py-2c-merge-sonarqube-panel.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2c: Merge Python SonarQube metrics into matched DiD panels
# ============================================================
#
# Purpose:
#   Merge treatment/control SonarQube metrics generated by run-py-2b
#   into the final Python matched event panels generated by run-py-1l.
#
# Inputs:
#   repo_python/run-py-1l/panel_event_matched_<variant>.csv
#   repo_python/run-py-2b/<variant>/treatment/ts_repos_monthly_scanned.csv
#   repo_python/run-py-2b/<variant>/control/ts_repos_monthly_scanned.csv
#
# Main output:
#   repo_python/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube.csv
#
# Extra QC output:
#   repo_python/tmp/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube_qc.csv
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2c-merge-sonarqube-panel.sh
#   PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh
# 
# 
# PANEL_VARIANT=strict \
# TREATMENT_METRICS=repo_python/run-py-2b/strict/treatment/ts_repos_monthly_scanned_python_only.csv \
# CONTROL_METRICS=repo_python/run-py-2b/strict/control/ts_repos_monthly_scanned_python_only.csv \
# OUTPUT_FILE=repo_python/run-py-2c/strict/panel_event_matched_strict_with_sonarqube_python_only.csv \
# QC_OUTPUT_FILE=repo_python/tmp/run-py-2c/strict/panel_event_matched_strict_with_sonarqube_python_only_qc.csv \
# bash run-py-2c-merge-sonarqube-panel.sh
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

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "strict" ]]; then
  echo "ERROR: PANEL_VARIANT must be either flexible or strict. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_merge_sonarqube_panel_${PANEL_VARIANT}_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/merge_sonarqube_panel_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-1l}"
SONAR_ROOT="${SONAR_ROOT:-${OUTPUT_BASE_DIR}/run-py-2b/${PANEL_VARIANT}}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}/${PANEL_VARIANT}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}/${PANEL_VARIANT}}"

PANEL_FILE="${PANEL_FILE:-${PANEL_INPUT_DIR}/panel_event_matched_${PANEL_VARIANT}.csv}"

TREATMENT_METRICS="${TREATMENT_METRICS:-${SONAR_ROOT}/treatment/ts_repos_monthly_scanned.csv}"
CONTROL_METRICS="${CONTROL_METRICS:-${SONAR_ROOT}/control/ts_repos_monthly_scanned.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-${MAIN_OUTPUT_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube.csv}"
QC_OUTPUT_FILE="${QC_OUTPUT_FILE:-${TMP_DIR}/panel_event_matched_${PANEL_VARIANT}_with_sonarqube_qc.csv}"

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: merge Python SonarQube metrics into matched panel"
  echo "Started:           $(date)"
  echo "Script name:       ${SCRIPT_NAME}"
  echo "Run prefix:        ${RUN_PREFIX}"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Python script:     ${PY_SCRIPT}"
  echo "Panel input dir:   ${PANEL_INPUT_DIR}"
  echo "Sonar root:        ${SONAR_ROOT}"
  echo "Main output dir:   ${MAIN_OUTPUT_DIR}"
  echo "Extra QC dir:      ${TMP_DIR}"
  echo "Panel file:        ${PANEL_FILE}"
  echo "Treatment metrics: ${TREATMENT_METRICS}"
  echo "Control metrics:   ${CONTROL_METRICS}"
  echo "Output file:       ${OUTPUT_FILE}"
  echo "QC output file:    ${QC_OUTPUT_FILE}"
  echo "Log file:          ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in "${PY_SCRIPT}" "${PANEL_FILE}" "${TREATMENT_METRICS}" "${CONTROL_METRICS}"; do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      echo
      echo "Make sure run-py-1l and both run-py-2b scans are complete"
      echo "for PANEL_VARIANT=${PANEL_VARIANT}."
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

print("Updated output:", output)
print("Updated QC:", qc_output)
print()
print(new_checks.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:       $(date)"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Output file:     ${OUTPUT_FILE}"
  echo "QC output file:  ${QC_OUTPUT_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Extra QC dir:    ${TMP_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9c-merge-sonarqube-panel.sh,
# but it does NOT call the existing JS/TS shell wrapper.

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/merge_sonarqube_panel_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_19__'
#!/usr/bin/env python3
"""
Merge SonarQube metrics into monthly DiD panels.

This script:
1. Loads a treatment-control panel.
2. Loads treatment and control SonarQube scanned outputs.
3. Merges SonarQube metrics by repo_name, time/month, and dataset_source.
4. Preserves raw SonarQube metrics as *_raw columns.
5. Creates analysis-ready quality outcomes.
6. Adds QC flags for missing metrics and ncloc == 0 rows.
7. Writes a QC summary CSV.

Important policy:
- Do not impute missing SonarQube quality metrics.
- Do not drop rows with missing metrics.
- Do not drop rows where ncloc == 0.
- Keep missing scanner failures as missing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd


METRIC_COLS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]

RAW_METRIC_COLS = [f"{col}_raw" for col in METRIC_COLS]


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge SonarQube metrics into a monthly DiD panel."
    )
    parser.add_argument("--panel", required=True, help="Input panel CSV path.")
    parser.add_argument(
        "--treatment-metrics",
        required=True,
        help="Treatment SonarQube scanned CSV path.",
    )
    parser.add_argument(
        "--control-metrics",
        required=True,
        help="Control SonarQube scanned CSV path.",
    )
    parser.add_argument("--output", required=True, help="Output merged panel CSV path.")
    parser.add_argument("--qc-output", required=True, help="Output QC summary CSV path.")
    return parser.parse_args()


def read_csv_checked(path: Path, label: str) -> pd.DataFrame:
    """Read a CSV file and fail clearly if it does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")

    logging.info("Loading %s: %s", label, path)
    df = pd.read_csv(path)
    logging.info("Loaded %s rows: %d", label, len(df))
    return df


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Validate required columns."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def normalize_technical_debt_column(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize SonarQube technical debt column name."""
    df = df.copy()
    long_name = "software_quality_maintainability_remediation_effort"

    if "technical_debt" not in df.columns and long_name in df.columns:
        df = df.rename(columns={long_name: "technical_debt"})

    if "technical_debt" in df.columns and long_name in df.columns:
        df["technical_debt"] = df["technical_debt"].combine_first(df[long_name])

    return df


def prepare_metrics(df: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    """Prepare treatment/control SonarQube metrics for panel merge."""
    df = normalize_technical_debt_column(df)

    require_columns(
        df,
        {"repo_name", "month", "latest_commit"} | set(METRIC_COLS),
        f"{dataset_source} metrics",
    )

    df = df.copy()
    df["repo_name"] = df["repo_name"].astype(str)
    df["time"] = df["month"].astype(str)
    df["dataset_source"] = dataset_source

    keep_cols = ["repo_name", "time", "dataset_source", "latest_commit"] + METRIC_COLS
    df = df[keep_cols].copy()

    duplicate_count = int(df.duplicated(["repo_name", "time", "dataset_source"]).sum())
    if duplicate_count:
        logging.warning(
            "%s metrics has %d duplicate repo-time-source rows; keeping first",
            dataset_source,
            duplicate_count,
        )

    df = df.drop_duplicates(["repo_name", "time", "dataset_source"], keep="first")

    rename_map = {"latest_commit": "sonarqube_latest_commit"}
    for col in METRIC_COLS:
        rename_map[col] = f"{col}_raw"

    prepared = df.rename(columns=rename_map)

    logging.info(
        "Prepared %s metrics: rows=%d, repos=%d, months=%s to %s",
        dataset_source,
        len(prepared),
        prepared["repo_name"].nunique(),
        prepared["time"].min(),
        prepared["time"].max(),
    )

    return prepared


def merge_panel_with_metrics(
    panel: pd.DataFrame,
    treatment_metrics: pd.DataFrame,
    control_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Merge panel with treatment/control SonarQube metrics."""
    require_columns(panel, {"repo_name", "time", "dataset_source"}, "panel")

    panel = panel.copy()
    panel["repo_name"] = panel["repo_name"].astype(str)
    panel["time"] = panel["time"].astype(str)
    panel["dataset_source"] = panel["dataset_source"].astype(str)

    prepared_metrics = pd.concat(
        [
            prepare_metrics(treatment_metrics, "treatment"),
            prepare_metrics(control_metrics, "control"),
        ],
        ignore_index=True,
    )

    before_rows = len(panel)
    logging.info("Merging SonarQube metrics into panel")

    merged = panel.merge(
        prepared_metrics,
        on=["repo_name", "time", "dataset_source"],
        how="left",
        validate="one_to_one",
    )

    if len(merged) != before_rows:
        raise ValueError(f"Row count changed after merge: {before_rows} -> {len(merged)}")

    logging.info("Merged panel rows: %d", len(merged))
    return merged


def add_analysis_ready_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Create analysis-ready quality outcomes and QC flags."""
    df = df.copy()
    require_columns(df, set(RAW_METRIC_COLS), "merged panel")

    for col in METRIC_COLS:
        df[col] = df[f"{col}_raw"]

    df["static_analysis_warnings"] = (
        df["bugs_raw"] + df["vulnerabilities_raw"] + df["code_smells_raw"]
    )
    df["duplicate_line_density"] = df["duplicated_lines_density_raw"]
    df["code_complexity"] = df["cognitive_complexity_raw"]

    valid_ncloc = df["ncloc_raw"].notna() & (df["ncloc_raw"] > 0)

    df["warnings_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "warnings_per_kloc"] = (
        df.loc[valid_ncloc, "static_analysis_warnings"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["complexity_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "complexity_per_kloc"] = (
        df.loc[valid_ncloc, "code_complexity"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["code_smells_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "code_smells_per_kloc"] = (
        df.loc[valid_ncloc, "code_smells_raw"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["sonarqube_any_raw_metric_missing"] = df[RAW_METRIC_COLS].isna().any(axis=1).astype(int)
    df["sonarqube_all_raw_metrics_missing"] = df[RAW_METRIC_COLS].isna().all(axis=1).astype(int)

    df["sonarqube_ncloc_zero"] = (
        df["ncloc_raw"].notna() & (df["ncloc_raw"] == 0)
    ).astype(int)

    df["sonarqube_static_warnings_missing"] = (
        df[["bugs_raw", "vulnerabilities_raw", "code_smells_raw"]]
        .isna()
        .any(axis=1)
    ).astype(int)

    df["sonarqube_duplicate_density_missing"] = (
        df["duplicated_lines_density_raw"].isna().astype(int)
    )

    df["sonarqube_cognitive_complexity_missing"] = (
        df["cognitive_complexity_raw"].isna().astype(int)
    )

    df["sonarqube_quality_outcomes_complete"] = (
        (df["sonarqube_static_warnings_missing"] == 0)
        & (df["sonarqube_duplicate_density_missing"] == 0)
        & (df["sonarqube_cognitive_complexity_missing"] == 0)
    ).astype(int)

    return df


def build_qc(panel: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Build QC summary dataframe."""
    rows = []

    def add(check: str, value) -> None:
        rows.append({"check": check, "value": value})

    add("input_panel_rows", len(panel))
    add("merged_rows", len(merged))
    add("row_count_preserved", int(len(panel) == len(merged)))

    add("repos", merged["repo_name"].nunique())
    add("treatment_rows", int((merged["dataset_source"] == "treatment").sum()))
    add("control_rows", int((merged["dataset_source"] == "control").sum()))
    add(
        "treatment_repos",
        merged.loc[merged["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add(
        "control_repos",
        merged.loc[merged["dataset_source"] == "control", "repo_name"].nunique(),
    )
    add("min_time", merged["time"].min())
    add("max_time", merged["time"].max())

    add(
        "duplicate_repo_time_source_rows",
        int(merged.duplicated(["repo_name", "time", "dataset_source"]).sum()),
    )
    add("missing_sonarqube_latest_commit", int(merged["sonarqube_latest_commit"].isna().sum()))

    for col in RAW_METRIC_COLS:
        add(f"{col}_nonmissing", int(merged[col].notna().sum()))
        add(f"{col}_missing", int(merged[col].isna().sum()))

    for col in [
        "static_analysis_warnings",
        "duplicate_line_density",
        "code_complexity",
        "warnings_per_kloc",
        "complexity_per_kloc",
        "code_smells_per_kloc",
    ]:
        add(f"{col}_nonmissing", int(merged[col].notna().sum()))
        add(f"{col}_missing", int(merged[col].isna().sum()))

    for flag in [
        "sonarqube_any_raw_metric_missing",
        "sonarqube_all_raw_metrics_missing",
        "sonarqube_ncloc_zero",
        "sonarqube_static_warnings_missing",
        "sonarqube_duplicate_density_missing",
        "sonarqube_cognitive_complexity_missing",
        "sonarqube_quality_outcomes_complete",
    ]:
        add(f"{flag}_sum", int(merged[flag].sum()))

    return pd.DataFrame(rows)


def main() -> int:
    """Run the merge."""
    setup_logging()
    args = parse_args()

    panel_path = Path(args.panel)
    treatment_path = Path(args.treatment_metrics)
    control_path = Path(args.control_metrics)
    output_path = Path(args.output)
    qc_output_path = Path(args.qc_output)

    panel = read_csv_checked(panel_path, "panel")
    treatment_metrics = read_csv_checked(treatment_path, "treatment metrics")
    control_metrics = read_csv_checked(control_path, "control metrics")

    merged = merge_panel_with_metrics(panel, treatment_metrics, control_metrics)
    merged = add_analysis_ready_metrics(merged)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_output_path.parent.mkdir(parents=True, exist_ok=True)

    merged.to_csv(output_path, index=False)
    logging.info("Saved merged panel: %s", output_path)

    qc = build_qc(panel, merged)
    qc.to_csv(qc_output_path, index=False)
    logging.info("Saved QC summary: %s", qc_output_path)

    logging.info("QC summary:")
    logging.info("\n%s", qc.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_19__

###############################################################################
# -- SHELL SCRIPT: run-py-2d-check-sonarqube-panels.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2d: Check Python merged SonarQube matched panels
# ============================================================
#
# Purpose:
#   Check merged Python SonarQube panels created by run-py-2c.
#
# Inputs:
#   strict:
#     repo_python/run-py-2c/strict/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/run-py-2c/flexible/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=all bash run-py-2d-check-sonarqube-panels.sh
#   OUTPUT_SUFFIX=python_only PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#
# Persistent output:
#   logs/run-py-2d_check_sonarqube_panels_<variant>_<timestamp>.log
#
# Temporary outputs:
#   check_sonarqube_panel.py requires summary and missing-row files.
#   They are created under repo_python/tmp/run-py-2d during validation
#   and removed automatically when the wrapper exits.
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

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

if [[ -n "${OUTPUT_SUFFIX}" && ! "${OUTPUT_SUFFIX}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERROR: OUTPUT_SUFFIX must contain only letters, numbers, and underscores. Got: ${OUTPUT_SUFFIX}"
  exit 1
fi

FILE_SUFFIX=""
LOG_SUFFIX=""
if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  FILE_SUFFIX="_${OUTPUT_SUFFIX}"
  LOG_SUFFIX="_${OUTPUT_SUFFIX}"
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_check_sonarqube_panels_${PANEL_VARIANT}${LOG_SUFFIX}_${RUN_TS}.log}"

CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
TMP_PARENT_DIR="${TMP_PARENT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
TMP_WORK_DIR="${TMP_WORK_DIR:-${TMP_PARENT_DIR}/${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}}"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube${FILE_SUFFIX}.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube${FILE_SUFFIX}.csv")
fi

cleanup_tmp_work_dir() {
  rm -rf "${TMP_WORK_DIR}"
  rmdir "${TMP_PARENT_DIR}" 2>/dev/null || true
}
trap cleanup_tmp_work_dir EXIT

mkdir -p "${LOG_DIR}" "${TMP_WORK_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: check Python merged SonarQube panels"
  echo "Started:          $(date)"
  echo "Script name:      ${SCRIPT_NAME}"
  echo "Run prefix:       ${RUN_PREFIX}"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Output suffix:    ${OUTPUT_SUFFIX:-<none>}"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "Panel input dir:  ${PANEL_INPUT_DIR}"
  echo "Temporary dir:    ${TMP_WORK_DIR}"
  echo "Persistent files: log only"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${CHECK_SCRIPT}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "Complete run-py-2c first for PANEL_VARIANT=${PANEL_LABEL}."
      exit 1
    fi

    SUMMARY_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_check_summary.csv"
    MISSING_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_missing_analysis_outcomes.csv"

    echo
    echo "============================================================"
    echo "Checking panel: ${PANEL_LABEL}"
    echo "Input:          ${INPUT_FILE}"
    echo "Temporary summary: ${SUMMARY_OUTPUT}"
    echo "Temporary missing: ${MISSING_OUTPUT}"
    echo "============================================================"

    python "${CHECK_SCRIPT}" \
      --input "${INPUT_FILE}" \
      --summary-output "${SUMMARY_OUTPUT}" \
      --missing-output "${MISSING_OUTPUT}"

    echo
    echo "Validation completed for ${PANEL_LABEL}."
    echo "Temporary checker outputs will be removed when the wrapper exits."
  done

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:         $(date)"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Output suffix:     ${OUTPUT_SUFFIX:-<none>}"
  echo "Persistent output: ${LOG_FILE}"
  echo "Temporary outputs: removed automatically"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9d-check-sonarqube-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.

###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/check_sonarqube_panel.py --
###############################################################################

: <<'__MERGED_PYTHON_20__'
#!/usr/bin/env python3
"""Sanity-check merged SonarQube panels from run9c."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]

RAW_METRIC_COLS = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

ANALYSIS_OUTCOME_COLS = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
    "warnings_per_kloc",
    "complexity_per_kloc",
    "code_smells_per_kloc",
]

CORE_DID_OUTCOME_COLS = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
]

QC_FLAG_COLS = [
    "sonarqube_any_raw_metric_missing",
    "sonarqube_all_raw_metrics_missing",
    "sonarqube_ncloc_zero",
    "sonarqube_static_warnings_missing",
    "sonarqube_duplicate_density_missing",
    "sonarqube_cognitive_complexity_missing",
    "sonarqube_quality_outcomes_complete",
]

EVENT_COLS = [
    "ever_treated",
    "is_treatment",
    "post_event",
    "time_to_event",
]

EXTRA_COLS = [
    "sonarqube_latest_commit",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check merged SonarQube panel from run9c."
    )
    parser.add_argument("--input", required=True, help="Merged panel CSV path.")
    parser.add_argument("--summary-output", required=True, help="Summary CSV path.")
    parser.add_argument("--missing-output", required=True, help="Missing rows CSV path.")
    return parser.parse_args()


def nonmissing_count(df: pd.DataFrame, col: str) -> int | None:
    if col not in df.columns:
        return None
    return int(df[col].notna().sum())


def missing_count(df: pd.DataFrame, col: str) -> int | None:
    if col not in df.columns:
        return None
    return int(df[col].isna().sum())


def numeric_summary(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {
            "metric": col,
            "exists": 0,
            "nonmissing": None,
            "missing": None,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "zero_count": None,
        }

    x = pd.to_numeric(df[col], errors="coerce")

    return {
        "metric": col,
        "exists": 1,
        "nonmissing": int(x.notna().sum()),
        "missing": int(x.isna().sum()),
        "mean": x.mean(),
        "median": x.median(),
        "min": x.min(),
        "max": x.max(),
        "zero_count": int((x == 0).sum()),
    }


def print_coverage(df: pd.DataFrame, cols: list[str], title: str) -> None:
    print(title)
    for col in cols:
        if col in df.columns:
            print(f"{col}: {df[col].notna().sum()} / {len(df)}")
        else:
            print(f"{col}: MISSING")
    print()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    summary_path = Path(args.summary_output)
    missing_path = Path(args.missing_output)

    df = pd.read_csv(input_path)

    print("=" * 72)
    print("Merged SonarQube panel sanity check")
    print("=" * 72)
    print("input:", input_path)
    print("rows:", len(df))

    if "repo_name" in df.columns:
        print("repos:", df["repo_name"].nunique())
    else:
        print("repos: MISSING repo_name column")

    if "time" in df.columns:
        print("months:", df["time"].min(), "to", df["time"].max())
    else:
        print("months: MISSING time column")

    print()

    if "dataset_source" in df.columns:
        print("Rows by dataset_source:")
        print(df["dataset_source"].value_counts(dropna=False).to_string())
    else:
        print("Rows by dataset_source: MISSING dataset_source column")
    print()

    if set(KEY_COLS).issubset(df.columns):
        duplicated_keys = int(df.duplicated(KEY_COLS).sum())
        print("duplicated repo-month-source keys:", duplicated_keys)
    else:
        duplicated_keys = None
        print("duplicated key check skipped: missing key columns")
    print()

    print_coverage(df, EVENT_COLS, "Event column coverage:")
    print_coverage(df, EXTRA_COLS, "SonarQube commit column coverage:")
    print_coverage(df, RAW_METRIC_COLS, "Raw metric coverage:")
    print_coverage(df, ANALYSIS_OUTCOME_COLS, "Analysis-ready outcome coverage:")
    print_coverage(df, QC_FLAG_COLS, "QC flag coverage:")

    summary_cols = RAW_METRIC_COLS + ANALYSIS_OUTCOME_COLS + QC_FLAG_COLS
    summary_rows = [numeric_summary(df, col) for col in summary_cols]
    summary = pd.DataFrame(summary_rows)

    print("Metric and QC summary:")
    print(summary.to_string(index=False))
    print()

    existing_core_cols = [c for c in CORE_DID_OUTCOME_COLS if c in df.columns]
    if existing_core_cols:
        missing = df[df[existing_core_cols].isna().any(axis=1)].copy()
    else:
        missing = df.copy()

    print("Rows with missing core DiD quality outcomes:", len(missing))

    if len(missing):
        show_cols = [
            c
            for c in KEY_COLS
            + EXTRA_COLS
            + CORE_DID_OUTCOME_COLS
            + QC_FLAG_COLS
            if c in missing.columns
        ]
        print(missing[show_cols].head(50).to_string(index=False))

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(summary_path, index=False)
    missing.to_csv(missing_path, index=False)

    print()
    print("saved summary:", summary_path)
    print("saved missing rows:", missing_path)


if __name__ == "__main__":
    main()

__MERGED_PYTHON_20__

###############################################################################
# -- SHELL SCRIPT: run-py-2e-prepare-quality-did-input.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2e: Prepare Python quality DiD input
# ============================================================
# Purpose:
#   Convert merged Python SonarQube panels into quality DiD inputs.
#   Optionally create a paper-schema diagnostic output without calling
#   compare/run-py-2b15-create-paper-structure-panel.sh.
#
# Input:
#   repo_python/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube.csv
#
# Main output for the strict paper-overlap run:
#   repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv
#
# Main output for flexible or non-paper runs:
#   repo_python/run-py-2e/<variant>/
#     panel_event_matched_<variant>_with_sonarqube_quality_did_input_complete.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-2e/<variant>/quality_did_input_qc.csv
#   repo_python/tmp/run-py-2e/<variant>/paper_audit/
#
# Temporary outputs:
#   Full inputs, missing-row outputs, manifest, and combined QC files are
#   created under a timestamped work directory and removed after success.
#
# Paper-comparable strict run:
#   PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE
# 
# Usage for Python only
# OUTPUT_SUFFIX=python_specific PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE
#
# Important:
#   The paper-schema output preserves regenerated Python SonarQube metrics.
#   Selected unavailable covariates are filled from the frozen paper panel
#   only on exact repo-month matches.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Usage:
  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh [options]

Options:
  --convert-paper-same-column TRUE|FALSE
  --keep-overlap-paper-same-column TRUE|FALSE
  --paper-panel-file PATH
  --paper-audit-dir PATH
  --fill-from-paper-columns CSV_LIST
  --metric-compare-columns CSV_LIST
  --top-print INTEGER
  --help
EOF
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
      exit 1
      ;;
  esac
}

require_option_value() {
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "${option_value}" ]]; then
    echo "ERROR: ${option_name} requires a value." >&2
    exit 1
  fi
}

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CONVERT_PAPER_SAME_COLUMN="${CONVERT_PAPER_SAME_COLUMN:-FALSE}"
KEEP_OVERLAP_PAPER_SAME_COLUMN="${KEEP_OVERLAP_PAPER_SAME_COLUMN:-FALSE}"
PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-data/panel_event_monthly.csv}"
PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR:-${TMP_DIR}}"
FILL_FROM_PAPER_COLUMNS="${FILL_FROM_PAPER_COLUMNS:-stars,issues,issue_comments,age,num_dependencies_total,num_vulnerable_dependencies,average_technical_lag,other_agents,high_confidence}"
METRIC_COMPARE_COLUMNS="${METRIC_COMPARE_COLUMNS:-ncloc,bugs,vulnerabilities,code_smells,duplicated_lines_density,comment_lines_density,cognitive_complexity,technical_debt}"
TOP_PRINT="${TOP_PRINT:-20}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --convert-paper-same-column)
      require_option_value "$1" "${2:-}"
      CONVERT_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --keep-overlap-paper-same-column)
      require_option_value "$1" "${2:-}"
      KEEP_OVERLAP_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --paper-panel-file)
      require_option_value "$1" "${2:-}"
      PAPER_PANEL_FILE="$2"
      shift 2
      ;;
    --paper-audit-dir)
      require_option_value "$1" "${2:-}"
      PAPER_AUDIT_DIR="$2"
      shift 2
      ;;
    --fill-from-paper-columns)
      require_option_value "$1" "${2:-}"
      FILL_FROM_PAPER_COLUMNS="$2"
      shift 2
      ;;
    --metric-compare-columns)
      require_option_value "$1" "${2:-}"
      METRIC_COMPARE_COLUMNS="$2"
      shift 2
      ;;
    --top-print)
      require_option_value "$1" "${2:-}"
      TOP_PRINT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

CONVERT_PAPER_SAME_COLUMN="$(normalize_bool "${CONVERT_PAPER_SAME_COLUMN}")"
KEEP_OVERLAP_PAPER_SAME_COLUMN="$(normalize_bool "${KEEP_OVERLAP_PAPER_SAME_COLUMN}")"

if [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" && "${CONVERT_PAPER_SAME_COLUMN}" != "TRUE" ]]; then
  echo "ERROR: --keep-overlap-paper-same-column TRUE requires --convert-paper-same-column TRUE."
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

if [[ -n "${OUTPUT_SUFFIX}" && ! "${OUTPUT_SUFFIX}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERROR: OUTPUT_SUFFIX must contain only letters, numbers, and underscores. Got: ${OUTPUT_SUFFIX}"
  exit 1
fi

FILE_SUFFIX=""
if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  FILE_SUFFIX="_${OUTPUT_SUFFIX}"
fi

WORK_ROOT="${WORK_ROOT:-${TMP_DIR}/work_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}}"


if ! [[ "${TOP_PRINT}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --top-print must be a non-negative integer. Got: ${TOP_PRINT}"
  exit 1
fi

if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && ! -f "${PAPER_PANEL_FILE}" ]]; then
  echo "ERROR: paper panel file not found: ${PAPER_PANEL_FILE}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_prepare_quality_did_input_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}.log}"
MANIFEST_FILE="${WORK_ROOT}/quality_did_input_manifest_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_QC_LONG="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}${FILE_SUFFIX}_long.csv"
COMBINED_QC_WIDE="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}${FILE_SUFFIX}_wide.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube${FILE_SUFFIX}.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube${FILE_SUFFIX}.csv")
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}" "${WORK_ROOT}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: prepare Python quality DiD input"
  echo "Started:                           $(date)"
  echo "Script name:                       ${SCRIPT_NAME}"
  echo "Run prefix:                        ${RUN_PREFIX}"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Output suffix:                     ${OUTPUT_SUFFIX:-<none>}"
  echo "Python script:                     ${PY_SCRIPT}"
  echo "Panel input dir:                   ${PANEL_INPUT_DIR}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Paper panel file:                  ${PAPER_PANEL_FILE}"
  echo "Paper audit root:                   ${PAPER_AUDIT_DIR}"
  echo "Fill from paper columns:           ${FILL_FROM_PAPER_COLUMNS}"
  echo "Metric compare columns:            ${METRIC_COMPARE_COLUMNS}"
  echo "Top print:                         ${TOP_PRINT}"
  echo "Temporary manifest:                ${MANIFEST_FILE}"
  echo "Temporary combined QC long:        ${COMBINED_QC_LONG}"
  echo "Temporary combined QC wide:        ${COMBINED_QC_WIDE}"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  echo "panel,input,output,complete_output,qc_output,missing_output,paper_same_column_output,paper_key_summary,paper_unmatched_output" > "${MANIFEST_FILE}"

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

    PANEL_MAIN_DIR="${MAIN_OUTPUT_DIR}/${PANEL_LABEL}"
    PANEL_TMP_DIR="${TMP_DIR}/${PANEL_LABEL}${FILE_SUFFIX}"
    PANEL_WORK_DIR="${WORK_ROOT}/${PANEL_LABEL}"
    CURRENT_PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR}/${PANEL_LABEL}${FILE_SUFFIX}/paper_audit"

    mkdir -p "${PANEL_MAIN_DIR}" "${PANEL_TMP_DIR}" "${PANEL_WORK_DIR}" "${CURRENT_PAPER_AUDIT_DIR}"

    OUTPUT_FILE="${PANEL_WORK_DIR}/quality_did_input_full.csv"
    MISSING_OUTPUT_FILE="${PANEL_WORK_DIR}/missing_core_quality.csv"
    QC_OUTPUT_FILE="${PANEL_TMP_DIR}/quality_did_input_qc.csv"

    if [[ "${PANEL_LABEL}" == "strict" && "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      COMPLETE_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_matched_strict_with_sonarqube${FILE_SUFFIX}_quality_did_input_complete.csv"
    else
      COMPLETE_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_matched_${PANEL_LABEL}_with_sonarqube${FILE_SUFFIX}_quality_did_input_complete.csv"
    fi

    PAPER_SAME_COLUMN_OUTPUT_FILE=""
    PAPER_KEY_SUMMARY_FILE=""
    PAPER_UNMATCHED_OUTPUT_FILE=""

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      if [[ "${PANEL_LABEL}" == "strict" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_monthly_quality_py${FILE_SUFFIX}.csv"
      elif [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}${FILE_SUFFIX}.csv"
      else
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}${FILE_SUFFIX}_with_unmatched.csv"
      fi
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      PAPER_KEY_SUMMARY_FILE="${PAPER_AUDIT_BASE}_key_match_summary.csv"
      PAPER_UNMATCHED_OUTPUT_FILE="${PAPER_AUDIT_BASE}_unmatched_repo_months.csv"
    fi

    echo
    echo "============================================================"
    echo "Preparing quality DiD input for panel: ${PANEL_LABEL}"
    echo "Input:                         ${INPUT_FILE}"
    echo "Output:                        ${OUTPUT_FILE}"
    echo "Complete output:               ${COMPLETE_OUTPUT_FILE}"
    echo "QC output:                     ${QC_OUTPUT_FILE}"
    echo "Missing output:                ${MISSING_OUTPUT_FILE}"
    echo "Paper same-column output:      ${PAPER_SAME_COLUMN_OUTPUT_FILE:-<disabled>}"
    echo "Paper audit directory:         ${CURRENT_PAPER_AUDIT_DIR}"
    echo "Paper overlap-only:            ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
    echo "============================================================"

    PY_ARGS=(
      --panel-label "${PANEL_LABEL}"
      --input "${INPUT_FILE}"
      --output "${OUTPUT_FILE}"
      --complete-output "${COMPLETE_OUTPUT_FILE}"
      --qc-output "${QC_OUTPUT_FILE}"
      --missing-output "${MISSING_OUTPUT_FILE}"
      --convert-paper-same-column "${CONVERT_PAPER_SAME_COLUMN}"
      --keep-overlap-paper-same-column "${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
      --paper-panel-file "${PAPER_PANEL_FILE}"
      --paper-audit-dir "${CURRENT_PAPER_AUDIT_DIR}"
      --fill-from-paper-columns "${FILL_FROM_PAPER_COLUMNS}"
      --metric-compare-columns "${METRIC_COMPARE_COLUMNS}"
      --top-print "${TOP_PRINT}"
    )

    if [[ -n "${PAPER_SAME_COLUMN_OUTPUT_FILE}" ]]; then
      PY_ARGS+=(--paper-same-column-output "${PAPER_SAME_COLUMN_OUTPUT_FILE}")
    fi

    python "${PY_SCRIPT}" "${PY_ARGS[@]}"

    for expected_file in \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}"; do
      if [[ ! -f "${expected_file}" ]]; then
        echo "ERROR: missing expected output: ${expected_file}"
        exit 1
      fi
    done

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      for expected_file in \
        "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
        "${PAPER_AUDIT_BASE}_column_sources.csv" \
        "${PAPER_AUDIT_BASE}_key_match_summary.csv" \
        "${PAPER_AUDIT_BASE}_metric_comparison.csv" \
        "${PAPER_AUDIT_BASE}_unmatched_repo_months.csv" \
        "${PAPER_AUDIT_BASE}_notes.md"; do
        if [[ ! -f "${expected_file}" ]]; then
          echo "ERROR: missing expected paper-schema output: ${expected_file}"
          exit 1
        fi
      done

      echo "Paper-schema key match summary:"
      cat "${PAPER_KEY_SUMMARY_FILE}"
      rm -f "${PAPER_AUDIT_BASE}_notes.md"
    fi

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}" \
      "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
      "${PAPER_KEY_SUMMARY_FILE}" \
      "${PAPER_UNMATCHED_OUTPUT_FILE}" >> "${MANIFEST_FILE}"
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

manifest = pd.read_csv(manifest_path).fillna("")

qc_frames = []
wide_rows = []

def read_csv_if_possible(path_value):
    if not path_value:
        return pd.DataFrame()
    path = Path(path_value)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    qc = read_csv_if_possible(row["qc_output"])
    if not qc.empty:
        qc.insert(0, "panel", panel)
        qc_frames.append(qc)

    output_df = read_csv_if_possible(row["output"])
    complete_df = read_csv_if_possible(row["complete_output"])
    missing_df = read_csv_if_possible(row["missing_output"])
    paper_df = read_csv_if_possible(row["paper_same_column_output"])
    paper_key_summary = read_csv_if_possible(row["paper_key_summary"])

    wide_row = {
        "panel": panel,
        "output_file": row["output"],
        "complete_output_file": row["complete_output"],
        "missing_output_file": row["missing_output"],
        "paper_same_column_output_file": row["paper_same_column_output"],
        "output_rows": len(output_df),
        "complete_rows": len(complete_df),
        "missing_core_quality_rows": len(missing_df),
        "paper_same_column_output_rows": len(paper_df) if row["paper_same_column_output"] else None,
        "output_repos": output_df["repo_name"].nunique() if "repo_name" in output_df.columns else None,
        "complete_repos": complete_df["repo_name"].nunique() if "repo_name" in complete_df.columns else None,
        "paper_same_column_repos": paper_df["repo_name"].nunique() if "repo_name" in paper_df.columns else None,
    }

    if not paper_key_summary.empty:
        summary = paper_key_summary.iloc[0]
        wide_row.update({
            "paper_repo_month_rows_matched": summary.get("repo_month_rows_matched_to_paper"),
            "paper_repo_month_rows_unmatched": summary.get("repo_month_rows_not_matched_to_paper"),
            "keep_overlap_paper_same_column": summary.get("keep_overlap_paper_same_column"),
            "paper_duplicate_repo_month_rows": summary.get("paper_duplicate_repo_month_rows"),
        })
    else:
        wide_row.update({
            "paper_repo_month_rows_matched": None,
            "paper_repo_month_rows_unmatched": None,
            "keep_overlap_paper_same_column": None,
            "paper_duplicate_repo_month_rows": None,
        })

    wide_rows.append(wide_row)

combined_long = pd.concat(qc_frames, ignore_index=True) if qc_frames else pd.DataFrame()
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

  rm -rf "${WORK_ROOT}"

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:                         $(date)"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Output suffix:                     ${OUTPUT_SUFFIX:-<none>}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Temporary work files:              removed"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

# This wrapper reuses the logic of the previous run-py-2e and run-py-2b15
# workflows without directly calling either existing wrapper.


###############################################################################
# -- CALLED PYTHON SCRIPT: proc_scripts/prepare_quality_did_input_v2.py --
###############################################################################

: <<'__MERGED_PYTHON_21__'
#!/usr/bin/env python3
"""Prepare analysis-ready Python quality DiD inputs.

The script performs two related tasks:

1. Build the existing quality DiD input, complete-case output, missing-row
   output, and QC summary from a merged SonarQube panel.
2. Optionally convert the complete-case output into the exact column order of
   the paper's data/panel_event_monthly.csv. During this optional conversion,
   regenerated SonarQube metrics remain unchanged, while selected columns that
   are unavailable in the regenerated Python panel are filled from the frozen
   paper panel using exact repo-month keys.

The optional paper-schema output is a diagnostic overlap dataset. It is not a
full independent reproduction dataset because it combines regenerated Python
SonarQube outcomes with selected frozen paper covariates.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]

PAPER_JOIN_COLS = [
    "repo_name",
    "time",
]

BASE_DID_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "ever_treated",
    "is_treatment",
    "post_event",
]

CORE_QUALITY_OUTCOMES = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
]

RATE_OUTCOMES = [
    "warnings_per_kloc",
    "complexity_per_kloc",
    "code_smells_per_kloc",
]

OPTIONAL_QUALITY_OUTCOMES = [
    "technical_debt",
    "ncloc",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "bugs",
    "vulnerabilities",
    "code_smells",
]

LOG_OUTCOME_MAP = {
    "static_analysis_warnings": "log_static_analysis_warnings",
    "code_complexity": "log_code_complexity",
    "technical_debt": "log_technical_debt",
    "ncloc": "log_ncloc",
    "bugs": "log_bugs",
    "vulnerabilities": "log_vulnerabilities",
    "code_smells": "log_code_smells",
    "warnings_per_kloc": "log_warnings_per_kloc",
    "complexity_per_kloc": "log_complexity_per_kloc",
    "code_smells_per_kloc": "log_code_smells_per_kloc",
}

QC_FLAG_COLS = [
    "sonarqube_any_raw_metric_missing",
    "sonarqube_all_raw_metrics_missing",
    "sonarqube_ncloc_zero",
    "sonarqube_static_warnings_missing",
    "sonarqube_duplicate_density_missing",
    "sonarqube_cognitive_complexity_missing",
    "sonarqube_quality_outcomes_complete",
]

RAW_METRIC_COLS = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

DEFAULT_FILL_FROM_PAPER_COLUMNS = [
    "stars",
    "issues",
    "issue_comments",
    "age",
    "num_dependencies_total",
    "num_vulnerable_dependencies",
    "average_technical_lag",
    "other_agents",
    "high_confidence",
]

DEFAULT_METRIC_COMPARE_COLUMNS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]


TRUE_VALUES = {"TRUE", "T", "1", "YES", "Y"}
FALSE_VALUES = {"FALSE", "F", "0", "NO", "N"}


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_bool(value: str) -> bool:
    """Parse a case-insensitive CLI boolean value."""
    normalized = str(value).strip().upper()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise argparse.ArgumentTypeError(
        f"Expected TRUE or FALSE for a boolean argument, got: {value}"
    )


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    """Parse a comma-separated CLI list."""
    if value is None or str(value).strip() == "":
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prepare quality DiD input from a merged Python SonarQube panel."
    )
    parser.add_argument("--input", required=True, help="Merged SonarQube panel CSV.")
    parser.add_argument("--output", required=True, help="Output full quality DiD panel CSV.")
    parser.add_argument("--qc-output", required=True, help="Output QC summary CSV.")
    parser.add_argument(
        "--missing-output",
        required=True,
        help="Output rows with missing core quality outcomes.",
    )
    parser.add_argument(
        "--complete-output",
        required=False,
        default=None,
        help="Optional output CSV containing only analysis-ready quality DiD rows.",
    )
    parser.add_argument(
        "--panel-label",
        required=False,
        default="panel",
        help="Human-readable panel label for QC output.",
    )
    parser.add_argument(
        "--convert-paper-same-column",
        type=parse_bool,
        default=False,
        metavar="TRUE|FALSE",
        help=(
            "Create an additional output with the same column order as the paper "
            "data/panel_event_monthly.csv."
        ),
    )
    parser.add_argument(
        "--keep-overlap-paper-same-column",
        type=parse_bool,
        default=False,
        metavar="TRUE|FALSE",
        help=(
            "When paper-schema conversion is enabled, keep only source repo-month "
            "rows that have an exact match in the frozen paper panel."
        ),
    )
    parser.add_argument(
        "--paper-panel-file",
        default="data/panel_event_monthly.csv",
        help="Frozen paper panel used as the schema and paper-data source.",
    )
    parser.add_argument(
        "--paper-audit-dir",
        default="repo_python/tmp",
        help=(
            "Directory for paper-schema audit outputs such as key summaries, "
            "metric comparisons, unmatched rows, and notes."
        ),
    )
    parser.add_argument(
        "--paper-same-column-output",
        default=None,
        help=(
            "Optional paper-schema output path. If omitted, derive it from "
            "--complete-output or --output."
        ),
    )
    parser.add_argument(
        "--fill-from-paper-columns",
        default=",".join(DEFAULT_FILL_FROM_PAPER_COLUMNS),
        help="Comma-separated columns to fill from the paper panel on exact repo-month matches.",
    )
    parser.add_argument(
        "--metric-compare-columns",
        default=",".join(DEFAULT_METRIC_COMPARE_COLUMNS),
        help="Comma-separated regenerated-versus-paper metric comparison columns.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=20,
        help="Number of largest regenerated-versus-paper metric differences to print.",
    )
    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    """Require essential columns."""
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def to_numeric_if_present(df: pd.DataFrame, col: str) -> None:
    """Convert a column to numeric if it exists."""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def copy_first_available(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    """Create a target column from the first available candidate column."""
    if target in df.columns:
        return

    for candidate in candidates:
        if candidate in df.columns:
            df[target] = df[candidate]
            return


def normalize_month_value(value: object) -> str:
    """Normalize month keys to YYYY-MM when possible."""
    if pd.isna(value):
        return ""

    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return text


def add_paper_join_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized exact repo-month keys for paper-panel joins."""
    require_columns(df, PAPER_JOIN_COLS, "paper join input")
    out = df.copy()
    out["repo_name"] = out["repo_name"].astype(str)
    out["time"] = out["time"].map(normalize_month_value)
    out["__join_repo_name"] = out["repo_name"]
    out["__join_time"] = out["time"]
    return out


def safe_read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV and fail clearly if it does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return pd.read_csv(path, low_memory=False)


def add_alias_and_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add run9-compatible analysis columns and aliases."""
    df = df.copy()

    copy_first_available(df, "ncloc", ["ncloc_raw"])
    copy_first_available(df, "technical_debt", ["technical_debt_raw"])
    copy_first_available(df, "bugs", ["bugs_raw"])
    copy_first_available(df, "vulnerabilities", ["vulnerabilities_raw"])
    copy_first_available(df, "code_smells", ["code_smells_raw"])
    copy_first_available(df, "duplicated_lines_density", ["duplicated_lines_density_raw"])
    copy_first_available(df, "comment_lines_density", ["comment_lines_density_raw"])
    copy_first_available(df, "cognitive_complexity", ["cognitive_complexity_raw"])

    copy_first_available(
        df,
        "duplicate_line_density",
        ["duplicated_lines_density", "duplicated_lines_density_raw"],
    )
    copy_first_available(
        df,
        "code_complexity",
        ["cognitive_complexity", "cognitive_complexity_raw"],
    )

    for col in (
        CORE_QUALITY_OUTCOMES
        + RATE_OUTCOMES
        + OPTIONAL_QUALITY_OUTCOMES
        + RAW_METRIC_COLS
    ):
        to_numeric_if_present(df, col)

    if "static_analysis_warnings" not in df.columns:
        if {"bugs", "vulnerabilities", "code_smells"}.issubset(df.columns):
            df["static_analysis_warnings"] = df[
                ["bugs", "vulnerabilities", "code_smells"]
            ].sum(axis=1, min_count=3)

    valid_ncloc = df.get("ncloc", pd.Series(index=df.index, dtype=float)).notna()
    if "ncloc" in df.columns:
        valid_ncloc = df["ncloc"].notna() & (df["ncloc"] > 0)

    if "warnings_per_kloc" not in df.columns and {
        "static_analysis_warnings",
        "ncloc",
    }.issubset(df.columns):
        df["warnings_per_kloc"] = np.nan
        df.loc[valid_ncloc, "warnings_per_kloc"] = (
            df.loc[valid_ncloc, "static_analysis_warnings"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "complexity_per_kloc" not in df.columns and {
        "code_complexity",
        "ncloc",
    }.issubset(df.columns):
        df["complexity_per_kloc"] = np.nan
        df.loc[valid_ncloc, "complexity_per_kloc"] = (
            df.loc[valid_ncloc, "code_complexity"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "code_smells_per_kloc" not in df.columns and {
        "code_smells",
        "ncloc",
    }.issubset(df.columns):
        df["code_smells_per_kloc"] = np.nan
        df.loc[valid_ncloc, "code_smells_per_kloc"] = (
            df.loc[valid_ncloc, "code_smells"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    for source_col, log_col in LOG_OUTCOME_MAP.items():
        if source_col not in df.columns:
            continue

        x = pd.to_numeric(df[source_col], errors="coerce")
        df[log_col] = np.where(x.notna() & (x >= 0), np.log1p(x), np.nan)

    return df


def add_readiness_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add DiD readiness flags."""
    df = df.copy()

    if set(KEY_COLS).issubset(df.columns):
        df["did_duplicate_repo_time_source_key"] = df.duplicated(KEY_COLS).astype(int)
    else:
        df["did_duplicate_repo_time_source_key"] = 1

    df["analysis_ready_core_quality"] = (
        df[CORE_QUALITY_OUTCOMES].notna().all(axis=1)
        if set(CORE_QUALITY_OUTCOMES).issubset(df.columns)
        else False
    )

    existing_rate_cols = [c for c in RATE_OUTCOMES if c in df.columns]
    if existing_rate_cols:
        df["analysis_ready_quality_rates"] = df[existing_rate_cols].notna().all(axis=1)
    else:
        df["analysis_ready_quality_rates"] = False

    df["analysis_ready_did_base"] = (
        df[BASE_DID_COLS].notna().all(axis=1)
        & (df["did_duplicate_repo_time_source_key"] == 0)
        & df["dataset_source"].isin(["treatment", "control"])
    )

    df["analysis_ready_quality_did"] = (
        df["analysis_ready_did_base"] & df["analysis_ready_core_quality"]
    )

    for col in [
        "analysis_ready_core_quality",
        "analysis_ready_quality_rates",
        "analysis_ready_did_base",
        "analysis_ready_quality_did",
    ]:
        df[col] = df[col].astype(int)

    return df


def assert_no_invalid_values(df: pd.DataFrame) -> None:
    """Fail on structural problems, not on expected SonarQube missingness."""
    if set(KEY_COLS).issubset(df.columns):
        duplicate_count = int(df.duplicated(KEY_COLS).sum())
        if duplicate_count:
            raise ValueError(f"Duplicated repo-time-source keys: {duplicate_count}")

    for col in CORE_QUALITY_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES + RATE_OUTCOMES:
        if col not in df.columns:
            continue

        x = pd.to_numeric(df[col], errors="coerce")
        negative_count = int((x < 0).sum())
        if negative_count:
            raise ValueError(f"Negative values found in {col}: {negative_count}")


def build_qc(df: pd.DataFrame, input_rows: int, output_rows: int, panel_label: str) -> pd.DataFrame:
    """Build the existing quality DiD QC summary."""
    rows: list[dict[str, object]] = []

    def add(check: str, value: object) -> None:
        rows.append({"check": check, "value": value})

    add("panel_label", panel_label)
    add("input_rows", input_rows)
    add("output_rows", output_rows)
    add("row_count_preserved_in_full_output", int(input_rows == output_rows))
    add("repos", df["repo_name"].nunique() if "repo_name" in df.columns else None)
    add("min_time", df["time"].min() if "time" in df.columns else None)
    add("max_time", df["time"].max() if "time" in df.columns else None)

    add("treatment_rows", int((df["dataset_source"] == "treatment").sum()))
    add("control_rows", int((df["dataset_source"] == "control").sum()))
    add(
        "treatment_repos",
        df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add(
        "control_repos",
        df.loc[df["dataset_source"] == "control", "repo_name"].nunique(),
    )

    add("duplicate_repo_time_source_rows", int(df["did_duplicate_repo_time_source_key"].sum()))
    add("analysis_ready_did_base_rows", int(df["analysis_ready_did_base"].sum()))
    add("analysis_ready_core_quality_rows", int(df["analysis_ready_core_quality"].sum()))
    add("analysis_ready_quality_did_rows", int(df["analysis_ready_quality_did"].sum()))
    add("missing_core_quality_rows", int((df["analysis_ready_core_quality"] == 0).sum()))

    if "time_to_event" in df.columns:
        add(
            "treatment_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "treatment", "time_to_event"].notna().sum()),
        )
        add(
            "control_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "control", "time_to_event"].notna().sum()),
        )

    if "post_event" in df.columns:
        add("post_event_sum", int(pd.to_numeric(df["post_event"], errors="coerce").fillna(0).sum()))
        add(
            "control_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "control", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )
        add(
            "treatment_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "treatment", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )

    if "sonarqube_latest_commit" in df.columns:
        add("sonarqube_latest_commit_missing", int(df["sonarqube_latest_commit"].isna().sum()))

    for col in QC_FLAG_COLS:
        if col in df.columns:
            add(f"{col}_sum", int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum()))
        else:
            add(f"{col}_sum", None)

    for col in CORE_QUALITY_OUTCOMES + RATE_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES:
        if col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce")
            add(f"{col}_nonmissing", int(x.notna().sum()))
            add(f"{col}_missing", int(x.isna().sum()))
            add(f"{col}_zero_count", int((x == 0).sum()))
            add(f"{col}_mean", float(x.mean()) if x.notna().any() else None)
            add(f"{col}_median", float(x.median()) if x.notna().any() else None)
        else:
            add(f"{col}_nonmissing", None)
            add(f"{col}_missing", None)

    for _, log_col in LOG_OUTCOME_MAP.items():
        if log_col in df.columns:
            x = pd.to_numeric(df[log_col], errors="coerce")
            add(f"{log_col}_nonmissing", int(x.notna().sum()))
            add(f"{log_col}_finite", int(np.isfinite(x).sum()))

    return pd.DataFrame(rows)


def derive_paper_same_column_output(args: argparse.Namespace) -> Path:
    """Derive a stable paper-schema output name when none is supplied."""
    if args.paper_same_column_output:
        return Path(args.paper_same_column_output)

    source = Path(args.complete_output) if args.complete_output else Path(args.output)
    suffix = (
        "_paper_same_column_overlap.csv"
        if args.keep_overlap_paper_same_column
        else "_paper_same_column.csv"
    )
    return source.with_name(f"{source.stem}{suffix}")


def create_metric_comparison(
    source_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    metrics: Iterable[str],
) -> pd.DataFrame:
    """Compare regenerated and frozen-paper metrics on exact repo-month matches."""
    source_keyed = add_paper_join_keys(source_df)
    paper_keyed = add_paper_join_keys(paper_df).drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )

    available_metrics = [
        metric
        for metric in metrics
        if metric in source_keyed.columns and metric in paper_keyed.columns
    ]
    if not available_metrics:
        return pd.DataFrame()

    merged = source_keyed[
        ["repo_name", "time", "__join_repo_name", "__join_time"]
        + available_metrics
    ].merge(
        paper_keyed[["__join_repo_name", "__join_time"] + available_metrics],
        on=["__join_repo_name", "__join_time"],
        how="inner",
        suffixes=("_our", "_paper"),
        sort=False,
    )

    rows: list[dict[str, object]] = []
    for metric in available_metrics:
        our_values = pd.to_numeric(merged[f"{metric}_our"], errors="coerce")
        paper_values = pd.to_numeric(merged[f"{metric}_paper"], errors="coerce")
        differences = our_values - paper_values

        for idx in merged.index:
            difference = differences.at[idx]
            rows.append(
                {
                    "repo_name": merged.at[idx, "repo_name"],
                    "time": merged.at[idx, "time"],
                    "metric": metric,
                    "our_value": our_values.at[idx],
                    "paper_value": paper_values.at[idx],
                    "diff_our_minus_paper": difference,
                    "abs_diff": abs(difference) if pd.notna(difference) else pd.NA,
                }
            )

    comparison = pd.DataFrame(rows)
    if not comparison.empty:
        comparison = comparison.sort_values(
            ["abs_diff", "repo_name", "time", "metric"],
            ascending=[False, True, True, True],
        )
    return comparison


def create_paper_same_column_panel(
    source_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    fill_from_paper_columns: Iterable[str],
    keep_overlap_only: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the paper-schema panel and exact-match audit outputs.

    The source_df is expected to be the analysis-ready complete-case quality
    DiD panel. Columns already present in source_df are preserved. Only paper
    schema columns missing from source_df are eligible for paper-panel filling.
    """
    source_keyed = add_paper_join_keys(source_df)
    paper_keyed = add_paper_join_keys(paper_df)

    source_keyed["__source_row_order"] = np.arange(len(source_keyed))
    paper_schema = [col for col in paper_keyed.columns if not col.startswith("__join_")]
    fill_set = set(fill_from_paper_columns)

    source_duplicate_count = int(
        source_keyed.duplicated(["__join_repo_name", "__join_time"]).sum()
    )
    paper_duplicate_count = int(
        paper_keyed.duplicated(["__join_repo_name", "__join_time"]).sum()
    )

    paper_unique = paper_keyed.drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )
    fill_available = [col for col in fill_set if col in paper_unique.columns]

    paper_fill = paper_unique[
        ["__join_repo_name", "__join_time"] + fill_available
    ].copy()
    paper_fill["__paper_same_column_match"] = 1

    merged = source_keyed.merge(
        paper_fill,
        on=["__join_repo_name", "__join_time"],
        how="left",
        suffixes=("", "__paper_fill"),
        sort=False,
    ).sort_values("__source_row_order")

    matched_mask = merged["__paper_same_column_match"].eq(1)
    unmatched = merged.loc[~matched_mask, source_df.columns].copy()
    unmatched.insert(2, "paper_same_column_match", 0)

    selected = merged.loc[matched_mask].copy() if keep_overlap_only else merged.copy()

    output = pd.DataFrame(index=selected.index)
    column_source_rows: list[dict[str, object]] = []

    for col in paper_schema:
        if col in source_df.columns:
            output[col] = selected[col]
            source_label = "python_quality_input"
        elif col in fill_available:
            output[col] = selected[col]
            source_label = "paper_panel_exact_repo_month_fill"
        else:
            output[col] = pd.NA
            source_label = "missing_set_na"

        column_source_rows.append(
            {
                "column": col,
                "source": source_label,
                "non_missing_count": int(output[col].notna().sum()),
                "missing_count": int(output[col].isna().sum()),
            }
        )

    if "time" in output.columns:
        output["time"] = output["time"].map(normalize_month_value)

    key_summary = pd.DataFrame(
        [
            {
                "source_complete_rows": len(source_df),
                "paper_rows": len(paper_df),
                "paper_same_column_output_rows": len(output),
                "paper_same_column_output_columns": len(output.columns),
                "paper_schema_columns": len(paper_schema),
                "source_duplicate_repo_month_rows": source_duplicate_count,
                "paper_duplicate_repo_month_rows": paper_duplicate_count,
                "repo_month_rows_matched_to_paper": int(matched_mask.sum()),
                "repo_month_rows_not_matched_to_paper": int((~matched_mask).sum()),
                "keep_overlap_paper_same_column": int(keep_overlap_only),
            }
        ]
    )

    column_sources = pd.DataFrame(column_source_rows)
    return output, column_sources, key_summary, unmatched


def write_paper_same_column_notes(
    notes_path: Path,
    source_path: str,
    paper_path: str,
    output_path: Path,
    key_summary: pd.DataFrame,
    column_sources: pd.DataFrame,
    keep_overlap_only: bool,
) -> None:
    """Write a compact human-readable paper-schema diagnostic note."""
    summary = key_summary.iloc[0].to_dict()
    filled_columns = column_sources.loc[
        column_sources["source"] == "paper_panel_exact_repo_month_fill", "column"
    ].tolist()

    lines = [
        "# run-py-2e paper-same-column diagnostic notes",
        "",
        "## Purpose",
        "",
        "Create a paper-schema diagnostic output from the analysis-ready Python quality DiD input.",
        "Regenerated SonarQube metrics are preserved, while selected unavailable columns are filled from the frozen paper panel on exact repo-month matches.",
        "",
        "## Inputs",
        "",
        f"- Analysis-ready source: `{source_path}`",
        f"- Frozen paper panel: `{paper_path}`",
        "",
        "## Output",
        "",
        f"- Paper-schema output: `{output_path}`",
        f"- Keep exact overlap only: `{str(keep_overlap_only).upper()}`",
        "",
        "## Key summary",
        "",
        f"- Source complete rows: {summary.get('source_complete_rows')}",
        f"- Exact repo-month matches: {summary.get('repo_month_rows_matched_to_paper')}",
        f"- Unmatched repo-month rows: {summary.get('repo_month_rows_not_matched_to_paper')}",
        f"- Output rows: {summary.get('paper_same_column_output_rows')}",
        f"- Output columns: {summary.get('paper_same_column_output_columns')}",
        f"- Paper duplicate repo-month rows before deduplication: {summary.get('paper_duplicate_repo_month_rows')}",
        "",
        "## Columns filled from the paper panel",
        "",
    ]

    if filled_columns:
        lines.extend([f"- `{column}`" for column in filled_columns])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Interpretation caution",
            "",
            "This output is an overlap-restricted diagnostic dataset, not a full independent reproduction dataset.",
            "Dropping unmatched repo-month rows changes the analysis sample and should be reported explicitly.",
        ]
    )

    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_paper_same_column_conversion(
    args: argparse.Namespace,
    complete_df: pd.DataFrame,
    complete_source_label: str,
) -> dict[str, object]:
    """Run optional paper-schema conversion and write all audit outputs."""
    if args.keep_overlap_paper_same_column and not args.convert_paper_same_column:
        raise ValueError(
            "--keep-overlap-paper-same-column TRUE requires "
            "--convert-paper-same-column TRUE"
        )

    if not args.convert_paper_same_column:
        return {
            "enabled": 0,
            "output_path": "",
            "key_summary_path": "",
            "unmatched_path": "",
            "output_rows": None,
            "matched_rows": None,
            "unmatched_rows": None,
            "keep_overlap": int(args.keep_overlap_paper_same_column),
        }

    paper_path = Path(args.paper_panel_file)
    paper_df = safe_read_csv(paper_path)
    output_path = derive_paper_same_column_output(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fill_columns = parse_csv_list(
        args.fill_from_paper_columns,
        DEFAULT_FILL_FROM_PAPER_COLUMNS,
    )
    metric_columns = parse_csv_list(
        args.metric_compare_columns,
        DEFAULT_METRIC_COMPARE_COLUMNS,
    )

    paper_output, column_sources, key_summary, unmatched = create_paper_same_column_panel(
        source_df=complete_df,
        paper_df=paper_df,
        fill_from_paper_columns=fill_columns,
        keep_overlap_only=args.keep_overlap_paper_same_column,
    )
    metric_comparison = create_metric_comparison(
        source_df=complete_df,
        paper_df=paper_df,
        metrics=metric_columns,
    )

    audit_dir = Path(args.paper_audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_base = audit_dir / output_path.stem
    column_sources_path = Path(f"{audit_base}_column_sources.csv")
    key_summary_path = Path(f"{audit_base}_key_match_summary.csv")
    metric_comparison_path = Path(f"{audit_base}_metric_comparison.csv")
    unmatched_path = Path(f"{audit_base}_unmatched_repo_months.csv")
    notes_path = Path(f"{audit_base}_notes.md")

    paper_output.to_csv(output_path, index=False)
    column_sources.to_csv(column_sources_path, index=False)
    key_summary.to_csv(key_summary_path, index=False)
    metric_comparison.to_csv(metric_comparison_path, index=False)
    unmatched.to_csv(unmatched_path, index=False)
    write_paper_same_column_notes(
        notes_path=notes_path,
        source_path=complete_source_label,
        paper_path=str(paper_path),
        output_path=output_path,
        key_summary=key_summary,
        column_sources=column_sources,
        keep_overlap_only=args.keep_overlap_paper_same_column,
    )

    summary = key_summary.iloc[0]
    logging.info("Saved paper-schema output: %s", output_path)
    logging.info("Saved paper-schema audit directory: %s", audit_dir)
    logging.info("Saved paper-schema key summary: %s", key_summary_path)
    logging.info("Saved unmatched repo-month rows: %s", unmatched_path)
    logging.info(
        "Paper-schema exact matches: %d; unmatched: %d; output rows: %d",
        int(summary["repo_month_rows_matched_to_paper"]),
        int(summary["repo_month_rows_not_matched_to_paper"]),
        int(summary["paper_same_column_output_rows"]),
    )

    if not metric_comparison.empty and args.top_print > 0:
        print()
        print("Top paper-versus-regenerated metric differences:")
        for _, row in metric_comparison.head(args.top_print).iterrows():
            print(
                f"  {row['repo_name']},{row['time']},{row['metric']},"
                f"our={row['our_value']},paper={row['paper_value']},"
                f"diff={row['diff_our_minus_paper']}"
            )

    return {
        "enabled": 1,
        "output_path": str(output_path),
        "key_summary_path": str(key_summary_path),
        "unmatched_path": str(unmatched_path),
        "output_rows": int(summary["paper_same_column_output_rows"]),
        "matched_rows": int(summary["repo_month_rows_matched_to_paper"]),
        "unmatched_rows": int(summary["repo_month_rows_not_matched_to_paper"]),
        "keep_overlap": int(args.keep_overlap_paper_same_column),
    }


def main() -> int:
    """Run quality DiD preparation and optional paper-schema conversion."""
    setup_logging()
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    qc_path = Path(args.qc_output)
    missing_path = Path(args.missing_output)
    complete_path = Path(args.complete_output) if args.complete_output else None

    logging.info("Loading merged panel: %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    input_rows = len(df)

    require_columns(df, BASE_DID_COLS, "input panel")

    logging.info("Input rows: %d", input_rows)
    logging.info("Input repos: %d", df["repo_name"].nunique())
    logging.info("Input months: %s to %s", df["time"].min(), df["time"].max())

    df = add_alias_and_analysis_columns(df)
    require_columns(df, CORE_QUALITY_OUTCOMES, "prepared panel")

    df = add_readiness_flags(df)
    assert_no_invalid_values(df)

    missing_core = df[df["analysis_ready_core_quality"] == 0].copy()
    complete_df = df[df["analysis_ready_quality_did"] == 1].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    if complete_path:
        complete_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)
    missing_core.to_csv(missing_path, index=False)

    if complete_path:
        complete_df.to_csv(complete_path, index=False)

    complete_source_label = str(complete_path) if complete_path else f"{output_path} [analysis_ready_quality_did == 1]"
    paper_conversion = run_paper_same_column_conversion(
        args=args,
        complete_df=complete_df,
        complete_source_label=complete_source_label,
    )

    qc = build_qc(df, input_rows=input_rows, output_rows=len(df), panel_label=args.panel_label)

    additional_qc_rows: list[dict[str, object]] = []
    if complete_path:
        additional_qc_rows.extend(
            [
                {"check": "complete_output_path", "value": str(complete_path)},
                {"check": "complete_output_rows", "value": len(complete_df)},
                {"check": "complete_output_repos", "value": complete_df["repo_name"].nunique()},
            ]
        )

    additional_qc_rows.extend(
        [
            {"check": "convert_paper_same_column", "value": paper_conversion["enabled"]},
            {
                "check": "keep_overlap_paper_same_column",
                "value": paper_conversion["keep_overlap"],
            },
            {
                "check": "paper_same_column_output_path",
                "value": paper_conversion["output_path"],
            },
            {
                "check": "paper_same_column_output_rows",
                "value": paper_conversion["output_rows"],
            },
            {
                "check": "paper_same_column_matched_rows",
                "value": paper_conversion["matched_rows"],
            },
            {
                "check": "paper_same_column_unmatched_rows",
                "value": paper_conversion["unmatched_rows"],
            },
            {
                "check": "paper_same_column_unmatched_output_path",
                "value": paper_conversion["unmatched_path"],
            },
        ]
    )

    qc = pd.concat([qc, pd.DataFrame(additional_qc_rows)], ignore_index=True)
    qc.to_csv(qc_path, index=False)

    logging.info("Saved full quality DiD input: %s", output_path)
    logging.info("Saved missing core quality rows: %s", missing_path)
    if complete_path:
        logging.info("Saved complete-case quality DiD input: %s", complete_path)
    logging.info("Saved QC: %s", qc_path)

    print()
    print("QC summary:")
    print(qc.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_21__

###############################################################################
# -- SHELL SCRIPT: run-py-2f1-did-borusyak-quality.sh --
###############################################################################

set -euo pipefail

# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd')"
# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd', params = list(panel_file = '../repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv'))"

OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-python_only}"
PANEL_FILE="${PANEL_FILE:-../repo_python/run-py-2e/strict/panel_event_monthly_quality_py_${OUTPUT_SUFFIX}.csv}"
HTML_OUTPUT="${HTML_OUTPUT:-DiffInDiffBorusyak_${OUTPUT_SUFFIX}.html}"
BORUSYAK_PDF="${BORUSYAK_PDF:-../proc_r/dynamic_effects_borusyak_${OUTPUT_SUFFIX}.pdf}"
PYTHON_GROUP_PDF="${PYTHON_GROUP_PDF:-../proc_r/dynamic_effects_python_group_${OUTPUT_SUFFIX}.pdf}"

Rscript - "${PANEL_FILE}" "${HTML_OUTPUT}" "${BORUSYAK_PDF}" "${PYTHON_GROUP_PDF}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)
rmarkdown::render(
  input = "proc_r/DiffInDiffBorusyak.Rmd",
  output_file = args[[2]],
  output_dir = "proc_r",
  params = list(
    panel_file = args[[1]],
    borusyak_pdf_file = args[[3]],
    python_group_pdf_file = args[[4]]
  )
)
RS


###############################################################################
# -- SHELL SCRIPT: run-py-2f-did-borusyak-quality.sh --
###############################################################################

set -euo pipefail

# ============================================================
# run-py-2f: Borusyak DiD for Python SonarQube quality outcomes
# ============================================================
# Purpose:
#   Run Borusyak DiD estimation for Python quality outcomes.
#
# Inputs:
#   strict:
#     repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv
#
#   flexible:
#     repo_python/run-py-2e/flexible/
#       panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv
#
# Main presentation outputs:
#   repo_python/run-py-2f/<variant>/DiffInDiffBorusyak_quality_python_v2.html
#   repo_python/run-py-2f/<variant>/dynamic_effects_borusyak_quality_python_v2.pdf
#
# Extra analysis outputs:
#   repo_python/tmp/run-py-2f/<variant>/
#
# Temporary combined outputs:
#   repo_python/tmp/run-py-2f/work_<timestamp>/
#   Removed automatically after a successful run.
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage1:
#   PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
#
# Usage2:
#   OUTPUT_SUFFIX=python_only PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
# 
# Notes:
#   This wrapper reuses the analysis flow of the existing run-py-2f
#   implementation, but it is independent and does not call another wrapper.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"
if [[ -n "${OUTPUT_SUFFIX}" && ! "${OUTPUT_SUFFIX}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERROR: OUTPUT_SUFFIX must contain only letters, numbers, and underscores. Got: ${OUTPUT_SUFFIX}"
  exit 1
fi

FILE_SUFFIX=""
if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  FILE_SUFFIX="_${OUTPUT_SUFFIX}"
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_did_borusyak_quality_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}.log}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_ROOT="${MAIN_OUTPUT_ROOT:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_ROOT="${TMP_ROOT:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
WORK_DIR="${WORK_DIR:-${TMP_ROOT}/work_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}}"
PROC_R_DIR="${PROC_R_DIR:-proc_r}"

RMD_FILE="${RMD_FILE:-${PROC_R_DIR}/DiffInDiffBorusyak_quality_python_v2.Rmd}"
HELPER_FILE="${HELPER_FILE:-${PROC_R_DIR}/diff_in_diff_borusyak_helpers.R}"
OUT_ROOT="${OUT_ROOT:-${TMP_ROOT}}"

STRICT_PANEL_FILE="${STRICT_PANEL_FILE:-${OUTPUT_BASE_DIR}/run-py-2e/strict/panel_event_monthly_quality_py${FILE_SUFFIX}.csv}"
FLEXIBLE_PANEL_FILE="${FLEXIBLE_PANEL_FILE:-${OUTPUT_BASE_DIR}/run-py-2e/flexible/panel_event_matched_flexible_with_sonarqube${FILE_SUFFIX}_quality_did_input_complete.csv}"

STRICT_HTML_FILE="${STRICT_HTML_FILE:-${MAIN_OUTPUT_ROOT}/strict/DiffInDiffBorusyak_quality_python_v2${FILE_SUFFIX}.html}"
STRICT_PDF_FILE="${STRICT_PDF_FILE:-${MAIN_OUTPUT_ROOT}/strict/dynamic_effects_borusyak_quality_python_v2${FILE_SUFFIX}.pdf}"
FLEXIBLE_HTML_FILE="${FLEXIBLE_HTML_FILE:-${MAIN_OUTPUT_ROOT}/flexible/DiffInDiffBorusyak_quality_python_v2${FILE_SUFFIX}.html}"
FLEXIBLE_PDF_FILE="${FLEXIBLE_PDF_FILE:-${MAIN_OUTPUT_ROOT}/flexible/dynamic_effects_borusyak_quality_python_v2${FILE_SUFFIX}.pdf}"

MANIFEST_FILE="${WORK_DIR}/borusyak_quality_manifest_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_STATIC="${WORK_DIR}/borusyak_quality_static_effects_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_DYNAMIC="${WORK_DIR}/borusyak_quality_dynamic_effects_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_CHECKS="${WORK_DIR}/borusyak_quality_panel_checks_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_INPUT_SUMMARY="${WORK_DIR}/borusyak_quality_input_summary_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_ERRORS="${WORK_DIR}/borusyak_quality_errors_${PANEL_VARIANT}${FILE_SUFFIX}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${STRICT_PANEL_FILE}")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${FLEXIBLE_PANEL_FILE}")
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_ROOT}" "${TMP_ROOT}" "${WORK_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: Python Borusyak DiD for SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "Script name:            ${SCRIPT_NAME}"
  echo "Run prefix:             ${RUN_PREFIX}"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Output suffix:          ${OUTPUT_SUFFIX:-<none>}"
  echo "Project root:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "Helper file:            ${HELPER_FILE}"
  echo "Strict input:           ${STRICT_PANEL_FILE}"
  echo "Flexible input:         ${FLEXIBLE_PANEL_FILE}"
  echo "Main output root:       ${MAIN_OUTPUT_ROOT}"
  echo "Extra output root:      ${TMP_ROOT}"
  echo "Temporary work dir:     ${WORK_DIR}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
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

  if ! command -v Rscript >/dev/null 2>&1; then
    echo "ERROR: Rscript was not found in PATH."
    exit 1
  fi

  echo "panel,input,out_dir,html,pdf,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}${FILE_SUFFIX}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      if [[ "${PANEL_LABEL}" == "strict" ]]; then
        echo "Create the strict paper-schema input first:"
        echo "  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE"
      else
        echo "Create the flexible complete-case quality input first."
      fi
      exit 1
    fi

    rm -rf "${PANEL_OUT_DIR}"
    mkdir -p "${PANEL_OUT_DIR}"

    GENERATED_PDF_FILE="${PANEL_OUT_DIR}/dynamic_effects_borusyak_quality.pdf"
    STATIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv"
    DYNAMIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv"
    CHECKS_FILE="${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv"
    INPUT_SUMMARY_FILE="${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv"
    METADATA_FILE="${PANEL_OUT_DIR}/borusyak_quality_metadata.csv"
    GENERATED_STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv"
    GENERATED_DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv"

    rm -f \
      "${GENERATED_PDF_FILE}" \
      "${GENERATED_STATIC_ERRORS_FILE}" \
      "${GENERATED_DYNAMIC_ERRORS_FILE}"

    if [[ "${PANEL_LABEL}" == "strict" ]]; then
      HTML_FILE="${STRICT_HTML_FILE}"
      PDF_FILE="${STRICT_PDF_FILE}"
      RENDER_OUTPUT_DIR="$(dirname "${HTML_FILE}")"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors_${RUN_TS}.csv"
    else
      HTML_FILE="${FLEXIBLE_HTML_FILE}"
      PDF_FILE="${FLEXIBLE_PDF_FILE}"
      RENDER_OUTPUT_DIR="$(dirname "${HTML_FILE}")"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors_${RUN_TS}.csv"
    fi

    mkdir -p "${RENDER_OUTPUT_DIR}" "$(dirname "${PDF_FILE}")"
    rm -f "${HTML_FILE}" "${PDF_FILE}" "${STATIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"

    echo
    echo "============================================================"
    echo "Running panel: ${PANEL_LABEL}"
    echo "Input:         ${INPUT_FILE}"
    echo "Main HTML:     ${HTML_FILE}"
    echo "Main PDF:      ${PDF_FILE}"
    echo "Extra outputs: ${PANEL_OUT_DIR}"
    echo "============================================================"

    export PANEL_LABEL
    export PANEL_PATH="${INPUT_FILE}"
    export OUT_DIR="${PANEL_OUT_DIR}"
    export RMD_FILE
    export RENDER_OUTPUT_DIR
    export RENDER_OUTPUT_FILE

    Rscript - <<'RS'
rmd <- Sys.getenv("RMD_FILE")
render_output_dir <- Sys.getenv("RENDER_OUTPUT_DIR")
render_output_file <- Sys.getenv("RENDER_OUTPUT_FILE")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = render_output_file,
  output_dir = render_output_dir,
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS

    if [[ ! -f "${HTML_FILE}" ]]; then
      echo "ERROR: Expected HTML output was not created: ${HTML_FILE}"
      exit 1
    fi

    if [[ ! -f "${GENERATED_PDF_FILE}" ]]; then
      echo "ERROR: Expected PDF output was not created: ${GENERATED_PDF_FILE}"
      exit 1
    fi
    mv -f "${GENERATED_PDF_FILE}" "${PDF_FILE}"

    if [[ -f "${GENERATED_STATIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_STATIC_ERRORS_FILE}" "${STATIC_ERRORS_FILE}"
    fi

    if [[ -f "${GENERATED_DYNAMIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_DYNAMIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"
    fi

    for required_output in \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}"; do
      if [[ ! -f "${required_output}" ]]; then
        echo "ERROR: Expected core output was not created: ${required_output}"
        exit 1
      fi
    done

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${PDF_FILE}" \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}" \
      "${STATIC_ERRORS_FILE}" \
      "${DYNAMIC_ERRORS_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined diagnostic outputs"
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


def read_required_csv(path: str, panel: str, kind: str) -> pd.DataFrame:
    """Read a required core output and attach panel metadata when needed."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {kind} output for {panel}: {csv_path}")

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        frame = pd.DataFrame()

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)

    return frame


def read_error_csv(path: str, panel: str, model_type: str) -> pd.DataFrame | None:
    """Read an optional model error file."""
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return None

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return None

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)
    if "model_type" not in frame.columns:
        insert_pos = 1 if "panel" in frame.columns else 0
        frame.insert(insert_pos, "model_type", model_type)

    return frame


static_frames = []
dynamic_frames = []
checks_frames = []
summary_frames = []
error_frames = []

for _, row in manifest.iterrows():
    panel = str(row["panel"])

    static_frames.append(read_required_csv(row["static"], panel, "static"))
    dynamic_frames.append(read_required_csv(row["dynamic"], panel, "dynamic"))
    checks_frames.append(read_required_csv(row["checks"], panel, "checks"))
    summary_frames.append(read_required_csv(row["input_summary"], panel, "input summary"))

    for error_column, model_type in (
        ("static_errors", "static"),
        ("dynamic_errors", "dynamic"),
    ):
        error_frame = read_error_csv(row[error_column], panel, model_type)
        if error_frame is not None:
            error_frames.append(error_frame)

combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = (
    pd.concat(error_frames, ignore_index=True)
    if error_frames
    else pd.DataFrame(columns=["panel", "model_type", "outcome", "error"])
)

for output_path in (
    combined_static_path,
    combined_dynamic_path,
    combined_checks_path,
    combined_input_summary_path,
    combined_errors_path,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)

combined_static.to_csv(combined_static_path, index=False)
combined_dynamic.to_csv(combined_dynamic_path, index=False)
combined_checks.to_csv(combined_checks_path, index=False)
combined_input_summary.to_csv(combined_input_summary_path, index=False)
combined_errors.to_csv(combined_errors_path, index=False)

print("Combined static effects rows:", len(combined_static))
print("Combined dynamic effects rows:", len(combined_dynamic))
print("Combined panel checks rows:", len(combined_checks))
print("Combined input summary rows:", len(combined_input_summary))
print("Combined error rows:", len(combined_errors))
print()
print("Saved combined static effects:", combined_static_path)
print("Saved combined dynamic effects:", combined_dynamic_path)
print("Saved combined panel checks:", combined_checks_path)
print("Saved combined input summary:", combined_input_summary_path)
print("Saved combined errors:", combined_errors_path)
PY

  rm -rf "${WORK_DIR}"

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:              $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Output suffix:          ${OUTPUT_SUFFIX:-<none>}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
  echo "Main output root:       ${MAIN_OUTPUT_ROOT}"
  echo "Extra output root:      ${TMP_ROOT}"
  echo "Temporary outputs:      removed"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

###############################################################################
# -- SHELL SCRIPT: run-py-2g-summarize-borusyak-quality.sh --
###############################################################################

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
# -- CALLED PYTHON SCRIPT: proc_scripts/summarize_borusyak_quality_outputs_python.py --
###############################################################################

: <<'__MERGED_PYTHON_22__'
#!/usr/bin/env python3
"""Summarize run-py-2f Borusyak quality DiD outputs for Python paper tables and figures.

Inputs are generated by run-py-2f-did-borusyak-quality.sh.

Main outputs:
  - borusyak_quality_static_effects_paper_ready.csv
  - borusyak_quality_static_effects_paper_ready.md
  - borusyak_quality_static_effects_wide.csv
  - borusyak_quality_dynamic_effects_percent.csv
  - borusyak_quality_dynamic_effects_plot_ready.csv
  - borusyak_quality_summary_notes.txt
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


PANEL_ORDER = [
    "flexible",
    "strict",
]

PANEL_LABELS = {
    "flexible": "Flexible sample-coverage panel",
    "strict": "Strict 1:3 matching-rule panel",
}

OUTCOME_ORDER = [
    "log_static_analysis_warnings",
    "log_duplicate_line_density",
    "log_code_complexity",
]

OUTCOME_LABELS = {
    "log_static_analysis_warnings": "Static analysis warnings",
    "log_duplicate_line_density": "Duplicate line density",
    "log_code_complexity": "Code complexity",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize run-py-2f Python Borusyak quality DiD outputs."
    )
    parser.add_argument(
        "--input-dir",
        default="repo_python/did_final/quality_did_borusyak",
        help="Directory containing run9f combined Borusyak outputs.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for summarized outputs. Defaults to input-dir/summary.",
    )
    parser.add_argument(
        "--main-panel",
        default="strict",
        choices=PANEL_ORDER,
        help="Main Python panel used for primary interpretation.",
    )
    return parser.parse_args()


def pct_from_log(x: float | int | None) -> float | None:
    if pd.isna(x):
        return None
    return (math.exp(float(x)) - 1.0) * 100.0


def p_value_from_estimate(row: pd.Series) -> float | None:
    estimate = row.get("estimate")
    std_error = row.get("std_error")

    if pd.isna(estimate) or pd.isna(std_error) or float(std_error) == 0.0:
        return None

    z = abs(float(estimate) / float(std_error))
    # normal two-sided p-value using erf
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    return p


def significance_from_ci(row: pd.Series) -> bool:
    low = row.get("conf_low")
    high = row.get("conf_high")

    if pd.isna(low) or pd.isna(high):
        return False

    return (float(low) > 0.0) or (float(high) < 0.0)


def stars_from_p(p: float | None) -> str:
    if p is None or pd.isna(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    if p < 0.10:
        return "+"
    return ""


def format_pct(value: float | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{value:.{digits}f}%"


def format_effect(row: pd.Series) -> str:
    pct = row.get("percent_change")
    low = row.get("conf_low_percent")
    high = row.get("conf_high_percent")
    stars = row.get("stars", "")

    if pd.isna(pct):
        return ""

    return (
        f"{pct:.1f}%{stars} "
        f"[{low:.1f}%, {high:.1f}%]"
    )


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")


def load_static(input_dir: Path) -> pd.DataFrame:
    path = input_dir / "borusyak_quality_static_effects_all.csv"
    require_file(path)

    df = pd.read_csv(path)

    required = {
        "panel",
        "outcome",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Static effects missing columns: {sorted(missing)}")

    return df


def load_dynamic(input_dir: Path) -> pd.DataFrame:
    path = input_dir / "borusyak_quality_dynamic_effects_all.csv"
    require_file(path)

    df = pd.read_csv(path)

    required = {
        "panel",
        "outcome",
        "time",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dynamic effects missing columns: {sorted(missing)}")

    return df


def load_optional(input_dir: Path, filename: str) -> pd.DataFrame:
    path = input_dir / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def prepare_static(static_df: pd.DataFrame) -> pd.DataFrame:
    df = static_df.copy()

    for col in ["estimate", "std_error", "conf_low", "conf_high", "p_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["panel_label"] = df["panel"].map(PANEL_LABELS).fillna(df["panel"])
    df["outcome_label"] = df["outcome"].map(OUTCOME_LABELS).fillna(df["outcome"])

    df["percent_change"] = df["estimate"].apply(pct_from_log)
    df["conf_low_percent"] = df["conf_low"].apply(pct_from_log)
    df["conf_high_percent"] = df["conf_high"].apply(pct_from_log)

    if "p_value" not in df.columns:
        df["p_value"] = pd.NA

    computed_p = df.apply(p_value_from_estimate, axis=1)
    df["p_value_computed"] = computed_p

    df["p_value_final"] = df["p_value"]
    df.loc[df["p_value_final"].isna(), "p_value_final"] = df.loc[
        df["p_value_final"].isna(), "p_value_computed"
    ]

    df["ci_excludes_zero"] = df.apply(significance_from_ci, axis=1)
    df["stars"] = df["p_value_final"].apply(stars_from_p)
    df["effect_percent_ci"] = df.apply(format_effect, axis=1)

    df["panel_order"] = df["panel"].map(
        {panel: i for i, panel in enumerate(PANEL_ORDER)}
    )
    df["outcome_order"] = df["outcome"].map(
        {outcome: i for i, outcome in enumerate(OUTCOME_ORDER)}
    )

    df = df.sort_values(["panel_order", "outcome_order"]).reset_index(drop=True)

    return df


def prepare_dynamic(dynamic_df: pd.DataFrame) -> pd.DataFrame:
    df = dynamic_df.copy()

    for col in ["time", "estimate", "std_error", "conf_low", "conf_high", "p_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["panel_label"] = df["panel"].map(PANEL_LABELS).fillna(df["panel"])
    df["outcome_label"] = df["outcome"].map(OUTCOME_LABELS).fillna(df["outcome"])

    df["percent_change"] = df["estimate"].apply(pct_from_log)
    df["conf_low_percent"] = df["conf_low"].apply(pct_from_log)
    df["conf_high_percent"] = df["conf_high"].apply(pct_from_log)

    if "p_value" not in df.columns:
        df["p_value"] = pd.NA

    computed_p = df.apply(p_value_from_estimate, axis=1)
    df["p_value_computed"] = computed_p

    df["p_value_final"] = df["p_value"]
    df.loc[df["p_value_final"].isna(), "p_value_final"] = df.loc[
        df["p_value_final"].isna(), "p_value_computed"
    ]

    df["ci_excludes_zero"] = df.apply(significance_from_ci, axis=1)
    df["stars"] = df["p_value_final"].apply(stars_from_p)

    df["panel_order"] = df["panel"].map(
        {panel: i for i, panel in enumerate(PANEL_ORDER)}
    )
    df["outcome_order"] = df["outcome"].map(
        {outcome: i for i, outcome in enumerate(OUTCOME_ORDER)}
    )

    df = df.sort_values(["panel_order", "outcome_order", "time"]).reset_index(
        drop=True
    )

    return df


def build_static_wide(static_ready: pd.DataFrame) -> pd.DataFrame:
    keep = static_ready[
        [
            "panel",
            "panel_label",
            "outcome",
            "outcome_label",
            "effect_percent_ci",
        ]
    ].copy()

    wide = keep.pivot_table(
        index=["panel", "panel_label"],
        columns="outcome_label",
        values="effect_percent_ci",
        aggfunc="first",
    ).reset_index()

    ordered_outcome_labels = [OUTCOME_LABELS[o] for o in OUTCOME_ORDER]
    existing = [c for c in ordered_outcome_labels if c in wide.columns]
    wide = wide[["panel", "panel_label"] + existing]

    wide["panel_order"] = wide["panel"].map(
        {panel: i for i, panel in enumerate(PANEL_ORDER)}
    )
    wide = wide.sort_values("panel_order").drop(columns=["panel_order"])

    return wide


def build_main_panel_table(static_ready: pd.DataFrame, main_panel: str) -> pd.DataFrame:
    main = static_ready[static_ready["panel"] == main_panel].copy()

    cols = [
        "outcome_label",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "percent_change",
        "conf_low_percent",
        "conf_high_percent",
        "p_value_final",
        "stars",
        "ci_excludes_zero",
        "effect_percent_ci",
    ]

    return main[cols]


def markdown_cell(value: object) -> str:
    """Format one markdown table cell without requiring tabulate."""
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text


def write_markdown_table(df: pd.DataFrame, path: Path) -> None:
    """Write a markdown table without pandas.to_markdown/tabulate."""
    cols = list(df.columns)

    lines = []
    lines.append("| " + " | ".join(markdown_cell(c) for c in cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")

    for _, row in df.iterrows():
        lines.append(
            "| " + " | ".join(markdown_cell(row[c]) for c in cols) + " |"
        )

    path.write_text("\n".join(lines) + "\n")


def build_notes(
    static_ready: pd.DataFrame,
    main_panel: str,
    errors_df: pd.DataFrame,
) -> str:
    lines: list[str] = []

    lines.append("Borusyak Quality DiD Summary")
    lines.append("=" * 32)
    lines.append("")
    lines.append(f"Main panel: {main_panel}")
    lines.append("")
    lines.append("Static effects are log-point estimates converted to percent changes:")
    lines.append("percent_change = (exp(estimate) - 1) * 100")
    lines.append("")

    main = static_ready[static_ready["panel"] == main_panel].copy()

    for _, row in main.iterrows():
        lines.append(
            f"- {row['outcome_label']}: "
            f"{format_pct(row['percent_change'])} "
            f"[{format_pct(row['conf_low_percent'])}, "
            f"{format_pct(row['conf_high_percent'])}], "
            f"CI excludes zero: {bool(row['ci_excludes_zero'])}"
        )

    lines.append("")
    lines.append("Robustness pattern:")
    for outcome in OUTCOME_ORDER:
        sub = static_ready[static_ready["outcome"] == outcome]
        positive = int((sub["estimate"] > 0).sum())
        significant = int(sub["ci_excludes_zero"].sum())
        total = len(sub)
        lines.append(
            f"- {OUTCOME_LABELS[outcome]}: positive in {positive}/{total} panels; "
            f"CI excludes zero in {significant}/{total} panels."
        )

    lines.append("")
    if errors_df.empty:
        lines.append("Model errors: none recorded.")
    else:
        lines.append(f"Model errors: {len(errors_df)} rows recorded.")
        for _, row in errors_df.head(20).iterrows():
            lines.append(f"- {row.to_dict()}")

    lines.append("")
    lines.append("Recommended interpretation:")
    code = static_ready[static_ready["outcome"] == "log_code_complexity"]
    if len(code) and int(code["ci_excludes_zero"].sum()) == len(code):
        lines.append(
            "Code complexity is the most robust quality outcome: all panels show "
            "positive estimates with confidence intervals excluding zero."
        )
    else:
        lines.append(
            "Code complexity remains the primary outcome to inspect, but not all "
            "robustness panels have confidence intervals excluding zero."
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "summary"
    output_dir.mkdir(parents=True, exist_ok=True)

    static_df = load_static(input_dir)
    dynamic_df = load_dynamic(input_dir)
    checks_df = load_optional(input_dir, "borusyak_quality_panel_checks_all.csv")
    input_summary_df = load_optional(input_dir, "borusyak_quality_input_summary_all.csv")
    errors_df = load_optional(input_dir, "borusyak_quality_errors_all.csv")

    static_ready = prepare_static(static_df)
    dynamic_ready = prepare_dynamic(dynamic_df)

    static_wide = build_static_wide(static_ready)
    main_table = build_main_panel_table(static_ready, args.main_panel)

    static_ready_path = output_dir / "borusyak_quality_static_effects_paper_ready.csv"
    static_wide_path = output_dir / "borusyak_quality_static_effects_wide.csv"
    main_table_path = output_dir / "borusyak_quality_main_panel_table.csv"
    main_table_md_path = output_dir / "borusyak_quality_main_panel_table.md"
    dynamic_percent_path = output_dir / "borusyak_quality_dynamic_effects_percent.csv"
    dynamic_plot_path = output_dir / "borusyak_quality_dynamic_effects_plot_ready.csv"
    notes_path = output_dir / "borusyak_quality_summary_notes.txt"

    static_ready.to_csv(static_ready_path, index=False)
    static_wide.to_csv(static_wide_path, index=False)
    main_table.to_csv(main_table_path, index=False)
    write_markdown_table(main_table, main_table_md_path)

    dynamic_ready.to_csv(dynamic_percent_path, index=False)
    dynamic_ready[
        [
            "panel",
            "panel_label",
            "outcome",
            "outcome_label",
            "time",
            "percent_change",
            "conf_low_percent",
            "conf_high_percent",
            "ci_excludes_zero",
            "stars",
        ]
    ].to_csv(dynamic_plot_path, index=False)

    notes = build_notes(static_ready, args.main_panel, errors_df)
    notes_path.write_text(notes)

    if not checks_df.empty:
        checks_df.to_csv(output_dir / "borusyak_quality_panel_checks_copy.csv", index=False)

    if not input_summary_df.empty:
        input_summary_df.to_csv(
            output_dir / "borusyak_quality_input_summary_copy.csv",
            index=False,
        )

    if not errors_df.empty:
        errors_df.to_csv(output_dir / "borusyak_quality_errors_copy.csv", index=False)

    print("Saved summary outputs to:", output_dir)
    print()
    print("Main panel table:")
    print(main_table.to_string(index=False))
    print()
    print("Static effects wide:")
    print(static_wide.to_string(index=False))
    print()
    print("Notes:")
    print(notes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__MERGED_PYTHON_22__

###############################################################################
# -- SHELL SCRIPT: run-py-2h-did-borusyak-velocity.sh --
###############################################################################

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


