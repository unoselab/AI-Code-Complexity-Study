#!/usr/bin/env python3
"""Audit recoverability of Python-only SonarQube issues from B01 snapshots.

This experiment does not run SonarScanner. It reuses the independent SonarQube
project key created for each B01 historical Python snapshot and verifies that
snapshot-specific issue information can still be retrieved reproducibly.

Primary audit questions:
1. Does the B01 SonarQube project still exist for the sampled snapshot?
2. Does the project analysis history identify the expected B01 analysis/version?
3. Does the current SonarQube NCLOC match the B01 stored NCLOC for that project?
4. Can the issues API return a snapshot-specific issue total and issue metadata?
5. Are sampled issue components restricted to Python files, as expected from
   the original sonar.inclusions=**/*.py scan scope?
6. Do paired early/late snapshots from the same repository remain independent
   SonarQube projects rather than a single overwritten project history?

The audit intentionally does not construct a quality outcome panel or run DiD.
Those are deferred until this feasibility check establishes that the B01
snapshot projects still provide reproducible quality information.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

IMPLEMENTATION_VERSION = "v1"
EXPECTED_SCAN_SCOPE = "python_only_sonar_inclusions"
REQUIRED_MANIFEST_COLUMNS = {
    "manifest_order",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "snapshot_key",
    "project_key",
    "project_version",
    "scan_scope",
    "status",
    "ncloc_py_sonarqube",
    "analysis_id",
    "first_panel_month",
    "last_panel_month",
}


class AuditError(RuntimeError):
    """Raised for an unrecoverable audit configuration or data error."""


@dataclass
class ApiResult:
    """Normalized result from one SonarQube Web API request."""

    ok: bool
    status_code: int | None
    data: dict[str, Any] | None
    error: str
    elapsed_seconds: float


class SonarClient:
    """Small SonarQube Web API client with bounded retries and timeouts."""

    def __init__(
        self,
        host: str,
        token: str,
        timeout_seconds: int,
        max_retries: int,
        retry_sleep_seconds: float,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def get(self, endpoint: str, params: dict[str, Any]) -> ApiResult:
        """GET one SonarQube endpoint and return a structured status."""
        url = f"{self.host}{endpoint}"
        last_error = ""
        last_status: int | None = None
        started = time.monotonic()

        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.session.get(
                    url, params=params, timeout=self.timeout_seconds
                )
                last_status = response.status_code
                if response.ok:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        return ApiResult(
                            False,
                            response.status_code,
                            None,
                            f"invalid_json: {exc}",
                            time.monotonic() - started,
                        )
                    return ApiResult(
                        True,
                        response.status_code,
                        payload,
                        "",
                        time.monotonic() - started,
                    )
                last_error = f"http_{response.status_code}: {response.text[:500]}"
            except requests.RequestException as exc:
                last_error = f"request_error: {exc}"

            if attempt <= self.max_retries:
                time.sleep(self.retry_sleep_seconds)

        return ApiResult(
            False,
            last_status,
            None,
            last_error,
            time.monotonic() - started,
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--completed-manifest-file",
        default=(
            "repo_x01/run-x-b01-sonarqube/"
            "model_c_ncloc_py_sonarqube_completed_manifest.csv"
        ),
    )
    parser.add_argument(
        "--audit-output",
        default=(
            "repo_x01/run-x-b04/python_sonarqube_issue_audit_sample.csv"
        ),
    )
    parser.add_argument(
        "--issue-samples-output",
        default=(
            "repo_x01/run-x-b04/python_sonarqube_issue_audit_issue_samples.csv"
        ),
    )
    parser.add_argument(
        "--pair-comparison-output",
        default=(
            "repo_x01/run-x-b04/python_sonarqube_issue_audit_pair_comparison.csv"
        ),
    )
    parser.add_argument(
        "--qc-output",
        default="repo_x01/run-x-b04/python_sonarqube_issue_audit_qc.csv",
    )
    parser.add_argument(
        "--summary-output",
        default="repo_x01/run-x-b04/python_sonarqube_issue_audit_summary.csv",
    )
    parser.add_argument(
        "--sample-manifest-output",
        default="repo_x01/run-x-b04/python_sonarqube_issue_audit_manifest.csv",
    )
    parser.add_argument(
        "--sonar-host", default=os.getenv("SONAR_HOST", "http://localhost:9000")
    )
    parser.add_argument("--repos-per-group", type=int, default=6)
    parser.add_argument("--issues-per-snapshot", type=int, default=25)
    parser.add_argument("--server-timeout-seconds", type=int, default=60)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Validate CLI options before any API access."""
    if args.repos_per_group < 1:
        raise AuditError("--repos-per-group must be at least 1")
    if args.issues_per_snapshot < 0:
        raise AuditError("--issues-per-snapshot must be non-negative")
    if args.server_timeout_seconds < 1:
        raise AuditError("--server-timeout-seconds must be at least 1")
    if args.max_retries < 0:
        raise AuditError("--max-retries must be non-negative")
    if args.retry_sleep_seconds < 0:
        raise AuditError("--retry-sleep-seconds must be non-negative")
    if not str(args.sonar_host).strip():
        raise AuditError("--sonar-host must not be empty")


def ensure_parent(path: str | Path) -> None:
    """Create the parent directory for an output path."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write a stable UTF-8 CSV, including headers for empty outputs."""
    ensure_parent(path)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def normalize_manifest(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the completed B01 SonarQube manifest."""
    missing = sorted(REQUIRED_MANIFEST_COLUMNS - set(df.columns))
    if missing:
        raise AuditError(f"completed manifest is missing columns: {missing}")

    out = df.copy()
    for column in [
        "dataset_source",
        "repo_name",
        "commit_sha",
        "snapshot_key",
        "project_key",
        "project_version",
        "scan_scope",
        "status",
        "analysis_id",
        "first_panel_month",
        "last_panel_month",
    ]:
        out[column] = out[column].fillna("").astype(str).str.strip()

    out["manifest_order"] = pd.to_numeric(out["manifest_order"], errors="coerce")
    out["ncloc_py_sonarqube"] = pd.to_numeric(
        out["ncloc_py_sonarqube"], errors="coerce"
    )

    successful = out[
        out["status"].eq("success")
        & out["project_key"].ne("")
        & out["snapshot_key"].ne("")
    ].copy()

    if successful.empty:
        raise AuditError("no successful B01 SonarQube snapshots were found")
    if successful["snapshot_key"].duplicated().any():
        duplicates = successful.loc[
            successful["snapshot_key"].duplicated(keep=False), "snapshot_key"
        ].head(10)
        raise AuditError(f"duplicate snapshot_key values: {duplicates.tolist()}")
    if successful["project_key"].duplicated().any():
        duplicates = successful.loc[
            successful["project_key"].duplicated(keep=False), "project_key"
        ].head(10)
        raise AuditError(f"duplicate project_key values: {duplicates.tolist()}")

    return successful.sort_values("manifest_order", kind="stable").reset_index(drop=True)


def month_sort_value(value: Any) -> int:
    """Convert YYYY-MM text to a sortable integer with a safe fallback."""
    text = str(value or "").strip()
    if len(text) >= 7 and text[4] == "-":
        try:
            return int(text[:4]) * 12 + int(text[5:7])
        except ValueError:
            pass
    return -1


def choose_representative_repos(group: pd.DataFrame, count: int) -> list[str]:
    """Choose repositories deterministically across the NCLOC size distribution."""
    repo_stats = (
        group.groupby("repo_name", as_index=False)
        .agg(
            snapshot_count=("snapshot_key", "size"),
            median_ncloc=("ncloc_py_sonarqube", "median"),
        )
        .query("snapshot_count >= 2")
        .sort_values(["median_ncloc", "repo_name"], kind="stable")
        .reset_index(drop=True)
    )
    if repo_stats.empty:
        raise AuditError("no repository has at least two successful snapshots")

    n = len(repo_stats)
    wanted = min(count, n)
    if wanted == 1:
        indices = [n // 2]
    else:
        indices = [round(i * (n - 1) / (wanted - 1)) for i in range(wanted)]

    # Preserve order while removing any duplicate index introduced by rounding.
    unique_indices: list[int] = []
    for index in indices:
        if index not in unique_indices:
            unique_indices.append(index)

    # Fill any rounding gap with the next unused repository.
    for index in range(n):
        if len(unique_indices) >= wanted:
            break
        if index not in unique_indices:
            unique_indices.append(index)

    return repo_stats.iloc[unique_indices[:wanted]]["repo_name"].tolist()


def build_audit_sample(manifest: pd.DataFrame, repos_per_group: int) -> pd.DataFrame:
    """Select paired early/late snapshots for size-diverse treatment/control repos."""
    rows: list[pd.Series] = []

    for dataset_source in ["control", "treatment"]:
        group = manifest[manifest["dataset_source"].eq(dataset_source)].copy()
        if group.empty:
            raise AuditError(f"no successful snapshots for {dataset_source}")

        selected_repos = choose_representative_repos(group, repos_per_group)
        for rank, repo_name in enumerate(selected_repos, start=1):
            repo_rows = group[group["repo_name"].eq(repo_name)].copy()
            repo_rows["_month_sort"] = repo_rows["first_panel_month"].map(month_sort_value)
            repo_rows = repo_rows.sort_values(
                ["_month_sort", "manifest_order"], kind="stable"
            )
            early = repo_rows.iloc[0].copy()
            late = repo_rows.iloc[-1].copy()
            for pair_position, item in [("early", early), ("late", late)]:
                item["sample_group"] = dataset_source
                item["sample_repo_rank"] = rank
                item["pair_position"] = pair_position
                rows.append(item)

    sample = pd.DataFrame(rows).drop(columns=["_month_sort"], errors="ignore")
    sample = sample.sort_values(
        ["sample_group", "sample_repo_rank", "pair_position"], kind="stable"
    ).reset_index(drop=True)
    sample["audit_order"] = range(1, len(sample) + 1)
    return sample


def extract_paging_total(data: dict[str, Any] | None) -> int | None:
    """Read paging.total from a SonarQube response."""
    if not data:
        return None
    paging = data.get("paging")
    if not isinstance(paging, dict):
        return None
    value = paging.get("total")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_measure_value(data: dict[str, Any] | None, metric: str) -> float | None:
    """Extract one numeric metric from api/measures/component."""
    if not data:
        return None
    component = data.get("component")
    if not isinstance(component, dict):
        return None
    measures = component.get("measures")
    if not isinstance(measures, list):
        return None
    for measure in measures:
        if isinstance(measure, dict) and measure.get("metric") == metric:
            try:
                return float(measure.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def collect_analyses(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return analysis dictionaries from project_analyses/search."""
    if not data:
        return []
    analyses = data.get("analyses")
    if not isinstance(analyses, list):
        return []
    return [item for item in analyses if isinstance(item, dict)]


def analysis_key(analysis: dict[str, Any]) -> str:
    """Read an analysis identifier across SonarQube response variants."""
    return str(analysis.get("key") or analysis.get("analysisId") or "").strip()


def project_version(analysis: dict[str, Any]) -> str:
    """Read project version from one analysis response object."""
    return str(analysis.get("projectVersion") or "").strip()


def component_path_map(data: dict[str, Any] | None) -> dict[str, str]:
    """Map component keys to paths from an issues/search response."""
    if not data:
        return {}
    components = data.get("components")
    if not isinstance(components, list):
        return {}
    mapping: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        key = str(component.get("key") or "").strip()
        path = str(component.get("path") or "").strip()
        if key:
            mapping[key] = path
    return mapping


def infer_component_path(component_key: str, project_key: str) -> str:
    """Fallback path extraction when the response omits components metadata."""
    prefix = f"{project_key}:"
    if component_key.startswith(prefix):
        return component_key[len(prefix) :]
    return ""


def normalize_issue_sample(
    data: dict[str, Any] | None,
    project_key: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    """Normalize up to max_rows issue records from one search response."""
    if not data or max_rows <= 0:
        return []
    issues = data.get("issues")
    if not isinstance(issues, list):
        return []
    paths = component_path_map(data)
    normalized: list[dict[str, Any]] = []

    for issue in issues[:max_rows]:
        if not isinstance(issue, dict):
            continue
        component_key = str(issue.get("component") or "").strip()
        path = paths.get(component_key, "") or infer_component_path(
            component_key, project_key
        )
        impacts = issue.get("impacts")
        if impacts is None:
            impacts_text = ""
        else:
            impacts_text = json.dumps(impacts, sort_keys=True, ensure_ascii=False)
        normalized.append(
            {
                "issue_key": str(issue.get("key") or ""),
                "rule": str(issue.get("rule") or ""),
                "type": str(issue.get("type") or ""),
                "severity": str(issue.get("severity") or ""),
                "status": str(issue.get("status") or ""),
                "resolution": str(issue.get("resolution") or ""),
                "component": component_key,
                "component_path": path,
                "component_is_python": bool(path.lower().endswith(".py")),
                "message": str(issue.get("message") or ""),
                "line": issue.get("line"),
                "creation_date": str(issue.get("creationDate") or ""),
                "update_date": str(issue.get("updateDate") or ""),
                "clean_code_attribute": str(issue.get("cleanCodeAttribute") or ""),
                "impacts_json": impacts_text,
            }
        )
    return normalized


def api_status(result: ApiResult) -> str:
    """Return a compact API status label."""
    if result.ok:
        return "success"
    if result.status_code == 404:
        return "not_found"
    return "error"


def audit_snapshot(
    row: pd.Series,
    client: SonarClient,
    issues_per_snapshot: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Audit one B01 snapshot project and return summary plus issue samples."""
    project_key_value = str(row["project_key"])
    manifest_analysis_id = str(row["analysis_id"])
    manifest_project_version = str(row["project_version"])

    component = client.get(
        "/api/components/show", {"component": project_key_value}
    )
    analyses = client.get(
        "/api/project_analyses/search",
        {"project": project_key_value, "category": "VERSION", "ps": 100},
    )
    ncloc = client.get(
        "/api/measures/component",
        {"component": project_key_value, "metricKeys": "ncloc"},
    )
    issues_default = client.get(
        "/api/issues/search",
        {
            "componentKeys": project_key_value,
            "p": 1,
            "ps": max(1, min(100, issues_per_snapshot or 1)),
        },
    )
    issues_unresolved = client.get(
        "/api/issues/search",
        {"componentKeys": project_key_value, "resolved": "false", "p": 1, "ps": 1},
    )
    issues_resolved = client.get(
        "/api/issues/search",
        {"componentKeys": project_key_value, "resolved": "true", "p": 1, "ps": 1},
    )

    analysis_rows = collect_analyses(analyses.data)
    analysis_ids = [analysis_key(item) for item in analysis_rows]
    versions = [project_version(item) for item in analysis_rows]
    manifest_analysis_found = bool(
        manifest_analysis_id and manifest_analysis_id in analysis_ids
    )
    expected_version_found = bool(
        manifest_project_version and manifest_project_version in versions
    )

    observed_ncloc = extract_measure_value(ncloc.data, "ncloc")
    manifest_ncloc = row.get("ncloc_py_sonarqube")
    try:
        manifest_ncloc_float = float(manifest_ncloc)
    except (TypeError, ValueError):
        manifest_ncloc_float = math.nan
    ncloc_matches = (
        observed_ncloc is not None
        and not math.isnan(manifest_ncloc_float)
        and abs(observed_ncloc - manifest_ncloc_float) < 1e-9
    )

    issue_rows = normalize_issue_sample(
        issues_default.data, project_key_value, issues_per_snapshot
    )
    for issue in issue_rows:
        issue.update(
            {
                "audit_order": int(row["audit_order"]),
                "sample_group": row["sample_group"],
                "sample_repo_rank": int(row["sample_repo_rank"]),
                "pair_position": row["pair_position"],
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "snapshot_key": row["snapshot_key"],
                "commit_sha": row["commit_sha"],
                "project_key": project_key_value,
                "manifest_analysis_id": manifest_analysis_id,
            }
        )

    issue_components_all_python = (
        True
        if not issue_rows
        else all(bool(issue["component_is_python"]) for issue in issue_rows)
    )
    issue_components_same_project = (
        True
        if not issue_rows
        else all(
            str(issue["component"]) == project_key_value
            or str(issue["component"]).startswith(f"{project_key_value}:")
            for issue in issue_rows
        )
    )

    default_total = extract_paging_total(issues_default.data)
    unresolved_total = extract_paging_total(issues_unresolved.data)
    resolved_total = extract_paging_total(issues_resolved.data)

    current_snapshot_recoverable = bool(
        component.ok
        and analyses.ok
        and ncloc.ok
        and issues_default.ok
        and ncloc_matches
        and expected_version_found
        and issue_components_same_project
    )

    summary = {
        "audit_order": int(row["audit_order"]),
        "sample_group": row["sample_group"],
        "sample_repo_rank": int(row["sample_repo_rank"]),
        "pair_position": row["pair_position"],
        "dataset_source": row["dataset_source"],
        "repo_name": row["repo_name"],
        "snapshot_key": row["snapshot_key"],
        "commit_sha": row["commit_sha"],
        "first_panel_month": row["first_panel_month"],
        "last_panel_month": row["last_panel_month"],
        "project_key": project_key_value,
        "manifest_project_version": manifest_project_version,
        "manifest_analysis_id": manifest_analysis_id,
        "manifest_ncloc_py_sonarqube": manifest_ncloc_float,
        "scan_scope": row["scan_scope"],
        "component_api_status": api_status(component),
        "analyses_api_status": api_status(analyses),
        "measure_api_status": api_status(ncloc),
        "issues_default_api_status": api_status(issues_default),
        "issues_unresolved_api_status": api_status(issues_unresolved),
        "issues_resolved_api_status": api_status(issues_resolved),
        "analysis_count": len(analysis_rows),
        "manifest_analysis_found": manifest_analysis_found,
        "expected_project_version_found": expected_version_found,
        "analysis_ids": " | ".join(analysis_ids),
        "analysis_project_versions": " | ".join(versions),
        "observed_ncloc": observed_ncloc,
        "ncloc_matches_manifest": ncloc_matches,
        "issue_total_default": default_total,
        "issue_total_unresolved": unresolved_total,
        "issue_total_resolved": resolved_total,
        "issue_sample_rows": len(issue_rows),
        "issue_sample_components_all_python": issue_components_all_python,
        "issue_sample_components_same_project": issue_components_same_project,
        "current_snapshot_recoverable": current_snapshot_recoverable,
        "component_error": component.error,
        "analyses_error": analyses.error,
        "measure_error": ncloc.error,
        "issues_default_error": issues_default.error,
        "issues_unresolved_error": issues_unresolved.error,
        "issues_resolved_error": issues_resolved.error,
    }
    return summary, issue_rows


def build_pair_comparison(audit: pd.DataFrame) -> pd.DataFrame:
    """Compare early and late independent SonarQube projects within each repo."""
    rows: list[dict[str, Any]] = []
    for (group, rank, repo_name), part in audit.groupby(
        ["sample_group", "sample_repo_rank", "repo_name"], sort=True
    ):
        early = part[part["pair_position"].eq("early")]
        late = part[part["pair_position"].eq("late")]
        if len(early) != 1 or len(late) != 1:
            continue
        e = early.iloc[0]
        l = late.iloc[0]
        early_total = pd.to_numeric(e["issue_total_default"], errors="coerce")
        late_total = pd.to_numeric(l["issue_total_default"], errors="coerce")
        rows.append(
            {
                "sample_group": group,
                "sample_repo_rank": rank,
                "repo_name": repo_name,
                "early_snapshot_key": e["snapshot_key"],
                "late_snapshot_key": l["snapshot_key"],
                "early_commit_sha": e["commit_sha"],
                "late_commit_sha": l["commit_sha"],
                "early_project_key": e["project_key"],
                "late_project_key": l["project_key"],
                "project_keys_distinct": e["project_key"] != l["project_key"],
                "manifest_analysis_ids_distinct": (
                    e["manifest_analysis_id"] != l["manifest_analysis_id"]
                ),
                "project_versions_distinct": (
                    e["manifest_project_version"] != l["manifest_project_version"]
                ),
                "early_recoverable": bool(e["current_snapshot_recoverable"]),
                "late_recoverable": bool(l["current_snapshot_recoverable"]),
                "early_issue_total": early_total,
                "late_issue_total": late_total,
                "issue_total_difference": (
                    late_total - early_total
                    if pd.notna(early_total) and pd.notna(late_total)
                    else math.nan
                ),
                "early_ncloc": e["observed_ncloc"],
                "late_ncloc": l["observed_ncloc"],
            }
        )
    return pd.DataFrame(rows)


def qc_row(check: str, value: Any, expected: Any, status: str, detail: str = "") -> dict[str, Any]:
    """Create one QC record."""
    return {
        "check": check,
        "value": value,
        "expected": expected,
        "status": status,
        "detail": detail,
    }


def build_qc(
    manifest: pd.DataFrame,
    sample: pd.DataFrame,
    audit: pd.DataFrame,
    issues: pd.DataFrame,
    pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Build hard-fail and warning checks for the B04 audit."""
    rows: list[dict[str, Any]] = []
    expected_sample = len(sample)

    rows.append(qc_row("successful_b01_snapshots", len(manifest), "> 0", "pass"))
    rows.append(
        qc_row(
            "sample_snapshots",
            len(audit),
            expected_sample,
            "pass" if len(audit) == expected_sample else "fail",
        )
    )
    rows.append(
        qc_row(
            "sample_unique_project_keys",
            audit["project_key"].nunique(),
            expected_sample,
            "pass" if audit["project_key"].nunique() == expected_sample else "fail",
        )
    )
    rows.append(
        qc_row(
            "projects_recoverable",
            int(audit["current_snapshot_recoverable"].sum()),
            expected_sample,
            "pass"
            if bool(audit["current_snapshot_recoverable"].all())
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "expected_project_versions_found",
            int(audit["expected_project_version_found"].sum()),
            expected_sample,
            "pass" if bool(audit["expected_project_version_found"].all()) else "fail",
        )
    )
    rows.append(
        qc_row(
            "manifest_analysis_ids_found",
            int(audit["manifest_analysis_found"].sum()),
            expected_sample,
            "pass" if bool(audit["manifest_analysis_found"].all()) else "warn",
            "A rerun can create a newer analysis ID while preserving the same project version.",
        )
    )
    rows.append(
        qc_row(
            "ncloc_matches_b01_manifest",
            int(audit["ncloc_matches_manifest"].sum()),
            expected_sample,
            "pass" if bool(audit["ncloc_matches_manifest"].all()) else "fail",
        )
    )
    rows.append(
        qc_row(
            "issues_api_success",
            int(audit["issues_default_api_status"].eq("success").sum()),
            expected_sample,
            "pass"
            if bool(audit["issues_default_api_status"].eq("success").all())
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "sample_issue_components_same_project",
            int(audit["issue_sample_components_same_project"].sum()),
            expected_sample,
            "pass"
            if bool(audit["issue_sample_components_same_project"].all())
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "sample_issue_components_all_python",
            int(audit["issue_sample_components_all_python"].sum()),
            expected_sample,
            "pass"
            if bool(audit["issue_sample_components_all_python"].all())
            else "warn",
            "Project-level or analyzer metadata issues may not have a .py file path.",
        )
    )
    if not pairs.empty:
        pair_count = len(pairs)
        rows.append(
            qc_row(
                "paired_projects_distinct",
                int(pairs["project_keys_distinct"].sum()),
                pair_count,
                "pass" if bool(pairs["project_keys_distinct"].all()) else "fail",
            )
        )
        rows.append(
            qc_row(
                "paired_project_versions_distinct",
                int(pairs["project_versions_distinct"].sum()),
                pair_count,
                "pass" if bool(pairs["project_versions_distinct"].all()) else "warn",
                "Equal commits can legitimately cover multiple carried-forward months.",
            )
        )
    else:
        rows.append(qc_row("paired_projects_distinct", 0, "> 0", "fail"))

    unresolved_mismatch = audit[
        audit["issue_total_default"].notna()
        & audit["issue_total_unresolved"].notna()
        & (audit["issue_total_default"] != audit["issue_total_unresolved"])
    ]
    rows.append(
        qc_row(
            "default_vs_unresolved_issue_total_mismatches",
            len(unresolved_mismatch),
            0,
            "pass" if unresolved_mismatch.empty else "warn",
            "A mismatch can indicate resolved issues or API default-filter semantics.",
        )
    )

    nonzero_resolved = audit[
        pd.to_numeric(audit["issue_total_resolved"], errors="coerce").fillna(0) > 0
    ]
    rows.append(
        qc_row(
            "snapshots_with_resolved_issues",
            len(nonzero_resolved),
            0,
            "pass" if nonzero_resolved.empty else "warn",
            "Resolved issue state should be reviewed before defining the B05 quality count.",
        )
    )

    rows.append(qc_row("sample_issue_rows_saved", len(issues), ">= 0", "pass"))
    return pd.DataFrame(rows)


def build_summary(
    manifest: pd.DataFrame,
    sample: pd.DataFrame,
    audit: pd.DataFrame,
    issues: pd.DataFrame,
    pairs: pd.DataFrame,
    qc: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact key-value summary."""
    metrics: list[tuple[str, Any]] = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("successful_b01_snapshots", len(manifest)),
        ("successful_b01_repositories", manifest["repo_name"].nunique()),
        ("audit_sample_snapshots", len(sample)),
        ("audit_sample_repositories", sample["repo_name"].nunique()),
        ("audit_control_snapshots", int(sample["dataset_source"].eq("control").sum())),
        ("audit_treatment_snapshots", int(sample["dataset_source"].eq("treatment").sum())),
        ("recoverable_snapshots", int(audit["current_snapshot_recoverable"].sum())),
        ("issues_api_success_snapshots", int(audit["issues_default_api_status"].eq("success").sum())),
        ("sample_issue_rows_saved", len(issues)),
        ("paired_repositories", len(pairs)),
        ("qc_failures", int(qc["status"].eq("fail").sum())),
        ("qc_warnings", int(qc["status"].eq("warn").sum())),
    ]

    if audit["issue_total_default"].notna().any():
        numeric = pd.to_numeric(audit["issue_total_default"], errors="coerce")
        metrics.extend(
            [
                ("issue_total_min", numeric.min()),
                ("issue_total_median", numeric.median()),
                ("issue_total_max", numeric.max()),
            ]
        )

    return pd.DataFrame(metrics, columns=["metric", "value"])


def run_self_test() -> None:
    """Run deterministic offline tests for selection and response parsing."""
    synthetic_rows: list[dict[str, Any]] = []
    order = 1
    for source in ["control", "treatment"]:
        for repo_idx in range(1, 5):
            for month_idx, month in enumerate(["2024-01", "2024-02", "2024-03"]):
                commit = f"{source[0]}{repo_idx}{month_idx}".ljust(40, "a")
                synthetic_rows.append(
                    {
                        "manifest_order": order,
                        "dataset_source": source,
                        "repo_name": f"org/{source}-{repo_idx}",
                        "commit_sha": commit,
                        "snapshot_key": f"{source}-{repo_idx}-{month_idx}",
                        "project_key": f"project-{source}-{repo_idx}-{month_idx}",
                        "project_version": commit,
                        "scan_scope": EXPECTED_SCAN_SCOPE,
                        "status": "success",
                        "ncloc_py_sonarqube": repo_idx * 100 + month_idx,
                        "analysis_id": f"analysis-{source}-{repo_idx}-{month_idx}",
                        "first_panel_month": month,
                        "last_panel_month": month,
                    }
                )
                order += 1
    manifest = normalize_manifest(pd.DataFrame(synthetic_rows))
    sample = build_audit_sample(manifest, repos_per_group=3)
    assert len(sample) == 12, len(sample)
    assert sample["repo_name"].nunique() == 6
    assert set(sample["pair_position"]) == {"early", "late"}

    measure = {
        "component": {
            "measures": [
                {"metric": "ncloc", "value": "123"},
                {"metric": "other", "value": "7"},
            ]
        }
    }
    assert extract_measure_value(measure, "ncloc") == 123.0
    assert extract_paging_total({"paging": {"total": 42}}) == 42

    issue_response = {
        "issues": [
            {
                "key": "I1",
                "component": "project-x:src/a.py",
                "rule": "python:S1",
                "message": "Example",
            }
        ],
        "components": [{"key": "project-x:src/a.py", "path": "src/a.py"}],
    }
    issues = normalize_issue_sample(issue_response, "project-x", 25)
    assert len(issues) == 1
    assert issues[0]["component_is_python"] is True
    assert issues[0]["component_path"] == "src/a.py"

    analyses = [{"key": "A1", "projectVersion": "abc"}]
    assert analysis_key(analyses[0]) == "A1"
    assert project_version(analyses[0]) == "abc"
    print("self-test passed")


def main() -> int:
    """Run the B04 historical SonarQube issue recoverability audit."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        validate_args(args)
        if args.self_test:
            run_self_test()
            return 0

        token = os.getenv("SONAR_TOKEN", "").strip()
        if not token:
            raise AuditError("SONAR_TOKEN must be set in the environment")

        logging.info("Reading completed B01 manifest: %s", args.completed_manifest_file)
        manifest = normalize_manifest(pd.read_csv(args.completed_manifest_file))
        sample = build_audit_sample(manifest, args.repos_per_group)
        write_csv(sample, args.sample_manifest_output)

        logging.info(
            "Selected %d snapshots from %d repositories for API audit",
            len(sample),
            sample["repo_name"].nunique(),
        )

        client = SonarClient(
            host=args.sonar_host,
            token=token,
            timeout_seconds=args.server_timeout_seconds,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )

        audit_rows: list[dict[str, Any]] = []
        issue_rows: list[dict[str, Any]] = []
        for _, row in sample.iterrows():
            logging.info(
                "Auditing %d/%d: %s %s %s",
                int(row["audit_order"]),
                len(sample),
                row["dataset_source"],
                row["repo_name"],
                row["pair_position"],
            )
            summary, issues = audit_snapshot(row, client, args.issues_per_snapshot)
            audit_rows.append(summary)
            issue_rows.extend(issues)

        audit = pd.DataFrame(audit_rows)
        issue_columns = [
            "audit_order",
            "sample_group",
            "sample_repo_rank",
            "pair_position",
            "dataset_source",
            "repo_name",
            "snapshot_key",
            "commit_sha",
            "project_key",
            "manifest_analysis_id",
            "issue_key",
            "rule",
            "type",
            "severity",
            "status",
            "resolution",
            "component",
            "component_path",
            "component_is_python",
            "message",
            "line",
            "creation_date",
            "update_date",
            "clean_code_attribute",
            "impacts_json",
        ]
        issues = pd.DataFrame(issue_rows, columns=issue_columns)
        pairs = build_pair_comparison(audit)
        qc = build_qc(manifest, sample, audit, issues, pairs)
        summary = build_summary(manifest, sample, audit, issues, pairs, qc)

        write_csv(audit, args.audit_output)
        write_csv(issues, args.issue_samples_output)
        write_csv(pairs, args.pair_comparison_output)
        write_csv(qc, args.qc_output)
        write_csv(summary, args.summary_output)

        failures = qc[qc["status"].eq("fail")]
        warnings = qc[qc["status"].eq("warn")]
        logging.info(
            "Completed B04 audit: sample=%d; repos=%d; recoverable=%d; "
            "issue samples=%d; QC failures=%d; warnings=%d",
            len(audit),
            audit["repo_name"].nunique(),
            int(audit["current_snapshot_recoverable"].sum()),
            len(issues),
            len(failures),
            len(warnings),
        )

        if args.strict and not failures.empty:
            logging.error("Strict QC failures:\n%s", failures.to_string(index=False))
            return 3
        return 0
    except (AuditError, FileNotFoundError, pd.errors.ParserError) as exc:
        logging.error("B04 audit failed: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
