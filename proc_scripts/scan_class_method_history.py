#!/usr/bin/env python3
"""Scan Python function structures across matched repository-month snapshots.

This is the first, outcome-blind stage of the run-py-9a experiment. It reads
the treatment and control repository-month histories created for run-py-2a,
resolves each exact ``latest_commit`` in the local Git clones, and inventories
the Python functions present in every distinct repository snapshot.

Scientific boundaries
---------------------
- This script does not read any run-py-7 or run-py-8 output.
- This script does not classify functions as AGC-like or HWC-like.
- This script does not estimate treatment effects or inspect confidence
  intervals.
- Class-method groups are not imposed in advance. Observable AST structure and
  decorator facts are recorded so that a taxonomy can be frozen later.
- Repeated repository-months pointing to the same commit share one Git-tree
  scan, while the complete repository-month manifest remains in the output.

The detailed inventories are normalized:
1. The history manifest maps repository-month rows to exact commits.
2. The file inventory maps repository commits and paths to Git blobs.
3. The function and decorator inventories record structures for each unique
   repository-commit-path occurrence.

Git blobs are parsed once per parser version through a reusable SQLite cache.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence


SCRIPT_VERSION = "run-py-9a-v1"
PARSER_VERSION = (
    "python-ast-raw-structure-v1-"
    f"py{sys.version_info.major}.{sys.version_info.minor}"
)
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ALLOWED_SOURCES = {"treatment", "control"}

EXCLUDED_PARTS = {
    ".git",
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

SNAPSHOT_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit",
    "repo_dir",
    "commit_available",
    "tree_scan_status",
    "tracked_python_paths",
    "eligible_python_files",
    "excluded_python_paths",
    "symlink_python_paths",
    "unique_eligible_python_blobs",
    "parsed_python_files",
    "parse_failure_files",
    "functions",
    "module_level_functions",
    "direct_class_scope_functions",
    "function_nested_functions",
    "class_contained_functions",
    "decorated_functions",
    "decorator_occurrences",
]

FILE_COLUMNS = [
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "git_mode",
    "git_object_type",
    "git_blob_sha",
    "scan_eligible",
    "selection_reason",
    "content_sha256",
    "source_encoding",
    "source_bytes",
    "physical_lines",
    "parse_status",
    "parse_error_type",
    "parse_error_message",
    "function_count",
]

FUNCTION_ID_COLUMNS = [
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "git_blob_sha",
    "function_ordinal",
]

FUNCTION_COLUMNS = [
    *FUNCTION_ID_COLUMNS,
    "qualified_function_name",
    "function_name",
    "function_node_type",
    "is_async",
    "start_line",
    "definition_line",
    "end_line",
    "direct_parent_node_type",
    "definition_parent_kind",
    "definition_parent_name",
    "ancestor_node_types_json",
    "definition_scope_names_json",
    "definition_scope_kinds_json",
    "class_ancestor_names_json",
    "function_ancestor_names_json",
    "class_depth",
    "function_depth",
    "control_flow_depth",
    "is_module_level",
    "is_direct_class_scope",
    "is_nested_in_function",
    "is_class_contained",
    "decorator_count",
    "decorators_raw_json",
    "decorators_callable_json",
    "first_parameter_name",
    "positional_parameter_count",
    "keyword_only_parameter_count",
    "has_vararg",
    "has_kwarg",
    "is_dunder_name",
    "function_source_sha256",
    "function_body_source_sha256",
    "function_ast_sha256",
    "function_body_ast_sha256",
]

DECORATOR_COLUMNS = [
    *FUNCTION_ID_COLUMNS,
    "qualified_function_name",
    "decorator_index",
    "decorator_raw",
    "decorator_callable",
    "decorator_root",
    "decorator_expression_type",
    "decorator_is_call",
]

PARSE_FAILURE_COLUMNS = [
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "git_blob_sha",
    "stage",
    "error_type",
    "error_message",
]


class ValidationError(RuntimeError):
    """Raised when an input or scan invariant is violated."""


@dataclass(frozen=True)
class InputRow:
    dataset_source: str
    repo_name: str
    month: str
    latest_commit: str
    clone_dir: Path


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    object_type: str
    object_id: str
    relative_path: str


@dataclass
class OutputTable:
    final_path: Path
    columns: list[str]
    temporary_path: Path | None = None
    handle: io.TextIOWrapper | None = None
    writer: csv.DictWriter | None = None
    rows_written: int = 0

    def open(self) -> None:
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{self.final_path.name}.",
            suffix=".tmp",
            dir=self.final_path.parent,
        )
        self.temporary_path = Path(name)
        self.handle = os.fdopen(
            fd,
            mode="w",
            encoding="utf-8",
            errors="backslashreplace",
            newline="",
        )
        self.writer = csv.DictWriter(
            self.handle,
            fieldnames=self.columns,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        self.writer.writeheader()

    def write(self, row: dict[str, Any]) -> None:
        if self.writer is None:
            raise RuntimeError(f"Output table is not open: {self.final_path}")
        self.writer.writerow(row)
        self.rows_written += 1

    def finish(self) -> None:
        if self.handle is None or self.temporary_path is None:
            raise RuntimeError(f"Output table is not open: {self.final_path}")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        self.handle = None
        os.replace(self.temporary_path, self.final_path)
        self.temporary_path = None

    def abort(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        if self.temporary_path is not None and self.temporary_path.exists():
            self.temporary_path.unlink()
        self.temporary_path = None


class CatFileBatch:
    """Read multiple Git blobs without starting one process per blob."""

    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = repo_dir
        self.process = subprocess.Popen(
            ["git", "-C", str(repo_dir), "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def read_blob(self, object_id: str) -> bytes:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("git cat-file pipes are unavailable")
        self.process.stdin.write(object_id.encode("ascii") + b"\n")
        self.process.stdin.flush()
        header = self.process.stdout.readline().rstrip(b"\n")
        fields = header.split()
        if len(fields) == 2 and fields[1] == b"missing":
            raise FileNotFoundError(f"Git object is missing: {object_id}")
        if len(fields) != 3 or fields[1] != b"blob":
            raise RuntimeError(
                f"Unexpected git cat-file header for {object_id}: {header!r}"
            )
        size = int(fields[2])
        payload = self.process.stdout.read(size)
        terminator = self.process.stdout.read(1)
        if len(payload) != size or terminator != b"\n":
            raise RuntimeError(f"Incomplete Git blob payload: {object_id}")
        return payload

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        return_code = self.process.wait()
        if return_code != 0:
            stderr = (
                self.process.stderr.read().decode("utf-8", errors="replace")
                if self.process.stderr is not None
                else ""
            )
            raise RuntimeError(
                f"git cat-file failed in {self.repo_dir}: {stderr.strip()}"
            )

    def __enter__(self) -> "CatFileBatch":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise


class BlobCache:
    """Persistent parser-versioned cache for Git blob parse results."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS blob_parse_cache (
                parser_version TEXT NOT NULL,
                blob_sha TEXT NOT NULL,
                parse_result_json TEXT NOT NULL,
                PRIMARY KEY (parser_version, blob_sha)
            )
            """
        )
        self.connection.commit()
        self.hits = 0
        self.misses = 0

    def get(self, blob_sha: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT parse_result_json
            FROM blob_parse_cache
            WHERE parser_version = ? AND blob_sha = ?
            """,
            (PARSER_VERSION, blob_sha),
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(row[0])

    def put(self, blob_sha: str, result: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO blob_parse_cache
                (parser_version, blob_sha, parse_result_json)
            VALUES (?, ?, ?)
            """,
            (PARSER_VERSION, blob_sha, json.dumps(result, ensure_ascii=True)),
        )

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory raw Python function structures at every matched "
            "repository-month snapshot without using prior AGC outcomes."
        )
    )
    parser.add_argument(
        "--treatment-input",
        type=Path,
        default=Path(
            "repo_python/run-py-2a/strict/treatment/data/ts_repos_monthly.csv"
        ),
    )
    parser.add_argument(
        "--control-input",
        type=Path,
        default=Path(
            "repo_python/run-py-2a/strict/control/data/ts_repos_monthly.csv"
        ),
    )
    parser.add_argument(
        "--treatment-clone-dir",
        type=Path,
        default=Path("../treatment-repos"),
    )
    parser.add_argument(
        "--control-clone-dir",
        type=Path,
        default=Path("../control-repos"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("repo_python/run-py-9a/strict"),
    )
    parser.add_argument(
        "--cache-db",
        type=Path,
        default=Path(
            "repo_python/tmp/run-py-9a/strict/"
            "run-py-9a-blob-parse-cache-v1.sqlite3"
        ),
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help=(
            "Optional exact owner/repository name. Repeat to scan multiple "
            "repositories in a targeted smoke run."
        ),
    )
    parser.add_argument(
        "--max-unique-commits",
        type=int,
        default=0,
        help="Optional deterministic limit for a smoke run; zero scans all commits.",
    )
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args()


def run_git(
    repo_dir: Path,
    args: Iterable[str],
    *,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *list(args)],
        capture_output=True,
        check=False,
        text=text,
    )


def require_git(result: subprocess.CompletedProcess[Any], label: str) -> Any:
    if result.returncode != 0:
        stderr = result.stderr
        stdout = result.stdout
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        message = str(stderr).strip() or str(stdout).strip()
        raise RuntimeError(f"{label}: {message}")
    return result.stdout


def valid_sha(value: str) -> bool:
    return bool(FULL_SHA_RE.fullmatch(value.strip()))


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def normalize_month(value: str) -> str:
    text = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", text):
        raise ValidationError(f"Invalid repository-month value: {value!r}")
    month = text[:7]
    year, month_number = month.split("-")
    if not (1 <= int(month_number) <= 12):
        raise ValidationError(f"Invalid repository-month value: {value!r}")
    return f"{int(year):04d}-{int(month_number):02d}"


def load_input_rows(path: Path, source: str, clone_dir: Path) -> list[InputRow]:
    if source not in ALLOWED_SOURCES:
        raise ValidationError(f"Unsupported dataset source: {source}")
    if not path.is_file():
        raise FileNotFoundError(f"Repository-month input not found: {path}")
    if not clone_dir.is_dir():
        raise FileNotFoundError(f"Clone directory not found: {clone_dir}")

    rows: list[InputRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        time_column = "month" if "month" in columns else "time" if "time" in columns else ""
        missing = {"repo_name", "latest_commit"} - set(columns)
        if not time_column or missing:
            raise ValidationError(
                f"Required columns are missing in {path}: "
                f"time/month plus {sorted(missing)}; available={columns}"
            )
        for line_number, raw in enumerate(reader, start=2):
            repo_name = str(raw.get("repo_name", "")).strip()
            commit = str(raw.get("latest_commit", "")).strip().lower()
            if not repo_name or "/" not in repo_name:
                raise ValidationError(
                    f"Invalid repo_name at {path}:{line_number}: {repo_name!r}"
                )
            if not valid_sha(commit):
                raise ValidationError(
                    f"Invalid latest_commit at {path}:{line_number}: {commit!r}"
                )
            rows.append(
                InputRow(
                    dataset_source=source,
                    repo_name=repo_name,
                    month=normalize_month(str(raw.get(time_column, ""))),
                    latest_commit=commit,
                    clone_dir=clone_dir.resolve(),
                )
            )
    return rows


def validate_input_rows(rows: Sequence[InputRow]) -> None:
    if not rows:
        raise ValidationError("No repository-month input rows were loaded")
    keys = [
        (row.dataset_source, row.repo_name, row.month)
        for row in rows
    ]
    duplicates = len(keys) - len(set(keys))
    if duplicates:
        raise ValidationError(
            f"Repository-month inputs contain {duplicates} duplicate keys"
        )
    conflicting = defaultdict(set)
    for row in rows:
        conflicting[(row.dataset_source, row.repo_name, row.month)].add(
            row.latest_commit
        )
    conflicts = sum(len(values) > 1 for values in conflicting.values())
    if conflicts:
        raise ValidationError(
            f"Repository-month inputs contain {conflicts} conflicting commit mappings"
        )


def decode_git_path(payload: bytes) -> str:
    return payload.decode("utf-8", errors="surrogateescape")


def list_tree(repo_dir: Path, commit: str) -> list[TreeEntry]:
    payload = require_git(
        run_git(repo_dir, ["ls-tree", "-r", "-z", commit]),
        f"git ls-tree failed for {commit}",
    )
    entries: list[TreeEntry] = []
    for item in payload.split(b"\0"):
        if not item:
            continue
        metadata, path_bytes = item.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
        entries.append(
            TreeEntry(
                mode=mode,
                object_type=object_type,
                object_id=object_id,
                relative_path=decode_git_path(path_bytes),
            )
        )
    return entries


def python_path_selection(entry: TreeEntry) -> tuple[bool, str]:
    path = PurePosixPath(entry.relative_path)
    if path.suffix.lower() != ".py":
        return False, "not_python"
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False, "unsafe_path"
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False, "excluded_directory"
    if entry.object_type != "blob":
        return False, f"git_object_type_{entry.object_type}"
    if entry.mode == "120000":
        return False, "symlink"
    return True, "eligible"


def decode_python_source(payload: bytes) -> tuple[str, str]:
    reader = io.BytesIO(payload).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return payload.decode(encoding), encoding


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_slice(
    lines: Sequence[str],
    start_line: int,
    end_line: int,
) -> str:
    if start_line <= 0 or end_line < start_line:
        return ""
    return "".join(lines[start_line - 1 : end_line])


def decorator_callable(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = target
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    try:
        return ast.unparse(target).strip()
    except Exception:
        return type(target).__name__


def decorator_root(callable_name: str) -> str:
    return callable_name.split(".", 1)[0] if callable_name else ""


def first_parameter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    positional = [*node.args.posonlyargs, *node.args.args]
    if positional:
        return positional[0].arg
    if node.args.vararg is not None:
        return node.args.vararg.arg
    if node.args.kwonlyargs:
        return node.args.kwonlyargs[0].arg
    if node.args.kwarg is not None:
        return node.args.kwarg.arg
    return ""


def definition_start_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    decorator_lines = [
        int(item.lineno)
        for item in node.decorator_list
        if hasattr(item, "lineno")
    ]
    return min([int(node.lineno), *decorator_lines])


def build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    result: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            result[child] = parent
    return result


def ancestor_chain(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> list[ast.AST]:
    result: list[ast.AST] = []
    current = parents.get(node)
    while current is not None:
        result.append(current)
        current = parents.get(current)
    return result


def definition_scopes(ancestors: Sequence[ast.AST]) -> list[ast.AST]:
    scope_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return [item for item in reversed(ancestors) if isinstance(item, scope_types)]


def scope_kind(node: ast.AST) -> str:
    if isinstance(node, ast.Module):
        return "module"
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_function"
    if isinstance(node, ast.FunctionDef):
        return "function"
    return type(node).__name__


def scope_name(node: ast.AST) -> str:
    if isinstance(node, ast.Module):
        return "<module>"
    return str(getattr(node, "name", type(node).__name__))


def parse_blob(payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "source_bytes": len(payload),
        "physical_lines": payload.count(b"\n")
        + (1 if payload and not payload.endswith(b"\n") else 0),
        "source_encoding": "",
        "parse_status": "not_started",
        "parse_error_type": "",
        "parse_error_message": "",
        "functions": [],
    }
    try:
        source, encoding = decode_python_source(payload)
        result["source_encoding"] = encoding
        tree = ast.parse(source, filename="<git-blob>", type_comments=True)
        parents = build_parent_map(tree)
        lines = source.splitlines(keepends=True)
        function_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        function_nodes.sort(
            key=lambda node: (
                int(getattr(node, "lineno", 0)),
                int(getattr(node, "col_offset", 0)),
                str(node.name),
            )
        )

        function_rows: list[dict[str, Any]] = []
        for ordinal, node in enumerate(function_nodes, start=1):
            ancestors = ancestor_chain(node, parents)
            scopes = definition_scopes(ancestors)
            non_module_scopes = [
                item for item in scopes if not isinstance(item, ast.Module)
            ]
            class_scopes = [
                item for item in non_module_scopes if isinstance(item, ast.ClassDef)
            ]
            function_scopes = [
                item
                for item in non_module_scopes
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            nearest_definition = non_module_scopes[-1] if non_module_scopes else tree
            parent = parents.get(node)
            start_line = definition_start_line(node)
            definition_line = int(node.lineno)
            end_line = int(getattr(node, "end_lineno", node.lineno))
            body_start = min(
                (int(getattr(item, "lineno", definition_line)) for item in node.body),
                default=definition_line,
            )
            body_end = max(
                (
                    int(getattr(item, "end_lineno", getattr(item, "lineno", end_line)))
                    for item in node.body
                ),
                default=end_line,
            )
            function_source = source_slice(lines, start_line, end_line)
            body_source = source_slice(lines, body_start, body_end)
            raw_decorators: list[str] = []
            callable_decorators: list[str] = []
            decorator_rows: list[dict[str, Any]] = []
            for decorator_index, decorator in enumerate(
                node.decorator_list,
                start=1,
            ):
                raw = ast.get_source_segment(source, decorator)
                if raw is None:
                    raw = ast.unparse(decorator)
                raw = raw.strip()
                callable_name = decorator_callable(decorator)
                raw_decorators.append(raw)
                callable_decorators.append(callable_name)
                decorator_rows.append(
                    {
                        "decorator_index": decorator_index,
                        "decorator_raw": raw,
                        "decorator_callable": callable_name,
                        "decorator_root": decorator_root(callable_name),
                        "decorator_expression_type": type(decorator).__name__,
                        "decorator_is_call": int(isinstance(decorator, ast.Call)),
                    }
                )

            scope_names = [scope_name(item) for item in non_module_scopes]
            qualified_name = ".".join([*scope_names, node.name])
            control_flow_depth = sum(
                isinstance(
                    item,
                    (
                        ast.If,
                        ast.For,
                        ast.AsyncFor,
                        ast.While,
                        ast.Try,
                        ast.With,
                        ast.AsyncWith,
                        ast.Match,
                    ),
                )
                for item in ancestors
            )
            definition_parent_kind = scope_kind(nearest_definition)
            function_rows.append(
                {
                    "function_ordinal": ordinal,
                    "qualified_function_name": qualified_name,
                    "function_name": node.name,
                    "function_node_type": type(node).__name__,
                    "is_async": int(isinstance(node, ast.AsyncFunctionDef)),
                    "start_line": start_line,
                    "definition_line": definition_line,
                    "end_line": end_line,
                    "direct_parent_node_type": (
                        type(parent).__name__ if parent is not None else ""
                    ),
                    "definition_parent_kind": definition_parent_kind,
                    "definition_parent_name": scope_name(nearest_definition),
                    "ancestor_node_types_json": json.dumps(
                        [type(item).__name__ for item in ancestors],
                        ensure_ascii=True,
                    ),
                    "definition_scope_names_json": json.dumps(
                        scope_names,
                        ensure_ascii=True,
                    ),
                    "definition_scope_kinds_json": json.dumps(
                        [scope_kind(item) for item in non_module_scopes],
                        ensure_ascii=True,
                    ),
                    "class_ancestor_names_json": json.dumps(
                        [scope_name(item) for item in class_scopes],
                        ensure_ascii=True,
                    ),
                    "function_ancestor_names_json": json.dumps(
                        [scope_name(item) for item in function_scopes],
                        ensure_ascii=True,
                    ),
                    "class_depth": len(class_scopes),
                    "function_depth": len(function_scopes),
                    "control_flow_depth": int(control_flow_depth),
                    "is_module_level": int(definition_parent_kind == "module"),
                    "is_direct_class_scope": int(definition_parent_kind == "class"),
                    "is_nested_in_function": int(bool(function_scopes)),
                    "is_class_contained": int(bool(class_scopes)),
                    "decorator_count": len(node.decorator_list),
                    "decorators_raw_json": json.dumps(
                        raw_decorators,
                        ensure_ascii=True,
                    ),
                    "decorators_callable_json": json.dumps(
                        callable_decorators,
                        ensure_ascii=True,
                    ),
                    "first_parameter_name": first_parameter(node),
                    "positional_parameter_count": len(node.args.posonlyargs)
                    + len(node.args.args),
                    "keyword_only_parameter_count": len(node.args.kwonlyargs),
                    "has_vararg": int(node.args.vararg is not None),
                    "has_kwarg": int(node.args.kwarg is not None),
                    "is_dunder_name": int(
                        len(node.name) > 4
                        and node.name.startswith("__")
                        and node.name.endswith("__")
                    ),
                    "function_source_sha256": sha256_text(function_source),
                    "function_body_source_sha256": sha256_text(body_source),
                    "function_ast_sha256": sha256_text(
                        ast.dump(
                            node,
                            annotate_fields=True,
                            include_attributes=False,
                        )
                    ),
                    "function_body_ast_sha256": sha256_text(
                        ast.dump(
                            ast.Module(body=node.body, type_ignores=[]),
                            annotate_fields=True,
                            include_attributes=False,
                        )
                    ),
                    "decorators": decorator_rows,
                }
            )

        result["parse_status"] = "success"
        result["functions"] = function_rows
    except Exception as error:
        result["parse_status"] = "failure"
        result["parse_error_type"] = type(error).__name__
        result["parse_error_message"] = str(error).replace("\x00", "\\0")
        result["functions"] = []
    return result


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[dict[str, Any]],
) -> int:
    table = OutputTable(path, list(columns))
    table.open()
    try:
        for row in rows:
            table.write(row)
        count = table.rows_written
        table.finish()
        return count
    except Exception:
        table.abort()
        raise


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def prepare_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {path}. "
                "Use --overwrite-output only for intentional replacement."
            )
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def self_test() -> None:
    source = b'''
def module_function(value):
    return value

class Outer:
    @classmethod
    def build(cls, value):
        def nested(local):
            return local
        return nested(value)

    class Inner:
        @property
        def value(self):
            return 1

async def module_async():
    return None
'''
    parsed = parse_blob(source)
    if parsed["parse_status"] != "success":
        raise AssertionError(parsed)
    functions = parsed["functions"]
    by_name = {row["qualified_function_name"]: row for row in functions}
    assert by_name["module_function"]["is_module_level"] == 1
    assert by_name["Outer.build"]["is_direct_class_scope"] == 1
    assert by_name["Outer.build.nested"]["is_nested_in_function"] == 1
    assert by_name["Outer.build.nested"]["is_class_contained"] == 1
    assert by_name["Outer.Inner.value"]["class_depth"] == 2
    assert by_name["module_async"]["is_async"] == 1
    assert json.loads(by_name["Outer.build"]["decorators_callable_json"]) == [
        "classmethod"
    ]

    failed = parse_blob(b"def broken(:\n    pass\n")
    assert failed["parse_status"] == "failure"
    assert failed["parse_error_type"] == "SyntaxError"
    print("run-py-9a self-test PASS")


def scan(args: argparse.Namespace) -> dict[str, Any]:
    treatment_input = args.treatment_input.expanduser().resolve()
    control_input = args.control_input.expanduser().resolve()
    treatment_clones = args.treatment_clone_dir.expanduser().resolve()
    control_clones = args.control_clone_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    cache_path = args.cache_db.expanduser().resolve()

    rows = [
        *load_input_rows(treatment_input, "treatment", treatment_clones),
        *load_input_rows(control_input, "control", control_clones),
    ]
    validate_input_rows(rows)

    requested_repos = set(args.repo)
    unknown_repos = requested_repos - {row.repo_name for row in rows}
    if unknown_repos:
        raise ValidationError(
            f"Requested repositories are absent from the inputs: {sorted(unknown_repos)}"
        )
    if requested_repos:
        rows = [row for row in rows if row.repo_name in requested_repos]

    unique_commit_rows: list[InputRow] = []
    seen_commit_keys: set[tuple[str, str, str]] = set()
    for row in sorted(
        rows,
        key=lambda item: (
            item.dataset_source,
            item.repo_name.lower(),
            item.latest_commit,
            item.month,
        ),
    ):
        key = (row.dataset_source, row.repo_name, row.latest_commit)
        if key not in seen_commit_keys:
            seen_commit_keys.add(key)
            unique_commit_rows.append(row)

    if args.max_unique_commits < 0:
        raise ValidationError("--max-unique-commits cannot be negative")
    if args.max_unique_commits:
        unique_commit_rows = unique_commit_rows[: args.max_unique_commits]
        retained_keys = {
            (row.dataset_source, row.repo_name, row.latest_commit)
            for row in unique_commit_rows
        }
        rows = [
            row
            for row in rows
            if (row.dataset_source, row.repo_name, row.latest_commit)
            in retained_keys
        ]

    prepare_output_dir(output_dir, args.overwrite_output)

    file_table = OutputTable(
        output_dir / "run-py-9a-python-file-inventory.csv",
        FILE_COLUMNS,
    )
    function_table = OutputTable(
        output_dir / "run-py-9a-python-function-inventory.csv",
        FUNCTION_COLUMNS,
    )
    decorator_table = OutputTable(
        output_dir / "run-py-9a-decorator-inventory.csv",
        DECORATOR_COLUMNS,
    )
    failure_table = OutputTable(
        output_dir / "run-py-9a-parse-failures.csv",
        PARSE_FAILURE_COLUMNS,
    )
    tables = [file_table, function_table, decorator_table, failure_table]
    for table in tables:
        table.open()

    cache = BlobCache(cache_path)
    commit_stats: dict[tuple[str, str, str], dict[str, Any]] = {}
    critical_errors: list[dict[str, str]] = []
    structure_counts: Counter[tuple[Any, ...]] = Counter()
    structure_repos: defaultdict[tuple[Any, ...], set[str]] = defaultdict(set)
    structure_commits: defaultdict[tuple[Any, ...], set[str]] = defaultdict(set)
    parent_counts: Counter[tuple[Any, ...]] = Counter()
    parent_repos: defaultdict[tuple[Any, ...], set[str]] = defaultdict(set)
    decorator_counts: Counter[tuple[str, str, str, int]] = Counter()
    decorator_repos: defaultdict[tuple[str, str, str, int], set[str]] = defaultdict(set)
    started_at = datetime.now(timezone.utc)
    try:
        total = len(unique_commit_rows)
        for number, row in enumerate(unique_commit_rows, start=1):
            key = (row.dataset_source, row.repo_name, row.latest_commit)
            repo_dir = row.clone_dir / repo_slug(row.repo_name)
            stats: dict[str, Any] = {
                "repo_dir": str(repo_dir),
                "commit_available": 0,
                "tree_scan_status": "not_started",
                "tracked_python_paths": 0,
                "eligible_python_files": 0,
                "excluded_python_paths": 0,
                "symlink_python_paths": 0,
                "unique_eligible_python_blobs": 0,
                "parsed_python_files": 0,
                "parse_failure_files": 0,
                "functions": 0,
                "module_level_functions": 0,
                "direct_class_scope_functions": 0,
                "function_nested_functions": 0,
                "class_contained_functions": 0,
                "decorated_functions": 0,
                "decorator_occurrences": 0,
            }
            commit_stats[key] = stats

            if not repo_dir.is_dir():
                stats["tree_scan_status"] = "missing_repository"
                critical_errors.append(
                    {
                        "dataset_source": row.dataset_source,
                        "repo_name": row.repo_name,
                        "latest_commit": row.latest_commit,
                        "error": f"Repository directory not found: {repo_dir}",
                    }
                )
                continue

            commit_check = run_git(
                repo_dir,
                ["cat-file", "-e", f"{row.latest_commit}^{{commit}}"],
            )
            if commit_check.returncode != 0:
                stats["tree_scan_status"] = "missing_commit"
                message = commit_check.stderr.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                critical_errors.append(
                    {
                        "dataset_source": row.dataset_source,
                        "repo_name": row.repo_name,
                        "latest_commit": row.latest_commit,
                        "error": message or "Commit object is unavailable",
                    }
                )
                continue
            stats["commit_available"] = 1

            try:
                tree_entries = list_tree(repo_dir, row.latest_commit)
                stats["tree_scan_status"] = "success"
            except Exception as error:
                stats["tree_scan_status"] = "failure"
                critical_errors.append(
                    {
                        "dataset_source": row.dataset_source,
                        "repo_name": row.repo_name,
                        "latest_commit": row.latest_commit,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                continue

            python_entries = [
                entry
                for entry in tree_entries
                if PurePosixPath(entry.relative_path).suffix.lower() == ".py"
            ]
            stats["tracked_python_paths"] = len(python_entries)
            unique_eligible_blobs: set[str] = set()

            with CatFileBatch(repo_dir) as batch:
                for entry in python_entries:
                    eligible, reason = python_path_selection(entry)
                    if not eligible:
                        stats["excluded_python_paths"] += 1
                        if reason == "symlink":
                            stats["symlink_python_paths"] += 1
                        file_table.write(
                            {
                                "dataset_source": row.dataset_source,
                                "repo_name": row.repo_name,
                                "latest_commit": row.latest_commit,
                                "relative_path": entry.relative_path,
                                "git_mode": entry.mode,
                                "git_object_type": entry.object_type,
                                "git_blob_sha": entry.object_id,
                                "scan_eligible": 0,
                                "selection_reason": reason,
                                "parse_status": "not_scanned",
                                "function_count": 0,
                            }
                        )
                        continue

                    stats["eligible_python_files"] += 1
                    unique_eligible_blobs.add(entry.object_id)
                    parsed = cache.get(entry.object_id)
                    if parsed is None:
                        try:
                            payload = batch.read_blob(entry.object_id)
                            parsed = parse_blob(payload)
                        except Exception as error:
                            parsed = {
                                "content_sha256": "",
                                "source_bytes": 0,
                                "physical_lines": 0,
                                "source_encoding": "",
                                "parse_status": "failure",
                                "parse_error_type": type(error).__name__,
                                "parse_error_message": str(error),
                                "functions": [],
                            }
                        cache.put(entry.object_id, parsed)

                    functions = parsed.get("functions", [])
                    parse_status = str(parsed.get("parse_status", "failure"))
                    if parse_status == "success":
                        stats["parsed_python_files"] += 1
                    else:
                        stats["parse_failure_files"] += 1
                        failure_table.write(
                            {
                                "dataset_source": row.dataset_source,
                                "repo_name": row.repo_name,
                                "latest_commit": row.latest_commit,
                                "relative_path": entry.relative_path,
                                "git_blob_sha": entry.object_id,
                                "stage": "python_ast_parse",
                                "error_type": parsed.get(
                                    "parse_error_type",
                                    "UnknownError",
                                ),
                                "error_message": parsed.get(
                                    "parse_error_message",
                                    "",
                                ),
                            }
                        )

                    file_table.write(
                        {
                            "dataset_source": row.dataset_source,
                            "repo_name": row.repo_name,
                            "latest_commit": row.latest_commit,
                            "relative_path": entry.relative_path,
                            "git_mode": entry.mode,
                            "git_object_type": entry.object_type,
                            "git_blob_sha": entry.object_id,
                            "scan_eligible": 1,
                            "selection_reason": reason,
                            "content_sha256": parsed.get("content_sha256", ""),
                            "source_encoding": parsed.get("source_encoding", ""),
                            "source_bytes": parsed.get("source_bytes", 0),
                            "physical_lines": parsed.get("physical_lines", 0),
                            "parse_status": parse_status,
                            "parse_error_type": parsed.get(
                                "parse_error_type",
                                "",
                            ),
                            "parse_error_message": parsed.get(
                                "parse_error_message",
                                "",
                            ),
                            "function_count": len(functions),
                        }
                    )

                    for function in functions:
                        prefix = {
                            "dataset_source": row.dataset_source,
                            "repo_name": row.repo_name,
                            "latest_commit": row.latest_commit,
                            "relative_path": entry.relative_path,
                            "git_blob_sha": entry.object_id,
                            "function_ordinal": function["function_ordinal"],
                        }
                        function_table.write({**prefix, **function})
                        stats["functions"] += 1
                        stats["module_level_functions"] += int(
                            function["is_module_level"]
                        )
                        stats["direct_class_scope_functions"] += int(
                            function["is_direct_class_scope"]
                        )
                        stats["function_nested_functions"] += int(
                            function["is_nested_in_function"]
                        )
                        stats["class_contained_functions"] += int(
                            function["is_class_contained"]
                        )
                        stats["decorated_functions"] += int(
                            int(function["decorator_count"]) > 0
                        )
                        stats["decorator_occurrences"] += int(
                            function["decorator_count"]
                        )

                        structure_key = (
                            function["definition_parent_kind"],
                            function["direct_parent_node_type"],
                            int(function["class_depth"]),
                            int(function["function_depth"]),
                            int(function["control_flow_depth"]),
                            int(function["is_async"]),
                            int(int(function["decorator_count"]) > 0),
                        )
                        structure_counts[structure_key] += 1
                        structure_repos[structure_key].add(
                            f"{row.dataset_source}:{row.repo_name}"
                        )
                        structure_commits[structure_key].add(
                            f"{row.dataset_source}:{row.repo_name}:{row.latest_commit}"
                        )

                        parent_key = (
                            function["direct_parent_node_type"],
                            function["definition_parent_kind"],
                            function["ancestor_node_types_json"],
                        )
                        parent_counts[parent_key] += 1
                        parent_repos[parent_key].add(
                            f"{row.dataset_source}:{row.repo_name}"
                        )

                        for decorator in function.get("decorators", []):
                            decorator_table.write(
                                {
                                    **prefix,
                                    "qualified_function_name": function[
                                        "qualified_function_name"
                                    ],
                                    **decorator,
                                }
                            )
                            decorator_key = (
                                decorator["decorator_raw"],
                                decorator["decorator_callable"],
                                decorator["decorator_root"],
                                int(decorator["decorator_is_call"]),
                            )
                            decorator_counts[decorator_key] += 1
                            decorator_repos[decorator_key].add(
                                f"{row.dataset_source}:{row.repo_name}"
                            )

            stats["unique_eligible_python_blobs"] = len(unique_eligible_blobs)
            if number % max(1, args.progress_every) == 0 or number == total:
                print(
                    f"Progress: {number}/{total} unique repository commits; "
                    f"functions={function_table.rows_written}; "
                    f"parse_failures={failure_table.rows_written}; "
                    f"cache_hits={cache.hits}; cache_misses={cache.misses}",
                    flush=True,
                )
            if number % 25 == 0:
                cache.commit()

        for table in tables:
            table.finish()
        cache.commit()
    except Exception:
        for table in tables:
            table.abort()
        raise
    finally:
        cache.close()

    snapshot_rows: list[dict[str, Any]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            item.dataset_source,
            item.repo_name.lower(),
            item.month,
        ),
    ):
        key = (row.dataset_source, row.repo_name, row.latest_commit)
        snapshot_rows.append(
            {
                "dataset_source": row.dataset_source,
                "repo_name": row.repo_name,
                "month": row.month,
                "latest_commit": row.latest_commit,
                **commit_stats[key],
            }
        )
    snapshot_count = atomic_write_csv(
        output_dir / "run-py-9a-history-snapshot-manifest.csv",
        SNAPSHOT_COLUMNS,
        snapshot_rows,
    )

    structure_rows = []
    for key, count in sorted(
        structure_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        (
            definition_parent_kind,
            direct_parent_node_type,
            class_depth,
            function_depth,
            control_flow_depth,
            is_async,
            is_decorated,
        ) = key
        structure_rows.append(
            {
                "definition_parent_kind": definition_parent_kind,
                "direct_parent_node_type": direct_parent_node_type,
                "class_depth": class_depth,
                "function_depth": function_depth,
                "control_flow_depth": control_flow_depth,
                "is_async": is_async,
                "is_decorated": is_decorated,
                "function_occurrences": count,
                "repositories": len(structure_repos[key]),
                "repository_commits": len(structure_commits[key]),
            }
        )
    atomic_write_csv(
        output_dir / "run-py-9a-function-structure-counts.csv",
        [
            "definition_parent_kind",
            "direct_parent_node_type",
            "class_depth",
            "function_depth",
            "control_flow_depth",
            "is_async",
            "is_decorated",
            "function_occurrences",
            "repositories",
            "repository_commits",
        ],
        structure_rows,
    )

    parent_rows = []
    for key, count in sorted(
        parent_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        direct_parent, definition_parent, ancestor_types = key
        parent_rows.append(
            {
                "direct_parent_node_type": direct_parent,
                "definition_parent_kind": definition_parent,
                "ancestor_node_types_json": ancestor_types,
                "function_occurrences": count,
                "repositories": len(parent_repos[key]),
            }
        )
    atomic_write_csv(
        output_dir / "run-py-9a-ast-parent-patterns.csv",
        [
            "direct_parent_node_type",
            "definition_parent_kind",
            "ancestor_node_types_json",
            "function_occurrences",
            "repositories",
        ],
        parent_rows,
    )

    decorator_summary_rows = []
    for key, count in sorted(
        decorator_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        raw, callable_name, root, is_call = key
        decorator_summary_rows.append(
            {
                "decorator_raw": raw,
                "decorator_callable": callable_name,
                "decorator_root": root,
                "decorator_is_call": is_call,
                "decorator_occurrences": count,
                "repositories": len(decorator_repos[key]),
            }
        )
    atomic_write_csv(
        output_dir / "run-py-9a-decorator-structure-counts.csv",
        [
            "decorator_raw",
            "decorator_callable",
            "decorator_root",
            "decorator_is_call",
            "decorator_occurrences",
            "repositories",
        ],
        decorator_summary_rows,
    )

    missing_repositories = sum(
        stats["tree_scan_status"] == "missing_repository"
        for stats in commit_stats.values()
    )
    missing_commits = sum(
        stats["tree_scan_status"] == "missing_commit"
        for stats in commit_stats.values()
    )
    tree_failures = sum(
        stats["tree_scan_status"] == "failure"
        for stats in commit_stats.values()
    )
    successful_commits = sum(
        stats["tree_scan_status"] == "success"
        for stats in commit_stats.values()
    )
    parse_failures = sum(
        int(stats["parse_failure_files"])
        for stats in commit_stats.values()
    )

    checks = [
        {
            "check_name": "repository_month_keys_unique",
            "severity": "critical",
            "passed": True,
            "observed": snapshot_count,
            "expected": len(rows),
            "note": "Input uniqueness was validated before scanning.",
        },
        {
            "check_name": "all_repository_directories_available",
            "severity": "critical",
            "passed": missing_repositories == 0,
            "observed": missing_repositories,
            "expected": 0,
            "note": "Every target repository must resolve to a local clone.",
        },
        {
            "check_name": "all_snapshot_commits_available",
            "severity": "critical",
            "passed": missing_commits == 0,
            "observed": missing_commits,
            "expected": 0,
            "note": "Every latest_commit must exist in its local Git object store.",
        },
        {
            "check_name": "all_git_trees_scanned",
            "severity": "critical",
            "passed": tree_failures == 0
            and successful_commits == len(unique_commit_rows),
            "observed": successful_commits,
            "expected": len(unique_commit_rows),
            "note": "Every distinct repository commit must have a readable Git tree.",
        },
        {
            "check_name": "all_eligible_python_files_parse_clean",
            "severity": "diagnostic",
            "passed": parse_failures == 0,
            "observed": parse_failures,
            "expected": 0,
            "note": (
                "Parse failures are retained as observed data and do not erase "
                "otherwise valid snapshot scans."
            ),
        },
        {
            "check_name": "no_prior_outcome_inputs_used",
            "severity": "critical",
            "passed": True,
            "observed": "run-py-2a repository-month histories and local Git objects",
            "expected": "no run-py-7 or run-py-8 CSV inputs",
            "note": "The scanner is outcome-blind by construction.",
        },
    ]
    atomic_write_csv(
        output_dir / "run-py-9a-repository-scan-qc.csv",
        ["check_name", "severity", "passed", "observed", "expected", "note"],
        checks,
    )

    critical_failed = sum(
        row["severity"] == "critical" and not bool(row["passed"])
        for row in checks
    )
    completed_at = datetime.now(timezone.utc)
    status = (
        "FAIL"
        if critical_failed
        else "PASS_WITH_PARSE_FAILURES"
        if parse_failures
        else "PASS"
    )
    metadata = {
        "status": status,
        "script_version": SCRIPT_VERSION,
        "parser_version": PARSER_VERSION,
        "python_version": sys.version,
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": completed_at.isoformat(),
        "elapsed_seconds": (completed_at - started_at).total_seconds(),
        "scientific_scope": {
            "effect_results_inspected": False,
            "agc_classification_performed": False,
            "predefined_method_taxonomy_applied": False,
            "run_py_7_outputs_consumed": False,
            "run_py_8_outputs_consumed": False,
            "unit_scanned": "exact repository-month latest_commit snapshot",
            "file_selection": (
                "tracked .py blobs excluding established generated/cache/vendor paths"
            ),
        },
        "inputs": {
            "treatment_input": str(treatment_input),
            "treatment_input_sha256": hash_file(treatment_input),
            "control_input": str(control_input),
            "control_input_sha256": hash_file(control_input),
            "treatment_clone_dir": str(treatment_clones),
            "control_clone_dir": str(control_clones),
        },
        "selection": {
            "requested_repositories": sorted(requested_repos),
            "max_unique_commits": args.max_unique_commits,
        },
        "counts": {
            "repository_month_rows": len(rows),
            "repositories": len(
                {(row.dataset_source, row.repo_name) for row in rows}
            ),
            "unique_repository_commits": len(unique_commit_rows),
            "successful_repository_commits": successful_commits,
            "file_inventory_rows": file_table.rows_written,
            "function_inventory_rows": function_table.rows_written,
            "decorator_inventory_rows": decorator_table.rows_written,
            "parse_failure_rows": failure_table.rows_written,
            "critical_errors": len(critical_errors),
            "critical_failed_checks": critical_failed,
            "blob_cache_hits": cache.hits,
            "blob_cache_misses": cache.misses,
        },
        "critical_errors": critical_errors,
        "outputs": {
            "history_snapshot_manifest": str(
                output_dir / "run-py-9a-history-snapshot-manifest.csv"
            ),
            "python_file_inventory": str(
                output_dir / "run-py-9a-python-file-inventory.csv"
            ),
            "python_function_inventory": str(
                output_dir / "run-py-9a-python-function-inventory.csv"
            ),
            "decorator_inventory": str(
                output_dir / "run-py-9a-decorator-inventory.csv"
            ),
            "decorator_structure_counts": str(
                output_dir / "run-py-9a-decorator-structure-counts.csv"
            ),
            "ast_parent_patterns": str(
                output_dir / "run-py-9a-ast-parent-patterns.csv"
            ),
            "function_structure_counts": str(
                output_dir / "run-py-9a-function-structure-counts.csv"
            ),
            "parse_failures": str(
                output_dir / "run-py-9a-parse-failures.csv"
            ),
            "repository_scan_qc": str(
                output_dir / "run-py-9a-repository-scan-qc.csv"
            ),
        },
    }
    atomic_write_json(
        output_dir / "run-py-9a-scan-metadata.json",
        metadata,
    )
    return metadata


def main() -> int:
    args = parse_args()
    if args.self_test or args.self_test_only:
        self_test()
    if args.self_test_only:
        return 0

    metadata = scan(args)
    print(json.dumps(metadata["counts"], indent=2, sort_keys=True))
    print(f"Status: {metadata['status']}")
    print(f"Output directory: {args.output_dir.expanduser().resolve()}")
    return 0 if metadata["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
