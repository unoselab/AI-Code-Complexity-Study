#!/usr/bin/env python3
"""
Filter matched control repositories using local Cursor evidence detected by run8d.

This script:
1. Reads local Cursor adoption evidence from control git-history analysis.
2. Splits evidence into in-window and post-window evidence.
3. Removes controls with Cursor evidence within the analysis window.
4. Keeps controls with Cursor evidence only after the analysis window as diagnostics.
5. Recomputes treatment-control coverage.
6. Optionally filters control monthly time-series files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter controls with local Cursor evidence inside the analysis window."
    )

    parser.add_argument("--analysis-end", default="2025-08")

    parser.add_argument("--control-file", required=True)
    parser.add_argument("--pair-file", required=True)
    parser.add_argument("--adoption-file", required=True)

    parser.add_argument("--control-ts-repos-file", default=None)
    parser.add_argument("--control-ts-contributors-file", default=None)

    parser.add_argument("--in-window-evidence-file", required=True)
    parser.add_argument("--post-window-evidence-file", required=True)
    parser.add_argument("--final-control-file", required=True)
    parser.add_argument("--final-pair-file", required=True)
    parser.add_argument("--dropped-pair-file", required=True)
    parser.add_argument("--coverage-file", required=True)
    parser.add_argument("--zero-control-treatment-file", required=True)
    parser.add_argument("--summary-file", required=True)

    parser.add_argument(
        "--strict-1to3-pair-file",
        default=None,
        help="Optional output path for final-clean pairs that retain exactly three controls.",
    )
    parser.add_argument(
        "--strict-1to3-coverage-file",
        default=None,
        help="Optional output path for final-clean coverage rows that retain exactly three controls.",
    )

    parser.add_argument("--final-control-ts-repos-file", default=None)
    parser.add_argument("--final-control-ts-contributors-file", default=None)

    parser.add_argument(
        "--fail-if-zero-control",
        action="store_true",
        help="Exit with code 2 if any treatment repository loses all controls.",
    )

    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {label} missing columns: {sorted(missing)}")


def normalize_repo(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def read_adoption_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "repo_name",
                "adoption_month",
                "adoption_date",
                "evidence_paths",
                "confidence",
            ]
        )

    df = pd.read_csv(path)

    if df.empty:
        return df

    require_columns(df, {"repo_name", "adoption_month"}, "local Cursor adoption file")

    df = df.copy()
    df["repo_name"] = normalize_repo(df["repo_name"])
    df["adoption_month"] = df["adoption_month"].astype(str).str.strip()

    return df[df["repo_name"].ne("")].copy()


def build_coverage(pairs: pd.DataFrame, final_pairs: pd.DataFrame) -> pd.DataFrame:
    original_counts = (
        pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_controls_before_local_cursor_filter")
    )

    final_counts = (
        final_pairs.groupby("treatment_repo")["control_repo"]
        .nunique()
        .reset_index(name="num_final_controls")
    )

    coverage = original_counts.merge(final_counts, on="treatment_repo", how="left")
    coverage["num_final_controls"] = coverage["num_final_controls"].fillna(0).astype(int)
    coverage["num_dropped_controls_local_cursor"] = (
        coverage["num_controls_before_local_cursor_filter"]
        - coverage["num_final_controls"]
    )

    coverage = coverage.sort_values(
        ["num_final_controls", "num_dropped_controls_local_cursor", "treatment_repo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    return coverage


def maybe_filter_time_series(
    input_path_text: str | None,
    output_path_text: str | None,
    removed_controls: set[str],
    label: str,
) -> tuple[int, int]:
    if not input_path_text or not output_path_text:
        return 0, 0

    input_path = Path(input_path_text)
    output_path = Path(output_path_text)

    if not input_path.exists():
        print(f"WARNING: {label} input file not found: {input_path}")
        return 0, 0

    df = pd.read_csv(input_path)

    if "repo_name" not in df.columns:
        print(f"WARNING: {label} has no repo_name column: {input_path}")
        save_csv(df, output_path)
        return len(df), len(df)

    df["repo_name"] = normalize_repo(df["repo_name"])
    filtered = df[~df["repo_name"].isin(removed_controls)].copy()
    save_csv(filtered, output_path)

    return len(df), len(filtered)


def main() -> int:
    args = parse_args()

    control_path = Path(args.control_file)
    pair_path = Path(args.pair_file)
    adoption_path = Path(args.adoption_file)

    require_file(control_path, "control file")
    require_file(pair_path, "pair file")

    controls = pd.read_csv(control_path)
    pairs = pd.read_csv(pair_path)
    adoptions = read_adoption_file(adoption_path)

    require_columns(controls, {"repo_name"}, "control file")
    require_columns(pairs, {"treatment_repo", "control_repo"}, "pair file")

    controls = controls.copy()
    pairs = pairs.copy()

    controls["repo_name"] = normalize_repo(controls["repo_name"])
    pairs["treatment_repo"] = normalize_repo(pairs["treatment_repo"])
    pairs["control_repo"] = normalize_repo(pairs["control_repo"])

    if adoptions.empty:
        in_window = adoptions.copy()
        post_window = adoptions.copy()
    else:
        adoptions["cursor_evidence_in_analysis_window"] = (
            adoptions["adoption_month"] <= args.analysis_end
        )
        in_window = adoptions[adoptions["cursor_evidence_in_analysis_window"]].copy()
        post_window = adoptions[~adoptions["cursor_evidence_in_analysis_window"]].copy()

    remove_controls = set(in_window["repo_name"].astype(str).str.strip())

    final_controls = controls[~controls["repo_name"].isin(remove_controls)].copy()
    dropped_pairs = pairs[pairs["control_repo"].isin(remove_controls)].copy()
    final_pairs = pairs[~pairs["control_repo"].isin(remove_controls)].copy()

    coverage = build_coverage(pairs, final_pairs)
    zero_control_treatments = coverage[coverage["num_final_controls"] == 0].copy()

    strict_1to3_treatments = set(
        coverage.loc[coverage["num_final_controls"] == 3, "treatment_repo"]
    )
    strict_1to3_pairs = final_pairs[
        final_pairs["treatment_repo"].isin(strict_1to3_treatments)
    ].copy()
    strict_1to3_coverage = coverage[
        coverage["treatment_repo"].isin(strict_1to3_treatments)
    ].copy()

    ts_repos_before, ts_repos_after = maybe_filter_time_series(
        args.control_ts_repos_file,
        args.final_control_ts_repos_file,
        remove_controls,
        "control repo time series",
    )

    ts_contrib_before, ts_contrib_after = maybe_filter_time_series(
        args.control_ts_contributors_file,
        args.final_control_ts_contributors_file,
        remove_controls,
        "control contributor time series",
    )

    summary = pd.DataFrame(
        [
            {"metric": "analysis_end", "value": args.analysis_end},
            {"metric": "controls_before_local_cursor_filter", "value": controls["repo_name"].nunique()},
            {"metric": "local_cursor_evidence_controls_total", "value": adoptions["repo_name"].nunique()},
            {"metric": "local_cursor_evidence_controls_in_window_removed", "value": len(remove_controls)},
            {"metric": "local_cursor_evidence_controls_post_window_kept", "value": post_window["repo_name"].nunique()},
            {"metric": "final_controls", "value": final_controls["repo_name"].nunique()},
            {"metric": "pairs_before_local_cursor_filter", "value": len(pairs)},
            {"metric": "final_pairs", "value": len(final_pairs)},
            {"metric": "strict_1to3_treatment_repos", "value": len(strict_1to3_treatments)},
            {"metric": "strict_1to3_pair_rows", "value": len(strict_1to3_pairs)},
            {"metric": "dropped_pairs_local_cursor_in_window", "value": len(dropped_pairs)},
            {"metric": "treatment_repos_before_local_cursor_filter", "value": pairs["treatment_repo"].nunique()},
            {"metric": "treatment_repos_with_final_controls", "value": final_pairs["treatment_repo"].nunique()},
            {"metric": "treatment_repos_lost_all_controls", "value": len(zero_control_treatments)},
            {"metric": "control_ts_repos_rows_before_filter", "value": ts_repos_before},
            {"metric": "control_ts_repos_rows_after_filter", "value": ts_repos_after},
            {"metric": "control_ts_contributors_rows_before_filter", "value": ts_contrib_before},
            {"metric": "control_ts_contributors_rows_after_filter", "value": ts_contrib_after},
        ]
    )

    save_csv(in_window, Path(args.in_window_evidence_file))
    save_csv(post_window, Path(args.post_window_evidence_file))
    save_csv(final_controls, Path(args.final_control_file))
    save_csv(final_pairs, Path(args.final_pair_file))
    save_csv(dropped_pairs, Path(args.dropped_pair_file))
    save_csv(coverage, Path(args.coverage_file))
    save_csv(zero_control_treatments, Path(args.zero_control_treatment_file))
    save_csv(summary, Path(args.summary_file))

    if args.strict_1to3_pair_file:
        save_csv(strict_1to3_pairs, Path(args.strict_1to3_pair_file))
    if args.strict_1to3_coverage_file:
        save_csv(strict_1to3_coverage, Path(args.strict_1to3_coverage_file))

    print("Summary:")
    print(summary.to_string(index=False))
    print()

    print("In-window local Cursor controls removed:")
    if in_window.empty:
        print("(none)")
    else:
        cols = ["repo_name", "adoption_month", "adoption_date", "evidence_paths", "confidence"]
        cols = [c for c in cols if c in in_window.columns]
        print(in_window[cols].to_string(index=False))
    print()

    print("Post-window local Cursor controls kept as diagnostics:")
    if post_window.empty:
        print("(none)")
    else:
        cols = ["repo_name", "adoption_month", "adoption_date", "evidence_paths", "confidence"]
        cols = [c for c in cols if c in post_window.columns]
        print(post_window[cols].to_string(index=False))
    print()

    print("Final control-count distribution:")
    print(coverage["num_final_controls"].value_counts().sort_index().to_string())
    print()

    print("Strict 1:3 robustness subset:")
    print("Strict 1:3 treatment repos:", len(strict_1to3_treatments))
    print("Strict 1:3 pair rows:", len(strict_1to3_pairs))
    if not strict_1to3_coverage.empty:
        print(strict_1to3_coverage["num_final_controls"].value_counts().sort_index().to_string())
    print()

    if len(zero_control_treatments) > 0:
        print("Treatment repositories that lost all controls:")
        print(zero_control_treatments.to_string(index=False))
        print()

    print("Saved final control file:", args.final_control_file)
    print("Saved final pair file:", args.final_pair_file)
    print("Saved final coverage file:", args.coverage_file)
    if args.strict_1to3_pair_file:
        print("Saved strict 1:3 pair file:", args.strict_1to3_pair_file)
    if args.strict_1to3_coverage_file:
        print("Saved strict 1:3 coverage file:", args.strict_1to3_coverage_file)
    print("Saved summary file:", args.summary_file)

    if args.fail_if_zero_control and len(zero_control_treatments) > 0:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
