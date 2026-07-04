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
