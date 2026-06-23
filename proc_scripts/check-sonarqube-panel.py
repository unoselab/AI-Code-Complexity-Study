#!/usr/bin/env python3
"""Sanity-check the balanced panel after merging SonarQube metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


OUTCOME_COLS = [
    "static_analysis_warnings",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "ncloc",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "warnings_per_kloc",
    "complexity_per_kloc",
]

KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check merged SonarQube balanced panel."
    )
    parser.add_argument("--input", required=True, help="Merged panel CSV path.")
    parser.add_argument("--summary-output", required=True, help="Summary CSV path.")
    parser.add_argument("--missing-output", required=True, help="Missing rows CSV path.")
    return parser.parse_args()


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
    print("repos:", df["repo_name"].nunique())
    print("months:", df["time"].min(), "to", df["time"].max())
    print()

    print("Rows by dataset_source:")
    print(df["dataset_source"].value_counts(dropna=False).to_string())
    print()

    if {"repo_name", "time", "dataset_source"}.issubset(df.columns):
        duplicated_keys = df.duplicated(KEY_COLS).sum()
        print("duplicated repo-month-source keys:", duplicated_keys)
    else:
        duplicated_keys = None
        print("duplicated key check skipped: missing key columns")
    print()

    event_cols = [
        "ever_treated",
        "is_treatment",
        "post_event",
        "time_to_event",
        "sonarqube_source_less_commit",
        "sonarqube_any_raw_metric_missing",
    ]

    print("Important column coverage:")
    for col in event_cols + OUTCOME_COLS:
        if col in df.columns:
            print(f"{col}: {df[col].notna().sum()} / {len(df)}")
        else:
            print(f"{col}: MISSING")
    print()

    summary_rows = []

    for col in OUTCOME_COLS:
        if col not in df.columns:
            summary_rows.append(
                {
                    "metric": col,
                    "nonmissing": None,
                    "missing": None,
                    "mean": None,
                    "median": None,
                    "min": None,
                    "max": None,
                    "zero_count": None,
                }
            )
            continue

        x = pd.to_numeric(df[col], errors="coerce")
        summary_rows.append(
            {
                "metric": col,
                "nonmissing": int(x.notna().sum()),
                "missing": int(x.isna().sum()),
                "mean": x.mean(),
                "median": x.median(),
                "min": x.min(),
                "max": x.max(),
                "zero_count": int((x == 0).sum()),
            }
        )

    summary = pd.DataFrame(summary_rows)

    print("Outcome summary:")
    print(summary.to_string(index=False))
    print()

    missing_cols = [c for c in OUTCOME_COLS if c in df.columns]
    missing = df[df[missing_cols].isna().any(axis=1)].copy()

    print("Rows with missing analysis-ready outcomes:", len(missing))
    if len(missing):
        show_cols = KEY_COLS + [c for c in missing_cols if c in df.columns]
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
