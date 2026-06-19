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
