#!/usr/bin/env python3
"""Analyze source-line-span distributions for commit-function AGC events.

This script is diagnostic only. It reads the existing event-level classifier
predictions, computes each function event's inclusive source-line span as

    function_line_count = end_line - start_line + 1

and writes descriptive distribution summaries. It does not filter predictions,
re-aggregate repository-month outcomes, or modify any run-py-5d/5e/5f result.

The line span includes decorators when the upstream extractor included them in
start_line, as well as multiline signatures, docstrings, blank lines, and the
function body. It is therefore a source-span measure, not executable LOC.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PREDICTIONS_REQUIRED_COLUMNS = [
    "function_event_id",
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "analysis_status",
    "predicted_agc",
    "predicted_hwc",
    "start_line",
    "end_line",
]

PANEL_REQUIRED_COLUMNS = ["dataset_source", "repo_name", "time", "time_to_event"]

DEFAULT_THRESHOLDS = [1, 2, 3, 4, 5, 6, 10, 20]
DEFAULT_PRIMARY_MIN_LINES = 6

LINE_BINS = [
    (1, 2, "1"),
    (2, 3, "2"),
    (3, 4, "3"),
    (4, 6, "4-5"),
    (6, 11, "6-10"),
    (11, 21, "11-20"),
    (21, 51, "21-50"),
    (51, 101, "51-100"),
    (101, 201, "101-200"),
    (201, None, ">=201"),
]

KEY_COLUMNS = ["dataset_source", "repo_name", "time"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Describe inclusive source-line spans for commit-function AGC "
            "prediction events without filtering downstream panels."
        )
    )
    parser.add_argument("--predictions", type=Path, required=False)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=False)
    parser.add_argument("--qc-dir", type=Path, required=False)
    parser.add_argument(
        "--thresholds",
        type=int,
        nargs="+",
        default=DEFAULT_THRESHOLDS,
        help=(
            "Minimum inclusive function-line thresholds to summarize. "
            "For example, threshold 6 excludes functions spanning 1-5 lines."
        ),
    )
    parser.add_argument(
        "--primary-min-lines",
        type=int,
        default=DEFAULT_PRIMARY_MIN_LINES,
        help=(
            "Threshold highlighted as the primary candidate. The default 6 "
            "means that functions spanning 5 lines or fewer would be excluded."
        ),
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def add_check(
    checks: list[dict[str, Any]], name: str, passed: bool, observed: Any
) -> None:
    checks.append({"check": name, "passed": bool(passed), "observed": observed})


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def normalize_thresholds(thresholds: list[int], primary: int) -> list[int]:
    values = sorted(set(thresholds + [primary]))
    if not values or any(value < 1 for value in values):
        raise ValueError("All minimum-line thresholds must be positive integers")
    return values


def assign_line_bin(line_count: pd.Series) -> pd.Series:
    labels = pd.Series(pd.NA, index=line_count.index, dtype="object")
    for lower, upper, label in LINE_BINS:
        if upper is None:
            mask = line_count >= lower
        else:
            mask = (line_count >= lower) & (line_count < upper)
        labels.loc[mask] = label
    return labels


def build_exact_distribution(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events.groupby("function_line_count", dropna=False)
        .agg(
            events=("function_event_id", "size"),
            agc_events=("predicted_agc", "sum"),
            hwc_events=("predicted_hwc", "sum"),
            repositories=("repo_name", "nunique"),
        )
        .reset_index()
        .sort_values("function_line_count")
        .reset_index(drop=True)
    )
    total = int(grouped["events"].sum())
    grouped["share_of_total"] = grouped["events"] / total if total else pd.NA
    grouped["cumulative_events_le"] = grouped["events"].cumsum()
    grouped["cumulative_share_le"] = (
        grouped["cumulative_events_le"] / total if total else pd.NA
    )
    grouped["agc_ratio"] = grouped["agc_events"] / grouped["events"]
    return grouped


def build_grouped_distribution(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events.groupby("line_size_bin", dropna=False)
        .agg(
            events=("function_event_id", "size"),
            agc_events=("predicted_agc", "sum"),
            hwc_events=("predicted_hwc", "sum"),
            min_line_count=("function_line_count", "min"),
            max_line_count=("function_line_count", "max"),
            median_line_count=("function_line_count", "median"),
        )
        .reset_index()
    )
    bin_order = [label for _, _, label in LINE_BINS]
    grouped["line_size_bin"] = pd.Categorical(
        grouped["line_size_bin"], categories=bin_order, ordered=True
    )
    grouped = grouped.sort_values("line_size_bin").reset_index(drop=True)
    total = int(grouped["events"].sum())
    grouped["share_of_total"] = grouped["events"] / total if total else pd.NA
    grouped["agc_ratio"] = grouped["agc_events"] / grouped["events"]
    return grouped


def describe_line_counts(
    events: pd.DataFrame, dataset_source: str, prediction_group: str
) -> dict[str, Any]:
    selected = events
    if dataset_source != "all":
        selected = selected.loc[selected["dataset_source"].eq(dataset_source)]
    if prediction_group == "agc":
        selected = selected.loc[selected["predicted_agc"].eq(1)]
    elif prediction_group == "hwc":
        selected = selected.loc[selected["predicted_hwc"].eq(1)]

    values = selected["function_line_count"]
    row: dict[str, Any] = {
        "dataset_source": dataset_source,
        "prediction_group": prediction_group,
        "events": int(len(selected)),
        "repositories": int(selected["repo_name"].nunique()),
        "repo_months": int(selected[KEY_COLUMNS].drop_duplicates().shape[0]),
    }
    if values.empty:
        for column in [
            "mean",
            "std",
            "min",
            "p01",
            "p05",
            "p10",
            "p25",
            "p50",
            "p75",
            "p90",
            "p95",
            "p99",
            "max",
        ]:
            row[column] = pd.NA
        return row

    quantiles = values.quantile([0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    row.update(
        {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
            "min": int(values.min()),
            "p01": float(quantiles.loc[0.01]),
            "p05": float(quantiles.loc[0.05]),
            "p10": float(quantiles.loc[0.10]),
            "p25": float(quantiles.loc[0.25]),
            "p50": float(quantiles.loc[0.50]),
            "p75": float(quantiles.loc[0.75]),
            "p90": float(quantiles.loc[0.90]),
            "p95": float(quantiles.loc[0.95]),
            "p99": float(quantiles.loc[0.99]),
            "max": int(values.max()),
        }
    )
    return row


def build_descriptive_summary(events: pd.DataFrame) -> pd.DataFrame:
    sources = ["all", *sorted(events["dataset_source"].dropna().unique())]
    rows = [
        describe_line_counts(events, source, group)
        for source in sources
        for group in ["all", "agc", "hwc"]
    ]
    return pd.DataFrame(rows)


def threshold_row(
    group: pd.DataFrame,
    threshold: int,
    primary: int,
    grouping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retained = group.loc[group["function_line_count"] >= threshold]
    total_events = int(len(group))
    retained_events = int(len(retained))
    total_agc = int(group["predicted_agc"].sum())
    total_hwc = int(group["predicted_hwc"].sum())
    retained_agc = int(retained["predicted_agc"].sum())
    retained_hwc = int(retained["predicted_hwc"].sum())
    row = {
        "min_function_lines": threshold,
        "excluded_line_span_max": threshold - 1,
        "is_primary": threshold == primary,
        "total_events": total_events,
        "retained_events": retained_events,
        "dropped_events": total_events - retained_events,
        "retained_share": retained_events / total_events if total_events else pd.NA,
        "retained_agc_events": retained_agc,
        "retained_hwc_events": retained_hwc,
        "dropped_agc_events": total_agc - retained_agc,
        "dropped_hwc_events": total_hwc - retained_hwc,
        "retained_agc_ratio": retained_agc / retained_events if retained_events else pd.NA,
        "retained_repositories": int(retained["repo_name"].nunique()),
        "retained_repo_months": int(retained[KEY_COLUMNS].drop_duplicates().shape[0]),
    }
    if grouping:
        row = {**grouping, **row}
    return row


def build_threshold_summary(
    events: pd.DataFrame, thresholds: list[int], primary: int
) -> pd.DataFrame:
    return pd.DataFrame(
        [threshold_row(events, threshold, primary) for threshold in thresholds]
    )


def build_by_treatment(
    events: pd.DataFrame, thresholds: list[int], primary: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dataset_source, group in events.groupby("dataset_source", dropna=False):
        for threshold in thresholds:
            rows.append(
                threshold_row(
                    group,
                    threshold,
                    primary,
                    {"dataset_source": dataset_source},
                )
            )
    return pd.DataFrame(rows)


def attach_treatment_period(events: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    panel_minimal = panel[PANEL_REQUIRED_COLUMNS].drop_duplicates()
    duplicate_keys = panel_minimal.duplicated(KEY_COLUMNS, keep=False)
    if duplicate_keys.any():
        conflicting = (
            panel_minimal.loc[duplicate_keys]
            .groupby(KEY_COLUMNS, dropna=False)["time_to_event"]
            .nunique(dropna=False)
        )
        if conflicting.gt(1).any():
            raise ValueError(
                "Panel contains conflicting time_to_event values for the same "
                "dataset_source/repo_name/time key"
            )
        panel_minimal = panel_minimal.drop_duplicates(KEY_COLUMNS)

    merged = events.merge(
        panel_minimal,
        on=KEY_COLUMNS,
        how="left",
        validate="many_to_one",
        indicator="panel_merge_status",
    )
    merged["panel_matched"] = merged["panel_merge_status"].eq("both")
    merged = merged.drop(columns=["panel_merge_status"])

    period = pd.Series("control", index=merged.index, dtype="object")
    treatment_mask = merged["dataset_source"].eq("treatment")
    event_time = pd.to_numeric(merged["time_to_event"], errors="coerce")
    period.loc[treatment_mask & event_time.lt(0)] = "pre"
    period.loc[treatment_mask & event_time.eq(0)] = "event"
    period.loc[treatment_mask & event_time.gt(0)] = "post"
    period.loc[~merged["panel_matched"]] = "unmatched"
    merged["treatment_period"] = period
    return merged


def build_by_period(
    events: pd.DataFrame, thresholds: list[int], primary: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for treatment_period, group in events.groupby("treatment_period", dropna=False):
        for threshold in thresholds:
            rows.append(
                threshold_row(
                    group,
                    threshold,
                    primary,
                    {"treatment_period": treatment_period},
                )
            )
    return pd.DataFrame(rows)


def build_repo_month_impact_preview(
    events: pd.DataFrame, thresholds: list[int], primary: int
) -> pd.DataFrame:
    baseline_repo_months = int(events[KEY_COLUMNS].drop_duplicates().shape[0])
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        retained = events.loc[events["function_line_count"] >= threshold]
        retained_repo_months = int(retained[KEY_COLUMNS].drop_duplicates().shape[0])
        rows.append(
            {
                "min_function_lines": threshold,
                "excluded_line_span_max": threshold - 1,
                "is_primary": threshold == primary,
                "baseline_event_positive_repo_months": baseline_repo_months,
                "retained_event_positive_repo_months": retained_repo_months,
                "newly_zero_eligible_repo_months": baseline_repo_months
                - retained_repo_months,
            }
        )
    return pd.DataFrame(rows)


def analyze(
    predictions_path: Path,
    panel_path: Path | None,
    output_dir: Path,
    qc_dir: Path,
    thresholds: list[int],
    primary_min_lines: int,
) -> dict[str, Any]:
    thresholds = normalize_thresholds(thresholds, primary_min_lines)
    predictions = pd.read_csv(predictions_path, low_memory=False)
    require_columns(predictions, PREDICTIONS_REQUIRED_COLUMNS, "Predictions file")

    checks: list[dict[str, Any]] = []
    total_rows = int(len(predictions))
    duplicate_ids = int(predictions["function_event_id"].duplicated().sum())
    add_check(checks, "function_event_id_unique", duplicate_ids == 0, duplicate_ids)
    add_check(
        checks,
        "analysis_status_nonmissing",
        bool(predictions["analysis_status"].notna().all()),
        int(predictions["analysis_status"].isna().sum()),
    )

    events = predictions.loc[predictions["analysis_status"].eq("ok")].copy()
    ok_rows = int(len(events))
    non_ok_rows = total_rows - ok_rows
    add_check(
        checks,
        "ok_events_positive",
        ok_rows > 0,
        {"total_rows": total_rows, "ok_rows": ok_rows, "non_ok_rows": non_ok_rows},
    )

    for column in ["start_line", "end_line", "predicted_agc", "predicted_hwc"]:
        events[column] = pd.to_numeric(events[column], errors="coerce")

    add_check(
        checks,
        "start_line_nonmissing_for_ok_events",
        bool(events["start_line"].notna().all()),
        int(events["start_line"].isna().sum()),
    )
    add_check(
        checks,
        "end_line_nonmissing_for_ok_events",
        bool(events["end_line"].notna().all()),
        int(events["end_line"].isna().sum()),
    )
    add_check(
        checks,
        "start_and_end_lines_are_integer_valued",
        bool(
            events["start_line"].dropna().mod(1).eq(0).all()
            and events["end_line"].dropna().mod(1).eq(0).all()
        ),
        {
            "noninteger_start_lines": int(
                events["start_line"].dropna().mod(1).ne(0).sum()
            ),
            "noninteger_end_lines": int(
                events["end_line"].dropna().mod(1).ne(0).sum()
            ),
        },
    )

    invalid_span = (
        events["start_line"].isna()
        | events["end_line"].isna()
        | events["start_line"].lt(1)
        | events["end_line"].lt(events["start_line"])
    )
    add_check(
        checks,
        "valid_inclusive_line_spans",
        not bool(invalid_span.any()),
        int(invalid_span.sum()),
    )
    if invalid_span.any():
        sample = events.loc[
            invalid_span,
            ["function_event_id", "start_line", "end_line"],
        ].head(20)
        raise ValueError(
            "OK prediction rows contain invalid start_line/end_line spans:\n"
            + sample.to_string(index=False)
        )

    events["start_line"] = events["start_line"].astype("int64")
    events["end_line"] = events["end_line"].astype("int64")
    events["predicted_agc"] = events["predicted_agc"].astype("int64")
    events["predicted_hwc"] = events["predicted_hwc"].astype("int64")
    events["function_line_count"] = events["end_line"] - events["start_line"] + 1

    add_check(
        checks,
        "function_line_count_positive",
        bool(events["function_line_count"].ge(1).all()),
        int(events["function_line_count"].lt(1).sum()),
    )
    add_check(
        checks,
        "predicted_agc_xor_predicted_hwc",
        bool((events["predicted_agc"] + events["predicted_hwc"]).eq(1).all()),
        int((events["predicted_agc"] + events["predicted_hwc"]).ne(1).sum()),
    )

    events["line_size_bin"] = assign_line_bin(events["function_line_count"])
    add_check(
        checks,
        "every_ok_event_assigned_a_line_size_bin",
        bool(events["line_size_bin"].notna().all()),
        int(events["line_size_bin"].isna().sum()),
    )

    descriptive = build_descriptive_summary(events)
    exact_distribution = build_exact_distribution(events)
    grouped_distribution = build_grouped_distribution(events)
    threshold_summary = build_threshold_summary(events, thresholds, primary_min_lines)
    by_treatment = build_by_treatment(events, thresholds, primary_min_lines)
    repo_month_preview = build_repo_month_impact_preview(
        events, thresholds, primary_min_lines
    )

    ordered = threshold_summary.sort_values("min_function_lines")
    add_check(
        checks,
        "retained_events_monotonic_nonincreasing_in_threshold",
        bool(ordered["retained_events"].is_monotonic_decreasing),
        ordered[["min_function_lines", "retained_events"]].to_dict("records"),
    )
    threshold_one = threshold_summary.loc[
        threshold_summary["min_function_lines"].eq(1)
    ]
    if not threshold_one.empty:
        retained_at_one = int(threshold_one.iloc[0]["retained_events"])
        add_check(
            checks,
            "minimum_one_line_retains_all_ok_events",
            retained_at_one == ok_rows,
            {"retained_at_one": retained_at_one, "ok_rows": ok_rows},
        )

    by_period: pd.DataFrame | None = None
    panel_join_performed = False
    unmatched_events = 0
    if panel_path is not None:
        panel = pd.read_csv(panel_path, low_memory=False)
        require_columns(panel, PANEL_REQUIRED_COLUMNS, "Panel file")
        events_with_period = attach_treatment_period(events, panel)
        by_period = build_by_period(events_with_period, thresholds, primary_min_lines)
        panel_join_performed = True
        unmatched_events = int((~events_with_period["panel_matched"]).sum())
        add_check(
            checks,
            "all_events_matched_to_panel",
            unmatched_events == 0,
            unmatched_events,
        )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    outputs = {
        "descriptive_summary": output_dir
        / "agc_function_event_line_size_descriptive_summary.csv",
        "exact_distribution": output_dir
        / "agc_function_event_line_size_exact_distribution.csv",
        "grouped_distribution": output_dir
        / "agc_function_event_line_size_grouped_distribution.csv",
        "threshold_summary": output_dir
        / "agc_function_event_line_size_threshold_summary.csv",
        "by_treatment": output_dir
        / "agc_function_event_line_size_by_treatment.csv",
        "by_period": output_dir / "agc_function_event_line_size_by_period.csv",
        "repo_month_impact_preview": output_dir
        / "agc_function_event_line_size_repo_month_impact_preview.csv",
        "checks": qc_dir / "agc_function_event_line_size_qc.csv",
        "summary": qc_dir / "agc_function_event_line_size_summary.json",
    }

    atomic_write_csv(descriptive, outputs["descriptive_summary"])
    atomic_write_csv(exact_distribution, outputs["exact_distribution"])
    atomic_write_csv(grouped_distribution, outputs["grouped_distribution"])
    atomic_write_csv(threshold_summary, outputs["threshold_summary"])
    atomic_write_csv(by_treatment, outputs["by_treatment"])
    atomic_write_csv(repo_month_preview, outputs["repo_month_impact_preview"])
    if by_period is not None:
        atomic_write_csv(by_period, outputs["by_period"])
    atomic_write_csv(checks_frame, outputs["checks"])

    primary_row = threshold_summary.loc[
        threshold_summary["min_function_lines"].eq(primary_min_lines)
    ].iloc[0]
    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "line_count_definition": "end_line - start_line + 1",
        "line_count_scope": (
            "Inclusive source span; may include decorators, multiline signature, "
            "docstring, blank lines, and function body."
        ),
        "predictions_path": str(predictions_path),
        "panel_path": str(panel_path) if panel_path is not None else None,
        "panel_join_performed": panel_join_performed,
        "unmatched_events": unmatched_events,
        "total_rows": total_rows,
        "ok_rows": ok_rows,
        "non_ok_rows": non_ok_rows,
        "analysis_status_counts": predictions["analysis_status"]
        .value_counts(dropna=False)
        .to_dict(),
        "thresholds_evaluated": thresholds,
        "primary_min_function_lines": primary_min_lines,
        "primary_excludes_line_spans_at_most": primary_min_lines - 1,
        "primary_retained_events": int(primary_row["retained_events"]),
        "primary_dropped_events": int(primary_row["dropped_events"]),
        "primary_retained_share": float(primary_row["retained_share"]),
        "primary_retained_agc_ratio": (
            float(primary_row["retained_agc_ratio"])
            if pd.notna(primary_row["retained_agc_ratio"])
            else None
        ),
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    atomic_write_json(summary, outputs["summary"])
    return summary


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-line-size-") as temp_dir:
        root = Path(temp_dir)
        spans = [1, 2, 5, 6, 10, 20]
        rows: list[dict[str, Any]] = []
        for index, line_count in enumerate(spans):
            dataset_source = "control" if index < 3 else "treatment"
            repo_name = "owner/tiny_repo" if index < 3 else "owner/normal_repo"
            time = "2024-01" if index < 3 else "2024-02"
            start_line = 10 + index * 30
            rows.append(
                {
                    "function_event_id": f"event_{index}",
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "time": time,
                    "commit": f"c{index}",
                    "analysis_status": "ok",
                    "predicted_agc": index % 2,
                    "predicted_hwc": 1 - (index % 2),
                    "start_line": start_line,
                    "end_line": start_line + line_count - 1,
                }
            )
        rows.append(
            {
                "function_event_id": "failed_event",
                "dataset_source": "treatment",
                "repo_name": "owner/normal_repo",
                "time": "2024-02",
                "commit": "failed",
                "analysis_status": "failed",
                "predicted_agc": 0,
                "predicted_hwc": 0,
                "start_line": "",
                "end_line": "",
            }
        )

        predictions_path = root / "predictions.csv"
        pd.DataFrame(rows).to_csv(predictions_path, index=False)
        panel_path = root / "panel.csv"
        pd.DataFrame(
            [
                {
                    "dataset_source": "control",
                    "repo_name": "owner/tiny_repo",
                    "time": "2024-01",
                    "time_to_event": pd.NA,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/normal_repo",
                    "time": "2024-02",
                    "time_to_event": 0,
                },
            ]
        ).to_csv(panel_path, index=False)

        output_dir = root / "out"
        qc_dir = root / "qc"
        summary = analyze(
            predictions_path=predictions_path,
            panel_path=panel_path,
            output_dir=output_dir,
            qc_dir=qc_dir,
            thresholds=[1, 5, 6, 10],
            primary_min_lines=6,
        )
        if summary["status"] != "PASS":
            raise AssertionError(f"Self-test expected PASS, got {summary}")
        if summary["total_rows"] != 7 or summary["ok_rows"] != 6:
            raise AssertionError("Self-test input row accounting failed")
        if summary["primary_retained_events"] != 3:
            raise AssertionError("Threshold 6 should retain spans 6, 10, and 20")
        if summary["primary_dropped_events"] != 3:
            raise AssertionError("Threshold 6 should drop spans 1, 2, and 5")

        preview = pd.read_csv(outputs_path := output_dir / "agc_function_event_line_size_repo_month_impact_preview.csv")
        primary_preview = preview.loc[preview["min_function_lines"].eq(6)].iloc[0]
        if int(primary_preview["newly_zero_eligible_repo_months"]) != 1:
            raise AssertionError(
                "The tiny control repo-month should become newly zero-eligible"
            )

        exact = pd.read_csv(
            output_dir / "agc_function_event_line_size_exact_distribution.csv"
        )
        if exact["events"].sum() != 6:
            raise AssertionError("Exact distribution must contain all OK events")
        if not outputs_path.is_file():
            raise AssertionError("Expected repo-month preview output is missing")

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    if args.predictions is None or args.output_dir is None or args.qc_dir is None:
        raise SystemExit(
            "--predictions, --output-dir, and --qc-dir are required unless "
            "--self-test is used"
        )
    if not args.predictions.is_file():
        raise FileNotFoundError(f"Missing predictions file: {args.predictions}")
    if args.panel is not None and not args.panel.is_file():
        raise FileNotFoundError(f"Missing panel file: {args.panel}")

    thresholds = normalize_thresholds(args.thresholds, args.primary_min_lines)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("AGC commit-function source-line-span distribution diagnostic")
    print(f"Predictions:                 {args.predictions}")
    print(f"Panel:                       {args.panel if args.panel else '<none>'}")
    print(f"Output directory:            {args.output_dir}")
    print(f"QC directory:                {args.qc_dir}")
    print(f"Thresholds:                  {thresholds}")
    print(f"Primary minimum lines:       {args.primary_min_lines}")
    print(
        "Primary excluded line spans: "
        f"1-{args.primary_min_lines - 1}"
    )
    print("=" * 76)

    summary = analyze(
        predictions_path=args.predictions,
        panel_path=args.panel,
        output_dir=args.output_dir,
        qc_dir=args.qc_dir,
        thresholds=thresholds,
        primary_min_lines=args.primary_min_lines,
    )

    print("=" * 76)
    print(f"Status:                         {summary['status']}")
    print(f"Total prediction rows:          {summary['total_rows']}")
    print(f"OK analyzed events:             {summary['ok_rows']}")
    print(f"Non-OK events:                  {summary['non_ok_rows']}")
    print(
        f"Primary >= {summary['primary_min_function_lines']} lines:       "
        f"retained={summary['primary_retained_events']} "
        f"dropped={summary['primary_dropped_events']}"
    )
    print(
        "Primary retained share:        "
        f"{summary['primary_retained_share']:.4%}"
    )
    if summary["primary_retained_agc_ratio"] is not None:
        print(
            "Primary retained AGC ratio:    "
            f"{summary['primary_retained_agc_ratio']:.4%}"
        )
    print(f"Panel join performed:           {summary['panel_join_performed']}")
    for name, path in summary["outputs"].items():
        print(f"{name:30s} {path}")
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
