#!/usr/bin/env python3
"""
Small, safe SEEDED control-aggregation smoke test over DAY tables.

Why a "_day" variant exists:
- The month-table version (test_fetch_gharchive_control_seeded.py) dry-runs at
  ~100 GiB even for 3 seed repos, because `githubarchive.month.*` is NOT
  clustered by repo.name. `repo.name IN UNNEST(@repos)` shrinks output rows but
  not bytes scanned: BigQuery still reads the selected columns across every
  monthly table the wildcard matches, and each monthly table is huge.
- The cost lever for GHArchive is the NUMBER/SIZE of tables scanned, not repos.
  `githubarchive.day.20*` over a 1-2 day window touches one or two small daily
  tables, so it stays well under a 1 GiB cap (this is exactly why the treatment
  smoke test test_fetch_gharchive_small.py is cheap).

What this validates (and what it does NOT):
- VALIDATES: the control output SCHEMA and the per-bucket aggregation SQL run
  end-to-end on real data, cheaply enough to actually execute (the month
  version is blocked by the cap and never emits rows).
- DOES NOT: produce realistic 6-month control metrics. A few days of data can
  only populate ONE of the six monthly 'within' buckets. The other buckets and
  the 'sum' bucket will be zero. Use this for schema/logic, not for values.

Output schema matches control_repo_candidates_*.csv, so the matcher's
load_control_repos() can consume the (degenerate) result unchanged.

Default behavior:
- Dry run only.
- Hard guard: refuses to execute if the dry-run estimate exceeds the cap,
  even if --execute is passed.

Use --execute only after checking the dry-run bytes.
"""

from __future__ import annotations

import argparse
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
from google.cloud import bigquery


# Seeded control aggregation, sourced from DAY tables over a bounded window.
# Differences vs. the production CONTROL_REPO_QUERY (scripts/fetch_gharchive_control.py):
#   (1) candid_repos: discovery scan            -> injected @repos seed list
#   (2) events.FROM:  githubarchive.month.*      -> githubarchive.day.*
#   (3) events.WHERE: _TABLE_SUFFIX <= @target   -> BETWEEN @start_suffix AND @end_suffix
#   (4) ym derivation: _TABLE_SUFFIX (YYYYMM)    -> SUBSTR(_TABLE_SUFFIX, 1, 6)
# params/periods/metrics_ts are byte-for-byte the production logic, so bucket
# assignment, the 12-column schema, and metric semantics are unchanged.
SEEDED_CONTROL_DAY_QUERY = """
WITH
  -- 1. Seeded candidate repos (NO full-archive discovery scan).
  candid_repos AS (
    SELECT repo_name
    FROM UNNEST(@repos) AS repo_name
  ),

  -- 2. Events for the seeded repos from DAY tables, bounded to a tiny window.
  --    ym is the YYYYMM of each daily table, so the monthly bucket logic below
  --    is reused unchanged. A 1-2 day window only intersects ONE month, so at
  --    most one 'within' bucket will be non-zero.
  events AS (
    SELECT
      repo.name                  AS repo_name,
      created_at,
      type,
      actor.id                   AS actor_id,
      CONCAT('20', SUBSTR(_TABLE_SUFFIX, 1, 4)) AS ym
    FROM
      `githubarchive.day.20*`
    WHERE
      _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix
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

      -- age in days at end of each bucket (NULL if repo has no scanned events)
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


def to_suffix(date_string: str) -> str:
    """Convert YYYY-MM-DD to the YYYYMMDD table suffix."""
    return date_string.replace("-", "")[2:]


def validate_date(value: str) -> str:
    """Validate a YYYY-MM-DD date string."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"Date must be in YYYY-MM-DD format, got: {value}")
    return value


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


def months_in_range(start_date: str, end_date: str) -> list[str]:
    """List the YYYYMM months covered by an inclusive [start, end] date range."""
    start_year, start_month = int(start_date[:4]), int(start_date[5:7])
    end_year, end_month = int(end_date[:4]), int(end_date[5:7])
    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


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
        description="Seeded control-aggregation smoke test over DAY tables (cheap, executable)."
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
        help="Pseudo-event month in YYYYMM; drives the six 'within' bucket windows",
    )
    parser.add_argument(
        "--start-date",
        default="2024-12-01",
        help="Scan window start (YYYY-MM-DD). Keep it small (1-2 days).",
    )
    parser.add_argument(
        "--end-date",
        default="2024-12-01",
        help="Scan window end (YYYY-MM-DD). Each extra day adds ~1 day of bytes.",
    )
    parser.add_argument("--max-gib", type=float, default=1.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--output",
        default="tmp_gharchive_test/control_candidates_seeded_day.csv",
        help="Output CSV path used only with --execute",
    )

    args = parser.parse_args()

    repos = load_repos(args)
    target_month = validate_month(args.target_month)
    start_date = validate_date(args.start_date)
    end_date = validate_date(args.end_date)
    if start_date > end_date:
        raise SystemExit(
            f"--start-date ({start_date}) is after --end-date ({end_date})."
        )
    start_suffix = to_suffix(start_date)
    end_suffix = to_suffix(end_date)
    max_bytes = int(args.max_gib * 1024**3)

    print("Project:", args.project_id)
    print("Repos:", repos)
    print("Target month:", target_month)
    print("Scan window:", start_date, "to", end_date, f"({start_suffix}..{end_suffix})")
    print("Max bytes billed:", format_bytes(max_bytes))

    # Advisory: which monthly bucket(s) the scanned days can populate.
    within_months = [shift_month(target_month, k) for k in range(1, 7)]
    sum_threshold = shift_month(target_month, 6)  # 'sum' bucket counts ym < this
    scanned_months = months_in_range(start_date, end_date)
    hits_within = sorted(set(scanned_months) & set(within_months))
    hits_sum = sorted(m for m in set(scanned_months) if m < sum_threshold)

    print("\nBucket mapping:")
    print("  'within' months for this target:", within_months)
    print("  'sum' bucket counts months <", sum_threshold)
    print("  scanned months:", scanned_months)
    if not hits_within and not hits_sum:
        print(
            "  ADVISORY: scanned months hit NO 'within' period and are not in the "
            "'sum' range."
        )
        print(
            "  All metric buckets will be zero. To see non-zero counts, scan days "
            "inside one"
        )
        print(
            f"  of the 'within' months above (e.g. --start-date "
            f"{within_months[0][:4]}-{within_months[0][4:]}-01)."
        )
    else:
        if hits_within:
            print("  -> will populate 'within' bucket(s):", hits_within)
        if hits_sum:
            print("  -> will contribute to the 'sum' bucket:", hits_sum)

    client = bigquery.Client(project=args.project_id)

    params = [
        bigquery.ScalarQueryParameter("target_month", "STRING", target_month),
        bigquery.ScalarQueryParameter("start_suffix", "STRING", start_suffix),
        bigquery.ScalarQueryParameter("end_suffix", "STRING", end_suffix),
        bigquery.ArrayQueryParameter("repos", "STRING", repos),
    ]

    dry_config = bigquery.QueryJobConfig(
        query_parameters=params,
        dry_run=True,
        use_query_cache=False,
    )

    dry_job = client.query(SEEDED_CONTROL_DAY_QUERY, job_config=dry_config)

    print("\nDry run OK")
    print("Bytes processed:", format_bytes(dry_job.total_bytes_processed))

    # Hard guard: never execute a query larger than the cap, even with --execute.
    if dry_job.total_bytes_processed > max_bytes:
        print("\nSTOP: dry-run estimate exceeds max_bytes_billed.")
        print("This query is too large for the current safety cap.")
        print("Narrow the date window, or intentionally raise --max-gib.")
        raise SystemExit(2)

    if not args.execute:
        print("\nDry run only. Add --execute to run the query with the safety cap.")
        return

    run_config = bigquery.QueryJobConfig(
        query_parameters=params,
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
    )

    print("\nExecuting actual query with maximum_bytes_billed...")
    result = client.query(SEEDED_CONTROL_DAY_QUERY, job_config=run_config).result()

    rows = [dict(row) for row in result]
    df = pd.DataFrame(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Rows returned:", len(df))
    print("Output:", output_path)

    if df.empty:
        print("\nNo rows returned. Check repo names and the scan window.")
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

    print("\nNon-zero metric rows by period (confirms the counting logic ran):")
    nonzero = df[df[METRIC_COLUMNS].to_numpy().sum(axis=1) > 0]
    if nonzero.empty:
        print("  none (see the bucket-mapping advisory above)")
    else:
        print(
            nonzero[["repo_name", "period", "period_type"] + METRIC_COLUMNS]
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
