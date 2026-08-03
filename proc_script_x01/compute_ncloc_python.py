#!/usr/bin/env python3
"""Compute two fast Python-only NCLOC measures for Model C.

This program is the self-contained analysis implementation for run-x-b01-v4.
It does not call an earlier shell wrapper or the SonarQube implementation.
For every historical repository-commit snapshot, it computes:

1. ``ncloc_py_ast`` using local Git objects, Python ``tokenize``, and AST.
   Blank lines, comment-only lines, and bare constant-string expression
   statements are excluded. Strings used in assignments, returns, calls,
   collections, formatting, and other executable expressions are preserved.
2. ``ncloc_py_cloc`` using the external ``cloc`` tool in its default Python
   mode over the exact same materialized tracked-Python file set.
3. Diagnostic comparisons with the preserved SonarQube result, when present.

The main treatment/control clone working trees are never checked out, reset,
cleaned, or modified. Historical content is read directly from Git objects.
"""

from __future__ import annotations

import argparse
import ast
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
import tokenize
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional

import pandas as pd


IMPLEMENTATION_VERSION = "v4"
COUNT_BACKEND = "local_git_ast_tokenize_and_cloc"
AST_METRIC_DEFINITION = (
    "tracked Python physical lines excluding blank lines, comment-only lines, "
    "and bare constant-string expression statements"
)
CLOC_METRIC_DEFINITION = (
    "cloc default Python code lines over the exact same tracked Python files"
)
METRIC_DEFINITION = AST_METRIC_DEFINITION
SCAN_SCOPE = "tracked_python_blobs_local_git"
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
    "count_backend",
    "metric_definition",
    "cloc_metric_definition",
    "scan_attempt",
    "scan_scope",
    "scan_started_at",
    "scan_completed_at",
    "runtime_seconds",
    "git_precheck_status",
    "python_file_count_manifest",
    "python_file_count_git",
    "python_file_count_matches_manifest",
    "git_blob_count",
    "git_blob_bytes",
    "physical_lines",
    "blank_lines",
    "comment_only_lines",
    "ncloc_py_before_string_expr_exclusion",
    "string_expr_span_lines",
    "string_expr_ncloc_lines",
    "string_expr_statements",
    "non_docstring_string_expr_statements",
    "module_docstrings",
    "class_docstrings",
    "function_docstrings",
    "async_function_docstrings",
    "ordinary_string_literal_lines",
    "tokenize_failed_files",
    "ast_parse_failed_files",
    "decode_failed_files",
    "ncloc_py_ast",
    "ast_status",
    "ast_error_message",
    "cloc_version",
    "cloc_runtime_seconds",
    "python_file_count_cloc",
    "python_file_count_cloc_matches_git",
    "cloc_blank_lines",
    "cloc_comment_lines",
    "ncloc_py_cloc",
    "cloc_status",
    "cloc_error_message",
    "ncloc_py_ast_minus_cloc",
    "exact_match_ast_cloc",
    "ncloc_py",
    "status",
    "error_stage",
    "error_message",
]

FILE_ISSUE_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "backend",
    "path",
    "blob_oid",
    "blob_size",
    "issue_stage",
    "issue_type",
    "issue_message",
]

COMPARISON_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "python_file_count_git",
    "python_file_count_cloc",
    "python_file_count_sonarqube_scan",
    "ncloc_py_ast",
    "ncloc_py_cloc",
    "ncloc_py_sonarqube",
    "ncloc_py_ast_minus_cloc",
    "sonar_minus_ast",
    "sonar_minus_cloc",
    "exact_match_ast_cloc",
    "exact_match_ast_sonar",
    "exact_match_cloc_sonar",
]

MEANINGFUL_TOKEN_EXCLUSIONS = {
    tokenize.ENCODING,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.COMMENT,
    tokenize.ENDMARKER,
}


@dataclass(frozen=True)
class GitBlob:
    """One tracked regular-file blob at a historical commit."""

    path: str
    oid: str
    mode: str


@dataclass(frozen=True)
class StringExpressionSpan:
    """One bare constant-string expression span and its semantic role."""

    expression_kind: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass
class SourceMetrics:
    """Per-file AST/tokenize physical-line metrics."""

    physical_lines: int = 0
    blank_lines: int = 0
    comment_only_lines: int = 0
    ncloc_py_before_string_expr_exclusion: int = 0
    string_expr_span_lines: int = 0
    string_expr_ncloc_lines: int = 0
    string_expr_statements: int = 0
    non_docstring_string_expr_statements: int = 0
    module_docstrings: int = 0
    class_docstrings: int = 0
    function_docstrings: int = 0
    async_function_docstrings: int = 0
    ordinary_string_literal_lines: int = 0
    ncloc_py_ast: Optional[int] = None


@dataclass
class ClocMetrics:
    """One snapshot-level cloc result over the selected Python files."""

    version: str = ""
    runtime_seconds: float = 0.0
    python_file_count: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0


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
    """Create a stable identifier fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value).strip())
    cleaned = cleaned.strip("_.:-") or "unknown"
    return cleaned[:max_length]


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    """Build the same stable repository-snapshot identifier used by v1."""
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


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    output_path = path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    df.to_csv(temp_path, index=False)
    temp_path.replace(output_path)


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Add missing columns and return them in the requested order."""
    result = df.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[columns].copy()


def load_existing_results(path: Path) -> pd.DataFrame:
    """Load prior local-Git results for resume behavior."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    existing = pd.read_csv(input_path)
    if "count_backend" not in existing.columns:
        raise ValueError(
            "The active result file is not a run-x-b01-v4 result. Preserve older "
            "backend results before rerunning."
        )
    if not existing["count_backend"].fillna("").eq(COUNT_BACKEND).all():
        raise ValueError("The active result file contains a different count backend.")
    if "snapshot_key" not in existing.columns:
        raise ValueError(f"Existing result file has no snapshot_key: {input_path}")
    if existing["snapshot_key"].duplicated().any():
        examples = existing.loc[
            existing["snapshot_key"].duplicated(keep=False), "snapshot_key"
        ].head(10)
        raise ValueError(
            "Existing result file contains duplicate snapshot keys: "
            + ", ".join(examples.astype(str))
        )
    return ensure_columns(existing, RESULT_COLUMNS)


def load_existing_file_issues(path: Path) -> pd.DataFrame:
    """Load prior file-level issues."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame(columns=FILE_ISSUE_COLUMNS)
    return ensure_columns(pd.read_csv(input_path), FILE_ISSUE_COLUMNS)


def upsert_result(existing: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
    """Insert or replace one snapshot result by snapshot key."""
    row = pd.DataFrame(
        [{column: result.get(column, pd.NA) for column in RESULT_COLUMNS}]
    )
    if existing.empty:
        return row
    remaining = existing[existing["snapshot_key"] != result["snapshot_key"]].copy()
    return pd.concat([remaining, row], ignore_index=True, sort=False)[RESULT_COLUMNS]


def replace_snapshot_issues(
    existing: pd.DataFrame,
    snapshot_key: str,
    new_issues: list[dict[str, Any]],
) -> pd.DataFrame:
    """Replace all issue rows for one snapshot."""
    remaining = existing[existing["snapshot_key"].astype(str) != snapshot_key].copy()
    if not new_issues:
        return ensure_columns(remaining, FILE_ISSUE_COLUMNS)
    incoming = ensure_columns(pd.DataFrame(new_issues), FILE_ISSUE_COLUMNS)
    return pd.concat([remaining, incoming], ignore_index=True, sort=False)[
        FILE_ISSUE_COLUMNS
    ]


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
        raise ValueError("Every Model C snapshot must have at least one Python file.")
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
            "Duplicate Model C repository-snapshot keys were found:\n"
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
    manifest["metric_definition"] = AST_METRIC_DEFINITION
    manifest["cloc_metric_definition"] = CLOC_METRIC_DEFINITION
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
    role_repos = (
        manifest.groupby("dataset_source")["repo_name"].nunique().to_dict()
    )

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
    """Apply the Python suffix and Sonar-era directory exclusions."""
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
        raise RuntimeError(
            "git ls-tree failed: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )

    blobs: list[GitBlob] = []
    for raw_entry in process.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode_b, object_type_b, oid_b = metadata.split(b" ", 2)
        except ValueError as exc:
            raise RuntimeError(f"Unexpected git ls-tree entry: {raw_entry!r}") from exc
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
    """Read all unique blob objects with one git cat-file --batch call."""
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
        raise RuntimeError(
            "git cat-file --batch failed: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )

    stream = io.BytesIO(process.stdout)
    contents: dict[str, bytes] = {}
    for requested_oid in unique_oids:
        header = stream.readline()
        if not header:
            raise RuntimeError(
                f"git cat-file ended before returning blob {requested_oid}"
            )
        header_parts = header.rstrip(b"\n").split()
        if len(header_parts) >= 2 and header_parts[1] == b"missing":
            raise RuntimeError(f"git cat-file reported missing blob {requested_oid}")
        if len(header_parts) != 3 or header_parts[1] != b"blob":
            raise RuntimeError(f"Unexpected git cat-file header: {header!r}")
        returned_oid = header_parts[0].decode("ascii", errors="replace")
        size = int(header_parts[2])
        data = stream.read(size)
        terminator = stream.read(1)
        if len(data) != size or terminator != b"\n":
            raise RuntimeError(f"Incomplete git cat-file payload for {requested_oid}")
        contents[returned_oid] = data

    return contents


def decode_python_source(data: bytes) -> str:
    """Decode Python source using PEP 263 encoding detection."""
    reader = io.BytesIO(data).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return data.decode(encoding)


def position_leq(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Return whether a source position is less than or equal to another."""
    return left[0] < right[0] or (left[0] == right[0] and left[1] <= right[1])


def token_inside_span(
    token_info: tokenize.TokenInfo, span: StringExpressionSpan
) -> bool:
    """Return whether a token is fully contained in a string-expression span."""
    return position_leq((span.start_line, span.start_col), token_info.start) and position_leq(
        token_info.end, (span.end_line, span.end_col)
    )


def collect_string_expression_spans(tree: ast.AST) -> list[StringExpressionSpan]:
    """Collect every bare constant-string expression and classify docstrings."""
    docstring_kinds: dict[tuple[int, int, int, int], str] = {}
    scope_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for scope in ast.walk(tree):
        if not isinstance(scope, scope_types):
            continue
        body = getattr(scope, "body", None)
        if not body:
            continue
        statement = body[0]
        if not isinstance(statement, ast.Expr):
            continue
        value = statement.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        if not all(
            hasattr(value, attribute)
            for attribute in ("lineno", "col_offset", "end_lineno", "end_col_offset")
        ):
            continue
        if isinstance(scope, ast.Module):
            kind = "module_docstring"
        elif isinstance(scope, ast.ClassDef):
            kind = "class_docstring"
        elif isinstance(scope, ast.AsyncFunctionDef):
            kind = "async_function_docstring"
        else:
            kind = "function_docstring"
        key = (
            int(value.lineno),
            int(value.col_offset),
            int(value.end_lineno),
            int(value.end_col_offset),
        )
        docstring_kinds[key] = kind

    spans: list[StringExpressionSpan] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        if not all(
            hasattr(value, attribute)
            for attribute in ("lineno", "col_offset", "end_lineno", "end_col_offset")
        ):
            continue
        key = (
            int(value.lineno),
            int(value.col_offset),
            int(value.end_lineno),
            int(value.end_col_offset),
        )
        spans.append(
            StringExpressionSpan(
                expression_kind=docstring_kinds.get(key, "standalone_string_expression"),
                start_line=key[0],
                start_col=key[1],
                end_line=key[2],
                end_col=key[3],
            )
        )
    spans.sort(
        key=lambda item: (
            item.start_line,
            item.start_col,
            item.end_line,
            item.end_col,
        )
    )
    return spans


def nonblank_lines_for_token(
    token_info: tokenize.TokenInfo, lines: list[str]
) -> set[int]:
    """Return nonblank physical lines covered by one token."""
    if not lines:
        return set()
    start_line = max(int(token_info.start[0]), 1)
    end_line = min(int(token_info.end[0]), len(lines))
    return {
        line_number
        for line_number in range(start_line, end_line + 1)
        if lines[line_number - 1].strip() != ""
    }


def analyze_python_source(data: bytes, filename: str) -> SourceMetrics:
    """Measure one Python file using tokenize plus AST string-expression rules."""
    text = decode_python_source(data)
    lines = text.splitlines()
    metrics = SourceMetrics(
        physical_lines=len(lines),
        blank_lines=sum(1 for line in lines if line.strip() == ""),
    )

    tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    tree = ast.parse(text, filename=filename, type_comments=True)
    string_expr_spans = collect_string_expression_spans(tree)

    excluded_token_indexes: set[int] = set()
    excluded_span_line_numbers: set[int] = set()
    for span in string_expr_spans:
        excluded_span_line_numbers.update(range(span.start_line, span.end_line + 1))
        for index, token_info in enumerate(tokens):
            if token_info.type == tokenize.STRING and token_inside_span(token_info, span):
                excluded_token_indexes.add(index)

    code_lines_before_exclusion: set[int] = set()
    code_lines_after_exclusion: set[int] = set()
    ordinary_string_lines: set[int] = set()
    per_line_non_excluded_tokens: dict[int, list[tokenize.TokenInfo]] = {}
    per_line_excluded_string_token: set[int] = set()

    for index, token_info in enumerate(tokens):
        if token_info.type in MEANINGFUL_TOKEN_EXCLUSIONS:
            continue
        covered_lines = nonblank_lines_for_token(token_info, lines)
        code_lines_before_exclusion.update(covered_lines)
        if index in excluded_token_indexes:
            per_line_excluded_string_token.update(covered_lines)
            continue
        code_lines_after_exclusion.update(covered_lines)
        for line_number in covered_lines:
            per_line_non_excluded_tokens.setdefault(line_number, []).append(token_info)
        if token_info.type == tokenize.STRING:
            ordinary_string_lines.update(covered_lines)

    # Parentheses and semicolons around a removed bare string do not make a line
    # executable. Any other token on that line keeps the line counted.
    wrapper_ops = {"(", ")", ";"}
    for line_number in sorted(per_line_excluded_string_token):
        remaining = per_line_non_excluded_tokens.get(line_number, [])
        if remaining and all(
            token_info.type == tokenize.OP and token_info.string in wrapper_ops
            for token_info in remaining
        ):
            code_lines_after_exclusion.discard(line_number)

    nonblank_line_numbers = {
        line_number
        for line_number, line in enumerate(lines, start=1)
        if line.strip() != ""
    }
    metrics.comment_only_lines = len(
        nonblank_line_numbers - code_lines_before_exclusion
    )
    metrics.ncloc_py_before_string_expr_exclusion = len(code_lines_before_exclusion)
    metrics.string_expr_span_lines = len(
        {
            line_number
            for line_number in excluded_span_line_numbers
            if 1 <= line_number <= len(lines)
        }
    )
    metrics.string_expr_ncloc_lines = len(
        code_lines_before_exclusion - code_lines_after_exclusion
    )
    metrics.string_expr_statements = len(string_expr_spans)
    metrics.non_docstring_string_expr_statements = sum(
        1
        for span in string_expr_spans
        if span.expression_kind == "standalone_string_expression"
    )
    metrics.module_docstrings = sum(
        1 for span in string_expr_spans if span.expression_kind == "module_docstring"
    )
    metrics.class_docstrings = sum(
        1 for span in string_expr_spans if span.expression_kind == "class_docstring"
    )
    metrics.function_docstrings = sum(
        1 for span in string_expr_spans if span.expression_kind == "function_docstring"
    )
    metrics.async_function_docstrings = sum(
        1
        for span in string_expr_spans
        if span.expression_kind == "async_function_docstring"
    )
    metrics.ordinary_string_literal_lines = len(ordinary_string_lines)
    metrics.ncloc_py_ast = len(code_lines_after_exclusion)
    return metrics


def parse_cloc_csv(output: str) -> ClocMetrics:
    """Parse cloc CSV output from summary or --by-file schemas.

    cloc --by-file omits the language column, while summary output includes
    language and files columns. This parser accepts both layouts. The caller
    already restricts cloc to Python with --include-lang=Python.
    """
    rows = list(csv.reader(io.StringIO(output)))
    header_index: Optional[int] = None
    normalized_header: list[str] = []

    for index, row in enumerate(rows):
        lowered = [cell.strip().lower() for cell in row]
        header_names = set(lowered)
        has_counts = {"blank", "comment", "code"}.issubset(header_names)
        has_identity = bool({"language", "file", "filename"} & header_names)
        if has_counts and has_identity:
            header_index = index
            normalized_header = lowered
            break

    if header_index is None:
        preview = " | ".join(output.splitlines()[:5])
        raise ValueError(f"cloc CSV header was not found in stdout: {preview}")

    positions = {name: index for index, name in enumerate(normalized_header)}
    language_index = positions.get("language")
    filename_index = positions.get("filename", positions.get("file"))
    files_index = positions.get("files")
    required_indexes = [positions["blank"], positions["comment"], positions["code"]]
    if language_index is not None:
        required_indexes.append(language_index)
    if filename_index is not None:
        required_indexes.append(filename_index)
    if files_index is not None:
        required_indexes.append(files_index)
    maximum_index = max(required_indexes)

    def parse_count(row: list[str], column: str) -> int:
        value = row[positions[column]].strip()
        return int(float(value or "0"))

    selected_rows: list[list[str]] = []
    for row in rows[header_index + 1 :]:
        if not row or len(row) <= maximum_index:
            continue

        if filename_index is not None:
            filename = row[filename_index].strip()
            normalized_filename = filename.rstrip(":").strip().lower()
            if not filename or normalized_filename in {"sum", "total"}:
                continue

        if language_index is not None:
            language = row[language_index].strip().lower()
            if language != "python":
                continue

        selected_rows.append(row)

    if not selected_rows:
        preview = " | ".join(output.splitlines()[:8])
        raise ValueError(f"cloc returned no Python rows: {preview}")

    blank_lines = sum(parse_count(row, "blank") for row in selected_rows)
    comment_lines = sum(parse_count(row, "comment") for row in selected_rows)
    code_lines = sum(parse_count(row, "code") for row in selected_rows)

    if filename_index is not None:
        python_file_count = len(
            {row[filename_index].strip() for row in selected_rows if row[filename_index].strip()}
        )
    elif files_index is not None:
        python_file_count = sum(
            int(float(row[files_index].strip() or "0")) for row in selected_rows
        )
    else:
        python_file_count = len(selected_rows)

    return ClocMetrics(
        python_file_count=python_file_count,
        blank_lines=blank_lines,
        comment_lines=comment_lines,
        code_lines=code_lines,
    )


def safe_materialized_path(root: Path, path_text: str) -> Path:
    """Return a safe destination for one repository-relative Git path."""
    path = PurePosixPath(path_text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe Git path for cloc materialization: {path_text!r}")
    destination = root.joinpath(*path.parts)
    resolved_root = root.resolve()
    resolved_destination = destination.resolve()
    if resolved_root != resolved_destination and resolved_root not in resolved_destination.parents:
        raise ValueError(f"Git path escaped cloc temporary root: {path_text!r}")
    return destination


def run_cloc_snapshot(
    blobs: list[GitBlob],
    blob_contents: dict[str, bytes],
    *,
    cloc_bin: str,
    cloc_timeout_seconds: int,
    cloc_temp_root: Path,
    keep_cloc_temp: bool,
    snapshot_key: str,
    cloc_version: str,
) -> ClocMetrics:
    """Run cloc default mode over the exact selected tracked-Python files."""
    cloc_temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=f"{sanitize_key(snapshot_key, 40)}-",
            dir=str(cloc_temp_root),
        )
    )
    started = time.monotonic()
    try:
        for blob in blobs:
            destination = safe_materialized_path(temp_dir, blob.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob_contents[blob.oid])

        command = [
            cloc_bin,
            "--csv",
            "--by-file",
            "--quiet",
            "--skip-uniqueness",
            "--include-lang=Python",
            str(temp_dir),
        ]
        process = run_text_command(command, timeout=cloc_timeout_seconds)
        metrics = parse_cloc_csv(process.stdout)
        metrics.version = cloc_version
        metrics.runtime_seconds = round(time.monotonic() - started, 3)
        return metrics
    finally:
        if keep_cloc_temp:
            logging.info("Kept cloc temporary directory: %s", temp_dir)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


def run_internal_self_test() -> None:
    """Verify AST string-expression policy and cloc CSV parsing."""
    sample = (
        'def load_data():\n'
        '    """Load the dataset.\n\n'
        '    Return parsed records.\n'
        '    """\n\n'
        '    """Temporary implementation note.\n\n'
        '    Remove after migration.\n'
        '    """\n'
        '    query = """SELECT *\n\nFROM records"""\n'
        '    f"{execute_side_effect()}"\n'
        '    return execute(query)\n'
    ).encode("utf-8")
    metrics = analyze_python_source(sample, "self_test.py")
    expected = {
        "ncloc_py_before_string_expr_exclusion": 11,
        "string_expr_span_lines": 8,
        "string_expr_ncloc_lines": 6,
        "string_expr_statements": 2,
        "non_docstring_string_expr_statements": 1,
        "function_docstrings": 1,
        "ncloc_py_ast": 5,
    }
    observed = {key: getattr(metrics, key) for key in expected}
    if observed != expected:
        raise AssertionError(
            f"Internal AST self-test failed: observed={observed}, expected={expected}"
        )

    cloc_samples = [
        (
            "language_and_filename",
            """Language,Filename,Blank,Comment,Code
Python,a.py,2,3,10
Python,b.py,1,4,7
SUM,,3,7,17
""",
            (2, 3, 7, 17),
        ),
        (
            "by_file_without_language",
            """File,blank,comment,code
/tmp/a.py,2,3,10
/tmp/b.py,1,4,7
SUM,3,7,17
""",
            (2, 3, 7, 17),
        ),
        (
            "language_summary",
            """language,files,blank,comment,code
Python,2,3,7,17
SUM,2,3,7,17
""",
            (2, 3, 7, 17),
        ),
    ]
    for sample_name, cloc_sample, expected_cloc in cloc_samples:
        cloc_metrics = parse_cloc_csv(cloc_sample)
        cloc_observed = (
            cloc_metrics.python_file_count,
            cloc_metrics.blank_lines,
            cloc_metrics.comment_lines,
            cloc_metrics.code_lines,
        )
        if cloc_observed != expected_cloc:
            raise AssertionError(
                "Internal cloc CSV self-test failed: "
                f"sample={sample_name}, observed={cloc_observed}, "
                f"expected={expected_cloc}"
            )
    logging.info(
        "Self-test PASS: bare constant-string statements excluded; assigned "
        "multiline strings and f-strings preserved; cloc summary and by-file CSV schemas validated"
    )


def prior_attempt_count(existing: pd.DataFrame, snapshot_key: str) -> int:
    """Return the previous local-Git attempt count for one snapshot."""
    if existing.empty:
        return 0
    rows = existing[existing["snapshot_key"].astype(str).eq(snapshot_key)]
    if rows.empty:
        return 0
    value = pd.to_numeric(rows.iloc[-1].get("scan_attempt"), errors="coerce")
    return int(value) if pd.notna(value) else 0


def base_result_row(
    manifest_row: pd.Series,
    *,
    scan_attempt: int,
) -> dict[str, Any]:
    """Create a complete two-method result record with default values."""
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
        "count_backend": COUNT_BACKEND,
        "metric_definition": AST_METRIC_DEFINITION,
        "cloc_metric_definition": CLOC_METRIC_DEFINITION,
        "scan_attempt": scan_attempt,
        "scan_scope": SCAN_SCOPE,
        "scan_started_at": utc_now(),
        "scan_completed_at": "",
        "runtime_seconds": pd.NA,
        "git_precheck_status": "pending",
        "python_file_count_manifest": int(manifest_row["python_file_count_manifest"]),
        "python_file_count_git": pd.NA,
        "python_file_count_matches_manifest": pd.NA,
        "git_blob_count": pd.NA,
        "git_blob_bytes": pd.NA,
        "physical_lines": pd.NA,
        "blank_lines": pd.NA,
        "comment_only_lines": pd.NA,
        "ncloc_py_before_string_expr_exclusion": pd.NA,
        "string_expr_span_lines": pd.NA,
        "string_expr_ncloc_lines": pd.NA,
        "string_expr_statements": pd.NA,
        "non_docstring_string_expr_statements": pd.NA,
        "module_docstrings": pd.NA,
        "class_docstrings": pd.NA,
        "function_docstrings": pd.NA,
        "async_function_docstrings": pd.NA,
        "ordinary_string_literal_lines": pd.NA,
        "tokenize_failed_files": 0,
        "ast_parse_failed_files": 0,
        "decode_failed_files": 0,
        "ncloc_py_ast": pd.NA,
        "ast_status": "pending",
        "ast_error_message": "",
        "cloc_version": "",
        "cloc_runtime_seconds": pd.NA,
        "python_file_count_cloc": pd.NA,
        "python_file_count_cloc_matches_git": pd.NA,
        "cloc_blank_lines": pd.NA,
        "cloc_comment_lines": pd.NA,
        "ncloc_py_cloc": pd.NA,
        "cloc_status": "pending",
        "cloc_error_message": "",
        "ncloc_py_ast_minus_cloc": pd.NA,
        "exact_match_ast_cloc": pd.NA,
        "ncloc_py": pd.NA,
        "status": "pending",
        "error_stage": "",
        "error_message": "",
    }


def aggregate_metric(result: dict[str, Any], name: str, value: int) -> None:
    """Add one integer source metric to a snapshot result."""
    current = pd.to_numeric(result.get(name), errors="coerce")
    result[name] = int(value) if pd.isna(current) else int(current) + int(value)


def add_snapshot_issue(
    issues: list[dict[str, Any]],
    result: dict[str, Any],
    *,
    backend: str,
    path: str,
    blob_oid: str,
    blob_size: Any,
    issue_stage: str,
    issue_type: str,
    issue_message: str,
) -> None:
    """Append one normalized file or snapshot issue record."""
    issues.append(
        {
            "snapshot_key": result["snapshot_key"],
            "dataset_source": result["dataset_source"],
            "repo_name": result["repo_name"],
            "commit_sha": result["commit_sha"],
            "backend": backend,
            "path": path,
            "blob_oid": blob_oid,
            "blob_size": blob_size,
            "issue_stage": issue_stage,
            "issue_type": issue_type,
            "issue_message": issue_message,
        }
    )


def finalize_backend_status(result: dict[str, Any]) -> None:
    """Set aggregate status and the backward-compatible primary NCLOC alias."""
    ast_success = result.get("ast_status") == "success" and pd.notna(
        pd.to_numeric(result.get("ncloc_py_ast"), errors="coerce")
    )
    cloc_success = result.get("cloc_status") == "success" and pd.notna(
        pd.to_numeric(result.get("ncloc_py_cloc"), errors="coerce")
    )

    result["ncloc_py"] = result["ncloc_py_ast"] if ast_success else pd.NA
    if ast_success and cloc_success:
        ast_value = int(pd.to_numeric(result["ncloc_py_ast"], errors="raise"))
        cloc_value = int(pd.to_numeric(result["ncloc_py_cloc"], errors="raise"))
        result["ncloc_py_ast_minus_cloc"] = ast_value - cloc_value
        result["exact_match_ast_cloc"] = ast_value == cloc_value
        result["status"] = "success"
        result["error_stage"] = ""
        result["error_message"] = ""
    elif ast_success or cloc_success:
        result["status"] = "partial_success"
        result["error_stage"] = "backend_completion"
        missing = []
        if not ast_success:
            missing.append("AST/tokenize")
        if not cloc_success:
            missing.append("cloc")
        result["error_message"] = "Missing successful backend: " + ", ".join(missing)
    else:
        result["status"] = "measurement_failed"
        result["error_stage"] = "backend_completion"
        result["error_message"] = "Neither AST/tokenize nor cloc completed successfully."


def run_local_git_snapshot(
    manifest_row: pd.Series,
    *,
    existing_results: pd.DataFrame,
    git_timeout_seconds: int,
    cloc_bin: str,
    cloc_version: str,
    cloc_timeout_seconds: int,
    cloc_temp_root: Path,
    keep_cloc_temp: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Measure one historical snapshot with AST/tokenize and cloc."""
    snapshot_key = str(manifest_row["snapshot_key"])
    clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
    commit_sha = str(manifest_row["commit_sha"]).lower()
    result = base_result_row(
        manifest_row,
        scan_attempt=prior_attempt_count(existing_results, snapshot_key) + 1,
    )
    result["cloc_version"] = cloc_version
    issues: list[dict[str, Any]] = []
    started = time.monotonic()

    ready, precheck_status = validate_git_snapshot(
        clone_path, commit_sha, git_timeout_seconds
    )
    result["git_precheck_status"] = precheck_status
    if not ready:
        result["ast_status"] = precheck_status
        result["cloc_status"] = precheck_status
        result["ast_error_message"] = precheck_status
        result["cloc_error_message"] = precheck_status
        result["status"] = precheck_status
        result["error_stage"] = "git_precheck"
        result["error_message"] = precheck_status
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)
        return result, issues

    try:
        blobs = list_python_blobs(clone_path, commit_sha, git_timeout_seconds)
        result["python_file_count_git"] = len(blobs)
        result["python_file_count_matches_manifest"] = (
            len(blobs) == int(result["python_file_count_manifest"])
        )
        result["git_blob_count"] = len(blobs)
        if not blobs:
            result["ast_status"] = "no_python_files"
            result["cloc_status"] = "no_python_files"
            result["ast_error_message"] = "No included tracked Python blobs were found."
            result["cloc_error_message"] = "No included tracked Python blobs were found."
            result["status"] = "no_python_files"
            result["error_stage"] = "git_ls_tree"
            result["error_message"] = "No included tracked Python blobs were found."
            return result, issues

        blob_contents = read_blob_batch(clone_path, blobs, git_timeout_seconds)
        result["git_blob_bytes"] = sum(len(blob_contents[blob.oid]) for blob in blobs)

        ast_metric_names = [
            "physical_lines",
            "blank_lines",
            "comment_only_lines",
            "ncloc_py_before_string_expr_exclusion",
            "string_expr_span_lines",
            "string_expr_ncloc_lines",
            "string_expr_statements",
            "non_docstring_string_expr_statements",
            "module_docstrings",
            "class_docstrings",
            "function_docstrings",
            "async_function_docstrings",
            "ordinary_string_literal_lines",
            "ncloc_py_ast",
        ]
        for name in ast_metric_names:
            result[name] = 0

        for blob in blobs:
            data = blob_contents[blob.oid]
            try:
                metrics = analyze_python_source(data, blob.path)
            except UnicodeDecodeError as exc:
                result["decode_failed_files"] = int(result["decode_failed_files"]) + 1
                add_snapshot_issue(
                    issues,
                    result,
                    backend="ast_tokenize",
                    path=blob.path,
                    blob_oid=blob.oid,
                    blob_size=len(data),
                    issue_stage="decode",
                    issue_type=type(exc).__name__,
                    issue_message=str(exc),
                )
                continue
            except (SyntaxError, IndentationError) as exc:
                result["ast_parse_failed_files"] = int(result["ast_parse_failed_files"]) + 1
                add_snapshot_issue(
                    issues,
                    result,
                    backend="ast_tokenize",
                    path=blob.path,
                    blob_oid=blob.oid,
                    blob_size=len(data),
                    issue_stage="ast_parse",
                    issue_type=type(exc).__name__,
                    issue_message=str(exc),
                )
                continue
            except tokenize.TokenError as exc:
                result["tokenize_failed_files"] = int(result["tokenize_failed_files"]) + 1
                add_snapshot_issue(
                    issues,
                    result,
                    backend="ast_tokenize",
                    path=blob.path,
                    blob_oid=blob.oid,
                    blob_size=len(data),
                    issue_stage="tokenize",
                    issue_type=type(exc).__name__,
                    issue_message=str(exc),
                )
                continue

            for name in ast_metric_names:
                aggregate_metric(result, name, int(getattr(metrics, name)))

        failed_files = (
            int(result["decode_failed_files"])
            + int(result["tokenize_failed_files"])
            + int(result["ast_parse_failed_files"])
        )
        if failed_files > 0:
            result["ncloc_py_ast"] = pd.NA
            result["ast_status"] = "source_analysis_failed"
            result["ast_error_message"] = (
                f"{failed_files} Python files could not be measured with the strict "
                "AST/tokenize definition; see the file-issues CSV."
            )
        else:
            result["ast_status"] = "success"

        try:
            cloc_metrics = run_cloc_snapshot(
                blobs,
                blob_contents,
                cloc_bin=cloc_bin,
                cloc_timeout_seconds=cloc_timeout_seconds,
                cloc_temp_root=cloc_temp_root,
                keep_cloc_temp=keep_cloc_temp,
                snapshot_key=snapshot_key,
                cloc_version=cloc_version,
            )
            result["cloc_runtime_seconds"] = cloc_metrics.runtime_seconds
            result["python_file_count_cloc"] = cloc_metrics.python_file_count
            result["python_file_count_cloc_matches_git"] = (
                cloc_metrics.python_file_count == len(blobs)
            )
            result["cloc_blank_lines"] = cloc_metrics.blank_lines
            result["cloc_comment_lines"] = cloc_metrics.comment_lines
            result["ncloc_py_cloc"] = cloc_metrics.code_lines
            result["cloc_status"] = "success"
        except subprocess.TimeoutExpired as exc:
            message = str(exc)
            result["cloc_status"] = "cloc_timeout"
            result["cloc_error_message"] = message
            add_snapshot_issue(
                issues,
                result,
                backend="cloc",
                path="",
                blob_oid="",
                blob_size=pd.NA,
                issue_stage="cloc_execution",
                issue_type=type(exc).__name__,
                issue_message=message,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            result["cloc_status"] = "cloc_failed"
            result["cloc_error_message"] = message
            add_snapshot_issue(
                issues,
                result,
                backend="cloc",
                path="",
                blob_oid="",
                blob_size=pd.NA,
                issue_stage="cloc_execution",
                issue_type=type(exc).__name__,
                issue_message=message,
            )
        except Exception as exc:
            message = str(exc)
            result["cloc_status"] = "cloc_failed"
            result["cloc_error_message"] = message
            add_snapshot_issue(
                issues,
                result,
                backend="cloc",
                path="",
                blob_oid="",
                blob_size=pd.NA,
                issue_stage="cloc_execution",
                issue_type=type(exc).__name__,
                issue_message=message,
            )

        finalize_backend_status(result)
        return result, issues
    except subprocess.TimeoutExpired as exc:
        result["ast_status"] = "git_timeout"
        result["cloc_status"] = "git_timeout"
        result["ast_error_message"] = str(exc)
        result["cloc_error_message"] = str(exc)
        result["status"] = "git_timeout"
        result["error_stage"] = "git_object_read"
        result["error_message"] = str(exc)
        return result, issues
    except Exception as exc:
        logging.exception(
            "Two-method measurement failed for %s at %s",
            result["repo_name"],
            commit_sha,
        )
        result["status"] = "measurement_failed"
        result["error_stage"] = "local_git_measurement"
        result["error_message"] = str(exc)
        if result["ast_status"] == "pending":
            result["ast_status"] = "measurement_failed"
            result["ast_error_message"] = str(exc)
        if result["cloc_status"] == "pending":
            result["cloc_status"] = "measurement_failed"
            result["cloc_error_message"] = str(exc)
        return result, issues
    finally:
        result["scan_completed_at"] = utc_now()
        result["runtime_seconds"] = round(time.monotonic() - started, 3)


def build_completed_manifest(
    manifest: pd.DataFrame, results: pd.DataFrame
) -> pd.DataFrame:
    """Merge current AST/cloc results into the full Model C manifest."""
    identity_columns = {
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
        "scan_scope",
        "metric_definition",
        "cloc_metric_definition",
        "python_file_count_manifest",
    }
    result_columns = [
        column
        for column in RESULT_COLUMNS
        if column not in identity_columns and column != "ncloc_py"
    ]
    available = [column for column in result_columns if column in results.columns]
    result_subset = results[["snapshot_key", *available]].copy()
    if "ncloc_py" in results.columns:
        result_subset["ncloc_py_measured"] = pd.to_numeric(
            results["ncloc_py"], errors="coerce"
        )

    merged = manifest.merge(result_subset, on="snapshot_key", how="left")
    merged["ncloc_py_status_original"] = merged["ncloc_py_status"]
    merged["ncloc_py_original"] = merged["ncloc_py"]
    merged["ncloc_py"] = pd.to_numeric(
        merged.get("ncloc_py_measured"), errors="coerce"
    )
    if "ncloc_py_measured" in merged.columns:
        merged = merged.drop(columns=["ncloc_py_measured"])

    ast_status = merged.get(
        "ast_status", pd.Series(index=merged.index, dtype="object")
    ).fillna("pending")
    cloc_status = merged.get(
        "cloc_status", pd.Series(index=merged.index, dtype="object")
    ).fillna("pending")
    merged["ncloc_py_status"] = ast_status
    merged["ncloc_py_cloc_status"] = cloc_status
    merged["ncloc_py_ast"] = pd.to_numeric(
        merged.get("ncloc_py_ast"), errors="coerce"
    )
    merged["ncloc_py_cloc"] = pd.to_numeric(
        merged.get("ncloc_py_cloc"), errors="coerce"
    )
    merged["ncloc_py_available"] = ast_status.eq("success") & merged[
        "ncloc_py_ast"
    ].notna()
    merged["ncloc_py_cloc_available"] = cloc_status.eq("success") & merged[
        "ncloc_py_cloc"
    ].notna()
    merged["ncloc_py_both_available"] = (
        merged["ncloc_py_available"] & merged["ncloc_py_cloc_available"]
    )
    merged["ncloc_py_source"] = merged["ncloc_py_available"].map(
        {
            True: "run-x-b01-v4-local-git-ast-tokenize",
            False: "",
        }
    )
    merged["ncloc_py_cloc_source"] = merged["ncloc_py_cloc_available"].map(
        {
            True: "run-x-b01-v4-cloc-default-same-python-files",
            False: "",
        }
    )
    return merged.sort_values("manifest_order", kind="stable").reset_index(drop=True)


def load_sonarqube_reference(path: Path) -> pd.DataFrame:
    """Load successful rows from the preserved SonarQube result file."""
    input_path = path.expanduser().resolve()
    if not input_path.exists() or input_path.stat().st_size == 0:
        return pd.DataFrame()
    reference = pd.read_csv(input_path)
    required = {"snapshot_key", "status", "ncloc_py"}
    if not required.issubset(reference.columns):
        logging.warning(
            "Ignoring SonarQube reference without required columns: %s", input_path
        )
        return pd.DataFrame()
    reference["ncloc_py"] = pd.to_numeric(reference["ncloc_py"], errors="coerce")
    reference = reference[
        reference["status"].eq("success") & reference["ncloc_py"].notna()
    ].copy()
    if reference["snapshot_key"].duplicated().any():
        reference = reference.drop_duplicates("snapshot_key", keep="last")
    return reference


def build_backend_comparison(
    results: pd.DataFrame, sonar_reference: pd.DataFrame
) -> pd.DataFrame:
    """Compare successful AST, cloc, and optional SonarQube measurements."""
    if results.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    local = results[
        results["ast_status"].eq("success")
        & results["cloc_status"].eq("success")
        & pd.to_numeric(results["ncloc_py_ast"], errors="coerce").notna()
        & pd.to_numeric(results["ncloc_py_cloc"], errors="coerce").notna()
    ].copy()
    if local.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    comparison = local[
        [
            "snapshot_key",
            "dataset_source",
            "repo_name",
            "commit_sha",
            "python_file_count_git",
            "python_file_count_cloc",
            "ncloc_py_ast",
            "ncloc_py_cloc",
        ]
    ].copy()
    comparison["ncloc_py_ast"] = pd.to_numeric(
        comparison["ncloc_py_ast"], errors="coerce"
    )
    comparison["ncloc_py_cloc"] = pd.to_numeric(
        comparison["ncloc_py_cloc"], errors="coerce"
    )

    if not sonar_reference.empty:
        sonar_columns = ["snapshot_key", "ncloc_py"]
        if "python_file_count_git" in sonar_reference.columns:
            sonar_columns.append("python_file_count_git")
        sonar = sonar_reference[sonar_columns].copy().rename(
            columns={
                "ncloc_py": "ncloc_py_sonarqube",
                "python_file_count_git": "python_file_count_sonarqube_scan",
            }
        )
        comparison = comparison.merge(sonar, on="snapshot_key", how="left")
    else:
        comparison["ncloc_py_sonarqube"] = pd.NA
        comparison["python_file_count_sonarqube_scan"] = pd.NA

    if "python_file_count_sonarqube_scan" not in comparison.columns:
        comparison["python_file_count_sonarqube_scan"] = pd.NA
    comparison["ncloc_py_sonarqube"] = pd.to_numeric(
        comparison.get("ncloc_py_sonarqube"), errors="coerce"
    )
    comparison["ncloc_py_ast_minus_cloc"] = (
        comparison["ncloc_py_ast"] - comparison["ncloc_py_cloc"]
    )
    comparison["sonar_minus_ast"] = (
        comparison["ncloc_py_sonarqube"] - comparison["ncloc_py_ast"]
    )
    comparison["sonar_minus_cloc"] = (
        comparison["ncloc_py_sonarqube"] - comparison["ncloc_py_cloc"]
    )
    comparison["exact_match_ast_cloc"] = comparison[
        "ncloc_py_ast_minus_cloc"
    ].eq(0)
    sonar_available = comparison["ncloc_py_sonarqube"].notna()
    comparison["exact_match_ast_sonar"] = pd.Series(
        pd.NA, index=comparison.index, dtype="boolean"
    )
    comparison.loc[sonar_available, "exact_match_ast_sonar"] = comparison.loc[
        sonar_available, "sonar_minus_ast"
    ].eq(0)
    comparison["exact_match_cloc_sonar"] = pd.Series(
        pd.NA, index=comparison.index, dtype="boolean"
    )
    comparison.loc[sonar_available, "exact_match_cloc_sonar"] = comparison.loc[
        sonar_available, "sonar_minus_cloc"
    ].eq(0)
    comparison["_abs_delta"] = comparison["ncloc_py_ast_minus_cloc"].abs()
    comparison = comparison.sort_values(
        ["_abs_delta", "dataset_source", "repo_name", "commit_sha"],
        ascending=[False, True, True, True],
        kind="stable",
    ).drop(columns=["_abs_delta"])
    return ensure_columns(comparison, COMPARISON_COLUMNS)


def build_qc_records(
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    completed: pd.DataFrame,
    file_issues: pd.DataFrame,
    comparison: pd.DataFrame,
    structural_checks: list[dict[str, Any]],
    counters: RunCounters,
    *,
    dry_run: bool,
    cloc_version: str,
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
        if not results.empty
        else {}
    )
    manifest_keys = set(manifest["snapshot_key"].astype(str))
    result_keys = (
        set(results["snapshot_key"].dropna().astype(str))
        if not results.empty
        else set()
    )
    orphan_result_rows = len(result_keys - manifest_keys)
    ast_success = completed[completed["ncloc_py_available"]].copy()
    cloc_success = completed[completed["ncloc_py_cloc_available"]].copy()
    both_success = completed[completed["ncloc_py_both_available"]].copy()
    unresolved = completed[~completed["ncloc_py_both_available"]].copy()
    manifest_mismatch = int(
        completed.get(
            "python_file_count_matches_manifest",
            pd.Series(index=completed.index, dtype="boolean"),
        )
        .eq(False)
        .fillna(False)
        .sum()
    )
    cloc_file_mismatch = int(
        completed.get(
            "python_file_count_cloc_matches_git",
            pd.Series(index=completed.index, dtype="boolean"),
        )
        .eq(False)
        .fillna(False)
        .sum()
    )
    duplicate_snapshot_keys = int(completed["snapshot_key"].duplicated().sum())
    negative_ast = int(
        (pd.to_numeric(ast_success["ncloc_py_ast"], errors="coerce") < 0).sum()
    )
    negative_cloc = int(
        (pd.to_numeric(cloc_success["ncloc_py_cloc"], errors="coerce") < 0).sum()
    )
    both_coverage = int(both_success["repo_month_rows"].sum())
    ast_issue_rows = (
        int(file_issues["backend"].eq("ast_tokenize").sum())
        if not file_issues.empty
        else 0
    )
    ast_issue_snapshots = (
        int(
            file_issues.loc[
                file_issues["backend"].eq("ast_tokenize"), "snapshot_key"
            ].nunique()
        )
        if not file_issues.empty
        else 0
    )
    cloc_issue_snapshots = (
        int(
            file_issues.loc[
                file_issues["backend"].eq("cloc"), "snapshot_key"
            ].nunique()
        )
        if not file_issues.empty
        else 0
    )
    comparison_rows = len(comparison)
    exact_ast_cloc = (
        int(comparison["exact_match_ast_cloc"].fillna(False).sum())
        if not comparison.empty
        else 0
    )
    sonar_rows = (
        int(comparison["ncloc_py_sonarqube"].notna().sum())
        if not comparison.empty
        else 0
    )

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
    )
    add_check(
        "duplicate_snapshot_keys",
        "pass" if duplicate_snapshot_keys == 0 else "fail",
        duplicate_snapshot_keys,
        0,
    )
    add_check(
        "negative_ncloc_py_ast_values",
        "pass" if negative_ast == 0 else "fail",
        negative_ast,
        0,
    )
    add_check(
        "negative_ncloc_py_cloc_values",
        "pass" if negative_cloc == 0 else "fail",
        negative_cloc,
        0,
    )
    add_check(
        "manifest_vs_git_python_file_mismatches",
        "warn" if manifest_mismatch > 0 else "pass",
        manifest_mismatch,
        0,
        "Mismatches are retained for review and do not silently change the manifest.",
    )
    add_check(
        "git_vs_cloc_python_file_mismatches",
        "warn" if cloc_file_mismatch > 0 else "pass",
        cloc_file_mismatch,
        0,
        "cloc must count the exact same materialized tracked-Python files.",
    )
    add_check(
        "ast_source_issue_files",
        "warn" if ast_issue_rows > 0 else "pass",
        ast_issue_rows,
        0,
        "Strict decode/tokenize/AST failures leave the AST metric unavailable.",
    )
    add_check(
        "ast_source_issue_snapshots",
        "warn" if ast_issue_snapshots > 0 else "pass",
        ast_issue_snapshots,
        0,
    )
    add_check(
        "cloc_issue_snapshots",
        "warn" if cloc_issue_snapshots > 0 else "pass",
        cloc_issue_snapshots,
        0,
    )
    add_check(
        "ast_cloc_comparison_rows",
        "pass" if comparison_rows > 0 else "warn",
        comparison_rows,
        "at least 1" if not dry_run else "dry_run",
    )
    add_check(
        "ast_cloc_exact_matches",
        "pass" if comparison_rows > 0 and exact_ast_cloc == comparison_rows else "warn",
        exact_ast_cloc,
        comparison_rows,
        "Differences are expected when cloc classifies strings differently from AST.",
    )
    add_check(
        "sonarqube_diagnostic_rows",
        "pass" if sonar_rows > 0 else "warn",
        sonar_rows,
        "at least 1" if not dry_run else "dry_run",
        "SonarQube is diagnostic only and is not a Model C input.",
    )
    add_check(
        "ast_successful_snapshots",
        "pass" if len(ast_success) == len(manifest) and not dry_run else "warn",
        len(ast_success),
        len(manifest) if not dry_run else "dry_run",
    )
    add_check(
        "cloc_successful_snapshots",
        "pass" if len(cloc_success) == len(manifest) and not dry_run else "warn",
        len(cloc_success),
        len(manifest) if not dry_run else "dry_run",
    )
    add_check(
        "both_successful_snapshots",
        "pass" if len(unresolved) == 0 and not dry_run else "warn",
        len(both_success),
        len(manifest) if not dry_run else "dry_run",
    )
    add_check(
        "unresolved_for_either_method",
        "pass" if len(unresolved) == 0 and not dry_run else "warn",
        len(unresolved),
        0 if not dry_run else "dry_run",
    )
    add_check(
        "both_successful_repo_month_coverage",
        "pass"
        if both_coverage == int(manifest["repo_month_rows"].sum()) and not dry_run
        else "warn",
        both_coverage,
        int(manifest["repo_month_rows"].sum()) if not dry_run else "dry_run",
    )

    summary_records: list[dict[str, Any]] = []

    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_records.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "cloc_version", cloc_version)
    add_summary("definition", "target", "model_c_python_only_ncloc")
    add_summary("definition", "count_backend", COUNT_BACKEND)
    add_summary("definition", "scan_scope", SCAN_SCOPE)
    add_summary("definition", "ast_metric", AST_METRIC_DEFINITION)
    add_summary("definition", "cloc_metric", CLOC_METRIC_DEFINITION)
    add_summary("definition", "primary_metric", "ncloc_py_ast")
    add_summary("definition", "robustness_metric", "ncloc_py_cloc")
    add_summary("definition", "sonarqube_role", "diagnostic_reference_only")
    add_summary("definition", "checkout_method", "none_main_clone_unchanged")
    add_summary("definition", "git_file_listing", "git_ls_tree")
    add_summary("definition", "git_blob_reader", "git_cat_file_batch")
    add_summary("definition", "string_expression_detection", "python_ast")
    add_summary("definition", "comment_detection", "python_tokenize")
    add_summary("definition", "cloc_mode", "default_python_by_file_skip_uniqueness")
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
    add_summary("result", "ast_successful_snapshots", len(ast_success))
    add_summary("result", "cloc_successful_snapshots", len(cloc_success))
    add_summary("result", "both_successful_snapshots", len(both_success))
    add_summary("result", "unresolved_for_either_method", len(unresolved))
    add_summary("result", "both_successful_repo_month_coverage", both_coverage)
    add_summary("qc", "manifest_vs_git_python_file_mismatches", manifest_mismatch)
    add_summary("qc", "git_vs_cloc_python_file_mismatches", cloc_file_mismatch)
    add_summary("qc", "ast_source_issue_files", ast_issue_rows)
    add_summary("qc", "ast_source_issue_snapshots", ast_issue_snapshots)
    add_summary("qc", "cloc_issue_snapshots", cloc_issue_snapshots)
    add_summary("comparison", "ast_cloc_rows", comparison_rows)
    add_summary("comparison", "ast_cloc_exact_matches", exact_ast_cloc)
    add_summary("comparison", "sonarqube_diagnostic_rows", sonar_rows)
    if not comparison.empty:
        delta = pd.to_numeric(
            comparison["ncloc_py_ast_minus_cloc"], errors="coerce"
        ).dropna()
        add_summary("comparison", "ast_greater_than_cloc", int((delta > 0).sum()))
        add_summary("comparison", "ast_less_than_cloc", int((delta < 0).sum()))
        add_summary("comparison", "delta_min", delta.min() if not delta.empty else "")
        add_summary("comparison", "delta_median", delta.median() if not delta.empty else "")
        add_summary("comparison", "delta_mean", delta.mean() if not delta.empty else "")
        add_summary("comparison", "delta_max", delta.max() if not delta.empty else "")
        sonar_subset = comparison[comparison["ncloc_py_sonarqube"].notna()]
        add_summary(
            "comparison",
            "exact_match_ast_sonar",
            int(sonar_subset["exact_match_ast_sonar"].astype("boolean").fillna(False).sum()),
        )
        add_summary(
            "comparison",
            "exact_match_cloc_sonar",
            int(sonar_subset["exact_match_cloc_sonar"].astype("boolean").fillna(False).sum()),
        )

    for source, metric_names in [
        (
            ast_success,
            [
                "ncloc_py_before_string_expr_exclusion",
                "string_expr_ncloc_lines",
                "ncloc_py_ast",
            ],
        ),
        (cloc_success, ["cloc_blank_lines", "cloc_comment_lines", "ncloc_py_cloc"]),
    ]:
        if source.empty:
            continue
        for metric_name in metric_names:
            if metric_name not in source.columns:
                continue
            values = pd.to_numeric(source[metric_name], errors="coerce").dropna()
            add_summary(metric_name, "min", values.min() if not values.empty else "")
            add_summary(metric_name, "median", values.median() if not values.empty else "")
            add_summary(metric_name, "mean", values.mean() if not values.empty else "")
            add_summary(metric_name, "max", values.max() if not values.empty else "")

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
    completed_count = counters.processed_this_run + counters.skipped_existing_success
    rate_per_hour = completed_count / elapsed * 3600 if completed_count else 0.0
    remaining = max(total - completed_count, 0)
    eta_hours = remaining / rate_per_hour if rate_per_hour > 0 else float("nan")
    eta_text = f"{eta_hours:.2f}" if eta_hours == eta_hours else "unknown"
    return (
        f"Progress: {completed_count}/{total}; position={position}; "
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
            "Compute AST/tokenize and cloc Python-only NCLOC over the exact same "
            "historical tracked-Python snapshots for Model C."
        )
    )
    parser.add_argument("--input-manifest-file", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-output", type=Path, required=True)
    parser.add_argument("--snapshot-results-output", type=Path, required=True)
    parser.add_argument("--completed-manifest-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--scan-qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--file-issues-output", type=Path, required=True)
    parser.add_argument("--sonarqube-reference-file", type=Path, required=True)
    parser.add_argument("--backend-comparison-output", type=Path, required=True)
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--cloc-bin", default="cloc")
    parser.add_argument("--cloc-timeout-seconds", type=int, default=300)
    parser.add_argument("--cloc-temp-root", type=Path, required=True)
    parser.add_argument("--keep-cloc-temp", action="store_true")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--start-order", type=int, default=1)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process the first N selected snapshots; 0 means all.",
    )
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
    return parser.parse_args()


def validate_cli_args(args: argparse.Namespace) -> None:
    """Validate numeric CLI arguments before reading data."""
    for name in [
        "git_timeout_seconds",
        "cloc_timeout_seconds",
        "progress_every",
        "limit",
    ]:
        value = int(getattr(args, name))
        if value < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative.")
    if args.git_timeout_seconds == 0 and not args.dry_run:
        raise ValueError("--git-timeout-seconds must be positive for a real run.")
    if args.cloc_timeout_seconds == 0 and not args.dry_run:
        raise ValueError("--cloc-timeout-seconds must be positive for a real run.")
    if args.start_order < 1:
        raise ValueError("--start-order must be at least 1.")


def main() -> int:
    """Run the Model C two-method Python NCLOC workflow."""
    args = parse_args()
    validate_cli_args(args)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if not args.skip_self_test:
        run_internal_self_test()

    if args.dry_run:
        cloc_version = "not_checked_dry_run"
    else:
        version_process = run_text_command(
            [args.cloc_bin, "--version"], timeout=args.cloc_timeout_seconds
        )
        cloc_version = (
            version_process.stdout.strip() or version_process.stderr.strip() or "unknown"
        )
        logging.info("cloc version: %s", cloc_version)

    input_path = args.input_manifest_file.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Model C snapshot manifest not found: {input_path}")

    raw_manifest = pd.read_csv(input_path)
    manifest = normalize_input_manifest(raw_manifest)
    structural_checks = expected_count_checks(manifest, args)
    save_dataframe(manifest, args.snapshot_manifest_output)

    selected = filter_targets(manifest, args)
    counters = RunCounters(selected_targets=len(selected))
    results = load_existing_results(args.snapshot_results_output)
    file_issues = load_existing_file_issues(args.file_issues_output)
    run_started = time.monotonic()

    successful_keys: set[str] = set()
    if not results.empty and not args.analysis_again:
        success_mask = (
            results["status"].eq("success")
            & results["ast_status"].eq("success")
            & results["cloc_status"].eq("success")
            & pd.to_numeric(results["ncloc_py_ast"], errors="coerce").notna()
            & pd.to_numeric(results["ncloc_py_cloc"], errors="coerce").notna()
        )
        successful_keys = set(results.loc[success_mask, "snapshot_key"].astype(str))

    for position, (_, target) in enumerate(selected.iterrows(), start=1):
        snapshot_key = str(target["snapshot_key"])
        if snapshot_key in successful_keys and not args.analysis_again:
            counters.skipped_existing_success += 1
            if position % max(args.progress_every, 1) == 0 or position == len(selected):
                logging.info(
                    progress_message(position, len(selected), counters, run_started)
                )
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
                    "cloc_version": cloc_version,
                    "ast_status": "dry_run",
                    "cloc_status": "dry_run",
                    "status": "dry_run",
                }
            )
            issues: list[dict[str, Any]] = []
        else:
            result, issues = run_local_git_snapshot(
                target,
                existing_results=results,
                git_timeout_seconds=args.git_timeout_seconds,
                cloc_bin=args.cloc_bin,
                cloc_version=cloc_version,
                cloc_timeout_seconds=args.cloc_timeout_seconds,
                cloc_temp_root=args.cloc_temp_root.expanduser().resolve(),
                keep_cloc_temp=args.keep_cloc_temp,
            )

        results = upsert_result(results, result)
        file_issues = replace_snapshot_issues(file_issues, snapshot_key, issues)
        save_dataframe(
            results.sort_values("manifest_order", kind="stable"),
            args.snapshot_results_output,
        )
        save_dataframe(file_issues, args.file_issues_output)
        counters.processed_this_run += 1
        if result["status"] == "success":
            counters.successful_this_run += 1
            logging.info(
                "Success: %s at %s -> AST=%s; cloc=%s; delta=%s; "
                "excluded_string_lines=%s",
                target["repo_name"],
                str(target["commit_sha"])[:12],
                result["ncloc_py_ast"],
                result["ncloc_py_cloc"],
                result["ncloc_py_ast_minus_cloc"],
                result["string_expr_ncloc_lines"],
            )
        elif result["status"] != "dry_run":
            counters.failed_this_run += 1
            logging.warning(
                "Unresolved: %s at %s -> status=%s; AST=%s; cloc=%s; message=%s",
                target["repo_name"],
                str(target["commit_sha"])[:12],
                result["status"],
                result["ast_status"],
                result["cloc_status"],
                result["error_message"],
            )

        if position % max(args.progress_every, 1) == 0 or position == len(selected):
            logging.info(progress_message(position, len(selected), counters, run_started))

    results = results.sort_values("manifest_order", kind="stable").reset_index(drop=True)
    save_dataframe(results, args.snapshot_results_output)
    save_dataframe(file_issues, args.file_issues_output)

    completed = build_completed_manifest(manifest, results)
    unresolved = completed[~completed["ncloc_py_both_available"]].copy()
    save_dataframe(completed, args.completed_manifest_output)
    save_dataframe(unresolved, args.unresolved_output)

    sonar_reference = load_sonarqube_reference(args.sonarqube_reference_file)
    comparison = build_backend_comparison(results, sonar_reference)
    save_dataframe(comparison, args.backend_comparison_output)

    qc, summary = build_qc_records(
        manifest,
        results,
        completed,
        file_issues,
        comparison,
        structural_checks,
        counters,
        dry_run=args.dry_run,
        cloc_version=cloc_version,
    )
    save_dataframe(qc, args.scan_qc_output)
    save_dataframe(summary, args.summary_output)

    ast_count = int(completed["ncloc_py_available"].sum())
    cloc_count = int(completed["ncloc_py_cloc_available"].sum())
    both_count = int(completed["ncloc_py_both_available"].sum())
    both_coverage = int(
        completed.loc[completed["ncloc_py_both_available"], "repo_month_rows"].sum()
    )
    logging.info(
        "Completed run-x-b01-v4: AST=%d/%d; cloc=%d/%d; both=%d/%d; "
        "both coverage=%d/%d repo-month rows; unresolved=%d; comparisons=%d",
        ast_count,
        len(manifest),
        cloc_count,
        len(manifest),
        both_count,
        len(manifest),
        both_coverage,
        int(manifest["repo_month_rows"].sum()),
        len(unresolved),
        len(comparison),
    )

    if args.fail_on_unresolved and len(unresolved) > 0:
        logging.error(
            "Fail-on-unresolved requested and %d snapshots lack one or both methods.",
            len(unresolved),
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
        logging.exception("run-x-b01-v4 failed: %s", exc)
        raise SystemExit(1)
