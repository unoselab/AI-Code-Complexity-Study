#!/usr/bin/env python3
"""List repo-month rows in the modified paper-structure panel that do not exist in the paper panel.

Purpose:
  The 2b15 diagnostic panel reuses paper covariates when a repo-month key
  exists in data/panel_event_monthly.csv. This script identifies rows in
  repo_python/did_final/panel_event_monthly_modified_structure.csv whose
  (repo_name, time) key is absent from the paper panel.

Inputs:
  - Modified paper-structure panel CSV produced by run-py-2b15.
  - Paper frozen panel_event_monthly.csv.

Outputs:
  - CSV with unmatched repo-month rows and selected diagnostic columns.
  - CSV summary with matched/unmatched counts.

Notes:
  This script does not mutate the input files. It only recomputes the key
  match status using repo_name and normalized month time.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

KEY_COLUMNS = ["repo_name", "time"]
DEFAULT_PAPER_EXTRA_COLUMNS = [
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
DEFAULT_CONTEXT_COLUMNS = [
    "repo_name",
    "time",
    "is_treatment",
    "event",
    "post_event",
    "time_to_event",
    "cursor",
    "commits",
    "lines_added",
    "contributors",
    "dataset_source",
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "cognitive_complexity",
    "technical_debt",
]


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    """Parse a comma-separated CLI value into a list of column names."""
    if value is None or str(value).strip() == "":
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def normalize_month_value(value: object) -> str:
    """Normalize month keys to YYYY-MM where possible."""
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


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file with a clear error if it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    return pd.read_csv(path, low_memory=False)


def add_key_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized join keys without dropping original columns."""
    missing = [col for col in KEY_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required key columns: {missing}")
    out = df.copy()
    out["__join_repo_name"] = out["repo_name"].astype(str)
    out["__join_time"] = out["time"].map(normalize_month_value)
    return out


def select_existing_columns(df: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    """Return requested columns that exist in the dataframe, preserving order."""
    return [col for col in columns if col in df.columns]


def build_unmatched_rows(
    modified_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    context_columns: list[str],
    paper_extra_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute unmatched rows and summary statistics."""
    modified_keyed = add_key_columns(modified_df)
    paper_keyed = add_key_columns(paper_df)

    paper_keys = paper_keyed[["__join_repo_name", "__join_time"]].drop_duplicates()
    merged = modified_keyed.merge(
        paper_keys.assign(__paper_key_found=1),
        on=["__join_repo_name", "__join_time"],
        how="left",
    )

    merged["paper_key_found"] = merged["__paper_key_found"].fillna(0).astype(int)
    unmatched = merged[merged["paper_key_found"] == 0].copy()

    requested_columns = []
    for col in context_columns + paper_extra_columns:
        if col not in requested_columns:
            requested_columns.append(col)
    output_columns = select_existing_columns(unmatched, requested_columns)

    unmatched_out = unmatched[output_columns].copy()
    unmatched_out.insert(0, "paper_key_found", unmatched["paper_key_found"].values)
    unmatched_out.insert(1, "join_repo_name", unmatched["__join_repo_name"].values)
    unmatched_out.insert(2, "join_time", unmatched["__join_time"].values)

    missing_value_rows = []
    for col in paper_extra_columns:
        if col in unmatched.columns:
            missing_count = int(unmatched[col].isna().sum())
            non_missing_count = int(unmatched[col].notna().sum())
        else:
            missing_count = len(unmatched)
            non_missing_count = 0
        missing_value_rows.append(
            {
                "paper_extra_column": col,
                "unmatched_rows": len(unmatched),
                "non_missing_count_in_modified_panel": non_missing_count,
                "missing_count_in_modified_panel": missing_count,
            }
        )

    summary = pd.DataFrame(
        [
            {
                "modified_rows": len(modified_keyed),
                "paper_rows": len(paper_keyed),
                "paper_duplicate_repo_month_rows": int(
                    paper_keyed.duplicated(["__join_repo_name", "__join_time"]).sum()
                ),
                "matched_rows": int(merged["paper_key_found"].sum()),
                "unmatched_rows": int((merged["paper_key_found"] == 0).sum()),
            }
        ]
    )
    missing_summary = pd.DataFrame(missing_value_rows)
    return unmatched_out, pd.concat([summary, missing_summary], axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List modified-panel repo-month rows that do not match the paper panel."
    )
    parser.add_argument(
        "--modified-panel-file",
        required=True,
        help="Path to panel_event_monthly_modified_structure.csv.",
    )
    parser.add_argument(
        "--paper-panel-file",
        required=True,
        help="Path to paper data/panel_event_monthly.csv.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="CSV path for unmatched repo-month rows.",
    )
    parser.add_argument(
        "--summary-file",
        required=True,
        help="CSV path for match and missing-value summary.",
    )
    parser.add_argument(
        "--context-columns",
        default=",".join(DEFAULT_CONTEXT_COLUMNS),
        help="Comma-separated context columns to include when available.",
    )
    parser.add_argument(
        "--paper-extra-columns",
        default=",".join(DEFAULT_PAPER_EXTRA_COLUMNS),
        help="Comma-separated paper-extra columns to inspect.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of unmatched rows to print to stdout.",
    )
    args = parser.parse_args()

    modified_panel_file = Path(args.modified_panel_file)
    paper_panel_file = Path(args.paper_panel_file)
    output_file = Path(args.output_file)
    summary_file = Path(args.summary_file)

    context_columns = parse_csv_list(args.context_columns, DEFAULT_CONTEXT_COLUMNS)
    paper_extra_columns = parse_csv_list(args.paper_extra_columns, DEFAULT_PAPER_EXTRA_COLUMNS)

    modified_df = read_csv(modified_panel_file)
    paper_df = read_csv(paper_panel_file)

    unmatched_rows, summary = build_unmatched_rows(
        modified_df=modified_df,
        paper_df=paper_df,
        context_columns=context_columns,
        paper_extra_columns=paper_extra_columns,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    unmatched_rows.to_csv(output_file, index=False)
    summary.to_csv(summary_file, index=False)

    print("Created unmatched repo-month report")
    print(f"Modified panel file: {modified_panel_file}")
    print(f"Paper panel file:    {paper_panel_file}")
    print(f"Output file:         {output_file}")
    print(f"Summary file:        {summary_file}")
    print(f"Unmatched rows:      {len(unmatched_rows)}")

    if len(unmatched_rows) > 0:
        print("Top unmatched rows:")
        print(unmatched_rows.head(args.top_print).to_csv(index=False).rstrip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
