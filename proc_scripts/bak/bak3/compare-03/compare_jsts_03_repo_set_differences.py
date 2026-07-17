#!/usr/bin/env python3
"""
Create JS/TS repository-set difference outputs.

This script creates two files:

  1. compare/output/jsts_repo_set_differences.csv
  2. compare/output/jsts_repo_set_differences-metadata.txt

Main purpose
------------
This script compares repository sets across these stages:

  - paper baseline JS/TS matching set
  - paper baseline matching restricted to our JS/TS sample
  - our initially extracted JS/TS pair set
  - our main final-clean JS/TS pair set
  - our strict 1:3 JS/TS pair set

The main research question is:

  Which treatment/control repositories exist in the paper-side JS/TS
  matching set but disappear from our strict 1:3 JS/TS set?

Why this matters
----------------
The paper uses 1:3 nearest-neighbor matching, meaning each treated
repository receives three matched control slots.

Our strict 1:3 set keeps only treatment repositories that still have
exactly three final controls after our replication filters. Therefore,
this script helps identify which repositories are removed when moving
from paper/main sets to the strict 1:3 set.

Important output design
-----------------------
The CSV file is intentionally clean and does not include a note column.
All explanations are saved in the metadata text file.

Default output files
--------------------
  compare/output/jsts_repo_set_differences.csv
  compare/output/jsts_repo_set_differences-metadata.txt
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


# ----------------------------------------------------------------------
# Column-name candidates
# ----------------------------------------------------------------------
# These candidates make the script robust to small column-name differences.

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
# Stage definitions
# ----------------------------------------------------------------------
# alias is used in short comparison names, such as:
#
#   paper_treatment_minus_strict_treatment
#   main_control_minus_strict_control

STAGE_ALIAS_TO_KEY = {
    "paper": "paper_matching_jsts",
    "paper_sample": "paper_matching_for_our_jsts_sample",
    "initial": "our_initial_extracted_pairs",
    "main": "our_main_final_clean_pairs",
    "strict": "our_strict_1to3_pairs",
}

STAGE_NOTES = {
    "paper_matching_jsts": (
        "Baseline paper matching.csv restricted to JS/TS treatment repositories "
        "identified from data_baseline_backup/repos.csv."
    ),
    "paper_matching_for_our_jsts_sample": (
        "Baseline paper matching.csv restricted to our JS/TS treatment sample. "
        "This stage helps separate paper-vs-our-sample differences from later "
        "replication filtering differences."
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
    Find the project root by walking upward from this script.

    A directory is treated as the project root if it contains:
      - data_baseline_backup/
      - and either proc_scripts/ or tmp_jsts_test/
    """
    current = start.resolve()

    if current.is_file():
        current = current.parent

    for parent in [current] + list(current.parents):
        has_baseline = (parent / "data_baseline_backup").exists()
        has_proc_scripts = (parent / "proc_scripts").exists()
        has_tmp_jsts = (parent / "tmp_jsts_test").exists()

        if has_baseline and (has_proc_scripts or has_tmp_jsts):
            return parent

    # Fallback for notebooks/compare_jsts_03_repo_set_differences.py.
    return start.resolve().parents[1]


def resolve_path(path_text: str, project_root: Path) -> Path:
    """
    Resolve an input/output path.

    Absolute paths are used directly.
    Relative paths are interpreted relative to project_root.
    """
    path = Path(path_text)

    if path.is_absolute():
        return path

    return project_root / path


def read_csv_required(path: Path) -> pd.DataFrame:
    """
    Read a required CSV file.

    A missing required file should stop execution because the comparison
    cannot be trusted without it.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path)


def read_csv_optional(path: Path) -> Optional[pd.DataFrame]:
    """
    Read an optional CSV file.

    Optional stages are skipped if the file does not exist.
    """
    if not path.exists():
        return None

    return pd.read_csv(path)


# ----------------------------------------------------------------------
# Column helpers
# ----------------------------------------------------------------------

def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """
    Find the first column whose name appears in candidates.
    """
    columns = set(df.columns)

    for col in candidates:
        if col in columns:
            return col

    return None


def normalize_repo_series(series: pd.Series) -> pd.Series:
    """
    Normalize repository-name values.

    Repository names should be comparable across files, so we convert them
    to strings and remove leading/trailing spaces.
    """
    return series.astype(str).str.strip()


def get_repo_col(df: pd.DataFrame) -> str:
    """
    Find a repository-name column in a dataframe.
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
    Extract JS/TS repository names from repository metadata.

    The paper-side repos.csv should contain:
      - a repository-name column
      - a primary-language column

    We keep repositories whose language is JavaScript or TypeScript.
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
    Extract a repository set from a file such as our JS/TS treatment sample.
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
      matched_control_1
      matched_control_2
      matched_control_3
    """
    def sort_key(col: str) -> Tuple[int, str]:
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
        if re.match(r"^matched_control_\d+$", col)
        or re.match(r"^control_\d+$", col)
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

    out = out.drop_duplicates(
        ["treatment_repo", "control_repo"]
    ).reset_index(drop=True)

    return out


def normalize_long_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize an already-long pair file.

    Expected long format:
      treatment_repo, control_repo

    If control_rank is missing, it is reconstructed after sorting.
    """
    if "treatment_repo" in df.columns:
        treatment_col = "treatment_repo"
    else:
        treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)

    if "control_repo" in df.columns:
        control_col = "control_repo"
    else:
        control_col = find_col(df, CONTROL_COL_CANDIDATES)

    if treatment_col is None or control_col is None:
        raise ValueError(
            "Could not find treatment/control columns in pair file. "
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

    out["control_rank"] = out.groupby("treatment_repo").cumcount() + 1

    return out


# ----------------------------------------------------------------------
# Stage statistics
# ----------------------------------------------------------------------

def build_stage_stats(pairs: pd.DataFrame) -> Dict[str, object]:
    """
    Build treatment/control sets and link counts for one pair stage.

    For treatment repositories:
      n_links = number of unique controls matched to the treatment.

    For control repositories:
      n_links = number of unique treatments using the control.
    """
    clean_pairs = pairs[["treatment_repo", "control_repo"]].drop_duplicates().copy()

    treatment_set = set(clean_pairs["treatment_repo"])
    control_set = set(clean_pairs["control_repo"])

    treatment_link_counts = (
        clean_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .to_dict()
    )

    control_link_counts = (
        clean_pairs.groupby("control_repo")["treatment_repo"]
        .nunique()
        .to_dict()
    )

    return {
        "pairs": clean_pairs,
        "treatment_set": treatment_set,
        "control_set": control_set,
        "treatment_link_counts": treatment_link_counts,
        "control_link_counts": control_link_counts,
    }


def get_stage_set(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    role: str,
) -> Set[str]:
    """
    Get treatment/control repository set for a stage alias.
    """
    if alias not in stage_stats_by_alias:
        return set()

    if role == "treatment":
        return set(stage_stats_by_alias[alias]["treatment_set"])

    if role == "control":
        return set(stage_stats_by_alias[alias]["control_set"])

    raise ValueError(f"Unknown role: {role}")


def repo_in_stage(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    role: str,
    repo_name: str,
) -> bool:
    """
    Return True if repo_name belongs to the requested role set in a stage.
    """
    return repo_name in get_stage_set(stage_stats_by_alias, alias, role)


def get_repo_link_count(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    role: str,
    repo_name: str,
) -> int:
    """
    Get link count for repo_name in one stage.

    If role == treatment:
      return number of unique controls assigned to this treatment.

    If role == control:
      return number of unique treatments linked to this control.
    """
    if alias not in stage_stats_by_alias:
        return 0

    if role == "treatment":
        counts = stage_stats_by_alias[alias]["treatment_link_counts"]
        return int(counts.get(repo_name, 0))

    if role == "control":
        counts = stage_stats_by_alias[alias]["control_link_counts"]
        return int(counts.get(repo_name, 0))

    raise ValueError(f"Unknown role: {role}")


# ----------------------------------------------------------------------
# Reason-code logic
# ----------------------------------------------------------------------

def infer_reason_code(
    repo_name: str,
    role: str,
    left_alias: str,
    right_alias: str,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
) -> str:
    """
    Infer a pipeline-stage reason code for a set difference row.

    The reason_code is not a perfect causal diagnosis.
    It is a compact explanation based on where the repository appears or
    disappears across available pair stages.
    """
    in_paper = repo_in_stage(stage_stats_by_alias, "paper", role, repo_name)
    in_paper_sample = repo_in_stage(
        stage_stats_by_alias, "paper_sample", role, repo_name
    )
    in_initial = repo_in_stage(stage_stats_by_alias, "initial", role, repo_name)
    in_main = repo_in_stage(stage_stats_by_alias, "main", role, repo_name)
    in_strict = repo_in_stage(stage_stats_by_alias, "strict", role, repo_name)

    paper_sample_available = "paper_sample" in stage_stats_by_alias
    initial_available = "initial" in stage_stats_by_alias

    n_main = get_repo_link_count(stage_stats_by_alias, "main", role, repo_name)

    # Main-to-strict attrition is the most important strict 1:3 diagnosis.
    if right_alias == "strict" and in_main and not in_strict:
        if role == "treatment":
            if n_main < 3:
                return "less_than_3_final_controls_after_filtering"
            return "not_in_strict_even_though_main_has_3_controls"

        if role == "control":
            return "control_removed_when_strict_dropped_treatments"

    # Paper-to-strict treatment attrition can happen before our sample exists.
    if left_alias == "paper" and right_alias == "strict" and role == "treatment":
        if paper_sample_available and not in_paper_sample:
            return "paper_jsts_treatment_not_in_our_jsts_sample"

        if initial_available and not in_initial:
            return "not_in_our_initial_extracted_pairs"

        if not in_main:
            return "removed_before_main_final_clean_pairs"

        if in_main and not in_strict:
            if n_main < 3:
                return "less_than_3_final_controls_after_filtering"
            return "strict_stage_attrition_unknown"

    # Paper-to-strict control attrition can be caused by sample restriction
    # or by later filtering/dropping of treatments.
    if left_alias == "paper" and right_alias == "strict" and role == "control":
        if paper_sample_available and not in_paper_sample:
            return "paper_jsts_control_not_matched_to_our_jsts_sample"

        if initial_available and not in_initial:
            return "not_in_our_initial_extracted_pairs"

        if not in_main:
            return "removed_before_main_final_clean_pairs"

        if in_main and not in_strict:
            return "control_removed_when_strict_dropped_treatments"

    # Initial-to-main attrition usually reflects filters after initial extraction.
    if left_alias == "initial" and right_alias == "main" and in_initial and not in_main:
        return "removed_after_initial_pair_extraction"

    # Reverse differences are usually unexpected but still useful to report.
    if left_alias == "strict" and right_alias == "paper" and in_strict and not in_paper:
        return "present_in_strict_but_not_in_paper_jsts_reference"

    if left_alias == "main" and right_alias == "paper" and in_main and not in_paper:
        return "present_in_main_but_not_in_paper_jsts_reference"

    if left_alias == "strict" and right_alias == "main" and in_strict and not in_main:
        return "present_in_strict_but_not_in_main_unexpected"

    return "stage_membership_difference"


# ----------------------------------------------------------------------
# Difference-row construction
# ----------------------------------------------------------------------

def build_difference_row(
    comparison: str,
    left_alias: str,
    right_alias: str,
    role: str,
    repo_name: str,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    """
    Build one row of the output CSV.

    The CSV has no note column.
    All explanations are in the metadata file.
    """
    reason_code = infer_reason_code(
        repo_name=repo_name,
        role=role,
        left_alias=left_alias,
        right_alias=right_alias,
        stage_stats_by_alias=stage_stats_by_alias,
    )

    return {
        "comparison": comparison,
        "left_stage": left_alias,
        "right_stage": right_alias,
        "role": role,
        "repo_name": repo_name,
        "reason_code": reason_code,
        "in_paper": repo_in_stage(stage_stats_by_alias, "paper", role, repo_name),
        "in_paper_sample": repo_in_stage(
            stage_stats_by_alias, "paper_sample", role, repo_name
        ),
        "in_initial": repo_in_stage(stage_stats_by_alias, "initial", role, repo_name),
        "in_main": repo_in_stage(stage_stats_by_alias, "main", role, repo_name),
        "in_strict": repo_in_stage(stage_stats_by_alias, "strict", role, repo_name),
        "n_paper": get_repo_link_count(
            stage_stats_by_alias, "paper", role, repo_name
        ),
        "n_paper_sample": get_repo_link_count(
            stage_stats_by_alias, "paper_sample", role, repo_name
        ),
        "n_initial": get_repo_link_count(
            stage_stats_by_alias, "initial", role, repo_name
        ),
        "n_main": get_repo_link_count(
            stage_stats_by_alias, "main", role, repo_name
        ),
        "n_strict": get_repo_link_count(
            stage_stats_by_alias, "strict", role, repo_name
        ),
    }


def add_set_difference_rows(
    rows: List[Dict[str, object]],
    left_alias: str,
    right_alias: str,
    role: str,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
) -> None:
    """
    Add rows for:

      left_stage role set minus right_stage role set

    Example:
      paper treatment set minus strict treatment set
    """
    if left_alias not in stage_stats_by_alias:
        return

    if right_alias not in stage_stats_by_alias:
        return

    left_set = get_stage_set(stage_stats_by_alias, left_alias, role)
    right_set = get_stage_set(stage_stats_by_alias, right_alias, role)

    diff_set = sorted(left_set - right_set)

    comparison = f"{left_alias}_{role}_minus_{right_alias}_{role}"

    for repo_name in diff_set:
        rows.append(
            build_difference_row(
                comparison=comparison,
                left_alias=left_alias,
                right_alias=right_alias,
                role=role,
                repo_name=repo_name,
                stage_stats_by_alias=stage_stats_by_alias,
            )
        )


# ----------------------------------------------------------------------
# Build all stages
# ----------------------------------------------------------------------

def build_stage_stats_by_alias(
    args: argparse.Namespace,
    project_root: Path,
) -> Dict[str, Dict[str, object]]:
    """
    Load all available stages and return statistics keyed by stage alias.
    """
    paper_repos_path = resolve_path(args.paper_repos, project_root)
    paper_matching_path = resolve_path(args.paper_matching, project_root)
    our_treatment_sample_path = resolve_path(args.our_treatment_sample, project_root)
    our_initial_pairs_path = resolve_path(args.our_initial_pairs, project_root)
    our_main_pairs_path = resolve_path(args.our_main_pairs, project_root)
    our_strict_pairs_path = resolve_path(args.our_strict_pairs, project_root)

    paper_repos = read_csv_required(paper_repos_path)
    paper_matching = read_csv_required(paper_matching_path)

    stage_stats_by_alias: Dict[str, Dict[str, object]] = {}

    # Stage 1: paper baseline matching restricted to paper JS/TS treatment repos.
    paper_jsts_treatment_repos = get_jsts_repos_from_metadata(paper_repos)

    paper_jsts_pairs = wide_matching_to_long_pairs(
        paper_matching,
        treatment_filter=paper_jsts_treatment_repos,
    )

    stage_stats_by_alias["paper"] = build_stage_stats(paper_jsts_pairs)

    # Stage 2: paper baseline matching restricted to our JS/TS treatment sample.
    # This stage is optional because some workspaces may not have the sample file.
    our_treatment_sample = read_csv_optional(our_treatment_sample_path)

    if our_treatment_sample is not None:
        our_sample_repos = get_repo_set_from_file(our_treatment_sample)

        paper_sample_pairs = wide_matching_to_long_pairs(
            paper_matching,
            treatment_filter=our_sample_repos,
        )

        stage_stats_by_alias["paper_sample"] = build_stage_stats(
            paper_sample_pairs
        )

    # Stage 3: our initially extracted pair file.
    # This stage is optional because some workspaces may keep only final files.
    our_initial_pairs_df = read_csv_optional(our_initial_pairs_path)

    if our_initial_pairs_df is not None:
        our_initial_pairs = normalize_long_pairs(our_initial_pairs_df)
        stage_stats_by_alias["initial"] = build_stage_stats(our_initial_pairs)

    # Stage 4: our main final-clean pair file.
    our_main_pairs_df = read_csv_required(our_main_pairs_path)
    our_main_pairs = normalize_long_pairs(our_main_pairs_df)
    stage_stats_by_alias["main"] = build_stage_stats(our_main_pairs)

    # Stage 5: our strict 1:3 pair file.
    our_strict_pairs_df = read_csv_required(our_strict_pairs_path)
    our_strict_pairs = normalize_long_pairs(our_strict_pairs_df)
    stage_stats_by_alias["strict"] = build_stage_stats(our_strict_pairs)

    return stage_stats_by_alias


def build_repo_set_differences(
    stage_stats_by_alias: Dict[str, Dict[str, object]]
) -> pd.DataFrame:
    """
    Build the full repository-set difference CSV.

    The most important comparisons are:
      - paper_treatment_minus_strict_treatment
      - paper_control_minus_strict_control
      - main_treatment_minus_strict_treatment
      - main_control_minus_strict_control

    Additional comparisons are included to explain where attrition happens.
    """
    rows: List[Dict[str, object]] = []

    comparison_pairs = [
        ("paper", "strict"),
        ("strict", "paper"),
        ("paper", "main"),
        ("main", "paper"),
        ("paper_sample", "strict"),
        ("strict", "paper_sample"),
        ("initial", "main"),
        ("main", "initial"),
        ("initial", "strict"),
        ("strict", "initial"),
        ("main", "strict"),
        ("strict", "main"),
    ]

    for left_alias, right_alias in comparison_pairs:
        for role in ["treatment", "control"]:
            add_set_difference_rows(
                rows=rows,
                left_alias=left_alias,
                right_alias=right_alias,
                role=role,
                stage_stats_by_alias=stage_stats_by_alias,
            )

    output_columns = [
        "comparison",
        "left_stage",
        "right_stage",
        "role",
        "repo_name",
        "reason_code",
        "in_paper",
        "in_paper_sample",
        "in_initial",
        "in_main",
        "in_strict",
        "n_paper",
        "n_paper_sample",
        "n_initial",
        "n_main",
        "n_strict",
    ]

    if not rows:
        return pd.DataFrame(columns=output_columns)

    out = pd.DataFrame(rows)
    out = out[output_columns].copy()
    out = out.sort_values(["comparison", "repo_name"]).reset_index(drop=True)

    return out


# ----------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------

def write_clean_csv(path: Path, df: pd.DataFrame) -> None:
    """
    Write the actual CSV.

    This CSV intentionally has no note column and no metadata comments.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_metadata_txt(
    path: Path,
    args: argparse.Namespace,
    project_root: Path,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    diff_df: pd.DataFrame,
) -> None:
    """
    Write a human-readable metadata file.

    All explanatory notes are stored here rather than in the CSV table.
    """
    lines: List[str] = []

    lines.append("File: jsts_repo_set_differences.csv")
    lines.append("---")
    lines.append("Purpose")
    lines.append(
        "Compare treatment/control repository set differences across paper "
        "baseline JS/TS matching, our main JS/TS pairs, and our strict 1:3 "
        "JS/TS pairs."
    )
    lines.append("")
    lines.append("Important interpretation")
    lines.append(
        "The paper uses 1:3 nearest-neighbor matching, meaning three matched "
        "control slots per treated repository. The same control repository may "
        "be reused across multiple treatment repositories."
    )
    lines.append("")
    lines.append(
        "This file is focused on repository-set differences. It does not compare "
        "panel row counts directly. For dataset-size comparison, use "
        "jsts_dataset_size_comparison.csv."
    )
    lines.append("")
    lines.append("---")
    lines.append("Stage notes")

    for alias, stage_key in STAGE_ALIAS_TO_KEY.items():
        if alias in stage_stats_by_alias:
            lines.append(f"{alias:<13} - {STAGE_NOTES[stage_key]}")

    lines.append("")
    lines.append("---")
    lines.append("Columns")
    lines.append("comparison     - Set-difference label, such as paper_treatment_minus_strict_treatment.")
    lines.append("left_stage     - Left-side stage alias in the set difference.")
    lines.append("right_stage    - Right-side stage alias in the set difference.")
    lines.append("role           - Repository role being compared: treatment or control.")
    lines.append("repo_name      - GitHub repository full name.")
    lines.append("reason_code    - Pipeline-stage diagnostic reason code.")
    lines.append("in_paper       - Whether the repo appears in the paper JS/TS matching stage for this role.")
    lines.append("in_paper_sample - Whether the repo appears in paper matching restricted to our JS/TS sample for this role.")
    lines.append("in_initial     - Whether the repo appears in our initially extracted pair stage for this role.")
    lines.append("in_main        - Whether the repo appears in our main final-clean pair stage for this role.")
    lines.append("in_strict      - Whether the repo appears in our strict 1:3 pair stage for this role.")
    lines.append("n_paper        - Link count in paper stage. For treatment, number of controls; for control, number of treatments.")
    lines.append("n_paper_sample - Link count in paper_sample stage. Same meaning as n_paper.")
    lines.append("n_initial      - Link count in initial stage. Same meaning as n_paper.")
    lines.append("n_main         - Link count in main stage. Same meaning as n_paper.")
    lines.append("n_strict       - Link count in strict stage. Same meaning as n_paper.")
    lines.append("")
    lines.append("---")
    lines.append("Reason codes")
    lines.append("less_than_3_final_controls_after_filtering - Treatment is in main but not strict because it has fewer than 3 final controls.")
    lines.append("control_removed_when_strict_dropped_treatments - Control is in main but not strict because strict removed the associated treatment(s).")
    lines.append("paper_jsts_treatment_not_in_our_jsts_sample - Paper JS/TS treatment is not in our JS/TS treatment sample file.")
    lines.append("paper_jsts_control_not_matched_to_our_jsts_sample - Paper JS/TS control is not linked to our JS/TS treatment sample.")
    lines.append("not_in_our_initial_extracted_pairs - Repository is absent from our initial extracted pair stage.")
    lines.append("removed_before_main_final_clean_pairs - Repository disappears before our main final-clean pair stage.")
    lines.append("removed_after_initial_pair_extraction - Repository is in initial pairs but not in main final-clean pairs.")
    lines.append("present_in_strict_but_not_in_paper_jsts_reference - Repository appears in strict but not in paper JS/TS reference.")
    lines.append("present_in_main_but_not_in_paper_jsts_reference - Repository appears in main but not in paper JS/TS reference.")
    lines.append("present_in_strict_but_not_in_main_unexpected - Repository appears in strict but not in main; this should normally be zero.")
    lines.append("stage_membership_difference - Generic stage-membership difference.")
    lines.append("")
    lines.append("---")
    lines.append("Comparison counts")

    if diff_df.empty:
        lines.append("No set differences were found.")
    else:
        counts = diff_df.groupby("comparison").size().reset_index(name="count")
        for _, row in counts.iterrows():
            lines.append(f"{row['comparison']:<55} {int(row['count'])}")

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
    lines.append("Output files")
    lines.append(f"csv: {args.csv_name}")
    lines.append(f"metadata: {args.metadata_name}")
    lines.append("")
    lines.append("---")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("Generated by: compare_jsts_03_repo_set_differences.py")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Defaults are based on the current JS/TS replication workspace.
    """
    script_path = Path(__file__).resolve()
    project_root = find_project_root(script_path)

    parser = argparse.ArgumentParser(
        description=(
            "Create jsts_repo_set_differences.csv and "
            "jsts_repo_set_differences-metadata.txt."
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
            "If missing, paper_sample comparisons are skipped."
        ),
    )

    parser.add_argument(
        "--our-initial-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv",
        help=(
            "Optional initially extracted JS/TS pair file. "
            "If missing, initial comparisons are skipped."
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
        default=str(script_path.parent),
        help=(
            "Output directory for both CSV and metadata files. "
            "Default is the same directory as this script."
        ),
    )

    parser.add_argument(
        "--csv-name",
        default="jsts_repo_set_differences.csv",
        help="Output CSV filename.",
    )

    parser.add_argument(
        "--metadata-name",
        default="jsts_repo_set_differences-metadata.txt",
        help="Output metadata filename.",
    )

    args = parser.parse_args()
    args.project_root = str(project_root)

    return args


def main() -> None:
    args = parse_args()

    project_root = Path(args.project_root)
    out_dir = resolve_path(args.out_dir, project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / args.csv_name
    out_metadata = out_dir / args.metadata_name

    stage_stats_by_alias = build_stage_stats_by_alias(
        args=args,
        project_root=project_root,
    )

    diff_df = build_repo_set_differences(stage_stats_by_alias)

    write_clean_csv(out_csv, diff_df)

    write_metadata_txt(
        path=out_metadata,
        args=args,
        project_root=project_root,
        stage_stats_by_alias=stage_stats_by_alias,
        diff_df=diff_df,
    )

    print("Repository-set difference comparison completed.")
    print(f"Output CSV: {out_csv}")
    print(f"Output metadata: {out_metadata}")
    print("")

    if diff_df.empty:
        print("No set differences found.")
    else:
        summary = diff_df.groupby("comparison").size().reset_index(name="count")
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
