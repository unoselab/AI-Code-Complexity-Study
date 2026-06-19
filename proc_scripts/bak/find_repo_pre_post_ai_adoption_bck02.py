#!/usr/bin/env python3
"""
Select clone candidates from existing baseline event-panel data.

Goal:
- Do not clone all repositories immediately.
- Use data_baseline_backup/panel_event_monthly.csv to find repositories with
  observed pre-adoption and post-adoption months.
- Output the top N repositories that are good candidates for cloning and
  Git-history validation.

Month classification (time_to_event):
    time_to_event < 0   -> pre-adoption month
    time_to_event == 0  -> adoption month
    time_to_event > 0   -> post-adoption month

Important:
- Do not filter on cursor == True, because that removes pre-adoption rows.
- Do not filter on is_treatment == 1, because in this panel it is time-varying.
  Prefer dataset_source == treatment.
- Count DISTINCT months, not rows: the baseline panel contains a few repos with
  duplicated (repo_name, time) rows, which would otherwise double their window.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def read_csv(path: Path, required: bool = True) -> pd.DataFrame | None:
    if not path.exists():
        if required:
            raise SystemExit(f"Missing required file: {path}")
        return None
    return pd.read_csv(path, dtype=str, low_memory=False)


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clean_month(series: pd.Series) -> pd.Series:
    """Normalize a month-ish string to YYYY-MM, blanking 'nan'/empty."""
    s = series.astype(str).str.strip().str[:7]
    return s.mask(s.str.lower().isin(["nan", "nat", "none", ""]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select top clone candidates from baseline event-panel data."
    )
    parser.add_argument("--data-dir", default="data_baseline_backup",
                        help="Directory containing baseline CSV files.")
    parser.add_argument("--top-n", type=int, default=100,
                        help="Number of candidate repos to output.")
    parser.add_argument("--min-pre-months", type=int, default=1,
                        help="Minimum observed pre-adoption months.")
    parser.add_argument("--min-post-months", type=int, default=1,
                        help="Minimum observed post-adoption months.")
    parser.add_argument("--require-cursor-evidence", action="store_true",
                        help="Keep only repos with >=1 cursor_commit or cursor_file row "
                             "(useful when the clones are for Cursor git-history validation).")
    parser.add_argument("--output",
                        default="tmp_adoption_test/data/top_100_clone_candidates.csv",
                        help="Output CSV path.")
    return parser.parse_args()


def build_treatment_summary(panel: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Per-repo event-window summary from deduplicated treatment panel rows."""
    panel = panel.copy()
    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["time"] = clean_month(panel["time"])
    panel["event"] = clean_month(panel["event"])
    panel["time_to_event_num"] = to_numeric(panel["time_to_event"])

    treatment = panel[
        panel["dataset_source"].astype(str).str.lower().eq("treatment")
    ].copy()
    treatment = treatment.dropna(subset=["time_to_event_num", "time"])
    treatment["time_to_event_num"] = treatment["time_to_event_num"].astype(int)

    # CRITICAL: collapse duplicated (repo_name, time) rows so windows count
    # distinct months, not rows.
    before = len(treatment)
    treatment = treatment.sort_values(["repo_name", "time"]).drop_duplicates(
        subset=["repo_name", "time"], keep="first"
    )
    n_dropped = before - len(treatment)

    summary = (
        treatment.groupby("repo_name")
        .agg(
            event_month=("event", "first"),
            panel_first_month=("time", "min"),
            panel_latest_month=("time", "max"),
            panel_month_count=("time", "nunique"),
            min_relative_month=("time_to_event_num", "min"),
            max_relative_month=("time_to_event_num", "max"),
            pre_panel_months=("time_to_event_num", lambda x: int((x < 0).sum())),
            event_months=("time_to_event_num", lambda x: int((x == 0).sum())),
            post_panel_months=("time_to_event_num", lambda x: int((x > 0).sum())),
        )
        .reset_index()
    )
    return summary, n_dropped


def add_count_evidence(summary: pd.DataFrame, path: Path, colname: str) -> pd.DataFrame:
    """Merge a per-repo row-count from an optional evidence file."""
    df = read_csv(path, required=False)
    if df is not None and "repo_name" in df.columns:
        counts = df.groupby("repo_name").size().reset_index(name=colname)
        summary = summary.merge(counts, on="repo_name", how="left")
    return summary


def add_ts_coverage(summary: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Optional: ts month coverage and how many months have a latest_commit hash."""
    ts = read_csv(path, required=False)
    if ts is None or not {"repo_name", "month"}.issubset(ts.columns):
        return summary
    ts = ts.copy()
    ts["repo_name"] = ts["repo_name"].astype(str).str.strip()
    ts["month"] = clean_month(ts["month"])
    ts = ts.dropna(subset=["month"]).drop_duplicates(["repo_name", "month"])
    has_commit = (
        ts.get("latest_commit", pd.Series("", index=ts.index))
        .astype(str).str.strip().str.lower()
    )
    ts["has_latest_commit"] = ~has_commit.isin(["", "nan", "nat", "none"])
    ts_summary = (
        ts.groupby("repo_name")
        .agg(
            ts_first_month=("month", "min"),
            ts_latest_month=("month", "max"),
            ts_month_count=("month", "nunique"),
            ts_rows_with_latest_commit=("has_latest_commit", "sum"),
        )
        .reset_index()
    )
    return summary.merge(ts_summary, on="repo_name", how="left")


def add_repo_metadata(summary: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Optional: stars / primary language / size for sanity-checking the clone set."""
    repos = read_csv(path, required=False)
    if repos is None or "repo_name" not in repos.columns:
        return summary
    keep = [c for c in ["repo_name", "repo_stars", "repo_primary_language", "repo_size"]
            if c in repos.columns]
    meta = repos[keep].copy()
    meta["repo_name"] = meta["repo_name"].astype(str).str.strip()
    return summary.merge(meta.drop_duplicates("repo_name"), on="repo_name", how="left")


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_path = Path(args.output)

    panel = read_csv(data_dir / "panel_event_monthly.csv")
    required_panel_cols = {"repo_name", "time", "event", "time_to_event", "dataset_source"}
    missing = required_panel_cols - set(panel.columns)
    if missing:
        raise SystemExit(
            f"Missing required columns in panel: {sorted(missing)}\n"
            f"Available columns: {list(panel.columns)}"
        )

    summary, n_dup_dropped = build_treatment_summary(panel)
    summary = add_ts_coverage(summary, data_dir / "ts_repos_monthly.csv")
    summary = add_count_evidence(summary, data_dir / "cursor_commits.csv", "cursor_commit_rows")
    summary = add_count_evidence(summary, data_dir / "cursor_files.csv", "cursor_file_rows")
    summary = add_repo_metadata(summary, data_dir / "repos.csv")

    int_cols = ["cursor_commit_rows", "cursor_file_rows", "ts_month_count",
                "ts_rows_with_latest_commit", "repo_stars", "repo_size"]
    for col in int_cols:
        if col not in summary.columns:
            summary[col] = 0
        summary[col] = to_numeric(summary[col]).fillna(0).astype(int)

    # Eligibility
    eligible = summary[
        (summary["pre_panel_months"] >= args.min_pre_months)
        & (summary["post_panel_months"] >= args.min_post_months)
        & (summary["event_months"] >= 1)
    ].copy()

    if args.require_cursor_evidence:
        eligible = eligible[
            (eligible["cursor_commit_rows"] > 0) | (eligible["cursor_file_rows"] > 0)
        ].copy()

    # Prefer balanced pre/post windows, then depth, then Cursor evidence.
    eligible["balanced_window"] = eligible[["pre_panel_months", "post_panel_months"]].min(axis=1)
    eligible["total_pre_post"] = eligible["pre_panel_months"] + eligible["post_panel_months"]
    # Flag windows that touch the data-collection boundary (true pre/post may be larger).
    overall_min, overall_max = summary["panel_first_month"].min(), summary["panel_latest_month"].max()
    eligible["window_touches_data_edge"] = (
        eligible["panel_first_month"].eq(overall_min)
        | eligible["panel_latest_month"].eq(overall_max)
    )

    eligible = eligible.sort_values(
        by=["balanced_window", "total_pre_post", "cursor_commit_rows",
            "cursor_file_rows", "ts_rows_with_latest_commit", "panel_month_count",
            "repo_name"],
        ascending=[False, False, False, False, False, False, True],
    ).reset_index(drop=True)
    eligible.insert(0, "rank", eligible.index + 1)

    top = eligible.head(args.top_n).copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(output_path, index=False)
    all_eligible_path = output_path.with_name(output_path.stem + "_all_eligible.csv")
    eligible.to_csv(all_eligible_path, index=False)

    # Diagnostics
    print("Data dir:", data_dir)
    print("Panel rows:", len(panel))
    print("Treatment repos summarized:", summary["repo_name"].nunique())
    print("Duplicated (repo, month) rows collapsed:", n_dup_dropped)
    print(f"Eligible (>= {args.min_pre_months} pre & >= {args.min_post_months} post"
          + (", with cursor evidence" if args.require_cursor_evidence else "") + "):",
          len(eligible))
    if len(top) < args.top_n:
        print(f"WARNING: only {len(top)} eligible repos (< top-n={args.top_n}); "
              "consider lowering --min-pre-months/--min-post-months.")
    print("Top N written:", len(top), "->", output_path)
    print("All eligible output:", all_eligible_path)
    if not top.empty:
        print("balanced_window in selection: min=%d max=%d | touching data edge: %d/%d"
              % (top["balanced_window"].min(), top["balanced_window"].max(),
                 int(top["window_touches_data_edge"].sum()), len(top)))

    display_cols = [c for c in [
        "rank", "repo_name", "event_month", "panel_first_month", "panel_latest_month",
        "pre_panel_months", "event_months", "post_panel_months", "balanced_window",
        "cursor_commit_rows", "cursor_file_rows", "ts_rows_with_latest_commit",
        "repo_stars", "repo_primary_language",
    ] if c in top.columns]
    print("\nTop candidates:")
    print(top[display_cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()