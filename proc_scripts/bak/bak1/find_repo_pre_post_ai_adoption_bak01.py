#!/usr/bin/env python3
"""
Select clone candidates from existing baseline event-panel data.

Goal:
- Do not clone all repositories immediately.
- Use data_baseline_backup/panel_event_monthly.csv to find repositories with
  observed pre-adoption and post-adoption months.
- Output the top N repositories that are good candidates for cloning and
  Git-history validation.

Important:
- Do not filter on cursor == True, because that removes pre-adoption rows.
- Do not filter on is_treatment == 1, because in this panel it is time-varying.
- Prefer dataset_source == treatment.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return pd.read_csv(path, dtype=str, low_memory=False)


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select top clone candidates from baseline event-panel data."
    )

    parser.add_argument(
        "--data-dir",
        default="data_baseline_backup",
        help="Directory containing baseline CSV files.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=100,
        help="Number of candidate repos to output.",
    )

    parser.add_argument(
        "--min-pre-months",
        type=int,
        default=1,
        help="Minimum observed pre-adoption months.",
    )

    parser.add_argument(
        "--min-post-months",
        type=int,
        default=1,
        help="Minimum observed post-adoption months.",
    )

    parser.add_argument(
        "--output",
        default="tmp_adoption_test/data/top_100_clone_candidates.csv",
        help="Output CSV path.",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    panel_path = data_dir / "panel_event_monthly.csv"
    ts_path = data_dir / "ts_repos_monthly.csv"
    cursor_commits_path = data_dir / "cursor_commits.csv"
    cursor_files_path = data_dir / "cursor_files.csv"
    output_path = Path(args.output)

    panel = read_csv(panel_path)
    ts = read_csv(ts_path)

    required_panel_cols = {
        "repo_name",
        "time",
        "event",
        "time_to_event",
        "dataset_source",
    }

    missing = required_panel_cols - set(panel.columns)
    if missing:
        raise SystemExit(
            f"Missing required columns in {panel_path}: {sorted(missing)}\n"
            f"Available columns: {list(panel.columns)}"
        )

    panel = panel.copy()
    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["time"] = panel["time"].astype(str).str[:7]
    panel["event"] = panel["event"].astype(str).str[:7]
    panel["time_to_event_num"] = to_numeric(panel["time_to_event"])

    # Keep treatment-source rows only.
    # Do not use cursor == True because that drops pre-adoption rows.
    treatment = panel[
        panel["dataset_source"].astype(str).str.lower().eq("treatment")
    ].copy()

    treatment = treatment.dropna(subset=["time_to_event_num"])
    treatment["time_to_event_num"] = treatment["time_to_event_num"].astype(int)

    # Basic event-window summary from the event panel
    summary = (
        treatment.groupby("repo_name")
        .agg(
            panel_first_month=("time", "min"),
            panel_latest_month=("time", "max"),
            event_month=("event", "first"),
            panel_month_count=("time", "nunique"),
            min_relative_month=("time_to_event_num", "min"),
            max_relative_month=("time_to_event_num", "max"),
            pre_panel_months=("time_to_event_num", lambda x: int((x < 0).sum())),
            event_months=("time_to_event_num", lambda x: int((x == 0).sum())),
            post_panel_months=("time_to_event_num", lambda x: int((x > 0).sum())),
        )
        .reset_index()
    )

    # Add time-series coverage and latest_commit availability
    if {"repo_name", "month", "latest_commit"}.issubset(ts.columns):
        ts2 = ts.copy()
        ts2["repo_name"] = ts2["repo_name"].astype(str).str.strip()
        ts2["month"] = ts2["month"].astype(str).str[:7]
        ts2["has_latest_commit"] = (
            ts2["latest_commit"].notna()
            & ts2["latest_commit"].astype(str).str.strip().ne("")
            & ts2["latest_commit"].astype(str).str.lower().ne("nan")
        )

        ts_summary = (
            ts2.groupby("repo_name")
            .agg(
                ts_first_month=("month", "min"),
                ts_latest_month=("month", "max"),
                ts_month_count=("month", "nunique"),
                ts_rows_with_latest_commit=("has_latest_commit", "sum"),
            )
            .reset_index()
        )

        summary = summary.merge(ts_summary, on="repo_name", how="left")

    # Add Cursor commit evidence counts
    if cursor_commits_path.exists():
        cursor_commits = read_csv(cursor_commits_path)
        if "repo_name" in cursor_commits.columns:
            commit_counts = (
                cursor_commits.groupby("repo_name")
                .size()
                .reset_index(name="cursor_commit_rows")
            )
            summary = summary.merge(commit_counts, on="repo_name", how="left")

    # Add Cursor file evidence counts
    if cursor_files_path.exists():
        cursor_files = read_csv(cursor_files_path)
        if "repo_name" in cursor_files.columns:
            file_counts = (
                cursor_files.groupby("repo_name")
                .size()
                .reset_index(name="cursor_file_rows")
            )
            summary = summary.merge(file_counts, on="repo_name", how="left")

    for col in [
        "cursor_commit_rows",
        "cursor_file_rows",
        "ts_month_count",
        "ts_rows_with_latest_commit",
    ]:
        if col not in summary.columns:
            summary[col] = 0
        summary[col] = to_numeric(summary[col]).fillna(0).astype(int)

    # Eligibility for our smoke-test cloning target
    eligible = summary[
        (summary["pre_panel_months"] >= args.min_pre_months)
        & (summary["post_panel_months"] >= args.min_post_months)
        & (summary["event_months"] >= 1)
    ].copy()

    # Prefer balanced pre/post windows and real Cursor evidence rows.
    eligible["balanced_window"] = eligible[
        ["pre_panel_months", "post_panel_months"]
    ].min(axis=1)
    eligible["total_pre_post"] = (
        eligible["pre_panel_months"] + eligible["post_panel_months"]
    )

    eligible = eligible.sort_values(
        by=[
            "balanced_window",
            "total_pre_post",
            "cursor_commit_rows",
            "cursor_file_rows",
            "ts_rows_with_latest_commit",
            "panel_month_count",
        ],
        ascending=[False, False, False, False, False, False],
    )

    top = eligible.head(args.top_n).copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(output_path, index=False)

    all_eligible_path = output_path.with_name(output_path.stem + "_all_eligible.csv")
    eligible.to_csv(all_eligible_path, index=False)

    print("Data dir:", data_dir)
    print("Panel rows:", len(panel))
    print("Treatment-source panel rows:", len(treatment))
    print("Treatment repos summarized:", summary["repo_name"].nunique())
    print("Eligible repos:", len(eligible))
    print("Top N written:", len(top))
    print("Output:", output_path)
    print("All eligible output:", all_eligible_path)

    print("\nTop candidates:")
    display_cols = [
        "repo_name",
        "event_month",
        "panel_first_month",
        "panel_latest_month",
        "pre_panel_months",
        "event_months",
        "post_panel_months",
        "balanced_window",
        "cursor_commit_rows",
        "cursor_file_rows",
        "ts_rows_with_latest_commit",
    ]
    display_cols = [col for col in display_cols if col in top.columns]
    print(top[display_cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
