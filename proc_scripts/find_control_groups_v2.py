#!/usr/bin/env python3
"""
Find matched control repositories using existing GHArchive CSV files.

This script does NOT call BigQuery.

Inputs:
- treatment repo list: tmp_adoption_test/data/ai_adopt_repo_python.csv
- treatment raw events: data/repo_events.csv
- existing control candidates: data/control_repo_candidates_YYYYMM.csv

Output:
- tmp_adoption_test/data/matched_controls_v2_summary.csv
- tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
- tmp_adoption_test/data/matched_controls_v2_pairs.csv
- tmp_adoption_test/data/control_repos_to_clone_v2.txt
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.matching_complex as mc  # noqa: E402


METRIC_COLUMNS = [
    "age_days",
    "users_involved",
    "n_stars",
    "n_forks",
    "n_releases",
    "n_pulls",
    "n_issues",
    "n_comments",
    "total_events",
]


def event_month_to_yyyymm(value: str) -> str:
    return pd.to_datetime(str(value)).strftime("%Y%m")


def load_treatment_repos(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = ["repo_name", "event_month", "repo_primary_language"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns in {path}: {missing}")

    df = df.copy()
    df["adoption_month"] = df["event_month"].map(event_month_to_yyyymm)
    df["repo_cursor_adoption"] = pd.to_datetime(df["event_month"])

    # Keep only one row per repo.
    df = df.drop_duplicates(subset=["repo_name"], keep="first")

    logging.info("Loaded %d treatment repos from %s", len(df), path)
    logging.info("Treatment months: %s", sorted(df["adoption_month"].unique()))

    return df


def load_filtered_events(events_path: Path, treatment_repos: set[str]) -> pd.DataFrame:
    """Load only event rows for selected treatment repos from large repo_events.csv."""
    usecols = ["type", "created_at", "repo", "actor"]
    chunks = []

    logging.info("Reading treatment events from %s", events_path)

    for chunk in pd.read_csv(events_path, usecols=usecols, chunksize=1_000_000):
        sub = chunk[chunk["repo"].isin(treatment_repos)]
        if not sub.empty:
            chunks.append(sub)

    if not chunks:
        raise SystemExit("No treatment events found in repo_events.csv")

    events = pd.concat(chunks, ignore_index=True)
    events["created_at"] = pd.to_datetime(events["created_at"]).dt.tz_localize(None)
    events["month"] = events["created_at"].dt.strftime("%Y%m")

    logging.info(
        "Loaded %d treatment event rows for %d repos",
        len(events),
        events["repo"].nunique(),
    )

    return events


def numeric_cleanup(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in METRIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def sample_control_repos(control: pd.DataFrame, max_repos: int, seed: int) -> pd.DataFrame:
    """Sample unique control repos, then keep all period rows for sampled repos."""
    unique_repos = pd.Series(control["repo_name"].dropna().unique())

    if len(unique_repos) <= max_repos:
        sampled_repos = set(unique_repos)
    else:
        sampled_repos = set(unique_repos.sample(n=max_repos, random_state=seed))

    sampled = control[control["repo_name"].isin(sampled_repos)].copy()

    logging.info(
        "Sampled %d unique control repos -> %d period rows",
        sampled["repo_name"].nunique(),
        len(sampled),
    )

    return sampled


def make_pairs(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []

    treatment = summary[summary["group"] == "treatment"].copy()

    for _, row in treatment.iterrows():
        for rank in [1, 2, 3]:
            col = f"matched_control_{rank}"
            control_repo = row.get(col, "")
            if pd.isna(control_repo) or str(control_repo).strip() == "":
                continue

            rows.append(
                {
                    "treatment_repo": row["repo_name"],
                    "matched_period": row["matched_period"],
                    "treatment_propensity_score": row["propensity_score"],
                    "match_rank": rank,
                    "control_repo": control_repo,
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--treatment-csv",
        default="tmp_adoption_test/data/ai_adopt_repo_python.csv",
    )
    parser.add_argument("--events-csv", default="data/repo_events.csv")
    parser.add_argument("--control-dir", default="data")
    parser.add_argument("--output-dir", default="tmp_adoption_test/data")
    parser.add_argument("--max-control-repos", type=int, default=10000)
    parser.add_argument("--random-state", type=int, default=42)

    language_group = parser.add_mutually_exclusive_group()
    language_group.add_argument(
        "--language-matching",
        action="store_true",
        default=True,
        help="Use GitHub API to require same primary language for matched controls.",
    )
    language_group.add_argument(
        "--no-language-matching",
        action="store_false",
        dest="language_matching",
        help="Disable language matching for a fast first run.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    treatment_path = PROJECT_ROOT / args.treatment_csv
    events_path = PROJECT_ROOT / args.events_csv
    control_dir = PROJECT_ROOT / args.control_dir
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure matching_complex globals.
    mc.CONTROL_REPOS_DIR = control_dir
    mc.MAX_CONTROL_REPOS = args.max_control_repos
    mc.USE_LANGUAGE_MATCHING = args.language_matching

    treatment_meta = load_treatment_repos(treatment_path)
    all_treatment_repos = set(treatment_meta["repo_name"])

    # matching_complex.perform_nearest_neighbor_matching reads mc.REPOS_FILE
    # only to get treatment repo language. Give it a small clean metadata file.
    temp_repos_file = output_dir / "treatment_repos_for_matching_v2.csv"
    treatment_meta[
        ["repo_name", "repo_primary_language", "event_month", "adoption_month"]
    ].to_csv(temp_repos_file, index=False)
    mc.REPOS_FILE = temp_repos_file

    events = load_filtered_events(events_path, all_treatment_repos)

    treatment_metrics = mc.compute_repo_metrics(events, treatment_meta)
    treatment_metrics = numeric_cleanup(treatment_metrics)

    found_metric_repos = set(treatment_metrics["repo_name"].unique())
    missing_metric_repos = sorted(all_treatment_repos - found_metric_repos)
    if missing_metric_repos:
        logging.warning("Treatment repos with no computed metrics: %s", missing_metric_repos)

    all_propensity = []

    for month in sorted(treatment_meta["adoption_month"].unique()):
        logging.info("=== Matching month %s ===", month)

        month_treatment_repos = set(
            treatment_meta.loc[
                treatment_meta["adoption_month"] == month, "repo_name"
            ]
        )

        treat = treatment_metrics[
            treatment_metrics["repo_name"].isin(month_treatment_repos)
        ].copy()

        if treat.empty:
            logging.warning("No treatment metrics for month %s; skipping", month)
            continue

        control = mc.load_control_repos(month)
        if control.empty:
            logging.warning("No control candidates for month %s; skipping", month)
            continue

        # Critical leakage prevention:
        # remove ALL 13 treatment repos from the control pool, not just same-month treatment repos.
        before_unique = control["repo_name"].nunique()
        control = control[~control["repo_name"].isin(all_treatment_repos)].copy()
        after_unique = control["repo_name"].nunique()
        logging.info(
            "Removed treatment repos from control pool: %d -> %d unique repos",
            before_unique,
            after_unique,
        )

        control = numeric_cleanup(control)
        control = sample_control_repos(
            control,
            max_repos=args.max_control_repos,
            seed=args.random_state,
        )

        logging.info(
            "Treatment repos this month: %d; control repos sampled: %d",
            treat["repo_name"].nunique(),
            control["repo_name"].nunique(),
        )

        propensity_df = mc.compute_propensity_scores(treat.copy(), control.copy())
        propensity_df["adoption_month"] = month
        all_propensity.append(propensity_df)

    if not all_propensity:
        raise SystemExit("No propensity score results were produced.")

    logging.info("Creating matching summary")
    summary = mc.create_matching_summary(all_propensity)

    # Add event/adoption metadata for treatment rows.
    treatment_lookup = treatment_meta[
        ["repo_name", "event_month", "adoption_month", "repo_primary_language"]
    ].drop_duplicates()

    summary = summary.merge(treatment_lookup, on="repo_name", how="left")

    summary_path = output_dir / "matched_controls_v2_summary.csv"
    treatment_only_path = output_dir / "matched_controls_v2_treatment_only.csv"
    pairs_path = output_dir / "matched_controls_v2_pairs.csv"
    clone_list_path = output_dir / "control_repos_to_clone_v2.txt"

    summary.to_csv(summary_path, index=False)

    treatment_only = summary[summary["group"] == "treatment"].copy()
    treatment_only.to_csv(treatment_only_path, index=False)

    pairs = make_pairs(summary)
    pairs.to_csv(pairs_path, index=False)

    control_repos = sorted(pairs["control_repo"].dropna().unique()) if not pairs.empty else []
    clone_list_path.write_text("\n".join(control_repos) + ("\n" if control_repos else ""))

    logging.info("Saved summary: %s", summary_path)
    logging.info("Saved treatment-only matches: %s", treatment_only_path)
    logging.info("Saved matched pairs: %s", pairs_path)
    logging.info("Saved clone list: %s", clone_list_path)
    logging.info("Unique control repos to clone: %d", len(control_repos))

    print("\n=== Treatment matches ===")
    cols = [
        "repo_name",
        "event_month",
        "matched_period",
        "propensity_score",
        "matched_control_1",
        "matched_control_2",
        "matched_control_3",
    ]
    existing_cols = [c for c in cols if c in treatment_only.columns]
    print(treatment_only[existing_cols].to_string(index=False))

    print("\n=== Clone list ===")
    for repo in control_repos:
        print(repo)


if __name__ == "__main__":
    main()
