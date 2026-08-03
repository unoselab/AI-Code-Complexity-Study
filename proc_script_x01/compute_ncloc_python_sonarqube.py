#!/usr/bin/env python3
"""Compute Python-only SonarQube NCLOC for the Model C snapshot manifest.

This program is the self-contained analysis implementation for run-x-b01.
It does not call any prior experiment script. The workflow is:

1. Read the run-x-a05 Model C snapshot manifest.
2. Validate the expected 1,496 repository-commit snapshots and coverage.
3. Create a detached temporary Git worktree for each historical commit.
4. run SonarScanner with ``sonar.inclusions=**/*.py``.
5. Poll the SonarQube Compute Engine task until completion.
6. Fetch the project-level ``ncloc`` measure as ``ncloc_py``.
7. Save each result atomically so interrupted runs can resume.
8. Write a completed manifest, unresolved targets, and QC summaries.

The main treatment/control clones are never checked out, reset, or cleaned.
All historical scans use detached temporary Git worktrees.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
except ImportError:  # Exported environment variables are sufficient.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(override=True)


IMPLEMENTATION_VERSION = "v1"
HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
EXPECTED_DATASET_SOURCES = {"treatment", "control"}

REQUIRED_INPUT_COLUMNS = {
    "dataset_source",
    "repo_name",
    "latest_commit_effective",
    "repo_month_rows",
    "first_panel_month",
    "last_panel_month",
    "clone_path",
    "python_file_count_all",
    "python_file_count_source",
    "tracked_file_count",
    "ncloc_model_a",
    "ncloc_source_values",
    "ncloc_py",
    "ncloc_py_status",
}

RESULT_COLUMNS = [
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "repo_key",
    "commit_sha",
    "clone_path",
    "repo_month_rows",
    "first_panel_month",
    "last_panel_month",
    "project_key",
    "project_version",
    "implementation_version",
    "scan_attempt",
    "scan_scope",
    "worktree_path",
    "scanner_log_path",
    "scan_started_at",
    "scan_completed_at",
    "runtime_seconds",
    "git_precheck_status",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "scanner_return_code",
    "ce_task_id",
    "analysis_id",
    "ncloc_py",
    "status",
    "error_stage",
    "error_message",
]

SONAR_EXCLUSIONS = ",".join(
    [
        "**/.git/**",
        "**/.scannerwork/**",
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
        "**/env/**",
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.tox/**",
        "**/.mypy_cache/**",
        "**/.pytest_cache/**",
        "**/coverage/**",
        "**/.next/**",
        "**/.nuxt/**",
    ]
)


@dataclass(frozen=True)
class SonarConfig:
    """Runtime configuration for one SonarQube scan."""

    host: str
    token: str
    scanner: str
    project_key_prefix: str
    scanner_timeout_seconds: int
    compute_timeout_seconds: int
    poll_interval_seconds: int


@dataclass
class RunCounters:
    """Counters used for progress and final QC reporting."""

    selected_targets: int = 0
    processed_this_run: int = 0
    skipped_existing_success: int = 0
    successful_this_run: int = 0
    failed_this_run: int = 0


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_key(value: str, max_length: int = 120) -> str:
    """Create a SonarQube-safe key fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value).strip())
    cleaned = cleaned.strip("_.:-") or "unknown"
    return cleaned[:max_length]


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    """Build a stable repository-snapshot identifier."""
    raw = f"{dataset_source}|{repo_name.lower()}|{commit_sha.lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return (
        f"{sanitize_key(dataset_source, 16)}__"
        f"{sanitize_key(repo_name, 70)}__{commit_sha[:12].lower()}__{digest}"
    )


def make_project_key(
    prefix: str, dataset_source: str, repo_name: str, commit_sha: str
) -> str:
    """Build a unique SonarQube project key for one historical snapshot."""
    raw_identity = f"{dataset_source}|{repo_name.lower()}|{commit_sha.lower()}"
    digest = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:12]
    key = (
        f"{prefix}{sanitize_key(dataset_source, 12)}_"
        f"{sanitize_key(repo_name, 110)}_{commit_sha[:12].lower()}_{digest}"
    )
    if key.isdigit():
        key = f"p_{key}"
    return key[:190]


def make_worktree_name(manifest_order: int, snapshot_key: str) -> str:
    """Create a short deterministic worktree directory name."""
    digest = hashlib.sha256(snapshot_key.encode("utf-8")).hexdigest()[:20]
    return f"snapshot_{manifest_order:04d}_{digest}"


def run_command(
    command: list[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with consistent text-mode behavior."""
    logging.debug("Running command: %s", " ".join(command))
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
        check=check,
        timeout=timeout,
    )


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp_path, index=False)
    temp_path.replace(path)


def load_existing_results(path: Path) -> pd.DataFrame:
    """Load prior incremental results for resume behavior."""
    path = path.expanduser().resolve()
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    existing = pd.read_csv(path)
    if "snapshot_key" not in existing.columns:
        raise ValueError(f"Existing result file has no snapshot_key: {path}")
    if existing["snapshot_key"].duplicated().any():
        duplicates = existing.loc[
            existing["snapshot_key"].duplicated(keep=False), "snapshot_key"
        ].head(10)
        raise ValueError(
            "Existing result file contains duplicate snapshot_key rows: "
            + ", ".join(duplicates.astype(str))
        )
    for column in RESULT_COLUMNS:
        if column not in existing.columns:
            existing[column] = pd.NA
    return existing[RESULT_COLUMNS].copy()


def upsert_result(existing: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
    """Insert or replace one snapshot result by snapshot_key."""
    row = pd.DataFrame([{column: result.get(column, pd.NA) for column in RESULT_COLUMNS}])
    if existing.empty:
        return row
    remaining = existing[existing["snapshot_key"] != result["snapshot_key"]].copy()
    return pd.concat([remaining, row], ignore_index=True, sort=False)[RESULT_COLUMNS]


def normalize_input_manifest(raw: pd.DataFrame, project_key_prefix: str) -> pd.DataFrame:
    """Validate and normalize the run-x-a05 Model C snapshot manifest."""
    missing_columns = REQUIRED_INPUT_COLUMNS - set(raw.columns)
    if missing_columns:
        raise ValueError(
            "Model C snapshot manifest is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    manifest = raw.copy()
    manifest["dataset_source"] = (
        manifest["dataset_source"].astype(str).str.strip().str.lower()
    )
    unexpected_sources = set(manifest["dataset_source"].dropna().unique()) - EXPECTED_DATASET_SOURCES
    if unexpected_sources:
        raise ValueError(f"Unexpected dataset_source values: {sorted(unexpected_sources)}")

    manifest["repo_name"] = manifest["repo_name"].astype(str).str.strip()
    manifest["clone_path"] = manifest["clone_path"].astype(str).str.strip()
    manifest["commit_sha"] = (
        manifest["latest_commit_effective"].astype(str).str.strip().str.lower()
    )

    invalid_sha = ~manifest["commit_sha"].str.fullmatch(HEX_SHA_RE)
    if invalid_sha.any():
        examples = manifest.loc[
            invalid_sha, ["dataset_source", "repo_name", "latest_commit_effective"]
        ].head(10)
        raise ValueError(
            "Model C manifest contains invalid commit SHAs:\n"
            + examples.to_string(index=False)
        )

    numeric_columns = [
        "repo_month_rows",
        "python_file_count_all",
        "python_file_count_source",
        "tracked_file_count",
        "ncloc_model_a",
    ]
    for column in numeric_columns:
        manifest[column] = pd.to_numeric(manifest[column], errors="coerce")

    if manifest["repo_month_rows"].isna().any() or (manifest["repo_month_rows"] <= 0).any():
        raise ValueError("repo_month_rows must be positive for every Model C snapshot.")
    if manifest["python_file_count_all"].isna().any() or (
        manifest["python_file_count_all"] <= 0
    ).any():
        raise ValueError("Every Model C snapshot must have at least one Python file.")
    if manifest["ncloc_model_a"].isna().any():
        raise ValueError("Model C manifest contains missing Model A NCLOC values.")

    duplicate_key = manifest.duplicated(
        ["dataset_source", "repo_name", "commit_sha"], keep=False
    )
    if duplicate_key.any():
        examples = manifest.loc[
            duplicate_key, ["dataset_source", "repo_name", "commit_sha"]
        ].head(10)
        raise ValueError(
            "Duplicate Model C repository-snapshot keys were found:\n"
            + examples.to_string(index=False)
        )

    # Preserve the source manifest order. This makes resume files easy to compare
    # with run-x-a05 while remaining deterministic for the same input file.
    manifest = manifest.reset_index(drop=True)
    manifest.insert(0, "manifest_order", range(1, len(manifest) + 1))
    manifest["snapshot_key"] = manifest.apply(
        lambda row: make_snapshot_key(
            str(row["dataset_source"]),
            str(row["repo_name"]),
            str(row["commit_sha"]),
        ),
        axis=1,
    )
    manifest["project_key"] = manifest.apply(
        lambda row: make_project_key(
            project_key_prefix,
            str(row["dataset_source"]),
            str(row["repo_name"]),
            str(row["commit_sha"]),
        ),
        axis=1,
    )
    manifest["project_version"] = manifest["commit_sha"]
    manifest["scan_scope"] = "python_only_sonar_inclusions"
    manifest["python_file_count_manifest"] = manifest[
        "python_file_count_all"
    ].round().astype("Int64")

    if manifest["snapshot_key"].duplicated().any():
        raise ValueError("Generated snapshot_key values are not unique.")
    if manifest["project_key"].duplicated().any():
        raise ValueError("Generated SonarQube project_key values are not unique.")

    return manifest


def expected_count_checks(manifest: pd.DataFrame, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build structural input checks and optionally fail on mismatches."""
    role_counts = manifest["dataset_source"].value_counts().to_dict()
    role_coverage = (
        manifest.groupby("dataset_source")["repo_month_rows"].sum().astype(int).to_dict()
    )
    role_repos = manifest.groupby("dataset_source")["repo_name"].nunique().to_dict()

    checks = [
        ("input_snapshot_rows", len(manifest), args.expected_snapshots),
        ("treatment_snapshots", int(role_counts.get("treatment", 0)), args.expected_treatment_snapshots),
        ("control_snapshots", int(role_counts.get("control", 0)), args.expected_control_snapshots),
        ("repo_month_coverage", int(manifest["repo_month_rows"].sum()), args.expected_repo_month_rows),
        ("treatment_repo_month_coverage", int(role_coverage.get("treatment", 0)), args.expected_treatment_repo_month_rows),
        ("control_repo_month_coverage", int(role_coverage.get("control", 0)), args.expected_control_repo_month_rows),
        ("unique_repositories", int(manifest["repo_name"].nunique()), args.expected_repositories),
        ("treatment_repositories", int(role_repos.get("treatment", 0)), args.expected_treatment_repositories),
        ("control_repositories", int(role_repos.get("control", 0)), args.expected_control_repositories),
    ]

    records: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for name, observed, expected in checks:
        passed = int(observed) == int(expected)
        records.append(
            {
                "check_name": name,
                "status": "pass" if passed else "fail",
                "observed": observed,
                "expected": expected,
                "note": "",
            }
        )
        if not passed:
            mismatches.append(f"{name}: observed={observed}, expected={expected}")

    if args.strict_expected_counts and mismatches:
        raise ValueError("Strict expected-count checks failed: " + " | ".join(mismatches))
    return records


def validate_git_snapshot(clone_path: Path, commit_sha: str) -> tuple[bool, str]:
    """Validate that a clone exists and contains the requested commit."""
    if not clone_path.exists():
        return False, "clone_path_missing"
    try:
        run_command(["git", "-C", str(clone_path), "rev-parse", "--git-dir"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False, "not_git_repository"
    try:
        run_command(
            ["git", "-C", str(clone_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"]
        )
    except subprocess.CalledProcessError:
        return False, "commit_not_found"
    return True, "ready"


def create_worktree(clone_path: Path, worktree_path: Path, commit_sha: str) -> None:
    """Create a detached temporary worktree for one historical commit."""
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        try:
            run_command(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree_path),
                ],
                check=False,
            )
        finally:
            shutil.rmtree(worktree_path, ignore_errors=True)

    run_command(
        [
            "git",
            "-C",
            str(clone_path),
            "worktree",
            "add",
            "--detach",
            str(worktree_path),
            commit_sha,
        ]
    )


def remove_worktree(clone_path: Path, worktree_path: Path) -> None:
    """Remove a temporary worktree without changing the main clone checkout."""
    try:
        run_command(
            [
                "git",
                "-C",
                str(clone_path),
                "worktree",
                "remove",
                "--force",
                str(worktree_path),
            ],
            check=False,
        )
        run_command(
            ["git", "-C", str(clone_path), "worktree", "prune"],
            check=False,
        )
    finally:
        shutil.rmtree(worktree_path, ignore_errors=True)


def count_python_files(worktree_path: Path) -> int:
    """Count checked-out Python files while skipping scanner metadata."""
    count = 0
    excluded_directory_names = {
        ".git",
        ".scannerwork",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "coverage",
        ".next",
        ".nuxt",
    }
    for root, directories, files in os.walk(worktree_path, followlinks=False):
        directories[:] = [
            directory
            for directory in directories
            if directory not in excluded_directory_names
        ]
        count += sum(1 for filename in files if filename.lower().endswith(".py"))
    return count


def wait_for_sonar_system(
    host: str, timeout_seconds: int, poll_interval_seconds: int
) -> None:
    """Wait until SonarQube reports an operational status."""
    deadline = time.monotonic() + timeout_seconds
    endpoint = urljoin(host.rstrip("/") + "/", "api/system/status")
    last_error = ""

    while time.monotonic() < deadline:
        try:
            response = requests.get(endpoint, timeout=15)
            response.raise_for_status()
            status = str(response.json().get("status", "")).upper()
            if status == "UP":
                logging.info("SonarQube is ready at %s", host)
                return
            last_error = f"SonarQube status is {status or 'unknown'}"
        except requests.RequestException as exc:
            last_error = str(exc)
        logging.info("Waiting for SonarQube: %s", last_error)
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"SonarQube did not become ready within {timeout_seconds} seconds: {last_error}"
    )


def parse_report_task(report_file: Path) -> dict[str, str]:
    """Parse SonarScanner's report-task.txt file."""
    values: dict[str, str] = {}
    if not report_file.exists():
        return values
    for line in report_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def poll_compute_task(ce_task_url: str, config: SonarConfig) -> dict[str, Any]:
    """Poll one SonarQube Compute Engine task until terminal status."""
    deadline = time.monotonic() + config.compute_timeout_seconds
    auth = (config.token, "")
    last_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        response = requests.get(ce_task_url, auth=auth, timeout=30)
        response.raise_for_status()
        task = response.json().get("task", {})
        last_payload = task
        status = str(task.get("status", "")).upper()
        if status == "SUCCESS":
            return task
        if status in {"FAILED", "CANCELED"}:
            error_message = task.get("errorMessage") or ""
            raise RuntimeError(
                f"SonarQube Compute Engine status={status}: {error_message}"
            )
        logging.debug("Compute Engine status=%s", status or "UNKNOWN")
        time.sleep(config.poll_interval_seconds)

    raise TimeoutError(
        "Timed out waiting for SonarQube Compute Engine task. "
        f"Last payload: {last_payload}"
    )


def fetch_ncloc_py(project_key: str, config: SonarConfig) -> float:
    """Fetch the current project-level NCLOC measure for a Python-only scan."""
    endpoint = urljoin(config.host.rstrip("/") + "/", "api/measures/component")
    response = requests.get(
        endpoint,
        auth=(config.token, ""),
        params={"component": project_key, "metricKeys": "ncloc"},
        timeout=30,
    )
    response.raise_for_status()
    measures = response.json().get("component", {}).get("measures", [])
    for measure in measures:
        if measure.get("metric") == "ncloc" and "value" in measure:
            value = float(measure["value"])
            if value < 0:
                raise RuntimeError(f"SonarQube returned negative ncloc={value}")
            return value
    raise RuntimeError(f"No ncloc measure returned for SonarQube project {project_key}")


def write_scanner_log(
    path: Path,
    command: list[str],
    *,
    return_code: int,
    stdout: str,
    stderr: str,
) -> None:
    """Persist the scanner command and output for one snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("Command:\n")
        handle.write(" ".join(command) + "\n\n")
        handle.write(f"Return code: {return_code}\n\n")
        handle.write("STDOUT:\n")
        handle.write(stdout or "")
        handle.write("\n\nSTDERR:\n")
        handle.write(stderr or "")


def prior_attempt_count(existing: pd.DataFrame, snapshot_key: str) -> int:
    """Return the previous attempt count for one snapshot."""
    if existing.empty:
        return 0
    rows = existing[existing["snapshot_key"].eq(snapshot_key)]
    if rows.empty:
        return 0
    value = pd.to_numeric(rows.iloc[-1].get("scan_attempt"), errors="coerce")
    return int(value) if pd.notna(value) else 0


def base_result_row(
    manifest_row: pd.Series,
    *,
    scan_attempt: int,
    worktree_path: Path,
    scanner_log_path: Path,
) -> dict[str, Any]:
    """Create a complete result record with default values."""
    values = {
        "manifest_order": int(manifest_row["manifest_order"]),
        "snapshot_key": str(manifest_row["snapshot_key"]),
        "dataset_source": str(manifest_row["dataset_source"]),
        "repo_name": str(manifest_row["repo_name"]),
        "repo_key": str(manifest_row.get("repo_key", "")),
        "commit_sha": str(manifest_row["commit_sha"]),
        "clone_path": str(manifest_row["clone_path"]),
        "repo_month_rows": int(manifest_row["repo_month_rows"]),
        "first_panel_month": str(manifest_row["first_panel_month"]),
        "last_panel_month": str(manifest_row["last_panel_month"]),
        "project_key": str(manifest_row["project_key"]),
        "project_version": str(manifest_row["project_version"]),
        "implementation_version": IMPLEMENTATION_VERSION,
        "scan_attempt": scan_attempt,
        "scan_scope": "python_only_sonar_inclusions",
        "worktree_path": str(worktree_path),
        "scanner_log_path": str(scanner_log_path),
        "scan_started_at": utc_now(),
        "scan_completed_at": "",
        "runtime_seconds": pd.NA,
        "git_precheck_status": "pending",
        "python_file_count_manifest": int(manifest_row["python_file_count_manifest"]),
        "python_file_count_git": pd.NA,
        "python_file_count_matches_manifest": pd.NA,
        "scanner_return_code": pd.NA,
        "ce_task_id": "",
        "analysis_id": "",
        "ncloc_py": pd.NA,
        "status": "pending",
        "error_stage": "",
        "error_message": "",
    }
    return values


def run_sonar_snapshot(
    manifest_row: pd.Series,
    *,
    existing_results: pd.DataFrame,
    config: SonarConfig,
    worktree_root: Path,
    scanner_log_dir: Path,
    keep_worktrees: bool,
) -> dict[str, Any]:
    """Scan one historical snapshot and return an incremental result row."""
    snapshot_key = str(manifest_row["snapshot_key"])
    clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
    commit_sha = str(manifest_row["commit_sha"]).lower()
    repo_name = str(manifest_row["repo_name"])
    worktree_path = worktree_root / make_worktree_name(
        int(manifest_row["manifest_order"]), snapshot_key
    )
    scanner_log_path = scanner_log_dir / f"{snapshot_key}.log"
    scan_attempt = prior_attempt_count(existing_results, snapshot_key) + 1
    result = base_result_row(
        manifest_row,
        scan_attempt=scan_attempt,
        worktree_path=worktree_path,
        scanner_log_path=scanner_log_path,
    )
    started = time.monotonic()

    ready, precheck_status = validate_git_snapshot(clone_path, commit_sha)
    result["git_precheck_status"] = precheck_status
    if not ready:
        result["status"] = precheck_status
        result["error_stage"] = "git_precheck"
        result["error_message"] = precheck_status
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)
        return result

    try:
        create_worktree(clone_path, worktree_path, commit_sha)
        python_file_count_git = count_python_files(worktree_path)
        result["python_file_count_git"] = python_file_count_git
        result["python_file_count_matches_manifest"] = (
            python_file_count_git == int(result["python_file_count_manifest"])
        )
        if python_file_count_git <= 0:
            result["status"] = "no_python_files"
            result["error_stage"] = "python_file_precheck"
            result["error_message"] = "No Python files were found in the checked-out snapshot."
            return result

        scanner_command = [
            config.scanner,
            f"-Dsonar.projectKey={result['project_key']}",
            f"-Dsonar.projectName={result['project_key']}",
            f"-Dsonar.projectVersion={result['project_version']}",
            "-Dsonar.sources=.",
            "-Dsonar.inclusions=**/*.py",
            "-Dsonar.python.version=3.11",
            "-Dsonar.sourceEncoding=UTF-8",
            f"-Dsonar.exclusions={SONAR_EXCLUSIONS}",
            f"-Dsonar.host.url={config.host}",
            f"-Dsonar.token={config.token}",
            "-Dsonar.scm.disabled=true",
        ]
        masked_command = [
            "-Dsonar.token=***" if part.startswith("-Dsonar.token=") else part
            for part in scanner_command
        ]

        try:
            process = subprocess.run(
                scanner_command,
                cwd=str(worktree_path),
                text=True,
                capture_output=True,
                check=False,
                timeout=config.scanner_timeout_seconds,
            )
            result["scanner_return_code"] = process.returncode
            write_scanner_log(
                scanner_log_path,
                masked_command,
                return_code=process.returncode,
                stdout=process.stdout or "",
                stderr=process.stderr or "",
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            write_scanner_log(
                scanner_log_path,
                masked_command,
                return_code=124,
                stdout=stdout,
                stderr=stderr + "\nScanner timed out.\n",
            )
            result["scanner_return_code"] = 124
            result["status"] = "scanner_timeout"
            result["error_stage"] = "sonar_scanner"
            result["error_message"] = (
                f"SonarScanner exceeded {config.scanner_timeout_seconds} seconds."
            )
            return result

        if process.returncode != 0:
            result["status"] = "scanner_failed"
            result["error_stage"] = "sonar_scanner"
            result["error_message"] = (
                f"SonarScanner exited with code {process.returncode}; "
                f"see {scanner_log_path}"
            )
            return result

        report = parse_report_task(worktree_path / ".scannerwork" / "report-task.txt")
        ce_task_url = report.get("ceTaskUrl", "")
        if not ce_task_url:
            result["status"] = "report_task_missing"
            result["error_stage"] = "report_task"
            result["error_message"] = (
                f"report-task.txt has no ceTaskUrl; see {scanner_log_path}"
            )
            return result

        try:
            task = poll_compute_task(ce_task_url, config)
        except TimeoutError as exc:
            result["status"] = "compute_timeout"
            result["error_stage"] = "compute_engine"
            result["error_message"] = str(exc)
            return result
        except Exception as exc:
            result["status"] = "compute_failed"
            result["error_stage"] = "compute_engine"
            result["error_message"] = str(exc)
            return result

        result["ce_task_id"] = task.get("id", "")
        result["analysis_id"] = task.get("analysisId", "")
        try:
            result["ncloc_py"] = fetch_ncloc_py(str(result["project_key"]), config)
        except Exception as exc:
            result["status"] = "measure_fetch_failed"
            result["error_stage"] = "measure_fetch"
            result["error_message"] = str(exc)
            return result

        result["status"] = "success"
        return result

    except Exception as exc:  # Preserve the failure and continue other targets.
        logging.exception("Snapshot scan failed for %s at %s", repo_name, commit_sha)
        result["status"] = "scan_failed"
        result["error_stage"] = result.get("error_stage") or "snapshot_scan"
        result["error_message"] = str(exc)
        return result
    finally:
        if not keep_worktrees:
            remove_worktree(clone_path, worktree_path)
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)


def build_completed_manifest(
    manifest: pd.DataFrame, results: pd.DataFrame
) -> pd.DataFrame:
    """Merge current snapshot results into the full Model C manifest."""
    result_columns = [
        "snapshot_key",
        "scan_attempt",
        "status",
        "ncloc_py",
        "git_precheck_status",
        "python_file_count_git",
        "python_file_count_matches_manifest",
        "scanner_return_code",
        "ce_task_id",
        "analysis_id",
        "scanner_log_path",
        "scan_started_at",
        "scan_completed_at",
        "runtime_seconds",
        "error_stage",
        "error_message",
    ]
    available = [column for column in result_columns if column in results.columns]
    merged = manifest.merge(results[available], on="snapshot_key", how="left")
    merged["ncloc_py_status_original"] = merged["ncloc_py_status"]
    merged["ncloc_py_original"] = merged["ncloc_py_x"] if "ncloc_py_x" in merged else merged["ncloc_py"]

    if "ncloc_py_y" in merged.columns:
        merged["ncloc_py"] = pd.to_numeric(merged["ncloc_py_y"], errors="coerce")
        merged = merged.drop(columns=["ncloc_py_x", "ncloc_py_y"])
    else:
        merged["ncloc_py"] = pd.to_numeric(merged["ncloc_py"], errors="coerce")

    status_series = merged.get(
        "status", pd.Series(index=merged.index, dtype="object")
    )
    merged["ncloc_py_status"] = status_series.fillna("pending")
    merged["ncloc_py_available"] = merged["ncloc_py_status"].eq("success") & merged[
        "ncloc_py"
    ].notna()
    merged["ncloc_py_source"] = merged["ncloc_py_available"].map(
        {True: "run-x-b01-sonarqube-python-only", False: ""}
    )
    return merged.sort_values("manifest_order", kind="stable").reset_index(drop=True)


def build_qc_records(
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    completed: pd.DataFrame,
    structural_checks: list[dict[str, Any]],
    counters: RunCounters,
    *,
    dry_run: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build check-oriented and long-form summary outputs."""
    qc_records = list(structural_checks)

    def add_check(
        name: str,
        status: str,
        observed: Any,
        expected: Any = "",
        note: str = "",
    ) -> None:
        qc_records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    result_status_counts = (
        results["status"].fillna("missing").value_counts().to_dict()
        if not results.empty and "status" in results.columns
        else {}
    )
    manifest_keys = set(manifest["snapshot_key"].astype(str))
    result_keys = set(results["snapshot_key"].dropna().astype(str)) if not results.empty else set()
    orphan_result_rows = len(result_keys - manifest_keys)
    successful = completed[completed["ncloc_py_available"]].copy()
    unresolved = completed[~completed["ncloc_py_available"]].copy()
    mismatch_count = int(
        completed["python_file_count_matches_manifest"].eq(False).fillna(False).sum()
    )
    duplicate_snapshot_keys = int(completed["snapshot_key"].duplicated().sum())
    duplicate_project_keys = int(completed["project_key"].duplicated().sum())
    negative_ncloc = int(
        (pd.to_numeric(successful["ncloc_py"], errors="coerce") < 0).sum()
    )
    successful_coverage = int(successful["repo_month_rows"].sum())

    add_check(
        "completed_manifest_rows",
        "pass" if len(completed) == len(manifest) else "fail",
        len(completed),
        len(manifest),
    )
    add_check(
        "orphan_result_snapshot_keys",
        "pass" if orphan_result_rows == 0 else "fail",
        orphan_result_rows,
        0,
        "Result rows must belong to the current run-x-a05 Model C manifest.",
    )
    add_check(
        "duplicate_snapshot_keys",
        "pass" if duplicate_snapshot_keys == 0 else "fail",
        duplicate_snapshot_keys,
        0,
    )
    add_check(
        "duplicate_project_keys",
        "pass" if duplicate_project_keys == 0 else "fail",
        duplicate_project_keys,
        0,
    )
    add_check(
        "negative_ncloc_py_values",
        "pass" if negative_ncloc == 0 else "fail",
        negative_ncloc,
        0,
    )
    add_check(
        "python_file_count_mismatches",
        "warn" if mismatch_count > 0 else "pass",
        mismatch_count,
        0,
        "A mismatch is recorded for review but does not invalidate SonarQube NCLOC.",
    )
    add_check(
        "successful_snapshots",
        "pass" if len(unresolved) == 0 and not dry_run else "warn",
        len(successful),
        len(manifest) if not dry_run else "dry_run",
    )
    add_check(
        "unresolved_snapshots",
        "pass" if len(unresolved) == 0 and not dry_run else "warn",
        len(unresolved),
        0 if not dry_run else "dry_run",
    )
    add_check(
        "successful_repo_month_coverage",
        "pass" if successful_coverage == int(manifest["repo_month_rows"].sum()) and not dry_run else "warn",
        successful_coverage,
        int(manifest["repo_month_rows"].sum()) if not dry_run else "dry_run",
    )

    summary_records: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_records.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("definition", "target", "model_c_python_only_ncloc")
    add_summary("definition", "scan_scope", "sonar.inclusions=**/*.py")
    add_summary("definition", "checkout_method", "detached_temporary_git_worktree")
    add_summary("definition", "resume_key", "snapshot_key")
    add_summary("definition", "dry_run", int(dry_run))
    add_summary("input", "snapshots", len(manifest))
    add_summary("input", "repositories", manifest["repo_name"].nunique())
    add_summary("input", "repo_month_coverage", int(manifest["repo_month_rows"].sum()))
    for role, group in manifest.groupby("dataset_source", sort=True):
        add_summary("input_by_role", f"{role}_snapshots", len(group))
        add_summary("input_by_role", f"{role}_repositories", group["repo_name"].nunique())
        add_summary(
            "input_by_role",
            f"{role}_repo_month_coverage",
            int(group["repo_month_rows"].sum()),
        )
    add_summary("run", "selected_targets", counters.selected_targets)
    add_summary("run", "processed_this_run", counters.processed_this_run)
    add_summary("run", "skipped_existing_success", counters.skipped_existing_success)
    add_summary("run", "successful_this_run", counters.successful_this_run)
    add_summary("run", "failed_this_run", counters.failed_this_run)
    for status, count in sorted(result_status_counts.items()):
        add_summary("result_status", str(status), int(count))
    add_summary("result", "successful_snapshots", len(successful))
    add_summary("result", "unresolved_snapshots", len(unresolved))
    add_summary("result", "successful_repo_month_coverage", successful_coverage)
    add_summary("qc", "python_file_count_mismatches", mismatch_count)
    add_summary("qc", "orphan_result_snapshot_keys", orphan_result_rows)
    if not successful.empty:
        values = pd.to_numeric(successful["ncloc_py"], errors="coerce").dropna()
        add_summary("ncloc_py", "min", values.min() if not values.empty else "")
        add_summary("ncloc_py", "median", values.median() if not values.empty else "")
        add_summary("ncloc_py", "mean", values.mean() if not values.empty else "")
        add_summary("ncloc_py", "max", values.max() if not values.empty else "")

    return pd.DataFrame(qc_records), pd.DataFrame(summary_records)


def filter_targets(manifest: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    """Apply optional source, repository, order, and limit filters."""
    selected = manifest.copy()
    if args.dataset_source:
        selected = selected[selected["dataset_source"].eq(args.dataset_source.lower())]
    if args.repo_name:
        selected = selected[selected["repo_name"].eq(args.repo_name)]
    selected = selected[selected["manifest_order"] >= args.start_order]
    if args.limit > 0:
        selected = selected.head(args.limit)
    if selected.empty:
        raise ValueError("No Model C snapshots matched the requested filters.")
    return selected.copy()


def progress_message(
    position: int,
    total: int,
    counters: RunCounters,
    run_started_monotonic: float,
) -> str:
    """Build a compact progress message with processing rate and ETA."""
    elapsed = max(time.monotonic() - run_started_monotonic, 0.001)
    completed = counters.processed_this_run + counters.skipped_existing_success
    rate_per_hour = completed / elapsed * 3600 if completed else 0.0
    remaining = max(total - completed, 0)
    eta_hours = remaining / rate_per_hour if rate_per_hour > 0 else float("nan")
    eta_text = f"{eta_hours:.2f}" if eta_hours == eta_hours else "unknown"
    return (
        f"Progress: {completed}/{total}; position={position}; "
        f"processed={counters.processed_this_run}; "
        f"skipped_success={counters.skipped_existing_success}; "
        f"success_this_run={counters.successful_this_run}; "
        f"failed_this_run={counters.failed_this_run}; "
        f"rate_snapshots_per_hour={rate_per_hour:.2f}; eta_hours={eta_text}"
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Compute Python-only SonarQube NCLOC for the run-x-a05 Model C "
            "snapshot manifest."
        )
    )
    parser.add_argument("--input-manifest-file", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-output", type=Path, required=True)
    parser.add_argument("--snapshot-results-output", type=Path, required=True)
    parser.add_argument("--completed-manifest-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--scan-qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--scanner-log-dir", type=Path, required=True)
    parser.add_argument(
        "--sonar-host", default=os.getenv("SONAR_HOST", "http://localhost:9000")
    )
    parser.add_argument("--sonar-token", default=os.getenv("SONAR_TOKEN", ""))
    parser.add_argument(
        "--sonar-scanner",
        default=(
            os.getenv("SONAR_PATH")
            or os.getenv("SONAR_SCANNER_PATH")
            or shutil.which("sonar-scanner")
            or "sonar-scanner"
        ),
    )
    parser.add_argument("--project-key-prefix", default="b01_ncloc_py_")
    parser.add_argument("--server-timeout-seconds", type=int, default=300)
    parser.add_argument("--scanner-timeout-seconds", type=int, default=1800)
    parser.add_argument("--compute-timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--sleep-between-scans-seconds", type=float, default=0.0)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0, help="Process the first N selected snapshots; 0 means all.")
    parser.add_argument("--dataset-source", choices=["", "treatment", "control"], default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--analysis-again", action="store_true")
    parser.add_argument("--keep-worktrees", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-treatment-snapshots", type=int, default=790)
    parser.add_argument("--expected-control-snapshots", type=int, default=706)
    parser.add_argument("--expected-repo-month-rows", type=int, default=1954)
    parser.add_argument("--expected-treatment-repo-month-rows", type=int, default=914)
    parser.add_argument("--expected-control-repo-month-rows", type=int, default=1040)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def validate_cli_args(args: argparse.Namespace) -> None:
    """Validate numeric CLI arguments before reading data."""
    integer_nonnegative = [
        "server_timeout_seconds",
        "scanner_timeout_seconds",
        "compute_timeout_seconds",
        "poll_interval_seconds",
        "progress_every",
        "limit",
    ]
    for name in integer_nonnegative:
        value = int(getattr(args, name))
        if value < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative.")
    if args.start_order < 1:
        raise ValueError("--start-order must be at least 1.")
    if args.sleep_between_scans_seconds < 0:
        raise ValueError("--sleep-between-scans-seconds must be non-negative.")
    if args.poll_interval_seconds == 0 and not args.dry_run:
        raise ValueError("--poll-interval-seconds must be positive for a real scan.")


def main() -> int:
    """Run the Model C Python-only NCLOC workflow."""
    args = parse_args()
    validate_cli_args(args)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    input_path = args.input_manifest_file.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Model C snapshot manifest not found: {input_path}")

    raw_manifest = pd.read_csv(input_path)
    manifest = normalize_input_manifest(raw_manifest, args.project_key_prefix)
    structural_checks = expected_count_checks(manifest, args)
    save_dataframe(manifest, args.snapshot_manifest_output)

    selected = filter_targets(manifest, args)
    counters = RunCounters(selected_targets=len(selected))
    existing_results = load_existing_results(args.snapshot_results_output)
    results = existing_results.copy()

    if args.dry_run:
        for _, target in selected.iterrows():
            snapshot_key = str(target["snapshot_key"])
            worktree_path = args.worktree_root.expanduser().resolve() / make_worktree_name(
                int(target["manifest_order"]), snapshot_key
            )
            scanner_log_path = (
                args.scanner_log_dir.expanduser().resolve() / f"{snapshot_key}.log"
            )
            result = base_result_row(
                target,
                scan_attempt=prior_attempt_count(results, snapshot_key) + 1,
                worktree_path=worktree_path,
                scanner_log_path=scanner_log_path,
            )
            result.update(
                {
                    "scan_completed_at": utc_now(),
                    "runtime_seconds": 0.0,
                    "git_precheck_status": "not_checked_dry_run",
                    "status": "dry_run",
                    "error_stage": "",
                    "error_message": "",
                }
            )
            results = upsert_result(results, result)
            counters.processed_this_run += 1
        save_dataframe(results.sort_values("manifest_order", kind="stable"), args.snapshot_results_output)
    else:
        if not args.sonar_token:
            raise ValueError("SONAR_TOKEN or --sonar-token is required for SonarQube scanning.")
        scanner_path = shutil.which(args.sonar_scanner) or args.sonar_scanner
        if not Path(scanner_path).exists() and shutil.which(scanner_path) is None:
            raise FileNotFoundError(
                f"SonarScanner executable not found: {args.sonar_scanner}. "
                "Set SONAR_PATH or SONAR_SCANNER_PATH."
            )

        wait_for_sonar_system(
            args.sonar_host,
            args.server_timeout_seconds,
            args.poll_interval_seconds,
        )
        config = SonarConfig(
            host=args.sonar_host.rstrip("/"),
            token=args.sonar_token,
            scanner=scanner_path,
            project_key_prefix=args.project_key_prefix,
            scanner_timeout_seconds=args.scanner_timeout_seconds,
            compute_timeout_seconds=args.compute_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

        successful_keys: set[str] = set()
        if not results.empty and not args.analysis_again:
            valid_success = results["status"].eq("success") & pd.to_numeric(
                results["ncloc_py"], errors="coerce"
            ).notna()
            successful_keys = set(results.loc[valid_success, "snapshot_key"].astype(str))

        total = len(selected)
        run_started_monotonic = time.monotonic()
        for position, (_, target) in enumerate(selected.iterrows(), start=1):
            snapshot_key = str(target["snapshot_key"])
            logging.info(
                "Target %d/%d: order=%d %s %s at %s (%d repo-month rows)",
                position,
                total,
                int(target["manifest_order"]),
                target["dataset_source"],
                target["repo_name"],
                str(target["commit_sha"])[:12],
                int(target["repo_month_rows"]),
            )

            if snapshot_key in successful_keys:
                counters.skipped_existing_success += 1
                logging.info("Skipping already successful snapshot: %s", snapshot_key)
            else:
                result = run_sonar_snapshot(
                    target,
                    existing_results=results,
                    config=config,
                    worktree_root=args.worktree_root.expanduser().resolve(),
                    scanner_log_dir=args.scanner_log_dir.expanduser().resolve(),
                    keep_worktrees=args.keep_worktrees,
                )
                results = upsert_result(results, result)
                save_dataframe(
                    results.sort_values("manifest_order", kind="stable"),
                    args.snapshot_results_output,
                )
                counters.processed_this_run += 1
                if result["status"] == "success":
                    counters.successful_this_run += 1
                    successful_keys.add(snapshot_key)
                    logging.info(
                        "Success: %s at %s -> ncloc_py=%s",
                        target["repo_name"],
                        str(target["commit_sha"])[:12],
                        result["ncloc_py"],
                    )
                else:
                    counters.failed_this_run += 1
                    logging.warning(
                        "Unresolved: %s at %s status=%s stage=%s error=%s",
                        target["repo_name"],
                        str(target["commit_sha"])[:12],
                        result["status"],
                        result["error_stage"],
                        result["error_message"],
                    )

                if args.sleep_between_scans_seconds > 0:
                    time.sleep(args.sleep_between_scans_seconds)

            completed_count = counters.processed_this_run + counters.skipped_existing_success
            if (
                args.progress_every > 0
                and (completed_count % args.progress_every == 0 or position == total)
            ):
                logging.info(
                    progress_message(
                        position,
                        total,
                        counters,
                        run_started_monotonic,
                    )
                )

    if results.empty:
        results = pd.DataFrame(columns=RESULT_COLUMNS)
    else:
        results = results.sort_values("manifest_order", kind="stable").reset_index(drop=True)
    save_dataframe(results, args.snapshot_results_output)

    completed = build_completed_manifest(manifest, results)
    save_dataframe(completed, args.completed_manifest_output)

    unresolved = completed[~completed["ncloc_py_available"]].copy()
    save_dataframe(unresolved, args.unresolved_output)

    qc, summary = build_qc_records(
        manifest,
        results,
        completed,
        structural_checks,
        counters,
        dry_run=args.dry_run,
    )
    save_dataframe(qc, args.scan_qc_output)
    save_dataframe(summary, args.summary_output)

    successful_count = int(completed["ncloc_py_available"].sum())
    successful_coverage = int(
        completed.loc[completed["ncloc_py_available"], "repo_month_rows"].sum()
    )
    logging.info(
        "Completed run-x-b01-%s: %d/%d snapshots resolved; %d/%d repo-month rows covered; %d unresolved",
        IMPLEMENTATION_VERSION,
        successful_count,
        len(manifest),
        successful_coverage,
        int(manifest["repo_month_rows"].sum()),
        len(unresolved),
    )

    hard_fail_checks = qc[qc["status"].eq("fail")]
    if not hard_fail_checks.empty:
        logging.error("QC failures remain:\n%s", hard_fail_checks.to_string(index=False))
        return 3
    if args.fail_on_unresolved and not args.dry_run and not unresolved.empty:
        logging.error("Unresolved snapshots remain: %d", len(unresolved))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
