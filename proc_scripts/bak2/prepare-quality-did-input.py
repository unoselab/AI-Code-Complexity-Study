#!/usr/bin/env python3
"""Prepare quality-outcome panel for DiD analysis."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "ever_treated",
    "is_treatment",
    "post_event",
    "static_analysis_warnings",
    "duplicated_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "ncloc",
]


OUTCOME_COLS = [
    "static_analysis_warnings",
    "log_static_analysis_warnings",
    "duplicated_lines_density",
    "cognitive_complexity",
    "log_cognitive_complexity",
    "technical_debt",
    "log_technical_debt",
    "ncloc",
    "log_ncloc",
]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare quality outcome input for DiD analysis."
    )
    parser.add_argument("--input", required=True, help="Merged SonarQube panel CSV.")
    parser.add_argument("--output", required=True, help="Output quality DiD panel CSV.")
    parser.add_argument("--qc-output", required=True, help="Output QC CSV.")
    return parser.parse_args()


def require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def main() -> None:
    setup_logging()
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    qc_path = Path(args.qc_output)

    logging.info("Loading merged panel: %s", input_path)
    df = pd.read_csv(input_path)

    require_columns(df, REQUIRED_COLS)

    logging.info("Rows: %d", len(df))
    logging.info("Repos: %d", df["repo_name"].nunique())
    logging.info("Months: %s to %s", df["time"].min(), df["time"].max())

    duplicated_keys = df.duplicated(["repo_name", "time", "dataset_source"]).sum()
    if duplicated_keys:
        raise ValueError(f"Duplicated repo-time-source keys: {duplicated_keys}")

    numeric_cols = [
        "static_analysis_warnings",
        "duplicated_lines_density",
        "cognitive_complexity",
        "technical_debt",
        "ncloc",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise ValueError(f"Missing values in required outcome column: {col}")
        if (df[col] < 0).any():
            raise ValueError(f"Negative values found in outcome column: {col}")

    df["log_static_analysis_warnings"] = np.log1p(df["static_analysis_warnings"])
    df["log_cognitive_complexity"] = np.log1p(df["cognitive_complexity"])
    df["log_technical_debt"] = np.log1p(df["technical_debt"])
    df["log_ncloc"] = np.log1p(df["ncloc"])

    qc_rows = []

    def add_qc(check: str, value: object) -> None:
        qc_rows.append({"check": check, "value": value})

    add_qc("rows", len(df))
    add_qc("repos", df["repo_name"].nunique())
    add_qc("treatment_rows", int((df["dataset_source"] == "treatment").sum()))
    add_qc("control_rows", int((df["dataset_source"] == "control").sum()))
    add_qc("treatment_repos", df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique())
    add_qc("control_repos", df.loc[df["dataset_source"] == "control", "repo_name"].nunique())
    add_qc("duplicated_repo_time_source_keys", int(duplicated_keys))
    add_qc("control_post_event_sum", int(df.loc[df["dataset_source"] == "control", "post_event"].sum()))
    add_qc("source_less_commit_rows", int(df.get("sonarqube_source_less_commit", pd.Series([0] * len(df))).sum()))

    for col in OUTCOME_COLS:
        add_qc(f"{col}_nonmissing", int(df[col].notna().sum()))
        add_qc(f"{col}_finite", int(np.isfinite(pd.to_numeric(df[col], errors="coerce")).sum()))
        add_qc(f"{col}_zero_count", int((df[col] == 0).sum()))

    qc = pd.DataFrame(qc_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)
    qc.to_csv(qc_path, index=False)

    logging.info("Saved quality DiD panel: %s", output_path)
    logging.info("Saved QC: %s", qc_path)

    print()
    print("QC summary:")
    print(qc.to_string(index=False))


if __name__ == "__main__":
    main()
