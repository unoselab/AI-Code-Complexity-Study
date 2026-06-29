#!/usr/bin/env python3
"""
Merge SonarQube metrics into monthly DiD panels.

This script:
1. Loads a treatment-control panel.
2. Loads treatment and control SonarQube scanned outputs.
3. Merges SonarQube metrics by repo_name, time/month, and dataset_source.
4. Preserves raw SonarQube metrics as *_raw columns.
5. Creates analysis-ready quality outcomes.
6. Adds QC flags for missing metrics and ncloc == 0 rows.
7. Writes a QC summary CSV.

Important policy:
- Do not impute missing SonarQube quality metrics.
- Do not drop rows with missing metrics.
- Do not drop rows where ncloc == 0.
- Keep missing scanner failures as missing.
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

RAW_METRIC_COLS = [f"{col}_raw" for col in METRIC_COLS]


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge SonarQube metrics into a monthly DiD panel."
    )
    parser.add_argument("--panel", required=True, help="Input panel CSV path.")
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
    parser.add_argument("--output", required=True, help="Output merged panel CSV path.")
    parser.add_argument("--qc-output", required=True, help="Output QC summary CSV path.")
    return parser.parse_args()


def read_csv_checked(path: Path, label: str) -> pd.DataFrame:
    """Read a CSV file and fail clearly if it does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")

    logging.info("Loading %s: %s", label, path)
    df = pd.read_csv(path)
    logging.info("Loaded %s rows: %d", label, len(df))
    return df


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Validate required columns."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def normalize_technical_debt_column(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize SonarQube technical debt column name."""
    df = df.copy()
    long_name = "software_quality_maintainability_remediation_effort"

    if "technical_debt" not in df.columns and long_name in df.columns:
        df = df.rename(columns={long_name: "technical_debt"})

    if "technical_debt" in df.columns and long_name in df.columns:
        df["technical_debt"] = df["technical_debt"].combine_first(df[long_name])

    return df


def prepare_metrics(df: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    """Prepare treatment/control SonarQube metrics for panel merge."""
    df = normalize_technical_debt_column(df)

    require_columns(
        df,
        {"repo_name", "month", "latest_commit"} | set(METRIC_COLS),
        f"{dataset_source} metrics",
    )

    df = df.copy()
    df["repo_name"] = df["repo_name"].astype(str)
    df["time"] = df["month"].astype(str)
    df["dataset_source"] = dataset_source

    keep_cols = ["repo_name", "time", "dataset_source", "latest_commit"] + METRIC_COLS
    df = df[keep_cols].copy()

    duplicate_count = int(df.duplicated(["repo_name", "time", "dataset_source"]).sum())
    if duplicate_count:
        logging.warning(
            "%s metrics has %d duplicate repo-time-source rows; keeping first",
            dataset_source,
            duplicate_count,
        )

    df = df.drop_duplicates(["repo_name", "time", "dataset_source"], keep="first")

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
    """Merge panel with treatment/control SonarQube metrics."""
    require_columns(panel, {"repo_name", "time", "dataset_source"}, "panel")

    panel = panel.copy()
    panel["repo_name"] = panel["repo_name"].astype(str)
    panel["time"] = panel["time"].astype(str)
    panel["dataset_source"] = panel["dataset_source"].astype(str)

    prepared_metrics = pd.concat(
        [
            prepare_metrics(treatment_metrics, "treatment"),
            prepare_metrics(control_metrics, "control"),
        ],
        ignore_index=True,
    )

    before_rows = len(panel)
    logging.info("Merging SonarQube metrics into panel")

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


def add_analysis_ready_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Create analysis-ready quality outcomes and QC flags."""
    df = df.copy()
    require_columns(df, set(RAW_METRIC_COLS), "merged panel")

    for col in METRIC_COLS:
        df[col] = df[f"{col}_raw"]

    df["static_analysis_warnings"] = (
        df["bugs_raw"] + df["vulnerabilities_raw"] + df["code_smells_raw"]
    )
    df["duplicate_line_density"] = df["duplicated_lines_density_raw"]
    df["code_complexity"] = df["cognitive_complexity_raw"]

    valid_ncloc = df["ncloc_raw"].notna() & (df["ncloc_raw"] > 0)

    df["warnings_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "warnings_per_kloc"] = (
        df.loc[valid_ncloc, "static_analysis_warnings"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["complexity_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "complexity_per_kloc"] = (
        df.loc[valid_ncloc, "code_complexity"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["code_smells_per_kloc"] = pd.NA
    df.loc[valid_ncloc, "code_smells_per_kloc"] = (
        df.loc[valid_ncloc, "code_smells_raw"]
        / df.loc[valid_ncloc, "ncloc_raw"]
        * 1000.0
    )

    df["sonarqube_any_raw_metric_missing"] = df[RAW_METRIC_COLS].isna().any(axis=1).astype(int)
    df["sonarqube_all_raw_metrics_missing"] = df[RAW_METRIC_COLS].isna().all(axis=1).astype(int)

    df["sonarqube_ncloc_zero"] = (
        df["ncloc_raw"].notna() & (df["ncloc_raw"] == 0)
    ).astype(int)

    df["sonarqube_static_warnings_missing"] = (
        df[["bugs_raw", "vulnerabilities_raw", "code_smells_raw"]]
        .isna()
        .any(axis=1)
    ).astype(int)

    df["sonarqube_duplicate_density_missing"] = (
        df["duplicated_lines_density_raw"].isna().astype(int)
    )

    df["sonarqube_cognitive_complexity_missing"] = (
        df["cognitive_complexity_raw"].isna().astype(int)
    )

    df["sonarqube_quality_outcomes_complete"] = (
        (df["sonarqube_static_warnings_missing"] == 0)
        & (df["sonarqube_duplicate_density_missing"] == 0)
        & (df["sonarqube_cognitive_complexity_missing"] == 0)
    ).astype(int)

    return df


def build_qc(panel: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Build QC summary dataframe."""
    rows = []

    def add(check: str, value) -> None:
        rows.append({"check": check, "value": value})

    add("input_panel_rows", len(panel))
    add("merged_rows", len(merged))
    add("row_count_preserved", int(len(panel) == len(merged)))

    add("repos", merged["repo_name"].nunique())
    add("treatment_rows", int((merged["dataset_source"] == "treatment").sum()))
    add("control_rows", int((merged["dataset_source"] == "control").sum()))
    add(
        "treatment_repos",
        merged.loc[merged["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add(
        "control_repos",
        merged.loc[merged["dataset_source"] == "control", "repo_name"].nunique(),
    )
    add("min_time", merged["time"].min())
    add("max_time", merged["time"].max())

    add(
        "duplicate_repo_time_source_rows",
        int(merged.duplicated(["repo_name", "time", "dataset_source"]).sum()),
    )
    add("missing_sonarqube_latest_commit", int(merged["sonarqube_latest_commit"].isna().sum()))

    for col in RAW_METRIC_COLS:
        add(f"{col}_nonmissing", int(merged[col].notna().sum()))
        add(f"{col}_missing", int(merged[col].isna().sum()))

    for col in [
        "static_analysis_warnings",
        "duplicate_line_density",
        "code_complexity",
        "warnings_per_kloc",
        "complexity_per_kloc",
        "code_smells_per_kloc",
    ]:
        add(f"{col}_nonmissing", int(merged[col].notna().sum()))
        add(f"{col}_missing", int(merged[col].isna().sum()))

    for flag in [
        "sonarqube_any_raw_metric_missing",
        "sonarqube_all_raw_metrics_missing",
        "sonarqube_ncloc_zero",
        "sonarqube_static_warnings_missing",
        "sonarqube_duplicate_density_missing",
        "sonarqube_cognitive_complexity_missing",
        "sonarqube_quality_outcomes_complete",
    ]:
        add(f"{flag}_sum", int(merged[flag].sum()))

    return pd.DataFrame(rows)


def main() -> int:
    """Run the merge."""
    setup_logging()
    args = parse_args()

    panel_path = Path(args.panel)
    treatment_path = Path(args.treatment_metrics)
    control_path = Path(args.control_metrics)
    output_path = Path(args.output)
    qc_output_path = Path(args.qc_output)

    panel = read_csv_checked(panel_path, "panel")
    treatment_metrics = read_csv_checked(treatment_path, "treatment metrics")
    control_metrics = read_csv_checked(control_path, "control metrics")

    merged = merge_panel_with_metrics(panel, treatment_metrics, control_metrics)
    merged = add_analysis_ready_metrics(merged)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_output_path.parent.mkdir(parents=True, exist_ok=True)

    merged.to_csv(output_path, index=False)
    logging.info("Saved merged panel: %s", output_path)

    qc = build_qc(panel, merged)
    qc.to_csv(qc_output_path, index=False)
    logging.info("Saved QC summary: %s", qc_output_path)

    logging.info("QC summary:")
    logging.info("\n%s", qc.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
