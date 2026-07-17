#!/usr/bin/env python3
"""
Create pair-stage comparison outputs.

This script creates two files in the same output directory:

  1. jsts_pair_stage_comparison.csv
  2. jsts_pair_stage_comparison-metadata.txt

Main purpose
------------
This script decomposes the pair-stage part of the comparison between:

  - the paper baseline matching structure
  - our main final-clean JS/TS pair structure
  - our strict 1:3 JS/TS pair structure

The key question is:

  How does the treatment-control matching structure change from the
  paper baseline matching.csv to our main and strict JS/TS pair files?

Why this matters
----------------
The paper states that it uses 1:3 nearest-neighbor matching, meaning
three matched control slots per treated repository. However, the same
control repository may be reused across multiple treatment repositories.

Therefore, the important checks are:

  - pairs: total treatment-control pair rows
  - treat: number of unique treatment repositories
  - ctrl: number of unique control repositories
  - t1/t2/t3: number of treatment repositories with 1, 2, or 3 controls
  - max_reuse/mean_reuse: how often control repositories are reused

Default output directory
------------------------
By default, this script writes outputs into the same directory as this
script, matching the compare-01 style:

  proc_scripts/compare-02/
    compare_jsts_02_pair_stage.py
    jsts_pair_stage_comparison.csv
    jsts_pair_stage_comparison-metadata.txt

You can override the output directory with:

  --out-dir compare/output
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pandas as pd


# ----------------------------------------------------------------------
# Column-name candidates
# ----------------------------------------------------------------------
# These lists make the script more robust to small column-name differences
# across baseline files and our generated files.

REPO_COL_CANDIDATES = [
    "repo_name",
    "repo",
    "repository",
    "full_name",
]

LANGUAGE_COL_CANDIDATES = [
    "primary_language",
    "repo_language",
    "language",
    "repo_primary_language",
    "detected_language",
]

TREATMENT_COL_CANDIDATES = [
    "treatment_repo",
    "repo_name",
    "repo",
]

CONTROL_COL_CANDIDATES = [
    "control_repo",
    "matched_control",
    "repo_name",
    "repo",
]


# ----------------------------------------------------------------------
# Stage notes
# ----------------------------------------------------------------------
# These notes are written into the metadata file and also included as a
# short note column in the actual CSV.

STAGE_NOTES = {
    "paper_matching_jsts": (
        "Baseline paper matching.csv restricted to JS/TS treatment repositories "
        "identified from data_baseline_backup/repos.csv."
    ),
    "paper_matching_for_our_jsts_sample": (
        "Baseline paper matching.csv restricted to our JS/TS treatment sample, "
        "if the sample file exists."
    ),
    "our_initial_extracted_pairs": (
        "Our initially extracted JS/TS treatment-control pairs, before later "
        "clone/local-Cursor filtering, if the file exists."
    ),
    "our_main_final_clean_pairs": (
        "Our main final-clean JS/TS pair file. This may include treatments with "
        "1, 2, or 3 final controls."
    ),
    "our_strict_1to3_pairs": (
        "Our strict 1:3 JS/TS pair file. This should keep only treatments with "
        "exactly 3 final controls."
    ),
}


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------

def find_project_root(start: Path) -> Path:
    """
    Find the project root by walking upward from the script location.

    We do not assume a fixed directory depth because the user may place
    this script under proc_scripts/compare-02, notebooks, or another folder.

    A directory is treated as the project root if it contains either:
      - data_baseline_backup/
      - tmp_jsts_test/
      - proc_scripts/
    """
    current = start.resolve()

    if current.is_file():
        current = current.parent

    for parent in [current] + list(current.parents):
        has_baseline = (parent / "data_baseline_backup").exists()
        has_tmp_jsts = (parent / "tmp_jsts_test").exists()
        has_proc_scripts = (parent / "proc_scripts").exists()

        if has_baseline and has_proc_scripts:
            return parent

        if has_baseline and has_tmp_jsts:
            return parent

    # Fallback: for proc_scripts/compare-02/script.py, parents[2] is usually root.
    return start.resolve().parents[2]


def resolve_path(path_text: str, project_root: Path) -> Path:
    """
    Resolve a path argument.

    If the path is absolute, use it as-is.
    If the path is relative, interpret it relative to project_root.
    """
    path = Path(path_text)

    if path.is_absolute():
        return path

    return project_root / path


def read_csv_required(path: Path) -> pd.DataFrame:
    """
    Read a required CSV file.

    This raises a clear error if the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path)


def read_csv_optional(path: Path) -> Optional[pd.DataFrame]:
    """
    Read an optional CSV file.

    This returns None if the file does not exist.
    Optional files are useful for intermediate stages that may not exist in
    every run.
    """
    if not path.exists():
        return None

    return pd.read_csv(path)


# ----------------------------------------------------------------------
# Column helpers
# ----------------------------------------------------------------------

def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """
    Find the first matching column from a candidate list.
    """
    columns = set(df.columns)

    for col in candidates:
        if col in columns:
            return col

    return None


def normalize_repo_series(series: pd.Series) -> pd.Series:
    """
    Normalize repository-name values.

    This removes leading/trailing spaces and converts values to strings.
    """
    return series.astype(str).str.strip()


def get_repo_col(df: pd.DataFrame) -> str:
    """
    Find the repository-name column in a dataframe.
    """
    col = find_col(df, REPO_COL_CANDIDATES)

    if col is None:
        raise ValueError(
            "Could not find repository column. "
            f"Available columns: {list(df.columns)}"
        )

    return col


def get_jsts_repos_from_metadata(df: pd.DataFrame) -> Set[str]:
    """
    Extract JS/TS repositories from repository metadata.

    The baseline repos.csv is expected to contain a repository column and
    a language column. This function keeps rows whose language is JavaScript
    or TypeScript.
    """
    repo_col = get_repo_col(df)
    lang_col = find_col(df, LANGUAGE_COL_CANDIDATES)

    if lang_col is None:
        raise ValueError(
            "Could not find language column in repo metadata. "
            f"Available columns: {list(df.columns)}"
        )

    lang = df[lang_col].astype(str).str.lower()

    is_jsts = lang.isin(["javascript", "typescript"]) | lang.str.contains(
        "javascript|typescript",
        regex=True,
        na=False,
    )

    return set(normalize_repo_series(df.loc[is_jsts, repo_col]))


def get_repo_set_from_file(df: pd.DataFrame) -> Set[str]:
    """
    Extract a repository set from a CSV file.

    This is used for optional files such as our JS/TS treatment sample file.
    """
    repo_col = get_repo_col(df)
    return set(normalize_repo_series(df[repo_col]))


# ----------------------------------------------------------------------
# Matching conversion helpers
# ----------------------------------------------------------------------

def sort_matched_control_columns(cols: List[str]) -> List[str]:
    """
    Sort matched-control columns by numeric suffix.

    Example:
      matched_control_1, matched_control_2, matched_control_3
    """
    def sort_key(col: str) -> tuple[int, str]:
        match = re.search(r"(\d+)$", col)

        if match:
            return (int(match.group(1)), col)

        return (9999, col)

    return sorted(cols, key=sort_key)


def wide_matching_to_long_pairs(
    df: pd.DataFrame,
    treatment_filter: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """
    Convert a wide matching file into long pair format.

    Expected wide format:
      repo_name, matched_control_1, matched_control_2, matched_control_3

    Output long format:
      treatment_repo, control_repo, control_rank

    treatment_filter:
      If provided, only treatment repositories in this set are kept.
    """
    treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)

    if treatment_col is None:
        raise ValueError(
            "Could not find treatment repository column in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    matched_cols = [
        col
        for col in df.columns
        if col.startswith("matched_control_") or col.startswith("control_")
    ]

    matched_cols = sort_matched_control_columns(matched_cols)

    if not matched_cols:
        raise ValueError(
            "Could not find matched-control columns in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    rows = []

    for _, row in df.iterrows():
        treatment_repo = str(row[treatment_col]).strip()

        if not treatment_repo or treatment_repo == "nan":
            continue

        if treatment_filter is not None and treatment_repo not in treatment_filter:
            continue

        for rank, col in enumerate(matched_cols, start=1):
            control_repo = row.get(col)

            if pd.isna(control_repo):
                continue

            control_repo = str(control_repo).strip()

            if not control_repo or control_repo == "nan":
                continue

            rows.append(
                {
                    "treatment_repo": treatment_repo,
                    "control_repo": control_repo,
                    "control_rank": rank,
                }
            )

    out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(
            columns=["treatment_repo", "control_repo", "control_rank"]
        )

    out["treatment_repo"] = normalize_repo_series(out["treatment_repo"])
    out["control_repo"] = normalize_repo_series(out["control_repo"])

    return out


def normalize_long_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize an already-long pair file.

    Expected long format:
      treatment_repo, control_repo

    Some files may also have control_rank. If control_rank is missing, this
    function reconstructs it within each treatment repository after sorting.
    """
    if "treatment_repo" not in df.columns:
        treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)
    else:
        treatment_col = "treatment_repo"

    if "control_repo" not in df.columns:
        control_col = find_col(df, CONTROL_COL_CANDIDATES)
    else:
        control_col = "control_repo"

    if treatment_col is None or control_col is None:
        raise ValueError(
            "Could not find treatment/control columns in long pair file. "
            f"Available columns: {list(df.columns)}"
        )

    out = df[[treatment_col, control_col]].copy()
    out.columns = ["treatment_repo", "control_repo"]

    out["treatment_repo"] = normalize_repo_series(out["treatment_repo"])
    out["control_repo"] = normalize_repo_series(out["control_repo"])

    out = out[
        (out["treatment_repo"] != "")
        & (out["control_repo"] != "")
        & (out["treatment_repo"] != "nan")
        & (out["control_repo"] != "nan")
    ].copy()

    out = out.drop_duplicates(["treatment_repo", "control_repo"]).copy()

    out = out.sort_values(["treatment_repo", "control_repo"]).reset_index(drop=True)

    out["control_rank"] = (
        out.groupby("treatment_repo").cumcount() + 1
    )

    return out


# ----------------------------------------------------------------------
# Pair-stage summary
# ----------------------------------------------------------------------

def summarize_pair_stage(pairs: pd.DataFrame, stage: str) -> Dict[str, object]:
    """
    Summarize one treatment-control pair stage.

    Definitions:
      pairs      = number of treatment-control pair rows
      treat      = number of unique treatment repos
      ctrl       = number of unique control repos
      t1         = treatments with exactly 1 unique control
      t2         = treatments with exactly 2 unique controls
      t3         = treatments with exactly 3 unique controls
      t_other    = treatments with control counts other than 1, 2, or 3
      max_c      = maximum number of controls per treatment
      mean_c     = average number of controls per treatment
      max_reuse  = maximum number of treatment repos sharing a single control repo
      mean_reuse = average number of treatment repos per control repo
    """
    if pairs.empty:
        return {
            "stage": stage,
            "pairs": 0,
            "treat": 0,
            "ctrl": 0,
            "t1": 0,
            "t2": 0,
            "t3": 0,
            "t_other": 0,
            "max_c": 0,
            "mean_c": 0.0,
            "max_reuse": 0,
            "mean_reuse": 0.0,
            "note": STAGE_NOTES.get(stage, ""),
        }

    # Remove duplicate treatment-control pairs before counting.
    clean_pairs = pairs[["treatment_repo", "control_repo"]].drop_duplicates().copy()

    # Count how many unique controls each treatment has.
    controls_per_treatment = (
        clean_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_controls")
    )

    # Count how many unique treatments each control is matched to.
    # This captures control reuse across treatment repositories.
    treatments_per_control = (
        clean_pairs.groupby("control_repo")["treatment_repo"]
        .nunique()
        .reset_index(name="num_treatments")
    )

    control_counts = controls_per_treatment["num_controls"]
    reuse_counts = treatments_per_control["num_treatments"]

    t1 = int((control_counts == 1).sum())
    t2 = int((control_counts == 2).sum())
    t3 = int((control_counts == 3).sum())
    t_other = int((~control_counts.isin([1, 2, 3])).sum())

    return {
        "stage": stage,
        "pairs": int(len(clean_pairs)),
        "treat": int(clean_pairs["treatment_repo"].nunique()),
        "ctrl": int(clean_pairs["control_repo"].nunique()),
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t_other": t_other,
        "max_c": int(control_counts.max()) if not control_counts.empty else 0,
        "mean_c": round(float(control_counts.mean()), 4)
        if not control_counts.empty
        else 0.0,
        "max_reuse": int(reuse_counts.max()) if not reuse_counts.empty else 0,
        "mean_reuse": round(float(reuse_counts.mean()), 4)
        if not reuse_counts.empty
        else 0.0,
        "note": STAGE_NOTES.get(stage, ""),
    }


# ----------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------

def write_pair_stage_csv(path: Path, summary_df: pd.DataFrame) -> None:
    """
    Write the actual CSV file.

    The CSV file intentionally has no comment lines because the metadata is
    stored separately in a companion text file.
    """
    output_columns = [
        "stage",
        "pairs",
        "treat",
        "ctrl",
        "t1",
        "t2",
        "t3",
        "t_other",
        "max_c",
        "mean_c",
        "max_reuse",
        "mean_reuse",
    ]

    summary_df[output_columns].to_csv(path, index=False)


def write_metadata_txt(
    path: Path,
    args: argparse.Namespace,
    project_root: Path,
    included_stages: List[str],
) -> None:
    """
    Write a human-readable metadata file.

    This file explains:
      - what the CSV is for
      - what each stage means
      - what each column means
      - which input files were used
    """
    lines = []

    lines.append("File: jsts_pair_stage_comparison.csv")
    lines.append("---")
    lines.append("Purpose")
    lines.append(
        "Compare treatment-control pair structure across paper baseline "
        "matching, our main JS/TS pairs, and our strict 1:3 JS/TS pairs."
    )
    lines.append("")
    lines.append("Important interpretation")
    lines.append(
        "The paper uses 1:3 nearest-neighbor matching, meaning three matched "
        "control slots per treated repository. However, the same control "
        "repository can be reused across multiple treatment repositories."
    )
    lines.append("")
    lines.append("---")
    lines.append("Stage notes")

    for stage in included_stages:
        lines.append(f"{stage:<38} - {STAGE_NOTES.get(stage, '')}")

    lines.append("")
    lines.append("---")
    lines.append("Columns")
    lines.append("stage      - Pair-stage label.")
    lines.append("pairs      - Number of unique treatment-control pair rows.")
    lines.append("treat      - Number of unique treatment repositories.")
    lines.append("ctrl       - Number of unique control repositories.")
    lines.append("t1         - Number of treatment repositories with exactly 1 control.")
    lines.append("t2         - Number of treatment repositories with exactly 2 controls.")
    lines.append("t3         - Number of treatment repositories with exactly 3 controls.")
    lines.append("t_other    - Number of treatment repositories with a control count other than 1, 2, or 3.")
    lines.append("max_c      - Maximum number of controls assigned to any one treatment repository.")
    lines.append("mean_c     - Mean number of controls per treatment repository.")
    lines.append("max_reuse  - Maximum number of treatment repositories sharing the same control repository.")
    lines.append("mean_reuse - Mean number of treatment repositories per control repository.")
    lines.append("")
    lines.append("---")
    lines.append("Input files")
    lines.append(f"project_root: {project_root}")
    lines.append(f"paper_repos: {args.paper_repos}")
    lines.append(f"paper_matching: {args.paper_matching}")
    lines.append(f"our_treatment_sample: {args.our_treatment_sample}")
    lines.append(f"our_initial_pairs: {args.our_initial_pairs}")
    lines.append(f"our_main_pairs: {args.our_main_pairs}")
    lines.append(f"our_strict_pairs: {args.our_strict_pairs}")
    lines.append("")
    lines.append("---")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("Generated by: compare_jsts_02_pair_stage.py")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------
# Main construction logic
# ----------------------------------------------------------------------

def build_pair_stage_comparison(args: argparse.Namespace, project_root: Path) -> tuple[pd.DataFrame, List[str]]:
    """
    Build the full pair-stage comparison dataframe.

    This function creates rows in this order when files are available:

      1. paper_matching_jsts
      2. paper_matching_for_our_jsts_sample
      3. our_initial_extracted_pairs
      4. our_main_final_clean_pairs
      5. our_strict_1to3_pairs
    """
    paper_repos_path = resolve_path(args.paper_repos, project_root)
    paper_matching_path = resolve_path(args.paper_matching, project_root)

    our_treatment_sample_path = resolve_path(args.our_treatment_sample, project_root)
    our_initial_pairs_path = resolve_path(args.our_initial_pairs, project_root)
    our_main_pairs_path = resolve_path(args.our_main_pairs, project_root)
    our_strict_pairs_path = resolve_path(args.our_strict_pairs, project_root)

    paper_repos = read_csv_required(paper_repos_path)
    paper_matching = read_csv_required(paper_matching_path)

    rows: List[Dict[str, object]] = []
    included_stages: List[str] = []

    # Stage 1: Paper baseline matching restricted to paper JS/TS treatment repos.
    paper_jsts_treatment_repos = get_jsts_repos_from_metadata(paper_repos)

    paper_jsts_pairs = wide_matching_to_long_pairs(
        paper_matching,
        treatment_filter=paper_jsts_treatment_repos,
    )

    rows.append(
        summarize_pair_stage(
            paper_jsts_pairs,
            "paper_matching_jsts",
        )
    )
    included_stages.append("paper_matching_jsts")

    # Stage 2: Paper matching restricted to our JS/TS treatment sample.
    # This is optional because the exact sample file may not exist in every workspace.
    our_treatment_sample = read_csv_optional(our_treatment_sample_path)

    if our_treatment_sample is not None:
        our_jsts_sample_repos = get_repo_set_from_file(our_treatment_sample)

        paper_for_our_sample_pairs = wide_matching_to_long_pairs(
            paper_matching,
            treatment_filter=our_jsts_sample_repos,
        )

        rows.append(
            summarize_pair_stage(
                paper_for_our_sample_pairs,
                "paper_matching_for_our_jsts_sample",
            )
        )
        included_stages.append("paper_matching_for_our_jsts_sample")

    # Stage 3: Our initially extracted pair file.
    # This is optional because some runs may keep only final-clean pair files.
    our_initial_pairs_df = read_csv_optional(our_initial_pairs_path)

    if our_initial_pairs_df is not None:
        our_initial_pairs = normalize_long_pairs(our_initial_pairs_df)

        rows.append(
            summarize_pair_stage(
                our_initial_pairs,
                "our_initial_extracted_pairs",
            )
        )
        included_stages.append("our_initial_extracted_pairs")

    # Stage 4: Our main final-clean pair file.
    our_main_pairs_df = read_csv_required(our_main_pairs_path)
    our_main_pairs = normalize_long_pairs(our_main_pairs_df)

    rows.append(
        summarize_pair_stage(
            our_main_pairs,
            "our_main_final_clean_pairs",
        )
    )
    included_stages.append("our_main_final_clean_pairs")

    # Stage 5: Our strict 1:3 pair file.
    our_strict_pairs_df = read_csv_required(our_strict_pairs_path)
    our_strict_pairs = normalize_long_pairs(our_strict_pairs_df)

    rows.append(
        summarize_pair_stage(
            our_strict_pairs,
            "our_strict_1to3_pairs",
        )
    )
    included_stages.append("our_strict_1to3_pairs")

    return pd.DataFrame(rows), included_stages


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    The defaults are based on the current JS/TS replication workspace.
    """
    script_path = Path(__file__).resolve()
    project_root = find_project_root(script_path)
    default_out_dir = script_path.parent

    parser = argparse.ArgumentParser(
        description=(
            "Create jsts_pair_stage_comparison.csv and "
            "jsts_pair_stage_comparison-metadata.txt."
        )
    )

    parser.add_argument(
        "--paper-repos",
        default="data_baseline_backup/repos.csv",
        help="Baseline paper repository metadata CSV.",
    )

    parser.add_argument(
        "--paper-matching",
        default="data_baseline_backup/matching.csv",
        help="Baseline paper matching CSV.",
    )

    parser.add_argument(
        "--our-treatment-sample",
        default="tmp_jsts_test/data/jsts_treatment_sample_main_398.csv",
        help=(
            "Optional JS/TS treatment sample file. "
            "If missing, the corresponding stage is skipped."
        ),
    )

    parser.add_argument(
        "--our-initial-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv",
        help=(
            "Optional initially extracted JS/TS pair file. "
            "If missing, the corresponding stage is skipped."
        ),
    )

    parser.add_argument(
        "--our-main-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398_final_clean.csv",
        help="Our main final-clean JS/TS pair file.",
    )

    parser.add_argument(
        "--our-strict-pairs",
        default=(
            "tmp_jsts_test/data/"
            "jsts_matched_control_pairs_main_398_final_clean_1to3_only.csv"
        ),
        help="Our strict 1:3 JS/TS pair file.",
    )

    parser.add_argument(
        "--out-dir",
        default=str(default_out_dir),
        help=(
            "Output directory. Default is the script directory, matching "
            "the compare-01 structure."
        ),
    )

    parser.add_argument(
        "--csv-name",
        default="jsts_pair_stage_comparison.csv",
        help="Output CSV filename.",
    )

    parser.add_argument(
        "--metadata-name",
        default="jsts_pair_stage_comparison-metadata.txt",
        help="Output metadata filename.",
    )

    args = parser.parse_args()

    # Store project_root on args so writer functions can report it.
    args.project_root = str(project_root)

    return args


def main() -> None:
    args = parse_args()

    script_path = Path(__file__).resolve()
    project_root = Path(args.project_root)

    out_dir = resolve_path(args.out_dir, project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / args.csv_name
    out_metadata = out_dir / args.metadata_name

    summary_df, included_stages = build_pair_stage_comparison(args, project_root)

    write_pair_stage_csv(out_csv, summary_df)
    write_metadata_txt(out_metadata, args, project_root, included_stages)

    print("Pair-stage comparison completed.")
    print(f"Output CSV: {out_csv}")
    print(f"Output metadata: {out_metadata}")
    print("")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
