#!/usr/bin/env python3
"""
check_empty_repos.py

Scan a directory of cloned repositories (as produced by the clone scripts,
e.g. ../treatment-repos or ../control-repos) and flag repos that likely have
little or no analyzable Python code -- for example because the repository
was migrated, archived, deprecated, or is otherwise a near-empty stub.

This is a *triage* tool: it does NOT modify anything. It only reports.

Why this matters:
    SonarQube's ncloc / cognitive_complexity / comment_lines_density /
    duplicated_lines_density metrics are only computed when there is
    analyzable source code. If a repo is a stub (e.g. "this repo has been
    migrated to X"), those metrics will be missing (NaN) for every month of
    that repo in the scanned output CSV. Finding these repos ahead of time
    lets you decide whether to exclude them, or re-collect them from their
    new location, before running (or re-running) the SonarQube scan.

Usage:
    python check_empty_repos.py --repos-dir ../control-repos --output control-empty-repos-report.csv
    python check_empty_repos.py --repos-dir ../treatment-repos --output treatment-empty-repos-report.csv

    # Both directories in one run, combined report:
    python check_empty_repos.py --repos-dir ../control-repos --repos-dir ../treatment-repos --output combined-report.csv

Flags a repo as SUSPECT if any of the following hold (checked against the
currently checked-out state of each cloned repo -- typically its default
branch HEAD, not necessarily the specific per-month commit used by the
SonarQube scan):
    - Zero .py files found anywhere in the repo (excluding .git, caches, venvs)
    - Fewer than MIN_COMMITS total commits on the checked-out branch
    - The README contains a migration/deprecation-style phrase
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path
from typing import Optional

# Directories to skip when counting .py files -- build artifacts, caches,
# virtualenvs, and VCS metadata should never count as "real" source.
EXCLUDED_DIR_NAMES = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache", "coverage",
    ".next", ".nuxt",
}

# Repos with fewer total commits than this are flagged as suspiciously thin.
MIN_COMMITS = 5

# Case-insensitive phrases that suggest the repo is a stub / pointer to
# somewhere else, commonly found in a lone README.
SUSPICIOUS_README_PATTERNS = [
    r"migrated to",
    r"has moved to",
    r"moved to\b",
    r"repository (has been|is) (archived|deprecated)",
    r"no longer maintained",
    r"this (repo|repository) is deprecated",
    r"renamed to",
    r"see the new repository",
    r"this project has moved",
]

README_CANDIDATES = ["README.md", "README.rst", "README.txt", "readme.md", "Readme.md"]


def count_python_files_and_lines(repo_path: Path) -> tuple[int, int]:
    """Count .py files and their total line count, skipping excluded dirs."""
    py_file_count = 0
    total_lines = 0

    for path in repo_path.rglob("*.py"):
        # Skip anything living inside an excluded directory.
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        py_file_count += 1
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                total_lines += sum(1 for _ in f)
        except OSError:
            # Unreadable file (permissions, broken symlink, etc.) -- skip.
            continue

    return py_file_count, total_lines


def get_commit_count(repo_path: Path) -> Optional[int]:
    """Return the total commit count on the currently checked-out ref."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        return None


def find_suspicious_readme_phrase(repo_path: Path) -> Optional[str]:
    """Return the first suspicious phrase found in a README, if any."""
    for candidate in README_CANDIDATES:
        readme_path = repo_path / candidate
        if not readme_path.exists():
            continue
        try:
            text = readme_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SUSPICIOUS_README_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
    return None


def scan_repos_dir(repos_dir: Path) -> list[dict]:
    """Scan every immediate subdirectory of repos_dir as one repo."""
    rows = []

    if not repos_dir.exists():
        print(f"WARNING: repos dir not found, skipping: {repos_dir}")
        return rows

    repo_paths = sorted(p for p in repos_dir.iterdir() if p.is_dir())
    print(f"Scanning {len(repo_paths)} repos under {repos_dir} ...")

    for i, repo_path in enumerate(repo_paths, 1):
        py_files, py_lines = count_python_files_and_lines(repo_path)
        commit_count = get_commit_count(repo_path)
        readme_flag = find_suspicious_readme_phrase(repo_path)

        reasons = []
        if py_files == 0:
            reasons.append("no .py files")
        if commit_count is not None and commit_count < MIN_COMMITS:
            reasons.append(f"only {commit_count} commits")
        if readme_flag:
            reasons.append(f"README mentions: '{readme_flag}'")

        rows.append({
            "source_dir": str(repos_dir),
            "repo_name": repo_path.name,
            "py_file_count": py_files,
            "py_total_lines": py_lines,
            "commit_count": commit_count if commit_count is not None else "unknown",
            "readme_flag": readme_flag or "",
            "suspect": bool(reasons),
            "reasons": "; ".join(reasons),
        })

        if i % 20 == 0 or i == len(repo_paths):
            print(f"  ... {i}/{len(repo_paths)} scanned")

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repos-dir", action="append", required=True, type=Path,
        help="Directory containing cloned repos as subdirectories. Can be given multiple times.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("empty-repos-report.csv"),
        help="Output CSV path. Default: %(default)s",
    )
    args = parser.parse_args()

    all_rows: list[dict] = []
    for repos_dir in args.repos_dir:
        all_rows.extend(scan_repos_dir(repos_dir))

    if not all_rows:
        print("No repos found to scan.")
        return

    fieldnames = [
        "source_dir", "repo_name", "py_file_count", "py_total_lines",
        "commit_count", "readme_flag", "suspect", "reasons",
    ]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    suspects = [r for r in all_rows if r["suspect"]]

    print()
    print("=" * 60)
    print(f"Total repos scanned: {len(all_rows)}")
    print(f"Suspect repos:       {len(suspects)}")
    print(f"Report written to:   {args.output}")
    print("=" * 60)

    if suspects:
        print("\nSuspect repos:")
        for r in suspects:
            print(f"  - {r['repo_name']}  ({r['reasons']})")


if __name__ == "__main__":
    main()