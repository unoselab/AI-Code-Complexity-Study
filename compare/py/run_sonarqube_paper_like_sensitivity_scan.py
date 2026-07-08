#!/usr/bin/env python3
"""Run a small SonarQube sensitivity scan using paper-like scanner settings.

This diagnostic script is intended for:
  compare/run-py-2b12-run-sonarqube-paper-like-sensitivity-scan.sh

Goal:
  Test whether paper-like SonarScanner flags move our pyv2 SonarQube metrics
  closer to the paper metrics for the highest-impact outlier repositories.

Inputs:
  - sonarqube_outlier_root_cause_evidence_table.csv from run-py-2b11
  - sonarqube_commit_hash_comparison.csv from run-py-2b5
  - local treatment/control clone directories

Outputs:
  - selected target repo-month-commit rows
  - scan results by configuration variant
  - metric-level distance-to-paper summary
  - failure diagnostics
  - human-readable notes

Important design:
  This script copies the scanner behavior of scripts/run_sonarqube.py for the
  paper_like variant. It does not call the original shell wrappers.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import git
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

SONAR_PATH = os.getenv("SONAR_SCANNER_PATH")
SONAR_TOKEN = os.getenv("SONAR_TOKEN")
SONAR_HOST = os.getenv("SONAR_HOST")

RAW_METRICS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]
DERIVED_METRICS = ["static_analysis_warnings"]
ALL_METRICS = RAW_METRICS + DERIVED_METRICS
SONAR_METRICS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "software_quality_maintainability_remediation_effort",
]

DEFAULT_VARIANTS = ["paper_like", "scope_exclude_common"]

COMMON_SCOPE_EXCLUSIONS = [
    "**/.git/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/env/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/.tox/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/coverage/**",
    "**/.next/**",
    "**/.nuxt/**",
    "**/frontend/**",
    "**/plugin-server/**",
    "**/static/**",
    "**/website/**",
    "**/examples/**",
    "**/docs/**",
    "**/doc/**",
    "**/tests/**",
    "**/test/**",
    "**/vendor/**",
    "**/third_party/**",
    "**/generated/**",
    "**/fixtures/**",
    "**/cypress/**",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run paper-like SonarQube sensitivity scans for top outlier repos."
    )
    parser.add_argument("--evidence-file", required=True)
    parser.add_argument("--comparison-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--treatment-clone-dir", default="../treatment-repos")
    parser.add_argument("--control-clone-dir", default="../control-repos")
    parser.add_argument("--project-key-prefix", default="py2b12_")
    parser.add_argument("--max-repos", type=int, default=5)
    parser.add_argument("--max-rows-per-repo", type=int, default=1)
    parser.add_argument("--top-print", type=int, default=30)
    parser.add_argument("--variants", default=",".join(DEFAULT_VARIANTS))
    parser.add_argument(
        "--commit-statuses",
        default="exact_match,prefix_match",
        help="Comma-separated commit_match_status values eligible for rescanning.",
    )
    parser.add_argument(
        "--rank-metrics",
        default="static_analysis_warnings,code_smells,technical_debt,ncloc",
        help="Comma-separated abs_diff_* columns used to choose repo-month target rows.",
    )
    parser.add_argument(
        "--rescan-existing",
        action="store_true",
        help="Run scanner even if an analysis with the same project version already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create target files and scanner command plan without running SonarQube.",
    )
    parser.add_argument("--metric-retry-attempts", type=int, default=5)
    parser.add_argument("--metric-retry-sleep", type=int, default=20)
    parser.add_argument("--sonar-timeout", type=int, default=1800)
    return parser.parse_args()


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def clean_repo(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str[:7]
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def clean_commit(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str.lower()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat", "null"]))


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: {label} missing required columns: {missing}")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def safe_key(text: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(text).strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned[:max_len - 11]}_{digest}"


def repo_dir_name(repo_name: str) -> str:
    return str(repo_name).replace("/", "_")


def resolve_repo_path(row: pd.Series, treatment_clone_dir: Path, control_clone_dir: Path) -> Path:
    root = control_clone_dir if str(row.get("source_group", "")).lower() == "control" else treatment_clone_dir
    return root / repo_dir_name(str(row["repo_name"]))


def load_evidence(path: Path) -> pd.DataFrame:
    require_file(path, "2b11 evidence file")
    df = pd.read_csv(path)
    require_columns(df, ["repo_name", "main_root_cause"], "2b11 evidence file")
    df = df.copy()
    df["repo_name"] = clean_repo(df["repo_name"])
    df["driver_abs_diff_sum_num"] = pd.to_numeric(df.get("driver_abs_diff_sum"), errors="coerce").fillna(0)
    df = df.dropna(subset=["repo_name"]).drop_duplicates("repo_name", keep="first")
    return df.sort_values("driver_abs_diff_sum_num", ascending=False).reset_index(drop=True)


def load_comparison(path: Path) -> pd.DataFrame:
    require_file(path, "2b5 comparison file")
    df = pd.read_csv(path, low_memory=False)
    require_columns(
        df,
        ["source_group", "repo_name", "time", "row_overlap_status", "commit_match_status"],
        "2b5 comparison file",
    )
    df = df.copy()
    df["repo_name"] = clean_repo(df["repo_name"])
    df["time"] = clean_month(df["time"])
    for col in ["paper_latest_commit", "our_latest_commit"]:
        if col in df.columns:
            df[col] = clean_commit(df[col])
        else:
            df[col] = pd.NA
    for metric in ALL_METRICS:
        for prefix in ["paper", "our", "diff", "abs_diff"]:
            col = f"{prefix}_{metric}"
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["repo_name", "time"]).reset_index(drop=True)


def choose_target_rows(
    evidence: pd.DataFrame,
    comparison: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    max_repos: int,
    max_rows_per_repo: int,
    commit_statuses: list[str],
    rank_metrics: list[str],
) -> pd.DataFrame:
    selected_repos = evidence.head(max_repos)[["repo_name", "main_root_cause", "driver_abs_diff_sum_num"]].copy()
    candidate = comparison.merge(selected_repos, on="repo_name", how="inner")
    candidate = candidate[candidate["row_overlap_status"].eq("both")].copy()
    candidate = candidate[candidate["commit_match_status"].isin(commit_statuses)].copy()

    if candidate.empty:
        raise SystemExit("ERROR: no comparable target rows found for selected repos.")

    score_cols = []
    for metric in rank_metrics:
        col = f"abs_diff_{metric}"
        if col in candidate.columns:
            candidate[col] = pd.to_numeric(candidate[col], errors="coerce").fillna(0)
            score_cols.append(col)

    if not score_cols:
        raise SystemExit("ERROR: none of the requested rank metrics exist in the comparison file.")

    candidate["target_score"] = candidate[score_cols].max(axis=1)
    candidate["scan_commit"] = candidate["paper_latest_commit"].fillna(candidate["our_latest_commit"])
    candidate = candidate.dropna(subset=["scan_commit"]).copy()

    candidate["repo_path"] = candidate.apply(
        lambda row: str(resolve_repo_path(row, treatment_clone_dir, control_clone_dir)),
        axis=1,
    )
    candidate["repo_path_exists"] = candidate["repo_path"].map(lambda p: Path(p).exists())
    candidate = candidate[candidate["repo_path_exists"]].copy()

    if candidate.empty:
        raise SystemExit("ERROR: target rows exist, but none has a local clone directory.")

    candidate = candidate.sort_values(["repo_name", "target_score"], ascending=[True, False])
    selected = candidate.groupby("repo_name", group_keys=False).head(max_rows_per_repo).copy()
    selected = selected.sort_values("target_score", ascending=False).reset_index(drop=True)
    selected.insert(0, "target_id", range(1, len(selected) + 1))
    return selected


def build_scanner_args(project_key: str, version: str, variant: str) -> list[str]:
    if not SONAR_PATH:
        raise RuntimeError("SONAR_SCANNER_PATH is not set.")
    if not SONAR_TOKEN:
        raise RuntimeError("SONAR_TOKEN is not set.")
    if not SONAR_HOST:
        raise RuntimeError("SONAR_HOST is not set.")

    cmd = [
        SONAR_PATH,
        f"-Dsonar.projectKey={project_key}",
        f"-Dsonar.projectName={project_key}",
        f"-Dsonar.projectVersion={version}",
        "-Dsonar.sources=.",
    ]

    if variant == "paper_like":
        pass
    elif variant == "paper_like_python_version":
        cmd.append("-Dsonar.python.version=3.11")
    elif variant == "scope_exclude_common":
        cmd.extend(
            [
                "-Dsonar.sourceEncoding=UTF-8",
                "-Dsonar.exclusions=" + ",".join(COMMON_SCOPE_EXCLUSIONS),
            ]
        )
    else:
        raise ValueError(
            f"Unsupported variant: {variant}. "
            "Use paper_like, paper_like_python_version, or scope_exclude_common."
        )

    cmd.extend(
        [
            "-Dsonar.java.binaries=.",
            f"-Dsonar.host.url={SONAR_HOST}",
            f"-Dsonar.token={SONAR_TOKEN}",
            "-Dsonar.scm.disabled=true",
        ]
    )
    return cmd


def check_analysis_exists(project_key: str, version: str) -> bool:
    try:
        page = 1
        while True:
            url = f"{SONAR_HOST}/api/project_analyses/search"
            auth = (SONAR_TOKEN, "")
            params = {"project": project_key, "category": "VERSION", "p": page, "ps": 100}
            response = requests.get(url, auth=auth, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            analyses = data.get("analyses", [])
            if not analyses:
                return False
            for analysis in analyses:
                if analysis.get("projectVersion") == version:
                    return True
            if len(analyses) < 100:
                return False
            page += 1
    except requests.exceptions.RequestException as exc:
        logging.warning("Could not check existing analysis for %s %s: %s", project_key, version, exc)
        return False


def get_analysis_date(project_key: str, version: str) -> str | None:
    page = 1
    while True:
        url = f"{SONAR_HOST}/api/project_analyses/search"
        auth = (SONAR_TOKEN, "")
        params = {"project": project_key, "category": "VERSION", "p": page, "ps": 100}
        response = requests.get(url, auth=auth, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        analyses = data.get("analyses", [])
        for analysis in analyses:
            if analysis.get("projectVersion") == version:
                return analysis.get("date")
        if len(analyses) < 100:
            return None
        page += 1


def get_sonar_metrics(project_key: str, version: str) -> dict[str, float] | None:
    try:
        analysis_date = get_analysis_date(project_key, version)
        if not analysis_date:
            return None
        url = f"{SONAR_HOST}/api/measures/search_history"
        auth = (SONAR_TOKEN, "")
        params = {
            "component": project_key,
            "metrics": ",".join(SONAR_METRICS),
            "from": analysis_date,
            "to": analysis_date,
        }
        response = requests.get(url, auth=auth, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        metrics: dict[str, float] = {}
        for measure in data.get("measures", []):
            history = measure.get("history", [])
            if history and "value" in history[0]:
                metric_name = measure.get("metric")
                if metric_name == "software_quality_maintainability_remediation_effort":
                    metric_name = "technical_debt"
                metrics[str(metric_name)] = float(history[0]["value"])
        if metrics:
            metrics["static_analysis_warnings"] = (
                metrics.get("bugs", 0.0)
                + metrics.get("vulnerabilities", 0.0)
                + metrics.get("code_smells", 0.0)
            )
        return metrics or None
    except requests.exceptions.RequestException as exc:
        logging.warning("Could not fetch metrics for %s %s: %s", project_key, version, exc)
        return None


def run_sonar_scan(repo_path: Path, commit_hash: str, project_key: str, version: str, variant: str, timeout: int) -> tuple[bool, str]:
    try:
        repo = git.Repo(str(repo_path))
        original_commit = repo.head.commit.hexsha
        repo.git.reset("--hard")
        repo.git.clean("-fd")
        repo.git.checkout(commit_hash, force=True)

        try:
            cmd = build_scanner_args(project_key, version, variant)
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
            if result.stdout:
                logging.info("scanner stdout for %s %s: %s", project_key, version, result.stdout[-1000:])
            return True, "ok"
        finally:
            repo.git.checkout(original_commit, force=True)
            repo.git.reset("--hard")
            repo.git.clean("-fd")
    except subprocess.CalledProcessError as exc:
        note = (exc.stderr or exc.stdout or str(exc)).replace("\n", " ")[:1000]
        return False, note
    except Exception as exc:
        return False, str(exc).replace("\n", " ")[:1000]


def build_target_variant_plan(targets: pd.DataFrame, variants: list[str], project_key_prefix: str) -> pd.DataFrame:
    rows: list[dict] = []
    for target in targets.itertuples(index=False):
        for variant in variants:
            digest_input = f"{target.repo_name}|{target.time}|{target.scan_commit}|{variant}"
            digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:10]
            repo_key = safe_key(str(target.repo_name).replace("/", "_"), max_len=60)
            month_key = str(target.time).replace("-", "")
            project_key = safe_key(f"{project_key_prefix}{repo_key}_{variant}_{month_key}_{digest}", max_len=180)
            version = f"{target.time}_{variant}_{str(target.scan_commit)[:10]}"
            rows.append(
                {
                    "target_id": target.target_id,
                    "variant": variant,
                    "project_key": project_key,
                    "project_version": version,
                    "source_group": target.source_group,
                    "repo_name": target.repo_name,
                    "time": target.time,
                    "scan_commit": target.scan_commit,
                    "commit_match_status": target.commit_match_status,
                    "main_root_cause": target.main_root_cause,
                    "target_score": target.target_score,
                    "repo_path": target.repo_path,
                }
            )
    return pd.DataFrame(rows)


def execute_plan(plan: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    output_rows: list[dict] = []

    for idx, row in enumerate(plan.itertuples(index=False), start=1):
        logging.info(
            "[%d/%d] %s %s %s %s",
            idx,
            len(plan),
            row.repo_name,
            row.time,
            row.variant,
            str(row.scan_commit)[:10],
        )

        base = row._asdict()
        base["dry_run"] = bool(args.dry_run)
        base["analysis_already_exists"] = False
        base["scan_success"] = False
        base["scan_note"] = "not_run"

        if args.dry_run:
            try:
                base["scanner_command"] = " ".join(build_scanner_args(row.project_key, row.project_version, row.variant))
            except Exception as exc:
                base["scanner_command"] = f"ERROR: {exc}"
            output_rows.append(base)
            continue

        exists = check_analysis_exists(row.project_key, row.project_version)
        base["analysis_already_exists"] = bool(exists)

        if exists and not args.rescan_existing:
            base["scan_success"] = True
            base["scan_note"] = "existing_analysis_reused"
        else:
            success, note = run_sonar_scan(
                repo_path=Path(row.repo_path),
                commit_hash=str(row.scan_commit),
                project_key=str(row.project_key),
                version=str(row.project_version),
                variant=str(row.variant),
                timeout=args.sonar_timeout,
            )
            base["scan_success"] = bool(success)
            base["scan_note"] = note

        metrics = None
        if base["scan_success"]:
            for attempt in range(1, args.metric_retry_attempts + 1):
                metrics = get_sonar_metrics(str(row.project_key), str(row.project_version))
                if metrics:
                    break
                if attempt < args.metric_retry_attempts:
                    time.sleep(args.metric_retry_sleep)

        if metrics:
            base["metrics_found"] = True
            for metric in ALL_METRICS:
                base[f"sensitivity_{metric}"] = metrics.get(metric)
        else:
            base["metrics_found"] = False
            for metric in ALL_METRICS:
                base[f"sensitivity_{metric}"] = pd.NA

        output_rows.append(base)

    return pd.DataFrame(output_rows)


def build_metric_differences(results: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    target_cols = [
        "target_id",
        "source_group",
        "repo_name",
        "time",
        "paper_latest_commit",
        "our_latest_commit",
        "scan_commit",
        "commit_match_status",
        "main_root_cause",
    ]
    metric_cols = []
    for metric in ALL_METRICS:
        for prefix in ["paper", "our"]:
            col = f"{prefix}_{metric}"
            if col in targets.columns:
                metric_cols.append(col)
    target_keep = targets[[col for col in target_cols + metric_cols if col in targets.columns]].copy()

    merged = results.merge(target_keep, on=["target_id", "source_group", "repo_name", "time", "scan_commit", "commit_match_status", "main_root_cause"], how="left")
    rows: list[dict] = []
    for rec in merged.itertuples(index=False):
        rec_dict = rec._asdict()
        for metric in ALL_METRICS:
            paper = pd.to_numeric(pd.Series([rec_dict.get(f"paper_{metric}")]), errors="coerce").iloc[0]
            ours = pd.to_numeric(pd.Series([rec_dict.get(f"our_{metric}")]), errors="coerce").iloc[0]
            sensitivity = pd.to_numeric(pd.Series([rec_dict.get(f"sensitivity_{metric}")]), errors="coerce").iloc[0]

            abs_our = abs(ours - paper) if pd.notna(ours) and pd.notna(paper) else pd.NA
            abs_sens = abs(sensitivity - paper) if pd.notna(sensitivity) and pd.notna(paper) else pd.NA
            improvement = pd.NA
            if pd.notna(abs_our) and pd.notna(abs_sens):
                improvement = abs_our - abs_sens

            rows.append(
                {
                    "target_id": rec_dict.get("target_id"),
                    "variant": rec_dict.get("variant"),
                    "source_group": rec_dict.get("source_group"),
                    "repo_name": rec_dict.get("repo_name"),
                    "time": rec_dict.get("time"),
                    "scan_commit": rec_dict.get("scan_commit"),
                    "commit_match_status": rec_dict.get("commit_match_status"),
                    "main_root_cause": rec_dict.get("main_root_cause"),
                    "metric": metric,
                    "paper_value": paper,
                    "our_pyv2_value": ours,
                    "sensitivity_value": sensitivity,
                    "abs_diff_our_to_paper": abs_our,
                    "abs_diff_sensitivity_to_paper": abs_sens,
                    "improvement_abs_diff": improvement,
                    "improved_vs_pyv2": bool(pd.notna(improvement) and improvement > 0),
                    "scan_success": rec_dict.get("scan_success"),
                    "metrics_found": rec_dict.get("metrics_found"),
                    "scan_note": rec_dict.get("scan_note"),
                }
            )
    out = pd.DataFrame(rows)
    return out.sort_values(["variant", "metric", "improvement_abs_diff"], ascending=[True, True, False]).reset_index(drop=True)


def summarize_by_variant_metric(metric_diffs: pd.DataFrame) -> pd.DataFrame:
    if metric_diffs.empty:
        return pd.DataFrame()
    df = metric_diffs.copy()
    for col in ["abs_diff_our_to_paper", "abs_diff_sensitivity_to_paper", "improvement_abs_diff"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    rows = []
    for (variant, metric), group in df.groupby(["variant", "metric"], dropna=False):
        comparable = group[group["abs_diff_sensitivity_to_paper"].notna()].copy()
        rows.append(
            {
                "variant": variant,
                "metric": metric,
                "target_metric_rows": int(len(group)),
                "comparable_rows": int(len(comparable)),
                "improved_rows": int(comparable["improved_vs_pyv2"].sum()) if len(comparable) else 0,
                "improved_share": float(comparable["improved_vs_pyv2"].mean()) if len(comparable) else pd.NA,
                "sum_abs_diff_our_to_paper": float(comparable["abs_diff_our_to_paper"].sum()) if len(comparable) else pd.NA,
                "sum_abs_diff_sensitivity_to_paper": float(comparable["abs_diff_sensitivity_to_paper"].sum()) if len(comparable) else pd.NA,
                "sum_improvement_abs_diff": float(comparable["improvement_abs_diff"].sum()) if len(comparable) else pd.NA,
                "median_abs_diff_sensitivity_to_paper": float(comparable["abs_diff_sensitivity_to_paper"].median()) if len(comparable) else pd.NA,
            }
        )
    return pd.DataFrame(rows).sort_values(["metric", "variant"]).reset_index(drop=True)


def write_notes(path: Path, args: argparse.Namespace, targets: pd.DataFrame, summary: pd.DataFrame, failures: pd.DataFrame) -> None:
    lines = [
        "# SonarQube paper-like sensitivity scan notes",
        "",
        "## Purpose",
        "Test whether a paper-like SonarScanner configuration moves pyv2 metrics closer to paper metrics for top outlier repo-month-commit rows.",
        "",
        "## Configuration variants",
        "- paper_like: `sonar.sources=.` plus original basic flags; no pyv2 exclusions; no explicit Python version.",
        "- paper_like_python_version: paper_like plus `sonar.python.version=3.11` when requested.",
        "- scope_exclude_common: paper_like plus common source-scope exclusions for frontend/tests/docs/examples/generated/vendor-like directories.",
        "",
        "## Inputs",
        f"- evidence_file: `{args.evidence_file}`",
        f"- comparison_file: `{args.comparison_file}`",
        "",
        "## Target selection",
        f"- selected target rows: {len(targets)}",
        f"- unique repos: {targets['repo_name'].nunique() if not targets.empty else 0}",
        f"- variants: {args.variants}",
        f"- dry_run: {args.dry_run}",
        "",
        "## Interpretation guide",
        "- If paper_like reduces distance to paper for ncloc and warning metrics, pyv2 exclusions/source scope were a major driver.",
        "- If ncloc becomes close to paper but warning metrics remain far, compare SonarQube server version, language analyzer/plugin version, quality profile, and active rules.",
        "- If scope_exclude_common moves metrics away from paper, the paper likely included directories that pyv2 excluded.",
        "",
    ]

    if not summary.empty:
        lines.extend(["## Summary by variant and metric", summary.to_markdown(index=False), ""])
    if not failures.empty:
        lines.extend(["## Failures", failures.head(args.top_print).to_markdown(index=False), ""])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.dry_run:
        missing_env = [name for name, value in [("SONAR_SCANNER_PATH", SONAR_PATH), ("SONAR_TOKEN", SONAR_TOKEN), ("SONAR_HOST", SONAR_HOST)] if not value]
        if missing_env:
            raise SystemExit(f"ERROR: missing required SonarQube environment variables: {missing_env}")

    variants = split_csv(args.variants)
    commit_statuses = split_csv(args.commit_statuses)
    rank_metrics = split_csv(args.rank_metrics)

    evidence = load_evidence(Path(args.evidence_file))
    comparison = load_comparison(Path(args.comparison_file))
    targets = choose_target_rows(
        evidence=evidence,
        comparison=comparison,
        treatment_clone_dir=Path(args.treatment_clone_dir),
        control_clone_dir=Path(args.control_clone_dir),
        max_repos=args.max_repos,
        max_rows_per_repo=args.max_rows_per_repo,
        commit_statuses=commit_statuses,
        rank_metrics=rank_metrics,
    )
    plan = build_target_variant_plan(targets, variants, args.project_key_prefix)

    save_csv(targets, output_dir / "sonarqube_paper_like_sensitivity_targets.csv")
    save_csv(plan, output_dir / "sonarqube_paper_like_sensitivity_plan.csv")

    results = execute_plan(plan, args)
    metric_diffs = build_metric_differences(results, targets)
    summary = summarize_by_variant_metric(metric_diffs)
    failures = results[(~results["scan_success"].fillna(False)) | (~results["metrics_found"].fillna(False))].copy()

    save_csv(results, output_dir / "sonarqube_paper_like_sensitivity_results.csv")
    save_csv(metric_diffs, output_dir / "sonarqube_paper_like_sensitivity_metric_differences.csv")
    save_csv(summary, output_dir / "sonarqube_paper_like_sensitivity_by_variant_metric.csv")
    save_csv(failures, output_dir / "sonarqube_paper_like_sensitivity_failures.csv")
    write_notes(output_dir / "sonarqube_paper_like_sensitivity_notes.md", args, targets, summary, failures)

    print(f"Saved output directory: {output_dir}")
    print()
    print("Selected targets:")
    print(targets[["target_id", "source_group", "repo_name", "time", "scan_commit", "main_root_cause", "target_score"]].head(args.top_print).to_string(index=False))
    print()
    print("Variant summary:")
    if summary.empty:
        print("(No summary rows.)")
    else:
        print(summary.to_string(index=False))
    print()
    print("Failures:", len(failures))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
