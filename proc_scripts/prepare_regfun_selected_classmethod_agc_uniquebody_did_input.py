#!/usr/bin/env python3
"""Prepare a fixed-sample hybrid AGC unique-body DiD input.

The hybrid outcome starts from the regular synchronous module-function outcome
used by run-py-7h. Class-method AGC unique-body counts are appended only for a
small, explicitly selected repository set identified by run-py-7m influence
analysis.

The positive-month sample is fixed by the original module-function outcome:
rows are retained only when the original module-function count is greater than
zero. Months that are zero for module functions but positive only because of a
selected repository's class methods are intentionally not added. This isolates
the effect of changing the outcome values from the effect of changing sample
membership.

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


SCRIPT_VERSION = "run-py-7n-v1"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
ORIGINAL_OUTCOME = "npr_agc_regular_module_function_unique_bodies"
ORIGINAL_LOG_OUTCOME = "log1p_npr_agc_regular_module_function_unique_bodies"
ORIGINAL_OCCURRENCE = "has_npr_agc_regular_module_function_unique_body"
ORIGINAL_ZERO = "zero_npr_agc_regular_module_function_unique_body_month"
ORIGINAL_READY_PAPER = (
    "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
)
ORIGINAL_READY_PYTHON = (
    "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc"
)

METHOD_COUNT_SOURCE = "method_agc_unique_bodies"
OVERLAP_COUNT_SOURCE = "module_method_agc_unique_body_overlap"
MODULE_COUNT_SOURCE = "module_function_agc_unique_bodies"

APPENDED_METHOD_COUNT = "selected_repo_method_agc_unique_bodies"
APPENDED_OVERLAP_COUNT = "selected_repo_module_method_agc_unique_body_overlap"
SELECTED_REPO_FLAG = "selected_classmethod_repository"
HYBRID_OUTCOME = "npr_agc_regfun_selected_classmethod_unique_bodies"
HYBRID_LOG_OUTCOME = "log1p_npr_agc_regfun_selected_classmethod_unique_bodies"
HYBRID_OCCURRENCE = "has_npr_agc_regfun_selected_classmethod_unique_body"
HYBRID_ZERO = "zero_npr_agc_regfun_selected_classmethod_unique_body_month"
HYBRID_READY_PAPER = (
    "analysis_ready_regfun_selected_classmethod_agc_uniquebody_paper_ncloc"
)
HYBRID_READY_PYTHON = (
    "analysis_ready_regfun_selected_classmethod_agc_uniquebody_"
    "python_snapshot_ncloc"
)

DEFAULT_SELECTED_REPOSITORIES = (
    "DataScienceUIBK/Rankify",
    "pieces-app/cli-agent",
    "HelpingAI/Webscout",
    "whiteducksoftware/flock",
    "getsentry/sentry",
)

EXPECTED_FIXED_SAMPLE_ADDITIONS = {
    "DataScienceUIBK/Rankify": 59,
    "pieces-app/cli-agent": 60,
    "HelpingAI/Webscout": 80,
    "whiteducksoftware/flock": 82,
    "getsentry/sentry": 544,
}

BASE_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "event",
    "time_to_event",
    "has_parse_exclusion",
    "npr_detection_complete",
    "npr_specification",
    "regular_function_scope",
    "agc_count_unit",
    "agc_outcome_scale",
    ORIGINAL_OUTCOME,
    ORIGINAL_LOG_OUTCOME,
    ORIGINAL_OCCURRENCE,
    ORIGINAL_ZERO,
    ORIGINAL_READY_PAPER,
    ORIGINAL_READY_PYTHON,
]

COUNT_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "npr_agc_regular_module_function_and_class_method_unique_bodies",
    MODULE_COUNT_SOURCE,
    METHOD_COUNT_SOURCE,
    OVERLAP_COUNT_SOURCE,
]


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a fixed original-positive-month panel that appends class "
            "methods only for selected repositories."
        )
    )
    parser.add_argument(
        "--base-panel",
        type=Path,
        default=Path(
            "repo_python/run-py-7e/strict/specifications/range100_200/"
            "panel_event_monthly_regular_module_function_agc_unique_body_"
            "parse_clean.csv"
        ),
        help=(
            "Parse-clean zero-inclusive regular module-function panel used by "
            "run-py-7h."
        ),
    )
    parser.add_argument(
        "--repo-month-counts",
        type=Path,
        default=Path(
            "repo_python/run-py-7j/strict/specifications/range100_200/"
            "regular_module_function_and_class_method_agc_unique_body_"
            "repo_month_counts.csv"
        ),
        help=(
            "run-py-7j repository-month counts containing separate module and "
            "method AGC unique-body counts."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7n/strict/specifications/range100_200"
        ),
    )
    parser.add_argument(
        "--selected-repo",
        action="append",
        default=None,
        help=(
            "Repository receiving class-method counts. Repeat for multiple "
            "repositories. Defaults to the five run-py-7m influence targets."
        ),
    )
    parser.add_argument("--specification-name", default="range100_200")
    parser.add_argument("--expected-base-rows", type=int, default=1536)
    parser.add_argument("--expected-original-positive-rows", type=int, default=487)
    parser.add_argument("--expected-original-positive-repositories", type=int, default=132)
    parser.add_argument("--expected-added-bodies", type=int, default=825)
    parser.add_argument(
        "--skip-frozen-count-checks",
        action="store_true",
        help=(
            "Skip fixed range100_200 count checks. Structural and arithmetic "
            "checks still run."
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


def build_synthetic_inputs(root: Path) -> tuple[Path, Path]:
    base_path = root / "base.csv"
    counts_path = root / "counts.csv"

    rows: list[dict[str, Any]] = []
    counts: list[dict[str, Any]] = []
    synthetic_repositories = [
        ("treatment", "DataScienceUIBK/Rankify"),
        ("control", "pieces-app/cli-agent"),
        ("control", "other/repository"),
    ]
    for dataset_source, repo_name in synthetic_repositories:
        for month_index, time in enumerate(("2025-01", "2025-02")):
            module_count = 1 if month_index == 0 else 0
            method_count = 2 if repo_name in DEFAULT_SELECTED_REPOSITORIES else 5
            row = {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "time": time,
                "event": "2025-02" if dataset_source == "treatment" else "",
                "time_to_event": -1 if month_index == 0 else 0,
                "has_parse_exclusion": 0,
                "npr_detection_complete": True,
                "npr_specification": "range100_200",
                "regular_function_scope": "module_function",
                "agc_count_unit": (
                    "distinct_function_body_sha256_per_repository_month"
                ),
                "agc_outcome_scale": "raw_count",
                ORIGINAL_OUTCOME: module_count,
                ORIGINAL_LOG_OUTCOME: float(np.log1p(module_count)),
                ORIGINAL_OCCURRENCE: int(module_count > 0),
                ORIGINAL_ZERO: int(module_count == 0),
                ORIGINAL_READY_PAPER: 1,
                ORIGINAL_READY_PYTHON: 1,
            }
            rows.append(row)
            counts.append(
                {
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "time": time,
                    "npr_agc_regular_module_function_and_class_method_unique_bodies": (
                        module_count + method_count
                    ),
                    MODULE_COUNT_SOURCE: module_count,
                    METHOD_COUNT_SOURCE: method_count,
                    OVERLAP_COUNT_SOURCE: 0,
                }
            )

    pd.DataFrame(rows).to_csv(base_path, index=False)
    pd.DataFrame(counts).to_csv(counts_path, index=False)
    return base_path, counts_path


def prepare_panel(args: argparse.Namespace) -> dict[str, Path]:
    selected_repositories = tuple(
        dict.fromkeys(args.selected_repo or DEFAULT_SELECTED_REPOSITORIES)
    )
    if not selected_repositories:
        raise ValidationError("At least one selected repository is required.")

    require_file(args.base_panel, "Base module-function panel")
    require_file(args.repo_month_counts, "run-py-7j repository-month counts")

    base = normalize_keys(pd.read_csv(args.base_panel, low_memory=False))
    counts = normalize_keys(pd.read_csv(args.repo_month_counts, low_memory=False))
    require_columns(base, BASE_REQUIRED_COLUMNS, "Base module-function panel")
    require_columns(counts, COUNT_REQUIRED_COLUMNS, "Repository-month counts")
    require_unique(base, KEY_COLUMNS, "Base module-function panel")
    require_unique(counts, KEY_COLUMNS, "Repository-month counts")

    if (base["has_parse_exclusion"].fillna(0).astype(int) != 0).any():
        raise ValidationError("Base panel is not parse-clean.")
    if not base["npr_specification"].astype(str).eq(args.specification_name).all():
        raise ValidationError("Base panel contains an unexpected specification.")
    if not base["regular_function_scope"].astype(str).eq("module_function").all():
        raise ValidationError("Base panel is not module-function-only.")
    if base[ORIGINAL_OUTCOME].isna().any() or (base[ORIGINAL_OUTCOME] < 0).any():
        raise ValidationError("Original module-function outcome is invalid.")

    count_columns = [
        *KEY_COLUMNS,
        MODULE_COUNT_SOURCE,
        METHOD_COUNT_SOURCE,
        OVERLAP_COUNT_SOURCE,
    ]
    merged = base.merge(
        counts[count_columns],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    for column in (
        MODULE_COUNT_SOURCE,
        METHOD_COUNT_SOURCE,
        OVERLAP_COUNT_SOURCE,
    ):
        merged[column] = merged[column].fillna(0)
        if (merged[column] < 0).any():
            raise ValidationError(f"Negative repository-month count in {column}.")
        if not np.allclose(merged[column], np.round(merged[column])):
            raise ValidationError(f"Noninteger repository-month count in {column}.")
        merged[column] = merged[column].astype("int64")

    module_mismatch = merged[ORIGINAL_OUTCOME].astype(int).ne(
        merged[MODULE_COUNT_SOURCE]
    )
    if module_mismatch.any():
        sample = merged.loc[
            module_mismatch,
            [*KEY_COLUMNS, ORIGINAL_OUTCOME, MODULE_COUNT_SOURCE],
        ].head(20)
        raise ValidationError(
            "run-py-7e module outcome does not match run-py-7j module count:\n"
            f"{sample.to_string(index=False)}"
        )

    found_selected = set(merged.loc[
        merged["repo_name"].isin(selected_repositories), "repo_name"
    ])
    missing_selected = sorted(set(selected_repositories) - found_selected)
    if missing_selected:
        raise ValidationError(
            f"Selected repositories are absent from the base panel: {missing_selected}"
        )

    merged[SELECTED_REPO_FLAG] = merged["repo_name"].isin(selected_repositories)
    merged[APPENDED_METHOD_COUNT] = np.where(
        merged[SELECTED_REPO_FLAG],
        merged[METHOD_COUNT_SOURCE],
        0,
    ).astype("int64")
    merged[APPENDED_OVERLAP_COUNT] = np.where(
        merged[SELECTED_REPO_FLAG],
        merged[OVERLAP_COUNT_SOURCE],
        0,
    ).astype("int64")

    merged[HYBRID_OUTCOME] = (
        merged[ORIGINAL_OUTCOME].astype("int64")
        + merged[APPENDED_METHOD_COUNT]
        - merged[APPENDED_OVERLAP_COUNT]
    )
    if (merged[HYBRID_OUTCOME] < merged[ORIGINAL_OUTCOME]).any():
        raise ValidationError("Hybrid outcome is smaller than the original outcome.")

    merged[HYBRID_LOG_OUTCOME] = np.log1p(merged[HYBRID_OUTCOME])
    merged[HYBRID_OCCURRENCE] = (merged[HYBRID_OUTCOME] > 0).astype("int8")
    merged[HYBRID_ZERO] = (merged[HYBRID_OUTCOME] == 0).astype("int8")
    merged[HYBRID_READY_PAPER] = merged[ORIGINAL_READY_PAPER].astype("int8")
    merged[HYBRID_READY_PYTHON] = merged[ORIGINAL_READY_PYTHON].astype("int8")
    merged["hybrid_function_scope"] = (
        "module_function_all_repositories+method_selected_repositories"
    )
    merged["selected_classmethod_repository_count"] = len(selected_repositories)
    merged["agc_count_unit_hybrid"] = (
        "distinct_function_body_sha256_per_repository_month_with_selected_"
        "class_methods"
    )
    merged["agc_outcome_scale_hybrid"] = "raw_count"

    drop_columns = ["_merge"]
    zero_inclusive = merged.drop(columns=drop_columns).copy()

    original_positive = zero_inclusive.loc[
        zero_inclusive[ORIGINAL_OUTCOME].astype(int) > 0
    ].copy()
    original_positive["sample_restriction"] = (
        "original_module_function_outcome > 0"
    )
    original_positive["sample_membership_fixed_to_run_py_7h"] = True
    original_positive["causal_interpretation_allowed"] = False
    original_positive["selection_note"] = (
        "Sample membership is fixed by the original module-function positive-"
        "outcome rule. Class methods are appended only to selected repositories; "
        "method-only positive months are not added. This is supplementary "
        "influence debugging, not a primary causal estimand."
    )

    selected_audit_columns = [
        "dataset_source",
        "repo_name",
        "time",
        "event",
        "time_to_event",
        ORIGINAL_OUTCOME,
        METHOD_COUNT_SOURCE,
        OVERLAP_COUNT_SOURCE,
        APPENDED_METHOD_COUNT,
        APPENDED_OVERLAP_COUNT,
        HYBRID_OUTCOME,
        ORIGINAL_READY_PYTHON,
        "has_parse_exclusion",
    ]
    selected_audit = zero_inclusive.loc[
        zero_inclusive[SELECTED_REPO_FLAG], selected_audit_columns
    ].copy()
    selected_audit["retained_original_positive_sample"] = (
        selected_audit[ORIGINAL_OUTCOME] > 0
    )
    selected_audit["method_only_positive_month_not_added"] = (
        (selected_audit[ORIGINAL_OUTCOME] == 0)
        & (selected_audit[HYBRID_OUTCOME] > 0)
    )
    selected_audit = selected_audit.sort_values(KEY_COLUMNS).reset_index(drop=True)

    selected_summary = (
        original_positive.loc[original_positive[SELECTED_REPO_FLAG]]
        .groupby(["dataset_source", "repo_name"], as_index=False)
        .agg(
            fixed_sample_rows=("time", "size"),
            original_module_unique_bodies=(ORIGINAL_OUTCOME, "sum"),
            appended_method_unique_bodies=(APPENDED_METHOD_COUNT, "sum"),
            subtracted_cross_kind_overlap=(APPENDED_OVERLAP_COUNT, "sum"),
            hybrid_unique_bodies=(HYBRID_OUTCOME, "sum"),
        )
    )
    selected_summary["net_added_unique_bodies"] = (
        selected_summary["hybrid_unique_bodies"]
        - selected_summary["original_module_unique_bodies"]
    )

    newly_positive_not_added = int(
        (
            (zero_inclusive[ORIGINAL_OUTCOME] == 0)
            & (zero_inclusive[HYBRID_OUTCOME] > 0)
        ).sum()
    )
    fixed_added_bodies = int(
        original_positive[HYBRID_OUTCOME].sum()
        - original_positive[ORIGINAL_OUTCOME].sum()
    )

    sample_summary = pd.DataFrame(
        [
            {"metric": "base_parse_clean_rows", "value": len(zero_inclusive)},
            {
                "metric": "original_positive_sample_rows",
                "value": len(original_positive),
            },
            {
                "metric": "original_positive_sample_repositories",
                "value": original_positive["repo_name"].nunique(),
            },
            {
                "metric": "selected_repositories",
                "value": len(selected_repositories),
            },
            {
                "metric": "original_positive_outcome_total",
                "value": int(original_positive[ORIGINAL_OUTCOME].sum()),
            },
            {
                "metric": "hybrid_outcome_total_fixed_sample",
                "value": int(original_positive[HYBRID_OUTCOME].sum()),
            },
            {
                "metric": "net_added_bodies_fixed_sample",
                "value": fixed_added_bodies,
            },
            {
                "metric": "method_only_positive_months_not_added",
                "value": newly_positive_not_added,
            },
        ]
    )

    checks: list[dict[str, Any]] = []
    add_check(
        checks,
        "base_keys_unique",
        not zero_inclusive.duplicated(KEY_COLUMNS).any(),
        int(zero_inclusive.duplicated(KEY_COLUMNS).sum()),
        0,
        "Repository-month keys must be unique.",
    )
    add_check(
        checks,
        "base_panel_is_parse_clean",
        not (zero_inclusive["has_parse_exclusion"].astype(int) != 0).any(),
        int((zero_inclusive["has_parse_exclusion"].astype(int) != 0).sum()),
        0,
        "run-py-7n starts from the run-py-7e parse-clean panel.",
    )
    add_check(
        checks,
        "module_counts_match_run7j",
        not module_mismatch.any(),
        int(module_mismatch.sum()),
        0,
        "run-py-7e and run-py-7j module-function counts must agree.",
    )
    add_check(
        checks,
        "nonselected_repositories_unchanged",
        bool(
            zero_inclusive.loc[
                ~zero_inclusive[SELECTED_REPO_FLAG], HYBRID_OUTCOME
            ].equals(
                zero_inclusive.loc[
                    ~zero_inclusive[SELECTED_REPO_FLAG], ORIGINAL_OUTCOME
                ].astype("int64")
            )
        ),
        int(
            zero_inclusive.loc[
                ~zero_inclusive[SELECTED_REPO_FLAG], HYBRID_OUTCOME
            ].ne(
                zero_inclusive.loc[
                    ~zero_inclusive[SELECTED_REPO_FLAG], ORIGINAL_OUTCOME
                ].astype("int64")
            ).sum()
        ),
        0,
        "Class methods must not alter nonselected repositories.",
    )
    add_check(
        checks,
        "fixed_sample_membership_matches_original_positive_rule",
        bool((original_positive[ORIGINAL_OUTCOME] > 0).all()),
        int((original_positive[ORIGINAL_OUTCOME] <= 0).sum()),
        0,
        "Rows are selected only by the original module-function outcome.",
    )
    add_check(
        checks,
        "fixed_sample_hybrid_outcome_positive",
        bool((original_positive[HYBRID_OUTCOME] > 0).all()),
        int((original_positive[HYBRID_OUTCOME] <= 0).sum()),
        0,
        "Appending methods cannot make a retained positive row nonpositive.",
    )
    add_check(
        checks,
        "method_only_positive_months_excluded",
        bool(
            not original_positive[KEY_COLUMNS].merge(
                zero_inclusive.loc[
                    (zero_inclusive[ORIGINAL_OUTCOME] == 0)
                    & (zero_inclusive[HYBRID_OUTCOME] > 0),
                    KEY_COLUMNS,
                ],
                on=KEY_COLUMNS,
                how="inner",
            ).shape[0]
        ),
        0,
        0,
        "Newly positive method-only months must not enter the fixed sample.",
    )
    add_check(
        checks,
        "all_selected_repositories_present",
        not missing_selected,
        len(found_selected),
        len(selected_repositories),
        "Every requested influence repository must exist in the panel.",
    )

    if not args.skip_frozen_count_checks:
        frozen_checks = [
            (
                "base_rows_match_frozen",
                len(zero_inclusive),
                args.expected_base_rows,
            ),
            (
                "original_positive_rows_match_frozen",
                len(original_positive),
                args.expected_original_positive_rows,
            ),
            (
                "original_positive_repositories_match_frozen",
                original_positive["repo_name"].nunique(),
                args.expected_original_positive_repositories,
            ),
            (
                "fixed_sample_added_bodies_match_frozen",
                fixed_added_bodies,
                args.expected_added_bodies,
            ),
        ]
        for name, observed, expected in frozen_checks:
            add_check(
                checks,
                name,
                int(observed) == int(expected),
                int(observed),
                int(expected),
                "Frozen range100_200 diagnostic count.",
            )

        observed_additions = dict(
            zip(
                selected_summary["repo_name"],
                selected_summary["net_added_unique_bodies"].astype(int),
            )
        )
        for repo_name, expected in EXPECTED_FIXED_SAMPLE_ADDITIONS.items():
            observed = int(observed_additions.get(repo_name, -1))
            add_check(
                checks,
                f"fixed_sample_added_bodies_{repo_name}",
                observed == expected,
                observed,
                expected,
                "Frozen selected-repository method contribution.",
            )

    checks_frame = pd.DataFrame(checks)
    failed = checks_frame.loc[~checks_frame["passed"]]
    if not failed.empty:
        raise ValidationError(
            "run-py-7n validation failed:\n"
            f"{failed.to_string(index=False)}"
        )

    prepare_output_directory(args.output_dir, args.overwrite_output)
    qc_dir = args.output_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    output_paths = {
        "zero_inclusive": args.output_dir
        / "panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_"
        "parse_clean.csv",
        "fixed_positive": args.output_dir
        / "panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_"
        "original_positive_sample_parse_clean.csv",
        "selected_repositories": args.output_dir
        / "regfun_selected_classmethod_agc_uniquebody_selected_"
        "repositories.csv",
        "selected_audit": args.output_dir
        / "regfun_selected_classmethod_agc_uniquebody_selected_repo_month_"
        "audit.csv",
        "selected_summary": args.output_dir
        / "regfun_selected_classmethod_agc_uniquebody_selected_repo_"
        "summary.csv",
        "sample_summary": args.output_dir
        / "regfun_selected_classmethod_agc_uniquebody_sample_summary.csv",
        "checks": qc_dir
        / "regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv",
        "summary_json": qc_dir
        / "regfun_selected_classmethod_agc_uniquebody_did_input_summary.json",
        "status": args.output_dir
        / "regfun_selected_classmethod_agc_uniquebody_status.txt",
    }

    selected_repository_frame = pd.DataFrame(
        {
            "repo_name": list(selected_repositories),
            "selection_source": "run-py-7m_top_lower_bound_increase",
            "append_class_methods": True,
        }
    )

    atomic_write_csv(zero_inclusive, output_paths["zero_inclusive"])
    atomic_write_csv(original_positive, output_paths["fixed_positive"])
    atomic_write_csv(selected_repository_frame, output_paths["selected_repositories"])
    atomic_write_csv(selected_audit, output_paths["selected_audit"])
    atomic_write_csv(selected_summary, output_paths["selected_summary"])
    atomic_write_csv(sample_summary, output_paths["sample_summary"])
    atomic_write_csv(checks_frame, output_paths["checks"])

    summary_payload = {
        "script_version": SCRIPT_VERSION,
        "specification_name": args.specification_name,
        "base_panel": str(args.base_panel),
        "base_panel_sha256": sha256_file(args.base_panel),
        "repo_month_counts": str(args.repo_month_counts),
        "repo_month_counts_sha256": sha256_file(args.repo_month_counts),
        "selected_repositories": list(selected_repositories),
        "sample_membership_rule": "original_module_function_outcome > 0",
        "method_only_positive_months_added": False,
        "causal_interpretation_allowed": False,
        "base_rows": int(len(zero_inclusive)),
        "fixed_positive_rows": int(len(original_positive)),
        "fixed_positive_repositories": int(original_positive["repo_name"].nunique()),
        "original_outcome_total": int(original_positive[ORIGINAL_OUTCOME].sum()),
        "hybrid_outcome_total": int(original_positive[HYBRID_OUTCOME].sum()),
        "net_added_bodies": fixed_added_bodies,
        "method_only_positive_months_not_added": newly_positive_not_added,
        "failed_checks": int((~checks_frame["passed"]).sum()),
        "outputs": {name: str(path) for name, path in output_paths.items()},
    }
    atomic_write_json(summary_payload, output_paths["summary_json"])

    status_text = "\n".join(
        [
            "status=PASS",
            f"script_version={SCRIPT_VERSION}",
            "sample_membership_fixed_to_run_py_7h=TRUE",
            "sample_restriction=original_module_function_outcome > 0",
            "method_only_positive_months_added=FALSE",
            "causal_interpretation_allowed=FALSE",
            f"selected_repositories={len(selected_repositories)}",
            f"fixed_positive_rows={len(original_positive)}",
            f"fixed_positive_repositories={original_positive['repo_name'].nunique()}",
            f"net_added_bodies={fixed_added_bodies}",
            f"failed_checks={int((~checks_frame['passed']).sum())}",
        ]
    ) + "\n"
    output_paths["status"].write_text(status_text, encoding="utf-8")

    print("=" * 80)
    print("run-py-7n: fixed-sample selected class-method panel")
    print("=" * 80)
    print("Status:                                  PASS")
    print(f"Base parse-clean rows:                   {len(zero_inclusive)}")
    print(f"Original positive-sample rows:           {len(original_positive)}")
    print(
        "Original positive-sample repositories:   "
        f"{original_positive['repo_name'].nunique()}"
    )
    print(f"Selected repositories:                   {len(selected_repositories)}")
    print(
        "Original outcome total, fixed sample:     "
        f"{int(original_positive[ORIGINAL_OUTCOME].sum())}"
    )
    print(
        "Hybrid outcome total, fixed sample:       "
        f"{int(original_positive[HYBRID_OUTCOME].sum())}"
    )
    print(f"Net appended bodies, fixed sample:       {fixed_added_bodies}")
    print(
        "Method-only positive months not added:    "
        f"{newly_positive_not_added}"
    )
    print(f"Failed checks:                           {int((~checks_frame['passed']).sum())}")
    print(f"Output directory:                        {args.output_dir}")
    print(f"Next-stage input:                        {output_paths['fixed_positive']}")
    print("=" * 80)

    return output_paths


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-7n-self-test-") as temporary:
        root = Path(temporary)
        base_path, counts_path = build_synthetic_inputs(root)
        output_dir = root / "output"
        args = argparse.Namespace(
            base_panel=base_path,
            repo_month_counts=counts_path,
            output_dir=output_dir,
            selected_repo=[
                "DataScienceUIBK/Rankify",
                "pieces-app/cli-agent",
            ],
            specification_name="range100_200",
            expected_base_rows=6,
            expected_original_positive_rows=3,
            expected_original_positive_repositories=3,
            expected_added_bodies=4,
            skip_frozen_count_checks=True,
            overwrite_output=True,
            self_test=False,
        )
        paths = prepare_panel(args)
        fixed = pd.read_csv(paths["fixed_positive"])
        if len(fixed) != 3:
            raise ValidationError("Self-test fixed sample row count failed.")
        if fixed[HYBRID_OUTCOME].sum() != 7:
            raise ValidationError("Self-test hybrid outcome sum failed.")
        if fixed.loc[
            fixed["repo_name"].eq("other/repository"), HYBRID_OUTCOME
        ].iloc[0] != 1:
            raise ValidationError("Self-test changed a nonselected repository.")
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        prepare_panel(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
