#!/usr/bin/env python3
"""
Analyze zero-function-event repository-months for the commit-function AGC study.

Inputs
------
1. Extraction-stage repository-month function-event counts.
   This table must preserve all repository-months, including zero-event months.

2. Detector repository-month summary.
   This table contains only repository-months with at least one scored event.

3. Matched panel containing treatment and event-time variables.

4. Optional parse-exclusion repository-month table.

Outputs
-------
1. A complete 1,633-row repository-month analysis table.
2. Zero-event summaries by dataset source.
3. Zero-event summaries by treatment period.
4. Zero-event summaries by event time.
5. Parse-exclusion overlap summary.
6. QC checks and a JSON summary.

Usage
-----
python proc_scripts/analyze_agc_zero_event_months.py \
  --source-counts repo_python/run-py-5a-py312/strict/repo_month_function_event_counts.csv \
  --detector-summary ../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/repo_month_function_event_summary_all.csv \
  --panel repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv \
  --parse-exclusions-by-repo-month repo_python/run-py-5b-py312/strict/agc_commit_function_parse_exclusions_by_repo_month.csv \
  --output-dir repo_python/run-py-5d/strict \
  --expected-panel-rows 1633 \
  --expected-detector-rows 1289 \
  --expected-zero-event-months 344

Important interpretation
------------------------
A zero-event repository-month has no structurally added or modified named
function event. Its AGC share is undefined because the denominator is zero.
Count outcomes remain valid with zero values, but the ratio outcome must remain
missing for these months.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


KEY_COLUMNS = ["dataset_source", "repo_name", "time"]

COUNT_COLUMNS = [
    "function_change_events",
    "agc_function_change_events",
    "hwc_function_change_events",
    "added_function_events",
    "modified_function_events",
    "added_agc_function_events",
    "added_hwc_function_events",
    "modified_agc_function_events",
    "modified_hwc_function_events",
]

DETECTOR_COUNT_COLUMNS = [
    "function_change_events_manifest",
    "function_change_events_scored",
    "function_change_events_failed",
    "agc_function_change_events",
    "hwc_function_change_events",
    "added_agc_function_events",
    "added_hwc_function_events",
    "modified_agc_function_events",
    "modified_hwc_function_events",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze zero-function-event repository-months and prepare a "
            "complete repository-month table for subsequent DiD analysis."
        )
    )
    parser.add_argument(
        "--source-counts",
        required=True,
        type=Path,
        help="Extraction-stage repo_month_function_event_counts.csv.",
    )
    parser.add_argument(
        "--detector-summary",
        required=True,
        type=Path,
        help="Detector repo_month_function_event_summary_all.csv.",
    )
    parser.add_argument(
        "--panel",
        required=True,
        type=Path,
        help="Matched panel containing treatment and event-time columns.",
    )
    parser.add_argument(
        "--parse-exclusions-by-repo-month",
        type=Path,
        default=None,
        help=(
            "Optional Python 3.12 parse-exclusion summary by repository-month."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for analysis outputs.",
    )
    parser.add_argument(
        "--expected-panel-rows",
        type=int,
        default=1633,
        help="Expected number of complete repository-month rows.",
    )
    parser.add_argument(
        "--expected-detector-rows",
        type=int,
        default=1289,
        help="Expected number of event-positive detector summary rows.",
    )
    parser.add_argument(
        "--expected-zero-event-months",
        type=int,
        default=344,
        help="Expected number of zero-function-event repository-months.",
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

    for column in ["dataset_source", "repo_name", "time"]:
        if column in result.columns:
            result[column] = result[column].astype("string").str.strip()

    return result


def assert_unique_keys(frame: pd.DataFrame, label: str) -> None:
    duplicates = frame.duplicated(KEY_COLUMNS, keep=False)
    if duplicates.any():
        sample = frame.loc[duplicates, KEY_COLUMNS].head(20)
        raise ValueError(
            f"{label} contains duplicate repository-month keys.\n"
            f"{sample.to_string(index=False)}"
        )


def infer_event_time_column(panel: pd.DataFrame) -> str:
    candidates = ["time_to_event", "event_time", "relative_month"]

    for column in candidates:
        if column in panel.columns:
            return column

    raise ValueError(
        "Could not identify an event-time column. "
        f"Tried: {candidates}. Available columns: {list(panel.columns)}"
    )


def summarize_binary(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    grouped = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            repo_months=("repo_name", "size"),
            zero_event_months=("zero_function_event_month", "sum"),
            event_positive_months=("has_function_change_event", "sum"),
            total_function_change_events=("function_change_events", "sum"),
            total_agc_function_change_events=(
                "agc_function_change_events",
                "sum",
            ),
            total_hwc_function_change_events=(
                "hwc_function_change_events",
                "sum",
            ),
        )
        .reset_index()
    )

    grouped["zero_event_month_ratio"] = (
        grouped["zero_event_months"] / grouped["repo_months"]
    )
    grouped["event_positive_month_ratio"] = (
        grouped["event_positive_months"] / grouped["repo_months"]
    )

    return grouped


def resolve_parse_exclusion_count_column(
    frame: pd.DataFrame,
) -> str | None:
    preferred = [
        "parse_exclusion_records",
        "exclusion_records",
        "error_records",
        "parse_errors",
        "records",
    ]

    for column in preferred:
        if column in frame.columns:
            return column

    numeric_candidates = [
        column
        for column in frame.columns
        if column not in KEY_COLUMNS
        and pd.api.types.is_numeric_dtype(frame[column])
        and (
            "record" in column.lower()
            or "error" in column.lower()
            or "exclusion" in column.lower()
        )
    ]

    if len(numeric_candidates) == 1:
        return numeric_candidates[0]

    return None


def main() -> int:
    args = parse_args()

    require_file(args.source_counts, "Source count table")
    require_file(args.detector_summary, "Detector summary")
    require_file(args.panel, "Matched panel")

    if args.parse_exclusions_by_repo_month is not None:
        require_file(
            args.parse_exclusions_by_repo_month,
            "Parse-exclusion repository-month table",
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    source = normalize_keys(pd.read_csv(args.source_counts))
    detector = normalize_keys(pd.read_csv(args.detector_summary))
    panel = normalize_keys(pd.read_csv(args.panel))

    require_columns(
        source,
        KEY_COLUMNS
        + [
            "function_change_events",
            "added_function_events",
            "modified_function_events",
        ],
        "Source count table",
    )
    require_columns(
        detector,
        KEY_COLUMNS
        + [
            "function_change_events_scored",
            "function_change_events_failed",
            "agc_function_change_events",
            "hwc_function_change_events",
            "agc_function_change_event_ratio",
            "detection_complete",
        ],
        "Detector summary",
    )
    require_columns(panel, KEY_COLUMNS, "Matched panel")

    assert_unique_keys(source, "Source count table")
    assert_unique_keys(detector, "Detector summary")
    assert_unique_keys(panel, "Matched panel")

    event_time_column = infer_event_time_column(panel)

    panel_columns = KEY_COLUMNS + [event_time_column]

    # is_treatment (or its aliases) is no longer required: static cohort
    # membership is derived from dataset_source, not from this dynamic
    # post-adoption indicator. Keep it in the output only if present, purely
    # as diagnostic context, so the script still runs against panels that
    # omit it.
    for optional_column in [
        "is_treatment",
        "treat",
        "treatment",
        "post_event",
        "event",
        "cursor",
    ]:
        if optional_column in panel.columns:
            panel_columns.append(optional_column)

    panel_minimal = panel[panel_columns].copy()

    complete = source.merge(
        panel_minimal,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator="panel_merge_status",
    )

    if not complete["panel_merge_status"].eq("both").all():
        unmatched = complete.loc[
            complete["panel_merge_status"] != "both",
            KEY_COLUMNS,
        ]
        raise ValueError(
            "Some source repository-months were not found in the panel.\n"
            f"{unmatched.head(20).to_string(index=False)}"
        )

    complete = complete.drop(columns=["panel_merge_status"])

    detector_columns = [
        column
        for column in detector.columns
        if column not in {
            "added_function_events",
            "modified_function_events",
        }
    ]

    complete = complete.merge(
        detector[detector_columns],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator="detector_merge_status",
    )

    complete["has_function_change_event"] = (
        pd.to_numeric(
            complete["function_change_events"],
            errors="raise",
        )
        .gt(0)
        .astype("int8")
    )
    complete["zero_function_event_month"] = (
        1 - complete["has_function_change_event"]
    ).astype("int8")

    event_positive = complete["has_function_change_event"].eq(1)
    zero_event = complete["zero_function_event_month"].eq(1)

    missing_positive = (
        event_positive
        & complete["detector_merge_status"].ne("both")
    )
    if missing_positive.any():
        sample = complete.loc[missing_positive, KEY_COLUMNS].head(20)
        raise ValueError(
            "Detector summary is missing event-positive repository-months.\n"
            f"{sample.to_string(index=False)}"
        )

    unexpected_zero_match = (
        zero_event
        & complete["detector_merge_status"].eq("both")
    )
    if unexpected_zero_match.any():
        sample = complete.loc[
            unexpected_zero_match,
            KEY_COLUMNS,
        ].head(20)
        raise ValueError(
            "Detector summary unexpectedly contains zero-event months.\n"
            f"{sample.to_string(index=False)}"
        )

    for column in DETECTOR_COUNT_COLUMNS:
        if column in complete.columns:
            complete[column] = pd.to_numeric(
                complete[column],
                errors="coerce",
            )
            complete.loc[zero_event, column] = 0
            complete[column] = complete[column].fillna(0)

    complete.loc[
        zero_event,
        "agc_function_change_event_ratio",
    ] = pd.NA

    # Normalize detection_complete to a nullable boolean dtype before
    # assigning True to the zero-event rows. Without this, the column can
    # arrive from the detector merge as float64 (e.g. 1.0) and mixing in a
    # Python bool True produces a pandas FutureWarning during assignment
    # and, worse, an object column that round-trips through CSV as mixed
    # "1.0"/"True" string literals -- a real downstream correctness bug,
    # not just a cosmetic warning.
    complete["detection_complete"] = (
        complete["detection_complete"]
        .map(
            {
                True: True,
                False: False,
                1: True,
                0: False,
                1.0: True,
                0.0: False,
                "True": True,
                "False": False,
                "1": True,
                "0": False,
                "1.0": True,
                "0.0": False,
            }
        )
        .astype("boolean")
    )

    complete.loc[
        zero_event,
        "detection_complete",
    ] = True

    if complete["detection_complete"].isna().any():
        raise ValueError(
            "detection_complete contains unresolved missing values."
        )

    complete["agc_function_change_event_ratio"] = pd.to_numeric(
        complete["agc_function_change_event_ratio"],
        errors="coerce",
    )

    # Use dataset_source as the static treatment/control cohort membership.
    # The panel's is_treatment column (formerly resolved via the now-removed
    # infer_treatment_column()) is a dynamic post-adoption indicator in this
    # project's run-py-4a / run-py-3b panel lineage, not static group
    # membership. Using it here previously misclassified 421 treatment
    # pre-event repository-months as "control" -- the exact bug already
    # found and fixed once before in
    # analyze_agc_commit_function_parse_exclusions.py (v1 -> v2). Do not
    # reintroduce that confusion here.
    complete["treatment_group"] = complete["dataset_source"].map(
        {
            "control": "control",
            "treatment": "treatment",
        }
    )

    if complete["treatment_group"].isna().any():
        unexpected = sorted(
            complete.loc[
                complete["treatment_group"].isna(),
                "dataset_source",
            ]
            .dropna()
            .unique()
            .tolist()
        )
        raise ValueError(
            f"Unexpected dataset_source values: {unexpected}"
        )

    event_time_numeric = pd.to_numeric(
        complete[event_time_column],
        errors="coerce",
    )

    complete["treatment_period"] = "control"
    treatment_mask = complete["treatment_group"].eq("treatment")

    complete.loc[
        treatment_mask & event_time_numeric.lt(0),
        "treatment_period",
    ] = "pre"
    complete.loc[
        treatment_mask & event_time_numeric.eq(0),
        "treatment_period",
    ] = "event"
    complete.loc[
        treatment_mask & event_time_numeric.gt(0),
        "treatment_period",
    ] = "post"
    complete.loc[
        treatment_mask & event_time_numeric.isna(),
        "treatment_period",
    ] = "treatment_unknown_time"

    parse_overlap_summary = pd.DataFrame(
        [
            {
                "parse_exclusion_input_supplied": False,
                "parse_exclusion_affected_months": 0,
                "zero_event_and_parse_exclusion_months": 0,
                "event_positive_and_parse_exclusion_months": 0,
            }
        ]
    )

    if args.parse_exclusions_by_repo_month is not None:
        exclusions = normalize_keys(
            pd.read_csv(args.parse_exclusions_by_repo_month)
        )
        require_columns(
            exclusions,
            KEY_COLUMNS,
            "Parse-exclusion repository-month table",
        )

        count_column = resolve_parse_exclusion_count_column(exclusions)

        if count_column is None:
            exclusions = (
                exclusions[KEY_COLUMNS]
                .drop_duplicates()
                .assign(parse_exclusion_records=1)
            )
        else:
            exclusions = (
                exclusions[KEY_COLUMNS + [count_column]]
                .rename(
                    columns={
                        count_column: "parse_exclusion_records",
                    }
                )
                .groupby(KEY_COLUMNS, as_index=False)
                .agg(
                    parse_exclusion_records=(
                        "parse_exclusion_records",
                        "sum",
                    )
                )
            )

        complete = complete.merge(
            exclusions,
            on=KEY_COLUMNS,
            how="left",
            validate="one_to_one",
        )
        complete["parse_exclusion_records"] = (
            pd.to_numeric(
                complete["parse_exclusion_records"],
                errors="coerce",
            )
            .fillna(0)
        )
        complete["has_parse_exclusion"] = (
            complete["parse_exclusion_records"].gt(0).astype("int8")
        )

        parse_overlap_summary = pd.DataFrame(
            [
                {
                    "parse_exclusion_input_supplied": True,
                    "parse_exclusion_affected_months": int(
                        complete["has_parse_exclusion"].sum()
                    ),
                    "zero_event_and_parse_exclusion_months": int(
                        (
                            complete["zero_function_event_month"].eq(1)
                            & complete["has_parse_exclusion"].eq(1)
                        ).sum()
                    ),
                    "event_positive_and_parse_exclusion_months": int(
                        (
                            complete["has_function_change_event"].eq(1)
                            & complete["has_parse_exclusion"].eq(1)
                        ).sum()
                    ),
                }
            ]
        )
    else:
        complete["parse_exclusion_records"] = 0
        complete["has_parse_exclusion"] = 0

    complete["log1p_function_change_events"] = (
        pd.to_numeric(
            complete["function_change_events"],
            errors="raise",
        )
        .clip(lower=0)
        .map(lambda value: __import__("math").log1p(value))
    )
    complete["log1p_agc_function_change_events"] = (
        pd.to_numeric(
            complete["agc_function_change_events"],
            errors="raise",
        )
        .clip(lower=0)
        .map(lambda value: __import__("math").log1p(value))
    )
    complete["log1p_hwc_function_change_events"] = (
        pd.to_numeric(
            complete["hwc_function_change_events"],
            errors="raise",
        )
        .clip(lower=0)
        .map(lambda value: __import__("math").log1p(value))
    )

    by_dataset_source = summarize_binary(
        complete,
        ["dataset_source"],
    )
    by_treatment_period = summarize_binary(
        complete,
        ["treatment_group", "treatment_period"],
    )
    by_event_time = summarize_binary(
        complete,
        ["treatment_group", event_time_column],
    )

    checks = []

    def add_check(name: str, passed: bool, observed: object) -> None:
        checks.append(
            {
                "check": name,
                "passed": bool(passed),
                "observed": observed,
            }
        )

    add_check(
        "complete_panel_row_count",
        len(complete) == args.expected_panel_rows,
        len(complete),
    )
    add_check(
        "detector_summary_row_count",
        len(detector) == args.expected_detector_rows,
        len(detector),
    )
    add_check(
        "zero_event_month_count",
        int(complete["zero_function_event_month"].sum())
        == args.expected_zero_event_months,
        int(complete["zero_function_event_month"].sum()),
    )
    add_check(
        "all_event_positive_months_have_detector_summary",
        not missing_positive.any(),
        int(missing_positive.sum()),
    )
    add_check(
        "all_detector_missing_months_are_zero_event",
        bool(
            complete.loc[
                complete["detector_merge_status"] != "both",
                "zero_function_event_month",
            ].eq(1).all()
        ),
        int(
            (
                complete["detector_merge_status"] != "both"
            ).sum()
        ),
    )
    add_check(
        "zero_event_ratio_is_missing",
        bool(
            complete.loc[
                zero_event,
                "agc_function_change_event_ratio",
            ].isna().all()
        ),
        int(
            complete.loc[
                zero_event,
                "agc_function_change_event_ratio",
            ].notna().sum()
        ),
    )
    add_check(
        "event_arithmetic",
        bool(
            (
                pd.to_numeric(
                    complete["agc_function_change_events"],
                    errors="raise",
                )
                + pd.to_numeric(
                    complete["hwc_function_change_events"],
                    errors="raise",
                )
                == pd.to_numeric(
                    complete["function_change_events"],
                    errors="raise",
                )
            ).all()
        ),
        int(len(complete)),
    )

    # These checks lock in the static dataset_source-based cohort counts and
    # the fixed treatment_period partition, so that a future regression back
    # to the dynamic is_treatment column (the bug this revision fixes) fails
    # loudly instead of silently reproducing incorrect downstream summaries.
    add_check(
        "static_control_repo_month_count",
        int(complete["dataset_source"].eq("control").sum()) == 780,
        int(complete["dataset_source"].eq("control").sum()),
    )
    add_check(
        "static_treatment_repo_month_count",
        int(complete["dataset_source"].eq("treatment").sum()) == 853,
        int(complete["dataset_source"].eq("treatment").sum()),
    )
    add_check(
        "treatment_pre_month_count",
        int(complete["treatment_period"].eq("pre").sum()) == 421,
        int(complete["treatment_period"].eq("pre").sum()),
    )
    add_check(
        "treatment_event_month_count",
        int(complete["treatment_period"].eq("event").sum()) == 100,
        int(complete["treatment_period"].eq("event").sum()),
    )
    add_check(
        "treatment_post_month_count",
        int(complete["treatment_period"].eq("post").sum()) == 332,
        int(complete["treatment_period"].eq("post").sum()),
    )
    add_check(
        "treatment_period_partition",
        int(complete["treatment_period"].isin(["pre", "event", "post"]).sum())
        == 853,
        int(complete["treatment_period"].isin(["pre", "event", "post"]).sum()),
    )
    add_check(
        "detection_complete_boolean_nonmissing",
        bool(
            complete["detection_complete"].dtype.name == "boolean"
            and complete["detection_complete"].notna().all()
        ),
        str(complete["detection_complete"].dtype),
    )
    add_check(
        "detection_complete_all_true",
        bool(complete["detection_complete"].eq(True).all()),
        int(complete["detection_complete"].eq(False).sum()),
    )
    add_check(
        "treatment_group_matches_dataset_source",
        int(complete["treatment_group"].ne(complete["dataset_source"]).sum())
        == 0,
        int(complete["treatment_group"].ne(complete["dataset_source"]).sum()),
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    treatment_group_validation = (
        complete.groupby(["dataset_source", "treatment_group"])
        .size()
        .reset_index(name="rows")
        .sort_values(["dataset_source", "treatment_group"])
    )
    treatment_group_validation_output = (
        args.output_dir / "zero_function_event_treatment_group_validation.csv"
    )

    complete_output = (
        args.output_dir
        / "repo_month_agc_function_event_analysis_complete.csv"
    )
    dataset_output = (
        args.output_dir
        / "zero_function_event_months_by_dataset_source.csv"
    )
    period_output = (
        args.output_dir
        / "zero_function_event_months_by_treatment_period.csv"
    )
    event_time_output = (
        args.output_dir
        / "zero_function_event_months_by_event_time.csv"
    )
    overlap_output = (
        args.output_dir
        / "zero_function_event_parse_exclusion_overlap.csv"
    )
    checks_output = (
        args.output_dir
        / "zero_function_event_month_checks.csv"
    )
    summary_output = (
        args.output_dir
        / "zero_function_event_month_summary.json"
    )

    complete.to_csv(complete_output, index=False)
    by_dataset_source.to_csv(dataset_output, index=False)
    by_treatment_period.to_csv(period_output, index=False)
    by_event_time.to_csv(event_time_output, index=False)
    parse_overlap_summary.to_csv(overlap_output, index=False)
    checks_frame.to_csv(checks_output, index=False)
    treatment_group_validation.to_csv(
        treatment_group_validation_output, index=False
    )

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "complete_repo_months": int(len(complete)),
        "detector_summary_repo_months": int(len(detector)),
        "event_positive_repo_months": int(
            complete["has_function_change_event"].sum()
        ),
        "zero_event_repo_months": int(
            complete["zero_function_event_month"].sum()
        ),
        "conditional_ratio_repo_months": int(
            complete["agc_function_change_event_ratio"].notna().sum()
        ),
        "parse_exclusion_affected_repo_months": int(
            complete["has_parse_exclusion"].sum()
        ),
        "outputs": {
            "complete_analysis_table": str(complete_output),
            "by_dataset_source": str(dataset_output),
            "by_treatment_period": str(period_output),
            "by_event_time": str(event_time_output),
            "parse_exclusion_overlap": str(overlap_output),
            "treatment_group_validation": str(treatment_group_validation_output),
            "checks": str(checks_output),
        },
    }

    summary_output.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("=" * 76)
    print("Zero-function-event repository-month analysis")
    print("=" * 76)
    print(f"Status:                       {summary['status']}")
    print(f"Complete repository-months:   {summary['complete_repo_months']}")
    print(
        "Event-positive months:        "
        f"{summary['event_positive_repo_months']}"
    )
    print(
        "Zero-event months:            "
        f"{summary['zero_event_repo_months']}"
    )
    print(
        "Conditional-ratio months:     "
        f"{summary['conditional_ratio_repo_months']}"
    )
    print(
        "Parse-exclusion months:       "
        f"{summary['parse_exclusion_affected_repo_months']}"
    )
    print(f"Complete table:               {complete_output}")
    print(f"QC checks:                    {checks_output}")
    print(f"Summary:                      {summary_output}")
    print("=" * 76)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise