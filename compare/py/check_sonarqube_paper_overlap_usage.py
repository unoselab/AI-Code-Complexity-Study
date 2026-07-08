#!/usr/bin/env python3
"""
Check whether paper-missing SonarQube scan rows are used in the final DiD input.

This diagnostic script is for the Python Cursor replication experiment. It compares
our pyv2 SonarQube scan outputs with the frozen paper panel and checks whether
extra scan rows that are not present in the paper panel enter the final quality
DiD input.

Main outputs:
  1. Summary CSV with key counts.
  2. Final DiD rows missing from the paper panel.
  3. Final DiD rows overlapping with the paper panel.
  4. Final DiD rows missing from our scan outputs.
  5. Final DiD rows overlapping with our scan outputs.
  6. Paper-overlap-only treatment and control SonarQube scan CSVs.

The filtered scan CSVs preserve the original scan columns so that downstream
merge scripts can reuse them as drop-in inputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


KEY_COLUMNS = ["repo_name", "time"]
SCAN_TIME_CANDIDATES = ["month", "time"]
PAPER_TIME_CANDIDATES = ["time", "month"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check paper-overlap usage for Python pyv2 SonarQube scans and "
            "the final complete-case quality DiD input."
        )
    )

    parser.add_argument(
        "--paper-panel",
        required=True,
        type=Path,
        help="Paper monthly panel CSV, typically data/panel_event_monthly.csv.",
    )
    parser.add_argument(
        "--treatment-scan",
        required=True,
        type=Path,
        help="Treatment SonarQube scan CSV.",
    )
    parser.add_argument(
        "--control-scan",
        required=True,
        type=Path,
        help="Control SonarQube scan CSV.",
    )
    parser.add_argument(
        "--final-did-input",
        required=True,
        type=Path,
        help="Final complete-case quality DiD input CSV.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where diagnostic CSV outputs will be written.",
    )
    parser.add_argument(
        "--treatment-overlap-output",
        required=True,
        type=Path,
        help="Output CSV for treatment scan rows present in the paper panel.",
    )
    parser.add_argument(
        "--control-overlap-output",
        required=True,
        type=Path,
        help="Output CSV for control scan rows present in the paper panel.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=30,
        help="Number of diagnostic rows to print to stdout.",
    )

    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise SystemExit(
            f"ERROR: {label} missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def read_csv(path: Path, label: str) -> pd.DataFrame:
    require_file(path, label)
    try:
        return pd.read_csv(path, low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")


def find_first_existing_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise SystemExit(
        f"ERROR: cannot find a time column for {label}. "
        f"Tried: {candidates}. Available columns: {list(df.columns)}"
    )


def clean_repo(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    out = out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))
    return out


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str[:7]
    out = out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))
    return out


def add_normalized_key(
    df: pd.DataFrame,
    label: str,
    time_candidates: list[str],
) -> pd.DataFrame:
    require_columns(df, ["repo_name"], label)
    time_col = find_first_existing_column(df, time_candidates, label)

    out = df.copy()
    out["repo_name_norm"] = clean_repo(out["repo_name"])
    out["time_norm"] = clean_month(out[time_col])
    out = out[out["repo_name_norm"].notna() & out["time_norm"].notna()].copy()
    out["repo_month_key"] = out["repo_name_norm"] + "@@" + out["time_norm"]
    return out


def key_frame(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["repo_name_norm", "time_norm", "repo_month_key"]]
        .drop_duplicates("repo_month_key")
        .rename(columns={"repo_name_norm": "repo_name", "time_norm": "time"})
        .reset_index(drop=True)
    )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def original_columns_without_helpers(df: pd.DataFrame) -> list[str]:
    helper_cols = {
        "repo_name_norm",
        "time_norm",
        "repo_month_key",
        "paper_overlap",
        "scan_overlap",
        "scan_group",
    }
    return [col for col in df.columns if col not in helper_cols]


def build_summary_row(metric: str, value) -> dict[str, object]:
    return {"metric": metric, "value": value}


def write_notes(path: Path, summary_rows: list[dict[str, object]]) -> None:
    value_map = {row["metric"]: row["value"] for row in summary_rows}
    notes = [
        "# SonarQube paper-overlap usage check",
        "",
        "This diagnostic checks whether Python pyv2 SonarQube scan rows that are not present in the frozen paper panel enter the final complete-case quality DiD input.",
        "",
        "## Key counts",
        "",
        f"- Combined scan rows: {value_map.get('combined_scan_rows')}",
        f"- Combined scan rows overlapping with paper: {value_map.get('combined_scan_rows_overlap_with_paper')}",
        f"- Combined scan rows missing in paper: {value_map.get('combined_scan_rows_missing_in_paper')}",
        f"- Final DiD rows: {value_map.get('final_did_input_rows')}",
        f"- Final DiD rows overlapping with paper: {value_map.get('final_rows_overlap_with_paper')}",
        f"- Final DiD rows missing in paper: {value_map.get('final_rows_missing_in_paper')}",
        f"- Final DiD rows missing in scan: {value_map.get('final_rows_missing_in_scan')}",
        "",
        "Interpretation: final_rows_missing_in_paper should be zero for a paper-overlap replication branch.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(notes), encoding="utf-8")


def main() -> int:
    args = parse_args()

    paper = add_normalized_key(
        read_csv(args.paper_panel, "paper panel"),
        label="paper panel",
        time_candidates=PAPER_TIME_CANDIDATES,
    )
    treatment_scan = add_normalized_key(
        read_csv(args.treatment_scan, "treatment scan"),
        label="treatment scan",
        time_candidates=SCAN_TIME_CANDIDATES,
    )
    control_scan = add_normalized_key(
        read_csv(args.control_scan, "control scan"),
        label="control scan",
        time_candidates=SCAN_TIME_CANDIDATES,
    )
    final_did = add_normalized_key(
        read_csv(args.final_did_input, "final DiD input"),
        label="final DiD input",
        time_candidates=PAPER_TIME_CANDIDATES,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    treatment_scan["scan_group"] = "treatment"
    control_scan["scan_group"] = "control"
    combined_scan = pd.concat([treatment_scan, control_scan], ignore_index=True)

    paper_keys = set(paper["repo_month_key"])
    scan_keys = set(combined_scan["repo_month_key"])
    final_keys = set(final_did["repo_month_key"])

    paper_duplicate_rows = int(paper.duplicated("repo_month_key", keep=False).sum())
    scan_duplicate_rows = int(combined_scan.duplicated("repo_month_key", keep=False).sum())
    final_duplicate_rows = int(final_did.duplicated("repo_month_key", keep=False).sum())

    treatment_overlap = treatment_scan[treatment_scan["repo_month_key"].isin(paper_keys)].copy()
    control_overlap = control_scan[control_scan["repo_month_key"].isin(paper_keys)].copy()
    combined_overlap = combined_scan[combined_scan["repo_month_key"].isin(paper_keys)].copy()
    combined_missing_paper = combined_scan[~combined_scan["repo_month_key"].isin(paper_keys)].copy()

    final_overlap_paper = final_did[final_did["repo_month_key"].isin(paper_keys)].copy()
    final_missing_paper = final_did[~final_did["repo_month_key"].isin(paper_keys)].copy()
    final_overlap_scan = final_did[final_did["repo_month_key"].isin(scan_keys)].copy()
    final_missing_scan = final_did[~final_did["repo_month_key"].isin(scan_keys)].copy()

    extra_scan_keys = scan_keys - paper_keys
    final_extra_scan_rows_used = final_did[final_did["repo_month_key"].isin(extra_scan_keys)].copy()

    # Save overlap-only scan files using original scan columns so they can be
    # used as drop-in downstream inputs.
    save_csv(
        treatment_overlap[original_columns_without_helpers(treatment_overlap)],
        args.treatment_overlap_output,
    )
    save_csv(
        control_overlap[original_columns_without_helpers(control_overlap)],
        args.control_overlap_output,
    )

    # Save final DiD usage diagnostics. Keep helper columns here because they
    # make inspection easier.
    save_csv(final_missing_paper, args.output_dir / "final_did_rows_missing_in_paper.csv")
    save_csv(final_overlap_paper, args.output_dir / "final_did_rows_overlap_with_paper.csv")
    save_csv(final_missing_scan, args.output_dir / "final_did_rows_missing_in_scan.csv")
    save_csv(final_overlap_scan, args.output_dir / "final_did_rows_overlap_with_scan.csv")
    save_csv(final_extra_scan_rows_used, args.output_dir / "final_extra_scan_rows_used.csv")

    save_csv(
        key_frame(combined_missing_paper),
        args.output_dir / "scan_rows_missing_in_paper_keys.csv",
    )
    save_csv(
        key_frame(combined_overlap),
        args.output_dir / "scan_rows_overlap_with_paper_keys.csv",
    )

    summary_rows = [
        build_summary_row("paper_panel_rows", len(paper)),
        build_summary_row("paper_panel_unique_repo_months", paper["repo_month_key"].nunique()),
        build_summary_row("paper_panel_unique_repos", paper["repo_name_norm"].nunique()),
        build_summary_row("paper_duplicate_repo_month_rows", paper_duplicate_rows),
        build_summary_row("treatment_scan_rows", len(treatment_scan)),
        build_summary_row("control_scan_rows", len(control_scan)),
        build_summary_row("combined_scan_rows", len(combined_scan)),
        build_summary_row("combined_scan_unique_repo_months", combined_scan["repo_month_key"].nunique()),
        build_summary_row("combined_scan_unique_repos", combined_scan["repo_name_norm"].nunique()),
        build_summary_row("combined_scan_duplicate_repo_month_rows", scan_duplicate_rows),
        build_summary_row("combined_scan_rows_overlap_with_paper", len(combined_overlap)),
        build_summary_row("combined_scan_unique_repo_months_overlap_with_paper", combined_overlap["repo_month_key"].nunique()),
        build_summary_row("combined_scan_rows_missing_in_paper", len(combined_missing_paper)),
        build_summary_row("combined_scan_unique_repo_months_missing_in_paper", combined_missing_paper["repo_month_key"].nunique()),
        build_summary_row("treatment_scan_rows_overlap_with_paper", len(treatment_overlap)),
        build_summary_row("treatment_scan_rows_missing_in_paper", len(treatment_scan) - len(treatment_overlap)),
        build_summary_row("control_scan_rows_overlap_with_paper", len(control_overlap)),
        build_summary_row("control_scan_rows_missing_in_paper", len(control_scan) - len(control_overlap)),
        build_summary_row("treatment_overlap_output_rows", len(treatment_overlap)),
        build_summary_row("control_overlap_output_rows", len(control_overlap)),
        build_summary_row("final_did_input_rows", len(final_did)),
        build_summary_row("final_did_unique_repo_months", final_did["repo_month_key"].nunique()),
        build_summary_row("final_did_unique_repos", final_did["repo_name_norm"].nunique()),
        build_summary_row("final_did_duplicate_repo_month_rows", final_duplicate_rows),
        build_summary_row("final_rows_overlap_with_paper", len(final_overlap_paper)),
        build_summary_row("final_rows_missing_in_paper", len(final_missing_paper)),
        build_summary_row("final_rows_overlap_with_scan", len(final_overlap_scan)),
        build_summary_row("final_rows_missing_in_scan", len(final_missing_scan)),
        build_summary_row("final_extra_scan_rows_used", len(final_extra_scan_rows_used)),
        build_summary_row("paper_repo_months_for_final_repos", len(paper[paper["repo_name_norm"].isin(set(final_did["repo_name_norm"]))])),
        build_summary_row("paper_repo_months_for_final_repos_missing_in_final", len(set(paper.loc[paper["repo_name_norm"].isin(set(final_did["repo_name_norm"])), "repo_month_key"]) - final_keys)),
    ]

    summary = pd.DataFrame(summary_rows)
    save_csv(summary, args.output_dir / "sonarqube_paper_overlap_usage_summary.csv")
    write_notes(args.output_dir / "sonarqube_paper_overlap_usage_notes.md", summary_rows)

    print("Saved output directory:", args.output_dir)
    print("Treatment overlap output:", args.treatment_overlap_output)
    print("Control overlap output:", args.control_overlap_output)
    print()
    print("Paper-overlap usage summary:")
    print(summary.to_string(index=False))

    if len(final_missing_paper) > 0:
        print()
        print(f"Top {args.top_print} final DiD rows missing in paper:")
        cols = [c for c in ["repo_name", "time", "month", "is_treatment", "dataset_source", "event"] if c in final_missing_paper.columns]
        if not cols:
            cols = ["repo_name_norm", "time_norm"]
        print(final_missing_paper[cols].head(args.top_print).to_string(index=False))

    if len(final_missing_scan) > 0:
        print()
        print(f"Top {args.top_print} final DiD rows missing in scan:")
        cols = [c for c in ["repo_name", "time", "month", "is_treatment", "dataset_source", "event"] if c in final_missing_scan.columns]
        if not cols:
            cols = ["repo_name_norm", "time_norm"]
        print(final_missing_scan[cols].head(args.top_print).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
