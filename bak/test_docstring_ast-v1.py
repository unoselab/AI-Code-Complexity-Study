#!/usr/bin/env python3
"""Demonstrate how Python AST distinguishes docstrings from ordinary strings."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DOCSTRING_PARENTS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class StringRecord:
    kind: str
    start_line: int
    end_line: int
    source_text: str


def is_string_expression(node: ast.AST) -> bool:
    """Return True when a node is a standalone string expression."""
    if not isinstance(node, ast.Expr):
        return False
    value = node.value
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def iter_docstring_nodes(tree: ast.AST) -> Iterable[ast.Expr]:
    """Yield AST expression nodes that Python recognizes structurally as docstrings."""
    for parent in ast.walk(tree):
        if not isinstance(parent, DOCSTRING_PARENTS):
            continue
        body = getattr(parent, "body", None)
        if body and is_string_expression(body[0]):
            yield body[0]


def classify_strings(source: str) -> list[StringRecord]:
    """Classify string literals as docstrings or ordinary strings."""
    tree = ast.parse(source)
    source_lines = source.splitlines()

    docstring_node_ids = {id(node) for node in iter_docstring_nodes(tree)}
    records: list[StringRecord] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue

        parent_expr = None
        for candidate in ast.walk(tree):
            if isinstance(candidate, ast.Expr) and candidate.value is node:
                parent_expr = candidate
                break

        is_docstring = parent_expr is not None and id(parent_expr) in docstring_node_ids
        kind = "docstring" if is_docstring else "ordinary_string"

        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno)
        snippet = "\n".join(source_lines[start_line - 1 : end_line])
        records.append(
            StringRecord(
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                source_text=snippet,
            )
        )

    return sorted(records, key=lambda item: (item.start_line, item.end_line, item.kind))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show how AST distinguishes a docstring from an assigned multiline string."
    )
    parser.add_argument("input_file", type=Path, help="Python source file to analyze")
    args = parser.parse_args()

    source = args.input_file.read_text(encoding="utf-8")
    records = classify_strings(source)

    print(f"Input: {args.input_file}")
    print(f"String literals found: {len(records)}")
    print()

    for index, record in enumerate(records, start=1):
        print(
            f"[{index}] kind={record.kind} "
            f"lines={record.start_line}-{record.end_line}"
        )
        for line in record.source_text.splitlines():
            print(f"    {line}")
        print()

    expected = [
        ("docstring", 2, 5),
        ("ordinary_string", 6, 8),
    ]
    observed = [(item.kind, item.start_line, item.end_line) for item in records]

    if observed != expected:
        raise AssertionError(f"Unexpected classification: {observed!r}")

    print("PASS: AST distinguished the function docstring from the assigned multiline string.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
