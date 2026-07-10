#!/usr/bin/env python3
"""Prepare analysis-ready Python quality DiD inputs.

The script performs two related tasks:

1. Build the existing quality DiD input, complete-case output, missing-row
   output, and QC summary from a merged SonarQube panel.
2. Optionally convert the complete-case output into the exact column order of
   the paper's data/panel_event_monthly.csv. During this optional conversion,
   regenerated SonarQube metrics remain unchanged, while selected columns that
   are unavailable in the regenerated Python panel are filled from the frozen
   paper panel using exact repo-month keys.

The optional paper-schema output is a diagnostic overlap dataset. It is not a
full independent reproduction dataset because it combines regenerated Python
SonarQube outcomes with selected frozen paper covariates.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


KEY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
]

PAPER_JOIN_COLS = [
    "repo_name",
    "time",
]

BASE_DID_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "ever_treated",
    "is_treatment",
    "post_event",
]

CORE_QUALITY_OUTCOMES = [
    "static_analysis_warnings",
    "duplicate_line_density",
    "code_complexity",
]

RATE_OUTCOMES = [
    "warnings_per_kloc",
    "complexity_per_kloc",
    "code_smells_per_kloc",
]

OPTIONAL_QUALITY_OUTCOMES = [
    "technical_debt",
    "ncloc",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "bugs",
    "vulnerabilities",
    "code_smells",
]

LOG_OUTCOME_MAP = {
    "static_analysis_warnings": "log_static_analysis_warnings",
    "code_complexity": "log_code_complexity",
    "technical_debt": "log_technical_debt",
    "ncloc": "log_ncloc",
    "bugs": "log_bugs",
    "vulnerabilities": "log_vulnerabilities",
    "code_smells": "log_code_smells",
    "warnings_per_kloc": "log_warnings_per_kloc",
    "complexity_per_kloc": "log_complexity_per_kloc",
    "code_smells_per_kloc": "log_code_smells_per_kloc",
}

QC_FLAG_COLS = [
    "sonarqube_any_raw_metric_missing",
    "sonarqube_all_raw_metrics_missing",
    "sonarqube_ncloc_zero",
    "sonarqube_static_warnings_missing",
    "sonarqube_duplicate_density_missing",
    "sonarqube_cognitive_complexity_missing",
    "sonarqube_quality_outcomes_complete",
]

RAW_METRIC_COLS = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

DEFAULT_FILL_FROM_PAPER_COLUMNS = [
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

DEFAULT_METRIC_COMPARE_COLUMNS = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]


TRUE_VALUES = {"TRUE", "T", "1", "YES", "Y"}
FALSE_VALUES = {"FALSE", "F", "0", "NO", "N"}


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def parse_bool(value: str) -> bool:
    """Parse a case-insensitive CLI boolean value."""
    normalized = str(value).strip().upper()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise argparse.ArgumentTypeError(
        f"Expected TRUE or FALSE for a boolean argument, got: {value}"
    )


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    """Parse a comma-separated CLI list."""
    if value is None or str(value).strip() == "":
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prepare quality DiD input from a merged Python SonarQube panel."
    )
    parser.add_argument("--input", required=True, help="Merged SonarQube panel CSV.")
    parser.add_argument("--output", required=True, help="Output full quality DiD panel CSV.")
    parser.add_argument("--qc-output", required=True, help="Output QC summary CSV.")
    parser.add_argument(
        "--missing-output",
        required=True,
        help="Output rows with missing core quality outcomes.",
    )
    parser.add_argument(
        "--complete-output",
        required=False,
        default=None,
        help="Optional output CSV containing only analysis-ready quality DiD rows.",
    )
    parser.add_argument(
        "--panel-label",
        required=False,
        default="panel",
        help="Human-readable panel label for QC output.",
    )
    parser.add_argument(
        "--convert-paper-same-column",
        type=parse_bool,
        default=False,
        metavar="TRUE|FALSE",
        help=(
            "Create an additional output with the same column order as the paper "
            "data/panel_event_monthly.csv."
        ),
    )
    parser.add_argument(
        "--keep-overlap-paper-same-column",
        type=parse_bool,
        default=False,
        metavar="TRUE|FALSE",
        help=(
            "When paper-schema conversion is enabled, keep only source repo-month "
            "rows that have an exact match in the frozen paper panel."
        ),
    )
    parser.add_argument(
        "--paper-panel-file",
        default="data/panel_event_monthly.csv",
        help="Frozen paper panel used as the schema and paper-data source.",
    )
    parser.add_argument(
        "--paper-audit-dir",
        default="repo_python/tmp",
        help=(
            "Directory for paper-schema audit outputs such as key summaries, "
            "metric comparisons, unmatched rows, and notes."
        ),
    )
    parser.add_argument(
        "--paper-same-column-output",
        default=None,
        help=(
            "Optional paper-schema output path. If omitted, derive it from "
            "--complete-output or --output."
        ),
    )
    parser.add_argument(
        "--fill-from-paper-columns",
        default=",".join(DEFAULT_FILL_FROM_PAPER_COLUMNS),
        help="Comma-separated columns to fill from the paper panel on exact repo-month matches.",
    )
    parser.add_argument(
        "--metric-compare-columns",
        default=",".join(DEFAULT_METRIC_COMPARE_COLUMNS),
        help="Comma-separated regenerated-versus-paper metric comparison columns.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=20,
        help="Number of largest regenerated-versus-paper metric differences to print.",
    )
    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    """Require essential columns."""
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def to_numeric_if_present(df: pd.DataFrame, col: str) -> None:
    """Convert a column to numeric if it exists."""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def copy_first_available(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    """Create a target column from the first available candidate column."""
    if target in df.columns:
        return

    for candidate in candidates:
        if candidate in df.columns:
            df[target] = df[candidate]
            return


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


def add_paper_join_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized exact repo-month keys for paper-panel joins."""
    require_columns(df, PAPER_JOIN_COLS, "paper join input")
    out = df.copy()
    out["repo_name"] = out["repo_name"].astype(str)
    out["time"] = out["time"].map(normalize_month_value)
    out["__join_repo_name"] = out["repo_name"]
    out["__join_time"] = out["time"]
    return out


def safe_read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV and fail clearly if it does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return pd.read_csv(path, low_memory=False)


def add_alias_and_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add run9-compatible analysis columns and aliases."""
    df = df.copy()

    copy_first_available(df, "ncloc", ["ncloc_raw"])
    copy_first_available(df, "technical_debt", ["technical_debt_raw"])
    copy_first_available(df, "bugs", ["bugs_raw"])
    copy_first_available(df, "vulnerabilities", ["vulnerabilities_raw"])
    copy_first_available(df, "code_smells", ["code_smells_raw"])
    copy_first_available(df, "duplicated_lines_density", ["duplicated_lines_density_raw"])
    copy_first_available(df, "comment_lines_density", ["comment_lines_density_raw"])
    copy_first_available(df, "cognitive_complexity", ["cognitive_complexity_raw"])

    copy_first_available(
        df,
        "duplicate_line_density",
        ["duplicated_lines_density", "duplicated_lines_density_raw"],
    )
    copy_first_available(
        df,
        "code_complexity",
        ["cognitive_complexity", "cognitive_complexity_raw"],
    )

    for col in (
        CORE_QUALITY_OUTCOMES
        + RATE_OUTCOMES
        + OPTIONAL_QUALITY_OUTCOMES
        + RAW_METRIC_COLS
    ):
        to_numeric_if_present(df, col)

    if "static_analysis_warnings" not in df.columns:
        if {"bugs", "vulnerabilities", "code_smells"}.issubset(df.columns):
            df["static_analysis_warnings"] = df[
                ["bugs", "vulnerabilities", "code_smells"]
            ].sum(axis=1, min_count=3)

    valid_ncloc = df.get("ncloc", pd.Series(index=df.index, dtype=float)).notna()
    if "ncloc" in df.columns:
        valid_ncloc = df["ncloc"].notna() & (df["ncloc"] > 0)

    if "warnings_per_kloc" not in df.columns and {
        "static_analysis_warnings",
        "ncloc",
    }.issubset(df.columns):
        df["warnings_per_kloc"] = np.nan
        df.loc[valid_ncloc, "warnings_per_kloc"] = (
            df.loc[valid_ncloc, "static_analysis_warnings"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "complexity_per_kloc" not in df.columns and {
        "code_complexity",
        "ncloc",
    }.issubset(df.columns):
        df["complexity_per_kloc"] = np.nan
        df.loc[valid_ncloc, "complexity_per_kloc"] = (
            df.loc[valid_ncloc, "code_complexity"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    if "code_smells_per_kloc" not in df.columns and {
        "code_smells",
        "ncloc",
    }.issubset(df.columns):
        df["code_smells_per_kloc"] = np.nan
        df.loc[valid_ncloc, "code_smells_per_kloc"] = (
            df.loc[valid_ncloc, "code_smells"]
            / df.loc[valid_ncloc, "ncloc"]
            * 1000.0
        )

    for source_col, log_col in LOG_OUTCOME_MAP.items():
        if source_col not in df.columns:
            continue

        x = pd.to_numeric(df[source_col], errors="coerce")
        df[log_col] = np.where(x.notna() & (x >= 0), np.log1p(x), np.nan)

    return df


def add_readiness_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add DiD readiness flags."""
    df = df.copy()

    if set(KEY_COLS).issubset(df.columns):
        df["did_duplicate_repo_time_source_key"] = df.duplicated(KEY_COLS).astype(int)
    else:
        df["did_duplicate_repo_time_source_key"] = 1

    df["analysis_ready_core_quality"] = (
        df[CORE_QUALITY_OUTCOMES].notna().all(axis=1)
        if set(CORE_QUALITY_OUTCOMES).issubset(df.columns)
        else False
    )

    existing_rate_cols = [c for c in RATE_OUTCOMES if c in df.columns]
    if existing_rate_cols:
        df["analysis_ready_quality_rates"] = df[existing_rate_cols].notna().all(axis=1)
    else:
        df["analysis_ready_quality_rates"] = False

    df["analysis_ready_did_base"] = (
        df[BASE_DID_COLS].notna().all(axis=1)
        & (df["did_duplicate_repo_time_source_key"] == 0)
        & df["dataset_source"].isin(["treatment", "control"])
    )

    df["analysis_ready_quality_did"] = (
        df["analysis_ready_did_base"] & df["analysis_ready_core_quality"]
    )

    for col in [
        "analysis_ready_core_quality",
        "analysis_ready_quality_rates",
        "analysis_ready_did_base",
        "analysis_ready_quality_did",
    ]:
        df[col] = df[col].astype(int)

    return df


def assert_no_invalid_values(df: pd.DataFrame) -> None:
    """Fail on structural problems, not on expected SonarQube missingness."""
    if set(KEY_COLS).issubset(df.columns):
        duplicate_count = int(df.duplicated(KEY_COLS).sum())
        if duplicate_count:
            raise ValueError(f"Duplicated repo-time-source keys: {duplicate_count}")

    for col in CORE_QUALITY_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES + RATE_OUTCOMES:
        if col not in df.columns:
            continue

        x = pd.to_numeric(df[col], errors="coerce")
        negative_count = int((x < 0).sum())
        if negative_count:
            raise ValueError(f"Negative values found in {col}: {negative_count}")


def build_qc(df: pd.DataFrame, input_rows: int, output_rows: int, panel_label: str) -> pd.DataFrame:
    """Build the existing quality DiD QC summary."""
    rows: list[dict[str, object]] = []

    def add(check: str, value: object) -> None:
        rows.append({"check": check, "value": value})

    add("panel_label", panel_label)
    add("input_rows", input_rows)
    add("output_rows", output_rows)
    add("row_count_preserved_in_full_output", int(input_rows == output_rows))
    add("repos", df["repo_name"].nunique() if "repo_name" in df.columns else None)
    add("min_time", df["time"].min() if "time" in df.columns else None)
    add("max_time", df["time"].max() if "time" in df.columns else None)

    add("treatment_rows", int((df["dataset_source"] == "treatment").sum()))
    add("control_rows", int((df["dataset_source"] == "control").sum()))
    add(
        "treatment_repos",
        df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique(),
    )
    add(
        "control_repos",
        df.loc[df["dataset_source"] == "control", "repo_name"].nunique(),
    )

    add("duplicate_repo_time_source_rows", int(df["did_duplicate_repo_time_source_key"].sum()))
    add("analysis_ready_did_base_rows", int(df["analysis_ready_did_base"].sum()))
    add("analysis_ready_core_quality_rows", int(df["analysis_ready_core_quality"].sum()))
    add("analysis_ready_quality_did_rows", int(df["analysis_ready_quality_did"].sum()))
    add("missing_core_quality_rows", int((df["analysis_ready_core_quality"] == 0).sum()))

    if "time_to_event" in df.columns:
        add(
            "treatment_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "treatment", "time_to_event"].notna().sum()),
        )
        add(
            "control_time_to_event_nonmissing",
            int(df.loc[df["dataset_source"] == "control", "time_to_event"].notna().sum()),
        )

    if "post_event" in df.columns:
        add("post_event_sum", int(pd.to_numeric(df["post_event"], errors="coerce").fillna(0).sum()))
        add(
            "control_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "control", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )
        add(
            "treatment_post_event_sum",
            int(
                pd.to_numeric(
                    df.loc[df["dataset_source"] == "treatment", "post_event"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            ),
        )

    if "sonarqube_latest_commit" in df.columns:
        add("sonarqube_latest_commit_missing", int(df["sonarqube_latest_commit"].isna().sum()))

    for col in QC_FLAG_COLS:
        if col in df.columns:
            add(f"{col}_sum", int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum()))
        else:
            add(f"{col}_sum", None)

    for col in CORE_QUALITY_OUTCOMES + RATE_OUTCOMES + OPTIONAL_QUALITY_OUTCOMES:
        if col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce")
            add(f"{col}_nonmissing", int(x.notna().sum()))
            add(f"{col}_missing", int(x.isna().sum()))
            add(f"{col}_zero_count", int((x == 0).sum()))
            add(f"{col}_mean", float(x.mean()) if x.notna().any() else None)
            add(f"{col}_median", float(x.median()) if x.notna().any() else None)
        else:
            add(f"{col}_nonmissing", None)
            add(f"{col}_missing", None)

    for _, log_col in LOG_OUTCOME_MAP.items():
        if log_col in df.columns:
            x = pd.to_numeric(df[log_col], errors="coerce")
            add(f"{log_col}_nonmissing", int(x.notna().sum()))
            add(f"{log_col}_finite", int(np.isfinite(x).sum()))

    return pd.DataFrame(rows)


def derive_paper_same_column_output(args: argparse.Namespace) -> Path:
    """Derive a stable paper-schema output name when none is supplied."""
    if args.paper_same_column_output:
        return Path(args.paper_same_column_output)

    source = Path(args.complete_output) if args.complete_output else Path(args.output)
    suffix = (
        "_paper_same_column_overlap.csv"
        if args.keep_overlap_paper_same_column
        else "_paper_same_column.csv"
    )
    return source.with_name(f"{source.stem}{suffix}")


def create_metric_comparison(
    source_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    metrics: Iterable[str],
) -> pd.DataFrame:
    """Compare regenerated and frozen-paper metrics on exact repo-month matches."""
    source_keyed = add_paper_join_keys(source_df)
    paper_keyed = add_paper_join_keys(paper_df).drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )

    available_metrics = [
        metric
        for metric in metrics
        if metric in source_keyed.columns and metric in paper_keyed.columns
    ]
    if not available_metrics:
        return pd.DataFrame()

    merged = source_keyed[
        ["repo_name", "time", "__join_repo_name", "__join_time"]
        + available_metrics
    ].merge(
        paper_keyed[["__join_repo_name", "__join_time"] + available_metrics],
        on=["__join_repo_name", "__join_time"],
        how="inner",
        suffixes=("_our", "_paper"),
        sort=False,
    )

    rows: list[dict[str, object]] = []
    for metric in available_metrics:
        our_values = pd.to_numeric(merged[f"{metric}_our"], errors="coerce")
        paper_values = pd.to_numeric(merged[f"{metric}_paper"], errors="coerce")
        differences = our_values - paper_values

        for idx in merged.index:
            difference = differences.at[idx]
            rows.append(
                {
                    "repo_name": merged.at[idx, "repo_name"],
                    "time": merged.at[idx, "time"],
                    "metric": metric,
                    "our_value": our_values.at[idx],
                    "paper_value": paper_values.at[idx],
                    "diff_our_minus_paper": difference,
                    "abs_diff": abs(difference) if pd.notna(difference) else pd.NA,
                }
            )

    comparison = pd.DataFrame(rows)
    if not comparison.empty:
        comparison = comparison.sort_values(
            ["abs_diff", "repo_name", "time", "metric"],
            ascending=[False, True, True, True],
        )
    return comparison


def create_paper_same_column_panel(
    source_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    fill_from_paper_columns: Iterable[str],
    keep_overlap_only: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the paper-schema panel and exact-match audit outputs.

    The source_df is expected to be the analysis-ready complete-case quality
    DiD panel. Columns already present in source_df are preserved. Only paper
    schema columns missing from source_df are eligible for paper-panel filling.
    """
    source_keyed = add_paper_join_keys(source_df)
    paper_keyed = add_paper_join_keys(paper_df)

    source_keyed["__source_row_order"] = np.arange(len(source_keyed))
    paper_schema = [col for col in paper_keyed.columns if not col.startswith("__join_")]
    fill_set = set(fill_from_paper_columns)

    source_duplicate_count = int(
        source_keyed.duplicated(["__join_repo_name", "__join_time"]).sum()
    )
    paper_duplicate_count = int(
        paper_keyed.duplicated(["__join_repo_name", "__join_time"]).sum()
    )

    paper_unique = paper_keyed.drop_duplicates(
        ["__join_repo_name", "__join_time"], keep="last"
    )
    fill_available = [col for col in fill_set if col in paper_unique.columns]

    paper_fill = paper_unique[
        ["__join_repo_name", "__join_time"] + fill_available
    ].copy()
    paper_fill["__paper_same_column_match"] = 1

    merged = source_keyed.merge(
        paper_fill,
        on=["__join_repo_name", "__join_time"],
        how="left",
        suffixes=("", "__paper_fill"),
        sort=False,
    ).sort_values("__source_row_order")

    matched_mask = merged["__paper_same_column_match"].eq(1)
    unmatched = merged.loc[~matched_mask, source_df.columns].copy()
    unmatched.insert(2, "paper_same_column_match", 0)

    selected = merged.loc[matched_mask].copy() if keep_overlap_only else merged.copy()

    output = pd.DataFrame(index=selected.index)
    column_source_rows: list[dict[str, object]] = []

    for col in paper_schema:
        if col in source_df.columns:
            output[col] = selected[col]
            source_label = "python_quality_input"
        elif col in fill_available:
            output[col] = selected[col]
            source_label = "paper_panel_exact_repo_month_fill"
        else:
            output[col] = pd.NA
            source_label = "missing_set_na"

        column_source_rows.append(
            {
                "column": col,
                "source": source_label,
                "non_missing_count": int(output[col].notna().sum()),
                "missing_count": int(output[col].isna().sum()),
            }
        )

    if "time" in output.columns:
        output["time"] = output["time"].map(normalize_month_value)

    key_summary = pd.DataFrame(
        [
            {
                "source_complete_rows": len(source_df),
                "paper_rows": len(paper_df),
                "paper_same_column_output_rows": len(output),
                "paper_same_column_output_columns": len(output.columns),
                "paper_schema_columns": len(paper_schema),
                "source_duplicate_repo_month_rows": source_duplicate_count,
                "paper_duplicate_repo_month_rows": paper_duplicate_count,
                "repo_month_rows_matched_to_paper": int(matched_mask.sum()),
                "repo_month_rows_not_matched_to_paper": int((~matched_mask).sum()),
                "keep_overlap_paper_same_column": int(keep_overlap_only),
            }
        ]
    )

    column_sources = pd.DataFrame(column_source_rows)
    return output, column_sources, key_summary, unmatched


def write_paper_same_column_notes(
    notes_path: Path,
    source_path: str,
    paper_path: str,
    output_path: Path,
    key_summary: pd.DataFrame,
    column_sources: pd.DataFrame,
    keep_overlap_only: bool,
) -> None:
    """Write a compact human-readable paper-schema diagnostic note."""
    summary = key_summary.iloc[0].to_dict()
    filled_columns = column_sources.loc[
        column_sources["source"] == "paper_panel_exact_repo_month_fill", "column"
    ].tolist()

    lines = [
        "# run-py-2e paper-same-column diagnostic notes",
        "",
        "## Purpose",
        "",
        "Create a paper-schema diagnostic output from the analysis-ready Python quality DiD input.",
        "Regenerated SonarQube metrics are preserved, while selected unavailable columns are filled from the frozen paper panel on exact repo-month matches.",
        "",
        "## Inputs",
        "",
        f"- Analysis-ready source: `{source_path}`",
        f"- Frozen paper panel: `{paper_path}`",
        "",
        "## Output",
        "",
        f"- Paper-schema output: `{output_path}`",
        f"- Keep exact overlap only: `{str(keep_overlap_only).upper()}`",
        "",
        "## Key summary",
        "",
        f"- Source complete rows: {summary.get('source_complete_rows')}",
        f"- Exact repo-month matches: {summary.get('repo_month_rows_matched_to_paper')}",
        f"- Unmatched repo-month rows: {summary.get('repo_month_rows_not_matched_to_paper')}",
        f"- Output rows: {summary.get('paper_same_column_output_rows')}",
        f"- Output columns: {summary.get('paper_same_column_output_columns')}",
        f"- Paper duplicate repo-month rows before deduplication: {summary.get('paper_duplicate_repo_month_rows')}",
        "",
        "## Columns filled from the paper panel",
        "",
    ]

    if filled_columns:
        lines.extend([f"- `{column}`" for column in filled_columns])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Interpretation caution",
            "",
            "This output is an overlap-restricted diagnostic dataset, not a full independent reproduction dataset.",
            "Dropping unmatched repo-month rows changes the analysis sample and should be reported explicitly.",
        ]
    )

    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_paper_same_column_conversion(
    args: argparse.Namespace,
    complete_df: pd.DataFrame,
    complete_source_label: str,
) -> dict[str, object]:
    """Run optional paper-schema conversion and write all audit outputs."""
    if args.keep_overlap_paper_same_column and not args.convert_paper_same_column:
        raise ValueError(
            "--keep-overlap-paper-same-column TRUE requires "
            "--convert-paper-same-column TRUE"
        )

    if not args.convert_paper_same_column:
        return {
            "enabled": 0,
            "output_path": "",
            "key_summary_path": "",
            "unmatched_path": "",
            "output_rows": None,
            "matched_rows": None,
            "unmatched_rows": None,
            "keep_overlap": int(args.keep_overlap_paper_same_column),
        }

    paper_path = Path(args.paper_panel_file)
    paper_df = safe_read_csv(paper_path)
    output_path = derive_paper_same_column_output(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fill_columns = parse_csv_list(
        args.fill_from_paper_columns,
        DEFAULT_FILL_FROM_PAPER_COLUMNS,
    )
    metric_columns = parse_csv_list(
        args.metric_compare_columns,
        DEFAULT_METRIC_COMPARE_COLUMNS,
    )

    paper_output, column_sources, key_summary, unmatched = create_paper_same_column_panel(
        source_df=complete_df,
        paper_df=paper_df,
        fill_from_paper_columns=fill_columns,
        keep_overlap_only=args.keep_overlap_paper_same_column,
    )
    metric_comparison = create_metric_comparison(
        source_df=complete_df,
        paper_df=paper_df,
        metrics=metric_columns,
    )

    audit_dir = Path(args.paper_audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_base = audit_dir / output_path.stem
    column_sources_path = Path(f"{audit_base}_column_sources.csv")
    key_summary_path = Path(f"{audit_base}_key_match_summary.csv")
    metric_comparison_path = Path(f"{audit_base}_metric_comparison.csv")
    unmatched_path = Path(f"{audit_base}_unmatched_repo_months.csv")
    notes_path = Path(f"{audit_base}_notes.md")

    paper_output.to_csv(output_path, index=False)
    column_sources.to_csv(column_sources_path, index=False)
    key_summary.to_csv(key_summary_path, index=False)
    metric_comparison.to_csv(metric_comparison_path, index=False)
    unmatched.to_csv(unmatched_path, index=False)
    write_paper_same_column_notes(
        notes_path=notes_path,
        source_path=complete_source_label,
        paper_path=str(paper_path),
        output_path=output_path,
        key_summary=key_summary,
        column_sources=column_sources,
        keep_overlap_only=args.keep_overlap_paper_same_column,
    )

    summary = key_summary.iloc[0]
    logging.info("Saved paper-schema output: %s", output_path)
    logging.info("Saved paper-schema audit directory: %s", audit_dir)
    logging.info("Saved paper-schema key summary: %s", key_summary_path)
    logging.info("Saved unmatched repo-month rows: %s", unmatched_path)
    logging.info(
        "Paper-schema exact matches: %d; unmatched: %d; output rows: %d",
        int(summary["repo_month_rows_matched_to_paper"]),
        int(summary["repo_month_rows_not_matched_to_paper"]),
        int(summary["paper_same_column_output_rows"]),
    )

    if not metric_comparison.empty and args.top_print > 0:
        print()
        print("Top paper-versus-regenerated metric differences:")
        for _, row in metric_comparison.head(args.top_print).iterrows():
            print(
                f"  {row['repo_name']},{row['time']},{row['metric']},"
                f"our={row['our_value']},paper={row['paper_value']},"
                f"diff={row['diff_our_minus_paper']}"
            )

    return {
        "enabled": 1,
        "output_path": str(output_path),
        "key_summary_path": str(key_summary_path),
        "unmatched_path": str(unmatched_path),
        "output_rows": int(summary["paper_same_column_output_rows"]),
        "matched_rows": int(summary["repo_month_rows_matched_to_paper"]),
        "unmatched_rows": int(summary["repo_month_rows_not_matched_to_paper"]),
        "keep_overlap": int(args.keep_overlap_paper_same_column),
    }


def main() -> int:
    """Run quality DiD preparation and optional paper-schema conversion."""
    setup_logging()
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    qc_path = Path(args.qc_output)
    missing_path = Path(args.missing_output)
    complete_path = Path(args.complete_output) if args.complete_output else None

    logging.info("Loading merged panel: %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    input_rows = len(df)

    require_columns(df, BASE_DID_COLS, "input panel")

    logging.info("Input rows: %d", input_rows)
    logging.info("Input repos: %d", df["repo_name"].nunique())
    logging.info("Input months: %s to %s", df["time"].min(), df["time"].max())

    df = add_alias_and_analysis_columns(df)
    require_columns(df, CORE_QUALITY_OUTCOMES, "prepared panel")

    df = add_readiness_flags(df)
    assert_no_invalid_values(df)

    missing_core = df[df["analysis_ready_core_quality"] == 0].copy()
    complete_df = df[df["analysis_ready_quality_did"] == 1].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    if complete_path:
        complete_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)
    missing_core.to_csv(missing_path, index=False)

    if complete_path:
        complete_df.to_csv(complete_path, index=False)

    complete_source_label = str(complete_path) if complete_path else f"{output_path} [analysis_ready_quality_did == 1]"
    paper_conversion = run_paper_same_column_conversion(
        args=args,
        complete_df=complete_df,
        complete_source_label=complete_source_label,
    )

    qc = build_qc(df, input_rows=input_rows, output_rows=len(df), panel_label=args.panel_label)

    additional_qc_rows: list[dict[str, object]] = []
    if complete_path:
        additional_qc_rows.extend(
            [
                {"check": "complete_output_path", "value": str(complete_path)},
                {"check": "complete_output_rows", "value": len(complete_df)},
                {"check": "complete_output_repos", "value": complete_df["repo_name"].nunique()},
            ]
        )

    additional_qc_rows.extend(
        [
            {"check": "convert_paper_same_column", "value": paper_conversion["enabled"]},
            {
                "check": "keep_overlap_paper_same_column",
                "value": paper_conversion["keep_overlap"],
            },
            {
                "check": "paper_same_column_output_path",
                "value": paper_conversion["output_path"],
            },
            {
                "check": "paper_same_column_output_rows",
                "value": paper_conversion["output_rows"],
            },
            {
                "check": "paper_same_column_matched_rows",
                "value": paper_conversion["matched_rows"],
            },
            {
                "check": "paper_same_column_unmatched_rows",
                "value": paper_conversion["unmatched_rows"],
            },
            {
                "check": "paper_same_column_unmatched_output_path",
                "value": paper_conversion["unmatched_path"],
            },
        ]
    )

    qc = pd.concat([qc, pd.DataFrame(additional_qc_rows)], ignore_index=True)
    qc.to_csv(qc_path, index=False)

    logging.info("Saved full quality DiD input: %s", output_path)
    logging.info("Saved missing core quality rows: %s", missing_path)
    if complete_path:
        logging.info("Saved complete-case quality DiD input: %s", complete_path)
    logging.info("Saved QC: %s", qc_path)

    print()
    print("QC summary:")
    print(qc.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
