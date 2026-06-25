#!/usr/bin/env python3
"""
Create a usable matched-control sample after cloning control repositories.

This script:
1. Reads the clean control repository list.
2. Reads clone status output from run8b.
3. Reads treatment-control matched pair data.
4. Keeps only controls with usable clone status.
5. Removes pair rows whose control repository failed cloning.
6. Saves usable controls, failed controls, usable pairs, dropped pairs,
   treatment-level coverage, zero-control treatments, and a summary table.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_USABLE_STATUSES = ("cloned", "skipped_existing", "updated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create usable JS/TS matched control sample after clone filtering."
    )

    parser.add_argument("--clone-status-file", required=True)
    parser.add_argument("--pair-file", required=True)
    parser.add_argument("--control-repos-file", required=True)

    parser.add_argument("--usable-control-file", required=True)
    parser.add_argument("--failed-control-file", required=True)
    parser.add_argument("--usable-pair-file", required=True)
    parser.add_argument("--dropped-pair-file", required=True)
    parser.add_argument("--coverage-file", required=True)
    parser.add_argument("--zero-control-treatment-file", required=True)
    parser.add_argument("--summary-file", required=True)

    parser.add_argument(
        "--usable-statuses",
        default=",".join(DEFAULT_USABLE_STATUSES),
        help="Comma-separated clone statuses treated as usable.",
    )

    parser.add_argument(
        "--fail-if-zero-control",
        action="store_true",
        help="Exit with code 2 if any treatment repo loses all controls.",
    )

    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {label} missing columns: {sorted(missing)}")


def normalize_repo_name(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def read_csv(path: Path, label: str) -> pd.DataFrame:
    require_file(path, label)
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise SystemExit(f"ERROR: failed to read {label}: {path}\n{exc}") from exc


def prepare_clone_status(clone_df: pd.DataFrame) -> pd.DataFrame:
    require_columns(clone_df, ["repo_name", "status"], "clone status file")

    clone_df = clone_df.copy()
    clone_df["repo_name"] = normalize_repo_name(clone_df["repo_name"])
    clone_df["status"] = clone_df["status"].astype(str).str.strip()
    clone_df["status_norm"] = clone_df["status"].str.lower()

    # Keep the last record if a repository appears multiple times.
    clone_df = clone_df.drop_duplicates(subset=["repo_name"], keep="last")
    return clone_df


def prepare_control_repos(control_df: pd.DataFrame) -> pd.DataFrame:
    require_columns(control_df, ["repo_name"], "control repos file")

    control_df = control_df.copy()
    control_df["repo_name"] = normalize_repo_name(control_df["repo_name"])
    control_df = control_df[control_df["repo_name"].ne("")]
    control_df = control_df.drop_duplicates(subset=["repo_name"], keep="first")
    return control_df


def detect_pair_columns(pair_df: pd.DataFrame) -> tuple[str, str]:
    treatment_candidates = [
        "treatment_repo",
        "treated_repo",
        "treatment_repo_name",
        "repo_name",
    ]
    control_candidates = [
        "control_repo",
        "matched_control",
        "matched_control_repo",
        "control_repo_name",
    ]

    treatment_col = next((c for c in treatment_candidates if c in pair_df.columns), None)
    control_col = next((c for c in control_candidates if c in pair_df.columns), None)

    if treatment_col and control_col:
        return treatment_col, control_col

    wide_control_cols = [
        c for c in pair_df.columns
        if c.startswith("matched_control_")
    ]

    if treatment_col and wide_control_cols:
        # The caller will handle wide format separately.
        return treatment_col, "__wide_matched_controls__"

    raise SystemExit(
        "ERROR: could not detect treatment/control columns in pair file. "
        "Expected long format columns such as treatment_repo/control_repo, "
        "or wide format columns such as repo_name/matched_control_1."
    )


def prepare_pairs(pair_df: pd.DataFrame) -> pd.DataFrame:
    treatment_col, control_col = detect_pair_columns(pair_df)

    pair_df = pair_df.copy()

    if control_col == "__wide_matched_controls__":
        wide_control_cols = [
            c for c in pair_df.columns
            if c.startswith("matched_control_")
        ]
        id_cols = [c for c in pair_df.columns if c not in wide_control_cols]

        pair_df = pair_df.melt(
            id_vars=id_cols,
            value_vars=wide_control_cols,
            var_name="matched_control_slot",
            value_name="control_repo",
        )
        pair_df = pair_df.rename(columns={treatment_col: "treatment_repo"})
    else:
        pair_df = pair_df.rename(
            columns={
                treatment_col: "treatment_repo",
                control_col: "control_repo",
            }
        )

    pair_df["treatment_repo"] = normalize_repo_name(pair_df["treatment_repo"])
    pair_df["control_repo"] = normalize_repo_name(pair_df["control_repo"])

    pair_df = pair_df[
        pair_df["treatment_repo"].ne("")
        & pair_df["control_repo"].ne("")
        & pair_df["control_repo"].str.lower().ne("nan")
    ].copy()

    pair_df = pair_df.drop_duplicates(
        subset=["treatment_repo", "control_repo"],
        keep="first",
    )

    return pair_df


def create_outputs(
    clone_df: pd.DataFrame,
    controls_df: pd.DataFrame,
    pairs_df: pd.DataFrame,
    usable_statuses: set[str],
) -> dict[str, pd.DataFrame]:
    clone_cols = list(clone_df.columns)

    # Merge the intended control list with clone status.
    control_clone = controls_df.merge(
        clone_df,
        on="repo_name",
        how="left",
        suffixes=("", "_clone"),
    )

    control_clone["status_norm"] = control_clone["status_norm"].fillna(
        "missing_clone_status"
    )
    control_clone["status"] = control_clone["status"].fillna("missing_clone_status")

    usable_controls = control_clone[
        control_clone["status_norm"].isin(usable_statuses)
    ].copy()

    failed_controls = control_clone[
        ~control_clone["status_norm"].isin(usable_statuses)
    ].copy()

    usable_control_set = set(usable_controls["repo_name"])

    usable_pairs = pairs_df[pairs_df["control_repo"].isin(usable_control_set)].copy()
    dropped_pairs = pairs_df[~pairs_df["control_repo"].isin(usable_control_set)].copy()

    original_counts = (
        pairs_df.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_original_controls")
    )

    usable_counts = (
        usable_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_usable_controls")
    )

    coverage = original_counts.merge(usable_counts, on="treatment_repo", how="left")
    coverage["num_usable_controls"] = coverage["num_usable_controls"].fillna(0).astype(int)
    coverage["num_dropped_controls"] = (
        coverage["num_original_controls"] - coverage["num_usable_controls"]
    )

    coverage = coverage.sort_values(
        ["num_usable_controls", "num_dropped_controls", "treatment_repo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    zero_control_treatments = coverage[coverage["num_usable_controls"] == 0].copy()

    extra_clone_rows = clone_df[~clone_df["repo_name"].isin(set(controls_df["repo_name"]))]

    summary = pd.DataFrame(
        [
            {
                "metric": "clean_control_repos_before_clone_filter",
                "value": controls_df["repo_name"].nunique(),
            },
            {
                "metric": "clone_status_rows",
                "value": len(clone_df),
            },
            {
                "metric": "clone_status_unique_repos",
                "value": clone_df["repo_name"].nunique(),
            },
            {
                "metric": "extra_clone_status_repos_not_in_control_list",
                "value": extra_clone_rows["repo_name"].nunique(),
            },
            {
                "metric": "usable_control_repos",
                "value": usable_controls["repo_name"].nunique(),
            },
            {
                "metric": "failed_or_missing_control_repos",
                "value": failed_controls["repo_name"].nunique(),
            },
            {
                "metric": "matched_pair_rows_before_clone_filter",
                "value": len(pairs_df),
            },
            {
                "metric": "usable_matched_pair_rows",
                "value": len(usable_pairs),
            },
            {
                "metric": "dropped_pair_rows_due_to_failed_or_missing_clone",
                "value": len(dropped_pairs),
            },
            {
                "metric": "treatment_repos_before_clone_filter",
                "value": pairs_df["treatment_repo"].nunique(),
            },
            {
                "metric": "treatment_repos_with_usable_controls",
                "value": usable_pairs["treatment_repo"].nunique(),
            },
            {
                "metric": "treatment_repos_lost_all_controls",
                "value": len(zero_control_treatments),
            },
        ]
    )

    return {
        "usable_controls": usable_controls,
        "failed_controls": failed_controls,
        "usable_pairs": usable_pairs,
        "dropped_pairs": dropped_pairs,
        "coverage": coverage,
        "zero_control_treatments": zero_control_treatments,
        "summary": summary,
        "extra_clone_rows": extra_clone_rows,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], args: argparse.Namespace) -> None:
    path_map = {
        "usable_controls": Path(args.usable_control_file),
        "failed_controls": Path(args.failed_control_file),
        "usable_pairs": Path(args.usable_pair_file),
        "dropped_pairs": Path(args.dropped_pair_file),
        "coverage": Path(args.coverage_file),
        "zero_control_treatments": Path(args.zero_control_treatment_file),
        "summary": Path(args.summary_file),
    }

    for key, path in path_map.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        outputs[key].to_csv(path, index=False)


def print_report(outputs: dict[str, pd.DataFrame]) -> None:
    usable_controls = outputs["usable_controls"]
    failed_controls = outputs["failed_controls"]
    usable_pairs = outputs["usable_pairs"]
    dropped_pairs = outputs["dropped_pairs"]
    coverage = outputs["coverage"]
    zero_control_treatments = outputs["zero_control_treatments"]
    summary = outputs["summary"]
    extra_clone_rows = outputs["extra_clone_rows"]

    print("Summary:")
    print(summary.to_string(index=False))
    print()

    print("Control clone status counts after merging with intended control list:")
    print(
        pd.concat([usable_controls, failed_controls])["status"]
        .value_counts(dropna=False)
        .to_string()
    )
    print()

    print("Control-count distribution after clone filtering:")
    print(coverage["num_usable_controls"].value_counts().sort_index().to_string())
    print()

    if len(failed_controls) > 0:
        print("Failed or missing control repositories:")
        cols = ["repo_name", "status", "target_dir", "note"]
        cols = [c for c in cols if c in failed_controls.columns]
        print(failed_controls[cols].to_string(index=False))
        print()

    if len(zero_control_treatments) > 0:
        print("Treatment repositories that lost all controls:")
        print(zero_control_treatments.to_string(index=False))
        print()

    if len(extra_clone_rows) > 0:
        print("Extra clone-status rows not present in intended control list:")
        cols = ["repo_name", "status", "target_dir", "note"]
        cols = [c for c in cols if c in extra_clone_rows.columns]
        print(extra_clone_rows[cols].to_string(index=False))
        print()

    print("Usable matched pair rows:", len(usable_pairs))
    print("Dropped matched pair rows:", len(dropped_pairs))
    print("Usable control repos:", usable_controls["repo_name"].nunique())
    print("Failed or missing control repos:", failed_controls["repo_name"].nunique())


def main() -> int:
    args = parse_args()

    clone_status_path = Path(args.clone_status_file)
    pair_path = Path(args.pair_file)
    control_repos_path = Path(args.control_repos_file)

    usable_statuses = {
        status.strip().lower()
        for status in args.usable_statuses.split(",")
        if status.strip()
    }

    clone_df = prepare_clone_status(
        read_csv(clone_status_path, "clone status file")
    )
    controls_df = prepare_control_repos(
        read_csv(control_repos_path, "control repos file")
    )
    pairs_df = prepare_pairs(
        read_csv(pair_path, "matched pair file")
    )

    outputs = create_outputs(
        clone_df=clone_df,
        controls_df=controls_df,
        pairs_df=pairs_df,
        usable_statuses=usable_statuses,
    )

    save_outputs(outputs, args)
    print_report(outputs)

    zero_count = len(outputs["zero_control_treatments"])
    if args.fail_if_zero_control and zero_count > 0:
        print(f"ERROR: {zero_count} treatment repositories lost all controls.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
