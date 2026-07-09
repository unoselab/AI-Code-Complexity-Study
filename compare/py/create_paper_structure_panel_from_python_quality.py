#!/usr/bin/env python3
"""Create a paper-schema panel from the Python quality DiD input.

This diagnostic script reshapes the regenerated Python quality DiD input into
exactly the same column order as the paper's data/panel_event_monthly.csv.
It preserves our regenerated SonarQube quality metrics and fills unavailable
paper covariates from the frozen paper panel when a matching repo-month exists.

Inputs:
  - Python strict quality DiD input CSV.
  - Paper frozen panel_event_monthly.csv.

Outputs:
  - panel_event_monthly_modified_structure.csv.
  - QC files describing column sources and paper-vs-our metric differences.

This is a diagnostic compatibility dataset, not a full reproduction dataset.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_FILL_FROM_PAPER = [
    "stars",
    "issues",
    "issue_comments",
    "age",
    "num_dependencies_total",
    "num_vulnerable_dependencies",
    "average_technical_lag",
    "other_agents",
    "high_confidence",
]

METRIC_COMPARE_COLUMNS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]

KEY_COLUMNS = ["repo_name", "time"]


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    if value is None or str(value).strip() == "":
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def normalize_month_value(value: object) -> str:
    """Normalize month keys to YYYY-MM when possible."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return text


def add_join_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "repo_name" not in out.columns or "time" not in out.columns:
        missing = [col for col in KEY_COLUMNS if col not in out.columns]
        raise ValueError(f"Missing required key columns: {missing}")
    out["repo_name"] = out["repo_name"].astype(str)
    out["time"] = out["time"].map(normalize_month_value)
    out["__join_repo_name"] = out["repo_name"]
    out["__join_time"] = out["time"]
    return out


def coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return pd.read_csv(path, low_memory=False)


def create_output_panel(
    input_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    fill_from_paper_columns: Iterable[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    input_df = add_join_keys(input_df)
    paper_df = add_join_keys(paper_df)
    paper_schema = [col for col in paper_df.columns if not col.startswith("__join_")]
    fill_from_paper_columns = set(fill_from_paper_columns)

    duplicate_paper_keys = int(
        paper_df.duplicated(["__join_repo_name", "__join_time"]).sum()
    )
    paper_keyed = paper_df.drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )

    fill_cols_available = [
        col for col in fill_from_paper_columns if col in paper_keyed.columns
    ]
    paper_fill = paper_keyed[
        ["__join_repo_name", "__join_time"] + fill_cols_available
    ].copy()
    paper_fill["__paper_match"] = 1

    merged = input_df.merge(
        paper_fill,
        on=["__join_repo_name", "__join_time"],
        how="left",
        suffixes=("", "__paper_fill"),
    )

    output = pd.DataFrame(index=merged.index)
    source_rows: list[dict[str, object]] = []

    for col in paper_schema:
        if col in input_df.columns:
            output[col] = merged[col]
            source = "python_input"
        elif col in fill_cols_available:
            output[col] = merged[col]
            source = "paper_panel_fill"
        else:
            output[col] = pd.NA
            source = "missing_set_na"

        missing_count = int(output[col].isna().sum())
        non_missing_count = int(output[col].notna().sum())
        source_rows.append(
            {
                "column": col,
                "source": source,
                "non_missing_count": non_missing_count,
                "missing_count": missing_count,
            }
        )

    if "time" in output.columns:
        output["time"] = output["time"].map(normalize_month_value)

    key_match_summary = pd.DataFrame(
        [
            {
                "input_rows": len(input_df),
                "paper_rows": len(paper_df),
                "output_rows": len(output),
                "output_columns": len(output.columns),
                "paper_schema_columns": len(paper_schema),
                "input_duplicate_repo_month_rows": int(
                    input_df.duplicated(["__join_repo_name", "__join_time"]).sum()
                ),
                "paper_duplicate_repo_month_rows": duplicate_paper_keys,
                "repo_month_rows_matched_to_paper": int(
                    merged["__paper_match"].fillna(0).astype(int).sum()
                ),
                "repo_month_rows_not_matched_to_paper": int(
                    merged["__paper_match"].isna().sum()
                ),
            }
        ]
    )

    column_sources = pd.DataFrame(source_rows)
    return output, column_sources, key_match_summary


def create_metric_comparison(
    output_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    metrics: Iterable[str],
) -> pd.DataFrame:
    output_keyed = add_join_keys(output_df)
    paper_keyed = add_join_keys(paper_df).drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )

    available_metrics = [
        metric for metric in metrics if metric in output_keyed.columns and metric in paper_keyed.columns
    ]
    if not available_metrics:
        return pd.DataFrame()

    merged = output_keyed[
        ["repo_name", "time", "__join_repo_name", "__join_time"] + available_metrics
    ].merge(
        paper_keyed[["__join_repo_name", "__join_time"] + available_metrics],
        on=["__join_repo_name", "__join_time"],
        how="inner",
        suffixes=("_our_modified", "_paper"),
    )

    rows: list[dict[str, object]] = []
    for metric in available_metrics:
        our_col = f"{metric}_our_modified"
        paper_col = f"{metric}_paper"
        our_values = coerce_numeric(merged[our_col])
        paper_values = coerce_numeric(merged[paper_col])
        diff = our_values - paper_values
        for idx in merged.index:
            rows.append(
                {
                    "repo_name": merged.at[idx, "repo_name"],
                    "time": merged.at[idx, "time"],
                    "metric": metric,
                    "our_modified_value": our_values.at[idx],
                    "paper_value": paper_values.at[idx],
                    "diff_our_minus_paper": diff.at[idx],
                    "abs_diff": abs(diff.at[idx]) if pd.notna(diff.at[idx]) else pd.NA,
                }
            )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["abs_diff", "repo_name", "time", "metric"], ascending=[False, True, True, True])
    return out


def write_notes(
    notes_path: Path,
    args: argparse.Namespace,
    output_df: pd.DataFrame,
    column_sources: pd.DataFrame,
    key_summary: pd.DataFrame,
    metric_comparison: pd.DataFrame,
) -> None:
    fill_count = int((column_sources["source"] == "paper_panel_fill").sum())
    input_count = int((column_sources["source"] == "python_input").sum())
    missing_count = int((column_sources["source"] == "missing_set_na").sum())

    lines = [
        "# run-py-2b15 paper-structure panel notes",
        "",
        "## Purpose",
        "",
        "Create a diagnostic CSV with the same column order as the paper `data/panel_event_monthly.csv`.",
        "The regenerated Python quality metrics are preserved, while unavailable paper covariates are filled from the frozen paper panel when repo-month keys match.",
        "",
        "## Inputs",
        "",
        f"- Python quality input: `{args.input_file}`",
        f"- Paper panel: `{args.paper_panel_file}`",
        "",
        "## Output",
        "",
        f"- Modified structure panel: `{args.output_file}`",
        "",
        "## Key summary",
        "",
        f"- Output rows: {len(output_df)}",
        f"- Output columns: {len(output_df.columns)}",
        f"- Columns copied from Python input: {input_count}",
        f"- Columns filled from paper panel: {fill_count}",
        f"- Columns set to NA: {missing_count}",
    ]

    if not key_summary.empty:
        summary = key_summary.iloc[0].to_dict()
        lines.extend(
            [
                f"- Repo-month rows matched to paper panel: {summary.get('repo_month_rows_matched_to_paper')}",
                f"- Repo-month rows not matched to paper panel: {summary.get('repo_month_rows_not_matched_to_paper')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation caution",
            "",
            "This file is for schema and Rmd-compatibility diagnostics only.",
            "It mixes regenerated Python SonarQube metrics with selected frozen paper covariates, so it should not be presented as a full paper reproduction dataset.",
            "",
            "## Largest paper-vs-our metric differences",
            "",
        ]
    )

    if metric_comparison.empty:
        lines.append("No metric comparison rows were created.")
    else:
        top = metric_comparison.head(10)
        for _, row in top.iterrows():
            lines.append(
                f"- {row['repo_name']} {row['time']} {row['metric']}: "
                f"our={row['our_modified_value']}, paper={row['paper_value']}, "
                f"diff={row['diff_our_minus_paper']}"
            )

    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a paper-schema panel from the Python quality DiD input."
    )
    parser.add_argument(
        "--input-file",
        default="repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv",
        help="Python quality DiD input CSV.",
    )
    parser.add_argument(
        "--paper-panel-file",
        default="data/panel_event_monthly.csv",
        help="Frozen paper panel_event_monthly.csv used as schema and covariate source.",
    )
    parser.add_argument(
        "--output-file",
        default="repo_python/did_final/panel_event_monthly_modified_structure.csv",
        help="Output CSV with the paper panel column structure.",
    )
    parser.add_argument(
        "--fill-from-paper-columns",
        default=",".join(DEFAULT_FILL_FROM_PAPER),
        help="Comma-separated columns to fill from the paper panel when missing in the Python input.",
    )
    parser.add_argument(
        "--metric-compare-columns",
        default=",".join(METRIC_COMPARE_COLUMNS),
        help="Comma-separated metrics for paper-vs-our comparison QC.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=20,
        help="Number of metric-difference rows to print.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    paper_path = Path(args.paper_panel_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fill_columns = parse_csv_list(args.fill_from_paper_columns, DEFAULT_FILL_FROM_PAPER)
    metric_columns = parse_csv_list(args.metric_compare_columns, METRIC_COMPARE_COLUMNS)

    input_df = safe_read_csv(input_path)
    paper_df = safe_read_csv(paper_path)

    output_df, column_sources, key_summary = create_output_panel(
        input_df=input_df,
        paper_df=paper_df,
        fill_from_paper_columns=fill_columns,
    )
    metric_comparison = create_metric_comparison(output_df, paper_df, metric_columns)

    output_df.to_csv(output_path, index=False)

    base = output_path.with_suffix("")
    column_sources_path = Path(f"{base}_column_sources.csv")
    key_summary_path = Path(f"{base}_key_match_summary.csv")
    metric_comparison_path = Path(f"{base}_metric_comparison.csv")
    notes_path = Path(f"{base}_notes.md")

    column_sources.to_csv(column_sources_path, index=False)
    key_summary.to_csv(key_summary_path, index=False)
    metric_comparison.to_csv(metric_comparison_path, index=False)
    write_notes(notes_path, args, output_df, column_sources, key_summary, metric_comparison)

    print("Created paper-structure diagnostic panel")
    print(f"Output file: {output_path}")
    print(f"Rows: {len(output_df)}")
    print(f"Columns: {len(output_df.columns)}")
    print(f"Column sources: {column_sources_path}")
    print(f"Key summary: {key_summary_path}")
    print(f"Metric comparison: {metric_comparison_path}")
    print(f"Notes: {notes_path}")

    if not metric_comparison.empty and args.top_print > 0:
        print("Top metric differences:")
        for _, row in metric_comparison.head(args.top_print).iterrows():
            print(
                f"  {row['repo_name']},{row['time']},{row['metric']},"
                f"our={row['our_modified_value']},paper={row['paper_value']},"
                f"diff={row['diff_our_minus_paper']}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
