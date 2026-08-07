#!/usr/bin/env python3
"""Audit Cursor adoption-month sensitivity to timezone and month-boundary handling.

This program is designed for the Python-only replication workflow. It does not
change treatment timing or fit a DiD model. Instead, it reconstructs the exact
Git commit timestamps for the Cursor-related commits that were recorded by the
legacy pipeline and compares their monthly buckets under explicit timezones.

Inputs
------
1. A final b02 Python-velocity panel. Treatment repositories, recorded event
   months, clone paths, and frozen analysis-tip commits are read from this file.
2. The legacy ``cursor_commits.csv`` produced by the original repository
   analyzer. Its ``committed_at`` values are especially important because the
   original analyzer used ``datetime.fromtimestamp()`` without an explicit
   timezone, so those timestamps preserve the wall-clock conversion used by the
   machine that generated the legacy CSV.
3. Local treatment repository clones. The program first tries the ``clone_path``
   stored in the panel and then falls back to ``--treatment-clone-dir``.

Outputs
-------
* commit audit: one row per legacy Cursor-related commit for treatment repos;
* repository summary: one row per treatment repository;
* timezone-difference subset: repositories whose adoption month differs under
  at least one audited timezone or differs from the recorded event month;
* inferred legacy-offset summary: observed offsets implied by legacy wall time
  versus exact Git epoch timestamps;
* QC table and compact key-value summary.

The analysis is intentionally audit-only. A repository-specific corrected
adoption panel should be created only after reviewing these outputs.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


IMPLEMENTATION_VERSION = "v1"
DEFAULT_TIMEZONES = ("UTC", "America/Chicago")


@dataclass(frozen=True)
class GitCommitMetadata:
    """Exact Git metadata used by the timezone audit."""

    commit_hash: str
    commit_epoch: int
    committer_iso: str
    author_epoch: int
    author_iso: str
    parents: str
    subject: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Cursor adoption months across explicit timezones."
    )
    parser.add_argument("--panel-file", required=False)
    parser.add_argument("--legacy-cursor-commits-file", required=False)
    parser.add_argument("--treatment-clone-dir", default="../treatment-repos")
    parser.add_argument(
        "--timezones",
        default=",".join(DEFAULT_TIMEZONES),
        help="Comma-separated IANA timezones. UTC and America/Chicago are recommended.",
    )
    parser.add_argument("--commit-output", required=False)
    parser.add_argument("--repo-output", required=False)
    parser.add_argument("--difference-output", required=False)
    parser.add_argument("--offset-output", required=False)
    parser.add_argument("--qc-output", required=False)
    parser.add_argument("--summary-output", required=False)
    parser.add_argument("--expected-treatment-repos", type=int, default=63)
    parser.add_argument("--strict-expected-counts", type=int, choices=(0, 1), default=1)
    parser.add_argument("--git-timeout-seconds", type=int, default=60)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=numeric_level,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_timezones(value: str) -> List[str]:
    zones: List[str] = []
    for raw in value.split(","):
        zone = raw.strip()
        if not zone:
            continue
        try:
            ZoneInfo(zone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {zone}") from exc
        if zone not in zones:
            zones.append(zone)
    if not zones:
        raise ValueError("At least one timezone is required")
    return zones


def sanitize_timezone_column(zone: str) -> str:
    return zone.lower().replace("/", "_").replace("-", "_").replace("+", "plus")


def month_string(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def month_delta(left: Optional[str], right: Optional[str]) -> Optional[int]:
    if not left or not right or pd.isna(left) or pd.isna(right):
        return None
    try:
        left_dt = datetime.strptime(str(left), "%Y-%m")
        right_dt = datetime.strptime(str(right), "%Y-%m")
    except ValueError:
        return None
    return (left_dt.year - right_dt.year) * 12 + (left_dt.month - right_dt.month)


def parse_legacy_datetime(value: object) -> Optional[datetime]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        dt = parsed.to_pydatetime()
    if dt.tzinfo is not None:
        # Legacy analyze_repos.py emitted naive timestamps. If an offset is present
        # in a supplied file, preserve the wall-clock fields and remove tzinfo so
        # inferred-offset calculations remain explicit and deterministic.
        dt = dt.replace(tzinfo=None)
    return dt


def legacy_inferred_offset_minutes(legacy_naive: Optional[datetime], epoch: int) -> Optional[float]:
    """Infer the original host UTC offset from a naive legacy wall time and epoch."""
    if legacy_naive is None:
        return None
    wall_as_utc_epoch = int(legacy_naive.replace(tzinfo=timezone.utc).timestamp())
    return (wall_as_utc_epoch - epoch) / 60.0


def hours_from_month_start(dt: datetime) -> float:
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (dt - start).total_seconds() / 3600.0


def hours_to_month_end(dt: datetime) -> float:
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return (next_month - dt).total_seconds() / 3600.0


def run_git(repo_path: Path, args: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def is_git_repo(repo_path: Path, timeout_seconds: int) -> bool:
    if not repo_path.is_dir():
        return False
    result = run_git(repo_path, ["rev-parse", "--is-inside-work-tree"], timeout_seconds)
    return result.returncode == 0 and result.stdout.strip() == "true"


def resolve_commit_metadata(
    repo_path: Path,
    commit_hash: str,
    timeout_seconds: int,
) -> Tuple[Optional[GitCommitMetadata], str]:
    fmt = "%H%x1f%ct%x1f%cI%x1f%at%x1f%aI%x1f%P%x1f%s"
    result = run_git(repo_path, ["show", "-s", f"--format={fmt}", commit_hash], timeout_seconds)
    if result.returncode != 0:
        return None, result.stderr.strip() or "git show failed"
    line = result.stdout.rstrip("\n")
    parts = line.split("\x1f")
    if len(parts) != 7:
        return None, f"unexpected git show field count: {len(parts)}"
    try:
        metadata = GitCommitMetadata(
            commit_hash=parts[0],
            commit_epoch=int(parts[1]),
            committer_iso=parts[2],
            author_epoch=int(parts[3]),
            author_iso=parts[4],
            parents=parts[5],
            subject=parts[6],
        )
    except ValueError as exc:
        return None, f"invalid git timestamp: {exc}"
    return metadata, ""


def commit_reachable_from_tip(
    repo_path: Path,
    commit_hash: str,
    tip_hash: Optional[str],
    timeout_seconds: int,
) -> Optional[bool]:
    if not tip_hash or pd.isna(tip_hash):
        return None
    result = run_git(
        repo_path,
        ["merge-base", "--is-ancestor", commit_hash, str(tip_hash)],
        timeout_seconds,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def choose_repo_path(panel_clone_path: object, repo_name: str, fallback_root: Path) -> Path:
    if panel_clone_path is not None and not pd.isna(panel_clone_path):
        candidate = Path(str(panel_clone_path))
        if candidate.exists():
            return candidate
    return fallback_root / repo_name.replace("/", "_")


def load_treatment_repositories(panel_file: Path, expected_treatment_repos: int, strict: bool) -> pd.DataFrame:
    panel = pd.read_csv(panel_file)
    required = {"repo_name", "is_treatment", "event"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Panel missing required columns: {sorted(missing)}")

    treatment = panel[panel["is_treatment"] == 1].copy()
    if treatment.empty:
        raise ValueError("No treatment rows found in panel")

    rows: List[Dict[str, object]] = []
    optional_columns = ["clone_path", "analysis_tip_commit", "event_index", "event_yyyymm"]
    for repo_name, group in treatment.groupby("repo_name", sort=True):
        events = [str(x) for x in group["event"].dropna().unique()]
        if len(events) != 1:
            raise ValueError(f"Treatment repo {repo_name} has {len(events)} unique event values: {events}")
        row: Dict[str, object] = {
            "repo_name": repo_name,
            "recorded_event_month": events[0],
            "panel_rows": len(group),
        }
        for col in optional_columns:
            if col in group.columns:
                values = group[col].dropna().unique()
                row[col] = values[0] if len(values) else None
        rows.append(row)

    repos = pd.DataFrame(rows)
    observed = len(repos)
    if strict and observed != expected_treatment_repos:
        raise ValueError(
            f"Unexpected treatment repository count: observed={observed}, expected={expected_treatment_repos}"
        )
    return repos


def build_commit_audit(
    treatment_repos: pd.DataFrame,
    legacy_cursor_commits: pd.DataFrame,
    treatment_clone_dir: Path,
    timezones: Sequence[str],
    git_timeout_seconds: int,
) -> pd.DataFrame:
    required = {"repo_name", "commit_hash", "committed_at"}
    missing = required - set(legacy_cursor_commits.columns)
    if missing:
        raise ValueError(f"Legacy cursor commits file missing required columns: {sorted(missing)}")

    repo_lookup = treatment_repos.set_index("repo_name").to_dict(orient="index")
    filtered = legacy_cursor_commits[
        legacy_cursor_commits["repo_name"].isin(set(treatment_repos["repo_name"]))
    ].copy()

    audit_rows: List[Dict[str, object]] = []
    for index, legacy_row in filtered.iterrows():
        repo_name = str(legacy_row["repo_name"])
        repo_info = repo_lookup[repo_name]
        repo_path = choose_repo_path(repo_info.get("clone_path"), repo_name, treatment_clone_dir)
        commit_hash = str(legacy_row["commit_hash"]).strip()
        legacy_dt = parse_legacy_datetime(legacy_row.get("committed_at"))

        base: Dict[str, object] = {
            "repo_name": repo_name,
            "recorded_event_month": repo_info.get("recorded_event_month"),
            "panel_clone_path": repo_info.get("clone_path"),
            "repo_path_used": str(repo_path),
            "repo_exists": repo_path.exists(),
            "is_git_repository": is_git_repo(repo_path, git_timeout_seconds),
            "analysis_tip_commit": repo_info.get("analysis_tip_commit"),
            "commit_hash": commit_hash,
            "legacy_committed_at": legacy_row.get("committed_at"),
            "legacy_committed_month": month_string(legacy_dt) if legacy_dt else None,
            "legacy_authored_at": legacy_row.get("authored_at"),
            "legacy_paths": legacy_row.get("paths"),
            "legacy_message": legacy_row.get("message"),
        }

        if not base["is_git_repository"]:
            base.update(
                {
                    "commit_resolved": False,
                    "resolve_error": "repository unavailable or not a Git repository",
                }
            )
            audit_rows.append(base)
            continue

        metadata, error = resolve_commit_metadata(repo_path, commit_hash, git_timeout_seconds)
        if metadata is None:
            base.update({"commit_resolved": False, "resolve_error": error})
            audit_rows.append(base)
            continue

        utc_dt = datetime.fromtimestamp(metadata.commit_epoch, tz=timezone.utc)
        host_local_dt = datetime.fromtimestamp(metadata.commit_epoch)
        base.update(
            {
                "commit_resolved": True,
                "resolve_error": "",
                "git_commit_epoch": metadata.commit_epoch,
                "git_committer_iso": metadata.committer_iso,
                "git_author_epoch": metadata.author_epoch,
                "git_author_iso": metadata.author_iso,
                "git_parent_hashes": metadata.parents,
                "git_subject": metadata.subject,
                "reachable_from_analysis_tip": commit_reachable_from_tip(
                    repo_path,
                    metadata.commit_hash,
                    repo_info.get("analysis_tip_commit"),
                    git_timeout_seconds,
                ),
                "utc_datetime": utc_dt.isoformat(),
                "utc_month": month_string(utc_dt),
                "host_local_datetime": host_local_dt.isoformat(),
                "host_local_month": month_string(host_local_dt),
                "legacy_inferred_offset_minutes": legacy_inferred_offset_minutes(
                    legacy_dt, metadata.commit_epoch
                ),
            }
        )

        for zone in timezones:
            zone_key = sanitize_timezone_column(zone)
            zone_dt = utc_dt.astimezone(ZoneInfo(zone))
            base[f"tz_{zone_key}_datetime"] = zone_dt.isoformat()
            base[f"tz_{zone_key}_month"] = month_string(zone_dt)
            base[f"tz_{zone_key}_utc_offset_minutes"] = zone_dt.utcoffset().total_seconds() / 60.0
            base[f"tz_{zone_key}_hours_from_month_start"] = hours_from_month_start(zone_dt)
            base[f"tz_{zone_key}_hours_to_month_end"] = hours_to_month_end(zone_dt)

        audit_rows.append(base)

    return pd.DataFrame(audit_rows)


def first_resolved_commit(group: pd.DataFrame) -> Optional[pd.Series]:
    resolved = group[group["commit_resolved"] == True].copy()  # noqa: E712
    if resolved.empty:
        return None
    resolved["git_commit_epoch"] = pd.to_numeric(resolved["git_commit_epoch"], errors="coerce")
    resolved = resolved.dropna(subset=["git_commit_epoch"])
    if resolved.empty:
        return None
    return resolved.sort_values(["git_commit_epoch", "commit_hash"]).iloc[0]


def build_repo_summary(
    treatment_repos: pd.DataFrame,
    commit_audit: pd.DataFrame,
    timezones: Sequence[str],
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for _, repo in treatment_repos.sort_values("repo_name").iterrows():
        repo_name = str(repo["repo_name"])
        recorded_event = str(repo["recorded_event_month"])
        group = commit_audit[commit_audit["repo_name"] == repo_name].copy()
        first = first_resolved_commit(group) if not group.empty else None

        legacy_months = sorted(
            {
                str(x)
                for x in group.get("legacy_committed_month", pd.Series(dtype=object)).dropna().tolist()
                if str(x)
            }
        )
        legacy_first_month = legacy_months[0] if legacy_months else None

        row: Dict[str, object] = {
            "repo_name": repo_name,
            "recorded_event_month": recorded_event,
            "panel_rows": repo.get("panel_rows"),
            "analysis_tip_commit": repo.get("analysis_tip_commit"),
            "legacy_cursor_commit_rows": len(group),
            "resolved_cursor_commit_rows": int(group.get("commit_resolved", pd.Series(dtype=bool)).fillna(False).sum()) if not group.empty else 0,
            "unresolved_cursor_commit_rows": int((~group.get("commit_resolved", pd.Series(dtype=bool)).fillna(False)).sum()) if not group.empty else 0,
            "legacy_first_month": legacy_first_month,
            "recorded_matches_legacy_first_month": legacy_first_month == recorded_event if legacy_first_month else False,
            "legacy_minus_recorded_months": month_delta(legacy_first_month, recorded_event),
        }

        if first is not None:
            legacy_dt = parse_legacy_datetime(first.get("legacy_committed_at"))
            row.update(
                {
                    "first_cursor_commit_hash": first.get("commit_hash"),
                    "first_cursor_commit_epoch": first.get("git_commit_epoch"),
                    "first_cursor_git_committer_iso": first.get("git_committer_iso"),
                    "first_cursor_legacy_committed_at": first.get("legacy_committed_at"),
                    "first_cursor_legacy_inferred_offset_minutes": first.get("legacy_inferred_offset_minutes"),
                    "first_cursor_reachable_from_analysis_tip": first.get("reachable_from_analysis_tip"),
                    "first_cursor_legacy_hours_from_month_start": hours_from_month_start(legacy_dt) if legacy_dt else None,
                    "first_cursor_legacy_hours_to_month_end": hours_to_month_end(legacy_dt) if legacy_dt else None,
                }
            )
        else:
            row.update(
                {
                    "first_cursor_commit_hash": None,
                    "first_cursor_commit_epoch": None,
                    "first_cursor_git_committer_iso": None,
                    "first_cursor_legacy_committed_at": None,
                    "first_cursor_legacy_inferred_offset_minutes": None,
                    "first_cursor_reachable_from_analysis_tip": None,
                    "first_cursor_legacy_hours_from_month_start": None,
                    "first_cursor_legacy_hours_to_month_end": None,
                }
            )

        candidate_months: List[str] = []
        if legacy_first_month:
            candidate_months.append(legacy_first_month)

        if first is not None:
            host_month = first.get("host_local_month")
            utc_month = first.get("utc_month")
            row["host_local_first_month"] = host_month
            row["utc_first_month"] = utc_month
            row["host_local_minus_recorded_months"] = month_delta(host_month, recorded_event)
            row["utc_minus_recorded_months"] = month_delta(utc_month, recorded_event)
            row["host_local_matches_legacy_first_month"] = host_month == legacy_first_month
            row["utc_matches_legacy_first_month"] = utc_month == legacy_first_month
            for candidate in (host_month, utc_month):
                if candidate:
                    candidate_months.append(str(candidate))
        else:
            row["host_local_first_month"] = None
            row["utc_first_month"] = None
            row["host_local_minus_recorded_months"] = None
            row["utc_minus_recorded_months"] = None
            row["host_local_matches_legacy_first_month"] = False
            row["utc_matches_legacy_first_month"] = False

        for zone in timezones:
            zone_key = sanitize_timezone_column(zone)
            column = f"tz_{zone_key}_month"
            if first is not None and column in first.index:
                zone_month = first.get(column)
                candidate_months.append(str(zone_month))
                row[f"{zone_key}_first_month"] = zone_month
                row[f"{zone_key}_minus_recorded_months"] = month_delta(zone_month, recorded_event)
                row[f"{zone_key}_matches_recorded_event"] = zone_month == recorded_event
                row[f"{zone_key}_matches_legacy_first_month"] = zone_month == legacy_first_month
                row[f"{zone_key}_hours_from_month_start"] = first.get(
                    f"tz_{zone_key}_hours_from_month_start"
                )
                row[f"{zone_key}_hours_to_month_end"] = first.get(
                    f"tz_{zone_key}_hours_to_month_end"
                )
            else:
                row[f"{zone_key}_first_month"] = None
                row[f"{zone_key}_minus_recorded_months"] = None
                row[f"{zone_key}_matches_recorded_event"] = False
                row[f"{zone_key}_matches_legacy_first_month"] = False
                row[f"{zone_key}_hours_from_month_start"] = None
                row[f"{zone_key}_hours_to_month_end"] = None

        clean_months = sorted(set(x for x in candidate_months if x and x != "nan"))
        row["candidate_first_months"] = "|".join(clean_months)
        row["timezone_sensitive_month"] = len(clean_months) > 1

        boundary_distances: List[float] = []
        for col, value in row.items():
            if col.endswith("_hours_from_month_start") or col.endswith("_hours_to_month_end"):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(numeric):
                    boundary_distances.append(numeric)
        min_boundary = min(boundary_distances) if boundary_distances else None
        row["minimum_hours_to_any_month_boundary"] = min_boundary
        row["within_6h_of_month_boundary"] = bool(min_boundary is not None and min_boundary <= 6)
        row["within_12h_of_month_boundary"] = bool(min_boundary is not None and min_boundary <= 12)
        row["within_24h_of_month_boundary"] = bool(min_boundary is not None and min_boundary <= 24)
        row["within_48h_of_month_boundary"] = bool(min_boundary is not None and min_boundary <= 48)

        rows.append(row)

    return pd.DataFrame(rows)


def build_offset_summary(commit_audit: pd.DataFrame) -> pd.DataFrame:
    if commit_audit.empty or "legacy_inferred_offset_minutes" not in commit_audit.columns:
        return pd.DataFrame(
            columns=["legacy_inferred_offset_minutes", "commit_rows", "repositories", "first_legacy_committed_at", "last_legacy_committed_at"]
        )
    data = commit_audit[commit_audit["commit_resolved"] == True].copy()  # noqa: E712
    data = data.dropna(subset=["legacy_inferred_offset_minutes"])
    if data.empty:
        return pd.DataFrame(
            columns=["legacy_inferred_offset_minutes", "commit_rows", "repositories", "first_legacy_committed_at", "last_legacy_committed_at"]
        )
    data["legacy_inferred_offset_minutes"] = pd.to_numeric(
        data["legacy_inferred_offset_minutes"], errors="coerce"
    ).round(6)
    summary = (
        data.groupby("legacy_inferred_offset_minutes", dropna=False)
        .agg(
            commit_rows=("commit_hash", "size"),
            repositories=("repo_name", "nunique"),
            first_legacy_committed_at=("legacy_committed_at", "min"),
            last_legacy_committed_at=("legacy_committed_at", "max"),
        )
        .reset_index()
        .sort_values(["commit_rows", "legacy_inferred_offset_minutes"], ascending=[False, True])
    )
    return summary


def build_qc(
    treatment_repos: pd.DataFrame,
    commit_audit: pd.DataFrame,
    repo_summary: pd.DataFrame,
    timezones: Sequence[str],
    expected_treatment_repos: int,
) -> pd.DataFrame:
    total_repos = len(treatment_repos)
    repos_with_legacy = int((repo_summary["legacy_cursor_commit_rows"] > 0).sum())
    repos_with_resolved = int(repo_summary["first_cursor_commit_hash"].notna().sum())
    recorded_legacy_mismatches = int(
        ((repo_summary["legacy_first_month"].notna()) & (~repo_summary["recorded_matches_legacy_first_month"])).sum()
    )
    timezone_sensitive = int(repo_summary["timezone_sensitive_month"].sum())
    unresolved_commits = int((commit_audit.get("commit_resolved", pd.Series(dtype=bool)) != True).sum()) if not commit_audit.empty else 0  # noqa: E712
    unreachable = 0
    if not commit_audit.empty and "reachable_from_analysis_tip" in commit_audit.columns:
        unreachable = int((commit_audit["reachable_from_analysis_tip"] == False).sum())  # noqa: E712

    rows: List[Dict[str, object]] = [
        {
            "check_name": "treatment_repositories",
            "status": "pass" if total_repos == expected_treatment_repos else "fail",
            "observed": total_repos,
            "expected": expected_treatment_repos,
            "note": "Treatment repositories read from the final b02 panel.",
        },
        {
            "check_name": "repositories_with_legacy_cursor_commits",
            "status": "pass" if repos_with_legacy == total_repos else "warning",
            "observed": repos_with_legacy,
            "expected": total_repos,
            "note": "A missing legacy Cursor commit record prevents exact legacy-host reconstruction.",
        },
        {
            "check_name": "repositories_with_resolved_first_cursor_commit",
            "status": "pass" if repos_with_resolved == total_repos else "warning",
            "observed": repos_with_resolved,
            "expected": total_repos,
            "note": "Commit hashes are resolved against local treatment clones.",
        },
        {
            "check_name": "recorded_event_vs_legacy_cursor_month_mismatches",
            "status": "pass" if recorded_legacy_mismatches == 0 else "warning",
            "observed": recorded_legacy_mismatches,
            "expected": 0,
            "note": "Nonzero values indicate recorded event timing differs from the legacy cursor_commits month reconstruction.",
        },
        {
            "check_name": "timezone_sensitive_repositories",
            "status": "info",
            "observed": timezone_sensitive,
            "expected": "audit",
            "note": "Repositories whose first Cursor commit maps to more than one calendar month across audited clocks.",
        },
        {
            "check_name": "unresolved_legacy_cursor_commit_hashes",
            "status": "pass" if unresolved_commits == 0 else "warning",
            "observed": unresolved_commits,
            "expected": 0,
            "note": "May indicate repository history rewrite, stale clone path, or missing local clone.",
        },
        {
            "check_name": "cursor_commits_not_reachable_from_b02_analysis_tip",
            "status": "pass" if unreachable == 0 else "warning",
            "observed": unreachable,
            "expected": 0,
            "note": "Checks whether legacy Cursor commit hashes are ancestors of the frozen b02 analysis tip when available.",
        },
        {
            "check_name": "first_cursor_commit_within_24h_of_month_boundary",
            "status": "info",
            "observed": int(repo_summary["within_24h_of_month_boundary"].sum()),
            "expected": "audit",
            "note": "A direct indicator of possible timezone-driven month reassignment.",
        },
    ]

    for zone in timezones:
        zone_key = sanitize_timezone_column(zone)
        mismatch_col = f"{zone_key}_matches_legacy_first_month"
        if mismatch_col in repo_summary.columns:
            comparable = repo_summary["legacy_first_month"].notna() & repo_summary[f"{zone_key}_first_month"].notna()
            mismatches = int((comparable & (~repo_summary[mismatch_col])).sum())
            rows.append(
                {
                    "check_name": f"legacy_month_vs_{zone_key}_month_mismatches",
                    "status": "info",
                    "observed": mismatches,
                    "expected": "audit",
                    "note": f"Exact first Cursor commit month under {zone} compared with legacy local-wall-clock month.",
                }
            )

    return pd.DataFrame(rows)


def build_summary_table(
    repo_summary: pd.DataFrame,
    commit_audit: pd.DataFrame,
    offset_summary: pd.DataFrame,
    timezones: Sequence[str],
) -> pd.DataFrame:
    offset_mode = None
    if not offset_summary.empty:
        offset_mode = offset_summary.iloc[0]["legacy_inferred_offset_minutes"]
    rows = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("treatment_repositories", len(repo_summary)),
        ("legacy_cursor_commit_rows", len(commit_audit)),
        ("resolved_cursor_commit_rows", int(commit_audit.get("commit_resolved", pd.Series(dtype=bool)).fillna(False).sum()) if not commit_audit.empty else 0),
        ("timezone_sensitive_repositories", int(repo_summary["timezone_sensitive_month"].sum())),
        ("recorded_event_vs_legacy_month_mismatches", int((repo_summary["legacy_first_month"].notna() & (~repo_summary["recorded_matches_legacy_first_month"])).sum())),
        ("first_cursor_commit_within_24h_of_month_boundary", int(repo_summary["within_24h_of_month_boundary"].sum())),
        ("legacy_inferred_offset_mode_minutes", offset_mode),
        ("audited_timezones", "|".join(timezones)),
    ]
    for zone in timezones:
        key = sanitize_timezone_column(zone)
        col = f"{key}_matches_legacy_first_month"
        if col in repo_summary.columns:
            comparable = repo_summary["legacy_first_month"].notna() & repo_summary[f"{key}_first_month"].notna()
            mismatches = int((comparable & (~repo_summary[col])).sum())
            rows.append((f"legacy_vs_{key}_month_mismatches", mismatches))
    return pd.DataFrame(rows, columns=["metric", "value"])


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    logging.info("Wrote %d rows to %s", len(df), path)


def validate_required_cli_outputs(args: argparse.Namespace) -> None:
    required_names = [
        "panel_file",
        "legacy_cursor_commits_file",
        "commit_output",
        "repo_output",
        "difference_output",
        "offset_output",
        "qc_output",
        "summary_output",
    ]
    missing = [name for name in required_names if not getattr(args, name)]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join('--' + x.replace('_', '-') for x in missing)}")


def run_audit(args: argparse.Namespace) -> int:
    validate_required_cli_outputs(args)
    timezones = parse_timezones(args.timezones)
    panel_file = Path(args.panel_file)
    legacy_file = Path(args.legacy_cursor_commits_file)
    clone_dir = Path(args.treatment_clone_dir)

    if not panel_file.is_file():
        raise FileNotFoundError(f"Panel file not found: {panel_file}")
    if not legacy_file.is_file():
        raise FileNotFoundError(f"Legacy cursor commits file not found: {legacy_file}")

    treatment_repos = load_treatment_repositories(
        panel_file,
        args.expected_treatment_repos,
        bool(args.strict_expected_counts),
    )
    legacy_cursor_commits = pd.read_csv(legacy_file)

    logging.info(
        "Auditing %d treatment repositories with legacy cursor commits from %s",
        len(treatment_repos),
        legacy_file,
    )
    logging.info("Explicit timezones: %s", ", ".join(timezones))

    commit_audit = build_commit_audit(
        treatment_repos=treatment_repos,
        legacy_cursor_commits=legacy_cursor_commits,
        treatment_clone_dir=clone_dir,
        timezones=timezones,
        git_timeout_seconds=args.git_timeout_seconds,
    )
    repo_summary = build_repo_summary(treatment_repos, commit_audit, timezones)
    offset_summary = build_offset_summary(commit_audit)

    difference_mask = (
        repo_summary["timezone_sensitive_month"]
        | (
            repo_summary["legacy_first_month"].notna()
            & (~repo_summary["recorded_matches_legacy_first_month"])
        )
    )
    differences = repo_summary[difference_mask].copy()
    qc = build_qc(
        treatment_repos,
        commit_audit,
        repo_summary,
        timezones,
        args.expected_treatment_repos,
    )
    summary = build_summary_table(repo_summary, commit_audit, offset_summary, timezones)

    write_csv(commit_audit, Path(args.commit_output))
    write_csv(repo_summary, Path(args.repo_output))
    write_csv(differences, Path(args.difference_output))
    write_csv(offset_summary, Path(args.offset_output))
    write_csv(qc, Path(args.qc_output))
    write_csv(summary, Path(args.summary_output))

    failed_qc = qc[qc["status"] == "fail"]
    if bool(args.strict_expected_counts) and not failed_qc.empty:
        logging.error("Strict QC failures:\n%s", failed_qc.to_string(index=False))
        return 2

    logging.info(
        "Completed timezone audit: treatment_repos=%d; legacy_cursor_commits=%d; timezone_sensitive_repos=%d",
        len(repo_summary),
        len(commit_audit),
        int(repo_summary["timezone_sensitive_month"].sum()),
    )
    return 0


def git_commit_with_dates(repo: Path, filename: str, content: str, date_text: str) -> str:
    (repo / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True, capture_output=True, text=True)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date_text
    env["GIT_COMMITTER_DATE"] = date_text
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", f"add {filename}"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_self_test() -> int:
    """Create a synthetic month-boundary commit and verify the audit semantics."""
    with tempfile.TemporaryDirectory(prefix="cursor-timezone-audit-") as tmp:
        root = Path(tmp)
        repo = root / "treatment-repos" / "owner_repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        git_commit_with_dates(repo, "README.md", "base\n", "2025-02-15T12:00:00+00:00")
        cursor_hash = git_commit_with_dates(
            repo,
            ".cursorrules",
            "rules\n",
            "2025-03-01T00:30:00+00:00",
        )
        tip = cursor_hash

        treatment = pd.DataFrame(
            [
                {
                    "repo_name": "owner/repo",
                    "recorded_event_month": "2025-02",
                    "panel_rows": 4,
                    "clone_path": str(repo),
                    "analysis_tip_commit": tip,
                }
            ]
        )
        legacy = pd.DataFrame(
            [
                {
                    "repo_name": "owner/repo",
                    "commit_hash": cursor_hash,
                    "committed_at": "2025-02-28T18:30:00",
                    "authored_at": "2025-02-28T18:30:00",
                    "paths": ".cursorrules",
                    "message": "add .cursorrules",
                }
            ]
        )
        audit = build_commit_audit(
            treatment,
            legacy,
            root / "treatment-repos",
            ["UTC", "America/Chicago"],
            10,
        )
        if len(audit) != 1 or not bool(audit.iloc[0]["commit_resolved"]):
            raise AssertionError("Synthetic cursor commit was not resolved")
        row = audit.iloc[0]
        if row["utc_month"] != "2025-03":
            raise AssertionError(f"Expected UTC month 2025-03, got {row['utc_month']}")
        if row["tz_america_chicago_month"] != "2025-02":
            raise AssertionError(
                f"Expected America/Chicago month 2025-02, got {row['tz_america_chicago_month']}"
            )
        if abs(float(row["legacy_inferred_offset_minutes"]) - (-360.0)) > 1e-9:
            raise AssertionError(
                f"Expected inferred legacy offset -360 minutes, got {row['legacy_inferred_offset_minutes']}"
            )
        summary = build_repo_summary(treatment, audit, ["UTC", "America/Chicago"])
        if not bool(summary.iloc[0]["timezone_sensitive_month"]):
            raise AssertionError("Synthetic boundary case should be timezone-sensitive")
        if not bool(summary.iloc[0]["recorded_matches_legacy_first_month"]):
            raise AssertionError("Synthetic recorded event should match legacy first month")

    logging.info(
        "Self-test PASS: exact epoch recovery, inferred legacy offset, UTC/Chicago month boundary, and repository summary"
    )
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        if args.self_test:
            return run_self_test()
        return run_audit(args)
    except Exception as exc:
        logging.exception("Timezone audit failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
