#!/usr/bin/env python3
"""Prepare repository-month AGC outcomes for the strict Python DiD panel.

The script combines validated block-level detector outputs with the exact
repository-month snapshot manifest, verifies the reconstructed top-level block
outcomes against the detector's existing repository-month outputs, and then
left-joins the AGC outcomes to the strict matched DiD panel.

The primary outcome is the share of scored top-level Python function and class
blocks classified as AI-generated-like. Function-only and class-only shares are
also retained as secondary outcomes. These outcomes capture structural
similarity to AI-generated code in the detector's training distribution; they
do not establish code provenance or identify a specific AI tool.

Revision v3 validates strict-panel treatment indicators before expensive work
and can reuse a previously validated repository-commit snapshot NCLOC file.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import tempfile
import tokenize
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


KEY_COLS = ["repo_name", "time", "dataset_source"]
MANIFEST_KEY_COLS = ["dataset_source", "repo_name", "month"]
COMMIT_KEY_COLS = ["dataset_source", "repo_name", "commit"]
ALLOWED_SOURCES = {"treatment", "control"}
ALLOWED_BLOCK_KINDS = {"function_definition", "class_definition"}

PANEL_IDENTITY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "is_treatment",
]

EVENT_COLS = [
    "event",
    "post_event",
    "time_to_event",
    "lead_6",
    "lead_5",
    "lead_4",
    "lead_3",
    "lead_2",
    "lead_1",
    "lag_0",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "lag_5",
    "lag_6",
    "cursor",
]

ACTIVITY_COLS = [
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
]

PAPER_COVARIATE_COLS = [
    "stars",
    "issues",
    "age",
    "ncloc_paper",
]

COVARIATE_COLS = PAPER_COVARIATE_COLS + [
    "ncloc_python_snapshot",
]

COVARIATE_AUDIT_COLS = [
    "paper_covariate_matched",
    "python_snapshot_ncloc_matched",
    "analysis_ready_agc_paper_ncloc",
    "analysis_ready_agc_python_snapshot_ncloc",
]

SNAPSHOT_AUDIT_COLS = [
    "latest_commit",
    "python_file_count",
    "files_analyzed",
    "failure_count",
    "agc_analysis_status",
    "agc_repo_month_matched",
]

TOP_LEVEL_COLS = [
    "top_level_blocks_scored",
    "agc_top_level_blocks",
    "human_top_level_blocks",
    "agc_top_level_block_ratio",
]

FUNCTION_COLS = [
    "function_blocks_scored",
    "agc_function_blocks",
    "human_function_blocks",
    "agc_function_block_ratio",
]

CLASS_COLS = [
    "class_blocks_scored",
    "agc_class_blocks",
    "human_class_blocks",
    "agc_class_block_ratio",
]

OUTPUT_COLS = (
    PANEL_IDENTITY_COLS
    + EVENT_COLS
    + ACTIVITY_COLS
    + COVARIATE_COLS
    + COVARIATE_AUDIT_COLS
    + SNAPSHOT_AUDIT_COLS
    + TOP_LEVEL_COLS
    + FUNCTION_COLS
    + CLASS_COLS
)

COUNT_COLS = [
    "top_level_blocks_scored",
    "agc_top_level_blocks",
    "human_top_level_blocks",
    "function_blocks_scored",
    "agc_function_blocks",
    "human_function_blocks",
    "class_blocks_scored",
    "agc_class_blocks",
    "human_class_blocks",
]

RATIO_COLS = [
    "agc_top_level_block_ratio",
    "agc_function_block_ratio",
    "agc_class_block_ratio",
]

METADATA_COMPARE_FIELDS = [
    "experiment",
    "classifier",
    "representation",
    "model_sha256",
    "model_key",
    "embedding_model_id",
    "max_len",
    "threshold_effective",
    "expected_score_mode",
]


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prepare strict repository-month AGC DiD input."
    )
    parser.add_argument("--base-panel", required=True, type=Path)
    parser.add_argument("--paper-panel", required=True, type=Path)
    parser.add_argument("--snapshot-manifest", required=True, type=Path)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--block-treatment", required=True, type=Path)
    parser.add_argument("--block-control", required=True, type=Path)
    parser.add_argument("--repo-month-treatment", required=True, type=Path)
    parser.add_argument("--repo-month-control", required=True, type=Path)
    parser.add_argument("--run-metadata-treatment", required=True, type=Path)
    parser.add_argument("--run-metadata-control", required=True, type=Path)
    parser.add_argument("--combined-validation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo-commit-ncloc-output", required=True, type=Path)
    parser.add_argument("--repo-month-outcomes-output", required=True, type=Path)
    parser.add_argument("--qc-dir", required=True, type=Path)
    parser.add_argument(
        "--reuse-repo-commit-ncloc",
        action="store_true",
        help=(
            "Reuse an existing validated repository-commit snapshot NCLOC "
            "output when the file exists. Missing files are recomputed."
        ),
    )
    parser.add_argument("--panel-label", default="strict")
    parser.add_argument(
        "--chunksize",
        type=int,
        default=250_000,
        help="Rows per block-prediction CSV chunk. Default: 250000.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    """Fail clearly when an input file is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    """Require a set of columns in a DataFrame."""
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def require_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    """Fail when a key is duplicated."""
    duplicate_count = int(df.duplicated(keys).sum())
    if duplicate_count:
        sample = df.loc[df.duplicated(keys, keep=False), keys].head(20)
        raise ValueError(
            f"{label} has {duplicate_count} duplicate rows for key {keys}.\n"
            f"Sample:\n{sample.to_string(index=False)}"
        )


def normalize_month_value(value: object) -> str:
    """Normalize a month value to YYYY-MM when possible."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return text


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Compute a ratio while preserving missingness for zero denominators."""
    numerator_numeric = pd.to_numeric(numerator, errors="coerce")
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    result = pd.Series(np.nan, index=denominator.index, dtype="float64")
    valid = denominator_numeric.gt(0)
    result.loc[valid] = numerator_numeric.loc[valid] / denominator_numeric.loc[valid]
    return result


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
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
        temp_path = Path(handle.name)
        df.to_csv(handle, index=False)
    os.replace(temp_path, path)


def load_json(path: Path, label: str) -> dict[str, Any]:
    """Load a JSON object."""
    require_file(path, label)
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def first_nonmissing(series: pd.Series) -> Any:
    """Return the first nonmissing value from a grouped series."""
    values = series.dropna()
    if values.empty:
        return np.nan
    return values.iloc[0]


def load_paper_covariates(
    path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load frozen-paper covariates and audit duplicate repository-month keys."""
    require_file(path, "frozen paper panel")
    source_columns = KEY_COLS + ["stars", "issues", "age", "ncloc"]
    paper = pd.read_csv(path, usecols=source_columns, low_memory=False)
    require_columns(paper, source_columns, "frozen paper panel")

    paper["repo_name"] = paper["repo_name"].astype(str).str.strip()
    paper["dataset_source"] = paper["dataset_source"].astype(str).str.strip()
    paper["time"] = paper["time"].map(normalize_month_value)

    invalid_sources = sorted(set(paper["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(f"Frozen paper panel has invalid sources: {invalid_sources}")

    duplicate_rows = paper.loc[paper.duplicated(KEY_COLS, keep=False)].copy()
    duplicate_summary_rows: list[dict[str, Any]] = []
    conflict_rows: list[pd.DataFrame] = []
    source_covariates = ["stars", "issues", "age", "ncloc"]

    if not duplicate_rows.empty:
        for key_values, group in duplicate_rows.groupby(KEY_COLS, dropna=False):
            if not isinstance(key_values, tuple):
                key_values = (key_values,)
            key_record = dict(zip(KEY_COLS, key_values))
            unique_counts = {
                column: int(group[column].dropna().nunique())
                for column in source_covariates
            }
            has_conflict = any(count > 1 for count in unique_counts.values())
            duplicate_summary_rows.append(
                {
                    **key_record,
                    "duplicate_rows": len(group),
                    **{
                        f"{column}_unique_nonmissing": count
                        for column, count in unique_counts.items()
                    },
                    "has_conflict": int(has_conflict),
                }
            )
            if has_conflict:
                conflict = group.copy()
                conflict["conflict_reason"] = ";".join(
                    column
                    for column, count in unique_counts.items()
                    if count > 1
                )
                conflict_rows.append(conflict)

    duplicate_summary = pd.DataFrame(
        duplicate_summary_rows,
        columns=(
            KEY_COLS
            + [
                "duplicate_rows",
                "stars_unique_nonmissing",
                "issues_unique_nonmissing",
                "age_unique_nonmissing",
                "ncloc_unique_nonmissing",
                "has_conflict",
            ]
        ),
    )
    conflicts = (
        pd.concat(conflict_rows, ignore_index=True)
        if conflict_rows
        else pd.DataFrame(columns=source_columns + ["conflict_reason"])
    )

    collapsed = (
        paper.groupby(KEY_COLS, as_index=False, dropna=False)[source_covariates]
        .agg(first_nonmissing)
        .rename(columns={"ncloc": "ncloc_paper"})
    )
    require_unique(collapsed, KEY_COLS, "collapsed frozen paper covariates")
    return collapsed, duplicate_summary, conflicts


def merge_paper_covariates(
    base: pd.DataFrame,
    paper_lookup: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Left-join frozen-paper covariates while preserving the strict base sample."""
    merged = base.merge(
        paper_lookup,
        on=KEY_COLS,
        how="left",
        validate="one_to_one",
        indicator="__paper_merge",
    )
    merged["paper_covariate_matched"] = merged["__paper_merge"].eq("both").astype(int)

    unmatched = merged.loc[
        merged["paper_covariate_matched"] == 0,
        KEY_COLS + ["is_treatment", "event", "post_event", "time_to_event"],
    ].copy()

    summary_rows: list[dict[str, Any]] = []
    for source in ["treatment", "control", "all"]:
        part = merged if source == "all" else merged.loc[merged["dataset_source"] == source]
        matched_rows = int(part["paper_covariate_matched"].sum())
        row = {
            "dataset_source": source,
            "base_rows": len(part),
            "paper_matched_rows": matched_rows,
            "paper_unmatched_rows": len(part) - matched_rows,
            "paper_match_rate": matched_rows / len(part) if len(part) else np.nan,
        }
        for column in PAPER_COVARIATE_COLS:
            row[f"{column}_nonmissing"] = int(part[column].notna().sum())
            row[f"{column}_missing"] = int(part[column].isna().sum())
        summary_rows.append(row)

    missingness_rows: list[dict[str, Any]] = []
    for source in ["treatment", "control", "all"]:
        part = merged if source == "all" else merged.loc[merged["dataset_source"] == source]
        for column in PAPER_COVARIATE_COLS:
            missingness_rows.append(
                {
                    "dataset_source": source,
                    "covariate": column,
                    "rows": len(part),
                    "nonmissing": int(part[column].notna().sum()),
                    "missing": int(part[column].isna().sum()),
                    "missing_rate": part[column].isna().mean() if len(part) else np.nan,
                }
            )

    merged = merged.drop(columns=["__paper_merge"])
    return (
        merged,
        unmatched,
        pd.DataFrame(summary_rows),
        pd.DataFrame(missingness_rows),
    )


def decode_python_source(data: bytes) -> str:
    """Decode Python source using the encoding declaration when available."""
    reader = io.BytesIO(data).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return data.decode(encoding)


def count_python_ncloc(data: bytes) -> tuple[int, int, int, str]:
    """Count nonblank, non-comment physical lines while retaining docstrings.

    The tokenizer identifies code-bearing physical lines. COMMENT-only and blank
    lines are excluded. Multiline STRING tokens, including module/class/function
    docstrings, mark each nonblank physical line in their span as code.
    """
    text = decode_python_source(data)
    lines = text.splitlines()
    nonblank_lines = {
        number
        for number, line in enumerate(lines, start=1)
        if line.strip()
    }
    code_lines: set[int] = set()
    ignored_types = {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.COMMENT,
    }

    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in ignored_types:
                continue
            start_line = max(1, token.start[0])
            end_line = max(start_line, token.end[0])
            for line_number in range(start_line, end_line + 1):
                if line_number in nonblank_lines:
                    code_lines.add(line_number)
        method = "python_tokenize"
    except (tokenize.TokenError, IndentationError, SyntaxError):
        code_lines = {
            number
            for number, line in enumerate(lines, start=1)
            if line.strip() and not line.lstrip().startswith("#")
        }
        method = "fallback_line_rule"

    ncloc = len(code_lines)
    comment_only_lines = len(nonblank_lines - code_lines)
    return ncloc, len(lines), comment_only_lines, method


def resolve_snapshot_dir(
    snapshot_root: Path,
    source: str,
    repo_name: str,
    commit: str,
) -> Path:
    """Resolve the canonical local snapshot directory."""
    repo_slug = repo_name.replace("/", "_")
    return snapshot_root / source / repo_slug / commit


def compute_python_snapshot_ncloc(
    manifest: pd.DataFrame,
    snapshot_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute Python-only NCLOC once per unique historical repository commit."""
    if not snapshot_root.is_dir():
        raise FileNotFoundError(f"Python snapshot root not found: {snapshot_root}")

    unique_commits = (
        manifest[["dataset_source", "repo_name", "latest_commit", "python_file_count"]]
        .drop_duplicates(["dataset_source", "repo_name", "latest_commit"])
        .sort_values(["dataset_source", "repo_name", "latest_commit"])
        .reset_index(drop=True)
    )

    commit_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    total_commits = len(unique_commits)

    for number, row in enumerate(unique_commits.itertuples(index=False), start=1):
        source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        commit = str(row.latest_commit)
        snapshot_dir = resolve_snapshot_dir(snapshot_root, source, repo_name, commit)
        file_manifest = snapshot_dir / "_files.jsonl"

        commit_result: dict[str, Any] = {
            "dataset_source": source,
            "repo_name": repo_name,
            "latest_commit": commit,
            "snapshot_dir": str(snapshot_dir),
            "python_files_manifest": int(row.python_file_count),
            "regular_python_files_counted": 0,
            "symlinks_skipped": 0,
            "total_physical_lines": 0,
            "comment_only_lines": 0,
            "ncloc_python_snapshot": 0,
            "tokenized_files": 0,
            "fallback_files": 0,
            "ncloc_failure_count": 0,
        }

        if not file_manifest.is_file():
            failure_rows.append(
                {
                    "dataset_source": source,
                    "repo_name": repo_name,
                    "latest_commit": commit,
                    "relative_path": "",
                    "error": f"snapshot file manifest not found: {file_manifest}",
                }
            )
            commit_result["ncloc_failure_count"] += 1
            commit_rows.append(commit_result)
            continue

        with file_manifest.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    relative_path = str(record["relative_path"])
                    file_type = str(record.get("file_type", ""))
                except Exception as exc:
                    failure_rows.append(
                        {
                            "dataset_source": source,
                            "repo_name": repo_name,
                            "latest_commit": commit,
                            "relative_path": f"_files.jsonl:{line_number}",
                            "error": f"invalid file-manifest record: {exc}",
                        }
                    )
                    commit_result["ncloc_failure_count"] += 1
                    continue

                if file_type != "file":
                    commit_result["symlinks_skipped"] += 1
                    continue

                source_path = snapshot_dir / Path(relative_path)
                try:
                    data = source_path.read_bytes()
                    ncloc, physical_lines, comment_lines, method = count_python_ncloc(data)
                    commit_result["regular_python_files_counted"] += 1
                    commit_result["total_physical_lines"] += physical_lines
                    commit_result["comment_only_lines"] += comment_lines
                    commit_result["ncloc_python_snapshot"] += ncloc
                    if method == "python_tokenize":
                        commit_result["tokenized_files"] += 1
                    else:
                        commit_result["fallback_files"] += 1
                except Exception as exc:
                    failure_rows.append(
                        {
                            "dataset_source": source,
                            "repo_name": repo_name,
                            "latest_commit": commit,
                            "relative_path": relative_path,
                            "error": str(exc),
                        }
                    )
                    commit_result["ncloc_failure_count"] += 1

        manifest_count = int(commit_result["python_files_manifest"])
        observed_count = (
            int(commit_result["regular_python_files_counted"])
            + int(commit_result["symlinks_skipped"])
            + int(commit_result["ncloc_failure_count"])
        )
        if observed_count != manifest_count:
            failure_rows.append(
                {
                    "dataset_source": source,
                    "repo_name": repo_name,
                    "latest_commit": commit,
                    "relative_path": "",
                    "error": (
                        "file count mismatch: "
                        f"manifest={manifest_count}, observed={observed_count}"
                    ),
                }
            )
            commit_result["ncloc_failure_count"] += 1

        commit_rows.append(commit_result)
        if number % 100 == 0 or number == total_commits:
            logging.info(
                "Python snapshot NCLOC: %d/%d unique commits processed",
                number,
                total_commits,
            )

    commit_ncloc = pd.DataFrame(commit_rows)
    failures = pd.DataFrame(
        failure_rows,
        columns=[
            "dataset_source",
            "repo_name",
            "latest_commit",
            "relative_path",
            "error",
        ],
    )
    require_unique(
        commit_ncloc,
        ["dataset_source", "repo_name", "latest_commit"],
        "repository-commit Python snapshot NCLOC",
    )
    return commit_ncloc, failures


def load_reusable_repo_commit_ncloc(
    path: Path,
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Load and fully validate a reusable repository-commit NCLOC output."""
    require_file(path, "reusable repository-commit snapshot NCLOC")
    required = [
        "dataset_source",
        "repo_name",
        "latest_commit",
        "snapshot_dir",
        "python_files_manifest",
        "regular_python_files_counted",
        "symlinks_skipped",
        "total_physical_lines",
        "comment_only_lines",
        "ncloc_python_snapshot",
        "tokenized_files",
        "fallback_files",
        "ncloc_failure_count",
    ]
    commit_ncloc = pd.read_csv(
        path,
        low_memory=False,
        dtype={"latest_commit": "string"},
    )
    require_columns(commit_ncloc, required, "reusable repository-commit snapshot NCLOC")
    commit_ncloc = commit_ncloc[required].copy()
    commit_ncloc["dataset_source"] = (
        commit_ncloc["dataset_source"].astype(str).str.strip()
    )
    commit_ncloc["repo_name"] = commit_ncloc["repo_name"].astype(str).str.strip()
    commit_ncloc["latest_commit"] = commit_ncloc["latest_commit"].astype(str).str.strip()

    invalid_sources = sorted(set(commit_ncloc["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC has invalid sources: "
            f"{invalid_sources}"
        )

    commit_keys = ["dataset_source", "repo_name", "latest_commit"]
    require_unique(
        commit_ncloc,
        commit_keys,
        "reusable repository-commit snapshot NCLOC",
    )

    expected = (
        manifest[commit_keys + ["python_file_count"]]
        .drop_duplicates(commit_keys)
        .rename(columns={"python_file_count": "expected_python_files_manifest"})
        .copy()
    )
    require_unique(expected, commit_keys, "expected repository-commit manifest")

    key_check = expected[commit_keys].merge(
        commit_ncloc[commit_keys],
        on=commit_keys,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    missing = int(key_check["_merge"].eq("left_only").sum())
    extra = int(key_check["_merge"].eq("right_only").sum())
    if missing or extra:
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC key mismatch: "
            f"missing={missing}, extra={extra}"
        )

    numeric_columns = [
        "python_files_manifest",
        "regular_python_files_counted",
        "symlinks_skipped",
        "total_physical_lines",
        "comment_only_lines",
        "ncloc_python_snapshot",
        "tokenized_files",
        "fallback_files",
        "ncloc_failure_count",
    ]
    for column in numeric_columns:
        values = pd.to_numeric(commit_ncloc[column], errors="coerce")
        invalid = values.isna() | values.lt(0) | values.mod(1).ne(0)
        if invalid.any():
            raise ValueError(
                f"Reusable repository-commit snapshot NCLOC column {column} has "
                f"{int(invalid.sum())} invalid values"
            )
        commit_ncloc[column] = values.astype("int64")

    checked = commit_ncloc.merge(
        expected,
        on=commit_keys,
        how="left",
        validate="one_to_one",
    )
    expected_count = pd.to_numeric(
        checked["expected_python_files_manifest"], errors="coerce"
    )
    manifest_mismatch = checked["python_files_manifest"].ne(expected_count)
    if manifest_mismatch.any():
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC has "
            f"{int(manifest_mismatch.sum())} Python file-count mismatches"
        )

    failures = checked["ncloc_failure_count"].ne(0)
    if failures.any():
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC has "
            f"{int(failures.sum())} commits with failures"
        )

    observed_files = (
        checked["regular_python_files_counted"] + checked["symlinks_skipped"]
    )
    observed_mismatch = observed_files.ne(checked["python_files_manifest"])
    if observed_mismatch.any():
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC has "
            f"{int(observed_mismatch.sum())} observed file-count mismatches"
        )

    method_mismatch = (
        checked["tokenized_files"] + checked["fallback_files"]
    ).ne(checked["regular_python_files_counted"])
    if method_mismatch.any():
        raise ValueError(
            "Reusable repository-commit snapshot NCLOC has "
            f"{int(method_mismatch.sum())} tokenizer/fallback count mismatches"
        )

    logging.info(
        "Reusing validated Python snapshot NCLOC: %d unique commits from %s",
        len(commit_ncloc),
        path,
    )
    return commit_ncloc.sort_values(commit_keys).reset_index(drop=True)


def expand_snapshot_ncloc_to_month(
    manifest: pd.DataFrame,
    commit_ncloc: pd.DataFrame,
) -> pd.DataFrame:
    """Expand unique-commit snapshot NCLOC to repository-month rows."""
    month_ncloc = manifest.merge(
        commit_ncloc,
        on=["dataset_source", "repo_name", "latest_commit"],
        how="left",
        validate="many_to_one",
        indicator="__ncloc_merge",
        suffixes=("", "_commit"),
    )
    month_ncloc["python_snapshot_ncloc_matched"] = (
        month_ncloc["__ncloc_merge"].eq("both")
        & pd.to_numeric(month_ncloc["ncloc_failure_count"], errors="coerce").fillna(1).eq(0)
    ).astype(int)
    month_ncloc = month_ncloc.drop(columns=["__ncloc_merge"])
    month_ncloc = month_ncloc.rename(columns={"month": "time"})
    require_unique(month_ncloc, KEY_COLS, "repository-month Python snapshot NCLOC")
    return month_ncloc


def build_snapshot_ncloc_summary(
    commit_ncloc: pd.DataFrame,
    month_ncloc: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize snapshot NCLOC coverage by source."""
    rows: list[dict[str, Any]] = []
    for source in ["treatment", "control", "all"]:
        commits = commit_ncloc if source == "all" else commit_ncloc.loc[commit_ncloc["dataset_source"] == source]
        months = month_ncloc if source == "all" else month_ncloc.loc[month_ncloc["dataset_source"] == source]
        rows.append(
            {
                "dataset_source": source,
                "unique_commits": len(commits),
                "repo_month_rows": len(months),
                "matched_repo_month_rows": int(months["python_snapshot_ncloc_matched"].sum()),
                "unmatched_repo_month_rows": int((months["python_snapshot_ncloc_matched"] == 0).sum()),
                "regular_python_files_counted": pd.to_numeric(commits["regular_python_files_counted"], errors="coerce").fillna(0).sum(),
                "tokenized_files": pd.to_numeric(commits["tokenized_files"], errors="coerce").fillna(0).sum(),
                "fallback_files": pd.to_numeric(commits["fallback_files"], errors="coerce").fillna(0).sum(),
                "ncloc_failure_count": pd.to_numeric(commits["ncloc_failure_count"], errors="coerce").fillna(0).sum(),
                "ncloc_python_snapshot_sum": pd.to_numeric(commits["ncloc_python_snapshot"], errors="coerce").fillna(0).sum(),
            }
        )
    return pd.DataFrame(rows)


def build_ncloc_comparison_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compare frozen-paper and snapshot-derived NCLOC where both are present."""
    rows: list[dict[str, Any]] = []
    group_specs = [
        ([], "all"),
        (["dataset_source"], "source"),
        (["dataset_source", "post_event"], "source_post"),
    ]
    for group_cols, group_type in group_specs:
        grouped = [((), df)] if not group_cols else df.groupby(group_cols, dropna=False)
        for group_values, group in grouped:
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            labels = dict(zip(group_cols, group_values))
            pair = group[["ncloc_paper", "ncloc_python_snapshot"]].apply(
                pd.to_numeric, errors="coerce"
            ).dropna()
            paper = pair["ncloc_paper"]
            snapshot = pair["ncloc_python_snapshot"]
            positive_paper = paper.gt(0)
            ratios = snapshot.loc[positive_paper] / paper.loc[positive_paper]
            rows.append(
                {
                    "group_type": group_type,
                    "dataset_source": labels.get("dataset_source", "all"),
                    "post_event": labels.get("post_event", "all"),
                    "paired_rows": len(pair),
                    "paper_mean": paper.mean() if len(pair) else np.nan,
                    "paper_median": paper.median() if len(pair) else np.nan,
                    "snapshot_mean": snapshot.mean() if len(pair) else np.nan,
                    "snapshot_median": snapshot.median() if len(pair) else np.nan,
                    "pearson_correlation": paper.corr(snapshot, method="pearson") if len(pair) > 1 else np.nan,
                    "spearman_correlation": paper.corr(snapshot, method="spearman") if len(pair) > 1 else np.nan,
                    "mean_absolute_difference": (snapshot - paper).abs().mean() if len(pair) else np.nan,
                    "median_snapshot_to_paper_ratio": ratios.median() if len(ratios) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def validate_detector_metadata(
    treatment_path: Path,
    control_path: Path,
    combined_validation_path: Path,
) -> pd.DataFrame:
    """Validate detector provenance and return a comparison table."""
    combined = load_json(combined_validation_path, "combined detector validation")
    if combined.get("status") != "PASS":
        raise ValueError(
            "Combined detector validation is not PASS: "
            f"{combined_validation_path}"
        )
    if combined.get("metadata_comparison_errors") not in ([], None):
        raise ValueError(
            "Combined detector validation reports metadata mismatches: "
            f"{combined.get('metadata_comparison_errors')}"
        )

    treatment = load_json(treatment_path, "treatment run metadata")
    control = load_json(control_path, "control run metadata")

    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for field in METADATA_COMPARE_FIELDS:
        treatment_value = treatment.get(field)
        control_value = control.get(field)
        matches = treatment_value == control_value
        rows.append(
            {
                "field": field,
                "treatment_value": treatment_value,
                "control_value": control_value,
                "matches": int(matches),
            }
        )
        if not matches:
            mismatches.append(
                f"{field}: treatment={treatment_value!r}, control={control_value!r}"
            )

    if mismatches:
        raise ValueError("Detector metadata mismatch: " + "; ".join(mismatches))

    return pd.DataFrame(rows)


def aggregate_block_file(path: Path, source: str, chunksize: int) -> pd.DataFrame:
    """Aggregate one large block-prediction CSV to commit and block kind."""
    require_file(path, f"{source} block predictions")
    usecols = [
        "dataset_source",
        "repo_name",
        "commit",
        "block_kind",
        "predicted_agc",
    ]
    partials: list[pd.DataFrame] = []
    total_rows = 0

    for chunk_number, chunk in enumerate(
        pd.read_csv(path, usecols=usecols, chunksize=chunksize, low_memory=False),
        start=1,
    ):
        total_rows += len(chunk)
        if not chunk["dataset_source"].eq(source).all():
            bad = sorted(chunk.loc[chunk["dataset_source"] != source, "dataset_source"].dropna().astype(str).unique())
            raise ValueError(
                f"{source} block file contains unexpected dataset_source values: {bad}"
            )

        unexpected_kinds = sorted(
            set(chunk["block_kind"].dropna().astype(str)) - ALLOWED_BLOCK_KINDS
        )
        if unexpected_kinds:
            raise ValueError(
                f"{source} block file contains unexpected block_kind values: "
                f"{unexpected_kinds}"
            )

        predicted = pd.to_numeric(chunk["predicted_agc"], errors="coerce")
        invalid = ~predicted.isin([0, 1])
        if invalid.any():
            raise ValueError(
                f"{source} block file has {int(invalid.sum())} invalid predicted_agc values"
            )
        chunk["predicted_agc"] = predicted.astype("int64")
        chunk["human_prediction"] = 1 - chunk["predicted_agc"]

        grouped = (
            chunk.groupby(COMMIT_KEY_COLS + ["block_kind"], as_index=False)
            .agg(
                blocks_scored=("predicted_agc", "size"),
                agc_blocks=("predicted_agc", "sum"),
                human_blocks=("human_prediction", "sum"),
            )
        )
        partials.append(grouped)
        logging.info(
            "%s block aggregation chunk %d: rows=%d cumulative=%d",
            source,
            chunk_number,
            len(chunk),
            total_rows,
        )

    if not partials:
        return pd.DataFrame(
            columns=COMMIT_KEY_COLS
            + ["block_kind", "blocks_scored", "agc_blocks", "human_blocks"]
        )

    combined = pd.concat(partials, ignore_index=True)
    combined = (
        combined.groupby(COMMIT_KEY_COLS + ["block_kind"], as_index=False)[
            ["blocks_scored", "agc_blocks", "human_blocks"]
        ]
        .sum()
    )
    logging.info("%s block rows aggregated: %d", source, total_rows)
    return combined


def make_commit_wide(block_aggregates: pd.DataFrame) -> pd.DataFrame:
    """Convert function/class commit aggregates to one row per commit."""
    function_df = block_aggregates.loc[
        block_aggregates["block_kind"] == "function_definition",
        COMMIT_KEY_COLS + ["blocks_scored", "agc_blocks", "human_blocks"],
    ].rename(
        columns={
            "blocks_scored": "function_blocks_scored",
            "agc_blocks": "agc_function_blocks",
            "human_blocks": "human_function_blocks",
        }
    )

    class_df = block_aggregates.loc[
        block_aggregates["block_kind"] == "class_definition",
        COMMIT_KEY_COLS + ["blocks_scored", "agc_blocks", "human_blocks"],
    ].rename(
        columns={
            "blocks_scored": "class_blocks_scored",
            "agc_blocks": "agc_class_blocks",
            "human_blocks": "human_class_blocks",
        }
    )

    commit_wide = function_df.merge(
        class_df,
        on=COMMIT_KEY_COLS,
        how="outer",
        validate="one_to_one",
    )

    kind_count_cols = FUNCTION_COLS[:3] + CLASS_COLS[:3]
    for column in kind_count_cols:
        if column not in commit_wide.columns:
            commit_wide[column] = 0
        commit_wide[column] = pd.to_numeric(
            commit_wide[column], errors="coerce"
        ).fillna(0).astype("int64")

    commit_wide["top_level_blocks_scored"] = (
        commit_wide["function_blocks_scored"]
        + commit_wide["class_blocks_scored"]
    )
    commit_wide["agc_top_level_blocks"] = (
        commit_wide["agc_function_blocks"] + commit_wide["agc_class_blocks"]
    )
    commit_wide["human_top_level_blocks"] = (
        commit_wide["human_function_blocks"] + commit_wide["human_class_blocks"]
    )

    return commit_wide


def load_snapshot_manifest(path: Path) -> pd.DataFrame:
    """Load and validate the exact repository-month snapshot manifest."""
    require_file(path, "snapshot manifest")
    manifest = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
    required = MANIFEST_KEY_COLS + [
        "latest_commit",
        "python_file_count",
        "has_python_files",
    ]
    require_columns(manifest, required, "snapshot manifest")
    manifest["repo_name"] = manifest["repo_name"].astype(str)
    manifest["dataset_source"] = manifest["dataset_source"].astype(str)
    manifest["month"] = manifest["month"].map(normalize_month_value)
    manifest["latest_commit"] = manifest["latest_commit"].astype(str)

    invalid_sources = sorted(set(manifest["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(f"Snapshot manifest has invalid sources: {invalid_sources}")
    require_unique(manifest, MANIFEST_KEY_COLS, "snapshot manifest")
    return manifest


def expand_commit_outcomes_to_month(
    manifest: pd.DataFrame,
    commit_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Expand unique commit outcomes to all repository-month manifest rows."""
    join_right = commit_wide.rename(columns={"commit": "latest_commit"})
    outcomes = manifest.merge(
        join_right,
        on=["dataset_source", "repo_name", "latest_commit"],
        how="left",
        validate="many_to_one",
        indicator="__commit_match",
    )

    for column in COUNT_COLS:
        if column not in outcomes.columns:
            outcomes[column] = 0
        outcomes[column] = pd.to_numeric(outcomes[column], errors="coerce").fillna(0).astype("int64")

    outcomes["agc_top_level_block_ratio"] = safe_ratio(
        outcomes["agc_top_level_blocks"], outcomes["top_level_blocks_scored"]
    )
    outcomes["agc_function_block_ratio"] = safe_ratio(
        outcomes["agc_function_blocks"], outcomes["function_blocks_scored"]
    )
    outcomes["agc_class_block_ratio"] = safe_ratio(
        outcomes["agc_class_blocks"], outcomes["class_blocks_scored"]
    )

    return outcomes


def load_repo_month_oracle(
    treatment_path: Path,
    control_path: Path,
) -> pd.DataFrame:
    """Load validated detector repository-month outputs used as an oracle."""
    frames: list[pd.DataFrame] = []
    for source, path in (
        ("treatment", treatment_path),
        ("control", control_path),
    ):
        require_file(path, f"{source} repository-month AGC panel")
        frame = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
        required = [
            "dataset_source",
            "repo_name",
            "month",
            "latest_commit",
            "python_file_count",
            "analysis_status",
            "blocks_scored",
            "human_blocks",
            "agc_blocks",
            "agc_block_ratio",
            "files_analyzed",
            "failure_count",
        ]
        require_columns(frame, required, f"{source} repository-month AGC panel")
        if not frame["dataset_source"].astype(str).eq(source).all():
            raise ValueError(
                f"{source} repository-month AGC panel contains another source"
            )
        frames.append(frame)

    oracle = pd.concat(frames, ignore_index=True)
    oracle["repo_name"] = oracle["repo_name"].astype(str)
    oracle["dataset_source"] = oracle["dataset_source"].astype(str)
    oracle["month"] = oracle["month"].map(normalize_month_value)
    oracle["latest_commit"] = oracle["latest_commit"].astype(str)
    require_unique(oracle, MANIFEST_KEY_COLS, "combined repository-month AGC oracle")
    return oracle


def compare_reconstructed_with_oracle(
    reconstructed: pd.DataFrame,
    oracle: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate reconstructed all-block outcomes against existing outputs."""
    manifest_keys = reconstructed[MANIFEST_KEY_COLS]
    oracle_keys = oracle[MANIFEST_KEY_COLS]
    key_check = manifest_keys.merge(
        oracle_keys,
        on=MANIFEST_KEY_COLS,
        how="outer",
        indicator=True,
    )
    if not key_check["_merge"].eq("both").all():
        raise ValueError(
            "Snapshot manifest and repository-month detector outputs do not have "
            "the same keys"
        )

    oracle_selected = oracle[
        MANIFEST_KEY_COLS
        + [
            "latest_commit",
            "python_file_count",
            "analysis_status",
            "blocks_scored",
            "human_blocks",
            "agc_blocks",
            "agc_block_ratio",
            "files_analyzed",
            "failure_count",
        ]
    ].rename(
        columns={
            "latest_commit": "oracle_latest_commit",
            "python_file_count": "oracle_python_file_count",
            "blocks_scored": "oracle_blocks_scored",
            "human_blocks": "oracle_human_blocks",
            "agc_blocks": "oracle_agc_blocks",
            "agc_block_ratio": "oracle_agc_block_ratio",
        }
    )

    compared = reconstructed.merge(
        oracle_selected,
        on=MANIFEST_KEY_COLS,
        how="inner",
        validate="one_to_one",
    )

    compared["latest_commit_matches"] = (
        compared["latest_commit"].astype(str)
        == compared["oracle_latest_commit"].astype(str)
    )
    compared["python_file_count_matches"] = (
        pd.to_numeric(compared["python_file_count"], errors="coerce")
        == pd.to_numeric(compared["oracle_python_file_count"], errors="coerce")
    )
    compared["top_level_blocks_match"] = (
        compared["top_level_blocks_scored"]
        == pd.to_numeric(compared["oracle_blocks_scored"], errors="coerce")
    )
    compared["agc_top_level_blocks_match"] = (
        compared["agc_top_level_blocks"]
        == pd.to_numeric(compared["oracle_agc_blocks"], errors="coerce")
    )
    compared["human_top_level_blocks_match"] = (
        compared["human_top_level_blocks"]
        == pd.to_numeric(compared["oracle_human_blocks"], errors="coerce")
    )

    left_ratio = pd.to_numeric(
        compared["agc_top_level_block_ratio"], errors="coerce"
    )
    right_ratio = pd.to_numeric(compared["oracle_agc_block_ratio"], errors="coerce")
    compared["top_level_ratio_match"] = np.isclose(
        left_ratio,
        right_ratio,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )

    check_cols = [
        "latest_commit_matches",
        "python_file_count_matches",
        "top_level_blocks_match",
        "agc_top_level_blocks_match",
        "human_top_level_blocks_match",
        "top_level_ratio_match",
    ]
    compared["all_checks_pass"] = compared[check_cols].all(axis=1)
    mismatches = compared.loc[~compared["all_checks_pass"]].copy()

    qc_rows = [
        {"check": "reconstructed_repo_month_rows", "value": len(reconstructed)},
        {"check": "oracle_repo_month_rows", "value": len(oracle)},
        {"check": "latest_commit_mismatches", "value": int((~compared["latest_commit_matches"]).sum())},
        {"check": "python_file_count_mismatches", "value": int((~compared["python_file_count_matches"]).sum())},
        {"check": "top_level_block_count_mismatches", "value": int((~compared["top_level_blocks_match"]).sum())},
        {"check": "agc_top_level_count_mismatches", "value": int((~compared["agc_top_level_blocks_match"]).sum())},
        {"check": "human_top_level_count_mismatches", "value": int((~compared["human_top_level_blocks_match"]).sum())},
        {"check": "top_level_ratio_mismatches", "value": int((~compared["top_level_ratio_match"]).sum())},
        {"check": "all_reconstructed_rows_match_oracle", "value": int(mismatches.empty)},
    ]
    qc = pd.DataFrame(qc_rows)

    if not mismatches.empty:
        raise ValueError(
            f"Reconstructed block-kind outcomes disagree with the existing "
            f"repository-month AGC panel for {len(mismatches)} rows"
        )

    outcomes = compared.copy()
    outcomes["agc_analysis_status"] = outcomes["analysis_status"].astype(str)
    outcomes = outcomes.rename(
        columns={
            "oracle_python_file_count": "oracle_python_file_count_for_qc",
        }
    )
    return outcomes, qc


def prepare_outcome_columns(compared: pd.DataFrame) -> pd.DataFrame:
    """Select the validated repository-month outcomes for panel merging."""
    columns = (
        MANIFEST_KEY_COLS
        + [
            "latest_commit",
            "python_file_count",
            "files_analyzed",
            "failure_count",
            "agc_analysis_status",
        ]
        + TOP_LEVEL_COLS
        + FUNCTION_COLS
        + CLASS_COLS
    )
    outcomes = compared[columns].copy()
    outcomes = outcomes.rename(columns={"month": "time"})
    require_unique(outcomes, KEY_COLS, "validated AGC repository-month outcomes")
    return outcomes


def merge_snapshot_ncloc_into_outcomes(
    outcomes: pd.DataFrame,
    month_ncloc: pd.DataFrame,
) -> pd.DataFrame:
    """Attach snapshot-derived Python NCLOC to validated AGC outcomes."""
    selected = month_ncloc[
        KEY_COLS
        + [
            "ncloc_python_snapshot",
            "python_snapshot_ncloc_matched",
            "regular_python_files_counted",
            "tokenized_files",
            "fallback_files",
            "ncloc_failure_count",
        ]
    ].copy()
    merged = outcomes.merge(
        selected,
        on=KEY_COLS,
        how="left",
        validate="one_to_one",
    )
    merged["python_snapshot_ncloc_matched"] = pd.to_numeric(
        merged["python_snapshot_ncloc_matched"], errors="coerce"
    ).fillna(0).astype(int)
    return merged


def load_base_panel(path: Path) -> pd.DataFrame:
    """Load and validate the strict matched DiD panel.

    ``ever_treated`` is the static treatment-group indicator. ``is_treatment``
    is the absorbing post-adoption indicator and must equal ``post_event``.
    ``is_treatment_dynamic`` records contemporaneous Cursor evidence and must
    equal ``cursor``.
    """
    require_file(path, "strict base panel")
    panel = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
    validation_columns = ["ever_treated", "is_treatment_dynamic"]
    required = PANEL_IDENTITY_COLS + EVENT_COLS + ACTIVITY_COLS + validation_columns
    require_columns(panel, required, "strict base panel")

    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["dataset_source"] = panel["dataset_source"].astype(str).str.strip()
    panel["time"] = panel["time"].map(normalize_month_value)
    invalid_sources = sorted(set(panel["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(f"Strict base panel has invalid sources: {invalid_sources}")
    require_unique(panel, KEY_COLS, "strict base panel")

    indicator_columns = [
        "ever_treated",
        "is_treatment",
        "is_treatment_dynamic",
        "post_event",
        "cursor",
    ]
    for column in indicator_columns:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
        invalid = panel[column].isna() | ~panel[column].isin([0, 1])
        if invalid.any():
            raise ValueError(
                f"Strict base panel column {column} has "
                f"{int(invalid.sum())} missing or non-binary values"
            )
        panel[column] = panel[column].astype(int)

    expected_ever_treated = panel["dataset_source"].map(
        {"treatment": 1, "control": 0}
    )
    static_mismatch = panel["ever_treated"].ne(expected_ever_treated)
    absorbing_mismatch = panel["is_treatment"].ne(panel["post_event"])
    dynamic_mismatch = panel["is_treatment_dynamic"].ne(panel["cursor"])
    control_post_mismatch = panel["dataset_source"].eq("control") & (
        panel["post_event"].ne(0) | panel["is_treatment"].ne(0)
    )

    validation_errors: list[str] = []
    if static_mismatch.any():
        validation_errors.append(
            "dataset_source vs ever_treated mismatches="
            f"{int(static_mismatch.sum())}"
        )
    if absorbing_mismatch.any():
        validation_errors.append(
            "is_treatment vs post_event mismatches="
            f"{int(absorbing_mismatch.sum())}"
        )
    if dynamic_mismatch.any():
        validation_errors.append(
            "is_treatment_dynamic vs cursor mismatches="
            f"{int(dynamic_mismatch.sum())}"
        )
    if control_post_mismatch.any():
        validation_errors.append(
            "control post-treatment mismatches="
            f"{int(control_post_mismatch.sum())}"
        )
    if validation_errors:
        raise ValueError(
            "Strict base panel treatment-indicator validation failed: "
            + "; ".join(validation_errors)
        )

    logging.info(
        "Strict base panel validated: rows=%d treatment=%d control=%d "
        "treatment_pre=%d treatment_post=%d",
        len(panel),
        int(panel["dataset_source"].eq("treatment").sum()),
        int(panel["dataset_source"].eq("control").sum()),
        int(
            (
                panel["dataset_source"].eq("treatment")
                & panel["post_event"].eq(0)
            ).sum()
        ),
        int(
            (
                panel["dataset_source"].eq("treatment")
                & panel["post_event"].eq(1)
            ).sum()
        ),
    )
    return panel


def merge_base_panel(
    base: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Left-join validated AGC outcomes to the strict panel."""
    outcome_nonkeys = [column for column in outcomes.columns if column not in KEY_COLS]
    allowed_overlap = {"latest_commit"}
    unexpected_overlap = sorted(
        (set(base.columns) & set(outcome_nonkeys)) - allowed_overlap
    )
    if unexpected_overlap:
        raise ValueError(
            "Base panel already contains AGC output columns that would be overwritten: "
            f"{unexpected_overlap}"
        )

    merge_outcomes = outcomes.copy()
    if "latest_commit" in base.columns:
        merge_outcomes = merge_outcomes.rename(
            columns={"latest_commit": "agc_latest_commit_internal"}
        )

    detector_only = outcomes[KEY_COLS].merge(
        base[KEY_COLS],
        on=KEY_COLS,
        how="left",
        indicator=True,
    )
    detector_only = detector_only.loc[detector_only["_merge"] == "left_only", KEY_COLS]
    if not detector_only.empty:
        detector_only = detector_only.merge(outcomes, on=KEY_COLS, how="left", validate="one_to_one")

    merged = base.merge(
        merge_outcomes,
        on=KEY_COLS,
        how="left",
        validate="one_to_one",
        indicator="__agc_merge",
    )
    merged["agc_repo_month_matched"] = merged["__agc_merge"].eq("both").astype(int)

    if "latest_commit" in base.columns:
        matched = merged["agc_repo_month_matched"].eq(1)
        base_commit = merged["latest_commit"].astype("string")
        agc_commit = merged["agc_latest_commit_internal"].astype("string")
        mismatch = matched & base_commit.notna() & agc_commit.notna() & base_commit.ne(agc_commit)
        if mismatch.any():
            sample = merged.loc[mismatch, KEY_COLS + ["latest_commit", "agc_latest_commit_internal"]].head(20)
            raise ValueError(
                f"Base latest_commit disagrees with AGC snapshot for {int(mismatch.sum())} rows.\n"
                f"Sample:\n{sample.to_string(index=False)}"
            )
        merged["latest_commit"] = base_commit.fillna(agc_commit)
        merged = merged.drop(columns=["agc_latest_commit_internal"])

    merged["agc_analysis_status"] = merged["agc_analysis_status"].fillna(
        "missing_agc_repo_month"
    )

    unmatched_base = merged.loc[
        merged["agc_repo_month_matched"] == 0,
        [column for column in OUTPUT_COLS if column in merged.columns],
    ].copy()

    merged = merged.drop(columns=["__agc_merge"])
    return merged, unmatched_base, detector_only


def coerce_output_types(df: pd.DataFrame) -> pd.DataFrame:
    """Apply stable numeric types and validate count/ratio invariants."""
    result = df.copy()
    for column in COUNT_COLS + ["python_file_count", "files_analyzed", "failure_count"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")

    for column in RATIO_COLS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        invalid = result[column].notna() & ~result[column].between(0, 1, inclusive="both")
        if invalid.any():
            raise ValueError(f"{column} contains {int(invalid.sum())} values outside [0, 1]")

    for column in COVARIATE_COLS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result["paper_covariate_matched"] = pd.to_numeric(
        result["paper_covariate_matched"], errors="coerce"
    ).fillna(0).astype("Int64")
    result["python_snapshot_ncloc_matched"] = pd.to_numeric(
        result["python_snapshot_ncloc_matched"], errors="coerce"
    ).fillna(0).astype("Int64")

    agc_ready = (
        result["agc_repo_month_matched"].eq(1)
        & result["agc_top_level_block_ratio"].notna()
    )
    shared_covariates_ready = result[["stars", "issues", "age"]].notna().all(axis=1)
    result["analysis_ready_agc_paper_ncloc"] = (
        agc_ready & shared_covariates_ready & result["ncloc_paper"].notna()
    ).astype("Int64")
    result["analysis_ready_agc_python_snapshot_ncloc"] = (
        agc_ready
        & shared_covariates_ready
        & result["ncloc_python_snapshot"].notna()
        & result["python_snapshot_ncloc_matched"].eq(1)
    ).astype("Int64")

    matched = result["agc_repo_month_matched"].eq(1)
    count_checks = {
        "top_level_total": (
            result["top_level_blocks_scored"],
            result["function_blocks_scored"] + result["class_blocks_scored"],
        ),
        "top_level_agc": (
            result["agc_top_level_blocks"],
            result["agc_function_blocks"] + result["agc_class_blocks"],
        ),
        "top_level_human": (
            result["human_top_level_blocks"],
            result["human_function_blocks"] + result["human_class_blocks"],
        ),
        "top_level_partition": (
            result["top_level_blocks_scored"],
            result["agc_top_level_blocks"] + result["human_top_level_blocks"],
        ),
        "function_partition": (
            result["function_blocks_scored"],
            result["agc_function_blocks"] + result["human_function_blocks"],
        ),
        "class_partition": (
            result["class_blocks_scored"],
            result["agc_class_blocks"] + result["human_class_blocks"],
        ),
    }
    for label, (left, right) in count_checks.items():
        mismatch = matched & left.ne(right)
        if mismatch.any():
            raise ValueError(f"Count invariant {label} failed for {int(mismatch.sum())} rows")

    return result


def build_match_summary(
    base: pd.DataFrame,
    merged: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize repository-month coverage by source."""
    rows: list[dict[str, Any]] = []
    for source in ["treatment", "control", "all"]:
        if source == "all":
            base_part = base
            merged_part = merged
            outcomes_part = outcomes
        else:
            base_part = base.loc[base["dataset_source"] == source]
            merged_part = merged.loc[merged["dataset_source"] == source]
            outcomes_part = outcomes.loc[outcomes["dataset_source"] == source]

        matched_rows = int(merged_part["agc_repo_month_matched"].sum())
        rows.append(
            {
                "dataset_source": source,
                "base_rows": len(base_part),
                "base_repositories": base_part["repo_name"].nunique(),
                "detector_repo_month_rows": len(outcomes_part),
                "matched_base_rows": matched_rows,
                "unmatched_base_rows": len(base_part) - matched_rows,
                "match_rate": matched_rows / len(base_part) if len(base_part) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_descriptive_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build outcome summaries by source and treatment period."""
    rows: list[dict[str, Any]] = []
    group_specs = [
        (["dataset_source"], "source"),
        (["dataset_source", "post_event"], "source_post"),
    ]
    for group_cols, group_type in group_specs:
        for group_values, group in df.groupby(group_cols, dropna=False):
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            labels = dict(zip(group_cols, group_values))
            for outcome in RATIO_COLS:
                values = pd.to_numeric(group[outcome], errors="coerce")
                nonmissing = values.dropna()
                rows.append(
                    {
                        "group_type": group_type,
                        "dataset_source": labels.get("dataset_source", "all"),
                        "post_event": labels.get("post_event", "all"),
                        "outcome": outcome,
                        "rows": len(group),
                        "nonmissing": len(nonmissing),
                        "mean": nonmissing.mean() if len(nonmissing) else np.nan,
                        "median": nonmissing.median() if len(nonmissing) else np.nan,
                        "std": nonmissing.std() if len(nonmissing) > 1 else np.nan,
                        "min": nonmissing.min() if len(nonmissing) else np.nan,
                        "max": nonmissing.max() if len(nonmissing) else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def build_qc_summary(
    panel_label: str,
    base: pd.DataFrame,
    merged: pd.DataFrame,
    outcomes: pd.DataFrame,
    unmatched_base: pd.DataFrame,
    detector_only: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact key-value QC summary."""
    rows: list[dict[str, Any]] = []

    def add(check: str, value: Any) -> None:
        rows.append({"check": check, "value": value})

    add("panel_label", panel_label)
    add("base_rows", len(base))
    add("output_rows", len(merged))
    add("row_count_preserved", int(len(base) == len(merged)))
    add("base_repositories", base["repo_name"].nunique())
    add("detector_repo_month_rows", len(outcomes))
    add("matched_base_rows", int(merged["agc_repo_month_matched"].sum()))
    add("unmatched_base_rows", len(unmatched_base))
    add("detector_only_rows", len(detector_only))
    add("duplicate_output_keys", int(merged.duplicated(KEY_COLS).sum()))
    add("min_time", merged["time"].min())
    add("max_time", merged["time"].max())
    add("treatment_rows", int((merged["dataset_source"] == "treatment").sum()))
    add("control_rows", int((merged["dataset_source"] == "control").sum()))
    add("agc_failure_count_sum", pd.to_numeric(merged["failure_count"], errors="coerce").fillna(0).sum())
    add("paper_covariate_matched_rows", int(pd.to_numeric(merged["paper_covariate_matched"], errors="coerce").fillna(0).sum()))
    add("python_snapshot_ncloc_matched_rows", int(pd.to_numeric(merged["python_snapshot_ncloc_matched"], errors="coerce").fillna(0).sum()))
    add("analysis_ready_agc_paper_ncloc_rows", int(pd.to_numeric(merged["analysis_ready_agc_paper_ncloc"], errors="coerce").fillna(0).sum()))
    add("analysis_ready_agc_python_snapshot_ncloc_rows", int(pd.to_numeric(merged["analysis_ready_agc_python_snapshot_ncloc"], errors="coerce").fillna(0).sum()))
    add("ncloc_paper_nonmissing", int(merged["ncloc_paper"].notna().sum()))
    add("ncloc_python_snapshot_nonmissing", int(merged["ncloc_python_snapshot"].notna().sum()))

    for outcome in RATIO_COLS:
        values = pd.to_numeric(merged[outcome], errors="coerce")
        add(f"{outcome}_nonmissing", int(values.notna().sum()))
        add(f"{outcome}_missing", int(values.isna().sum()))
        add(f"{outcome}_mean", values.mean())
        add(f"{outcome}_median", values.median())

    return pd.DataFrame(rows)


def main() -> int:
    """Run the AGC DiD input preparation pipeline."""
    setup_logging()
    args = parse_args()
    if args.chunksize <= 0:
        raise ValueError("--chunksize must be positive")

    input_paths = [
        args.base_panel,
        args.paper_panel,
        args.snapshot_manifest,
        args.block_treatment,
        args.block_control,
        args.repo_month_treatment,
        args.repo_month_control,
        args.run_metadata_treatment,
        args.run_metadata_control,
        args.combined_validation,
    ]
    for path in input_paths:
        require_file(path, "required input")
    if not args.snapshot_root.is_dir():
        raise FileNotFoundError(f"Python snapshot root not found: {args.snapshot_root}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.repo_commit_ncloc_output.parent.mkdir(parents=True, exist_ok=True)
    args.repo_month_outcomes_output.parent.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    # Fail fast on panel semantics and frozen-paper duplicate conflicts before
    # running expensive block aggregation or historical snapshot scans.
    logging.info("Loading and validating strict matched DiD panel")
    base = load_base_panel(args.base_panel)

    logging.info("Loading frozen-paper covariates")
    paper_lookup, paper_duplicate_summary, paper_conflicts = load_paper_covariates(
        args.paper_panel
    )
    atomic_write_csv(
        paper_duplicate_summary,
        args.qc_dir / "agc_paper_duplicate_key_summary.csv",
    )
    atomic_write_csv(
        paper_conflicts,
        args.qc_dir / "agc_paper_duplicate_key_conflicts.csv",
    )
    if not paper_conflicts.empty:
        raise ValueError(
            "Frozen paper panel has conflicting duplicate repository-month keys; "
            f"see {args.qc_dir / 'agc_paper_duplicate_key_conflicts.csv'}"
        )

    logging.info("Validating detector metadata")
    metadata_comparison = validate_detector_metadata(
        args.run_metadata_treatment,
        args.run_metadata_control,
        args.combined_validation,
    )

    logging.info("Loading repository-month snapshot manifest")
    manifest = load_snapshot_manifest(args.snapshot_manifest)

    empty_failures = pd.DataFrame(
        columns=[
            "dataset_source",
            "repo_name",
            "latest_commit",
            "relative_path",
            "error",
        ]
    )
    if args.reuse_repo_commit_ncloc and args.repo_commit_ncloc_output.is_file():
        commit_ncloc = load_reusable_repo_commit_ncloc(
            args.repo_commit_ncloc_output,
            manifest,
        )
        ncloc_failures = empty_failures
        ncloc_mode = "reused"
    else:
        if args.reuse_repo_commit_ncloc:
            logging.info(
                "Reusable Python snapshot NCLOC file does not exist; computing: %s",
                args.repo_commit_ncloc_output,
            )
        logging.info("Computing Python snapshot NCLOC from exported historical files")
        commit_ncloc, ncloc_failures = compute_python_snapshot_ncloc(
            manifest,
            args.snapshot_root,
        )
        ncloc_mode = "computed"
        atomic_write_csv(commit_ncloc, args.repo_commit_ncloc_output)

    month_ncloc = expand_snapshot_ncloc_to_month(manifest, commit_ncloc)
    snapshot_ncloc_summary = build_snapshot_ncloc_summary(
        commit_ncloc,
        month_ncloc,
    )
    snapshot_ncloc_summary["ncloc_mode"] = ncloc_mode
    atomic_write_csv(
        ncloc_failures,
        args.qc_dir / "agc_python_snapshot_ncloc_failures.csv",
    )
    atomic_write_csv(
        snapshot_ncloc_summary,
        args.qc_dir / "agc_python_snapshot_ncloc_summary.csv",
    )
    if not ncloc_failures.empty:
        raise ValueError(
            "Python snapshot NCLOC computation reported "
            f"{len(ncloc_failures)} failures; see "
            f"{args.qc_dir / 'agc_python_snapshot_ncloc_failures.csv'}"
        )

    logging.info("Aggregating treatment block predictions")
    treatment_blocks = aggregate_block_file(
        args.block_treatment, "treatment", args.chunksize
    )
    logging.info("Aggregating control block predictions")
    control_blocks = aggregate_block_file(
        args.block_control, "control", args.chunksize
    )
    block_aggregates = pd.concat(
        [treatment_blocks, control_blocks], ignore_index=True
    )
    commit_wide = make_commit_wide(block_aggregates)
    require_unique(commit_wide, COMMIT_KEY_COLS, "commit-level block outcomes")

    reconstructed = expand_commit_outcomes_to_month(manifest, commit_wide)

    logging.info("Loading existing repository-month AGC outputs")
    oracle = load_repo_month_oracle(
        args.repo_month_treatment,
        args.repo_month_control,
    )
    compared, aggregation_qc = compare_reconstructed_with_oracle(
        reconstructed,
        oracle,
    )
    outcomes = prepare_outcome_columns(compared)
    outcomes = merge_snapshot_ncloc_into_outcomes(outcomes, month_ncloc)
    require_unique(outcomes, KEY_COLS, "AGC outcomes with snapshot NCLOC")

    base_with_covariates, unmatched_paper, paper_match_summary, paper_missingness = (
        merge_paper_covariates(base, paper_lookup)
    )

    merged, unmatched_base, detector_only = merge_base_panel(
        base_with_covariates,
        outcomes,
    )
    merged = coerce_output_types(merged)
    require_unique(merged, KEY_COLS, "final AGC DiD panel")

    missing_output_columns = sorted(set(OUTPUT_COLS) - set(merged.columns))
    if missing_output_columns:
        raise ValueError(
            f"Final panel is missing required output columns: {missing_output_columns}"
        )
    final_output = merged[OUTPUT_COLS].copy()

    unmatched_snapshot_ncloc = final_output.loc[
        final_output["python_snapshot_ncloc_matched"].fillna(0).eq(0),
        KEY_COLS
        + [
            "latest_commit",
            "python_file_count",
            "ncloc_python_snapshot",
            "agc_repo_month_matched",
        ],
    ].copy()

    match_summary = build_match_summary(base, merged, outcomes)
    descriptive_summary = build_descriptive_summary(final_output)
    qc_summary = build_qc_summary(
        args.panel_label,
        base,
        merged,
        outcomes,
        unmatched_base,
        detector_only,
    )
    ncloc_comparison = build_ncloc_comparison_summary(final_output)
    column_manifest = pd.DataFrame(
        {
            "column_order": range(1, len(OUTPUT_COLS) + 1),
            "column": OUTPUT_COLS,
        }
    )

    output_paths = {
        "main": args.output,
        "repo_month_outcomes": args.repo_month_outcomes_output,
        "qc": args.qc_dir / "agc_did_input_qc.csv",
        "match_summary": args.qc_dir / "agc_repo_month_match_summary.csv",
        "unmatched_base": args.qc_dir / "agc_unmatched_base_repo_months.csv",
        "detector_only": args.qc_dir / "agc_unmatched_detector_repo_months.csv",
        "metadata": args.qc_dir / "agc_detector_metadata_comparison.csv",
        "descriptive": args.qc_dir / "agc_outcome_descriptive_summary.csv",
        "aggregation_qc": args.qc_dir / "agc_block_kind_aggregation_qc.csv",
        "aggregation_mismatches": args.qc_dir / "agc_block_kind_aggregation_mismatches.csv",
        "column_manifest": args.qc_dir / "agc_output_column_manifest.csv",
        "paper_match": args.qc_dir / "agc_paper_covariate_match_summary.csv",
        "paper_unmatched": args.qc_dir / "agc_unmatched_paper_covariate_repo_months.csv",
        "paper_missingness": args.qc_dir / "agc_paper_covariate_missingness.csv",
        "snapshot_ncloc_unmatched": args.qc_dir / "agc_unmatched_python_snapshot_ncloc_rows.csv",
        "ncloc_comparison": args.qc_dir / "agc_ncloc_comparison_summary.csv",
    }

    atomic_write_csv(final_output, output_paths["main"])
    atomic_write_csv(outcomes, output_paths["repo_month_outcomes"])
    atomic_write_csv(qc_summary, output_paths["qc"])
    atomic_write_csv(match_summary, output_paths["match_summary"])
    atomic_write_csv(unmatched_base, output_paths["unmatched_base"])
    atomic_write_csv(detector_only, output_paths["detector_only"])
    atomic_write_csv(metadata_comparison, output_paths["metadata"])
    atomic_write_csv(descriptive_summary, output_paths["descriptive"])
    atomic_write_csv(aggregation_qc, output_paths["aggregation_qc"])
    atomic_write_csv(
        compared.loc[~compared["all_checks_pass"]],
        output_paths["aggregation_mismatches"],
    )
    atomic_write_csv(column_manifest, output_paths["column_manifest"])
    atomic_write_csv(paper_match_summary, output_paths["paper_match"])
    atomic_write_csv(unmatched_paper, output_paths["paper_unmatched"])
    atomic_write_csv(paper_missingness, output_paths["paper_missingness"])
    atomic_write_csv(unmatched_snapshot_ncloc, output_paths["snapshot_ncloc_unmatched"])
    atomic_write_csv(ncloc_comparison, output_paths["ncloc_comparison"])

    logging.info("Saved AGC DiD panel: %s", args.output)
    logging.info(
        "Saved repository-commit snapshot NCLOC: %s (%s)",
        args.repo_commit_ncloc_output,
        ncloc_mode,
    )
    logging.info(
        "Saved repository-month AGC outcomes: %s",
        args.repo_month_outcomes_output,
    )
    logging.info("Saved QC directory: %s", args.qc_dir)
    print()
    print("QC summary:")
    print(qc_summary.to_string(index=False))
    print()
    print("Repository-month match summary:")
    print(match_summary.to_string(index=False))
    print()
    print("Paper covariate match summary:")
    print(paper_match_summary.to_string(index=False))
    print()
    print("Python snapshot NCLOC summary:")
    print(snapshot_ncloc_summary.to_string(index=False))
    print()
    print("Completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
