#!/usr/bin/env python3
"""
Compare the paper Appendix JS/TS dataset with our main_unbalanced and
strict_1to3_unbalanced JS/TS replication datasets.

Key outputs use short column names plus companion dictionary CSV files.

Main questions:
1. How close are our main_unbalanced and strict_1to3_unbalanced datasets
   to the paper Appendix JS/TS dataset?
2. Which paper JS/TS treatment/control repositories are missing from
   strict_1to3_unbalanced?
3. Why are they missing, as far as the available files can explain?

Outputs:
- compare/output/jsts_dataset_size_comparison.csv
- compare/output/jsts_dataset_size_comparison_dictionary.csv
- compare/output/jsts_pair_stage_comparison.csv
- compare/output/jsts_pair_stage_comparison_dictionary.csv
- compare/output/jsts_repo_set_differences.csv
- compare/output/jsts_repo_set_differences_dictionary.csv
- compare/output/jsts_paper_minus_strict_treatment_reasons.csv
- compare/output/jsts_paper_minus_strict_treatment_reasons_dictionary.csv
- compare/output/jsts_paper_minus_strict_control_reasons.csv
- compare/output/jsts_paper_minus_strict_control_reasons_dictionary.csv
- compare/output/jsts_strict_dropped_treatments.csv
- compare/output/jsts_strict_dropped_treatments_dictionary.csv
- compare/output/jsts_compare_report.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd


PAPER_APPENDIX_JSTS = {
    "ds": "paper_table7_jsts",
    "treat": 411,
    "ctrl": 422,
    "obs": 8870,
    "post": 2279,
    "min_t": "",
    "max_t": "",
    "note": "Paper Appendix Table 7 JavaScript/TypeScript row.",
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

MATCHED_CONTROL_PREFIXES = (
    "matched_control_",
    "control_",
)

JS_TS_LANG_VALUES = {"javascript", "typescript"}


# ---------------------------------------------------------------------------
# Argument parsing and IO
# ---------------------------------------------------------------------------


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
        "--our-original-pairs",
        default="tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv",
        help="Our originally extracted JS/TS pair CSV before final filtering.",
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


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    names = set(df.columns)
    for col in candidates:
        if col in names:
            return col
    return None


def normalize_repo_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def normalize_repo_set(values: Iterable[object]) -> Set[str]:
    out = set()
    for value in values:
        if pd.isna(value):
            continue
        repo = str(value).strip()
        if repo and repo.lower() != "nan":
            out.add(repo)
    return out


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
    mask = lang.isin(JS_TS_LANG_VALUES) | lang.str.contains(
        "javascript|typescript", regex=True, na=False
    )

    return set(normalize_repo_series(df.loc[mask, repo_col]))


def list_to_cell(values: Iterable[str]) -> str:
    return ";".join(sorted(set(values)))


def set_diff_rows(comparisons: Sequence[Tuple[str, Set[str], Set[str]]]) -> pd.DataFrame:
    rows = []
    for cmp_name, left, right in comparisons:
        diff = left - right
        rows.append({"cmp": cmp_name, "n": len(diff), "repos": list_to_cell(diff)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Matching / pair helpers
# ---------------------------------------------------------------------------


def matching_wide_to_long(
    df: pd.DataFrame,
    treatment_filter: Optional[Set[str]] = None,
    stage: str = "paper_match",
) -> pd.DataFrame:
    """Convert wide matching.csv with matched_control_1..3 to long pair rows."""
    treatment_col = find_col(df, TREATMENT_COL_CANDIDATES)
    if treatment_col is None:
        raise ValueError(
            "Could not find treatment repo column in matching file. "
            f"Available columns: {list(df.columns)}"
        )

    matched_cols = [
        col for col in df.columns if col.startswith(MATCHED_CONTROL_PREFIXES)
    ]

    if not matched_cols:
        control_col = find_col(df, CONTROL_COL_CANDIDATES)
        if control_col is None:
            raise ValueError(
                "Could not find matched control columns. "
                f"Available columns: {list(df.columns)}"
            )
        out = df[[treatment_col, control_col]].copy()
        out.columns = ["treat_repo", "ctrl_repo"]
        out["rank"] = pd.NA
        out["stage"] = stage
    else:
        rows = []
        for _, row in df.iterrows():
            treat_repo = row.get(treatment_col)
            if pd.isna(treat_repo):
                continue
            treat_repo = str(treat_repo).strip()
            if not treat_repo or treat_repo.lower() == "nan":
                continue
            if treatment_filter is not None and treat_repo not in treatment_filter:
                continue

            for rank, col in enumerate(sorted(matched_cols), start=1):
                ctrl_repo = row.get(col)
                if pd.isna(ctrl_repo):
                    continue
                ctrl_repo = str(ctrl_repo).strip()
                if not ctrl_repo or ctrl_repo.lower() == "nan":
                    continue
                rows.append(
                    {
                        "stage": stage,
                        "treat_repo": treat_repo,
                        "ctrl_repo": ctrl_repo,
                        "rank": rank,
                    }
                )
        out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(columns=["stage", "treat_repo", "ctrl_repo", "rank"])

    out["treat_repo"] = normalize_repo_series(out["treat_repo"])
    out["ctrl_repo"] = normalize_repo_series(out["ctrl_repo"])
    out["stage"] = stage
    return out[["stage", "treat_repo", "ctrl_repo", "rank"]]


def pair_file_to_long(path: str | Path, stage: str) -> pd.DataFrame:
    df = read_csv_required(path)

    treatment_col = find_col(df, ["treatment_repo", "repo_name", "repo"])
    control_col = find_col(df, ["control_repo", "matched_control", "matched_repo"])

    if treatment_col is None or control_col is None:
        raise ValueError(
            f"Could not find treatment/control columns in {path}. "
            f"Available columns: {list(df.columns)}"
        )

    out = df[[treatment_col, control_col]].copy()
    out.columns = ["treat_repo", "ctrl_repo"]

    rank_col = find_col(df, ["control_rank", "match_rank", "rank"])
    out["rank"] = df[rank_col] if rank_col is not None else pd.NA

    out["treat_repo"] = normalize_repo_series(out["treat_repo"])
    out["ctrl_repo"] = normalize_repo_series(out["ctrl_repo"])
    out["stage"] = stage

    out = out.dropna(subset=["treat_repo", "ctrl_repo"])
    out = out[
        (out["treat_repo"] != "")
        & (out["ctrl_repo"] != "")
        & (out["treat_repo"].str.lower() != "nan")
        & (out["ctrl_repo"].str.lower() != "nan")
    ]

    return out[["stage", "treat_repo", "ctrl_repo", "rank"]]


def summarize_pairs(pairs: pd.DataFrame, stage: str) -> Dict[str, object]:
    if pairs.empty:
        return {
            "stage": stage,
            "pairs": 0,
            "treat": 0,
            "ctrl": 0,
            "t1": 0,
            "t2": 0,
            "t3": 0,
            "t_other": 0,
            "max_c": 0,
            "mean_c": 0.0,
            "max_reuse": 0,
            "mean_reuse": 0.0,
        }

    controls_per_treatment = pairs.groupby("treat_repo")["ctrl_repo"].nunique()
    treatments_per_control = pairs.groupby("ctrl_repo")["treat_repo"].nunique()

    return {
        "stage": stage,
        "pairs": int(len(pairs)),
        "treat": int(pairs["treat_repo"].nunique()),
        "ctrl": int(pairs["ctrl_repo"].nunique()),
        "t1": int((controls_per_treatment == 1).sum()),
        "t2": int((controls_per_treatment == 2).sum()),
        "t3": int((controls_per_treatment == 3).sum()),
        "t_other": int((~controls_per_treatment.isin([1, 2, 3])).sum()),
        "max_c": int(controls_per_treatment.max()),
        "mean_c": round(float(controls_per_treatment.mean()), 4),
        "max_reuse": int(treatments_per_control.max()),
        "mean_reuse": round(float(treatments_per_control.mean()), 4),
    }


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------


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
    ds: str,
    restrict_repos: Optional[Set[str]] = None,
    note: str = "",
) -> Dict[str, object]:
    repo_col = get_repo_col(panel)
    df = panel.copy()
    df[repo_col] = normalize_repo_series(df[repo_col])

    if restrict_repos is not None:
        df = df[df[repo_col].isin(restrict_repos)].copy()

    if df.empty:
        return {
            "ds": ds,
            "treat": 0,
            "ctrl": 0,
            "obs": 0,
            "post": 0,
            "min_t": "",
            "max_t": "",
            "note": note,
        }

    treat_mask = infer_treatment_mask(df)
    control_mask = ~treat_mask

    post_obs = 0
    if "post_event" in df.columns:
        post_obs = int(df.loc[treat_mask, "post_event"].fillna(0).astype(int).sum())

    time_col = find_col(df, ["time", "month", "week"])

    return {
        "ds": ds,
        "treat": int(df.loc[treat_mask, repo_col].nunique()),
        "ctrl": int(df.loc[control_mask, repo_col].nunique()),
        "obs": int(len(df)),
        "post": post_obs,
        "min_t": str(df[time_col].min()) if time_col else "",
        "max_t": str(df[time_col].max()) if time_col else "",
        "note": note,
    }


def get_panel_repo_sets(panel: pd.DataFrame) -> Tuple[Set[str], Set[str]]:
    repo_col = get_repo_col(panel)
    panel = panel.copy()
    panel[repo_col] = normalize_repo_series(panel[repo_col])
    treat_mask = infer_treatment_mask(panel)
    treatment_repos = set(panel.loc[treat_mask, repo_col])
    control_repos = set(panel.loc[~treat_mask, repo_col])
    return treatment_repos, control_repos


# ---------------------------------------------------------------------------
# Reasons and diagnostics
# ---------------------------------------------------------------------------


def make_strict_dropped_table(
    main_pairs: pd.DataFrame,
    strict_pairs: pd.DataFrame,
) -> pd.DataFrame:
    main_counts = (
        main_pairs.groupby("treat_repo")["ctrl_repo"]
        .nunique()
        .reset_index(name="n_ctrl_main")
    )
    main_controls = (
        main_pairs.groupby("treat_repo")["ctrl_repo"]
        .apply(lambda x: list_to_cell(x))
        .reset_index(name="ctrls_main")
    )
    strict_treatments = set(strict_pairs["treat_repo"].unique())

    dropped = main_counts[~main_counts["treat_repo"].isin(strict_treatments)].copy()
    dropped = dropped.merge(main_controls, on="treat_repo", how="left")
    dropped["reason"] = "final_controls_less_than_3"
    dropped["detail"] = (
        "Treatment appears in main final-clean pairs but does not have exactly "
        "3 final controls, so strict_1to3 drops it."
    )
    dropped = dropped.sort_values(["n_ctrl_main", "treat_repo"])
    return dropped


def classify_paper_minus_strict_treatments(
    paper_treatments: Set[str],
    strict_panel_treatments: Set[str],
    our_jsts_treatments: Set[str],
    paper_matching_for_our_jsts: pd.DataFrame,
    original_pairs: Optional[pd.DataFrame],
    main_pairs: pd.DataFrame,
    strict_pairs: pd.DataFrame,
    main_panel_treatments: Set[str],
) -> pd.DataFrame:
    missing = sorted(paper_treatments - strict_panel_treatments)

    paper_match_treat = set(paper_matching_for_our_jsts["treat_repo"].unique())
    orig_treat = set(original_pairs["treat_repo"].unique()) if original_pairs is not None else set()
    main_pair_treat = set(main_pairs["treat_repo"].unique())
    strict_pair_treat = set(strict_pairs["treat_repo"].unique())

    main_counts = main_pairs.groupby("treat_repo")["ctrl_repo"].nunique().to_dict()

    rows = []
    for repo in missing:
        if repo not in our_jsts_treatments:
            reason = "not_in_our_jsts_sample"
            detail = "Paper JS/TS treatment is absent from our JS/TS treatment sample."
        elif repo not in paper_match_treat:
            reason = "not_in_paper_matching_for_our_sample"
            detail = "Repo is in our JS/TS sample but no matching row was found for it."
        elif original_pairs is not None and repo not in orig_treat:
            reason = "not_in_original_extracted_pairs"
            detail = "Repo is absent from our originally extracted JS/TS pair file."
        elif repo not in main_pair_treat:
            reason = "not_in_main_final_pairs"
            detail = "Repo was removed before or during final-clean pair construction."
        elif repo in main_pair_treat and repo not in strict_pair_treat:
            n_ctrl = int(main_counts.get(repo, 0))
            reason = "dropped_by_strict_1to3"
            detail = f"Repo has {n_ctrl} final controls in main pairs, not exactly 3."
        elif repo in strict_pair_treat and repo not in strict_panel_treatments:
            reason = "in_strict_pairs_no_panel_rows"
            detail = "Repo is in strict pairs but has no usable strict panel rows."
        elif repo in main_panel_treatments and repo not in strict_panel_treatments:
            reason = "in_main_panel_not_strict_panel"
            detail = "Repo appears in main panel but not strict panel."
        else:
            reason = "other_or_unclassified"
            detail = "Missing from strict panel for a reason not classified by available files."

        rows.append({"repo": repo, "type": "treat", "reason": reason, "detail": detail})

    return pd.DataFrame(rows)


def classify_paper_minus_strict_controls(
    paper_controls: Set[str],
    strict_panel_controls: Set[str],
    paper_matching_for_our_jsts: pd.DataFrame,
    original_pairs: Optional[pd.DataFrame],
    main_pairs: pd.DataFrame,
    strict_pairs: pd.DataFrame,
    main_panel_controls: Set[str],
) -> pd.DataFrame:
    missing = sorted(paper_controls - strict_panel_controls)

    paper_match_ctrl = set(paper_matching_for_our_jsts["ctrl_repo"].unique())
    orig_ctrl = set(original_pairs["ctrl_repo"].unique()) if original_pairs is not None else set()
    main_pair_ctrl = set(main_pairs["ctrl_repo"].unique())
    strict_pair_ctrl = set(strict_pairs["ctrl_repo"].unique())

    # Which treatments were connected to this control at each stage?
    paper_ctrl_to_treats = (
        paper_matching_for_our_jsts.groupby("ctrl_repo")["treat_repo"]
        .apply(lambda x: list_to_cell(x))
        .to_dict()
        if not paper_matching_for_our_jsts.empty
        else {}
    )
    main_ctrl_to_treats = (
        main_pairs.groupby("ctrl_repo")["treat_repo"]
        .apply(lambda x: list_to_cell(x))
        .to_dict()
        if not main_pairs.empty
        else {}
    )

    rows = []
    for repo in missing:
        if repo not in paper_match_ctrl:
            reason = "not_in_paper_matching_for_our_sample"
            detail = "Control is not matched to our JS/TS treatment sample in paper matching."
        elif original_pairs is not None and repo not in orig_ctrl:
            reason = "not_in_original_extracted_pairs"
            detail = "Control is absent from our originally extracted JS/TS pair file."
        elif repo not in main_pair_ctrl:
            reason = "removed_before_final_clean"
            detail = (
                "Control was removed before final-clean pairs, likely due to clone "
                "unavailability, overlap filtering, or local Cursor-evidence filtering."
            )
        elif repo in main_pair_ctrl and repo not in strict_pair_ctrl:
            reason = "linked_only_to_strict_dropped_treatments"
            detail = "Control appears in main pairs but is not linked to any treatment kept by strict_1to3."
        elif repo in strict_pair_ctrl and repo not in strict_panel_controls:
            reason = "in_strict_pairs_no_panel_rows"
            detail = "Control is in strict pairs but has no usable strict panel rows."
        elif repo in main_panel_controls and repo not in strict_panel_controls:
            reason = "in_main_panel_not_strict_panel"
            detail = "Control appears in main panel but not strict panel."
        else:
            reason = "other_or_unclassified"
            detail = "Missing from strict panel for a reason not classified by available files."

        rows.append(
            {
                "repo": repo,
                "type": "ctrl",
                "reason": reason,
                "paper_treats": paper_ctrl_to_treats.get(repo, ""),
                "main_treats": main_ctrl_to_treats.get(repo, ""),
                "detail": detail,
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data dictionaries and report
# ---------------------------------------------------------------------------


def dictionary_dataset_size() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"col": "ds", "meaning": "Dataset/stage label."},
            {"col": "treat", "meaning": "Number of treatment repositories."},
            {"col": "ctrl", "meaning": "Number of control repositories."},
            {"col": "obs", "meaning": "Total panel observations/rows."},
            {"col": "post", "meaning": "Treatment-group post-treatment observations."},
            {"col": "min_t", "meaning": "First time period in the panel, if available."},
            {"col": "max_t", "meaning": "Last time period in the panel, if available."},
            {"col": "note", "meaning": "Short explanation of the dataset row."},
        ]
    )


def dictionary_pair_stage() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"col": "stage", "meaning": "Pair-file or matching stage label."},
            {"col": "pairs", "meaning": "Number of treatment-control pair rows."},
            {"col": "treat", "meaning": "Number of treatment repositories."},
            {"col": "ctrl", "meaning": "Number of unique control repositories."},
            {"col": "t1", "meaning": "Treatments with exactly 1 unique control."},
            {"col": "t2", "meaning": "Treatments with exactly 2 unique controls."},
            {"col": "t3", "meaning": "Treatments with exactly 3 unique controls."},
            {"col": "t_other", "meaning": "Treatments with a control count other than 1, 2, or 3."},
            {"col": "max_c", "meaning": "Maximum controls per treatment."},
            {"col": "mean_c", "meaning": "Mean controls per treatment."},
            {"col": "max_reuse", "meaning": "Maximum number of treatments sharing one control."},
            {"col": "mean_reuse", "meaning": "Mean number of treatments per control."},
        ]
    )


def dictionary_repo_set_diff() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"col": "cmp", "meaning": "Set-difference comparison name."},
            {"col": "n", "meaning": "Number of repositories in the set difference."},
            {"col": "repos", "meaning": "Semicolon-separated repository names."},
            {"label": "paper_treat_minus_strict_treat", "meaning": "Paper JS/TS treatment repos not in strict treatment repos."},
            {"label": "paper_ctrl_minus_strict_ctrl", "meaning": "Paper JS/TS matched controls not in strict controls."},
            {"label": "main_treat_minus_strict_treat", "meaning": "Main treatment repos not in strict treatment repos."},
            {"label": "main_ctrl_minus_strict_ctrl", "meaning": "Main control repos not in strict control repos."},
        ]
    )


def dictionary_reasons() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"col": "repo", "meaning": "Repository full name."},
            {"col": "type", "meaning": "Repository role: treat or ctrl."},
            {"col": "reason", "meaning": "Short reason category."},
            {"col": "paper_treats", "meaning": "For controls: paper treatments matched to this control."},
            {"col": "main_treats", "meaning": "For controls: main-pair treatments linked to this control."},
            {"col": "detail", "meaning": "Human-readable explanation."},
        ]
    )


def dictionary_strict_dropped() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"col": "treat_repo", "meaning": "Treatment repository dropped from strict pairs."},
            {"col": "n_ctrl_main", "meaning": "Number of final controls in main final-clean pairs."},
            {"col": "ctrls_main", "meaning": "Controls linked to this treatment in main final-clean pairs."},
            {"col": "reason", "meaning": "Reason category for dropping from strict."},
            {"col": "detail", "meaning": "Human-readable explanation."},
        ]
    )


def write_report(
    out_path: Path,
    dataset_summary: pd.DataFrame,
    pair_summary: pd.DataFrame,
    repo_diffs: pd.DataFrame,
    treat_reasons: pd.DataFrame,
    ctrl_reasons: pd.DataFrame,
    dropped: pd.DataFrame,
) -> None:
    lines: List[str] = []
    lines.append("# JS/TS Paper vs Our Strict 1:3 Dataset Comparison")
    lines.append("")
    lines.append("## Main conclusion")
    lines.append("")
    lines.append(
        "The strict_1to3_unbalanced panel is closer to the paper's stated "
        "1:3 matching organization, while main_unbalanced is usually closer "
        "to the paper Appendix JS/TS sample size."
    )
    lines.append("")
    lines.append(
        "This report focuses on paper_treat_minus_strict_treat and "
        "paper_ctrl_minus_strict_ctrl because strict_1to3_unbalanced is the "
        "comparison dataset most aligned with the paper's matching rule."
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

    lines.append("## Key set differences")
    lines.append("")
    lines.append(repo_diffs.to_markdown(index=False))
    lines.append("")

    def reason_counts(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["reason", "n"])
        return df["reason"].value_counts().rename_axis("reason").reset_index(name="n")

    lines.append("## Paper treatment repos missing from strict")
    lines.append("")
    lines.append(reason_counts(treat_reasons).to_markdown(index=False))
    lines.append("")

    lines.append("## Paper control repos missing from strict")
    lines.append("")
    lines.append(reason_counts(ctrl_reasons).to_markdown(index=False))
    lines.append("")

    lines.append("## Main-to-strict attrition")
    lines.append("")
    lines.append(
        f"Treatment repos kept in main pairs but dropped from strict pairs: {len(dropped)}"
    )
    lines.append("")
    if not dropped.empty:
        count_table = (
            dropped["n_ctrl_main"]
            .value_counts()
            .sort_index()
            .rename_axis("n_ctrl_main")
            .reset_index(name="dropped_treat")
        )
        lines.append(count_table.to_markdown(index=False))
        lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "A repository can be absent from strict_1to3_unbalanced for several reasons: "
        "it may not be in our JS/TS sample, it may not survive pair extraction, "
        "its matched controls may have been removed before final-clean pairs, "
        "or it may have fewer than exactly three final controls and therefore be "
        "dropped by the strict 1:3 rule."
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_repos = read_csv_required(args.paper_repos)
    paper_matching = read_csv_required(args.paper_matching)
    paper_panel = read_csv_required(args.paper_panel)

    our_treatment_sample = read_csv_optional(args.our_treatment_sample)
    original_pairs = None
    if Path(args.our_original_pairs).exists():
        original_pairs = pair_file_to_long(args.our_original_pairs, "our_orig_pairs")

    main_pairs = pair_file_to_long(args.our_main_pairs, "our_main_pairs")
    strict_pairs = pair_file_to_long(args.our_strict_pairs, "our_strict_pairs")
    main_panel = read_csv_required(args.our_main_panel)
    strict_panel = read_csv_required(args.our_strict_panel)

    paper_jsts_treatments = get_jsts_repos_from_metadata(paper_repos)

    our_jsts_treatments: Set[str] = set()
    if our_treatment_sample is not None:
        sample_repo_col = get_repo_col(our_treatment_sample)
        our_jsts_treatments = set(normalize_repo_series(our_treatment_sample[sample_repo_col]))

    paper_matching_jsts = matching_wide_to_long(
        paper_matching,
        treatment_filter=paper_jsts_treatments if paper_jsts_treatments else None,
        stage="paper_match_jsts",
    )

    paper_matching_for_our_jsts = matching_wide_to_long(
        paper_matching,
        treatment_filter=our_jsts_treatments if our_jsts_treatments else None,
        stage="paper_match_our_jsts",
    )

    # Paper JS/TS matched repo set reconstructed from matching.csv.
    paper_jsts_match_treat = set(paper_matching_jsts["treat_repo"].unique())
    paper_jsts_match_ctrl = set(paper_matching_jsts["ctrl_repo"].unique())
    paper_jsts_matched_repos = paper_jsts_match_treat | paper_jsts_match_ctrl

    # Panel repo sets.
    paper_panel_treat, paper_panel_ctrl = get_panel_repo_sets(paper_panel)
    main_panel_treat, main_panel_ctrl = get_panel_repo_sets(main_panel)
    strict_panel_treat, strict_panel_ctrl = get_panel_repo_sets(strict_panel)

    # Prefer paper matching-derived JS/TS control set for paper-vs-strict control comparison.
    paper_treat_for_diff = paper_jsts_match_treat if paper_jsts_match_treat else paper_jsts_treatments
    paper_ctrl_for_diff = paper_jsts_match_ctrl

    dataset_summary = pd.DataFrame(
        [
            PAPER_APPENDIX_JSTS.copy(),
            summarize_panel(
                paper_panel,
                "paper_jsts_matched_panel_recomputed",
                restrict_repos=paper_jsts_matched_repos if paper_jsts_matched_repos else None,
                note=(
                    "Recomputed from baseline panel using JS/TS treatments and their "
                    "matched controls from baseline matching.csv."
                ),
            ),
            summarize_panel(
                paper_panel,
                "paper_jsts_treatment_only_panel",
                restrict_repos=paper_jsts_treatments if paper_jsts_treatments else None,
                note=(
                    "Treatment-only baseline panel restricted to JS/TS treatment repos. "
                    "Not directly comparable to Table 7 because controls are excluded."
                ),
            ),
            summarize_panel(
                main_panel,
                "our_main_unbalanced",
                note="Our main unbalanced JS/TS panel.",
            ),
            summarize_panel(
                strict_panel,
                "our_strict_1to3_unbalanced",
                note="Our strict 1:3 unbalanced JS/TS panel.",
            ),
        ]
    )

    pair_rows = [
        summarize_pairs(paper_matching_jsts, "paper_match_jsts"),
        summarize_pairs(paper_matching_for_our_jsts, "paper_match_our_jsts"),
    ]
    if original_pairs is not None:
        pair_rows.append(summarize_pairs(original_pairs, "our_orig_pairs"))
    pair_rows.extend(
        [
            summarize_pairs(main_pairs, "our_main_pairs"),
            summarize_pairs(strict_pairs, "our_strict_pairs"),
        ]
    )
    pair_summary = pd.DataFrame(pair_rows)

    repo_diffs = set_diff_rows(
        [
            ("paper_treat_minus_main_treat", paper_treat_for_diff, main_panel_treat),
            ("paper_ctrl_minus_main_ctrl", paper_ctrl_for_diff, main_panel_ctrl),
            ("paper_treat_minus_strict_treat", paper_treat_for_diff, strict_panel_treat),
            ("paper_ctrl_minus_strict_ctrl", paper_ctrl_for_diff, strict_panel_ctrl),
            ("main_treat_minus_strict_treat", main_panel_treat, strict_panel_treat),
            ("main_ctrl_minus_strict_ctrl", main_panel_ctrl, strict_panel_ctrl),
            ("strict_treat_minus_main_treat", strict_panel_treat, main_panel_treat),
            ("strict_ctrl_minus_main_ctrl", strict_panel_ctrl, main_panel_ctrl),
        ]
    )

    dropped = make_strict_dropped_table(main_pairs, strict_pairs)

    treat_reasons = classify_paper_minus_strict_treatments(
        paper_treatments=paper_treat_for_diff,
        strict_panel_treatments=strict_panel_treat,
        our_jsts_treatments=our_jsts_treatments,
        paper_matching_for_our_jsts=paper_matching_for_our_jsts,
        original_pairs=original_pairs,
        main_pairs=main_pairs,
        strict_pairs=strict_pairs,
        main_panel_treatments=main_panel_treat,
    )

    ctrl_reasons = classify_paper_minus_strict_controls(
        paper_controls=paper_ctrl_for_diff,
        strict_panel_controls=strict_panel_ctrl,
        paper_matching_for_our_jsts=paper_matching_for_our_jsts,
        original_pairs=original_pairs,
        main_pairs=main_pairs,
        strict_pairs=strict_pairs,
        main_panel_controls=main_panel_ctrl,
    )

    # Main outputs.
    write_csv(dataset_summary, out_dir / "jsts_dataset_size_comparison.csv")
    write_csv(pair_summary, out_dir / "jsts_pair_stage_comparison.csv")
    write_csv(repo_diffs, out_dir / "jsts_repo_set_differences.csv")
    write_csv(treat_reasons, out_dir / "jsts_paper_minus_strict_treatment_reasons.csv")
    write_csv(ctrl_reasons, out_dir / "jsts_paper_minus_strict_control_reasons.csv")
    write_csv(dropped, out_dir / "jsts_strict_dropped_treatments.csv")

    # Dictionaries.
    write_csv(dictionary_dataset_size(), out_dir / "jsts_dataset_size_comparison_dictionary.csv")
    write_csv(dictionary_pair_stage(), out_dir / "jsts_pair_stage_comparison_dictionary.csv")
    write_csv(dictionary_repo_set_diff(), out_dir / "jsts_repo_set_differences_dictionary.csv")
    write_csv(dictionary_reasons(), out_dir / "jsts_paper_minus_strict_treatment_reasons_dictionary.csv")
    write_csv(dictionary_reasons(), out_dir / "jsts_paper_minus_strict_control_reasons_dictionary.csv")
    write_csv(dictionary_strict_dropped(), out_dir / "jsts_strict_dropped_treatments_dictionary.csv")

    write_report(
        out_path=out_dir / "jsts_compare_report.md",
        dataset_summary=dataset_summary,
        pair_summary=pair_summary,
        repo_diffs=repo_diffs,
        treat_reasons=treat_reasons,
        ctrl_reasons=ctrl_reasons,
        dropped=dropped,
    )

    print("Comparison completed.")
    print(f"Output directory: {out_dir}")
    print("")
    print("Generated files:")
    for path in sorted(out_dir.glob("jsts_*")):
        print(f"  - {path}")


if __name__ == "__main__":
    main()
