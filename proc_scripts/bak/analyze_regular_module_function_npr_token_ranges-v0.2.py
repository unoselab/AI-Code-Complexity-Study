#!/usr/bin/env python3
"""Analyze token-range distributions for regular module-level Python functions.

This diagnostic consumes the frozen run-py-7a NPR classifications. It focuses
on synchronous module-level functions (function_kind == "module_function") and
produces both unique-body and event-level distributions.

Why both units are reported
---------------------------
Unique-body distributions describe distinct implementation bodies. Event-level
distributions describe the unit that is expanded into repository-month counts
for the current DiD analysis. Comparing both helps identify whether repeated
body references, token-range composition, or treatment timing may drive an
unexpected DiD result.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_VERSION = "run-py-7d-v2"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
BODY_COLUMN = "function_body_sha256"
TOKEN_COLUMN = "function_body_split_space_token_count"
FUNCTION_KIND_COLUMN = "function_kind"
AGC_COLUMN = "npr_agc_like"
HWC_COLUMN = "npr_hwc_like"

# These bands intentionally match the earlier DetectCodeGPT calibration-range
# pilot. The first band includes 11 integer token counts; the remaining bands
# include 10 each.
PILOT_BANDS = [
    (100, 110, "100-110"),
    (111, 120, "111-120"),
    (121, 130, "121-130"),
    (131, 140, "131-140"),
    (141, 150, "141-150"),
    (151, 160, "151-160"),
    (161, 170, "161-170"),
    (171, 180, "171-180"),
    (181, 190, "181-190"),
    (191, 200, "191-200"),
]
PILOT_BAND_LABELS = [label for _, _, label in PILOT_BANDS]


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze unique-body and event distributions across token ranges "
            "for regular module-level synchronous Python functions."
        )
    )
    parser.add_argument(
        "--event-classifications",
        type=Path,
        default=Path(
            "repo_python/run-py-7a/strict/specifications/range100_200/"
            "agc_commit_function_npr_event_classifications.csv"
        ),
    )
    parser.add_argument(
        "--body-classifications",
        type=Path,
        default=Path(
            "repo_python/run-py-7a/strict/specifications/range100_200/"
            "agc_commit_function_npr_body_classifications.csv"
        ),
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path(
            "repo_python/run-py-4a/strict/"
            "panel_event_monthly_agc_changed_block_py.csv"
        ),
        help=(
            "Matched repository-month panel used only to attach time_to_event "
            "for treatment-period diagnostics."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7d/strict/specifications/range100_200/"
            "regular_module_function_token_ranges"
        ),
    )
    parser.add_argument("--function-kind", default="module_function")
    parser.add_argument("--minimum-body-tokens", type=int, default=100)
    parser.add_argument("--maximum-body-tokens", type=int, default=200)
    parser.add_argument("--expected-event-rows", type=int, default=22360)
    parser.add_argument("--expected-unique-bodies", type=int, default=18673)
    parser.add_argument("--expected-agc-unique-bodies", type=int, default=2463)
    parser.add_argument("--expected-hwc-unique-bodies", type=int, default=16210)
    parser.add_argument("--overwrite-output", action="store_true")
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    label: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValidationError(
            f"{label} is missing required columns: {missing}. "
            f"Available columns: {list(frame.columns)}"
        )


def normalize_sha(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower()


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
    result["time"] = result["time"].str[:7]
    return result


def normalize_binary(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = numeric.isna() | ~numeric.isin([0, 1])
    if invalid.any():
        sample = series.loc[invalid].head(20).tolist()
        raise ValidationError(f"{label} contains non-binary values: {sample}")
    return numeric.astype("int8")


def prepare_output_directory(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {path}. "
                "Use --overwrite-output only after confirming replacement."
            )
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


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
        temporary_path = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temporary_path, path)


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
        temporary_path = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary_path, path)


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
) -> None:
    checks.append(
        {
            "check_name": name,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def assign_pilot_band(tokens: pd.Series) -> pd.Categorical:
    labels = pd.Series(pd.NA, index=tokens.index, dtype="string")
    for lower, upper, label in PILOT_BANDS:
        labels.loc[tokens.between(lower, upper, inclusive="both")] = label
    return pd.Categorical(
        labels,
        categories=PILOT_BAND_LABELS,
        ordered=True,
    )


def derive_treatment_period(frame: pd.DataFrame) -> pd.Series:
    source = frame["dataset_source"].astype("string").str.lower()
    relative = pd.to_numeric(frame["time_to_event"], errors="coerce")
    result = pd.Series("unknown", index=frame.index, dtype="string")
    result.loc[source.eq("control")] = "control"
    treatment = source.eq("treatment")
    result.loc[treatment & relative.lt(0)] = "pre"
    result.loc[treatment & relative.eq(0)] = "event"
    result.loc[treatment & relative.gt(0)] = "post"
    result.loc[treatment & relative.isna()] = "treatment_unknown_time"
    return result


def add_share_columns(frame: pd.DataFrame, total_column: str) -> pd.DataFrame:
    result = frame.copy()
    denominator = pd.to_numeric(result[total_column], errors="coerce")
    result["agc_share_within_range"] = np.where(
        denominator.gt(0), result["agc_count"] / denominator, np.nan
    )
    result["hwc_share_within_range"] = np.where(
        denominator.gt(0), result["hwc_count"] / denominator, np.nan
    )
    return result


def build_band_summary(
    frame: pd.DataFrame,
    unit_column: str,
    total_label: str,
) -> pd.DataFrame:
    grouped = (
        frame.groupby("token_range", observed=False, dropna=False)
        .agg(
            **{
                total_label: (unit_column, "nunique"),
                "agc_count": (
                    AGC_COLUMN,
                    lambda values: int(values.groupby(frame.loc[values.index, unit_column]).max().sum()),
                ),
                "hwc_count": (
                    HWC_COLUMN,
                    lambda values: int(values.groupby(frame.loc[values.index, unit_column]).max().sum()),
                ),
                "mean_function_npr": ("function_npr", "mean"),
                "median_function_npr": ("function_npr", "median"),
            }
        )
        .reset_index()
    )
    grouped["token_range"] = grouped["token_range"].astype("string")
    grouped = add_share_columns(grouped, total_label)
    grand_total = int(grouped[total_label].sum())
    grouped["share_of_all_regular_units"] = np.where(
        grand_total > 0, grouped[total_label] / grand_total, np.nan
    )
    return grouped


def build_unique_body_band_summary(unique_bodies: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        unique_bodies.groupby("token_range", observed=False, dropna=False)
        .agg(
            unique_bodies=(BODY_COLUMN, "size"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
            mean_function_npr=("function_npr", "mean"),
            median_function_npr=("function_npr", "median"),
        )
        .reset_index()
    )
    grouped["token_range"] = grouped["token_range"].astype("string")
    grouped = add_share_columns(grouped, "unique_bodies")
    total = int(grouped["unique_bodies"].sum())
    grouped["share_of_all_regular_unique_bodies"] = np.where(
        total > 0, grouped["unique_bodies"] / total, np.nan
    )
    return grouped


def build_event_band_summary(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events.groupby("token_range", observed=False, dropna=False)
        .agg(
            event_rows=("function_event_id", "size"),
            unique_bodies=(BODY_COLUMN, "nunique"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
            mean_function_npr=("function_npr", "mean"),
            median_function_npr=("function_npr", "median"),
        )
        .reset_index()
    )
    grouped["token_range"] = grouped["token_range"].astype("string")
    grouped = add_share_columns(grouped, "event_rows")
    total = int(grouped["event_rows"].sum())
    grouped["share_of_all_regular_events"] = np.where(
        total > 0, grouped["event_rows"] / total, np.nan
    )
    grouped["event_rows_per_unique_body"] = np.where(
        grouped["unique_bodies"].gt(0),
        grouped["event_rows"] / grouped["unique_bodies"],
        np.nan,
    )
    return grouped


def build_exact_token_summary(
    frame: pd.DataFrame,
    unit: str,
) -> pd.DataFrame:
    if unit == "body":
        grouped = (
            frame.groupby(TOKEN_COLUMN, dropna=False)
            .agg(
                unique_bodies=(BODY_COLUMN, "size"),
                agc_count=(AGC_COLUMN, "sum"),
                hwc_count=(HWC_COLUMN, "sum"),
                mean_function_npr=("function_npr", "mean"),
                median_function_npr=("function_npr", "median"),
            )
            .reset_index()
        )
        return add_share_columns(grouped, "unique_bodies")

    grouped = (
        frame.groupby(TOKEN_COLUMN, dropna=False)
        .agg(
            event_rows=("function_event_id", "size"),
            unique_bodies=(BODY_COLUMN, "nunique"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
            mean_function_npr=("function_npr", "mean"),
            median_function_npr=("function_npr", "median"),
        )
        .reset_index()
    )
    grouped = add_share_columns(grouped, "event_rows")
    grouped["event_rows_per_unique_body"] = np.where(
        grouped["unique_bodies"].gt(0),
        grouped["event_rows"] / grouped["unique_bodies"],
        np.nan,
    )
    return grouped


def build_window_summary(unique_bodies: pd.DataFrame) -> pd.DataFrame:
    return (
        unique_bodies.groupby("n_expected_windows", dropna=False)
        .agg(
            unique_bodies=(BODY_COLUMN, "size"),
            minimum_tokens=(TOKEN_COLUMN, "min"),
            maximum_tokens=(TOKEN_COLUMN, "max"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
            mean_function_npr=("function_npr", "mean"),
            median_function_npr=("function_npr", "median"),
        )
        .reset_index()
        .pipe(add_share_columns, "unique_bodies")
    )


def build_grouped_event_summary(
    events: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    grouped = (
        events.groupby([*group_columns, "token_range"], observed=False, dropna=False)
        .agg(
            event_rows=("function_event_id", "size"),
            unique_bodies=(BODY_COLUMN, "nunique"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
        )
        .reset_index()
    )
    grouped["token_range"] = grouped["token_range"].astype("string")
    return add_share_columns(grouped, "event_rows")


def build_period_totals(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize event rows and distinct bodies for each adoption period."""
    group_columns = ["dataset_source", "treatment_period"]
    event_totals = (
        events.groupby(group_columns, dropna=False)
        .agg(
            event_rows=("function_event_id", "size"),
            agc_event_rows=(AGC_COLUMN, "sum"),
            hwc_event_rows=(HWC_COLUMN, "sum"),
        )
        .reset_index()
    )

    period_bodies = events.drop_duplicates([*group_columns, BODY_COLUMN])
    body_totals = (
        period_bodies.groupby(group_columns, dropna=False)
        .agg(
            unique_bodies=(BODY_COLUMN, "size"),
            agc_unique_bodies=(AGC_COLUMN, "sum"),
            hwc_unique_bodies=(HWC_COLUMN, "sum"),
        )
        .reset_index()
    )

    result = event_totals.merge(
        body_totals,
        on=group_columns,
        how="outer",
        validate="one_to_one",
    )
    result["agc_event_share"] = np.where(
        result["event_rows"].gt(0),
        result["agc_event_rows"] / result["event_rows"],
        np.nan,
    )
    result["agc_unique_body_share"] = np.where(
        result["unique_bodies"].gt(0),
        result["agc_unique_bodies"] / result["unique_bodies"],
        np.nan,
    )
    return result


def build_unique_body_band_by_period(events: pd.DataFrame) -> pd.DataFrame:
    """Count distinct bodies within each period and token band."""
    group_columns = ["dataset_source", "treatment_period", "token_range"]
    period_bodies = events.drop_duplicates(
        ["dataset_source", "treatment_period", BODY_COLUMN]
    )
    grouped = (
        period_bodies.groupby(
            group_columns,
            observed=False,
            dropna=False,
        )
        .agg(
            unique_bodies=(BODY_COLUMN, "size"),
            agc_count=(AGC_COLUMN, "sum"),
            hwc_count=(HWC_COLUMN, "sum"),
            mean_function_npr=("function_npr", "mean"),
            median_function_npr=("function_npr", "median"),
        )
        .reset_index()
    )
    grouped["token_range"] = grouped["token_range"].astype("string")
    grouped = add_share_columns(grouped, "unique_bodies")
    period_denominator = grouped.groupby(
        ["dataset_source", "treatment_period"],
        dropna=False,
    )["unique_bodies"].transform("sum")
    grouped["share_of_period_unique_bodies"] = np.where(
        period_denominator.gt(0),
        grouped["unique_bodies"] / period_denominator,
        np.nan,
    )
    return grouped


def build_treatment_event_time_totals(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize treatment events at each exact relative event month."""
    treatment = events.loc[
        events["dataset_source"].astype("string").str.lower().eq("treatment")
    ].copy()
    treatment["time_to_event"] = pd.to_numeric(
        treatment["time_to_event"],
        errors="raise",
    ).astype("int64")

    event_totals = (
        treatment.groupby("time_to_event", dropna=False)
        .agg(
            event_rows=("function_event_id", "size"),
            agc_event_rows=(AGC_COLUMN, "sum"),
            hwc_event_rows=(HWC_COLUMN, "sum"),
        )
        .reset_index()
    )
    event_time_bodies = treatment.drop_duplicates(["time_to_event", BODY_COLUMN])
    body_totals = (
        event_time_bodies.groupby("time_to_event", dropna=False)
        .agg(
            unique_bodies=(BODY_COLUMN, "size"),
            agc_unique_bodies=(AGC_COLUMN, "sum"),
            hwc_unique_bodies=(HWC_COLUMN, "sum"),
        )
        .reset_index()
    )
    result = event_totals.merge(
        body_totals,
        on="time_to_event",
        how="outer",
        validate="one_to_one",
    )
    result["agc_event_share"] = np.where(
        result["event_rows"].gt(0),
        result["agc_event_rows"] / result["event_rows"],
        np.nan,
    )
    result["agc_unique_body_share"] = np.where(
        result["unique_bodies"].gt(0),
        result["agc_unique_bodies"] / result["unique_bodies"],
        np.nan,
    )
    return result.sort_values("time_to_event").reset_index(drop=True)


def build_event_band_by_event_time(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize treatment event rows by exact event time and token band."""
    treatment = events.loc[
        events["dataset_source"].astype("string").str.lower().eq("treatment")
    ].copy()
    treatment["time_to_event"] = pd.to_numeric(
        treatment["time_to_event"],
        errors="raise",
    ).astype("int64")
    return build_grouped_event_summary(treatment, ["time_to_event"])


def build_pre_post_overlap(events: pd.DataFrame) -> pd.DataFrame:
    """Measure body overlap between pre-adoption and adoption-and-after."""
    treatment = events.loc[
        events["dataset_source"].astype("string").str.lower().eq("treatment")
    ].copy()
    treatment["time_to_event"] = pd.to_numeric(
        treatment["time_to_event"],
        errors="raise",
    )

    rows: list[dict[str, Any]] = []
    classifications = {
        "ALL": pd.Series(True, index=treatment.index),
        "AGC-like": treatment[AGC_COLUMN].eq(1),
        "HWC-like": treatment[HWC_COLUMN].eq(1),
    }
    band_values = ["ALL", *PILOT_BAND_LABELS]

    for classification, class_mask in classifications.items():
        for token_range in band_values:
            if token_range == "ALL":
                band_mask = pd.Series(True, index=treatment.index)
            else:
                band_mask = treatment["token_range"].astype("string").eq(token_range)

            subset = treatment.loc[class_mask & band_mask]
            pre = set(
                subset.loc[subset["time_to_event"].lt(0), BODY_COLUMN].dropna()
            )
            event = set(
                subset.loc[subset["time_to_event"].eq(0), BODY_COLUMN].dropna()
            )
            post = set(
                subset.loc[subset["time_to_event"].gt(0), BODY_COLUMN].dropna()
            )
            adoption_after = event | post

            rows.append(
                {
                    "classification": classification,
                    "token_range": token_range,
                    "pre_unique_bodies": len(pre),
                    "adoption_month_unique_bodies": len(event),
                    "strict_post_unique_bodies": len(post),
                    "adoption_and_after_unique_bodies": len(adoption_after),
                    "pre_only": len(pre - adoption_after),
                    "adoption_and_after_only": len(adoption_after - pre),
                    "observed_in_both": len(pre & adoption_after),
                    "union": len(pre | adoption_after),
                }
            )

    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    require_file(args.event_classifications, "Event classifications")
    require_file(args.body_classifications, "Body classifications")
    require_file(args.panel, "Matched panel")

    if args.minimum_body_tokens != 100 or args.maximum_body_tokens != 200:
        raise ValueError(
            "This v2 diagnostic uses the frozen 100-200 pilot bands. "
            "Use minimum=100 and maximum=200."
        )

    prepare_output_directory(args.output_dir, args.overwrite_output)
    qc_dir = args.output_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    events = normalize_keys(
        pd.read_csv(args.event_classifications, low_memory=False)
    )
    bodies = pd.read_csv(args.body_classifications, low_memory=False)
    panel = normalize_keys(pd.read_csv(args.panel, low_memory=False))

    require_columns(
        events,
        [
            *KEY_COLUMNS,
            "function_event_id",
            BODY_COLUMN,
            TOKEN_COLUMN,
            FUNCTION_KIND_COLUMN,
            AGC_COLUMN,
            HWC_COLUMN,
            "function_npr",
        ],
        "Event classifications",
    )
    require_columns(
        bodies,
        [
            BODY_COLUMN,
            TOKEN_COLUMN,
            "agc_like",
            "hwc_like",
            "function_npr",
            "n_expected_windows",
        ],
        "Body classifications",
    )
    require_columns(panel, [*KEY_COLUMNS, "time_to_event"], "Matched panel")

    checks: list[dict[str, Any]] = []

    events[BODY_COLUMN] = normalize_sha(events[BODY_COLUMN])
    bodies[BODY_COLUMN] = normalize_sha(bodies[BODY_COLUMN])
    events[FUNCTION_KIND_COLUMN] = (
        events[FUNCTION_KIND_COLUMN].astype("string").str.strip().str.lower()
    )

    events[AGC_COLUMN] = normalize_binary(events[AGC_COLUMN], AGC_COLUMN)
    events[HWC_COLUMN] = normalize_binary(events[HWC_COLUMN], HWC_COLUMN)
    bodies["agc_like"] = normalize_binary(bodies["agc_like"], "agc_like")
    bodies["hwc_like"] = normalize_binary(bodies["hwc_like"], "hwc_like")

    for frame, label in [(events, "events"), (bodies, "bodies")]:
        frame[TOKEN_COLUMN] = pd.to_numeric(
            frame[TOKEN_COLUMN], errors="raise"
        ).astype("int64")
        frame["function_npr"] = pd.to_numeric(
            frame["function_npr"], errors="raise"
        )
        out_of_range = int(
            (~frame[TOKEN_COLUMN].between(100, 200, inclusive="both")).sum()
        )
        add_check(
            checks,
            f"{label}_within_range100_200",
            out_of_range == 0,
            out_of_range,
            0,
            "Every analyzed row must remain inside the frozen range100_200 specification.",
        )

    body_duplicates = int(bodies.duplicated(BODY_COLUMN).sum())
    add_check(
        checks,
        "body_classifications_unique_by_sha",
        body_duplicates == 0,
        body_duplicates,
        0,
        "Body classifications must contain one row per SHA-256 body.",
    )
    if body_duplicates:
        raise ValidationError("Body classifications contain duplicate SHA values")

    body_lookup = bodies[
        [
            BODY_COLUMN,
            TOKEN_COLUMN,
            "agc_like",
            "hwc_like",
            "function_npr",
            "n_expected_windows",
        ]
    ].rename(
        columns={
            TOKEN_COLUMN: f"{TOKEN_COLUMN}_body",
            "agc_like": "agc_like_body",
            "hwc_like": "hwc_like_body",
            "function_npr": "function_npr_body",
        }
    )

    regular_events = events.loc[
        events[FUNCTION_KIND_COLUMN].eq(args.function_kind)
    ].copy()
    regular_events = regular_events.merge(
        body_lookup,
        on=BODY_COLUMN,
        how="left",
        validate="many_to_one",
        indicator="body_merge_status",
    )

    unresolved = int(regular_events["body_merge_status"].ne("both").sum())
    add_check(
        checks,
        "all_regular_events_map_to_body_classifications",
        unresolved == 0,
        unresolved,
        0,
        "Every regular-function event must map to one frozen body classification.",
    )
    if unresolved:
        raise ValidationError("Some regular-function events do not map to body rows")

    token_mismatch = int(
        regular_events[TOKEN_COLUMN]
        .ne(regular_events[f"{TOKEN_COLUMN}_body"])
        .sum()
    )
    agc_mismatch = int(
        regular_events[AGC_COLUMN].ne(regular_events["agc_like_body"]).sum()
    )
    hwc_mismatch = int(
        regular_events[HWC_COLUMN].ne(regular_events["hwc_like_body"]).sum()
    )
    npr_mismatch = int(
        (~np.isclose(
            regular_events["function_npr"],
            regular_events["function_npr_body"],
            rtol=0.0,
            atol=1e-12,
        )).sum()
    )
    add_check(
        checks,
        "regular_event_body_token_counts_match",
        token_mismatch == 0,
        token_mismatch,
        0,
        "Event and body token counts must agree.",
    )
    add_check(
        checks,
        "regular_event_body_agc_labels_match",
        agc_mismatch == 0,
        agc_mismatch,
        0,
        "Event and body AGC labels must agree.",
    )
    add_check(
        checks,
        "regular_event_body_hwc_labels_match",
        hwc_mismatch == 0,
        hwc_mismatch,
        0,
        "Event and body HWC labels must agree.",
    )
    add_check(
        checks,
        "regular_event_body_npr_scores_match",
        npr_mismatch == 0,
        npr_mismatch,
        0,
        "Event and body NPR scores must agree.",
    )

    regular_events = regular_events.drop(
        columns=[
            "body_merge_status",
            f"{TOKEN_COLUMN}_body",
            "agc_like_body",
            "hwc_like_body",
            "function_npr_body",
        ]
    )
    regular_events["token_range"] = assign_pilot_band(
        regular_events[TOKEN_COLUMN]
    )

    missing_band_events = int(pd.isna(regular_events["token_range"]).sum())
    add_check(
        checks,
        "all_regular_events_assigned_to_token_band",
        missing_band_events == 0,
        missing_band_events,
        0,
        "Every regular event must map to one frozen pilot token band.",
    )

    regular_hashes = regular_events[BODY_COLUMN].dropna().drop_duplicates()
    unique_bodies = bodies.loc[bodies[BODY_COLUMN].isin(regular_hashes)].copy()
    unique_bodies = unique_bodies.rename(
        columns={"agc_like": AGC_COLUMN, "hwc_like": HWC_COLUMN}
    )
    unique_bodies["token_range"] = assign_pilot_band(unique_bodies[TOKEN_COLUMN])

    body_partition_failures = int(
        (unique_bodies[AGC_COLUMN] + unique_bodies[HWC_COLUMN]).ne(1).sum()
    )
    event_partition_failures = int(
        (regular_events[AGC_COLUMN] + regular_events[HWC_COLUMN]).ne(1).sum()
    )
    add_check(
        checks,
        "regular_unique_body_agc_hwc_partition",
        body_partition_failures == 0,
        body_partition_failures,
        0,
        "Each regular unique body must be exactly AGC-like or HWC-like.",
    )
    add_check(
        checks,
        "regular_event_agc_hwc_partition",
        event_partition_failures == 0,
        event_partition_failures,
        0,
        "Each regular event must be exactly AGC-like or HWC-like.",
    )

    observed_event_rows = int(len(regular_events))
    observed_unique_bodies = int(len(unique_bodies))
    observed_agc_unique = int(unique_bodies[AGC_COLUMN].sum())
    observed_hwc_unique = int(unique_bodies[HWC_COLUMN].sum())

    for name, observed, expected in [
        ("regular_event_rows_match_expected", observed_event_rows, args.expected_event_rows),
        (
            "regular_unique_bodies_match_expected",
            observed_unique_bodies,
            args.expected_unique_bodies,
        ),
        (
            "regular_agc_unique_bodies_match_expected",
            observed_agc_unique,
            args.expected_agc_unique_bodies,
        ),
        (
            "regular_hwc_unique_bodies_match_expected",
            observed_hwc_unique,
            args.expected_hwc_unique_bodies,
        ),
    ]:
        add_check(
            checks,
            name,
            observed == expected,
            observed,
            expected,
            "Observed values must reproduce the prior xrun1 diagnostic.",
        )

    unique_band = build_unique_body_band_summary(unique_bodies)
    event_band = build_event_band_summary(regular_events)
    unique_exact = build_exact_token_summary(unique_bodies, unit="body")
    event_exact = build_exact_token_summary(regular_events, unit="event")
    window_summary = build_window_summary(unique_bodies)
    event_by_source = build_grouped_event_summary(
        regular_events, ["dataset_source"]
    )

    panel_duplicates = int(panel.duplicated(KEY_COLUMNS).sum())
    add_check(
        checks,
        "matched_panel_unique_by_repo_month",
        panel_duplicates == 0,
        panel_duplicates,
        0,
        "Matched panel must have one row per repository-month.",
    )
    if panel_duplicates:
        raise ValidationError("Matched panel contains duplicate repository-month keys")

    timed_events = regular_events.drop(columns=["time_to_event"], errors="ignore").merge(
        panel[[*KEY_COLUMNS, "time_to_event"]],
        on=KEY_COLUMNS,
        how="left",
        validate="many_to_one",
        indicator="panel_merge_status",
    )
    unresolved_panel = int(timed_events["panel_merge_status"].ne("both").sum())
    add_check(
        checks,
        "all_regular_events_map_to_matched_panel",
        unresolved_panel == 0,
        unresolved_panel,
        0,
        "Every regular event must map to the matched repository-month panel.",
    )
    timed_events = timed_events.drop(columns="panel_merge_status")
    timed_events["treatment_period"] = derive_treatment_period(timed_events)

    unresolved_treatment_time = int(
        timed_events["treatment_period"].eq("treatment_unknown_time").sum()
    )
    add_check(
        checks,
        "all_treatment_events_have_event_time",
        unresolved_treatment_time == 0,
        unresolved_treatment_time,
        0,
        "Every treatment regular-function event must have a relative event month.",
    )

    event_by_period = build_grouped_event_summary(
        timed_events, ["dataset_source", "treatment_period"]
    )
    period_totals = build_period_totals(timed_events)
    unique_body_by_period = build_unique_body_band_by_period(timed_events)
    event_time_totals = build_treatment_event_time_totals(timed_events)
    event_band_by_event_time = build_event_band_by_event_time(timed_events)
    pre_post_overlap = build_pre_post_overlap(timed_events)

    period_event_total = int(period_totals["event_rows"].sum())
    add_check(
        checks,
        "period_event_totals_reconstruct_regular_events",
        period_event_total == observed_event_rows,
        period_event_total,
        observed_event_rows,
        "Control, pre, event, and post rows must reconstruct all regular events.",
    )

    treatment_events = timed_events.loc[
        timed_events["dataset_source"].astype("string").str.lower().eq("treatment")
    ]
    treatment_event_total = int(len(treatment_events))
    treatment_period_total = int(
        period_totals.loc[
            period_totals["dataset_source"].astype("string").str.lower().eq("treatment"),
            "event_rows",
        ].sum()
    )
    add_check(
        checks,
        "treatment_pre_event_post_reconstruct_treatment_events",
        treatment_period_total == treatment_event_total,
        treatment_period_total,
        treatment_event_total,
        "Treatment pre, adoption-month, and post rows must reconstruct treatment events.",
    )

    overlap_all = pre_post_overlap.loc[
        pre_post_overlap["classification"].eq("ALL")
        & pre_post_overlap["token_range"].eq("ALL")
    ].iloc[0]
    treatment_unique_total = int(treatment_events[BODY_COLUMN].nunique())
    add_check(
        checks,
        "pre_post_overlap_union_reconstructs_treatment_unique_bodies",
        int(overlap_all["union"]) == treatment_unique_total,
        int(overlap_all["union"]),
        treatment_unique_total,
        "The pre versus adoption-and-after union must equal all treatment unique bodies.",
    )

    unique_quantiles = (
        unique_bodies.groupby(
            unique_bodies[AGC_COLUMN].map({1: "AGC-like", 0: "HWC-like"}),
            dropna=False,
        )[TOKEN_COLUMN]
        .quantile([0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00])
        .rename("token_count")
        .reset_index()
        .rename(columns={AGC_COLUMN: "classification", "level_1": "quantile"})
    )

    outputs = {
        "unique_body_token_bands": args.output_dir
        / "regular_module_function_unique_body_token_band_distribution.csv",
        "event_token_bands": args.output_dir
        / "regular_module_function_event_token_band_distribution.csv",
        "unique_body_exact_tokens": args.output_dir
        / "regular_module_function_unique_body_exact_token_distribution.csv",
        "event_exact_tokens": args.output_dir
        / "regular_module_function_event_exact_token_distribution.csv",
        "unique_body_window_regimes": args.output_dir
        / "regular_module_function_unique_body_window_distribution.csv",
        "event_bands_by_dataset_source": args.output_dir
        / "regular_module_function_event_token_band_by_dataset_source.csv",
        "event_bands_by_treatment_period": args.output_dir
        / "regular_module_function_event_token_band_by_treatment_period.csv",
        "period_totals": args.output_dir
        / "regular_module_function_adoption_period_totals.csv",
        "unique_body_bands_by_treatment_period": args.output_dir
        / "regular_module_function_unique_body_token_band_by_treatment_period.csv",
        "treatment_event_time_totals": args.output_dir
        / "regular_module_function_treatment_event_time_totals.csv",
        "event_bands_by_event_time": args.output_dir
        / "regular_module_function_event_token_band_by_event_time.csv",
        "pre_post_unique_body_overlap": args.output_dir
        / "regular_module_function_unique_body_pre_vs_adoption_after_overlap.csv",
        "unique_body_token_quantiles": args.output_dir
        / "regular_module_function_unique_body_token_quantiles.csv",
        "checks": qc_dir / "regular_module_function_token_range_checks.csv",
        "summary": qc_dir / "regular_module_function_token_range_summary.json",
    }

    atomic_write_csv(unique_band, outputs["unique_body_token_bands"])
    atomic_write_csv(event_band, outputs["event_token_bands"])
    atomic_write_csv(unique_exact, outputs["unique_body_exact_tokens"])
    atomic_write_csv(event_exact, outputs["event_exact_tokens"])
    atomic_write_csv(window_summary, outputs["unique_body_window_regimes"])
    atomic_write_csv(event_by_source, outputs["event_bands_by_dataset_source"])
    atomic_write_csv(event_by_period, outputs["event_bands_by_treatment_period"])
    atomic_write_csv(period_totals, outputs["period_totals"])
    atomic_write_csv(
        unique_body_by_period,
        outputs["unique_body_bands_by_treatment_period"],
    )
    atomic_write_csv(event_time_totals, outputs["treatment_event_time_totals"])
    atomic_write_csv(
        event_band_by_event_time,
        outputs["event_bands_by_event_time"],
    )
    atomic_write_csv(
        pre_post_overlap,
        outputs["pre_post_unique_body_overlap"],
    )
    atomic_write_csv(unique_quantiles, outputs["unique_body_token_quantiles"])

    band_body_total = int(unique_band["unique_bodies"].sum())
    band_event_total = int(event_band["event_rows"].sum())
    add_check(
        checks,
        "unique_body_bands_reconstruct_regular_unique_bodies",
        band_body_total == observed_unique_bodies,
        band_body_total,
        observed_unique_bodies,
        "Token bands must reconstruct all regular unique bodies.",
    )
    add_check(
        checks,
        "event_bands_reconstruct_regular_events",
        band_event_total == observed_event_rows,
        band_event_total,
        observed_event_rows,
        "Token bands must reconstruct all regular event rows.",
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())
    atomic_write_csv(checks_frame, outputs["checks"])

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "script_version": SCRIPT_VERSION,
        "function_kind": args.function_kind,
        "specification": "range100_200",
        "regular_event_rows": observed_event_rows,
        "regular_unique_bodies": observed_unique_bodies,
        "regular_agc_unique_bodies": observed_agc_unique,
        "regular_hwc_unique_bodies": observed_hwc_unique,
        "regular_unique_body_agc_share": (
            observed_agc_unique / observed_unique_bodies
            if observed_unique_bodies
            else None
        ),
        "treatment_regular_event_rows": treatment_event_total,
        "treatment_regular_unique_bodies": treatment_unique_total,
        "failed_checks": int((~checks_frame["passed"]).sum()),
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    atomic_write_json(summary, outputs["summary"])

    print("=" * 80)
    print("run-py-7d: regular module-function NPR token-range diagnostics")
    print("=" * 80)
    print(f"Status:                         {summary['status']}")
    print(f"Regular event rows:             {observed_event_rows}")
    print(f"Regular unique bodies:          {observed_unique_bodies}")
    print(f"AGC-like unique bodies:         {observed_agc_unique}")
    print(f"HWC-like unique bodies:         {observed_hwc_unique}")
    print(
        "AGC share among unique bodies: "
        f"{summary['regular_unique_body_agc_share']:.6f}"
    )
    print(f"Failed checks:                  {summary['failed_checks']}")
    print()
    print("Unique-body distribution by frozen pilot token band")
    print(unique_band.to_string(index=False))
    print()
    print("Unique-body distribution by expected window count")
    print(window_summary.to_string(index=False))
    print()
    print("Regular-function totals by adoption period")
    print(period_totals.to_string(index=False))
    print()
    print("Unique-body overlap: pre versus adoption-and-after")
    print(
        pre_post_overlap.loc[
            pre_post_overlap["token_range"].eq("ALL")
        ].to_string(index=False)
    )
    print()
    print(f"Output directory:               {args.output_dir}")
    print(f"Checks:                         {outputs['checks']}")
    print(f"Summary:                        {outputs['summary']}")
    print("=" * 80)

    if not overall_pass:
        failed = checks_frame.loc[~checks_frame["passed"]]
        print(failed.to_string(index=False))

    return summary


def main() -> int:
    args = parse_args()
    summary = run(args)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
