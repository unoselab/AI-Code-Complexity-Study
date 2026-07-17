#!/usr/bin/env python3
"""
Create paper-minus-strict treatment-reason outputs.

This script creates two files in the same directory as this script by default:

  1. jsts_paper_minus_strict_treatment_reasons.csv
  2. jsts_paper_minus_strict_treatment_reasons-metadata.txt

Main purpose
------------
This script explains treatment repository attrition from:

  paper JS/TS treatment repositories
  to
  our strict 1:3 JS/TS treatment repositories

The key question is:

  Which paper JS/TS treatment repositories are missing from our
  strict_1to3 pair set, and why?

Important output design
-----------------------
The actual CSV is kept clean and analysis-friendly.
It does NOT include a note column.

All explanations, stage descriptions, column meanings, and reason-code
definitions are stored in the metadata text file.

Default output directory
------------------------
By default, outputs are written into this script directory:

  proc_scripts/compare-04/
    compare_jsts_04_treatment_reasons.py
    jsts_paper_minus_strict_treatment_reasons.csv
    jsts_paper_minus_strict_treatment_reasons-metadata.txt
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
# These candidates make the script robust to small column-name differences
# across baseline files and generated pair files.

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
    "matched_repo",
]

# ----------------------------------------------------------------------
# Stage notes
# ----------------------------------------------------------------------
# These explanations are written to the metadata file only.
# They are not stored as a note column in the actual CSV.

STAGE_NOTES = {
    "paper": (
        "Baseline paper matching.csv restricted to JS/TS treatment repositories "
        "identified from data_baseline_backup/repos.csv."
    ),
    "paper_sample": (
        "Baseline paper matching.csv restricted to our JS/TS treatment sample. "
        "This separates paper-vs-our-sample differences from later filtering."
    ),
    "initial": (
        "Our initially extracted JS/TS treatment-control pairs, before later "
        "clone/local-Cursor filtering, if the file exists."
    ),
    "main": (
        "Our main final-clean JS/TS pair file. This may include treatments with "
        "1, 2, or 3 final controls."
    ),
    "strict": (
        "Our strict 1:3 JS/TS pair file. This should keep only treatments with "
        "exactly 3 final controls."
    ),
}

REASON_CODE_NOTES = {
    "paper_jsts_treatment_not_in_our_jsts_sample": (
        "The treatment exists in the paper JS/TS treatment set, but it is absent "
        "from our JS/TS treatment sample file."
    ),
    "not_in_our_initial_extracted_pairs": (
        "The treatment exists in the paper-side sample comparison, but it is "
        "absent from our initially extracted pair file."
    ),
    "removed_before_main_final_clean_pairs": (
        "The treatment does not appear in our main final-clean pair stage."
    ),
    "less_than_3_final_controls_after_filtering": (
        "The treatment appears in our main final-clean pairs but has fewer than "
        "3 final controls, so it is removed from strict 1:3."
    ),
    "not_in_strict_even_though_main_has_3_controls": (
        "The treatment appears in main with at least 3 controls but is not in "
        "strict. This is unexpected and should be inspected."
    ),
    "strict_stage_attrition_unknown": (
        "The treatment is absent from strict, but the available stage information "
        "does not identify a more specific reason."
    ),
}

# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------

def find_project_root(start: Path) -> Path:
    """
    Find the project root by walking upward from the script path.

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

    # Fallback for proc_scripts/compare-04/script.py.
    return start.resolve().parents[2]

def resolve_path(path_text: str, project_root: Path) -> Path:
    """
    Resolve path_text.

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

    Missing required files should stop execution because the output would be
    incomplete or misleading.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path)

def read_csv_optional(path: Path) -> Optional[pd.DataFrame]:
    """
    Read an optional CSV file.

    Optional stages are skipped when the file does not exist.
    """
    if not path.exists():
        return None

    return pd.read_csv(path)

# ----------------------------------------------------------------------
# Column helpers
# ----------------------------------------------------------------------

def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """
    Return the first column from candidates that exists in df.
    """
    columns = set(df.columns)

    for col in candidates:
        if col in columns:
            return col

    return None

def normalize_repo_series(series: pd.Series) -> pd.Series:
    """
    Normalize repository names for reliable set comparisons.
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
    Extract JS/TS treatment repositories from paper repository metadata.

    The baseline repos.csv is expected to contain treatment repository metadata.
    We keep repositories whose primary language is JavaScript or TypeScript.
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
    Extract a repository-name set from a CSV file.
    """
    repo_col = get_repo_col(df)
    return set(normalize_repo_series(df[repo_col]))

# ----------------------------------------------------------------------
# Pair conversion helpers
# ----------------------------------------------------------------------

def sort_matched_control_columns(cols: List[str]) -> List[str]:
    """
    Sort matched-control columns by their numeric suffix.

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
    Convert baseline wide matching.csv into long pair format.

    Expected input shape:
      repo_name, matched_control_1, matched_control_2, matched_control_3

    Output shape:
      treatment_repo, control_repo, control_rank

    treatment_filter:
      If provided, keep only rows whose treatment repository is in the filter.
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

    Expected input columns:
      treatment_repo, control_repo

    If the rank is missing, this function reconstructs a simple control_rank
    after sorting.
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
    Build treatment-level statistics for one pair stage.

    treatment_set:
      Unique treatment repositories in this stage.

    control_map:
      treatment_repo -> sorted list of unique matched controls.

    control_count_map:
      treatment_repo -> number of unique matched controls.
    """
    clean_pairs = pairs[["treatment_repo", "control_repo"]].drop_duplicates().copy()

    treatment_set = set(clean_pairs["treatment_repo"])

    control_map = (
        clean_pairs.groupby("treatment_repo")["control_repo"]
        .apply(lambda values: sorted(set(values)))
        .to_dict()
    )

    control_count_map = {
        treatment_repo: len(controls)
        for treatment_repo, controls in control_map.items()
    }

    return {
        "pairs": clean_pairs,
        "treatment_set": treatment_set,
        "control_map": control_map,
        "control_count_map": control_count_map,
    }

def repo_in_stage(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    repo_name: str,
) -> bool:
    """
    Return True if a treatment repository appears in a stage.
    """
    if alias not in stage_stats_by_alias:
        return False

    return repo_name in stage_stats_by_alias[alias]["treatment_set"]

def get_control_count(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    repo_name: str,
) -> int:
    """
    Return the number of controls linked to a treatment in a stage.
    """
    if alias not in stage_stats_by_alias:
        return 0

    return int(
        stage_stats_by_alias[alias]["control_count_map"].get(repo_name, 0)
    )

def get_control_list_text(
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    alias: str,
    repo_name: str,
) -> str:
    """
    Return a semicolon-separated list of controls for a treatment in a stage.
    """
    if alias not in stage_stats_by_alias:
        return ""

    controls = stage_stats_by_alias[alias]["control_map"].get(repo_name, [])
    return ";".join(controls)

# ----------------------------------------------------------------------
# Reason-code logic
# ----------------------------------------------------------------------

def infer_treatment_reason_code(
    repo_name: str,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
) -> str:
    """
    Infer why a paper JS/TS treatment repository is missing from strict 1:3.

    This reason code is a pipeline-stage diagnostic. It is not a perfect causal
    diagnosis, but it explains where the treatment disappears across available
    comparison stages.
    """
    in_paper_sample = repo_in_stage(stage_stats_by_alias, "paper_sample", repo_name)
    in_initial = repo_in_stage(stage_stats_by_alias, "initial", repo_name)
    in_main = repo_in_stage(stage_stats_by_alias, "main", repo_name)
    in_strict = repo_in_stage(stage_stats_by_alias, "strict", repo_name)

    paper_sample_available = "paper_sample" in stage_stats_by_alias
    initial_available = "initial" in stage_stats_by_alias

    if in_strict:
        return "present_in_strict_unexpected_for_minus_set"

    if paper_sample_available and not in_paper_sample:
        return "paper_jsts_treatment_not_in_our_jsts_sample"

    if initial_available and not in_initial:
        return "not_in_our_initial_extracted_pairs"

    if not in_main:
        return "removed_before_main_final_clean_pairs"

    main_control_count = get_control_count(
        stage_stats_by_alias,
        "main",
        repo_name,
    )

    if in_main and not in_strict:
        if main_control_count < 3:
            return "less_than_3_final_controls_after_filtering"

        return "not_in_strict_even_though_main_has_3_controls"

    return "strict_stage_attrition_unknown"

# ----------------------------------------------------------------------
# Build stages and output table
# ----------------------------------------------------------------------

def build_stage_stats_by_alias(
    args: argparse.Namespace,
    project_root: Path,
) -> Dict[str, Dict[str, object]]:
    """
    Load all available stages and return treatment-stage statistics.

    Stages:
      paper        - paper matching restricted to paper JS/TS treatments
      paper_sample - paper matching restricted to our JS/TS sample
      initial      - our initial extracted pairs
      main         - our main final-clean pairs
      strict       - our strict 1:3 pairs
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

    # Stage 1: paper matching restricted to paper JS/TS treatment repos.
    paper_jsts_treatment_repos = get_jsts_repos_from_metadata(paper_repos)

    paper_jsts_pairs = wide_matching_to_long_pairs(
        paper_matching,
        treatment_filter=paper_jsts_treatment_repos,
    )

    stage_stats_by_alias["paper"] = build_stage_stats(paper_jsts_pairs)

    # Stage 2: paper matching restricted to our JS/TS treatment sample.
    # This is optional because the sample file may not exist in every workspace.
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

    # Stage 3: our initially extracted JS/TS pair file.
    # This is optional because some workspaces may only keep final-clean files.
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

def build_treatment_reason_table(
    stage_stats_by_alias: Dict[str, Dict[str, object]]
) -> pd.DataFrame:
    """
    Build the actual CSV table.

    The target set is:

      paper treatment set - strict treatment set

    Each row is one paper JS/TS treatment repository that is missing from
    our strict 1:3 treatment set.
    """
    paper_treatments = set(stage_stats_by_alias["paper"]["treatment_set"])
    strict_treatments = set(stage_stats_by_alias["strict"]["treatment_set"])

    missing_treatments = sorted(paper_treatments - strict_treatments)

    rows: List[Dict[str, object]] = []

    for repo_name in missing_treatments:
        rows.append(
            {
                "repo_name": repo_name,
                "reason_code": infer_treatment_reason_code(
                    repo_name,
                    stage_stats_by_alias,
                ),
                "in_paper_sample": repo_in_stage(
                    stage_stats_by_alias,
                    "paper_sample",
                    repo_name,
                ),
                "in_initial": repo_in_stage(
                    stage_stats_by_alias,
                    "initial",
                    repo_name,
                ),
                "in_main": repo_in_stage(
                    stage_stats_by_alias,
                    "main",
                    repo_name,
                ),
                "in_strict": repo_in_stage(
                    stage_stats_by_alias,
                    "strict",
                    repo_name,
                ),
                "n_paper_ctrl": get_control_count(
                    stage_stats_by_alias,
                    "paper",
                    repo_name,
                ),
                "n_paper_sample_ctrl": get_control_count(
                    stage_stats_by_alias,
                    "paper_sample",
                    repo_name,
                ),
                "n_initial_ctrl": get_control_count(
                    stage_stats_by_alias,
                    "initial",
                    repo_name,
                ),
                "n_main_ctrl": get_control_count(
                    stage_stats_by_alias,
                    "main",
                    repo_name,
                ),
                "n_strict_ctrl": get_control_count(
                    stage_stats_by_alias,
                    "strict",
                    repo_name,
                ),
                "paper_controls": get_control_list_text(
                    stage_stats_by_alias,
                    "paper",
                    repo_name,
                ),
                "paper_sample_controls": get_control_list_text(
                    stage_stats_by_alias,
                    "paper_sample",
                    repo_name,
                ),
                "initial_controls": get_control_list_text(
                    stage_stats_by_alias,
                    "initial",
                    repo_name,
                ),
                "main_controls": get_control_list_text(
                    stage_stats_by_alias,
                    "main",
                    repo_name,
                ),
                "strict_controls": get_control_list_text(
                    stage_stats_by_alias,
                    "strict",
                    repo_name,
                ),
            }
        )

    output_columns = [
        "repo_name",
        "reason_code",
        "in_paper_sample",
        "in_initial",
        "in_main",
        "in_strict",
        "n_paper_ctrl",
        "n_paper_sample_ctrl",
        "n_initial_ctrl",
        "n_main_ctrl",
        "n_strict_ctrl",
        "paper_controls",
        "paper_sample_controls",
        "initial_controls",
        "main_controls",
        "strict_controls",
    ]

    if not rows:
        return pd.DataFrame(columns=output_columns)

    out = pd.DataFrame(rows)
    out = out[output_columns].copy()
    out = out.sort_values(["reason_code", "repo_name"]).reset_index(drop=True)

    return out

# ----------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------

def write_clean_csv(path: Path, df: pd.DataFrame) -> None:
    """
    Write the actual CSV.

    The CSV intentionally has no note column and no metadata comments.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

def write_metadata_txt(
    path: Path,
    args: argparse.Namespace,
    project_root: Path,
    stage_stats_by_alias: Dict[str, Dict[str, object]],
    reason_df: pd.DataFrame,
) -> None:
    """
    Write the metadata text file.

    This file stores all explanations that should not be placed in the CSV.
    """
    lines: List[str] = []

    lines.append("File: jsts_paper_minus_strict_treatment_reasons.csv")
    lines.append("---")
    lines.append("Purpose")
    lines.append(
        "Explain why paper JS/TS treatment repositories are missing from our "
        "strict 1:3 JS/TS treatment set."
    )
    lines.append("")
    lines.append("Important interpretation")
    lines.append(
        "The paper uses 1:3 nearest-neighbor matching, meaning three matched "
        "control slots per treated repository. Our strict 1:3 pair set keeps "
        "only treatments that still have exactly three final controls after "
        "replication filtering."
    )
    lines.append("")
    lines.append(
        "This file focuses only on treatment repositories in "
        "paper_treatment_minus_strict_treatment."
    )
    lines.append("")
    lines.append("---")
    lines.append("Stage notes")

    for alias in ["paper", "paper_sample", "initial", "main", "strict"]:
        if alias in stage_stats_by_alias:
            lines.append(f"{alias:<13} - {STAGE_NOTES[alias]}")

    lines.append("")
    lines.append("---")
    lines.append("Columns")
    lines.append("repo_name             - GitHub repository full name.")
    lines.append("reason_code           - Diagnostic reason code explaining why the treatment is missing from strict.")
    lines.append("in_paper_sample       - Whether the treatment appears in paper matching restricted to our JS/TS sample.")
    lines.append("in_initial            - Whether the treatment appears in our initially extracted JS/TS pair file.")
    lines.append("in_main               - Whether the treatment appears in our main final-clean pair file.")
    lines.append("in_strict             - Whether the treatment appears in our strict 1:3 pair file. This should be False for all rows.")
    lines.append("n_paper_ctrl          - Number of controls for this treatment in the paper JS/TS matching stage.")
    lines.append("n_paper_sample_ctrl   - Number of controls for this treatment in the paper matching restricted to our JS/TS sample.")
    lines.append("n_initial_ctrl        - Number of controls for this treatment in our initial extracted pair stage.")
    lines.append("n_main_ctrl           - Number of final controls for this treatment in our main final-clean pair stage.")
    lines.append("n_strict_ctrl         - Number of controls for this treatment in our strict 1:3 pair stage.")
    lines.append("paper_controls        - Semicolon-separated controls in the paper JS/TS matching stage.")
    lines.append("paper_sample_controls - Semicolon-separated controls in the paper matching restricted to our JS/TS sample.")
    lines.append("initial_controls      - Semicolon-separated controls in our initial extracted pair stage.")
    lines.append("main_controls         - Semicolon-separated controls in our main final-clean pair stage.")
    lines.append("strict_controls       - Semicolon-separated controls in our strict 1:3 pair stage.")
    lines.append("")
    lines.append("---")
    lines.append("Reason codes")

    for reason_code, explanation in REASON_CODE_NOTES.items():
        lines.append(f"{reason_code} - {explanation}")

    lines.append("")
    lines.append("---")
    lines.append("Reason-code counts")

    if reason_df.empty:
        lines.append("No paper-minus-strict treatment differences were found.")
    else:
        counts = reason_df.groupby("reason_code").size().reset_index(name="count")
        for _, row in counts.iterrows():
            lines.append(f"{row['reason_code']:<55} {int(row['count'])}")

    lines.append("")
    lines.append("---")
    lines.append("Stage sizes")

    for alias in ["paper", "paper_sample", "initial", "main", "strict"]:
        if alias not in stage_stats_by_alias:
            continue

        treatment_count = len(stage_stats_by_alias[alias]["treatment_set"])
        pair_count = len(stage_stats_by_alias[alias]["pairs"])
        lines.append(
            f"{alias:<13} treatment_repos={treatment_count}, pair_rows={pair_count}"
        )

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
    lines.append("Generated by: compare_jsts_04_treatment_reasons.py")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    script_path = Path(__file__).resolve()
    project_root = find_project_root(script_path)
    default_out_dir = script_path.parent

    parser = argparse.ArgumentParser(
        description=(
            "Create jsts_paper_minus_strict_treatment_reasons.csv and "
            "jsts_paper_minus_strict_treatment_reasons-metadata.txt."
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
            "If missing, paper_sample stage is skipped."
        ),
    )

    parser.add_argument(
        "--our-initial-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv",
        help=(
            "Optional initially extracted JS/TS pair file. "
            "If missing, initial stage is skipped."
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
            "Output directory. Default is this script directory, matching "
            "the compare-01 structure."
        ),
    )

    parser.add_argument(
        "--csv-name",
        default="jsts_paper_minus_strict_treatment_reasons.csv",
        help="Output CSV filename.",
    )

    parser.add_argument(
        "--metadata-name",
        default="jsts_paper_minus_strict_treatment_reasons-metadata.txt",
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

    reason_df = build_treatment_reason_table(stage_stats_by_alias)

    write_clean_csv(out_csv, reason_df)

    write_metadata_txt(
        path=out_metadata,
        args=args,
        project_root=project_root,
        stage_stats_by_alias=stage_stats_by_alias,
        reason_df=reason_df,
    )

    print("Paper-minus-strict treatment-reason comparison completed.")
    print(f"Output CSV: {out_csv}")
    print(f"Output metadata: {out_metadata}")
    print("")

    if reason_df.empty:
        print("No paper-minus-strict treatment differences found.")
    else:
        counts = reason_df.groupby("reason_code").size().reset_index(name="count")
        print(counts.to_string(index=False))

if __name__ == "__main__":
    main()
