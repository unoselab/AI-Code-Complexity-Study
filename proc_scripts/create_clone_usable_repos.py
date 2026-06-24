#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a repo list containing only successfully cloned or existing repositories."
    )
    parser.add_argument(
        "--clone-status-file",
        required=True,
        help="Merged clone status CSV, e.g., jsts_treatment_clone_status.csv.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output CSV containing usable repositories only.",
    )
    parser.add_argument(
        "--usable-statuses",
        nargs="+",
        default=["cloned", "skipped_existing", "updated_existing"],
        help="Clone status values treated as usable.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=50,
        help="Number of rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    path = Path(args.clone_status_file)
    if not path.exists():
        raise SystemExit(f"ERROR: clone status file not found: {path}")

    df = pd.read_csv(path)

    if "repo_name" not in df.columns:
        raise SystemExit("ERROR: clone status file must contain repo_name.")

    if "status" not in df.columns:
        raise SystemExit("ERROR: clone status file must contain status.")

    usable = df[df["status"].isin(args.usable_statuses)].copy()
    usable = usable.drop_duplicates("repo_name").reset_index(drop=True)

    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    usable.to_csv(out, index=False)

    print("Clone status file:", path)
    print("Input rows:", len(df))
    print("Unique input repos:", df["repo_name"].nunique())
    print()
    print("Status counts:")
    print(df["status"].fillna("(missing)").value_counts().to_string())
    print()
    print("Usable statuses:", ", ".join(args.usable_statuses))
    print("Usable rows:", len(usable))
    print("Unique usable repos:", usable["repo_name"].nunique())

    if "repo_primary_language" in usable.columns:
        print()
        print("Usable primary language counts:")
        print(usable["repo_primary_language"].fillna("(missing)").value_counts().to_string())

    print()
    print("Saved:", out)
    print()

    cols = [
        "repo_name",
        "repo_primary_language",
        "event_month",
        "pre_panel_months",
        "post_panel_months",
        "balanced_window",
        "status",
        "target_dir",
    ]
    cols = [c for c in cols if c in usable.columns]

    print(f"Top {args.top_print} usable repos:")
    if len(usable) == 0:
        print("(No usable repos.)")
    else:
        print(usable[cols].head(args.top_print).to_string(index=False))


if __name__ == "__main__":
    main()
