#!/usr/bin/env python3
"""
Clone controls reported as missing by run-x-a01 and create an extra-repository skip list.

The script consumes the repository-level alignment CSV produced by run-x-a01.
It performs two independent tasks:

1. For every control row with alignment_status=expected_control_clone_missing,
   check the GitHub remote and attempt a full clone into the control clone root.
2. For every locally cloned repository marked as outside the current matching scope,
   write a CSV and plain-text skip list for downstream repo-month processing.

Inputs:
- run-x-a01 repository-level alignment CSV
- local control clone root

Outputs:
- missing-control clone attempt/status CSV
- extra-repository skip-list CSV
- extra-repository skip-list text file
- summary/QC CSV

A full clone is used because downstream historical repo-month analysis may need
commits across the repository history. Cloning is first performed into a temporary
sibling directory and moved into the final target only after Git verification, so a
failed clone does not leave an invalid target directory behind.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


REQUIRED_ALIGNMENT_COLUMNS = {
    "role",
    "repo_name",
    "repo_dir_name_expected",
    "expected_for_current_scope",
    "in_clone_directory",
    "is_git_repository",
    "clone_dir_name",
    "clone_path",
    "origin_url",
    "alignment_status",
}

MISSING_CONTROL_STATUS = "expected_control_clone_missing"
EXTRA_REPOSITORY_STATUSES = {
    "clone_not_in_matching_treatment",
    "extra_control_clone_not_selected",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clone controls missing from the run-x-a01 alignment and create a "
            "skip list for cloned repositories outside the matching scope."
        )
    )
    parser.add_argument("--alignment-file", required=True, type=Path)
    parser.add_argument("--control-clone-dir", required=True, type=Path)
    parser.add_argument("--clone-status-output", required=True, type=Path)
    parser.add_argument("--skip-csv-output", required=True, type=Path)
    parser.add_argument("--skip-txt-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument(
        "--remote-url-template",
        default="https://github.com/{repo_name}.git",
        help=(
            "Remote URL template containing {repo_name}. The default targets "
            "GitHub HTTPS clone URLs."
        ),
    )
    parser.add_argument(
        "--remote-check-timeout-seconds",
        type=int,
        default=120,
    )
    parser.add_argument(
        "--clone-timeout-seconds",
        type=int,
        default=3600,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check remotes and write outputs without creating clone directories.",
    )
    parser.add_argument(
        "--fail-on-clone-error",
        action="store_true",
        help="Return exit code 2 when at least one required control is not valid locally.",
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


def expected_dir_name(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def run_command(
    command: list[str],
    *,
    timeout_seconds: int,
) -> tuple[int, str, str]:
    """Run a command without raising and return code, stdout, and stderr."""
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return (
            int(completed.returncode),
            completed.stdout.strip(),
            completed.stderr.strip(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = clean_text(exc.stdout)
        stderr = clean_text(exc.stderr)
        message = f"Command timed out after {timeout_seconds} seconds."
        if stderr:
            message = f"{message} {stderr}"
        return 124, stdout, message
    except OSError as exc:
        return 127, "", str(exc)


def truncate_message(value: str, limit: int = 4000) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def inspect_git_repository(repo_path: Path) -> tuple[bool, str]:
    """Return whether the path is a Git work tree and its origin URL."""
    if not repo_path.is_dir():
        return False, ""

    code, stdout, _ = run_command(
        ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
        timeout_seconds=30,
    )
    if code != 0 or stdout.casefold() != "true":
        return False, ""

    code, origin_url, _ = run_command(
        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
        timeout_seconds=30,
    )
    if code != 0:
        origin_url = ""
    return True, origin_url


def validate_args(args: argparse.Namespace) -> None:
    if not args.alignment_file.is_file():
        raise FileNotFoundError(f"Alignment file not found: {args.alignment_file}")
    if not args.control_clone_dir.is_dir():
        raise NotADirectoryError(
            f"Control clone directory not found: {args.control_clone_dir}"
        )
    if args.remote_check_timeout_seconds <= 0:
        raise ValueError("remote-check-timeout-seconds must be positive")
    if args.clone_timeout_seconds <= 0:
        raise ValueError("clone-timeout-seconds must be positive")
    if "{repo_name}" not in args.remote_url_template:
        raise ValueError("remote-url-template must contain {repo_name}")


def load_alignment(path: Path) -> pd.DataFrame:
    alignment = pd.read_csv(path)
    missing_columns = REQUIRED_ALIGNMENT_COLUMNS - set(alignment.columns)
    if missing_columns:
        raise ValueError(
            "Alignment CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
    return alignment


def build_skip_list(alignment: pd.DataFrame) -> pd.DataFrame:
    """Create a stable list of cloned repositories outside the matching scope."""
    mask = alignment["alignment_status"].astype(str).isin(EXTRA_REPOSITORY_STATUSES)
    extra = alignment.loc[mask].copy()

    records: list[dict[str, object]] = []
    for row in extra.itertuples(index=False):
        repo_name = clean_text(row.repo_name)
        records.append(
            {
                "repo_name": repo_name,
                "repo_dir_name": clean_text(row.clone_dir_name)
                or clean_text(row.repo_dir_name_expected)
                or expected_dir_name(repo_name),
                "role": clean_text(row.role),
                "clone_path": clean_text(row.clone_path),
                "alignment_status": clean_text(row.alignment_status),
                "skip_reason": (
                    "Locally cloned repository is outside the treatment-control "
                    "scope defined by the original matching.csv for run-x-a01."
                ),
            }
        )

    columns = [
        "repo_name",
        "repo_dir_name",
        "role",
        "clone_path",
        "alignment_status",
        "skip_reason",
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if not result.empty:
        result = result.sort_values(
            ["role", "repo_name"],
            key=lambda series: series.astype(str).str.casefold(),
        ).reset_index(drop=True)
    return result


def select_missing_controls(alignment: pd.DataFrame) -> pd.DataFrame:
    mask = (
        alignment["role"].astype(str).str.casefold().eq("control")
        & alignment["alignment_status"].astype(str).eq(MISSING_CONTROL_STATUS)
    )
    missing = alignment.loc[mask].copy()
    if missing.empty:
        return missing

    missing["repo_name"] = missing["repo_name"].astype(str).str.strip()
    missing["_repo_key"] = missing["repo_name"].str.casefold()
    missing = missing.drop_duplicates("_repo_key", keep="first")
    return missing.sort_values("_repo_key").drop(columns=["_repo_key"])


def clone_one_repository(
    *,
    repo_name: str,
    target_dir: Path,
    remote_url: str,
    dry_run: bool,
    remote_check_timeout_seconds: int,
    clone_timeout_seconds: int,
) -> dict[str, object]:
    """Check and clone one repository, returning a detailed status record."""
    checked_at = datetime.now(timezone.utc).isoformat()
    target_exists_before = target_dir.exists()
    valid_before, origin_before = inspect_git_repository(target_dir)

    base_record: dict[str, object] = {
        "repo_name": repo_name,
        "repo_dir_name": target_dir.name,
        "clone_path": str(target_dir),
        "remote_url": remote_url,
        "checked_at_utc": checked_at,
        "dry_run": int(dry_run),
        "target_exists_before": int(target_exists_before),
        "valid_git_before": int(valid_before),
        "origin_url_before": origin_before,
        "remote_check_return_code": "",
        "remote_check_status": "not_run",
        "clone_attempted": 0,
        "clone_return_code": "",
        "clone_status": "",
        "valid_git_after": int(valid_before),
        "origin_url_after": origin_before,
        "error_message": "",
    }

    if valid_before:
        base_record["clone_status"] = "already_valid_git"
        return base_record

    if target_exists_before:
        base_record["clone_status"] = "target_exists_not_git"
        base_record["error_message"] = (
            "The final target path already exists but is not a valid Git repository; "
            "it was not modified."
        )
        return base_record

    remote_code, _, remote_stderr = run_command(
        ["git", "ls-remote", "--exit-code", remote_url, "HEAD"],
        timeout_seconds=remote_check_timeout_seconds,
    )
    base_record["remote_check_return_code"] = remote_code

    if remote_code != 0:
        base_record["remote_check_status"] = "unavailable"
        base_record["clone_status"] = "remote_unavailable"
        base_record["error_message"] = truncate_message(remote_stderr)
        return base_record

    base_record["remote_check_status"] = "available"
    if dry_run:
        base_record["clone_status"] = "dry_run_clone_planned"
        return base_record

    temporary_dir = target_dir.with_name(
        f".{target_dir.name}.clone-tmp-{os.getpid()}"
    )
    if temporary_dir.exists():
        shutil.rmtree(temporary_dir)

    logging.info("Cloning %s -> %s", repo_name, target_dir)
    base_record["clone_attempted"] = 1
    clone_code, _, clone_stderr = run_command(
        ["git", "clone", remote_url, str(temporary_dir)],
        timeout_seconds=clone_timeout_seconds,
    )
    base_record["clone_return_code"] = clone_code

    if clone_code != 0:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)
        base_record["clone_status"] = "clone_failed"
        base_record["error_message"] = truncate_message(clone_stderr)
        return base_record

    valid_temp, origin_temp = inspect_git_repository(temporary_dir)
    if not valid_temp:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        base_record["clone_status"] = "clone_verification_failed"
        base_record["error_message"] = (
            "git clone returned success, but the temporary directory did not "
            "verify as a Git work tree."
        )
        return base_record

    try:
        temporary_dir.rename(target_dir)
    except OSError as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        base_record["clone_status"] = "clone_finalize_failed"
        base_record["error_message"] = str(exc)
        return base_record

    valid_after, origin_after = inspect_git_repository(target_dir)
    base_record["valid_git_after"] = int(valid_after)
    base_record["origin_url_after"] = origin_after or origin_temp

    if valid_after:
        base_record["clone_status"] = "cloned"
    else:
        base_record["clone_status"] = "final_verification_failed"
        base_record["error_message"] = (
            "The repository was moved to the final target, but final Git "
            "verification failed."
        )
    return base_record


def write_outputs(
    *,
    clone_status: pd.DataFrame,
    skip_list: pd.DataFrame,
    clone_status_output: Path,
    skip_csv_output: Path,
    skip_txt_output: Path,
    summary_output: Path,
    dry_run: bool,
) -> pd.DataFrame:
    for path in [
        clone_status_output,
        skip_csv_output,
        skip_txt_output,
        summary_output,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)

    clone_status.to_csv(clone_status_output, index=False)
    skip_list.to_csv(skip_csv_output, index=False)
    skip_txt_output.write_text(
        "".join(f"{repo_name}\n" for repo_name in skip_list["repo_name"].tolist()),
        encoding="utf-8",
    )

    status_counts = (
        clone_status["clone_status"].value_counts(dropna=False).to_dict()
        if not clone_status.empty
        else {}
    )
    valid_after = (
        int(pd.to_numeric(clone_status["valid_git_after"], errors="coerce").fillna(0).sum())
        if not clone_status.empty
        else 0
    )
    unresolved_after = len(clone_status) - valid_after

    summary_rows: list[dict[str, object]] = [
        {
            "section": "input",
            "metric": "missing_control_repositories",
            "value": len(clone_status),
            "note": "Unique controls marked expected_control_clone_missing by run-x-a01.",
        },
        {
            "section": "mode",
            "metric": "dry_run",
            "value": int(dry_run),
            "note": "1 means remotes were checked but clone directories were not created.",
        },
        {
            "section": "result",
            "metric": "valid_control_repositories_after",
            "value": valid_after,
            "note": "Required controls verified as local Git repositories after this run.",
        },
        {
            "section": "result",
            "metric": "unresolved_control_repositories_after",
            "value": unresolved_after,
            "note": "Required controls still unavailable or invalid after this run.",
        },
        {
            "section": "skip_list",
            "metric": "extra_repositories_to_skip",
            "value": len(skip_list),
            "note": "Cloned repositories outside the current matching.csv scope.",
        },
        {
            "section": "skip_list",
            "metric": "extra_treatment_repositories_to_skip",
            "value": int((skip_list["role"].astype(str).str.casefold() == "treatment").sum()),
            "note": "Treatment clones not represented as treatment rows in matching.csv.",
        },
        {
            "section": "skip_list",
            "metric": "extra_control_repositories_to_skip",
            "value": int((skip_list["role"].astype(str).str.casefold() == "control").sum()),
            "note": "Control clones not selected by the cloned treatment scope.",
        },
    ]

    for status, count in sorted(status_counts.items(), key=lambda item: str(item[0])):
        summary_rows.append(
            {
                "section": "clone_status",
                "metric": str(status),
                "value": int(count),
                "note": "",
            }
        )

    summary = pd.DataFrame(summary_rows, columns=["section", "metric", "value", "note"])
    summary.to_csv(summary_output, index=False)
    return summary


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        validate_args(args)
        alignment = load_alignment(args.alignment_file)
        missing_controls = select_missing_controls(alignment)
        skip_list = build_skip_list(alignment)

        logging.info(
            "Missing unique control repositories selected for checking/cloning: %d",
            len(missing_controls),
        )
        logging.info("Extra cloned repositories selected for skip list: %d", len(skip_list))

        clone_records: list[dict[str, object]] = []
        for row in missing_controls.itertuples(index=False):
            repo_name = clean_text(row.repo_name)
            repo_dir_name = (
                clean_text(row.repo_dir_name_expected) or expected_dir_name(repo_name)
            )
            target_dir = args.control_clone_dir / repo_dir_name
            remote_url = args.remote_url_template.format(repo_name=repo_name)

            record = clone_one_repository(
                repo_name=repo_name,
                target_dir=target_dir,
                remote_url=remote_url,
                dry_run=args.dry_run,
                remote_check_timeout_seconds=args.remote_check_timeout_seconds,
                clone_timeout_seconds=args.clone_timeout_seconds,
            )
            clone_records.append(record)
            logging.info(
                "%s: %s (valid_after=%s)",
                repo_name,
                record["clone_status"],
                record["valid_git_after"],
            )

        clone_columns = [
            "repo_name",
            "repo_dir_name",
            "clone_path",
            "remote_url",
            "checked_at_utc",
            "dry_run",
            "target_exists_before",
            "valid_git_before",
            "origin_url_before",
            "remote_check_return_code",
            "remote_check_status",
            "clone_attempted",
            "clone_return_code",
            "clone_status",
            "valid_git_after",
            "origin_url_after",
            "error_message",
        ]
        clone_status = pd.DataFrame.from_records(clone_records, columns=clone_columns)

        summary = write_outputs(
            clone_status=clone_status,
            skip_list=skip_list,
            clone_status_output=args.clone_status_output,
            skip_csv_output=args.skip_csv_output,
            skip_txt_output=args.skip_txt_output,
            summary_output=args.summary_output,
            dry_run=args.dry_run,
        )

        logging.info("Wrote %d rows to %s", len(clone_status), args.clone_status_output)
        logging.info("Wrote %d rows to %s", len(skip_list), args.skip_csv_output)
        logging.info("Wrote skip text list to %s", args.skip_txt_output)
        logging.info("Wrote %d rows to %s", len(summary), args.summary_output)

        unresolved = (
            int((pd.to_numeric(clone_status["valid_git_after"], errors="coerce").fillna(0) == 0).sum())
            if not clone_status.empty
            else 0
        )
        if args.fail_on_clone_error and unresolved > 0 and not args.dry_run:
            logging.error(
                "%d required control repositories remain unresolved after clone attempts",
                unresolved,
            )
            return 2
        return 0

    except Exception as exc:
        logging.exception("Missing-control clone task failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
