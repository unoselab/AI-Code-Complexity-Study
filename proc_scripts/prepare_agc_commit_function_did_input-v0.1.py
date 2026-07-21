#!/usr/bin/env python3
"""
Prepare Borusyak DiD inputs for Python commit-function AGC outcomes.

Inputs
------
1. Complete repository-month table produced by run-py-5d.
   This table must preserve all 1,633 repository-months, including
   zero-function-event months.

Outputs
-------
1. Full DiD panel for zero-inclusive occurrence and count outcomes.
2. Conditional-ratio panel containing only months with positive event counts.
3. Parse-clean robustness panels.
4. Event-time support and outcome-completeness tables.
5. QC checks and a JSON summary.

Outcome interpretation
----------------------
Zero-inclusive outcomes use all repository-months:
- has_function_change_event
- log1p_function_change_events
- log1p_agc_function_change_events
- log1p_hwc_function_change_events

The AGC share is conditional:
- agc_function_change_event_ratio

The ratio is undefined when function_change_events == 0 and therefore remains
missing in the full panel. A separate positive-event panel is created for
conditional-composition analysis.

Usage
-----
python proc_scripts/prepare_agc_commit_function_did_input.py --input-table repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv --output-dir repo_python/run-py-5e/strict --expected-rows 1633 --expected-positive-event-rows 1289 --expected-zero-event-rows 344 --expected-control-rows 780 --expected-treatment-rows 853 --expected-parse-exclusion-months 97

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


KEY_COLUMNS = ["dataset_source", "repo_name", "time"]

FULL_SAMPLE_OUTCOMES = [
    "has_function_change_event",
    "log1p_function_change_events",
    "log1p_agc_function_change_events",
    "log1p_hwc_function_change_events",
]

CONDITIONAL_OUTCOMES = [
    "agc_function_change_event_ratio",
]

REQUIRED_EVENT_COLUMNS = [
    "time_to_event",
    "event",
    "post_event",
]

REQUIRED_COUNT_COLUMNS = [
    "function_change_events",
    "agc_function_change_events",
    "hwc_function_change_events",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare zero-inclusive and conditional-composition Borusyak "
            "DiD input panels for commit-function AGC outcomes."
        )
    )
    parser.add_argument(
        "--input-table",
        required=True,
        type=Path,
        help=(
            "Complete run-py-5d repository-month analysis table."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for run-py-5e outputs.",
    )
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=1633,
        help="Expected rows in the complete repository-month panel.",
    )
    parser.add_argument(
        "--expected-positive-event-rows",
        type=int,
        default=1289,
        help=(
            "Expected rows with function_change_events greater than zero."
        ),
    )
    parser.add_argument(
        "--expected-zero-event-rows",
        type=int,
        default=344,
        help="Expected zero-function-event repository-months.",
    )
    parser.add_argument(
        "--expected-control-rows",
        type=int,
        default=780,
        help="Expected static control repository-month rows.",
    )
    parser.add_argument(
        "--expected-treatment-rows",
        type=int,
        default=853,
        help="Expected static treatment repository-month rows.",
    )
    parser.add_argument(
        "--expected-parse-exclusion-months",
        type=int,
        default=97,
        help="Expected parse-exclusion-affected repository-months.",
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
        {
            "check": name,
            "passed": bool(passed),
            "observed": observed,
        }
    )


def create_event_time_support(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    support = (
        frame.groupby(
            ["dataset_source", "time_to_event"],
            dropna=False,
        )
        .agg(
            repo_months=("repo_name", "size"),
            repositories=("repo_name", "nunique"),
            event_positive_months=(
                "has_function_change_event",
                "sum",
            ),
            zero_event_months=(
                "zero_function_event_month",
                "sum",
            ),
            total_function_change_events=(
                "function_change_events",
                "sum",
            ),
            total_agc_function_change_events=(
                "agc_function_change_events",
                "sum",
            ),
            total_hwc_function_change_events=(
                "hwc_function_change_events",
                "sum",
            ),
            parse_exclusion_months=(
                "has_parse_exclusion",
                "sum",
            ),
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


def create_outcome_completeness(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

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


def main() -> int:
    args = parse_args()

    require_file(args.input_table, "run-py-5d input table")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    panel = normalize_keys(pd.read_csv(args.input_table))

    required_columns = (
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

    require_columns(
        panel,
        required_columns,
        "run-py-5d input table",
    )
    require_unique_keys(panel, "run-py-5d input table")

    for column in REQUIRED_COUNT_COLUMNS + [
        "has_function_change_event",
        "zero_function_event_month",
        "has_parse_exclusion",
        "parse_exclusion_records",
    ]:
        panel[column] = pd.to_numeric(
            panel[column],
            errors="raise",
        )

    for column in [
        "time_to_event",
        "event",
        "post_event",
    ]:
        panel[column] = pd.to_numeric(
            panel[column],
            errors="coerce",
        )

    for outcome in FULL_SAMPLE_OUTCOMES + CONDITIONAL_OUTCOMES:
        panel[outcome] = pd.to_numeric(
            panel[outcome],
            errors="coerce",
        )

    panel["detection_complete"] = normalize_boolean_series(
        panel["detection_complete"],
        "detection_complete",
    )

    panel["treat"] = (
        panel["dataset_source"]
        .map(
            {
                "control": 0,
                "treatment": 1,
            }
        )
        .astype("Int64")
    )

    if panel["treat"].isna().any():
        unexpected = sorted(
            panel.loc[
                panel["treat"].isna(),
                "dataset_source",
            ]
            .dropna()
            .unique()
            .tolist()
        )
        raise ValueError(
            f"Unexpected dataset_source values: {unexpected}"
        )

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

    sample_summary = pd.DataFrame(
        [
            {
                "sample": "full",
                "repo_months": int(len(full_panel)),
                "repositories": int(
                    full_panel["repo_name"].nunique()
                ),
                "control_repo_months": int(
                    full_panel["dataset_source"].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    full_panel["dataset_source"].eq("treatment").sum()
                ),
                "zero_event_months": int(
                    zero_event_mask.sum()
                ),
                "event_positive_months": int(
                    positive_event_mask.sum()
                ),
                "parse_exclusion_months": int(
                    full_panel["has_parse_exclusion"].sum()
                ),
            },
            {
                "sample": "ratio_positive_event",
                "repo_months": int(len(ratio_panel)),
                "repositories": int(
                    ratio_panel["repo_name"].nunique()
                ),
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
                    parse_clean_full_panel[
                        "dataset_source"
                    ].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    parse_clean_full_panel[
                        "dataset_source"
                    ].eq("treatment").sum()
                ),
                "zero_event_months": int(
                    parse_clean_full_panel[
                        "zero_function_event_month"
                    ].sum()
                ),
                "event_positive_months": int(
                    parse_clean_full_panel[
                        "has_function_change_event"
                    ].sum()
                ),
                "parse_exclusion_months": int(
                    parse_clean_full_panel[
                        "has_parse_exclusion"
                    ].sum()
                ),
            },
            {
                "sample": "parse_clean_ratio_positive_event",
                "repo_months": int(len(parse_clean_ratio_panel)),
                "repositories": int(
                    parse_clean_ratio_panel[
                        "repo_name"
                    ].nunique()
                ),
                "control_repo_months": int(
                    parse_clean_ratio_panel[
                        "dataset_source"
                    ].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    parse_clean_ratio_panel[
                        "dataset_source"
                    ].eq("treatment").sum()
                ),
                "zero_event_months": 0,
                "event_positive_months": int(
                    len(parse_clean_ratio_panel)
                ),
                "parse_exclusion_months": int(
                    parse_clean_ratio_panel[
                        "has_parse_exclusion"
                    ].sum()
                ),
            },
        ]
    )

    checks: list[dict[str, object]] = []

    add_check(
        checks,
        "full_panel_row_count",
        len(full_panel) == args.expected_rows,
        len(full_panel),
    )
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
        int(
            (
                full_panel["agc_function_change_events"]
                + full_panel["hwc_function_change_events"]
                == full_panel["function_change_events"]
            ).sum()
        )
        == len(full_panel),
        int(len(full_panel)),
    )
    add_check(
        checks,
        "positive_event_ratio_nonmissing",
        bool(
            ratio_panel[
                "agc_function_change_event_ratio"
            ].notna().all()
        ),
        int(
            ratio_panel[
                "agc_function_change_event_ratio"
            ].isna().sum()
        ),
    )
    add_check(
        checks,
        "zero_event_ratio_missing",
        bool(
            full_panel.loc[
                zero_event_mask,
                "agc_function_change_event_ratio",
            ].isna().all()
        ),
        int(
            full_panel.loc[
                zero_event_mask,
                "agc_function_change_event_ratio",
            ].notna().sum()
        ),
    )
    add_check(
        checks,
        "ratio_bounds",
        bool(
            ratio_panel[
                "agc_function_change_event_ratio"
            ].between(0, 1, inclusive="both").all()
        ),
        int(
            (
                ~ratio_panel[
                    "agc_function_change_event_ratio"
                ].between(0, 1, inclusive="both")
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
                    {
                        "control": 0,
                        "treatment": 1,
                    }
                )
            ).all()
        ),
        int(
            (
                full_panel["treat"]
                != full_panel["dataset_source"].map(
                    {
                        "control": 0,
                        "treatment": 1,
                    }
                )
            ).sum()
        ),
    )
    add_check(
        checks,
        "full_sample_outcomes_nonmissing",
        bool(
            full_panel[FULL_SAMPLE_OUTCOMES]
            .notna()
            .all()
            .all()
        ),
        int(
            full_panel[FULL_SAMPLE_OUTCOMES]
            .isna()
            .sum()
            .sum()
        ),
    )
    add_check(
        checks,
        "parse_clean_full_has_no_exclusions",
        int(
            parse_clean_full_panel[
                "has_parse_exclusion"
            ].sum()
        )
        == 0,
        int(
            parse_clean_full_panel[
                "has_parse_exclusion"
            ].sum()
        ),
    )
    add_check(
        checks,
        "parse_clean_ratio_has_no_exclusions",
        int(
            parse_clean_ratio_panel[
                "has_parse_exclusion"
            ].sum()
        )
        == 0,
        int(
            parse_clean_ratio_panel[
                "has_parse_exclusion"
            ].sum()
        ),
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    full_output = (
        args.output_dir
        / "panel_event_monthly_agc_commit_function.csv"
    )
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
        / (
            "panel_event_monthly_agc_commit_function_"
            "ratio_positive_parse_clean.csv"
        )
    )
    support_output = (
        args.output_dir
        / "agc_commit_function_event_time_support.csv"
    )
    completeness_output = (
        args.output_dir
        / "agc_commit_function_outcome_completeness.csv"
    )
    sample_summary_output = (
        args.output_dir
        / "agc_commit_function_sample_summary.csv"
    )
    checks_output = (
        args.output_dir
        / "agc_commit_function_did_input_checks.csv"
    )
    summary_output = (
        args.output_dir
        / "agc_commit_function_did_input_summary.json"
    )

    full_panel.to_csv(full_output, index=False)
    ratio_panel.to_csv(ratio_output, index=False)
    parse_clean_full_panel.to_csv(
        parse_clean_full_output,
        index=False,
    )
    parse_clean_ratio_panel.to_csv(
        parse_clean_ratio_output,
        index=False,
    )
    event_time_support.to_csv(support_output, index=False)
    outcome_completeness.to_csv(
        completeness_output,
        index=False,
    )
    sample_summary.to_csv(
        sample_summary_output,
        index=False,
    )
    checks_frame.to_csv(checks_output, index=False)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "input_table": str(args.input_table),
        "full_panel_rows": int(len(full_panel)),
        "ratio_panel_rows": int(len(ratio_panel)),
        "zero_event_rows": int(zero_event_mask.sum()),
        "control_rows": int(
            full_panel["dataset_source"].eq("control").sum()
        ),
        "treatment_rows": int(
            full_panel["dataset_source"].eq("treatment").sum()
        ),
        "parse_exclusion_months": int(
            full_panel["has_parse_exclusion"].sum()
        ),
        "full_sample_outcomes": FULL_SAMPLE_OUTCOMES,
        "conditional_outcomes": CONDITIONAL_OUTCOMES,
        "outputs": {
            "full_panel": str(full_output),
            "ratio_panel": str(ratio_output),
            "parse_clean_full_panel": str(
                parse_clean_full_output
            ),
            "parse_clean_ratio_panel": str(
                parse_clean_ratio_output
            ),
            "event_time_support": str(support_output),
            "outcome_completeness": str(
                completeness_output
            ),
            "sample_summary": str(sample_summary_output),
            "checks": str(checks_output),
        },
    }

    summary_output.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("=" * 76)
    print("Prepare commit-function AGC Borusyak DiD inputs")
    print("=" * 76)
    print(f"Status:                    {summary['status']}")
    print(f"Full panel rows:           {summary['full_panel_rows']}")
    print(f"Ratio panel rows:          {summary['ratio_panel_rows']}")
    print(f"Zero-event rows:           {summary['zero_event_rows']}")
    print(f"Control rows:              {summary['control_rows']}")
    print(f"Treatment rows:            {summary['treatment_rows']}")
    print(
        "Parse-exclusion months:  "
        f"{summary['parse_exclusion_months']}"
    )
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