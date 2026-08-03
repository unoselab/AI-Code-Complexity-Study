#!/usr/bin/env python3
"""Prepare Python-NCLOC velocity DiD panels from SonarQube and cloc results.

This program is the self-contained analysis implementation for run-x-b02.
It does not call any prior experiment script. The workflow is:

1. Read the final 1,954-row run-x-a05 Model A panel.
2. Read the 1,496-snapshot run-x-a05 Python-NCLOC manifest.
3. Read the completed run-x-b01 local cloc results.
4. Read the completed run-x-b01 SonarQube results.
5. Validate snapshot identity, repository-month coverage, and result status.
6. Join both Python-only NCLOC measurements to every Model A panel row.
7. Write backend-specific DiD panels whose generic ``ncloc`` column points to
   either SonarQube or cloc while preserving the Model A NCLOC provenance.
8. Write a common-sample panel, snapshot comparison, unresolved audit, QC, and
   long-form summary.

The two Python-NCLOC backends are never averaged or calibrated to each other.
They remain separate measurement specifications for the later DiD analysis.
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v1"

BASE_PANEL_REQUIRED_COLUMNS = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "treatment_group",
    "time",
    "time_index",
    "event",
    "event_index",
    "post_event",
    "time_to_event",
    "commits",
    "log_commits",
    "lines_added",
    "log_lines_added",
    "contributors",
    "log_contributors",
    "stars",
    "log_stars",
    "issues",
    "log_issues",
    "age",
    "log_age",
    "ncloc",
    "ncloc_source",
    "model_a_complete",
    "latest_commit_effective",
    "model_c_snapshot_key",
}

SNAPSHOT_MANIFEST_REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "repo_key",
    "latest_commit_effective",
    "repo_month_rows",
    "first_panel_month",
    "last_panel_month",
    "python_file_count_all",
    "tracked_file_count",
    "ncloc_model_a",
}

LOCAL_RESULT_REQUIRED_COLUMNS = {
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "repo_key",
    "commit_sha",
    "repo_month_rows",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "python_file_count_cloc",
    "python_file_count_cloc_matches_git",
    "ncloc_py_cloc",
    "cloc_status",
    "cloc_version",
    "cloc_runtime_seconds",
}

SONAR_RESULT_REQUIRED_COLUMNS = {
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "repo_key",
    "commit_sha",
    "repo_month_rows",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "ncloc_py_sonarqube",
    "status",
    "project_key",
    "project_version",
    "scanner_log_path",
    "runtime_seconds",
}

KEY_STRING_COLUMNS = [
    "dataset_source",
    "repo_name",
    "repo_key",
    "latest_commit_effective",
    "commit_sha",
    "snapshot_key",
    "model_c_snapshot_key",
]

PRESERVATION_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "treatment_group",
    "time",
    "time_index",
    "event",
    "event_index",
    "post_event",
    "time_to_event",
    "commits",
    "log_commits",
    "lines_added",
    "log_lines_added",
    "age",
    "log_age",
    "contributors",
    "log_contributors",
    "stars",
    "log_stars",
    "issues",
    "log_issues",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Join completed SonarQube and cloc Python-NCLOC results to the "
            "final velocity DiD panel and create backend-specific inputs."
        )
    )
    parser.add_argument("--base-panel-file", required=True, type=Path)
    parser.add_argument("--snapshot-manifest-file", required=True, type=Path)
    parser.add_argument("--local-results-file", required=True, type=Path)
    parser.add_argument("--sonarqube-results-file", required=True, type=Path)
    parser.add_argument("--combined-panel-output", required=True, type=Path)
    parser.add_argument("--sonarqube-panel-output", required=True, type=Path)
    parser.add_argument("--cloc-panel-output", required=True, type=Path)
    parser.add_argument("--common-sample-output", required=True, type=Path)
    parser.add_argument("--snapshot-comparison-output", required=True, type=Path)
    parser.add_argument("--unresolved-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-treatment-panel-rows", type=int, default=914)
    parser.add_argument("--expected-control-panel-rows", type=int, default=1040)
    parser.add_argument("--expected-treatment-snapshots", type=int, default=790)
    parser.add_argument("--expected-control-snapshots", type=int, default=706)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    """Configure compact timestamped logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def clean_text(value: object) -> str:
    """Return a trimmed string while treating missing values as empty."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Fail when an input is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    """Read a CSV while preserving identity columns as strings."""
    if not path.is_file():
        raise FileNotFoundError(f"Required input file not found: {path}")
    header = pd.read_csv(path, nrows=0)
    dtype = {
        column: "string"
        for column in string_columns
        if column in header.columns
    }
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(temporary, index=False)
    temporary.replace(target)


def identity_key(
    dataset_source: pd.Series,
    repo_name: pd.Series,
    commit_sha: pd.Series,
) -> pd.Series:
    """Create a normalized repository-snapshot identity."""
    return (
        dataset_source.map(clean_text).str.casefold()
        + "|"
        + repo_name.map(clean_text).str.casefold()
        + "|"
        + commit_sha.map(clean_text).str.casefold()
    )


def validate_unique_identity(df: pd.DataFrame, label: str) -> None:
    """Ensure one row per normalized snapshot identity."""
    duplicated = df["_snapshot_identity"].duplicated(keep=False)
    if duplicated.any():
        sample = df.loc[
            duplicated,
            ["dataset_source", "repo_name", "_commit_sha", "_snapshot_identity"],
        ].head(20)
        raise ValueError(
            f"{label} contains duplicate snapshot identities: "
            + repr(sample.to_dict(orient="records"))
        )


def normalize_base_panel(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate the final run-x-a05 Model A panel."""
    require_columns(raw, BASE_PANEL_REQUIRED_COLUMNS, "base Model A panel")
    panel = raw.copy()
    panel["dataset_source"] = panel["dataset_source"].map(clean_text).str.casefold()
    panel["repo_name"] = panel["repo_name"].map(clean_text)
    panel["latest_commit_effective"] = (
        panel["latest_commit_effective"].map(clean_text).str.casefold()
    )
    panel["model_c_snapshot_key"] = panel["model_c_snapshot_key"].map(clean_text)

    if not set(panel["dataset_source"].unique()).issubset({"treatment", "control"}):
        raise ValueError("Base panel contains unexpected dataset_source values")

    panel["repo_id"] = pd.to_numeric(panel["repo_id"], errors="raise").astype(int)
    panel["time_index"] = pd.to_numeric(panel["time_index"], errors="raise").astype(int)
    panel["treatment_group"] = (
        pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
    )
    panel["model_a_complete"] = (
        pd.to_numeric(panel["model_a_complete"], errors="raise").astype(int)
    )
    panel["ncloc"] = pd.to_numeric(panel["ncloc"], errors="coerce")

    duplicate_repo_month = panel.duplicated(["repo_id", "time_index"], keep=False)
    if duplicate_repo_month.any():
        sample = panel.loc[
            duplicate_repo_month,
            ["repo_id", "repo_name", "time", "time_index"],
        ].head(20)
        raise ValueError(
            "Base panel contains duplicate repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )

    if panel["model_a_complete"].ne(1).any():
        raise ValueError("Base panel contains rows that are not Model A complete cases")
    if panel["ncloc"].isna().any() or (panel["ncloc"] < 0).any():
        raise ValueError("Base panel contains missing or negative Model A NCLOC")

    expected_legacy_key = (
        panel["dataset_source"]
        + "|"
        + panel["repo_name"]
        + "|"
        + panel["latest_commit_effective"]
    )
    panel["model_c_snapshot_key_format_matches"] = expected_legacy_key.eq(
        panel["model_c_snapshot_key"]
    )
    panel["_snapshot_identity"] = identity_key(
        panel["dataset_source"],
        panel["repo_name"],
        panel["latest_commit_effective"],
    )

    panel["ncloc_model_a"] = panel["ncloc"]
    panel["ncloc_source_model_a"] = panel["ncloc_source"].map(clean_text)
    return panel


def normalize_snapshot_manifest(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the run-x-a05 unique snapshot manifest."""
    require_columns(raw, SNAPSHOT_MANIFEST_REQUIRED_COLUMNS, "snapshot manifest")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_key"].map(clean_text).str.casefold()
    data["latest_commit_effective"] = (
        data["latest_commit_effective"].map(clean_text).str.casefold()
    )
    data["_commit_sha"] = data["latest_commit_effective"]
    data["_snapshot_identity"] = identity_key(
        data["dataset_source"], data["repo_name"], data["_commit_sha"]
    )
    validate_unique_identity(data, "snapshot manifest")

    for column in [
        "repo_month_rows",
        "python_file_count_all",
        "tracked_file_count",
        "ncloc_model_a",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data["repo_month_rows"].isna().any() or (data["repo_month_rows"] <= 0).any():
        raise ValueError("Snapshot manifest contains invalid repo_month_rows")
    return data


def normalize_local_results(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the completed local cloc snapshot results."""
    require_columns(raw, LOCAL_RESULT_REQUIRED_COLUMNS, "local cloc results")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_key"].map(clean_text).str.casefold()
    data["commit_sha"] = data["commit_sha"].map(clean_text).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean_text)
    data["_commit_sha"] = data["commit_sha"]
    data["_snapshot_identity"] = identity_key(
        data["dataset_source"], data["repo_name"], data["commit_sha"]
    )
    validate_unique_identity(data, "local cloc results")

    numeric_columns = [
        "manifest_order",
        "repo_month_rows",
        "python_file_count_manifest",
        "python_file_count_git",
        "python_file_count_cloc",
        "ncloc_py_cloc",
        "cloc_runtime_seconds",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["cloc_status"] = data["cloc_status"].map(clean_text).str.casefold()
    data["cloc_available"] = data["cloc_status"].eq("success") & data[
        "ncloc_py_cloc"
    ].notna()
    return data


def normalize_sonarqube_results(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the completed SonarQube snapshot results."""
    require_columns(raw, SONAR_RESULT_REQUIRED_COLUMNS, "SonarQube results")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_key"].map(clean_text).str.casefold()
    data["commit_sha"] = data["commit_sha"].map(clean_text).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean_text)
    data["_commit_sha"] = data["commit_sha"]
    data["_snapshot_identity"] = identity_key(
        data["dataset_source"], data["repo_name"], data["commit_sha"]
    )
    validate_unique_identity(data, "SonarQube results")

    numeric_columns = [
        "manifest_order",
        "repo_month_rows",
        "python_file_count_manifest",
        "python_file_count_git",
        "ncloc_py_sonarqube",
        "runtime_seconds",
        "scanner_return_code",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["status"] = data["status"].map(clean_text).str.casefold()
    data["sonarqube_available"] = data["status"].eq("success") & data[
        "ncloc_py_sonarqube"
    ].notna()
    return data


def build_snapshot_comparison(
    manifest: pd.DataFrame,
    local: pd.DataFrame,
    sonar: pd.DataFrame,
) -> pd.DataFrame:
    """Create one audited comparison row per repository snapshot."""
    manifest_columns = [
        "_snapshot_identity",
        "dataset_source",
        "repo_name",
        "repo_key",
        "latest_commit_effective",
        "repo_month_rows",
        "first_panel_month",
        "last_panel_month",
        "python_file_count_all",
        "tracked_file_count",
        "ncloc_model_a",
    ]
    comparison = manifest[manifest_columns].copy()
    comparison = comparison.rename(
        columns={
            "latest_commit_effective": "commit_sha",
            "repo_month_rows": "repo_month_rows_manifest",
            "python_file_count_all": "python_file_count_manifest_a05",
            "tracked_file_count": "tracked_file_count_a05",
            "ncloc_model_a": "ncloc_model_a_snapshot",
        }
    )

    local_columns = [
        "_snapshot_identity",
        "manifest_order",
        "snapshot_key",
        "repo_month_rows",
        "python_file_count_manifest",
        "python_file_count_git",
        "python_file_count_matches_manifest",
        "python_file_count_cloc",
        "python_file_count_cloc_matches_git",
        "ncloc_py_cloc",
        "cloc_status",
        "cloc_available",
        "cloc_version",
        "cloc_runtime_seconds",
    ]
    local_selected = local[local_columns].rename(
        columns={
            "manifest_order": "manifest_order_local",
            "snapshot_key": "snapshot_key_local",
            "repo_month_rows": "repo_month_rows_local",
            "python_file_count_manifest": "python_file_count_manifest_local",
            "python_file_count_git": "python_file_count_git_local",
            "python_file_count_matches_manifest": "python_file_count_local_matches_manifest",
            "python_file_count_cloc_matches_git": "python_file_count_cloc_matches_git_local",
        }
    )

    sonar_columns = [
        "_snapshot_identity",
        "manifest_order",
        "snapshot_key",
        "repo_month_rows",
        "python_file_count_manifest",
        "python_file_count_git",
        "python_file_count_matches_manifest",
        "ncloc_py_sonarqube",
        "status",
        "sonarqube_available",
        "project_key",
        "project_version",
        "scanner_log_path",
        "runtime_seconds",
    ]
    sonar_selected = sonar[sonar_columns].rename(
        columns={
            "manifest_order": "manifest_order_sonarqube",
            "snapshot_key": "snapshot_key_sonarqube",
            "repo_month_rows": "repo_month_rows_sonarqube",
            "python_file_count_manifest": "python_file_count_manifest_sonarqube",
            "python_file_count_git": "python_file_count_worktree_sonarqube",
            "python_file_count_matches_manifest": "python_file_count_sonarqube_matches_manifest",
            "status": "sonarqube_status",
            "runtime_seconds": "sonarqube_runtime_seconds",
        }
    )

    comparison = comparison.merge(
        local_selected,
        on="_snapshot_identity",
        how="left",
        validate="one_to_one",
    )
    comparison = comparison.merge(
        sonar_selected,
        on="_snapshot_identity",
        how="left",
        validate="one_to_one",
    )

    comparison["snapshot_key_matches_backends"] = comparison[
        "snapshot_key_local"
    ].eq(comparison["snapshot_key_sonarqube"])
    comparison["manifest_order_matches_backends"] = comparison[
        "manifest_order_local"
    ].eq(comparison["manifest_order_sonarqube"])
    comparison["repo_month_rows_match_all"] = (
        comparison["repo_month_rows_manifest"]
        .eq(comparison["repo_month_rows_local"])
        .fillna(False)
        & comparison["repo_month_rows_manifest"]
        .eq(comparison["repo_month_rows_sonarqube"])
        .fillna(False)
    )
    comparison["python_ncloc_both_available"] = (
        comparison["cloc_available"].fillna(False)
        & comparison["sonarqube_available"].fillna(False)
    )
    comparison["sonarqube_minus_cloc"] = (
        comparison["ncloc_py_sonarqube"] - comparison["ncloc_py_cloc"]
    )
    comparison["sonarqube_minus_model_a"] = (
        comparison["ncloc_py_sonarqube"]
        - comparison["ncloc_model_a_snapshot"]
    )
    comparison["cloc_minus_model_a"] = (
        comparison["ncloc_py_cloc"] - comparison["ncloc_model_a_snapshot"]
    )
    cloc_denominator = comparison["ncloc_py_cloc"].replace(0, np.nan)
    comparison["sonarqube_minus_cloc_relative"] = (
        comparison["sonarqube_minus_cloc"] / cloc_denominator
    )
    comparison["log1p_ncloc_py_sonarqube"] = np.log1p(
        comparison["ncloc_py_sonarqube"]
    )
    comparison["log1p_ncloc_py_cloc"] = np.log1p(comparison["ncloc_py_cloc"])
    comparison["log1p_sonarqube_minus_cloc"] = (
        comparison["log1p_ncloc_py_sonarqube"]
        - comparison["log1p_ncloc_py_cloc"]
    )
    comparison["exact_match_sonarqube_cloc"] = comparison[
        "ncloc_py_sonarqube"
    ].eq(comparison["ncloc_py_cloc"])

    preferred_order = [
        "manifest_order_sonarqube",
        "snapshot_key_sonarqube",
        "dataset_source",
        "repo_name",
        "repo_key",
        "commit_sha",
        "repo_month_rows_manifest",
        "first_panel_month",
        "last_panel_month",
        "ncloc_model_a_snapshot",
        "ncloc_py_sonarqube",
        "sonarqube_status",
        "ncloc_py_cloc",
        "cloc_status",
        "python_ncloc_both_available",
        "sonarqube_minus_cloc",
        "sonarqube_minus_cloc_relative",
        "log1p_sonarqube_minus_cloc",
        "exact_match_sonarqube_cloc",
        "sonarqube_minus_model_a",
        "cloc_minus_model_a",
        "python_file_count_manifest_a05",
        "python_file_count_worktree_sonarqube",
        "python_file_count_sonarqube_matches_manifest",
        "python_file_count_git_local",
        "python_file_count_cloc",
        "python_file_count_cloc_matches_git_local",
        "snapshot_key_matches_backends",
        "manifest_order_matches_backends",
        "repo_month_rows_match_all",
        "project_key",
        "project_version",
        "scanner_log_path",
        "sonarqube_runtime_seconds",
        "cloc_version",
        "cloc_runtime_seconds",
        "_snapshot_identity",
    ]
    remaining = [column for column in comparison.columns if column not in preferred_order]
    return comparison[preferred_order + remaining].sort_values(
        ["manifest_order_sonarqube", "dataset_source", "repo_name"],
        kind="stable",
    ).reset_index(drop=True)


def build_combined_panel(
    panel: pd.DataFrame,
    snapshot_comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Join both Python-NCLOC backends to every repository-month row."""
    merge_columns = [
        "_snapshot_identity",
        "snapshot_key_sonarqube",
        "snapshot_key_local",
        "ncloc_py_sonarqube",
        "sonarqube_status",
        "sonarqube_available",
        "ncloc_py_cloc",
        "cloc_status",
        "cloc_available",
        "python_ncloc_both_available",
        "sonarqube_minus_cloc",
        "sonarqube_minus_cloc_relative",
        "log1p_ncloc_py_sonarqube",
        "log1p_ncloc_py_cloc",
        "log1p_sonarqube_minus_cloc",
        "exact_match_sonarqube_cloc",
        "python_file_count_worktree_sonarqube",
        "python_file_count_cloc",
        "project_key",
        "project_version",
        "scanner_log_path",
        "cloc_version",
    ]
    combined = panel.merge(
        snapshot_comparison[merge_columns],
        on="_snapshot_identity",
        how="left",
        validate="many_to_one",
    )
    combined["python_ncloc_snapshot_key"] = combined["snapshot_key_sonarqube"]
    combined["ncloc_py_sonarqube_status"] = combined["sonarqube_status"]
    combined["ncloc_py_cloc_status"] = combined["cloc_status"]
    combined["ncloc_py_sonarqube_available"] = combined[
        "sonarqube_available"
    ].fillna(False)
    combined["ncloc_py_cloc_available"] = combined["cloc_available"].fillna(False)
    combined["python_ncloc_both_available"] = combined[
        "python_ncloc_both_available"
    ].fillna(False)
    combined["ncloc_py_sonarqube_source"] = np.where(
        combined["ncloc_py_sonarqube_available"],
        "run-x-b01-sonarqube-python-only",
        "",
    )
    combined["ncloc_py_cloc_source"] = np.where(
        combined["ncloc_py_cloc_available"],
        "run-x-b01-cloc-python-only",
        "",
    )
    return combined.sort_values(["repo_id", "time_index"], kind="stable").reset_index(
        drop=True
    )


def build_backend_panel(
    combined: pd.DataFrame,
    *,
    backend: str,
) -> pd.DataFrame:
    """Create a complete-case DiD panel for one Python-NCLOC backend."""
    if backend == "sonarqube":
        metric_column = "ncloc_py_sonarqube"
        status_column = "ncloc_py_sonarqube_status"
        available_column = "ncloc_py_sonarqube_available"
        source_value = "run-x-b01-sonarqube-python-only"
    elif backend == "cloc":
        metric_column = "ncloc_py_cloc"
        status_column = "ncloc_py_cloc_status"
        available_column = "ncloc_py_cloc_available"
        source_value = "run-x-b01-cloc-python-only"
    else:
        raise ValueError(f"Unsupported backend: {backend}")

    output = combined[combined[available_column]].copy()
    output["ncloc"] = pd.to_numeric(output[metric_column], errors="coerce")
    output["ncloc_py"] = output["ncloc"]
    output["ncloc_backend"] = backend
    output["ncloc_source"] = source_value
    output["ncloc_py_status"] = output[status_column]
    output["ncloc_py_available"] = True
    output["ncloc_model_a_minus_python"] = output["ncloc_model_a"] - output["ncloc"]
    return output.sort_values(["repo_id", "time_index"], kind="stable").reset_index(
        drop=True
    )


def count_role_rows(df: pd.DataFrame, role: str) -> int:
    """Count rows for one dataset role."""
    return int(df["dataset_source"].eq(role).sum())


def count_role_repositories(df: pd.DataFrame, role: str) -> int:
    """Count unique repositories for one dataset role."""
    return int(df.loc[df["dataset_source"].eq(role), "repo_name"].nunique())


def numeric_equal(left: pd.Series, right: pd.Series) -> pd.Series:
    """Compare numeric columns while treating paired missing values as equal."""
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    return np.isclose(left_numeric, right_numeric, rtol=0.0, atol=0.0, equal_nan=True)


def preservation_mismatches(base: pd.DataFrame, candidate: pd.DataFrame) -> int:
    """Count altered non-NCLOC analysis values after a backend transformation."""
    if len(base) != len(candidate):
        return abs(len(base) - len(candidate)) + min(len(base), len(candidate))
    base_sorted = base.sort_values(["repo_id", "time_index"], kind="stable").reset_index(
        drop=True
    )
    candidate_sorted = candidate.sort_values(
        ["repo_id", "time_index"], kind="stable"
    ).reset_index(drop=True)
    mismatch_rows = pd.Series(False, index=base_sorted.index)
    for column in PRESERVATION_COLUMNS:
        if pd.api.types.is_numeric_dtype(base_sorted[column]) or pd.api.types.is_numeric_dtype(
            candidate_sorted[column]
        ):
            mismatch_rows |= ~numeric_equal(base_sorted[column], candidate_sorted[column])
        else:
            mismatch_rows |= base_sorted[column].map(clean_text).ne(
                candidate_sorted[column].map(clean_text)
            )
    return int(mismatch_rows.sum())


def build_qc_and_summary(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    manifest: pd.DataFrame,
    local: pd.DataFrame,
    sonar: pd.DataFrame,
    snapshot_comparison: pd.DataFrame,
    combined: pd.DataFrame,
    sonarqube_panel: pd.DataFrame,
    cloc_panel: pd.DataFrame,
    common_sample: pd.DataFrame,
    unresolved: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build check-oriented QC and long-form summary outputs."""
    records: list[dict[str, Any]] = []

    def add_check(
        name: str,
        observed: Any,
        expected: Any,
        *,
        severity: str = "fail",
        note: str = "",
    ) -> None:
        passed = observed == expected
        if passed:
            status = "pass"
        elif severity == "warn":
            status = "warn"
        else:
            status = "fail"
        records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    panel_snapshot_count = int(panel["_snapshot_identity"].nunique())
    manifest_identity_set = set(manifest["_snapshot_identity"])
    local_identity_set = set(local["_snapshot_identity"])
    sonar_identity_set = set(sonar["_snapshot_identity"])
    panel_identity_set = set(panel["_snapshot_identity"])

    add_check("input_panel_rows", len(panel), args.expected_panel_rows)
    add_check("input_panel_unique_snapshots", panel_snapshot_count, args.expected_snapshots)
    add_check(
        "input_treatment_panel_rows",
        count_role_rows(panel, "treatment"),
        args.expected_treatment_panel_rows,
    )
    add_check(
        "input_control_panel_rows",
        count_role_rows(panel, "control"),
        args.expected_control_panel_rows,
    )
    add_check("input_repositories", panel["repo_name"].nunique(), args.expected_repositories)
    add_check(
        "input_treatment_repositories",
        count_role_repositories(panel, "treatment"),
        args.expected_treatment_repositories,
    )
    add_check(
        "input_control_repositories",
        count_role_repositories(panel, "control"),
        args.expected_control_repositories,
    )
    add_check(
        "duplicate_input_repo_month_rows",
        int(panel.duplicated(["repo_id", "time_index"]).sum()),
        0,
    )
    add_check(
        "model_c_snapshot_key_format_mismatches",
        int((~panel["model_c_snapshot_key_format_matches"]).sum()),
        0,
    )
    add_check("snapshot_manifest_rows", len(manifest), args.expected_snapshots)
    add_check("local_result_rows", len(local), args.expected_snapshots)
    add_check("sonarqube_result_rows", len(sonar), args.expected_snapshots)
    add_check(
        "treatment_snapshots",
        int(manifest["dataset_source"].eq("treatment").sum()),
        args.expected_treatment_snapshots,
    )
    add_check(
        "control_snapshots",
        int(manifest["dataset_source"].eq("control").sum()),
        args.expected_control_snapshots,
    )
    add_check("panel_vs_manifest_snapshot_set_mismatches", len(panel_identity_set ^ manifest_identity_set), 0)
    add_check("manifest_vs_local_snapshot_set_mismatches", len(manifest_identity_set ^ local_identity_set), 0)
    add_check("manifest_vs_sonarqube_snapshot_set_mismatches", len(manifest_identity_set ^ sonar_identity_set), 0)
    add_check(
        "local_cloc_successful_snapshots",
        int(local["cloc_available"].sum()),
        args.expected_snapshots,
    )
    add_check(
        "sonarqube_successful_snapshots",
        int(sonar["sonarqube_available"].sum()),
        args.expected_snapshots,
    )
    add_check(
        "snapshot_key_backend_mismatches",
        int((~snapshot_comparison["snapshot_key_matches_backends"].fillna(False)).sum()),
        0,
    )
    add_check(
        "manifest_order_backend_mismatches",
        int((~snapshot_comparison["manifest_order_matches_backends"].fillna(False)).sum()),
        0,
    )
    add_check(
        "repo_month_rows_mismatches",
        int((~snapshot_comparison["repo_month_rows_match_all"].fillna(False)).sum()),
        0,
    )
    add_check("combined_panel_rows", len(combined), args.expected_panel_rows)
    add_check(
        "duplicate_combined_repo_month_rows",
        int(combined.duplicated(["repo_id", "time_index"]).sum()),
        0,
    )
    add_check(
        "missing_sonarqube_panel_rows",
        int((~combined["ncloc_py_sonarqube_available"]).sum()),
        0,
    )
    add_check(
        "missing_cloc_panel_rows",
        int((~combined["ncloc_py_cloc_available"]).sum()),
        0,
    )
    add_check("unresolved_panel_rows", len(unresolved), 0)
    add_check("sonarqube_panel_rows", len(sonarqube_panel), args.expected_panel_rows)
    add_check("cloc_panel_rows", len(cloc_panel), args.expected_panel_rows)
    add_check("common_sample_rows", len(common_sample), args.expected_panel_rows)
    add_check(
        "sonarqube_generic_ncloc_alias_mismatches",
        int((~numeric_equal(sonarqube_panel["ncloc"], sonarqube_panel["ncloc_py_sonarqube"])).sum()),
        0,
    )
    add_check(
        "cloc_generic_ncloc_alias_mismatches",
        int((~numeric_equal(cloc_panel["ncloc"], cloc_panel["ncloc_py_cloc"])).sum()),
        0,
    )
    add_check(
        "sonarqube_non_ncloc_field_mismatches",
        preservation_mismatches(panel, sonarqube_panel),
        0,
    )
    add_check(
        "cloc_non_ncloc_field_mismatches",
        preservation_mismatches(panel, cloc_panel),
        0,
    )
    add_check(
        "negative_sonarqube_ncloc",
        int((pd.to_numeric(combined["ncloc_py_sonarqube"], errors="coerce") < 0).sum()),
        0,
    )
    add_check(
        "negative_cloc_ncloc",
        int((pd.to_numeric(combined["ncloc_py_cloc"], errors="coerce") < 0).sum()),
        0,
    )

    sonar_manifest_mismatch = int(
        snapshot_comparison["python_file_count_sonarqube_matches_manifest"]
        .eq(False)
        .fillna(False)
        .sum()
    )
    cloc_git_mismatch = int(
        snapshot_comparison["python_file_count_cloc_matches_git_local"]
        .eq(False)
        .fillna(False)
        .sum()
    )
    exact_matches = int(snapshot_comparison["exact_match_sonarqube_cloc"].sum())
    add_check(
        "sonarqube_manifest_python_file_count_mismatches",
        sonar_manifest_mismatch,
        0,
        severity="warn",
        note="Retained as a file-inventory diagnostic; successful NCLOC remains available.",
    )
    add_check(
        "cloc_git_python_file_count_mismatches",
        cloc_git_mismatch,
        0,
        severity="warn",
        note="cloc may omit empty or zero-count Python files from by-file output.",
    )
    add_check(
        "sonarqube_cloc_exact_matches",
        exact_matches,
        args.expected_snapshots,
        severity="warn",
        note="Different NCLOC definitions are expected; the backends are analyzed separately.",
    )

    qc = pd.DataFrame(records)

    summary_records: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_records.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("definition", "target", "python_only_ncloc_velocity_did_panels")
    add_summary("definition", "sonarqube_metric", "ncloc_py_sonarqube")
    add_summary("definition", "cloc_metric", "ncloc_py_cloc")
    add_summary("definition", "backend_combination", "none_separate_specifications")
    add_summary("definition", "generic_model_column", "ncloc")
    add_summary("input", "panel_rows", len(panel))
    add_summary("input", "snapshots", len(manifest))
    add_summary("input", "repositories", panel["repo_name"].nunique())
    add_summary("input", "treatment_panel_rows", count_role_rows(panel, "treatment"))
    add_summary("input", "control_panel_rows", count_role_rows(panel, "control"))
    add_summary("input", "treatment_snapshots", int(manifest["dataset_source"].eq("treatment").sum()))
    add_summary("input", "control_snapshots", int(manifest["dataset_source"].eq("control").sum()))
    add_summary("output", "combined_panel_rows", len(combined))
    add_summary("output", "sonarqube_panel_rows", len(sonarqube_panel))
    add_summary("output", "cloc_panel_rows", len(cloc_panel))
    add_summary("output", "common_sample_rows", len(common_sample))
    add_summary("output", "unresolved_panel_rows", len(unresolved))
    add_summary("availability", "sonarqube_snapshots", int(snapshot_comparison["sonarqube_available"].sum()))
    add_summary("availability", "cloc_snapshots", int(snapshot_comparison["cloc_available"].sum()))
    add_summary("availability", "both_snapshots", int(snapshot_comparison["python_ncloc_both_available"].sum()))
    add_summary("comparison", "exact_matches", exact_matches)
    add_summary(
        "comparison",
        "sonarqube_greater_than_cloc",
        int((snapshot_comparison["sonarqube_minus_cloc"] > 0).sum()),
    )
    add_summary(
        "comparison",
        "sonarqube_less_than_cloc",
        int((snapshot_comparison["sonarqube_minus_cloc"] < 0).sum()),
    )

    comparable = snapshot_comparison[
        snapshot_comparison["python_ncloc_both_available"]
    ].copy()
    statistic_columns = {
        "sonarqube_minus_cloc": comparable["sonarqube_minus_cloc"],
        "sonarqube_minus_cloc_relative": comparable[
            "sonarqube_minus_cloc_relative"
        ],
        "log1p_sonarqube_minus_cloc": comparable[
            "log1p_sonarqube_minus_cloc"
        ],
        "ncloc_py_sonarqube": comparable["ncloc_py_sonarqube"],
        "ncloc_py_cloc": comparable["ncloc_py_cloc"],
    }
    for metric, values in statistic_columns.items():
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if numeric.empty:
            continue
        add_summary(metric, "min", float(numeric.min()))
        add_summary(metric, "median", float(numeric.median()))
        add_summary(metric, "mean", float(numeric.mean()))
        add_summary(metric, "max", float(numeric.max()))

    for role, role_data in comparable.groupby("dataset_source", sort=True):
        add_summary("comparison_by_role", f"{role}_snapshots", len(role_data))
        add_summary(
            "comparison_by_role",
            f"{role}_median_sonarqube_minus_cloc",
            float(role_data["sonarqube_minus_cloc"].median()),
        )
        add_summary(
            "comparison_by_role",
            f"{role}_mean_sonarqube_minus_cloc",
            float(role_data["sonarqube_minus_cloc"].mean()),
        )
        relative = pd.to_numeric(
            role_data["sonarqube_minus_cloc_relative"], errors="coerce"
        ).dropna()
        add_summary(
            "comparison_by_role",
            f"{role}_median_relative_gap",
            float(relative.median()) if not relative.empty else "",
        )
        add_summary(
            "comparison_by_role",
            f"{role}_mean_relative_gap",
            float(relative.mean()) if not relative.empty else "",
        )

    add_summary("qc", "sonarqube_manifest_file_count_mismatches", sonar_manifest_mismatch)
    add_summary("qc", "cloc_git_file_count_mismatches", cloc_git_mismatch)
    add_summary("qc", "hard_failures", int(qc["status"].eq("fail").sum()))
    add_summary("qc", "warnings", int(qc["status"].eq("warn").sum()))

    return qc, pd.DataFrame(summary_records)


def main() -> int:
    """Run the Python-NCLOC panel preparation workflow."""
    args = parse_args()
    configure_logging(args.log_level)

    for name in [
        "expected_panel_rows",
        "expected_snapshots",
        "expected_treatment_panel_rows",
        "expected_control_panel_rows",
        "expected_treatment_snapshots",
        "expected_control_snapshots",
        "expected_repositories",
        "expected_treatment_repositories",
        "expected_control_repositories",
    ]:
        if int(getattr(args, name)) < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative")

    logging.info("Reading base Model A panel: %s", args.base_panel_file)
    panel = normalize_base_panel(
        read_csv_stable(args.base_panel_file, KEY_STRING_COLUMNS)
    )
    logging.info("Reading snapshot manifest: %s", args.snapshot_manifest_file)
    manifest = normalize_snapshot_manifest(
        read_csv_stable(args.snapshot_manifest_file, KEY_STRING_COLUMNS)
    )
    logging.info("Reading local cloc results: %s", args.local_results_file)
    local = normalize_local_results(
        read_csv_stable(args.local_results_file, KEY_STRING_COLUMNS)
    )
    logging.info("Reading SonarQube results: %s", args.sonarqube_results_file)
    sonar = normalize_sonarqube_results(
        read_csv_stable(args.sonarqube_results_file, KEY_STRING_COLUMNS)
    )

    snapshot_comparison = build_snapshot_comparison(manifest, local, sonar)
    combined = build_combined_panel(panel, snapshot_comparison)
    sonarqube_panel = build_backend_panel(combined, backend="sonarqube")
    cloc_panel = build_backend_panel(combined, backend="cloc")
    common_sample = combined[combined["python_ncloc_both_available"]].copy()
    unresolved = combined[~combined["python_ncloc_both_available"]].copy()

    qc, summary = build_qc_and_summary(
        args,
        panel,
        manifest,
        local,
        sonar,
        snapshot_comparison,
        combined,
        sonarqube_panel,
        cloc_panel,
        common_sample,
        unresolved,
    )

    # Internal helper columns are excluded from user-facing panel outputs.
    panel_internal_columns = ["_snapshot_identity"]
    snapshot_internal_columns = ["_snapshot_identity"]
    combined_output = combined.drop(columns=panel_internal_columns, errors="ignore")
    sonarqube_output = sonarqube_panel.drop(columns=panel_internal_columns, errors="ignore")
    cloc_output = cloc_panel.drop(columns=panel_internal_columns, errors="ignore")
    common_output = common_sample.drop(columns=panel_internal_columns, errors="ignore")
    unresolved_output = unresolved.drop(columns=panel_internal_columns, errors="ignore")
    snapshot_output = snapshot_comparison.drop(
        columns=snapshot_internal_columns, errors="ignore"
    )

    save_dataframe(combined_output, args.combined_panel_output)
    save_dataframe(sonarqube_output, args.sonarqube_panel_output)
    save_dataframe(cloc_output, args.cloc_panel_output)
    save_dataframe(common_output, args.common_sample_output)
    save_dataframe(snapshot_output, args.snapshot_comparison_output)
    save_dataframe(unresolved_output, args.unresolved_output)
    save_dataframe(qc, args.qc_output)
    save_dataframe(summary, args.summary_output)

    hard_failures = qc[qc["status"].eq("fail")]
    logging.info(
        "Completed run-x-b02-%s: combined=%d; SonarQube=%d; cloc=%d; "
        "common=%d; unresolved=%d; QC failures=%d; warnings=%d",
        IMPLEMENTATION_VERSION,
        len(combined_output),
        len(sonarqube_output),
        len(cloc_output),
        len(common_output),
        len(unresolved_output),
        len(hard_failures),
        int(qc["status"].eq("warn").sum()),
    )

    if args.strict_expected_counts and not hard_failures.empty:
        logging.error("Strict QC failures remain:\n%s", hard_failures.to_string(index=False))
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
