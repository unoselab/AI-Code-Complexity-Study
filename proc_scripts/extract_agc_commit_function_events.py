#!/usr/bin/env python3
"""Extract structurally changed Python function events from commit pairs.

Input
-----
A commit-pair CSV produced by ``prepare_agc_commit_function_scan_manifest.py``.
Each eligible row defines one comparison from a commit's direct first parent
(X-1) to the commit itself (X).

Output
------
- One manifest row per structurally added or modified named Python function.
- One standalone, dedented Python source artifact per event.
- Repository-month event counts and extraction QC artifacts.

Function scope
--------------
- module-level functions
- methods defined inside classes
- nested functions
- asynchronous variants of all function types above

Class definitions are not emitted as events. Lambda expressions are not emitted
as independent events. Nested definitions are removed from ancestor structural
fingerprints so that changing a nested function does not automatically create a
second change event for its enclosing function.

Repeated edits to the same function in separate commits remain separate events,
including a later commit that reverts an earlier change.
"""

from __future__ import annotations

import argparse
import ast
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")

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

PAIR_REQUIRED = {
    "dataset_source",
    "repo_name",
    "month",
    "scan_parent_commit",
    "scan_current_commit",
    "commit_order",
    "primary_scan_eligible",
    "repo_dir",
}

MANIFEST_COLUMNS = [
    "function_event_id",
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "commit_order",
    "relative_path",
    "parent_relative_path",
    "diff_status",
    "qualified_function_name",
    "function_name",
    "function_kind",
    "occurrence_index",
    "change_type",
    "start_line",
    "end_line",
    "parent_start_line",
    "parent_end_line",
    "structural_sha256",
    "parent_structural_sha256",
    "function_source_relative_path",
    "content_sha256",
    "source_bytes",
]

AUDIT_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "commit_order",
    "diff_status",
    "relative_path",
    "parent_relative_path",
    "current_functions",
    "parent_functions",
    "added_function_events",
    "modified_function_events",
    "unchanged_functions",
    "deleted_functions_ignored",
    "file_status",
    "error_message",
]

REPO_MONTH_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "commits_scanned",
    "commits_with_python_changes",
    "commits_with_function_change_events",
    "function_change_events",
    "added_function_events",
    "modified_function_events",
    "unique_changed_functions",
    "unique_changed_files",
]

ERROR_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "relative_path",
    "stage",
    "error",
]


@dataclass(frozen=True)
class ChangedPath:
    status: str
    old_path: str
    new_path: str


@dataclass(frozen=True)
class FunctionRecord:
    qualified_name: str
    function_name: str
    function_kind: str
    occurrence_index: int
    start_line: int
    end_line: int
    structural_text: str
    structural_sha256: str
    source_text: str

    @property
    def identity(self) -> tuple[str, int]:
        return self.qualified_name, self.occurrence_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract commit-function change events for fresh AGC detection."
    )
    parser.add_argument(
        "--input-commit-pairs",
        type=Path,
        default=Path("repo_python/run-py-5a/strict/commit_parent_pairs.csv"),
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
        "--output-manifest",
        type=Path,
        default=Path(
            "repo_python/run-py-5a/strict/commit_function_detection_manifest.csv"
        ),
    )
    parser.add_argument(
        "--function-source-root",
        type=Path,
        default=Path("repo_python/run-py-5a/strict/commit_function_sources"),
    )
    parser.add_argument(
        "--qc-dir",
        type=Path,
        default=Path("repo_python/tmp/run-py-5a/strict"),
    )
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--max-pairs", type=int, default=0)
    parser.add_argument("--overwrite-source-root", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def run_git_bytes(repo_dir: Path, args: Iterable[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *list(args)],
        capture_output=True,
        check=False,
    )


def require_git_bytes(result: subprocess.CompletedProcess[bytes], label: str) -> bytes:
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            message = result.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{label}: {message}")
    return result.stdout


def valid_sha(value: str) -> bool:
    return bool(FULL_SHA_RE.fullmatch(value.strip()))


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def safe_path_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned or "unknown"


def eligible_python_path(path_text: str) -> bool:
    if not path_text:
        return False
    path = PurePosixPath(path_text)
    return (
        not path.is_absolute()
        and path.suffix.lower() == ".py"
        and not any(part in EXCLUDED_PARTS for part in path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def decode_git_path(raw: bytes) -> str:
    return raw.decode("utf-8", errors="surrogateescape")


def parse_name_status_z(payload: bytes) -> list[ChangedPath]:
    tokens = payload.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    rows: list[ChangedPath] = []
    index = 0
    while index < len(tokens):
        status = decode_git_path(tokens[index])
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise ValueError("Malformed rename/copy name-status output")
            old_path = decode_git_path(tokens[index])
            new_path = decode_git_path(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                raise ValueError("Malformed name-status output")
            path = decode_git_path(tokens[index])
            index += 1
            old_path = "" if status.startswith("A") else path
            new_path = "" if status.startswith("D") else path
        rows.append(ChangedPath(status=status, old_path=old_path, new_path=new_path))
    return rows


def list_changed_paths(repo_dir: Path, parent: str, current: str) -> list[ChangedPath]:
    if parent == EMPTY_TREE_SHA:
        args = [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-M",
            "-z",
            current,
            "--",
        ]
    else:
        args = [
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-M",
            "-z",
            parent,
            current,
            "--",
        ]
    payload = require_git_bytes(run_git_bytes(repo_dir, args), "git diff-tree failed")
    return parse_name_status_z(payload)


def git_blob(repo_dir: Path, commit: str, relative_path: str) -> bytes:
    if commit == EMPTY_TREE_SHA or not relative_path:
        raise FileNotFoundError("Blob does not exist in empty tree")
    spec = f"{commit}:{relative_path}"
    result = run_git_bytes(repo_dir, ["show", spec])
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise FileNotFoundError(f"Cannot read {spec}: {message}")
    return result.stdout


def decode_python_source(payload: bytes) -> str:
    reader = io.BytesIO(payload).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return payload.decode(encoding)


def structural_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class NestedDefinitionStripper(ast.NodeTransformer):
    """Remove nested named definitions from an enclosing function fingerprint."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        return None


def direct_function_fingerprint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    clone = copy.deepcopy(node)
    stripper = NestedDefinitionStripper()
    clone.body = [
        transformed
        for statement in clone.body
        if (transformed := stripper.visit(statement)) is not None
    ]
    return ast.dump(clone, annotate_fields=True, include_attributes=False)


def source_start_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    decorator_lines = [
        int(decorator.lineno)
        for decorator in node.decorator_list
        if hasattr(decorator, "lineno")
    ]
    return min([int(node.lineno), *decorator_lines])


def extract_source_segment(
    source_lines: Sequence[str],
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, int, int]:
    start_line = source_start_line(node)
    end_line = int(getattr(node, "end_lineno", node.lineno))
    segment = "".join(source_lines[start_line - 1 : end_line])
    normalized = textwrap.dedent(segment).rstrip() + "\n"
    ast.parse(normalized)
    return normalized, start_line, end_line


def function_kind(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    scope_kinds: Sequence[str],
) -> str:
    is_async = isinstance(node, ast.AsyncFunctionDef)
    if scope_kinds and scope_kinds[-1] == "class":
        return "async_method" if is_async else "method"
    if "function" in scope_kinds:
        return "nested_async_function" if is_async else "nested_function"
    return "module_async_function" if is_async else "module_function"


def iter_child_definitions(statements: Sequence[ast.stmt]) -> Iterator[ast.AST]:
    for statement in statements:
        yield statement


def extract_functions(source: str) -> list[FunctionRecord]:
    tree = ast.parse(source, type_comments=True)
    source_lines = source.splitlines(keepends=True)
    occurrence_counts: Counter[str] = Counter()
    records: list[FunctionRecord] = []

    def walk_statements(
        statements: Sequence[ast.stmt],
        scope_names: list[str],
        scope_kinds: list[str],
    ) -> None:
        for statement in iter_child_definitions(statements):
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified_base = ".".join([*scope_names, statement.name])
                occurrence_counts[qualified_base] += 1
                occurrence_index = occurrence_counts[qualified_base]
                source_text, start_line, end_line = extract_source_segment(
                    source_lines,
                    statement,
                )
                fingerprint = direct_function_fingerprint(statement)
                records.append(
                    FunctionRecord(
                        qualified_name=qualified_base,
                        function_name=statement.name,
                        function_kind=function_kind(statement, scope_kinds),
                        occurrence_index=occurrence_index,
                        start_line=start_line,
                        end_line=end_line,
                        structural_text=fingerprint,
                        structural_sha256=structural_sha(fingerprint),
                        source_text=source_text,
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
                nested_bodies: list[Sequence[ast.stmt]] = []
                for field_name in (
                    "body",
                    "orelse",
                    "finalbody",
                ):
                    value = getattr(statement, field_name, None)
                    if isinstance(value, list) and value and all(
                        isinstance(item, ast.stmt) for item in value
                    ):
                        nested_bodies.append(value)
                handlers = getattr(statement, "handlers", None)
                if isinstance(handlers, list):
                    for handler in handlers:
                        if isinstance(handler, ast.ExceptHandler):
                            nested_bodies.append(handler.body)
                cases = getattr(statement, "cases", None)
                if isinstance(cases, list):
                    for case in cases:
                        body = getattr(case, "body", None)
                        if isinstance(body, list):
                            nested_bodies.append(body)
                for body in nested_bodies:
                    walk_statements(body, scope_names, scope_kinds)

    walk_statements(tree.body, [], [])
    return records


def compare_function_sets(
    parent_records: Sequence[FunctionRecord],
    current_records: Sequence[FunctionRecord],
) -> tuple[list[tuple[FunctionRecord, FunctionRecord | None, str]], int, int]:
    parent_by_key = {record.identity: record for record in parent_records}
    current_by_key = {record.identity: record for record in current_records}
    events: list[tuple[FunctionRecord, FunctionRecord | None, str]] = []
    unchanged = 0

    for key, current_record in current_by_key.items():
        parent_record = parent_by_key.get(key)
        if parent_record is None:
            events.append((current_record, None, "added"))
        elif current_record.structural_sha256 != parent_record.structural_sha256:
            events.append((current_record, parent_record, "modified"))
        else:
            unchanged += 1

    deleted_ignored = sum(key not in current_by_key for key in parent_by_key)
    return events, unchanged, deleted_ignored


def deterministic_event_id(
    source: str,
    repo_name: str,
    month: str,
    commit: str,
    relative_path: str,
    qualified_name: str,
    occurrence_index: int,
    change_type: str,
) -> str:
    payload = "\0".join(
        [
            source,
            repo_name,
            month,
            commit,
            relative_path,
            qualified_name,
            str(occurrence_index),
            change_type,
        ]
    ).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(payload).hexdigest()[:24]


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, quoting=csv.QUOTE_MINIMAL)
    os.replace(temporary, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_source_artifact(
    root: Path,
    dataset_source: str,
    repo_name: str,
    month: str,
    commit: str,
    event_id: str,
    source_text: str,
) -> tuple[str, str, int]:
    relative = Path(
        safe_path_part(dataset_source),
        safe_path_part(repo_slug(repo_name)),
        safe_path_part(month),
        safe_path_part(commit),
        f"{event_id}.py",
    )
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = source_text.encode("utf-8")
    temporary = destination.with_suffix(".py.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)
    return relative.as_posix(), content_sha(payload), len(payload)


def load_pairs(path: Path) -> pd.DataFrame:
    pairs = pd.read_csv(
        path,
        dtype={
            "scan_parent_commit": "string",
            "scan_current_commit": "string",
        },
        low_memory=False,
    )
    missing = sorted(PAIR_REQUIRED - set(pairs.columns))
    if missing:
        raise ValueError(f"Commit-pair input missing columns: {missing}")

    for column in [
        "dataset_source",
        "repo_name",
        "month",
        "scan_parent_commit",
        "scan_current_commit",
        "repo_dir",
    ]:
        pairs[column] = pairs[column].fillna("").astype(str).str.strip()
    for column in ["commit_order", "primary_scan_eligible"]:
        pairs[column] = pd.to_numeric(pairs[column], errors="coerce")
        if pairs[column].isna().any():
            raise ValueError(f"Commit-pair column must be numeric: {column}")
        pairs[column] = pairs[column].astype(int)

    invalid_sources = sorted(
        set(pairs["dataset_source"]) - {"treatment", "control"}
    )
    if invalid_sources:
        raise ValueError(f"Unsupported dataset sources: {invalid_sources}")

    pairs = pairs.loc[pairs["primary_scan_eligible"].eq(1)].copy()
    duplicate_keys = int(
        pairs.duplicated(
            ["dataset_source", "repo_name", "month", "scan_current_commit"]
        ).sum()
    )
    if duplicate_keys:
        raise ValueError(f"Duplicate eligible commit-pair rows: {duplicate_keys}")
    return pairs.sort_values(
        ["dataset_source", "repo_name", "month", "commit_order"]
    ).reset_index(drop=True)


def resolve_repo_dir(
    row: Any,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> Path:
    expected_root = (
        treatment_clone_dir
        if str(row.dataset_source) == "treatment"
        else control_clone_dir
    )
    expected = expected_root / repo_slug(str(row.repo_name))
    supplied = Path(str(row.repo_dir))
    if supplied.is_dir() and (supplied / ".git").exists():
        return supplied.resolve()
    return expected.resolve()


def extract_events(
    pairs: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    source_root: Path,
    progress_every: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []

    total = len(pairs)
    for pair_number, row in enumerate(pairs.itertuples(index=False), start=1):
        dataset_source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        month = str(row.month)
        parent_commit = str(row.scan_parent_commit)
        current_commit = str(row.scan_current_commit)
        commit_order = int(row.commit_order)
        repo_dir = resolve_repo_dir(
            row,
            treatment_clone_dir,
            control_clone_dir,
        )

        try:
            if not (repo_dir / ".git").exists():
                raise FileNotFoundError(f"Missing Git clone: {repo_dir}")
            if parent_commit != EMPTY_TREE_SHA and not valid_sha(parent_commit):
                raise ValueError(f"Invalid parent commit: {parent_commit}")
            if not valid_sha(current_commit):
                raise ValueError(f"Invalid current commit: {current_commit}")
            changed_paths = list_changed_paths(repo_dir, parent_commit, current_commit)
        except Exception as exc:
            error_rows.append(
                {
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "time": month,
                    "commit": current_commit,
                    "parent_commit": parent_commit,
                    "relative_path": "",
                    "stage": "commit_diff",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        python_change_seen = False
        for changed in changed_paths:
            current_path = changed.new_path
            parent_path = changed.old_path
            if not eligible_python_path(current_path):
                continue
            python_change_seen = True
            current_records: list[FunctionRecord] = []
            parent_records: list[FunctionRecord] = []
            file_status = "ok"
            error_message = ""

            try:
                current_source = decode_python_source(
                    git_blob(repo_dir, current_commit, current_path)
                )
                current_records = extract_functions(current_source)

                parent_is_python = eligible_python_path(parent_path)
                if parent_is_python and not changed.status.startswith("A"):
                    parent_source = decode_python_source(
                        git_blob(repo_dir, parent_commit, parent_path)
                    )
                    parent_records = extract_functions(parent_source)

                events, unchanged, deleted_ignored = compare_function_sets(
                    parent_records,
                    current_records,
                )
                added_count = 0
                modified_count = 0
                for current_record, parent_record, change_type in events:
                    event_id = deterministic_event_id(
                        dataset_source,
                        repo_name,
                        month,
                        current_commit,
                        current_path,
                        current_record.qualified_name,
                        current_record.occurrence_index,
                        change_type,
                    )
                    relative_source_path, source_hash, source_bytes = write_source_artifact(
                        source_root,
                        dataset_source,
                        repo_name,
                        month,
                        current_commit,
                        event_id,
                        current_record.source_text,
                    )
                    manifest_rows.append(
                        {
                            "function_event_id": event_id,
                            "dataset_source": dataset_source,
                            "repo_name": repo_name,
                            "time": month,
                            "commit": current_commit,
                            "parent_commit": parent_commit,
                            "commit_order": commit_order,
                            "relative_path": current_path,
                            "parent_relative_path": parent_path,
                            "diff_status": changed.status,
                            "qualified_function_name": current_record.qualified_name,
                            "function_name": current_record.function_name,
                            "function_kind": current_record.function_kind,
                            "occurrence_index": current_record.occurrence_index,
                            "change_type": change_type,
                            "start_line": current_record.start_line,
                            "end_line": current_record.end_line,
                            "parent_start_line": (
                                "" if parent_record is None else parent_record.start_line
                            ),
                            "parent_end_line": (
                                "" if parent_record is None else parent_record.end_line
                            ),
                            "structural_sha256": current_record.structural_sha256,
                            "parent_structural_sha256": (
                                ""
                                if parent_record is None
                                else parent_record.structural_sha256
                            ),
                            "function_source_relative_path": relative_source_path,
                            "content_sha256": source_hash,
                            "source_bytes": source_bytes,
                        }
                    )
                    added_count += int(change_type == "added")
                    modified_count += int(change_type == "modified")

                audit_rows.append(
                    {
                        "dataset_source": dataset_source,
                        "repo_name": repo_name,
                        "time": month,
                        "commit": current_commit,
                        "parent_commit": parent_commit,
                        "commit_order": commit_order,
                        "diff_status": changed.status,
                        "relative_path": current_path,
                        "parent_relative_path": parent_path,
                        "current_functions": len(current_records),
                        "parent_functions": len(parent_records),
                        "added_function_events": added_count,
                        "modified_function_events": modified_count,
                        "unchanged_functions": unchanged,
                        "deleted_functions_ignored": deleted_ignored,
                        "file_status": file_status,
                        "error_message": error_message,
                    }
                )
            except Exception as exc:
                file_status = "error"
                error_message = f"{type(exc).__name__}: {exc}"
                audit_rows.append(
                    {
                        "dataset_source": dataset_source,
                        "repo_name": repo_name,
                        "time": month,
                        "commit": current_commit,
                        "parent_commit": parent_commit,
                        "commit_order": commit_order,
                        "diff_status": changed.status,
                        "relative_path": current_path,
                        "parent_relative_path": parent_path,
                        "current_functions": len(current_records),
                        "parent_functions": len(parent_records),
                        "added_function_events": 0,
                        "modified_function_events": 0,
                        "unchanged_functions": 0,
                        "deleted_functions_ignored": 0,
                        "file_status": file_status,
                        "error_message": error_message,
                    }
                )
                error_rows.append(
                    {
                        "dataset_source": dataset_source,
                        "repo_name": repo_name,
                        "time": month,
                        "commit": current_commit,
                        "parent_commit": parent_commit,
                        "relative_path": current_path,
                        "stage": "python_function_extraction",
                        "error": error_message,
                    }
                )

        if not python_change_seen:
            audit_rows.append(
                {
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "time": month,
                    "commit": current_commit,
                    "parent_commit": parent_commit,
                    "commit_order": commit_order,
                    "diff_status": "",
                    "relative_path": "",
                    "parent_relative_path": "",
                    "current_functions": 0,
                    "parent_functions": 0,
                    "added_function_events": 0,
                    "modified_function_events": 0,
                    "unchanged_functions": 0,
                    "deleted_functions_ignored": 0,
                    "file_status": "no_python_changes",
                    "error_message": "",
                }
            )

        if progress_every > 0 and (
            pair_number % progress_every == 0 or pair_number == total
        ):
            print(
                f"Function-event extraction: {pair_number}/{total} commit pairs; "
                f"events={len(manifest_rows)} errors={len(error_rows)}",
                flush=True,
            )

    manifest = pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS)
    audit = pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS)
    errors = pd.DataFrame(error_rows, columns=ERROR_COLUMNS)
    return manifest, audit, errors


def build_repo_month_counts(
    pairs: pd.DataFrame,
    manifest: pd.DataFrame,
    audit: pd.DataFrame,
) -> pd.DataFrame:
    base = (
        pairs.groupby(["dataset_source", "repo_name", "month"], as_index=False)
        .agg(commits_scanned=("scan_current_commit", "nunique"))
        .rename(columns={"month": "time"})
    )

    python_commit_rows = audit.loc[
        audit["file_status"].ne("no_python_changes")
        & audit["relative_path"].astype(str).str.len().gt(0)
    ]
    python_commits = (
        python_commit_rows.groupby(
            ["dataset_source", "repo_name", "time"], as_index=False
        )
        .agg(commits_with_python_changes=("commit", "nunique"))
    )

    if manifest.empty:
        event_counts = pd.DataFrame(columns=REPO_MONTH_COLUMNS)
        output = base.copy()
        for column in REPO_MONTH_COLUMNS[4:]:
            output[column] = 0
        output["commits_with_python_changes"] = 0
        return output[REPO_MONTH_COLUMNS]

    event_counts = (
        manifest.groupby(["dataset_source", "repo_name", "time"], as_index=False)
        .agg(
            commits_with_function_change_events=("commit", "nunique"),
            function_change_events=("function_event_id", "size"),
            added_function_events=(
                "change_type",
                lambda values: int((values == "added").sum()),
            ),
            modified_function_events=(
                "change_type",
                lambda values: int((values == "modified").sum()),
            ),
            unique_changed_functions=(
                "qualified_function_name",
                "nunique",
            ),
            unique_changed_files=("relative_path", "nunique"),
        )
    )

    output = base.merge(
        python_commits,
        on=["dataset_source", "repo_name", "time"],
        how="left",
    ).merge(
        event_counts,
        on=["dataset_source", "repo_name", "time"],
        how="left",
    )
    numeric = [column for column in REPO_MONTH_COLUMNS if column not in {
        "dataset_source", "repo_name", "time"
    }]
    output[numeric] = output[numeric].fillna(0).astype(int)
    return output[REPO_MONTH_COLUMNS]


def build_checks(
    pairs: pd.DataFrame,
    manifest: pd.DataFrame,
    audit: pd.DataFrame,
    errors: pd.DataFrame,
    source_root: Path,
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(section: str, check: str, passed: bool, value: Any) -> None:
        checks.append(
            {
                "section": section,
                "check": check,
                "passed": int(bool(passed)),
                "value": value,
            }
        )

    duplicate_event_ids = int(manifest["function_event_id"].duplicated().sum())
    add("manifest", "function_event_ids_unique", duplicate_event_ids == 0, duplicate_event_ids)
    invalid_change_types = int(
        (~manifest["change_type"].isin(["added", "modified"])).sum()
    )
    add("manifest", "change_types_valid", invalid_change_types == 0, invalid_change_types)
    invalid_kinds = int(
        (~manifest["function_kind"].isin([
            "module_function",
            "module_async_function",
            "method",
            "async_method",
            "nested_function",
            "nested_async_function",
        ])).sum()
    )
    add("manifest", "function_kinds_valid", invalid_kinds == 0, invalid_kinds)

    missing_sources = 0
    hash_mismatches = 0
    for row in manifest.itertuples(index=False):
        path = source_root / str(row.function_source_relative_path)
        if not path.is_file():
            missing_sources += 1
            continue
        if content_sha(path.read_bytes()) != str(row.content_sha256):
            hash_mismatches += 1
    add("sources", "all_source_artifacts_present", missing_sources == 0, missing_sources)
    add("sources", "source_hashes_match_manifest", hash_mismatches == 0, hash_mismatches)

    arithmetic_errors = int(
        (
            audit["added_function_events"]
            + audit["modified_function_events"]
            < 0
        ).sum()
    )
    add("arithmetic", "event_counts_nonnegative", arithmetic_errors == 0, arithmetic_errors)
    manifest_from_audit = int(
        audit["added_function_events"].sum()
        + audit["modified_function_events"].sum()
    )
    add(
        "arithmetic",
        "audit_event_count_matches_manifest",
        manifest_from_audit == len(manifest),
        f"{manifest_from_audit}:{len(manifest)}",
    )
    add("processing", "extraction_errors_zero", len(errors) == 0, len(errors))
    add(
        "coverage",
        "all_input_pairs_audited",
        audit["commit"].nunique() <= len(pairs),
        f"{audit['commit'].nunique()}:{len(pairs)}",
    )
    return pd.DataFrame(checks)


def build_summary(
    pairs: pd.DataFrame,
    manifest: pd.DataFrame,
    audit: pd.DataFrame,
    errors: pd.DataFrame,
    repo_month_counts: pd.DataFrame,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "status": "PASS" if checks["passed"].eq(1).all() else "FAIL",
        "checks_total": int(len(checks)),
        "checks_passed": int(checks["passed"].eq(1).sum()),
        "checks_failed": int(checks["passed"].ne(1).sum()),
        "commit_pairs_scanned": int(len(pairs)),
        "repository_months": int(len(repo_month_counts)),
        "python_files_audited": int(
            audit["relative_path"].astype(str).str.len().gt(0).sum()
        ),
        "function_change_events": int(len(manifest)),
        "added_function_events": int(
            manifest["change_type"].eq("added").sum()
        ),
        "modified_function_events": int(
            manifest["change_type"].eq("modified").sum()
        ),
        "module_function_events": int(
            manifest["function_kind"].isin(
                ["module_function", "module_async_function"]
            ).sum()
        ),
        "method_events": int(
            manifest["function_kind"].isin(["method", "async_method"]).sum()
        ),
        "nested_function_events": int(
            manifest["function_kind"].isin(
                ["nested_function", "nested_async_function"]
            ).sum()
        ),
        "extraction_errors": int(len(errors)),
        "primary_event_definition": (
            "One structurally added or modified named Python function in one "
            "commit; repeated edits and later reverts remain separate events."
        ),
        "downstream_outcomes": {
            "velocity_like_count": "agc_function_change_events",
            "composition_ratio": "agc_function_change_event_ratio",
        },
    }


def self_test() -> None:
    source = textwrap.dedent(
        """
        def f1():
            return 1

        class C:
            def m1(self):
                def inner():
                    return 2
                return inner()
        """
    )
    functions = extract_functions(source)
    names = [record.qualified_name for record in functions]
    if names != ["f1", "C.m1", "C.m1.inner"]:
        raise AssertionError(f"All-function extraction mismatch: {names}")

    with tempfile.TemporaryDirectory(prefix="agc-function-events-") as temp_dir:
        root = Path(temp_dir)
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test User"],
            check=True,
        )

        (repo / "a.py").write_text(
            "def f1():\n    return 0\n\ndef f2():\n    return 0\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repo), "add", "a.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
        base = require_git_bytes(
            run_git_bytes(repo, ["rev-parse", "HEAD"]),
            "rev-parse",
        ).decode().strip()

        commits: list[str] = []
        contents = [
            "def f1():\n    return 'X'\n\ndef f2():\n    return 0\n",
            "def f1():\n    return 'X'\n\ndef f2():\n    return 'Y'\n",
            "def f1():\n    return 0\n\ndef f2():\n    return 'Y'\n",
        ]
        for index, content in enumerate(contents, start=1):
            (repo / "a.py").write_text(content, encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "a.py"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-q", "-m", f"c{index}"],
                check=True,
            )
            commits.append(
                require_git_bytes(
                    run_git_bytes(repo, ["rev-parse", "HEAD"]),
                    "rev-parse",
                ).decode().strip()
            )

        pair_rows = []
        parents = [base, commits[0], commits[1]]
        for order, (parent, current) in enumerate(zip(parents, commits), start=1):
            pair_rows.append(
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "month": "2024-01",
                    "scan_parent_commit": parent,
                    "scan_current_commit": current,
                    "commit_order": order,
                    "primary_scan_eligible": 1,
                    "repo_dir": str(repo),
                }
            )
        pairs = pd.DataFrame(pair_rows)
        source_root = root / "sources"
        manifest, audit, errors = extract_events(
            pairs,
            root,
            root,
            source_root,
            progress_every=0,
        )
        if len(errors) != 0:
            raise AssertionError(errors.to_dict("records"))
        event_keys = list(zip(manifest["commit_order"], manifest["qualified_function_name"]))
        if event_keys != [(1, "f1"), (2, "f2"), (3, "f1")]:
            raise AssertionError(f"Repeated/reverted event mismatch: {event_keys}")
        if len(manifest) != 3:
            raise AssertionError("Expected three commit-function events")
        if audit["modified_function_events"].sum() != 3:
            raise AssertionError("Expected three modified-function events")
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    input_pairs = args.input_commit_pairs.expanduser().resolve()
    treatment_clone_dir = args.treatment_clone_dir.expanduser().resolve()
    control_clone_dir = args.control_clone_dir.expanduser().resolve()
    output_manifest = args.output_manifest.expanduser().resolve()
    source_root = args.function_source_root.expanduser().resolve()
    qc_dir = args.qc_dir.expanduser().resolve()

    if not input_pairs.is_file():
        raise FileNotFoundError(f"Missing commit-pair input: {input_pairs}")
    for path, label in [
        (treatment_clone_dir, "treatment clone directory"),
        (control_clone_dir, "control clone directory"),
    ]:
        if not path.is_dir():
            raise FileNotFoundError(f"Missing {label}: {path}")

    if source_root.exists() and args.overwrite_source_root:
        shutil.rmtree(source_root)
    source_root.mkdir(parents=True, exist_ok=True)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    pairs = load_pairs(input_pairs)
    if args.max_pairs > 0:
        pairs = pairs.head(args.max_pairs).copy()

    print("=" * 72)
    print("Extract commit-function change events")
    print(f"Input commit pairs:    {input_pairs}")
    print(f"Eligible pairs:        {len(pairs)}")
    print(f"Treatment clones:      {treatment_clone_dir}")
    print(f"Control clones:        {control_clone_dir}")
    print(f"Output manifest:       {output_manifest}")
    print(f"Function source root:  {source_root}")
    print(f"QC directory:          {qc_dir}")
    print("=" * 72)

    manifest, audit, errors = extract_events(
        pairs,
        treatment_clone_dir,
        control_clone_dir,
        source_root,
        args.progress_every,
    )
    repo_month_counts = build_repo_month_counts(pairs, manifest, audit)
    checks = build_checks(pairs, manifest, audit, errors, source_root)
    summary = build_summary(
        pairs,
        manifest,
        audit,
        errors,
        repo_month_counts,
        checks,
    )

    audit_path = output_manifest.parent / "commit_function_event_extraction_audit.csv"
    repo_month_path = output_manifest.parent / "repo_month_function_event_counts.csv"
    checks_path = qc_dir / "agc_commit_function_event_extract_checks.csv"
    errors_path = qc_dir / "agc_commit_function_event_extract_errors.csv"
    summary_path = qc_dir / "agc_commit_function_event_extract_summary.json"

    atomic_csv(manifest, output_manifest)
    atomic_csv(audit, audit_path)
    atomic_csv(repo_month_counts, repo_month_path)
    atomic_csv(checks, checks_path)
    atomic_csv(errors, errors_path)
    atomic_json(summary, summary_path)

    print("=" * 72)
    print("AGC commit-function event extraction")
    print(f"Status:                     {summary['status']}")
    print(f"Checks passed:              {summary['checks_passed']}/{summary['checks_total']}")
    print(f"Commit pairs scanned:       {summary['commit_pairs_scanned']}")
    print(f"Function-change events:     {summary['function_change_events']}")
    print(f"Added function events:      {summary['added_function_events']}")
    print(f"Modified function events:   {summary['modified_function_events']}")
    print(f"Method events:              {summary['method_events']}")
    print(f"Nested function events:     {summary['nested_function_events']}")
    print(f"Extraction errors:          {summary['extraction_errors']}")
    print(f"Detection manifest:         {output_manifest}")
    print(f"Function source root:       {source_root}")
    print(f"Repository-month counts:    {repo_month_path}")
    print(f"Audit:                       {audit_path}")
    print(f"Summary:                     {summary_path}")
    print("=" * 72)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
