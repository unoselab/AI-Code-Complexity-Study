#!/usr/bin/env python3
"""Diagnose AST-sequence-token size distribution for commit-function AGC events.

Purpose
-------
Before applying any minimum function-size filter to the fresh AGC detector
output (450,548 scored commit-function events), this script only measures
the distribution. It does not filter, re-aggregate, or touch run-py-5d/5e/5f
outputs. Its job is purely diagnostic, matching README-0720c-CheckDiD's
explicit instruction that filtering and re-aggregation come as a separate,
later step once a primary threshold is confirmed against real data.

ast_sequence_token_count definition
------------------------------------
This is NOT a CodeT5+ subword tokenizer count. It is the number of
whitespace-delimited elements in the AST traversal string produced by
agc_detector.generate_ast_sequence(), computed with
``len(ast_sequence.split())`` in analyze_did_python_commit_functions.py.
This value is stored before any --max-len truncation is applied to the
CodeT5+ embedding input, so it is unaffected by that truncation and safe to
use for a minimum-size filter.

Separately, agc_detector.embed_text() truncates the CodeT5+ tokenizer input
to --max-len (subword tokens, not AST-sequence tokens). Since subword token
counts are always >= whitespace-token counts for the same text,
ast_sequence_token_count > max-len is a safe (conservative) lower bound for
"this event's embedding was truncated." This script reports that as a
separate diagnostic, independent of the minimum-size question.

Primary candidate (per README-0720c-CheckDiD): ast_sequence_token_count >= 50
Sensitivity candidates: >= 20, >= 100
Diagnostic baseline: no minimum (>= 0)

python -m py_compile proc_scripts/analyze_agc_commit_function_ast_sequence_size.py
python proc_scripts/analyze_agc_commit_function_ast_sequence_size.py --self-test

python proc_scripts/analyze_agc_commit_function_ast_sequence_size.py \
  --predictions ../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/function_event_predictions_all.csv \
  --panel repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv \
  --output-dir repo_python/run-py-5g/strict \
  --qc-dir repo_python/tmp/run-py-5g/strict \
  --max-len 2048

Inputs
------
--predictions   function_event_predictions_all.csv from the fresh full run
                (python_commit_function_detect/.../py312-full-450548-fresh/).
--panel         Optional. A repository-month panel carrying dataset_source,
                repo_name, time, and time_to_event, used only to attach
                treatment_period (control / pre / event / post) to each
                event for the by-period breakdown. If omitted, the
                by-period breakdown is skipped and only the by-dataset-source
                breakdown is produced.

Outputs (under --output-dir)
------------------------------
- agc_function_event_ast_sequence_size_distribution.csv
- agc_function_event_ast_sequence_threshold_summary.csv
- agc_function_event_ast_sequence_size_by_treatment.csv
- agc_function_event_ast_sequence_size_by_period.csv   (only if --panel given)
- agc_function_event_ast_sequence_repo_month_impact_preview.csv
- agc_function_event_ast_sequence_size_qc.csv          (under --qc-dir)
- agc_function_event_ast_sequence_size_summary.json    (under --qc-dir)

This script never fills missing values with 0 and never mutates the input
prediction file. It is read-only with respect to run-py-5f inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

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
    "ast_sequence_character_count",
    "ast_sequence_token_count",
]

PANEL_REQUIRED_COLUMNS = ["dataset_source", "repo_name", "time", "time_to_event"]

SIZE_BINS = [
    (0, 20, "<20"),
    (20, 50, "20-49"),
    (50, 100, "50-99"),
    (100, 200, "100-199"),
    (200, 2048, "200-2047"),
    (2048, None, ">=2048 (subword-truncation lower bound)"),
]

# Primary + sensitivity + diagnostic-baseline thresholds, per README-0720c.
THRESHOLDS = [0, 20, 50, 100]
PRIMARY_THRESHOLD = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose ast_sequence_token_count size distribution for "
            "commit-function AGC detector predictions, without filtering "
            "or re-aggregating any downstream panel."
        )
    )
    parser.add_argument("--predictions", type=Path, required=False)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=False)
    parser.add_argument("--qc-dir", type=Path, required=False)
    parser.add_argument(
        "--max-len",
        type=int,
        default=2048,
        help=(
            "The --max-len value used for the fresh inference run, i.e. the "
            "CodeT5+ subword-token truncation length. Used only to report "
            "the conservative ast_sequence_token_count > max-len lower "
            "bound on truncated events; does not affect the size filter."
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


def require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def assign_size_bin(token_count: pd.Series) -> pd.Series:
    labels = pd.Series(pd.NA, index=token_count.index, dtype="object")
    for lower, upper, label in SIZE_BINS:
        if upper is None:
            mask = token_count >= lower
        else:
            mask = (token_count >= lower) & (token_count < upper)
        labels.loc[mask] = label
    return labels


def build_size_distribution(events: pd.DataFrame) -> pd.DataFrame:
    counted = (
        events.groupby("size_bin", dropna=False)
        .agg(
            events=("function_event_id", "size"),
            agc_events=("predicted_agc", "sum"),
            hwc_events=("predicted_hwc", "sum"),
            min_token_count=("ast_sequence_token_count", "min"),
            max_token_count=("ast_sequence_token_count", "max"),
            median_token_count=("ast_sequence_token_count", "median"),
        )
        .reset_index()
    )
    bin_order = [label for _, _, label in SIZE_BINS]
    counted["size_bin"] = pd.Categorical(
        counted["size_bin"], categories=bin_order, ordered=True
    )
    counted = counted.sort_values("size_bin").reset_index(drop=True)
    total_events = int(len(events))
    counted["share_of_total"] = (
        counted["events"] / total_events if total_events else pd.NA
    )
    return counted


def build_threshold_summary(events: pd.DataFrame) -> pd.DataFrame:
    total_events = int(len(events))
    total_agc = int(events["predicted_agc"].sum())
    total_hwc = int(events["predicted_hwc"].sum())
    rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        retained = events.loc[events["ast_sequence_token_count"] >= threshold]
        retained_events = int(len(retained))
        retained_agc = int(retained["predicted_agc"].sum())
        retained_hwc = int(retained["predicted_hwc"].sum())
        dropped_events = total_events - retained_events
        rows.append(
            {
                "threshold": threshold,
                "is_primary": threshold == PRIMARY_THRESHOLD,
                "retained_events": retained_events,
                "dropped_events": dropped_events,
                "retained_share": (
                    retained_events / total_events if total_events else pd.NA
                ),
                "retained_agc_events": retained_agc,
                "retained_hwc_events": retained_hwc,
                "retained_agc_ratio": (
                    retained_agc / retained_events if retained_events else pd.NA
                ),
                "dropped_agc_events": total_agc - retained_agc,
                "dropped_hwc_events": total_hwc - retained_hwc,
                "retained_repositories": int(
                    retained["repo_name"].nunique() if retained_events else 0
                ),
                "retained_repo_months": int(
                    retained[["dataset_source", "repo_name", "time"]]
                    .drop_duplicates()
                    .shape[0]
                ),
            }
        )
    return pd.DataFrame(rows)


def build_by_treatment(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dataset_source, group in events.groupby("dataset_source"):
        total_events = int(len(group))
        for threshold in THRESHOLDS:
            retained = group.loc[group["ast_sequence_token_count"] >= threshold]
            retained_events = int(len(retained))
            rows.append(
                {
                    "dataset_source": dataset_source,
                    "threshold": threshold,
                    "is_primary": threshold == PRIMARY_THRESHOLD,
                    "total_events": total_events,
                    "retained_events": retained_events,
                    "dropped_events": total_events - retained_events,
                    "retained_share": (
                        retained_events / total_events if total_events else pd.NA
                    ),
                    "retained_agc_events": int(retained["predicted_agc"].sum()),
                    "retained_hwc_events": int(retained["predicted_hwc"].sum()),
                }
            )
    return pd.DataFrame(rows)


def attach_treatment_period(
    events: pd.DataFrame, panel: pd.DataFrame
) -> pd.DataFrame:
    panel_minimal = panel[PANEL_REQUIRED_COLUMNS].drop_duplicates(
        subset=["dataset_source", "repo_name", "time"]
    )
    merged = events.merge(
        panel_minimal,
        on=["dataset_source", "repo_name", "time"],
        how="left",
        validate="many_to_one",
        indicator="panel_merge_status",
    )
    unmatched = int(merged["panel_merge_status"].ne("both").sum())
    if unmatched:
        print(
            f"WARNING: {unmatched} events could not be matched to the panel "
            "on (dataset_source, repo_name, time); their treatment_period "
            "will be 'unmatched'.",
            file=sys.stderr,
        )
    merged = merged.drop(columns=["panel_merge_status"])

    period = pd.Series("control", index=merged.index, dtype="object")
    treatment_mask = merged["dataset_source"].eq("treatment")
    event_time = pd.to_numeric(merged["time_to_event"], errors="coerce")
    period.loc[treatment_mask & event_time.lt(0)] = "pre"
    period.loc[treatment_mask & event_time.eq(0)] = "event"
    period.loc[treatment_mask & event_time.gt(0)] = "post"
    period.loc[treatment_mask & event_time.isna()] = "unmatched"
    merged["treatment_period"] = period
    return merged


def build_by_period(events_with_period: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for treatment_period, group in events_with_period.groupby("treatment_period"):
        total_events = int(len(group))
        for threshold in THRESHOLDS:
            retained = group.loc[group["ast_sequence_token_count"] >= threshold]
            retained_events = int(len(retained))
            rows.append(
                {
                    "treatment_period": treatment_period,
                    "threshold": threshold,
                    "is_primary": threshold == PRIMARY_THRESHOLD,
                    "total_events": total_events,
                    "retained_events": retained_events,
                    "dropped_events": total_events - retained_events,
                    "retained_share": (
                        retained_events / total_events if total_events else pd.NA
                    ),
                    "retained_agc_events": int(retained["predicted_agc"].sum()),
                    "retained_hwc_events": int(retained["predicted_hwc"].sum()),
                }
            )
    return pd.DataFrame(rows)


def build_repo_month_impact_preview(events: pd.DataFrame) -> pd.DataFrame:
    """Preview only: which currently event-positive repository-months would
    become zero-eligible at each threshold. This does not restore or
    re-aggregate anything -- that belongs to the later filtering/
    re-aggregation script, per README-0720c step 7.
    """
    key_columns = ["dataset_source", "repo_name", "time"]
    baseline_positive_repo_months = (
        events[key_columns].drop_duplicates().shape[0]
    )
    rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        retained = events.loc[events["ast_sequence_token_count"] >= threshold]
        retained_repo_months = retained[key_columns].drop_duplicates().shape[0]
        rows.append(
            {
                "threshold": threshold,
                "is_primary": threshold == PRIMARY_THRESHOLD,
                "baseline_event_positive_repo_months": baseline_positive_repo_months,
                "retained_event_positive_repo_months": int(retained_repo_months),
                "newly_zero_eligible_repo_months": int(
                    baseline_positive_repo_months - retained_repo_months
                ),
            }
        )
    return pd.DataFrame(rows)


def analyze(
    predictions_path: Path,
    panel_path: Path | None,
    output_dir: Path,
    qc_dir: Path,
    max_len: int,
) -> dict[str, Any]:
    predictions = pd.read_csv(predictions_path, low_memory=False)
    require_columns(predictions, PREDICTIONS_REQUIRED_COLUMNS, "Predictions file")

    checks: list[dict[str, Any]] = []

    total_rows = int(len(predictions))
    duplicate_ids = int(predictions["function_event_id"].duplicated().sum())
    add_check(checks, "function_event_id_unique", duplicate_ids == 0, duplicate_ids)

    status_counts = predictions["analysis_status"].value_counts(dropna=False)
    add_check(
        checks,
        "analysis_status_values_known",
        bool(set(status_counts.index) <= {"ok", "failed", "error"}),
        status_counts.to_dict(),
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

    events["ast_sequence_token_count"] = pd.to_numeric(
        events["ast_sequence_token_count"], errors="raise"
    )
    add_check(
        checks,
        "ast_sequence_token_count_nonnegative",
        bool(events["ast_sequence_token_count"].ge(0).all()),
        int(events["ast_sequence_token_count"].lt(0).sum()),
    )
    add_check(
        checks,
        "ast_sequence_token_count_nonmissing_for_ok_events",
        bool(events["ast_sequence_token_count"].notna().all()),
        int(events["ast_sequence_token_count"].isna().sum()),
    )

    for column in ["predicted_agc", "predicted_hwc"]:
        events[column] = pd.to_numeric(events[column], errors="raise")
    add_check(
        checks,
        "predicted_agc_xor_predicted_hwc",
        bool((events["predicted_agc"] + events["predicted_hwc"]).eq(1).all()),
        int((events["predicted_agc"] + events["predicted_hwc"]).ne(1).sum()),
    )

    events["size_bin"] = assign_size_bin(events["ast_sequence_token_count"])
    add_check(
        checks,
        "every_ok_event_assigned_a_size_bin",
        bool(events["size_bin"].notna().all()),
        int(events["size_bin"].isna().sum()),
    )

    size_distribution = build_size_distribution(events)
    threshold_summary = build_threshold_summary(events)
    by_treatment = build_by_treatment(events)
    repo_month_impact_preview = build_repo_month_impact_preview(events)

    # Threshold retained-event counts must be monotonically non-increasing
    # as the threshold rises -- this is a structural identity, not just an
    # empirical expectation, so a violation indicates a bug.
    ordered = threshold_summary.sort_values("threshold")
    add_check(
        checks,
        "retained_events_monotonic_nonincreasing_in_threshold",
        bool(ordered["retained_events"].is_monotonic_decreasing),
        ordered[["threshold", "retained_events"]].to_dict("records"),
    )
    zero_threshold_row = threshold_summary.loc[
        threshold_summary["threshold"] == 0
    ].iloc[0]
    add_check(
        checks,
        "zero_threshold_retains_all_ok_events",
        int(zero_threshold_row["retained_events"]) == ok_rows,
        {
            "retained_at_zero": int(zero_threshold_row["retained_events"]),
            "ok_rows": ok_rows,
        },
    )

    # Conservative lower bound on subword-token truncation: whitespace-split
    # AST-sequence tokens are always <= subword tokens for the same text, so
    # this count under-estimates (never over-estimates) how many events were
    # actually truncated by --max-len during embedding.
    truncation_lower_bound = int(
        events["ast_sequence_token_count"].gt(max_len).sum()
    )

    by_period: pd.DataFrame | None = None
    panel_join_performed = False
    if panel_path is not None:
        panel = pd.read_csv(panel_path, low_memory=False)
        require_columns(panel, PANEL_REQUIRED_COLUMNS, "Panel file")
        events_with_period = attach_treatment_period(events, panel)
        by_period = build_by_period(events_with_period)
        panel_join_performed = True
        unmatched_events = int(
            events_with_period["treatment_period"].eq("unmatched").sum()
        )
        add_check(
            checks,
            "all_events_matched_to_panel",
            unmatched_events == 0,
            unmatched_events,
        )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    size_distribution_output = (
        output_dir / "agc_function_event_ast_sequence_size_distribution.csv"
    )
    threshold_summary_output = (
        output_dir / "agc_function_event_ast_sequence_threshold_summary.csv"
    )
    by_treatment_output = (
        output_dir / "agc_function_event_ast_sequence_size_by_treatment.csv"
    )
    by_period_output = (
        output_dir / "agc_function_event_ast_sequence_size_by_period.csv"
    )
    repo_month_preview_output = (
        output_dir
        / "agc_function_event_ast_sequence_repo_month_impact_preview.csv"
    )
    checks_output = qc_dir / "agc_function_event_ast_sequence_size_qc.csv"
    summary_output = qc_dir / "agc_function_event_ast_sequence_size_summary.json"

    atomic_write_csv(size_distribution, size_distribution_output)
    atomic_write_csv(threshold_summary, threshold_summary_output)
    atomic_write_csv(by_treatment, by_treatment_output)
    atomic_write_csv(repo_month_impact_preview, repo_month_preview_output)
    if by_period is not None:
        atomic_write_csv(by_period, by_period_output)
    atomic_write_csv(checks_frame, checks_output)

    primary_row = threshold_summary.loc[
        threshold_summary["threshold"] == PRIMARY_THRESHOLD
    ].iloc[0]

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "predictions_path": str(predictions_path),
        "panel_path": str(panel_path) if panel_path is not None else None,
        "panel_join_performed": panel_join_performed,
        "max_len": max_len,
        "total_rows": total_rows,
        "ok_rows": ok_rows,
        "non_ok_rows": non_ok_rows,
        "primary_threshold": PRIMARY_THRESHOLD,
        "thresholds_evaluated": THRESHOLDS,
        "primary_retained_events": int(primary_row["retained_events"]),
        "primary_dropped_events": int(primary_row["dropped_events"]),
        "primary_retained_share": float(primary_row["retained_share"]),
        "primary_retained_agc_ratio": (
            float(primary_row["retained_agc_ratio"])
            if pd.notna(primary_row["retained_agc_ratio"])
            else None
        ),
        "subword_truncation_lower_bound_events": truncation_lower_bound,
        "outputs": {
            "size_distribution": str(size_distribution_output),
            "threshold_summary": str(threshold_summary_output),
            "by_treatment": str(by_treatment_output),
            "by_period": (
                str(by_period_output) if by_period is not None else None
            ),
            "repo_month_impact_preview": str(repo_month_preview_output),
            "checks": str(checks_output),
            "summary": str(summary_output),
        },
    }
    atomic_write_json(summary, summary_output)
    return summary


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-ast-size-") as temp_dir:
        root = Path(temp_dir)

        rows = []
        # A repository-month with only tiny (excluded-at-50) events.
        for i, token_count in enumerate([1, 5, 15]):
            rows.append(
                {
                    "function_event_id": f"tiny_{i}",
                    "dataset_source": "control",
                    "repo_name": "owner/tiny_repo",
                    "time": "2024-01",
                    "commit": "c1",
                    "analysis_status": "ok",
                    "predicted_agc": 0,
                    "predicted_hwc": 1,
                    "ast_sequence_character_count": token_count * 5,
                    "ast_sequence_token_count": token_count,
                }
            )
        # A repository-month with a healthy mix, including one event above
        # max_len to exercise the truncation lower-bound diagnostic.
        for i, (token_count, agc) in enumerate(
            [(60, 1), (150, 0), (3000, 1)]
        ):
            rows.append(
                {
                    "function_event_id": f"normal_{i}",
                    "dataset_source": "treatment",
                    "repo_name": "owner/normal_repo",
                    "time": "2024-02",
                    "commit": "c2",
                    "analysis_status": "ok",
                    "predicted_agc": agc,
                    "predicted_hwc": 1 - agc,
                    "ast_sequence_character_count": token_count * 5,
                    "ast_sequence_token_count": token_count,
                }
            )
        # A non-"ok" row that must be excluded before any distribution math.
        rows.append(
            {
                "function_event_id": "failed_1",
                "dataset_source": "treatment",
                "repo_name": "owner/normal_repo",
                "time": "2024-02",
                "commit": "c2",
                "analysis_status": "failed",
                "predicted_agc": 0,
                "predicted_hwc": 0,
                "ast_sequence_character_count": 0,
                "ast_sequence_token_count": 0,
            }
        )
        predictions = pd.DataFrame(rows)
        predictions_path = root / "function_event_predictions_all.csv"
        predictions.to_csv(predictions_path, index=False)

        panel = pd.DataFrame(
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
        )
        panel_path = root / "panel.csv"
        panel.to_csv(panel_path, index=False)

        output_dir = root / "out"
        qc_dir = root / "qc"
        summary = analyze(
            predictions_path=predictions_path,
            panel_path=panel_path,
            output_dir=output_dir,
            qc_dir=qc_dir,
            max_len=2048,
        )

        if summary["status"] != "PASS":
            raise AssertionError(f"Self-test expected PASS, got: {summary}")
        if summary["total_rows"] != 7:
            raise AssertionError("Self-test row count mismatch")
        if summary["ok_rows"] != 6:
            raise AssertionError("Self-test ok-row count mismatch")
        if summary["non_ok_rows"] != 1:
            raise AssertionError("Self-test non-ok-row count mismatch")

        # At threshold=50: tiny_repo's 3 events (1,5,15) all drop; normal_repo
        # keeps 60, 150, 3000 -> 3 retained.
        if summary["primary_retained_events"] != 3:
            raise AssertionError(
                f"Expected 3 retained events at threshold=50, "
                f"got {summary['primary_retained_events']}"
            )
        if summary["primary_dropped_events"] != 3:
            raise AssertionError("Expected 3 dropped events at threshold=50")

        # Exactly one event (3000 tokens) exceeds max_len=2048.
        if summary["subword_truncation_lower_bound_events"] != 1:
            raise AssertionError(
                "Expected exactly 1 event above the max_len lower bound"
            )

        threshold_summary = pd.read_csv(
            output_dir / "agc_function_event_ast_sequence_threshold_summary.csv"
        )
        # Retained events must be strictly monotonic non-increasing here:
        # threshold 0 -> 6, 20 -> 5 (drops the 1-token, 5-token events... wait
        # 15 stays at threshold 20? No: 15 < 20, so threshold 20 drops
        # (1, 5, 15) -> retains 3 (60, 150, 3000)). Confirm shape only,
        # exact values are re-derived independently by the impact-preview
        # check below rather than duplicated here.
        if not threshold_summary["retained_events"].is_monotonic_decreasing:
            raise AssertionError(
                "retained_events must be non-increasing across thresholds"
            )

        # tiny_repo (2024-01) has zero retained events at threshold 50,
        # so it must show up as a newly-zero-eligible repository-month.
        preview = pd.read_csv(
            output_dir
            / "agc_function_event_ast_sequence_repo_month_impact_preview.csv"
        )
        primary_preview = preview.loc[preview["threshold"] == 50].iloc[0]
        if primary_preview["newly_zero_eligible_repo_months"] != 1:
            raise AssertionError(
                "Expected exactly 1 newly-zero-eligible repository-month "
                "at threshold=50 (owner/tiny_repo, 2024-01)"
            )

        by_period = pd.read_csv(
            output_dir / "agc_function_event_ast_sequence_size_by_period.csv"
        )
        if "event" not in set(by_period["treatment_period"]):
            raise AssertionError(
                "Expected an 'event' treatment_period row from the panel join"
            )

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    if args.predictions is None or args.output_dir is None or args.qc_dir is None:
        raise SystemExit(
            "--predictions, --output-dir, and --qc-dir are required "
            "unless --self-test is given."
        )

    if not args.predictions.is_file():
        raise FileNotFoundError(f"Missing predictions file: {args.predictions}")
    if args.panel is not None and not args.panel.is_file():
        raise FileNotFoundError(f"Missing panel file: {args.panel}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("AGC commit-function AST-sequence-token size diagnostic")
    print(f"Predictions:       {args.predictions}")
    print(f"Panel:             {args.panel if args.panel else '<none>'}")
    print(f"Output directory:  {args.output_dir}")
    print(f"QC directory:      {args.qc_dir}")
    print(f"Max length:        {args.max_len}")
    print(f"Primary threshold: {PRIMARY_THRESHOLD}")
    print("=" * 72)

    summary = analyze(
        predictions_path=args.predictions,
        panel_path=args.panel,
        output_dir=args.output_dir,
        qc_dir=args.qc_dir,
        max_len=args.max_len,
    )

    print("=" * 72)
    print(f"Status:                          {summary['status']}")
    print(f"Total rows:                      {summary['total_rows']}")
    print(f"OK (analyzed) rows:              {summary['ok_rows']}")
    print(f"Non-OK rows:                     {summary['non_ok_rows']}")
    print(
        f"Primary threshold (>= {summary['primary_threshold']}):"
        f"          retained={summary['primary_retained_events']} "
        f"dropped={summary['primary_dropped_events']}"
    )
    print(
        "Primary retained share:         "
        f"{summary['primary_retained_share']:.4%}"
    )
    if summary["primary_retained_agc_ratio"] is not None:
        print(
            "Primary retained AGC ratio:     "
            f"{summary['primary_retained_agc_ratio']:.4%}"
        )
    print(
        "Subword-truncation lower bound: "
        f"{summary['subword_truncation_lower_bound_events']} events "
        f"(ast_sequence_token_count > {summary['max_len']})"
    )
    print(f"Panel join performed:            {summary['panel_join_performed']}")
    print(f"Size distribution:  {summary['outputs']['size_distribution']}")
    print(f"Threshold summary:  {summary['outputs']['threshold_summary']}")
    print(f"By treatment:       {summary['outputs']['by_treatment']}")
    print(f"By period:          {summary['outputs']['by_period']}")
    print(
        "Repo-month impact preview: "
        f"{summary['outputs']['repo_month_impact_preview']}"
    )
    print(f"Checks:             {summary['outputs']['checks']}")
    print(f"Summary:            {summary['outputs']['summary']}")
    print("=" * 72)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
