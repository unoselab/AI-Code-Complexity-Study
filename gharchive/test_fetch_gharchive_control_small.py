#!/usr/bin/env python3
"""
Small, safe GHArchive control-candidate BigQuery test.

This is a miniature version of fetch_gharchive_control.py.

Default behavior:
- Dry run only
- One target month
- Bounded history window
- Deterministic sampled candidate pool
- SQL-level candidate limit
- No full control population pull

Use --execute only after checking dry-run bytes.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
from google.cloud import bigquery


CONTROL_QUERY_TEMPLATE = """
-- Build GHArchive-based control-candidate metrics for one target adoption month.
-- This is a sampled, byte-capped smoke-test version of the control-candidate query.
WITH
  params AS (
    SELECT
      PARSE_DATE('%Y%m', @target_month) AS first_of_target,
      FORMAT_DATE(
        '%Y%m',
        DATE_SUB(PARSE_DATE('%Y%m', @target_month), INTERVAL 6 MONTH)
      ) AS recent_window_start_month
  ),

  -- Step 1: Find repos active in the target month.
  -- The hash sample keeps the smoke test small.
  active_repos AS (
    SELECT DISTINCT
      repo.name AS repo_name
    FROM
      `githubarchive.month.*`
    WHERE
      _TABLE_SUFFIX = @target_month
      AND repo.name IS NOT NULL
      AND ABS(MOD(FARM_FINGERPRINT(repo.name), @sample_mod_denominator))
          < @sample_mod_numerator
  ),

  -- Step 2: Keep sampled active repos with enough WatchEvent activity.
  -- WatchEvent is used as the GHArchive approximation of starring.
  candid_repos AS (
    SELECT
      repo.name AS repo_name
    FROM
      `githubarchive.month.*`
    WHERE
      _TABLE_SUFFIX BETWEEN @history_start_month AND @target_month
      AND type = 'WatchEvent'
      AND repo.name IN (SELECT repo_name FROM active_repos)
    GROUP BY
      repo_name
    HAVING
      COUNT(*) >= @min_stars
    ORDER BY
      FARM_FINGERPRINT(repo_name)
    LIMIT {candidate_limit}
  ),

  -- Step 3: Pull all relevant events for the sampled candidate repos.
  events AS (
    SELECT
      repo.name AS repo_name,
      created_at,
      type,
      actor.login AS actor_login,
      _TABLE_SUFFIX AS ym
    FROM
      `githubarchive.month.*`
    WHERE
      _TABLE_SUFFIX BETWEEN @history_start_month AND @target_month
      AND repo.name IN (SELECT repo_name FROM candid_repos)
  ),

  -- Step 4: Approximate first observed activity date within the bounded history.
  -- For the full pipeline, this may need longer history.
  repo_first_seen AS (
    SELECT
      repo_name,
      MIN(created_at) AS first_seen_at
    FROM
      events
    GROUP BY
      repo_name
  ),

  -- Step 5: Define six recent pre-treatment months plus one older cumulative bucket.
  periods AS (
    SELECT
      FORMAT_DATE('%Y%m', DATE_SUB(p.first_of_target, INTERVAL i MONTH)) AS period,
      'within' AS period_type,
      DATE_SUB(
        DATE_ADD(
          DATE_SUB(p.first_of_target, INTERVAL i MONTH),
          INTERVAL 1 MONTH
        ),
        INTERVAL 1 DAY
      ) AS period_end_date
    FROM
      params p,
      UNNEST(GENERATE_ARRAY(1, 6)) AS i

    UNION ALL

    SELECT
      FORMAT_DATE('%Y%m', DATE_SUB(p.first_of_target, INTERVAL 7 MONTH)) AS period,
      'sum' AS period_type,
      DATE_SUB(DATE_SUB(p.first_of_target, INTERVAL 6 MONTH), INTERVAL 1 DAY)
        AS period_end_date
    FROM
      params p
  ),

  -- Step 6: Attach events to the matching period they belong to.
  period_events AS (
    SELECT
      cr.repo_name,
      pr.period,
      pr.period_type,
      pr.period_end_date,
      e.created_at,
      e.type,
      e.actor_login
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
      AND (
        (pr.period_type = 'within' AND e.ym = pr.period)
        OR
        (pr.period_type = 'sum' AND e.ym < p.recent_window_start_month)
      )
  ),

  -- Step 7: Aggregate repo-period activity metrics.
  metrics_ts AS (
    SELECT
      pe.repo_name,
      pe.period,
      pe.period_type,

      GREATEST(
        0,
        DATE_DIFF(
          pe.period_end_date,
          DATE(rfs.first_seen_at),
          DAY
        )
      ) AS age_days,

      COUNT(DISTINCT pe.actor_login) AS users_involved,

      COUNTIF(pe.type = 'WatchEvent') AS n_stars,
      COUNTIF(pe.type = 'ForkEvent') AS n_forks,
      COUNTIF(pe.type = 'ReleaseEvent') AS n_releases,
      COUNTIF(pe.type = 'PullRequestEvent') AS n_pulls,
      COUNTIF(pe.type = 'IssuesEvent') AS n_issues,
      COUNTIF(pe.type IN (
        'IssueCommentEvent',
        'PullRequestReviewCommentEvent'
      )) AS n_comments,

      COUNT(pe.type) AS total_events

    FROM
      period_events pe
    LEFT JOIN
      repo_first_seen rfs
    ON
      rfs.repo_name = pe.repo_name
    GROUP BY
      pe.repo_name,
      pe.period,
      pe.period_type,
      pe.period_end_date,
      rfs.first_seen_at
  )

SELECT
  repo_name,
  period,
  period_type,
  age_days,
  users_involved,
  n_stars,
  n_forks,
  n_releases,
  n_pulls,
  n_issues,
  n_comments,
  total_events
FROM
  metrics_ts
ORDER BY
  repo_name,
  period DESC
"""


def format_bytes(n: int) -> str:
    mib = n / 1024**2
    gib = n / 1024**3
    return f"{n:,} bytes ({mib:.2f} MiB, {gib:.4f} GiB)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Small safe GHArchive control-candidate test."
    )
    parser.add_argument("--project-id", default="se-project-438721")
    parser.add_argument("--target-month", default="202501")
    parser.add_argument("--history-start-month", default="202407")
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--min-stars", type=int, default=10)
    parser.add_argument("--sample-mod-numerator", type=int, default=1)
    parser.add_argument("--sample-mod-denominator", type=int, default=100)
    parser.add_argument("--max-gib", type=float, default=1.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--output",
        default="tmp_gharchive_test/control_repo_candidates_small_202501.csv",
    )

    args = parser.parse_args()

    if args.candidate_limit <= 0:
        raise SystemExit("--candidate-limit must be positive")

    if args.sample_mod_numerator <= 0:
        raise SystemExit("--sample-mod-numerator must be positive")

    if args.sample_mod_denominator <= 0:
        raise SystemExit("--sample-mod-denominator must be positive")

    if args.sample_mod_numerator > args.sample_mod_denominator:
        raise SystemExit("--sample-mod-numerator cannot exceed --sample-mod-denominator")



    from datetime import datetime
    from dateutil.relativedelta import relativedelta


    def parse_month(month: str) -> datetime:
        return datetime.strptime(month, "%Y%m")


    target_dt = parse_month(args.target_month)
    history_start_dt = parse_month(args.history_start_month)
    recent_window_start_dt = target_dt - relativedelta(months=6)

    if history_start_dt >= recent_window_start_dt:
        print(
            "WARNING: history_start_month is inside or after the recent six-month window."
        )
        print(
            "The 'sum' period will be empty or incomplete."
        )
        print(
            "For target_month=%s, use history_start_month earlier than %s to test the sum bucket."
            % (args.target_month, recent_window_start_dt.strftime("%Y%m"))
        )



    query = CONTROL_QUERY_TEMPLATE.format(candidate_limit=int(args.candidate_limit))
    max_bytes = int(args.max_gib * 1024**3)

    print("Project:", args.project_id)
    print("Target month:", args.target_month)
    print("History start month:", args.history_start_month)
    print("Candidate limit:", args.candidate_limit)
    print("Minimum stars:", args.min_stars)
    print(
        "Sample fraction:",
        f"{args.sample_mod_numerator}/{args.sample_mod_denominator}",
    )
    print("Max bytes billed:", format_bytes(max_bytes))

    client = bigquery.Client(project=args.project_id)

    params = [
        bigquery.ScalarQueryParameter("target_month", "STRING", args.target_month),
        bigquery.ScalarQueryParameter(
            "history_start_month", "STRING", args.history_start_month
        ),
        bigquery.ScalarQueryParameter("min_stars", "INT64", args.min_stars),
        bigquery.ScalarQueryParameter(
            "sample_mod_numerator", "INT64", args.sample_mod_numerator
        ),
        bigquery.ScalarQueryParameter(
            "sample_mod_denominator", "INT64", args.sample_mod_denominator
        ),
    ]

    dry_config = bigquery.QueryJobConfig(
        query_parameters=params,
        dry_run=True,
        use_query_cache=False,
    )

    dry_job = client.query(query, job_config=dry_config)
    print("\nDry run OK")
    print("Bytes processed:", format_bytes(dry_job.total_bytes_processed))

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
    result = client.query(query, job_config=run_config).result()
    rows = [dict(row) for row in result]
    df = pd.DataFrame(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Rows returned:", len(df))
    print("Unique repos:", df["repo_name"].nunique() if not df.empty else 0)
    print("Output:", output_path)

    if not df.empty:
        print("\nColumns:")
        print(list(df.columns))

        print("\nFirst rows:")
        print(df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
