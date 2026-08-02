#!/usr/bin/env python3
"""Recover missing whole-repository SonarQube NCLOC values for run-x-a05.

This script targets only repository-commit snapshots whose Python-eligible
repo-month rows have a missing original ``ncloc`` value. It does not call any
existing SonarQube runner. Instead, it implements a self-contained recovery
workflow designed for this experiment:

1. Read the run-x-a05 pooled Python panel.
2. Deduplicate missing NCLOC rows into repository-commit snapshots.
3. Create a detached temporary Git worktree for each historical commit.
4. Run a whole-repository SonarQube scan.
5. Poll the SonarQube Compute Engine task until completion.
6. Fetch the ``ncloc`` measure and save results incrementally.
7. Expand successful snapshot values back to the affected repo-month rows.

The temporary-worktree approach avoids changing the checkout state of the
main treatment and control clones.
"""

from __future__ import annotations

import argparse
import csv
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
from typing import Any, Iterable, Optional
from urllib.parse import urljoin

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
except ImportError:  # Optional; exported environment variables still work.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(override=True)


IMPLEMENTATION_VERSION = "v1"
HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
REQUIRED_PANEL_COLUMNS = {
    "dataset_source",
    "scope_role",
    "repo_name",
    "time",
    "clone_path",
    "latest_commit_effective",
    "python_eligible",
    "ncloc",
}

SONAR_EXCLUSIONS = ",".join(
    [
        "**/.git/**",
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
    host: str
    token: str
    scanner: str
    project_key_prefix: str
    compute_timeout_seconds: int
    poll_interval_seconds: int


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_bool(value: Any) -> bool:
    """Parse common truthy values from CSV or CLI-derived data."""
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def numeric_python_eligible(series: pd.Series) -> pd.Series:
    """Normalize Python eligibility to a Boolean mask."""
    numeric = pd.to_numeric(series, errors="coerce")
    text = series.astype(str).str.strip().str.lower()
    return numeric.eq(1) | text.isin({"true", "yes"})


def sanitize_key(value: str, max_length: int = 120) -> str:
    """Create a SonarQube-safe key fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    cleaned = cleaned.strip("_.:-") or "unknown"
    return cleaned[:max_length]


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    """Build a stable snapshot identifier for CSV joins and resume logic."""
    raw = f"{dataset_source}|{repo_name}|{commit_sha.lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{sanitize_key(dataset_source, 20)}__{sanitize_key(repo_name, 80)}__{commit_sha[:12]}__{digest}"


def make_project_key(prefix: str, repo_name: str, commit_sha: str) -> str:
    """Build a unique SonarQube project key for one historical snapshot."""
    raw = f"{prefix}{sanitize_key(repo_name, 100)}_{commit_sha[:12].lower()}"
    # SonarQube project keys must contain at least one non-digit character.
    if raw.isdigit():
        raw = f"p_{raw}"
    return raw[:190]


def run_command(
    command: list[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with consistent text-mode behavior."""
    logging.debug("Running command: %s", " ".join(command))
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def validate_git_snapshot(clone_path: Path, commit_sha: str) -> tuple[bool, str]:
    """Validate that the clone exists and contains the requested commit."""
    if not clone_path.exists():
        return False, "clone_path_missing"
    if not (clone_path / ".git").exists() and not (clone_path / "HEAD").exists():
        # Worktrees and bare repositories have different layouts; rev-parse is authoritative.
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


def build_manifest(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create the 1-row-per-snapshot manifest and affected repo-month mapping."""
    missing = panel[
        panel["ncloc"].isna() & numeric_python_eligible(panel["python_eligible"])
    ].copy()

    missing["latest_commit_effective"] = (
        missing["latest_commit_effective"].astype(str).str.strip().str.lower()
    )
    missing["clone_path"] = missing["clone_path"].astype(str).str.strip()

    invalid_sha = ~missing["latest_commit_effective"].str.fullmatch(HEX_SHA_RE)
    if invalid_sha.any():
        examples = missing.loc[
            invalid_sha, ["repo_name", "time", "latest_commit_effective"]
        ].head(10)
        raise ValueError(
            "Missing-NCLOC rows contain invalid effective commits:\n"
            + examples.to_string(index=False)
        )

    key_columns = [
        "dataset_source",
        "scope_role",
        "repo_name",
        "clone_path",
        "latest_commit_effective",
    ]

    manifest = (
        missing.groupby(key_columns, dropna=False)
        .agg(
            affected_repo_month_rows=("time", "size"),
            first_affected_month=("time", "min"),
            last_affected_month=("time", "max"),
        )
        .reset_index()
    )
    manifest["snapshot_key"] = manifest.apply(
        lambda row: make_snapshot_key(
            str(row["dataset_source"]),
            str(row["repo_name"]),
            str(row["latest_commit_effective"]),
        ),
        axis=1,
    )
    manifest["commit_sha"] = manifest["latest_commit_effective"]
    manifest["project_version"] = manifest["commit_sha"]
    manifest = manifest.drop(columns=["latest_commit_effective"])

    missing["snapshot_key"] = missing.apply(
        lambda row: make_snapshot_key(
            str(row["dataset_source"]),
            str(row["repo_name"]),
            str(row["latest_commit_effective"]),
        ),
        axis=1,
    )

    mapping_columns = [
        "snapshot_key",
        "dataset_source",
        "scope_role",
        "repo_name",
        "time",
        "clone_path",
        "latest_commit_effective",
        "commit_resolution",
        "months_since_observed_commit",
        "python_eligible",
        "scan_status",
    ]
    mapping_columns = [column for column in mapping_columns if column in missing.columns]
    row_mapping = missing[mapping_columns].copy()

    manifest = manifest.sort_values(
        ["scope_role", "repo_name", "commit_sha"], kind="stable"
    ).reset_index(drop=True)
    manifest.insert(0, "manifest_order", range(1, len(manifest) + 1))

    return manifest, row_mapping


def wait_for_sonar_system(
    host: str, timeout_seconds: int, poll_interval_seconds: int
) -> None:
    """Wait until the SonarQube server reports an operational status."""
    deadline = time.monotonic() + timeout_seconds
    endpoint = urljoin(host.rstrip("/") + "/", "api/system/status")
    last_error = ""

    while time.monotonic() < deadline:
        try:
            response = requests.get(endpoint, timeout=15)
            response.raise_for_status()
            status = str(response.json().get("status", "")).upper()
            if status in {"UP", "DB_MIGRATION_NEEDED", "DB_MIGRATION_RUNNING"}:
                if status != "UP":
                    last_error = f"SonarQube status is {status}"
                else:
                    logging.info("SonarQube is ready at %s", host)
                    return
            else:
                last_error = f"SonarQube status is {status or 'unknown'}"
        except requests.RequestException as exc:
            last_error = str(exc)
        logging.info("Waiting for SonarQube: %s", last_error)
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"SonarQube did not become ready within {timeout_seconds} seconds: {last_error}"
    )


def create_worktree(clone_path: Path, worktree_path: Path, commit_sha: str) -> None:
    """Create a detached worktree for a historical commit."""
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        try:
            run_command(
                ["git", "-C", str(clone_path), "worktree", "remove", "--force", str(worktree_path)],
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
    """Remove a temporary Git worktree without touching the main clone checkout."""
    try:
        run_command(
            ["git", "-C", str(clone_path), "worktree", "remove", "--force", str(worktree_path)],
            check=False,
        )
        run_command(
            ["git", "-C", str(clone_path), "worktree", "prune"],
            check=False,
        )
    finally:
        shutil.rmtree(worktree_path, ignore_errors=True)


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


def poll_compute_task(
    ce_task_url: str,
    config: SonarConfig,
) -> dict[str, Any]:
    """Poll one SonarQube Compute Engine task until terminal status."""
    deadline = time.monotonic() + config.compute_timeout_seconds
    auth = (config.token, "")
    last_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        response = requests.get(ce_task_url, auth=auth, timeout=30)
        response.raise_for_status()
        payload = response.json()
        task = payload.get("task", {})
        last_payload = task
        status = str(task.get("status", "")).upper()

        if status == "SUCCESS":
            return task
        if status in {"FAILED", "CANCELED"}:
            error_message = task.get("errorMessage") or ""
            raise RuntimeError(f"SonarQube Compute Engine status={status}: {error_message}")

        logging.info("Compute Engine status=%s", status or "UNKNOWN")
        time.sleep(config.poll_interval_seconds)

    raise TimeoutError(
        "Timed out waiting for SonarQube Compute Engine task. "
        f"Last payload: {last_payload}"
    )


def fetch_ncloc(project_key: str, config: SonarConfig) -> float:
    """Fetch the current NCLOC measure for a snapshot-specific project."""
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
            return float(measure["value"])
    raise RuntimeError(f"No ncloc measure returned for SonarQube project {project_key}")


def write_scanner_log(path: Path, command: list[str], process: subprocess.CompletedProcess[str]) -> None:
    """Persist the scanner command and output for one target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("Command:\n")
        # Token values are masked before this function is called.
        handle.write(" ".join(command) + "\n\n")
        handle.write("STDOUT:\n")
        handle.write(process.stdout or "")
        handle.write("\n\nSTDERR:\n")
        handle.write(process.stderr or "")


def run_sonar_snapshot(
    manifest_row: pd.Series,
    *,
    config: SonarConfig,
    worktree_root: Path,
    scanner_log_dir: Path,
    keep_worktrees: bool,
) -> dict[str, Any]:
    """Scan one historical repository snapshot and return an incremental result row."""
    snapshot_key = str(manifest_row["snapshot_key"])
    clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
    commit_sha = str(manifest_row["commit_sha"]).lower()
    repo_name = str(manifest_row["repo_name"])
    project_key = make_project_key(config.project_key_prefix, repo_name, commit_sha)
    project_version = str(manifest_row["project_version"])
    worktree_path = worktree_root / snapshot_key
    scanner_log_path = scanner_log_dir / f"{snapshot_key}.log"

    result: dict[str, Any] = manifest_row.to_dict()
    result.update(
        {
            "implementation_version": IMPLEMENTATION_VERSION,
            "project_key": project_key,
            "project_version": project_version,
            "scanner_log_path": str(scanner_log_path),
            "scan_started_at": utc_now(),
            "scan_completed_at": "",
            "status": "pending",
            "ncloc_recovered": pd.NA,
            "ce_task_id": "",
            "analysis_id": "",
            "error_message": "",
        }
    )

    ready, precheck_status = validate_git_snapshot(clone_path, commit_sha)
    result["git_precheck_status"] = precheck_status
    if not ready:
        result["status"] = precheck_status
        result["scan_completed_at"] = utc_now()
        return result

    try:
        create_worktree(clone_path, worktree_path, commit_sha)

        scanner_command = [
            config.scanner,
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.projectName={project_key}",
            f"-Dsonar.projectVersion={project_version}",
            "-Dsonar.sources=.",
            "-Dsonar.sourceEncoding=UTF-8",
            f"-Dsonar.exclusions={SONAR_EXCLUSIONS}",
            "-Dsonar.java.binaries=.",
            f"-Dsonar.host.url={config.host}",
            f"-Dsonar.token={config.token}",
            "-Dsonar.scm.disabled=true",
        ]

        process = subprocess.run(
            scanner_command,
            cwd=str(worktree_path),
            text=True,
            capture_output=True,
            check=False,
        )
        masked_command = [
            "-Dsonar.token=***" if part.startswith("-Dsonar.token=") else part
            for part in scanner_command
        ]
        write_scanner_log(scanner_log_path, masked_command, process)

        if process.returncode != 0:
            raise RuntimeError(
                f"sonar-scanner exited with code {process.returncode}; "
                f"see {scanner_log_path}"
            )

        report = parse_report_task(worktree_path / ".scannerwork" / "report-task.txt")
        ce_task_url = report.get("ceTaskUrl", "")
        if not ce_task_url:
            raise RuntimeError(
                f"SonarScanner report-task.txt has no ceTaskUrl; see {scanner_log_path}"
            )

        task = poll_compute_task(ce_task_url, config)
        result["ce_task_id"] = task.get("id", "")
        result["analysis_id"] = task.get("analysisId", "")
        result["ncloc_recovered"] = fetch_ncloc(project_key, config)
        result["status"] = "success"

    except Exception as exc:  # Keep partial results and continue other snapshots.
        logging.exception("Snapshot recovery failed for %s at %s", repo_name, commit_sha)
        result["status"] = "scan_failed"
        result["error_message"] = str(exc)
    finally:
        if not keep_worktrees:
            remove_worktree(clone_path, worktree_path)
        result["scan_completed_at"] = utc_now()

    return result


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp_path, index=False)
    temp_path.replace(path)


def load_existing_results(path: Path) -> pd.DataFrame:
    """Read prior incremental results for resume behavior."""
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    existing = pd.read_csv(path)
    if "snapshot_key" not in existing.columns:
        raise ValueError(f"Existing result file has no snapshot_key: {path}")
    return existing


def upsert_result(existing: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
    """Insert or replace one snapshot result by snapshot_key."""
    row = pd.DataFrame([result])
    if existing.empty:
        return row
    existing = existing[existing["snapshot_key"] != result["snapshot_key"]].copy()
    return pd.concat([existing, row], ignore_index=True, sort=False)


def build_repo_month_patch(
    row_mapping: pd.DataFrame, results: pd.DataFrame
) -> pd.DataFrame:
    """Expand snapshot-level recovery results to the affected repo-month rows."""
    result_columns = [
        "snapshot_key",
        "project_key",
        "project_version",
        "status",
        "ncloc_recovered",
        "git_precheck_status",
        "scanner_log_path",
        "error_message",
    ]
    available = [column for column in result_columns if column in results.columns]
    patch = row_mapping.merge(results[available], on="snapshot_key", how="left")
    patch["ncloc_patch_available"] = patch["status"].eq("success") & pd.to_numeric(
        patch["ncloc_recovered"], errors="coerce"
    ).notna()
    patch["ncloc_patch_source"] = "run-x-a05b-sonarqube-whole-repository"
    return patch.sort_values(["scope_role", "repo_name", "time"], kind="stable")


def build_summary(
    panel: pd.DataFrame,
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    patch: pd.DataFrame,
    *,
    dry_run: bool,
) -> pd.DataFrame:
    """Build a long-form QC summary."""
    missing_mask = panel["ncloc"].isna() & numeric_python_eligible(panel["python_eligible"])
    records: list[dict[str, Any]] = []

    def add(section: str, metric: str, value: Any, note: str = "") -> None:
        records.append({"section": section, "metric": metric, "value": value, "note": note})

    add("implementation", "version", IMPLEMENTATION_VERSION)
    add("definition", "target", "python_eligible_repo_month_with_missing_ncloc")
    add("definition", "scan_scope", "whole_repository", "Model A NCLOC, not Python-only NCLOC.")
    add("definition", "checkout_method", "detached_temporary_git_worktree")
    add("definition", "dry_run", int(dry_run))
    add("input", "pooled_panel_rows", len(panel))
    add("target", "missing_ncloc_repo_month_rows", int(missing_mask.sum()))
    add("target", "unique_repository_commit_snapshots", len(manifest))

    for role, group in manifest.groupby("scope_role", dropna=False):
        add("target_by_role", f"{role}_snapshots", len(group))
        add(
            "target_by_role",
            f"{role}_affected_repo_month_rows",
            int(group["affected_repo_month_rows"].sum()),
        )

    if not results.empty and "status" in results.columns:
        for status, count in results["status"].fillna("missing").value_counts().items():
            add("result_status", str(status), int(count))
        success = results[results["status"].eq("success")].copy()
        add("result", "successful_snapshots", len(success))
        if not success.empty:
            ncloc = pd.to_numeric(success["ncloc_recovered"], errors="coerce").dropna()
            add("result", "ncloc_min", ncloc.min() if not ncloc.empty else "")
            add("result", "ncloc_median", ncloc.median() if not ncloc.empty else "")
            add("result", "ncloc_max", ncloc.max() if not ncloc.empty else "")
    else:
        add("result", "successful_snapshots", 0)

    add(
        "patch",
        "repo_month_rows_with_recovered_ncloc",
        int(patch.get("ncloc_patch_available", pd.Series(dtype=bool)).fillna(False).sum()),
    )
    add(
        "patch",
        "repo_month_rows_without_recovered_ncloc",
        int((~patch.get("ncloc_patch_available", pd.Series(dtype=bool)).fillna(False)).sum()),
    )

    return pd.DataFrame(records)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Recover missing whole-repository NCLOC for run-x-a05 using targeted SonarQube scans."
    )
    parser.add_argument("--pooled-panel-file", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-output", type=Path, required=True)
    parser.add_argument("--snapshot-results-output", type=Path, required=True)
    parser.add_argument("--repo-month-patch-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--scanner-log-dir", type=Path, required=True)
    parser.add_argument(
        "--sonar-host",
        default=os.getenv("SONAR_HOST", "http://localhost:9000"),
    )
    parser.add_argument(
        "--sonar-token",
        default=os.getenv("SONAR_TOKEN", ""),
    )
    parser.add_argument(
        "--sonar-scanner",
        default=(
            os.getenv("SONAR_PATH")
            or os.getenv("SONAR_SCANNER_PATH")
            or shutil.which("sonar-scanner")
            or "sonar-scanner"
        ),
    )
    parser.add_argument("--project-key-prefix", default="a05b_ncloc_")
    parser.add_argument("--server-timeout-seconds", type=int, default=300)
    parser.add_argument("--compute-timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N snapshots; 0 means all.")
    parser.add_argument("--repo-name", default="", help="Optional exact repository-name filter.")
    parser.add_argument("--analysis-again", action="store_true")
    parser.add_argument("--keep-worktrees", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Write the manifest and dry-run results without scanning.")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    """Run the targeted NCLOC recovery workflow."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    panel_path = args.pooled_panel_file.expanduser().resolve()
    if not panel_path.exists():
        raise FileNotFoundError(f"Pooled panel not found: {panel_path}")

    panel = pd.read_csv(panel_path)
    missing_columns = REQUIRED_PANEL_COLUMNS - set(panel.columns)
    if missing_columns:
        raise ValueError(f"Pooled panel is missing required columns: {sorted(missing_columns)}")

    manifest, row_mapping = build_manifest(panel)
    manifest["project_key"] = manifest.apply(
        lambda row: make_project_key(
            args.project_key_prefix,
            str(row["repo_name"]),
            str(row["commit_sha"]),
        ),
        axis=1,
    )
    save_dataframe(manifest, args.snapshot_manifest_output)

    selected = manifest.copy()
    if args.repo_name:
        selected = selected[selected["repo_name"].eq(args.repo_name)].copy()
    if args.limit > 0:
        selected = selected.head(args.limit).copy()

    existing = load_existing_results(args.snapshot_results_output)
    results = existing.copy()

    if args.dry_run:
        for _, target in selected.iterrows():
            result = target.to_dict()
            result.update(
                {
                    "implementation_version": IMPLEMENTATION_VERSION,
                    "project_version": target["commit_sha"],
                    "scanner_log_path": "",
                    "scan_started_at": utc_now(),
                    "scan_completed_at": utc_now(),
                    "git_precheck_status": "not_checked_dry_run",
                    "status": "dry_run",
                    "ncloc_recovered": pd.NA,
                    "ce_task_id": "",
                    "analysis_id": "",
                    "error_message": "",
                }
            )
            results = upsert_result(results, result)
            save_dataframe(results.sort_values("manifest_order"), args.snapshot_results_output)
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
            compute_timeout_seconds=args.compute_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

        successful_keys = set()
        if not results.empty and not args.analysis_again:
            successful_keys = set(results.loc[results["status"].eq("success"), "snapshot_key"])

        total = len(selected)
        for position, (_, target) in enumerate(selected.iterrows(), start=1):
            snapshot_key = str(target["snapshot_key"])
            logging.info(
                "Target %d/%d: %s at %s (%d affected repo-month rows)",
                position,
                total,
                target["repo_name"],
                str(target["commit_sha"])[:12],
                int(target["affected_repo_month_rows"]),
            )
            if snapshot_key in successful_keys:
                logging.info("Skipping already successful snapshot: %s", snapshot_key)
                continue

            result = run_sonar_snapshot(
                target,
                config=config,
                worktree_root=args.worktree_root.expanduser().resolve(),
                scanner_log_dir=args.scanner_log_dir.expanduser().resolve(),
                keep_worktrees=args.keep_worktrees,
            )
            results = upsert_result(results, result)
            save_dataframe(results.sort_values("manifest_order"), args.snapshot_results_output)

    # Ensure all selected targets have a result row, even if a filtered resume file was supplied.
    if results.empty:
        results = pd.DataFrame(columns=["snapshot_key", "status", "ncloc_recovered"])
    save_dataframe(results.sort_values("manifest_order"), args.snapshot_results_output)

    patch = build_repo_month_patch(row_mapping, results)
    save_dataframe(patch, args.repo_month_patch_output)

    unresolved = results[~results["status"].eq("success")].copy()
    save_dataframe(unresolved.sort_values("manifest_order"), args.unresolved_output)

    summary = build_summary(panel, manifest, results, patch, dry_run=args.dry_run)
    save_dataframe(summary, args.summary_output)

    successful = int(results["status"].eq("success").sum()) if "status" in results else 0
    logging.info(
        "Completed run-x-a05b: %d target snapshots, %d successful, %d affected repo-month rows patched",
        len(manifest),
        successful,
        int(patch["ncloc_patch_available"].fillna(False).sum()),
    )

    if args.fail_on_unresolved and not args.dry_run and not unresolved.empty:
        logging.error("Unresolved snapshots remain: %d", len(unresolved))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
