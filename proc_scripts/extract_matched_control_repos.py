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
