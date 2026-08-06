#!/usr/bin/env python3
"""Build the run-x-d02 repository-month panel for the token metric.

This program is the self-contained analysis implementation for run-x-d02. It
reuses the validated panel-join design used by earlier project experiments but
does not call or import any earlier experiment script.

Workflow:
1. Read the final 1,954-row run-x-a05 Model A panel.
2. Read the 1,496-snapshot run-x-a05 Model C manifest.
3. Read the fully classified run-x-d01b-v2 snapshot results.
4. Read the explicit manual-review exclusion produced by run-x-d01b-v2.
5. Validate snapshot identity, row coverage, availability, and exclusion status.
6. Join the snapshot metric to every repository-month row.
7. Retain 1,953 metric-available rows and preserve the single documented
   TradeMind exclusion in dedicated audit outputs.
8. Write snapshot audit, all-row panel, usable panel, exclusions, unresolved
   rows, treatment estimability audit, QC, and summary outputs.

The primary later-model outcome is ``log_token_py_100_200``, defined as
``log1p(token_py_100_200)``. The raw metric and function-count companion
metrics remain available for robustness and descriptive analysis.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v1"
EXPERIMENT_NAME = "run-x-d02-prepare-token-py-repo-month-panel"
TOKEN_DEFINITION = "len(raw_implementation_body.split(' '))"
PRIMARY_RAW_METRIC = "token_py_100_200"
PRIMARY_LOG_METRIC = "log_token_py_100_200"

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
}

RESOLVED_RESULT_REQUIRED_COLUMNS = {
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "repo_key",
    "commit_sha",
    "repo_month_rows",
    "token_definition",
    "token_min_inclusive",
    "token_max_inclusive",
    "function_count_py_all",
    "function_count_py_extracted",
    "function_count_py_100_200",
    "function_count_py_docstring_only",
    "function_count_py_with_nested",
    "python_file_count_with_function",
    "python_file_count_with_function_100_200",
    "token_py_all_function_bodies",
    "token_py_100_200",
    "metric_available",
    "snapshot_status",
    "resolution_decision",
    "d01b_implementation_version",
    "d01b_resolution_status",
    "d01b_recovery_methods",
    "d01b_explicit_exclusion_reason",
    "d01b_manual_review_reference",
}

EXCLUSION_REQUIRED_COLUMNS = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "recovery_method",
    "root_cause",
    "resolution_status",
    "resolution_note",
    "manual_review_reference",
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

SNAPSHOT_METRIC_COLUMNS = [
    "function_count_py_all",
    "function_count_py_extracted",
    "function_count_py_100_200",
    "function_count_py_docstring_only",
    "function_count_py_with_nested",
    "python_file_count_with_function",
    "python_file_count_with_function_100_200",
    "token_py_all_function_bodies",
    "token_py_100_200",
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
    "ncloc",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Join run-x-d01b-v2 token metrics to the final Model A "
            "repository-month panel and create the run-x-d02 analysis input."
        )
    )
    parser.add_argument("--base-panel-file", required=True, type=Path)
    parser.add_argument("--snapshot-manifest-file", required=True, type=Path)
    parser.add_argument("--resolved-snapshot-results-file", required=True, type=Path)
    parser.add_argument("--explicit-exclusions-file", required=True, type=Path)
    parser.add_argument("--all-rows-panel-output", required=True, type=Path)
    parser.add_argument("--usable-panel-output", required=True, type=Path)
    parser.add_argument("--snapshot-audit-output", required=True, type=Path)
    parser.add_argument("--repo-month-exclusions-output", required=True, type=Path)
    parser.add_argument("--unresolved-output", required=True, type=Path)
    parser.add_argument("--treatment-estimability-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-input-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-input-snapshots", type=int, default=1496)
    parser.add_argument("--expected-input-treatment-panel-rows", type=int, default=914)
    parser.add_argument("--expected-input-control-panel-rows", type=int, default=1040)
    parser.add_argument("--expected-input-treatment-snapshots", type=int, default=790)
    parser.add_argument("--expected-input-control-snapshots", type=int, default=706)
    parser.add_argument("--expected-output-panel-rows", type=int, default=1953)
    parser.add_argument("--expected-output-snapshots", type=int, default=1495)
    parser.add_argument("--expected-output-treatment-panel-rows", type=int, default=913)
    parser.add_argument("--expected-output-control-panel-rows", type=int, default=1040)
    parser.add_argument("--expected-output-treatment-snapshots", type=int, default=789)
    parser.add_argument("--expected-output-control-snapshots", type=int, default=706)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-explicit-excluded-snapshots", type=int, default=1)
    parser.add_argument("--expected-explicit-excluded-panel-rows", type=int, default=1)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    """Configure timestamped logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def clean_text(value: object) -> str:
    """Return trimmed text while treating missing values as empty."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Fail when an input is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    """Read CSV identity columns as strings and preserve other inferred types."""
    input_path = path.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Required input file not found: {input_path}")
    header = pd.read_csv(input_path, nrows=0)
    dtype = {
        column: "string"
        for column in string_columns
        if column in header.columns
    }
    return pd.read_csv(input_path, dtype=dtype, low_memory=False)


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(temporary, index=False)
    temporary.replace(target)
    logging.info("Wrote %d rows to %s", len(df), target)


def identity_key(
    dataset_source: pd.Series,
    repo_name: pd.Series,
    commit_sha: pd.Series,
) -> pd.Series:
    """Create a normalized snapshot identity used only for validated joins."""
    return (
        dataset_source.map(clean_text).str.casefold()
        + "|"
        + repo_name.map(clean_text).str.casefold()
        + "|"
        + commit_sha.map(clean_text).str.casefold()
    )


def parse_boolean_series(series: pd.Series, label: str) -> pd.Series:
    """Parse common CSV boolean representations into non-nullable booleans."""
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    normalized = series.map(clean_text).str.casefold()
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    invalid = normalized.ne("") & ~normalized.isin(mapping)
    if invalid.any():
        sample = sorted(normalized.loc[invalid].unique().tolist())[:20]
        raise ValueError(f"{label} contains invalid Boolean values: {sample}")
    return normalized.map(mapping).fillna(False).astype(bool)


def validate_unique_identity(df: pd.DataFrame, label: str) -> None:
    """Require one row per normalized snapshot identity."""
    duplicated = df["_snapshot_identity"].duplicated(keep=False)
    if duplicated.any():
        columns = [
            column
            for column in [
                "dataset_source",
                "repo_name",
                "_commit_sha",
                "snapshot_key",
                "_snapshot_identity",
            ]
            if column in df.columns
        ]
        sample = df.loc[duplicated, columns].head(20)
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

    for column in ["repo_id", "time_index", "treatment_group", "model_a_complete"]:
        panel[column] = pd.to_numeric(panel[column], errors="raise").astype(int)

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
    panel["_commit_sha"] = panel["latest_commit_effective"]
    panel["_snapshot_identity"] = identity_key(
        panel["dataset_source"], panel["repo_name"], panel["_commit_sha"]
    )
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
    data["repo_month_rows"] = pd.to_numeric(
        data["repo_month_rows"], errors="raise"
    ).astype(int)
    if data["repo_month_rows"].le(0).any():
        raise ValueError("Snapshot manifest contains non-positive repo_month_rows")
    return data


def normalize_resolved_results(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the final run-x-d01b-v2 snapshot results."""
    require_columns(raw, RESOLVED_RESULT_REQUIRED_COLUMNS, "resolved snapshot results")
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
    validate_unique_identity(data, "resolved snapshot results")

    for column in ["manifest_order", "repo_month_rows", *SNAPSHOT_METRIC_COLUMNS]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["metric_available"] = parse_boolean_series(
        data["metric_available"], "metric_available"
    )
    data["snapshot_status"] = data["snapshot_status"].map(clean_text)
    data["resolution_decision"] = data["resolution_decision"].map(clean_text)
    data["d01b_resolution_status"] = data["d01b_resolution_status"].map(clean_text)
    data["d01b_recovery_methods"] = data["d01b_recovery_methods"].map(clean_text)
    data["token_definition"] = data["token_definition"].map(clean_text)

    available = data["metric_available"]
    if data.loc[available, PRIMARY_RAW_METRIC].isna().any():
        raise ValueError("Available snapshot results contain missing primary metrics")
    if (data.loc[available, PRIMARY_RAW_METRIC] < 0).any():
        raise ValueError("Available snapshot results contain negative primary metrics")
    if data.loc[~available, PRIMARY_RAW_METRIC].notna().any():
        sample = data.loc[
            ~available & data[PRIMARY_RAW_METRIC].notna(),
            ["snapshot_key", PRIMARY_RAW_METRIC, "snapshot_status"],
        ].head(20)
        raise ValueError(
            "Unavailable snapshots contain final primary metrics: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def normalize_exclusions(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the explicit D01b manual-review exclusions."""
    require_columns(raw, EXCLUSION_REQUIRED_COLUMNS, "explicit exclusions")
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].map(clean_text).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["commit_sha"] = data["commit_sha"].map(clean_text).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean_text)
    data["_commit_sha"] = data["commit_sha"]
    data["_snapshot_identity"] = identity_key(
        data["dataset_source"], data["repo_name"], data["commit_sha"]
    )
    validate_unique_identity(data, "explicit exclusions")
    return data


def build_snapshot_audit(
    panel: pd.DataFrame,
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> pd.DataFrame:
    """Create one audited row for every Model C snapshot."""
    panel_counts = (
        panel.groupby("_snapshot_identity", as_index=False)
        .agg(
            panel_repo_month_rows=("time", "size"),
            panel_first_month=("time", "min"),
            panel_last_month=("time", "max"),
        )
    )

    manifest_columns = [
        "_snapshot_identity",
        "dataset_source",
        "repo_name",
        "repo_key",
        "latest_commit_effective",
        "repo_month_rows",
        "first_panel_month",
        "last_panel_month",
    ]
    audit = manifest[manifest_columns].rename(
        columns={
            "latest_commit_effective": "commit_sha",
            "repo_month_rows": "repo_month_rows_manifest",
        }
    )

    result_columns = [
        "_snapshot_identity",
        "manifest_order",
        "snapshot_key",
        "repo_month_rows",
        "token_definition",
        "token_min_inclusive",
        "token_max_inclusive",
        *SNAPSHOT_METRIC_COLUMNS,
        "metric_available",
        "snapshot_status",
        "resolution_decision",
        "d01b_implementation_version",
        "d01b_resolution_status",
        "d01b_recovery_methods",
        "d01b_explicit_exclusion_reason",
        "d01b_manual_review_reference",
        "d01b_resolution_note",
    ]
    result_columns = [column for column in result_columns if column in results.columns]
    result_selected = results[result_columns].rename(
        columns={"repo_month_rows": "repo_month_rows_result"}
    )

    exclusion_columns = [
        "_snapshot_identity",
        "path",
        "blob_oid",
        "recovery_method",
        "root_cause",
        "resolution_status",
        "resolution_note",
        "manual_review_reference",
    ]
    exclusion_selected = exclusions[exclusion_columns].rename(
        columns={
            "path": "excluded_path",
            "blob_oid": "excluded_blob_oid",
            "recovery_method": "exclusion_recovery_method",
            "root_cause": "exclusion_root_cause",
            "resolution_status": "exclusion_resolution_status",
            "resolution_note": "exclusion_resolution_note",
            "manual_review_reference": "exclusion_manual_review_reference",
        }
    )

    audit = audit.merge(panel_counts, on="_snapshot_identity", how="left", validate="one_to_one")
    audit = audit.merge(result_selected, on="_snapshot_identity", how="left", validate="one_to_one")
    audit = audit.merge(exclusion_selected, on="_snapshot_identity", how="left", validate="one_to_one")

    audit["explicitly_excluded"] = audit["exclusion_resolution_status"].fillna("").eq(
        "excluded_after_manual_review"
    )
    audit["metric_available"] = audit["metric_available"].fillna(False).astype(bool)
    audit["unclassified_unresolved"] = ~audit["metric_available"] & ~audit[
        "explicitly_excluded"
    ]
    audit["repo_month_rows_panel_match_manifest"] = audit[
        "panel_repo_month_rows"
    ].eq(audit["repo_month_rows_manifest"])
    audit["repo_month_rows_result_match_manifest"] = audit[
        "repo_month_rows_result"
    ].eq(audit["repo_month_rows_manifest"])
    audit["panel_month_range_matches_manifest"] = (
        audit["panel_first_month"].astype("string").eq(
            audit["first_panel_month"].astype("string")
        )
        & audit["panel_last_month"].astype("string").eq(
            audit["last_panel_month"].astype("string")
        )
    )
    audit["token_metric_source"] = np.where(
        audit["metric_available"],
        "run-x-d01b-v2-resolved-snapshot",
        "",
    )

    preferred = [
        "manifest_order",
        "snapshot_key",
        "dataset_source",
        "repo_name",
        "repo_key",
        "commit_sha",
        "repo_month_rows_manifest",
        "repo_month_rows_result",
        "panel_repo_month_rows",
        "first_panel_month",
        "last_panel_month",
        "panel_first_month",
        "panel_last_month",
        "repo_month_rows_panel_match_manifest",
        "repo_month_rows_result_match_manifest",
        "panel_month_range_matches_manifest",
        "metric_available",
        "explicitly_excluded",
        "unclassified_unresolved",
        PRIMARY_RAW_METRIC,
        "function_count_py_100_200",
        "function_count_py_extracted",
        "token_py_all_function_bodies",
        "snapshot_status",
        "resolution_decision",
        "d01b_resolution_status",
        "d01b_recovery_methods",
        "token_metric_source",
        "exclusion_recovery_method",
        "exclusion_root_cause",
        "exclusion_resolution_status",
        "excluded_path",
        "excluded_blob_oid",
        "exclusion_resolution_note",
        "exclusion_manual_review_reference",
        "_snapshot_identity",
    ]
    remaining = [column for column in audit.columns if column not in preferred]
    return audit[preferred + remaining].sort_values(
        ["manifest_order", "dataset_source", "repo_name"], kind="stable"
    ).reset_index(drop=True)


def safe_log1p(series: pd.Series, label: str) -> pd.Series:
    """Compute log1p after rejecting negative non-missing values."""
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = numeric.notna() & numeric.lt(0)
    if invalid.any():
        raise ValueError(f"Cannot apply log1p to negative values in {label}")
    return np.log1p(numeric)


def safe_share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Compute a share with missing values for zero denominators."""
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    return num / den


def build_panels(
    panel: pd.DataFrame,
    snapshot_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Join snapshot measurements and create all-row, usable, exclusion, and unresolved panels."""
    merge_columns = [
        "_snapshot_identity",
        "snapshot_key",
        *SNAPSHOT_METRIC_COLUMNS,
        "metric_available",
        "snapshot_status",
        "resolution_decision",
        "d01b_implementation_version",
        "d01b_resolution_status",
        "d01b_recovery_methods",
        "token_metric_source",
        "explicitly_excluded",
        "unclassified_unresolved",
        "exclusion_recovery_method",
        "exclusion_root_cause",
        "exclusion_resolution_status",
        "excluded_path",
        "excluded_blob_oid",
        "exclusion_resolution_note",
        "exclusion_manual_review_reference",
    ]
    merge_columns = [column for column in merge_columns if column in snapshot_audit.columns]
    all_rows = panel.merge(
        snapshot_audit[merge_columns],
        on="_snapshot_identity",
        how="left",
        validate="many_to_one",
    )

    all_rows["token_py_snapshot_key"] = all_rows["snapshot_key"]
    all_rows["token_py_100_200_available"] = all_rows["metric_available"].fillna(False).astype(bool)
    all_rows["token_py_100_200_source"] = all_rows["token_metric_source"].fillna("")
    all_rows["token_py_100_200_resolution_status"] = all_rows[
        "d01b_resolution_status"
    ].fillna("")
    all_rows["token_py_100_200_resolution_decision"] = all_rows[
        "resolution_decision"
    ].fillna("")
    all_rows["token_py_100_200_explicitly_excluded"] = all_rows[
        "explicitly_excluded"
    ].fillna(False).astype(bool)
    all_rows["token_py_100_200_unclassified_unresolved"] = all_rows[
        "unclassified_unresolved"
    ].fillna(True).astype(bool)

    all_rows[PRIMARY_LOG_METRIC] = safe_log1p(
        all_rows[PRIMARY_RAW_METRIC], PRIMARY_RAW_METRIC
    )
    all_rows["log_function_count_py_100_200"] = safe_log1p(
        all_rows["function_count_py_100_200"], "function_count_py_100_200"
    )
    all_rows["log_token_py_all_function_bodies"] = safe_log1p(
        all_rows["token_py_all_function_bodies"], "token_py_all_function_bodies"
    )
    all_rows["share_function_count_py_100_200"] = safe_share(
        all_rows["function_count_py_100_200"],
        all_rows["function_count_py_extracted"],
    )
    all_rows["share_token_py_100_200"] = safe_share(
        all_rows[PRIMARY_RAW_METRIC],
        all_rows["token_py_all_function_bodies"],
    )

    all_rows["model_d_token_complete"] = all_rows[
        "token_py_100_200_available"
    ].astype(int)
    all_rows["model_d_token_exclusion_reason"] = ""
    excluded_mask = all_rows["token_py_100_200_explicitly_excluded"]
    unresolved_mask = all_rows["token_py_100_200_unclassified_unresolved"]
    all_rows.loc[excluded_mask, "model_d_token_exclusion_reason"] = (
        "explicit_malformed_source_exclusion"
    )
    all_rows.loc[unresolved_mask, "model_d_token_exclusion_reason"] = (
        "unclassified_unresolved_snapshot"
    )

    all_rows = all_rows.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    usable = all_rows[all_rows["model_d_token_complete"].eq(1)].copy()
    excluded = all_rows[all_rows["model_d_token_complete"].eq(0)].copy()
    unresolved = excluded[
        excluded["token_py_100_200_unclassified_unresolved"]
    ].copy()
    return all_rows, usable.reset_index(drop=True), excluded.reset_index(drop=True), unresolved.reset_index(drop=True)


def build_treatment_estimability(usable: pd.DataFrame) -> pd.DataFrame:
    """Audit pre/post support after the explicit repo-month exclusion."""
    treatment = usable[usable["treatment_group"].eq(1)].copy()
    treatment["is_pre_treatment"] = (
        treatment["time_index"] < treatment["event_index"]
    ).astype(int)
    treatment["is_post_treatment"] = (
        treatment["time_index"] >= treatment["event_index"]
    ).astype(int)
    audit = (
        treatment.groupby(
            ["repo_id", "repo_name", "event", "event_index"], as_index=False
        )
        .agg(
            usable_rows=("time", "size"),
            pre_treatment_rows=("is_pre_treatment", "sum"),
            post_treatment_rows=("is_post_treatment", "sum"),
            first_usable_month=("time", "min"),
            last_usable_month=("time", "max"),
        )
        .sort_values("repo_name", kind="stable")
        .reset_index(drop=True)
    )
    audit["borusyak_estimable_after_d02"] = (
        audit["pre_treatment_rows"].gt(0)
        & audit["post_treatment_rows"].gt(0)
    )
    audit["estimability_reason"] = "estimable"
    audit.loc[
        audit["pre_treatment_rows"].eq(0), "estimability_reason"
    ] = "no_pre_treatment_row_after_d02"
    audit.loc[
        audit["post_treatment_rows"].eq(0), "estimability_reason"
    ] = "no_post_treatment_row_after_d02"
    return audit


def count_role_rows(df: pd.DataFrame, role: str) -> int:
    """Count repository-month rows for a dataset role."""
    return int(df["dataset_source"].eq(role).sum())


def count_role_snapshots(df: pd.DataFrame, role: str) -> int:
    """Count unique snapshots for a dataset role."""
    return int(
        df.loc[df["dataset_source"].eq(role), "_snapshot_identity"].nunique()
    )


def count_role_repositories(df: pd.DataFrame, role: str) -> int:
    """Count unique repositories for a dataset role."""
    return int(df.loc[df["dataset_source"].eq(role), "repo_name"].nunique())


def numeric_equal(left: pd.Series, right: pd.Series) -> pd.Series:
    """Compare numeric values exactly while treating paired missing values as equal."""
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    return pd.Series(
        np.isclose(left_numeric, right_numeric, rtol=0.0, atol=0.0, equal_nan=True),
        index=left.index,
    )


def preservation_mismatches(base: pd.DataFrame, all_rows: pd.DataFrame) -> int:
    """Count altered base-panel analysis rows after joining snapshot metrics."""
    base_sorted = base.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    candidate_sorted = all_rows.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    if len(base_sorted) != len(candidate_sorted):
        return abs(len(base_sorted) - len(candidate_sorted)) + min(len(base_sorted), len(candidate_sorted))
    mismatch = pd.Series(False, index=base_sorted.index)
    for column in PRESERVATION_COLUMNS:
        if pd.api.types.is_numeric_dtype(base_sorted[column]) or pd.api.types.is_numeric_dtype(candidate_sorted[column]):
            mismatch |= ~numeric_equal(base_sorted[column], candidate_sorted[column])
        else:
            mismatch |= base_sorted[column].map(clean_text).ne(candidate_sorted[column].map(clean_text))
    return int(mismatch.sum())


def build_qc_and_summary(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    exclusions_input: pd.DataFrame,
    snapshot_audit: pd.DataFrame,
    all_rows: pd.DataFrame,
    usable: pd.DataFrame,
    exclusions: pd.DataFrame,
    unresolved: pd.DataFrame,
    treatment_estimability: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build check-oriented QC and long-form summary outputs."""
    qc_records: list[dict[str, Any]] = []

    def add_check(
        name: str,
        observed: Any,
        expected: Any,
        *,
        severity: str = "fail",
        note: str = "",
    ) -> None:
        passed = observed == expected
        status = "pass" if passed else ("warn" if severity == "warn" else "fail")
        qc_records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    strict = bool(args.strict_expected_counts)

    def expected_or_observed(expected: int, observed: int) -> int:
        return expected if strict else observed

    panel_identity_set = set(panel["_snapshot_identity"])
    manifest_identity_set = set(manifest["_snapshot_identity"])
    result_identity_set = set(results["_snapshot_identity"])
    exclusion_identity_set = set(exclusions_input["_snapshot_identity"])
    unavailable_result_set = set(
        results.loc[~results["metric_available"], "_snapshot_identity"]
    )

    add_check("input_panel_rows", len(panel), expected_or_observed(args.expected_input_panel_rows, len(panel)))
    add_check("input_panel_unique_snapshots", panel["_snapshot_identity"].nunique(), expected_or_observed(args.expected_input_snapshots, panel["_snapshot_identity"].nunique()))
    add_check("input_treatment_panel_rows", count_role_rows(panel, "treatment"), expected_or_observed(args.expected_input_treatment_panel_rows, count_role_rows(panel, "treatment")))
    add_check("input_control_panel_rows", count_role_rows(panel, "control"), expected_or_observed(args.expected_input_control_panel_rows, count_role_rows(panel, "control")))
    add_check("input_treatment_snapshots", count_role_snapshots(panel, "treatment"), expected_or_observed(args.expected_input_treatment_snapshots, count_role_snapshots(panel, "treatment")))
    add_check("input_control_snapshots", count_role_snapshots(panel, "control"), expected_or_observed(args.expected_input_control_snapshots, count_role_snapshots(panel, "control")))
    add_check("input_repositories", panel["repo_name"].nunique(), expected_or_observed(args.expected_repositories, panel["repo_name"].nunique()))
    add_check("input_treatment_repositories", count_role_repositories(panel, "treatment"), expected_or_observed(args.expected_treatment_repositories, count_role_repositories(panel, "treatment")))
    add_check("input_control_repositories", count_role_repositories(panel, "control"), expected_or_observed(args.expected_control_repositories, count_role_repositories(panel, "control")))
    add_check("duplicate_input_repo_month_rows", int(panel.duplicated(["repo_id", "time_index"]).sum()), 0)
    add_check("model_c_snapshot_key_format_mismatches", int((~panel["model_c_snapshot_key_format_matches"]).sum()), 0)
    add_check("snapshot_manifest_rows", len(manifest), expected_or_observed(args.expected_input_snapshots, len(manifest)))
    add_check("resolved_snapshot_result_rows", len(results), expected_or_observed(args.expected_input_snapshots, len(results)))
    add_check("panel_vs_manifest_snapshot_set_mismatches", len(panel_identity_set.symmetric_difference(manifest_identity_set)), 0)
    add_check("manifest_vs_result_snapshot_set_mismatches", len(manifest_identity_set.symmetric_difference(result_identity_set)), 0)
    add_check("explicit_exclusion_snapshot_rows", len(exclusions_input), expected_or_observed(args.expected_explicit_excluded_snapshots, len(exclusions_input)))
    add_check("explicit_exclusion_matches_unavailable_result_set", len(exclusion_identity_set.symmetric_difference(unavailable_result_set)), 0)
    add_check("snapshot_panel_row_count_mismatches", int((~snapshot_audit["repo_month_rows_panel_match_manifest"].fillna(False)).sum()), 0)
    add_check("snapshot_result_row_count_mismatches", int((~snapshot_audit["repo_month_rows_result_match_manifest"].fillna(False)).sum()), 0)
    add_check("snapshot_panel_month_range_mismatches", int((~snapshot_audit["panel_month_range_matches_manifest"].fillna(False)).sum()), 0)
    add_check("available_snapshots", int(snapshot_audit["metric_available"].sum()), expected_or_observed(args.expected_output_snapshots, int(snapshot_audit["metric_available"].sum())))
    add_check("explicitly_excluded_snapshots", int(snapshot_audit["explicitly_excluded"].sum()), expected_or_observed(args.expected_explicit_excluded_snapshots, int(snapshot_audit["explicitly_excluded"].sum())))
    add_check("unclassified_unresolved_snapshots", int(snapshot_audit["unclassified_unresolved"].sum()), 0)
    add_check("all_rows_panel_rows", len(all_rows), expected_or_observed(args.expected_input_panel_rows, len(all_rows)))
    add_check("usable_panel_rows", len(usable), expected_or_observed(args.expected_output_panel_rows, len(usable)))
    add_check("explicitly_excluded_panel_rows", int(exclusions["token_py_100_200_explicitly_excluded"].sum()), expected_or_observed(args.expected_explicit_excluded_panel_rows, int(exclusions["token_py_100_200_explicitly_excluded"].sum())))
    add_check("unresolved_panel_rows", len(unresolved), 0)
    add_check("output_treatment_panel_rows", count_role_rows(usable, "treatment"), expected_or_observed(args.expected_output_treatment_panel_rows, count_role_rows(usable, "treatment")))
    add_check("output_control_panel_rows", count_role_rows(usable, "control"), expected_or_observed(args.expected_output_control_panel_rows, count_role_rows(usable, "control")))
    add_check("output_treatment_snapshots", count_role_snapshots(usable, "treatment"), expected_or_observed(args.expected_output_treatment_snapshots, count_role_snapshots(usable, "treatment")))
    add_check("output_control_snapshots", count_role_snapshots(usable, "control"), expected_or_observed(args.expected_output_control_snapshots, count_role_snapshots(usable, "control")))
    add_check("output_repositories", usable["repo_name"].nunique(), expected_or_observed(args.expected_repositories, usable["repo_name"].nunique()))
    add_check("output_treatment_repositories", count_role_repositories(usable, "treatment"), expected_or_observed(args.expected_treatment_repositories, count_role_repositories(usable, "treatment")))
    add_check("output_control_repositories", count_role_repositories(usable, "control"), expected_or_observed(args.expected_control_repositories, count_role_repositories(usable, "control")))
    add_check("duplicate_usable_repo_month_rows", int(usable.duplicated(["repo_id", "time_index"]).sum()), 0)
    add_check("missing_primary_metric_in_usable_panel", int(usable[PRIMARY_RAW_METRIC].isna().sum()), 0)
    add_check("negative_primary_metric_in_usable_panel", int((usable[PRIMARY_RAW_METRIC] < 0).sum()), 0)
    add_check("missing_log_metric_in_usable_panel", int(usable[PRIMARY_LOG_METRIC].isna().sum()), 0)
    add_check("base_panel_preservation_mismatches", preservation_mismatches(panel, all_rows), 0)
    add_check("non_estimable_treatment_repositories_after_d02", int((~treatment_estimability["borusyak_estimable_after_d02"]).sum()), 0)
    add_check("treatment_estimability_audit_repositories", len(treatment_estimability), expected_or_observed(args.expected_treatment_repositories, len(treatment_estimability)))

    qc = pd.DataFrame(qc_records)

    summary_records: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_records.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "experiment", EXPERIMENT_NAME)
    add_summary("definition", "primary_raw_metric", PRIMARY_RAW_METRIC)
    add_summary("definition", "primary_log_metric", PRIMARY_LOG_METRIC)
    add_summary("definition", "token_definition", TOKEN_DEFINITION)
    add_summary("definition", "log_transformation", "log1p")
    add_summary("definition", "snapshot_join_identity", "dataset_source|casefold(repo_name)|commit_sha")
    add_summary("definition", "explicit_exclusion_policy", "retain audit row; exclude from usable panel; do not impute")
    add_summary("input", "panel_rows", len(panel))
    add_summary("input", "snapshots", len(manifest))
    add_summary("input", "repositories", panel["repo_name"].nunique())
    add_summary("input", "treatment_panel_rows", count_role_rows(panel, "treatment"))
    add_summary("input", "control_panel_rows", count_role_rows(panel, "control"))
    add_summary("output", "all_rows_panel_rows", len(all_rows))
    add_summary("output", "usable_panel_rows", len(usable))
    add_summary("output", "usable_snapshots", usable["_snapshot_identity"].nunique())
    add_summary("output", "usable_repositories", usable["repo_name"].nunique())
    add_summary("output", "treatment_panel_rows", count_role_rows(usable, "treatment"))
    add_summary("output", "control_panel_rows", count_role_rows(usable, "control"))
    add_summary("output", "treatment_snapshots", count_role_snapshots(usable, "treatment"))
    add_summary("output", "control_snapshots", count_role_snapshots(usable, "control"))
    add_summary("output", "explicitly_excluded_snapshots", int(snapshot_audit["explicitly_excluded"].sum()))
    add_summary("output", "explicitly_excluded_panel_rows", len(exclusions))
    add_summary("output", "unclassified_unresolved_snapshots", int(snapshot_audit["unclassified_unresolved"].sum()))
    add_summary("output", "unresolved_panel_rows", len(unresolved))
    add_summary("estimability", "treatment_repositories", len(treatment_estimability))
    add_summary("estimability", "non_estimable_treatment_repositories", int((~treatment_estimability["borusyak_estimable_after_d02"]).sum()))

    available_snapshots = snapshot_audit[snapshot_audit["metric_available"]].copy()
    for label, frame in [("snapshot_metric", available_snapshots), ("panel_metric", usable)]:
        for metric in [
            PRIMARY_RAW_METRIC,
            PRIMARY_LOG_METRIC if PRIMARY_LOG_METRIC in frame.columns else "",
            "function_count_py_100_200",
            "share_function_count_py_100_200" if "share_function_count_py_100_200" in frame.columns else "",
        ]:
            if not metric or metric not in frame.columns:
                continue
            values = pd.to_numeric(frame[metric], errors="coerce").dropna()
            if values.empty:
                continue
            add_summary(label, f"{metric}_min", values.min())
            add_summary(label, f"{metric}_median", values.median())
            add_summary(label, f"{metric}_mean", values.mean())
            add_summary(label, f"{metric}_max", values.max())
            add_summary(label, f"{metric}_zero_count", int(values.eq(0).sum()))

    for role, group in usable.groupby("dataset_source", sort=True):
        values = pd.to_numeric(group[PRIMARY_RAW_METRIC], errors="coerce").dropna()
        add_summary("metric_by_role", f"{role}_rows", len(group))
        add_summary("metric_by_role", f"{role}_median_{PRIMARY_RAW_METRIC}", values.median())
        add_summary("metric_by_role", f"{role}_mean_{PRIMARY_RAW_METRIC}", values.mean())

    add_summary("qc", "hard_failures", int(qc["status"].eq("fail").sum()))
    add_summary("qc", "warnings", int(qc["status"].eq("warn").sum()))
    return qc, pd.DataFrame(summary_records)


def main() -> int:
    """Run the complete D02 panel-preparation workflow."""
    args = parse_args()
    configure_logging(args.log_level)

    try:
        logging.info("Reading base Model A panel: %s", args.base_panel_file)
        panel = normalize_base_panel(
            read_csv_stable(args.base_panel_file, KEY_STRING_COLUMNS)
        )
        logging.info("Reading snapshot manifest: %s", args.snapshot_manifest_file)
        manifest = normalize_snapshot_manifest(
            read_csv_stable(args.snapshot_manifest_file, KEY_STRING_COLUMNS)
        )
        logging.info(
            "Reading resolved D01b snapshot results: %s",
            args.resolved_snapshot_results_file,
        )
        results = normalize_resolved_results(
            read_csv_stable(args.resolved_snapshot_results_file, KEY_STRING_COLUMNS)
        )
        logging.info("Reading explicit exclusions: %s", args.explicit_exclusions_file)
        exclusions_input = normalize_exclusions(
            read_csv_stable(args.explicit_exclusions_file, KEY_STRING_COLUMNS)
        )

        snapshot_audit = build_snapshot_audit(
            panel, manifest, results, exclusions_input
        )
        all_rows, usable, exclusions, unresolved = build_panels(
            panel, snapshot_audit
        )
        treatment_estimability = build_treatment_estimability(usable)
        qc, summary = build_qc_and_summary(
            args,
            panel,
            manifest,
            results,
            exclusions_input,
            snapshot_audit,
            all_rows,
            usable,
            exclusions,
            unresolved,
            treatment_estimability,
        )

        save_dataframe(all_rows, args.all_rows_panel_output)
        save_dataframe(usable, args.usable_panel_output)
        save_dataframe(snapshot_audit, args.snapshot_audit_output)
        save_dataframe(exclusions, args.repo_month_exclusions_output)
        save_dataframe(unresolved, args.unresolved_output)
        save_dataframe(treatment_estimability, args.treatment_estimability_output)
        save_dataframe(qc, args.qc_output)
        save_dataframe(summary, args.summary_output)

        failures = int(qc["status"].eq("fail").sum())
        warnings = int(qc["status"].eq("warn").sum())
        logging.info(
            "Completed run-x-d02-v1: all_rows=%d; usable=%d; snapshots=%d; "
            "excluded=%d; unresolved=%d; QC failures=%d; warnings=%d",
            len(all_rows),
            len(usable),
            usable["_snapshot_identity"].nunique(),
            len(exclusions),
            len(unresolved),
            failures,
            warnings,
        )
        return 1 if failures else 0
    except Exception:
        logging.exception("run-x-d02 failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
