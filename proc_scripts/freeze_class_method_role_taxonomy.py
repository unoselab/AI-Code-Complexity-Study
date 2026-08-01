#!/usr/bin/env python3
"""Freeze the testing/boilerplate/other taxonomy for class methods.

This stage reads the completed run-py-7f12 empirical inventory and assigns
every retained body-month unit to exactly one group:

1. testing: testing-related class methods and test-support methods;
2. boilerplate: non-testing methods matching a conservative AST rule;
3. other: every retained method not assigned to testing or boilerplate.

Testing keeps the previously frozen regular-function name/path rule and adds
only strong class-specific evidence. Generic class-base tokens containing
``test`` are not evidence because names such as ``BBoxTestMixin`` represent
model inference rather than software testing.

Testing has first priority, boilerplate second, and other is the remainder.
Therefore Category 4 = Category 5 + Category 6 + Category 7. Exact Git blobs
are read again because run-py-7f12 intentionally preserved raw features rather
than a semantic boilerplate taxonomy. Lexically nested/local-class methods are
excluded. This script creates no repository-month outcome and computes no ATT.
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
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_VERSION = "run-py-7f13-v2"
UPSTREAM_SCRIPT_VERSION = "run-py-7f12-v2"
TAXONOMY_STATUS = "FROZEN_PARTITION"
TAXONOMY_VERSION = "class-method-testing-boilerplate-other-v1"

KEY_COLUMNS = ["dataset_source", "repo_name", "time", "function_body_sha256"]
GROUPS = ["testing", "boilerplate", "other"]
GROUP_LABELS = {
    "testing": "Testing-related synchronous class methods",
    "boilerplate": "Boilerplate synchronous class methods",
    "other": "Other synchronous class methods",
}

BOILERPLATE_RULE_LABELS = {
    "attribute_binding_constructor": "Attribute-binding constructor",
    "super_delegating_constructor": "Super-delegating constructor",
    "property_accessor": "Property getter or setter",
    "representation": "Representation method",
    "comparison_or_hashing": "Comparison or hashing method",
    "container_protocol": "Container protocol delegation",
    "context_manager": "Context-manager boilerplate",
    "serialization": "Serialization boilerplate",
    "factory": "Class factory",
    "delegation_pass_through": "Same-name delegation or pass-through",
    "stub_abstract": "Stub or abstract method",
}

TEST_PATH_TOKENS = {"test", "tests", "testing"}
TEST_LIFECYCLE_NORMALIZED_NAMES = {
    "setup",
    "teardown",
    "setupclass",
    "teardownclass",
    "setupmethod",
    "teardownmethod",
    "setupmodule",
    "teardownmodule",
}

SIGNAL_COLUMNS = [
    "test_name",
    "test_path",
    "test_class_name",
    "test_lifecycle_name",
    "testcase_base",
    "test_framework_decorator",
]

EVENT_REQUIRED_COLUMNS = {
    *KEY_COLUMNS,
    "function_event_id",
    "function_name",
    "relative_path",
    "is_nested_function",
    "containing_class_name",
    "class_base_names",
    "method_decorator_callables",
    "time_to_event",
    "treatment_period",
    "git_repo_dir",
    "git_source_label",
    "git_function_name",
    "method_definition_line",
}

BODY_REQUIRED_COLUMNS = {
    *KEY_COLUMNS,
    "time_to_event",
    "treatment_period",
    "event_context_count",
    "function_names",
    "qualified_function_names",
    "relative_paths",
}

ASSIGNMENT_COLUMNS = [
    *KEY_COLUMNS,
    "time_to_event",
    "treatment_period",
    "event_context_count",
    "function_names",
    "qualified_function_names",
    "relative_paths",
    *SIGNAL_COLUMNS,
    "testing_signal",
    "testing_signal_count",
    "testing_evidence",
    "event_context_testing_disagreement",
    "boilerplate_signal",
    "boilerplate_rule_count",
    "boilerplate_rule_ids",
    "event_context_boilerplate_disagreement",
    "assignment_priority",
    "class_method_group",
    "class_method_group_label",
    "taxonomy_status",
    "taxonomy_version",
]

OUTPUT_FILES = {
    "assignments": "run-py-7f13-primary-body-month-role-group-assignments.csv",
    "summary": "run-py-7f13-role-group-summary.csv",
    "support": "run-py-7f13-testing-signal-support.csv",
    "rules": "run-py-7f13-role-taxonomy-rules.csv",
    "boilerplate_support": "run-py-7f13-boilerplate-rule-support.csv",
    "boilerplate_contexts": "run-py-7f13-boilerplate-event-contexts.csv",
    "boilerplate_audit": "run-py-7f13-boilerplate-deterministic-audit.csv",
    "disagreements": "run-py-7f13-body-month-context-disagreements.csv",
    "scan_errors": "run-py-7f13-direct-source-scan-errors.csv",
    "nested": "run-py-7f13-excluded-lexically-nested-methods.csv",
    "unsafe_bases": "run-py-7f13-excluded-broad-test-base-candidates.csv",
    "taxonomy": "run-py-7f13-role-taxonomy.json",
    "qc": "run-py-7f13-role-taxonomy-qc.csv",
    "metadata": "run-py-7f13-role-taxonomy-metadata.json",
}


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


@dataclass
class UnitEvidence:
    signals: dict[str, bool] = field(
        default_factory=lambda: {name: False for name in SIGNAL_COLUMNS}
    )
    event_contexts: int = 0
    event_testing_values: set[bool] = field(default_factory=set)
    event_boilerplate_values: set[bool] = field(default_factory=set)
    boilerplate_rule_ids: set[str] = field(default_factory=set)
    nested_values: set[bool] = field(default_factory=set)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-inventory", type=Path)
    parser.add_argument("--body-month-inventory", type=Path)
    parser.add_argument("--upstream-metadata", type=Path)
    parser.add_argument("--upstream-qc", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-event-contexts", type=int, default=4364)
    parser.add_argument("--expected-input-body-months", type=int, default=3931)
    parser.add_argument("--expected-nested-events", type=int, default=6)
    parser.add_argument("--expected-retained-body-months", type=int, default=3925)
    parser.add_argument("--expected-testing", type=int, default=1201)
    parser.add_argument("--expected-context-disagreements", type=int, default=0)
    parser.add_argument("--audit-sample-size", type=int, default=240)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Expected a JSON object in {path}")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValidationError(f"CSV has no header: {path}")
            return list(reader.fieldnames), list(reader)
    except OSError as exc:
        raise ValidationError(f"Cannot read CSV {path}: {exc}") from exc


def parse_bool(value: str, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "1.0", "true", "t", "yes"}:
        return True
    if normalized in {"0", "0.0", "false", "f", "no"}:
        return False
    raise ValidationError(f"{label} must be binary; found {value!r}")


def parse_positive_integer(value: str, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be numeric; found {value!r}") from exc
    if number <= 0 or not number.is_integer():
        raise ValidationError(f"{label} must be a positive integer; found {value!r}")
    return int(number)


def lexical_tokens(value: str) -> list[str]:
    split_acronym = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", str(value))
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", split_acronym)
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", split_camel)]


def path_tokens(value: str) -> set[str]:
    path = PurePosixPath(str(value).replace("\\", "/"))
    result: list[str] = []
    for part in path.parts:
        result.extend(lexical_tokens(PurePosixPath(part).stem))
    return set(result)


def normalized_identifier(value: str) -> str:
    return "".join(lexical_tokens(value))


def pipe_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def is_strong_test_class_name(value: str) -> bool:
    name = str(value or "").strip()
    if not name or name.endswith("TestMixin"):
        return False
    tokens = lexical_tokens(name)
    return "test" in tokens and (name.startswith("Test") or name.endswith("Test"))


def has_testcase_base(value: str) -> bool:
    for base in pipe_values(value):
        terminal = base.split(".")[-1]
        if normalized_identifier(terminal).endswith("testcase"):
            return True
    return False


def has_broad_test_base(value: str) -> bool:
    return any("test" in lexical_tokens(base) for base in pipe_values(value))


def has_test_framework_decorator(value: str) -> bool:
    for decorator in pipe_values(value):
        lowered = decorator.lower()
        if lowered.startswith("pytest.") or lowered.startswith("unittest."):
            return True
    return False


def classify_event(row: Mapping[str, str]) -> dict[str, bool]:
    function_name = row["function_name"].strip()
    lowered_name = function_name.lower()
    class_name = row["containing_class_name"].strip()
    signals = {
        "test_name": lowered_name.startswith("test") or lowered_name.endswith("_test"),
        "test_path": bool(path_tokens(row["relative_path"]) & TEST_PATH_TOKENS),
        "test_class_name": is_strong_test_class_name(class_name),
        "test_lifecycle_name": (
            normalized_identifier(function_name) in TEST_LIFECYCLE_NORMALIZED_NAMES
        ),
        "testcase_base": has_testcase_base(row["class_base_names"]),
        "test_framework_decorator": has_test_framework_decorator(
            row["method_decorator_callables"]
        ),
    }
    return signals


def decode_python_source(payload: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(payload).readline)
    return payload.decode(encoding)


def read_git_source(repo_dir: Path, source_label: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "show", source_label],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"Cannot read Git source {repo_dir} {source_label}: {message}")
    return decode_python_source(result.stdout)


def function_nodes_by_line(source: str, source_label: str) -> dict[int, ast.FunctionDef]:
    tree = ast.parse(source, filename=source_label, type_comments=True)
    result: dict[int, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            line = int(node.lineno)
            if line in result:
                raise ValidationError(f"Multiple synchronous functions begin at line {line}")
            result[line] = node
    return result


def decorator_terminals(node: ast.FunctionDef) -> set[str]:
    terminals: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            terminals.add(target.id)
        elif isinstance(target, ast.Attribute):
            terminals.add(target.attr)
    return terminals


def method_statements(node: ast.FunctionDef) -> list[ast.stmt]:
    statements = list(node.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    return statements


def attribute_root(node: ast.AST) -> tuple[str, list[str]] | None:
    attrs: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        attrs.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    return current.id, list(reversed(attrs))


def is_self_attribute(node: ast.AST) -> bool:
    rooted = attribute_root(node)
    return bool(rooted and rooted[0] == "self" and rooted[1])


def contains_self_attribute(node: ast.AST) -> bool:
    return any(is_self_attribute(item) for item in ast.walk(node))


def parameter_names(node: ast.FunctionDef) -> set[str]:
    result = {
        item.arg
        for item in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    }
    if node.args.vararg:
        result.add(node.args.vararg.arg)
    if node.args.kwarg:
        result.add(node.args.kwarg.arg)
    return result - {"self", "cls"}


def assigned_self_attribute(statement: ast.stmt) -> tuple[ast.Attribute, ast.AST] | None:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target, value = statement.targets[0], statement.value
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        target, value = statement.target, statement.value
    else:
        return None
    if isinstance(target, ast.Attribute) and is_self_attribute(target):
        return target, value
    return None


def is_attribute_binding_constructor(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if node.name != "__init__" or not body:
        return False
    parameters = parameter_names(node)
    for statement in body:
        assignment = assigned_self_attribute(statement)
        if assignment is None or not isinstance(assignment[1], ast.Name):
            return False
        if assignment[1].id not in parameters:
            return False
    return True


def is_super_init_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    receiver = node.func.value
    return (
        node.func.attr == "__init__"
        and isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "super"
    )


def is_super_delegating_constructor(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    return (
        node.name == "__init__"
        and len(body) == 1
        and isinstance(body[0], ast.Expr)
        and is_super_init_call(body[0].value)
    )


def is_property_accessor(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    terminals = decorator_terminals(node)
    if "property" in terminals:
        return (
            len(body) == 1
            and isinstance(body[0], ast.Return)
            and body[0].value is not None
            and is_self_attribute(body[0].value)
        )
    if "setter" in terminals and len(body) == 1:
        assignment = assigned_self_attribute(body[0])
        return bool(
            assignment
            and isinstance(assignment[1], ast.Name)
            and assignment[1].id in parameter_names(node)
        )
    return False


def is_representation(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if node.name not in {"__repr__", "__str__"} or len(body) != 1:
        return False
    if not isinstance(body[0], ast.Return) or body[0].value is None:
        return False
    value = body[0].value
    representation_shape = isinstance(value, ast.JoinedStr) or (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "format"
    )
    return representation_shape and contains_self_attribute(value)


def is_notimplemented_raise(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Raise) or statement.exc is None:
        return False
    exc = statement.exc.func if isinstance(statement.exc, ast.Call) else statement.exc
    return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"


def is_isinstance_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
    )


def is_comparison_or_hashing(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    comparison_names = {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"}
    if node.name == "__hash__" and len(body) == 1 and isinstance(body[0], ast.Return):
        value = body[0].value
        return bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "hash"
            and len(value.args) == 1
            and contains_self_attribute(value.args[0])
        )
    if node.name not in comparison_names:
        return False
    if len(body) == 1 and isinstance(body[0], ast.Return):
        return (
            isinstance(body[0].value, ast.Compare)
            and contains_self_attribute(body[0].value)
        )
    if len(body) == 2 and isinstance(body[0], ast.If) and isinstance(body[1], ast.Return):
        guard = body[0]
        guard_test = guard.test.operand if isinstance(guard.test, ast.UnaryOp) else guard.test
        guard_returns = all(isinstance(item, ast.Return) for item in guard.body)
        return (
            is_isinstance_call(guard_test)
            and guard_returns
            and isinstance(body[1].value, ast.Compare)
            and contains_self_attribute(body[1].value)
        )
    return False


def is_container_protocol(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if node.name not in {"__len__", "__iter__", "__getitem__", "__contains__"}:
        return False
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        return False
    value = body[0].value
    if node.name in {"__len__", "__iter__"}:
        return bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == node.name.strip("_")
            and len(value.args) == 1
            and is_self_attribute(value.args[0])
        )
    if node.name == "__getitem__":
        return isinstance(value, ast.Subscript) and is_self_attribute(value.value)
    return (
        isinstance(value, ast.Compare)
        and len(value.ops) == 1
        and isinstance(value.ops[0], ast.In)
        and len(value.comparators) == 1
        and is_self_attribute(value.comparators[0])
    )


def is_cleanup_call(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and is_self_attribute(statement.value.func)
    )


def is_context_manager(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if node.name == "__enter__":
        return (
            len(body) == 1
            and isinstance(body[0], ast.Return)
            and isinstance(body[0].value, ast.Name)
            and body[0].value.id == "self"
        )
    if node.name != "__exit__" or not body or len(body) > 2:
        return False
    if not is_cleanup_call(body[0]):
        return False
    return len(body) == 1 or (
        isinstance(body[1], ast.Return)
        and (
            body[1].value is None
            or isinstance(body[1].value, ast.Constant)
            and body[1].value.value in {None, False}
        )
    )


def unwrap_serialized_dict(value: ast.AST) -> ast.Dict | None:
    if isinstance(value, ast.Dict):
        return value
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr in {"dumps", "dump"}
        and value.args
        and isinstance(value.args[0], ast.Dict)
    ):
        return value.args[0]
    return None


def is_serialization(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if node.name not in {"to_dict", "as_dict", "to_json"} or len(body) != 1:
        return False
    if not isinstance(body[0], ast.Return) or body[0].value is None:
        return False
    value = unwrap_serialized_dict(body[0].value)
    return bool(value is not None and contains_self_attribute(value))


def is_factory(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if not node.name.startswith("from_") or len(body) != 1:
        return False
    if not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return False
    first = [*node.args.posonlyargs, *node.args.args]
    has_cls = bool(first and first[0].arg == "cls")
    return (
        ("classmethod" in decorator_terminals(node) or has_cls)
        and isinstance(body[0].value.func, ast.Name)
        and body[0].value.func.id == "cls"
    )


def is_forwarded_value(node: ast.AST, parameters: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in parameters
    if isinstance(node, ast.Starred) and isinstance(node.value, ast.Name):
        return node.value.id in parameters
    return False


def is_delegation_pass_through(node: ast.FunctionDef, body: Sequence[ast.stmt]) -> bool:
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    call = body[0].value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return False
    receiver = attribute_root(call.func.value)
    if not receiver or receiver[0] != "self" or not receiver[1]:
        return False
    if call.func.attr != node.name:
        return False
    parameters = parameter_names(node)
    return all(is_forwarded_value(item, parameters) for item in call.args) and all(
        keyword.arg is None and is_forwarded_value(keyword.value, parameters)
        or keyword.arg is not None and is_forwarded_value(keyword.value, parameters)
        for keyword in call.keywords
    )


def is_stub_abstract(body: Sequence[ast.stmt]) -> bool:
    if not body:
        return True
    if len(body) != 1:
        return False
    statement = body[0]
    return (
        isinstance(statement, ast.Pass)
        or is_notimplemented_raise(statement)
        or isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    )


def classify_boilerplate(node: ast.FunctionDef) -> list[str]:
    body = method_statements(node)
    rules = [
        ("attribute_binding_constructor", is_attribute_binding_constructor(node, body)),
        ("super_delegating_constructor", is_super_delegating_constructor(node, body)),
        ("property_accessor", is_property_accessor(node, body)),
        ("representation", is_representation(node, body)),
        ("comparison_or_hashing", is_comparison_or_hashing(node, body)),
        ("container_protocol", is_container_protocol(node, body)),
        ("context_manager", is_context_manager(node, body)),
        ("serialization", is_serialization(node, body)),
        ("factory", is_factory(node, body)),
        ("delegation_pass_through", is_delegation_pass_through(node, body)),
        ("stub_abstract", is_stub_abstract(body)),
    ]
    return [rule_id for rule_id, matched in rules if matched]


def scan_boilerplate_events(
    rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    cache: dict[tuple[str, str], dict[int, ast.FunctionDef]] = {}
    results: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for row in rows:
        event_id = row["function_event_id"].strip()
        repo_dir = Path(row["git_repo_dir"])
        source_label = row["git_source_label"].strip()
        try:
            cache_key = (str(repo_dir), source_label)
            if cache_key not in cache:
                source = read_git_source(repo_dir, source_label)
                cache[cache_key] = function_nodes_by_line(source, source_label)
            line = int(float(row["method_definition_line"]))
            node = cache[cache_key].get(line)
            if node is None:
                raise ValidationError(f"No synchronous function at definition line {line}")
            if node.name != row["git_function_name"].strip():
                raise ValidationError(
                    f"Function-name mismatch at line {line}: {node.name!r} != "
                    f"{row['git_function_name']!r}"
                )
            rule_ids = classify_boilerplate(node)
            rendered = ast.unparse(copy.deepcopy(node)).rstrip() + "\n"
            results[event_id] = {
                "boilerplate": bool(rule_ids),
                "rule_ids": rule_ids,
                "method_source": rendered,
                "method_source_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            }
        except Exception as exc:
            errors.append(
                {
                    "function_event_id": event_id,
                    "dataset_source": row["dataset_source"],
                    "repo_name": row["repo_name"],
                    "time": row["time"],
                    "git_repo_dir": str(repo_dir),
                    "git_source_label": source_label,
                    "method_definition_line": row["method_definition_line"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return results, errors


def stable_key(row: Mapping[str, str]) -> tuple[str, str, str, str]:
    key = tuple(row[column].strip() for column in KEY_COLUMNS)
    if any(not value for value in key):
        raise ValidationError(f"Empty body-month key: {key}")
    return key  # type: ignore[return-value]


def validate_upstream(metadata: Mapping[str, Any], qc_path: Path) -> None:
    if metadata.get("script_version") != UPSTREAM_SCRIPT_VERSION:
        raise ValidationError(
            "Unexpected run-py-7f12 script_version: "
            f"{metadata.get('script_version')!r}"
        )
    if metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f12 metadata status must be PASS")
    feature_policy = metadata.get("feature_policy")
    if not isinstance(feature_policy, dict):
        raise ValidationError("run-py-7f12 feature_policy is missing")
    if feature_policy.get("semantic_role_taxonomy") != "none":
        raise ValidationError("run-py-7f12 must not contain a prior semantic taxonomy")

    fields, rows = read_csv(qc_path)
    required = {"check_name", "passed"}
    if not required.issubset(fields) or not rows:
        raise ValidationError("Unexpected or empty run-py-7f12 QC")
    failed = [row["check_name"] for row in rows if not parse_bool(row["passed"], row["check_name"])]
    if failed:
        raise ValidationError("run-py-7f12 has failed QC checks: " + ", ".join(failed))


def aggregate_events(
    rows: Sequence[Mapping[str, str]],
    boilerplate_results: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[tuple[str, str, str, str], UnitEvidence],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    units: dict[tuple[str, str, str, str], UnitEvidence] = defaultdict(UnitEvidence)
    nested_rows: list[dict[str, str]] = []
    unsafe_base_rows: list[dict[str, str]] = []
    boilerplate_contexts: list[dict[str, str]] = []
    seen_events: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        event_id = row["function_event_id"].strip()
        if not event_id or event_id in seen_events:
            raise ValidationError(f"Invalid or duplicate function_event_id at row {row_number}")
        seen_events.add(event_id)
        if event_id not in boilerplate_results:
            raise ValidationError(f"Missing boilerplate result for event {event_id}")
        key = stable_key(row)
        signals = classify_event(row)
        testing = any(signals.values())
        boilerplate_result = boilerplate_results[event_id]
        boilerplate = bool(boilerplate_result["boilerplate"])
        rule_ids = [str(item) for item in boilerplate_result["rule_ids"]]
        nested = parse_bool(row["is_nested_function"], f"event row {row_number} nested")

        unit = units[key]
        unit.event_contexts += 1
        unit.event_testing_values.add(testing)
        unit.event_boilerplate_values.add(boilerplate)
        unit.boilerplate_rule_ids.update(rule_ids)
        unit.nested_values.add(nested)
        for name, value in signals.items():
            unit.signals[name] = unit.signals[name] or value

        if nested:
            nested_rows.append(
                {
                    **{column: row[column] for column in KEY_COLUMNS},
                    "function_event_id": event_id,
                    "relative_path": row["relative_path"],
                    "qualified_function_name": row.get("qualified_function_name", ""),
                    "containing_class_name": row["containing_class_name"],
                    "exclusion_reason": "lexically_nested_or_local_class_method",
                }
            )

        broad_base = has_broad_test_base(row["class_base_names"])
        if broad_base and not signals["testcase_base"]:
            unsafe_base_rows.append(
                {
                    **{column: row[column] for column in KEY_COLUMNS},
                    "function_event_id": event_id,
                    "relative_path": row["relative_path"],
                    "function_name": row["function_name"],
                    "containing_class_name": row["containing_class_name"],
                    "class_base_names": row["class_base_names"],
                    "otherwise_testing": "1" if testing else "0",
                    "policy": "generic_test_base_not_used_as_testing_evidence",
                }
            )

        if boilerplate:
            boilerplate_contexts.append(
                {
                    **{column: row[column] for column in KEY_COLUMNS},
                    "function_event_id": event_id,
                    "relative_path": row["relative_path"],
                    "qualified_function_name": row.get("qualified_function_name", ""),
                    "function_name": row["function_name"],
                    "containing_class_name": row["containing_class_name"],
                    "testing_signal": "1" if testing else "0",
                    "boilerplate_rule_ids": "|".join(rule_ids),
                    "method_source_sha256": str(boilerplate_result["method_source_sha256"]),
                    "method_source": str(boilerplate_result["method_source"]),
                }
            )

    return dict(units), nested_rows, unsafe_base_rows, boilerplate_contexts


def build_assignments(
    body_rows: Sequence[Mapping[str, str]],
    units: Mapping[tuple[str, str, str, str], UnitEvidence],
) -> tuple[
    list[dict[str, str]],
    Counter[str],
    Counter[str],
    Counter[str],
    int,
    int,
    int,
    list[dict[str, str]],
]:
    assignments: list[dict[str, str]] = []
    group_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    boilerplate_rule_counts: Counter[str] = Counter()
    seen: set[tuple[str, str, str, str]] = set()
    excluded_units = 0
    disagreements = 0
    boilerplate_disagreements = 0
    disagreement_rows: list[dict[str, str]] = []

    for row_number, row in enumerate(body_rows, start=2):
        key = stable_key(row)
        if key in seen:
            raise ValidationError(f"Duplicate body-month key at row {row_number}: {key}")
        seen.add(key)
        if key not in units:
            raise ValidationError(f"Body-month key has no event contexts: {key}")
        evidence = units[key]
        expected_events = parse_positive_integer(
            row["event_context_count"], f"body row {row_number} event_context_count"
        )
        if expected_events != evidence.event_contexts:
            raise ValidationError(
                f"Event-context count mismatch for {key}: "
                f"body={expected_events}, events={evidence.event_contexts}"
            )
        if len(evidence.nested_values) != 1:
            raise ValidationError(f"Mixed nested/non-nested contexts for body-month {key}")
        if True in evidence.nested_values:
            excluded_units += 1
            continue

        disagreement = len(evidence.event_testing_values) > 1
        disagreements += int(disagreement)
        testing = any(evidence.signals.values())
        boilerplate_disagreement = len(evidence.event_boilerplate_values) > 1
        boilerplate_disagreements += int(boilerplate_disagreement)
        boilerplate = any(evidence.event_boilerplate_values)
        group = "testing" if testing else "boilerplate" if boilerplate else "other"
        assignment_priority = (
            "testing_first" if testing else "boilerplate_second" if boilerplate else "other_remainder"
        )
        active_signals = [name for name in SIGNAL_COLUMNS if evidence.signals[name]]
        for name in active_signals:
            signal_counts[name] += 1
        group_counts[group] += 1
        if group == "boilerplate":
            for rule_id in evidence.boilerplate_rule_ids:
                boilerplate_rule_counts[rule_id] += 1
        assignments.append(
            {
                **{column: row[column].strip() for column in KEY_COLUMNS},
                "time_to_event": row["time_to_event"].strip(),
                "treatment_period": row["treatment_period"].strip(),
                "event_context_count": str(expected_events),
                "function_names": row["function_names"],
                "qualified_function_names": row["qualified_function_names"],
                "relative_paths": row["relative_paths"],
                **{name: "1" if evidence.signals[name] else "0" for name in SIGNAL_COLUMNS},
                "testing_signal": "1" if testing else "0",
                "testing_signal_count": str(len(active_signals)),
                "testing_evidence": "|".join(active_signals),
                "event_context_testing_disagreement": "1" if disagreement else "0",
                "boilerplate_signal": "1" if boilerplate else "0",
                "boilerplate_rule_count": str(len(evidence.boilerplate_rule_ids)),
                "boilerplate_rule_ids": "|".join(sorted(evidence.boilerplate_rule_ids)),
                "event_context_boilerplate_disagreement": (
                    "1" if boilerplate_disagreement else "0"
                ),
                "assignment_priority": assignment_priority,
                "class_method_group": group,
                "class_method_group_label": GROUP_LABELS[group],
                "taxonomy_status": TAXONOMY_STATUS,
                "taxonomy_version": TAXONOMY_VERSION,
            }
        )
        if disagreement or boilerplate_disagreement:
            disagreement_rows.append(
                {
                    **{column: row[column].strip() for column in KEY_COLUMNS},
                    "testing_values": "|".join(
                        "1" if value else "0" for value in sorted(evidence.event_testing_values)
                    ),
                    "boilerplate_values": "|".join(
                        "1" if value else "0" for value in sorted(evidence.event_boilerplate_values)
                    ),
                    "assigned_group": group,
                    "assignment_priority": assignment_priority,
                }
            )

    missing = set(units) - seen
    if missing:
        raise ValidationError(f"Event inventory has {len(missing)} keys absent from body inventory")
    assignments.sort(key=lambda row: tuple(row[column] for column in KEY_COLUMNS))
    return (
        assignments,
        group_counts,
        signal_counts,
        boilerplate_rule_counts,
        excluded_units,
        disagreements,
        boilerplate_disagreements,
        disagreement_rows,
    )


def qc_row(name: str, passed: bool, observed: Any, expected: Any, note: str) -> dict[str, Any]:
    return {
        "check_name": name,
        "severity": "critical",
        "passed": passed,
        "observed": observed,
        "expected": expected,
        "note": note,
    }


def build_qc(
    *,
    event_rows: int,
    input_units: int,
    nested_events: int,
    excluded_units: int,
    assignments: Sequence[Mapping[str, str]],
    group_counts: Mapping[str, int],
    disagreements: int,
    direct_scan_errors: int,
    expected_event_rows: int,
    expected_input_units: int,
    expected_nested_events: int,
    expected_retained_units: int,
    expected_testing: int,
    expected_disagreements: int,
) -> list[dict[str, Any]]:
    duplicate_keys = len(assignments) - len(
        {tuple(row[column] for column in KEY_COLUMNS) for row in assignments}
    )
    invalid_group_rows = sum(
        row["class_method_group"] not in GROUPS for row in assignments
    )
    rule_mismatches = 0
    for row in assignments:
        testing = parse_bool(row["testing_signal"], "testing_signal")
        boilerplate = parse_bool(row["boilerplate_signal"], "boilerplate_signal")
        expected_group = "testing" if testing else "boilerplate" if boilerplate else "other"
        rule_mismatches += int(row["class_method_group"] != expected_group)
    return [
        qc_row("event_context_rows", event_rows == expected_event_rows, event_rows, expected_event_rows, "Preserve the complete run-py-7f12 event inventory."),
        qc_row("input_body_month_units", input_units == expected_input_units, input_units, expected_input_units, "Preserve the complete run-py-7f12 body-month inventory."),
        qc_row("lexically_nested_event_contexts", nested_events == expected_nested_events, nested_events, expected_nested_events, "Exclude the pre-identified nested/local-class method contexts."),
        qc_row("excluded_nested_body_month_units", excluded_units == expected_nested_events, excluded_units, expected_nested_events, "Each excluded event must map to one excluded body-month unit."),
        qc_row("retained_body_month_units", len(assignments) == expected_retained_units, len(assignments), expected_retained_units, "Retained units define the frozen class-method universe."),
        qc_row("testing_units", group_counts.get("testing", 0) == expected_testing, group_counts.get("testing", 0), expected_testing, "Testing uses name/path plus strong class-specific evidence."),
        qc_row("direct_source_scan_errors", direct_scan_errors == 0, direct_scan_errors, 0, "Every run-py-7f12 event must resolve in the exact Git source."),
        qc_row("role_group_total", sum(group_counts.values()) == expected_retained_units, sum(group_counts.values()), expected_retained_units, "Testing, boilerplate, and other must be exhaustive."),
        qc_row("duplicate_assignment_keys", duplicate_keys == 0, duplicate_keys, 0, "Each retained body-month key has one assignment."),
        qc_row("invalid_group_rows", invalid_group_rows == 0, invalid_group_rows, 0, "Only the three frozen groups are allowed."),
        qc_row("priority_rule_mismatches", rule_mismatches == 0, rule_mismatches, 0, "Testing-first, boilerplate-second, other-remainder priority must determine every group."),
        qc_row("event_context_testing_disagreements", disagreements == expected_disagreements, disagreements, expected_disagreements, "A repeated body-month should not change testing status across contexts."),
        qc_row("taxonomy_frozen", True, TAXONOMY_STATUS, TAXONOMY_STATUS, "The rule is frozen before any class-method ATT estimation."),
    ]


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def output_rows_by_source(assignments: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    repos: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in assignments:
        key = (row["class_method_group"], row["dataset_source"])
        counts[key] += 1
        repos[key].add(row["repo_name"])
    output: list[dict[str, Any]] = []
    for group in GROUPS:
        for source in ["treatment", "control", "all"]:
            if source == "all":
                count = sum(counts[(group, item)] for item in ["treatment", "control"])
                repo_count = len(
                    repos[(group, "treatment")] | repos[(group, "control")]
                )
            else:
                count = counts[(group, source)]
                repo_count = len(repos[(group, source)])
            output.append(
                {
                    "class_method_group": group,
                    "class_method_group_label": GROUP_LABELS[group],
                    "dataset_source": source,
                    "body_month_units": count,
                    "repositories": repo_count,
                }
            )
    return output


def deterministic_audit_rows(
    event_rows: Sequence[Mapping[str, str]],
    boilerplate_results: Mapping[str, Mapping[str, Any]],
    sample_size: int,
) -> list[dict[str, str]]:
    candidates: dict[str, list[dict[str, str]]] = {group: [] for group in GROUPS}
    for row in event_rows:
        if parse_bool(row["is_nested_function"], "audit nested"):
            continue
        event_id = row["function_event_id"].strip()
        result = boilerplate_results[event_id]
        testing = any(classify_event(row).values())
        boilerplate = bool(result["boilerplate"])
        group = "testing" if testing else "boilerplate" if boilerplate else "other"
        candidates[group].append(
            {
                "sample_rank_key": hashlib.sha256(event_id.encode("utf-8")).hexdigest(),
                "class_method_group": group,
                "function_event_id": event_id,
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "time": row["time"],
                "relative_path": row["relative_path"],
                "qualified_function_name": row.get("qualified_function_name", ""),
                "function_body_sha256": row["function_body_sha256"],
                "boilerplate_rule_ids": "|".join(str(item) for item in result["rule_ids"]),
                "method_source": str(result["method_source"]),
            }
        )
    per_group = sample_size // len(GROUPS)
    remainder = sample_size % len(GROUPS)
    selected: list[dict[str, str]] = []
    for index, group in enumerate(GROUPS):
        take = per_group + int(index < remainder)
        selected.extend(sorted(candidates[group], key=lambda row: row["sample_rank_key"])[:take])
    return sorted(selected, key=lambda row: (row["class_method_group"], row["sample_rank_key"]))


def write_outputs(
    *,
    output_dir: Path,
    assignments: Sequence[Mapping[str, str]],
    summary_rows: Sequence[Mapping[str, Any]],
    signal_counts: Mapping[str, int],
    boilerplate_rule_counts: Mapping[str, int],
    boilerplate_contexts: Sequence[Mapping[str, str]],
    boilerplate_audit_rows: Sequence[Mapping[str, str]],
    disagreement_rows: Sequence[Mapping[str, str]],
    scan_errors: Sequence[Mapping[str, str]],
    nested_rows: Sequence[Mapping[str, str]],
    unsafe_base_rows: Sequence[Mapping[str, str]],
    qc_rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    overwrite: bool,
) -> None:
    paths = {key: output_dir / value for key, value in OUTPUT_FILES.items()}
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise ValidationError(
            "Output files already exist; use --overwrite for an intentional rerun: "
            + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".run-py-7f13-", dir=output_dir))
    try:
        write_csv(staging / OUTPUT_FILES["assignments"], assignments, ASSIGNMENT_COLUMNS)
        write_csv(
            staging / OUTPUT_FILES["summary"],
            summary_rows,
            ["class_method_group", "class_method_group_label", "dataset_source", "body_month_units", "repositories"],
        )
        support_rows = [
            {"testing_signal": name, "body_month_units": signal_counts.get(name, 0)}
            for name in SIGNAL_COLUMNS
        ]
        write_csv(staging / OUTPUT_FILES["support"], support_rows, ["testing_signal", "body_month_units"])
        boilerplate_support_rows = [
            {
                "boilerplate_rule_id": rule_id,
                "boilerplate_rule_label": BOILERPLATE_RULE_LABELS[rule_id],
                "assigned_body_month_units": boilerplate_rule_counts.get(rule_id, 0),
            }
            for rule_id in BOILERPLATE_RULE_LABELS
        ]
        write_csv(
            staging / OUTPUT_FILES["boilerplate_support"],
            boilerplate_support_rows,
            ["boilerplate_rule_id", "boilerplate_rule_label", "assigned_body_month_units"],
        )
        rule_rows = [
            {"rule_id": "test_name", "included": 1, "definition": "method name starts with test or ends with _test"},
            {"rule_id": "test_path", "included": 1, "definition": "relative-path tokens contain test, tests, or testing"},
            {"rule_id": "test_class_name", "included": 1, "definition": "containing class has a lexical test token and starts or ends with Test; *TestMixin excluded"},
            {"rule_id": "test_lifecycle_name", "included": 1, "definition": "exact normalized setup/teardown lifecycle method name"},
            {"rule_id": "testcase_base", "included": 1, "definition": "class base terminal name ends with TestCase"},
            {"rule_id": "test_framework_decorator", "included": 1, "definition": "method decorator callable begins with pytest. or unittest."},
            {"rule_id": "generic_test_base", "included": 0, "definition": "generic class-base test token is audit-only; avoids BBoxTestMixin and MaskTestMixin false positives"},
            {"rule_id": "lexically_nested_method", "included": 0, "definition": "method is excluded when run-py-7f12 marks is_nested_function=true"},
            {"rule_id": "group_priority", "included": 1, "definition": "testing first; boilerplate second; other is the remainder"},
            {"rule_id": "category_identity", "included": 1, "definition": "Category 4 = Category 5 + Category 6 + Category 7"},
        ]
        rule_rows.extend(
            {
                "rule_id": rule_id,
                "included": 1,
                "definition": label,
            }
            for rule_id, label in BOILERPLATE_RULE_LABELS.items()
        )
        write_csv(staging / OUTPUT_FILES["rules"], rule_rows, ["rule_id", "included", "definition"])
        write_csv(
            staging / OUTPUT_FILES["boilerplate_contexts"],
            boilerplate_contexts,
            [*KEY_COLUMNS, "function_event_id", "relative_path", "qualified_function_name", "function_name", "containing_class_name", "testing_signal", "boilerplate_rule_ids", "method_source_sha256", "method_source"],
        )
        write_csv(
            staging / OUTPUT_FILES["boilerplate_audit"],
            boilerplate_audit_rows,
            ["sample_rank_key", "class_method_group", "function_event_id", "dataset_source", "repo_name", "time", "relative_path", "qualified_function_name", "function_body_sha256", "boilerplate_rule_ids", "method_source"],
        )
        write_csv(
            staging / OUTPUT_FILES["disagreements"],
            disagreement_rows,
            [*KEY_COLUMNS, "testing_values", "boilerplate_values", "assigned_group", "assignment_priority"],
        )
        write_csv(
            staging / OUTPUT_FILES["scan_errors"],
            scan_errors,
            ["function_event_id", "dataset_source", "repo_name", "time", "git_repo_dir", "git_source_label", "method_definition_line", "error_type", "error"],
        )
        write_csv(
            staging / OUTPUT_FILES["nested"],
            nested_rows,
            [*KEY_COLUMNS, "function_event_id", "relative_path", "qualified_function_name", "containing_class_name", "exclusion_reason"],
        )
        write_csv(
            staging / OUTPUT_FILES["unsafe_bases"],
            unsafe_base_rows,
            [*KEY_COLUMNS, "function_event_id", "relative_path", "function_name", "containing_class_name", "class_base_names", "otherwise_testing", "policy"],
        )
        taxonomy = {
            "schema_version": SCRIPT_VERSION,
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "groups": [
                {"id": "testing", "category": 5, "label": GROUP_LABELS["testing"]},
                {"id": "boilerplate", "category": 6, "label": GROUP_LABELS["boilerplate"]},
                {"id": "other", "category": 7, "label": GROUP_LABELS["other"]},
            ],
            "all_class_methods_category": 4,
            "testing_rule": "OR of the six included strong signals",
            "boilerplate_rule": "OR of the eleven conservative AST rules after testing exclusion",
            "assignment_priority": ["testing", "boilerplate", "other"],
            "partition_identity": "category_4 = category_5 + category_6 + category_7",
            "generic_test_base_is_evidence": False,
            "lexically_nested_methods_included": False,
            "att_or_uncertainty_computed": False,
        }
        (staging / OUTPUT_FILES["taxonomy"]).write_text(
            json.dumps(taxonomy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_csv(staging / OUTPUT_FILES["qc"], qc_rows, ["check_name", "severity", "passed", "observed", "expected", "note"])

        materialized = [key for key in OUTPUT_FILES if key != "metadata"]
        output_hashes = {
            key: sha256_file(staging / OUTPUT_FILES[key]) for key in materialized
        }
        full_metadata = dict(metadata)
        full_metadata["outputs"] = {
            key: {"file": OUTPUT_FILES[key], "sha256": output_hashes[key]}
            for key in materialized
        }
        (staging / OUTPUT_FILES["metadata"]).write_text(
            json.dumps(full_metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for filename in OUTPUT_FILES.values():
            os.replace(staging / filename, output_dir / filename)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def run_self_test() -> None:
    base = {
        "function_name": "my_sum",
        "relative_path": "src/calculator.py",
        "containing_class_name": "OrderCalculator",
        "class_base_names": "",
        "method_decorator_callables": "staticmethod",
    }
    if any(classify_event(base).values()):
        raise ValidationError("Self-test misclassified a non-testing static method")
    testcase = dict(base, class_base_names="unittest.TestCase")
    if not classify_event(testcase)["testcase_base"]:
        raise ValidationError("Self-test missed TestCase evidence")
    inference = dict(base, class_base_names="BaseRoIHead|BBoxTestMixin|MaskTestMixin")
    if any(classify_event(inference).values()):
        raise ValidationError("Self-test misclassified an inference TestMixin")
    named_test = dict(base, function_name="test_total")
    if not classify_event(named_test)["test_name"]:
        raise ValidationError("Self-test missed a test-oriented method name")
    source = """
class Example:
    def __init__(self, value):
        self.value = value

    @property
    def value(self):
        return self._value

    def calculate(self, value):
        return value * 2

    def empty(self):
        raise NotImplementedError
"""
    nodes = function_nodes_by_line(source, "<self-test>")
    by_name = {node.name: node for node in nodes.values()}
    if classify_boilerplate(by_name["__init__"]) != ["attribute_binding_constructor"]:
        raise ValidationError("Self-test missed attribute-binding constructor")
    if classify_boilerplate(by_name["value"]) != ["property_accessor"]:
        raise ValidationError("Self-test missed property accessor")
    if classify_boilerplate(by_name["calculate"]):
        raise ValidationError("Self-test misclassified business logic as boilerplate")
    if classify_boilerplate(by_name["empty"]) != ["stub_abstract"]:
        raise ValidationError("Self-test missed abstract stub")
    print("run-py-7f13 self-test PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test_only:
            run_self_test()
            return 0
        required = {
            "event inventory": args.event_inventory,
            "body-month inventory": args.body_month_inventory,
            "upstream metadata": args.upstream_metadata,
            "upstream QC": args.upstream_qc,
        }
        for label, path in required.items():
            if path is None or not path.is_file() or path.stat().st_size == 0:
                raise ValidationError(f"Missing or empty {label}: {path}")
        if args.output_dir is None:
            raise ValidationError("--output-dir is required")

        metadata = read_json(args.upstream_metadata)
        validate_upstream(metadata, args.upstream_qc)
        event_fields, event_rows = read_csv(args.event_inventory)
        body_fields, body_rows = read_csv(args.body_month_inventory)
        missing_event = sorted(EVENT_REQUIRED_COLUMNS - set(event_fields))
        missing_body = sorted(BODY_REQUIRED_COLUMNS - set(body_fields))
        if missing_event:
            raise ValidationError("Event inventory is missing columns: " + ", ".join(missing_event))
        if missing_body:
            raise ValidationError("Body-month inventory is missing columns: " + ", ".join(missing_body))

        boilerplate_results, scan_errors = scan_boilerplate_events(event_rows)
        units, nested_rows, unsafe_base_rows, boilerplate_contexts = aggregate_events(
            event_rows, boilerplate_results
        )
        (
            assignments,
            group_counts,
            signal_counts,
            boilerplate_rule_counts,
            excluded_units,
            disagreements,
            boilerplate_disagreements,
            disagreement_rows,
        ) = build_assignments(body_rows, units)
        qc_rows = build_qc(
            event_rows=len(event_rows),
            input_units=len(body_rows),
            nested_events=len(nested_rows),
            excluded_units=excluded_units,
            assignments=assignments,
            group_counts=group_counts,
            disagreements=disagreements,
            direct_scan_errors=len(scan_errors),
            expected_event_rows=args.expected_event_contexts,
            expected_input_units=args.expected_input_body_months,
            expected_nested_events=args.expected_nested_events,
            expected_retained_units=args.expected_retained_body_months,
            expected_testing=args.expected_testing,
            expected_disagreements=args.expected_context_disagreements,
        )
        failed = [row["check_name"] for row in qc_rows if not row["passed"]]
        if failed:
            raise ValidationError("Critical QC failed before publication: " + ", ".join(failed))

        summary_rows = output_rows_by_source(assignments)
        audit_rows = deterministic_audit_rows(
            event_rows, boilerplate_results, args.audit_sample_size
        )
        output_metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": "PASS",
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "inputs": {
                "run_py_7f12_event_inventory": {"path": str(args.event_inventory), "sha256": sha256_file(args.event_inventory)},
                "run_py_7f12_body_month_inventory": {"path": str(args.body_month_inventory), "sha256": sha256_file(args.body_month_inventory)},
                "run_py_7f12_metadata": {"path": str(args.upstream_metadata), "sha256": sha256_file(args.upstream_metadata)},
                "run_py_7f12_qc": {"path": str(args.upstream_qc), "sha256": sha256_file(args.upstream_qc)},
            },
            "counts": {
                "input_event_contexts": len(event_rows),
                "input_body_month_units": len(body_rows),
                "excluded_nested_event_contexts": len(nested_rows),
                "excluded_nested_body_month_units": excluded_units,
                "retained_body_month_units": len(assignments),
                "testing_body_month_units": group_counts.get("testing", 0),
                "boilerplate_body_month_units": group_counts.get("boilerplate", 0),
                "other_body_month_units": group_counts.get("other", 0),
                "event_context_testing_disagreements": disagreements,
                "event_context_boilerplate_disagreements": boilerplate_disagreements,
                "direct_source_scan_errors": len(scan_errors),
                "excluded_broad_test_base_candidate_contexts": len(unsafe_base_rows),
                "critical_qc_failures": 0,
            },
            "scientific_scope": {
                "synchronous_direct_class_scope_methods": True,
                "lexically_nested_or_local_class_methods_excluded": True,
                "role_groups_mutually_exclusive_and_exhaustive": True,
                "category_4_equals_categories_5_plus_6_plus_7": True,
                "generic_test_base_signal_excluded": True,
                "repository_month_outcomes_created": False,
                "att_or_uncertainty_computed": False,
            },
        }
        write_outputs(
            output_dir=args.output_dir,
            assignments=assignments,
            summary_rows=summary_rows,
            signal_counts=signal_counts,
            boilerplate_rule_counts=boilerplate_rule_counts,
            boilerplate_contexts=boilerplate_contexts,
            boilerplate_audit_rows=audit_rows,
            disagreement_rows=disagreement_rows,
            scan_errors=scan_errors,
            nested_rows=nested_rows,
            unsafe_base_rows=unsafe_base_rows,
            qc_rows=qc_rows,
            metadata=output_metadata,
            overwrite=args.overwrite,
        )
        print("run-py-7f13 class-method role taxonomy complete")
        print(f"Input event contexts:             {len(event_rows):,}")
        print(f"Input body-month units:           {len(body_rows):,}")
        print(f"Excluded nested units:            {excluded_units:,}")
        print(f"Retained body-month units:        {len(assignments):,}")
        print(f"Testing class-method units:       {group_counts.get('testing', 0):,}")
        print(f"Boilerplate class-method units:   {group_counts.get('boilerplate', 0):,}")
        print(f"Other class-method units:         {group_counts.get('other', 0):,}")
        print(f"Context disagreements:            {disagreements:,}")
        print(f"Boilerplate disagreements:        {boilerplate_disagreements:,}")
        print(f"Unsafe broad-base audit contexts: {len(unsafe_base_rows):,}")
        print(f"Output directory:                 {args.output_dir.resolve()}")
        print("ATT/uncertainty computed:          NO")
        print("Status:                            PASS")
        return 0
    except (ValidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
