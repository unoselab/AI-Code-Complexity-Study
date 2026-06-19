#!/usr/bin/env python3
"""
Small, safe SEEDED control-aggregation smoke test.

Purpose:
- Validate the control-style metrics SCHEMA and SQL aggregation logic
  (repo_name, period, period_type, age_days, users_involved, n_stars, ...)
  WITHOUT running full-population control discovery.

Why this exists:
- scripts/fetch_gharchive_control.py discovers control candidates by scanning
  every WatchEvent across `githubarchive.month.*` (all >=10-star repos). That
  discovery scan is what makes the production query ~60 GiB and unsafe to run
  casually. Candidate-limit / sampling do NOT shrink the bytes scanned, because
  BigQuery bills the columns it reads BEFORE LIMIT/HAVING/sampling are applied.
- This script removes the discovery step entirely. It injects a known repo
  list (`--repo` / `--repos-file`) and bounds the scan to a month window, so
  BigQuery prunes partitions down to just those repos. The OUTPUT schema stays
  identical to control_repo_candidates_*.csv, so the matcher's load_control_repos
  can consume it unchanged.

Default behavior:
- Dry run only.
- Hard guard: refuses to execute if the dry-run estimate exceeds the cap,
  even if --execute is passed.

Use --execute only after checking the dry-run bytes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from google.cloud import bigquery


# Seeded variant of CONTROL_REPO_QUERY from scripts/fetch_gharchive_control.py.
# Only two things changed vs. production:
#   (1) candid_repos: discovery scan  ->  injected @repos seed list
#   (2) events:       _TABLE_SUFFIX <= @target_month  ->  bounded BETWEEN window
# Everything from params/periods/metrics_ts down is byte-for-byte the production
# logic, so the emitted schema and per-bucket semantics are unchanged.
SEEDED_CONTROL_QUERY = """
WITH
  -- 1. Seeded candidate repos (NO full-archive discovery scan).
  candid_repos AS (
    SELECT repo_name
    FROM UNNEST(@repos) AS repo_name
  ),

  -- 2. All events for the seeded repos, BOUNDED to [history_start, target].
  --    NOTE: the period_type='sum' bucket (below) counts events strictly
  --    OLDER than (target - 6 months). If @history_start is not earlier than
  --    that boundary, the sum bucket is empty and age_days reflects only the
  --    bounded window. The schema is still valid; the values are truncated.
  events AS (
    SELECT
      repo.name       AS repo_name,
      created_at,
      type,
      actor.id        AS actor_id,
      _TABLE_SUFFIX   AS ym
    FROM
      `githubarchive.month.*`
    WHERE
      _TABLE_SUFFIX BETWEEN @history_start AND @target_month
      AND repo.name IN UNNEST(@repos)
  ),

  -- 3. First-of-target date.
  params AS (
    SELECT
      PARSE_DATE('%Y%m', @target_month) AS first_of_target
  ),

  -- 4. Seven "period" rows: six individual months (within) + one sum bucket.
  periods AS (
    SELECT
      FORMAT_DATE('%Y%m',
        DATE_SUB(p.first_of_target, INTERVAL i MONTH)
      )         AS period,
      'within'  AS period_type
    FROM
      params p,
      UNNEST(GENERATE_ARRAY(1, 6)) AS i

    UNION ALL

    SELECT
      FORMAT_DATE('%Y%m',
        DATE_SUB(p.first_of_target, INTERVAL 7 MONTH)
      )         AS period,
      'sum'     AS period_type
    FROM
      params p
  ),

  -- 5. repos x periods, aggregated per bucket.
  metrics_ts AS (
    SELECT
      cr.repo_name,
      pr.period,
      pr.period_type,

      -- age in days at end of each bucket
      GREATEST(0, DATE_DIFF(
        CASE
          WHEN pr.period_type = 'within' THEN
            DATE_SUB(
              DATE_ADD(PARSE_DATE('%Y%m', pr.period), INTERVAL 1 MONTH),
              INTERVAL 1 DAY
            )
          ELSE
            DATE_SUB(
              DATE_SUB(p.first_of_target, INTERVAL 6 MONTH),
              INTERVAL 1 DAY
            )
        END,
        DATE(MIN(e.created_at)),
        DAY
      )) AS age_days,

      -- distinct users in the bucket
      COUNT(DISTINCT
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          ) THEN e.actor_id
        END
      ) AS users_involved,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type = 'WatchEvent' THEN 1 ELSE 0
        END
      ) AS n_stars,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type = 'ForkEvent' THEN 1 ELSE 0
        END
      ) AS n_forks,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type = 'ReleaseEvent' THEN 1 ELSE 0
        END
      ) AS n_releases,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type = 'PullRequestEvent' THEN 1 ELSE 0
        END
      ) AS n_pulls,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type = 'IssuesEvent' THEN 1 ELSE 0
        END
      ) AS n_issues,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          )
          AND e.type IN ('IssueCommentEvent', 'PullRequestReviewCommentEvent')
        THEN 1 ELSE 0
        END
      ) AS n_comments,

      SUM(
        CASE
          WHEN (
            (pr.period_type = 'within' AND e.ym = pr.period)
            OR
            (pr.period_type = 'sum'    AND e.ym < FORMAT_DATE('%Y%m',
               DATE_SUB(p.first_of_target, INTERVAL 6 MONTH)))
          ) THEN 1 ELSE 0
        END
      ) AS total_events

    FROM
      candid_repos cr
    CROSS JOIN
      params p
    CROSS JOIN
      periods pr
    LEFT JOIN
      events e
    ON
      e.repo_name = cr.repo_name
    GROUP BY
      cr.repo_name,
      pr.period,
      pr.period_type,
      p.first_of_target
  )

SELECT
  *
FROM
  metrics_ts
ORDER BY
  repo_name,
  period DESC;
"""

# Columns the matcher's load_control_repos() expects (it then adds group="control").
EXPECTED_COLUMNS = [
    "repo_name",
    "period",
    "period_type",
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

METRIC_COLUMNS = [
    "users_involved",
    "n_stars",
    "n_forks",
    "n_releases",
    "n_pulls",
    "n_issues",
    "n_comments",
    "total_events",
]


def validate_month(value: str) -> str:
    """Validate a YYYYMM month string."""
    if not (len(value) == 6 and value.isdigit()):
        raise SystemExit(f"Month must be in YYYYMM format, got: {value}")
    return value


def shift_month(yyyymm: str, months_back: int) -> str:
    """Return the YYYYMM that is `months_back` months before yyyymm."""
    year, month = int(yyyymm[:4]), int(yyyymm[4:])
    index = (year * 12 + (month - 1)) - months_back
    new_year, new_month = divmod(index, 12)
    return f"{new_year:04d}{new_month + 1:02d}"


def load_repos(args: argparse.Namespace) -> list[str]:
    """Collect seed repos from --repo flags and/or a --repos-file CSV."""
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
    parser = argparse.ArgumentParser(
        description="Seeded control-aggregation smoke test (schema validation, not discovery)."
    )
    parser.add_argument("--project-id", default="se-project-438721")
    parser.add_argument(
        "--repo", action="append", help="Repo name, e.g., VRSEN/agency-swarm"
    )
    parser.add_argument("--repos-file", help="CSV file with a repo_name column")
    parser.add_argument("--max-repos", type=int, default=3)
    parser.add_argument(
        "--target-month",
        default="202501",
        help="Pseudo-event month in YYYYMM (the matched control's anchor month)",
    )
    parser.add_argument(
        "--history-start-month",
        default="202407",
        help=(
            "Lower bound (YYYYMM) for the event scan. To populate the 'sum' "
            "bucket and get realistic age_days, set this EARLIER than "
            "(target - 6 months), e.g. target - 12."
        ),
    )
    parser.add_argument("--max-gib", type=float, default=1.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--output",
        default="tmp_gharchive_test/control_candidates_seeded_small.csv",
        help="Output CSV path used only with --execute",
    )

    args = parser.parse_args()

    repos = load_repos(args)
    target_month = validate_month(args.target_month)
    history_start = validate_month(args.history_start_month)
    if history_start > target_month:
        raise SystemExit(
            f"--history-start-month ({history_start}) is after "
            f"--target-month ({target_month})."
        )
    max_bytes = int(args.max_gib * 1024**3)

    print("Project:", args.project_id)
    print("Repos:", repos)
    print("Target month:", target_month)
    print("History start:", history_start)
    print("Max bytes billed:", format_bytes(max_bytes))

    # Advisory: warn when the 'sum' bucket cannot be populated by this window.
    sum_threshold = shift_month(target_month, 6)  # earliest 'within' month
    if history_start >= sum_threshold:
        print(
            f"\nADVISORY: history-start ({history_start}) is not earlier than "
            f"target-6mo ({sum_threshold})."
        )
        print(
            "  The 'sum' bucket counts events OLDER than that boundary, so it "
            "will be empty"
        )
        print(
            "  and age_days will be truncated. Schema is still valid for a "
            "smoke test."
        )
        print(
            f"  For realistic values, pass e.g. --history-start-month "
            f"{shift_month(target_month, 12)}."
        )

    client = bigquery.Client(project=args.project_id)

    params = [
        bigquery.ScalarQueryParameter("target_month", "STRING", target_month),
        bigquery.ScalarQueryParameter("history_start", "STRING", history_start),
        bigquery.ArrayQueryParameter("repos", "STRING", repos),
    ]

    dry_config = bigquery.QueryJobConfig(
        query_parameters=params,
        dry_run=True,
        use_query_cache=False,
    )

    dry_job = client.query(SEEDED_CONTROL_QUERY, job_config=dry_config)

    print("\nDry run OK")
    print("Bytes processed:", format_bytes(dry_job.total_bytes_processed))

    # Hard guard: never execute a query larger than the cap, even with --execute.
    if dry_job.total_bytes_processed > max_bytes:
        print("\nSTOP: dry-run estimate exceeds max_bytes_billed.")
        print("This query is too large for the current safety cap.")
        print("Do not execute unless you intentionally raise --max-gib.")
        return

    if not args.execute:
        print("\nDry run only. Add --execute to run the query with the safety cap.")
        return

    run_config = bigquery.QueryJobConfig(
        query_parameters=params,
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
    )

    print("\nExecuting actual query with maximum_bytes_billed...")
    result = client.query(SEEDED_CONTROL_QUERY, job_config=run_config).result()

    rows = [dict(row) for row in result]
    df = pd.DataFrame(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Rows returned:", len(df))
    print("Output:", output_path)

    if df.empty:
        print("\nNo rows returned. Check repo names and the month window.")
        return

    # --- Schema / aggregation smoke checks ---
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    print("\nSchema check:")
    print("  Columns:", list(df.columns))
    print("  Missing vs. expected:", missing if missing else "none")
    print("  Extra vs. expected:", extra if extra else "none")

    print("\nRows per repo (expect 7 each: 6 'within' + 1 'sum'):")
    print(df["repo_name"].value_counts().to_string())

    print("\nperiod_type distribution:")
    print(df["period_type"].value_counts().to_string())

    sum_rows = df[df["period_type"] == "sum"]
    if not sum_rows.empty and sum_rows[METRIC_COLUMNS].to_numpy().sum() == 0:
        print(
            "\nNote: the 'sum' bucket is all zero (expected, given the "
            "history-start advisory above)."
        )


if __name__ == "__main__":
    main()
