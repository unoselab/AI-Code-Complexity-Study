#!/usr/bin/env python3
"""
Collect monthly lines added inside Python function implementation bodies.

The primary metric is a flow measure:

    lines_added_py_function_body

For every repository-month in the run-x-a05 Model A panel, the script walks the
Git commits assigned to that calendar month, compares each commit with its first
parent, identifies added physical lines in tracked Python files, and attributes
those lines to post-change Python function bodies.

Important design rules:
- Preserve the run-x-a/run-x-b monthly flow semantics.
- Use committed timestamps in America/Chicago by default.
- Count all commits reachable from the selected analysis tip.
- Compare merge commits with their first parent only.
- Do not count root-commit additions, matching the original lines-added logic.
- Include module functions, methods, async functions, and nested functions.
- Attribute an added line to the innermost containing function.
- Exclude decorators, function headers, and leading function docstrings.
- Count comments and blank physical lines when they are inside a function body.
- A one-line function such as ``def f(): return 1`` contributes one body line.
- Carry forward code state only; never carry forward monthly activity.
- A month with no commits has lines_added_py_function_body = 0.

The script can reuse safe function boundaries from run-x-d01 metadata when the
exact Python blob was already parsed and no nested named definition was present.
The reusable body store is treated as read-only and used only to verify that the
D01 boundary record still points to a saved body. New or unsafe blobs are parsed
with the configured AST Python runtime and cached by Git blob OID.
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
import sqlite3
import subprocess
import sys
import tempfile
import time
import tokenize
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Optional, Sequence
from zoneinfo import ZoneInfo

AST_WORKER_STREAM_MODE = "--ast-worker-stream" in sys.argv
AST_WORKER_MODE = "--ast-worker" in sys.argv or AST_WORKER_STREAM_MODE

if not AST_WORKER_MODE:
    import numpy as np
    import pandas as pd

IMPLEMENTATION_VERSION = "v1"
AST_WORKER_PROTOCOL_VERSION = "e01-v1"
EXPECTED_DATASET_SOURCES = {"treatment", "control"}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "site-packages",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

REQUIRED_PANEL_COLUMNS = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "commits",
    "lines_added",
    "latest_commit_effective",
    "clone_path",
}

REPO_MONTH_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "time_index",
    "commits_original",
    "commits_recomputed",
    "commits_match_original",
    "lines_added_original",
    "lines_added_repo_recomputed",
    "lines_added_repo_match_original",
    "lines_added_py_total",
    "lines_added_py_function_body",
    "lines_added_py_function_signature_or_decorator",
    "lines_added_py_function_leading_docstring",
    "lines_added_py_outside_function",
    "lines_added_py_unclassified",
    "lines_removed_repo_recomputed",
    "python_commits_in_month",
    "python_files_changed",
    "functions_touched_by_added_lines",
    "commits_with_py_function_body_additions",
    "latest_commit_effective",
    "commit_resolution",
    "months_since_observed_commit",
    "analysis_tip_commit",
    "analysis_timezone",
    "function_metric_parse_complete",
    "history_reconciliation_complete",
    "model_e_complete",
    "function_line_metric_status",
    "issue_count",
]

COMMIT_COLUMNS = [
    "repo_name",
    "dataset_source",
    "commit_sha",
    "first_parent_sha",
    "commit_time_epoch",
    "commit_time_local",
    "commit_month",
    "is_merge_commit",
    "is_root_commit",
    "lines_added_repo_recomputed",
    "lines_removed_repo_recomputed",
    "lines_added_py_total",
    "lines_added_py_function_body",
    "lines_added_py_function_signature_or_decorator",
    "lines_added_py_function_leading_docstring",
    "lines_added_py_outside_function",
    "lines_added_py_unclassified",
    "python_files_changed",
    "functions_touched_by_added_lines",
    "diff_status",
    "parse_complete",
    "runtime_seconds",
]

FILE_COLUMNS = [
    "repo_name",
    "dataset_source",
    "commit_sha",
    "commit_month",
    "change_status",
    "old_path",
    "new_path",
    "post_blob_oid",
    "source_encoding",
    "boundary_source",
    "parse_status",
    "parse_error_type",
    "parse_error_message",
    "lines_added_py_total",
    "lines_added_py_function_body",
    "lines_added_py_function_signature_or_decorator",
    "lines_added_py_function_leading_docstring",
    "lines_added_py_outside_function",
    "lines_added_py_unclassified",
    "functions_touched_by_added_lines",
]

FUNCTION_COLUMNS = [
    "repo_name",
    "dataset_source",
    "commit_sha",
    "commit_month",
    "path",
    "post_blob_oid",
    "qualified_name",
    "function_kind",
    "nesting_depth",
    "decorated_start_line",
    "function_start_line",
    "body_start_line",
    "body_end_line",
    "added_body_line_count",
    "added_body_line_numbers",
    "boundary_source",
]

ISSUE_COLUMNS = [
    "repo_name",
    "dataset_source",
    "time",
    "commit_sha",
    "path",
    "stage",
    "error_type",
    "error_message",
    "lines_added_affected",
    "resolution_status",
]

RECONCILIATION_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "time",
    "commits_original",
    "commits_recomputed",
    "commits_delta",
    "lines_added_original",
    "lines_added_repo_recomputed",
    "lines_added_delta",
    "commits_match_original",
    "lines_added_repo_match_original",
    "function_metric_parse_complete",
    "history_reconciliation_complete",
    "model_e_complete",
]


class StageError(RuntimeError):
    """Represent a recoverable stage-specific processing error."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass(frozen=True)
class FunctionBoundary:
    """Line-oriented boundary metadata for one Python function occurrence."""

    qualified_name: str
    function_name: str
    function_kind: str
    occurrence_index: int
    nesting_depth: int
    decorated_start_line: int
    function_start_line: int
    function_end_line: int
    body_start_line: int
    body_end_line: int
    leading_docstring_start_line: int
    leading_docstring_end_line: int
    contains_nested_named_definition: bool

    @property
    def span_size(self) -> int:
        return self.function_end_line - self.decorated_start_line


@dataclass(frozen=True)
class ChangedPath:
    """One path-level change between a commit and its first parent."""

    status: str
    old_path: str
    new_path: str


@dataclass
class BoundaryResult:
    """Cached result for one post-change Python blob."""

    status: str
    source: str
    encoding: str
    boundaries: list[FunctionBoundary]
    error_type: str = ""
    error_message: str = ""


@dataclass
class D01BoundaryRecord:
    """Safe D01 boundary data grouped by blob OID."""

    boundaries: list[FunctionBoundary]
    body_paths: list[str]
    safe_for_reuse: bool


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_repo_key(dataset_source: str, repo_name: str) -> str:
    payload = f"{dataset_source}|{repo_name.casefold()}"
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{dataset_source}__{repo_name}")
    return f"{readable}__{sha256_text(payload)[:16]}"


def write_csv_rows(path: Path, rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_command(
    command: Sequence[str],
    *,
    timeout: int,
    cwd: Optional[Path] = None,
    text: bool = False,
    input_data: Optional[bytes | str] = None,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        text=text,
    )


def git_text(clone_path: Path, args: Sequence[str], timeout: int) -> str:
    process = run_command(["git", "-C", str(clone_path), *args], timeout=timeout, text=True)
    if process.returncode != 0:
        raise StageError("git", process.stderr.strip() or "git command failed")
    return process.stdout


def git_bytes(clone_path: Path, args: Sequence[str], timeout: int) -> bytes:
    process = run_command(["git", "-C", str(clone_path), *args], timeout=timeout, text=False)
    if process.returncode != 0:
        raise StageError(
            "git", process.stderr.decode("utf-8", errors="replace").strip() or "git command failed"
        )
    return process.stdout


def validate_clone(clone_path: Path, timeout: int) -> tuple[bool, str]:
    if not clone_path.exists():
        return False, "clone_path_missing"
    try:
        result = git_text(clone_path, ["rev-parse", "--git-dir"], timeout)
    except Exception as exc:
        return False, f"not_git_repository:{exc}"
    return bool(result.strip()), "ready"


def commit_exists(clone_path: Path, commit_sha: str, timeout: int) -> bool:
    process = run_command(
        ["git", "-C", str(clone_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        timeout=timeout,
    )
    return process.returncode == 0


def path_is_python(path_text: str) -> bool:
    if not path_text:
        return False
    path = PurePosixPath(path_text)
    if not path.name.lower().endswith(".py"):
        return False
    return not any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts[:-1])


def decode_python_source(data: bytes) -> tuple[str, str]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding), encoding
    except Exception as exc:
        raise StageError("source_decode", f"{type(exc).__name__}: {exc}") from exc


def statement_child_bodies(statement: ast.stmt) -> Iterator[Sequence[ast.stmt]]:
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(statement, field_name, None)
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
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


def is_docstring_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(getattr(statement, "value", None), ast.Constant)
        and isinstance(statement.value.value, str)
    )


def contains_nested_named_definition(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return True
    return False


def function_kind(node: ast.FunctionDef | ast.AsyncFunctionDef, scope_kinds: Sequence[str]) -> str:
    is_async = isinstance(node, ast.AsyncFunctionDef)
    if scope_kinds and scope_kinds[-1] == "class":
        return "async_method" if is_async else "method"
    if "function" in scope_kinds:
        return "nested_async_function" if is_async else "nested_function"
    return "module_async_function" if is_async else "module_function"


def build_line_offsets(source: str) -> tuple[list[str], list[int], list[int]]:
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
    payload = line.encode("utf-8")
    if byte_col < 0 or byte_col > len(payload):
        raise ValueError(f"Invalid AST byte column: {byte_col}")
    return len(payload[:byte_col].decode("utf-8"))


def locate_suite_start_line(
    source: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: Optional[Sequence[str]] = None,
    source_tokens: Optional[Sequence[tokenize.TokenInfo]] = None,
) -> tuple[int, bool]:
    if source_lines is None:
        lines, _, _ = build_line_offsets(source)
    else:
        lines = list(source_lines)
    if source_tokens is None:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    else:
        tokens = list(source_tokens)
    node_line = int(node.lineno)
    node_char_col = utf8_byte_col_to_char_col(lines[node_line - 1], int(node.col_offset))

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
            return int(token_info.end[0]) + 1, True
        if token_info.type in {tokenize.INDENT, tokenize.DEDENT}:
            continue
        return int(token_info.start[0]), False
    raise StageError("function_boundary", "Could not locate function suite content")


def index_all_functions(source: str, filename: str) -> list[FunctionBoundary]:
    tree = ast.parse(source, filename=filename, type_comments=True)
    source_lines, _, _ = build_line_offsets(source)
    source_tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    occurrence_counts: Counter[str] = Counter()
    records: list[FunctionBoundary] = []

    def walk(
        statements: Sequence[ast.stmt],
        scope_names: list[str],
        scope_kinds: list[str],
    ) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified_name = ".".join([*scope_names, statement.name])
                occurrence_counts[qualified_name] += 1
                suite_start_line, block_suite = locate_suite_start_line(
                    source, statement, source_lines, source_tokens
                )
                leading_docstring = bool(statement.body and is_docstring_statement(statement.body[0]))
                doc_start = 0
                doc_end = 0
                real_body = statement.body
                if leading_docstring:
                    doc = statement.body[0]
                    doc_start = int(doc.lineno)
                    doc_end = int(getattr(doc, "end_lineno", doc.lineno))
                    real_body = statement.body[1:]

                if real_body:
                    first_real = real_body[0]
                    first_real_line = int(first_real.lineno)
                    if leading_docstring:
                        body_start_line = first_real_line if first_real_line == doc_end else doc_end + 1
                    else:
                        body_start_line = suite_start_line if block_suite else first_real_line
                else:
                    body_start_line = int(getattr(statement, "end_lineno", statement.lineno)) + 1

                decorated_start_line = int(statement.lineno)
                if statement.decorator_list:
                    decorated_start_line = min(int(item.lineno) for item in statement.decorator_list)

                records.append(
                    FunctionBoundary(
                        qualified_name=qualified_name,
                        function_name=statement.name,
                        function_kind=function_kind(statement, scope_kinds),
                        occurrence_index=occurrence_counts[qualified_name],
                        nesting_depth=sum(kind == "function" for kind in scope_kinds),
                        decorated_start_line=decorated_start_line,
                        function_start_line=int(statement.lineno),
                        function_end_line=int(getattr(statement, "end_lineno", statement.lineno)),
                        body_start_line=int(body_start_line),
                        body_end_line=int(getattr(statement, "end_lineno", statement.lineno)),
                        leading_docstring_start_line=doc_start,
                        leading_docstring_end_line=doc_end,
                        contains_nested_named_definition=contains_nested_named_definition(statement),
                    )
                )
                walk(
                    statement.body,
                    [*scope_names, statement.name],
                    [*scope_kinds, "function"],
                )
            elif isinstance(statement, ast.ClassDef):
                walk(statement.body, [*scope_names, statement.name], [*scope_kinds, "class"])
            else:
                for child_body in statement_child_bodies(statement):
                    walk(child_body, scope_names, scope_kinds)

    walk(tree.body, [], [])
    return records


def process_ast_worker_request(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
        raise ValueError("Unsupported AST worker protocol version")
    output: list[dict[str, Any]] = []
    for item in request.get("files", []):
        request_index = int(item["request_index"])
        path = str(item["path"])
        try:
            source = base64.b64decode(item["source_utf8_b64"]).decode("utf-8")
            boundaries = index_all_functions(source, path)
            output.append(
                {
                    "request_index": request_index,
                    "path": path,
                    "status": "success",
                    "error_type": "",
                    "error_message": "",
                    "boundaries": [asdict(boundary) for boundary in boundaries],
                }
            )
        except Exception as exc:
            output.append(
                {
                    "request_index": request_index,
                    "path": path,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "boundaries": [],
                }
            )
    return {
        "protocol_version": AST_WORKER_PROTOCOL_VERSION,
        "python_version": sys.version.split()[0],
        "files": output,
    }


def run_ast_worker() -> int:
    request = json.load(sys.stdin)
    json.dump(process_ast_worker_request(request), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def run_ast_worker_stream() -> int:
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            request = json.loads(raw_line)
            response = process_ast_worker_request(request)
        except Exception as exc:
            response = {
                "protocol_version": AST_WORKER_PROTOCOL_VERSION,
                "worker_error_type": type(exc).__name__,
                "worker_error_message": str(exc),
                "files": [],
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


class ASTWorkerClient:
    """Lazy persistent client for the external AST Python runtime."""

    def __init__(self, python_bin: str, timeout: int) -> None:
        self.python_bin = python_bin
        self.timeout = timeout
        self.process: Optional[subprocess.Popen[str]] = None

    def _start(self) -> None:
        if self.process is not None:
            return
        self.process = subprocess.Popen(
            [self.python_bin, str(Path(__file__).resolve()), "--ast-worker-stream"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def request(self, files: Sequence[tuple[str, str]]) -> dict[int, dict[str, Any]]:
        self._start()
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        request = {
            "protocol_version": AST_WORKER_PROTOCOL_VERSION,
            "files": [
                {
                    "request_index": index,
                    "path": path,
                    "source_utf8_b64": base64.b64encode(source.encode("utf-8")).decode("ascii"),
                }
                for index, (path, source) in enumerate(files)
            ],
        }
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            stderr = ""
            if self.process.stderr is not None:
                stderr = self.process.stderr.read()
            raise StageError("ast_worker", stderr.strip() or "AST worker stream ended")
        response = json.loads(response_line)
        if response.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
            raise StageError("ast_worker", "AST worker protocol mismatch")
        if response.get("worker_error_type"):
            raise StageError(
                "ast_worker",
                f"{response.get('worker_error_type')}: {response.get('worker_error_message')}",
            )
        return {int(item["request_index"]): item for item in response.get("files", [])}

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None


def invoke_ast_worker(
    python_bin: str,
    files: Sequence[tuple[str, str]],
    timeout: int,
) -> dict[int, dict[str, Any]]:
    request = {
        "protocol_version": AST_WORKER_PROTOCOL_VERSION,
        "files": [
            {
                "request_index": index,
                "path": path,
                "source_utf8_b64": base64.b64encode(source.encode("utf-8")).decode("ascii"),
            }
            for index, (path, source) in enumerate(files)
        ],
    }
    process = run_command(
        [python_bin, str(Path(__file__).resolve()), "--ast-worker"],
        timeout=timeout,
        text=True,
        input_data=json.dumps(request),
    )
    if process.returncode != 0:
        raise StageError("ast_worker", process.stderr.strip() or "AST worker failed")
    response = json.loads(process.stdout)
    if response.get("protocol_version") != AST_WORKER_PROTOCOL_VERSION:
        raise StageError("ast_worker", "AST worker protocol mismatch")
    return {int(item["request_index"]): item for item in response.get("files", [])}


def boundary_cache_path(root: Path, blob_oid: str) -> Path:
    return root / "boundaries" / blob_oid[:2] / f"{blob_oid}.json"


def load_boundary_cache(root: Path, blob_oid: str) -> Optional[BoundaryResult]:
    path = boundary_cache_path(root, blob_oid)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("cache_schema") != "e01-v1":
            return None
        return BoundaryResult(
            status=str(payload.get("status", "error")),
            source=str(payload.get("source", "cache")),
            encoding=str(payload.get("encoding", "")),
            boundaries=[FunctionBoundary(**item) for item in payload.get("boundaries", [])],
            error_type=str(payload.get("error_type", "")),
            error_message=str(payload.get("error_message", "")),
        )
    except Exception:
        return None


def save_boundary_cache(root: Path, blob_oid: str, result: BoundaryResult) -> None:
    path = boundary_cache_path(root, blob_oid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_schema": "e01-v1",
        "blob_oid": blob_oid,
        "status": result.status,
        "source": result.source,
        "encoding": result.encoding,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "boundaries": [asdict(item) for item in result.boundaries],
    }
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def parse_d01_boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes"}




def d01_input_fingerprint(paths: Sequence[Path]) -> str:
    payload = []
    for path in paths:
        if path.exists():
            stat = path.stat()
            payload.append(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}")
    return sha256_text("\n".join(payload))


def ensure_d01_sqlite_index(
    paths: Sequence[Path],
    db_path: Path,
    body_store_root: Path,
) -> None:
    existing_paths = [path for path in paths if path.exists() and path.stat().st_size > 0]
    if not existing_paths:
        return
    if not body_store_root.exists():
        logging.warning("D01 body store root is missing; D01 reuse is disabled: %s", body_store_root)
        return
    fingerprint = d01_input_fingerprint(existing_paths)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as connection:
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'input_fingerprint'"
                ).fetchone()
                schema = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()
                if row and row[0] == fingerprint and schema and schema[0] == "e01-v1":
                    logging.info("Reusing D01 SQLite boundary index: %s", db_path)
                    return
        except Exception:
            pass
        db_path.unlink(missing_ok=True)

    logging.info("Building D01 SQLite boundary index: %s", db_path)
    temp_path = db_path.with_suffix(".sqlite.tmp")
    temp_path.unlink(missing_ok=True)
    with sqlite3.connect(temp_path) as connection:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            """
            CREATE TABLE boundaries (
                blob_oid TEXT NOT NULL,
                qualified_name TEXT,
                function_name TEXT,
                function_kind TEXT,
                occurrence_index INTEGER,
                function_start_line INTEGER,
                function_end_line INTEGER,
                body_start_line INTEGER,
                body_end_line INTEGER,
                leading_docstring_removed INTEGER,
                contains_nested INTEGER
            )
            """
        )
        total_rows = 0
        for path in existing_paths:
            logging.info("Indexing D01 boundary metadata: %s", path)
            for chunk in pd.read_csv(path, chunksize=200_000, low_memory=False):
                required = {
                    "blob_oid",
                    "qualified_name",
                    "function_name",
                    "function_kind",
                    "occurrence_index",
                    "function_start_line",
                    "function_end_line",
                    "body_start_line",
                    "body_end_line",
                }
                if not required.issubset(chunk.columns):
                    continue
                if "extraction_status" in chunk.columns:
                    chunk = chunk[chunk["extraction_status"].fillna("") == "success"].copy()
                if chunk.empty:
                    continue
                rows = []
                for row in chunk.to_dict("records"):
                    blob_oid = str(row.get("blob_oid", "")).strip()
                    if not blob_oid or blob_oid == "nan":
                        continue
                    try:
                        rows.append(
                            (
                                blob_oid,
                                str(row.get("qualified_name", "")),
                                str(row.get("function_name", "")),
                                str(row.get("function_kind", "")),
                                int(float(row.get("occurrence_index", 1))),
                                int(float(row.get("function_start_line"))),
                                int(float(row.get("function_end_line"))),
                                int(float(row.get("body_start_line"))),
                                int(float(row.get("body_end_line"))),
                                int(parse_d01_boolean(row.get("leading_docstring_removed", False))),
                                int(parse_d01_boolean(row.get("contains_nested_named_definition", False))),
                            )
                        )
                    except (TypeError, ValueError):
                        continue
                connection.executemany(
                    "INSERT INTO boundaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                total_rows += len(rows)
                connection.commit()
        connection.execute("CREATE INDEX boundaries_blob_oid_idx ON boundaries(blob_oid)")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("schema_version", "e01-v1"),
                ("input_fingerprint", fingerprint),
                ("indexed_rows", str(total_rows)),
                ("body_store_root", str(body_store_root)),
            ],
        )
        connection.commit()
    temp_path.replace(db_path)
    logging.info("Built D01 SQLite boundary index with %d rows", total_rows)


def query_d01_boundary_index(
    db_path: Path,
    required_blob_oids: set[str],
) -> dict[str, D01BoundaryRecord]:
    if not db_path.exists() or not required_blob_oids:
        return {}
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    with sqlite3.connect(db_path) as connection:
        oid_list = sorted(required_blob_oids)
        for start in range(0, len(oid_list), 500):
            batch = oid_list[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            query = f"""
                SELECT blob_oid, qualified_name, function_name, function_kind,
                       occurrence_index, function_start_line, function_end_line,
                       body_start_line, body_end_line, leading_docstring_removed,
                       contains_nested
                FROM boundaries
                WHERE blob_oid IN ({placeholders})
                ORDER BY blob_oid, function_start_line, occurrence_index
            """
            for row in connection.execute(query, batch):
                grouped[str(row[0])].append(row)

    output: dict[str, D01BoundaryRecord] = {}
    for blob_oid, rows in grouped.items():
        if any(int(row[10]) == 1 or int(row[9]) == 1 for row in rows):
            continue
        boundaries = []
        for row in rows:
            body_start = int(row[7])
            leading_docstring_removed = int(row[9]) == 1
            boundaries.append(
                FunctionBoundary(
                    qualified_name=str(row[1]),
                    function_name=str(row[2]),
                    function_kind=str(row[3]),
                    occurrence_index=int(row[4]),
                    nesting_depth=0,
                    decorated_start_line=int(row[5]),
                    function_start_line=int(row[5]),
                    function_end_line=int(row[6]),
                    body_start_line=body_start,
                    body_end_line=int(row[8]),
                    leading_docstring_start_line=0,
                    leading_docstring_end_line=max(0, body_start - 1)
                    if leading_docstring_removed
                    else 0,
                    contains_nested_named_definition=False,
                )
            )
        output[blob_oid] = D01BoundaryRecord(
            boundaries=boundaries,
            body_paths=[],
            safe_for_reuse=True,
        )
    return output

def load_d01_boundary_index(
    paths: Sequence[Path],
    body_store_root: Path,
    required_blob_oids: set[str],
) -> dict[str, D01BoundaryRecord]:
    if not paths or not required_blob_oids:
        return {}
    records_by_blob: dict[str, list[dict[str, Any]]] = defaultdict(list)
    body_paths_by_blob: dict[str, list[str]] = defaultdict(list)
    unsafe_blobs: set[str] = set()

    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            continue
        logging.info("Scanning D01 boundary metadata: %s", path)
        for chunk in pd.read_csv(path, chunksize=200_000, low_memory=False):
            if "blob_oid" not in chunk.columns:
                continue
            subset = chunk[chunk["blob_oid"].astype(str).isin(required_blob_oids)].copy()
            if subset.empty:
                continue
            for row in subset.to_dict("records"):
                blob_oid = str(row.get("blob_oid", "")).strip()
                if not blob_oid:
                    continue
                if str(row.get("extraction_status", "success")) != "success":
                    unsafe_blobs.add(blob_oid)
                    continue
                if parse_d01_boolean(row.get("contains_nested_named_definition", False)):
                    unsafe_blobs.add(blob_oid)
                    continue
                body_path_text = str(row.get("body_output_path", "")).strip()
                if body_path_text:
                    body_path = Path(body_path_text)
                    try:
                        body_path.relative_to(body_store_root)
                    except ValueError:
                        unsafe_blobs.add(blob_oid)
                        continue
                    if not body_path.exists():
                        unsafe_blobs.add(blob_oid)
                        continue
                    body_paths_by_blob[blob_oid].append(body_path_text)
                records_by_blob[blob_oid].append(row)

    index: dict[str, D01BoundaryRecord] = {}
    for blob_oid, rows in records_by_blob.items():
        if blob_oid in unsafe_blobs:
            continue
        boundaries: list[FunctionBoundary] = []
        for row in rows:
            start_line = int(float(row["function_start_line"]))
            end_line = int(float(row["function_end_line"]))
            body_start = int(float(row["body_start_line"]))
            body_end = int(float(row["body_end_line"]))
            boundaries.append(
                FunctionBoundary(
                    qualified_name=str(row.get("qualified_name", "")),
                    function_name=str(row.get("function_name", "")),
                    function_kind=str(row.get("function_kind", "")),
                    occurrence_index=int(float(row.get("occurrence_index", 1))),
                    nesting_depth=0,
                    decorated_start_line=start_line,
                    function_start_line=start_line,
                    function_end_line=end_line,
                    body_start_line=body_start,
                    body_end_line=body_end,
                    leading_docstring_start_line=0,
                    leading_docstring_end_line=max(0, body_start - 1)
                    if parse_d01_boolean(row.get("leading_docstring_removed", False))
                    else 0,
                    contains_nested_named_definition=False,
                )
            )
        index[blob_oid] = D01BoundaryRecord(
            boundaries=boundaries,
            body_paths=body_paths_by_blob.get(blob_oid, []),
            safe_for_reuse=True,
        )
    logging.info("Loaded safe D01 boundaries for %d blobs", len(index))
    return index


def list_changed_paths(
    clone_path: Path,
    parent_sha: str,
    commit_sha: str,
    timeout: int,
) -> list[ChangedPath]:
    payload = git_bytes(
        clone_path,
        [
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-M",
            "-C",
            "-z",
            parent_sha,
            commit_sha,
        ],
        timeout,
    )
    parts = payload.split(b"\0")
    output: list[ChangedPath] = []
    index = 0
    while index < len(parts):
        if not parts[index]:
            index += 1
            continue
        status = parts[index].decode("utf-8", errors="surrogateescape")
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(parts):
                break
            old_path = parts[index].decode("utf-8", errors="surrogateescape")
            new_path = parts[index + 1].decode("utf-8", errors="surrogateescape")
            index += 2
        else:
            if index >= len(parts):
                break
            path = parts[index].decode("utf-8", errors="surrogateescape")
            index += 1
            old_path = "" if code == "A" else path
            new_path = "" if code == "D" else path
        output.append(ChangedPath(status=status, old_path=old_path, new_path=new_path))
    return output


def parse_numstat(payload: bytes) -> tuple[int, int]:
    added = 0
    removed = 0
    for raw_line in payload.splitlines():
        fields = raw_line.split(b"\t", 2)
        if len(fields) < 2:
            continue
        if fields[0] != b"-":
            try:
                added += int(fields[0])
            except ValueError:
                pass
        if fields[1] != b"-":
            try:
                removed += int(fields[1])
            except ValueError:
                pass
    return added, removed


def repo_numstat(
    clone_path: Path,
    parent_sha: str,
    commit_sha: str,
    timeout: int,
) -> tuple[int, int]:
    payload = git_bytes(clone_path, ["diff", "--numstat", f"{parent_sha}..{commit_sha}"], timeout)
    return parse_numstat(payload)


def patch_added_line_numbers(
    clone_path: Path,
    parent_sha: str,
    commit_sha: str,
    old_path: str,
    new_path: str,
    timeout: int,
) -> list[int]:
    path_args = [path for path in (old_path, new_path) if path]
    payload = git_bytes(
        clone_path,
        [
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--find-renames",
            parent_sha,
            commit_sha,
            "--",
            *path_args,
        ],
        timeout,
    )
    text = payload.decode("utf-8", errors="replace")
    hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    line_numbers: list[int] = []
    current_new_line: Optional[int] = None
    in_hunk = False
    for line in text.splitlines():
        match = hunk_pattern.match(line)
        if match:
            current_new_line = int(match.group(1))
            in_hunk = True
            continue
        if not in_hunk or current_new_line is None:
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            line_numbers.append(current_new_line)
            current_new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif line.startswith(" "):
            current_new_line += 1
        elif line.startswith("diff --git") or line.startswith("index "):
            in_hunk = False
    return line_numbers


def post_blob_oid(clone_path: Path, commit_sha: str, path: str, timeout: int) -> str:
    output = git_text(clone_path, ["ls-tree", commit_sha, "--", path], timeout).strip()
    if not output:
        return ""
    metadata = output.split("\t", 1)[0].split()
    if len(metadata) < 3 or metadata[1] != "blob":
        return ""
    return metadata[2]


def read_git_blob(clone_path: Path, commit_sha: str, path: str, timeout: int) -> bytes:
    return git_bytes(clone_path, ["show", f"{commit_sha}:{path}"], timeout)


def classify_added_line(
    line_number: int,
    boundaries: Sequence[FunctionBoundary],
) -> tuple[str, Optional[FunctionBoundary]]:
    candidates = [
        boundary
        for boundary in boundaries
        if boundary.decorated_start_line <= line_number <= boundary.function_end_line
    ]
    if not candidates:
        return "outside_function", None
    candidates.sort(
        key=lambda item: (item.nesting_depth, -item.span_size, item.function_start_line),
        reverse=True,
    )
    boundary = candidates[0]
    if (
        boundary.leading_docstring_start_line > 0
        and boundary.leading_docstring_start_line <= line_number <= boundary.leading_docstring_end_line
        and line_number < boundary.body_start_line
    ):
        return "function_leading_docstring", boundary
    if line_number < boundary.body_start_line:
        return "function_signature_or_decorator", boundary
    if line_number <= boundary.body_end_line:
        return "function_body", boundary
    return "outside_function", None


def select_analysis_tip(group: "pd.DataFrame", clone_path: Path, timeout: int) -> tuple[str, str]:
    ordered = group.sort_values(["time_index", "time"], ascending=False)
    for column, method in (
        ("latest_commit_original", "latest_commit_original"),
        ("latest_commit_effective", "latest_commit_effective"),
        ("latest_commit", "latest_commit"),
    ):
        if column not in ordered.columns:
            continue
        for value in ordered[column].tolist():
            commit_sha = str(value).strip().lower()
            if commit_sha and commit_sha != "nan" and commit_exists(clone_path, commit_sha, timeout):
                return commit_sha, method
    head = git_text(clone_path, ["rev-parse", "HEAD"], timeout).strip().lower()
    return head, "head_fallback"


def list_commits_for_months(
    clone_path: Path,
    tip_commit: str,
    requested_months: set[str],
    timezone: ZoneInfo,
    timeout: int,
) -> list[dict[str, Any]]:
    output = git_text(
        clone_path,
        ["rev-list", "--parents", "--timestamp", tip_commit],
        timeout,
    )
    commits: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        epoch = int(parts[0])
        commit_sha = parts[1].lower()
        parents = [item.lower() for item in parts[2:]]
        local_time = datetime.fromtimestamp(epoch, timezone)
        month = local_time.strftime("%Y-%m")
        if month not in requested_months:
            continue
        commits.append(
            {
                "commit_sha": commit_sha,
                "parents": parents,
                "first_parent_sha": parents[0] if parents else "",
                "commit_time_epoch": epoch,
                "commit_time_local": local_time.isoformat(),
                "commit_month": month,
                "is_merge_commit": len(parents) > 1,
                "is_root_commit": len(parents) == 0,
            }
        )
    commits.sort(key=lambda item: (item["commit_time_epoch"], item["commit_sha"]))
    return commits


def collect_required_blob_oids(
    clone_path: Path,
    commits: Sequence[dict[str, Any]],
    timeout: int,
) -> set[str]:
    output: set[str] = set()
    for commit in commits:
        if commit["is_root_commit"]:
            continue
        try:
            changed = list_changed_paths(
                clone_path,
                commit["first_parent_sha"],
                commit["commit_sha"],
                timeout,
            )
        except Exception:
            continue
        for item in changed:
            if not item.new_path or not path_is_python(item.new_path):
                continue
            try:
                oid = post_blob_oid(clone_path, commit["commit_sha"], item.new_path, timeout)
            except Exception:
                oid = ""
            if oid:
                output.add(oid)
    return output


def get_boundaries_for_blob(
    *,
    clone_path: Path,
    commit_sha: str,
    path: str,
    blob_oid: str,
    boundary_cache_root: Path,
    d01_index: dict[str, D01BoundaryRecord],
    ast_python_bin: str,
    git_timeout: int,
    ast_timeout: int,
) -> BoundaryResult:
    cached = load_boundary_cache(boundary_cache_root, blob_oid)
    if cached is not None:
        return cached

    if blob_oid in d01_index and d01_index[blob_oid].safe_for_reuse:
        result = BoundaryResult(
            status="success",
            source="run-x-d01-body-store",
            encoding="d01-recorded",
            boundaries=d01_index[blob_oid].boundaries,
        )
        save_boundary_cache(boundary_cache_root, blob_oid, result)
        return result

    try:
        payload = read_git_blob(clone_path, commit_sha, path, git_timeout)
        source, encoding = decode_python_source(payload)
        response = invoke_ast_worker(ast_python_bin, [(path, source)], ast_timeout)[0]
        if response.get("status") != "success":
            result = BoundaryResult(
                status="error",
                source="e01_ast_worker",
                encoding=encoding,
                boundaries=[],
                error_type=str(response.get("error_type", "ASTError")),
                error_message=str(response.get("error_message", "AST parse failed")),
            )
        else:
            result = BoundaryResult(
                status="success",
                source="e01_ast_worker",
                encoding=encoding,
                boundaries=[FunctionBoundary(**item) for item in response.get("boundaries", [])],
            )
    except Exception as exc:
        result = BoundaryResult(
            status="error",
            source="e01_ast_worker",
            encoding="",
            boundaries=[],
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    save_boundary_cache(boundary_cache_root, blob_oid, result)
    return result




def resolve_boundaries_for_changes(
    *,
    clone_path: Path,
    commit_sha: str,
    changes: Sequence[dict[str, Any]],
    boundary_cache_root: Path,
    d01_index: dict[str, D01BoundaryRecord],
    ast_python_bin: str,
    ast_worker_client: ASTWorkerClient,
    git_timeout: int,
    ast_timeout: int,
    batch_size: int = 100,
) -> dict[str, BoundaryResult]:
    results: dict[str, BoundaryResult] = {}
    pending: dict[str, tuple[str, str, str]] = {}

    for item in changes:
        blob_oid = str(item.get("blob_oid", ""))
        path = str(item.get("new_path", ""))
        if not blob_oid:
            continue
        if blob_oid in results:
            continue
        cached = load_boundary_cache(boundary_cache_root, blob_oid)
        if cached is not None:
            results[blob_oid] = cached
            continue
        if blob_oid in d01_index and d01_index[blob_oid].safe_for_reuse:
            reused = BoundaryResult(
                status="success",
                source="run-x-d01-body-store",
                encoding="d01-recorded",
                boundaries=d01_index[blob_oid].boundaries,
            )
            save_boundary_cache(boundary_cache_root, blob_oid, reused)
            results[blob_oid] = reused
            continue
        try:
            payload = read_git_blob(clone_path, commit_sha, path, git_timeout)
            source, encoding = decode_python_source(payload)
            pending[blob_oid] = (path, source, encoding)
        except Exception as exc:
            failed = BoundaryResult(
                status="error",
                source="e01_ast_worker",
                encoding="",
                boundaries=[],
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            save_boundary_cache(boundary_cache_root, blob_oid, failed)
            results[blob_oid] = failed

    pending_items = list(pending.items())
    for start in range(0, len(pending_items), batch_size):
        batch = pending_items[start : start + batch_size]
        files = [(metadata[0], metadata[1]) for _, metadata in batch]
        try:
            responses = ast_worker_client.request(files)
        except Exception as exc:
            for blob_oid, (_, _, encoding) in batch:
                failed = BoundaryResult(
                    status="error",
                    source="e01_ast_worker",
                    encoding=encoding,
                    boundaries=[],
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                save_boundary_cache(boundary_cache_root, blob_oid, failed)
                results[blob_oid] = failed
            continue

        for request_index, (blob_oid, (_, _, encoding)) in enumerate(batch):
            response = responses.get(request_index, {})
            if response.get("status") == "success":
                resolved = BoundaryResult(
                    status="success",
                    source="e01_ast_worker",
                    encoding=encoding,
                    boundaries=[
                        FunctionBoundary(**item)
                        for item in response.get("boundaries", [])
                    ],
                )
            else:
                resolved = BoundaryResult(
                    status="error",
                    source="e01_ast_worker",
                    encoding=encoding,
                    boundaries=[],
                    error_type=str(response.get("error_type", "ASTError")),
                    error_message=str(response.get("error_message", "AST parse failed")),
                )
            save_boundary_cache(boundary_cache_root, blob_oid, resolved)
            results[blob_oid] = resolved
    return results

def process_repository(
    group: "pd.DataFrame",
    args: argparse.Namespace,
    cache_root: Path,
    boundary_cache_root: Path,
) -> dict[str, Any]:
    dataset_source = str(group["dataset_source"].iloc[0])
    repo_name = str(group["repo_name"].iloc[0])
    clone_path = Path(str(group["clone_path"].dropna().iloc[0])).expanduser().resolve()
    repo_key = stable_repo_key(dataset_source, repo_name)
    repo_cache_dir = cache_root / repo_key
    repo_cache_dir.mkdir(parents=True, exist_ok=True)
    summary_path = repo_cache_dir / "summary.json"

    panel_fingerprint_columns = [
        column
        for column in [
            "repo_id",
            "repo_name",
            "dataset_source",
            "time",
            "time_index",
            "commits",
            "lines_added",
            "latest_commit_effective",
            "clone_path",
        ]
        if column in group.columns
    ]
    fingerprint_payload = group[panel_fingerprint_columns].sort_values("time").to_csv(index=False)
    input_fingerprint = sha256_text(fingerprint_payload)

    if summary_path.exists() and not args.analysis_again:
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
            if (
                existing.get("status") == "completed"
                and existing.get("input_fingerprint") == input_fingerprint
                and existing.get("implementation_version") == IMPLEMENTATION_VERSION
            ):
                logging.info("Resume skip: %s", repo_name)
                return existing
        except Exception:
            pass

    if args.analysis_again and repo_cache_dir.exists():
        shutil.rmtree(repo_cache_dir)
        repo_cache_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()
    repo_month_rows: list[dict[str, Any]] = []
    commit_rows: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    function_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []

    clone_valid, clone_status = validate_clone(clone_path, args.git_timeout_seconds)
    if not clone_valid:
        for row in group.to_dict("records"):
            issue_rows.append(
                {
                    "repo_name": repo_name,
                    "dataset_source": dataset_source,
                    "time": row["time"],
                    "commit_sha": "",
                    "path": "",
                    "stage": "clone_validation",
                    "error_type": clone_status,
                    "error_message": clone_status,
                    "lines_added_affected": row.get("lines_added", ""),
                    "resolution_status": "unresolved",
                }
            )
        tip_commit = ""
        tip_method = clone_status
        commits: list[dict[str, Any]] = []
    else:
        tip_commit, tip_method = select_analysis_tip(group, clone_path, args.git_timeout_seconds)
        commits = list_commits_for_months(
            clone_path,
            tip_commit,
            set(group["time"].astype(str)),
            ZoneInfo(args.analysis_timezone),
            args.git_timeout_seconds,
        )

    required_blob_oids = (
        collect_required_blob_oids(clone_path, commits, args.git_timeout_seconds)
        if clone_valid and args.reuse_d01_boundaries
        else set()
    )
    d01_index = (
        query_d01_boundary_index(
            Path(args.d01_index_db).expanduser().resolve(),
            required_blob_oids,
        )
        if args.reuse_d01_boundaries
        else {}
    )

    ast_worker_client = ASTWorkerClient(
        args.ast_python_bin, args.ast_worker_timeout_seconds
    )

    for commit_index, commit in enumerate(commits, start=1):
        commit_started = time.monotonic()
        commit_metric = {
            "repo_name": repo_name,
            "dataset_source": dataset_source,
            "commit_sha": commit["commit_sha"],
            "first_parent_sha": commit["first_parent_sha"],
            "commit_time_epoch": commit["commit_time_epoch"],
            "commit_time_local": commit["commit_time_local"],
            "commit_month": commit["commit_month"],
            "is_merge_commit": int(commit["is_merge_commit"]),
            "is_root_commit": int(commit["is_root_commit"]),
            "lines_added_repo_recomputed": 0,
            "lines_removed_repo_recomputed": 0,
            "lines_added_py_total": 0,
            "lines_added_py_function_body": 0,
            "lines_added_py_function_signature_or_decorator": 0,
            "lines_added_py_function_leading_docstring": 0,
            "lines_added_py_outside_function": 0,
            "lines_added_py_unclassified": 0,
            "python_files_changed": 0,
            "functions_touched_by_added_lines": 0,
            "diff_status": "success",
            "parse_complete": 1,
            "runtime_seconds": 0.0,
        }
        touched_functions: set[tuple[str, str, int, int]] = set()

        if commit["is_root_commit"]:
            commit_metric["diff_status"] = "root_commit_skipped_like_original"
            commit_metric["runtime_seconds"] = time.monotonic() - commit_started
            commit_rows.append(commit_metric)
            continue

        try:
            added_repo, removed_repo = repo_numstat(
                clone_path,
                commit["first_parent_sha"],
                commit["commit_sha"],
                args.git_timeout_seconds,
            )
            commit_metric["lines_added_repo_recomputed"] = added_repo
            commit_metric["lines_removed_repo_recomputed"] = removed_repo
            changed_paths = list_changed_paths(
                clone_path,
                commit["first_parent_sha"],
                commit["commit_sha"],
                args.git_timeout_seconds,
            )
        except Exception as exc:
            commit_metric["diff_status"] = "diff_error"
            commit_metric["parse_complete"] = 0
            issue_rows.append(
                {
                    "repo_name": repo_name,
                    "dataset_source": dataset_source,
                    "time": commit["commit_month"],
                    "commit_sha": commit["commit_sha"],
                    "path": "",
                    "stage": "commit_diff",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "lines_added_affected": "",
                    "resolution_status": "unresolved",
                }
            )
            commit_metric["runtime_seconds"] = time.monotonic() - commit_started
            commit_rows.append(commit_metric)
            continue

        python_changes: list[dict[str, Any]] = []
        for changed in changed_paths:
            if not changed.new_path or not path_is_python(changed.new_path):
                continue
            commit_metric["python_files_changed"] += 1
            try:
                added_lines = patch_added_line_numbers(
                    clone_path,
                    commit["first_parent_sha"],
                    commit["commit_sha"],
                    changed.old_path,
                    changed.new_path,
                    args.git_timeout_seconds,
                )
            except Exception as exc:
                added_lines = []
                commit_metric["parse_complete"] = 0
                issue_rows.append(
                    {
                        "repo_name": repo_name,
                        "dataset_source": dataset_source,
                        "time": commit["commit_month"],
                        "commit_sha": commit["commit_sha"],
                        "path": changed.new_path,
                        "stage": "python_patch",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "lines_added_affected": "unknown",
                        "resolution_status": "unresolved",
                    }
                )

            blob_oid = ""
            try:
                blob_oid = post_blob_oid(
                    clone_path,
                    commit["commit_sha"],
                    changed.new_path,
                    args.git_timeout_seconds,
                )
            except Exception as exc:
                issue_rows.append(
                    {
                        "repo_name": repo_name,
                        "dataset_source": dataset_source,
                        "time": commit["commit_month"],
                        "commit_sha": commit["commit_sha"],
                        "path": changed.new_path,
                        "stage": "post_blob_oid",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "lines_added_affected": len(added_lines),
                        "resolution_status": "unresolved",
                    }
                )
            python_changes.append(
                {
                    "changed": changed,
                    "old_path": changed.old_path,
                    "new_path": changed.new_path,
                    "added_lines": added_lines,
                    "blob_oid": blob_oid,
                }
            )

        boundary_results = resolve_boundaries_for_changes(
            clone_path=clone_path,
            commit_sha=commit["commit_sha"],
            changes=python_changes,
            boundary_cache_root=boundary_cache_root,
            d01_index=d01_index,
            ast_python_bin=args.ast_python_bin,
            ast_worker_client=ast_worker_client,
            git_timeout=args.git_timeout_seconds,
            ast_timeout=args.ast_worker_timeout_seconds,
        )

        for change_info in python_changes:
            changed = change_info["changed"]
            added_lines = change_info["added_lines"]
            blob_oid = change_info["blob_oid"]
            boundary_result = boundary_results.get(
                blob_oid,
                BoundaryResult(
                    status="error",
                    source="none",
                    encoding="",
                    boundaries=[],
                    error_type="MissingBlobOID",
                    error_message="Could not identify post-change blob OID",
                ),
            )

            file_counts = Counter()
            function_line_numbers: dict[
                tuple[str, str, int, int, int, int, int], list[int]
            ] = defaultdict(list)
            for line_number in added_lines:
                if boundary_result.status != "success":
                    category = "unclassified"
                    boundary = None
                else:
                    category, boundary = classify_added_line(
                        line_number, boundary_result.boundaries
                    )
                file_counts[category] += 1
                if category == "function_body" and boundary is not None:
                    key = (
                        boundary.qualified_name,
                        boundary.function_kind,
                        boundary.nesting_depth,
                        boundary.decorated_start_line,
                        boundary.function_start_line,
                        boundary.body_start_line,
                        boundary.body_end_line,
                    )
                    function_line_numbers[key].append(line_number)
                    touched_functions.add(
                        (
                            changed.new_path,
                            boundary.qualified_name,
                            boundary.function_start_line,
                            boundary.body_end_line,
                        )
                    )

            commit_metric["lines_added_py_total"] += len(added_lines)
            commit_metric["lines_added_py_function_body"] += file_counts["function_body"]
            commit_metric[
                "lines_added_py_function_signature_or_decorator"
            ] += file_counts["function_signature_or_decorator"]
            commit_metric[
                "lines_added_py_function_leading_docstring"
            ] += file_counts["function_leading_docstring"]
            commit_metric["lines_added_py_outside_function"] += file_counts[
                "outside_function"
            ]
            commit_metric["lines_added_py_unclassified"] += file_counts[
                "unclassified"
            ]
            if file_counts["unclassified"]:
                commit_metric["parse_complete"] = 0
                issue_rows.append(
                    {
                        "repo_name": repo_name,
                        "dataset_source": dataset_source,
                        "time": commit["commit_month"],
                        "commit_sha": commit["commit_sha"],
                        "path": changed.new_path,
                        "stage": "function_boundary_parse",
                        "error_type": boundary_result.error_type,
                        "error_message": boundary_result.error_message,
                        "lines_added_affected": file_counts["unclassified"],
                        "resolution_status": "unclassified",
                    }
                )

            file_rows.append(
                {
                    "repo_name": repo_name,
                    "dataset_source": dataset_source,
                    "commit_sha": commit["commit_sha"],
                    "commit_month": commit["commit_month"],
                    "change_status": changed.status,
                    "old_path": changed.old_path,
                    "new_path": changed.new_path,
                    "post_blob_oid": blob_oid,
                    "source_encoding": boundary_result.encoding,
                    "boundary_source": boundary_result.source,
                    "parse_status": boundary_result.status,
                    "parse_error_type": boundary_result.error_type,
                    "parse_error_message": boundary_result.error_message,
                    "lines_added_py_total": len(added_lines),
                    "lines_added_py_function_body": file_counts["function_body"],
                    "lines_added_py_function_signature_or_decorator": file_counts[
                        "function_signature_or_decorator"
                    ],
                    "lines_added_py_function_leading_docstring": file_counts[
                        "function_leading_docstring"
                    ],
                    "lines_added_py_outside_function": file_counts[
                        "outside_function"
                    ],
                    "lines_added_py_unclassified": file_counts["unclassified"],
                    "functions_touched_by_added_lines": len(function_line_numbers),
                }
            )

            for key, line_numbers in function_line_numbers.items():
                (
                    qualified_name,
                    kind,
                    depth,
                    decorated_start,
                    function_start,
                    body_start,
                    body_end,
                ) = key
                function_rows.append(
                    {
                        "repo_name": repo_name,
                        "dataset_source": dataset_source,
                        "commit_sha": commit["commit_sha"],
                        "commit_month": commit["commit_month"],
                        "path": changed.new_path,
                        "post_blob_oid": blob_oid,
                        "qualified_name": qualified_name,
                        "function_kind": kind,
                        "nesting_depth": depth,
                        "decorated_start_line": decorated_start,
                        "function_start_line": function_start,
                        "body_start_line": body_start,
                        "body_end_line": body_end,
                        "added_body_line_count": len(line_numbers),
                        "added_body_line_numbers": ";".join(
                            str(item) for item in sorted(line_numbers)
                        ),
                        "boundary_source": boundary_result.source,
                    }
                )

        commit_metric["functions_touched_by_added_lines"] = len(touched_functions)
        commit_metric["runtime_seconds"] = time.monotonic() - commit_started
        commit_rows.append(commit_metric)
        if args.progress_every_commits and commit_index % args.progress_every_commits == 0:
            logging.info("%s: processed %d/%d commits", repo_name, commit_index, len(commits))

    ast_worker_client.close()

    commit_frame = pd.DataFrame(commit_rows, columns=COMMIT_COLUMNS)
    if commit_frame.empty:
        commit_frame = pd.DataFrame(columns=COMMIT_COLUMNS)

    for panel_row in group.sort_values("time_index").to_dict("records"):
        month = str(panel_row["time"])
        month_commits = commit_frame[commit_frame["commit_month"] == month].copy()
        commits_recomputed = int(len(month_commits))
        lines_added_repo_recomputed = int(
            pd.to_numeric(month_commits["lines_added_repo_recomputed"], errors="coerce").fillna(0).sum()
        )
        lines_removed_repo_recomputed = int(
            pd.to_numeric(month_commits["lines_removed_repo_recomputed"], errors="coerce").fillna(0).sum()
        )
        original_commits = int(round(float(panel_row.get("commits", 0) or 0)))
        original_lines_added = int(round(float(panel_row.get("lines_added", 0) or 0)))
        commits_match = commits_recomputed == original_commits
        lines_match = lines_added_repo_recomputed == original_lines_added
        parse_complete = bool(
            month_commits.empty
            or (
                pd.to_numeric(month_commits["parse_complete"], errors="coerce").fillna(0).eq(1).all()
                and pd.to_numeric(month_commits["lines_added_py_unclassified"], errors="coerce").fillna(0).sum() == 0
            )
        )
        history_complete = commits_match and lines_match
        model_e_complete = parse_complete and history_complete and clone_valid

        lines_body = int(pd.to_numeric(month_commits["lines_added_py_function_body"], errors="coerce").fillna(0).sum())
        lines_py_total = int(pd.to_numeric(month_commits["lines_added_py_total"], errors="coerce").fillna(0).sum())
        lines_signature = int(
            pd.to_numeric(month_commits["lines_added_py_function_signature_or_decorator"], errors="coerce").fillna(0).sum()
        )
        lines_docstring = int(
            pd.to_numeric(month_commits["lines_added_py_function_leading_docstring"], errors="coerce").fillna(0).sum()
        )
        lines_outside = int(pd.to_numeric(month_commits["lines_added_py_outside_function"], errors="coerce").fillna(0).sum())
        lines_unclassified = int(pd.to_numeric(month_commits["lines_added_py_unclassified"], errors="coerce").fillna(0).sum())
        python_commits = int((pd.to_numeric(month_commits["python_files_changed"], errors="coerce").fillna(0) > 0).sum())
        python_files_changed = int(pd.to_numeric(month_commits["python_files_changed"], errors="coerce").fillna(0).sum())
        functions_touched = int(pd.to_numeric(month_commits["functions_touched_by_added_lines"], errors="coerce").fillna(0).sum())
        commits_with_body = int((pd.to_numeric(month_commits["lines_added_py_function_body"], errors="coerce").fillna(0) > 0).sum())

        month_issue_count = sum(
            1 for issue in issue_rows if str(issue.get("time", "")) == month
        )
        if not clone_valid:
            status = "unresolved_clone"
        elif commits_recomputed == 0 and original_commits == 0:
            status = "success_zero_no_commits"
        elif not history_complete and not parse_complete:
            status = "partial_history_and_parse"
        elif not history_complete:
            status = "partial_history_reconciliation"
        elif not parse_complete:
            status = "partial_parse_failure"
        elif lines_body > 0:
            status = "success_with_function_body_additions"
        elif lines_py_total == 0:
            status = "success_zero_no_python_additions"
        else:
            status = "success_zero_outside_function_only"

        repo_month_rows.append(
            {
                "repo_id": panel_row.get("repo_id", ""),
                "repo_name": repo_name,
                "dataset_source": dataset_source,
                "time": month,
                "time_index": panel_row.get("time_index", ""),
                "commits_original": original_commits,
                "commits_recomputed": commits_recomputed,
                "commits_match_original": int(commits_match),
                "lines_added_original": original_lines_added,
                "lines_added_repo_recomputed": lines_added_repo_recomputed,
                "lines_added_repo_match_original": int(lines_match),
                "lines_added_py_total": lines_py_total,
                "lines_added_py_function_body": lines_body,
                "lines_added_py_function_signature_or_decorator": lines_signature,
                "lines_added_py_function_leading_docstring": lines_docstring,
                "lines_added_py_outside_function": lines_outside,
                "lines_added_py_unclassified": lines_unclassified,
                "lines_removed_repo_recomputed": lines_removed_repo_recomputed,
                "python_commits_in_month": python_commits,
                "python_files_changed": python_files_changed,
                "functions_touched_by_added_lines": functions_touched,
                "commits_with_py_function_body_additions": commits_with_body,
                "latest_commit_effective": panel_row.get("latest_commit_effective", ""),
                "commit_resolution": panel_row.get("commit_resolution", ""),
                "months_since_observed_commit": panel_row.get("months_since_observed_commit", ""),
                "analysis_tip_commit": tip_commit,
                "analysis_timezone": args.analysis_timezone,
                "function_metric_parse_complete": int(parse_complete),
                "history_reconciliation_complete": int(history_complete),
                "model_e_complete": int(model_e_complete),
                "function_line_metric_status": status,
                "issue_count": month_issue_count,
            }
        )

    write_csv_rows(repo_cache_dir / "repo_month_metrics.csv", repo_month_rows, REPO_MONTH_COLUMNS)
    write_csv_rows(repo_cache_dir / "commit_metrics.csv", commit_rows, COMMIT_COLUMNS)
    write_csv_rows(repo_cache_dir / "file_metrics.csv", file_rows, FILE_COLUMNS)
    write_csv_rows(repo_cache_dir / "function_metrics.csv", function_rows, FUNCTION_COLUMNS)
    write_csv_rows(repo_cache_dir / "issues.csv", issue_rows, ISSUE_COLUMNS)

    summary = {
        "status": "completed",
        "implementation_version": IMPLEMENTATION_VERSION,
        "input_fingerprint": input_fingerprint,
        "repo_name": repo_name,
        "dataset_source": dataset_source,
        "repo_key": repo_key,
        "clone_path": str(clone_path),
        "clone_status": clone_status,
        "analysis_tip_commit": tip_commit,
        "analysis_tip_method": tip_method,
        "repo_month_rows": len(repo_month_rows),
        "commit_rows": len(commit_rows),
        "file_rows": len(file_rows),
        "function_rows": len(function_rows),
        "issue_rows": len(issue_rows),
        "d01_reused_blob_count": len(d01_index),
        "runtime_seconds": time.monotonic() - start_time,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logging.info(
        "Completed %s: months=%d commits=%d files=%d functions=%d issues=%d runtime=%.1fs",
        repo_name,
        len(repo_month_rows),
        len(commit_rows),
        len(file_rows),
        len(function_rows),
        len(issue_rows),
        summary["runtime_seconds"],
    )
    return summary


def load_panel(path: Path) -> "pd.DataFrame":
    panel = pd.read_csv(path, low_memory=False)
    missing = REQUIRED_PANEL_COLUMNS - set(panel.columns)
    if missing:
        raise ValueError(f"Panel is missing required columns: {sorted(missing)}")
    panel = panel.copy()
    panel["dataset_source"] = panel["dataset_source"].astype(str).str.strip().str.lower()
    unexpected = set(panel["dataset_source"].unique()) - EXPECTED_DATASET_SOURCES
    if unexpected:
        raise ValueError(f"Unexpected dataset_source values: {sorted(unexpected)}")
    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["time"] = panel["time"].astype(str).str.strip()
    if not panel["time"].str.match(r"^\d{4}-\d{2}$").all():
        raise ValueError("Panel time must use YYYY-MM format")
    if panel.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("Panel contains duplicate repo_id + time_index rows")
    if panel.duplicated(["dataset_source", "repo_name", "time"]).any():
        raise ValueError("Panel contains duplicate dataset_source + repo_name + time rows")
    return panel


def expected_count_checks(panel: "pd.DataFrame", args: argparse.Namespace) -> list[dict[str, Any]]:
    role_rows = panel.groupby("dataset_source").size().to_dict()
    role_repos = panel.groupby("dataset_source")["repo_name"].nunique().to_dict()
    checks = [
        ("input_panel_rows", len(panel), args.expected_panel_rows),
        ("repositories", panel["repo_name"].str.casefold().nunique(), args.expected_repositories),
        ("treatment_rows", int(role_rows.get("treatment", 0)), args.expected_treatment_rows),
        ("control_rows", int(role_rows.get("control", 0)), args.expected_control_rows),
        ("treatment_repositories", int(role_repos.get("treatment", 0)), args.expected_treatment_repositories),
        ("control_repositories", int(role_repos.get("control", 0)), args.expected_control_repositories),
    ]
    output: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, observed, expected in checks:
        passed = int(observed) == int(expected)
        output.append(
            {
                "check_name": name,
                "status": "pass" if passed else "fail",
                "observed": observed,
                "expected": expected,
                "note": "",
            }
        )
        if not passed:
            failures.append(f"{name}: observed={observed}, expected={expected}")
    if args.strict_expected_counts and failures:
        raise ValueError("Strict expected counts failed: " + " | ".join(failures))
    return output


def concatenate_cache_files(cache_root: Path, filename: str, columns: Sequence[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(cache_root.glob(f"*/{filename}")):
        rows.extend(read_csv_rows(path))
    return [{column: row.get(column, "") for column in columns} for row in rows]


def build_qc(
    panel: "pd.DataFrame",
    repo_month: "pd.DataFrame",
    commits: "pd.DataFrame",
    files: "pd.DataFrame",
    functions: "pd.DataFrame",
    issues: "pd.DataFrame",
    initial_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks = list(initial_checks)

    def add(name: str, passed: bool, observed: Any, expected: Any, note: str = "") -> None:
        checks.append(
            {
                "check_name": name,
                "status": "pass" if passed else "fail",
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    add("repo_month_output_rows", len(repo_month) == len(panel), len(repo_month), len(panel))
    duplicate_months = int(repo_month.duplicated(["dataset_source", "repo_name", "time"]).sum()) if not repo_month.empty else 0
    add("duplicate_repo_month_rows", duplicate_months == 0, duplicate_months, 0)
    negative_body = int((pd.to_numeric(repo_month.get("lines_added_py_function_body", pd.Series(dtype=float)), errors="coerce") < 0).sum())
    add("negative_function_body_lines", negative_body == 0, negative_body, 0)
    py_identity_errors = 0
    if not repo_month.empty:
        total = pd.to_numeric(repo_month["lines_added_py_total"], errors="coerce").fillna(0)
        parts = sum(
            pd.to_numeric(repo_month[column], errors="coerce").fillna(0)
            for column in [
                "lines_added_py_function_body",
                "lines_added_py_function_signature_or_decorator",
                "lines_added_py_function_leading_docstring",
                "lines_added_py_outside_function",
                "lines_added_py_unclassified",
            ]
        )
        py_identity_errors = int((total != parts).sum())
    add("python_added_line_partition_identity", py_identity_errors == 0, py_identity_errors, 0)
    body_gt_py = 0
    if not repo_month.empty:
        body_gt_py = int(
            (
                pd.to_numeric(repo_month["lines_added_py_function_body"], errors="coerce").fillna(0)
                > pd.to_numeric(repo_month["lines_added_py_total"], errors="coerce").fillna(0)
            ).sum()
        )
    add("function_body_not_above_python_total", body_gt_py == 0, body_gt_py, 0)
    zero_commit_nonzero = 0
    if not repo_month.empty:
        zero_commit_nonzero = int(
            (
                (pd.to_numeric(repo_month["commits_recomputed"], errors="coerce").fillna(0) == 0)
                & (pd.to_numeric(repo_month["lines_added_py_function_body"], errors="coerce").fillna(0) != 0)
            ).sum()
        )
    add("zero_commit_month_has_zero_function_lines", zero_commit_nonzero == 0, zero_commit_nonzero, 0)
    root_nonzero = 0
    if not commits.empty:
        root_mask = pd.to_numeric(commits["is_root_commit"], errors="coerce").fillna(0).eq(1)
        root_nonzero = int(
            (
                pd.to_numeric(commits.loc[root_mask, "lines_added_repo_recomputed"], errors="coerce").fillna(0)
                != 0
            ).sum()
        )
    add("root_commit_additions_excluded", root_nonzero == 0, root_nonzero, 0)
    invalid_function_counts = 0
    if not functions.empty:
        invalid_function_counts = int(
            (pd.to_numeric(functions["added_body_line_count"], errors="coerce").fillna(0) <= 0).sum()
        )
    add("function_rows_have_positive_added_lines", invalid_function_counts == 0, invalid_function_counts, 0)
    unknown_issue_lines = int(
        pd.to_numeric(issues.get("lines_added_affected", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    ) if not issues.empty else 0
    add("issues_recorded", True, len(issues), "informational", f"affected_numeric_lines={unknown_issue_lines}")
    complete_rows = int(pd.to_numeric(repo_month.get("model_e_complete", pd.Series(dtype=float)), errors="coerce").fillna(0).eq(1).sum())
    add("complete_repo_month_rows", True, complete_rows, "informational")
    commits_match = int(pd.to_numeric(repo_month.get("commits_match_original", pd.Series(dtype=float)), errors="coerce").fillna(0).eq(1).sum())
    lines_match = int(pd.to_numeric(repo_month.get("lines_added_repo_match_original", pd.Series(dtype=float)), errors="coerce").fillna(0).eq(1).sum())
    add("commit_reconciliation_matches", True, commits_match, "informational")
    add("lines_added_reconciliation_matches", True, lines_match, "informational")
    return checks


def build_summary(
    panel: "pd.DataFrame",
    repo_month: "pd.DataFrame",
    commits: "pd.DataFrame",
    files: "pd.DataFrame",
    functions: "pd.DataFrame",
    issues: "pd.DataFrame",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(section: str, metric: str, value: Any, note: str = "") -> None:
        rows.append({"section": section, "metric": metric, "value": value, "note": note})

    add("input", "panel_rows", len(panel))
    add("input", "repositories", panel["repo_name"].str.casefold().nunique())
    add("output", "repo_month_rows", len(repo_month))
    add("output", "commit_rows", len(commits))
    add("output", "python_file_change_rows", len(files))
    add("output", "function_attribution_rows", len(functions))
    add("output", "issue_rows", len(issues))
    if not repo_month.empty:
        for column in [
            "lines_added_repo_recomputed",
            "lines_added_py_total",
            "lines_added_py_function_body",
            "lines_added_py_unclassified",
        ]:
            values = pd.to_numeric(repo_month[column], errors="coerce").fillna(0)
            add("metric", f"{column}_sum", int(values.sum()))
            add("metric", f"{column}_median", float(values.median()))
            add("metric", f"{column}_mean", float(values.mean()))
            add("metric", f"{column}_max", int(values.max()))
            add("metric", f"{column}_zero_rows", int((values == 0).sum()))
        add(
            "quality",
            "model_e_complete_rows",
            int(pd.to_numeric(repo_month["model_e_complete"], errors="coerce").fillna(0).eq(1).sum()),
        )
        add(
            "quality",
            "parse_complete_rows",
            int(
                pd.to_numeric(repo_month["function_metric_parse_complete"], errors="coerce")
                .fillna(0)
                .eq(1)
                .sum()
            ),
        )
        add(
            "quality",
            "history_reconciliation_complete_rows",
            int(
                pd.to_numeric(repo_month["history_reconciliation_complete"], errors="coerce")
                .fillna(0)
                .eq(1)
                .sum()
            ),
        )
    return rows


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-file", required=True)
    parser.add_argument("--repo-month-output", required=True)
    parser.add_argument("--commit-output", required=True)
    parser.add_argument("--file-output", required=True)
    parser.add_argument("--function-output", required=True)
    parser.add_argument("--issues-output", required=True)
    parser.add_argument("--reconciliation-output", required=True)
    parser.add_argument("--qc-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--boundary-cache-root", required=True)
    parser.add_argument("--d01-function-details-file", action="append", default=[])
    parser.add_argument("--d01-body-store-root", required=True)
    parser.add_argument("--d01-index-db", required=True)
    parser.add_argument("--reuse-d01-boundaries", type=int, choices=[0, 1], default=1)
    parser.add_argument("--ast-python-bin", required=True)
    parser.add_argument("--analysis-timezone", default="America/Chicago")
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--ast-worker-timeout-seconds", type=int, default=300)
    parser.add_argument("--start-repo-order", type=int, default=1)
    parser.add_argument("--limit-repos", type=int, default=0)
    parser.add_argument("--dataset-source", choices=["", "treatment", "control"], default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--analysis-again", type=int, choices=[0, 1], default=0)
    parser.add_argument("--dry-run", type=int, choices=[0, 1], default=0)
    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-rows", type=int, default=914)
    parser.add_argument("--expected-control-rows", type=int, default=1040)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--progress-every-repos", type=int, default=5)
    parser.add_argument("--progress-every-commits", type=int, default=250)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def run_self_test() -> int:
    source = '''\ndef outer():\n    # comment\n    x = 1\n    def inner():\n        """doc"""\n\n        return 2\n    return x\n\ndef one(): return 1\n'''
    boundaries = index_all_functions(source, "self_test.py")
    assert len(boundaries) == 3
    categories = {line: classify_added_line(line, boundaries)[0] for line in range(1, 13)}
    assert categories[3] == "function_body"
    assert categories[5] == "function_signature_or_decorator"
    assert categories[6] == "function_leading_docstring"
    assert categories[8] == "function_body"
    assert categories[11] == "function_body"
    print("Self-test passed")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    panel_path = Path(args.panel_file).expanduser().resolve()
    panel = load_panel(panel_path)
    initial_checks = expected_count_checks(panel, args)

    if args.dataset_source:
        panel = panel[panel["dataset_source"] == args.dataset_source].copy()
    if args.repo_name:
        panel = panel[panel["repo_name"].str.casefold() == args.repo_name.casefold()].copy()
    if panel.empty:
        raise ValueError("No panel rows remain after filters")

    repo_manifest = (
        panel.groupby(["dataset_source", "repo_name"], as_index=False)
        .agg(repo_month_rows=("time", "size"), first_month=("time", "min"), last_month=("time", "max"))
        .sort_values(["dataset_source", "repo_name"], key=lambda col: col.astype(str).str.casefold())
        .reset_index(drop=True)
    )
    repo_manifest["repo_order"] = np.arange(1, len(repo_manifest) + 1)
    selected_manifest = repo_manifest[repo_manifest["repo_order"] >= args.start_repo_order].copy()
    if args.limit_repos > 0:
        selected_manifest = selected_manifest.head(args.limit_repos).copy()
    selected_keys = set(zip(selected_manifest["dataset_source"], selected_manifest["repo_name"]))
    selected_panel = panel[
        panel.apply(lambda row: (row["dataset_source"], row["repo_name"]) in selected_keys, axis=1)
    ].copy()

    logging.info(
        "Input panel rows=%d repositories=%d; selected rows=%d repositories=%d",
        len(panel),
        len(repo_manifest),
        len(selected_panel),
        len(selected_manifest),
    )
    if args.dry_run:
        print(selected_manifest.to_csv(index=False))
        return 0

    cache_root = Path(args.cache_dir).expanduser().resolve()
    boundary_cache_root = Path(args.boundary_cache_root).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    boundary_cache_root.mkdir(parents=True, exist_ok=True)

    if args.reuse_d01_boundaries:
        ensure_d01_sqlite_index(
            [Path(path).expanduser().resolve() for path in args.d01_function_details_file],
            Path(args.d01_index_db).expanduser().resolve(),
            Path(args.d01_body_store_root).expanduser().resolve(),
        )

    for index, manifest_row in selected_manifest.iterrows():
        source = manifest_row["dataset_source"]
        repo = manifest_row["repo_name"]
        group = selected_panel[
            (selected_panel["dataset_source"] == source)
            & (selected_panel["repo_name"] == repo)
        ].copy()
        process_repository(group, args, cache_root, boundary_cache_root)
        processed = index + 1
        if args.progress_every_repos and processed % args.progress_every_repos == 0:
            logging.info("Processed %d/%d repositories", processed, len(selected_manifest))

    repo_month_rows = concatenate_cache_files(cache_root, "repo_month_metrics.csv", REPO_MONTH_COLUMNS)
    commit_rows = concatenate_cache_files(cache_root, "commit_metrics.csv", COMMIT_COLUMNS)
    file_rows = concatenate_cache_files(cache_root, "file_metrics.csv", FILE_COLUMNS)
    function_rows = concatenate_cache_files(cache_root, "function_metrics.csv", FUNCTION_COLUMNS)
    issue_rows = concatenate_cache_files(cache_root, "issues.csv", ISSUE_COLUMNS)

    repo_month = pd.DataFrame(repo_month_rows, columns=REPO_MONTH_COLUMNS)
    commits = pd.DataFrame(commit_rows, columns=COMMIT_COLUMNS)
    files = pd.DataFrame(file_rows, columns=FILE_COLUMNS)
    functions = pd.DataFrame(function_rows, columns=FUNCTION_COLUMNS)
    issues = pd.DataFrame(issue_rows, columns=ISSUE_COLUMNS)

    if not repo_month.empty:
        repo_month = repo_month[
            repo_month.apply(
                lambda row: (str(row["dataset_source"]), str(row["repo_name"])) in selected_keys,
                axis=1,
            )
        ].copy()
    if not commits.empty:
        commits = commits[
            commits.apply(
                lambda row: (str(row["dataset_source"]), str(row["repo_name"])) in selected_keys,
                axis=1,
            )
        ].copy()
    if not files.empty:
        files = files[
            files.apply(
                lambda row: (str(row["dataset_source"]), str(row["repo_name"])) in selected_keys,
                axis=1,
            )
        ].copy()
    if not functions.empty:
        functions = functions[
            functions.apply(
                lambda row: (str(row["dataset_source"]), str(row["repo_name"])) in selected_keys,
                axis=1,
            )
        ].copy()
    if not issues.empty:
        issues = issues[
            issues.apply(
                lambda row: (str(row["dataset_source"]), str(row["repo_name"])) in selected_keys,
                axis=1,
            )
        ].copy()

    reconciliation = repo_month[
        [
            "repo_id",
            "repo_name",
            "dataset_source",
            "time",
            "commits_original",
            "commits_recomputed",
            "lines_added_original",
            "lines_added_repo_recomputed",
            "commits_match_original",
            "lines_added_repo_match_original",
            "function_metric_parse_complete",
            "history_reconciliation_complete",
            "model_e_complete",
        ]
    ].copy()
    for column in [
        "commits_original",
        "commits_recomputed",
        "lines_added_original",
        "lines_added_repo_recomputed",
    ]:
        reconciliation[column] = pd.to_numeric(reconciliation[column], errors="coerce").fillna(0)
    reconciliation["commits_delta"] = reconciliation["commits_recomputed"] - reconciliation["commits_original"]
    reconciliation["lines_added_delta"] = (
        reconciliation["lines_added_repo_recomputed"] - reconciliation["lines_added_original"]
    )
    reconciliation = reconciliation[RECONCILIATION_COLUMNS]

    qc = build_qc(selected_panel, repo_month, commits, files, functions, issues, initial_checks)
    summary = build_summary(selected_panel, repo_month, commits, files, functions, issues)

    outputs = {
        args.repo_month_output: repo_month,
        args.commit_output: commits,
        args.file_output: files,
        args.function_output: functions,
        args.issues_output: issues,
        args.reconciliation_output: reconciliation,
        args.qc_output: pd.DataFrame(qc),
        args.summary_output: pd.DataFrame(summary),
    }
    for output_path_text, frame in outputs.items():
        output_path = Path(output_path_text).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_path, index=False)
        logging.info("Wrote %d rows to %s", len(frame), output_path)

    failures = [row for row in qc if row["status"] == "fail"]
    if failures:
        raise ValueError("QC failures: " + " | ".join(row["check_name"] for row in failures))
    return 0


if __name__ == "__main__":
    if AST_WORKER_STREAM_MODE:
        raise SystemExit(run_ast_worker_stream())
    if "--ast-worker" in sys.argv:
        raise SystemExit(run_ast_worker())
    if "--self-test" in sys.argv:
        raise SystemExit(run_self_test())
    raise SystemExit(main())
