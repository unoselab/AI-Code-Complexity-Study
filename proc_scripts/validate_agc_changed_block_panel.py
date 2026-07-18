#!/usr/bin/env python3
"""Independently validate the AGC changed-block repository-month panel.

The validator checks the outputs produced by run-py-4a without importing or
calling the preparation script. It verifies panel preservation, repository-
month outcome arithmetic, block-level reaggregation, pair-level QC, ratio
availability, and analysis-sample selection patterns.

Primary arithmetic
------------------
changed blocks = changed AGC blocks + changed HWC blocks
AGC changed-block ratio = changed AGC blocks / changed blocks

AGC means AI-likely-generated code. HWC means human-likely-written code.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd


PANEL_KEY = ["dataset_source", "repo_name", "time"]
OUTCOME_KEY = ["dataset_source", "repo_name", "month"]
PAIR_KEY = ["dataset_source", "repo_name", "month"]
CLASSIFICATION_KEY = [
    "dataset_source",
    "repo_name",
    "month",
    "current_commit",
    "current_relative_path",
    "current_block_idx",
]
ALLOWED_SOURCES = {"treatment", "control"}
ALLOWED_OUTCOME_STATUSES = {
    "no_previous_month",
    "nonconsecutive_month",
    "same_commit",
    "ready",
    "git_diff_error",
}
ALLOWED_PAIR_STATUSES = {
    "no_previous_month",
    "nonconsecutive_month",
    "same_commit",
    "processed",
    "git_diff_error",
    "error",
}
ALLOWED_CHANGE_TYPES = {"unchanged", "moved_unchanged", "added", "modified"}
ALLOWED_BLOCK_KINDS = {"function_definition", "class_definition"}

METRIC_SPECS = [
    ("changed", "top_level"),
    ("added", "top_level"),
    ("modified", "top_level"),
    ("changed", "function"),
    ("changed", "class"),
]

OUTCOME_BASE_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_commit",
    "current_commit",
    "month_gap",
    "comparison_status",
]

PAIR_REQUIRED_COLUMNS = OUTCOME_BASE_COLUMNS + [
    "python_file_diff_rows",
    "current_regular_python_files",
    "previous_regular_python_files",
    "current_blocks_in_diff_files",
    "previous_blocks_in_diff_files",
    "unchanged_blocks",
    "moved_unchanged_blocks",
    "added_blocks",
    "modified_blocks",
    "deleted_blocks",
    "prediction_mismatches",
    "elapsed_seconds",
]

CLASSIFICATION_REQUIRED_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_commit",
    "current_commit",
    "file_status",
    "previous_relative_path",
    "current_relative_path",
    "current_content_sha256",
    "current_block_idx",
    "block_kind",
    "block_name",
    "start_line",
    "end_line",
    "ast_sequence_sha256",
    "code_sha256",
    "change_type",
    "matching_method",
    "previous_block_idx",
    "previous_block_name",
    "previous_start_line",
    "previous_end_line",
    "previous_ast_sequence_sha256",
    "pred_label",
    "code_label",
    "predicted_agc",
    "human_score",
    "human_decision_score",
    "agc_score",
    "score_mode",
    "model_key",
]

PREPARE_QC_FILES = [
    "agc_changed_block_prepare_summary.json",
    "agc_changed_block_prepare_checks.csv",
    "agc_changed_block_pair_qc.csv",
    "agc_changed_block_prediction_mismatches.csv",
    "agc_changed_block_errors.csv",
]


class ValidationRecorder:
    """Collect checks and preserve diagnostics before failing."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def check(
        self,
        category: str,
        name: str,
        actual: Any,
        expected: Any,
        passed: bool,
        detail: str = "",
    ) -> None:
        record = {
            "category": category,
            "check": name,
            "actual": actual,
            "expected": expected,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }
        self.checks.append(record)
        if not passed:
            self.errors.append(record.copy())

    def equal(
        self,
        category: str,
        name: str,
        actual: Any,
        expected: Any,
        detail: str = "",
    ) -> None:
        self.check(category, name, actual, expected, actual == expected, detail)

    def zero(
        self,
        category: str,
        name: str,
        actual: int,
        detail: str = "",
    ) -> None:
        self.equal(category, name, int(actual), 0, detail)


def metric_columns(scope: str, unit: str) -> tuple[str, str, str, str]:
    """Return total, AGC, HWC, and ratio column names."""
    return (
        f"{scope}_{unit}_blocks",
        f"{scope}_agc_{unit}_blocks",
        f"{scope}_hwc_{unit}_blocks",
        f"agc_{scope}_{unit}_block_ratio",
    )


def metric_columns_flat() -> list[str]:
    """Return all metric columns in stable order."""
    return [column for spec in METRIC_SPECS for column in metric_columns(*spec)]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate the strict AGC changed-block repository-month panel."
    )
    parser.add_argument("--input-panel", required=True, type=Path)
    parser.add_argument("--base-panel", required=True, type=Path)
    parser.add_argument("--repo-month-outcomes", required=True, type=Path)
    parser.add_argument("--block-classifications", required=True, type=Path)
    parser.add_argument("--prepare-qc-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--panel-label", default="strict")
    parser.add_argument("--chunksize", type=int, default=100_000)

    parser.add_argument("--expected-panel-rows", type=int, default=1633)
    parser.add_argument("--expected-repositories", type=int, default=220)
    parser.add_argument("--expected-treatment-rows", type=int, default=853)
    parser.add_argument("--expected-control-rows", type=int, default=780)
    parser.add_argument("--expected-treatment-repositories", type=int, default=100)
    parser.add_argument("--expected-control-repositories", type=int, default=120)
    parser.add_argument("--expected-post-rows", type=int, default=432)
    parser.add_argument("--expected-min-time", default="2024-01")
    parser.add_argument("--expected-max-time", default="2025-08")
    parser.add_argument("--expected-outcome-rows", type=int, default=3043)
    parser.add_argument("--expected-changed-blocks", type=int, default=163540)
    parser.add_argument("--expected-changed-agc-blocks", type=int, default=23595)
    parser.add_argument("--expected-changed-hwc-blocks", type=int, default=139945)
    parser.add_argument("--expected-ratio-rows", type=int, default=1127)
    parser.add_argument("--expected-score-mode", default="decision")
    parser.add_argument(
        "--expected-model-key",
        default="codesearchnet_codellama-7b_python_merged_4500ast_",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run lightweight arithmetic tests and exit.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    """Fail clearly when a required file is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_columns(df: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    """Fail clearly when required columns are absent."""
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv.tmp",
        prefix=f"{path.stem}.",
        dir=path.parent,
        delete=False,
        encoding="utf-8",
        newline="",
    ) as handle:
        temp_path = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temp_path, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json.tmp",
        prefix=f"{path.stem}.",
        dir=path.parent,
        delete=False,
        encoding="utf-8",
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)


def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object."""
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def normalize_key_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Normalize key columns without modifying the caller's frame."""
    output = frame.copy()
    for column in columns:
        output[column] = output[column].astype("string").str.strip()
    return output


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Convert a column to numeric values."""
    return pd.to_numeric(frame[column], errors="coerce")


def finite_integer_failure_count(series: pd.Series) -> int:
    """Count nonmissing values that are negative, nonfinite, or nonintegral."""
    values = pd.to_numeric(series, errors="coerce")
    original_nonmissing = series.notna()
    invalid_parse = original_nonmissing & values.isna()
    finite = np.isfinite(values.fillna(0).to_numpy(dtype=float))
    nonfinite = original_nonmissing & ~pd.Series(finite, index=series.index)
    negative = values.lt(0).fillna(False)
    noninteger = values.notna() & (values - np.round(values)).abs().gt(1e-12)
    return int((invalid_parse | nonfinite | negative | noninteger).sum())


def compare_base_columns(
    base_panel: pd.DataFrame,
    output_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Compare every original base-panel value after key alignment."""
    aligned_base = normalize_key_columns(base_panel, PANEL_KEY).set_index(PANEL_KEY)
    aligned_output = normalize_key_columns(output_panel, PANEL_KEY).set_index(PANEL_KEY)
    common_index = aligned_base.index.intersection(aligned_output.index)
    mismatch_rows: list[dict[str, Any]] = []

    for column in base_panel.columns:
        if column in PANEL_KEY or column not in output_panel.columns:
            continue
        left = aligned_base.loc[common_index, column]
        right = aligned_output.loc[common_index, column]

        left_num = pd.to_numeric(left, errors="coerce")
        right_num = pd.to_numeric(right, errors="coerce")
        numeric_candidate = bool(
            left.notna().eq(left_num.notna()).all()
            and right.notna().eq(right_num.notna()).all()
        )
        if numeric_candidate:
            same = pd.Series(
                np.isclose(
                    left_num.to_numpy(dtype=float),
                    right_num.to_numpy(dtype=float),
                    rtol=1e-10,
                    atol=1e-12,
                    equal_nan=True,
                ),
                index=common_index,
            )
        else:
            left_text = left.astype("string").fillna("<NA>").str.strip()
            right_text = right.astype("string").fillna("<NA>").str.strip()
            same = left_text.eq(right_text)

        for key in same.index[~same].tolist():
            key_tuple = key if isinstance(key, tuple) else (key,)
            mismatch_rows.append(
                {
                    **dict(zip(PANEL_KEY, key_tuple)),
                    "column": column,
                    "base_value": left.loc[key],
                    "output_value": right.loc[key],
                }
            )
    return pd.DataFrame(
        mismatch_rows,
        columns=PANEL_KEY + ["column", "base_value", "output_value"],
    )


def validate_metric_arithmetic(
    frame: pd.DataFrame,
    eligible_mask: pd.Series,
) -> tuple[int, int, int, int]:
    """Return count, ratio, range, and integer failure counts."""
    arithmetic_failures = 0
    ratio_failures = 0
    range_failures = 0
    integer_failures = 0

    for scope, unit in METRIC_SPECS:
        total_col, agc_col, hwc_col, ratio_col = metric_columns(scope, unit)
        total = numeric_series(frame, total_col)
        agc = numeric_series(frame, agc_col)
        hwc = numeric_series(frame, hwc_col)
        ratio = numeric_series(frame, ratio_col)

        subset = eligible_mask
        arithmetic_failures += int(
            (subset & total.notna() & agc.notna() & hwc.notna() & total.ne(agc + hwc)).sum()
        )
        expected_ratio = agc / total.where(total.ne(0))
        ratio_failures += int((subset & total.eq(0) & ratio.notna()).sum())
        ratio_failures += int(
            (
                subset
                & total.gt(0)
                & (
                    ratio.isna()
                    | (ratio - expected_ratio).abs().gt(1e-12)
                )
            ).sum()
        )
        range_failures += int((ratio.notna() & ~ratio.between(0, 1)).sum())
        integer_failures += sum(
            finite_integer_failure_count(frame.loc[subset, column])
            for column in [total_col, agc_col, hwc_col]
        )

    return (
        arithmetic_failures,
        ratio_failures,
        range_failures,
        integer_failures,
    )


def validate_decompositions(frame: pd.DataFrame, eligible_mask: pd.Series) -> int:
    """Count added/modified and function/class decomposition failures."""
    failures = 0
    for label in ["", "agc_", "hwc_"]:
        changed = numeric_series(frame, f"changed_{label}top_level_blocks")
        added = numeric_series(frame, f"added_{label}top_level_blocks")
        modified = numeric_series(frame, f"modified_{label}top_level_blocks")
        failures += int((eligible_mask & changed.ne(added + modified)).sum())

    for label in ["", "agc_", "hwc_"]:
        changed = numeric_series(frame, f"changed_{label}top_level_blocks")
        functions = numeric_series(frame, f"changed_{label}function_blocks")
        classes = numeric_series(frame, f"changed_{label}class_blocks")
        failures += int((eligible_mask & changed.ne(functions + classes)).sum())
    return failures


def aggregate_classification_chunks(
    path: Path,
    chunksize: int,
    expected_score_mode: str,
    expected_model_key: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate and reaggregate the block-level classification file."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, CLASSIFICATION_REQUIRED_COLUMNS, "block classifications")

    aggregate_parts: list[pd.DataFrame] = []
    diagnostic_rows: list[dict[str, Any]] = []
    change_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    seen_keys: set[tuple[str, ...]] = set()
    duplicate_keys = 0
    invalid_sources = 0
    invalid_change_types = 0
    invalid_block_kinds = 0
    invalid_predictions = 0
    label_mismatches = 0
    invalid_lines = 0
    semantic_failures = 0
    score_mode_mismatches = 0
    model_key_mismatches = 0
    total_rows = 0

    usecols = CLASSIFICATION_REQUIRED_COLUMNS
    dtype = {
        "dataset_source": "string",
        "repo_name": "string",
        "month": "string",
        "current_commit": "string",
        "current_relative_path": "string",
        "block_kind": "string",
        "change_type": "string",
        "code_label": "string",
        "score_mode": "string",
        "model_key": "string",
        "ast_sequence_sha256": "string",
        "previous_ast_sequence_sha256": "string",
        "previous_relative_path": "string",
    }

    for chunk_number, chunk in enumerate(
        pd.read_csv(path, usecols=usecols, dtype=dtype, chunksize=chunksize, low_memory=False),
        start=1,
    ):
        total_rows += len(chunk)
        for column in CLASSIFICATION_KEY:
            chunk[column] = chunk[column].astype("string").fillna("").str.strip()

        invalid_sources += int((~chunk["dataset_source"].isin(ALLOWED_SOURCES)).sum())
        invalid_change_types += int((~chunk["change_type"].isin(ALLOWED_CHANGE_TYPES)).sum())
        invalid_block_kinds += int((~chunk["block_kind"].isin(ALLOWED_BLOCK_KINDS)).sum())

        predicted = pd.to_numeric(chunk["predicted_agc"], errors="coerce")
        invalid_predictions += int((~predicted.isin([0, 1])).sum())
        expected_labels = predicted.map({0: "HWC", 1: "AGC"})
        label_mismatches += int(
            (predicted.isin([0, 1]) & chunk["code_label"].astype("string").ne(expected_labels)).sum()
        )

        start_line = pd.to_numeric(chunk["start_line"], errors="coerce")
        end_line = pd.to_numeric(chunk["end_line"], errors="coerce")
        invalid_lines += int(
            (start_line.isna() | end_line.isna() | start_line.lt(1) | end_line.lt(start_line)).sum()
        )

        current_ast = chunk["ast_sequence_sha256"].astype("string").fillna("")
        previous_ast = chunk["previous_ast_sequence_sha256"].astype("string").fillna("")
        previous_path = chunk["previous_relative_path"].astype("string").fillna("")
        current_path = chunk["current_relative_path"].astype("string").fillna("")
        change_type = chunk["change_type"].astype("string")

        semantic_failures += int(
            (change_type.eq("added") & previous_ast.ne("")).sum()
            + (change_type.eq("modified") & (previous_ast.eq("") | previous_ast.eq(current_ast))).sum()
            + (change_type.isin(["unchanged", "moved_unchanged"]) & previous_ast.ne(current_ast)).sum()
            + (change_type.eq("moved_unchanged") & previous_path.eq(current_path)).sum()
        )

        score_mode_mismatches += int(
            chunk["score_mode"].astype("string").ne(expected_score_mode).sum()
        )
        model_key_mismatches += int(
            chunk["model_key"].astype("string").ne(expected_model_key).sum()
        )

        key_values = chunk[CLASSIFICATION_KEY].astype("string").fillna("")
        for key in key_values.itertuples(index=False, name=None):
            key_tuple = tuple(str(value) for value in key)
            if key_tuple in seen_keys:
                duplicate_keys += 1
            else:
                seen_keys.add(key_tuple)

        change_counts.update(chunk["change_type"].dropna().astype(str).tolist())
        kind_counts.update(chunk["block_kind"].dropna().astype(str).tolist())

        changed = chunk.loc[chunk["change_type"].isin(["added", "modified"])].copy()
        if not changed.empty:
            changed["predicted_agc"] = pd.to_numeric(
                changed["predicted_agc"], errors="coerce"
            ).fillna(-1).astype(int)
            changed["one"] = 1
            changed["hwc"] = 1 - changed["predicted_agc"]
            changed["is_added"] = changed["change_type"].eq("added").astype(int)
            changed["is_modified"] = changed["change_type"].eq("modified").astype(int)
            changed["is_function"] = changed["block_kind"].eq("function_definition").astype(int)
            changed["is_class"] = changed["block_kind"].eq("class_definition").astype(int)
            changed["added_agc"] = changed["is_added"] * changed["predicted_agc"]
            changed["added_hwc"] = changed["is_added"] * changed["hwc"]
            changed["modified_agc"] = changed["is_modified"] * changed["predicted_agc"]
            changed["modified_hwc"] = changed["is_modified"] * changed["hwc"]
            changed["function_agc"] = changed["is_function"] * changed["predicted_agc"]
            changed["function_hwc"] = changed["is_function"] * changed["hwc"]
            changed["class_agc"] = changed["is_class"] * changed["predicted_agc"]
            changed["class_hwc"] = changed["is_class"] * changed["hwc"]

            group_cols = OUTCOME_KEY + ["current_commit"]
            grouped = changed.groupby(group_cols, dropna=False).agg(
                changed_top_level_blocks=("one", "sum"),
                changed_agc_top_level_blocks=("predicted_agc", "sum"),
                changed_hwc_top_level_blocks=("hwc", "sum"),
                added_top_level_blocks=("is_added", "sum"),
                added_agc_top_level_blocks=("added_agc", "sum"),
                added_hwc_top_level_blocks=("added_hwc", "sum"),
                modified_top_level_blocks=("is_modified", "sum"),
                modified_agc_top_level_blocks=("modified_agc", "sum"),
                modified_hwc_top_level_blocks=("modified_hwc", "sum"),
                changed_function_blocks=("is_function", "sum"),
                changed_agc_function_blocks=("function_agc", "sum"),
                changed_hwc_function_blocks=("function_hwc", "sum"),
                changed_class_blocks=("is_class", "sum"),
                changed_agc_class_blocks=("class_agc", "sum"),
                changed_hwc_class_blocks=("class_hwc", "sum"),
            ).reset_index()
            aggregate_parts.append(grouped)

        if chunk_number % 10 == 0:
            print(
                f"Classification validation: chunks={chunk_number} rows={total_rows}",
                flush=True,
            )

    if aggregate_parts:
        combined = pd.concat(aggregate_parts, ignore_index=True)
        sum_columns = [
            column
            for column in combined.columns
            if column not in OUTCOME_KEY + ["current_commit"]
        ]
        aggregate = (
            combined.groupby(OUTCOME_KEY + ["current_commit"], dropna=False)[sum_columns]
            .sum()
            .reset_index()
        )
    else:
        aggregate = pd.DataFrame(columns=OUTCOME_KEY + ["current_commit"])

    diagnostic_rows.extend(
        {"dimension": "change_type", "value": key, "rows": value}
        for key, value in sorted(change_counts.items())
    )
    diagnostic_rows.extend(
        {"dimension": "block_kind", "value": key, "rows": value}
        for key, value in sorted(kind_counts.items())
    )

    summary = {
        "classification_rows": int(total_rows),
        "duplicate_classification_keys": int(duplicate_keys),
        "invalid_sources": int(invalid_sources),
        "invalid_change_types": int(invalid_change_types),
        "invalid_block_kinds": int(invalid_block_kinds),
        "invalid_predictions": int(invalid_predictions),
        "code_label_mismatches": int(label_mismatches),
        "invalid_line_ranges": int(invalid_lines),
        "change_semantic_failures": int(semantic_failures),
        "score_mode_mismatches": int(score_mode_mismatches),
        "model_key_mismatches": int(model_key_mismatches),
        "change_type_counts": dict(sorted(change_counts.items())),
        "block_kind_counts": dict(sorted(kind_counts.items())),
    }
    return aggregate, pd.DataFrame(diagnostic_rows), summary


def compare_reaggregated_outcomes(
    outcomes: pd.DataFrame,
    aggregate: pd.DataFrame,
) -> pd.DataFrame:
    """Compare block-level reaggregation with saved repository-month outcomes."""
    metric_count_columns = [
        column
        for scope, unit in METRIC_SPECS
        for column in metric_columns(scope, unit)[:3]
    ]
    ready = outcomes.loc[outcomes["comparison_status"].eq("ready")].copy()
    ready = ready.merge(
        aggregate,
        on=OUTCOME_KEY + ["current_commit"],
        how="left",
        suffixes=("_saved", "_reaggregated"),
        validate="one_to_one",
    )
    mismatch_rows: list[dict[str, Any]] = []
    for column in metric_count_columns:
        saved = pd.to_numeric(ready[f"{column}_saved"], errors="coerce").fillna(0)
        rebuilt = pd.to_numeric(
            ready[f"{column}_reaggregated"], errors="coerce"
        ).fillna(0)
        mask = saved.ne(rebuilt)
        for index in ready.index[mask]:
            mismatch_rows.append(
                {
                    **{key: ready.at[index, key] for key in OUTCOME_KEY},
                    "current_commit": ready.at[index, "current_commit"],
                    "column": column,
                    "saved_value": saved.at[index],
                    "reaggregated_value": rebuilt.at[index],
                }
            )
    return pd.DataFrame(
        mismatch_rows,
        columns=OUTCOME_KEY
        + ["current_commit", "column", "saved_value", "reaggregated_value"],
    )


def build_outcome_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    """Summarize denominator and ratio coverage for all outcomes."""
    rows: list[dict[str, Any]] = []
    for scope, unit in METRIC_SPECS:
        total_col, _, _, ratio_col = metric_columns(scope, unit)
        total = numeric_series(panel, total_col)
        ratio = numeric_series(panel, ratio_col)
        rows.append(
            {
                "scope": scope,
                "unit": unit,
                "panel_rows": len(panel),
                "count_available_rows": int(total.notna().sum()),
                "positive_denominator_rows": int(total.gt(0).sum()),
                "zero_denominator_rows": int(total.eq(0).sum()),
                "count_unavailable_rows": int(total.isna().sum()),
                "ratio_available_rows": int(ratio.notna().sum()),
                "ratio_availability_rate": float(ratio.notna().mean()),
                "total_blocks": int(total.fillna(0).sum()),
            }
        )
    return pd.DataFrame(rows)


def add_analysis_group(panel: pd.DataFrame) -> pd.DataFrame:
    """Add control, treatment-pre, and treatment-post labels."""
    output = panel.copy()
    post = pd.to_numeric(output.get("post_event"), errors="coerce").fillna(0)
    output["analysis_group"] = np.select(
        [
            output["dataset_source"].eq("control"),
            output["dataset_source"].eq("treatment") & post.eq(0),
            output["dataset_source"].eq("treatment") & post.eq(1),
        ],
        ["control", "treatment_pre", "treatment_post"],
        default="unknown",
    )
    return output


def coverage_by_group(panel: pd.DataFrame) -> pd.DataFrame:
    """Summarize outcome availability by analysis group."""
    grouped_panel = add_analysis_group(panel)
    rows: list[dict[str, Any]] = []
    for group_name, group in grouped_panel.groupby("analysis_group", dropna=False):
        for scope, unit in METRIC_SPECS:
            total_col, _, _, ratio_col = metric_columns(scope, unit)
            total = numeric_series(group, total_col)
            ratio = numeric_series(group, ratio_col)
            rows.append(
                {
                    "analysis_group": group_name,
                    "scope": scope,
                    "unit": unit,
                    "rows": len(group),
                    "positive_denominator_rows": int(total.gt(0).sum()),
                    "zero_denominator_rows": int(total.eq(0).sum()),
                    "unavailable_rows": int(total.isna().sum()),
                    "ratio_available_rows": int(ratio.notna().sum()),
                    "ratio_availability_rate": float(ratio.notna().mean()),
                    "total_blocks": int(total.fillna(0).sum()),
                    "mean_ratio": float(ratio.mean()) if ratio.notna().any() else math.nan,
                    "median_ratio": float(ratio.median()) if ratio.notna().any() else math.nan,
                }
            )
    return pd.DataFrame(rows)


def coverage_by_event_time(panel: pd.DataFrame) -> pd.DataFrame:
    """Summarize primary outcome availability across treatment event time."""
    treatment = panel.loc[panel["dataset_source"].eq("treatment")].copy()
    event_time = pd.to_numeric(treatment.get("time_to_event"), errors="coerce")
    treatment["event_time_group"] = np.select(
        [event_time.lt(-6), event_time.between(-6, 6), event_time.gt(6)],
        ["before_-6", event_time.round().astype("Int64").astype("string"), "after_6"],
        default="missing",
    )
    total = numeric_series(treatment, "changed_top_level_blocks")
    treatment["positive_denominator"] = total.gt(0).astype(int)
    treatment["zero_denominator"] = total.eq(0).astype(int)
    treatment["unavailable"] = total.isna().astype(int)
    treatment["ratio_available"] = treatment[
        "agc_changed_top_level_block_ratio"
    ].notna().astype(int)
    return (
        treatment.groupby("event_time_group", dropna=False)
        .agg(
            rows=("repo_name", "size"),
            positive_denominator_rows=("positive_denominator", "sum"),
            zero_denominator_rows=("zero_denominator", "sum"),
            unavailable_rows=("unavailable", "sum"),
            ratio_available_rows=("ratio_available", "sum"),
        )
        .reset_index()
        .assign(
            ratio_availability_rate=lambda frame: frame["ratio_available_rows"]
            / frame["rows"]
        )
    )


def coverage_by_month(panel: pd.DataFrame) -> pd.DataFrame:
    """Summarize primary outcome availability by calendar month and source."""
    output = panel.copy()
    total = numeric_series(output, "changed_top_level_blocks")
    output["positive_denominator"] = total.gt(0).astype(int)
    output["zero_denominator"] = total.eq(0).astype(int)
    output["unavailable"] = total.isna().astype(int)
    output["ratio_available"] = output[
        "agc_changed_top_level_block_ratio"
    ].notna().astype(int)
    return (
        output.groupby(["time", "dataset_source"], dropna=False)
        .agg(
            rows=("repo_name", "size"),
            positive_denominator_rows=("positive_denominator", "sum"),
            zero_denominator_rows=("zero_denominator", "sum"),
            unavailable_rows=("unavailable", "sum"),
            ratio_available_rows=("ratio_available", "sum"),
        )
        .reset_index()
        .assign(
            ratio_availability_rate=lambda frame: frame["ratio_available_rows"]
            / frame["rows"]
        )
    )


def denominator_distribution(panel: pd.DataFrame) -> pd.DataFrame:
    """Describe the primary changed-block denominator by analysis group."""
    output = add_analysis_group(panel)
    total = numeric_series(output, "changed_top_level_blocks")
    output["changed_top_level_blocks_numeric"] = total
    rows: list[dict[str, Any]] = []
    for group_name, group in output.groupby("analysis_group", dropna=False):
        values = group["changed_top_level_blocks_numeric"].dropna()
        positive = values.loc[values.gt(0)]
        rows.append(
            {
                "analysis_group": group_name,
                "rows": len(group),
                "count_available_rows": int(values.size),
                "positive_denominator_rows": int(positive.size),
                "total_changed_blocks": int(values.sum()),
                "minimum": float(positive.min()) if not positive.empty else math.nan,
                "p25": float(positive.quantile(0.25)) if not positive.empty else math.nan,
                "median": float(positive.median()) if not positive.empty else math.nan,
                "p75": float(positive.quantile(0.75)) if not positive.empty else math.nan,
                "p90": float(positive.quantile(0.90)) if not positive.empty else math.nan,
                "p95": float(positive.quantile(0.95)) if not positive.empty else math.nan,
                "maximum": float(positive.max()) if not positive.empty else math.nan,
            }
        )
    return pd.DataFrame(rows)


def run_self_test() -> int:
    """Run lightweight arithmetic tests."""
    frame = pd.DataFrame(
        {
            "changed_top_level_blocks": [2, 0],
            "changed_agc_top_level_blocks": [1, 0],
            "changed_hwc_top_level_blocks": [1, 0],
            "agc_changed_top_level_block_ratio": [0.5, np.nan],
            "added_top_level_blocks": [1, 0],
            "added_agc_top_level_blocks": [1, 0],
            "added_hwc_top_level_blocks": [0, 0],
            "agc_added_top_level_block_ratio": [1.0, np.nan],
            "modified_top_level_blocks": [1, 0],
            "modified_agc_top_level_blocks": [0, 0],
            "modified_hwc_top_level_blocks": [1, 0],
            "agc_modified_top_level_block_ratio": [0.0, np.nan],
            "changed_function_blocks": [2, 0],
            "changed_agc_function_blocks": [1, 0],
            "changed_hwc_function_blocks": [1, 0],
            "agc_changed_function_block_ratio": [0.5, np.nan],
            "changed_class_blocks": [0, 0],
            "changed_agc_class_blocks": [0, 0],
            "changed_hwc_class_blocks": [0, 0],
            "agc_changed_class_block_ratio": [np.nan, np.nan],
        }
    )
    eligible = pd.Series([True, True])
    failures = validate_metric_arithmetic(frame, eligible)
    decomposition_failures = validate_decompositions(frame, eligible)
    if failures != (0, 0, 0, 0) or decomposition_failures != 0:
        print(f"SELF-TEST FAIL: arithmetic={failures} decomposition={decomposition_failures}")
        return 1
    print("SELF-TEST PASS")
    return 0


def main() -> int:
    """Run all validation checks and write diagnostics."""
    args = parse_args()
    if args.self_test:
        return run_self_test()

    started = time.time()
    recorder = ValidationRecorder()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    input_panel_path = args.input_panel.resolve()
    base_panel_path = args.base_panel.resolve()
    outcomes_path = args.repo_month_outcomes.resolve()
    classifications_path = args.block_classifications.resolve()
    prepare_qc_dir = args.prepare_qc_dir.resolve()

    require_file(input_panel_path, "changed-block panel")
    require_file(base_panel_path, "base AGC panel")
    require_file(outcomes_path, "repository-month changed-block outcomes")
    require_file(classifications_path, "block classifications")
    for filename in PREPARE_QC_FILES:
        require_file(prepare_qc_dir / filename, filename)

    print("=" * 72)
    print("Validate AGC changed-block repository-month panel")
    print(f"Panel:                 {input_panel_path}")
    print(f"Base panel:            {base_panel_path}")
    print(f"Outcomes:              {outcomes_path}")
    print(f"Classifications:       {classifications_path}")
    print(f"Preparation QC:        {prepare_qc_dir}")
    print(f"Validation output:     {output_dir}")
    print("=" * 72)

    panel = pd.read_csv(input_panel_path, low_memory=False)
    base_panel = pd.read_csv(base_panel_path, low_memory=False)
    outcomes = pd.read_csv(outcomes_path, low_memory=False)
    pair_qc = pd.read_csv(prepare_qc_dir / "agc_changed_block_pair_qc.csv", low_memory=False)
    prepare_checks = pd.read_csv(
        prepare_qc_dir / "agc_changed_block_prepare_checks.csv", low_memory=False
    )
    prepare_summary = read_json(
        prepare_qc_dir / "agc_changed_block_prepare_summary.json"
    )
    prediction_mismatches = pd.read_csv(
        prepare_qc_dir / "agc_changed_block_prediction_mismatches.csv",
        low_memory=False,
    )
    prepare_errors = pd.read_csv(
        prepare_qc_dir / "agc_changed_block_errors.csv", low_memory=False
    )

    required_panel_columns = (
        list(base_panel.columns)
        + ["comparison_status"]
        + metric_columns_flat()
        + [
            "analysis_ready_agc_changed_block_paper_ncloc",
            "analysis_ready_agc_changed_block_python_snapshot_ncloc",
        ]
    )
    require_columns(panel, required_panel_columns, "changed-block panel")
    require_columns(base_panel, PANEL_KEY, "base panel")
    require_columns(
        outcomes,
        OUTCOME_BASE_COLUMNS + metric_columns_flat(),
        "repository-month outcomes",
    )
    require_columns(pair_qc, PAIR_REQUIRED_COLUMNS, "pair QC")

    panel = normalize_key_columns(panel, PANEL_KEY)
    base_panel = normalize_key_columns(base_panel, PANEL_KEY)
    outcomes = normalize_key_columns(outcomes, OUTCOME_KEY + ["current_commit"])
    pair_qc = normalize_key_columns(pair_qc, PAIR_KEY + ["current_commit"])

    # Preparation-stage checks.
    recorder.equal("upstream", "prepare_summary_status", prepare_summary.get("status"), "PASS")
    recorder.equal(
        "upstream",
        "prepare_summary_checks_failed",
        int(prepare_summary.get("checks_failed", -1)),
        0,
    )
    prepare_failed = int(
        pd.to_numeric(prepare_checks.get("passed"), errors="coerce").fillna(0).eq(0).sum()
    )
    recorder.zero("upstream", "prepare_checks_failed", prepare_failed)
    recorder.zero("upstream", "prediction_mismatch_rows", len(prediction_mismatches))
    recorder.zero("upstream", "prepare_error_rows", len(prepare_errors))

    # Panel identity and preservation.
    recorder.equal("panel", "panel_rows", len(panel), args.expected_panel_rows)
    repositories = panel[["dataset_source", "repo_name"]].drop_duplicates()
    recorder.equal("panel", "repositories", len(repositories), args.expected_repositories)
    recorder.zero("panel", "duplicate_panel_keys", int(panel.duplicated(PANEL_KEY).sum()))
    recorder.zero(
        "panel",
        "invalid_dataset_sources",
        int((~panel["dataset_source"].isin(ALLOWED_SOURCES)).sum()),
    )
    recorder.equal(
        "panel",
        "treatment_rows",
        int(panel["dataset_source"].eq("treatment").sum()),
        args.expected_treatment_rows,
    )
    recorder.equal(
        "panel",
        "control_rows",
        int(panel["dataset_source"].eq("control").sum()),
        args.expected_control_rows,
    )
    recorder.equal(
        "panel",
        "treatment_repositories",
        int(repositories["dataset_source"].eq("treatment").sum()),
        args.expected_treatment_repositories,
    )
    recorder.equal(
        "panel",
        "control_repositories",
        int(repositories["dataset_source"].eq("control").sum()),
        args.expected_control_repositories,
    )
    recorder.equal(
        "panel",
        "post_rows",
        int(pd.to_numeric(panel["post_event"], errors="coerce").eq(1).sum()),
        args.expected_post_rows,
    )
    recorder.equal("panel", "minimum_time", str(panel["time"].min()), args.expected_min_time)
    recorder.equal("panel", "maximum_time", str(panel["time"].max()), args.expected_max_time)

    base_keys = set(map(tuple, base_panel[PANEL_KEY].itertuples(index=False, name=None)))
    panel_keys = set(map(tuple, panel[PANEL_KEY].itertuples(index=False, name=None)))
    key_mismatch_rows = []
    for key in sorted(base_keys - panel_keys):
        key_mismatch_rows.append({**dict(zip(PANEL_KEY, key)), "location": "base_only"})
    for key in sorted(panel_keys - base_keys):
        key_mismatch_rows.append({**dict(zip(PANEL_KEY, key)), "location": "output_only"})
    panel_key_mismatches = pd.DataFrame(
        key_mismatch_rows, columns=PANEL_KEY + ["location"]
    )
    recorder.zero("panel", "base_panel_key_mismatches", len(panel_key_mismatches))

    base_value_mismatches = compare_base_columns(base_panel, panel)
    recorder.zero("panel", "base_panel_value_mismatches", len(base_value_mismatches))

    # Outcome table validation.
    recorder.equal("outcomes", "outcome_rows", len(outcomes), args.expected_outcome_rows)
    recorder.zero("outcomes", "duplicate_outcome_keys", int(outcomes.duplicated(OUTCOME_KEY).sum()))
    recorder.zero(
        "outcomes",
        "invalid_dataset_sources",
        int((~outcomes["dataset_source"].isin(ALLOWED_SOURCES)).sum()),
    )
    recorder.zero(
        "outcomes",
        "invalid_comparison_statuses",
        int((~outcomes["comparison_status"].isin(ALLOWED_OUTCOME_STATUSES)).sum()),
    )
    recorder.zero(
        "outcomes",
        "git_diff_error_status_rows",
        int(outcomes["comparison_status"].eq("git_diff_error").sum()),
    )

    ready = outcomes["comparison_status"].eq("ready")
    unavailable = outcomes["comparison_status"].isin(
        ["no_previous_month", "nonconsecutive_month", "git_diff_error"]
    )
    same_commit = outcomes["comparison_status"].eq("same_commit")

    metric_counts = [
        column
        for scope, unit in METRIC_SPECS
        for column in metric_columns(scope, unit)[:3]
    ]
    unavailable_nonmissing = int(outcomes.loc[unavailable, metric_counts].notna().sum().sum())
    same_commit_nonzero = int(
        pd.concat(
            [numeric_series(outcomes.loc[same_commit], column) for column in metric_counts],
            axis=1,
        ).fillna(0).ne(0).sum().sum()
    ) if same_commit.any() else 0
    ready_missing_counts = int(outcomes.loc[ready, metric_counts].isna().sum().sum())
    recorder.zero("outcomes", "unavailable_status_nonmissing_counts", unavailable_nonmissing)
    recorder.zero("outcomes", "same_commit_nonzero_counts", same_commit_nonzero)
    recorder.zero("outcomes", "ready_status_missing_counts", ready_missing_counts)

    arithmetic = validate_metric_arithmetic(outcomes, ready | same_commit)
    recorder.zero("outcomes", "agc_hwc_arithmetic_failures", arithmetic[0])
    recorder.zero("outcomes", "ratio_arithmetic_failures", arithmetic[1])
    recorder.zero("outcomes", "ratio_range_failures", arithmetic[2])
    recorder.zero("outcomes", "count_integer_failures", arithmetic[3])
    recorder.zero(
        "outcomes",
        "decomposition_failures",
        validate_decompositions(outcomes, ready | same_commit),
    )

    changed_total = int(numeric_series(outcomes, "changed_top_level_blocks").fillna(0).sum())
    changed_agc = int(numeric_series(outcomes, "changed_agc_top_level_blocks").fillna(0).sum())
    changed_hwc = int(numeric_series(outcomes, "changed_hwc_top_level_blocks").fillna(0).sum())
    ratio_rows = int(outcomes["agc_changed_top_level_block_ratio"].notna().sum())
    recorder.equal("outcomes", "changed_top_level_blocks", changed_total, args.expected_changed_blocks)
    recorder.equal("outcomes", "changed_agc_top_level_blocks", changed_agc, args.expected_changed_agc_blocks)
    recorder.equal("outcomes", "changed_hwc_top_level_blocks", changed_hwc, args.expected_changed_hwc_blocks)
    recorder.equal("outcomes", "primary_ratio_rows", ratio_rows, args.expected_ratio_rows)
    recorder.equal(
        "outcomes",
        "global_changed_arithmetic",
        changed_total,
        changed_agc + changed_hwc,
    )

    # Pair-level QC checks.
    recorder.equal("pair_qc", "pair_rows", len(pair_qc), args.expected_outcome_rows)
    recorder.zero("pair_qc", "duplicate_pair_keys", int(pair_qc.duplicated(PAIR_KEY).sum()))
    recorder.zero(
        "pair_qc",
        "invalid_pair_statuses",
        int((~pair_qc["comparison_status"].isin(ALLOWED_PAIR_STATUSES)).sum()),
    )
    recorder.zero(
        "pair_qc",
        "error_status_rows",
        int(pair_qc["comparison_status"].isin(["error", "git_diff_error"]).sum()),
    )
    processed = pair_qc["comparison_status"].eq("processed")
    pair_prediction_mismatches = int(
        numeric_series(pair_qc.loc[processed], "prediction_mismatches").fillna(0).sum()
    )
    recorder.zero("pair_qc", "prediction_mismatches", pair_prediction_mismatches)

    pair_changed = numeric_series(pair_qc, "added_blocks").fillna(0) + numeric_series(
        pair_qc, "modified_blocks"
    ).fillna(0)
    recorder.equal(
        "pair_qc",
        "pair_changed_block_sum",
        int(pair_changed.sum()),
        changed_total,
    )

    pair_compare = outcomes.merge(
        pair_qc[
            PAIR_KEY
            + ["current_commit", "comparison_status", "added_blocks", "modified_blocks"]
        ].rename(columns={"comparison_status": "pair_comparison_status"}),
        on=PAIR_KEY + ["current_commit"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    pair_key_mismatches = int(pair_compare["_merge"].ne("both").sum())
    pair_count_mismatches = int(
        (
            pair_compare["_merge"].eq("both")
            & pair_compare["comparison_status"].eq("ready")
            & (
                numeric_series(pair_compare, "changed_top_level_blocks").fillna(0)
                != numeric_series(pair_compare, "added_blocks").fillna(0)
                + numeric_series(pair_compare, "modified_blocks").fillna(0)
            )
        ).sum()
    )
    recorder.zero("pair_qc", "outcome_pair_key_mismatches", pair_key_mismatches)
    recorder.zero("pair_qc", "outcome_pair_count_mismatches", pair_count_mismatches)

    # Panel-to-outcome join validation.
    panel_outcome = panel.merge(
        outcomes.rename(columns={"month": "time", "current_commit": "latest_commit"})[
            ["dataset_source", "repo_name", "time", "latest_commit", "comparison_status"]
            + metric_columns_flat()
        ],
        on=["dataset_source", "repo_name", "time", "latest_commit"],
        how="left",
        suffixes=("_panel", "_outcome"),
        indicator=True,
        validate="one_to_one",
    )
    panel_outcome_key_mismatches = int(panel_outcome["_merge"].ne("both").sum())
    panel_outcome_value_mismatches = 0
    for column in ["comparison_status"] + metric_columns_flat():
        left = panel_outcome[f"{column}_panel"]
        right = panel_outcome[f"{column}_outcome"]
        if column.endswith("_ratio"):
            left_num = pd.to_numeric(left, errors="coerce")
            right_num = pd.to_numeric(right, errors="coerce")
            equal = np.isclose(
                left_num.to_numpy(dtype=float),
                right_num.to_numpy(dtype=float),
                rtol=1e-10,
                atol=1e-12,
                equal_nan=True,
            )
            panel_outcome_value_mismatches += int((~equal).sum())
        elif column == "comparison_status":
            panel_outcome_value_mismatches += int(
                left.astype("string").fillna("<NA>").ne(
                    right.astype("string").fillna("<NA>")
                ).sum()
            )
        else:
            panel_outcome_value_mismatches += int(
                pd.to_numeric(left, errors="coerce").fillna(-1).ne(
                    pd.to_numeric(right, errors="coerce").fillna(-1)
                ).sum()
            )
    recorder.zero("cross_file", "panel_outcome_key_mismatches", panel_outcome_key_mismatches)
    recorder.zero("cross_file", "panel_outcome_value_mismatches", panel_outcome_value_mismatches)

    paper_required = [
        "agc_changed_top_level_block_ratio",
        "age",
        "contributors",
        "stars",
        "issues",
        "ncloc_paper",
    ]
    snapshot_required = [
        "agc_changed_top_level_block_ratio",
        "age",
        "contributors",
        "stars",
        "issues",
        "ncloc_python_snapshot",
    ]
    expected_paper_ready = panel[paper_required].notna().all(axis=1).astype(int)
    expected_snapshot_ready = panel[snapshot_required].notna().all(axis=1).astype(int)
    recorder.zero(
        "panel",
        "paper_analysis_ready_flag_mismatches",
        int(
            pd.to_numeric(
                panel["analysis_ready_agc_changed_block_paper_ncloc"],
                errors="coerce",
            ).fillna(-1).ne(expected_paper_ready).sum()
        ),
    )
    recorder.zero(
        "panel",
        "snapshot_analysis_ready_flag_mismatches",
        int(
            pd.to_numeric(
                panel["analysis_ready_agc_changed_block_python_snapshot_ncloc"],
                errors="coerce",
            ).fillna(-1).ne(expected_snapshot_ready).sum()
        ),
    )

    # Independent block-level reaggregation.
    classification_aggregate, classification_summary_table, classification_summary = (
        aggregate_classification_chunks(
            classifications_path,
            args.chunksize,
            args.expected_score_mode,
            args.expected_model_key,
        )
    )
    for key in [
        "duplicate_classification_keys",
        "invalid_sources",
        "invalid_change_types",
        "invalid_block_kinds",
        "invalid_predictions",
        "code_label_mismatches",
        "invalid_line_ranges",
        "change_semantic_failures",
        "score_mode_mismatches",
        "model_key_mismatches",
    ]:
        recorder.zero("classifications", key, int(classification_summary[key]))

    reaggregation_mismatches = compare_reaggregated_outcomes(
        outcomes,
        classification_aggregate,
    )
    recorder.zero(
        "classifications",
        "repository_month_reaggregation_mismatches",
        len(reaggregation_mismatches),
    )
    recorder.equal(
        "classifications",
        "classification_rows_match_prepare_summary",
        int(classification_summary["classification_rows"]),
        int(prepare_summary.get("classification_rows", -1)),
    )
    recorder.equal(
        "classifications",
        "added_rows_match_pair_qc",
        int(classification_summary["change_type_counts"].get("added", 0)),
        int(numeric_series(pair_qc, "added_blocks").fillna(0).sum()),
    )
    recorder.equal(
        "classifications",
        "modified_rows_match_pair_qc",
        int(classification_summary["change_type_counts"].get("modified", 0)),
        int(numeric_series(pair_qc, "modified_blocks").fillna(0).sum()),
    )
    recorder.equal(
        "classifications",
        "unchanged_rows_match_pair_qc",
        int(classification_summary["change_type_counts"].get("unchanged", 0)),
        int(numeric_series(pair_qc, "unchanged_blocks").fillna(0).sum()),
    )
    recorder.equal(
        "classifications",
        "moved_unchanged_rows_match_pair_qc",
        int(classification_summary["change_type_counts"].get("moved_unchanged", 0)),
        int(numeric_series(pair_qc, "moved_unchanged_blocks").fillna(0).sum()),
    )

    # Selection and coverage diagnostics.
    outcome_coverage = build_outcome_coverage(panel)
    group_coverage = coverage_by_group(panel)
    event_time_coverage = coverage_by_event_time(panel)
    month_coverage = coverage_by_month(panel)
    denominator_summary = denominator_distribution(panel)

    unknown_group_rows = int(
        add_analysis_group(panel)["analysis_group"].eq("unknown").sum()
    )
    recorder.zero("selection", "unknown_analysis_group_rows", unknown_group_rows)

    # Persist all diagnostics before deciding the exit status.
    checks_frame = pd.DataFrame(recorder.checks)
    errors_frame = pd.DataFrame(
        recorder.errors,
        columns=["category", "check", "actual", "expected", "status", "detail"],
    )
    status = "PASS" if errors_frame.empty else "FAIL"
    summary = {
        "status": status,
        "panel_label": args.panel_label,
        "checks_total": int(len(checks_frame)),
        "checks_passed": int(checks_frame["status"].eq("PASS").sum()),
        "checks_failed": int(checks_frame["status"].eq("FAIL").sum()),
        "panel_rows": int(len(panel)),
        "repositories": int(len(repositories)),
        "outcome_rows": int(len(outcomes)),
        "classification_rows": int(classification_summary["classification_rows"]),
        "changed_top_level_blocks": changed_total,
        "changed_agc_top_level_blocks": changed_agc,
        "changed_hwc_top_level_blocks": changed_hwc,
        "repo_months_with_primary_ratio": ratio_rows,
        "repo_months_without_primary_ratio": int(len(panel) - ratio_rows),
        "global_block_weighted_agc_ratio": (
            float(changed_agc / changed_total) if changed_total else None
        ),
        "paper_analysis_ready_rows": int(expected_paper_ready.sum()),
        "snapshot_analysis_ready_rows": int(expected_snapshot_ready.sum()),
        "pair_status_counts": {
            str(key): int(value)
            for key, value in pair_qc["comparison_status"].value_counts(dropna=False).items()
        },
        "outcome_status_counts": {
            str(key): int(value)
            for key, value in outcomes["comparison_status"].value_counts(dropna=False).items()
        },
        "classification_change_type_counts": classification_summary[
            "change_type_counts"
        ],
        "classification_block_kind_counts": classification_summary[
            "block_kind_counts"
        ],
        "elapsed_seconds": round(time.time() - started, 3),
        "input_panel": str(input_panel_path),
        "base_panel": str(base_panel_path),
        "repo_month_outcomes": str(outcomes_path),
        "block_classifications": str(classifications_path),
        "prepare_qc_dir": str(prepare_qc_dir),
    }

    atomic_write_csv(
        checks_frame,
        output_dir / "agc_changed_block_panel_validation_checks.csv",
    )
    atomic_write_csv(
        errors_frame,
        output_dir / "agc_changed_block_panel_validation_errors.csv",
    )
    atomic_write_csv(
        panel_key_mismatches,
        output_dir / "agc_changed_block_panel_key_mismatches.csv",
    )
    atomic_write_csv(
        base_value_mismatches,
        output_dir / "agc_changed_block_base_value_mismatches.csv",
    )
    atomic_write_csv(
        reaggregation_mismatches,
        output_dir / "agc_changed_block_reaggregation_mismatches.csv",
    )
    atomic_write_csv(
        classification_summary_table,
        output_dir / "agc_changed_block_classification_summary.csv",
    )
    atomic_write_csv(
        outcome_coverage,
        output_dir / "agc_changed_block_outcome_coverage.csv",
    )
    atomic_write_csv(
        group_coverage,
        output_dir / "agc_changed_block_ratio_coverage_by_group.csv",
    )
    atomic_write_csv(
        event_time_coverage,
        output_dir / "agc_changed_block_ratio_coverage_by_event_time.csv",
    )
    atomic_write_csv(
        month_coverage,
        output_dir / "agc_changed_block_ratio_coverage_by_month.csv",
    )
    atomic_write_csv(
        denominator_summary,
        output_dir / "agc_changed_block_denominator_distribution.csv",
    )
    atomic_write_json(
        summary,
        output_dir / "agc_changed_block_panel_validation_summary.json",
    )

    print("=" * 72)
    print("AGC changed-block panel validation")
    print(f"Status:                    {status}")
    print(f"Checks passed:             {summary['checks_passed']}/{summary['checks_total']}")
    print(f"Panel rows:                {summary['panel_rows']}")
    print(f"Repositories:              {summary['repositories']}")
    print(f"Changed top-level blocks:  {changed_total}")
    print(f"Changed AGC blocks:        {changed_agc}")
    print(f"Changed HWC blocks:        {changed_hwc}")
    print(f"Repo-months with ratio:    {ratio_rows}")
    print(f"Validation output:         {output_dir}")
    print("=" * 72)

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
