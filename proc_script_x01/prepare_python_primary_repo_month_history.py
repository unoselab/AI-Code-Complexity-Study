#!/usr/bin/env python3
"""
Prepare the Python-primary paper repo-month history panel for run-x-c03.

Purpose
-------
This stage joins the paper Appendix Python repository scope from run-x-c01 with
clone availability from run-x-c02 and the replication-package monthly inputs.
For every paper repo-month, it records whether a valid local clone exists and,
when available, resolves a historical Git commit without modifying the clone.

The resulting unique snapshot manifest is the input for the next whole-repo
cloc stage. Repeated repo-months that resolve to the same commit are retained in
the repo-month history output but deduplicated in the unique snapshot manifest.

Commit-resolution order
-----------------------
1. Use the monthly CSV latest_commit when it exists locally and was committed
   before the end of that calendar month.
2. For a blank or unusable monthly value, carry forward the most recent prior
   nonblank monthly latest_commit from the same repository when valid.
3. Otherwise, resolve the latest commit reachable from the clone's current HEAD
   before the end of the calendar month.
4. Keep the row unresolved when none of the above methods succeeds.

Safety
------
Only read-only Git commands are used: rev-parse, cat-file, show, and rev-list.
The script never checks out, resets, cleans, pulls, fetches, or writes into a
repository clone.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


TREATMENT_REQUIRED_COLUMNS = {
    "repo_name",
    "repo_name_key",
    "paper_panel_rows",
    "event_yyyymm",
    "included_in_clone_manifest",
}
CONTROL_REQUIRED_COLUMNS = {
    "repo_name",
    "repo_name_key",
    "paper_panel_rows",
    "eligible_for_python_scope_clone",
}
CLONE_MANIFEST_REQUIRED_COLUMNS = {
    "scope_role",
    "repo_name",
    "repo_name_key",
    "expected_clone_path",
}
CLONE_STATUS_REQUIRED_COLUMNS = {
    "scope_role",
    "repo_name",
    "repo_name_key",
    "expected_clone_path",
    "status",
    "success",
    "clone_exists",
    "is_git_repository",
    "git_head_sha",
    "failure_reason",
}
PANEL_REQUIRED_COLUMNS = {
    "repo_name",
    "time",
    "is_treatment",
    "event",
    "post_event",
    "time_to_event",
    "commits",
    "lines_added",
    "ncloc",
    "dataset_source",
}
MONTHLY_REQUIRED_COLUMNS = {
    "month",
    "repo_name",
    "latest_commit",
}

SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
ROLE_ORDER = {"treatment": 0, "control": 1}


@dataclass(frozen=True)
class GitResult:
    """Result of one read-only Git command."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class CommitCheck:
    """Cached validation metadata for one Git commit object."""

    exists: bool
    timestamp: Optional[int]
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a paper-aligned Python-primary repo-month history panel "
            "and unique historical snapshot manifest."
        )
    )
    parser.add_argument("--treatment-repos-file", required=True, type=Path)
    parser.add_argument("--control-repos-file", required=True, type=Path)
    parser.add_argument("--clone-manifest-file", required=True, type=Path)
    parser.add_argument("--clone-status-file", required=True, type=Path)
    parser.add_argument("--panel-file", required=True, type=Path)
    parser.add_argument("--treatment-monthly-file", required=True, type=Path)
    parser.add_argument("--control-monthly-file", required=True, type=Path)

    parser.add_argument("--paper-panel-output", required=True, type=Path)
    parser.add_argument("--history-output", required=True, type=Path)
    parser.add_argument("--unique-snapshot-output", required=True, type=Path)
    parser.add_argument("--resolution-audit-output", required=True, type=Path)
    parser.add_argument("--timezone-audit-output", required=True, type=Path)
    parser.add_argument("--unresolved-output", required=True, type=Path)
    parser.add_argument("--clone-unavailable-output", required=True, type=Path)
    parser.add_argument("--support-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)

    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--git-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--history-timezone",
        default="America/Chicago",
        help=(
            "IANA timezone used by the original monthly pipeline when assigning "
            "commit timestamps to calendar months. Default: America/Chicago."
        ),
    )
    parser.add_argument("--allow-carry-forward", type=int, choices=[0, 1], default=1)
    parser.add_argument("--allow-git-head-fallback", type=int, choices=[0, 1], default=1)
    parser.add_argument("--fail-on-unresolved", type=int, choices=[0, 1], default=0)
    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)

    parser.add_argument("--expected-paper-treatment-repos", type=int, default=121)
    parser.add_argument("--expected-paper-control-repos", type=int, default=127)
    parser.add_argument("--expected-paper-treatment-rows", type=int, default=1223)
    parser.add_argument("--expected-paper-control-rows", type=int, default=1238)
    parser.add_argument("--expected-paper-panel-rows", type=int, default=2461)
    parser.add_argument("--expected-clone-available-treatment-repos", type=int, default=116)
    parser.add_argument("--expected-clone-available-control-repos", type=int, default=126)
    parser.add_argument("--expected-clone-available-repos", type=int, default=242)
    parser.add_argument("--expected-clone-unavailable-repos", type=int, default=6)
    parser.add_argument("--expected-clone-unavailable-rows", type=int, default=50)
    parser.add_argument("--expected-history-candidate-rows", type=int, default=2411)

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
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
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def repo_key(value: object) -> str:
    return clean_text(value).strip("/").casefold()


def normalize_bool_value(value: object) -> bool:
    text = clean_text(value).casefold()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    raise ValueError(f"Invalid Boolean value: {value!r}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def parse_month_series(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text)
    parsed = pd.to_datetime(text, format="%Y-%m", errors="coerce")
    invalid = text.ne("") & parsed.isna()
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid YYYY-MM values: {examples}")
    result = pd.Series(pd.NaT, index=values.index, dtype="period[M]")
    valid = parsed.notna()
    result.loc[valid] = parsed.loc[valid].dt.to_period("M")
    return result


def normalize_repo_table(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_name_key"] = data["repo_name"].map(repo_key)
    return data


def validate_args(args: argparse.Namespace) -> None:
    load_history_timezone(args.history_timezone)
    for path, label in [
        (args.treatment_repos_file, "Treatment repository input"),
        (args.control_repos_file, "Control repository input"),
        (args.clone_manifest_file, "Clone manifest input"),
        (args.clone_status_file, "Clone status input"),
        (args.panel_file, "Paper panel input"),
        (args.treatment_monthly_file, "Treatment monthly input"),
        (args.control_monthly_file, "Control monthly input"),
    ]:
        require_file(path, label)
    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.git_timeout_seconds <= 0:
        raise ValueError("git-timeout-seconds must be positive")


def run_command(command: list[str], timeout_seconds: int) -> GitResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=timeout_seconds,
        )
        return GitResult(
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GitResult(
            returncode=124,
            stdout=stdout.strip(),
            stderr=(stderr.strip() or f"Command timed out after {timeout_seconds} seconds."),
            timed_out=True,
        )


def run_git(clone_path: Path, git_args: list[str], timeout_seconds: int) -> GitResult:
    return run_command(["git", "-C", str(clone_path), *git_args], timeout_seconds)


def make_snapshot_key(scope_role: str, repo_name: str, commit_sha: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", repo_name).strip("_")
    digest = hashlib.sha256(
        f"{scope_role}|{repo_key(repo_name)}|{commit_sha.casefold()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{scope_role}__{slug}__{commit_sha[:12]}__{digest}"


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, ...]:
    treatment = pd.read_csv(args.treatment_repos_file, low_memory=False)
    control = pd.read_csv(args.control_repos_file, low_memory=False)
    manifest = pd.read_csv(args.clone_manifest_file, low_memory=False)
    status = pd.read_csv(args.clone_status_file, low_memory=False)
    panel = pd.read_csv(args.panel_file, low_memory=False)
    treatment_monthly = pd.read_csv(args.treatment_monthly_file, low_memory=False)
    control_monthly = pd.read_csv(args.control_monthly_file, low_memory=False)

    require_columns(treatment, TREATMENT_REQUIRED_COLUMNS, "Treatment repository file")
    require_columns(control, CONTROL_REQUIRED_COLUMNS, "Control repository file")
    require_columns(manifest, CLONE_MANIFEST_REQUIRED_COLUMNS, "Clone manifest file")
    require_columns(status, CLONE_STATUS_REQUIRED_COLUMNS, "Clone status file")
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "Paper panel file")
    require_columns(treatment_monthly, MONTHLY_REQUIRED_COLUMNS, "Treatment monthly file")
    require_columns(control_monthly, MONTHLY_REQUIRED_COLUMNS, "Control monthly file")

    return treatment, control, manifest, status, panel, treatment_monthly, control_monthly


def build_scope(
    treatment: pd.DataFrame,
    control: pd.DataFrame,
    manifest: pd.DataFrame,
    status: pd.DataFrame,
) -> pd.DataFrame:
    treatment = normalize_repo_table(treatment)
    control = normalize_repo_table(control)
    manifest = normalize_repo_table(manifest)
    status = normalize_repo_table(status)

    treatment = treatment[
        treatment["included_in_clone_manifest"].map(normalize_bool_value)
    ].copy()
    control = control[
        control["eligible_for_python_scope_clone"].map(normalize_bool_value)
    ].copy()

    treatment_scope = treatment[["repo_name", "repo_name_key", "paper_panel_rows", "event_yyyymm"]].copy()
    treatment_scope["scope_role"] = "treatment"
    control_scope = control[["repo_name", "repo_name_key", "paper_panel_rows"]].copy()
    control_scope["event_yyyymm"] = pd.NA
    control_scope["scope_role"] = "control"
    scope = pd.concat([treatment_scope, control_scope], ignore_index=True)

    if scope.duplicated(["scope_role", "repo_name_key"]).any():
        raise ValueError("C01 scope contains duplicate role/repository rows")
    overlap = set(treatment_scope["repo_name_key"]) & set(control_scope["repo_name_key"])
    if overlap:
        raise ValueError(f"Treatment/control repository overlap detected: {sorted(overlap)[:10]}")

    manifest_key = manifest[["scope_role", "repo_name_key", "expected_clone_path"]].copy()
    if manifest_key.duplicated(["scope_role", "repo_name_key"]).any():
        raise ValueError("Clone manifest contains duplicate role/repository rows")

    status_key = status.copy()
    if status_key.duplicated(["scope_role", "repo_name_key"]).any():
        raise ValueError("Clone status contains duplicate role/repository rows")
    for column in ["success", "clone_exists", "is_git_repository"]:
        status_key[column] = status_key[column].map(normalize_bool_value)

    status_columns = [
        "scope_role",
        "repo_name_key",
        "expected_clone_path",
        "status",
        "success",
        "clone_exists",
        "is_git_repository",
        "git_head_sha",
        "failure_reason",
    ]
    status_key = status_key[status_columns].rename(
        columns={
            "expected_clone_path": "c02_expected_clone_path",
            "status": "c02_clone_status",
            "success": "c02_success",
            "clone_exists": "c02_clone_exists",
            "is_git_repository": "c02_is_git_repository",
            "git_head_sha": "c02_git_head_sha",
            "failure_reason": "c02_failure_reason",
        }
    )

    scope = scope.merge(
        manifest_key,
        on=["scope_role", "repo_name_key"],
        how="left",
        validate="one_to_one",
    )
    scope = scope.merge(
        status_key,
        on=["scope_role", "repo_name_key"],
        how="left",
        validate="one_to_one",
    )

    missing_manifest = scope["expected_clone_path"].isna()
    if missing_manifest.any():
        examples = scope.loc[missing_manifest, ["scope_role", "repo_name"]].head(10).to_dict("records")
        raise ValueError(f"C01 scope rows missing from clone manifest: {examples}")
    missing_status = scope["c02_clone_status"].isna()
    if missing_status.any():
        examples = scope.loc[missing_status, ["scope_role", "repo_name"]].head(10).to_dict("records")
        raise ValueError(f"C01 scope rows missing from C02 status: {examples}")

    path_mismatch = scope["expected_clone_path"].map(clean_text).ne(
        scope["c02_expected_clone_path"].map(clean_text)
    )
    if path_mismatch.any():
        examples = scope.loc[
            path_mismatch,
            ["scope_role", "repo_name", "expected_clone_path", "c02_expected_clone_path"],
        ].head(10).to_dict("records")
        raise ValueError(f"C01/C02 clone path mismatch: {examples}")

    scope["clone_available"] = (
        scope["c02_success"]
        & scope["c02_clone_exists"]
        & scope["c02_is_git_repository"]
    )
    scope["clone_path"] = scope["expected_clone_path"].map(clean_text)
    scope["c02_git_head_sha"] = scope["c02_git_head_sha"].map(clean_text)
    scope["c02_failure_reason"] = scope["c02_failure_reason"].map(clean_text)
    return scope


def prepare_monthly(monthly: pd.DataFrame, role: str) -> pd.DataFrame:
    data = normalize_repo_table(monthly)
    data["time"] = data["month"].map(clean_text)
    data["time_period"] = parse_month_series(data["time"], f"{role} monthly month")
    if data["time_period"].isna().any():
        raise ValueError(f"{role} monthly input contains blank months")
    if data.duplicated(["repo_name_key", "time"]).any():
        raise ValueError(f"{role} monthly input contains duplicate repository-month rows")
    data["latest_commit_monthly"] = data["latest_commit"].map(clean_text)
    return data[["repo_name_key", "time", "time_period", "latest_commit_monthly"]]


def build_paper_panel(
    panel: pd.DataFrame,
    scope: pd.DataFrame,
    treatment_monthly: pd.DataFrame,
    control_monthly: pd.DataFrame,
) -> pd.DataFrame:
    data = normalize_repo_table(panel)
    data["time"] = data["time"].map(clean_text)
    data["time_period"] = parse_month_series(data["time"], "paper panel time")
    if data["time_period"].isna().any():
        raise ValueError("Paper panel contains blank months")

    scope_keys = scope[["scope_role", "repo_name_key"]].copy()
    treatment_keys = set(scope_keys.loc[scope_keys["scope_role"].eq("treatment"), "repo_name_key"])
    control_keys = set(scope_keys.loc[scope_keys["scope_role"].eq("control"), "repo_name_key"])

    role = pd.Series("", index=data.index, dtype="string")
    role.loc[data["repo_name_key"].isin(treatment_keys)] = "treatment"
    role.loc[data["repo_name_key"].isin(control_keys)] = "control"
    data["scope_role"] = role
    data = data[data["scope_role"].ne("")].copy()

    invalid_treatment_source = data["scope_role"].eq("treatment") & ~data["dataset_source"].map(clean_text).str.casefold().eq("treatment")
    invalid_control_source = data["scope_role"].eq("control") & ~data["dataset_source"].map(clean_text).str.casefold().eq("control")
    if invalid_treatment_source.any() or invalid_control_source.any():
        raise ValueError("Paper panel dataset_source conflicts with C01 scope role")

    if data.duplicated(["scope_role", "repo_name_key", "time"]).any():
        raise ValueError("Paper scope panel contains duplicate role/repository-month rows")

    treatment_monthly = prepare_monthly(treatment_monthly, "treatment")
    control_monthly = prepare_monthly(control_monthly, "control")
    treatment_monthly["scope_role"] = "treatment"
    control_monthly["scope_role"] = "control"
    monthly = pd.concat([treatment_monthly, control_monthly], ignore_index=True)

    monthly = monthly.drop(columns=["time_period"])
    data = data.merge(
        monthly,
        on=["scope_role", "repo_name_key", "time"],
        how="left",
        validate="one_to_one",
        indicator="monthly_merge_status",
    )
    if data["monthly_merge_status"].ne("both").any():
        examples = data.loc[
            data["monthly_merge_status"].ne("both"),
            ["scope_role", "repo_name", "time", "monthly_merge_status"],
        ].head(10).to_dict("records")
        raise ValueError(f"Paper panel rows missing from monthly inputs: {examples}")
    data = data.drop(columns=["monthly_merge_status"])

    scope_columns = [
        "scope_role",
        "repo_name_key",
        "paper_panel_rows",
        "event_yyyymm",
        "clone_available",
        "clone_path",
        "c02_clone_status",
        "c02_git_head_sha",
        "c02_failure_reason",
    ]
    data = data.merge(
        scope[scope_columns],
        on=["scope_role", "repo_name_key"],
        how="left",
        validate="many_to_one",
    )

    data["paper_ncloc"] = pd.to_numeric(data["ncloc"], errors="coerce")
    data["paper_panel_included"] = True
    data["history_candidate"] = data["clone_available"].astype(bool)
    data["latest_commit_monthly"] = data["latest_commit_monthly"].map(clean_text)
    data["role_order"] = data["scope_role"].map(ROLE_ORDER)
    data = data.sort_values(["role_order", "repo_name_key", "time_period"]).drop(columns=["role_order"])
    return data.reset_index(drop=True)


def load_history_timezone(name: str) -> ZoneInfo:
    """Load and validate the IANA timezone used for calendar-month boundaries."""

    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {name}") from exc


def month_boundary_details(month: pd.Period, history_timezone: ZoneInfo) -> dict[str, object]:
    """Return the exclusive next-month boundary in local time and UTC."""

    next_month_naive = (month + 1).start_time.to_pydatetime()
    boundary_local = next_month_naive.replace(tzinfo=history_timezone)
    boundary_utc = boundary_local.astimezone(timezone.utc)
    return {
        "boundary_local": boundary_local,
        "boundary_utc": boundary_utc,
        "boundary_epoch": int(boundary_utc.timestamp()),
    }


def timestamp_details(
    timestamp: Optional[int],
    month: pd.Period,
    history_timezone: ZoneInfo,
) -> dict[str, object]:
    """Build UTC/local timestamp fields and month-boundary diagnostics."""

    boundary = month_boundary_details(month, history_timezone)
    empty = {
        "timestamp_utc": "",
        "timestamp_local": "",
        "utc_month": "",
        "local_month": "",
        "local_month_matches_repo_month": False,
        "month_boundary_local": boundary["boundary_local"].isoformat(),
        "month_boundary_utc": boundary["boundary_utc"].isoformat(),
        "seconds_before_month_boundary": pd.NA,
        "after_month_end": False,
        "valid_under_utc_boundary": False,
        "valid_under_local_boundary": False,
        "timezone_boundary_classification_changed": False,
    }
    if timestamp is None:
        return empty

    utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    local_dt = utc_dt.astimezone(history_timezone)
    utc_month = utc_dt.strftime("%Y-%m")
    local_month = local_dt.strftime("%Y-%m")
    utc_boundary_epoch = int((month + 1).start_time.tz_localize("UTC").timestamp())
    local_boundary_epoch = int(boundary["boundary_epoch"])
    valid_utc = timestamp < utc_boundary_epoch
    valid_local = timestamp < local_boundary_epoch

    return {
        "timestamp_utc": utc_dt.isoformat(),
        "timestamp_local": local_dt.isoformat(),
        "utc_month": utc_month,
        "local_month": local_month,
        "local_month_matches_repo_month": local_month == str(month),
        "month_boundary_local": boundary["boundary_local"].isoformat(),
        "month_boundary_utc": boundary["boundary_utc"].isoformat(),
        "seconds_before_month_boundary": int(local_boundary_epoch - timestamp),
        "after_month_end": timestamp >= local_boundary_epoch,
        "valid_under_utc_boundary": valid_utc,
        "valid_under_local_boundary": valid_local,
        "timezone_boundary_classification_changed": valid_utc != valid_local,
    }


def validate_commit(
    clone_path: Path,
    sha: str,
    month: pd.Period,
    timeout_seconds: int,
    cache: dict[str, CommitCheck],
    history_timezone: ZoneInfo,
) -> CommitCheck:
    normalized = sha.casefold()
    if normalized not in cache:
        if not SHA_PATTERN.fullmatch(sha):
            cache[normalized] = CommitCheck(False, None, "invalid_commit_sha")
        else:
            exists_result = run_git(
                clone_path,
                ["cat-file", "-e", f"{sha}^{{commit}}"],
                timeout_seconds,
            )
            if exists_result.timed_out:
                cache[normalized] = CommitCheck(False, None, "commit_validation_timeout")
            elif exists_result.returncode != 0:
                cache[normalized] = CommitCheck(False, None, "commit_not_in_clone")
            else:
                timestamp_result = run_git(
                    clone_path,
                    ["show", "-s", "--format=%ct", sha],
                    timeout_seconds,
                )
                if timestamp_result.timed_out:
                    cache[normalized] = CommitCheck(True, None, "commit_timestamp_timeout")
                elif timestamp_result.returncode != 0 or not timestamp_result.stdout.isdigit():
                    cache[normalized] = CommitCheck(True, None, "commit_timestamp_unavailable")
                else:
                    cache[normalized] = CommitCheck(
                        True,
                        int(timestamp_result.stdout),
                        "commit_exists",
                    )

    check = cache[normalized]
    if not check.exists or check.timestamp is None:
        return check
    next_month_epoch = int(month_boundary_details(month, history_timezone)["boundary_epoch"])
    if check.timestamp >= next_month_epoch:
        return CommitCheck(True, check.timestamp, "commit_after_month_end")
    return check


def resolve_head_before_month_end(
    clone_path: Path,
    month: pd.Period,
    timeout_seconds: int,
    cache: dict[str, tuple[str, str]],
    history_timezone: ZoneInfo,
) -> tuple[str, str]:
    month_text = str(month)
    if month_text in cache:
        return cache[month_text]
    before = month_boundary_details(month, history_timezone)["boundary_utc"].isoformat()
    result = run_git(
        clone_path,
        ["rev-list", "-1", f"--before={before}", "HEAD"],
        timeout_seconds,
    )
    if result.timed_out:
        cache[month_text] = ("", "git_head_fallback_timeout")
    elif result.returncode != 0:
        cache[month_text] = ("", "git_head_fallback_failed")
    elif not result.stdout:
        cache[month_text] = ("", "no_head_commit_before_month_end")
    else:
        cache[month_text] = (result.stdout.splitlines()[0].strip(), "git_head_candidate_found")
    return cache[month_text]


def resolve_repository_rows(
    repo_rows: pd.DataFrame,
    timeout_seconds: int,
    allow_carry_forward: bool,
    allow_git_head_fallback: bool,
    history_timezone: ZoneInfo,
) -> pd.DataFrame:
    rows = repo_rows.sort_values("time_period").copy()
    clone_path = Path(clean_text(rows["clone_path"].iloc[0]))
    repo_name = clean_text(rows["repo_name"].iloc[0])
    scope_role = clean_text(rows["scope_role"].iloc[0])

    git_repo_result = run_git(clone_path, ["rev-parse", "--is-inside-work-tree"], timeout_seconds)
    path_is_valid_git = (
        clone_path.is_dir()
        and git_repo_result.returncode == 0
        and git_repo_result.stdout.casefold() == "true"
    )

    commit_cache: dict[str, CommitCheck] = {}
    month_cache: dict[str, tuple[str, str]] = {}
    prior_observed_sha = ""
    prior_observed_month: Optional[pd.Period] = None
    output_rows: list[dict[str, object]] = []

    for row in rows.itertuples(index=False):
        month: pd.Period = row.time_period
        original = clean_text(row.latest_commit_monthly)
        resolution_method = "unresolved"
        resolved_sha = ""
        resolution_source_month = ""
        months_since_observed_commit: object = pd.NA
        original_status = "blank"
        prior_status = "not_attempted"
        fallback_status = "not_attempted"
        resolved_timestamp: Optional[int] = None
        error_message = ""

        if not path_is_valid_git:
            resolution_method = "invalid_clone_path_or_git_repository"
            error_message = git_repo_result.stderr or "Clone path is not a valid Git work tree."
        else:
            if original:
                original_check = validate_commit(
                    clone_path,
                    original,
                    month,
                    timeout_seconds,
                    commit_cache,
                    history_timezone,
                )
                original_status = original_check.status
                if original_check.status == "commit_exists":
                    resolved_sha = original
                    resolution_method = "exact_monthly_commit"
                    resolution_source_month = str(month)
                    months_since_observed_commit = 0
                    resolved_timestamp = original_check.timestamp

            if (
                not resolved_sha
                and allow_carry_forward
                and prior_observed_sha
            ):
                prior_check = validate_commit(
                    clone_path,
                    prior_observed_sha,
                    month,
                    timeout_seconds,
                    commit_cache,
                    history_timezone,
                )
                prior_status = prior_check.status
                if prior_check.status == "commit_exists":
                    resolved_sha = prior_observed_sha
                    resolution_method = "carried_forward_prior_monthly_commit"
                    resolution_source_month = str(prior_observed_month) if prior_observed_month is not None else ""
                    if prior_observed_month is not None:
                        months_since_observed_commit = int(month.ordinal - prior_observed_month.ordinal)
                    resolved_timestamp = prior_check.timestamp

            if not resolved_sha and allow_git_head_fallback:
                fallback_sha, fallback_search_status = resolve_head_before_month_end(
                    clone_path,
                    month,
                    timeout_seconds,
                    month_cache,
                    history_timezone,
                )
                fallback_status = fallback_search_status
                if fallback_sha:
                    fallback_check = validate_commit(
                        clone_path,
                        fallback_sha,
                        month,
                        timeout_seconds,
                        commit_cache,
                        history_timezone,
                    )
                    fallback_status = fallback_check.status
                    if fallback_check.status == "commit_exists":
                        resolved_sha = fallback_sha
                        resolution_method = "git_head_before_month_end"
                        resolution_source_month = "git_history"
                        resolved_timestamp = fallback_check.timestamp

            if not resolved_sha and resolution_method == "unresolved":
                if not allow_git_head_fallback:
                    error_message = "Git HEAD fallback is disabled."
                elif fallback_status == "no_head_commit_before_month_end":
                    error_message = "No commit reachable from HEAD before the repo-month end."
                elif fallback_status.endswith("timeout"):
                    error_message = "Git command timed out during commit resolution."
                else:
                    error_message = "No valid historical commit could be resolved."

        if original:
            prior_observed_sha = original
            prior_observed_month = month

        snapshot_available = bool(resolved_sha)
        original_timestamp = None
        if original:
            cached_original = commit_cache.get(original.casefold())
            if cached_original is not None:
                original_timestamp = cached_original.timestamp
        original_details = timestamp_details(original_timestamp, month, history_timezone)
        resolved_details = timestamp_details(resolved_timestamp, month, history_timezone)

        output_rows.append(
            {
                "scope_role": scope_role,
                "repo_name": repo_name,
                "repo_name_key": repo_key(repo_name),
                "time": str(month),
                "clone_path": str(clone_path),
                "latest_commit_monthly": original,
                "resolved_commit": resolved_sha,
                "resolution_method": resolution_method,
                "resolution_source_month": resolution_source_month,
                "months_since_observed_commit": months_since_observed_commit,
                "history_timezone": str(history_timezone),
                "month_boundary_local": original_details["month_boundary_local"],
                "month_boundary_utc": original_details["month_boundary_utc"],
                "original_commit_validation_status": original_status,
                "original_commit_timestamp_utc": original_details["timestamp_utc"],
                "original_commit_timestamp_local": original_details["timestamp_local"],
                "original_commit_utc_month": original_details["utc_month"],
                "original_commit_local_month": original_details["local_month"],
                "original_commit_local_month_matches_repo_month": original_details["local_month_matches_repo_month"],
                "original_commit_seconds_before_month_boundary": original_details["seconds_before_month_boundary"],
                "original_commit_valid_under_utc_boundary": original_details["valid_under_utc_boundary"],
                "original_commit_valid_under_local_boundary": original_details["valid_under_local_boundary"],
                "timezone_boundary_classification_changed": original_details["timezone_boundary_classification_changed"],
                "prior_commit_validation_status": prior_status,
                "git_head_fallback_status": fallback_status,
                "resolved_commit_timestamp_utc": resolved_details["timestamp_utc"],
                "resolved_commit_timestamp_local": resolved_details["timestamp_local"],
                "resolved_commit_local_month": resolved_details["local_month"],
                "resolved_commit_seconds_before_month_boundary": resolved_details["seconds_before_month_boundary"],
                "resolved_commit_after_month_end": resolved_details["after_month_end"],
                "snapshot_available": snapshot_available,
                "repo_snapshot_key": (
                    make_snapshot_key(scope_role, repo_name, resolved_sha)
                    if resolved_sha
                    else ""
                ),
                "resolution_error_message": error_message,
                "clone_path_valid_git": path_is_valid_git,
            }
        )

    return pd.DataFrame(output_rows)


def resolve_history(
    paper_panel: pd.DataFrame,
    workers: int,
    timeout_seconds: int,
    allow_carry_forward: bool,
    allow_git_head_fallback: bool,
    history_timezone: ZoneInfo,
) -> pd.DataFrame:
    candidates = paper_panel[paper_panel["history_candidate"]].copy()
    groups = [group.copy() for _, group in candidates.groupby(["scope_role", "repo_name_key"], sort=True)]
    logging.info(
        "Resolving historical commits for %d repo-month rows across %d repositories using %d workers",
        len(candidates),
        len(groups),
        workers,
    )

    results: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                resolve_repository_rows,
                group,
                timeout_seconds,
                allow_carry_forward,
                allow_git_head_fallback,
                history_timezone,
            ): clean_text(group["repo_name"].iloc[0])
            for group in groups
        }
        completed = 0
        for future in as_completed(future_map):
            repo_name = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                raise RuntimeError(f"History resolution failed for {repo_name}: {exc}") from exc
            completed += 1
            if completed % 25 == 0 or completed == len(groups):
                logging.info("History resolution progress: %d/%d repositories", completed, len(groups))

    if not results:
        return pd.DataFrame()
    history = pd.concat(results, ignore_index=True)
    history["role_order"] = history["scope_role"].map(ROLE_ORDER)
    history = history.sort_values(["role_order", "repo_name_key", "time"]).drop(columns=["role_order"])
    return history.reset_index(drop=True)


def build_resolution_audit(history: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "scope_role",
        "repo_name",
        "time",
        "latest_commit_monthly",
        "resolved_commit",
        "resolution_method",
        "resolution_source_month",
        "months_since_observed_commit",
        "history_timezone",
        "month_boundary_local",
        "month_boundary_utc",
        "original_commit_validation_status",
        "original_commit_timestamp_utc",
        "original_commit_timestamp_local",
        "original_commit_utc_month",
        "original_commit_local_month",
        "original_commit_local_month_matches_repo_month",
        "original_commit_seconds_before_month_boundary",
        "original_commit_valid_under_utc_boundary",
        "original_commit_valid_under_local_boundary",
        "timezone_boundary_classification_changed",
        "prior_commit_validation_status",
        "git_head_fallback_status",
        "resolved_commit_timestamp_utc",
        "resolved_commit_timestamp_local",
        "resolved_commit_local_month",
        "resolved_commit_seconds_before_month_boundary",
        "resolved_commit_after_month_end",
        "snapshot_available",
        "repo_snapshot_key",
        "clone_path_valid_git",
        "resolution_error_message",
    ]
    return history[columns].copy()


def build_unique_snapshot_manifest(history: pd.DataFrame) -> pd.DataFrame:
    resolved = history[history["snapshot_available"]].copy()
    if resolved.empty:
        return pd.DataFrame(
            columns=[
                "repo_snapshot_key",
                "scope_role",
                "repo_name",
                "repo_name_key",
                "clone_path",
                "resolved_commit",
                "resolved_commit_timestamp_utc",
                "resolved_commit_timestamp_local",
                "history_timezone",
                "first_repo_month",
                "last_repo_month",
                "repo_month_count",
                "resolution_methods",
            ]
        )

    rows: list[dict[str, object]] = []
    for snapshot_key, group in resolved.groupby("repo_snapshot_key", sort=True):
        rows.append(
            {
                "repo_snapshot_key": snapshot_key,
                "scope_role": clean_text(group["scope_role"].iloc[0]),
                "repo_name": clean_text(group["repo_name"].iloc[0]),
                "repo_name_key": clean_text(group["repo_name_key"].iloc[0]),
                "clone_path": clean_text(group["clone_path"].iloc[0]),
                "resolved_commit": clean_text(group["resolved_commit"].iloc[0]),
                "resolved_commit_timestamp_utc": clean_text(group["resolved_commit_timestamp_utc"].iloc[0]),
                "resolved_commit_timestamp_local": clean_text(group["resolved_commit_timestamp_local"].iloc[0]),
                "history_timezone": clean_text(group["history_timezone"].iloc[0]),
                "first_repo_month": group["time"].min(),
                "last_repo_month": group["time"].max(),
                "repo_month_count": int(len(group)),
                "resolution_methods": ";".join(sorted(set(group["resolution_method"].map(clean_text)))),
            }
        )
    result = pd.DataFrame(rows)
    result["role_order"] = result["scope_role"].map(ROLE_ORDER)
    return result.sort_values(["role_order", "repo_name_key", "first_repo_month"]).drop(columns=["role_order"]).reset_index(drop=True)


def support_row(
    dimension: str,
    value: str,
    role: str,
    rows: pd.DataFrame,
) -> dict[str, object]:
    return {
        "support_dimension": dimension,
        "support_value": value,
        "scope_role": role,
        "repository_count": int(rows["repo_name_key"].nunique()),
        "repo_month_count": int(len(rows)),
        "clone_available_repo_months": int(rows["clone_available"].sum()),
        "snapshot_resolved_repo_months": int(rows.get("snapshot_available", pd.Series(False, index=rows.index)).fillna(False).sum()),
        "snapshot_unresolved_repo_months": int(
            (rows["clone_available"] & ~rows.get("snapshot_available", pd.Series(False, index=rows.index)).fillna(False)).sum()
        ),
    }


def build_support(enriched_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role in ["treatment", "control", "all"]:
        subset = enriched_panel if role == "all" else enriched_panel[enriched_panel["scope_role"].eq(role)]
        rows.append(support_row("overall", "all", role, subset))

    for time, group in enriched_panel.groupby("time", sort=True):
        for role in ["treatment", "control", "all"]:
            subset = group if role == "all" else group[group["scope_role"].eq(role)]
            rows.append(support_row("calendar_month", str(time), role, subset))

    treatment = enriched_panel[enriched_panel["scope_role"].eq("treatment")].copy()
    treatment["event_value"] = treatment["event"].map(clean_text)
    for event, group in treatment.groupby("event_value", sort=True):
        rows.append(support_row("treatment_cohort", event, "treatment", group))

    treatment["event_time_value"] = pd.to_numeric(treatment["time_to_event"], errors="coerce").astype("Int64")
    for event_time, group in treatment.dropna(subset=["event_time_value"]).groupby("event_time_value", sort=True):
        rows.append(support_row("treatment_event_time", str(int(event_time)), "treatment", group))

    available = enriched_panel[enriched_panel["clone_available"]].copy()
    for method, group in available.groupby("resolution_method", dropna=False, sort=True):
        rows.append(support_row("resolution_method", clean_text(method) or "blank", "all", group))

    return pd.DataFrame(rows)


def qc_record(
    name: str,
    observed: object,
    expected: object,
    severity: str,
    passed: bool,
    note: str,
) -> dict[str, object]:
    return {
        "qc_check": name,
        "observed": observed,
        "expected": expected,
        "severity": severity,
        "passed": bool(passed),
        "note": note,
    }


def build_qc(
    args: argparse.Namespace,
    scope: pd.DataFrame,
    paper_panel: pd.DataFrame,
    history: pd.DataFrame,
    unique_snapshots: pd.DataFrame,
) -> pd.DataFrame:
    treatment_scope = scope[scope["scope_role"].eq("treatment")]
    control_scope = scope[scope["scope_role"].eq("control")]
    treatment_rows = paper_panel[paper_panel["scope_role"].eq("treatment")]
    control_rows = paper_panel[paper_panel["scope_role"].eq("control")]
    available_scope = scope[scope["clone_available"]]
    unavailable_scope = scope[~scope["clone_available"]]
    unavailable_rows = paper_panel[~paper_panel["clone_available"]]
    history_candidates = paper_panel[paper_panel["clone_available"]]

    checks: list[dict[str, object]] = []

    expected_pairs = [
        ("paper_treatment_repositories", treatment_scope["repo_name_key"].nunique(), args.expected_paper_treatment_repos),
        ("paper_control_repositories", control_scope["repo_name_key"].nunique(), args.expected_paper_control_repos),
        ("paper_treatment_repo_months", len(treatment_rows), args.expected_paper_treatment_rows),
        ("paper_control_repo_months", len(control_rows), args.expected_paper_control_rows),
        ("paper_panel_repo_months", len(paper_panel), args.expected_paper_panel_rows),
        ("clone_available_treatment_repositories", available_scope.loc[available_scope["scope_role"].eq("treatment"), "repo_name_key"].nunique(), args.expected_clone_available_treatment_repos),
        ("clone_available_control_repositories", available_scope.loc[available_scope["scope_role"].eq("control"), "repo_name_key"].nunique(), args.expected_clone_available_control_repos),
        ("clone_available_repositories", available_scope["repo_name_key"].nunique(), args.expected_clone_available_repos),
        ("clone_unavailable_repositories", unavailable_scope["repo_name_key"].nunique(), args.expected_clone_unavailable_repos),
        ("clone_unavailable_repo_months", len(unavailable_rows), args.expected_clone_unavailable_rows),
        ("history_candidate_repo_months", len(history_candidates), args.expected_history_candidate_rows),
    ]
    for name, observed, expected in expected_pairs:
        severity = "hard" if args.strict_expected_counts else "warning"
        checks.append(
            qc_record(
                name,
                observed,
                expected,
                severity,
                observed == expected,
                "Expected counts are based on the completed C01/C02 paper-scope run.",
            )
        )

    structural_checks = [
        (
            "duplicate_paper_repo_month_keys",
            int(paper_panel.duplicated(["scope_role", "repo_name_key", "time"]).sum()),
            0,
            "hard",
            "Paper panel must contain one row per role/repository/month.",
        ),
        (
            "history_row_count_matches_candidates",
            len(history),
            len(history_candidates),
            "hard",
            "Every clone-available paper row must receive a history-resolution row.",
        ),
        (
            "duplicate_history_repo_month_keys",
            int(history.duplicated(["scope_role", "repo_name_key", "time"]).sum()),
            0,
            "hard",
            "History output must contain one row per clone-available repository/month.",
        ),
        (
            "resolved_commits_after_month_end",
            int(history["resolved_commit_after_month_end"].fillna(False).sum()),
            0,
            "hard",
            "A historical snapshot commit cannot be committed after its repo-month end.",
        ),
        (
            "duplicate_unique_snapshot_keys",
            int(unique_snapshots["repo_snapshot_key"].duplicated().sum()) if not unique_snapshots.empty else 0,
            0,
            "hard",
            "Unique snapshot manifest keys must be unique.",
        ),
        (
            "resolved_repo_months_match_snapshot_weights",
            int(history["snapshot_available"].fillna(False).sum()),
            int(unique_snapshots["repo_month_count"].sum()) if not unique_snapshots.empty else 0,
            "hard",
            "Unique snapshot repo-month weights must reconstruct resolved history rows.",
        ),
        (
            "c02_success_repositories_with_invalid_clone_path",
            int(
                history.loc[
                    ~history["clone_path_valid_git"].astype("boolean").fillna(False),
                    "repo_name_key",
                ].nunique()
            ),
            0,
            "hard",
            "C02-success repositories must remain valid local Git work trees.",
        ),
    ]
    for name, observed, expected, severity, note in structural_checks:
        checks.append(qc_record(name, observed, expected, severity, observed == expected, note))

    timezone_changed_count = int(history["timezone_boundary_classification_changed"].fillna(False).sum())
    checks.append(
        qc_record(
            "monthly_commits_reclassified_by_local_timezone_boundary",
            timezone_changed_count,
            "informational",
            "info",
            True,
            "Rows where UTC-midnight and configured local-midnight boundaries classify the monthly commit differently.",
        )
    )

    local_month_mismatch_count = int(
        (
            history["original_commit_timestamp_local"].ne("")
            & history["original_commit_valid_under_local_boundary"].fillna(False)
            & ~history["original_commit_local_month_matches_repo_month"].fillna(False)
        ).sum()
    )
    checks.append(
        qc_record(
            "locally_valid_monthly_commits_with_month_mismatch",
            local_month_mismatch_count,
            0,
            "warning",
            local_month_mismatch_count == 0,
            "A monthly latest_commit should normally belong to its repo-month in the configured timezone.",
        )
    )

    unresolved_count = int((~history["snapshot_available"].fillna(False)).sum())
    checks.append(
        qc_record(
            "unresolved_history_repo_months",
            unresolved_count,
            0,
            "hard" if args.fail_on_unresolved else "warning",
            unresolved_count == 0,
            "Unresolved rows are retained for audit and excluded from the unique snapshot manifest.",
        )
    )

    blank_monthly = int(paper_panel["latest_commit_monthly"].eq("").sum())
    checks.append(
        qc_record(
            "blank_monthly_latest_commit_rows",
            blank_monthly,
            "informational",
            "info",
            True,
            "Blank latest_commit values are expected in months with no recorded commit activity.",
        )
    )
    return pd.DataFrame(checks)


def append_summary(rows: list[dict[str, object]], section: str, metric: str, value: object, note: str = "") -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def build_summary(
    scope: pd.DataFrame,
    paper_panel: pd.DataFrame,
    history: pd.DataFrame,
    unique_snapshots: pd.DataFrame,
    qc: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    append_summary(rows, "paper_scope", "treatment_repositories", int(scope.loc[scope["scope_role"].eq("treatment"), "repo_name_key"].nunique()))
    append_summary(rows, "paper_scope", "control_repositories", int(scope.loc[scope["scope_role"].eq("control"), "repo_name_key"].nunique()))
    append_summary(rows, "paper_scope", "repo_month_rows", len(paper_panel))
    append_summary(rows, "clone_scope", "available_repositories", int(scope.loc[scope["clone_available"], "repo_name_key"].nunique()))
    append_summary(rows, "clone_scope", "unavailable_repositories", int(scope.loc[~scope["clone_available"], "repo_name_key"].nunique()))
    append_summary(rows, "clone_scope", "available_repo_month_rows", int(paper_panel["clone_available"].sum()))
    append_summary(rows, "clone_scope", "unavailable_repo_month_rows", int((~paper_panel["clone_available"]).sum()))
    append_summary(rows, "history", "candidate_repo_month_rows", len(history))
    append_summary(rows, "history", "resolved_repo_month_rows", int(history["snapshot_available"].sum()))
    append_summary(rows, "history", "unresolved_repo_month_rows", int((~history["snapshot_available"]).sum()))
    append_summary(rows, "history", "unique_resolved_snapshots", len(unique_snapshots))
    append_summary(rows, "configuration", "history_timezone", clean_text(history["history_timezone"].iloc[0]) if not history.empty else "")
    append_summary(rows, "timezone", "boundary_reclassified_monthly_commits", int(history["timezone_boundary_classification_changed"].fillna(False).sum()))
    for method, count in history["resolution_method"].value_counts(dropna=False).sort_index().items():
        append_summary(rows, "resolution_method", clean_text(method) or "blank", int(count))
    append_summary(rows, "qc", "hard_failures", int(((qc["severity"] == "hard") & (~qc["passed"])).sum()))
    append_summary(rows, "qc", "warnings", int(((qc["severity"] == "warning") & (~qc["passed"])).sum()))
    return pd.DataFrame(rows)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logging.info("Wrote %d rows to %s", len(df), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    validate_args(args)
    history_timezone = load_history_timezone(args.history_timezone)

    logging.info("Reading C01 treatment scope: %s", args.treatment_repos_file)
    logging.info("Reading C01 control scope: %s", args.control_repos_file)
    logging.info("Reading C02 clone status: %s", args.clone_status_file)
    treatment, control, manifest, status, panel, treatment_monthly, control_monthly = read_inputs(args)

    scope = build_scope(treatment, control, manifest, status)
    paper_panel = build_paper_panel(panel, scope, treatment_monthly, control_monthly)

    history = resolve_history(
        paper_panel,
        workers=args.workers,
        timeout_seconds=args.git_timeout_seconds,
        allow_carry_forward=bool(args.allow_carry_forward),
        allow_git_head_fallback=bool(args.allow_git_head_fallback),
        history_timezone=history_timezone,
    )
    resolution_audit = build_resolution_audit(history)
    timezone_audit = resolution_audit[
        resolution_audit["timezone_boundary_classification_changed"].fillna(False)
    ].copy()
    unique_snapshots = build_unique_snapshot_manifest(history)
    unresolved = history[~history["snapshot_available"]].copy()
    clone_unavailable = paper_panel[~paper_panel["clone_available"]].copy()

    history_merge_columns = [
        "scope_role",
        "repo_name_key",
        "time",
        "resolved_commit",
        "resolution_method",
        "resolution_source_month",
        "months_since_observed_commit",
        "history_timezone",
        "month_boundary_local",
        "month_boundary_utc",
        "original_commit_timestamp_utc",
        "original_commit_timestamp_local",
        "original_commit_utc_month",
        "original_commit_local_month",
        "original_commit_local_month_matches_repo_month",
        "timezone_boundary_classification_changed",
        "resolved_commit_timestamp_utc",
        "resolved_commit_timestamp_local",
        "resolved_commit_local_month",
        "resolved_commit_after_month_end",
        "snapshot_available",
        "repo_snapshot_key",
        "clone_path_valid_git",
        "resolution_error_message",
    ]
    enriched_panel = paper_panel.merge(
        history[history_merge_columns],
        on=["scope_role", "repo_name_key", "time"],
        how="left",
        validate="one_to_one",
    )
    enriched_panel["snapshot_available"] = enriched_panel["snapshot_available"].astype("boolean").fillna(False).astype(bool)
    enriched_panel.loc[~enriched_panel["clone_available"], "resolution_method"] = "clone_unavailable"
    enriched_panel.loc[~enriched_panel["clone_available"], "resolution_error_message"] = enriched_panel.loc[
        ~enriched_panel["clone_available"], "c02_failure_reason"
    ].map(lambda value: clean_text(value) or "C02 clone unavailable")

    support = build_support(enriched_panel)
    qc = build_qc(args, scope, paper_panel, history, unique_snapshots)
    summary = build_summary(scope, paper_panel, history, unique_snapshots, qc)

    paper_output_columns = [
        "scope_role",
        "repo_name",
        "repo_name_key",
        "time",
        "is_treatment",
        "event",
        "post_event",
        "time_to_event",
        "commits",
        "lines_added",
        "lines_removed",
        "contributors",
        "stars",
        "issues",
        "issue_comments",
        "age",
        "paper_ncloc",
        "bugs",
        "vulnerabilities",
        "code_smells",
        "duplicated_lines_density",
        "comment_lines_density",
        "cognitive_complexity",
        "technical_debt",
        "num_dependencies_total",
        "num_vulnerable_dependencies",
        "average_technical_lag",
        "dataset_source",
        "other_agents",
        "high_confidence",
        "latest_commit_monthly",
        "clone_available",
        "clone_path",
        "c02_clone_status",
        "c02_git_head_sha",
        "c02_failure_reason",
        "history_candidate",
        "resolved_commit",
        "resolution_method",
        "resolution_source_month",
        "months_since_observed_commit",
        "history_timezone",
        "month_boundary_local",
        "month_boundary_utc",
        "original_commit_timestamp_utc",
        "original_commit_timestamp_local",
        "original_commit_utc_month",
        "original_commit_local_month",
        "original_commit_local_month_matches_repo_month",
        "timezone_boundary_classification_changed",
        "resolved_commit_timestamp_utc",
        "resolved_commit_timestamp_local",
        "resolved_commit_local_month",
        "resolved_commit_after_month_end",
        "snapshot_available",
        "repo_snapshot_key",
        "clone_path_valid_git",
        "resolution_error_message",
    ]
    paper_panel_output = enriched_panel[paper_output_columns].copy()

    write_csv(paper_panel_output, args.paper_panel_output)
    write_csv(history, args.history_output)
    write_csv(unique_snapshots, args.unique_snapshot_output)
    write_csv(resolution_audit, args.resolution_audit_output)
    write_csv(timezone_audit, args.timezone_audit_output)
    write_csv(unresolved, args.unresolved_output)
    write_csv(clone_unavailable, args.clone_unavailable_output)
    write_csv(support, args.support_output)
    write_csv(qc, args.qc_output)
    write_csv(summary, args.summary_output)

    hard_failures = int(((qc["severity"] == "hard") & (~qc["passed"])).sum())
    warnings = int(((qc["severity"] == "warning") & (~qc["passed"])).sum())
    logging.info(
        "Completed run-x-c03-v3: paper rows=%d; history candidates=%d; resolved=%d; "
        "unresolved=%d; unique snapshots=%d; hard failures=%d; warnings=%d",
        len(paper_panel),
        len(history),
        int(history["snapshot_available"].sum()),
        int((~history["snapshot_available"]).sum()),
        len(unique_snapshots),
        hard_failures,
        warnings,
    )

    if hard_failures:
        logging.error("C03 produced %d hard QC failure(s).", hard_failures)
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("run-x-c03-v3 failed: %s", exc)
        raise SystemExit(1)
