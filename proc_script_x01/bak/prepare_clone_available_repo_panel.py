#!/usr/bin/env python3
"""
Prepare the clone-available, all-language repository-month panel for run-x-c01.

Purpose
-------
This stage reconstructs the paper's matched repository scope using only local
Git clones that are currently available under the treatment and control clone
roots. It uses the replication-package monthly CSV files as the authoritative
source for outcomes, covariates, Cursor adoption, and paper SonarQube NCLOC.

The stage does not restrict repositories or source files to one programming
language. It prepares a whole-repository snapshot manifest for the later cloc
scan in run-x-c02.

Primary design
--------------
- Preserve the original matched-control assignments from matching.csv.
- Start from locally cloned treatment repositories that appear as treatment
  rows in matching.csv.
- Retain treatment repositories with a first Cursor adoption event inside the
  configured paper cohort window.
- Use only locally available controls assigned to those valid-event treatments.
- Censor a matched control at and after its own first Cursor adoption event.
- Use absorbing treatment timing for treatment repositories.
- Preserve paper NCLOC as ncloc_paper_sonarqube.
- Resolve one historical Git commit per repository-month without modifying any
  local checkout.
- Keep unresolved snapshot rows in the paper-NCLOC panel, but exclude them from
  the unique snapshot manifest used by run-x-c02.

Inputs
------
- matching.csv
- ts_repos_monthly.csv
- ts_repos_control_monthly.csv
- treatment clone directory
- control clone directory

Outputs
-------
- clone-available repository-month panel
- unique whole-repository snapshot manifest
- clone availability audit
- treatment-control matching-slot audit
- control-adoption censoring audit
- treatment estimability audit for five paper outcomes
- unresolved repository-month snapshot rows
- QC table
- long-form summary table

Safety
------
Only read-only Git commands are used. This script never checks out, resets,
cleans, pulls, fetches, or modifies a repository.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import numpy as np
import pandas as pd


MATCHING_REQUIRED_COLUMNS = {
    "repo_name",
    "group",
    "matched_period",
    "propensity_score",
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
}

MONTHLY_REQUIRED_COLUMNS = {
    "month",
    "repo_name",
    "latest_commit",
    "cursor",
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
    "stars",
    "issues",
    "issue_comments",
    "age",
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "num_dependencies_total",
    "num_vulnerable_dependencies",
    "average_technical_lag",
}

CONTROL_COLUMNS = [
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
]

FIRST_STAGE_RAW_COLUMNS = [
    "age",
    "ncloc_paper_sonarqube",
    "contributors",
    "stars",
    "issues",
]

OUTCOME_COLUMNS = {
    "commits": "commits",
    "lines_added": "lines_added",
    "quality_warnings": "quality_warnings",
    "duplicated_lines_density": "duplicated_lines_density",
    "cognitive_complexity": "cognitive_complexity",
}

LOG1P_SOURCE_COLUMNS = [
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
    "stars",
    "issues",
    "issue_comments",
    "age",
    "quality_warnings",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]


@dataclass(frozen=True)
class CloneRecord:
    """Identity and Git validity for one local clone directory."""

    clone_role: str
    repo_name: str
    repo_key: str
    clone_dir_name: str
    clone_path: str
    clone_found: int
    is_git_repository: int
    origin_url: str
    identity_source: str
    identity_status: str


@dataclass(frozen=True)
class CommitCheck:
    """Cached read-only validation result for one commit candidate."""

    exists: bool
    timestamp: Optional[int]
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a clone-available, all-language repository-month panel "
            "and historical snapshot manifest for run-x-c01."
        )
    )
    parser.add_argument("--matching-file", required=True, type=Path)
    parser.add_argument("--treatment-monthly-file", required=True, type=Path)
    parser.add_argument("--control-monthly-file", required=True, type=Path)
    parser.add_argument("--treatment-clone-dir", required=True, type=Path)
    parser.add_argument("--control-clone-dir", required=True, type=Path)

    parser.add_argument("--panel-output", required=True, type=Path)
    parser.add_argument("--snapshot-manifest-output", required=True, type=Path)
    parser.add_argument("--clone-audit-output", required=True, type=Path)
    parser.add_argument("--pair-audit-output", required=True, type=Path)
    parser.add_argument("--control-adoption-audit-output", required=True, type=Path)
    parser.add_argument("--treatment-estimability-audit-output", required=True, type=Path)
    parser.add_argument("--unresolved-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)

    parser.add_argument("--start-month", default="2024-01")
    parser.add_argument("--end-month", default="2025-08")
    parser.add_argument("--treatment-cohort-start", default="2024-08")
    parser.add_argument("--treatment-cohort-end", default="2025-03")
    parser.add_argument("--git-timeout-seconds", type=int, default=30)

    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-local-treatment-clones", type=int, default=123)
    parser.add_argument("--expected-matched-treatment-clones", type=int, default=115)
    parser.add_argument("--expected-extra-treatment-clones", type=int, default=8)
    parser.add_argument("--expected-primary-treatment-repos", type=int, default=110)
    parser.add_argument("--expected-candidate-control-repos", type=int, default=156)
    parser.add_argument("--expected-available-control-repos", type=int, default=154)
    parser.add_argument("--expected-primary-pair-slots", type=int, default=323)
    parser.add_argument("--expected-panel-rows", type=int, default=2261)
    parser.add_argument("--expected-treatment-panel-rows", type=int, default=1079)
    parser.add_argument("--expected-control-panel-rows", type=int, default=1182)
    parser.add_argument("--expected-panel-repositories", type=int, default=232)

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def repo_key(value: object) -> str:
    return clean_text(value).strip("/").casefold()


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")


def parse_period(value: object, label: str) -> pd.Period:
    text = clean_text(value)
    try:
        return pd.Period(text, freq="M")
    except Exception as exc:
        raise ValueError(f"{label} must use YYYY-MM format: {value!r}") from exc


def parse_period_series(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text)
    parsed = pd.to_datetime(text, format="%Y-%m", errors="coerce")
    invalid = text.ne("") & parsed.isna()
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid months: {examples}")
    result = pd.Series(pd.NaT, index=values.index, dtype="period[M]")
    valid = parsed.notna()
    result.loc[valid] = parsed.loc[valid].dt.to_period("M")
    return result


def normalize_bool(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text).str.casefold()
    true_values = {"1", "true", "t", "yes", "y"}
    false_values = {"0", "false", "f", "no", "n"}
    invalid = ~text.isin(true_values | false_values | {""})
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid Boolean values: {examples}")
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    result.loc[text.isin(true_values)] = 1
    result.loc[text.isin(false_values)] = 0
    return result


def parse_github_repo_from_origin(origin_url: str) -> str:
    value = clean_text(origin_url)
    if not value:
        return ""

    scp_match = re.match(r"^(?:[^@]+@)?github\.com:(?P<path>[^\s]+)$", value)
    if scp_match:
        path = scp_match.group("path")
    else:
        parsed = urlparse(value)
        if (parsed.hostname or "").casefold() != "github.com":
            return ""
        path = parsed.path

    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        return ""
    return f"{parts[0]}/{parts[1]}"


def run_git(
    repo_path: Path,
    args: list[str],
    timeout_seconds: int,
) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return True, completed.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logging.debug("Git command failed for %s: %s", repo_path, exc)
        return False, ""


def build_known_repo_names(
    matching: pd.DataFrame,
    treatment_monthly: pd.DataFrame,
    control_monthly: pd.DataFrame,
) -> dict[str, list[str]]:
    names: dict[str, set[str]] = {}
    columns: list[pd.Series] = [
        matching["repo_name"],
        matching["matched_control_1"],
        matching["matched_control_2"],
        matching["matched_control_3"],
        treatment_monthly["repo_name"],
        control_monthly["repo_name"],
    ]
    for series in columns:
        for value in series:
            text = clean_text(value)
            key = repo_key(text)
            if key:
                names.setdefault(key, set()).add(text)
    return {
        key: sorted(values, key=lambda item: (item.casefold(), item))
        for key, values in names.items()
    }


def build_directory_candidates(known_names: dict[str, list[str]]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for spellings in known_names.values():
        for name in spellings:
            candidates.setdefault(name.replace("/", "_").casefold(), []).append(name)
    return candidates


def scan_clone_root(
    clone_root: Path,
    role: str,
    known_names: dict[str, list[str]],
    directory_candidates: dict[str, list[str]],
    timeout_seconds: int,
) -> list[CloneRecord]:
    records: list[CloneRecord] = []
    for child in sorted(clone_root.iterdir(), key=lambda path: path.name.casefold()):
        if not child.is_dir():
            continue

        git_ok, inside = run_git(
            child, ["rev-parse", "--is-inside-work-tree"], timeout_seconds
        )
        is_git = int(git_ok and inside == "true")
        origin_url = ""
        parsed_name = ""
        identity_source = "unresolved"
        identity_status = "unresolved"

        if is_git:
            origin_ok, origin_url = run_git(
                child, ["remote", "get-url", "origin"], timeout_seconds
            )
            if origin_ok:
                parsed_name = parse_github_repo_from_origin(origin_url)
                if parsed_name:
                    identity_source = "origin_url"
                    identity_status = "resolved"

        if not parsed_name:
            fallback = directory_candidates.get(child.name.casefold(), [])
            fallback_keys = sorted({repo_key(value) for value in fallback if repo_key(value)})
            if len(fallback_keys) == 1:
                key = fallback_keys[0]
                parsed_name = known_names.get(key, fallback)[0]
                identity_source = "directory_name_fallback"
                identity_status = "resolved"
            elif len(fallback_keys) > 1:
                identity_source = "directory_name_ambiguous"
                identity_status = "ambiguous"

        key = repo_key(parsed_name)
        if key and key in known_names:
            parsed_name = known_names[key][0]

        records.append(
            CloneRecord(
                clone_role=role,
                repo_name=parsed_name,
                repo_key=key,
                clone_dir_name=child.name,
                clone_path=str(child.resolve()),
                clone_found=1,
                is_git_repository=is_git,
                origin_url=origin_url,
                identity_source=identity_source,
                identity_status=identity_status,
            )
        )
    return records


def index_clone_records(records: list[CloneRecord], role: str) -> dict[str, CloneRecord]:
    resolved = [
        record
        for record in records
        if record.clone_role == role
        and record.repo_key
        and record.identity_status == "resolved"
        and record.is_git_repository == 1
    ]
    duplicates: dict[str, list[CloneRecord]] = {}
    for record in resolved:
        duplicates.setdefault(record.repo_key, []).append(record)
    conflicts = {key: values for key, values in duplicates.items() if len(values) > 1}
    if conflicts:
        sample = {
            key: [record.clone_path for record in values]
            for key, values in list(conflicts.items())[:10]
        }
        raise ValueError(f"Duplicate valid {role} clones resolve to one repo key: {sample}")
    return {key: values[0] for key, values in duplicates.items()}


def normalize_matching(matching: pd.DataFrame) -> pd.DataFrame:
    require_columns(matching, MATCHING_REQUIRED_COLUMNS, "matching.csv")
    data = matching.copy()
    for column in ["repo_name", "group", *CONTROL_COLUMNS]:
        data[column] = data[column].map(clean_text)
    data["group"] = data["group"].str.casefold()
    data["repo_key"] = data["repo_name"].map(repo_key)

    treatment = data[data["group"].eq("treatment")].copy()
    blank = treatment["repo_key"].eq("")
    if blank.any():
        raise ValueError("matching.csv contains a treatment row with a blank repo_name")

    duplicate_keys = treatment.duplicated("repo_key", keep=False)
    if duplicate_keys.any():
        conflict_columns = ["repo_key", "repo_name", *CONTROL_COLUMNS]
        grouped = treatment.loc[duplicate_keys, conflict_columns].groupby("repo_key")
        conflicts = []
        for key, group in grouped:
            assignments = group[CONTROL_COLUMNS].fillna("").astype(str).drop_duplicates()
            if len(assignments) > 1:
                conflicts.append((key, group.to_dict(orient="records")))
        if conflicts:
            raise ValueError(
                "matching.csv has conflicting treatment assignments for case-insensitive keys: "
                + repr(conflicts[:5])
            )
        treatment = treatment.drop_duplicates("repo_key", keep="first")
    return treatment


def normalize_monthly(df: pd.DataFrame, source: str) -> pd.DataFrame:
    require_columns(df, MONTHLY_REQUIRED_COLUMNS, f"{source} monthly CSV")
    data = df.copy()
    data["dataset_source"] = source
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["month"] = data["month"].map(clean_text)
    data["time_period"] = parse_period_series(data["month"], f"{source}.month")
    data["latest_commit"] = data["latest_commit"].map(clean_text)
    data["cursor_flag"] = normalize_bool(data["cursor"], f"{source}.cursor")

    duplicated = data.duplicated(["repo_key", "month"], keep=False)
    if duplicated.any():
        sample = data.loc[duplicated, ["repo_name", "month"]].head(20)
        raise ValueError(
            f"{source} monthly CSV contains duplicate repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )

    numeric_columns = sorted(MONTHLY_REQUIRED_COLUMNS - {
        "month", "repo_name", "latest_commit", "cursor"
    })
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def first_adoption_map(monthly: pd.DataFrame) -> dict[str, pd.Period]:
    adopted = monthly[monthly["cursor_flag"].eq(1)].copy()
    if adopted.empty:
        return {}
    return adopted.groupby("repo_key")["time_period"].min().to_dict()


def period_distance(later: pd.Period, earlier: pd.Period) -> int:
    return int(later.ordinal - earlier.ordinal)


def expected_value(args: argparse.Namespace, name: str) -> int:
    return int(getattr(args, name))


def make_snapshot_key(dataset_source: str, repo_name: str, commit_sha: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", repo_name).strip("_")
    digest = hashlib.sha256(
        f"{dataset_source}|{repo_key(repo_name)}|{commit_sha.casefold()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{dataset_source}__{slug}__{commit_sha[:12]}__{digest}"


def validate_commit(
    clone_path: Path,
    commit_sha: str,
    month: pd.Period,
    timeout_seconds: int,
    cache: dict[tuple[str, str], CommitCheck],
) -> CommitCheck:
    key = (str(clone_path), commit_sha.casefold())
    if key not in cache:
        exists, _ = run_git(
            clone_path, ["cat-file", "-e", f"{commit_sha}^{{commit}}"], timeout_seconds
        )
        if not exists:
            cache[key] = CommitCheck(False, None, "commit_not_in_clone")
        else:
            timestamp_ok, timestamp_text = run_git(
                clone_path, ["show", "-s", "--format=%ct", commit_sha], timeout_seconds
            )
            if not timestamp_ok or not timestamp_text.isdigit():
                cache[key] = CommitCheck(True, None, "commit_timestamp_unavailable")
            else:
                cache[key] = CommitCheck(True, int(timestamp_text), "commit_exists")

    check = cache[key]
    if not check.exists or check.timestamp is None:
        return check

    next_month_epoch = int(
        (month + 1).start_time.tz_localize("UTC").timestamp()
    )
    if check.timestamp >= next_month_epoch:
        return CommitCheck(True, check.timestamp, "commit_after_month_end")
    return check


def resolve_git_month_end_commit(
    clone_path: Path,
    month: pd.Period,
    timeout_seconds: int,
    cache: dict[tuple[str, str], str],
) -> str:
    key = (str(clone_path), str(month))
    if key in cache:
        return cache[key]
    before = (month + 1).start_time.strftime("%Y-%m-%dT00:00:00Z")
    ok, commit_sha = run_git(
        clone_path,
        ["rev-list", "-1", f"--before={before}", "HEAD"],
        timeout_seconds,
    )
    cache[key] = commit_sha if ok else ""
    return cache[key]


def add_commit_resolution(
    panel: pd.DataFrame,
    clone_map: dict[tuple[str, str], CloneRecord],
    timeout_seconds: int,
) -> pd.DataFrame:
    data = panel.copy()
    data["latest_commit_original"] = data["latest_commit"].map(clean_text)

    ordered = data.sort_values(["dataset_source", "repo_key", "time_period"]).copy()
    ordered["observed_commit_value"] = ordered["latest_commit_original"].replace("", np.nan)
    ordered["prior_commit_before"] = ordered.groupby(
        ["dataset_source", "repo_key"], sort=False
    )["observed_commit_value"].transform(lambda values: values.shift(1).ffill())
    ordered["observed_commit_month_value"] = ordered["time_period"].where(
        ordered["latest_commit_original"].ne("")
    )
    ordered["prior_commit_month_before"] = ordered.groupby(
        ["dataset_source", "repo_key"], sort=False
    )["observed_commit_month_value"].transform(lambda values: values.shift(1).ffill())

    commit_cache: dict[tuple[str, str], CommitCheck] = {}
    month_end_cache: dict[tuple[str, str], str] = {}
    resolved_rows: list[dict[str, object]] = []

    for row in ordered.itertuples(index=False):
        clone = clone_map[(row.dataset_source, row.repo_key)]
        clone_path = Path(clone.clone_path)
        original = clean_text(row.latest_commit_original)
        prior = clean_text(row.prior_commit_before)
        month = row.time_period

        effective = ""
        resolution = "unresolved"
        resolution_source_month = ""
        original_status = "blank"
        prior_status = "blank"
        fallback_status = "not_attempted"
        effective_timestamp: Optional[int] = None

        if original:
            original_check = validate_commit(
                clone_path, original, month, timeout_seconds, commit_cache
            )
            original_status = original_check.status
            if original_check.exists and original_check.timestamp is not None and original_check.status == "commit_exists":
                effective = original
                resolution = "exact_month_commit"
                resolution_source_month = str(month)
                effective_timestamp = original_check.timestamp

        if not effective and prior:
            prior_check = validate_commit(
                clone_path, prior, month, timeout_seconds, commit_cache
            )
            prior_status = prior_check.status
            if prior_check.exists and prior_check.timestamp is not None and prior_check.status == "commit_exists":
                effective = prior
                resolution = "carried_forward_prior_commit"
                prior_month = row.prior_commit_month_before
                resolution_source_month = "" if pd.isna(prior_month) else str(prior_month)
                effective_timestamp = prior_check.timestamp

        if not effective:
            fallback = resolve_git_month_end_commit(
                clone_path, month, timeout_seconds, month_end_cache
            )
            if fallback:
                fallback_check = validate_commit(
                    clone_path, fallback, month, timeout_seconds, commit_cache
                )
                fallback_status = fallback_check.status
                if fallback_check.exists and fallback_check.timestamp is not None and fallback_check.status == "commit_exists":
                    effective = fallback
                    resolution = "resolved_from_git_before_month_end"
                    resolution_source_month = "git_history"
                    effective_timestamp = fallback_check.timestamp
            else:
                fallback_status = "no_commit_before_month_end"

        months_since = pd.NA
        if resolution in {"exact_month_commit", "carried_forward_prior_commit"}:
            if resolution_source_month:
                source_period = pd.Period(resolution_source_month, freq="M")
                months_since = period_distance(month, source_period)

        snapshot_available = int(bool(effective))
        snapshot_key = (
            make_snapshot_key(row.dataset_source, row.repo_name, effective)
            if effective
            else ""
        )
        timestamp_iso = ""
        if effective_timestamp is not None:
            timestamp_iso = pd.Timestamp(effective_timestamp, unit="s", tz="UTC").isoformat()

        effective_after_month_end = 0
        if effective_timestamp is not None:
            next_month_epoch = int((month + 1).start_time.tz_localize("UTC").timestamp())
            effective_after_month_end = int(effective_timestamp >= next_month_epoch)

        resolved_rows.append(
            {
                "row_index": row.Index if hasattr(row, "Index") else None,
                "latest_commit_effective": effective,
                "commit_resolution": resolution,
                "commit_resolution_source_month": resolution_source_month,
                "months_since_observed_commit": months_since,
                "original_commit_validation_status": original_status,
                "prior_commit_validation_status": prior_status,
                "git_fallback_validation_status": fallback_status,
                "effective_commit_timestamp_utc": timestamp_iso,
                "effective_commit_after_month_end": effective_after_month_end,
                "snapshot_available": snapshot_available,
                "repo_snapshot_key": snapshot_key,
            }
        )

    resolution_df = pd.DataFrame(resolved_rows)
    ordered = ordered.reset_index(drop=False).rename(columns={"index": "original_index"})
    resolution_df = resolution_df.drop(columns=["row_index"], errors="ignore")
    ordered = pd.concat([ordered.reset_index(drop=True), resolution_df], axis=1)
    ordered = ordered.sort_values("original_index").set_index("original_index")
    ordered = ordered.loc[data.index]
    return ordered.drop(
        columns=[
            "observed_commit_value",
            "prior_commit_before",
            "observed_commit_month_value",
            "prior_commit_month_before",
        ]
    )


def add_analysis_columns(
    panel: pd.DataFrame,
    start_period: pd.Period,
) -> pd.DataFrame:
    data = panel.copy()
    data["time"] = data["time_period"].astype(str)
    data["time_index"] = data["time_period"].map(
        lambda value: period_distance(value, start_period) + 1
    )
    data["time_yyyymm"] = data["time"].str.replace("-", "", regex=False).astype(int)

    data["event"] = ""
    treatment = data["scope_role"].eq("treatment")
    data.loc[treatment, "event"] = data.loc[treatment, "event_period"].astype(str)
    data["event_yyyymm"] = 0
    data.loc[treatment, "event_yyyymm"] = (
        data.loc[treatment, "event"].str.replace("-", "", regex=False).astype(int)
    )
    data["event_index"] = 0
    data.loc[treatment, "event_index"] = data.loc[treatment, "event_period"].map(
        lambda value: period_distance(value, start_period) + 1
    )

    data["time_to_event"] = pd.Series(pd.NA, index=data.index, dtype="Int64")
    data.loc[treatment, "time_to_event"] = data.loc[treatment].apply(
        lambda row: period_distance(row["time_period"], row["event_period"]), axis=1
    ).astype("Int64")
    data["treatment_group"] = treatment.astype(int)
    data["treated_absorbing"] = (
        treatment & data["time_to_event"].fillna(-10_000).ge(0)
    ).astype(int)
    data["post_event"] = data["treated_absorbing"]

    for lead in range(1, 7):
        if lead == 6:
            data[f"lead_{lead}"] = (
                treatment & data["time_to_event"].fillna(0).le(-lead)
            ).astype(int)
        else:
            data[f"lead_{lead}"] = (
                treatment & data["time_to_event"].eq(-lead).fillna(False)
            ).astype(int)
    for lag in range(0, 7):
        if lag == 6:
            data[f"lag_{lag}"] = (
                treatment & data["time_to_event"].fillna(-1).ge(lag)
            ).astype(int)
        else:
            data[f"lag_{lag}"] = (
                treatment & data["time_to_event"].eq(lag).fillna(False)
            ).astype(int)

    data["ncloc_paper_sonarqube"] = pd.to_numeric(data["ncloc"], errors="coerce")
    data["ncloc_paper_source"] = "paper_replication_monthly_csv"
    data["quality_warnings"] = (
        pd.to_numeric(data["bugs"], errors="coerce")
        + pd.to_numeric(data["vulnerabilities"], errors="coerce")
        + pd.to_numeric(data["code_smells"], errors="coerce")
    )

    for column in LOG1P_SOURCE_COLUMNS:
        numeric = pd.to_numeric(data[column], errors="coerce")
        invalid = numeric.notna() & numeric.lt(0)
        if invalid.any():
            sample = data.loc[invalid, ["repo_name", "time", column]].head(20)
            raise ValueError(
                f"Cannot apply log1p to negative {column}: "
                + repr(sample.to_dict(orient="records"))
            )
        data[f"log_{column}"] = np.log1p(numeric)

    for outcome_name, outcome_column in OUTCOME_COLUMNS.items():
        complete_column = f"paper_ncloc_complete_{outcome_name}"
        required = [outcome_column, *FIRST_STAGE_RAW_COLUMNS]
        data[complete_column] = data[required].notna().all(axis=1).astype(int)

    data["paper_ncloc_complete_all_outcomes"] = data[
        [f"paper_ncloc_complete_{name}" for name in OUTCOME_COLUMNS]
    ].all(axis=1).astype(int)

    repo_names = sorted(data["repo_name"].unique().tolist(), key=str.casefold)
    repo_ids = {name: index + 1 for index, name in enumerate(repo_names)}
    data["repo_id"] = data["repo_name"].map(repo_ids).astype(int)
    return data


def build_treatment_estimability_audit(panel: pd.DataFrame) -> pd.DataFrame:
    treatment = panel[panel["scope_role"].eq("treatment")].copy()
    rows: list[dict[str, object]] = []
    for repo_name, repo_data in treatment.groupby("repo_name", sort=True):
        event = repo_data["event"].iloc[0]
        for outcome_name in OUTCOME_COLUMNS:
            complete_column = f"paper_ncloc_complete_{outcome_name}"
            complete = repo_data[complete_column].eq(1)
            pre = complete & repo_data["time_to_event"].lt(0)
            post = complete & repo_data["time_to_event"].ge(0)
            rows.append(
                {
                    "repo_name": repo_name,
                    "repo_key": repo_data["repo_key"].iloc[0],
                    "event": event,
                    "outcome": outcome_name,
                    "panel_rows": len(repo_data),
                    "complete_rows": int(complete.sum()),
                    "pre_complete_rows": int(pre.sum()),
                    "post_complete_rows": int(post.sum()),
                    "borusyak_estimable": int(pre.any() and post.any()),
                    "estimability_reason": (
                        "estimable"
                        if pre.any() and post.any()
                        else "no_pre_complete_row"
                        if not pre.any()
                        else "no_post_complete_row"
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_snapshot_manifest(panel: pd.DataFrame) -> pd.DataFrame:
    resolved = panel[panel["snapshot_available"].eq(1)].copy()
    if resolved.empty:
        return pd.DataFrame(
            columns=[
                "manifest_order",
                "repo_snapshot_key",
                "dataset_source",
                "scope_role",
                "repo_name",
                "repo_key",
                "clone_path",
                "latest_commit_effective",
                "repo_month_rows",
                "first_panel_month",
                "last_panel_month",
                "commit_resolution_values",
                "paper_ncloc_nonmissing_rows",
                "paper_ncloc_min",
                "paper_ncloc_max",
            ]
        )

    manifest = (
        resolved.groupby(
            [
                "repo_snapshot_key",
                "dataset_source",
                "scope_role",
                "repo_name",
                "repo_key",
                "clone_path",
                "latest_commit_effective",
            ],
            as_index=False,
        )
        .agg(
            repo_month_rows=("time", "size"),
            first_panel_month=("time", "min"),
            last_panel_month=("time", "max"),
            commit_resolution_values=(
                "commit_resolution",
                lambda values: "|".join(sorted(set(values))),
            ),
            paper_ncloc_nonmissing_rows=(
                "ncloc_paper_sonarqube",
                lambda values: int(values.notna().sum()),
            ),
            paper_ncloc_min=("ncloc_paper_sonarqube", "min"),
            paper_ncloc_max=("ncloc_paper_sonarqube", "max"),
        )
        .sort_values(["dataset_source", "repo_name", "first_panel_month", "latest_commit_effective"])
        .reset_index(drop=True)
    )
    manifest.insert(0, "manifest_order", np.arange(1, len(manifest) + 1))
    return manifest


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logging.info("Wrote %d rows to %s", len(df), path)


def add_qc(
    rows: list[dict[str, object]],
    check_name: str,
    observed: object,
    expected: object,
    status: str,
    note: str = "",
) -> None:
    rows.append(
        {
            "check_name": check_name,
            "status": status,
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def check_expected(
    rows: list[dict[str, object]],
    args: argparse.Namespace,
    check_name: str,
    observed: int,
    arg_name: str,
) -> None:
    expected = expected_value(args, arg_name)
    matches = observed == expected
    status = "pass" if matches else ("fail" if args.strict_expected_counts else "warn")
    add_qc(rows, check_name, observed, expected, status)


def append_summary(
    rows: list[dict[str, object]],
    section: str,
    metric: str,
    value: object,
    note: str = "",
) -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    for path in [args.matching_file, args.treatment_monthly_file, args.control_monthly_file]:
        if not path.is_file():
            raise FileNotFoundError(f"Required input file not found: {path}")
    for path in [args.treatment_clone_dir, args.control_clone_dir]:
        if not path.is_dir():
            raise FileNotFoundError(f"Required clone directory not found: {path}")
    if args.git_timeout_seconds <= 0:
        raise ValueError("git-timeout-seconds must be positive")

    start_period = parse_period(args.start_month, "start-month")
    end_period = parse_period(args.end_month, "end-month")
    cohort_start = parse_period(args.treatment_cohort_start, "treatment-cohort-start")
    cohort_end = parse_period(args.treatment_cohort_end, "treatment-cohort-end")
    if start_period > end_period or cohort_start > cohort_end:
        raise ValueError("Month ranges are invalid")

    logging.info("Reading matching data: %s", args.matching_file)
    matching_raw = pd.read_csv(args.matching_file, low_memory=False)
    treatment_matching = normalize_matching(matching_raw)

    logging.info("Reading treatment monthly data: %s", args.treatment_monthly_file)
    treatment_monthly = normalize_monthly(
        pd.read_csv(args.treatment_monthly_file, low_memory=False), "treatment"
    )
    logging.info("Reading control monthly data: %s", args.control_monthly_file)
    control_monthly = normalize_monthly(
        pd.read_csv(args.control_monthly_file, low_memory=False), "control"
    )

    known_names = build_known_repo_names(matching_raw, treatment_monthly, control_monthly)
    directory_candidates = build_directory_candidates(known_names)

    logging.info("Scanning treatment clones: %s", args.treatment_clone_dir)
    treatment_clone_records = scan_clone_root(
        args.treatment_clone_dir,
        "treatment",
        known_names,
        directory_candidates,
        args.git_timeout_seconds,
    )
    logging.info("Scanning control clones: %s", args.control_clone_dir)
    control_clone_records = scan_clone_root(
        args.control_clone_dir,
        "control",
        known_names,
        directory_candidates,
        args.git_timeout_seconds,
    )
    treatment_clone_map = index_clone_records(treatment_clone_records, "treatment")
    control_clone_map = index_clone_records(control_clone_records, "control")

    matching_by_key = treatment_matching.set_index("repo_key", drop=False)
    local_treatment_keys = set(treatment_clone_map)
    matched_treatment_keys = local_treatment_keys & set(matching_by_key.index)
    extra_treatment_keys = local_treatment_keys - set(matching_by_key.index)

    treatment_adoptions = first_adoption_map(treatment_monthly)
    primary_treatment_keys = {
        key
        for key in matched_treatment_keys
        if key in treatment_adoptions
        and cohort_start <= treatment_adoptions[key] <= cohort_end
    }

    pair_rows: list[dict[str, object]] = []
    for treatment_key in sorted(matched_treatment_keys):
        match_row = matching_by_key.loc[treatment_key]
        if isinstance(match_row, pd.DataFrame):
            match_row = match_row.iloc[0]
        treatment_name = clean_text(match_row["repo_name"])
        event_period = treatment_adoptions.get(treatment_key)
        event_valid = int(treatment_key in primary_treatment_keys)
        for rank, column in enumerate(CONTROL_COLUMNS, start=1):
            control_name = clean_text(match_row[column])
            control_key_value = repo_key(control_name)
            control_clone = control_clone_map.get(control_key_value)
            control_available = int(control_clone is not None)
            primary_pair = int(event_valid == 1 and control_available == 1)
            if not event_valid:
                status = "treatment_not_in_primary_event_cohort"
            elif not control_name:
                status = "matching_slot_blank"
            elif not control_available:
                status = "control_clone_unavailable"
            else:
                status = "aligned_available"
            pair_rows.append(
                {
                    "treatment_repo": treatment_name,
                    "treatment_key": treatment_key,
                    "treatment_clone_path": treatment_clone_map[treatment_key].clone_path,
                    "matched_period": match_row["matched_period"],
                    "propensity_score": match_row["propensity_score"],
                    "treatment_event": "" if event_period is None else str(event_period),
                    "treatment_event_valid": event_valid,
                    "control_rank": rank,
                    "control_repo": control_name,
                    "control_key": control_key_value,
                    "control_clone_available": control_available,
                    "control_clone_path": "" if control_clone is None else control_clone.clone_path,
                    "primary_pair_eligible": primary_pair,
                    "pair_status": status,
                }
            )
    pair_audit = pd.DataFrame(pair_rows)

    primary_pair_audit = pair_audit[pair_audit["treatment_event_valid"].eq(1)].copy()
    candidate_control_keys = {
        key for key in primary_pair_audit["control_key"] if clean_text(key)
    }
    available_control_keys = set(
        primary_pair_audit.loc[
            primary_pair_audit["control_clone_available"].eq(1), "control_key"
        ]
    )

    treatment_display = {
        key: clean_text(matching_by_key.loc[key, "repo_name"])
        for key in primary_treatment_keys
    }
    control_display = (
        primary_pair_audit.drop_duplicates("control_key")
        .set_index("control_key")["control_repo"]
        .to_dict()
    )

    treatment_window = treatment_monthly[
        treatment_monthly["repo_key"].isin(primary_treatment_keys)
        & treatment_monthly["time_period"].between(start_period, end_period)
    ].copy()
    treatment_window["scope_role"] = "treatment"
    treatment_window["event_period"] = treatment_window["repo_key"].map(treatment_adoptions)
    treatment_window["repo_name"] = treatment_window["repo_key"].map(treatment_display)

    control_adoptions = first_adoption_map(control_monthly)
    control_window_all = control_monthly[
        control_monthly["repo_key"].isin(available_control_keys)
        & control_monthly["time_period"].between(start_period, end_period)
    ].copy()
    control_window_all["control_event_period"] = control_window_all["repo_key"].map(
        control_adoptions
    )
    control_window_all["control_post_adoption_row"] = (
        control_window_all["control_event_period"].notna()
        & (control_window_all["time_period"] >= control_window_all["control_event_period"])
    ).astype(int)
    control_window = control_window_all[
        control_window_all["control_post_adoption_row"].eq(0)
    ].copy()
    control_window["scope_role"] = "control"
    control_window["event_period"] = pd.NaT
    control_window["repo_name"] = control_window["repo_key"].map(control_display)

    panel = pd.concat([treatment_window, control_window], ignore_index=True, sort=False)
    panel = panel.sort_values(["dataset_source", "repo_name", "time_period"]).reset_index(drop=True)

    duplicated_panel = panel.duplicated(["dataset_source", "repo_key", "month"], keep=False)
    if duplicated_panel.any():
        sample = panel.loc[
            duplicated_panel, ["dataset_source", "repo_name", "month"]
        ].head(20)
        raise ValueError(
            "Primary panel contains duplicate repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )

    clone_map: dict[tuple[str, str], CloneRecord] = {}
    for key in primary_treatment_keys:
        clone_map[("treatment", key)] = treatment_clone_map[key]
    for key in available_control_keys:
        clone_map[("control", key)] = control_clone_map[key]

    panel["clone_path"] = panel.apply(
        lambda row: clone_map[(row["dataset_source"], row["repo_key"])].clone_path,
        axis=1,
    )
    panel["clone_exists"] = 1
    panel["is_git_repository"] = 1

    treatment_slot_counts = (
        pair_audit[pair_audit["treatment_event_valid"].eq(1)]
        .groupby("treatment_key")
        .agg(
            original_control_slots=("control_rank", "size"),
            available_control_slots=("control_clone_available", "sum"),
        )
    )
    control_reuse = (
        primary_pair_audit.groupby("control_key")
        .agg(
            matched_treatment_count=("treatment_key", "nunique"),
            matched_slot_count=("control_rank", "size"),
        )
    )
    panel["original_control_slots"] = 0
    panel["available_control_slots"] = 0
    treatment_mask = panel["scope_role"].eq("treatment")
    panel.loc[treatment_mask, "original_control_slots"] = panel.loc[
        treatment_mask, "repo_key"
    ].map(treatment_slot_counts["original_control_slots"]).fillna(0).astype(int)
    panel.loc[treatment_mask, "available_control_slots"] = panel.loc[
        treatment_mask, "repo_key"
    ].map(treatment_slot_counts["available_control_slots"]).fillna(0).astype(int)
    panel["matched_treatment_count"] = 0
    control_mask = panel["scope_role"].eq("control")
    panel.loc[control_mask, "matched_treatment_count"] = panel.loc[
        control_mask, "repo_key"
    ].map(control_reuse["matched_treatment_count"]).fillna(0).astype(int)

    panel = add_analysis_columns(panel, start_period)
    panel = add_commit_resolution(panel, clone_map, args.git_timeout_seconds)

    control_adoption_rows: list[dict[str, object]] = []
    for control_key_value in sorted(available_control_keys):
        control_name = control_display.get(control_key_value, control_key_value)
        event_period = control_adoptions.get(control_key_value)
        rows_before = int(
            (
                control_window_all["repo_key"].eq(control_key_value)
                & control_window_all["control_post_adoption_row"].eq(0)
            ).sum()
        )
        rows_censored = int(
            (
                control_window_all["repo_key"].eq(control_key_value)
                & control_window_all["control_post_adoption_row"].eq(1)
            ).sum()
        )
        control_adoption_rows.append(
            {
                "control_repo": control_name,
                "control_key": control_key_value,
                "control_clone_path": control_clone_map[control_key_value].clone_path,
                "first_cursor_adoption": "" if event_period is None else str(event_period),
                "control_has_adoption_event": int(event_period is not None),
                "pre_adoption_rows_retained": rows_before,
                "post_adoption_rows_censored": rows_censored,
                "monthly_rows_in_window": rows_before + rows_censored,
                "appears_in_primary_panel": int(rows_before > 0),
            }
        )
    control_adoption_audit = pd.DataFrame(control_adoption_rows)

    treatment_estimability = build_treatment_estimability_audit(panel)
    snapshot_manifest = build_snapshot_manifest(panel)
    unresolved = panel[panel["snapshot_available"].eq(0)].copy()

    local_treatment_count = len(treatment_clone_records)
    matched_treatment_count = len(matched_treatment_keys)
    extra_treatment_count = len(extra_treatment_keys)
    primary_treatment_count = len(primary_treatment_keys)
    candidate_control_count = len(candidate_control_keys)
    available_control_count = len(available_control_keys)
    primary_pair_slots = int(primary_pair_audit["control_clone_available"].sum())
    treatment_panel_rows = int(panel["scope_role"].eq("treatment").sum())
    control_panel_rows = int(panel["scope_role"].eq("control").sum())
    panel_repositories = panel["repo_key"].nunique()

    clone_audit_rows: list[dict[str, object]] = []
    for record in [*treatment_clone_records, *control_clone_records]:
        in_matching_treatment = int(record.repo_key in set(matching_by_key.index))
        is_primary_treatment = int(record.repo_key in primary_treatment_keys)
        is_candidate_control = int(record.repo_key in candidate_control_keys)
        is_available_primary_control = int(record.repo_key in available_control_keys)
        if record.clone_role == "treatment" and not in_matching_treatment:
            exclusion = "extra_treatment_outside_matching_scope"
        elif record.clone_role == "treatment" and not is_primary_treatment:
            exclusion = "treatment_missing_or_outside_event_cohort"
        elif record.clone_role == "control" and not is_candidate_control:
            exclusion = "control_not_matched_to_primary_treatments"
        elif record.is_git_repository != 1:
            exclusion = "invalid_git_repository"
        elif record.identity_status != "resolved":
            exclusion = "clone_identity_unresolved"
        else:
            exclusion = ""
        clone_audit_rows.append(
            {
                **record.__dict__,
                "in_matching_treatment_scope": in_matching_treatment,
                "is_primary_treatment": is_primary_treatment,
                "is_candidate_control": is_candidate_control,
                "is_available_primary_control": is_available_primary_control,
                "primary_scope_included": int(
                    is_primary_treatment == 1 or is_available_primary_control == 1
                ),
                "exclusion_reason": exclusion,
            }
        )

    missing_control_keys = candidate_control_keys - set(control_clone_map)
    for key in sorted(missing_control_keys):
        clone_audit_rows.append(
            {
                "clone_role": "control",
                "repo_name": control_display.get(key, key),
                "repo_key": key,
                "clone_dir_name": "",
                "clone_path": "",
                "clone_found": 0,
                "is_git_repository": 0,
                "origin_url": "",
                "identity_source": "expected_from_matching",
                "identity_status": "missing",
                "in_matching_treatment_scope": 0,
                "is_primary_treatment": 0,
                "is_candidate_control": 1,
                "is_available_primary_control": 0,
                "primary_scope_included": 0,
                "exclusion_reason": "control_clone_unavailable",
            }
        )
    clone_audit = pd.DataFrame(clone_audit_rows)

    qc_rows: list[dict[str, object]] = []
    check_expected(
        qc_rows, args, "local_treatment_clone_directories", local_treatment_count,
        "expected_local_treatment_clones"
    )
    check_expected(
        qc_rows, args, "matched_treatment_clones", matched_treatment_count,
        "expected_matched_treatment_clones"
    )
    check_expected(
        qc_rows, args, "extra_treatment_clones", extra_treatment_count,
        "expected_extra_treatment_clones"
    )
    check_expected(
        qc_rows, args, "primary_treatment_repositories", primary_treatment_count,
        "expected_primary_treatment_repos"
    )
    check_expected(
        qc_rows, args, "candidate_control_repositories", candidate_control_count,
        "expected_candidate_control_repos"
    )
    check_expected(
        qc_rows, args, "available_candidate_control_repositories", available_control_count,
        "expected_available_control_repos"
    )
    check_expected(
        qc_rows, args, "available_primary_matching_slots", primary_pair_slots,
        "expected_primary_pair_slots"
    )
    check_expected(
        qc_rows, args, "panel_rows", len(panel), "expected_panel_rows"
    )
    check_expected(
        qc_rows, args, "treatment_panel_rows", treatment_panel_rows,
        "expected_treatment_panel_rows"
    )
    check_expected(
        qc_rows, args, "control_panel_rows", control_panel_rows,
        "expected_control_panel_rows"
    )
    check_expected(
        qc_rows, args, "panel_repositories", panel_repositories,
        "expected_panel_repositories"
    )

    hard_checks = {
        "duplicate_panel_repo_month_rows": int(
            panel.duplicated(["dataset_source", "repo_key", "time"]).sum()
        ),
        "control_post_adoption_rows_retained": int(
            (
                panel["scope_role"].eq("control")
                & panel["repo_key"].map(control_adoptions).notna()
                & (
                    panel["time_period"]
                    >= panel["repo_key"].map(control_adoptions)
                )
            ).sum()
        ),
        "treatment_event_outside_cohort": int(
            (
                panel["scope_role"].eq("treatment")
                & ~panel["event_period"].between(cohort_start, cohort_end)
            ).sum()
        ),
        "negative_paper_ncloc": int(panel["ncloc_paper_sonarqube"].lt(0).sum()),
        "duplicate_snapshot_keys": int(
            snapshot_manifest["repo_snapshot_key"].duplicated().sum()
        ),
        "snapshot_manifest_row_count_mismatch": int(
            len(snapshot_manifest)
            != panel.loc[panel["snapshot_available"].eq(1), "repo_snapshot_key"].nunique()
        ),
        "future_effective_commit_rows": int(
            panel["effective_commit_after_month_end"].sum()
        ),
    }
    for name, observed in hard_checks.items():
        add_qc(qc_rows, name, observed, 0, "pass" if observed == 0 else "fail")

    warning_checks = {
        "unavailable_candidate_control_repositories": candidate_control_count - available_control_count,
        "candidate_controls_without_window_rows": available_control_count - control_window_all["repo_key"].nunique(),
        "paper_ncloc_missing_rows": int(panel["ncloc_paper_sonarqube"].isna().sum()),
        "snapshot_unresolved_rows": len(unresolved),
        "snapshot_unresolved_repositories": unresolved["repo_key"].nunique(),
        "controls_with_adoption_event": int(
            control_adoption_audit["control_has_adoption_event"].sum()
        ),
        "control_post_adoption_rows_censored": int(
            control_adoption_audit["post_adoption_rows_censored"].sum()
        ),
        "source_commit_candidates_after_month_end": int(
            panel["original_commit_validation_status"].eq("commit_after_month_end").sum()
            + panel["prior_commit_validation_status"].eq("commit_after_month_end").sum()
            + panel["git_fallback_validation_status"].eq("commit_after_month_end").sum()
        ),
    }
    for name, observed in warning_checks.items():
        add_qc(
            qc_rows,
            name,
            observed,
            "diagnostic",
            "warn" if observed else "pass",
            "Recorded for sample and snapshot provenance; not silently imputed.",
        )

    qc = pd.DataFrame(qc_rows)
    hard_failures = int(qc["status"].eq("fail").sum())
    warnings = int(qc["status"].eq("warn").sum())

    summary_rows: list[dict[str, object]] = []
    append_summary(summary_rows, "implementation", "version", "v1")
    append_summary(summary_rows, "definition", "analysis_scope", "clone_available_all_language_repository_month")
    append_summary(summary_rows, "definition", "paper_ncloc_metric", "ncloc_paper_sonarqube")
    append_summary(summary_rows, "definition", "treatment_rule", "absorbing_from_first_cursor_adoption")
    append_summary(summary_rows, "definition", "control_rule", "matched_available_controls_pre_adoption_only")
    append_summary(summary_rows, "definition", "analysis_window", f"{start_period}:{end_period}")
    append_summary(summary_rows, "definition", "treatment_cohort_window", f"{cohort_start}:{cohort_end}")
    append_summary(summary_rows, "clone_scope", "local_treatment_clone_directories", local_treatment_count)
    append_summary(summary_rows, "clone_scope", "matched_treatment_clones", matched_treatment_count)
    append_summary(summary_rows, "clone_scope", "extra_treatment_clones", extra_treatment_count)
    append_summary(summary_rows, "clone_scope", "primary_treatment_repositories", primary_treatment_count)
    append_summary(summary_rows, "clone_scope", "candidate_control_repositories", candidate_control_count)
    append_summary(summary_rows, "clone_scope", "available_candidate_control_repositories", available_control_count)
    append_summary(summary_rows, "clone_scope", "available_primary_matching_slots", primary_pair_slots)
    append_summary(summary_rows, "panel", "rows", len(panel))
    append_summary(summary_rows, "panel", "repositories", panel_repositories)
    append_summary(summary_rows, "panel", "treatment_rows", treatment_panel_rows)
    append_summary(summary_rows, "panel", "control_rows", control_panel_rows)
    append_summary(summary_rows, "panel", "treatment_repositories", panel.loc[panel["scope_role"].eq("treatment"), "repo_key"].nunique())
    append_summary(summary_rows, "panel", "control_repositories", panel.loc[panel["scope_role"].eq("control"), "repo_key"].nunique())
    append_summary(summary_rows, "panel", "paper_ncloc_missing_rows", int(panel["ncloc_paper_sonarqube"].isna().sum()))
    for outcome_name in OUTCOME_COLUMNS:
        append_summary(
            summary_rows,
            "complete_case",
            f"paper_ncloc_complete_{outcome_name}_rows",
            int(panel[f"paper_ncloc_complete_{outcome_name}"].sum()),
        )
        append_summary(
            summary_rows,
            "estimability",
            f"paper_ncloc_{outcome_name}_estimable_treatments",
            int(
                treatment_estimability.loc[
                    treatment_estimability["outcome"].eq(outcome_name),
                    "borusyak_estimable",
                ].sum()
            ),
        )
    append_summary(summary_rows, "snapshot", "resolved_repo_month_rows", int(panel["snapshot_available"].sum()))
    append_summary(summary_rows, "snapshot", "unresolved_repo_month_rows", len(unresolved))
    append_summary(summary_rows, "snapshot", "unique_resolved_snapshots", len(snapshot_manifest))
    append_summary(summary_rows, "control_adoption", "controls_with_event", int(control_adoption_audit["control_has_adoption_event"].sum()))
    append_summary(summary_rows, "control_adoption", "post_adoption_rows_censored", int(control_adoption_audit["post_adoption_rows_censored"].sum()))
    append_summary(summary_rows, "qc", "hard_failures", hard_failures)
    append_summary(summary_rows, "qc", "warnings", warnings)
    summary = pd.DataFrame(summary_rows)

    output_panel = panel.drop(columns=["time_period", "event_period", "control_event_period"], errors="ignore")
    preferred_columns = [
        "repo_id",
        "repo_name",
        "repo_key",
        "dataset_source",
        "scope_role",
        "time",
        "time_index",
        "time_yyyymm",
        "event",
        "event_index",
        "event_yyyymm",
        "treatment_group",
        "treated_absorbing",
        "post_event",
        "time_to_event",
        "lead_6",
        "lead_5",
        "lead_4",
        "lead_3",
        "lead_2",
        "lead_1",
        "lag_0",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_5",
        "lag_6",
        "cursor",
        "cursor_flag",
        "commits",
        "log_commits",
        "lines_added",
        "log_lines_added",
        "lines_removed",
        "contributors",
        "log_contributors",
        "stars",
        "log_stars",
        "issues",
        "log_issues",
        "issue_comments",
        "age",
        "log_age",
        "ncloc",
        "ncloc_paper_sonarqube",
        "ncloc_paper_source",
        "bugs",
        "vulnerabilities",
        "code_smells",
        "quality_warnings",
        "log_quality_warnings",
        "duplicated_lines_density",
        "log_duplicated_lines_density",
        "comment_lines_density",
        "log_comment_lines_density",
        "cognitive_complexity",
        "log_cognitive_complexity",
        "technical_debt",
        "num_dependencies_total",
        "num_vulnerable_dependencies",
        "average_technical_lag",
        "latest_commit_original",
        "latest_commit_effective",
        "commit_resolution",
        "commit_resolution_source_month",
        "months_since_observed_commit",
        "original_commit_validation_status",
        "prior_commit_validation_status",
        "git_fallback_validation_status",
        "effective_commit_timestamp_utc",
        "effective_commit_after_month_end",
        "snapshot_available",
        "repo_snapshot_key",
        "clone_path",
        "clone_exists",
        "is_git_repository",
        "original_control_slots",
        "available_control_slots",
        "matched_treatment_count",
    ]
    preferred_columns += [
        f"paper_ncloc_complete_{name}" for name in OUTCOME_COLUMNS
    ]
    preferred_columns += ["paper_ncloc_complete_all_outcomes"]
    remaining = [column for column in output_panel.columns if column not in preferred_columns]
    output_panel = output_panel[[column for column in preferred_columns if column in output_panel.columns] + remaining]

    write_csv(output_panel, args.panel_output)
    write_csv(snapshot_manifest, args.snapshot_manifest_output)
    write_csv(clone_audit, args.clone_audit_output)
    write_csv(pair_audit, args.pair_audit_output)
    write_csv(control_adoption_audit, args.control_adoption_audit_output)
    write_csv(treatment_estimability, args.treatment_estimability_audit_output)
    write_csv(unresolved.drop(columns=["time_period", "event_period", "control_event_period"], errors="ignore"), args.unresolved_output)
    write_csv(qc, args.qc_output)
    write_csv(summary, args.summary_output)

    logging.info(
        "Completed run-x-c01-v1: panel=%d rows; treatments=%d; controls=%d; "
        "resolved snapshots=%d; unresolved rows=%d; QC failures=%d; warnings=%d",
        len(panel),
        panel.loc[panel["scope_role"].eq("treatment"), "repo_key"].nunique(),
        panel.loc[panel["scope_role"].eq("control"), "repo_key"].nunique(),
        len(snapshot_manifest),
        len(unresolved),
        hard_failures,
        warnings,
    )

    if hard_failures:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("run-x-c01-v1 failed: %s", exc)
        raise
