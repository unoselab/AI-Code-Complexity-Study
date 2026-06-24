#!/usr/bin/env python3
"""
Count repositories by primary language group and summarize event-window coverage.

This script:
1. Reads panel_event_monthly.csv.
2. Extracts unique repositories from a dataset source, usually treatment.
3. Joins repository metadata from repos.csv.
4. Saves the selected language or language-group subset.
5. Computes pre/post event-window coverage from panel_event_monthly.csv.
6. Saves the selected language-group subset with balanced_window >= K.

Examples:
  Single language:
    python proc_scripts/count_repo_lang.py \
      --data-dir data_baseline_backup \
      --dataset-source treatment \
      --language TypeScript \
      --output-file tmp_typescript_test/data/original_paper_treatment_typescript_repos.csv \
      --window-output-file tmp_typescript_test/data/original_paper_treatment_typescript_repos_bw6.csv

  Multiple languages:
    python proc_scripts/count_repo_lang.py \
      --data-dir data_baseline_backup \
      --dataset-source treatment \
      --languages TypeScript JavaScript \
      --group-name JavaScript_TypeScript \
      --output-file tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv \
      --window-output-file tmp_jsts_test/data/original_paper_treatment_jsts_repos_bw6.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_META_COLUMNS = [
    "repo_name",
    "repo_primary_language",
    "repo_stars",
    "repo_commits",
    "repo_contributors",
    "repo_size",
    "repo_languages",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count repositories by language group and summarize balanced event-window coverage."
    )

    parser.add_argument(
        "--data-dir",
        default="data_baseline_backup",
        help="Directory containing panel_event_monthly.csv and repos.csv.",
    )
    parser.add_argument(
        "--panel-file",
        default=None,
        help="Optional explicit path to panel_event_monthly.csv.",
    )
    parser.add_argument(
        "--repos-file",
        default=None,
        help="Optional explicit path to repos.csv.",
    )
    parser.add_argument(
        "--dataset-source",
        default="treatment",
        help='Dataset source to count, usually "treatment" or "control".',
    )
    parser.add_argument(
        "--language",
        default=None,
        help='Single primary language to export, e.g., "TypeScript".',
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help='One or more primary languages to export, e.g., "TypeScript JavaScript".',
    )
    parser.add_argument(
        "--group-name",
        default=None,
        help='Readable group name for reporting, e.g., "JavaScript_TypeScript".',
    )
    parser.add_argument(
        "--language-column",
        default="repo_primary_language",
        help="Column used for language filtering.",
    )
    parser.add_argument(
        "--output-file",
        default="tmp_typescript_test/data/original_paper_treatment_typescript_repos.csv",
        help="Output CSV for the selected language subset.",
    )
    parser.add_argument(
        "--window-output-file",
        default="tmp_typescript_test/data/original_paper_treatment_typescript_repos_bw6.csv",
        help="Output CSV for selected language subset with sufficient balanced_window.",
    )
    parser.add_argument(
        "--min-balanced-window",
        type=int,
        default=6,
        help="Minimum balanced_window threshold for the strict output file.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=30,
        help="Number of selected rows to print.",
    )

    return parser.parse_args()


def resolve_language_group(args: argparse.Namespace) -> tuple[list[str], str]:
    if args.languages:
        languages = args.languages
    elif args.language:
        languages = [args.language]
    else:
        languages = ["TypeScript"]

    languages = [str(x).strip() for x in languages if str(x).strip()]
    if not languages:
        raise SystemExit("ERROR: no valid language was provided.")

    if args.group_name:
        group_name = args.group_name
    else:
        group_name = "_".join(languages)

    return languages, group_name


def read_csv_checked(path: Path, required_columns: list[str], label: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} file not found: {path}")

    df = pd.read_csv(path, dtype=str, low_memory=False)

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: {label} file is missing required columns: {missing}")

    return df


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    data_dir = Path(args.data_dir)

    panel_path = Path(args.panel_file) if args.panel_file else data_dir / "panel_event_monthly.csv"
    repos_path = Path(args.repos_file) if args.repos_file else data_dir / "repos.csv"

    return panel_path, repos_path


def clean_repo_name(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def clean_month(series: pd.Series) -> pd.Series:
    out = series.astype(str).str.strip().str[:7]
    return out.mask(out.str.lower().isin(["", "nan", "nat", "none"]))


def extract_unique_repos(panel: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    source = dataset_source.lower()

    panel = panel.copy()
    panel["dataset_source_norm"] = panel["dataset_source"].astype(str).str.lower()
    panel["repo_name"] = clean_repo_name(panel["repo_name"])

    selected = (
        panel[panel["dataset_source_norm"].eq(source)]
        [["repo_name"]]
        .drop_duplicates()
        .copy()
    )

    return selected


def get_repo_metadata(repos: pd.DataFrame) -> pd.DataFrame:
    keep_cols = [col for col in DEFAULT_META_COLUMNS if col in repos.columns]

    if "repo_name" not in keep_cols:
        raise SystemExit("ERROR: repos metadata does not contain repo_name.")

    meta = repos[keep_cols].copy()
    meta["repo_name"] = clean_repo_name(meta["repo_name"])
    meta = meta.drop_duplicates("repo_name")

    return meta


def join_repo_metadata(selected: pd.DataFrame, repos: pd.DataFrame) -> pd.DataFrame:
    meta = get_repo_metadata(repos)
    return selected.merge(meta, on="repo_name", how="left")


def filter_language_group(
    df: pd.DataFrame,
    language_column: str,
    languages: list[str],
) -> pd.DataFrame:
    if language_column not in df.columns:
        raise SystemExit(f"ERROR: language column not found: {language_column}")

    return df[df[language_column].isin(languages)].copy()


def summarize_event_windows(panel: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    required = ["repo_name", "dataset_source", "time", "event", "time_to_event"]
    missing = [col for col in required if col not in panel.columns]
    if missing:
        raise SystemExit(f"ERROR: panel file is missing required event-window columns: {missing}")

    source = dataset_source.lower()

    p = panel[panel["dataset_source"].astype(str).str.lower().eq(source)].copy()

    p["repo_name"] = clean_repo_name(p["repo_name"])
    p["time"] = clean_month(p["time"])
    p["event"] = clean_month(p["event"])
    p["time_to_event_num"] = pd.to_numeric(p["time_to_event"], errors="coerce")

    p = p.dropna(subset=["repo_name", "time", "time_to_event_num"])
    p["time_to_event_num"] = p["time_to_event_num"].astype(int)

    before = len(p)
    p = p.sort_values(["repo_name", "time"]).drop_duplicates(
        ["repo_name", "time"],
        keep="first",
    )
    duplicated_repo_month_rows = before - len(p)

    summary = (
        p.groupby("repo_name")
        .agg(
            event_month=("event", "first"),
            panel_first_month=("time", "min"),
            panel_latest_month=("time", "max"),
            panel_month_count=("time", "nunique"),
            min_relative_month=("time_to_event_num", "min"),
            max_relative_month=("time_to_event_num", "max"),
            pre_panel_months=("time_to_event_num", lambda x: int((x < 0).sum())),
            event_months=("time_to_event_num", lambda x: int((x == 0).sum())),
            post_panel_months=("time_to_event_num", lambda x: int((x > 0).sum())),
        )
        .reset_index()
    )

    summary["balanced_window"] = summary[
        ["pre_panel_months", "post_panel_months"]
    ].min(axis=1)

    summary.attrs["duplicated_repo_month_rows"] = duplicated_repo_month_rows

    return summary


def save_csv(df: pd.DataFrame, output_file: str) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def print_language_report(
    panel: pd.DataFrame,
    repos: pd.DataFrame,
    selected: pd.DataFrame,
    selected_meta: pd.DataFrame,
    language_subset: pd.DataFrame,
    args: argparse.Namespace,
    panel_path: Path,
    repos_path: Path,
    languages: list[str],
    group_name: str,
) -> None:
    print("Panel file:", panel_path)
    print("Repos file:", repos_path)
    print("panel rows:", len(panel))
    print("repos rows:", len(repos))
    print()

    print("dataset_source counts:")
    print(panel["dataset_source"].value_counts(dropna=False).to_string())
    print()

    print(f"unique {args.dataset_source} repos from panel:", selected["repo_name"].nunique())
    print("repos after metadata join:", len(selected_meta))

    if args.language_column in selected_meta.columns:
        print("missing primary language:", selected_meta[args.language_column].isna().sum())
    print()

    print(f"Primary language counts among {args.dataset_source} repos:")
    print(selected_meta[args.language_column].fillna("(missing)").value_counts().head(30).to_string())
    print()

    print("Selected languages:", ", ".join(languages))
    print("Group name:", group_name)
    print(f"{group_name} {args.dataset_source} repos:", len(language_subset))
    print("Unique repos:", language_subset["repo_name"].nunique())
    print()

    print("Saved language subset:", args.output_file)
    print()

    print(f"Top {args.top_print} {group_name} repos:")
    cols = [
        "repo_name",
        "repo_primary_language",
        "repo_stars",
        "repo_commits",
        "repo_contributors",
        "repo_size",
    ]
    cols = [col for col in cols if col in language_subset.columns]

    if len(language_subset) == 0:
        print("(No matching rows.)")
    else:
        print(language_subset[cols].head(args.top_print).to_string(index=False))


def print_window_report(
    language_window: pd.DataFrame,
    strict_window: pd.DataFrame,
    args: argparse.Namespace,
    duplicated_repo_month_rows: int,
    group_name: str,
) -> None:
    print()
    print("============================================================")
    print("Event-window coverage among selected language-group repos")
    print("============================================================")
    print("Duplicated repo-month rows collapsed:", duplicated_repo_month_rows)
    print(f"All {group_name} {args.dataset_source} repos with window summary:", len(language_window))
    print("Unique repos:", language_window["repo_name"].nunique())
    print()

    print("Primary language counts in window-summary subset:")
    print(language_window[args.language_column].fillna("(missing)").value_counts().to_string())
    print()

    print("balanced_window counts:")
    print(language_window["balanced_window"].value_counts().sort_index().to_string())
    print()

    for k in [3, 4, 5, 6, 7, 8, 9]:
        n = int((language_window["balanced_window"] >= k).sum())
        print(f"balanced_window >= {k}: {n}")

    print()
    print(
        f"Good-window {group_name} repos, "
        f"balanced_window >= {args.min_balanced_window}: {len(strict_window)}"
    )
    print("Unique good-window repos:", strict_window["repo_name"].nunique())
    print()

    if len(strict_window) > 0 and "event_month" in strict_window.columns:
        print(f"Event month counts for balanced_window >= {args.min_balanced_window}:")
        print(strict_window["event_month"].value_counts().sort_index().to_string())
        print()

    print("Saved good-window subset:", args.window_output_file)
    print()

    cols = [
        "repo_name",
        "event_month",
        "pre_panel_months",
        "post_panel_months",
        "balanced_window",
        "repo_primary_language",
        "repo_stars",
        "repo_commits",
        "repo_contributors",
    ]
    cols = [col for col in cols if col in strict_window.columns]

    print(f"Top {args.top_print} good-window {group_name} repos:")
    if len(strict_window) == 0:
        print("(No matching rows.)")
    else:
        print(strict_window[cols].head(args.top_print).to_string(index=False))


def main() -> None:
    args = parse_args()
    languages, group_name = resolve_language_group(args)

    panel_path, repos_path = resolve_paths(args)

    panel = read_csv_checked(
        panel_path,
        required_columns=["repo_name", "dataset_source"],
        label="panel",
    )
    repos = read_csv_checked(
        repos_path,
        required_columns=["repo_name", args.language_column],
        label="repos",
    )

    selected = extract_unique_repos(panel, args.dataset_source)
    selected_meta = join_repo_metadata(selected, repos)

    language_subset = filter_language_group(
        df=selected_meta,
        language_column=args.language_column,
        languages=languages,
    )
    save_csv(language_subset, args.output_file)

    window_summary = summarize_event_windows(panel, args.dataset_source)
    duplicated_repo_month_rows = int(window_summary.attrs.get("duplicated_repo_month_rows", 0))

    meta = get_repo_metadata(repos)
    window_meta = window_summary.merge(meta, on="repo_name", how="left")

    language_window = filter_language_group(
        df=window_meta,
        language_column=args.language_column,
        languages=languages,
    )
    language_window = language_window.sort_values(["repo_name"]).reset_index(drop=True)

    strict_window = language_window[
        language_window["balanced_window"] >= args.min_balanced_window
    ].copy()
    strict_window = strict_window.sort_values(
        ["balanced_window", "repo_name"],
        ascending=[False, True],
    ).reset_index(drop=True)

    save_csv(strict_window, args.window_output_file)

    print_language_report(
        panel=panel,
        repos=repos,
        selected=selected,
        selected_meta=selected_meta,
        language_subset=language_subset,
        args=args,
        panel_path=panel_path,
        repos_path=repos_path,
        languages=languages,
        group_name=group_name,
    )

    print_window_report(
        language_window=language_window,
        strict_window=strict_window,
        args=args,
        duplicated_repo_month_rows=duplicated_repo_month_rows,
        group_name=group_name,
    )


if __name__ == "__main__":
    main()
