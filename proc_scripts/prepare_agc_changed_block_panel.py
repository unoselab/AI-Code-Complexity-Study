#!/usr/bin/env python3
"""Prepare repository-month AGC outcomes for newly added or modified blocks.

The script compares consecutive monthly Python snapshots at the top-level
function/class block level. It excludes unchanged blocks, including blocks
that only move between files without a structural change. Existing detector
predictions are reused; model inference is not run again.

Primary arithmetic
------------------
changed blocks = changed AGC blocks + changed HWC blocks
AGC changed-block ratio = changed AGC blocks / changed blocks

AGC means AI-likely-generated code. HWC means human-likely-written code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import tokenize
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd


DETECTOR_PROFILE = "codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast"

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

PREDICTION_COLUMNS = [
    "dataset_source",
    "repo_name",
    "commit",
    "relative_path",
    "content_sha256",
    "block_idx",
    "block_kind",
    "block_name",
    "start_line",
    "end_line",
    "pred_label",
    "predicted_agc",
    "human_score",
    "human_decision_score",
    "agc_score",
    "score_mode",
    "model_key",
]

MANIFEST_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit",
    "snapshot_dir",
    "python_file_count",
]

BASE_PANEL_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "latest_commit",
]

CLASSIFICATION_FIELDS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_commit",
    "current_commit",
    "file_status",
    "previous_relative_path",
    "current_relative_path",
    "current_content_sha256",
    "current_block_idx",
    "block_kind",
    "block_name",
    "start_line",
    "end_line",
    "ast_sequence_sha256",
    "code_sha256",
    "change_type",
    "matching_method",
    "previous_block_idx",
    "previous_block_name",
    "previous_start_line",
    "previous_end_line",
    "previous_ast_sequence_sha256",
    "pred_label",
    "code_label",
    "predicted_agc",
    "human_score",
    "human_decision_score",
    "agc_score",
    "score_mode",
    "model_key",
]

FILE_DIFF_FIELDS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_commit",
    "current_commit",
    "raw_status",
    "status_code",
    "previous_relative_path",
    "current_relative_path",
]

METRIC_SPECS = [
    ("changed", "top_level"),
    ("added", "top_level"),
    ("modified", "top_level"),
    ("changed", "function"),
    ("changed", "class"),
]

MISMATCH_FIELDS = [
    "dataset_source",
    "repo_name",
    "month",
    "current_commit",
    "relative_path",
    "block_idx",
    "block_kind",
    "block_name",
    "problems",
]

ERROR_FIELDS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_commit",
    "current_commit",
    "month_gap",
    "comparison_status",
    "stage",
    "error",
]


@dataclass(frozen=True)
class FileChange:
    raw_status: str
    status_code: str
    previous_path: str | None
    current_path: str | None


@dataclass
class PairPlan:
    dataset_source: str
    repo_name: str
    month: str
    previous_month: str | None
    previous_commit: str | None
    current_commit: str
    month_gap: int | None
    comparison_status: str
    repo_dir: Path
    file_changes: list[FileChange]
    git_diff_error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare AGC changed-block repository-month outcomes."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("repo_python/run-py-3a/strict/repo_month_snapshot_manifest.csv"),
    )
    parser.add_argument(
        "--base-panel",
        type=Path,
        default=Path("repo_python/run-py-3b/strict/panel_event_monthly_agc_py.csv"),
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("repo_python/run-py-3a/strict/python_snapshots"),
    )
    parser.add_argument(
        "--detector-root",
        type=Path,
        default=Path(f"../python_snapshots_detect/{DETECTOR_PROFILE}/strict"),
    )
    parser.add_argument("--block-treatment", type=Path, default=None)
    parser.add_argument("--block-control", type=Path, default=None)
    parser.add_argument(
        "--input-check-summary",
        type=Path,
        default=Path(
            "repo_python/tmp/run-py-4a-input-check/strict/"
            "agc_changed_block_input_check_summary.json"
        ),
    )
    parser.add_argument(
        "--tree-sitter-lib",
        type=Path,
        default=Path(
            "../../ai_detector/src/code-analyzer-tree-sitter/build/my-languages.so"
        ),
    )
    parser.add_argument(
        "--ast-helper-dir",
        type=Path,
        default=Path("../../ai_detector/src/code-analyzer-tree-sitter"),
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
        default=Path("repo_python/run-py-4a/strict"),
    )
    parser.add_argument(
        "--qc-dir",
        type=Path,
        default=Path("repo_python/tmp/run-py-4a/strict"),
    )
    parser.add_argument("--chunksize", type=int, default=200_000)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a small matching test without reading project data.",
    )
    return parser.parse_args()


def resolved_file(path: Path, label: str) -> Path:
    result = path.expanduser().resolve()
    if not result.is_file():
        raise FileNotFoundError(f"Missing {label}: {result}")
    return result


def resolved_dir(path: Path, label: str) -> Path:
    result = path.expanduser().resolve()
    if not result.is_dir():
        raise FileNotFoundError(f"Missing {label}: {result}")
    return result


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def month_number(period: pd.Period) -> int:
    return period.year * 12 + period.month


def eligible_python_path(path_text: str | None) -> bool:
    if not path_text:
        return False
    path = PurePosixPath(path_text)
    return path.suffix == ".py" and not any(
        part in EXCLUDED_PARTS for part in path.parts
    )


def run_git(repo: Path, arguments: Iterable[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        check=False,
    )


def parse_name_status_z(raw: bytes) -> list[FileChange]:
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes: list[FileChange] = []
    index = 0
    while index < len(fields):
        raw_status = fields[index].decode("ascii", errors="replace")
        index += 1
        if not raw_status:
            raise ValueError("Blank git diff status")
        status_code = raw_status[0]
        if status_code in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ValueError(f"Incomplete rename/copy record: {raw_status}")
            previous_path = fields[index].decode("utf-8", errors="surrogateescape")
            current_path = fields[index + 1].decode(
                "utf-8", errors="surrogateescape"
            )
            index += 2
        else:
            if index >= len(fields):
                raise ValueError(f"Incomplete path record: {raw_status}")
            path_text = fields[index].decode("utf-8", errors="surrogateescape")
            index += 1
            if status_code == "A":
                previous_path, current_path = None, path_text
            elif status_code == "D":
                previous_path, current_path = path_text, None
            else:
                previous_path, current_path = path_text, path_text
        changes.append(
            FileChange(
                raw_status=raw_status,
                status_code=status_code,
                previous_path=previous_path,
                current_path=current_path,
            )
        )
    return changes


def normalize_python_change(change: FileChange) -> FileChange | None:
    previous_is_python = eligible_python_path(change.previous_path)
    current_is_python = eligible_python_path(change.current_path)
    if not previous_is_python and not current_is_python:
        return None
    if previous_is_python and current_is_python:
        return change
    if current_is_python:
        return FileChange(
            raw_status=change.raw_status,
            status_code="A",
            previous_path=None,
            current_path=change.current_path,
        )
    return FileChange(
        raw_status=change.raw_status,
        status_code="D",
        previous_path=change.previous_path,
        current_path=None,
    )


def load_parser_and_ast_function(lib_path: Path, helper_dir: Path):
    try:
        from tree_sitter import Language, Parser
    except ImportError as exc:
        raise RuntimeError(
            "tree_sitter is not installed in the active Python environment"
        ) from exc

    language = Language(str(lib_path), "python")
    parser = Parser()
    parser.set_language(language)

    helper_text = str(helper_dir)
    if helper_text not in sys.path:
        sys.path.insert(0, helper_text)
    from tree_sitter_ast_python import F  # type: ignore

    return parser, F


def node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )


def node_name(node, source_bytes: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return node_text(name_node, source_bytes)


def extract_blocks(source: str, parser) -> list[dict[str, Any]]:
    """Use the same top-level block boundaries as agc_detector.py."""
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node
    blocks: list[dict[str, Any]] = []

    for child in root.children:
        target = None
        if child.type in ("function_definition", "class_definition"):
            target = child
        elif child.type == "decorated_definition":
            for nested in child.children:
                if nested.type in ("function_definition", "class_definition"):
                    target = nested
                    break
        elif child.type == "async_function_definition":
            target = child

        if target is None:
            continue

        kind = (
            "class_definition"
            if target.type == "class_definition"
            else "function_definition"
        )
        outer = child
        blocks.append(
            {
                "kind": kind,
                "name": node_name(target, source_bytes) or "<anon>",
                "start_line": outer.start_point[0] + 1,
                "end_line": outer.end_point[0] + 1,
                "code": node_text(outer, source_bytes),
            }
        )
    return blocks


def generate_ast_sequence(code: str, parser, ast_function) -> str:
    code_bytes = code.encode("utf-8")
    tree = parser.parse(code_bytes)
    return " ".join(ast_function(tree.root_node, code_bytes))


def read_python_source(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def load_input_check_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("status") != "PASS" or int(payload.get("checks_failed", 0)) != 0:
        raise RuntimeError(
            f"Changed-block input check is not PASS: {path}"
        )
    return payload


def load_manifest(path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(path, dtype={"latest_commit": "string"})
    missing = sorted(set(MANIFEST_COLUMNS) - set(manifest.columns))
    if missing:
        raise ValueError(f"Manifest missing columns: {missing}")

    for column in ["dataset_source", "repo_name", "month", "latest_commit"]:
        manifest[column] = manifest[column].astype(str).str.strip()
    duplicates = int(
        manifest.duplicated(["dataset_source", "repo_name", "month"]).sum()
    )
    if duplicates:
        raise ValueError(f"Duplicate manifest source/repo/month rows: {duplicates}")

    manifest["month_period"] = pd.PeriodIndex(manifest["month"], freq="M")
    manifest = manifest.sort_values(
        ["dataset_source", "repo_name", "month_period"]
    ).reset_index(drop=True)
    grouped = manifest.groupby(["dataset_source", "repo_name"], sort=False)
    manifest["previous_month_period"] = grouped["month_period"].shift(1)
    manifest["previous_commit"] = grouped["latest_commit"].shift(1)
    manifest["previous_month"] = manifest["previous_month_period"].astype("string")
    current_number = manifest["month_period"].map(month_number)
    previous_number = manifest["previous_month_period"].map(
        lambda value: month_number(value) if pd.notna(value) else pd.NA
    )
    manifest["month_gap"] = current_number - previous_number
    return manifest


def build_pair_plans(
    manifest: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> tuple[list[PairPlan], pd.DataFrame, dict[str, set[tuple[str, str, str]]]]:
    clone_roots = {
        "treatment": treatment_clone_dir,
        "control": control_clone_dir,
    }
    plans: list[PairPlan] = []
    diff_rows: list[dict[str, Any]] = []
    needed_current_files: dict[str, set[tuple[str, str, str]]] = {
        "treatment": set(),
        "control": set(),
    }

    total = len(manifest)
    for number, row in enumerate(manifest.itertuples(index=False), start=1):
        source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        month = str(row.month)
        current_commit = str(row.latest_commit)
        previous_commit = (
            None if pd.isna(row.previous_commit) else str(row.previous_commit)
        )
        previous_month = (
            None
            if pd.isna(row.previous_month_period)
            else str(row.previous_month_period)
        )
        month_gap = None if pd.isna(row.month_gap) else int(row.month_gap)
        repo_dir = clone_roots[source] / repo_name.replace("/", "_")

        if previous_commit is None:
            comparison_status = "no_previous_month"
            changes: list[FileChange] = []
            error = ""
        elif month_gap != 1:
            comparison_status = "nonconsecutive_month"
            changes = []
            error = ""
        elif previous_commit == current_commit:
            comparison_status = "same_commit"
            changes = []
            error = ""
        else:
            result = run_git(
                repo_dir,
                [
                    "diff",
                    "--name-status",
                    "-z",
                    "--find-renames",
                    previous_commit,
                    current_commit,
                    "--",
                ],
            )
            if result.returncode != 0:
                comparison_status = "git_diff_error"
                changes = []
                error = result.stderr.decode("utf-8", errors="replace").strip()
            else:
                comparison_status = "ready"
                error = ""
                parsed = parse_name_status_z(result.stdout)
                changes = []
                for change in parsed:
                    normalized = normalize_python_change(change)
                    if normalized is None:
                        continue
                    changes.append(normalized)
                    diff_rows.append(
                        {
                            "dataset_source": source,
                            "repo_name": repo_name,
                            "month": month,
                            "previous_month": previous_month,
                            "previous_commit": previous_commit,
                            "current_commit": current_commit,
                            "raw_status": normalized.raw_status,
                            "status_code": normalized.status_code,
                            "previous_relative_path": normalized.previous_path or "",
                            "current_relative_path": normalized.current_path or "",
                        }
                    )
                    if normalized.current_path:
                        needed_current_files[source].add(
                            (repo_name, current_commit, normalized.current_path)
                        )

        plans.append(
            PairPlan(
                dataset_source=source,
                repo_name=repo_name,
                month=month,
                previous_month=previous_month,
                previous_commit=previous_commit,
                current_commit=current_commit,
                month_gap=month_gap,
                comparison_status=comparison_status,
                repo_dir=repo_dir,
                file_changes=changes,
                git_diff_error=error,
            )
        )
        if number % 250 == 0 or number == total:
            print(
                f"Git diff planning: {number}/{total} repository-month rows",
                flush=True,
            )

    return plans, pd.DataFrame(diff_rows, columns=FILE_DIFF_FIELDS), needed_current_files


def load_prediction_lookup(
    path: Path,
    expected_source: str,
    needed_files: set[tuple[str, str, str]],
    chunksize: int,
) -> tuple[dict[tuple[str, str, str, int], dict[str, Any]], int]:
    header = pd.read_csv(path, nrows=0)
    missing = sorted(set(PREDICTION_COLUMNS) - set(header.columns))
    if missing:
        raise ValueError(f"Prediction CSV missing columns {missing}: {path}")

    if not needed_files:
        return {}, 0

    needed_tokens = {
        "\x1f".join((repo_name, commit, relative_path))
        for repo_name, commit, relative_path in needed_files
    }
    lookup: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    duplicates = 0

    dtype = {
        "dataset_source": "string",
        "repo_name": "string",
        "commit": "string",
        "relative_path": "string",
        "content_sha256": "string",
        "block_kind": "string",
        "block_name": "string",
        "pred_label": "string",
        "score_mode": "string",
        "model_key": "string",
    }

    for chunk in pd.read_csv(
        path,
        usecols=PREDICTION_COLUMNS,
        dtype=dtype,
        chunksize=chunksize,
        low_memory=False,
    ):
        source_mismatch = chunk["dataset_source"].astype(str).ne(expected_source)
        if source_mismatch.any():
            raise ValueError(
                f"Prediction source mismatch in {path}: {int(source_mismatch.sum())}"
            )
        tokens = (
            chunk["repo_name"].astype(str)
            + "\x1f"
            + chunk["commit"].astype(str)
            + "\x1f"
            + chunk["relative_path"].astype(str)
        )
        selected = chunk.loc[tokens.isin(needed_tokens)].copy()
        for row in selected.itertuples(index=False):
            key = (
                str(row.repo_name),
                str(row.commit),
                str(row.relative_path),
                int(row.block_idx),
            )
            if key in lookup:
                duplicates += 1
                continue
            predicted_agc = int(row.predicted_agc)
            if predicted_agc not in {0, 1}:
                raise ValueError(f"Invalid predicted_agc={predicted_agc} for {key}")
            lookup[key] = {
                "content_sha256": str(row.content_sha256),
                "block_kind": str(row.block_kind),
                "block_name": str(row.block_name),
                "start_line": int(row.start_line),
                "end_line": int(row.end_line),
                "pred_label": str(row.pred_label),
                "predicted_agc": predicted_agc,
                "human_score": row.human_score,
                "human_decision_score": row.human_decision_score,
                "agc_score": row.agc_score,
                "score_mode": str(row.score_mode),
                "model_key": str(row.model_key),
            }
    return lookup, duplicates


def pair_exact_blocks(
    previous_blocks: list[dict[str, Any]],
    current_blocks: list[dict[str, Any]],
    previous_used: set[str],
    current_matches: dict[str, dict[str, Any]],
    current_change_type: dict[str, str],
    current_matching_method: dict[str, str],
    moved_if_path_differs: bool,
) -> None:
    """Match unchanged blocks by kind, name, and detector AST representation."""
    previous_by_key: dict[tuple[str, str, str], deque[dict[str, Any]]] = defaultdict(
        deque
    )
    for block in sorted(previous_blocks, key=lambda item: (item["start_line"], item["block_idx"])):
        if block["uid"] in previous_used:
            continue
        previous_by_key[
            (block["block_kind"], block["block_name"], block["ast_sequence_sha256"])
        ].append(block)

    for current in sorted(current_blocks, key=lambda item: (item["start_line"], item["block_idx"])):
        if current["uid"] in current_change_type:
            continue
        key = (
            current["block_kind"],
            current["block_name"],
            current["ast_sequence_sha256"],
        )
        candidates = previous_by_key.get(key)
        if not candidates:
            continue
        previous = candidates.popleft()
        previous_used.add(previous["uid"])
        current_matches[current["uid"]] = previous
        path_differs = previous["relative_path"] != current["relative_path"]
        current_change_type[current["uid"]] = (
            "moved_unchanged"
            if moved_if_path_differs and path_differs
            else "unchanged"
        )
        current_matching_method[current["uid"]] = "same_kind_name_ast"


def pair_modified_blocks(
    previous_blocks: list[dict[str, Any]],
    current_blocks: list[dict[str, Any]],
    previous_used: set[str],
    current_matches: dict[str, dict[str, Any]],
    current_change_type: dict[str, str],
    current_matching_method: dict[str, str],
) -> None:
    """Pair remaining same-name blocks within one file mapping as modified."""
    previous_by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    current_by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for block in previous_blocks:
        if block["uid"] not in previous_used:
            previous_by_name[(block["block_kind"], block["block_name"])].append(block)
    for block in current_blocks:
        if block["uid"] not in current_change_type:
            current_by_name[(block["block_kind"], block["block_name"])].append(block)

    for key in sorted(set(previous_by_name) & set(current_by_name)):
        previous_values = sorted(
            previous_by_name[key], key=lambda item: (item["start_line"], item["block_idx"])
        )
        current_values = sorted(
            current_by_name[key], key=lambda item: (item["start_line"], item["block_idx"])
        )
        for previous, current in zip(previous_values, current_values):
            previous_used.add(previous["uid"])
            current_matches[current["uid"]] = previous
            current_change_type[current["uid"]] = "modified"
            current_matching_method[current["uid"]] = "same_kind_name_changed_ast"


def classify_blocks(
    file_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Classify current blocks and return unmatched previous blocks as deleted."""
    previous_used: set[str] = set()
    current_matches: dict[str, dict[str, Any]] = {}
    current_change_type: dict[str, str] = {}
    current_matching_method: dict[str, str] = {}

    all_previous: list[dict[str, Any]] = []
    all_current: list[dict[str, Any]] = []

    for group in file_groups:
        previous_blocks = group["previous_blocks"]
        current_blocks = group["current_blocks"]
        all_previous.extend(previous_blocks)
        all_current.extend(current_blocks)

        pair_exact_blocks(
            previous_blocks,
            current_blocks,
            previous_used,
            current_matches,
            current_change_type,
            current_matching_method,
            moved_if_path_differs=True,
        )
        pair_modified_blocks(
            previous_blocks,
            current_blocks,
            previous_used,
            current_matches,
            current_change_type,
            current_matching_method,
        )

    # Detect an unchanged block moved across files, including moves that Git
    # reports as a delete plus add rather than as a rename.
    remaining_previous = [
        block for block in all_previous if block["uid"] not in previous_used
    ]
    remaining_current = [
        block for block in all_current if block["uid"] not in current_change_type
    ]
    pair_exact_blocks(
        remaining_previous,
        remaining_current,
        previous_used,
        current_matches,
        current_change_type,
        current_matching_method,
        moved_if_path_differs=True,
    )

    for current in all_current:
        if current["uid"] not in current_change_type:
            current_change_type[current["uid"]] = "added"
            current_matching_method[current["uid"]] = "current_block_without_match"

    classifications: list[dict[str, Any]] = []
    for current in all_current:
        previous = current_matches.get(current["uid"])
        classifications.append(
            {
                **current,
                "change_type": current_change_type[current["uid"]],
                "matching_method": current_matching_method[current["uid"]],
                "previous_block": previous,
            }
        )

    deleted = [block for block in all_previous if block["uid"] not in previous_used]
    return classifications, deleted


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def metric_column_names(scope: str, unit: str) -> tuple[str, str, str, str]:
    return (
        f"{scope}_{unit}_blocks",
        f"{scope}_agc_{unit}_blocks",
        f"{scope}_hwc_{unit}_blocks",
        f"agc_{scope}_{unit}_block_ratio",
    )


def aggregate_changed_blocks(
    classifications: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    changed = [
        row for row in classifications if row["change_type"] in {"added", "modified"}
    ]

    def summarize(
        rows: Sequence[dict[str, Any]], scope: str, unit: str
    ) -> dict[str, Any]:
        total = len(rows)
        agc = sum(int(row["prediction"]["predicted_agc"]) for row in rows)
        hwc = total - agc
        total_column, agc_column, hwc_column, ratio_column = metric_column_names(
            scope, unit
        )
        return {
            total_column: total,
            agc_column: agc,
            hwc_column: hwc,
            ratio_column: safe_ratio(agc, total),
        }

    output: dict[str, Any] = {}
    output.update(summarize(changed, "changed", "top_level"))
    output.update(
        summarize(
            [row for row in changed if row["change_type"] == "added"],
            "added",
            "top_level",
        )
    )
    output.update(
        summarize(
            [row for row in changed if row["change_type"] == "modified"],
            "modified",
            "top_level",
        )
    )
    output.update(
        summarize(
            [row for row in changed if row["block_kind"] == "function_definition"],
            "changed",
            "function",
        )
    )
    output.update(
        summarize(
            [row for row in changed if row["block_kind"] == "class_definition"],
            "changed",
            "class",
        )
    )
    return output


def empty_outcome_counts(value: Any = 0) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for scope, unit in METRIC_SPECS:
        total_column, agc_column, hwc_column, ratio_column = metric_column_names(
            scope, unit
        )
        result[total_column] = value
        result[agc_column] = value
        result[hwc_column] = value
        result[ratio_column] = None
    return result


def build_classification_output(
    plan: PairPlan,
    classification: dict[str, Any],
) -> dict[str, Any]:
    current = classification
    previous = classification.get("previous_block")
    prediction = current["prediction"]
    predicted_agc = int(prediction["predicted_agc"])
    return {
        "dataset_source": plan.dataset_source,
        "repo_name": plan.repo_name,
        "month": plan.month,
        "previous_month": plan.previous_month or "",
        "previous_commit": plan.previous_commit or "",
        "current_commit": plan.current_commit,
        "file_status": current["file_status"],
        "previous_relative_path": (
            previous["relative_path"] if previous is not None else ""
        ),
        "current_relative_path": current["relative_path"],
        "current_content_sha256": current["content_sha256"],
        "current_block_idx": current["block_idx"],
        "block_kind": current["block_kind"],
        "block_name": current["block_name"],
        "start_line": current["start_line"],
        "end_line": current["end_line"],
        "ast_sequence_sha256": current["ast_sequence_sha256"],
        "code_sha256": current["code_sha256"],
        "change_type": current["change_type"],
        "matching_method": current["matching_method"],
        "previous_block_idx": previous["block_idx"] if previous is not None else "",
        "previous_block_name": previous["block_name"] if previous is not None else "",
        "previous_start_line": previous["start_line"] if previous is not None else "",
        "previous_end_line": previous["end_line"] if previous is not None else "",
        "previous_ast_sequence_sha256": (
            previous["ast_sequence_sha256"] if previous is not None else ""
        ),
        "pred_label": prediction["pred_label"],
        "code_label": "AGC" if predicted_agc else "HWC",
        "predicted_agc": predicted_agc,
        "human_score": prediction["human_score"],
        "human_decision_score": prediction["human_decision_score"],
        "agc_score": prediction["agc_score"],
        "score_mode": prediction["score_mode"],
        "model_key": prediction["model_key"],
    }


def validate_prediction_alignment(
    block: dict[str, Any],
    prediction: dict[str, Any] | None,
) -> list[str]:
    if prediction is None:
        return ["prediction_missing"]
    mismatches: list[str] = []
    comparisons = {
        "content_sha256": str(block["content_sha256"]),
        "block_kind": str(block["block_kind"]),
        "block_name": str(block["block_name"]),
        "start_line": int(block["start_line"]),
        "end_line": int(block["end_line"]),
    }
    for field, expected in comparisons.items():
        observed = prediction[field]
        if field in {"start_line", "end_line"}:
            observed = int(observed)
        else:
            observed = str(observed)
        if observed != expected:
            mismatches.append(f"{field}: expected={expected!r} observed={observed!r}")
    return mismatches


def run_self_test() -> int:
    def block(uid: str, path: str, name: str, ast_hash: str, line: int) -> dict[str, Any]:
        return {
            "uid": uid,
            "relative_path": path,
            "block_idx": line,
            "block_kind": "function_definition",
            "block_name": name,
            "start_line": line,
            "end_line": line + 1,
            "ast_sequence_sha256": ast_hash,
        }

    groups = [
        {
            "previous_blocks": [
                block("p1", "c1.py", "f", "old", 1),
                block("p2", "c1.py", "unchanged", "same", 10),
            ],
            "current_blocks": [
                block("c1", "c1.py", "f", "new", 1),
                block("c2", "c1.py", "unchanged", "same", 20),
            ],
        },
        {
            "previous_blocks": [],
            "current_blocks": [block("c3", "a1.py", "added", "added", 1)],
        },
    ]
    classifications, deleted = classify_blocks(groups)
    result = {row["uid"]: row["change_type"] for row in classifications}
    expected = {"c1": "modified", "c2": "unchanged", "c3": "added"}
    if result != expected or deleted:
        raise AssertionError(f"Self-test failed: result={result} deleted={deleted}")
    print("Self-test: PASS")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    started = time.time()
    manifest_path = resolved_file(args.manifest, "snapshot manifest")
    base_panel_path = resolved_file(args.base_panel, "base AGC DiD panel")
    snapshot_root = resolved_dir(args.snapshot_root, "snapshot root")
    detector_root = resolved_dir(args.detector_root, "detector root")
    input_check_path = resolved_file(args.input_check_summary, "input-check summary")
    tree_sitter_lib = resolved_file(args.tree_sitter_lib, "tree-sitter library")
    ast_helper_dir = resolved_dir(args.ast_helper_dir, "AST helper directory")
    treatment_clone_dir = resolved_dir(args.treatment_clone_dir, "treatment clones")
    control_clone_dir = resolved_dir(args.control_clone_dir, "control clones")

    block_paths = {
        "treatment": resolved_file(
            args.block_treatment or detector_root / "block_predictions_treatment.csv",
            "treatment block predictions",
        ),
        "control": resolved_file(
            args.block_control or detector_root / "block_predictions_control.csv",
            "control block predictions",
        ),
    }

    output_dir = args.output_dir.expanduser().resolve()
    qc_dir = args.qc_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    input_check = load_input_check_summary(input_check_path)
    manifest = load_manifest(manifest_path)

    print("=" * 72)
    print("Prepare AGC changed-block repository-month panel")
    print(f"Manifest rows:       {len(manifest)}")
    print(f"Snapshot root:       {snapshot_root}")
    print(f"Detector root:       {detector_root}")
    print(f"Output directory:    {output_dir}")
    print(f"QC directory:        {qc_dir}")
    print("=" * 72)

    plans, file_diffs, needed_current_files = build_pair_plans(
        manifest,
        treatment_clone_dir,
        control_clone_dir,
    )
    atomic_write_csv(file_diffs, qc_dir / "agc_changed_block_file_diffs.csv")

    prediction_lookup: dict[str, dict[tuple[str, str, str, int], dict[str, Any]]] = {}
    prediction_duplicates = 0
    for source in ["treatment", "control"]:
        print(
            f"Loading {source} predictions for "
            f"{len(needed_current_files[source])} changed current files...",
            flush=True,
        )
        lookup, duplicates = load_prediction_lookup(
            block_paths[source],
            source,
            needed_current_files[source],
            args.chunksize,
        )
        prediction_lookup[source] = lookup
        prediction_duplicates += duplicates
        print(f"  Loaded block predictions: {len(lookup)}", flush=True)

    parser, ast_function = load_parser_and_ast_function(
        tree_sitter_lib,
        ast_helper_dir,
    )

    @lru_cache(maxsize=64)
    def load_snapshot_manifest_rows(
        source: str,
        repo_name: str,
        commit: str,
    ) -> dict[str, dict[str, Any]]:
        repo_slug = repo_name.replace("/", "_")
        file_list = snapshot_root / source / repo_slug / commit / "_files.jsonl"
        if not file_list.is_file():
            raise FileNotFoundError(file_list)
        result: dict[str, dict[str, Any]] = {}
        with file_list.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                relative_path = str(row.get("relative_path", ""))
                if relative_path in result:
                    raise ValueError(
                        f"Duplicate path in {file_list} at line {line_number}: "
                        f"{relative_path}"
                    )
                result[relative_path] = row
        return result

    @lru_cache(maxsize=20_000)
    def parse_snapshot_blocks(
        source: str,
        repo_name: str,
        commit: str,
        relative_path: str,
    ) -> tuple[dict[str, Any], ...]:
        manifest_rows = load_snapshot_manifest_rows(source, repo_name, commit)
        manifest_row = manifest_rows.get(relative_path)
        if manifest_row is None:
            raise FileNotFoundError(
                f"Snapshot manifest path missing: {source} {repo_name} "
                f"{commit} {relative_path}"
            )
        if str(manifest_row.get("file_type", "")) != "file":
            return tuple()

        repo_slug = repo_name.replace("/", "_")
        file_path = snapshot_root / source / repo_slug / commit / Path(relative_path)
        if not file_path.is_file() or file_path.is_symlink():
            raise FileNotFoundError(f"Regular snapshot file missing: {file_path}")
        expected_sha = str(manifest_row.get("content_sha256", ""))
        observed_sha = sha256_file(file_path)
        if observed_sha != expected_sha:
            raise ValueError(
                f"Snapshot content hash mismatch: {file_path} "
                f"expected={expected_sha} observed={observed_sha}"
            )

        source_text = read_python_source(file_path)
        extracted = extract_blocks(source_text, parser)
        records: list[dict[str, Any]] = []
        for block_index, block_value in enumerate(extracted, start=1):
            ast_sequence = generate_ast_sequence(
                block_value["code"], parser, ast_function
            )
            records.append(
                {
                    "uid": f"{relative_path}::{block_index}",
                    "relative_path": relative_path,
                    "content_sha256": expected_sha,
                    "block_idx": block_index,
                    "block_kind": block_value["kind"],
                    "block_name": block_value["name"],
                    "start_line": int(block_value["start_line"]),
                    "end_line": int(block_value["end_line"]),
                    "ast_sequence_sha256": sha256_text(ast_sequence),
                    "code_sha256": sha256_text(block_value["code"]),
                }
            )
        return tuple(records)

    classification_path = output_dir / "changed_block_classifications_py.csv"
    classification_temp = classification_path.with_suffix(
        classification_path.suffix + ".tmp"
    )
    pair_qc_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    mismatch_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    classification_row_count = 0

    with classification_temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLASSIFICATION_FIELDS)
        writer.writeheader()

        total_plans = len(plans)
        for plan_number, plan in enumerate(plans, start=1):
            pair_started = time.time()
            base_record: dict[str, Any] = {
                "dataset_source": plan.dataset_source,
                "repo_name": plan.repo_name,
                "month": plan.month,
                "previous_month": plan.previous_month or "",
                "previous_commit": plan.previous_commit or "",
                "current_commit": plan.current_commit,
                "month_gap": plan.month_gap,
                "comparison_status": plan.comparison_status,
            }
            if plan.comparison_status == "git_diff_error":
                error_rows.append(
                    {
                        **base_record,
                        "stage": "git_diff",
                        "error": plan.git_diff_error,
                    }
                )
                pair_qc_rows.append(
                    {
                        **base_record,
                        "python_file_diff_rows": 0,
                        "current_regular_python_files": 0,
                        "previous_regular_python_files": 0,
                        "current_blocks_in_diff_files": pd.NA,
                        "previous_blocks_in_diff_files": pd.NA,
                        "unchanged_blocks": pd.NA,
                        "moved_unchanged_blocks": pd.NA,
                        "added_blocks": pd.NA,
                        "modified_blocks": pd.NA,
                        "deleted_blocks": pd.NA,
                        "prediction_mismatches": pd.NA,
                        "elapsed_seconds": round(time.time() - pair_started, 3),
                    }
                )
                outcome_rows.append({**base_record, **empty_outcome_counts(pd.NA)})
                continue

            if plan.comparison_status in {"no_previous_month", "nonconsecutive_month"}:
                pair_qc_rows.append(
                    {
                        **base_record,
                        "python_file_diff_rows": 0,
                        "current_regular_python_files": 0,
                        "previous_regular_python_files": 0,
                        "current_blocks_in_diff_files": pd.NA,
                        "previous_blocks_in_diff_files": pd.NA,
                        "unchanged_blocks": pd.NA,
                        "moved_unchanged_blocks": pd.NA,
                        "added_blocks": pd.NA,
                        "modified_blocks": pd.NA,
                        "deleted_blocks": pd.NA,
                        "prediction_mismatches": pd.NA,
                        "elapsed_seconds": round(time.time() - pair_started, 3),
                    }
                )
                outcome_rows.append({**base_record, **empty_outcome_counts(pd.NA)})
                continue

            if plan.comparison_status == "same_commit":
                pair_qc_rows.append(
                    {
                        **base_record,
                        "python_file_diff_rows": 0,
                        "current_regular_python_files": 0,
                        "previous_regular_python_files": 0,
                        "current_blocks_in_diff_files": 0,
                        "previous_blocks_in_diff_files": 0,
                        "unchanged_blocks": 0,
                        "moved_unchanged_blocks": 0,
                        "added_blocks": 0,
                        "modified_blocks": 0,
                        "deleted_blocks": 0,
                        "prediction_mismatches": 0,
                        "elapsed_seconds": round(time.time() - pair_started, 3),
                    }
                )
                outcome_rows.append({**base_record, **empty_outcome_counts(0)})
                continue

            try:
                previous_manifest = load_snapshot_manifest_rows(
                    plan.dataset_source,
                    plan.repo_name,
                    str(plan.previous_commit),
                )
                current_manifest = load_snapshot_manifest_rows(
                    plan.dataset_source,
                    plan.repo_name,
                    plan.current_commit,
                )
                file_groups: list[dict[str, Any]] = []
                current_regular_files = 0
                previous_regular_files = 0

                for change_index, change in enumerate(plan.file_changes, start=1):
                    previous_path = change.previous_path
                    current_path = change.current_path
                    previous_regular = bool(
                        previous_path
                        and previous_path in previous_manifest
                        and str(previous_manifest[previous_path].get("file_type", ""))
                        == "file"
                    )
                    current_regular = bool(
                        current_path
                        and current_path in current_manifest
                        and str(current_manifest[current_path].get("file_type", ""))
                        == "file"
                    )
                    previous_regular_files += int(previous_regular)
                    current_regular_files += int(current_regular)

                    previous_blocks = (
                        [
                            {**record, "uid": f"p{change_index}::{record['uid']}"}
                            for record in parse_snapshot_blocks(
                                plan.dataset_source,
                                plan.repo_name,
                                str(plan.previous_commit),
                                str(previous_path),
                            )
                        ]
                        if previous_regular
                        else []
                    )
                    current_blocks = (
                        [
                            {
                                **record,
                                "uid": f"c{change_index}::{record['uid']}",
                                "file_status": change.raw_status,
                            }
                            for record in parse_snapshot_blocks(
                                plan.dataset_source,
                                plan.repo_name,
                                plan.current_commit,
                                str(current_path),
                            )
                        ]
                        if current_regular
                        else []
                    )
                    file_groups.append(
                        {
                            "previous_path": previous_path,
                            "current_path": current_path,
                            "previous_blocks": previous_blocks,
                            "current_blocks": current_blocks,
                        }
                    )

                classifications, deleted_blocks = classify_blocks(file_groups)
                pair_mismatches = 0
                valid_classifications: list[dict[str, Any]] = []
                source_lookup = prediction_lookup[plan.dataset_source]

                for classification in classifications:
                    key = (
                        plan.repo_name,
                        plan.current_commit,
                        classification["relative_path"],
                        int(classification["block_idx"]),
                    )
                    prediction = source_lookup.get(key)
                    problems = validate_prediction_alignment(
                        classification,
                        prediction,
                    )
                    if problems:
                        pair_mismatches += 1
                        mismatch_rows.append(
                            {
                                "dataset_source": plan.dataset_source,
                                "repo_name": plan.repo_name,
                                "month": plan.month,
                                "current_commit": plan.current_commit,
                                "relative_path": classification["relative_path"],
                                "block_idx": classification["block_idx"],
                                "block_kind": classification["block_kind"],
                                "block_name": classification["block_name"],
                                "problems": "; ".join(problems),
                            }
                        )
                        continue
                    classification["prediction"] = prediction
                    valid_classifications.append(classification)
                    writer.writerow(build_classification_output(plan, classification))
                    classification_row_count += 1

                if pair_mismatches:
                    raise RuntimeError(
                        f"Current block prediction mismatches: {pair_mismatches}"
                    )

                aggregates = aggregate_changed_blocks(valid_classifications)
                outcome_rows.append({**base_record, **aggregates})
                type_counts = defaultdict(int)
                for row in valid_classifications:
                    type_counts[row["change_type"]] += 1
                pair_qc_rows.append(
                    {
                        **base_record,
                        "comparison_status": "processed",
                        "python_file_diff_rows": len(plan.file_changes),
                        "current_regular_python_files": current_regular_files,
                        "previous_regular_python_files": previous_regular_files,
                        "current_blocks_in_diff_files": len(valid_classifications),
                        "previous_blocks_in_diff_files": sum(
                            len(group["previous_blocks"]) for group in file_groups
                        ),
                        "unchanged_blocks": type_counts["unchanged"],
                        "moved_unchanged_blocks": type_counts["moved_unchanged"],
                        "added_blocks": type_counts["added"],
                        "modified_blocks": type_counts["modified"],
                        "deleted_blocks": len(deleted_blocks),
                        "prediction_mismatches": pair_mismatches,
                        "elapsed_seconds": round(time.time() - pair_started, 3),
                    }
                )
            except Exception as exc:
                error_rows.append(
                    {
                        **base_record,
                        "stage": "pair_processing",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                pair_qc_rows.append(
                    {
                        **base_record,
                        "comparison_status": "error",
                        "python_file_diff_rows": len(plan.file_changes),
                        "current_regular_python_files": pd.NA,
                        "previous_regular_python_files": pd.NA,
                        "current_blocks_in_diff_files": pd.NA,
                        "previous_blocks_in_diff_files": pd.NA,
                        "unchanged_blocks": pd.NA,
                        "moved_unchanged_blocks": pd.NA,
                        "added_blocks": pd.NA,
                        "modified_blocks": pd.NA,
                        "deleted_blocks": pd.NA,
                        "prediction_mismatches": pd.NA,
                        "elapsed_seconds": round(time.time() - pair_started, 3),
                    }
                )
                outcome_rows.append({**base_record, **empty_outcome_counts(pd.NA)})

            if plan_number % 50 == 0 or plan_number == total_plans:
                print(
                    f"Block comparison: {plan_number}/{total_plans} rows; "
                    f"classification rows={classification_row_count}",
                    flush=True,
                )

    os.replace(classification_temp, classification_path)

    pair_qc = pd.DataFrame(pair_qc_rows)
    outcomes = pd.DataFrame(outcome_rows)
    mismatches = pd.DataFrame(mismatch_rows, columns=MISMATCH_FIELDS)
    errors = pd.DataFrame(error_rows, columns=ERROR_FIELDS)

    outcome_path = output_dir / "repo_month_agc_changed_block_outcomes_py.csv"
    pair_qc_path = qc_dir / "agc_changed_block_pair_qc.csv"
    mismatch_path = qc_dir / "agc_changed_block_prediction_mismatches.csv"
    error_path = qc_dir / "agc_changed_block_errors.csv"

    atomic_write_csv(outcomes, outcome_path)
    atomic_write_csv(pair_qc, pair_qc_path)
    atomic_write_csv(
        mismatches,
        mismatch_path,
    )
    atomic_write_csv(errors, error_path)

    base_panel = pd.read_csv(base_panel_path, dtype={"latest_commit": "string"})
    missing_base = sorted(set(BASE_PANEL_COLUMNS) - set(base_panel.columns))
    if missing_base:
        raise ValueError(f"Base panel missing columns: {missing_base}")
    for column in ["dataset_source", "repo_name", "time", "latest_commit"]:
        base_panel[column] = base_panel[column].astype(str).str.strip()

    merge_outcomes = outcomes.rename(
        columns={"month": "time", "current_commit": "latest_commit"}
    ).copy()
    merge_columns = [
        column
        for column in merge_outcomes.columns
        if column
        not in {
            "previous_month",
            "previous_commit",
            "month_gap",
        }
    ]
    merge_outcomes = merge_outcomes[merge_columns]
    panel = base_panel.merge(
        merge_outcomes,
        on=["dataset_source", "repo_name", "time", "latest_commit"],
        how="left",
        validate="one_to_one",
        indicator="_changed_block_merge",
    )
    unmatched_panel_rows = int(panel["_changed_block_merge"].ne("both").sum())
    panel = panel.drop(columns=["_changed_block_merge"])

    paper_covariates = [
        "agc_changed_top_level_block_ratio",
        "age",
        "contributors",
        "stars",
        "issues",
        "ncloc_paper",
    ]
    snapshot_covariates = [
        "agc_changed_top_level_block_ratio",
        "age",
        "contributors",
        "stars",
        "issues",
        "ncloc_python_snapshot",
    ]
    if set(paper_covariates).issubset(panel.columns):
        panel["analysis_ready_agc_changed_block_paper_ncloc"] = (
            panel[paper_covariates].notna().all(axis=1).astype(int)
        )
    if set(snapshot_covariates).issubset(panel.columns):
        panel["analysis_ready_agc_changed_block_python_snapshot_ncloc"] = (
            panel[snapshot_covariates].notna().all(axis=1).astype(int)
        )

    panel_path = output_dir / "panel_event_monthly_agc_changed_block_py.csv"
    atomic_write_csv(panel, panel_path)

    checks: list[dict[str, Any]] = []

    def add_check(section: str, check: str, passed: bool, value: Any) -> None:
        checks.append(
            {
                "section": section,
                "check": check,
                "passed": int(bool(passed)),
                "value": value,
            }
        )

    add_check(
        "upstream",
        "input_check_pass",
        input_check.get("status") == "PASS",
        input_check.get("status"),
    )
    add_check(
        "predictions",
        "filtered_prediction_keys_unique",
        prediction_duplicates == 0,
        prediction_duplicates,
    )
    add_check("processing", "pair_errors_zero", len(errors) == 0, len(errors))
    add_check(
        "processing",
        "prediction_mismatches_zero",
        len(mismatches) == 0,
        len(mismatches),
    )
    add_check(
        "panel",
        "base_rows_preserved",
        len(panel) == len(base_panel),
        f"output={len(panel)} input={len(base_panel)}",
    )
    add_check(
        "panel",
        "base_rows_all_matched",
        unmatched_panel_rows == 0,
        unmatched_panel_rows,
    )
    duplicate_panel_keys = int(
        panel.duplicated(["dataset_source", "repo_name", "time"]).sum()
    )
    add_check(
        "panel",
        "unique_source_repo_month",
        duplicate_panel_keys == 0,
        duplicate_panel_keys,
    )

    arithmetic_failures = 0
    ratio_failures = 0
    available = outcomes.loc[outcomes["changed_top_level_blocks"].notna()].copy()
    for scope, unit in METRIC_SPECS:
        total_column, agc_column, hwc_column, ratio_column = metric_column_names(
            scope, unit
        )
        totals = pd.to_numeric(available[total_column], errors="coerce")
        agc_values = pd.to_numeric(available[agc_column], errors="coerce")
        hwc_values = pd.to_numeric(available[hwc_column], errors="coerce")
        arithmetic_failures += int((totals != agc_values + hwc_values).sum())
        expected_ratio = agc_values / totals.where(totals.ne(0))
        observed_ratio = pd.to_numeric(available[ratio_column], errors="coerce")
        ratio_failures += int(
            ((totals.eq(0)) & observed_ratio.notna()).sum()
            + (
                totals.gt(0)
                & (observed_ratio - expected_ratio).abs().gt(1e-12)
            ).sum()
        )

    changed_totals = pd.to_numeric(
        available["changed_top_level_blocks"], errors="coerce"
    )
    added_totals = pd.to_numeric(
        available["added_top_level_blocks"], errors="coerce"
    )
    modified_totals = pd.to_numeric(
        available["modified_top_level_blocks"], errors="coerce"
    )
    function_totals = pd.to_numeric(
        available["changed_function_blocks"], errors="coerce"
    )
    class_totals = pd.to_numeric(
        available["changed_class_blocks"], errors="coerce"
    )
    decomposition_failures = int(
        (changed_totals != added_totals + modified_totals).sum()
        + (changed_totals != function_totals + class_totals).sum()
    )

    add_check(
        "outcomes",
        "agc_hwc_arithmetic",
        arithmetic_failures == 0,
        arithmetic_failures,
    )
    add_check(
        "outcomes",
        "ratio_arithmetic",
        ratio_failures == 0,
        ratio_failures,
    )
    add_check(
        "outcomes",
        "changed_decomposition",
        decomposition_failures == 0,
        decomposition_failures,
    )

    processed_qc = pair_qc.loc[pair_qc["comparison_status"].eq("processed")]
    qc_changed_sum = pd.to_numeric(
        processed_qc["added_blocks"], errors="coerce"
    ).sum() + pd.to_numeric(processed_qc["modified_blocks"], errors="coerce").sum()
    outcome_changed_sum = pd.to_numeric(
        outcomes["changed_top_level_blocks"], errors="coerce"
    ).sum()
    add_check(
        "cross_file",
        "pair_qc_matches_outcomes",
        int(qc_changed_sum) == int(outcome_changed_sum),
        f"pair_qc={int(qc_changed_sum)} outcomes={int(outcome_changed_sum)}",
    )

    checks_frame = pd.DataFrame(checks)
    checks_failed = int(checks_frame["passed"].eq(0).sum())
    status = "PASS" if checks_failed == 0 else "FAIL"

    summary = {
        "status": status,
        "checks_total": len(checks_frame),
        "checks_passed": int(checks_frame["passed"].sum()),
        "checks_failed": checks_failed,
        "manifest_rows": len(manifest),
        "base_panel_rows": len(base_panel),
        "output_panel_rows": len(panel),
        "repositories": int(
            panel[["dataset_source", "repo_name"]].drop_duplicates().shape[0]
        ),
        "pair_status_counts": {
            str(key): int(value)
            for key, value in pair_qc["comparison_status"].value_counts(
                dropna=False
            ).items()
        },
        "classification_rows": classification_row_count,
        "changed_top_level_blocks": int(outcome_changed_sum),
        "changed_agc_top_level_blocks": int(
            pd.to_numeric(
                outcomes["changed_agc_top_level_blocks"], errors="coerce"
            ).sum()
        ),
        "changed_hwc_top_level_blocks": int(
            pd.to_numeric(
                outcomes["changed_hwc_top_level_blocks"], errors="coerce"
            ).sum()
        ),
        "repo_months_with_changed_blocks": int(
            pd.to_numeric(
                outcomes["changed_top_level_blocks"], errors="coerce"
            ).gt(0).sum()
        ),
        "repo_months_with_ratio": int(
            outcomes["agc_changed_top_level_block_ratio"].notna().sum()
        ),
        "prediction_mismatches": len(mismatches),
        "pair_errors": len(errors),
        "elapsed_seconds": round(time.time() - started, 3),
        "input_manifest": str(manifest_path),
        "base_panel": str(base_panel_path),
        "output_panel": str(panel_path),
        "outcome_file": str(outcome_path),
        "classification_file": str(classification_path),
    }

    checks_path = qc_dir / "agc_changed_block_prepare_checks.csv"
    summary_path = qc_dir / "agc_changed_block_prepare_summary.json"
    atomic_write_csv(checks_frame, checks_path)
    atomic_write_json(summary, summary_path)

    print("=" * 72)
    print("AGC changed-block preparation")
    print(f"Status:                    {status}")
    print(
        f"Checks passed:             {summary['checks_passed']}/"
        f"{summary['checks_total']}"
    )
    print(f"Output panel rows:         {len(panel)}")
    print(f"Changed top-level blocks:  {summary['changed_top_level_blocks']}")
    print(f"Changed AGC blocks:        {summary['changed_agc_top_level_blocks']}")
    print(f"Changed HWC blocks:        {summary['changed_hwc_top_level_blocks']}")
    print(f"Repo-months with ratio:    {summary['repo_months_with_ratio']}")
    print(f"Pair errors:               {len(errors)}")
    print(f"Prediction mismatches:     {len(mismatches)}")
    print(f"Output panel:              {panel_path}")
    print(f"Summary:                   {summary_path}")
    print("=" * 72)

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
