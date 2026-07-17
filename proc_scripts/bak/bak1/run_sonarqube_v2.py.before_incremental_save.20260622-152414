#!/usr/bin/env python3
"""
Script to run SonarQube scanner on the latest commits of each week or month.

This script:
1. Reads the time series repository stats from ts_repos_weekly.csv or ts_repos_monthly.csv
2. For each repository and time period, runs SonarQube scanner on the latest commit
3. Collects and stores the analysis results

NOTE: Sometimes the analysis results are not immediately available in database,
so you may have to run this script twice in order to fetch all available metrics
"""

import argparse
import time
import re
import logging
import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import git
import pandas as pd
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Constants
SONAR_PATH = os.getenv("SONAR_SCANNER_PATH")
SONAR_TOKEN = os.getenv("SONAR_TOKEN")
SONAR_HOST = os.getenv("SONAR_HOST")

# Time key in the time series dataframe
TIME_KEY = None

# Fixed start date for data collection, 2024-01-01 determined by adoption time analysis
START_DATE = "2024-01-01"
END_DATE = "2025-08-31"

# Metrics to collect from SonarQube
METRICS_OF_INTEREST = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "software_quality_maintainability_remediation_effort",  # technical debt
]

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "tmp_sonar_batch" / "data"
CLONE_DIR = SCRIPT_DIR.parent.parent / "CursorRepos"
CONTROL_CLONE_DIR = SCRIPT_DIR.parent.parent / "ControlRepos"

# Number of processes to use for parallel processing
NUM_PROCESSES = 1  # small-batch smoke test

# Taking too long to analyze
REPO_IGNORE = [
    "meshery/meshery",
    "swc-project/swc",
    "djmonkeyuk/nms-base-builder",
    "Azure/azure-rest-api-specs-examples",
]


def check_analysis_exists(project_key: str, version: str) -> bool:
    """
    Check if SonarQube analysis already exists for a project and version.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis

    Returns:
        bool: True if analysis exists, False otherwise
    """
    try:
        page = 1
        while True:
            url = f"{SONAR_HOST}/api/project_analyses/search"
            auth = (SONAR_TOKEN, "")
            params = {
                "project": project_key,
                "category": "VERSION",
                "p": page,
                "ps": 100,  # Page size of 100 analyses
            }

            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()

            data = response.json()
            if "analyses" not in data or not data["analyses"]:
                # No more analyses to check
                break

            for analysis in data["analyses"]:
                if analysis.get("projectVersion") == version:
                    logging.info(
                        "Analysis already exists for %s version %s",
                        project_key,
                        version,
                    )
                    return True

            # Check if we've reached the last page
            if len(data["analyses"]) < 100:
                break

            page += 1

        return False

    except requests.exceptions.RequestException as e:
        logging.error(
            "Failed to check existing analysis for %s: %s", project_key, str(e)
        )
        return False


def run_sonar_scan(
    repo_path: Path, commit_hash: str, version: str, project_key: str
) -> bool:
    """
    Run SonarQube scanner on a specific commit.

    Args:
        repo_path: Path to the repository
        commit_hash: Git commit hash to analyze
        version: Version identifier for the analysis
        project_key: SonarQube project key

    Returns:
        bool: True if scan was successful, False otherwise
    """
    try:
        # Checkout the specific commit
        repo = git.Repo(str(repo_path))
        current = repo.head.commit

        # Force checkout and clean the working directory
        repo.git.reset("--hard")
        repo.git.clean("-fd")
        repo.git.checkout(commit_hash, force=True)

        try:
            # Run sonar-scanner
            cmd = [
                SONAR_PATH,
                f"-Dsonar.projectKey={project_key}",
                f"-Dsonar.projectName={project_key}",
                f"-Dsonar.projectVersion={version}",
                "-Dsonar.sources=.",
                f"-Dsonar.java.binaries=.",  # Fix Java errors, hopefully we find some .class here
                f"-Dsonar.host.url={SONAR_HOST}",
                f"-Dsonar.token={SONAR_TOKEN}",
                "-Dsonar.scm.disabled=true",  # Disable SCM to speed up analysis
            ]

            subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, check=True
            )
            logging.info("SonarQube scan completed for %s at %s", project_key, version)
            return True

        finally:
            # Always return to original commit
            repo.git.checkout(current)

    except subprocess.CalledProcessError as e:
        logging.error(
            "SonarQube scan failed for %s at %s: %s", project_key, version, e.stderr
        )
        return False
    except Exception as e:
        logging.error("Error during scan of %s at %s: %s", project_key, version, str(e))
        return False


def get_sonar_metrics(project_key: str, version: str) -> Optional[Dict]:
    """
    Get metrics from SonarQube API for a project and specific version.

    Args:
        project_key: SonarQube project key
        version: Version identifier of the analysis

    Returns:
        dict: Metrics data or None if request failed
    """
    try:
        # First, find the analysis with the matching version to get its date
        analysis_date = None
        page = 1

        while analysis_date is None:
            url = f"{SONAR_HOST}/api/project_analyses/search"
            auth = (SONAR_TOKEN, "")
            params = {
                "project": project_key,
                "category": "VERSION",
                "ps": 100,  # Page size
                "p": page,  # Page number
            }

            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()

            data = response.json()

            logging.info("Found %d analyses for %s", len(data["analyses"]), project_key)

            # Find the analysis with matching version to get its date
            if "analyses" in data and data["analyses"]:
                for analysis in data["analyses"]:
                    if analysis.get("projectVersion") == version:
                        analysis_date = analysis.get("date")
                        break

                # If we haven't found the analysis and there are more pages, continue to the next page
                if analysis_date is None and len(data["analyses"]) == 100:
                    page += 1
                else:
                    break  # No more results or found the analysis
            else:
                break  # No analyses returned

        if not analysis_date:
            logging.warning("No analysis found for %s version %s", project_key, version)
            return None

        # Now get the measures for this specific date using search_history
        url = f"{SONAR_HOST}/api/measures/search_history"
        params = {
            "component": project_key,
            "metrics": ",".join(METRICS_OF_INTEREST),
            "from": analysis_date,
            "to": analysis_date,
        }

        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()

        data = response.json()
        metrics = {}

        if "measures" in data:
            for measure in data["measures"]:
                if (
                    measure["history"]
                    and len(measure["history"]) > 0
                    and "value" in measure["history"][0]
                ):
                    metrics[measure["metric"]] = float(measure["history"][0]["value"])

        return metrics if metrics else None

    except requests.exceptions.RequestException as e:
        logging.error(
            "Failed to get metrics for %s version %s: %s", project_key, version, str(e)
        )
        return None


def wait_for_analysis_ready(
    project_key: str,
    version: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
) -> bool:
    """Wait until a SonarQube VERSION analysis appears for the given project/version."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if check_analysis_exists(project_key, version):
            logging.info(
                "SonarQube analysis is ready for %s version %s",
                project_key,
                version,
            )
            return True

        logging.info(
            "Waiting for SonarQube analysis for %s version %s...",
            project_key,
            version,
        )
        time.sleep(poll_interval_seconds)

    logging.warning(
        "Timed out waiting for SonarQube analysis for %s version %s",
        project_key,
        version,
    )
    return False


def process_repository(
    ts_df: pd.DataFrame,
    repo_name: str,
    aggregation: str,
    clone_dir: Path,
) -> pd.DataFrame:
    """
    Process a single repository's SonarQube analysis.

    Args:
        ts_df: Time series dataframe.
        repo_name: Name of the repository to process.
        aggregation: Either "week" or "month".
        clone_dir: Directory containing cloned repositories.

    Returns:
        pd.DataFrame: Updated time series dataframe for this repository.
    """
    # Setup repository info and data.
    project_key = repo_name.replace("/", "_")
    repo_path = Path(clone_dir) / project_key

    if not repo_path.exists():
        logging.warning("Repository %s not found at %s", repo_name, repo_path)
        return ts_df[ts_df["repo_name"] == repo_name]

    # Get repository-specific rows.
    repo_df = ts_df[ts_df["repo_name"] == repo_name].copy()

    # Use a single date format string based on aggregation.
    date_format = "%Y-W%W" if aggregation == "week" else "%Y-%m"

    # Get start and end times using the same format.
    start_time = pd.Timestamp(START_DATE).strftime(date_format)
    end_time = pd.Timestamp(END_DATE).strftime(date_format)

    logging.info("Processing %s from %s to %s", repo_name, start_time, end_time)

    # Process each time period's latest commit in chronological order.
    time_periods = sorted(
        repo_df[
            (repo_df[TIME_KEY].astype(str) >= start_time)
            & (repo_df[TIME_KEY].astype(str) <= end_time)
        ][TIME_KEY].unique()
    )

    for time_period in time_periods:
        row_idx = repo_df[repo_df[TIME_KEY] == time_period].index[0]
        commit_hash = repo_df.loc[row_idx, "latest_commit"]

        # Handle missing or invalid commit hashes robustly.
        if pd.isna(commit_hash) or not str(commit_hash).strip():
            logging.warning("No commit hash for %s at %s", repo_name, time_period)
            continue

        commit_hash = str(commit_hash).strip()
        time_period = str(time_period).strip()

        analysis_exists = check_analysis_exists(project_key, time_period)

        if not analysis_exists:
            logging.info("%s at %s (%s)", repo_name, time_period, commit_hash[:8])

            scan_result = run_sonar_scan(
                repo_path,
                commit_hash,
                time_period,
                project_key,
            )

            # Some versions of run_sonar_scan may return None on success.
            # Treat only explicit False as failure.
            if scan_result is False:
                logging.warning(
                    "Skipping metrics because SonarQube scan failed for %s at %s",
                    repo_name,
                    time_period,
                )
                continue

            # SonarScanner returns after uploading the report, but SonarQube's
            # Compute Engine may need time before the VERSION analysis appears.
            ready = wait_for_analysis_ready(
                project_key=project_key,
                version=time_period,
                timeout_seconds=120,
                poll_interval_seconds=5,
            )

            if not ready:
                logging.warning(
                    "Skipping metrics because analysis was not ready for %s at %s",
                    repo_name,
                    time_period,
                )
                continue

        # Get and store metrics.
        metrics = get_sonar_metrics(project_key, time_period)

        if metrics:
            for metric, value in metrics.items():
                repo_df.loc[row_idx, metric] = value

            logging.info("Metrics for %s at %s: %s", repo_name, time_period, metrics)
        else:
            logging.warning("No metrics returned for %s at %s", repo_name, time_period)

    return repo_df



def infer_date_range_from_input(ts_df: pd.DataFrame, time_key: str) -> tuple[str, str]:
    """Infer START_DATE and END_DATE from the input time-series file."""
    if time_key not in ts_df.columns:
        raise ValueError(f"Missing time column: {time_key}")

    values = (
        ts_df[time_key]
        .dropna()
        .astype(str)
        .str.strip()
    )

    if values.empty:
        raise ValueError(f"No valid values found in time column: {time_key}")

    # Accept both YYYY-MM and YYYYMM formats, but normalize to YYYY-MM.
    normalized = []
    for value in values:
        if re.fullmatch(r"\d{6}", value):
            normalized.append(f"{value[:4]}-{value[4:]}")
        elif re.fullmatch(r"\d{4}-\d{2}", value):
            normalized.append(value)
        else:
            raise ValueError(
                f"Unsupported time value format in {time_key}: {value}. "
                "Expected YYYY-MM or YYYYMM."
            )

    return min(normalized), max(normalized)


def main() -> None:
    """Main function to run SonarQube analysis on repositories."""
    global TIME_KEY
    parser = argparse.ArgumentParser(
        description="Run SonarQube analysis on repository commits with weekly or monthly aggregation."
    )
    parser.add_argument(
        "--aggregation",
        choices=["week", "month"],
        default="week",
        help="Aggregate data by week or month (default: week)",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="Run analysis on control repositories instead of experimental ones",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=(
            "Directory containing ts_repos_monthly.csv or ts_repos_weekly.csv. "
            "Default: %(default)s"
        ),
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help=(
            "Explicit input time-series CSV. "
            "If provided, this overrides --data-dir and --control file-name selection."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help=(
            "Output CSV path. Default: overwrite the selected input file."
        ),
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing cloned repositories. "
            "Default: treatment clone dir, or control clone dir when --control is used."
        ),
    )
    parser.add_argument(
        "--num-processes",
        type=int,
        default=NUM_PROCESSES,
        help="Number of worker processes. Default: %(default)s",
    )
    args = parser.parse_args()
    TIME_KEY = "week" if args.aggregation == "week" else "month"

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if not SONAR_PATH or not SONAR_TOKEN:
        logging.error("SONAR_PATH and SONAR_TOKEN must be set in .env file")
        return

    # Set input/output file paths.
    data_dir = Path(args.data_dir).expanduser().resolve()
    logging.info("Using data directory: %s", data_dir)

    if args.input_file is not None:
        ts_repos_file = Path(args.input_file).expanduser().resolve()
    else:
        file_prefix = "ts_repos_control_" if args.control else "ts_repos_"
        ts_repos_file = data_dir / f"{file_prefix}{args.aggregation}ly.csv"

    if args.output_file is not None:
        output_file = Path(args.output_file).expanduser().resolve()
    else:
        output_file = ts_repos_file

    if args.clone_dir is not None:
        clone_dir = Path(args.clone_dir).expanduser().resolve()
    else:
        clone_dir = CONTROL_CLONE_DIR if args.control else CLONE_DIR

    logging.info("Using input file: %s", ts_repos_file)
    logging.info("Using output file: %s", output_file)
    logging.info("Using clone directory: %s", clone_dir)
    logging.info("Using num processes: %s", args.num_processes)

    # Read repository time series data and adoption data
    try:
        ts_df = pd.read_csv(ts_repos_file)
        global START_DATE, END_DATE
        START_DATE, END_DATE = infer_date_range_from_input(ts_df, TIME_KEY)
        logging.info("Using input-derived date range: %s to %s", START_DATE, END_DATE)

    except FileNotFoundError as e:
        logging.error(f"Required file not found: {e}")
        return

    # Create columns for metrics if they don't exist
    for col in METRICS_OF_INTEREST:
        if col not in ts_df.columns:
            ts_df[col] = None

    # Get unique repository names
    repo_names = set(ts_df["repo_name"].unique()) - set(REPO_IGNORE)
    with mp.Pool(args.num_processes) as pool:
        args_list = [
            (ts_df, repo_name, args.aggregation, clone_dir)
            for repo_name in repo_names
        ]
        results = pool.starmap(process_repository, args_list, chunksize=1)

    updated_df = pd.concat(results)
    if "technical_debt" in updated_df.columns:
        updated_df.drop(columns=["technical_debt"], inplace=True)
    updated_df.rename(
        columns={
            "software_quality_maintainability_remediation_effort": "technical_debt"
        },
        inplace=True,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    updated_df.sort_values(by=["repo_name", TIME_KEY]).to_csv(
        output_file, index=False
    )
    logging.info("Updated metrics saved to %s", output_file)


if __name__ == "__main__":
    main()
