#!/usr/bin/env python3
"""
Save treatment sample options from adoption-month validation results.

This script reads an adoption_month_check.csv file and creates four
treatment sample files:

1. main
   - All valid event-month treatment repositories.
   - This is the primary sample for the unbalanced-panel replication.

2. exact
   - Repositories where event_month exactly matches git-detected adoption_month.

3. within1
   - Repositories where:
       a) event_month exactly matches adoption_month, or
       b) event_month and adoption_month differ by at most one month.
   - This can be used as a robustness sample.

4. diagnostic
   - Repositories with missing local adoption evidence or large mismatch.
   - This file is for audit/debugging, not for primary analysis.

Expected input columns:
  repo_name
  event_month
  adoption_month
  match_status
  month_difference

Additional columns are preserved in all output files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create main/exact/within1/diagnostic treatment samples."
    )

    parser.add_argument(
        "--check-file",
        required=True,
        help="Input adoption_month_check.csv file.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where treatment sample option files will be saved.",
    )
    parser.add_argument(
        "--prefix",
        default="treatment_sample",
        help="Output filename prefix.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of diagnostic rows to print.",
    )

    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: list[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(
            f"ERROR: {path} is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> int:
    args = parse_args()

    check_path = Path(args.check_file)
    out_dir = Path(args.output_dir)

    if not check_path.exists():
        raise SystemExit(f"ERROR: check file not found: {check_path}")

    df = pd.read_csv(check_path)

    require_columns(
        df,
        required=["repo_name", "event_month", "match_status", "month_difference"],
        path=check_path,
    )

    # Main sample:
    # Keep all validated treatment repositories. This is the primary sample.
    main = df.copy()

    # Exact-match sample:
    # Keep repositories where baseline event_month equals local git adoption_month.
    exact = df[df["match_status"].eq("matched")].copy()

    # Within-one-month sample:
    # Keep exact matches plus small timing differences.
    month_diff = pd.to_numeric(df["month_difference"], errors="coerce")
    within1 = df[
        df["match_status"].eq("matched")
        | (
            df["match_status"].eq("mismatched")
            & month_diff.abs().le(1)
        )
    ].copy()

    # Diagnostic sample:
    # Missing local adoption evidence or mismatch larger than one month.
    diagnostic = df[
        df["match_status"].eq("missing_adoption_month")
        | (
            df["match_status"].eq("mismatched")
            & ~month_diff.abs().le(1)
        )
    ].copy()

    files = {
        "main": out_dir / f"{args.prefix}_main_{len(main)}.csv",
        "exact": out_dir / f"{args.prefix}_exact_match_{len(exact)}.csv",
        "within1": out_dir / f"{args.prefix}_within1_month_{len(within1)}.csv",
        "diagnostic": out_dir / f"{args.prefix}_diagnostic_{len(diagnostic)}.csv",
    }

    save_csv(main, files["main"])
    save_csv(exact, files["exact"])
    save_csv(within1, files["within1"])
    save_csv(diagnostic, files["diagnostic"])

    print("Input file:", check_path)
    print("Input rows:", len(df))
    print("Unique repos:", df["repo_name"].nunique())
    print()

    print("Match status counts:")
    print(df["match_status"].fillna("(missing)").value_counts(dropna=False).to_string())
    print()

    print("Saved treatment sample files:")
    print("Main rows:", len(main), "->", files["main"])
    print("Exact matched rows:", len(exact), "->", files["exact"])
    print("Within-one-month rows:", len(within1), "->", files["within1"])
    print("Diagnostic rows:", len(diagnostic), "->", files["diagnostic"])
    print()

    print("Diagnostic repos:")
    cols = [
        "repo_name",
        "repo_primary_language",
        "event_month",
        "adoption_month",
        "match_status",
        "month_difference",
        "confidence",
        "evidence_paths",
    ]
    cols = [c for c in cols if c in diagnostic.columns]

    if len(diagnostic) == 0:
        print("(No diagnostic repos.)")
    else:
        print(diagnostic[cols].head(args.top_print).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
