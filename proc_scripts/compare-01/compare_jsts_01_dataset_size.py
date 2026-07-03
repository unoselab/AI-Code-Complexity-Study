#!/usr/bin/env python3
"""
Create only one CSV:

  compare/output/jsts_dataset_size_comparison.csv

This script is a decomposed version of the dataset-size part of
proc_scripts/compare_jsts_paper.py.

It compares:
1. Paper Appendix Table 7 JS/TS row
2. Recomputed paper JS/TS matched panel
3. Paper JS/TS treatment-only diagnostic panel
4. Our main unbalanced JS/TS panel
5. Our strict 1:3 unbalanced JS/TS panel
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pandas as pd


PAPER_TABLE7_JSTS = {
    "ds": "paper_table7_jsts",
    "treat": 411,
    "ctrl": 422,
    "obs": 8870,
    "post": 2279,
    "min_t": "",
    "max_t": "",
}

DATASET_ROW_NOTES = {
    "paper_table7_jsts": (
        "Paper Appendix Table 7 JavaScript/TypeScript row."
    ),
    "paper_jsts_matched_panel_recomputed": (
        "Recomputed from baseline panel using JS/TS treatments and their matched "
        "controls from baseline matching.csv."
    ),
    "paper_jsts_treatment_only_panel": (
        "Treatment-only baseline panel restricted to JS/TS treatment repos. "
        "Not directly comparable to Table 7 because controls are excluded."
    ),
    "our_main_unbalanced": (
        "Our main unbalanced JS/TS panel."
    ),
    "our_strict_1to3_unbalanced": (
        "Our strict 1:3 unbalanced JS/TS panel."
    ),
}

LANGUAGE_COL_CANDIDATES = [
    "primary_language",
    "repo_language",
    "language",
    "repo_primary_language",
    "detected_language",
]

REPO_COL_CANDIDATES = [
    "repo_name",
    "repo",
    "repository",
    "full_name",
]

TREATMENT_COL_CANDIDATES = [
    "treatment_repo",
    "repo_name",
    "repo",
]


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description=(
            "Create compare/output/jsts_dataset_size_comparison.csv only."
        )
    )

    parser.add_argument(
        "--paper-repos",
        default=str(project_root / "data_baseline_backup/repos.csv"),
        help="Paper baseline repository metadata CSV.",
    )
    parser.add_argument(
        "--paper-matching",
        default=str(project_root / "data_baseline_backup/matching.csv"),
        help="Paper baseline matching CSV.",
    )
    parser.add_argument(
        "--paper-panel",
        default=str(project_root / "data_baseline_backup/panel_event_monthly.csv"),
        help="Paper baseline monthly panel CSV.",
    )
    parser.add_argument(
        "--our-main-panel",
        default=str(
            project_root
            / "tmp_jsts_test/data/jsts_did_final/"
            / "panel_event_monthly_matched_final_clean.csv"
        ),
        help="Our main unbalanced JS/TS panel CSV.",
    )
    parser.add_argument(
        "--our-strict-panel",
        default=str(
            project_root
            / "tmp_jsts_test/data/jsts_did_final/"
            / "panel_event_monthly_matched_final_clean_1to3_only.csv"
        ),
        help="Our strict 1:3 unbalanced JS/TS panel CSV.",
    )
    parser.add_argument(
        "--out-csv",
        default=str(
            # project_root / "compare/output/jsts_dataset_size_comparison.csv"
            script_dir / "jsts_dataset_size_comparison.csv"
        ),
        help="Output CSV path.",
    )

    parser.add_argument(
        "--exclude-treatment-only",
        action="store_true",
        help=(
            "Exclude paper_jsts_treatment_only_panel from the output. "
            "Default is to include it as a diagnostic row."
        ),
    )

    return parser.parse_args()


def read_csv_required(path: str | Path) -> pd.DataFrame:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path)


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    names = set(df.columns)

    for col in candidates:
        if col in names:
            return col

    return None


def normalize_repo_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def get_repo_col(df: pd.DataFrame) -> str:
    col = find_col(df, REPO_COL_CANDIDATES)

    if col is None:
        raise ValueError(
            "Could not find repository column. "
            f"Available columns: {list(df.columns)}"
        )

    return col


def get_jsts_repos_from_metadata(df: pd.DataFrame) -> Set[str]:
    repo_col = get_repo_col(df)
    lang_col = find_col(df, LANGUAGE_COL_CANDIDATES)

    if lang_col is None:
        raise ValueError(
            "Could not find language column in paper repos file. "
            f"Available columns: {list(df.columns)}"
        )

    lang = df[lang_col].astype(str).str.lower()

    mask = lang.isin(["javascript", "typescript"]) | lang.str.contains(
        "javascript|typescript",
        regex=True,
        na=False,
    )

    return set(normalize_repo_series(df.loc[mask, repo_col]))


def sort_matched_control_columns(cols: List[str]) -> List[str]:
    def key(col: str) -> tuple[int, str]:
        match = re.search(r"(\d+)$", col)
        if match:
            return (int(match.group(1)), col)
        return (9999, col)

    return sorted(cols, key=key)


def matching_wide_to_long(
    df: pd.DataFrame,
    treatment_filter: Optional[Set[str]] = None,
) -> pd.DataFrame:
    treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)

    if treatment_col is None:
        raise ValueError(
            "Could not find treatment repo column in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    matched_cols = [
        col
        for col in df.columns
        if col.startswith("matched_control_") or col.startswith("control_")
    ]

    matched_cols = sort_matched_control_columns(matched_cols)

    if not matched_cols:
        raise ValueError(
            "Could not find matched control columns in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    rows = []

    for _, row in df.iterrows():
        treatment_repo = str(row[treatment_col]).strip()

        if not treatment_repo or treatment_repo == "nan":
            continue

        if treatment_filter is not None and treatment_repo not in treatment_filter:
            continue

        for rank, col in enumerate(matched_cols, start=1):
            control_repo = row.get(col)

            if pd.isna(control_repo):
                continue

            control_repo = str(control_repo).strip()

            if not control_repo or control_repo == "nan":
                continue

            rows.append(
                {
                    "treatment_repo": treatment_repo,
                    "control_repo": control_repo,
                    "control_rank": rank,
                }
            )

    out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(
            columns=["treatment_repo", "control_repo", "control_rank"]
        )

    out["treatment_repo"] = normalize_repo_series(out["treatment_repo"])
    out["control_repo"] = normalize_repo_series(out["control_repo"])

    return out


def infer_treatment_mask(panel: pd.DataFrame) -> pd.Series:
    if "dataset_source" in panel.columns:
        return panel["dataset_source"].astype(str).str.lower().eq("treatment")

    if "is_treatment" in panel.columns:
        return panel["is_treatment"].fillna(0).astype(int).eq(1)

    if "event" in panel.columns:
        return panel["event"].notna()

    raise ValueError(
        "Could not infer treatment/control rows. "
        "Need dataset_source, is_treatment, or event column."
    )


def summarize_panel(
    panel: pd.DataFrame,
    dataset_label: str,
    restrict_repos: Optional[Set[str]] = None,
) -> Dict[str, object]:
    repo_col = get_repo_col(panel)

    df = panel.copy()
    df[repo_col] = normalize_repo_series(df[repo_col])

    if restrict_repos is not None:
        df = df[df[repo_col].isin(restrict_repos)].copy()

    if df.empty:
        return {
            "ds": dataset_label,
            "treat": 0,
            "ctrl": 0,
            "obs": 0,
            "post": 0,
            "min_t": "",
            "max_t": "",
        }

    treat_mask = infer_treatment_mask(df)
    control_mask = ~treat_mask

    post_obs = 0
    if "post_event" in df.columns:
        post_obs = int(
            df.loc[treat_mask, "post_event"]
            .fillna(0)
            .astype(int)
            .sum()
        )

    time_col = find_col(df, ["time", "month", "week"])

    return {
        "ds": dataset_label,
        "treat": int(df.loc[treat_mask, repo_col].nunique()),
        "ctrl": int(df.loc[control_mask, repo_col].nunique()),
        "obs": int(len(df)),
        "post": post_obs,
        "min_t": str(df[time_col].min()) if time_col else "",
        "max_t": str(df[time_col].max()) if time_col else "",
    }


def build_dataset_size_comparison(args: argparse.Namespace) -> pd.DataFrame:
    paper_repos = read_csv_required(args.paper_repos)
    paper_matching = read_csv_required(args.paper_matching)
    paper_panel = read_csv_required(args.paper_panel)
    our_main_panel = read_csv_required(args.our_main_panel)
    our_strict_panel = read_csv_required(args.our_strict_panel)

    paper_jsts_treatments = get_jsts_repos_from_metadata(paper_repos)

    paper_jsts_pairs = matching_wide_to_long(
        paper_matching,
        treatment_filter=paper_jsts_treatments,
    )

    paper_jsts_matched_controls = set(paper_jsts_pairs["control_repo"])
    paper_jsts_matched_repo_set = (
        paper_jsts_treatments | paper_jsts_matched_controls
    )

    rows: List[Dict[str, object]] = []

    rows.append(PAPER_TABLE7_JSTS.copy())

    rows.append(
        summarize_panel(
            paper_panel,
            "paper_jsts_matched_panel_recomputed",
            restrict_repos=paper_jsts_matched_repo_set,
        )
    )

    if not args.exclude_treatment_only:
        rows.append(
            summarize_panel(
                paper_panel,
                "paper_jsts_treatment_only_panel",
                restrict_repos=paper_jsts_treatments,
            )
        )

    rows.append(
        summarize_panel(
            our_main_panel,
            "our_main_unbalanced",
            restrict_repos=None,
        )
    )

    rows.append(
        summarize_panel(
            our_strict_panel,
            "our_strict_1to3_unbalanced",
            restrict_repos=None,
        )
    )

    out = pd.DataFrame(rows)
    out["note"] = out["ds"].map(DATASET_ROW_NOTES)

    output_columns = [
        "ds",
        "treat",
        "ctrl",
        "obs",
        "post",
        "min_t",
        "max_t",
    ]

    return out[output_columns]


def write_csv_with_metadata(path: str | Path, df: pd.DataFrame) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = path.with_name(f"{path.stem}-metadata.txt")

    dataset_note_lines = [
        "Dataset row notes",
    ]

    for ds, note in DATASET_ROW_NOTES.items():
        dataset_note_lines.append(f"{ds:<38} - {note}")

    dataset_notes = "\n".join(dataset_note_lines)

    metadata = f"""File: {path.name}
---

{dataset_notes}

---
Column notes
ds    - Dataset/stage label.
treat - Number of treatment repositories.
ctrl  - Number of control repositories.
obs   - Total panel observations/rows.
post  - Treatment-group post-treatment observations.
min_t - First time period in the panel, if available.
max_t - Last time period in the panel, if available.
---
"""

    df.to_csv(path, index=False)

    with metadata_path.open("w", encoding="utf-8", newline="") as f:
        f.write(metadata)


def main() -> None:
    args = parse_args()

    dataset_summary = build_dataset_size_comparison(args)

    write_csv_with_metadata(args.out_csv, dataset_summary)

    print("Dataset-size comparison completed.")
    print(f"Output CSV: {args.out_csv}")
    print("")
    print(dataset_summary.to_string(index=False))


if __name__ == "__main__":
    main()
