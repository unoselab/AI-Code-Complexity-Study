#!/usr/bin/env python3
"""
Recover historical Git commit objects referenced by run-x-a03-v2 outputs.

The input eligibility CSV may contain repository-month rows with
scan_status=commit_not_found. This script groups those rows by repository and
unique commit SHA, records the current local/remote Git state, and attempts
non-destructive recovery without checking out or resetting the working tree.

Recovery stages:
1. Verify whether each commit already exists locally.
2. If the clone is shallow, fetch the remaining history with --unshallow.
3. Fetch all configured remotes and tags without pruning existing refs.
4. Fetch all origin branch and tag refs explicitly.
5. Attempt a direct fetch of each still-missing SHA.
6. Optionally fetch GitHub-style pull-request head refs.

The script never deletes refs, runs git gc, checks out branches, resets files,
or modifies the working tree. Missing objects that cannot be recovered remain
explicitly unresolved.

Inputs:
- run-x-a03-v2 repository-month Python eligibility CSV

Outputs:
- one row per unique missing commit and its recovery result
- one row per affected repository with remote/ref audit details
- unresolved repository-month rows after recovery
- compact QC summary
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit_effective",
    "clone_path",
    "scan_status",
}
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
GITHUB_HTTPS_PATTERN = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", re.IGNORECASE
)
GITHUB_SSH_PATTERN = re.compile(
    r"^(?:ssh://git@github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass
class CommitState:
    repo_name: str
    clone_path: Path
    sha: str
    affected_month_count: int
    affected_months: str
    commit_resolution_types: str
    exists_before: int = 0
    after_unshallow: int = 0
    after_fetch_all: int = 0
    after_explicit_refs: int = 0
    after_direct_sha_fetch: int = 0
    after_pr_fetch: int = 0
    final_exists: int = 0
    recovery_stage: str = "unresolved"
    object_type: str = ""
    commit_date: str = ""
    commit_subject: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit and recover local Git commit objects referenced by "
            "run-x-a03-v2 commit_not_found rows."
        )
    )
    parser.add_argument("--eligibility-file", required=True, type=Path)
    parser.add_argument("--recovery-status-output", required=True, type=Path)
    parser.add_argument("--repository-output", required=True, type=Path)
    parser.add_argument("--unresolved-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--git-timeout-seconds", type=int, default=600)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit local and remote state without executing fetch commands.",
    )
    parser.add_argument(
        "--fetch-pr-refs",
        action="store_true",
        help=(
            "After normal recovery stages, fetch GitHub pull-request head refs. "
            "This may transfer many refs and is disabled by default."
        ),
    )
    parser.add_argument(
        "--skip-direct-sha-fetch",
        action="store_true",
        help="Do not attempt `git fetch origin <sha>` for unresolved commits.",
    )
    parser.add_argument(
        "--fail-on-unresolved",
        action="store_true",
        help="Return exit code 2 when any unique commit remains unresolved.",
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


def truncate(value: str, limit: int = 2000) -> str:
    text = clean_text(value).replace("\x00", "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(sorted(missing))}")


def validate_args(args: argparse.Namespace) -> None:
    if not args.eligibility_file.is_file():
        raise FileNotFoundError(f"Eligibility input not found: {args.eligibility_file}")
    if args.git_timeout_seconds <= 0:
        raise ValueError("git-timeout-seconds must be positive")


def run_command(command: list[str], timeout_seconds: int) -> CommandResult:
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
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(
            returncode=124,
            stdout=stdout.strip(),
            stderr=(stderr.strip() or f"Command timed out after {timeout_seconds} seconds."),
            timed_out=True,
        )


def run_git(clone_path: Path, args: list[str], timeout_seconds: int) -> CommandResult:
    return run_command(["git", "-C", str(clone_path), *args], timeout_seconds)


def is_git_repository(clone_path: Path, timeout_seconds: int) -> bool:
    if not clone_path.is_dir():
        return False
    result = run_git(clone_path, ["rev-parse", "--is-inside-work-tree"], timeout_seconds)
    return result.returncode == 0 and result.stdout.casefold() == "true"


def commit_exists(clone_path: Path, sha: str, timeout_seconds: int) -> bool:
    result = run_git(clone_path, ["cat-file", "-e", f"{sha}^{{commit}}"], timeout_seconds)
    return result.returncode == 0


def parse_github_repo_name(url: str) -> str:
    text = clean_text(url)
    for pattern in (GITHUB_HTTPS_PATTERN, GITHUB_SSH_PATTERN):
        match = pattern.match(text)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return ""


def parse_remote_head(stdout: str) -> tuple[str, str]:
    head_ref = ""
    head_sha = ""
    for line in stdout.splitlines():
        if line.startswith("ref:") and line.endswith("\tHEAD"):
            head_ref = line.split("\t", 1)[0].replace("ref:", "", 1).strip()
        elif line.endswith("\tHEAD"):
            head_sha = line.split("\t", 1)[0].strip()
    return head_ref, head_sha


def get_commit_metadata(clone_path: Path, sha: str, timeout_seconds: int) -> tuple[str, str, str]:
    type_result = run_git(clone_path, ["cat-file", "-t", sha], timeout_seconds)
    show_result = run_git(
        clone_path,
        ["show", "-s", "--format=%cI%x00%s", sha],
        timeout_seconds,
    )
    object_type = type_result.stdout if type_result.returncode == 0 else ""
    commit_date = ""
    commit_subject = ""
    if show_result.returncode == 0:
        parts = show_result.stdout.split("\x00", 1)
        commit_date = parts[0].strip()
        commit_subject = parts[1].strip() if len(parts) > 1 else ""
    return object_type, commit_date, commit_subject


def read_missing_rows(path: Path) -> pd.DataFrame:
    dtype_columns = [
        "dataset_source",
        "repo_name",
        "month",
        "latest_commit_original",
        "latest_commit_effective",
        "commit_resolution",
        "clone_path",
        "scan_status",
        "error_message",
    ]
    df = pd.read_csv(
        path,
        dtype={column: "string" for column in dtype_columns},
        low_memory=False,
    )
    require_columns(df, REQUIRED_COLUMNS, "eligibility CSV")
    missing = df[df["scan_status"].fillna("").eq("commit_not_found")].copy()
    if missing.empty:
        return missing

    for column in dtype_columns:
        if column in missing.columns:
            missing[column] = missing[column].fillna("").astype(str).str.strip()

    invalid_sha = ~missing["latest_commit_effective"].map(
        lambda value: bool(SHA_PATTERN.fullmatch(value))
    )
    if invalid_sha.any():
        examples = missing.loc[invalid_sha, "latest_commit_effective"].head(5).tolist()
        raise ValueError(f"Invalid missing commit SHA values: {examples}")

    empty_clone_path = missing["clone_path"].eq("")
    if empty_clone_path.any():
        examples = missing.loc[empty_clone_path, "repo_name"].head(5).tolist()
        raise ValueError(f"Missing clone paths for commit_not_found rows: {examples}")
    return missing


def build_commit_states(missing_rows: pd.DataFrame) -> dict[tuple[str, str], CommitState]:
    states: dict[tuple[str, str], CommitState] = {}
    if missing_rows.empty:
        return states

    grouped = missing_rows.groupby(
        ["repo_name", "clone_path", "latest_commit_effective"],
        sort=True,
        dropna=False,
    )
    for (repo_name, clone_path, sha), group in grouped:
        months = sorted({clean_text(value) for value in group["month"] if clean_text(value)})
        resolution_types = sorted(
            {
                clean_text(value)
                for value in group.get("commit_resolution", pd.Series(dtype="string"))
                if clean_text(value)
            }
        )
        states[(clean_text(repo_name), clean_text(sha))] = CommitState(
            repo_name=clean_text(repo_name),
            clone_path=Path(clean_text(clone_path)),
            sha=clean_text(sha),
            affected_month_count=len(group),
            affected_months=";".join(months),
            commit_resolution_types=";".join(resolution_types),
        )
    return states


def mark_stage(
    repo_states: list[CommitState],
    attribute: str,
    stage_name: str,
    timeout_seconds: int,
) -> int:
    recovered = 0
    for state in repo_states:
        exists = commit_exists(state.clone_path, state.sha, timeout_seconds)
        setattr(state, attribute, int(exists))
        if exists and not state.final_exists:
            state.final_exists = 1
            state.recovery_stage = stage_name
            recovered += 1
    return recovered


def repository_audit_base(repo_name: str, clone_path: Path, timeout_seconds: int) -> dict[str, object]:
    clone_exists = int(clone_path.is_dir())
    git_valid = int(is_git_repository(clone_path, timeout_seconds)) if clone_exists else 0
    record: dict[str, object] = {
        "repo_name": repo_name,
        "clone_path": str(clone_path),
        "clone_exists": clone_exists,
        "is_git_repository": git_valid,
        "configured_origin_url": "",
        "origin_repo_name": "",
        "origin_name_matches_input": "",
        "local_head_sha": "",
        "is_shallow_before": "",
        "partial_clone_filter": "",
        "remote_accessible": 0,
        "remote_head_ref": "",
        "remote_head_sha": "",
        "remote_check_stderr": "",
        "missing_unique_commits": 0,
        "already_available_before": 0,
        "recovered_unique_commits": 0,
        "unresolved_unique_commits": 0,
        "unshallow_returncode": "",
        "unshallow_stderr": "",
        "fetch_all_returncode": "",
        "fetch_all_stderr": "",
        "explicit_refs_returncode": "",
        "explicit_refs_stderr": "",
        "direct_sha_fetch_attempts": 0,
        "direct_sha_fetch_failures": 0,
        "direct_sha_fetch_error_samples": "",
        "pr_fetch_returncode": "",
        "pr_fetch_stderr": "",
    }
    if not git_valid:
        return record

    origin = run_git(clone_path, ["remote", "get-url", "origin"], timeout_seconds)
    record["configured_origin_url"] = origin.stdout if origin.returncode == 0 else ""
    origin_repo_name = parse_github_repo_name(record["configured_origin_url"])
    record["origin_repo_name"] = origin_repo_name
    if origin_repo_name:
        record["origin_name_matches_input"] = int(origin_repo_name.casefold() == repo_name.casefold())

    head = run_git(clone_path, ["rev-parse", "HEAD"], timeout_seconds)
    record["local_head_sha"] = head.stdout if head.returncode == 0 else ""

    shallow = run_git(clone_path, ["rev-parse", "--is-shallow-repository"], timeout_seconds)
    record["is_shallow_before"] = shallow.stdout if shallow.returncode == 0 else ""

    partial = run_git(clone_path, ["config", "--get", "remote.origin.partialclonefilter"], timeout_seconds)
    record["partial_clone_filter"] = partial.stdout if partial.returncode == 0 else ""

    remote = run_git(clone_path, ["ls-remote", "--symref", "origin", "HEAD"], timeout_seconds)
    record["remote_accessible"] = int(remote.returncode == 0)
    remote_head_ref, remote_head_sha = parse_remote_head(remote.stdout)
    record["remote_head_ref"] = remote_head_ref
    record["remote_head_sha"] = remote_head_sha
    record["remote_check_stderr"] = truncate(remote.stderr)
    return record


def process_repository(
    repo_name: str,
    repo_states: list[CommitState],
    *,
    timeout_seconds: int,
    dry_run: bool,
    fetch_pr_refs: bool,
    skip_direct_sha_fetch: bool,
) -> dict[str, object]:
    clone_paths = {state.clone_path for state in repo_states}
    if len(clone_paths) != 1:
        raise ValueError(f"Repository has inconsistent clone paths: {repo_name}: {sorted(map(str, clone_paths))}")
    clone_path = next(iter(clone_paths))
    audit = repository_audit_base(repo_name, clone_path, timeout_seconds)
    audit["missing_unique_commits"] = len(repo_states)

    if not audit["is_git_repository"]:
        for state in repo_states:
            state.recovery_stage = "invalid_or_missing_clone"
        audit["unresolved_unique_commits"] = len(repo_states)
        return audit

    already_available = mark_stage(
        repo_states,
        "exists_before",
        "already_available",
        timeout_seconds,
    )
    audit["already_available_before"] = already_available

    if dry_run:
        for state in repo_states:
            state.after_unshallow = state.exists_before
            state.after_fetch_all = state.exists_before
            state.after_explicit_refs = state.exists_before
            state.after_direct_sha_fetch = state.exists_before
            state.after_pr_fetch = state.exists_before
            state.final_exists = state.exists_before
            if not state.final_exists:
                state.recovery_stage = "dry_run_unresolved"
        audit["recovered_unique_commits"] = 0
        audit["unresolved_unique_commits"] = sum(not state.final_exists for state in repo_states)
        return audit

    unresolved = [state for state in repo_states if not state.final_exists]

    if unresolved and str(audit["is_shallow_before"]).casefold() == "true":
        result = run_git(clone_path, ["fetch", "--unshallow", "--tags", "origin"], timeout_seconds)
        audit["unshallow_returncode"] = result.returncode
        audit["unshallow_stderr"] = truncate(result.stderr)
    mark_stage(repo_states, "after_unshallow", "unshallow", timeout_seconds)

    unresolved = [state for state in repo_states if not state.final_exists]
    if unresolved:
        result = run_git(clone_path, ["fetch", "--all", "--tags", "--force"], timeout_seconds)
        audit["fetch_all_returncode"] = result.returncode
        audit["fetch_all_stderr"] = truncate(result.stderr)
    mark_stage(repo_states, "after_fetch_all", "fetch_all", timeout_seconds)

    unresolved = [state for state in repo_states if not state.final_exists]
    if unresolved:
        result = run_git(
            clone_path,
            [
                "fetch",
                "--force",
                "origin",
                "+refs/heads/*:refs/remotes/origin/*",
                "+refs/tags/*:refs/tags/*",
            ],
            timeout_seconds,
        )
        audit["explicit_refs_returncode"] = result.returncode
        audit["explicit_refs_stderr"] = truncate(result.stderr)
    mark_stage(repo_states, "after_explicit_refs", "explicit_refs", timeout_seconds)

    unresolved = [state for state in repo_states if not state.final_exists]
    direct_errors: list[str] = []
    if unresolved and not skip_direct_sha_fetch:
        for state in unresolved:
            result = run_git(
                clone_path,
                ["fetch", "--no-tags", "origin", state.sha],
                timeout_seconds,
            )
            audit["direct_sha_fetch_attempts"] = int(audit["direct_sha_fetch_attempts"]) + 1
            if result.returncode != 0:
                audit["direct_sha_fetch_failures"] = int(audit["direct_sha_fetch_failures"]) + 1
                if len(direct_errors) < 5:
                    direct_errors.append(f"{state.sha}: {truncate(result.stderr, 500)}")
            if commit_exists(clone_path, state.sha, timeout_seconds) and not state.final_exists:
                state.final_exists = 1
                state.recovery_stage = "direct_sha_fetch"
        audit["direct_sha_fetch_error_samples"] = " | ".join(direct_errors)
    for state in repo_states:
        state.after_direct_sha_fetch = int(commit_exists(clone_path, state.sha, timeout_seconds))
        if state.after_direct_sha_fetch and not state.final_exists:
            state.final_exists = 1
            state.recovery_stage = "direct_sha_fetch"

    unresolved = [state for state in repo_states if not state.final_exists]
    if unresolved and fetch_pr_refs:
        result = run_git(
            clone_path,
            [
                "fetch",
                "--force",
                "origin",
                "+refs/pull/*/head:refs/remotes/origin/pull/*/head",
            ],
            timeout_seconds,
        )
        audit["pr_fetch_returncode"] = result.returncode
        audit["pr_fetch_stderr"] = truncate(result.stderr)
    mark_stage(repo_states, "after_pr_fetch", "pull_request_refs", timeout_seconds)

    for state in repo_states:
        state.final_exists = int(commit_exists(clone_path, state.sha, timeout_seconds))
        if state.final_exists:
            if state.recovery_stage == "unresolved":
                state.recovery_stage = "available_after_fetch"
            state.object_type, state.commit_date, state.commit_subject = get_commit_metadata(
                clone_path, state.sha, timeout_seconds
            )
        else:
            state.recovery_stage = "unresolved_after_fetch"

    audit["recovered_unique_commits"] = sum(
        state.final_exists and not state.exists_before for state in repo_states
    )
    audit["unresolved_unique_commits"] = sum(not state.final_exists for state in repo_states)
    return audit


def states_to_dataframe(states: Iterable[CommitState]) -> pd.DataFrame:
    records = []
    for state in sorted(states, key=lambda item: (item.repo_name.casefold(), item.sha)):
        records.append(
            {
                "repo_name": state.repo_name,
                "clone_path": str(state.clone_path),
                "missing_commit_sha": state.sha,
                "affected_month_count": state.affected_month_count,
                "affected_months": state.affected_months,
                "commit_resolution_types": state.commit_resolution_types,
                "exists_before": state.exists_before,
                "after_unshallow": state.after_unshallow,
                "after_fetch_all": state.after_fetch_all,
                "after_explicit_refs": state.after_explicit_refs,
                "after_direct_sha_fetch": state.after_direct_sha_fetch,
                "after_pr_fetch": state.after_pr_fetch,
                "final_exists": state.final_exists,
                "recovery_stage": state.recovery_stage,
                "object_type": state.object_type,
                "commit_date": state.commit_date,
                "commit_subject": state.commit_subject,
            }
        )
    return pd.DataFrame(records)


def build_unresolved_rows(
    missing_rows: pd.DataFrame,
    status_df: pd.DataFrame,
) -> pd.DataFrame:
    if missing_rows.empty:
        return missing_rows.copy()
    status_subset = status_df[
        ["repo_name", "missing_commit_sha", "final_exists", "recovery_stage"]
    ].rename(columns={"missing_commit_sha": "latest_commit_effective"})
    merged = missing_rows.merge(
        status_subset,
        on=["repo_name", "latest_commit_effective"],
        how="left",
        validate="many_to_one",
    )
    return merged[merged["final_exists"].fillna(0).eq(0)].copy()


def write_summary(
    *,
    args: argparse.Namespace,
    missing_rows: pd.DataFrame,
    status_df: pd.DataFrame,
    repository_df: pd.DataFrame,
    unresolved_df: pd.DataFrame,
) -> pd.DataFrame:
    def count_stage(stage: str) -> int:
        if status_df.empty:
            return 0
        return int(status_df["recovery_stage"].eq(stage).sum())

    input_unique = len(status_df)
    final_resolved_unique = int(status_df["final_exists"].fillna(0).astype(int).sum()) if not status_df.empty else 0
    recovered_unique = int(
        ((status_df["exists_before"].fillna(0).astype(int) == 0)
         & (status_df["final_exists"].fillna(0).astype(int) == 1)).sum()
    ) if not status_df.empty else 0
    rows = [
        ("implementation", "version", "v1", "run-x-a03b recovery implementation."),
        ("mode", "dry_run", int(args.dry_run), "1 means no fetch commands were executed."),
        ("mode", "fetch_pr_refs", int(args.fetch_pr_refs), "Optional GitHub pull-request refs fetch."),
        ("input", "commit_not_found_repo_month_rows", len(missing_rows), "Rows selected from run-x-a03-v2."),
        ("input", "unique_missing_commits", input_unique, "Unique repo_name + commit SHA pairs."),
        ("input", "affected_repositories", missing_rows["repo_name"].nunique() if not missing_rows.empty else 0, ""),
        ("result", "unique_commits_available_before", int(status_df["exists_before"].sum()) if not status_df.empty else 0, ""),
        ("result", "unique_commits_recovered", recovered_unique, "Missing before and available after recovery."),
        ("result", "unique_commits_resolved_final", final_resolved_unique, "Includes commits already available before the run."),
        ("result", "unique_commits_unresolved_final", input_unique - final_resolved_unique, ""),
        ("result", "repo_month_rows_unresolved_final", len(unresolved_df), ""),
        ("repository", "remote_accessible", int(repository_df["remote_accessible"].sum()) if not repository_df.empty else 0, ""),
        ("repository", "remote_unavailable", int((repository_df["remote_accessible"] == 0).sum()) if not repository_df.empty else 0, ""),
        ("repository", "origin_name_mismatch", int((repository_df["origin_name_matches_input"] == 0).sum()) if not repository_df.empty else 0, "Only rows with a parsed GitHub origin name are counted."),
        ("recovery_stage", "already_available", count_stage("already_available"), ""),
        ("recovery_stage", "unshallow", count_stage("unshallow"), ""),
        ("recovery_stage", "fetch_all", count_stage("fetch_all"), ""),
        ("recovery_stage", "explicit_refs", count_stage("explicit_refs"), ""),
        ("recovery_stage", "direct_sha_fetch", count_stage("direct_sha_fetch"), ""),
        ("recovery_stage", "pull_request_refs", count_stage("pull_request_refs"), ""),
        ("recovery_stage", "dry_run_unresolved", count_stage("dry_run_unresolved"), ""),
        ("recovery_stage", "unresolved_after_fetch", count_stage("unresolved_after_fetch"), ""),
    ]
    summary = pd.DataFrame(rows, columns=["section", "metric", "value", "note"])
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_output, index=False)
    return summary


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        validate_args(args)
        missing_rows = read_missing_rows(args.eligibility_file)
        states_map = build_commit_states(missing_rows)
        states = list(states_map.values())

        logging.info(
            "Selected %d commit_not_found repo-month rows: %d repositories and %d unique commits",
            len(missing_rows),
            missing_rows["repo_name"].nunique() if not missing_rows.empty else 0,
            len(states),
        )

        repository_records: list[dict[str, object]] = []
        states_by_repo: dict[str, list[CommitState]] = {}
        for state in states:
            states_by_repo.setdefault(state.repo_name, []).append(state)

        for index, repo_name in enumerate(sorted(states_by_repo, key=str.casefold), start=1):
            repo_states = states_by_repo[repo_name]
            logging.info(
                "[%d/%d] Recovering %s (%d unique missing commits)",
                index,
                len(states_by_repo),
                repo_name,
                len(repo_states),
            )
            record = process_repository(
                repo_name,
                repo_states,
                timeout_seconds=args.git_timeout_seconds,
                dry_run=args.dry_run,
                fetch_pr_refs=args.fetch_pr_refs,
                skip_direct_sha_fetch=args.skip_direct_sha_fetch,
            )
            repository_records.append(record)
            logging.info(
                "%s: recovered=%s unresolved=%s remote_accessible=%s",
                repo_name,
                record["recovered_unique_commits"],
                record["unresolved_unique_commits"],
                record["remote_accessible"],
            )

        status_df = states_to_dataframe(states)
        repository_df = pd.DataFrame(repository_records)
        unresolved_df = build_unresolved_rows(missing_rows, status_df)

        for path in [
            args.recovery_status_output,
            args.repository_output,
            args.unresolved_output,
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)

        status_df.to_csv(args.recovery_status_output, index=False)
        repository_df.to_csv(args.repository_output, index=False)
        unresolved_df.to_csv(args.unresolved_output, index=False)
        summary = write_summary(
            args=args,
            missing_rows=missing_rows,
            status_df=status_df,
            repository_df=repository_df,
            unresolved_df=unresolved_df,
        )

        logging.info("Wrote %d rows to %s", len(status_df), args.recovery_status_output)
        logging.info("Wrote %d rows to %s", len(repository_df), args.repository_output)
        logging.info("Wrote %d rows to %s", len(unresolved_df), args.unresolved_output)
        logging.info("Wrote %d rows to %s", len(summary), args.summary_output)

        unresolved_unique = int((status_df["final_exists"] == 0).sum()) if not status_df.empty else 0
        if args.fail_on_unresolved and unresolved_unique:
            logging.error("Unresolved unique commits remain: %d", unresolved_unique)
            return 2
        return 0
    except Exception as exc:
        logging.exception("Missing-commit recovery failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
