#!/usr/bin/env python3
"""Inspect local Git repositories for SonarQube metric outlier diagnosis.

This script reads row-level SonarQube difference outliers and inspects the
corresponding local Git clones without modifying the working tree. It uses
`git ls-tree` and `git show` at the recorded commits to collect file-scope and
configuration clues that can explain differences between a paper snapshot and a
new SonarQube scan.

Inputs:
  - Row-level positive/negative outlier CSV files from run-py-2b9.
  - Optional aggregated top-repo CSV file from run-py-2b9.
  - Local treatment/control clone roots.

Outputs:
  - Selected outlier rows for inspection.
  - Git tree summaries at paper and our commits when available.
  - Top directory summaries.
  - Configuration file presence table.
  - Configuration snippets extracted from Git objects.
  - Manual command helper script for deeper per-repo inspection.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


CONFIG_CANDIDATES = [
    "sonar-project.properties",
    ".sonarcloud.properties",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    ".flake8",
    ".pylintrc",
    "ruff.toml",
    ".ruff.toml",
    ".pre-commit-config.yaml",
    ".gitignore",
]

WARNING_METRICS = {
    "bugs",
    "vulnerabilities",
    "code_smells",
    "technical_debt",
    "static_analysis_warnings",
}

KEY_METRICS = WARNING_METRICS | {
    "ncloc",
    "cognitive_complexity",
    "duplicated_lines_density",
    "comment_lines_density",
}

GENERATED_HINTS = [
    "generated",
    "vendor",
    "vendors",
    "third_party",
    "third-party",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "site-packages",
    "migrations",
]

TEST_HINTS = ["test", "tests", "testing", "pytest"]
DOC_HINTS = ["doc", "docs", "documentation", "examples", "example"]


@dataclass
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_git(repo_path: Path, args: list[str], timeout: int = 30) -> GitCommandResult:
    """Run a git command in a local clone and return stdout/stderr."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - runtime environment guard
        return GitCommandResult(returncode=999, stdout="", stderr=str(exc))
    return GitCommandResult(proc.returncode, proc.stdout, proc.stderr)


def normalize_repo_dir_name(repo_name: str) -> str:
    """Convert owner/repo into the local clone directory naming convention."""
    return str(repo_name).replace("/", "_")


def safe_float(value) -> float | None:
    """Convert a value to float when possible."""
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def choose_existing_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Return the subset of requested columns that exist in the dataframe."""
    return [c for c in cols if c in df.columns]


def read_optional_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file when it exists, otherwise return an empty dataframe."""
    if not path or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_outlier_rows(args: argparse.Namespace) -> pd.DataFrame:
    """Load and combine positive/negative row-level outliers for inspection."""
    frames = []
    for path, direction in [
        (Path(args.negative_outliers_file), "negative"),
        (Path(args.positive_outliers_file), "positive"),
    ]:
        df = read_optional_csv(path)
        if len(df) > 0:
            df = df.copy()
            df["outlier_direction"] = direction
            frames.append(df)

    if not frames:
        raise SystemExit(
            "ERROR: no outlier rows were loaded. Check negative/positive outlier files."
        )

    combined = pd.concat(frames, ignore_index=True, sort=False)

    if "metric" in combined.columns:
        combined = combined[combined["metric"].isin(KEY_METRICS)].copy()

    if "abs_diff" not in combined.columns and {"paper_value", "our_value"}.issubset(combined.columns):
        combined["diff"] = pd.to_numeric(combined["our_value"], errors="coerce") - pd.to_numeric(
            combined["paper_value"], errors="coerce"
        )
        combined["abs_diff"] = combined["diff"].abs()

    if "abs_diff" in combined.columns:
        combined = combined.sort_values("abs_diff", ascending=False)

    return combined.reset_index(drop=True)


def select_inspection_rows(outliers: pd.DataFrame, max_rows: int, max_repos: int) -> pd.DataFrame:
    """Select a balanced set of row-level outliers across cause categories and metrics."""
    if len(outliers) == 0:
        return outliers

    required = ["source_group", "repo_name"]
    missing = [c for c in required if c not in outliers.columns]
    if missing:
        raise SystemExit(f"ERROR: required columns missing from outlier rows: {missing}")

    priority_causes = [
        "source_scope_difference_or_mixed",
        "rule_config_analyzer_profile_signal",
        "commit_selection_difference",
        "paper_commit_missing",
    ]
    priority_metrics = [
        "static_analysis_warnings",
        "code_smells",
        "technical_debt",
        "ncloc",
        "bugs",
        "vulnerabilities",
        "cognitive_complexity",
    ]

    selected_parts = []
    for cause in priority_causes:
        cause_df = outliers
        if "cause_category" in outliers.columns:
            cause_df = outliers[outliers["cause_category"].eq(cause)]
        if len(cause_df) == 0:
            continue
        for metric in priority_metrics:
            metric_df = cause_df
            if "metric" in cause_df.columns:
                metric_df = cause_df[cause_df["metric"].eq(metric)]
            if len(metric_df) == 0:
                continue
            selected_parts.append(metric_df.head(max(1, max_rows // 20)))

    if selected_parts:
        selected = pd.concat(selected_parts, ignore_index=True, sort=False)
    else:
        selected = outliers.head(max_rows).copy()

    selected = selected.drop_duplicates(
        subset=choose_existing_columns(
            selected,
            [
                "source_group",
                "repo_name",
                "time",
                "metric",
                "cause_category",
                "paper_latest_commit",
                "our_latest_commit",
            ],
        )
    )

    if "abs_diff" in selected.columns:
        selected = selected.sort_values("abs_diff", ascending=False)

    if max_repos > 0:
        repo_key_cols = ["source_group", "repo_name"]
        top_repos = (
            selected.groupby(repo_key_cols, dropna=False)["abs_diff"]
            .sum()
            .sort_values(ascending=False)
            .head(max_repos)
            .reset_index()[repo_key_cols]
        )
        selected = selected.merge(top_repos, on=repo_key_cols, how="inner")

    if max_rows > 0:
        selected = selected.head(max_rows)

    return selected.reset_index(drop=True)


def list_tree_files(repo_path: Path, commit: str) -> tuple[list[str], str | None]:
    """List files tracked by Git at a commit without checking it out."""
    if not commit or str(commit).lower() in {"nan", "none"}:
        return [], "missing_commit"
    result = run_git(repo_path, ["ls-tree", "-r", "--name-only", str(commit)], timeout=60)
    if result.returncode != 0:
        return [], result.stderr.strip() or "git_ls_tree_failed"
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return files, None


def top_level_dir(path: str) -> str:
    """Return the top-level directory for a repository-relative path."""
    parts = str(path).split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def classify_paths(files: list[str]) -> dict[str, int]:
    """Compute simple source-scope indicators from a list of Git-tracked files."""
    lower_files = [f.lower() for f in files]
    py_files = [f for f in lower_files if f.endswith(".py")]
    ipynb_files = [f for f in lower_files if f.endswith(".ipynb")]
    js_ts_files = [f for f in lower_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))]

    def has_any_hint(path: str, hints: list[str]) -> bool:
        parts = re.split(r"[/_.-]+", path.lower())
        return any(h in parts or h in path.lower() for h in hints)

    return {
        "tracked_files": len(files),
        "python_files": len(py_files),
        "notebook_files": len(ipynb_files),
        "js_ts_files": len(js_ts_files),
        "test_like_files": sum(1 for f in lower_files if has_any_hint(f, TEST_HINTS)),
        "doc_example_files": sum(1 for f in lower_files if has_any_hint(f, DOC_HINTS)),
        "generated_vendor_like_files": sum(1 for f in lower_files if has_any_hint(f, GENERATED_HINTS)),
    }


def summarize_top_dirs(files: list[str], top_n: int = 12) -> list[dict[str, object]]:
    """Summarize top-level directory file counts."""
    rows = []
    if not files:
        return rows
    df = pd.DataFrame({"path": files})
    df["top_dir"] = df["path"].map(top_level_dir)
    df["is_py"] = df["path"].str.lower().str.endswith(".py")
    grouped = (
        df.groupby("top_dir")
        .agg(files=("path", "count"), python_files=("is_py", "sum"))
        .reset_index()
        .sort_values(["python_files", "files"], ascending=False)
        .head(top_n)
    )
    return grouped.to_dict("records")


def git_object_exists(repo_path: Path, commit: str, file_path: str) -> bool:
    """Check whether a file exists at a commit."""
    if not commit or str(commit).lower() in {"nan", "none"}:
        return False
    result = run_git(repo_path, ["cat-file", "-e", f"{commit}:{file_path}"], timeout=10)
    return result.returncode == 0


def git_show_file(repo_path: Path, commit: str, file_path: str, max_chars: int) -> str:
    """Read a file from a Git object without checking out the commit."""
    if not git_object_exists(repo_path, commit, file_path):
        return ""
    result = run_git(repo_path, ["show", f"{commit}:{file_path}"], timeout=20)
    if result.returncode != 0:
        return ""
    text = result.stdout
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]...\n"
    return text


def collect_config_presence(repo_path: Path, commit: str) -> list[dict[str, object]]:
    """Collect presence of known configuration files at a commit."""
    rows = []
    for rel_path in CONFIG_CANDIDATES:
        rows.append(
            {
                "config_file": rel_path,
                "exists_at_commit": git_object_exists(repo_path, commit, rel_path),
            }
        )
    return rows


def build_manual_command(row: pd.Series, clone_root: Path) -> str:
    """Build a compact manual inspection command for one repo/commit."""
    repo_name = str(row.get("repo_name", ""))
    repo_dir = clone_root / normalize_repo_dir_name(repo_name)
    commit = str(row.get("our_latest_commit") or row.get("paper_latest_commit") or "")
    metric = str(row.get("metric", ""))
    time = str(row.get("time", ""))
    return (
        f"echo '=== {repo_name} {time} {metric} ==='\n"
        f"git -C '{repo_dir}' rev-parse --is-inside-work-tree\n"
        f"git -C '{repo_dir}' ls-tree -r --name-only {commit} | awk -F/ '{{print $1}}' | sort | uniq -c | sort -nr | head -30\n"
        f"git -C '{repo_dir}' ls-tree -r --name-only {commit} | grep -E '\\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l\n"
        f"git -C '{repo_dir}' show {commit}:sonar-project.properties 2>/dev/null || true\n"
        f"git -C '{repo_dir}' show {commit}:pyproject.toml 2>/dev/null | head -120 || true\n"
    )


def inspect_rows(selected: pd.DataFrame, args: argparse.Namespace) -> dict[str, pd.DataFrame | str]:
    """Inspect local repos for selected outlier rows."""
    treatment_root = Path(args.treatment_clone_root)
    control_root = Path(args.control_clone_root)

    tree_rows = []
    dir_rows = []
    config_rows = []
    command_lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    snippet_sections = []

    for idx, row in selected.iterrows():
        source_group = str(row.get("source_group", ""))
        repo_name = str(row.get("repo_name", ""))
        clone_root = treatment_root if source_group == "treatment" else control_root
        repo_path = clone_root / normalize_repo_dir_name(repo_name)
        repo_exists = repo_path.exists()

        selected.loc[idx, "local_repo_path"] = str(repo_path)
        selected.loc[idx, "local_repo_exists"] = repo_exists

        if not repo_exists:
            continue

        commits = []
        paper_commit = str(row.get("paper_latest_commit", ""))
        our_commit = str(row.get("our_latest_commit", ""))
        if paper_commit and paper_commit.lower() not in {"nan", "none"}:
            commits.append(("paper", paper_commit))
        if our_commit and our_commit.lower() not in {"nan", "none"} and our_commit != paper_commit:
            commits.append(("our", our_commit))
        if not commits and our_commit and our_commit.lower() not in {"nan", "none"}:
            commits.append(("our", our_commit))

        command_lines.append(build_manual_command(row, clone_root))
        command_lines.append("")

        for commit_label, commit in commits:
            files, error = list_tree_files(repo_path, commit)
            indicators = classify_paths(files)
            base = {
                "source_group": source_group,
                "repo_name": repo_name,
                "time": row.get("time", ""),
                "metric": row.get("metric", ""),
                "cause_category": row.get("cause_category", ""),
                "commit_label": commit_label,
                "commit": commit,
                "local_repo_path": str(repo_path),
                "git_error": error or "",
                **indicators,
            }
            tree_rows.append(base)

            for dir_info in summarize_top_dirs(files):
                dir_rows.append({**base, **dir_info})

            for cfg in collect_config_presence(repo_path, commit):
                config_rows.append({**base, **cfg})

            for cfg in CONFIG_CANDIDATES:
                text = git_show_file(repo_path, commit, cfg, args.max_config_chars)
                if not text:
                    continue
                snippet_sections.append(
                    f"## {repo_name} | {commit_label} | {commit} | {cfg}\n\n"
                    f"```text\n{text}\n```\n"
                )

    return {
        "selected": selected,
        "tree_summary": pd.DataFrame(tree_rows),
        "top_directories": pd.DataFrame(dir_rows),
        "config_presence": pd.DataFrame(config_rows),
        "manual_commands": "\n".join(command_lines),
        "config_snippets": "\n".join(snippet_sections),
    }


def write_notes(args: argparse.Namespace, selected: pd.DataFrame, tree_summary: pd.DataFrame) -> str:
    """Create a human-readable inspection note."""
    lines = [
        "# SonarQube outlier repository inspection notes",
        "",
        "## Purpose",
        "Inspect actual local repositories for the largest SonarQube differences between the paper data and the new Python pyv2 scan.",
        "",
        "## Interpretation guide",
        "- If a source-scope outlier has different tracked file counts or many generated/vendor/test files, source inclusion/exclusion is likely involved.",
        "- If an exact-commit and ncloc-identical outlier still has warning metric differences, SonarQube rule/config/analyzer/profile differences remain the strongest explanation.",
        "- Configuration files such as sonar-project.properties, pyproject.toml, setup.cfg, tox.ini, and .gitignore can explain local source-scope and analyzer behavior.",
        "",
        "## Selected inspection size",
        f"Selected rows: {len(selected)}",
        f"Selected unique repos: {selected['repo_name'].nunique() if 'repo_name' in selected.columns else 'NA'}",
        "",
    ]
    if len(tree_summary) > 0:
        lines.extend(
            [
                "## Git tree summary",
                f"Rows with Git tree summaries: {len(tree_summary)}",
                f"Repos with Git tree summaries: {tree_summary['repo_name'].nunique() if 'repo_name' in tree_summary.columns else 'NA'}",
                "",
            ]
        )
    return "\n".join(lines)


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """Save a dataframe to CSV, preserving empty outputs with headers when possible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local repos for SonarQube difference outlier diagnosis."
    )
    parser.add_argument("--top-repos-file", required=True)
    parser.add_argument("--negative-outliers-file", required=True)
    parser.add_argument("--positive-outliers-file", required=True)
    parser.add_argument("--treatment-clone-root", default="../treatment-repos")
    parser.add_argument("--control-clone-root", default="../control-repos")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=500)
    parser.add_argument("--max-repos", type=int, default=12)
    parser.add_argument("--max-config-chars", type=int, default=12000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outliers = load_outlier_rows(args)
    selected = select_inspection_rows(outliers, max_rows=args.top_n, max_repos=args.max_repos)
    results = inspect_rows(selected, args)

    selected_path = output_dir / "sonarqube_outlier_repo_inspection_selected_rows.csv"
    tree_path = output_dir / "sonarqube_outlier_repo_git_tree_summary.csv"
    dirs_path = output_dir / "sonarqube_outlier_repo_top_directories.csv"
    configs_path = output_dir / "sonarqube_outlier_repo_config_presence.csv"
    snippets_path = output_dir / "sonarqube_outlier_repo_config_snippets.md"
    commands_path = output_dir / "sonarqube_outlier_repo_manual_commands.sh"
    notes_path = output_dir / "sonarqube_outlier_repo_inspection_notes.md"

    save_dataframe(results["selected"], selected_path)
    save_dataframe(results["tree_summary"], tree_path)
    save_dataframe(results["top_directories"], dirs_path)
    save_dataframe(results["config_presence"], configs_path)

    snippets_path.write_text(str(results["config_snippets"]), encoding="utf-8")
    commands_path.write_text(str(results["manual_commands"]), encoding="utf-8")
    commands_path.chmod(0o755)
    notes_path.write_text(
        write_notes(args, results["selected"], results["tree_summary"]), encoding="utf-8"
    )

    print(f"Saved output directory: {output_dir}")
    print()
    print("Outlier repo inspection summary:")
    print(f"Selected rows: {len(results['selected'])}")
    if "repo_name" in results["selected"].columns:
        print(f"Selected unique repos: {results['selected']['repo_name'].nunique()}")
    if "local_repo_exists" in results["selected"].columns:
        print("Local repo exists counts:")
        print(results["selected"]["local_repo_exists"].value_counts(dropna=False).to_string())
    print()
    print("Key outputs:")
    for path in [selected_path, tree_path, dirs_path, configs_path, commands_path, notes_path]:
        print(path)


if __name__ == "__main__":
    main()
