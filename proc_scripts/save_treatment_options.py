#!/usr/bin/env python3
"""
Save treatment sample options from adoption_month_check.csv.

This script reads the event/adoption-month validation output created by
run7d1/run7d2 and creates four treatment sample files:

1. Main sample
   - Includes all valid treatment repositories in adoption_month_check.csv.

2. Exact-match sample
   - Includes only repositories where event_month exactly matches the
     git-detected adoption_month.

3. Within-one-month sample
   - Includes exact matches.
   - Also includes mismatched repositories if the detected adoption month is
     within the configured month tolerance, usually +/- 1 month.

4. Diagnostic sample
   - Includes repositories with no locally detected adoption month.
   - Also includes mismatched repositories where the month difference is larger
     than the configured tolerance.

The output filenames include the actual row counts. For the current JS/TS
treatment pipeline, this should reproduce filenames such as:

  jsts_treatment_sample_main_398.csv
  jsts_treatment_sample_exact_match_381.csv
  jsts_treatment_sample_within1_month_388.csv
  jsts_treatment_sample_diagnostic_10.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for input/output paths and sample rules."""
    parser = argparse.ArgumentParser(
        description="Save treatment sample options from adoption_month_check.csv."
    )

    parser.add_argument(
        "--check-file",
        default="tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv",
        help=(
            "Input CSV created by check_time_of_event_and_adoption.py. "
            "It must contain match_status and month_difference columns."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="tmp_jsts_test/data",
        help="Directory where treatment sample option CSV files will be saved.",
    )

    parser.add_argument(
        "--prefix",
        default="jsts_treatment_sample",
        help="Filename prefix for all output sample files.",
    )

    parser.add_argument(
        "--within-month-tolerance",
        type=int,
        default=1,
        help=(
            "Maximum absolute month difference allowed for the within-month "
            "validation sample. Default is 1, meaning +/- 1 month."
        ),
    )

    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Maximum number of diagnostic repositories to print.",
    )

    return parser.parse_args()


def read_check_file(check_path: Path) -> pd.DataFrame:
    """
    Read adoption_month_check.csv and validate the required columns.

    Required columns:
      - match_status: identifies matched, mismatched, and missing adoption rows.
      - month_difference: numeric month difference between adoption_month and
        event_month. Missing values are expected for missing_adoption_month rows.
    """
    if not check_path.exists():
        raise SystemExit(f"ERROR: check file not found: {check_path}")

    df = pd.read_csv(check_path)

    required_columns = ["match_status", "month_difference"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise SystemExit(
            "ERROR: check file is missing required columns: "
            f"{missing_columns}"
        )

    if len(df) == 0:
        raise SystemExit(f"ERROR: check file has zero rows: {check_path}")

    return df


def build_sample_options(
    df: pd.DataFrame,
    within_month_tolerance: int,
) -> dict[str, pd.DataFrame]:
    """
    Build the four treatment sample options.

    The input DataFrame is expected to contain one row per treatment repository.

    Sample definitions:
      - main:
          Every row from adoption_month_check.csv.
      - exact:
          Rows where match_status == "matched".
      - within1:
          Rows where match_status == "matched", plus mismatched rows whose
          absolute month_difference is within the configured tolerance.
      - diagnostic:
          Rows where match_status == "missing_adoption_month", plus mismatched
          rows whose absolute month_difference is larger than the configured
          tolerance.

    Note:
      pd.to_numeric(..., errors="coerce") converts blank values to NaN.
      This is useful because missing_adoption_month rows usually do not have
      a valid month_difference value.
    """
    month_diff = pd.to_numeric(df["month_difference"], errors="coerce")

    matched_mask = df["match_status"].eq("matched")
    mismatched_mask = df["match_status"].eq("mismatched")
    missing_adoption_mask = df["match_status"].eq("missing_adoption_month")

    within_tolerance_mask = month_diff.abs().le(within_month_tolerance)
    large_mismatch_mask = ~within_tolerance_mask

    main = df.copy()

    exact = df[matched_mask].copy()

    within = df[
        matched_mask
        | (
            mismatched_mask
            & within_tolerance_mask
        )
    ].copy()

    diagnostic = df[
        missing_adoption_mask
        | (
            mismatched_mask
            & large_mismatch_mask
        )
    ].copy()

    return {
        "main": main,
        "exact": exact,
        "within": within,
        "diagnostic": diagnostic,
    }


def build_output_files(
    output_dir: Path,
    prefix: str,
    samples: dict[str, pd.DataFrame],
    within_month_tolerance: int,
) -> dict[str, Path]:
    """
    Create output filenames using actual row counts.

    Counted filenames are safer than hard-coded filenames because they make the
    output self-documenting. If the input sample changes later, the filename will
    automatically reflect the new row count.
    """
    return {
        "main": output_dir / f"{prefix}_main_{len(samples['main'])}.csv",
        "exact": output_dir / f"{prefix}_exact_match_{len(samples['exact'])}.csv",
        "within": (
            output_dir
            / f"{prefix}_within{within_month_tolerance}_month_{len(samples['within'])}.csv"
        ),
        "diagnostic": (
            output_dir
            / f"{prefix}_diagnostic_{len(samples['diagnostic'])}.csv"
        ),
    }


def save_samples(
    samples: dict[str, pd.DataFrame],
    output_files: dict[str, Path],
) -> None:
    """Save each treatment sample DataFrame to its corresponding CSV file."""
    for sample_name, sample_df in samples.items():
        output_path = output_files[sample_name]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_df.to_csv(output_path, index=False)


def print_summary(
    df: pd.DataFrame,
    samples: dict[str, pd.DataFrame],
    output_files: dict[str, Path],
    top_print: int,
) -> None:
    """Print row counts, output paths, and diagnostic repositories."""
    print("Input rows:", len(df))
    print("Main rows:", len(samples["main"]), "->", output_files["main"])
    print("Exact matched rows:", len(samples["exact"]), "->", output_files["exact"])
    print(
        "Within-one-month rows:",
        len(samples["within"]),
        "->",
        output_files["within"],
    )
    print(
        "Diagnostic rows:",
        len(samples["diagnostic"]),
        "->",
        output_files["diagnostic"],
    )

    print()
    print("Match status counts:")
    print(df["match_status"].fillna("(missing)").value_counts().to_string())

    print()
    print("Diagnostic repos:")

    diagnostic = samples["diagnostic"]

    diagnostic_columns = [
        "repo_name",
        "repo_primary_language",
        "event_month",
        "adoption_month",
        "match_status",
        "month_difference",
        "confidence",
        "evidence_paths",
    ]
    diagnostic_columns = [
        col for col in diagnostic_columns if col in diagnostic.columns
    ]

    if len(diagnostic) == 0:
        print("(No diagnostic repositories.)")
        return

    if top_print > 0:
        diagnostic = diagnostic.head(top_print)

    print(diagnostic[diagnostic_columns].to_string(index=False))


def main() -> None:
    """Run the treatment sample export workflow."""
    args = parse_args()

    check_path = Path(args.check_file)
    output_dir = Path(args.output_dir)

    df = read_check_file(check_path)

    samples = build_sample_options(
        df=df,
        within_month_tolerance=args.within_month_tolerance,
    )

    output_files = build_output_files(
        output_dir=output_dir,
        prefix=args.prefix,
        samples=samples,
        within_month_tolerance=args.within_month_tolerance,
    )

    save_samples(
        samples=samples,
        output_files=output_files,
    )

    print_summary(
        df=df,
        samples=samples,
        output_files=output_files,
        top_print=args.top_print,
    )


if __name__ == "__main__":
    main()
    