#!/usr/bin/env python3
"""Build threshold-specific Quality x FUN+C_FUN-NPR repository-month burden panels.

This I04 experiment is a standalone adaptation of the validated D03 FUN-NPR
threshold-quality implementation. It does not call I04, rerun SonarQube, rescore
NPR, or choose thresholds from quality outcomes.

Frozen upstream contracts:
1. I02: outcome-blind FUN+C_FUN-NPR threshold specification and audit.
2. I03: I01-backed file-level FUN+C_FUN-NPR joined to unresolved SonarQube issue stock.
3. B06: authoritative 1,954-row Python SonarQube quality DiD base panel.

The I03 scope-exclusion artifact is also consumed deterministically. Repositories
with I03 issue-bearing Python files outside the frozen I01 NPR file universe are
identified before any DiD model is fit and used to construct a robustness sample:
    full_sample
    exclude_scope_mismatch_repos

The output is a long-format repository-month panel indexed by:
    sample_spec x threshold_id x repo_id x time_index

Only files with finite ``file_npr_fun_cfun_space_by_token_weighted`` are threshold
eligible. Files without finite FUN+C_FUN NPR are unclassified; they are never treated
as below-threshold or human-written files.

Quality outcomes are unresolved SonarQube issue stocks observed at historical
snapshots. Selected-file density is not computed because file-level SonarQube
NCLOC is not part of the frozen I03 input contract.
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
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCRIPT_VERSION = "run-x-i04-v1"
NPR_METRIC = "file_npr_fun_cfun_space_by_token_weighted"
PRIMARY_THRESHOLD = 1.571637
LEGACY_THRESHOLD = 1.5183
EXPECTED_THRESHOLD_COUNT = 22
EXPECTED_MAIN_GRID_COUNT = 21

I03_REQUIRED_COLUMNS = {
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
    "fun_cfun_space_by_tokens_scored",
    "fun_cfun_npr_coverage_ratio",
    NPR_METRIC,
    "file_npr_fun_cfun_status",
    "sonar_issue_total",
    "sonar_issue_type_code_smell",
    "sonar_issue_type_bug",
    "sonar_issue_type_vulnerability",
    "sonar_issue_type_other",
    "sonar_issue_high_severity",
    "sonar_issue_with_maintainability_impact",
    "sonar_issue_with_reliability_impact",
    "sonar_issue_with_security_impact",
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

THRESHOLD_AUDIT_REQUIRED = {
    "threshold_id",
    "threshold_role",
    "threshold",
    "comparison_operator",
    "eligible_finite_fun_cfun_rows",
    "selected_file_rows",
}

I03_OUTSIDE_REQUIRED = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "component_path",
    "exclusion_class",
    "sonar_issue_total",
}

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

LOG_OUTCOMES = [
    "selected_issue_total",
    "selected_issue_code_smell",
    "selected_issue_bug",
    "selected_issue_vulnerability",
    "selected_issue_high_severity",
    "selected_issue_maintainability_impact",
    "selected_issue_reliability_impact",
    "selected_issue_security_impact",
]

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
class ThresholdSpec:
    threshold_id: str
    threshold_role: str
    grid_order: int | None
    delta_from_primary: float
    threshold: float
    comparison_operator: str
    metric: str
    note: str


def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: Any) -> str:
    """Normalize text and missing values."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def bool_int(value: Any) -> int:
    """Normalize common Boolean encodings to 0/1."""
    text = clean(value).casefold()
    if text in {"1", "true", "t", "yes", "y"}:
        return 1
    if text in {"0", "false", "f", "no", "n", ""}:
        return 0
    raise ValueError(f"Unsupported Boolean value: {value!r}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Fail if required columns are missing."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def read_csv(path: Path, string_columns: Iterable[str] = ()) -> pd.DataFrame:
    """Read a CSV while preserving selected identity fields as strings."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    header = pd.read_csv(path, nrows=0)
    dtype = {column: "string" for column in string_columns if column in header.columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def read_metric_csv(path: Path) -> dict[str, str]:
    """Read a two-column metric/value CSV into a dictionary."""
    df = read_csv(path)
    if not {"metric", "value"}.issubset(df.columns):
        raise ValueError(f"Metric CSV missing metric/value columns: {path}")
    return {clean(row.metric): clean(row.value) for row in df.itertuples(index=False)}



def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value

def atomic_csv(df: pd.DataFrame, path: Path, compression: str | None = None) -> None:
    """Write a CSV atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".tmp.gz" if str(path).endswith(".gz") else ".tmp"
    tmp = Path(str(path) + suffix)
    df.to_csv(tmp, index=False, compression=compression)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    """Compute SHA256 for an input file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_check(
    rows: list[dict[str, Any]],
    check: str,
    observed: Any,
    expected: Any,
    passed: bool,
    detail: str = "",
) -> None:
    """Append one QC check row."""
    rows.append(
        {
            "check": check,
            "observed": observed,
            "expected": expected,
            "status": "pass" if passed else "fail",
            "detail": detail,
        }
    )


def load_thresholds(spec_path: Path, audit_path: Path) -> tuple[list[ThresholdSpec], pd.DataFrame]:
    """Load and validate the frozen I02 threshold contract."""
    spec = read_csv(spec_path, ["threshold_id", "threshold_role", "comparison_operator", "metric", "note"])
    audit = read_csv(audit_path, ["threshold_id", "threshold_role", "comparison_operator"])
    require_columns(spec, THRESHOLD_SPEC_REQUIRED, "I02 threshold specification")
    require_columns(audit, THRESHOLD_AUDIT_REQUIRED, "I02 threshold audit")

    if spec["threshold_id"].duplicated().any():
        raise ValueError("I02 threshold specification contains duplicate threshold_id values")
    if audit["threshold_id"].duplicated().any():
        raise ValueError("I02 threshold audit contains duplicate threshold_id values")

    rows: list[ThresholdSpec] = []
    for row in spec.itertuples(index=False):
        grid_order = pd.to_numeric(pd.Series([row.grid_order]), errors="coerce").iloc[0]
        rows.append(
            ThresholdSpec(
                threshold_id=clean(row.threshold_id),
                threshold_role=clean(row.threshold_role),
                grid_order=None if pd.isna(grid_order) else int(grid_order),
                delta_from_primary=float(row.delta_from_primary),
                threshold=float(row.threshold),
                comparison_operator=clean(row.comparison_operator),
                metric=clean(row.metric),
                note=clean(row.note),
            )
        )

    if len(rows) != EXPECTED_THRESHOLD_COUNT:
        raise ValueError(f"Expected {EXPECTED_THRESHOLD_COUNT} frozen thresholds, observed {len(rows)}")
    if any(item.comparison_operator != ">" for item in rows):
        raise ValueError("I04 requires the frozen strict '>' comparison operator")
    if any(item.metric != NPR_METRIC for item in rows):
        raise ValueError(f"I04 requires the frozen NPR metric {NPR_METRIC}")
    primary = [item for item in rows if item.threshold_role == "primary"]
    legacy = [item for item in rows if item.threshold_role == "legacy_anchor"]
    grid = [item for item in rows if item.threshold_role != "legacy_anchor"]
    if len(primary) != 1 or not math.isclose(primary[0].threshold, PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError("Frozen primary threshold is not 1.571637")
    if len(legacy) != 1 or not math.isclose(legacy[0].threshold, LEGACY_THRESHOLD, abs_tol=1e-12):
        raise ValueError("Frozen legacy threshold is not 1.5183")
    if len(grid) != EXPECTED_MAIN_GRID_COUNT:
        raise ValueError(f"Expected {EXPECTED_MAIN_GRID_COUNT} main-grid thresholds, observed {len(grid)}")

    audit_ids = set(audit["threshold_id"].map(clean))
    spec_ids = {item.threshold_id for item in rows}
    if audit_ids != spec_ids:
        raise ValueError("I02 threshold specification and threshold audit IDs do not match")
    return rows, audit


def validate_upstream_contracts(
    i02_summary_path: Path,
    i03_summary_path: Path,
    i03_outside_scope_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, str]]:
    """Validate the frozen I02/I03 gates and derive the scope-sensitivity repos."""
    i02 = read_json(i02_summary_path)
    i03 = read_metric_csv(i03_summary_path)

    if clean(i02.get("script_version")) != "run-x-i02-v1":
        raise ValueError(f"Unexpected I02 script version: {i02.get('script_version')}")
    if clean(i02.get("status")) != "PASS" or int(i02.get("hard_check_failures", -1)) != 0:
        raise ValueError("I02 threshold audit is not a clean PASS")
    if bool(i02.get("quality_outcome_inputs_consumed", True)):
        raise ValueError("I02 reports quality-outcome inputs were consumed")
    methodology = i02.get("methodology", {})
    if clean(methodology.get("metric")) != NPR_METRIC:
        raise ValueError("I02 metric does not match the I04 FUN+C_FUN NPR metric")
    if not math.isclose(float(methodology.get("primary_threshold")), PRIMARY_THRESHOLD, abs_tol=1e-12):
        raise ValueError("I02 primary threshold does not match the frozen value")

    if i03.get("script_version") != "run-x-i03-v1":
        raise ValueError(f"Unexpected I03 script version: {i03.get('script_version')}")
    if i03.get("status") != "PASS_WITH_SCOPE_EXCLUSIONS":
        raise ValueError(f"I03 status is not PASS_WITH_SCOPE_EXCLUSIONS: {i03.get('status')}")
    if i03.get("hard_qc_failures") != "0" or i03.get("threshold_applied") != "0" or i03.get("density_computed") != "0":
        raise ValueError("I03 summary does not satisfy the no-failure/no-threshold/no-density contract")
    if i03.get("npr_metric_preserved") != NPR_METRIC:
        raise ValueError("I03 did not preserve the expected FUN+C_FUN NPR metric")

    outside = read_csv(
        i03_outside_scope_path,
        ["snapshot_key", "dataset_source", "repo_name", "commit_sha", "component_path", "exclusion_class"],
    )
    require_columns(outside, I03_OUTSIDE_REQUIRED, "I03 outside-I01 scope exclusions")
    if outside.empty:
        raise ValueError("I03 outside-I01 scope exclusion file is unexpectedly empty")
    if not outside["exclusion_class"].map(clean).eq("outside_i01_npr_file_universe").all():
        raise ValueError("Unexpected I03 scope exclusion class")
    outside["sonar_issue_total"] = pd.to_numeric(outside["sonar_issue_total"], errors="coerce")
    if outside["sonar_issue_total"].isna().any() or (outside["sonar_issue_total"] < 0).any():
        raise ValueError("I03 outside-scope issue totals must be complete and non-negative")

    scope_repos = (
        outside[["dataset_source", "repo_name"]]
        .assign(
            dataset_source=lambda x: x["dataset_source"].map(clean).str.casefold(),
            repo_name=lambda x: x["repo_name"].map(clean),
        )
        .drop_duplicates()
        .sort_values(["dataset_source", "repo_name"], kind="stable")
        .reset_index(drop=True)
    )
    return scope_repos, i02, i03

def load_i03_file_table(path: Path) -> pd.DataFrame:
    """Load only the I03 columns needed for I04."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, I03_REQUIRED_COLUMNS, "I03 file-quality table")
    usecols = sorted(I03_REQUIRED_COLUMNS)
    string_columns = {
        "dataset_source",
        "repo_name",
        "repo_month",
        "event",
        "snapshot_id",
        "snapshot_commit",
        "relative_path",
        "file_npr_fun_cfun_status",
    }
    dtype = {column: "string" for column in string_columns}
    data = pd.read_csv(path, usecols=usecols, dtype=dtype, low_memory=False)

    data["dataset_source"] = data["dataset_source"].map(clean).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean)
    data["repo_month"] = data["repo_month"].map(clean)
    data["snapshot_id"] = data["snapshot_id"].map(clean)
    data["snapshot_commit"] = data["snapshot_commit"].map(clean).str.casefold()
    data["relative_path"] = data["relative_path"].map(clean)
    for column in [
        "repo_id", "time_index", "event_index", "python_lines",
        "fun_cfun_space_by_tokens_scored", "fun_cfun_npr_coverage_ratio", NPR_METRIC,
        *ISSUE_COLUMNS,
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[["repo_id", "time_index"]].isna().any().any():
        raise ValueError("I03 repo_id/time_index contains missing numeric values")
    for column in ISSUE_COLUMNS:
        if data[column].isna().any() or (data[column] < 0).any():
            raise ValueError(f"I03 issue column must be complete non-negative: {column}")
        data[column] = data[column].astype("int64")
    data["repo_id"] = data["repo_id"].astype("int64")
    data["time_index"] = data["time_index"].astype("int64")
    return data

def load_b06_panel(path: Path) -> pd.DataFrame:
    """Load the authoritative 1,954-row B06 analysis base."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, B06_REQUIRED_COLUMNS, "B06 quality panel")
    string_columns = [
        "repo_name",
        "dataset_source",
        "scope_role",
        "time",
        "event",
        "latest_commit_effective",
        "snapshot_key",
        "quality_scope",
        "quality_count_semantics",
        "quality_metric_version",
    ]
    data = read_csv(path, string_columns)
    data["dataset_source"] = data["dataset_source"].map(clean).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean)
    data["time"] = data["time"].map(clean)
    data["latest_commit_effective"] = data["latest_commit_effective"].map(clean).str.casefold()
    data["snapshot_key"] = data["snapshot_key"].map(clean)
    for column in ["repo_id", "treatment_group", "time_index", "event_index", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[["repo_id", "treatment_group", "time_index", "event_index", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"]].isna().any().any():
        raise ValueError("B06 required numeric/model fields contain missing values")
    data["repo_id"] = data["repo_id"].astype("int64")
    data["treatment_group"] = data["treatment_group"].astype("int64")
    data["time_index"] = data["time_index"].astype("int64")
    data["event_index"] = data["event_index"].astype("int64")
    if data.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("B06 panel contains duplicate repo_id/time_index rows")
    if not pd.Series(data["quality_did_complete"]).map(bool_int).eq(1).all():
        raise ValueError("B06 quality_did_complete is not 1 for all rows")
    if not data["quality_scope"].map(clean).eq("python_only_sonar_inclusions").all():
        raise ValueError("B06 quality_scope mismatch")
    if not data["quality_count_semantics"].map(clean).eq("unresolved_issue_stock_at_historical_snapshot").all():
        raise ValueError("B06 quality count semantics mismatch")
    return data


def validate_repo_month_identity(i03: pd.DataFrame, b06: pd.DataFrame) -> pd.DataFrame:
    """Validate that I03 and B06 describe the same 1,954 repo-month observations."""
    identity_cols = [
        "repo_id",
        "time_index",
        "dataset_source",
        "repo_name",
        "repo_month",
        "event",
        "event_index",
        "snapshot_id",
        "snapshot_commit",
    ]
    grouped = i03[identity_cols].drop_duplicates()
    dup_key = grouped.duplicated(["repo_id", "time_index"], keep=False)
    if dup_key.any():
        raise ValueError("I03 has inconsistent repo-month identity within repo_id/time_index")

    right = b06[["repo_id", "time_index", "dataset_source", "repo_name", "time", "event", "event_index", "snapshot_key", "latest_commit_effective"]].copy()
    merged = right.merge(grouped, on=["repo_id", "time_index"], how="outer", suffixes=("_b06", "_i03"), indicator=True, validate="one_to_one")
    if not merged["_merge"].eq("both").all():
        raise ValueError("I03/B06 repo-month key universes do not match")
    comparisons = {
        "dataset_source": merged["dataset_source_b06"].map(clean).str.casefold().eq(merged["dataset_source_i03"].map(clean).str.casefold()),
        "repo_name": merged["repo_name_b06"].map(clean).str.casefold().eq(merged["repo_name_i03"].map(clean).str.casefold()),
        "time": merged["time"].map(clean).eq(merged["repo_month"].map(clean)),
        "event": merged["event_b06"].map(clean).eq(merged["event_i03"].map(clean)),
        "event_index": pd.to_numeric(merged["event_index_b06"], errors="coerce").eq(pd.to_numeric(merged["event_index_i03"], errors="coerce")),
        "snapshot_key": merged["snapshot_key"].map(clean).eq(merged["snapshot_id"].map(clean)),
        "commit": merged["latest_commit_effective"].map(clean).str.casefold().eq(merged["snapshot_commit"].map(clean).str.casefold()),
    }
    failures = {name: int((~mask).sum()) for name, mask in comparisons.items()}
    if any(failures.values()):
        raise ValueError(f"I03/B06 identity mismatches: {failures}")
    return grouped


def normalized_timing(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the authoritative normalized treatment timing fields."""
    data = panel.copy()
    data["event_time_normalized"] = np.where(
        data["treatment_group"].eq(1),
        data["time_index"] - data["event_index"],
        np.nan,
    )
    data["absorbing_treated"] = (
        data["treatment_group"].eq(1)
        & data["event_index"].gt(0)
        & data["time_index"].ge(data["event_index"])
    ).astype("int64")
    return data


def aggregate_one_threshold(files: pd.DataFrame, threshold: float, base_keys: pd.DataFrame) -> pd.DataFrame:
    """Aggregate one frozen threshold from file rows to repo-month burden rows."""
    metric = pd.to_numeric(files[NPR_METRIC], errors="coerce")
    eligible = np.isfinite(metric.to_numpy(dtype=float))
    selected = eligible & metric.gt(threshold).to_numpy(dtype=bool)

    work = files[["repo_id", "time_index", "python_lines", "fun_cfun_space_by_tokens_scored", "sonar_issue_total", *[c for c in ISSUE_COLUMNS if c != "sonar_issue_total"]]].copy()
    work["eligible_fun_cfun_file_count"] = eligible.astype("int64")
    work["selected_file_count"] = selected.astype("int64")
    work["selected_file_with_any_issue_count"] = (selected & files["sonar_issue_total"].gt(0).to_numpy(dtype=bool)).astype("int64")
    work["selected_python_lines"] = pd.to_numeric(work["python_lines"], errors="coerce").fillna(0).where(selected, 0)
    work["selected_fun_cfun_space_by_tokens"] = pd.to_numeric(work["fun_cfun_space_by_tokens_scored"], errors="coerce").fillna(0).where(selected, 0)
    for column in ISSUE_COLUMNS:
        work[column] = work[column].where(selected, 0)

    agg_map: dict[str, str] = {
        "eligible_fun_cfun_file_count": "sum",
        "selected_file_count": "sum",
        "selected_file_with_any_issue_count": "sum",
        "selected_python_lines": "sum",
        "selected_fun_cfun_space_by_tokens": "sum",
    }
    agg_map.update({column: "sum" for column in ISSUE_COLUMNS})
    grouped = work.groupby(["repo_id", "time_index"], as_index=False).agg(agg_map)
    grouped = grouped.rename(columns=OUTCOME_RENAME)
    grouped["selected_issue_free_file_count"] = grouped["selected_file_count"] - grouped["selected_file_with_any_issue_count"]
    grouped["selected_file_share_of_eligible"] = np.where(
        grouped["eligible_fun_cfun_file_count"].gt(0),
        grouped["selected_file_count"] / grouped["eligible_fun_cfun_file_count"],
        np.nan,
    )
    grouped["has_eligible_fun_cfun_files"] = grouped["eligible_fun_cfun_file_count"].gt(0).astype("int64")
    grouped["has_selected_files"] = grouped["selected_file_count"].gt(0).astype("int64")
    grouped["has_selected_issue_burden"] = grouped["selected_issue_total"].gt(0).astype("int64")
    for column in LOG_OUTCOMES:
        grouped[f"log1p_{column}"] = np.log1p(grouped[column].astype(float))

    output = base_keys.merge(grouped, on=["repo_id", "time_index"], how="left", validate="one_to_one")
    count_columns = [
        "eligible_fun_cfun_file_count",
        "selected_file_count",
        "selected_file_with_any_issue_count",
        "selected_issue_free_file_count",
        "selected_python_lines",
        "selected_fun_cfun_space_by_tokens",
        "selected_issue_total",
        "selected_issue_code_smell",
        "selected_issue_bug",
        "selected_issue_vulnerability",
        "selected_issue_other",
        "selected_issue_high_severity",
        "selected_issue_maintainability_impact",
        "selected_issue_reliability_impact",
        "selected_issue_security_impact",
        "has_eligible_fun_cfun_files",
        "has_selected_files",
        "has_selected_issue_burden",
    ]
    for column in count_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    for column in LOG_OUTCOMES:
        log_col = f"log1p_{column}"
        output[log_col] = pd.to_numeric(output[log_col], errors="coerce").fillna(0.0)
    output["selected_file_share_of_eligible"] = np.where(
        output["eligible_fun_cfun_file_count"].gt(0),
        output["selected_file_count"] / output["eligible_fun_cfun_file_count"],
        np.nan,
    )
    return output


def sample_stratum(panel: pd.DataFrame) -> pd.Series:
    """Return normalized descriptive treatment-timing strata."""
    treatment = panel["treatment_group"].eq(1)
    post = panel["absorbing_treated"].eq(1)
    return pd.Series(
        np.select(
            [~treatment, treatment & ~post, treatment & post],
            ["control", "treatment_pre", "treatment_post"],
            default="unknown",
        ),
        index=panel.index,
        dtype="string",
    )


def build_outputs(
    i03: pd.DataFrame,
    b06: pd.DataFrame,
    specs: list[ThresholdSpec],
    i02_audit: pd.DataFrame,
    scope_repos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the long I04 panel and audit outputs."""
    validate_repo_month_identity(i03, b06)
    base = normalized_timing(b06[BASE_PANEL_COLUMNS].copy())
    base_keys = base[["repo_id", "time_index"]].copy()

    exclude_repos = {clean(value).casefold() for value in scope_repos["repo_name"]}
    sample_specs = {
        "full_sample": base,
        "exclude_scope_mismatch_repos": base[
            ~base["repo_name"].map(clean).str.casefold().isin(exclude_repos)
        ].copy(),
    }

    scope_spec = scope_repos.copy()
    scope_spec.insert(0, "sample_spec", "exclude_scope_mismatch_repos")
    scope_spec["exclude_repository"] = 1
    scope_spec["frozen_before_did"] = 1
    scope_spec["reason"] = (
        "I03 contains issue-bearing Python file paths outside the frozen I01 FUN+C_FUN NPR file universe; "
        "exclude the affected repository as a scope-sensitivity analysis."
    )

    audit_by_id = i02_audit.set_index(i02_audit["threshold_id"].map(clean), drop=False)
    panel_parts: list[pd.DataFrame] = []
    global_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []

    for spec in specs:
        aggregated = aggregate_one_threshold(i03, spec.threshold, base_keys)
        full = base.merge(aggregated.drop(columns=["repo_id", "time_index"]), left_index=True, right_index=True)
        if not full[["repo_id", "time_index"]].equals(base[["repo_id", "time_index"]]):
            raise ValueError("Internal I04 aggregation order mismatch")

        for sample_name, sample_base in sample_specs.items():
            if sample_name == "full_sample":
                sample = full.copy()
            else:
                keys = sample_base[["repo_id", "time_index"]]
                sample = full.merge(keys, on=["repo_id", "time_index"], how="inner", validate="one_to_one")
                sample = sample.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)

            sample.insert(0, "sample_spec", sample_name)
            sample.insert(1, "threshold_id", spec.threshold_id)
            sample.insert(2, "threshold_role", spec.threshold_role)
            sample.insert(3, "grid_order", "" if spec.grid_order is None else spec.grid_order)
            sample.insert(4, "delta_from_primary", spec.delta_from_primary)
            sample.insert(5, "threshold", spec.threshold)
            sample.insert(6, "comparison_operator", spec.comparison_operator)
            sample.insert(7, "npr_metric", spec.metric)
            sample.insert(8, "quality_scope", "canonical_i01_python_files_with_finite_fun_cfun_npr")
            sample.insert(9, "quality_count_semantics", "unresolved_sonarqube_issue_stock_at_historical_snapshot")
            sample.insert(10, "density_computed", 0)
            sample["timing_stratum"] = sample_stratum(sample)
            panel_parts.append(sample)

            selected_files = int(sample["selected_file_count"].sum())
            eligible_files = int(sample["eligible_fun_cfun_file_count"].sum())
            global_rows.append(
                {
                    "sample_spec": sample_name,
                    "threshold_id": spec.threshold_id,
                    "threshold_role": spec.threshold_role,
                    "grid_order": "" if spec.grid_order is None else spec.grid_order,
                    "delta_from_primary": spec.delta_from_primary,
                    "threshold": spec.threshold,
                    "comparison_operator": spec.comparison_operator,
                    "repo_month_rows": len(sample),
                    "repositories": sample["repo_id"].nunique(),
                    "eligible_fun_cfun_file_rows": eligible_files,
                    "selected_file_rows": selected_files,
                    "selected_share_of_eligible": selected_files / eligible_files if eligible_files else np.nan,
                    "repo_months_with_selected_files": int(sample["has_selected_files"].sum()),
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

            timing_groups: list[tuple[str, pd.DataFrame]] = [
                ("all", sample),
                ("control", sample[sample["timing_stratum"].eq("control")]),
                ("treatment_all", sample[sample["treatment_group"].eq(1)]),
                ("treatment_pre", sample[sample["timing_stratum"].eq("treatment_pre")]),
                ("treatment_post", sample[sample["timing_stratum"].eq("treatment_post")]),
            ]
            for stratum, group in timing_groups:
                eligible = int(group["eligible_fun_cfun_file_count"].sum())
                selected_count = int(group["selected_file_count"].sum())
                timing_rows.append(
                    {
                        "sample_spec": sample_name,
                        "threshold_id": spec.threshold_id,
                        "threshold_role": spec.threshold_role,
                        "threshold": spec.threshold,
                        "timing_stratum": stratum,
                        "repo_month_rows": len(group),
                        "repositories": group["repo_id"].nunique(),
                        "eligible_fun_cfun_file_rows": eligible,
                        "selected_file_rows": selected_count,
                        "selected_share_of_eligible": selected_count / eligible if eligible else np.nan,
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

    sample_summary_rows: list[dict[str, Any]] = []
    for sample_name, sample in sample_specs.items():
        normalized = normalized_timing(sample)
        sample_summary_rows.append(
            {
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
    sample_summary = pd.DataFrame(sample_summary_rows)

    outcome_spec = pd.DataFrame(
        [
            {"outcome": "log1p_selected_issue_total", "role": "primary_burden", "count_column": "selected_issue_total", "description": "log1p unresolved SonarQube issue stock in finite FUN+C_FUN NPR files exceeding the frozen threshold"},
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
    specs: list[ThresholdSpec],
    i02_audit: pd.DataFrame,
    i03: pd.DataFrame,
    strict: bool,
    expected_rows: int,
    expected_repos: int,
    expected_treatment_repos: int,
    expected_control_repos: int,
    expected_untreated_rows: int,
    expected_treated_rows: int,
    expected_dynamic_rows: int,
    expected_i03_rows: int,
    expected_finite_rows: int,
    expected_scope_repos: int,
    expected_scope_rows: int,
    expected_primary_selected_files: int,
    expected_primary_selected_issues: int,
    expected_primary_selected_code_smell: int,
    expected_primary_sensitivity_selected_files: int,
    expected_primary_sensitivity_selected_issues: int,
) -> pd.DataFrame:
    """Construct strong structural and accounting checks for I04."""
    rows: list[dict[str, Any]] = []
    full_summary = sample_summary.set_index("sample_spec").loc["full_sample"]
    add_check(rows, "threshold_count", len(specs), EXPECTED_THRESHOLD_COUNT, len(specs) == EXPECTED_THRESHOLD_COUNT)
    add_check(rows, "i03_file_rows", len(i03), expected_i03_rows, (len(i03) == expected_i03_rows) or not strict)
    finite = int(np.isfinite(pd.to_numeric(i03[NPR_METRIC], errors="coerce").to_numpy(dtype=float)).sum())
    add_check(rows, "i03_finite_fun_cfun_rows", finite, expected_finite_rows, (finite == expected_finite_rows) or not strict)
    add_check(rows, "full_sample_repo_month_rows", int(full_summary["repo_month_rows"]), expected_rows, (int(full_summary["repo_month_rows"]) == expected_rows) or not strict)
    add_check(rows, "full_sample_repositories", int(full_summary["repositories"]), expected_repos, (int(full_summary["repositories"]) == expected_repos) or not strict)
    add_check(rows, "full_sample_treatment_repositories", int(full_summary["treatment_repositories"]), expected_treatment_repos, (int(full_summary["treatment_repositories"]) == expected_treatment_repos) or not strict)
    add_check(rows, "full_sample_control_repositories", int(full_summary["control_repositories"]), expected_control_repos, (int(full_summary["control_repositories"]) == expected_control_repos) or not strict)
    add_check(rows, "full_sample_untreated_rows", int(full_summary["untreated_first_stage_rows"]), expected_untreated_rows, (int(full_summary["untreated_first_stage_rows"]) == expected_untreated_rows) or not strict)
    add_check(rows, "full_sample_treated_rows", int(full_summary["treatment_post_rows"]), expected_treated_rows, (int(full_summary["treatment_post_rows"]) == expected_treated_rows) or not strict)
    add_check(rows, "full_sample_dynamic_0_6_rows", int(full_summary["dynamic_event_0_to_6_rows"]), expected_dynamic_rows, (int(full_summary["dynamic_event_0_to_6_rows"]) == expected_dynamic_rows) or not strict)

    expected_panel_rows = int(sample_summary["repo_month_rows"].sum()) * len(specs)
    add_check(rows, "long_panel_row_count", len(panel), expected_panel_rows, len(panel) == expected_panel_rows)
    duplicate_keys = int(panel.duplicated(["sample_spec", "threshold_id", "repo_id", "time_index"]).sum())
    add_check(rows, "long_panel_duplicate_keys", duplicate_keys, 0, duplicate_keys == 0)

    i02 = i02_audit.set_index(i02_audit["threshold_id"].map(clean), drop=False)
    full_global = global_audit[global_audit["sample_spec"].eq("full_sample")].set_index("threshold_id")
    mismatch_count = 0
    for spec in specs:
        observed_selected = int(full_global.loc[spec.threshold_id, "selected_file_rows"])
        expected_selected = int(pd.to_numeric(i02.loc[spec.threshold_id, "selected_file_rows"]))
        expected_eligible = int(pd.to_numeric(i02.loc[spec.threshold_id, "eligible_finite_fun_cfun_rows"]))
        observed_eligible = int(full_global.loc[spec.threshold_id, "eligible_fun_cfun_file_rows"])
        mismatch_count += int(observed_selected != expected_selected or observed_eligible != expected_eligible)
    add_check(rows, "i02_selected_and_eligible_counts_reconcile_all_thresholds", mismatch_count, 0, mismatch_count == 0)

    for sample_name in global_audit["sample_spec"].unique():
        group = global_audit[(global_audit["sample_spec"].eq(sample_name)) & (~global_audit["threshold_role"].eq("legacy_anchor"))].sort_values("threshold")
        for column in ["selected_file_rows", "selected_issue_total", "selected_issue_code_smell", "selected_issue_bug", "selected_issue_vulnerability", "selected_issue_high_severity"]:
            values = group[column].to_numpy(dtype=float)
            violations = int(np.sum(np.diff(values) > 0))
            add_check(rows, f"monotonic_nonincreasing::{sample_name}::{column}", violations, 0, violations == 0)

    negative_outcomes = 0
    for column in [c for c in panel.columns if c.startswith("selected_issue_") and not c.endswith("file_count")]:
        numeric = pd.to_numeric(panel[column], errors="coerce")
        negative_outcomes += int((numeric < 0).sum())
    add_check(rows, "negative_selected_issue_values", negative_outcomes, 0, negative_outcomes == 0)

    log_mismatches = 0
    for column in LOG_OUTCOMES:
        expected = np.log1p(pd.to_numeric(panel[column], errors="coerce").astype(float))
        observed = pd.to_numeric(panel[f"log1p_{column}"], errors="coerce").astype(float)
        log_mismatches += int((~np.isclose(expected, observed, rtol=0, atol=1e-12, equal_nan=True)).sum())
    add_check(rows, "log1p_outcome_recomputation_mismatches", log_mismatches, 0, log_mismatches == 0)

    excluded = sample_summary.set_index("sample_spec").loc["exclude_scope_mismatch_repos"]
    excluded_count = int(excluded["excluded_repository_count"])
    add_check(rows, "scope_sensitivity_repositories_excluded", excluded_count, expected_scope_repos, (excluded_count == expected_scope_repos) or not strict)
    excluded_rows = int(excluded["repo_month_rows"])
    add_check(rows, "scope_sensitivity_repo_month_rows", excluded_rows, expected_scope_rows, (excluded_rows == expected_scope_rows) or not strict)

    primary = full_global.loc["primary"]
    add_check(rows, "primary_threshold_exact", float(primary["threshold"]), PRIMARY_THRESHOLD, math.isclose(float(primary["threshold"]), PRIMARY_THRESHOLD, abs_tol=1e-12))
    add_check(rows, "primary_full_selected_file_rows", int(primary["selected_file_rows"]), expected_primary_selected_files, (int(primary["selected_file_rows"]) == expected_primary_selected_files) or not strict)
    add_check(rows, "primary_full_selected_issue_total", int(primary["selected_issue_total"]), expected_primary_selected_issues, (int(primary["selected_issue_total"]) == expected_primary_selected_issues) or not strict)
    add_check(rows, "primary_full_selected_code_smell", int(primary["selected_issue_code_smell"]), expected_primary_selected_code_smell, (int(primary["selected_issue_code_smell"]) == expected_primary_selected_code_smell) or not strict)
    sensitivity_global = global_audit[global_audit["sample_spec"].eq("exclude_scope_mismatch_repos")].set_index("threshold_id")
    primary_sensitivity = sensitivity_global.loc["primary"]
    add_check(rows, "primary_sensitivity_selected_file_rows", int(primary_sensitivity["selected_file_rows"]), expected_primary_sensitivity_selected_files, (int(primary_sensitivity["selected_file_rows"]) == expected_primary_sensitivity_selected_files) or not strict)
    add_check(rows, "primary_sensitivity_selected_issue_total", int(primary_sensitivity["selected_issue_total"]), expected_primary_sensitivity_selected_issues, (int(primary_sensitivity["selected_issue_total"]) == expected_primary_sensitivity_selected_issues) or not strict)
    legacy = full_global.loc["legacy_15183"]
    add_check(rows, "legacy_threshold_exact", float(legacy["threshold"]), LEGACY_THRESHOLD, math.isclose(float(legacy["threshold"]), LEGACY_THRESHOLD, abs_tol=1e-12))
    return pd.DataFrame(rows)

def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the I04 build."""
    started = utc_now()
    specs, i02_audit = load_thresholds(args.threshold_spec_file, args.threshold_audit_file)
    scope_repos, i02_summary, i03_summary = validate_upstream_contracts(
        args.i02_summary_file,
        args.i03_summary_file,
        args.i03_outside_scope_file,
    )
    i03 = load_i03_file_table(args.i03_file)
    b06 = load_b06_panel(args.b06_panel_file)

    panel, global_audit, timing_audit, sample_summary, outcome_spec, scope_spec = build_outputs(
        i03, b06, specs, i02_audit, scope_repos
    )
    checks = make_checks(
        panel,
        global_audit,
        sample_summary,
        specs,
        i02_audit,
        i03,
        args.strict_expected_counts,
        args.expected_panel_rows,
        args.expected_repositories,
        args.expected_treatment_repositories,
        args.expected_control_repositories,
        args.expected_untreated_rows,
        args.expected_treated_rows,
        args.expected_dynamic_rows,
        args.expected_i03_rows,
        args.expected_finite_fun_cfun_rows,
        args.expected_scope_repositories,
        args.expected_scope_repo_month_rows,
        args.expected_primary_selected_files,
        args.expected_primary_selected_issues,
        args.expected_primary_selected_code_smell,
        args.expected_primary_sensitivity_selected_files,
        args.expected_primary_sensitivity_selected_issues,
    )
    hard_failures = int(checks["status"].eq("fail").sum())

    atomic_csv(panel, args.panel_output, compression="gzip")
    atomic_csv(global_audit, args.global_audit_output)
    atomic_csv(timing_audit, args.timing_audit_output)
    atomic_csv(sample_summary, args.sample_summary_output)
    atomic_csv(scope_spec, args.scope_sensitivity_output)
    atomic_csv(outcome_spec, args.outcome_spec_output)
    atomic_csv(checks, args.checks_output)

    primary_rows = global_audit[global_audit["threshold_id"].eq("primary")].copy()
    primary_full = primary_rows[primary_rows["sample_spec"].eq("full_sample")].iloc[0]
    primary_sens = primary_rows[primary_rows["sample_spec"].eq("exclude_scope_mismatch_repos")].iloc[0]
    summary_rows = [
        ("script_version", SCRIPT_VERSION),
        ("status", "PASS" if hard_failures == 0 else "FAIL"),
        ("npr_metric", NPR_METRIC),
        ("quality_semantics", "unresolved_sonarqube_issue_stock_at_historical_snapshot"),
        ("thresholds", len(specs)),
        ("sample_specs", sample_summary["sample_spec"].nunique()),
        ("full_sample_repo_month_rows", int(sample_summary.set_index("sample_spec").loc["full_sample", "repo_month_rows"])),
        ("scope_sensitivity_repo_month_rows", int(sample_summary.set_index("sample_spec").loc["exclude_scope_mismatch_repos", "repo_month_rows"])),
        ("long_panel_rows", len(panel)),
        ("primary_threshold", PRIMARY_THRESHOLD),
        ("primary_full_selected_file_rows", int(primary_full["selected_file_rows"])),
        ("primary_full_selected_issue_total", int(primary_full["selected_issue_total"])),
        ("primary_full_selected_code_smell", int(primary_full["selected_issue_code_smell"])),
        ("primary_sensitivity_selected_file_rows", int(primary_sens["selected_file_rows"])),
        ("primary_sensitivity_selected_issue_total", int(primary_sens["selected_issue_total"])),
        ("density_computed", 0),
        ("scope_sensitivity_repositories", len(scope_repos)),
        ("i03_outside_scope_file_rows", int(pd.to_numeric(read_metric_csv(args.i03_summary_file).get("b05_issue_bearing_snapshot_files_outside_i01", "0")))),
        ("hard_qc_failures", hard_failures),
    ]
    summary = pd.DataFrame(summary_rows, columns=["metric", "value"])
    atomic_csv(summary, args.summary_output)

    metadata = {
        "script_version": SCRIPT_VERSION,
        "started_utc": started,
        "completed_utc": utc_now(),
        "status": "PASS" if hard_failures == 0 else "FAIL",
        "inputs": {
            "i03_file": str(args.i03_file.resolve()),
            "i03_summary_file": str(args.i03_summary_file.resolve()),
            "i03_outside_scope_file": str(args.i03_outside_scope_file.resolve()),
            "b06_panel_file": str(args.b06_panel_file.resolve()),
            "i02_summary_file": str(args.i02_summary_file.resolve()),
            "threshold_spec_file": str(args.threshold_spec_file.resolve()),
            "threshold_audit_file": str(args.threshold_audit_file.resolve()),
        },
        "input_sha256": {
            "i03_file": sha256_file(args.i03_file),
            "i03_summary_file": sha256_file(args.i03_summary_file),
            "i03_outside_scope_file": sha256_file(args.i03_outside_scope_file),
            "b06_panel_file": sha256_file(args.b06_panel_file),
            "i02_summary_file": sha256_file(args.i02_summary_file),
            "threshold_spec_file": sha256_file(args.threshold_spec_file),
            "threshold_audit_file": sha256_file(args.threshold_audit_file),
        },
        "frozen_contracts": {
            "i02_status": clean(i02_summary.get("status")),
            "i03_status": i03_summary.get("status"),
            "comparison_operator": ">",
            "primary_threshold": PRIMARY_THRESHOLD,
            "legacy_threshold": LEGACY_THRESHOLD,
            "threshold_metric": NPR_METRIC,
            "scope_sensitivity_repositories": scope_repos.to_dict(orient="records"),
        },
        "semantics": {
            "eligible_file": "finite file_npr_fun_cfun_space_by_token_weighted",
            "selected_file": "eligible file with NPR strictly greater than the frozen I02 threshold",
            "nonfinite_file": "unclassified; never interpreted as below-threshold/human",
            "quality_burden": "unresolved SonarQube issue stock on canonical I01-backed Python file paths",
            "density": "not computed because selected-file SonarQube NCLOC is not available",
            "causal_interpretation": "decomposition/mechanism outcome; NPR may be post-treatment and is not a regression control",
        },
        "hard_qc_failures": hard_failures,
    }
    atomic_json(metadata, args.metadata_output)

    print("=" * 80)
    print("run-x-i04 frozen FUN+C_FUN-NPR threshold x SonarQube burden panel")
    print(f"Status:                                  {'PASS' if hard_failures == 0 else 'FAIL'}")
    print(f"Thresholds:                              {len(specs)}")
    print(f"Sample specifications:                   {sample_summary['sample_spec'].nunique()}")
    print(f"Full-sample repo-month rows:              {int(sample_summary.set_index('sample_spec').loc['full_sample', 'repo_month_rows'])}")
    print(f"Scope-sensitivity repo-month rows:        {int(sample_summary.set_index('sample_spec').loc['exclude_scope_mismatch_repos', 'repo_month_rows'])}")
    print(f"Long panel rows:                          {len(panel)}")
    print(f"Primary threshold:                        {PRIMARY_THRESHOLD}")
    print(f"Primary full selected files:              {int(primary_full['selected_file_rows'])}")
    print(f"Primary full selected issue stock:        {int(primary_full['selected_issue_total'])}")
    print(f"Primary full selected code-smell stock:   {int(primary_full['selected_issue_code_smell'])}")
    print(f"Primary sensitivity selected files:       {int(primary_sens['selected_file_rows'])}")
    print(f"Primary sensitivity selected issue stock: {int(primary_sens['selected_issue_total'])}")
    print(f"Scope-sensitivity repositories:           {len(scope_repos)}")
    print("Density computed:                         0")
    print(f"Hard QC failures:                         {hard_failures}")
    print(f"Panel:                                    {args.panel_output}")
    print("=" * 80)

    if hard_failures:
        raise RuntimeError(f"I04 hard QC failures: {hard_failures}; see {args.checks_output}")
    return metadata

def run_self_test() -> None:
    """Exercise strict-threshold, zero-selection, and FUN+C_FUN aggregation logic."""
    base = pd.DataFrame(
        {
            "repo_id": [1, 1, 2, 2],
            "repo_name": ["c/repo", "c/repo", "t/repo", "t/repo"],
            "dataset_source": ["control", "control", "treatment", "treatment"],
            "scope_role": ["control", "control", "treatment", "treatment"],
            "treatment_group": [0, 0, 1, 1],
            "time": ["2025-01", "2025-02", "2025-01", "2025-02"],
            "time_index": [1, 2, 1, 2],
            "event": ["", "", "2025-02", "2025-02"],
            "event_index": [0, 0, 2, 2],
            "time_to_event": [np.nan, np.nan, -1, 0],
            "is_treatment": [0, 0, 0, 1],
            "post_event": [0, 0, 0, 1],
            "cursor": [0, 0, 0, 1],
            "latest_commit_effective": ["a", "b", "c", "d"],
            "snapshot_key": ["s1", "s2", "s3", "s4"],
            "log_age": [1.0] * 4,
            "ncloc_py_sonarqube": [100.0] * 4,
            "log_contributors": [1.0] * 4,
            "log_stars": [1.0] * 4,
            "log_issues": [1.0] * 4,
        }
    )
    file_rows = []
    values = {
        (1, 1): [(1.0, 2), (1.5, 3), (np.nan, 9)],
        (1, 2): [(2.0, 5)],
        (2, 1): [(1.6, 7)],
        (2, 2): [(1.4, 11)],
    }
    for row in base.itertuples(index=False):
        for idx, (npr, issues) in enumerate(values[(row.repo_id, row.time_index)]):
            file_rows.append(
                {
                    "repo_id": row.repo_id,
                    "dataset_source": row.dataset_source,
                    "repo_name": row.repo_name,
                    "repo_month": row.time,
                    "time_index": row.time_index,
                    "event": row.event,
                    "event_index": row.event_index,
                    "snapshot_id": row.snapshot_key,
                    "snapshot_commit": row.latest_commit_effective,
                    "relative_path": f"f{idx}.py",
                    "python_lines": 10,
                    "fun_cfun_space_by_tokens_scored": 10,
                    "fun_cfun_npr_coverage_ratio": 1.0 if np.isfinite(npr) else np.nan,
                    NPR_METRIC: npr,
                    "file_npr_fun_cfun_status": "scored" if np.isfinite(npr) else "no_fun_cfun",
                    "sonar_issue_total": issues,
                    "sonar_issue_type_code_smell": issues,
                    "sonar_issue_type_bug": 0,
                    "sonar_issue_type_vulnerability": 0,
                    "sonar_issue_type_other": 0,
                    "sonar_issue_high_severity": 0,
                    "sonar_issue_with_maintainability_impact": issues,
                    "sonar_issue_with_reliability_impact": 0,
                    "sonar_issue_with_security_impact": 0,
                }
            )
    files = pd.DataFrame(file_rows)
    result = aggregate_one_threshold(files, 1.5, base[["repo_id", "time_index"]])
    selected = result.set_index(["repo_id", "time_index"])
    assert int(selected.loc[(1, 1), "eligible_fun_cfun_file_count"]) == 2
    assert int(selected.loc[(1, 1), "selected_file_count"]) == 0
    assert int(selected.loc[(1, 1), "selected_issue_total"]) == 0
    assert int(selected.loc[(2, 1), "selected_issue_total"]) == 7
    assert math.isclose(float(selected.loc[(2, 1), "log1p_selected_issue_total"]), math.log1p(7), abs_tol=1e-12)
    print("build_fun_cfun_npr_threshold_quality_burden_panel self-test: PASS")

def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Build I04 frozen-threshold Quality x FUN+C_FUN-NPR burden panel.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--i03-file", type=Path)
    parser.add_argument("--i03-summary-file", type=Path)
    parser.add_argument("--i03-outside-scope-file", type=Path)
    parser.add_argument("--b06-panel-file", type=Path)
    parser.add_argument("--i02-summary-file", type=Path)
    parser.add_argument("--threshold-spec-file", type=Path)
    parser.add_argument("--threshold-audit-file", type=Path)
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
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-untreated-rows", type=int, default=1591)
    parser.add_argument("--expected-treated-rows", type=int, default=363)
    parser.add_argument("--expected-dynamic-rows", type=int, default=343)
    parser.add_argument("--expected-i03-rows", type=int, default=510297)
    parser.add_argument("--expected-finite-fun-cfun-rows", type=int, default=359057)
    parser.add_argument("--expected-scope-repositories", type=int, default=2)
    parser.add_argument("--expected-scope-repo-month-rows", type=int, default=1915)
    parser.add_argument("--expected-primary-selected-files", type=int, default=17071)
    parser.add_argument("--expected-primary-selected-issues", type=int, default=14809)
    parser.add_argument("--expected-primary-selected-code-smell", type=int, default=14318)
    parser.add_argument("--expected-primary-sensitivity-selected-files", type=int, default=16885)
    parser.add_argument("--expected-primary-sensitivity-selected-issues", type=int, default=14748)
    args = parser.parse_args()
    if args.self_test:
        return args
    required = [
        "i03_file", "i03_summary_file", "i03_outside_scope_file", "b06_panel_file",
        "i02_summary_file", "threshold_spec_file", "threshold_audit_file",
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
