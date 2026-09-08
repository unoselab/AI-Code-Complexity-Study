#!/usr/bin/env python3
"""Build frozen-threshold RF and CM NPR x SonarQube burden panels.

run-x-l03-v1 is the detector-scope bridge required before refreshing the paper's
RF/CM NPR-localized quality DiD results. It reuses the validated D03/H03/L01
aggregation semantics without calling those historical scripts.

Frozen upstream inputs:
1. C02 v3: outcome-blind RF/FUN threshold catalog and audit.
2. C03 v1: outcome-blind CM/C_FUN threshold catalog and audit.
3. C05 v1: file-level unresolved SonarQube issue stock joined to the frozen
   continuous RF, CM, and RF+CM NPR measurements.
4. B06: authoritative 1,954-row Python SonarQube quality DiD base panel.

This experiment does not rescore NPR, regenerate perturbations, rerun SonarQube,
reselect a threshold, or estimate DiD. It applies the frozen common SC2-7B
threshold catalog independently to RF and CM file NPR metrics, then aggregates
selected-file issue stock to repository-month outcomes.

Output panel index:
    localization_scope x sample_spec x threshold_id x repo_id x time_index

Eligibility:
    RF: finite(file_npr_fun_space_by_token_weighted)
    CM: finite(file_npr_cfun_space_by_token_weighted)

Selection:
    eligible AND NPR > frozen threshold

Files without a finite scope-specific NPR are unclassified for that scope and are
never interpreted as below-threshold or human-written files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_VERSION = "run-x-l03-v1"
PRIMARY_THRESHOLD = 1.515059
LEGACY_THRESHOLD = 1.5183
PRIOR_PRIMARY_THRESHOLD = 1.571637
EXPECTED_THRESHOLD_COUNT = 23
EXPECTED_MAIN_GRID_COUNT = 21

ISSUE_COLUMNS = [
    "sonar_issue_total",
    "sonar_issue_type_code_smell",
    "sonar_issue_type_bug",
    "sonar_issue_type_vulnerability",
    "sonar_issue_type_other",
    "sonar_issue_high_severity",
    "sonar_issue_with_maintainability_impact",
    "sonar_issue_with_reliability_impact",
    "sonar_issue_with_security_impact",
]

OUTCOME_RENAME = {
    "sonar_issue_total": "selected_issue_total",
    "sonar_issue_type_code_smell": "selected_issue_code_smell",
    "sonar_issue_type_bug": "selected_issue_bug",
    "sonar_issue_type_vulnerability": "selected_issue_vulnerability",
    "sonar_issue_type_other": "selected_issue_other",
    "sonar_issue_high_severity": "selected_issue_high_severity",
    "sonar_issue_with_maintainability_impact": "selected_issue_maintainability_impact",
    "sonar_issue_with_reliability_impact": "selected_issue_reliability_impact",
    "sonar_issue_with_security_impact": "selected_issue_security_impact",
}

LOG_OUTCOME_COUNTS = [
    "selected_issue_total",
    "selected_issue_code_smell",
    "selected_issue_bug",
    "selected_issue_vulnerability",
    "selected_issue_high_severity",
    "selected_issue_maintainability_impact",
    "selected_issue_reliability_impact",
    "selected_issue_security_impact",
]

C05_REQUIRED_COLUMNS = {
    "repo_id",
    "dataset_source",
    "repo_name",
    "repo_month",
    "time_index",
    "event",
    "event_index",
    "snapshot_id",
    "snapshot_commit",
    "relative_path",
    "python_lines",
    "fun_space_by_tokens_scored",
    "fun_npr_coverage_ratio",
    "file_npr_fun_space_by_token_weighted",
    "file_npr_fun_status",
    "cfun_space_by_tokens_scored",
    "cfun_npr_coverage_ratio",
    "file_npr_cfun_space_by_token_weighted",
    "file_npr_cfun_status",
    *ISSUE_COLUMNS,
}

B06_REQUIRED_COLUMNS = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "scope_role",
    "treatment_group",
    "time",
    "time_index",
    "event",
    "event_index",
    "time_to_event",
    "is_treatment",
    "post_event",
    "cursor",
    "latest_commit_effective",
    "snapshot_key",
    "log_age",
    "ncloc_py_sonarqube",
    "log_contributors",
    "log_stars",
    "log_issues",
    "quality_did_complete",
    "quality_scope",
    "quality_count_semantics",
    "quality_metric_version",
}

THRESHOLD_SPEC_REQUIRED = {
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "metric",
    "note",
}

C05_OUTSIDE_REQUIRED = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "component_path",
    "sonar_issue_total",
}

BASE_PANEL_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "scope_role",
    "treatment_group",
    "time",
    "time_index",
    "event",
    "event_index",
    "time_to_event",
    "is_treatment",
    "post_event",
    "cursor",
    "latest_commit_effective",
    "snapshot_key",
    "log_age",
    "ncloc_py_sonarqube",
    "log_contributors",
    "log_stars",
    "log_issues",
]


@dataclass(frozen=True)
class ScopeSpec:
    scope_id: str
    scope_label: str
    metric: str
    token_column: str
    coverage_column: str
    status_column: str
    eligible_audit_column: str
    expected_finite_rows: int
    expected_primary_files: int
    expected_primary_issues: int
    expected_primary_smells: int
    expected_primary_sensitivity_files: int
    expected_primary_sensitivity_issues: int
    expected_prior_files: int
    expected_prior_issues: int
    expected_prior_smells: int
    expected_prior_sensitivity_files: int
    expected_prior_sensitivity_issues: int


RF_SCOPE = ScopeSpec(
    scope_id="rf",
    scope_label="RF",
    metric="file_npr_fun_space_by_token_weighted",
    token_column="fun_space_by_tokens_scored",
    coverage_column="fun_npr_coverage_ratio",
    status_column="file_npr_fun_status",
    eligible_audit_column="eligible_finite_fun_rows",
    expected_finite_rows=204508,
    expected_primary_files=20388,
    expected_primary_issues=31252,
    expected_primary_smells=30362,
    expected_primary_sensitivity_files=20236,
    expected_primary_sensitivity_issues=31030,
    expected_prior_files=13739,
    expected_prior_issues=20306,
    expected_prior_smells=19639,
    expected_prior_sensitivity_files=13659,
    expected_prior_sensitivity_issues=20251,
)

CM_SCOPE = ScopeSpec(
    scope_id="cm",
    scope_label="CM",
    metric="file_npr_cfun_space_by_token_weighted",
    token_column="cfun_space_by_tokens_scored",
    coverage_column="cfun_npr_coverage_ratio",
    status_column="file_npr_cfun_status",
    eligible_audit_column="eligible_finite_cfun_rows",
    expected_finite_rows=202027,
    expected_primary_files=13357,
    expected_primary_issues=17806,
    expected_primary_smells=17253,
    expected_primary_sensitivity_files=13106,
    expected_primary_sensitivity_issues=17710,
    expected_prior_files=7185,
    expected_prior_issues=9198,
    expected_prior_smells=8856,
    expected_prior_sensitivity_files=7045,
    expected_prior_sensitivity_issues=9158,
)

SCOPES = [RF_SCOPE, CM_SCOPE]


@dataclass(frozen=True)
class ThresholdSpec:
    threshold_id: str
    threshold_role: str
    grid_order: int | None
    delta_from_primary: float
    threshold: float
    comparison_operator: str
    note: str


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: Any) -> str:
    """Normalize nullable text."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def read_csv(path: Path, string_columns: list[str] | None = None) -> pd.DataFrame:
    """Read a CSV while preserving requested identifier columns as strings."""
    dtype = {column: "string" for column in (string_columns or [])}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def read_metric_csv(path: Path) -> dict[str, str]:
    """Read a two-column metric,value summary CSV."""
    frame = read_csv(path, ["metric", "value"])
    require_columns(frame, {"metric", "value"}, f"metric summary {path}")
    if frame["metric"].duplicated().any():
        raise ValueError(f"Duplicate metric keys in {path}")
    return {clean(row.metric): clean(row.value) for row in frame.itertuples(index=False)}


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    """Require a set of columns."""
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def sha256_file(path: Path) -> str:
    """Compute SHA256 for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path, compression: str | None = None) -> None:
    """Write CSV output atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + (".tmp.gz" if str(path).endswith(".gz") else ".tmp"))
    kwargs: dict[str, Any] = {"index": False}
    if compression == "gzip":
        kwargs["compression"] = {"method": "gzip", "mtime": 0}
    elif compression:
        kwargs["compression"] = compression
    frame.to_csv(tmp, **kwargs)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON output atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def add_check(rows: list[dict[str, Any]], check: str, observed: Any, expected: Any, passed: bool, detail: str = "") -> None:
    """Append one machine-readable QC row."""
    rows.append(
        {
            "check": check,
            "observed": observed,
            "expected": expected,
            "status": "pass" if passed else "fail",
            "detail": detail,
        }
    )


def load_threshold_catalog(spec_path: Path, audit_path: Path, scope: ScopeSpec) -> tuple[list[ThresholdSpec], pd.DataFrame]:
    """Load one frozen C02/C03 threshold catalog and its historical file audit."""
    spec = read_csv(spec_path, ["threshold_id", "threshold_role", "comparison_operator", "metric", "note"])
    audit = read_csv(audit_path, ["threshold_id", "threshold_role", "comparison_operator"])
    require_columns(spec, THRESHOLD_SPEC_REQUIRED, f"{scope.scope_label} threshold specification")
    require_columns(
        audit,
        {"threshold_id", "threshold_role", "threshold", "comparison_operator", scope.eligible_audit_column, "selected_file_rows"},
        f"{scope.scope_label} threshold audit",
    )
    if spec["threshold_id"].duplicated().any() or audit["threshold_id"].duplicated().any():
        raise ValueError(f"{scope.scope_label} threshold specification/audit contains duplicate threshold IDs")
    if not spec["metric"].map(clean).eq(scope.metric).all():
        raise ValueError(f"{scope.scope_label} threshold metric does not match {scope.metric}")
    if not spec["comparison_operator"].map(clean).eq(">").all():
        raise ValueError(f"{scope.scope_label} threshold comparator must be strict >")

    rows: list[ThresholdSpec] = []
    for row in spec.itertuples(index=False):
        order = None if pd.isna(row.grid_order) else int(row.grid_order)
        rows.append(
            ThresholdSpec(
                threshold_id=clean(row.threshold_id),
                threshold_role=clean(row.threshold_role),
                grid_order=order,
                delta_from_primary=float(row.delta_from_primary),
                threshold=float(row.threshold),
                comparison_operator=clean(row.comparison_operator),
                note=clean(row.note),
            )
        )

    if len(rows) != EXPECTED_THRESHOLD_COUNT:
        raise ValueError(f"Expected {EXPECTED_THRESHOLD_COUNT} {scope.scope_label} thresholds, observed {len(rows)}")
    primary = [item for item in rows if item.threshold_role == "primary"]
    legacy = [item for item in rows if item.threshold_role == "legacy_anchor"]
    prior = [item for item in rows if item.threshold_role == "prior_primary_anchor"]
    main = [item for item in rows if item.threshold_role in {"primary", "sensitivity_grid"}]
    if len(primary) != 1 or not math.isclose(primary[0].threshold, PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError(f"{scope.scope_label} primary threshold is not {PRIMARY_THRESHOLD}")
    if primary[0].grid_order != 10 or not math.isclose(primary[0].delta_from_primary, 0.0, abs_tol=1e-12):
        raise ValueError(f"{scope.scope_label} primary threshold must be grid order 10 with zero delta")
    if len(legacy) != 1 or not math.isclose(legacy[0].threshold, LEGACY_THRESHOLD, abs_tol=1e-12):
        raise ValueError(f"{scope.scope_label} legacy threshold is not {LEGACY_THRESHOLD}")
    if len(prior) != 1 or not math.isclose(prior[0].threshold, PRIOR_PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError(f"{scope.scope_label} prior-primary threshold is not {PRIOR_PRIMARY_THRESHOLD}")
    if len(main) != EXPECTED_MAIN_GRID_COUNT or sorted(item.grid_order for item in main if item.grid_order is not None) != list(range(21)):
        raise ValueError(f"{scope.scope_label} main-grid orders must be exactly 0..20")
    if set(spec["threshold_id"].map(clean)) != set(audit["threshold_id"].map(clean)):
        raise ValueError(f"{scope.scope_label} threshold spec/audit IDs do not match")
    return rows, audit


def validate_common_catalog(rf_specs: list[ThresholdSpec], cm_specs: list[ThresholdSpec]) -> None:
    """Require RF and CM to use the same outcome-blind threshold values and IDs."""
    rf = {(s.threshold_id, s.threshold_role, s.grid_order, round(s.delta_from_primary, 12), round(s.threshold, 12), s.comparison_operator) for s in rf_specs}
    cm = {(s.threshold_id, s.threshold_role, s.grid_order, round(s.delta_from_primary, 12), round(s.threshold, 12), s.comparison_operator) for s in cm_specs}
    if rf != cm:
        raise ValueError("C02 RF and C03 CM threshold catalogs are not identical apart from the NPR metric")


def validate_threshold_summary(path: Path, scope: ScopeSpec, expected_version: str) -> dict[str, Any]:
    """Validate an outcome-blind C02/C03 summary gate."""
    summary = read_json(path)
    if clean(summary.get("script_version")) != expected_version:
        raise ValueError(f"Unexpected {scope.scope_label} threshold script version: {summary.get('script_version')}")
    if clean(summary.get("status")) != "PASS" or int(summary.get("hard_check_failures", -1)) != 0:
        raise ValueError(f"{scope.scope_label} threshold audit is not a clean PASS")
    if bool(summary.get("quality_outcome_inputs_consumed")):
        raise ValueError(f"{scope.scope_label} threshold construction consumed quality outcomes")
    methodology = summary.get("methodology", {})
    if clean(methodology.get("metric")) != scope.metric:
        raise ValueError(f"{scope.scope_label} summary metric mismatch")
    if clean(methodology.get("comparison_operator")) != ">":
        raise ValueError(f"{scope.scope_label} summary comparator is not strict >")
    if not math.isclose(float(methodology.get("primary_threshold")), PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError(f"{scope.scope_label} summary primary threshold mismatch")
    if int(methodology.get("threshold_total_including_anchors")) != EXPECTED_THRESHOLD_COUNT:
        raise ValueError(f"{scope.scope_label} summary threshold count mismatch")
    return summary


def derive_scope_sensitivity_repositories(c05_summary_path: Path, c05_checks_path: Path, outside_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Validate C05 and derive the pre-DiD repository sensitivity exclusion."""
    summary = read_metric_csv(c05_summary_path)
    if summary.get("script_version") != "run-x-c05-v1":
        raise ValueError(f"Unexpected C05 version: {summary.get('script_version')}")
    if summary.get("status") != "PASS_WITH_SCOPE_EXCLUSIONS":
        raise ValueError(f"Unexpected C05 status: {summary.get('status')}")
    if summary.get("threshold_applied") != "0" or summary.get("density_computed") != "0" or summary.get("hard_qc_failures") != "0":
        raise ValueError("C05 does not satisfy the no-threshold/no-density/no-hard-failure contract")
    if not math.isclose(float(summary.get("c04_primary_threshold_provenance_only", "nan")), PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError("C05 primary threshold provenance does not match 1.515059")

    checks = read_csv(c05_checks_path, ["check", "status"])
    require_columns(checks, {"check", "status"}, "C05 checks")
    if checks.empty or checks["check"].duplicated().any() or not checks["status"].map(clean).eq("pass").all():
        raise ValueError("C05 hard-QC table is not a clean all-pass table")

    outside = read_csv(outside_path, ["snapshot_key", "dataset_source", "repo_name", "commit_sha", "component_path"])
    require_columns(outside, C05_OUTSIDE_REQUIRED, "C05 outside-C04 scope file")
    if outside.empty:
        raise ValueError("C05 outside-C04 scope file is unexpectedly empty")
    outside["sonar_issue_total"] = pd.to_numeric(outside["sonar_issue_total"], errors="coerce")
    if outside["sonar_issue_total"].isna().any() or (outside["sonar_issue_total"] < 0).any():
        raise ValueError("C05 outside-C04 issue totals must be complete and non-negative")
    expected_files = int(summary.get("b05_issue_bearing_snapshot_files_outside_c04", "-1"))
    expected_issues = int(summary.get("b05_issue_rows_outside_c04", "-1"))
    if len(outside) != expected_files or int(outside["sonar_issue_total"].sum()) != expected_issues:
        raise ValueError("C05 outside-C04 rows/issues do not reconcile with C05 summary")

    repos = outside[["dataset_source", "repo_name"]].drop_duplicates().sort_values(["dataset_source", "repo_name"]).reset_index(drop=True)
    if len(repos) != 2:
        raise ValueError(f"Expected 2 scope-sensitivity repositories, observed {len(repos)}")
    return repos, summary


def load_c05_file_table(path: Path) -> pd.DataFrame:
    """Load only columns required to build RF and CM threshold-quality panels."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, C05_REQUIRED_COLUMNS, "C05 file-quality table")
    data = pd.read_csv(path, usecols=sorted(C05_REQUIRED_COLUMNS), low_memory=False)

    for column in ["repo_id", "time_index", "event_index", "python_lines", RF_SCOPE.token_column, CM_SCOPE.token_column, RF_SCOPE.coverage_column, CM_SCOPE.coverage_column, RF_SCOPE.metric, CM_SCOPE.metric, *ISSUE_COLUMNS]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[["repo_id", "time_index"]].isna().any().any():
        raise ValueError("C05 repo_id/time_index contains missing numeric values")
    for column in ISSUE_COLUMNS:
        if data[column].isna().any() or (data[column] < 0).any():
            raise ValueError(f"C05 issue column must be complete and non-negative: {column}")
    return data


def load_b06_panel(path: Path) -> pd.DataFrame:
    """Load and validate the authoritative B06 causal-panel skeleton."""
    data = read_csv(path, ["repo_name", "dataset_source", "scope_role", "time", "event", "latest_commit_effective", "snapshot_key", "quality_scope", "quality_count_semantics", "quality_metric_version"])
    require_columns(data, B06_REQUIRED_COLUMNS, "B06 quality DiD panel")
    for column in ["repo_id", "treatment_group", "time_index", "event_index", "time_to_event", "is_treatment", "post_event", "cursor", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues", "quality_did_complete"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if len(data) != 1954 or data["repo_id"].nunique() != 167:
        raise ValueError(f"Unexpected B06 support: rows={len(data)}, repos={data['repo_id'].nunique()}")
    if data.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("B06 contains duplicate repo_id/time_index keys")
    if not data["quality_did_complete"].eq(1).all():
        raise ValueError("B06 quality_did_complete is not 1 for all rows")
    if not data["quality_scope"].map(clean).eq("python_only_sonar_inclusions").all():
        raise ValueError("B06 quality_scope mismatch")
    return data


def validate_repo_month_identity(c05: pd.DataFrame, b06: pd.DataFrame) -> None:
    """Require C05 and B06 to describe exactly the same 1,954 repo-months."""
    identity_cols = [
        "repo_id", "time_index", "dataset_source", "repo_name", "repo_month", "event", "event_index",
        "snapshot_id", "snapshot_commit",
    ]
    grouped = c05[identity_cols].drop_duplicates()
    if grouped.duplicated(["repo_id", "time_index"], keep=False).any():
        raise ValueError("C05 has inconsistent repo-month identity within repo_id/time_index")

    right = b06[["repo_id", "time_index", "dataset_source", "repo_name", "time", "event", "event_index", "snapshot_key", "latest_commit_effective"]].copy()
    merged = right.merge(grouped, on=["repo_id", "time_index"], how="outer", suffixes=("_b06", "_c05"), indicator=True, validate="one_to_one")
    if not merged["_merge"].eq("both").all():
        raise ValueError("C05/B06 repo-month key universes do not match")
    comparisons = {
        "dataset_source": merged["dataset_source_b06"].map(clean).str.casefold().eq(merged["dataset_source_c05"].map(clean).str.casefold()),
        "repo_name": merged["repo_name_b06"].map(clean).str.casefold().eq(merged["repo_name_c05"].map(clean).str.casefold()),
        "time": merged["time"].map(clean).eq(merged["repo_month"].map(clean)),
        "event": merged["event_b06"].map(clean).eq(merged["event_c05"].map(clean)),
        "event_index": pd.to_numeric(merged["event_index_b06"], errors="coerce").eq(pd.to_numeric(merged["event_index_c05"], errors="coerce")),
        "snapshot_key": merged["snapshot_key"].map(clean).eq(merged["snapshot_id"].map(clean)),
        "commit": merged["latest_commit_effective"].map(clean).str.casefold().eq(merged["snapshot_commit"].map(clean).str.casefold()),
    }
    failures = {name: int((~mask).sum()) for name, mask in comparisons.items()}
    if any(failures.values()):
        raise ValueError(f"C05/B06 identity mismatches: {failures}")


def normalized_timing(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the normalized event clock and absorbing-treatment indicator."""
    data = panel.copy()
    data["event_time_normalized"] = np.where(
        data["treatment_group"].eq(1), data["time_index"] - data["event_index"], np.nan
    )
    data["absorbing_treated"] = (
        data["treatment_group"].eq(1)
        & data["event_index"].gt(0)
        & data["time_index"].ge(data["event_index"])
    ).astype("int64")
    return data


def timing_stratum(panel: pd.DataFrame) -> pd.Series:
    """Return control/treatment-pre/treatment-post descriptive strata."""
    treatment = panel["treatment_group"].eq(1)
    post = panel["absorbing_treated"].eq(1)
    return pd.Series(
        np.select([~treatment, treatment & ~post, treatment & post], ["control", "treatment_pre", "treatment_post"], default="unknown"),
        index=panel.index,
        dtype="string",
    )


def aggregate_one_threshold(files: pd.DataFrame, threshold: float, base_keys: pd.DataFrame, scope: ScopeSpec) -> pd.DataFrame:
    """Aggregate one scope and one frozen threshold to repository-month burden."""
    metric = pd.to_numeric(files[scope.metric], errors="coerce")
    eligible = np.isfinite(metric.to_numpy(dtype=float))
    selected = eligible & metric.gt(threshold).to_numpy(dtype=bool)

    work = files[["repo_id", "time_index", "python_lines", scope.token_column, *ISSUE_COLUMNS]].copy()
    work["eligible_file_count"] = eligible.astype("int64")
    work["selected_file_count"] = selected.astype("int64")
    work["selected_file_with_any_issue_count"] = (selected & files["sonar_issue_total"].gt(0).to_numpy(dtype=bool)).astype("int64")
    work["selected_python_lines"] = pd.to_numeric(work["python_lines"], errors="coerce").fillna(0).where(selected, 0)
    work["selected_procedure_space_by_tokens"] = pd.to_numeric(work[scope.token_column], errors="coerce").fillna(0).where(selected, 0)
    for column in ISSUE_COLUMNS:
        work[column] = work[column].where(selected, 0)

    agg_map: dict[str, str] = {
        "eligible_file_count": "sum",
        "selected_file_count": "sum",
        "selected_file_with_any_issue_count": "sum",
        "selected_python_lines": "sum",
        "selected_procedure_space_by_tokens": "sum",
    }
    agg_map.update({column: "sum" for column in ISSUE_COLUMNS})
    grouped = work.groupby(["repo_id", "time_index"], as_index=False).agg(agg_map).rename(columns=OUTCOME_RENAME)
    grouped["selected_issue_free_file_count"] = grouped["selected_file_count"] - grouped["selected_file_with_any_issue_count"]
    grouped["selected_file_share_of_eligible"] = np.where(
        grouped["eligible_file_count"].gt(0), grouped["selected_file_count"] / grouped["eligible_file_count"], np.nan
    )
    grouped["has_eligible_files"] = grouped["eligible_file_count"].gt(0).astype("int64")
    grouped["has_selected_files"] = grouped["selected_file_count"].gt(0).astype("int64")
    grouped["has_selected_issue_burden"] = grouped["selected_issue_total"].gt(0).astype("int64")

    output = base_keys.merge(grouped, on=["repo_id", "time_index"], how="left", validate="one_to_one")
    count_columns = [
        "eligible_file_count", "selected_file_count", "selected_file_with_any_issue_count", "selected_issue_free_file_count",
        "selected_python_lines", "selected_procedure_space_by_tokens", *OUTCOME_RENAME.values(),
        "has_eligible_files", "has_selected_files", "has_selected_issue_burden",
    ]
    for column in count_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    integer_columns = [c for c in count_columns if c != "selected_file_share_of_eligible"]
    for column in integer_columns:
        output[column] = output[column].astype("int64")
    output["selected_file_share_of_eligible"] = np.where(
        output["eligible_file_count"].gt(0), output["selected_file_count"] / output["eligible_file_count"], np.nan
    )
    for count_column in LOG_OUTCOME_COUNTS:
        output[f"log1p_{count_column}"] = np.log1p(output[count_column].astype(float))
    return output


def build_outputs(
    c05: pd.DataFrame,
    b06: pd.DataFrame,
    catalogs: dict[str, list[ThresholdSpec]],
    audits: dict[str, pd.DataFrame],
    scope_repos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build unified RF/CM long panel plus global/timing/sample audits."""
    validate_repo_month_identity(c05, b06)
    base = normalized_timing(b06[BASE_PANEL_COLUMNS].copy())
    base_keys = base[["repo_id", "time_index"]].copy()

    exclude_repos = {clean(value).casefold() for value in scope_repos["repo_name"]}
    sample_specs = {
        "full_sample": base,
        "exclude_scope_mismatch_repos": base[~base["repo_name"].map(clean).str.casefold().isin(exclude_repos)].copy(),
    }

    scope_spec = scope_repos.copy()
    scope_spec.insert(0, "sample_spec", "exclude_scope_mismatch_repos")
    scope_spec["exclude_repository"] = 1
    scope_spec["frozen_before_did"] = 1
    scope_spec["reason"] = (
        "C05 contains issue-bearing Python file paths outside the frozen combined NPR file universe; "
        "exclude the affected repository as a common scope-sensitivity analysis for RF and CM."
    )

    panel_parts: list[pd.DataFrame] = []
    global_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []

    for scope in SCOPES:
        audit_by_id = audits[scope.scope_id].set_index(audits[scope.scope_id]["threshold_id"].map(clean), drop=False)
        for spec in catalogs[scope.scope_id]:
            aggregated = aggregate_one_threshold(c05, spec.threshold, base_keys, scope)
            for sample_name, sample_base in sample_specs.items():
                sample = sample_base.merge(aggregated, on=["repo_id", "time_index"], how="left", validate="one_to_one")
                sample["timing_stratum"] = timing_stratum(sample)
                sample.insert(0, "localization_scope", scope.scope_label)
                sample.insert(1, "scope_id", scope.scope_id)
                sample.insert(2, "npr_metric", scope.metric)
                sample.insert(3, "sample_spec", sample_name)
                sample.insert(4, "threshold_id", spec.threshold_id)
                sample.insert(5, "threshold_role", spec.threshold_role)
                sample.insert(6, "grid_order", spec.grid_order)
                sample.insert(7, "delta_from_primary", spec.delta_from_primary)
                sample.insert(8, "threshold", spec.threshold)
                sample.insert(9, "comparison_operator", spec.comparison_operator)
                sample.insert(10, "quality_scope", f"canonical_{scope.scope_id}_python_files_with_finite_scope_npr")
                panel_parts.append(sample)

                selected_files = int(sample["selected_file_count"].sum())
                eligible_files = int(sample["eligible_file_count"].sum())
                global_rows.append(
                    {
                        "localization_scope": scope.scope_label,
                        "scope_id": scope.scope_id,
                        "npr_metric": scope.metric,
                        "sample_spec": sample_name,
                        "threshold_id": spec.threshold_id,
                        "threshold_role": spec.threshold_role,
                        "grid_order": spec.grid_order,
                        "delta_from_primary": spec.delta_from_primary,
                        "threshold": spec.threshold,
                        "comparison_operator": spec.comparison_operator,
                        "eligible_file_rows": eligible_files,
                        "selected_file_rows": selected_files,
                        "selected_share_of_eligible": selected_files / eligible_files if eligible_files else np.nan,
                        "repo_months_with_selected_files": int(sample["has_selected_files"].sum()),
                        "repositories_with_selected_files": int(sample.loc[sample["has_selected_files"].eq(1), "repo_id"].nunique()),
                        "selected_issue_total": int(sample["selected_issue_total"].sum()),
                        "selected_issue_code_smell": int(sample["selected_issue_code_smell"].sum()),
                        "selected_issue_bug": int(sample["selected_issue_bug"].sum()),
                        "selected_issue_vulnerability": int(sample["selected_issue_vulnerability"].sum()),
                        "selected_issue_high_severity": int(sample["selected_issue_high_severity"].sum()),
                        "selected_issue_maintainability_impact": int(sample["selected_issue_maintainability_impact"].sum()),
                        "selected_issue_reliability_impact": int(sample["selected_issue_reliability_impact"].sum()),
                        "selected_issue_security_impact": int(sample["selected_issue_security_impact"].sum()),
                    }
                )

                timing_groups = [
                    ("all", sample),
                    ("control", sample[sample["timing_stratum"].eq("control")]),
                    ("treatment", sample[sample["treatment_group"].eq(1)]),
                    ("treatment_pre", sample[sample["timing_stratum"].eq("treatment_pre")]),
                    ("treatment_post", sample[sample["timing_stratum"].eq("treatment_post")]),
                ]
                for stratum, group in timing_groups:
                    timing_rows.append(
                        {
                            "localization_scope": scope.scope_label,
                            "scope_id": scope.scope_id,
                            "sample_spec": sample_name,
                            "threshold_id": spec.threshold_id,
                            "threshold_role": spec.threshold_role,
                            "threshold": spec.threshold,
                            "timing_stratum": stratum,
                            "repo_month_rows": len(group),
                            "repositories": group["repo_id"].nunique(),
                            "eligible_file_rows": int(group["eligible_file_count"].sum()),
                            "selected_file_rows": int(group["selected_file_count"].sum()),
                            "repo_months_with_selected_files": int(group["has_selected_files"].sum()),
                            "selected_issue_total": int(group["selected_issue_total"].sum()),
                            "selected_issue_code_smell": int(group["selected_issue_code_smell"].sum()),
                            "selected_issue_bug": int(group["selected_issue_bug"].sum()),
                            "selected_issue_vulnerability": int(group["selected_issue_vulnerability"].sum()),
                            "selected_issue_high_severity": int(group["selected_issue_high_severity"].sum()),
                        }
                    )

    panel = pd.concat(panel_parts, ignore_index=True)
    global_audit = pd.DataFrame(global_rows)
    timing_audit = pd.DataFrame(timing_rows)

    sample_rows: list[dict[str, Any]] = []
    for scope in SCOPES:
        for sample_name, sample in sample_specs.items():
            normalized = normalized_timing(sample)
            sample_rows.append(
                {
                    "localization_scope": scope.scope_label,
                    "scope_id": scope.scope_id,
                    "sample_spec": sample_name,
                    "repo_month_rows": len(normalized),
                    "repositories": normalized["repo_id"].nunique(),
                    "control_repositories": normalized.loc[normalized["treatment_group"].eq(0), "repo_id"].nunique(),
                    "treatment_repositories": normalized.loc[normalized["treatment_group"].eq(1), "repo_id"].nunique(),
                    "control_rows": int(normalized["treatment_group"].eq(0).sum()),
                    "treatment_pre_rows": int((normalized["treatment_group"].eq(1) & normalized["absorbing_treated"].eq(0)).sum()),
                    "treatment_post_rows": int(normalized["absorbing_treated"].eq(1).sum()),
                    "untreated_first_stage_rows": int(normalized["absorbing_treated"].eq(0).sum()),
                    "dynamic_event_0_to_6_rows": int((normalized["absorbing_treated"].eq(1) & pd.Series(normalized["event_time_normalized"]).between(0, 6)).sum()),
                    "excluded_repository_count": 0 if sample_name == "full_sample" else len(exclude_repos),
                    "excluded_repositories": "" if sample_name == "full_sample" else " | ".join(sorted(scope_repos["repo_name"].map(clean))),
                }
            )
    sample_summary = pd.DataFrame(sample_rows)

    outcome_spec = pd.DataFrame(
        [
            {"outcome": "log1p_selected_issue_total", "role": "primary_burden", "count_column": "selected_issue_total", "description": "log1p unresolved SonarQube issue stock in scope-eligible files exceeding the frozen NPR threshold"},
            {"outcome": "log1p_selected_issue_code_smell", "role": "robustness_burden", "count_column": "selected_issue_code_smell", "description": "log1p code-smell stock in selected files"},
            {"outcome": "log1p_selected_issue_bug", "role": "robustness_burden", "count_column": "selected_issue_bug", "description": "log1p bug stock in selected files"},
            {"outcome": "log1p_selected_issue_vulnerability", "role": "robustness_burden", "count_column": "selected_issue_vulnerability", "description": "log1p vulnerability stock in selected files"},
            {"outcome": "log1p_selected_issue_maintainability_impact", "role": "robustness_burden", "count_column": "selected_issue_maintainability_impact", "description": "log1p maintainability-impact issue stock in selected files"},
            {"outcome": "log1p_selected_issue_reliability_impact", "role": "robustness_burden", "count_column": "selected_issue_reliability_impact", "description": "log1p reliability-impact issue stock in selected files"},
            {"outcome": "log1p_selected_issue_security_impact", "role": "robustness_burden", "count_column": "selected_issue_security_impact", "description": "log1p security-impact issue stock in selected files"},
            {"outcome": "log1p_selected_issue_high_severity", "role": "robustness_burden", "count_column": "selected_issue_high_severity", "description": "log1p BLOCKER+CRITICAL issue stock in selected files"},
        ]
    )
    return panel, global_audit, timing_audit, sample_summary, outcome_spec, scope_spec


def make_checks(
    panel: pd.DataFrame,
    global_audit: pd.DataFrame,
    sample_summary: pd.DataFrame,
    catalogs: dict[str, list[ThresholdSpec]],
    audits: dict[str, pd.DataFrame],
    c05: pd.DataFrame,
    strict: bool,
) -> pd.DataFrame:
    """Create hard structural, lineage, monotonicity, and bridge checks."""
    rows: list[dict[str, Any]] = []
    add_check(rows, "localization_scope_count", panel["scope_id"].nunique(), 2, panel["scope_id"].nunique() == 2)
    add_check(rows, "threshold_count_per_scope", min(len(catalogs[s.scope_id]) for s in SCOPES), 23, all(len(catalogs[s.scope_id]) == 23 for s in SCOPES))
    add_check(rows, "c05_file_rows", len(c05), 510297, (len(c05) == 510297) or not strict)

    for scope in SCOPES:
        finite = int(np.isfinite(pd.to_numeric(c05[scope.metric], errors="coerce").to_numpy(dtype=float)).sum())
        add_check(rows, f"{scope.scope_id}_finite_rows", finite, scope.expected_finite_rows, (finite == scope.expected_finite_rows) or not strict)

    for scope in SCOPES:
        for sample_name, expected_rows, expected_repos in [("full_sample", 1954, 167), ("exclude_scope_mismatch_repos", 1915, 165)]:
            row = sample_summary[(sample_summary["scope_id"].eq(scope.scope_id)) & (sample_summary["sample_spec"].eq(sample_name))].iloc[0]
            add_check(rows, f"{scope.scope_id}_{sample_name}_repo_month_rows", int(row["repo_month_rows"]), expected_rows, (int(row["repo_month_rows"]) == expected_rows) or not strict)
            add_check(rows, f"{scope.scope_id}_{sample_name}_repositories", int(row["repositories"]), expected_repos, (int(row["repositories"]) == expected_repos) or not strict)

    expected_panel_rows = 2 * 23 * (1954 + 1915)
    add_check(rows, "long_panel_rows", len(panel), expected_panel_rows, len(panel) == expected_panel_rows)
    duplicate_keys = int(panel.duplicated(["scope_id", "sample_spec", "threshold_id", "repo_id", "time_index"]).sum())
    add_check(rows, "long_panel_duplicate_keys", duplicate_keys, 0, duplicate_keys == 0)

    # Reconcile every full-sample threshold to the outcome-blind C02/C03 file-selection audits.
    mismatch_total = 0
    for scope in SCOPES:
        expected = audits[scope.scope_id].set_index(audits[scope.scope_id]["threshold_id"].map(clean), drop=False)
        observed = global_audit[(global_audit["scope_id"].eq(scope.scope_id)) & (global_audit["sample_spec"].eq("full_sample"))].set_index("threshold_id")
        mismatches = 0
        for spec in catalogs[scope.scope_id]:
            exp_eligible = int(pd.to_numeric(expected.loc[spec.threshold_id, scope.eligible_audit_column]))
            exp_selected = int(pd.to_numeric(expected.loc[spec.threshold_id, "selected_file_rows"]))
            obs_eligible = int(observed.loc[spec.threshold_id, "eligible_file_rows"])
            obs_selected = int(observed.loc[spec.threshold_id, "selected_file_rows"])
            mismatches += int(exp_eligible != obs_eligible or exp_selected != obs_selected)
        mismatch_total += mismatches
        add_check(rows, f"{scope.scope_id}_frozen_threshold_selection_reconcile_all_thresholds", mismatches, 0, mismatches == 0)
    add_check(rows, "all_scope_threshold_selection_reconcile", mismatch_total, 0, mismatch_total == 0)

    # Main-grid nesting: a stricter threshold cannot add selected files or nonnegative issue stock.
    for scope in SCOPES:
        for sample_name in ["full_sample", "exclude_scope_mismatch_repos"]:
            group = global_audit[
                global_audit["scope_id"].eq(scope.scope_id)
                & global_audit["sample_spec"].eq(sample_name)
                & global_audit["threshold_role"].isin(["primary", "sensitivity_grid"])
            ].sort_values("threshold")
            for column in ["selected_file_rows", "selected_issue_total", "selected_issue_code_smell", "selected_issue_bug", "selected_issue_vulnerability", "selected_issue_high_severity"]:
                violations = int(np.sum(np.diff(group[column].to_numpy(dtype=float)) > 0))
                add_check(rows, f"monotonic::{scope.scope_id}::{sample_name}::{column}", violations, 0, violations == 0)

    negative = 0
    for column in [c for c in panel.columns if c.startswith("selected_issue_") and not c.endswith("file_count")]:
        negative += int((pd.to_numeric(panel[column], errors="coerce") < 0).sum())
    add_check(rows, "negative_selected_issue_values", negative, 0, negative == 0)

    log_mismatch = 0
    for count_column in LOG_OUTCOME_COUNTS:
        log_column = f"log1p_{count_column}"
        expected = np.log1p(pd.to_numeric(panel[count_column], errors="coerce").to_numpy(dtype=float))
        observed = pd.to_numeric(panel[log_column], errors="coerce").to_numpy(dtype=float)
        log_mismatch += int(np.sum(~np.isclose(expected, observed, atol=1e-12, rtol=0.0, equal_nan=True)))
    add_check(rows, "log1p_recomputation_mismatches", log_mismatch, 0, log_mismatch == 0)

    # Freeze the most important primary and prior-primary accounting numbers for both scopes.
    expected_values = {
        "rf": RF_SCOPE,
        "cm": CM_SCOPE,
    }
    for scope_id, scope in expected_values.items():
        full = global_audit[(global_audit["scope_id"].eq(scope_id)) & (global_audit["sample_spec"].eq("full_sample"))].set_index("threshold_id")
        sens = global_audit[(global_audit["scope_id"].eq(scope_id)) & (global_audit["sample_spec"].eq("exclude_scope_mismatch_repos"))].set_index("threshold_id")
        pairs = [
            ("primary_files", int(full.loc["primary", "selected_file_rows"]), scope.expected_primary_files),
            ("primary_issues", int(full.loc["primary", "selected_issue_total"]), scope.expected_primary_issues),
            ("primary_smells", int(full.loc["primary", "selected_issue_code_smell"]), scope.expected_primary_smells),
            ("primary_sensitivity_files", int(sens.loc["primary", "selected_file_rows"]), scope.expected_primary_sensitivity_files),
            ("primary_sensitivity_issues", int(sens.loc["primary", "selected_issue_total"]), scope.expected_primary_sensitivity_issues),
            ("prior_files", int(full.loc["prior_primary_1571637", "selected_file_rows"]), scope.expected_prior_files),
            ("prior_issues", int(full.loc["prior_primary_1571637", "selected_issue_total"]), scope.expected_prior_issues),
            ("prior_smells", int(full.loc["prior_primary_1571637", "selected_issue_code_smell"]), scope.expected_prior_smells),
            ("prior_sensitivity_files", int(sens.loc["prior_primary_1571637", "selected_file_rows"]), scope.expected_prior_sensitivity_files),
            ("prior_sensitivity_issues", int(sens.loc["prior_primary_1571637", "selected_issue_total"]), scope.expected_prior_sensitivity_issues),
        ]
        for label, observed, expected in pairs:
            add_check(rows, f"{scope_id}_{label}", observed, expected, (observed == expected) or not strict)

    add_check(rows, "primary_threshold_exact", PRIMARY_THRESHOLD, 1.515059, math.isclose(PRIMARY_THRESHOLD, 1.515059, abs_tol=1e-12))
    add_check(rows, "legacy_threshold_exact", LEGACY_THRESHOLD, 1.5183, math.isclose(LEGACY_THRESHOLD, 1.5183, abs_tol=1e-12))
    add_check(rows, "prior_primary_threshold_exact", PRIOR_PRIMARY_THRESHOLD, 1.571637, math.isclose(PRIOR_PRIMARY_THRESHOLD, 1.571637, abs_tol=1e-12))
    return pd.DataFrame(rows)


def build_summary(global_audit: pd.DataFrame, sample_summary: pd.DataFrame, panel: pd.DataFrame, scope_repos: pd.DataFrame, hard_failures: int) -> pd.DataFrame:
    """Build concise experiment-level summary metrics."""
    rows: list[tuple[str, Any]] = [
        ("script_version", SCRIPT_VERSION),
        ("status", "PASS" if hard_failures == 0 else "FAIL"),
        ("localization_scopes", 2),
        ("thresholds_per_scope", 23),
        ("sample_specs_per_scope", 2),
        ("full_sample_repo_month_rows", 1954),
        ("scope_sensitivity_repo_month_rows", 1915),
        ("long_panel_rows", len(panel)),
        ("primary_threshold", PRIMARY_THRESHOLD),
        ("legacy_threshold", LEGACY_THRESHOLD),
        ("prior_primary_threshold", PRIOR_PRIMARY_THRESHOLD),
    ]
    for scope in SCOPES:
        full = global_audit[(global_audit["scope_id"].eq(scope.scope_id)) & (global_audit["sample_spec"].eq("full_sample"))].set_index("threshold_id")
        sens = global_audit[(global_audit["scope_id"].eq(scope.scope_id)) & (global_audit["sample_spec"].eq("exclude_scope_mismatch_repos"))].set_index("threshold_id")
        rows.extend(
            [
                (f"{scope.scope_id}_primary_selected_file_rows", int(full.loc["primary", "selected_file_rows"])),
                (f"{scope.scope_id}_primary_selected_issue_total", int(full.loc["primary", "selected_issue_total"])),
                (f"{scope.scope_id}_primary_selected_code_smell", int(full.loc["primary", "selected_issue_code_smell"])),
                (f"{scope.scope_id}_primary_sensitivity_selected_file_rows", int(sens.loc["primary", "selected_file_rows"])),
                (f"{scope.scope_id}_primary_sensitivity_selected_issue_total", int(sens.loc["primary", "selected_issue_total"])),
                (f"{scope.scope_id}_prior_primary_selected_file_rows", int(full.loc["prior_primary_1571637", "selected_file_rows"])),
                (f"{scope.scope_id}_prior_primary_selected_issue_total", int(full.loc["prior_primary_1571637", "selected_issue_total"])),
                (f"{scope.scope_id}_delta_primary_vs_prior_selected_files", int(full.loc["primary", "selected_file_rows"]) - int(full.loc["prior_primary_1571637", "selected_file_rows"])),
            ]
        )
    rows.extend(
        [
            ("scope_sensitivity_repositories", len(scope_repos)),
            ("density_computed", 0),
            ("hard_qc_failures", hard_failures),
        ]
    )
    return pd.DataFrame(rows, columns=["metric", "value"])


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the complete l03 panel build."""
    started = utc_now()
    rf_specs, rf_audit = load_threshold_catalog(args.rf_threshold_spec_file, args.rf_threshold_audit_file, RF_SCOPE)
    cm_specs, cm_audit = load_threshold_catalog(args.cm_threshold_spec_file, args.cm_threshold_audit_file, CM_SCOPE)
    validate_common_catalog(rf_specs, cm_specs)
    rf_summary = validate_threshold_summary(args.rf_threshold_summary_file, RF_SCOPE, "run-x-c02-v3")
    cm_summary = validate_threshold_summary(args.cm_threshold_summary_file, CM_SCOPE, "run-x-c03-v1")
    scope_repos, c05_summary = derive_scope_sensitivity_repositories(args.c05_summary_file, args.c05_checks_file, args.c05_outside_scope_file)
    c05 = load_c05_file_table(args.c05_file)
    b06 = load_b06_panel(args.b06_panel_file)

    catalogs = {"rf": rf_specs, "cm": cm_specs}
    audits = {"rf": rf_audit, "cm": cm_audit}
    panel, global_audit, timing_audit, sample_summary, outcome_spec, scope_spec = build_outputs(
        c05, b06, catalogs, audits, scope_repos
    )
    checks = make_checks(panel, global_audit, sample_summary, catalogs, audits, c05, args.strict_expected_counts)
    hard_failures = int(checks["status"].eq("fail").sum())
    summary = build_summary(global_audit, sample_summary, panel, scope_repos, hard_failures)

    atomic_csv(panel, args.panel_output, compression="gzip")
    atomic_csv(global_audit, args.global_audit_output)
    atomic_csv(timing_audit, args.timing_audit_output)
    atomic_csv(sample_summary, args.sample_summary_output)
    atomic_csv(scope_spec, args.scope_sensitivity_output)
    atomic_csv(outcome_spec, args.outcome_spec_output)
    atomic_csv(checks, args.checks_output)
    atomic_csv(summary, args.summary_output)

    metadata = {
        "script_version": SCRIPT_VERSION,
        "started_utc": started,
        "completed_utc": utc_now(),
        "status": "PASS" if hard_failures == 0 else "FAIL",
        "inputs": {
            "c05_file": str(args.c05_file.resolve()),
            "c05_summary_file": str(args.c05_summary_file.resolve()),
            "c05_checks_file": str(args.c05_checks_file.resolve()),
            "c05_outside_scope_file": str(args.c05_outside_scope_file.resolve()),
            "b06_panel_file": str(args.b06_panel_file.resolve()),
            "rf_threshold_summary_file": str(args.rf_threshold_summary_file.resolve()),
            "rf_threshold_spec_file": str(args.rf_threshold_spec_file.resolve()),
            "rf_threshold_audit_file": str(args.rf_threshold_audit_file.resolve()),
            "cm_threshold_summary_file": str(args.cm_threshold_summary_file.resolve()),
            "cm_threshold_spec_file": str(args.cm_threshold_spec_file.resolve()),
            "cm_threshold_audit_file": str(args.cm_threshold_audit_file.resolve()),
        },
        "input_sha256": {
            "c05_file": sha256_file(args.c05_file),
            "c05_summary_file": sha256_file(args.c05_summary_file),
            "c05_checks_file": sha256_file(args.c05_checks_file),
            "c05_outside_scope_file": sha256_file(args.c05_outside_scope_file),
            "b06_panel_file": sha256_file(args.b06_panel_file),
            "rf_threshold_summary_file": sha256_file(args.rf_threshold_summary_file),
            "rf_threshold_spec_file": sha256_file(args.rf_threshold_spec_file),
            "rf_threshold_audit_file": sha256_file(args.rf_threshold_audit_file),
            "cm_threshold_summary_file": sha256_file(args.cm_threshold_summary_file),
            "cm_threshold_spec_file": sha256_file(args.cm_threshold_spec_file),
            "cm_threshold_audit_file": sha256_file(args.cm_threshold_audit_file),
        },
        "frozen_contracts": {
            "c02_status": rf_summary.get("status"),
            "c03_status": cm_summary.get("status"),
            "c05_status": c05_summary.get("status"),
            "comparison_operator": ">",
            "primary_threshold": PRIMARY_THRESHOLD,
            "legacy_threshold": LEGACY_THRESHOLD,
            "prior_primary_threshold": PRIOR_PRIMARY_THRESHOLD,
            "rf_metric": RF_SCOPE.metric,
            "cm_metric": CM_SCOPE.metric,
            "thresholds_per_scope": 23,
            "scope_sensitivity_repositories": scope_repos.to_dict(orient="records"),
        },
        "semantics": {
            "eligible_file": "finite scope-specific file NPR",
            "selected_file": "eligible file with scope-specific NPR strictly greater than the frozen threshold",
            "nonfinite_file": "unclassified for that localization scope; never interpreted as below-threshold/human",
            "quality_burden": "unresolved SonarQube issue stock on canonical C05-backed Python file paths",
            "density": "not computed because selected-file SonarQube NCLOC is not available",
            "causal_interpretation": "decomposition/mechanism outcome; NPR is not used as a regression control",
            "combined_scope": "not rebuilt in l03; frozen RF+CM panel remains run-x-l01-v2 and DiD remains run-x-l02-v1",
        },
        "hard_qc_failures": hard_failures,
    }
    atomic_json(metadata, args.metadata_output)

    print("=" * 88)
    print("run-x-l03 frozen RF/CM NPR threshold x SonarQube burden panels")
    print(f"Status:                                      {'PASS' if hard_failures == 0 else 'FAIL'}")
    print(f"Localization scopes:                         2 (RF, CM)")
    print(f"Thresholds per scope:                        23")
    print(f"Sample specifications per scope:             2")
    print(f"Long panel rows:                              {len(panel)}")
    print(f"Primary threshold:                            {PRIMARY_THRESHOLD}")
    for scope in SCOPES:
        full = global_audit[(global_audit['scope_id'].eq(scope.scope_id)) & (global_audit['sample_spec'].eq('full_sample'))].set_index('threshold_id')
        sens = global_audit[(global_audit['scope_id'].eq(scope.scope_id)) & (global_audit['sample_spec'].eq('exclude_scope_mismatch_repos'))].set_index('threshold_id')
        print(f"{scope.scope_label} primary selected files:                     {int(full.loc['primary', 'selected_file_rows'])}")
        print(f"{scope.scope_label} primary selected issue stock:               {int(full.loc['primary', 'selected_issue_total'])}")
        print(f"{scope.scope_label} sensitivity selected files:                 {int(sens.loc['primary', 'selected_file_rows'])}")
        print(f"{scope.scope_label} prior-primary selected files:               {int(full.loc['prior_primary_1571637', 'selected_file_rows'])}")
    print(f"Scope-sensitivity repositories:               {len(scope_repos)}")
    print("Density computed:                             0")
    print(f"Hard QC failures:                             {hard_failures}")
    print(f"Panel:                                        {args.panel_output}")
    print("=" * 88)

    if hard_failures:
        raise RuntimeError(f"l03 hard QC failures: {hard_failures}; see {args.checks_output}")
    return metadata


def run_self_test() -> None:
    """Test strict > behavior and scope-specific eligibility."""
    base_keys = pd.DataFrame({"repo_id": [1, 2], "time_index": [1, 1]})
    files = pd.DataFrame(
        {
            "repo_id": [1, 1, 2, 2],
            "time_index": [1, 1, 1, 1],
            "python_lines": [10, 10, 10, 10],
            RF_SCOPE.token_column: [5, 5, 5, 5],
            CM_SCOPE.token_column: [7, 7, 7, 7],
            RF_SCOPE.metric: [1.5, 1.6, np.nan, 2.0],
            CM_SCOPE.metric: [np.nan, 1.5, 1.6, 2.0],
            "sonar_issue_total": [3, 5, 7, 11],
            "sonar_issue_type_code_smell": [3, 5, 7, 11],
            "sonar_issue_type_bug": [0, 0, 0, 0],
            "sonar_issue_type_vulnerability": [0, 0, 0, 0],
            "sonar_issue_type_other": [0, 0, 0, 0],
            "sonar_issue_high_severity": [0, 0, 0, 0],
            "sonar_issue_with_maintainability_impact": [3, 5, 7, 11],
            "sonar_issue_with_reliability_impact": [0, 0, 0, 0],
            "sonar_issue_with_security_impact": [0, 0, 0, 0],
        }
    )
    rf = aggregate_one_threshold(files, 1.5, base_keys, RF_SCOPE).set_index(["repo_id", "time_index"])
    cm = aggregate_one_threshold(files, 1.5, base_keys, CM_SCOPE).set_index(["repo_id", "time_index"])
    assert int(rf.loc[(1, 1), "eligible_file_count"]) == 2
    assert int(rf.loc[(1, 1), "selected_file_count"]) == 1
    assert int(rf.loc[(1, 1), "selected_issue_total"]) == 5
    assert int(cm.loc[(1, 1), "eligible_file_count"]) == 1
    assert int(cm.loc[(1, 1), "selected_file_count"]) == 0
    assert int(cm.loc[(1, 1), "selected_issue_total"]) == 0
    assert int(cm.loc[(2, 1), "selected_issue_total"]) == 18
    print("build_sc2_npr_rf_cm_threshold_quality_burden_panel self-test: PASS")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build run-x-l03 frozen RF/CM NPR threshold-quality repo-month panels.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--c05-file", type=Path)
    parser.add_argument("--c05-summary-file", type=Path)
    parser.add_argument("--c05-checks-file", type=Path)
    parser.add_argument("--c05-outside-scope-file", type=Path)
    parser.add_argument("--b06-panel-file", type=Path)
    parser.add_argument("--rf-threshold-summary-file", type=Path)
    parser.add_argument("--rf-threshold-spec-file", type=Path)
    parser.add_argument("--rf-threshold-audit-file", type=Path)
    parser.add_argument("--cm-threshold-summary-file", type=Path)
    parser.add_argument("--cm-threshold-spec-file", type=Path)
    parser.add_argument("--cm-threshold-audit-file", type=Path)
    parser.add_argument("--panel-output", type=Path)
    parser.add_argument("--global-audit-output", type=Path)
    parser.add_argument("--timing-audit-output", type=Path)
    parser.add_argument("--sample-summary-output", type=Path)
    parser.add_argument("--scope-sensitivity-output", type=Path)
    parser.add_argument("--outcome-spec-output", type=Path)
    parser.add_argument("--checks-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--strict-expected-counts", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return args
    required = [
        "c05_file", "c05_summary_file", "c05_checks_file", "c05_outside_scope_file", "b06_panel_file",
        "rf_threshold_summary_file", "rf_threshold_spec_file", "rf_threshold_audit_file",
        "cm_threshold_summary_file", "cm_threshold_spec_file", "cm_threshold_audit_file",
        "panel_output", "global_audit_output", "timing_audit_output", "sample_summary_output",
        "scope_sensitivity_output", "outcome_spec_output", "checks_output", "summary_output", "metadata_output",
    ]
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("Missing required arguments: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    return args


def main() -> int:
    """Program entry point."""
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0
    try:
        run_pipeline(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
