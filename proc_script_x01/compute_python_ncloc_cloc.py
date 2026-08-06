#!/usr/bin/env python3
"""Compute Python-only NCLOC with cloc for historical Git snapshots.

This is the cloc-only measurement stage for run-x-b02-v3. It reads the unique
snapshot manifest from run-x-a05, materializes the exact tracked regular Python
files from each historical commit without changing the clone checkout, and runs
cloc in default Python mode.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Sequence

import pandas as pd


IMPLEMENTATION_VERSION = "v3"
COUNT_BACKEND = "cloc_default_tracked_python_git_objects"
SCAN_SCOPE = "tracked_regular_python_blobs"
VALID_PYTHON_MODES = {"100644", "100755"}
EXCLUDED_DIRECTORY_NAMES = {
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
REQUIRED_MANIFEST_COLUMNS = {
    "dataset_source",
    "repo_name",
    "latest_commit_effective",
    "repo_month_rows",
    "first_panel_month",
    "last_panel_month",
    "clone_path",
    "python_file_count_all",
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
    "implementation_version",
    "count_backend",
    "scan_scope",
    "scan_attempt",
    "scan_started_at",
    "scan_completed_at",
    "runtime_seconds",
    "git_precheck_status",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "manifest_minus_git_file_count",
    "git_blob_count",
    "git_blob_bytes",
    "cloc_version",
    "cloc_runtime_seconds",
    "python_file_count_cloc",
    "python_file_count_cloc_matches_git",
    "git_minus_cloc_file_count",
    "git_paths_missing_from_cloc_count",
    "git_paths_missing_from_cloc_samples",
    "cloc_paths_not_in_git_count",
    "cloc_paths_not_in_git_samples",
    "cloc_blank_lines",
    "cloc_comment_lines",
    "ncloc_py_cloc",
    "cloc_status",
    "cloc_error_message",
    "status",
    "error_stage",
    "error_message",
]
ISSUE_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "stage",
    "error_type",
    "error_message",
]
FILE_COUNT_AUDIT_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "audit_type",
    "path",
    "path_bytes",
    "is_empty_blob",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_cloc",
    "count_delta",
    "note",
]


@dataclass(frozen=True)
class GitBlob:
    """One tracked regular Python blob."""

    path: str
    oid: str
    mode: str


@dataclass
class ClocMetrics:
    """Parsed cloc metrics for one snapshot."""

    python_file_count: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0
    counted_paths: tuple[str, ...] = ()


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    """Normalize a potentially missing text value."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def sanitize_key(value: str, max_length: int = 100) -> str:
    """Create a filesystem-safe identifier fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", clean_text(value))
    return (cleaned.strip("_.:-") or "unknown")[:max_length]


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    """Build the stable snapshot key used by the existing b01 workflow."""
    raw = f"{dataset_source}|{repo_name.lower()}|{commit_sha.lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return (
        f"{sanitize_key(dataset_source, 16)}__"
        f"{sanitize_key(repo_name, 70)}__{commit_sha[:12].lower()}__{digest}"
    )


def save_dataframe(df: pd.DataFrame, path: Path, columns: Optional[Sequence[str]] = None) -> None:
    """Write a CSV atomically."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    if columns is not None:
        for column in columns:
            if column not in output.columns:
                output[column] = pd.NA
        output = output[list(columns)]
    temporary = target.with_suffix(target.suffix + ".tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(target)


def run_command(
    command: Sequence[str],
    *,
    timeout: int,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    """Run an external command and capture output."""
    logging.debug("Running command: %s", " ".join(command))
    return subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        text=text,
    )


def validate_git_snapshot(clone_path: Path, commit_sha: str, timeout: int) -> tuple[bool, str]:
    """Validate the clone and requested commit."""
    if not clone_path.exists():
        return False, "clone_path_missing"
    repo_check = run_command(
        ["git", "-C", str(clone_path), "rev-parse", "--git-dir"],
        timeout=timeout,
    )
    if repo_check.returncode != 0:
        return False, "not_git_repository"
    commit_check = run_command(
        ["git", "-C", str(clone_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        timeout=timeout,
    )
    if commit_check.returncode != 0:
        return False, "commit_not_found"
    return True, "ready"


def path_is_python(path_text: str) -> bool:
    """Apply the run-x-b02 tracked Python path policy."""
    path = PurePosixPath(path_text)
    if not path.name.lower().endswith(".py"):
        return False
    return not any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts[:-1])


def list_python_blobs(clone_path: Path, commit_sha: str, timeout: int) -> list[GitBlob]:
    """List tracked regular Python blobs without checking out the commit."""
    process = run_command(
        ["git", "-C", str(clone_path), "ls-tree", "-r", "-z", "--full-tree", commit_sha],
        timeout=timeout,
        text=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "git ls-tree failed")
    blobs: list[GitBlob] = []
    for raw_entry in process.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode_b, object_type_b, oid_b = metadata.split(b" ", 2)
        mode = mode_b.decode("ascii", errors="replace")
        object_type = object_type_b.decode("ascii", errors="replace")
        oid = oid_b.decode("ascii", errors="replace")
        path = os.fsdecode(raw_path)
        if object_type == "blob" and mode in VALID_PYTHON_MODES and path_is_python(path):
            blobs.append(GitBlob(path=path, oid=oid, mode=mode))
    blobs.sort(key=lambda item: item.path)
    return blobs


def read_blob_batch(clone_path: Path, blobs: Sequence[GitBlob], timeout: int) -> dict[str, bytes]:
    """Read unique Git blobs with one cat-file batch call."""
    unique_oids = list(dict.fromkeys(blob.oid for blob in blobs))
    if not unique_oids:
        return {}
    request = "".join(f"{oid}\n" for oid in unique_oids).encode("ascii")
    process = subprocess.run(
        ["git", "-C", str(clone_path), "cat-file", "--batch"],
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "git cat-file --batch failed")
    stream = io.BytesIO(process.stdout)
    contents: dict[str, bytes] = {}
    for requested_oid in unique_oids:
        header = stream.readline()
        if not header:
            raise RuntimeError(f"Missing cat-file header for {requested_oid}")
        parts = header.rstrip(b"\n").split()
        if len(parts) != 3 or parts[1] != b"blob":
            raise RuntimeError(f"Unexpected cat-file header: {header!r}")
        returned_oid = parts[0].decode("ascii", errors="replace")
        size = int(parts[2])
        payload = stream.read(size)
        terminator = stream.read(1)
        if len(payload) != size or terminator != b"\n":
            raise RuntimeError(f"Incomplete cat-file payload for {requested_oid}")
        contents[returned_oid] = payload
    return contents


def safe_materialized_path(root: Path, path_text: str) -> Path:
    """Return a safe path under the temporary cloc root."""
    path = PurePosixPath(path_text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe Git path: {path_text!r}")
    destination = root.joinpath(*path.parts)
    resolved_root = root.resolve()
    resolved_destination = destination.resolve()
    if resolved_root != resolved_destination and resolved_root not in resolved_destination.parents:
        raise ValueError(f"Git path escaped the temporary root: {path_text!r}")
    return destination


def normalize_cloc_path(filename: str, materialized_root: Optional[Path]) -> str:
    """Normalize one cloc by-file path to the Git-relative POSIX path."""
    cleaned = clean_text(filename)
    if not cleaned:
        return ""
    candidate = Path(cleaned)
    if materialized_root is not None:
        try:
            relative = candidate.resolve().relative_to(materialized_root.resolve())
            return PurePosixPath(relative.as_posix()).as_posix()
        except (OSError, ValueError):
            root_text = materialized_root.resolve().as_posix().rstrip("/") + "/"
            normalized = candidate.as_posix()
            if normalized.startswith(root_text):
                return PurePosixPath(normalized[len(root_text) :]).as_posix()
    return PurePosixPath(candidate.as_posix()).as_posix()


def parse_cloc_csv(output: str, materialized_root: Optional[Path] = None) -> ClocMetrics:
    """Parse cloc summary or by-file CSV output."""
    rows = list(csv.reader(io.StringIO(output)))
    header_index: Optional[int] = None
    header: list[str] = []
    for index, row in enumerate(rows):
        lowered = [cell.strip().lower() for cell in row]
        names = set(lowered)
        if {"blank", "comment", "code"}.issubset(names) and ({"file", "filename", "language"} & names):
            header_index = index
            header = lowered
            break
    if header_index is None:
        raise ValueError("cloc CSV header was not found")
    positions = {name: index for index, name in enumerate(header)}
    filename_index = positions.get("filename", positions.get("file"))
    language_index = positions.get("language")
    files_index = positions.get("files")
    selected: list[list[str]] = []
    counted_paths: set[str] = set()
    for row in rows[header_index + 1 :]:
        if not row:
            continue
        if filename_index is not None:
            if len(row) <= filename_index:
                continue
            filename = row[filename_index].strip()
            if not filename or filename.rstrip(":").lower() in {"sum", "total"}:
                continue
        if language_index is not None:
            if len(row) <= language_index or row[language_index].strip().lower() != "python":
                continue
        selected.append(row)
        if filename_index is not None:
            normalized_path = normalize_cloc_path(row[filename_index], materialized_root)
            if normalized_path:
                counted_paths.add(normalized_path)
    if not selected:
        raise ValueError("cloc returned no Python rows")

    def count(row: list[str], name: str) -> int:
        return int(float(row[positions[name]].strip() or "0"))

    blank = sum(count(row, "blank") for row in selected)
    comment = sum(count(row, "comment") for row in selected)
    code = sum(count(row, "code") for row in selected)
    if filename_index is not None:
        file_count = len(counted_paths)
    elif files_index is not None:
        file_count = sum(int(float(row[files_index].strip() or "0")) for row in selected)
    else:
        file_count = len(selected)
    return ClocMetrics(file_count, blank, comment, code, tuple(sorted(counted_paths)))


def run_cloc(
    blobs: Sequence[GitBlob],
    contents: dict[str, bytes],
    *,
    cloc_bin: str,
    timeout: int,
    temp_root: Path,
    keep_temp: bool,
    snapshot_key: str,
) -> tuple[ClocMetrics, float]:
    """Materialize selected files and run cloc."""
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"{sanitize_key(snapshot_key, 40)}-", dir=str(temp_root))
    )
    started = time.monotonic()
    try:
        for blob in blobs:
            destination = safe_materialized_path(temp_dir, blob.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents[blob.oid])
        process = run_command(
            [
                cloc_bin,
                "--csv",
                "--by-file",
                "--quiet",
                "--skip-uniqueness",
                "--include-lang=Python",
                str(temp_dir),
            ],
            timeout=timeout,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or process.stdout.strip() or "cloc failed")
        return parse_cloc_csv(process.stdout, temp_dir), round(time.monotonic() - started, 3)
    finally:
        if keep_temp:
            logging.info("Kept cloc temporary directory: %s", temp_dir)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


def normalize_manifest(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the unique snapshot manifest."""
    missing = sorted(REQUIRED_MANIFEST_COLUMNS - set(raw.columns))
    if missing:
        raise ValueError(f"Snapshot manifest is missing required columns: {missing}")
    manifest = raw.copy()
    manifest["dataset_source"] = manifest["dataset_source"].map(clean_text).str.casefold()
    manifest["repo_name"] = manifest["repo_name"].map(clean_text)
    manifest["repo_key"] = manifest.get("repo_key", manifest["repo_name"]).map(clean_text).str.casefold()
    manifest["clone_path"] = manifest["clone_path"].map(clean_text)
    manifest["commit_sha"] = manifest["latest_commit_effective"].map(clean_text).str.casefold()
    if not manifest["commit_sha"].str.fullmatch(r"[0-9a-f]{40}").all():
        raise ValueError("Manifest contains invalid 40-character commit SHAs")
    for column in ["repo_month_rows", "python_file_count_all"]:
        manifest[column] = pd.to_numeric(manifest[column], errors="raise").astype(int)
    if manifest.duplicated(["dataset_source", "repo_name", "commit_sha"]).any():
        raise ValueError("Manifest contains duplicate repository-snapshot identities")
    manifest = manifest.reset_index(drop=True)
    manifest.insert(0, "manifest_order", range(1, len(manifest) + 1))
    manifest["snapshot_key"] = manifest.apply(
        lambda row: make_snapshot_key(row["dataset_source"], row["repo_name"], row["commit_sha"]),
        axis=1,
    )
    return manifest


def load_existing(path: Path) -> pd.DataFrame:
    """Load prior results for resume behavior."""
    target = path.expanduser().resolve()
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    existing = pd.read_csv(target, low_memory=False)
    if "snapshot_key" not in existing.columns:
        raise ValueError("Existing cloc results do not contain snapshot_key")
    if existing["snapshot_key"].duplicated().any():
        raise ValueError("Existing cloc results contain duplicate snapshot_key values")
    for column in RESULT_COLUMNS:
        if column not in existing.columns:
            existing[column] = pd.NA
    return existing[RESULT_COLUMNS]


def prior_attempt(existing: pd.DataFrame, snapshot_key: str) -> int:
    """Return the previous attempt count for a snapshot."""
    rows = existing[existing["snapshot_key"].astype(str).eq(snapshot_key)]
    if rows.empty:
        return 0
    value = pd.to_numeric(rows.iloc[-1]["scan_attempt"], errors="coerce")
    return int(value) if pd.notna(value) else 0


def upsert(existing: pd.DataFrame, row: dict[str, Any]) -> pd.DataFrame:
    """Insert or replace one snapshot result without empty-frame concatenation."""
    output = existing.copy()
    values = [row.get(column, pd.NA) for column in RESULT_COLUMNS]
    matches = output["snapshot_key"].astype(str).eq(str(row["snapshot_key"])) if not output.empty else pd.Series(dtype=bool)
    if not output.empty and matches.any():
        index = output.index[matches][0]
        output.loc[index, RESULT_COLUMNS] = values
        return output[RESULT_COLUMNS]
    output.loc[len(output), RESULT_COLUMNS] = values
    return output[RESULT_COLUMNS]


def load_file_count_audit(path: Path) -> pd.DataFrame:
    """Load the resumable file-count audit output."""
    target = path.expanduser().resolve()
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=FILE_COUNT_AUDIT_COLUMNS)
    audit = pd.read_csv(target, low_memory=False)
    for column in FILE_COUNT_AUDIT_COLUMNS:
        if column not in audit.columns:
            audit[column] = pd.NA
    return audit[FILE_COUNT_AUDIT_COLUMNS]


def make_file_count_audit_row(
    row: dict[str, Any],
    *,
    audit_type: str,
    path: str = "",
    path_bytes: Any = pd.NA,
    is_empty_blob: Any = pd.NA,
    count_delta: Any = pd.NA,
    note: str = "",
) -> dict[str, Any]:
    """Build one file-count audit record."""
    return {
        "snapshot_key": row["snapshot_key"],
        "dataset_source": row["dataset_source"],
        "repo_name": row["repo_name"],
        "commit_sha": row["commit_sha"],
        "audit_type": audit_type,
        "path": path,
        "path_bytes": path_bytes,
        "is_empty_blob": is_empty_blob,
        "python_file_count_manifest": row.get("python_file_count_manifest", pd.NA),
        "python_file_count_git": row.get("python_file_count_git", pd.NA),
        "python_file_count_cloc": row.get("python_file_count_cloc", pd.NA),
        "count_delta": count_delta,
        "note": note,
    }


def measure_snapshot(
    manifest_row: pd.Series,
    existing: pd.DataFrame,
    args: argparse.Namespace,
    cloc_version: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Measure one historical snapshot with cloc."""
    started = time.monotonic()
    snapshot_key = str(manifest_row["snapshot_key"])
    clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
    commit_sha = str(manifest_row["commit_sha"])
    row: dict[str, Any] = {
        "manifest_order": int(manifest_row["manifest_order"]),
        "snapshot_key": snapshot_key,
        "dataset_source": str(manifest_row["dataset_source"]),
        "repo_name": str(manifest_row["repo_name"]),
        "repo_key": str(manifest_row["repo_key"]),
        "commit_sha": commit_sha,
        "clone_path": str(clone_path),
        "repo_month_rows": int(manifest_row["repo_month_rows"]),
        "first_panel_month": str(manifest_row["first_panel_month"]),
        "last_panel_month": str(manifest_row["last_panel_month"]),
        "implementation_version": IMPLEMENTATION_VERSION,
        "count_backend": COUNT_BACKEND,
        "scan_scope": SCAN_SCOPE,
        "scan_attempt": prior_attempt(existing, snapshot_key) + 1,
        "scan_started_at": utc_now(),
        "scan_completed_at": "",
        "runtime_seconds": pd.NA,
        "git_precheck_status": "pending",
        "python_file_count_manifest": int(manifest_row["python_file_count_all"]),
        "python_file_count_git": pd.NA,
        "python_file_count_matches_manifest": pd.NA,
        "manifest_minus_git_file_count": pd.NA,
        "git_blob_count": pd.NA,
        "git_blob_bytes": pd.NA,
        "cloc_version": cloc_version,
        "cloc_runtime_seconds": pd.NA,
        "python_file_count_cloc": pd.NA,
        "python_file_count_cloc_matches_git": pd.NA,
        "git_minus_cloc_file_count": pd.NA,
        "git_paths_missing_from_cloc_count": pd.NA,
        "git_paths_missing_from_cloc_samples": "",
        "cloc_paths_not_in_git_count": pd.NA,
        "cloc_paths_not_in_git_samples": "",
        "cloc_blank_lines": pd.NA,
        "cloc_comment_lines": pd.NA,
        "ncloc_py_cloc": pd.NA,
        "cloc_status": "pending",
        "cloc_error_message": "",
        "status": "pending",
        "error_stage": "",
        "error_message": "",
    }
    issues: list[dict[str, Any]] = []
    file_count_audit: list[dict[str, Any]] = []
    try:
        ready, precheck = validate_git_snapshot(clone_path, commit_sha, args.git_timeout_seconds)
        row["git_precheck_status"] = precheck
        if not ready:
            row["cloc_status"] = precheck
            row["status"] = precheck
            row["error_stage"] = "git_precheck"
            row["error_message"] = precheck
            return row, issues, file_count_audit
        blobs = list_python_blobs(clone_path, commit_sha, args.git_timeout_seconds)
        row["python_file_count_git"] = len(blobs)
        row["python_file_count_matches_manifest"] = len(blobs) == int(row["python_file_count_manifest"])
        row["manifest_minus_git_file_count"] = int(row["python_file_count_manifest"]) - len(blobs)
        row["git_blob_count"] = len(blobs)
        if not row["python_file_count_matches_manifest"]:
            file_count_audit.append(
                make_file_count_audit_row(
                    row,
                    audit_type="manifest_vs_git_count",
                    count_delta=row["manifest_minus_git_file_count"],
                    note=(
                        "The snapshot manifest stores the expected count but not the complete path list; "
                        "inspect upstream path-policy provenance when this delta is nonzero."
                    ),
                )
            )
        if not blobs:
            row["cloc_status"] = "no_python_files"
            row["status"] = "no_python_files"
            row["error_stage"] = "git_ls_tree"
            row["error_message"] = "No included tracked Python files were found."
            return row, issues, file_count_audit
        contents = read_blob_batch(clone_path, blobs, args.git_timeout_seconds)
        row["git_blob_bytes"] = sum(len(contents[blob.oid]) for blob in blobs)
        metrics, cloc_runtime = run_cloc(
            blobs,
            contents,
            cloc_bin=args.cloc_bin,
            timeout=args.cloc_timeout_seconds,
            temp_root=args.cloc_temp_root.expanduser().resolve(),
            keep_temp=args.keep_cloc_temp,
            snapshot_key=snapshot_key,
        )
        row["cloc_runtime_seconds"] = cloc_runtime
        row["python_file_count_cloc"] = metrics.python_file_count
        row["python_file_count_cloc_matches_git"] = metrics.python_file_count == len(blobs)
        row["git_minus_cloc_file_count"] = len(blobs) - metrics.python_file_count
        row["cloc_blank_lines"] = metrics.blank_lines
        row["cloc_comment_lines"] = metrics.comment_lines
        row["ncloc_py_cloc"] = metrics.code_lines

        blob_by_path = {blob.path: blob for blob in blobs}
        git_paths = set(blob_by_path)
        cloc_paths = set(metrics.counted_paths)
        missing_from_cloc = sorted(git_paths - cloc_paths)
        cloc_not_in_git = sorted(cloc_paths - git_paths)
        row["git_paths_missing_from_cloc_count"] = len(missing_from_cloc)
        row["git_paths_missing_from_cloc_samples"] = " | ".join(missing_from_cloc[:10])
        row["cloc_paths_not_in_git_count"] = len(cloc_not_in_git)
        row["cloc_paths_not_in_git_samples"] = " | ".join(cloc_not_in_git[:10])

        for path in missing_from_cloc:
            blob = blob_by_path[path]
            payload_size = len(contents[blob.oid])
            file_count_audit.append(
                make_file_count_audit_row(
                    row,
                    audit_type="git_path_missing_from_cloc",
                    path=path,
                    path_bytes=payload_size,
                    is_empty_blob=payload_size == 0,
                    count_delta=1,
                    note="Tracked included Python path was materialized but did not appear in cloc by-file output.",
                )
            )
        for path in cloc_not_in_git:
            file_count_audit.append(
                make_file_count_audit_row(
                    row,
                    audit_type="cloc_path_not_in_git",
                    path=path,
                    count_delta=1,
                    note="cloc reported a path that was not in the selected Git Python path set.",
                )
            )
        if not row["python_file_count_cloc_matches_git"] and not missing_from_cloc and not cloc_not_in_git:
            file_count_audit.append(
                make_file_count_audit_row(
                    row,
                    audit_type="git_vs_cloc_count_without_path_delta",
                    count_delta=row["git_minus_cloc_file_count"],
                    note="File-count mismatch remained after normalized path-set comparison.",
                )
            )
        row["cloc_status"] = "success"
        row["status"] = "success"
        return row, issues, file_count_audit
    except Exception as exc:
        row["cloc_status"] = "measurement_failed"
        row["cloc_error_message"] = str(exc)
        row["status"] = "measurement_failed"
        row["error_stage"] = "cloc_measurement"
        row["error_message"] = str(exc)
        issues.append(
            {
                "snapshot_key": snapshot_key,
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "commit_sha": commit_sha,
                "path": "",
                "stage": "cloc_measurement",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        return row, issues, file_count_audit
    finally:
        row["scan_completed_at"] = utc_now()
        row["runtime_seconds"] = round(time.monotonic() - started, 3)


def boolean_false_count(series: pd.Series) -> int:
    """Count explicit false values without object-dtype downcasting."""
    return int(series.astype("string").str.strip().str.casefold().eq("false").sum())


def build_qc(manifest: pd.DataFrame, results: pd.DataFrame, args: argparse.Namespace, full_scope: bool) -> pd.DataFrame:
    """Build cloc measurement QC checks."""
    records: list[dict[str, Any]] = []

    def add(name: str, observed: Any, expected: Any, policy: str = "always", note: str = "") -> None:
        if observed == expected:
            status = "pass"
        elif policy == "always":
            status = "fail"
        elif policy == "strict":
            status = "fail" if args.strict_expected_counts else "warn"
        else:
            status = "warn"
        records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "policy": policy,
                "note": note,
            }
        )

    selected_keys = set(manifest["snapshot_key"])
    selected_results = results[results["snapshot_key"].isin(selected_keys)].copy()
    add("selected_result_rows", len(selected_results), len(manifest), policy="always")
    add("duplicate_snapshot_keys", int(selected_results["snapshot_key"].duplicated().sum()), 0, policy="always")
    success = selected_results["cloc_status"].eq("success")
    add("successful_snapshots", int(success.sum()), len(manifest), policy="strict")
    add(
        "negative_ncloc_py_cloc",
        int((pd.to_numeric(selected_results["ncloc_py_cloc"], errors="coerce") < 0).sum()),
        0,
        policy="always",
    )
    add(
        "manifest_vs_git_file_count_mismatches",
        boolean_false_count(selected_results["python_file_count_matches_manifest"]),
        0,
        policy="warn",
        note="A nonzero value indicates a path-policy or upstream-manifest count difference.",
    )
    add(
        "git_vs_cloc_file_count_mismatches",
        boolean_false_count(selected_results["python_file_count_cloc_matches_git"]),
        0,
        policy="warn",
        note="cloc may omit empty or zero-count files; inspect the file-count audit CSV.",
    )
    add(
        "git_paths_missing_from_cloc",
        int(pd.to_numeric(selected_results["git_paths_missing_from_cloc_count"], errors="coerce").fillna(0).sum()),
        0,
        policy="warn",
        note="Each missing path is listed in the file-count audit CSV.",
    )
    add(
        "cloc_paths_not_in_git",
        int(pd.to_numeric(selected_results["cloc_paths_not_in_git_count"], errors="coerce").fillna(0).sum()),
        0,
        policy="always",
        note="cloc must not report paths outside the selected Git path set.",
    )
    if full_scope:
        add("full_snapshot_rows", len(manifest), args.expected_snapshots, policy="strict")
        add(
            "treatment_snapshots",
            int(manifest["dataset_source"].eq("treatment").sum()),
            args.expected_treatment_snapshots,
            policy="strict",
        )
        add(
            "control_snapshots",
            int(manifest["dataset_source"].eq("control").sum()),
            args.expected_control_snapshots,
            policy="strict",
        )
    return pd.DataFrame(records)


def build_summary(
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    issues: pd.DataFrame,
    file_count_audit: pd.DataFrame,
    cloc_version: str,
) -> pd.DataFrame:
    """Build a long-form cloc summary."""
    rows: list[dict[str, Any]] = []

    def add(section: str, metric: str, value: Any, note: str = "") -> None:
        rows.append({"section": section, "metric": metric, "value": value, "note": note})

    selected = results[results["snapshot_key"].isin(set(manifest["snapshot_key"]))].copy()
    success = selected[selected["cloc_status"].eq("success")]
    add("implementation", "version", IMPLEMENTATION_VERSION)
    add("implementation", "cloc_version", cloc_version)
    add("definition", "count_backend", COUNT_BACKEND)
    add("definition", "scan_scope", SCAN_SCOPE)
    add("definition", "cloc_mode", "default_python_by_file_skip_uniqueness")
    add("input", "snapshots", len(manifest))
    add("input", "repositories", manifest["repo_name"].nunique())
    add("output", "successful_snapshots", len(success))
    add("output", "unresolved_snapshots", len(manifest) - len(success))
    add("output", "issue_rows", len(issues))
    add("output", "file_count_audit_rows", len(file_count_audit))
    if not success.empty:
        values = pd.to_numeric(success["ncloc_py_cloc"], errors="coerce").dropna()
        add("ncloc_py_cloc", "min", values.min())
        add("ncloc_py_cloc", "median", values.median())
        add("ncloc_py_cloc", "mean", values.mean())
        add("ncloc_py_cloc", "max", values.max())
    return pd.DataFrame(rows)


def filter_manifest(manifest: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    """Apply optional snapshot filters."""
    selected = manifest.copy()
    if args.dataset_source:
        selected = selected[selected["dataset_source"].eq(args.dataset_source)]
    if args.repo_name:
        selected = selected[selected["repo_name"].eq(args.repo_name)]
    selected = selected[selected["manifest_order"] >= args.start_order]
    if args.limit > 0:
        selected = selected.head(args.limit)
    if selected.empty:
        raise ValueError("No snapshots matched the requested filters")
    return selected


def run_self_test() -> None:
    """Validate cloc CSV parsing and path policies."""
    sample = """File,blank,comment,code\n/tmp/a.py,2,3,10\n/tmp/b.py,1,4,7\nSUM,3,7,17\n"""
    metrics = parse_cloc_csv(sample)
    assert (metrics.python_file_count, metrics.blank_lines, metrics.comment_lines, metrics.code_lines) == (2, 3, 7, 17)
    assert metrics.counted_paths == ("/tmp/a.py", "/tmp/b.py")
    assert path_is_python("src/a.py")
    assert not path_is_python("build/a.py")
    logging.info("Self-test PASS: cloc CSV parser and Python path policy")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    if "--self-test" in sys.argv[1:]:
        return argparse.Namespace(self_test=True, log_level="INFO")
    parser = argparse.ArgumentParser(description="Compute Python-only NCLOC with cloc.")
    parser.add_argument("--input-manifest-file", type=Path, required=True)
    parser.add_argument("--snapshot-results-output", type=Path, required=True)
    parser.add_argument("--issues-output", type=Path, required=True)
    parser.add_argument("--file-count-audit-output", type=Path, required=True)
    parser.add_argument("--qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--cloc-bin", default="cloc")
    parser.add_argument("--cloc-temp-root", type=Path, required=True)
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--cloc-timeout-seconds", type=int, default=300)
    parser.add_argument("--keep-cloc-temp", action="store_true")
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dataset-source", choices=["", "treatment", "control"], default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--analysis-again", action="store_true")
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-treatment-snapshots", type=int, default=790)
    parser.add_argument("--expected-control-snapshots", type=int, default=706)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run the cloc-only snapshot measurement workflow."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    if args.self_test:
        run_self_test()
        return 0
    if args.start_order < 1 or args.limit < 0:
        raise ValueError("Invalid start-order or limit")
    version_process = run_command([args.cloc_bin, "--version"], timeout=args.cloc_timeout_seconds)
    if version_process.returncode != 0:
        raise RuntimeError(version_process.stderr.strip() or f"cloc not found: {args.cloc_bin}")
    cloc_version = version_process.stdout.strip() or version_process.stderr.strip() or "unknown"
    manifest = normalize_manifest(pd.read_csv(args.input_manifest_file, low_memory=False))
    selected = filter_manifest(manifest, args)
    full_scope = (
        not args.dataset_source
        and not args.repo_name
        and args.start_order == 1
        and args.limit == 0
    )
    existing = load_existing(args.snapshot_results_output)
    issues = pd.DataFrame(columns=ISSUE_COLUMNS)
    file_count_audit = load_file_count_audit(args.file_count_audit_output)
    successful_keys = set()
    if not args.analysis_again and not existing.empty:
        audit_keys = set(file_count_audit["snapshot_key"].astype(str))
        manifest_match = ~existing["python_file_count_matches_manifest"].astype("string").str.casefold().eq("false")
        cloc_match = ~existing["python_file_count_cloc_matches_git"].astype("string").str.casefold().eq("false")
        audit_ready = (manifest_match & cloc_match) | existing["snapshot_key"].astype(str).isin(audit_keys)
        success_mask = (
            existing["cloc_status"].eq("success")
            & pd.to_numeric(existing["ncloc_py_cloc"], errors="coerce").notna()
            & existing["implementation_version"].astype(str).eq(IMPLEMENTATION_VERSION)
            & audit_ready
        )
        successful_keys = set(existing.loc[success_mask, "snapshot_key"].astype(str))
    run_started = time.monotonic()
    for position, (_, target) in enumerate(selected.iterrows(), start=1):
        snapshot_key = str(target["snapshot_key"])
        if snapshot_key in successful_keys and not args.analysis_again:
            logging.info("Resume skip %d/%d: %s", position, len(selected), target["repo_name"])
            continue
        logging.info(
            "Snapshot %d/%d: %s at %s",
            position,
            len(selected),
            target["repo_name"],
            str(target["commit_sha"])[:12],
        )
        result, new_issues, new_file_count_audit = measure_snapshot(target, existing, args, cloc_version)
        existing = upsert(existing, result)
        issues = issues[issues["snapshot_key"].astype(str) != snapshot_key]
        if new_issues:
            incoming_issues = pd.DataFrame(new_issues, columns=ISSUE_COLUMNS)
            issues = incoming_issues if issues.empty else pd.concat([issues, incoming_issues], ignore_index=True)
        file_count_audit = file_count_audit[
            file_count_audit["snapshot_key"].astype(str) != snapshot_key
        ]
        if new_file_count_audit:
            incoming_audit = pd.DataFrame(new_file_count_audit, columns=FILE_COUNT_AUDIT_COLUMNS)
            file_count_audit = (
                incoming_audit
                if file_count_audit.empty
                else pd.concat([file_count_audit, incoming_audit], ignore_index=True)
            )
        save_dataframe(existing.sort_values("manifest_order", kind="stable"), args.snapshot_results_output, RESULT_COLUMNS)
        save_dataframe(issues, args.issues_output, ISSUE_COLUMNS)
        save_dataframe(file_count_audit, args.file_count_audit_output, FILE_COUNT_AUDIT_COLUMNS)
        if position % max(args.progress_every, 1) == 0 or position == len(selected):
            elapsed = max(time.monotonic() - run_started, 0.001)
            logging.info(
                "Progress: %d/%d; rate=%.2f snapshots/hour",
                position,
                len(selected),
                position / elapsed * 3600,
            )
    existing = existing.sort_values("manifest_order", kind="stable").reset_index(drop=True)
    qc = build_qc(selected, existing, args, full_scope)
    summary = build_summary(selected, existing, issues, file_count_audit, cloc_version)
    save_dataframe(existing, args.snapshot_results_output, RESULT_COLUMNS)
    save_dataframe(issues, args.issues_output, ISSUE_COLUMNS)
    save_dataframe(file_count_audit, args.file_count_audit_output, FILE_COUNT_AUDIT_COLUMNS)
    save_dataframe(qc, args.qc_output)
    save_dataframe(summary, args.summary_output)
    failures = qc[qc["status"].eq("fail")]
    logging.info(
        "Completed cloc measurement: selected=%d; successful=%d; failures=%d; warnings=%d",
        len(selected),
        int(existing[existing["snapshot_key"].isin(set(selected["snapshot_key"]))]["cloc_status"].eq("success").sum()),
        len(failures),
        int(qc["status"].eq("warn").sum()),
    )
    if not failures.empty:
        logging.error("Blocking QC failures:\n%s", failures.to_string(index=False))
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        logging.exception("compute_python_ncloc_cloc failed: %s", exc)
        raise SystemExit(1)
