#!/usr/bin/env python3
"""Resolve run-x-d01 parsing and function-boundary issues.

This self-contained run-x-d01a implementation reviews the final file-level
issues produced by run-x-d01 and reconstructs missing raw function bodies
without overwriting the original run-x-d01 outputs.

The resolver uses three evidence levels:

1. ``python312_ast_exact``
   The original source parses under the configured Python 3.12 interpreter.
   Function identity comes from AST and header/body boundaries are computed in
   the same Python 3.12 worker with one tokenization pass per file.
2. ``python312_token_fallback_complete``
   The original source does not parse as Python 3.12, but Python tokenization
   completes and all named function declarations are indexed directly from the
   original source. This handles templates and Python 2 grammar while keeping
   token counts on the unmodified historical source.
3. ``counterfactual_ast_repair``
   A line-count-preserving diagnostic repair makes AST parsing possible. These
   values are reported separately and are not applied unless explicitly
   enabled by ``--apply-counterfactual``.

Nested functions are not separate metric occurrences; their source remains in
outer raw bodies. Extracted raw bodies are saved in the existing body store.
Each tracked path and function occurrence remains distinct.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

WORKER_MODE = any(arg in {"--resolver-worker", "--resolver-worker-version"} for arg in sys.argv[1:])
if not WORKER_MODE:
    import pandas as pd

IMPLEMENTATION_VERSION = "v1"
EXPERIMENT_NAME = "run-x-d01a-resolve-token-py-parsing-errors"
WORKER_PROTOCOL_VERSION = "v1"
TOKEN_MIN = 100
TOKEN_MAX = 200
TOKEN_DEFINITION = "len(raw_implementation_body.split(' '))"
BODY_OUTPUT_ENCODING = "utf-8"
APPLIED_METHODS = {
    "python312_ast_exact",
    "python312_token_fallback_complete",
    "no_function_confirmed",
}

ISSUE_KEY_COLUMNS = ["snapshot_key", "path", "blob_oid"]
FUNCTION_MATCH_COLUMNS = [
    "qualified_name",
    "occurrence_index",
    "function_start_line",
]

BLOB_REVIEW_COLUMNS = [
    "blob_oid",
    "representative_repo_name",
    "representative_path",
    "issue_stages",
    "issue_types",
    "issue_occurrences",
    "affected_snapshots",
    "affected_paths",
    "source_byte_count",
    "source_encoding",
    "python312_ast_status",
    "python312_ast_error_type",
    "python312_ast_error_message",
    "tokenizer_complete",
    "tokenizer_error_type",
    "tokenizer_error_message",
    "regex_named_function_candidates",
    "indexed_named_function_headers",
    "eligible_function_count",
    "extractable_function_count",
    "docstring_only_function_count",
    "qualifying_function_count",
    "token_py_all_function_bodies",
    "token_py_100_200",
    "recovery_method",
    "root_cause",
    "python2_validation_status",
    "counterfactual_repair_applied",
    "counterfactual_repair_description",
    "resolution_status",
    "auto_applied",
    "requires_review",
    "notes",
]

RECOVERED_DETAIL_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "blob_size",
    "original_issue_stage",
    "recovery_method",
    "recovery_confidence",
    "counterfactual_repair",
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

FILE_RESOLUTION_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "blob_size",
    "original_issue_stage",
    "original_issue_row_count",
    "original_boundary_failed_function_count",
    "recovery_method",
    "root_cause",
    "recovered_function_count_all_delta",
    "recovered_function_count_extracted_delta",
    "recovered_function_count_100_200_delta",
    "recovered_function_count_docstring_only_delta",
    "recovered_function_count_with_nested_delta",
    "recovered_python_file_with_function_delta",
    "recovered_python_file_with_function_100_200_delta",
    "recovered_token_py_all_delta",
    "recovered_token_py_100_200_delta",
    "resolved_boundary_failure_count",
    "unresolved_boundary_failure_count",
    "metric_impact_resolved",
    "counterfactual_repair",
    "auto_applied",
    "resolution_status",
    "resolution_note",
]

SNAPSHOT_CORRECTION_COLUMNS = [
    "manifest_order",
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "repo_month_rows",
    "original_snapshot_status",
    "original_metric_available",
    "original_failed_python_file_count",
    "original_boundary_failure_count",
    "affected_file_occurrences",
    "resolved_file_occurrences",
    "unresolved_file_occurrences",
    "counterfactual_file_occurrences",
    "function_count_py_all_delta",
    "function_count_py_extracted_delta",
    "function_count_py_100_200_delta",
    "function_count_py_docstring_only_delta",
    "function_count_py_with_nested_delta",
    "python_file_count_with_function_delta",
    "python_file_count_with_function_100_200_delta",
    "token_py_all_function_bodies_delta",
    "token_py_100_200_delta",
    "corrected_function_count_py_all",
    "corrected_function_count_py_extracted",
    "corrected_function_count_py_100_200",
    "corrected_function_count_py_docstring_only",
    "corrected_function_count_py_with_nested",
    "corrected_python_file_count_with_function",
    "corrected_python_file_count_with_function_100_200",
    "corrected_token_py_all_function_bodies",
    "corrected_token_py_100_200",
    "metric_available_after_d01a",
    "resolution_status",
    "resolution_note",
]

UNRESOLVED_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "original_issue_stage",
    "recovery_method",
    "root_cause",
    "resolution_status",
    "resolution_note",
]

QC_COLUMNS = ["check_name", "status", "observed", "expected", "note"]
SUMMARY_COLUMNS = ["section", "metric", "value", "note"]


@dataclass(frozen=True)
class AstFunction:
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


@dataclass
class LexicalSpan:
    kind: str
    name: str
    async_function: bool
    start_line: int
    start_col: int
    start_offset: int
    colon_index: int
    block_suite: bool
    suite_start_offset: int
    suite_token_start_index: int
    suite_token_end_index: int
    end_line: int
    end_offset: int
    complete: bool


@dataclass(frozen=True)
class WorkerFunction:
    qualified_name: str
    function_name: str
    function_kind: str
    occurrence_index: int
    function_start_line: int
    function_end_line: int
    function_start_offset: int
    function_end_offset: int
    body_start_line: int
    body_end_line: int
    body_start_offset: int
    leading_docstring_removed: bool
    contains_nested_named_definition: bool
    extraction_status: str
    exclusion_reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if not WORKER_MODE and pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitize_key(value: str, max_length: int = 120) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    cleaned = cleaned.strip("_.:-") or "unknown"
    return cleaned[:max_length]


def count_physical_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines()) or 1


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


def token_offset(token_info: tokenize.TokenInfo, line_starts: Sequence[int]) -> int:
    line_number, char_col = token_info.start
    return line_starts[line_number - 1] + char_col


def token_end_offset(token_info: tokenize.TokenInfo, line_starts: Sequence[int]) -> int:
    line_number, char_col = token_info.end
    return line_starts[line_number - 1] + char_col


def utf8_byte_col_to_char_col(line: str, byte_col: int) -> int:
    payload = line.encode("utf-8")
    if byte_col < 0 or byte_col > len(payload):
        raise ValueError(f"Invalid UTF-8 byte column {byte_col}")
    return len(payload[:byte_col].decode("utf-8"))


def ast_position_offset(
    lines: Sequence[str], line_starts: Sequence[int], lineno: int, byte_col: int
) -> int:
    return line_starts[lineno - 1] + utf8_byte_col_to_char_col(lines[lineno - 1], byte_col)


def is_docstring_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(getattr(statement, "value", None), ast.Constant)
        and isinstance(statement.value.value, str)
    )


def statement_child_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    for field_name in (
        "body",
        "orelse",
        "finalbody",
    ):
        value = getattr(statement, field_name, None)
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
            bodies.append(value)
    handlers = getattr(statement, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            body = getattr(handler, "body", None)
            if isinstance(body, list):
                bodies.append(body)
    cases = getattr(statement, "cases", None)
    if isinstance(cases, list):
        for case in cases:
            body = getattr(case, "body", None)
            if isinstance(body, list):
                bodies.append(body)
    return bodies


def contains_nested_named_definition(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return True
    return False


def function_kind(node: ast.AST, scope_kinds: Sequence[str]) -> str:
    is_async = isinstance(node, ast.AsyncFunctionDef)
    in_class = bool(scope_kinds and scope_kinds[-1] == "class")
    if in_class and is_async:
        return "async_method"
    if in_class:
        return "method"
    if is_async:
        return "async_function"
    return "function"


def index_ast_functions(source: str, filename: str) -> list[AstFunction]:
    tree = ast.parse(source, filename=filename, type_comments=True)
    occurrence_counts: Counter[str] = Counter()
    records: list[AstFunction] = []

    def walk(statements: Sequence[ast.stmt], names: list[str], kinds: list[str]) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nested = "function" in kinds
                qualified_name = ".".join([*names, statement.name])
                occurrence_counts[qualified_name] += 1
                if not nested:
                    has_docstring = bool(statement.body and is_docstring_statement(statement.body[0]))
                    real_body = statement.body[1:] if has_docstring else statement.body
                    first_statement = real_body[0] if real_body else None
                    doc_end = 0
                    if has_docstring:
                        doc_end = int(getattr(statement.body[0], "end_lineno", statement.body[0].lineno))
                    records.append(
                        AstFunction(
                            qualified_name=qualified_name,
                            function_name=statement.name,
                            function_kind=function_kind(statement, kinds),
                            occurrence_index=occurrence_counts[qualified_name],
                            start_line=int(statement.lineno),
                            start_col=int(statement.col_offset),
                            end_line=int(getattr(statement, "end_lineno", statement.lineno)),
                            end_col=int(getattr(statement, "end_col_offset", statement.col_offset)),
                            first_statement_line=int(first_statement.lineno) if first_statement else 0,
                            first_statement_col=int(first_statement.col_offset) if first_statement else 0,
                            leading_docstring_removed=has_docstring,
                            docstring_end_line=doc_end,
                            contains_nested_named_definition=contains_nested_named_definition(statement),
                        )
                    )
                walk(statement.body, [*names, statement.name], [*kinds, "function"])
            elif isinstance(statement, ast.ClassDef):
                walk(statement.body, [*names, statement.name], [*kinds, "class"])
            else:
                for body in statement_child_bodies(statement):
                    walk(body, names, kinds)

    walk(tree.body, [], [])
    return records


def collect_tokens(source: str) -> tuple[list[tokenize.TokenInfo], bool, str, str]:
    tokens: list[tokenize.TokenInfo] = []
    complete = True
    error_type = ""
    error_message = ""
    generator = tokenize.generate_tokens(io.StringIO(source).readline)
    try:
        for token_info in generator:
            tokens.append(token_info)
    except Exception as exc:
        complete = False
        error_type = type(exc).__name__
        error_message = str(exc)
    return tokens, complete, error_type, error_message


def next_significant(tokens: Sequence[tokenize.TokenInfo], index: int) -> Optional[int]:
    ignored = {
        tokenize.NL,
        tokenize.COMMENT,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
    }
    for position in range(index, len(tokens)):
        if tokens[position].type not in ignored:
            return position
    return None


def find_header_colon(tokens: Sequence[tokenize.TokenInfo], start_index: int) -> Optional[int]:
    depth = 0
    for index in range(start_index, len(tokens)):
        token_info = tokens[index]
        if token_info.type == tokenize.NEWLINE and depth == 0:
            return None
        if token_info.type != tokenize.OP:
            continue
        if token_info.string in "([{":
            depth += 1
        elif token_info.string in ")]}":
            depth = max(depth - 1, 0)
        elif token_info.string == ":" and depth == 0:
            return index
    return None


def build_lexical_spans(
    source: str, tokens: Sequence[tokenize.TokenInfo]
) -> tuple[list[LexicalSpan], list[LexicalSpan]]:
    lines, line_starts, line_ends = build_line_offsets(source)
    functions: list[LexicalSpan] = []
    classes: list[LexicalSpan] = []
    index = 0
    while index < len(tokens):
        token_info = tokens[index]
        async_function = False
        keyword_index: Optional[int] = None
        kind = ""
        start_token = token_info
        if token_info.type == tokenize.NAME and token_info.string == "async":
            following = next_significant(tokens, index + 1)
            if following is not None and tokens[following].type == tokenize.NAME and tokens[following].string == "def":
                async_function = True
                keyword_index = following
                kind = "function"
                start_token = token_info
        elif token_info.type == tokenize.NAME and token_info.string == "def":
            keyword_index = index
            kind = "function"
        elif token_info.type == tokenize.NAME and token_info.string == "class":
            keyword_index = index
            kind = "class"

        if keyword_index is None:
            index += 1
            continue

        name_index = next_significant(tokens, keyword_index + 1)
        if name_index is None or tokens[name_index].type != tokenize.NAME:
            index += 1
            continue
        name = tokens[name_index].string
        colon_index = find_header_colon(tokens, name_index + 1)
        if colon_index is None:
            index += 1
            continue

        after_colon = next_significant(tokens, colon_index + 1)
        if after_colon is None:
            index += 1
            continue
        block_suite = tokens[after_colon].type == tokenize.NEWLINE
        suite_start_offset = 0
        suite_token_start = after_colon
        suite_token_end = after_colon
        end_line = 0
        end_offset = 0
        complete = True

        if block_suite:
            newline_token = tokens[after_colon]
            header_line = newline_token.end[0]
            suite_start_offset = line_starts[header_line] if header_line < len(line_starts) else line_ends[header_line - 1]
            indent_index: Optional[int] = None
            for position in range(after_colon + 1, len(tokens)):
                if tokens[position].type == tokenize.INDENT:
                    indent_index = position
                    break
                if tokens[position].type not in {tokenize.NL, tokenize.COMMENT, tokenize.NEWLINE}:
                    break
            if indent_index is None:
                complete = False
                suite_token_start = after_colon + 1
                suite_token_end = after_colon + 1
            else:
                suite_token_start = indent_index + 1
                depth = 1
                last_newline: Optional[tokenize.TokenInfo] = None
                closing_index: Optional[int] = None
                for position in range(indent_index + 1, len(tokens)):
                    current = tokens[position]
                    if current.type == tokenize.INDENT:
                        depth += 1
                    elif current.type == tokenize.DEDENT:
                        depth -= 1
                        if depth == 0:
                            closing_index = position
                            break
                    elif current.type == tokenize.NEWLINE and depth >= 1:
                        last_newline = current
                if closing_index is None or last_newline is None:
                    complete = False
                    suite_token_end = len(tokens)
                else:
                    suite_token_end = closing_index
                    end_line = int(last_newline.end[0])
                    end_offset = line_ends[end_line - 1]
        else:
            first_body_index = after_colon
            suite_token_start = first_body_index
            suite_start_offset = token_offset(tokens[first_body_index], line_starts)
            newline_index: Optional[int] = None
            for position in range(first_body_index, len(tokens)):
                if tokens[position].type == tokenize.NEWLINE:
                    newline_index = position
                    break
            if newline_index is None:
                complete = False
                suite_token_end = len(tokens)
            else:
                suite_token_end = newline_index
                end_line = int(tokens[newline_index].end[0])
                end_offset = line_ends[end_line - 1]

        span = LexicalSpan(
            kind=kind,
            name=name,
            async_function=async_function,
            start_line=int(start_token.start[0]),
            start_col=int(start_token.start[1]),
            start_offset=line_starts[start_token.start[0] - 1],
            colon_index=colon_index,
            block_suite=block_suite,
            suite_start_offset=suite_start_offset,
            suite_token_start_index=suite_token_start,
            suite_token_end_index=suite_token_end,
            end_line=end_line,
            end_offset=end_offset,
            complete=complete,
        )
        if kind == "function":
            functions.append(span)
        else:
            classes.append(span)
        index = max(index + 1, colon_index + 1)

    return functions, classes


def lexical_docstring_boundary(
    tokens: Sequence[tokenize.TokenInfo], span: LexicalSpan, line_ends: Sequence[int], line_starts: Sequence[int]
) -> tuple[bool, int, bool, str]:
    ignored = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT}
    first_index: Optional[int] = None
    for index in range(span.suite_token_start_index, min(span.suite_token_end_index, len(tokens))):
        if tokens[index].type not in ignored:
            first_index = index
            break
    if first_index is None:
        return False, span.suite_start_offset, True, "empty_body"
    if tokens[first_index].type != tokenize.STRING:
        return False, span.suite_start_offset, False, ""

    last_string = tokens[first_index]
    terminator_index: Optional[int] = None
    only_strings = True
    index = first_index + 1
    while index < min(span.suite_token_end_index, len(tokens)):
        current = tokens[index]
        if current.type == tokenize.STRING:
            last_string = current
        elif current.type in {tokenize.NL, tokenize.COMMENT}:
            pass
        elif current.type == tokenize.OP and current.string in {"(", ")"}:
            pass
        elif current.type == tokenize.OP and current.string == ";":
            terminator_index = index
            break
        elif current.type == tokenize.NEWLINE:
            terminator_index = index
            break
        else:
            only_strings = False
            break
        index += 1
    if not only_strings or terminator_index is None:
        return False, span.suite_start_offset, False, ""

    next_index: Optional[int] = None
    for position in range(terminator_index + 1, min(span.suite_token_end_index, len(tokens))):
        current = tokens[position]
        if current.type not in ignored and not (current.type == tokenize.OP and current.string == ";"):
            next_index = position
            break
    if next_index is None:
        return True, 0, True, "docstring_only"

    doc_end_line = int(last_string.end[0])
    next_token = tokens[next_index]
    if next_token.start[0] == doc_end_line:
        body_start = token_offset(next_token, line_starts)
    else:
        body_start = line_ends[doc_end_line - 1]
    return True, body_start, False, ""


def lexical_records(
    source: str,
    tokens: Sequence[tokenize.TokenInfo],
    functions: Sequence[LexicalSpan],
    classes: Sequence[LexicalSpan],
) -> tuple[list[WorkerFunction], int]:
    lines, line_starts, line_ends = build_line_offsets(source)
    complete_functions = [span for span in functions if span.complete]
    complete_classes = [span for span in classes if span.complete]
    records: list[WorkerFunction] = []
    occurrence_counts: Counter[str] = Counter()

    for span in sorted(complete_functions, key=lambda item: (item.start_offset, item.end_offset)):
        containing_functions = [
            other
            for other in complete_functions
            if other.start_offset < span.start_offset < other.end_offset
        ]
        if containing_functions:
            continue
        containing_classes = [
            item
            for item in complete_classes
            if item.start_offset < span.start_offset < item.end_offset
        ]
        containing_classes.sort(key=lambda item: item.start_offset)
        class_names = [item.name for item in containing_classes]
        qualified_name = ".".join([*class_names, span.name])
        occurrence_counts[qualified_name] += 1
        has_docstring, body_start, no_body, reason = lexical_docstring_boundary(
            tokens, span, line_ends, line_starts
        )
        if no_body:
            body_start_line = 0
            extraction_status = "no_body_after_docstring" if reason == "docstring_only" else "boundary_failed"
        else:
            body_start_line = source.count("\n", 0, body_start) + 1
            extraction_status = "success"
        contains_nested = any(
            other.start_offset > span.start_offset and other.start_offset < span.end_offset
            for other in [*complete_functions, *complete_classes]
        )
        if containing_classes:
            function_kind_value = "async_method" if span.async_function else "method"
        else:
            function_kind_value = "async_function" if span.async_function else "function"
        records.append(
            WorkerFunction(
                qualified_name=qualified_name,
                function_name=span.name,
                function_kind=function_kind_value,
                occurrence_index=occurrence_counts[qualified_name],
                function_start_line=span.start_line,
                function_end_line=span.end_line,
                function_start_offset=span.start_offset,
                function_end_offset=span.end_offset,
                body_start_line=body_start_line,
                body_end_line=span.end_line,
                body_start_offset=body_start,
                leading_docstring_removed=has_docstring,
                contains_nested_named_definition=contains_nested,
                extraction_status=extraction_status,
                exclusion_reason=reason,
            )
        )
    return records, len(functions)


def ast_exact_records(
    source: str,
    ast_functions: Sequence[AstFunction],
    lexical_functions: Sequence[LexicalSpan],
) -> list[WorkerFunction]:
    lines, line_starts, line_ends = build_line_offsets(source)
    output: list[WorkerFunction] = []
    used: set[int] = set()
    for record in ast_functions:
        match_index: Optional[int] = None
        for index, span in enumerate(lexical_functions):
            if index in used or not span.complete:
                continue
            if span.name == record.function_name and span.start_line == record.start_line:
                match_index = index
                break
        if match_index is None:
            raise ValueError(
                f"Could not match AST function to lexical header: {record.qualified_name}@{record.start_line}"
            )
        used.add(match_index)
        span = lexical_functions[match_index]
        if record.first_statement_line <= 0:
            output.append(
                WorkerFunction(
                    qualified_name=record.qualified_name,
                    function_name=record.function_name,
                    function_kind=record.function_kind,
                    occurrence_index=record.occurrence_index,
                    function_start_line=record.start_line,
                    function_end_line=record.end_line,
                    function_start_offset=line_starts[record.start_line - 1],
                    function_end_offset=line_ends[record.end_line - 1],
                    body_start_line=0,
                    body_end_line=record.end_line,
                    body_start_offset=0,
                    leading_docstring_removed=record.leading_docstring_removed,
                    contains_nested_named_definition=record.contains_nested_named_definition,
                    extraction_status="no_body_after_docstring",
                    exclusion_reason="docstring_only_after_leading_docstring_removal",
                )
            )
            continue
        if record.leading_docstring_removed:
            if record.first_statement_line == record.docstring_end_line:
                body_start = ast_position_offset(
                    lines, line_starts, record.first_statement_line, record.first_statement_col
                )
            else:
                body_start = line_ends[record.docstring_end_line - 1]
        else:
            body_start = span.suite_start_offset
            if not span.block_suite:
                body_start = ast_position_offset(
                    lines, line_starts, record.first_statement_line, record.first_statement_col
                )
        function_end = line_ends[record.end_line - 1]
        if not (line_starts[record.start_line - 1] <= body_start < function_end <= len(source)):
            raise ValueError(f"Invalid exact boundaries for {record.qualified_name}")
        output.append(
            WorkerFunction(
                qualified_name=record.qualified_name,
                function_name=record.function_name,
                function_kind=record.function_kind,
                occurrence_index=record.occurrence_index,
                function_start_line=record.start_line,
                function_end_line=record.end_line,
                function_start_offset=line_starts[record.start_line - 1],
                function_end_offset=function_end,
                body_start_line=source.count("\n", 0, body_start) + 1,
                body_end_line=record.end_line,
                body_start_offset=body_start,
                leading_docstring_removed=record.leading_docstring_removed,
                contains_nested_named_definition=record.contains_nested_named_definition,
                extraction_status="success",
                exclusion_reason="",
            )
        )
    return output


def serialize_worker_record(record: WorkerFunction) -> dict[str, Any]:
    return {name: getattr(record, name) for name in WorkerFunction.__dataclass_fields__}


def regex_named_function_lines(source: str) -> list[int]:
    pattern = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+[A-Za-z_][A-Za-z0-9_]*[ \t]*\(", re.MULTILINE)
    return [source.count("\n", 0, match.start()) + 1 for match in pattern.finditer(source)]


def repair_source_preserving_layout(source: str) -> tuple[str, list[str]]:
    repaired = source
    descriptions: list[str] = []
    placeholder_pattern = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
    if placeholder_pattern.search(repaired):
        repaired = placeholder_pattern.sub(lambda match: "x" * len(match.group(0)), repaired)
        descriptions.append("replace_template_placeholders_with_equal_length_identifiers")
    if repaired.startswith("LPimport "):
        repaired = "##" + repaired[2:]
        descriptions.append("comment_out_LP_prefix_typo_with_equal_length_marker")
    if len(repaired) != len(source) or repaired.count("\n") != source.count("\n"):
        raise ValueError("Diagnostic repair did not preserve source layout")
    return repaired, descriptions


def worker_analyze_file(source: str, path: str) -> dict[str, Any]:
    regex_lines = regex_named_function_lines(source)
    tokens, tokenizer_complete, token_error_type, token_error_message = collect_tokens(source)
    lexical_functions, lexical_classes = build_lexical_spans(source, tokens)
    ast_status = "success"
    ast_error_type = ""
    ast_error_message = ""
    method = ""
    records: list[WorkerFunction] = []
    repair_description = ""
    counterfactual = False

    try:
        ast_functions = index_ast_functions(source, path)
        records = ast_exact_records(source, ast_functions, lexical_functions)
        method = "python312_ast_exact"
    except Exception as exc:
        ast_status = "error"
        ast_error_type = type(exc).__name__
        ast_error_message = str(exc)
        lexical, indexed_headers = lexical_records(source, tokens, lexical_functions, lexical_classes)
        all_headers_complete = tokenizer_complete and indexed_headers == len(regex_lines)
        if not regex_lines:
            records = []
            method = "no_function_confirmed"
        elif all_headers_complete:
            records = lexical
            method = "python312_token_fallback_complete"
        else:
            repaired, descriptions = repair_source_preserving_layout(source)
            if descriptions:
                try:
                    repaired_tokens, repaired_complete, _, _ = collect_tokens(repaired)
                    repaired_functions, _ = build_lexical_spans(repaired, repaired_tokens)
                    repaired_ast = index_ast_functions(repaired, path)
                    if repaired_complete:
                        records = ast_exact_records(repaired, repaired_ast, repaired_functions)
                        method = "counterfactual_ast_repair"
                        repair_description = " | ".join(descriptions)
                        counterfactual = True
                    else:
                        method = "unresolved"
                except Exception:
                    method = "unresolved"
            else:
                method = "unresolved"

    return {
        "path": path,
        "python312_ast_status": ast_status,
        "python312_ast_error_type": ast_error_type,
        "python312_ast_error_message": ast_error_message,
        "tokenizer_complete": tokenizer_complete,
        "tokenizer_error_type": token_error_type,
        "tokenizer_error_message": token_error_message,
        "regex_named_function_candidates": len(regex_lines),
        "indexed_named_function_headers": len(lexical_functions),
        "recovery_method": method,
        "counterfactual_repair_applied": counterfactual,
        "counterfactual_repair_description": repair_description,
        "records": [serialize_worker_record(record) for record in records],
    }


def worker_version_payload() -> dict[str, Any]:
    return {
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "python_version": sys.version.split()[0],
        "python_version_info": list(sys.version_info[:3]),
    }


def run_worker_cli() -> int:
    request = json.load(sys.stdin)
    if request.get("protocol_version") != WORKER_PROTOCOL_VERSION:
        raise ValueError("Resolver worker protocol mismatch")
    output: list[dict[str, Any]] = []
    for item in request.get("files", []):
        request_index = int(item["request_index"])
        path = str(item["path"])
        try:
            source = base64.b64decode(item["source_utf8_b64"]).decode("utf-8")
            analysis = worker_analyze_file(source, path)
            output.append({"request_index": request_index, "status": "success", **analysis})
        except Exception as exc:
            output.append(
                {
                    "request_index": request_index,
                    "path": path,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "records": [],
                }
            )
    json.dump({**worker_version_payload(), "files": output}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def inspect_ast_python(ast_python_bin: str, script_path: Path, timeout_seconds: int) -> dict[str, Any]:
    process = subprocess.run(
        [ast_python_bin, str(script_path), "--resolver-worker-version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    payload = json.loads(process.stdout)
    if tuple(payload["python_version_info"][:2]) < (3, 12):
        raise RuntimeError(f"AST_PYTHON_BIN must be Python 3.12+: {payload['python_version']}")
    return payload


def run_worker_batch(
    entries: list[dict[str, Any]],
    ast_python_bin: str,
    script_path: Path,
    timeout_seconds: int,
) -> dict[int, dict[str, Any]]:
    request = {
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "files": [
            {
                "request_index": int(entry["request_index"]),
                "path": str(entry["path"]),
                "source_utf8_b64": base64.b64encode(entry["source"].encode("utf-8")).decode("ascii"),
            }
            for entry in entries
        ],
    }
    process = subprocess.run(
        [ast_python_bin, str(script_path), "--resolver-worker"],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    response = json.loads(process.stdout)
    return {int(item["request_index"]): item for item in response.get("files", [])}


def decode_python_source(data: bytes) -> tuple[str, str]:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def read_git_blob(clone_path: Path, blob_oid: str, timeout_seconds: int) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(clone_path), "cat-file", "blob", blob_oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_seconds,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace").strip())
    return process.stdout


def validate_python2_source(python2_bin: str, source_bytes: bytes, timeout_seconds: int) -> str:
    if not python2_bin:
        return "not_configured"
    if not Path(python2_bin).exists() and not shutil_which(python2_bin):
        return "executable_not_found"
    worker = (
        "import base64,sys\n"
        "data=base64.b64decode(sys.stdin.read())\n"
        "try:\n"
        " compile(data, '<blob>', 'exec')\n"
        " sys.stdout.write('success')\n"
        "except Exception as e:\n"
        " sys.stdout.write('error:' + e.__class__.__name__ + ':' + str(e))\n"
    )
    try:
        process = subprocess.run(
            [python2_bin, "-c", worker],
            input=base64.b64encode(source_bytes).decode("ascii"),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return f"execution_failed:{type(exc).__name__}:{exc}"
    return process.stdout.strip() or f"exit_{process.returncode}"


def shutil_which(command: str) -> Optional[str]:
    import shutil

    return shutil.which(command)


def classify_root_cause(source: str, worker_result: dict[str, Any], python2_status: str) -> str:
    if re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", source):
        return "template_placeholder"
    if source.startswith("LPimport "):
        return "simple_source_typo"
    if python2_status == "success":
        return "python2_source"
    if worker_result.get("recovery_method") == "no_function_confirmed":
        return "malformed_source_without_named_functions"
    if worker_result.get("python312_ast_status") == "success":
        return "python311_312_boundary_runtime_mismatch"
    return "malformed_or_incomplete_source"


def make_body_key(
    snapshot_key: str,
    path: str,
    qualified_name: str,
    occurrence_index: int,
    function_start_line: int,
    function_end_line: int,
    raw_body_sha256: str,
) -> str:
    raw = (
        f"{snapshot_key}|{path}|{qualified_name}|{occurrence_index}|"
        f"{function_start_line}|{function_end_line}|{raw_body_sha256}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def save_body(
    body_store_root: Path,
    snapshot_key: str,
    body_key: str,
    body_text: str,
    token_count: int,
    start_line: int,
    end_line: int,
    save_scope: str,
    qualifies: bool,
) -> tuple[bool, str, str]:
    if save_scope == "qualifying" and not qualifies:
        return False, "", ""
    snapshot_dir = body_store_root / snapshot_key
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{body_key}__tok-{token_count}__L{start_line}-L{end_line}.txt"
    output_path = snapshot_dir / filename
    encoded = body_text.encode(BODY_OUTPUT_ENCODING)
    if output_path.exists():
        if output_path.read_bytes() != encoded:
            raise ValueError(f"Existing body content mismatch: {output_path}")
    else:
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        temp_path.write_bytes(encoded)
        temp_path.replace(output_path)
    relative = f"{snapshot_key}/{filename}"
    return True, relative, str(output_path)


def save_dataframe(frame: "pd.DataFrame", path: Path, columns: Optional[list[str]] = None) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if columns is not None:
        for column in columns:
            if column not in output.columns:
                output[column] = pd.NA
        output = output[columns]
    temp = path.with_suffix(path.suffix + ".tmp")
    output.to_csv(temp, index=False)
    temp.replace(path)


def load_relevant_function_details(path: Path, affected_keys: set[tuple[str, str, str]]) -> "pd.DataFrame":
    selected: list[pd.DataFrame] = []
    use_columns = None
    for chunk in pd.read_csv(path, low_memory=False, chunksize=200_000, usecols=use_columns):
        key_series = list(zip(chunk["snapshot_key"].astype(str), chunk["path"].astype(str), chunk["blob_oid"].astype(str)))
        mask = pd.Series([key in affected_keys for key in key_series], index=chunk.index)
        if mask.any():
            selected.append(chunk.loc[mask].copy())
    if not selected:
        return pd.DataFrame()
    return pd.concat(selected, ignore_index=True, sort=False)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"1", "true", "t", "yes", "y"}


def int_value(value: Any, default: int = 0) -> int:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return default if pd.isna(numeric) else int(numeric)


def process_worker_record(
    source: str,
    payload: dict[str, Any],
    metadata: dict[str, Any],
    body_store_root: Path,
    body_save_scope: str,
) -> dict[str, Any]:
    start_offset = int(payload["function_start_offset"])
    end_offset = int(payload["function_end_offset"])
    body_start = int(payload["body_start_offset"])
    extraction_status = str(payload["extraction_status"])
    detail = {
        **metadata,
        "qualified_name": payload["qualified_name"],
        "function_name": payload["function_name"],
        "function_kind": payload["function_kind"],
        "occurrence_index": int(payload["occurrence_index"]),
        "function_start_line": int(payload["function_start_line"]),
        "function_end_line": int(payload["function_end_line"]),
        "body_start_line": int(payload["body_start_line"]),
        "body_end_line": int(payload["body_end_line"]),
        "leading_docstring_removed": bool(payload["leading_docstring_removed"]),
        "contains_nested_named_definition": bool(payload["contains_nested_named_definition"]),
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
        "extraction_status": extraction_status,
        "exclusion_reason": payload.get("exclusion_reason", ""),
    }
    if extraction_status != "success":
        return detail
    raw_function = source[start_offset:end_offset]
    body_text = source[body_start:end_offset]
    if not body_text or not body_text.strip():
        detail["extraction_status"] = "no_body_after_docstring"
        detail["exclusion_reason"] = "empty_body_after_extraction"
        return detail
    token_count = len(body_text.split(" "))
    qualifies = TOKEN_MIN <= token_count <= TOKEN_MAX
    raw_body_sha = sha256_text(body_text)
    body_key = make_body_key(
        metadata["snapshot_key"],
        metadata["path"],
        str(payload["qualified_name"]),
        int(payload["occurrence_index"]),
        int(payload["function_start_line"]),
        int(payload["function_end_line"]),
        raw_body_sha,
    )
    saved, relative, absolute = save_body(
        body_store_root,
        metadata["snapshot_key"],
        body_key,
        body_text,
        token_count,
        int(payload["body_start_line"]),
        int(payload["body_end_line"]),
        body_save_scope,
        qualifies,
    )
    detail.update(
        {
            "raw_function_sha256": sha256_text(raw_function),
            "raw_body_sha256": raw_body_sha,
            "raw_body_character_count": len(body_text),
            "raw_body_utf8_byte_count": len(body_text.encode(BODY_OUTPUT_ENCODING)),
            "raw_body_physical_line_count": count_physical_lines(body_text),
            "body_key": body_key,
            "body_saved": saved,
            "body_output_relative_path": relative,
            "body_output_path": absolute,
            "token_count": token_count,
            "qualifies_100_200": qualifies,
        }
    )
    return detail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve run-x-d01 parsing and boundary issues.")
    parser.add_argument("--snapshot-manifest-file", type=Path, required=True)
    parser.add_argument("--snapshot-results-file", type=Path, required=True)
    parser.add_argument("--function-details-file", type=Path, required=True)
    parser.add_argument("--file-issues-file", type=Path, required=True)
    parser.add_argument("--body-store-root", type=Path, required=True)
    parser.add_argument("--body-save-scope", choices=["all", "qualifying"], default="all")
    parser.add_argument("--blob-review-output", type=Path, required=True)
    parser.add_argument("--recovered-function-details-output", type=Path, required=True)
    parser.add_argument("--file-resolution-output", type=Path, required=True)
    parser.add_argument("--snapshot-corrections-output", type=Path, required=True)
    parser.add_argument("--resolved-snapshot-results-output", type=Path, required=True)
    parser.add_argument("--resolution-decisions-output", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True)
    parser.add_argument("--qc-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--ast-python-bin", required=True)
    parser.add_argument("--python2-bin", default="")
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--worker-timeout-seconds", type=int, default=600)
    parser.add_argument("--python2-timeout-seconds", type=int, default=60)
    parser.add_argument("--worker-batch-bytes", type=int, default=20_000_000)
    parser.add_argument("--apply-counterfactual", action="store_true")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--blob-oid", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-self-test", action="store_true")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def run_internal_self_test(ast_python_bin: str, script_path: Path, timeout_seconds: int) -> None:
    samples = [
        (
            "exact.py",
            'def f():\n    # comment\n    x = 1\n\nclass C:\n    async def m(self): return value\n',
            "python312_ast_exact",
            2,
        ),
        (
            "template.py",
            'class {check_class}(AgentCheck):\n    def check(self, instance):\n        value = 1\n        return value\n',
            "python312_token_fallback_complete",
            1,
        ),
        (
            "typo.py",
            'LPimport asyncio\n\ndef outer():\n    def nested():\n        return 1\n    return nested()\n',
            "python312_token_fallback_complete",
            1,
        ),
        (
            "python2.py",
            'def legacy(value):\n    try:\n        return 0x10L\n    except Exception, e:\n        return value\n',
            "python312_token_fallback_complete",
            1,
        ),
        (
            "nofunc.py",
            "from ",
            "no_function_confirmed",
            0,
        ),
        (
            "doc.py",
            'def f():\n    """Doc."""\n\n    # implementation\n    return 1\n',
            "python312_ast_exact",
            1,
        ),
    ]
    entries = [
        {"request_index": index, "path": name, "source": source}
        for index, (name, source, _, _) in enumerate(samples)
    ]
    results = run_worker_batch(entries, ast_python_bin, script_path, timeout_seconds)
    for index, (_, source, expected_method, expected_count) in enumerate(samples):
        result = results[index]
        if result.get("status") != "success":
            raise AssertionError(f"Worker self-test failed: {result}")
        if result.get("recovery_method") != expected_method:
            raise AssertionError(
                f"Unexpected method for sample {index}: {result.get('recovery_method')} != {expected_method}"
            )
        if len(result.get("records", [])) != expected_count:
            raise AssertionError(
                f"Unexpected function count for sample {index}: {len(result.get('records', []))} != {expected_count}"
            )
    doc_result = results[5]["records"][0]
    body = samples[5][1][int(doc_result["body_start_offset"]):int(doc_result["function_end_offset"])]
    if not body.startswith("\n    # implementation"):
        raise AssertionError(f"Docstring boundary self-test failed: {body!r}")
    logging.info("Internal self-test PASS: exact AST, templates, typo, Python 2 syntax, no-function, and docstring cases")


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    for path in [
        args.snapshot_manifest_file,
        args.snapshot_results_file,
        args.function_details_file,
        args.file_issues_file,
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)
    args.body_store_root.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()
    ast_metadata = inspect_ast_python(args.ast_python_bin, script_path, args.worker_timeout_seconds)
    logging.info("AST worker Python: %s", ast_metadata["python_version"])
    if not args.skip_self_test:
        run_internal_self_test(args.ast_python_bin, script_path, args.worker_timeout_seconds)

    manifest = pd.read_csv(args.snapshot_manifest_file, low_memory=False)
    results = pd.read_csv(args.snapshot_results_file, low_memory=False)
    issues = pd.read_csv(args.file_issues_file, low_memory=False)
    required_issue = set(ISSUE_KEY_COLUMNS + ["repo_name", "commit_sha", "issue_stage", "issue_type", "issue_message"])
    missing = required_issue - set(issues.columns)
    if missing:
        raise ValueError(f"File issues missing columns: {sorted(missing)}")
    issue_occurrences = issues.drop_duplicates(ISSUE_KEY_COLUMNS + ["issue_stage"]).copy()
    if args.repo_name:
        issue_occurrences = issue_occurrences[issue_occurrences["repo_name"].eq(args.repo_name)]
    if args.blob_oid:
        issue_occurrences = issue_occurrences[issue_occurrences["blob_oid"].eq(args.blob_oid)]
    issue_occurrences = issue_occurrences.sort_values(["repo_name", "blob_oid", "snapshot_key", "path"])
    if args.limit > 0:
        selected_blobs = issue_occurrences["blob_oid"].drop_duplicates().head(args.limit)
        issue_occurrences = issue_occurrences[issue_occurrences["blob_oid"].isin(set(selected_blobs))]
    if issue_occurrences.empty:
        raise ValueError("No issue occurrences matched the requested filters")

    manifest_map = manifest.set_index("snapshot_key", drop=False)
    result_map = results.set_index("snapshot_key", drop=False)
    affected_keys = set(
        zip(
            issue_occurrences["snapshot_key"].astype(str),
            issue_occurrences["path"].astype(str),
            issue_occurrences["blob_oid"].astype(str),
        )
    )
    logging.info("Loading relevant function-detail rows for %d affected file occurrences", len(affected_keys))
    relevant_details = load_relevant_function_details(args.function_details_file, affected_keys)

    unique_blob_rows = issue_occurrences.drop_duplicates("blob_oid", keep="first").reset_index(drop=True)
    blob_sources: dict[str, dict[str, Any]] = {}
    worker_entries: list[dict[str, Any]] = []
    for request_index, row in unique_blob_rows.iterrows():
        snapshot_key = str(row["snapshot_key"])
        manifest_row = manifest_map.loc[snapshot_key]
        clone_path = Path(str(manifest_row["clone_path"])).expanduser().resolve()
        blob_oid = str(row["blob_oid"])
        data = read_git_blob(clone_path, blob_oid, args.git_timeout_seconds)
        source, encoding = decode_python_source(data)
        blob_sources[blob_oid] = {
            "data": data,
            "source": source,
            "encoding": encoding,
            "request_index": request_index,
        }
        worker_entries.append(
            {
                "request_index": request_index,
                "path": str(row["path"]),
                "source": source,
                "byte_count": len(source.encode("utf-8")),
            }
        )

    worker_results: dict[int, dict[str, Any]] = {}
    batch: list[dict[str, Any]] = []
    batch_bytes = 0
    for entry in worker_entries:
        size = int(entry["byte_count"])
        if batch and batch_bytes + size > args.worker_batch_bytes:
            worker_results.update(
                run_worker_batch(batch, args.ast_python_bin, script_path, args.worker_timeout_seconds)
            )
            batch = []
            batch_bytes = 0
        batch.append(entry)
        batch_bytes += size
    if batch:
        worker_results.update(
            run_worker_batch(batch, args.ast_python_bin, script_path, args.worker_timeout_seconds)
        )

    blob_analysis: dict[str, dict[str, Any]] = {}
    blob_review_rows: list[dict[str, Any]] = []
    for _, row in unique_blob_rows.iterrows():
        blob_oid = str(row["blob_oid"])
        source_info = blob_sources[blob_oid]
        worker_result = worker_results[int(source_info["request_index"])]
        python2_status = validate_python2_source(
            args.python2_bin,
            source_info["data"],
            args.python2_timeout_seconds,
        )
        root_cause = classify_root_cause(source_info["source"], worker_result, python2_status)
        method = str(worker_result.get("recovery_method", "unresolved"))
        counterfactual = bool(worker_result.get("counterfactual_repair_applied", False))
        auto_applied = method in APPLIED_METHODS or (counterfactual and args.apply_counterfactual)
        requires_review = not auto_applied
        resolution_status = "resolved" if auto_applied else "pending_review"
        records = worker_result.get("records", [])
        extracted_records = [record for record in records if record.get("extraction_status") == "success"]
        docstring_only = [record for record in records if record.get("extraction_status") == "no_body_after_docstring"]
        token_all = 0
        token_range = 0
        qualifying = 0
        for record in extracted_records:
            body = source_info["source"][int(record["body_start_offset"]):int(record["function_end_offset"])]
            count = len(body.split(" "))
            token_all += count
            if TOKEN_MIN <= count <= TOKEN_MAX:
                token_range += count
                qualifying += 1
        matching_issue_rows = issues[issues["blob_oid"].astype(str).eq(blob_oid)]
        matching_occurrences = issue_occurrences[issue_occurrences["blob_oid"].astype(str).eq(blob_oid)]
        blob_review_rows.append(
            {
                "blob_oid": blob_oid,
                "representative_repo_name": row["repo_name"],
                "representative_path": row["path"],
                "issue_stages": " | ".join(sorted(set(matching_issue_rows["issue_stage"].astype(str)))),
                "issue_types": " | ".join(sorted(set(matching_issue_rows["issue_type"].astype(str)))),
                "issue_occurrences": len(matching_issue_rows),
                "affected_snapshots": matching_occurrences["snapshot_key"].nunique(),
                "affected_paths": matching_occurrences["path"].nunique(),
                "source_byte_count": len(source_info["data"]),
                "source_encoding": source_info["encoding"],
                "python312_ast_status": worker_result.get("python312_ast_status", "error"),
                "python312_ast_error_type": worker_result.get("python312_ast_error_type", ""),
                "python312_ast_error_message": worker_result.get("python312_ast_error_message", ""),
                "tokenizer_complete": worker_result.get("tokenizer_complete", False),
                "tokenizer_error_type": worker_result.get("tokenizer_error_type", ""),
                "tokenizer_error_message": worker_result.get("tokenizer_error_message", ""),
                "regex_named_function_candidates": worker_result.get("regex_named_function_candidates", 0),
                "indexed_named_function_headers": worker_result.get("indexed_named_function_headers", 0),
                "eligible_function_count": len(records),
                "extractable_function_count": len(extracted_records),
                "docstring_only_function_count": len(docstring_only),
                "qualifying_function_count": qualifying,
                "token_py_all_function_bodies": token_all,
                "token_py_100_200": token_range,
                "recovery_method": method,
                "root_cause": root_cause,
                "python2_validation_status": python2_status,
                "counterfactual_repair_applied": counterfactual,
                "counterfactual_repair_description": worker_result.get("counterfactual_repair_description", ""),
                "resolution_status": resolution_status,
                "auto_applied": auto_applied,
                "requires_review": requires_review,
                "notes": "Original historical source is never rewritten; token counts use original raw body text.",
            }
        )
        blob_analysis[blob_oid] = {
            "worker": worker_result,
            "root_cause": root_cause,
            "auto_applied": auto_applied,
            "requires_review": requires_review,
            "source": source_info["source"],
            "source_encoding": source_info["encoding"],
        }

    recovered_details: list[dict[str, Any]] = []
    file_resolution_rows: list[dict[str, Any]] = []
    for _, occurrence in issue_occurrences.iterrows():
        snapshot_key = str(occurrence["snapshot_key"])
        path = str(occurrence["path"])
        blob_oid = str(occurrence["blob_oid"])
        stage = str(occurrence["issue_stage"])
        manifest_row = manifest_map.loc[snapshot_key]
        analysis = blob_analysis[blob_oid]
        worker_result = analysis["worker"]
        auto_applied = bool(analysis["auto_applied"])
        source = analysis["source"]
        records = list(worker_result.get("records", []))
        old_file_details = relevant_details[
            relevant_details["snapshot_key"].astype(str).eq(snapshot_key)
            & relevant_details["path"].astype(str).eq(path)
            & relevant_details["blob_oid"].astype(str).eq(blob_oid)
        ].copy() if not relevant_details.empty else pd.DataFrame()
        old_boundary = old_file_details[
            old_file_details.get("extraction_status", pd.Series(dtype=str)).astype(str).eq("boundary_failed")
        ].copy() if not old_file_details.empty else pd.DataFrame()
        original_boundary_count = len(old_boundary)

        selected_records = records
        unresolved_boundary = 0
        if stage == "function_boundary":
            wanted = {
                (
                    str(row["qualified_name"]),
                    int_value(row["occurrence_index"]),
                    int_value(row["function_start_line"]),
                )
                for _, row in old_boundary.iterrows()
            }
            selected_records = [
                record
                for record in records
                if (
                    str(record["qualified_name"]),
                    int(record["occurrence_index"]),
                    int(record["function_start_line"]),
                ) in wanted
            ]
            unresolved_boundary = max(original_boundary_count - len(selected_records), 0)

        metadata_base = {
            "snapshot_key": snapshot_key,
            "dataset_source": manifest_row["dataset_source"],
            "repo_name": manifest_row["repo_name"],
            "commit_sha": manifest_row["latest_commit_effective"] if "latest_commit_effective" in manifest_row else occurrence["commit_sha"],
            "path": path,
            "blob_oid": blob_oid,
            "blob_size": int_value(issues.loc[
                issues["snapshot_key"].astype(str).eq(snapshot_key)
                & issues["path"].astype(str).eq(path)
                & issues["blob_oid"].astype(str).eq(blob_oid),
                "blob_size",
            ].iloc[0] if not issues.loc[
                issues["snapshot_key"].astype(str).eq(snapshot_key)
                & issues["path"].astype(str).eq(path)
                & issues["blob_oid"].astype(str).eq(blob_oid)
            ].empty else 0),
            "original_issue_stage": stage,
            "recovery_method": worker_result.get("recovery_method", "unresolved"),
            "recovery_confidence": "exact" if worker_result.get("recovery_method") == "python312_ast_exact" else "tolerant_original_source",
            "counterfactual_repair": bool(worker_result.get("counterfactual_repair_applied", False)),
        }
        occurrence_details: list[dict[str, Any]] = []
        if auto_applied and not args.dry_run:
            for record in selected_records:
                occurrence_details.append(
                    process_worker_record(
                        source,
                        record,
                        metadata_base,
                        args.body_store_root,
                        args.body_save_scope,
                    )
                )
        elif auto_applied:
            for record in selected_records:
                detail = process_worker_record(
                    source,
                    record,
                    metadata_base,
                    Path(tempfile.mkdtemp(prefix="d01a-dry-run-")),
                    "qualifying",
                )
                detail["body_saved"] = False
                detail["body_output_relative_path"] = ""
                detail["body_output_path"] = ""
                occurrence_details.append(detail)

        recovered_details.extend(occurrence_details)
        success_details = [row for row in occurrence_details if row["extraction_status"] == "success"]
        docstring_details = [row for row in occurrence_details if row["extraction_status"] == "no_body_after_docstring"]
        qualifying_details = [row for row in success_details if bool_value(row["qualifies_100_200"])]
        token_all_delta = sum(int_value(row["token_count"]) for row in success_details)
        token_range_delta = sum(int_value(row["token_count"]) for row in qualifying_details)

        old_file_has_qualifying = False
        if not old_file_details.empty and "qualifies_100_200" in old_file_details.columns:
            old_file_has_qualifying = old_file_details["qualifies_100_200"].map(bool_value).any()

        if stage == "function_boundary":
            all_delta = 0
            nested_delta = 0
            file_with_function_delta = 0
            file_qualifying_delta = int(bool(qualifying_details) and not old_file_has_qualifying)
        else:
            all_delta = len(selected_records) if auto_applied else 0
            nested_delta = sum(int(bool(row.get("contains_nested_named_definition", False))) for row in selected_records) if auto_applied else 0
            file_with_function_delta = int(bool(selected_records) and auto_applied)
            file_qualifying_delta = int(bool(qualifying_details))

        no_function_resolved = (
            auto_applied
            and worker_result.get("recovery_method") == "no_function_confirmed"
            and not selected_records
        )
        metric_impact_resolved = bool(auto_applied and (no_function_resolved or unresolved_boundary == 0))
        resolution_status = "resolved" if metric_impact_resolved else "pending_review"
        note = (
            "No named function declarations were found; metric delta is zero."
            if no_function_resolved
            else "Recovered from original raw source."
            if metric_impact_resolved
            else "Recovery remains incomplete or requires policy review."
        )
        original_issue_rows = issues[
            issues["snapshot_key"].astype(str).eq(snapshot_key)
            & issues["path"].astype(str).eq(path)
            & issues["blob_oid"].astype(str).eq(blob_oid)
            & issues["issue_stage"].astype(str).eq(stage)
        ]
        file_resolution_rows.append(
            {
                "snapshot_key": snapshot_key,
                "dataset_source": manifest_row["dataset_source"],
                "repo_name": manifest_row["repo_name"],
                "commit_sha": occurrence["commit_sha"],
                "path": path,
                "blob_oid": blob_oid,
                "blob_size": metadata_base["blob_size"],
                "original_issue_stage": stage,
                "original_issue_row_count": len(original_issue_rows),
                "original_boundary_failed_function_count": original_boundary_count,
                "recovery_method": worker_result.get("recovery_method", "unresolved"),
                "root_cause": analysis["root_cause"],
                "recovered_function_count_all_delta": all_delta,
                "recovered_function_count_extracted_delta": len(success_details),
                "recovered_function_count_100_200_delta": len(qualifying_details),
                "recovered_function_count_docstring_only_delta": len(docstring_details),
                "recovered_function_count_with_nested_delta": nested_delta,
                "recovered_python_file_with_function_delta": file_with_function_delta,
                "recovered_python_file_with_function_100_200_delta": file_qualifying_delta,
                "recovered_token_py_all_delta": token_all_delta,
                "recovered_token_py_100_200_delta": token_range_delta,
                "resolved_boundary_failure_count": original_boundary_count - unresolved_boundary if stage == "function_boundary" else 0,
                "unresolved_boundary_failure_count": unresolved_boundary,
                "metric_impact_resolved": metric_impact_resolved,
                "counterfactual_repair": bool(worker_result.get("counterfactual_repair_applied", False)),
                "auto_applied": auto_applied,
                "resolution_status": resolution_status,
                "resolution_note": note,
            }
        )

    file_resolutions = pd.DataFrame(file_resolution_rows)
    recovered_detail_frame = pd.DataFrame(recovered_details)
    correction_rows: list[dict[str, Any]] = []
    resolved_results = results.copy()
    for text_column in [
        "snapshot_status",
        "resolution_decision",
        "resolution_note",
        "error_stage",
        "error_message",
    ]:
        if text_column in resolved_results.columns:
            resolved_results[text_column] = resolved_results[text_column].fillna("").astype("object")
    extra_columns = [
        "d01a_implementation_version",
        "d01a_resolution_status",
        "d01a_affected_file_occurrences",
        "d01a_resolved_file_occurrences",
        "d01a_unresolved_file_occurrences",
        "d01a_counterfactual_file_occurrences",
        "d01a_token_py_100_200_delta",
        "d01a_resolution_note",
    ]
    for column in extra_columns:
        if column not in resolved_results.columns:
            resolved_results[column] = "" if "count" not in column and "delta" not in column else 0

    delta_map = {
        "function_count_py_all": "recovered_function_count_all_delta",
        "function_count_py_extracted": "recovered_function_count_extracted_delta",
        "function_count_py_100_200": "recovered_function_count_100_200_delta",
        "function_count_py_docstring_only": "recovered_function_count_docstring_only_delta",
        "function_count_py_with_nested": "recovered_function_count_with_nested_delta",
        "python_file_count_with_function": "recovered_python_file_with_function_delta",
        "python_file_count_with_function_100_200": "recovered_python_file_with_function_100_200_delta",
        "token_py_all_function_bodies": "recovered_token_py_all_delta",
        "token_py_100_200": "recovered_token_py_100_200_delta",
    }

    for snapshot_key, group in file_resolutions.groupby("snapshot_key", sort=False):
        original = result_map.loc[snapshot_key]
        affected_count = len(group)
        resolved_count = int(group["metric_impact_resolved"].map(bool_value).sum())
        unresolved_count = affected_count - resolved_count
        counterfactual_count = int(group["counterfactual_repair"].map(bool_value).sum())
        deltas = {name: int(pd.to_numeric(group[column], errors="coerce").fillna(0).sum()) for name, column in delta_map.items()}
        corrected: dict[str, int] = {}
        for metric_name, delta in deltas.items():
            partial_name = f"{metric_name}_partial"
            base_value = int_value(original.get(partial_name, original.get(metric_name, 0)))
            corrected[metric_name] = base_value + delta
        available = unresolved_count == 0
        status = "resolved_after_d01a" if available else "partial_needs_review_after_d01a"
        note = f"resolved_files={resolved_count}/{affected_count}; token_delta={deltas['token_py_100_200']}"
        correction_rows.append(
            {
                "manifest_order": original["manifest_order"],
                "snapshot_key": snapshot_key,
                "dataset_source": original["dataset_source"],
                "repo_name": original["repo_name"],
                "commit_sha": original["commit_sha"],
                "repo_month_rows": original["repo_month_rows"],
                "original_snapshot_status": original["snapshot_status"],
                "original_metric_available": bool_value(original["metric_available"]),
                "original_failed_python_file_count": int_value(original["failed_python_file_count"]),
                "original_boundary_failure_count": int_value(original["function_count_py_boundary_failed_partial"]),
                "affected_file_occurrences": affected_count,
                "resolved_file_occurrences": resolved_count,
                "unresolved_file_occurrences": unresolved_count,
                "counterfactual_file_occurrences": counterfactual_count,
                "function_count_py_all_delta": deltas["function_count_py_all"],
                "function_count_py_extracted_delta": deltas["function_count_py_extracted"],
                "function_count_py_100_200_delta": deltas["function_count_py_100_200"],
                "function_count_py_docstring_only_delta": deltas["function_count_py_docstring_only"],
                "function_count_py_with_nested_delta": deltas["function_count_py_with_nested"],
                "python_file_count_with_function_delta": deltas["python_file_count_with_function"],
                "python_file_count_with_function_100_200_delta": deltas["python_file_count_with_function_100_200"],
                "token_py_all_function_bodies_delta": deltas["token_py_all_function_bodies"],
                "token_py_100_200_delta": deltas["token_py_100_200"],
                "corrected_function_count_py_all": corrected["function_count_py_all"],
                "corrected_function_count_py_extracted": corrected["function_count_py_extracted"],
                "corrected_function_count_py_100_200": corrected["function_count_py_100_200"],
                "corrected_function_count_py_docstring_only": corrected["function_count_py_docstring_only"],
                "corrected_function_count_py_with_nested": corrected["function_count_py_with_nested"],
                "corrected_python_file_count_with_function": corrected["python_file_count_with_function"],
                "corrected_python_file_count_with_function_100_200": corrected["python_file_count_with_function_100_200"],
                "corrected_token_py_all_function_bodies": corrected["token_py_all_function_bodies"],
                "corrected_token_py_100_200": corrected["token_py_100_200"],
                "metric_available_after_d01a": available,
                "resolution_status": status,
                "resolution_note": note,
            }
        )
        index_mask = resolved_results["snapshot_key"].astype(str).eq(snapshot_key)
        resolved_results.loc[index_mask, "d01a_implementation_version"] = IMPLEMENTATION_VERSION
        resolved_results.loc[index_mask, "d01a_resolution_status"] = status
        resolved_results.loc[index_mask, "d01a_affected_file_occurrences"] = affected_count
        resolved_results.loc[index_mask, "d01a_resolved_file_occurrences"] = resolved_count
        resolved_results.loc[index_mask, "d01a_unresolved_file_occurrences"] = unresolved_count
        resolved_results.loc[index_mask, "d01a_counterfactual_file_occurrences"] = counterfactual_count
        resolved_results.loc[index_mask, "d01a_token_py_100_200_delta"] = deltas["token_py_100_200"]
        resolved_results.loc[index_mask, "d01a_resolution_note"] = note
        if available:
            for metric_name, value in corrected.items():
                resolved_results.loc[index_mask, metric_name] = value
            resolved_results.loc[index_mask, "metric_available"] = True
            resolved_results.loc[index_mask, "snapshot_status"] = status
            resolved_results.loc[index_mask, "resolution_decision"] = "resolved_full"
            resolved_results.loc[index_mask, "resolution_note"] = note
            resolved_results.loc[index_mask, "partial_metric_accepted"] = False
            resolved_results.loc[index_mask, "error_stage"] = ""
            resolved_results.loc[index_mask, "error_message"] = ""

    corrections = pd.DataFrame(correction_rows)
    unresolved_files = file_resolutions[~file_resolutions["metric_impact_resolved"].map(bool_value)].copy()
    unresolved_frame = pd.DataFrame(
        [
            {
                "snapshot_key": row["snapshot_key"],
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "commit_sha": row["commit_sha"],
                "path": row["path"],
                "blob_oid": row["blob_oid"],
                "original_issue_stage": row["original_issue_stage"],
                "recovery_method": row["recovery_method"],
                "root_cause": row["root_cause"],
                "resolution_status": row["resolution_status"],
                "resolution_note": row["resolution_note"],
            }
            for _, row in unresolved_files.iterrows()
        ]
    )
    decisions = corrections[["snapshot_key", "resolution_status", "resolution_note"]].copy()
    decisions["resolution_decision"] = decisions["resolution_status"].map(
        {"resolved_after_d01a": "resolved_full", "partial_needs_review_after_d01a": "pending_review"}
    )
    decisions = decisions[["snapshot_key", "resolution_decision", "resolution_note"]]

    blob_review = pd.DataFrame(blob_review_rows)
    qc_rows: list[dict[str, Any]] = []
    def add_qc(name: str, observed: Any, expected: Any, status: str, note: str = "") -> None:
        qc_rows.append({"check_name": name, "status": status, "observed": observed, "expected": expected, "note": note})

    unique_issue_blobs = issue_occurrences["blob_oid"].nunique()
    add_qc("unique_issue_blobs_reviewed", len(blob_review), unique_issue_blobs, "pass" if len(blob_review) == unique_issue_blobs else "fail")
    add_qc("affected_file_occurrences", len(file_resolutions), len(issue_occurrences), "pass" if len(file_resolutions) == len(issue_occurrences) else "fail")
    add_qc("resolved_file_occurrences", int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()), len(file_resolutions), "pass" if unresolved_frame.empty else "warn")
    add_qc("unresolved_file_occurrences", len(unresolved_frame), 0, "pass" if unresolved_frame.empty else "warn")
    add_qc("resolved_snapshots", int(corrections["metric_available_after_d01a"].map(bool_value).sum()), len(corrections), "pass" if corrections["metric_available_after_d01a"].map(bool_value).all() else "warn")
    add_qc("negative_corrected_token_metrics", int((pd.to_numeric(corrections["corrected_token_py_100_200"], errors="coerce") < 0).sum()), 0, "pass")
    add_qc("counterfactual_files_applied", int((file_resolutions["counterfactual_repair"].map(bool_value) & file_resolutions["auto_applied"].map(bool_value)).sum()), 0 if not args.apply_counterfactual else "allowed", "pass" if args.apply_counterfactual or not (file_resolutions["counterfactual_repair"].map(bool_value) & file_resolutions["auto_applied"].map(bool_value)).any() else "fail")
    qc = pd.DataFrame(qc_rows)

    summary_rows: list[dict[str, Any]] = []
    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_rows.append({"section": section, "metric": metric, "value": value, "note": note})

    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "experiment", EXPERIMENT_NAME)
    add_summary("implementation", "main_python", sys.version.split()[0])
    add_summary("implementation", "ast_python", ast_metadata["python_version"])
    add_summary("definition", "token_definition", TOKEN_DEFINITION)
    add_summary("definition", "apply_counterfactual", int(args.apply_counterfactual))
    add_summary("input", "issue_rows", len(issues))
    add_summary("input", "selected_issue_file_occurrences", len(issue_occurrences))
    add_summary("input", "selected_unique_blobs", unique_issue_blobs)
    add_summary("result", "resolved_file_occurrences", int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()))
    add_summary("result", "unresolved_file_occurrences", len(unresolved_frame))
    add_summary("result", "affected_snapshots", corrections["snapshot_key"].nunique())
    add_summary("result", "resolved_snapshots", int(corrections["metric_available_after_d01a"].map(bool_value).sum()))
    add_summary("result", "token_py_100_200_delta", int(pd.to_numeric(file_resolutions["recovered_token_py_100_200_delta"], errors="coerce").fillna(0).sum()))
    add_summary("result", "recovered_function_details", len(recovered_detail_frame))
    for method, count in blob_review["recovery_method"].value_counts().items():
        add_summary("recovery_method", str(method), int(count))
    for cause, count in blob_review["root_cause"].value_counts().items():
        add_summary("root_cause", str(cause), int(count))
    summary = pd.DataFrame(summary_rows)

    save_dataframe(blob_review, args.blob_review_output, BLOB_REVIEW_COLUMNS)
    save_dataframe(recovered_detail_frame, args.recovered_function_details_output, RECOVERED_DETAIL_COLUMNS)
    save_dataframe(file_resolutions, args.file_resolution_output, FILE_RESOLUTION_COLUMNS)
    save_dataframe(corrections, args.snapshot_corrections_output, SNAPSHOT_CORRECTION_COLUMNS)
    save_dataframe(resolved_results, args.resolved_snapshot_results_output)
    save_dataframe(decisions, args.resolution_decisions_output)
    save_dataframe(unresolved_frame, args.unresolved_output, UNRESOLVED_COLUMNS)
    save_dataframe(qc, args.qc_output, QC_COLUMNS)
    save_dataframe(summary, args.summary_output, SUMMARY_COLUMNS)

    logging.info(
        "Completed run-x-d01a-v1: blobs=%d; file_occurrences=%d; resolved=%d; unresolved=%d; snapshots_resolved=%d/%d; token_delta=%d",
        unique_issue_blobs,
        len(file_resolutions),
        int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()),
        len(unresolved_frame),
        int(corrections["metric_available_after_d01a"].map(bool_value).sum()),
        len(corrections),
        int(pd.to_numeric(file_resolutions["recovered_token_py_100_200_delta"], errors="coerce").fillna(0).sum()),
    )
    if args.fail_on_unresolved and not unresolved_frame.empty:
        return 2
    return 0


if __name__ == "__main__":
    if "--resolver-worker-version" in sys.argv:
        json.dump(worker_version_payload(), sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(0)
    if "--resolver-worker" in sys.argv:
        raise SystemExit(run_worker_cli())
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        logging.exception("run-x-d01a failed: %s", exc)
        raise SystemExit(1)
