#!/usr/bin/env python3
"""Validate the strict repository-month AGC DiD input and supporting artifacts.

The validator is intentionally independent from the preparation script. It
recomputes structural invariants from the saved CSV/JSON artifacts and fails
when any required check is violated.

Primary validation areas:
- strict panel dimensions, unique keys, treatment/control counts, and dates;
- event-time, absorbing treatment, lead, and lag consistency;
- AGC count partitions and ratio numerator/denominator consistency;
- expected missing ratios only when the relevant denominator is zero;
- frozen-paper and Python-snapshot NCLOC readiness flags;
- repository-commit NCLOC arithmetic and fallback-file accounting;
- exact overlap between the main panel and repository-month outcome artifact;
- detector metadata provenance consistency;
- empty mismatch/error files emitted by run-py-3b.

The validator can also identify the exact Python files that required the
fallback physical-line rule because Python tokenization failed. Fallback is not
an inference failure: the file is still counted with the documented fallback
rule. The audit verifies that the located file count matches the aggregate
fallback count saved by run-py-3b.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import tempfile
import tokenize
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


KEY_COLS = ["repo_name", "time", "dataset_source"]
COMMIT_KEY_COLS = ["dataset_source", "repo_name", "latest_commit"]
ALLOWED_SOURCES = {"treatment", "control"}

LEAD_COLS = [f"lead_{value}" for value in range(6, 0, -1)]
LAG_COLS = [f"lag_{value}" for value in range(0, 7)]

COUNT_GROUPS = {
    "top_level": (
        "top_level_blocks_scored",
        "agc_top_level_blocks",
        "human_top_level_blocks",
        "agc_top_level_block_ratio",
    ),
    "function": (
        "function_blocks_scored",
        "agc_function_blocks",
        "human_function_blocks",
        "agc_function_block_ratio",
    ),
    "class": (
        "class_blocks_scored",
        "agc_class_blocks",
        "human_class_blocks",
        "agc_class_block_ratio",
    ),
}

MAIN_REQUIRED_COLUMNS = (
    KEY_COLS
    + [
        "is_treatment",
        "event",
        "post_event",
        "time_to_event",
    ]
    + LEAD_COLS
    + LAG_COLS
    + [
        "cursor",
        "commits",
        "lines_added",
        "lines_removed",
        "contributors",
        "stars",
        "issues",
        "age",
        "ncloc_paper",
        "ncloc_python_snapshot",
        "paper_covariate_matched",
        "python_snapshot_ncloc_matched",
        "analysis_ready_agc_paper_ncloc",
        "analysis_ready_agc_python_snapshot_ncloc",
        "latest_commit",
        "python_file_count",
        "files_analyzed",
        "failure_count",
        "agc_analysis_status",
        "agc_repo_month_matched",
    ]
    + [column for columns in COUNT_GROUPS.values() for column in columns]
)

COMMIT_NCLOC_REQUIRED_COLUMNS = COMMIT_KEY_COLS + [
    "snapshot_dir",
    "python_files_manifest",
    "regular_python_files_counted",
    "symlinks_skipped",
    "total_physical_lines",
    "comment_only_lines",
    "ncloc_python_snapshot",
    "tokenized_files",
    "fallback_files",
    "ncloc_failure_count",
]

METADATA_COMPARE_FIELDS = [
    "experiment",
    "classifier",
    "representation",
    "model_sha256",
    "model_key",
    "embedding_model_id",
    "max_len",
    "threshold_effective",
    "expected_score_mode",
]

EMPTY_QC_FILENAMES = [
    "agc_block_kind_aggregation_mismatches.csv",
    "agc_paper_duplicate_key_conflicts.csv",
    "agc_python_snapshot_ncloc_failures.csv",
    "agc_unmatched_python_snapshot_ncloc_rows.csv",
    "agc_unmatched_base_repo_months.csv",
]


class ValidationRecorder:
    """Collect validation checks and fail after writing all diagnostics."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def check(
        self,
        name: str,
        actual: Any,
        expected: Any,
        passed: bool,
        category: str,
        detail: str = "",
    ) -> None:
        self.checks.append(
            {
                "category": category,
                "check": name,
                "actual": actual,
                "expected": expected,
                "status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )
        if not passed:
            self.errors.append(
                {
                    "category": category,
                    "check": name,
                    "actual": actual,
                    "expected": expected,
                    "detail": detail,
                }
            )

    def require_zero(
        self,
        name: str,
        actual: int,
        category: str,
        detail: str = "",
    ) -> None:
        self.check(name, int(actual), 0, int(actual) == 0, category, detail)

    def require_equal(
        self,
        name: str,
        actual: Any,
        expected: Any,
        category: str,
        detail: str = "",
    ) -> None:
        self.check(name, actual, expected, actual == expected, category, detail)



def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate the strict repository-month AGC DiD input."
    )
    parser.add_argument("--input-panel", required=True, type=Path)
    parser.add_argument("--repo-commit-ncloc", required=True, type=Path)
    parser.add_argument("--repo-month-outcomes", required=True, type=Path)
    parser.add_argument("--prepare-qc-dir", required=True, type=Path)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--run-metadata-treatment", required=True, type=Path)
    parser.add_argument("--run-metadata-control", required=True, type=Path)
    parser.add_argument("--combined-validation", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--panel-label", default="strict")

    parser.add_argument("--expected-rows", type=int, default=1633)
    parser.add_argument("--expected-repositories", type=int, default=220)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-repositories", type=int, default=100)
    parser.add_argument("--expected-control-repositories", type=int, default=120)
    parser.add_argument("--expected-post-rows", type=int, default=432)
    parser.add_argument("--expected-min-time", default="2024-01")
    parser.add_argument("--expected-max-time", default="2025-08")
    parser.add_argument("--expected-commit-rows", type=int, default=1663)
    parser.add_argument("--expected-repo-month-outcome-rows", type=int, default=3043)
    parser.add_argument("--expected-paper-ready-rows", type=int, default=1568)
    parser.add_argument("--expected-snapshot-ready-rows", type=int, default=1568)
    parser.add_argument("--expected-top-level-nonmissing", type=int, default=1581)
    parser.add_argument("--expected-function-nonmissing", type=int, default=1566)
    parser.add_argument("--expected-class-nonmissing", type=int, default=1475)

    parser.add_argument(
        "--expected-experiment",
        default="codellama-7b_4500_complexity_stratified_maxlen2048",
    )
    parser.add_argument("--expected-classifier", default="svm")
    parser.add_argument("--expected-representation", default="ast")
    parser.add_argument("--expected-score-mode", default="decision")
    parser.add_argument(
        "--expected-model-key",
        default="codesearchnet_codellama-7b_python_merged_4500ast_",
    )
    parser.add_argument(
        "--audit-fallback-files",
        action="store_true",
        help="Locate exact files that required the tokenizer fallback rule.",
    )
    return parser.parse_args()



def require_file(path: Path, label: str) -> None:
    """Fail clearly when a required file is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")



def require_columns(df: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    """Fail clearly when required columns are absent."""
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")



def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        df.to_csv(handle, index=False)
    os.replace(temp_path, path)



def atomic_write_json(value: dict[str, Any], path: Path) -> None:
    """Write a JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)



def load_json(path: Path, label: str) -> dict[str, Any]:
    """Load a JSON object."""
    require_file(path, label)
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value



def to_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    """Convert selected columns to numeric values in place."""
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")



def finite_nonnegative_count(series: pd.Series) -> int:
    """Count nonmissing values that are non-finite or negative."""
    values = pd.to_numeric(series, errors="coerce")
    invalid = values.notna() & (~np.isfinite(values) | values.lt(0))
    return int(invalid.sum())



def month_difference(month: pd.Series, event: pd.Series) -> pd.Series:
    """Compute whole-month difference between YYYY-MM month and event values."""
    month_period = pd.PeriodIndex(month.astype(str), freq="M")
    event_period = pd.PeriodIndex(event.astype(str), freq="M")
    return pd.Series(
        (month_period.year - event_period.year) * 12
        + (month_period.month - event_period.month),
        index=month.index,
        dtype="int64",
    )



def validate_main_panel(
    df: pd.DataFrame,
    args: argparse.Namespace,
    recorder: ValidationRecorder,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate the main repository-month AGC panel."""
    require_columns(df, MAIN_REQUIRED_COLUMNS, "AGC DiD input panel")

    df = df.copy()
    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["time"] = df["time"].astype(str).str.slice(0, 7)
    df["dataset_source"] = df["dataset_source"].astype(str).str.strip()

    numeric_columns = [
        "is_treatment",
        "post_event",
        "time_to_event",
        "cursor",
        "commits",
        "lines_added",
        "lines_removed",
        "contributors",
        "stars",
        "issues",
        "age",
        "ncloc_paper",
        "ncloc_python_snapshot",
        "paper_covariate_matched",
        "python_snapshot_ncloc_matched",
        "analysis_ready_agc_paper_ncloc",
        "analysis_ready_agc_python_snapshot_ncloc",
        "python_file_count",
        "files_analyzed",
        "failure_count",
        "agc_repo_month_matched",
    ] + LEAD_COLS + LAG_COLS
    for columns in COUNT_GROUPS.values():
        numeric_columns.extend(columns)
    to_numeric(df, numeric_columns)

    recorder.require_equal("panel_rows", len(df), args.expected_rows, "dimensions")
    recorder.require_equal(
        "panel_repositories",
        int(df["repo_name"].nunique()),
        args.expected_repositories,
        "dimensions",
    )
    recorder.require_zero(
        "duplicate_repo_time_source_keys",
        int(df.duplicated(KEY_COLS).sum()),
        "keys",
    )

    invalid_sources = sorted(set(df["dataset_source"]) - ALLOWED_SOURCES)
    recorder.require_equal("invalid_dataset_sources", invalid_sources, [], "keys")

    treatment = df["dataset_source"].eq("treatment")
    control = df["dataset_source"].eq("control")
    recorder.require_equal(
        "treatment_rows", int(treatment.sum()), args.expected_treatment_rows, "dimensions"
    )
    recorder.require_equal(
        "control_rows", int(control.sum()), args.expected_control_rows, "dimensions"
    )
    recorder.require_equal(
        "treatment_repositories",
        int(df.loc[treatment, "repo_name"].nunique()),
        args.expected_treatment_repositories,
        "dimensions",
    )
    recorder.require_equal(
        "control_repositories",
        int(df.loc[control, "repo_name"].nunique()),
        args.expected_control_repositories,
        "dimensions",
    )
    recorder.require_equal(
        "post_event_rows",
        int(df["post_event"].fillna(0).sum()),
        args.expected_post_rows,
        "event",
    )
    recorder.require_equal("min_time", df["time"].min(), args.expected_min_time, "dates")
    recorder.require_equal("max_time", df["time"].max(), args.expected_max_time, "dates")

    invalid_binary_columns = [
        "is_treatment",
        "post_event",
        "cursor",
        "paper_covariate_matched",
        "python_snapshot_ncloc_matched",
        "analysis_ready_agc_paper_ncloc",
        "analysis_ready_agc_python_snapshot_ncloc",
        "agc_repo_month_matched",
    ] + LEAD_COLS + LAG_COLS
    for column in invalid_binary_columns:
        invalid_count = int((~df[column].isin([0, 1])).sum())
        recorder.require_zero(f"invalid_binary_{column}", invalid_count, "types")

    recorder.require_zero(
        "is_treatment_post_event_mismatches",
        int(df["is_treatment"].ne(df["post_event"]).sum()),
        "event",
    )
    recorder.require_zero(
        "control_post_event_nonzero",
        int((control & df["post_event"].ne(0)).sum()),
        "event",
    )
    recorder.require_zero(
        "control_is_treatment_nonzero",
        int((control & df["is_treatment"].ne(0)).sum()),
        "event",
    )
    recorder.require_zero(
        "control_event_nonmissing",
        int((control & df["event"].notna()).sum()),
        "event",
    )
    recorder.require_zero(
        "control_time_to_event_nonmissing",
        int((control & df["time_to_event"].notna()).sum()),
        "event",
    )
    recorder.require_zero(
        "treatment_event_missing",
        int((treatment & df["event"].isna()).sum()),
        "event",
    )
    recorder.require_zero(
        "treatment_time_to_event_missing",
        int((treatment & df["time_to_event"].isna()).sum()),
        "event",
    )

    treatment_rows = df.loc[treatment].copy()
    recomputed_time_to_event = month_difference(
        treatment_rows["time"], treatment_rows["event"]
    )
    observed_time_to_event = treatment_rows["time_to_event"].astype("int64")
    recorder.require_zero(
        "treatment_time_to_event_mismatches",
        int(observed_time_to_event.ne(recomputed_time_to_event).sum()),
        "event",
    )

    expected_post = treatment_rows["time_to_event"].ge(0).astype(int)
    recorder.require_zero(
        "treatment_absorbing_post_mismatches",
        int(treatment_rows["post_event"].astype(int).ne(expected_post).sum()),
        "event",
    )

    for value in range(1, 6):
        expected = treatment_rows["time_to_event"].eq(-value).astype(int)
        recorder.require_zero(
            f"lead_{value}_mismatches",
            int(treatment_rows[f"lead_{value}"].astype(int).ne(expected).sum()),
            "lead_lag",
        )
    expected_lead_6 = treatment_rows["time_to_event"].le(-6).astype(int)
    recorder.require_zero(
        "lead_6_mismatches",
        int(treatment_rows["lead_6"].astype(int).ne(expected_lead_6).sum()),
        "lead_lag",
    )

    for value in range(0, 6):
        expected = treatment_rows["time_to_event"].eq(value).astype(int)
        recorder.require_zero(
            f"lag_{value}_mismatches",
            int(treatment_rows[f"lag_{value}"].astype(int).ne(expected).sum()),
            "lead_lag",
        )
    expected_lag_6 = treatment_rows["time_to_event"].ge(6).astype(int)
    recorder.require_zero(
        "lag_6_mismatches",
        int(treatment_rows["lag_6"].astype(int).ne(expected_lag_6).sum()),
        "lead_lag",
    )
    recorder.require_zero(
        "control_nonzero_lead_lag_values",
        int(df.loc[control, LEAD_COLS + LAG_COLS].fillna(0).ne(0).sum().sum()),
        "lead_lag",
    )

    integer_count_columns = [
        "python_file_count",
        "files_analyzed",
        "failure_count",
    ] + [
        column
        for group_columns in COUNT_GROUPS.values()
        for column in group_columns[:3]
    ]
    for column in integer_count_columns:
        values = df[column]
        invalid = values.notna() & (
            ~np.isfinite(values) | values.lt(0) | values.mod(1).ne(0)
        )
        recorder.require_zero(
            f"invalid_nonnegative_integer_{column}", int(invalid.sum()), "counts"
        )

    matched = df["agc_repo_month_matched"].eq(1)
    recorder.require_equal(
        "agc_repo_month_matched_rows",
        int(matched.sum()),
        args.expected_rows,
        "coverage",
    )
    recorder.require_zero(
        "agc_failure_count_sum",
        int(df["failure_count"].fillna(0).sum()),
        "coverage",
    )
    recorder.require_zero(
        "missing_agc_analysis_status",
        int(df["agc_analysis_status"].isna().sum()),
        "coverage",
    )
    recorder.require_zero(
        "missing_agc_repo_month_status_rows",
        int(df["agc_analysis_status"].astype(str).eq("missing_agc_repo_month").sum()),
        "coverage",
    )

    partition_checks = {
        "top_level_function_plus_class": df["top_level_blocks_scored"].ne(
            df["function_blocks_scored"] + df["class_blocks_scored"]
        ),
        "top_level_agc_function_plus_class": df["agc_top_level_blocks"].ne(
            df["agc_function_blocks"] + df["agc_class_blocks"]
        ),
        "top_level_human_function_plus_class": df["human_top_level_blocks"].ne(
            df["human_function_blocks"] + df["human_class_blocks"]
        ),
    }
    for label, mismatch in partition_checks.items():
        recorder.require_zero(label, int((matched & mismatch).sum()), "counts")

    coverage_rows: list[dict[str, Any]] = []
    expected_nonmissing = {
        "top_level": args.expected_top_level_nonmissing,
        "function": args.expected_function_nonmissing,
        "class": args.expected_class_nonmissing,
    }
    for label, (total_col, agc_col, human_col, ratio_col) in COUNT_GROUPS.items():
        partition_mismatch = matched & df[total_col].ne(df[agc_col] + df[human_col])
        recorder.require_zero(
            f"{label}_agc_human_partition_mismatches",
            int(partition_mismatch.sum()),
            "counts",
        )

        denominator_positive = df[total_col].gt(0)
        ratio_missing = df[ratio_col].isna()
        recorder.require_zero(
            f"{label}_ratio_missing_with_positive_denominator",
            int((matched & denominator_positive & ratio_missing).sum()),
            "ratios",
        )
        recorder.require_zero(
            f"{label}_ratio_nonmissing_with_zero_denominator",
            int((matched & df[total_col].eq(0) & df[ratio_col].notna()).sum()),
            "ratios",
        )

        observed_ratio = df.loc[matched & denominator_positive, ratio_col]
        expected_ratio = (
            df.loc[matched & denominator_positive, agc_col]
            / df.loc[matched & denominator_positive, total_col]
        )
        ratio_mismatch = ~np.isclose(
            observed_ratio,
            expected_ratio,
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        )
        recorder.require_zero(
            f"{label}_ratio_value_mismatches",
            int(ratio_mismatch.sum()),
            "ratios",
        )
        invalid_range = df[ratio_col].notna() & ~df[ratio_col].between(0, 1)
        recorder.require_zero(
            f"{label}_ratio_outside_unit_interval",
            int(invalid_range.sum()),
            "ratios",
        )

        nonmissing = int(df[ratio_col].notna().sum())
        recorder.require_equal(
            f"{label}_ratio_nonmissing",
            nonmissing,
            expected_nonmissing[label],
            "coverage",
        )
        coverage_rows.append(
            {
                "outcome": ratio_col,
                "rows": len(df),
                "nonmissing": nonmissing,
                "missing": int(df[ratio_col].isna().sum()),
                "zero_denominator": int(df[total_col].eq(0).sum()),
                "mean": df[ratio_col].mean(),
                "median": df[ratio_col].median(),
            }
        )

    for column in [
        "commits",
        "lines_added",
        "lines_removed",
        "contributors",
        "stars",
        "issues",
        "age",
        "ncloc_paper",
        "ncloc_python_snapshot",
    ]:
        recorder.require_zero(
            f"invalid_finite_nonnegative_{column}",
            finite_nonnegative_count(df[column]),
            "covariates",
        )

    recorder.require_equal(
        "python_snapshot_ncloc_matched_rows",
        int(df["python_snapshot_ncloc_matched"].sum()),
        args.expected_rows,
        "ncloc",
    )
    recorder.require_equal(
        "ncloc_python_snapshot_nonmissing",
        int(df["ncloc_python_snapshot"].notna().sum()),
        args.expected_rows,
        "ncloc",
    )

    expected_paper_ready = (
        matched
        & df["agc_top_level_block_ratio"].notna()
        & df[["stars", "issues", "age", "ncloc_paper"]].notna().all(axis=1)
    ).astype(int)
    expected_snapshot_ready = (
        matched
        & df["agc_top_level_block_ratio"].notna()
        & df[["stars", "issues", "age", "ncloc_python_snapshot"]]
        .notna()
        .all(axis=1)
        & df["python_snapshot_ncloc_matched"].eq(1)
    ).astype(int)

    recorder.require_zero(
        "paper_ncloc_readiness_flag_mismatches",
        int(
            df["analysis_ready_agc_paper_ncloc"]
            .astype(int)
            .ne(expected_paper_ready)
            .sum()
        ),
        "readiness",
    )
    recorder.require_zero(
        "snapshot_ncloc_readiness_flag_mismatches",
        int(
            df["analysis_ready_agc_python_snapshot_ncloc"]
            .astype(int)
            .ne(expected_snapshot_ready)
            .sum()
        ),
        "readiness",
    )
    recorder.require_equal(
        "paper_ncloc_ready_rows",
        int(df["analysis_ready_agc_paper_ncloc"].sum()),
        args.expected_paper_ready_rows,
        "readiness",
    )
    recorder.require_equal(
        "snapshot_ncloc_ready_rows",
        int(df["analysis_ready_agc_python_snapshot_ncloc"].sum()),
        args.expected_snapshot_ready_rows,
        "readiness",
    )

    by_source = (
        df.groupby("dataset_source", as_index=False)
        .agg(
            rows=("repo_name", "size"),
            repositories=("repo_name", "nunique"),
            post_rows=("post_event", "sum"),
            top_level_nonmissing=("agc_top_level_block_ratio", "count"),
            function_nonmissing=("agc_function_block_ratio", "count"),
            class_nonmissing=("agc_class_block_ratio", "count"),
            paper_ncloc_nonmissing=("ncloc_paper", "count"),
            snapshot_ncloc_nonmissing=("ncloc_python_snapshot", "count"),
            paper_ready_rows=("analysis_ready_agc_paper_ncloc", "sum"),
            snapshot_ready_rows=("analysis_ready_agc_python_snapshot_ncloc", "sum"),
        )
    )
    return by_source, pd.DataFrame(coverage_rows)



def validate_commit_ncloc(
    df: pd.DataFrame,
    args: argparse.Namespace,
    recorder: ValidationRecorder,
) -> pd.DataFrame:
    """Validate repository-commit Python snapshot NCLOC output."""
    require_columns(df, COMMIT_NCLOC_REQUIRED_COLUMNS, "repository-commit NCLOC")
    df = df.copy()
    for column in COMMIT_KEY_COLS:
        df[column] = df[column].astype(str).str.strip()

    numeric_columns = [
        "python_files_manifest",
        "regular_python_files_counted",
        "symlinks_skipped",
        "total_physical_lines",
        "comment_only_lines",
        "ncloc_python_snapshot",
        "tokenized_files",
        "fallback_files",
        "ncloc_failure_count",
    ]
    to_numeric(df, numeric_columns)

    recorder.require_equal(
        "repo_commit_ncloc_rows", len(df), args.expected_commit_rows, "commit_ncloc"
    )
    recorder.require_zero(
        "repo_commit_ncloc_duplicate_keys",
        int(df.duplicated(COMMIT_KEY_COLS).sum()),
        "commit_ncloc",
    )
    invalid_sources = sorted(set(df["dataset_source"]) - ALLOWED_SOURCES)
    recorder.require_equal(
        "repo_commit_ncloc_invalid_sources", invalid_sources, [], "commit_ncloc"
    )

    for column in numeric_columns:
        invalid = df[column].isna() | (
            ~np.isfinite(df[column]) | df[column].lt(0) | df[column].mod(1).ne(0)
        )
        recorder.require_zero(
            f"repo_commit_invalid_{column}", int(invalid.sum()), "commit_ncloc"
        )

    recorder.require_zero(
        "repo_commit_ncloc_failure_count_sum",
        int(df["ncloc_failure_count"].sum()),
        "commit_ncloc",
    )
    recorder.require_zero(
        "repo_commit_file_manifest_count_mismatches",
        int(
            df["python_files_manifest"]
            .ne(df["regular_python_files_counted"] + df["symlinks_skipped"])
            .sum()
        ),
        "commit_ncloc",
    )
    recorder.require_zero(
        "repo_commit_tokenizer_fallback_count_mismatches",
        int(
            df["regular_python_files_counted"]
            .ne(df["tokenized_files"] + df["fallback_files"])
            .sum()
        ),
        "commit_ncloc",
    )
    recorder.require_zero(
        "repo_commit_physical_line_lower_bound_violations",
        int(
            df["total_physical_lines"]
            .lt(df["ncloc_python_snapshot"] + df["comment_only_lines"])
            .sum()
        ),
        "commit_ncloc",
    )

    summary = (
        df.groupby("dataset_source", as_index=False)
        .agg(
            unique_commits=("repo_name", "size"),
            repositories=("repo_name", "nunique"),
            regular_python_files_counted=("regular_python_files_counted", "sum"),
            tokenized_files=("tokenized_files", "sum"),
            fallback_files=("fallback_files", "sum"),
            ncloc_failure_count=("ncloc_failure_count", "sum"),
            ncloc_python_snapshot_sum=("ncloc_python_snapshot", "sum"),
        )
    )
    all_row = pd.DataFrame(
        [
            {
                "dataset_source": "all",
                "unique_commits": len(df),
                "repositories": int(df["repo_name"].nunique()),
                "regular_python_files_counted": int(
                    df["regular_python_files_counted"].sum()
                ),
                "tokenized_files": int(df["tokenized_files"].sum()),
                "fallback_files": int(df["fallback_files"].sum()),
                "ncloc_failure_count": int(df["ncloc_failure_count"].sum()),
                "ncloc_python_snapshot_sum": int(
                    df["ncloc_python_snapshot"].sum()
                ),
            }
        ]
    )
    return pd.concat([summary, all_row], ignore_index=True)



def validate_repo_month_outcomes(
    main: pd.DataFrame,
    outcomes: pd.DataFrame,
    args: argparse.Namespace,
    recorder: ValidationRecorder,
) -> None:
    """Validate the repository-month outcome artifact and exact main-panel overlap."""
    required = KEY_COLS + [
        "latest_commit",
        "python_file_count",
        "files_analyzed",
        "failure_count",
        "agc_analysis_status",
        "ncloc_python_snapshot",
        "python_snapshot_ncloc_matched",
    ] + [column for columns in COUNT_GROUPS.values() for column in columns]
    require_columns(outcomes, required, "repository-month AGC outcomes")
    outcomes = outcomes.copy()
    outcomes["time"] = outcomes["time"].astype(str).str.slice(0, 7)
    outcomes["repo_name"] = outcomes["repo_name"].astype(str).str.strip()
    outcomes["dataset_source"] = outcomes["dataset_source"].astype(str).str.strip()

    recorder.require_equal(
        "repo_month_outcome_rows",
        len(outcomes),
        args.expected_repo_month_outcome_rows,
        "repo_month_outcomes",
    )
    recorder.require_zero(
        "repo_month_outcome_duplicate_keys",
        int(outcomes.duplicated(KEY_COLS).sum()),
        "repo_month_outcomes",
    )

    compare_columns = [
        "latest_commit",
        "python_file_count",
        "files_analyzed",
        "failure_count",
        "agc_analysis_status",
        "ncloc_python_snapshot",
        "python_snapshot_ncloc_matched",
    ] + [column for columns in COUNT_GROUPS.values() for column in columns]
    left = main[KEY_COLS + compare_columns].copy()
    right = outcomes[KEY_COLS + compare_columns].copy()
    merged = left.merge(
        right,
        on=KEY_COLS,
        how="left",
        validate="one_to_one",
        suffixes=("_main", "_outcome"),
        indicator=True,
    )
    recorder.require_zero(
        "main_rows_missing_from_repo_month_outcomes",
        int(merged["_merge"].ne("both").sum()),
        "repo_month_outcomes",
    )

    mismatch_count = 0
    for column in compare_columns:
        left_col = merged[f"{column}_main"]
        right_col = merged[f"{column}_outcome"]
        if column in {"latest_commit", "agc_analysis_status"}:
            mismatch = left_col.fillna("<NA>").astype(str).ne(
                right_col.fillna("<NA>").astype(str)
            )
        elif column.endswith("_ratio") or column == "ncloc_python_snapshot":
            mismatch = ~np.isclose(
                pd.to_numeric(left_col, errors="coerce"),
                pd.to_numeric(right_col, errors="coerce"),
                rtol=1e-12,
                atol=1e-12,
                equal_nan=True,
            )
        else:
            mismatch = pd.to_numeric(left_col, errors="coerce").fillna(-1).ne(
                pd.to_numeric(right_col, errors="coerce").fillna(-1)
            )
        mismatch_count += int(mismatch.sum())
    recorder.require_zero(
        "main_repo_month_outcome_value_mismatches",
        mismatch_count,
        "repo_month_outcomes",
    )



def validate_detector_provenance(
    args: argparse.Namespace,
    recorder: ValidationRecorder,
) -> pd.DataFrame:
    """Validate treatment/control detector provenance and saved comparison QC."""
    combined = load_json(args.combined_validation, "combined detector validation")
    recorder.require_equal(
        "combined_detector_status", combined.get("status"), "PASS", "detector"
    )
    recorder.require_equal(
        "combined_detector_metadata_errors",
        combined.get("metadata_comparison_errors", []),
        [],
        "detector",
    )
    recorder.require_equal(
        "combined_detector_errors", combined.get("errors", []), [], "detector"
    )

    treatment = load_json(args.run_metadata_treatment, "treatment run metadata")
    control = load_json(args.run_metadata_control, "control run metadata")
    rows: list[dict[str, Any]] = []
    for field in METADATA_COMPARE_FIELDS:
        treatment_value = treatment.get(field)
        control_value = control.get(field)
        matches = treatment_value == control_value
        recorder.require_equal(
            f"detector_metadata_match_{field}",
            int(matches),
            1,
            "detector",
            detail=f"treatment={treatment_value!r}; control={control_value!r}",
        )
        rows.append(
            {
                "field": field,
                "treatment_value": treatment_value,
                "control_value": control_value,
                "matches": int(matches),
            }
        )

    expected_values = {
        "experiment": args.expected_experiment,
        "classifier": args.expected_classifier,
        "representation": args.expected_representation,
        "expected_score_mode": args.expected_score_mode,
        "model_key": args.expected_model_key,
    }
    for field, expected in expected_values.items():
        recorder.require_equal(
            f"expected_detector_{field}",
            treatment.get(field),
            expected,
            "detector",
        )

    qc_path = args.prepare_qc_dir / "agc_detector_metadata_comparison.csv"
    require_file(qc_path, "run-py-3b detector metadata comparison")
    qc = pd.read_csv(qc_path, low_memory=False)
    require_columns(
        qc,
        ["field", "treatment_value", "control_value", "matches"],
        "run-py-3b detector metadata comparison",
    )
    recorder.require_equal(
        "detector_metadata_qc_rows",
        len(qc),
        len(METADATA_COMPARE_FIELDS),
        "detector",
    )
    recorder.require_zero(
        "detector_metadata_qc_mismatches",
        int(pd.to_numeric(qc["matches"], errors="coerce").fillna(0).ne(1).sum()),
        "detector",
    )
    return pd.DataFrame(rows)



def validate_prepare_qc_files(
    args: argparse.Namespace,
    recorder: ValidationRecorder,
) -> pd.DataFrame:
    """Validate required run-py-3b mismatch/error files are header-only."""
    rows: list[dict[str, Any]] = []
    for filename in EMPTY_QC_FILENAMES:
        path = args.prepare_qc_dir / filename
        require_file(path, f"run-py-3b QC file {filename}")
        frame = pd.read_csv(path, low_memory=False)
        data_rows = len(frame)
        recorder.require_zero(
            f"empty_qc_{filename}",
            data_rows,
            "prepare_qc",
            detail=str(path),
        )
        rows.append(
            {
                "file": filename,
                "path": str(path),
                "data_rows": data_rows,
                "status": "PASS" if data_rows == 0 else "FAIL",
            }
        )

    qc_summary_path = args.prepare_qc_dir / "agc_did_input_qc.csv"
    require_file(qc_summary_path, "run-py-3b QC summary")
    summary = pd.read_csv(qc_summary_path, low_memory=False)
    require_columns(summary, ["check", "value"], "run-py-3b QC summary")
    summary_map = dict(zip(summary["check"].astype(str), summary["value"]))
    expected_checks = {
        "base_rows": args.expected_rows,
        "output_rows": args.expected_rows,
        "row_count_preserved": 1,
        "base_repositories": args.expected_repositories,
        "matched_base_rows": args.expected_rows,
        "unmatched_base_rows": 0,
        "duplicate_output_keys": 0,
        "treatment_rows": args.expected_treatment_rows,
        "control_rows": args.expected_control_rows,
        "agc_failure_count_sum": 0,
        "python_snapshot_ncloc_matched_rows": args.expected_rows,
        "analysis_ready_agc_paper_ncloc_rows": args.expected_paper_ready_rows,
        "analysis_ready_agc_python_snapshot_ncloc_rows": args.expected_snapshot_ready_rows,
    }
    for check, expected in expected_checks.items():
        actual_raw = summary_map.get(check)
        actual = pd.to_numeric(pd.Series([actual_raw]), errors="coerce").iloc[0]
        actual_value = int(actual) if pd.notna(actual) else None
        recorder.require_equal(
            f"prepare_qc_summary_{check}", actual_value, expected, "prepare_qc"
        )
    return pd.DataFrame(rows)



def tokenizer_fallback_reason(data: bytes) -> str | None:
    """Return the tokenizer exception when the fallback rule is required."""
    reader = io.BytesIO(data).readline
    encoding, _ = tokenize.detect_encoding(reader)
    text = data.decode(encoding)
    try:
        list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None



def audit_fallback_files(
    commit_ncloc: pd.DataFrame,
    snapshot_root: Path,
    recorder: ValidationRecorder,
) -> pd.DataFrame:
    """Locate exact files that required the Python tokenizer fallback rule."""
    if not snapshot_root.is_dir():
        raise FileNotFoundError(f"snapshot root not found: {snapshot_root}")

    candidate_commits = commit_ncloc.loc[
        pd.to_numeric(commit_ncloc["fallback_files"], errors="coerce").fillna(0).gt(0)
    ].copy()
    audit_rows: list[dict[str, Any]] = []

    for row in candidate_commits.itertuples(index=False):
        source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        commit = str(row.latest_commit)
        repo_slug = repo_name.replace("/", "_")
        snapshot_dir = snapshot_root / source / repo_slug / commit
        manifest_path = snapshot_dir / "_files.jsonl"
        require_file(manifest_path, "snapshot file manifest for fallback audit")

        with manifest_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if str(record.get("file_type", "")) != "file":
                    continue
                relative_path = str(record["relative_path"])
                source_path = snapshot_dir / relative_path
                data = source_path.read_bytes()
                reason = tokenizer_fallback_reason(data)
                if reason is None:
                    continue
                audit_rows.append(
                    {
                        "dataset_source": source,
                        "repo_name": repo_name,
                        "latest_commit": commit,
                        "relative_path": relative_path,
                        "snapshot_path": str(source_path),
                        "manifest_line": line_number,
                        "fallback_reason": reason,
                    }
                )

    audit = pd.DataFrame(
        audit_rows,
        columns=[
            "dataset_source",
            "repo_name",
            "latest_commit",
            "relative_path",
            "snapshot_path",
            "manifest_line",
            "fallback_reason",
        ],
    )
    expected_total = int(
        pd.to_numeric(commit_ncloc["fallback_files"], errors="coerce").fillna(0).sum()
    )
    recorder.require_equal(
        "fallback_file_audit_count", len(audit), expected_total, "fallback_audit"
    )

    if not audit.empty:
        expected_by_commit = (
            commit_ncloc.loc[
                pd.to_numeric(commit_ncloc["fallback_files"], errors="coerce")
                .fillna(0)
                .gt(0),
                COMMIT_KEY_COLS + ["fallback_files"],
            ]
            .copy()
        )
        observed_by_commit = (
            audit.groupby(COMMIT_KEY_COLS, as_index=False)
            .size()
            .rename(columns={"size": "observed_fallback_files"})
        )
        checked = expected_by_commit.merge(
            observed_by_commit,
            on=COMMIT_KEY_COLS,
            how="left",
            validate="one_to_one",
        )
        checked["observed_fallback_files"] = checked[
            "observed_fallback_files"
        ].fillna(0)
        recorder.require_zero(
            "fallback_file_audit_commit_count_mismatches",
            int(
                pd.to_numeric(checked["fallback_files"], errors="coerce")
                .ne(pd.to_numeric(checked["observed_fallback_files"], errors="coerce"))
                .sum()
            ),
            "fallback_audit",
        )
    return audit



def main() -> int:
    """Run all validation checks and write detailed artifacts."""
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for path, label in [
        (args.input_panel, "AGC DiD input panel"),
        (args.repo_commit_ncloc, "repository-commit snapshot NCLOC"),
        (args.repo_month_outcomes, "repository-month AGC outcomes"),
        (args.run_metadata_treatment, "treatment run metadata"),
        (args.run_metadata_control, "control run metadata"),
        (args.combined_validation, "combined detector validation"),
    ]:
        require_file(path, label)
    if not args.prepare_qc_dir.is_dir():
        raise FileNotFoundError(f"run-py-3b QC directory not found: {args.prepare_qc_dir}")

    recorder = ValidationRecorder()

    main_panel = pd.read_csv(
        args.input_panel,
        low_memory=False,
        dtype={"latest_commit": "string"},
    )
    by_source, outcome_coverage = validate_main_panel(main_panel, args, recorder)

    commit_ncloc = pd.read_csv(
        args.repo_commit_ncloc,
        low_memory=False,
        dtype={"latest_commit": "string"},
    )
    commit_summary = validate_commit_ncloc(commit_ncloc, args, recorder)

    repo_month_outcomes = pd.read_csv(
        args.repo_month_outcomes,
        low_memory=False,
        dtype={"latest_commit": "string"},
    )
    validate_repo_month_outcomes(main_panel, repo_month_outcomes, args, recorder)

    detector_metadata = validate_detector_provenance(args, recorder)
    prepare_qc_files = validate_prepare_qc_files(args, recorder)

    if args.audit_fallback_files:
        fallback_audit = audit_fallback_files(
            commit_ncloc,
            args.snapshot_root,
            recorder,
        )
    else:
        fallback_audit = pd.DataFrame(
            columns=[
                "dataset_source",
                "repo_name",
                "latest_commit",
                "relative_path",
                "snapshot_path",
                "manifest_line",
                "fallback_reason",
            ]
        )
        recorder.check(
            "fallback_file_audit_skipped",
            1,
            1,
            True,
            "fallback_audit",
            "Run with --audit-fallback-files to identify exact fallback files.",
        )

    checks = pd.DataFrame(recorder.checks)
    errors = pd.DataFrame(
        recorder.errors,
        columns=["category", "check", "actual", "expected", "detail"],
    )
    status = "PASS" if errors.empty else "FAIL"

    summary = {
        "status": status,
        "panel_label": args.panel_label,
        "input_panel": str(args.input_panel),
        "repo_commit_ncloc": str(args.repo_commit_ncloc),
        "repo_month_outcomes": str(args.repo_month_outcomes),
        "prepare_qc_dir": str(args.prepare_qc_dir),
        "rows": len(main_panel),
        "repositories": int(main_panel["repo_name"].nunique()),
        "checks_total": len(checks),
        "checks_passed": int(checks["status"].eq("PASS").sum()),
        "checks_failed": int(checks["status"].eq("FAIL").sum()),
        "fallback_audit_enabled": bool(args.audit_fallback_files),
        "fallback_files_located": len(fallback_audit),
        "errors": recorder.errors,
    }

    output_paths = {
        "summary": args.output_dir / "agc_did_input_validation_summary.json",
        "checks": args.output_dir / "agc_did_input_validation_checks.csv",
        "errors": args.output_dir / "agc_did_input_validation_errors.csv",
        "by_source": args.output_dir / "agc_did_input_validation_by_source.csv",
        "outcome_coverage": args.output_dir / "agc_did_input_outcome_coverage.csv",
        "commit_summary": args.output_dir / "agc_python_snapshot_ncloc_validation_summary.csv",
        "detector_metadata": args.output_dir / "agc_detector_provenance_validation.csv",
        "prepare_qc_files": args.output_dir / "agc_prepare_qc_file_validation.csv",
        "fallback_audit": args.output_dir / "agc_python_snapshot_fallback_files.csv",
    }

    atomic_write_json(summary, output_paths["summary"])
    atomic_write_csv(checks, output_paths["checks"])
    atomic_write_csv(errors, output_paths["errors"])
    atomic_write_csv(by_source, output_paths["by_source"])
    atomic_write_csv(outcome_coverage, output_paths["outcome_coverage"])
    atomic_write_csv(commit_summary, output_paths["commit_summary"])
    atomic_write_csv(detector_metadata, output_paths["detector_metadata"])
    atomic_write_csv(prepare_qc_files, output_paths["prepare_qc_files"])
    atomic_write_csv(fallback_audit, output_paths["fallback_audit"])

    print("=" * 72)
    print("AGC DiD input validation")
    print(f"Status:              {status}")
    print(f"Panel rows:          {len(main_panel)}")
    print(f"Repositories:        {main_panel['repo_name'].nunique()}")
    print(f"Checks passed:       {summary['checks_passed']}/{summary['checks_total']}")
    print(f"Checks failed:       {summary['checks_failed']}")
    print(f"Fallback files:      {len(fallback_audit)}")
    print(f"Validation output:   {args.output_dir}")
    print(f"Summary:             {output_paths['summary']}")
    print("=" * 72)

    if not errors.empty:
        print()
        print("Failed checks:")
        print(errors.to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
