#!/usr/bin/env python3
"""Sanity-check merged SonarQube panels from run9c."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]

RAW_METRIC_COLS = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

ANALYSIS_OUTCOME_COLS = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
    "warnings_per_kloc",
    "complexity_per_kloc",
    "code_smells_per_kloc",
]

CORE_DID_OUTCOME_COLS = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
]

QC_FLAG_COLS = [
    "sonarqube_any_raw_metric_missing",
    "sonarqube_all_raw_metrics_missing",
    "sonarqube_ncloc_zero",
    "sonarqube_static_warnings_missing",
    "sonarqube_duplicate_density_missing",
    "sonarqube_cognitive_complexity_missing",
    "sonarqube_quality_outcomes_complete",
]

EVENT_COLS = [
    "ever_treated",
    "is_treatment",
    "post_event",
    "time_to_event",
]

EXTRA_COLS = [
    "sonarqube_latest_commit",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check merged SonarQube panel from run9c."
    )
    parser.add_argument("--input", required=True, help="Merged panel CSV path.")
    parser.add_argument("--summary-output", required=True, help="Summary CSV path.")
    parser.add_argument("--missing-output", required=True, help="Missing rows CSV path.")
    return parser.parse_args()


def nonmissing_count(df: pd.DataFrame, col: str) -> int | None:
    if col not in df.columns:
        return None
    return int(df[col].notna().sum())


def missing_count(df: pd.DataFrame, col: str) -> int | None:
    if col not in df.columns:
        return None
    return int(df[col].isna().sum())


def numeric_summary(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {
            "metric": col,
            "exists": 0,
            "nonmissing": None,
            "missing": None,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "zero_count": None,
        }

    x = pd.to_numeric(df[col], errors="coerce")

    return {
        "metric": col,
        "exists": 1,
        "nonmissing": int(x.notna().sum()),
        "missing": int(x.isna().sum()),
        "mean": x.mean(),
        "median": x.median(),
        "min": x.min(),
        "max": x.max(),
        "zero_count": int((x == 0).sum()),
    }


def print_coverage(df: pd.DataFrame, cols: list[str], title: str) -> None:
    print(title)
    for col in cols:
        if col in df.columns:
            print(f"{col}: {df[col].notna().sum()} / {len(df)}")
        else:
            print(f"{col}: MISSING")
    print()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    summary_path = Path(args.summary_output)
    missing_path = Path(args.missing_output)

    df = pd.read_csv(input_path)

    print("=" * 72)
    print("Merged SonarQube panel sanity check")
    print("=" * 72)
    print("input:", input_path)
    print("rows:", len(df))

    if "repo_name" in df.columns:
        print("repos:", df["repo_name"].nunique())
    else:
        print("repos: MISSING repo_name column")

    if "time" in df.columns:
        print("months:", df["time"].min(), "to", df["time"].max())
    else:
        print("months: MISSING time column")

    print()

    if "dataset_source" in df.columns:
        print("Rows by dataset_source:")
        print(df["dataset_source"].value_counts(dropna=False).to_string())
    else:
        print("Rows by dataset_source: MISSING dataset_source column")
    print()

    if set(KEY_COLS).issubset(df.columns):
        duplicated_keys = int(df.duplicated(KEY_COLS).sum())
        print("duplicated repo-month-source keys:", duplicated_keys)
    else:
        duplicated_keys = None
        print("duplicated key check skipped: missing key columns")
    print()

    print_coverage(df, EVENT_COLS, "Event column coverage:")
    print_coverage(df, EXTRA_COLS, "SonarQube commit column coverage:")
    print_coverage(df, RAW_METRIC_COLS, "Raw metric coverage:")
    print_coverage(df, ANALYSIS_OUTCOME_COLS, "Analysis-ready outcome coverage:")
    print_coverage(df, QC_FLAG_COLS, "QC flag coverage:")

    summary_cols = RAW_METRIC_COLS + ANALYSIS_OUTCOME_COLS + QC_FLAG_COLS
    summary_rows = [numeric_summary(df, col) for col in summary_cols]
    summary = pd.DataFrame(summary_rows)

    print("Metric and QC summary:")
    print(summary.to_string(index=False))
    print()

    existing_core_cols = [c for c in CORE_DID_OUTCOME_COLS if c in df.columns]
    if existing_core_cols:
        missing = df[df[existing_core_cols].isna().any(axis=1)].copy()
    else:
        missing = df.copy()

    print("Rows with missing core DiD quality outcomes:", len(missing))

    if len(missing):
        show_cols = [
            c
            for c in KEY_COLS
            + EXTRA_COLS
            + CORE_DID_OUTCOME_COLS
            + QC_FLAG_COLS
            if c in missing.columns
        ]
        print(missing[show_cols].head(50).to_string(index=False))

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(summary_path, index=False)
    missing.to_csv(missing_path, index=False)

    print()
    print("saved summary:", summary_path)
    print("saved missing rows:", missing_path)


if __name__ == "__main__":
    main()
