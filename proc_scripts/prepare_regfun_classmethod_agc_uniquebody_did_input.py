#!/usr/bin/env python3
"""Prepare combined module-function and class-method AGC DiD panels.

The outcome is the number of distinct AGC-like implementation-body SHA values
observed among synchronous module-level functions and synchronous class methods
within each repository-month.

Scope
-----
- Included function kinds: ``module_function`` and ``method``.
- Excluded function kinds: async and nested variants.
- Detector range: frozen ``range100_200`` specification.
- Classification used by the outcome: AGC-like only.
- Counting unit: distinct ``function_body_sha256`` per repository-month across
  both included function kinds. A body observed in both kinds in the same
  repository-month is counted once in the combined outcome.
- Outputs: zero-inclusive, parse-clean, positive-outcome, and positive-outcome
  parse-clean panels.
- HWC counts and AGC/HWC ratios are used only for input-integrity checks and are
  not carried into the analysis panels.

This script prepares data only. It does not estimate treatment effects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_VERSION = "run-py-7j-v1"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
BODY_COLUMN = "function_body_sha256"
FUNCTION_KIND_COLUMN = "function_kind"
AGC_COLUMN = "npr_agc_like"
HWC_COLUMN = "npr_hwc_like"
INCLUDED_FUNCTION_KINDS = ("module_function", "method")
SCOPE_LABEL = "module_function+method"

OUTCOME_COLUMN = (
    "npr_agc_regular_module_function_and_class_method_unique_bodies"
)
LOG_OUTCOME_COLUMN = (
    "log1p_npr_agc_regular_module_function_and_class_method_unique_bodies"
)
OCCURRENCE_COLUMN = (
    "has_npr_agc_regular_module_function_and_class_method_unique_body"
)
ZERO_COLUMN = (
    "zero_npr_agc_regular_module_function_and_class_method_unique_body_month"
)
PAPER_READY_COLUMN = (
    "analysis_ready_regular_module_function_and_class_method_agc_unique_body_"
    "paper_ncloc"
)
PYTHON_READY_COLUMN = (
    "analysis_ready_regular_module_function_and_class_method_agc_unique_body_"
    "python_snapshot_ncloc"
)

MODULE_COUNT_COLUMN = "module_function_agc_unique_bodies"
METHOD_COUNT_COLUMN = "method_agc_unique_bodies"
OVERLAP_COUNT_COLUMN = "module_method_agc_unique_body_overlap"

EVENT_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "function_event_id",
    BODY_COLUMN,
    FUNCTION_KIND_COLUMN,
    AGC_COLUMN,
    HWC_COLUMN,
]

BASE_PANEL_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "event",
    "time_to_event",
    "post_event",
    "age",
    "ncloc_paper",
    "ncloc_python_snapshot",
    "contributors",
    "stars",
    "issues",
    "log1p_age",
    "log1p_contributors",
    "log1p_stars",
    "log1p_issues",
    "has_parse_exclusion",
    "parse_exclusion_records",
    "npr_detection_complete",
    "npr_specification",
    "npr_agc_threshold",
    "npr_algorithm_version",
    "npr_decision_rule",
    "npr_window_policy",
    "npr_function_aggregation",
    "npr_partial_body_policy",
    "npr_scoring_model",
    "npr_window_size_literal_space_tokens",
    "npr_perturbations_per_window",
    "npr_random_seed",
    "treatment_group",
]

OPTIONAL_PANEL_COLUMNS = [
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

DETECTOR_METADATA_COLUMNS = [
    "npr_agc_threshold",
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

FORBIDDEN_PANEL_PATTERNS = ("hwc", "ratio")


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare repository-month panels for distinct AGC-like bodies from "
            "synchronous module functions and synchronous class methods."
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
        "--base-panel",
        type=Path,
        default=Path(
            "repo_python/run-py-7b/strict/specifications/range100_200/"
            "panel_event_monthly_agc_commit_function_npr.csv"
        ),
        help=(
            "Zero-inclusive matched panel used only for repository-month "
            "membership, treatment timing, covariates, parse flags, and frozen "
            "detector metadata. Existing AGC/HWC outcomes are not copied."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7j/strict/specifications/range100_200"
        ),
    )
    parser.add_argument("--specification-name", default="range100_200")
    parser.add_argument("--expected-panel-rows", type=int, default=1633)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument("--expected-parse-exclusion-rows", type=int, default=97)
    parser.add_argument("--expected-module-event-rows", type=int, default=22360)
    parser.add_argument("--expected-method-event-rows", type=int, default=50758)
    parser.add_argument("--expected-module-unique-bodies", type=int, default=18673)
    parser.add_argument("--expected-method-unique-bodies", type=int, default=39297)
    parser.add_argument("--expected-module-agc-event-rows", type=int, default=2994)
    parser.add_argument("--expected-method-agc-event-rows", type=int, default=5392)
    parser.add_argument(
        "--skip-frozen-kind-count-checks",
        action="store_true",
        help=(
            "Skip fixed range100_200 function-kind count checks. Structural, "
            "classification, panel, and arithmetic checks still run."
        ),
    )
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test", action="store_true")
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


def require_unique(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    duplicated = frame.duplicated(columns, keep=False)
    if duplicated.any():
        sample = frame.loc[duplicated, columns].head(20)
        raise ValidationError(
            f"{label} contains duplicate keys for {columns}:\n"
            f"{sample.to_string(index=False)}"
        )


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
    result["time"] = result["time"].str[:7]
    return result


def normalize_binary(series: pd.Series, label: str) -> pd.Series:
    mapping: dict[Any, int] = {
        True: 1,
        False: 0,
        1: 1,
        0: 0,
        1.0: 1,
        0.0: 0,
        "True": 1,
        "False": 0,
        "TRUE": 1,
        "FALSE": 0,
        "true": 1,
        "false": 0,
        "1": 1,
        "0": 0,
        "1.0": 1,
        "0.0": 0,
    }
    result = series.map(mapping)
    if result.isna().any():
        examples = series.loc[result.isna()].astype("string").head(20).tolist()
        raise ValidationError(f"{label} contains non-binary values: {examples}")
    return result.astype("int8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_output_directory(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {path}. "
                "Use --overwrite-output only for intentional replacement."
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


def count_unique_bodies(frame: pd.DataFrame) -> int:
    return int(frame[BODY_COLUMN].nunique())


def build_kind_summary(selected_events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for kind in INCLUDED_FUNCTION_KINDS:
        kind_events = selected_events.loc[
            selected_events[FUNCTION_KIND_COLUMN].eq(kind)
        ]
        agc_events = kind_events.loc[kind_events[AGC_COLUMN].eq(1)]
        hwc_events = kind_events.loc[kind_events[HWC_COLUMN].eq(1)]
        rows.append(
            {
                "function_scope": kind,
                "all_event_rows": int(len(kind_events)),
                "agc_event_rows": int(len(agc_events)),
                "hwc_event_rows": int(len(hwc_events)),
                "all_unique_bodies_global": count_unique_bodies(kind_events),
                "agc_unique_bodies_global": count_unique_bodies(agc_events),
                "hwc_unique_bodies_global": count_unique_bodies(hwc_events),
                "agc_unique_body_repo_month_occurrences": int(
                    agc_events.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN]).shape[0]
                ),
            }
        )

    agc_selected = selected_events.loc[selected_events[AGC_COLUMN].eq(1)]
    hwc_selected = selected_events.loc[selected_events[HWC_COLUMN].eq(1)]
    rows.append(
        {
            "function_scope": SCOPE_LABEL,
            "all_event_rows": int(len(selected_events)),
            "agc_event_rows": int(len(agc_selected)),
            "hwc_event_rows": int(len(hwc_selected)),
            "all_unique_bodies_global": count_unique_bodies(selected_events),
            "agc_unique_bodies_global": count_unique_bodies(agc_selected),
            "hwc_unique_bodies_global": count_unique_bodies(hwc_selected),
            "agc_unique_body_repo_month_occurrences": int(
                agc_selected.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN]).shape[0]
            ),
        }
    )
    return pd.DataFrame(rows)


def build_repo_month_counts(agc_events: pd.DataFrame) -> pd.DataFrame:
    distinct = agc_events.drop_duplicates(
        [*KEY_COLUMNS, FUNCTION_KIND_COLUMN, BODY_COLUMN]
    ).copy()

    module = distinct.loc[
        distinct[FUNCTION_KIND_COLUMN].eq("module_function"),
        [*KEY_COLUMNS, BODY_COLUMN],
    ]
    method = distinct.loc[
        distinct[FUNCTION_KIND_COLUMN].eq("method"),
        [*KEY_COLUMNS, BODY_COLUMN],
    ]

    module_counts = (
        module.groupby(KEY_COLUMNS, dropna=False)[BODY_COLUMN]
        .nunique()
        .rename(MODULE_COUNT_COLUMN)
        .reset_index()
    )
    method_counts = (
        method.groupby(KEY_COLUMNS, dropna=False)[BODY_COLUMN]
        .nunique()
        .rename(METHOD_COUNT_COLUMN)
        .reset_index()
    )

    overlap = module.merge(
        method,
        on=[*KEY_COLUMNS, BODY_COLUMN],
        how="inner",
        validate="many_to_many",
    ).drop_duplicates([*KEY_COLUMNS, BODY_COLUMN])
    overlap_counts = (
        overlap.groupby(KEY_COLUMNS, dropna=False)[BODY_COLUMN]
        .nunique()
        .rename(OVERLAP_COUNT_COLUMN)
        .reset_index()
    )

    combined = (
        agc_events.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN])
        .groupby(KEY_COLUMNS, dropna=False)[BODY_COLUMN]
        .nunique()
        .rename(OUTCOME_COLUMN)
        .reset_index()
    )

    counts = combined.merge(module_counts, on=KEY_COLUMNS, how="outer")
    counts = counts.merge(method_counts, on=KEY_COLUMNS, how="outer")
    counts = counts.merge(overlap_counts, on=KEY_COLUMNS, how="outer")
    for column in [
        OUTCOME_COLUMN,
        MODULE_COUNT_COLUMN,
        METHOD_COUNT_COLUMN,
        OVERLAP_COUNT_COLUMN,
    ]:
        counts[column] = counts[column].fillna(0).astype("int64")

    counts = counts.sort_values(KEY_COLUMNS).reset_index(drop=True)
    return counts


def build_overlap_audit(
    selected_events: pd.DataFrame,
    agc_events: pd.DataFrame,
    repo_month_counts: pd.DataFrame,
) -> pd.DataFrame:
    def body_set(frame: pd.DataFrame, kind: str) -> set[str]:
        return set(
            frame.loc[
                frame[FUNCTION_KIND_COLUMN].eq(kind), BODY_COLUMN
            ].dropna().astype(str)
        )

    all_module = body_set(selected_events, "module_function")
    all_method = body_set(selected_events, "method")
    agc_module = body_set(agc_events, "module_function")
    agc_method = body_set(agc_events, "method")

    return pd.DataFrame(
        [
            {
                "included_function_kinds": SCOPE_LABEL,
                "all_global_cross_kind_body_overlap": len(all_module & all_method),
                "agc_global_cross_kind_body_overlap": len(agc_module & agc_method),
                "agc_repo_month_cross_kind_body_overlap": int(
                    repo_month_counts[OVERLAP_COUNT_COLUMN].sum()
                ),
                "module_agc_repo_month_occurrences": int(
                    repo_month_counts[MODULE_COUNT_COLUMN].sum()
                ),
                "method_agc_repo_month_occurrences": int(
                    repo_month_counts[METHOD_COUNT_COLUMN].sum()
                ),
                "combined_agc_repo_month_occurrences": int(
                    repo_month_counts[OUTCOME_COLUMN].sum()
                ),
                "combined_identity_expected": int(
                    repo_month_counts[MODULE_COUNT_COLUMN].sum()
                    + repo_month_counts[METHOD_COUNT_COLUMN].sum()
                    - repo_month_counts[OVERLAP_COUNT_COLUMN].sum()
                ),
            }
        ]
    )


def build_panel(
    events: pd.DataFrame,
    base_panel: pd.DataFrame,
    specification_name: str,
    expected: dict[str, int],
    skip_frozen_kind_count_checks: bool,
) -> dict[str, Any]:
    require_columns(events, EVENT_REQUIRED_COLUMNS, "Event classifications")
    require_columns(base_panel, BASE_PANEL_REQUIRED_COLUMNS, "Base panel")
    require_unique(events, ["function_event_id"], "Event classifications")
    require_unique(base_panel, KEY_COLUMNS, "Base panel")

    checks: list[dict[str, Any]] = []

    events = normalize_keys(events)
    base_panel = normalize_keys(base_panel)
    events[BODY_COLUMN] = (
        events[BODY_COLUMN].astype("string").str.strip().str.lower()
    )
    events[FUNCTION_KIND_COLUMN] = (
        events[FUNCTION_KIND_COLUMN].astype("string").str.strip().str.lower()
    )
    events[AGC_COLUMN] = normalize_binary(events[AGC_COLUMN], AGC_COLUMN)
    events[HWC_COLUMN] = normalize_binary(events[HWC_COLUMN], HWC_COLUMN)

    panel_sources_valid = base_panel["dataset_source"].isin(
        ["control", "treatment"]
    )
    add_check(
        checks,
        "base_panel_dataset_source_valid",
        bool(panel_sources_valid.all()),
        int((~panel_sources_valid).sum()),
        0,
        "The matched panel must contain only control and treatment rows.",
    )

    treatment_group_mismatch = int(
        base_panel["treatment_group"]
        .astype("string")
        .ne(base_panel["dataset_source"].astype("string"))
        .sum()
    )
    add_check(
        checks,
        "treatment_group_matches_dataset_source",
        treatment_group_mismatch == 0,
        treatment_group_mismatch,
        0,
        "Treatment-group metadata must agree with dataset_source.",
    )

    specification_mismatch = int(
        base_panel["npr_specification"]
        .astype("string")
        .ne(specification_name)
        .sum()
    )
    add_check(
        checks,
        "base_panel_specification_matches",
        specification_mismatch == 0,
        specification_mismatch,
        0,
        "The base panel must use the requested frozen NPR specification.",
    )

    detection_complete = normalize_binary(
        base_panel["npr_detection_complete"], "npr_detection_complete"
    )
    detection_incomplete = int(detection_complete.ne(1).sum())
    add_check(
        checks,
        "base_panel_detection_complete",
        detection_incomplete == 0,
        detection_incomplete,
        0,
        "All retained repository-months must have complete frozen detection metadata.",
    )

    selected_events = events.loc[
        events[FUNCTION_KIND_COLUMN].isin(INCLUDED_FUNCTION_KINDS)
    ].copy()
    agc_events = selected_events.loc[selected_events[AGC_COLUMN].eq(1)].copy()

    classification_sum = selected_events[AGC_COLUMN] + selected_events[HWC_COLUMN]
    invalid_classification_rows = int(classification_sum.ne(1).sum())
    add_check(
        checks,
        "selected_events_have_exactly_one_agc_or_hwc_classification",
        invalid_classification_rows == 0,
        invalid_classification_rows,
        0,
        "Every selected event must be classified as exactly one of AGC-like or HWC-like.",
    )

    kind_summary = build_kind_summary(selected_events)
    summary_by_kind = kind_summary.set_index("function_scope")

    if not skip_frozen_kind_count_checks:
        frozen_checks = [
            (
                "module_event_rows_match_expected",
                int(summary_by_kind.loc["module_function", "all_event_rows"]),
                expected["module_event_rows"],
            ),
            (
                "method_event_rows_match_expected",
                int(summary_by_kind.loc["method", "all_event_rows"]),
                expected["method_event_rows"],
            ),
            (
                "module_unique_bodies_match_expected",
                int(summary_by_kind.loc["module_function", "all_unique_bodies_global"]),
                expected["module_unique_bodies"],
            ),
            (
                "method_unique_bodies_match_expected",
                int(summary_by_kind.loc["method", "all_unique_bodies_global"]),
                expected["method_unique_bodies"],
            ),
            (
                "module_agc_event_rows_match_expected",
                int(summary_by_kind.loc["module_function", "agc_event_rows"]),
                expected["module_agc_event_rows"],
            ),
            (
                "method_agc_event_rows_match_expected",
                int(summary_by_kind.loc["method", "agc_event_rows"]),
                expected["method_agc_event_rows"],
            ),
        ]
        for name, observed, expected_value in frozen_checks:
            add_check(
                checks,
                name,
                observed == expected_value,
                observed,
                expected_value,
                "Frozen range100_200 function-kind count must match the prior diagnostic.",
            )

    module_event_rows = int(
        summary_by_kind.loc["module_function", "all_event_rows"]
    )
    method_event_rows = int(summary_by_kind.loc["method", "all_event_rows"])
    combined_event_rows = int(summary_by_kind.loc[SCOPE_LABEL, "all_event_rows"])
    add_check(
        checks,
        "combined_event_rows_equal_sum_of_included_kinds",
        combined_event_rows == module_event_rows + method_event_rows,
        combined_event_rows,
        module_event_rows + method_event_rows,
        "Included function kinds are mutually exclusive at the event-row level.",
    )

    combined_agc_rows = int(summary_by_kind.loc[SCOPE_LABEL, "agc_event_rows"])
    combined_hwc_rows = int(summary_by_kind.loc[SCOPE_LABEL, "hwc_event_rows"])
    add_check(
        checks,
        "combined_agc_plus_hwc_equals_all_selected_events",
        combined_agc_rows + combined_hwc_rows == combined_event_rows,
        combined_agc_rows + combined_hwc_rows,
        combined_event_rows,
        "AGC-like plus HWC-like rows must reconstruct all selected events.",
    )

    event_keys = selected_events[KEY_COLUMNS].drop_duplicates()
    event_key_map = event_keys.merge(
        base_panel[KEY_COLUMNS],
        on=KEY_COLUMNS,
        how="left",
        indicator=True,
        validate="one_to_one",
    )
    unmapped_event_repo_months = int(event_key_map["_merge"].ne("both").sum())
    add_check(
        checks,
        "all_selected_event_repo_months_map_to_panel",
        unmapped_event_repo_months == 0,
        unmapped_event_repo_months,
        0,
        "Every selected function-event repository-month must exist in the matched panel.",
    )

    repo_month_counts = build_repo_month_counts(agc_events)
    overlap_audit = build_overlap_audit(
        selected_events, agc_events, repo_month_counts
    )
    monthly_identity_failures = int(
        (
            repo_month_counts[OUTCOME_COLUMN]
            != repo_month_counts[MODULE_COUNT_COLUMN]
            + repo_month_counts[METHOD_COUNT_COLUMN]
            - repo_month_counts[OVERLAP_COUNT_COLUMN]
        ).sum()
    )
    add_check(
        checks,
        "combined_monthly_count_equals_module_plus_method_minus_overlap",
        monthly_identity_failures == 0,
        monthly_identity_failures,
        0,
        "Combined distinct-body counts must account for cross-kind overlap.",
    )

    allowed_panel_columns = [
        *KEY_COLUMNS,
        "event",
        "time_to_event",
        "post_event",
        *[column for column in OPTIONAL_PANEL_COLUMNS if column in base_panel.columns],
        "age",
        "ncloc_paper",
        "ncloc_python_snapshot",
        "contributors",
        "stars",
        "issues",
        "log1p_age",
        "log1p_contributors",
        "log1p_stars",
        "log1p_issues",
        "has_parse_exclusion",
        "parse_exclusion_records",
        "npr_detection_complete",
        "npr_specification",
        *DETECTOR_METADATA_COLUMNS,
        "treatment_group",
    ]
    allowed_panel_columns = list(dict.fromkeys(allowed_panel_columns))

    panel = base_panel[allowed_panel_columns].copy()
    panel = panel.merge(
        repo_month_counts[[*KEY_COLUMNS, OUTCOME_COLUMN]],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    panel[OUTCOME_COLUMN] = panel[OUTCOME_COLUMN].fillna(0).astype("int64")
    panel[LOG_OUTCOME_COLUMN] = np.log1p(panel[OUTCOME_COLUMN])
    panel[OCCURRENCE_COLUMN] = panel[OUTCOME_COLUMN].gt(0).astype("int8")
    panel[ZERO_COLUMN] = panel[OUTCOME_COLUMN].eq(0).astype("int8")
    panel["regular_function_scope"] = SCOPE_LABEL
    panel["included_function_kinds"] = "module_function;method"
    panel["agc_count_unit"] = (
        "distinct_function_body_sha256_per_repository_month_across_included_kinds"
    )
    panel["agc_outcome_scale"] = "raw_count"

    shared_complete = panel[
        [
            OUTCOME_COLUMN,
            "log1p_age",
            "log1p_contributors",
            "log1p_stars",
            "log1p_issues",
        ]
    ].notna().all(axis=1)
    panel[PAPER_READY_COLUMN] = (
        shared_complete & panel["ncloc_paper"].notna()
    ).astype("int8")
    panel[PYTHON_READY_COLUMN] = (
        shared_complete & panel["ncloc_python_snapshot"].notna()
    ).astype("int8")

    panel_rows = int(len(panel))
    control_rows = int(panel["dataset_source"].eq("control").sum())
    treatment_rows = int(panel["dataset_source"].eq("treatment").sum())
    parse_exclusion_rows = int(
        normalize_binary(panel["has_parse_exclusion"], "has_parse_exclusion")
        .eq(1)
        .sum()
    )

    panel_expectations = [
        (
            "panel_rows_match_expected",
            panel_rows,
            expected["panel_rows"],
        ),
        (
            "control_rows_match_expected",
            control_rows,
            expected["control_rows"],
        ),
        (
            "treatment_rows_match_expected",
            treatment_rows,
            expected["treatment_rows"],
        ),
        (
            "parse_exclusion_rows_match_expected",
            parse_exclusion_rows,
            expected["parse_exclusion_rows"],
        ),
    ]
    for name, observed, expected_value in panel_expectations:
        add_check(
            checks,
            name,
            observed == expected_value,
            observed,
            expected_value,
            "The combined-scope panel must preserve the frozen matched-panel support.",
        )

    count_is_nonnegative_integer = bool(
        panel[OUTCOME_COLUMN].ge(0).all()
        and np.allclose(
            panel[OUTCOME_COLUMN].to_numpy(dtype=float),
            np.floor(panel[OUTCOME_COLUMN].to_numpy(dtype=float)),
        )
    )
    add_check(
        checks,
        "outcome_is_nonnegative_integer_count",
        count_is_nonnegative_integer,
        int((panel[OUTCOME_COLUMN] < 0).sum()),
        0,
        "The outcome must be a nonnegative integer count.",
    )

    occurrence_mismatch = int(
        panel[OCCURRENCE_COLUMN]
        .ne(panel[OUTCOME_COLUMN].gt(0).astype("int8"))
        .sum()
    )
    zero_mismatch = int(
        panel[ZERO_COLUMN]
        .ne(panel[OUTCOME_COLUMN].eq(0).astype("int8"))
        .sum()
    )
    log_mismatch = int(
        (~np.isclose(
            panel[LOG_OUTCOME_COLUMN],
            np.log1p(panel[OUTCOME_COLUMN]),
            rtol=0.0,
            atol=1e-12,
        )).sum()
    )
    add_check(
        checks,
        "occurrence_flag_matches_count",
        occurrence_mismatch == 0,
        occurrence_mismatch,
        0,
        "Occurrence must equal one exactly when the count is positive.",
    )
    add_check(
        checks,
        "zero_flag_matches_count",
        zero_mismatch == 0,
        zero_mismatch,
        0,
        "Zero-month flag must equal one exactly when the count is zero.",
    )
    add_check(
        checks,
        "log1p_diagnostic_matches_raw_count",
        log_mismatch == 0,
        log_mismatch,
        0,
        "The diagnostic log1p column must be a deterministic transform of the raw count.",
    )

    distinct_repo_month_bodies = int(
        agc_events.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN]).shape[0]
    )
    aggregated_count_sum = int(panel[OUTCOME_COLUMN].sum())
    add_check(
        checks,
        "repo_month_counts_reconstruct_distinct_combined_agc_body_rows",
        aggregated_count_sum == distinct_repo_month_bodies,
        aggregated_count_sum,
        distinct_repo_month_bodies,
        "Summed counts must reconstruct distinct combined-scope AGC body occurrences.",
    )

    forbidden_columns = sorted(
        column
        for column in panel.columns
        if any(pattern in column.lower() for pattern in FORBIDDEN_PANEL_PATTERNS)
    )
    add_check(
        checks,
        "analysis_panels_exclude_hwc_and_ratio_columns",
        len(forbidden_columns) == 0,
        ";".join(forbidden_columns),
        "none",
        "HWC and ratio variables must not be carried into the analysis panels.",
    )

    zero_rows = int(panel[OUTCOME_COLUMN].eq(0).sum())
    positive_rows = int(panel[OUTCOME_COLUMN].gt(0).sum())
    add_check(
        checks,
        "full_panel_retains_zero_count_months",
        zero_rows > 0,
        zero_rows,
        "> 0",
        "The zero-inclusive artifact must retain zero-count repository-months.",
    )
    add_check(
        checks,
        "full_panel_contains_positive_count_months",
        positive_rows > 0,
        positive_rows,
        "> 0",
        "At least one repository-month must contain a combined-scope AGC body.",
    )

    parse_clean = panel.loc[
        normalize_binary(panel["has_parse_exclusion"], "has_parse_exclusion").eq(0)
    ].copy()
    positive_outcome = panel.loc[panel[OUTCOME_COLUMN].gt(0)].copy()
    positive_parse_clean = parse_clean.loc[
        parse_clean[OUTCOME_COLUMN].gt(0)
    ].copy()

    for positive_frame in [positive_outcome, positive_parse_clean]:
        positive_frame["sample_restriction"] = "outcome > 0"
        positive_frame["causal_interpretation_allowed"] = False
        positive_frame["selection_note"] = (
            "Repository-months with zero realized outcome were excluded. "
            "This conditions on the outcome and is supplementary only."
        )

    parse_clean_remaining_exclusions = int(
        normalize_binary(
            parse_clean["has_parse_exclusion"], "has_parse_exclusion"
        ).eq(1).sum()
    )
    add_check(
        checks,
        "parse_clean_panel_has_no_parse_exclusions",
        parse_clean_remaining_exclusions == 0,
        parse_clean_remaining_exclusions,
        0,
        "Parse-clean output must remove every parse-exclusion repository-month.",
    )
    add_check(
        checks,
        "positive_outcome_panel_has_no_zero_rows",
        int(positive_outcome[OUTCOME_COLUMN].eq(0).sum()) == 0,
        int(positive_outcome[OUTCOME_COLUMN].eq(0).sum()),
        0,
        "The selected positive-outcome panel must not contain zero outcomes.",
    )
    add_check(
        checks,
        "positive_parse_clean_panel_has_no_zero_rows",
        int(positive_parse_clean[OUTCOME_COLUMN].eq(0).sum()) == 0,
        int(positive_parse_clean[OUTCOME_COLUMN].eq(0).sum()),
        0,
        "The positive parse-clean panel must not contain zero outcomes.",
    )
    add_check(
        checks,
        "positive_parse_clean_panel_has_no_parse_exclusions",
        int(
            normalize_binary(
                positive_parse_clean["has_parse_exclusion"],
                "has_parse_exclusion",
            ).eq(1).sum()
        )
        == 0,
        int(
            normalize_binary(
                positive_parse_clean["has_parse_exclusion"],
                "has_parse_exclusion",
            ).eq(1).sum()
        ),
        0,
        "The positive parse-clean panel must contain no parse-exclusion rows.",
    )

    positive_treatment_rows = int(
        positive_parse_clean["dataset_source"].eq("treatment").sum()
    )
    positive_control_rows = int(
        positive_parse_clean["dataset_source"].eq("control").sum()
    )
    add_check(
        checks,
        "positive_parse_clean_treatment_rows_nonzero",
        positive_treatment_rows > 0,
        positive_treatment_rows,
        "> 0",
        "Positive selected sample must retain treatment observations.",
    )
    add_check(
        checks,
        "positive_parse_clean_control_rows_nonzero",
        positive_control_rows > 0,
        positive_control_rows,
        "> 0",
        "Positive selected sample must retain control observations.",
    )

    rankify_audit = panel.loc[
        panel["repo_name"].eq("DataScienceUIBK/Rankify"),
        [
            "dataset_source",
            "repo_name",
            "time",
            "event",
            "time_to_event",
            OUTCOME_COLUMN,
            "has_parse_exclusion",
        ],
    ].copy()
    rankify_audit["retained_positive_outcome_sample"] = rankify_audit[
        OUTCOME_COLUMN
    ].gt(0)
    rankify_audit["retained_positive_parse_clean_sample"] = (
        rankify_audit[OUTCOME_COLUMN].gt(0)
        & normalize_binary(
            rankify_audit["has_parse_exclusion"], "has_parse_exclusion"
        ).eq(0)
    )

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "script_version": SCRIPT_VERSION,
        "specification": specification_name,
        "included_function_kinds": list(INCLUDED_FUNCTION_KINDS),
        "excluded_function_kinds": [
            "module_async_function",
            "async_method",
            "nested_function",
            "nested_async_function",
        ],
        "classification": "AGC-like outcome; HWC used only for integrity checks",
        "count_unit": (
            "distinct_function_body_sha256_per_repository_month_across_included_kinds"
        ),
        "primary_outcome": OUTCOME_COLUMN,
        "panel_rows": panel_rows,
        "control_rows": control_rows,
        "treatment_rows": treatment_rows,
        "parse_exclusion_rows": parse_exclusion_rows,
        "parse_clean_rows": int(len(parse_clean)),
        "zero_outcome_rows": zero_rows,
        "positive_outcome_rows": positive_rows,
        "positive_parse_clean_rows": int(len(positive_parse_clean)),
        "positive_parse_clean_treatment_rows": positive_treatment_rows,
        "positive_parse_clean_control_rows": positive_control_rows,
        "positive_parse_clean_treatment_repositories": int(
            positive_parse_clean.loc[
                positive_parse_clean["dataset_source"].eq("treatment"),
                "repo_name",
            ].nunique()
        ),
        "positive_parse_clean_control_repositories": int(
            positive_parse_clean.loc[
                positive_parse_clean["dataset_source"].eq("control"),
                "repo_name",
            ].nunique()
        ),
        "selected_event_rows": combined_event_rows,
        "selected_agc_event_rows": combined_agc_rows,
        "selected_hwc_event_rows": combined_hwc_rows,
        "selected_unique_bodies_global": int(
            summary_by_kind.loc[SCOPE_LABEL, "all_unique_bodies_global"]
        ),
        "selected_agc_unique_bodies_global": int(
            summary_by_kind.loc[SCOPE_LABEL, "agc_unique_bodies_global"]
        ),
        "agc_unique_body_repo_month_occurrences": aggregated_count_sum,
        "cross_kind_agc_global_body_overlap": int(
            overlap_audit.loc[0, "agc_global_cross_kind_body_overlap"]
        ),
        "cross_kind_agc_repo_month_body_overlap": int(
            overlap_audit.loc[0, "agc_repo_month_cross_kind_body_overlap"]
        ),
        "positive_selected_sample_causal_interpretation_allowed": False,
        "failed_checks": int((~checks_frame["passed"]).sum()),
    }

    return {
        "panel": panel,
        "parse_clean": parse_clean,
        "positive_outcome": positive_outcome,
        "positive_parse_clean": positive_parse_clean,
        "repo_month_counts": repo_month_counts,
        "kind_summary": kind_summary,
        "overlap_audit": overlap_audit,
        "rankify_audit": rankify_audit,
        "checks": checks_frame,
        "summary": summary,
        "overall_pass": overall_pass,
    }


def output_paths(output_dir: Path) -> dict[str, Path]:
    prefix = "regular_module_function_and_class_method_agc_unique_body"
    panel_prefix = "panel_event_monthly_" + prefix
    qc_dir = output_dir / "qc"
    return {
        "panel": output_dir / f"{panel_prefix}.csv",
        "parse_clean": output_dir / f"{panel_prefix}_parse_clean.csv",
        "positive_outcome": output_dir / f"{panel_prefix}_positive_outcome.csv",
        "positive_parse_clean": (
            output_dir / f"{panel_prefix}_positive_outcome_parse_clean.csv"
        ),
        "repo_month_counts": output_dir / f"{prefix}_repo_month_counts.csv",
        "kind_summary": output_dir / f"{prefix}_kind_summary.csv",
        "overlap_audit": output_dir / f"{prefix}_overlap_audit.csv",
        "rankify_audit": output_dir / f"{prefix}_rankify_audit.csv",
        "checks": qc_dir / f"{prefix}_did_input_checks.csv",
        "summary": qc_dir / f"{prefix}_did_input_summary.json",
    }


def write_outputs(
    outputs: dict[str, Any],
    output_dir: Path,
    event_path: Path,
    base_panel_path: Path,
) -> dict[str, Path]:
    paths = output_paths(output_dir)
    for key in [
        "panel",
        "parse_clean",
        "positive_outcome",
        "positive_parse_clean",
        "repo_month_counts",
        "kind_summary",
        "overlap_audit",
        "rankify_audit",
        "checks",
    ]:
        atomic_write_csv(outputs[key], paths[key])

    summary = dict(outputs["summary"])
    summary["event_classifications"] = str(event_path)
    summary["event_classifications_sha256"] = sha256_file(event_path)
    summary["base_panel"] = str(base_panel_path)
    summary["base_panel_sha256"] = sha256_file(base_panel_path)
    summary["outputs"] = {key: str(path) for key, path in paths.items()}
    atomic_write_json(summary, paths["summary"])
    return paths


def synthetic_base_panel() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source, repo, event in [
        ("control", "c/repo", pd.NA),
        ("treatment", "t/repo", "2024-02"),
    ]:
        for time, relative in [("2024-01", -1), ("2024-02", 0)]:
            rows.append(
                {
                    "dataset_source": source,
                    "repo_name": repo,
                    "time": time,
                    "event": event,
                    "time_to_event": relative if source == "treatment" else pd.NA,
                    "post_event": int(source == "treatment" and relative >= 0),
                    "age": 10,
                    "ncloc_paper": 100,
                    "ncloc_python_snapshot": 90,
                    "contributors": 2,
                    "stars": 3,
                    "issues": 1,
                    "log1p_age": np.log1p(10),
                    "log1p_contributors": np.log1p(2),
                    "log1p_stars": np.log1p(3),
                    "log1p_issues": np.log1p(1),
                    "has_parse_exclusion": int(
                        source == "control" and time == "2024-02"
                    ),
                    "parse_exclusion_records": int(
                        source == "control" and time == "2024-02"
                    ),
                    "npr_detection_complete": 1,
                    "npr_specification": "range100_200",
                    "npr_agc_threshold": 1.5,
                    "npr_algorithm_version": "test-v1",
                    "npr_decision_rule": "function_npr > agc_threshold",
                    "npr_window_policy": "test",
                    "npr_function_aggregation": "test",
                    "npr_partial_body_policy": "test",
                    "npr_scoring_model": "test/model",
                    "npr_window_size_literal_space_tokens": 128,
                    "npr_perturbations_per_window": 50,
                    "npr_random_seed": 1,
                    "treatment_group": source,
                }
            )
    return pd.DataFrame(rows)


def synthetic_events() -> pd.DataFrame:
    rows = [
        ("treatment", "t/repo", "2024-02", "e1", "a", "module_function", 1, 0),
        ("treatment", "t/repo", "2024-02", "e2", "a", "module_function", 1, 0),
        ("treatment", "t/repo", "2024-02", "e3", "a", "method", 1, 0),
        ("treatment", "t/repo", "2024-02", "e4", "b", "method", 1, 0),
        ("control", "c/repo", "2024-01", "e5", "c", "module_function", 0, 1),
        ("control", "c/repo", "2024-01", "e6", "d", "method", 1, 0),
        ("control", "c/repo", "2024-02", "e7", "e", "async_method", 1, 0),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            *KEY_COLUMNS,
            "function_event_id",
            BODY_COLUMN,
            FUNCTION_KIND_COLUMN,
            AGC_COLUMN,
            HWC_COLUMN,
        ],
    )


def run_self_test() -> None:
    outputs = build_panel(
        synthetic_events(),
        synthetic_base_panel(),
        "range100_200",
        {
            "panel_rows": 4,
            "control_rows": 2,
            "treatment_rows": 2,
            "parse_exclusion_rows": 1,
            "module_event_rows": 3,
            "method_event_rows": 3,
            "module_unique_bodies": 2,
            "method_unique_bodies": 3,
            "module_agc_event_rows": 2,
            "method_agc_event_rows": 3,
        },
        skip_frozen_kind_count_checks=False,
    )
    if not outputs["overall_pass"]:
        failed = outputs["checks"].loc[~outputs["checks"]["passed"]]
        raise AssertionError(f"Self-test failed:\n{failed.to_string(index=False)}")

    t_event = outputs["panel"].loc[
        (outputs["panel"]["repo_name"] == "t/repo")
        & (outputs["panel"]["time"] == "2024-02"),
        OUTCOME_COLUMN,
    ].iloc[0]
    if int(t_event) != 2:
        raise AssertionError(
            "Combined scope did not deduplicate repeated and cross-kind body SHA values"
        )

    c_january = outputs["panel"].loc[
        (outputs["panel"]["repo_name"] == "c/repo")
        & (outputs["panel"]["time"] == "2024-01"),
        OUTCOME_COLUMN,
    ].iloc[0]
    if int(c_january) != 1:
        raise AssertionError("Class-method AGC body was not included")

    if int(len(outputs["positive_outcome"])) != 2:
        raise AssertionError("Positive-outcome panel row count is incorrect")
    if int(outputs["overlap_audit"].loc[0, "agc_global_cross_kind_body_overlap"]) != 1:
        raise AssertionError("Cross-kind AGC body overlap was not detected")
    if any(
        pattern in column.lower()
        for column in outputs["panel"].columns
        for pattern in FORBIDDEN_PANEL_PATTERNS
    ):
        raise AssertionError("Analysis panel unexpectedly contains HWC or ratio columns")


def main() -> int:
    args = parse_args()

    if args.self_test:
        run_self_test()
        print("Self-test: PASS")
        return 0

    require_file(args.event_classifications, "Event classifications")
    require_file(args.base_panel, "Base panel")
    prepare_output_directory(args.output_dir, args.overwrite_output)

    events = pd.read_csv(args.event_classifications, low_memory=False)
    base_panel = pd.read_csv(args.base_panel, low_memory=False)

    outputs = build_panel(
        events,
        base_panel,
        args.specification_name,
        {
            "panel_rows": args.expected_panel_rows,
            "control_rows": args.expected_control_rows,
            "treatment_rows": args.expected_treatment_rows,
            "parse_exclusion_rows": args.expected_parse_exclusion_rows,
            "module_event_rows": args.expected_module_event_rows,
            "method_event_rows": args.expected_method_event_rows,
            "module_unique_bodies": args.expected_module_unique_bodies,
            "method_unique_bodies": args.expected_method_unique_bodies,
            "module_agc_event_rows": args.expected_module_agc_event_rows,
            "method_agc_event_rows": args.expected_method_agc_event_rows,
        },
        skip_frozen_kind_count_checks=args.skip_frozen_kind_count_checks,
    )
    paths = write_outputs(
        outputs,
        args.output_dir,
        args.event_classifications,
        args.base_panel,
    )

    summary = outputs["summary"]
    print("=" * 80)
    print("run-py-7j: prepare module-function + class-method AGC unique-body panels")
    print("=" * 80)
    print(f"Status:                                  {summary['status']}")
    print(f"Panel rows:                              {summary['panel_rows']}")
    print(f"Control rows:                            {summary['control_rows']}")
    print(f"Treatment rows:                          {summary['treatment_rows']}")
    print(f"Parse-clean rows:                        {summary['parse_clean_rows']}")
    print(f"Zero-outcome rows:                       {summary['zero_outcome_rows']}")
    print(f"Positive-outcome rows:                   {summary['positive_outcome_rows']}")
    print(f"Positive parse-clean rows:               {summary['positive_parse_clean_rows']}")
    print(f"Selected module+method event rows:       {summary['selected_event_rows']}")
    print(f"Selected AGC-like event rows:             {summary['selected_agc_event_rows']}")
    print(f"Selected HWC-like event rows (QC only):  {summary['selected_hwc_event_rows']}")
    print(f"Global selected unique bodies:           {summary['selected_unique_bodies_global']}")
    print(f"Global selected AGC unique bodies:       {summary['selected_agc_unique_bodies_global']}")
    print(
        "AGC body repository-month occurrences:  "
        f"{summary['agc_unique_body_repo_month_occurrences']}"
    )
    print(
        "Cross-kind AGC global body overlap:      "
        f"{summary['cross_kind_agc_global_body_overlap']}"
    )
    print(
        "Cross-kind AGC repo-month overlap:       "
        f"{summary['cross_kind_agc_repo_month_body_overlap']}"
    )
    print(f"Positive treatment repositories:         {summary['positive_parse_clean_treatment_repositories']}")
    print(f"Positive control repositories:           {summary['positive_parse_clean_control_repositories']}")
    print(f"Failed checks:                           {summary['failed_checks']}")
    print(f"Output directory:                        {args.output_dir}")
    print(f"Positive parse-clean panel:              {paths['positive_parse_clean']}")
    print("=" * 80)

    if not outputs["overall_pass"]:
        failed = outputs["checks"].loc[~outputs["checks"]["passed"]]
        print(failed.to_string(index=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
