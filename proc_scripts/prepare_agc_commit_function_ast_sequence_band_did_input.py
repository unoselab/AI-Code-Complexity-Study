#!/usr/bin/env python3
"""Prepare repository-month DiD inputs for named AST sequence token band sets.

This script re-aggregates event-level AGC detector predictions into bounded
AST sequence token bands and merges the band-specific outcomes onto the
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

Supported band sets
-------------------
``width10_50_149``
    Ten bounded bands: 50-59, 60-69, ..., 140-149. This is the original
    pre-specified narrow-band heterogeneity specification.

``width20_80_139``
    Three bounded bands: 80-99, 100-119, and 120-139. This is a post hoc
    exploratory sensitivity specification that pools adjacent 10-token bands
    to increase repository-month support.

For every repository-month and band:

function_change_events
    = agc_function_change_events + hwc_function_change_events

agc_function_change_event_ratio
    = agc_function_change_events / function_change_events

The ratio remains missing when ``function_change_events`` equals zero. Count
outcomes are additionally stored with log1p transformations:

- log1p_function_change_events
- log1p_agc_function_change_events
- log1p_hwc_function_change_events

The base-panel activity outcomes are preserved and validated:

- commits
- lines_added
- log1p_commits
- log1p_lines_added

The script prepares and reports every band in the requested set. It does not
select a band based on effect direction or statistical significance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

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
    "analysis_ready_paper_ncloc",
    "analysis_ready_python_snapshot_ncloc",
    "commits",
    "lines_added",
    "log1p_commits",
    "log1p_lines_added",
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


@dataclass(frozen=True)
class BandSetDefinition:
    """Immutable definition of one named AST sequence token band set."""

    name: str
    analysis_design_status: str
    description: str
    bands: tuple[tuple[int, int, str], ...]

    @property
    def widths(self) -> tuple[int, ...]:
        return tuple(upper - lower for lower, upper, _ in self.bands)

    @property
    def common_width(self) -> int | None:
        unique_widths = set(self.widths)
        return next(iter(unique_widths)) if len(unique_widths) == 1 else None

    @property
    def lower_bound(self) -> int:
        return self.bands[0][0]

    @property
    def upper_bound_exclusive(self) -> int:
        return self.bands[-1][1]


BAND_SETS: dict[str, BandSetDefinition] = {
    "width10_50_149": BandSetDefinition(
        name="width10_50_149",
        analysis_design_status="pre_specified_heterogeneity",
        description="Ten non-overlapping 10-token bands from 50 through 149.",
        bands=(
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
        ),
    ),
    "width20_80_139": BandSetDefinition(
        name="width20_80_139",
        analysis_design_status="post_hoc_exploratory_sensitivity",
        description="Three non-overlapping 20-token bands from 80 through 139.",
        bands=(
            (80, 100, "80-99"),
            (100, 120, "100-119"),
            (120, 140, "120-139"),
        ),
    ),
}


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
    parser.add_argument(
        "--band-set",
        choices=sorted(BAND_SETS),
        default="width10_50_149",
        help="Named AST sequence token band set to prepare.",
    )
    parser.add_argument("--expected-base-rows", type=int, default=1633)
    parser.add_argument("--list-band-sets", action="store_true")
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


def validate_band_set(definition: BandSetDefinition) -> None:
    if not definition.bands:
        raise ValueError(f"Band set {definition.name!r} contains no bands")

    labels: set[str] = set()
    previous_upper: int | None = None
    for lower, upper, label in definition.bands:
        if lower < 0 or upper <= lower:
            raise ValueError(
                f"Invalid band bounds in {definition.name}: "
                f"lower={lower}, upper={upper}"
            )
        expected_label = f"{lower}-{upper - 1}"
        if label != expected_label:
            raise ValueError(
                f"Band label mismatch in {definition.name}: "
                f"expected {expected_label!r}, observed {label!r}"
            )
        if label in labels:
            raise ValueError(f"Duplicate band label in {definition.name}: {label}")
        labels.add(label)
        if previous_upper is not None and lower != previous_upper:
            raise ValueError(
                f"Bands in {definition.name} must be ordered, contiguous, and "
                f"non-overlapping: previous upper={previous_upper}, lower={lower}"
            )
        previous_upper = upper


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

    return (
        selected.groupby(KEY_COLUMNS, dropna=False)
        .agg(
            function_change_events=("function_event_id", "size"),
            agc_function_change_events=("predicted_agc", "sum"),
            hwc_function_change_events=("predicted_hwc", "sum"),
        )
        .reset_index()
    )


def build_band_panel(
    base_panel: pd.DataFrame,
    events: pd.DataFrame,
    lower: int,
    upper: int,
    label: str,
    definition: BandSetDefinition,
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
    panel["ast_sequence_token_band_set"] = definition.name
    panel["ast_sequence_token_band_width"] = upper - lower
    panel["analysis_design_status"] = definition.analysis_design_status

    # Recompute ratio readiness because each band has its own denominator.
    panel["analysis_ready_ratio_paper_ncloc"] = (
        panel["function_change_events"].gt(0)
        & panel["agc_function_change_event_ratio"].notna()
        & pd.to_numeric(
            panel["analysis_ready_paper_ncloc"], errors="coerce"
        ).eq(1)
    ).astype("int8")
    panel["analysis_ready_ratio_python_snapshot_ncloc"] = (
        panel["function_change_events"].gt(0)
        & panel["agc_function_change_event_ratio"].notna()
        & pd.to_numeric(
            panel["analysis_ready_python_snapshot_ncloc"], errors="coerce"
        ).eq(1)
    ).astype("int8")

    return panel


def build_support_row(
    panel: pd.DataFrame,
    lower: int,
    upper: int,
    label: str,
    definition: BandSetDefinition,
) -> dict[str, Any]:
    positive = panel["function_change_events"].gt(0)
    ratio = panel.loc[positive, "agc_function_change_event_ratio"]
    total_events = int(panel["function_change_events"].sum())
    total_agc = int(panel["agc_function_change_events"].sum())

    return {
        "ast_sequence_token_band_set": definition.name,
        "analysis_design_status": definition.analysis_design_status,
        "ast_sequence_token_band_width": upper - lower,
        "ast_sequence_token_band": label,
        "ast_sequence_token_lower_bound_inclusive": lower,
        "ast_sequence_token_upper_bound_exclusive": upper,
        "repo_months": int(len(panel)),
        "repositories": int(panel["repo_name"].nunique()),
        "control_repo_months": int(panel["dataset_source"].eq("control").sum()),
        "treatment_repo_months": int(
            panel["dataset_source"].eq("treatment").sum()
        ),
        "event_positive_repo_months": int(positive.sum()),
        "zero_event_repo_months": int((~positive).sum()),
        "event_positive_repositories": int(
            panel.loc[positive, "repo_name"].nunique()
        ),
        "control_event_positive_repo_months": int(
            (positive & panel["dataset_source"].eq("control")).sum()
        ),
        "treatment_event_positive_repo_months": int(
            (positive & panel["dataset_source"].eq("treatment")).sum()
        ),
        "function_change_events": total_events,
        "agc_function_change_events": total_agc,
        "hwc_function_change_events": int(
            panel["hwc_function_change_events"].sum()
        ),
        "pooled_agc_function_change_event_ratio": (
            total_agc / total_events if total_events > 0 else None
        ),
        "mean_repo_month_agc_ratio_positive": (
            float(ratio.mean()) if not ratio.empty else None
        ),
        "median_events_per_positive_repo_month": (
            float(panel.loc[positive, "function_change_events"].median())
            if positive.any()
            else None
        ),
    }


def direct_selection_totals(
    events: pd.DataFrame,
    lower: int,
    upper: int,
) -> dict[str, int]:
    selected = events.loc[
        events["ast_sequence_token_count"].ge(lower)
        & events["ast_sequence_token_count"].lt(upper)
    ]
    return {
        "function_change_events": int(len(selected)),
        "agc_function_change_events": int(selected["predicted_agc"].sum()),
        "hwc_function_change_events": int(selected["predicted_hwc"].sum()),
    }


def validate_panel_outcomes(
    panel: pd.DataFrame,
    label: str,
    checks: list[dict[str, Any]],
) -> None:
    positive = panel["function_change_events"].gt(0)
    arithmetic_failures = int(
        (
            panel["agc_function_change_events"]
            + panel["hwc_function_change_events"]
            != panel["function_change_events"]
        ).sum()
    )
    zero_ratio_nonmissing = int(
        panel.loc[~positive, "agc_function_change_event_ratio"].notna().sum()
    )
    positive_ratio_missing = int(
        panel.loc[positive, "agc_function_change_event_ratio"].isna().sum()
    )
    ratio_out_of_bounds = int(
        (~panel.loc[positive, "agc_function_change_event_ratio"].between(0, 1)).sum()
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

    add_check(checks, f"{label}_event_partition", arithmetic_failures == 0, arithmetic_failures)
    add_check(checks, f"{label}_zero_event_ratio_missing", zero_ratio_nonmissing == 0, zero_ratio_nonmissing)
    add_check(checks, f"{label}_positive_event_ratio_nonmissing", positive_ratio_missing == 0, positive_ratio_missing)
    add_check(checks, f"{label}_ratio_bounds", ratio_out_of_bounds == 0, ratio_out_of_bounds)
    add_check(checks, f"{label}_ratio_formula", ratio_formula_mismatch == 0, ratio_formula_mismatch)

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
            f"{label}_{log_column}_matches_raw",
            mismatch == 0,
            mismatch,
        )


def validate_base_activity_outcomes(
    base_panel: pd.DataFrame,
    checks: list[dict[str, Any]],
) -> None:
    for raw_column, log_column in [
        ("commits", "log1p_commits"),
        ("lines_added", "log1p_lines_added"),
    ]:
        raw = pd.to_numeric(base_panel[raw_column], errors="coerce")
        logged = pd.to_numeric(base_panel[log_column], errors="coerce")
        missing = int(raw.isna().sum() + logged.isna().sum())
        negative = int(raw.lt(0).sum())
        mismatch = int(
            (
                ~np.isclose(
                    logged,
                    np.log1p(raw),
                    rtol=0.0,
                    atol=1e-12,
                    equal_nan=False,
                )
            ).sum()
        )
        add_check(checks, f"{raw_column}_activity_values_nonmissing", missing == 0, missing)
        add_check(checks, f"{raw_column}_activity_values_nonnegative", negative == 0, negative)
        add_check(checks, f"{log_column}_matches_raw", mismatch == 0, mismatch)


def analyze(
    predictions_path: Path,
    base_did_panel_path: Path,
    output_dir: Path,
    qc_dir: Path,
    expected_base_rows: int,
    band_set_name: str,
) -> dict[str, Any]:
    definition = BAND_SETS[band_set_name]
    validate_band_set(definition)

    predictions = normalize_keys(pd.read_csv(predictions_path, low_memory=False))
    base_panel = normalize_keys(pd.read_csv(base_did_panel_path, low_memory=False))

    require_columns(predictions, PREDICTION_REQUIRED_COLUMNS, "Predictions")
    require_columns(base_panel, BASE_PANEL_REQUIRED_COLUMNS, "Base DiD panel")
    require_unique_keys(base_panel, "Base DiD panel")

    checks: list[dict[str, Any]] = []
    add_check(checks, "band_set_name_known", band_set_name in BAND_SETS, band_set_name)
    add_check(
        checks,
        "band_set_labels_match_bounds",
        all(label == f"{lower}-{upper - 1}" for lower, upper, label in definition.bands),
        [label for _, _, label in definition.bands],
    )
    add_check(
        checks,
        "band_set_widths_expected",
        definition.common_width in {10, 20},
        definition.widths,
    )

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
        "ast_sequence_token_count_nonnegative",
        bool(events["ast_sequence_token_count"].ge(0).all()),
        int(events["ast_sequence_token_count"].lt(0).sum()),
    )
    add_check(
        checks,
        "base_panel_expected_rows",
        len(base_panel) == expected_base_rows,
        int(len(base_panel)),
    )
    validate_base_activity_outcomes(base_panel, checks)

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

    band_panels: list[pd.DataFrame] = []
    support_rows: list[dict[str, Any]] = []
    band_output_paths: dict[str, dict[str, str]] = {}

    for lower, upper, label in definition.bands:
        panel = build_band_panel(
            base_panel=base_panel,
            events=events,
            lower=lower,
            upper=upper,
            label=label,
            definition=definition,
        )
        positive_panel = panel.loc[panel["function_change_events"].gt(0)].copy()
        positive_panel["ratio_sample"] = 1

        add_check(checks, f"{label}_row_count", len(panel) == len(base_panel), int(len(panel)))
        add_check(
            checks,
            f"{label}_unique_repo_month_keys",
            not panel.duplicated(KEY_COLUMNS).any(),
            int(panel.duplicated(KEY_COLUMNS).sum()),
        )
        validate_panel_outcomes(panel, label, checks)

        direct = direct_selection_totals(events, lower, upper)
        observed = {
            "function_change_events": int(panel["function_change_events"].sum()),
            "agc_function_change_events": int(panel["agc_function_change_events"].sum()),
            "hwc_function_change_events": int(panel["hwc_function_change_events"].sum()),
        }
        add_check(
            checks,
            f"{label}_totals_match_direct_event_selection",
            observed == direct,
            {"observed": observed, "direct": direct},
        )

        band_slug = label.replace("-", "_")
        band_dir = output_dir / "bands" / label
        full_path = (
            band_dir
            / f"panel_event_monthly_agc_commit_function_ast_{band_slug}.csv"
        )
        ratio_path = (
            band_dir
            / f"panel_event_monthly_agc_commit_function_ast_{band_slug}_ratio_positive.csv"
        )
        atomic_write_csv(panel, full_path)
        atomic_write_csv(positive_panel, ratio_path)

        band_output_paths[label] = {
            "full_panel": str(full_path),
            "ratio_positive_panel": str(ratio_path),
        }
        band_panels.append(panel)
        support_rows.append(
            build_support_row(panel, lower, upper, label, definition)
        )

    long_panel = pd.concat(band_panels, ignore_index=True)
    long_ratio_panel = long_panel.loc[
        long_panel["function_change_events"].gt(0)
    ].copy()
    long_ratio_panel["ratio_sample"] = 1
    support = pd.DataFrame(support_rows)

    expected_long_rows = len(base_panel) * len(definition.bands)
    add_check(
        checks,
        "long_panel_row_count",
        len(long_panel) == expected_long_rows,
        {"observed": int(len(long_panel)), "expected": int(expected_long_rows)},
    )
    add_check(
        checks,
        "long_panel_unique_repo_month_band_keys",
        not long_panel.duplicated(KEY_COLUMNS + ["ast_sequence_token_band"]).any(),
        int(
            long_panel.duplicated(
                KEY_COLUMNS + ["ast_sequence_token_band"]
            ).sum()
        ),
    )

    direct_union = direct_selection_totals(
        events,
        definition.lower_bound,
        definition.upper_bound_exclusive,
    )
    support_union = {
        "function_change_events": int(support["function_change_events"].sum()),
        "agc_function_change_events": int(
            support["agc_function_change_events"].sum()
        ),
        "hwc_function_change_events": int(
            support["hwc_function_change_events"].sum()
        ),
    }
    add_check(
        checks,
        "band_set_union_totals_match_direct_event_selection",
        support_union == direct_union,
        {"observed": support_union, "direct": direct_union},
    )

    metadata_columns = [
        "ast_sequence_token_band_set",
        "analysis_design_status",
        "ast_sequence_token_band_width",
    ]
    metadata_consistent = all(
        long_panel[column].nunique(dropna=False) == 1 for column in metadata_columns
    )
    add_check(
        checks,
        "band_set_metadata_constant_in_long_panel",
        metadata_consistent,
        {
            column: long_panel[column].drop_duplicates().tolist()
            for column in metadata_columns
        },
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    long_path = (
        output_dir
        / "panel_event_monthly_agc_commit_function_ast_sequence_bands_long.csv"
    )
    long_ratio_path = (
        output_dir
        / "panel_event_monthly_agc_commit_function_ast_sequence_bands_ratio_positive.csv"
    )
    support_path = output_dir / "agc_commit_function_ast_sequence_band_support.csv"
    checks_path = qc_dir / "agc_commit_function_ast_sequence_band_checks.csv"
    summary_path = qc_dir / "agc_commit_function_ast_sequence_band_summary.json"

    atomic_write_csv(long_panel, long_path)
    atomic_write_csv(long_ratio_panel, long_ratio_path)
    atomic_write_csv(support, support_path)
    atomic_write_csv(checks_frame, checks_path)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "band_set": definition.name,
        "analysis_design_status": definition.analysis_design_status,
        "band_set_description": definition.description,
        "band_width": definition.common_width,
        "predictions_path": str(predictions_path),
        "predictions_sha256": sha256_file(predictions_path),
        "base_did_panel_path": str(base_did_panel_path),
        "base_did_panel_sha256": sha256_file(base_did_panel_path),
        "base_panel_rows": int(len(base_panel)),
        "bands": [
            {
                "label": label,
                "lower_bound_inclusive": lower,
                "upper_bound_exclusive": upper,
            }
            for lower, upper, label in definition.bands
        ],
        "long_panel_rows": int(len(long_panel)),
        "long_ratio_positive_rows": int(len(long_ratio_panel)),
        "outcomes": OUTCOME_COLUMNS,
        "activity_reference_outcomes": [
            "commits",
            "lines_added",
            "log1p_commits",
            "log1p_lines_added",
        ],
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
            "summary": str(summary_path),
            "band_panels": band_output_paths,
        },
    }
    atomic_write_json(summary, summary_path)
    return summary


def build_self_test_inputs(root: Path) -> tuple[Path, Path]:
    predictions = pd.DataFrame(
        [
            # Outside the width20 specification, immediately below the boundary.
            {
                "function_event_id": "e79",
                "dataset_source": "control",
                "repo_name": "o/c",
                "time": "2024-01",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "ast_sequence_token_count": 79,
            },
            # Exact lower boundary and exact final included value for 80-99.
            {
                "function_event_id": "e80",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "ast_sequence_token_count": 80,
            },
            {
                "function_event_id": "e99",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "ast_sequence_token_count": 99,
            },
            # Exact lower boundary and exact final included value for 100-119.
            {
                "function_event_id": "e100",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "ast_sequence_token_count": 100,
            },
            {
                "function_event_id": "e119",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "ast_sequence_token_count": 119,
            },
            # Exact lower boundary and exact final included value for 120-139.
            {
                "function_event_id": "e120",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "ast_sequence_token_count": 120,
            },
            {
                "function_event_id": "e139",
                "dataset_source": "treatment",
                "repo_name": "o/t",
                "time": "2024-02",
                "analysis_status": "ok",
                "predicted_agc": 0,
                "predicted_hwc": 1,
                "ast_sequence_token_count": 139,
            },
            # Outside the width20 specification, exactly at its upper bound.
            {
                "function_event_id": "e140",
                "dataset_source": "control",
                "repo_name": "o/c",
                "time": "2024-01",
                "analysis_status": "ok",
                "predicted_agc": 1,
                "predicted_hwc": 0,
                "ast_sequence_token_count": 140,
            },
        ]
    )

    base_rows = []
    for dataset_source, repo_name, time, treat, event in [
        ("control", "o/c", "2024-01", 0, pd.NA),
        ("treatment", "o/t", "2024-02", 1, "2024-02"),
    ]:
        commits = 3 if treat == 0 else 5
        lines_added = 10 if treat == 0 else 20
        base_rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "time": time,
                "time_to_event": pd.NA if treat == 0 else 0,
                "event": event,
                "post_event": treat,
                "treat": treat,
                "unit_id": repo_name,
                "calendar_time": time,
                "analysis_ready_paper_ncloc": 1,
                "analysis_ready_python_snapshot_ncloc": 1,
                "commits": commits,
                "lines_added": lines_added,
                "log1p_commits": np.log1p(commits),
                "log1p_lines_added": np.log1p(lines_added),
                "function_change_events": 99,
                "agc_function_change_events": 99,
                "hwc_function_change_events": 0,
                "agc_function_change_event_ratio": 1.0,
            }
        )

    predictions_path = root / "predictions.csv"
    base_panel_path = root / "base.csv"
    predictions.to_csv(predictions_path, index=False)
    pd.DataFrame(base_rows).to_csv(base_panel_path, index=False)
    return predictions_path, base_panel_path


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-band-did-v2-") as temp_dir:
        root = Path(temp_dir)
        predictions_path, base_panel_path = build_self_test_inputs(root)

        for band_set_name in BAND_SETS:
            output_dir = root / band_set_name / "out"
            qc_dir = root / band_set_name / "qc"
            summary = analyze(
                predictions_path=predictions_path,
                base_did_panel_path=base_panel_path,
                output_dir=output_dir,
                qc_dir=qc_dir,
                expected_base_rows=2,
                band_set_name=band_set_name,
            )
            if summary["status"] != "PASS":
                raise AssertionError(summary)

        width20_output = root / "width20_80_139" / "out" / "bands"
        for label in ["80-99", "100-119", "120-139"]:
            slug = label.replace("-", "_")
            panel = pd.read_csv(
                width20_output
                / label
                / f"panel_event_monthly_agc_commit_function_ast_{slug}.csv"
            )
            control = panel.loc[panel["repo_name"].eq("o/c")].iloc[0]
            treatment = panel.loc[panel["repo_name"].eq("o/t")].iloc[0]
            if int(control["function_change_events"]) != 0:
                raise AssertionError(f"Expected zero control events in {label}")
            if pd.notna(control["agc_function_change_event_ratio"]):
                raise AssertionError(f"Zero-event ratio must be missing in {label}")
            if int(treatment["function_change_events"]) != 2:
                raise AssertionError(f"Expected two treatment events in {label}")
            if int(treatment["agc_function_change_events"]) != 1:
                raise AssertionError(f"Expected one AGC event in {label}")
            if int(treatment["hwc_function_change_events"]) != 1:
                raise AssertionError(f"Expected one HWC event in {label}")
            if not np.isclose(
                float(treatment["agc_function_change_event_ratio"]), 0.5
            ):
                raise AssertionError(f"Expected AGC ratio 0.5 in {label}")
            if treatment["ast_sequence_token_band_set"] != "width20_80_139":
                raise AssertionError("Band-set metadata mismatch")
            if int(treatment["ast_sequence_token_band_width"]) != 20:
                raise AssertionError("Band-width metadata mismatch")

        width20_summary = json.loads(
            (
                root
                / "width20_80_139"
                / "qc"
                / "agc_commit_function_ast_sequence_band_summary.json"
            ).read_text(encoding="utf-8")
        )
        if width20_summary["long_panel_rows"] != 6:
            raise AssertionError("Expected 2 repository-months x 3 bands = 6 rows")
        if width20_summary["long_ratio_positive_rows"] != 3:
            raise AssertionError("Expected one positive repository-month per band")

    print("Self-test: PASS")


def print_band_sets() -> None:
    for definition in BAND_SETS.values():
        labels = ", ".join(label for _, _, label in definition.bands)
        print(
            f"{definition.name}: {labels} "
            f"[{definition.analysis_design_status}]"
        )


def main() -> int:
    args = parse_args()

    if args.list_band_sets:
        print_band_sets()
        return 0
    if args.self_test:
        self_test()
        return 0

    required = [args.predictions, args.base_did_panel, args.output_dir, args.qc_dir]
    if any(value is None for value in required):
        raise SystemExit(
            "--predictions, --base-did-panel, --output-dir, and --qc-dir "
            "are required unless --self-test or --list-band-sets is used."
        )
    if not args.predictions.is_file():
        raise FileNotFoundError(f"Predictions file not found: {args.predictions}")
    if not args.base_did_panel.is_file():
        raise FileNotFoundError(f"Base DiD panel not found: {args.base_did_panel}")
    if args.expected_base_rows <= 0:
        raise ValueError("--expected-base-rows must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    summary = analyze(
        predictions_path=args.predictions,
        base_did_panel_path=args.base_did_panel,
        output_dir=args.output_dir,
        qc_dir=args.qc_dir,
        expected_base_rows=args.expected_base_rows,
        band_set_name=args.band_set,
    )

    print("=" * 76)
    print("Prepare AGC commit-function AST sequence band DiD inputs")
    print(f"Status:                    {summary['status']}")
    print(f"Band set:                  {summary['band_set']}")
    print(f"Design status:             {summary['analysis_design_status']}")
    print(f"Band width:                {summary['band_width']}")
    print(f"Base panel rows:           {summary['base_panel_rows']}")
    print(f"Bands:                     {len(summary['bands'])}")
    print(f"Long panel rows:           {summary['long_panel_rows']}")
    print(f"Ratio-positive rows:       {summary['long_ratio_positive_rows']}")
    print(f"Long panel:                {summary['outputs']['long_panel']}")
    print(
        "Ratio-positive panel:      "
        f"{summary['outputs']['long_ratio_positive_panel']}"
    )
    print(f"Support:                   {summary['outputs']['support']}")
    print(f"Checks:                    {summary['outputs']['checks']}")
    print(f"Summary:                   {summary['outputs']['summary']}")
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
