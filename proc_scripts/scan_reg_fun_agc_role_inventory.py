#!/usr/bin/env python3
"""Build an outcome-aligned empirical inventory for run-py-7f functions.

This diagnostic does not assign semantic roles. It scans the exact AGC-like
regular module-function events that contribute to the model-ready run-py-7f
panel and reports observed names, name tokens, path tokens, docstring terms,
call names, AST features, and deterministic source samples.

Decorator syntax is intentionally excluded from feature extraction. The
function source artifact may retain decorator lines, but decorators are not
used to define a category or feature in this stage.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd


SCRIPT_VERSION = "run-py-7f01-v1"
KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
UNIT_COLUMNS = [*KEY_COLUMNS, "function_body_sha256"]
READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_"
    "python_snapshot_ncloc"
)
OUTCOME_COLUMN = "npr_agc_regular_module_function_unique_bodies"
FUNCTION_KIND = "module_function"

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
    "relative_path",
    "qualified_function_name",
    "function_name",
    "function_kind",
    "function_source_relative_path",
]

PANEL_REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "time_to_event",
    READY_COLUMN,
    OUTCOME_COLUMN,
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
            "Scan the exact run-py-7f AGC-like regular module functions and "
            "produce outcome-blind empirical distributions before role design."
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
        "--function-source-root",
        type=Path,
        default=Path(
            "repo_python/run-py-5a-py312/strict/commit_function_sources"
        ),
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
            "repo_python/run-py-7f01/strict/specifications/range100_200/"
            "python_snapshot_ncloc/calendar_month/parse_clean"
        ),
    )
    parser.add_argument("--audit-sample-size", type=int, default=240)
    parser.add_argument("--expected-full-event-rows", type=int, default=2994)
    parser.add_argument("--expected-full-unique-bodies", type=int, default=2463)
    parser.add_argument("--expected-panel-rows", type=int, default=1536)
    parser.add_argument("--expected-model-rows", type=int, default=1521)
    parser.add_argument(
        "--expected-model-body-month-occurrences",
        type=int,
        default=2249,
    )
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
    source_root: Path,
    expected: dict[str, int],
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
    panel[OUTCOME_COLUMN] = pd.to_numeric(
        panel[OUTCOME_COLUMN], errors="raise"
    ).astype("int64")
    # panel["time_to_event"] = pd.to_numeric(
    #     panel["time_to_event"], errors="raise"
    # ).astype("int64")
    model_panel = panel.loc[panel[READY_COLUMN].eq(1)].copy()
    model_panel["treatment_period"] = [
        treatment_period(source, relative_time)
        for source, relative_time in zip(
            model_panel["dataset_source"],
            model_panel["time_to_event"],
        )
    ]

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

    check(
        "full_agc_regular_event_rows",
        int(len(full)),
        expected["full_event_rows"],
        "The upstream run-py-7e scope must be reproduced before model filtering.",
    )
    check(
        "full_agc_regular_unique_bodies",
        int(full["function_body_sha256"].nunique()),
        expected["full_unique_bodies"],
        "The upstream run-py-7e distinct-body universe must be reproduced.",
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
    check(
        "panel_outcome_occurrences",
        int(model_panel[OUTCOME_COLUMN].sum()),
        expected["model_body_month_occurrences"],
        "The model-ready panel must reproduce the run-py-7f outcome total.",
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
        "event_derived_body_month_occurrences",
        observed_units,
        expected["model_body_month_occurrences"],
        "Distinct event-derived body-month units must equal the panel outcome sum.",
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

    feature_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for row in scoped.itertuples(index=False):
        relative_source = str(row.manifest_function_source_relative_path)
        source_path = source_root / relative_source
        try:
            source_text = source_path.read_text(encoding="utf-8")
            features = source_features(source_text, str(source_path))
        except Exception as exc:
            parse_errors.append(
                {
                    "function_event_id": row.function_event_id,
                    "source_path": str(source_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            continue
        feature_rows.append(
            {
                "function_event_id": row.function_event_id,
                "function_name_tokens": ordered_unique(
                    lexical_tokens(row.manifest_function_name)
                ),
                "relative_path_tokens": path_tokens(row.manifest_relative_path),
                "source_path": str(source_path),
                "source_text": source_text,
                **features,
            }
        )

    check(
        "source_artifact_parse_errors",
        len(parse_errors),
        0,
        "Every selected source artifact was previously rendered and must parse.",
    )
    if parse_errors:
        return scoped, pd.DataFrame(parse_errors), checks

    features = pd.DataFrame(feature_rows)
    scoped = scoped.merge(
        features,
        on="function_event_id",
        how="left",
        validate="one_to_one",
    )
    return scoped, pd.DataFrame(parse_errors), checks


def add_serialized_list_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in [
        "function_name_tokens",
        "relative_path_tokens",
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
                "time_to_event": int(representative["time_to_event"]),
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
                "representative_source_path": representative["source_path"],
            }
        )
    return pd.DataFrame(rows)


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
    source_root = require_directory(
        args.function_source_root, "Function source root"
    )
    prepare_output_directory(args.output_dir, args.overwrite_output)

    events = pd.read_csv(event_path, low_memory=False)
    manifest = pd.read_csv(manifest_path, low_memory=False)
    panel = pd.read_csv(panel_path, low_memory=False)
    expected = {
        "full_event_rows": args.expected_full_event_rows,
        "full_unique_bodies": args.expected_full_unique_bodies,
        "panel_rows": args.expected_panel_rows,
        "model_rows": args.expected_model_rows,
        "model_body_month_occurrences": (
            args.expected_model_body_month_occurrences
        ),
    }
    contexts, parse_errors, checks = join_model_scope(
        events,
        manifest,
        panel,
        source_root,
        expected,
    )

    output_dir = args.output_dir
    qc_dir = output_dir / "qc"
    parse_error_path = qc_dir / "run-py-7f01-source-parse-errors.csv"
    checks_path = qc_dir / "run-py-7f01-role-inventory-checks.csv"
    summary_path = qc_dir / "run-py-7f01-role-inventory-summary.json"
    metadata_path = qc_dir / "run-py-7f01-role-inventory-metadata.json"

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
    path_token_distribution = exploded_distribution(
        contexts,
        "relative_path_tokens",
        "path_token",
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
            output_dir / "run-py-7f01-function-event-context-inventory.csv"
        ),
        "body_month_units": (
            output_dir / "run-py-7f01-body-month-outcome-unit-inventory.csv"
        ),
        "function_name_distribution": (
            output_dir / "run-py-7f01-function-name-distribution.csv"
        ),
        "name_token_distribution": (
            output_dir / "run-py-7f01-function-name-token-distribution.csv"
        ),
        "path_token_distribution": (
            output_dir / "run-py-7f01-path-token-distribution.csv"
        ),
        "call_name_distribution": (
            output_dir / "run-py-7f01-call-name-distribution.csv"
        ),
        "docstring_term_distribution": (
            output_dir / "run-py-7f01-docstring-term-distribution.csv"
        ),
        "ast_node_distribution": (
            output_dir / "run-py-7f01-ast-node-distribution.csv"
        ),
        "numeric_feature_summary": (
            output_dir / "run-py-7f01-numeric-feature-summary.csv"
        ),
        "audit_samples": (
            output_dir / "run-py-7f01-deterministic-source-audit-samples.csv"
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
        (path_token_distribution, outputs["path_token_distribution"]),
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
        "decorator_features_included": False,
        "function_scope": "AGC-like synchronous module functions",
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
        "body_month_units_with_multiple_function_names": int(
            body_month_units["has_multiple_function_names"].sum()
        ),
        "body_month_units_with_multiple_relative_paths": int(
            body_month_units["has_multiple_relative_paths"].sum()
        ),
        "audit_sample_rows": int(len(audit_samples)),
        "source_parse_errors": int(len(parse_errors)),
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
            "function_source_root": str(source_root),
        },
        "expected_invariants": expected,
        "sampling": {
            "method": "deterministic SHA-256 ordering stratified by dataset source and treatment period",
            "requested_rows": args.audit_sample_size,
            "observed_rows": int(len(audit_samples)),
        },
        "feature_policy": {
            "semantic_role_taxonomy": "none",
            "decorator_features": "excluded",
            "observed_features": [
                "exact function names",
                "function-name tokens",
                "relative-path tokens",
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
            "run-py-7f01 QC failed:\n" + failed.to_string(index=False)
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
    print("run-py-7f01 self-test PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if sys.version_info < (3, 12):
        raise RuntimeError(
            "run-py-7f01 requires Python 3.12+ to match the py312 source "
            "artifact parser."
        )
    summary = run_analysis(args)
    print("=" * 80)
    print("run-py-7f01: empirical function-role inventory")
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
    print("Decorator features included:         NO")
    print(f"Output directory:                    {args.output_dir}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
