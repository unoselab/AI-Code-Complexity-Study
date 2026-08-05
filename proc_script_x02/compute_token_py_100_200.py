#!/usr/bin/env python3
"""Compute snapshot-level raw Python function-body token metrics.

This is the self-contained v2 implementation for the run-x-d01 experiment. It
uses the same historical repository snapshots and tracked-Python file scope as
run-x-b01, but it does not run cloc and it does not measure code lines.

For each snapshot, the program:

1. Lists tracked Python blobs at the requested commit with ``git ls-tree``.
2. Reads original blob bytes with one ``git cat-file --batch`` process.
3. Delegates AST parsing to the configured external Python 3.12 interpreter.
4. Locates module functions, class methods, and async variants.
5. Excludes nested functions as separate occurrences; their source remains in
   the enclosing function's raw implementation body.
6. Extracts the original raw implementation body, excluding decorators,
   function signature, and a leading docstring according to the established
   raw-body extraction policy.
7. Defines one token as one field returned by ``raw_body.split(" ")``. Empty
   fields created by leading, trailing, or repeated literal spaces are counted.
8. Aggregates bodies whose individual token counts are between 100 and 200,
   inclusive, into ``token_py_100_200``.

No source normalization is applied. Indentation, comments, line endings, tabs,
repeated literal spaces, inline comments, and original formatting are retained.
Each tracked path and each eligible function occurrence is counted. Function
bodies are not deduplicated.

Every successfully extracted raw body is also saved as a UTF-8 ``.txt`` file
under a stable per-snapshot directory. The default wrapper stores these files
under ``py-fun-body`` so later research modules can reuse the exact extracted
inputs without repeating source-boundary logic.

When one or more source files cannot be decoded or parsed, successful-file
partial aggregates are retained in ``*_partial`` columns. The final metric is
left unavailable until the snapshot is reviewed, unless an optional resolution
file explicitly accepts the partial value.
"""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Optional, Sequence

AST_WORKER_MODE = any(
    argument in {"--ast-worker", "--ast-worker-version"}
    for argument in sys.argv[1:]
)

if not AST_WORKER_MODE:
    import pandas as pd


IMPLEMENTATION_VERSION = "v2"
EXPERIMENT_NAME = "run-x-d01-compute-token-py-100-200"
COUNT_BACKEND = "local_git_external_python312_ast_raw_body_split_space"
SCAN_SCOPE = "tracked_python_blobs_local_git"
TOKEN_MIN = 100
TOKEN_MAX = 200
TOKEN_DEFINITION = "len(raw_implementation_body.split(' '))"
FUNCTION_SCOPE_DEFINITION = (
    "module functions, class methods, and async variants; nested functions "
    "are not separate occurrences and remain inside outer raw bodies"
)
RAW_BODY_DEFINITION = (
    "original source after function header or leading docstring through the "
    "complete physical AST end line; no strip, dedent, or whitespace normalization"
)
BODY_OUTPUT_ENCODING = "utf-8"
BODY_SAVE_SCOPES = {"all", "qualifying"}
AST_WORKER_PROTOCOL_VERSION = "v1"

HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
EXPECTED_DATASET_SOURCES = {"treatment", "control"}
VALID_PYTHON_BLOB_MODES = {"100644", "100755"}
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
    "implementation_version",
    "experiment_name",
    "count_backend",
    "scan_scope",
    "token_definition",
    "token_min_inclusive",
    "token_max_inclusive",
    "function_scope_definition",
    "raw_body_definition",
    "main_python_version",
    "ast_python_bin",
    "ast_python_version",
    "ast_worker_protocol_version",
    "ast_worker_timeout_seconds",
    "body_store_root",
    "body_save_scope",
    "body_store_snapshot_dir",
    "body_files_saved",
    "body_files_saved_100_200",
    "scan_attempt",
    "scan_started_at",
    "scan_completed_at",
    "runtime_seconds",
    "git_precheck_status",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "git_blob_count",
    "git_blob_bytes",
    "decoded_python_file_count",
    "parsed_python_file_count",
    "failed_python_file_count",
    "decode_failed_file_count",
    "syntax_error_file_count",
    "indentation_error_file_count",
    "tokenize_error_file_count",
    "other_parse_failed_file_count",
    "function_count_py_all_partial",
    "function_count_py_extracted_partial",
    "function_count_py_100_200_partial",
    "function_count_py_docstring_only_partial",
    "function_count_py_boundary_failed_partial",
    "function_count_py_with_nested_partial",
    "python_file_count_with_function_partial",
    "python_file_count_with_function_100_200_partial",
    "token_py_all_function_bodies_partial",
    "token_py_100_200_partial",
    "function_count_py_all",
    "function_count_py_extracted",
    "function_count_py_100_200",
    "function_count_py_docstring_only",
    "function_count_py_with_nested",
    "python_file_count_with_function",
    "python_file_count_with_function_100_200",
    "token_py_all_function_bodies",
    "token_py_100_200",
    "metric_available",
    "snapshot_status",
    "resolution_decision",
    "resolution_note",
    "partial_metric_accepted",
    "error_stage",
    "error_message",
]

FUNCTION_DETAIL_COLUMNS = [
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "blob_size",
    "source_encoding",
    "newline_style",
    "qualified_name",
    "function_name",
    "function_kind",
    "occurrence_index",
    "function_start_line",
    "function_end_line",
    "body_start_line",
    "body_end_line",
    "leading_docstring_removed",
    "contains_nested_named_definition",
    "raw_function_sha256",
    "raw_body_sha256",
    "raw_body_character_count",
    "raw_body_utf8_byte_count",
    "raw_body_physical_line_count",
    "body_key",
    "body_saved",
    "body_output_encoding",
    "body_output_relative_path",
    "body_output_path",
    "token_count",
    "qualifies_100_200",
    "extraction_status",
    "exclusion_reason",
]

FILE_ISSUE_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "blob_size",
    "issue_stage",
    "issue_type",
    "issue_message",
    "requires_review",
]

RESOLUTION_REQUIRED_COLUMNS = {
    "snapshot_key",
    "resolution_decision",
    "resolution_note",
}
RESOLUTION_DECISIONS = {"resolved_full", "accept_partial", "exclude"}


@dataclass(frozen=True)
class GitBlob:
    """One tracked regular Python blob at a historical commit."""

    path: str
    oid: str
    mode: str


@dataclass(frozen=True)
class FunctionRecord:
    """One eligible non-nested function indexed by the Python 3.12 AST worker."""

    qualified_name: str
    function_name: str
    function_kind: str
    occurrence_index: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    first_statement_line: int
    first_statement_col: int
    leading_docstring_removed: bool
    docstring_end_line: int
    contains_nested_named_definition: bool


@dataclass(frozen=True)
class ExtractedBody:
    """One original raw implementation-body extraction."""

    raw_function_source: str
    body_text: str
    body_start_line: int
    body_end_line: int
    leading_docstring_removed: bool
    token_count: int


@dataclass
class SnapshotPartialMetrics:
    """Successful-file partial aggregates for one snapshot."""

    decoded_python_file_count: int = 0
    parsed_python_file_count: int = 0
    failed_python_file_count: int = 0
    decode_failed_file_count: int = 0
    syntax_error_file_count: int = 0
    indentation_error_file_count: int = 0
    tokenize_error_file_count: int = 0
    other_parse_failed_file_count: int = 0
    function_count_py_all: int = 0
    function_count_py_extracted: int = 0
    function_count_py_100_200: int = 0
    function_count_py_docstring_only: int = 0
    function_count_py_boundary_failed: int = 0
    function_count_py_with_nested: int = 0
    python_file_count_with_function: int = 0
    python_file_count_with_function_100_200: int = 0
    token_py_all_function_bodies: int = 0
    token_py_100_200: int = 0


@dataclass
class RunCounters:
    """Run-level progress counters."""

    selected_targets: int = 0
    processed_this_run: int = 0
    skipped_existing_success: int = 0
    successful_this_run: int = 0
    partial_this_run: int = 0
    failed_this_run: int = 0


class StageError(RuntimeError):
    """Attach an explicit pipeline stage to an extraction failure."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class AstWorkerFileError(StageError):
    """Represent one source-file parsing error returned by the AST worker."""

    def __init__(self, stage: str, issue_type: str, message: str) -> None:
        super().__init__(stage, message)
        self.issue_type = issue_type


class SnapshotBodyStore:
    """Write one snapshot's extracted raw bodies and replace it atomically."""

    def __init__(self, root: Path, snapshot_key: str, save_scope: str) -> None:
        self.root = root.expanduser().resolve()
        self.snapshot_key = snapshot_key
        self.save_scope = save_scope
        self.final_dir = self.root / snapshot_key
        self.temp_dir: Optional[Path] = None
        self.saved_count = 0
        self.saved_qualifying_count = 0

    def start(self) -> None:
        """Create a temporary per-snapshot directory under the shared body root."""
        self.root.mkdir(parents=True, exist_ok=True)
        temp_root = self.root / ".tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(
            tempfile.mkdtemp(
                prefix=f"{sanitize_key(self.snapshot_key, 80)}-",
                dir=str(temp_root),
            )
        )

    def save(
        self,
        *,
        body_key: str,
        body_text: str,
        token_count: int,
        start_line: int,
        end_line: int,
        qualifies: bool,
    ) -> tuple[bool, str, str]:
        """Save one body and return saved flag, relative path, and final path."""
        should_save = self.save_scope == "all" or qualifies
        if not should_save:
            return False, "", ""
        if self.temp_dir is None:
            raise StageError("body_store", "Snapshot body store was not started")

        filename = (
            f"{body_key}__tok-{token_count}__L{start_line}-L{end_line}.txt"
        )
        temporary_path = self.temp_dir / filename
        temporary_path.write_bytes(body_text.encode(BODY_OUTPUT_ENCODING))
        relative_path = str(Path(self.snapshot_key) / filename)
        final_path = str((self.root / relative_path).resolve())
        self.saved_count += 1
        if qualifies:
            self.saved_qualifying_count += 1
        return True, relative_path, final_path

    def commit(self) -> None:
        """Replace the previous snapshot directory with the completed temp directory."""
        if self.temp_dir is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        if self.final_dir.exists():
            shutil.rmtree(self.final_dir)
        self.temp_dir.replace(self.final_dir)
        self.temp_dir = None

    def cleanup(self) -> None:
        """Remove an uncommitted temporary directory."""
        if self.temp_dir is not None:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    """Return a hexadecimal SHA-256 digest for bytes."""
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    """Return a UTF-8 SHA-256 digest for text."""
    return sha256_bytes(text.encode("utf-8"))


def sanitize_key(value: str, max_length: int = 120) -> str:
    """Create a stable identifier fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value).strip())
    cleaned = cleaned.strip("_.:-") or "unknown"
    return cleaned[:max_length]


def make_body_key(
    snapshot_key: str,
    path: str,
    record: FunctionRecord,
    raw_body_sha256: str,
) -> str:
    """Build a stable identifier for one extracted function occurrence."""
    raw = (
        f"{snapshot_key}|{path}|{record.qualified_name}|"
        f"{record.occurrence_index}|{record.start_line}|{record.end_line}|"
        f"{raw_body_sha256}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    """Build the stable repository-snapshot identifier used by run-x-b01."""
    raw = f"{dataset_source}|{repo_name.lower()}|{commit_sha.lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return (
        f"{sanitize_key(dataset_source, 16)}__"
        f"{sanitize_key(repo_name, 70)}__{commit_sha[:12].lower()}__{digest}"
    )


def run_text_command(
    command: list[str],
    *,
    check: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a text subprocess with captured output."""
    logging.debug("Running command: %s", " ".join(command))
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=check,
        timeout=timeout,
    )


def save_dataframe(frame: pd.DataFrame, path: Path) -> None:
    """Write one CSV atomically."""
    output_path = path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, quoting=csv.QUOTE_MINIMAL)
    temporary.replace(output_path)


def ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Add missing columns and return them in the requested order."""
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[columns].copy()


def detect_newline_style(payload: bytes) -> str:
    """Classify original source newline bytes without normalization."""
    crlf = payload.count(b"\r\n")
    remainder = payload.replace(b"\r\n", b"")
    lf = remainder.count(b"\n")
    cr = remainder.count(b"\r")
    kinds = sum(value > 0 for value in (crlf, lf, cr))
    if kinds == 0:
        return "none"
    if kinds > 1:
        return "mixed"
    if crlf:
        return "CRLF"
    if lf:
        return "LF"
    return "CR"


def decode_python_source(data: bytes) -> tuple[str, str]:
    """Decode Python source using PEP 263 encoding detection."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding), encoding
    except Exception as exc:
        raise StageError("source_decode", f"{type(exc).__name__}: {exc}") from exc


def normalize_input_manifest(raw: pd.DataFrame) -> pd.DataFrame:
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
    unexpected_sources = (
        set(manifest["dataset_source"].dropna().unique())
        - EXPECTED_DATASET_SOURCES
    )
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
            invalid_sha,
            ["dataset_source", "repo_name", "latest_commit_effective"],
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

    if manifest["repo_month_rows"].isna().any() or (
        manifest["repo_month_rows"] <= 0
    ).any():
        raise ValueError("repo_month_rows must be positive for every snapshot.")
    if manifest["python_file_count_all"].isna().any() or (
        manifest["python_file_count_all"] <= 0
    ).any():
        raise ValueError("Every snapshot must have at least one Python file.")
    if manifest["ncloc_model_a"].isna().any():
        raise ValueError("Model C manifest contains missing Model A NCLOC values.")

    duplicate_key = manifest.duplicated(
        ["dataset_source", "repo_name", "commit_sha"], keep=False
    )
    if duplicate_key.any():
        examples = manifest.loc[
            duplicate_key,
            ["dataset_source", "repo_name", "commit_sha"],
        ].head(10)
        raise ValueError(
            "Duplicate repository-snapshot keys were found:\n"
            + examples.to_string(index=False)
        )

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
    manifest["scan_scope"] = SCAN_SCOPE
    manifest["token_definition"] = TOKEN_DEFINITION
    manifest["token_min_inclusive"] = TOKEN_MIN
    manifest["token_max_inclusive"] = TOKEN_MAX
    manifest["function_scope_definition"] = FUNCTION_SCOPE_DEFINITION
    manifest["raw_body_definition"] = RAW_BODY_DEFINITION
    manifest["python_file_count_manifest"] = manifest[
        "python_file_count_all"
    ].round().astype("Int64")

    if manifest["snapshot_key"].duplicated().any():
        raise ValueError("Generated snapshot_key values are not unique.")
    return manifest


def expected_count_checks(
    manifest: pd.DataFrame, args: argparse.Namespace
) -> list[dict[str, Any]]:
    """Build structural input checks and optionally fail on mismatches."""
    role_counts = manifest["dataset_source"].value_counts().to_dict()
    role_coverage = (
        manifest.groupby("dataset_source")["repo_month_rows"]
        .sum()
        .astype(int)
        .to_dict()
    )
    role_repos = manifest.groupby("dataset_source")["repo_name"].nunique().to_dict()

    checks = [
        ("input_snapshot_rows", len(manifest), args.expected_snapshots),
        (
            "treatment_snapshots",
            int(role_counts.get("treatment", 0)),
            args.expected_treatment_snapshots,
        ),
        (
            "control_snapshots",
            int(role_counts.get("control", 0)),
            args.expected_control_snapshots,
        ),
        (
            "repo_month_coverage",
            int(manifest["repo_month_rows"].sum()),
            args.expected_repo_month_rows,
        ),
        (
            "treatment_repo_month_coverage",
            int(role_coverage.get("treatment", 0)),
            args.expected_treatment_repo_month_rows,
        ),
        (
            "control_repo_month_coverage",
            int(role_coverage.get("control", 0)),
            args.expected_control_repo_month_rows,
        ),
        (
            "unique_repositories",
            int(manifest["repo_name"].nunique()),
            args.expected_repositories,
        ),
        (
            "treatment_repositories",
            int(role_repos.get("treatment", 0)),
            args.expected_treatment_repositories,
        ),
        (
            "control_repositories",
            int(role_repos.get("control", 0)),
            args.expected_control_repositories,
        ),
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
        raise ValueError(
            "Strict expected-count checks failed: " + " | ".join(mismatches)
        )
    return records


def validate_git_snapshot(
    clone_path: Path, commit_sha: str, timeout_seconds: int
) -> tuple[bool, str]:
    """Validate that a clone exists and contains the requested commit."""
    if not clone_path.exists():
        return False, "clone_path_missing"
    try:
        run_text_command(
            ["git", "-C", str(clone_path), "rev-parse", "--git-dir"],
            timeout=timeout_seconds,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not_git_repository"
    try:
        run_text_command(
            [
                "git",
                "-C",
                str(clone_path),
                "cat-file",
                "-e",
                f"{commit_sha}^{{commit}}",
            ],
            timeout=timeout_seconds,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, "commit_not_found"
    return True, "ready"


def path_is_included_python(path_text: str) -> bool:
    """Apply the same Python suffix and directory exclusions as run-x-b01."""
    path = PurePosixPath(path_text)
    if not path.name.lower().endswith(".py"):
        return False
    return not any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts[:-1])


def list_python_blobs(
    clone_path: Path, commit_sha: str, timeout_seconds: int
) -> list[GitBlob]:
    """List tracked regular Python blobs without checking out the commit."""
    process = subprocess.run(
        [
            "git",
            "-C",
            str(clone_path),
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit_sha,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise StageError(
            "git_ls_tree",
            "git ls-tree failed: "
            + process.stderr.decode("utf-8", errors="replace").strip(),
        )

    blobs: list[GitBlob] = []
    for raw_entry in process.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode_b, object_type_b, oid_b = metadata.split(b" ", 2)
        except ValueError as exc:
            raise StageError(
                "git_ls_tree", f"Unexpected git ls-tree entry: {raw_entry!r}"
            ) from exc
        mode = mode_b.decode("ascii", errors="replace")
        object_type = object_type_b.decode("ascii", errors="replace")
        oid = oid_b.decode("ascii", errors="replace")
        path_text = os.fsdecode(raw_path)
        if object_type != "blob" or mode not in VALID_PYTHON_BLOB_MODES:
            continue
        if path_is_included_python(path_text):
            blobs.append(GitBlob(path=path_text, oid=oid, mode=mode))

    blobs.sort(key=lambda item: item.path)
    return blobs


def read_blob_batch(
    clone_path: Path, blobs: list[GitBlob], timeout_seconds: int
) -> dict[str, bytes]:
    """Read all unique Git blob objects with one cat-file process."""
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
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise StageError(
            "git_cat_file",
            "git cat-file --batch failed: "
            + process.stderr.decode("utf-8", errors="replace").strip(),
        )

    stream = io.BytesIO(process.stdout)
    contents: dict[str, bytes] = {}
    for requested_oid in unique_oids:
        header = stream.readline()
        if not header:
            raise StageError(
                "git_cat_file",
                f"git cat-file ended before returning blob {requested_oid}",
            )
        parts = header.rstrip(b"\n").split()
        if len(parts) >= 2 and parts[1] == b"missing":
            raise StageError(
                "git_cat_file", f"git cat-file reported missing blob {requested_oid}"
            )
        if len(parts) != 3 or parts[1] != b"blob":
            raise StageError(
                "git_cat_file", f"Unexpected git cat-file header: {header!r}"
            )
        returned_oid = parts[0].decode("ascii", errors="replace")
        size = int(parts[2])
        data = stream.read(size)
        terminator = stream.read(1)
        if len(data) != size or terminator != b"\n":
            raise StageError(
                "git_cat_file", f"Incomplete git cat-file payload for {requested_oid}"
            )
        contents[returned_oid] = data
    return contents


def statement_child_bodies(statement: ast.stmt) -> Iterator[Sequence[ast.stmt]]:
    """Yield statement lists nested in control-flow constructs."""
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(statement, field_name, None)
        if isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value):
            if value:
                yield value
    handlers = getattr(statement, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            if isinstance(handler, ast.ExceptHandler) and handler.body:
                yield handler.body
    cases = getattr(statement, "cases", None)
    if isinstance(cases, list):
        for case in cases:
            body = getattr(case, "body", None)
            if isinstance(body, list) and body:
                yield body


def contains_nested_named_definition(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return whether an outer function body contains a named nested definition."""
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return True
    return False


def function_kind(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    scope_kinds: Sequence[str],
) -> str:
    """Classify an eligible function occurrence."""
    is_async = isinstance(node, ast.AsyncFunctionDef)
    if scope_kinds and scope_kinds[-1] == "class":
        return "async_method" if is_async else "method"
    return "module_async_function" if is_async else "module_function"


def index_eligible_functions(source: str, filename: str) -> list[FunctionRecord]:
    """Index eligible functions using the interpreter executing the AST worker."""
    try:
        tree = ast.parse(source, filename=filename, type_comments=True)
    except IndentationError:
        raise
    except SyntaxError:
        raise
    except Exception as exc:
        raise StageError("raw_file_parse", f"{type(exc).__name__}: {exc}") from exc

    occurrence_counts: Counter[str] = Counter()
    records: list[FunctionRecord] = []

    def walk_statements(
        statements: Sequence[ast.stmt],
        scope_names: list[str],
        scope_kinds: list[str],
    ) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nested = "function" in scope_kinds
                qualified_name = ".".join([*scope_names, statement.name])
                occurrence_counts[qualified_name] += 1
                if not nested:
                    leading_docstring_removed = bool(
                        statement.body and is_docstring_statement(statement.body[0])
                    )
                    real_body = (
                        statement.body[1:]
                        if leading_docstring_removed
                        else statement.body
                    )
                    first_statement = real_body[0] if real_body else None
                    docstring_end_line = 0
                    if leading_docstring_removed:
                        docstring = statement.body[0]
                        docstring_end_line = int(
                            getattr(docstring, "end_lineno", docstring.lineno)
                        )
                    records.append(
                        FunctionRecord(
                            qualified_name=qualified_name,
                            function_name=statement.name,
                            function_kind=function_kind(statement, scope_kinds),
                            occurrence_index=occurrence_counts[qualified_name],
                            start_line=int(statement.lineno),
                            start_col=int(statement.col_offset),
                            end_line=int(
                                getattr(statement, "end_lineno", statement.lineno)
                            ),
                            end_col=int(
                                getattr(statement, "end_col_offset", statement.col_offset)
                            ),
                            first_statement_line=(
                                int(first_statement.lineno) if first_statement else 0
                            ),
                            first_statement_col=(
                                int(first_statement.col_offset) if first_statement else 0
                            ),
                            leading_docstring_removed=leading_docstring_removed,
                            docstring_end_line=docstring_end_line,
                            contains_nested_named_definition=(
                                contains_nested_named_definition(statement)
                            ),
                        )
                    )
                walk_statements(
                    statement.body,
                    [*scope_names, statement.name],
                    [*scope_kinds, "function"],
                )
            elif isinstance(statement, ast.ClassDef):
                walk_statements(
                    statement.body,
                    [*scope_names, statement.name],
                    [*scope_kinds, "class"],
                )
            else:
                for child_body in statement_child_bodies(statement):
                    walk_statements(child_body, scope_names, scope_kinds)

    walk_statements(tree.body, [], [])
    return records


def function_record_to_dict(record: FunctionRecord) -> dict[str, Any]:
    """Serialize one AST-worker function record."""
    return {
        field_name: getattr(record, field_name)
        for field_name in FunctionRecord.__dataclass_fields__
    }


def function_record_from_dict(payload: dict[str, Any]) -> FunctionRecord:
    """Deserialize one function record returned by the AST worker."""
    return FunctionRecord(
        qualified_name=str(payload["qualified_name"]),
        function_name=str(payload["function_name"]),
        function_kind=str(payload["function_kind"]),
        occurrence_index=int(payload["occurrence_index"]),
        start_line=int(payload["start_line"]),
        start_col=int(payload["start_col"]),
        end_line=int(payload["end_line"]),
        end_col=int(payload["end_col"]),
        first_statement_line=int(payload["first_statement_line"]),
        first_statement_col=int(payload["first_statement_col"]),
        leading_docstring_removed=bool(payload["leading_docstring_removed"]),
        docstring_end_line=int(payload["docstring_end_line"]),
        contains_nested_named_definition=bool(
            payload["contains_nested_named_definition"]
        ),
    )


def ast_worker_version_payload() -> dict[str, Any]:
    """Return AST-worker runtime metadata without importing third-party packages."""
    return {
        "protocol_version": AST_WORKER_PROTOCOL_VERSION,
        "python_version": sys.version.split()[0],
        "python_version_info": list(sys.version_info[:3]),
        "ast_module": getattr(ast, "__file__", "built-in"),
    }


def run_ast_worker_cli() -> int:
    """Read one batch request from stdin and emit per-file AST records as JSON."""
    request = json.load(sys.stdin)
    if request.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
        raise ValueError("Unsupported AST worker protocol version")

    output_files: list[dict[str, Any]] = []
    for item in request.get("files", []):
        request_index = int(item["request_index"])
        path = str(item["path"])
        try:
            source = base64.b64decode(item["source_utf8_b64"]).decode("utf-8")
            records = index_eligible_functions(source, path)
            output_files.append(
                {
                    "request_index": request_index,
                    "path": path,
                    "status": "success",
                    "error_type": "",
                    "error_message": "",
                    "records": [function_record_to_dict(record) for record in records],
                }
            )
        except Exception as exc:
            output_files.append(
                {
                    "request_index": request_index,
                    "path": path,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "records": [],
                }
            )

    response = {**ast_worker_version_payload(), "files": output_files}
    json.dump(response, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def inspect_ast_python(
    ast_python_bin: str,
    python_script_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Validate the external interpreter dedicated to Python 3.12 AST parsing."""
    process = subprocess.run(
        [ast_python_bin, str(python_script_path), "--ast-worker-version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "AST Python validation failed: "
            + (process.stderr.strip() or process.stdout.strip())
        )
    try:
        metadata = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AST Python returned invalid version JSON: {process.stdout[:500]}"
        ) from exc
    version_info = tuple(int(value) for value in metadata["python_version_info"][:2])
    if version_info < (3, 12):
        raise RuntimeError(
            "AST_PYTHON_BIN must provide Python 3.12 or later; "
            f"found {metadata.get('python_version', 'unknown')}"
        )
    if metadata.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
        raise RuntimeError("AST worker protocol mismatch")
    return metadata


def run_ast_worker_batch(
    decoded_files: list[dict[str, Any]],
    *,
    ast_python_bin: str,
    python_script_path: Path,
    timeout_seconds: int,
) -> dict[int, dict[str, Any]]:
    """Parse one snapshot's decoded sources in a Python 3.12 AST subprocess."""
    request = {
        "protocol_version": AST_WORKER_PROTOCOL_VERSION,
        "files": [
            {
                "request_index": int(item["request_index"]),
                "path": str(item["blob"].path),
                "source_utf8_b64": base64.b64encode(
                    str(item["source"]).encode("utf-8")
                ).decode("ascii"),
            }
            for item in decoded_files
        ],
    }
    process = subprocess.run(
        [ast_python_bin, str(python_script_path), "--ast-worker"],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise StageError(
            "ast_worker_process",
            process.stderr.strip() or process.stdout.strip() or (
                f"AST worker exited with code {process.returncode}"
            ),
        )
    try:
        response = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise StageError(
            "ast_worker_protocol",
            f"AST worker returned invalid JSON: {process.stdout[:500]}",
        ) from exc
    if response.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
        raise StageError("ast_worker_protocol", "AST worker protocol mismatch")
    return {int(item["request_index"]): item for item in response.get("files", [])}


def build_line_offsets(source: str) -> tuple[list[str], list[int], list[int]]:
    """Return physical source lines and absolute start/end offsets."""
    lines = source.splitlines(keepends=True)
    if not lines:
        lines = [""]
    starts: list[int] = []
    ends: list[int] = []
    cursor = 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line)
        ends.append(cursor)
    return lines, starts, ends


def utf8_byte_col_to_char_col(line: str, byte_col: int) -> int:
    """Convert an AST UTF-8 byte column to a Python character column."""
    if byte_col < 0:
        raise ValueError(f"Negative AST column offset: {byte_col}")
    payload = line.encode("utf-8")
    if byte_col > len(payload):
        raise ValueError(
            f"AST byte column {byte_col} exceeds UTF-8 line length {len(payload)}"
        )
    try:
        return len(payload[:byte_col].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"AST byte column splits a UTF-8 character: {byte_col}") from exc


def node_position_offset(
    source_lines: Sequence[str],
    line_starts: Sequence[int],
    lineno: int,
    utf8_byte_col: int,
) -> int:
    """Convert one AST source position to an absolute character offset."""
    if lineno < 1 or lineno > len(source_lines):
        raise ValueError(f"Line number outside source: {lineno}")
    char_col = utf8_byte_col_to_char_col(source_lines[lineno - 1], utf8_byte_col)
    return line_starts[lineno - 1] + char_col


def is_docstring_statement(statement: ast.stmt) -> bool:
    """Return whether one AST statement is a leading constant-string expression."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(getattr(statement, "value", None), ast.Constant)
        and isinstance(statement.value.value, str)
    )


def locate_function_suite_start(
    source: str,
    record: FunctionRecord,
    source_lines: Sequence[str],
    line_starts: Sequence[int],
    line_ends: Sequence[int],
) -> tuple[int, bool]:
    """Return raw suite start and whether the function uses block form.

    For a block function, the offset is immediately after the header's physical
    newline. This preserves comments, blank lines, indentation, and formatting
    before the first AST statement. For a one-line function, the offset is the
    first body statement's exact position, excluding separator spaces after the
    header colon.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except Exception as exc:
        raise StageError("function_boundary", f"Tokenization failed: {exc}") from exc

    node_line = int(record.start_line)
    node_char_col = utf8_byte_col_to_char_col(
        source_lines[node_line - 1], int(record.start_col)
    )

    def_index: Optional[int] = None
    for index, token_info in enumerate(tokens):
        if token_info.type == tokenize.NAME and token_info.string == "def":
            if token_info.start[0] == node_line and token_info.start[1] >= node_char_col:
                def_index = index
                break
    if def_index is None:
        raise StageError("function_boundary", "Could not locate function def token")

    bracket_depth = 0
    colon_index: Optional[int] = None
    for index in range(def_index + 1, len(tokens)):
        token_info = tokens[index]
        if token_info.type == tokenize.OP:
            if token_info.string in "([{":
                bracket_depth += 1
            elif token_info.string in ")]}":
                bracket_depth -= 1
            elif token_info.string == ":" and bracket_depth == 0:
                colon_index = index
                break
    if colon_index is None:
        raise StageError("function_boundary", "Could not locate function header colon")

    for token_info in tokens[colon_index + 1 :]:
        if token_info.type in {tokenize.ENCODING, tokenize.NL, tokenize.COMMENT}:
            continue
        if token_info.type == tokenize.NEWLINE:
            header_line = token_info.end[0]
            if header_line < len(line_starts):
                return line_starts[header_line], True
            return line_ends[header_line - 1], True
        if token_info.type in {tokenize.INDENT, tokenize.DEDENT}:
            continue
        absolute = line_starts[token_info.start[0] - 1] + token_info.start[1]
        return absolute, False

    raise StageError("function_boundary", "Could not locate function suite content")


def count_physical_lines(text: str) -> int:
    """Count physical lines in one raw body."""
    if not text:
        return 0
    return len(text.splitlines()) or 1


def extract_raw_implementation_body(
    source: str,
    record: FunctionRecord,
) -> ExtractedBody:
    """Extract one raw function body from Python 3.12 AST-worker boundaries."""
    if record.first_statement_line <= 0:
        raise StageError(
            "implementation_body_extract",
            "docstring_only_after_leading_docstring_removal",
        )

    lines, line_starts, line_ends = build_line_offsets(source)
    first_line = int(record.first_statement_line)
    suite_start, block_suite = locate_function_suite_start(
        source, record, lines, line_starts, line_ends
    )

    if record.leading_docstring_removed:
        docstring_end_line = int(record.docstring_end_line)
        if first_line == docstring_end_line:
            body_start = node_position_offset(
                lines,
                line_starts,
                first_line,
                int(record.first_statement_col),
            )
        else:
            if docstring_end_line < 1 or docstring_end_line > len(line_ends):
                raise StageError(
                    "docstring_boundary",
                    f"Docstring end line outside source: {docstring_end_line}",
                )
            body_start = line_ends[docstring_end_line - 1]
    else:
        body_start = suite_start
        if not block_suite:
            body_start = node_position_offset(
                lines,
                line_starts,
                first_line,
                int(record.first_statement_col),
            )

    end_line = int(record.end_line)
    if end_line < 1 or end_line > len(line_ends):
        raise StageError(
            "function_boundary", f"Function end line outside source: {end_line}"
        )
    function_end = line_ends[end_line - 1]

    function_start_line = int(record.start_line)
    if function_start_line < 1 or function_start_line > len(line_starts):
        raise StageError(
            "function_boundary",
            f"Function start line outside source: {function_start_line}",
        )
    function_start = line_starts[function_start_line - 1]

    if not (function_start <= body_start < function_end <= len(source)):
        raise StageError(
            "implementation_body_extract",
            (
                "Invalid source boundaries: "
                f"function_start={function_start}, body_start={body_start}, "
                f"function_end={function_end}, source_length={len(source)}"
            ),
        )

    raw_function_source = source[function_start:function_end]
    body_text = source[body_start:function_end]
    if not body_text or not body_text.strip():
        raise StageError("implementation_body_extract", "empty_body_after_extraction")

    body_start_line = source.count("\n", 0, body_start) + 1
    token_count = len(body_text.split(" "))
    return ExtractedBody(
        raw_function_source=raw_function_source,
        body_text=body_text,
        body_start_line=body_start_line,
        body_end_line=end_line,
        leading_docstring_removed=record.leading_docstring_removed,
        token_count=token_count,
    )


def load_existing_results(path: Path) -> pd.DataFrame:
    """Load prior D01 snapshot results for resume behavior."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    existing = pd.read_csv(input_path, low_memory=False)
    if "count_backend" not in existing.columns:
        raise ValueError(f"Existing result has no count_backend: {input_path}")
    if not existing["count_backend"].fillna("").eq(COUNT_BACKEND).all():
        raise ValueError("Existing result contains a different count backend.")
    if "snapshot_key" not in existing.columns:
        raise ValueError(f"Existing result has no snapshot_key: {input_path}")
    if existing["snapshot_key"].duplicated().any():
        raise ValueError("Existing result contains duplicate snapshot keys.")
    return ensure_columns(existing, RESULT_COLUMNS)


def load_existing_function_details(path: Path) -> pd.DataFrame:
    """Load prior function-level details."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame(columns=FUNCTION_DETAIL_COLUMNS)
    return ensure_columns(pd.read_csv(input_path, low_memory=False), FUNCTION_DETAIL_COLUMNS)


def load_existing_file_issues(path: Path) -> pd.DataFrame:
    """Load prior file-level issues."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame(columns=FILE_ISSUE_COLUMNS)
    return ensure_columns(pd.read_csv(input_path, low_memory=False), FILE_ISSUE_COLUMNS)


def load_resolution_decisions(path: Optional[Path]) -> pd.DataFrame:
    """Load optional manual snapshot-resolution decisions."""
    if path is None:
        return pd.DataFrame(columns=sorted(RESOLUTION_REQUIRED_COLUMNS))
    input_path = path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Resolution decisions file not found: {input_path}")
    frame = pd.read_csv(input_path, dtype=str).fillna("")
    missing = RESOLUTION_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Resolution file missing columns: {sorted(missing)}")
    frame["snapshot_key"] = frame["snapshot_key"].str.strip()
    frame["resolution_decision"] = frame["resolution_decision"].str.strip().str.lower()
    frame["resolution_note"] = frame["resolution_note"].str.strip()
    invalid = ~frame["resolution_decision"].isin(RESOLUTION_DECISIONS)
    if invalid.any():
        values = sorted(frame.loc[invalid, "resolution_decision"].unique())
        raise ValueError(f"Unsupported resolution decisions: {values}")
    if frame["snapshot_key"].duplicated().any():
        raise ValueError("Resolution file contains duplicate snapshot_key values.")
    return frame[["snapshot_key", "resolution_decision", "resolution_note"]].copy()


def prior_attempt_count(existing: pd.DataFrame, snapshot_key: str) -> int:
    """Return the previous attempt count for one snapshot."""
    if existing.empty:
        return 0
    rows = existing[existing["snapshot_key"].astype(str).eq(snapshot_key)]
    if rows.empty:
        return 0
    value = pd.to_numeric(rows.iloc[-1].get("scan_attempt"), errors="coerce")
    return int(value) if pd.notna(value) else 0


def base_result_row(manifest_row: pd.Series, scan_attempt: int) -> dict[str, Any]:
    """Create a complete snapshot result with default values."""
    return {
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
        "implementation_version": IMPLEMENTATION_VERSION,
        "experiment_name": EXPERIMENT_NAME,
        "count_backend": COUNT_BACKEND,
        "scan_scope": SCAN_SCOPE,
        "token_definition": TOKEN_DEFINITION,
        "token_min_inclusive": TOKEN_MIN,
        "token_max_inclusive": TOKEN_MAX,
        "function_scope_definition": FUNCTION_SCOPE_DEFINITION,
        "raw_body_definition": RAW_BODY_DEFINITION,
        "main_python_version": sys.version.split()[0],
        "ast_python_bin": "",
        "ast_python_version": "",
        "ast_worker_protocol_version": AST_WORKER_PROTOCOL_VERSION,
        "ast_worker_timeout_seconds": pd.NA,
        "body_store_root": "",
        "body_save_scope": "",
        "body_store_snapshot_dir": "",
        "body_files_saved": 0,
        "body_files_saved_100_200": 0,
        "scan_attempt": scan_attempt,
        "scan_started_at": utc_now(),
        "scan_completed_at": "",
        "runtime_seconds": pd.NA,
        "git_precheck_status": "pending",
        "python_file_count_manifest": int(manifest_row["python_file_count_manifest"]),
        "python_file_count_git": pd.NA,
        "python_file_count_matches_manifest": pd.NA,
        "git_blob_count": pd.NA,
        "git_blob_bytes": pd.NA,
        "decoded_python_file_count": 0,
        "parsed_python_file_count": 0,
        "failed_python_file_count": 0,
        "decode_failed_file_count": 0,
        "syntax_error_file_count": 0,
        "indentation_error_file_count": 0,
        "tokenize_error_file_count": 0,
        "other_parse_failed_file_count": 0,
        "function_count_py_all_partial": 0,
        "function_count_py_extracted_partial": 0,
        "function_count_py_100_200_partial": 0,
        "function_count_py_docstring_only_partial": 0,
        "function_count_py_boundary_failed_partial": 0,
        "function_count_py_with_nested_partial": 0,
        "python_file_count_with_function_partial": 0,
        "python_file_count_with_function_100_200_partial": 0,
        "token_py_all_function_bodies_partial": 0,
        "token_py_100_200_partial": 0,
        "function_count_py_all": pd.NA,
        "function_count_py_extracted": pd.NA,
        "function_count_py_100_200": pd.NA,
        "function_count_py_docstring_only": pd.NA,
        "function_count_py_with_nested": pd.NA,
        "python_file_count_with_function": pd.NA,
        "python_file_count_with_function_100_200": pd.NA,
        "token_py_all_function_bodies": pd.NA,
        "token_py_100_200": pd.NA,
        "metric_available": False,
        "snapshot_status": "pending",
        "resolution_decision": "not_needed",
        "resolution_note": "",
        "partial_metric_accepted": False,
        "error_stage": "",
        "error_message": "",
    }


def upsert_result(existing: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
    """Insert or replace one snapshot result."""
    row = pd.DataFrame([{column: result.get(column, pd.NA) for column in RESULT_COLUMNS}])
    remaining = existing[
        existing["snapshot_key"].astype(str) != str(result["snapshot_key"])
    ].copy()
    return pd.concat([remaining, row], ignore_index=True, sort=False)[RESULT_COLUMNS]


def replace_snapshot_rows(
    existing: pd.DataFrame,
    snapshot_key: str,
    incoming_rows: list[dict[str, Any]],
    columns: list[str],
) -> pd.DataFrame:
    """Replace all detail or issue rows for one snapshot."""
    if existing.empty:
        remaining = pd.DataFrame(columns=columns)
    else:
        remaining = existing[
            existing["snapshot_key"].astype(str) != snapshot_key
        ].copy()
    if not incoming_rows:
        return ensure_columns(remaining, columns)
    incoming = ensure_columns(pd.DataFrame(incoming_rows), columns)
    return pd.concat([remaining, incoming], ignore_index=True, sort=False)[columns]


def add_file_issue(
    issues: list[dict[str, Any]],
    result: dict[str, Any],
    blob: Optional[GitBlob],
    blob_size: Any,
    stage: str,
    error: BaseException,
) -> None:
    """Append one normalized source issue."""
    issues.append(
        {
            "snapshot_key": result["snapshot_key"],
            "dataset_source": result["dataset_source"],
            "repo_name": result["repo_name"],
            "commit_sha": result["commit_sha"],
            "path": blob.path if blob else "",
            "blob_oid": blob.oid if blob else "",
            "blob_size": blob_size,
            "issue_stage": stage,
            "issue_type": getattr(error, "issue_type", type(error).__name__),
            "issue_message": str(error),
            "requires_review": True,
        }
    )


def blank_function_detail(
    result: dict[str, Any],
    blob: GitBlob,
    blob_size: int,
    source_encoding: str,
    newline_style: str,
    record: FunctionRecord,
) -> dict[str, Any]:
    """Create one function-detail row before extraction."""
    return {
        "manifest_order": result["manifest_order"],
        "snapshot_key": result["snapshot_key"],
        "dataset_source": result["dataset_source"],
        "repo_name": result["repo_name"],
        "commit_sha": result["commit_sha"],
        "path": blob.path,
        "blob_oid": blob.oid,
        "blob_size": blob_size,
        "source_encoding": source_encoding,
        "newline_style": newline_style,
        "qualified_name": record.qualified_name,
        "function_name": record.function_name,
        "function_kind": record.function_kind,
        "occurrence_index": record.occurrence_index,
        "function_start_line": record.start_line,
        "function_end_line": record.end_line,
        "body_start_line": pd.NA,
        "body_end_line": pd.NA,
        "leading_docstring_removed": pd.NA,
        "contains_nested_named_definition": record.contains_nested_named_definition,
        "raw_function_sha256": "",
        "raw_body_sha256": "",
        "raw_body_character_count": pd.NA,
        "raw_body_utf8_byte_count": pd.NA,
        "raw_body_physical_line_count": pd.NA,
        "body_key": "",
        "body_saved": False,
        "body_output_encoding": BODY_OUTPUT_ENCODING,
        "body_output_relative_path": "",
        "body_output_path": "",
        "token_count": pd.NA,
        "qualifies_100_200": False,
        "extraction_status": "pending",
        "exclusion_reason": "",
    }


def apply_resolution(
    result: dict[str, Any], resolution_map: dict[str, tuple[str, str]]
) -> None:
    """Finalize metric availability using automatic or manual resolution."""
    snapshot_key = str(result["snapshot_key"])
    failed_files = int(result["failed_python_file_count"])
    boundary_failures = int(result["function_count_py_boundary_failed_partial"])
    complete = failed_files == 0 and boundary_failures == 0

    if complete:
        for final_name, partial_name in [
            ("function_count_py_all", "function_count_py_all_partial"),
            ("function_count_py_extracted", "function_count_py_extracted_partial"),
            ("function_count_py_100_200", "function_count_py_100_200_partial"),
            (
                "function_count_py_docstring_only",
                "function_count_py_docstring_only_partial",
            ),
            ("function_count_py_with_nested", "function_count_py_with_nested_partial"),
            (
                "python_file_count_with_function",
                "python_file_count_with_function_partial",
            ),
            (
                "python_file_count_with_function_100_200",
                "python_file_count_with_function_100_200_partial",
            ),
            (
                "token_py_all_function_bodies",
                "token_py_all_function_bodies_partial",
            ),
            ("token_py_100_200", "token_py_100_200_partial"),
        ]:
            result[final_name] = int(result[partial_name])
        result["metric_available"] = True
        result["snapshot_status"] = "success"
        result["resolution_decision"] = "not_needed"
        result["resolution_note"] = ""
        result["partial_metric_accepted"] = False
        result["error_stage"] = ""
        result["error_message"] = ""
        return

    decision, note = resolution_map.get(snapshot_key, ("pending_review", ""))
    result["resolution_decision"] = decision
    result["resolution_note"] = note
    result["snapshot_status"] = "partial_needs_review"
    result["metric_available"] = False
    result["partial_metric_accepted"] = False
    result["error_stage"] = "source_or_boundary_failure"
    result["error_message"] = (
        f"failed_python_files={failed_files}; boundary_failures={boundary_failures}"
    )

    if decision == "accept_partial":
        for final_name, partial_name in [
            ("function_count_py_all", "function_count_py_all_partial"),
            ("function_count_py_extracted", "function_count_py_extracted_partial"),
            ("function_count_py_100_200", "function_count_py_100_200_partial"),
            (
                "function_count_py_docstring_only",
                "function_count_py_docstring_only_partial",
            ),
            ("function_count_py_with_nested", "function_count_py_with_nested_partial"),
            (
                "python_file_count_with_function",
                "python_file_count_with_function_partial",
            ),
            (
                "python_file_count_with_function_100_200",
                "python_file_count_with_function_100_200_partial",
            ),
            (
                "token_py_all_function_bodies",
                "token_py_all_function_bodies_partial",
            ),
            ("token_py_100_200", "token_py_100_200_partial"),
        ]:
            result[final_name] = int(result[partial_name])
        result["metric_available"] = True
        result["snapshot_status"] = "partial_accepted"
        result["partial_metric_accepted"] = True
    elif decision == "resolved_full":
        result["snapshot_status"] = "resolution_inconsistent"
        result["error_message"] += "; resolution says resolved_full but failures remain"
    elif decision == "exclude":
        result["snapshot_status"] = "excluded_after_review"


def run_snapshot(
    manifest_row: pd.Series,
    *,
    existing_results: pd.DataFrame,
    git_timeout_seconds: int,
    resolution_map: dict[str, tuple[str, str]],
    body_store_root: Path,
    body_save_scope: str,
    ast_python_bin: str,
    ast_python_version: str,
    ast_worker_timeout_seconds: int,
    python_script_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Measure one historical snapshot with AST parsing delegated to Python 3.12."""
    snapshot_key = str(manifest_row["snapshot_key"])
    clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
    commit_sha = str(manifest_row["commit_sha"]).lower()
    result = base_result_row(
        manifest_row,
        scan_attempt=prior_attempt_count(existing_results, snapshot_key) + 1,
    )
    result["ast_python_bin"] = ast_python_bin
    result["ast_python_version"] = ast_python_version
    result["ast_worker_timeout_seconds"] = ast_worker_timeout_seconds
    details: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    partial = SnapshotPartialMetrics()
    started = time.monotonic()
    body_store = SnapshotBodyStore(body_store_root, snapshot_key, body_save_scope)
    result["body_store_root"] = str(body_store.root)
    result["body_save_scope"] = body_save_scope
    result["body_store_snapshot_dir"] = str(body_store.final_dir)

    try:
        ready, precheck_status = validate_git_snapshot(
            clone_path, commit_sha, git_timeout_seconds
        )
        result["git_precheck_status"] = precheck_status
        if not ready:
            result["snapshot_status"] = precheck_status
            result["resolution_decision"] = "pending_review"
            result["error_stage"] = "git_precheck"
            result["error_message"] = precheck_status
            add_file_issue(
                issues,
                result,
                None,
                pd.NA,
                "git_precheck",
                StageError("git_precheck", precheck_status),
            )
            return result, details, issues

        blobs = list_python_blobs(clone_path, commit_sha, git_timeout_seconds)
        result["python_file_count_git"] = len(blobs)
        result["python_file_count_matches_manifest"] = (
            len(blobs) == int(result["python_file_count_manifest"])
        )
        result["git_blob_count"] = len(blobs)
        if not blobs:
            result["snapshot_status"] = "no_python_files"
            result["resolution_decision"] = "pending_review"
            result["error_stage"] = "git_ls_tree"
            result["error_message"] = "No included tracked Python blobs were found."
            add_file_issue(
                issues,
                result,
                None,
                pd.NA,
                "git_ls_tree",
                StageError("git_ls_tree", result["error_message"]),
            )
            return result, details, issues

        blob_contents = read_blob_batch(clone_path, blobs, git_timeout_seconds)
        result["git_blob_bytes"] = sum(len(blob_contents[blob.oid]) for blob in blobs)
        body_store.start()

        decoded_files: list[dict[str, Any]] = []
        for request_index, blob in enumerate(blobs):
            data = blob_contents[blob.oid]
            try:
                source, source_encoding = decode_python_source(data)
                partial.decoded_python_file_count += 1
                decoded_files.append(
                    {
                        "request_index": request_index,
                        "blob": blob,
                        "data": data,
                        "source": source,
                        "source_encoding": source_encoding,
                        "newline_style": detect_newline_style(data),
                    }
                )
            except StageError as exc:
                partial.failed_python_file_count += 1
                partial.decode_failed_file_count += 1
                add_file_issue(issues, result, blob, len(data), exc.stage, exc)

        worker_results: dict[int, dict[str, Any]] = {}
        if decoded_files:
            try:
                worker_results = run_ast_worker_batch(
                    decoded_files,
                    ast_python_bin=ast_python_bin,
                    python_script_path=python_script_path,
                    timeout_seconds=ast_worker_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise StageError(
                    "ast_worker_timeout",
                    f"AST worker exceeded {ast_worker_timeout_seconds} seconds",
                ) from exc

        for item in decoded_files:
            request_index = int(item["request_index"])
            blob = item["blob"]
            data = item["data"]
            source = item["source"]
            source_encoding = item["source_encoding"]
            newline_style = item["newline_style"]
            worker_item = worker_results.get(request_index)
            if worker_item is None:
                partial.failed_python_file_count += 1
                partial.other_parse_failed_file_count += 1
                error = AstWorkerFileError(
                    "ast_worker_protocol",
                    "MissingAstWorkerResult",
                    f"No AST worker result for request index {request_index}",
                )
                add_file_issue(
                    issues, result, blob, len(data), error.stage, error
                )
                continue

            if worker_item.get("status") != "success":
                partial.failed_python_file_count += 1
                issue_type = str(worker_item.get("error_type", "AstWorkerError"))
                message = str(worker_item.get("error_message", "AST parsing failed"))
                if issue_type == "IndentationError":
                    partial.indentation_error_file_count += 1
                elif issue_type == "SyntaxError":
                    partial.syntax_error_file_count += 1
                elif issue_type == "TokenError":
                    partial.tokenize_error_file_count += 1
                else:
                    partial.other_parse_failed_file_count += 1
                error = AstWorkerFileError("raw_file_parse", issue_type, message)
                add_file_issue(issues, result, blob, len(data), error.stage, error)
                continue

            records = [
                function_record_from_dict(record_payload)
                for record_payload in worker_item.get("records", [])
            ]
            partial.parsed_python_file_count += 1
            if records:
                partial.python_file_count_with_function += 1
            partial.function_count_py_all += len(records)
            partial.function_count_py_with_nested += sum(
                int(record.contains_nested_named_definition) for record in records
            )
            file_has_qualifying = False

            for record in records:
                detail = blank_function_detail(
                    result,
                    blob,
                    len(data),
                    source_encoding,
                    newline_style,
                    record,
                )
                try:
                    extracted = extract_raw_implementation_body(source, record)
                    qualifies = TOKEN_MIN <= extracted.token_count <= TOKEN_MAX
                    raw_body_sha256 = sha256_text(extracted.body_text)
                    body_key = make_body_key(
                        snapshot_key, blob.path, record, raw_body_sha256
                    )
                    body_saved, body_relative_path, body_output_path = body_store.save(
                        body_key=body_key,
                        body_text=extracted.body_text,
                        token_count=extracted.token_count,
                        start_line=extracted.body_start_line,
                        end_line=extracted.body_end_line,
                        qualifies=qualifies,
                    )
                    detail.update(
                        {
                            "body_start_line": extracted.body_start_line,
                            "body_end_line": extracted.body_end_line,
                            "leading_docstring_removed": (
                                extracted.leading_docstring_removed
                            ),
                            "raw_function_sha256": sha256_text(
                                extracted.raw_function_source
                            ),
                            "raw_body_sha256": raw_body_sha256,
                            "raw_body_character_count": len(extracted.body_text),
                            "raw_body_utf8_byte_count": len(
                                extracted.body_text.encode(BODY_OUTPUT_ENCODING)
                            ),
                            "raw_body_physical_line_count": count_physical_lines(
                                extracted.body_text
                            ),
                            "body_key": body_key,
                            "body_saved": body_saved,
                            "body_output_encoding": BODY_OUTPUT_ENCODING,
                            "body_output_relative_path": body_relative_path,
                            "body_output_path": body_output_path,
                            "token_count": extracted.token_count,
                            "qualifies_100_200": qualifies,
                            "extraction_status": "success",
                            "exclusion_reason": "",
                        }
                    )
                    partial.function_count_py_extracted += 1
                    partial.token_py_all_function_bodies += extracted.token_count
                    if qualifies:
                        partial.function_count_py_100_200 += 1
                        partial.token_py_100_200 += extracted.token_count
                        file_has_qualifying = True
                except StageError as exc:
                    if "docstring_only" in str(exc) or "empty_body" in str(exc):
                        partial.function_count_py_docstring_only += 1
                        detail["extraction_status"] = "no_body_after_docstring"
                        detail["exclusion_reason"] = str(exc)
                    else:
                        partial.function_count_py_boundary_failed += 1
                        detail["extraction_status"] = "boundary_failed"
                        detail["exclusion_reason"] = str(exc)
                        add_file_issue(issues, result, blob, len(data), exc.stage, exc)
                except Exception as exc:
                    partial.function_count_py_boundary_failed += 1
                    detail["extraction_status"] = "boundary_failed"
                    detail["exclusion_reason"] = str(exc)
                    add_file_issue(
                        issues,
                        result,
                        blob,
                        len(data),
                        "implementation_body_extract",
                        exc,
                    )
                details.append(detail)

            if file_has_qualifying:
                partial.python_file_count_with_function_100_200 += 1

        for name in [
            "decoded_python_file_count",
            "parsed_python_file_count",
            "failed_python_file_count",
            "decode_failed_file_count",
            "syntax_error_file_count",
            "indentation_error_file_count",
            "tokenize_error_file_count",
            "other_parse_failed_file_count",
        ]:
            result[name] = int(getattr(partial, name))

        for name in [
            "function_count_py_all",
            "function_count_py_extracted",
            "function_count_py_100_200",
            "function_count_py_docstring_only",
            "function_count_py_boundary_failed",
            "function_count_py_with_nested",
            "python_file_count_with_function",
            "python_file_count_with_function_100_200",
            "token_py_all_function_bodies",
            "token_py_100_200",
        ]:
            result[f"{name}_partial"] = int(getattr(partial, name))

        result["body_files_saved"] = body_store.saved_count
        result["body_files_saved_100_200"] = body_store.saved_qualifying_count
        apply_resolution(result, resolution_map)
        return result, details, issues
    except subprocess.TimeoutExpired as exc:
        result["snapshot_status"] = "git_timeout"
        result["resolution_decision"] = "pending_review"
        result["error_stage"] = "git_object_read"
        result["error_message"] = str(exc)
        add_file_issue(issues, result, None, pd.NA, "git_object_read", exc)
        return result, details, issues
    except Exception as exc:
        logging.exception(
            "Snapshot measurement failed for %s at %s",
            result["repo_name"],
            commit_sha,
        )
        stage = getattr(exc, "stage", "snapshot_measurement")
        result["snapshot_status"] = "measurement_failed"
        result["resolution_decision"] = "pending_review"
        result["error_stage"] = stage
        result["error_message"] = str(exc)
        add_file_issue(issues, result, None, pd.NA, stage, exc)
        return result, details, issues
    finally:
        if body_store.temp_dir is not None:
            try:
                body_store.commit()
                result["body_files_saved"] = body_store.saved_count
                result["body_files_saved_100_200"] = (
                    body_store.saved_qualifying_count
                )
            except Exception as exc:
                body_store.cleanup()
                result["metric_available"] = False
                result["snapshot_status"] = "body_store_failed"
                result["resolution_decision"] = "pending_review"
                result["error_stage"] = "body_store"
                result["error_message"] = str(exc)
                add_file_issue(issues, result, None, pd.NA, "body_store", exc)
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)


def build_unresolved(results: pd.DataFrame) -> pd.DataFrame:
    """Build a review queue for unavailable or manually accepted metrics."""
    if results.empty:
        return results.copy()
    mask = (
        ~results["metric_available"].fillna(False).astype(bool)
        | results["partial_metric_accepted"].fillna(False).astype(bool)
    )
    columns = [
        "manifest_order",
        "snapshot_key",
        "dataset_source",
        "repo_name",
        "commit_sha",
        "python_file_count_git",
        "failed_python_file_count",
        "function_count_py_boundary_failed_partial",
        "token_py_100_200_partial",
        "token_py_100_200",
        "metric_available",
        "snapshot_status",
        "resolution_decision",
        "resolution_note",
        "partial_metric_accepted",
        "error_stage",
        "error_message",
    ]
    return results.loc[mask, columns].sort_values("manifest_order").reset_index(drop=True)


def build_qc_and_summary(
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    details: pd.DataFrame,
    issues: pd.DataFrame,
    structural_checks: list[dict[str, Any]],
    counters: RunCounters,
    *,
    dry_run: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build check-oriented QC and long-form summary outputs."""
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

    duplicate_results = int(results["snapshot_key"].duplicated().sum())
    manifest_keys = set(manifest["snapshot_key"].astype(str))
    result_keys = set(results["snapshot_key"].dropna().astype(str))
    orphan_results = len(result_keys - manifest_keys)
    available = results["metric_available"].fillna(False).astype(bool)
    unavailable_count = int((~available).sum())
    partial_accepted = int(
        results["partial_metric_accepted"].fillna(False).astype(bool).sum()
    )
    negative_metric = int(
        (
            pd.to_numeric(
                results.loc[available, "token_py_100_200"], errors="coerce"
            )
            < 0
        ).sum()
    )
    out_of_range_qualifiers = 0
    if not details.empty:
        token_values = pd.to_numeric(details["token_count"], errors="coerce")
        qualifier = details["qualifies_100_200"].fillna(False).astype(bool)
        out_of_range_qualifiers = int(
            (qualifier & ~token_values.between(TOKEN_MIN, TOKEN_MAX, inclusive="both")).sum()
        )
    nested_kinds = 0
    if not details.empty:
        nested_kinds = int(
            details["function_kind"].astype(str).str.contains("nested", case=False).sum()
        )
    manifest_file_mismatches = int(
        results["python_file_count_matches_manifest"].eq(False).fillna(False).sum()
    )
    issue_snapshots = int(issues["snapshot_key"].nunique()) if not issues.empty else 0
    available_coverage = int(results.loc[available, "repo_month_rows"].sum())
    result_saved_bodies = int(
        pd.to_numeric(results["body_files_saved"], errors="coerce").fillna(0).sum()
    )
    detail_saved_mask = (
        details["body_saved"].fillna(False).astype(bool)
        if not details.empty
        else pd.Series(dtype=bool)
    )
    detail_saved_bodies = int(detail_saved_mask.sum())
    missing_saved_body_files = 0
    if not details.empty and detail_saved_bodies > 0:
        saved_paths = details.loc[detail_saved_mask, "body_output_path"].fillna("")
        missing_saved_body_files = int(
            sum(1 for value in saved_paths if not value or not Path(str(value)).is_file())
        )

    add_check(
        "result_rows",
        "pass" if len(results) == len(manifest) and not dry_run else "warn",
        len(results),
        len(manifest),
    )
    add_check(
        "duplicate_result_snapshot_keys",
        "pass" if duplicate_results == 0 else "fail",
        duplicate_results,
        0,
    )
    add_check(
        "orphan_result_snapshot_keys",
        "pass" if orphan_results == 0 else "fail",
        orphan_results,
        0,
    )
    add_check(
        "negative_token_py_100_200",
        "pass" if negative_metric == 0 else "fail",
        negative_metric,
        0,
    )
    add_check(
        "qualifying_function_out_of_range",
        "pass" if out_of_range_qualifiers == 0 else "fail",
        out_of_range_qualifiers,
        0,
    )
    add_check(
        "nested_functions_as_separate_occurrences",
        "pass" if nested_kinds == 0 else "fail",
        nested_kinds,
        0,
    )
    add_check(
        "manifest_vs_git_python_file_mismatches",
        "warn" if manifest_file_mismatches > 0 else "pass",
        manifest_file_mismatches,
        0,
    )
    add_check(
        "snapshots_with_source_or_boundary_issues",
        "warn" if issue_snapshots > 0 else "pass",
        issue_snapshots,
        0,
    )
    add_check(
        "unavailable_snapshot_metrics",
        "warn" if unavailable_count > 0 else "pass",
        unavailable_count,
        0,
    )
    add_check(
        "manually_accepted_partial_metrics",
        "warn" if partial_accepted > 0 else "pass",
        partial_accepted,
        0,
    )
    add_check(
        "available_repo_month_coverage",
        "pass"
        if available_coverage == int(manifest["repo_month_rows"].sum()) and not dry_run
        else "warn",
        available_coverage,
        int(manifest["repo_month_rows"].sum()) if not dry_run else "dry_run",
    )
    add_check(
        "body_file_count_matches_function_details",
        "pass" if result_saved_bodies == detail_saved_bodies else "fail",
        result_saved_bodies,
        detail_saved_bodies,
    )
    add_check(
        "missing_saved_body_files",
        "pass" if missing_saved_body_files == 0 else "fail",
        missing_saved_body_files,
        0,
    )

    summary_records: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_records.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    add_summary("implementation", "experiment", EXPERIMENT_NAME)
    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "main_python_version", sys.version.split()[0])
    add_summary(
        "implementation",
        "ast_python_bin",
        str(results["ast_python_bin"].dropna().astype(str).replace("", pd.NA).dropna().iloc[0])
        if not results.empty and results["ast_python_bin"].dropna().astype(str).replace("", pd.NA).dropna().size
        else "",
    )
    add_summary(
        "implementation",
        "ast_python_version",
        str(results["ast_python_version"].dropna().astype(str).replace("", pd.NA).dropna().iloc[0])
        if not results.empty and results["ast_python_version"].dropna().astype(str).replace("", pd.NA).dropna().size
        else "",
    )
    add_summary("implementation", "ast_worker_protocol_version", AST_WORKER_PROTOCOL_VERSION)
    add_summary("definition", "count_backend", COUNT_BACKEND)
    add_summary("definition", "scan_scope", SCAN_SCOPE)
    add_summary("definition", "token_definition", TOKEN_DEFINITION)
    add_summary("definition", "token_min_inclusive", TOKEN_MIN)
    add_summary("definition", "token_max_inclusive", TOKEN_MAX)
    add_summary("definition", "function_scope", FUNCTION_SCOPE_DEFINITION)
    add_summary("definition", "raw_body", RAW_BODY_DEFINITION)
    add_summary("definition", "body_output_encoding", BODY_OUTPUT_ENCODING)
    add_summary("definition", "nested_function_deduplication", "none_as_occurrence")
    add_summary("definition", "tracked_path_deduplication", "none")
    add_summary("definition", "body_content_deduplication", "none")
    add_summary("definition", "added_or_modified_filter", "none_snapshot_stock_metric")
    add_summary("definition", "strip_applied", 0)
    add_summary("definition", "dedent_applied", 0)
    add_summary("definition", "empty_split_fields_counted", 1)
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
    if not results.empty:
        add_summary(
            "body_store",
            "body_store_root",
            str(results["body_store_root"].dropna().astype(str).replace("", pd.NA).dropna().iloc[0])
            if results["body_store_root"].dropna().astype(str).replace("", pd.NA).dropna().size
            else "",
        )
        add_summary(
            "body_store",
            "body_save_scope",
            str(results["body_save_scope"].dropna().astype(str).replace("", pd.NA).dropna().iloc[0])
            if results["body_save_scope"].dropna().astype(str).replace("", pd.NA).dropna().size
            else "",
        )
        add_summary(
            "body_store",
            "body_files_saved",
            int(pd.to_numeric(results["body_files_saved"], errors="coerce").fillna(0).sum()),
        )
        add_summary(
            "body_store",
            "body_files_saved_100_200",
            int(pd.to_numeric(results["body_files_saved_100_200"], errors="coerce").fillna(0).sum()),
        )
    add_summary("run", "processed_this_run", counters.processed_this_run)
    add_summary("run", "skipped_existing_success", counters.skipped_existing_success)
    add_summary("run", "successful_this_run", counters.successful_this_run)
    add_summary("run", "partial_this_run", counters.partial_this_run)
    add_summary("run", "failed_this_run", counters.failed_this_run)
    add_summary("result", "available_snapshots", int(available.sum()))
    add_summary("result", "unavailable_snapshots", unavailable_count)
    add_summary("result", "partial_accepted_snapshots", partial_accepted)
    add_summary("result", "available_repo_month_coverage", available_coverage)
    add_summary("result", "function_detail_rows", len(details))
    add_summary("result", "file_issue_rows", len(issues))
    add_summary("result", "file_issue_snapshots", issue_snapshots)

    if available.any():
        for metric in [
            "token_py_100_200",
            "function_count_py_100_200",
            "token_py_all_function_bodies",
            "function_count_py_all",
        ]:
            values = pd.to_numeric(results.loc[available, metric], errors="coerce").dropna()
            add_summary(metric, "min", values.min() if not values.empty else "")
            add_summary(metric, "median", values.median() if not values.empty else "")
            add_summary(metric, "mean", values.mean() if not values.empty else "")
            add_summary(metric, "max", values.max() if not values.empty else "")

    status_counts = results["snapshot_status"].fillna("missing").value_counts()
    for status, count in status_counts.items():
        add_summary("snapshot_status", str(status), int(count))

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
        raise ValueError("No snapshots matched the requested filters.")
    return selected.copy()


def progress_message(
    position: int,
    total: int,
    counters: RunCounters,
    run_started: float,
) -> str:
    """Build one compact progress message."""
    elapsed = max(time.monotonic() - run_started, 0.001)
    completed = counters.processed_this_run + counters.skipped_existing_success
    rate = completed / elapsed * 3600 if completed else 0.0
    remaining = max(total - completed, 0)
    eta = remaining / rate if rate > 0 else float("nan")
    eta_text = f"{eta:.2f}" if eta == eta else "unknown"
    return (
        f"Progress: {completed}/{total}; position={position}; "
        f"processed={counters.processed_this_run}; "
        f"skipped_success={counters.skipped_existing_success}; "
        f"success={counters.successful_this_run}; "
        f"partial={counters.partial_this_run}; failed={counters.failed_this_run}; "
        f"rate_snapshots_per_hour={rate:.2f}; eta_hours={eta_text}"
    )


def run_internal_self_test(
    ast_python_bin: str,
    python_script_path: Path,
    timeout_seconds: int,
) -> None:
    """Verify AST-worker indexing and raw-body extraction boundary rules."""
    source = (
        "def with_comment():\n"
        "    # comment\n"
        "    x  = 1\n"
        "    return x\n"
        "\n"
        "def one_line():   return  value  # inline\n"
        "\n"
        "def with_doc():\n"
        "    \"\"\"Docstring.\"\"\"\n"
        "\n"
        "    # implementation\n"
        "    return 1\n"
        "\n"
        "async def outer_async():\n"
        "    def nested():\n"
        "        return 2\n"
        "    return nested()\n"
        "\n"
        "class C:\n"
        "    async def method(self):\n"
        "        return 3\n"
        "\n"
        "def doc_only():\n"
        "    \"\"\"Only documentation.\"\"\"\n"
    )
    decoded_files = [
        {
            "request_index": 0,
            "blob": GitBlob(path="self_test.py", oid="0" * 40, mode="100644"),
            "source": source,
        }
    ]
    response = run_ast_worker_batch(
        decoded_files,
        ast_python_bin=ast_python_bin,
        python_script_path=python_script_path,
        timeout_seconds=timeout_seconds,
    )[0]
    assert response["status"] == "success", response
    records = [function_record_from_dict(item) for item in response["records"]]
    names = [record.qualified_name for record in records]
    assert names == [
        "with_comment",
        "one_line",
        "with_doc",
        "outer_async",
        "C.method",
        "doc_only",
    ], names
    assert "outer_async.nested" not in names

    by_name = {record.qualified_name: record for record in records}
    comment_body = extract_raw_implementation_body(source, by_name["with_comment"])
    assert comment_body.body_text.startswith("    # comment\n")
    assert "x  = 1" in comment_body.body_text

    one_line = extract_raw_implementation_body(source, by_name["one_line"])
    assert one_line.body_text.startswith("return  value")
    assert not one_line.body_text.startswith(" ")
    assert "# inline" in one_line.body_text

    with_doc = extract_raw_implementation_body(source, by_name["with_doc"])
    assert "Docstring" not in with_doc.body_text
    assert with_doc.body_text.startswith("\n")
    assert "    # implementation\n" in with_doc.body_text

    outer = extract_raw_implementation_body(source, by_name["outer_async"])
    assert "def nested():" in outer.body_text
    assert by_name["outer_async"].contains_nested_named_definition is True

    method = extract_raw_implementation_body(source, by_name["C.method"])
    assert method.body_text.startswith("        return 3")

    try:
        extract_raw_implementation_body(source, by_name["doc_only"])
    except StageError as exc:
        assert "docstring_only" in str(exc)
    else:
        raise AssertionError("Docstring-only function must have no implementation body")

    repeated = "a  b"
    assert len(repeated.split(" ")) == 3
    assert len(" ".join(["x"] * 100).split(" ")) == 100
    assert len(" ".join(["x"] * 200).split(" ")) == 200

    crlf_source = "def f():\r\n    # c\r\n    return  1\r\n"
    crlf_response = run_ast_worker_batch(
        [
            {
                "request_index": 0,
                "blob": GitBlob(path="crlf.py", oid="1" * 40, mode="100644"),
                "source": crlf_source,
            }
        ],
        ast_python_bin=ast_python_bin,
        python_script_path=python_script_path,
        timeout_seconds=timeout_seconds,
    )[0]
    crlf_record = function_record_from_dict(crlf_response["records"][0])
    crlf_body = extract_raw_implementation_body(crlf_source, crlf_record)
    assert "\r\n" in crlf_body.body_text
    assert crlf_body.body_text.startswith("    # c\r\n")

    print("Self-test: PASS")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Compute raw Python function-body token metrics for 100-200-token "
            "bodies over run-x-a05 historical snapshots."
        )
    )
    parser.add_argument("--input-manifest-file", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-output", type=Path, required=True)
    parser.add_argument("--snapshot-results-output", type=Path, required=True)
    parser.add_argument("--function-details-output", type=Path, required=True)
    parser.add_argument("--file-issues-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--scan-qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--body-store-root", type=Path, required=True)
    parser.add_argument(
        "--body-save-scope",
        choices=sorted(BODY_SAVE_SCOPES),
        default="all",
        help="Save all extracted bodies or only bodies qualifying for 100-200 tokens.",
    )
    parser.add_argument("--resolution-decisions-file", type=Path, default=None)
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--ast-python-bin", required=True)
    parser.add_argument("--ast-worker-timeout-seconds", type=int, default=300)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--dataset-source", choices=["", "treatment", "control"], default=""
    )
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--analysis-again", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--skip-self-test", action="store_true")
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
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def validate_cli_args(args: argparse.Namespace) -> None:
    """Validate numeric command-line arguments."""
    for name in [
        "git_timeout_seconds",
        "ast_worker_timeout_seconds",
        "progress_every",
        "limit",
    ]:
        value = int(getattr(args, name))
        if value < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative.")
    if args.git_timeout_seconds == 0 and not args.dry_run:
        raise ValueError("--git-timeout-seconds must be positive for a real run.")
    if args.ast_worker_timeout_seconds == 0:
        raise ValueError("--ast-worker-timeout-seconds must be positive.")
    if args.start_order < 1:
        raise ValueError("--start-order must be at least 1.")
    if args.body_save_scope not in BODY_SAVE_SCOPES:
        raise ValueError(f"Unsupported body save scope: {args.body_save_scope}")


def main() -> int:
    """Run the D01 token metric workflow."""
    if "--ast-worker-version" in sys.argv[1:]:
        json.dump(ast_worker_version_payload(), sys.stdout)
        sys.stdout.write("\n")
        return 0
    if "--ast-worker" in sys.argv[1:]:
        return run_ast_worker_cli()

    args = parse_args()
    validate_cli_args(args)
    python_script_path = Path(__file__).expanduser().resolve()
    ast_metadata = inspect_ast_python(
        args.ast_python_bin,
        python_script_path,
        args.ast_worker_timeout_seconds,
    )
    ast_python_version = str(ast_metadata["python_version"])

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if not args.skip_self_test:
        run_internal_self_test(
            args.ast_python_bin,
            python_script_path,
            args.ast_worker_timeout_seconds,
        )

    input_path = args.input_manifest_file.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Snapshot manifest not found: {input_path}")

    raw_manifest = pd.read_csv(input_path, low_memory=False)
    manifest = normalize_input_manifest(raw_manifest)
    structural_checks = expected_count_checks(manifest, args)
    save_dataframe(manifest, args.snapshot_manifest_output)

    selected = filter_targets(manifest, args)
    resolution_frame = load_resolution_decisions(args.resolution_decisions_file)
    resolution_map = {
        str(row["snapshot_key"]): (
            str(row["resolution_decision"]),
            str(row["resolution_note"]),
        )
        for _, row in resolution_frame.iterrows()
    }

    results = load_existing_results(args.snapshot_results_output)
    details = load_existing_function_details(args.function_details_output)
    issues = load_existing_file_issues(args.file_issues_output)
    counters = RunCounters(selected_targets=len(selected))
    run_started = time.monotonic()

    successful_keys: set[str] = set()
    if not results.empty and not args.analysis_again:
        success_mask = (
            results["snapshot_status"].eq("success")
            & results["metric_available"].fillna(False).astype(bool)
        )
        body_root = args.body_store_root.expanduser().resolve()
        compatible = (
            results["body_save_scope"].fillna("").astype(str).eq(
                args.body_save_scope
            )
            & results["body_store_root"].fillna("").astype(str).eq(
                str(body_root)
            )
        )
        candidate_keys = set(
            results.loc[success_mask & compatible, "snapshot_key"].astype(str)
        )
        successful_keys = {
            key for key in candidate_keys if (body_root / key).is_dir()
        }

    for position, (_, target) in enumerate(selected.iterrows(), start=1):
        snapshot_key = str(target["snapshot_key"])
        if snapshot_key in successful_keys and not args.analysis_again:
            counters.skipped_existing_success += 1
            if position % max(args.progress_every, 1) == 0 or position == len(selected):
                logging.info(progress_message(position, len(selected), counters, run_started))
            continue

        logging.info(
            "Target %d/%d: order=%d %s %s at %s (%d repo-month rows)",
            position,
            len(selected),
            int(target["manifest_order"]),
            target["dataset_source"],
            target["repo_name"],
            str(target["commit_sha"])[:12],
            int(target["repo_month_rows"]),
        )

        if args.dry_run:
            result = base_result_row(
                target,
                scan_attempt=prior_attempt_count(results, snapshot_key) + 1,
            )
            result.update(
                {
                    "scan_completed_at": utc_now(),
                    "runtime_seconds": 0.0,
                    "git_precheck_status": "not_checked_dry_run",
                    "snapshot_status": "dry_run",
                    "resolution_decision": "not_needed",
                    "ast_python_bin": args.ast_python_bin,
                    "ast_python_version": ast_python_version,
                    "ast_worker_timeout_seconds": args.ast_worker_timeout_seconds,
                }
            )
            snapshot_details: list[dict[str, Any]] = []
            snapshot_issues: list[dict[str, Any]] = []
        else:
            result, snapshot_details, snapshot_issues = run_snapshot(
                target,
                existing_results=results,
                git_timeout_seconds=args.git_timeout_seconds,
                resolution_map=resolution_map,
                body_store_root=args.body_store_root,
                body_save_scope=args.body_save_scope,
                ast_python_bin=args.ast_python_bin,
                ast_python_version=ast_python_version,
                ast_worker_timeout_seconds=args.ast_worker_timeout_seconds,
                python_script_path=python_script_path,
            )

        results = upsert_result(results, result)
        details = replace_snapshot_rows(
            details,
            snapshot_key,
            snapshot_details,
            FUNCTION_DETAIL_COLUMNS,
        )
        issues = replace_snapshot_rows(
            issues,
            snapshot_key,
            snapshot_issues,
            FILE_ISSUE_COLUMNS,
        )
        save_dataframe(results.sort_values("manifest_order"), args.snapshot_results_output)
        save_dataframe(details, args.function_details_output)
        save_dataframe(issues, args.file_issues_output)

        counters.processed_this_run += 1
        status = str(result["snapshot_status"])
        if status == "success":
            counters.successful_this_run += 1
            logging.info(
                "Success: %s at %s -> token_py_100_200=%s; functions=%s; qualifying=%s",
                target["repo_name"],
                str(target["commit_sha"])[:12],
                result["token_py_100_200"],
                result["function_count_py_all"],
                result["function_count_py_100_200"],
            )
        elif status in {"partial_needs_review", "partial_accepted", "excluded_after_review"}:
            counters.partial_this_run += 1
            logging.warning(
                "Partial: %s at %s -> status=%s; partial_token=%s; failed_files=%s; boundary_failures=%s",
                target["repo_name"],
                str(target["commit_sha"])[:12],
                status,
                result["token_py_100_200_partial"],
                result["failed_python_file_count"],
                result["function_count_py_boundary_failed_partial"],
            )
        elif status != "dry_run":
            counters.failed_this_run += 1
            logging.warning(
                "Failed: %s at %s -> status=%s; stage=%s; message=%s",
                target["repo_name"],
                str(target["commit_sha"])[:12],
                status,
                result["error_stage"],
                result["error_message"],
            )

        if position % max(args.progress_every, 1) == 0 or position == len(selected):
            logging.info(progress_message(position, len(selected), counters, run_started))

    results = results.sort_values("manifest_order", kind="stable").reset_index(drop=True)
    details = details.sort_values(
        ["manifest_order", "path", "function_start_line", "qualified_name"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    issues = issues.sort_values(
        ["dataset_source", "repo_name", "commit_sha", "path", "issue_stage"],
        kind="stable",
    ).reset_index(drop=True)

    save_dataframe(results, args.snapshot_results_output)
    save_dataframe(details, args.function_details_output)
    save_dataframe(issues, args.file_issues_output)

    unresolved = build_unresolved(results)
    save_dataframe(unresolved, args.unresolved_output)

    qc, summary = build_qc_and_summary(
        manifest,
        results,
        details,
        issues,
        structural_checks,
        counters,
        dry_run=args.dry_run,
    )
    save_dataframe(qc, args.scan_qc_output)
    save_dataframe(summary, args.summary_output)

    available = results["metric_available"].fillna(False).astype(bool)
    available_count = int(available.sum())
    available_coverage = int(results.loc[available, "repo_month_rows"].sum())
    logging.info(
        "Completed %s-%s: available=%d/%d snapshots; coverage=%d/%d repo-month rows; "
        "unresolved_or_reviewed=%d; function_details=%d; file_issues=%d",
        EXPERIMENT_NAME,
        IMPLEMENTATION_VERSION,
        available_count,
        len(manifest),
        available_coverage,
        int(manifest["repo_month_rows"].sum()),
        len(unresolved),
        len(details),
        len(issues),
    )

    if args.fail_on_unresolved and (~available).any():
        logging.error(
            "Fail-on-unresolved requested and %d snapshots lack an available metric.",
            int((~available).sum()),
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        logging.exception("%s failed: %s", EXPERIMENT_NAME, exc)
        raise SystemExit(1)
