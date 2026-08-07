#!/usr/bin/env python3
"""
Build the Python-only SonarQube quality DiD panel (run-x-b06, v1).

This stage does not rescan source code and does not query SonarQube. It joins
snapshot-level Python-only issue stocks collected by run-x-b05 onto the exact
1,954-row monthly Python panel already validated by run-x-b02.

Primary quality construct:
- issue_total_py_sonarqube: unresolved static-analysis issue stock present in
  the historical Python-only source snapshot.
- log_issue_total_py_sonarqube: log1p transform of the issue stock. This is the
  closest Python-only analogue to the original paper's log-transformed static
  analysis warning outcome.

Density construct:
- issues_per_kloc_py_sonarqube: issue stock per 1,000 Python NCLOC.
- log_issues_per_kloc_py_sonarqube: log1p transform of the density.

The issue stock is not interpreted as the number of issues newly introduced in
that month. Each run-x-b01 SonarQube project represents one historical source
snapshot and run-x-b05 records the unresolved issues present in that snapshot.

The output preserves the run-x-b02 treatment timing, covariates, Python added
lines, and Python NCLOC so that run-x-b07 can compare adjusted and FE-only
quality specifications on exactly the same monthly sample used for Python
velocity analysis.
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v1"

BASE_REQUIRED = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "event_index",
    "post_event",
    "snapshot_key_sonarqube",
    "latest_commit_effective",
    "ncloc_py_sonarqube",
}

B05_REQUIRED = {
    "implementation_version",
    "dataset_source",
    "repo_name",
    "snapshot_key",
    "commit_sha",
    "repo_month_rows",
    "project_key",
    "manifest_project_version",
    "manifest_analysis_id",
    "scan_scope",
    "manifest_ncloc_py_sonarqube",
    "observed_ncloc_py_sonarqube",
    "ncloc_matches_manifest",
    "issue_total_py_sonarqube",
    "log_issue_total_py_sonarqube",
    "issues_per_kloc_py_sonarqube",
    "issue_type_code_smell",
    "issue_type_bug",
    "issue_type_vulnerability",
    "issue_type_other",
    "issue_severity_blocker",
    "issue_severity_critical",
    "issue_severity_major",
    "issue_severity_minor",
    "issue_severity_info",
    "issue_severity_other",
    "issue_with_maintainability_impact",
    "issue_with_reliability_impact",
    "issue_with_security_impact",
    "issue_component_python_file",
    "issue_component_project",
    "issue_component_non_python",
    "issue_component_unknown",
    "rule_distinct",
    "clean_code_attribute_distinct",
    "resolved_issue_total",
    "analysis_count",
    "manifest_analysis_found",
    "expected_project_version_found",
    "issue_rows_complete",
    "current_snapshot_recoverable",
    "duplicate_issue_keys_within_snapshot",
    "issue_rows",
    "issue_status_open",
}

QUALITY_COUNT_COLUMNS = [
    "issue_total_py_sonarqube",
    "issue_type_code_smell",
    "issue_type_bug",
    "issue_type_vulnerability",
    "issue_type_other",
    "issue_severity_blocker",
    "issue_severity_critical",
    "issue_severity_major",
    "issue_severity_minor",
    "issue_severity_info",
    "issue_severity_other",
    "issue_with_maintainability_impact",
    "issue_with_reliability_impact",
    "issue_with_security_impact",
]

TRANSFORM_SPECS = [
    ("issue_type_code_smell", "code_smell"),
    ("issue_type_bug", "bug"),
    ("issue_type_vulnerability", "vulnerability"),
    ("issue_with_maintainability_impact", "maintainability_impact"),
    ("issue_with_reliability_impact", "reliability_impact"),
    ("issue_with_security_impact", "security_impact"),
    ("issue_high_severity", "high_severity"),
]


def require_columns(frame: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    text = series.astype("string").str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y", "t"})


def close_numeric(a: pd.Series, b: pd.Series, tolerance: float = 1e-9) -> pd.Series:
    aa = pd.to_numeric(a, errors="coerce")
    bb = pd.to_numeric(b, errors="coerce")
    both_missing = aa.isna() & bb.isna()
    both_present = aa.notna() & bb.notna()
    result = pd.Series(False, index=a.index)
    result.loc[both_missing] = True
    result.loc[both_present] = (aa.loc[both_present] - bb.loc[both_present]).abs() <= tolerance
    return result


def add_quality_transforms(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    ncloc = pd.to_numeric(result["ncloc_py_sonarqube"], errors="coerce")
    total = pd.to_numeric(result["issue_total_py_sonarqube"], errors="coerce")

    result["log_issue_total_py_sonarqube_recomputed"] = np.log1p(total)
    result["log_issue_total_py_sonarqube_matches_b05"] = close_numeric(
        result["log_issue_total_py_sonarqube"],
        result["log_issue_total_py_sonarqube_recomputed"],
    )

    density = np.where(ncloc > 0, total * 1000.0 / ncloc, np.nan)
    result["issues_per_kloc_py_sonarqube_recomputed"] = density
    result["issues_per_kloc_py_sonarqube_matches_b05"] = close_numeric(
        result["issues_per_kloc_py_sonarqube"],
        result["issues_per_kloc_py_sonarqube_recomputed"],
    )
    result["log_issues_per_kloc_py_sonarqube"] = np.log1p(result["issues_per_kloc_py_sonarqube_recomputed"])

    result["issue_high_severity"] = (
        pd.to_numeric(result["issue_severity_blocker"], errors="coerce").fillna(0)
        + pd.to_numeric(result["issue_severity_critical"], errors="coerce").fillna(0)
    )

    for count_col, stem in TRANSFORM_SPECS:
        count = pd.to_numeric(result[count_col], errors="coerce")
        result[f"log_issue_{stem}_py_sonarqube"] = np.log1p(count)
        result[f"issue_{stem}_per_kloc_py_sonarqube"] = np.where(
            ncloc > 0,
            count * 1000.0 / ncloc,
            np.nan,
        )
        result[f"log_issue_{stem}_per_kloc_py_sonarqube"] = np.log1p(
            result[f"issue_{stem}_per_kloc_py_sonarqube"]
        )

    result["static_analysis_warnings_py_sonarqube"] = total
    result["log_static_analysis_warnings_py_sonarqube"] = np.log1p(total)
    result["static_analysis_warnings_per_kloc_py_sonarqube"] = result[
        "issues_per_kloc_py_sonarqube_recomputed"
    ]
    result["log_static_analysis_warnings_per_kloc_py_sonarqube"] = result[
        "log_issues_per_kloc_py_sonarqube"
    ]

    type_sum = sum(pd.to_numeric(result[c], errors="coerce").fillna(0) for c in [
        "issue_type_code_smell",
        "issue_type_bug",
        "issue_type_vulnerability",
        "issue_type_other",
    ])
    severity_sum = sum(pd.to_numeric(result[c], errors="coerce").fillna(0) for c in [
        "issue_severity_blocker",
        "issue_severity_critical",
        "issue_severity_major",
        "issue_severity_minor",
        "issue_severity_info",
        "issue_severity_other",
    ])
    component_sum = sum(pd.to_numeric(result[c], errors="coerce").fillna(0) for c in [
        "issue_component_python_file",
        "issue_component_project",
        "issue_component_non_python",
        "issue_component_unknown",
    ])
    result["quality_type_counts_match_total"] = close_numeric(pd.Series(type_sum), total)
    result["quality_severity_counts_match_total"] = close_numeric(pd.Series(severity_sum), total)
    result["quality_component_counts_match_total"] = close_numeric(pd.Series(component_sum), total)

    result["quality_did_complete"] = 1
    result["quality_scope"] = "python_only_sonar_inclusions"
    result["quality_count_semantics"] = "unresolved_issue_stock_at_historical_snapshot"
    result["quality_primary_outcome"] = "log_issue_total_py_sonarqube"
    result["quality_density_outcome"] = "log_issues_per_kloc_py_sonarqube"
    result["quality_metric_version"] = IMPLEMENTATION_VERSION
    return result


def prepare_b05_for_merge(b05: pd.DataFrame) -> pd.DataFrame:
    require_columns(b05, B05_REQUIRED, "run-x-b05 snapshot counts")
    if b05["snapshot_key"].duplicated().any():
        dup = b05.loc[b05["snapshot_key"].duplicated(keep=False), "snapshot_key"].head().tolist()
        raise ValueError(f"run-x-b05 contains duplicate snapshot keys, examples: {dup}")

    provenance_rename = {
        "implementation_version": "quality_collection_version",
        "repo_name": "quality_repo_name",
        "dataset_source": "quality_dataset_source",
        "commit_sha": "quality_snapshot_commit_sha",
        "repo_month_rows": "quality_expected_repo_month_rows",
        "project_key": "quality_project_key",
        "manifest_project_version": "quality_project_version",
        "manifest_analysis_id": "quality_analysis_id",
        "scan_scope": "quality_scan_scope",
        "manifest_ncloc_py_sonarqube": "quality_manifest_ncloc_py_sonarqube",
        "observed_ncloc_py_sonarqube": "quality_observed_ncloc_py_sonarqube",
        "ncloc_matches_manifest": "quality_ncloc_matches_b01_manifest",
        "analysis_count": "quality_analysis_count",
        "manifest_analysis_found": "quality_manifest_analysis_found",
        "expected_project_version_found": "quality_expected_project_version_found",
        "issue_rows_complete": "quality_issue_rows_complete",
        "current_snapshot_recoverable": "quality_snapshot_recoverable",
        "duplicate_issue_keys_within_snapshot": "quality_duplicate_issue_keys_within_snapshot",
        "issue_rows": "quality_issue_rows",
        "issue_status_open": "quality_issue_status_open",
        "resolved_issue_total": "quality_resolved_issue_total",
    }
    return b05.rename(columns=provenance_rename)


def build_panel(base: pd.DataFrame, b05_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    require_columns(base, BASE_REQUIRED, "run-x-b02 monthly panel")
    b05 = prepare_b05_for_merge(b05_raw)

    merge_columns = [
        "snapshot_key",
        "quality_collection_version",
        "quality_repo_name",
        "quality_dataset_source",
        "quality_snapshot_commit_sha",
        "quality_expected_repo_month_rows",
        "quality_project_key",
        "quality_project_version",
        "quality_analysis_id",
        "quality_scan_scope",
        "quality_manifest_ncloc_py_sonarqube",
        "quality_observed_ncloc_py_sonarqube",
        "quality_ncloc_matches_b01_manifest",
        "issue_total_py_sonarqube",
        "log_issue_total_py_sonarqube",
        "issues_per_kloc_py_sonarqube",
        "issue_type_code_smell",
        "issue_type_bug",
        "issue_type_vulnerability",
        "issue_type_other",
        "issue_severity_blocker",
        "issue_severity_critical",
        "issue_severity_major",
        "issue_severity_minor",
        "issue_severity_info",
        "issue_severity_other",
        "issue_with_maintainability_impact",
        "issue_with_reliability_impact",
        "issue_with_security_impact",
        "issue_component_python_file",
        "issue_component_project",
        "issue_component_non_python",
        "issue_component_unknown",
        "rule_distinct",
        "clean_code_attribute_distinct",
        "quality_resolved_issue_total",
        "quality_analysis_count",
        "quality_manifest_analysis_found",
        "quality_expected_project_version_found",
        "quality_issue_rows_complete",
        "quality_snapshot_recoverable",
        "quality_duplicate_issue_keys_within_snapshot",
        "quality_issue_rows",
        "quality_issue_status_open",
    ]

    panel = base.merge(
        b05[merge_columns],
        left_on="snapshot_key_sonarqube",
        right_on="snapshot_key",
        how="left",
        validate="many_to_one",
        indicator="quality_merge_status",
    )

    panel["quality_snapshot_matched"] = panel["quality_merge_status"].eq("both")
    panel["quality_repo_identity_match"] = panel["repo_name"].astype("string").eq(
        panel["quality_repo_name"].astype("string")
    )
    panel["quality_dataset_source_match"] = panel["dataset_source"].astype("string").eq(
        panel["quality_dataset_source"].astype("string")
    )
    panel["quality_commit_identity_match"] = panel["latest_commit_effective"].astype("string").str.lower().eq(
        panel["quality_snapshot_commit_sha"].astype("string").str.lower()
    )
    panel["quality_ncloc_match_panel"] = close_numeric(
        panel["ncloc_py_sonarqube"],
        panel["quality_observed_ncloc_py_sonarqube"],
    )

    panel = add_quality_transforms(panel)

    unresolved_mask = ~(
        panel["quality_snapshot_matched"]
        & panel["quality_repo_identity_match"]
        & panel["quality_dataset_source_match"]
        & panel["quality_commit_identity_match"]
        & panel["quality_ncloc_match_panel"]
        & panel["log_issue_total_py_sonarqube_matches_b05"]
        & panel["issues_per_kloc_py_sonarqube_matches_b05"]
        & panel["quality_type_counts_match_total"]
        & panel["quality_severity_counts_match_total"]
        & panel["quality_component_counts_match_total"]
    )
    unresolved_columns = [
        "repo_id",
        "repo_name",
        "dataset_source",
        "time",
        "snapshot_key_sonarqube",
        "snapshot_key",
        "quality_snapshot_matched",
        "quality_repo_identity_match",
        "quality_dataset_source_match",
        "quality_commit_identity_match",
        "quality_ncloc_match_panel",
        "log_issue_total_py_sonarqube_matches_b05",
        "issues_per_kloc_py_sonarqube_matches_b05",
        "quality_type_counts_match_total",
        "quality_severity_counts_match_total",
        "quality_component_counts_match_total",
    ]
    unresolved = panel.loc[unresolved_mask, unresolved_columns].copy()

    mapped_counts = (
        base.groupby("snapshot_key_sonarqube", dropna=False)
        .size()
        .rename("mapped_repo_month_rows")
        .reset_index()
    )
    audit = b05[[
        "snapshot_key",
        "quality_repo_name",
        "quality_dataset_source",
        "quality_snapshot_commit_sha",
        "quality_expected_repo_month_rows",
        "quality_observed_ncloc_py_sonarqube",
        "issue_total_py_sonarqube",
    ]].merge(
        mapped_counts,
        left_on="snapshot_key",
        right_on="snapshot_key_sonarqube",
        how="outer",
        validate="one_to_one",
    )
    audit["repo_month_reuse_count_match"] = (
        pd.to_numeric(audit["quality_expected_repo_month_rows"], errors="coerce")
        == pd.to_numeric(audit["mapped_repo_month_rows"], errors="coerce")
    )
    audit["snapshot_used_by_panel"] = audit["mapped_repo_month_rows"].notna()
    return panel, audit, unresolved


def build_distribution_summary(panel: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "issue_total_py_sonarqube",
        "log_issue_total_py_sonarqube",
        "issues_per_kloc_py_sonarqube_recomputed",
        "log_issues_per_kloc_py_sonarqube",
        "issue_type_code_smell",
        "issue_type_bug",
        "issue_type_vulnerability",
        "issue_with_maintainability_impact",
        "issue_with_reliability_impact",
        "issue_with_security_impact",
        "issue_high_severity",
    ]
    source = panel["dataset_source"].astype("string")
    post = pd.to_numeric(panel["post_event"], errors="coerce").fillna(0).astype(int)
    groups = {
        "all": pd.Series(True, index=panel.index),
        "control_all": source.eq("control"),
        "treatment_all": source.eq("treatment"),
        "treatment_pre": source.eq("treatment") & post.eq(0),
        "treatment_post": source.eq("treatment") & post.eq(1),
    }
    rows: list[dict[str, object]] = []
    for group_name, mask in groups.items():
        for metric in metrics:
            values = pd.to_numeric(panel.loc[mask, metric], errors="coerce").dropna()
            if values.empty:
                stats = {k: np.nan for k in ["min", "p25", "median", "mean", "p75", "p95", "p99", "max"]}
                zero_count = 0
            else:
                stats = {
                    "min": float(values.min()),
                    "p25": float(values.quantile(0.25)),
                    "median": float(values.median()),
                    "mean": float(values.mean()),
                    "p75": float(values.quantile(0.75)),
                    "p95": float(values.quantile(0.95)),
                    "p99": float(values.quantile(0.99)),
                    "max": float(values.max()),
                }
                zero_count = int((values == 0).sum())
            rows.append({
                "group": group_name,
                "metric": metric,
                "rows_in_group": int(mask.sum()),
                "nonmissing": int(values.shape[0]),
                "zero_count": zero_count,
                **stats,
            })
    return pd.DataFrame(rows)


def build_outcome_manifest() -> pd.DataFrame:
    rows = [
        {
            "outcome": "log_issue_total_py_sonarqube",
            "label": "Python SonarQube Static Analysis Warnings: Total Issue Stock",
            "role": "primary_original_style_burden",
            "scale": "log1p_count",
            "interpretation": "Unresolved Python-only issue stock present in each historical snapshot; closest analogue to the original paper's warning-count outcome.",
        },
        {
            "outcome": "log_issues_per_kloc_py_sonarqube",
            "label": "Python SonarQube Static Analysis Warnings per KLOC",
            "role": "primary_density_robustness",
            "scale": "log1p_issues_per_1000_python_ncloc",
            "interpretation": "Issue density normalized by Python-only SonarQube NCLOC; distinguishes burden growth from quality degradation per code unit.",
        },
        {
            "outcome": "log_issue_code_smell_py_sonarqube",
            "label": "Python SonarQube Code Smell Stock",
            "role": "type_robustness",
            "scale": "log1p_count",
            "interpretation": "Legacy SonarQube CODE_SMELL issue stock.",
        },
        {
            "outcome": "log_issue_bug_py_sonarqube",
            "label": "Python SonarQube Bug Stock",
            "role": "type_robustness",
            "scale": "log1p_count",
            "interpretation": "Legacy SonarQube BUG issue stock.",
        },
        {
            "outcome": "log_issue_vulnerability_py_sonarqube",
            "label": "Python SonarQube Vulnerability Stock",
            "role": "type_robustness",
            "scale": "log1p_count",
            "interpretation": "Legacy SonarQube VULNERABILITY issue stock.",
        },
        {
            "outcome": "log_issue_maintainability_impact_py_sonarqube",
            "label": "Python SonarQube Maintainability-Impact Issue Stock",
            "role": "software_quality_impact_robustness",
            "scale": "log1p_count",
            "interpretation": "Issues with a maintainability impact. Impact categories can overlap across an issue.",
        },
        {
            "outcome": "log_issue_reliability_impact_py_sonarqube",
            "label": "Python SonarQube Reliability-Impact Issue Stock",
            "role": "software_quality_impact_robustness",
            "scale": "log1p_count",
            "interpretation": "Issues with a reliability impact. Impact categories can overlap across an issue.",
        },
        {
            "outcome": "log_issue_security_impact_py_sonarqube",
            "label": "Python SonarQube Security-Impact Issue Stock",
            "role": "software_quality_impact_robustness",
            "scale": "log1p_count",
            "interpretation": "Issues with a security impact. Impact categories can overlap across an issue.",
        },
        {
            "outcome": "log_issue_high_severity_py_sonarqube",
            "label": "Python SonarQube High-Severity Issue Stock",
            "role": "severity_robustness",
            "scale": "log1p_count",
            "interpretation": "BLOCKER plus CRITICAL issue stock under the collected SonarQube severity schema.",
        },
    ]
    return pd.DataFrame(rows)


def add_qc(rows: list[dict[str, object]], check: str, value: object, expected: object, passed: bool, detail: str = "") -> None:
    rows.append({
        "check": check,
        "value": value,
        "expected": expected,
        "status": "pass" if passed else "fail",
        "detail": detail,
    })


def build_qc(
    panel: pd.DataFrame,
    audit: pd.DataFrame,
    unresolved: pd.DataFrame,
    b05_raw: pd.DataFrame,
    expected_rows: int,
    expected_repositories: int,
    expected_treatment_rows: int,
    expected_control_rows: int,
    expected_treatment_repositories: int,
    expected_control_repositories: int,
    expected_snapshots: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    source = panel["dataset_source"].astype("string")
    treatment = source.eq("treatment")
    control = source.eq("control")

    add_qc(rows, "panel_rows", len(panel), expected_rows, len(panel) == expected_rows)
    add_qc(rows, "panel_repositories", panel["repo_name"].nunique(), expected_repositories, panel["repo_name"].nunique() == expected_repositories)
    add_qc(rows, "treatment_rows", int(treatment.sum()), expected_treatment_rows, int(treatment.sum()) == expected_treatment_rows)
    add_qc(rows, "control_rows", int(control.sum()), expected_control_rows, int(control.sum()) == expected_control_rows)
    add_qc(rows, "treatment_repositories", panel.loc[treatment, "repo_name"].nunique(), expected_treatment_repositories, panel.loc[treatment, "repo_name"].nunique() == expected_treatment_repositories)
    add_qc(rows, "control_repositories", panel.loc[control, "repo_name"].nunique(), expected_control_repositories, panel.loc[control, "repo_name"].nunique() == expected_control_repositories)
    add_qc(rows, "b05_snapshots", len(b05_raw), expected_snapshots, len(b05_raw) == expected_snapshots)
    add_qc(rows, "panel_unique_quality_snapshots", panel["snapshot_key_sonarqube"].nunique(), expected_snapshots, panel["snapshot_key_sonarqube"].nunique() == expected_snapshots)
    add_qc(rows, "unresolved_panel_rows", len(unresolved), 0, len(unresolved) == 0)
    add_qc(rows, "unused_b05_snapshots", int((~audit["snapshot_used_by_panel"]).sum()), 0, int((~audit["snapshot_used_by_panel"]).sum()) == 0)
    add_qc(rows, "snapshot_repo_month_reuse_mismatches", int((~audit["repo_month_reuse_count_match"]).sum()), 0, int((~audit["repo_month_reuse_count_match"]).sum()) == 0)

    bool_checks = [
        ("quality_snapshot_matched", "unmatched_quality_snapshot_rows"),
        ("quality_repo_identity_match", "repo_identity_mismatch_rows"),
        ("quality_dataset_source_match", "dataset_source_mismatch_rows"),
        ("quality_commit_identity_match", "commit_identity_mismatch_rows"),
        ("quality_ncloc_match_panel", "ncloc_mismatch_rows"),
        ("log_issue_total_py_sonarqube_matches_b05", "log_transform_mismatch_rows"),
        ("issues_per_kloc_py_sonarqube_matches_b05", "density_recompute_mismatch_rows"),
        ("quality_type_counts_match_total", "type_sum_mismatch_rows"),
        ("quality_severity_counts_match_total", "severity_sum_mismatch_rows"),
        ("quality_component_counts_match_total", "component_sum_mismatch_rows"),
    ]
    for column, label in bool_checks:
        failures = int((~as_bool(panel[column])).sum())
        add_qc(rows, label, failures, 0, failures == 0)

    negative_count_rows = pd.Series(False, index=panel.index)
    for column in QUALITY_COUNT_COLUMNS:
        values = pd.to_numeric(panel[column], errors="coerce")
        negative_count_rows |= values.lt(0).fillna(False)
    negative_count = int(negative_count_rows.sum())
    add_qc(rows, "negative_quality_count_rows", negative_count, 0, negative_count == 0)

    missing_primary = int(panel["log_issue_total_py_sonarqube"].isna().sum())
    missing_density = int(panel["log_issues_per_kloc_py_sonarqube"].isna().sum())
    add_qc(rows, "missing_primary_quality_outcome_rows", missing_primary, 0, missing_primary == 0)
    add_qc(rows, "missing_density_quality_outcome_rows", missing_density, 0, missing_density == 0)

    non_python_components = int(pd.to_numeric(panel["issue_component_non_python"], errors="coerce").fillna(0).sum())
    unknown_components = int(pd.to_numeric(panel["issue_component_unknown"], errors="coerce").fillna(0).sum())
    add_qc(rows, "non_python_issue_components_across_panel_rows", non_python_components, 0, non_python_components == 0, "Snapshot stocks repeat when one snapshot represents multiple repo-month rows.")
    add_qc(rows, "unknown_issue_components_across_panel_rows", unknown_components, 0, unknown_components == 0)

    resolved_stock = int(pd.to_numeric(panel["quality_resolved_issue_total"], errors="coerce").fillna(0).sum())
    add_qc(rows, "resolved_issue_stock_across_panel_rows", resolved_stock, 0, resolved_stock == 0, "Primary outcome uses unresolved issue stock from independently scanned historical snapshot projects.")
    return pd.DataFrame(rows)


def build_summary(panel: pd.DataFrame, audit: pd.DataFrame, qc: pd.DataFrame) -> pd.DataFrame:
    source = panel["dataset_source"].astype("string")
    issue_total = pd.to_numeric(panel["issue_total_py_sonarqube"], errors="coerce")
    density = pd.to_numeric(panel["issues_per_kloc_py_sonarqube_recomputed"], errors="coerce")
    metrics = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("panel_rows", len(panel)),
        ("repositories", panel["repo_name"].nunique()),
        ("treatment_rows", int(source.eq("treatment").sum())),
        ("control_rows", int(source.eq("control").sum())),
        ("treatment_repositories", panel.loc[source.eq("treatment"), "repo_name"].nunique()),
        ("control_repositories", panel.loc[source.eq("control"), "repo_name"].nunique()),
        ("quality_snapshots", panel["snapshot_key_sonarqube"].nunique()),
        ("snapshots_reused_for_multiple_repo_months", int((pd.to_numeric(audit["mapped_repo_month_rows"], errors="coerce") > 1).sum())),
        ("max_repo_month_rows_per_snapshot", int(pd.to_numeric(audit["mapped_repo_month_rows"], errors="coerce").max())),
        ("issue_stock_min_repo_month", float(issue_total.min())),
        ("issue_stock_median_repo_month", float(issue_total.median())),
        ("issue_stock_mean_repo_month", float(issue_total.mean())),
        ("issue_stock_max_repo_month", float(issue_total.max())),
        ("zero_issue_repo_month_rows", int((issue_total == 0).sum())),
        ("density_median_issues_per_kloc_repo_month", float(density.median())),
        ("density_mean_issues_per_kloc_repo_month", float(density.mean())),
        ("density_p95_issues_per_kloc_repo_month", float(density.quantile(0.95))),
        ("density_p99_issues_per_kloc_repo_month", float(density.quantile(0.99))),
        ("density_max_issues_per_kloc_repo_month", float(density.max())),
        ("qc_failures", int(qc["status"].eq("fail").sum())),
        ("primary_outcome", "log_issue_total_py_sonarqube"),
        ("density_outcome", "log_issues_per_kloc_py_sonarqube"),
        ("count_semantics", "unresolved_issue_stock_at_historical_snapshot"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value"])


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    logging.info("Wrote %s rows to %s", len(frame), path)


def run_self_test() -> None:
    base = pd.DataFrame([
        {
            "repo_id": 1,
            "repo_name": "org/a",
            "dataset_source": "treatment",
            "time": "2025-01",
            "time_index": 1,
            "event_index": 2,
            "post_event": 0,
            "snapshot_key_sonarqube": "s1",
            "latest_commit_effective": "a" * 40,
            "ncloc_py_sonarqube": 100.0,
        },
        {
            "repo_id": 1,
            "repo_name": "org/a",
            "dataset_source": "treatment",
            "time": "2025-02",
            "time_index": 2,
            "event_index": 2,
            "post_event": 1,
            "snapshot_key_sonarqube": "s1",
            "latest_commit_effective": "a" * 40,
            "ncloc_py_sonarqube": 100.0,
        },
        {
            "repo_id": 2,
            "repo_name": "org/b",
            "dataset_source": "control",
            "time": "2025-01",
            "time_index": 1,
            "event_index": 0,
            "post_event": 0,
            "snapshot_key_sonarqube": "s2",
            "latest_commit_effective": "b" * 40,
            "ncloc_py_sonarqube": 200.0,
        },
    ])

    def b05_row(key: str, repo: str, source: str, sha: str, rows: int, ncloc: float, issues: int) -> dict[str, object]:
        return {
            "implementation_version": "v1",
            "dataset_source": source,
            "repo_name": repo,
            "snapshot_key": key,
            "commit_sha": sha,
            "repo_month_rows": rows,
            "project_key": f"p_{key}",
            "manifest_project_version": sha,
            "manifest_analysis_id": f"analysis_{key}",
            "scan_scope": "python_only_sonar_inclusions",
            "manifest_ncloc_py_sonarqube": ncloc,
            "observed_ncloc_py_sonarqube": ncloc,
            "ncloc_matches_manifest": True,
            "issue_total_py_sonarqube": issues,
            "log_issue_total_py_sonarqube": math.log1p(issues),
            "issues_per_kloc_py_sonarqube": issues * 1000.0 / ncloc,
            "issue_type_code_smell": issues,
            "issue_type_bug": 0,
            "issue_type_vulnerability": 0,
            "issue_type_other": 0,
            "issue_severity_blocker": 0,
            "issue_severity_critical": 0,
            "issue_severity_major": issues,
            "issue_severity_minor": 0,
            "issue_severity_info": 0,
            "issue_severity_other": 0,
            "issue_with_maintainability_impact": issues,
            "issue_with_reliability_impact": 0,
            "issue_with_security_impact": 0,
            "issue_component_python_file": issues,
            "issue_component_project": 0,
            "issue_component_non_python": 0,
            "issue_component_unknown": 0,
            "rule_distinct": 1 if issues else 0,
            "clean_code_attribute_distinct": 1 if issues else 0,
            "resolved_issue_total": 0,
            "analysis_count": 1,
            "manifest_analysis_found": True,
            "expected_project_version_found": True,
            "issue_rows_complete": True,
            "current_snapshot_recoverable": True,
            "duplicate_issue_keys_within_snapshot": 0,
            "issue_rows": issues,
            "issue_status_open": issues,
        }

    b05 = pd.DataFrame([
        b05_row("s1", "org/a", "treatment", "a" * 40, 2, 100.0, 10),
        b05_row("s2", "org/b", "control", "b" * 40, 1, 200.0, 20),
    ])
    panel, audit, unresolved = build_panel(base, b05)
    assert len(panel) == 3
    assert len(unresolved) == 0
    assert audit["repo_month_reuse_count_match"].all()
    assert np.allclose(panel.loc[panel["snapshot_key"] == "s1", "issues_per_kloc_py_sonarqube_recomputed"], 100.0)
    assert panel["quality_type_counts_match_total"].all()
    assert panel["quality_severity_counts_match_total"].all()
    assert panel["quality_component_counts_match_total"].all()
    print("Self-test passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-panel-file", type=Path)
    parser.add_argument("--b05-snapshot-counts-file", type=Path)
    parser.add_argument("--panel-output", type=Path)
    parser.add_argument("--snapshot-join-audit-output", type=Path)
    parser.add_argument("--distribution-summary-output", type=Path)
    parser.add_argument("--outcome-manifest-output", type=Path)
    parser.add_argument("--unresolved-output", type=Path)
    parser.add_argument("--qc-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-rows", type=int, default=914)
    parser.add_argument("--expected-control-rows", type=int, default=1040)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.self_test:
        run_self_test()
        return

    required_paths = {
        "base panel": args.base_panel_file,
        "run-x-b05 snapshot counts": args.b05_snapshot_counts_file,
        "panel output": args.panel_output,
        "snapshot join audit output": args.snapshot_join_audit_output,
        "distribution summary output": args.distribution_summary_output,
        "outcome manifest output": args.outcome_manifest_output,
        "unresolved output": args.unresolved_output,
        "QC output": args.qc_output,
        "summary output": args.summary_output,
    }
    missing_args = [label for label, value in required_paths.items() if value is None]
    if missing_args:
        raise ValueError(f"Missing required path arguments: {missing_args}")

    logging.info("Reading run-x-b02 monthly Python panel: %s", args.base_panel_file)
    base = pd.read_csv(args.base_panel_file, low_memory=False)
    logging.info("Reading run-x-b05 Python SonarQube issue snapshot counts: %s", args.b05_snapshot_counts_file)
    b05 = pd.read_csv(args.b05_snapshot_counts_file, low_memory=False)

    panel, audit, unresolved = build_panel(base, b05)
    distribution = build_distribution_summary(panel)
    outcome_manifest = build_outcome_manifest()
    qc = build_qc(
        panel,
        audit,
        unresolved,
        b05,
        expected_rows=args.expected_panel_rows,
        expected_repositories=args.expected_repositories,
        expected_treatment_rows=args.expected_treatment_rows,
        expected_control_rows=args.expected_control_rows,
        expected_treatment_repositories=args.expected_treatment_repositories,
        expected_control_repositories=args.expected_control_repositories,
        expected_snapshots=args.expected_snapshots,
    )
    summary = build_summary(panel, audit, qc)

    write_csv(panel, args.panel_output)
    write_csv(audit, args.snapshot_join_audit_output)
    write_csv(distribution, args.distribution_summary_output)
    write_csv(outcome_manifest, args.outcome_manifest_output)
    write_csv(unresolved, args.unresolved_output)
    write_csv(qc, args.qc_output)
    write_csv(summary, args.summary_output)

    failures = qc.loc[qc["status"].eq("fail")]
    logging.info(
        "Completed run-x-b06 panel build: rows=%s repos=%s snapshots=%s QC failures=%s",
        len(panel),
        panel["repo_name"].nunique(),
        panel["snapshot_key_sonarqube"].nunique(),
        len(failures),
    )
    if args.strict_expected_counts and not failures.empty:
        detail = "; ".join(f"{row.check}={row.value} expected={row.expected}" for row in failures.itertuples())
        raise SystemExit(f"Strict QC failed: {detail}")


if __name__ == "__main__":
    main()
