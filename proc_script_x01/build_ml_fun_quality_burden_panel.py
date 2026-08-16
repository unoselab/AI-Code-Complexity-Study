#!/usr/bin/env python3
"""
run-x-d05-v1: build the ML-selected Python quality-burden repo-month panel.

Scientific purpose
------------------
D05 connects the frozen run-x-a04 ML file classification to the already-canonical
D02 Python SonarQube file-burden table, then aggregates selected-file issue stock
to the B06 1,954-row repository-month quality panel.

The program deliberately does NOT:
- rerun the ML detector,
- change the frozen A04 primary file threshold,
- rerun SonarQube or recollect B05 issues,
- recompute the D02 file-level SonarQube join,
- estimate a DiD model.

Frozen primary ML file rule
---------------------------
A file is primary ML-AGC-like iff:

    file_ml_agc_share_space_by_token_weighted > 0.50

Only A04 rows with file_ml_agc_status == "scored" are ML-classifiable.
Rows with no_ml_fun or file_not_prepared remain unclassified and are never
implicitly treated as HWC.

Canonical quality source
------------------------
D02 already joined the complete B05 historical Python SonarQube issue stock to
A12 repo-month/file rows. D05 reuses that canonical join instead of touching raw
SonarQube data again.

Exact A04 x D02 join
--------------------
The authoritative historical file identity is:

    snapshot_id + relative_path + file_sha256

D02 contains repeated repo-month/file rows when the same historical snapshot is
reused by more than one panel month. Therefore the join is many D02 rows to one
unique A04 snapshot/file row. D05 requires the UNIQUE D02 snapshot/file universe
to match A04 exactly.

Pre-specified analysis dimensions
---------------------------------
Repository sample specifications:
1. full_sample
2. exclude_scope_mismatch_repos

ML mapping specifications:
1. all_ml_files                 (primary)
2. exclude_mapping_warning_files (robustness)

The mapping-warning robustness excludes warning-bearing A04 file rows from both
the ML-eligible denominator and the selected-file numerator.

Primary downstream outcome for D06
----------------------------------
    log1p_selected_issue_total

This is the log1p unresolved SonarQube issue stock in contemporaneously selected
ML-AGC-like Python files at the historical repository-month snapshot. It is a
quality-burden decomposition, not a calibrated defect rate and not proof that an
individual file was AI-generated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCRIPT_VERSION = "run-x-d05-v1"
A04_EXPECTED_RUN = "run-x-a04-v1"
A04_EXPECTED_STATUS = "PASS_WITH_WARNINGS"
D02_EXPECTED_RUN = "run-x-d02-v2"
D02_EXPECTED_STATUS = "PASS_WITH_SCOPE_EXCLUSIONS"
PRIMARY_ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
PRIMARY_ML_THRESHOLD = 0.50
PRIMARY_ML_OPERATOR = ">"
QUALITY_SEMANTICS = "unresolved_sonarqube_issue_stock_at_historical_snapshot"

EXPECTED_A04_FILE_ROWS = 494_592
EXPECTED_A04_FILES_WITH_FUN = 196_644
EXPECTED_A04_NO_FUN = 297_688
EXPECTED_A04_NOT_PREPARED = 260
EXPECTED_A04_PRIMARY_SELECTED = 41_905
EXPECTED_A04_MAPPING_WARNING_FILES = 5_378
EXPECTED_D02_ROWS = 510_297
EXPECTED_UNIQUE_SNAPSHOT_FILES = 494_592
EXPECTED_PANEL_ROWS = 1_954
EXPECTED_REPOSITORIES = 167
EXPECTED_TREATMENT_REPOSITORIES = 63
EXPECTED_CONTROL_REPOSITORIES = 104

A04_REQUIRED = {
    "snapshot_id",
    "dataset_source",
    "repo_name",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "python_lines",
    "ml_fun_occurrences_total",
    "ml_fun_agc_occurrences",
    "ml_fun_hwc_occurrences",
    "ml_fun_space_by_tokens_total",
    "ml_fun_agc_space_by_tokens",
    "ml_fun_hwc_space_by_tokens",
    "file_ml_agc_share_by_count",
    PRIMARY_ML_METRIC,
    "file_ml_human_decision_score_space_by_token_weighted",
    "file_ml_agc_score_space_by_token_weighted",
    "ml_fun_mapping_warning_occurrences",
    "ml_fun_mapping_warning_present",
    "file_ml_agc_like_primary",
    "file_ml_agc_primary_threshold",
    "file_ml_agc_primary_operator",
    "file_ml_agc_status",
}

D02_REQUIRED = {
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
    "file_sha256",
    "python_lines",
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

B06_REQUIRED = {
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

SENSITIVITY_SPEC_REQUIRED = {
    "sample_spec",
    "dataset_source",
    "repo_name",
    "exclude_repository",
    "prespecified_before_d03",
    "reason",
}

ALIAS_HANDLING_REQUIRED = {
    "policy_id",
    "apply_in_d03",
    "prespecified_before_d03",
    "alias_rows",
    "alias_issue_stock",
    "analysis_signature_overlap_issue_stock",
    "unmatched_alias_analysis_issue_stock",
    "policy_condition",
    "action",
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

CHECK_COLUMNS = ["check", "observed", "expected", "status", "detail"]
SUMMARY_COLUMNS = ["metric", "value"]


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
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
    """Fail if required columns are absent."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def read_csv(path: Path, string_columns: Iterable[str] = ()) -> pd.DataFrame:
    """Read a CSV/CSV.GZ while preserving requested identity columns."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    header = pd.read_csv(path, nrows=0)
    dtype = {column: "string" for column in string_columns if column in header.columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def read_metric_csv(path: Path) -> dict[str, str]:
    """Read a metric/value CSV into a dictionary."""
    df = read_csv(path)
    if not {"metric", "value"}.issubset(df.columns):
        raise ValueError(f"Metric CSV missing metric/value columns: {path}")
    return {clean(row.metric): clean(row.value) for row in df.itertuples(index=False)}


def sha256_file(path: Path) -> str:
    """Compute SHA256 for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(df: pd.DataFrame, path: Path, compression: str | None = None) -> None:
    """Write a CSV atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + (".tmp.gz" if str(path).endswith(".gz") else ".tmp"))
    df.to_csv(tmp, index=False, compression=compression)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def add_check(
    rows: list[dict[str, Any]],
    check: str,
    observed: Any,
    expected: Any,
    passed: bool,
    detail: str = "",
) -> None:
    """Append one QC check."""
    rows.append(
        {
            "check": check,
            "observed": observed,
            "expected": expected,
            "status": "pass" if passed else "fail",
            "detail": detail,
        }
    )


def validate_a04_contract(summary_path: Path, checks_path: Path) -> dict[str, Any]:
    """Validate the frozen A04 primary file-classification contract."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if clean(summary.get("run")) != A04_EXPECTED_RUN:
        raise ValueError(f"Unexpected A04 run: {summary.get('run')}")
    if clean(summary.get("mode")) != "full":
        raise ValueError(f"A04 mode must be full: {summary.get('mode')}")
    if clean(summary.get("status")) != A04_EXPECTED_STATUS:
        raise ValueError(f"Unexpected A04 status: {summary.get('status')}")
    if int(summary.get("failed_hard_checks", -1)) != 0:
        raise ValueError("A04 has failed hard checks")

    rule = summary.get("primary_file_rule", {})
    if clean(rule.get("metric")) != PRIMARY_ML_METRIC:
        raise ValueError("A04 primary metric mismatch")
    if clean(rule.get("operator")) != PRIMARY_ML_OPERATOR:
        raise ValueError("A04 primary operator mismatch")
    if not math.isclose(float(rule.get("threshold")), PRIMARY_ML_THRESHOLD, abs_tol=1e-12):
        raise ValueError("A04 primary threshold mismatch")

    checks = read_csv(checks_path, ["check", "severity", "passed"])
    require_columns(checks, {"check", "severity", "passed"}, "A04 checks")
    hard = checks[checks["severity"].map(clean).eq("hard")].copy()
    passed = hard["passed"].map(bool_int)
    if not passed.eq(1).all():
        failed = hard.loc[~passed.eq(1), "check"].map(clean).tolist()
        raise ValueError(f"A04 hard checks are not clean: {failed}")
    return summary


def validate_d02_contracts(
    d02_summary_path: Path,
    d02a_summary_path: Path,
    d02b_summary_path: Path,
    sensitivity_spec_path: Path,
    alias_handling_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str], dict[str, str], dict[str, str]]:
    """Validate the same D02/D02-a/D02-b gates used by D03."""
    d02 = read_metric_csv(d02_summary_path)
    d02a = read_metric_csv(d02a_summary_path)
    d02b = read_metric_csv(d02b_summary_path)

    if d02.get("script_version") != D02_EXPECTED_RUN:
        raise ValueError(f"Unexpected D02 script version: {d02.get('script_version')}")
    if d02.get("status") != D02_EXPECTED_STATUS:
        raise ValueError(f"Unexpected D02 status: {d02.get('status')}")
    if d02.get("hard_qc_failures") != "0" or d02.get("threshold_applied") != "0":
        raise ValueError("D02 no-failure/no-threshold contract is not satisfied")

    if d02a.get("status") != "PASS_CONFIRMED_FILESYSTEM_ALIAS_SCOPE":
        raise ValueError(f"Unexpected D02-a status: {d02a.get('status')}")
    if d02a.get("hard_qc_failures") != "0" or d02a.get("high_concern_rows") != "0":
        raise ValueError("D02-a contains hard/high-concern failures")

    if d02b.get("status") != "PASS_CONFIRMED_ALIAS_ISSUE_DUPLICATION":
        raise ValueError(f"Unexpected D02-b status: {d02b.get('status')}")
    if d02b.get("hard_qc_failures") != "0" or d02b.get("d03_ready") != "1":
        raise ValueError("D02-b does not mark the canonical burden as ready")
    if d02b.get("unmatched_alias_analysis_issue_stock") != "0":
        raise ValueError("D02-b reports unmatched alias issue stock")

    sensitivity = read_csv(sensitivity_spec_path, ["sample_spec", "dataset_source", "repo_name", "reason"])
    require_columns(sensitivity, SENSITIVITY_SPEC_REQUIRED, "D02-a sensitivity specification")
    sensitivity["exclude_repository"] = sensitivity["exclude_repository"].map(bool_int)
    sensitivity["prespecified_before_d03"] = sensitivity["prespecified_before_d03"].map(bool_int)
    if len(sensitivity) != 2:
        raise ValueError(f"Expected exactly 2 D02-a scope-sensitivity repositories, observed {len(sensitivity)}")
    if not sensitivity["exclude_repository"].eq(1).all() or not sensitivity["prespecified_before_d03"].eq(1).all():
        raise ValueError("D02-a sensitivity repositories are not fully pre-specified exclusions")
    if set(sensitivity["sample_spec"].map(clean)) != {"exclude_scope_mismatch_repos"}:
        raise ValueError("Unexpected D02-a sample_spec")

    alias = read_csv(alias_handling_path, ["policy_id", "policy_condition", "action"])
    require_columns(alias, ALIAS_HANDLING_REQUIRED, "D02-b alias handling specification")
    if len(alias) != 1:
        raise ValueError("Expected exactly one D02-b alias policy")
    row = alias.iloc[0]
    if clean(row["policy_id"]) != "exclude_filesystem_alias_issues_keep_canonical_a12_path":
        raise ValueError("Unexpected D02-b alias policy")
    if bool_int(row["apply_in_d03"]) != 1 or bool_int(row["prespecified_before_d03"]) != 1:
        raise ValueError("D02-b alias policy was not frozen before D03")
    if int(row["unmatched_alias_analysis_issue_stock"]) != 0:
        raise ValueError("D02-b alias policy contains unmatched analysis issue stock")
    return sensitivity, alias, d02, d02a, d02b


def load_a04(path: Path) -> pd.DataFrame:
    """Load and validate the unique A04 historical snapshot/file table."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, A04_REQUIRED, "A04 file scores")
    usecols = sorted(A04_REQUIRED)
    string_cols = {
        "snapshot_id",
        "dataset_source",
        "repo_name",
        "snapshot_commit",
        "relative_path",
        "file_sha256",
        "file_ml_agc_primary_operator",
        "file_ml_agc_status",
    }
    dtype = {column: "string" for column in string_cols}
    data = pd.read_csv(path, usecols=usecols, dtype=dtype, low_memory=False)

    for column in string_cols:
        data[column] = data[column].map(clean)
    data["dataset_source"] = data["dataset_source"].str.casefold()
    data["snapshot_commit"] = data["snapshot_commit"].str.casefold()
    data["file_sha256"] = data["file_sha256"].str.casefold()

    numeric = [
        "python_lines",
        "ml_fun_occurrences_total",
        "ml_fun_agc_occurrences",
        "ml_fun_hwc_occurrences",
        "ml_fun_space_by_tokens_total",
        "ml_fun_agc_space_by_tokens",
        "ml_fun_hwc_space_by_tokens",
        "file_ml_agc_share_by_count",
        PRIMARY_ML_METRIC,
        "file_ml_human_decision_score_space_by_token_weighted",
        "file_ml_agc_score_space_by_token_weighted",
        "ml_fun_mapping_warning_occurrences",
        "ml_fun_mapping_warning_present",
        "file_ml_agc_like_primary",
        "file_ml_agc_primary_threshold",
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    key = ["snapshot_id", "relative_path", "file_sha256"]
    # A05 can preserve a small number of explicitly not-prepared files without
    # a content SHA. Their snapshot_id + relative_path identity is still
    # authoritative, and A04 intentionally keeps file_sha256 blank for them.
    if data[["snapshot_id", "relative_path"]].astype(str).apply(lambda col: col.str.len().eq(0)).any().any():
        raise ValueError("A04 contains missing snapshot_id or relative_path")
    if data.duplicated(key).any():
        raise ValueError("A04 contains duplicate snapshot/path/file_sha256 keys")

    allowed_status = {"scored", "no_ml_fun", "file_not_prepared"}
    if not set(data["file_ml_agc_status"]) <= allowed_status:
        raise ValueError(f"Unexpected A04 status values: {sorted(set(data['file_ml_agc_status']) - allowed_status)}")

    scored = data["file_ml_agc_status"].eq("scored")
    unclassified = ~scored
    if data.loc[scored, PRIMARY_ML_METRIC].isna().any():
        raise ValueError("A04 scored rows contain missing weighted AGC share")
    if data.loc[unclassified, PRIMARY_ML_METRIC].notna().any():
        raise ValueError("A04 unclassified rows unexpectedly contain weighted AGC share")
    if data.loc[unclassified, "file_ml_agc_like_primary"].notna().any():
        raise ValueError("A04 unclassified rows unexpectedly contain primary classification")

    expected_flags = data.loc[scored, PRIMARY_ML_METRIC].gt(PRIMARY_ML_THRESHOLD).astype("int64")
    observed_flags = data.loc[scored, "file_ml_agc_like_primary"].astype("int64")
    if not expected_flags.equals(observed_flags):
        raise ValueError("A04 primary classification does not reproduce weighted-share > 0.50")
    if not data.loc[scored, "file_ml_agc_primary_operator"].eq(PRIMARY_ML_OPERATOR).all():
        raise ValueError("A04 primary operator mismatch in scored rows")
    if not np.allclose(
        data.loc[scored, "file_ml_agc_primary_threshold"].astype(float),
        PRIMARY_ML_THRESHOLD,
        atol=1e-12,
        rtol=0,
    ):
        raise ValueError("A04 primary threshold mismatch in scored rows")
    return data


def load_d02(path: Path) -> pd.DataFrame:
    """Load the canonical D02 repo-month/file SonarQube burden table."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, D02_REQUIRED, "D02 file-quality burden")
    usecols = sorted(D02_REQUIRED)
    string_cols = {
        "dataset_source",
        "repo_name",
        "repo_month",
        "event",
        "snapshot_id",
        "snapshot_commit",
        "relative_path",
        "file_sha256",
    }
    dtype = {column: "string" for column in string_cols}
    data = pd.read_csv(path, usecols=usecols, dtype=dtype, low_memory=False)
    for column in string_cols:
        data[column] = data[column].map(clean)
    data["dataset_source"] = data["dataset_source"].str.casefold()
    data["snapshot_commit"] = data["snapshot_commit"].str.casefold()
    data["file_sha256"] = data["file_sha256"].str.casefold()

    for column in ["repo_id", "time_index", "event_index", "python_lines", *ISSUE_COLUMNS]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[["repo_id", "time_index", "event_index"]].isna().any().any():
        raise ValueError("D02 contains missing repo/time/event identity")
    data["repo_id"] = data["repo_id"].astype("int64")
    data["time_index"] = data["time_index"].astype("int64")
    data["event_index"] = data["event_index"].astype("int64")
    for column in ISSUE_COLUMNS:
        if data[column].isna().any() or data[column].lt(0).any():
            raise ValueError(f"D02 issue column must be complete and non-negative: {column}")
        data[column] = data[column].astype("int64")
    return data


def load_b06(path: Path) -> pd.DataFrame:
    """Load the authoritative B06 1,954-row quality panel."""
    header = pd.read_csv(path, nrows=0)
    require_columns(header, B06_REQUIRED, "B06 quality panel")
    string_cols = [
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
    data = read_csv(path, string_cols)
    for column in string_cols:
        data[column] = data[column].map(clean)
    data["dataset_source"] = data["dataset_source"].str.casefold()
    data["latest_commit_effective"] = data["latest_commit_effective"].str.casefold()

    numeric = [
        "repo_id",
        "treatment_group",
        "time_index",
        "event_index",
        "log_age",
        "ncloc_py_sonarqube",
        "log_contributors",
        "log_stars",
        "log_issues",
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[numeric].isna().any().any():
        raise ValueError("B06 contains missing required numeric values")
    data["repo_id"] = data["repo_id"].astype("int64")
    data["treatment_group"] = data["treatment_group"].astype("int64")
    data["time_index"] = data["time_index"].astype("int64")
    data["event_index"] = data["event_index"].astype("int64")
    if data.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("B06 contains duplicate repo_id/time_index rows")
    if not data["quality_did_complete"].map(bool_int).eq(1).all():
        raise ValueError("B06 quality_did_complete is not uniformly true")
    if not data["quality_scope"].eq("python_only_sonar_inclusions").all():
        raise ValueError("B06 quality_scope mismatch")
    if not data["quality_count_semantics"].eq("unresolved_issue_stock_at_historical_snapshot").all():
        raise ValueError("B06 quality count semantics mismatch")
    return data


def validate_repo_month_identity(d02: pd.DataFrame, b06: pd.DataFrame) -> None:
    """Require D02 and B06 to describe the same repo-month observations."""
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
    grouped = d02[identity_cols].drop_duplicates()
    if grouped.duplicated(["repo_id", "time_index"], keep=False).any():
        raise ValueError("D02 has inconsistent repo-month identity within repo_id/time_index")

    right = b06[
        [
            "repo_id",
            "time_index",
            "dataset_source",
            "repo_name",
            "time",
            "event",
            "event_index",
            "snapshot_key",
            "latest_commit_effective",
        ]
    ].copy()
    merged = right.merge(
        grouped,
        on=["repo_id", "time_index"],
        how="outer",
        suffixes=("_b06", "_d02"),
        indicator=True,
        validate="one_to_one",
    )
    if not merged["_merge"].eq("both").all():
        raise ValueError("D02/B06 repo-month key universes do not match")
    comparisons = {
        "dataset_source": merged["dataset_source_b06"].str.casefold().eq(merged["dataset_source_d02"].str.casefold()),
        "repo_name": merged["repo_name_b06"].str.casefold().eq(merged["repo_name_d02"].str.casefold()),
        "time": merged["time"].eq(merged["repo_month"]),
        "event": merged["event_b06"].eq(merged["event_d02"]),
        "event_index": merged["event_index_b06"].eq(merged["event_index_d02"]),
        "snapshot_key": merged["snapshot_key"].eq(merged["snapshot_id"]),
        "commit": merged["latest_commit_effective"].eq(merged["snapshot_commit"]),
    }
    failures = {name: int((~mask).sum()) for name, mask in comparisons.items()}
    if any(failures.values()):
        raise ValueError(f"D02/B06 repo-month identity mismatch: {failures}")


def normalized_timing(panel: pd.DataFrame) -> pd.DataFrame:
    """Add authoritative treatment timing reconstructed from time/event indices."""
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


def attach_a04_to_d02(d02: pd.DataFrame, a04: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach one unique A04 file classification to every D02 repo-month/file row."""
    key = ["snapshot_id", "relative_path", "file_sha256"]
    d02_unique = d02[key].drop_duplicates()
    a04_unique = a04[key].drop_duplicates()

    universe = d02_unique.merge(a04_unique, on=key, how="outer", indicator=True, validate="one_to_one")
    d02_only = int(universe["_merge"].eq("left_only").sum())
    a04_only = int(universe["_merge"].eq("right_only").sum())
    if d02_only or a04_only:
        raise ValueError(f"A04/D02 historical file universes differ: d02_only={d02_only}, a04_only={a04_only}")

    a04_cols = [
        *key,
        "dataset_source",
        "repo_name",
        "snapshot_commit",
        "python_lines",
        "ml_fun_occurrences_total",
        "ml_fun_agc_occurrences",
        "ml_fun_hwc_occurrences",
        "ml_fun_space_by_tokens_total",
        "ml_fun_agc_space_by_tokens",
        "ml_fun_hwc_space_by_tokens",
        "file_ml_agc_share_by_count",
        PRIMARY_ML_METRIC,
        "file_ml_human_decision_score_space_by_token_weighted",
        "file_ml_agc_score_space_by_token_weighted",
        "ml_fun_mapping_warning_occurrences",
        "ml_fun_mapping_warning_present",
        "file_ml_agc_like_primary",
        "file_ml_agc_primary_threshold",
        "file_ml_agc_primary_operator",
        "file_ml_agc_status",
    ]
    merged = d02.merge(
        a04[a04_cols],
        on=key,
        how="left",
        validate="many_to_one",
        suffixes=("_d02", "_a04"),
    )
    if len(merged) != len(d02):
        raise ValueError("A04 attachment changed D02 row count")

    identity_failures = {
        "dataset_source": int((~merged["dataset_source_d02"].str.casefold().eq(merged["dataset_source_a04"].str.casefold())).sum()),
        "repo_name": int((~merged["repo_name_d02"].str.casefold().eq(merged["repo_name_a04"].str.casefold())).sum()),
        "snapshot_commit": int((~merged["snapshot_commit_d02"].str.casefold().eq(merged["snapshot_commit_a04"].str.casefold())).sum()),
    }
    if any(identity_failures.values()):
        raise ValueError(f"A04/D02 identity mismatches: {identity_failures}")

    d02_lines = pd.to_numeric(merged["python_lines_d02"], errors="coerce")
    a04_lines = pd.to_numeric(merged["python_lines_a04"], errors="coerce")
    line_mismatch = int((d02_lines.fillna(-1) != a04_lines.fillna(-1)).sum())
    if line_mismatch:
        raise ValueError(f"A04/D02 python_lines mismatch rows: {line_mismatch}")

    merged = merged.rename(
        columns={
            "dataset_source_d02": "dataset_source",
            "repo_name_d02": "repo_name",
            "snapshot_commit_d02": "snapshot_commit",
            "python_lines_d02": "python_lines",
        }
    )
    merged = merged.drop(
        columns=["dataset_source_a04", "repo_name_a04", "snapshot_commit_a04", "python_lines_a04"]
    )
    diagnostics = {
        "d02_rows": len(d02),
        "d02_unique_snapshot_files": len(d02_unique),
        "a04_rows": len(a04),
        "a04_unique_snapshot_files": len(a04_unique),
        "d02_only_file_keys": d02_only,
        "a04_only_file_keys": a04_only,
        "identity_mismatch_rows": sum(identity_failures.values()),
        "python_lines_mismatch_rows": line_mismatch,
    }
    return merged, diagnostics


def aggregate_mapping_spec(files: pd.DataFrame, base_keys: pd.DataFrame, exclude_mapping_warnings: bool) -> pd.DataFrame:
    """Aggregate one frozen ML mapping specification to repository-month rows."""
    scored = files["file_ml_agc_status"].eq("scored").to_numpy(dtype=bool)
    warning = files["ml_fun_mapping_warning_present"].fillna(0).astype("int64").eq(1).to_numpy(dtype=bool)
    eligible = scored & (~warning if exclude_mapping_warnings else True)
    primary = files["file_ml_agc_like_primary"].fillna(0).astype("int64").eq(1).to_numpy(dtype=bool)
    selected = eligible & primary

    work = files[["repo_id", "time_index", "python_lines", *ISSUE_COLUMNS]].copy()
    work["eligible_ml_file_count"] = eligible.astype("int64")
    work["selected_file_count"] = selected.astype("int64")
    work["mapping_warning_eligible_file_count"] = (eligible & warning).astype("int64")
    work["mapping_warning_selected_file_count"] = (selected & warning).astype("int64")
    work["selected_file_with_any_issue_count"] = (
        selected & files["sonar_issue_total"].gt(0).to_numpy(dtype=bool)
    ).astype("int64")
    work["selected_python_lines"] = pd.to_numeric(work["python_lines"], errors="coerce").fillna(0).where(selected, 0)
    work["eligible_ml_fun_space_by_tokens"] = pd.to_numeric(
        files["ml_fun_space_by_tokens_total"], errors="coerce"
    ).fillna(0).where(eligible, 0)
    work["eligible_ml_agc_space_by_tokens"] = pd.to_numeric(
        files["ml_fun_agc_space_by_tokens"], errors="coerce"
    ).fillna(0).where(eligible, 0)
    work["selected_ml_fun_space_by_tokens"] = pd.to_numeric(
        files["ml_fun_space_by_tokens_total"], errors="coerce"
    ).fillna(0).where(selected, 0)
    work["selected_ml_agc_space_by_tokens"] = pd.to_numeric(
        files["ml_fun_agc_space_by_tokens"], errors="coerce"
    ).fillna(0).where(selected, 0)
    for column in ISSUE_COLUMNS:
        work[column] = work[column].where(selected, 0)

    agg_map: dict[str, str] = {
        "eligible_ml_file_count": "sum",
        "selected_file_count": "sum",
        "mapping_warning_eligible_file_count": "sum",
        "mapping_warning_selected_file_count": "sum",
        "selected_file_with_any_issue_count": "sum",
        "selected_python_lines": "sum",
        "eligible_ml_fun_space_by_tokens": "sum",
        "eligible_ml_agc_space_by_tokens": "sum",
        "selected_ml_fun_space_by_tokens": "sum",
        "selected_ml_agc_space_by_tokens": "sum",
    }
    agg_map.update({column: "sum" for column in ISSUE_COLUMNS})
    grouped = work.groupby(["repo_id", "time_index"], as_index=False).agg(agg_map)
    grouped = grouped.rename(columns=OUTCOME_RENAME)
    grouped["selected_issue_free_file_count"] = (
        grouped["selected_file_count"] - grouped["selected_file_with_any_issue_count"]
    )
    grouped["selected_file_share_of_eligible"] = np.where(
        grouped["eligible_ml_file_count"].gt(0),
        grouped["selected_file_count"] / grouped["eligible_ml_file_count"],
        np.nan,
    )
    grouped["has_eligible_ml_files"] = grouped["eligible_ml_file_count"].gt(0).astype("int64")
    grouped["has_selected_files"] = grouped["selected_file_count"].gt(0).astype("int64")
    grouped["has_selected_issue_burden"] = grouped["selected_issue_total"].gt(0).astype("int64")
    for column in LOG_OUTCOMES:
        grouped[f"log1p_{column}"] = np.log1p(grouped[column].astype(float))

    output = base_keys.merge(grouped, on=["repo_id", "time_index"], how="left", validate="one_to_one")
    zero_fill = [
        "eligible_ml_file_count",
        "selected_file_count",
        "mapping_warning_eligible_file_count",
        "mapping_warning_selected_file_count",
        "selected_file_with_any_issue_count",
        "selected_issue_free_file_count",
        "selected_python_lines",
        "eligible_ml_fun_space_by_tokens",
        "eligible_ml_agc_space_by_tokens",
        "selected_ml_fun_space_by_tokens",
        "selected_ml_agc_space_by_tokens",
        *OUTCOME_RENAME.values(),
        "has_eligible_ml_files",
        "has_selected_files",
        "has_selected_issue_burden",
    ]
    for column in zero_fill:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    for column in LOG_OUTCOMES:
        log_col = f"log1p_{column}"
        output[log_col] = pd.to_numeric(output[log_col], errors="coerce").fillna(0.0)
    output["selected_file_share_of_eligible"] = np.where(
        output["eligible_ml_file_count"].gt(0),
        output["selected_file_count"] / output["eligible_ml_file_count"],
        np.nan,
    )
    return output


def sample_stratum(panel: pd.DataFrame) -> pd.Series:
    """Return descriptive control/treatment-pre/treatment-post strata."""
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
    files: pd.DataFrame,
    a04: pd.DataFrame,
    b06: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build long-form D05 panel and descriptive audits."""
    base = normalized_timing(b06[BASE_PANEL_COLUMNS].copy())
    base_keys = base[["repo_id", "time_index"]].copy()

    excluded_repos = {clean(value).casefold() for value in sensitivity["repo_name"]}
    sample_specs = {
        "full_sample": base,
        "exclude_scope_mismatch_repos": base[
            ~base["repo_name"].map(clean).str.casefold().isin(excluded_repos)
        ].copy(),
    }
    mapping_specs = {
        "all_ml_files": False,
        "exclude_mapping_warning_files": True,
    }

    panel_parts: list[pd.DataFrame] = []
    global_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []

    for mapping_name, exclude_warnings in mapping_specs.items():
        aggregated = aggregate_mapping_spec(files, base_keys, exclude_warnings)
        full = base.merge(aggregated, on=["repo_id", "time_index"], how="left", validate="one_to_one")

        for sample_name, sample_base in sample_specs.items():
            keys = sample_base[["repo_id", "time_index"]]
            sample = full.merge(keys, on=["repo_id", "time_index"], how="inner", validate="one_to_one")
            sample = sample.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
            sample.insert(0, "mapping_spec", mapping_name)
            sample.insert(0, "sample_spec", sample_name)
            sample.insert(2, "primary_analysis", int(sample_name == "full_sample" and mapping_name == "all_ml_files"))
            sample.insert(3, "ml_primary_metric", PRIMARY_ML_METRIC)
            sample.insert(4, "ml_primary_operator", PRIMARY_ML_OPERATOR)
            sample.insert(5, "ml_primary_threshold", PRIMARY_ML_THRESHOLD)
            panel_parts.append(sample)

            sample_repo_keys = set(sample["repo_id"].astype(int).tolist())
            file_sample = files[files["repo_id"].isin(sample_repo_keys)].copy()
            scored = file_sample["file_ml_agc_status"].eq("scored")
            warning = file_sample["ml_fun_mapping_warning_present"].fillna(0).astype("int64").eq(1)
            eligible = scored & (~warning if exclude_warnings else True)
            selected = eligible & file_sample["file_ml_agc_like_primary"].fillna(0).astype("int64").eq(1)
            unique_selected = file_sample.loc[selected, ["snapshot_id", "relative_path", "file_sha256"]].drop_duplicates()
            unique_eligible = file_sample.loc[eligible, ["snapshot_id", "relative_path", "file_sha256"]].drop_duplicates()

            global_rows.append(
                {
                    "sample_spec": sample_name,
                    "mapping_spec": mapping_name,
                    "repo_month_rows": len(sample),
                    "repositories": sample["repo_id"].nunique(),
                    "eligible_file_rows": int(sample["eligible_ml_file_count"].sum()),
                    "eligible_unique_snapshot_files": len(unique_eligible),
                    "selected_file_rows": int(sample["selected_file_count"].sum()),
                    "selected_unique_snapshot_files": len(unique_selected),
                    "selected_share_of_eligible_rows": (
                        float(sample["selected_file_count"].sum()) / float(sample["eligible_ml_file_count"].sum())
                        if float(sample["eligible_ml_file_count"].sum()) > 0
                        else np.nan
                    ),
                    "repo_months_with_selected_files": int(sample["has_selected_files"].sum()),
                    "mapping_warning_selected_file_rows": int(sample["mapping_warning_selected_file_count"].sum()),
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

            temp = sample.copy()
            temp["timing_stratum"] = sample_stratum(temp)
            for stratum, group in temp.groupby("timing_stratum", sort=False):
                timing_rows.append(
                    {
                        "sample_spec": sample_name,
                        "mapping_spec": mapping_name,
                        "timing_stratum": stratum,
                        "repo_month_rows": len(group),
                        "repositories": group["repo_id"].nunique(),
                        "eligible_file_rows": int(group["eligible_ml_file_count"].sum()),
                        "selected_file_rows": int(group["selected_file_count"].sum()),
                        "selected_share_of_eligible_rows": (
                            float(group["selected_file_count"].sum()) / float(group["eligible_ml_file_count"].sum())
                            if float(group["eligible_ml_file_count"].sum()) > 0
                            else np.nan
                        ),
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

    sample_summary = (
        panel.groupby(["sample_spec", "mapping_spec"], as_index=False)
        .agg(
            repo_month_rows=("repo_id", "size"),
            repositories=("repo_id", "nunique"),
            treatment_repositories=("repo_id", lambda s: panel.loc[s.index].query("treatment_group == 1")["repo_id"].nunique()),
            control_repositories=("repo_id", lambda s: panel.loc[s.index].query("treatment_group == 0")["repo_id"].nunique()),
            repo_months_with_selected_files=("has_selected_files", "sum"),
            selected_file_rows=("selected_file_count", "sum"),
            selected_issue_total=("selected_issue_total", "sum"),
        )
        .sort_values(["sample_spec", "mapping_spec"], kind="stable")
        .reset_index(drop=True)
    )

    outcome_spec = pd.DataFrame(
        [
            {
                "outcome": "log1p_selected_issue_total",
                "role": "primary_burden",
                "count_column": "selected_issue_total",
                "description": "log1p unresolved SonarQube issue stock in contemporaneously ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_code_smell",
                "role": "robustness_burden",
                "count_column": "selected_issue_code_smell",
                "description": "log1p code-smell stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_bug",
                "role": "robustness_burden",
                "count_column": "selected_issue_bug",
                "description": "log1p bug stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_vulnerability",
                "role": "robustness_burden",
                "count_column": "selected_issue_vulnerability",
                "description": "log1p vulnerability stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_maintainability_impact",
                "role": "robustness_burden",
                "count_column": "selected_issue_maintainability_impact",
                "description": "log1p maintainability-impact issue stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_reliability_impact",
                "role": "robustness_burden",
                "count_column": "selected_issue_reliability_impact",
                "description": "log1p reliability-impact issue stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_security_impact",
                "role": "robustness_burden",
                "count_column": "selected_issue_security_impact",
                "description": "log1p security-impact issue stock in ML-selected Python files",
            },
            {
                "outcome": "log1p_selected_issue_high_severity",
                "role": "robustness_burden",
                "count_column": "selected_issue_high_severity",
                "description": "log1p BLOCKER+CRITICAL issue stock in ML-selected Python files",
            },
        ]
    )
    return panel, global_audit, timing_audit, sample_summary, outcome_spec


def production_checks(
    args: argparse.Namespace,
    a04: pd.DataFrame,
    a04_summary: dict[str, Any],
    d02: pd.DataFrame,
    b06: pd.DataFrame,
    joined: pd.DataFrame,
    join_diag: dict[str, Any],
    panel: pd.DataFrame,
    global_audit: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Build strict D05 QC checks."""
    rows: list[dict[str, Any]] = []
    strict = args.strict_expected_counts

    status_counts = a04["file_ml_agc_status"].value_counts().to_dict()
    selected_unique = int(a04["file_ml_agc_like_primary"].fillna(0).eq(1).sum())
    warning_unique = int(a04["ml_fun_mapping_warning_present"].fillna(0).eq(1).sum())
    d02_unique = len(d02[["snapshot_id", "relative_path", "file_sha256"]].drop_duplicates())

    expected_pairs = [
        ("a04_file_rows", len(a04), EXPECTED_A04_FILE_ROWS),
        ("a04_files_with_fun", int(status_counts.get("scored", 0)), EXPECTED_A04_FILES_WITH_FUN),
        ("a04_no_ml_fun", int(status_counts.get("no_ml_fun", 0)), EXPECTED_A04_NO_FUN),
        ("a04_file_not_prepared", int(status_counts.get("file_not_prepared", 0)), EXPECTED_A04_NOT_PREPARED),
        ("a04_primary_selected_unique_files", selected_unique, EXPECTED_A04_PRIMARY_SELECTED),
        ("a04_mapping_warning_unique_files", warning_unique, EXPECTED_A04_MAPPING_WARNING_FILES),
        ("d02_repo_month_file_rows", len(d02), EXPECTED_D02_ROWS),
        ("d02_unique_snapshot_files", d02_unique, EXPECTED_UNIQUE_SNAPSHOT_FILES),
        ("b06_repo_month_rows", len(b06), EXPECTED_PANEL_ROWS),
        ("b06_repositories", b06["repo_id"].nunique(), EXPECTED_REPOSITORIES),
        (
            "b06_treatment_repositories",
            b06.loc[b06["treatment_group"].eq(1), "repo_id"].nunique(),
            EXPECTED_TREATMENT_REPOSITORIES,
        ),
        (
            "b06_control_repositories",
            b06.loc[b06["treatment_group"].eq(0), "repo_id"].nunique(),
            EXPECTED_CONTROL_REPOSITORIES,
        ),
    ]
    for name, observed, expected in expected_pairs:
        add_check(rows, name, observed, expected, (observed == expected) or not strict)

    add_check(rows, "a04_failed_hard_checks", a04_summary.get("failed_hard_checks"), 0, int(a04_summary.get("failed_hard_checks", -1)) == 0)
    add_check(rows, "a04_d02_d02_only_file_keys", join_diag["d02_only_file_keys"], 0, join_diag["d02_only_file_keys"] == 0)
    add_check(rows, "a04_d02_a04_only_file_keys", join_diag["a04_only_file_keys"], 0, join_diag["a04_only_file_keys"] == 0)
    add_check(rows, "a04_d02_identity_mismatch_rows", join_diag["identity_mismatch_rows"], 0, join_diag["identity_mismatch_rows"] == 0)
    add_check(rows, "a04_d02_python_lines_mismatch_rows", join_diag["python_lines_mismatch_rows"], 0, join_diag["python_lines_mismatch_rows"] == 0)
    add_check(rows, "joined_d02_row_conservation", len(joined), len(d02), len(joined) == len(d02))

    invalid_selected = int((joined["file_ml_agc_like_primary"].fillna(0).eq(1) & ~joined["file_ml_agc_status"].eq("scored")).sum())
    add_check(rows, "selected_unclassified_file_rows", invalid_selected, 0, invalid_selected == 0)

    duplicate_panel = int(panel.duplicated(["sample_spec", "mapping_spec", "repo_id", "time_index"]).sum())
    add_check(rows, "panel_duplicate_keys", duplicate_panel, 0, duplicate_panel == 0)

    primary = panel[(panel["sample_spec"].eq("full_sample")) & (panel["mapping_spec"].eq("all_ml_files"))]
    add_check(rows, "primary_panel_rows", len(primary), EXPECTED_PANEL_ROWS, len(primary) == EXPECTED_PANEL_ROWS)
    add_check(rows, "primary_panel_repositories", primary["repo_id"].nunique(), EXPECTED_REPOSITORIES, primary["repo_id"].nunique() == EXPECTED_REPOSITORIES)

    primary_global = global_audit[(global_audit["sample_spec"].eq("full_sample")) & (global_audit["mapping_spec"].eq("all_ml_files"))].iloc[0]
    add_check(
        rows,
        "primary_unique_selected_snapshot_files",
        int(primary_global["selected_unique_snapshot_files"]),
        EXPECTED_A04_PRIMARY_SELECTED,
        int(primary_global["selected_unique_snapshot_files"]) == EXPECTED_A04_PRIMARY_SELECTED,
    )

    mapping_sens = panel[(panel["mapping_spec"].eq("exclude_mapping_warning_files"))]
    warning_selected = int(mapping_sens["mapping_warning_selected_file_count"].sum())
    warning_eligible = int(mapping_sens["mapping_warning_eligible_file_count"].sum())
    add_check(rows, "mapping_sensitivity_selected_warning_rows", warning_selected, 0, warning_selected == 0)
    add_check(rows, "mapping_sensitivity_eligible_warning_rows", warning_eligible, 0, warning_eligible == 0)

    negative_outcomes = 0
    for column in OUTCOME_RENAME.values():
        negative_outcomes += int(pd.to_numeric(panel[column], errors="coerce").lt(0).sum())
    add_check(rows, "negative_selected_issue_values", negative_outcomes, 0, negative_outcomes == 0)

    log_mismatches = 0
    for column in LOG_OUTCOMES:
        expected = np.log1p(panel[column].astype(float).to_numpy())
        observed = panel[f"log1p_{column}"].astype(float).to_numpy()
        log_mismatches += int((~np.isclose(expected, observed, atol=1e-12, rtol=0)).sum())
    add_check(rows, "log1p_outcome_mismatches", log_mismatches, 0, log_mismatches == 0)

    excluded_count = len(sensitivity)
    add_check(rows, "scope_sensitivity_repositories_prespecified", excluded_count, 2, excluded_count == 2)
    return rows


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Run the full D05 build."""
    for path in [
        args.a04_file,
        args.a04_summary_file,
        args.a04_checks_file,
        args.d02_file,
        args.d02_summary_file,
        args.b06_panel_file,
        args.scope_sensitivity_spec_file,
        args.d02a_summary_file,
        args.alias_handling_spec_file,
        args.d02b_summary_file,
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Required input not found: {path}")

    a04_summary = validate_a04_contract(args.a04_summary_file, args.a04_checks_file)
    sensitivity, alias, d02_summary, d02a_summary, d02b_summary = validate_d02_contracts(
        args.d02_summary_file,
        args.d02a_summary_file,
        args.d02b_summary_file,
        args.scope_sensitivity_spec_file,
        args.alias_handling_spec_file,
    )

    a04 = load_a04(args.a04_file)
    d02 = load_d02(args.d02_file)
    b06 = load_b06(args.b06_panel_file)
    validate_repo_month_identity(d02, b06)
    joined, join_diag = attach_a04_to_d02(d02, a04)
    panel, global_audit, timing_audit, sample_summary, outcome_spec = build_outputs(
        joined, a04, b06, sensitivity
    )

    checks = production_checks(
        args,
        a04,
        a04_summary,
        d02,
        b06,
        joined,
        join_diag,
        panel,
        global_audit,
        sensitivity,
    )
    checks_df = pd.DataFrame(checks, columns=CHECK_COLUMNS)
    hard_failures = int(checks_df["status"].ne("pass").sum())
    status = "PASS" if hard_failures == 0 else "FAIL"

    atomic_csv(panel, args.panel_output, compression="gzip")
    atomic_csv(global_audit, args.global_audit_output)
    atomic_csv(timing_audit, args.timing_audit_output)
    atomic_csv(sample_summary, args.sample_summary_output)
    atomic_csv(outcome_spec, args.outcome_spec_output)
    atomic_csv(checks_df, args.checks_output)

    primary_global = global_audit[
        global_audit["sample_spec"].eq("full_sample") & global_audit["mapping_spec"].eq("all_ml_files")
    ].iloc[0]
    mapping_global = global_audit[
        global_audit["sample_spec"].eq("full_sample")
        & global_audit["mapping_spec"].eq("exclude_mapping_warning_files")
    ].iloc[0]

    summary_rows = [
        ("script_version", SCRIPT_VERSION),
        ("status", status),
        ("quality_semantics", QUALITY_SEMANTICS),
        ("primary_ml_metric", PRIMARY_ML_METRIC),
        ("primary_ml_operator", PRIMARY_ML_OPERATOR),
        ("primary_ml_threshold", PRIMARY_ML_THRESHOLD),
        ("density_computed", 0),
        ("a04_file_rows", len(a04)),
        ("a04_files_with_fun", int(a04["file_ml_agc_status"].eq("scored").sum())),
        ("a04_primary_selected_unique_files", int(a04["file_ml_agc_like_primary"].fillna(0).eq(1).sum())),
        ("a04_mapping_warning_unique_files", int(a04["ml_fun_mapping_warning_present"].fillna(0).eq(1).sum())),
        ("d02_repo_month_file_rows", len(d02)),
        ("d02_unique_snapshot_files", join_diag["d02_unique_snapshot_files"]),
        ("b06_repo_month_rows", len(b06)),
        ("sample_specs", panel["sample_spec"].nunique()),
        ("mapping_specs", panel["mapping_spec"].nunique()),
        ("primary_selected_file_rows_expanded", int(primary_global["selected_file_rows"])),
        ("primary_selected_unique_snapshot_files", int(primary_global["selected_unique_snapshot_files"])),
        ("primary_selected_issue_total", int(primary_global["selected_issue_total"])),
        ("mapping_sensitivity_selected_unique_snapshot_files", int(mapping_global["selected_unique_snapshot_files"])),
        ("mapping_sensitivity_selected_issue_total", int(mapping_global["selected_issue_total"])),
        ("scope_sensitivity_repositories", len(sensitivity)),
        ("alias_policy_applied", clean(alias.iloc[0]["policy_id"])),
        ("hard_qc_failures", hard_failures),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    atomic_csv(summary_df, args.summary_output)

    metadata = {
        "script_version": SCRIPT_VERSION,
        "status": status,
        "created_at_utc": utc_now(),
        "inputs": {
            "a04_file": str(args.a04_file.resolve()),
            "a04_file_sha256": sha256_file(args.a04_file),
            "a04_summary_file": str(args.a04_summary_file.resolve()),
            "a04_summary_file_sha256": sha256_file(args.a04_summary_file),
            "a04_checks_file": str(args.a04_checks_file.resolve()),
            "a04_checks_file_sha256": sha256_file(args.a04_checks_file),
            "d02_file": str(args.d02_file.resolve()),
            "d02_file_sha256": sha256_file(args.d02_file),
            "d02_summary_file": str(args.d02_summary_file.resolve()),
            "d02_summary_file_sha256": sha256_file(args.d02_summary_file),
            "b06_panel_file": str(args.b06_panel_file.resolve()),
            "b06_panel_file_sha256": sha256_file(args.b06_panel_file),
            "scope_sensitivity_spec_file": str(args.scope_sensitivity_spec_file.resolve()),
            "scope_sensitivity_spec_file_sha256": sha256_file(args.scope_sensitivity_spec_file),
            "d02a_summary_file": str(args.d02a_summary_file.resolve()),
            "d02a_summary_file_sha256": sha256_file(args.d02a_summary_file),
            "alias_handling_spec_file": str(args.alias_handling_spec_file.resolve()),
            "alias_handling_spec_file_sha256": sha256_file(args.alias_handling_spec_file),
            "d02b_summary_file": str(args.d02b_summary_file.resolve()),
            "d02b_summary_file_sha256": sha256_file(args.d02b_summary_file),
        },
        "upstream_contracts": {
            "a04_run": a04_summary.get("run"),
            "a04_status": a04_summary.get("status"),
            "d02_run": d02_summary.get("script_version"),
            "d02_status": d02_summary.get("status"),
            "d02a_status": d02a_summary.get("status"),
            "d02b_status": d02b_summary.get("status"),
            "alias_policy": clean(alias.iloc[0]["policy_id"]),
        },
        "method": {
            "historical_file_key": "snapshot_id + relative_path + file_sha256",
            "join_cardinality": "D02 repo-month/file rows many-to-one A04 unique snapshot/files",
            "file_universe_equality": "unique D02 snapshot/files must equal A04 exactly",
            "primary_selection": f"{PRIMARY_ML_METRIC} {PRIMARY_ML_OPERATOR} {PRIMARY_ML_THRESHOLD}",
            "no_fun_policy": "A04 no_ml_fun remains unclassified and is never treated as HWC",
            "quality_source": "frozen D02 canonical historical Python SonarQube file-burden join",
            "quality_semantics": QUALITY_SEMANTICS,
            "primary_sample_spec": "full_sample",
            "primary_mapping_spec": "all_ml_files",
            "mapping_sensitivity": "exclude A04 ml_fun_mapping_warning_present == 1 from both eligible and selected sets",
            "scope_sensitivity": "reuse D02-a pre-specified repository exclusions",
            "density": "not computed; B06 ncloc_py_sonarqube remains a whole-snapshot covariate for downstream adjusted burden models",
            "did": "not estimated in D05; downstream D06 reuses validated Borusyak design",
        },
        "diagnostics": {**join_diag, "hard_qc_failures": hard_failures},
        "outputs": {
            "panel": str(args.panel_output.resolve()),
            "global_audit": str(args.global_audit_output.resolve()),
            "timing_audit": str(args.timing_audit_output.resolve()),
            "sample_summary": str(args.sample_summary_output.resolve()),
            "outcome_spec": str(args.outcome_spec_output.resolve()),
            "checks": str(args.checks_output.resolve()),
            "summary": str(args.summary_output.resolve()),
        },
    }
    atomic_json(metadata, args.metadata_output)

    if hard_failures:
        raise RuntimeError(f"D05 hard QC failures: {hard_failures}; see {args.checks_output}")

    print("=" * 80)
    print("run-x-d05 ML-selected Python quality-burden panel")
    print(f"Status:                              {status}")
    print(f"A04 unique historical files:        {len(a04)}")
    print(f"D02 repo-month/file rows:           {len(d02)}")
    print(f"B06 repo-month rows:                {len(b06)}")
    print(f"Primary ML-selected unique files:   {int(primary_global['selected_unique_snapshot_files'])}")
    print(f"Primary selected file rows:         {int(primary_global['selected_file_rows'])}")
    print(f"Primary selected issue stock:       {int(primary_global['selected_issue_total'])}")
    print(f"Mapping-sensitivity unique files:   {int(mapping_global['selected_unique_snapshot_files'])}")
    print(f"Mapping-sensitivity issue stock:    {int(mapping_global['selected_issue_total'])}")
    print(f"Failed hard checks:                 {hard_failures}")
    print(f"Panel:                              {args.panel_output}")
    print("=" * 80)
    return {"status": status, "hard_qc_failures": hard_failures}


def run_self_test() -> None:
    """Exercise strict selection, warning exclusion, zero burden, and log transforms."""
    files = pd.DataFrame(
        {
            "repo_id": [1, 1, 2, 2],
            "time_index": [1, 1, 1, 1],
            "python_lines": [10, 20, 30, 40],
            "sonar_issue_total": [3, 5, 0, 7],
            "sonar_issue_type_code_smell": [2, 4, 0, 5],
            "sonar_issue_type_bug": [1, 1, 0, 2],
            "sonar_issue_type_vulnerability": [0, 0, 0, 0],
            "sonar_issue_type_other": [0, 0, 0, 0],
            "sonar_issue_high_severity": [0, 1, 0, 1],
            "sonar_issue_with_maintainability_impact": [2, 4, 0, 5],
            "sonar_issue_with_reliability_impact": [1, 1, 0, 2],
            "sonar_issue_with_security_impact": [0, 0, 0, 0],
            "file_ml_agc_status": ["scored", "scored", "no_ml_fun", "scored"],
            "file_ml_agc_like_primary": [1, 1, np.nan, 0],
            "ml_fun_mapping_warning_present": [0, 1, 0, 0],
            "ml_fun_space_by_tokens_total": [100, 50, 0, 80],
            "ml_fun_agc_space_by_tokens": [80, 40, 0, 20],
        }
    )
    base_keys = pd.DataFrame({"repo_id": [1, 2, 3], "time_index": [1, 1, 1]})
    primary = aggregate_mapping_spec(files, base_keys, exclude_mapping_warnings=False).set_index(["repo_id", "time_index"])
    robust = aggregate_mapping_spec(files, base_keys, exclude_mapping_warnings=True).set_index(["repo_id", "time_index"])

    assert int(primary.loc[(1, 1), "eligible_ml_file_count"]) == 2
    assert int(primary.loc[(1, 1), "selected_file_count"]) == 2
    assert int(primary.loc[(1, 1), "selected_issue_total"]) == 8
    assert int(primary.loc[(1, 1), "mapping_warning_selected_file_count"]) == 1
    assert math.isclose(float(primary.loc[(1, 1), "log1p_selected_issue_total"]), math.log1p(8), abs_tol=1e-12)

    assert int(robust.loc[(1, 1), "eligible_ml_file_count"]) == 1
    assert int(robust.loc[(1, 1), "selected_file_count"]) == 1
    assert int(robust.loc[(1, 1), "selected_issue_total"]) == 3
    assert int(robust.loc[(1, 1), "mapping_warning_selected_file_count"]) == 0

    assert int(primary.loc[(2, 1), "eligible_ml_file_count"]) == 1
    assert int(primary.loc[(2, 1), "selected_file_count"]) == 0
    assert int(primary.loc[(3, 1), "selected_issue_total"]) == 0
    assert float(primary.loc[(3, 1), "log1p_selected_issue_total"]) == 0.0
    print("build_ml_fun_quality_burden_panel self-test: PASS")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build run-x-d05 ML-selected Python quality burden panel.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--a04-file", type=Path)
    parser.add_argument("--a04-summary-file", type=Path)
    parser.add_argument("--a04-checks-file", type=Path)
    parser.add_argument("--d02-file", type=Path)
    parser.add_argument("--d02-summary-file", type=Path)
    parser.add_argument("--b06-panel-file", type=Path)
    parser.add_argument("--scope-sensitivity-spec-file", type=Path)
    parser.add_argument("--d02a-summary-file", type=Path)
    parser.add_argument("--alias-handling-spec-file", type=Path)
    parser.add_argument("--d02b-summary-file", type=Path)
    parser.add_argument("--panel-output", type=Path)
    parser.add_argument("--global-audit-output", type=Path)
    parser.add_argument("--timing-audit-output", type=Path)
    parser.add_argument("--sample-summary-output", type=Path)
    parser.add_argument("--outcome-spec-output", type=Path)
    parser.add_argument("--checks-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--strict-expected-counts", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return args
    required = [
        "a04_file",
        "a04_summary_file",
        "a04_checks_file",
        "d02_file",
        "d02_summary_file",
        "b06_panel_file",
        "scope_sensitivity_spec_file",
        "d02a_summary_file",
        "alias_handling_spec_file",
        "d02b_summary_file",
        "panel_output",
        "global_audit_output",
        "timing_audit_output",
        "sample_summary_output",
        "outcome_spec_output",
        "checks_output",
        "summary_output",
        "metadata_output",
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
