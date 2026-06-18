#!/usr/bin/env python3
"""
Select clone candidates with enough pre- and post-Cursor-adoption coverage.

Runs BEFORE cloning, so it depends only on signals already available from
GH Archive collection (no SonarQube / cloned-repo metrics):

  - cursor_commits.csv : first Cursor commit per repo  -> adoption month
  - repo_events.csv    : raw events per repo            -> which months a repo
                         was observed/active

For every adopter we classify each observed month by time-to-event:

    time_to_event < 0   -> pre-adoption month
    time_to_event == 0  -> adoption month
    time_to_event > 0   -> post-adoption month

A repo qualifies if it has at least --min-pre pre months AND --min-post post
months. Qualifying repos are ranked by the most balanced / deepest window and
the top --n are written out as the clone list.

Optionally, --source ts uses ts_repos_monthly.csv instead of repo_events.csv to
define observed months (a month counts if the repo has a row that month; add
--require-activity to require commits > 0).
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd


# --------------------------------------------------------------------------- #
# Adoption month
# --------------------------------------------------------------------------- #
def adoption_month_from_cursor_commits(path: Path) -> pd.Series:
    """First Cursor commit per repo -> adoption month (pandas Period[M])."""
    cc = pd.read_csv(path, usecols=["repo_name", "authored_at"])
    cc["authored_at"] = pd.to_datetime(cc["authored_at"], errors="coerce", utc=True)
    cc = cc.dropna(subset=["authored_at"])
    first = cc.groupby("repo_name")["authored_at"].min()
    return first.dt.tz_convert(None).dt.to_period("M").rename("adoption_month")


def adoption_month_from_repo_metrics(path: Path) -> pd.Series:
    """Adoption month from repo_metrics.csv cursor_adoption_time (alternative)."""
    rm = pd.read_csv(path, usecols=["repo_name", "cursor_adoption_time"])
    rm["t"] = pd.to_datetime(rm["cursor_adoption_time"], errors="coerce")
    rm = rm.dropna(subset=["t"])
    return (
        rm.set_index("repo_name")["t"].dt.to_period("M").rename("adoption_month")
    )


# --------------------------------------------------------------------------- #
# Observed months
# --------------------------------------------------------------------------- #
def observed_months_from_events(path: Path, chunksize: int = 2_000_000) -> pd.DataFrame:
    """
    repo_events.csv -> one row per (repo, observed month) with an activity count.
    Read in chunks because this file can be very large (millions of rows).
    """
    parts = []
    for chunk in pd.read_csv(
        path, usecols=["created_at", "repo"], chunksize=chunksize
    ):
        chunk["month"] = (
            pd.to_datetime(chunk["created_at"], errors="coerce", utc=True)
            .dt.tz_convert(None)
            .dt.to_period("M")
        )
        chunk = chunk.dropna(subset=["month"])
        parts.append(
            chunk.groupby(["repo", "month"]).size().rename("activity").reset_index()
        )
    out = (
        pd.concat(parts, ignore_index=True)
        .groupby(["repo", "month"])["activity"]
        .sum()
        .reset_index()
        .rename(columns={"repo": "repo_name"})
    )
    return out


def observed_months_from_ts(path: Path, require_activity: bool) -> pd.DataFrame:
    """ts_repos_monthly.csv -> one row per (repo, observed month)."""
    ts = pd.read_csv(path, usecols=["repo_name", "month", "commits"])
    ts["month"] = pd.PeriodIndex(ts["month"], freq="M")
    ts["activity"] = ts["commits"].fillna(0)
    if require_activity:
        ts = ts[ts["activity"] > 0]
    return ts[["repo_name", "month", "activity"]]


# --------------------------------------------------------------------------- #
# Coverage + selection (pure, easy to test)
# --------------------------------------------------------------------------- #
def build_coverage(
    observed: pd.DataFrame, adoption: pd.Series
) -> pd.DataFrame:
    """
    Join observed months to each repo's adoption month, classify by
    time_to_event, and summarise pre/post coverage per repo.
    """
    df = observed.merge(
        adoption.reset_index(), on="repo_name", how="inner"
    )  # inner -> adopters only
    df["tte"] = (df["month"] - df["adoption_month"]).apply(lambda x: x.n)

    g = df.groupby("repo_name")
    cov = pd.DataFrame(
        {
            "adoption_month": g["adoption_month"].first().astype(str),
            "n_pre": g["tte"].apply(lambda s: int((s < 0).sum())),
            "n_post": g["tte"].apply(lambda s: int((s > 0).sum())),
            "has_adoption_obs": g["tte"].apply(lambda s: bool((s == 0).any())),
            "n_obs_months": g.size(),
            "total_activity": g["activity"].sum(),
        }
    )
    cov["balance"] = cov[["n_pre", "n_post"]].min(axis=1)
    cov["window"] = cov["n_pre"] + cov["n_post"]
    return cov.reset_index()


def select_candidates(
    cov: pd.DataFrame, min_pre: int, min_post: int, n: int
) -> pd.DataFrame:
    """Filter on min pre/post, rank by balanced/deepest window, take top n."""
    qualifying = cov[(cov["n_pre"] >= min_pre) & (cov["n_post"] >= min_post)].copy()
    ranked = qualifying.sort_values(
        ["balance", "window", "total_activity"], ascending=False
    ).reset_index(drop=True)
    ranked.insert(0, "rank", ranked.index + 1)
    return ranked.head(n)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path("data_baseline_backup"))
    p.add_argument("--source", choices=["events", "ts"], default="events",
                   help="Define observed months from raw events (pre-clone) or ts_repos_monthly.")
    p.add_argument("--adoption-source", choices=["cursor_commits", "repo_metrics"],
                   default="cursor_commits")
    p.add_argument("--min-pre", type=int, default=3)
    p.add_argument("--min-post", type=int, default=3)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--require-activity", action="store_true",
                   help="With --source ts, only count months with commits > 0.")
    p.add_argument("--out", type=Path, default=Path("clone_candidates.csv"))
    args = p.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    dd = args.data_dir
    if args.adoption_source == "cursor_commits":
        adoption = adoption_month_from_cursor_commits(dd / "cursor_commits.csv")
    else:
        adoption = adoption_month_from_repo_metrics(dd / "repo_metrics.csv")
    logging.info("Adopters with an adoption month: %d", adoption.index.nunique())

    if args.source == "events":
        observed = observed_months_from_events(dd / "repo_events.csv")
    else:
        observed = observed_months_from_ts(
            dd / "ts_repos_monthly.csv", args.require_activity
        )
    logging.info("Observed repo-months: %d (repos: %d)",
                 len(observed), observed["repo_name"].nunique())

    cov = build_coverage(observed, adoption)
    logging.info("Adopters with any observed months: %d", len(cov))

    candidates = select_candidates(cov, args.min_pre, args.min_post, args.n)

    n_qual = ((cov["n_pre"] >= args.min_pre) & (cov["n_post"] >= args.min_post)).sum()
    logging.info(
        "Qualifying (>=%d pre & >=%d post): %d | selected: %d",
        args.min_pre, args.min_post, n_qual, len(candidates),
    )
    if len(candidates) < args.n:
        logging.warning(
            "Only %d candidates meet the bar (<%d). Lower --min-pre/--min-post.",
            len(candidates), args.n,
        )

    candidates.to_csv(args.out, index=False)
    logging.info("Wrote %d candidates to %s", len(candidates), args.out)
    logging.info("Balance range in selection: %d..%d pre/post months",
                 candidates["balance"].min(), candidates["balance"].max())


if __name__ == "__main__":
    main()