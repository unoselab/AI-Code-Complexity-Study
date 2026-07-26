#!/usr/bin/env python3
"""Prepare commit-function AGC DiD inputs for one inclusive line-size range.

This script reuses the already-computed event-level ML classifier predictions.
It does not rerun the classifier.

Research question
-----------------
Did Cursor adoption increase or decrease function-change events whose inclusive
source-line span is within a selected range, relative to control repositories?

The inclusive source-line span is computed as:

    function_line_count = end_line - start_line + 1

For the default specification, only events satisfying the following condition
are retained:

    3 <= function_line_count <= 8

The selected events are re-aggregated to the repository-month level and merged
onto the existing covariate-complete run-py-5e full panel. Repository-months
with no selected events remain in the full panel with zero counts. The AGC
ratio remains missing when the selected-event count is zero.

This is a post hoc exploratory heterogeneity specification. It must not be
reported as the all-function primary effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


KEY_COLUMNS = ["dataset_source", "repo_name", "time"]

PREDICTION_REQUIRED_COLUMNS = KEY_COLUMNS + [
    "function_event_id",
    "analysis_status",
    "predicted_agc",
    "predicted_hwc",
    "start_line",
    "end_line",
]

# These columns are needed by the existing commit-function Borusyak Rmd.
BASE_PANEL_REQUIRED_COLUMNS = KEY_COLUMNS + [
    "time_to_event",
    "event",
    "post_event",
    "treat",
    "unit_id",
    "calendar_time",
    "log1p_age",
    "ncloc_paper",
    "ncloc_python_snapshot",
    "log1p_contributors",
    "log1p_stars",
    "log1p_issues",
    "analysis_ready_paper_ncloc",
    "analysis_ready_python_snapshot_ncloc",
    "has_parse_exclusion",
    "detection_complete",
    "treatment_group",
    "parse_exclusion_records",
    "treatment_period",
]

OUTCOME_COLUMNS = [
    "has_function_change_event",
    "zero_function_event_month",
    "function_change_events",
    "agc_function_change_events",
    "hwc_function_change_events",
    "agc_function_change_event_ratio",
    "log1p_function_change_events",
    "log1p_agc_function_change_events",
    "log1p_hwc_function_change_events",
]

# Remove all-size outcomes before attaching the line-range-specific outcomes.
# This prevents downstream code from accidentally analyzing the wrong counts.
DROP_EXISTING_OUTCOME_COLUMNS = OUTCOME_COLUMNS + [
    "function_change_events_manifest",
    "function_change_events_scored",
    "function_change_events_failed",
    "added_function_events",
    "modified_function_events",
    "added_agc_function_events",
    "added_hwc_function_events",
    "modified_agc_function_events",
    "modified_hwc_function_events",
    "unique_changed_functions_scored",
    "ratio_sample",
]

DEFAULT_MIN_FUNCTION_LINES = 3
DEFAULT_MAX_FUNCTION_LINES = 8
DEFAULT_EXPECTED_BASE_ROWS = 1633


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare repository-month Borusyak DiD panels for an inclusive "
            "commit-function source-line-span range."
        )
    )
    parser.add_argument("--predictions", type=Path, required=False)
    parser.add_argument("--base-did-panel", type=Path, required=False)
    parser.add_argument("--output-dir", type=Path, required=False)
    parser.add_argument("--qc-dir", type=Path, required=False)
    parser.add_argument(
        "--min-function-lines",
        type=int,
        default=DEFAULT_MIN_FUNCTION_LINES,
        help="Inclusive minimum function source-line span. Default: 3.",
    )
    parser.add_argument(
        "--max-function-lines",
        type=int,
        default=DEFAULT_MAX_FUNCTION_LINES,
        help="Inclusive maximum function source-line span. Default: 8.",
    )
    parser.add_argument(
        "--expected-base-rows",
        type=int,
        default=DEFAULT_EXPECTED_BASE_ROWS,
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    label: str,
) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
    return result


def require_unique_keys(frame: pd.DataFrame, label: str) -> None:
    duplicated = frame.duplicated(KEY_COLUMNS, keep=False)
    if duplicated.any():
        sample = frame.loc[duplicated, KEY_COLUMNS].head(20)
        raise ValueError(
            f"{label} contains duplicate repository-month keys:\n"
            f"{sample.to_string(index=False)}"
        )


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    observed: Any,
) -> None:
    checks.append({"check": name, "passed": bool(passed), "observed": observed})


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
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
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    temporary.replace(path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_range(min_lines: int, max_lines: int) -> None:
    if min_lines < 1:
        raise ValueError("--min-function-lines must be at least 1")
    if max_lines < min_lines:
        raise ValueError(
            "--max-function-lines must be greater than or equal to "
            "--min-function-lines"
        )


def clean_base_panel(base_panel: pd.DataFrame) -> pd.DataFrame:
    columns_to_drop = [
        column
        for column in DROP_EXISTING_OUTCOME_COLUMNS
        if column in base_panel.columns
    ]
    return base_panel.drop(columns=columns_to_drop).copy()


def prepare_scored_events(
    predictions: pd.DataFrame,
    checks: list[dict[str, Any]],
) -> pd.DataFrame:
    duplicate_ids = int(predictions["function_event_id"].duplicated().sum())
    add_check(
        checks,
        "function_event_id_unique",
        duplicate_ids == 0,
        duplicate_ids,
    )

    status_missing = int(predictions["analysis_status"].isna().sum())
    add_check(
        checks,
        "analysis_status_nonmissing",
        status_missing == 0,
        status_missing,
    )

    events = predictions.loc[predictions["analysis_status"].eq("ok")].copy()
    add_check(
        checks,
        "all_prediction_rows_scored",
        len(events) == len(predictions),
        {"total": int(len(predictions)), "scored": int(len(events))},
    )

    for column in ["start_line", "end_line", "predicted_agc", "predicted_hwc"]:
        events[column] = pd.to_numeric(events[column], errors="coerce")

    invalid_span = (
        events["start_line"].isna()
        | events["end_line"].isna()
        | events["start_line"].lt(1)
        | events["end_line"].lt(events["start_line"])
        | events["start_line"].mod(1).ne(0)
        | events["end_line"].mod(1).ne(0)
    )
    add_check(
        checks,
        "valid_inclusive_function_line_spans",
        not bool(invalid_span.any()),
        int(invalid_span.sum()),
    )
    if invalid_span.any():
        sample = events.loc[
            invalid_span,
            ["function_event_id", "start_line", "end_line"],
        ].head(20)
        raise ValueError(
            "Scored prediction rows contain invalid line spans:\n"
            + sample.to_string(index=False)
        )

    prediction_invalid = (
        events["predicted_agc"].isna()
        | events["predicted_hwc"].isna()
        | events["predicted_agc"].mod(1).ne(0)
        | events["predicted_hwc"].mod(1).ne(0)
    )
    if prediction_invalid.any():
        raise ValueError("Scored rows contain invalid AGC/HWC prediction values")

    events["start_line"] = events["start_line"].astype("int64")
    events["end_line"] = events["end_line"].astype("int64")
    events["predicted_agc"] = events["predicted_agc"].astype("int64")
    events["predicted_hwc"] = events["predicted_hwc"].astype("int64")
    events["function_line_count"] = (
        events["end_line"] - events["start_line"] + 1
    )

    partition_failures = int(
        (events["predicted_agc"] + events["predicted_hwc"]).ne(1).sum()
    )
    add_check(
        checks,
        "prediction_agc_hwc_partition",
        partition_failures == 0,
        partition_failures,
    )
    add_check(
        checks,
        "function_line_count_positive",
        bool(events["function_line_count"].ge(1).all()),
        int(events["function_line_count"].lt(1).sum()),
    )
    return events


def aggregate_selected_events(
    events: pd.DataFrame,
    min_lines: int,
    max_lines: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = events.loc[
        events["function_line_count"].between(
            min_lines, max_lines, inclusive="both"
        )
    ].copy()

    if selected.empty:
        aggregated = pd.DataFrame(
            columns=KEY_COLUMNS
            + [
                "function_change_events",
                "agc_function_change_events",
                "hwc_function_change_events",
            ]
        )
        return selected, aggregated

    aggregated = (
        selected.groupby(KEY_COLUMNS, dropna=False)
        .agg(
            function_change_events=("function_event_id", "size"),
            agc_function_change_events=("predicted_agc", "sum"),
            hwc_function_change_events=("predicted_hwc", "sum"),
        )
        .reset_index()
    )
    return selected, aggregated


def build_line_range_panel(
    base_panel: pd.DataFrame,
    aggregated: pd.DataFrame,
    min_lines: int,
    max_lines: int,
) -> pd.DataFrame:
    panel = clean_base_panel(base_panel).merge(
        aggregated,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    count_columns = [
        "function_change_events",
        "agc_function_change_events",
        "hwc_function_change_events",
    ]
    for column in count_columns:
        panel[column] = (
            pd.to_numeric(panel[column], errors="coerce")
            .fillna(0)
            .astype("int64")
        )

    panel["has_function_change_event"] = (
        panel["function_change_events"].gt(0).astype("int8")
    )
    panel["zero_function_event_month"] = (
        panel["function_change_events"].eq(0).astype("int8")
    )
    panel["agc_function_change_event_ratio"] = np.where(
        panel["function_change_events"].gt(0),
        panel["agc_function_change_events"] / panel["function_change_events"],
        np.nan,
    )
    panel["log1p_function_change_events"] = np.log1p(
        panel["function_change_events"]
    )
    panel["log1p_agc_function_change_events"] = np.log1p(
        panel["agc_function_change_events"]
    )
    panel["log1p_hwc_function_change_events"] = np.log1p(
        panel["hwc_function_change_events"]
    )

    range_label = f"{min_lines}-{max_lines}"
    panel["function_line_lower_bound_inclusive"] = min_lines
    panel["function_line_upper_bound_inclusive"] = max_lines
    panel["function_line_range"] = range_label
    panel["function_line_range_specification"] = "inclusive_bounded_range"
    panel["analysis_design_status"] = "post_hoc_exploratory_heterogeneity"

    # Full-sample readiness depends only on covariate completeness and can be
    # retained from run-py-5e. Ratio readiness must be recomputed because the
    # 3-8-line denominator differs from the all-function denominator.
    full_paper_ready = pd.to_numeric(
        panel["analysis_ready_paper_ncloc"], errors="coerce"
    ).eq(1)
    full_snapshot_ready = pd.to_numeric(
        panel["analysis_ready_python_snapshot_ncloc"], errors="coerce"
    ).eq(1)
    ratio_ready = (
        panel["function_change_events"].gt(0)
        & panel["agc_function_change_event_ratio"].notna()
    )
    panel["analysis_ready_ratio_paper_ncloc"] = (
        ratio_ready & full_paper_ready
    ).astype("int8")
    panel["analysis_ready_ratio_python_snapshot_ncloc"] = (
        ratio_ready & full_snapshot_ready
    ).astype("int8")

    return panel


def validate_panel_outcomes(
    panel: pd.DataFrame,
    checks: list[dict[str, Any]],
) -> None:
    positive = panel["function_change_events"].gt(0)

    event_partition_failures = int(
        (
            panel["agc_function_change_events"]
            + panel["hwc_function_change_events"]
            != panel["function_change_events"]
        ).sum()
    )
    add_check(
        checks,
        "line_range_event_partition",
        event_partition_failures == 0,
        event_partition_failures,
    )

    occurrence_failures = int(
        (
            panel["has_function_change_event"].astype("int64")
            != panel["function_change_events"].gt(0).astype("int64")
        ).sum()
    )
    zero_flag_failures = int(
        (
            panel["zero_function_event_month"].astype("int64")
            != panel["function_change_events"].eq(0).astype("int64")
        ).sum()
    )
    add_check(
        checks,
        "line_range_occurrence_matches_count",
        occurrence_failures == 0,
        occurrence_failures,
    )
    add_check(
        checks,
        "line_range_zero_flag_matches_count",
        zero_flag_failures == 0,
        zero_flag_failures,
    )

    zero_ratio_nonmissing = int(
        panel.loc[~positive, "agc_function_change_event_ratio"].notna().sum()
    )
    positive_ratio_missing = int(
        panel.loc[positive, "agc_function_change_event_ratio"].isna().sum()
    )
    ratio_out_of_bounds = int(
        (
            ~panel.loc[positive, "agc_function_change_event_ratio"].between(
                0, 1, inclusive="both"
            )
        ).sum()
    )
    ratio_formula_mismatch = int(
        (
            ~np.isclose(
                panel.loc[positive, "agc_function_change_event_ratio"],
                panel.loc[positive, "agc_function_change_events"]
                / panel.loc[positive, "function_change_events"],
                rtol=0.0,
                atol=1e-12,
            )
        ).sum()
    )
    add_check(
        checks,
        "line_range_zero_event_ratio_missing",
        zero_ratio_nonmissing == 0,
        zero_ratio_nonmissing,
    )
    add_check(
        checks,
        "line_range_positive_event_ratio_nonmissing",
        positive_ratio_missing == 0,
        positive_ratio_missing,
    )
    add_check(
        checks,
        "line_range_ratio_bounds",
        ratio_out_of_bounds == 0,
        ratio_out_of_bounds,
    )
    add_check(
        checks,
        "line_range_ratio_formula",
        ratio_formula_mismatch == 0,
        ratio_formula_mismatch,
    )

    for raw_column, log_column in [
        ("function_change_events", "log1p_function_change_events"),
        ("agc_function_change_events", "log1p_agc_function_change_events"),
        ("hwc_function_change_events", "log1p_hwc_function_change_events"),
    ]:
        mismatch = int(
            (
                ~np.isclose(
                    panel[log_column],
                    np.log1p(panel[raw_column]),
                    rtol=0.0,
                    atol=1e-12,
                )
            ).sum()
        )
        add_check(
            checks,
            f"{log_column}_matches_line_range_raw_count",
            mismatch == 0,
            mismatch,
        )


def create_support(
    events: pd.DataFrame,
    selected: pd.DataFrame,
    panel: pd.DataFrame,
    min_lines: int,
    max_lines: int,
) -> pd.DataFrame:
    positive = panel["function_change_events"].gt(0)
    selected_total = int(len(selected))
    selected_agc = int(selected["predicted_agc"].sum())
    below = int(events["function_line_count"].lt(min_lines).sum())
    above = int(events["function_line_count"].gt(max_lines).sum())

    return pd.DataFrame(
        [
            {
                "function_line_range": f"{min_lines}-{max_lines}",
                "min_function_lines_inclusive": min_lines,
                "max_function_lines_inclusive": max_lines,
                "analysis_design_status": "post_hoc_exploratory_heterogeneity",
                "total_scored_events": int(len(events)),
                "selected_events": selected_total,
                "selected_event_share": (
                    selected_total / len(events) if len(events) else np.nan
                ),
                "events_below_range": below,
                "events_above_range": above,
                "selected_agc_events": selected_agc,
                "selected_hwc_events": int(selected["predicted_hwc"].sum()),
                "selected_pooled_agc_ratio": (
                    selected_agc / selected_total if selected_total else np.nan
                ),
                "base_repo_months": int(len(panel)),
                "event_positive_repo_months": int(positive.sum()),
                "zero_event_repo_months": int((~positive).sum()),
                "event_positive_repositories": int(
                    panel.loc[positive, "repo_name"].nunique()
                ),
                "all_repositories": int(panel["repo_name"].nunique()),
            }
        ]
    )


def create_support_by_group(panel: pd.DataFrame) -> pd.DataFrame:
    grouping_columns = ["dataset_source", "treatment_period"]
    rows: list[dict[str, Any]] = []
    for group_values, group in panel.groupby(
        grouping_columns, dropna=False, observed=False
    ):
        dataset_source, treatment_period = group_values
        positive = group["function_change_events"].gt(0)
        total_events = int(group["function_change_events"].sum())
        agc_events = int(group["agc_function_change_events"].sum())
        rows.append(
            {
                "dataset_source": dataset_source,
                "treatment_period": treatment_period,
                "repo_months": int(len(group)),
                "repositories": int(group["repo_name"].nunique()),
                "event_positive_repo_months": int(positive.sum()),
                "zero_event_repo_months": int((~positive).sum()),
                "event_positive_repo_month_share": float(positive.mean()),
                "function_change_events": total_events,
                "agc_function_change_events": agc_events,
                "hwc_function_change_events": int(
                    group["hwc_function_change_events"].sum()
                ),
                "pooled_agc_ratio": (
                    agc_events / total_events if total_events else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def create_event_time_support(panel: pd.DataFrame) -> pd.DataFrame:
    return (
        panel.groupby(["dataset_source", "time_to_event"], dropna=False)
        .agg(
            repo_months=("repo_name", "size"),
            repositories=("repo_name", "nunique"),
            event_positive_repo_months=("has_function_change_event", "sum"),
            zero_event_repo_months=("zero_function_event_month", "sum"),
            function_change_events=("function_change_events", "sum"),
            agc_function_change_events=("agc_function_change_events", "sum"),
            hwc_function_change_events=("hwc_function_change_events", "sum"),
            parse_exclusion_months=("has_parse_exclusion", "sum"),
        )
        .reset_index()
    )


def create_sample_summary(
    full_panel: pd.DataFrame,
    ratio_panel: pd.DataFrame,
    parse_clean_full: pd.DataFrame,
    parse_clean_ratio: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sample_name, frame in [
        ("full", full_panel),
        ("ratio_positive_event", ratio_panel),
        ("parse_clean_full", parse_clean_full),
        ("parse_clean_ratio_positive_event", parse_clean_ratio),
    ]:
        rows.append(
            {
                "sample": sample_name,
                "repo_months": int(len(frame)),
                "repositories": int(frame["repo_name"].nunique()),
                "control_repo_months": int(
                    frame["dataset_source"].eq("control").sum()
                ),
                "treatment_repo_months": int(
                    frame["dataset_source"].eq("treatment").sum()
                ),
                "event_positive_repo_months": int(
                    frame["function_change_events"].gt(0).sum()
                ),
                "zero_event_repo_months": int(
                    frame["function_change_events"].eq(0).sum()
                ),
                "parse_exclusion_months": int(
                    pd.to_numeric(
                        frame["has_parse_exclusion"], errors="coerce"
                    ).fillna(0).sum()
                ),
                "paper_ncloc_ready_rows": int(
                    pd.to_numeric(
                        frame["analysis_ready_paper_ncloc"], errors="coerce"
                    ).eq(1).sum()
                ),
                "python_snapshot_ncloc_ready_rows": int(
                    pd.to_numeric(
                        frame["analysis_ready_python_snapshot_ncloc"],
                        errors="coerce",
                    ).eq(1).sum()
                ),
                "ratio_paper_ncloc_ready_rows": int(
                    pd.to_numeric(
                        frame["analysis_ready_ratio_paper_ncloc"],
                        errors="coerce",
                    ).eq(1).sum()
                ),
                "ratio_python_snapshot_ncloc_ready_rows": int(
                    pd.to_numeric(
                        frame["analysis_ready_ratio_python_snapshot_ncloc"],
                        errors="coerce",
                    ).eq(1).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def analyze(
    predictions_path: Path,
    base_did_panel_path: Path,
    output_dir: Path,
    qc_dir: Path,
    min_function_lines: int,
    max_function_lines: int,
    expected_base_rows: int,
) -> dict[str, Any]:
    validate_range(min_function_lines, max_function_lines)

    predictions = normalize_keys(
        pd.read_csv(predictions_path, low_memory=False)
    )
    base_panel = normalize_keys(
        pd.read_csv(base_did_panel_path, low_memory=False)
    )

    require_columns(predictions, PREDICTION_REQUIRED_COLUMNS, "Predictions")
    require_columns(base_panel, BASE_PANEL_REQUIRED_COLUMNS, "Base DiD panel")
    require_unique_keys(base_panel, "Base DiD panel")

    checks: list[dict[str, Any]] = []
    add_check(
        checks,
        "line_range_valid",
        min_function_lines >= 1 and max_function_lines >= min_function_lines,
        {
            "min_inclusive": min_function_lines,
            "max_inclusive": max_function_lines,
        },
    )
    add_check(
        checks,
        "base_panel_expected_rows",
        len(base_panel) == expected_base_rows,
        int(len(base_panel)),
    )

    events = prepare_scored_events(predictions, checks)

    event_keys = events[KEY_COLUMNS].drop_duplicates()
    unmatched_event_keys = event_keys.merge(
        base_panel[KEY_COLUMNS],
        on=KEY_COLUMNS,
        how="left",
        indicator=True,
    )
    unmatched_count = int(unmatched_event_keys["_merge"].ne("both").sum())
    add_check(
        checks,
        "all_event_repo_months_in_base_panel",
        unmatched_count == 0,
        unmatched_count,
    )

    selected, aggregated = aggregate_selected_events(
        events,
        min_function_lines,
        max_function_lines,
    )
    add_check(
        checks,
        "selected_events_nonempty",
        len(selected) > 0,
        int(len(selected)),
    )
    add_check(
        checks,
        "selected_events_within_requested_range",
        bool(
            selected["function_line_count"]
            .between(
                min_function_lines,
                max_function_lines,
                inclusive="both",
            )
            .all()
        ),
        {
            "observed_min": (
                int(selected["function_line_count"].min())
                if not selected.empty
                else None
            ),
            "observed_max": (
                int(selected["function_line_count"].max())
                if not selected.empty
                else None
            ),
        },
    )

    panel = build_line_range_panel(
        base_panel,
        aggregated,
        min_function_lines,
        max_function_lines,
    )
    add_check(
        checks,
        "full_panel_row_count_preserved",
        len(panel) == len(base_panel),
        int(len(panel)),
    )
    add_check(
        checks,
        "full_panel_repo_month_key_order_preserved",
        panel[KEY_COLUMNS].reset_index(drop=True).equals(
            base_panel[KEY_COLUMNS].reset_index(drop=True)
        ),
        int(len(panel)),
    )
    add_check(
        checks,
        "full_panel_unique_repo_month_keys",
        not panel.duplicated(KEY_COLUMNS).any(),
        int(panel.duplicated(KEY_COLUMNS).sum()),
    )

    validate_panel_outcomes(panel, checks)

    direct_totals = {
        "function_change_events": int(len(selected)),
        "agc_function_change_events": int(selected["predicted_agc"].sum()),
        "hwc_function_change_events": int(selected["predicted_hwc"].sum()),
    }
    panel_totals = {
        "function_change_events": int(panel["function_change_events"].sum()),
        "agc_function_change_events": int(
            panel["agc_function_change_events"].sum()
        ),
        "hwc_function_change_events": int(
            panel["hwc_function_change_events"].sum()
        ),
    }
    add_check(
        checks,
        "panel_totals_match_direct_event_selection",
        panel_totals == direct_totals,
        {"panel": panel_totals, "direct": direct_totals},
    )

    positive_mask = panel["function_change_events"].gt(0)
    parse_clean_mask = pd.to_numeric(
        panel["has_parse_exclusion"], errors="coerce"
    ).eq(0)

    full_panel = panel.copy()
    ratio_panel = panel.loc[positive_mask].copy()
    ratio_panel["ratio_sample"] = 1
    parse_clean_full = panel.loc[parse_clean_mask].copy()
    parse_clean_ratio = panel.loc[positive_mask & parse_clean_mask].copy()
    parse_clean_ratio["ratio_sample"] = 1

    add_check(
        checks,
        "ratio_panel_contains_only_positive_event_months",
        bool(ratio_panel["function_change_events"].gt(0).all()),
        int(ratio_panel["function_change_events"].le(0).sum()),
    )
    add_check(
        checks,
        "parse_clean_full_has_no_parse_exclusions",
        int(
            pd.to_numeric(
                parse_clean_full["has_parse_exclusion"], errors="coerce"
            ).fillna(0).sum()
        )
        == 0,
        int(
            pd.to_numeric(
                parse_clean_full["has_parse_exclusion"], errors="coerce"
            ).fillna(0).sum()
        ),
    )
    add_check(
        checks,
        "parse_clean_ratio_has_no_parse_exclusions",
        int(
            pd.to_numeric(
                parse_clean_ratio["has_parse_exclusion"], errors="coerce"
            ).fillna(0).sum()
        )
        == 0,
        int(
            pd.to_numeric(
                parse_clean_ratio["has_parse_exclusion"], errors="coerce"
            ).fillna(0).sum()
        ),
    )

    support = create_support(
        events,
        selected,
        panel,
        min_function_lines,
        max_function_lines,
    )
    support_by_group = create_support_by_group(panel)
    event_time_support = create_event_time_support(panel)
    sample_summary = create_sample_summary(
        full_panel,
        ratio_panel,
        parse_clean_full,
        parse_clean_ratio,
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    range_slug = f"{min_function_lines}_{max_function_lines}"
    full_path = (
        output_dir
        / f"panel_event_monthly_agc_commit_function_lines_{range_slug}.csv"
    )
    ratio_path = (
        output_dir
        / f"panel_event_monthly_agc_commit_function_lines_{range_slug}_ratio_positive.csv"
    )
    parse_clean_full_path = (
        output_dir
        / f"panel_event_monthly_agc_commit_function_lines_{range_slug}_parse_clean.csv"
    )
    parse_clean_ratio_path = (
        output_dir
        / f"panel_event_monthly_agc_commit_function_lines_{range_slug}_ratio_positive_parse_clean.csv"
    )
    support_path = output_dir / "agc_commit_function_line_range_support.csv"
    support_by_group_path = (
        output_dir / "agc_commit_function_line_range_support_by_group.csv"
    )
    event_time_support_path = (
        output_dir / "agc_commit_function_line_range_event_time_support.csv"
    )
    sample_summary_path = (
        output_dir / "agc_commit_function_line_range_sample_summary.csv"
    )
    checks_path = qc_dir / "agc_commit_function_line_range_checks.csv"
    summary_path = qc_dir / "agc_commit_function_line_range_summary.json"

    atomic_write_csv(full_panel, full_path)
    atomic_write_csv(ratio_panel, ratio_path)
    atomic_write_csv(parse_clean_full, parse_clean_full_path)
    atomic_write_csv(parse_clean_ratio, parse_clean_ratio_path)
    atomic_write_csv(support, support_path)
    atomic_write_csv(support_by_group, support_by_group_path)
    atomic_write_csv(event_time_support, event_time_support_path)
    atomic_write_csv(sample_summary, sample_summary_path)
    atomic_write_csv(checks_frame, checks_path)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "analysis_design_status": "post_hoc_exploratory_heterogeneity",
        "research_question": (
            "Did Cursor adoption increase or decrease function-change events "
            f"spanning {min_function_lines}-{max_function_lines} source lines "
            "relative to control repositories?"
        ),
        "line_count_definition": "end_line - start_line + 1",
        "min_function_lines_inclusive": min_function_lines,
        "max_function_lines_inclusive": max_function_lines,
        "predictions_path": str(predictions_path),
        "predictions_sha256": sha256_file(predictions_path),
        "base_did_panel_path": str(base_did_panel_path),
        "base_did_panel_sha256": sha256_file(base_did_panel_path),
        "base_panel_rows": int(len(base_panel)),
        "selected_events": int(len(selected)),
        "selected_agc_events": int(selected["predicted_agc"].sum()),
        "selected_hwc_events": int(selected["predicted_hwc"].sum()),
        "full_panel_rows": int(len(full_panel)),
        "ratio_positive_rows": int(len(ratio_panel)),
        "parse_clean_full_rows": int(len(parse_clean_full)),
        "parse_clean_ratio_positive_rows": int(len(parse_clean_ratio)),
        "outcomes": OUTCOME_COLUMNS,
        "outputs": {
            "full_panel": str(full_path),
            "ratio_positive_panel": str(ratio_path),
            "parse_clean_full_panel": str(parse_clean_full_path),
            "parse_clean_ratio_positive_panel": str(parse_clean_ratio_path),
            "support": str(support_path),
            "support_by_group": str(support_by_group_path),
            "event_time_support": str(event_time_support_path),
            "sample_summary": str(sample_summary_path),
            "checks": str(checks_path),
            "summary": str(summary_path),
        },
    }
    atomic_write_json(summary, summary_path)
    return summary


def build_self_test_inputs(root: Path) -> tuple[Path, Path]:
    predictions = pd.DataFrame(
        [
            # Below the selected range: excluded.
            {
                "function_event_id": "e2",
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2024-01",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "start_line": 10,
                "end_line": 11,
            },
            # Exact lower boundary: included as AGC-like.
            {
                "function_event_id": "e3",
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2024-01",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "start_line": 20,
                "end_line": 22,
            },
            # Exact upper boundary: included as HWC-like.
            {
                "function_event_id": "e8",
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "start_line": 30,
                "end_line": 37,
            },
            # Above the selected range: excluded.
            {
                "function_event_id": "e9",
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "start_line": 40,
                "end_line": 48,
            },
        ]
    )

    base_rows: list[dict[str, Any]] = []
    for dataset_source, repo_name, time, event, parse_exclusion in [
        ("control", "owner/control", "2024-01", pd.NA, 0),
        ("treatment", "owner/treatment", "2024-02", "2024-02", 1),
    ]:
        treat = 1 if dataset_source == "treatment" else 0
        base_rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "time": time,
                "time_to_event": 0 if treat else pd.NA,
                "event": event,
                "post_event": treat,
                "treat": treat,
                "unit_id": repo_name,
                "calendar_time": time,
                "log1p_age": np.log1p(10),
                "ncloc_paper": 100,
                "ncloc_python_snapshot": 90,
                "log1p_contributors": np.log1p(2),
                "log1p_stars": np.log1p(3),
                "log1p_issues": np.log1p(4),
                "analysis_ready_paper_ncloc": 1,
                "analysis_ready_python_snapshot_ncloc": 1,
                "analysis_ready_ratio_paper_ncloc": 1,
                "analysis_ready_ratio_python_snapshot_ncloc": 1,
                "has_parse_exclusion": parse_exclusion,
                "detection_complete": True,
                "treatment_group": dataset_source,
                "parse_exclusion_records": parse_exclusion,
                "treatment_period": "event" if treat else "control",
                # Existing all-size outcomes must be replaced.
                "function_change_events": 99,
                "agc_function_change_events": 99,
                "hwc_function_change_events": 0,
                "has_function_change_event": 1,
                "zero_function_event_month": 0,
                "agc_function_change_event_ratio": 1.0,
                "log1p_function_change_events": np.log1p(99),
                "log1p_agc_function_change_events": np.log1p(99),
                "log1p_hwc_function_change_events": 0.0,
            }
        )

    predictions_path = root / "predictions.csv"
    base_panel_path = root / "base_panel.csv"
    predictions.to_csv(predictions_path, index=False)
    pd.DataFrame(base_rows).to_csv(base_panel_path, index=False)
    return predictions_path, base_panel_path


def self_test() -> None:
    with tempfile.TemporaryDirectory(
        prefix="agc-function-line-range-did-v1-"
    ) as temp_dir:
        root = Path(temp_dir)
        predictions_path, base_panel_path = build_self_test_inputs(root)
        output_dir = root / "output"
        qc_dir = root / "qc"

        summary = analyze(
            predictions_path=predictions_path,
            base_did_panel_path=base_panel_path,
            output_dir=output_dir,
            qc_dir=qc_dir,
            min_function_lines=3,
            max_function_lines=8,
            expected_base_rows=2,
        )
        if summary["status"] != "PASS":
            raise AssertionError(summary)
        if summary["selected_events"] != 2:
            raise AssertionError("Expected exactly two selected boundary events")

        panel = pd.read_csv(
            output_dir
            / "panel_event_monthly_agc_commit_function_lines_3_8.csv"
        )
        control = panel.loc[panel["repo_name"].eq("owner/control")].iloc[0]
        treatment = panel.loc[
            panel["repo_name"].eq("owner/treatment")
        ].iloc[0]

        if int(control["function_change_events"]) != 1:
            raise AssertionError("Expected one selected control event")
        if int(control["agc_function_change_events"]) != 1:
            raise AssertionError("Expected selected control event to be AGC-like")
        if int(treatment["function_change_events"]) != 1:
            raise AssertionError("Expected one selected treatment event")
        if int(treatment["hwc_function_change_events"]) != 1:
            raise AssertionError("Expected selected treatment event to be HWC-like")
        if int(control["function_line_lower_bound_inclusive"]) != 3:
            raise AssertionError("Minimum line-range metadata mismatch")
        if int(control["function_line_upper_bound_inclusive"]) != 8:
            raise AssertionError("Maximum line-range metadata mismatch")

        parse_clean = pd.read_csv(
            output_dir
            / "panel_event_monthly_agc_commit_function_lines_3_8_parse_clean.csv"
        )
        if len(parse_clean) != 1:
            raise AssertionError("Expected one parse-clean repository-month")

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()

    if args.self_test:
        self_test()
        return 0

    required = [args.predictions, args.base_did_panel, args.output_dir, args.qc_dir]
    if any(value is None for value in required):
        raise SystemExit(
            "--predictions, --base-did-panel, --output-dir, and --qc-dir "
            "are required unless --self-test is used."
        )
    validate_range(args.min_function_lines, args.max_function_lines)
    if args.expected_base_rows <= 0:
        raise ValueError("--expected-base-rows must be positive")
    if not args.predictions.is_file():
        raise FileNotFoundError(f"Predictions file not found: {args.predictions}")
    if not args.base_did_panel.is_file():
        raise FileNotFoundError(
            f"Base DiD panel not found: {args.base_did_panel}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    summary = analyze(
        predictions_path=args.predictions,
        base_did_panel_path=args.base_did_panel,
        output_dir=args.output_dir,
        qc_dir=args.qc_dir,
        min_function_lines=args.min_function_lines,
        max_function_lines=args.max_function_lines,
        expected_base_rows=args.expected_base_rows,
    )

    print("=" * 76)
    print("Prepare AGC commit-function line-range DiD inputs")
    print(f"Status:                       {summary['status']}")
    print(
        "Function line range:          "
        f"{summary['min_function_lines_inclusive']}-"
        f"{summary['max_function_lines_inclusive']} inclusive"
    )
    print(f"Design status:                {summary['analysis_design_status']}")
    print(f"Base panel rows:              {summary['base_panel_rows']}")
    print(f"Selected function events:     {summary['selected_events']}")
    print(f"Selected AGC-like events:     {summary['selected_agc_events']}")
    print(f"Selected HWC-like events:     {summary['selected_hwc_events']}")
    print(f"Full panel rows:              {summary['full_panel_rows']}")
    print(f"Ratio-positive rows:          {summary['ratio_positive_rows']}")
    print(f"Parse-clean full rows:        {summary['parse_clean_full_rows']}")
    print(
        "Parse-clean ratio rows:       "
        f"{summary['parse_clean_ratio_positive_rows']}"
    )
    print(f"Full panel:                   {summary['outputs']['full_panel']}")
    print(
        "Ratio-positive panel:         "
        f"{summary['outputs']['ratio_positive_panel']}"
    )
    print(f"Checks:                       {summary['outputs']['checks']}")
    print(f"Summary:                      {summary['outputs']['summary']}")
    print("=" * 76)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
