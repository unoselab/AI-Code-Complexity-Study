#!/usr/bin/env python3
"""
Prepare Borusyak DiD inputs for Python commit-function AGC outcomes.

This revision joins the paper-compatible covariates and preserves event-study
lead/lag indicators from the matched repository-month panel.

Covariate groups
----------------
Shared covariates (used in both specifications):
- age
- contributors
- stars
- issues

ncloc_paper and ncloc_python_snapshot are two competing code-size covariate
definitions (Specification 1 vs Specification 2 in the quality Borusyak
analysis; see run-py-3b/run-py-3c/run-py-3d). Both are preserved in this
script's output for storage and diagnostics, but they must never be entered
together in the same regression formula -- doing so double-controls for code
size and induces strong collinearity between two measurements of the same
underlying quantity. Downstream R code must pick exactly one of:

- Paper NCLOC specification: age, ncloc_paper, contributors, stars, issues
- Python snapshot NCLOC specification: age, ncloc_python_snapshot,
  contributors, stars, issues

The script also creates the transformed columns used by the planned R model:
- log1p_age
- log1p_contributors
- log1p_stars
- log1p_issues

ncloc_paper and ncloc_python_snapshot are intentionally left untransformed
here; confirm the exact functional form (log1p vs raw) against the existing
quality Borusyak Rmd/helper before finalizing the R formula.

Lead/lag columns are retained for validation and plotting context. They are not
intended to be included as ordinary regression covariates.

Missing covariates
-------------------
age/stars/issues/contributors have 15 known unmatched repository-months and
ncloc_paper has 37 known missing values (see run-py-3b). These are expected,
genuine missingness -- never filled with 0 -- and are reported as
informational counts. A separate hard check confirms the counts match the
known run-py-3b values exactly, so a silent regression in join coverage is
caught even though missingness itself is not treated as failure.

Analysis-ready flags
---------------------
Complete-case readiness is computed explicitly per specification rather than
left for R to determine implicitly, so that dropping rows for missing
covariates cannot silently change the sample between specifications without
being visible in this script's output:

- analysis_ready_paper_ncloc
- analysis_ready_python_snapshot_ncloc
- analysis_ready_ratio_paper_ncloc
- analysis_ready_ratio_python_snapshot_ncloc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


KEY_COLUMNS = ["dataset_source", "repo_name", "time"]

FULL_SAMPLE_OUTCOMES = [
    "has_function_change_event",
    "log1p_function_change_events",
    "log1p_agc_function_change_events",
    "log1p_hwc_function_change_events",
]

CONDITIONAL_OUTCOMES = ["agc_function_change_event_ratio"]

REQUIRED_EVENT_COLUMNS = ["time_to_event", "event", "post_event"]
REQUIRED_COUNT_COLUMNS = [
    "function_change_events",
    "agc_function_change_events",
    "hwc_function_change_events",
]

COVARIATE_COLUMNS = [
    "age",
    "ncloc_paper",
    "ncloc_python_snapshot",
    "contributors",
    "stars",
    "issues",
]
# These are the covariates known (from run-py-3b) to have genuine,
# expected missingness. Do not require these to be all non-missing.
EXPECTED_NULLABLE_COVARIATE_COLUMNS = [
    "age",
    "contributors",
    "stars",
    "issues",
    "ncloc_paper",
    "ncloc_python_snapshot",
]
# Covariates shared by both NCLOC specifications.
SHARED_COVARIATE_COLUMNS = ["age", "contributors", "stars", "issues"]
SHARED_TRANSFORMED_COVARIATE_COLUMNS = [
    "log1p_age",
    "log1p_contributors",
    "log1p_stars",
    "log1p_issues",
]
# The two competing code-size specifications. Never combine both NCLOC
# columns in a single regression formula -- see module docstring.
PAPER_NCLOC_SPECIFICATION_COLUMNS = SHARED_TRANSFORMED_COVARIATE_COLUMNS + [
    "ncloc_paper"
]
PYTHON_SNAPSHOT_NCLOC_SPECIFICATION_COLUMNS = (
    SHARED_TRANSFORMED_COVARIATE_COLUMNS + ["ncloc_python_snapshot"]
)
# Analysis-ready flags computed by this script for each specification.
READINESS_FLAG_COLUMNS = [
    "analysis_ready_paper_ncloc",
    "analysis_ready_python_snapshot_ncloc",
    "analysis_ready_ratio_paper_ncloc",
    "analysis_ready_ratio_python_snapshot_ncloc",
]
# Existing readiness flags computed upstream (run-py-4a) for the older
# changed-block outcome. Joined as diagnostic-only context; never used as
# the model sample flag for the commit-function outcomes in this script.
EXISTING_DIAGNOSTIC_READINESS_COLUMNS = [
    "analysis_ready_agc_changed_block_paper_ncloc",
    "analysis_ready_agc_changed_block_python_snapshot_ncloc",
]
LEAD_LAG_COLUMNS = [
    "lead_6",
    "lead_5",
    "lead_4",
    "lead_3",
    "lead_2",
    "lead_1",
    "lag_0",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "lag_5",
    "lag_6",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare covariate-complete Borusyak DiD input panels for "
            "commit-function AGC outcomes."
        )
    )
    parser.add_argument(
        "--input-table",
        required=True,
        type=Path,
        help="Complete run-py-5d repository-month analysis table.",
    )
    parser.add_argument(
        "--covariate-panel",
        required=True,
        type=Path,
        help=(
            "Matched repository-month panel containing paper-compatible "
            "covariates and lead/lag indicators."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for run-py-5e outputs.",
    )
    parser.add_argument("--expected-rows", type=int, default=1633)
    parser.add_argument(
        "--expected-positive-event-rows", type=int, default=1289
    )
    parser.add_argument("--expected-zero-event-rows", type=int, default=344)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument(
        "--expected-parse-exclusion-months", type=int, default=97
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    label: str,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {missing}. "
            f"Available columns: {list(frame.columns)}"
        )


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
    return result


def require_unique_keys(frame: pd.DataFrame, label: str) -> None:
    duplicate_mask = frame.duplicated(KEY_COLUMNS, keep=False)
    if duplicate_mask.any():
        sample = frame.loc[duplicate_mask, KEY_COLUMNS].head(20)
        raise ValueError(
            f"{label} contains duplicate repository-month keys.\n"
            f"{sample.to_string(index=False)}"
        )


def normalize_boolean_series(
    series: pd.Series,
    column_name: str,
) -> pd.Series:
    mapping = {
        True: True,
        False: False,
        1: True,
        0: False,
        1.0: True,
        0.0: False,
        "True": True,
        "False": False,
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "1.0": True,
        "0.0": False,
    }
    normalized = series.map(mapping).astype("boolean")
    if normalized.isna().any():
        unresolved = (
            series.loc[normalized.isna()]
            .astype("string")
            .value_counts(dropna=False)
            .head(20)
            .to_dict()
        )
        raise ValueError(
            f"{column_name} contains unresolved Boolean values: {unresolved}"
        )
    return normalized


def add_check(
    checks: list[dict[str, object]],
    name: str,
    passed: bool,
    observed: object,
) -> None:
    checks.append(
        {"check": name, "passed": bool(passed), "observed": observed}
    )


def create_event_time_support(frame: pd.DataFrame) -> pd.DataFrame:
    support = (
        frame.groupby(["dataset_source", "time_to_event"], dropna=False)
        .agg(
            repo_months=("repo_name", "size"),
            repositories=("repo_name", "nunique"),
            event_positive_months=("has_function_change_event", "sum"),
            zero_event_months=("zero_function_event_month", "sum"),
            total_function_change_events=("function_change_events", "sum"),
            total_agc_function_change_events=(
                "agc_function_change_events",
                "sum",
            ),
            total_hwc_function_change_events=(
                "hwc_function_change_events",
                "sum",
            ),
            parse_exclusion_months=("has_parse_exclusion", "sum"),
        )
        .reset_index()
    )
    support["event_positive_month_ratio"] = (
        support["event_positive_months"] / support["repo_months"]
    )
    support["zero_event_month_ratio"] = (
        support["zero_event_months"] / support["repo_months"]
    )
    return support


def create_outcome_completeness(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for outcome in FULL_SAMPLE_OUTCOMES + CONDITIONAL_OUTCOMES:
        values = frame[outcome]
        rows.append(
            {
                "outcome": outcome,
                "total_repo_months": int(len(frame)),
                "nonmissing_repo_months": int(values.notna().sum()),
                "missing_repo_months": int(values.isna().sum()),
                "zero_values": int(
                    pd.to_numeric(values, errors="coerce").eq(0).sum()
                ),
                "analysis_scope": (
                    "full_sample"
                    if outcome in FULL_SAMPLE_OUTCOMES
                    else "positive_event_months_only"
                ),
            }
        )
    return pd.DataFrame(rows)


def create_covariate_completeness(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column in COVARIATE_COLUMNS + SHARED_TRANSFORMED_COVARIATE_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        rows.append(
            {
                "covariate": column,
                "repo_months": int(len(frame)),
                "nonmissing_repo_months": int(values.notna().sum()),
                "missing_repo_months": int(values.isna().sum()),
                "negative_values": int(values.lt(0).sum()),
                "zero_values": int(values.eq(0).sum()),
                "expected_nullable": bool(
                    column in EXPECTED_NULLABLE_COVARIATE_COLUMNS
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()

    require_file(args.input_table, "run-py-5d input table")
    require_file(args.covariate_panel, "Covariate panel")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    panel = normalize_keys(pd.read_csv(args.input_table))
    covariates = normalize_keys(pd.read_csv(args.covariate_panel))

    required_panel_columns = (
        KEY_COLUMNS
        + REQUIRED_EVENT_COLUMNS
        + REQUIRED_COUNT_COLUMNS
        + FULL_SAMPLE_OUTCOMES
        + CONDITIONAL_OUTCOMES
        + [
            "zero_function_event_month",
            "detection_complete",
            "has_parse_exclusion",
            "parse_exclusion_records",
            "treatment_group",
            "treatment_period",
        ]
    )
    require_columns(panel, required_panel_columns, "run-py-5d input table")
    require_columns(
        covariates,
        KEY_COLUMNS + COVARIATE_COLUMNS + LEAD_LAG_COLUMNS,
        "Covariate panel",
    )
    require_unique_keys(panel, "run-py-5d input table")
    require_unique_keys(covariates, "Covariate panel")

    original_rows = len(panel)
    original_keys = panel[KEY_COLUMNS].copy()
    original_outcomes = panel[
        KEY_COLUMNS + FULL_SAMPLE_OUTCOMES + CONDITIONAL_OUTCOMES
    ].copy()

    join_columns = KEY_COLUMNS + COVARIATE_COLUMNS + LEAD_LAG_COLUMNS
    optional_diagnostic_columns = [
        column
        for column in EXISTING_DIAGNOSTIC_READINESS_COLUMNS
        if column in covariates.columns
    ]
    covariate_minimal = covariates[
        join_columns + optional_diagnostic_columns
    ].copy()

    panel = panel.merge(
        covariate_minimal,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator="covariate_merge_status",
    )

    unmatched_covariates = panel["covariate_merge_status"].ne("both")
    if unmatched_covariates.any():
        sample = panel.loc[unmatched_covariates, KEY_COLUMNS].head(20)
        raise ValueError(
            "Covariate panel is missing repository-month keys.\n"
            f"{sample.to_string(index=False)}"
        )
    panel = panel.drop(columns=["covariate_merge_status"])

    for column in REQUIRED_COUNT_COLUMNS + [
        "has_function_change_event",
        "zero_function_event_month",
        "has_parse_exclusion",
        "parse_exclusion_records",
    ]:
        panel[column] = pd.to_numeric(panel[column], errors="raise")

    # 'event' is a YYYY-MM adoption-month string (e.g. "2024-09"), not a
    # numeric indicator. Coercing it with pd.to_numeric(errors="coerce")
    # silently turns every treatment repository-month's adoption month into
    # NaN, since none of them parse as numbers -- this previously passed
    # every QC check because no check inspected event's actual content, only
    # its presence and dtype. Only time_to_event and post_event are genuinely
    # numeric event variables and belong in this coercion loop.
    panel["event"] = (
        panel["event"]
        .astype("string")
        .str.strip()
        .replace(
            {
                "": pd.NA,
                "nan": pd.NA,
                "NaN": pd.NA,
                "None": pd.NA,
                "<NA>": pd.NA,
            }
        )
    )

    for column in ["time_to_event", "post_event"] + COVARIATE_COLUMNS + LEAD_LAG_COLUMNS:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")

    for outcome in FULL_SAMPLE_OUTCOMES + CONDITIONAL_OUTCOMES:
        panel[outcome] = pd.to_numeric(panel[outcome], errors="coerce")

    panel["detection_complete"] = normalize_boolean_series(
        panel["detection_complete"], "detection_complete"
    )

    for column in ["age", "contributors", "stars", "issues"]:
        negative_mask = panel[column].lt(0) & panel[column].notna()
        if negative_mask.any():
            sample = panel.loc[negative_mask, KEY_COLUMNS + [column]].head(20)
            raise ValueError(
                f"{column} contains negative values that cannot be log1p transformed.\n"
                f"{sample.to_string(index=False)}"
            )

    # ncloc_paper and ncloc_python_snapshot are not log1p-transformed here,
    # but a code-size measure can never legitimately be negative, so this is
    # checked independently of the log1p precondition above.
    for column in ["ncloc_paper", "ncloc_python_snapshot"]:
        negative_mask = panel[column].lt(0) & panel[column].notna()
        if negative_mask.any():
            sample = panel.loc[negative_mask, KEY_COLUMNS + [column]].head(20)
            raise ValueError(
                f"{column} contains negative values, which is not a valid "
                f"code-size measurement.\n{sample.to_string(index=False)}"
            )

    panel["log1p_age"] = np.log1p(panel["age"])
    panel["log1p_contributors"] = np.log1p(panel["contributors"])
    panel["log1p_stars"] = np.log1p(panel["stars"])
    panel["log1p_issues"] = np.log1p(panel["issues"])

    shared_covariates_nonmissing = (
        panel[SHARED_TRANSFORMED_COVARIATE_COLUMNS].notna().all(axis=1)
    )
    panel["analysis_ready_paper_ncloc"] = (
        shared_covariates_nonmissing & panel["ncloc_paper"].notna()
    ).astype("int8")
    panel["analysis_ready_python_snapshot_ncloc"] = (
        shared_covariates_nonmissing & panel["ncloc_python_snapshot"].notna()
    ).astype("int8")

    ratio_ready_base = (
        panel["function_change_events"].gt(0)
        & panel["agc_function_change_event_ratio"].notna()
    )
    panel["analysis_ready_ratio_paper_ncloc"] = (
        ratio_ready_base & panel["analysis_ready_paper_ncloc"].eq(1)
    ).astype("int8")
    panel["analysis_ready_ratio_python_snapshot_ncloc"] = (
        ratio_ready_base
        & panel["analysis_ready_python_snapshot_ncloc"].eq(1)
    ).astype("int8")

    panel["treat"] = (
        panel["dataset_source"]
        .map({"control": 0, "treatment": 1})
        .astype("Int64")
    )
    if panel["treat"].isna().any():
        unexpected = sorted(
            panel.loc[panel["treat"].isna(), "dataset_source"]
            .dropna()
            .unique()
            .tolist()
        )
        raise ValueError(f"Unexpected dataset_source values: {unexpected}")

    panel["unit_id"] = panel["repo_name"].astype("string")
    panel["calendar_time"] = panel["time"].astype("string")

    positive_event_mask = panel["function_change_events"].gt(0)
    zero_event_mask = panel["function_change_events"].eq(0)
    parse_clean_mask = panel["has_parse_exclusion"].eq(0)

    full_panel = panel.copy()
    ratio_panel = panel.loc[positive_event_mask].copy()
    parse_clean_full_panel = panel.loc[parse_clean_mask].copy()
    parse_clean_ratio_panel = panel.loc[
        positive_event_mask & parse_clean_mask
    ].copy()

    ratio_panel["ratio_sample"] = 1
    parse_clean_ratio_panel["ratio_sample"] = 1

    event_time_support = create_event_time_support(full_panel)
    outcome_completeness = create_outcome_completeness(full_panel)
    covariate_completeness = create_covariate_completeness(full_panel)

    sample_summary = pd.DataFrame(
        [
            {
                "sample": "full",
                "repo_months": int(len(full_panel)),
                "repositories": int(full_panel["repo_name"].nunique()),
                "control_repo_months": int(
                    full_panel["dataset_source"].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    full_panel["dataset_source"].eq("treatment").sum()
                ),
                "zero_event_months": int(zero_event_mask.sum()),
                "event_positive_months": int(positive_event_mask.sum()),
                "parse_exclusion_months": int(
                    full_panel["has_parse_exclusion"].sum()
                ),
            },
            {
                "sample": "ratio_positive_event",
                "repo_months": int(len(ratio_panel)),
                "repositories": int(ratio_panel["repo_name"].nunique()),
                "control_repo_months": int(
                    ratio_panel["dataset_source"].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    ratio_panel["dataset_source"].eq("treatment").sum()
                ),
                "zero_event_months": 0,
                "event_positive_months": int(len(ratio_panel)),
                "parse_exclusion_months": int(
                    ratio_panel["has_parse_exclusion"].sum()
                ),
            },
            {
                "sample": "parse_clean_full",
                "repo_months": int(len(parse_clean_full_panel)),
                "repositories": int(
                    parse_clean_full_panel["repo_name"].nunique()
                ),
                "control_repo_months": int(
                    parse_clean_full_panel["dataset_source"]
                    .eq("control")
                    .sum()
                ),
                "treatment_repo_months": int(
                    parse_clean_full_panel["dataset_source"]
                    .eq("treatment")
                    .sum()
                ),
                "zero_event_months": int(
                    parse_clean_full_panel["zero_function_event_month"].sum()
                ),
                "event_positive_months": int(
                    parse_clean_full_panel["has_function_change_event"].sum()
                ),
                "parse_exclusion_months": 0,
            },
            {
                "sample": "parse_clean_ratio_positive_event",
                "repo_months": int(len(parse_clean_ratio_panel)),
                "repositories": int(
                    parse_clean_ratio_panel["repo_name"].nunique()
                ),
                "control_repo_months": int(
                    parse_clean_ratio_panel["dataset_source"]
                    .eq("control")
                    .sum()
                ),
                "treatment_repo_months": int(
                    parse_clean_ratio_panel["dataset_source"]
                    .eq("treatment")
                    .sum()
                ),
                "zero_event_months": 0,
                "event_positive_months": int(len(parse_clean_ratio_panel)),
                "parse_exclusion_months": 0,
            },
        ]
    )

    specification_sample_summary = pd.DataFrame(
        [
            {
                "sample": sample_name,
                "paper_ncloc_analysis_ready_rows": int(
                    frame["analysis_ready_paper_ncloc"].eq(1).sum()
                ),
                "python_snapshot_ncloc_analysis_ready_rows": int(
                    frame["analysis_ready_python_snapshot_ncloc"].eq(1).sum()
                ),
                "paper_ncloc_ratio_analysis_ready_rows": int(
                    frame["analysis_ready_ratio_paper_ncloc"].eq(1).sum()
                ),
                "python_snapshot_ncloc_ratio_analysis_ready_rows": int(
                    frame["analysis_ready_ratio_python_snapshot_ncloc"]
                    .eq(1)
                    .sum()
                ),
            }
            for sample_name, frame in [
                ("full", full_panel),
                ("ratio_positive_event", ratio_panel),
                ("parse_clean_full", parse_clean_full_panel),
                (
                    "parse_clean_ratio_positive_event",
                    parse_clean_ratio_panel,
                ),
            ]
        ]
    )

    checks: list[dict[str, object]] = []
    add_check(checks, "covariate_join_row_count_unchanged", len(panel) == original_rows, len(panel))
    add_check(
        checks,
        "covariate_join_key_order_unchanged",
        panel[KEY_COLUMNS].reset_index(drop=True).equals(
            original_keys.reset_index(drop=True)
        ),
        int(len(panel)),
    )
    merged_outcomes = panel[
        KEY_COLUMNS + FULL_SAMPLE_OUTCOMES + CONDITIONAL_OUTCOMES
    ]
    add_check(
        checks,
        "covariate_join_outcomes_unchanged",
        merged_outcomes.reset_index(drop=True).equals(
            original_outcomes.reset_index(drop=True)
        ),
        int(len(panel)),
    )
    add_check(checks, "full_panel_row_count", len(full_panel) == args.expected_rows, len(full_panel))
    add_check(
        checks,
        "positive_event_panel_row_count",
        len(ratio_panel) == args.expected_positive_event_rows,
        len(ratio_panel),
    )
    add_check(
        checks,
        "zero_event_row_count",
        int(zero_event_mask.sum()) == args.expected_zero_event_rows,
        int(zero_event_mask.sum()),
    )
    add_check(
        checks,
        "control_row_count",
        int(full_panel["dataset_source"].eq("control").sum())
        == args.expected_control_rows,
        int(full_panel["dataset_source"].eq("control").sum()),
    )
    add_check(
        checks,
        "treatment_row_count",
        int(full_panel["dataset_source"].eq("treatment").sum())
        == args.expected_treatment_rows,
        int(full_panel["dataset_source"].eq("treatment").sum()),
    )
    add_check(
        checks,
        "parse_exclusion_month_count",
        int(full_panel["has_parse_exclusion"].sum())
        == args.expected_parse_exclusion_months,
        int(full_panel["has_parse_exclusion"].sum()),
    )
    add_check(
        checks,
        "event_count_partition",
        bool(
            (
                full_panel["agc_function_change_events"]
                + full_panel["hwc_function_change_events"]
                == full_panel["function_change_events"]
            ).all()
        ),
        int(len(full_panel)),
    )
    add_check(
        checks,
        "positive_event_ratio_nonmissing",
        bool(ratio_panel["agc_function_change_event_ratio"].notna().all()),
        int(ratio_panel["agc_function_change_event_ratio"].isna().sum()),
    )
    add_check(
        checks,
        "zero_event_ratio_missing",
        bool(
            full_panel.loc[
                zero_event_mask, "agc_function_change_event_ratio"
            ].isna().all()
        ),
        int(
            full_panel.loc[
                zero_event_mask, "agc_function_change_event_ratio"
            ].notna().sum()
        ),
    )
    add_check(
        checks,
        "ratio_bounds",
        bool(
            ratio_panel["agc_function_change_event_ratio"]
            .between(0, 1, inclusive="both")
            .all()
        ),
        int(
            (
                ~ratio_panel["agc_function_change_event_ratio"].between(
                    0, 1, inclusive="both"
                )
            ).sum()
        ),
    )
    add_check(
        checks,
        "detection_complete_all_true",
        bool(full_panel["detection_complete"].eq(True).all()),
        int(full_panel["detection_complete"].eq(False).sum()),
    )
    add_check(
        checks,
        "treat_matches_dataset_source",
        bool(
            (
                full_panel["treat"]
                == full_panel["dataset_source"].map(
                    {"control": 0, "treatment": 1}
                )
            ).all()
        ),
        int(
            (
                full_panel["treat"]
                != full_panel["dataset_source"].map(
                    {"control": 0, "treatment": 1}
                )
            ).sum()
        ),
    )
    # These three checks guard against the event-month string being
    # silently zeroed out by numeric coercion (the exact bug fixed in this
    # revision): every treatment repository-month must carry its adoption
    # month, every control repository-month must have none, and each
    # treatment repository must report exactly one distinct adoption month
    # across all of its repository-months.
    treatment_event_missing_rows = int(
        full_panel.loc[
            full_panel["dataset_source"].eq("treatment"), "event"
        ]
        .isna()
        .sum()
    )
    add_check(
        checks,
        "treatment_event_month_nonmissing",
        treatment_event_missing_rows == 0,
        treatment_event_missing_rows,
    )
    control_event_nonmissing_rows = int(
        full_panel.loc[full_panel["dataset_source"].eq("control"), "event"]
        .notna()
        .sum()
    )
    add_check(
        checks,
        "control_event_month_missing",
        control_event_nonmissing_rows == 0,
        control_event_nonmissing_rows,
    )
    treatment_event_counts = (
        full_panel.loc[
            full_panel["dataset_source"].eq("treatment"),
            ["repo_name", "event"],
        ]
        .groupby("repo_name")["event"]
        .nunique(dropna=True)
    )
    add_check(
        checks,
        "one_event_month_per_treatment_repository",
        bool(treatment_event_counts.eq(1).all()),
        int(treatment_event_counts.ne(1).sum()),
    )
    add_check(
        checks,
        "full_sample_outcomes_nonmissing",
        bool(full_panel[FULL_SAMPLE_OUTCOMES].notna().all().all()),
        int(full_panel[FULL_SAMPLE_OUTCOMES].isna().sum().sum()),
    )
    add_check(
        checks,
        "raw_covariates_missing_counts_informational",
        True,
        {
            column: int(full_panel[column].isna().sum())
            for column in COVARIATE_COLUMNS
        },
    )
    # age/stars/issues have 15 known unmatched repository-months, while contributors is complete with 0 missing
    # repository-months (unmatched against the frozen paper panel), and
    # ncloc_paper is expected to have exactly 37 missing values -- both
    # documented in run-py-3b. These counts are known, genuine missingness,
    # not a pipeline defect, so this check confirms the counts match rather
    # than requiring zero missingness.
    add_check(
        checks,
        "known_covariate_missing_counts_match_run_py_3b",
        bool(
            int(full_panel["age"].isna().sum()) == 15
            and int(full_panel["contributors"].isna().sum()) == 0
            and int(full_panel["stars"].isna().sum()) == 15
            and int(full_panel["issues"].isna().sum()) == 15
            and int(full_panel["ncloc_paper"].isna().sum()) == 37
        ),
        {
            "age_missing": int(full_panel["age"].isna().sum()),
            "contributors_missing": int(
                full_panel["contributors"].isna().sum()
            ),
            "stars_missing": int(full_panel["stars"].isna().sum()),
            "issues_missing": int(full_panel["issues"].isna().sum()),
            "ncloc_paper_missing": int(full_panel["ncloc_paper"].isna().sum()),
        },
    )
    add_check(
        checks,
        "transformed_covariates_missing_matches_raw",
        bool(
            full_panel["log1p_age"].isna().sum()
            == full_panel["age"].isna().sum()
            and full_panel["log1p_contributors"].isna().sum()
            == full_panel["contributors"].isna().sum()
            and full_panel["log1p_stars"].isna().sum()
            == full_panel["stars"].isna().sum()
            and full_panel["log1p_issues"].isna().sum()
            == full_panel["issues"].isna().sum()
        ),
        int(full_panel[SHARED_TRANSFORMED_COVARIATE_COLUMNS].isna().sum().sum()),
    )
    add_check(
        checks,
        "lead_lag_columns_missing_count_informational",
        True,
        int(full_panel[LEAD_LAG_COLUMNS].isna().sum().sum()),
    )
    add_check(
        checks,
        "readiness_flags_never_exceed_nonmissing_covariates",
        bool(
            int(
                full_panel["analysis_ready_paper_ncloc"].eq(1).sum()
            )
            <= int(full_panel["ncloc_paper"].notna().sum())
            and int(
                full_panel["analysis_ready_python_snapshot_ncloc"].eq(1).sum()
            )
            <= int(full_panel["ncloc_python_snapshot"].notna().sum())
        ),
        {
            "paper_ncloc_ready": int(
                full_panel["analysis_ready_paper_ncloc"].eq(1).sum()
            ),
            "paper_ncloc_nonmissing": int(
                full_panel["ncloc_paper"].notna().sum()
            ),
            "snapshot_ncloc_ready": int(
                full_panel["analysis_ready_python_snapshot_ncloc"].eq(1).sum()
            ),
            "snapshot_ncloc_nonmissing": int(
                full_panel["ncloc_python_snapshot"].notna().sum()
            ),
        },
    )
    add_check(
        checks,
        "ratio_readiness_flags_subset_of_full_readiness",
        bool(
            (
                full_panel["analysis_ready_ratio_paper_ncloc"]
                <= full_panel["analysis_ready_paper_ncloc"]
            ).all()
            and (
                full_panel["analysis_ready_ratio_python_snapshot_ncloc"]
                <= full_panel["analysis_ready_python_snapshot_ncloc"]
            ).all()
        ),
        int(
            (
                full_panel["analysis_ready_ratio_paper_ncloc"]
                > full_panel["analysis_ready_paper_ncloc"]
            ).sum()
            + (
                full_panel["analysis_ready_ratio_python_snapshot_ncloc"]
                > full_panel["analysis_ready_python_snapshot_ncloc"]
            ).sum()
        ),
    )
    # Informational only: the upstream (run-py-4a) changed-block readiness
    # flags were computed for a different outcome and are not expected to
    # match the commit-function readiness flags row-for-row. This is a
    # diagnostic comparison, not a correctness gate.
    for existing_column, new_column in [
        (
            "analysis_ready_agc_changed_block_paper_ncloc",
            "analysis_ready_paper_ncloc",
        ),
        (
            "analysis_ready_agc_changed_block_python_snapshot_ncloc",
            "analysis_ready_python_snapshot_ncloc",
        ),
    ]:
        if existing_column in full_panel.columns:
            existing_values = pd.to_numeric(
                full_panel[existing_column], errors="coerce"
            )
            new_values = full_panel[new_column]
            add_check(
                checks,
                f"diagnostic_{existing_column}_vs_{new_column}_agreement",
                True,
                {
                    "agree": int((existing_values == new_values).sum()),
                    "disagree": int((existing_values != new_values).sum()),
                    "existing_missing": int(existing_values.isna().sum()),
                },
            )
    add_check(
        checks,
        "parse_clean_full_has_no_exclusions",
        int(parse_clean_full_panel["has_parse_exclusion"].sum()) == 0,
        int(parse_clean_full_panel["has_parse_exclusion"].sum()),
    )
    add_check(
        checks,
        "parse_clean_ratio_has_no_exclusions",
        int(parse_clean_ratio_panel["has_parse_exclusion"].sum()) == 0,
        int(parse_clean_ratio_panel["has_parse_exclusion"].sum()),
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    full_output = args.output_dir / "panel_event_monthly_agc_commit_function.csv"
    ratio_output = (
        args.output_dir
        / "panel_event_monthly_agc_commit_function_ratio_positive.csv"
    )
    parse_clean_full_output = (
        args.output_dir
        / "panel_event_monthly_agc_commit_function_parse_clean.csv"
    )
    parse_clean_ratio_output = (
        args.output_dir
        / "panel_event_monthly_agc_commit_function_ratio_positive_parse_clean.csv"
    )
    support_output = args.output_dir / "agc_commit_function_event_time_support.csv"
    outcome_completeness_output = (
        args.output_dir / "agc_commit_function_outcome_completeness.csv"
    )
    covariate_completeness_output = (
        args.output_dir / "agc_commit_function_covariate_completeness.csv"
    )
    sample_summary_output = (
        args.output_dir / "agc_commit_function_sample_summary.csv"
    )
    specification_sample_summary_output = (
        args.output_dir
        / "agc_commit_function_specification_sample_summary.csv"
    )
    checks_output = args.output_dir / "agc_commit_function_did_input_checks.csv"
    summary_output = args.output_dir / "agc_commit_function_did_input_summary.json"

    full_panel.to_csv(full_output, index=False)
    ratio_panel.to_csv(ratio_output, index=False)
    parse_clean_full_panel.to_csv(parse_clean_full_output, index=False)
    parse_clean_ratio_panel.to_csv(parse_clean_ratio_output, index=False)
    event_time_support.to_csv(support_output, index=False)
    outcome_completeness.to_csv(outcome_completeness_output, index=False)
    covariate_completeness.to_csv(covariate_completeness_output, index=False)
    sample_summary.to_csv(sample_summary_output, index=False)
    specification_sample_summary.to_csv(
        specification_sample_summary_output, index=False
    )
    checks_frame.to_csv(checks_output, index=False)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "input_table": str(args.input_table),
        "covariate_panel": str(args.covariate_panel),
        "full_panel_rows": int(len(full_panel)),
        "ratio_panel_rows": int(len(ratio_panel)),
        "zero_event_rows": int(zero_event_mask.sum()),
        "control_rows": int(full_panel["dataset_source"].eq("control").sum()),
        "treatment_rows": int(
            full_panel["dataset_source"].eq("treatment").sum()
        ),
        "parse_exclusion_months": int(
            full_panel["has_parse_exclusion"].sum()
        ),
        # Renamed from the previous, misleading "primary_covariates" key.
        # ncloc_paper and ncloc_python_snapshot are competing specifications
        # and must never both appear in the same regression formula -- see
        # module docstring.
        "shared_covariates": SHARED_COVARIATE_COLUMNS,
        "shared_transformed_covariates": SHARED_TRANSFORMED_COVARIATE_COLUMNS,
        "paper_ncloc_specification": PAPER_NCLOC_SPECIFICATION_COLUMNS,
        "python_snapshot_ncloc_specification": (
            PYTHON_SNAPSHOT_NCLOC_SPECIFICATION_COLUMNS
        ),
        "readiness_flag_columns": READINESS_FLAG_COLUMNS,
        "lead_lag_columns": LEAD_LAG_COLUMNS,
        "full_sample_outcomes": FULL_SAMPLE_OUTCOMES,
        "conditional_outcomes": CONDITIONAL_OUTCOMES,
        "outputs": {
            "full_panel": str(full_output),
            "ratio_panel": str(ratio_output),
            "parse_clean_full_panel": str(parse_clean_full_output),
            "parse_clean_ratio_panel": str(parse_clean_ratio_output),
            "event_time_support": str(support_output),
            "outcome_completeness": str(outcome_completeness_output),
            "covariate_completeness": str(covariate_completeness_output),
            "sample_summary": str(sample_summary_output),
            "specification_sample_summary": str(
                specification_sample_summary_output
            ),
            "checks": str(checks_output),
        },
    }
    summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("=" * 76)
    print("Prepare covariate-complete commit-function AGC Borusyak DiD inputs")
    print("=" * 76)
    print(f"Status:                    {summary['status']}")
    print(f"Full panel rows:           {summary['full_panel_rows']}")
    print(f"Ratio panel rows:          {summary['ratio_panel_rows']}")
    print(f"Zero-event rows:           {summary['zero_event_rows']}")
    print(f"Control rows:              {summary['control_rows']}")
    print(f"Treatment rows:            {summary['treatment_rows']}")
    print(f"Parse-exclusion months:    {summary['parse_exclusion_months']}")
    print(f"Covariate panel:           {args.covariate_panel}")
    print(f"Full panel:                {full_output}")
    print(f"Conditional ratio panel:   {ratio_output}")
    print(f"QC checks:                 {checks_output}")
    print(f"Summary:                   {summary_output}")
    print("=" * 76)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise