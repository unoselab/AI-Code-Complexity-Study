#!/usr/bin/env python3
"""
Small, safe GHArchive BigQuery test.

Default behavior:
- Dry run only
- One small date range
- 1 to 3 repos
- No full GHArchive scan

Use --execute only after checking dry-run bytes.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
from google.cloud import bigquery


QUERY = """
SELECT
  type,
  created_at,
  repo.name AS repo,
  actor.login AS actor
FROM `githubarchive.day.20*`
WHERE _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix
  AND repo.name IN UNNEST(@repos)
ORDER BY repo, created_at
"""


def to_suffix(date_string: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD."""
    return date_string.replace("-", "")[2:]


def load_repos(args: argparse.Namespace) -> list[str]:
    repos: list[str] = []

    if args.repo:
        repos.extend(args.repo)

    if args.repos_file:
        path = Path(args.repos_file)
        df = pd.read_csv(path)

        if "repo_name" not in df.columns:
            raise SystemExit(f"Missing repo_name column in {path}")

        repos.extend(df["repo_name"].dropna().astype(str).tolist())

    repos = [repo.strip() for repo in repos if repo and repo.strip()]
    repos = list(dict.fromkeys(repos))

    if not repos:
        raise SystemExit("No repos provided. Use --repo or --repos-file.")

    if len(repos) > args.max_repos:
        print(f"Trimming repos from {len(repos)} to {args.max_repos}")
        repos = repos[: args.max_repos]

    return repos


def format_bytes(n: int) -> str:
    gib = n / 1024**3
    mib = n / 1024**2
    return f"{n:,} bytes ({mib:.2f} MiB, {gib:.4f} GiB)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default="se-project-438721")
    parser.add_argument("--repo", action="append", help="Repo name, e.g., VRSEN/agency-swarm")
    parser.add_argument("--repos-file", help="CSV file with repo_name column")
    parser.add_argument("--max-repos", type=int, default=3)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default="2025-01-01")
    parser.add_argument("--max-gib", type=float, default=1.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--output",
        default="tmp_gharchive_test/repo_events_small.csv",
        help="Output CSV path used only with --execute",
    )

    args = parser.parse_args()

    repos = load_repos(args)
    start_suffix = to_suffix(args.start_date)
    end_suffix = to_suffix(args.end_date)
    max_bytes = int(args.max_gib * 1024**3)

    print("Project:", args.project_id)
    print("Repos:", repos)
    print("Date range:", args.start_date, "to", args.end_date)
    print("Max bytes billed:", format_bytes(max_bytes))

    client = bigquery.Client(project=args.project_id)

    params = [
        bigquery.ScalarQueryParameter("start_suffix", "STRING", start_suffix),
        bigquery.ScalarQueryParameter("end_suffix", "STRING", end_suffix),
        bigquery.ArrayQueryParameter("repos", "STRING", repos),
    ]

    dry_config = bigquery.QueryJobConfig(
        query_parameters=params,
        dry_run=True,
        use_query_cache=False,
    )

    dry_job = client.query(QUERY, job_config=dry_config)

    print("\nDry run OK")
    print("Bytes processed:", format_bytes(dry_job.total_bytes_processed))

    if not args.execute:
        print("\nDry run only. Add --execute to run the query with the safety cap.")
        return

    run_config = bigquery.QueryJobConfig(
        query_parameters=params,
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
    )

    print("\nExecuting actual query with maximum_bytes_billed...")
    result = client.query(QUERY, job_config=run_config).result()

    rows = [dict(row) for row in result]
    df = pd.DataFrame(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Rows returned:", len(df))
    print("Output:", output_path)

    if not df.empty:
        print("\nEvents by type:")
        print(df["type"].value_counts().to_string())

        print("\nEvents by repo:")
        print(df["repo"].value_counts().to_string())


if __name__ == "__main__":
    main()
