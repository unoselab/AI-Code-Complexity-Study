#!/usr/bin/env python3
"""
Clone repositories from a candidate CSV file.

This script extends the original scripts/clone_repos.py behavior without
modifying the original file.

Original reusable logic:
  - ensure_dir()
  - is_git_repo()
  - pull_latest_changes()

New v2 logic:
  - read arbitrary CSV with repo_name column
  - clone into a user-specified clone root
  - save timestamped clone log under ./logs
  - support max clone count for smoke tests
  - skip existing repositories by default
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "clone_repos.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original clone script not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location("original_clone_repos", ORIGINAL_SCRIPT)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone repositories from a candidate CSV file."
    )

    parser.add_argument(
        "--repos-file",
        type=Path,
        required=True,
        help="CSV file containing repo_name column.",
    )

    parser.add_argument(
        "--repo-column",
        default="repo_name",
        help="Column containing GitHub repo names. Default: repo_name.",
    )

    parser.add_argument(
        "--clone-root",
        type=Path,
        default=PROJECT_DIR.parent / "ai_code_complexity_study_repo_dataset",
        help="Directory where repositories will be cloned.",
    )

    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=PROJECT_DIR / "logs",
        help="Directory for timestamped clone logs.",
    )

    parser.add_argument(
        "--log-prefix",
        default="run4a_clone_log",
        help="Clone log filename prefix.",
    )

    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional timestamp for log file. Default: current YYYYMMDD-HHMM.",
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=0,
        help="Maximum repos to process. Use 0 for all.",
    )

    parser.add_argument(
        "--existing-action",
        choices=["skip", "pull"],
        default="skip",
        help=(
            "What to do if target repo already exists. "
            "skip is safer for this study; pull refreshes existing clones."
        ),
    )

    parser.add_argument(
        "--git-clone-extra-arg",
        action="append",
        default=[],
        help=(
            "Extra argument passed to git clone. Can be repeated. "
            "Do not use --depth 1 because full history is needed."
        ),
    )

    return parser.parse_args()


def read_repo_names(csv_path: Path, repo_column: str) -> list[str]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Repos file not found: {csv_path}")

    repos: list[str] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None or repo_column not in reader.fieldnames:
            raise ValueError(
                f"Column {repo_column!r} not found in {csv_path}. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            repo = str(row.get(repo_column, "")).strip()
            if repo:
                repos.append(repo)

    # Preserve input order while removing duplicates.
    seen = set()
    unique_repos = []
    for repo in repos:
        if repo not in seen:
            unique_repos.append(repo)
            seen.add(repo)

    return unique_repos


def clone_repository_v2(
    repo_name: str,
    clone_path: Path,
    extra_args: Iterable[str],
) -> tuple[bool, str]:
    repo_url = f"https://github.com/{repo_name}.git"
    cmd = ["git", "clone", *extra_args, repo_url, str(clone_path)]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        logging.info("Successfully cloned %s", repo_name)
        return True, "ok"
    except subprocess.CalledProcessError as exc:
        note = (exc.stderr or exc.stdout or "git_clone_failed").strip()
        logging.error("Failed to clone %s: %s", repo_name, note)
        return False, note.replace("\n", " ")[:300]
    except Exception as exc:
        logging.error("Failed to clone %s: %s", repo_name, exc)
        return False, str(exc).replace("\n", " ")[:300]


def write_log_row(writer, repo_name: str, status: str, target_dir: Path, note: str) -> None:
    writer.writerow(
        {
            "repo_name": repo_name,
            "status": status,
            "target_dir": str(target_dir),
            "note": note,
        }
    )


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    repos_file = args.repos_file.expanduser().resolve()
    clone_root = args.clone_root.expanduser().resolve()
    logs_dir = args.logs_dir.expanduser().resolve()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d-%H%M")
    log_file = logs_dir / f"{args.log_prefix}_{timestamp}.csv"

    orig.ensure_dir(clone_root)
    orig.ensure_dir(logs_dir)

    repos = read_repo_names(repos_file, args.repo_column)

    if args.max_repos > 0:
        repos = repos[: args.max_repos]

    logging.info("Repos file: %s", repos_file)
    logging.info("Clone root: %s", clone_root)
    logging.info("Log file: %s", log_file)
    logging.info("Existing action: %s", args.existing_action)
    logging.info("Repositories to process: %d", len(repos))

    cloned = 0
    skipped = 0
    updated = 0
    failed = 0

    with log_file.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["repo_name", "status", "target_dir", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, repo_name in enumerate(repos, start=1):
            target_dir = clone_root / repo_name.replace("/", "_")

            logging.info("[%d/%d] %s -> %s", idx, len(repos), repo_name, target_dir)

            if target_dir.exists():
                if orig.is_git_repo(target_dir):
                    if args.existing_action == "skip":
                        logging.info("Already cloned. Skipping %s", repo_name)
                        write_log_row(
                            writer,
                            repo_name,
                            "skipped_existing",
                            target_dir,
                            "already_has_git_dir",
                        )
                        skipped += 1
                        continue

                    if args.existing_action == "pull":
                        ok = orig.pull_latest_changes(target_dir, repo_name)
                        if ok:
                            write_log_row(
                                writer,
                                repo_name,
                                "updated_existing",
                                target_dir,
                                "pulled_latest_changes",
                            )
                            updated += 1
                        else:
                            write_log_row(
                                writer,
                                repo_name,
                                "failed",
                                target_dir,
                                "pull_latest_changes_failed",
                            )
                            failed += 1
                        continue

                logging.warning(
                    "Path exists but is not a valid Git repo: %s",
                    target_dir,
                )
                write_log_row(
                    writer,
                    repo_name,
                    "failed",
                    target_dir,
                    "path_exists_not_git_repo",
                )
                failed += 1
                continue

            ok, note = clone_repository_v2(
                repo_name=repo_name,
                clone_path=target_dir,
                extra_args=args.git_clone_extra_arg,
            )

            if ok:
                write_log_row(writer, repo_name, "cloned", target_dir, note)
                cloned += 1
            else:
                write_log_row(writer, repo_name, "failed", target_dir, note)
                failed += 1

    logging.info("")
    logging.info("Clone summary")
    logging.info("-------------")
    logging.info("processed: %d", len(repos))
    logging.info("cloned:    %d", cloned)
    logging.info("updated:   %d", updated)
    logging.info("skipped:   %d", skipped)
    logging.info("failed:    %d", failed)
    logging.info("clone log: %s", log_file)


if __name__ == "__main__":
    main()
