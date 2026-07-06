#!/usr/bin/env python3
"""
Summarize matched Python DiD panels.

This script summarizes four panel variants using the current Python naming convention:

  1. flexible
     - Keeps all final-clean matched treatments, including treatments with 2 or 3 controls.
     - Uses observed repo-month rows only.

  2. strict
     - Keeps only treatments with exactly 3 final controls.
     - Uses observed repo-month rows only.

  3. flexible_window_driven
     - Uses the flexible matched sample.
     - Completes the Jan 2024-Aug 2025 observation window.

  4. strict_window_driven
     - Uses the strict matched sample.
     - Completes the Jan 2024-Aug 2025 observation window.

Inputs:
  - Panel CSV files under repo_python/did_final/
  - Optional treatment/control coverage files for attrition diagnostics

Outputs:
  - panel_qc_summary.csv
  - panel_qc_by_source.csv
  - panel_qc_paper_comparison.csv
  - panel_qc_attrition_summary.csv
  - panel_qc_dropped_by_strict.csv
  - panel_qc_notes.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


def read_csv_required(path: Path) -> pd.DataFrame:
    """Read a required CSV file and raise a clear error when it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path)


def find_time_column(df: pd.DataFrame) -> Optional[str]:
    """Return the panel time column name."""
    for col in ["time", "month"]:
        if col in df.columns:
            return col
    return None


def find_post_column(df: pd.DataFrame) -> Optional[str]:
    """Return the post-treatment indicator column name."""
    for col in ["post_event", "post", "post_treatment"]:
        if col in df.columns:
            return col
    return None


def find_treatment_column(df: pd.DataFrame) -> Optional[str]:
    """Return the treatment indicator column name."""
    for col in ["is_treatment", "ever_treated", "treated"]:
        if col in df.columns:
            return col
    return None


def source_mask(df: pd.DataFrame, source: str) -> pd.Series:
    """Return a boolean mask for treatment or control rows."""
    if "dataset_source" in df.columns:
        return df["dataset_source"].astype(str).str.lower().eq(source)

    treatment_col = find_treatment_column(df)
    if treatment_col is None:
        raise ValueError(
            "Panel must contain dataset_source or a treatment indicator column "
            "(is_treatment, ever_treated, or treated)."
        )

    if source == "treatment":
        return df[treatment_col].eq(1)
    if source == "control":
        return df[treatment_col].eq(0)

    raise ValueError(f"Unknown source: {source}")


def summarize_panel(panel_name: str, path: Path) -> Dict[str, object]:
    """Summarize one panel file."""
    df = read_csv_required(path)

    if "repo_name" not in df.columns:
        raise ValueError(f"{path} is missing repo_name column.")

    time_col = find_time_column(df)
    post_col = find_post_column(df)

    treat_mask = source_mask(df, "treatment")
    control_mask = source_mask(df, "control")

    treatment_df = df.loc[treat_mask].copy()
    control_df = df.loc[control_mask].copy()

    if post_col is not None:
        post_rows = int(treatment_df[post_col].fillna(0).astype(int).sum())
    else:
        post_rows = None

    summary = {
        "panel": panel_name,
        "file": str(path),
        "rows": int(len(df)),
        "repos": int(df["repo_name"].nunique()),
        "treated_repos": int(treatment_df["repo_name"].nunique()),
        "control_repos": int(control_df["repo_name"].nunique()),
        "treatment_rows": int(len(treatment_df)),
        "control_rows": int(len(control_df)),
        "post_treatment_rows": post_rows,
        "avg_rows_per_repo": round(float(len(df) / df["repo_name"].nunique()), 4)
        if df["repo_name"].nunique()
        else 0.0,
        "time_col": time_col or "",
        "time_min": df[time_col].min() if time_col else "",
        "time_max": df[time_col].max() if time_col else "",
    }

    return summary


def summarize_by_source(panel_name: str, path: Path) -> pd.DataFrame:
    """Summarize treatment/control rows inside one panel."""
    df = read_csv_required(path)

    if "repo_name" not in df.columns:
        raise ValueError(f"{path} is missing repo_name column.")

    post_col = find_post_column(df)
    rows: List[Dict[str, object]] = []

    for source in ["treatment", "control"]:
        mask = source_mask(df, source)
        sub = df.loc[mask].copy()

        if post_col is not None:
            post_rows = int(sub[post_col].fillna(0).astype(int).sum())
        else:
            post_rows = None

        rows.append(
            {
                "panel": panel_name,
                "dataset_source": source,
                "repos": int(sub["repo_name"].nunique()),
                "rows": int(len(sub)),
                "post_rows": post_rows,
            }
        )

    return pd.DataFrame(rows)


def build_paper_comparison(summary_df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    """Compare flexible and strict unbalanced panels with paper Table 7."""
    rows = []
    paper = {
        "treatment_repos": args.paper_treatment_repos,
        "control_repos": args.paper_control_repos,
        "total_observations": args.paper_total_observations,
        "post_treatment_observations": args.paper_post_treatment_observations,
    }

    target_panels = ["flexible", "strict"]

    for panel in target_panels:
        match = summary_df.loc[summary_df["panel"].eq(panel)]
        if match.empty:
            continue

        row = match.iloc[0]

        rows.append(
            {
                "panel": panel,
                "comparison_focus": "sample_size" if panel == "flexible" else "matching_rule",
                "paper_treatment_repos": paper["treatment_repos"],
                "current_treatment_repos": int(row["treated_repos"]),
                "treatment_repo_difference": int(row["treated_repos"]) - paper["treatment_repos"],
                "paper_control_repos": paper["control_repos"],
                "current_control_repos": int(row["control_repos"]),
                "control_repo_difference": int(row["control_repos"]) - paper["control_repos"],
                "paper_total_observations": paper["total_observations"],
                "current_total_observations": int(row["rows"]),
                "total_observation_difference": int(row["rows"]) - paper["total_observations"],
                "paper_post_treatment_observations": paper["post_treatment_observations"],
                "current_post_treatment_observations": int(row["post_treatment_rows"]),
                "post_treatment_observation_difference": int(row["post_treatment_rows"])
                - paper["post_treatment_observations"],
            }
        )

    return pd.DataFrame(rows)


def build_attrition_summary(args: argparse.Namespace) -> pd.DataFrame:
    """Build treatment/control attrition summary when supporting files are available."""
    rows: List[Dict[str, object]] = []

    def add(metric: str, value: object, note: str) -> None:
        rows.append({"metric": metric, "value": value, "note": note})

    if args.treatment_sample.exists():
        treatment = pd.read_csv(args.treatment_sample)
        if "repo_name" in treatment.columns:
            add(
                "current_treatment_sample",
                int(treatment["repo_name"].nunique()),
                "Current reproducible Python treatment sample.",
            )

    if args.treatment_missing_matching.exists():
        missing = pd.read_csv(args.treatment_missing_matching)
        repo_col = "repo_name" if "repo_name" in missing.columns else None
        if repo_col:
            add(
                "treatments_missing_matching_rows",
                int(missing[repo_col].nunique()),
                "Treatment repos present in the treatment sample but missing selected matching rows.",
            )

    if args.final_coverage.exists():
        coverage = pd.read_csv(args.final_coverage)
        if "treatment_repo" in coverage.columns:
            add(
                "flexible_final_matched_treatments",
                int(coverage["treatment_repo"].nunique()),
                "Treatments retained by the flexible final-clean matched pair file.",
            )

        if "num_final_controls" in coverage.columns:
            counts = coverage["num_final_controls"].value_counts().sort_index()
            for num_controls, count in counts.items():
                add(
                    f"treatments_with_{int(num_controls)}_final_controls",
                    int(count),
                    "Final control-count distribution after clone and local Cursor filtering.",
                )

    if args.strict_coverage.exists():
        strict_coverage = pd.read_csv(args.strict_coverage)
        if "treatment_repo" in strict_coverage.columns:
            add(
                "strict_1to3_treatments",
                int(strict_coverage["treatment_repo"].nunique()),
                "Treatments retained by the strict 1:3 final-clean matched pair file.",
            )

    if args.final_controls.exists():
        final_controls = pd.read_csv(args.final_controls)
        if "repo_name" in final_controls.columns:
            add(
                "final_clean_controls_before_panel",
                int(final_controls["repo_name"].nunique()),
                "Final clean controls before unbalanced observed-row filtering.",
            )

    return pd.DataFrame(rows)


def build_dropped_by_strict(args: argparse.Namespace) -> pd.DataFrame:
    """Return treatments dropped by strict 1:3 because they do not have exactly 3 controls."""
    if not args.final_coverage.exists():
        return pd.DataFrame(columns=["treatment_repo", "num_final_controls"])

    coverage = pd.read_csv(args.final_coverage)
    needed = {"treatment_repo", "num_final_controls"}
    if not needed.issubset(set(coverage.columns)):
        return pd.DataFrame(columns=["treatment_repo", "num_final_controls"])

    out = coverage.loc[coverage["num_final_controls"].ne(3), ["treatment_repo", "num_final_controls"]].copy()
    out = out.sort_values(["num_final_controls", "treatment_repo"])
    return out


def write_notes(
    path: Path,
    summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    attrition_df: pd.DataFrame,
) -> None:
    """Write a compact Markdown note for human review."""
    lines: List[str] = []
    lines.append("# Python Matched Panel QC Notes")
    lines.append("")
    lines.append("## Panel summary")
    lines.append("")
    lines.append(summary_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Paper comparison")
    lines.append("")
    if comparison_df.empty:
        lines.append("(No paper comparison rows generated.)")
    else:
        lines.append(comparison_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Attrition summary")
    lines.append("")
    if attrition_df.empty:
        lines.append("(No attrition summary rows generated.)")
    else:
        lines.append(attrition_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "- `flexible` is the sample-size / coverage-oriented unbalanced panel. "
        "It keeps all final-clean matched treatments, including treatments with 2 or 3 controls."
    )
    lines.append(
        "- `strict` is the matching-rule-oriented unbalanced panel. "
        "It keeps only treatments with exactly 3 final controls."
    )
    lines.append(
        "- `window_driven` panels complete the Jan 2024-Aug 2025 window and should not be "
        "directly compared with paper Table 7 unbalanced observation counts."
    )
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize matched Python DiD panels.")

    parser.add_argument("--flexible-panel", type=Path, required=True)
    parser.add_argument("--strict-panel", type=Path, required=True)
    parser.add_argument("--flexible-window-driven-panel", type=Path, required=True)
    parser.add_argument("--strict-window-driven-panel", type=Path, required=True)

    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-by-source", type=Path, required=True)
    parser.add_argument("--output-paper-comparison", type=Path, required=True)
    parser.add_argument("--output-attrition", type=Path, required=True)
    parser.add_argument("--output-dropped-by-strict", type=Path, required=True)
    parser.add_argument("--output-notes", type=Path, required=True)

    parser.add_argument("--treatment-sample", type=Path, default=Path("repo_python/treatment_sample_main.csv"))
    parser.add_argument(
        "--treatment-missing-matching",
        type=Path,
        default=Path("repo_python/treatment_missing_matching_main.csv"),
    )
    parser.add_argument(
        "--final-coverage",
        type=Path,
        default=Path("repo_python/control_pair_coverage_main_final_clean.csv"),
    )
    parser.add_argument(
        "--strict-coverage",
        type=Path,
        default=Path("repo_python/control_pair_coverage_main_final_clean_1to3_only.csv"),
    )
    parser.add_argument(
        "--final-controls",
        type=Path,
        default=Path("repo_python/control_clone_usable_repos_main_final_clean.csv"),
    )

    parser.add_argument("--paper-treatment-repos", type=int, default=121)
    parser.add_argument("--paper-control-repos", type=int, default=127)
    parser.add_argument("--paper-total-observations", type=int, default=2461)
    parser.add_argument("--paper-post-treatment-observations", type=int, default=582)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    panel_paths = {
        "flexible": args.flexible_panel,
        "strict": args.strict_panel,
        "flexible_window_driven": args.flexible_window_driven_panel,
        "strict_window_driven": args.strict_window_driven_panel,
    }

    summary_rows = []
    by_source_frames = []

    for panel_name, path in panel_paths.items():
        summary_rows.append(summarize_panel(panel_name, path))
        by_source_frames.append(summarize_by_source(panel_name, path))

    summary_df = pd.DataFrame(summary_rows)
    by_source_df = pd.concat(by_source_frames, ignore_index=True)
    comparison_df = build_paper_comparison(summary_df, args)
    attrition_df = build_attrition_summary(args)
    dropped_df = build_dropped_by_strict(args)

    for path in [
        args.output_summary,
        args.output_by_source,
        args.output_paper_comparison,
        args.output_attrition,
        args.output_dropped_by_strict,
        args.output_notes,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)

    summary_df.to_csv(args.output_summary, index=False)
    by_source_df.to_csv(args.output_by_source, index=False)
    comparison_df.to_csv(args.output_paper_comparison, index=False)
    attrition_df.to_csv(args.output_attrition, index=False)
    dropped_df.to_csv(args.output_dropped_by_strict, index=False)

    write_notes(args.output_notes, summary_df, comparison_df, attrition_df)

    print("Saved panel summary:", args.output_summary)
    print(summary_df.to_string(index=False))
    print()
    print("Saved by-source summary:", args.output_by_source)
    print(by_source_df.to_string(index=False))
    print()
    print("Saved paper comparison:", args.output_paper_comparison)
    print(comparison_df.to_string(index=False))
    print()
    print("Saved attrition summary:", args.output_attrition)
    print(attrition_df.to_string(index=False))
    print()
    print("Saved dropped-by-strict diagnostics:", args.output_dropped_by_strict)
    if len(dropped_df):
        print(dropped_df.to_string(index=False))
    else:
        print("(none)")
    print()
    print("Saved notes:", args.output_notes)


if __name__ == "__main__":
    main()
