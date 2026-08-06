#!/usr/bin/env python3
"""Prepare same-sample Python added-lines DiD panels.

The script joins three measurement sources to the final run-x-a05 Model A panel:
1. Newly collected monthly Python physical added lines.
2. Newly computed cloc Python-only NCLOC.
3. Existing SonarQube Python-only NCLOC from a completed CSV.

The SonarQube and cloc backend panels use the exact same common sample and the
same four Python velocity outcomes. Only the generic ``ncloc`` value and its
backend provenance are allowed to differ. The primary outcome is
``log_lines_added_py_source``; broad, no-merge, and no-test definitions are
retained for robustness analysis.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v4"
BASE_REQUIRED_COLUMNS = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "latest_commit_effective",
    "ncloc",
    "lines_added",
    "log_lines_added",
    "log_age",
    "log_contributors",
    "log_stars",
    "log_issues",
}
MANIFEST_REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "latest_commit_effective",
    "repo_month_rows",
    "first_panel_month",
    "last_panel_month",
}
ADDED_REQUIRED_COLUMNS = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "lines_added_repo_original",
    "lines_added_repo_recomputed",
    "lines_added_py_total",
    "lines_added_py",
    "log_lines_added_py",
    "lines_added_py_all",
    "log_lines_added_py_all",
    "lines_added_py_no_merge",
    "log_lines_added_py_no_merge",
    "lines_added_py_source",
    "log_lines_added_py_source",
    "lines_added_py_source_no_tests",
    "log_lines_added_py_source_no_tests",
    "python_added_lines_complete",
    "reference_reconciliation_complete",
    "reference_reconciliation_status",
    "history_reconciliation_complete",
    "python_added_lines_available",
    "python_added_lines_status",
}
CLOC_REQUIRED_COLUMNS = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "ncloc_py_cloc",
    "cloc_status",
    "cloc_version",
}
SONAR_REQUIRED_COLUMNS = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "ncloc_py_sonarqube",
    "status",
}
OUTCOME_NAMES = [
    "lines_added_py_all",
    "lines_added_py_no_merge",
    "lines_added_py_source",
    "lines_added_py_source_no_tests",
]
LOG_OUTCOME_NAMES = [f"log_{name}" for name in OUTCOME_NAMES]
MODEL_REQUIRED_FIELDS = [
    *LOG_OUTCOME_NAMES,
    "log_age",
    "log_contributors",
    "log_stars",
    "log_issues",
]
PRESERVATION_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "lines_added_py",
    "log_lines_added_py",
    *OUTCOME_NAMES,
    *LOG_OUTCOME_NAMES,
    "lines_added_repo_original",
    "log_lines_added_repo_original",
    "log_age",
    "log_contributors",
    "log_stars",
    "log_issues",
]



def clean_text(value: Any) -> str:
    """Normalize missing text values."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def boolean_series(series: pd.Series) -> pd.Series:
    """Convert mixed boolean-like values without silent object downcasting."""
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.astype("boolean").fillna(False).astype(bool)
    normalized = series.astype("string").str.strip().str.casefold()
    return normalized.isin({"1", "true", "t", "yes", "y"})


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Fail when required input columns are missing."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(temporary, index=False)
    temporary.replace(target)


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    """Read a CSV while preserving identity columns as strings."""
    target = path.expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Required input file not found: {target}")
    header = pd.read_csv(target, nrows=0)
    dtype = {column: "string" for column in string_columns if column in header.columns}
    return pd.read_csv(target, dtype=dtype, low_memory=False)


def snapshot_identity(dataset_source: pd.Series, repo_name: pd.Series, commit_sha: pd.Series) -> pd.Series:
    """Build a normalized repository-snapshot identity."""
    return (
        dataset_source.map(clean_text).str.casefold()
        + "|"
        + repo_name.map(clean_text).str.casefold()
        + "|"
        + commit_sha.map(clean_text).str.casefold()
    )


def normalize_base(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the final Model A panel."""
    require_columns(raw, BASE_REQUIRED_COLUMNS, "base Model A panel")
    panel = raw.copy()
    panel["dataset_source"] = panel["dataset_source"].map(clean_text).str.casefold()
    panel["repo_name"] = panel["repo_name"].map(clean_text)
    panel["time"] = panel["time"].map(clean_text)
    panel["latest_commit_effective"] = panel["latest_commit_effective"].map(clean_text).str.casefold()
    for column in ["repo_id", "time_index"]:
        panel[column] = pd.to_numeric(panel[column], errors="raise").astype(int)
    for column in [
        "ncloc",
        "lines_added",
        "log_lines_added",
        "log_age",
        "log_contributors",
        "log_stars",
        "log_issues",
    ]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    if panel.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("Base panel contains duplicate repo_id-time_index rows")
    if panel["ncloc"].isna().any() or (panel["ncloc"] < 0).any():
        raise ValueError("Base panel contains missing or negative Model A NCLOC")
    panel["_snapshot_identity"] = snapshot_identity(
        panel["dataset_source"], panel["repo_name"], panel["latest_commit_effective"]
    )
    panel["ncloc_model_a"] = panel["ncloc"]
    panel["ncloc_source_model_a"] = panel.get("ncloc_source", "").map(clean_text) if "ncloc_source" in panel.columns else ""
    panel["lines_added_repo_original"] = panel["lines_added"]
    panel["log_lines_added_repo_original"] = panel["log_lines_added"]
    return panel.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def normalize_manifest(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the unique snapshot manifest."""
    require_columns(raw, MANIFEST_REQUIRED_COLUMNS, "snapshot manifest")
    manifest = raw.copy()
    manifest["dataset_source"] = manifest["dataset_source"].map(clean_text).str.casefold()
    manifest["repo_name"] = manifest["repo_name"].map(clean_text)
    manifest["commit_sha"] = manifest["latest_commit_effective"].map(clean_text).str.casefold()
    manifest["repo_key"] = manifest.get("repo_key", manifest["repo_name"]).map(clean_text).str.casefold()
    manifest["repo_month_rows"] = pd.to_numeric(manifest["repo_month_rows"], errors="raise").astype(int)
    manifest["_snapshot_identity"] = snapshot_identity(
        manifest["dataset_source"], manifest["repo_name"], manifest["commit_sha"]
    )
    if manifest["_snapshot_identity"].duplicated().any():
        raise ValueError("Snapshot manifest contains duplicate identities")
    return manifest


def normalize_added(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize newly collected monthly Python added lines."""
    require_columns(raw, ADDED_REQUIRED_COLUMNS, "Python added-lines repo-month results")
    added = raw.copy()
    added["dataset_source"] = added["dataset_source"].map(clean_text).str.casefold()
    added["repo_name"] = added["repo_name"].map(clean_text)
    added["time"] = added["time"].map(clean_text)
    for column in ["repo_id", "time_index"]:
        added[column] = pd.to_numeric(added[column], errors="raise").astype(int)
    numeric = [
        "lines_added_repo_original",
        "lines_added_repo_recomputed",
        "lines_added_py_total",
        "lines_added_py",
        "log_lines_added_py",
        *OUTCOME_NAMES,
        *LOG_OUTCOME_NAMES,
        "python_added_lines_complete",
        "reference_reconciliation_complete",
        "history_reconciliation_complete",
        "python_added_lines_available",
    ]
    for column in numeric:
        added[column] = pd.to_numeric(added[column], errors="coerce")
    if added.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("Python added-lines results contain duplicate repo-month keys")
    for outcome in OUTCOME_NAMES:
        if (added[outcome] < 0).any():
            raise ValueError(f"Python added-lines results contain negative values in {outcome}")
        expected_log = np.log1p(added[outcome])
        if (~np.isclose(expected_log, added[f"log_{outcome}"], rtol=0, atol=1e-12)).any():
            raise ValueError(f"Python added-lines log transformation is inconsistent for {outcome}")
    if (
        added["lines_added_py"].ne(added["lines_added_py_all"]).any()
        or added["lines_added_py_total"].ne(added["lines_added_py_all"]).any()
        or (~np.isclose(added["log_lines_added_py"], added["log_lines_added_py_all"], rtol=0, atol=1e-12)).any()
    ):
        raise ValueError("Legacy Python added-lines aliases do not match lines_added_py_all")
    if (
        (added["lines_added_py_source_no_tests"] > added["lines_added_py_source"]).any()
        or (added["lines_added_py_source"] > added["lines_added_py_no_merge"]).any()
        or (added["lines_added_py_no_merge"] > added["lines_added_py_all"]).any()
    ):
        raise ValueError("Python added-lines outcome nesting is inconsistent")
    expected_available = added["python_added_lines_complete"].fillna(0).eq(1)
    observed_available = added["python_added_lines_available"].fillna(0).eq(1)
    if observed_available.ne(expected_available).any():
        raise ValueError(
            "v4 availability contract violated: python_added_lines_available must "
            "equal python_added_lines_complete and must not depend on Model A reconciliation"
        )
    return added


def normalize_cloc(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize newly computed cloc snapshot results."""
    require_columns(raw, CLOC_REQUIRED_COLUMNS, "cloc snapshot results")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["commit_sha"] = data["commit_sha"].map(clean_text).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean_text)
    data["ncloc_py_cloc"] = pd.to_numeric(data["ncloc_py_cloc"], errors="coerce")
    data["cloc_status"] = data["cloc_status"].map(clean_text).str.casefold()
    data["cloc_available"] = data["cloc_status"].eq("success") & data["ncloc_py_cloc"].notna()
    data["_snapshot_identity"] = snapshot_identity(
        data["dataset_source"], data["repo_name"], data["commit_sha"]
    )
    if data["_snapshot_identity"].duplicated().any():
        raise ValueError("cloc results contain duplicate snapshot identities")
    return data


def normalize_sonar(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the existing SonarQube snapshot CSV."""
    require_columns(raw, SONAR_REQUIRED_COLUMNS, "SonarQube snapshot results")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["commit_sha"] = data["commit_sha"].map(clean_text).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean_text)
    data["ncloc_py_sonarqube"] = pd.to_numeric(data["ncloc_py_sonarqube"], errors="coerce")
    data["status"] = data["status"].map(clean_text).str.casefold()
    data["sonarqube_available"] = data["status"].eq("success") & data["ncloc_py_sonarqube"].notna()
    data["_snapshot_identity"] = snapshot_identity(
        data["dataset_source"], data["repo_name"], data["commit_sha"]
    )
    if data["_snapshot_identity"].duplicated().any():
        raise ValueError("SonarQube results contain duplicate snapshot identities")
    return data


def build_snapshot_comparison(
    manifest: pd.DataFrame,
    cloc: pd.DataFrame,
    sonar: pd.DataFrame,
) -> pd.DataFrame:
    """Build one NCLOC comparison row per unique historical snapshot."""
    base_columns = [
        "_snapshot_identity",
        "dataset_source",
        "repo_name",
        "repo_key",
        "commit_sha",
        "repo_month_rows",
        "first_panel_month",
        "last_panel_month",
    ]
    output = manifest[base_columns].copy()
    cloc_columns = [
        "_snapshot_identity",
        "snapshot_key",
        "ncloc_py_cloc",
        "cloc_status",
        "cloc_available",
        "cloc_version",
    ]
    for optional in [
        "python_file_count_manifest",
        "python_file_count_git",
        "python_file_count_matches_manifest",
        "manifest_minus_git_file_count",
        "python_file_count_cloc",
        "python_file_count_cloc_matches_git",
        "git_minus_cloc_file_count",
        "git_paths_missing_from_cloc_count",
        "git_paths_missing_from_cloc_samples",
        "cloc_paths_not_in_git_count",
        "cloc_paths_not_in_git_samples",
        "cloc_runtime_seconds",
    ]:
        if optional in cloc.columns:
            cloc_columns.append(optional)
    cloc_selected = cloc[cloc_columns].rename(columns={"snapshot_key": "snapshot_key_cloc"})
    sonar_columns = [
        "_snapshot_identity",
        "snapshot_key",
        "ncloc_py_sonarqube",
        "status",
        "sonarqube_available",
    ]
    for optional in ["project_key", "project_version", "scanner_log_path", "runtime_seconds"]:
        if optional in sonar.columns:
            sonar_columns.append(optional)
    sonar_selected = sonar[sonar_columns].rename(
        columns={
            "snapshot_key": "snapshot_key_sonarqube",
            "status": "sonarqube_status",
            "runtime_seconds": "sonarqube_runtime_seconds",
        }
    )
    output = output.merge(cloc_selected, on="_snapshot_identity", how="left", validate="one_to_one")
    output = output.merge(sonar_selected, on="_snapshot_identity", how="left", validate="one_to_one")
    output["cloc_available"] = boolean_series(output["cloc_available"])
    output["sonarqube_available"] = boolean_series(output["sonarqube_available"])
    output["both_ncloc_available"] = output["cloc_available"] & output["sonarqube_available"]
    output["snapshot_key_matches_backends"] = output["snapshot_key_cloc"].eq(output["snapshot_key_sonarqube"])
    output["sonarqube_minus_cloc"] = output["ncloc_py_sonarqube"] - output["ncloc_py_cloc"]
    output["exact_match_sonarqube_cloc"] = output["sonarqube_minus_cloc"].eq(0)
    return output.sort_values(["dataset_source", "repo_name", "commit_sha"], kind="stable").reset_index(drop=True)


def build_combined_panel(
    panel: pd.DataFrame,
    added: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    """Join monthly outcome and snapshot NCLOC measurements to all base rows."""
    added_columns = [column for column in added.columns if column not in {"repo_name", "dataset_source", "time"}]
    added_merge = added[["repo_id", "time_index", "repo_name", "dataset_source", "time", *[
        column for column in added_columns if column not in {"repo_id", "time_index"}
    ]]].copy()
    added_merge["_python_added_lines_row_present"] = True
    added_merge = added_merge.rename(
        columns={
            "repo_name": "added_repo_name",
            "dataset_source": "added_dataset_source",
            "time": "added_time",
            "lines_added_repo_original": "lines_added_repo_original_collector",
            "log_lines_added_repo_original": "log_lines_added_repo_original_collector",
            "latest_commit_effective": "latest_commit_effective_collector",
        }
    )
    combined = panel.merge(
        added_merge,
        on=["repo_id", "time_index"],
        how="left",
        validate="one_to_one",
    )
    joined = boolean_series(combined["_python_added_lines_row_present"])
    combined["python_added_lines_joined"] = joined
    identity_difference = (
        combined["repo_name"].map(clean_text).ne(combined["added_repo_name"].map(clean_text))
        | combined["dataset_source"].map(clean_text).str.casefold().ne(
            combined["added_dataset_source"].map(clean_text).str.casefold()
        )
        | combined["time"].map(clean_text).ne(combined["added_time"].map(clean_text))
    )
    combined["python_added_lines_identity_mismatch"] = joined & identity_difference
    original_difference = ~np.isclose(
        pd.to_numeric(combined["lines_added_repo_original"], errors="coerce"),
        pd.to_numeric(combined["lines_added_repo_original_collector"], errors="coerce"),
        rtol=0,
        atol=0,
        equal_nan=True,
    )
    combined["python_added_lines_original_value_mismatch"] = joined & original_difference
    outcome_log_mismatch_columns: list[str] = []
    for outcome in OUTCOME_NAMES:
        mismatch_column = f"{outcome}_log_transform_mismatch"
        expected_log = np.log1p(pd.to_numeric(combined[outcome], errors="coerce"))
        observed_log = pd.to_numeric(combined[f"log_{outcome}"], errors="coerce")
        log_equal = np.isclose(expected_log, observed_log, rtol=0, atol=1e-12, equal_nan=True)
        combined[mismatch_column] = joined & ~log_equal
        outcome_log_mismatch_columns.append(mismatch_column)
    combined["python_added_lines_log_transform_mismatch"] = combined[
        outcome_log_mismatch_columns
    ].any(axis=1)

    snapshot_columns = [
        "_snapshot_identity",
        "snapshot_key_cloc",
        "snapshot_key_sonarqube",
        "ncloc_py_cloc",
        "cloc_status",
        "cloc_available",
        "cloc_version",
        "ncloc_py_sonarqube",
        "sonarqube_status",
        "sonarqube_available",
        "both_ncloc_available",
        "sonarqube_minus_cloc",
        "exact_match_sonarqube_cloc",
    ]
    for optional in [
        "project_key",
        "project_version",
        "scanner_log_path",
        "sonarqube_runtime_seconds",
        "python_file_count_manifest",
        "python_file_count_git",
        "python_file_count_matches_manifest",
        "manifest_minus_git_file_count",
        "python_file_count_cloc",
        "python_file_count_cloc_matches_git",
        "git_minus_cloc_file_count",
        "git_paths_missing_from_cloc_count",
        "git_paths_missing_from_cloc_samples",
        "cloc_paths_not_in_git_count",
        "cloc_paths_not_in_git_samples",
        "cloc_runtime_seconds",
    ]:
        if optional in snapshots.columns:
            snapshot_columns.append(optional)
    combined = combined.merge(
        snapshots[snapshot_columns],
        on="_snapshot_identity",
        how="left",
        validate="many_to_one",
    )
    combined["cloc_available"] = boolean_series(combined["cloc_available"])
    combined["sonarqube_available"] = boolean_series(combined["sonarqube_available"])
    combined["python_added_lines_available"] = (
        pd.to_numeric(combined["python_added_lines_available"], errors="coerce").fillna(0).eq(1)
    )
    model_complete = pd.Series(True, index=combined.index)
    for column in MODEL_REQUIRED_FIELDS:
        values = pd.to_numeric(combined[column], errors="coerce")
        model_complete &= values.notna() & np.isfinite(values)
    combined["python_added_lines_model_fields_complete"] = model_complete
    combined["sonarqube_backend_available"] = (
        combined["python_added_lines_available"]
        & combined["sonarqube_available"]
        & combined["python_added_lines_model_fields_complete"]
        & ~combined["python_added_lines_identity_mismatch"]
        & ~combined["python_added_lines_original_value_mismatch"]
        & ~combined["python_added_lines_log_transform_mismatch"]
    )
    combined["cloc_backend_available"] = (
        combined["python_added_lines_available"]
        & combined["cloc_available"]
        & combined["python_added_lines_model_fields_complete"]
        & ~combined["python_added_lines_identity_mismatch"]
        & ~combined["python_added_lines_original_value_mismatch"]
        & ~combined["python_added_lines_log_transform_mismatch"]
    )
    combined["python_added_lines_common_available"] = (
        combined["sonarqube_backend_available"] & combined["cloc_backend_available"]
    )
    return combined.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def build_backend_panel(combined: pd.DataFrame, backend: str) -> pd.DataFrame:
    """Create one same-sample backend panel from the common available rows."""
    output = combined[combined["python_added_lines_common_available"]].copy()
    if backend == "sonarqube":
        metric = "ncloc_py_sonarqube"
        status = "sonarqube_status"
        source = "run-x-b01-sonarqube-python-only-existing-csv"
    elif backend == "cloc":
        metric = "ncloc_py_cloc"
        status = "cloc_status"
        source = "run-x-b02-v4-cloc-python-only"
    else:
        raise ValueError(f"Unsupported backend: {backend}")
    output["ncloc"] = pd.to_numeric(output[metric], errors="coerce")
    output["ncloc_py"] = output["ncloc"]
    output["ncloc_backend"] = backend
    output["ncloc_source"] = source
    output["ncloc_py_status"] = output[status]
    output["ncloc_py_available"] = True
    output["python_added_lines_did_complete"] = 1
    output["did_primary_outcome"] = "log_lines_added_py_source"
    output["did_robustness_outcomes"] = "log_lines_added_py_no_merge|log_lines_added_py_source_no_tests|log_lines_added_py_all"
    output["python_velocity_metric_version"] = IMPLEMENTATION_VERSION
    return output.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def numeric_equal(left: pd.Series, right: pd.Series) -> pd.Series:
    """Compare numeric columns with paired missing values treated as equal."""
    return pd.Series(
        np.isclose(
            pd.to_numeric(left, errors="coerce"),
            pd.to_numeric(right, errors="coerce"),
            rtol=0,
            atol=0,
            equal_nan=True,
        ),
        index=left.index,
    )


def backend_preservation_mismatches(sonar: pd.DataFrame, cloc: pd.DataFrame) -> int:
    """Count rows where non-NCLOC fields differ across backend panels."""
    if len(sonar) != len(cloc):
        return max(len(sonar), len(cloc))
    left = sonar.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    right = cloc.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    mismatch = pd.Series(False, index=left.index)
    for column in PRESERVATION_COLUMNS:
        if column not in left.columns or column not in right.columns:
            mismatch |= True
            continue
        if pd.api.types.is_numeric_dtype(left[column]) or pd.api.types.is_numeric_dtype(right[column]):
            mismatch |= ~numeric_equal(left[column], right[column])
        else:
            mismatch |= left[column].map(clean_text).ne(right[column].map(clean_text))
    return int(mismatch.sum())


def build_qc_and_summary(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    manifest: pd.DataFrame,
    added: pd.DataFrame,
    snapshots: pd.DataFrame,
    combined: pd.DataFrame,
    sonar_panel: pd.DataFrame,
    cloc_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build panel QC checks and a long-form summary."""
    records: list[dict[str, Any]] = []

    def add_check(
        name: str,
        observed: Any,
        expected: Any,
        *,
        policy: str = "always",
        note: str = "",
    ) -> None:
        if observed == expected:
            status = "pass"
        elif policy == "always":
            status = "fail"
        elif policy == "strict":
            status = "fail" if args.strict_expected_counts else "warn"
        else:
            status = "warn"
        records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "policy": policy,
                "note": note,
            }
        )

    joined_rows = int(combined["python_added_lines_joined"].sum())
    not_selected_rows = len(combined) - joined_rows
    added_available_rows = int(combined["python_added_lines_available"].sum())
    cloc_result_rows = int(combined["snapshot_key_cloc"].notna().groupby(combined["_snapshot_identity"]).max().sum())
    expected_cloc_rows = cloc_result_rows if args.partial_run else args.expected_snapshots
    expected_added_rows = len(added) if args.partial_run else args.expected_panel_rows

    add_check("base_panel_rows", len(panel), args.expected_panel_rows, policy="strict")
    add_check("base_panel_repositories", panel["repo_name"].nunique(), args.expected_repositories, policy="strict")
    add_check("snapshot_manifest_rows", len(manifest), args.expected_snapshots, policy="strict")
    add_check(
        "python_added_lines_rows",
        len(added),
        args.expected_panel_rows,
        policy="warn" if args.partial_run else "strict",
        note="A partial smoke run is expected to contain fewer rows." if args.partial_run else "",
    )
    add_check("combined_panel_rows", len(combined), len(panel), policy="always")
    add_check("duplicate_combined_repo_month_rows", int(combined.duplicated(["repo_id", "time_index"]).sum()), 0)
    add_check(
        "python_added_lines_not_selected_rows",
        not_selected_rows,
        0,
        policy="warn" if args.partial_run else "strict",
        note="Rows outside a partial smoke selection remain in the full audit panel." if args.partial_run else "",
    )
    add_check(
        "python_added_lines_identity_mismatches_joined_rows",
        int(combined["python_added_lines_identity_mismatch"].sum()),
        0,
        policy="always",
    )
    add_check(
        "python_added_lines_original_value_mismatches_joined_rows",
        int(combined["python_added_lines_original_value_mismatch"].sum()),
        0,
        policy="always",
    )
    add_check(
        "python_log_transform_mismatches_joined_rows",
        int(combined["python_added_lines_log_transform_mismatch"].sum()),
        0,
        policy="always",
    )
    joined_mask = combined["python_added_lines_joined"]
    reference_drift = joined_mask & pd.to_numeric(
        combined["reference_reconciliation_complete"], errors="coerce"
    ).fillna(0).ne(1)
    add_check(
        "reference_reconciliation_drift_rows_joined",
        int(reference_drift.sum()),
        0,
        policy="warn",
        note="Model A reconciliation is an audit reference and does not gate availability.",
    )
    complete_reference_drift = reference_drift & pd.to_numeric(
        combined["python_added_lines_complete"], errors="coerce"
    ).fillna(0).eq(1)
    add_check(
        "technically_complete_reference_drift_rows_excluded",
        int((complete_reference_drift & ~combined["python_added_lines_available"]).sum()),
        0,
        policy="always",
        note="Complete rows with reference drift must remain available in v4.",
    )
    for outcome in OUTCOME_NAMES:
        add_check(
            f"negative_{outcome}",
            int((pd.to_numeric(combined.loc[combined["python_added_lines_joined"], outcome], errors="coerce") < 0).sum()),
            0,
            policy="always",
        )
    add_check(
        "sonarqube_successful_snapshots",
        int(snapshots["sonarqube_available"].sum()),
        args.expected_snapshots,
        policy="strict",
    )
    add_check(
        "cloc_result_snapshots",
        int(snapshots["snapshot_key_cloc"].notna().sum()),
        expected_cloc_rows,
        policy="always",
    )
    add_check(
        "cloc_successful_snapshots",
        int(snapshots["cloc_available"].sum()),
        expected_cloc_rows,
        policy="warn" if args.partial_run else "strict",
    )
    add_check(
        "both_ncloc_successful_snapshots",
        int(snapshots["both_ncloc_available"].sum()),
        expected_cloc_rows,
        policy="warn" if args.partial_run else "strict",
    )
    add_check(
        "python_added_lines_available_rows",
        added_available_rows,
        expected_added_rows,
        policy="warn" if args.partial_run else "strict",
    )
    add_check(
        "common_sample_rows",
        int(combined["python_added_lines_common_available"].sum()),
        expected_added_rows,
        policy="warn" if args.partial_run else "strict",
        note="Independent LIMIT_REPOS and LIMIT_SNAPSHOTS settings can reduce overlap in a smoke run.",
    )
    add_check("sonarqube_panel_rows", len(sonar_panel), int(combined["python_added_lines_common_available"].sum()))
    add_check("cloc_panel_rows", len(cloc_panel), int(combined["python_added_lines_common_available"].sum()))
    add_check(
        "backend_repo_month_key_mismatches",
        int(
            (
                sonar_panel[["repo_id", "time_index"]].reset_index(drop=True)
                != cloc_panel[["repo_id", "time_index"]].reset_index(drop=True)
            ).any(axis=1).sum()
        ) if len(sonar_panel) == len(cloc_panel) else max(len(sonar_panel), len(cloc_panel)),
        0,
    )
    add_check("backend_non_ncloc_field_mismatches", backend_preservation_mismatches(sonar_panel, cloc_panel), 0)
    add_check(
        "sonarqube_ncloc_alias_mismatches",
        int((~numeric_equal(sonar_panel["ncloc"], sonar_panel["ncloc_py_sonarqube"])).sum()),
        0,
    )
    add_check(
        "cloc_ncloc_alias_mismatches",
        int((~numeric_equal(cloc_panel["ncloc"], cloc_panel["ncloc_py_cloc"])).sum()),
        0,
    )
    qc = pd.DataFrame(records)

    summary_rows: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_rows.append({"section": section, "metric": metric, "value": value, "note": note})

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "partial_run", int(args.partial_run))
    add_summary("definition", "primary_outcome", "log_lines_added_py_source")
    add_summary("definition", "robustness_outcomes", "log_lines_added_py_no_merge|log_lines_added_py_source_no_tests|log_lines_added_py_all")
    add_summary("definition", "raw_outcome", "lines_added_py_source")
    add_summary("definition", "legacy_raw_outcome", "lines_added_py_all")
    add_summary("definition", "sonarqube_ncloc_metric", "ncloc_py_sonarqube")
    add_summary("definition", "cloc_ncloc_metric", "ncloc_py_cloc")
    add_summary("definition", "backend_sample", "exact_common_sample")
    add_summary("definition", "model_a_reconciliation_policy", "warning_only_reference_drift_audit")
    add_summary("input", "panel_rows", len(panel))
    add_summary("input", "snapshots", len(manifest))
    add_summary("input", "python_added_lines_rows", len(added))
    add_summary("availability", "python_added_lines_joined_rows", joined_rows)
    add_summary("availability", "python_added_lines_not_selected_rows", not_selected_rows)
    add_summary("availability", "python_added_lines_rows", added_available_rows)
    add_summary("reference_drift", "joined_rows", int((combined["python_added_lines_joined"] & pd.to_numeric(combined["reference_reconciliation_complete"], errors="coerce").fillna(0).ne(1)).sum()))
    add_summary("availability", "sonarqube_rows", int(combined["sonarqube_backend_available"].sum()))
    add_summary("availability", "cloc_rows", int(combined["cloc_backend_available"].sum()))
    add_summary("availability", "common_rows", int(combined["python_added_lines_common_available"].sum()))
    add_summary("output", "sonarqube_panel_rows", len(sonar_panel))
    add_summary("output", "cloc_panel_rows", len(cloc_panel))
    for outcome in OUTCOME_NAMES:
        add_summary("metric", f"{outcome}_total", int(pd.to_numeric(combined[outcome], errors="coerce").fillna(0).sum()))
    add_summary("qc", "blocking_failures", int(qc["status"].eq("fail").sum()))
    add_summary("qc", "warnings", int(qc["status"].eq("warn").sum()))
    return qc, pd.DataFrame(summary_rows)


def drop_internal(df: pd.DataFrame) -> pd.DataFrame:
    """Remove internal join columns from user-facing outputs."""
    internal = [
        "_snapshot_identity",
        "added_repo_name",
        "added_dataset_source",
        "added_time",
        "_python_added_lines_row_present",
    ]
    return df.drop(columns=internal, errors="ignore")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Prepare Python added-lines DiD panels.")
    parser.add_argument("--base-panel-file", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-file", type=Path, required=True)
    parser.add_argument("--python-added-lines-file", type=Path, required=True)
    parser.add_argument("--cloc-results-file", type=Path, required=True)
    parser.add_argument("--sonarqube-results-file", type=Path, required=True)
    parser.add_argument("--combined-panel-output", type=Path, required=True)
    parser.add_argument("--sonarqube-panel-output", type=Path, required=True)
    parser.add_argument("--cloc-panel-output", type=Path, required=True)
    parser.add_argument("--common-sample-output", type=Path, required=True)
    parser.add_argument("--snapshot-comparison-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--partial-run", action="store_true")
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main() -> int:
    """Run the Python added-lines panel preparation workflow."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    string_columns = [
        "dataset_source",
        "repo_name",
        "time",
        "latest_commit_effective",
        "commit_sha",
        "snapshot_key",
    ]
    panel = normalize_base(read_csv_stable(args.base_panel_file, string_columns))
    manifest = normalize_manifest(read_csv_stable(args.snapshot_manifest_file, string_columns))
    added = normalize_added(read_csv_stable(args.python_added_lines_file, string_columns))
    cloc = normalize_cloc(read_csv_stable(args.cloc_results_file, string_columns))
    sonar = normalize_sonar(read_csv_stable(args.sonarqube_results_file, string_columns))
    snapshots = build_snapshot_comparison(manifest, cloc, sonar)
    combined = build_combined_panel(panel, added, snapshots)
    sonar_panel = build_backend_panel(combined, "sonarqube")
    cloc_panel = build_backend_panel(combined, "cloc")
    common_sample = combined[combined["python_added_lines_common_available"]].copy()
    unresolved = combined[~combined["python_added_lines_common_available"]].copy()
    qc, summary = build_qc_and_summary(
        args,
        panel,
        manifest,
        added,
        snapshots,
        combined,
        sonar_panel,
        cloc_panel,
    )
    save_dataframe(drop_internal(combined), args.combined_panel_output)
    save_dataframe(drop_internal(sonar_panel), args.sonarqube_panel_output)
    save_dataframe(drop_internal(cloc_panel), args.cloc_panel_output)
    save_dataframe(drop_internal(common_sample), args.common_sample_output)
    save_dataframe(drop_internal(snapshots), args.snapshot_comparison_output)
    save_dataframe(drop_internal(unresolved), args.unresolved_output)
    save_dataframe(qc, args.qc_output)
    save_dataframe(summary, args.summary_output)
    failures = qc[qc["status"].eq("fail")]
    logging.info(
        "Completed panel preparation: combined=%d; common=%d; sonarqube=%d; "
        "cloc=%d; unresolved=%d; failures=%d; warnings=%d",
        len(combined),
        len(common_sample),
        len(sonar_panel),
        len(cloc_panel),
        len(unresolved),
        len(failures),
        int(qc["status"].eq("warn").sum()),
    )
    if not failures.empty:
        logging.error("Blocking QC failures:\n%s", failures.to_string(index=False))
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("prepare_python_added_lines_did_panels failed: %s", exc)
        raise SystemExit(1)
