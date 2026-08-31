#!/usr/bin/env python3
"""
Collect file-level SonarQube cognitive complexity and NCLOC from existing
historical SonarQube projects created by run-x-b01-sonarqube.

This experiment performs API retrieval only. It never invokes SonarScanner and
never changes an existing SonarQube project. Each historical project represents
one repository-commit snapshot in the frozen Model C sample.

Primary output:
  One row per SonarQube file component per historical snapshot with the actual
  file-level cognitive_complexity and ncloc measures.

Supporting outputs:
  - one row per snapshot with project totals and file-sum reconciliation;
  - unresolved/error rows;
  - QC checks;
  - compact summary metadata.

Implementation version: v1
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
from pathlib import Path
from typing import Any, Iterable, Optional

import requests
from dotenv import load_dotenv

IMPLEMENTATION_VERSION = "v1"
DEFAULT_METRICS = ("cognitive_complexity", "ncloc")
DEFAULT_PAGE_SIZE = 500
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve file-level SonarQube cognitive complexity and NCLOC from "
            "the existing run-x-b01 historical snapshot projects."
        )
    )
    parser.add_argument(
        "--input-manifest-file",
        required=True,
        help="B01 SonarQube completed manifest containing snapshot_key/project_key.",
    )
    parser.add_argument("--file-output", required=True)
    parser.add_argument("--snapshot-output", required=True)
    parser.add_argument("--unresolved-output", required=True)
    parser.add_argument("--qc-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument(
        "--sonar-host",
        default=os.getenv("SONAR_HOST", "http://localhost:9000"),
    )
    parser.add_argument("--sonar-token", default=os.getenv("SONAR_TOKEN", ""))
    parser.add_argument(
        "--metrics",
        default=",".join(DEFAULT_METRICS),
        help="Comma-separated SonarQube metric keys.",
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--request-timeout-seconds", type=int, default=60)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--sleep-between-projects-seconds", type=float, default=0.0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum selected snapshots; 0 means all remaining snapshots.",
    )
    parser.add_argument("--dataset-source", choices=("treatment", "control"))
    parser.add_argument("--repo-name")
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-treatment-snapshots", type=int, default=790)
    parser.add_argument("--expected-control-snapshots", type=int, default=706)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument(
        "--strict-expected-counts",
        action="store_true",
        help="Fail if the unfiltered production manifest does not match expected counts.",
    )
    parser.add_argument(
        "--strict-metric-reconciliation",
        action="store_true",
        help="Fail if project totals do not equal sums of file measures.",
    )
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def metric_map(measures: Iterable[dict[str, Any]]) -> dict[str, Optional[float]]:
    result: dict[str, Optional[float]] = {}
    for measure in measures or []:
        metric = measure.get("metric")
        if metric:
            result[str(metric)] = safe_float(measure.get("value"))
    return result


def component_path(component: dict[str, Any], project_key: str) -> str:
    path = str(component.get("path") or "").strip()
    if path:
        return path
    key = str(component.get("key") or "")
    prefix = f"{project_key}:"
    if key.startswith(prefix):
        return key[len(prefix) :]
    return key


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Input manifest is empty: {path}")
    return rows


def choose_column(fieldnames: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    available = set(fieldnames)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def normalize_manifest(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    fieldnames = rows[0].keys()
    required = {
        "snapshot_key": choose_column(fieldnames, ("snapshot_key", "snapshot_id")),
        "project_key": choose_column(fieldnames, ("project_key",)),
        "dataset_source": choose_column(fieldnames, ("dataset_source",)),
        "repo_name": choose_column(fieldnames, ("repo_name",)),
        "commit_sha": choose_column(
            fieldnames,
            ("commit_sha", "latest_commit_effective", "project_version"),
        ),
    }
    missing = [name for name, column in required.items() if column is None]
    if missing:
        raise ValueError(f"Missing required manifest columns: {', '.join(missing)}")

    repo_month_col = choose_column(fieldnames, ("repo_month_rows",))
    manifest_order_col = choose_column(fieldnames, ("manifest_order", "order"))
    status_col = choose_column(fieldnames, ("status", "scan_status"))
    analysis_id_col = choose_column(fieldnames, ("analysis_id", "manifest_analysis_id"))

    normalized: list[dict[str, Any]] = []
    seen_snapshot: set[str] = set()
    seen_project: set[str] = set()
    for position, row in enumerate(rows, start=1):
        snapshot_key = str(row[required["snapshot_key"]] or "").strip()
        project_key = str(row[required["project_key"]] or "").strip()
        if not snapshot_key or not project_key:
            continue
        if snapshot_key in seen_snapshot:
            raise ValueError(f"Duplicate snapshot_key in input: {snapshot_key}")
        if project_key in seen_project:
            raise ValueError(f"Duplicate project_key in input: {project_key}")
        seen_snapshot.add(snapshot_key)
        seen_project.add(project_key)

        manifest_order = position
        if manifest_order_col:
            raw_order = str(row.get(manifest_order_col, "") or "").strip()
            if raw_order.isdigit():
                manifest_order = int(raw_order)

        repo_month_rows = None
        if repo_month_col:
            repo_month_rows = safe_float(row.get(repo_month_col))

        normalized.append(
            {
                "manifest_order": manifest_order,
                "dataset_source": str(row[required["dataset_source"]] or "").strip(),
                "repo_name": str(row[required["repo_name"]] or "").strip(),
                "snapshot_key": snapshot_key,
                "commit_sha": str(row[required["commit_sha"]] or "").strip(),
                "project_key": project_key,
                "repo_month_rows": repo_month_rows,
                "manifest_status": str(row.get(status_col, "") or "").strip()
                if status_col
                else "",
                "manifest_analysis_id": str(row.get(analysis_id_col, "") or "").strip()
                if analysis_id_col
                else "",
            }
        )

    if not normalized:
        raise ValueError("No usable snapshot/project rows found in manifest.")
    normalized.sort(key=lambda row: (row["manifest_order"], row["snapshot_key"]))
    return normalized


def request_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: int,
    max_retries: int,
    backoff: float,
) -> dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                wait = backoff * (2**attempt)
                logging.warning(
                    "Retryable SonarQube HTTP %s for %s; retrying in %.1fs",
                    response.status_code,
                    response.url,
                    wait,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object from {response.url}")
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            wait = backoff * (2**attempt)
            logging.warning("SonarQube request failed: %s; retrying in %.1fs", exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"SonarQube request failed after retries: {last_error}")


def check_server(session: requests.Session, host: str, args: argparse.Namespace) -> dict[str, Any]:
    status = request_json(
        session,
        f"{host}/api/system/status",
        {},
        args.request_timeout_seconds,
        args.max_retries,
        args.retry_backoff_seconds,
    )
    if status.get("status") != "UP":
        raise RuntimeError(f"SonarQube status is not UP: {status}")
    return status


def fetch_project_measures(
    session: requests.Session,
    host: str,
    project_key: str,
    metrics: tuple[str, ...],
    args: argparse.Namespace,
) -> dict[str, Optional[float]]:
    data = request_json(
        session,
        f"{host}/api/measures/component",
        {"component": project_key, "metricKeys": ",".join(metrics)},
        args.request_timeout_seconds,
        args.max_retries,
        args.retry_backoff_seconds,
    )
    component = data.get("component") or {}
    return metric_map(component.get("measures") or [])


def fetch_file_components(
    session: requests.Session,
    host: str,
    project_key: str,
    metrics: tuple[str, ...],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    page = 1
    expected_total: Optional[int] = None
    while True:
        data = request_json(
            session,
            f"{host}/api/measures/component_tree",
            {
                "component": project_key,
                "metricKeys": ",".join(metrics),
                "qualifiers": "FIL",
                "ps": args.page_size,
                "p": page,
            },
            args.request_timeout_seconds,
            args.max_retries,
            args.retry_backoff_seconds,
        )
        page_components = data.get("components") or []
        if not isinstance(page_components, list):
            raise ValueError(f"Invalid component_tree payload for {project_key}")
        components.extend(page_components)

        paging = data.get("paging") or {}
        total = paging.get("total")
        if isinstance(total, int):
            expected_total = total
        if not page_components:
            break
        if expected_total is not None and len(components) >= expected_total:
            break
        if len(page_components) < args.page_size:
            break
        page += 1

    if expected_total is not None and len(components) != expected_total:
        raise ValueError(
            f"component_tree pagination mismatch for {project_key}: "
            f"collected={len(components)} expected={expected_total}"
        )
    return components


def close_enough(left: Optional[float], right: Optional[float], tolerance: float = 1e-9) -> bool:
    if left is None or right is None:
        return False
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".gz" if path.suffix == ".gz" else ""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=f".tmp{suffix}", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        if path.suffix == ".gz":
            handle: Any = gzip.open(tmp_path, "wt", encoding="utf-8", newline="")
        else:
            handle = tmp_path.open("w", encoding="utf-8", newline="")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_qc(
    rows: list[dict[str, Any]],
    check_name: str,
    observed: Any,
    expected: Any,
    passed: bool,
    severity: str = "hard",
    note: str = "",
) -> None:
    rows.append(
        {
            "check_name": check_name,
            "status": "pass" if passed else ("fail" if severity == "hard" else "warn"),
            "observed": observed,
            "expected": expected,
            "severity": severity,
            "note": note,
        }
    )


def run_self_test() -> int:
    project = {"cognitive_complexity": 9.0, "ncloc": 30.0}
    components = [
        {
            "key": "p:a.py",
            "path": "a.py",
            "qualifier": "FIL",
            "language": "py",
            "measures": [
                {"metric": "cognitive_complexity", "value": "9"},
                {"metric": "ncloc", "value": "20"},
            ],
        },
        {
            "key": "p:b.py",
            "path": "b.py",
            "qualifier": "FIL",
            "language": "py",
            "measures": [{"metric": "ncloc", "value": "10"}],
        },
    ]
    file_rows = []
    for component in components:
        measures = metric_map(component.get("measures") or [])
        file_rows.append(
            {
                "path": component_path(component, "p"),
                "cognitive_complexity": measures.get("cognitive_complexity") or 0.0,
                "ncloc": measures.get("ncloc") or 0.0,
            }
        )
    complexity_sum = sum(row["cognitive_complexity"] for row in file_rows)
    ncloc_sum = sum(row["ncloc"] for row in file_rows)
    assert complexity_sum == project["cognitive_complexity"]
    assert ncloc_sum == project["ncloc"]
    assert file_rows[1]["cognitive_complexity"] == 0.0
    assert file_rows[0]["path"] == "a.py"
    print("SELF_TEST PASS")
    return 0


def main() -> int:
    load_dotenv(dotenv_path=".env", override=False)
    args = parse_args()
    configure_logging(args.log_level)

    if args.self_test:
        return run_self_test()

    if args.start_order < 1:
        raise SystemExit("--start-order must be at least 1")
    if args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    if not 1 <= args.page_size <= 500:
        raise SystemExit("--page-size must be between 1 and 500")
    if args.progress_every < 1:
        raise SystemExit("--progress-every must be at least 1")

    input_path = Path(args.input_manifest_file)
    file_output = Path(args.file_output)
    snapshot_output = Path(args.snapshot_output)
    unresolved_output = Path(args.unresolved_output)
    qc_output = Path(args.qc_output)
    summary_output = Path(args.summary_output)

    manifest = normalize_manifest(read_csv_rows(input_path))
    production_manifest = list(manifest)

    treatment_count = sum(row["dataset_source"] == "treatment" for row in production_manifest)
    control_count = sum(row["dataset_source"] == "control" for row in production_manifest)
    repository_count = len({row["repo_name"].lower() for row in production_manifest})

    filtered = [row for row in manifest if row["manifest_order"] >= args.start_order]
    if args.dataset_source:
        filtered = [row for row in filtered if row["dataset_source"] == args.dataset_source]
    if args.repo_name:
        target = args.repo_name.lower()
        filtered = [row for row in filtered if row["repo_name"].lower() == target]
    if args.limit:
        filtered = filtered[: args.limit]

    metrics = tuple(metric.strip() for metric in args.metrics.split(",") if metric.strip())
    if "cognitive_complexity" not in metrics or "ncloc" not in metrics:
        raise SystemExit("J01 v1 requires cognitive_complexity and ncloc metrics")

    logging.info("Implementation version: %s", IMPLEMENTATION_VERSION)
    logging.info("Input manifest: %s", input_path)
    logging.info("Input SHA256: %s", sha256_file(input_path))
    logging.info("Production manifest snapshots: %d", len(production_manifest))
    logging.info("Selected snapshots: %d", len(filtered))
    logging.info("Metrics: %s", ",".join(metrics))

    qc_rows: list[dict[str, Any]] = []
    unfiltered_run = (
        args.start_order == 1
        and args.limit == 0
        and args.dataset_source is None
        and args.repo_name is None
    )
    if unfiltered_run:
        add_qc(
            qc_rows,
            "input_snapshot_rows",
            len(production_manifest),
            args.expected_snapshots,
            len(production_manifest) == args.expected_snapshots,
        )
        add_qc(
            qc_rows,
            "treatment_snapshots",
            treatment_count,
            args.expected_treatment_snapshots,
            treatment_count == args.expected_treatment_snapshots,
        )
        add_qc(
            qc_rows,
            "control_snapshots",
            control_count,
            args.expected_control_snapshots,
            control_count == args.expected_control_snapshots,
        )
        add_qc(
            qc_rows,
            "unique_repositories",
            repository_count,
            args.expected_repositories,
            repository_count == args.expected_repositories,
        )

    if args.dry_run:
        summary_rows = [
            {
                "section": "run",
                "metric": "status",
                "value": "DRY_RUN",
                "note": "No SonarQube API retrieval performed.",
            },
            {
                "section": "input",
                "metric": "selected_snapshots",
                "value": len(filtered),
                "note": "",
            },
        ]
        write_csv_atomic(summary_output, summary_rows, ["section", "metric", "value", "note"])
        write_csv_atomic(qc_output, qc_rows, ["check_name", "status", "observed", "expected", "severity", "note"])
        print("DRY_RUN PASS")
        return 0

    token = args.sonar_token or os.getenv("SONAR_TOKEN", "")
    if not token:
        raise SystemExit("SONAR_TOKEN is required in .env, environment, or --sonar-token")
    host = args.sonar_host.rstrip("/")
    session = requests.Session()
    session.auth = (token, "")
    session.headers.update({"Accept": "application/json", "User-Agent": "run-x-j01-v1"})

    server_status = check_server(session, host, args)
    logging.info(
        "SonarQube ready: version=%s status=%s",
        server_status.get("version", ""),
        server_status.get("status", ""),
    )

    file_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    started = time.monotonic()
    for selected_position, snapshot in enumerate(filtered, start=1):
        project_key = snapshot["project_key"]
        try:
            project_measures = fetch_project_measures(session, host, project_key, metrics, args)
            components = fetch_file_components(session, host, project_key, metrics, args)

            snapshot_file_rows: list[dict[str, Any]] = []
            duplicate_paths: Counter[str] = Counter()
            for component in components:
                path = component_path(component, project_key)
                duplicate_paths[path] += 1
                measures = metric_map(component.get("measures") or [])
                complexity_raw = measures.get("cognitive_complexity")
                ncloc_raw = measures.get("ncloc")
                row = {
                    "manifest_order": snapshot["manifest_order"],
                    "dataset_source": snapshot["dataset_source"],
                    "repo_name": snapshot["repo_name"],
                    "snapshot_key": snapshot["snapshot_key"],
                    "commit_sha": snapshot["commit_sha"],
                    "project_key": project_key,
                    "manifest_analysis_id": snapshot["manifest_analysis_id"],
                    "repo_month_rows": snapshot["repo_month_rows"],
                    "component_key": component.get("key", ""),
                    "component_name": component.get("name", ""),
                    "component_path": path,
                    "qualifier": component.get("qualifier", ""),
                    "language": component.get("language", ""),
                    "cognitive_complexity": 0.0 if complexity_raw is None else complexity_raw,
                    "cognitive_complexity_measure_present": int(complexity_raw is not None),
                    "ncloc": 0.0 if ncloc_raw is None else ncloc_raw,
                    "ncloc_measure_present": int(ncloc_raw is not None),
                }
                snapshot_file_rows.append(row)

            duplicate_path_count = sum(count > 1 for count in duplicate_paths.values())
            file_complexity_sum = sum(float(row["cognitive_complexity"]) for row in snapshot_file_rows)
            file_ncloc_sum = sum(float(row["ncloc"]) for row in snapshot_file_rows)
            project_complexity = project_measures.get("cognitive_complexity")
            project_ncloc = project_measures.get("ncloc")
            complexity_match = close_enough(file_complexity_sum, project_complexity)
            ncloc_match = close_enough(file_ncloc_sum, project_ncloc)

            file_rows.extend(snapshot_file_rows)
            snapshot_rows.append(
                {
                    "manifest_order": snapshot["manifest_order"],
                    "dataset_source": snapshot["dataset_source"],
                    "repo_name": snapshot["repo_name"],
                    "snapshot_key": snapshot["snapshot_key"],
                    "commit_sha": snapshot["commit_sha"],
                    "project_key": project_key,
                    "manifest_analysis_id": snapshot["manifest_analysis_id"],
                    "repo_month_rows": snapshot["repo_month_rows"],
                    "file_components": len(snapshot_file_rows),
                    "python_path_components": sum(
                        str(row["component_path"]).lower().endswith(".py")
                        for row in snapshot_file_rows
                    ),
                    "duplicate_component_paths": duplicate_path_count,
                    "files_with_complexity_measure": sum(
                        int(row["cognitive_complexity_measure_present"])
                        for row in snapshot_file_rows
                    ),
                    "files_with_ncloc_measure": sum(
                        int(row["ncloc_measure_present"]) for row in snapshot_file_rows
                    ),
                    "project_cognitive_complexity": project_complexity,
                    "file_cognitive_complexity_sum": file_complexity_sum,
                    "cognitive_complexity_reconciles": int(complexity_match),
                    "project_ncloc": project_ncloc,
                    "file_ncloc_sum": file_ncloc_sum,
                    "ncloc_reconciles": int(ncloc_match),
                    "status": "success",
                }
            )
        except Exception as exc:  # noqa: BLE001 - preserve per-snapshot failure provenance.
            logging.error("Failed snapshot %s (%s): %s", snapshot["snapshot_key"], project_key, exc)
            unresolved_rows.append(
                {
                    **snapshot,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )

        if selected_position % args.progress_every == 0 or selected_position == len(filtered):
            elapsed = max(time.monotonic() - started, 1e-9)
            rate = selected_position / elapsed * 3600.0
            logging.info(
                "Progress: %d/%d snapshots; success=%d unresolved=%d; rate=%.1f snapshots/hour",
                selected_position,
                len(filtered),
                len(snapshot_rows),
                len(unresolved_rows),
                rate,
            )
        if args.sleep_between_projects_seconds > 0:
            time.sleep(args.sleep_between_projects_seconds)

    duplicate_snapshot_paths = 0
    seen_pairs: set[tuple[str, str]] = set()
    for row in file_rows:
        pair = (str(row["snapshot_key"]), str(row["component_path"]))
        if pair in seen_pairs:
            duplicate_snapshot_paths += 1
        seen_pairs.add(pair)

    complexity_mismatches = sum(
        int(row["cognitive_complexity_reconciles"]) == 0 for row in snapshot_rows
    )
    ncloc_mismatches = sum(int(row["ncloc_reconciles"]) == 0 for row in snapshot_rows)
    non_python_components = sum(
        not str(row["component_path"]).lower().endswith(".py") for row in file_rows
    )

    add_qc(qc_rows, "selected_snapshots", len(filtered), len(filtered), True)
    add_qc(qc_rows, "successful_snapshots", len(snapshot_rows), len(filtered), len(snapshot_rows) == len(filtered))
    add_qc(qc_rows, "unresolved_snapshots", len(unresolved_rows), 0, len(unresolved_rows) == 0)
    add_qc(qc_rows, "duplicate_snapshot_component_paths", duplicate_snapshot_paths, 0, duplicate_snapshot_paths == 0)
    add_qc(qc_rows, "non_python_file_components", non_python_components, 0, non_python_components == 0)
    add_qc(
        qc_rows,
        "cognitive_complexity_project_file_sum_mismatches",
        complexity_mismatches,
        0,
        complexity_mismatches == 0,
        "hard" if args.strict_metric_reconciliation else "warning",
        "Project cognitive_complexity should equal the sum of file-level values.",
    )
    add_qc(
        qc_rows,
        "ncloc_project_file_sum_mismatches",
        ncloc_mismatches,
        0,
        ncloc_mismatches == 0,
        "hard" if args.strict_metric_reconciliation else "warning",
        "Project ncloc should equal the sum of file-level values.",
    )

    file_fields = [
        "manifest_order",
        "dataset_source",
        "repo_name",
        "snapshot_key",
        "commit_sha",
        "project_key",
        "manifest_analysis_id",
        "repo_month_rows",
        "component_key",
        "component_name",
        "component_path",
        "qualifier",
        "language",
        "cognitive_complexity",
        "cognitive_complexity_measure_present",
        "ncloc",
        "ncloc_measure_present",
    ]
    snapshot_fields = [
        "manifest_order",
        "dataset_source",
        "repo_name",
        "snapshot_key",
        "commit_sha",
        "project_key",
        "manifest_analysis_id",
        "repo_month_rows",
        "file_components",
        "python_path_components",
        "duplicate_component_paths",
        "files_with_complexity_measure",
        "files_with_ncloc_measure",
        "project_cognitive_complexity",
        "file_cognitive_complexity_sum",
        "cognitive_complexity_reconciles",
        "project_ncloc",
        "file_ncloc_sum",
        "ncloc_reconciles",
        "status",
    ]
    unresolved_fields = [
        "manifest_order",
        "dataset_source",
        "repo_name",
        "snapshot_key",
        "commit_sha",
        "project_key",
        "repo_month_rows",
        "manifest_status",
        "manifest_analysis_id",
        "error_type",
        "error_message",
    ]
    qc_fields = ["check_name", "status", "observed", "expected", "severity", "note"]

    hard_failures = [row for row in qc_rows if row["severity"] == "hard" and row["status"] == "fail"]
    warning_checks = [row for row in qc_rows if row["status"] == "warn"]
    run_status = "PASS" if not warning_checks else "PASS_WITH_WARNINGS"
    if hard_failures:
        run_status = "FAIL"

    summary_rows = [
        {"section": "implementation", "metric": "version", "value": IMPLEMENTATION_VERSION, "note": ""},
        {"section": "implementation", "metric": "retrieval_mode", "value": "existing_sonarqube_api_only", "note": "No rescan."},
        {"section": "implementation", "metric": "metrics", "value": ",".join(metrics), "note": ""},
        {"section": "input", "metric": "manifest_file", "value": str(input_path), "note": ""},
        {"section": "input", "metric": "manifest_sha256", "value": sha256_file(input_path), "note": ""},
        {"section": "input", "metric": "production_snapshots", "value": len(production_manifest), "note": ""},
        {"section": "run", "metric": "selected_snapshots", "value": len(filtered), "note": ""},
        {"section": "run", "metric": "successful_snapshots", "value": len(snapshot_rows), "note": ""},
        {"section": "run", "metric": "unresolved_snapshots", "value": len(unresolved_rows), "note": ""},
        {"section": "output", "metric": "file_rows", "value": len(file_rows), "note": "One row per snapshot/file component."},
        {"section": "qc", "metric": "complexity_reconciliation_mismatches", "value": complexity_mismatches, "note": ""},
        {"section": "qc", "metric": "ncloc_reconciliation_mismatches", "value": ncloc_mismatches, "note": ""},
        {"section": "qc", "metric": "non_python_components", "value": non_python_components, "note": ""},
        {"section": "run", "metric": "status", "value": run_status, "note": ""},
        {"section": "sonarqube", "metric": "version", "value": server_status.get("version", ""), "note": ""},
    ]

    write_csv_atomic(file_output, file_rows, file_fields)
    write_csv_atomic(snapshot_output, snapshot_rows, snapshot_fields)
    write_csv_atomic(unresolved_output, unresolved_rows, unresolved_fields)
    write_csv_atomic(qc_output, qc_rows, qc_fields)
    write_csv_atomic(summary_output, summary_rows, ["section", "metric", "value", "note"])

    print("=" * 72)
    print("run-x-j01 file-level SonarQube complexity retrieval summary")
    print(f"Status:                              {run_status}")
    print(f"Selected snapshots:                  {len(filtered)}")
    print(f"Successful snapshots:                {len(snapshot_rows)}")
    print(f"Unresolved snapshots:                {len(unresolved_rows)}")
    print(f"File component rows:                 {len(file_rows)}")
    print(f"Cognitive complexity mismatches:     {complexity_mismatches}")
    print(f"NCLOC mismatches:                    {ncloc_mismatches}")
    print(f"Non-Python file components:          {non_python_components}")
    print(f"File output:                         {file_output}")
    print(f"Snapshot output:                     {snapshot_output}")
    print(f"QC output:                           {qc_output}")
    print(f"Summary output:                      {summary_output}")
    print("=" * 72)

    if hard_failures:
        return 2
    if args.fail_on_unresolved and unresolved_rows:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
