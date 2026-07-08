#!/usr/bin/env python3
"""Summarize SonarQube outlier root causes at repository level.

This diagnostic script consumes the outputs from run-py-2b9 and run-py-2b10
and creates report-ready tables that connect metric differences to likely root
causes. It does not run SonarQube and does not modify repositories.

Inputs:
  - sonarqube_main_difference_drivers_top_repos_final_did.csv
  - sonarqube_outlier_repo_git_tree_summary.csv
  - sonarqube_outlier_repo_top_directories.csv
  - sonarqube_outlier_repo_config_presence.csv

Optional inputs:
  - original paper SonarQube script, usually scripts/run_sonarqube.py
  - current Python pyv2 SonarQube script, usually proc_scripts/run_sonarqube_v2.py

Outputs:
  - sonarqube_outlier_root_cause_by_repo.csv
  - sonarqube_outlier_root_cause_by_metric.csv
  - sonarqube_outlier_root_cause_evidence_table.csv
  - sonarqube_outlier_root_cause_notes.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


TREE_COUNT_COLS = [
    "tracked_files",
    "python_files",
    "notebook_files",
    "js_ts_files",
    "test_like_files",
    "doc_example_files",
    "generated_vendor_like_files",
]

WARNING_METRICS = {
    "bugs",
    "vulnerabilities",
    "code_smells",
    "technical_debt",
    "static_analysis_warnings",
}

CAUSE_PRIORITY = [
    "source_scope_difference_or_mixed",
    "rule_config_analyzer_profile_signal",
    "commit_selection_difference",
    "paper_commit_missing_or_unavailable",
    "our_only_or_paper_missing",
]

CONFIG_FILES_OF_INTEREST = [
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

SOURCE_SCOPE_DIR_HINTS = {
    "frontend",
    "plugin-server",
    "rust",
    "cypress",
    "tests",
    "test",
    "testing",
    "examples",
    "example",
    "docs",
    "doc",
    "website",
    "generated",
    "vendor",
    "third_party",
    "third-party",
    "migrations",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "notebooks",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize SonarQube outlier root causes at repository level."
    )
    parser.add_argument("--top-repos-file", required=True)
    parser.add_argument("--git-tree-summary-file", required=True)
    parser.add_argument("--top-directories-file", required=True)
    parser.add_argument("--config-presence-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--original-sonarqube-script", default=None)
    parser.add_argument("--pyv2-sonarqube-script", default=None)
    parser.add_argument("--top-dirs-per-repo", type=int, default=8)
    parser.add_argument("--top-print", type=int, default=30)
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def read_csv_checked(path: Path, label: str) -> pd.DataFrame:
    require_file(path, label)
    return pd.read_csv(path, dtype=str, low_memory=False)


def normalize_repo(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def first_existing_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def add_numeric_tree_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in TREE_COUNT_COLS:
        if col in out.columns:
            out[col] = to_number(out[col]).fillna(0)
        else:
            out[col] = 0
    return out


def safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    den2 = den.replace(0, pd.NA)
    return (num / den2).fillna(0)


def summarize_top_repo_drivers(top_repos: pd.DataFrame) -> pd.DataFrame:
    if top_repos.empty or "repo_name" not in top_repos.columns:
        return pd.DataFrame(columns=["repo_name"])

    df = top_repos.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])

    if "metric" not in df.columns:
        df["metric"] = "unknown_metric"
    if "cause_category" not in df.columns:
        df["cause_category"] = "unknown_cause"
    if "source_group" not in df.columns:
        df["source_group"] = "unknown_source_group"

    abs_col = first_existing_column(
        df,
        [
            "total_abs_diff",
            "sum_abs_diff",
            "abs_diff",
            "metric_abs_diff",
            "absolute_difference",
        ],
    )
    if abs_col is not None:
        df["_abs_diff_for_summary"] = to_number(df[abs_col]).fillna(0)
    else:
        df["_abs_diff_for_summary"] = 0

    def join_unique(values: pd.Series, limit: int = 12) -> str:
        items = []
        for value in values.dropna().astype(str):
            value = value.strip()
            if value and value not in items:
                items.append(value)
        return "; ".join(items[:limit])

    summary = (
        df.groupby("repo_name", as_index=False)
        .agg(
            driver_rows=("repo_name", "size"),
            source_group=("source_group", lambda x: join_unique(x, 4)),
            driver_metrics=("metric", lambda x: join_unique(x, 12)),
            cause_categories=("cause_category", lambda x: join_unique(x, 12)),
            driver_abs_diff_sum=("_abs_diff_for_summary", "sum"),
            driver_abs_diff_max=("_abs_diff_for_summary", "max"),
        )
    )

    cause_counts = (
        df.groupby(["repo_name", "cause_category"])
        .size()
        .reset_index(name="rows")
        .sort_values(["repo_name", "rows", "cause_category"], ascending=[True, False, True])
    )
    cause_text = (
        cause_counts.groupby("repo_name")
        .apply(lambda g: "; ".join(f"{r.cause_category}:{int(r.rows)}" for r in g.itertuples()))
        .reset_index(name="cause_row_counts")
    )
    return summary.merge(cause_text, on="repo_name", how="left")


def summarize_git_tree(tree: pd.DataFrame) -> pd.DataFrame:
    if tree.empty or "repo_name" not in tree.columns:
        return pd.DataFrame(columns=["repo_name"])

    df = add_numeric_tree_columns(tree)
    df["repo_name"] = normalize_repo(df["repo_name"])

    agg_dict = {
        "tree_rows": ("repo_name", "size"),
        "max_tracked_files": ("tracked_files", "max"),
        "max_python_files": ("python_files", "max"),
        "max_notebook_files": ("notebook_files", "max"),
        "max_js_ts_files": ("js_ts_files", "max"),
        "max_test_like_files": ("test_like_files", "max"),
        "max_doc_example_files": ("doc_example_files", "max"),
        "max_generated_vendor_like_files": ("generated_vendor_like_files", "max"),
    }

    if "time" in df.columns:
        agg_dict["months_observed"] = ("time", lambda x: x.dropna().nunique())
    if "commit" in df.columns:
        agg_dict["commits_observed"] = ("commit", lambda x: x.dropna().nunique())
    if "cause_category" in df.columns:
        agg_dict["tree_cause_categories"] = (
            "cause_category",
            lambda x: "; ".join(sorted(set(x.dropna().astype(str))))[:500],
        )

    summary = df.groupby("repo_name", as_index=False).agg(**agg_dict)

    summary["python_file_share"] = safe_ratio(
        summary["max_python_files"], summary["max_tracked_files"]
    )
    summary["js_ts_file_share"] = safe_ratio(
        summary["max_js_ts_files"], summary["max_tracked_files"]
    )
    summary["test_like_file_share"] = safe_ratio(
        summary["max_test_like_files"], summary["max_tracked_files"]
    )
    summary["doc_example_file_share"] = safe_ratio(
        summary["max_doc_example_files"], summary["max_tracked_files"]
    )
    summary["generated_vendor_file_share"] = safe_ratio(
        summary["max_generated_vendor_like_files"], summary["max_tracked_files"]
    )

    return summary


def summarize_top_directories(top_dirs: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if top_dirs.empty or "repo_name" not in top_dirs.columns or "top_dir" not in top_dirs.columns:
        return pd.DataFrame(columns=["repo_name"])

    df = top_dirs.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["top_dir"] = df["top_dir"].astype(str).str.strip()
    files_col = "files" if "files" in df.columns else None
    if files_col is None:
        df["files"] = 0
    else:
        df["files"] = to_number(df[files_col]).fillna(0)

    # A directory can appear in multiple selected rows. Use the maximum observed
    # file count per repo-directory to avoid counting the same tree repeatedly.
    dir_summary = (
        df.groupby(["repo_name", "top_dir"], as_index=False)
        .agg(max_files=("files", "max"))
        .sort_values(["repo_name", "max_files", "top_dir"], ascending=[True, False, True])
    )

    def top_dir_text(g: pd.DataFrame) -> str:
        return "; ".join(
            f"{row.top_dir}:{int(row.max_files)}" for row in g.head(top_n).itertuples()
        )

    def scope_hint_text(g: pd.DataFrame) -> str:
        hints = []
        for row in g.itertuples():
            name = str(row.top_dir).lower()
            if name in SOURCE_SCOPE_DIR_HINTS or any(h in name for h in SOURCE_SCOPE_DIR_HINTS):
                if row.top_dir not in hints:
                    hints.append(row.top_dir)
        return "; ".join(hints[:top_n])

    out = dir_summary.groupby("repo_name").apply(top_dir_text).reset_index(name="top_directories")
    hints = (
        dir_summary.groupby("repo_name")
        .apply(scope_hint_text)
        .reset_index(name="source_scope_hint_directories")
    )
    return out.merge(hints, on="repo_name", how="left")


def summarize_config_presence(config: pd.DataFrame) -> pd.DataFrame:
    if config.empty or "repo_name" not in config.columns or "config_file" not in config.columns:
        return pd.DataFrame(columns=["repo_name"])

    df = config.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["config_file"] = df["config_file"].astype(str).str.strip()
    if "exists_at_commit" in df.columns:
        exists = df["exists_at_commit"].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        exists = pd.Series(False, index=df.index)
    df["exists_bool"] = exists

    existing = df[df["exists_bool"]].copy()
    existing_summary = (
        existing.groupby("repo_name")["config_file"]
        .apply(lambda x: "; ".join(sorted(set(x.astype(str)))))
        .reset_index(name="existing_config_files")
    )

    all_repos = pd.DataFrame({"repo_name": sorted(df["repo_name"].dropna().unique())})
    out = all_repos.merge(existing_summary, on="repo_name", how="left")
    out["existing_config_files"] = out["existing_config_files"].fillna("")
    out["sonar_specific_config_present"] = out["existing_config_files"].str.contains(
        "sonar-project.properties|.sonarcloud.properties", regex=True, na=False
    )
    out["python_lint_config_present"] = out["existing_config_files"].str.contains(
        "pyproject.toml|setup.cfg|tox.ini|.flake8|.pylintrc|ruff.toml|.ruff.toml", regex=True, na=False
    )
    out["generic_repo_config_present"] = out["existing_config_files"].str.contains(
        ".gitignore|.pre-commit-config.yaml", regex=True, na=False
    )
    return out


def infer_root_cause(row: pd.Series) -> tuple[str, str, str]:
    causes = str(row.get("cause_categories", "")) + "; " + str(row.get("tree_cause_categories", ""))
    cause_counts = str(row.get("cause_row_counts", ""))

    source_scope_score = 0
    rule_config_score = 0
    commit_score = 0

    if "source_scope_difference_or_mixed" in causes or "source_scope_difference_or_mixed" in cause_counts:
        source_scope_score += 3
    if "rule_config_analyzer_profile_signal" in causes or "rule_config_analyzer_profile_signal" in cause_counts:
        rule_config_score += 3
    if "commit_selection_difference" in causes or "commit_selection_difference" in cause_counts:
        commit_score += 2

    tracked = float(row.get("max_tracked_files", 0) or 0)
    js_share = float(row.get("js_ts_file_share", 0) or 0)
    test_share = float(row.get("test_like_file_share", 0) or 0)
    doc_share = float(row.get("doc_example_file_share", 0) or 0)
    gen_share = float(row.get("generated_vendor_file_share", 0) or 0)
    hint_dirs = str(row.get("source_scope_hint_directories", ""))

    if tracked >= 5000:
        source_scope_score += 1
    if js_share >= 0.15:
        source_scope_score += 1
    if test_share >= 0.15:
        source_scope_score += 1
    if doc_share >= 0.15:
        source_scope_score += 1
    if gen_share >= 0.05:
        source_scope_score += 1
    if hint_dirs.strip():
        source_scope_score += 1

    if row.get("sonar_specific_config_present", False) is False:
        rule_config_score += 1
    if row.get("python_lint_config_present", False):
        rule_config_score += 1

    if source_scope_score >= rule_config_score and source_scope_score >= commit_score and source_scope_score >= 3:
        reason = "source_scope_inclusion_exclusion_difference"
        evidence = (
            "Large or mixed-language repository with source-scope directories/files; "
            "SonarQube inclusion/exclusion settings can change ncloc and warning counts."
        )
        recommendation = (
            "First mimic the paper scanner configuration: sonar.sources=. without the pyv2 "
            "language-specific exclusions; then run a small sensitivity scan that excludes "
            "frontend/tests/docs/examples/generated/vendor directories to quantify scope effects."
        )
    elif rule_config_score >= commit_score and rule_config_score >= 3:
        reason = "rule_config_analyzer_profile_difference"
        evidence = (
            "Warning metrics differ under controlled rows or no repo-level SonarQube config is present; "
            "rule set, quality profile, analyzer/plugin version, or scanner options are likely involved."
        )
        recommendation = (
            "Run paper-like scanner configuration first, then compare SonarQube server/analyzer version, "
            "quality profile, active rules, and Python analyzer options."
        )
    elif commit_score > 0:
        reason = "commit_selection_difference"
        evidence = "Paper and pyv2 selected different commits for at least some repo-month rows."
        recommendation = "Use paper latest_commit values for a targeted rescan before changing SonarQube rules."
    else:
        reason = "mixed_or_uncertain"
        evidence = "Multiple weak signals are present; no single root cause dominates."
        recommendation = "Inspect the largest repo-month rows manually and run one targeted paper-like scan."

    return reason, evidence, recommendation


def parse_sonar_flags(script_path: str | None) -> dict[str, str]:
    if not script_path:
        return {"path": "", "exists": "False", "sonar_flags": "", "notes": "not provided"}

    path = Path(script_path)
    if not path.exists():
        return {"path": str(path), "exists": "False", "sonar_flags": "", "notes": "file not found"}

    text = path.read_text(encoding="utf-8", errors="replace")
    flags = sorted(set(re.findall(r"-Dsonar\.[A-Za-z0-9_.-]+(?:=[^\"'\s,)]*)?", text)))
    selected = []
    for flag in flags:
        if any(
            key in flag
            for key in [
                "sonar.sources",
                "sonar.exclusions",
                "sonar.python.version",
                "sonar.java.binaries",
                "sonar.scm.disabled",
                "sonar.sourceEncoding",
            ]
        ):
            selected.append(flag)

    notes = []
    if "build_language_specific_sonar_args" in text:
        notes.append("language-specific helper present")
    if "wait_for_analysis_ready" in text:
        notes.append("waits for compute-engine readiness")
    if "sonar.exclusions" in text:
        notes.append("explicit exclusions present")
    if "sonar.python.version" in text:
        notes.append("explicit Python version present")

    return {
        "path": str(path),
        "exists": "True",
        "sonar_flags": "; ".join(selected),
        "notes": "; ".join(notes) if notes else "basic scanner flags only",
    }


def build_repo_summary(
    top_repos: pd.DataFrame,
    tree: pd.DataFrame,
    top_dirs: pd.DataFrame,
    config: pd.DataFrame,
    top_dirs_per_repo: int,
) -> pd.DataFrame:
    driver_summary = summarize_top_repo_drivers(top_repos)
    tree_summary = summarize_git_tree(tree)
    dir_summary = summarize_top_directories(top_dirs, top_dirs_per_repo)
    config_summary = summarize_config_presence(config)

    repo_names = set()
    for df in [driver_summary, tree_summary, dir_summary, config_summary]:
        if "repo_name" in df.columns:
            repo_names.update(df["repo_name"].dropna().astype(str).str.strip())

    out = pd.DataFrame({"repo_name": sorted(repo_names)})
    for df in [driver_summary, tree_summary, dir_summary, config_summary]:
        if not df.empty and "repo_name" in df.columns:
            out = out.merge(df, on="repo_name", how="left")

    for col in TREE_COUNT_COLS:
        max_col = f"max_{col}"
        if max_col in out.columns:
            out[max_col] = to_number(out[max_col]).fillna(0).astype(int)

    for col in [
        "python_file_share",
        "js_ts_file_share",
        "test_like_file_share",
        "doc_example_file_share",
        "generated_vendor_file_share",
    ]:
        if col in out.columns:
            out[col] = to_number(out[col]).fillna(0).round(4)

    for col in [
        "driver_rows",
        "driver_abs_diff_sum",
        "driver_abs_diff_max",
        "tree_rows",
        "months_observed",
        "commits_observed",
    ]:
        if col in out.columns:
            out[col] = to_number(out[col]).fillna(0)

    for col in ["sonar_specific_config_present", "python_lint_config_present", "generic_repo_config_present"]:
        if col in out.columns:
            out[col] = out[col].fillna(False).astype(bool)

    inferred = out.apply(infer_root_cause, axis=1, result_type="expand")
    inferred.columns = ["main_root_cause", "root_cause_evidence", "recommended_reconfiguration_step"]
    out = pd.concat([out, inferred], axis=1)

    sort_cols = [c for c in ["driver_abs_diff_sum", "max_tracked_files", "repo_name"] if c in out.columns]
    if sort_cols:
        ascending = [False if c != "repo_name" else True for c in sort_cols]
        out = out.sort_values(sort_cols, ascending=ascending)

    return out.reset_index(drop=True)


def build_metric_summary(top_repos: pd.DataFrame, repo_summary: pd.DataFrame) -> pd.DataFrame:
    if top_repos.empty:
        return pd.DataFrame()

    df = top_repos.copy()
    if "repo_name" in df.columns:
        df["repo_name"] = normalize_repo(df["repo_name"])
    else:
        df["repo_name"] = "unknown_repo"
    if "metric" not in df.columns:
        df["metric"] = "unknown_metric"
    if "cause_category" not in df.columns:
        df["cause_category"] = "unknown_cause"

    abs_col = first_existing_column(
        df,
        ["total_abs_diff", "sum_abs_diff", "abs_diff", "metric_abs_diff", "absolute_difference"],
    )
    if abs_col:
        df["abs_diff_for_summary"] = to_number(df[abs_col]).fillna(0)
    else:
        df["abs_diff_for_summary"] = 0

    repo_causes = repo_summary[["repo_name", "main_root_cause"]].drop_duplicates()
    df = df.merge(repo_causes, on="repo_name", how="left")

    out = (
        df.groupby(["metric", "cause_category", "main_root_cause"], dropna=False)
        .agg(
            rows=("repo_name", "size"),
            unique_repos=("repo_name", "nunique"),
            abs_diff_sum=("abs_diff_for_summary", "sum"),
            abs_diff_max=("abs_diff_for_summary", "max"),
        )
        .reset_index()
        .sort_values(["metric", "abs_diff_sum", "rows"], ascending=[True, False, False])
    )
    return out


def build_evidence_table(repo_summary: pd.DataFrame) -> pd.DataFrame:
    keep_cols = [
        "repo_name",
        "source_group",
        "driver_metrics",
        "main_root_cause",
        "root_cause_evidence",
        "recommended_reconfiguration_step",
        "max_tracked_files",
        "max_python_files",
        "max_js_ts_files",
        "max_test_like_files",
        "max_doc_example_files",
        "max_generated_vendor_like_files",
        "top_directories",
        "source_scope_hint_directories",
        "existing_config_files",
        "sonar_specific_config_present",
        "driver_abs_diff_sum",
        "cause_row_counts",
    ]
    keep_cols = [c for c in keep_cols if c in repo_summary.columns]
    return repo_summary[keep_cols].copy()


def write_notes(
    path: Path,
    repo_summary: pd.DataFrame,
    metric_summary: pd.DataFrame,
    original_config: dict[str, str],
    pyv2_config: dict[str, str],
    inputs: dict[str, str],
) -> None:
    counts = repo_summary["main_root_cause"].value_counts(dropna=False)
    top_repos = repo_summary.head(10)

    lines: list[str] = []
    lines.append("# SonarQube outlier root cause notes")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "Summarize repo-level evidence for why the new Python pyv2 SonarQube results differ from the paper data."
    )
    lines.append("")
    lines.append("## Inputs")
    for label, value in inputs.items():
        lines.append(f"- {label}: `{value}`")
    lines.append("")
    lines.append("## Scanner configuration comparison")
    lines.append("### Original paper scanner script")
    lines.append(f"- Path: `{original_config.get('path', '')}`")
    lines.append(f"- Exists: {original_config.get('exists', '')}")
    lines.append(f"- Key Sonar flags: {original_config.get('sonar_flags', '') or '(none parsed)'}")
    lines.append(f"- Notes: {original_config.get('notes', '')}")
    lines.append("")
    lines.append("### Current Python pyv2 scanner script")
    lines.append(f"- Path: `{pyv2_config.get('path', '')}`")
    lines.append(f"- Exists: {pyv2_config.get('exists', '')}")
    lines.append(f"- Key Sonar flags: {pyv2_config.get('sonar_flags', '') or '(none parsed)'}")
    lines.append(f"- Notes: {pyv2_config.get('notes', '')}")
    lines.append("")
    lines.append("## Root cause distribution")
    if counts.empty:
        lines.append("No repositories were summarized.")
    else:
        for reason, count in counts.items():
            lines.append(f"- {reason}: {int(count)} repos")
    lines.append("")
    lines.append("## Key interpretation")
    lines.append(
        "The first target for reproducing the paper should be a paper-like SonarQube scanner configuration: "
        "`sonar.sources=.` with no pyv2 language-specific exclusions and no explicit `sonar.python.version=3.11`."
    )
    lines.append(
        "If this reduces the gap for source-scope outliers, then pyv2 exclusions/source scope were a major driver. "
        "If warning counts still differ under the same commit and ncloc, compare SonarQube server version, language analyzer/plugin version, "
        "quality profile, and active rules."
    )
    lines.append("")
    lines.append("## Top repositories by summarized difference")
    if top_repos.empty:
        lines.append("No top repositories available.")
    else:
        for row in top_repos.itertuples(index=False):
            repo = getattr(row, "repo_name", "")
            reason = getattr(row, "main_root_cause", "")
            dirs = getattr(row, "top_directories", "")
            metrics = getattr(row, "driver_metrics", "")
            lines.append(f"- `{repo}`: {reason}; metrics={metrics}; dirs={dirs}")
    lines.append("")
    lines.append("## Recommended next step")
    lines.append(
        "Create a small `run-py-2b12` sensitivity scan for the highest-impact repositories. "
        "Start with the original paper-like scanner flags, then test one source-scope variant. "
        "Do not run a full rescan until the small sensitivity scan shows which configuration moves pyv2 metrics toward the paper values."
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    top_repos_path = Path(args.top_repos_file)
    tree_path = Path(args.git_tree_summary_file)
    dirs_path = Path(args.top_directories_file)
    config_path = Path(args.config_presence_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    top_repos = read_csv_checked(top_repos_path, "top repos file")
    tree = read_csv_checked(tree_path, "git tree summary file")
    top_dirs = read_csv_checked(dirs_path, "top directories file")
    config = read_csv_checked(config_path, "config presence file")

    repo_summary = build_repo_summary(
        top_repos=top_repos,
        tree=tree,
        top_dirs=top_dirs,
        config=config,
        top_dirs_per_repo=args.top_dirs_per_repo,
    )
    metric_summary = build_metric_summary(top_repos, repo_summary)
    evidence_table = build_evidence_table(repo_summary)

    by_repo_file = output_dir / "sonarqube_outlier_root_cause_by_repo.csv"
    by_metric_file = output_dir / "sonarqube_outlier_root_cause_by_metric.csv"
    evidence_file = output_dir / "sonarqube_outlier_root_cause_evidence_table.csv"
    notes_file = output_dir / "sonarqube_outlier_root_cause_notes.md"

    repo_summary.to_csv(by_repo_file, index=False)
    metric_summary.to_csv(by_metric_file, index=False)
    evidence_table.to_csv(evidence_file, index=False)

    original_config = parse_sonar_flags(args.original_sonarqube_script)
    pyv2_config = parse_sonar_flags(args.pyv2_sonarqube_script)
    write_notes(
        path=notes_file,
        repo_summary=repo_summary,
        metric_summary=metric_summary,
        original_config=original_config,
        pyv2_config=pyv2_config,
        inputs={
            "top_repos_file": str(top_repos_path),
            "git_tree_summary_file": str(tree_path),
            "top_directories_file": str(dirs_path),
            "config_presence_file": str(config_path),
            "original_sonarqube_script": str(args.original_sonarqube_script or ""),
            "pyv2_sonarqube_script": str(args.pyv2_sonarqube_script or ""),
        },
    )

    print("Saved output directory:", output_dir)
    print()
    print("Root cause summary:")
    if repo_summary.empty:
        print("No repositories summarized.")
    else:
        print(repo_summary["main_root_cause"].value_counts().to_string())
    print()
    print("Key outputs:")
    print(by_repo_file)
    print(by_metric_file)
    print(evidence_file)
    print(notes_file)
    print()
    print("Top evidence rows:")
    cols = [
        "repo_name",
        "source_group",
        "driver_metrics",
        "main_root_cause",
        "max_tracked_files",
        "max_python_files",
        "max_js_ts_files",
        "top_directories",
    ]
    cols = [c for c in cols if c in evidence_table.columns]
    if evidence_table.empty:
        print("(No rows.)")
    else:
        print(evidence_table[cols].head(args.top_print).to_string(index=False))


if __name__ == "__main__":
    main()
