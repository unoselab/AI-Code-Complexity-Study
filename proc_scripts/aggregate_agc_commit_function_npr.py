#!/usr/bin/env python3
"""Aggregate function-body NPR scores to event and repository-month outcomes.

This stage consumes frozen DetectCodeGPT outputs from one NPR eligibility
specification and prepares analysis artifacts inside the DiD workspace.
It does not load a language model and does not run a causal model.

Scientific unit
---------------
One approved commit-function change event.

Computational input
-------------------
One scored implementation body identified by SHA-256. A body can be referenced
by multiple commit-function events, so body-level classifications are expanded
back to event rows before repository-month aggregation.

Important interpretation
------------------------
The resulting counts describe NPR-eligible and successfully scored events for
one explicit token-range specification. For example, range100_200 includes
only events whose implementation body has 100-200 literal-space tokens. A
repository-month with zero selected events is therefore not necessarily a
month with zero function-change activity; it can contain function events that
fall outside the selected NPR range.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_VERSION = "run-py-7a-v1"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]

EVENT_REQUIRED_COLUMNS = KEY_COLUMNS + [
    "function_event_id",
    "change_type",
    "function_body_sha256",
    "function_body_split_space_token_count",
    "input_preparation_complete",
    "body_extraction_status",
]

BODY_SCORE_REQUIRED_COLUMNS = [
    "function_body_sha256",
    "function_body_split_space_token_count",
    "n_expected_windows",
    "n_scored_windows",
    "n_attempted_windows",
    "n_valid_npr_windows",
    "n_invalid_npr_windows",
    "valid_npr_token_count",
    "invalid_npr_token_count",
    "partial_body_score",
    "referencing_function_event_count",
    "function_npr",
    "agc_threshold",
    "agc_like",
    "hwc_like",
    "status",
]

MANIFEST_REQUIRED_COLUMNS = [
    "function_body_sha256",
    "function_body_split_space_token_count",
    "n_expected_windows",
    "referencing_function_event_count",
    "selected_for_full_scoring",
]

SOURCE_COUNT_REQUIRED_COLUMNS = KEY_COLUMNS + [
    "function_change_events",
    "added_function_events",
    "modified_function_events",
]

PANEL_REQUIRED_COLUMNS = KEY_COLUMNS + ["time_to_event"]

THRESHOLD_REQUIRED_KEYS = {
    "status",
    "scoring_model",
    "window_size_literal_space_tokens",
    "perturbations_per_window",
    "perturbation_type",
    "function_aggregation",
    "agc_threshold",
    "random_seed",
    "algorithm_version",
    "decision_rule",
    "window_policy",
    "partial_body_policy",
}

NPR_COUNT_COLUMNS = [
    "npr_scored_function_change_events",
    "npr_agc_function_change_events",
    "npr_hwc_function_change_events",
    "npr_added_function_change_events",
    "npr_modified_function_change_events",
    "npr_added_agc_function_change_events",
    "npr_added_hwc_function_change_events",
    "npr_modified_agc_function_change_events",
    "npr_modified_hwc_function_change_events",
    "npr_unique_scored_bodies",
]


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Expand frozen function-body NPR scores to commit-function events "
            "and aggregate them to a complete repository-month panel."
        )
    )
    parser.add_argument("--input-events", type=Path)
    parser.add_argument("--body-scores", type=Path)
    parser.add_argument("--full-manifest", type=Path)
    parser.add_argument("--threshold-specification", type=Path)
    parser.add_argument("--detector-summary", type=Path, default=None)
    parser.add_argument("--detector-metadata", type=Path, default=None)
    parser.add_argument("--source-counts", type=Path)
    parser.add_argument("--panel", type=Path)
    parser.add_argument(
        "--parse-exclusions-by-repo-month",
        type=Path,
        default=None,
        help="Optional parse-exclusion summary keyed by dataset_source/repo_name/time.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--qc-dir", type=Path, default=None)
    parser.add_argument("--specification-name", default="range100_200")
    parser.add_argument("--minimum-body-tokens", type=int, default=100)
    parser.add_argument("--maximum-body-tokens", type=int, default=200)
    parser.add_argument("--expected-panel-rows", type=int, default=1633)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument("--expected-selected-bodies", type=int, default=69231)
    parser.add_argument("--expected-windows", type=int, default=114379)
    parser.add_argument("--expected-partial-body-scores", type=int, default=0)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_file(path: Path | None, label: str) -> Path:
    if path is None:
        raise FileNotFoundError(f"{label} path was not supplied")
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


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


def require_unique(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    duplicate_mask = frame.duplicated(columns, keep=False)
    if duplicate_mask.any():
        sample = frame.loc[duplicate_mask, columns].head(20)
        raise ValidationError(
            f"{label} contains duplicate keys for {columns}:\n"
            f"{sample.to_string(index=False)}"
        )


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        if column in result.columns:
            result[column] = result[column].astype("string").str.strip()
    if "time" in result.columns:
        result["time"] = result["time"].str[:7]
    return result


def normalize_sha(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower()


def normalize_boolean(series: pd.Series) -> pd.Series:
    truthy = {"1", "1.0", "true", "t", "yes", "y"}
    falsy = {"0", "0.0", "false", "f", "no", "n", "", "nan", "none"}

    def convert(value: Any) -> bool | None:
        text = str(value).strip().lower()
        if text in truthy:
            return True
        if text in falsy:
            return False
        return None

    return series.map(convert).astype("boolean")


def normalize_binary(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = numeric.isna() | ~numeric.isin([0, 1])
    if invalid.any():
        sample = series.loc[invalid].head(20).tolist()
        raise ValidationError(f"{label} contains non-binary values: {sample}")
    return numeric.astype("int8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValidationError(f"{label} is not valid JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValidationError(f"{label} must contain a JSON object: {path}")
    return payload


def prepare_output_directories(
    output_dir: Path,
    qc_dir: Path,
    overwrite_output: bool,
) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite_output:
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}. "
                "Use --overwrite-output only after confirming that replacement is safe."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)


def resolve_parse_exclusion_count_column(frame: pd.DataFrame) -> str | None:
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

    candidates = [
        column
        for column in frame.columns
        if column not in KEY_COLUMNS
        and pd.api.types.is_numeric_dtype(frame[column])
        and any(
            token in column.lower()
            for token in ["record", "error", "exclusion"]
        )
    ]
    return candidates[0] if len(candidates) == 1 else None


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


def compare_hash_sets(
    left: pd.Series,
    right: pd.Series,
) -> tuple[set[str], set[str]]:
    left_set = set(normalize_sha(left).dropna().tolist())
    right_set = set(normalize_sha(right).dropna().tolist())
    return left_set - right_set, right_set - left_set


def validate_threshold_specification(payload: dict[str, Any]) -> None:
    missing = sorted(THRESHOLD_REQUIRED_KEYS - set(payload))
    if missing:
        raise ValidationError(
            f"Threshold specification is missing required keys: {missing}"
        )
    if str(payload["decision_rule"]) != "function_npr > agc_threshold":
        raise ValidationError(
            "Unsupported decision rule: " + str(payload["decision_rule"])
        )


def prepare_body_classifications(
    body_scores: pd.DataFrame,
    manifest: pd.DataFrame,
    threshold: dict[str, Any],
    specification_name: str,
    min_tokens: int,
    max_tokens: int,
    checks: list[dict[str, Any]],
) -> pd.DataFrame:
    body_scores = body_scores.copy()
    manifest = manifest.copy()
    body_scores["function_body_sha256"] = normalize_sha(
        body_scores["function_body_sha256"]
    )
    manifest["function_body_sha256"] = normalize_sha(
        manifest["function_body_sha256"]
    )

    require_unique(body_scores, ["function_body_sha256"], "Body scores")
    require_unique(manifest, ["function_body_sha256"], "Full manifest")

    body_only, manifest_only = compare_hash_sets(
        body_scores["function_body_sha256"],
        manifest["function_body_sha256"],
    )
    add_check(
        checks,
        "body_score_and_manifest_hash_sets_match",
        not body_only and not manifest_only,
        {
            "body_scores_only": len(body_only),
            "manifest_only": len(manifest_only),
        },
        {"body_scores_only": 0, "manifest_only": 0},
        "Every selected manifest body must have exactly one body score.",
    )
    if body_only or manifest_only:
        raise ValidationError(
            "Body-score and manifest hash sets differ: "
            f"body_scores_only={len(body_only)}, manifest_only={len(manifest_only)}"
        )

    score_tokens = pd.to_numeric(
        body_scores["function_body_split_space_token_count"], errors="coerce"
    )
    manifest_tokens = pd.to_numeric(
        manifest["function_body_split_space_token_count"], errors="coerce"
    )
    if score_tokens.isna().any() or manifest_tokens.isna().any():
        raise ValidationError("Body token counts contain missing or nonnumeric values")

    body_scores["function_body_split_space_token_count"] = score_tokens.astype(
        "int64"
    )
    manifest["function_body_split_space_token_count"] = manifest_tokens.astype(
        "int64"
    )

    status_success = body_scores["status"].astype("string").str.lower().eq("success")
    add_check(
        checks,
        "all_body_scores_successful",
        bool(status_success.all()),
        int((~status_success).sum()),
        0,
        "Only successful body scores may be expanded to event classifications.",
    )

    function_npr = pd.to_numeric(body_scores["function_npr"], errors="coerce")
    finite_npr = np.isfinite(function_npr.to_numpy(dtype=float))
    add_check(
        checks,
        "all_function_npr_values_finite",
        bool(finite_npr.all()),
        int((~finite_npr).sum()),
        0,
        "Every successful body must have a finite function-level NPR.",
    )

    body_scores["agc_like"] = normalize_binary(body_scores["agc_like"], "agc_like")
    body_scores["hwc_like"] = normalize_binary(body_scores["hwc_like"], "hwc_like")
    classification_partition_failures = int(
        (body_scores["agc_like"] + body_scores["hwc_like"]).ne(1).sum()
    )
    add_check(
        checks,
        "body_agc_hwc_partition",
        classification_partition_failures == 0,
        classification_partition_failures,
        0,
        "Every scored body must be classified as exactly one of AGC-like or HWC-like.",
    )

    expected_threshold = float(threshold["agc_threshold"])
    observed_threshold = pd.to_numeric(
        body_scores["agc_threshold"], errors="coerce"
    )
    threshold_mismatches = int(
        (~np.isclose(observed_threshold, expected_threshold, rtol=0.0, atol=1e-12)).sum()
    )
    add_check(
        checks,
        "body_threshold_matches_frozen_specification",
        threshold_mismatches == 0,
        threshold_mismatches,
        0,
        "Every body score must use the frozen threshold specification.",
    )

    decision_agc = function_npr.gt(expected_threshold).astype("int8")
    decision_mismatches = int(decision_agc.ne(body_scores["agc_like"]).sum())
    add_check(
        checks,
        "body_classification_matches_strict_threshold_rule",
        decision_mismatches == 0,
        decision_mismatches,
        0,
        "AGC-like classification must use function_npr > agc_threshold.",
    )

    token_range_failures = int(
        (~score_tokens.between(min_tokens, max_tokens, inclusive="both")).sum()
    )
    add_check(
        checks,
        "body_scores_within_requested_token_range",
        token_range_failures == 0,
        token_range_failures,
        0,
        "Every body score must satisfy the selected eligibility range.",
    )

    manifest_selected = normalize_boolean(manifest["selected_for_full_scoring"])
    add_check(
        checks,
        "all_manifest_bodies_selected_for_full_scoring",
        bool(manifest_selected.eq(True).all()),
        int(manifest_selected.ne(True).sum()),
        0,
        "The full manifest must contain only selected production bodies.",
    )

    manifest_extra_columns = [
        column
        for column in manifest.columns
        if column not in body_scores.columns
    ]
    combined = body_scores.merge(
        manifest[["function_body_sha256", *manifest_extra_columns]],
        on="function_body_sha256",
        how="inner",
        validate="one_to_one",
    )
    combined["npr_specification"] = specification_name
    combined["npr_minimum_body_tokens_inclusive"] = min_tokens
    combined["npr_maximum_body_tokens_inclusive"] = max_tokens
    combined["npr_algorithm_version"] = str(threshold["algorithm_version"])
    combined["npr_decision_rule"] = str(threshold["decision_rule"])
    combined["npr_window_policy"] = str(threshold["window_policy"])
    combined["npr_function_aggregation"] = str(threshold["function_aggregation"])
    combined["npr_partial_body_policy"] = str(threshold["partial_body_policy"])
    combined["npr_scoring_model"] = str(threshold["scoring_model"])
    combined["npr_window_size_literal_space_tokens"] = int(
        threshold["window_size_literal_space_tokens"]
    )
    combined["npr_perturbations_per_window"] = int(
        threshold["perturbations_per_window"]
    )
    combined["npr_random_seed"] = int(threshold["random_seed"])
    return combined.sort_values("function_body_sha256", kind="mergesort")


def prepare_event_classifications(
    events: pd.DataFrame,
    body_classifications: pd.DataFrame,
    specification_name: str,
    checks: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    events = normalize_keys(events)
    events["function_body_sha256"] = normalize_sha(events["function_body_sha256"])
    events["function_event_id"] = events["function_event_id"].astype("string").str.strip()
    require_unique(events, ["function_event_id"], "Input events")

    preparation_complete = normalize_boolean(events["input_preparation_complete"])
    extraction_prepared = (
        events["body_extraction_status"].astype("string").str.strip().str.lower().eq("prepared")
    )
    prepared_events = events.loc[
        preparation_complete.eq(True) & extraction_prepared
    ].copy()

    selected_hashes = set(
        body_classifications["function_body_sha256"].astype("string").tolist()
    )
    selected_events = prepared_events.loc[
        prepared_events["function_body_sha256"].isin(selected_hashes)
    ].copy()

    score_columns = [
        "function_body_sha256",
        "function_npr",
        "agc_threshold",
        "agc_like",
        "hwc_like",
        "partial_body_score",
        "n_attempted_windows",
        "n_valid_npr_windows",
        "n_invalid_npr_windows",
        "valid_npr_token_count",
        "invalid_npr_token_count",
        "npr_algorithm_version",
        "npr_decision_rule",
        "npr_window_policy",
        "npr_function_aggregation",
        "npr_partial_body_policy",
        "npr_scoring_model",
        "npr_window_size_literal_space_tokens",
        "npr_perturbations_per_window",
        "npr_random_seed",
    ]
    selected_events = selected_events.merge(
        body_classifications[score_columns],
        on="function_body_sha256",
        how="left",
        validate="many_to_one",
        indicator="npr_body_merge_status",
    )

    missing_body_score = selected_events["npr_body_merge_status"].ne("both")
    add_check(
        checks,
        "all_selected_events_map_to_body_scores",
        not bool(missing_body_score.any()),
        int(missing_body_score.sum()),
        0,
        "Every selected event must map to exactly one successful body score.",
    )
    if missing_body_score.any():
        raise ValidationError("Selected events contain unresolved body-score mappings")
    selected_events = selected_events.drop(columns=["npr_body_merge_status"])

    selected_events = selected_events.rename(
        columns={
            "agc_like": "npr_agc_like",
            "hwc_like": "npr_hwc_like",
        }
    )
    selected_events["npr_specification"] = specification_name
    selected_events["npr_scoring_status"] = "success"

    selected_events["change_type_normalized"] = (
        selected_events["change_type"].astype("string").str.strip().str.lower()
    )
    unknown_change_type = ~selected_events["change_type_normalized"].isin(
        ["added", "modified"]
    )
    add_check(
        checks,
        "selected_events_use_added_or_modified_change_types",
        not bool(unknown_change_type.any()),
        int(unknown_change_type.sum()),
        0,
        "Repository-month subtype counts require added/modified event labels.",
    )
    if unknown_change_type.any():
        sample = selected_events.loc[
            unknown_change_type,
            ["function_event_id", "change_type"],
        ].head(20)
        raise ValidationError(
            "Unexpected change_type values in selected events:\n"
            + sample.to_string(index=False)
        )

    event_tokens = pd.to_numeric(
        selected_events["function_body_split_space_token_count"], errors="coerce"
    )
    body_token_lookup = body_classifications.set_index("function_body_sha256")[
        "function_body_split_space_token_count"
    ]
    expected_event_tokens = selected_events["function_body_sha256"].map(
        body_token_lookup
    )
    token_mismatch = int(event_tokens.ne(expected_event_tokens).sum())
    add_check(
        checks,
        "event_and_body_score_token_counts_match",
        token_mismatch == 0,
        token_mismatch,
        0,
        "Event metadata and body-score token counts must agree.",
    )

    observed_references = (
        selected_events.groupby("function_body_sha256", as_index=False)
        .agg(observed_event_references=("function_event_id", "size"))
    )
    reference_check = body_classifications[
        ["function_body_sha256", "referencing_function_event_count"]
    ].merge(
        observed_references,
        on="function_body_sha256",
        how="left",
        validate="one_to_one",
    )
    reference_check["observed_event_references"] = (
        reference_check["observed_event_references"].fillna(0).astype("int64")
    )
    reference_check["referencing_function_event_count"] = pd.to_numeric(
        reference_check["referencing_function_event_count"], errors="coerce"
    ).astype("int64")
    reference_check["reference_count_matches"] = (
        reference_check["referencing_function_event_count"]
        == reference_check["observed_event_references"]
    )
    reference_mismatches = int((~reference_check["reference_count_matches"]).sum())
    add_check(
        checks,
        "body_reference_counts_match_selected_events",
        reference_mismatches == 0,
        reference_mismatches,
        0,
        "Body-level reference counts must reconstruct selected event rows.",
    )

    selected_events = selected_events.sort_values(
        [*KEY_COLUMNS, "function_event_id"], kind="mergesort"
    )
    return selected_events, reference_check


def aggregate_events(selected_events: pd.DataFrame) -> pd.DataFrame:
    if selected_events.empty:
        return pd.DataFrame(columns=KEY_COLUMNS + NPR_COUNT_COLUMNS)

    events = selected_events.copy()
    events["is_added"] = events["change_type_normalized"].eq("added").astype("int8")
    events["is_modified"] = events["change_type_normalized"].eq("modified").astype("int8")
    events["is_added_agc"] = (events["is_added"] * events["npr_agc_like"]).astype("int8")
    events["is_added_hwc"] = (events["is_added"] * events["npr_hwc_like"]).astype("int8")
    events["is_modified_agc"] = (
        events["is_modified"] * events["npr_agc_like"]
    ).astype("int8")
    events["is_modified_hwc"] = (
        events["is_modified"] * events["npr_hwc_like"]
    ).astype("int8")

    return (
        events.groupby(KEY_COLUMNS, dropna=False)
        .agg(
            npr_scored_function_change_events=("function_event_id", "size"),
            npr_agc_function_change_events=("npr_agc_like", "sum"),
            npr_hwc_function_change_events=("npr_hwc_like", "sum"),
            npr_added_function_change_events=("is_added", "sum"),
            npr_modified_function_change_events=("is_modified", "sum"),
            npr_added_agc_function_change_events=("is_added_agc", "sum"),
            npr_added_hwc_function_change_events=("is_added_hwc", "sum"),
            npr_modified_agc_function_change_events=("is_modified_agc", "sum"),
            npr_modified_hwc_function_change_events=("is_modified_hwc", "sum"),
            npr_unique_scored_bodies=("function_body_sha256", "nunique"),
            npr_mean_function_npr=("function_npr", "mean"),
            npr_median_function_npr=("function_npr", "median"),
        )
        .reset_index()
    )


def prepare_source_counts(source_counts: pd.DataFrame) -> pd.DataFrame:
    source = normalize_keys(source_counts)
    require_unique(source, KEY_COLUMNS, "Source function-event counts")
    rename_map = {
        "function_change_events": "all_function_change_events",
        "added_function_events": "all_added_function_events",
        "modified_function_events": "all_modified_function_events",
    }
    keep = KEY_COLUMNS + list(rename_map)
    source = source[keep].rename(columns=rename_map)
    for column in rename_map.values():
        source[column] = pd.to_numeric(source[column], errors="raise").astype("int64")
    return source


def merge_parse_exclusions(
    complete: pd.DataFrame,
    exclusions_path: Path | None,
) -> pd.DataFrame:
    result = complete.copy()
    if exclusions_path is None:
        result["parse_exclusion_records"] = 0
        result["has_parse_exclusion"] = 0
        return result

    exclusions = normalize_keys(pd.read_csv(exclusions_path, low_memory=False))
    require_columns(exclusions, KEY_COLUMNS, "Parse-exclusion repository-month table")
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
            .rename(columns={count_column: "parse_exclusion_records"})
        )
        exclusions["parse_exclusion_records"] = pd.to_numeric(
            exclusions["parse_exclusion_records"], errors="coerce"
        ).fillna(0)
        exclusions = (
            exclusions.groupby(KEY_COLUMNS, as_index=False)
            .agg(parse_exclusion_records=("parse_exclusion_records", "sum"))
        )

    result = result.merge(
        exclusions,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    result["parse_exclusion_records"] = pd.to_numeric(
        result["parse_exclusion_records"], errors="coerce"
    ).fillna(0)
    result["has_parse_exclusion"] = (
        result["parse_exclusion_records"].gt(0).astype("int8")
    )
    return result


def build_complete_panel(
    panel: pd.DataFrame,
    source_counts: pd.DataFrame,
    aggregated: pd.DataFrame,
    threshold: dict[str, Any],
    specification_name: str,
    min_tokens: int,
    max_tokens: int,
    parse_exclusions_path: Path | None,
    checks: list[dict[str, Any]],
) -> pd.DataFrame:
    panel = normalize_keys(panel)
    require_unique(panel, KEY_COLUMNS, "Matched panel")

    source = prepare_source_counts(source_counts)
    source_key_check = panel[KEY_COLUMNS].merge(
        source[KEY_COLUMNS],
        on=KEY_COLUMNS,
        how="outer",
        indicator=True,
    )
    panel_only = int(source_key_check["_merge"].eq("left_only").sum())
    source_only = int(source_key_check["_merge"].eq("right_only").sum())
    add_check(
        checks,
        "panel_and_source_count_keys_match",
        panel_only == 0 and source_only == 0,
        {"panel_only": panel_only, "source_only": source_only},
        {"panel_only": 0, "source_only": 0},
        "The complete panel and extraction-stage source counts must cover the same repository-months.",
    )
    if panel_only or source_only:
        raise ValidationError("Panel and source-count repository-month keys differ")

    complete = panel.merge(
        source,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    complete = complete.merge(
        aggregated,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    for column in NPR_COUNT_COLUMNS:
        complete[column] = pd.to_numeric(
            complete[column], errors="coerce"
        ).fillna(0).astype("int64")

    complete["has_npr_scored_function_change_event"] = (
        complete["npr_scored_function_change_events"].gt(0).astype("int8")
    )
    complete["zero_npr_scored_function_event_month"] = (
        complete["npr_scored_function_change_events"].eq(0).astype("int8")
    )
    complete["zero_all_function_event_month"] = (
        complete["all_function_change_events"].eq(0).astype("int8")
    )
    complete["has_function_events_but_no_npr_selected_event"] = (
        complete["all_function_change_events"].gt(0)
        & complete["npr_scored_function_change_events"].eq(0)
    ).astype("int8")

    positive = complete["npr_scored_function_change_events"].gt(0)
    complete["npr_agc_function_change_event_ratio"] = np.where(
        positive,
        complete["npr_agc_function_change_events"]
        / complete["npr_scored_function_change_events"],
        np.nan,
    )
    complete["npr_event_retention_rate_vs_all_function_events"] = np.where(
        complete["all_function_change_events"].gt(0),
        complete["npr_scored_function_change_events"]
        / complete["all_function_change_events"],
        np.nan,
    )

    complete["log1p_npr_scored_function_change_events"] = np.log1p(
        complete["npr_scored_function_change_events"]
    )
    complete["log1p_npr_agc_function_change_events"] = np.log1p(
        complete["npr_agc_function_change_events"]
    )
    complete["log1p_npr_hwc_function_change_events"] = np.log1p(
        complete["npr_hwc_function_change_events"]
    )

    complete["npr_detection_complete"] = True
    complete["npr_specification"] = specification_name
    complete["npr_minimum_body_tokens_inclusive"] = min_tokens
    complete["npr_maximum_body_tokens_inclusive"] = max_tokens
    complete["npr_agc_threshold"] = float(threshold["agc_threshold"])
    complete["npr_algorithm_version"] = str(threshold["algorithm_version"])
    complete["npr_decision_rule"] = str(threshold["decision_rule"])
    complete["npr_window_policy"] = str(threshold["window_policy"])
    complete["npr_function_aggregation"] = str(threshold["function_aggregation"])
    complete["npr_partial_body_policy"] = str(threshold["partial_body_policy"])
    complete["npr_scoring_model"] = str(threshold["scoring_model"])
    complete["npr_window_size_literal_space_tokens"] = int(
        threshold["window_size_literal_space_tokens"]
    )
    complete["npr_perturbations_per_window"] = int(
        threshold["perturbations_per_window"]
    )
    complete["npr_random_seed"] = int(threshold["random_seed"])

    complete["treatment_group"] = complete["dataset_source"].map(
        {"control": "control", "treatment": "treatment"}
    )
    if complete["treatment_group"].isna().any():
        unexpected = sorted(
            complete.loc[
                complete["treatment_group"].isna(), "dataset_source"
            ].dropna().unique().tolist()
        )
        raise ValidationError(f"Unexpected dataset_source values: {unexpected}")
    complete["npr_treatment_period"] = derive_treatment_period(complete)

    complete = merge_parse_exclusions(complete, parse_exclusions_path)

    selected_exceeds_all = int(
        (
            complete["npr_scored_function_change_events"]
            > complete["all_function_change_events"]
        ).sum()
    )
    add_check(
        checks,
        "npr_selected_event_counts_do_not_exceed_all_function_events",
        selected_exceeds_all == 0,
        selected_exceeds_all,
        0,
        "Range-specific scored events must be a subset of all function-change events.",
    )

    event_partition_failures = int(
        (
            complete["npr_agc_function_change_events"]
            + complete["npr_hwc_function_change_events"]
            != complete["npr_scored_function_change_events"]
        ).sum()
    )
    add_check(
        checks,
        "repo_month_agc_hwc_event_partition",
        event_partition_failures == 0,
        event_partition_failures,
        0,
        "AGC-like and HWC-like event counts must reconstruct all NPR-scored events.",
    )

    subtype_partition_failures = int(
        (
            complete["npr_added_function_change_events"]
            + complete["npr_modified_function_change_events"]
            != complete["npr_scored_function_change_events"]
        ).sum()
    )
    add_check(
        checks,
        "repo_month_added_modified_event_partition",
        subtype_partition_failures == 0,
        subtype_partition_failures,
        0,
        "Added and modified event counts must reconstruct all NPR-scored events.",
    )

    agc_subtype_failures = int(
        (
            complete["npr_added_agc_function_change_events"]
            + complete["npr_modified_agc_function_change_events"]
            != complete["npr_agc_function_change_events"]
        ).sum()
    )
    hwc_subtype_failures = int(
        (
            complete["npr_added_hwc_function_change_events"]
            + complete["npr_modified_hwc_function_change_events"]
            != complete["npr_hwc_function_change_events"]
        ).sum()
    )
    add_check(
        checks,
        "repo_month_agc_subtype_partition",
        agc_subtype_failures == 0,
        agc_subtype_failures,
        0,
        "Added/modified AGC-like counts must reconstruct AGC-like counts.",
    )
    add_check(
        checks,
        "repo_month_hwc_subtype_partition",
        hwc_subtype_failures == 0,
        hwc_subtype_failures,
        0,
        "Added/modified HWC-like counts must reconstruct HWC-like counts.",
    )

    zero_ratio_nonmissing = int(
        complete.loc[~positive, "npr_agc_function_change_event_ratio"].notna().sum()
    )
    positive_ratio_missing = int(
        complete.loc[positive, "npr_agc_function_change_event_ratio"].isna().sum()
    )
    ratio_out_of_bounds = int(
        (
            ~complete.loc[positive, "npr_agc_function_change_event_ratio"].between(
                0, 1, inclusive="both"
            )
        ).sum()
    )
    add_check(
        checks,
        "zero_npr_event_month_ratio_is_missing",
        zero_ratio_nonmissing == 0,
        zero_ratio_nonmissing,
        0,
        "The AGC ratio is undefined when the selected-event denominator is zero.",
    )
    add_check(
        checks,
        "positive_npr_event_month_ratio_is_nonmissing",
        positive_ratio_missing == 0,
        positive_ratio_missing,
        0,
        "Every selected-event-positive month must have an AGC ratio.",
    )
    add_check(
        checks,
        "npr_agc_ratio_within_unit_interval",
        ratio_out_of_bounds == 0,
        ratio_out_of_bounds,
        0,
        "The selected-event AGC ratio must be between zero and one.",
    )

    return complete


def summarize_by_dimensions(complete: pd.DataFrame) -> dict[str, pd.DataFrame]:
    aggregation = {
        "repo_months": ("repo_name", "size"),
        "repositories": ("repo_name", "nunique"),
        "npr_event_positive_months": (
            "has_npr_scored_function_change_event",
            "sum",
        ),
        "zero_npr_event_months": (
            "zero_npr_scored_function_event_month",
            "sum",
        ),
        "all_function_event_months": (
            "zero_all_function_event_month",
            lambda series: int((series == 0).sum()),
        ),
        "out_of_range_or_unscored_only_months": (
            "has_function_events_but_no_npr_selected_event",
            "sum",
        ),
        "all_function_change_events": ("all_function_change_events", "sum"),
        "npr_scored_function_change_events": (
            "npr_scored_function_change_events",
            "sum",
        ),
        "npr_agc_function_change_events": (
            "npr_agc_function_change_events",
            "sum",
        ),
        "npr_hwc_function_change_events": (
            "npr_hwc_function_change_events",
            "sum",
        ),
    }

    def build(group_columns: list[str]) -> pd.DataFrame:
        grouped = (
            complete.groupby(group_columns, dropna=False)
            .agg(**aggregation)
            .reset_index()
        )
        grouped["npr_event_positive_month_share"] = (
            grouped["npr_event_positive_months"] / grouped["repo_months"]
        )
        grouped["pooled_npr_agc_event_ratio"] = np.where(
            grouped["npr_scored_function_change_events"].gt(0),
            grouped["npr_agc_function_change_events"]
            / grouped["npr_scored_function_change_events"],
            np.nan,
        )
        return grouped

    return {
        "by_dataset_source": build(["dataset_source"]),
        "by_treatment_period": build(["treatment_group", "npr_treatment_period"]),
        "by_event_time": build(["treatment_group", "time_to_event"]),
    }


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    input_events_path = require_file(args.input_events, "Input events")
    body_scores_path = require_file(args.body_scores, "Body scores")
    full_manifest_path = require_file(args.full_manifest, "Full manifest")
    threshold_path = require_file(
        args.threshold_specification, "Threshold specification"
    )
    source_counts_path = require_file(args.source_counts, "Source counts")
    panel_path = require_file(args.panel, "Matched panel")
    if args.parse_exclusions_by_repo_month is not None:
        require_file(
            args.parse_exclusions_by_repo_month,
            "Parse-exclusion repository-month table",
        )
    if args.detector_summary is not None:
        require_file(args.detector_summary, "Detector summary")
    if args.detector_metadata is not None:
        require_file(args.detector_metadata, "Detector metadata")

    if args.minimum_body_tokens < 1:
        raise ValueError("--minimum-body-tokens must be positive")
    if args.maximum_body_tokens < args.minimum_body_tokens:
        raise ValueError(
            "--maximum-body-tokens must be greater than or equal to the minimum"
        )

    output_dir = args.output_dir
    if output_dir is None:
        raise ValueError("--output-dir is required")
    qc_dir = args.qc_dir or output_dir / "qc"
    prepare_output_directories(output_dir, qc_dir, args.overwrite_output)

    events = pd.read_csv(input_events_path, low_memory=False)
    body_scores = pd.read_csv(body_scores_path, low_memory=False)
    manifest = pd.read_csv(full_manifest_path, low_memory=False)
    source_counts = pd.read_csv(source_counts_path, low_memory=False)
    panel = pd.read_csv(panel_path, low_memory=False)
    threshold = load_json(threshold_path, "Threshold specification")

    require_columns(events, EVENT_REQUIRED_COLUMNS, "Input events")
    require_columns(body_scores, BODY_SCORE_REQUIRED_COLUMNS, "Body scores")
    require_columns(manifest, MANIFEST_REQUIRED_COLUMNS, "Full manifest")
    require_columns(source_counts, SOURCE_COUNT_REQUIRED_COLUMNS, "Source counts")
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "Matched panel")
    validate_threshold_specification(threshold)

    checks: list[dict[str, Any]] = []

    add_check(
        checks,
        "threshold_specification_status_frozen",
        str(threshold["status"]).lower() == "frozen",
        str(threshold["status"]),
        "frozen",
        "Production aggregation must use the frozen calibration artifact.",
    )
    add_check(
        checks,
        "threshold_decision_rule_is_strict_greater_than",
        str(threshold["decision_rule"]) == "function_npr > agc_threshold",
        str(threshold["decision_rule"]),
        "function_npr > agc_threshold",
        "The calibrated decision rule is strict greater-than.",
    )

    body_classifications = prepare_body_classifications(
        body_scores=body_scores,
        manifest=manifest,
        threshold=threshold,
        specification_name=args.specification_name,
        min_tokens=args.minimum_body_tokens,
        max_tokens=args.maximum_body_tokens,
        checks=checks,
    )

    event_classifications, reference_check = prepare_event_classifications(
        events=events,
        body_classifications=body_classifications,
        specification_name=args.specification_name,
        checks=checks,
    )
    aggregated = aggregate_events(event_classifications)

    complete = build_complete_panel(
        panel=panel,
        source_counts=source_counts,
        aggregated=aggregated,
        threshold=threshold,
        specification_name=args.specification_name,
        min_tokens=args.minimum_body_tokens,
        max_tokens=args.maximum_body_tokens,
        parse_exclusions_path=args.parse_exclusions_by_repo_month,
        checks=checks,
    )

    observed_windows = int(
        pd.to_numeric(manifest["n_expected_windows"], errors="coerce").sum()
    )
    observed_partial = int(
        pd.to_numeric(body_scores["partial_body_score"], errors="coerce")
        .fillna(0)
        .sum()
    )
    control_rows = int(complete["dataset_source"].eq("control").sum())
    treatment_rows = int(complete["dataset_source"].eq("treatment").sum())

    add_check(
        checks,
        "selected_body_count_matches_expected",
        len(body_classifications) == args.expected_selected_bodies,
        int(len(body_classifications)),
        int(args.expected_selected_bodies),
        "The completed 173-server production run selected 69,231 unique bodies.",
    )
    add_check(
        checks,
        "selected_window_count_matches_expected",
        observed_windows == args.expected_windows,
        observed_windows,
        int(args.expected_windows),
        "Manifest window counts must match the completed run-1d production total.",
    )
    add_check(
        checks,
        "partial_body_score_count_matches_expected",
        observed_partial == args.expected_partial_body_scores,
        observed_partial,
        int(args.expected_partial_body_scores),
        "The completed range100_200 run reported zero partial-body scores.",
    )
    add_check(
        checks,
        "complete_panel_row_count_matches_expected",
        len(complete) == args.expected_panel_rows,
        int(len(complete)),
        int(args.expected_panel_rows),
        "All matched repository-months must remain in the complete panel.",
    )
    add_check(
        checks,
        "control_repo_month_count_matches_expected",
        control_rows == args.expected_control_rows,
        control_rows,
        int(args.expected_control_rows),
        "Static control membership is derived from dataset_source.",
    )
    add_check(
        checks,
        "treatment_repo_month_count_matches_expected",
        treatment_rows == args.expected_treatment_rows,
        treatment_rows,
        int(args.expected_treatment_rows),
        "Static treatment membership is derived from dataset_source.",
    )
    add_check(
        checks,
        "complete_panel_repo_month_keys_unique",
        not complete.duplicated(KEY_COLUMNS).any(),
        int(complete.duplicated(KEY_COLUMNS).sum()),
        0,
        "The complete analysis table must have one row per repository-month.",
    )

    event_total = int(len(event_classifications))
    body_reference_total = int(
        pd.to_numeric(
            body_classifications["referencing_function_event_count"],
            errors="coerce",
        ).sum()
    )
    panel_event_total = int(complete["npr_scored_function_change_events"].sum())
    add_check(
        checks,
        "event_rows_match_body_reference_total",
        event_total == body_reference_total,
        event_total,
        body_reference_total,
        "Expanding unique body classifications must reconstruct all selected event references.",
    )
    add_check(
        checks,
        "repo_month_total_matches_event_classification_rows",
        panel_event_total == event_total,
        panel_event_total,
        event_total,
        "Repository-month aggregation must preserve the selected event total.",
    )

    detector_summary_payload: dict[str, Any] | None = None
    if args.detector_summary is not None:
        detector_summary_payload = load_json(args.detector_summary, "Detector summary")
        add_check(
            checks,
            "detector_summary_status_pass",
            str(detector_summary_payload.get("status")) == "PASS",
            detector_summary_payload.get("status"),
            "PASS",
            "Downstream aggregation requires a completed run-1d result.",
        )
        add_check(
            checks,
            "detector_summary_selected_bodies_match",
            int(detector_summary_payload.get("selected_unique_bodies", -1))
            == len(body_classifications),
            detector_summary_payload.get("selected_unique_bodies"),
            int(len(body_classifications)),
            "Detector summary and body-score row count must agree.",
        )
        add_check(
            checks,
            "detector_summary_scored_windows_match",
            int(detector_summary_payload.get("scored_windows", -1))
            == observed_windows,
            detector_summary_payload.get("scored_windows"),
            observed_windows,
            "Detector summary and manifest window total must agree.",
        )

    detector_metadata_payload: dict[str, Any] | None = None
    if args.detector_metadata is not None:
        detector_metadata_payload = load_json(args.detector_metadata, "Detector metadata")
        add_check(
            checks,
            "detector_metadata_status_pass",
            str(detector_metadata_payload.get("status")) == "PASS",
            detector_metadata_payload.get("status"),
            "PASS",
            "Detector metadata must describe the successful production run.",
        )

    summaries = summarize_by_dimensions(complete)

    mapping_audit = pd.DataFrame(
        [
            {
                "specification": args.specification_name,
                "input_event_rows": int(len(events)),
                "prepared_input_event_rows": int(
                    (
                        normalize_boolean(events["input_preparation_complete"]).eq(True)
                        & events["body_extraction_status"]
                        .astype("string")
                        .str.strip()
                        .str.lower()
                        .eq("prepared")
                    ).sum()
                ),
                "selected_unique_bodies": int(len(body_classifications)),
                "selected_event_rows": event_total,
                "selected_event_repo_months": int(len(aggregated)),
                "complete_repo_months": int(len(complete)),
                "zero_npr_selected_event_months": int(
                    complete["zero_npr_scored_function_event_month"].sum()
                ),
                "zero_all_function_event_months": int(
                    complete["zero_all_function_event_month"].sum()
                ),
                "function_event_months_with_no_npr_selected_event": int(
                    complete["has_function_events_but_no_npr_selected_event"].sum()
                ),
                "all_function_change_events": int(
                    complete["all_function_change_events"].sum()
                ),
                "npr_scored_function_change_events": panel_event_total,
                "npr_agc_function_change_events": int(
                    complete["npr_agc_function_change_events"].sum()
                ),
                "npr_hwc_function_change_events": int(
                    complete["npr_hwc_function_change_events"].sum()
                ),
                "pooled_npr_agc_event_ratio": (
                    float(complete["npr_agc_function_change_events"].sum())
                    / panel_event_total
                    if panel_event_total
                    else math.nan
                ),
                "event_retention_rate_vs_all_function_events": (
                    panel_event_total
                    / float(complete["all_function_change_events"].sum())
                    if complete["all_function_change_events"].sum()
                    else math.nan
                ),
            }
        ]
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    body_output = output_dir / "agc_commit_function_npr_body_classifications.csv"
    event_output = output_dir / "agc_commit_function_npr_event_classifications.csv"
    complete_output = (
        output_dir / "repo_month_agc_commit_function_npr_analysis_complete.csv"
    )
    mapping_output = output_dir / "agc_commit_function_npr_mapping_audit.csv"
    reference_output = output_dir / "agc_commit_function_npr_body_reference_audit.csv"
    source_output = output_dir / "agc_commit_function_npr_support_by_dataset_source.csv"
    period_output = output_dir / "agc_commit_function_npr_support_by_treatment_period.csv"
    event_time_output = output_dir / "agc_commit_function_npr_support_by_event_time.csv"
    checks_output = qc_dir / "agc_commit_function_npr_aggregation_checks.csv"
    summary_output = qc_dir / "agc_commit_function_npr_aggregation_summary.json"
    metadata_output = qc_dir / "agc_commit_function_npr_aggregation_metadata.json"

    atomic_write_csv(body_classifications, body_output)
    atomic_write_csv(event_classifications, event_output)
    atomic_write_csv(complete, complete_output)
    atomic_write_csv(mapping_audit, mapping_output)
    atomic_write_csv(reference_check, reference_output)
    atomic_write_csv(summaries["by_dataset_source"], source_output)
    atomic_write_csv(summaries["by_treatment_period"], period_output)
    atomic_write_csv(summaries["by_event_time"], event_time_output)
    atomic_write_csv(checks_frame, checks_output)

    input_paths = {
        "input_events": input_events_path,
        "body_scores": body_scores_path,
        "full_manifest": full_manifest_path,
        "threshold_specification": threshold_path,
        "source_counts": source_counts_path,
        "panel": panel_path,
    }
    if args.parse_exclusions_by_repo_month is not None:
        input_paths["parse_exclusions_by_repo_month"] = (
            args.parse_exclusions_by_repo_month
        )
    if args.detector_summary is not None:
        input_paths["detector_summary"] = args.detector_summary
    if args.detector_metadata is not None:
        input_paths["detector_metadata"] = args.detector_metadata

    metadata = {
        "status": "PASS" if overall_pass else "FAIL",
        "script_version": SCRIPT_VERSION,
        "specification_name": args.specification_name,
        "minimum_body_tokens_inclusive": args.minimum_body_tokens,
        "maximum_body_tokens_inclusive": args.maximum_body_tokens,
        "threshold_specification": threshold,
        "input_files": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in input_paths.items()
        },
        "detector_summary": detector_summary_payload,
        "detector_metadata_status": (
            detector_metadata_payload.get("status")
            if detector_metadata_payload is not None
            else None
        ),
        "outputs": {
            "body_classifications": str(body_output),
            "event_classifications": str(event_output),
            "complete_repo_month_panel": str(complete_output),
            "mapping_audit": str(mapping_output),
            "body_reference_audit": str(reference_output),
            "support_by_dataset_source": str(source_output),
            "support_by_treatment_period": str(period_output),
            "support_by_event_time": str(event_time_output),
            "checks": str(checks_output),
            "summary": str(summary_output),
        },
    }
    atomic_write_json(metadata, metadata_output)

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "failed_checks": int((~checks_frame["passed"]).sum()),
        "checks_total": int(len(checks_frame)),
        "specification_name": args.specification_name,
        "selected_unique_bodies": int(len(body_classifications)),
        "selected_event_rows": event_total,
        "selected_event_repo_months": int(len(aggregated)),
        "complete_repo_months": int(len(complete)),
        "zero_npr_selected_event_months": int(
            complete["zero_npr_scored_function_event_month"].sum()
        ),
        "function_event_months_with_no_npr_selected_event": int(
            complete["has_function_events_but_no_npr_selected_event"].sum()
        ),
        "npr_agc_function_change_events": int(
            complete["npr_agc_function_change_events"].sum()
        ),
        "npr_hwc_function_change_events": int(
            complete["npr_hwc_function_change_events"].sum()
        ),
        "conditional_ratio_repo_months": int(
            complete["npr_agc_function_change_event_ratio"].notna().sum()
        ),
        "parse_exclusion_affected_repo_months": int(
            complete["has_parse_exclusion"].sum()
        ),
        "outputs": metadata["outputs"],
    }
    atomic_write_json(summary, summary_output)

    print("=" * 78)
    print("run-py-7a: aggregate commit-function NPR classifications")
    print("=" * 78)
    print(f"Status:                                  {summary['status']}")
    print(f"Specification:                           {summary['specification_name']}")
    print(f"Selected unique bodies:                  {summary['selected_unique_bodies']}")
    print(f"Selected event rows:                     {summary['selected_event_rows']}")
    print(f"Selected-event repository-months:        {summary['selected_event_repo_months']}")
    print(f"Complete repository-months:              {summary['complete_repo_months']}")
    print(f"Zero selected-event months:              {summary['zero_npr_selected_event_months']}")
    print(
        "Function-event months with no selected NPR event: "
        f"{summary['function_event_months_with_no_npr_selected_event']}"
    )
    print(f"AGC-like selected events:                {summary['npr_agc_function_change_events']}")
    print(f"HWC-like selected events:                {summary['npr_hwc_function_change_events']}")
    print(f"Conditional-ratio repository-months:     {summary['conditional_ratio_repo_months']}")
    print(f"Failed checks:                           {summary['failed_checks']}")
    print(f"Complete panel:                          {complete_output}")
    print(f"Checks:                                  {checks_output}")
    print(f"Summary:                                 {summary_output}")
    print("=" * 78)

    if not overall_pass:
        failed = checks_frame.loc[~checks_frame["passed"]]
        print(failed.to_string(index=False), file=sys.stderr)
    return summary


def build_self_test_inputs(root: Path) -> dict[str, Path]:
    panel = pd.DataFrame(
        [
            {
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-01",
                "time_to_event": pd.NA,
            },
            {
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-02",
                "time_to_event": pd.NA,
            },
            {
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-01",
                "time_to_event": -1,
            },
            {
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-02",
                "time_to_event": 0,
            },
        ]
    )
    source_counts = pd.DataFrame(
        [
            {
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-01",
                "function_change_events": 3,
                "added_function_events": 2,
                "modified_function_events": 1,
            },
            {
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-02",
                "function_change_events": 0,
                "added_function_events": 0,
                "modified_function_events": 0,
            },
            {
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-01",
                "function_change_events": 1,
                "added_function_events": 1,
                "modified_function_events": 0,
            },
            {
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-02",
                "function_change_events": 2,
                "added_function_events": 0,
                "modified_function_events": 2,
            },
        ]
    )

    body_rows = [
        ("a" * 64, 100, 1.80, 1, 0, 2),
        ("b" * 64, 150, 1.20, 0, 1, 1),
        ("c" * 64, 200, 1.60, 1, 0, 1),
    ]
    body_scores_records: list[dict[str, Any]] = []
    manifest_records: list[dict[str, Any]] = []
    for index, (sha, tokens, npr, agc, hwc, references) in enumerate(body_rows):
        windows = 1 if tokens <= 128 else 2
        body_scores_records.append(
            {
                "profile_name": "range100_200_full",
                "stratum_name": "range100_200",
                "sample_rank": index + 1,
                "function_body_sha256": sha,
                "function_body_split_space_token_count": tokens,
                "n_expected_windows": windows,
                "n_scored_windows": windows,
                "n_attempted_windows": windows,
                "n_valid_npr_windows": windows,
                "n_invalid_npr_windows": 0,
                "valid_npr_token_count": tokens,
                "invalid_npr_token_count": 0,
                "partial_body_score": 0,
                "referencing_function_event_count": references,
                "function_npr": npr,
                "agc_threshold": 1.571637,
                "agc_like": agc,
                "hwc_like": hwc,
                "status": "success",
            }
        )
        manifest_records.append(
            {
                "function_body_sha256": sha,
                "function_body_split_space_token_count": tokens,
                "n_expected_windows": windows,
                "referencing_function_event_count": references,
                "selected_for_full_scoring": 1,
                "profile_name": "range100_200_full",
                "sample_rank": index + 1,
            }
        )

    events = pd.DataFrame(
        [
            {
                "function_event_id": "e1",
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-01",
                "change_type": "added",
                "function_body_sha256": "a" * 64,
                "function_body_split_space_token_count": 100,
                "input_preparation_complete": 1,
                "body_extraction_status": "prepared",
            },
            {
                "function_event_id": "e2",
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-02",
                "change_type": "modified",
                "function_body_sha256": "a" * 64,
                "function_body_split_space_token_count": 100,
                "input_preparation_complete": 1,
                "body_extraction_status": "prepared",
            },
            {
                "function_event_id": "e3",
                "dataset_source": "control",
                "repo_name": "owner/control",
                "time": "2025-01",
                "change_type": "modified",
                "function_body_sha256": "b" * 64,
                "function_body_split_space_token_count": 150,
                "input_preparation_complete": True,
                "body_extraction_status": "prepared",
            },
            {
                "function_event_id": "e4",
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-02",
                "change_type": "modified",
                "function_body_sha256": "c" * 64,
                "function_body_split_space_token_count": 200,
                "input_preparation_complete": "true",
                "body_extraction_status": "prepared",
            },
            {
                "function_event_id": "excluded",
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-01",
                "change_type": "added",
                "function_body_sha256": "d" * 64,
                "function_body_split_space_token_count": 90,
                "input_preparation_complete": 0,
                "body_extraction_status": "excluded",
            },
        ]
    )
    parse_exclusions = pd.DataFrame(
        [
            {
                "dataset_source": "treatment",
                "repo_name": "owner/treatment",
                "time": "2025-01",
                "parse_exclusion_records": 2,
            }
        ]
    )
    threshold = {
        "status": "frozen",
        "scoring_model": "bigcode/starcoder2-7b",
        "window_size_literal_space_tokens": 128,
        "perturbations_per_window": 50,
        "perturbation_type": "random-insert-space+newline",
        "function_aggregation": "valid_frontier_weighted_mean",
        "agc_threshold": 1.571637,
        "random_seed": 20260723,
        "algorithm_version": "overlap_final_full_window_valid_frontier_weighting-v1",
        "decision_rule": "function_npr > agc_threshold",
        "window_policy": "full_size_final_window_shifted_backward_with_overlap",
        "partial_body_policy": "any_valid_window_partial_success_full_windows-v2",
    }
    detector_summary = {
        "status": "PASS",
        "selected_unique_bodies": 3,
        "scored_windows": 5,
    }
    detector_metadata = {"status": "PASS"}

    paths = {
        "events": root / "events.csv",
        "body_scores": root / "body_scores.csv",
        "manifest": root / "manifest.csv",
        "threshold": root / "threshold.json",
        "source_counts": root / "source_counts.csv",
        "panel": root / "panel.csv",
        "parse_exclusions": root / "parse_exclusions.csv",
        "detector_summary": root / "detector_summary.json",
        "detector_metadata": root / "detector_metadata.json",
    }
    events.to_csv(paths["events"], index=False)
    pd.DataFrame(body_scores_records).to_csv(paths["body_scores"], index=False)
    pd.DataFrame(manifest_records).to_csv(paths["manifest"], index=False)
    source_counts.to_csv(paths["source_counts"], index=False)
    panel.to_csv(paths["panel"], index=False)
    parse_exclusions.to_csv(paths["parse_exclusions"], index=False)
    paths["threshold"].write_text(json.dumps(threshold), encoding="utf-8")
    paths["detector_summary"].write_text(
        json.dumps(detector_summary), encoding="utf-8"
    )
    paths["detector_metadata"].write_text(
        json.dumps(detector_metadata), encoding="utf-8"
    )
    return paths


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-7a-npr-v1-") as temporary:
        root = Path(temporary)
        paths = build_self_test_inputs(root)
        args = argparse.Namespace(
            input_events=paths["events"],
            body_scores=paths["body_scores"],
            full_manifest=paths["manifest"],
            threshold_specification=paths["threshold"],
            detector_summary=paths["detector_summary"],
            detector_metadata=paths["detector_metadata"],
            source_counts=paths["source_counts"],
            panel=paths["panel"],
            parse_exclusions_by_repo_month=paths["parse_exclusions"],
            output_dir=root / "output",
            qc_dir=root / "output" / "qc",
            specification_name="range100_200",
            minimum_body_tokens=100,
            maximum_body_tokens=200,
            expected_panel_rows=4,
            expected_control_rows=2,
            expected_treatment_rows=2,
            expected_selected_bodies=3,
            expected_windows=5,
            expected_partial_body_scores=0,
            overwrite_output=True,
            self_test=False,
        )
        summary = run_analysis(args)
        if summary["status"] != "PASS":
            raise AssertionError(summary)
        if summary["selected_event_rows"] != 4:
            raise AssertionError("Expected four selected event rows")
        if summary["npr_agc_function_change_events"] != 3:
            raise AssertionError("Expected three AGC-like event references")
        if summary["npr_hwc_function_change_events"] != 1:
            raise AssertionError("Expected one HWC-like event reference")

        complete = pd.read_csv(
            args.output_dir
            / "repo_month_agc_commit_function_npr_analysis_complete.csv"
        )
        if len(complete) != 4:
            raise AssertionError("Complete self-test panel row count mismatch")
        control_feb = complete.loc[
            complete["dataset_source"].eq("control")
            & complete["time"].eq("2025-02")
        ].iloc[0]
        if int(control_feb["npr_scored_function_change_events"]) != 0:
            raise AssertionError("Expected zero selected events in control February")
        if not pd.isna(control_feb["npr_agc_function_change_event_ratio"]):
            raise AssertionError("Zero selected-event month must have missing ratio")

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    required = [
        args.input_events,
        args.body_scores,
        args.full_manifest,
        args.threshold_specification,
        args.source_counts,
        args.panel,
        args.output_dir,
    ]
    if any(value is None for value in required):
        raise SystemExit(
            "--input-events, --body-scores, --full-manifest, "
            "--threshold-specification, --source-counts, --panel, and "
            "--output-dir are required unless --self-test is used."
        )

    summary = run_analysis(args)
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
