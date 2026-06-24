#!/usr/bin/env python3
"""
Check candidate repositories by balanced event-window size and optionally
write a filtered candidate file.

Example:
  python proc_scripts/check_repo_balanced_window.py \
    --input-file tmp_typescript_test/data/ai_adopt_repo_typescript_candidates.csv \
    --output-file tmp_typescript_test/data/ai_adopt_repo_typescript_candidates_bw6.csv \
    --min-balanced-window 6 \
    --language TypeScript
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_DISPLAY_COLUMNS = [
    "rank",
    "repo_name",
    "event_month",
    "pre_panel_months",
    "post_panel_months",
    "balanced_window",
    "cursor_commit_share",
    "cursor_commit_rows",
    "repo_commits",
    "repo_contributors",
    "repo_stars",
    "repo_primary_language",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check and filter candidate repos by balanced event-window size."
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Input candidate CSV.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output filtered candidate CSV.",
    )
    parser.add_argument(
        "--min-balanced-window",
        type=int,
        default=6,
        help="Minimum required balanced_window value. Default: 6.",
    )
    parser.add_argument(
        "--language",
        default=None,
        help='Optional language label for reporting, e.g., "TypeScript".',
    )
    parser.add_argument(
        "--language-column",
        default="repo_primary_language",
        help="Column containing primary repository language.",
    )
    parser.add_argument(
        "--rank-column",
        default="rank",
        help="Column used to preserve original ranking order.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of filtered rows to print.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty filtered output instead of failing.",
    )
    return parser.parse_args()


def read_candidates(input_file: str) -> pd.DataFrame:
    path = Path(input_file)
    if not path.exists():
        raise SystemExit(f"ERROR: input file not found: {path}")

    df = pd.read_csv(path, dtype=str, low_memory=False)
    if df.empty:
        raise SystemExit(f"ERROR: input file is empty: {path}")

    return df


def require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: missing required columns: {missing}")


def coerce_window_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    required = ["pre_panel_months", "post_panel_months", "balanced_window"]
    require_columns(df, required)

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df["balanced_window"].isna().any():
        bad = int(df["balanced_window"].isna().sum())
        raise SystemExit(f"ERROR: balanced_window has {bad} missing/non-numeric values.")

    return df


def sort_by_rank(df: pd.DataFrame, rank_column: str) -> pd.DataFrame:
    if rank_column in df.columns:
        return df.sort_values(
            rank_column,
            key=lambda s: pd.to_numeric(s, errors="coerce"),
        ).reset_index(drop=True)

    if "repo_name" in df.columns:
        return df.sort_values("repo_name").reset_index(drop=True)

    return df.reset_index(drop=True)


def save_filtered(df: pd.DataFrame, output_file: str) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def print_summary(
    df: pd.DataFrame,
    strict: pd.DataFrame,
    input_file: str,
    output_file: str,
    min_balanced_window: int,
    language: str | None,
    top_print: int,
) -> None:
    label = language if language else "candidate"

    print("Input:", input_file)
    print(f"All {label} candidates:", len(df))

    if "repo_name" in df.columns:
        print("Unique repos:", df["repo_name"].nunique())

    if "repo_primary_language" in df.columns:
        print()
        print("Primary language counts:")
        print(df["repo_primary_language"].fillna("(missing)").value_counts().head(30).to_string())

    print()
    print("balanced_window counts:")
    print(df["balanced_window"].value_counts().sort_index().to_string())

    print()
    print(f"{label} candidates with balanced_window >= {min_balanced_window}:", len(strict))

    if "repo_name" in strict.columns:
        print("Unique strict repos:", strict["repo_name"].nunique())

    if "event_month" in strict.columns and len(strict) > 0:
        print()
        print("Event month counts for strict sample:")
        print(strict["event_month"].value_counts().sort_index().to_string())

    print()
    print(f"Saved: {output_file}")
    print("Rows:", len(strict))

    if "repo_name" in strict.columns:
        print("Unique repos:", strict["repo_name"].nunique())

    print()
    print(f"Top strict {label} candidates:")
    cols = [c for c in DEFAULT_DISPLAY_COLUMNS if c in strict.columns]

    if len(strict) == 0:
        print("(No matching rows.)")
    elif cols:
        print(strict[cols].head(top_print).to_string(index=False))
    else:
        print(strict.head(top_print).to_string(index=False))


def main() -> None:
    args = parse_args()

    df = read_candidates(args.input_file)
    df = coerce_window_columns(df)

    strict = df[df["balanced_window"] >= args.min_balanced_window].copy()
    strict = sort_by_rank(strict, args.rank_column)

    if strict.empty and not args.allow_empty:
        raise SystemExit(
            f"ERROR: no rows matched balanced_window >= {args.min_balanced_window}"
        )

    save_filtered(strict, args.output_file)

    print_summary(
        df=df,
        strict=strict,
        input_file=args.input_file,
        output_file=args.output_file,
        min_balanced_window=args.min_balanced_window,
        language=args.language,
        top_print=args.top_print,
    )


if __name__ == "__main__":
    main()
