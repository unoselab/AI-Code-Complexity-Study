#!/usr/bin/env python3
"""Collect SonarQube issue-level warnings for treatment and control JS/TS repos.

This script creates all-repo warning files needed for category-level DiD.

Inputs:
  - treatment ts_repos_monthly_scanned.csv
  - control ts_repos_monthly_scanned.csv
  - optional panel file for event_time / relative_period metadata
  - sonarqube_warning_definitions.csv for rule -> category mapping

Outputs:
  - data/sonarqube_warnings_all_repos.csv
  - data/sonarqube_warning_category_counts_all_repos.csv
  - data/sonarqube_warnings_all_repos_collection_qc.csv

Important:
  This script reconstructs SonarQube project_key as:
    repo_name.replace("/", "_")

  It uses SonarQube analysis versions, where monthly scan version is usually:
    YYYY-MM

  It collects issues created between the previous analysis date and the current
  analysis date. If no previous analysis exists, it collects issues up to the
  current analysis date and marks range_has_previous_analysis = 0.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ISSUE_TYPES = ["BUG", "VULNERABILITY", "CODE_SMELL"]

DEFAULT_TREATMENT_SCANNED = (
    "tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/ts_repos_monthly_scanned.csv"
)

DEFAULT_CONTROL_SCANNED = (
    "tmp_jsts_test/data/jsts_sonarqube_main/control/data/ts_repos_monthly_scanned.csv"
)

DEFAULT_PANEL = (
    "tmp_jsts_test/data/jsts_did_final/"
    "panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input.csv"
)

DEFAULT_WARNING_DEFINITIONS = "data/sonarqube_warning_definitions.csv"

DEFAULT_ISSUES_OUTPUT = "data/sonarqube_warnings_all_repos.csv"
DEFAULT_COUNTS_OUTPUT = "data/sonarqube_warning_category_counts_all_repos.csv"
DEFAULT_QC_OUTPUT = "data/sonarqube_warnings_all_repos_collection_qc.csv"


ISSUE_COLUMNS = [
    "repo_name",
    "dataset_source",
    "month",
    "event_time",
    "relative_period",
    "project_key",
    "analysis_version",
    "analysis_date",
    "previous_analysis_date",
    "range_has_previous_analysis",
    "issue_key",
    "type",
    "severity",
    "message",
    "component",
    "line",
    "rule",
    "effort",
    "creation_date",
    "category",
]

QC_COLUMNS = [
    "repo_name",
    "dataset_source",
    "month",
    "project_key",
    "analysis_version",
    "analysis_date",
    "previous_analysis_date",
    "range_has_previous_analysis",
    "status",
    "issue_count",
    "category_count",
    "truncated",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect SonarQube warning issues for treatment and control repos."
    )

    parser.add_argument("--treatment-scanned", default=DEFAULT_TREATMENT_SCANNED)
    parser.add_argument("--control-scanned", default=DEFAULT_CONTROL_SCANNED)
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--warning-definitions", default=DEFAULT_WARNING_DEFINITIONS)

    parser.add_argument("--issues-output", default=DEFAULT_ISSUES_OUTPUT)
    parser.add_argument("--counts-output", default=DEFAULT_COUNTS_OUTPUT)
    parser.add_argument("--qc-output", default=DEFAULT_QC_OUTPUT)

    parser.add_argument("--sonar-host", default=os.getenv("SONAR_HOST"))
    parser.add_argument("--sonar-token", default=os.getenv("SONAR_TOKEN"))

    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)

    parser.add_argument(
        "--max-repos-per-source",
        type=int,
        default=0,
        help="Smoke-test limit. 0 means no limit.",
    )
    parser.add_argument(
        "--max-months-per-repo",
        type=int,
        default=0,
        help="Smoke-test limit. 0 means no limit.",
    )
    parser.add_argument(
        "--max-issues-per-repo-month",
        type=int,
        default=0,
        help="Safety cap. 0 means no cap. If cap is hit, truncated=1.",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip repo-months already recorded in the QC output.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete existing outputs before running.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned repo-months. Do not call SonarQube.",
    )

    return parser.parse_args()


def load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(override=True)


def normalize_month(value: Any) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None

    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"

    if len(text) >= 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
        return text[:7]

    return None


def month_to_yyyymm(value: Any) -> int | None:
    month = normalize_month(value)
    if month is None:
        return None
    return int(month.replace("-", ""))


def month_to_id(value: Any) -> int | None:
    month = normalize_month(value)
    if month is None:
        return None
    year = int(month[:4])
    mon = int(month[5:7])
    return year * 12 + mon


def add_month_metadata(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "month" not in out.columns:
        raise ValueError("Input scanned file must contain month column.")

    out["month_norm"] = out["month"].map(normalize_month)
    out = out[out["month_norm"].notna()].copy()
    out["month_yyyymm"] = out["month_norm"].str.replace("-", "", regex=False).astype(int)
    out["month_id"] = out["month_norm"].map(month_to_id)

    return out


def load_scanned(path: Path, dataset_source: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing scanned input: {path}")

    df = pd.read_csv(path, low_memory=False)

    required = {"repo_name", "month", "latest_commit"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")

    df = add_month_metadata(df)
    df["dataset_source"] = dataset_source
    df["project_key"] = df["repo_name"].astype(str).str.replace("/", "_", regex=False)

    df = df[df["latest_commit"].notna()].copy()
    df = df[["repo_name", "dataset_source", "project_key", "month_norm", "month_yyyymm", "month_id"]]

    df = df.drop_duplicates(["repo_name", "dataset_source", "month_yyyymm"]).copy()

    return df


def load_panel_event_map(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Panel file not found. Event metadata will be omitted: {path}")
        return None

    panel = pd.read_csv(path, low_memory=False)

    if "repo_name" not in panel.columns or "event" not in panel.columns:
        print("Panel has no repo_name/event columns. Event metadata will be omitted.")
        return None

    event_map = panel[["repo_name", "event"]].drop_duplicates("repo_name").copy()
    event_map["event_norm"] = event_map["event"].map(normalize_month)
    event_map["event_time"] = event_map["event_norm"].map(month_to_yyyymm)
    event_map["event_id"] = event_map["event_norm"].map(month_to_id)

    return event_map[["repo_name", "event_time", "event_id"]]


def attach_event_metadata(scanned: pd.DataFrame, event_map: pd.DataFrame | None) -> pd.DataFrame:
    out = scanned.copy()

    if event_map is not None:
        out = out.merge(event_map, on="repo_name", how="left")
    else:
        out["event_time"] = pd.NA
        out["event_id"] = pd.NA

    out["relative_period"] = out["month_id"] - out["event_id"]

    out.loc[out["event_time"].isna(), "relative_period"] = pd.NA

    return out


def load_rule_category_map(path: Path) -> dict[str, str]:
    if not path.exists():
        print(f"Warning definitions not found: {path}")
        return {}

    df = pd.read_csv(path, low_memory=False)

    if "rule" not in df.columns or "category" not in df.columns:
        raise ValueError(f"{path} must contain rule and category columns.")

    mapping = (
        df[["rule", "category"]]
        .dropna()
        .drop_duplicates("rule")
        .set_index("rule")["category"]
        .to_dict()
    )

    print(f"Loaded rule-category mapping: {path}")
    print(f"Mapped rules: {len(mapping)}")

    return mapping


def request_json(
    sonar_host: str,
    sonar_token: str,
    endpoint: str,
    params: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    url = f"{sonar_host.rstrip('/')}{endpoint}"
    headers = {"Authorization": f"Bearer {sonar_token}"}

    response = requests.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()

    return response.json()


def get_analysis_versions(
    sonar_host: str,
    sonar_token: str,
    project_key: str,
) -> list[dict[str, str]]:
    analyses: list[dict[str, str]] = []
    page = 1

    while True:
        data = request_json(
            sonar_host=sonar_host,
            sonar_token=sonar_token,
            endpoint="/api/project_analyses/search",
            params={
                "project": project_key,
                "category": "VERSION",
                "p": page,
                "ps": 100,
            },
        )

        batch = data.get("analyses", [])

        if not batch:
            break

        for analysis in batch:
            version = analysis.get("projectVersion")
            date = analysis.get("date")

            if version and date:
                analyses.append({"version": version, "date": date})

        if len(batch) < 100:
            break

        page += 1

    return analyses


def find_analysis_for_month(
    analyses: list[dict[str, str]],
    month_yyyymm: int,
) -> tuple[str, str] | None:
    target_plain = str(month_yyyymm)
    target_dash = f"{target_plain[:4]}-{target_plain[4:6]}"

    for analysis in analyses:
        version = str(analysis["version"])
        version_plain = version.replace("-", "")

        if version == target_dash or version_plain == target_plain:
            return version, analysis["date"]

    return None


def find_previous_analysis_date(
    analyses: list[dict[str, str]],
    current_date: str,
) -> str | None:
    sorted_analyses = sorted(analyses, key=lambda x: x["date"])

    previous_date = None
    for analysis in sorted_analyses:
        if analysis["date"] >= current_date:
            break
        previous_date = analysis["date"]

    return previous_date


def fetch_issues_for_range(
    sonar_host: str,
    sonar_token: str,
    project_key: str,
    created_after: str | None,
    created_before: str,
    page_size: int,
    max_issues: int,
) -> tuple[list[dict[str, Any]], bool]:
    all_issues: list[dict[str, Any]] = []
    truncated = False

    for issue_type in ISSUE_TYPES:
        page = 1

        while True:
            params: dict[str, Any] = {
                "componentKeys": project_key,
                "types": issue_type,
                "p": page,
                "ps": page_size,
                "createdBefore": created_before,
            }

            if created_after:
                params["createdAfter"] = created_after

            data = request_json(
                sonar_host=sonar_host,
                sonar_token=sonar_token,
                endpoint="/api/issues/search",
                params=params,
            )

            issues = data.get("issues", [])

            for issue in issues:
                all_issues.append(
                    {
                        "issue_key": issue.get("key"),
                        "type": issue.get("type"),
                        "severity": issue.get("severity"),
                        "message": issue.get("message"),
                        "component": issue.get("component"),
                        "line": issue.get("line"),
                        "rule": issue.get("rule"),
                        "effort": issue.get("effort"),
                        "creation_date": issue.get("creationDate"),
                    }
                )

                if max_issues > 0 and len(all_issues) >= max_issues:
                    truncated = True
                    return all_issues, truncated

            if len(issues) < page_size:
                break

            page += 1

    return all_issues, truncated


def append_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")

        if not file_exists:
            writer.writeheader()

        for row in rows:
            writer.writerow(row)


def load_completed_keys(qc_output: Path) -> set[tuple[str, str, int]]:
    if not qc_output.exists():
        return set()

    qc = pd.read_csv(qc_output, low_memory=False)

    required = {"repo_name", "dataset_source", "month", "status"}
    if not required.issubset(qc.columns):
        return set()

    completed = qc[qc["status"].isin(["ok", "no_issues", "analysis_not_found", "no_analyses"])]
    keys = set(
        zip(
            completed["repo_name"].astype(str),
            completed["dataset_source"].astype(str),
            completed["month"].astype(int),
        )
    )

    return keys


def build_counts(issues_output: Path, counts_output: Path) -> None:
    if not issues_output.exists():
        raise FileNotFoundError(f"Cannot build counts. Missing: {issues_output}")

    issues = pd.read_csv(issues_output, low_memory=False)

    if issues.empty:
        counts = pd.DataFrame(
            columns=[
                "repo_name",
                "dataset_source",
                "month",
                "category",
                "warning_count",
            ]
        )
    else:
        if "category" not in issues.columns:
            issues["category"] = "Other"

        counts = (
            issues.groupby(["repo_name", "dataset_source", "month", "category"], dropna=False)
            .size()
            .reset_index(name="warning_count")
            .sort_values(["dataset_source", "repo_name", "month", "category"])
        )

    counts_output.parent.mkdir(parents=True, exist_ok=True)
    counts.to_csv(counts_output, index=False)


def maybe_delete_outputs(args: argparse.Namespace) -> None:
    if not args.overwrite:
        return

    for output in [args.issues_output, args.counts_output, args.qc_output]:
        path = Path(output)
        if path.exists():
            path.unlink()
            print(f"Deleted existing output: {path}")


def main() -> int:
    load_env()
    args = parse_args()

    sonar_host = args.sonar_host or os.getenv("SONAR_HOST")
    sonar_token = args.sonar_token or os.getenv("SONAR_TOKEN")

    if not sonar_host or not sonar_token:
        raise ValueError("SONAR_HOST and SONAR_TOKEN must be set in .env or passed as args.")

    maybe_delete_outputs(args)

    treatment = load_scanned(Path(args.treatment_scanned), "treatment")
    control = load_scanned(Path(args.control_scanned), "control")

    if args.max_repos_per_source > 0:
        treatment_repos = sorted(treatment["repo_name"].unique())[: args.max_repos_per_source]
        control_repos = sorted(control["repo_name"].unique())[: args.max_repos_per_source]
        treatment = treatment[treatment["repo_name"].isin(treatment_repos)].copy()
        control = control[control["repo_name"].isin(control_repos)].copy()

    scanned = pd.concat([treatment, control], ignore_index=True)

    if args.max_months_per_repo > 0:
        scanned = (
            scanned.sort_values(["dataset_source", "repo_name", "month_yyyymm"])
            .groupby(["dataset_source", "repo_name"], group_keys=False)
            .head(args.max_months_per_repo)
            .copy()
        )

    event_map = load_panel_event_map(Path(args.panel))
    scanned = attach_event_metadata(scanned, event_map)

    mapping = load_rule_category_map(Path(args.warning_definitions))

    issues_output = Path(args.issues_output)
    counts_output = Path(args.counts_output)
    qc_output = Path(args.qc_output)

    completed_keys = load_completed_keys(qc_output) if args.resume else set()

    print("=" * 80)
    print("run10b: collect SonarQube warnings for treatment + control repos")
    print("=" * 80)
    print(f"Treatment scanned: {args.treatment_scanned}")
    print(f"Control scanned:   {args.control_scanned}")
    print(f"Panel:             {args.panel}")
    print(f"Issues output:     {issues_output}")
    print(f"Counts output:     {counts_output}")
    print(f"QC output:         {qc_output}")
    print(f"Rows planned:      {len(scanned)}")
    print(f"Repos planned:     {scanned['repo_name'].nunique()}")
    print(f"Treatment repos:   {scanned.loc[scanned['dataset_source'] == 'treatment', 'repo_name'].nunique()}")
    print(f"Control repos:     {scanned.loc[scanned['dataset_source'] == 'control', 'repo_name'].nunique()}")
    print(f"Resume:            {args.resume}")
    print(f"Completed keys:    {len(completed_keys)}")
    print(f"Dry run:           {args.dry_run}")
    print("=" * 80)

    if args.dry_run:
        print(scanned.head(30).to_string(index=False))
        return 0

    analyses_cache: dict[str, list[dict[str, str]]] = {}

    processed = 0
    skipped = 0
    total_issues = 0

    for row in scanned.itertuples(index=False):
        repo_name = str(row.repo_name)
        dataset_source = str(row.dataset_source)
        project_key = str(row.project_key)
        month_yyyymm = int(row.month_yyyymm)

        key = (repo_name, dataset_source, month_yyyymm)

        if key in completed_keys:
            skipped += 1
            continue

        issue_rows: list[dict[str, Any]] = []
        qc_row: dict[str, Any] = {
            "repo_name": repo_name,
            "dataset_source": dataset_source,
            "month": month_yyyymm,
            "project_key": project_key,
            "analysis_version": "",
            "analysis_date": "",
            "previous_analysis_date": "",
            "range_has_previous_analysis": 0,
            "status": "",
            "issue_count": 0,
            "category_count": 0,
            "truncated": 0,
            "error": "",
        }

        try:
            if project_key not in analyses_cache:
                analyses_cache[project_key] = get_analysis_versions(
                    sonar_host=sonar_host,
                    sonar_token=sonar_token,
                    project_key=project_key,
                )

            analyses = analyses_cache[project_key]

            if not analyses:
                qc_row["status"] = "no_analyses"
                append_rows(qc_output, [qc_row], QC_COLUMNS)
                processed += 1
                continue

            analysis_info = find_analysis_for_month(analyses, month_yyyymm)

            if analysis_info is None:
                qc_row["status"] = "analysis_not_found"
                append_rows(qc_output, [qc_row], QC_COLUMNS)
                processed += 1
                continue

            analysis_version, analysis_date = analysis_info
            previous_analysis_date = find_previous_analysis_date(analyses, analysis_date)

            qc_row["analysis_version"] = analysis_version
            qc_row["analysis_date"] = analysis_date
            qc_row["previous_analysis_date"] = previous_analysis_date or ""
            qc_row["range_has_previous_analysis"] = 1 if previous_analysis_date else 0

            issues, truncated = fetch_issues_for_range(
                sonar_host=sonar_host,
                sonar_token=sonar_token,
                project_key=project_key,
                created_after=previous_analysis_date,
                created_before=analysis_date,
                page_size=args.page_size,
                max_issues=args.max_issues_per_repo_month,
            )

            for issue in issues:
                rule = issue.get("rule")
                category = mapping.get(rule, "Other")

                issue_row = {
                    "repo_name": repo_name,
                    "dataset_source": dataset_source,
                    "month": month_yyyymm,
                    "event_time": row.event_time if pd.notna(row.event_time) else "",
                    "relative_period": row.relative_period if pd.notna(row.relative_period) else "",
                    "project_key": project_key,
                    "analysis_version": analysis_version,
                    "analysis_date": analysis_date,
                    "previous_analysis_date": previous_analysis_date or "",
                    "range_has_previous_analysis": 1 if previous_analysis_date else 0,
                    "category": category,
                    **issue,
                }
                issue_rows.append(issue_row)

            unique_categories = len({r["category"] for r in issue_rows})

            qc_row["status"] = "ok" if issue_rows else "no_issues"
            qc_row["issue_count"] = len(issue_rows)
            qc_row["category_count"] = unique_categories
            qc_row["truncated"] = 1 if truncated else 0

            append_rows(issues_output, issue_rows, ISSUE_COLUMNS)
            append_rows(qc_output, [qc_row], QC_COLUMNS)

            total_issues += len(issue_rows)
            processed += 1

            if processed % 25 == 0:
                print(
                    f"Processed={processed}, skipped={skipped}, "
                    f"total_issues={total_issues}, current={dataset_source}:{repo_name}:{month_yyyymm}"
                )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

        except Exception as exc:
            qc_row["status"] = "error"
            qc_row["error"] = str(exc)
            append_rows(qc_output, [qc_row], QC_COLUMNS)
            processed += 1
            print(f"ERROR {dataset_source}:{repo_name}:{month_yyyymm}: {exc}", file=sys.stderr)

    print("=" * 80)
    print("Collection finished.")
    print(f"Processed repo-months: {processed}")
    print(f"Skipped repo-months:   {skipped}")
    print(f"Total issues fetched:  {total_issues}")
    print("=" * 80)

    build_counts(issues_output, counts_output)

    print(f"Saved issues: {issues_output}")
    print(f"Saved counts: {counts_output}")
    print(f"Saved QC:     {qc_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
