#!/usr/bin/env python3
"""Merge SonarQube metrics into the balanced monthly DiD panel.

This script:
1. Loads the balanced treatment-control panel.
2. Loads treatment and control SonarQube scanned outputs.
3. Merges SonarQube metrics by repo_name, time/month, and dataset_source.
4. Preserves raw SonarQube metrics as *_raw columns.
5. Creates analysis-ready metric columns.
6. Handles confirmed source-less commits.
7. Computes derived quality outcomes and QC output.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd


METRIC_COLS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge SonarQube metrics into the balanced monthly DiD panel."
    )

    parser.add_argument(
        "--panel",
        required=True,
        help="Balanced panel CSV path.",
    )
    parser.add_argument(
        "--treatment-metrics",
        required=True,
        help="Treatment SonarQube scanned CSV path.",
    )
    parser.add_argument(
        "--control-metrics",
        required=True,
        help="Control SonarQube scanned CSV path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output merged panel CSV path.",
    )
    parser.add_argument(
        "--qc-output",
        required=True,
        help="Output QC summary CSV path.",
    )

    return parser.parse_args()


def read_csv_checked(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")

    logging.info("Loading %s: %s", label, path)
    df = pd.read_csv(path)
    logging.info("Loaded %s rows: %d", label, len(df))
    return df


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def prepare_metrics(df: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    """Prepare treatment/control SonarQube metrics for panel merge."""
    df = df.copy()

    require_columns(
        df,
        {"repo_name", "month", "latest_commit"} | set(METRIC_COLS),
        f"{dataset_source} metrics",
    )

    df = df.rename(columns={"month": "time"})
    df["dataset_source"] = dataset_source

    keep_cols = ["repo_name", "time", "dataset_source", "latest_commit"] + METRIC_COLS
    df = df[keep_cols].drop_duplicates(["repo_name", "time", "dataset_source"])

    rename_map = {"latest_commit": "sonarqube_latest_commit"}
    for col in METRIC_COLS:
        rename_map[col] = f"{col}_raw"

    prepared = df.rename(columns=rename_map)

    logging.info(
        "Prepared %s metrics: rows=%d, repos=%d, months=%s to %s",
        dataset_source,
        len(prepared),
        prepared["repo_name"].nunique(),
        prepared["time"].min(),
        prepared["time"].max(),
    )

    return prepared


def merge_panel_with_metrics(
    panel: pd.DataFrame,
    treatment_metrics: pd.DataFrame,
    control_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Merge balanced panel with prepared SonarQube metrics."""
    require_columns(
        panel,
        {"repo_name", "time", "dataset_source"},
        "balanced panel",
    )

    prepared_metrics = pd.concat(
        [
            prepare_metrics(treatment_metrics, "treatment"),
            prepare_metrics(control_metrics, "control"),
        ],
        ignore_index=True,
    )

    before_rows = len(panel)

    logging.info("Merging metrics into panel")
    merged = panel.merge(
        prepared_metrics,
        on=["repo_name", "time", "dataset_source"],
        how="left",
        validate="one_to_one",
    )

    if len(merged) != before_rows:
        raise ValueError(f"Row count changed after merge: {before_rows} -> {len(merged)}")

    logging.info("Merged panel rows: %d", len(merged))
    return merged


def add_analysis_ready_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """Create analysis-ready metrics while preserving raw columns."""
    merged = merged.copy()

    raw_cols = [f"{col}_raw" for col in METRIC_COLS]
    require_columns(merged, set(raw_cols), "merged panel")

    missing_metric_rows = merged[raw_cols].isna().any(axis=1)

    source_less = (
        merged["ncloc_raw"].isna()
        & merged["duplicated_lines_density_raw"].isna()
        & merged["comment_lines_density_raw"].isna()
        & merged["cognitive_complexity_raw"].isna()
        & (merged["bugs_raw"].fillna(-1) == 0)
        & (merged["vulnerabilities_raw"].fillna(-1) == 0)
        & (merged["code_smells_raw"].fillna(-1) == 0)
        & (merged["technical_debt_raw"].fillna(-1) == 0)
    )

    merged["sonarqube_source_less_commit"] = source_less.astype(int)
    merged["sonarqube_any_raw_metric_missing"] = missing_metric_rows.astype(int)

    for col in METRIC_COLS:
        merged[col] = merged[f"{col}_raw"]

    source_size_cols = [
        "ncloc",
        "duplicated_lines_density",
        "comment_lines_density",
        "cognitive_complexity",
    ]

    for col in source_size_cols:
        merged.loc[source_less, col] = 0

    for col in ["bugs", "vulnerabilities", "code_smells", "technical_debt"]:
        merged.loc[source_less, col] = merged.loc[source_less, col].fillna(0)

    merged["static_analysis_warnings"] = (
        merged["bugs"] + merged["vulnerabilities"] + merged["code_smells"]
    )

    merged["warnings_per_kloc"] = pd.NA
    has_ncloc = merged["ncloc"] > 0
    merged.loc[has_ncloc, "warnings_per_kloc"] = (
        merged.loc[has_ncloc, "static_analysis_warnings"]
        / merged.loc[has_ncloc, "ncloc"]
        * 1000
    )

    merged["complexity_per_kloc"] = pd.NA
    merged.loc[has_ncloc, "complexity_per_kloc"] = (
        merged.loc[has_ncloc, "cognitive_complexity"]
        / merged.loc[has_ncloc, "ncloc"]
        * 1000
    )

    logging.info("Rows with any raw metric missing: %d", int(missing_metric_rows.sum()))
    logging.info("Source-less commits identified: %d", int(source_less.sum()))

    return merged


def build_qc_table(merged: pd.DataFrame) -> pd.DataFrame:
    qc_rows: list[dict[str, object]] = []

    def add_qc(name: str, value: object) -> None:
        qc_rows.append({"check": name, "value": value})

    add_qc("merged_rows", len(merged))
    add_qc("treatment_rows", int((merged["dataset_source"] == "treatment").sum()))
    add_qc("control_rows", int((merged["dataset_source"] == "control").sum()))
    add_qc(
        "treatment_repos",
        merged.loc[merged["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add_qc(
        "control_repos",
        merged.loc[merged["dataset_source"] == "control", "repo_name"].nunique(),
    )
    add_qc(
        "rows_with_any_raw_metric_missing",
        int(merged["sonarqube_any_raw_metric_missing"].sum()),
    )
    add_qc(
        "source_less_commits",
        int(merged["sonarqube_source_less_commit"].sum()),
    )

    for col in METRIC_COLS + ["static_analysis_warnings"]:
        add_qc(f"{col}_analysis_nonmissing", int(merged[col].notna().sum()))

    return pd.DataFrame(qc_rows)


def log_raw_missing_rows(merged: pd.DataFrame) -> None:
    raw_cols = [f"{col}_raw" for col in METRIC_COLS]
    cols_to_show = [
        "repo_name",
        "time",
        "dataset_source",
        "sonarqube_latest_commit",
    ] + raw_cols

    raw_missing = merged[merged["sonarqube_any_raw_metric_missing"] == 1]

    logging.info("Rows with raw missing metrics: %d", len(raw_missing))
    if len(raw_missing):
        print()
        print("Rows with raw missing metrics:")
        print(raw_missing[cols_to_show].to_string(index=False))
    else:
        print()
        print("Rows with raw missing metrics: None")


def save_outputs(merged: pd.DataFrame, qc: pd.DataFrame, output: Path, qc_output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    qc_output.parent.mkdir(parents=True, exist_ok=True)

    merged.to_csv(output, index=False)
    qc.to_csv(qc_output, index=False)

    logging.info("Saved merged panel: %s", output)
    logging.info("Saved QC summary: %s", qc_output)


def main() -> None:
    setup_logging()
    args = parse_args()

    panel_path = Path(args.panel)
    treatment_path = Path(args.treatment_metrics)
    control_path = Path(args.control_metrics)
    output_path = Path(args.output)
    qc_output_path = Path(args.qc_output)

    logging.info("Starting SonarQube panel merge")

    panel = read_csv_checked(panel_path, "balanced panel")
    treatment = read_csv_checked(treatment_path, "treatment metrics")
    control = read_csv_checked(control_path, "control metrics")

    merged = merge_panel_with_metrics(panel, treatment, control)
    merged = add_analysis_ready_metrics(merged)
    qc = build_qc_table(merged)

    save_outputs(merged, qc, output_path, qc_output_path)

    print()
    print("QC summary:")
    print(qc.to_string(index=False))

    log_raw_missing_rows(merged)

    logging.info("Completed SonarQube panel merge")


if __name__ == "__main__":
    main()
