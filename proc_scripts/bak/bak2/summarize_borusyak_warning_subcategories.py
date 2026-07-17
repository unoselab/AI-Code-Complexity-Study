#!/usr/bin/env python3
"""
Build combined summary outputs for warning-subcategory Borusyak DiD runs.

This script is called by run10a-did-warning-subcategories-borusyak.sh after
per-panel R Markdown rendering is complete.
"""

import argparse
import math
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


DEFAULT_LABELS = [
    "main_unbalanced",
    "main_balanced",
    "strict_1to3_unbalanced",
    "strict_1to3_balanced",
]

COMBINED_SPECS = [
    (
        "borusyak_warning_subcategories_static_effects.csv",
        "borusyak_warning_subcategories_static_effects_all.csv",
    ),
    (
        "borusyak_warning_subcategories_dynamic_effects.csv",
        "borusyak_warning_subcategories_dynamic_effects_all.csv",
    ),
    (
        "borusyak_warning_subcategories_input_summary.csv",
        "borusyak_warning_subcategories_input_summary_all.csv",
    ),
    (
        "borusyak_warning_subcategories_panel_checks.csv",
        "borusyak_warning_subcategories_panel_checks_all.csv",
    ),
    (
        "borusyak_warning_subcategories_composition.csv",
        "borusyak_warning_subcategories_composition_all.csv",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build combined warning-subcategory Borusyak DiD summaries."
    )
    parser.add_argument(
        "--out-root",
        required=True,
        help="Root output directory containing per-panel Borusyak outputs.",
    )
    parser.add_argument(
        "--summary-dir",
        required=True,
        help="Directory where paper-ready summary files will be written.",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=DEFAULT_LABELS,
        help="Panel labels to combine.",
    )
    return parser.parse_args()


def read_if_exists(out_root: Path, label: str, filename: str) -> Optional[pd.DataFrame]:
    path = out_root / label / filename
    if not path.exists():
        print(f"Missing: {path}")
        return None

    df = pd.read_csv(path)
    if "panel" not in df.columns:
        df["panel"] = label
    return df


def add_percent_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[f"{col}_pct"] = out[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(x) - 1.0) * 100.0
            )
    return out


def combine_panel_outputs(out_root: Path, labels: list[str]) -> None:
    for src_name, out_name in COMBINED_SPECS:
        parts = []
        for label in labels:
            df = read_if_exists(out_root, label, src_name)
            if df is not None:
                parts.append(df)

        if parts:
            combined = pd.concat(parts, ignore_index=True)
            out = out_root / out_name
            combined.to_csv(out, index=False)
            print("Saved:", out)
        else:
            print(f"No panel outputs found for {src_name}")


def build_static_summaries(out_root: Path, summary_dir: Path) -> None:
    static_path = out_root / "borusyak_warning_subcategories_static_effects_all.csv"
    if not static_path.exists():
        print("Static summary input not found:", static_path)
        return

    static = pd.read_csv(static_path)
    static = add_percent_columns(static, ["estimate", "conf_low", "conf_high"])

    paper_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "estimate",
        "estimate_pct",
        "conf_low",
        "conf_low_pct",
        "conf_high",
        "conf_high_pct",
        "std_error",
        "p_value",
        "note",
    ]
    paper_cols = [c for c in paper_cols if c in static.columns]

    paper = static[paper_cols].copy()
    out = summary_dir / "borusyak_warning_subcategories_static_effects_paper_ready.csv"
    paper.to_csv(out, index=False)
    print("Saved:", out)

    try:
        wide = paper.pivot_table(
            index=["panel"],
            columns=["outcome"],
            values=["estimate_pct", "conf_low_pct", "conf_high_pct"],
            aggfunc="first",
        )
        wide.columns = [
            "_".join([str(x) for x in col if str(x) != ""]) for col in wide.columns
        ]
        wide = wide.reset_index()
        out = summary_dir / "borusyak_warning_subcategories_static_effects_wide.csv"
        wide.to_csv(out, index=False)
        print("Saved:", out)
    except Exception as exc:
        print("Could not create static wide summary:", exc)


def build_dynamic_summaries(out_root: Path, summary_dir: Path) -> None:
    dynamic_path = out_root / "borusyak_warning_subcategories_dynamic_effects_all.csv"
    if not dynamic_path.exists():
        print("Dynamic summary input not found:", dynamic_path)
        return

    dynamic = pd.read_csv(dynamic_path)
    dynamic = add_percent_columns(dynamic, ["estimate", "conf_low", "conf_high"])

    out = summary_dir / "borusyak_warning_subcategories_dynamic_effects_percent.csv"
    dynamic.to_csv(out, index=False)
    print("Saved:", out)

    plot_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "time",
        "estimate",
        "conf_low",
        "conf_high",
        "estimate_pct",
        "conf_low_pct",
        "conf_high_pct",
        "significant",
    ]
    plot_cols = [c for c in plot_cols if c in dynamic.columns]
    out = summary_dir / "borusyak_warning_subcategories_dynamic_effects_plot_ready.csv"
    dynamic[plot_cols].to_csv(out, index=False)
    print("Saved:", out)


def write_notes(summary_dir: Path) -> None:
    notes = summary_dir / "borusyak_warning_subcategories_summary_notes.txt"
    notes.write_text(
        "Warning-subcategory Borusyak DiD completed. "
        "Outcomes are log_bugs, log_vulnerabilities, and log_code_smells. "
        "The model uses repository and month fixed effects with contributors_log and log_ncloc as covariates. "
        "Default run analyzes strict_1to3_unbalanced only; use RUN_ALL=1 for all four panels.\n"
    )
    print("Saved:", notes)


def main() -> int:
    args = parse_args()
    out_root = Path(args.out_root)
    summary_dir = Path(args.summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)

    combine_panel_outputs(out_root, args.labels)
    build_static_summaries(out_root, summary_dir)
    build_dynamic_summaries(out_root, summary_dir)
    write_notes(summary_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
