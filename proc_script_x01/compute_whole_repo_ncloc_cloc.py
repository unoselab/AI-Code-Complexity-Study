#!/usr/bin/env python3
"""Compute whole-repository cloc NCLOC for historical Git snapshots.

This program is the self-contained implementation for run-x-c04-v3. It reads
C03's unique repository-commit snapshot manifest, materializes each historical
snapshot without changing the clone's working tree, runs cloc across all
tracked regular files, preserves one normalized row per cloc-recognized
language/file type, and sums the language-level ``code`` counts into repository-level
``ncloc_local_cloc_whole_repo``.

The metric is intentionally defined as all cloc-recognized language/file types in
the tracked repository snapshot. It is not derived from ``repos.csv`` language
metadata, and it is not restricted to Python files.
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
import tarfile
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional

import pandas as pd


IMPLEMENTATION_VERSION = "v3"
COUNT_BACKEND = "cloc_whole_repository_all_recognized_languages"
METRIC_DEFINITION = (
    "sum of cloc language-level code lines across all cloc-recognized "
    "languages in tracked regular files at the historical Git commit"
)
SCAN_SCOPE = "historical_git_snapshot_tracked_regular_files"
SUCCESS_STATUSES = {"success", "success_no_recognized_languages", "success_empty_git_tree"}
VALID_SCOPE_ROLES = {"treatment", "control"}
REQUIRED_SNAPSHOT_COLUMNS = {
    "repo_snapshot_key",
    "scope_role",
    "repo_name",
    "clone_path",
    "resolved_commit",
    "first_repo_month",
    "last_repo_month",
    "repo_month_count",
    "resolution_methods",
}
REQUIRED_HISTORY_COLUMNS = {
    "repo_snapshot_key",
    "scope_role",
    "repo_name",
    "time",
    "clone_path",
    "resolved_commit",
    "snapshot_available",
}
HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"

SNAPSHOT_RESULT_COLUMNS = [
    "manifest_order",
    "repo_snapshot_key",
    "scope_role",
    "repo_name",
    "clone_path",
    "resolved_commit",
    "first_repo_month",
    "last_repo_month",
    "repo_month_count",
    "resolution_methods",
    "implementation_version",
    "count_backend",
    "metric_definition",
    "scan_scope",
    "scan_attempt",
    "scan_started_at",
    "scan_completed_at",
    "runtime_seconds",
    "git_precheck_status",
    "git_archive_status",
    "git_tree_entry_count",
    "git_tree_regular_file_count",
    "git_tree_symlink_count",
    "git_tree_gitlink_count",
    "git_tree_other_entry_count",
    "archive_regular_file_count",
    "archive_symlink_count",
    "archive_other_entry_count",
    "materialized_file_count",
    "materialized_bytes",
    "git_lfs_pointer_file_count",
    "cloc_version",
    "cloc_runtime_seconds",
    "cloc_return_code",
    "cloc_stdout_bytes",
    "cloc_stderr_bytes",
    "cloc_language_count",
    "cloc_file_count",
    "cloc_blank_lines",
    "cloc_comment_lines",
    "ncloc_local_cloc_whole_repo",
    "cloc_sum_row_present",
    "cloc_sum_reported_files",
    "cloc_sum_reported_blank",
    "cloc_sum_reported_comment",
    "cloc_sum_reported_code",
    "language_sum_matches_sum_row",
    "zero_ncloc_reason",
    "raw_cloc_csv_path",
    "status",
    "error_stage",
    "error_message",
]

LANGUAGE_RESULT_COLUMNS = [
    "repo_snapshot_key",
    "scope_role",
    "repo_name",
    "resolved_commit",
    "language",
    "files",
    "blank",
    "comment",
    "code",
    "implementation_version",
    "count_backend",
    "cloc_version",
]


@dataclass
class ArchiveMetrics:
    """Materialization diagnostics for one Git archive."""

    regular_file_count: int = 0
    symlink_count: int = 0
    other_entry_count: int = 0
    materialized_bytes: int = 0
    lfs_pointer_file_count: int = 0


@dataclass
class GitTreeMetrics:
    """Tracked entry counts read directly from one historical Git tree."""

    entry_count: int = 0
    regular_file_count: int = 0
    symlink_count: int = 0
    gitlink_count: int = 0
    other_entry_count: int = 0


@dataclass
class ParsedCloc:
    """Normalized language and aggregate values parsed from cloc CSV."""

    language_rows: list[dict[str, Any]]
    sum_row_present: bool
    sum_files: Optional[int]
    sum_blank: Optional[int]
    sum_comment: Optional[int]
    sum_code: Optional[int]

    @property
    def language_count(self) -> int:
        return len(self.language_rows)

    @property
    def files(self) -> int:
        return sum(int(row["files"]) for row in self.language_rows)

    @property
    def blank(self) -> int:
        return sum(int(row["blank"]) for row in self.language_rows)

    @property
    def comment(self) -> int:
        return sum(int(row["comment"]) for row in self.language_rows)

    @property
    def code(self) -> int:
        return sum(int(row["code"]) for row in self.language_rows)

    @property
    def matches_sum_row(self) -> bool:
        if not self.sum_row_present:
            return True
        return (
            self.files == int(self.sum_files or 0)
            and self.blank == int(self.sum_blank or 0)
            and self.comment == int(self.sum_comment or 0)
            and self.code == int(self.sum_code or 0)
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Run whole-repository cloc over C03 historical snapshots and map "
            "snapshot metrics back to repository-month rows."
        )
    )
    parser.add_argument("--snapshot-manifest-file", required=True)
    parser.add_argument("--history-manifest-file", required=True)
    parser.add_argument("--snapshot-results-output", required=True)
    parser.add_argument("--language-results-output", required=True)
    parser.add_argument("--repo-month-results-output", required=True)
    parser.add_argument("--completed-manifest-output", required=True)
    parser.add_argument("--failures-output", required=True)
    parser.add_argument("--qc-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--temp-root", required=True)
    parser.add_argument("--raw-cloc-csv-root", required=True)
    parser.add_argument("--cloc-bin", default="cloc")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--git-timeout-seconds", type=int, default=600)
    parser.add_argument("--cloc-timeout-seconds", type=int, default=900)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--scope-role", choices=["", "treatment", "control"], default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--exclude-dirs", default="")
    parser.add_argument("--analysis-again", type=int, choices=[0, 1], default=0)
    parser.add_argument("--dry-run", type=int, choices=[0, 1], default=0)
    parser.add_argument("--keep-temp", type=int, choices=[0, 1], default=0)
    parser.add_argument("--keep-raw-cloc-csv", type=int, choices=[0, 1], default=0)
    parser.add_argument("--fail-on-unresolved", type=int, choices=[0, 1], default=0)
    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--require-complete-output", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-unique-snapshots", type=int, default=1828)
    parser.add_argument("--expected-treatment-snapshots", type=int, default=1004)
    parser.add_argument("--expected-control-snapshots", type=int, default=824)
    parser.add_argument("--expected-repo-month-rows", type=int, default=2411)
    parser.add_argument("--expected-treatment-repo-month-rows", type=int, default=1174)
    parser.add_argument("--expected-control-repo-month-rows", type=int, default=1237)
    parser.add_argument("--expected-repositories", type=int, default=242)
    parser.add_argument("--expected-treatment-repositories", type=int, default=116)
    parser.add_argument("--expected-control-repositories", type=int, default=126)
    parser.add_argument("--expected-zero-ncloc-snapshots", type=int, default=5)
    parser.add_argument("--expected-empty-git-tree-snapshots", type=int, default=1)
    parser.add_argument("--expected-no-recognized-language-snapshots", type=int, default=4)
    parser.add_argument("--expected-preserved-v2-successes", type=int, default=1823)
    parser.add_argument("--expected-v3-successes", type=int, default=5)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    for name in (
        "workers",
        "git_timeout_seconds",
        "cloc_timeout_seconds",
        "save_every",
        "progress_every",
        "start_order",
    ):
        if int(getattr(args, name)) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be at least 1")
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    for name in (
        "expected_zero_ncloc_snapshots",
        "expected_empty_git_tree_snapshots",
        "expected_no_recognized_language_snapshots",
        "expected_preserved_v2_successes",
        "expected_v3_successes",
    ):
        if int(getattr(args, name)) < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative")
    return args


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_key(value: str, maximum: int = 80) -> str:
    """Return a filesystem-safe identifier."""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not normalized:
        normalized = "snapshot"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:maximum]}__{digest}"


def atomic_write_csv(frame: pd.DataFrame, path: Path, columns: Optional[list[str]] = None) -> None:
    """Write a CSV atomically so interrupted runs keep the previous valid file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if columns is not None:
        for column in columns:
            if column not in output.columns:
                output[column] = pd.NA
        output = output[columns]
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    output.to_csv(temporary, index=False)
    os.replace(temporary, path)


def read_optional_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    """Read a prior output, or return an empty frame with the expected schema."""
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, low_memory=False)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[columns]


def normalize_boolean(series: pd.Series) -> pd.Series:
    """Normalize common CSV boolean encodings."""
    return series.astype(str).str.strip().str.lower().map(
        {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
    )


def load_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and structurally validate the C03 manifests."""
    snapshot_path = Path(args.snapshot_manifest_file)
    history_path = Path(args.history_manifest_file)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot manifest not found: {snapshot_path}")
    if not history_path.exists():
        raise FileNotFoundError(f"History manifest not found: {history_path}")

    snapshots = pd.read_csv(snapshot_path, low_memory=False)
    history = pd.read_csv(history_path, low_memory=False)
    missing_snapshot = REQUIRED_SNAPSHOT_COLUMNS - set(snapshots.columns)
    missing_history = REQUIRED_HISTORY_COLUMNS - set(history.columns)
    if missing_snapshot:
        raise ValueError(f"Snapshot manifest missing columns: {sorted(missing_snapshot)}")
    if missing_history:
        raise ValueError(f"History manifest missing columns: {sorted(missing_history)}")

    for frame_name, frame in (("snapshot", snapshots), ("history", history)):
        frame["scope_role"] = frame["scope_role"].astype(str).str.strip().str.lower()
        invalid_roles = sorted(set(frame["scope_role"]) - VALID_SCOPE_ROLES)
        if invalid_roles:
            raise ValueError(f"{frame_name} manifest has invalid roles: {invalid_roles}")
        frame["repo_snapshot_key"] = frame["repo_snapshot_key"].astype(str).str.strip()
        frame["repo_name"] = frame["repo_name"].astype(str).str.strip()
        frame["resolved_commit"] = frame["resolved_commit"].astype(str).str.strip().str.lower()
        invalid_sha = ~frame["resolved_commit"].str.match(HEX_SHA_RE)
        if invalid_sha.any():
            examples = frame.loc[invalid_sha, ["repo_name", "resolved_commit"]].head(10)
            raise ValueError("Invalid resolved commit SHA values:\n" + examples.to_string(index=False))

    if snapshots["repo_snapshot_key"].duplicated().any():
        raise ValueError("Snapshot manifest contains duplicate repo_snapshot_key values")
    if history.duplicated(["repo_name", "time"], keep=False).any():
        raise ValueError("History manifest contains duplicate repository-month rows")
    if not set(history["repo_snapshot_key"]).issubset(set(snapshots["repo_snapshot_key"])):
        missing = sorted(set(history["repo_snapshot_key"]) - set(snapshots["repo_snapshot_key"]))[:10]
        raise ValueError(f"History rows reference snapshot keys absent from unique manifest: {missing}")

    if "snapshot_available" in history.columns:
        available = normalize_boolean(history["snapshot_available"])
        if available.isna().any() or not available.all():
            raise ValueError("C04 history manifest must contain only snapshot_available=True rows")

    snapshots = snapshots.reset_index(drop=True)
    snapshots.insert(0, "manifest_order", range(1, len(snapshots) + 1))
    snapshots["repo_month_count"] = pd.to_numeric(
        snapshots["repo_month_count"], errors="raise"
    ).astype(int)
    return snapshots, history


def build_input_qc(snapshots: pd.DataFrame, history: pd.DataFrame, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build expected-count checks for the complete C03 inputs."""
    snapshot_roles = snapshots["scope_role"].value_counts().to_dict()
    history_roles = history["scope_role"].value_counts().to_dict()
    repository_roles = snapshots.groupby("scope_role")["repo_name"].nunique().to_dict()
    checks = [
        ("input_unique_snapshots", len(snapshots), args.expected_unique_snapshots),
        ("input_treatment_snapshots", int(snapshot_roles.get("treatment", 0)), args.expected_treatment_snapshots),
        ("input_control_snapshots", int(snapshot_roles.get("control", 0)), args.expected_control_snapshots),
        ("input_repo_month_rows", len(history), args.expected_repo_month_rows),
        ("input_treatment_repo_month_rows", int(history_roles.get("treatment", 0)), args.expected_treatment_repo_month_rows),
        ("input_control_repo_month_rows", int(history_roles.get("control", 0)), args.expected_control_repo_month_rows),
        ("input_repositories", int(snapshots["repo_name"].nunique()), args.expected_repositories),
        ("input_treatment_repositories", int(repository_roles.get("treatment", 0)), args.expected_treatment_repositories),
        ("input_control_repositories", int(repository_roles.get("control", 0)), args.expected_control_repositories),
        ("snapshot_repo_month_weight", int(snapshots["repo_month_count"].sum()), len(history)),
    ]
    records: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for name, observed, expected in checks:
        passed = int(observed) == int(expected)
        records.append(
            {
                "check_name": name,
                "status": "pass" if passed else "fail",
                "severity": "hard",
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


def run_command(command: list[str], timeout: int, *, stdout_path: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
    """Run a text command with captured diagnostics."""
    if stdout_path is None:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8", newline="") as handle:
        return subprocess.run(
            command,
            stdout=handle,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )


def validate_git_snapshot(clone_path: Path, commit_sha: str, timeout: int) -> tuple[bool, str]:
    """Validate the clone and requested historical commit."""
    if not clone_path.exists():
        return False, "clone_path_missing"
    check_repo = run_command(["git", "-C", str(clone_path), "rev-parse", "--git-dir"], timeout)
    if check_repo.returncode != 0:
        return False, "not_git_repository"
    check_commit = run_command(
        ["git", "-C", str(clone_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        timeout,
    )
    if check_commit.returncode != 0:
        return False, "commit_not_found"
    return True, "ready"


def inspect_git_tree(clone_path: Path, commit_sha: str, timeout: int) -> GitTreeMetrics:
    """Count tracked entries without decoding repository file names."""
    process = subprocess.run(
        ["git", "-C", str(clone_path), "ls-tree", "-r", "-z", "--full-tree", commit_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "git ls-tree failed")

    metrics = GitTreeMetrics()
    for raw_entry in process.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, separator, _path = raw_entry.partition(b"\t")
        if not separator:
            raise ValueError("Unexpected git ls-tree entry without a path separator")
        fields = metadata.split()
        if len(fields) < 3:
            raise ValueError("Unexpected git ls-tree metadata format")
        mode = fields[0].decode("ascii", errors="replace")
        object_type = fields[1].decode("ascii", errors="replace")
        metrics.entry_count += 1
        if object_type == "blob" and mode in {"100644", "100755"}:
            metrics.regular_file_count += 1
        elif object_type == "blob" and mode == "120000":
            metrics.symlink_count += 1
        elif object_type == "commit" and mode == "160000":
            metrics.gitlink_count += 1
        else:
            metrics.other_entry_count += 1
    return metrics


def zero_parsed_cloc(*, sum_row_present: bool = False) -> ParsedCloc:
    """Return a normalized zero-language cloc result."""
    return ParsedCloc(
        language_rows=[],
        sum_row_present=sum_row_present,
        sum_files=0,
        sum_blank=0,
        sum_comment=0,
        sum_code=0,
    )


def safe_archive_destination(root: Path, member_name: str) -> Path:
    """Return a traversal-safe destination for a Git archive member."""
    path = PurePosixPath(member_name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe Git archive path: {member_name!r}")
    destination = root.joinpath(*path.parts)
    root_resolved = root.resolve()
    destination_resolved = destination.resolve()
    if root_resolved != destination_resolved and root_resolved not in destination_resolved.parents:
        raise ValueError(f"Git archive path escaped temporary root: {member_name!r}")
    return destination


def materialize_archive(archive_path: Path, tree_root: Path) -> ArchiveMetrics:
    """Extract only regular files from a Git archive and collect diagnostics."""
    metrics = ArchiveMetrics()
    tree_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="r:") as archive:
        for member in archive:
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                metrics.symlink_count += 1
                continue
            if not member.isfile():
                metrics.other_entry_count += 1
                continue
            destination = safe_archive_destination(tree_root, member.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"Unable to read Git archive member: {member.name}")
            prefix = bytearray()
            written = 0
            with destination.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    if len(prefix) < 256:
                        prefix.extend(chunk[: 256 - len(prefix)])
                    output.write(chunk)
                    written += len(chunk)
            if member.mode & 0o111:
                destination.chmod(0o755)
            metrics.regular_file_count += 1
            metrics.materialized_bytes += written
            if bytes(prefix).startswith(LFS_POINTER_PREFIX):
                metrics.lfs_pointer_file_count += 1
    return metrics


def parse_nonnegative_int(value: str, field: str) -> int:
    """Parse a cloc count field."""
    try:
        parsed = int(float((value or "0").strip()))
    except ValueError as exc:
        raise ValueError(f"Invalid cloc {field} value: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"Negative cloc {field} value: {parsed}")
    return parsed


def parse_cloc_csv(path: Path) -> ParsedCloc:
    """Parse cloc summary CSV and preserve one row per recognized language."""
    if not path.exists():
        raise FileNotFoundError(f"cloc CSV output was not created: {path}")
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))

    header_index: Optional[int] = None
    positions: dict[str, int] = {}
    for index, row in enumerate(rows):
        lowered = [cell.strip().lower() for cell in row]
        candidate = {name: pos for pos, name in enumerate(lowered)}
        if {"language", "files", "blank", "comment", "code"}.issubset(candidate):
            header_index = index
            positions = candidate
            break
    if header_index is None:
        preview = " | ".join(",".join(row) for row in rows[:5])
        raise ValueError(f"cloc summary CSV header was not found: {preview}")

    maximum = max(positions[name] for name in ("language", "files", "blank", "comment", "code"))
    languages: list[dict[str, Any]] = []
    sum_values: Optional[tuple[int, int, int, int]] = None
    for row in rows[header_index + 1 :]:
        if not row or len(row) <= maximum:
            continue
        language = row[positions["language"]].strip()
        if not language:
            continue
        values = (
            parse_nonnegative_int(row[positions["files"]], "files"),
            parse_nonnegative_int(row[positions["blank"]], "blank"),
            parse_nonnegative_int(row[positions["comment"]], "comment"),
            parse_nonnegative_int(row[positions["code"]], "code"),
        )
        if language.rstrip(":").strip().lower() in {"sum", "total"}:
            sum_values = values
            continue
        languages.append(
            {
                "language": language,
                "files": values[0],
                "blank": values[1],
                "comment": values[2],
                "code": values[3],
            }
        )

    if not languages and sum_values is None:
        # Some cloc versions produce only the header for a tree without any
        # recognized source language. Treat this as a valid zero-NCLOC result.
        sum_values = (0, 0, 0, 0)

    parsed = ParsedCloc(
        language_rows=languages,
        sum_row_present=sum_values is not None,
        sum_files=sum_values[0] if sum_values is not None else None,
        sum_blank=sum_values[1] if sum_values is not None else None,
        sum_comment=sum_values[2] if sum_values is not None else None,
        sum_code=sum_values[3] if sum_values is not None else None,
    )
    if not parsed.matches_sum_row:
        raise ValueError(
            "cloc language rows do not match the reported SUM row: "
            f"language_sum={(parsed.files, parsed.blank, parsed.comment, parsed.code)}, "
            f"sum_row={(parsed.sum_files, parsed.sum_blank, parsed.sum_comment, parsed.sum_code)}"
        )
    return parsed


def cloc_version(cloc_bin: str) -> str:
    """Read the cloc version string once per run."""
    process = run_command([cloc_bin, "--version"], 30)
    if process.returncode != 0:
        raise RuntimeError(f"Unable to run cloc --version: {process.stderr.strip()}")
    return process.stdout.strip().splitlines()[0] if process.stdout.strip() else "unknown"


def base_result(row: pd.Series, attempt: int, version: str) -> dict[str, Any]:
    """Create a complete snapshot result initialized to pending values."""
    record = {column: pd.NA for column in SNAPSHOT_RESULT_COLUMNS}
    for column in (
        "manifest_order",
        "repo_snapshot_key",
        "scope_role",
        "repo_name",
        "clone_path",
        "resolved_commit",
        "first_repo_month",
        "last_repo_month",
        "repo_month_count",
        "resolution_methods",
    ):
        record[column] = row[column]
    record.update(
        {
            "implementation_version": IMPLEMENTATION_VERSION,
            "count_backend": COUNT_BACKEND,
            "metric_definition": METRIC_DEFINITION,
            "scan_scope": SCAN_SCOPE,
            "scan_attempt": attempt,
            "scan_started_at": utc_now(),
            "scan_completed_at": "",
            "runtime_seconds": pd.NA,
            "git_precheck_status": "pending",
            "git_archive_status": "pending",
            "cloc_version": version,
            "status": "pending",
            "error_stage": "",
            "error_message": "",
            "raw_cloc_csv_path": "",
        }
    )
    return record


def process_snapshot(
    row: pd.Series,
    *,
    attempt: int,
    args: argparse.Namespace,
    version: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Materialize and measure one historical repository snapshot."""
    started = time.monotonic()
    result = base_result(row, attempt, version)
    language_records: list[dict[str, Any]] = []
    current_stage = "initialization"

    # Resolve every temporary path before invoking commands that may change
    # their working directory (notably `git -C`). Relative --output paths are
    # interpreted from the repository selected by `git -C`, not from the
    # project root. Using absolute paths prevents the C04 v1 archive failure.
    temp_root = Path(args.temp_root).expanduser()
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_root = temp_root.resolve()
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f"{sanitize_key(str(row['repo_snapshot_key']), 48)}-",
            dir=str(temp_root),
        )
    ).resolve()
    archive_path = (temporary / "snapshot.tar").resolve()
    tree_root = (temporary / "tree").resolve()
    raw_csv = (temporary / "cloc-summary.csv").resolve()

    try:
        clone_path = Path(str(row["clone_path"])).expanduser().resolve()
        commit_sha = str(row["resolved_commit"])

        current_stage = "git_precheck"
        valid, precheck = validate_git_snapshot(clone_path, commit_sha, args.git_timeout_seconds)
        result["git_precheck_status"] = precheck
        if not valid:
            raise RuntimeError(precheck)

        current_stage = "git_tree_inspection"
        tree_metrics = inspect_git_tree(clone_path, commit_sha, args.git_timeout_seconds)
        result.update(
            {
                "git_tree_entry_count": tree_metrics.entry_count,
                "git_tree_regular_file_count": tree_metrics.regular_file_count,
                "git_tree_symlink_count": tree_metrics.symlink_count,
                "git_tree_gitlink_count": tree_metrics.gitlink_count,
                "git_tree_other_entry_count": tree_metrics.other_entry_count,
            }
        )

        if tree_metrics.regular_file_count == 0:
            # A valid historical commit can contain an empty tree or only
            # symlink/gitlink entries. Neither case contributes tracked regular
            # source files, so whole-repository cloc NCLOC is exactly zero.
            empty_tree = tree_metrics.entry_count == 0
            result.update(
                {
                    "git_archive_status": "not_required_empty_tree" if empty_tree else "not_required_no_regular_files",
                    "archive_regular_file_count": 0,
                    "archive_symlink_count": tree_metrics.symlink_count,
                    "archive_other_entry_count": tree_metrics.gitlink_count + tree_metrics.other_entry_count,
                    "materialized_file_count": 0,
                    "materialized_bytes": 0,
                    "git_lfs_pointer_file_count": 0,
                    "cloc_runtime_seconds": 0.0,
                    "cloc_return_code": 0,
                    "cloc_stdout_bytes": 0,
                    "cloc_stderr_bytes": 0,
                    "cloc_language_count": 0,
                    "cloc_file_count": 0,
                    "cloc_blank_lines": 0,
                    "cloc_comment_lines": 0,
                    "ncloc_local_cloc_whole_repo": 0,
                    "cloc_sum_row_present": False,
                    "cloc_sum_reported_files": 0,
                    "cloc_sum_reported_blank": 0,
                    "cloc_sum_reported_comment": 0,
                    "cloc_sum_reported_code": 0,
                    "language_sum_matches_sum_row": True,
                    "zero_ncloc_reason": "empty_git_tree" if empty_tree else "no_tracked_regular_files",
                    "status": "success_empty_git_tree" if empty_tree else "success_no_recognized_languages",
                }
            )
        else:
            current_stage = "git_archive"
            archive_command = [
                "git",
                "-C",
                str(clone_path),
                "archive",
                "--format=tar",
                f"--output={archive_path}",
                commit_sha,
            ]
            archive_process = run_command(archive_command, args.git_timeout_seconds)
            if archive_process.returncode != 0:
                result["git_archive_status"] = "git_archive_failed"
                raise RuntimeError(archive_process.stderr.strip() or "git archive failed")
            result["git_archive_status"] = "success"

            current_stage = "archive_materialization"
            archive_metrics = materialize_archive(archive_path, tree_root)
            archive_path.unlink(missing_ok=True)
            result.update(
                {
                    "archive_regular_file_count": archive_metrics.regular_file_count,
                    "archive_symlink_count": archive_metrics.symlink_count,
                    "archive_other_entry_count": archive_metrics.other_entry_count,
                    "materialized_file_count": archive_metrics.regular_file_count,
                    "materialized_bytes": archive_metrics.materialized_bytes,
                    "git_lfs_pointer_file_count": archive_metrics.lfs_pointer_file_count,
                }
            )

            current_stage = "cloc_execution"
            command = [
                args.cloc_bin,
                "--csv",
                "--quiet",
                "--skip-uniqueness",
                f"--out={raw_csv}",
            ]
            if args.exclude_dirs.strip():
                command.append(f"--exclude-dir={args.exclude_dirs.strip()}")
            command.append(str(tree_root))

            cloc_started = time.monotonic()
            cloc_process = run_command(command, args.cloc_timeout_seconds)
            result.update(
                {
                    "cloc_runtime_seconds": round(time.monotonic() - cloc_started, 3),
                    "cloc_return_code": cloc_process.returncode,
                    "cloc_stdout_bytes": len(cloc_process.stdout.encode("utf-8", errors="replace")),
                    "cloc_stderr_bytes": len(cloc_process.stderr.encode("utf-8", errors="replace")),
                }
            )
            if cloc_process.returncode != 0:
                raise RuntimeError(cloc_process.stderr.strip() or f"cloc exited with {cloc_process.returncode}")

            current_stage = "cloc_parse_or_zero_detection"
            zero_reason = ""
            if raw_csv.exists() and raw_csv.stat().st_size > 0:
                parsed = parse_cloc_csv(raw_csv)
            elif cloc_process.stdout.strip():
                # Preserve a valid CSV unexpectedly emitted to stdout instead
                # of the requested --out path, then parse it normally.
                raw_csv.write_text(cloc_process.stdout, encoding="utf-8")
                parsed = parse_cloc_csv(raw_csv)
            elif not cloc_process.stderr.strip():
                # cloc 1.90 returns zero and creates no CSV when the tree has
                # regular tracked files but none are recognized as source.
                parsed = zero_parsed_cloc(sum_row_present=False)
                zero_reason = "no_cloc_recognized_files"
            else:
                raise RuntimeError(
                    "cloc returned zero but created no CSV and emitted diagnostics: "
                    + cloc_process.stderr.strip()
                )

            result.update(
                {
                    "cloc_language_count": parsed.language_count,
                    "cloc_file_count": parsed.files,
                    "cloc_blank_lines": parsed.blank,
                    "cloc_comment_lines": parsed.comment,
                    "ncloc_local_cloc_whole_repo": parsed.code,
                    "cloc_sum_row_present": parsed.sum_row_present,
                    "cloc_sum_reported_files": parsed.sum_files,
                    "cloc_sum_reported_blank": parsed.sum_blank,
                    "cloc_sum_reported_comment": parsed.sum_comment,
                    "cloc_sum_reported_code": parsed.sum_code,
                    "language_sum_matches_sum_row": parsed.matches_sum_row,
                    "zero_ncloc_reason": zero_reason,
                    "status": "success" if parsed.language_count > 0 else "success_no_recognized_languages",
                }
            )

            for language in parsed.language_rows:
                language_records.append(
                    {
                        "repo_snapshot_key": row["repo_snapshot_key"],
                        "scope_role": row["scope_role"],
                        "repo_name": row["repo_name"],
                        "resolved_commit": row["resolved_commit"],
                        **language,
                        "implementation_version": IMPLEMENTATION_VERSION,
                        "count_backend": COUNT_BACKEND,
                        "cloc_version": version,
                    }
                )

            if args.keep_raw_cloc_csv:
                raw_root = Path(args.raw_cloc_csv_root).expanduser()
                raw_root.mkdir(parents=True, exist_ok=True)
                raw_root = raw_root.resolve()
                destination = (raw_root / f"{sanitize_key(str(row['repo_snapshot_key']), 100)}.csv").resolve()
                if raw_csv.exists():
                    shutil.copy2(raw_csv, destination)
                else:
                    destination.write_text("language,files,blank,comment,code\n", encoding="utf-8")
                result["raw_cloc_csv_path"] = str(destination)

    except subprocess.TimeoutExpired as exc:
        result["status"] = "timeout"
        result["error_stage"] = current_stage
        result["error_message"] = f"Command timed out after {exc.timeout} seconds: {exc.cmd}"
    except Exception as exc:  # noqa: BLE001 - preserve repository-level failures for audit
        result["status"] = "failed"
        result["error_stage"] = current_stage
        result["error_message"] = str(exc)[:4000]
        language_records = []
    finally:
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)
        if args.keep_temp:
            logging.info("Kept C04 temporary directory: %s", temporary)
        else:
            shutil.rmtree(temporary, ignore_errors=True)

    return result, language_records


def existing_success_is_complete(result: dict[str, Any], language_rows: list[dict[str, Any]]) -> bool:
    """Return whether a previous success has its expected normalized language rows."""
    if str(result.get("status")) not in SUCCESS_STATUSES:
        return False
    language_count = pd.to_numeric(result.get("cloc_language_count"), errors="coerce")
    if pd.isna(language_count):
        return False
    return int(language_count) == len(language_rows)


def select_targets(
    snapshots: pd.DataFrame,
    result_by_key: dict[str, dict[str, Any]],
    language_by_key: dict[str, list[dict[str, Any]]],
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, int]:
    """Apply run filters and resume rules."""
    selected = snapshots[snapshots["manifest_order"] >= args.start_order].copy()
    if args.scope_role:
        selected = selected[selected["scope_role"].eq(args.scope_role)]
    if args.repo_name:
        selected = selected[selected["repo_name"].eq(args.repo_name)]

    skipped = 0
    if not args.analysis_again:
        keep_indexes: list[int] = []
        for index, row in selected.iterrows():
            key = str(row["repo_snapshot_key"])
            previous = result_by_key.get(key)
            if previous and existing_success_is_complete(previous, language_by_key.get(key, [])):
                skipped += 1
            else:
                keep_indexes.append(index)
        selected = selected.loc[keep_indexes]

    if args.limit > 0:
        selected = selected.head(args.limit)
    return selected, skipped


def assemble_outputs(
    snapshots: pd.DataFrame,
    history: pd.DataFrame,
    result_by_key: dict[str, dict[str, Any]],
    language_by_key: dict[str, list[dict[str, Any]]],
    input_qc: list[dict[str, Any]],
    args: argparse.Namespace,
    run_target_keys: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Assemble normalized C04 outputs and strict coverage checks.

    Full runs require complete success for every C03 snapshot and repo-month.
    Filtered smoke tests validate only the snapshots selected for that run so
    stale failures from an earlier interrupted or defective run do not prevent
    a focused regression test from completing.
    """
    processed_results = pd.DataFrame(result_by_key.values())
    if processed_results.empty:
        processed_results = pd.DataFrame(columns=SNAPSHOT_RESULT_COLUMNS)
    for column in SNAPSHOT_RESULT_COLUMNS:
        if column not in processed_results.columns:
            processed_results[column] = pd.NA
    processed_results = processed_results[SNAPSHOT_RESULT_COLUMNS]
    order_map = snapshots.set_index("repo_snapshot_key")["manifest_order"].to_dict()
    processed_results["_order"] = processed_results["repo_snapshot_key"].map(order_map)
    processed_results = processed_results.sort_values("_order", na_position="last").drop(columns="_order")

    language_records = [row for rows in language_by_key.values() for row in rows]
    language_results = pd.DataFrame(language_records)
    if language_results.empty:
        language_results = pd.DataFrame(columns=LANGUAGE_RESULT_COLUMNS)
    for column in LANGUAGE_RESULT_COLUMNS:
        if column not in language_results.columns:
            language_results[column] = pd.NA
    language_results = language_results[LANGUAGE_RESULT_COLUMNS]
    language_results["_order"] = language_results["repo_snapshot_key"].map(order_map)
    language_results = language_results.sort_values(["_order", "language"]).drop(columns="_order")

    metric_columns = [
        "repo_snapshot_key",
        "status",
        "implementation_version",
        "count_backend",
        "cloc_version",
        "git_tree_entry_count",
        "git_tree_regular_file_count",
        "cloc_language_count",
        "cloc_file_count",
        "cloc_blank_lines",
        "cloc_comment_lines",
        "ncloc_local_cloc_whole_repo",
        "language_sum_matches_sum_row",
        "zero_ncloc_reason",
        "materialized_file_count",
        "materialized_bytes",
        "git_lfs_pointer_file_count",
        "runtime_seconds",
        "error_stage",
        "error_message",
    ]
    metrics = processed_results[metric_columns].rename(columns={"status": "cloc_snapshot_status"})
    completed = snapshots.merge(metrics, on="repo_snapshot_key", how="left", validate="one_to_one")
    completed["cloc_snapshot_status"] = completed["cloc_snapshot_status"].fillna("pending")

    repo_month = history.merge(metrics, on="repo_snapshot_key", how="left", validate="many_to_one")
    repo_month["cloc_snapshot_status"] = repo_month["cloc_snapshot_status"].fillna("pending")
    repo_month["cloc_available"] = repo_month["cloc_snapshot_status"].isin(SUCCESS_STATUSES)

    failures = processed_results[~processed_results["status"].isin(SUCCESS_STATUSES)].copy()

    qc_records = list(input_qc)
    duplicate_snapshot_results = int(processed_results["repo_snapshot_key"].duplicated().sum())
    duplicate_language_rows = int(language_results.duplicated(["repo_snapshot_key", "language"]).sum())
    success_results = processed_results[processed_results["status"].isin(SUCCESS_STATUSES)].copy()
    failed_results = processed_results[~processed_results["status"].isin(SUCCESS_STATUSES)].copy()
    run_scope_results = processed_results[
        processed_results["repo_snapshot_key"].astype(str).isin(run_target_keys)
    ].copy()
    run_scope_successes = run_scope_results[run_scope_results["status"].isin(SUCCESS_STATUSES)].copy()
    run_scope_failures = run_scope_results[~run_scope_results["status"].isin(SUCCESS_STATUSES)].copy()

    negative_counts = 0
    for column in ("cloc_file_count", "cloc_blank_lines", "cloc_comment_lines", "ncloc_local_cloc_whole_repo"):
        values = pd.to_numeric(success_results[column], errors="coerce")
        negative_counts += int((values < 0).sum())
    missing_success_ncloc = int(
        pd.to_numeric(success_results["ncloc_local_cloc_whole_repo"], errors="coerce").isna().sum()
    )
    missing_success_language_count = int(
        pd.to_numeric(success_results["cloc_language_count"], errors="coerce").isna().sum()
    )
    sum_mismatches = int(
        (~normalize_boolean(success_results["language_sum_matches_sum_row"]).fillna(False)).sum()
    ) if not success_results.empty else 0
    zero_ncloc = int(
        (pd.to_numeric(success_results["ncloc_local_cloc_whole_repo"], errors="coerce") == 0).sum()
    )
    empty_git_tree_successes = int(success_results["status"].eq("success_empty_git_tree").sum())
    no_recognized_language_successes = int(
        success_results["status"].eq("success_no_recognized_languages").sum()
    )
    preserved_v2_successes = int(success_results["implementation_version"].eq("v2").sum())
    v3_successes = int(success_results["implementation_version"].eq("v3").sum())
    success_repo_month_rows = int(repo_month["cloc_available"].sum())
    language_aggregate_mismatches = 0
    if not success_results.empty:
        language_sums = language_results.groupby("repo_snapshot_key", as_index=True)["code"].sum()
        for _, row in success_results.iterrows():
            expected = int(pd.to_numeric(row["ncloc_local_cloc_whole_repo"], errors="raise"))
            observed = int(language_sums.get(row["repo_snapshot_key"], 0))
            if observed != expected:
                language_aggregate_mismatches += 1

    def add_check(name: str, observed: Any, expected: Any, severity: str, note: str = "") -> None:
        passed = int(observed) == int(expected)
        if severity == "info":
            status = "info"
        elif passed:
            status = "pass"
        else:
            status = "fail" if severity == "hard" else "warning"
        qc_records.append(
            {
                "check_name": name,
                "status": status,
                "severity": severity,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    # Structural checks are hard for every run mode.
    add_check("output_duplicate_snapshot_results", duplicate_snapshot_results, 0, "hard")
    add_check("output_duplicate_language_rows", duplicate_language_rows, 0, "hard")
    add_check("output_negative_cloc_counts", negative_counts, 0, "hard")
    add_check("output_success_missing_ncloc", missing_success_ncloc, 0, "hard")
    add_check("output_success_missing_language_count", missing_success_language_count, 0, "hard")
    add_check("output_language_sum_mismatches", sum_mismatches, 0, "hard")
    add_check("output_language_aggregate_mismatches", language_aggregate_mismatches, 0, "hard")
    add_check("output_repo_month_mapping_rows", len(repo_month), len(history), "hard")

    if args.require_complete_output:
        snapshot_role_counts = snapshots["scope_role"].value_counts().to_dict()
        success_role_counts = success_results["scope_role"].value_counts().to_dict() if not success_results.empty else {}
        add_check("output_processed_snapshot_results", len(processed_results), len(snapshots), "hard")
        add_check("output_successful_snapshot_results", len(success_results), len(snapshots), "hard")
        add_check("output_failed_or_pending_snapshot_results", len(failed_results), 0, "hard")
        add_check(
            "output_successful_treatment_snapshots",
            int(success_role_counts.get("treatment", 0)),
            int(snapshot_role_counts.get("treatment", 0)),
            "hard",
        )
        add_check(
            "output_successful_control_snapshots",
            int(success_role_counts.get("control", 0)),
            int(snapshot_role_counts.get("control", 0)),
            "hard",
        )
        add_check("output_success_repo_month_rows", success_repo_month_rows, len(history), "hard")
        add_check("output_missing_repo_month_cloc_rows", len(repo_month) - success_repo_month_rows, 0, "hard")
        add_check(
            "output_recognized_language_rows_positive",
            int(len(language_results) > 0),
            1,
            "hard",
            "A complete C04 run must produce normalized language-level rows.",
        )
        add_check(
            "output_zero_ncloc_successes",
            zero_ncloc,
            args.expected_zero_ncloc_snapshots,
            "hard",
            "Confirmed by the C04d manual diagnostics before the v3 resume run.",
        )
        add_check(
            "output_empty_git_tree_successes",
            empty_git_tree_successes,
            args.expected_empty_git_tree_snapshots,
            "hard",
        )
        add_check(
            "output_no_recognized_language_successes",
            no_recognized_language_successes,
            args.expected_no_recognized_language_snapshots,
            "hard",
        )
        add_check(
            "output_preserved_v2_successes",
            preserved_v2_successes,
            args.expected_preserved_v2_successes,
            "hard",
            "The v3 resume run must preserve the 1,823 complete v2 results.",
        )
        add_check(
            "output_v3_successes",
            v3_successes,
            args.expected_v3_successes,
            "hard",
            "The v3 resume run should repair only the five confirmed zero-NCLOC snapshots.",
        )
    elif not args.dry_run:
        # Filtered/smoke runs validate exactly the snapshots selected for this
        # invocation. Other stored failures remain visible but do not invalidate
        # the regression test; the subsequent full run must clear them.
        run_scope_missing_ncloc = int(
            pd.to_numeric(run_scope_successes["ncloc_local_cloc_whole_repo"], errors="coerce").isna().sum()
        )
        add_check("run_target_snapshot_results", len(run_scope_results), len(run_target_keys), "hard")
        add_check("run_target_successful_snapshots", len(run_scope_successes), len(run_target_keys), "hard")
        add_check("run_target_failed_snapshots", len(run_scope_failures), 0, "hard")
        add_check("run_target_success_missing_ncloc", run_scope_missing_ncloc, 0, "hard")
        add_check(
            "stored_non_success_snapshots_outside_run_target",
            len(failed_results) - len(run_scope_failures),
            0,
            "warning",
            "Expected after a partial smoke test over stale or incomplete prior outputs.",
        )
    else:
        add_check("dry_run_selected_snapshots", len(run_target_keys), 0, "info")

    if not args.require_complete_output:
        add_check(
            "zero_ncloc_successes_observed",
            zero_ncloc,
            zero_ncloc,
            "info",
            "Zero-NCLOC successes are valid when Git or cloc finds no tracked regular source files.",
        )
    qc = pd.DataFrame(qc_records)

    role_success = success_results["scope_role"].value_counts().to_dict() if not success_results.empty else {}
    summary_pairs = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("count_backend", COUNT_BACKEND),
        ("metric_definition", METRIC_DEFINITION),
        ("require_complete_output", args.require_complete_output),
        ("input_unique_snapshots", len(snapshots)),
        ("input_repo_month_rows", len(history)),
        ("run_target_snapshots", len(run_target_keys)),
        ("processed_snapshot_results", len(processed_results)),
        ("successful_snapshots", len(success_results)),
        ("successful_treatment_snapshots", int(role_success.get("treatment", 0))),
        ("successful_control_snapshots", int(role_success.get("control", 0))),
        ("failed_or_pending_snapshots", len(failed_results)),
        ("recognized_language_rows", len(language_results)),
        ("zero_ncloc_successes", zero_ncloc),
        ("empty_git_tree_successes", empty_git_tree_successes),
        ("no_recognized_language_successes", no_recognized_language_successes),
        ("preserved_v2_successes", preserved_v2_successes),
        ("v3_successes", v3_successes),
        ("repo_month_rows_with_cloc", success_repo_month_rows),
        ("repo_month_rows_without_cloc", int(len(repo_month) - success_repo_month_rows)),
        ("hard_qc_failures", int(((qc["severity"] == "hard") & (qc["status"] == "fail")).sum())),
        ("qc_warnings", int((qc["status"] == "warning").sum())),
    ]
    summary = pd.DataFrame(summary_pairs, columns=["metric", "value"])
    return processed_results, language_results, repo_month, completed, failures, qc, summary


def write_outputs(
    snapshots: pd.DataFrame,
    history: pd.DataFrame,
    result_by_key: dict[str, dict[str, Any]],
    language_by_key: dict[str, list[dict[str, Any]]],
    input_qc: list[dict[str, Any]],
    args: argparse.Namespace,
    run_target_keys: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write every C04 output and return QC and summary frames."""
    outputs = assemble_outputs(
        snapshots,
        history,
        result_by_key,
        language_by_key,
        input_qc,
        args,
        run_target_keys,
    )
    snapshot_results, language_results, repo_month, completed, failures, qc, summary = outputs
    atomic_write_csv(snapshot_results, Path(args.snapshot_results_output), SNAPSHOT_RESULT_COLUMNS)
    atomic_write_csv(language_results, Path(args.language_results_output), LANGUAGE_RESULT_COLUMNS)
    atomic_write_csv(repo_month, Path(args.repo_month_results_output))
    atomic_write_csv(completed, Path(args.completed_manifest_output))
    atomic_write_csv(failures, Path(args.failures_output), SNAPSHOT_RESULT_COLUMNS)
    atomic_write_csv(qc, Path(args.qc_output))
    atomic_write_csv(summary, Path(args.summary_output))
    return qc, summary


def main() -> int:
    """Run C04."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    snapshots, history = load_inputs(args)
    input_qc = build_input_qc(snapshots, history, args)
    version = cloc_version(args.cloc_bin)
    logging.info("cloc version: %s", version)
    logging.info(
        "Loaded %d unique snapshots covering %d repo-month rows across %d repositories",
        len(snapshots),
        len(history),
        snapshots["repo_name"].nunique(),
    )

    existing_results = read_optional_csv(Path(args.snapshot_results_output), SNAPSHOT_RESULT_COLUMNS)
    existing_languages = read_optional_csv(Path(args.language_results_output), LANGUAGE_RESULT_COLUMNS)
    valid_keys = set(snapshots["repo_snapshot_key"])
    existing_results = existing_results[existing_results["repo_snapshot_key"].isin(valid_keys)]
    existing_languages = existing_languages[existing_languages["repo_snapshot_key"].isin(valid_keys)]

    result_by_key = {
        str(row["repo_snapshot_key"]): row.to_dict()
        for _, row in existing_results.iterrows()
    }
    language_by_key: dict[str, list[dict[str, Any]]] = {}
    for key, group in existing_languages.groupby("repo_snapshot_key", sort=False):
        language_by_key[str(key)] = group.to_dict("records")

    selected, skipped = select_targets(snapshots, result_by_key, language_by_key, args)
    run_target_keys = set(selected["repo_snapshot_key"].astype(str))
    logging.info(
        "Selected %d snapshots for this run; skipped %d prior complete successes",
        len(selected),
        skipped,
    )

    if args.dry_run:
        qc, summary = write_outputs(snapshots, history, result_by_key, language_by_key, input_qc, args, run_target_keys)
        logging.info("Dry run completed without scanning snapshots")
        return 0

    processed_this_run = 0
    successes_this_run = 0
    failures_this_run = 0
    started = time.monotonic()

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures: dict[Future[tuple[dict[str, Any], list[dict[str, Any]]]], str] = {}
            for _, row in selected.iterrows():
                key = str(row["repo_snapshot_key"])
                prior = result_by_key.get(key, {})
                prior_attempt = pd.to_numeric(prior.get("scan_attempt"), errors="coerce")
                attempt = int(prior_attempt) + 1 if pd.notna(prior_attempt) else 1
                future = executor.submit(process_snapshot, row, attempt=attempt, args=args, version=version)
                futures[future] = key

            for future in as_completed(futures):
                key = futures[future]
                result, languages = future.result()
                result_by_key[key] = result
                language_by_key[key] = languages
                processed_this_run += 1
                if result["status"] in SUCCESS_STATUSES:
                    successes_this_run += 1
                else:
                    failures_this_run += 1
                    logging.warning(
                        "C04 snapshot failed: %s %s status=%s stage=%s error=%s",
                        result["repo_name"],
                        result["resolved_commit"],
                        result["status"],
                        result["error_stage"],
                        result["error_message"],
                    )

                if processed_this_run % args.save_every == 0:
                    write_outputs(snapshots, history, result_by_key, language_by_key, input_qc, args, run_target_keys)
                if processed_this_run % args.progress_every == 0 or processed_this_run == len(selected):
                    elapsed = max(time.monotonic() - started, 0.001)
                    rate = processed_this_run / elapsed * 3600.0
                    logging.info(
                        "Progress: %d/%d processed; success=%d; failures=%d; rate=%.1f snapshots/hour",
                        processed_this_run,
                        len(selected),
                        successes_this_run,
                        failures_this_run,
                        rate,
                    )
    except KeyboardInterrupt:
        logging.warning("Interrupted by user; saving completed snapshot results before exit")
        write_outputs(snapshots, history, result_by_key, language_by_key, input_qc, args, run_target_keys)
        return 130

    qc, summary = write_outputs(snapshots, history, result_by_key, language_by_key, input_qc, args, run_target_keys)
    hard_failures = int(((qc["severity"] == "hard") & (qc["status"] == "fail")).sum())
    warning_count = int((qc["status"] == "warning").sum())
    total_successes = sum(1 for result in result_by_key.values() if result.get("status") in SUCCESS_STATUSES)
    total_failed_or_pending = len(snapshots) - total_successes
    logging.info(
        "Completed run-x-c04-v3: processed_this_run=%d; successes_this_run=%d; "
        "failures_this_run=%d; total_successes=%d; total_failed_or_pending=%d; "
        "hard_qc_failures=%d; warnings=%d",
        processed_this_run,
        successes_this_run,
        failures_this_run,
        total_successes,
        total_failed_or_pending,
        hard_failures,
        warning_count,
    )
    if hard_failures:
        logging.error("C04 produced %d hard QC failure(s)", hard_failures)
        return 2
    if args.fail_on_unresolved and total_successes < len(snapshots):
        logging.error("C04 has unresolved snapshot scans and --fail-on-unresolved=1")
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - top-level logging for reproducible runs
        logging.exception("run-x-c04-v3 failed: %s", exc)
        raise
