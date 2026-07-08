#!/usr/bin/env python3
"""
Compare Python pyv2 SonarQube scan metrics against the paper panel.

Inputs:
  - Paper panel CSV containing repo_name, time, and SonarQube metric columns.
  - Our treatment SonarQube scan CSV containing repo_name, month, latest_commit, and metrics.
  - Our control SonarQube scan CSV containing repo_name, month, latest_commit, and metrics.

Outputs:
  - CSV diagnostics under the requested output directory.
  - A Markdown notes file summarizing overlap and metric differences.

Comparison key:
  - repo_name + month/time

Difference definition:
  - diff = our_value - paper_value
  - diff == 0 means identical within tolerance.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
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

KEY_COLUMNS = ["repo_name", "time"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare our pyv2 SonarQube metrics with the paper panel metrics."
    )
    parser.add_argument("--paper-panel", required=True, help="Paper panel_event_monthly.csv path.")
    parser.add_argument("--treatment-scan", required=True, help="Our treatment SonarQube scan CSV path.")
    parser.add_argument("--control-scan", required=True, help="Our control SonarQube scan CSV path.")
    parser.add_argument("--output-dir", required=True, help="Output directory for comparison files.")
    parser.add_argument("--panel-variant", default="strict", help="Panel variant label, e.g., strict.")
    parser.add_argument("--scan-suffix", default="pyv2", help="Scan suffix label, e.g., pyv2.")
    parser.add_argument("--tolerance", type=float, default=1e-9, help="Numeric tolerance for equality.")
    parser.add_argument("--top-n", type=int, default=500, help="Maximum large-difference rows to save.")
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise SystemExit(
            f"ERROR: {label} is missing columns: {missing}. Available columns: {list(df.columns)}"
        )


def normalize_repo(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def normalize_month(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str[:7]
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def to_numeric_metrics(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in metrics:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def add_static_analysis_warnings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    required = ["bugs", "vulnerabilities", "code_smells"]
    if all(col in out.columns for col in required):
        out["static_analysis_warnings"] = out[required].sum(axis=1, min_count=1)
    else:
        out["static_analysis_warnings"] = np.nan
    return out


def read_paper_panel(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(df, ["repo_name", "time", *RAW_METRICS], "paper panel")

    df = df.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["time"] = normalize_month(df["time"])
    df = df.dropna(subset=KEY_COLUMNS)
    df = to_numeric_metrics(df, RAW_METRICS)
    df = add_static_analysis_warnings(df)

    keep_extra = [col for col in ["is_treatment", "event", "post_event", "time_to_event", "dataset_source"] if col in df.columns]
    keep_cols = KEY_COLUMNS + keep_extra + ALL_METRICS
    df = df[keep_cols].copy()

    duplicated = df[df.duplicated(KEY_COLUMNS, keep=False)].copy()
    if not duplicated.empty:
        df = df.sort_values(KEY_COLUMNS).drop_duplicates(KEY_COLUMNS, keep="first").copy()

    return df, duplicated


def read_scan(path: Path, group_label: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(df, ["repo_name", "month", *RAW_METRICS], f"{group_label} scan")

    df = df.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["time"] = normalize_month(df["month"])
    df = df.dropna(subset=KEY_COLUMNS)
    df = to_numeric_metrics(df, RAW_METRICS)
    df = add_static_analysis_warnings(df)
    df["scan_group"] = group_label

    keep_extra = [col for col in ["latest_commit"] if col in df.columns]
    keep_cols = KEY_COLUMNS + ["scan_group"] + keep_extra + ALL_METRICS
    df = df[keep_cols].copy()

    df = df.sort_values(KEY_COLUMNS + ["scan_group"]).drop_duplicates(
        KEY_COLUMNS + ["scan_group"], keep="first"
    )
    return df


def make_wide_comparison(our_df: pd.DataFrame, paper_df: pd.DataFrame) -> pd.DataFrame:
    paper_cols = KEY_COLUMNS + [col for col in paper_df.columns if col not in KEY_COLUMNS]
    our_cols = KEY_COLUMNS + [col for col in our_df.columns if col not in KEY_COLUMNS]

    merged = our_df[our_cols].merge(
        paper_df[paper_cols],
        on=KEY_COLUMNS,
        how="left",
        suffixes=("_our", "_paper"),
        indicator="paper_match_status",
    )

    # Rename metrics to explicit our/paper names because suffixes only apply to overlapping columns.
    rename_map = {}
    for metric in ALL_METRICS:
        if metric in merged.columns:
            rename_map[metric] = f"{metric}_our"
        paper_metric = f"{metric}_paper"
        if paper_metric not in merged.columns and metric in paper_df.columns:
            # This branch is usually not needed because suffixes create metric_paper.
            pass
    merged = merged.rename(columns=rename_map)

    for metric in ALL_METRICS:
        our_col = f"{metric}_our"
        paper_col = f"{metric}_paper"
        diff_col = f"diff_{metric}"
        abs_col = f"abs_diff_{metric}"
        same_col = f"identical_{metric}"

        if our_col in merged.columns and paper_col in merged.columns:
            merged[diff_col] = merged[our_col] - merged[paper_col]
            merged[abs_col] = merged[diff_col].abs()
            merged[same_col] = merged[abs_col].le(1e-9)

    return merged


def make_row_level_comparison(wide: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    rows: list[dict] = []
    for metric in ALL_METRICS:
        our_col = f"{metric}_our"
        paper_col = f"{metric}_paper"
        if our_col not in wide.columns or paper_col not in wide.columns:
            continue

        temp = wide[KEY_COLUMNS + ["scan_group", "paper_match_status", our_col, paper_col]].copy()
        temp = temp.rename(columns={our_col: "our_value", paper_col: "paper_value"})
        temp["metric"] = metric
        temp["diff"] = temp["our_value"] - temp["paper_value"]
        temp["abs_diff"] = temp["diff"].abs()
        temp["identical"] = temp["abs_diff"].le(tolerance)
        rows.append(temp)

    if not rows:
        return pd.DataFrame(
            columns=KEY_COLUMNS + [
                "scan_group",
                "paper_match_status",
                "metric",
                "paper_value",
                "our_value",
                "diff",
                "abs_diff",
                "identical",
            ]
        )

    out = pd.concat(rows, ignore_index=True)
    out = out[
        KEY_COLUMNS
        + ["scan_group", "paper_match_status", "metric", "paper_value", "our_value", "diff", "abs_diff", "identical"]
    ]
    return out.sort_values(["metric", "scan_group", "repo_name", "time"]).reset_index(drop=True)


def summarize_differences(row_level: pd.DataFrame) -> pd.DataFrame:
    if row_level.empty:
        return pd.DataFrame()

    grouped = row_level.groupby("metric", dropna=False)
    summary = grouped.agg(
        compared_rows=("metric", "size"),
        rows_with_paper_match=("paper_match_status", lambda x: int((x == "both").sum())),
        paper_value_missing=("paper_value", lambda x: int(x.isna().sum())),
        our_value_missing=("our_value", lambda x: int(x.isna().sum())),
        comparable_non_null=("diff", lambda x: int(x.notna().sum())),
        identical_rows=("identical", lambda x: int(x.fillna(False).sum())),
        different_rows=("identical", lambda x: int((~x.fillna(False)).sum())),
        mean_paper=("paper_value", "mean"),
        mean_our=("our_value", "mean"),
        mean_diff=("diff", "mean"),
        median_diff=("diff", "median"),
        mean_abs_diff=("abs_diff", "mean"),
        median_abs_diff=("abs_diff", "median"),
        max_abs_diff=("abs_diff", "max"),
    ).reset_index()

    summary["identical_share_among_non_null"] = np.where(
        summary["comparable_non_null"] > 0,
        summary["identical_rows"] / summary["comparable_non_null"],
        np.nan,
    )
    return summary


def summarize_differences_by_group(row_level: pd.DataFrame) -> pd.DataFrame:
    if row_level.empty:
        return pd.DataFrame()

    grouped = row_level.groupby(["scan_group", "metric"], dropna=False)
    summary = grouped.agg(
        compared_rows=("metric", "size"),
        rows_with_paper_match=("paper_match_status", lambda x: int((x == "both").sum())),
        comparable_non_null=("diff", lambda x: int(x.notna().sum())),
        identical_rows=("identical", lambda x: int(x.fillna(False).sum())),
        mean_paper=("paper_value", "mean"),
        mean_our=("our_value", "mean"),
        mean_diff=("diff", "mean"),
        median_abs_diff=("abs_diff", "median"),
        max_abs_diff=("abs_diff", "max"),
    ).reset_index()

    summary["identical_share_among_non_null"] = np.where(
        summary["comparable_non_null"] > 0,
        summary["identical_rows"] / summary["comparable_non_null"],
        np.nan,
    )
    return summary


def build_overlap_summary(
    our_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    wide: pd.DataFrame,
    paper_duplicates: pd.DataFrame,
) -> pd.DataFrame:
    our_keys = set(map(tuple, our_df[KEY_COLUMNS].drop_duplicates().to_numpy()))
    paper_keys = set(map(tuple, paper_df[KEY_COLUMNS].drop_duplicates().to_numpy()))

    our_repos = set(our_df["repo_name"].dropna())
    paper_for_our_repos = paper_df[paper_df["repo_name"].isin(our_repos)].copy()
    paper_our_repo_keys = set(map(tuple, paper_for_our_repos[KEY_COLUMNS].drop_duplicates().to_numpy()))

    return pd.DataFrame(
        [
            {"metric": "our_scan_rows", "value": len(our_df)},
            {"metric": "our_scan_unique_repo_months", "value": len(our_keys)},
            {"metric": "our_scan_unique_repos", "value": our_df["repo_name"].nunique()},
            {"metric": "paper_panel_rows", "value": len(paper_df)},
            {"metric": "paper_panel_unique_repo_months", "value": len(paper_keys)},
            {"metric": "paper_panel_unique_repos", "value": paper_df["repo_name"].nunique()},
            {"metric": "overlap_repo_months", "value": len(our_keys & paper_keys)},
            {"metric": "our_repo_months_missing_in_paper", "value": len(our_keys - paper_keys)},
            {
                "metric": "paper_repo_months_for_our_repos_missing_in_ours",
                "value": len(paper_our_repo_keys - our_keys),
            },
            {"metric": "wide_rows", "value": len(wide)},
            {"metric": "wide_rows_with_paper_match", "value": int((wide["paper_match_status"] == "both").sum())},
            {"metric": "paper_duplicate_repo_month_rows", "value": len(paper_duplicates)},
        ]
    )


def write_notes(
    path: Path,
    args: argparse.Namespace,
    overlap_summary: pd.DataFrame,
    diff_summary: pd.DataFrame,
    by_group: pd.DataFrame,
) -> None:
    def get_metric(name: str) -> str:
        row = overlap_summary[overlap_summary["metric"] == name]
        if row.empty:
            return "NA"
        return str(row.iloc[0]["value"])

    lines = [
        "# SonarQube pyv2 vs paper panel comparison",
        "",
        "## Inputs",
        f"- Paper panel: `{args.paper_panel}`",
        f"- Treatment scan: `{args.treatment_scan}`",
        f"- Control scan: `{args.control_scan}`",
        f"- Panel variant: `{args.panel_variant}`",
        f"- Scan suffix: `{args.scan_suffix}`",
        "",
        "## Key definition",
        "- Comparison key: `repo_name + time`.",
        "- Difference: `diff = our_value - paper_value`.",
        "- A difference of 0 means identical within the configured tolerance.",
        "",
        "## Overlap summary",
        f"- Our unique repo-months: {get_metric('our_scan_unique_repo_months')}",
        f"- Paper unique repo-months: {get_metric('paper_panel_unique_repo_months')}",
        f"- Overlap repo-months: {get_metric('overlap_repo_months')}",
        f"- Our repo-months missing in paper: {get_metric('our_repo_months_missing_in_paper')}",
        f"- Paper repo-months for our repos missing in ours: {get_metric('paper_repo_months_for_our_repos_missing_in_ours')}",
        "",
        "## Metric difference summary",
    ]

    if not diff_summary.empty:
        keep = [
            "metric",
            "comparable_non_null",
            "identical_rows",
            "identical_share_among_non_null",
            "mean_diff",
            "median_abs_diff",
            "max_abs_diff",
        ]
        lines.extend(diff_summary[keep].to_markdown(index=False).splitlines())
    else:
        lines.append("No metric comparison rows were produced.")

    lines.extend(["", "## Metric difference by scan group"])
    if not by_group.empty:
        keep = [
            "scan_group",
            "metric",
            "comparable_non_null",
            "identical_rows",
            "identical_share_among_non_null",
            "mean_diff",
            "median_abs_diff",
            "max_abs_diff",
        ]
        lines.extend(by_group[keep].to_markdown(index=False).splitlines())
    else:
        lines.append("No group-level comparison rows were produced.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    paper_path = Path(args.paper_panel)
    treatment_path = Path(args.treatment_scan)
    control_path = Path(args.control_scan)
    output_dir = Path(args.output_dir)

    require_file(paper_path, "paper panel")
    require_file(treatment_path, "treatment scan")
    require_file(control_path, "control scan")

    output_dir.mkdir(parents=True, exist_ok=True)

    paper, paper_duplicates = read_paper_panel(paper_path)
    treatment = read_scan(treatment_path, "treatment")
    control = read_scan(control_path, "control")
    our = pd.concat([treatment, control], ignore_index=True)

    wide = make_wide_comparison(our, paper)
    row_level = make_row_level_comparison(wide, args.tolerance)
    diff_summary = summarize_differences(row_level)
    by_group = summarize_differences_by_group(row_level)
    overlap_summary = build_overlap_summary(our, paper, wide, paper_duplicates)

    missing_in_paper = wide[wide["paper_match_status"] == "left_only"].copy()

    our_keys = our[KEY_COLUMNS].drop_duplicates().copy()
    our_repos = set(our["repo_name"].dropna())
    paper_for_our_repos = paper[paper["repo_name"].isin(our_repos)].copy()
    missing_in_ours = paper_for_our_repos.merge(
        our_keys,
        on=KEY_COLUMNS,
        how="left",
        indicator=True,
    )
    missing_in_ours = missing_in_ours[missing_in_ours["_merge"] == "left_only"].drop(columns=["_merge"])

    large_diffs = row_level[
        row_level["paper_match_status"].eq("both") & row_level["diff"].notna() & (~row_level["identical"])
    ].sort_values("abs_diff", ascending=False).head(args.top_n)

    static_warning = row_level[row_level["metric"].eq("static_analysis_warnings")].copy()

    overlap_summary.to_csv(output_dir / "sonarqube_metric_overlap_summary.csv", index=False)
    diff_summary.to_csv(output_dir / "sonarqube_metric_difference_summary.csv", index=False)
    by_group.to_csv(output_dir / "sonarqube_metric_difference_by_group.csv", index=False)
    row_level.to_csv(output_dir / "sonarqube_metric_row_level_comparison.csv", index=False)
    wide.to_csv(output_dir / "sonarqube_metric_wide_comparison.csv", index=False)
    large_diffs.to_csv(output_dir / "sonarqube_metric_large_differences.csv", index=False)
    missing_in_paper.to_csv(output_dir / "sonarqube_missing_in_paper.csv", index=False)
    missing_in_ours.to_csv(output_dir / "sonarqube_missing_in_ours.csv", index=False)
    static_warning.to_csv(output_dir / "sonarqube_static_warning_comparison.csv", index=False)
    paper_duplicates.to_csv(output_dir / "paper_duplicate_repo_month_rows.csv", index=False)

    write_notes(
        output_dir / "sonarqube_compare_notes.md",
        args,
        overlap_summary,
        diff_summary,
        by_group,
    )

    print("Saved output directory:", output_dir)
    print()
    print("Overlap summary:")
    print(overlap_summary.to_string(index=False))
    print()
    print("Metric difference summary:")
    if diff_summary.empty:
        print("(empty)")
    else:
        print(
            diff_summary[
                [
                    "metric",
                    "comparable_non_null",
                    "identical_rows",
                    "identical_share_among_non_null",
                    "mean_diff",
                    "median_abs_diff",
                    "max_abs_diff",
                ]
            ].to_string(index=False)
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
