#!/usr/bin/env python3
"""
Compare the paper Appendix JS/TS dataset with our main_unbalanced and
strict_1to3_unbalanced JS/TS replication datasets.

Main questions:
1. How close is our main_unbalanced / strict_1to3_unbalanced dataset to
   the paper Appendix JS/TS dataset?
2. Why is strict_1to3_unbalanced smaller?
3. Which treatments are dropped when moving from final_clean to 1to3_only?

Outputs:
- compare/output/jsts_dataset_size_comparison.csv
- compare/output/jsts_pair_stage_comparison.csv
- compare/output/jsts_strict_dropped_treatments.csv
- compare/output/jsts_repo_set_differences.csv
- compare/output/jsts_compare_report.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


PAPER_APPENDIX_JSTS = {
    "dataset": "paper_appendix_jsts_table7",
    "treatment_repos": 411,
    "control_repos": 422,
    "total_observations": 8870,
    "post_treatment_observations": 2279,
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

CONTROL_COL_CANDIDATES = [
    "control_repo",
    "matched_control",
    "matched_repo",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare paper JS/TS dataset with our main/strict JS/TS panels."
    )

    parser.add_argument(
        "--paper-repos",
        default="data_baseline_backup/repos.csv",
        help="Paper baseline repository metadata CSV.",
    )
    parser.add_argument(
        "--paper-matching",
        default="data_baseline_backup/matching.csv",
        help="Paper baseline matching CSV.",
    )
    parser.add_argument(
        "--paper-panel",
        default="data_baseline_backup/panel_event_monthly.csv",
        help="Paper baseline monthly panel CSV.",
    )

    parser.add_argument(
        "--our-treatment-sample",
        default="tmp_jsts_test/data/jsts_treatment_sample_main_398.csv",
        help="Our JS/TS treatment sample CSV.",
    )
    parser.add_argument(
        "--our-main-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398_final_clean.csv",
        help="Our final-clean main pair CSV.",
    )
    parser.add_argument(
        "--our-strict-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398_final_clean_1to3_only.csv",
        help="Our strict 1:3 pair CSV.",
    )
    parser.add_argument(
        "--our-main-panel",
        default=(
            "tmp_jsts_test/data/jsts_did_final/"
            "panel_event_monthly_matched_final_clean.csv"
        ),
        help="Our main_unbalanced panel CSV.",
    )
    parser.add_argument(
        "--our-strict-panel",
        default=(
            "tmp_jsts_test/data/jsts_did_final/"
            "panel_event_monthly_matched_final_clean_1to3_only.csv"
        ),
        help="Our strict_1to3_unbalanced panel CSV.",
    )

    parser.add_argument(
        "--out-dir",
        default="compare/output",
        help="Output directory for comparison files.",
    )

    return parser.parse_args()


def read_csv_required(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path)


def read_csv_optional(path: str | Path) -> Optional[pd.DataFrame]:
    path = Path(path)
    if not path.exists():
        return None
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
            f"Could not find repository column. Available columns: {list(df.columns)}"
        )
    return col


def get_jsts_repos_from_metadata(df: pd.DataFrame) -> Set[str]:
    repo_col = get_repo_col(df)
    lang_col = find_col(df, LANGUAGE_COL_CANDIDATES)

    if lang_col is None:
        return set()

    lang = df[lang_col].astype(str).str.lower()
    mask = lang.isin(["javascript", "typescript"]) | lang.str.contains(
        "javascript|typescript", regex=True, na=False
    )

    return set(normalize_repo_series(df.loc[mask, repo_col]))


def matching_wide_to_long(
    df: pd.DataFrame,
    treatment_filter: Optional[Set[str]] = None,
    dataset_label: str = "paper_matching",
) -> pd.DataFrame:
    """Convert wide matching.csv with matched_control_1..3 to long pair rows."""
    treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)
    if treatment_col is None:
        raise ValueError(
            f"Could not find treatment repo column in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    matched_cols = [
        col for col in df.columns
        if col.startswith("matched_control_") or col.startswith("control_")
    ]

    if not matched_cols:
        # It may already be long format.
        control_col = find_col(df, CONTROL_COL_CANDIDATES)
        if control_col is None:
            raise ValueError(
                f"Could not find matched control columns. "
                f"Available columns: {list(df.columns)}"
            )

        out = df[[treatment_col, control_col]].copy()
        out.columns = ["treatment_repo", "control_repo"]
        out["control_rank"] = pd.NA
        out["stage"] = dataset_label
    else:
        rows = []
        for _, row in df.iterrows():
            treatment_repo = str(row[treatment_col]).strip()
            if not treatment_repo or treatment_repo == "nan":
                continue
            if treatment_filter is not None and treatment_repo not in treatment_filter:
                continue

            for rank, col in enumerate(sorted(matched_cols), start=1):
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
                        "stage": dataset_label,
                    }
                )
        out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(
            columns=["stage", "treatment_repo", "control_repo", "control_rank"]
        )

    out["treatment_repo"] = normalize_repo_series(out["treatment_repo"])
    out["control_repo"] = normalize_repo_series(out["control_repo"])
    out["stage"] = dataset_label

    return out[["stage", "treatment_repo", "control_repo", "control_rank"]]


def pair_file_to_long(path: str | Path, dataset_label: str) -> pd.DataFrame:
    df = read_csv_required(path)

    treatment_col = find_col(df, ["treatment_repo", "repo_name", "repo"])
    control_col = find_col(df, ["control_repo", "matched_control", "matched_repo"])

    if treatment_col is None or control_col is None:
        raise ValueError(
            f"Could not find treatment/control columns in {path}. "
            f"Available columns: {list(df.columns)}"
        )

    out = df[[treatment_col, control_col]].copy()
    out.columns = ["treatment_repo", "control_repo"]

    rank_col = find_col(df, ["control_rank", "match_rank", "rank"])
    if rank_col is not None:
        out["control_rank"] = df[rank_col]
    else:
        out["control_rank"] = pd.NA

    out["treatment_repo"] = normalize_repo_series(out["treatment_repo"])
    out["control_repo"] = normalize_repo_series(out["control_repo"])
    out["stage"] = dataset_label

    out = out.dropna(subset=["treatment_repo", "control_repo"])
    out = out[
        (out["treatment_repo"] != "")
        & (out["control_repo"] != "")
        & (out["treatment_repo"] != "nan")
        & (out["control_repo"] != "nan")
    ]

    return out[["stage", "treatment_repo", "control_repo", "control_rank"]]


def summarize_pairs(pairs: pd.DataFrame, dataset_label: str) -> Dict[str, object]:
    if pairs.empty:
        return {
            "dataset": dataset_label,
            "pair_rows": 0,
            "treatment_repos": 0,
            "unique_control_repos": 0,
            "treatments_with_1_control": 0,
            "treatments_with_2_controls": 0,
            "treatments_with_3_controls": 0,
            "treatments_with_other_control_count": 0,
            "max_controls_per_treatment": 0,
            "mean_controls_per_treatment": 0,
            "max_treatments_per_control": 0,
            "mean_treatments_per_control": 0,
        }

    controls_per_treatment = (
        pairs.groupby("treatment_repo")["control_repo"].nunique()
    )
    treatments_per_control = (
        pairs.groupby("control_repo")["treatment_repo"].nunique()
    )

    return {
        "dataset": dataset_label,
        "pair_rows": int(len(pairs)),
        "treatment_repos": int(pairs["treatment_repo"].nunique()),
        "unique_control_repos": int(pairs["control_repo"].nunique()),
        "treatments_with_1_control": int((controls_per_treatment == 1).sum()),
        "treatments_with_2_controls": int((controls_per_treatment == 2).sum()),
        "treatments_with_3_controls": int((controls_per_treatment == 3).sum()),
        "treatments_with_other_control_count": int(
            (~controls_per_treatment.isin([1, 2, 3])).sum()
        ),
        "max_controls_per_treatment": int(controls_per_treatment.max()),
        "mean_controls_per_treatment": float(controls_per_treatment.mean()),
        "max_treatments_per_control": int(treatments_per_control.max()),
        "mean_treatments_per_control": float(treatments_per_control.mean()),
    }


def infer_treatment_mask(panel: pd.DataFrame) -> pd.Series:
    if "dataset_source" in panel.columns:
        return panel["dataset_source"].astype(str).str.lower().eq("treatment")

    if "is_treatment" in panel.columns:
        return panel["is_treatment"].fillna(0).astype(int).eq(1)

    if "event" in panel.columns:
        return panel["event"].notna()

    raise ValueError(
        "Could not infer treatment/control rows. Need dataset_source, "
        "is_treatment, or event column."
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
            "dataset": dataset_label,
            "treatment_repos": 0,
            "control_repos": 0,
            "total_observations": 0,
            "post_treatment_observations": 0,
            "min_time": "",
            "max_time": "",
        }

    treat_mask = infer_treatment_mask(df)
    control_mask = ~treat_mask

    post_obs = 0
    if "post_event" in df.columns:
        post_obs = int(df.loc[treat_mask, "post_event"].fillna(0).astype(int).sum())

    time_col = find_col(df, ["time", "month", "week"])

    return {
        "dataset": dataset_label,
        "treatment_repos": int(df.loc[treat_mask, repo_col].nunique()),
        "control_repos": int(df.loc[control_mask, repo_col].nunique()),
        "total_observations": int(len(df)),
        "post_treatment_observations": post_obs,
        "min_time": str(df[time_col].min()) if time_col else "",
        "max_time": str(df[time_col].max()) if time_col else "",
    }


def get_panel_repo_sets(panel: pd.DataFrame) -> Tuple[Set[str], Set[str]]:
    repo_col = get_repo_col(panel)
    panel = panel.copy()
    panel[repo_col] = normalize_repo_series(panel[repo_col])
    treat_mask = infer_treatment_mask(panel)

    treatment_repos = set(panel.loc[treat_mask, repo_col])
    control_repos = set(panel.loc[~treat_mask, repo_col])

    return treatment_repos, control_repos


def make_strict_dropped_table(
    main_pairs: pd.DataFrame,
    strict_pairs: pd.DataFrame,
) -> pd.DataFrame:
    main_counts = (
        main_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="main_final_control_count")
    )

    main_controls = (
        main_pairs.groupby("treatment_repo")["control_repo"]
        .apply(lambda x: ";".join(sorted(set(x))))
        .reset_index(name="main_final_controls")
    )

    strict_treatments = set(strict_pairs["treatment_repo"].unique())

    dropped = main_counts[
        ~main_counts["treatment_repo"].isin(strict_treatments)
    ].copy()

    dropped = dropped.merge(main_controls, on="treatment_repo", how="left")
    dropped["drop_reason"] = (
        "not_in_strict_1to3; treatment does not have exactly "
        "3 final controls after clone/control filtering"
    )

    dropped = dropped.sort_values(
        ["main_final_control_count", "treatment_repo"],
        ascending=[True, True],
    )

    return dropped


def make_repo_set_differences(
    paper_panel: pd.DataFrame,
    main_panel: pd.DataFrame,
    strict_panel: pd.DataFrame,
    paper_jsts_repo_set: Optional[Set[str]],
) -> pd.DataFrame:
    paper_treat, paper_control = get_panel_repo_sets(paper_panel)
    main_treat, main_control = get_panel_repo_sets(main_panel)
    strict_treat, strict_control = get_panel_repo_sets(strict_panel)

    if paper_jsts_repo_set:
        paper_treat = paper_treat.intersection(paper_jsts_repo_set)

    rows = [
        {
            "comparison": "paper_treatment_minus_main_treatment",
            "count": len(paper_treat - main_treat),
            "repos": ";".join(sorted(paper_treat - main_treat)),
        },
        {
            "comparison": "main_treatment_minus_strict_treatment",
            "count": len(main_treat - strict_treat),
            "repos": ";".join(sorted(main_treat - strict_treat)),
        },
        {
            "comparison": "main_control_minus_strict_control",
            "count": len(main_control - strict_control),
            "repos": ";".join(sorted(main_control - strict_control)),
        },
        {
            "comparison": "strict_treatment_minus_main_treatment",
            "count": len(strict_treat - main_treat),
            "repos": ";".join(sorted(strict_treat - main_treat)),
        },
        {
            "comparison": "strict_control_minus_main_control",
            "count": len(strict_control - main_control),
            "repos": ";".join(sorted(strict_control - main_control)),
        },
    ]

    return pd.DataFrame(rows)


def write_report(
    out_path: Path,
    dataset_summary: pd.DataFrame,
    pair_summary: pd.DataFrame,
    dropped: pd.DataFrame,
) -> None:
    paper = dataset_summary[dataset_summary["dataset"] == "paper_appendix_jsts_table7"]
    main = dataset_summary[dataset_summary["dataset"] == "our_main_unbalanced_panel"]
    strict = dataset_summary[dataset_summary["dataset"] == "our_strict_1to3_unbalanced_panel"]

    def get_value(df: pd.DataFrame, col: str) -> object:
        if df.empty or col not in df.columns:
            return ""
        return df.iloc[0][col]

    lines = []
    lines.append("# JS/TS Paper vs Our main/strict Dataset Comparison")
    lines.append("")
    lines.append("## Main conclusion")
    lines.append("")
    lines.append(
        "The main_unbalanced panel is closer to the paper Appendix JS/TS dataset "
        "in sample size, while the strict_1to3_unbalanced panel is closer to the "
        "paper's stated 1:3 matching organization."
    )
    lines.append("")
    lines.append("## Dataset size comparison")
    lines.append("")
    lines.append(dataset_summary.to_markdown(index=False))
    lines.append("")
    lines.append("## Pair-stage comparison")
    lines.append("")
    lines.append(pair_summary.to_markdown(index=False))
    lines.append("")
    lines.append("## Strict 1:3 attrition")
    lines.append("")
    lines.append(
        f"Number of treatment repos kept in main pairs but dropped from strict pairs: "
        f"{len(dropped)}"
    )
    lines.append("")
    if not dropped.empty:
        count_table = (
            dropped["main_final_control_count"]
            .value_counts()
            .sort_index()
            .rename_axis("main_final_control_count")
            .reset_index(name="dropped_treatment_repos")
        )
        lines.append(count_table.to_markdown(index=False))
        lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "The strict_1to3_unbalanced panel becomes smaller because it keeps only "
        "treated repositories that still have exactly three final controls after "
        "clone usability and control contamination filtering. Treatments that lose "
        "one or more controls remain in main_unbalanced but are removed from "
        "strict_1to3_unbalanced."
    )
    lines.append("")
    lines.append("## Key numbers")
    lines.append("")
    lines.append(
        f"- Paper Appendix JS/TS: treatment={get_value(paper, 'treatment_repos')}, "
        f"control={get_value(paper, 'control_repos')}, "
        f"observations={get_value(paper, 'total_observations')}, "
        f"post={get_value(paper, 'post_treatment_observations')}"
    )
    lines.append(
        f"- Our main_unbalanced: treatment={get_value(main, 'treatment_repos')}, "
        f"control={get_value(main, 'control_repos')}, "
        f"observations={get_value(main, 'total_observations')}, "
        f"post={get_value(main, 'post_treatment_observations')}"
    )
    lines.append(
        f"- Our strict_1to3_unbalanced: treatment={get_value(strict, 'treatment_repos')}, "
        f"control={get_value(strict, 'control_repos')}, "
        f"observations={get_value(strict, 'total_observations')}, "
        f"post={get_value(strict, 'post_treatment_observations')}"
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_repos = read_csv_required(args.paper_repos)
    paper_matching = read_csv_required(args.paper_matching)
    paper_panel = read_csv_required(args.paper_panel)

    our_treatment_sample = read_csv_optional(args.our_treatment_sample)
    main_pairs = pair_file_to_long(args.our_main_pairs, "our_main_final_clean_pairs")
    strict_pairs = pair_file_to_long(args.our_strict_pairs, "our_strict_1to3_pairs")
    main_panel = read_csv_required(args.our_main_panel)
    strict_panel = read_csv_required(args.our_strict_panel)

    # Paper JS/TS treatment set from repos metadata.
    paper_jsts_treatments = get_jsts_repos_from_metadata(paper_repos)

    # If our JS/TS treatment sample exists, use it to slice paper matching for
    # a direct comparison with the exact treatment set used in our pipeline.
    our_jsts_treatments: Set[str] = set()
    if our_treatment_sample is not None:
        sample_repo_col = get_repo_col(our_treatment_sample)
        our_jsts_treatments = set(
            normalize_repo_series(our_treatment_sample[sample_repo_col])
        )

    paper_matching_for_paper_jsts = matching_wide_to_long(
        paper_matching,
        treatment_filter=paper_jsts_treatments if paper_jsts_treatments else None,
        dataset_label="paper_matching_jsts_from_repos",
    )

    paper_matching_for_our_jsts = matching_wide_to_long(
        paper_matching,
        treatment_filter=our_jsts_treatments if our_jsts_treatments else None,
        dataset_label="paper_matching_for_our_jsts_sample",
    )

    pair_summary = pd.DataFrame(
        [
            summarize_pairs(
                paper_matching_for_paper_jsts,
                "paper_matching_jsts_from_repos",
            ),
            summarize_pairs(
                paper_matching_for_our_jsts,
                "paper_matching_for_our_jsts_sample",
            ),
            summarize_pairs(main_pairs, "our_main_final_clean_pairs"),
            summarize_pairs(strict_pairs, "our_strict_1to3_pairs"),
        ]
    )

    # Paper Table 7 target row.
    dataset_rows: List[Dict[str, object]] = [PAPER_APPENDIX_JSTS.copy()]

    # Try to reproduce paper JS/TS from baseline panel. If language metadata exists,
    # restrict to JS/TS repo set. If not, still summarize the full paper panel with
    # a clear dataset label.
    if paper_jsts_treatments:
        dataset_rows.append(
            summarize_panel(
                paper_panel,
                "paper_baseline_panel_recomputed_jsts_treatment_repos_only",
                restrict_repos=paper_jsts_treatments,
            )
        )
    else:
        dataset_rows.append(
            summarize_panel(
                paper_panel,
                "paper_baseline_panel_full_no_language_filter_available",
                restrict_repos=None,
            )
        )

    dataset_rows.append(
        summarize_panel(main_panel, "our_main_unbalanced_panel", restrict_repos=None)
    )
    dataset_rows.append(
        summarize_panel(
            strict_panel,
            "our_strict_1to3_unbalanced_panel",
            restrict_repos=None,
        )
    )

    dataset_summary = pd.DataFrame(dataset_rows)

    dropped = make_strict_dropped_table(main_pairs, strict_pairs)

    repo_diffs = make_repo_set_differences(
        paper_panel=paper_panel,
        main_panel=main_panel,
        strict_panel=strict_panel,
        paper_jsts_repo_set=paper_jsts_treatments if paper_jsts_treatments else None,
    )

    dataset_summary.to_csv(
        out_dir / "jsts_dataset_size_comparison.csv",
        index=False,
    )
    pair_summary.to_csv(
        out_dir / "jsts_pair_stage_comparison.csv",
        index=False,
    )
    dropped.to_csv(
        out_dir / "jsts_strict_dropped_treatments.csv",
        index=False,
    )
    repo_diffs.to_csv(
        out_dir / "jsts_repo_set_differences.csv",
        index=False,
    )

    write_report(
        out_path=out_dir / "jsts_compare_report.md",
        dataset_summary=dataset_summary,
        pair_summary=pair_summary,
        dropped=dropped,
    )

    print("Comparison completed.")
    print(f"Output directory: {out_dir}")
    print("")
    print("Generated files:")
    for path in [
        out_dir / "jsts_dataset_size_comparison.csv",
        out_dir / "jsts_pair_stage_comparison.csv",
        out_dir / "jsts_strict_dropped_treatments.csv",
        out_dir / "jsts_repo_set_differences.csv",
        out_dir / "jsts_compare_report.md",
    ]:
        print(f"  - {path}")


if __name__ == "__main__":
    main()