#!/usr/bin/env python3
"""Build an outcome-aligned empirical inventory for AGC-like class methods.

This run-py-7f12 diagnostic scans the exact Git blobs in the matched treatment
and control clones. It focuses on synchronous direct class-scope methods
(``function_kind == "method"``) that are AGC-like under the frozen
``range100_200`` NPR specification and occur in the Python-NCLOC model-ready,
parse-clean repository-month sample used by run-py-7f.

The stage is taxonomy-free. It records observable method names, containing
class names, path tokens, decorators, parameters, docstrings, calls, AST
features, and deterministic source samples. It does not assign semantic roles
and does not estimate a Difference-in-Differences model.
"""

from __future__ import annotations

import argparse
import ast
import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd


SCRIPT_VERSION = "run-py-7f12-v2"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
UNIT_COLUMNS = [*KEY_COLUMNS, "function_body_sha256"]
READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_"
    "python_snapshot_ncloc"
)
FUNCTION_KIND = "method"

EVENT_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "function_event_id",
    "function_body_sha256",
    "function_kind",
    "npr_agc_like",
]

MANIFEST_REQUIRED_COLUMNS = [
    "function_event_id",
    *KEY_COLUMNS,
    "commit",
    "relative_path",
    "qualified_function_name",
    "function_name",
    "function_kind",
    "occurrence_index",
]

PANEL_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "time_to_event",
    READY_COLUMN,
]

SCAN_ERROR_COLUMNS = [
    "function_event_id",
    "dataset_source",
    "repo_name",
    "commit",
    "relative_path",
    "qualified_function_name",
    "occurrence_index",
    "stage",
    "error_type",
    "error",
]

DOCSTRING_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan exact cloned-repository Git blobs for AGC-like synchronous "
            "class methods and produce empirical distributions before role design."
        )
    )
    parser.add_argument(
        "--event-classifications",
        type=Path,
        default=Path(
            "repo_python/run-py-7a/strict/specifications/range100_200/"
            "agc_commit_function_npr_event_classifications.csv"
        ),
    )
    parser.add_argument(
        "--function-manifest",
        type=Path,
        default=Path(
            "repo_python/run-py-5a-py312/strict/"
            "commit_function_detection_manifest.csv"
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
        "--analysis-panel",
        type=Path,
        default=Path(
            "repo_python/run-py-7e/strict/specifications/range100_200/"
            "panel_event_monthly_regular_module_function_agc_unique_body_"
            "parse_clean.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "repo_python/run-py-7f12/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean"
        ),
    )
    parser.add_argument("--audit-sample-size", type=int, default=240)
    parser.add_argument("--expected-panel-rows", type=int, default=1536)
    parser.add_argument("--expected-model-rows", type=int, default=1521)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    label: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValidationError(
            f"{label} is missing required columns: {missing}. "
            f"Available columns: {list(frame.columns)}"
        )


def require_unique(
    frame: pd.DataFrame,
    columns: Sequence[str],
    label: str,
) -> None:
    duplicate = frame.duplicated(list(columns), keep=False)
    if duplicate.any():
        sample = frame.loc[duplicate, list(columns)].head(20)
        raise ValidationError(
            f"{label} contains duplicate keys for {list(columns)}:\n"
            f"{sample.to_string(index=False)}"
        )


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in KEY_COLUMNS:
        result[column] = result[column].fillna("").astype("string").str.strip()
    result["time"] = result["time"].str[:7]
    return result


def normalize_binary(series: pd.Series, label: str) -> pd.Series:
    text = series.fillna("").astype("string").str.strip().str.lower()
    mapping = {
        "1": 1,
        "1.0": 1,
        "true": 1,
        "t": 1,
        "yes": 1,
        "0": 0,
        "0.0": 0,
        "false": 0,
        "f": 0,
        "no": 0,
    }
    result = text.map(mapping)
    if result.isna().any():
        examples = series.loc[result.isna()].head(20).tolist()
        raise ValidationError(f"{label} contains non-binary values: {examples}")
    return result.astype("int8")


def to_nullable_integer(series: pd.Series, label: str) -> pd.Series:
    """Coerce integer-like values to nullable Int64.

    Control repository-months have no treatment event, so their relative time
    is undefined and legitimately missing. Pandas nullable Int64 preserves that
    missing marker while still rejecting fractional values.
    """
    numeric = pd.to_numeric(series, errors="raise")
    present = numeric.notna()
    fractional = present & numeric.ne(numeric.round())
    if fractional.any():
        examples = series.loc[fractional].head(20).tolist()
        raise ValidationError(
            f"{label} contains non-integer values: {examples}"
        )
    return numeric.astype("Int64")


def prepare_output_directory(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {path}. "
                "Use --overwrite-output for intentional replacement."
            )
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False, quoting=csv.QUOTE_MINIMAL)
    os.replace(temporary, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*values: Any) -> str:
    payload = "\0".join(str(value) for value in values).encode(
        "utf-8", errors="surrogateescape"
    )
    return hashlib.sha256(payload).hexdigest()


def ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def lexical_tokens(value: str) -> list[str]:
    split_acronym = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", str(value))
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", split_acronym)
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", split_camel)
        if token
    ]


def path_tokens(value: str) -> list[str]:
    path = PurePosixPath(str(value).replace("\\", "/"))
    tokens: list[str] = []
    for part in path.parts:
        stem = PurePosixPath(part).stem
        tokens.extend(lexical_tokens(stem))
    return ordered_unique(tokens)


def repo_slug(repo_name: str) -> str:
    return str(repo_name).replace("/", "_")


def decode_python_source(payload: bytes) -> str:
    reader = io.BytesIO(payload).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return payload.decode(encoding)


def read_git_blob(repo_dir: Path, commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "show", f"{commit}:{relative_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Cannot read Git blob {commit}:{relative_path}: {message}"
        )
    return result.stdout


def callable_name(node: ast.AST) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    return expression_name(target)


def definition_start_line(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int:
    decorator_lines = [
        int(item.lineno)
        for item in node.decorator_list
        if hasattr(item, "lineno")
    ]
    return min([int(node.lineno), *decorator_lines])


def render_standalone_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    rendered = ast.unparse(copy.deepcopy(node)).rstrip() + "\n"
    parsed = ast.parse(rendered, filename="<run-py-7f12-method>", type_comments=True)
    if (
        len(parsed.body) != 1
        or not isinstance(parsed.body[0], (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        raise ValidationError("Rendered method is not one standalone definition")
    return rendered


def iter_nested_statement_bodies(statement: ast.stmt) -> Iterator[Sequence[ast.stmt]]:
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(statement, field_name, None)
        if isinstance(value, list) and all(
            isinstance(item, ast.stmt) for item in value
        ):
            yield value
    handlers = getattr(statement, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            if isinstance(handler, ast.ExceptHandler):
                yield handler.body
    cases = getattr(statement, "cases", None)
    if isinstance(cases, list):
        for case in cases:
            body = getattr(case, "body", None)
            if isinstance(body, list):
                yield body


def extract_synchronous_class_methods(
    source: str,
    source_label: str,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Reproduce run-py-5a identities and retain direct synchronous methods."""
    tree = ast.parse(source, filename=source_label, type_comments=True)
    occurrence_counts: Counter[str] = Counter()
    records: dict[tuple[str, int], dict[str, Any]] = {}

    def walk(
        statements: Sequence[ast.stmt],
        scope_names: list[str],
        scope_kinds: list[str],
        class_stack: list[ast.ClassDef],
    ) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified_name = ".".join([*scope_names, statement.name])
                occurrence_counts[qualified_name] += 1
                occurrence_index = occurrence_counts[qualified_name]
                is_direct_class_scope = bool(
                    scope_kinds and scope_kinds[-1] == "class"
                )
                is_async = isinstance(statement, ast.AsyncFunctionDef)
                if is_direct_class_scope and not is_async:
                    containing_class = class_stack[-1]
                    method_decorators = ordered_unique(
                        callable_name(item) for item in statement.decorator_list
                    )
                    class_decorators = ordered_unique(
                        callable_name(item)
                        for item in containing_class.decorator_list
                    )
                    class_bases = ordered_unique(
                        expression_name(item) or ast.unparse(item).strip()
                        for item in containing_class.bases
                    )
                    positional = [
                        *statement.args.posonlyargs,
                        *statement.args.args,
                    ]
                    first_parameter = positional[0].arg if positional else ""
                    rendered = render_standalone_function(statement)
                    decorator_terminals = ordered_unique(
                        item.rsplit(".", 1)[-1]
                        for item in method_decorators
                        if item
                    )
                    key = (qualified_name, occurrence_index)
                    if key in records:
                        raise ValidationError(
                            f"Duplicate extracted method identity: {key}"
                        )
                    records[key] = {
                        "git_qualified_function_name": qualified_name,
                        "git_function_name": statement.name,
                        "git_occurrence_index": occurrence_index,
                        "containing_class_name": containing_class.name,
                        "qualified_class_name": ".".join(scope_names),
                        "class_depth": len(class_stack),
                        "method_definition_line": int(statement.lineno),
                        "method_start_line": definition_start_line(statement),
                        "method_end_line": int(
                            getattr(statement, "end_lineno", statement.lineno)
                        ),
                        "function_name_tokens": ordered_unique(
                            lexical_tokens(statement.name)
                        ),
                        "class_name_tokens": ordered_unique(
                            lexical_tokens(containing_class.name)
                        ),
                        "method_decorator_callables": method_decorators,
                        "method_decorator_terminals": decorator_terminals,
                        "class_decorator_callables": class_decorators,
                        "class_base_names": class_bases,
                        "first_parameter_name": first_parameter,
                        "decorator_count": len(statement.decorator_list),
                        "has_classmethod_decorator": int(
                            "classmethod" in decorator_terminals
                        ),
                        "has_staticmethod_decorator": int(
                            "staticmethod" in decorator_terminals
                        ),
                        "has_property_decorator": int(
                            "property" in decorator_terminals
                        ),
                        "has_setter_decorator": int(
                            "setter" in decorator_terminals
                        ),
                        "has_deleter_decorator": int(
                            "deleter" in decorator_terminals
                        ),
                        "is_dunder_name": int(
                            len(statement.name) > 4
                            and statement.name.startswith("__")
                            and statement.name.endswith("__")
                        ),
                        "rendered_source_sha256": hashlib.sha256(
                            rendered.encode("utf-8")
                        ).hexdigest(),
                        "source_text": rendered,
                    }
                walk(
                    statement.body,
                    [*scope_names, statement.name],
                    [*scope_kinds, "function"],
                    class_stack,
                )
            elif isinstance(statement, ast.ClassDef):
                walk(
                    statement.body,
                    [*scope_names, statement.name],
                    [*scope_kinds, "class"],
                    [*class_stack, statement],
                )
            else:
                for nested_body in iter_nested_statement_bodies(statement):
                    walk(nested_body, scope_names, scope_kinds, class_stack)

    walk(tree.body, [], [], [])
    return records


def expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return expression_name(node.func)
    if isinstance(node, ast.Subscript):
        return expression_name(node.value)
    return ""


def walk_function_body(
    root: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    """Walk implementation statements without traversing root decorators."""
    for statement in root.body:
        yield from ast.walk(statement)


def source_features(source_text: str, source_label: str) -> dict[str, Any]:
    tree = ast.parse(source_text, filename=source_label, type_comments=True)
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if len(tree.body) != 1 or len(definitions) != 1:
        raise ValidationError(
            f"Source artifact is not exactly one named function: {source_label}"
        )
    root = definitions[0]
    body_nodes = list(walk_function_body(root))
    node_counts = Counter(type(node).__name__ for node in body_nodes)
    call_names = ordered_unique(
        expression_name(node.func)
        for node in body_nodes
        if isinstance(node, ast.Call)
    )
    call_terminals = ordered_unique(
        name.rsplit(".", 1)[-1] for name in call_names if name
    )
    document = ast.get_docstring(root, clean=True) or ""
    document_preview = re.sub(r"\s+", " ", document).strip()[:500]
    document_terms = [
        token
        for token in lexical_tokens(document_preview)
        if len(token) > 1 and token not in DOCSTRING_STOP_WORDS
    ]
    positional = [*root.args.posonlyargs, *root.args.args]
    keyword_only = list(root.args.kwonlyargs)
    nested_definitions = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in body_nodes
    )
    return {
        "source_line_count": len(source_text.splitlines()),
        "source_character_count": len(source_text),
        "body_top_level_statement_count": len(root.body),
        "positional_argument_count": len(positional),
        "keyword_only_argument_count": len(keyword_only),
        "has_vararg": int(root.args.vararg is not None),
        "has_kwarg": int(root.args.kwarg is not None),
        "has_docstring": int(bool(document)),
        "docstring_preview": document_preview,
        "docstring_terms": ordered_unique(document_terms),
        "call_names": call_names,
        "call_terminals": call_terminals,
        "called_function_count": len(call_names),
        "return_count": node_counts["Return"],
        "raise_count": node_counts["Raise"],
        "yield_count": node_counts["Yield"] + node_counts["YieldFrom"],
        "assert_count": node_counts["Assert"],
        "branch_count": node_counts["If"] + node_counts["Match"],
        "loop_count": node_counts["For"] + node_counts["AsyncFor"] + node_counts["While"],
        "with_count": node_counts["With"] + node_counts["AsyncWith"],
        "try_count": node_counts["Try"] + node_counts["TryStar"],
        "await_count": node_counts["Await"],
        "nested_definition_count": nested_definitions,
        "ast_node_count": len(body_nodes),
        "ast_node_types": ordered_unique(type(node).__name__ for node in body_nodes),
    }


def treatment_period(dataset_source: str, time_to_event: Any) -> str:
    if str(dataset_source).strip().lower() == "control":
        return "control"
    if pd.isna(time_to_event):
        raise ValidationError(
            "time_to_event is missing for a non-control row; only control "
            "repository-months may omit the relative-time anchor."
        )
    value = int(time_to_event)
    if value < 0:
        return "pre"
    if value == 0:
        return "event"
    return "post"


def join_model_scope(
    events: pd.DataFrame,
    manifest: pd.DataFrame,
    panel: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    expected: dict[str, int],
    progress_every: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    require_columns(events, EVENT_REQUIRED_COLUMNS, "Event classifications")
    require_columns(manifest, MANIFEST_REQUIRED_COLUMNS, "Function manifest")
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "Analysis panel")

    events = normalize_keys(events)
    manifest = normalize_keys(manifest)
    panel = normalize_keys(panel)
    require_unique(events, ["function_event_id"], "Event classifications")
    require_unique(manifest, ["function_event_id"], "Function manifest")
    require_unique(panel, KEY_COLUMNS, "Analysis panel")

    events["function_event_id"] = (
        events["function_event_id"].astype("string").str.strip()
    )
    events["function_body_sha256"] = (
        events["function_body_sha256"].astype("string").str.strip().str.lower()
    )
    events["function_kind"] = (
        events["function_kind"].astype("string").str.strip().str.lower()
    )
    events["npr_agc_like"] = normalize_binary(
        events["npr_agc_like"], "npr_agc_like"
    )

    full = events.loc[
        events["function_kind"].eq(FUNCTION_KIND)
        & events["npr_agc_like"].eq(1)
    ].copy()
    panel[READY_COLUMN] = normalize_binary(panel[READY_COLUMN], READY_COLUMN)
    # Control repository-months have no anchoring event. Preserve their
    # undefined relative time as pd.NA instead of forcing the full column to
    # plain int64, which raises IntCastingNaNError.
    panel["time_to_event"] = to_nullable_integer(
        panel["time_to_event"], "time_to_event"
    )

    checks: list[dict[str, Any]] = []

    def check(name: str, observed: Any, expected_value: Any, note: str) -> None:
        checks.append(
            {
                "check_name": name,
                "passed": bool(observed == expected_value),
                "observed": observed,
                "expected": expected_value,
                "note": note,
            }
        )

    model_panel = panel.loc[panel[READY_COLUMN].eq(1)].copy()
    control_rows = (
        model_panel["dataset_source"]
        .astype("string")
        .str.strip()
        .str.lower()
        .eq("control")
    )
    unanchored_non_control = (
        model_panel["time_to_event"].isna() & ~control_rows
    )
    check(
        "model_ready_relative_time_present_outside_control",
        int(unanchored_non_control.sum()),
        0,
        "Only control repository-months may omit time_to_event.",
    )
    if unanchored_non_control.any():
        sample = model_panel.loc[
            unanchored_non_control, [*KEY_COLUMNS, "time_to_event"]
        ].head(20)
        raise ValidationError(
            "Model-ready non-control rows have a missing time_to_event "
            "anchor:\n" + sample.to_string(index=False)
        )
    model_panel["treatment_period"] = [
        treatment_period(source, relative_time)
        for source, relative_time in zip(
            model_panel["dataset_source"],
            model_panel["time_to_event"],
        )
    ]

    check(
        "full_agc_class_method_events_present",
        int(len(full) > 0),
        1,
        "The frozen detector input must contain AGC-like synchronous methods.",
    )
    check(
        "full_agc_class_method_unique_bodies_present",
        int(full["function_body_sha256"].nunique() > 0),
        1,
        "The method inventory must contain at least one distinct AGC-like body.",
    )
    check(
        "parse_clean_panel_rows",
        int(len(panel)),
        expected["panel_rows"],
        "The scan must use the same parse-clean panel as run-py-7f.",
    )
    check(
        "model_ready_panel_rows",
        int(len(model_panel)),
        expected["model_rows"],
        "The scan must use the Python-NCLOC model-ready run-py-7f rows.",
    )
    scoped = full.merge(
        model_panel[
            [*KEY_COLUMNS, "time_to_event", "treatment_period"]
        ],
        on=KEY_COLUMNS,
        how="inner",
        validate="many_to_one",
    )
    observed_units = int(scoped.drop_duplicates(UNIT_COLUMNS).shape[0])
    check(
        "model_scoped_class_method_body_month_units_present",
        int(observed_units > 0),
        1,
        "At least one AGC-like method body-month must occur in the model scope.",
    )

    manifest_keep = MANIFEST_REQUIRED_COLUMNS + [
        column
        for column in ["change_type", "content_sha256", "source_bytes"]
        if column in manifest.columns
    ]
    manifest_view = manifest[manifest_keep].copy()
    rename = {
        column: f"manifest_{column}"
        for column in manifest_view.columns
        if column != "function_event_id"
    }
    manifest_view = manifest_view.rename(columns=rename)
    scoped = scoped.merge(
        manifest_view,
        on="function_event_id",
        how="left",
        validate="one_to_one",
        indicator="manifest_merge_status",
    )
    unresolved = int(scoped["manifest_merge_status"].ne("both").sum())
    check(
        "all_scoped_events_map_to_manifest",
        unresolved,
        0,
        "Every model-scoped event must map to one extraction manifest row.",
    )
    if unresolved:
        raise ValidationError(
            f"Model-scoped events missing from manifest: {unresolved}"
        )
    scoped = scoped.drop(columns=["manifest_merge_status"])

    mismatch_total = 0
    for column in [*KEY_COLUMNS, "function_kind"]:
        left = scoped[column].astype("string").str.strip()
        right = scoped[f"manifest_{column}"].astype("string").str.strip()
        mismatch_total += int(left.ne(right).sum())
    check(
        "event_manifest_identity_fields_match",
        mismatch_total,
        0,
        "Event and manifest identity metadata must agree exactly.",
    )
    if mismatch_total:
        raise ValidationError(
            f"Event and manifest identity mismatches: {mismatch_total}"
        )

    occurrence = pd.to_numeric(
        scoped["manifest_occurrence_index"], errors="coerce"
    )
    invalid_occurrence = int(occurrence.isna().sum() + occurrence.lt(1).sum())
    check(
        "manifest_occurrence_indexes_positive",
        invalid_occurrence,
        0,
        "Every selected method must have a positive run-py-5a occurrence index.",
    )
    if invalid_occurrence:
        raise ValidationError(
            f"Invalid method occurrence indexes: {invalid_occurrence}"
        )
    scoped["manifest_occurrence_index"] = occurrence.astype("int64")

    feature_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    blob_columns = [
        "dataset_source",
        "repo_name",
        "manifest_commit",
        "manifest_relative_path",
    ]
    blob_rows = scoped[blob_columns].drop_duplicates().sort_values(
        blob_columns, kind="mergesort"
    )
    blob_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    total_blobs = len(blob_rows)
    for blob_number, blob in enumerate(blob_rows.itertuples(index=False), start=1):
        dataset_source = str(blob.dataset_source)
        repo_name = str(blob.repo_name)
        commit = str(blob.manifest_commit).strip()
        relative_path = str(blob.manifest_relative_path)
        clone_root = (
            treatment_clone_dir
            if dataset_source == "treatment"
            else control_clone_dir
        )
        repo_dir = clone_root / repo_slug(repo_name)
        cache_key = (dataset_source, repo_name, commit, relative_path)
        try:
            if not (repo_dir / ".git").is_dir():
                raise FileNotFoundError(f"Missing Git clone: {repo_dir}")
            payload = read_git_blob(repo_dir, commit, relative_path)
            source = decode_python_source(payload)
            methods = extract_synchronous_class_methods(
                source,
                f"{repo_name}:{commit}:{relative_path}",
            )
            blob_cache[cache_key] = {
                "repo_dir": str(repo_dir),
                "git_blob_sha256": hashlib.sha256(payload).hexdigest(),
                "methods": methods,
            }
        except Exception as exc:
            parse_errors.append(
                {
                    "function_event_id": "",
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "commit": commit,
                    "relative_path": relative_path,
                    "qualified_function_name": "",
                    "occurrence_index": "",
                    "stage": "git_blob_read_or_parse",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        if progress_every > 0 and (
            blob_number % progress_every == 0 or blob_number == total_blobs
        ):
            print(
                f"Git blob scan: {blob_number}/{total_blobs}; "
                f"failures={len(parse_errors)}",
                flush=True,
            )

    rendered_hash_mismatches = 0
    for row in scoped.itertuples(index=False):
        cache_key = (
            str(row.dataset_source),
            str(row.repo_name),
            str(row.manifest_commit).strip(),
            str(row.manifest_relative_path),
        )
        cached = blob_cache.get(cache_key)
        if cached is None:
            continue
        identity = (
            str(row.manifest_qualified_function_name),
            int(row.manifest_occurrence_index),
        )
        method = cached["methods"].get(identity)
        if method is None:
            parse_errors.append(
                {
                    "function_event_id": row.function_event_id,
                    "dataset_source": row.dataset_source,
                    "repo_name": row.repo_name,
                    "commit": row.manifest_commit,
                    "relative_path": row.manifest_relative_path,
                    "qualified_function_name": identity[0],
                    "occurrence_index": identity[1],
                    "stage": "method_identity_lookup",
                    "error_type": "LookupError",
                    "error": "Method identity was not found in the exact Git blob",
                }
            )
            continue
        source_text = str(method["source_text"])
        try:
            features = source_features(
                source_text,
                (
                    f"{row.repo_name}:{row.manifest_commit}:"
                    f"{row.manifest_relative_path}:{identity[0]}"
                ),
            )
        except Exception as exc:
            parse_errors.append(
                {
                    "function_event_id": row.function_event_id,
                    "dataset_source": row.dataset_source,
                    "repo_name": row.repo_name,
                    "commit": row.manifest_commit,
                    "relative_path": row.manifest_relative_path,
                    "qualified_function_name": identity[0],
                    "occurrence_index": identity[1],
                    "stage": "method_feature_parse",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            continue
        manifest_hash = str(
            getattr(row, "manifest_content_sha256", "")
        ).strip().lower()
        rendered_hash = str(method["rendered_source_sha256"])
        hash_matches = int(not manifest_hash or manifest_hash == rendered_hash)
        rendered_hash_mismatches += int(hash_matches == 0)
        feature_rows.append(
            {
                "function_event_id": row.function_event_id,
                "relative_path_tokens": path_tokens(row.manifest_relative_path),
                "class_base_tokens": ordered_unique(
                    token
                    for base in method["class_base_names"]
                    for token in lexical_tokens(base)
                ),
                "git_repo_dir": cached["repo_dir"],
                "git_source_label": (
                    f"{row.manifest_commit}:{row.manifest_relative_path}"
                ),
                "git_blob_sha256": cached["git_blob_sha256"],
                "manifest_rendered_source_sha256": manifest_hash,
                "rendered_source_hash_matches_manifest": hash_matches,
                "source_text": source_text,
                **method,
                **features,
            }
        )

    check(
        "direct_clone_scan_errors",
        len(parse_errors),
        0,
        "Every selected event must resolve in its exact cloned-repository Git blob.",
    )
    check(
        "rendered_method_hash_mismatches",
        rendered_hash_mismatches,
        0,
        "Directly rendered methods must reproduce run-py-5a source artifacts.",
    )
    if parse_errors:
        return scoped, pd.DataFrame(parse_errors, columns=SCAN_ERROR_COLUMNS), checks

    features = pd.DataFrame(feature_rows)
    scoped = scoped.merge(
        features,
        on="function_event_id",
        how="left",
        validate="one_to_one",
    )
    missing_feature_rows = int(scoped["source_text"].isna().sum())
    check(
        "all_scoped_events_have_direct_clone_features",
        missing_feature_rows,
        0,
        "Every selected event must have one feature row from the clone scan.",
    )
    return scoped, pd.DataFrame(parse_errors, columns=SCAN_ERROR_COLUMNS), checks


def add_serialized_list_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in [
        "function_name_tokens",
        "class_name_tokens",
        "relative_path_tokens",
        "class_base_tokens",
        "method_decorator_callables",
        "method_decorator_terminals",
        "class_decorator_callables",
        "class_base_names",
        "docstring_terms",
        "call_names",
        "call_terminals",
        "ast_node_types",
    ]:
        if column in result.columns:
            result[column] = result[column].map(
                lambda values: "|".join(str(value) for value in values)
            )
    return result


def distribution(
    contexts: pd.DataFrame,
    value_column: str,
    output_label: str,
) -> pd.DataFrame:
    values = contexts.loc[
        contexts[value_column].notna()
        & contexts[value_column].astype("string").str.strip().ne("")
    ].copy()
    if values.empty:
        return pd.DataFrame(
            columns=[
                output_label,
                "event_contexts",
                "body_month_occurrences",
                "unique_bodies",
                "repositories",
                "treatment_event_contexts",
                "control_event_contexts",
                "share_of_event_contexts",
                "share_of_body_month_occurrences",
            ]
        )
    grouped = (
        values.groupby(value_column, dropna=False)
        .agg(
            event_contexts=("function_event_id", "size"),
            unique_bodies=("function_body_sha256", "nunique"),
            repositories=("repo_name", "nunique"),
            treatment_event_contexts=(
                "dataset_source",
                lambda series: int(series.astype("string").eq("treatment").sum()),
            ),
            control_event_contexts=(
                "dataset_source",
                lambda series: int(series.astype("string").eq("control").sum()),
            ),
        )
        .reset_index()
        .rename(columns={value_column: output_label})
    )
    body_month = (
        values.drop_duplicates([*UNIT_COLUMNS, value_column])
        .groupby(value_column, dropna=False)
        .size()
        .rename("body_month_occurrences")
        .reset_index()
        .rename(columns={value_column: output_label})
    )
    grouped = grouped.merge(
        body_month,
        on=output_label,
        how="left",
        validate="one_to_one",
    )
    grouped["share_of_event_contexts"] = (
        grouped["event_contexts"] / len(contexts)
    )
    denominator = contexts.drop_duplicates(UNIT_COLUMNS).shape[0]
    grouped["share_of_body_month_occurrences"] = (
        grouped["body_month_occurrences"] / denominator
    )
    return grouped.sort_values(
        ["body_month_occurrences", "event_contexts", output_label],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def exploded_distribution(
    contexts: pd.DataFrame,
    list_column: str,
    output_label: str,
) -> pd.DataFrame:
    expanded = contexts.copy()
    expanded[list_column] = expanded[list_column].map(ordered_unique)
    expanded = expanded.explode(list_column).rename(
        columns={list_column: output_label}
    )
    return distribution(expanded, output_label, output_label)


def build_body_month_units(contexts: pd.DataFrame) -> pd.DataFrame:
    sorted_contexts = contexts.sort_values(
        [*UNIT_COLUMNS, "function_event_id"], kind="mergesort"
    )
    rows: list[dict[str, Any]] = []
    for unit_key, group in sorted_contexts.groupby(
        UNIT_COLUMNS, sort=False, dropna=False
    ):
        representative = group.iloc[0]
        relative_time = representative["time_to_event"]
        function_names = sorted(
            set(group["manifest_function_name"].astype(str))
        )
        qualified_names = sorted(
            set(group["manifest_qualified_function_name"].astype(str))
        )
        relative_paths = sorted(
            set(group["manifest_relative_path"].astype(str))
        )
        rows.append(
            {
                **dict(zip(UNIT_COLUMNS, unit_key)),
                "time_to_event": (
                    None if pd.isna(relative_time) else int(relative_time)
                ),
                "treatment_period": representative["treatment_period"],
                "event_context_count": int(len(group)),
                "distinct_function_names": len(function_names),
                "distinct_qualified_names": len(qualified_names),
                "distinct_relative_paths": len(relative_paths),
                "has_multiple_function_names": int(len(function_names) > 1),
                "has_multiple_relative_paths": int(len(relative_paths) > 1),
                "function_names": "|".join(function_names),
                "qualified_function_names": "|".join(qualified_names),
                "relative_paths": "|".join(relative_paths),
                "representative_function_event_id": representative[
                    "function_event_id"
                ],
                "representative_function_name": representative[
                    "manifest_function_name"
                ],
                "representative_relative_path": representative[
                    "manifest_relative_path"
                ],
                "representative_git_source": representative["git_source_label"],
                "representative_containing_class": representative[
                    "containing_class_name"
                ],
            }
        )
    units = pd.DataFrame(rows)
    if not units.empty:
        units["time_to_event"] = units["time_to_event"].astype("Int64")
    return units


def feature_summary(contexts: pd.DataFrame) -> pd.DataFrame:
    numeric_features = [
        "source_line_count",
        "source_character_count",
        "body_top_level_statement_count",
        "positional_argument_count",
        "keyword_only_argument_count",
        "has_vararg",
        "has_kwarg",
        "has_docstring",
        "decorator_count",
        "has_classmethod_decorator",
        "has_staticmethod_decorator",
        "has_property_decorator",
        "has_setter_decorator",
        "has_deleter_decorator",
        "is_dunder_name",
        "class_depth",
        "called_function_count",
        "return_count",
        "raise_count",
        "yield_count",
        "assert_count",
        "branch_count",
        "loop_count",
        "with_count",
        "try_count",
        "await_count",
        "nested_definition_count",
        "ast_node_count",
    ]
    rows: list[dict[str, Any]] = []
    for feature in numeric_features:
        values = pd.to_numeric(contexts[feature], errors="raise")
        rows.append(
            {
                "feature": feature,
                "event_contexts": int(len(values)),
                "sum": float(values.sum()),
                "mean": float(values.mean()),
                "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                "minimum": float(values.min()),
                "p25": float(values.quantile(0.25)),
                "median": float(values.median()),
                "p75": float(values.quantile(0.75)),
                "p90": float(values.quantile(0.90)),
                "maximum": float(values.max()),
                "positive_event_contexts": int(values.gt(0).sum()),
                "positive_share": float(values.gt(0).mean()),
            }
        )
    return pd.DataFrame(rows)


def deterministic_audit_sample(
    contexts: pd.DataFrame,
    body_month_units: pd.DataFrame,
    sample_size: int,
) -> pd.DataFrame:
    if sample_size < 1:
        raise ValueError("--audit-sample-size must be positive")
    units = body_month_units.copy()
    units["sample_hash"] = [
        stable_hash(*values)
        for values in units[UNIT_COLUMNS].itertuples(index=False, name=None)
    ]
    strata = ["dataset_source", "treatment_period"]
    stratum_count = max(1, units.groupby(strata).ngroups)
    per_stratum = max(1, math.ceil(sample_size / stratum_count))
    selected = (
        units.sort_values([*strata, "sample_hash"], kind="mergesort")
        .groupby(strata, group_keys=False)
        .head(per_stratum)
    )
    if len(selected) < sample_size:
        remaining = units.loc[~units.index.isin(selected.index)].sort_values(
            "sample_hash", kind="mergesort"
        )
        selected = pd.concat(
            [selected, remaining.head(sample_size - len(selected))],
            ignore_index=False,
        )
    selected = selected.sort_values("sample_hash", kind="mergesort").head(
        min(sample_size, len(units))
    )
    representative = contexts[
        [
            "function_event_id",
            "manifest_function_name",
            "manifest_qualified_function_name",
            "manifest_relative_path",
            "containing_class_name",
            "qualified_class_name",
            "first_parameter_name",
            "method_decorator_callables",
            "class_base_names",
            "docstring_preview",
            "source_text",
        ]
    ].rename(
        columns={
            "function_event_id": "representative_function_event_id",
            "manifest_function_name": "function_name",
            "manifest_qualified_function_name": "qualified_function_name",
            "manifest_relative_path": "relative_path",
        }
    )
    representative = add_serialized_list_columns(representative)
    return selected.merge(
        representative,
        on="representative_function_event_id",
        how="left",
        validate="one_to_one",
    ).sort_values(
        ["dataset_source", "treatment_period", "sample_hash"],
        kind="mergesort",
    ).reset_index(drop=True)


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    event_path = require_file(
        args.event_classifications, "Event classifications"
    )
    manifest_path = require_file(args.function_manifest, "Function manifest")
    panel_path = require_file(args.analysis_panel, "Analysis panel")
    treatment_clone_dir = require_directory(
        args.treatment_clone_dir, "Treatment clone directory"
    )
    control_clone_dir = require_directory(
        args.control_clone_dir, "Control clone directory"
    )
    prepare_output_directory(args.output_dir, args.overwrite_output)

    events = pd.read_csv(event_path, low_memory=False)
    manifest = pd.read_csv(manifest_path, low_memory=False)
    panel = pd.read_csv(panel_path, low_memory=False)
    expected = {
        "panel_rows": args.expected_panel_rows,
        "model_rows": args.expected_model_rows,
    }
    contexts, parse_errors, checks = join_model_scope(
        events,
        manifest,
        panel,
        treatment_clone_dir,
        control_clone_dir,
        expected,
        args.progress_every,
    )

    output_dir = args.output_dir
    qc_dir = output_dir / "qc"
    parse_error_path = qc_dir / "run-py-7f12-direct-clone-scan-errors.csv"
    checks_path = qc_dir / "run-py-7f12-role-inventory-checks.csv"
    summary_path = qc_dir / "run-py-7f12-role-inventory-summary.json"
    metadata_path = qc_dir / "run-py-7f12-role-inventory-metadata.json"

    if not parse_errors.empty:
        atomic_write_csv(parse_errors, parse_error_path)
        atomic_write_csv(pd.DataFrame(checks), checks_path)
        raise ValidationError(
            "Source parsing failed; inspect "
            f"{parse_error_path} before interpreting distributions."
        )

    body_month_units = build_body_month_units(contexts)
    checks_frame = pd.DataFrame(checks)
    failed_checks = int((~checks_frame["passed"].astype(bool)).sum())

    context_output = add_serialized_list_columns(
        contexts.drop(columns=["source_text"])
    )
    name_distribution = distribution(
        contexts,
        "manifest_function_name",
        "function_name",
    )
    name_token_distribution = exploded_distribution(
        contexts,
        "function_name_tokens",
        "name_token",
    )
    class_distribution = distribution(
        contexts,
        "containing_class_name",
        "class_name",
    )
    class_token_distribution = exploded_distribution(
        contexts,
        "class_name_tokens",
        "class_name_token",
    )
    path_token_distribution = exploded_distribution(
        contexts,
        "relative_path_tokens",
        "path_token",
    )
    method_decorator_distribution = exploded_distribution(
        contexts,
        "method_decorator_callables",
        "method_decorator",
    )
    class_decorator_distribution = exploded_distribution(
        contexts,
        "class_decorator_callables",
        "class_decorator",
    )
    class_base_distribution = exploded_distribution(
        contexts,
        "class_base_names",
        "class_base",
    )
    class_base_token_distribution = exploded_distribution(
        contexts,
        "class_base_tokens",
        "class_base_token",
    )
    first_parameter_distribution = distribution(
        contexts,
        "first_parameter_name",
        "first_parameter_name",
    )
    call_distribution = exploded_distribution(
        contexts,
        "call_terminals",
        "call_name",
    )
    docstring_distribution = exploded_distribution(
        contexts,
        "docstring_terms",
        "docstring_term",
    )
    ast_distribution = exploded_distribution(
        contexts,
        "ast_node_types",
        "ast_node_type",
    )
    numeric_summary = feature_summary(contexts)
    audit_samples = deterministic_audit_sample(
        contexts,
        body_month_units,
        args.audit_sample_size,
    )

    outputs = {
        "event_context_inventory": (
            output_dir / "run-py-7f12-class-method-event-context-inventory.csv"
        ),
        "body_month_units": (
            output_dir / "run-py-7f12-class-method-body-month-unit-inventory.csv"
        ),
        "function_name_distribution": (
            output_dir / "run-py-7f12-method-name-distribution.csv"
        ),
        "name_token_distribution": (
            output_dir / "run-py-7f12-method-name-token-distribution.csv"
        ),
        "class_name_distribution": (
            output_dir / "run-py-7f12-class-name-distribution.csv"
        ),
        "class_name_token_distribution": (
            output_dir / "run-py-7f12-class-name-token-distribution.csv"
        ),
        "path_token_distribution": (
            output_dir / "run-py-7f12-path-token-distribution.csv"
        ),
        "method_decorator_distribution": (
            output_dir / "run-py-7f12-method-decorator-distribution.csv"
        ),
        "class_decorator_distribution": (
            output_dir / "run-py-7f12-class-decorator-distribution.csv"
        ),
        "class_base_distribution": (
            output_dir / "run-py-7f12-class-base-distribution.csv"
        ),
        "class_base_token_distribution": (
            output_dir / "run-py-7f12-class-base-token-distribution.csv"
        ),
        "first_parameter_distribution": (
            output_dir / "run-py-7f12-first-parameter-distribution.csv"
        ),
        "call_name_distribution": (
            output_dir / "run-py-7f12-call-name-distribution.csv"
        ),
        "docstring_term_distribution": (
            output_dir / "run-py-7f12-docstring-term-distribution.csv"
        ),
        "ast_node_distribution": (
            output_dir / "run-py-7f12-ast-node-distribution.csv"
        ),
        "numeric_feature_summary": (
            output_dir / "run-py-7f12-numeric-feature-summary.csv"
        ),
        "audit_samples": (
            output_dir / "run-py-7f12-deterministic-source-audit-samples.csv"
        ),
        "checks": checks_path,
        "summary": summary_path,
        "metadata": metadata_path,
        "parse_errors": parse_error_path,
    }

    for frame, path in [
        (context_output, outputs["event_context_inventory"]),
        (body_month_units, outputs["body_month_units"]),
        (name_distribution, outputs["function_name_distribution"]),
        (name_token_distribution, outputs["name_token_distribution"]),
        (class_distribution, outputs["class_name_distribution"]),
        (class_token_distribution, outputs["class_name_token_distribution"]),
        (path_token_distribution, outputs["path_token_distribution"]),
        (method_decorator_distribution, outputs["method_decorator_distribution"]),
        (class_decorator_distribution, outputs["class_decorator_distribution"]),
        (class_base_distribution, outputs["class_base_distribution"]),
        (class_base_token_distribution, outputs["class_base_token_distribution"]),
        (first_parameter_distribution, outputs["first_parameter_distribution"]),
        (call_distribution, outputs["call_name_distribution"]),
        (docstring_distribution, outputs["docstring_term_distribution"]),
        (ast_distribution, outputs["ast_node_distribution"]),
        (numeric_summary, outputs["numeric_feature_summary"]),
        (audit_samples, outputs["audit_samples"]),
        (checks_frame, checks_path),
        (parse_errors, parse_error_path),
    ]:
        atomic_write_csv(frame, path)

    summary = {
        "status": "PASS" if failed_checks == 0 else "FAIL",
        "script_version": SCRIPT_VERSION,
        "taxonomy_applied": False,
        "decorator_features_included": True,
        "function_scope": "AGC-like synchronous direct class-scope methods",
        "analysis_scope": (
            "Python-NCLOC model-ready repository-months used by run-py-7f"
        ),
        "parse_clean_panel_rows": int(len(panel)),
        "model_ready_panel_rows": int(
            normalize_binary(panel[READY_COLUMN], READY_COLUMN).eq(1).sum()
        ),
        "model_scoped_event_contexts": int(len(contexts)),
        "model_scoped_body_month_outcome_units": int(len(body_month_units)),
        "model_scoped_unique_bodies": int(
            contexts["function_body_sha256"].nunique()
        ),
        "model_scoped_repositories": int(contexts["repo_name"].nunique()),
        "direct_git_blobs_scanned": int(
            contexts[
                [
                    "dataset_source",
                    "repo_name",
                    "manifest_commit",
                    "manifest_relative_path",
                ]
            ].drop_duplicates().shape[0]
        ),
        "decorated_event_contexts": int(contexts["decorator_count"].gt(0).sum()),
        "dunder_event_contexts": int(contexts["is_dunder_name"].eq(1).sum()),
        "body_month_units_with_multiple_function_names": int(
            body_month_units["has_multiple_function_names"].sum()
        ),
        "body_month_units_with_multiple_relative_paths": int(
            body_month_units["has_multiple_relative_paths"].sum()
        ),
        "audit_sample_rows": int(len(audit_samples)),
        "direct_clone_scan_errors": int(len(parse_errors)),
        "checks_total": int(len(checks_frame)),
        "failed_checks": failed_checks,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    metadata = {
        "status": summary["status"],
        "script_version": SCRIPT_VERSION,
        "python_version": sys.version,
        "inputs": {
            "event_classifications": {
                "path": str(event_path),
                "sha256": sha256_file(event_path),
            },
            "function_manifest": {
                "path": str(manifest_path),
                "sha256": sha256_file(manifest_path),
            },
            "analysis_panel": {
                "path": str(panel_path),
                "sha256": sha256_file(panel_path),
            },
            "treatment_clone_dir": str(treatment_clone_dir),
            "control_clone_dir": str(control_clone_dir),
        },
        "expected_invariants": expected,
        "sampling": {
            "method": "deterministic SHA-256 ordering stratified by dataset source and treatment period",
            "requested_rows": args.audit_sample_size,
            "observed_rows": int(len(audit_samples)),
        },
        "feature_policy": {
            "semantic_role_taxonomy": "none",
            "decorator_features": "raw observable syntax included",
            "source_access": "exact Git blob read from local clone",
            "observed_features": [
                "exact method names",
                "method-name tokens",
                "containing class names and bases",
                "relative-path tokens",
                "method and class decorators",
                "first parameter names",
                "docstring terms",
                "called function terminal names",
                "AST node types",
                "numeric AST and signature features",
            ],
        },
    }
    atomic_write_json(summary, summary_path)
    atomic_write_json(metadata, metadata_path)

    if failed_checks:
        failed = checks_frame.loc[~checks_frame["passed"].astype(bool)]
        raise ValidationError(
            "run-py-7f12 QC failed:\n" + failed.to_string(index=False)
        )
    return summary


def self_test() -> None:
    sample = (
        "def parse_record(value, *, strict=False):\n"
        "    \"\"\"Parse one input record.\"\"\"\n"
        "    if strict:\n"
        "        validate(value)\n"
        "    return json.loads(value)\n"
    )
    features = source_features(sample, "<self-test>")
    if features["has_docstring"] != 1:
        raise AssertionError("Docstring detection failed")
    if features["branch_count"] != 1:
        raise AssertionError("Branch count failed")
    if features["return_count"] != 1:
        raise AssertionError("Return count failed")
    if features["call_terminals"] != ["validate", "loads"]:
        raise AssertionError(
            f"Call extraction failed: {features['call_terminals']}"
        )
    if lexical_tokens("parseHTTPResponse_v2") != [
        "parse",
        "http",
        "response",
        "v2",
    ]:
        raise AssertionError("Lexical tokenization failed")
    if "test" not in path_tokens("tests/unit/test_parser.py"):
        raise AssertionError("Path tokenization failed")
    decorated = (
        "@framework.command()\n"
        "def execute():\n"
        "    return run()\n"
    )
    decorated_features = source_features(decorated, "<decorated-self-test>")
    if "command" in decorated_features["call_terminals"]:
        raise AssertionError("Decorator calls must be excluded from features")
    if decorated_features["call_terminals"] != ["run"]:
        raise AssertionError("Function-body calls were not preserved")
    class_source = (
        "@dataclass\n"
        "class Parser(BaseParser):\n"
        "    @classmethod\n"
        "    def from_text(cls, value):\n"
        "        return cls(value)\n"
        "\n"
        "    @property\n"
        "    def size(self):\n"
        "        return 1\n"
        "\n"
        "    async def skipped(self):\n"
        "        return 0\n"
    )
    methods = extract_synchronous_class_methods(class_source, "<class-self-test>")
    if sorted(methods) != [("Parser.from_text", 1), ("Parser.size", 1)]:
        raise AssertionError(f"Class-method extraction mismatch: {sorted(methods)}")
    from_text = methods[("Parser.from_text", 1)]
    if from_text["has_classmethod_decorator"] != 1:
        raise AssertionError("classmethod decorator detection failed")
    if from_text["first_parameter_name"] != "cls":
        raise AssertionError("First-parameter extraction failed")
    if from_text["class_base_names"] != ["BaseParser"]:
        raise AssertionError("Class-base extraction failed")
    size = methods[("Parser.size", 1)]
    if size["has_property_decorator"] != 1:
        raise AssertionError("property decorator detection failed")

    relative_time = to_nullable_integer(
        pd.Series(["-1", "", None, "2.0"]), "time_to_event"
    )
    if str(relative_time.dtype) != "Int64":
        raise AssertionError("Nullable relative-time dtype was not preserved")
    if relative_time.tolist() != [-1, pd.NA, pd.NA, 2]:
        raise AssertionError(
            f"Nullable relative-time conversion failed: {relative_time.tolist()}"
        )
    if treatment_period("control", pd.NA) != "control":
        raise AssertionError("Control relative-time handling failed")
    try:
        treatment_period("treatment", pd.NA)
    except ValidationError:
        pass
    else:
        raise AssertionError("Missing treatment relative time was not rejected")

    body_month_context = pd.DataFrame(
        [
            {
                "dataset_source": "control",
                "repo_name": "example/control",
                "time": "2026-01",
                "function_body_sha256": "a" * 64,
                "function_event_id": "event-control-1",
                "time_to_event": pd.NA,
                "treatment_period": "control",
                "manifest_function_name": "size",
                "manifest_qualified_function_name": "Parser.size",
                "manifest_relative_path": "parser.py",
                "git_source_label": "example/control:abc:parser.py",
                "containing_class_name": "Parser",
            }
        ]
    )
    body_month_units = build_body_month_units(body_month_context)
    if str(body_month_units["time_to_event"].dtype) != "Int64":
        raise AssertionError("Body-month relative-time dtype is not Int64")
    if not pd.isna(body_month_units.loc[0, "time_to_event"]):
        raise AssertionError("Control body-month relative time was not preserved")
    print("run-py-7f12 self-test PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if sys.version_info < (3, 12):
        raise RuntimeError(
            "run-py-7f12 requires Python 3.12+ to reproduce the py312 "
            "run-py-5a AST identities and rendered source hashes."
        )
    summary = run_analysis(args)
    print("=" * 80)
    print("run-py-7f12: empirical class-method role inventory")
    print(f"Status:                              {summary['status']}")
    print(
        "Model-scoped event contexts:         "
        f"{summary['model_scoped_event_contexts']}"
    )
    print(
        "Body-month outcome units:            "
        f"{summary['model_scoped_body_month_outcome_units']}"
    )
    print(
        "Model-scoped unique bodies:          "
        f"{summary['model_scoped_unique_bodies']}"
    )
    print(
        "Multiple-name body-month units:      "
        f"{summary['body_month_units_with_multiple_function_names']}"
    )
    print(
        "Deterministic source audit samples:  "
        f"{summary['audit_sample_rows']}"
    )
    print("Semantic role taxonomy applied:      NO")
    print("Decorator features included:         YES (raw syntax only)")
    print(f"Output directory:                    {args.output_dir}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
