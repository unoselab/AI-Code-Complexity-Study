#!/usr/bin/env python3
"""
Summarize likely causes of SonarQube metric differences between paper data and our pyv2 scan.

This diagnostic script combines outputs from run-py-2b5, run-py-2b6, and run-py-2b7.
It does not run SonarQube again.

Main idea:
  - Commit mismatch suggests commit-selection difference.
  - Exact commit + different ncloc suggests source-scope difference.
  - Exact commit + identical ncloc + warning metric difference suggests rule/config/analyzer/profile difference.

Inputs:
  --commit-diff-long
      Long-format metric difference file from run-py-2b5.
  --exact-row-classification
      Exact-commit row classification file from run-py-2b6.
  --rule-config-subset
      Optional row subset from run-py-2b7.

Outputs:
  Several CSV and Markdown files summarizing cause categories, top repos, and outliers.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

KEY_COLS = ["source_group", "repo_name", "time"]
WARNING_METRICS = [
    "bugs",
    "vulnerabilities",
    "code_smells",
    "technical_debt",
    "static_analysis_warnings",
]
MAIN_METRICS = WARNING_METRICS + [
    "ncloc",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize likely causes of SonarQube metric differences."
    )
    parser.add_argument("--commit-diff-long", required=True)
    parser.add_argument("--exact-row-classification", required=True)
    parser.add_argument("--rule-config-subset", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=500)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    return parser.parse_args()


def read_csv_checked(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")
    return pd.read_csv(path, low_memory=False)


def normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in KEY_COLS:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
    if "time" in out.columns:
        out["time"] = out["time"].astype(str).str.strip().str[:7]
    return out


def to_numeric_safe(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise SystemExit(
            f"ERROR: {label} is missing columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def prepare_long_diff(diff_long: pd.DataFrame, exact_class: pd.DataFrame) -> pd.DataFrame:
    require_columns(
        diff_long,
        ["source_group", "repo_name", "time", "metric", "paper_value", "our_value"],
        "commit-diff long file",
    )

    diff = normalize_keys(diff_long)
    diff["metric"] = diff["metric"].astype(str).str.strip()

    for col in ["paper_value", "our_value"]:
        diff[col] = to_numeric_safe(diff[col])

    if "diff" not in diff.columns:
        diff["diff"] = diff["our_value"] - diff["paper_value"]
    else:
        diff["diff"] = to_numeric_safe(diff["diff"])

    if "abs_diff" not in diff.columns:
        diff["abs_diff"] = diff["diff"].abs()
    else:
        diff["abs_diff"] = to_numeric_safe(diff["abs_diff"])

    # Attach ncloc scope status from the exact-commit classifier when available.
    exact = normalize_keys(exact_class)
    attach_cols = [col for col in KEY_COLS + ["ncloc_scope_status"] if col in exact.columns]
    if set(KEY_COLS + ["ncloc_scope_status"]).issubset(set(attach_cols)):
        exact_attach = exact[KEY_COLS + ["ncloc_scope_status"]].drop_duplicates(KEY_COLS)
        if "ncloc_scope_status" not in diff.columns:
            diff = diff.merge(exact_attach, on=KEY_COLS, how="left")
        else:
            diff = diff.merge(
                exact_attach,
                on=KEY_COLS,
                how="left",
                suffixes=("", "_from_exact"),
            )
            diff["ncloc_scope_status"] = diff["ncloc_scope_status"].fillna(
                diff.get("ncloc_scope_status_from_exact")
            )
            if "ncloc_scope_status_from_exact" in diff.columns:
                diff.drop(columns=["ncloc_scope_status_from_exact"], inplace=True)

    if "commit_match_status" not in diff.columns:
        diff["commit_match_status"] = "unknown"
    if "row_overlap_status" not in diff.columns:
        diff["row_overlap_status"] = "unknown"
    if "ncloc_scope_status" not in diff.columns:
        diff["ncloc_scope_status"] = "unknown"

    diff["commit_match_status"] = diff["commit_match_status"].fillna("unknown").astype(str)
    diff["row_overlap_status"] = diff["row_overlap_status"].fillna("unknown").astype(str)
    diff["ncloc_scope_status"] = diff["ncloc_scope_status"].fillna("unknown").astype(str)

    return diff


def classify_cause(row: pd.Series) -> str:
    row_status = str(row.get("row_overlap_status", "unknown"))
    commit_status = str(row.get("commit_match_status", "unknown"))
    ncloc_status = str(row.get("ncloc_scope_status", "unknown"))

    if row_status == "paper_only":
        return "paper_only_repo_month"
    if row_status == "our_only":
        return "our_only_repo_month"

    if commit_status in {"mismatch", "commit_mismatch"}:
        return "commit_selection_difference"
    if commit_status == "paper_commit_missing":
        return "paper_commit_missing"
    if commit_status == "our_commit_missing":
        return "our_commit_missing"
    if commit_status == "both_commits_missing":
        return "both_commits_missing"

    if commit_status == "exact_match":
        if ncloc_status == "ncloc_identical":
            return "rule_config_analyzer_profile_signal"
        if ncloc_status in {"ncloc_close", "ncloc_different"}:
            return "source_scope_difference_or_mixed"
        if ncloc_status == "ncloc_missing":
            return "ncloc_missing_exact_commit"
        return "exact_commit_unknown_ncloc_status"

    return "unclassified"


def summarize_group(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec = dict(zip(group_cols, keys))
        comparable = group.dropna(subset=["paper_value", "our_value"])
        rec.update(
            rows=len(group),
            comparable_non_null=len(comparable),
            unique_repos=group["repo_name"].nunique() if "repo_name" in group.columns else np.nan,
            identical_rows=int((comparable["abs_diff"] <= 1e-9).sum()) if len(comparable) else 0,
            different_rows=int((comparable["abs_diff"] > 1e-9).sum()) if len(comparable) else 0,
            positive_diff_rows=int((comparable["diff"] > 1e-9).sum()) if len(comparable) else 0,
            negative_diff_rows=int((comparable["diff"] < -1e-9).sum()) if len(comparable) else 0,
            mean_diff=float(comparable["diff"].mean()) if len(comparable) else np.nan,
            median_diff=float(comparable["diff"].median()) if len(comparable) else np.nan,
            median_abs_diff=float(comparable["abs_diff"].median()) if len(comparable) else np.nan,
            p90_abs_diff=float(comparable["abs_diff"].quantile(0.90)) if len(comparable) else np.nan,
            p95_abs_diff=float(comparable["abs_diff"].quantile(0.95)) if len(comparable) else np.nan,
            max_abs_diff=float(comparable["abs_diff"].max()) if len(comparable) else np.nan,
            total_abs_diff=float(comparable["abs_diff"].sum()) if len(comparable) else 0.0,
            paper_mean=float(comparable["paper_value"].mean()) if len(comparable) else np.nan,
            our_mean=float(comparable["our_value"].mean()) if len(comparable) else np.nan,
        )
        if rec["comparable_non_null"] > 0:
            rec["different_share"] = rec["different_rows"] / rec["comparable_non_null"]
            rec["positive_diff_share"] = rec["positive_diff_rows"] / rec["comparable_non_null"]
            rec["negative_diff_share"] = rec["negative_diff_rows"] / rec["comparable_non_null"]
        else:
            rec["different_share"] = np.nan
            rec["positive_diff_share"] = np.nan
            rec["negative_diff_share"] = np.nan
        rows.append(rec)

    out = pd.DataFrame(rows)
    if not out.empty and "metric" in out.columns:
        metric_totals = out.groupby("metric")["total_abs_diff"].transform("sum")
        out["share_total_abs_diff_within_metric"] = np.where(
            metric_totals > 0,
            out["total_abs_diff"] / metric_totals,
            np.nan,
        )
    return out


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def build_top_repos(df: pd.DataFrame, metrics: list[str], top_n: int) -> pd.DataFrame:
    subset = df[df["metric"].isin(metrics)].copy()
    comparable = subset.dropna(subset=["paper_value", "our_value"])
    if comparable.empty:
        return pd.DataFrame()

    out = (
        comparable.groupby(["cause_category", "source_group", "repo_name", "metric"], dropna=False)
        .agg(
            rows=("metric", "size"),
            total_abs_diff=("abs_diff", "sum"),
            mean_diff=("diff", "mean"),
            median_abs_diff=("abs_diff", "median"),
            max_abs_diff=("abs_diff", "max"),
            positive_diff_rows=("diff", lambda x: int((x > 1e-9).sum())),
            negative_diff_rows=("diff", lambda x: int((x < -1e-9).sum())),
            paper_mean=("paper_value", "mean"),
            our_mean=("our_value", "mean"),
        )
        .reset_index()
        .sort_values(["metric", "total_abs_diff", "max_abs_diff"], ascending=[True, False, False])
    )
    return out.head(top_n)


def write_notes(path: Path, signal: pd.DataFrame, cause_metric: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("# SonarQube difference cause summary")
    lines.append("")
    lines.append("This diagnostic summarizes likely causes of paper-vs-pyv2 metric differences.")
    lines.append("")
    lines.append("## Interpretation rules")
    lines.append("")
    lines.append("- Commit mismatch suggests commit-selection difference.")
    lines.append("- Exact commit with different ncloc suggests source-scope difference or mixed source/config effects.")
    lines.append("- Exact commit with identical ncloc but warning-metric differences suggests rule/config/analyzer/profile difference.")
    lines.append("")
    lines.append("## Key signal")
    lines.append("")

    if not signal.empty:
        for _, row in signal.iterrows():
            metric = row.get("metric")
            if metric in WARNING_METRICS:
                lines.append(
                    f"- {metric}: cause={row.get('cause_category')}, "
                    f"rows={row.get('comparable_non_null')}, "
                    f"different_share={row.get('different_share')}, "
                    f"median_abs_diff={row.get('median_abs_diff')}, "
                    f"share_total_abs_diff_within_metric={row.get('share_total_abs_diff_within_metric')}"
                )

    lines.append("")
    lines.append("## Files to inspect next")
    lines.append("")
    lines.append("- sonarqube_difference_cause_summary_by_metric.csv")
    lines.append("- sonarqube_difference_cause_top_repos.csv")
    lines.append("- sonarqube_difference_cause_negative_outliers.csv")
    lines.append("- sonarqube_difference_cause_positive_outliers.csv")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    diff_long = read_csv_checked(Path(args.commit_diff_long), "commit-diff long file")
    exact_class = read_csv_checked(Path(args.exact_row_classification), "exact-row classification file")

    diff = prepare_long_diff(diff_long, exact_class)
    diff = diff[diff["metric"].isin(MAIN_METRICS)].copy()
    diff["cause_category"] = diff.apply(classify_cause, axis=1)

    # Main summaries.
    cause_summary = summarize_group(diff, ["cause_category"])
    cause_metric_summary = summarize_group(diff, ["metric", "cause_category"])
    cause_group_metric_summary = summarize_group(diff, ["metric", "cause_category", "source_group"])

    # Focused signal: exact commit + identical ncloc + warning metrics.
    rule_signal = cause_metric_summary[
        (cause_metric_summary["cause_category"] == "rule_config_analyzer_profile_signal")
        & (cause_metric_summary["metric"].isin(WARNING_METRICS))
    ].copy()

    top_repos = build_top_repos(diff, WARNING_METRICS, args.top_n)

    warning_diff = diff[
        diff["metric"].isin(["static_analysis_warnings", "code_smells"])
        & diff["paper_value"].notna()
        & diff["our_value"].notna()
        & (diff["abs_diff"] > args.tolerance)
    ].copy()

    negative = warning_diff[warning_diff["diff"] < -args.tolerance].copy()
    positive = warning_diff[warning_diff["diff"] > args.tolerance].copy()
    negative = negative.sort_values(["abs_diff", "repo_name", "time"], ascending=[False, True, True]).head(args.top_n)
    positive = positive.sort_values(["abs_diff", "repo_name", "time"], ascending=[False, True, True]).head(args.top_n)

    save_csv(diff, output_dir / "sonarqube_difference_cause_classified_long.csv")
    save_csv(cause_summary, output_dir / "sonarqube_difference_cause_summary.csv")
    save_csv(cause_metric_summary, output_dir / "sonarqube_difference_cause_summary_by_metric.csv")
    save_csv(cause_group_metric_summary, output_dir / "sonarqube_difference_cause_summary_by_source_group.csv")
    save_csv(rule_signal, output_dir / "sonarqube_difference_cause_rule_config_signal.csv")
    save_csv(top_repos, output_dir / "sonarqube_difference_cause_top_repos.csv")
    save_csv(negative, output_dir / "sonarqube_difference_cause_negative_outliers.csv")
    save_csv(positive, output_dir / "sonarqube_difference_cause_positive_outliers.csv")
    write_notes(output_dir / "sonarqube_difference_cause_notes.md", rule_signal, cause_metric_summary)

    print("Saved output directory:", output_dir)
    print()
    print("Cause summary:")
    print(cause_summary.to_string(index=False))
    print()
    print("Rule/config signal for warning metrics:")
    if rule_signal.empty:
        print("(No rule/config signal rows.)")
    else:
        cols = [
            "metric",
            "cause_category",
            "comparable_non_null",
            "different_share",
            "median_abs_diff",
            "p95_abs_diff",
            "max_abs_diff",
            "share_total_abs_diff_within_metric",
        ]
        cols = [c for c in cols if c in rule_signal.columns]
        print(rule_signal[cols].to_string(index=False))
    print()
    print("Key outputs:")
    print(output_dir / "sonarqube_difference_cause_summary_by_metric.csv")
    print(output_dir / "sonarqube_difference_cause_rule_config_signal.csv")
    print(output_dir / "sonarqube_difference_cause_top_repos.csv")
    print(output_dir / "sonarqube_difference_cause_notes.md")


if __name__ == "__main__":
    main()
