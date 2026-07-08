#!/usr/bin/env python3
"""Compare SonarQube commit hashes and metrics between paper data and our pyv2 scan.

This diagnostic script answers two questions:
1. For the same repo-month, did the paper and our scan use the same latest_commit?
2. If the commit hashes match, do SonarQube metrics still differ?

The script is intended to be called by:
  compare/run-py-2b5-compare-sonarqube-commit-hash-with-paper.sh

Inputs:
  - Paper treatment monthly time series: data/ts_repos_monthly.csv
  - Paper control monthly time series: data/ts_repos_control_monthly.csv
  - Our treatment SonarQube scan output
  - Our control SonarQube scan output

Outputs are written under the requested output directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

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

KEY_COLUMNS = ["source_group", "repo_name", "time"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare paper treatment/control monthly time series with our "
            "SonarQube scan outputs using repo-month latest_commit hashes."
        )
    )
    parser.add_argument("--paper-treatment-ts", required=True)
    parser.add_argument("--paper-control-ts", required=True)
    parser.add_argument("--treatment-scan", required=True)
    parser.add_argument("--control-scan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument("--top-print", type=int, default=30)
    return parser.parse_args()


def clean_repo(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str[:7]
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def clean_commit(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str.lower()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat", "null"]))


def require_columns(df: pd.DataFrame, cols: Iterable[str], label: str) -> None:
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: {label} missing required columns: {missing}")


def read_monthly(path: Path, source_group: str, label: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")

    df = pd.read_csv(path, low_memory=False)
    require_columns(df, ["repo_name", "latest_commit"], label)

    if "month" in df.columns:
        month_col = "month"
    elif "time" in df.columns:
        month_col = "time"
    else:
        raise SystemExit(f"ERROR: {label} must contain either month or time column")

    out = df.copy()
    out["source_group"] = source_group
    out["repo_name"] = clean_repo(out["repo_name"])
    out["time"] = clean_month(out[month_col])
    out["latest_commit"] = clean_commit(out["latest_commit"])

    for metric in RAW_METRICS:
        if metric in out.columns:
            out[metric] = pd.to_numeric(out[metric], errors="coerce")
        else:
            out[metric] = pd.NA

    out["static_analysis_warnings"] = (
        pd.to_numeric(out["bugs"], errors="coerce").fillna(0)
        + pd.to_numeric(out["vulnerabilities"], errors="coerce").fillna(0)
        + pd.to_numeric(out["code_smells"], errors="coerce").fillna(0)
    )

    keep_cols = KEY_COLUMNS + ["latest_commit"] + ALL_METRICS
    out = out[keep_cols].dropna(subset=["repo_name", "time"]).copy()
    out = out[out["repo_name"].ne("")].copy()
    return out


def drop_duplicate_keys(df: pd.DataFrame, label: str) -> tuple[pd.DataFrame, int]:
    before = len(df)
    out = df.sort_values(KEY_COLUMNS).drop_duplicates(KEY_COLUMNS, keep="first").copy()
    duplicate_rows = before - len(out)
    if duplicate_rows > 0:
        print(f"WARNING: {label} has {duplicate_rows} duplicate source_group-repo-time rows; kept first row")
    return out, duplicate_rows


def classify_commit(row: pd.Series) -> str:
    paper = row.get("paper_latest_commit")
    ours = row.get("our_latest_commit")

    paper_missing = pd.isna(paper) or str(paper).strip() == ""
    our_missing = pd.isna(ours) or str(ours).strip() == ""

    if paper_missing and our_missing:
        return "both_commits_missing"
    if paper_missing:
        return "paper_commit_missing"
    if our_missing:
        return "our_commit_missing"

    paper_s = str(paper).strip().lower()
    our_s = str(ours).strip().lower()

    if paper_s == our_s:
        return "exact_match"

    # Be robust to cases where one side stores a shortened SHA.
    if paper_s.startswith(our_s) or our_s.startswith(paper_s):
        return "prefix_match"

    return "mismatch"


def build_comparison(paper: pd.DataFrame, ours: pd.DataFrame) -> pd.DataFrame:
    paper_renamed = paper.rename(
        columns={
            "latest_commit": "paper_latest_commit",
            **{metric: f"paper_{metric}" for metric in ALL_METRICS},
        }
    )
    our_renamed = ours.rename(
        columns={
            "latest_commit": "our_latest_commit",
            **{metric: f"our_{metric}" for metric in ALL_METRICS},
        }
    )

    comp = paper_renamed.merge(
        our_renamed,
        on=KEY_COLUMNS,
        how="outer",
        indicator=True,
    )

    comp["row_overlap_status"] = comp["_merge"].map(
        {
            "both": "both",
            "left_only": "paper_only",
            "right_only": "our_only",
        }
    )
    comp = comp.drop(columns=["_merge"])

    comp["commit_match_status"] = "not_comparable"
    both_mask = comp["row_overlap_status"].eq("both")
    comp.loc[both_mask, "commit_match_status"] = comp.loc[both_mask].apply(
        classify_commit,
        axis=1,
    )

    comp["commit_equal_or_prefix"] = comp["commit_match_status"].isin(
        ["exact_match", "prefix_match"]
    )

    for metric in ALL_METRICS:
        paper_col = f"paper_{metric}"
        our_col = f"our_{metric}"
        diff_col = f"diff_{metric}"
        abs_col = f"abs_diff_{metric}"
        comp[diff_col] = pd.to_numeric(comp[our_col], errors="coerce") - pd.to_numeric(
            comp[paper_col], errors="coerce"
        )
        comp[abs_col] = comp[diff_col].abs()

    return comp.sort_values(KEY_COLUMNS).reset_index(drop=True)


def summarize_overlap(paper: pd.DataFrame, ours: pd.DataFrame, comp: pd.DataFrame, paper_dups: int, our_dups: int) -> pd.DataFrame:
    both = comp[comp["row_overlap_status"].eq("both")].copy()
    summary = [
        ("paper_rows", len(paper)),
        ("paper_unique_repo_months", len(paper.drop_duplicates(KEY_COLUMNS))),
        ("paper_unique_repos", paper["repo_name"].nunique()),
        ("paper_duplicate_source_group_repo_month_rows", paper_dups),
        ("our_scan_rows", len(ours)),
        ("our_scan_unique_repo_months", len(ours.drop_duplicates(KEY_COLUMNS))),
        ("our_scan_unique_repos", ours["repo_name"].nunique()),
        ("our_scan_duplicate_source_group_repo_month_rows", our_dups),
        ("comparison_rows", len(comp)),
        ("overlap_repo_months", int(comp["row_overlap_status"].eq("both").sum())),
        ("paper_only_repo_months", int(comp["row_overlap_status"].eq("paper_only").sum())),
        ("our_only_repo_months", int(comp["row_overlap_status"].eq("our_only").sum())),
        ("commit_exact_match_rows", int(both["commit_match_status"].eq("exact_match").sum())),
        ("commit_prefix_match_rows", int(both["commit_match_status"].eq("prefix_match").sum())),
        ("commit_mismatch_rows", int(both["commit_match_status"].eq("mismatch").sum())),
        ("paper_commit_missing_rows", int(both["commit_match_status"].eq("paper_commit_missing").sum())),
        ("our_commit_missing_rows", int(both["commit_match_status"].eq("our_commit_missing").sum())),
        ("both_commits_missing_rows", int(both["commit_match_status"].eq("both_commits_missing").sum())),
    ]

    for group in ["treatment", "control"]:
        g = comp[comp["source_group"].eq(group)]
        gboth = g[g["row_overlap_status"].eq("both")]
        summary.extend(
            [
                (f"{group}_overlap_repo_months", int(g["row_overlap_status"].eq("both").sum())),
                (f"{group}_paper_only_repo_months", int(g["row_overlap_status"].eq("paper_only").sum())),
                (f"{group}_our_only_repo_months", int(g["row_overlap_status"].eq("our_only").sum())),
                (f"{group}_commit_exact_match_rows", int(gboth["commit_match_status"].eq("exact_match").sum())),
                (f"{group}_commit_prefix_match_rows", int(gboth["commit_match_status"].eq("prefix_match").sum())),
                (f"{group}_commit_mismatch_rows", int(gboth["commit_match_status"].eq("mismatch").sum())),
            ]
        )

    return pd.DataFrame(summary, columns=["metric", "value"])


def metric_summary_by_commit_status(comp: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    rows: list[dict] = []
    both = comp[comp["row_overlap_status"].eq("both")].copy()

    for status, part in both.groupby("commit_match_status", dropna=False):
        for metric in ALL_METRICS:
            paper_col = f"paper_{metric}"
            our_col = f"our_{metric}"
            diff_col = f"diff_{metric}"
            abs_col = f"abs_diff_{metric}"

            comparable = part[paper_col].notna() & part[our_col].notna()
            sub = part.loc[comparable].copy()
            if sub.empty:
                rows.append(
                    {
                        "commit_match_status": status,
                        "metric": metric,
                        "comparable_non_null": 0,
                        "identical_rows": 0,
                        "identical_share_among_non_null": pd.NA,
                        "mean_diff": pd.NA,
                        "median_abs_diff": pd.NA,
                        "max_abs_diff": pd.NA,
                    }
                )
                continue

            identical = sub[abs_col].le(tolerance)
            rows.append(
                {
                    "commit_match_status": status,
                    "metric": metric,
                    "comparable_non_null": int(len(sub)),
                    "identical_rows": int(identical.sum()),
                    "identical_share_among_non_null": float(identical.mean()),
                    "mean_diff": float(sub[diff_col].mean()),
                    "median_abs_diff": float(sub[abs_col].median()),
                    "max_abs_diff": float(sub[abs_col].max()),
                }
            )

    return pd.DataFrame(rows).sort_values(["commit_match_status", "metric"])


def long_metric_differences(comp: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    base_cols = [
        "source_group",
        "repo_name",
        "time",
        "row_overlap_status",
        "commit_match_status",
        "commit_equal_or_prefix",
        "paper_latest_commit",
        "our_latest_commit",
    ]

    both = comp[comp["row_overlap_status"].eq("both")].copy()

    for metric in ALL_METRICS:
        paper_col = f"paper_{metric}"
        our_col = f"our_{metric}"
        diff_col = f"diff_{metric}"
        abs_col = f"abs_diff_{metric}"
        cols = base_cols + [paper_col, our_col, diff_col, abs_col]
        tmp = both[cols].copy()
        tmp = tmp.rename(
            columns={
                paper_col: "paper_value",
                our_col: "our_value",
                diff_col: "diff",
                abs_col: "abs_diff",
            }
        )
        tmp.insert(3, "metric", metric)
        rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    out = out[out["paper_value"].notna() & out["our_value"].notna()].copy()
    out = out.sort_values(["abs_diff", "metric", "repo_name", "time"], ascending=[False, True, True, True])
    return out.reset_index(drop=True)


def write_notes(path: Path, summary: pd.DataFrame, metric_by_status: pd.DataFrame, top_print: int) -> None:
    values = dict(zip(summary["metric"], summary["value"]))

    lines = [
        "# SonarQube Commit Hash Comparison Notes",
        "",
        "## Purpose",
        "Compare paper monthly time-series latest_commit values with our pyv2 SonarQube scan latest_commit values.",
        "",
        "## Key counts",
        f"- Overlap repo-months: {values.get('overlap_repo_months', 'NA')}",
        f"- Commit exact matches: {values.get('commit_exact_match_rows', 'NA')}",
        f"- Commit prefix matches: {values.get('commit_prefix_match_rows', 'NA')}",
        f"- Commit mismatches: {values.get('commit_mismatch_rows', 'NA')}",
        f"- Paper-only repo-months: {values.get('paper_only_repo_months', 'NA')}",
        f"- Our-only repo-months: {values.get('our_only_repo_months', 'NA')}",
        "",
        "## Interpretation guide",
        "- If commit mismatches are common, metric differences can be explained by different checked-out commits.",
        "- If commits match but metrics differ, the likely cause is SonarQube version, plugin, scanner option, exclusion rule, or language profile differences.",
        "- static_analysis_warnings is computed as bugs + vulnerabilities + code_smells on both sides.",
        "",
        "## Metric difference summary by commit status",
    ]

    if metric_by_status.empty:
        lines.append("No comparable metric rows were found.")
    else:
        lines.append(metric_by_status.head(top_print).to_markdown(index=False))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paper_treatment = read_monthly(Path(args.paper_treatment_ts), "treatment", "paper treatment time series")
    paper_control = read_monthly(Path(args.paper_control_ts), "control", "paper control time series")
    our_treatment = read_monthly(Path(args.treatment_scan), "treatment", "our treatment scan")
    our_control = read_monthly(Path(args.control_scan), "control", "our control scan")

    paper_raw = pd.concat([paper_treatment, paper_control], ignore_index=True)
    ours_raw = pd.concat([our_treatment, our_control], ignore_index=True)

    paper, paper_dups = drop_duplicate_keys(paper_raw, "paper combined time series")
    ours, our_dups = drop_duplicate_keys(ours_raw, "our combined scan")

    comp = build_comparison(paper, ours)
    summary = summarize_overlap(paper, ours, comp, paper_dups, our_dups)
    metric_by_status = metric_summary_by_commit_status(comp, args.tolerance)
    long_diffs = long_metric_differences(comp)

    mismatch = comp[comp["commit_match_status"].eq("mismatch")].copy()
    match = comp[comp["commit_match_status"].isin(["exact_match", "prefix_match"])].copy()
    paper_only = comp[comp["row_overlap_status"].eq("paper_only")].copy()
    our_only = comp[comp["row_overlap_status"].eq("our_only")].copy()

    large = long_diffs.head(max(args.top_print, 1)).copy()

    summary.to_csv(output_dir / "sonarqube_commit_overlap_summary.csv", index=False)
    comp.to_csv(output_dir / "sonarqube_commit_hash_comparison.csv", index=False)
    mismatch.to_csv(output_dir / "sonarqube_commit_hash_mismatch.csv", index=False)
    match.to_csv(output_dir / "sonarqube_commit_hash_match.csv", index=False)
    paper_only.to_csv(output_dir / "sonarqube_commit_paper_only_repo_months.csv", index=False)
    our_only.to_csv(output_dir / "sonarqube_commit_our_only_repo_months.csv", index=False)
    metric_by_status.to_csv(output_dir / "sonarqube_metric_diff_by_commit_match_status.csv", index=False)
    long_diffs.to_csv(output_dir / "sonarqube_commit_hash_metric_differences_long.csv", index=False)
    large.to_csv(output_dir / "sonarqube_commit_hash_large_metric_differences.csv", index=False)
    write_notes(output_dir / "sonarqube_commit_hash_compare_notes.md", summary, metric_by_status, args.top_print)

    print(f"Saved output directory: {output_dir}")
    print()
    print("Commit overlap summary:")
    print(summary.to_string(index=False))
    print()
    print("Metric difference summary by commit status:")
    if metric_by_status.empty:
        print("(No comparable rows.)")
    else:
        print(metric_by_status.to_string(index=False))
    print()
    print(f"Top {args.top_print} large metric differences saved to:")
    print(output_dir / "sonarqube_commit_hash_large_metric_differences.csv")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
