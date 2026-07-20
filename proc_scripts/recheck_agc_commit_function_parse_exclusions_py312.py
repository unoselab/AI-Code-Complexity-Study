#!/usr/bin/env python3
"""Recheck Python 3.11 parse exclusions with Python 3.12 or newer.

This diagnostic reads the parse-exclusion records produced by the commit-function
extractor, resolves the exact historical Git blob that failed, and parses each
unique blob with the currently running Python interpreter. It does not modify
run-py-5a outputs or regenerate function-event artifacts.

Run this script with Python 3.12 or newer because the primary purpose is to
measure recovery from pre-PEP 701 parser limitations.
"""

from __future__ import annotations

import argparse
import ast
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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

import pandas as pd


ALLOWED_STAGES = {"current_file_parse", "parent_file_parse"}
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
PANEL_KEY = ["dataset_source", "repo_name", "time"]
BLOB_KEY = ["dataset_source", "repo_name", "blob_commit", "blob_relative_path"]

ERROR_REQUIRED = {
    "dataset_source",
    "repo_name",
    "time",
    "commit",
    "parent_commit",
    "relative_path",
    "stage",
    "error",
}
PANEL_REQUIRED = {"dataset_source", "repo_name", "time", "time_to_event"}


@dataclass(frozen=True)
class ChangedPath:
    status: str
    old_path: str
    new_path: str


@dataclass
class DiagnosticResult:
    unique_blobs: pd.DataFrame
    records: pd.DataFrame
    by_dataset_source: pd.DataFrame
    by_treatment_period: pd.DataFrame
    by_event_time: pd.DataFrame
    by_repository: pd.DataFrame
    by_py311_error: pd.DataFrame
    checks: pd.DataFrame
    summary: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reparse historical Python blobs excluded by run-py-5a using "
            "Python 3.12 or newer."
        )
    )
    parser.add_argument(
        "--errors",
        default=(
            "repo_python/tmp/run-py-5a/strict/"
            "agc_commit_function_event_extract_errors.csv"
        ),
        help="Input parse-exclusion CSV from run-py-5a.",
    )
    parser.add_argument(
        "--panel",
        default=(
            "repo_python/run-py-4a/strict/"
            "panel_event_monthly_agc_changed_block_py.csv"
        ),
        help="Input repository-month panel containing time_to_event.",
    )
    parser.add_argument(
        "--treatment-clone-dir",
        default="../treatment-repos",
        help="Root directory containing treatment Git clones.",
    )
    parser.add_argument(
        "--control-clone-dir",
        default="../control-repos",
        help="Root directory containing control Git clones.",
    )
    parser.add_argument(
        "--output-dir",
        default="repo_python/run-py-5c/strict",
        help="Directory for Python 3.12 recheck CSV outputs.",
    )
    parser.add_argument(
        "--qc-dir",
        default="repo_python/tmp/run-py-5c/strict",
        help="Directory for summary and check outputs.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print progress after this many unique blobs; use 0 to disable.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a synthetic Git/path/parser regression test and exit.",
    )
    return parser.parse_args()


def require_python_312() -> None:
    if sys.version_info < (3, 12):
        raise RuntimeError(
            "Python 3.12 or newer is required. "
            f"Current interpreter: {sys.version.split()[0]}"
        )


def resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def normalize_text_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = result[column].fillna("").astype(str).str.strip()
    return result


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def valid_sha(value: str) -> bool:
    return bool(FULL_SHA_RE.fullmatch(value.strip()))


def decode_git_path(raw: bytes) -> str:
    return raw.decode("utf-8", errors="surrogateescape")


def run_git_bytes(repo_dir: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
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
    return parse_name_status_z(
        require_git_bytes(run_git_bytes(repo_dir, args), "git diff-tree failed")
    )


def git_blob_exists(repo_dir: Path, commit: str, relative_path: str) -> bool:
    if not valid_sha(commit) or not relative_path:
        return False
    result = run_git_bytes(repo_dir, ["cat-file", "-e", f"{commit}:{relative_path}"])
    return result.returncode == 0


def git_blob(repo_dir: Path, commit: str, relative_path: str) -> bytes:
    if not valid_sha(commit):
        raise ValueError(f"Invalid blob commit SHA: {commit}")
    if not relative_path:
        raise ValueError("Empty blob path")
    result = run_git_bytes(repo_dir, ["show", f"{commit}:{relative_path}"])
    return require_git_bytes(result, f"Cannot read {commit}:{relative_path}")


def decode_python_source(payload: bytes) -> tuple[str, str]:
    reader = io.BytesIO(payload).readline
    encoding, _ = tokenize.detect_encoding(reader)
    return payload.decode(encoding), encoding


def error_type(error_text: str) -> str:
    return error_text.split(":", 1)[0].strip() if error_text else ""


def py311_error_signature(error_text: str) -> str:
    if not error_text:
        return ""
    return re.sub(r"\s*\([^()]*, line \d+\)\s*$", "", error_text).strip()


def treatment_period(dataset_source: str, time_to_event: Any) -> str:
    if dataset_source != "treatment":
        return "control"
    if pd.isna(time_to_event):
        return "treatment_unknown_event_time"
    value = float(time_to_event)
    if value < 0:
        return "treatment_pre_event"
    if value == 0:
        return "treatment_event_month"
    return "treatment_post_event"


def resolve_repo_dir(
    dataset_source: str,
    repo_name: str,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> Path:
    root = treatment_clone_dir if dataset_source == "treatment" else control_clone_dir
    return (root / repo_slug(repo_name)).resolve()


def resolve_failed_blob_path(
    row: Any,
    repo_dir: Path,
    changed_path_cache: dict[tuple[str, str], list[ChangedPath]],
) -> tuple[str, str, str]:
    """Return blob commit, exact blob path, and the path-resolution method."""

    stage = str(row.stage)
    current = str(row.commit)
    parent = str(row.parent_commit)
    current_path = str(row.relative_path)

    if stage == "current_file_parse":
        return current, current_path, "current_path"

    if stage != "parent_file_parse":
        raise ValueError(f"Unsupported parse-exclusion stage: {stage}")

    cache_key = (parent, current)
    if cache_key not in changed_path_cache:
        changed_path_cache[cache_key] = list_changed_paths(repo_dir, parent, current)

    matches = [
        changed
        for changed in changed_path_cache[cache_key]
        if changed.new_path == current_path
    ]
    if len(matches) == 1 and matches[0].old_path:
        return parent, matches[0].old_path, "git_diff_old_path"
    if len(matches) > 1:
        raise ValueError(
            "Multiple Git diff entries matched the current path for a parent parse error: "
            f"{current_path}"
        )

    # The extractor records the current path in its error table. For an ordinary
    # modification, the parent path is identical. This fallback is safe only
    # when the blob is verified to exist in the parent commit.
    if git_blob_exists(repo_dir, parent, current_path):
        return parent, current_path, "verified_same_path_fallback"

    raise FileNotFoundError(
        "Could not resolve the parent blob path from Git diff metadata: "
        f"parent={parent} current={current} current_path={current_path}"
    )


def load_inputs(errors_path: Path, panel_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    errors = pd.read_csv(errors_path, low_memory=False)
    panel = pd.read_csv(panel_path, low_memory=False)
    require_columns(errors, ERROR_REQUIRED, "Extraction errors")
    require_columns(panel, PANEL_REQUIRED, "Panel")

    errors = normalize_text_columns(
        errors,
        [
            "dataset_source",
            "repo_name",
            "time",
            "commit",
            "parent_commit",
            "relative_path",
            "stage",
            "error",
        ],
    )
    panel = normalize_text_columns(panel, ["dataset_source", "repo_name", "time"])
    panel["time_to_event"] = pd.to_numeric(panel["time_to_event"], errors="coerce")

    if panel.duplicated(PANEL_KEY).any():
        duplicates = panel.loc[panel.duplicated(PANEL_KEY, keep=False), PANEL_KEY]
        raise ValueError(
            "Panel key is not unique. Example duplicates: "
            f"{duplicates.head(10).to_dict(orient='records')}"
        )

    return errors, panel


def build_resolved_records(
    errors: pd.DataFrame,
    panel: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    panel_map = panel[PANEL_KEY + ["time_to_event"]].copy()
    records = errors.reset_index(drop=True).copy()
    records.insert(0, "error_record_id", range(len(records)))
    records = records.merge(panel_map, on=PANEL_KEY, how="left", validate="many_to_one")
    records["treatment_period"] = [
        treatment_period(source, value)
        for source, value in zip(
            records["dataset_source"], records["time_to_event"], strict=True
        )
    ]
    records["py311_error_type"] = records["error"].map(error_type)
    records["py311_error_signature"] = records["error"].map(py311_error_signature)
    records["py311_fstring_error"] = (
        records["error"].str.contains("f-string", case=False, na=False).astype(int)
    )

    resolved_rows: list[dict[str, Any]] = []
    resolution_errors: list[dict[str, Any]] = []
    changed_path_cache_by_repo: dict[tuple[str, str], dict[tuple[str, str], list[ChangedPath]]] = {}

    for row in records.itertuples(index=False):
        repo_dir = resolve_repo_dir(
            str(row.dataset_source),
            str(row.repo_name),
            treatment_clone_dir,
            control_clone_dir,
        )
        repo_cache_key = (str(row.dataset_source), str(row.repo_name))
        pair_cache = changed_path_cache_by_repo.setdefault(repo_cache_key, {})

        try:
            if not (repo_dir / ".git").exists():
                raise FileNotFoundError(f"Missing Git clone: {repo_dir}")
            blob_commit, blob_path, resolution_method = resolve_failed_blob_path(
                row, repo_dir, pair_cache
            )
            resolved_rows.append(
                {
                    "error_record_id": int(row.error_record_id),
                    "repo_dir": str(repo_dir),
                    "blob_commit": blob_commit,
                    "blob_relative_path": blob_path,
                    "path_resolution_method": resolution_method,
                }
            )
        except Exception as exc:
            resolution_errors.append(
                {
                    "error_record_id": int(row.error_record_id),
                    "dataset_source": str(row.dataset_source),
                    "repo_name": str(row.repo_name),
                    "time": str(row.time),
                    "commit": str(row.commit),
                    "parent_commit": str(row.parent_commit),
                    "relative_path": str(row.relative_path),
                    "stage": str(row.stage),
                    "resolution_error": f"{type(exc).__name__}: {exc}",
                }
            )

    resolved = pd.DataFrame(resolved_rows)
    if not resolved.empty:
        records = records.merge(
            resolved,
            on="error_record_id",
            how="left",
            validate="one_to_one",
        )
    else:
        for column in [
            "repo_dir",
            "blob_commit",
            "blob_relative_path",
            "path_resolution_method",
        ]:
            records[column] = ""

    return records, resolution_errors


def build_unique_blob_targets(records: pd.DataFrame) -> pd.DataFrame:
    if records[BLOB_KEY].isna().any().any() or (
        records[BLOB_KEY].astype(str).apply(lambda column: column.str.len().eq(0)).any().any()
    ):
        raise ValueError("One or more error records do not have a resolved blob key")

    rows: list[dict[str, Any]] = []
    for key, group in records.groupby(BLOB_KEY, sort=True, dropna=False):
        dataset_source, repo_name, blob_commit, blob_path = key
        rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "blob_commit": blob_commit,
                "blob_relative_path": blob_path,
                "repo_dir": group["repo_dir"].iloc[0],
                "error_record_count": int(len(group)),
                "current_error_record_count": int(
                    group["stage"].eq("current_file_parse").sum()
                ),
                "parent_error_record_count": int(
                    group["stage"].eq("parent_file_parse").sum()
                ),
                "first_observed_time": str(group["time"].min()),
                "last_observed_time": str(group["time"].max()),
                "observed_treatment_periods": ";".join(
                    sorted(set(group["treatment_period"].astype(str)))
                ),
                "py311_error_types": ";".join(
                    sorted(set(group["py311_error_type"].astype(str)))
                ),
                "py311_error_signatures": " || ".join(
                    sorted(set(group["py311_error_signature"].astype(str)))
                ),
                "py311_fstring_error": int(group["py311_fstring_error"].max()),
            }
        )
    return pd.DataFrame(rows)


def parse_unique_blobs(
    targets: pd.DataFrame,
    progress_every: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    parsed_rows: list[dict[str, Any]] = []
    processing_errors: list[dict[str, Any]] = []
    total = len(targets)

    for index, row in enumerate(targets.itertuples(index=False), start=1):
        repo_dir = Path(str(row.repo_dir))
        base = row._asdict()
        try:
            payload = git_blob(
                repo_dir,
                str(row.blob_commit),
                str(row.blob_relative_path),
            )
            source, encoding = decode_python_source(payload)
            content_hash = hashlib.sha256(payload).hexdigest()
            try:
                ast.parse(
                    source,
                    filename=f"{row.blob_commit}:{row.blob_relative_path}",
                    type_comments=True,
                )
                parse_success = 1
                py312_error_type = ""
                py312_error = ""
            except SyntaxError as exc:
                parse_success = 0
                py312_error_type = type(exc).__name__
                py312_error = f"{type(exc).__name__}: {exc}"

            parsed_rows.append(
                {
                    **base,
                    "source_bytes": int(len(payload)),
                    "source_encoding": encoding,
                    "content_sha256": content_hash,
                    "py312_parse_success": parse_success,
                    "py312_recovered": parse_success,
                    "py312_error_type": py312_error_type,
                    "py312_error": py312_error,
                }
            )
        except Exception as exc:
            processing_errors.append(
                {
                    "dataset_source": str(row.dataset_source),
                    "repo_name": str(row.repo_name),
                    "blob_commit": str(row.blob_commit),
                    "blob_relative_path": str(row.blob_relative_path),
                    "processing_error": f"{type(exc).__name__}: {exc}",
                }
            )

        if progress_every > 0 and (index % progress_every == 0 or index == total):
            recovered = sum(int(item["py312_recovered"]) for item in parsed_rows)
            print(
                "Python 3.12 blob recheck: "
                f"{index}/{total}; recovered={recovered}; "
                f"processing_errors={len(processing_errors)}",
                flush=True,
            )

    return pd.DataFrame(parsed_rows), processing_errors


def enrich_records_with_recheck(
    records: pd.DataFrame,
    unique_blobs: pd.DataFrame,
) -> pd.DataFrame:
    selected = unique_blobs[
        BLOB_KEY
        + [
            "content_sha256",
            "source_bytes",
            "source_encoding",
            "py312_parse_success",
            "py312_recovered",
            "py312_error_type",
            "py312_error",
        ]
    ].copy()
    return records.merge(selected, on=BLOB_KEY, how="left", validate="many_to_one")


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def aggregate_recovery(frame: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped: Iterable[tuple[Any, pd.DataFrame]]
    if group_columns:
        grouped = frame.groupby(group_columns, sort=True, dropna=False)
    else:
        grouped = [((), frame)]

    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        record: dict[str, Any] = {
            column: value for column, value in zip(group_columns, key, strict=True)
        }
        error_records = int(len(group))
        recovered_records = int(group["py312_recovered"].sum())
        unique_blobs = int(group[BLOB_KEY].drop_duplicates().shape[0])
        recovered_unique = int(
            group.loc[group["py312_recovered"].eq(1), BLOB_KEY]
            .drop_duplicates()
            .shape[0]
        )
        fstring_records = int(group["py311_fstring_error"].sum())
        fstring_recovered = int(
            group.loc[group["py311_fstring_error"].eq(1), "py312_recovered"].sum()
        )
        record.update(
            {
                "error_records": error_records,
                "recovered_error_records": recovered_records,
                "remaining_error_records": error_records - recovered_records,
                "record_recovery_rate": safe_ratio(recovered_records, error_records),
                "unique_blob_revisions": unique_blobs,
                "recovered_unique_blob_revisions": recovered_unique,
                "remaining_unique_blob_revisions": unique_blobs - recovered_unique,
                "unique_blob_recovery_rate": safe_ratio(recovered_unique, unique_blobs),
                "py311_fstring_error_records": fstring_records,
                "py311_fstring_recovered_records": fstring_recovered,
                "py311_fstring_record_recovery_rate": safe_ratio(
                    fstring_recovered, fstring_records
                ),
            }
        )
        rows.append(record)
    return pd.DataFrame(rows)


def make_check(section: str, check: str, passed: bool, value: Any) -> dict[str, Any]:
    return {
        "section": section,
        "check": check,
        "passed": int(bool(passed)),
        "value": value,
    }


def build_checks(
    errors: pd.DataFrame,
    panel: pd.DataFrame,
    records: pd.DataFrame,
    unique_blobs: pd.DataFrame,
    resolution_errors: list[dict[str, Any]],
    processing_errors: list[dict[str, Any]],
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []
    checks.append(
        make_check(
            "environment",
            "python_version_at_least_3_12",
            sys.version_info >= (3, 12),
            sys.version.split()[0],
        )
    )
    unexpected_stages = int((~errors["stage"].isin(ALLOWED_STAGES)).sum())
    checks.append(
        make_check(
            "input",
            "unexpected_error_stages_zero",
            unexpected_stages == 0,
            unexpected_stages,
        )
    )
    checks.append(
        make_check(
            "input",
            "panel_keys_unique",
            not panel.duplicated(PANEL_KEY).any(),
            int(panel.duplicated(PANEL_KEY).sum()),
        )
    )
    missing_panel = int(records["time_to_event"].isna().sum())
    control_missing = int(
        records.loc[
            records["dataset_source"].eq("control"), "time_to_event"
        ].isna().sum()
    )
    treatment_missing = int(
        records.loc[
            records["dataset_source"].eq("treatment"), "time_to_event"
        ].isna().sum()
    )
    checks.append(
        make_check(
            "input",
            "treatment_panel_matches_complete",
            treatment_missing == 0,
            treatment_missing,
        )
    )
    # Control time_to_event may be missing depending on the matched-panel schema.
    checks.append(
        make_check(
            "input",
            "panel_merge_row_count_preserved",
            len(records) == len(errors),
            f"{len(records)}:{len(errors)};all_missing={missing_panel};control_missing={control_missing}",
        )
    )
    checks.append(
        make_check(
            "resolution",
            "blob_path_resolution_errors_zero",
            len(resolution_errors) == 0,
            len(resolution_errors),
        )
    )
    checks.append(
        make_check(
            "resolution",
            "all_error_records_have_blob_keys",
            len(records) == len(errors)
            and records[BLOB_KEY].notna().all().all()
            and not records[BLOB_KEY]
            .astype(str)
            .apply(lambda column: column.str.len().eq(0))
            .any()
            .any(),
            f"records={len(records)} errors={len(errors)}",
        )
    )
    checks.append(
        make_check(
            "processing",
            "blob_processing_errors_zero",
            len(processing_errors) == 0,
            len(processing_errors),
        )
    )
    checks.append(
        make_check(
            "processing",
            "unique_blob_keys_unique",
            not unique_blobs.duplicated(BLOB_KEY).any(),
            int(unique_blobs.duplicated(BLOB_KEY).sum()),
        )
    )
    expected_unique = int(records[BLOB_KEY].drop_duplicates().shape[0])
    checks.append(
        make_check(
            "processing",
            "all_unique_blobs_rechecked",
            len(unique_blobs) == expected_unique,
            f"{len(unique_blobs)}:{expected_unique}",
        )
    )
    missing_recheck = int(records["py312_parse_success"].isna().sum())
    checks.append(
        make_check(
            "coverage",
            "all_error_records_mapped_to_recheck",
            missing_recheck == 0,
            missing_recheck,
        )
    )
    recovered_records = int(records["py312_recovered"].fillna(0).sum())
    remaining_records = int(len(records) - recovered_records)
    checks.append(
        make_check(
            "arithmetic",
            "record_recovery_partition_matches_input",
            recovered_records + remaining_records == len(errors),
            f"{recovered_records}+{remaining_records}:{len(errors)}",
        )
    )
    recovered_unique = int(unique_blobs["py312_recovered"].sum())
    remaining_unique = int(len(unique_blobs) - recovered_unique)
    checks.append(
        make_check(
            "arithmetic",
            "unique_recovery_partition_matches_targets",
            recovered_unique + remaining_unique == len(unique_blobs),
            f"{recovered_unique}+{remaining_unique}:{len(unique_blobs)}",
        )
    )
    source_counts = records.groupby("dataset_source").size().sum()
    checks.append(
        make_check(
            "arithmetic",
            "dataset_source_partition_matches_input",
            int(source_counts) == len(errors),
            f"{int(source_counts)}:{len(errors)}",
        )
    )
    return pd.DataFrame(checks)


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    frame.to_csv(temp, index=False)
    os.replace(temp, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temp, path)


def analyze(
    errors_path: Path,
    panel_path: Path,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    progress_every: int,
) -> tuple[DiagnosticResult, list[dict[str, Any]], list[dict[str, Any]]]:
    errors, panel = load_inputs(errors_path, panel_path)
    records, resolution_errors = build_resolved_records(
        errors,
        panel,
        treatment_clone_dir,
        control_clone_dir,
    )

    unexpected_stages = errors.loc[~errors["stage"].isin(ALLOWED_STAGES)]
    if not unexpected_stages.empty:
        raise ValueError(
            "Input contains unsupported error stages: "
            f"{unexpected_stages['stage'].value_counts().to_dict()}"
        )
    if resolution_errors:
        unique_blobs = pd.DataFrame()
        processing_errors: list[dict[str, Any]] = []
    else:
        targets = build_unique_blob_targets(records)
        unique_blobs, processing_errors = parse_unique_blobs(targets, progress_every)

    if not processing_errors and not unique_blobs.empty:
        records = enrich_records_with_recheck(records, unique_blobs)
    else:
        for column in [
            "content_sha256",
            "source_bytes",
            "source_encoding",
            "py312_parse_success",
            "py312_recovered",
            "py312_error_type",
            "py312_error",
        ]:
            records[column] = pd.NA

    checks = build_checks(
        errors,
        panel,
        records,
        unique_blobs,
        resolution_errors,
        processing_errors,
    )

    by_dataset_source = aggregate_recovery(records, ["dataset_source"])
    by_treatment_period = aggregate_recovery(records, ["treatment_period"])
    by_event_time = aggregate_recovery(
        records.loc[records["dataset_source"].eq("treatment")].copy(),
        ["time_to_event"],
    )
    by_repository = aggregate_recovery(records, ["dataset_source", "repo_name"])
    by_py311_error = aggregate_recovery(
        records,
        ["py311_error_type", "py311_error_signature", "py311_fstring_error"],
    )

    failed_checks = int((checks["passed"] != 1).sum())
    recovered_unique = int(unique_blobs["py312_recovered"].sum()) if not unique_blobs.empty else 0
    remaining_unique = int(len(unique_blobs) - recovered_unique)
    recovered_records = int(records["py312_recovered"].fillna(0).sum())
    fstring_records = int(records["py311_fstring_error"].sum())
    fstring_recovered_records = int(
        records.loc[records["py311_fstring_error"].eq(1), "py312_recovered"]
        .fillna(0)
        .sum()
    )

    status = "PASS" if failed_checks == 0 else "FAIL"
    if status == "FAIL":
        recommendation = "FIX_RECHECK_PIPELINE_BEFORE_INTERPRETATION"
    elif recovered_unique > 0:
        recommendation = "REEXTRACT_FULL_RUN_PY_5A_WITH_PYTHON_3_12"
    else:
        recommendation = "KEEP_PYTHON_3_11_EXTRACTION_WITH_AUDITED_EXCLUSIONS"

    summary: dict[str, Any] = {
        "status": status,
        "recommendation": recommendation,
        "python_version": sys.version.split()[0],
        "python_implementation": sys.implementation.name,
        "checks_total": int(len(checks)),
        "checks_passed": int((checks["passed"] == 1).sum()),
        "checks_failed": failed_checks,
        "input_error_records": int(len(errors)),
        "input_fstring_error_records": fstring_records,
        "resolved_unique_blob_revisions": int(len(unique_blobs)),
        "recovered_error_records": recovered_records,
        "remaining_error_records": int(len(records) - recovered_records),
        "error_record_recovery_rate": safe_ratio(recovered_records, len(records)),
        "recovered_unique_blob_revisions": recovered_unique,
        "remaining_unique_blob_revisions": remaining_unique,
        "unique_blob_recovery_rate": safe_ratio(recovered_unique, len(unique_blobs)),
        "fstring_recovered_error_records": fstring_recovered_records,
        "fstring_remaining_error_records": fstring_records - fstring_recovered_records,
        "fstring_error_record_recovery_rate": safe_ratio(
            fstring_recovered_records, fstring_records
        ),
        "path_resolution_errors": int(len(resolution_errors)),
        "blob_processing_errors": int(len(processing_errors)),
        "interpretation": (
            "A recovered blob failed under the original Python 3.11 extractor but "
            "parses under the current Python 3.12+ interpreter. Remaining blobs "
            "still fail under the newer parser and require audited exclusion or "
            "separate source-level investigation."
        ),
    }

    result = DiagnosticResult(
        unique_blobs=unique_blobs,
        records=records,
        by_dataset_source=by_dataset_source,
        by_treatment_period=by_treatment_period,
        by_event_time=by_event_time,
        by_repository=by_repository,
        by_py311_error=by_py311_error,
        checks=checks,
        summary=summary,
    )
    return result, resolution_errors, processing_errors


def write_outputs(
    result: DiagnosticResult,
    resolution_errors: list[dict[str, Any]],
    processing_errors: list[dict[str, Any]],
    output_dir: Path,
    qc_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "unique_blobs": output_dir / "py312_parse_recheck_unique_blobs.csv",
        "records": output_dir / "py312_parse_recheck_error_records.csv",
        "recovered": output_dir / "py312_recovered_parse_exclusions.csv",
        "remaining": output_dir / "py312_remaining_parse_exclusions.csv",
        "by_dataset_source": output_dir / "py312_parse_recovery_by_dataset_source.csv",
        "by_treatment_period": output_dir / "py312_parse_recovery_by_treatment_period.csv",
        "by_event_time": output_dir / "py312_parse_recovery_by_event_time.csv",
        "by_repository": output_dir / "py312_parse_recovery_by_repository.csv",
        "by_py311_error": output_dir / "py312_parse_recovery_by_py311_error.csv",
        "resolution_errors": qc_dir / "py312_parse_recheck_resolution_errors.csv",
        "processing_errors": qc_dir / "py312_parse_recheck_processing_errors.csv",
        "checks": qc_dir / "py312_parse_recheck_checks.csv",
        "summary": qc_dir / "py312_parse_recheck_summary.json",
    }

    atomic_write_csv(result.unique_blobs, paths["unique_blobs"])
    atomic_write_csv(result.records, paths["records"])
    atomic_write_csv(
        result.unique_blobs.loc[result.unique_blobs["py312_recovered"].eq(1)].copy(),
        paths["recovered"],
    )
    atomic_write_csv(
        result.unique_blobs.loc[result.unique_blobs["py312_recovered"].eq(0)].copy(),
        paths["remaining"],
    )
    atomic_write_csv(result.by_dataset_source, paths["by_dataset_source"])
    atomic_write_csv(result.by_treatment_period, paths["by_treatment_period"])
    atomic_write_csv(result.by_event_time, paths["by_event_time"])
    atomic_write_csv(result.by_repository, paths["by_repository"])
    atomic_write_csv(result.by_py311_error, paths["by_py311_error"])
    atomic_write_csv(pd.DataFrame(resolution_errors), paths["resolution_errors"])
    atomic_write_csv(pd.DataFrame(processing_errors), paths["processing_errors"])
    atomic_write_csv(result.checks, paths["checks"])

    summary = dict(result.summary)
    summary["outputs"] = {name: str(path) for name, path in paths.items()}
    atomic_write_json(summary, paths["summary"])
    result.summary.clear()
    result.summary.update(summary)
    return {name: str(path) for name, path in paths.items()}


def git_run(repo_dir: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def run_self_test() -> None:
    require_python_312()
    with tempfile.TemporaryDirectory(prefix="py312-parse-recheck-") as temp_text:
        root = Path(temp_text)
        treatment_root = root / "treatment-repos"
        control_root = root / "control-repos"
        repo_dir = treatment_root / "owner_repo"
        repo_dir.mkdir(parents=True)
        control_root.mkdir(parents=True)

        git_run(repo_dir, "init", "-q")
        git_run(repo_dir, "config", "user.email", "test@example.com")
        git_run(repo_dir, "config", "user.name", "Test User")

        parent_source = (
            "def join_items(items):\n"
            "    return f\"{'\\n'.join(items)}\"\n"
        )
        old_path = repo_dir / "old_name.py"
        old_path.write_text(parent_source, encoding="utf-8")
        git_run(repo_dir, "add", "old_name.py")
        git_run(repo_dir, "commit", "-q", "-m", "parent")
        parent_commit = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True
        ).strip()

        new_path = repo_dir / "new_name.py"
        old_path.rename(new_path)
        new_path.write_text(parent_source + "\ndef broken(:\n", encoding="utf-8")
        git_run(repo_dir, "add", "-A")
        git_run(repo_dir, "commit", "-q", "-m", "current")
        current_commit = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True
        ).strip()

        errors = pd.DataFrame(
            [
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "time": "2025-01",
                    "commit": current_commit,
                    "parent_commit": parent_commit,
                    "relative_path": "new_name.py",
                    "stage": "parent_file_parse",
                    "error": "SyntaxError: f-string expression part cannot include a backslash",
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "time": "2025-01",
                    "commit": current_commit,
                    "parent_commit": parent_commit,
                    "relative_path": "new_name.py",
                    "stage": "current_file_parse",
                    "error": "SyntaxError: invalid syntax",
                },
            ]
        )
        panel = pd.DataFrame(
            [
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "time": "2025-01",
                    "time_to_event": 0,
                }
            ]
        )
        errors_path = root / "errors.csv"
        panel_path = root / "panel.csv"
        errors.to_csv(errors_path, index=False)
        panel.to_csv(panel_path, index=False)

        result, resolution_errors, processing_errors = analyze(
            errors_path,
            panel_path,
            treatment_root,
            control_root,
            progress_every=0,
        )
        if resolution_errors or processing_errors:
            raise AssertionError(
                f"Unexpected self-test errors: {resolution_errors} {processing_errors}"
            )
        if result.summary["checks_failed"] != 0:
            raise AssertionError(result.checks.to_string(index=False))
        if len(result.unique_blobs) != 2:
            raise AssertionError("Expected two unique blob revisions")
        recovered = result.unique_blobs.loc[
            result.unique_blobs["py312_recovered"].eq(1)
        ]
        remaining = result.unique_blobs.loc[
            result.unique_blobs["py312_recovered"].eq(0)
        ]
        if len(recovered) != 1 or len(remaining) != 1:
            raise AssertionError("Expected one recovered and one remaining blob")
        recovered_row = recovered.iloc[0]
        if recovered_row["blob_relative_path"] != "old_name.py":
            raise AssertionError("Parent rename path was not resolved correctly")
        if result.summary["recommendation"] != "REEXTRACT_FULL_RUN_PY_5A_WITH_PYTHON_3_12":
            raise AssertionError("Unexpected recommendation")

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    require_python_312()
    errors_path = resolve_path(args.errors)
    panel_path = resolve_path(args.panel)
    treatment_clone_dir = resolve_path(args.treatment_clone_dir)
    control_clone_dir = resolve_path(args.control_clone_dir)
    output_dir = resolve_path(args.output_dir)
    qc_dir = resolve_path(args.qc_dir)

    print("=" * 72)
    print("Recheck AGC commit-function parse exclusions with Python 3.12+")
    print(f"Python:               {sys.version.split()[0]}")
    print(f"Extraction errors:    {errors_path}")
    print(f"Input panel:          {panel_path}")
    print(f"Treatment clones:     {treatment_clone_dir}")
    print(f"Control clones:       {control_clone_dir}")
    print(f"Output directory:     {output_dir}")
    print(f"QC directory:         {qc_dir}")
    print("=" * 72)

    result, resolution_errors, processing_errors = analyze(
        errors_path,
        panel_path,
        treatment_clone_dir,
        control_clone_dir,
        progress_every=max(0, int(args.progress_every)),
    )
    paths = write_outputs(
        result,
        resolution_errors,
        processing_errors,
        output_dir,
        qc_dir,
    )

    summary = result.summary
    print("=" * 72)
    print("Python 3.12 parse-exclusion recheck")
    print(f"Status:                         {summary['status']}")
    print(f"Recommendation:                 {summary['recommendation']}")
    print(
        "Checks passed:                  "
        f"{summary['checks_passed']}/{summary['checks_total']}"
    )
    print(f"Input error records:             {summary['input_error_records']}")
    print(f"Unique blob revisions:           {summary['resolved_unique_blob_revisions']}")
    print(f"Recovered unique blobs:          {summary['recovered_unique_blob_revisions']}")
    print(f"Remaining unique blobs:          {summary['remaining_unique_blob_revisions']}")
    print(
        "Unique blob recovery rate:      "
        f"{summary['unique_blob_recovery_rate']:.6f}"
        if summary["unique_blob_recovery_rate"] is not None
        else "Unique blob recovery rate:      NA"
    )
    print(f"F-string error records:          {summary['input_fstring_error_records']}")
    print(
        "Recovered f-string records:     "
        f"{summary['fstring_recovered_error_records']}"
    )
    print(
        "F-string record recovery rate:  "
        f"{summary['fstring_error_record_recovery_rate']:.6f}"
        if summary["fstring_error_record_recovery_rate"] is not None
        else "F-string record recovery rate:  NA"
    )
    print(f"Summary:                         {paths['summary']}")
    print("=" * 72)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
