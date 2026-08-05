#!/usr/bin/env python3
"""Resolve the final run-x-d01a parser-version and malformed-source cases.

This self-contained run-x-d01b implementation consumes only the unresolved
file occurrences left by run-x-d01a.  Recovery follows a strict evidence
order:

1. Parse the original historical source with Python 3.12 AST.
2. If Python 3.12 fails, parse the same unmodified source with Python 3.13 AST.
3. If both exact parsers fail, apply one of the two explicitly reviewed,
   blob-specific diagnostic repairs.  Function identity and boundaries come
   from the repaired source, but every body hash and literal-space token count
   is computed from the original historical blob.

Python 3.13 exact recovery is automatically production-applied because it does
not alter the source.  Reviewed malformed-source repairs remain diagnostic by
default and are production-applied only when
``--apply-reviewed-malformed`` is explicitly supplied.

Nested functions are not separate metric occurrences.  Their original source
remains inside the enclosing function body.  Existing run-x-d01 and
run-x-d01a outputs are never overwritten.
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
EXPERIMENT_NAME = "run-x-d01b-resolve-python313-and-malformed"
WORKER_PROTOCOL_VERSION = "v1"
TOKEN_MIN = 100
TOKEN_MAX = 200
TOKEN_DEFINITION = "len(raw_implementation_body.split(' '))"
BODY_OUTPUT_ENCODING = "utf-8"

ISSUE_KEY_COLUMNS = ["snapshot_key", "path", "blob_oid"]
METRIC_NAMES = [
    "function_count_py_all",
    "function_count_py_extracted",
    "function_count_py_100_200",
    "function_count_py_docstring_only",
    "function_count_py_with_nested",
    "python_file_count_with_function",
    "python_file_count_with_function_100_200",
    "token_py_all_function_bodies",
    "token_py_100_200",
]

# These two blobs were reviewed at source level after run-x-d01a.  The repair
# functions below verify both the blob id and the exact malformed source shape
# before producing a diagnostic parse source.
HAL_MALFORMED_BLOB = "9512baaad8dfb8bf7e2bd89be5378d2ce4c09df4"
TRADEMIND_MALFORMED_BLOB = "d9b802fdd9ff8575ac2e32ec8bf619dbc5a91582"
KNOWN_MALFORMED_BLOBS = {HAL_MALFORMED_BLOB, TRADEMIND_MALFORMED_BLOB}

BLOB_REVIEW_COLUMNS = [
    "blob_oid",
    "representative_repo_name",
    "representative_path",
    "file_occurrences",
    "affected_snapshots",
    "source_byte_count",
    "source_encoding",
    "python312_version",
    "python312_ast_status",
    "python312_ast_error_type",
    "python312_ast_error_message",
    "python313_version",
    "python313_ast_status",
    "python313_ast_error_type",
    "python313_ast_error_message",
    "diagnostic_repair_id",
    "diagnostic_repair_description",
    "diagnostic_repair_ast_status",
    "diagnostic_repair_error_type",
    "diagnostic_repair_error_message",
    "recovery_method",
    "parser_used",
    "root_cause",
    "exact_original_source",
    "counterfactual_repair",
    "production_applied",
    "eligible_function_count",
    "extractable_function_count",
    "docstring_only_function_count",
    "qualifying_function_count",
    "token_py_all_function_bodies",
    "token_py_100_200",
    "resolution_status",
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
    "parser_used",
    "parser_version",
    "recovery_confidence",
    "counterfactual_repair",
    "diagnostic_repair_id",
    "production_applied",
    "raw_source_basis",
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
    "recovery_method",
    "parser_used",
    "parser_version",
    "root_cause",
    "exact_original_source",
    "counterfactual_repair",
    "diagnostic_repair_id",
    "production_applied",
    "diagnostic_function_count_all_delta",
    "diagnostic_function_count_extracted_delta",
    "diagnostic_function_count_100_200_delta",
    "diagnostic_function_count_docstring_only_delta",
    "diagnostic_function_count_with_nested_delta",
    "diagnostic_python_file_count_with_function_delta",
    "diagnostic_python_file_count_with_function_100_200_delta",
    "diagnostic_token_py_all_delta",
    "diagnostic_token_py_100_200_delta",
    "applied_function_count_all_delta",
    "applied_function_count_extracted_delta",
    "applied_function_count_100_200_delta",
    "applied_function_count_docstring_only_delta",
    "applied_function_count_with_nested_delta",
    "applied_python_file_count_with_function_delta",
    "applied_python_file_count_with_function_100_200_delta",
    "applied_token_py_all_delta",
    "applied_token_py_100_200_delta",
    "metric_impact_resolved",
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
    "metric_available_before_d01b",
    "affected_file_occurrences",
    "resolved_file_occurrences",
    "unresolved_file_occurrences",
    "python313_exact_file_occurrences",
    "malformed_diagnostic_file_occurrences",
    "malformed_applied_file_occurrences",
]
for _metric in METRIC_NAMES:
    SNAPSHOT_CORRECTION_COLUMNS.extend(
        [
            f"base_{_metric}_after_d01a",
            f"diagnostic_{_metric}_delta_d01b",
            f"applied_{_metric}_delta_d01b",
            f"diagnostic_{_metric}_after_d01b",
            f"production_{_metric}_after_d01b",
        ]
    )
SNAPSHOT_CORRECTION_COLUMNS.extend(
    [
        "metric_available_after_d01b",
        "resolution_status",
        "resolution_decision",
        "resolution_note",
    ]
)

UNRESOLVED_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
    "recovery_method",
    "root_cause",
    "diagnostic_repair_id",
    "diagnostic_token_py_100_200_delta",
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
    """Parse one file exactly under the worker interpreter.

    No lexical fallback and no source repair is performed here.  This makes
    the Python 3.12 versus Python 3.13 evidence explicit in the main process.
    """
    regex_lines = regex_named_function_lines(source)
    tokens, tokenizer_complete, token_error_type, token_error_message = collect_tokens(source)
    lexical_functions, _ = build_lexical_spans(source, tokens)
    ast_status = "success"
    ast_error_type = ""
    ast_error_message = ""
    records: list[WorkerFunction] = []
    try:
        ast_functions = index_ast_functions(source, path)
        records = ast_exact_records(source, ast_functions, lexical_functions)
    except Exception as exc:
        ast_status = "error"
        ast_error_type = type(exc).__name__
        ast_error_message = str(exc)
    return {
        "path": path,
        "ast_status": ast_status,
        "ast_error_type": ast_error_type,
        "ast_error_message": ast_error_message,
        "tokenizer_complete": tokenizer_complete,
        "tokenizer_error_type": token_error_type,
        "tokenizer_error_message": token_error_message,
        "regex_named_function_candidates": len(regex_lines),
        "indexed_named_function_headers": len(lexical_functions),
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
    save_enabled: bool,
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
    if not (0 <= start_offset <= body_start < end_offset <= len(source)):
        raise ValueError(
            "Mapped function offsets are invalid: "
            f"start={start_offset}, body={body_start}, end={end_offset}, length={len(source)}"
        )
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
    saved = False
    relative = ""
    absolute = ""
    if save_enabled:
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


@dataclass(frozen=True)
class SourceEdit:
    original_start: int
    original_end: int
    replacement: str
    description: str


def split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1:]
    return line, ""


def apply_source_edits(source: str, edits: Sequence[SourceEdit]) -> str:
    ordered = sorted(edits, key=lambda item: item.original_start)
    cursor = 0
    output: list[str] = []
    for edit in ordered:
        if edit.original_start < cursor or edit.original_end < edit.original_start:
            raise ValueError("Source edits overlap or contain invalid offsets")
        output.append(source[cursor:edit.original_start])
        output.append(edit.replacement)
        cursor = edit.original_end
    output.append(source[cursor:])
    return "".join(output)


def map_repaired_offset_to_original(offset: int, edits: Sequence[SourceEdit]) -> int:
    cumulative_delta = 0
    for edit in sorted(edits, key=lambda item: item.original_start):
        old_length = edit.original_end - edit.original_start
        new_length = len(edit.replacement)
        repaired_start = edit.original_start + cumulative_delta
        repaired_end = repaired_start + new_length
        if offset < repaired_start:
            break
        if repaired_start <= offset < repaired_end:
            relative = offset - repaired_start
            if new_length == old_length:
                return edit.original_start + min(relative, old_length)
            if old_length == 0:
                return edit.original_start
            return edit.original_start + min(
                old_length,
                int(round(relative * old_length / max(new_length, 1))),
            )
        cumulative_delta += new_length - old_length
    return offset - cumulative_delta


def map_worker_records_to_original(
    records: Sequence[dict[str, Any]],
    edits: Sequence[SourceEdit],
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        for field in (
            "function_start_offset",
            "function_end_offset",
            "body_start_offset",
        ):
            item[field] = map_repaired_offset_to_original(int(item[field]), edits)
        mapped.append(item)
    return mapped


def build_known_malformed_repair(
    blob_oid: str,
    path: str,
    source: str,
) -> tuple[str, str, list[SourceEdit]]:
    """Return a reviewed diagnostic repair for one known malformed blob."""
    lines = source.splitlines(keepends=True)
    line_starts: list[int] = []
    cursor = 0
    for line in lines:
        line_starts.append(cursor)
        cursor += len(line)

    if blob_oid == HAL_MALFORMED_BLOB:
        matches = [index for index, line in enumerate(lines) if split_line_ending(line)[0].strip() == "def update()"]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one malformed 'def update()' line in {path}; found {len(matches)}"
            )
        index = matches[0]
        content, ending = split_line_ending(lines[index])
        indent = content[: len(content) - len(content.lstrip(" \t"))]
        replacement_content = indent + "#" + " " * max(len(content) - len(indent) - 1, 0)
        if len(replacement_content) != len(content):
            raise ValueError("HAL diagnostic mask did not preserve line length")
        edit = SourceEdit(
            original_start=line_starts[index],
            original_end=line_starts[index] + len(lines[index]),
            replacement=replacement_content + ending,
            description="mask_invalid_def_update_without_colon_equal_length",
        )
        repaired = apply_source_edits(source, [edit])
        return "hal_mask_invalid_def_update", edit.description, [edit]

    if blob_oid == TRADEMIND_MALFORMED_BLOB:
        candidate_indexes: list[int] = []
        for index, line in enumerate(lines):
            content, _ = split_line_ending(line)
            if content.strip() != "patterns.append(TechnicalPattern(":
                continue
            previous = index - 1
            while previous >= 0 and not split_line_ending(lines[previous])[0].strip():
                previous -= 1
            if previous >= 0 and split_line_ending(lines[previous])[0].strip() == "else:":
                candidate_indexes.append(index)
        if len(candidate_indexes) != 1:
            raise ValueError(
                "Expected one under-indented patterns.append statement after else; "
                f"found {len(candidate_indexes)} in {path}"
            )
        index = candidate_indexes[0]
        edit = SourceEdit(
            original_start=line_starts[index],
            original_end=line_starts[index],
            replacement="    ",
            description="indent_patterns_append_four_spaces_after_else",
        )
        repaired = apply_source_edits(source, [edit])
        return "trademind_indent_else_body", edit.description, [edit]

    return "", "", []


def run_worker_batches(
    entries: list[dict[str, Any]],
    python_bin: str,
    script_path: Path,
    timeout_seconds: int,
    batch_byte_limit: int,
) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    batch: list[dict[str, Any]] = []
    batch_bytes = 0
    for entry in entries:
        size = int(entry["byte_count"])
        if batch and batch_bytes + size > batch_byte_limit:
            output.update(run_worker_batch(batch, python_bin, script_path, timeout_seconds))
            batch = []
            batch_bytes = 0
        batch.append(entry)
        batch_bytes += size
    if batch:
        output.update(run_worker_batch(batch, python_bin, script_path, timeout_seconds))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-manifest-file", type=Path, required=True)
    parser.add_argument("--d01a-snapshot-results-file", type=Path, required=True)
    parser.add_argument("--d01a-snapshot-corrections-file", type=Path, required=True)
    parser.add_argument("--d01a-unresolved-file", type=Path, required=True)
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
    parser.add_argument("--python312-bin", required=True)
    parser.add_argument("--python313-bin", required=True)
    parser.add_argument("--git-timeout-seconds", type=int, default=300)
    parser.add_argument("--worker-timeout-seconds", type=int, default=600)
    parser.add_argument("--worker-batch-bytes", type=int, default=20_000_000)
    parser.add_argument("--apply-reviewed-malformed", action="store_true")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--blob-oid", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-self-test", action="store_true")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def run_internal_self_test(
    python313_bin: str,
    script_path: Path,
    timeout_seconds: int,
) -> None:
    generic_source = """class Box[T, H: Hashable = int]:
    def value(self, item: T) -> T:
        return item
"""
    result = run_worker_batch(
        [{"request_index": 1, "path": "generic.py", "source": generic_source}],
        python313_bin,
        script_path,
        timeout_seconds,
    )[1]
    if result.get("ast_status") != "success" or len(result.get("records", [])) != 1:
        raise AssertionError("Python 3.13 generic-syntax AST self-test failed")

    hal_source = """class Cache:
    def __init__(self):
        self.value = 1
    def update()

class Model:
    def run(self):
        return 1
"""
    repair_id, _, edits = build_known_malformed_repair(
        HAL_MALFORMED_BLOB, "gpt_cached.py", hal_source
    )
    if repair_id != "hal_mask_invalid_def_update" or not edits:
        raise AssertionError("HAL repair self-test did not produce a plan")
    repaired = apply_source_edits(hal_source, edits)
    hal_result = run_worker_batch(
        [{"request_index": 2, "path": "gpt_cached.py", "source": repaired}],
        python313_bin,
        script_path,
        timeout_seconds,
    )[2]
    if hal_result.get("ast_status") != "success":
        raise AssertionError("HAL diagnostic repair self-test failed")

    trade_source = """class Analyzer:
    def analyze(self):
        if True:
            pass
        else:
        patterns.append(TechnicalPattern(
            name='x'
        ))

    def later(self):
        return 2
"""
    repair_id, _, edits = build_known_malformed_repair(
        TRADEMIND_MALFORMED_BLOB, "stock_analyzer_original_backup.py", trade_source
    )
    if repair_id != "trademind_indent_else_body" or not edits:
        raise AssertionError("TradeMind repair self-test did not produce a plan")
    repaired = apply_source_edits(trade_source, edits)
    trade_result = run_worker_batch(
        [{"request_index": 3, "path": "stock.py", "source": repaired}],
        python313_bin,
        script_path,
        timeout_seconds,
    )[3]
    if trade_result.get("ast_status") != "success":
        raise AssertionError("TradeMind diagnostic repair self-test failed")
    mapped = map_worker_records_to_original(trade_result.get("records", []), edits)
    if any(int(row["function_end_offset"]) > len(trade_source) for row in mapped):
        raise AssertionError("TradeMind repaired offsets were not mapped to original source")
    logging.info("Internal self-test: PASS")


def metric_base_after_d01a(
    correction_row: "pd.Series",
    result_row: "pd.Series",
    metric_name: str,
) -> int:
    corrected_name = f"corrected_{metric_name}"
    if corrected_name in correction_row.index and clean_text(correction_row.get(corrected_name, "")):
        return int_value(correction_row[corrected_name])
    partial_name = f"{metric_name}_partial"
    return int_value(result_row.get(partial_name, result_row.get(metric_name, 0)))


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    required_files = [
        args.snapshot_manifest_file,
        args.d01a_snapshot_results_file,
        args.d01a_snapshot_corrections_file,
        args.d01a_unresolved_file,
    ]
    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(path)
    args.body_store_root.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()

    python312_meta = inspect_ast_python(args.python312_bin, script_path, args.worker_timeout_seconds)
    python313_meta = inspect_ast_python(args.python313_bin, script_path, args.worker_timeout_seconds)
    if tuple(python312_meta["python_version_info"][:2]) != (3, 12):
        raise RuntimeError(
            f"PYTHON312_BIN must be Python 3.12.x, found {python312_meta['python_version']}"
        )
    if tuple(python313_meta["python_version_info"][:2]) != (3, 13):
        raise RuntimeError(
            f"PYTHON313_BIN must be Python 3.13.x, found {python313_meta['python_version']}"
        )
    logging.info(
        "AST workers: Python 3.12=%s; Python 3.13=%s",
        python312_meta["python_version"],
        python313_meta["python_version"],
    )
    if not args.skip_self_test:
        run_internal_self_test(args.python313_bin, script_path, args.worker_timeout_seconds)

    manifest = pd.read_csv(args.snapshot_manifest_file, low_memory=False)
    results = pd.read_csv(args.d01a_snapshot_results_file, low_memory=False)
    d01a_corrections = pd.read_csv(args.d01a_snapshot_corrections_file, low_memory=False)
    unresolved = pd.read_csv(args.d01a_unresolved_file, low_memory=False)

    required_manifest = {"snapshot_key", "clone_path", "dataset_source", "repo_name"}
    required_results = {"snapshot_key", "metric_available", "repo_month_rows"}
    required_unresolved = {
        "snapshot_key", "dataset_source", "repo_name", "commit_sha", "path", "blob_oid"
    }
    for label, frame, required in (
        ("manifest", manifest, required_manifest),
        ("D01a results", results, required_results),
        ("D01a unresolved", unresolved, required_unresolved),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} is missing required columns: {missing}")

    issue_occurrences = unresolved.drop_duplicates(ISSUE_KEY_COLUMNS, keep="first").copy()
    issue_occurrences["original_issue_stage"] = issue_occurrences.get(
        "original_issue_stage", "raw_file_parse"
    )
    if args.repo_name:
        issue_occurrences = issue_occurrences[issue_occurrences["repo_name"].astype(str).eq(args.repo_name)]
    if args.blob_oid:
        issue_occurrences = issue_occurrences[issue_occurrences["blob_oid"].astype(str).eq(args.blob_oid)]
    issue_occurrences = issue_occurrences.sort_values(
        ["repo_name", "blob_oid", "snapshot_key", "path"]
    ).reset_index(drop=True)
    if args.limit > 0:
        selected = set(issue_occurrences["blob_oid"].astype(str).drop_duplicates().head(args.limit))
        issue_occurrences = issue_occurrences[
            issue_occurrences["blob_oid"].astype(str).isin(selected)
        ].copy()
    if issue_occurrences.empty:
        raise ValueError("No D01a unresolved occurrences matched the requested filters")

    manifest_map = manifest.drop_duplicates("snapshot_key").set_index("snapshot_key", drop=False)
    result_map = results.drop_duplicates("snapshot_key").set_index("snapshot_key", drop=False)
    correction_map = d01a_corrections.drop_duplicates("snapshot_key").set_index(
        "snapshot_key", drop=False
    )
    missing_manifest_keys = sorted(
        set(issue_occurrences["snapshot_key"].astype(str)) - set(manifest_map.index.astype(str))
    )
    if missing_manifest_keys:
        raise ValueError(f"Unresolved snapshots missing from manifest: {missing_manifest_keys[:5]}")

    unique_blob_rows = issue_occurrences.drop_duplicates("blob_oid", keep="first").reset_index(drop=True)
    blob_sources: dict[str, dict[str, Any]] = {}
    original_entries: list[dict[str, Any]] = []
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
            "request_index": int(request_index),
        }
        original_entries.append(
            {
                "request_index": int(request_index),
                "path": str(row["path"]),
                "source": source,
                "byte_count": len(source.encode("utf-8")),
            }
        )

    logging.info(
        "Selected D01a unresolved scope: unique_blobs=%d; file_occurrences=%d; snapshots=%d",
        len(unique_blob_rows),
        len(issue_occurrences),
        issue_occurrences["snapshot_key"].nunique(),
    )
    python312_results = run_worker_batches(
        original_entries,
        args.python312_bin,
        script_path,
        args.worker_timeout_seconds,
        args.worker_batch_bytes,
    )
    python313_entries = [
        entry
        for entry in original_entries
        if python312_results[int(entry["request_index"])].get("ast_status") != "success"
    ]
    python313_results = run_worker_batches(
        python313_entries,
        args.python313_bin,
        script_path,
        args.worker_timeout_seconds,
        args.worker_batch_bytes,
    ) if python313_entries else {}

    repaired_entries: list[dict[str, Any]] = []
    repair_plans: dict[int, dict[str, Any]] = {}
    for _, row in unique_blob_rows.iterrows():
        blob_oid = str(row["blob_oid"])
        info = blob_sources[blob_oid]
        request_index = int(info["request_index"])
        result312 = python312_results[request_index]
        result313 = python313_results.get(request_index, {})
        if result312.get("ast_status") == "success" or result313.get("ast_status") == "success":
            continue
        repair_id, description, edits = build_known_malformed_repair(
            blob_oid, str(row["path"]), info["source"]
        )
        if not edits:
            continue
        repaired_source = apply_source_edits(info["source"], edits)
        repair_plans[request_index] = {
            "repair_id": repair_id,
            "description": description,
            "edits": edits,
            "source": repaired_source,
        }
        repaired_entries.append(
            {
                "request_index": request_index,
                "path": str(row["path"]),
                "source": repaired_source,
                "byte_count": len(repaired_source.encode("utf-8")),
            }
        )
    repaired_results = run_worker_batches(
        repaired_entries,
        args.python313_bin,
        script_path,
        args.worker_timeout_seconds,
        args.worker_batch_bytes,
    ) if repaired_entries else {}

    blob_analysis: dict[str, dict[str, Any]] = {}
    blob_review_rows: list[dict[str, Any]] = []
    for _, row in unique_blob_rows.iterrows():
        blob_oid = str(row["blob_oid"])
        source_info = blob_sources[blob_oid]
        request_index = int(source_info["request_index"])
        result312 = python312_results[request_index]
        result313 = python313_results.get(request_index, {})
        repair_plan = repair_plans.get(request_index, {})
        repair_result = repaired_results.get(request_index, {})

        records: list[dict[str, Any]] = []
        method = "unresolved"
        parser_used = ""
        parser_version = ""
        root_cause = "unclassified_parse_failure"
        exact_original = False
        counterfactual = False
        production_applied = False
        repair_id = str(repair_plan.get("repair_id", ""))
        repair_description = str(repair_plan.get("description", ""))

        if result312.get("ast_status") == "success":
            records = list(result312.get("records", []))
            method = "python312_ast_exact"
            parser_used = "python312"
            parser_version = python312_meta["python_version"]
            root_cause = "python312_supported_source"
            exact_original = True
            production_applied = True
        elif result313.get("ast_status") == "success":
            records = list(result313.get("records", []))
            method = "python313_ast_exact"
            parser_used = "python313"
            parser_version = python313_meta["python_version"]
            root_cause = "python313_syntax_parser_version_mismatch"
            exact_original = True
            production_applied = True
        elif repair_result.get("ast_status") == "success":
            records = map_worker_records_to_original(
                list(repair_result.get("records", [])),
                repair_plan["edits"],
            )
            method = "reviewed_malformed_diagnostic_repair"
            parser_used = "python313_repaired_layout"
            parser_version = python313_meta["python_version"]
            root_cause = "malformed_historical_source"
            counterfactual = True
            production_applied = bool(args.apply_reviewed_malformed)
        requires_review = not production_applied
        status = "resolved" if production_applied else "pending_review"

        extracted = [record for record in records if record.get("extraction_status") == "success"]
        docstring_only = [
            record for record in records
            if record.get("extraction_status") == "no_body_after_docstring"
        ]
        token_all = 0
        token_range = 0
        qualifying = 0
        for record in extracted:
            body = source_info["source"][
                int(record["body_start_offset"]):int(record["function_end_offset"])
            ]
            count = len(body.split(" "))
            token_all += count
            if TOKEN_MIN <= count <= TOKEN_MAX:
                token_range += count
                qualifying += 1

        matching = issue_occurrences[
            issue_occurrences["blob_oid"].astype(str).eq(blob_oid)
        ]
        blob_review_rows.append(
            {
                "blob_oid": blob_oid,
                "representative_repo_name": row["repo_name"],
                "representative_path": row["path"],
                "file_occurrences": len(matching),
                "affected_snapshots": matching["snapshot_key"].nunique(),
                "source_byte_count": len(source_info["data"]),
                "source_encoding": source_info["encoding"],
                "python312_version": python312_meta["python_version"],
                "python312_ast_status": result312.get("ast_status", "error"),
                "python312_ast_error_type": result312.get("ast_error_type", ""),
                "python312_ast_error_message": result312.get("ast_error_message", ""),
                "python313_version": python313_meta["python_version"],
                "python313_ast_status": result313.get("ast_status", "not_run"),
                "python313_ast_error_type": result313.get("ast_error_type", ""),
                "python313_ast_error_message": result313.get("ast_error_message", ""),
                "diagnostic_repair_id": repair_id,
                "diagnostic_repair_description": repair_description,
                "diagnostic_repair_ast_status": repair_result.get("ast_status", "not_run"),
                "diagnostic_repair_error_type": repair_result.get("ast_error_type", ""),
                "diagnostic_repair_error_message": repair_result.get("ast_error_message", ""),
                "recovery_method": method,
                "parser_used": parser_used,
                "root_cause": root_cause,
                "exact_original_source": exact_original,
                "counterfactual_repair": counterfactual,
                "production_applied": production_applied,
                "eligible_function_count": len(records),
                "extractable_function_count": len(extracted),
                "docstring_only_function_count": len(docstring_only),
                "qualifying_function_count": qualifying,
                "token_py_all_function_bodies": token_all,
                "token_py_100_200": token_range,
                "resolution_status": status,
                "requires_review": requires_review,
                "notes": (
                    "Exact parser recovery uses the unmodified historical source."
                    if exact_original
                    else "Diagnostic AST boundaries come from a reviewed repair; all hashes and token counts use the original historical source."
                    if counterfactual
                    else "No approved recovery was found."
                ),
            }
        )
        blob_analysis[blob_oid] = {
            "source": source_info["source"],
            "records": records,
            "method": method,
            "parser_used": parser_used,
            "parser_version": parser_version,
            "root_cause": root_cause,
            "exact_original": exact_original,
            "counterfactual": counterfactual,
            "production_applied": production_applied,
            "repair_id": repair_id,
        }

    recovered_details: list[dict[str, Any]] = []
    file_resolution_rows: list[dict[str, Any]] = []
    for _, occurrence in issue_occurrences.iterrows():
        snapshot_key = str(occurrence["snapshot_key"])
        blob_oid = str(occurrence["blob_oid"])
        path = str(occurrence["path"])
        manifest_row = manifest_map.loc[snapshot_key]
        analysis = blob_analysis[blob_oid]
        source = analysis["source"]
        records = list(analysis["records"])
        production_applied = bool(analysis["production_applied"])
        metadata = {
            "snapshot_key": snapshot_key,
            "dataset_source": occurrence["dataset_source"],
            "repo_name": occurrence["repo_name"],
            "commit_sha": occurrence["commit_sha"],
            "path": path,
            "blob_oid": blob_oid,
            "blob_size": len(blob_sources[blob_oid]["data"]),
            "original_issue_stage": occurrence.get("original_issue_stage", "raw_file_parse"),
            "recovery_method": analysis["method"],
            "parser_used": analysis["parser_used"],
            "parser_version": analysis["parser_version"],
            "recovery_confidence": "exact_original_source" if analysis["exact_original"] else "reviewed_diagnostic_repair",
            "counterfactual_repair": analysis["counterfactual"],
            "diagnostic_repair_id": analysis["repair_id"],
            "production_applied": production_applied,
            "raw_source_basis": "original_historical_blob",
        }
        details = [
            process_worker_record(
                source,
                record,
                metadata,
                args.body_store_root,
                args.body_save_scope,
                save_enabled=production_applied and not args.dry_run,
            )
            for record in records
        ]
        recovered_details.extend(details)
        success = [row for row in details if row["extraction_status"] == "success"]
        docstring_only = [
            row for row in details if row["extraction_status"] == "no_body_after_docstring"
        ]
        qualifying = [row for row in success if bool_value(row["qualifies_100_200"])]
        diagnostic = {
            "function_count_all": len(records),
            "function_count_extracted": len(success),
            "function_count_100_200": len(qualifying),
            "function_count_docstring_only": len(docstring_only),
            "function_count_with_nested": sum(
                int(bool_value(row["contains_nested_named_definition"])) for row in details
            ),
            "python_file_count_with_function": int(bool(records)),
            "python_file_count_with_function_100_200": int(bool(qualifying)),
            "token_py_all": sum(int_value(row["token_count"]) for row in success),
            "token_py_100_200": sum(int_value(row["token_count"]) for row in qualifying),
        }
        applied = {
            key: value if production_applied else 0 for key, value in diagnostic.items()
        }
        metric_resolved = production_applied
        status = "resolved" if metric_resolved else "pending_review"
        note = (
            "Recovered exactly from the original source with Python 3.13."
            if analysis["method"] == "python313_ast_exact"
            else "Recovered exactly from the original source with Python 3.12."
            if analysis["method"] == "python312_ast_exact"
            else "Reviewed malformed-source diagnostic was production-applied; token counts use original raw source."
            if production_applied and analysis["counterfactual"]
            else "Reviewed malformed-source diagnostic is available but production application is pending."
            if analysis["counterfactual"]
            else "No recovery was available."
        )
        file_resolution_rows.append(
            {
                "snapshot_key": snapshot_key,
                "dataset_source": occurrence["dataset_source"],
                "repo_name": occurrence["repo_name"],
                "commit_sha": occurrence["commit_sha"],
                "path": path,
                "blob_oid": blob_oid,
                "blob_size": len(blob_sources[blob_oid]["data"]),
                "original_issue_stage": occurrence.get("original_issue_stage", "raw_file_parse"),
                "recovery_method": analysis["method"],
                "parser_used": analysis["parser_used"],
                "parser_version": analysis["parser_version"],
                "root_cause": analysis["root_cause"],
                "exact_original_source": analysis["exact_original"],
                "counterfactual_repair": analysis["counterfactual"],
                "diagnostic_repair_id": analysis["repair_id"],
                "production_applied": production_applied,
                "diagnostic_function_count_all_delta": diagnostic["function_count_all"],
                "diagnostic_function_count_extracted_delta": diagnostic["function_count_extracted"],
                "diagnostic_function_count_100_200_delta": diagnostic["function_count_100_200"],
                "diagnostic_function_count_docstring_only_delta": diagnostic["function_count_docstring_only"],
                "diagnostic_function_count_with_nested_delta": diagnostic["function_count_with_nested"],
                "diagnostic_python_file_count_with_function_delta": diagnostic["python_file_count_with_function"],
                "diagnostic_python_file_count_with_function_100_200_delta": diagnostic["python_file_count_with_function_100_200"],
                "diagnostic_token_py_all_delta": diagnostic["token_py_all"],
                "diagnostic_token_py_100_200_delta": diagnostic["token_py_100_200"],
                "applied_function_count_all_delta": applied["function_count_all"],
                "applied_function_count_extracted_delta": applied["function_count_extracted"],
                "applied_function_count_100_200_delta": applied["function_count_100_200"],
                "applied_function_count_docstring_only_delta": applied["function_count_docstring_only"],
                "applied_function_count_with_nested_delta": applied["function_count_with_nested"],
                "applied_python_file_count_with_function_delta": applied["python_file_count_with_function"],
                "applied_python_file_count_with_function_100_200_delta": applied["python_file_count_with_function_100_200"],
                "applied_token_py_all_delta": applied["token_py_all"],
                "applied_token_py_100_200_delta": applied["token_py_100_200"],
                "metric_impact_resolved": metric_resolved,
                "resolution_status": status,
                "resolution_note": note,
            }
        )

    blob_review = pd.DataFrame(blob_review_rows)
    recovered_detail_frame = pd.DataFrame(recovered_details)
    file_resolutions = pd.DataFrame(file_resolution_rows)
    resolved_results = results.copy()
    for column in (
        "snapshot_status", "resolution_decision", "resolution_note", "error_stage", "error_message"
    ):
        if column in resolved_results.columns:
            resolved_results[column] = resolved_results[column].fillna("").astype("object")

    d01b_extra_defaults: dict[str, Any] = {
        "d01b_implementation_version": "",
        "d01b_resolution_status": "",
        "d01b_recovery_methods": "",
        "d01b_affected_file_occurrences": 0,
        "d01b_resolved_file_occurrences": 0,
        "d01b_unresolved_file_occurrences": 0,
        "d01b_python313_exact_file_occurrences": 0,
        "d01b_malformed_diagnostic_file_occurrences": 0,
        "d01b_malformed_applied_file_occurrences": 0,
        "d01b_token_py_100_200_diagnostic_delta": 0,
        "d01b_token_py_100_200_applied_delta": 0,
        "token_py_100_200_partial_after_d01b": pd.NA,
        "diagnostic_token_py_100_200_after_d01b": pd.NA,
        "failed_python_file_count_after_d01b": pd.NA,
        "d01b_resolution_note": "",
    }
    for column, default in d01b_extra_defaults.items():
        if column not in resolved_results.columns:
            resolved_results[column] = default

    correction_rows: list[dict[str, Any]] = []
    for snapshot_key, group in file_resolutions.groupby("snapshot_key", sort=False):
        result_row = result_map.loc[snapshot_key]
        if snapshot_key not in correction_map.index:
            raise ValueError(f"Snapshot is missing from D01a corrections: {snapshot_key}")
        d01a_row = correction_map.loc[snapshot_key]
        diagnostic_deltas = {
            "function_count_py_all": int(group["diagnostic_function_count_all_delta"].sum()),
            "function_count_py_extracted": int(group["diagnostic_function_count_extracted_delta"].sum()),
            "function_count_py_100_200": int(group["diagnostic_function_count_100_200_delta"].sum()),
            "function_count_py_docstring_only": int(group["diagnostic_function_count_docstring_only_delta"].sum()),
            "function_count_py_with_nested": int(group["diagnostic_function_count_with_nested_delta"].sum()),
            "python_file_count_with_function": int(group["diagnostic_python_file_count_with_function_delta"].sum()),
            "python_file_count_with_function_100_200": int(group["diagnostic_python_file_count_with_function_100_200_delta"].sum()),
            "token_py_all_function_bodies": int(group["diagnostic_token_py_all_delta"].sum()),
            "token_py_100_200": int(group["diagnostic_token_py_100_200_delta"].sum()),
        }
        applied_deltas = {
            "function_count_py_all": int(group["applied_function_count_all_delta"].sum()),
            "function_count_py_extracted": int(group["applied_function_count_extracted_delta"].sum()),
            "function_count_py_100_200": int(group["applied_function_count_100_200_delta"].sum()),
            "function_count_py_docstring_only": int(group["applied_function_count_docstring_only_delta"].sum()),
            "function_count_py_with_nested": int(group["applied_function_count_with_nested_delta"].sum()),
            "python_file_count_with_function": int(group["applied_python_file_count_with_function_delta"].sum()),
            "python_file_count_with_function_100_200": int(group["applied_python_file_count_with_function_100_200_delta"].sum()),
            "token_py_all_function_bodies": int(group["applied_token_py_all_delta"].sum()),
            "token_py_100_200": int(group["applied_token_py_100_200_delta"].sum()),
        }
        bases = {
            metric: metric_base_after_d01a(d01a_row, result_row, metric)
            for metric in METRIC_NAMES
        }
        diagnostic_after = {
            metric: bases[metric] + diagnostic_deltas[metric] for metric in METRIC_NAMES
        }
        production_after = {
            metric: bases[metric] + applied_deltas[metric] for metric in METRIC_NAMES
        }
        affected_count = len(group)
        resolved_count = int(group["metric_impact_resolved"].map(bool_value).sum())
        unresolved_count = affected_count - resolved_count
        available = unresolved_count == 0
        status = "resolved_after_d01b" if available else "partial_needs_review_after_d01b"
        decision = "resolved_full" if available else "pending_review"
        methods = " | ".join(sorted(set(group["recovery_method"].astype(str))))
        note = (
            f"resolved_files={resolved_count}/{affected_count}; "
            f"applied_token_delta={applied_deltas['token_py_100_200']}; "
            f"diagnostic_token_delta={diagnostic_deltas['token_py_100_200']}"
        )
        correction = {
            "manifest_order": result_row.get("manifest_order", ""),
            "snapshot_key": snapshot_key,
            "dataset_source": result_row["dataset_source"],
            "repo_name": result_row["repo_name"],
            "commit_sha": result_row["commit_sha"],
            "repo_month_rows": int_value(result_row["repo_month_rows"]),
            "metric_available_before_d01b": bool_value(result_row["metric_available"]),
            "affected_file_occurrences": affected_count,
            "resolved_file_occurrences": resolved_count,
            "unresolved_file_occurrences": unresolved_count,
            "python313_exact_file_occurrences": int(group["recovery_method"].eq("python313_ast_exact").sum()),
            "malformed_diagnostic_file_occurrences": int(group["counterfactual_repair"].map(bool_value).sum()),
            "malformed_applied_file_occurrences": int(
                (group["counterfactual_repair"].map(bool_value) & group["production_applied"].map(bool_value)).sum()
            ),
            "metric_available_after_d01b": available,
            "resolution_status": status,
            "resolution_decision": decision,
            "resolution_note": note,
        }
        for metric in METRIC_NAMES:
            correction[f"base_{metric}_after_d01a"] = bases[metric]
            correction[f"diagnostic_{metric}_delta_d01b"] = diagnostic_deltas[metric]
            correction[f"applied_{metric}_delta_d01b"] = applied_deltas[metric]
            correction[f"diagnostic_{metric}_after_d01b"] = diagnostic_after[metric]
            correction[f"production_{metric}_after_d01b"] = production_after[metric]
        correction_rows.append(correction)

        mask = resolved_results["snapshot_key"].astype(str).eq(snapshot_key)
        resolved_results.loc[mask, "d01b_implementation_version"] = IMPLEMENTATION_VERSION
        resolved_results.loc[mask, "d01b_resolution_status"] = status
        resolved_results.loc[mask, "d01b_recovery_methods"] = methods
        resolved_results.loc[mask, "d01b_affected_file_occurrences"] = affected_count
        resolved_results.loc[mask, "d01b_resolved_file_occurrences"] = resolved_count
        resolved_results.loc[mask, "d01b_unresolved_file_occurrences"] = unresolved_count
        resolved_results.loc[mask, "d01b_python313_exact_file_occurrences"] = correction["python313_exact_file_occurrences"]
        resolved_results.loc[mask, "d01b_malformed_diagnostic_file_occurrences"] = correction["malformed_diagnostic_file_occurrences"]
        resolved_results.loc[mask, "d01b_malformed_applied_file_occurrences"] = correction["malformed_applied_file_occurrences"]
        resolved_results.loc[mask, "d01b_token_py_100_200_diagnostic_delta"] = diagnostic_deltas["token_py_100_200"]
        resolved_results.loc[mask, "d01b_token_py_100_200_applied_delta"] = applied_deltas["token_py_100_200"]
        resolved_results.loc[mask, "token_py_100_200_partial_after_d01b"] = production_after["token_py_100_200"]
        resolved_results.loc[mask, "diagnostic_token_py_100_200_after_d01b"] = diagnostic_after["token_py_100_200"]
        resolved_results.loc[mask, "failed_python_file_count_after_d01b"] = unresolved_count
        resolved_results.loc[mask, "d01b_resolution_note"] = note
        resolved_results.loc[mask, "snapshot_status"] = status
        resolved_results.loc[mask, "resolution_decision"] = decision
        resolved_results.loc[mask, "resolution_note"] = note
        if available:
            for metric, value in production_after.items():
                resolved_results.loc[mask, metric] = value
            resolved_results.loc[mask, "metric_available"] = True
            resolved_results.loc[mask, "partial_metric_accepted"] = False
            resolved_results.loc[mask, "error_stage"] = ""
            resolved_results.loc[mask, "error_message"] = ""
        else:
            resolved_results.loc[mask, "metric_available"] = False
            for metric in METRIC_NAMES:
                resolved_results.loc[mask, metric] = pd.NA

    corrections = pd.DataFrame(correction_rows)
    unresolved_files = file_resolutions[
        ~file_resolutions["metric_impact_resolved"].map(bool_value)
    ].copy()
    unresolved_frame = pd.DataFrame(
        [
            {
                "snapshot_key": row["snapshot_key"],
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "commit_sha": row["commit_sha"],
                "path": row["path"],
                "blob_oid": row["blob_oid"],
                "recovery_method": row["recovery_method"],
                "root_cause": row["root_cause"],
                "diagnostic_repair_id": row["diagnostic_repair_id"],
                "diagnostic_token_py_100_200_delta": row["diagnostic_token_py_100_200_delta"],
                "resolution_status": row["resolution_status"],
                "resolution_note": row["resolution_note"],
            }
            for _, row in unresolved_files.iterrows()
        ]
    )
    decisions = corrections[
        ["snapshot_key", "resolution_decision", "resolution_note"]
    ].copy()

    qc_rows: list[dict[str, Any]] = []
    def add_qc(name: str, observed: Any, expected: Any, status: str, note: str = "") -> None:
        qc_rows.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    add_qc(
        "unique_blobs_reviewed",
        len(blob_review),
        issue_occurrences["blob_oid"].nunique(),
        "pass" if len(blob_review) == issue_occurrences["blob_oid"].nunique() else "fail",
    )
    add_qc(
        "file_occurrences_resolved",
        int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()),
        len(file_resolutions),
        "pass" if unresolved_frame.empty else "warn",
    )
    add_qc(
        "python313_exact_blobs",
        int(blob_review["recovery_method"].eq("python313_ast_exact").sum()),
        "source-dependent",
        "pass",
        "Exact Python 3.13 recovery uses the unmodified historical blob.",
    )
    malformed_rows = blob_review[blob_review["counterfactual_repair"].map(bool_value)]
    add_qc(
        "known_malformed_blobs_only",
        sorted(malformed_rows["blob_oid"].astype(str).tolist()),
        sorted(KNOWN_MALFORMED_BLOBS),
        "pass" if set(malformed_rows["blob_oid"].astype(str)).issubset(KNOWN_MALFORMED_BLOBS) else "fail",
    )
    exact_counterfactual = blob_review[
        blob_review["recovery_method"].isin(["python312_ast_exact", "python313_ast_exact"])
        & blob_review["counterfactual_repair"].map(bool_value)
    ]
    add_qc("exact_recovery_counterfactual_rows", len(exact_counterfactual), 0, "pass" if exact_counterfactual.empty else "fail")
    duplicate_body_keys = 0
    if not recovered_detail_frame.empty:
        nonempty_keys = recovered_detail_frame[
            recovered_detail_frame["body_key"].fillna("").astype(str).ne("")
        ]
        duplicate_body_keys = int(nonempty_keys["body_key"].duplicated().sum())
    add_qc("duplicate_recovered_body_keys", duplicate_body_keys, 0, "pass" if duplicate_body_keys == 0 else "fail")
    add_qc(
        "resolved_snapshot_result_rows",
        len(resolved_results),
        len(results),
        "pass" if len(resolved_results) == len(results) else "fail",
    )
    negative = 0
    for metric in METRIC_NAMES:
        values = pd.to_numeric(corrections[f"production_{metric}_after_d01b"], errors="coerce")
        negative += int((values < 0).sum())
    add_qc("negative_production_metrics", negative, 0, "pass" if negative == 0 else "fail")
    add_qc(
        "remaining_unresolved_file_occurrences",
        len(unresolved_frame),
        0,
        "pass" if unresolved_frame.empty else "warn",
        "Use --apply-reviewed-malformed only after accepting the two explicit diagnostic repairs.",
    )
    qc = pd.DataFrame(qc_rows)

    summary_rows: list[dict[str, Any]] = []
    def add_summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_rows.append(
            {"section": section, "metric": metric, "value": value, "note": note}
        )

    available_before = int(results["metric_available"].map(bool_value).sum())
    available_after = int(resolved_results["metric_available"].map(bool_value).sum())
    repo_months_after = int(
        pd.to_numeric(
            resolved_results.loc[resolved_results["metric_available"].map(bool_value), "repo_month_rows"],
            errors="coerce",
        ).fillna(0).sum()
    )
    add_summary("implementation", "version", IMPLEMENTATION_VERSION)
    add_summary("implementation", "experiment", EXPERIMENT_NAME)
    add_summary("implementation", "main_python", sys.version.split()[0])
    add_summary("implementation", "python312", python312_meta["python_version"])
    add_summary("implementation", "python313", python313_meta["python_version"])
    add_summary("definition", "token_definition", TOKEN_DEFINITION)
    add_summary("definition", "apply_reviewed_malformed", int(args.apply_reviewed_malformed))
    add_summary("input", "unresolved_file_occurrences", len(issue_occurrences))
    add_summary("input", "unique_unresolved_blobs", issue_occurrences["blob_oid"].nunique())
    add_summary("result", "python313_exact_blobs", int(blob_review["recovery_method"].eq("python313_ast_exact").sum()))
    add_summary("result", "malformed_diagnostic_blobs", int(blob_review["counterfactual_repair"].map(bool_value).sum()))
    add_summary("result", "resolved_file_occurrences", int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()))
    add_summary("result", "unresolved_file_occurrences", len(unresolved_frame))
    add_summary("result", "available_snapshots_before", available_before)
    add_summary("result", "available_snapshots_after", available_after)
    add_summary("result", "available_repo_months_after", repo_months_after)
    add_summary("result", "diagnostic_token_py_100_200_delta", int(file_resolutions["diagnostic_token_py_100_200_delta"].sum()))
    add_summary("result", "applied_token_py_100_200_delta", int(file_resolutions["applied_token_py_100_200_delta"].sum()))
    add_summary("result", "recovered_function_detail_rows", len(recovered_detail_frame))
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
        "Completed run-x-d01b-v1: blobs=%d; file_occurrences=%d; resolved=%d; unresolved=%d; available_snapshots=%d/%d; applied_token_delta=%d",
        issue_occurrences["blob_oid"].nunique(),
        len(file_resolutions),
        int(file_resolutions["metric_impact_resolved"].map(bool_value).sum()),
        len(unresolved_frame),
        available_after,
        len(resolved_results),
        int(file_resolutions["applied_token_py_100_200_delta"].sum()),
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
        logging.exception("run-x-d01b failed: %s", exc)
        raise SystemExit(1)
