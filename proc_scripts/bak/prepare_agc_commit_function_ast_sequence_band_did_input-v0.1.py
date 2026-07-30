#!/usr/bin/env python3
"""Prepare repository-month DiD inputs for pre-specified AST sequence token bands.

This script aggregates event-level AGC detector predictions into bounded,
pre-specified AST sequence token bands and merges those outcomes onto the
existing covariate-complete repository-month DiD panel.

Analysis unit
-------------
One event is one named Python function structurally added or modified in one
commit. Repeated changes to the same function in different commits remain
separate function-change events.

AST sequence token definition
-----------------------------
``ast_sequence_token_count`` is the number of whitespace-delimited elements
in the detector's AST traversal sequence. It is not an embedding-model
subword-token count.

Pre-specified bands
-------------------
50-59, 60-69, 70-79, 80-89, 90-99,
100-109, 110-119, 120-129, 130-139, 140-149.

For every repository-month and band:

function_change_events
    = agc_function_change_events + hwc_function_change_events

agc_function_change_event_ratio
    = agc_function_change_events / function_change_events

The ratio remains missing when function_change_events equals zero. Count
outcomes are additionally stored with log1p transformations:

- log1p_function_change_events
- log1p_agc_function_change_events
- log1p_hwc_function_change_events

Outputs
-------
- panel_event_monthly_agc_commit_function_ast_sequence_bands_long.csv
- panel_event_monthly_agc_commit_function_ast_sequence_bands_ratio_positive.csv
- bands/<band>/panel_event_monthly_agc_commit_function_ast_<band>.csv
- bands/<band>/panel_event_monthly_agc_commit_function_ast_<band>_ratio_positive.csv
- agc_commit_function_ast_sequence_band_support.csv
- agc_commit_function_ast_sequence_band_checks.csv
- agc_commit_function_ast_sequence_band_summary.json

All ten bands are prepared and reported. The script does not select a band
based on effect direction or statistical significance.
"""

from __future__ import annotations

import argparse
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
    "ast_sequence_token_count",
]
BASE_PANEL_REQUIRED_COLUMNS = KEY_COLUMNS + [
    "time_to_event",
    "event",
    "post_event",
    "treat",
    "unit_id",
    "calendar_time",
]

BANDS: list[tuple[int, int, str]] = [
    (50, 60, "50-59"),
    (60, 70, "60-69"),
    (70, 80, "70-79"),
    (80, 90, "80-89"),
    (90, 100, "90-99"),
    (100, 110, "100-109"),
    (110, 120, "110-119"),
    (120, 130, "120-129"),
    (130, 140, "130-139"),
    (140, 150, "140-149"),
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

# Existing all-size outcomes are removed before band-specific outcomes are
# attached so downstream models cannot accidentally use the wrong measure.
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
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare bounded AST-sequence-token band panels for "
            "commit-function AGC staggered DiD analysis."
        )
    )
    parser.add_argument("--predictions", type=Path, required=False)
    parser.add_argument("--base-did-panel", type=Path, required=False)
    parser.add_argument("--output-dir", type=Path, required=False)
    parser.add_argument("--qc-dir", type=Path, required=False)
    parser.add_argument("--expected-base-rows", type=int, default=1633)
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


def clean_base_panel(base_panel: pd.DataFrame) -> pd.DataFrame:
    columns_to_drop = [
        column for column in DROP_EXISTING_OUTCOME_COLUMNS if column in base_panel.columns
    ]
    return base_panel.drop(columns=columns_to_drop).copy()


def aggregate_band(
    events: pd.DataFrame,
    lower: int,
    upper: int,
) -> pd.DataFrame:
    selected = events.loc[
        events["ast_sequence_token_count"].ge(lower)
        & events["ast_sequence_token_count"].lt(upper)
    ].copy()

    if selected.empty:
        return pd.DataFrame(
            columns=KEY_COLUMNS
            + [
                "function_change_events",
                "agc_function_change_events",
                "hwc_function_change_events",
            ]
        )

    aggregated = (
        selected.groupby(KEY_COLUMNS, dropna=False)
        .agg(
            function_change_events=("function_event_id", "size"),
            agc_function_change_events=("predicted_agc", "sum"),
            hwc_function_change_events=("predicted_hwc", "sum"),
        )
        .reset_index()
    )
    return aggregated


def build_band_panel(
    base_panel: pd.DataFrame,
    events: pd.DataFrame,
    lower: int,
    upper: int,
    label: str,
) -> pd.DataFrame:
    aggregated = aggregate_band(events, lower, upper)
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
            pd.to_numeric(panel[column], errors="coerce").fillna(0).astype("int64")
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

    panel["ast_sequence_token_lower_bound_inclusive"] = lower
    panel["ast_sequence_token_upper_bound_exclusive"] = upper
    panel["ast_sequence_token_band"] = label
    panel["ast_sequence_token_specification"] = "bounded_band"

    # Recompute ratio readiness because each band has its own denominator.
    if "analysis_ready_paper_ncloc" in panel.columns:
        panel["analysis_ready_ratio_paper_ncloc"] = (
            panel["function_change_events"].gt(0)
            & panel["agc_function_change_event_ratio"].notna()
            & pd.to_numeric(
                panel["analysis_ready_paper_ncloc"], errors="coerce"
            ).eq(1)
        ).astype("int8")
    if "analysis_ready_python_snapshot_ncloc" in panel.columns:
        panel["analysis_ready_ratio_python_snapshot_ncloc"] = (
            panel["function_change_events"].gt(0)
            & panel["agc_function_change_event_ratio"].notna()
            & pd.to_numeric(
                panel["analysis_ready_python_snapshot_ncloc"], errors="coerce"
            ).eq(1)
        ).astype("int8")

    return panel


def build_support_row(panel: pd.DataFrame, lower: int, upper: int, label: str) -> dict[str, Any]:
    positive = panel["function_change_events"].gt(0)
    ratio = panel.loc[positive, "agc_function_change_event_ratio"]
    return {
        "ast_sequence_token_band": label,
        "ast_sequence_token_lower_bound_inclusive": lower,
        "ast_sequence_token_upper_bound_exclusive": upper,
        "repo_months": int(len(panel)),
        "repositories": int(panel["repo_name"].nunique()),
        "control_repo_months": int(panel["dataset_source"].eq("control").sum()),
        "treatment_repo_months": int(panel["dataset_source"].eq("treatment").sum()),
        "event_positive_repo_months": int(positive.sum()),
        "zero_event_repo_months": int((~positive).sum()),
        "event_positive_repositories": int(panel.loc[positive, "repo_name"].nunique()),
        "control_event_positive_repo_months": int(
            (positive & panel["dataset_source"].eq("control")).sum()
        ),
        "treatment_event_positive_repo_months": int(
            (positive & panel["dataset_source"].eq("treatment")).sum()
        ),
        "function_change_events": int(panel["function_change_events"].sum()),
        "agc_function_change_events": int(panel["agc_function_change_events"].sum()),
        "hwc_function_change_events": int(panel["hwc_function_change_events"].sum()),
        "pooled_agc_function_change_event_ratio": (
            float(panel["agc_function_change_events"].sum() / panel["function_change_events"].sum())
            if panel["function_change_events"].sum() > 0
            else None
        ),
        "mean_repo_month_agc_ratio_positive": float(ratio.mean()) if not ratio.empty else None,
        "median_events_per_positive_repo_month": (
            float(panel.loc[positive, "function_change_events"].median())
            if positive.any()
            else None
        ),
    }


def analyze(
    predictions_path: Path,
    base_did_panel_path: Path,
    output_dir: Path,
    qc_dir: Path,
    expected_base_rows: int,
) -> dict[str, Any]:
    predictions = normalize_keys(pd.read_csv(predictions_path, low_memory=False))
    base_panel = normalize_keys(pd.read_csv(base_did_panel_path, low_memory=False))

    require_columns(predictions, PREDICTION_REQUIRED_COLUMNS, "Predictions")
    require_columns(base_panel, BASE_PANEL_REQUIRED_COLUMNS, "Base DiD panel")
    require_unique_keys(base_panel, "Base DiD panel")

    checks: list[dict[str, Any]] = []
    duplicate_event_ids = int(predictions["function_event_id"].duplicated().sum())
    add_check(checks, "function_event_id_unique", duplicate_event_ids == 0, duplicate_event_ids)

    events = predictions.loc[predictions["analysis_status"].eq("ok")].copy()
    events["ast_sequence_token_count"] = pd.to_numeric(
        events["ast_sequence_token_count"], errors="raise"
    )
    events["predicted_agc"] = pd.to_numeric(events["predicted_agc"], errors="raise")
    events["predicted_hwc"] = pd.to_numeric(events["predicted_hwc"], errors="raise")

    add_check(
        checks,
        "all_prediction_rows_scored",
        len(events) == len(predictions),
        {"total": int(len(predictions)), "scored": int(len(events))},
    )
    add_check(
        checks,
        "prediction_agc_hwc_partition",
        bool((events["predicted_agc"] + events["predicted_hwc"]).eq(1).all()),
        int((events["predicted_agc"] + events["predicted_hwc"]).ne(1).sum()),
    )
    add_check(
        checks,
        "base_panel_expected_rows",
        len(base_panel) == expected_base_rows,
        int(len(base_panel)),
    )

    event_keys = events[KEY_COLUMNS].drop_duplicates()
    unmatched_event_keys = event_keys.merge(
        base_panel[KEY_COLUMNS],
        on=KEY_COLUMNS,
        how="left",
        indicator=True,
    )
    unmatched_count = int(unmatched_event_keys["_merge"].ne("both").sum())
    add_check(checks, "all_event_repo_months_in_base_panel", unmatched_count == 0, unmatched_count)

    band_panels: list[pd.DataFrame] = []
    support_rows: list[dict[str, Any]] = []
    band_output_paths: dict[str, dict[str, str]] = {}

    for lower, upper, label in BANDS:
        panel = build_band_panel(base_panel, events, lower, upper, label)
        positive_panel = panel.loc[panel["function_change_events"].gt(0)].copy()
        positive_panel["ratio_sample"] = 1

        arithmetic_failures = int(
            (
                panel["agc_function_change_events"]
                + panel["hwc_function_change_events"]
                != panel["function_change_events"]
            ).sum()
        )
        zero_ratio_nonmissing = int(
            panel.loc[
                panel["function_change_events"].eq(0),
                "agc_function_change_event_ratio",
            ].notna().sum()
        )
        positive_ratio_missing = int(
            panel.loc[
                panel["function_change_events"].gt(0),
                "agc_function_change_event_ratio",
            ].isna().sum()
        )
        ratio_out_of_bounds = int(
            (~positive_panel["agc_function_change_event_ratio"].between(0, 1)).sum()
        )

        add_check(checks, f"{label}_row_count", len(panel) == len(base_panel), int(len(panel)))
        add_check(checks, f"{label}_event_partition", arithmetic_failures == 0, arithmetic_failures)
        add_check(checks, f"{label}_zero_event_ratio_missing", zero_ratio_nonmissing == 0, zero_ratio_nonmissing)
        add_check(checks, f"{label}_positive_event_ratio_nonmissing", positive_ratio_missing == 0, positive_ratio_missing)
        add_check(checks, f"{label}_ratio_bounds", ratio_out_of_bounds == 0, ratio_out_of_bounds)

        band_slug = label.replace("-", "_")
        band_dir = output_dir / "bands" / label
        full_path = band_dir / f"panel_event_monthly_agc_commit_function_ast_{band_slug}.csv"
        ratio_path = band_dir / f"panel_event_monthly_agc_commit_function_ast_{band_slug}_ratio_positive.csv"
        atomic_write_csv(panel, full_path)
        atomic_write_csv(positive_panel, ratio_path)

        band_output_paths[label] = {
            "full_panel": str(full_path),
            "ratio_positive_panel": str(ratio_path),
        }
        band_panels.append(panel)
        support_rows.append(build_support_row(panel, lower, upper, label))

    long_panel = pd.concat(band_panels, ignore_index=True)
    long_ratio_panel = long_panel.loc[long_panel["function_change_events"].gt(0)].copy()
    long_ratio_panel["ratio_sample"] = 1
    support = pd.DataFrame(support_rows)

    expected_long_rows = len(base_panel) * len(BANDS)
    add_check(checks, "long_panel_row_count", len(long_panel) == expected_long_rows, int(len(long_panel)))
    add_check(
        checks,
        "long_panel_unique_repo_month_band_keys",
        not long_panel.duplicated(KEY_COLUMNS + ["ast_sequence_token_band"]).any(),
        int(long_panel.duplicated(KEY_COLUMNS + ["ast_sequence_token_band"]).sum()),
    )
    add_check(
        checks,
        "band_event_totals_match_direct_selection",
        all(
            int(row.function_change_events)
            == int(
                events["ast_sequence_token_count"].ge(int(row.ast_sequence_token_lower_bound_inclusive))
                .mul(events["ast_sequence_token_count"].lt(int(row.ast_sequence_token_upper_bound_exclusive)))
                .sum()
            )
            for row in support.itertuples(index=False)
        ),
        support[["ast_sequence_token_band", "function_change_events"]].to_dict("records"),
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    long_path = output_dir / "panel_event_monthly_agc_commit_function_ast_sequence_bands_long.csv"
    long_ratio_path = output_dir / "panel_event_monthly_agc_commit_function_ast_sequence_bands_ratio_positive.csv"
    support_path = output_dir / "agc_commit_function_ast_sequence_band_support.csv"
    checks_path = qc_dir / "agc_commit_function_ast_sequence_band_checks.csv"
    summary_path = qc_dir / "agc_commit_function_ast_sequence_band_summary.json"

    atomic_write_csv(long_panel, long_path)
    atomic_write_csv(long_ratio_panel, long_ratio_path)
    atomic_write_csv(support, support_path)
    atomic_write_csv(checks_frame, checks_path)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "predictions_path": str(predictions_path),
        "base_did_panel_path": str(base_did_panel_path),
        "base_panel_rows": int(len(base_panel)),
        "bands": [
            {
                "label": label,
                "lower_bound_inclusive": lower,
                "upper_bound_exclusive": upper,
            }
            for lower, upper, label in BANDS
        ],
        "long_panel_rows": int(len(long_panel)),
        "long_ratio_positive_rows": int(len(long_ratio_panel)),
        "outcomes": OUTCOME_COLUMNS,
        "arithmetic": (
            "function_change_events = agc_function_change_events + "
            "hwc_function_change_events"
        ),
        "ratio_definition": (
            "agc_function_change_event_ratio = agc_function_change_events / "
            "function_change_events"
        ),
        "outputs": {
            "long_panel": str(long_path),
            "long_ratio_positive_panel": str(long_ratio_path),
            "support": str(support_path),
            "checks": str(checks_path),
            "band_panels": band_output_paths,
        },
    }
    atomic_write_json(summary, summary_path)
    return summary


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-band-did-") as temp_dir:
        root = Path(temp_dir)
        predictions = pd.DataFrame(
            [
                {
                    "function_event_id": "e1",
                    "dataset_source": "control",
                    "repo_name": "o/c",
                    "time": "2024-01",
                    "analysis_status": "ok",
                    "predicted_agc": 1,
                    "predicted_hwc": 0,
                    "ast_sequence_token_count": 55,
                },
                {
                    "function_event_id": "e2",
                    "dataset_source": "treatment",
                    "repo_name": "o/t",
                    "time": "2024-02",
                    "analysis_status": "ok",
                    "predicted_agc": 0,
                    "predicted_hwc": 1,
                    "ast_sequence_token_count": 64,
                },
                {
                    "function_event_id": "e3",
                    "dataset_source": "treatment",
                    "repo_name": "o/t",
                    "time": "2024-02",
                    "analysis_status": "ok",
                    "predicted_agc": 1,
                    "predicted_hwc": 0,
                    "ast_sequence_token_count": 64,
                },
                {
                    "function_event_id": "e4",
                    "dataset_source": "treatment",
                    "repo_name": "o/t",
                    "time": "2024-02",
                    "analysis_status": "ok",
                    "predicted_agc": 1,
                    "predicted_hwc": 0,
                    "ast_sequence_token_count": 150,
                },
            ]
        )
        base_panel = pd.DataFrame(
            [
                {
                    "dataset_source": "control",
                    "repo_name": "o/c",
                    "time": "2024-01",
                    "time_to_event": pd.NA,
                    "event": pd.NA,
                    "post_event": 0,
                    "treat": 0,
                    "unit_id": "o/c",
                    "calendar_time": "2024-01",
                    "analysis_ready_paper_ncloc": 1,
                    "analysis_ready_python_snapshot_ncloc": 1,
                    "function_change_events": 99,
                    "agc_function_change_events": 99,
                    "hwc_function_change_events": 0,
                    "agc_function_change_event_ratio": 1.0,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "o/t",
                    "time": "2024-02",
                    "time_to_event": 0,
                    "event": "2024-02",
                    "post_event": 1,
                    "treat": 1,
                    "unit_id": "o/t",
                    "calendar_time": "2024-02",
                    "analysis_ready_paper_ncloc": 1,
                    "analysis_ready_python_snapshot_ncloc": 1,
                    "function_change_events": 99,
                    "agc_function_change_events": 99,
                    "hwc_function_change_events": 0,
                    "agc_function_change_event_ratio": 1.0,
                },
            ]
        )

        predictions_path = root / "predictions.csv"
        base_panel_path = root / "base.csv"
        predictions.to_csv(predictions_path, index=False)
        base_panel.to_csv(base_panel_path, index=False)

        summary = analyze(
            predictions_path=predictions_path,
            base_did_panel_path=base_panel_path,
            output_dir=root / "out",
            qc_dir=root / "qc",
            expected_base_rows=2,
        )
        if summary["status"] != "PASS":
            raise AssertionError(summary)

        band_50 = pd.read_csv(
            root
            / "out"
            / "bands"
            / "50-59"
            / "panel_event_monthly_agc_commit_function_ast_50_59.csv"
        )
        control = band_50.loc[band_50["repo_name"].eq("o/c")].iloc[0]
        treatment = band_50.loc[band_50["repo_name"].eq("o/t")].iloc[0]
        if int(control["function_change_events"]) != 1:
            raise AssertionError("Expected one 50-59 event for control")
        if int(treatment["function_change_events"]) != 0:
            raise AssertionError("Expected zero 50-59 events for treatment")
        if pd.notna(treatment["agc_function_change_event_ratio"]):
            raise AssertionError("Zero-event ratio must remain missing")

        band_60 = pd.read_csv(
            root
            / "out"
            / "bands"
            / "60-69"
            / "panel_event_monthly_agc_commit_function_ast_60_69.csv"
        )
        treatment_60 = band_60.loc[band_60["repo_name"].eq("o/t")].iloc[0]
        if int(treatment_60["function_change_events"]) != 2:
            raise AssertionError("Expected two 60-69 events")
        if int(treatment_60["agc_function_change_events"]) != 1:
            raise AssertionError("Expected one AGC event in 60-69")
        if float(treatment_60["agc_function_change_event_ratio"]) != 0.5:
            raise AssertionError("Expected AGC ratio 0.5 in 60-69")

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
    if not args.predictions.is_file():
        raise FileNotFoundError(f"Predictions file not found: {args.predictions}")
    if not args.base_did_panel.is_file():
        raise FileNotFoundError(f"Base DiD panel not found: {args.base_did_panel}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    summary = analyze(
        predictions_path=args.predictions,
        base_did_panel_path=args.base_did_panel,
        output_dir=args.output_dir,
        qc_dir=args.qc_dir,
        expected_base_rows=args.expected_base_rows,
    )

    print("=" * 76)
    print("Prepare AGC commit-function AST sequence band DiD inputs")
    print(f"Status:                    {summary['status']}")
    print(f"Base panel rows:           {summary['base_panel_rows']}")
    print(f"Bands:                     {len(summary['bands'])}")
    print(f"Long panel rows:           {summary['long_panel_rows']}")
    print(f"Ratio-positive rows:       {summary['long_ratio_positive_rows']}")
    print(f"Long panel:                {summary['outputs']['long_panel']}")
    print(f"Ratio-positive panel:      {summary['outputs']['long_ratio_positive_panel']}")
    print(f"Support:                   {summary['outputs']['support']}")
    print(f"Checks:                    {summary['outputs']['checks']}")
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
