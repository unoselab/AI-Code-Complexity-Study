#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare candidate event_month with git-detected adoption_month."
    )
    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--adoption-file", required=True)
    parser.add_argument("--output-match-file", required=True)
    parser.add_argument("--top-print", type=int, default=50)
    return parser.parse_args()


def clean_month(series: pd.Series) -> pd.Series:
    """Normalize month-like values to YYYY-MM strings."""
    s = series.astype("string").str.strip()

    # Treat common missing tokens as NA.
    s = s.mask(s.str.lower().isin(["", "nan", "nat", "none", "<na>"]))

    # Convert YYYYMM to YYYY-MM.
    yyyymm = s.str.fullmatch(r"\d{6}", na=False)
    s = s.mask(yyyymm, s.str.slice(0, 4) + "-" + s.str.slice(4, 6))

    # Keep the first 7 characters for YYYY-MM or ISO dates.
    s = s.str.slice(0, 7)

    # Keep only valid-looking YYYY-MM values.
    valid = s.str.fullmatch(r"\d{4}-\d{2}", na=False)
    s = s.mask(~valid)

    return s


def month_to_index(series: pd.Series) -> pd.Series:
    """Convert YYYY-MM strings to integer month index."""
    s = clean_month(series)
    year = pd.to_numeric(s.str.slice(0, 4), errors="coerce")
    month = pd.to_numeric(s.str.slice(5, 7), errors="coerce")
    return year * 12 + month


def pick_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    """Pick the first available column from a candidate list."""
    for col in candidates:
        if col in df.columns:
            return col
    raise SystemExit(
        f"ERROR: cannot find {label} column. Tried: {', '.join(candidates)}"
    )


def main() -> None:
    args = parse_args()

    candidate_path = Path(args.candidate_file)
    adoption_path = Path(args.adoption_file)
    output_path = Path(args.output_match_file)

    if not candidate_path.exists():
        raise SystemExit(f"ERROR: candidate file not found: {candidate_path}")

    if not adoption_path.exists():
        raise SystemExit(f"ERROR: adoption file not found: {adoption_path}")

    candidates = pd.read_csv(candidate_path)
    adoptions = pd.read_csv(adoption_path)

    if "repo_name" not in candidates.columns:
        raise SystemExit("ERROR: candidate file must contain repo_name.")

    if "repo_name" not in adoptions.columns:
        raise SystemExit("ERROR: adoption file must contain repo_name.")

    event_col = pick_column(
        candidates,
        ["event_month", "event", "candidate_event_month"],
        "event month",
    )

    adoption_col = pick_column(
        adoptions,
        ["adoption_month", "cursor_adoption_month", "detected_adoption_month"],
        "adoption month",
    )

    # Keep useful adoption-side columns without duplicating repo_name.
    adoption_keep = ["repo_name", adoption_col]
    for col in [
        "adoption_date",
        "first_cursor_commit",
        "adoption_commit",
        "confidence",
        "evidence_paths",
        "evidence",
    ]:
        if col in adoptions.columns and col not in adoption_keep:
            adoption_keep.append(col)

    adoption_small = adoptions[adoption_keep].drop_duplicates("repo_name").copy()

    if adoption_col != "adoption_month":
        adoption_small = adoption_small.rename(columns={adoption_col: "adoption_month"})

    merged = candidates.merge(adoption_small, on="repo_name", how="left")

    # Preserve the original event column but expose a standard event_month column.
    if event_col != "event_month":
        merged["event_month"] = merged[event_col]

    merged["event_month_clean"] = clean_month(merged["event_month"])
    merged["adoption_month_clean"] = clean_month(merged["adoption_month"])

    event_idx = month_to_index(merged["event_month_clean"])
    adoption_idx = month_to_index(merged["adoption_month_clean"])

    merged["month_difference"] = adoption_idx - event_idx

    # Avoid pd.NA boolean ambiguity by requiring both sides to be non-missing first.
    has_event = merged["event_month_clean"].notna()
    has_adoption = merged["adoption_month_clean"].notna()

    merged["event_month_match"] = (
        has_event
        & has_adoption
        & (merged["event_month_clean"] == merged["adoption_month_clean"])
    )

    merged["match_status"] = "mismatched"
    merged.loc[~has_event, "match_status"] = "missing_event_month"
    merged.loc[has_event & ~has_adoption, "match_status"] = "missing_adoption_month"
    merged.loc[merged["event_month_match"], "match_status"] = "matched"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)

    total = len(merged)
    matched = int(merged["event_month_match"].sum())
    missing_event = int((~has_event).sum())
    missing_adoption = int((has_event & ~has_adoption).sum())
    mismatched = int(
        (has_event & has_adoption & ~merged["event_month_match"]).sum()
    )
    detected = int(has_adoption.sum())

    print("Candidate file:", candidate_path)
    print("Adoption file: ", adoption_path)
    print("Output file:   ", output_path)
    print()

    print("Treatment repos:", total)
    print("Repos with detected adoption month:", detected)
    print("Matched event/adoption month:", matched)
    print("Mismatched event/adoption month:", mismatched)
    print("Missing event month:", missing_event)
    print("Missing adoption month:", missing_adoption)
    print()

    status_counts = merged["match_status"].value_counts(dropna=False)
    print("Match status counts:")
    print(status_counts.to_string())
    print()

    display_cols = [
        "repo_name",
        "event_month",
        "adoption_month",
        "adoption_date",
        "event_month_match",
        "match_status",
        "month_difference",
        "confidence",
        "evidence_paths",
    ]
    display_cols = [c for c in display_cols if c in merged.columns]

    print(f"Event/adoption month check, top {args.top_print}:")
    print(merged[display_cols].head(args.top_print).to_string(index=False))


if __name__ == "__main__":
    main()
