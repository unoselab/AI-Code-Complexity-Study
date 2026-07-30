#!/usr/bin/env python3
"""Rank local replacement controls for HelpingAI/Webscout.

This script performs a design-stage rematching sensitivity for the six Python
repositories that originally used HelpingAI/Webscout as their third matched
control. It does not run Difference-in-Differences and it does not inspect any
post-adoption AGC outcome.

Two propensity-score specifications are fit for the 2024-10 Python cohort:

P0
    The paper-derived pre-adoption repository features: age at t-1, six monthly
    lags for users involved, stars, forks, releases, pull requests, issues,
    comments, and total events, plus the cumulative history before lag 6.

P1
    P0 plus Python-only NCLOC level, six-month log change, and six-month log
    mean over 2024-04 through 2024-09.

The candidate pool is restricted to repositories available under the local
control clone root. The script produces per-treatment rankings and a common-
donor ranking. The common-donor ranking minimizes the worst propensity-score
distance across the six target treatments before considering mean distance and
covariate distance.

No candidate is selected using 2025-04 or 2025-06 AGC outcomes. Those outcomes
must remain sealed until a donor is frozen for the next experiment.
"""

from __future__ import annotations

import argparse
import configparser
import json
import math
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TARGET_CONTROL = "HelpingAI/Webscout"
TARGET_COHORT = "2024-10"
PRE_MONTHS = ("2024-04", "2024-05", "2024-06", "2024-07", "2024-08", "2024-09")
LAG_MONTHS = {
    1: "2024-09",
    2: "2024-08",
    3: "2024-07",
    4: "2024-06",
    5: "2024-05",
    6: "2024-04",
}
HISTORY_END_MONTH = "2024-03"

EXPECTED_TARGET_TREATMENTS = (
    "Elevate-Code/better-voice-typing",
    "PiotrCzapla/smart_dictation",
    "TheSethRose/Agent-Chat",
    "VRSEN/agency-voice-interface",
    "codingforentrepreneurs/Cursor-Django",
    "matebenyovszky/healing-agent",
)

PAPER_METRICS = (
    "users_involved",
    "stars",
    "forks",
    "releases",
    "pull_requests",
    "issues",
    "comments",
    "total_events",
)

REPO_ALIASES = (
    "repo_name",
    "repository",
    "repo",
    "repository_name",
    "name_with_owner",
    "full_name",
)
MONTH_ALIASES = (
    "time",
    "month",
    "year_month",
    "event_month",
    "created_month",
    "date",
    "created_at",
)
AGE_ALIASES = (
    "age",
    "repo_age",
    "age_days",
    "repository_age",
    "repo_age_days",
)
LANGUAGE_ALIASES = (
    "repo_primary_language",
    "primary_language",
    "language",
)
EVENT_MONTH_ALIASES = (
    "event_month",
    "event",
    "adoption_month",
    "cursor_adoption_month",
)
GROUP_ALIASES = (
    "group",
    "dataset_source",
    "is_treatment",
    "treatment",
)
EVENT_TYPE_ALIASES = (
    "event_type",
    "type",
)
ACTOR_ALIASES = (
    "actor_id",
    "actor_login",
    "user_id",
    "user_login",
    "actor",
    "user",
)
NCLOC_ALIASES = (
    "ncloc_python_snapshot",
    "ncloc_python",
    "python_ncloc",
    "ncloc",
)
CLONE_PATH_ALIASES = (
    "clone_path",
    "repo_path",
    "local_path",
    "path",
)

METRIC_ALIASES: Mapping[str, tuple[str, ...]] = {
    "users_involved": (
        "users_involved",
        "active_users",
        "users",
        "contributors_active",
        "num_users",
    ),
    "stars": ("stars", "watch", "watches", "watch_events", "star_events"),
    "forks": ("forks", "fork_events"),
    "releases": ("releases", "release_events"),
    "pull_requests": (
        "pull_requests",
        "pull_request",
        "prs",
        "pr_events",
        "pullrequestevents",
    ),
    "issues": ("issues", "issue_events"),
    "comments": (
        "comments",
        "issue_comments",
        "comment_events",
        "all_comments",
    ),
    "total_events": ("total_events", "events", "event_count", "num_events"),
}

OUTPUT_PREFIX = "webscout_local_control_rematching"


@dataclass(frozen=True)
class InputPaths:
    target_pair_manifest: Path
    treatment_sample: Path
    candidate_feature_csv: Path
    treatment_feature_csv: Path | None
    treatment_events_csv: Path | None
    treatment_monthly_csv: Path | None
    original_matching_csv: Path | None
    local_control_manifest: Path | None
    control_clone_root: Path
    treatment_ncloc_csv: Path
    control_ncloc_csv: Path
    output_dir: Path


@dataclass
class ModelResult:
    specification: str
    feature_columns: list[str]
    pipeline: Pipeline
    scored: pd.DataFrame
    diagnostics: dict[str, object]
    coefficients: pd.DataFrame
    training_means: pd.Series
    training_stds: pd.Series


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rank local replacement controls for HelpingAI/Webscout using the "
            "paper-derived PSM features with and without Python-only NCLOC."
        )
    )
    parser.add_argument("--target-pair-manifest", type=Path)
    parser.add_argument("--treatment-sample", type=Path)
    parser.add_argument("--candidate-feature-csv", type=Path)
    parser.add_argument("--treatment-feature-csv", type=Path)
    parser.add_argument("--treatment-events-csv", type=Path)
    parser.add_argument("--treatment-monthly-csv", type=Path)
    parser.add_argument("--original-matching-csv", type=Path)
    parser.add_argument("--local-control-manifest", type=Path)
    parser.add_argument("--control-clone-root", type=Path)
    parser.add_argument("--treatment-ncloc-csv", type=Path)
    parser.add_argument("--control-ncloc-csv", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--target-control", default=TARGET_CONTROL)
    parser.add_argument("--target-cohort", default=TARGET_COHORT)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--random-state", type=int, default=20260730)
    parser.add_argument("--min-local-candidates", type=int, default=20)
    parser.add_argument("--min-python-ncloc-months", type=int, default=6)
    parser.add_argument(
        "--allow-ncloc-partial-window",
        action="store_true",
        help=(
            "Allow candidates with fewer than six observed NCLOC months. Missing "
            "months remain missing and are median-imputed inside the P1 model."
        ),
    )
    parser.add_argument(
        "--skip-frozen-target-checks",
        action="store_true",
        help="Skip the exact six-treatment frozen manifest check.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a synthetic end-to-end self-test and exit.",
    )
    return parser.parse_args()


def require_file(path: Path | None, label: str, optional: bool = False) -> None:
    if path is None:
        if optional:
            return
        raise ValueError(f"{label} path was not provided.")
    if not path.is_file():
        if optional:
            return
        raise FileNotFoundError(f"{label} not found: {path}")


def find_column(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in columns}
    for alias in aliases:
        match = lookup.get(alias.lower())
        if match is not None:
            return match
    return None


def normalize_repo_name(value: object) -> str:
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    text = text.replace("git@github.com:", "")
    text = text.replace("https://github.com/", "")
    text = text.replace("http://github.com/", "")
    text = text.removesuffix(".git").strip("/")
    return text


def normalize_repo_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_repo_name)


def normalize_month_value(value: object) -> str:
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "nat", "null"}:
        return ""
    match = re.search(r"(20\d{2})[-_/]?(0[1-9]|1[0-2])", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text[:7]


def normalize_month_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_month_value)


def safe_numeric(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.replace({"": np.nan, "nan": np.nan, "None": np.nan})
    return pd.to_numeric(cleaned, errors="coerce")


def read_csv_header(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def read_filtered_csv(
    path: Path,
    wanted_repos: set[str] | None,
    chunksize: int,
    label: str,
) -> pd.DataFrame:
    columns = read_csv_header(path)
    repo_col = find_column(columns, REPO_ALIASES)
    if repo_col is None:
        raise ValueError(f"{label} has no recognizable repository column: {path}")

    pieces: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, dtype=str, low_memory=False, chunksize=chunksize):
        chunk[repo_col] = normalize_repo_series(chunk[repo_col])
        chunk = chunk[chunk[repo_col].ne("")]
        if wanted_repos is not None:
            chunk = chunk[chunk[repo_col].isin(wanted_repos)]
        if not chunk.empty:
            pieces.append(chunk)

    if not pieces:
        return pd.DataFrame(columns=columns)
    result = pd.concat(pieces, ignore_index=True)
    if repo_col != "repo_name":
        result = result.rename(columns={repo_col: "repo_name"})
    return result


def parse_remote_repo_from_config(repo_dir: Path) -> str:
    config_path = repo_dir / ".git" / "config"
    if not config_path.is_file():
        return ""
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeError):
        return ""
    section = 'remote "origin"'
    if not parser.has_section(section):
        return ""
    return normalize_repo_name(parser.get(section, "url", fallback=""))


def discover_local_controls(
    clone_root: Path,
    manifest_path: Path | None,
) -> pd.DataFrame:
    if not clone_root.is_dir():
        raise FileNotFoundError(f"Control clone root not found: {clone_root}")

    manifest = pd.DataFrame()
    if manifest_path is not None and manifest_path.is_file():
        manifest = pd.read_csv(manifest_path, dtype=str, low_memory=False)
        repo_col = find_column(manifest.columns, REPO_ALIASES)
        if repo_col is None:
            raise ValueError(
                f"Local control manifest has no recognizable repository column: {manifest_path}"
            )
        manifest[repo_col] = normalize_repo_series(manifest[repo_col])
        manifest = manifest[manifest[repo_col].ne("")].copy()
        if repo_col != "repo_name":
            manifest = manifest.rename(columns={repo_col: "repo_name"})
    else:
        manifest = pd.DataFrame(columns=["repo_name"])

    path_col = find_column(manifest.columns, CLONE_PATH_ALIASES)
    discovered_rows: list[dict[str, object]] = []

    for repo_dir in sorted(path for path in clone_root.iterdir() if path.is_dir()):
        remote_repo = parse_remote_repo_from_config(repo_dir)
        discovered_rows.append(
            {
                "repo_name": remote_repo,
                "clone_path": str(repo_dir.resolve()),
                "clone_dir_name": repo_dir.name,
                "repo_name_from_remote": bool(remote_repo),
            }
        )

    discovered = pd.DataFrame(discovered_rows)
    if discovered.empty:
        raise ValueError(f"No local control directories found under: {clone_root}")

    if not manifest.empty:
        rows: list[dict[str, object]] = []
        discovered_by_repo = {
            row.repo_name: row for row in discovered.itertuples(index=False) if row.repo_name
        }
        discovered_by_dir = {row.clone_dir_name: row for row in discovered.itertuples(index=False)}

        for row in manifest.itertuples(index=False):
            repo_name = normalize_repo_name(getattr(row, "repo_name"))
            explicit_path = ""
            if path_col is not None:
                explicit_path = str(getattr(row, path_col, "") or "").strip()
            candidate_path = Path(explicit_path) if explicit_path else clone_root / repo_name.replace("/", "_")
            found = discovered_by_repo.get(repo_name)
            if found is None:
                found = discovered_by_dir.get(candidate_path.name)
            rows.append(
                {
                    "repo_name": repo_name,
                    "clone_path": str(candidate_path.resolve()) if candidate_path.exists() else "",
                    "clone_dir_name": candidate_path.name,
                    "repo_name_from_remote": bool(found and found.repo_name_from_remote),
                    "local_clone_exists": bool(candidate_path.is_dir() or found is not None),
                }
            )
        local = pd.DataFrame(rows)
        local["listed_in_manifest"] = True

        # Search the complete local clone root, not only repositories listed in
        # the optional prior-pipeline manifest. This keeps the manifest useful
        # for provenance while allowing newly cloned or previously unmatched
        # controls to enter the rematching candidate pool.
        extra_local = discovered[discovered["repo_name"].ne("")].copy()
        extra_local = extra_local[~extra_local["repo_name"].isin(set(local["repo_name"]))]
        if not extra_local.empty:
            extra_local["local_clone_exists"] = True
            extra_local["listed_in_manifest"] = False
            local = pd.concat([local, extra_local], ignore_index=True, sort=False)
    else:
        local = discovered.rename(columns={"repo_name_from_remote": "repo_name_from_remote"}).copy()
        local["local_clone_exists"] = local["repo_name"].ne("")
        local["listed_in_manifest"] = False

    local = local[local["repo_name"].ne("")].copy()
    local = local.sort_values("repo_name").drop_duplicates("repo_name", keep="first")
    local = local.reset_index(drop=True)
    return local


def load_target_treatments(
    manifest_path: Path,
    target_control: str,
    skip_frozen_checks: bool,
) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path, dtype=str, low_memory=False)
    treatment_col = find_column(manifest.columns, ("treatment_repo", "repo_name"))
    control_col = find_column(manifest.columns, ("control_repo", "matched_control"))
    rank_col = find_column(manifest.columns, ("control_rank", "rank"))
    if treatment_col is None or control_col is None:
        raise ValueError(
            "Target pair manifest must contain treatment_repo and control_repo columns."
        )

    manifest[treatment_col] = normalize_repo_series(manifest[treatment_col])
    manifest[control_col] = normalize_repo_series(manifest[control_col])
    target = manifest[manifest[control_col].eq(target_control)].copy()
    if target.empty:
        raise ValueError(f"No pairs found for target control: {target_control}")

    output = pd.DataFrame(
        {
            "treatment_repo": target[treatment_col],
            "control_repo": target[control_col],
            "control_rank": (
                safe_numeric(target[rank_col]) if rank_col is not None else np.nan
            ),
        }
    )
    output = output.drop_duplicates(["treatment_repo", "control_repo"]).sort_values(
        "treatment_repo"
    )
    output = output.reset_index(drop=True)

    if not skip_frozen_checks:
        actual = tuple(output["treatment_repo"].tolist())
        expected = tuple(sorted(EXPECTED_TARGET_TREATMENTS))
        if actual != expected:
            raise ValueError(
                "Frozen Webscout treatment manifest mismatch. "
                f"Expected {expected}, found {actual}."
            )
        if len(output) != 6:
            raise ValueError(f"Expected 6 Webscout treatment pairs, found {len(output)}.")
        if output["control_rank"].notna().any() and not output["control_rank"].dropna().eq(3).all():
            raise ValueError("Expected Webscout to be control rank 3 for all six treatments.")
    return output


def load_treatment_cohort(
    treatment_sample_path: Path,
    target_cohort: str,
    target_treatments: set[str],
) -> pd.DataFrame:
    sample = pd.read_csv(treatment_sample_path, dtype=str, low_memory=False)
    repo_col = find_column(sample.columns, REPO_ALIASES)
    event_col = find_column(sample.columns, EVENT_MONTH_ALIASES)
    language_col = find_column(sample.columns, LANGUAGE_ALIASES)
    if repo_col is None or event_col is None:
        raise ValueError(
            "Treatment sample must contain repository and adoption/event month columns."
        )
    sample[repo_col] = normalize_repo_series(sample[repo_col])
    sample[event_col] = normalize_month_series(sample[event_col])
    cohort = sample[sample[event_col].eq(target_cohort)].copy()
    if language_col is not None:
        language = cohort[language_col].astype(str).str.strip().str.lower()
        python_mask = language.eq("python") | language.eq("") | language.eq("nan")
        cohort = cohort[python_mask].copy()
    cohort = cohort[cohort[repo_col].ne("")].drop_duplicates(repo_col)
    cohort = cohort.rename(columns={repo_col: "repo_name", event_col: "event_month"})
    missing_targets = sorted(target_treatments - set(cohort["repo_name"]))
    if missing_targets:
        raise ValueError(
            "Target Webscout treatments are missing from the 2024-10 Python cohort: "
            + ", ".join(missing_targets)
        )
    return cohort.sort_values("repo_name").reset_index(drop=True)


def canonical_paper_feature_columns() -> list[str]:
    columns = ["age_lag1"]
    for metric in PAPER_METRICS:
        columns.extend(f"{metric}_lag{lag}" for lag in range(1, 7))
        columns.append(f"{metric}_history")
    return columns


def canonical_ncloc_feature_columns() -> list[str]:
    return [
        "python_ncloc_log_level_lag1",
        "python_ncloc_log_change_6m",
        "python_ncloc_log_mean_6m",
    ]


def match_wide_feature_column(columns: Sequence[str], canonical: str) -> str | None:
    normalized = {re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_"): str(c) for c in columns}
    if canonical in normalized:
        return normalized[canonical]

    if canonical == "age_lag1":
        candidates = (
            "age_lag1",
            "repo_age_lag1",
            "age_t_1",
            "age_1",
            "age",
            "repo_age",
        )
        for candidate in candidates:
            if candidate in normalized:
                return normalized[candidate]
        return None

    match = re.fullmatch(r"([a-z_]+)_(lag([1-6])|history)", canonical)
    if not match:
        return None
    metric = match.group(1)
    suffix = match.group(2)
    aliases = METRIC_ALIASES.get(metric, (metric,))

    candidate_norms: list[str] = []
    if suffix == "history":
        for alias in aliases:
            candidate_norms.extend(
                [
                    f"{alias}_history",
                    f"{alias}_historical",
                    f"{alias}_baseline",
                    f"{alias}_cumulative",
                    f"{alias}_before_lag6",
                    f"{alias}_older",
                    f"history_{alias}",
                ]
            )
    else:
        lag = match.group(3)
        for alias in aliases:
            candidate_norms.extend(
                [
                    f"{alias}_lag{lag}",
                    f"{alias}_lag_{lag}",
                    f"{alias}_t_{lag}",
                    f"{alias}_{lag}",
                    f"lag{lag}_{alias}",
                    f"lag_{lag}_{alias}",
                ]
            )
    for candidate in candidate_norms:
        normalized_candidate = re.sub(r"[^a-z0-9]+", "_", candidate.lower()).strip("_")
        if normalized_candidate in normalized:
            return normalized[normalized_candidate]
    return None


def canonicalize_wide_feature_table(df: pd.DataFrame, label: str) -> tuple[pd.DataFrame, dict[str, str]]:
    if df.empty:
        raise ValueError(f"{label} is empty.")
    repo_col = find_column(df.columns, REPO_ALIASES)
    if repo_col is None and "repo_name" not in df.columns:
        raise ValueError(f"{label} has no recognizable repository column.")
    if repo_col is not None and repo_col != "repo_name":
        df = df.rename(columns={repo_col: "repo_name"})
    df = df.copy()
    df["repo_name"] = normalize_repo_series(df["repo_name"])

    mapping: dict[str, str] = {}
    for canonical in canonical_paper_feature_columns():
        source = match_wide_feature_column(list(df.columns), canonical)
        if source is not None:
            mapping[canonical] = source

    missing = sorted(set(canonical_paper_feature_columns()) - set(mapping))
    if missing:
        raise ValueError(
            f"{label} does not expose the complete paper feature matrix. "
            f"Missing canonical features: {', '.join(missing)}"
        )

    output = df[["repo_name"] + list(dict.fromkeys(mapping.values()))].copy()
    for canonical, source in mapping.items():
        output[canonical] = safe_numeric(df[source])
    output = output[["repo_name"] + canonical_paper_feature_columns()]
    output = output.groupby("repo_name", as_index=False).first()
    return output, mapping


def identify_base_metric_columns(columns: Sequence[str]) -> dict[str, str]:
    normalized = {re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_"): str(c) for c in columns}
    mapping: dict[str, str] = {}
    for metric, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            key = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
            if key in normalized:
                mapping[metric] = normalized[key]
                break
    return mapping


def aggregate_event_level_monthly(df: pd.DataFrame, label: str) -> pd.DataFrame:
    repo_col = find_column(df.columns, REPO_ALIASES)
    date_col = find_column(df.columns, MONTH_ALIASES)
    if repo_col is None or date_col is None:
        raise ValueError(f"{label} requires repository and date/month columns.")
    data = df.copy()
    data["repo_name"] = normalize_repo_series(data[repo_col])
    data["time"] = normalize_month_series(data[date_col])
    data = data[data["repo_name"].ne("") & data["time"].ne("")].copy()

    direct_metrics = identify_base_metric_columns(list(data.columns))
    event_type_col = find_column(data.columns, EVENT_TYPE_ALIASES)
    actor_col = find_column(data.columns, ACTOR_ALIASES)

    if len(direct_metrics) >= 6:
        pieces = data[["repo_name", "time"]].copy()
        for metric in PAPER_METRICS:
            source = direct_metrics.get(metric)
            pieces[metric] = safe_numeric(data[source]) if source is not None else 0.0
        monthly = pieces.groupby(["repo_name", "time"], as_index=False)[list(PAPER_METRICS)].sum()
    elif event_type_col is not None:
        event_type = data[event_type_col].astype(str)
        data["total_events"] = 1.0
        data["stars"] = event_type.eq("WatchEvent").astype(float)
        data["forks"] = event_type.eq("ForkEvent").astype(float)
        data["releases"] = event_type.eq("ReleaseEvent").astype(float)
        data["pull_requests"] = event_type.eq("PullRequestEvent").astype(float)
        data["issues"] = event_type.eq("IssuesEvent").astype(float)
        data["comments"] = event_type.isin(
            {
                "IssueCommentEvent",
                "PullRequestReviewCommentEvent",
                "PullRequestReviewEvent",
                "CommitCommentEvent",
            }
        ).astype(float)
        sums = data.groupby(["repo_name", "time"], as_index=False)[
            ["stars", "forks", "releases", "pull_requests", "issues", "comments", "total_events"]
        ].sum()
        if actor_col is not None:
            users = (
                data.assign(_actor=data[actor_col].astype(str).str.strip())
                .loc[lambda x: x["_actor"].ne("")]
                .groupby(["repo_name", "time"])["_actor"]
                .nunique()
                .reset_index(name="users_involved")
            )
            monthly = sums.merge(users, on=["repo_name", "time"], how="left", validate="one_to_one")
            monthly["users_involved"] = monthly["users_involved"].fillna(0.0)
        else:
            monthly = sums.copy()
            monthly["users_involved"] = np.nan
        monthly = monthly[["repo_name", "time"] + list(PAPER_METRICS)]
    else:
        raise ValueError(
            f"{label} has neither enough direct metric columns nor an event_type column."
        )
    return monthly


def load_age_monthly(path: Path | None, wanted_repos: set[str], chunksize: int) -> pd.DataFrame:
    if path is None or not path.is_file():
        return pd.DataFrame(columns=["repo_name", "time", "age"])
    data = read_filtered_csv(path, wanted_repos, chunksize, "Treatment monthly covariate source")
    if data.empty:
        return pd.DataFrame(columns=["repo_name", "time", "age"])
    month_col = find_column(data.columns, MONTH_ALIASES)
    age_col = find_column(data.columns, AGE_ALIASES)
    if month_col is None or age_col is None:
        return pd.DataFrame(columns=["repo_name", "time", "age"])
    output = pd.DataFrame(
        {
            "repo_name": normalize_repo_series(data["repo_name"]),
            "time": normalize_month_series(data[month_col]),
            "age": safe_numeric(data[age_col]),
        }
    )
    return output.groupby(["repo_name", "time"], as_index=False)["age"].max()


def engineer_paper_features_from_monthly(
    monthly: pd.DataFrame,
    age_monthly: pd.DataFrame,
    repos: set[str],
    label: str,
) -> pd.DataFrame:
    required = {"repo_name", "time", *PAPER_METRICS}
    missing = sorted(required - set(monthly.columns))
    if missing:
        raise ValueError(f"{label} monthly data missing columns: {', '.join(missing)}")

    data = monthly.copy()
    data["repo_name"] = normalize_repo_series(data["repo_name"])
    data["time"] = normalize_month_series(data["time"])
    data = data[data["repo_name"].isin(repos)].copy()
    for metric in PAPER_METRICS:
        data[metric] = safe_numeric(data[metric]).fillna(0.0)
    data = data.groupby(["repo_name", "time"], as_index=False)[list(PAPER_METRICS)].sum()

    age_lookup = age_monthly.copy()
    if not age_lookup.empty:
        age_lookup["repo_name"] = normalize_repo_series(age_lookup["repo_name"])
        age_lookup["time"] = normalize_month_series(age_lookup["time"])
        age_lookup["age"] = safe_numeric(age_lookup["age"])
        age_lookup = age_lookup.set_index(["repo_name", "time"])["age"]

    rows: list[dict[str, object]] = []
    for repo in sorted(repos):
        repo_df = data[data["repo_name"].eq(repo)].set_index("time")
        row: dict[str, object] = {"repo_name": repo}
        if not age_monthly.empty and (repo, "2024-09") in age_lookup.index:
            row["age_lag1"] = float(age_lookup.loc[(repo, "2024-09")])
        else:
            row["age_lag1"] = np.nan
        for metric in PAPER_METRICS:
            for lag, month in LAG_MONTHS.items():
                row[f"{metric}_lag{lag}"] = (
                    float(repo_df.loc[month, metric]) if month in repo_df.index else 0.0
                )
            history = repo_df.loc[repo_df.index <= HISTORY_END_MONTH, metric]
            row[f"{metric}_history"] = float(history.sum()) if not history.empty else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def load_or_engineer_feature_table(
    wide_or_monthly_path: Path,
    wanted_repos: set[str],
    chunksize: int,
    label: str,
    age_monthly_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    data = read_filtered_csv(wide_or_monthly_path, wanted_repos, chunksize, label)
    if data.empty:
        raise ValueError(f"No requested repositories were found in {label}: {wide_or_monthly_path}")

    metadata: dict[str, object] = {
        "path": str(wide_or_monthly_path),
        "input_rows": int(len(data)),
        "input_columns": list(data.columns),
    }
    language_col = find_column(data.columns, LANGUAGE_ALIASES)
    language_map = pd.DataFrame(columns=["repo_name", "repo_primary_language"])
    if language_col is not None:
        language_map = data[["repo_name", language_col]].copy()
        language_map["repo_name"] = normalize_repo_series(language_map["repo_name"])
        language_map["repo_primary_language"] = (
            language_map[language_col].astype(str).str.strip()
        )
        language_map = (
            language_map[["repo_name", "repo_primary_language"]]
            .loc[lambda frame: frame["repo_name"].ne("")]
            .groupby("repo_name", as_index=False)["repo_primary_language"]
            .first()
        )

    try:
        wide, mapping = canonicalize_wide_feature_table(data, label)
        if not language_map.empty:
            wide = wide.merge(language_map, on="repo_name", how="left", validate="one_to_one")
        metadata["mode"] = "wide_preengineered"
        metadata["column_mapping"] = mapping
        metadata["primary_language_column"] = language_col
        return wide, metadata
    except ValueError as wide_error:
        month_col = find_column(data.columns, MONTH_ALIASES)
        if month_col is None:
            raise ValueError(
                f"{label} could not be interpreted as wide or monthly data. "
                f"Wide error: {wide_error}"
            ) from wide_error
        monthly = aggregate_event_level_monthly(data, label)
        age = load_age_monthly(age_monthly_path, wanted_repos, chunksize)
        if age.empty:
            source_month_col = find_column(data.columns, MONTH_ALIASES)
            source_age_col = find_column(data.columns, AGE_ALIASES)
            if source_month_col is not None and source_age_col is not None:
                age = pd.DataFrame(
                    {
                        "repo_name": normalize_repo_series(data["repo_name"]),
                        "time": normalize_month_series(data[source_month_col]),
                        "age": safe_numeric(data[source_age_col]),
                    }
                )
                age = (
                    age.dropna(subset=["age"])
                    .groupby(["repo_name", "time"], as_index=False)["age"]
                    .max()
                )
        engineered = engineer_paper_features_from_monthly(monthly, age, wanted_repos, label)
        if not language_map.empty:
            engineered = engineered.merge(
                language_map, on="repo_name", how="left", validate="one_to_one"
            )
        metadata["mode"] = "long_monthly_or_event_engineered"
        metadata["wide_error"] = str(wide_error)
        metadata["primary_language_column"] = language_col
        return engineered, metadata


def load_treatment_features(
    treatment_repos: set[str],
    treatment_feature_csv: Path | None,
    treatment_events_csv: Path | None,
    treatment_monthly_csv: Path | None,
    original_matching_csv: Path | None,
    chunksize: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    attempts: list[dict[str, str]] = []
    for path, label in (
        (treatment_feature_csv, "Treatment feature source"),
        (original_matching_csv, "Original matching source"),
    ):
        if path is None or not path.is_file():
            continue
        try:
            features, metadata = load_or_engineer_feature_table(
                path,
                treatment_repos,
                chunksize,
                label,
                age_monthly_path=treatment_monthly_csv,
            )
            if treatment_repos.issubset(set(features["repo_name"])):
                metadata["attempts"] = attempts
                return features, metadata
            attempts.append({"path": str(path), "error": "not all treatment repositories found"})
        except Exception as error:  # noqa: BLE001 - preserve diagnostics from schema attempts
            attempts.append({"path": str(path), "error": str(error)})

    if treatment_events_csv is None or not treatment_events_csv.is_file():
        raise ValueError(
            "Unable to build treatment features. Attempts: " + json.dumps(attempts, indent=2)
        )
    try:
        features, metadata = load_or_engineer_feature_table(
            treatment_events_csv,
            treatment_repos,
            chunksize,
            "Treatment event source",
            age_monthly_path=treatment_monthly_csv,
        )
        metadata["attempts"] = attempts
        return features, metadata
    except Exception as error:  # noqa: BLE001
        attempts.append({"path": str(treatment_events_csv), "error": str(error)})
        raise ValueError(
            "Unable to build treatment features from all configured sources. Attempts: "
            + json.dumps(attempts, indent=2)
        ) from error


def load_ncloc_features(
    path: Path,
    wanted_repos: set[str],
    chunksize: int,
    label: str,
    minimum_months: int,
    allow_partial: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    data = read_filtered_csv(path, wanted_repos, chunksize, label)
    if data.empty:
        raise ValueError(f"No requested repositories found in {label}: {path}")
    month_col = find_column(data.columns, MONTH_ALIASES)
    ncloc_col = find_column(data.columns, NCLOC_ALIASES)
    if month_col is None or ncloc_col is None:
        raise ValueError(
            f"{label} requires month and Python NCLOC columns. Columns: {list(data.columns)}"
        )
    ncloc = pd.DataFrame(
        {
            "repo_name": normalize_repo_series(data["repo_name"]),
            "time": normalize_month_series(data[month_col]),
            "python_ncloc": safe_numeric(data[ncloc_col]),
        }
    )
    ncloc = ncloc[ncloc["time"].isin(PRE_MONTHS)].copy()
    ncloc = ncloc.dropna(subset=["python_ncloc"])
    ncloc = ncloc.groupby(["repo_name", "time"], as_index=False)["python_ncloc"].max()

    rows: list[dict[str, object]] = []
    for repo in sorted(wanted_repos):
        repo_df = ncloc[ncloc["repo_name"].eq(repo)].set_index("time")
        observed = int(repo_df.index.nunique())
        values = pd.Series(index=list(PRE_MONTHS), dtype="float64")
        if not repo_df.empty:
            values.loc[repo_df.index] = repo_df["python_ncloc"].astype(float)
        level = values.loc["2024-09"] if "2024-09" in values.index else np.nan
        start = values.loc["2024-04"] if "2024-04" in values.index else np.nan
        log_values = np.log1p(values)
        eligible = observed >= minimum_months
        if not allow_partial:
            eligible = eligible and values.notna().all()
        rows.append(
            {
                "repo_name": repo,
                "python_ncloc_observed_months": observed,
                "python_ncloc_complete_window": bool(values.notna().all()),
                "python_ncloc_eligible": bool(eligible),
                "python_ncloc_log_level_lag1": float(np.log1p(level)) if pd.notna(level) else np.nan,
                "python_ncloc_log_change_6m": (
                    float(np.log1p(level) - np.log1p(start))
                    if pd.notna(level) and pd.notna(start)
                    else np.nan
                ),
                "python_ncloc_log_mean_6m": float(log_values.mean(skipna=True))
                if log_values.notna().any()
                else np.nan,
                **{
                    f"python_ncloc_{month.replace('-', '_')}": float(values.loc[month])
                    if pd.notna(values.loc[month])
                    else np.nan
                    for month in PRE_MONTHS
                },
            }
        )
    output = pd.DataFrame(rows)
    metadata = {
        "path": str(path),
        "input_rows_for_requested_repos": int(len(data)),
        "window_rows": int(len(ncloc)),
        "minimum_months": int(minimum_months),
        "allow_partial": bool(allow_partial),
        "eligible_repositories": int(output["python_ncloc_eligible"].sum()),
    }
    return output, metadata


def complete_feature_inventory(
    treatment_features: pd.DataFrame,
    candidate_features: pd.DataFrame,
    treatment_ncloc: pd.DataFrame,
    control_ncloc: pd.DataFrame,
    treatment_repos: set[str],
    candidate_repos: set[str],
) -> pd.DataFrame:
    treatment = treatment_features[treatment_features["repo_name"].isin(treatment_repos)].copy()
    treatment["is_treatment"] = 1
    treatment = treatment.merge(
        treatment_ncloc,
        on="repo_name",
        how="left",
        validate="one_to_one",
    )
    control = candidate_features[candidate_features["repo_name"].isin(candidate_repos)].copy()
    control["is_treatment"] = 0
    control = control.merge(control_ncloc, on="repo_name", how="left", validate="one_to_one")
    inventory = pd.concat([treatment, control], ignore_index=True, sort=False)
    inventory["sample_group"] = np.where(inventory["is_treatment"].eq(1), "treatment", "local_control")
    paper_columns = canonical_paper_feature_columns()
    ncloc_columns = canonical_ncloc_feature_columns()
    inventory["paper_feature_complete"] = inventory[paper_columns].notna().all(axis=1)
    inventory["ncloc_feature_complete"] = inventory[ncloc_columns].notna().all(axis=1)
    inventory["p1_feature_complete"] = (
        inventory["paper_feature_complete"] & inventory["ncloc_feature_complete"]
    )
    return inventory


def fit_propensity_model(
    inventory: pd.DataFrame,
    feature_columns: list[str],
    specification: str,
    random_state: int,
) -> ModelResult:
    data = inventory.copy()
    data = data[data["repo_name"].ne("")].drop_duplicates("repo_name")
    if data["is_treatment"].nunique() != 2:
        raise ValueError(f"{specification}: both treatment and control rows are required.")
    if int(data["is_treatment"].sum()) < 3:
        raise ValueError(f"{specification}: too few treatment repositories.")
    if int((data["is_treatment"] == 0).sum()) < 10:
        raise ValueError(f"{specification}: too few control repositories.")

    x = data[feature_columns].apply(pd.to_numeric, errors="coerce")
    y = data["is_treatment"].astype(int)
    pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=20_000,
                    random_state=random_state,
                ),
            ),
        ]
    )
    pipeline.fit(x, y)
    probability = pipeline.predict_proba(x)[:, 1]
    scored = data.copy()
    scored[f"propensity_score_{specification}"] = probability

    prevalence = float(y.mean())
    eps = np.finfo(float).eps
    fitted = np.clip(probability, eps, 1 - eps)
    null = np.clip(np.repeat(prevalence, len(y)), eps, 1 - eps)
    log_likelihood = float(np.sum(y * np.log(fitted) + (1 - y) * np.log(1 - fitted)))
    null_log_likelihood = float(np.sum(y * np.log(null) + (1 - y) * np.log(1 - null)))
    pseudo_r2 = 1.0 - (log_likelihood / null_log_likelihood) if null_log_likelihood != 0 else np.nan
    auc = float(roc_auc_score(y, probability))

    imputer: SimpleImputer = pipeline.named_steps["imputer"]
    scaler: StandardScaler = pipeline.named_steps["scaler"]
    logistic: LogisticRegression = pipeline.named_steps["logistic"]
    transformed_names = list(imputer.get_feature_names_out(feature_columns))
    coefficients = pd.DataFrame(
        {
            "specification": specification,
            "transformed_feature": transformed_names,
            "standardized_coefficient": logistic.coef_[0],
        }
    ).sort_values("standardized_coefficient", key=lambda s: s.abs(), ascending=False)

    diagnostics = {
        "specification": specification,
        "rows": int(len(data)),
        "treatment_repositories": int(y.sum()),
        "control_repositories": int((1 - y).sum()),
        "feature_count_before_missing_indicators": int(len(feature_columns)),
        "feature_count_after_missing_indicators": int(len(transformed_names)),
        "auc_in_sample": auc,
        "mcfadden_pseudo_r2_in_sample": pseudo_r2,
        "treatment_propensity_mean": float(probability[y.eq(1)].mean()),
        "control_propensity_mean": float(probability[y.eq(0)].mean()),
        "converged_iterations": int(logistic.n_iter_[0]),
        "random_state": int(random_state),
        "outcome_leakage_allowed": False,
    }
    training_means = x.mean(axis=0, skipna=True)
    training_stds = x.std(axis=0, ddof=0).replace(0, np.nan)
    return ModelResult(
        specification=specification,
        feature_columns=feature_columns,
        pipeline=pipeline,
        scored=scored,
        diagnostics=diagnostics,
        coefficients=coefficients,
        training_means=training_means,
        training_stds=training_stds,
    )


def standardized_distance(
    left: pd.Series,
    right: pd.Series,
    feature_columns: Sequence[str],
    means: pd.Series,
    stds: pd.Series,
) -> float:
    left_values = pd.to_numeric(left[list(feature_columns)], errors="coerce")
    right_values = pd.to_numeric(right[list(feature_columns)], errors="coerce")
    left_values = left_values.fillna(means)
    right_values = right_values.fillna(means)
    valid_stds = stds.reindex(feature_columns).fillna(1.0).replace(0, 1.0)
    diff = (left_values - right_values) / valid_stds
    return float(np.sqrt(np.mean(np.square(diff.to_numpy(dtype=float)))))


def build_pairwise_ranking(
    p0: ModelResult,
    p1: ModelResult,
    target_treatments: Sequence[str],
    candidate_repos: set[str],
    original_pairs: pd.DataFrame | None,
) -> pd.DataFrame:
    p0_score_col = "propensity_score_p0_paper"
    p1_score_col = "propensity_score_p1_paper_python_ncloc"
    p0_scored = p0.scored.set_index("repo_name", drop=False)
    p1_scored = p1.scored.set_index("repo_name", drop=False)
    candidates = sorted(candidate_repos & set(p1_scored.index))

    existing_pair_lookup: set[tuple[str, str]] = set()
    if original_pairs is not None and not original_pairs.empty:
        treatment_col = find_column(original_pairs.columns, ("treatment_repo", "repo_name"))
        control_col = find_column(original_pairs.columns, ("control_repo", "matched_control"))
        if treatment_col is not None and control_col is not None:
            existing_pair_lookup = set(
                zip(
                    normalize_repo_series(original_pairs[treatment_col]),
                    normalize_repo_series(original_pairs[control_col]),
                )
            )

    rows: list[dict[str, object]] = []
    ncloc_features = canonical_ncloc_feature_columns()
    p1_features = p1.feature_columns
    for treatment in target_treatments:
        if treatment not in p1_scored.index:
            raise ValueError(f"Target treatment missing from P1 scored sample: {treatment}")
        t0 = p0_scored.loc[treatment]
        t1 = p1_scored.loc[treatment]
        for candidate in candidates:
            c0 = p0_scored.loc[candidate]
            c1 = p1_scored.loc[candidate]
            p0_distance = abs(float(t0[p0_score_col]) - float(c0[p0_score_col]))
            p1_distance = abs(float(t1[p1_score_col]) - float(c1[p1_score_col]))
            paper_distance = standardized_distance(
                t1,
                c1,
                canonical_paper_feature_columns(),
                p1.training_means,
                p1.training_stds,
            )
            ncloc_distance = standardized_distance(
                t1,
                c1,
                ncloc_features,
                p1.training_means,
                p1.training_stds,
            )
            all_distance = standardized_distance(
                t1,
                c1,
                p1_features,
                p1.training_means,
                p1.training_stds,
            )
            rows.append(
                {
                    "treatment_repo": treatment,
                    "candidate_control_repo": candidate,
                    "is_original_webscout": candidate == TARGET_CONTROL,
                    "already_matched_to_treatment_in_original_data": (
                        treatment,
                        candidate,
                    ) in existing_pair_lookup,
                    "treatment_propensity_p0": float(t0[p0_score_col]),
                    "candidate_propensity_p0": float(c0[p0_score_col]),
                    "propensity_distance_p0": p0_distance,
                    "treatment_propensity_p1": float(t1[p1_score_col]),
                    "candidate_propensity_p1": float(c1[p1_score_col]),
                    "propensity_distance_p1": p1_distance,
                    "standardized_paper_feature_distance": paper_distance,
                    "standardized_python_ncloc_distance": ncloc_distance,
                    "standardized_all_feature_distance_p1": all_distance,
                    "candidate_python_ncloc_log_level_lag1": float(
                        c1["python_ncloc_log_level_lag1"]
                    ),
                    "candidate_python_ncloc_log_change_6m": float(
                        c1["python_ncloc_log_change_6m"]
                    ),
                    "candidate_python_ncloc_log_mean_6m": float(
                        c1["python_ncloc_log_mean_6m"]
                    ),
                }
            )

    ranking = pd.DataFrame(rows)
    ranking = ranking.sort_values(
        [
            "treatment_repo",
            "propensity_distance_p1",
            "standardized_all_feature_distance_p1",
            "candidate_control_repo",
        ]
    )
    ranking["rank_within_treatment_p1"] = (
        ranking.groupby("treatment_repo").cumcount() + 1
    )
    ranking = ranking.sort_values(
        ["treatment_repo", "rank_within_treatment_p1"]
    ).reset_index(drop=True)
    return ranking


def build_common_donor_ranking(pairwise: pd.DataFrame) -> pd.DataFrame:
    common = (
        pairwise.groupby("candidate_control_repo", as_index=False)
        .agg(
            target_treatments_covered=("treatment_repo", "nunique"),
            is_original_webscout=("is_original_webscout", "max"),
            original_pair_count=("already_matched_to_treatment_in_original_data", "sum"),
            max_propensity_distance_p1=("propensity_distance_p1", "max"),
            mean_propensity_distance_p1=("propensity_distance_p1", "mean"),
            median_propensity_distance_p1=("propensity_distance_p1", "median"),
            max_propensity_distance_p0=("propensity_distance_p0", "max"),
            mean_propensity_distance_p0=("propensity_distance_p0", "mean"),
            max_standardized_all_feature_distance_p1=(
                "standardized_all_feature_distance_p1",
                "max",
            ),
            mean_standardized_all_feature_distance_p1=(
                "standardized_all_feature_distance_p1",
                "mean",
            ),
            mean_standardized_paper_feature_distance=(
                "standardized_paper_feature_distance",
                "mean",
            ),
            mean_standardized_python_ncloc_distance=(
                "standardized_python_ncloc_distance",
                "mean",
            ),
            python_ncloc_log_level_lag1=(
                "candidate_python_ncloc_log_level_lag1",
                "first",
            ),
            python_ncloc_log_change_6m=(
                "candidate_python_ncloc_log_change_6m",
                "first",
            ),
            python_ncloc_log_mean_6m=(
                "candidate_python_ncloc_log_mean_6m",
                "first",
            ),
        )
    )
    common = common.sort_values(
        [
            "max_propensity_distance_p1",
            "mean_propensity_distance_p1",
            "mean_standardized_all_feature_distance_p1",
            "candidate_control_repo",
        ]
    ).reset_index(drop=True)
    common["overall_similarity_rank_p1"] = np.arange(1, len(common) + 1)
    common["eligible_replacement_candidate"] = ~common["is_original_webscout"].astype(bool)
    common["common_donor_rank_p1"] = pd.Series(pd.NA, index=common.index, dtype="Int64")
    eligible_index = common.index[common["eligible_replacement_candidate"]]
    common.loc[eligible_index, "common_donor_rank_p1"] = np.arange(1, len(eligible_index) + 1)
    common["selection_uses_post_adoption_agc_outcomes"] = False
    common["recommended_for_manual_freeze_review"] = (
        common["eligible_replacement_candidate"]
        & common["common_donor_rank_p1"].fillna(10_000).le(10)
    )
    return common


def build_balance_table(
    inventory: pd.DataFrame,
    common_ranking: pd.DataFrame,
    target_treatments: Sequence[str],
    p1: ModelResult,
) -> pd.DataFrame:
    eligible_common = common_ranking[common_ranking["eligible_replacement_candidate"]].copy()
    if eligible_common.empty:
        raise ValueError("No eligible replacement candidate is available for balance checks.")
    top_candidate = str(eligible_common.iloc[0]["candidate_control_repo"])
    candidates = [top_candidate]
    if TARGET_CONTROL in set(inventory["repo_name"]):
        candidates.append(TARGET_CONTROL)
    inventory_index = inventory.set_index("repo_name", drop=False)
    treatment_frame = inventory_index.loc[list(target_treatments)]
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_row = inventory_index.loc[candidate]
        for feature in p1.feature_columns:
            treatment_mean = float(pd.to_numeric(treatment_frame[feature], errors="coerce").mean())
            candidate_value = float(pd.to_numeric(pd.Series([candidate_row[feature]]), errors="coerce").iloc[0])
            training_sd = float(p1.training_stds.get(feature, np.nan))
            normalized_difference = (
                (treatment_mean - candidate_value) / training_sd
                if pd.notna(training_sd) and training_sd > 0
                else np.nan
            )
            rows.append(
                {
                    "candidate_control_repo": candidate,
                    "is_top_ranked_common_donor": candidate == top_candidate,
                    "is_original_webscout": candidate == TARGET_CONTROL,
                    "feature": feature,
                    "target_treatment_mean": treatment_mean,
                    "candidate_value": candidate_value,
                    "training_sample_sd": training_sd,
                    "normalized_difference": normalized_difference,
                    "absolute_normalized_difference": abs(normalized_difference)
                    if pd.notna(normalized_difference)
                    else np.nan,
                    "balance_below_0_10": bool(
                        pd.notna(normalized_difference) and abs(normalized_difference) < 0.10
                    ),
                    "balance_below_0_25": bool(
                        pd.notna(normalized_difference) and abs(normalized_difference) < 0.25
                    ),
                }
            )
    return pd.DataFrame(rows)


def load_original_pairs(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.is_file():
        return None
    return pd.read_csv(path, dtype=str, low_memory=False)


def write_status(output_dir: Path, status: str, details: Sequence[str]) -> None:
    path = output_dir / f"{OUTPUT_PREFIX}_status.txt"
    path.write_text("\n".join([status, *details]) + "\n", encoding="utf-8")


def run_analysis(
    paths: InputPaths,
    target_control: str,
    target_cohort: str,
    top_k: int,
    chunksize: int,
    random_state: int,
    min_local_candidates: int,
    min_python_ncloc_months: int,
    allow_partial_ncloc: bool,
    skip_frozen_target_checks: bool,
) -> dict[str, object]:
    for path, label in (
        (paths.target_pair_manifest, "Target pair manifest"),
        (paths.treatment_sample, "Treatment sample"),
        (paths.candidate_feature_csv, "Control candidate feature CSV"),
        (paths.treatment_ncloc_csv, "Treatment Python NCLOC CSV"),
        (paths.control_ncloc_csv, "Control Python NCLOC CSV"),
    ):
        require_file(path, label)
    require_file(paths.treatment_feature_csv, "Treatment feature CSV", optional=True)
    require_file(paths.treatment_events_csv, "Treatment events CSV", optional=True)
    require_file(paths.treatment_monthly_csv, "Treatment monthly CSV", optional=True)
    require_file(paths.original_matching_csv, "Original matching CSV", optional=True)
    require_file(paths.local_control_manifest, "Local control manifest", optional=True)

    paths.output_dir.mkdir(parents=True, exist_ok=True)

    target_pairs = load_target_treatments(
        paths.target_pair_manifest,
        target_control,
        skip_frozen_target_checks,
    )
    target_treatment_names = target_pairs["treatment_repo"].tolist()
    target_treatment_set = set(target_treatment_names)
    cohort = load_treatment_cohort(
        paths.treatment_sample,
        target_cohort,
        target_treatment_set,
    )
    cohort_repos = set(cohort["repo_name"])

    local_controls = discover_local_controls(paths.control_clone_root, paths.local_control_manifest)
    local_controls["excluded_target_control"] = local_controls["repo_name"].eq(target_control)
    local_controls["excluded_treatment_overlap"] = local_controls["repo_name"].isin(cohort_repos)
    local_controls["candidate_pre_feature_eligible"] = (
        local_controls["local_clone_exists"]
        & ~local_controls["excluded_target_control"]
        & ~local_controls["excluded_treatment_overlap"]
    )
    pre_candidate_repos = set(
        local_controls.loc[local_controls["candidate_pre_feature_eligible"], "repo_name"]
    )
    if len(pre_candidate_repos) < min_local_candidates:
        raise ValueError(
            f"Too few local control candidates before feature checks: {len(pre_candidate_repos)} "
            f"< {min_local_candidates}."
        )

    candidate_features, candidate_feature_metadata = load_or_engineer_feature_table(
        paths.candidate_feature_csv,
        pre_candidate_repos | {target_control},
        chunksize,
        "Control candidate feature source",
        age_monthly_path=None,
    )

    candidate_language_verified = "repo_primary_language" in candidate_features.columns
    if candidate_language_verified:
        candidate_language = candidate_features[["repo_name", "repo_primary_language"]].copy()
        candidate_language["candidate_primary_language"] = (
            candidate_language["repo_primary_language"].astype(str).str.strip()
        )
        python_candidate_repos = set(
            candidate_language.loc[
                candidate_language["candidate_primary_language"].str.casefold().eq("python"),
                "repo_name",
            ]
        )
        pre_candidate_repos &= python_candidate_repos
        local_controls = local_controls.merge(
            candidate_language[["repo_name", "candidate_primary_language"]],
            on="repo_name",
            how="left",
            validate="one_to_one",
        )
        local_controls["same_primary_language_python"] = (
            local_controls["candidate_primary_language"].astype(str).str.casefold().eq("python")
        )
        local_controls["candidate_pre_feature_eligible"] = (
            local_controls["candidate_pre_feature_eligible"]
            & local_controls["same_primary_language_python"]
        )
        if len(pre_candidate_repos) < min_local_candidates:
            raise ValueError(
                f"Too few local Python control candidates after same-language filtering: "
                f"{len(pre_candidate_repos)} < {min_local_candidates}."
            )
    else:
        local_controls["candidate_primary_language"] = ""
        local_controls["same_primary_language_python"] = pd.NA

    treatment_features, treatment_feature_metadata = load_treatment_features(
        cohort_repos,
        paths.treatment_feature_csv,
        paths.treatment_events_csv,
        paths.treatment_monthly_csv,
        paths.original_matching_csv,
        chunksize,
    )

    treatment_ncloc, treatment_ncloc_metadata = load_ncloc_features(
        paths.treatment_ncloc_csv,
        cohort_repos,
        chunksize,
        "Treatment Python NCLOC source",
        min_python_ncloc_months,
        allow_partial_ncloc,
    )
    control_ncloc, control_ncloc_metadata = load_ncloc_features(
        paths.control_ncloc_csv,
        pre_candidate_repos | {target_control},
        chunksize,
        "Control Python NCLOC source",
        min_python_ncloc_months,
        allow_partial_ncloc,
    )

    candidate_feature_repos = set(candidate_features["repo_name"])
    candidate_ncloc_eligible = set(
        control_ncloc.loc[control_ncloc["python_ncloc_eligible"], "repo_name"]
    )
    final_candidate_repos = pre_candidate_repos & candidate_feature_repos & candidate_ncloc_eligible
    if len(final_candidate_repos) < min_local_candidates:
        raise ValueError(
            f"Too few local candidates after feature and NCLOC checks: "
            f"{len(final_candidate_repos)} < {min_local_candidates}."
        )

    treatment_feature_repos = set(treatment_features["repo_name"])
    treatment_ncloc_eligible = set(
        treatment_ncloc.loc[treatment_ncloc["python_ncloc_eligible"], "repo_name"]
    )
    missing_treatment_features = sorted(cohort_repos - treatment_feature_repos)
    missing_treatment_ncloc = sorted(cohort_repos - treatment_ncloc_eligible)
    if missing_treatment_features:
        raise ValueError(
            "2024-10 treatment repositories missing paper features: "
            + ", ".join(missing_treatment_features)
        )
    if missing_treatment_ncloc:
        raise ValueError(
            "2024-10 treatment repositories missing required Python NCLOC coverage: "
            + ", ".join(missing_treatment_ncloc)
        )

    benchmark_control_repos: set[str] = set()
    if (
        target_control in candidate_feature_repos
        and target_control in candidate_ncloc_eligible
    ):
        benchmark_control_repos.add(target_control)
    model_control_repos = final_candidate_repos | benchmark_control_repos

    inventory = complete_feature_inventory(
        treatment_features,
        candidate_features,
        treatment_ncloc,
        control_ncloc,
        cohort_repos,
        model_control_repos,
    )
    inventory = inventory[
        inventory["repo_name"].isin(cohort_repos | model_control_repos)
    ].copy()
    inventory["is_target_treatment"] = inventory["repo_name"].isin(target_treatment_set)
    inventory["is_original_webscout"] = inventory["repo_name"].eq(target_control)

    # P0 and P1 use the same treatment/control repository set. This isolates the
    # contribution of Python-only NCLOC rather than changes in sample membership.
    model_inventory = inventory[inventory["p1_feature_complete"]].copy()
    if target_treatment_set - set(model_inventory["repo_name"]):
        raise ValueError("At least one target treatment is missing from the common P0/P1 model sample.")

    p0 = fit_propensity_model(
        model_inventory,
        canonical_paper_feature_columns(),
        "p0_paper",
        random_state,
    )
    p1 = fit_propensity_model(
        model_inventory,
        canonical_paper_feature_columns() + canonical_ncloc_feature_columns(),
        "p1_paper_python_ncloc",
        random_state,
    )

    original_pairs = load_original_pairs(paths.original_matching_csv)
    ranking_control_repos = final_candidate_repos | benchmark_control_repos
    pairwise = build_pairwise_ranking(
        p0,
        p1,
        target_treatment_names,
        ranking_control_repos,
        original_pairs,
    )
    common = build_common_donor_ranking(pairwise)
    balance = build_balance_table(
        model_inventory,
        common,
        target_treatment_names,
        p1,
    )

    local_controls = local_controls.merge(
        candidate_features[["repo_name"]].assign(paper_features_found=True),
        on="repo_name",
        how="left",
    )
    local_controls = local_controls.merge(
        control_ncloc[
            [
                "repo_name",
                "python_ncloc_observed_months",
                "python_ncloc_complete_window",
                "python_ncloc_eligible",
            ]
        ],
        on="repo_name",
        how="left",
    )
    local_controls["paper_features_found"] = local_controls["paper_features_found"].fillna(False)
    local_controls["python_ncloc_eligible"] = local_controls["python_ncloc_eligible"].fillna(False)
    local_controls["final_candidate_eligible"] = local_controls["repo_name"].isin(final_candidate_repos)
    local_controls["ineligibility_reason"] = "eligible"
    local_controls.loc[~local_controls["local_clone_exists"], "ineligibility_reason"] = "local_clone_missing"
    local_controls.loc[local_controls["excluded_target_control"], "ineligibility_reason"] = "original_webscout_excluded"
    local_controls.loc[local_controls["excluded_treatment_overlap"], "ineligibility_reason"] = "treatment_overlap"
    if candidate_language_verified:
        local_controls.loc[
            ~local_controls["excluded_target_control"]
            & ~local_controls["excluded_treatment_overlap"]
            & local_controls["local_clone_exists"]
            & ~local_controls["same_primary_language_python"],
            "ineligibility_reason",
        ] = "primary_language_not_python"
    local_controls.loc[
        local_controls["candidate_pre_feature_eligible"] & ~local_controls["paper_features_found"],
        "ineligibility_reason",
    ] = "paper_features_missing"
    local_controls.loc[
        local_controls["candidate_pre_feature_eligible"]
        & local_controls["paper_features_found"]
        & ~local_controls["python_ncloc_eligible"],
        "ineligibility_reason",
    ] = "python_ncloc_window_incomplete"

    p0_scores = p0.scored[["repo_name", "sample_group", "is_treatment", "propensity_score_p0_paper"]]
    p1_scores = p1.scored[
        [
            "repo_name",
            "sample_group",
            "is_treatment",
            "propensity_score_p1_paper_python_ncloc",
        ]
    ]
    scores = p0_scores.merge(
        p1_scores,
        on=["repo_name", "sample_group", "is_treatment"],
        how="inner",
        validate="one_to_one",
    )
    scores["is_target_treatment"] = scores["repo_name"].isin(target_treatment_set)
    scores["is_original_webscout"] = scores["repo_name"].eq(target_control)

    diagnostics = pd.DataFrame([p0.diagnostics, p1.diagnostics])
    coefficients = pd.concat([p0.coefficients, p1.coefficients], ignore_index=True)

    validation_rows = [
        ("target_control_is_webscout", target_control == TARGET_CONTROL, target_control),
        ("target_treatment_count_is_six", len(target_pairs) == 6, len(target_pairs)),
        (
            "target_treatments_in_202410_cohort",
            target_treatment_set.issubset(cohort_repos),
            len(target_treatment_set & cohort_repos),
        ),
        (
            "local_candidates_before_features_at_least_minimum",
            len(pre_candidate_repos) >= min_local_candidates,
            len(pre_candidate_repos),
        ),
        (
            "final_candidates_at_least_minimum",
            len(final_candidate_repos) >= min_local_candidates,
            len(final_candidate_repos),
        ),
        (
            "same_primary_language_rule_applied",
            True,
            (
                "Verified from candidate feature source"
                if candidate_language_verified
                else "Candidate source has no language column; relied on Python-specific local control pool"
            ),
        ),
        (
            "all_target_treatments_scored_p0",
            target_treatment_set.issubset(set(p0.scored["repo_name"])),
            len(target_treatment_set & set(p0.scored["repo_name"])),
        ),
        (
            "all_target_treatments_scored_p1",
            target_treatment_set.issubset(set(p1.scored["repo_name"])),
            len(target_treatment_set & set(p1.scored["repo_name"])),
        ),
        (
            "pairwise_rows_equal_targets_times_candidates_and_optional_webscout_benchmark",
            len(pairwise)
            == len(target_treatment_set)
            * (len(final_candidate_repos) + len(benchmark_control_repos)),
            len(pairwise),
        ),
        (
            "common_ranking_has_all_candidates_and_optional_webscout_benchmark",
            len(common) == len(final_candidate_repos) + len(benchmark_control_repos),
            len(common),
        ),
        (
            "no_post_adoption_agc_outcome_read",
            True,
            "No AGC outcome path is accepted by this script",
        ),
        (
            "did_not_run",
            True,
            "Candidate ranking only",
        ),
        (
            "causal_interpretation_disallowed",
            True,
            "Noncausal local-control rematching sensitivity",
        ),
    ]
    validation = pd.DataFrame(validation_rows, columns=["check", "passed", "observed"])
    failed_checks = int((~validation["passed"].astype(bool)).sum())
    if failed_checks:
        raise ValueError(
            "Validation failed: "
            + ", ".join(validation.loc[~validation["passed"].astype(bool), "check"])
        )

    output_dir = paths.output_dir
    target_pairs.to_csv(output_dir / f"{OUTPUT_PREFIX}_target_treatments.csv", index=False)
    cohort.to_csv(output_dir / f"{OUTPUT_PREFIX}_202410_python_treatment_cohort.csv", index=False)
    local_controls.to_csv(output_dir / f"{OUTPUT_PREFIX}_candidate_eligibility.csv", index=False)
    model_inventory.to_csv(output_dir / f"{OUTPUT_PREFIX}_model_feature_inventory.csv", index=False)
    scores.to_csv(output_dir / f"{OUTPUT_PREFIX}_propensity_scores.csv", index=False)
    diagnostics.to_csv(output_dir / f"{OUTPUT_PREFIX}_model_diagnostics.csv", index=False)
    coefficients.to_csv(output_dir / f"{OUTPUT_PREFIX}_model_coefficients.csv", index=False)
    pairwise.to_csv(output_dir / f"{OUTPUT_PREFIX}_per_treatment_ranking.csv", index=False)
    pairwise[pairwise["rank_within_treatment_p1"].le(top_k)].to_csv(
        output_dir / f"{OUTPUT_PREFIX}_per_treatment_top{top_k}.csv",
        index=False,
    )
    common.to_csv(output_dir / f"{OUTPUT_PREFIX}_common_donor_ranking.csv", index=False)
    common[common["eligible_replacement_candidate"]].head(top_k).to_csv(
        output_dir / f"{OUTPUT_PREFIX}_common_donor_top{top_k}.csv",
        index=False,
    )
    balance.to_csv(output_dir / f"{OUTPUT_PREFIX}_top_candidate_balance.csv", index=False)
    treatment_ncloc.to_csv(output_dir / f"{OUTPUT_PREFIX}_treatment_python_ncloc_features.csv", index=False)
    control_ncloc.to_csv(output_dir / f"{OUTPUT_PREFIX}_control_python_ncloc_features.csv", index=False)
    validation.to_csv(output_dir / f"{OUTPUT_PREFIX}_validation.csv", index=False)

    summary = {
        "status": "PASS",
        "analysis": "local cloned-control rematching candidate ranking",
        "target_control": target_control,
        "target_cohort": target_cohort,
        "target_treatments": target_treatment_names,
        "target_treatment_count": len(target_treatment_names),
        "cohort_treatment_count": len(cohort_repos),
        "local_control_directories": int(len(local_controls)),
        "pre_feature_candidates": len(pre_candidate_repos),
        "final_p0_p1_candidates": len(final_candidate_repos),
        "p0_diagnostics": p0.diagnostics,
        "p1_diagnostics": p1.diagnostics,
        "top_common_candidate": common[common["eligible_replacement_candidate"]].iloc[0].to_dict(),
        "original_webscout_in_similarity_ranking": bool(common["is_original_webscout"].any()),
        "original_webscout_similarity_rank": (
            int(common.loc[common["is_original_webscout"], "overall_similarity_rank_p1"].iloc[0])
            if common["is_original_webscout"].any()
            else None
        ),
        "selection_uses_post_adoption_agc_outcomes": False,
        "did_ran": False,
        "causal_interpretation_allowed": False,
        "candidate_feature_source": candidate_feature_metadata,
        "candidate_language_verified_from_feature_source": candidate_language_verified,
        "treatment_feature_source": treatment_feature_metadata,
        "treatment_ncloc_source": treatment_ncloc_metadata,
        "control_ncloc_source": control_ncloc_metadata,
        "output_prefix": OUTPUT_PREFIX,
        "next_step": (
            "Manually review and freeze a donor from the top-ranked candidates before "
            "opening 2025-04 and 2025-06 AGC class-method outcomes."
        ),
    }
    (output_dir / f"{OUTPUT_PREFIX}_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_status(
        output_dir,
        "PASS",
        [
            f"target_treatments={len(target_treatment_names)}",
            f"cohort_treatments={len(cohort_repos)}",
            f"final_candidates={len(final_candidate_repos)}",
            f"top_common_candidate={common[common['eligible_replacement_candidate']].iloc[0]['candidate_control_repo']}",
            "post_adoption_agc_outcome_used=FALSE",
            "did_ran=FALSE",
            "causal_interpretation_allowed=FALSE",
        ],
    )

    print("=" * 80)
    print("run-py-8d: Webscout local-control rematching candidate ranking")
    print("=" * 80)
    print("Status: PASS")
    print(f"Target treatments: {len(target_treatment_names)}")
    print(f"2024-10 Python cohort treatments: {len(cohort_repos)}")
    print(f"Local candidate controls before features: {len(pre_candidate_repos)}")
    print(f"Final P0/P1 candidate controls: {len(final_candidate_repos)}")
    print("Post-adoption AGC outcomes inspected: NO")
    print("DiD executed: NO")
    print("\nTop common-donor candidates under P1:")
    print(
        common[common["eligible_replacement_candidate"]].head(min(10, int(common["eligible_replacement_candidate"].sum())))[
            [
                "common_donor_rank_p1",
                "candidate_control_repo",
                "max_propensity_distance_p1",
                "mean_propensity_distance_p1",
                "mean_standardized_all_feature_distance_p1",
                "mean_standardized_python_ncloc_distance",
            ]
        ].to_string(index=False)
    )
    print(f"\nOutput directory: {output_dir.resolve()}")
    print("=" * 80)
    return summary


def create_synthetic_paper_features(repos: Sequence[str], offset: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, repo in enumerate(repos):
        base = offset + index * 0.15
        row: dict[str, object] = {"repo_name": repo, "age_lag1": 200.0 + base * 20.0}
        for metric_index, metric in enumerate(PAPER_METRICS, start=1):
            for lag in range(1, 7):
                row[f"{metric}_lag{lag}"] = base * metric_index + lag * 0.1
            row[f"{metric}_history"] = base * metric_index * 8.0
        rows.append(row)
    return pd.DataFrame(rows)


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-8d-self-test-") as tmp_raw:
        tmp = Path(tmp_raw)
        output_dir = tmp / "output"
        control_root = tmp / "control-repos"
        control_root.mkdir()

        targets = list(EXPECTED_TARGET_TREATMENTS)
        other_treatments = ["example/TreatmentA", "example/TreatmentB"]
        treatments = targets + other_treatments
        controls = [f"example/Control{i:02d}" for i in range(1, 31)]
        for repo in controls + [TARGET_CONTROL]:
            repo_dir = control_root / repo.replace("/", "_")
            (repo_dir / ".git").mkdir(parents=True)
            (repo_dir / ".git" / "config").write_text(
                f'[remote "origin"]\n\turl = https://github.com/{repo}.git\n',
                encoding="utf-8",
            )

        pair_manifest = pd.DataFrame(
            {
                "treatment_repo": targets,
                "control_repo": [TARGET_CONTROL] * len(targets),
                "control_rank": [3] * len(targets),
            }
        )
        pair_path = tmp / "pairs.csv"
        pair_manifest.to_csv(pair_path, index=False)

        treatment_sample = pd.DataFrame(
            {
                "repo_name": treatments,
                "event_month": [TARGET_COHORT] * len(treatments),
                "repo_primary_language": ["Python"] * len(treatments),
            }
        )
        treatment_sample_path = tmp / "treatment_sample.csv"
        treatment_sample.to_csv(treatment_sample_path, index=False)

        treatment_features = create_synthetic_paper_features(treatments, 1.0)
        treatment_feature_path = tmp / "treatment_features.csv"
        treatment_features.to_csv(treatment_feature_path, index=False)

        candidate_features = create_synthetic_paper_features(controls + [TARGET_CONTROL], 1.05)
        # Make Control07 deliberately close to the center of the six target treatments.
        target_center = treatment_features[treatment_features["repo_name"].isin(targets)][
            canonical_paper_feature_columns()
        ].mean()
        candidate_features.loc[
            candidate_features["repo_name"].eq("example/Control07"),
            canonical_paper_feature_columns(),
        ] = target_center.to_numpy()
        candidate_feature_path = tmp / "candidate_features.csv"
        candidate_features.to_csv(candidate_feature_path, index=False)

        local_manifest_path = tmp / "local_controls.csv"
        pd.DataFrame({"repo_name": controls + [TARGET_CONTROL]}).to_csv(
            local_manifest_path,
            index=False,
        )

        treatment_ncloc_rows: list[dict[str, object]] = []
        control_ncloc_rows: list[dict[str, object]] = []
        for repo_index, repo in enumerate(treatments):
            for month_index, month in enumerate(PRE_MONTHS):
                treatment_ncloc_rows.append(
                    {
                        "repo_name": repo,
                        "time": month,
                        "ncloc_python_snapshot": 1000 + repo_index * 25 + month_index * 20,
                    }
                )
        for repo_index, repo in enumerate(controls + [TARGET_CONTROL]):
            for month_index, month in enumerate(PRE_MONTHS):
                value = 1020 + repo_index * 30 + month_index * 18
                if repo == "example/Control07":
                    value = 1060 + month_index * 20
                control_ncloc_rows.append(
                    {
                        "repo_name": repo,
                        "time": month,
                        "ncloc_python_snapshot": value,
                    }
                )
        treatment_ncloc_path = tmp / "treatment_ncloc.csv"
        control_ncloc_path = tmp / "control_ncloc.csv"
        pd.DataFrame(treatment_ncloc_rows).to_csv(treatment_ncloc_path, index=False)
        pd.DataFrame(control_ncloc_rows).to_csv(control_ncloc_path, index=False)

        original_matching_path = tmp / "matching.csv"
        pair_manifest.to_csv(original_matching_path, index=False)

        summary = run_analysis(
            InputPaths(
                target_pair_manifest=pair_path,
                treatment_sample=treatment_sample_path,
                candidate_feature_csv=candidate_feature_path,
                treatment_feature_csv=treatment_feature_path,
                treatment_events_csv=None,
                treatment_monthly_csv=None,
                original_matching_csv=original_matching_path,
                local_control_manifest=local_manifest_path,
                control_clone_root=control_root,
                treatment_ncloc_csv=treatment_ncloc_path,
                control_ncloc_csv=control_ncloc_path,
                output_dir=output_dir,
            ),
            target_control=TARGET_CONTROL,
            target_cohort=TARGET_COHORT,
            top_k=10,
            chunksize=10,
            random_state=20260730,
            min_local_candidates=20,
            min_python_ncloc_months=6,
            allow_partial_ncloc=False,
            skip_frozen_target_checks=False,
        )
        if summary["status"] != "PASS":
            raise AssertionError("Synthetic analysis did not pass.")
        status_path = output_dir / f"{OUTPUT_PREFIX}_status.txt"
        if status_path.read_text(encoding="utf-8").splitlines()[0] != "PASS":
            raise AssertionError("Synthetic status file is not PASS.")
        common = pd.read_csv(output_dir / f"{OUTPUT_PREFIX}_common_donor_ranking.csv")
        if len(common) != len(controls) + 1:
            raise AssertionError(
                "Synthetic common ranking does not contain every eligible control plus Webscout."
            )
        webscout_rows = common[common["is_original_webscout"].astype(bool)]
        if len(webscout_rows) != 1 or bool(webscout_rows.iloc[0]["eligible_replacement_candidate"]):
            raise AssertionError("Synthetic Webscout benchmark was not retained as an ineligible benchmark.")
        if common["selection_uses_post_adoption_agc_outcomes"].astype(bool).any():
            raise AssertionError("Synthetic ranking incorrectly indicates outcome use.")
        print("Self-test: PASS")


def main() -> None:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return

    required_args = {
        "target_pair_manifest": args.target_pair_manifest,
        "treatment_sample": args.treatment_sample,
        "candidate_feature_csv": args.candidate_feature_csv,
        "control_clone_root": args.control_clone_root,
        "treatment_ncloc_csv": args.treatment_ncloc_csv,
        "control_ncloc_csv": args.control_ncloc_csv,
        "output_dir": args.output_dir,
    }
    missing = [name for name, value in required_args.items() if value is None]
    if missing:
        raise SystemExit("ERROR: missing required arguments: " + ", ".join(missing))

    try:
        run_analysis(
            InputPaths(
                target_pair_manifest=args.target_pair_manifest,
                treatment_sample=args.treatment_sample,
                candidate_feature_csv=args.candidate_feature_csv,
                treatment_feature_csv=args.treatment_feature_csv,
                treatment_events_csv=args.treatment_events_csv,
                treatment_monthly_csv=args.treatment_monthly_csv,
                original_matching_csv=args.original_matching_csv,
                local_control_manifest=args.local_control_manifest,
                control_clone_root=args.control_clone_root,
                treatment_ncloc_csv=args.treatment_ncloc_csv,
                control_ncloc_csv=args.control_ncloc_csv,
                output_dir=args.output_dir,
            ),
            target_control=args.target_control,
            target_cohort=args.target_cohort,
            top_k=args.top_k,
            chunksize=args.chunksize,
            random_state=args.random_state,
            min_local_candidates=args.min_local_candidates,
            min_python_ncloc_months=args.min_python_ncloc_months,
            allow_partial_ncloc=args.allow_ncloc_partial_window,
            skip_frozen_target_checks=args.skip_frozen_target_checks,
        )
    except Exception as error:  # noqa: BLE001 - emit a concise terminal failure
        print(f"ERROR: {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
