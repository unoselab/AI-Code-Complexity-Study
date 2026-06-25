#!/usr/bin/env python3
"""
Prepare JS/TS SonarQube scan inputs from a final matched DiD panel.

This script:
1. Reads the final window-completed matched DiD panel.
2. Extracts treatment/control repository lists and analysis months.
3. Calls create_tmp_repo_timeseries_history.py to find the latest commit
   at or before each month-end for each repository.
4. Writes treatment/control SonarQube input files.
5. Writes repo lists, month list, and a compact summary CSV.

The output files are intended to be consumed by run_sonarqube_v2.py.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare treatment/control SonarQube input files from a final JS/TS DiD panel."
    )

    parser.add_argument(
        "--panel-file",
        default="tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv",
        help="Final window-completed matched DiD panel.",
    )

    parser.add_argument(
        "--sonar-root",
        default="tmp_jsts_test/data/jsts_sonarqube_main",
        help="Root output directory for SonarQube input artifacts.",
    )

    parser.add_argument(
        "--treatment-clone-root",
        default="../ai_code_complexity_study_jsts_repo_dataset",
        help="Clone root for treatment repositories.",
    )

    parser.add_argument(
        "--control-clone-root",
        default="../ai_code_complexity_study_jsts_control_repo_dataset",
        help="Clone root for control repositories.",
    )

    parser.add_argument(
        "--history-script",
        default="proc_scripts/create_tmp_repo_timeseries_history.py",
        help="Script used to create historical repo-month latest_commit input.",
    )

    parser.add_argument(
        "--treatment-output",
        default=None,
        help="Treatment SonarQube input CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--control-output",
        default=None,
        help="Control SonarQube input CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--months-file",
        default=None,
        help="Output text file containing comma-separated months. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--treatment-repos-file",
        default=None,
        help="Output text file containing treatment repos. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--control-repos-file",
        default=None,
        help="Output text file containing control repos. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--summary-file",
        default=None,
        help="Output summary CSV. Defaults under sonar-root.",
    )

    parser.add_argument(
        "--max-treatment-repos",
        type=int,
        default=0,
        help="Optional smoke-test limit for treatment repos. 0 means all.",
    )

    parser.add_argument(
        "--max-control-repos",
        type=int,
        default=0,
        help="Optional smoke-test limit for control repos. 0 means all.",
    )

    parser.add_argument(
        "--allow-missing-latest-commit",
        action="store_true",
        help="Allow rows with missing latest_commit instead of failing.",
    )

    return parser.parse_args()


def require_path(path: Path, label: str, is_dir: bool = False) -> None:
    if is_dir:
        if not path.is_dir():
            raise SystemExit(f"ERROR: {label} not found or not a directory: {path}")
    else:
        if not path.is_file():
            raise SystemExit(f"ERROR: {label} not found: {path}")


def write_lines(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(values) + ("\n" if values else ""))


def summarize_input(path: Path, label: str) -> dict:
    require_path(path, f"{label} output file")

    df = pd.read_csv(path)

    required = {"repo_name", "month", "latest_commit"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")

    duplicate_repo_month_rows = int(df.duplicated(["repo_name", "month"]).sum())
    missing_latest_commit = int(df["latest_commit"].isna().sum())

    return {
        "dataset_source": label,
        "file": str(path),
        "rows": len(df),
        "repos": df["repo_name"].nunique(),
        "min_month": df["month"].min(),
        "max_month": df["month"].max(),
        "missing_latest_commit": missing_latest_commit,
        "duplicate_repo_month_rows": duplicate_repo_month_rows,
    }


def run_history_script(
    history_script: Path,
    output_file: Path,
    clone_root: Path,
    months_csv: str,
    repos: list[str],
    label: str,
) -> None:
    if not repos:
        raise SystemExit(f"ERROR: no {label} repos to process.")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(history_script),
        "--output",
        str(output_file),
        "--clone-root",
        str(clone_root),
        "--months",
        months_csv,
        *repos,
    ]

    print()
    print(f"** Creating {label} historical SonarQube input")
    print("------------------------------------------------------------")
    print("repos:", len(repos))
    print("output:", output_file)
    print("clone root:", clone_root)
    print("command:")
    print(" ".join(cmd[:8]) + f" ... [{len(repos)} repos]")

    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()

    panel_file = Path(args.panel_file)
    sonar_root = Path(args.sonar_root)
    treatment_clone_root = Path(args.treatment_clone_root)
    control_clone_root = Path(args.control_clone_root)
    history_script = Path(args.history_script)

    treatment_output = (
        Path(args.treatment_output)
        if args.treatment_output
        else sonar_root / "treatment" / "data" / "ts_repos_monthly.csv"
    )
    control_output = (
        Path(args.control_output)
        if args.control_output
        else sonar_root / "control" / "data" / "ts_repos_monthly.csv"
    )

    months_file = (
        Path(args.months_file) if args.months_file else sonar_root / "months.txt"
    )
    treatment_repos_file = (
        Path(args.treatment_repos_file)
        if args.treatment_repos_file
        else sonar_root / "treatment_repos.txt"
    )
    control_repos_file = (
        Path(args.control_repos_file)
        if args.control_repos_file
        else sonar_root / "control_repos.txt"
    )
    summary_file = (
        Path(args.summary_file)
        if args.summary_file
        else sonar_root / "sonarqube_input_summary.csv"
    )

    require_path(panel_file, "panel file")
    require_path(history_script, "history script")
    require_path(treatment_clone_root, "treatment clone root", is_dir=True)
    require_path(control_clone_root, "control clone root", is_dir=True)

    sonar_root.mkdir(parents=True, exist_ok=True)
    treatment_output.parent.mkdir(parents=True, exist_ok=True)
    control_output.parent.mkdir(parents=True, exist_ok=True)

    print("** Loading final panel")
    print("------------------------------------------------------------")
    print("panel:", panel_file)

    panel = pd.read_csv(panel_file)

    required = {"repo_name", "time", "dataset_source"}
    missing = required - set(panel.columns)
    if missing:
        raise SystemExit(f"ERROR: panel missing required columns: {sorted(missing)}")

    panel["repo_name"] = panel["repo_name"].astype(str).str.strip()
    panel["time"] = panel["time"].astype(str).str.strip()
    panel["dataset_source"] = panel["dataset_source"].astype(str).str.strip()

    months = sorted(panel["time"].dropna().unique().tolist())
    treatment_repos = sorted(
        panel.loc[panel["dataset_source"] == "treatment", "repo_name"]
        .dropna()
        .unique()
        .tolist()
    )
    control_repos = sorted(
        panel.loc[panel["dataset_source"] == "control", "repo_name"]
        .dropna()
        .unique()
        .tolist()
    )

    if args.max_treatment_repos > 0:
        treatment_repos = treatment_repos[: args.max_treatment_repos]
    if args.max_control_repos > 0:
        control_repos = control_repos[: args.max_control_repos]

    if not months:
        raise SystemExit("ERROR: no months found in panel.")
    if not treatment_repos:
        raise SystemExit("ERROR: no treatment repos found in panel.")
    if not control_repos:
        raise SystemExit("ERROR: no control repos found in panel.")

    months_csv = ",".join(months)

    months_file.parent.mkdir(parents=True, exist_ok=True)
    months_file.write_text(months_csv + "\n")
    write_lines(treatment_repos_file, treatment_repos)
    write_lines(control_repos_file, control_repos)

    print("months:", months[0], "to", months[-1], "n=", len(months))
    print("treatment repos:", len(treatment_repos))
    print("control repos:", len(control_repos))
    print("wrote:", months_file)
    print("wrote:", treatment_repos_file)
    print("wrote:", control_repos_file)

    run_history_script(
        history_script=history_script,
        output_file=treatment_output,
        clone_root=treatment_clone_root,
        months_csv=months_csv,
        repos=treatment_repos,
        label="treatment",
    )

    run_history_script(
        history_script=history_script,
        output_file=control_output,
        clone_root=control_clone_root,
        months_csv=months_csv,
        repos=control_repos,
        label="control",
    )

    print()
    print("** Input summary")
    print("------------------------------------------------------------")

    summary_rows = [
        summarize_input(treatment_output, "treatment"),
        summarize_input(control_output, "control"),
    ]

    summary = pd.DataFrame(summary_rows)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_file, index=False)

    print(summary.to_string(index=False))
    print()
    print("Saved summary:", summary_file)

    total_missing_latest_commit = int(summary["missing_latest_commit"].sum())
    total_duplicate_rows = int(summary["duplicate_repo_month_rows"].sum())

    if total_duplicate_rows > 0:
        raise SystemExit(
            f"ERROR: duplicate repo-month rows detected: {total_duplicate_rows}"
        )

    if total_missing_latest_commit > 0 and not args.allow_missing_latest_commit:
        raise SystemExit(
            "ERROR: missing latest_commit values detected. "
            "Use --allow-missing-latest-commit only if this is expected."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
