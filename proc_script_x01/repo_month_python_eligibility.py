#!/usr/bin/env python3
"""
Scan historical repository-month snapshots for tracked Python files.

Version 2 resolves repository-month snapshots before scanning. The original
monthly files record latest_commit only in months that contain commits. Empty
latest_commit cells therefore represent months whose source tree should be
carried forward from the most recent observed commit for the same repository.

Primary eligibility definition:
    python_eligible = 1 when the effective historical commit can be inspected
    and contains at least one tracked path ending in .py (case-insensitive).

Unknown handling:
    If a clone, effective commit, or Git tree cannot be inspected, Python
    eligibility and file counts remain missing. Unknown states are never encoded
    as zero, because zero is reserved for successfully inspected trees that do
    not contain Python files.

Inputs:
- run-x-a01 treatment-control pair CSV
- run-x-a02 extra-repository skip CSV
- treatment monthly time series
- control monthly time series
- panel_event_monthly.csv
- local treatment and control clone roots

Outputs:
- repository-month Python eligibility CSV
- matching-scope panel enriched with Python eligibility
- anomaly/QC detail CSV
- summary CSV
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

import pandas as pd


PAIR_REQUIRED_COLUMNS = {
    "treatment_repo",
    "treatment_clone_path",
    "control_repo",
    "control_clone_path",
    "control_rank",
}
MONTHLY_REQUIRED_COLUMNS = {"repo_name", "month", "latest_commit"}
PANEL_REQUIRED_COLUMNS = {"repo_name", "time", "dataset_source"}
SKIP_REQUIRED_COLUMNS = {"repo_name"}
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
SUCCESS_STATUSES = {"success_python", "success_no_python"}

DEFAULT_EXCLUDED_DIRS = (
    ".eggs",
    ".nox",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "generated",
    "node_modules",
    "site-packages",
    "third-party",
    "third_party",
    "vendor",
    "venv",
)

NULLABLE_INTEGER_COLUMNS = [
    "clone_exists",
    "is_git_repository",
    "commit_exists",
    "tracked_file_count",
    "python_file_count_all",
    "python_file_count_source",
    "python_file_count_excluded",
    "has_python",
    "has_python_source",
    "python_eligible",
    "months_since_observed_commit",
]


@dataclass(frozen=True)
class ScanTask:
    dataset_source: str
    repo_name: str
    latest_commit_effective: str
    clone_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and inspect each in-scope historical repository-month "
            "snapshot, then record whether the Git tree contains Python files."
        )
    )
    parser.add_argument("--matching-pairs-file", required=True, type=Path)
    parser.add_argument("--skip-repos-file", required=True, type=Path)
    parser.add_argument("--treatment-monthly-file", required=True, type=Path)
    parser.add_argument("--control-monthly-file", required=True, type=Path)
    parser.add_argument("--panel-file", required=True, type=Path)
    parser.add_argument("--treatment-clone-dir", required=True, type=Path)
    parser.add_argument("--control-clone-dir", required=True, type=Path)
    parser.add_argument("--eligibility-output", required=True, type=Path)
    parser.add_argument("--panel-output", required=True, type=Path)
    parser.add_argument("--anomaly-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--git-timeout-seconds", type=int, default=120)
    parser.add_argument("--sample-path-limit", type=int, default=5)
    parser.add_argument(
        "--excluded-dir-names",
        default=",".join(DEFAULT_EXCLUDED_DIRS),
        help=(
            "Comma-separated directory names excluded only from the secondary "
            "python_file_count_source calculation."
        ),
    )
    parser.add_argument(
        "--fail-on-scan-error",
        action="store_true",
        help="Return exit code 2 when any in-scope repository-month remains unresolved.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def repo_key(repo_name: str) -> str:
    return clean_text(repo_name).casefold()


def expected_dir_name(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def validate_args(args: argparse.Namespace) -> None:
    for path in [
        args.matching_pairs_file,
        args.skip_repos_file,
        args.treatment_monthly_file,
        args.control_monthly_file,
        args.panel_file,
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Required input file not found: {path}")

    for path in [args.treatment_clone_dir, args.control_clone_dir]:
        if not path.is_dir():
            raise NotADirectoryError(f"Required clone directory not found: {path}")

    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.git_timeout_seconds <= 0:
        raise ValueError("git-timeout-seconds must be positive")
    if args.sample_path_limit < 0:
        raise ValueError("sample-path-limit must be non-negative")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(sorted(missing))}")


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    """Read a CSV without chunk-based dtype inference for key text columns."""
    dtype = {column: "string" for column in string_columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, ...]:
    pairs = read_csv_stable(
        args.matching_pairs_file,
        ["treatment_repo", "treatment_clone_path", "control_repo", "control_clone_path"],
    )
    skip = read_csv_stable(args.skip_repos_file, ["repo_name"])
    treatment = read_csv_stable(
        args.treatment_monthly_file,
        ["repo_name", "month", "latest_commit"],
    )
    control = read_csv_stable(
        args.control_monthly_file,
        ["repo_name", "month", "latest_commit"],
    )
    panel = read_csv_stable(args.panel_file, ["repo_name", "time", "dataset_source"])

    require_columns(pairs, PAIR_REQUIRED_COLUMNS, "matching-pairs CSV")
    require_columns(skip, SKIP_REQUIRED_COLUMNS, "skip-repositories CSV")
    require_columns(treatment, MONTHLY_REQUIRED_COLUMNS, "treatment monthly CSV")
    require_columns(control, MONTHLY_REQUIRED_COLUMNS, "control monthly CSV")
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "panel CSV")
    return pairs, skip, treatment, control, panel


def choose_stable_path(values: Iterable[object], fallback: Path) -> Path:
    cleaned = sorted({clean_text(value) for value in values if clean_text(value)})
    if not cleaned:
        return fallback
    return Path(cleaned[0])


def build_scope(
    pairs: pd.DataFrame,
    skip: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> pd.DataFrame:
    skip_keys = {repo_key(value) for value in skip["repo_name"].tolist() if clean_text(value)}
    records: list[dict[str, object]] = []

    treatment_groups = pairs.groupby(
        pairs["treatment_repo"].map(repo_key), dropna=False, sort=True
    )
    for key, group in treatment_groups:
        repo_names = sorted(
            {clean_text(value) for value in group["treatment_repo"] if clean_text(value)}
        )
        if not key or not repo_names:
            continue
        canonical = repo_names[0]
        if key in skip_keys:
            continue
        clone_path = choose_stable_path(
            group["treatment_clone_path"],
            treatment_clone_dir / expected_dir_name(canonical),
        )
        records.append(
            {
                "dataset_source": "treatment",
                "repo_key": key,
                "repo_name_scope": canonical,
                "clone_path": str(clone_path),
            }
        )

    control_rows = pairs[pairs["control_repo"].notna()].copy()
    control_rows["_control_key"] = control_rows["control_repo"].map(repo_key)
    for key, group in control_rows.groupby("_control_key", dropna=False, sort=True):
        repo_names = sorted(
            {clean_text(value) for value in group["control_repo"] if clean_text(value)}
        )
        if not key or not repo_names:
            continue
        canonical = repo_names[0]
        if key in skip_keys:
            continue
        clone_path = choose_stable_path(
            group["control_clone_path"],
            control_clone_dir / expected_dir_name(canonical),
        )
        records.append(
            {
                "dataset_source": "control",
                "repo_key": key,
                "repo_name_scope": canonical,
                "clone_path": str(clone_path),
            }
        )

    scope = pd.DataFrame.from_records(
        records,
        columns=["dataset_source", "repo_key", "repo_name_scope", "clone_path"],
    )
    duplicate_mask = scope.duplicated(["dataset_source", "repo_key"], keep=False)
    if duplicate_mask.any():
        duplicates = scope.loc[duplicate_mask, ["dataset_source", "repo_name_scope"]]
        raise ValueError(
            "Scope construction produced duplicate repository identities: "
            + repr(duplicates.to_dict(orient="records"))
        )
    return scope.sort_values(["dataset_source", "repo_name_scope"]).reset_index(drop=True)


def resolve_snapshot_commits(selected: pd.DataFrame) -> pd.DataFrame:
    """Carry the last observed commit through months with no new commit."""
    data = selected.copy()
    data["latest_commit_original"] = data["latest_commit"].map(clean_text)

    valid_month_mask = data["month"].map(lambda value: bool(MONTH_PATTERN.match(value)))
    month_period = pd.Series(pd.NaT, index=data.index, dtype="period[M]")
    if valid_month_mask.any():
        month_period.loc[valid_month_mask] = pd.PeriodIndex(
            data.loc[valid_month_mask, "month"], freq="M"
        )
    data["_month_period"] = month_period
    data["_month_ordinal"] = pd.Series(pd.NA, index=data.index, dtype="Int64")
    data.loc[valid_month_mask, "_month_ordinal"] = (
        data.loc[valid_month_mask, "_month_period"].astype("int64").astype("Int64")
    )

    data = data.sort_values(
        ["dataset_source", "repo_key", "_month_period", "month"],
        na_position="last",
    ).reset_index(drop=True)

    original_nonempty = data["latest_commit_original"].replace("", pd.NA)
    data["latest_commit_effective"] = original_nonempty.groupby(
        [data["dataset_source"], data["repo_key"]], sort=False
    ).ffill()
    data["latest_commit_effective"] = data["latest_commit_effective"].fillna("")

    observed_month_ordinal = data["_month_ordinal"].where(
        data["latest_commit_original"].ne("")
    )
    data["_observed_month_ordinal"] = observed_month_ordinal.groupby(
        [data["dataset_source"], data["repo_key"]], sort=False
    ).ffill()

    data["commit_resolution"] = "missing_no_prior_commit"
    data.loc[data["latest_commit_original"].ne(""), "commit_resolution"] = "observed"
    data.loc[
        data["latest_commit_original"].eq("")
        & data["latest_commit_effective"].ne(""),
        "commit_resolution",
    ] = "carried_forward"

    data["months_since_observed_commit"] = (
        data["_month_ordinal"] - data["_observed_month_ordinal"]
    ).astype("Int64")

    # Keep a compatibility alias that points to the effective snapshot commit.
    data["latest_commit"] = data["latest_commit_effective"]
    return data


def prepare_monthly(
    monthly: pd.DataFrame,
    dataset_source: str,
    scope: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = monthly.copy()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["month"] = data["month"].map(clean_text)
    data["latest_commit"] = data["latest_commit"].map(clean_text)
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["dataset_source"] = dataset_source

    source_scope = scope[scope["dataset_source"] == dataset_source].copy()
    selected = data.merge(
        source_scope,
        on=["dataset_source", "repo_key"],
        how="inner",
        validate="many_to_one",
    )

    anomaly_records: list[dict[str, object]] = []
    duplicate_mask = selected.duplicated(
        ["dataset_source", "repo_key", "month"], keep=False
    )
    for row in selected.loc[duplicate_mask].itertuples(index=False):
        anomaly_records.append(
            {
                "anomaly_type": "duplicate_monthly_key",
                "dataset_source": dataset_source,
                "repo_name": row.repo_name,
                "month": row.month,
                "latest_commit_original": row.latest_commit,
                "latest_commit_effective": "",
                "commit_resolution": "",
                "detail": "Duplicate dataset_source + repo_name + month in monthly input.",
            }
        )
    if duplicate_mask.any():
        raise ValueError(
            f"{dataset_source} monthly input contains duplicate in-scope repository-month keys"
        )

    for row in selected.itertuples(index=False):
        if not MONTH_PATTERN.match(row.month):
            anomaly_records.append(
                {
                    "anomaly_type": "invalid_month_format",
                    "dataset_source": dataset_source,
                    "repo_name": row.repo_name,
                    "month": row.month,
                    "latest_commit_original": row.latest_commit,
                    "latest_commit_effective": "",
                    "commit_resolution": "",
                    "detail": "Expected YYYY-MM month format.",
                }
            )

    monthly_keys = set(selected["repo_key"])
    for row in source_scope.itertuples(index=False):
        if row.repo_key not in monthly_keys:
            anomaly_records.append(
                {
                    "anomaly_type": "scope_repo_missing_monthly_rows",
                    "dataset_source": dataset_source,
                    "repo_name": row.repo_name_scope,
                    "month": "",
                    "latest_commit_original": "",
                    "latest_commit_effective": "",
                    "commit_resolution": "",
                    "detail": "In matching scope but absent from the corresponding monthly CSV.",
                }
            )

    selected = resolve_snapshot_commits(selected)
    anomalies = pd.DataFrame.from_records(
        anomaly_records,
        columns=[
            "anomaly_type",
            "dataset_source",
            "repo_name",
            "month",
            "latest_commit_original",
            "latest_commit_effective",
            "commit_resolution",
            "detail",
        ],
    )

    keep_columns = [
        "dataset_source",
        "repo_name",
        "repo_key",
        "repo_name_scope",
        "month",
        "latest_commit_original",
        "latest_commit_effective",
        "latest_commit",
        "commit_resolution",
        "months_since_observed_commit",
        "clone_path",
    ]
    return selected[keep_columns].copy(), anomalies


def run_git(command: list[str], timeout_seconds: int) -> tuple[int, bytes, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        return int(completed.returncode), completed.stdout, stderr
    except subprocess.TimeoutExpired as exc:
        stderr = b"" if exc.stderr is None else exc.stderr
        decoded = (
            stderr.decode("utf-8", errors="replace").strip()
            if isinstance(stderr, bytes)
            else str(stderr).strip()
        )
        return 124, b"", (
            f"Git command timed out after {timeout_seconds} seconds. {decoded}"
        ).strip()
    except OSError as exc:
        return 127, b"", str(exc)


def is_excluded_python_path(path: str, excluded_dirs: set[str]) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path).parts[:-1]]
    return any(part in excluded_dirs for part in parts)


def unknown_scan_base(task: ScanTask) -> dict[str, object]:
    return {
        "dataset_source": task.dataset_source,
        "repo_name": task.repo_name,
        "latest_commit_effective": task.latest_commit_effective,
        "clone_path": str(task.clone_path),
        "clone_exists": int(task.clone_path.is_dir()),
        "is_git_repository": pd.NA,
        "commit_exists": pd.NA,
        "tracked_file_count": pd.NA,
        "python_file_count_all": pd.NA,
        "python_file_count_source": pd.NA,
        "python_file_count_excluded": pd.NA,
        "has_python": pd.NA,
        "has_python_source": pd.NA,
        "python_eligible": pd.NA,
        "python_path_samples": "",
        "excluded_python_path_samples": "",
        "scan_status": "",
        "error_message": "",
    }


def scan_one_task(
    task: ScanTask,
    *,
    timeout_seconds: int,
    excluded_dirs: set[str],
    sample_path_limit: int,
) -> dict[str, object]:
    base = unknown_scan_base(task)

    if not task.clone_path.is_dir():
        base["is_git_repository"] = 0
        base["commit_exists"] = 0
        base["scan_status"] = "missing_clone"
        base["error_message"] = "Clone directory does not exist."
        return base

    code, stdout, stderr = run_git(
        ["git", "-C", str(task.clone_path), "rev-parse", "--is-inside-work-tree"],
        timeout_seconds,
    )
    if code != 0 or stdout.decode("utf-8", errors="replace").strip().casefold() != "true":
        base["is_git_repository"] = 0
        base["commit_exists"] = 0
        base["scan_status"] = "not_git_repository"
        base["error_message"] = stderr or "Path is not a Git work tree."
        return base
    base["is_git_repository"] = 1

    code, _, stderr = run_git(
        [
            "git",
            "-C",
            str(task.clone_path),
            "cat-file",
            "-e",
            f"{task.latest_commit_effective}^{{commit}}",
        ],
        timeout_seconds,
    )
    if code != 0:
        base["commit_exists"] = 0
        base["scan_status"] = "commit_not_found"
        base["error_message"] = stderr or "Commit is not available in the local clone."
        return base
    base["commit_exists"] = 1

    code, stdout, stderr = run_git(
        [
            "git",
            "-C",
            str(task.clone_path),
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            task.latest_commit_effective,
        ],
        timeout_seconds,
    )
    if code != 0:
        base["scan_status"] = "git_ls_tree_failed"
        base["error_message"] = stderr or "git ls-tree failed."
        return base

    paths = [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in stdout.split(b"\0")
        if raw
    ]
    python_paths = [path for path in paths if path.casefold().endswith(".py")]
    source_paths = [
        path for path in python_paths if not is_excluded_python_path(path, excluded_dirs)
    ]
    source_path_set = set(source_paths)
    excluded_paths = [path for path in python_paths if path not in source_path_set]

    base["tracked_file_count"] = len(paths)
    base["python_file_count_all"] = len(python_paths)
    base["python_file_count_source"] = len(source_paths)
    base["python_file_count_excluded"] = len(excluded_paths)
    base["has_python"] = int(bool(python_paths))
    base["has_python_source"] = int(bool(source_paths))
    base["python_eligible"] = int(bool(python_paths))
    base["python_path_samples"] = " | ".join(python_paths[:sample_path_limit])
    base["excluded_python_path_samples"] = " | ".join(
        excluded_paths[:sample_path_limit]
    )
    base["scan_status"] = "success_python" if python_paths else "success_no_python"
    return base


def make_unresolved_commit_rows(monthly_scope: pd.DataFrame) -> pd.DataFrame:
    unresolved = monthly_scope[monthly_scope["latest_commit_effective"].eq("")].copy()
    if unresolved.empty:
        return pd.DataFrame()

    unresolved["clone_exists"] = unresolved["clone_path"].map(
        lambda value: int(Path(clean_text(value)).is_dir())
    )
    unresolved["is_git_repository"] = pd.NA
    unresolved["commit_exists"] = pd.NA
    for column in [
        "tracked_file_count",
        "python_file_count_all",
        "python_file_count_source",
        "python_file_count_excluded",
        "has_python",
        "has_python_source",
        "python_eligible",
    ]:
        unresolved[column] = pd.NA
    unresolved["python_path_samples"] = ""
    unresolved["excluded_python_path_samples"] = ""
    unresolved["scan_status"] = "missing_no_prior_commit"
    unresolved["error_message"] = (
        "Monthly row has no observed commit and no earlier commit to carry forward."
    )
    return unresolved


def scan_monthly_rows(
    monthly_scope: pd.DataFrame,
    *,
    workers: int,
    timeout_seconds: int,
    excluded_dirs: set[str],
    sample_path_limit: int,
) -> tuple[pd.DataFrame, int]:
    resolved = monthly_scope[monthly_scope["latest_commit_effective"].ne("")].copy()
    scan_keys = [
        "dataset_source",
        "repo_name_scope",
        "latest_commit_effective",
        "clone_path",
    ]
    unique_snapshots = resolved[scan_keys].drop_duplicates().reset_index(drop=True)
    logging.info(
        "Resolved %d repository-month rows into %d unique historical snapshots",
        len(resolved),
        len(unique_snapshots),
    )

    tasks = [
        ScanTask(
            dataset_source=clean_text(row.dataset_source),
            repo_name=clean_text(row.repo_name_scope),
            latest_commit_effective=clean_text(row.latest_commit_effective),
            clone_path=Path(clean_text(row.clone_path)),
        )
        for row in unique_snapshots.itertuples(index=False)
    ]

    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_task = {
            executor.submit(
                scan_one_task,
                task,
                timeout_seconds=timeout_seconds,
                excluded_dirs=excluded_dirs,
                sample_path_limit=sample_path_limit,
            ): task
            for task in tasks
        }
        completed_count = 0
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                record = future.result()
            except Exception as exc:  # Defensive per-snapshot isolation.
                record = unknown_scan_base(task)
                record["scan_status"] = "unexpected_scan_error"
                record["error_message"] = str(exc)
            records.append(record)
            completed_count += 1
            if completed_count % 1000 == 0 or completed_count == len(tasks):
                logging.info(
                    "Scanned %d/%d unique historical snapshots",
                    completed_count,
                    len(tasks),
                )

    scan_results = pd.DataFrame.from_records(records)
    if not scan_results.empty:
        scan_results = scan_results.rename(columns={"repo_name": "repo_name_scope"})
        resolved = resolved.merge(
            scan_results,
            on=scan_keys,
            how="left",
            validate="many_to_one",
        )

    unresolved = make_unresolved_commit_rows(monthly_scope)
    eligibility = pd.concat([resolved, unresolved], ignore_index=True, sort=False)

    output_columns = [
        "dataset_source",
        "repo_name_scope",
        "month",
        "latest_commit_original",
        "latest_commit_effective",
        "latest_commit",
        "commit_resolution",
        "months_since_observed_commit",
        "clone_path",
        "clone_exists",
        "is_git_repository",
        "commit_exists",
        "tracked_file_count",
        "python_file_count_all",
        "python_file_count_source",
        "python_file_count_excluded",
        "has_python",
        "has_python_source",
        "python_eligible",
        "python_path_samples",
        "excluded_python_path_samples",
        "scan_status",
        "error_message",
    ]
    eligibility = eligibility[output_columns].rename(
        columns={"repo_name_scope": "repo_name"}
    )
    for column in NULLABLE_INTEGER_COLUMNS:
        eligibility[column] = pd.to_numeric(eligibility[column], errors="coerce").astype("Int64")

    eligibility = eligibility.sort_values(
        ["dataset_source", "repo_name", "month"]
    ).reset_index(drop=True)
    return eligibility, len(unique_snapshots)


def filter_panel_to_scope(panel: pd.DataFrame, scope: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    result["repo_name"] = result["repo_name"].map(clean_text)
    result["time"] = result["time"].map(clean_text)
    result["dataset_source"] = result["dataset_source"].map(
        lambda value: clean_text(value).casefold()
    )
    result["repo_key"] = result["repo_name"].map(repo_key)

    scope_keys = scope[["dataset_source", "repo_key"]].drop_duplicates()
    return result.merge(
        scope_keys,
        on=["dataset_source", "repo_key"],
        how="inner",
        validate="many_to_one",
    )


def enrich_panel(panel_scope: pd.DataFrame, eligibility: pd.DataFrame) -> pd.DataFrame:
    scan = eligibility.copy()
    scan["repo_key"] = scan["repo_name"].map(repo_key)
    scan_columns = [
        "dataset_source",
        "repo_key",
        "month",
        "latest_commit_original",
        "latest_commit_effective",
        "latest_commit",
        "commit_resolution",
        "months_since_observed_commit",
        "clone_path",
        "clone_exists",
        "is_git_repository",
        "commit_exists",
        "tracked_file_count",
        "python_file_count_all",
        "python_file_count_source",
        "python_file_count_excluded",
        "has_python",
        "has_python_source",
        "python_eligible",
        "python_path_samples",
        "excluded_python_path_samples",
        "scan_status",
        "error_message",
    ]
    scan = scan[scan_columns].rename(columns={"month": "time"})

    enriched = panel_scope.merge(
        scan,
        on=["dataset_source", "repo_key", "time"],
        how="left",
        validate="many_to_one",
    )
    enriched["eligibility_join_status"] = enriched["scan_status"].notna().map(
        {True: "matched_repo_month", False: "missing_monthly_snapshot"}
    )
    return enriched.drop(columns=["repo_key"])


def build_anomalies(
    input_anomalies: list[pd.DataFrame],
    eligibility: pd.DataFrame,
    panel_enriched: pd.DataFrame,
    scope: pd.DataFrame,
    panel_scope: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for frame in input_anomalies:
        if not frame.empty:
            records.extend(frame.to_dict(orient="records"))

    for row in eligibility[~eligibility["scan_status"].isin(SUCCESS_STATUSES)].itertuples(
        index=False
    ):
        records.append(
            {
                "anomaly_type": "repo_month_scan_failure",
                "dataset_source": row.dataset_source,
                "repo_name": row.repo_name,
                "month": row.month,
                "latest_commit_original": row.latest_commit_original,
                "latest_commit_effective": row.latest_commit_effective,
                "commit_resolution": row.commit_resolution,
                "detail": f"{row.scan_status}: {row.error_message}",
            }
        )

    missing_panel = panel_enriched[
        panel_enriched["eligibility_join_status"] == "missing_monthly_snapshot"
    ]
    for row in missing_panel.itertuples(index=False):
        records.append(
            {
                "anomaly_type": "panel_row_missing_monthly_snapshot",
                "dataset_source": row.dataset_source,
                "repo_name": row.repo_name,
                "month": row.time,
                "latest_commit_original": "",
                "latest_commit_effective": "",
                "commit_resolution": "",
                "detail": "Panel row has no matching in-scope monthly snapshot row.",
            }
        )

    panel_repo_keys = set(
        zip(panel_scope["dataset_source"], panel_scope["repo_key"], strict=False)
    )
    for row in scope.itertuples(index=False):
        if (row.dataset_source, row.repo_key) not in panel_repo_keys:
            records.append(
                {
                    "anomaly_type": "scope_repo_missing_panel_rows",
                    "dataset_source": row.dataset_source,
                    "repo_name": row.repo_name_scope,
                    "month": "",
                    "latest_commit_original": "",
                    "latest_commit_effective": "",
                    "commit_resolution": "",
                    "detail": "In matching scope but absent from panel_event_monthly.csv.",
                }
            )

    columns = [
        "anomaly_type",
        "dataset_source",
        "repo_name",
        "month",
        "latest_commit_original",
        "latest_commit_effective",
        "commit_resolution",
        "detail",
    ]
    anomalies = pd.DataFrame.from_records(records, columns=columns)
    if anomalies.empty:
        return pd.DataFrame(columns=columns)
    return anomalies.sort_values(
        ["anomaly_type", "dataset_source", "repo_name", "month"]
    ).reset_index(drop=True)


def add_summary_row(
    rows: list[dict[str, object]],
    section: str,
    metric: str,
    value: object,
    note: str = "",
) -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def build_summary(
    *,
    pairs: pd.DataFrame,
    skip: pd.DataFrame,
    scope: pd.DataFrame,
    treatment_scope_monthly: pd.DataFrame,
    control_scope_monthly: pd.DataFrame,
    eligibility: pd.DataFrame,
    unique_snapshots_scanned: int,
    panel_scope: pd.DataFrame,
    panel_enriched: pd.DataFrame,
    anomalies: pd.DataFrame,
    excluded_dirs: set[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    add_summary_row(rows, "implementation", "version", "v2")
    add_summary_row(rows, "input", "matching_pair_rows", len(pairs))
    add_summary_row(rows, "input", "skip_repository_rows", len(skip))
    add_summary_row(
        rows,
        "definition",
        "python_eligibility",
        "tracked_py_file_count_gt_0",
        "Primary eligibility requires at least one tracked .py path in latest_commit_effective.",
    )
    add_summary_row(
        rows,
        "definition",
        "empty_latest_commit_resolution",
        "repository_forward_fill",
        "Empty monthly latest_commit values use the most recent observed commit from the same repository.",
    )
    add_summary_row(
        rows,
        "definition",
        "unknown_eligibility",
        "blank",
        "Failed or unavailable snapshots keep Python eligibility and file counts missing rather than zero.",
    )
    add_summary_row(
        rows,
        "definition",
        "secondary_source_excluded_dirs",
        ";".join(sorted(excluded_dirs)),
        "Applied only to python_file_count_source; it does not change primary eligibility.",
    )

    for source in ["treatment", "control"]:
        source_scope = scope[scope["dataset_source"] == source]
        source_eligibility = eligibility[eligibility["dataset_source"] == source]
        add_summary_row(
            rows, "scope", f"{source}_repositories", source_scope["repo_key"].nunique()
        )
        add_summary_row(rows, "scope", f"{source}_repo_month_rows", len(source_eligibility))
        add_summary_row(
            rows,
            "result",
            f"{source}_repo_months_with_python",
            int(source_eligibility["python_eligible"].eq(1).sum()),
        )
        add_summary_row(
            rows,
            "result",
            f"{source}_repo_months_without_python",
            int(source_eligibility["scan_status"].eq("success_no_python").sum()),
        )
        add_summary_row(
            rows,
            "result",
            f"{source}_repo_month_scan_failures",
            int((~source_eligibility["scan_status"].isin(SUCCESS_STATUSES)).sum()),
        )
        add_summary_row(
            rows,
            "resolution",
            f"{source}_repo_months_carried_forward",
            int(source_eligibility["commit_resolution"].eq("carried_forward").sum()),
        )

    add_summary_row(
        rows, "input", "treatment_monthly_rows_selected", len(treatment_scope_monthly)
    )
    add_summary_row(
        rows, "input", "control_monthly_rows_selected", len(control_scope_monthly)
    )
    add_summary_row(rows, "result", "total_repo_month_rows", len(eligibility))
    add_summary_row(rows, "result", "unique_historical_snapshots_scanned", unique_snapshots_scanned)
    add_summary_row(
        rows,
        "result",
        "total_repo_months_with_python",
        int(eligibility["python_eligible"].eq(1).sum()),
    )
    add_summary_row(
        rows,
        "result",
        "total_repo_months_without_python",
        int(eligibility["scan_status"].eq("success_no_python").sum()),
    )
    add_summary_row(
        rows,
        "result",
        "total_repo_months_unknown",
        int((~eligibility["scan_status"].isin(SUCCESS_STATUSES)).sum()),
    )
    add_summary_row(
        rows,
        "result",
        "total_repo_month_scan_failures",
        int((~eligibility["scan_status"].isin(SUCCESS_STATUSES)).sum()),
    )
    add_summary_row(rows, "panel", "matching_scope_panel_rows", len(panel_scope))
    add_summary_row(
        rows,
        "panel",
        "panel_rows_joined_to_eligibility",
        int((panel_enriched["eligibility_join_status"] == "matched_repo_month").sum()),
    )
    add_summary_row(
        rows,
        "panel",
        "panel_rows_missing_monthly_snapshot",
        int((panel_enriched["eligibility_join_status"] == "missing_monthly_snapshot").sum()),
    )
    add_summary_row(
        rows,
        "panel",
        "panel_rows_with_resolved_python_eligibility",
        int(panel_enriched["scan_status"].isin(SUCCESS_STATUSES).sum()),
    )
    add_summary_row(
        rows,
        "panel",
        "panel_rows_with_unknown_python_eligibility",
        int((panel_enriched["eligibility_join_status"].eq("matched_repo_month")
             & ~panel_enriched["scan_status"].isin(SUCCESS_STATUSES)).sum()),
    )
    add_summary_row(rows, "qc", "anomaly_rows", len(anomalies))

    for resolution, count in (
        eligibility["commit_resolution"].value_counts(dropna=False).sort_index().items()
    ):
        add_summary_row(rows, "commit_resolution", str(resolution), int(count))
    for status, count in eligibility["scan_status"].value_counts(dropna=False).sort_index().items():
        add_summary_row(rows, "scan_status", str(status), int(count))
    for anomaly_type, count in anomalies["anomaly_type"].value_counts().sort_index().items():
        add_summary_row(rows, "anomaly_type", str(anomaly_type), int(count))

    return pd.DataFrame(rows, columns=["section", "metric", "value", "note"])


def write_outputs(
    *,
    eligibility: pd.DataFrame,
    panel_enriched: pd.DataFrame,
    anomalies: pd.DataFrame,
    summary: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    for path in [
        args.eligibility_output,
        args.panel_output,
        args.anomaly_output,
        args.summary_output,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)

    eligibility.to_csv(args.eligibility_output, index=False)
    panel_enriched.to_csv(args.panel_output, index=False)
    anomalies.to_csv(args.anomaly_output, index=False)
    summary.to_csv(args.summary_output, index=False)

    logging.info("Wrote %d rows to %s", len(eligibility), args.eligibility_output)
    logging.info("Wrote %d rows to %s", len(panel_enriched), args.panel_output)
    logging.info("Wrote %d rows to %s", len(anomalies), args.anomaly_output)
    logging.info("Wrote %d rows to %s", len(summary), args.summary_output)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        validate_args(args)
        pairs, skip, treatment, control, panel = read_inputs(args)
        excluded_dirs = {
            item.strip().casefold()
            for item in args.excluded_dir_names.split(",")
            if item.strip()
        }

        scope = build_scope(
            pairs,
            skip,
            args.treatment_clone_dir,
            args.control_clone_dir,
        )
        logging.info(
            "Matching scope: %d treatment repositories and %d control repositories",
            int((scope["dataset_source"] == "treatment").sum()),
            int((scope["dataset_source"] == "control").sum()),
        )

        treatment_scope_monthly, treatment_anomalies = prepare_monthly(
            treatment, "treatment", scope
        )
        control_scope_monthly, control_anomalies = prepare_monthly(
            control, "control", scope
        )
        monthly_scope = pd.concat(
            [treatment_scope_monthly, control_scope_monthly], ignore_index=True
        )
        logging.info("Selected %d in-scope repository-month rows", len(monthly_scope))
        logging.info(
            "Commit resolution: observed=%d, carried_forward=%d, missing_no_prior_commit=%d",
            int(monthly_scope["commit_resolution"].eq("observed").sum()),
            int(monthly_scope["commit_resolution"].eq("carried_forward").sum()),
            int(monthly_scope["commit_resolution"].eq("missing_no_prior_commit").sum()),
        )

        eligibility, unique_snapshots_scanned = scan_monthly_rows(
            monthly_scope,
            workers=args.workers,
            timeout_seconds=args.git_timeout_seconds,
            excluded_dirs=excluded_dirs,
            sample_path_limit=args.sample_path_limit,
        )

        panel_scope = filter_panel_to_scope(panel, scope)
        panel_enriched = enrich_panel(panel_scope, eligibility)
        anomalies = build_anomalies(
            [treatment_anomalies, control_anomalies],
            eligibility,
            panel_enriched,
            scope,
            panel_scope,
        )
        summary = build_summary(
            pairs=pairs,
            skip=skip,
            scope=scope,
            treatment_scope_monthly=treatment_scope_monthly,
            control_scope_monthly=control_scope_monthly,
            eligibility=eligibility,
            unique_snapshots_scanned=unique_snapshots_scanned,
            panel_scope=panel_scope,
            panel_enriched=panel_enriched,
            anomalies=anomalies,
            excluded_dirs=excluded_dirs,
        )
        write_outputs(
            eligibility=eligibility,
            panel_enriched=panel_enriched,
            anomalies=anomalies,
            summary=summary,
            args=args,
        )

        scan_failures = int(
            (~eligibility["scan_status"].isin(SUCCESS_STATUSES)).sum()
        )
        logging.info("Repository-month scan failures: %d", scan_failures)
        if args.fail_on_scan_error and scan_failures:
            logging.error("Strict mode requested and scan failures remain")
            return 2
        return 0
    except Exception as exc:
        logging.exception("Repository-month Python eligibility scan failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
