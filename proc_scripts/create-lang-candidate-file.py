#!/usr/bin/env python3
"""
Create a language-specific candidate CSV from an all-eligible candidate file.

Example:
  python proc_scripts/create-lang-candidate-file.py \
    --input-file tmp_typescript_test/data/top_typescript_clone_candidates_all_eligible.csv \
    --output-file tmp_typescript_test/data/ai_adopt_repo_typescript_candidates.csv \
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
        description="Filter candidate repositories by primary language."
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Input candidate CSV, usually *_all_eligible.csv.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output language-specific candidate CSV.",
    )
    parser.add_argument(
        "--language",
        required=True,
        help='Target primary language, e.g., "TypeScript", "Python", "JavaScript".',
    )
    parser.add_argument(
        "--language-column",
        default="repo_primary_language",
        help="Column containing the repository primary language.",
    )
    parser.add_argument(
        "--rank-column",
        default="rank",
        help="Column used to preserve candidate ranking order.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of rows to print for inspection.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty output instead of failing when no rows match.",
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


def filter_by_language(
    df: pd.DataFrame,
    language: str,
    language_column: str,
) -> pd.DataFrame:
    require_columns(df, [language_column])

    out = df[df[language_column].eq(language)].copy()
    return out


def sort_candidates(df: pd.DataFrame, rank_column: str) -> pd.DataFrame:
    if rank_column in df.columns:
        return df.sort_values(
            rank_column,
            key=lambda s: pd.to_numeric(s, errors="coerce"),
        ).reset_index(drop=True)

    if "repo_name" in df.columns:
        return df.sort_values("repo_name").reset_index(drop=True)

    return df.reset_index(drop=True)


def save_candidates(df: pd.DataFrame, output_file: str) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def print_summary(
    input_file: str,
    output_file: str,
    input_df: pd.DataFrame,
    output_df: pd.DataFrame,
    language: str,
    language_column: str,
    top_print: int,
) -> None:
    print("Input:", input_file)
    print("Input rows:", len(input_df))
    print("Output:", output_file)
    print(f"Target language: {language}")
    print(f"Language column: {language_column}")
    print(f"Language-specific candidate rows: {len(output_df)}")

    if "repo_name" in output_df.columns:
        print("Unique repos:", output_df["repo_name"].nunique())

    print()
    print("Input primary language counts:")
    print(input_df[language_column].fillna("(missing)").value_counts().head(30).to_string())

    if "event_month" in output_df.columns and len(output_df) > 0:
        print()
        print("Event month counts:")
        print(output_df["event_month"].value_counts().sort_index().to_string())

    print()
    print(f"Top {top_print} {language} candidates:")
    cols = [col for col in DEFAULT_DISPLAY_COLUMNS if col in output_df.columns]

    if len(output_df) == 0:
        print("(No matching rows.)")
    elif cols:
        print(output_df[cols].head(top_print).to_string(index=False))
    else:
        print(output_df.head(top_print).to_string(index=False))


def main() -> None:
    args = parse_args()

    df = read_candidates(args.input_file)
    require_columns(df, [args.language_column])

    lang_df = filter_by_language(
        df=df,
        language=args.language,
        language_column=args.language_column,
    )

    lang_df = sort_candidates(lang_df, args.rank_column)

    if lang_df.empty and not args.allow_empty:
        raise SystemExit(
            f"ERROR: no candidate rows matched {args.language_column} == {args.language!r}"
        )

    save_candidates(lang_df, args.output_file)

    print_summary(
        input_file=args.input_file,
        output_file=args.output_file,
        input_df=df,
        output_df=lang_df,
        language=args.language,
        language_column=args.language_column,
        top_print=args.top_print,
    )


if __name__ == "__main__":
    main()
