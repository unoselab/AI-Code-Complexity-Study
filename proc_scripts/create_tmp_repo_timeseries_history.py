#!/usr/bin/env python3
"""
Create a temporary multi-month repository time-series input from actual Git history.

For each repo and month, this script finds the latest commit at or before the
end of that month using:

    git rev-list -n 1 --before <month-end> HEAD

This is closer to the original paper pipeline than repeating current HEAD.
"""

from __future__ import annotations

import argparse
import calendar
import subprocess
from pathlib import Path

import pandas as pd


def repo_to_project_key(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def month_end_timestamp(month: str) -> str:
    year, mon = map(int, month.split("-"))
    last_day = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-{last_day:02d} 23:59:59"


def get_latest_commit_before(repo_path: Path, before_time: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-list", "-n", "1", "--before", before_time, "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )

    commit = result.stdout.strip()
    return commit if commit else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create temporary multi-month SonarQube input from actual Git history."
    )

    parser.add_argument(
        "repo_names",
        nargs="+",
        help="GitHub repositories in OWNER/REPO format.",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path, e.g., tmp_sonar_batch/data/ts_repos_monthly.csv.",
    )

    parser.add_argument(
        "--clone-root",
        default="../CursorRepos",
        help="Directory containing cloned repositories. Default: ../CursorRepos.",
    )

    parser.add_argument(
        "--months",
        required=True,
        help="Comma-separated months, e.g., 2026-03,2026-04,2026-05.",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    clone_root = Path(args.clone_root)
    months = [m.strip() for m in args.months.split(",") if m.strip()]

    rows = []

    for repo_name in args.repo_names:
        project_key = repo_to_project_key(repo_name)
        repo_path = clone_root / project_key

        if not (repo_path / ".git").exists():
            raise SystemExit(f"Missing cloned Git repository: {repo_path}")

        for month in months:
            before_time = month_end_timestamp(month)
            commit = get_latest_commit_before(repo_path, before_time)

            if not commit:
                print(f"WARNING: no commit found for {repo_name} at {month}")
                continue

            rows.append(
                {
                    "repo_name": repo_name,
                    "month": month,
                    "latest_commit": commit,
                }
            )

    df = pd.DataFrame(rows)
    df = df.sort_values(["repo_name", "month"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Wrote:", output_path)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
