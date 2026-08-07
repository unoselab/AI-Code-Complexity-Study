#!/usr/bin/env python3
"""Collect full Python-only SonarQube issue stocks for B01 historical snapshots.

B05 does not run SonarScanner. It reuses the independent snapshot-level
SonarQube projects created by run-x-b01 and queries their current issue stock.
Each successful B01 project represents one historical Git snapshot that was
scanned with sonar.inclusions=**/*.py.

Primary measurement:
    issue_total_py_sonarqube
        Number of unresolved SonarQube issues present in the independent
        Python-only snapshot project.

The script also stores issue-level metadata, snapshot-by-rule counts, legacy
issue type/severity counts, Clean Code attributes, software-quality impacts,
Python NCLOC, and issue density. Raw issues are written as gzip-compressed CSV.

Important interpretation:
    This measures the issue stock present in each historical source snapshot.
    SonarQube issue creationDate reflects the later B01 scan execution time and
    must not be interpreted as the historical date when the defect was added.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import logging
import math
import os
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

IMPLEMENTATION_VERSION = "v1"
EXPECTED_SCAN_SCOPE = "python_only_sonar_inclusions"
DEFAULT_EXPECTED_SNAPSHOTS = 1496
DEFAULT_EXPECTED_REPOSITORIES = 167
DEFAULT_EXPECTED_TREATMENT = 790
DEFAULT_EXPECTED_CONTROL = 706
DEFAULT_PAGE_SIZE = 500
DEFAULT_MAX_RESULT_WINDOW = 10000
LEGACY_TYPES = ["BUG", "VULNERABILITY", "CODE_SMELL"]
LEGACY_SEVERITIES = ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]
SOFTWARE_QUALITIES = ["MAINTAINABILITY", "RELIABILITY", "SECURITY"]

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

ISSUE_COLUMNS = [
    "manifest_order",
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
    "component_scope",
    "message",
    "line",
    "creation_date",
    "update_date",
    "clean_code_attribute",
    "impacts_json",
]

RULE_COUNT_COLUMNS = [
    "manifest_order",
    "dataset_source",
    "repo_name",
    "snapshot_key",
    "commit_sha",
    "project_key",
    "rule",
    "type",
    "severity",
    "clean_code_attribute",
    "impact_signature",
    "issue_count",
]


class CollectionError(RuntimeError):
    """Raised when an input or API invariant prevents reliable collection."""


@dataclass
class ApiResult:
    """Structured result from one SonarQube Web API request."""

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
        """GET one endpoint and return a structured status."""
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
        "--snapshot-counts-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv",
    )
    parser.add_argument(
        "--issues-output",
        default="repo_x01/run-x-b05/python_sonarqube_issues.csv.gz",
    )
    parser.add_argument(
        "--rule-counts-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_rule_counts.csv.gz",
    )
    parser.add_argument(
        "--rule-definitions-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_rule_definitions.csv",
    )
    parser.add_argument(
        "--unresolved-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_unresolved.csv",
    )
    parser.add_argument(
        "--qc-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_qc.csv",
    )
    parser.add_argument(
        "--summary-output",
        default="repo_x01/run-x-b05/python_sonarqube_issue_summary.csv",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="repo_x01/tmp/run-x-b05/checkpoints",
    )
    parser.add_argument(
        "--sonar-host", default=os.getenv("SONAR_HOST", "http://localhost:9000")
    )
    parser.add_argument("--server-timeout-seconds", type=int, default=60)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument(
        "--max-result-window", type=int, default=DEFAULT_MAX_RESULT_WINDOW
    )
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dataset-source", choices=["treatment", "control"])
    parser.add_argument("--repo-name")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--expected-snapshots", type=int, default=DEFAULT_EXPECTED_SNAPSHOTS
    )
    parser.add_argument(
        "--expected-repositories", type=int, default=DEFAULT_EXPECTED_REPOSITORIES
    )
    parser.add_argument(
        "--expected-treatment", type=int, default=DEFAULT_EXPECTED_TREATMENT
    )
    parser.add_argument(
        "--expected-control", type=int, default=DEFAULT_EXPECTED_CONTROL
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-checkpoints", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Validate CLI options before API access."""
    if args.server_timeout_seconds < 1:
        raise CollectionError("--server-timeout-seconds must be at least 1")
    if args.max_retries < 0:
        raise CollectionError("--max-retries must be non-negative")
    if args.retry_sleep_seconds < 0:
        raise CollectionError("--retry-sleep-seconds must be non-negative")
    if args.page_size < 1 or args.page_size > 500:
        raise CollectionError("--page-size must be between 1 and 500")
    if args.max_result_window < args.page_size:
        raise CollectionError("--max-result-window must be >= --page-size")
    if args.start_order < 1:
        raise CollectionError("--start-order must be at least 1")
    if args.limit < 0:
        raise CollectionError("--limit must be non-negative")
    if args.progress_every < 1:
        raise CollectionError("--progress-every must be at least 1")
    if not str(args.sonar_host).strip():
        raise CollectionError("--sonar-host must not be empty")


def ensure_parent(path: str | Path) -> None:
    """Create the parent directory for an output path."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write a stable UTF-8 CSV with a header even when empty."""
    ensure_parent(path)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def normalize_manifest(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the successful B01 SonarQube manifest."""
    missing = sorted(REQUIRED_MANIFEST_COLUMNS - set(df.columns))
    if missing:
        raise CollectionError(f"completed manifest is missing columns: {missing}")

    out = df.copy()
    text_columns = [
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
    ]
    for column in text_columns:
        out[column] = out[column].fillna("").astype(str).str.strip()

    out["manifest_order"] = pd.to_numeric(out["manifest_order"], errors="coerce")
    out["ncloc_py_sonarqube"] = pd.to_numeric(
        out["ncloc_py_sonarqube"], errors="coerce"
    )
    successful = out[
        out["status"].eq("success")
        & out["snapshot_key"].ne("")
        & out["project_key"].ne("")
    ].copy()
    if successful.empty:
        raise CollectionError("no successful B01 SonarQube snapshots were found")
    if successful["manifest_order"].isna().any():
        raise CollectionError("manifest_order contains non-numeric values")
    successful["manifest_order"] = successful["manifest_order"].astype(int)
    if successful["snapshot_key"].duplicated().any():
        values = successful.loc[
            successful["snapshot_key"].duplicated(keep=False), "snapshot_key"
        ].head(10)
        raise CollectionError(f"duplicate snapshot_key values: {values.tolist()}")
    if successful["project_key"].duplicated().any():
        values = successful.loc[
            successful["project_key"].duplicated(keep=False), "project_key"
        ].head(10)
        raise CollectionError(f"duplicate project_key values: {values.tolist()}")
    return successful.sort_values("manifest_order", kind="stable").reset_index(drop=True)


def select_manifest(manifest: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    """Apply optional smoke-test filters while preserving manifest order."""
    selected = manifest[manifest["manifest_order"] >= args.start_order].copy()
    if args.dataset_source:
        selected = selected[selected["dataset_source"].eq(args.dataset_source)].copy()
    if args.repo_name:
        selected = selected[selected["repo_name"].eq(args.repo_name)].copy()
    selected = selected.sort_values("manifest_order", kind="stable")
    if args.limit:
        selected = selected.head(args.limit).copy()
    if selected.empty:
        raise CollectionError("no snapshots remain after filters")
    return selected.reset_index(drop=True)


def sha256_text(text: str) -> str:
    """Return a deterministic short hash for a text key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def checkpoint_path(checkpoint_dir: Path, snapshot_key: str) -> Path:
    """Return a filesystem-safe checkpoint path for one snapshot."""
    return checkpoint_dir / f"{sha256_text(snapshot_key)}.json.gz"


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write one gzip-compressed snapshot checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, delete=False, prefix=f".{path.name}.", suffix=".tmp"
    ) as handle:
        temp_path = Path(handle.name)
    try:
        with gzip.open(temp_path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def read_checkpoint(path: Path) -> dict[str, Any] | None:
    """Read one checkpoint, returning None if it is missing or invalid."""
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None
        return payload
    except (OSError, json.JSONDecodeError):
        return None


def extract_measure_value(data: dict[str, Any] | None, metric: str) -> float | None:
    """Extract one numeric measure from api/measures/component."""
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
    """Read an analysis ID across SonarQube response variants."""
    return str(analysis.get("key") or analysis.get("analysisId") or "").strip()


def analysis_version(analysis: dict[str, Any]) -> str:
    """Read projectVersion from one analysis object."""
    return str(analysis.get("projectVersion") or "").strip()


def extract_paging_total(data: dict[str, Any] | None) -> int | None:
    """Read paging.total from a SonarQube response."""
    if not data:
        return None
    paging = data.get("paging")
    if not isinstance(paging, dict):
        return None
    try:
        return int(paging.get("total"))
    except (TypeError, ValueError):
        return None


def component_path_map(data: dict[str, Any] | None) -> dict[str, str]:
    """Map issue component keys to source paths for one response page."""
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
    """Infer a file path when the response omits component metadata."""
    prefix = f"{project_key}:"
    if component_key.startswith(prefix):
        return component_key[len(prefix) :]
    return ""


def component_scope(component_key: str, path: str, project_key: str) -> str:
    """Classify an issue component for Python-scope QC."""
    if path.lower().endswith(".py"):
        return "python_file"
    if component_key == project_key and not path:
        return "project"
    if path:
        return "non_python"
    return "unknown"


def normalize_impacts(value: Any) -> list[dict[str, str]]:
    """Normalize SonarQube impact objects to stable uppercase strings."""
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        quality = str(item.get("softwareQuality") or "").strip().upper()
        severity = str(item.get("severity") or "").strip().upper()
        if quality or severity:
            normalized.append({"softwareQuality": quality, "severity": severity})
    normalized.sort(key=lambda item: (item["softwareQuality"], item["severity"]))
    return normalized


def normalize_issue(
    issue: dict[str, Any], data: dict[str, Any], project_key: str
) -> dict[str, Any]:
    """Normalize one SonarQube issue record."""
    paths = component_path_map(data)
    component_key = str(issue.get("component") or "").strip()
    path = paths.get(component_key, "") or infer_component_path(component_key, project_key)
    impacts = normalize_impacts(issue.get("impacts"))
    return {
        "issue_key": str(issue.get("key") or ""),
        "rule": str(issue.get("rule") or ""),
        "type": str(issue.get("type") or "").upper(),
        "severity": str(issue.get("severity") or "").upper(),
        "status": str(issue.get("status") or "").upper(),
        "resolution": str(issue.get("resolution") or "").upper(),
        "component": component_key,
        "component_path": path,
        "component_scope": component_scope(component_key, path, project_key),
        "message": str(issue.get("message") or ""),
        "line": issue.get("line"),
        "creation_date": str(issue.get("creationDate") or ""),
        "update_date": str(issue.get("updateDate") or ""),
        "clean_code_attribute": str(issue.get("cleanCodeAttribute") or "").upper(),
        "impacts": impacts,
    }


def issue_query(
    client: SonarClient,
    project_key: str,
    page: int,
    page_size: int,
    extra: dict[str, Any] | None = None,
) -> ApiResult:
    """Query unresolved issues for one independent snapshot project."""
    params: dict[str, Any] = {
        "componentKeys": project_key,
        "resolved": "false",
        "p": page,
        "ps": page_size,
    }
    if extra:
        params.update(extra)
    return client.get("/api/issues/search", params)


def fetch_partition(
    client: SonarClient,
    project_key: str,
    page_size: int,
    max_result_window: int,
    extra: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int, str]:
    """Fetch one issue partition when its total fits the API result window."""
    first = issue_query(client, project_key, 1, page_size, extra)
    if not first.ok:
        return [], -1, first.error
    total = extract_paging_total(first.data)
    if total is None:
        return [], -1, "missing_paging_total"
    if total > max_result_window:
        return [], total, "result_window_exceeded"

    issues: list[dict[str, Any]] = []
    page = 1
    result = first
    while True:
        data = result.data or {}
        page_issues = data.get("issues")
        if not isinstance(page_issues, list):
            return [], total, "missing_issues_list"
        for issue in page_issues:
            if isinstance(issue, dict):
                issues.append(normalize_issue(issue, data, project_key))
        if len(issues) >= total or len(page_issues) < page_size:
            break
        page += 1
        result = issue_query(client, project_key, page, page_size, extra)
        if not result.ok:
            return [], total, result.error
    if len(issues) != total:
        return issues, total, f"row_total_mismatch:{len(issues)}!={total}"
    return issues, total, ""


def fetch_all_unresolved_issues(
    client: SonarClient,
    project_key: str,
    page_size: int,
    max_result_window: int,
) -> tuple[list[dict[str, Any]], int, str, str]:
    """Fetch all unresolved issues, partitioning only when the API window requires it."""
    issues, total, error = fetch_partition(
        client, project_key, page_size, max_result_window
    )
    if error != "result_window_exceeded":
        return issues, total, error, "direct"

    # Large projects are first partitioned by legacy severity. This preserves
    # disjoint buckets and avoids the common SonarQube 10,000-result window.
    combined: list[dict[str, Any]] = []
    severity_total = 0
    for severity in LEGACY_SEVERITIES:
        part, part_total, part_error = fetch_partition(
            client,
            project_key,
            page_size,
            max_result_window,
            {"severities": severity},
        )
        if part_error == "result_window_exceeded":
            # Extremely large severity buckets are subdivided by legacy issue
            # type. B04 confirmed these types are present in the B01 projects.
            type_combined: list[dict[str, Any]] = []
            type_total = 0
            for issue_type in LEGACY_TYPES:
                subpart, sub_total, sub_error = fetch_partition(
                    client,
                    project_key,
                    page_size,
                    max_result_window,
                    {"severities": severity, "types": issue_type},
                )
                if sub_error:
                    return [], total, (
                        f"partition_failed:{severity}:{issue_type}:{sub_error}"
                    ), "severity_type"
                type_combined.extend(subpart)
                type_total += sub_total
            if type_total != part_total:
                return [], total, (
                    f"partition_type_total_mismatch:{severity}:{type_total}!={part_total}"
                ), "severity_type"
            part = type_combined
            part_error = ""
        if part_error:
            return [], total, f"partition_failed:{severity}:{part_error}", "severity"
        combined.extend(part)
        severity_total += part_total

    if severity_total != total:
        return [], total, (
            f"partition_severity_total_mismatch:{severity_total}!={total}"
        ), "severity"
    return combined, total, "", "severity"


def issue_impact_signature(issue: dict[str, Any]) -> str:
    """Return a stable compact signature for software-quality impacts."""
    impacts = issue.get("impacts") or []
    parts = [
        f"{item.get('softwareQuality', '')}:{item.get('severity', '')}"
        for item in impacts
        if isinstance(item, dict)
    ]
    return "|".join(sorted(parts))


def summarize_issue_rows(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Create snapshot-level counts from complete unresolved issue rows."""
    type_counts = Counter(str(issue.get("type") or "").upper() for issue in issues)
    severity_counts = Counter(
        str(issue.get("severity") or "").upper() for issue in issues
    )
    status_counts = Counter(str(issue.get("status") or "").upper() for issue in issues)
    scope_counts = Counter(str(issue.get("component_scope") or "") for issue in issues)
    clean_counts = Counter(
        str(issue.get("clean_code_attribute") or "").upper() for issue in issues
    )

    software_quality_issue_counts = Counter()
    impact_pair_occurrences = Counter()
    for issue in issues:
        qualities_for_issue: set[str] = set()
        for impact in issue.get("impacts") or []:
            if not isinstance(impact, dict):
                continue
            quality = str(impact.get("softwareQuality") or "").upper()
            severity = str(impact.get("severity") or "").upper()
            if quality:
                qualities_for_issue.add(quality)
            if quality or severity:
                impact_pair_occurrences[(quality, severity)] += 1
        for quality in qualities_for_issue:
            software_quality_issue_counts[quality] += 1

    known_type_total = sum(type_counts[item] for item in LEGACY_TYPES)
    known_severity_total = sum(severity_counts[item] for item in LEGACY_SEVERITIES)
    output: dict[str, Any] = {
        "issue_rows": len(issues),
        "issue_type_bug": type_counts["BUG"],
        "issue_type_vulnerability": type_counts["VULNERABILITY"],
        "issue_type_code_smell": type_counts["CODE_SMELL"],
        "issue_type_other": len(issues) - known_type_total,
        "issue_severity_blocker": severity_counts["BLOCKER"],
        "issue_severity_critical": severity_counts["CRITICAL"],
        "issue_severity_major": severity_counts["MAJOR"],
        "issue_severity_minor": severity_counts["MINOR"],
        "issue_severity_info": severity_counts["INFO"],
        "issue_severity_other": len(issues) - known_severity_total,
        "issue_status_open": status_counts["OPEN"],
        "issue_component_python_file": scope_counts["python_file"],
        "issue_component_project": scope_counts["project"],
        "issue_component_non_python": scope_counts["non_python"],
        "issue_component_unknown": scope_counts["unknown"],
        "issue_with_maintainability_impact": software_quality_issue_counts[
            "MAINTAINABILITY"
        ],
        "issue_with_reliability_impact": software_quality_issue_counts["RELIABILITY"],
        "issue_with_security_impact": software_quality_issue_counts["SECURITY"],
        "clean_code_attribute_distinct": sum(1 for k, v in clean_counts.items() if k and v),
        "rule_distinct": len({str(issue.get("rule") or "") for issue in issues if issue.get("rule")}),
        "issue_key_distinct": len({str(issue.get("issue_key") or "") for issue in issues if issue.get("issue_key")}),
        "duplicate_issue_keys_within_snapshot": (
            len(issues)
            - len({str(issue.get("issue_key") or "") for issue in issues if issue.get("issue_key")})
        ),
    }
    for quality in SOFTWARE_QUALITIES:
        for severity in ["HIGH", "MEDIUM", "LOW"]:
            key = f"impact_{quality.lower()}_{severity.lower()}_occurrences"
            output[key] = impact_pair_occurrences[(quality, severity)]
    return output


def build_rule_counts(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate complete issue rows into snapshot-by-rule cells."""
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    for issue in issues:
        key = (
            str(issue.get("rule") or ""),
            str(issue.get("type") or ""),
            str(issue.get("severity") or ""),
            str(issue.get("clean_code_attribute") or ""),
            issue_impact_signature(issue),
        )
        counts[key] += 1
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counts.items()):
        rule, issue_type, severity, clean_attr, impact_signature = key
        rows.append(
            {
                "rule": rule,
                "type": issue_type,
                "severity": severity,
                "clean_code_attribute": clean_attr,
                "impact_signature": impact_signature,
                "issue_count": count,
            }
        )
    return rows


def api_status(result: ApiResult) -> str:
    """Return a compact API status label."""
    if result.ok:
        return "success"
    if result.status_code == 404:
        return "not_found"
    return "error"


def collect_snapshot(
    row: pd.Series,
    client: SonarClient,
    page_size: int,
    max_result_window: int,
) -> dict[str, Any]:
    """Collect and validate one independent B01 Python-only snapshot project."""
    project_key = str(row["project_key"])
    manifest_analysis_id = str(row["analysis_id"])
    manifest_project_version = str(row["project_version"])

    component = client.get("/api/components/show", {"component": project_key})
    analyses = client.get(
        "/api/project_analyses/search",
        {"project": project_key, "category": "VERSION", "ps": 100},
    )
    measure = client.get(
        "/api/measures/component",
        {"component": project_key, "metricKeys": "ncloc"},
    )
    resolved = client.get(
        "/api/issues/search",
        {"componentKeys": project_key, "resolved": "true", "p": 1, "ps": 1},
    )

    analysis_rows = collect_analyses(analyses.data)
    analysis_ids = [analysis_key(item) for item in analysis_rows]
    analysis_versions = [analysis_version(item) for item in analysis_rows]
    manifest_analysis_found = bool(
        manifest_analysis_id and manifest_analysis_id in analysis_ids
    )
    expected_project_version_found = bool(
        manifest_project_version and manifest_project_version in analysis_versions
    )

    observed_ncloc = extract_measure_value(measure.data, "ncloc")
    manifest_ncloc = pd.to_numeric(row.get("ncloc_py_sonarqube"), errors="coerce")
    ncloc_matches = bool(
        observed_ncloc is not None
        and pd.notna(manifest_ncloc)
        and abs(observed_ncloc - float(manifest_ncloc)) < 1e-9
    )
    resolved_total = extract_paging_total(resolved.data) if resolved.ok else None

    issues, unresolved_total, issue_error, retrieval_strategy = (
        fetch_all_unresolved_issues(
            client, project_key, page_size, max_result_window
        )
    )
    issue_rows_complete = bool(
        unresolved_total >= 0
        and not issue_error
        and len(issues) == unresolved_total
    )
    counts = summarize_issue_rows(issues) if issue_rows_complete else summarize_issue_rows([])
    density = (
        (1000.0 * unresolved_total / observed_ncloc)
        if issue_rows_complete and observed_ncloc is not None and observed_ncloc > 0
        else math.nan
    )
    log_issue_total = (
        math.log1p(unresolved_total) if issue_rows_complete and unresolved_total >= 0 else math.nan
    )

    recoverable = bool(
        component.ok
        and analyses.ok
        and measure.ok
        and resolved.ok
        and expected_project_version_found
        and ncloc_matches
        and issue_rows_complete
        and counts["duplicate_issue_keys_within_snapshot"] == 0
        and counts["issue_component_non_python"] == 0
    )

    summary = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "manifest_order": int(row["manifest_order"]),
        "dataset_source": str(row["dataset_source"]),
        "repo_name": str(row["repo_name"]),
        "snapshot_key": str(row["snapshot_key"]),
        "commit_sha": str(row["commit_sha"]),
        "first_panel_month": str(row["first_panel_month"]),
        "last_panel_month": str(row["last_panel_month"]),
        "repo_month_rows": row.get("repo_month_rows", ""),
        "project_key": project_key,
        "manifest_project_version": manifest_project_version,
        "manifest_analysis_id": manifest_analysis_id,
        "scan_scope": str(row["scan_scope"]),
        "manifest_ncloc_py_sonarqube": (
            float(manifest_ncloc) if pd.notna(manifest_ncloc) else math.nan
        ),
        "component_api_status": api_status(component),
        "analyses_api_status": api_status(analyses),
        "measure_api_status": api_status(measure),
        "resolved_issues_api_status": api_status(resolved),
        "analysis_count": len(analysis_rows),
        "manifest_analysis_found": manifest_analysis_found,
        "expected_project_version_found": expected_project_version_found,
        "analysis_ids": " | ".join(analysis_ids),
        "analysis_project_versions": " | ".join(analysis_versions),
        "observed_ncloc_py_sonarqube": observed_ncloc,
        "ncloc_matches_manifest": ncloc_matches,
        "issue_total_py_sonarqube": unresolved_total if unresolved_total >= 0 else math.nan,
        "log_issue_total_py_sonarqube": log_issue_total,
        "issues_per_kloc_py_sonarqube": density,
        "resolved_issue_total": resolved_total,
        "issue_rows_complete": issue_rows_complete,
        "issue_retrieval_strategy": retrieval_strategy,
        "issue_retrieval_error": issue_error,
        "current_snapshot_recoverable": recoverable,
        **counts,
        "component_error": component.error,
        "analyses_error": analyses.error,
        "measure_error": measure.error,
        "resolved_issues_error": resolved.error,
    }

    issue_rows: list[dict[str, Any]] = []
    for issue in issues:
        issue_rows.append(
            {
                "manifest_order": int(row["manifest_order"]),
                "dataset_source": str(row["dataset_source"]),
                "repo_name": str(row["repo_name"]),
                "snapshot_key": str(row["snapshot_key"]),
                "commit_sha": str(row["commit_sha"]),
                "project_key": project_key,
                "manifest_analysis_id": manifest_analysis_id,
                "issue_key": issue["issue_key"],
                "rule": issue["rule"],
                "type": issue["type"],
                "severity": issue["severity"],
                "status": issue["status"],
                "resolution": issue["resolution"],
                "component": issue["component"],
                "component_path": issue["component_path"],
                "component_scope": issue["component_scope"],
                "message": issue["message"],
                "line": issue["line"],
                "creation_date": issue["creation_date"],
                "update_date": issue["update_date"],
                "clean_code_attribute": issue["clean_code_attribute"],
                "impacts_json": json.dumps(
                    issue["impacts"], ensure_ascii=False, sort_keys=True
                ),
            }
        )

    rule_rows: list[dict[str, Any]] = []
    for item in build_rule_counts(issues):
        rule_rows.append(
            {
                "manifest_order": int(row["manifest_order"]),
                "dataset_source": str(row["dataset_source"]),
                "repo_name": str(row["repo_name"]),
                "snapshot_key": str(row["snapshot_key"]),
                "commit_sha": str(row["commit_sha"]),
                "project_key": project_key,
                **item,
            }
        )

    return {
        "implementation_version": IMPLEMENTATION_VERSION,
        "snapshot_key": str(row["snapshot_key"]),
        "project_key": project_key,
        "status": "success" if recoverable else "failed_qc",
        "summary": summary,
        "issues": issue_rows,
        "rule_counts": rule_rows,
    }


def cached_success_matches(
    payload: dict[str, Any] | None, row: pd.Series
) -> bool:
    """Return True only for a reusable success checkpoint for this exact snapshot."""
    if not payload:
        return False
    return bool(
        payload.get("implementation_version") == IMPLEMENTATION_VERSION
        and payload.get("status") == "success"
        and payload.get("snapshot_key") == str(row["snapshot_key"])
        and payload.get("project_key") == str(row["project_key"])
    )


def augment_rule_definition(
    definitions: dict[str, dict[str, Any]], issue: dict[str, Any]
) -> None:
    """Update one cross-snapshot rule definition record."""
    rule = str(issue.get("rule") or "")
    if not rule:
        return
    entry = definitions.setdefault(
        rule,
        {
            "rule": rule,
            "types": set(),
            "severities": set(),
            "clean_code_attributes": set(),
            "impact_signatures": set(),
            "example_message": str(issue.get("message") or ""),
            "snapshot_occurrences": 0,
        },
    )
    if issue.get("type"):
        entry["types"].add(str(issue["type"]))
    if issue.get("severity"):
        entry["severities"].add(str(issue["severity"]))
    if issue.get("clean_code_attribute"):
        entry["clean_code_attributes"].add(str(issue["clean_code_attribute"]))
    impacts_json = str(issue.get("impacts_json") or "")
    if impacts_json:
        try:
            impacts = json.loads(impacts_json)
        except json.JSONDecodeError:
            impacts = []
        signature_parts = []
        for impact in impacts if isinstance(impacts, list) else []:
            if isinstance(impact, dict):
                signature_parts.append(
                    f"{impact.get('softwareQuality', '')}:{impact.get('severity', '')}"
                )
        if signature_parts:
            entry["impact_signatures"].add("|".join(sorted(signature_parts)))


def consolidate(
    selected: pd.DataFrame,
    checkpoint_dir: Path,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, int, int]:
    """Consolidate successful checkpoints into final compact and raw outputs."""
    summaries: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    rule_definitions: dict[str, dict[str, Any]] = {}
    issue_row_total = 0
    rule_count_row_total = 0

    ensure_parent(args.issues_output)
    ensure_parent(args.rule_counts_output)
    with gzip.open(args.issues_output, "wt", encoding="utf-8", newline="") as issue_handle, gzip.open(
        args.rule_counts_output, "wt", encoding="utf-8", newline=""
    ) as rule_handle:
        issue_writer = csv.DictWriter(issue_handle, fieldnames=ISSUE_COLUMNS)
        rule_writer = csv.DictWriter(rule_handle, fieldnames=RULE_COUNT_COLUMNS)
        issue_writer.writeheader()
        rule_writer.writeheader()

        for _, row in selected.iterrows():
            path = checkpoint_path(checkpoint_dir, str(row["snapshot_key"]))
            payload = read_checkpoint(path)
            if not payload or payload.get("status") != "success":
                unresolved_rows.append(
                    {
                        "manifest_order": int(row["manifest_order"]),
                        "dataset_source": row["dataset_source"],
                        "repo_name": row["repo_name"],
                        "snapshot_key": row["snapshot_key"],
                        "commit_sha": row["commit_sha"],
                        "project_key": row["project_key"],
                        "status": "missing_success_checkpoint",
                        "error": (
                            str((payload or {}).get("summary", {}).get("issue_retrieval_error", ""))
                            or str((payload or {}).get("status", ""))
                        ),
                    }
                )
                continue
            summary = payload.get("summary")
            if not isinstance(summary, dict):
                unresolved_rows.append(
                    {
                        "manifest_order": int(row["manifest_order"]),
                        "dataset_source": row["dataset_source"],
                        "repo_name": row["repo_name"],
                        "snapshot_key": row["snapshot_key"],
                        "commit_sha": row["commit_sha"],
                        "project_key": row["project_key"],
                        "status": "invalid_checkpoint_summary",
                        "error": "",
                    }
                )
                continue
            summaries.append(summary)

            issues = payload.get("issues") or []
            for issue in issues:
                if isinstance(issue, dict):
                    issue_writer.writerow({column: issue.get(column, "") for column in ISSUE_COLUMNS})
                    augment_rule_definition(rule_definitions, issue)
                    issue_row_total += 1

            rule_rows = payload.get("rule_counts") or []
            for rule_row in rule_rows:
                if isinstance(rule_row, dict):
                    rule_writer.writerow(
                        {column: rule_row.get(column, "") for column in RULE_COUNT_COLUMNS}
                    )
                    rule_count_row_total += 1

    snapshot_counts = pd.DataFrame(summaries)
    if not snapshot_counts.empty:
        snapshot_counts = snapshot_counts.sort_values("manifest_order", kind="stable")
        preferred_columns = [
            "implementation_version",
            "manifest_order",
            "dataset_source",
            "repo_name",
            "snapshot_key",
            "commit_sha",
            "first_panel_month",
            "last_panel_month",
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
            "issue_retrieval_strategy",
            "current_snapshot_recoverable",
        ]
        remaining_columns = [
            column for column in snapshot_counts.columns if column not in preferred_columns
        ]
        snapshot_counts = snapshot_counts[preferred_columns + remaining_columns]
    unresolved = pd.DataFrame(
        unresolved_rows,
        columns=[
            "manifest_order",
            "dataset_source",
            "repo_name",
            "snapshot_key",
            "commit_sha",
            "project_key",
            "status",
            "error",
        ],
    )

    definition_rows: list[dict[str, Any]] = []
    for rule, entry in sorted(rule_definitions.items()):
        definition_rows.append(
            {
                "rule": rule,
                "types": " | ".join(sorted(entry["types"])),
                "severities": " | ".join(sorted(entry["severities"])),
                "clean_code_attributes": " | ".join(
                    sorted(entry["clean_code_attributes"])
                ),
                "impact_signatures": " | ".join(sorted(entry["impact_signatures"])),
                "example_message": entry["example_message"],
            }
        )
    definitions = pd.DataFrame(
        definition_rows,
        columns=[
            "rule",
            "types",
            "severities",
            "clean_code_attributes",
            "impact_signatures",
            "example_message",
        ],
    )
    return snapshot_counts, unresolved, definitions, issue_row_total, rule_count_row_total


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
    full_manifest: pd.DataFrame,
    selected: pd.DataFrame,
    snapshot_counts: pd.DataFrame,
    unresolved: pd.DataFrame,
    issue_row_total: int,
    args: argparse.Namespace,
) -> pd.DataFrame:
    """Build full-collection integrity and measurement QC checks."""
    rows: list[dict[str, Any]] = []
    is_full_selection = (
        len(selected) == len(full_manifest)
        and selected["snapshot_key"].tolist() == full_manifest["snapshot_key"].tolist()
    )

    rows.append(
        qc_row(
            "selected_snapshots_collected",
            len(snapshot_counts),
            len(selected),
            "pass" if len(snapshot_counts) == len(selected) else "fail",
        )
    )
    rows.append(
        qc_row(
            "unresolved_snapshots",
            len(unresolved),
            0,
            "pass" if unresolved.empty else "fail",
        )
    )
    if snapshot_counts.empty:
        rows.append(qc_row("snapshot_counts_nonempty", 0, "> 0", "fail"))
        return pd.DataFrame(rows)

    def bool_check(column: str, check: str, severity: str = "fail") -> None:
        values = snapshot_counts[column].fillna(False).astype(bool)
        passed = int(values.sum())
        rows.append(
            qc_row(
                check,
                passed,
                len(snapshot_counts),
                "pass" if bool(values.all()) else severity,
            )
        )

    bool_check("current_snapshot_recoverable", "snapshots_recoverable")
    bool_check("expected_project_version_found", "expected_project_versions_found")
    bool_check("manifest_analysis_found", "manifest_analysis_ids_found", "warn")
    bool_check("ncloc_matches_manifest", "ncloc_matches_b01_manifest")
    bool_check("issue_rows_complete", "issue_rows_complete")

    rows.append(
        qc_row(
            "scan_scope_python_only",
            int(snapshot_counts["scan_scope"].eq(EXPECTED_SCAN_SCOPE).sum()),
            len(snapshot_counts),
            "pass"
            if bool(snapshot_counts["scan_scope"].eq(EXPECTED_SCAN_SCOPE).all())
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "duplicate_snapshot_keys",
            int(snapshot_counts["snapshot_key"].duplicated().sum()),
            0,
            "pass" if not snapshot_counts["snapshot_key"].duplicated().any() else "fail",
        )
    )
    rows.append(
        qc_row(
            "duplicate_project_keys",
            int(snapshot_counts["project_key"].duplicated().sum()),
            0,
            "pass" if not snapshot_counts["project_key"].duplicated().any() else "fail",
        )
    )
    rows.append(
        qc_row(
            "duplicate_issue_keys_within_snapshot",
            int(
                pd.to_numeric(
                    snapshot_counts["duplicate_issue_keys_within_snapshot"],
                    errors="coerce",
                ).fillna(0).sum()
            ),
            0,
            "pass"
            if pd.to_numeric(
                snapshot_counts["duplicate_issue_keys_within_snapshot"], errors="coerce"
            ).fillna(0).sum()
            == 0
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "non_python_issue_components",
            int(
                pd.to_numeric(
                    snapshot_counts["issue_component_non_python"], errors="coerce"
                ).fillna(0).sum()
            ),
            0,
            "pass"
            if pd.to_numeric(
                snapshot_counts["issue_component_non_python"], errors="coerce"
            ).fillna(0).sum()
            == 0
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "unknown_issue_components",
            int(
                pd.to_numeric(
                    snapshot_counts["issue_component_unknown"], errors="coerce"
                ).fillna(0).sum()
            ),
            0,
            "pass"
            if pd.to_numeric(
                snapshot_counts["issue_component_unknown"], errors="coerce"
            ).fillna(0).sum()
            == 0
            else "warn",
            "Project-level issues are tracked separately and are not counted as unknown.",
        )
    )
    rows.append(
        qc_row(
            "snapshots_with_resolved_issues",
            int(
                (pd.to_numeric(snapshot_counts["resolved_issue_total"], errors="coerce").fillna(0) > 0).sum()
            ),
            0,
            "pass"
            if not bool(
                (pd.to_numeric(snapshot_counts["resolved_issue_total"], errors="coerce").fillna(0) > 0).any()
            )
            else "warn",
            "B05 primary counts explicitly use unresolved issue stock.",
        )
    )
    rows.append(
        qc_row(
            "snapshots_with_multiple_analyses",
            int(
                (pd.to_numeric(snapshot_counts["analysis_count"], errors="coerce").fillna(0) != 1).sum()
            ),
            0,
            "pass"
            if not bool(
                (pd.to_numeric(snapshot_counts["analysis_count"], errors="coerce").fillna(0) != 1).any()
            )
            else "warn",
            "Multiple analyses are reviewable when version and NCLOC still match the B01 snapshot.",
        )
    )
    rows.append(
        qc_row(
            "raw_issue_rows_match_snapshot_totals",
            issue_row_total,
            int(
                pd.to_numeric(
                    snapshot_counts["issue_total_py_sonarqube"], errors="coerce"
                ).fillna(0).sum()
            ),
            "pass"
            if issue_row_total
            == int(
                pd.to_numeric(
                    snapshot_counts["issue_total_py_sonarqube"], errors="coerce"
                ).fillna(0).sum()
            )
            else "fail",
        )
    )
    rows.append(
        qc_row(
            "positive_ncloc_with_issues_density_defined",
            int(
                snapshot_counts.loc[
                    pd.to_numeric(snapshot_counts["observed_ncloc_py_sonarqube"], errors="coerce") > 0,
                    "issues_per_kloc_py_sonarqube",
                ].notna().sum()
            ),
            int(
                (pd.to_numeric(snapshot_counts["observed_ncloc_py_sonarqube"], errors="coerce") > 0).sum()
            ),
            "pass"
            if snapshot_counts.loc[
                pd.to_numeric(snapshot_counts["observed_ncloc_py_sonarqube"], errors="coerce") > 0,
                "issues_per_kloc_py_sonarqube",
            ].notna().all()
            else "fail",
        )
    )

    if args.strict_expected_counts and is_full_selection:
        count_checks = [
            ("full_expected_snapshots", len(snapshot_counts), args.expected_snapshots),
            (
                "full_expected_repositories",
                snapshot_counts["repo_name"].nunique(),
                args.expected_repositories,
            ),
            (
                "full_expected_treatment_snapshots",
                int(snapshot_counts["dataset_source"].eq("treatment").sum()),
                args.expected_treatment,
            ),
            (
                "full_expected_control_snapshots",
                int(snapshot_counts["dataset_source"].eq("control").sum()),
                args.expected_control,
            ),
        ]
        for check, value, expected in count_checks:
            rows.append(
                qc_row(
                    check,
                    value,
                    expected,
                    "pass" if value == expected else "fail",
                )
            )
    elif args.strict_expected_counts:
        rows.append(
            qc_row(
                "full_expected_counts_skipped_for_filtered_run",
                len(selected),
                len(full_manifest),
                "warn",
                "Expected 1,496-snapshot checks apply only to an unfiltered full run.",
            )
        )
    return pd.DataFrame(rows)


def build_summary(
    full_manifest: pd.DataFrame,
    selected: pd.DataFrame,
    snapshot_counts: pd.DataFrame,
    unresolved: pd.DataFrame,
    definitions: pd.DataFrame,
    issue_row_total: int,
    rule_count_row_total: int,
    qc: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact key-value summary for B05."""
    metrics: list[tuple[str, Any]] = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("available_b01_snapshots", len(full_manifest)),
        ("selected_snapshots", len(selected)),
        ("collected_snapshots", len(snapshot_counts)),
        ("collected_repositories", snapshot_counts["repo_name"].nunique() if not snapshot_counts.empty else 0),
        ("control_snapshots", int(snapshot_counts["dataset_source"].eq("control").sum()) if not snapshot_counts.empty else 0),
        ("treatment_snapshots", int(snapshot_counts["dataset_source"].eq("treatment").sum()) if not snapshot_counts.empty else 0),
        ("unresolved_snapshots", len(unresolved)),
        ("raw_issue_rows", issue_row_total),
        ("snapshot_rule_count_rows", rule_count_row_total),
        ("unique_rules", len(definitions)),
        ("qc_failures", int(qc["status"].eq("fail").sum())),
        ("qc_warnings", int(qc["status"].eq("warn").sum())),
    ]
    if not snapshot_counts.empty:
        issue_total = pd.to_numeric(
            snapshot_counts["issue_total_py_sonarqube"], errors="coerce"
        )
        density = pd.to_numeric(
            snapshot_counts["issues_per_kloc_py_sonarqube"], errors="coerce"
        )
        metrics.extend(
            [
                ("sum_snapshot_issue_stocks", int(issue_total.fillna(0).sum())),
                ("issue_count_min", issue_total.min()),
                ("issue_count_median", issue_total.median()),
                ("issue_count_mean", issue_total.mean()),
                ("issue_count_max", issue_total.max()),
                ("zero_issue_snapshots", int(issue_total.fillna(0).eq(0).sum())),
                ("density_median_issues_per_kloc", density.median()),
                ("density_mean_issues_per_kloc", density.mean()),
                (
                    "code_smell_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_type_code_smell"], errors="coerce").fillna(0).sum()),
                ),
                (
                    "bug_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_type_bug"], errors="coerce").fillna(0).sum()),
                ),
                (
                    "vulnerability_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_type_vulnerability"], errors="coerce").fillna(0).sum()),
                ),
                (
                    "maintainability_impact_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_with_maintainability_impact"], errors="coerce").fillna(0).sum()),
                ),
                (
                    "reliability_impact_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_with_reliability_impact"], errors="coerce").fillna(0).sum()),
                ),
                (
                    "security_impact_issue_stock_sum",
                    int(pd.to_numeric(snapshot_counts["issue_with_security_impact"], errors="coerce").fillna(0).sum()),
                ),
            ]
        )
    return pd.DataFrame(metrics, columns=["metric", "value"])


def run_self_test() -> None:
    """Run deterministic offline tests for manifest and issue aggregation logic."""
    rows = []
    for order, source in [(1, "control"), (2, "treatment")]:
        sha = ("a" if source == "control" else "b") * 40
        rows.append(
            {
                "manifest_order": order,
                "dataset_source": source,
                "repo_name": f"org/{source}",
                "commit_sha": sha,
                "snapshot_key": f"{source}-snapshot",
                "project_key": f"project-{source}",
                "project_version": sha,
                "scan_scope": EXPECTED_SCAN_SCOPE,
                "status": "success",
                "ncloc_py_sonarqube": 100,
                "analysis_id": f"analysis-{source}",
                "first_panel_month": "2025-01",
                "last_panel_month": "2025-01",
            }
        )
    manifest = normalize_manifest(pd.DataFrame(rows))
    assert len(manifest) == 2

    response = {
        "issues": [
            {
                "key": "I1",
                "rule": "python:S1",
                "type": "CODE_SMELL",
                "severity": "MAJOR",
                "status": "OPEN",
                "component": "project-control:src/a.py",
                "message": "Example",
                "cleanCodeAttribute": "COMPLETE",
                "impacts": [
                    {"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}
                ],
            },
            {
                "key": "I2",
                "rule": "python:S2",
                "type": "BUG",
                "severity": "CRITICAL",
                "status": "OPEN",
                "component": "project-control:src/b.py",
                "message": "Bug",
                "impacts": [
                    {"softwareQuality": "RELIABILITY", "severity": "HIGH"}
                ],
            },
        ],
        "components": [
            {"key": "project-control:src/a.py", "path": "src/a.py"},
            {"key": "project-control:src/b.py", "path": "src/b.py"},
        ],
        "paging": {"total": 2},
    }
    normalized = [
        normalize_issue(issue, response, "project-control")
        for issue in response["issues"]
    ]
    summary = summarize_issue_rows(normalized)
    assert summary["issue_rows"] == 2
    assert summary["issue_type_code_smell"] == 1
    assert summary["issue_type_bug"] == 1
    assert summary["issue_with_maintainability_impact"] == 1
    assert summary["issue_with_reliability_impact"] == 1
    assert summary["issue_component_non_python"] == 0
    assert len(build_rule_counts(normalized)) == 2

    with tempfile.TemporaryDirectory() as temp_dir:
        path = checkpoint_path(Path(temp_dir), "control-snapshot")
        payload = {
            "implementation_version": IMPLEMENTATION_VERSION,
            "snapshot_key": "control-snapshot",
            "project_key": "project-control",
            "status": "success",
            "summary": {"x": 1},
            "issues": [],
            "rule_counts": [],
        }
        write_checkpoint(path, payload)
        loaded = read_checkpoint(path)
        assert loaded == payload
    print("self-test passed")


def main() -> int:
    """Run B05 full Python-only SonarQube issue collection."""
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
            raise CollectionError("SONAR_TOKEN must be set in the environment")

        logging.info("Reading B01 completed manifest: %s", args.completed_manifest_file)
        full_manifest = normalize_manifest(pd.read_csv(args.completed_manifest_file))
        selected = select_manifest(full_manifest, args)
        checkpoint_dir = Path(args.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logging.info(
            "Selected %d/%d snapshots across %d repositories",
            len(selected),
            len(full_manifest),
            selected["repo_name"].nunique(),
        )
        client = SonarClient(
            host=args.sonar_host,
            token=token,
            timeout_seconds=args.server_timeout_seconds,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )

        reused = 0
        attempted = 0
        api_success = 0
        api_failed = 0
        started = time.monotonic()
        for position, (_, row) in enumerate(selected.iterrows(), start=1):
            path = checkpoint_path(checkpoint_dir, str(row["snapshot_key"]))
            cached = None if args.force else read_checkpoint(path)
            if cached_success_matches(cached, row):
                reused += 1
            else:
                attempted += 1
                try:
                    payload = collect_snapshot(
                        row,
                        client,
                        page_size=args.page_size,
                        max_result_window=args.max_result_window,
                    )
                except Exception as exc:  # Keep the full run resumable.
                    logging.exception(
                        "Snapshot collection crashed for %s", row["snapshot_key"]
                    )
                    payload = {
                        "implementation_version": IMPLEMENTATION_VERSION,
                        "snapshot_key": str(row["snapshot_key"]),
                        "project_key": str(row["project_key"]),
                        "status": "exception",
                        "summary": {
                            "manifest_order": int(row["manifest_order"]),
                            "dataset_source": str(row["dataset_source"]),
                            "repo_name": str(row["repo_name"]),
                            "snapshot_key": str(row["snapshot_key"]),
                            "commit_sha": str(row["commit_sha"]),
                            "project_key": str(row["project_key"]),
                            "issue_retrieval_error": f"exception:{exc}",
                        },
                        "issues": [],
                        "rule_counts": [],
                    }
                write_checkpoint(path, payload)
                if payload.get("status") == "success":
                    api_success += 1
                else:
                    api_failed += 1
                    logging.warning(
                        "Snapshot failed QC: %s (%s)",
                        row["snapshot_key"],
                        payload.get("status"),
                    )

            if position % args.progress_every == 0 or position == len(selected):
                elapsed = max(time.monotonic() - started, 1e-9)
                logging.info(
                    "Progress %d/%d; reused=%d; attempted=%d; new_success=%d; "
                    "new_failed=%d; %.2f snapshots/sec",
                    position,
                    len(selected),
                    reused,
                    attempted,
                    api_success,
                    api_failed,
                    position / elapsed,
                )

        logging.info("Consolidating checkpoints into final outputs")
        snapshot_counts, unresolved, definitions, issue_row_total, rule_count_row_total = consolidate(
            selected, checkpoint_dir, args
        )
        qc = build_qc(
            full_manifest,
            selected,
            snapshot_counts,
            unresolved,
            issue_row_total,
            args,
        )
        summary = build_summary(
            full_manifest,
            selected,
            snapshot_counts,
            unresolved,
            definitions,
            issue_row_total,
            rule_count_row_total,
            qc,
        )

        write_csv(snapshot_counts, args.snapshot_counts_output)
        write_csv(definitions, args.rule_definitions_output)
        write_csv(unresolved, args.unresolved_output)
        write_csv(qc, args.qc_output)
        write_csv(summary, args.summary_output)

        failures = qc[qc["status"].eq("fail")]
        warnings = qc[qc["status"].eq("warn")]
        logging.info(
            "Completed B05 collection: snapshots=%d; repos=%d; raw issues=%d; "
            "rules=%d; unresolved=%d; QC failures=%d; warnings=%d",
            len(snapshot_counts),
            snapshot_counts["repo_name"].nunique() if not snapshot_counts.empty else 0,
            issue_row_total,
            len(definitions),
            len(unresolved),
            len(failures),
            len(warnings),
        )

        if not args.keep_checkpoints and failures.empty and unresolved.empty:
            removed = 0
            for _, row in selected.iterrows():
                path = checkpoint_path(checkpoint_dir, str(row["snapshot_key"]))
                if path.exists():
                    path.unlink()
                    removed += 1
            logging.info("Removed %d successful temporary checkpoints", removed)

        if args.strict and not failures.empty:
            logging.error("Strict QC failures:\n%s", failures.to_string(index=False))
            return 3
        return 0
    except (CollectionError, FileNotFoundError, pd.errors.ParserError) as exc:
        logging.error("B05 collection failed: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
