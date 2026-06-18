#!/usr/bin/env python3
"""
Create a temporary repository time-series input CSV for SonarQube smoke tests.

This script does not depend on the original paper's data/ts_repos_monthly.csv.
It reads the current HEAD commit from already cloned repositories and writes
a minimal CSV that can be consumed by proc_scripts/run_sonarqube_v2.py.

Example:
    python proc_scripts/create_tmp_repo_timeseries_input.py \
      --output tmp_sonar_batch/data/ts_repos_monthly.csv \
      --clone-root ../CursorRepos \
      --month 2026-06 \
      TheSethRose/Agent-Chat \
      utensils/mcp-nixos \
      nextml-code/pytorch-datastream
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd


def repo_to_project_key(repo_name: str) -> str:
    """Convert GitHub repo name OWNER/REPO to SonarQube project key OWNER_REPO."""
    return repo_name.replace("/", "_")


def get_head_commit(repo_path: Path) -> str:
    """Return the current HEAD commit hash for a cloned Git repository."""
    if not (repo_path / ".git").exists():
        raise FileNotFoundError(f"Missing cloned Git repository: {repo_path}")

    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )

    return result.stdout.strip()


def build_rows(repo_names: list[str], clone_root: Path, month: str) -> list[dict[str, str]]:
    """Build minimal time-series rows from cloned repository HEAD commits."""
    rows = []

    for repo_name in repo_names:
        project_key = repo_to_project_key(repo_name)
        repo_path = clone_root / project_key
        latest_commit = get_head_commit(repo_path)

        rows.append(
            {
                "repo_name": repo_name,
                "month": month,
                "latest_commit": latest_commit,
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create temporary SonarQube time-series input from cloned repo HEAD commits."
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
        "--month",
        default="2026-06",
        help="Month/version label to write to the CSV. Default: 2026-06.",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    clone_root = Path(args.clone_root)

    rows = build_rows(
        repo_names=args.repo_names,
        clone_root=clone_root,
        month=args.month,
    )

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("Wrote:", output_path)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
