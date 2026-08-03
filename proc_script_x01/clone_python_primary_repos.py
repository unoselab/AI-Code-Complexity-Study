#!/usr/bin/env python3
"""Clone the C01 Python-primary treatment and control repository manifest.

This script is intentionally independent from the legacy clone scripts. It reuses
only their basic Git-clone idea while adding manifest validation, separate
Python-primary clone roots, incremental status persistence, retry handling,
non-interactive Git execution, and structured failure classification.

Inputs
------
- C01 clone manifest with one row per repository.

Outputs
-------
- Final status for every manifest repository.
- One row per Git clone attempt.
- Clone-failure subset with classified reasons.
- QC and summary CSV files.

The script never pulls, resets, cleans, or checks out an existing repository.
A valid existing clone is inspected and skipped. An invalid existing path is not
modified unless an explicit repair option is enabled.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REQUIRED_MANIFEST_COLUMNS = {
    "scope_role",
    "repo_name",
    "expected_clone_path",
    "clone_url",
}
VALID_ROLES = {"treatment", "control"}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bool_arg(value: str | int | bool) -> bool:
    """Parse a permissive command-line Boolean value."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid Boolean value: {value}")


def normalize_repo_name(value: Any) -> str:
    """Normalize an owner/repository identifier for comparisons."""
    return str(value).strip().rstrip("/").lower()


def normalize_remote_repo(url: str) -> str:
    """Extract a normalized owner/repository identifier from a Git remote URL."""
    text = (url or "").strip().rstrip("/")
    text = re.sub(r"\.git$", "", text, flags=re.IGNORECASE)

    patterns = [
        r"github\.com[:/](?P<repo>[^/]+/[^/]+)$",
        r"^git@github\.com:(?P<repo>[^/]+/[^/]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_repo_name(match.group("repo"))

    # Local file URLs are used only by validation fixtures.
    if text.startswith("file://") or text.startswith("/"):
        return text.lower()
    return text.lower()


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture text output without invoking a shell."""
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=env,
    )


def is_git_repository(path: Path) -> bool:
    """Return True when path is a valid non-bare Git work tree."""
    if not path.is_dir():
        return False
    result = run_command(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        timeout_seconds=30,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_head(path: Path) -> str:
    """Return HEAD SHA or an empty string when it cannot be resolved."""
    result = run_command(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        timeout_seconds=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def git_origin(path: Path) -> str:
    """Return origin URL or an empty string when unavailable."""
    result = run_command(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        timeout_seconds=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def disk_usage_bytes(path: Path) -> int | None:
    """Return disk usage from du, or None if it cannot be measured."""
    if not path.exists():
        return None
    result = run_command(["du", "-sk", str(path)], timeout_seconds=300)
    if result.returncode != 0:
        return None
    try:
        kib = int(result.stdout.split()[0])
        return kib * 1024
    except (ValueError, IndexError):
        return None


def classify_clone_failure(stderr: str, stdout: str, timed_out: bool) -> tuple[str, bool]:
    """Classify a Git clone failure and whether retrying may help."""
    text = f"{stderr}\n{stdout}".lower()
    if timed_out:
        return "timeout", True
    if (
        "repository not found" in text
        or ("not found" in text and "repository" in text)
        or "does not appear to be a git repository" in text
    ):
        return "repository_not_found_or_private", False
    if "dmca" in text or "legal" in text or "451" in text:
        return "legal_restriction", False
    if "authentication failed" in text or "could not read username" in text:
        return "authentication_required", False
    if "permission denied" in text or "access denied" in text:
        return "permission_denied", False
    if "too many requests" in text or "rate limit" in text or "http 429" in text:
        return "rate_limited", True
    if "could not resolve host" in text or "name or service not known" in text:
        return "dns_failure", True
    if "connection timed out" in text or "operation timed out" in text:
        return "network_timeout", True
    if "connection reset" in text or "failed to connect" in text or "network is unreachable" in text:
        return "network_failure", True
    if "ssl" in text or "tls" in text or "certificate" in text:
        return "tls_failure", True
    if "no space left on device" in text:
        return "disk_full", False
    if "destination path" in text and "already exists" in text:
        return "destination_exists", False
    if "early eof" in text or "rpc failed" in text or "remote end hung up" in text:
        return "transfer_interrupted", True
    return "git_clone_failed", True


def atomic_write_csv(rows: Iterable[dict[str, Any]], path: Path, columns: list[str]) -> None:
    """Write CSV atomically so interrupted runs do not leave a partial status file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_list = list(rows)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_list)
        temp_name = handle.name
    os.replace(temp_name, path)


@dataclass
class CloneAttempt:
    manifest_order: int
    scope_role: str
    repo_name: str
    attempt_number: int
    started_at_utc: str
    completed_at_utc: str
    duration_seconds: float
    clone_url: str
    temporary_clone_path: str
    return_code: int | None
    timed_out: bool
    failure_reason: str
    retryable: bool
    stdout_excerpt: str
    stderr_excerpt: str


STATUS_COLUMNS = [
    "manifest_order",
    "scope_role",
    "repo_name",
    "repo_name_key",
    "clone_url",
    "expected_clone_path",
    "operation",
    "status",
    "success",
    "attempted_this_run",
    "attempt_count_this_run",
    "previous_status",
    "started_at_utc",
    "completed_at_utc",
    "duration_seconds",
    "clone_exists",
    "is_git_repository",
    "git_head_sha",
    "origin_url",
    "origin_matches_expected",
    "failure_reason",
    "failure_retryable",
    "failure_message",
    "disk_usage_bytes",
    "repair_backup_path",
]

ATTEMPT_COLUMNS = list(CloneAttempt.__dataclass_fields__.keys())


class StatusStore:
    """Thread-safe incremental writer for final status and attempt outputs."""

    def __init__(self, status_path: Path, attempts_path: Path) -> None:
        self.status_path = status_path
        self.attempts_path = attempts_path
        self.lock = threading.Lock()
        self.status_by_order: dict[int, dict[str, Any]] = {}
        self.attempts: list[dict[str, Any]] = []

    def load_previous_status(self) -> dict[str, str]:
        """Load previous status by normalized repository name for resume metadata."""
        if not self.status_path.exists():
            return {}
        try:
            previous = pd.read_csv(self.status_path, dtype=str, keep_default_na=False)
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.warning("Could not read previous status output: %s", exc)
            return {}
        if "repo_name" not in previous.columns or "status" not in previous.columns:
            return {}
        return {
            normalize_repo_name(row.repo_name): str(row.status)
            for row in previous.itertuples(index=False)
        }

    def add_status(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.status_by_order[int(row["manifest_order"])] = row
            ordered = [self.status_by_order[key] for key in sorted(self.status_by_order)]
            atomic_write_csv(ordered, self.status_path, STATUS_COLUMNS)

    def add_attempt(self, attempt: CloneAttempt) -> None:
        with self.lock:
            self.attempts.append(asdict(attempt))
            atomic_write_csv(self.attempts, self.attempts_path, ATTEMPT_COLUMNS)


def inspect_existing(
    manifest_row: dict[str, Any],
    previous_status: str,
    measure_disk: bool,
) -> dict[str, Any] | None:
    """Return a terminal status for an existing path, or None when cloning is needed."""
    path = Path(manifest_row["expected_clone_path"])
    if not path.exists():
        return None

    now = utc_now()
    base = {
        "manifest_order": manifest_row["manifest_order"],
        "scope_role": manifest_row["scope_role"],
        "repo_name": manifest_row["repo_name"],
        "repo_name_key": normalize_repo_name(manifest_row["repo_name"]),
        "clone_url": manifest_row["clone_url"],
        "expected_clone_path": str(path),
        "attempted_this_run": False,
        "attempt_count_this_run": 0,
        "previous_status": previous_status,
        "started_at_utc": now,
        "completed_at_utc": now,
        "duration_seconds": 0.0,
        "clone_exists": True,
        "repair_backup_path": "",
    }

    if not path.is_dir():
        return {
            **base,
            "operation": "inspect_existing",
            "status": "clone_path_not_directory",
            "success": False,
            "is_git_repository": False,
            "git_head_sha": "",
            "origin_url": "",
            "origin_matches_expected": False,
            "failure_reason": "clone_path_not_directory",
            "failure_retryable": False,
            "failure_message": "Expected clone path exists but is not a directory.",
            "disk_usage_bytes": None,
        }

    if not is_git_repository(path):
        return {
            **base,
            "operation": "inspect_existing",
            "status": "invalid_existing_git_repository",
            "success": False,
            "is_git_repository": False,
            "git_head_sha": "",
            "origin_url": git_origin(path),
            "origin_matches_expected": False,
            "failure_reason": "invalid_existing_git_repository",
            "failure_retryable": False,
            "failure_message": "Expected clone path is not a valid Git work tree.",
            "disk_usage_bytes": disk_usage_bytes(path) if measure_disk else None,
        }

    head_sha = git_head(path)
    origin_url = git_origin(path)
    expected_repo = normalize_repo_name(manifest_row["repo_name"])
    origin_repo = normalize_remote_repo(origin_url)
    origin_matches = origin_repo == expected_repo or origin_url == manifest_row["clone_url"]

    if not head_sha:
        return {
            **base,
            "operation": "inspect_existing",
            "status": "git_head_unresolved",
            "success": False,
            "is_git_repository": True,
            "git_head_sha": "",
            "origin_url": origin_url,
            "origin_matches_expected": origin_matches,
            "failure_reason": "git_head_unresolved",
            "failure_retryable": False,
            "failure_message": "Existing Git repository has no resolvable HEAD commit.",
            "disk_usage_bytes": disk_usage_bytes(path) if measure_disk else None,
        }

    if not origin_matches:
        return {
            **base,
            "operation": "inspect_existing",
            "status": "existing_origin_mismatch",
            "success": False,
            "is_git_repository": True,
            "git_head_sha": head_sha,
            "origin_url": origin_url,
            "origin_matches_expected": False,
            "failure_reason": "existing_origin_mismatch",
            "failure_retryable": False,
            "failure_message": "Existing clone origin does not match the manifest repository.",
            "disk_usage_bytes": disk_usage_bytes(path) if measure_disk else None,
        }

    return {
        **base,
        "operation": "skip_existing",
        "status": "available_existing",
        "success": True,
        "is_git_repository": True,
        "git_head_sha": head_sha,
        "origin_url": origin_url,
        "origin_matches_expected": True,
        "failure_reason": "",
        "failure_retryable": False,
        "failure_message": "",
        "disk_usage_bytes": disk_usage_bytes(path) if measure_disk else None,
    }


def backup_invalid_path(path: Path) -> Path:
    """Move an invalid existing path aside without deleting user data."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.invalid-backup-{timestamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.invalid-backup-{timestamp}-{suffix}")
        suffix += 1
    path.rename(candidate)
    return candidate


def clone_one_repository(
    manifest_row: dict[str, Any],
    previous_status: str,
    store: StatusStore,
    *,
    retry_count: int,
    retry_delay_seconds: float,
    timeout_seconds: int,
    repair_invalid_existing: bool,
    repair_origin_mismatch: bool,
    skip_lfs_smudge: bool,
    measure_disk: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Inspect or clone one repository and return its final status row."""
    started_at = utc_now()
    start_monotonic = time.monotonic()
    path = Path(manifest_row["expected_clone_path"])
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = inspect_existing(manifest_row, previous_status, measure_disk)
    repair_backup = ""
    if existing is not None:
        if existing["success"]:
            return existing
        repair_allowed = (
            repair_origin_mismatch
            if existing["failure_reason"] == "existing_origin_mismatch"
            else repair_invalid_existing
        )
        if not repair_allowed:
            return existing
        backup_path = backup_invalid_path(path)
        repair_backup = str(backup_path)
        logging.warning(
            "Moved invalid existing path for %s to %s",
            manifest_row["repo_name"],
            backup_path,
        )

    if dry_run:
        completed_at = utc_now()
        return {
            "manifest_order": manifest_row["manifest_order"],
            "scope_role": manifest_row["scope_role"],
            "repo_name": manifest_row["repo_name"],
            "repo_name_key": normalize_repo_name(manifest_row["repo_name"]),
            "clone_url": manifest_row["clone_url"],
            "expected_clone_path": str(path),
            "operation": "dry_run",
            "status": "clone_planned",
            "success": False,
            "attempted_this_run": False,
            "attempt_count_this_run": 0,
            "previous_status": previous_status,
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
            "duration_seconds": round(time.monotonic() - start_monotonic, 3),
            "clone_exists": path.exists(),
            "is_git_repository": is_git_repository(path) if path.exists() else False,
            "git_head_sha": git_head(path) if is_git_repository(path) else "",
            "origin_url": git_origin(path) if is_git_repository(path) else "",
            "origin_matches_expected": False,
            "failure_reason": "",
            "failure_retryable": False,
            "failure_message": "",
            "disk_usage_bytes": disk_usage_bytes(path) if measure_disk and path.exists() else None,
            "repair_backup_path": repair_backup,
        }

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if skip_lfs_smudge:
        env["GIT_LFS_SKIP_SMUDGE"] = "1"

    final_failure_reason = "git_clone_failed"
    final_retryable = False
    final_message = ""
    attempts_made = 0

    for attempt_number in range(1, retry_count + 2):
        attempts_made = attempt_number
        temp_path = path.with_name(
            f".{path.name}.clone-tmp-{os.getpid()}-{threading.get_ident()}-{attempt_number}"
        )
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)

        attempt_started = utc_now()
        attempt_monotonic = time.monotonic()
        timed_out = False
        return_code: int | None = None
        stdout = ""
        stderr = ""

        try:
            result = run_command(
                ["git", "clone", manifest_row["clone_url"], str(temp_path)],
                timeout_seconds=timeout_seconds,
                env=env,
            )
            return_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

        attempt_duration = time.monotonic() - attempt_monotonic
        failure_reason = ""
        retryable = False

        if not timed_out and return_code == 0 and is_git_repository(temp_path):
            head_sha = git_head(temp_path)
            if head_sha:
                if path.exists():
                    # This should not occur because existing paths were handled above.
                    failure_reason = "destination_exists_after_clone"
                    retryable = False
                    stderr = f"Destination appeared during clone: {path}"
                else:
                    temp_path.rename(path)
                    origin_url = git_origin(path)
                    origin_repo = normalize_remote_repo(origin_url)
                    expected_repo = normalize_repo_name(manifest_row["repo_name"])
                    origin_matches = origin_repo == expected_repo or origin_url == manifest_row["clone_url"]
                    completed_at = utc_now()
                    attempt = CloneAttempt(
                        manifest_order=int(manifest_row["manifest_order"]),
                        scope_role=manifest_row["scope_role"],
                        repo_name=manifest_row["repo_name"],
                        attempt_number=attempt_number,
                        started_at_utc=attempt_started,
                        completed_at_utc=completed_at,
                        duration_seconds=round(attempt_duration, 3),
                        clone_url=manifest_row["clone_url"],
                        temporary_clone_path=str(temp_path),
                        return_code=return_code,
                        timed_out=False,
                        failure_reason="",
                        retryable=False,
                        stdout_excerpt=(stdout or "")[-2000:],
                        stderr_excerpt=(stderr or "")[-2000:],
                    )
                    store.add_attempt(attempt)
                    return {
                        "manifest_order": manifest_row["manifest_order"],
                        "scope_role": manifest_row["scope_role"],
                        "repo_name": manifest_row["repo_name"],
                        "repo_name_key": expected_repo,
                        "clone_url": manifest_row["clone_url"],
                        "expected_clone_path": str(path),
                        "operation": "clone",
                        "status": "cloned_successfully",
                        "success": True,
                        "attempted_this_run": True,
                        "attempt_count_this_run": attempts_made,
                        "previous_status": previous_status,
                        "started_at_utc": started_at,
                        "completed_at_utc": completed_at,
                        "duration_seconds": round(time.monotonic() - start_monotonic, 3),
                        "clone_exists": True,
                        "is_git_repository": True,
                        "git_head_sha": head_sha,
                        "origin_url": origin_url,
                        "origin_matches_expected": origin_matches,
                        "failure_reason": "" if origin_matches else "cloned_origin_mismatch",
                        "failure_retryable": False,
                        "failure_message": "" if origin_matches else "Clone succeeded but origin verification failed.",
                        "disk_usage_bytes": disk_usage_bytes(path) if measure_disk else None,
                        "repair_backup_path": repair_backup,
                    }
            else:
                failure_reason = "git_head_unresolved_after_clone"
                retryable = False
                stderr = f"Clone completed but HEAD could not be resolved.\n{stderr}"
        else:
            failure_reason, retryable = classify_clone_failure(stderr, stdout, timed_out)

        final_failure_reason = failure_reason or "git_clone_failed"
        final_retryable = retryable
        final_message = (stderr or stdout or "Git clone failed without output.").strip()[-4000:]
        attempt_completed = utc_now()
        store.add_attempt(
            CloneAttempt(
                manifest_order=int(manifest_row["manifest_order"]),
                scope_role=manifest_row["scope_role"],
                repo_name=manifest_row["repo_name"],
                attempt_number=attempt_number,
                started_at_utc=attempt_started,
                completed_at_utc=attempt_completed,
                duration_seconds=round(attempt_duration, 3),
                clone_url=manifest_row["clone_url"],
                temporary_clone_path=str(temp_path),
                return_code=return_code,
                timed_out=timed_out,
                failure_reason=final_failure_reason,
                retryable=retryable,
                stdout_excerpt=(stdout or "")[-2000:],
                stderr_excerpt=(stderr or "")[-2000:],
            )
        )
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)

        if not retryable or attempt_number > retry_count:
            break
        sleep_seconds = retry_delay_seconds * attempt_number
        logging.warning(
            "Retrying %s after %s (attempt %d/%d) in %.1f seconds",
            manifest_row["repo_name"],
            final_failure_reason,
            attempt_number,
            retry_count + 1,
            sleep_seconds,
        )
        time.sleep(sleep_seconds)

    completed_at = utc_now()
    return {
        "manifest_order": manifest_row["manifest_order"],
        "scope_role": manifest_row["scope_role"],
        "repo_name": manifest_row["repo_name"],
        "repo_name_key": normalize_repo_name(manifest_row["repo_name"]),
        "clone_url": manifest_row["clone_url"],
        "expected_clone_path": str(path),
        "operation": "clone",
        "status": "clone_failed",
        "success": False,
        "attempted_this_run": True,
        "attempt_count_this_run": attempts_made,
        "previous_status": previous_status,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "duration_seconds": round(time.monotonic() - start_monotonic, 3),
        "clone_exists": path.exists(),
        "is_git_repository": is_git_repository(path) if path.exists() else False,
        "git_head_sha": git_head(path) if is_git_repository(path) else "",
        "origin_url": git_origin(path) if is_git_repository(path) else "",
        "origin_matches_expected": False,
        "failure_reason": final_failure_reason,
        "failure_retryable": final_retryable,
        "failure_message": final_message,
        "disk_usage_bytes": disk_usage_bytes(path) if measure_disk and path.exists() else None,
        "repair_backup_path": repair_backup,
    }


def validate_manifest(
    manifest: pd.DataFrame,
    expected_total: int,
    expected_treatments: int,
    expected_controls: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]], int]:
    """Validate and normalize the C01 clone manifest."""
    missing_columns = sorted(REQUIRED_MANIFEST_COLUMNS - set(manifest.columns))
    if missing_columns:
        raise ValueError(f"Manifest is missing required columns: {missing_columns}")

    normalized = manifest.copy()
    normalized["scope_role"] = normalized["scope_role"].astype(str).str.strip().str.lower()
    normalized["repo_name"] = normalized["repo_name"].astype(str).str.strip()
    normalized["expected_clone_path"] = normalized["expected_clone_path"].astype(str).str.strip()
    normalized["clone_url"] = normalized["clone_url"].astype(str).str.strip()
    normalized["repo_name_key"] = normalized["repo_name"].map(normalize_repo_name)
    normalized.insert(0, "manifest_order", range(1, len(normalized) + 1))

    qc: list[dict[str, Any]] = []

    def add_check(name: str, observed: Any, expected: Any, hard: bool, note: str = "") -> None:
        status = "pass" if observed == expected else ("fail" if hard else "warn")
        qc.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    add_check("manifest_rows", len(normalized), expected_total, True)
    add_check(
        "treatment_manifest_rows",
        int((normalized["scope_role"] == "treatment").sum()),
        expected_treatments,
        True,
    )
    add_check(
        "control_manifest_rows",
        int((normalized["scope_role"] == "control").sum()),
        expected_controls,
        True,
    )
    add_check(
        "invalid_scope_role_rows",
        int((~normalized["scope_role"].isin(VALID_ROLES)).sum()),
        0,
        True,
    )
    add_check(
        "duplicate_repo_name_rows",
        int(normalized.duplicated("repo_name_key", keep=False).sum()),
        0,
        True,
    )
    add_check(
        "duplicate_clone_path_rows",
        int(normalized.duplicated("expected_clone_path", keep=False).sum()),
        0,
        True,
    )
    add_check(
        "blank_repo_name_rows",
        int((normalized["repo_name"].str.len() == 0).sum()),
        0,
        True,
    )
    add_check(
        "blank_clone_url_rows",
        int((normalized["clone_url"].str.len() == 0).sum()),
        0,
        True,
    )
    add_check(
        "blank_clone_path_rows",
        int((normalized["expected_clone_path"].str.len() == 0).sum()),
        0,
        True,
    )

    hard_failures = sum(row["status"] == "fail" for row in qc)
    return normalized, qc, hard_failures


def build_final_qc(
    base_qc: list[dict[str, Any]],
    status_df: pd.DataFrame,
    expected_total: int,
    expected_treatments: int,
    expected_controls: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    """Append post-clone coverage and integrity checks."""
    qc = list(base_qc)

    def add(name: str, observed: Any, expected: Any, status: str, note: str = "") -> None:
        qc.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    add("status_rows", len(status_df), expected_total, "pass" if len(status_df) == expected_total else "fail")
    add(
        "duplicate_status_repo_rows",
        int(status_df.duplicated("repo_name_key", keep=False).sum()),
        0,
        "pass" if not status_df.duplicated("repo_name_key", keep=False).any() else "fail",
    )
    add(
        "treatment_status_rows",
        int((status_df["scope_role"] == "treatment").sum()),
        expected_treatments,
        "pass" if int((status_df["scope_role"] == "treatment").sum()) == expected_treatments else "fail",
    )
    add(
        "control_status_rows",
        int((status_df["scope_role"] == "control").sum()),
        expected_controls,
        "pass" if int((status_df["scope_role"] == "control").sum()) == expected_controls else "fail",
    )

    success_count = int(status_df["success"].map(bool_arg).sum()) if len(status_df) else 0
    failure_count = len(status_df) - success_count
    if dry_run:
        add("successful_clone_targets", success_count, expected_total, "info", "Dry-run mode does not clone missing repositories.")
        add("failed_clone_targets", failure_count, 0, "info", "Dry-run planned rows are not failures.")
    else:
        add("successful_clone_targets", success_count, expected_total, "pass" if success_count == expected_total else "warn")
        add("failed_clone_targets", failure_count, 0, "pass" if failure_count == 0 else "warn")

    successful = status_df[status_df["success"].map(bool_arg)] if len(status_df) else status_df
    head_missing = int((successful["git_head_sha"].fillna("").astype(str).str.len() == 0).sum())
    origin_mismatch = int((~successful["origin_matches_expected"].map(bool_arg)).sum()) if len(successful) else 0
    add("successful_rows_missing_git_head", head_missing, 0, "pass" if head_missing == 0 else "fail")
    add("successful_rows_origin_mismatch", origin_mismatch, 0, "pass" if origin_mismatch == 0 else "fail")
    return qc


def build_summary(
    status_df: pd.DataFrame,
    attempts_df: pd.DataFrame,
    implementation_version: str,
    workers: int,
    retry_count: int,
    timeout_seconds: int,
    skip_lfs_smudge: bool,
    dry_run: bool,
) -> pd.DataFrame:
    """Build a compact long-form execution summary."""
    rows: list[dict[str, Any]] = []

    def add(section: str, metric: str, value: Any, note: str = "") -> None:
        rows.append({"section": section, "metric": metric, "value": value, "note": note})

    add("implementation", "version", implementation_version)
    add("configuration", "workers", workers)
    add("configuration", "retry_count", retry_count)
    add("configuration", "clone_timeout_seconds", timeout_seconds)
    add("configuration", "skip_lfs_smudge", skip_lfs_smudge)
    add("configuration", "dry_run", dry_run)
    add("scope", "manifest_rows", len(status_df))
    add("scope", "treatment_rows", int((status_df["scope_role"] == "treatment").sum()))
    add("scope", "control_rows", int((status_df["scope_role"] == "control").sum()))
    success_mask = status_df["success"].map(bool_arg) if len(status_df) else pd.Series(dtype=bool)
    add("result", "successful_repositories", int(success_mask.sum()))
    add("result", "failed_or_pending_repositories", int((~success_mask).sum()))
    add("result", "cloned_this_run", int((status_df["status"] == "cloned_successfully").sum()))
    add("result", "available_existing", int((status_df["status"] == "available_existing").sum()))
    add("result", "attempt_rows", len(attempts_df))
    add("result", "total_attempts", int(status_df["attempt_count_this_run"].fillna(0).astype(int).sum()))
    add(
        "storage",
        "successful_clone_disk_usage_bytes",
        int(pd.to_numeric(status_df.loc[success_mask, "disk_usage_bytes"], errors="coerce").fillna(0).sum()) if len(status_df) else 0,
    )

    for role in ["treatment", "control"]:
        role_df = status_df[status_df["scope_role"] == role]
        role_success = role_df["success"].map(bool_arg) if len(role_df) else pd.Series(dtype=bool)
        add("result_by_role", f"{role}_successful", int(role_success.sum()))
        add("result_by_role", f"{role}_failed_or_pending", int((~role_success).sum()))

    if len(status_df):
        for status, count in status_df["status"].value_counts(dropna=False).items():
            add("status_counts", str(status), int(count))
        failures = status_df[~success_mask]
        for reason, count in failures["failure_reason"].fillna("").replace("", "none").value_counts().items():
            add("failure_reason_counts", str(reason), int(count))

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clone C01 Python-primary repositories.")
    parser.add_argument("--manifest-file", required=True)
    parser.add_argument("--status-output", required=True)
    parser.add_argument("--attempts-output", required=True)
    parser.add_argument("--failures-output", required=True)
    parser.add_argument("--qc-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--implementation-version", default="v1")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=5.0)
    parser.add_argument("--clone-timeout-seconds", type=int, default=1800)
    parser.add_argument("--repair-invalid-existing", type=bool_arg, default=False)
    parser.add_argument("--repair-origin-mismatch", type=bool_arg, default=False)
    parser.add_argument("--skip-lfs-smudge", type=bool_arg, default=True)
    parser.add_argument("--measure-disk-usage", type=bool_arg, default=True)
    parser.add_argument("--dry-run", type=bool_arg, default=False)
    parser.add_argument("--fail-on-clone-failure", type=bool_arg, default=False)
    parser.add_argument("--strict-expected-counts", type=bool_arg, default=True)
    parser.add_argument("--expected-repositories", type=int, default=248)
    parser.add_argument("--expected-treatment-repositories", type=int, default=121)
    parser.add_argument("--expected-control-repositories", type=int, default=127)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    if args.retry_count < 0:
        raise ValueError("--retry-count cannot be negative")
    if args.clone_timeout_seconds < 1:
        raise ValueError("--clone-timeout-seconds must be positive")

    manifest_path = Path(args.manifest_file)
    if not manifest_path.is_file():
        logging.error("Manifest file not found: %s", manifest_path)
        return 1

    logging.info("Reading C01 clone manifest: %s", manifest_path)
    manifest_raw = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    manifest, base_qc, manifest_failures = validate_manifest(
        manifest_raw,
        args.expected_repositories,
        args.expected_treatment_repositories,
        args.expected_control_repositories,
    )

    if manifest_failures and args.strict_expected_counts:
        qc_path = Path(args.qc_output)
        qc_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(base_qc).to_csv(qc_path, index=False)
        logging.error("Manifest validation produced %d hard failure(s).", manifest_failures)
        return 2

    status_path = Path(args.status_output)
    attempts_path = Path(args.attempts_output)
    failures_path = Path(args.failures_output)
    qc_path = Path(args.qc_output)
    summary_path = Path(args.summary_output)
    for path in [status_path, attempts_path, failures_path, qc_path, summary_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    store = StatusStore(status_path, attempts_path)
    previous_status_map = store.load_previous_status()

    rows = manifest.to_dict(orient="records")
    start_time = time.monotonic()
    completed = 0
    total = len(rows)

    def execute(row: dict[str, Any]) -> dict[str, Any]:
        previous_status = previous_status_map.get(normalize_repo_name(row["repo_name"]), "")
        return clone_one_repository(
            row,
            previous_status,
            store,
            retry_count=args.retry_count,
            retry_delay_seconds=args.retry_delay_seconds,
            timeout_seconds=args.clone_timeout_seconds,
            repair_invalid_existing=args.repair_invalid_existing,
            repair_origin_mismatch=args.repair_origin_mismatch,
            skip_lfs_smudge=args.skip_lfs_smudge,
            measure_disk=args.measure_disk_usage,
            dry_run=args.dry_run,
        )

    logging.info(
        "Starting C02 repository processing: total=%d; workers=%d; retries=%d; timeout=%ds",
        total,
        args.workers,
        args.retry_count,
        args.clone_timeout_seconds,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_row = {executor.submit(execute, row): row for row in rows}
        for future in concurrent.futures.as_completed(future_to_row):
            row = future_to_row[future]
            try:
                status_row = future.result()
            except Exception as exc:  # pragma: no cover - defensive worker handling
                logging.exception("Unhandled worker error for %s", row["repo_name"])
                now = utc_now()
                status_row = {
                    "manifest_order": row["manifest_order"],
                    "scope_role": row["scope_role"],
                    "repo_name": row["repo_name"],
                    "repo_name_key": normalize_repo_name(row["repo_name"]),
                    "clone_url": row["clone_url"],
                    "expected_clone_path": row["expected_clone_path"],
                    "operation": "worker_error",
                    "status": "worker_error",
                    "success": False,
                    "attempted_this_run": False,
                    "attempt_count_this_run": 0,
                    "previous_status": previous_status_map.get(normalize_repo_name(row["repo_name"]), ""),
                    "started_at_utc": now,
                    "completed_at_utc": now,
                    "duration_seconds": 0.0,
                    "clone_exists": Path(row["expected_clone_path"]).exists(),
                    "is_git_repository": False,
                    "git_head_sha": "",
                    "origin_url": "",
                    "origin_matches_expected": False,
                    "failure_reason": "worker_error",
                    "failure_retryable": False,
                    "failure_message": str(exc),
                    "disk_usage_bytes": None,
                    "repair_backup_path": "",
                }
            store.add_status(status_row)
            completed += 1
            elapsed = time.monotonic() - start_time
            rate_per_hour = completed / elapsed * 3600 if elapsed > 0 else 0.0
            remaining = total - completed
            eta_hours = remaining / rate_per_hour if rate_per_hour > 0 else float("inf")
            logging.info(
                "Progress: %d/%d; role=%s; repo=%s; status=%s; success=%s; rate_repos_per_hour=%.2f; eta_hours=%.2f",
                completed,
                total,
                status_row["scope_role"],
                status_row["repo_name"],
                status_row["status"],
                status_row["success"],
                rate_per_hour,
                eta_hours,
            )

    if not attempts_path.exists():
        atomic_write_csv([], attempts_path, ATTEMPT_COLUMNS)

    status_df = pd.read_csv(status_path, keep_default_na=False)
    attempts_df = pd.read_csv(attempts_path, keep_default_na=False)
    success_mask = status_df["success"].map(bool_arg)
    failures_df = status_df[~success_mask].copy()
    failures_df.to_csv(failures_path, index=False)

    final_qc = build_final_qc(
        base_qc,
        status_df,
        args.expected_repositories,
        args.expected_treatment_repositories,
        args.expected_control_repositories,
        args.dry_run,
    )
    pd.DataFrame(final_qc).to_csv(qc_path, index=False)

    summary_df = build_summary(
        status_df,
        attempts_df,
        args.implementation_version,
        args.workers,
        args.retry_count,
        args.clone_timeout_seconds,
        args.skip_lfs_smudge,
        args.dry_run,
    )
    summary_df.to_csv(summary_path, index=False)

    success_count = int(success_mask.sum())
    failure_count = len(status_df) - success_count
    logging.info(
        "Completed run-x-c02-%s: total=%d; success=%d; failed_or_pending=%d; cloned_this_run=%d; existing=%d; attempts=%d",
        args.implementation_version,
        len(status_df),
        success_count,
        failure_count,
        int((status_df["status"] == "cloned_successfully").sum()),
        int((status_df["status"] == "available_existing").sum()),
        len(attempts_df),
    )

    hard_qc_failures = sum(row["status"] == "fail" for row in final_qc)
    if hard_qc_failures:
        logging.error("C02 produced %d hard QC failure(s).", hard_qc_failures)
        return 2
    if failure_count and args.fail_on_clone_failure and not args.dry_run:
        logging.error("C02 has %d repository clone failure(s).", failure_count)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
