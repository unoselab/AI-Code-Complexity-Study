#!/usr/bin/env python3
"""Prepare the covariance-aware regular-function count-contrast DiD input.

For every locked repository-month, the outcome is constructed before model
estimation as:

    AGC-like non-testing regular-function unique bodies
    minus AGC-like testing regular-function unique bodies

Running the same linear Borusyak imputation DiD on this row-level difference
estimates ATT_other - ATT_testing while retaining their covariance in the
clustered uncertainty calculation. Negative outcome values are valid and must
not be log transformed.

This script only prepares and validates the contrast panel. It does not
estimate ATT, standard errors, confidence intervals, or p-values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


SCRIPT_VERSION = "run-py-7f10-v1"
UPSTREAM_SCHEMA_VERSION = "run-py-7f08-v1"
TAXONOMY_STATUS = "FROZEN_BINARY"
TAXONOMY_VERSION = "testing-vs-other-functions-v1"

KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
COUNT_COLUMN = "npr_agc_regular_module_function_unique_bodies"
LOG_COLUMN = "log1p_npr_agc_regular_module_function_unique_bodies"
HAS_COLUMN = "has_npr_agc_regular_module_function_unique_body"
ZERO_COLUMN = "zero_npr_agc_regular_module_function_unique_body_month"
GROUP_COLUMN = "regular_function_outcome_group"
GROUP_LABEL_COLUMN = "regular_function_outcome_label"
GROUP_DEFINITION_COLUMN = "regular_function_outcome_definition"

TESTING_COUNT_COLUMN = (
    "npr_agc_testing_regular_module_function_unique_bodies"
)
OTHER_COUNT_COLUMN = (
    "npr_agc_other_regular_module_function_unique_bodies"
)
ALL_COUNT_COLUMN = "npr_agc_all_regular_module_function_unique_bodies"
CONTRAST_COLUMN = (
    "npr_agc_other_minus_testing_regular_module_function_unique_bodies"
)
POSITIVE_COLUMN = "has_positive_npr_agc_other_minus_testing_contrast"
NEGATIVE_COLUMN = "has_negative_npr_agc_other_minus_testing_contrast"
CONTRAST_ZERO_COLUMN = "zero_npr_agc_other_minus_testing_contrast"

CONTRAST_ID = "other_minus_testing"
CONTRAST_LABEL = (
    "AGC-like non-testing minus testing regular-function unique bodies"
)
CONTRAST_DEFINITION = (
    "Repository-month raw-count difference: distinct AGC-like non-testing "
    "regular-function bodies minus distinct AGC-like testing and test-support "
    "regular-function bodies."
)

VARIANT_COLUMNS = {
    COUNT_COLUMN,
    LOG_COLUMN,
    HAS_COLUMN,
    ZERO_COLUMN,
    GROUP_COLUMN,
    GROUP_LABEL_COLUMN,
    GROUP_DEFINITION_COLUMN,
}

REQUIRED_COLUMNS = {
    *KEY_COLUMNS,
    "event",
    "time_to_event",
    "post_event",
    "log1p_age",
    "ncloc_python_snapshot",
    "log1p_contributors",
    "log1p_stars",
    "log1p_issues",
    "has_parse_exclusion",
    "npr_detection_complete",
    "npr_specification",
    "treatment_group",
    "regular_function_scope",
    "agc_count_unit",
    "agc_outcome_scale",
    "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc",
    "regular_function_outcome_schema_version",
    "regular_function_taxonomy_status",
    "regular_function_taxonomy_version",
    *VARIANT_COLUMNS,
}

OUTPUT_FILES = {
    "panel": "run-py-7f10-did-input-other-minus-testing-count-contrast.csv",
    "summary": "run-py-7f10-count-contrast-summary.csv",
    "qc": "run-py-7f10-count-contrast-input-qc.csv",
    "metadata": "run-py-7f10-count-contrast-input-metadata.json",
}


class ValidationError(RuntimeError):
    """Raised when an input or output contract is violated."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--testing-panel", type=Path)
    parser.add_argument("--other-panel", type=Path)
    parser.add_argument("--all-panel", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-rows", type=int, default=1521)
    parser.add_argument("--expected-repositories", type=int, default=218)
    parser.add_argument("--expected-testing-total", type=int, default=627)
    parser.add_argument("--expected-other-total", type=int, default=1622)
    parser.add_argument("--expected-all-total", type=int, default=2249)
    parser.add_argument("--expected-contrast-total", type=int, default=995)
    parser.add_argument("--expected-negative-rows", type=int, default=112)
    parser.add_argument("--expected-zero-rows", type=int, default=1064)
    parser.add_argument("--expected-positive-rows", type=int, default=345)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValidationError(f"CSV has no header: {path}")
            return list(reader.fieldnames), list(reader)
    except OSError as exc:
        raise ValidationError(f"Cannot read CSV {path}: {exc}") from exc


def parse_nonnegative_integer(value: str, label: str) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be numeric; found {value!r}") from exc
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValidationError(
            f"{label} must be a nonnegative integer; found {value!r}"
        )
    return int(numeric)


def parse_bool01(value: str, label: str) -> int:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "1.0"}:
        return 1
    if normalized in {"0", "false", "0.0"}:
        return 0
    raise ValidationError(f"{label} must be binary; found {value!r}")


def validate_log1p(raw_count: int, value: str, label: str) -> None:
    try:
        observed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be numeric; found {value!r}") from exc
    if not math.isfinite(observed) or not math.isclose(
        observed, math.log1p(raw_count), rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValidationError(
            f"{label} does not equal log1p({raw_count}); found {value!r}"
        )


def require_paths(args: argparse.Namespace) -> None:
    for name in ("testing_panel", "other_panel", "all_panel", "output_dir"):
        if getattr(args, name) is None:
            raise ValidationError(f"--{name.replace('_', '-')} is required")
    for name in ("testing_panel", "other_panel", "all_panel"):
        path = getattr(args, name)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValidationError(f"Missing or empty input: {path}")


def validate_expected_values(args: argparse.Namespace) -> None:
    positive_names = (
        "expected_rows",
        "expected_repositories",
        "expected_testing_total",
        "expected_other_total",
        "expected_all_total",
        "expected_contrast_total",
        "expected_negative_rows",
        "expected_zero_rows",
        "expected_positive_rows",
    )
    for name in positive_names:
        value = getattr(args, name)
        if value <= 0:
            raise ValidationError(f"--{name.replace('_', '-')} must be positive")
    if args.expected_testing_total + args.expected_other_total != args.expected_all_total:
        raise ValidationError("Expected testing + other totals must equal all total")
    if args.expected_other_total - args.expected_testing_total != args.expected_contrast_total:
        raise ValidationError("Expected other - testing total must equal contrast total")
    if (
        args.expected_negative_rows
        + args.expected_zero_rows
        + args.expected_positive_rows
        != args.expected_rows
    ):
        raise ValidationError("Expected sign-row counts must sum to expected rows")


def validate_panel_contract(
    fields: list[str],
    rows: list[dict[str, str]],
    expected_group: str,
    expected_rows: int,
    expected_repositories: int,
) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(fields))
    if missing:
        raise ValidationError(
            f"{expected_group} panel missing columns: {', '.join(missing)}"
        )
    if len(rows) != expected_rows:
        raise ValidationError(
            f"{expected_group} rows={len(rows)}; expected {expected_rows}"
        )

    keys: set[tuple[str, str, str]] = set()
    repositories: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        key = tuple(row[column].strip() for column in KEY_COLUMNS)
        if any(not item for item in key):
            raise ValidationError(f"{expected_group} row {row_number} has empty key")
        if key in keys:
            raise ValidationError(
                f"{expected_group} row {row_number} duplicates key {key}"
            )
        keys.add(key)
        repositories.add(row["repo_name"])

        if row[GROUP_COLUMN] != expected_group:
            raise ValidationError(
                f"{expected_group} row {row_number} has group {row[GROUP_COLUMN]!r}"
            )
        if row["regular_function_outcome_schema_version"] != UPSTREAM_SCHEMA_VERSION:
            raise ValidationError("Unexpected run-py-7f08 schema version")
        if row["regular_function_taxonomy_status"] != TAXONOMY_STATUS:
            raise ValidationError("Binary taxonomy is not frozen")
        if row["regular_function_taxonomy_version"] != TAXONOMY_VERSION:
            raise ValidationError("Unexpected binary taxonomy version")
        if row["regular_function_scope"] != "module_function":
            raise ValidationError("Unexpected regular-function scope")
        if row["agc_outcome_scale"] != "raw_count":
            raise ValidationError("Upstream outcome scale must be raw_count")
        if row["agc_count_unit"] != (
            "distinct_function_body_sha256_per_repository_month"
        ):
            raise ValidationError("Unexpected upstream count unit")
        if row["npr_specification"] != "range100_200":
            raise ValidationError("Unexpected NPR specification")
        if row["dataset_source"] not in {"control", "treatment"}:
            raise ValidationError("Unexpected dataset_source")
        if row["treatment_group"] != row["dataset_source"]:
            raise ValidationError("treatment_group disagrees with dataset_source")
        if parse_bool01(
            row["npr_detection_complete"],
            f"{expected_group} row {row_number} npr_detection_complete",
        ) != 1:
            raise ValidationError("npr_detection_complete must be true")
        if parse_bool01(
            row[
                "analysis_ready_regular_module_function_agc_unique_body_"
                "python_snapshot_ncloc"
            ],
            f"{expected_group} row {row_number} analysis readiness",
        ) != 1:
            raise ValidationError("All contrast rows must be model-ready")
        if parse_bool01(
            row["has_parse_exclusion"],
            f"{expected_group} row {row_number} parse exclusion",
        ) != 0:
            raise ValidationError("Contrast input must exclude parse-failure rows")

        count = parse_nonnegative_integer(
            row[COUNT_COLUMN], f"{expected_group} row {row_number} count"
        )
        validate_log1p(
            count, row[LOG_COLUMN], f"{expected_group} row {row_number} log count"
        )
        if parse_bool01(row[HAS_COLUMN], "has outcome") != int(count > 0):
            raise ValidationError(f"{expected_group} row {row_number} has-flag mismatch")
        if parse_bool01(row[ZERO_COLUMN], "zero outcome") != int(count == 0):
            raise ValidationError(f"{expected_group} row {row_number} zero-flag mismatch")

    if len(repositories) != expected_repositories:
        raise ValidationError(
            f"{expected_group} repositories={len(repositories)}; "
            f"expected {expected_repositories}"
        )


def derive_contrast(testing: int, other: int, all_count: int) -> int:
    if testing + other != all_count:
        raise ValidationError(
            f"Binary-group reconciliation failed: {testing} + {other} != {all_count}"
        )
    return other - testing


def build_outputs(args: argparse.Namespace) -> tuple[
    list[str], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    testing_fields, testing_rows = read_csv(args.testing_panel)
    other_fields, other_rows = read_csv(args.other_panel)
    all_fields, all_rows = read_csv(args.all_panel)

    if not (testing_fields == other_fields == all_fields):
        raise ValidationError("The three upstream panels do not share one column order")

    validate_panel_contract(
        testing_fields,
        testing_rows,
        "testing",
        args.expected_rows,
        args.expected_repositories,
    )
    validate_panel_contract(
        other_fields,
        other_rows,
        "other_functions",
        args.expected_rows,
        args.expected_repositories,
    )
    validate_panel_contract(
        all_fields,
        all_rows,
        "all_regular_functions",
        args.expected_rows,
        args.expected_repositories,
    )

    shared_fields = [column for column in testing_fields if column not in VARIANT_COLUMNS]
    added_fields = [
        TESTING_COUNT_COLUMN,
        OTHER_COUNT_COLUMN,
        ALL_COUNT_COLUMN,
        CONTRAST_COLUMN,
        POSITIVE_COLUMN,
        NEGATIVE_COLUMN,
        CONTRAST_ZERO_COLUMN,
        "regular_function_contrast_id",
        "regular_function_contrast_label",
        "regular_function_contrast_definition",
        "regular_function_contrast_scale",
        "regular_function_contrast_unit",
        "regular_function_contrast_schema_version",
        "regular_function_contrast_covariance_handling",
    ]
    output_fields = [*shared_fields, *added_fields]

    output_rows: list[dict[str, Any]] = []
    testing_total = other_total = all_total = contrast_total = 0
    negative_rows = zero_rows = positive_rows = 0

    for row_number, (testing_row, other_row, all_row) in enumerate(
        zip(testing_rows, other_rows, all_rows, strict=True), start=2
    ):
        testing_key = tuple(testing_row[column] for column in KEY_COLUMNS)
        other_key = tuple(other_row[column] for column in KEY_COLUMNS)
        all_key = tuple(all_row[column] for column in KEY_COLUMNS)
        if not (testing_key == other_key == all_key):
            raise ValidationError(f"Panel key/order mismatch at CSV row {row_number}")

        for column in shared_fields:
            if not (
                testing_row[column] == other_row[column] == all_row[column]
            ):
                raise ValidationError(
                    f"Shared column {column!r} differs at CSV row {row_number}"
                )

        testing_count = parse_nonnegative_integer(
            testing_row[COUNT_COLUMN], f"testing row {row_number}"
        )
        other_count = parse_nonnegative_integer(
            other_row[COUNT_COLUMN], f"other row {row_number}"
        )
        all_count = parse_nonnegative_integer(
            all_row[COUNT_COLUMN], f"all row {row_number}"
        )
        contrast = derive_contrast(testing_count, other_count, all_count)

        output_row: dict[str, Any] = {
            column: testing_row[column] for column in shared_fields
        }
        output_row.update(
            {
                TESTING_COUNT_COLUMN: testing_count,
                OTHER_COUNT_COLUMN: other_count,
                ALL_COUNT_COLUMN: all_count,
                CONTRAST_COLUMN: contrast,
                POSITIVE_COLUMN: int(contrast > 0),
                NEGATIVE_COLUMN: int(contrast < 0),
                CONTRAST_ZERO_COLUMN: int(contrast == 0),
                "regular_function_contrast_id": CONTRAST_ID,
                "regular_function_contrast_label": CONTRAST_LABEL,
                "regular_function_contrast_definition": CONTRAST_DEFINITION,
                "regular_function_contrast_scale": "raw_count_difference",
                "regular_function_contrast_unit": (
                    "distinct_function_body_count_difference_per_repository_month"
                ),
                "regular_function_contrast_schema_version": SCRIPT_VERSION,
                "regular_function_contrast_covariance_handling": (
                    "components combined within repository-month before DiD estimation"
                ),
            }
        )
        output_rows.append(output_row)

        testing_total += testing_count
        other_total += other_count
        all_total += all_count
        contrast_total += contrast
        negative_rows += int(contrast < 0)
        zero_rows += int(contrast == 0)
        positive_rows += int(contrast > 0)

    observed = {
        "testing_total": testing_total,
        "other_total": other_total,
        "all_total": all_total,
        "contrast_total": contrast_total,
        "negative_rows": negative_rows,
        "zero_rows": zero_rows,
        "positive_rows": positive_rows,
    }
    expected = {
        "testing_total": args.expected_testing_total,
        "other_total": args.expected_other_total,
        "all_total": args.expected_all_total,
        "contrast_total": args.expected_contrast_total,
        "negative_rows": args.expected_negative_rows,
        "zero_rows": args.expected_zero_rows,
        "positive_rows": args.expected_positive_rows,
    }
    for name, expected_value in expected.items():
        if observed[name] != expected_value:
            raise ValidationError(
                f"{name}={observed[name]}; expected {expected_value}"
            )

    summary_rows: list[dict[str, Any]] = []
    for source in ("control", "treatment", "all"):
        selected = (
            output_rows
            if source == "all"
            else [row for row in output_rows if row["dataset_source"] == source]
        )
        values = [int(row[CONTRAST_COLUMN]) for row in selected]
        summary_rows.append(
            {
                "dataset_source": source,
                "rows": len(selected),
                "repositories": len({row["repo_name"] for row in selected}),
                "testing_total": sum(int(row[TESTING_COUNT_COLUMN]) for row in selected),
                "other_functions_total": sum(int(row[OTHER_COUNT_COLUMN]) for row in selected),
                "all_regular_functions_total": sum(int(row[ALL_COUNT_COLUMN]) for row in selected),
                "contrast_total": sum(values),
                "contrast_mean": sum(values) / len(values),
                "contrast_min": min(values),
                "contrast_max": max(values),
                "negative_rows": sum(value < 0 for value in values),
                "zero_rows": sum(value == 0 for value in values),
                "positive_rows": sum(value > 0 for value in values),
            }
        )

    qc_observations = {
        "input_rows": len(output_rows),
        "input_repositories": len({row["repo_name"] for row in output_rows}),
        "testing_total": testing_total,
        "other_functions_total": other_total,
        "all_regular_functions_total": all_total,
        "contrast_total": contrast_total,
        "negative_contrast_rows": negative_rows,
        "zero_contrast_rows": zero_rows,
        "positive_contrast_rows": positive_rows,
        "key_order_mismatches": 0,
        "shared_column_mismatches": 0,
        "testing_plus_other_equals_all_mismatches": 0,
        "contrast_arithmetic_mismatches": 0,
        "contrast_sign_partition_mismatches": 0,
        "covariate_missing_cells": 0,
        "att_or_uncertainty_computed": False,
    }
    qc_expected = {
        "input_rows": args.expected_rows,
        "input_repositories": args.expected_repositories,
        "testing_total": args.expected_testing_total,
        "other_functions_total": args.expected_other_total,
        "all_regular_functions_total": args.expected_all_total,
        "contrast_total": args.expected_contrast_total,
        "negative_contrast_rows": args.expected_negative_rows,
        "zero_contrast_rows": args.expected_zero_rows,
        "positive_contrast_rows": args.expected_positive_rows,
        "key_order_mismatches": 0,
        "shared_column_mismatches": 0,
        "testing_plus_other_equals_all_mismatches": 0,
        "contrast_arithmetic_mismatches": 0,
        "contrast_sign_partition_mismatches": 0,
        "covariate_missing_cells": 0,
        "att_or_uncertainty_computed": False,
    }
    covariates = [
        "log1p_age",
        "ncloc_python_snapshot",
        "log1p_contributors",
        "log1p_stars",
        "log1p_issues",
    ]
    missing_covariates = sum(
        not row[column].strip() for row in output_rows for column in covariates
    )
    qc_observations["covariate_missing_cells"] = missing_covariates
    if missing_covariates:
        raise ValidationError(f"Covariate missing cells={missing_covariates}")

    qc_rows = [
        {
            "check_name": name,
            "observed": observed_value,
            "expected": qc_expected[name],
            "passed": observed_value == qc_expected[name],
            "severity": "critical",
        }
        for name, observed_value in qc_observations.items()
    ]
    if not all(row["passed"] for row in qc_rows):
        raise ValidationError("One or more critical contrast-input QC checks failed")

    return output_fields, output_rows, summary_rows, qc_rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    args: argparse.Namespace,
    fields: list[str],
    rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    qc_rows: list[dict[str, Any]],
) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {name: args.output_dir / filename for name, filename in OUTPUT_FILES.items()}
    existing = [str(path) for path in output_paths.values() if path.exists()]
    if existing and not args.overwrite:
        raise ValidationError(
            "Output exists and --overwrite was not supplied: " + ", ".join(existing)
        )

    with tempfile.TemporaryDirectory(
        prefix="run-py-7f10-stage-", dir=args.output_dir
    ) as stage_name:
        stage = Path(stage_name)
        panel_path = stage / OUTPUT_FILES["panel"]
        summary_path = stage / OUTPUT_FILES["summary"]
        qc_path = stage / OUTPUT_FILES["qc"]
        metadata_path = stage / OUTPUT_FILES["metadata"]

        write_csv(panel_path, fields, rows)
        write_csv(summary_path, list(summary_rows[0]), summary_rows)
        write_csv(qc_path, list(qc_rows[0]), qc_rows)

        metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": "PASS",
            "purpose": "covariance-aware absolute-count contrast input",
            "contrast": "other_functions - testing",
            "outcome": CONTRAST_COLUMN,
            "outcome_scale": "raw_count_difference",
            "negative_values_allowed": True,
            "log_transform_applied": False,
            "zero_count_months_retained": True,
            "covariance_handling": (
                "component outcomes combined within repository-month before "
                "Borusyak DiD estimation"
            ),
            "null_hypothesis": "ATT_other_functions - ATT_testing = 0",
            "inputs": {
                "testing_panel": str(args.testing_panel),
                "other_panel": str(args.other_panel),
                "all_panel": str(args.all_panel),
            },
            "input_sha256": {
                "testing_panel": sha256_file(args.testing_panel),
                "other_panel": sha256_file(args.other_panel),
                "all_panel": sha256_file(args.all_panel),
            },
            "rows": len(rows),
            "repositories": len({row["repo_name"] for row in rows}),
            "contrast_total": sum(int(row[CONTRAST_COLUMN]) for row in rows),
            "negative_rows": sum(int(row[CONTRAST_COLUMN]) < 0 for row in rows),
            "zero_rows": sum(int(row[CONTRAST_COLUMN]) == 0 for row in rows),
            "positive_rows": sum(int(row[CONTRAST_COLUMN]) > 0 for row in rows),
            "att_or_uncertainty_computed": False,
            "critical_qc_checks": len(qc_rows),
            "critical_qc_failures": sum(not row["passed"] for row in qc_rows),
            "output_sha256": {
                OUTPUT_FILES["panel"]: sha256_file(panel_path),
                OUTPUT_FILES["summary"]: sha256_file(summary_path),
                OUTPUT_FILES["qc"]: sha256_file(qc_path),
            },
        }
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        for name, final_path in output_paths.items():
            os.replace(stage / OUTPUT_FILES[name], final_path)


def run_self_test() -> None:
    observed = [
        derive_contrast(testing, other, all_count)
        for testing, other, all_count in [(2, 4, 6), (5, 1, 6), (0, 0, 0)]
    ]
    if observed != [2, -4, 0]:
        raise AssertionError(f"Unexpected contrast values: {observed}")
    try:
        derive_contrast(1, 2, 4)
    except ValidationError:
        pass
    else:
        raise AssertionError("Reconciliation failure was not detected")
    print("Self-test: PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_expected_values(args)
        if args.self_test_only:
            run_self_test()
            return 0
        require_paths(args)
        fields, rows, summary_rows, qc_rows = build_outputs(args)
        write_outputs(args, fields, rows, summary_rows, qc_rows)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("run-py-7f10: PASS")
    print(f"Rows: {len(rows):,}")
    print(f"Repositories: {len({row['repo_name'] for row in rows}):,}")
    print(
        "Contrast sign rows (negative/zero/positive): "
        f"{sum(int(row[CONTRAST_COLUMN]) < 0 for row in rows):,}/"
        f"{sum(int(row[CONTRAST_COLUMN]) == 0 for row in rows):,}/"
        f"{sum(int(row[CONTRAST_COLUMN]) > 0 for row in rows):,}"
    )
    print(f"Contrast total: {sum(int(row[CONTRAST_COLUMN]) for row in rows):,}")
    print("ATT/uncertainty computed: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
