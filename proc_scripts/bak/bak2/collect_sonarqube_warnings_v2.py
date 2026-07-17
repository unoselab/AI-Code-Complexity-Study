#!/usr/bin/env python3
"""
Extended SonarQube warning collector.

This file intentionally keeps the original paper-oriented warning logic available
by importing scripts/collect_sonarqube_warnings.py, then adds a second mode for
run3a-style repo-month smoke tests.

Modes:
  event:
    Paper-style workflow.
    Reads panel_event_monthly.csv, identifies treated repos and event_time,
    then collects warnings for relative periods around treatment.

  timeseries:
    Smoke-test / diagnostic workflow.
    Reads ts_repos_monthly.csv with repo_name, month, latest_commit,
    then collects warning records for those exact repo-month rows.

Why not replace the original?
  The original file contains the paper-specific event-time logic. We preserve it
  and reuse its pure helper functions where possible.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import random
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

SONAR_TOKEN = os.getenv("SONAR_TOKEN")
SONAR_HOST = os.getenv("SONAR_HOST")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ORIGINAL_SCRIPT = PROJECT_DIR / "scripts" / "collect_sonarqube_warnings.py"

if not ORIGINAL_SCRIPT.exists():
    raise FileNotFoundError(f"Original warning collector not found: {ORIGINAL_SCRIPT}")

spec = importlib.util.spec_from_file_location(
    "original_collect_sonarqube_warnings",
    ORIGINAL_SCRIPT,
)
orig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orig)

# Reuse original constants and pure helper logic where possible.
ISSUE_TYPES = getattr(orig, "ISSUE_TYPES", ["BUG", "VULNERABILITY", "CODE_SMELL"])
SAMPLE_SIZE_PER_REPO_PERIOD = getattr(orig, "SAMPLE_SIZE_PER_REPO_PERIOD", 1000)
MAX_PERIODS = getattr(orig, "MAX_PERIODS", 6)
RANDOM_SEED = getattr(orig, "RANDOM_SEED", 114514)

# Reused original functions:
#   orig.add_months()
#   orig.find_analysis_for_month()
#   orig.find_previous_analysis_date()
#
# New functions are added below where the original implementation is constrained
# by hardcoded files, Bearer auth, or event-only input structure.


def normalize_version_label(value: str) -> str:
    """Normalize YYYY-MM or YYYYMM version labels to YYYYMM."""
    return str(value).strip().replace("-", "")


def repo_to_project_key(repo_name: str) -> str:
    """Convert GitHub repo name owner/repo to SonarQube project key owner_repo."""
    return repo_name.replace("/", "_")


def sonar_get_json(path: str, params: dict) -> dict:
    """GET JSON from SonarQube using token-as-basic-auth."""
    if not SONAR_HOST or not SONAR_TOKEN:
        raise RuntimeError("SONAR_HOST and SONAR_TOKEN must be set in .env")

    url = f"{SONAR_HOST.rstrip('/')}{path}"

    response = requests.get(
        url,
        auth=(SONAR_TOKEN, ""),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_analysis_versions(project_key: str) -> list[dict]:
    """
    Get all VERSION analyses for a SonarQube project.

    This replaces the original API implementation because the original uses
    Bearer auth. The returned structure remains compatible with the original
    helper functions: each row has at least version and date.
    """
    analyses: list[dict] = []
    page = 1
    page_size = 100

    while True:
        data = sonar_get_json(
            "/api/project_analyses/search",
            {
                "project": project_key,
                "category": "VERSION",
                "p": page,
                "ps": page_size,
            },
        )

        batch = data.get("analyses", [])
        if not batch:
            break

        for analysis in batch:
            version = analysis.get("projectVersion")
            if not version:
                continue

            analyses.append(
                {
                    "version": version,
                    "version_normalized": normalize_version_label(version),
                    "date": analysis.get("date"),
                    "analysis_key": analysis.get("key"),
                }
            )

        if len(batch) < page_size:
            break

        page += 1

    return analyses


def find_analysis_for_version(
    analyses: list[dict],
    version: str,
) -> Optional[dict]:
    """Find analysis metadata for a specific YYYY-MM or YYYYMM version label."""
    target = normalize_version_label(version)

    matches = [
        analysis
        for analysis in analyses
        if analysis.get("version_normalized") == target
    ]

    if not matches:
        return None

    # If repeated scans exist for the same version, use the newest analysis.
    return sorted(matches, key=lambda x: x.get("date") or "")[-1]


def fetch_issues_in_created_range(
    project_key: str,
    issue_type: str,
    created_after: Optional[str],
    created_before: str,
) -> list[dict]:
    """
    Fetch SonarQube issues for one type created within a date range.

    This mirrors the original _fetch_issues + get_issues_introduced_in_range
    behavior, but uses token-as-basic-auth and keeps a few extra metadata fields.
    """
    issues_list: list[dict] = []
    page = 1
    page_size = 500

    while True:
        params = {
            "componentKeys": project_key,
            "types": issue_type,
            "createdBefore": created_before,
            "ps": page_size,
            "p": page,
        }

        if created_after:
            params["createdAfter"] = created_after

        try:
            data = sonar_get_json("/api/issues/search", params)
        except requests.exceptions.RequestException as exc:
            logging.warning(
                "Failed to fetch %s issues for %s: %s",
                issue_type,
                project_key,
                exc,
            )
            break

        issues = data.get("issues", [])

        for issue in issues:
            issues_list.append(
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
                    "update_date": issue.get("updateDate"),
                    "status": issue.get("status"),
                    "resolution": issue.get("resolution"),
                }
            )

        if len(issues) < page_size:
            break

        page += 1

    return issues_list


def get_issues_introduced_in_range(
    project_key: str,
    created_after: Optional[str],
    created_before: str,
) -> list[dict]:
    """
    Fetch all BUG, VULNERABILITY, and CODE_SMELL issues created in a date range.

    This is the basic-auth version of the original function with the same name.
    """
    all_issues: list[dict] = []

    for issue_type in ISSUE_TYPES:
        all_issues.extend(
            fetch_issues_in_created_range(
                project_key=project_key,
                issue_type=issue_type,
                created_after=created_after,
                created_before=created_before,
            )
        )

    return all_issues


def collect_warnings_for_repo_event_mode(
    repo_name: str,
    event_time: int,
    sample_size: int = SAMPLE_SIZE_PER_REPO_PERIOD,
) -> list[dict]:
    """
    Paper-style warning collection around treatment.

    This intentionally preserves the original conceptual logic:
      event_time
      relative_period from -MAX_PERIODS to +MAX_PERIODS
      month = add_months(event_time, offset)

    It reuses original pure helper functions but uses the v2 API functions.
    """
    project_key = repo_to_project_key(repo_name)
    analyses = get_analysis_versions(project_key)

    if not analyses:
        logging.warning("No analyses found for %s", repo_name)
        return []

    sorted_analyses = sorted(analyses, key=lambda x: x["date"] or "")
    for analysis in sorted_analyses:
        logging.info("  %s: version %s", analysis["date"], analysis["version"])

    all_issues: list[dict] = []
    periods_found = 0

    for offset in range(-MAX_PERIODS, MAX_PERIODS + 1):
        target_month = orig.add_months(event_time, offset)

        # Reuse original matching logic.
        analysis_info = orig.find_analysis_for_month(analyses, target_month)

        if analysis_info is None:
            logging.debug(
                "No version for %s at period %+d month %d",
                repo_name,
                offset,
                target_month,
            )
            continue

        version, analysis_date = analysis_info

        # Reuse original previous-analysis logic.
        previous_date = orig.find_previous_analysis_date(analyses, analysis_date)

        version_issues = get_issues_introduced_in_range(
            project_key=project_key,
            created_after=previous_date,
            created_before=analysis_date,
        )

        total_issues = len(version_issues)

        if sample_size > 0 and total_issues > sample_size:
            issues = random.sample(version_issues, sample_size)
        else:
            issues = version_issues

        logging.info(
            "Period %+d for %s: sampled %d/%d issues version %s",
            offset,
            repo_name,
            len(issues),
            total_issues,
            version,
        )

        periods_found += 1

        for issue in issues:
            issue["repo_name"] = repo_name
            issue["month"] = target_month
            issue["event_time"] = event_time
            issue["relative_period"] = offset
            issue["sonarqube_version"] = version
            issue["analysis_date"] = analysis_date
            issue["previous_analysis_date"] = previous_date

        all_issues.extend(issues)

    logging.info("Found %d periods with data for %s", periods_found, repo_name)
    return all_issues


def collect_issues_for_repo_month(
    repo_name: str,
    month: str,
    latest_commit: str,
    sample_size: int,
) -> list[dict]:
    """
    run3a-style warning collection for one repo-month row.

    This is new because the original script only works from treatment event time.
    """
    project_key = repo_to_project_key(repo_name)
    analyses = get_analysis_versions(project_key)

    if not analyses:
        logging.warning("No SonarQube analyses found for %s", repo_name)
        return []

    analysis = find_analysis_for_version(analyses, month)

    if not analysis:
        logging.warning(
            "No SonarQube analysis found for %s version %s",
            project_key,
            month,
        )
        return []

    analysis_date = analysis["date"]

    # Reuse original previous-analysis logic.
    previous_date = orig.find_previous_analysis_date(analyses, analysis_date)

    version_issues = get_issues_introduced_in_range(
        project_key=project_key,
        created_after=previous_date,
        created_before=analysis_date,
    )

    total_issues = len(version_issues)

    if sample_size > 0 and total_issues > sample_size:
        issues = random.sample(version_issues, sample_size)
    else:
        issues = version_issues

    logging.info(
        "%s at %s: collected %d/%d detailed issues",
        repo_name,
        month,
        len(issues),
        total_issues,
    )

    for issue in issues:
        issue["repo_name"] = repo_name
        issue["project_key"] = project_key
        issue["month"] = month
        issue["latest_commit"] = latest_commit
        issue["sonarqube_version"] = analysis["version"]
        issue["analysis_date"] = analysis_date
        issue["previous_analysis_date"] = previous_date

    return issues


def read_treatment_repos_from_panel(
    panel_file: Path,
    event_min: int,
    event_max: int,
    repos: Optional[list[str]],
) -> pd.DataFrame:
    """
    Read treatment repositories and event times from panel_event_monthly.csv.

    This preserves the original treatment filtering logic but makes paths and
    event-window bounds configurable.
    """
    if not panel_file.exists():
        raise FileNotFoundError(f"Panel data file not found: {panel_file}")

    panel_df = pd.read_csv(panel_file)

    treatment_df = panel_df[
        panel_df["event"].notna() & (panel_df["event"] != "")
    ].copy()

    treatment_df["event"] = treatment_df["event"].astype(str).str.replace("-", "")
    treatment_df = treatment_df[treatment_df["event"].str.match(r"^\d{6}$")]
    treatment_df["event"] = treatment_df["event"].astype(int)

    treatment_df = treatment_df[
        (treatment_df["event"] > event_min) & (treatment_df["event"] <= event_max)
    ]

    if repos:
        treatment_df = treatment_df[treatment_df["repo_name"].isin(repos)]

    treatment_repos = treatment_df.groupby("repo_name")["event"].first().reset_index()

    return treatment_repos


def collect_event_mode(
    panel_file: Path,
    sample_size: int,
    event_min: int,
    event_max: int,
    repos: Optional[list[str]],
) -> list[dict]:
    """Collect warning records using the original paper-style event mode."""
    treatment_repos = read_treatment_repos_from_panel(
        panel_file=panel_file,
        event_min=event_min,
        event_max=event_max,
        repos=repos,
    )

    logging.info("Found %d treatment repositories", len(treatment_repos))

    all_issues: list[dict] = []

    for _, row in treatment_repos.iterrows():
        repo_name = row["repo_name"]
        event_time = int(row["event"])

        logging.info("Processing %s treatment at %d", repo_name, event_time)

        issues = collect_warnings_for_repo_event_mode(
            repo_name=repo_name,
            event_time=event_time,
            sample_size=sample_size,
        )

        all_issues.extend(issues)

    return all_issues


def collect_timeseries_mode(
    timeseries_file: Path,
    sample_size: int,
    repos: Optional[list[str]],
) -> list[dict]:
    """Collect warning records for repo-month rows in a simple time-series CSV."""
    if not timeseries_file.exists():
        raise FileNotFoundError(f"Time-series file not found: {timeseries_file}")

    ts_df = pd.read_csv(
        timeseries_file,
        dtype={
            "repo_name": str,
            "month": str,
            "latest_commit": str,
        },
    )

    required_cols = {"repo_name", "month", "latest_commit"}
    missing_cols = required_cols - set(ts_df.columns)

    if missing_cols:
        raise ValueError(f"Missing required columns in {timeseries_file}: {missing_cols}")

    if repos:
        ts_df = ts_df[ts_df["repo_name"].isin(repos)]

    logging.info("Found %d repo-month rows", len(ts_df))

    all_issues: list[dict] = []

    for _, row in ts_df.iterrows():
        repo_name = str(row["repo_name"]).strip()
        month = str(row["month"]).strip()
        latest_commit = str(row["latest_commit"]).strip()

        logging.info("Processing %s at %s", repo_name, month)

        issues = collect_issues_for_repo_month(
            repo_name=repo_name,
            month=month,
            latest_commit=latest_commit,
            sample_size=sample_size,
        )

        all_issues.extend(issues)

    return all_issues


def write_outputs(
    all_issues: list[dict],
    warnings_output: Path,
    definitions_output: Path,
    mode: str,
) -> None:
    """Write detailed warning records and unique rule definitions."""
    warnings_output.parent.mkdir(parents=True, exist_ok=True)
    definitions_output.parent.mkdir(parents=True, exist_ok=True)

    if not all_issues:
        logging.warning("No issues collected")
        pd.DataFrame().to_csv(warnings_output, index=False)
        pd.DataFrame().to_csv(definitions_output, index=False)
        return

    output_df = pd.DataFrame(all_issues)

    definition_cols = ["rule", "type", "severity", "effort", "message"]
    available_definition_cols = [
        col for col in definition_cols if col in output_df.columns
    ]

    definitions_df = (
        output_df[available_definition_cols]
        .drop_duplicates(subset=["rule"])
        .rename(columns={"message": "example_message"})
        .sort_values("rule")
        .reset_index(drop=True)
    )

    if mode == "event":
        # Keep the original output layout as much as possible.
        key_cols = ["repo_name", "month", "event_time", "relative_period"]
        other_cols = [col for col in output_df.columns if col not in key_cols]
        output_df = output_df[key_cols + other_cols]

        # Preserve original behavior: definitions contain type/severity/message/effort;
        # warning rows focus on identifiers and locations.
        cols_to_drop = [
            col
            for col in ["type", "severity", "message", "effort"]
            if col in output_df.columns
        ]
        output_df = output_df.drop(columns=cols_to_drop)

    else:
        key_cols = [
            "repo_name",
            "project_key",
            "month",
            "latest_commit",
            "sonarqube_version",
            "analysis_date",
            "previous_analysis_date",
        ]
        key_cols = [col for col in key_cols if col in output_df.columns]
        other_cols = [col for col in output_df.columns if col not in key_cols]
        output_df = output_df[key_cols + other_cols]

    definitions_df.to_csv(definitions_output, index=False)
    output_df.to_csv(warnings_output, index=False)

    logging.info(
        "Saved %d unique rule definitions to %s",
        len(definitions_df),
        definitions_output,
    )
    logging.info("Saved %d issues to %s", len(output_df), warnings_output)

    if "type" in pd.DataFrame(all_issues).columns:
        summary_df = pd.DataFrame(all_issues)
        logging.info("Issues by type:\n%s", summary_df.groupby("type").size())

    if mode == "event" and "relative_period" in output_df.columns:
        logging.info(
            "Issues per relative period:\n%s",
            output_df.groupby("relative_period").size(),
        )

    if mode == "timeseries" and "month" in output_df.columns:
        logging.info("Issues per month:\n%s", output_df.groupby("month").size())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect SonarQube warning records in event or timeseries mode."
    )

    parser.add_argument(
        "--mode",
        choices=["event", "timeseries"],
        default="event",
        help="event preserves original paper logic; timeseries supports run3a.",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_DIR / "data",
        help="Base data directory.",
    )

    parser.add_argument(
        "--panel-file",
        type=Path,
        default=None,
        help="Panel CSV for event mode. Default: DATA_DIR/panel_event_monthly.csv.",
    )

    parser.add_argument(
        "--timeseries-file",
        type=Path,
        default=None,
        help="Time-series CSV for timeseries mode. Default: DATA_DIR/ts_repos_monthly.csv.",
    )

    parser.add_argument(
        "--warnings-output",
        type=Path,
        default=None,
        help="Output detailed warnings CSV. Default: DATA_DIR/sonarqube_warnings.csv.",
    )

    parser.add_argument(
        "--definitions-output",
        type=Path,
        default=None,
        help=(
            "Output unique warning rule definitions CSV. "
            "Default: DATA_DIR/sonarqube_warning_definitions.csv."
        ),
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=SAMPLE_SIZE_PER_REPO_PERIOD,
        help="Maximum issue rows sampled per repo-period. Use 0 to keep all.",
    )

    parser.add_argument(
        "--event-min",
        type=int,
        default=202407,
        help="Original-style lower bound: keep events > event-min.",
    )

    parser.add_argument(
        "--event-max",
        type=int,
        default=202503,
        help="Original-style upper bound: keep events <= event-max.",
    )

    parser.add_argument(
        "--repos",
        nargs="*",
        default=None,
        help="Optional repo_name filter, e.g., owner/repo owner2/repo2.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    random.seed(RANDOM_SEED)

    if not SONAR_TOKEN or not SONAR_HOST:
        raise SystemExit("SONAR_TOKEN and SONAR_HOST must be set in .env")

    data_dir = args.data_dir.expanduser().resolve()

    panel_file = (
        args.panel_file.expanduser().resolve()
        if args.panel_file
        else data_dir / "panel_event_monthly.csv"
    )

    timeseries_file = (
        args.timeseries_file.expanduser().resolve()
        if args.timeseries_file
        else data_dir / "ts_repos_monthly.csv"
    )

    warnings_output = (
        args.warnings_output.expanduser().resolve()
        if args.warnings_output
        else data_dir / "sonarqube_warnings.csv"
    )

    definitions_output = (
        args.definitions_output.expanduser().resolve()
        if args.definitions_output
        else data_dir / "sonarqube_warning_definitions.csv"
    )

    logging.info("Original script imported from: %s", ORIGINAL_SCRIPT)
    logging.info("Mode: %s", args.mode)
    logging.info("Data dir: %s", data_dir)

    if args.mode == "event":
        logging.info("Panel file: %s", panel_file)
        all_issues = collect_event_mode(
            panel_file=panel_file,
            sample_size=args.sample_size,
            event_min=args.event_min,
            event_max=args.event_max,
            repos=args.repos,
        )

    else:
        logging.info("Time-series file: %s", timeseries_file)
        all_issues = collect_timeseries_mode(
            timeseries_file=timeseries_file,
            sample_size=args.sample_size,
            repos=args.repos,
        )

    write_outputs(
        all_issues=all_issues,
        warnings_output=warnings_output,
        definitions_output=definitions_output,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
