#!/usr/bin/env python3
"""Prepare a zero-inclusive DiD panel for AGC-like regular-function bodies.

The outcome is the number of distinct AGC-like implementation bodies observed
for synchronous module-level Python functions in each repository-month.

Scope
-----
- Function kind: ``module_function`` only.
- Detector range: frozen ``range100_200`` specification.
- Classification: AGC-like only.
- Counting unit: distinct ``function_body_sha256`` per repository-month.
- Sample: full matched repository-month panel, including zero-count months.
- HWC counts and AGC/HWC ratios are intentionally excluded.

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


SCRIPT_VERSION = "run-py-7e-v1"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
BODY_COLUMN = "function_body_sha256"
FUNCTION_KIND_COLUMN = "function_kind"
AGC_COLUMN = "npr_agc_like"
OUTCOME_COLUMN = "npr_agc_regular_module_function_unique_bodies"
LOG_OUTCOME_COLUMN = "log1p_npr_agc_regular_module_function_unique_bodies"
OCCURRENCE_COLUMN = "has_npr_agc_regular_module_function_unique_body"
ZERO_COLUMN = "zero_npr_agc_regular_module_function_unique_body_month"
PAPER_READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
)
PYTHON_READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc"
)

EVENT_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "function_event_id",
    BODY_COLUMN,
    FUNCTION_KIND_COLUMN,
    AGC_COLUMN,
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

FORBIDDEN_OUTPUT_PATTERNS = ("hwc", "ratio")


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a Borusyak DiD input panel for monthly counts of distinct "
            "AGC-like regular module-function bodies."
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
            "Existing zero-inclusive matched panel used only for repository-month "
            "membership, treatment timing, covariates, parse flags, and frozen "
            "detector metadata. Old AGC/HWC outcomes are not copied."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7e/strict/specifications/range100_200"
        ),
    )
    parser.add_argument("--specification-name", default="range100_200")
    parser.add_argument("--function-kind", default="module_function")
    parser.add_argument("--expected-panel-rows", type=int, default=1633)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument("--expected-parse-exclusion-rows", type=int, default=97)
    parser.add_argument("--expected-regular-event-rows", type=int, default=22360)
    parser.add_argument("--expected-regular-unique-bodies", type=int, default=18673)
    parser.add_argument("--expected-agc-event-rows", type=int, default=2994)
    parser.add_argument("--expected-agc-unique-bodies", type=int, default=2463)
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


def build_panel(
    events: pd.DataFrame,
    base_panel: pd.DataFrame,
    function_kind: str,
    specification_name: str,
    expected: dict[str, int],
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

    regular_events = events.loc[
        events[FUNCTION_KIND_COLUMN].eq(function_kind)
    ].copy()
    agc_regular_events = regular_events.loc[regular_events[AGC_COLUMN].eq(1)].copy()

    regular_event_rows = int(len(regular_events))
    regular_unique_bodies = int(regular_events[BODY_COLUMN].nunique())
    agc_event_rows = int(len(agc_regular_events))
    agc_unique_bodies = int(agc_regular_events[BODY_COLUMN].nunique())

    for name, observed, key, note in [
        (
            "regular_event_rows_match_expected",
            regular_event_rows,
            "regular_event_rows",
            "Regular synchronous module-function events must reproduce run-py-7d.",
        ),
        (
            "regular_unique_bodies_match_expected",
            regular_unique_bodies,
            "regular_unique_bodies",
            "Regular unique bodies must reproduce run-py-7d.",
        ),
        (
            "agc_regular_event_rows_match_expected",
            agc_event_rows,
            "agc_event_rows",
            "AGC-like regular-function events must reproduce run-py-7d.",
        ),
        (
            "agc_regular_unique_bodies_match_expected",
            agc_unique_bodies,
            "agc_unique_bodies",
            "AGC-like regular-function unique bodies must reproduce run-py-7d.",
        ),
    ]:
        expected_value = expected[key]
        add_check(
            checks,
            name,
            observed == expected_value,
            observed,
            expected_value,
            note,
        )

    event_keys = regular_events[KEY_COLUMNS].drop_duplicates()
    event_key_map = event_keys.merge(
        base_panel[KEY_COLUMNS],
        on=KEY_COLUMNS,
        how="left",
        indicator=True,
        validate="one_to_one",
    )
    unmapped_regular_repo_months = int(event_key_map["_merge"].ne("both").sum())
    add_check(
        checks,
        "all_regular_event_repo_months_map_to_panel",
        unmapped_regular_repo_months == 0,
        unmapped_regular_repo_months,
        0,
        "Every regular-function event repository-month must exist in the matched panel.",
    )

    agc_repo_month = (
        agc_regular_events.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN])
        .groupby(KEY_COLUMNS, dropna=False)
        .agg(
            **{
                OUTCOME_COLUMN: (BODY_COLUMN, "size"),
            }
        )
        .reset_index()
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
        agc_repo_month,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    panel[OUTCOME_COLUMN] = (
        panel[OUTCOME_COLUMN].fillna(0).astype("int64")
    )
    panel[LOG_OUTCOME_COLUMN] = np.log1p(panel[OUTCOME_COLUMN])
    panel[OCCURRENCE_COLUMN] = panel[OUTCOME_COLUMN].gt(0).astype("int8")
    panel[ZERO_COLUMN] = panel[OUTCOME_COLUMN].eq(0).astype("int8")
    panel["regular_function_scope"] = function_kind
    panel["agc_count_unit"] = (
        "distinct_function_body_sha256_per_repository_month"
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

    for name, observed, key, note in [
        (
            "panel_rows_match_expected",
            panel_rows,
            "panel_rows",
            "The zero-inclusive panel must retain every matched repository-month.",
        ),
        (
            "control_rows_match_expected",
            control_rows,
            "control_rows",
            "Control repository-month count must match the frozen strict panel.",
        ),
        (
            "treatment_rows_match_expected",
            treatment_rows,
            "treatment_rows",
            "Treatment repository-month count must match the frozen strict panel.",
        ),
        (
            "parse_exclusion_rows_match_expected",
            parse_exclusion_rows,
            "parse_exclusion_rows",
            "Parse-exclusion count must match the frozen strict panel.",
        ),
    ]:
        expected_value = expected[key]
        add_check(
            checks,
            name,
            observed == expected_value,
            observed,
            expected_value,
            note,
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
        "The primary outcome must be a nonnegative integer count.",
    )

    occurrence_mismatch = int(
        panel[OCCURRENCE_COLUMN].ne(panel[OUTCOME_COLUMN].gt(0).astype("int8")).sum()
    )
    zero_mismatch = int(
        panel[ZERO_COLUMN].ne(panel[OUTCOME_COLUMN].eq(0).astype("int8")).sum()
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
        agc_regular_events.drop_duplicates([*KEY_COLUMNS, BODY_COLUMN]).shape[0]
    )
    aggregated_count_sum = int(panel[OUTCOME_COLUMN].sum())
    add_check(
        checks,
        "repo_month_counts_reconstruct_distinct_agc_body_rows",
        aggregated_count_sum == distinct_repo_month_bodies,
        aggregated_count_sum,
        distinct_repo_month_bodies,
        "Summed repository-month counts must reconstruct distinct AGC body occurrences.",
    )

    forbidden_columns = sorted(
        column
        for column in panel.columns
        if any(pattern in column.lower() for pattern in FORBIDDEN_OUTPUT_PATTERNS)
    )
    add_check(
        checks,
        "output_excludes_hwc_and_ratio_columns",
        len(forbidden_columns) == 0,
        ";".join(forbidden_columns),
        "none",
        "The focused panel must not carry HWC or ratio variables.",
    )

    zero_rows = int(panel[OUTCOME_COLUMN].eq(0).sum())
    positive_rows = int(panel[OUTCOME_COLUMN].gt(0).sum())
    add_check(
        checks,
        "full_panel_retains_zero_count_months",
        zero_rows > 0,
        zero_rows,
        "> 0",
        "The unconditional count estimand requires zero-count repository-months.",
    )
    add_check(
        checks,
        "full_panel_contains_positive_count_months",
        positive_rows > 0,
        positive_rows,
        "> 0",
        "At least one repository-month must contain an AGC-like regular body.",
    )

    parse_clean = panel.loc[
        normalize_binary(panel["has_parse_exclusion"], "has_parse_exclusion").eq(0)
    ].copy()
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

    checks_frame = pd.DataFrame(checks)
    overall_pass = bool(checks_frame["passed"].all())

    summary = {
        "status": "PASS" if overall_pass else "FAIL",
        "script_version": SCRIPT_VERSION,
        "specification": specification_name,
        "function_kind": function_kind,
        "classification": "AGC-like",
        "count_unit": "distinct_function_body_sha256_per_repository_month",
        "primary_outcome": OUTCOME_COLUMN,
        "panel_rows": panel_rows,
        "control_rows": control_rows,
        "treatment_rows": treatment_rows,
        "parse_exclusion_rows": parse_exclusion_rows,
        "parse_clean_rows": int(len(parse_clean)),
        "zero_outcome_rows": zero_rows,
        "positive_outcome_rows": positive_rows,
        "regular_event_rows": regular_event_rows,
        "regular_unique_bodies": regular_unique_bodies,
        "agc_regular_event_rows": agc_event_rows,
        "agc_regular_unique_bodies_global": agc_unique_bodies,
        "agc_unique_body_repo_month_occurrences": aggregated_count_sum,
        "failed_checks": int((~checks_frame["passed"]).sum()),
    }

    return {
        "panel": panel,
        "parse_clean": parse_clean,
        "repo_month_counts": agc_repo_month,
        "checks": checks_frame,
        "summary": summary,
        "overall_pass": overall_pass,
    }


def write_outputs(
    outputs: dict[str, Any],
    output_dir: Path,
    event_path: Path,
    base_panel_path: Path,
) -> None:
    qc_dir = output_dir / "qc"
    atomic_write_csv(
        outputs["panel"],
        output_dir / "panel_event_monthly_regular_module_function_agc_unique_body.csv",
    )
    atomic_write_csv(
        outputs["parse_clean"],
        output_dir
        / "panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv",
    )
    atomic_write_csv(
        outputs["repo_month_counts"],
        output_dir / "regular_module_function_agc_unique_body_repo_month_counts.csv",
    )
    atomic_write_csv(
        outputs["checks"],
        qc_dir / "regular_module_function_agc_unique_body_did_input_checks.csv",
    )

    summary = dict(outputs["summary"])
    summary["event_classifications"] = str(event_path)
    summary["event_classifications_sha256"] = sha256_file(event_path)
    summary["base_panel"] = str(base_panel_path)
    summary["base_panel_sha256"] = sha256_file(base_panel_path)
    summary["outputs"] = {
        "panel": str(
            output_dir
            / "panel_event_monthly_regular_module_function_agc_unique_body.csv"
        ),
        "parse_clean_panel": str(
            output_dir
            / "panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv"
        ),
        "repo_month_counts": str(
            output_dir / "regular_module_function_agc_unique_body_repo_month_counts.csv"
        ),
        "checks": str(
            qc_dir / "regular_module_function_agc_unique_body_did_input_checks.csv"
        ),
    }
    atomic_write_json(
        summary,
        qc_dir / "regular_module_function_agc_unique_body_did_input_summary.json",
    )


def run_self_test() -> None:
    panel_rows = []
    for source, repo, event in [
        ("control", "c/repo", pd.NA),
        ("treatment", "t/repo", "2024-02"),
    ]:
        for time, relative in [("2024-01", -1), ("2024-02", 0)]:
            row: dict[str, Any] = {
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
                "has_parse_exclusion": 0,
                "parse_exclusion_records": 0,
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
            panel_rows.append(row)
    base_panel = pd.DataFrame(panel_rows)
    events = pd.DataFrame(
        [
            {
                "dataset_source": "treatment",
                "repo_name": "t/repo",
                "time": "2024-02",
                "function_event_id": "e1",
                BODY_COLUMN: "a",
                FUNCTION_KIND_COLUMN: "module_function",
                AGC_COLUMN: 1,
            },
            {
                "dataset_source": "treatment",
                "repo_name": "t/repo",
                "time": "2024-02",
                "function_event_id": "e2",
                BODY_COLUMN: "a",
                FUNCTION_KIND_COLUMN: "module_function",
                AGC_COLUMN: 1,
            },
            {
                "dataset_source": "control",
                "repo_name": "c/repo",
                "time": "2024-01",
                "function_event_id": "e3",
                BODY_COLUMN: "b",
                FUNCTION_KIND_COLUMN: "module_function",
                AGC_COLUMN: 0,
            },
        ]
    )
    outputs = build_panel(
        events,
        base_panel,
        "module_function",
        "range100_200",
        {
            "panel_rows": 4,
            "control_rows": 2,
            "treatment_rows": 2,
            "parse_exclusion_rows": 0,
            "regular_event_rows": 3,
            "regular_unique_bodies": 2,
            "agc_event_rows": 2,
            "agc_unique_bodies": 1,
        },
    )
    if not outputs["overall_pass"]:
        failed = outputs["checks"].loc[~outputs["checks"]["passed"]]
        raise AssertionError(f"Self-test failed:\n{failed.to_string(index=False)}")
    treatment_event = outputs["panel"].loc[
        (outputs["panel"]["repo_name"] == "t/repo")
        & (outputs["panel"]["time"] == "2024-02"),
        OUTCOME_COLUMN,
    ].iloc[0]
    if int(treatment_event) != 1:
        raise AssertionError("Duplicate event references were not deduplicated by body")
    if any(
        pattern in column.lower()
        for column in outputs["panel"].columns
        for pattern in FORBIDDEN_OUTPUT_PATTERNS
    ):
        raise AssertionError("Focused output unexpectedly contains HWC or ratio columns")


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
        args.function_kind,
        args.specification_name,
        {
            "panel_rows": args.expected_panel_rows,
            "control_rows": args.expected_control_rows,
            "treatment_rows": args.expected_treatment_rows,
            "parse_exclusion_rows": args.expected_parse_exclusion_rows,
            "regular_event_rows": args.expected_regular_event_rows,
            "regular_unique_bodies": args.expected_regular_unique_bodies,
            "agc_event_rows": args.expected_agc_event_rows,
            "agc_unique_bodies": args.expected_agc_unique_bodies,
        },
    )
    write_outputs(
        outputs,
        args.output_dir,
        args.event_classifications,
        args.base_panel,
    )

    summary = outputs["summary"]
    print("=" * 80)
    print("run-py-7e: prepare regular-function AGC unique-body DiD input")
    print("=" * 80)
    print(f"Status:                              {summary['status']}")
    print(f"Panel rows:                          {summary['panel_rows']}")
    print(f"Control rows:                        {summary['control_rows']}")
    print(f"Treatment rows:                      {summary['treatment_rows']}")
    print(f"Parse-clean rows:                    {summary['parse_clean_rows']}")
    print(f"Zero-outcome rows:                   {summary['zero_outcome_rows']}")
    print(f"Positive-outcome rows:               {summary['positive_outcome_rows']}")
    print(f"Regular event rows:                  {summary['regular_event_rows']}")
    print(f"Global regular unique bodies:        {summary['regular_unique_bodies']}")
    print(f"AGC-like regular event rows:         {summary['agc_regular_event_rows']}")
    print(
        "Global AGC-like regular unique bodies: "
        f"{summary['agc_regular_unique_bodies_global']}"
    )
    print(
        "AGC body repository-month occurrences: "
        f"{summary['agc_unique_body_repo_month_occurrences']}"
    )
    print(f"Failed checks:                       {summary['failed_checks']}")
    print(f"Output directory:                    {args.output_dir}")
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
