#!/usr/bin/env python3
"""Identify the main drivers of SonarQube metric differences.

This diagnostic script summarizes why our Python pyv2 SonarQube metrics differ
from the paper's frozen data. It uses outputs from the earlier comparison steps:

Inputs:
  - sonarqube_commit_hash_metric_differences_long.csv
  - sonarqube_exact_commit_row_classification.csv
  - sonarqube_rule_config_row_subset.csv
  - final DiD input CSV

Outputs:
  - cause-level summaries for all overlap rows
  - cause-level summaries restricted to final DiD input rows
  - treatment/post and event-time summaries for final DiD input rows
  - top outlier repositories and positive/negative outlier rows
  - a short markdown diagnosis note
"""

from __future__ import annotations

import argparse
import sys
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
PRIMARY_METRICS = [
    "static_analysis_warnings",
    "code_smells",
    "technical_debt",
    "bugs",
    "vulnerabilities",
    "ncloc",
    "cognitive_complexity",
    "duplicated_lines_density",
    "comment_lines_density",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identify the main drivers of SonarQube paper-vs-pyv2 differences."
    )
    parser.add_argument("--commit-diff-long", required=True)
    parser.add_argument("--exact-row-classification", required=True)
    parser.add_argument("--rule-config-subset", required=True)
    parser.add_argument("--final-did-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=500)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    return parser.parse_args()


def read_csv_required(path: str | Path, label: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing required {label}: {path}")
    return pd.read_csv(path)


def normalize_key_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["repo_name", "time", "source_group"]:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
    if "source_group" in out.columns:
        out["source_group"] = out["source_group"].str.lower()
    return out


def add_source_group_to_final(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "source_group" in out.columns:
        out["source_group"] = out["source_group"].astype(str).str.strip().str.lower()
        return out
    if "dataset_source" in out.columns:
        out["source_group"] = out["dataset_source"].astype(str).str.strip().str.lower()
        return out
    if "is_treatment" in out.columns:
        out["source_group"] = np.where(out["is_treatment"].astype(float) == 1.0, "treatment", "control")
        return out
    raise ValueError("Final DiD input must contain source_group, dataset_source, or is_treatment.")


def make_rule_config_key_set(rule_subset: pd.DataFrame) -> set[tuple[str, str, str]]:
    available = [col for col in KEY_COLS if col in rule_subset.columns]
    if set(available) != set(KEY_COLS):
        return set()
    tmp = normalize_key_columns(rule_subset[KEY_COLS].drop_duplicates())
    return set(map(tuple, tmp[KEY_COLS].to_numpy()))


def attach_cause_categories(
    diff_long: pd.DataFrame,
    exact_classification: pd.DataFrame,
    rule_config_subset: pd.DataFrame,
) -> pd.DataFrame:
    diff = normalize_key_columns(diff_long)
    cls = normalize_key_columns(exact_classification)

    class_cols = [col for col in KEY_COLS + ["ncloc_scope_status"] if col in cls.columns]
    if "ncloc_scope_status" not in class_cols:
        raise ValueError("exact row classification must contain ncloc_scope_status.")

    cls_small = cls[class_cols].drop_duplicates(KEY_COLS)
    out = diff.merge(cls_small, on=KEY_COLS, how="left")

    rule_keys = make_rule_config_key_set(rule_config_subset)

    def infer(row: pd.Series) -> str:
        status = str(row.get("commit_match_status", "")).strip()
        scope = str(row.get("ncloc_scope_status", "")).strip()
        key = (str(row.get("source_group", "")).strip().lower(), str(row.get("repo_name", "")).strip(), str(row.get("time", "")).strip())

        if status == "mismatch":
            return "commit_selection_difference"
        if status == "paper_commit_missing":
            return "paper_commit_missing"
        if status == "our_commit_missing":
            return "our_commit_missing"
        if status == "both_commits_missing":
            return "both_commits_missing"
        if status == "exact_match":
            if key in rule_keys or scope == "ncloc_identical":
                return "rule_config_analyzer_profile_signal"
            if scope == "ncloc_missing":
                return "ncloc_missing_exact_commit"
            if scope in {"ncloc_close", "ncloc_different"}:
                return "source_scope_difference_or_mixed"
            return "exact_commit_unknown_ncloc_status"
        return "other_or_unclassified"

    out["cause_category"] = out.apply(infer, axis=1)
    return out


def safe_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def summarize_by(df: pd.DataFrame, group_cols: list[str], tolerance: float) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=group_cols)

    data = safe_numeric(df, ["paper_value", "our_value", "diff", "abs_diff"])
    records = []
    grouped = data.groupby(group_cols, dropna=False)

    for keys, g in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        comparable = g[g["paper_value"].notna() & g["our_value"].notna()].copy()
        diffs = comparable["diff"].dropna()
        abs_diffs = comparable["abs_diff"].dropna()
        different_mask = comparable["abs_diff"].fillna(0) > tolerance

        record = dict(zip(group_cols, keys))
        record.update(
            {
                "rows": int(len(g)),
                "comparable_non_null": int(len(comparable)),
                "unique_repos": int(g["repo_name"].nunique()) if "repo_name" in g.columns else np.nan,
                "identical_rows": int((comparable["abs_diff"].fillna(0) <= tolerance).sum()),
                "different_rows": int(different_mask.sum()),
                "positive_diff_rows": int((comparable["diff"] > tolerance).sum()),
                "negative_diff_rows": int((comparable["diff"] < -tolerance).sum()),
                "mean_diff": float(diffs.mean()) if len(diffs) else np.nan,
                "median_diff": float(diffs.median()) if len(diffs) else np.nan,
                "median_abs_diff": float(abs_diffs.median()) if len(abs_diffs) else np.nan,
                "p90_abs_diff": float(abs_diffs.quantile(0.90)) if len(abs_diffs) else np.nan,
                "p95_abs_diff": float(abs_diffs.quantile(0.95)) if len(abs_diffs) else np.nan,
                "max_abs_diff": float(abs_diffs.max()) if len(abs_diffs) else np.nan,
                "total_abs_diff": float(abs_diffs.sum()) if len(abs_diffs) else 0.0,
                "paper_mean": float(comparable["paper_value"].mean()) if len(comparable) else np.nan,
                "our_mean": float(comparable["our_value"].mean()) if len(comparable) else np.nan,
            }
        )
        if len(comparable):
            record["different_share"] = record["different_rows"] / len(comparable)
            record["positive_diff_share"] = record["positive_diff_rows"] / len(comparable)
            record["negative_diff_share"] = record["negative_diff_rows"] / len(comparable)
        else:
            record["different_share"] = np.nan
            record["positive_diff_share"] = np.nan
            record["negative_diff_share"] = np.nan
        records.append(record)

    result = pd.DataFrame(records)
    if "metric" in result.columns:
        totals = result.groupby("metric")["total_abs_diff"].transform("sum")
        result["share_total_abs_diff_within_metric"] = np.where(totals > 0, result["total_abs_diff"] / totals, 0.0)
    return result


def attach_final_did_metadata(diff_with_cause: pd.DataFrame, final_did: pd.DataFrame) -> pd.DataFrame:
    final_norm = normalize_key_columns(add_source_group_to_final(final_did))
    metadata_cols = [
        col
        for col in [
            "source_group",
            "repo_name",
            "time",
            "is_treatment",
            "post_event",
            "time_to_event",
            "event",
            "dataset_source",
        ]
        if col in final_norm.columns
    ]
    final_keys = final_norm[metadata_cols].drop_duplicates(KEY_COLS)
    merged = diff_with_cause.merge(final_keys, on=KEY_COLS, how="inner", suffixes=("", "_final"))
    return merged


def write_notes(
    out_dir: Path,
    overall: pd.DataFrame,
    final_metric: pd.DataFrame,
    final_by_group: pd.DataFrame,
) -> None:
    lines = []
    lines.append("# SonarQube Difference Main Driver Diagnosis")
    lines.append("")
    lines.append("This report summarizes likely causes of paper-vs-pyv2 SonarQube metric differences.")
    lines.append("")

    if not overall.empty:
        cause_total = overall.groupby("cause_category", as_index=False)["total_abs_diff"].sum()
        cause_total = cause_total.sort_values("total_abs_diff", ascending=False)
        lines.append("## Overall cause ranking by total absolute metric difference")
        for _, row in cause_total.iterrows():
            lines.append(f"- {row['cause_category']}: total_abs_diff={row['total_abs_diff']:.3f}")
        lines.append("")

    if not final_metric.empty:
        lines.append("## Final DiD input cause ranking by primary metrics")
        for metric in PRIMARY_METRICS:
            sub = final_metric[final_metric["metric"] == metric].sort_values("total_abs_diff", ascending=False)
            if sub.empty:
                continue
            top = sub.iloc[0]
            lines.append(
                f"- {metric}: top_cause={top['cause_category']}, "
                f"share_total_abs_diff={top.get('share_total_abs_diff_within_metric', np.nan):.3f}, "
                f"different_share={top.get('different_share', np.nan):.3f}"
            )
        lines.append("")

    if not final_by_group.empty:
        lines.append("## Final DiD group interpretation")
        lines.append(
            "Use sonarqube_main_difference_drivers_final_did_by_treatment_post.csv "
            "to check whether differences concentrate in treatment-post rows, "
            "which can directly alter the DiD trajectory."
        )
        lines.append("")

    lines.append("## Interpretation")
    lines.append(
        "If source_scope_difference_or_mixed dominates total_abs_diff, large metric differences are mainly linked to "
        "rows where ncloc differs or source inclusion/exclusion differs."
    )
    lines.append(
        "If rule_config_analyzer_profile_signal remains large for warning metrics, the evidence supports differences in "
        "SonarQube rules, quality profile, analyzer/plugin version, or scanner configuration even under the same commit and ncloc."
    )
    lines.append(
        "If differences concentrate in treatment-post rows, they are more likely to affect the final ATT trajectory."
    )
    lines.append("")

    (out_dir / "sonarqube_main_difference_drivers_notes.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    diff_long = read_csv_required(args.commit_diff_long, "commit-difference long file")
    exact_classification = read_csv_required(args.exact_row_classification, "exact-row classification file")
    rule_subset = read_csv_required(args.rule_config_subset, "rule-config subset file")
    final_did = read_csv_required(args.final_did_input, "final DiD input file")

    diff_with_cause = attach_cause_categories(diff_long, exact_classification, rule_subset)
    diff_with_cause = safe_numeric(diff_with_cause, ["paper_value", "our_value", "diff", "abs_diff"])

    overall_by_cause = summarize_by(diff_with_cause, ["cause_category"], args.tolerance)
    overall_by_metric = summarize_by(diff_with_cause, ["metric", "cause_category"], args.tolerance)
    warning_overall = overall_by_metric[overall_by_metric["metric"].isin(WARNING_METRICS)].copy()

    final_diff = attach_final_did_metadata(diff_with_cause, final_did)
    final_by_cause = summarize_by(final_diff, ["cause_category"], args.tolerance)
    final_by_metric = summarize_by(final_diff, ["metric", "cause_category"], args.tolerance)
    final_warning = final_by_metric[final_by_metric["metric"].isin(WARNING_METRICS)].copy()

    group_cols = ["metric", "cause_category"]
    if "is_treatment" in final_diff.columns:
        group_cols.append("is_treatment")
    if "post_event" in final_diff.columns:
        group_cols.append("post_event")
    final_by_treat_post = summarize_by(final_diff, group_cols, args.tolerance)

    if "time_to_event" in final_diff.columns:
        final_by_event_time = summarize_by(final_diff, ["metric", "cause_category", "time_to_event"], args.tolerance)
    else:
        final_by_event_time = pd.DataFrame()

    final_top_repos = summarize_by(final_diff, ["cause_category", "source_group", "repo_name", "metric"], args.tolerance)
    if not final_top_repos.empty:
        final_top_repos = final_top_repos.sort_values("total_abs_diff", ascending=False).head(args.top_n)

    final_outlier_cols = [
        col
        for col in [
            "cause_category",
            "source_group",
            "repo_name",
            "time",
            "metric",
            "commit_match_status",
            "ncloc_scope_status",
            "paper_latest_commit",
            "our_latest_commit",
            "paper_value",
            "our_value",
            "diff",
            "abs_diff",
            "is_treatment",
            "post_event",
            "time_to_event",
        ]
        if col in final_diff.columns
    ]
    final_outliers = final_diff[final_outlier_cols].copy()
    final_outliers = safe_numeric(final_outliers, ["diff", "abs_diff"])
    final_negative = final_outliers[final_outliers["diff"] < -args.tolerance].sort_values("abs_diff", ascending=False).head(args.top_n)
    final_positive = final_outliers[final_outliers["diff"] > args.tolerance].sort_values("abs_diff", ascending=False).head(args.top_n)
    final_abs = final_outliers.sort_values("abs_diff", ascending=False).head(args.top_n)

    coverage_records = [
        {"metric": "all_comparison_metric_rows", "value": len(diff_with_cause)},
        {"metric": "all_comparison_unique_repo_months", "value": diff_with_cause[KEY_COLS].drop_duplicates().shape[0]},
        {"metric": "final_did_metric_rows_with_comparison", "value": len(final_diff)},
        {"metric": "final_did_unique_repo_months_with_comparison", "value": final_diff[KEY_COLS].drop_duplicates().shape[0]},
        {"metric": "final_did_unique_repos_with_comparison", "value": final_diff["repo_name"].nunique()},
    ]
    if "metric" in final_diff.columns:
        for metric in PRIMARY_METRICS:
            coverage_records.append(
                {
                    "metric": f"final_did_rows_for_{metric}",
                    "value": int((final_diff["metric"] == metric).sum()),
                }
            )
    coverage = pd.DataFrame(coverage_records)

    diff_with_cause.to_csv(out_dir / "sonarqube_main_difference_drivers_all_rows_long.csv", index=False)
    final_diff.to_csv(out_dir / "sonarqube_main_difference_drivers_final_did_rows_long.csv", index=False)
    overall_by_cause.to_csv(out_dir / "sonarqube_main_difference_drivers_overall_by_cause.csv", index=False)
    overall_by_metric.to_csv(out_dir / "sonarqube_main_difference_drivers_overall_by_metric.csv", index=False)
    warning_overall.to_csv(out_dir / "sonarqube_main_difference_drivers_warning_metrics_overall.csv", index=False)
    final_by_cause.to_csv(out_dir / "sonarqube_main_difference_drivers_final_did_by_cause.csv", index=False)
    final_by_metric.to_csv(out_dir / "sonarqube_main_difference_drivers_final_did_by_metric.csv", index=False)
    final_warning.to_csv(out_dir / "sonarqube_main_difference_drivers_warning_metrics_final_did.csv", index=False)
    final_by_treat_post.to_csv(out_dir / "sonarqube_main_difference_drivers_final_did_by_treatment_post.csv", index=False)
    final_by_event_time.to_csv(out_dir / "sonarqube_main_difference_drivers_final_did_by_event_time.csv", index=False)
    final_top_repos.to_csv(out_dir / "sonarqube_main_difference_drivers_top_repos_final_did.csv", index=False)
    final_negative.to_csv(out_dir / "sonarqube_main_difference_drivers_negative_outliers_final_did.csv", index=False)
    final_positive.to_csv(out_dir / "sonarqube_main_difference_drivers_positive_outliers_final_did.csv", index=False)
    final_abs.to_csv(out_dir / "sonarqube_main_difference_drivers_abs_outliers_final_did.csv", index=False)
    coverage.to_csv(out_dir / "sonarqube_main_difference_drivers_coverage_summary.csv", index=False)

    write_notes(out_dir, overall_by_metric, final_by_metric, final_by_treat_post)

    print(f"Saved output directory: {out_dir}")
    print("\nFinal DiD cause summary:")
    if not final_by_cause.empty:
        print(final_by_cause.sort_values("total_abs_diff", ascending=False).to_string(index=False))
    else:
        print("No final DiD comparison rows were available.")

    print("\nFinal DiD warning metric drivers:")
    if not final_warning.empty:
        display_cols = [
            "metric",
            "cause_category",
            "comparable_non_null",
            "different_share",
            "median_abs_diff",
            "share_total_abs_diff_within_metric",
            "total_abs_diff",
        ]
        print(final_warning[display_cols].sort_values(["metric", "total_abs_diff"], ascending=[True, False]).to_string(index=False))
    else:
        print("No final DiD warning metric rows were available.")

    print("\nKey outputs:")
    for name in [
        "sonarqube_main_difference_drivers_final_did_by_cause.csv",
        "sonarqube_main_difference_drivers_final_did_by_metric.csv",
        "sonarqube_main_difference_drivers_final_did_by_treatment_post.csv",
        "sonarqube_main_difference_drivers_top_repos_final_did.csv",
        "sonarqube_main_difference_drivers_notes.md",
    ]:
        print(out_dir / name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
