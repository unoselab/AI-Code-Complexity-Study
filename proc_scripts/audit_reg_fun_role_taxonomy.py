#!/usr/bin/env python3
"""Audit candidate semantic roles for regular module functions.

This stage freezes neither role-specific outcomes nor treatment effects. It
defines transparent candidate signals, measures them in the outcome-blind
run-py-7f02 full-history inventory, produces deterministic source-review
samples, and checks how the same rules partition the already locked 2,249
run-py-7f01 body-month units.

Scientific boundaries
---------------------
- Candidate rules are fixed in this source file before execution.
- Full-history source audit samples come only from run-py-7f02 v2.
- run-py-7f01 is used only for compatibility and partition invariants.
- No role-specific repository-month panel is created.
- No ATT, standard error, confidence interval, or p-value is read or computed.
- Decorators remain structural evidence and are never a primary role.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import heapq
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
from typing import Any, Iterable, Iterator, Mapping, Sequence


SCRIPT_VERSION = "run-py-7f06-v1"
TAXONOMY_STATUS = "CANDIDATE_NOT_FROZEN"

PRIMARY_KEY_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "function_body_sha256",
]

PRIMARY_ROLES = [
    "testing",
    "main_entry_point",
    "web_api_handler",
    "cli_argument_processing",
    "validation_parsing_conversion",
    "other_general",
]

ROLE_PRECEDENCE = [
    "testing",
    "main_entry_point",
    "web_api_handler",
    "cli_argument_processing",
    "validation_parsing_conversion",
]

SIGNAL_NAMES = [
    "testing",
    "main_entry_point",
    "web_api_handler",
    "cli_argument_processing",
    "validation_parsing_conversion",
]

FLAG_NAMES = [
    "test_name",
    "test_path",
    "web_api_path",
    "web_route_decorator",
    "cli_name",
    "cli_path",
    "cli_decorator",
    "crud_name",
    "migration_context",
    "setup_lifecycle_name",
    "builder_factory_name",
    "has_decorator",
]

TEST_PATH_TOKENS = {"test", "tests", "testing"}
CLI_PATH_TOKENS = {"cli", "cmd", "command", "commands", "console"}
CLI_NAME_TOKENS = {"arg", "args", "argparse", "argument", "arguments", "cli"}
CLI_NAME_EXACT = {
    "add_arguments",
    "build_parser",
    "create_parser",
    "get_parser",
    "main_cli",
    "parse_args",
    "parse_arguments",
    "register_commands",
}
CLI_DECORATOR_ROOTS = {"click", "typer"}
CLI_DECORATOR_TERMINALS = {"argument", "command", "group", "option"}

WEB_PATH_TOKENS = {
    "api",
    "apis",
    "controller",
    "controllers",
    "endpoint",
    "endpoints",
    "handler",
    "handlers",
    "route",
    "routes",
    "router",
    "routers",
    "view",
    "views",
}
WEB_NAME_TOKENS = {"endpoint", "handler", "route", "view"}
CRUD_NAME_TOKENS = {
    "create",
    "delete",
    "destroy",
    "get",
    "list",
    "patch",
    "post",
    "put",
    "read",
    "retrieve",
    "update",
}
WEB_DECORATOR_TERMINALS = {
    "action",
    "api_view",
    "endpoint",
    "route",
    "view_config",
    "websocket",
    "websocket_route",
}
HTTP_DECORATOR_TERMINALS = {
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
}
WEB_DECORATOR_ROOT_TOKENS = {
    "api",
    "app",
    "blueprint",
    "bp",
    "router",
    "routes",
    "server",
}

VALIDATION_NAME_TOKENS = {
    "coerce",
    "coercion",
    "conversion",
    "convert",
    "converter",
    "decode",
    "deserialize",
    "deserializer",
    "encode",
    "normalization",
    "normalize",
    "normalizer",
    "parse",
    "parser",
    "parsing",
    "sanitize",
    "sanitizer",
    "serialization",
    "serialize",
    "serializer",
    "transform",
    "transformation",
    "valid",
    "validate",
    "validation",
    "validator",
    "verification",
    "verify",
}

MIGRATION_TOKENS = {"alembic", "migration", "migrations", "upgrade", "downgrade"}
SETUP_LIFECYCLE_TOKENS = {
    "bootstrap",
    "cleanup",
    "initialize",
    "initialise",
    "setup",
    "shutdown",
    "startup",
    "teardown",
}
BUILDER_FACTORY_TOKENS = {"builder", "build", "factory", "make"}

AUDIT_STRATUM_QUOTAS = {
    "testing_name_and_path": 20,
    "testing_path_only": 25,
    "testing_name_only": 10,
    "validation_only": 35,
    "web_api_only": 35,
    "cli_only": 25,
    "main_only": 20,
    "multi_signal": 35,
    "other_general": 35,
}

FULL_HISTORY_REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "git_blob_sha",
    "function_ordinal",
    "qualified_function_name",
    "function_name",
    "is_async",
    "start_line",
    "end_line",
    "is_module_level",
    "decorator_count",
    "decorators_callable_json",
    "function_source_sha256",
}

PRIMARY_EVENT_REQUIRED_COLUMNS = {
    *PRIMARY_KEY_COLUMNS,
    "function_event_id",
    "function_name",
    "relative_path",
    "source_path",
}

PRIMARY_BODY_REQUIRED_COLUMNS = {
    *PRIMARY_KEY_COLUMNS,
    "time_to_event",
    "treatment_period",
    "event_context_count",
    "function_names",
    "relative_paths",
}


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


@dataclass
class UnitAggregate:
    signals: dict[str, bool] = field(
        default_factory=lambda: {name: False for name in SIGNAL_NAMES}
    )
    flags: dict[str, bool] = field(
        default_factory=lambda: {name: False for name in FLAG_NAMES}
    )
    context_roles: set[str] = field(default_factory=set)
    function_names: set[str] = field(default_factory=set)
    relative_paths: set[str] = field(default_factory=set)
    decorator_callables: set[str] = field(default_factory=set)
    event_contexts: int = 0


class DeterministicSampler:
    """Retain the lexicographically smallest stable hashes per stratum."""

    def __init__(self, quotas: Mapping[str, int]) -> None:
        self.quotas = dict(quotas)
        self.heaps: dict[str, list[tuple[int, str, dict[str, str]]]] = {
            name: [] for name in quotas
        }

    def consider(self, stratum: str, row: dict[str, str]) -> None:
        quota = self.quotas[stratum]
        stable_id = "\0".join(
            [
                stratum,
                row["dataset_source"],
                row["repo_name"],
                row["latest_commit"],
                row["relative_path"],
                row["function_ordinal"],
                row["function_source_sha256"],
            ]
        )
        sample_hash = hashlib.sha256(stable_id.encode("utf-8")).hexdigest()
        rank = int(sample_hash, 16)
        item = (-rank, stable_id, dict(row, sample_hash=sample_hash))
        heap = self.heaps[stratum]
        if len(heap) < quota:
            heapq.heappush(heap, item)
        elif rank < -heap[0][0]:
            heapq.heapreplace(heap, item)

    def rows(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for stratum in self.quotas:
            selected = [item[2] for item in self.heaps[stratum]]
            selected.sort(key=lambda row: row["sample_hash"])
            for row in selected:
                row["audit_stratum"] = stratum
            result.extend(selected)
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit candidate regular-module-function role rules before "
            "freezing role-specific outcomes or estimating ATT."
        )
    )
    parser.add_argument(
        "--full-history-function-inventory",
        type=Path,
        default=Path(
            "repo_python/run-py-7f02/strict/"
            "run-py-7f02-python-function-inventory.csv"
        ),
    )
    parser.add_argument(
        "--full-history-metadata",
        type=Path,
        default=Path(
            "repo_python/run-py-7f02/strict/run-py-7f02-scan-metadata.json"
        ),
    )
    parser.add_argument(
        "--primary-event-inventory",
        type=Path,
        default=Path(
            "repo_python/run-py-7f01/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean/"
            "run-py-7f01-function-event-context-inventory.csv"
        ),
    )
    parser.add_argument(
        "--primary-body-month-inventory",
        type=Path,
        default=Path(
            "repo_python/run-py-7f01/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean/"
            "run-py-7f01-body-month-outcome-unit-inventory.csv"
        ),
    )
    parser.add_argument(
        "--primary-metadata",
        type=Path,
        default=Path(
            "repo_python/run-py-7f01/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean/qc/"
            "run-py-7f01-role-inventory-metadata.json"
        ),
    )
    parser.add_argument(
        "--adjudication-metadata",
        type=Path,
        default=Path(
            "repo_python/run-py-7f05/strict/"
            "run-py-7f05-adjudication-metadata.json"
        ),
    )
    parser.add_argument("--treatment-clone-dir", type=Path, default=Path("../treatment-repos"))
    parser.add_argument("--control-clone-dir", type=Path, default=Path("../control-repos"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7f06/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean"
        ),
    )
    parser.add_argument("--expected-full-history-function-rows", type=int, default=2_899_926)
    parser.add_argument("--expected-primary-event-contexts", type=int, default=2_569)
    parser.add_argument("--expected-primary-body-months", type=int, default=2_249)
    parser.add_argument("--expected-audit-samples", type=int, default=240)
    parser.add_argument("--audit-source-max-characters", type=int, default=20_000)
    parser.add_argument("--progress-every", type=int, default=250_000)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Missing or empty {label}: {path}")
    return path


def require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lexical_tokens(value: str) -> list[str]:
    split_acronym = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", str(value))
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", split_acronym)
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", split_camel)]


def path_tokens(value: str) -> list[str]:
    path = PurePosixPath(str(value).replace("\\", "/"))
    result: list[str] = []
    for part in path.parts:
        result.extend(lexical_tokens(PurePosixPath(part).stem))
    return list(dict.fromkeys(result))


def parse_json_string_list(value: str, label: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON list in {label}: {error}") from error
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValidationError(f"{label} must be a JSON list of strings")
    return parsed


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


def decode_python_bytes(payload: bytes) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(payload).readline)
        return payload.decode(encoding)
    except Exception as error:
        raise ValidationError(f"Unable to decode Python source: {error}") from error


def parse_artifact_decorators(path: Path) -> list[str]:
    source = decode_python_bytes(path.read_bytes())
    primary_error: Exception | None = None
    try:
        tree = ast.parse(source, filename=str(path), type_comments=True)
    except Exception as error:
        primary_error = error
        try:
            tree = ast.parse(source, filename=str(path), type_comments=False)
        except Exception as fallback_error:
            raise ValidationError(
                f"Function artifact failed both parse modes: {path}; "
                f"primary={primary_error}; fallback={fallback_error}"
            ) from fallback_error
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if len(tree.body) != 1 or len(definitions) != 1:
        raise ValidationError(f"Expected exactly one function artifact: {path}")
    return [decorator_callable(node) for node in definitions[0].decorator_list]


def decorator_facts(callables: Sequence[str]) -> dict[str, bool]:
    cli = False
    web = False
    for raw in callables:
        value = raw.strip().lower()
        if not value:
            continue
        parts = [part for part in value.split(".") if part]
        root = parts[0] if parts else ""
        terminal = parts[-1] if parts else ""
        if root in CLI_DECORATOR_ROOTS or terminal in CLI_DECORATOR_TERMINALS:
            cli = True
        if terminal in WEB_DECORATOR_TERMINALS:
            web = True
        if terminal in HTTP_DECORATOR_TERMINALS and (
            root in WEB_DECORATOR_ROOT_TOKENS
            or bool(set(lexical_tokens(root)) & WEB_DECORATOR_ROOT_TOKENS)
        ):
            web = True
    return {"cli_decorator": cli, "web_route_decorator": web}


def classify_features(
    function_name: str,
    relative_path: str,
    decorator_callables: Sequence[str],
) -> dict[str, Any]:
    name_lower = function_name.strip().lower()
    name_tokens = lexical_tokens(function_name)
    name_token_set = set(name_tokens)
    path_token_set = set(path_tokens(relative_path))
    decorators = decorator_facts(decorator_callables)

    test_name = name_lower.startswith("test") or name_lower.endswith("_test")
    test_path = bool(path_token_set & TEST_PATH_TOKENS)
    cli_name = name_lower in CLI_NAME_EXACT or bool(name_token_set & CLI_NAME_TOKENS)
    cli_path = bool(path_token_set & CLI_PATH_TOKENS)
    web_api_path = bool(path_token_set & WEB_PATH_TOKENS)
    crud_name = bool(name_token_set & CRUD_NAME_TOKENS)
    web_handler_name = bool(name_token_set & WEB_NAME_TOKENS)
    web_api_handler = decorators["web_route_decorator"] or (
        web_api_path and (web_handler_name or crud_name)
    )
    validation = bool(name_token_set & VALIDATION_NAME_TOKENS)

    signals = {
        "testing": test_name or test_path,
        "main_entry_point": name_lower == "main",
        "web_api_handler": web_api_handler,
        "cli_argument_processing": cli_name or cli_path or decorators["cli_decorator"],
        "validation_parsing_conversion": validation,
    }
    flags = {
        "test_name": test_name,
        "test_path": test_path,
        "web_api_path": web_api_path,
        "web_route_decorator": decorators["web_route_decorator"],
        "cli_name": cli_name,
        "cli_path": cli_path,
        "cli_decorator": decorators["cli_decorator"],
        "crud_name": crud_name,
        "migration_context": bool((name_token_set | path_token_set) & MIGRATION_TOKENS),
        "setup_lifecycle_name": bool(name_token_set & SETUP_LIFECYCLE_TOKENS),
        "builder_factory_name": bool(name_token_set & BUILDER_FACTORY_TOKENS),
        "has_decorator": bool(decorator_callables),
    }
    matched = [name for name in SIGNAL_NAMES if signals[name]]
    role = assign_role(signals)
    return {
        "signals": signals,
        "flags": flags,
        "matched_signals": matched,
        "signal_count": len(matched),
        "candidate_primary_role": role,
        "name_tokens": name_tokens,
        "path_tokens": sorted(path_token_set),
    }


def assign_role(signals: Mapping[str, bool]) -> str:
    for role in ROLE_PRECEDENCE:
        if bool(signals.get(role, False)):
            return role
    return "other_general"


def audit_stratum(features: Mapping[str, Any]) -> str:
    signals = features["signals"]
    flags = features["flags"]
    if int(features["signal_count"]) > 1:
        return "multi_signal"
    if signals["testing"]:
        if flags["test_name"] and flags["test_path"]:
            return "testing_name_and_path"
        if flags["test_path"]:
            return "testing_path_only"
        return "testing_name_only"
    role = str(features["candidate_primary_role"])
    mapping = {
        "validation_parsing_conversion": "validation_only",
        "web_api_handler": "web_api_only",
        "cli_argument_processing": "cli_only",
        "main_entry_point": "main_only",
        "other_general": "other_general",
    }
    return mapping[role]


def require_columns(fieldnames: Sequence[str] | None, required: Iterable[str], label: str) -> None:
    available = set(fieldnames or [])
    missing = sorted(set(required) - available)
    if missing:
        raise ValidationError(f"{label} is missing columns {missing}; available={sorted(available)}")


def binary_value(value: str, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "1.0", "true", "t", "yes"}:
        return True
    if normalized in {"0", "0.0", "false", "f", "no"}:
        return False
    raise ValidationError(f"Invalid binary value for {label}: {value!r}")


def stable_key(row: Mapping[str, str], columns: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(row.get(column, "")).strip() for column in columns)


def role_rule_rows() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "name": "testing",
            "kind": "primary_candidate",
            "condition": "function name starts with test or ends with _test, OR path token is test/tests/testing",
            "precedence": 1,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 2,
            "name": "main_entry_point",
            "kind": "primary_candidate",
            "condition": "exact normalized function name is main",
            "precedence": 2,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 3,
            "name": "web_api_handler",
            "kind": "primary_candidate",
            "condition": "recognized route decorator, OR web/API path plus handler/view/endpoint/route or CRUD name token",
            "precedence": 3,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 4,
            "name": "cli_argument_processing",
            "kind": "primary_candidate",
            "condition": "CLI path token, CLI/argument name signal, or Click/Typer decorator signal",
            "precedence": 4,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 5,
            "name": "validation_parsing_conversion",
            "kind": "primary_candidate",
            "condition": "function-name token denotes validation, parsing, conversion, serialization, normalization, sanitization, encoding, decoding, coercion, verification, or transformation",
            "precedence": 5,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 6,
            "name": "other_general",
            "kind": "exhaustive_fallback",
            "condition": "no higher-precedence primary candidate signal",
            "precedence": 6,
            "status": TAXONOMY_STATUS,
        },
        {
            "order": 7,
            "name": "has_decorator",
            "kind": "structural_flag",
            "condition": "one or more decorators are attached to the function",
            "precedence": "",
            "status": "FLAG_ONLY",
        },
        {
            "order": 8,
            "name": "multi_signal",
            "kind": "ambiguity_audit_flag",
            "condition": "two or more primary candidate signals are true; candidate assignment uses precedence",
            "precedence": "",
            "status": "AUDIT_ONLY_NOT_A_CATEGORY",
        },
    ]


def scan_full_history(
    path: Path,
    expected_rows: int,
    progress_every: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    role_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    overlap_counts: Counter[str] = Counter()
    role_repositories: defaultdict[str, set[str]] = defaultdict(set)
    role_commits: defaultdict[str, set[tuple[str, str, str]]] = defaultdict(set)
    role_decorated: Counter[str] = Counter()
    source_counts: Counter[tuple[str, str]] = Counter()
    sampler = DeterministicSampler(AUDIT_STRATUM_QUOTAS)
    rows_read = 0
    module_sync_rows = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, FULL_HISTORY_REQUIRED_COLUMNS, "run-py-7f02 function inventory")
        for rows_read, row in enumerate(reader, start=1):
            if progress_every > 0 and rows_read % progress_every == 0:
                print(f"Full-history progress: {rows_read:,} function rows read", flush=True)
            if not binary_value(row["is_module_level"], "is_module_level"):
                continue
            if binary_value(row["is_async"], "is_async"):
                continue
            module_sync_rows += 1
            callables = parse_json_string_list(
                row["decorators_callable_json"],
                "decorators_callable_json",
            )
            features = classify_features(row["function_name"], row["relative_path"], callables)
            role = features["candidate_primary_role"]
            role_counts[role] += 1
            role_repositories[role].add(row["repo_name"])
            role_commits[role].add(
                (row["dataset_source"], row["repo_name"], row["latest_commit"])
            )
            role_decorated[role] += int(features["flags"]["has_decorator"])
            source_counts[(role, row["dataset_source"])] += 1
            for name, active in features["signals"].items():
                signal_counts[name] += int(active)
            for name, active in features["flags"].items():
                flag_counts[name] += int(active)
            combination = "|".join(features["matched_signals"]) or "none"
            overlap_counts[combination] += 1

            sample_row = {
                key: row[key]
                for key in [
                    "dataset_source",
                    "repo_name",
                    "latest_commit",
                    "relative_path",
                    "git_blob_sha",
                    "function_ordinal",
                    "qualified_function_name",
                    "function_name",
                    "start_line",
                    "end_line",
                    "decorator_count",
                    "decorators_callable_json",
                    "function_source_sha256",
                ]
            }
            sample_row.update(
                {
                    "candidate_primary_role": role,
                    "matched_signals": combination,
                    "signal_count": str(features["signal_count"]),
                    **{
                        name: str(int(active))
                        for name, active in features["signals"].items()
                    },
                    **{
                        name: str(int(active))
                        for name, active in features["flags"].items()
                    },
                }
            )
            sampler.consider(audit_stratum(features), sample_row)

    if rows_read != expected_rows:
        raise ValidationError(
            f"Full-history function row count mismatch: {rows_read} != {expected_rows}"
        )
    if module_sync_rows <= 0:
        raise ValidationError("No synchronous module-level functions were found")

    role_summary = []
    for role in PRIMARY_ROLES:
        role_summary.append(
            {
                "candidate_primary_role": role,
                "function_occurrences": role_counts[role],
                "repositories": len(role_repositories[role]),
                "repository_commits": len(role_commits[role]),
                "decorated_function_occurrences": role_decorated[role],
                "share_of_module_sync_functions": role_counts[role] / module_sync_rows,
            }
        )
    source_summary = [
        {
            "candidate_primary_role": role,
            "dataset_source": source,
            "function_occurrences": source_counts[(role, source)],
        }
        for role in PRIMARY_ROLES
        for source in ["control", "treatment"]
    ]
    signal_summary = [
        {
            "signal_or_flag": name,
            "kind": "primary_signal" if name in SIGNAL_NAMES else "structural_or_descriptive_flag",
            "function_occurrences": signal_counts[name] if name in SIGNAL_NAMES else flag_counts[name],
            "share_of_module_sync_functions": (
                (signal_counts[name] if name in SIGNAL_NAMES else flag_counts[name])
                / module_sync_rows
            ),
        }
        for name in [*SIGNAL_NAMES, *FLAG_NAMES]
    ]
    overlap_summary = [
        {
            "matched_signal_combination": combination,
            "function_occurrences": count,
            "share_of_module_sync_functions": count / module_sync_rows,
        }
        for combination, count in sorted(
            overlap_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return (
        {
            "rows_read": rows_read,
            "module_sync_rows": module_sync_rows,
            "role_summary": role_summary,
            "source_summary": source_summary,
            "signal_summary": signal_summary,
            "overlap_summary": overlap_summary,
        },
        sampler.rows(),
    )


def extract_sample_sources(
    rows: list[dict[str, str]],
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    max_characters: int,
) -> tuple[list[dict[str, Any]], int, int]:
    failures = 0
    hash_mismatches = 0
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        clone_root = treatment_clone_dir if row["dataset_source"] == "treatment" else control_clone_dir
        repo_dir = clone_root / row["repo_name"].replace("/", "_")
        command = ["git", "-C", str(repo_dir), "cat-file", "blob", row["git_blob_sha"]]
        completed = subprocess.run(command, capture_output=True, check=False)
        source_text = ""
        error_message = ""
        extracted_hash = ""
        source_truncated = 0
        full_characters = 0
        full_lines = 0
        if completed.returncode != 0:
            failures += 1
            error_message = completed.stderr.decode("utf-8", errors="replace").strip()
        else:
            try:
                file_source = decode_python_bytes(completed.stdout)
                lines = file_source.splitlines(keepends=True)
                start_line = int(row["start_line"])
                end_line = int(row["end_line"])
                function_source = "".join(lines[start_line - 1 : end_line])
                extracted_hash = hashlib.sha256(function_source.encode("utf-8")).hexdigest()
                if extracted_hash != row["function_source_sha256"]:
                    hash_mismatches += 1
                    error_message = (
                        "function source SHA mismatch: "
                        f"{extracted_hash} != {row['function_source_sha256']}"
                    )
                full_characters = len(function_source)
                full_lines = len(function_source.splitlines())
                source_truncated = int(full_characters > max_characters)
                source_text = function_source[:max_characters]
            except Exception as error:
                failures += 1
                error_message = str(error)

        output = dict(row)
        output.update(
            {
                "audit_sample_id": f"role-audit-{index:03d}",
                "extracted_function_source_sha256": extracted_hash,
                "source_hash_matches_inventory": int(
                    bool(extracted_hash) and extracted_hash == row["function_source_sha256"]
                ),
                "source_full_characters": full_characters,
                "source_full_lines": full_lines,
                "source_truncated": source_truncated,
                "source_extraction_error": error_message,
                "source_text": source_text,
                "manual_semantic_role": "",
                "manual_rule_correct": "",
                "manual_notes": "",
            }
        )
        result.append(output)
    return result, failures, hash_mismatches


def load_primary_body_rows(path: Path) -> tuple[list[dict[str, str]], dict[tuple[str, ...], dict[str, str]]]:
    rows: list[dict[str, str]] = []
    mapping: dict[tuple[str, ...], dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, PRIMARY_BODY_REQUIRED_COLUMNS, "run-py-7f01 body-month inventory")
        for row in reader:
            key = stable_key(row, PRIMARY_KEY_COLUMNS)
            if key in mapping:
                raise ValidationError(f"Duplicate primary body-month key: {key}")
            rows.append(row)
            mapping[key] = row
    return rows, mapping


def classify_primary_units(
    event_path: Path,
    body_path: Path,
    project_root: Path,
    expected_event_contexts: int,
    expected_body_months: int,
) -> dict[str, Any]:
    body_rows, body_map = load_primary_body_rows(body_path)
    if len(body_rows) != expected_body_months:
        raise ValidationError(
            f"Primary body-month count mismatch: {len(body_rows)} != {expected_body_months}"
        )
    aggregates: defaultdict[tuple[str, ...], UnitAggregate] = defaultdict(UnitAggregate)
    decorator_cache: dict[Path, list[str]] = {}
    event_count = 0
    parse_errors = 0

    with event_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, PRIMARY_EVENT_REQUIRED_COLUMNS, "run-py-7f01 event inventory")
        for event_count, row in enumerate(reader, start=1):
            key = stable_key(row, PRIMARY_KEY_COLUMNS)
            source_path = Path(row["source_path"])
            if not source_path.is_absolute():
                source_path = project_root / source_path
            source_path = source_path.resolve()
            try:
                if source_path not in decorator_cache:
                    decorator_cache[source_path] = parse_artifact_decorators(source_path)
                callables = decorator_cache[source_path]
            except Exception:
                parse_errors += 1
                raise
            features = classify_features(row["function_name"], row["relative_path"], callables)
            aggregate = aggregates[key]
            aggregate.event_contexts += 1
            aggregate.context_roles.add(features["candidate_primary_role"])
            aggregate.function_names.add(row["function_name"])
            aggregate.relative_paths.add(row["relative_path"])
            aggregate.decorator_callables.update(callables)
            for name, active in features["signals"].items():
                aggregate.signals[name] = aggregate.signals[name] or bool(active)
            for name, active in features["flags"].items():
                aggregate.flags[name] = aggregate.flags[name] or bool(active)

    if event_count != expected_event_contexts:
        raise ValidationError(
            f"Primary event-context count mismatch: {event_count} != {expected_event_contexts}"
        )
    if set(aggregates) != set(body_map):
        missing = len(set(body_map) - set(aggregates))
        extra = len(set(aggregates) - set(body_map))
        raise ValidationError(
            f"Primary event/body unit mismatch: missing={missing}, extra={extra}"
        )

    assignment_rows: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    role_repositories: defaultdict[str, set[str]] = defaultdict(set)
    signal_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    overlap_counts: Counter[str] = Counter()
    support_counts: Counter[tuple[str, str, str]] = Counter()
    context_disagreements = 0

    for body_row in body_rows:
        key = stable_key(body_row, PRIMARY_KEY_COLUMNS)
        aggregate = aggregates[key]
        role = assign_role(aggregate.signals)
        matched = [name for name in SIGNAL_NAMES if aggregate.signals[name]]
        combination = "|".join(matched) or "none"
        role_counts[role] += 1
        role_repositories[role].add(body_row["repo_name"])
        overlap_counts[combination] += 1
        source = body_row["dataset_source"]
        period = body_row["treatment_period"] or source
        support_counts[(role, source, period)] += 1
        context_disagreement = int(len(aggregate.context_roles) > 1)
        context_disagreements += context_disagreement
        for name, active in aggregate.signals.items():
            signal_counts[name] += int(active)
        for name, active in aggregate.flags.items():
            flag_counts[name] += int(active)
        assignment_rows.append(
            {
                **{column: body_row[column] for column in PRIMARY_KEY_COLUMNS},
                "time_to_event": body_row["time_to_event"],
                "treatment_period": body_row["treatment_period"],
                "event_context_count": body_row["event_context_count"],
                "function_names": body_row["function_names"],
                "relative_paths": body_row["relative_paths"],
                **{name: int(aggregate.signals[name]) for name in SIGNAL_NAMES},
                **{name: int(aggregate.flags[name]) for name in FLAG_NAMES},
                "matched_signals": combination,
                "signal_count": len(matched),
                "candidate_primary_role": role,
                "candidate_context_roles": "|".join(sorted(aggregate.context_roles)),
                "context_role_disagreement": context_disagreement,
                "decorator_callables": "|".join(sorted(aggregate.decorator_callables)),
                "taxonomy_status": TAXONOMY_STATUS,
            }
        )

    category_summary = [
        {
            "candidate_primary_role": role,
            "body_month_units": role_counts[role],
            "repositories": len(role_repositories[role]),
            "share_of_primary_body_month_units": role_counts[role] / len(body_rows),
        }
        for role in PRIMARY_ROLES
    ]
    support_summary = [
        {
            "candidate_primary_role": role,
            "dataset_source": source,
            "treatment_period": period,
            "body_month_units": count,
        }
        for (role, source, period), count in sorted(support_counts.items())
    ]
    signal_summary = [
        {
            "signal_or_flag": name,
            "kind": "primary_signal" if name in SIGNAL_NAMES else "structural_or_descriptive_flag",
            "body_month_units": signal_counts[name] if name in SIGNAL_NAMES else flag_counts[name],
            "share_of_primary_body_month_units": (
                (signal_counts[name] if name in SIGNAL_NAMES else flag_counts[name])
                / len(body_rows)
            ),
        }
        for name in [*SIGNAL_NAMES, *FLAG_NAMES]
    ]
    overlap_summary = [
        {
            "matched_signal_combination": combination,
            "body_month_units": count,
            "share_of_primary_body_month_units": count / len(body_rows),
        }
        for combination, count in sorted(
            overlap_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return {
        "event_contexts": event_count,
        "body_month_units": len(body_rows),
        "source_parse_errors": parse_errors,
        "context_role_disagreements": context_disagreements,
        "assignment_rows": assignment_rows,
        "category_summary": category_summary,
        "support_summary": support_summary,
        "signal_summary": signal_summary,
        "overlap_summary": overlap_summary,
        "category_total": sum(role_counts.values()),
    }


def atomic_write_csv(rows: Sequence[Mapping[str, Any]], path: Path, fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def atomic_write_json(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_staging(output_dir: Path, overwrite: bool) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. Use --overwrite-output for intentional replacement."
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging.", dir=output_dir.parent))


def commit_staging(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if any(output_dir.iterdir()) and not overwrite:
            raise FileExistsError(f"Output directory became non-empty during execution: {output_dir}")
        shutil.rmtree(output_dir)
    os.replace(staging, output_dir)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError(f"Expected JSON object: {path}")
    return payload


def add_qc(
    rows: list[dict[str, Any]],
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
    severity: str = "critical",
) -> None:
    rows.append(
        {
            "check_name": name,
            "severity": severity,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def candidate_taxonomy_payload() -> dict[str, Any]:
    return {
        "schema_version": SCRIPT_VERSION,
        "taxonomy_status": TAXONOMY_STATUS,
        "primary_candidate_roles": PRIMARY_ROLES,
        "precedence": PRIMARY_ROLES,
        "ambiguity_policy": {
            "candidate_assignment": "highest-precedence active signal",
            "multi_signal_primary_category": False,
            "multi_signal_retained_for_manual_audit": True,
        },
        "exhaustiveness_policy": "assign no-signal units to other_general",
        "decorator_policy": "retain has_decorator and decorator callables as structural flags; never assign decorator as a primary role",
        "audit_stratum_quotas": AUDIT_STRATUM_QUOTAS,
        "rule_tokens": {
            "test_path_tokens": sorted(TEST_PATH_TOKENS),
            "cli_path_tokens": sorted(CLI_PATH_TOKENS),
            "cli_name_tokens": sorted(CLI_NAME_TOKENS),
            "cli_name_exact": sorted(CLI_NAME_EXACT),
            "web_path_tokens": sorted(WEB_PATH_TOKENS),
            "web_name_tokens": sorted(WEB_NAME_TOKENS),
            "crud_name_tokens": sorted(CRUD_NAME_TOKENS),
            "validation_name_tokens": sorted(VALIDATION_NAME_TOKENS),
        },
        "prohibited_at_this_stage": [
            "role-specific zero-inclusive repository-month outcomes",
            "ATT estimates",
            "standard errors",
            "confidence intervals",
            "p-values",
        ],
    }


def run_self_test() -> None:
    cases = [
        ("test_api", "src/api/views.py", [], "testing"),
        ("main", "cli/commands.py", [], "main_entry_point"),
        ("validate_request", "api/routes.py", ["router.post"], "web_api_handler"),
        ("parse_args", "src/tool.py", [], "cli_argument_processing"),
        ("normalize_value", "src/utils.py", [], "validation_parsing_conversion"),
        ("calculate_total", "src/math.py", ["cache"], "other_general"),
    ]
    for name, path, decorators, expected in cases:
        observed = classify_features(name, path, decorators)
        if observed["candidate_primary_role"] != expected:
            raise AssertionError((name, path, expected, observed))
    testing = classify_features("helper", "tests/conftest.py", [])
    if not testing["signals"]["testing"] or testing["flags"]["test_name"]:
        raise AssertionError("Test-path-only classification failed")
    decorated = classify_features("health", "src/api.py", ["router.get"])
    if not decorated["flags"]["has_decorator"] or not decorated["signals"]["web_api_handler"]:
        raise AssertionError("Decorator structural/web signal failed")
    if assign_role({name: False for name in SIGNAL_NAMES}) != "other_general":
        raise AssertionError("Exhaustive fallback failed")
    if sum(AUDIT_STRATUM_QUOTAS.values()) != 240:
        raise AssertionError("Audit quotas must sum to 240")
    sampler = DeterministicSampler(AUDIT_STRATUM_QUOTAS)
    for stratum, quota in AUDIT_STRATUM_QUOTAS.items():
        for index in range(quota + 3):
            sampler.consider(
                stratum,
                {
                    "dataset_source": "control" if index % 2 == 0 else "treatment",
                    "repo_name": f"owner/repository-{stratum}",
                    "latest_commit": f"{index + 1:040x}",
                    "relative_path": f"src/{stratum}_{index}.py",
                    "function_ordinal": str(index + 1),
                    "function_source_sha256": hashlib.sha256(
                        f"{stratum}:{index}".encode("utf-8")
                    ).hexdigest(),
                },
            )
    sampled = sampler.rows()
    sampled_counts = Counter(row["audit_stratum"] for row in sampled)
    if len(sampled) != 240 or sampled_counts != Counter(AUDIT_STRATUM_QUOTAS):
        raise AssertionError("Deterministic audit sampling quotas failed")
    if len({row["sample_hash"] for row in sampled}) != len(sampled):
        raise AssertionError("Deterministic audit samples are not unique")
    print("Self-test: PASS")


def run(args: argparse.Namespace) -> None:
    if sys.version_info < (3, 13):
        found = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        raise ValidationError(
            f"Python 3.13 or newer is required for run-py-7f06; found {found}"
        )
    if args.progress_every <= 0:
        raise ValidationError("--progress-every must be positive")
    if args.audit_source_max_characters <= 0:
        raise ValidationError("--audit-source-max-characters must be positive")
    for value, label in [
        (args.expected_full_history_function_rows, "expected full-history rows"),
        (args.expected_primary_event_contexts, "expected primary event contexts"),
        (args.expected_primary_body_months, "expected primary body-months"),
        (args.expected_audit_samples, "expected audit samples"),
    ]:
        if value <= 0:
            raise ValidationError(f"{label} must be positive")

    full_history_function_inventory = require_file(
        args.full_history_function_inventory.resolve(),
        "run-py-7f02 function inventory",
    )
    full_history_metadata_path = require_file(
        args.full_history_metadata.resolve(),
        "run-py-7f02 metadata",
    )
    primary_event_inventory = require_file(
        args.primary_event_inventory.resolve(),
        "run-py-7f01 event inventory",
    )
    primary_body_inventory = require_file(
        args.primary_body_month_inventory.resolve(),
        "run-py-7f01 body-month inventory",
    )
    primary_metadata_path = require_file(
        args.primary_metadata.resolve(),
        "run-py-7f01 metadata",
    )
    adjudication_metadata_path = require_file(
        args.adjudication_metadata.resolve(),
        "run-py-7f05 metadata",
    )
    treatment_clone_dir = require_directory(args.treatment_clone_dir.resolve(), "treatment clone root")
    control_clone_dir = require_directory(args.control_clone_dir.resolve(), "control clone root")
    project_root = require_directory(args.project_root.resolve(), "project root")
    output_dir = args.output_dir.resolve()

    full_metadata = load_json(full_history_metadata_path)
    primary_metadata = load_json(primary_metadata_path)
    adjudication_metadata = load_json(adjudication_metadata_path)

    if full_metadata.get("script_version") != "run-py-7f02-v2":
        raise ValidationError("run-py-7f02 metadata must report script_version run-py-7f02-v2")
    if not str(full_metadata.get("parser_version", "")).startswith("python-ast-raw-structure-v2-"):
        raise ValidationError("run-py-7f02 metadata must report parser v2")
    if not str(full_metadata.get("status", "")).startswith("PASS"):
        raise ValidationError("run-py-7f02 metadata status must start with PASS")
    metadata_function_rows = int(full_metadata.get("counts", {}).get("function_inventory_rows", -1))
    if metadata_function_rows != args.expected_full_history_function_rows:
        raise ValidationError(
            "run-py-7f02 metadata function count mismatch: "
            f"{metadata_function_rows} != {args.expected_full_history_function_rows}"
        )
    if primary_metadata.get("script_version") != "run-py-7f01-v1":
        raise ValidationError("run-py-7f01 metadata must report run-py-7f01-v1")
    if primary_metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f01 metadata status must be PASS")
    if primary_metadata.get("feature_policy", {}).get("semantic_role_taxonomy") != "none":
        raise ValidationError("run-py-7f01 input must predate semantic-role taxonomy")
    if adjudication_metadata.get("schema_version") != "run-py-7f05-v1":
        raise ValidationError("run-py-7f05 metadata must report schema run-py-7f05-v1")
    if adjudication_metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f05 metadata status must be PASS")

    staging = prepare_staging(output_dir, args.overwrite_output)
    try:
        full, selected_samples = scan_full_history(
            full_history_function_inventory,
            args.expected_full_history_function_rows,
            args.progress_every,
        )
        audit_rows, extraction_failures, hash_mismatches = extract_sample_sources(
            selected_samples,
            treatment_clone_dir,
            control_clone_dir,
            args.audit_source_max_characters,
        )
        primary = classify_primary_units(
            primary_event_inventory,
            primary_body_inventory,
            project_root,
            args.expected_primary_event_contexts,
            args.expected_primary_body_months,
        )

        qc_rows: list[dict[str, Any]] = []
        add_qc(qc_rows, "run_py_7f02_v2_pass", True, full_metadata.get("status"), "PASS*", "Full-history inventory must be parser-v2 and PASS.")
        add_qc(qc_rows, "run_py_7f05_adjudication_pass", True, adjudication_metadata.get("status"), "PASS", "Residual source adjudication must be locked first.")
        add_qc(qc_rows, "full_history_function_rows", full["rows_read"] == args.expected_full_history_function_rows, full["rows_read"], args.expected_full_history_function_rows, "All run-py-7f02 function rows must be streamed exactly once.")
        add_qc(qc_rows, "full_history_module_sync_functions_positive", full["module_sync_rows"] > 0, full["module_sync_rows"], ">0", "Taxonomy audit scope is synchronous module-level functions.")
        add_qc(qc_rows, "audit_sample_rows", len(audit_rows) == args.expected_audit_samples, len(audit_rows), args.expected_audit_samples, "Deterministic stratum quotas must be filled.")
        add_qc(qc_rows, "audit_sample_keys_unique", len({row["sample_hash"] for row in audit_rows}) == len(audit_rows), len({row["sample_hash"] for row in audit_rows}), len(audit_rows), "A full-history function may appear in at most one audit stratum.")
        add_qc(qc_rows, "audit_source_extraction_failures", extraction_failures == 0, extraction_failures, 0, "Every audit sample must be extracted from its immutable Git blob.")
        add_qc(qc_rows, "audit_source_hash_mismatches", hash_mismatches == 0, hash_mismatches, 0, "Extracted function source must match the run-py-7f02 inventory SHA.")
        add_qc(qc_rows, "primary_event_contexts", primary["event_contexts"] == args.expected_primary_event_contexts, primary["event_contexts"], args.expected_primary_event_contexts, "The locked run-py-7f01 event scope must be reproduced.")
        add_qc(qc_rows, "primary_body_month_units", primary["body_month_units"] == args.expected_primary_body_months, primary["body_month_units"], args.expected_primary_body_months, "The locked run-py-7f01 counting units must be reproduced.")
        add_qc(qc_rows, "primary_category_sum", primary["category_total"] == args.expected_primary_body_months, primary["category_total"], args.expected_primary_body_months, "Candidate categories must sum to all 2,249 body-month units.")
        add_qc(qc_rows, "duplicate_primary_assignments", len(primary["assignment_rows"]) == len({stable_key(row, PRIMARY_KEY_COLUMNS) for row in primary["assignment_rows"]}), len(primary["assignment_rows"]) - len({stable_key(row, PRIMARY_KEY_COLUMNS) for row in primary["assignment_rows"]}), 0, "Each body-month unit must receive exactly one candidate role.")
        add_qc(qc_rows, "unassigned_primary_units", all(row["candidate_primary_role"] in PRIMARY_ROLES for row in primary["assignment_rows"]), sum(row["candidate_primary_role"] not in PRIMARY_ROLES for row in primary["assignment_rows"]), 0, "No unit may remain unassigned; no-signal units use other_general.")
        add_qc(qc_rows, "primary_artifact_parse_errors", primary["source_parse_errors"] == 0, primary["source_parse_errors"], 0, "Decorator flags must be recovered from every selected function artifact.")
        add_qc(qc_rows, "taxonomy_not_frozen", TAXONOMY_STATUS == "CANDIDATE_NOT_FROZEN", TAXONOMY_STATUS, "CANDIDATE_NOT_FROZEN", "Manual audit must occur before final taxonomy freeze.")

        failed_critical = sum(
            row["severity"] == "critical" and not row["passed"] for row in qc_rows
        )
        status = "PASS" if failed_critical == 0 else "FAIL"

        rules_path = staging / "run-py-7f06-candidate-role-rules.csv"
        taxonomy_path = staging / "run-py-7f06-candidate-taxonomy.json"
        full_role_path = staging / "run-py-7f06-full-history-candidate-role-summary.csv"
        full_source_path = staging / "run-py-7f06-full-history-candidate-role-by-source.csv"
        full_signal_path = staging / "run-py-7f06-full-history-signal-summary.csv"
        full_overlap_path = staging / "run-py-7f06-full-history-signal-overlaps.csv"
        audit_path = staging / "run-py-7f06-outcome-blind-source-audit-samples.csv"
        primary_assignments_path = staging / "run-py-7f06-primary-body-month-candidate-assignments.csv"
        primary_role_path = staging / "run-py-7f06-primary-candidate-role-summary.csv"
        primary_support_path = staging / "run-py-7f06-primary-candidate-role-support.csv"
        primary_signal_path = staging / "run-py-7f06-primary-signal-summary.csv"
        primary_overlap_path = staging / "run-py-7f06-primary-signal-overlaps.csv"
        qc_path = staging / "run-py-7f06-taxonomy-audit-qc.csv"
        metadata_path = staging / "run-py-7f06-taxonomy-audit-metadata.json"

        atomic_write_csv(role_rule_rows(), rules_path, ["order", "name", "kind", "condition", "precedence", "status"])
        atomic_write_json(candidate_taxonomy_payload(), taxonomy_path)
        atomic_write_csv(full["role_summary"], full_role_path, ["candidate_primary_role", "function_occurrences", "repositories", "repository_commits", "decorated_function_occurrences", "share_of_module_sync_functions"])
        atomic_write_csv(full["source_summary"], full_source_path, ["candidate_primary_role", "dataset_source", "function_occurrences"])
        atomic_write_csv(full["signal_summary"], full_signal_path, ["signal_or_flag", "kind", "function_occurrences", "share_of_module_sync_functions"])
        atomic_write_csv(full["overlap_summary"], full_overlap_path, ["matched_signal_combination", "function_occurrences", "share_of_module_sync_functions"])
        audit_fields = [
            "audit_sample_id", "audit_stratum", "sample_hash", "dataset_source", "repo_name", "latest_commit", "relative_path", "git_blob_sha", "function_ordinal", "qualified_function_name", "function_name", "start_line", "end_line", "decorator_count", "decorators_callable_json", *SIGNAL_NAMES, *FLAG_NAMES, "matched_signals", "signal_count", "candidate_primary_role", "function_source_sha256", "extracted_function_source_sha256", "source_hash_matches_inventory", "source_full_characters", "source_full_lines", "source_truncated", "source_extraction_error", "source_text", "manual_semantic_role", "manual_rule_correct", "manual_notes",
        ]
        atomic_write_csv(audit_rows, audit_path, audit_fields)
        assignment_fields = [
            *PRIMARY_KEY_COLUMNS, "time_to_event", "treatment_period", "event_context_count", "function_names", "relative_paths", *SIGNAL_NAMES, *FLAG_NAMES, "matched_signals", "signal_count", "candidate_primary_role", "candidate_context_roles", "context_role_disagreement", "decorator_callables", "taxonomy_status",
        ]
        atomic_write_csv(primary["assignment_rows"], primary_assignments_path, assignment_fields)
        atomic_write_csv(primary["category_summary"], primary_role_path, ["candidate_primary_role", "body_month_units", "repositories", "share_of_primary_body_month_units"])
        atomic_write_csv(primary["support_summary"], primary_support_path, ["candidate_primary_role", "dataset_source", "treatment_period", "body_month_units"])
        atomic_write_csv(primary["signal_summary"], primary_signal_path, ["signal_or_flag", "kind", "body_month_units", "share_of_primary_body_month_units"])
        atomic_write_csv(primary["overlap_summary"], primary_overlap_path, ["matched_signal_combination", "body_month_units", "share_of_primary_body_month_units"])
        atomic_write_csv(qc_rows, qc_path, ["check_name", "severity", "passed", "observed", "expected", "note"])

        metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": status,
            "taxonomy_status": TAXONOMY_STATUS,
            "scientific_scope": {
                "full_history_audit_is_outcome_blind": True,
                "full_history_inputs": "run-py-7f02 v2 function inventory and immutable Git blobs",
                "primary_compatibility_input": "locked run-py-7f01 body-month inventory",
                "role_specific_monthly_outcomes_created": False,
                "att_or_uncertainty_computed": False,
                "decorator_is_primary_role": False,
            },
            "counts": {
                "full_history_function_rows": full["rows_read"],
                "full_history_synchronous_module_functions": full["module_sync_rows"],
                "audit_samples": len(audit_rows),
                "audit_source_extraction_failures": extraction_failures,
                "audit_source_hash_mismatches": hash_mismatches,
                "primary_event_contexts": primary["event_contexts"],
                "primary_body_month_units": primary["body_month_units"],
                "primary_category_sum": primary["category_total"],
                "primary_context_role_disagreements": primary["context_role_disagreements"],
                "critical_qc_failures": failed_critical,
            },
            "inputs": {
                "full_history_function_inventory": str(args.full_history_function_inventory),
                "full_history_metadata": {
                    "path": str(args.full_history_metadata),
                    "sha256": sha256_file(full_history_metadata_path),
                },
                "primary_event_inventory": {
                    "path": str(args.primary_event_inventory),
                    "sha256": sha256_file(primary_event_inventory),
                },
                "primary_body_month_inventory": {
                    "path": str(args.primary_body_month_inventory),
                    "sha256": sha256_file(primary_body_inventory),
                },
                "primary_metadata": {
                    "path": str(args.primary_metadata),
                    "sha256": sha256_file(primary_metadata_path),
                },
                "adjudication_metadata": {
                    "path": str(args.adjudication_metadata),
                    "sha256": sha256_file(adjudication_metadata_path),
                },
            },
            "outputs": {
                "candidate_rules": rules_path.name,
                "candidate_taxonomy": taxonomy_path.name,
                "outcome_blind_source_audit_samples": audit_path.name,
                "primary_candidate_assignments": primary_assignments_path.name,
                "qc": qc_path.name,
            },
        }
        atomic_write_json(metadata, metadata_path)
        if failed_critical:
            raise ValidationError(f"run-py-7f06 has {failed_critical} critical QC failure(s)")
        commit_staging(staging, output_dir, args.overwrite_output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print("run-py-7f06 taxonomy audit complete")
    print(f"Full-history function rows:          {full['rows_read']:,}")
    print(f"Synchronous module functions:        {full['module_sync_rows']:,}")
    print(f"Outcome-blind source audit samples:  {len(audit_rows):,}")
    print(f"Primary body-month units:            {primary['body_month_units']:,}")
    print(f"Candidate category sum:              {primary['category_total']:,}")
    print(f"Critical QC failures:                {failed_critical}")
    print(f"Taxonomy status:                     {TAXONOMY_STATUS}")
    print(f"Output directory:                    {output_dir}")
    print(f"Status:                              {status}")


def main() -> int:
    args = parse_args()
    if args.self_test_only:
        run_self_test()
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, ValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
