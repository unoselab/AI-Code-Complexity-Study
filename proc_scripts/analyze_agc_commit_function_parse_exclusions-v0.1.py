#!/usr/bin/env python3
"""Analyze audited Python parse exclusions from commit-function extraction.

Purpose
-------
This diagnostic separates expected historical source parse exclusions from
fatal pipeline failures after ``extract_agc_commit_function_events.py``.
It does not rerun Git extraction or AGC detection.

Primary interpretation
----------------------
- ``current_file_parse`` and ``parent_file_parse`` are audited source
  exclusions because an AST cannot be created for the historical file
  revision under the active Python parser.
- Any other error stage is treated as a fatal or regression signal.

Inputs
------
- Validated repository-month panel with treatment/event-time metadata.
- Commit-parent pair manifest from run-py-5a Stage 1.
- File-level extraction audit from run-py-5a Stage 2.
- Extraction error table from run-py-5a Stage 2.
- Extraction summary JSON from run-py-5a Stage 2.

Outputs
-------
Analysis tables:
- unique excluded historical Python blob revisions
- exclusion metrics by repository
- exclusion metrics by repository-month
- exclusion metrics by dataset source
- exclusion metrics by treatment period
- exclusion metrics by treatment event time
- error-stage and error-type distribution
- top-repository concentration sensitivity

QC artifacts:
- diagnostic summary JSON
- diagnostic checks CSV
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd


ALLOWED_PARSE_STAGES = {"current_file_parse", "parent_file_parse"}
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

PANEL_KEY = ["dataset_source", "repo_name", "time"]
PAIR_KEY = ["dataset_source", "repo_name", "month", "scan_current_commit"]
PAIR_AUDIT_KEY = ["dataset_source", "repo_name", "time", "commit"]
ERROR_AUDIT_JOIN_KEY = [
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "relative_path",
]
UNIQUE_BLOB_KEY = [
    "dataset_source",
    "repo_name",
    "blob_commit",
    "blob_relative_path",
]

PANEL_REQUIRED = {"dataset_source", "repo_name", "time"}
PAIR_REQUIRED = {
    "dataset_source",
    "repo_name",
    "month",
    "scan_current_commit",
    "primary_scan_eligible",
}
AUDIT_REQUIRED = {
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "diff_status",
    "relative_path",
    "parent_relative_path",
    "file_status",
}
ERROR_REQUIRED = {
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "relative_path",
    "stage",
    "error",
}

CURRENT_FAILURE_STAGES = {
    "current_blob_read",
    "current_file_decode",
    "current_file_parse",
    "current_function_extraction",
}

COUNT_COLUMNS = [
    "input_commit_pairs",
    "eligible_commit_pairs",
    "python_file_change_audits",
    "current_blob_attempts",
    "parent_blob_attempts",
    "blob_parse_attempts",
    "unique_blob_revisions_attempted",
    "parse_exclusion_records",
    "current_file_parse_exclusions",
    "parent_file_parse_exclusions",
    "unique_excluded_blob_revisions",
    "commit_pairs_with_parse_exclusions",
]


@dataclass(frozen=True)
class AnalysisPaths:
    input_panel: Path
    input_commit_pairs: Path
    input_audit: Path
    input_errors: Path
    input_extract_summary: Path
    output_dir: Path
    qc_dir: Path


@dataclass
class AnalysisResult:
    summary: dict[str, Any]
    checks: pd.DataFrame
    unique_exclusions: pd.DataFrame
    by_repo: pd.DataFrame
    by_repo_month: pd.DataFrame
    by_dataset_source: pd.DataFrame
    by_treatment_period: pd.DataFrame
    by_event_time: pd.DataFrame
    by_error_type: pd.DataFrame
    top_repo_sensitivity: pd.DataFrame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze historical Python parse exclusions from AGC "
            "commit-function event extraction."
        )
    )
    parser.add_argument(
        "--input-panel",
        default=(
            "repo_python/run-py-4a/strict/"
            "panel_event_monthly_agc_changed_block_py.csv"
        ),
        help="Validated repository-month panel with treatment metadata.",
    )
    parser.add_argument(
        "--input-commit-pairs",
        default="repo_python/run-py-5a/strict/commit_parent_pairs.csv",
        help="Commit-parent pair manifest from run-py-5a Stage 1.",
    )
    parser.add_argument(
        "--input-audit",
        default=(
            "repo_python/run-py-5a/strict/"
            "commit_function_event_extraction_audit.csv"
        ),
        help="File-level extraction audit from run-py-5a Stage 2.",
    )
    parser.add_argument(
        "--input-errors",
        default=(
            "repo_python/tmp/run-py-5a/strict/"
            "agc_commit_function_event_extract_errors.csv"
        ),
        help="Extraction error records from run-py-5a Stage 2.",
    )
    parser.add_argument(
        "--input-extract-summary",
        default=(
            "repo_python/tmp/run-py-5a/strict/"
            "agc_commit_function_event_extract_summary.json"
        ),
        help="Extraction summary JSON from run-py-5a Stage 2.",
    )
    parser.add_argument(
        "--output-dir",
        default="repo_python/run-py-5b/strict",
        help="Directory for parse-exclusion analysis tables.",
    )
    parser.add_argument(
        "--qc-dir",
        default="repo_python/tmp/run-py-5b/strict",
        help="Directory for summary and QC checks.",
    )
    parser.add_argument(
        "--top-repo-cutoffs",
        default="1,3,5,10,20",
        help="Comma-separated repository cutoffs for concentration sensitivity.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a synthetic regression test and exit.",
    )
    return parser.parse_args()


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def numeric_flag(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator_num = pd.to_numeric(numerator, errors="coerce")
    denominator_num = pd.to_numeric(denominator, errors="coerce")
    result = numerator_num / denominator_num.where(denominator_num.ne(0))
    return result.astype(float)


def scalar_rate(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def parse_cutoffs(text: str) -> list[int]:
    values = {0}
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value < 0:
            raise ValueError("Top-repository cutoffs must be nonnegative")
        values.add(value)
    return sorted(values)


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    if "time" not in panel.columns and "month" in panel.columns:
        panel = panel.rename(columns={"month": "time"})
    require_columns(panel, PANEL_REQUIRED, "input panel")
    for column in PANEL_KEY:
        panel[column] = clean_text(panel[column])
    if panel[PANEL_KEY].eq("").any(axis=None):
        raise ValueError("Input panel contains blank repository-month keys")
    if panel.duplicated(PANEL_KEY).any():
        duplicates = int(panel.duplicated(PANEL_KEY).sum())
        raise ValueError(f"Input panel contains {duplicates} duplicate keys")

    if "is_treatment" not in panel.columns:
        panel["is_treatment"] = panel["dataset_source"].eq("treatment").astype(int)
    else:
        panel["is_treatment"] = numeric_flag(panel["is_treatment"])

    if "time_to_event" not in panel.columns:
        panel["time_to_event"] = pd.NA
    panel["time_to_event"] = pd.to_numeric(
        panel["time_to_event"], errors="coerce"
    )

    if "post_event" not in panel.columns:
        panel["post_event"] = (
            panel["is_treatment"].eq(1)
            & panel["time_to_event"].ge(0)
        ).astype(int)
    else:
        panel["post_event"] = numeric_flag(panel["post_event"])

    if "event" not in panel.columns:
        panel["event"] = ""
    else:
        panel["event"] = clean_text(panel["event"])

    return panel


def normalize_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    pairs = pairs.copy()
    require_columns(pairs, PAIR_REQUIRED, "commit-pair manifest")
    text_columns = [
        "dataset_source",
        "repo_name",
        "month",
        "scan_current_commit",
    ]
    for column in text_columns:
        pairs[column] = clean_text(pairs[column])
    pairs["primary_scan_eligible"] = numeric_flag(pairs["primary_scan_eligible"])
    if pairs.duplicated(PAIR_KEY).any():
        duplicates = int(pairs.duplicated(PAIR_KEY).sum())
        raise ValueError(f"Commit-pair manifest contains {duplicates} duplicate pair keys")
    return pairs


def normalize_audit(audit: pd.DataFrame) -> pd.DataFrame:
    audit = audit.copy()
    require_columns(audit, AUDIT_REQUIRED, "extraction audit")
    for column in [
        "dataset_source",
        "repo_name",
        "time",
        "commit",
        "parent_commit",
        "diff_status",
        "relative_path",
        "parent_relative_path",
        "file_status",
    ]:
        audit[column] = clean_text(audit[column])
    return audit


def normalize_errors(errors: pd.DataFrame) -> pd.DataFrame:
    errors = errors.copy()
    require_columns(errors, ERROR_REQUIRED, "extraction errors")
    for column in [
        "dataset_source",
        "repo_name",
        "time",
        "commit",
        "parent_commit",
        "relative_path",
        "stage",
        "error",
    ]:
        errors[column] = clean_text(errors[column])
    errors["error_type"] = (
        errors["error"].str.split(":", n=1).str[0].replace("", "UnknownError")
    )
    return errors


def load_extract_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Extraction summary JSON must contain an object")
    return payload


def build_blob_attempts(audit: pd.DataFrame) -> pd.DataFrame:
    file_audit = audit.loc[audit["relative_path"].ne("")].copy()

    current = file_audit[
        [
            "dataset_source",
            "repo_name",
            "time",
            "commit",
            "parent_commit",
            "relative_path",
            "file_status",
        ]
    ].copy()
    current["blob_role"] = "current"
    current["blob_commit"] = current["commit"]
    current["blob_relative_path"] = current["relative_path"]

    parent_applicable = (
        file_audit["parent_relative_path"].ne("")
        & file_audit["parent_relative_path"].str.lower().str.endswith(".py")
        & file_audit["parent_commit"].ne("")
        & file_audit["parent_commit"].ne(EMPTY_TREE_SHA)
        & ~file_audit["diff_status"].str.startswith("A")
        & ~file_audit["file_status"].isin(CURRENT_FAILURE_STAGES)
    )
    parent = file_audit.loc[
        parent_applicable,
        [
            "dataset_source",
            "repo_name",
            "time",
            "commit",
            "parent_commit",
            "relative_path",
            "parent_relative_path",
            "file_status",
        ],
    ].copy()
    parent["blob_role"] = "parent"
    parent["blob_commit"] = parent["parent_commit"]
    parent["blob_relative_path"] = parent["parent_relative_path"]
    parent = parent.drop(columns=["parent_relative_path"])

    attempts = pd.concat([current, parent], ignore_index=True, sort=False)
    attempts["pair_key"] = (
        attempts["dataset_source"]
        + "|"
        + attempts["repo_name"]
        + "|"
        + attempts["time"]
        + "|"
        + attempts["commit"]
    )
    attempts["blob_revision_key"] = (
        attempts["dataset_source"]
        + "|"
        + attempts["repo_name"]
        + "|"
        + attempts["blob_commit"]
        + "|"
        + attempts["blob_relative_path"]
    )
    return attempts


def enrich_errors(
    errors: pd.DataFrame,
    audit: pd.DataFrame,
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    audit_lookup_columns = ERROR_AUDIT_JOIN_KEY + [
        "parent_relative_path",
        "diff_status",
        "file_status",
    ]
    audit_lookup = audit[audit_lookup_columns].copy()
    audit_lookup = audit_lookup.loc[
        audit_lookup["file_status"].isin(errors["stage"].unique())
    ]
    duplicate_lookup = int(audit_lookup.duplicated(ERROR_AUDIT_JOIN_KEY).sum())
    if duplicate_lookup:
        audit_lookup = audit_lookup.drop_duplicates(ERROR_AUDIT_JOIN_KEY, keep="first")

    enriched = errors.merge(
        audit_lookup,
        on=ERROR_AUDIT_JOIN_KEY,
        how="left",
        validate="many_to_one",
        indicator="_audit_merge",
    )
    unmatched = int(enriched["_audit_merge"].ne("both").sum())
    enriched = enriched.drop(columns=["_audit_merge"])
    enriched["parent_relative_path"] = clean_text(
        enriched.get("parent_relative_path", pd.Series(index=enriched.index, dtype=str))
    )
    enriched["diff_status"] = clean_text(
        enriched.get("diff_status", pd.Series(index=enriched.index, dtype=str))
    )
    enriched["file_status"] = clean_text(
        enriched.get("file_status", pd.Series(index=enriched.index, dtype=str))
    )

    enriched["blob_role"] = enriched["stage"].map(
        {"current_file_parse": "current", "parent_file_parse": "parent"}
    ).fillna("unexpected")
    enriched["blob_commit"] = enriched["commit"]
    parent_mask = enriched["stage"].eq("parent_file_parse")
    enriched.loc[parent_mask, "blob_commit"] = enriched.loc[
        parent_mask, "parent_commit"
    ]
    enriched["blob_relative_path"] = enriched["relative_path"]
    parent_path = enriched.loc[parent_mask, "parent_relative_path"]
    enriched.loc[parent_mask, "blob_relative_path"] = parent_path.where(
        parent_path.ne(""),
        enriched.loc[parent_mask, "relative_path"],
    )
    enriched["pair_key"] = (
        enriched["dataset_source"]
        + "|"
        + enriched["repo_name"]
        + "|"
        + enriched["time"]
        + "|"
        + enriched["commit"]
    )
    enriched["repo_month_key"] = (
        enriched["dataset_source"]
        + "|"
        + enriched["repo_name"]
        + "|"
        + enriched["time"]
    )
    enriched["blob_revision_key"] = (
        enriched["dataset_source"]
        + "|"
        + enriched["repo_name"]
        + "|"
        + enriched["blob_commit"]
        + "|"
        + enriched["blob_relative_path"]
    )

    metadata_columns = [
        column
        for column in [
            "dataset_source",
            "repo_name",
            "time",
            "is_treatment",
            "event",
            "post_event",
            "time_to_event",
            "high_confidence",
        ]
        if column in panel.columns
    ]
    enriched = enriched.merge(
        panel[metadata_columns],
        on=PANEL_KEY,
        how="left",
        validate="many_to_one",
    )
    return enriched, unmatched + duplicate_lookup


def unique_exclusion_table(enriched_errors: pd.DataFrame) -> pd.DataFrame:
    if enriched_errors.empty:
        columns = [
            *UNIQUE_BLOB_KEY,
            "blob_revision_key",
            "first_observed_time",
            "last_observed_time",
            "observed_roles",
            "error_record_count",
            "affected_commit_pairs",
            "affected_repository_months",
            "error_types",
            "error_messages",
            "is_treatment",
        ]
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for key, group in enriched_errors.groupby(UNIQUE_BLOB_KEY, dropna=False, sort=True):
        dataset_source, repo_name, blob_commit, blob_relative_path = key
        rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "blob_commit": blob_commit,
                "blob_relative_path": blob_relative_path,
                "blob_revision_key": str(group["blob_revision_key"].iloc[0]),
                "first_observed_time": str(group["time"].min()),
                "last_observed_time": str(group["time"].max()),
                "observed_roles": ";".join(sorted(set(group["blob_role"]))),
                "error_record_count": int(len(group)),
                "affected_commit_pairs": int(group["pair_key"].nunique()),
                "affected_repository_months": int(
                    group[["dataset_source", "repo_name", "time"]]
                    .drop_duplicates()
                    .shape[0]
                ),
                "error_types": ";".join(sorted(set(group["error_type"]))),
                "error_messages": " || ".join(sorted(set(group["error"]))),
                "is_treatment": int(
                    pd.to_numeric(group.get("is_treatment"), errors="coerce")
                    .fillna(0)
                    .max()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["dataset_source", "repo_name", "first_observed_time", "blob_relative_path"]
    ).reset_index(drop=True)


def aggregate_metrics(frame: pd.DataFrame, group_columns: Sequence[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_columns, *COUNT_COLUMNS])

    aggregations: dict[str, tuple[str, str]] = {
        column: (column, "sum")
        for column in COUNT_COLUMNS
        if column in frame.columns
    }
    aggregations.update(
        {
            "repository_months": ("time", "size"),
            "repository_months_with_parse_exclusions": (
                "has_parse_exclusion",
                "sum",
            ),
        }
    )
    result = frame.groupby(list(group_columns), dropna=False).agg(**aggregations).reset_index()
    result["repository_month_parse_exclusion_rate"] = safe_divide(
        result["repository_months_with_parse_exclusions"],
        result["repository_months"],
    )
    result["commit_pair_parse_exclusion_rate"] = safe_divide(
        result["commit_pairs_with_parse_exclusions"],
        result["eligible_commit_pairs"],
    )
    result["file_audit_parse_exclusion_rate"] = safe_divide(
        result["parse_exclusion_records"],
        result["python_file_change_audits"],
    )
    result["unique_blob_parse_exclusion_rate"] = safe_divide(
        result["unique_excluded_blob_revisions"],
        result["unique_blob_revisions_attempted"],
    )
    return result


def build_repo_month_table(
    panel: pd.DataFrame,
    pairs: pd.DataFrame,
    audit: pd.DataFrame,
    attempts: pd.DataFrame,
    enriched_errors: pd.DataFrame,
) -> pd.DataFrame:
    base_columns = [
        column
        for column in [
            "dataset_source",
            "repo_name",
            "time",
            "is_treatment",
            "event",
            "post_event",
            "time_to_event",
            "high_confidence",
        ]
        if column in panel.columns
    ]
    result = panel[base_columns].copy()

    pair_counts = (
        pairs.assign(time=pairs["month"])
        .groupby(PANEL_KEY, dropna=False)
        .agg(
            input_commit_pairs=("scan_current_commit", "size"),
            eligible_commit_pairs=("primary_scan_eligible", "sum"),
        )
        .reset_index()
    )

    file_audit = audit.loc[audit["relative_path"].ne("")].copy()
    audit_counts = (
        file_audit.groupby(PANEL_KEY, dropna=False)
        .agg(
            python_file_change_audits=("relative_path", "size"),
            audited_commit_pairs=("commit", "nunique"),
        )
        .reset_index()
    )

    attempt_counts = (
        attempts.groupby(PANEL_KEY, dropna=False)
        .agg(
            current_blob_attempts=(
                "blob_role",
                lambda values: int((values == "current").sum()),
            ),
            parent_blob_attempts=(
                "blob_role",
                lambda values: int((values == "parent").sum()),
            ),
            blob_parse_attempts=("blob_revision_key", "size"),
            unique_blob_revisions_attempted=("blob_revision_key", "nunique"),
        )
        .reset_index()
    )

    if enriched_errors.empty:
        error_counts = pd.DataFrame(columns=PANEL_KEY + [
            "parse_exclusion_records",
            "current_file_parse_exclusions",
            "parent_file_parse_exclusions",
            "unique_excluded_blob_revisions",
            "commit_pairs_with_parse_exclusions",
        ])
    else:
        error_counts = (
            enriched_errors.groupby(PANEL_KEY, dropna=False)
            .agg(
                parse_exclusion_records=("stage", "size"),
                current_file_parse_exclusions=(
                    "stage",
                    lambda values: int((values == "current_file_parse").sum()),
                ),
                parent_file_parse_exclusions=(
                    "stage",
                    lambda values: int((values == "parent_file_parse").sum()),
                ),
                unique_excluded_blob_revisions=("blob_revision_key", "nunique"),
                commit_pairs_with_parse_exclusions=("pair_key", "nunique"),
            )
            .reset_index()
        )

    for table in [pair_counts, audit_counts, attempt_counts, error_counts]:
        result = result.merge(table, on=PANEL_KEY, how="left", validate="one_to_one")

    numeric_columns = [
        "input_commit_pairs",
        "eligible_commit_pairs",
        "python_file_change_audits",
        "audited_commit_pairs",
        "current_blob_attempts",
        "parent_blob_attempts",
        "blob_parse_attempts",
        "unique_blob_revisions_attempted",
        "parse_exclusion_records",
        "current_file_parse_exclusions",
        "parent_file_parse_exclusions",
        "unique_excluded_blob_revisions",
        "commit_pairs_with_parse_exclusions",
    ]
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)

    result["has_parse_exclusion"] = result["parse_exclusion_records"].gt(0).astype(int)
    result["commit_pair_parse_exclusion_rate"] = safe_divide(
        result["commit_pairs_with_parse_exclusions"],
        result["eligible_commit_pairs"],
    )
    result["file_audit_parse_exclusion_rate"] = safe_divide(
        result["parse_exclusion_records"],
        result["python_file_change_audits"],
    )
    result["unique_blob_parse_exclusion_rate"] = safe_divide(
        result["unique_excluded_blob_revisions"],
        result["unique_blob_revisions_attempted"],
    )
    return result.sort_values(PANEL_KEY).reset_index(drop=True)


def build_by_repo(repo_month: pd.DataFrame) -> pd.DataFrame:
    by_repo = aggregate_metrics(repo_month, ["dataset_source", "repo_name"])
    if by_repo.empty:
        return by_repo

    metadata = (
        repo_month.groupby(["dataset_source", "repo_name"], dropna=False)
        .agg(
            is_treatment=("is_treatment", "max"),
            first_month=("time", "min"),
            last_month=("time", "max"),
            event_month=(
                "event",
                lambda values: next((str(value) for value in values if str(value)), ""),
            ),
        )
        .reset_index()
    )
    by_repo = by_repo.merge(
        metadata,
        on=["dataset_source", "repo_name"],
        how="left",
        validate="one_to_one",
    )
    total_errors = int(by_repo["parse_exclusion_records"].sum())
    by_repo["parse_exclusion_record_share"] = (
        by_repo["parse_exclusion_records"] / total_errors
        if total_errors
        else 0.0
    )
    by_repo["parse_exclusion_rank"] = (
        by_repo["parse_exclusion_records"]
        .rank(method="min", ascending=False)
        .astype(int)
    )
    return by_repo.sort_values(
        ["parse_exclusion_records", "repo_name"],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_by_treatment_period(repo_month: pd.DataFrame) -> pd.DataFrame:
    groups: list[tuple[str, pd.Series]] = [
        ("overall", pd.Series(True, index=repo_month.index)),
        ("control_all", repo_month["is_treatment"].eq(0)),
        ("treatment_all", repo_month["is_treatment"].eq(1)),
        (
            "treatment_pre_event",
            repo_month["is_treatment"].eq(1)
            & repo_month["time_to_event"].lt(0),
        ),
        (
            "treatment_event_month",
            repo_month["is_treatment"].eq(1)
            & repo_month["time_to_event"].eq(0),
        ),
        (
            "treatment_post_event",
            repo_month["is_treatment"].eq(1)
            & repo_month["time_to_event"].ge(0),
        ),
    ]
    rows: list[pd.DataFrame] = []
    for label, mask in groups:
        subset = repo_month.loc[mask].copy()
        if subset.empty:
            row = {"treatment_period": label}
            for column in COUNT_COLUMNS:
                row[column] = 0
            row["repository_months"] = 0
            row["repository_months_with_parse_exclusions"] = 0
            rows.append(pd.DataFrame([row]))
            continue
        subset["treatment_period"] = label
        rows.append(aggregate_metrics(subset, ["treatment_period"]))
    result = pd.concat(rows, ignore_index=True, sort=False)
    for column in COUNT_COLUMNS + [
        "repository_months",
        "repository_months_with_parse_exclusions",
    ]:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    for rate_column, numerator, denominator in [
        (
            "repository_month_parse_exclusion_rate",
            "repository_months_with_parse_exclusions",
            "repository_months",
        ),
        (
            "commit_pair_parse_exclusion_rate",
            "commit_pairs_with_parse_exclusions",
            "eligible_commit_pairs",
        ),
        (
            "file_audit_parse_exclusion_rate",
            "parse_exclusion_records",
            "python_file_change_audits",
        ),
        (
            "unique_blob_parse_exclusion_rate",
            "unique_excluded_blob_revisions",
            "unique_blob_revisions_attempted",
        ),
    ]:
        result[rate_column] = safe_divide(result[numerator], result[denominator])
    return result


def build_by_event_time(repo_month: pd.DataFrame) -> pd.DataFrame:
    subset = repo_month.loc[
        repo_month["is_treatment"].eq(1)
        & repo_month["time_to_event"].notna()
    ].copy()
    if subset.empty:
        return pd.DataFrame(columns=["time_to_event", *COUNT_COLUMNS])
    subset["time_to_event"] = pd.to_numeric(subset["time_to_event"], errors="coerce")
    result = aggregate_metrics(subset, ["time_to_event"])
    return result.sort_values("time_to_event").reset_index(drop=True)


def build_by_error_type(enriched_errors: pd.DataFrame) -> pd.DataFrame:
    if enriched_errors.empty:
        return pd.DataFrame(
            columns=[
                "dataset_source",
                "stage",
                "error_type",
                "error_records",
                "unique_blob_revisions",
                "affected_commit_pairs",
                "affected_repositories",
                "affected_repository_months",
            ]
        )
    return (
        enriched_errors.groupby(
            ["dataset_source", "stage", "error_type"],
            dropna=False,
        )
        .agg(
            error_records=("error", "size"),
            unique_blob_revisions=("blob_revision_key", "nunique"),
            affected_commit_pairs=("pair_key", "nunique"),
            affected_repositories=("repo_name", "nunique"),
            affected_repository_months=("repo_month_key", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["error_records", "dataset_source", "stage", "error_type"],
            ascending=[False, True, True, True],
        )
        .reset_index(drop=True)
    )


def build_top_repo_sensitivity(
    repo_month: pd.DataFrame,
    by_repo: pd.DataFrame,
    cutoffs: Sequence[int],
) -> pd.DataFrame:
    ranked_rows = by_repo.loc[
        by_repo["parse_exclusion_records"].gt(0),
        ["dataset_source", "repo_name"],
    ].copy()
    ranked_rows["repo_key"] = (
        ranked_rows["dataset_source"] + "|" + ranked_rows["repo_name"]
    )
    ranked = ranked_rows["repo_key"].tolist()
    repo_month = repo_month.copy()
    repo_month["repo_key"] = (
        repo_month["dataset_source"] + "|" + repo_month["repo_name"]
    )
    rows: list[pd.DataFrame] = []
    group_masks = {
        "overall": pd.Series(True, index=repo_month.index),
        "control": repo_month["is_treatment"].eq(0),
        "treatment": repo_month["is_treatment"].eq(1),
    }
    for cutoff in cutoffs:
        removed = set(ranked[:cutoff])
        for group_label, group_mask in group_masks.items():
            subset = repo_month.loc[
                group_mask & ~repo_month["repo_key"].isin(removed)
            ].copy()
            if subset.empty:
                continue
            subset["analysis_group"] = group_label
            aggregate = aggregate_metrics(subset, ["analysis_group"])
            aggregate.insert(0, "excluded_top_repositories", int(cutoff))
            aggregate.insert(
                1,
                "excluded_repository_names",
                ";".join(ranked[:cutoff]),
            )
            rows.append(aggregate)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True, sort=False)


def build_checks(
    panel: pd.DataFrame,
    pairs: pd.DataFrame,
    audit: pd.DataFrame,
    attempts: pd.DataFrame,
    errors: pd.DataFrame,
    enriched_errors: pd.DataFrame,
    unique_exclusions: pd.DataFrame,
    repo_month: pd.DataFrame,
    extract_summary: dict[str, Any],
    audit_join_problems: int,
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(section: str, check: str, passed: bool, value: Any) -> None:
        checks.append(
            {
                "section": section,
                "check": check,
                "passed": int(bool(passed)),
                "value": value,
            }
        )

    unexpected_stages = sorted(set(errors["stage"]) - ALLOWED_PARSE_STAGES)
    add(
        "classification",
        "unexpected_error_stages_zero",
        not unexpected_stages,
        ";".join(unexpected_stages),
    )
    add(
        "classification",
        "all_error_records_are_audited_parse_exclusions",
        len(errors) == int(errors["stage"].isin(ALLOWED_PARSE_STAGES).sum()),
        f"{int(errors['stage'].isin(ALLOWED_PARSE_STAGES).sum())}:{len(errors)}",
    )
    add(
        "joins",
        "error_records_match_audit_rows",
        audit_join_problems == 0,
        audit_join_problems,
    )

    attempted_keys = set(attempts["blob_revision_key"])
    excluded_keys = set(enriched_errors["blob_revision_key"])
    missing_attempts = excluded_keys - attempted_keys
    add(
        "joins",
        "excluded_blob_revisions_were_attempted",
        not missing_attempts,
        len(missing_attempts),
    )

    expected_repo_months = set(map(tuple, panel[PANEL_KEY].itertuples(index=False, name=None)))
    actual_repo_months = set(
        map(tuple, repo_month[PANEL_KEY].itertuples(index=False, name=None))
    )
    add(
        "repo_month",
        "all_panel_repository_months_preserved",
        expected_repo_months == actual_repo_months,
        (
            f"missing={len(expected_repo_months - actual_repo_months)};"
            f"unexpected={len(actual_repo_months - expected_repo_months)}"
        ),
    )

    pair_repo_months = set(
        map(
            tuple,
            pairs[["dataset_source", "repo_name", "month"]]
            .drop_duplicates()
            .itertuples(index=False, name=None),
        )
    )
    add(
        "repo_month",
        "commit_pair_repository_months_exist_in_panel",
        pair_repo_months.issubset(expected_repo_months),
        len(pair_repo_months - expected_repo_months),
    )

    expected_eligible = int(pairs["primary_scan_eligible"].eq(1).sum())
    observed_eligible = int(repo_month["eligible_commit_pairs"].sum())
    add(
        "arithmetic",
        "eligible_commit_pairs_match",
        expected_eligible == observed_eligible,
        f"{observed_eligible}:{expected_eligible}",
    )

    expected_file_audits = int(audit["relative_path"].ne("").sum())
    observed_file_audits = int(repo_month["python_file_change_audits"].sum())
    add(
        "arithmetic",
        "python_file_audits_match",
        expected_file_audits == observed_file_audits,
        f"{observed_file_audits}:{expected_file_audits}",
    )

    observed_errors = int(repo_month["parse_exclusion_records"].sum())
    add(
        "arithmetic",
        "parse_exclusion_records_match_input_errors",
        observed_errors == len(errors),
        f"{observed_errors}:{len(errors)}",
    )
    stage_total = int(
        repo_month["current_file_parse_exclusions"].sum()
        + repo_month["parent_file_parse_exclusions"].sum()
    )
    add(
        "arithmetic",
        "parse_stage_counts_match_total",
        stage_total == len(errors),
        f"{stage_total}:{len(errors)}",
    )

    unique_count = int(repo_month["unique_excluded_blob_revisions"].sum())
    expected_unique = int(len(unique_exclusions))
    add(
        "arithmetic",
        "repository_month_unique_blob_counts_match_unique_table",
        unique_count >= expected_unique,
        f"repo_month_sum={unique_count};global_unique={expected_unique}",
    )
    add(
        "uniqueness",
        "unique_exclusion_blob_keys_unique",
        not unique_exclusions.duplicated(UNIQUE_BLOB_KEY).any(),
        int(unique_exclusions.duplicated(UNIQUE_BLOB_KEY).sum()),
    )

    rate_columns = [
        "commit_pair_parse_exclusion_rate",
        "file_audit_parse_exclusion_rate",
        "unique_blob_parse_exclusion_rate",
    ]
    invalid_rate_count = 0
    for column in rate_columns:
        values = pd.to_numeric(repo_month[column], errors="coerce").dropna()
        invalid_rate_count += int((~values.between(0, 1)).sum())
    add(
        "rates",
        "all_repo_month_rates_bounded_zero_one",
        invalid_rate_count == 0,
        invalid_rate_count,
    )

    if extract_summary:
        summary_expected = {
            "commit_pairs_scanned": expected_eligible,
            "python_files_audited": expected_file_audits,
            "extraction_errors": len(errors),
            "repository_months": len(panel),
        }
        for field, expected in summary_expected.items():
            actual = int(extract_summary.get(field, -1))
            add(
                "source_summary",
                f"extract_summary_{field}_matches",
                actual == expected,
                f"{actual}:{expected}",
            )

    return pd.DataFrame(checks)


def overall_metrics(repo_month: pd.DataFrame) -> dict[str, int | float | None]:
    totals: dict[str, int | float | None] = {}
    for column in COUNT_COLUMNS:
        totals[column] = int(repo_month[column].sum())
    totals["repository_months"] = int(len(repo_month))
    totals["repository_months_with_parse_exclusions"] = int(
        repo_month["has_parse_exclusion"].sum()
    )
    totals["repository_month_parse_exclusion_rate"] = scalar_rate(
        int(totals["repository_months_with_parse_exclusions"]),
        int(totals["repository_months"]),
    )
    totals["commit_pair_parse_exclusion_rate"] = scalar_rate(
        int(totals["commit_pairs_with_parse_exclusions"]),
        int(totals["eligible_commit_pairs"]),
    )
    totals["file_audit_parse_exclusion_rate"] = scalar_rate(
        int(totals["parse_exclusion_records"]),
        int(totals["python_file_change_audits"]),
    )
    totals["unique_blob_parse_exclusion_rate"] = scalar_rate(
        int(totals["unique_excluded_blob_revisions"]),
        int(totals["unique_blob_revisions_attempted"]),
    )
    return totals


def row_to_metrics(frame: pd.DataFrame, label: str) -> dict[str, Any]:
    row = frame.loc[frame["treatment_period"].eq(label)]
    if row.empty:
        return {}
    value = row.iloc[0]
    fields = [
        *COUNT_COLUMNS,
        "repository_months",
        "repository_months_with_parse_exclusions",
        "repository_month_parse_exclusion_rate",
        "commit_pair_parse_exclusion_rate",
        "file_audit_parse_exclusion_rate",
        "unique_blob_parse_exclusion_rate",
    ]
    result: dict[str, Any] = {}
    for field in fields:
        item = value.get(field)
        if pd.isna(item):
            result[field] = None
        elif field.endswith("_rate"):
            result[field] = float(item)
        else:
            result[field] = int(item)
    return result


def build_summary(
    paths: AnalysisPaths,
    extract_summary: dict[str, Any],
    errors: pd.DataFrame,
    enriched_errors: pd.DataFrame,
    attempts: pd.DataFrame,
    unique_exclusions: pd.DataFrame,
    by_repo: pd.DataFrame,
    repo_month: pd.DataFrame,
    by_treatment_period: pd.DataFrame,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    checks_passed = int(checks["passed"].eq(1).sum())
    checks_failed = int(checks["passed"].ne(1).sum())
    unexpected_records = int((~errors["stage"].isin(ALLOWED_PARSE_STAGES)).sum())
    audited_exclusion_records = int(errors["stage"].isin(ALLOWED_PARSE_STAGES).sum())

    if checks_failed:
        diagnostic_status = "FAIL"
    elif audited_exclusion_records:
        diagnostic_status = "PASS_WITH_EXCLUSIONS"
    else:
        diagnostic_status = "PASS"

    top_repo_counts = (
        by_repo.loc[by_repo["parse_exclusion_records"].gt(0)]
        .head(20)[["repo_name", "parse_exclusion_records"]]
        .to_dict(orient="records")
    )
    top_shares: dict[str, float | None] = {}
    total_error_records = int(len(errors))
    for cutoff in [1, 3, 5, 10, 20]:
        top_count = int(by_repo.head(cutoff)["parse_exclusion_records"].sum())
        top_shares[f"top_{cutoff}_repository_share"] = scalar_rate(
            top_count,
            total_error_records,
        )

    return {
        "status": diagnostic_status,
        "recommended_extractor_status": (
            "FAIL"
            if unexpected_records
            else (
                "PASS_WITH_EXCLUSIONS"
                if audited_exclusion_records
                else "PASS"
            )
        ),
        "checks_total": int(len(checks)),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "allowed_parse_stages": sorted(ALLOWED_PARSE_STAGES),
        "fatal_or_unexpected_error_records": unexpected_records,
        "audited_parse_exclusion_records": audited_exclusion_records,
        "error_stage_counts": {
            str(key): int(value)
            for key, value in errors["stage"].value_counts(dropna=False).items()
        },
        "error_type_counts": {
            str(key): int(value)
            for key, value in errors["error_type"].value_counts(dropna=False).items()
        },
        "unique_excluded_blob_revisions": int(len(unique_exclusions)),
        "global_unique_blob_revisions_attempted": int(
            attempts["blob_revision_key"].nunique()
        ),
        "global_unique_blob_parse_exclusion_rate": scalar_rate(
            int(len(unique_exclusions)),
            int(attempts["blob_revision_key"].nunique()),
        ),
        "affected_repositories": int(
            enriched_errors[["dataset_source", "repo_name"]]
            .drop_duplicates()
            .shape[0]
        ),
        "affected_repository_months": int(
            enriched_errors[PANEL_KEY].drop_duplicates().shape[0]
        ),
        "affected_commit_pairs": int(enriched_errors["pair_key"].nunique()),
        "overall": overall_metrics(repo_month),
        "control": row_to_metrics(by_treatment_period, "control_all"),
        "treatment": row_to_metrics(by_treatment_period, "treatment_all"),
        "treatment_pre_event": row_to_metrics(
            by_treatment_period,
            "treatment_pre_event",
        ),
        "treatment_event_month": row_to_metrics(
            by_treatment_period,
            "treatment_event_month",
        ),
        "treatment_post_event": row_to_metrics(
            by_treatment_period,
            "treatment_post_event",
        ),
        "repository_concentration": top_shares,
        "top_repositories": top_repo_counts,
        "input_extractor_summary_status": extract_summary.get("status"),
        "input_extractor_python_version": extract_summary.get("python_version"),
        "interpretation": (
            "All observed extraction errors are historical current/parent "
            "Python file parse exclusions. No unexpected pipeline-error stage "
            "was observed. Rates are descriptive and must be interpreted with "
            "repository clustering and treatment/control denominators."
        ),
        "inputs": {
            "panel": str(paths.input_panel),
            "commit_pairs": str(paths.input_commit_pairs),
            "audit": str(paths.input_audit),
            "errors": str(paths.input_errors),
            "extract_summary": str(paths.input_extract_summary),
        },
        "outputs": {
            "unique_exclusions": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_unique.csv"
            ),
            "by_repo": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_repo.csv"
            ),
            "by_repo_month": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_repo_month.csv"
            ),
            "by_dataset_source": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_dataset_source.csv"
            ),
            "by_treatment_period": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_treatment_period.csv"
            ),
            "by_event_time": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_event_time.csv"
            ),
            "by_error_type": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_by_error_type.csv"
            ),
            "top_repo_sensitivity": str(
                paths.output_dir
                / "agc_commit_function_parse_exclusions_top_repo_sensitivity.csv"
            ),
            "checks": str(
                paths.qc_dir
                / "agc_commit_function_parse_exclusion_checks.csv"
            ),
            "summary": str(
                paths.qc_dir
                / "agc_commit_function_parse_exclusion_summary.json"
            ),
        },
    }


def analyze(paths: AnalysisPaths, cutoffs: Sequence[int]) -> AnalysisResult:
    panel = normalize_panel(pd.read_csv(paths.input_panel, low_memory=False))
    pairs = normalize_pairs(pd.read_csv(paths.input_commit_pairs, low_memory=False))
    audit = normalize_audit(pd.read_csv(paths.input_audit, low_memory=False))
    errors = normalize_errors(pd.read_csv(paths.input_errors, low_memory=False))
    extract_summary = load_extract_summary(paths.input_extract_summary)

    attempts = build_blob_attempts(audit)
    enriched_errors, audit_join_problems = enrich_errors(errors, audit, panel)
    unique_exclusions = unique_exclusion_table(enriched_errors)
    repo_month = build_repo_month_table(
        panel,
        pairs,
        audit,
        attempts,
        enriched_errors,
    )
    by_repo = build_by_repo(repo_month)
    by_dataset_source = aggregate_metrics(repo_month, ["dataset_source"])
    by_treatment_period = build_by_treatment_period(repo_month)
    by_event_time = build_by_event_time(repo_month)
    by_error_type = build_by_error_type(enriched_errors)
    top_repo_sensitivity = build_top_repo_sensitivity(
        repo_month,
        by_repo,
        cutoffs,
    )
    checks = build_checks(
        panel,
        pairs,
        audit,
        attempts,
        errors,
        enriched_errors,
        unique_exclusions,
        repo_month,
        extract_summary,
        audit_join_problems,
    )
    summary = build_summary(
        paths,
        extract_summary,
        errors,
        enriched_errors,
        attempts,
        unique_exclusions,
        by_repo,
        repo_month,
        by_treatment_period,
        checks,
    )
    return AnalysisResult(
        summary=summary,
        checks=checks,
        unique_exclusions=unique_exclusions,
        by_repo=by_repo,
        by_repo_month=repo_month,
        by_dataset_source=by_dataset_source,
        by_treatment_period=by_treatment_period,
        by_event_time=by_event_time,
        by_error_type=by_error_type,
        top_repo_sensitivity=top_repo_sensitivity,
    )


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
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temporary, path)


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
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def write_result(result: AnalysisResult, paths: AnalysisPaths) -> None:
    outputs = {
        paths.output_dir
        / "agc_commit_function_parse_exclusions_unique.csv": result.unique_exclusions,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_repo.csv": result.by_repo,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_repo_month.csv": result.by_repo_month,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_dataset_source.csv": result.by_dataset_source,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_treatment_period.csv": result.by_treatment_period,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_event_time.csv": result.by_event_time,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_by_error_type.csv": result.by_error_type,
        paths.output_dir
        / "agc_commit_function_parse_exclusions_top_repo_sensitivity.csv": result.top_repo_sensitivity,
        paths.qc_dir
        / "agc_commit_function_parse_exclusion_checks.csv": result.checks,
    }
    for path, frame in outputs.items():
        atomic_write_csv(frame, path)
    atomic_write_json(
        result.summary,
        paths.qc_dir / "agc_commit_function_parse_exclusion_summary.json",
    )


def synthetic_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-parse-exclusion-self-test-") as temp:
        root = Path(temp)
        panel = pd.DataFrame(
            [
                {
                    "dataset_source": "control",
                    "repo_name": "control/repo",
                    "time": "2025-01",
                    "is_treatment": 0,
                    "event": "",
                    "post_event": 0,
                    "time_to_event": pd.NA,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "time": "2025-01",
                    "is_treatment": 1,
                    "event": "2025-02",
                    "post_event": 0,
                    "time_to_event": -1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "time": "2025-02",
                    "is_treatment": 1,
                    "event": "2025-02",
                    "post_event": 1,
                    "time_to_event": 0,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "time": "2025-03",
                    "is_treatment": 1,
                    "event": "2025-02",
                    "post_event": 1,
                    "time_to_event": 1,
                },
            ]
        )
        pairs = pd.DataFrame(
            [
                {
                    "dataset_source": "control",
                    "repo_name": "control/repo",
                    "month": "2025-01",
                    "scan_current_commit": "c1",
                    "primary_scan_eligible": 1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "month": "2025-01",
                    "scan_current_commit": "t1",
                    "primary_scan_eligible": 1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "month": "2025-02",
                    "scan_current_commit": "t2",
                    "primary_scan_eligible": 1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "month": "2025-03",
                    "scan_current_commit": "t3",
                    "primary_scan_eligible": 1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "month": "2025-03",
                    "scan_current_commit": "merge1",
                    "primary_scan_eligible": 0,
                },
            ]
        )
        audit_rows = [
            {
                "dataset_source": "control",
                "repo_name": "control/repo",
                "time": "2025-01",
                "commit": "c1",
                "parent_commit": "c0",
                "diff_status": "M",
                "relative_path": "a.py",
                "parent_relative_path": "a.py",
                "file_status": "ok",
            },
            {
                "dataset_source": "treatment",
                "repo_name": "treatment/repo",
                "time": "2025-01",
                "commit": "t1",
                "parent_commit": "t0",
                "diff_status": "M",
                "relative_path": "a.py",
                "parent_relative_path": "a.py",
                "file_status": "ok",
            },
            {
                "dataset_source": "treatment",
                "repo_name": "treatment/repo",
                "time": "2025-02",
                "commit": "t2",
                "parent_commit": "t1",
                "diff_status": "M",
                "relative_path": "broken.py",
                "parent_relative_path": "broken.py",
                "file_status": "current_file_parse",
            },
            {
                "dataset_source": "treatment",
                "repo_name": "treatment/repo",
                "time": "2025-03",
                "commit": "t3",
                "parent_commit": "t2",
                "diff_status": "M",
                "relative_path": "broken.py",
                "parent_relative_path": "broken.py",
                "file_status": "parent_file_parse",
            },
        ]
        audit = pd.DataFrame(audit_rows)
        errors = pd.DataFrame(
            [
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "time": "2025-02",
                    "commit": "t2",
                    "parent_commit": "t1",
                    "relative_path": "broken.py",
                    "stage": "current_file_parse",
                    "error": "SyntaxError: invalid syntax (broken.py, line 1)",
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "treatment/repo",
                    "time": "2025-03",
                    "commit": "t3",
                    "parent_commit": "t2",
                    "relative_path": "broken.py",
                    "stage": "parent_file_parse",
                    "error": "SyntaxError: invalid syntax (broken.py, line 1)",
                },
            ]
        )
        summary = {
            "status": "FAIL",
            "commit_pairs_scanned": 4,
            "python_files_audited": 4,
            "extraction_errors": 2,
            "repository_months": 4,
            "python_version": "3.11.test",
        }

        panel_path = root / "panel.csv"
        pairs_path = root / "pairs.csv"
        audit_path = root / "audit.csv"
        errors_path = root / "errors.csv"
        extract_summary_path = root / "extract_summary.json"
        panel.to_csv(panel_path, index=False)
        pairs.to_csv(pairs_path, index=False)
        audit.to_csv(audit_path, index=False)
        errors.to_csv(errors_path, index=False)
        extract_summary_path.write_text(json.dumps(summary), encoding="utf-8")

        paths = AnalysisPaths(
            input_panel=panel_path,
            input_commit_pairs=pairs_path,
            input_audit=audit_path,
            input_errors=errors_path,
            input_extract_summary=extract_summary_path,
            output_dir=root / "output",
            qc_dir=root / "qc",
        )
        result = analyze(paths, [0, 1, 3])
        assert result.summary["status"] == "PASS_WITH_EXCLUSIONS"
        assert result.summary["recommended_extractor_status"] == "PASS_WITH_EXCLUSIONS"
        assert result.summary["audited_parse_exclusion_records"] == 2
        assert result.summary["unique_excluded_blob_revisions"] == 1
        assert result.summary["affected_commit_pairs"] == 2
        assert len(result.by_repo_month) == 4
        assert int(result.checks["passed"].min()) == 1
        assert int(result.by_repo_month["parse_exclusion_records"].sum()) == 2
        assert int(result.by_repo_month["eligible_commit_pairs"].sum()) == 4
        write_result(result, paths)
        expected_summary = paths.qc_dir / "agc_commit_function_parse_exclusion_summary.json"
        assert expected_summary.is_file()
        written = json.loads(expected_summary.read_text(encoding="utf-8"))
        assert written["status"] == "PASS_WITH_EXCLUSIONS"
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        synthetic_self_test()
        return 0

    paths = AnalysisPaths(
        input_panel=Path(args.input_panel).expanduser().resolve(),
        input_commit_pairs=Path(args.input_commit_pairs).expanduser().resolve(),
        input_audit=Path(args.input_audit).expanduser().resolve(),
        input_errors=Path(args.input_errors).expanduser().resolve(),
        input_extract_summary=Path(args.input_extract_summary).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
        qc_dir=Path(args.qc_dir).expanduser().resolve(),
    )
    for label, path in [
        ("input panel", paths.input_panel),
        ("commit-pair manifest", paths.input_commit_pairs),
        ("extraction audit", paths.input_audit),
        ("extraction errors", paths.input_errors),
        ("extraction summary", paths.input_extract_summary),
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    cutoffs = parse_cutoffs(args.top_repo_cutoffs)
    print("=" * 72)
    print("Analyze AGC commit-function parse exclusions")
    print(f"Input panel:          {paths.input_panel}")
    print(f"Commit pairs:         {paths.input_commit_pairs}")
    print(f"Extraction audit:     {paths.input_audit}")
    print(f"Extraction errors:    {paths.input_errors}")
    print(f"Extraction summary:   {paths.input_extract_summary}")
    print(f"Output directory:     {paths.output_dir}")
    print(f"QC directory:         {paths.qc_dir}")
    print(f"Top-repo cutoffs:     {','.join(map(str, cutoffs))}")
    print("=" * 72)

    result = analyze(paths, cutoffs)
    write_result(result, paths)

    overall = result.summary["overall"]
    print("=" * 72)
    print("AGC commit-function parse-exclusion diagnostic")
    print(f"Status:                         {result.summary['status']}")
    print(
        "Recommended extractor status:   "
        f"{result.summary['recommended_extractor_status']}"
    )
    print(
        "Checks passed:                  "
        f"{result.summary['checks_passed']}/{result.summary['checks_total']}"
    )
    print(
        "Audited parse exclusions:       "
        f"{result.summary['audited_parse_exclusion_records']}"
    )
    print(
        "Unexpected error records:       "
        f"{result.summary['fatal_or_unexpected_error_records']}"
    )
    print(
        "Unique excluded blob revisions: "
        f"{result.summary['unique_excluded_blob_revisions']}"
    )
    print(
        "Affected commit pairs:          "
        f"{result.summary['affected_commit_pairs']}"
    )
    print(
        "Affected repository-months:     "
        f"{result.summary['affected_repository_months']}"
    )
    print(
        "File-audit exclusion rate:      "
        f"{overall['file_audit_parse_exclusion_rate']:.6f}"
        if overall["file_audit_parse_exclusion_rate"] is not None
        else "File-audit exclusion rate:      NA"
    )
    print(
        "Commit-pair exclusion rate:     "
        f"{overall['commit_pair_parse_exclusion_rate']:.6f}"
        if overall["commit_pair_parse_exclusion_rate"] is not None
        else "Commit-pair exclusion rate:     NA"
    )
    print(
        "Summary:                        "
        f"{paths.qc_dir / 'agc_commit_function_parse_exclusion_summary.json'}"
    )
    print("=" * 72)

    return 0 if result.summary["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
