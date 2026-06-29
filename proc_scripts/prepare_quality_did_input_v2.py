#!/usr/bin/env python3
"""Prepare analysis-ready quality DiD input panels from run9c/run9d outputs.

This script keeps the full merged panel, adds analysis-ready variables,
adds readiness flags, writes a complete-case quality DiD file if requested,
and writes QC summaries for verification before R/DiD analysis.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd


KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]

BASE_DID_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "ever_treated",
    "is_treatment",
    "post_event",
]

CORE_QUALITY_OUTCOMES = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
]

RATE_OUTCOMES = [
    "warnings_per_kloc",
    "complexity_per_kloc",
    "code_smells_per_kloc",
]

OPTIONAL_QUALITY_OUTCOMES = [
    "technical_debt",
    "ncloc",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "bugs",
    "vulnerabilities",
    "code_smells",
]

LOG_OUTCOME_MAP = {
    "static_analysis_warnings": "log_static_analysis_warnings",
    "code_complexity": "log_code_complexity",
    "technical_debt": "log_technical_debt",
    "ncloc": "log_ncloc",
    "bugs": "log_bugs",
    "vulnerabilities": "log_vulnerabilities",
    "code_smells": "log_code_smells",
    "warnings_per_kloc": "log_warnings_per_kloc",
    "complexity_per_kloc": "log_complexity_per_kloc",
    "code_smells_per_kloc": "log_code_smells_per_kloc",
}

QC_FLAG_COLS = [
    "sonarqube_any_raw_metric_missing",
    "sonarqube_all_raw_metrics_missing",
    "sonarqube_ncloc_zero",
    "sonarqube_static_warnings_missing",
    "sonarqube_duplicate_density_missing",
    "sonarqube_cognitive_complexity_missing",
    "sonarqube_quality_outcomes_complete",
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
        description="Prepare quality DiD input panel from run9 SonarQube merged panel."
    )
    parser.add_argument("--input", required=True, help="Merged SonarQube panel CSV.")
    parser.add_argument("--output", required=True, help="Output full quality DiD panel CSV.")
    parser.add_argument("--qc-output", required=True, help="Output QC summary CSV.")
    parser.add_argument(
        "--missing-output",
        required=True,
        help="Output rows with missing core quality outcomes.",
    )
    parser.add_argument(
        "--complete-output",
        required=False,
        default=None,
        help="Optional output CSV containing only complete core quality outcome rows.",
    )
    parser.add_argument(
        "--panel-label",
        required=False,
        default="panel",
        help="Human-readable panel label for QC output.",
    )
    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    """Require essential columns."""
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def to_numeric_if_present(df: pd.DataFrame, col: str) -> None:
    """Convert a column to numeric if it exists."""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def copy_first_available(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    """Create target column from the first available candidate column."""
    if target in df.columns:
        return

    for candidate in candidates:
        if candidate in df.columns:
            df[target] = df[candidate]
            return


def add_alias_and_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add run9-compatible analysis columns and aliases."""
    df = df.copy()

    copy_first_available(df, "ncloc", ["ncloc_raw"])
    copy_first_available(df, "technical_debt", ["technical_debt_raw"])
    copy_first_available(df, "bugs", ["bugs_raw"])
    copy_first_available(df, "vulnerabilities", ["vulnerabilities_raw"])
    copy_first_available(df, "code_smells", ["code_smells_raw"])
    copy_first_available(df, "duplicated_lines_density", ["duplicated_lines_density_raw"])
    copy_first_available(df, "comment_lines_density", ["comment_lines_density_raw"])
    copy_first_available(df, "cognitive_complexity", ["cognitive_complexity_raw"])

    copy_first_available(
        df,
        "duplicate_line_density",
        ["duplicated_lines_density", "duplicated_lines_density_raw"],
    )
    copy_first_available(
        df,
        "code_complexity",
        ["cognitive_complexity", "cognitive_complexity_raw"],
    )

    for col in (
        CORE_QUALITY_OUTCOMES
        + RATE_OUTCOMES
        + OPTIONAL_QUALITY_OUTCOMES
        + RAW_METRIC_COLS
    ):
        to_numeric_if_present(df, col)

    if "static_analysis_warnings" not in df.columns:
        if {"bugs", "vulnerabilities", "code_smells"}.issubset(df.columns):
            df["static_analysis_warnings"] = df[
                ["bugs", "vulnerabilities", "code_smells"]
            ].sum(axis=1, min_count=3)

    valid_ncloc = df.get("ncloc", pd.Series(index=df.index, dtype=float)).notna()
    if "ncloc" in df.columns:
        valid_ncloc = df["ncloc"].notna() & (df["ncloc"] > 0)

    if "warnings_per_kloc" not in df.columns and {
        "static_analysis_warnings",
        "ncloc",
    }.issubset(df.columns):
        df["warnings_per_kloc"] = np.nan
        df.loc[valid_ncloc, "warnings_per_kloc"] = (
            df.loc[valid_ncloc, "static_analysis_warnings"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "complexity_per_kloc" not in df.columns and {
        "code_complexity",
        "ncloc",
    }.issubset(df.columns):
        df["complexity_per_kloc"] = np.nan
        df.loc[valid_ncloc, "complexity_per_kloc"] = (
            df.loc[valid_ncloc, "code_complexity"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "code_smells_per_kloc" not in df.columns and {
        "code_smells",
        "ncloc",
    }.issubset(df.columns):
        df["code_smells_per_kloc"] = np.nan
        df.loc[valid_ncloc, "code_smells_per_kloc"] = (
            df.loc[valid_ncloc, "code_smells"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    for source_col, log_col in LOG_OUTCOME_MAP.items():
        if source_col not in df.columns:
            continue

        x = pd.to_numeric(df[source_col], errors="coerce")
        df[log_col] = np.where(x.notna() & (x >= 0), np.log1p(x), np.nan)

    return df


def add_readiness_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add DiD readiness flags."""
    df = df.copy()

    if set(KEY_COLS).issubset(df.columns):
        df["did_duplicate_repo_time_source_key"] = df.duplicated(KEY_COLS).astype(int)
    else:
        df["did_duplicate_repo_time_source_key"] = 1

    df["analysis_ready_core_quality"] = (
        df[CORE_QUALITY_OUTCOMES].notna().all(axis=1)
        if set(CORE_QUALITY_OUTCOMES).issubset(df.columns)
        else False
    )

    existing_rate_cols = [c for c in RATE_OUTCOMES if c in df.columns]
    if existing_rate_cols:
        df["analysis_ready_quality_rates"] = df[existing_rate_cols].notna().all(axis=1)
    else:
        df["analysis_ready_quality_rates"] = False

    df["analysis_ready_did_base"] = (
        df[BASE_DID_COLS].notna().all(axis=1)
        & (df["did_duplicate_repo_time_source_key"] == 0)
        & df["dataset_source"].isin(["treatment", "control"])
    )

    df["analysis_ready_quality_did"] = (
        df["analysis_ready_did_base"] & df["analysis_ready_core_quality"]
    )

    for col in [
        "analysis_ready_core_quality",
        "analysis_ready_quality_rates",
        "analysis_ready_did_base",
        "analysis_ready_quality_did",
    ]:
        df[col] = df[col].astype(int)

    return df


def assert_no_invalid_values(df: pd.DataFrame) -> None:
    """Fail on structural problems, not on expected SonarQube missingness."""
    if set(KEY_COLS).issubset(df.columns):
        duplicate_count = int(df.duplicated(KEY_COLS).sum())
        if duplicate_count:
            raise ValueError(f"Duplicated repo-time-source keys: {duplicate_count}")

    for col in CORE_QUALITY_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES + RATE_OUTCOMES:
        if col not in df.columns:
            continue

        x = pd.to_numeric(df[col], errors="coerce")
        negative_count = int((x < 0).sum())
        if negative_count:
            raise ValueError(f"Negative values found in {col}: {negative_count}")


def build_qc(df: pd.DataFrame, input_rows: int, output_rows: int, panel_label: str) -> pd.DataFrame:
    """Build QC summary."""
    rows: list[dict[str, object]] = []

    def add(check: str, value: object) -> None:
        rows.append({"check": check, "value": value})

    add("panel_label", panel_label)
    add("input_rows", input_rows)
    add("output_rows", output_rows)
    add("row_count_preserved_in_full_output", int(input_rows == output_rows))
    add("repos", df["repo_name"].nunique() if "repo_name" in df.columns else None)
    add("min_time", df["time"].min() if "time" in df.columns else None)
    add("max_time", df["time"].max() if "time" in df.columns else None)

    add("treatment_rows", int((df["dataset_source"] == "treatment").sum()))
    add("control_rows", int((df["dataset_source"] == "control").sum()))
    add(
        "treatment_repos",
        df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add(
        "control_repos",
        df.loc[df["dataset_source"] == "control", "repo_name"].nunique(),
    )

    add("duplicate_repo_time_source_rows", int(df["did_duplicate_repo_time_source_key"].sum()))
    add("analysis_ready_did_base_rows", int(df["analysis_ready_did_base"].sum()))
    add("analysis_ready_core_quality_rows", int(df["analysis_ready_core_quality"].sum()))
    add("analysis_ready_quality_did_rows", int(df["analysis_ready_quality_did"].sum()))
    add("missing_core_quality_rows", int((df["analysis_ready_core_quality"] == 0).sum()))

    if "time_to_event" in df.columns:
        add(
            "treatment_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "treatment", "time_to_event"].notna().sum()),
        )
        add(
            "control_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "control", "time_to_event"].notna().sum()),
        )

    if "post_event" in df.columns:
        add("post_event_sum", int(pd.to_numeric(df["post_event"], errors="coerce").fillna(0).sum()))
        add(
            "control_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "control", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )
        add(
            "treatment_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "treatment", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )

    if "sonarqube_latest_commit" in df.columns:
        add("sonarqube_latest_commit_missing", int(df["sonarqube_latest_commit"].isna().sum()))

    for col in QC_FLAG_COLS:
        if col in df.columns:
            add(f"{col}_sum", int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum()))
        else:
            add(f"{col}_sum", None)

    for col in CORE_QUALITY_OUTCOMES + RATE_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES:
        if col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce")
            add(f"{col}_nonmissing", int(x.notna().sum()))
            add(f"{col}_missing", int(x.isna().sum()))
            add(f"{col}_zero_count", int((x == 0).sum()))
            add(f"{col}_mean", float(x.mean()) if x.notna().any() else None)
            add(f"{col}_median", float(x.median()) if x.notna().any() else None)
        else:
            add(f"{col}_nonmissing", None)
            add(f"{col}_missing", None)

    for source_col, log_col in LOG_OUTCOME_MAP.items():
        if log_col in df.columns:
            x = pd.to_numeric(df[log_col], errors="coerce")
            add(f"{log_col}_nonmissing", int(x.notna().sum()))
            add(f"{log_col}_finite", int(np.isfinite(x).sum()))

    return pd.DataFrame(rows)


def main() -> int:
    """Run the preparation."""
    setup_logging()
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    qc_path = Path(args.qc_output)
    missing_path = Path(args.missing_output)
    complete_path = Path(args.complete_output) if args.complete_output else None

    logging.info("Loading merged panel: %s", input_path)
    df = pd.read_csv(input_path)
    input_rows = len(df)

    require_columns(df, BASE_DID_COLS, "input panel")

    logging.info("Input rows: %d", input_rows)
    logging.info("Input repos: %d", df["repo_name"].nunique())
    logging.info("Input months: %s to %s", df["time"].min(), df["time"].max())

    df = add_alias_and_analysis_columns(df)
    require_columns(df, CORE_QUALITY_OUTCOMES, "prepared panel")

    df = add_readiness_flags(df)
    assert_no_invalid_values(df)

    missing_core = df[df["analysis_ready_core_quality"] == 0].copy()
    complete_df = df[df["analysis_ready_quality_did"] == 1].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    if complete_path:
        complete_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)
    missing_core.to_csv(missing_path, index=False)

    if complete_path:
        complete_df.to_csv(complete_path, index=False)

    qc = build_qc(df, input_rows=input_rows, output_rows=len(df), panel_label=args.panel_label)
    if complete_path:
        qc = pd.concat(
            [
                qc,
                pd.DataFrame(
                    [
                        {"check": "complete_output_path", "value": str(complete_path)},
                        {"check": "complete_output_rows", "value": len(complete_df)},
                        {"check": "complete_output_repos", "value": complete_df["repo_name"].nunique()},
                    ]
                ),
            ],
            ignore_index=True,
        )

    qc.to_csv(qc_path, index=False)

    logging.info("Saved full quality DiD input: %s", output_path)
    logging.info("Saved missing core quality rows: %s", missing_path)
    if complete_path:
        logging.info("Saved complete-case quality DiD input: %s", complete_path)
    logging.info("Saved QC: %s", qc_path)

    print()
    print("QC summary:")
    print(qc.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
