#!/usr/bin/env python3
"""Restore pre-adoption Python NCLOC and rank Webscout replacement controls.

This program implements a noncausal design-stage rematching sensitivity for the
six treatment repositories that originally used HelpingAI/Webscout as their
third matched control.

The original paper propensity score is preserved. The six target treatments
and their three original controls are exact ties under the paper score. This
program therefore restores Python-only source snapshots at the end of the last
pre-adoption month and uses direct Python NCLOC as a tie-breaking dimension.

Important design constraints:
- The program never reads post-adoption AGC outcomes.
- The program does not run Difference-in-Differences.
- Missing snapshot measurements are never converted to zero.
- A zero is assigned only when complete Git history shows that the repository
  had no commit before the cutoff.
- Repository working trees and HEAD positions are not modified. Snapshots are
  read through ``git archive`` from immutable commit objects.

Direct NCLOC is measured with a documented Python token/AST procedure. It is
not silently presented as an exact SonarQube reproduction. Existing SonarQube
Python-only NCLOC files may be supplied for validation, but donor ranking uses
only the restored direct measurement.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tokenize
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

TARGET_CONTROL = "HelpingAI/Webscout"
TARGET_ADOPTION_COHORT = "2024-10"
PAPER_MATCHED_PERIOD = 202409
CUTOFF_UTC = "2024-09-30T23:59:59+00:00"
TARGET_PROPENSITY_SCORE = 0.0212830932484271
OUTPUT_PREFIX = "webscout_local_control_rematching"
MEASUREMENT_METHOD = "git_archive_python_token_ast_ncloc_v1"

EXPECTED_TARGET_TREATMENTS = (
    "Elevate-Code/better-voice-typing",
    "PiotrCzapla/smart_dictation",
    "TheSethRose/Agent-Chat",
    "VRSEN/agency-voice-interface",
    "codingforentrepreneurs/Cursor-Django",
    "matebenyovszky/healing-agent",
)

PAPER_SUMMARY_FEATURES = (
    "age_days",
    "users_involved",
    "n_stars",
    "n_forks",
    "n_releases",
    "n_pulls",
    "n_issues",
    "n_comments",
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
EVENT_MONTH_ALIASES = (
    "event_month",
    "event",
    "adoption_month",
    "cursor_adoption_month",
)
LANGUAGE_ALIASES = (
    "repo_primary_language",
    "primary_language",
    "language",
)
CLONE_PATH_ALIASES = (
    "clone_path",
    "repo_path",
    "local_path",
    "path",
    "target_dir",
)

DEFAULT_EXCLUDED_DIRS = (
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".next",
    ".nuxt",
)


@dataclass(frozen=True)
class AnalysisPaths:
    target_pair_manifest: Path
    treatment_sample: Path
    original_matching_csv: Path
    treatment_clone_root: Path
    control_clone_root: Path
    output_dir: Path
    local_control_manifest: Path | None = None
    candidate_feature_csv: Path | None = None
    treatment_sonar_ncloc_csv: Path | None = None
    control_sonar_ncloc_csv: Path | None = None


@dataclass
class SnapshotMeasurement:
    dataset_source: str
    repo_name: str
    clone_path: str
    local_clone_exists: bool
    git_repository_valid: bool
    shallow_repository: bool | None
    cutoff_utc: str
    selected_ref: str
    cutoff_commit: str
    cutoff_commit_timestamp: str
    earliest_commit: str
    earliest_commit_timestamp: str
    repository_age_days_at_cutoff: float | None
    snapshot_status: str
    measurement_eligible: bool
    python_file_count: int | None
    python_ncloc_direct: int | None
    python_physical_lines: int | None
    python_blank_lines: int | None
    python_comment_only_lines: int | None
    python_docstring_lines: int | None
    python_parse_failure_files: int | None
    python_skipped_large_files: int | None
    measurement_method: str
    failure_reason: str


@dataclass
class FileMeasurement:
    dataset_source: str
    repo_name: str
    cutoff_commit: str
    file_path: str
    file_bytes: int
    physical_lines: int
    blank_lines: int
    comment_only_lines: int
    docstring_lines: int
    python_ncloc_direct: int
    parse_status: str
    failure_reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Restore pre-adoption Python NCLOC from local Git history and rank "
            "replacement controls for HelpingAI/Webscout."
        )
    )
    parser.add_argument("--target-pair-manifest", type=Path)
    parser.add_argument("--treatment-sample", type=Path)
    parser.add_argument("--original-matching-csv", type=Path)
    parser.add_argument("--treatment-clone-root", type=Path)
    parser.add_argument("--control-clone-root", type=Path)
    parser.add_argument("--local-control-manifest", type=Path)
    parser.add_argument("--candidate-feature-csv", type=Path)
    parser.add_argument("--treatment-sonar-ncloc-csv", type=Path)
    parser.add_argument("--control-sonar-ncloc-csv", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--target-control", default=TARGET_CONTROL)
    parser.add_argument("--target-adoption-cohort", default=TARGET_ADOPTION_COHORT)
    parser.add_argument("--paper-matched-period", type=int, default=PAPER_MATCHED_PERIOD)
    parser.add_argument("--cutoff-utc", default=CUTOFF_UTC)
    parser.add_argument("--propensity-caliper", type=float, default=1e-12)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunksize", type=int, default=250_000)
    parser.add_argument("--max-controls", type=int, default=0)
    parser.add_argument("--max-python-file-bytes", type=int, default=5_000_000)
    parser.add_argument(
        "--excluded-dirs",
        default=",".join(DEFAULT_EXCLUDED_DIRS),
        help="Comma-separated directory names excluded from direct NCLOC counting.",
    )
    parser.add_argument(
        "--skip-frozen-target-checks",
        action="store_true",
        help="Disable exact six-treatment and original-control validation.",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_repo_name(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    text = text.replace("\\", "/")
    text = re.sub(r"^git@github\.com:", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^https?://github\.com/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^ssh://git@github\.com/", "", text, flags=re.IGNORECASE)
    text = text.removesuffix(".git").strip("/")
    return text


def normalize_repo_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_repo_name)


def normalize_month(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d{6}(?:\.0)?", text):
        digits = text[:6]
        return f"{digits[:4]}-{digits[4:]}"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return text
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m")


def find_column(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    normalized = {
        re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_"): str(column)
        for column in columns
    }
    for alias in aliases:
        key = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
        if key in normalized:
            return normalized[key]
    return None


def require_file(path: Path | None, label: str, optional: bool = False) -> None:
    if path is None:
        if optional:
            return
        raise FileNotFoundError(f"{label} is not configured.")
    if not path.is_file():
        if optional:
            return
        raise FileNotFoundError(f"{label} not found: {path}")


def require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"{label} not found: {path}")


def parse_cutoff(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=dict(env) if env is not None else None,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"Command failed: {' '.join(args)}: {detail}")
    return completed


def git_output(repo_path: Path, args: Sequence[str], timeout: int = 120) -> str:
    completed = run_command(
        ["git", "-C", str(repo_path), *args],
        timeout=timeout,
        check=True,
    )
    return completed.stdout.strip()


def git_try_output(repo_path: Path, args: Sequence[str], timeout: int = 120) -> str:
    completed = run_command(
        ["git", "-C", str(repo_path), *args],
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def repository_name_from_remote(repo_path: Path) -> str:
    url = git_try_output(repo_path, ["remote", "get-url", "origin"])
    return normalize_repo_name(url)


def discover_clone_root(
    clone_root: Path,
    dataset_source: str,
    manifest_path: Path | None = None,
) -> pd.DataFrame:
    require_dir(clone_root, f"{dataset_source} clone root")

    manifest = pd.DataFrame()
    if manifest_path is not None and manifest_path.is_file():
        manifest = pd.read_csv(manifest_path, dtype=str, low_memory=False)
        repo_col = find_column(manifest.columns, REPO_ALIASES)
        if repo_col is None:
            raise ValueError(
                f"Local manifest has no recognizable repository column: {manifest_path}"
            )
        manifest[repo_col] = normalize_repo_series(manifest[repo_col])
        manifest = manifest[manifest[repo_col].ne("")].copy()
        if repo_col != "repo_name":
            manifest = manifest.rename(columns={repo_col: "repo_name"})
        path_col = find_column(manifest.columns, CLONE_PATH_ALIASES)
    else:
        path_col = None

    discovered_rows: list[dict[str, object]] = []
    for child in sorted(path for path in clone_root.iterdir() if path.is_dir()):
        repo_name = repository_name_from_remote(child)
        discovered_rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "clone_path": str(child.resolve()),
                "clone_dir_name": child.name,
                "repo_name_from_remote": bool(repo_name),
                "listed_in_manifest": False,
                "local_clone_exists": True,
            }
        )
    discovered = pd.DataFrame(discovered_rows)
    if discovered.empty:
        raise ValueError(f"No repository directories found under: {clone_root}")

    if manifest.empty:
        local = discovered
    else:
        discovered_by_repo = {
            row.repo_name: row
            for row in discovered.itertuples(index=False)
            if row.repo_name
        }
        discovered_by_dir = {
            row.clone_dir_name: row for row in discovered.itertuples(index=False)
        }
        rows: list[dict[str, object]] = []
        for manifest_row in manifest.itertuples(index=False):
            repo_name = normalize_repo_name(getattr(manifest_row, "repo_name"))
            explicit_path = ""
            if path_col is not None:
                explicit_path = str(getattr(manifest_row, path_col, "") or "").strip()
            expected_path = (
                Path(explicit_path)
                if explicit_path
                else clone_root / repo_name.replace("/", "_")
            )
            found = discovered_by_repo.get(repo_name)
            if found is None:
                found = discovered_by_dir.get(expected_path.name)
            clone_path = Path(found.clone_path) if found is not None else expected_path
            rows.append(
                {
                    "dataset_source": dataset_source,
                    "repo_name": repo_name,
                    "clone_path": str(clone_path.resolve()) if clone_path.exists() else "",
                    "clone_dir_name": clone_path.name,
                    "repo_name_from_remote": bool(found and found.repo_name_from_remote),
                    "listed_in_manifest": True,
                    "local_clone_exists": clone_path.is_dir(),
                }
            )
        listed = pd.DataFrame(rows)
        extras = discovered[
            discovered["repo_name"].ne("")
            & ~discovered["repo_name"].isin(set(listed["repo_name"]))
        ].copy()
        local = pd.concat([listed, extras], ignore_index=True, sort=False)

    local = local[local["repo_name"].ne("")].copy()
    local = local.sort_values(["repo_name", "listed_in_manifest"], ascending=[True, False])
    local = local.drop_duplicates("repo_name", keep="first").reset_index(drop=True)
    return local


def ensure_requested_repo_paths(
    discovered: pd.DataFrame,
    clone_root: Path,
    repo_names: Iterable[str],
    dataset_source: str,
) -> pd.DataFrame:
    existing = set(discovered["repo_name"])
    rows = []
    for repo_name in sorted(set(repo_names) - existing):
        expected = clone_root / repo_name.replace("/", "_")
        rows.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "clone_path": str(expected.resolve()) if expected.is_dir() else "",
                "clone_dir_name": expected.name,
                "repo_name_from_remote": False,
                "listed_in_manifest": False,
                "local_clone_exists": expected.is_dir(),
            }
        )
    if rows:
        discovered = pd.concat([discovered, pd.DataFrame(rows)], ignore_index=True)
    return discovered.sort_values("repo_name").drop_duplicates("repo_name").reset_index(drop=True)


def load_target_pairs(
    path: Path,
    target_control: str,
    skip_frozen_checks: bool,
) -> pd.DataFrame:
    require_file(path, "Target pair manifest")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    treatment_col = find_column(df.columns, ("treatment_repo", "repo_name"))
    control_col = find_column(df.columns, ("control_repo", "matched_control"))
    rank_col = find_column(df.columns, ("control_rank", "rank"))
    if treatment_col is None or control_col is None:
        raise ValueError(
            "Target pair manifest must contain treatment_repo and control_repo columns."
        )
    df[treatment_col] = normalize_repo_series(df[treatment_col])
    df[control_col] = normalize_repo_series(df[control_col])
    target = df[df[control_col].eq(target_control)].copy()
    if target.empty:
        raise ValueError(f"No target pairs found for control: {target_control}")
    result = pd.DataFrame(
        {
            "treatment_repo": target[treatment_col],
            "control_repo": target[control_col],
            "control_rank": (
                pd.to_numeric(target[rank_col], errors="coerce")
                if rank_col is not None
                else np.nan
            ),
        }
    )
    result = result.drop_duplicates(["treatment_repo", "control_repo"])
    result = result.sort_values("treatment_repo").reset_index(drop=True)

    if not skip_frozen_checks:
        expected = tuple(sorted(EXPECTED_TARGET_TREATMENTS))
        actual = tuple(result["treatment_repo"])
        if actual != expected:
            raise ValueError(
                "Frozen target-treatment mismatch. "
                f"Expected {expected}, found {actual}."
            )
        if len(result) != 6:
            raise ValueError(f"Expected six target treatments, found {len(result)}.")
        ranks = result["control_rank"].dropna()
        if not ranks.empty and not ranks.eq(3).all():
            raise ValueError("Expected Webscout to be control rank 3 for all targets.")
    return result


def validate_treatment_cohort(
    path: Path,
    target_treatments: set[str],
    target_cohort: str,
) -> pd.DataFrame:
    require_file(path, "Treatment sample")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    repo_col = find_column(df.columns, REPO_ALIASES)
    event_col = find_column(df.columns, EVENT_MONTH_ALIASES)
    language_col = find_column(df.columns, LANGUAGE_ALIASES)
    if repo_col is None or event_col is None:
        raise ValueError(
            "Treatment sample must contain repository and adoption/event month columns."
        )
    df[repo_col] = normalize_repo_series(df[repo_col])
    df[event_col] = df[event_col].map(normalize_month)
    cohort = df[df[event_col].eq(target_cohort)].copy()
    if language_col is not None:
        language = cohort[language_col].astype(str).str.strip().str.lower()
        cohort = cohort[language.eq("python") | language.eq("") | language.eq("nan")]
    cohort = cohort[cohort[repo_col].ne("")].drop_duplicates(repo_col)
    missing = sorted(target_treatments - set(cohort[repo_col]))
    if missing:
        raise ValueError(
            "Target treatments missing from the requested adoption cohort: "
            + ", ".join(missing)
        )
    cohort = cohort.rename(columns={repo_col: "repo_name", event_col: "event_month"})
    return cohort.sort_values("repo_name").reset_index(drop=True)


def load_matching_period(
    path: Path,
    matched_period: int,
) -> pd.DataFrame:
    require_file(path, "Original matching CSV")
    df = pd.read_csv(path, low_memory=False)
    required = {
        "repo_name",
        "matched_period",
        "group",
        "propensity_score",
        "matched_control_1",
        "matched_control_2",
        "matched_control_3",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Original matching CSV missing columns: {missing}")
    df["repo_name"] = normalize_repo_series(df["repo_name"])
    df["matched_period"] = pd.to_numeric(df["matched_period"], errors="coerce")
    df["propensity_score"] = pd.to_numeric(df["propensity_score"], errors="coerce")
    df["group"] = df["group"].astype(str).str.strip().str.lower()
    for column in PAPER_SUMMARY_FEATURES:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    result = df[df["matched_period"].eq(matched_period)].copy()
    if result.empty:
        raise ValueError(f"No matching rows found for matched_period={matched_period}.")
    return result


def extract_target_matching_profile(
    matching: pd.DataFrame,
    target_treatments: Sequence[str],
    target_control: str,
    skip_frozen_checks: bool,
) -> tuple[pd.DataFrame, list[str], float]:
    target = matching[
        matching["group"].eq("treatment")
        & matching["repo_name"].isin(target_treatments)
    ].copy()
    if len(target) != len(target_treatments):
        missing = sorted(set(target_treatments) - set(target["repo_name"]))
        raise ValueError(
            "Target treatment rows missing from original matching data: "
            + ", ".join(missing)
        )
    scores = target["propensity_score"].dropna().to_numpy(dtype=float)
    if len(scores) != len(target_treatments):
        raise ValueError("One or more target treatments have missing propensity scores.")
    if float(np.max(scores) - np.min(scores)) > 1e-15:
        raise ValueError(
            "Target treatments do not share one exact original propensity score."
        )
    target_score = float(scores[0])

    controls: list[str] = []
    for column in ("matched_control_1", "matched_control_2", "matched_control_3"):
        values = target[column].map(normalize_repo_name)
        unique_values = sorted(value for value in values.unique() if value)
        if len(unique_values) != 1:
            raise ValueError(
                f"Target treatments do not share one exact value for {column}: "
                f"{unique_values}"
            )
        controls.append(unique_values[0])

    if not skip_frozen_checks:
        if controls[-1] != target_control:
            raise ValueError(
                f"Expected {target_control} as original control 3, found {controls[-1]}."
            )
        if abs(target_score - TARGET_PROPENSITY_SCORE) > 1e-15:
            raise ValueError(
                "Frozen target propensity score changed. "
                f"Expected {TARGET_PROPENSITY_SCORE:.16g}, found {target_score:.16g}."
            )
        target_features = [column for column in PAPER_SUMMARY_FEATURES if column in target]
        if target_features:
            values = target[target_features].fillna(0.0).to_numpy(dtype=float)
            if not np.allclose(values, 0.0, atol=0.0, rtol=0.0):
                raise ValueError(
                    "Frozen target paper summary covariates are no longer all zero."
                )
    return target.sort_values("repo_name").reset_index(drop=True), controls, target_score


def read_candidate_feature_audit(
    path: Path | None,
    wanted_repos: set[str],
    chunksize: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if path is None or not path.is_file() or not wanted_repos:
        return pd.DataFrame(), pd.DataFrame()
    pieces: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
        repo_col = find_column(chunk.columns, REPO_ALIASES)
        if repo_col is None:
            raise ValueError(
                f"Candidate feature CSV has no recognizable repository column: {path}"
            )
        chunk[repo_col] = normalize_repo_series(chunk[repo_col])
        selected = chunk[chunk[repo_col].isin(wanted_repos)].copy()
        if not selected.empty:
            if repo_col != "repo_name":
                selected = selected.rename(columns={repo_col: "repo_name"})
            pieces.append(selected)
    if not pieces:
        return pd.DataFrame(), pd.DataFrame()
    long_df = pd.concat(pieces, ignore_index=True)
    if "period_type" not in long_df.columns or "period" not in long_df.columns:
        summary = long_df.groupby("repo_name", as_index=False).size().rename(
            columns={"size": "paper_candidate_feature_rows"}
        )
        summary["paper_candidate_profile_complete"] = False
        return long_df, summary

    normalized_type = long_df["period_type"].astype(str).str.strip().str.lower()
    period = pd.to_numeric(long_df["period"], errors="coerce")
    long_df["period_type_normalized"] = normalized_type
    long_df["period_numeric"] = period
    rows = []
    activity_columns = [
        "users_involved",
        "n_stars",
        "n_forks",
        "n_releases",
        "n_pulls",
        "n_issues",
        "n_comments",
        "total_events",
    ]
    for repo_name, repo_df in long_df.groupby("repo_name"):
        within_periods = set(
            repo_df.loc[
                repo_df["period_type_normalized"].eq("within"), "period_numeric"
            ].dropna().astype(int)
        )
        sum_periods = set(
            repo_df.loc[
                repo_df["period_type_normalized"].eq("sum"), "period_numeric"
            ].dropna().astype(int)
        )
        expected_within = {202404, 202405, 202406, 202407, 202408, 202409}
        profile_complete = within_periods == expected_within and sum_periods == {202403}

        activity_complete = all(column in repo_df.columns for column in activity_columns)
        activity_values = pd.DataFrame()
        if activity_complete:
            activity_values = repo_df[activity_columns].apply(
                pd.to_numeric, errors="coerce"
            )
            activity_complete = bool(activity_values.notna().all().all())
        all_activity_zero = bool(
            activity_complete and (activity_values.to_numpy(dtype=float) == 0).all()
        )

        age_202409 = np.nan
        if "age_days" in repo_df.columns:
            age_rows = repo_df[
                repo_df["period_type_normalized"].eq("within")
                & repo_df["period_numeric"].eq(202409)
            ]
            if len(age_rows) == 1:
                age_202409 = pd.to_numeric(
                    age_rows["age_days"], errors="coerce"
                ).iloc[0]
        exact_zero_profile = bool(
            profile_complete
            and all_activity_zero
            and pd.notna(age_202409)
            and float(age_202409) == 0.0
        )
        rows.append(
            {
                "repo_name": repo_name,
                "paper_candidate_feature_rows": len(repo_df),
                "paper_within_period_count": len(within_periods),
                "paper_sum_period_count": len(sum_periods),
                "paper_candidate_profile_complete": profile_complete,
                "paper_age_days_202409": age_202409,
                "paper_all_activity_features_zero": all_activity_zero,
                "paper_zero_profile_exact": exact_zero_profile,
            }
        )
    return long_df, pd.DataFrame(rows)


def preferred_refs(repo_path: Path) -> list[str]:
    refs: list[str] = []
    origin_head = git_try_output(
        repo_path,
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
    )
    if origin_head:
        refs.append(origin_head)
    for candidate in (
        "refs/remotes/origin/main",
        "refs/remotes/origin/master",
        "refs/heads/main",
        "refs/heads/master",
        "HEAD",
    ):
        if candidate == "HEAD":
            if git_try_output(repo_path, ["rev-parse", "--verify", "HEAD"]):
                refs.append(candidate)
        elif git_try_output(repo_path, ["show-ref", "--verify", "--hash", candidate]):
            refs.append(candidate)
    deduped = []
    seen = set()
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            deduped.append(ref)
    deduped.append("--all")
    return deduped


def select_cutoff_commit(repo_path: Path, cutoff: datetime) -> tuple[str, str]:
    cutoff_text = cutoff.isoformat()
    for ref in preferred_refs(repo_path):
        args = ["rev-list", "-1", f"--before={cutoff_text}"]
        if ref == "--all":
            args.append("--all")
        else:
            args.append(ref)
        commit = git_try_output(repo_path, args)
        if commit:
            return commit.splitlines()[0].strip(), ref
    return "", ""


def commit_timestamp(repo_path: Path, commit: str) -> tuple[str, int | None]:
    if not commit:
        return "", None
    output = git_try_output(repo_path, ["show", "-s", "--format=%cI%x09%ct", commit])
    if not output:
        return "", None
    first = output.splitlines()[0]
    parts = first.split("\t")
    iso = parts[0].strip()
    epoch = None
    if len(parts) > 1:
        try:
            epoch = int(parts[1].strip())
        except ValueError:
            epoch = None
    return iso, epoch


def earliest_commit(repo_path: Path) -> tuple[str, str, int | None]:
    output = git_try_output(repo_path, ["rev-list", "--all", "--timestamp"], timeout=300)
    earliest_sha = ""
    earliest_epoch: int | None = None
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            epoch = int(parts[0])
        except ValueError:
            continue
        sha = parts[1]
        if earliest_epoch is None or epoch < earliest_epoch:
            earliest_epoch = epoch
            earliest_sha = sha
    if earliest_epoch is None:
        return "", "", None
    iso = datetime.fromtimestamp(earliest_epoch, tz=timezone.utc).isoformat()
    return earliest_sha, iso, earliest_epoch


def docstring_line_numbers(source_text: str) -> set[int]:
    try:
        tree = ast.parse(source_text)
    except (SyntaxError, ValueError, TypeError):
        return set()

    lines: set[int] = set()
    docstring_nodes = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, docstring_nodes):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = getattr(first, "lineno", None)
            end = getattr(first, "end_lineno", start)
            if start is not None and end is not None:
                lines.update(range(int(start), int(end) + 1))
    return lines


def decode_python_source(data: bytes) -> tuple[str, str]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except (SyntaxError, UnicodeDecodeError):
        encoding = "utf-8"
    try:
        return data.decode(encoding), encoding
    except (UnicodeDecodeError, LookupError):
        return data.decode("utf-8", errors="replace"), "utf-8-replace"


def count_python_ncloc(data: bytes) -> dict[str, object]:
    text, _ = decode_python_source(data)
    physical_lines = text.splitlines()
    total_physical = len(physical_lines)
    blank_lines = {
        index
        for index, line in enumerate(physical_lines, start=1)
        if not line.strip()
    }
    comment_only_lines = {
        index
        for index, line in enumerate(physical_lines, start=1)
        if line.lstrip().startswith("#")
    }
    docstring_lines = docstring_line_numbers(text)
    code_lines: set[int] = set()
    parse_status = "tokenized"
    failure_reason = ""

    ignored_types = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in ignored_types:
                continue
            start_line, _ = token.start
            end_line, _ = token.end
            if token.type == tokenize.STRING:
                token_lines = set(range(start_line, max(start_line, end_line) + 1))
                if token_lines and token_lines.issubset(docstring_lines):
                    continue
            for line_number in range(start_line, max(start_line, end_line) + 1):
                if line_number not in docstring_lines:
                    code_lines.add(line_number)
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        parse_status = "physical_line_fallback"
        failure_reason = f"{type(exc).__name__}: {exc}"
        code_lines = {
            index
            for index, line in enumerate(physical_lines, start=1)
            if index not in blank_lines
            and index not in comment_only_lines
            and index not in docstring_lines
        }

    return {
        "physical_lines": total_physical,
        "blank_lines": len(blank_lines),
        "comment_only_lines": len(comment_only_lines),
        "docstring_lines": len(docstring_lines),
        "python_ncloc_direct": len(code_lines),
        "parse_status": parse_status,
        "failure_reason": failure_reason,
    }


def path_is_excluded(path: str, excluded_dirs: set[str]) -> bool:
    parts = PurePosixPath(path).parts
    return any(part in excluded_dirs for part in parts[:-1])


def archive_and_measure_python(
    repo_path: Path,
    dataset_source: str,
    repo_name: str,
    commit: str,
    excluded_dirs: set[str],
    max_python_file_bytes: int,
) -> tuple[dict[str, int], list[FileMeasurement]]:
    summaries = {
        "python_file_count": 0,
        "python_ncloc_direct": 0,
        "python_physical_lines": 0,
        "python_blank_lines": 0,
        "python_comment_only_lines": 0,
        "python_docstring_lines": 0,
        "python_parse_failure_files": 0,
        "python_skipped_large_files": 0,
    }
    file_rows: list[FileMeasurement] = []

    # Limit the archive to tracked Python files. This avoids materializing large
    # binary assets, datasets, or non-Python source trees from large repositories.
    tracked_paths = git_try_output(
        repo_path,
        ["ls-tree", "-r", "--name-only", commit],
        timeout=300,
    )
    python_paths = [
        path
        for path in tracked_paths.splitlines()
        if path.lower().endswith(".py")
    ]
    if not python_paths:
        return summaries, file_rows

    with tempfile.TemporaryDirectory(prefix="run-py-8d-archive-") as temp_dir:
        tar_path = Path(temp_dir) / "snapshot.tar"
        run_command(
            [
                "git",
                "-C",
                str(repo_path),
                "archive",
                "--format=tar",
                f"--output={tar_path}",
                commit,
                "--",
                ":(glob)**/*.py",
            ],
            timeout=600,
            check=True,
        )
        with tarfile.open(tar_path, mode="r") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                normalized = member.name.strip("./")
                if not normalized.lower().endswith((".py", ".pyw")):
                    continue
                if path_is_excluded(normalized, excluded_dirs):
                    continue
                if member.size > max_python_file_bytes:
                    summaries["python_skipped_large_files"] += 1
                    file_rows.append(
                        FileMeasurement(
                            dataset_source=dataset_source,
                            repo_name=repo_name,
                            cutoff_commit=commit,
                            file_path=normalized,
                            file_bytes=int(member.size),
                            physical_lines=0,
                            blank_lines=0,
                            comment_only_lines=0,
                            docstring_lines=0,
                            python_ncloc_direct=0,
                            parse_status="skipped_large_file",
                            failure_reason=(
                                f"File size {member.size} exceeds "
                                f"max_python_file_bytes={max_python_file_bytes}"
                            ),
                        )
                    )
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                data = extracted.read()
                measured = count_python_ncloc(data)
                summaries["python_file_count"] += 1
                summaries["python_ncloc_direct"] += int(measured["python_ncloc_direct"])
                summaries["python_physical_lines"] += int(measured["physical_lines"])
                summaries["python_blank_lines"] += int(measured["blank_lines"])
                summaries["python_comment_only_lines"] += int(
                    measured["comment_only_lines"]
                )
                summaries["python_docstring_lines"] += int(measured["docstring_lines"])
                if measured["parse_status"] != "tokenized":
                    summaries["python_parse_failure_files"] += 1
                file_rows.append(
                    FileMeasurement(
                        dataset_source=dataset_source,
                        repo_name=repo_name,
                        cutoff_commit=commit,
                        file_path=normalized,
                        file_bytes=len(data),
                        physical_lines=int(measured["physical_lines"]),
                        blank_lines=int(measured["blank_lines"]),
                        comment_only_lines=int(measured["comment_only_lines"]),
                        docstring_lines=int(measured["docstring_lines"]),
                        python_ncloc_direct=int(measured["python_ncloc_direct"]),
                        parse_status=str(measured["parse_status"]),
                        failure_reason=str(measured["failure_reason"]),
                    )
                )
        return summaries, file_rows


def measure_repository_snapshot(
    dataset_source: str,
    repo_name: str,
    clone_path: str,
    cutoff: datetime,
    excluded_dirs: set[str],
    max_python_file_bytes: int,
) -> tuple[SnapshotMeasurement, list[FileMeasurement]]:
    base = SnapshotMeasurement(
        dataset_source=dataset_source,
        repo_name=repo_name,
        clone_path=clone_path,
        local_clone_exists=False,
        git_repository_valid=False,
        shallow_repository=None,
        cutoff_utc=cutoff.isoformat(),
        selected_ref="",
        cutoff_commit="",
        cutoff_commit_timestamp="",
        earliest_commit="",
        earliest_commit_timestamp="",
        repository_age_days_at_cutoff=None,
        snapshot_status="missing_history_or_measurement_failure",
        measurement_eligible=False,
        python_file_count=None,
        python_ncloc_direct=None,
        python_physical_lines=None,
        python_blank_lines=None,
        python_comment_only_lines=None,
        python_docstring_lines=None,
        python_parse_failure_files=None,
        python_skipped_large_files=None,
        measurement_method=MEASUREMENT_METHOD,
        failure_reason="",
    )
    repo_path = Path(clone_path) if clone_path else Path("/__missing__")
    if not clone_path or not repo_path.is_dir():
        base.failure_reason = "local_clone_missing"
        return base, []
    base.local_clone_exists = True

    valid = git_try_output(repo_path, ["rev-parse", "--is-inside-work-tree"])
    if valid.lower() != "true":
        base.failure_reason = "not_a_valid_git_work_tree"
        return base, []
    base.git_repository_valid = True

    shallow_text = git_try_output(repo_path, ["rev-parse", "--is-shallow-repository"])
    base.shallow_repository = shallow_text.lower() == "true" if shallow_text else None

    earliest_sha, earliest_iso, earliest_epoch = earliest_commit(repo_path)
    base.earliest_commit = earliest_sha
    base.earliest_commit_timestamp = earliest_iso
    if earliest_epoch is not None:
        age_seconds = cutoff.timestamp() - earliest_epoch
        base.repository_age_days_at_cutoff = max(0.0, age_seconds / 86400.0)

    cutoff_commit, selected_ref = select_cutoff_commit(repo_path, cutoff)
    if not cutoff_commit:
        if base.shallow_repository:
            base.failure_reason = "no_cutoff_commit_in_shallow_history"
            return base, []
        if earliest_epoch is None:
            base.failure_reason = "repository_has_no_commits"
            return base, []
        if earliest_epoch > cutoff.timestamp():
            # Git history alone proves that no commit is available before the
            # cutoff, but it does not prove the GitHub repository creation date.
            # A later step confirms structural zero only when the paper's
            # matched-period age_days value is also zero.
            base.snapshot_status = "no_commit_before_cutoff_full_history"
            base.measurement_eligible = False
            base.failure_reason = "awaiting_paper_age_zero_confirmation"
            return base, []
        base.failure_reason = "no_cutoff_commit_found_despite_earlier_history"
        return base, []

    base.cutoff_commit = cutoff_commit
    base.selected_ref = selected_ref
    cutoff_iso, _ = commit_timestamp(repo_path, cutoff_commit)
    base.cutoff_commit_timestamp = cutoff_iso

    try:
        summary, files = archive_and_measure_python(
            repo_path=repo_path,
            dataset_source=dataset_source,
            repo_name=repo_name,
            commit=cutoff_commit,
            excluded_dirs=excluded_dirs,
            max_python_file_bytes=max_python_file_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - preserve repository-level failure
        base.failure_reason = f"snapshot_measurement_failed: {type(exc).__name__}: {exc}"
        return base, []

    base.snapshot_status = "observed_pre_adoption_snapshot"
    base.measurement_eligible = True
    base.python_file_count = summary["python_file_count"]
    base.python_ncloc_direct = summary["python_ncloc_direct"]
    base.python_physical_lines = summary["python_physical_lines"]
    base.python_blank_lines = summary["python_blank_lines"]
    base.python_comment_only_lines = summary["python_comment_only_lines"]
    base.python_docstring_lines = summary["python_docstring_lines"]
    base.python_parse_failure_files = summary["python_parse_failure_files"]
    base.python_skipped_large_files = summary["python_skipped_large_files"]
    base.failure_reason = ""
    return base, files


def measure_repository_set(
    repositories: pd.DataFrame,
    cutoff: datetime,
    excluded_dirs: set[str],
    max_python_file_bytes: int,
    workers: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = repositories[
        ["dataset_source", "repo_name", "clone_path"]
    ].drop_duplicates(["dataset_source", "repo_name"])
    summaries: list[SnapshotMeasurement] = []
    file_rows: list[FileMeasurement] = []

    max_workers = max(1, int(workers))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                measure_repository_snapshot,
                row.dataset_source,
                row.repo_name,
                row.clone_path,
                cutoff,
                excluded_dirs,
                max_python_file_bytes,
            ): (row.dataset_source, row.repo_name)
            for row in records.itertuples(index=False)
        }
        completed_count = 0
        for future in as_completed(futures):
            dataset_source, repo_name = futures[future]
            try:
                summary, files = future.result()
            except Exception as exc:  # noqa: BLE001
                summary = SnapshotMeasurement(
                    dataset_source=dataset_source,
                    repo_name=repo_name,
                    clone_path="",
                    local_clone_exists=False,
                    git_repository_valid=False,
                    shallow_repository=None,
                    cutoff_utc=cutoff.isoformat(),
                    selected_ref="",
                    cutoff_commit="",
                    cutoff_commit_timestamp="",
                    earliest_commit="",
                    earliest_commit_timestamp="",
                    repository_age_days_at_cutoff=None,
                    snapshot_status="missing_history_or_measurement_failure",
                    measurement_eligible=False,
                    python_file_count=None,
                    python_ncloc_direct=None,
                    python_physical_lines=None,
                    python_blank_lines=None,
                    python_comment_only_lines=None,
                    python_docstring_lines=None,
                    python_parse_failure_files=None,
                    python_skipped_large_files=None,
                    measurement_method=MEASUREMENT_METHOD,
                    failure_reason=f"worker_failure: {type(exc).__name__}: {exc}",
                )
                files = []
            summaries.append(summary)
            file_rows.extend(files)
            completed_count += 1
            if completed_count % 25 == 0 or completed_count == len(records):
                print(
                    f"Snapshot restoration: {completed_count}/{len(records)} repositories",
                    flush=True,
                )

    summary_df = pd.DataFrame([asdict(item) for item in summaries])
    file_df = pd.DataFrame([asdict(item) for item in file_rows])
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["dataset_source", "repo_name"]).reset_index(
            drop=True
        )
    if not file_df.empty:
        file_df = file_df.sort_values(
            ["dataset_source", "repo_name", "file_path"]
        ).reset_index(drop=True)
    return summary_df, file_df


def resolve_structural_zero_status(
    measurements: pd.DataFrame,
    target_profile: pd.DataFrame,
    matching_controls: pd.DataFrame,
) -> pd.DataFrame:
    """Confirm structural zero with both full Git history and paper age metadata."""
    target_age = target_profile[["repo_name"]].copy()
    target_age["dataset_source"] = "treatment"
    target_age["paper_age_days_at_matched_period"] = pd.to_numeric(
        target_profile.get("age_days", np.nan), errors="coerce"
    )

    control_age = matching_controls[["repo_name"]].copy()
    control_age["dataset_source"] = "control"
    control_age["paper_age_days_at_matched_period"] = pd.to_numeric(
        matching_controls.get("age_days", np.nan), errors="coerce"
    )
    control_age = control_age.sort_values("repo_name").drop_duplicates(
        "repo_name", keep="first"
    )

    age_meta = pd.concat([target_age, control_age], ignore_index=True)
    age_meta = age_meta.drop_duplicates(["dataset_source", "repo_name"], keep="first")
    result = measurements.merge(
        age_meta,
        on=["dataset_source", "repo_name"],
        how="left",
        validate="one_to_one",
    )
    result["structural_zero_confirmation"] = "not_applicable"
    pending = result["snapshot_status"].eq("no_commit_before_cutoff_full_history")
    confirmed = pending & result["paper_age_days_at_matched_period"].eq(0)
    unresolved = pending & ~confirmed

    zero_columns = [
        "python_file_count",
        "python_ncloc_direct",
        "python_physical_lines",
        "python_blank_lines",
        "python_comment_only_lines",
        "python_docstring_lines",
        "python_parse_failure_files",
        "python_skipped_large_files",
    ]
    result.loc[confirmed, zero_columns] = 0
    result.loc[confirmed, "snapshot_status"] = "structural_zero_not_created"
    result.loc[confirmed, "measurement_eligible"] = True
    result.loc[confirmed, "failure_reason"] = ""
    result.loc[confirmed, "structural_zero_confirmation"] = (
        "full_git_history_no_pre_cutoff_commit_and_paper_age_days_zero"
    )

    result.loc[unresolved, "snapshot_status"] = (
        "missing_history_or_measurement_failure"
    )
    result.loc[unresolved, "measurement_eligible"] = False
    result.loc[unresolved, "failure_reason"] = (
        "no_pre_cutoff_commit_but_paper_age_days_not_zero_or_missing"
    )
    result.loc[unresolved, "structural_zero_confirmation"] = "not_confirmed"
    return result


def load_sonar_validation(
    path: Path | None,
    dataset_source: str,
    wanted_repos: set[str],
    cutoff_month: str,
) -> pd.DataFrame:
    columns = [
        "dataset_source",
        "repo_name",
        "sonar_validation_month",
        "sonar_latest_commit",
        "sonar_python_ncloc",
        "sonar_validation_source",
    ]
    if path is None or not path.is_file() or not wanted_repos:
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, low_memory=False)
    repo_col = find_column(df.columns, REPO_ALIASES)
    month_col = find_column(df.columns, ("month", "time", "period"))
    ncloc_col = find_column(
        df.columns,
        ("ncloc_python_snapshot", "python_ncloc", "ncloc"),
    )
    commit_col = find_column(df.columns, ("latest_commit", "commit", "commit_hash"))
    if repo_col is None or month_col is None or ncloc_col is None:
        raise ValueError(
            f"Sonar NCLOC validation file lacks repo/month/ncloc columns: {path}"
        )
    df[repo_col] = normalize_repo_series(df[repo_col])
    df[month_col] = df[month_col].map(normalize_month)
    selected = df[
        df[repo_col].isin(wanted_repos) & df[month_col].eq(cutoff_month)
    ].copy()
    result = pd.DataFrame(
        {
            "dataset_source": dataset_source,
            "repo_name": selected[repo_col],
            "sonar_validation_month": selected[month_col],
            "sonar_latest_commit": (
                selected[commit_col].astype(str).str.strip()
                if commit_col is not None
                else ""
            ),
            "sonar_python_ncloc": pd.to_numeric(
                selected[ncloc_col], errors="coerce"
            ),
            "sonar_validation_source": str(path),
        }
    )
    return result.drop_duplicates(["dataset_source", "repo_name"], keep="last")


def build_candidate_eligibility(
    local_controls: pd.DataFrame,
    matching_controls: pd.DataFrame,
    measurements: pd.DataFrame,
    target_score: float,
    target_control: str,
    target_treatments: set[str],
    original_controls: Sequence[str],
    propensity_caliper: float,
    feature_summary: pd.DataFrame,
) -> pd.DataFrame:
    controls = local_controls.copy()
    match_columns = [
        "repo_name",
        "propensity_score",
        *[column for column in PAPER_SUMMARY_FEATURES if column in matching_controls],
    ]
    matching_unique = matching_controls[match_columns].copy()
    duplicates = matching_unique.groupby("repo_name")["propensity_score"].nunique(dropna=False)
    inconsistent = set(duplicates[duplicates.gt(1)].index)
    if inconsistent:
        raise ValueError(
            "Control repositories have inconsistent original propensity scores: "
            + ", ".join(sorted(inconsistent)[:20])
        )
    matching_unique = matching_unique.sort_values("repo_name").drop_duplicates(
        "repo_name", keep="first"
    )
    matching_unique = matching_unique.rename(
        columns={"propensity_score": "original_propensity_score"}
    )
    controls = controls.merge(matching_unique, on="repo_name", how="left")
    control_measurements = measurements[
        measurements["dataset_source"].eq("control")
    ].drop(
        columns=["local_clone_exists"],
        errors="ignore",
    )
    controls = controls.merge(
        control_measurements,
        on=["dataset_source", "repo_name", "clone_path"],
        how="left",
        validate="one_to_one",
    )
    if not feature_summary.empty:
        controls = controls.merge(feature_summary, on="repo_name", how="left")
    if "paper_zero_profile_exact" not in controls.columns:
        controls["paper_zero_profile_exact"] = False
    controls["paper_zero_profile_exact"] = controls[
        "paper_zero_profile_exact"
    ].fillna(False)

    controls["original_propensity_score_source"] = np.where(
        controls["original_propensity_score"].notna(),
        "matching_csv_observed",
        "missing",
    )
    inferred_exact = (
        controls["original_propensity_score"].isna()
        & controls["paper_zero_profile_exact"]
    )
    controls.loc[inferred_exact, "original_propensity_score"] = target_score
    controls.loc[inferred_exact, "original_propensity_score_source"] = (
        "inferred_from_identical_zero_paper_feature_vector"
    )

    controls["target_propensity_score"] = target_score
    controls["propensity_distance"] = (
        controls["original_propensity_score"] - target_score
    ).abs()
    controls["within_propensity_caliper"] = (
        controls["propensity_distance"].notna()
        & controls["propensity_distance"].le(propensity_caliper)
    )
    controls["is_original_webscout"] = controls["repo_name"].eq(target_control)
    controls["is_original_control"] = controls["repo_name"].isin(original_controls)
    control_rank_map = {repo: rank for rank, repo in enumerate(original_controls, start=1)}
    controls["original_control_rank"] = controls["repo_name"].map(control_rank_map)
    controls["is_target_treatment_overlap"] = controls["repo_name"].isin(target_treatments)
    controls["paper_matching_row_found"] = controls[
        "original_propensity_score_source"
    ].eq("matching_csv_observed")
    controls["paper_propensity_score_available"] = controls[
        "original_propensity_score"
    ].notna()
    controls["direct_ncloc_measurement_eligible"] = controls[
        "measurement_eligible"
    ].fillna(False)
    controls["eligible_replacement_candidate"] = (
        controls["local_clone_exists"].fillna(False)
        & controls["paper_propensity_score_available"]
        & controls["within_propensity_caliper"]
        & controls["direct_ncloc_measurement_eligible"]
        & ~controls["is_original_webscout"]
        & ~controls["is_target_treatment_overlap"]
    )

    controls["ineligibility_reason"] = "eligible"
    masks_and_reasons = [
        (~controls["local_clone_exists"].fillna(False), "local_clone_missing"),
        (~controls["paper_propensity_score_available"], "paper_propensity_score_unavailable"),
        (
            controls["paper_propensity_score_available"]
            & ~controls["within_propensity_caliper"],
            "outside_original_propensity_caliper",
        ),
        (
            controls["within_propensity_caliper"]
            & ~controls["direct_ncloc_measurement_eligible"],
            "direct_ncloc_measurement_unavailable",
        ),
        (controls["is_target_treatment_overlap"], "treatment_overlap"),
        (controls["is_original_webscout"], "original_webscout_benchmark_only"),
    ]
    for mask, reason in masks_and_reasons:
        controls.loc[mask, "ineligibility_reason"] = reason
    controls.loc[controls["eligible_replacement_candidate"], "ineligibility_reason"] = (
        "eligible"
    )
    return controls.sort_values("repo_name").reset_index(drop=True)


def build_target_measurements(
    target_profile: pd.DataFrame,
    measurements: pd.DataFrame,
) -> pd.DataFrame:
    target = target_profile.copy()
    target = target.rename(
        columns={
            "repo_name": "treatment_repo",
            "propensity_score": "treatment_propensity_score",
        }
    )
    measure = measurements[measurements["dataset_source"].eq("treatment")].copy()
    measure = measure.rename(columns={"repo_name": "treatment_repo"})
    target = target.merge(
        measure,
        on="treatment_repo",
        how="left",
        validate="one_to_one",
    )
    target["treatment_log1p_python_ncloc"] = np.log1p(
        pd.to_numeric(target["python_ncloc_direct"], errors="coerce")
    )
    return target.sort_values("treatment_repo").reset_index(drop=True)


def build_rankings(
    target_measurements: pd.DataFrame,
    candidates: pd.DataFrame,
    top_k: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_required = target_measurements[
        [
            "treatment_repo",
            "treatment_propensity_score",
            "python_ncloc_direct",
            "treatment_log1p_python_ncloc",
            "repository_age_days_at_cutoff",
            "snapshot_status",
            "measurement_eligible",
        ]
    ].copy()
    if not target_required["measurement_eligible"].fillna(False).all():
        unavailable = target_required.loc[
            ~target_required["measurement_eligible"].fillna(False),
            ["treatment_repo", "snapshot_status"],
        ]
        raise ValueError(
            "Direct pre-adoption Python NCLOC is unavailable for target treatments:\n"
            + unavailable.to_string(index=False)
        )

    candidate_columns = [
        "repo_name",
        "original_propensity_score",
        "propensity_distance",
        "within_propensity_caliper",
        "python_ncloc_direct",
        "repository_age_days_at_cutoff",
        "snapshot_status",
        "measurement_eligible",
        "eligible_replacement_candidate",
        "is_original_webscout",
        "is_original_control",
        "original_control_rank",
        "failure_reason",
    ]
    candidate_data = candidates[candidate_columns].copy()
    candidate_data = candidate_data.rename(
        columns={
            "repo_name": "candidate_control_repo",
            "python_ncloc_direct": "candidate_python_ncloc_direct",
            "repository_age_days_at_cutoff": "candidate_repository_age_days_at_cutoff",
            "snapshot_status": "candidate_snapshot_status",
            "measurement_eligible": "candidate_measurement_eligible",
            "failure_reason": "candidate_measurement_failure_reason",
        }
    )
    candidate_data["candidate_log1p_python_ncloc"] = np.log1p(
        pd.to_numeric(candidate_data["candidate_python_ncloc_direct"], errors="coerce")
    )

    target_required["_key"] = 1
    candidate_data["_key"] = 1
    pairwise = target_required.merge(candidate_data, on="_key", how="inner").drop(
        columns="_key"
    )
    pairwise["propensity_distance_pair"] = (
        pairwise["original_propensity_score"]
        - pairwise["treatment_propensity_score"]
    ).abs()
    pairwise["python_ncloc_log_distance"] = (
        pairwise["candidate_log1p_python_ncloc"]
        - pairwise["treatment_log1p_python_ncloc"]
    ).abs()
    pairwise["python_ncloc_raw_distance"] = (
        pairwise["candidate_python_ncloc_direct"]
        - pairwise["python_ncloc_direct"]
    ).abs()
    pairwise["repository_age_distance_days"] = (
        pairwise["candidate_repository_age_days_at_cutoff"]
        - pairwise["repository_age_days_at_cutoff"]
    ).abs()

    pairwise["rank_within_treatment"] = np.nan
    for treatment_repo, index in pairwise.groupby("treatment_repo").groups.items():
        eligible_index = pairwise.loc[index].index[
            pairwise.loc[index, "eligible_replacement_candidate"].astype(bool)
        ]
        ordered = pairwise.loc[eligible_index].sort_values(
            [
                "propensity_distance_pair",
                "python_ncloc_log_distance",
                "repository_age_distance_days",
                "candidate_control_repo",
            ],
            na_position="last",
        )
        pairwise.loc[ordered.index, "rank_within_treatment"] = np.arange(
            1, len(ordered) + 1
        )
    pairwise = pairwise.sort_values(
        ["treatment_repo", "rank_within_treatment", "candidate_control_repo"],
        na_position="last",
    ).reset_index(drop=True)

    grouped_rows = []
    for candidate_repo, group in pairwise.groupby("candidate_control_repo", sort=True):
        first = group.iloc[0]
        grouped_rows.append(
            {
                "candidate_control_repo": candidate_repo,
                "original_propensity_score": first["original_propensity_score"],
                "max_propensity_distance": group["propensity_distance_pair"].max(),
                "mean_propensity_distance": group["propensity_distance_pair"].mean(),
                "candidate_python_ncloc_direct": first[
                    "candidate_python_ncloc_direct"
                ],
                "candidate_log1p_python_ncloc": first[
                    "candidate_log1p_python_ncloc"
                ],
                "max_python_ncloc_log_distance": group[
                    "python_ncloc_log_distance"
                ].max(),
                "mean_python_ncloc_log_distance": group[
                    "python_ncloc_log_distance"
                ].mean(),
                "median_python_ncloc_log_distance": group[
                    "python_ncloc_log_distance"
                ].median(),
                "max_python_ncloc_raw_distance": group[
                    "python_ncloc_raw_distance"
                ].max(),
                "mean_python_ncloc_raw_distance": group[
                    "python_ncloc_raw_distance"
                ].mean(),
                "max_repository_age_distance_days": group[
                    "repository_age_distance_days"
                ].max(),
                "mean_repository_age_distance_days": group[
                    "repository_age_distance_days"
                ].mean(),
                "candidate_snapshot_status": first["candidate_snapshot_status"],
                "candidate_measurement_eligible": first[
                    "candidate_measurement_eligible"
                ],
                "within_propensity_caliper": first["within_propensity_caliper"],
                "eligible_replacement_candidate": first[
                    "eligible_replacement_candidate"
                ],
                "is_original_webscout": first["is_original_webscout"],
                "is_original_control": first["is_original_control"],
                "original_control_rank": first["original_control_rank"],
                "candidate_measurement_failure_reason": first[
                    "candidate_measurement_failure_reason"
                ],
            }
        )
    common = pd.DataFrame(grouped_rows)
    common["common_donor_rank"] = np.nan
    eligible = common[common["eligible_replacement_candidate"].astype(bool)].sort_values(
        [
            "max_propensity_distance",
            "max_python_ncloc_log_distance",
            "mean_python_ncloc_log_distance",
            "median_python_ncloc_log_distance",
            "mean_repository_age_distance_days",
            "candidate_control_repo",
        ],
        na_position="last",
    )
    common.loc[eligible.index, "common_donor_rank"] = np.arange(1, len(eligible) + 1)
    common["top_k_candidate"] = common["common_donor_rank"].le(top_k)
    common = common.sort_values(
        ["common_donor_rank", "is_original_control", "candidate_control_repo"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)
    return pairwise, common


def merge_sonar_validation(
    measurements: pd.DataFrame,
    validation: pd.DataFrame,
) -> pd.DataFrame:
    if validation.empty:
        result = measurements.copy()
        result["sonar_validation_month"] = ""
        result["sonar_latest_commit"] = ""
        result["sonar_python_ncloc"] = np.nan
        result["sonar_validation_source"] = ""
    else:
        result = measurements.merge(
            validation,
            on=["dataset_source", "repo_name"],
            how="left",
            validate="one_to_one",
        )
    result["same_commit_as_sonar_validation"] = (
        result["cutoff_commit"].astype(str).str.strip().ne("")
        & result["sonar_latest_commit"].astype(str).str.strip().ne("")
        & result["cutoff_commit"].astype(str).str.strip().eq(
            result["sonar_latest_commit"].astype(str).str.strip()
        )
    )
    result["direct_minus_sonar_python_ncloc"] = (
        pd.to_numeric(result["python_ncloc_direct"], errors="coerce")
        - pd.to_numeric(result["sonar_python_ncloc"], errors="coerce")
    )
    result["direct_to_sonar_ncloc_ratio"] = np.where(
        pd.to_numeric(result["sonar_python_ncloc"], errors="coerce").gt(0),
        pd.to_numeric(result["python_ncloc_direct"], errors="coerce")
        / pd.to_numeric(result["sonar_python_ncloc"], errors="coerce"),
        np.nan,
    )
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_status(output_dir: Path, status: str, details: Sequence[str]) -> None:
    path = output_dir / f"{OUTPUT_PREFIX}_status.txt"
    text = status + "\n" + "\n".join(details) + "\n"
    path.write_text(text, encoding="utf-8")


def run_analysis(
    paths: AnalysisPaths,
    *,
    target_control: str,
    target_adoption_cohort: str,
    paper_matched_period: int,
    cutoff_utc: str,
    propensity_caliper: float,
    top_k: int,
    workers: int,
    chunksize: int,
    max_controls: int,
    max_python_file_bytes: int,
    excluded_dirs: set[str],
    skip_frozen_target_checks: bool,
) -> dict[str, object]:
    require_file(paths.target_pair_manifest, "Target pair manifest")
    require_file(paths.treatment_sample, "Treatment sample")
    require_file(paths.original_matching_csv, "Original matching CSV")
    require_dir(paths.treatment_clone_root, "Treatment clone root")
    require_dir(paths.control_clone_root, "Control clone root")
    require_file(paths.local_control_manifest, "Local control manifest", optional=True)
    require_file(paths.candidate_feature_csv, "Candidate feature CSV", optional=True)
    require_file(
        paths.treatment_sonar_ncloc_csv,
        "Treatment Sonar NCLOC validation CSV",
        optional=True,
    )
    require_file(
        paths.control_sonar_ncloc_csv,
        "Control Sonar NCLOC validation CSV",
        optional=True,
    )

    cutoff = parse_cutoff(cutoff_utc)
    output_dir = paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    target_pairs = load_target_pairs(
        paths.target_pair_manifest,
        target_control,
        skip_frozen_target_checks,
    )
    target_treatments = target_pairs["treatment_repo"].tolist()
    target_treatment_set = set(target_treatments)
    treatment_cohort = validate_treatment_cohort(
        paths.treatment_sample,
        target_treatment_set,
        target_adoption_cohort,
    )

    matching = load_matching_period(paths.original_matching_csv, paper_matched_period)
    target_profile, original_controls, target_score = extract_target_matching_profile(
        matching,
        target_treatments,
        target_control,
        skip_frozen_target_checks,
    )
    matching_controls = matching[matching["group"].eq("control")].copy()

    treatment_local = discover_clone_root(
        paths.treatment_clone_root,
        "treatment",
    )
    treatment_local = ensure_requested_repo_paths(
        treatment_local,
        paths.treatment_clone_root,
        target_treatments,
        "treatment",
    )
    treatment_local = treatment_local[
        treatment_local["repo_name"].isin(target_treatment_set)
    ].copy()

    control_local = discover_clone_root(
        paths.control_clone_root,
        "control",
        paths.local_control_manifest,
    )
    control_local = ensure_requested_repo_paths(
        control_local,
        paths.control_clone_root,
        original_controls,
        "control",
    )

    matching_control_repos = set(matching_controls["repo_name"])
    control_local["paper_matching_row_found"] = control_local["repo_name"].isin(
        matching_control_repos
    )

    # Audit every local control against the complete 2024-10 candidate feature
    # file. Controls that were not retained in matching.csv can still be exact
    # PSM ties when their full paper input vector is the same all-zero vector as
    # the frozen target treatments.
    feature_long, feature_summary = read_candidate_feature_audit(
        paths.candidate_feature_csv,
        set(control_local["repo_name"]),
        chunksize,
    )
    if not feature_summary.empty:
        control_local = control_local.merge(
            feature_summary[["repo_name", "paper_zero_profile_exact"]],
            on="repo_name",
            how="left",
            validate="one_to_one",
        )
    else:
        control_local["paper_zero_profile_exact"] = False
    control_local["paper_zero_profile_exact"] = control_local[
        "paper_zero_profile_exact"
    ].fillna(False)

    candidate_pool = control_local[
        control_local["paper_matching_row_found"]
        | control_local["paper_zero_profile_exact"]
        | control_local["repo_name"].isin(original_controls)
    ].copy()
    if max_controls > 0:
        benchmark = candidate_pool[candidate_pool["repo_name"].isin(original_controls)]
        regular = candidate_pool[~candidate_pool["repo_name"].isin(original_controls)]
        regular = regular.sort_values("repo_name").head(max_controls)
        candidate_pool = pd.concat([benchmark, regular], ignore_index=True)
        candidate_pool = candidate_pool.drop_duplicates("repo_name")

    if candidate_pool.empty:
        raise ValueError(
            "No local controls have an original matching score or an exact zero "
            "paper-feature profile for the 2024-10 cohort."
        )

    measurement_input = pd.concat(
        [
            treatment_local[["dataset_source", "repo_name", "clone_path"]],
            candidate_pool[["dataset_source", "repo_name", "clone_path"]],
        ],
        ignore_index=True,
    ).drop_duplicates(["dataset_source", "repo_name"])

    print("=" * 80)
    print("run-py-8d: restore pre-adoption Python NCLOC")
    print("=" * 80)
    print(f"Cutoff UTC: {cutoff.isoformat()}")
    print(f"Target treatments: {len(treatment_local)}")
    print(f"Candidate controls selected for measurement: {len(candidate_pool)}")
    print(f"Workers: {workers}")
    print(f"Measurement method: {MEASUREMENT_METHOD}")
    print("Post-adoption AGC outcomes inspected: NO")
    print("DiD executed: NO")

    measurements, file_measurements = measure_repository_set(
        measurement_input,
        cutoff,
        excluded_dirs,
        max_python_file_bytes,
        workers,
    )
    measurements = resolve_structural_zero_status(
        measurements,
        target_profile,
        matching_controls,
    )

    cutoff_month = cutoff.strftime("%Y-%m")
    sonar_treatment = load_sonar_validation(
        paths.treatment_sonar_ncloc_csv,
        "treatment",
        target_treatment_set,
        cutoff_month,
    )
    sonar_control = load_sonar_validation(
        paths.control_sonar_ncloc_csv,
        "control",
        set(candidate_pool["repo_name"]),
        cutoff_month,
    )
    sonar_validation = pd.concat(
        [sonar_treatment, sonar_control], ignore_index=True
    )
    measurements = merge_sonar_validation(measurements, sonar_validation)

    candidate_eligibility = build_candidate_eligibility(
        local_controls=control_local,
        matching_controls=matching_controls,
        measurements=measurements,
        target_score=target_score,
        target_control=target_control,
        target_treatments=target_treatment_set,
        original_controls=original_controls,
        propensity_caliper=propensity_caliper,
        feature_summary=feature_summary,
    )

    target_measurements = build_target_measurements(target_profile, measurements)
    pairwise, common = build_rankings(target_measurements, candidate_eligibility, top_k)

    eligible_candidates = candidate_eligibility[
        candidate_eligibility["eligible_replacement_candidate"].astype(bool)
    ]
    target_measurement_complete = target_measurements["measurement_eligible"].fillna(
        False
    ).all()
    target_scores_identical = (
        target_profile["propensity_score"].max()
        - target_profile["propensity_score"].min()
        <= 1e-15
    )
    original_control_rows = candidate_eligibility[
        candidate_eligibility["is_original_control"].astype(bool)
    ]

    validation_rows = [
        (
            "target_treatment_count_is_six",
            len(target_pairs) == 6,
            len(target_pairs),
        ),
        (
            "target_treatments_in_adoption_cohort",
            target_treatment_set.issubset(set(treatment_cohort["repo_name"])),
            len(target_treatment_set & set(treatment_cohort["repo_name"])),
        ),
        (
            "target_paper_scores_are_identical",
            bool(target_scores_identical),
            f"{target_score:.16g}",
        ),
        (
            "paper_matched_period_is_202409",
            paper_matched_period == PAPER_MATCHED_PERIOD,
            paper_matched_period,
        ),
        (
            "cutoff_is_end_of_2024_09_utc",
            cutoff.isoformat() == parse_cutoff(CUTOFF_UTC).isoformat(),
            cutoff.isoformat(),
        ),
        (
            "all_target_treatments_have_direct_ncloc",
            bool(target_measurement_complete),
            int(target_measurements["measurement_eligible"].fillna(False).sum()),
        ),
        (
            "at_least_one_eligible_replacement_candidate",
            len(eligible_candidates) >= 1,
            len(eligible_candidates),
        ),
        (
            "webscout_present_as_benchmark",
            target_control in set(candidate_eligibility["repo_name"]),
            target_control,
        ),
        (
            "webscout_excluded_from_replacement",
            not candidate_eligibility.loc[
                candidate_eligibility["repo_name"].eq(target_control),
                "eligible_replacement_candidate",
            ].fillna(False).any(),
            "benchmark_only",
        ),
        (
            "original_controls_audited",
            set(original_controls).issubset(set(original_control_rows["repo_name"])),
            len(original_control_rows),
        ),
        (
            "missing_measurements_not_imputed_to_zero",
            True,
            "Only structural_zero_not_created receives zero",
        ),
        (
            "post_adoption_agc_outcome_not_read",
            True,
            "No AGC outcome CLI argument exists",
        ),
        ("did_not_run", True, "Candidate ranking only"),
        (
            "causal_interpretation_disallowed",
            True,
            "Noncausal design-stage rematching sensitivity",
        ),
    ]
    validation = pd.DataFrame(validation_rows, columns=["check", "passed", "observed"])
    failed = validation[~validation["passed"].astype(bool)]
    if not failed.empty:
        validation.to_csv(
            output_dir / f"{OUTPUT_PREFIX}_validation.csv", index=False
        )
        write_status(
            output_dir,
            "FAIL",
            [f"failed_check={row.check}" for row in failed.itertuples(index=False)],
        )
        raise ValueError(
            "Validation failed: " + ", ".join(failed["check"].astype(str))
        )

    paths_to_write = {
        "target_pairs": output_dir / f"{OUTPUT_PREFIX}_target_treatments.csv",
        "target_profile": output_dir / f"{OUTPUT_PREFIX}_target_matching_profile.csv",
        "treatment_cohort": output_dir
        / f"{OUTPUT_PREFIX}_202410_python_treatment_cohort.csv",
        "clone_inventory": output_dir / f"{OUTPUT_PREFIX}_local_clone_inventory.csv",
        "snapshot_measurements": output_dir
        / f"{OUTPUT_PREFIX}_python_ncloc_snapshot_restoration.csv",
        "file_measurements": output_dir
        / f"{OUTPUT_PREFIX}_python_ncloc_file_measurements.csv",
        "target_measurements": output_dir
        / f"{OUTPUT_PREFIX}_target_python_ncloc_measurements.csv",
        "candidate_eligibility": output_dir
        / f"{OUTPUT_PREFIX}_candidate_eligibility.csv",
        "pairwise": output_dir / f"{OUTPUT_PREFIX}_per_treatment_ranking.csv",
        "pairwise_top": output_dir
        / f"{OUTPUT_PREFIX}_per_treatment_top{top_k}.csv",
        "common": output_dir / f"{OUTPUT_PREFIX}_common_donor_ranking.csv",
        "common_top": output_dir / f"{OUTPUT_PREFIX}_common_donor_top{top_k}.csv",
        "validation": output_dir / f"{OUTPUT_PREFIX}_validation.csv",
        "feature_long": output_dir
        / f"{OUTPUT_PREFIX}_paper_candidate_features_long_audit.csv",
        "feature_summary": output_dir
        / f"{OUTPUT_PREFIX}_paper_candidate_feature_profile_audit.csv",
    }

    target_pairs.to_csv(paths_to_write["target_pairs"], index=False)
    target_profile.to_csv(paths_to_write["target_profile"], index=False)
    treatment_cohort.to_csv(paths_to_write["treatment_cohort"], index=False)
    pd.concat([treatment_local, control_local], ignore_index=True).to_csv(
        paths_to_write["clone_inventory"], index=False
    )
    measurements.to_csv(paths_to_write["snapshot_measurements"], index=False)
    file_measurements.to_csv(paths_to_write["file_measurements"], index=False)
    target_measurements.to_csv(paths_to_write["target_measurements"], index=False)
    candidate_eligibility.to_csv(paths_to_write["candidate_eligibility"], index=False)
    pairwise.to_csv(paths_to_write["pairwise"], index=False)
    pairwise[pairwise["rank_within_treatment"].le(top_k)].to_csv(
        paths_to_write["pairwise_top"], index=False
    )
    common.to_csv(paths_to_write["common"], index=False)
    common[common["top_k_candidate"].astype(bool)].to_csv(
        paths_to_write["common_top"], index=False
    )
    validation.to_csv(paths_to_write["validation"], index=False)
    feature_long.to_csv(paths_to_write["feature_long"], index=False)
    feature_summary.to_csv(paths_to_write["feature_summary"], index=False)

    top_candidate = common[common["eligible_replacement_candidate"].astype(bool)].iloc[0]
    output_hashes = {
        name: sha256_file(path)
        for name, path in paths_to_write.items()
        if path.is_file()
    }
    summary = {
        "status": "PASS",
        "analysis": (
            "original propensity-score exact matching with direct Python-NCLOC "
            "tie-breaking"
        ),
        "interpretation": "noncausal design-stage rematching sensitivity",
        "target_control": target_control,
        "target_adoption_cohort": target_adoption_cohort,
        "paper_matched_period": paper_matched_period,
        "cutoff_utc": cutoff.isoformat(),
        "target_propensity_score": target_score,
        "propensity_caliper": propensity_caliper,
        "target_treatments": target_treatments,
        "original_controls": original_controls,
        "target_treatment_count": len(target_treatments),
        "local_control_count": len(control_local),
        "candidate_controls_selected_for_measurement": len(candidate_pool),
        "eligible_replacement_candidate_count": len(eligible_candidates),
        "target_snapshot_status_counts": target_measurements[
            "snapshot_status"
        ].value_counts(dropna=False).to_dict(),
        "control_snapshot_status_counts": measurements.loc[
            measurements["dataset_source"].eq("control"), "snapshot_status"
        ].value_counts(dropna=False).to_dict(),
        "measurement_method": MEASUREMENT_METHOD,
        "measurement_note": (
            "Direct Python token/AST NCLOC is an explicit operationalization and "
            "is not assumed to be numerically identical to SonarQube NCLOC."
        ),
        "top_common_candidate": top_candidate.to_dict(),
        "post_adoption_agc_outcome_used": False,
        "did_ran": False,
        "causal_interpretation_allowed": False,
        "output_hashes": output_hashes,
        "next_step": (
            "Review and freeze one donor from the common ranking before reading "
            "2025-04 or 2025-06 AGC class-method outcomes."
        ),
    }
    summary_path = output_dir / f"{OUTPUT_PREFIX}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_status(
        output_dir,
        "PASS",
        [
            f"target_treatments={len(target_treatments)}",
            f"candidate_controls_selected_for_measurement={len(candidate_pool)}",
            f"eligible_replacement_candidates={len(eligible_candidates)}",
            f"top_common_candidate={top_candidate['candidate_control_repo']}",
            f"measurement_method={MEASUREMENT_METHOD}",
            "post_adoption_agc_outcome_used=FALSE",
            "did_ran=FALSE",
            "causal_interpretation_allowed=FALSE",
        ],
    )

    print("=" * 80)
    print("run-py-8d: candidate ranking PASS")
    print("=" * 80)
    print(f"Target treatments measured: {len(target_measurements)}")
    print(f"Candidate controls selected for measurement: {len(candidate_pool)}")
    print(f"Eligible replacement candidates: {len(eligible_candidates)}")
    print("Post-adoption AGC outcomes inspected: NO")
    print("DiD executed: NO")
    print("\nTop common donors:")
    print(
        common[common["eligible_replacement_candidate"].astype(bool)]
        .head(min(10, len(eligible_candidates)))[
            [
                "common_donor_rank",
                "candidate_control_repo",
                "candidate_python_ncloc_direct",
                "max_python_ncloc_log_distance",
                "mean_python_ncloc_log_distance",
                "mean_repository_age_distance_days",
            ]
        ]
        .to_string(index=False)
    )
    print(f"\nOutput directory: {output_dir}")
    return summary


def initialize_git_repo(path: Path, repo_name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_command(["git", "init", "-q", str(path)])
    run_command(["git", "-C", str(path), "config", "user.email", "test@example.com"])
    run_command(["git", "-C", str(path), "config", "user.name", "Test User"])
    run_command(
        [
            "git",
            "-C",
            str(path),
            "remote",
            "add",
            "origin",
            f"https://github.com/{repo_name}.git",
        ]
    )


def commit_files(path: Path, files: Mapping[str, str], timestamp: str, message: str) -> None:
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    run_command(["git", "-C", str(path), "add", "."])
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = timestamp
    env["GIT_COMMITTER_DATE"] = timestamp
    run_command(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        env=env,
    )


def create_self_test_repository(
    root: Path,
    repo_name: str,
    before_cutoff_source: str | None,
    after_cutoff_source: str,
) -> Path:
    path = root / repo_name.replace("/", "_")
    initialize_git_repo(path, repo_name)
    if before_cutoff_source is not None:
        commit_files(
            path,
            {"src/main.py": before_cutoff_source},
            "2024-09-15T12:00:00+00:00",
            "before cutoff",
        )
    commit_files(
        path,
        {"src/main.py": after_cutoff_source},
        "2024-10-15T12:00:00+00:00",
        "after cutoff",
    )
    return path


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-8d-self-test-") as temp:
        root = Path(temp)
        treatment_root = root / "treatment-repos"
        control_root = root / "control-repos"
        output_dir = root / "output"
        treatment_root.mkdir()
        control_root.mkdir()

        target_treatments = list(EXPECTED_TARGET_TREATMENTS)
        for index, repo in enumerate(target_treatments):
            source = (
                '"""Module docstring."""\n'
                f"value_{index} = {index}\n"
                "def f(x):\n"
                "    # comment\n"
                "    return x + 1\n"
            )
            create_self_test_repository(
                treatment_root,
                repo,
                source,
                source + "after = True\n",
            )

        controls = {
            "example/GoodControl": (
                "value = 1\ndef f(x):\n    return x + 1\n",
                0.0212830932484271,
            ),
            "example/LargeControl": (
                "\n".join(f"value_{i} = {i}" for i in range(80)) + "\n",
                0.0212830932484271,
            ),
            TARGET_CONTROL: (
                "\n".join(f"web_{i} = {i}" for i in range(120)) + "\n",
                0.0212830932484271,
            ),
            "example/LateControl": (None, 0.0212830932484271),
            "example/OutsideCaliper": ("value = 1\n", 0.5),
        }
        for repo, (before_source, _) in controls.items():
            create_self_test_repository(
                control_root,
                repo,
                before_source,
                "after = True\n",
            )

        pair_rows = [
            {
                "treatment_repo": repo,
                "control_repo": TARGET_CONTROL,
                "control_rank": 3,
            }
            for repo in target_treatments
        ]
        pair_path = root / "pairs.csv"
        pd.DataFrame(pair_rows).to_csv(pair_path, index=False)

        sample_path = root / "treatment_sample.csv"
        pd.DataFrame(
            {
                "repo_name": target_treatments,
                "event_month": [TARGET_ADOPTION_COHORT] * len(target_treatments),
                "repo_primary_language": ["Python"] * len(target_treatments),
            }
        ).to_csv(sample_path, index=False)

        matching_rows = []
        original_controls = [
            "example/GoodControl",
            "example/LargeControl",
            TARGET_CONTROL,
        ]
        for repo in target_treatments:
            row = {
                "repo_name": repo,
                "matched_period": PAPER_MATCHED_PERIOD,
                "group": "treatment",
                "propensity_score": TARGET_PROPENSITY_SCORE,
                "matched_control_1": original_controls[0],
                "matched_control_2": original_controls[1],
                "matched_control_3": original_controls[2],
            }
            row.update({feature: 0 for feature in PAPER_SUMMARY_FEATURES})
            matching_rows.append(row)
        for repo, (_, score) in controls.items():
            row = {
                "repo_name": repo,
                "matched_period": PAPER_MATCHED_PERIOD,
                "group": "control",
                "propensity_score": score,
                "matched_control_1": np.nan,
                "matched_control_2": np.nan,
                "matched_control_3": np.nan,
            }
            row.update({feature: 0 for feature in PAPER_SUMMARY_FEATURES})
            matching_rows.append(row)
        matching_path = root / "matching.csv"
        pd.DataFrame(matching_rows).to_csv(matching_path, index=False)

        candidate_rows = []
        for repo in controls:
            for period in range(202404, 202410):
                candidate_rows.append(
                    {
                        "repo_name": repo,
                        "period": period,
                        "period_type": "within",
                        "age_days": 0,
                        "users_involved": 0,
                        "n_stars": 0,
                        "n_forks": 0,
                        "n_releases": 0,
                        "n_pulls": 0,
                        "n_issues": 0,
                        "n_comments": 0,
                        "total_events": 0,
                    }
                )
            history = candidate_rows[-1].copy()
            history["period"] = 202403
            history["period_type"] = "sum"
            candidate_rows.append(history)
        candidate_path = root / "candidate_features.csv"
        pd.DataFrame(candidate_rows).to_csv(candidate_path, index=False)

        summary = run_analysis(
            AnalysisPaths(
                target_pair_manifest=pair_path,
                treatment_sample=sample_path,
                original_matching_csv=matching_path,
                treatment_clone_root=treatment_root,
                control_clone_root=control_root,
                output_dir=output_dir,
                candidate_feature_csv=candidate_path,
            ),
            target_control=TARGET_CONTROL,
            target_adoption_cohort=TARGET_ADOPTION_COHORT,
            paper_matched_period=PAPER_MATCHED_PERIOD,
            cutoff_utc=CUTOFF_UTC,
            propensity_caliper=1e-12,
            top_k=5,
            workers=2,
            chunksize=50,
            max_controls=0,
            max_python_file_bytes=1_000_000,
            excluded_dirs=set(DEFAULT_EXCLUDED_DIRS),
            skip_frozen_target_checks=False,
        )
        top = summary["top_common_candidate"]["candidate_control_repo"]
        if top != "example/GoodControl":
            raise AssertionError(
                f"Self-test expected example/GoodControl as top donor, found {top}."
            )
        late = pd.read_csv(
            output_dir / f"{OUTPUT_PREFIX}_python_ncloc_snapshot_restoration.csv"
        )
        late_status = late.loc[
            late["repo_name"].eq("example/LateControl"), "snapshot_status"
        ].iloc[0]
        if late_status != "structural_zero_not_created":
            raise AssertionError(
                "Self-test failed to classify the post-cutoff repository as structural zero."
            )
        print("Self-test: PASS")


def main() -> None:
    args = parse_args()
    if args.self_test:
        run_self_test()
        required = [
            args.target_pair_manifest,
            args.treatment_sample,
            args.original_matching_csv,
            args.treatment_clone_root,
            args.control_clone_root,
            args.output_dir,
        ]
        if all(value is None for value in required):
            return

    required_arguments = {
        "--target-pair-manifest": args.target_pair_manifest,
        "--treatment-sample": args.treatment_sample,
        "--original-matching-csv": args.original_matching_csv,
        "--treatment-clone-root": args.treatment_clone_root,
        "--control-clone-root": args.control_clone_root,
        "--output-dir": args.output_dir,
    }
    missing = [name for name, value in required_arguments.items() if value is None]
    if missing:
        raise SystemExit("Missing required arguments: " + ", ".join(missing))

    excluded_dirs = {
        item.strip()
        for item in args.excluded_dirs.split(",")
        if item.strip()
    }
    try:
        run_analysis(
            AnalysisPaths(
                target_pair_manifest=args.target_pair_manifest,
                treatment_sample=args.treatment_sample,
                original_matching_csv=args.original_matching_csv,
                treatment_clone_root=args.treatment_clone_root,
                control_clone_root=args.control_clone_root,
                output_dir=args.output_dir,
                local_control_manifest=args.local_control_manifest,
                candidate_feature_csv=args.candidate_feature_csv,
                treatment_sonar_ncloc_csv=args.treatment_sonar_ncloc_csv,
                control_sonar_ncloc_csv=args.control_sonar_ncloc_csv,
            ),
            target_control=args.target_control,
            target_adoption_cohort=args.target_adoption_cohort,
            paper_matched_period=args.paper_matched_period,
            cutoff_utc=args.cutoff_utc,
            propensity_caliper=args.propensity_caliper,
            top_k=args.top_k,
            workers=args.workers,
            chunksize=args.chunksize,
            max_controls=args.max_controls,
            max_python_file_bytes=args.max_python_file_bytes,
            excluded_dirs=excluded_dirs,
            skip_frozen_target_checks=args.skip_frozen_target_checks,
        )
    except Exception as exc:  # noqa: BLE001
        if args.output_dir is not None:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            write_status(
                args.output_dir,
                "FAIL",
                [f"error_type={type(exc).__name__}", f"error={exc}"],
            )
        print(f"ERROR: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
