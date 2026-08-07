#!/usr/bin/env python3
"""Audit whether recorded Cursor treatment dates remain supported by the frozen analysis history.

This program is an audit-only follow-up to the Cursor adoption timezone check. It
reconstructs Cursor-related evidence from the exact Git history reachable from
each repository's frozen b02 analysis tip and compares that evidence with the
legacy ``cursor_commits.csv`` and the recorded monthly treatment event.

The scan intentionally reproduces the original Cursor-path predicate:
``.cursorrules``, ``.cursorignore``, or any path containing a ``.cursor`` path
component. For non-root commits, changed paths are verified against the first
parent, matching the original analyzer's first-parent diff behavior.

The program never changes a Git checkout and never modifies treatment timing.
It produces repository-specific evidence and candidate actions for a later DiD
sensitivity analysis only when the current frozen history supports them.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


IMPLEMENTATION_VERSION = "v1"
DEFAULT_CALENDAR_TIMEZONE = "America/New_York"


@dataclass(frozen=True)
class GitCommitMetadata:
    """Minimal exact Git metadata needed by the treatment-history audit."""

    commit_hash: str
    commit_epoch: int
    committer_iso: str
    author_epoch: int
    author_iso: str
    parents: str
    subject: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Cursor treatment evidence against the frozen analysis-tip history."
    )
    parser.add_argument("--panel-file", required=False)
    parser.add_argument("--legacy-cursor-commits-file", required=False)
    parser.add_argument("--treatment-clone-dir", default="../treatment-repos")
    parser.add_argument(
        "--calendar-timezone",
        default=DEFAULT_CALENDAR_TIMEZONE,
        help="IANA timezone used to assign current-history Cursor commits to YYYY-MM buckets.",
    )
    parser.add_argument("--current-commit-output", required=False)
    parser.add_argument("--legacy-audit-output", required=False)
    parser.add_argument("--repo-output", required=False)
    parser.add_argument("--inconsistency-output", required=False)
    parser.add_argument("--candidate-output", required=False)
    parser.add_argument("--qc-output", required=False)
    parser.add_argument("--summary-output", required=False)
    parser.add_argument("--expected-treatment-repos", type=int, default=63)
    parser.add_argument("--strict-expected-counts", type=int, choices=(0, 1), default=1)
    parser.add_argument("--git-timeout-seconds", type=int, default=120)
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


def validate_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {name}") from exc


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
        dt = dt.replace(tzinfo=None)
    return dt


def run_git(
    repo_path: Path,
    args: Sequence[str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
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


def commit_exists(repo_path: Path, commit_hash: object, timeout_seconds: int) -> bool:
    if commit_hash is None or pd.isna(commit_hash):
        return False
    value = str(commit_hash).strip()
    if not value:
        return False
    result = run_git(repo_path, ["cat-file", "-e", f"{value}^{{commit}}"], timeout_seconds)
    return result.returncode == 0


def resolve_commit_metadata(
    repo_path: Path,
    commit_hash: str,
    timeout_seconds: int,
) -> Tuple[Optional[GitCommitMetadata], str]:
    fmt = "%H%x1f%ct%x1f%cI%x1f%at%x1f%aI%x1f%P%x1f%s"
    result = run_git(repo_path, ["show", "-s", f"--format={fmt}", commit_hash], timeout_seconds)
    if result.returncode != 0:
        return None, result.stderr.strip() or "git show failed"
    parts = result.stdout.rstrip("\n").split("\x1f")
    if len(parts) != 7:
        return None, f"unexpected git show field count: {len(parts)}"
    try:
        return (
            GitCommitMetadata(
                commit_hash=parts[0],
                commit_epoch=int(parts[1]),
                committer_iso=parts[2],
                author_epoch=int(parts[3]),
                author_iso=parts[4],
                parents=parts[5],
                subject=parts[6],
            ),
            "",
        )
    except ValueError as exc:
        return None, f"invalid git timestamp: {exc}"


def commit_reachable_from_tip(
    repo_path: Path,
    commit_hash: str,
    tip_hash: object,
    timeout_seconds: int,
) -> Optional[bool]:
    if tip_hash is None or pd.isna(tip_hash):
        return None
    tip = str(tip_hash).strip()
    if not tip:
        return None
    result = run_git(
        repo_path,
        ["merge-base", "--is-ancestor", commit_hash, tip],
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


def load_treatment_repositories(
    panel_file: Path,
    expected_treatment_repos: int,
    strict: bool,
) -> pd.DataFrame:
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
            raise ValueError(
                f"Treatment repo {repo_name} has {len(events)} unique event values: {events}"
            )
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
    if strict and len(repos) != expected_treatment_repos:
        raise ValueError(
            f"Unexpected treatment repository count: observed={len(repos)}, "
            f"expected={expected_treatment_repos}"
        )
    return repos


def is_cursor_related_path(path: Optional[str]) -> bool:
    """Replicate the original analyzer's Cursor-related path predicate exactly."""
    if not path:
        return False
    try:
        name = Path(path).name
    except Exception:
        name = path
    if name in {".cursorrules", ".cursorignore"}:
        return True
    try:
        parts = set(Path(path).parts)
    except Exception:
        parts = set(path.split("/"))
    if ".cursor" in parts:
        return True
    if path.startswith(".cursor/") or "/.cursor/" in path:
        return True
    return False


def parse_name_status_paths(stdout: str) -> List[str]:
    paths: List[str] = []
    for raw in stdout.splitlines():
        line = raw.rstrip("\n")
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        paths.extend(fields[1:])
    return paths


def changed_paths_first_parent(
    repo_path: Path,
    metadata: GitCommitMetadata,
    timeout_seconds: int,
) -> Tuple[List[str], str]:
    parents = [x for x in metadata.parents.split() if x]
    if parents:
        result = run_git(
            repo_path,
            ["diff", "--name-status", "-M", "-C", parents[0], metadata.commit_hash, "--"],
            timeout_seconds,
        )
    else:
        result = run_git(
            repo_path,
            [
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-status",
                "-r",
                "-M",
                "-C",
                metadata.commit_hash,
            ],
            timeout_seconds,
        )
    if result.returncode != 0:
        return [], result.stderr.strip() or "git diff failed"
    return parse_name_status_paths(result.stdout), ""


def candidate_cursor_commits(
    repo_path: Path,
    tip_hash: str,
    timeout_seconds: int,
) -> Tuple[List[str], str]:
    """Use Git pathspec filtering to find a small candidate set, then verify exactly."""
    pathspecs = [
        ".cursorrules",
        ".cursorignore",
        ".cursor/**",
        ":(glob)**/.cursorrules",
        ":(glob)**/.cursorignore",
        ":(glob)**/.cursor/**",
    ]
    result = run_git(
        repo_path,
        ["log", "--full-history", "--format=%H", tip_hash, "--", *pathspecs],
        timeout_seconds,
    )
    if result.returncode != 0:
        return [], result.stderr.strip() or "git log pathspec scan failed"
    seen: Set[str] = set()
    commits: List[str] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            commits.append(value)
    return commits, ""


def scan_current_reachable_history(
    repo_name: str,
    repo_path: Path,
    tip_hash: str,
    recorded_event_month: str,
    calendar_tz: ZoneInfo,
    timeout_seconds: int,
) -> Tuple[pd.DataFrame, str]:
    candidates, error = candidate_cursor_commits(repo_path, tip_hash, timeout_seconds)
    if error:
        return pd.DataFrame(), error

    rows: List[Dict[str, object]] = []
    for commit_hash in candidates:
        metadata, metadata_error = resolve_commit_metadata(repo_path, commit_hash, timeout_seconds)
        if metadata is None:
            logging.warning("Could not resolve candidate %s in %s: %s", commit_hash, repo_name, metadata_error)
            continue
        changed_paths, diff_error = changed_paths_first_parent(repo_path, metadata, timeout_seconds)
        if diff_error:
            logging.warning("Could not diff candidate %s in %s: %s", commit_hash, repo_name, diff_error)
            continue
        cursor_paths = sorted({path for path in changed_paths if is_cursor_related_path(path)})
        if not cursor_paths:
            continue
        utc_dt = datetime.fromtimestamp(metadata.commit_epoch, tz=timezone.utc)
        calendar_dt = utc_dt.astimezone(calendar_tz)
        rows.append(
            {
                "repo_name": repo_name,
                "recorded_event_month": recorded_event_month,
                "analysis_tip_commit": tip_hash,
                "commit_hash": metadata.commit_hash,
                "commit_epoch": metadata.commit_epoch,
                "git_committer_iso": metadata.committer_iso,
                "git_author_iso": metadata.author_iso,
                "calendar_timezone": str(calendar_tz.key),
                "calendar_datetime": calendar_dt.isoformat(),
                "calendar_month": month_string(calendar_dt),
                "recorded_month_delta": month_delta(month_string(calendar_dt), recorded_event_month),
                "parents": metadata.parents,
                "is_merge": len([x for x in metadata.parents.split() if x]) > 1,
                "subject": metadata.subject,
                "cursor_paths": ";".join(cursor_paths),
            }
        )

    scan = pd.DataFrame(rows)
    if not scan.empty:
        scan = scan.sort_values(["calendar_month", "commit_epoch", "commit_hash"]).reset_index(drop=True)
    return scan, ""


def build_legacy_commit_audit(
    treatment_repos: pd.DataFrame,
    legacy_cursor_commits: pd.DataFrame,
    treatment_clone_dir: Path,
    calendar_tz: ZoneInfo,
    timeout_seconds: int,
) -> pd.DataFrame:
    required = {"repo_name", "commit_hash", "committed_at"}
    missing = required - set(legacy_cursor_commits.columns)
    if missing:
        raise ValueError(f"Legacy cursor commits file missing required columns: {sorted(missing)}")

    repo_lookup = treatment_repos.set_index("repo_name").to_dict(orient="index")
    filtered = legacy_cursor_commits[
        legacy_cursor_commits["repo_name"].isin(set(treatment_repos["repo_name"]))
    ].copy()

    rows: List[Dict[str, object]] = []
    for _, legacy_row in filtered.iterrows():
        repo_name = str(legacy_row["repo_name"])
        info = repo_lookup[repo_name]
        repo_path = choose_repo_path(info.get("clone_path"), repo_name, treatment_clone_dir)
        tip = info.get("analysis_tip_commit")
        commit_hash = str(legacy_row["commit_hash"]).strip()
        legacy_dt = parse_legacy_datetime(legacy_row.get("committed_at"))
        base: Dict[str, object] = {
            "repo_name": repo_name,
            "recorded_event_month": info.get("recorded_event_month"),
            "analysis_tip_commit": tip,
            "repo_path_used": str(repo_path),
            "commit_hash": commit_hash,
            "legacy_committed_at": legacy_row.get("committed_at"),
            "legacy_committed_month": month_string(legacy_dt) if legacy_dt else None,
            "legacy_authored_at": legacy_row.get("authored_at"),
            "legacy_paths": legacy_row.get("paths"),
            "legacy_message": legacy_row.get("message"),
            "commit_resolved": False,
            "reachable_from_analysis_tip": None,
        }
        if not is_git_repo(repo_path, timeout_seconds):
            base["resolve_error"] = "repository unavailable or not a Git repository"
            rows.append(base)
            continue
        metadata, error = resolve_commit_metadata(repo_path, commit_hash, timeout_seconds)
        if metadata is None:
            base["resolve_error"] = error
            rows.append(base)
            continue
        utc_dt = datetime.fromtimestamp(metadata.commit_epoch, tz=timezone.utc)
        calendar_dt = utc_dt.astimezone(calendar_tz)
        base.update(
            {
                "commit_resolved": True,
                "resolve_error": "",
                "reachable_from_analysis_tip": commit_reachable_from_tip(
                    repo_path, metadata.commit_hash, tip, timeout_seconds
                ),
                "git_commit_epoch": metadata.commit_epoch,
                "git_committer_iso": metadata.committer_iso,
                "git_author_iso": metadata.author_iso,
                "calendar_timezone": str(calendar_tz.key),
                "calendar_datetime": calendar_dt.isoformat(),
                "calendar_month": month_string(calendar_dt),
                "calendar_matches_legacy_month": (
                    month_string(calendar_dt) == month_string(legacy_dt) if legacy_dt else None
                ),
                "parents": metadata.parents,
                "subject": metadata.subject,
            }
        )
        rows.append(base)
    return pd.DataFrame(rows)


def first_legacy_row(group: pd.DataFrame) -> Optional[pd.Series]:
    if group.empty:
        return None
    work = group.copy()
    work["legacy_sort"] = pd.to_datetime(work["legacy_committed_at"], errors="coerce")
    work = work.sort_values(["legacy_sort", "commit_hash"], na_position="last")
    return work.iloc[0]


def classify_repository(
    repo_available: bool,
    tip_available: bool,
    legacy_count: int,
    legacy_first_reachable: Optional[bool],
    current_count: int,
    recorded_month: str,
    current_month: Optional[str],
) -> Tuple[str, str, str, Optional[str]]:
    if not repo_available:
        return (
            "repo_unavailable",
            "manual_review",
            "Repository clone is unavailable or not a Git repository.",
            None,
        )
    if not tip_available:
        return (
            "analysis_tip_unavailable",
            "manual_review",
            "Frozen b02 analysis-tip commit cannot be resolved in the local clone.",
            None,
        )

    month_matches = current_month == recorded_month if current_month else False
    candidate_month = current_month if current_month and current_month != recorded_month else None

    if legacy_count == 0:
        if current_count == 0:
            return (
                "legacy_missing_no_current_evidence",
                "manual_review",
                "No legacy Cursor commit row and no Cursor-related commit in the frozen analysis history.",
                None,
            )
        if month_matches:
            return (
                "legacy_missing_current_same_month",
                "retain_recorded_supported_by_current_history",
                "Legacy provenance is missing, but current frozen history independently supports the recorded month.",
                None,
            )
        return (
            "legacy_missing_current_month_differs",
            "candidate_repository_specific_correction",
            "Legacy provenance is missing and current frozen history supports a different first Cursor month.",
            candidate_month,
        )

    if legacy_first_reachable is True:
        if current_count == 0:
            return (
                "legacy_reachable_but_current_scan_missing",
                "implementation_review",
                "The legacy first Cursor commit is reachable, but the current-history path scan did not recover Cursor evidence.",
                None,
            )
        if month_matches:
            return (
                "consistent_legacy_reachable",
                "retain_recorded",
                "Legacy first Cursor evidence is reachable and current frozen history supports the recorded month.",
                None,
            )
        return (
            "legacy_reachable_current_month_differs",
            "manual_review",
            "Legacy first evidence is reachable, but the earliest current-history Cursor month differs from recorded timing.",
            candidate_month,
        )

    if legacy_first_reachable is False:
        if current_count == 0:
            return (
                "legacy_unreachable_no_current_evidence",
                "manual_review",
                "Legacy first Cursor evidence is not reachable from the frozen analysis tip and no replacement evidence exists.",
                None,
            )
        if month_matches:
            return (
                "history_rewritten_but_current_same_month",
                "retain_recorded_supported_by_current_history",
                "Legacy first evidence is unreachable, but replacement Cursor evidence in current frozen history supports the same month.",
                None,
            )
        return (
            "history_rewritten_current_month_differs",
            "candidate_repository_specific_correction",
            "Legacy first evidence is unreachable and replacement Cursor evidence supports a different month.",
            candidate_month,
        )

    return (
        "legacy_reachability_unknown",
        "manual_review",
        "Legacy first Cursor evidence could not be classified for reachability.",
        candidate_month,
    )


def build_repo_summary(
    treatment_repos: pd.DataFrame,
    legacy_audit: pd.DataFrame,
    current_scan: pd.DataFrame,
    treatment_clone_dir: Path,
    calendar_tz: ZoneInfo,
    timeout_seconds: int,
    scan_errors: Dict[str, str],
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for _, info in treatment_repos.sort_values("repo_name").iterrows():
        repo_name = str(info["repo_name"])
        recorded_month = str(info["recorded_event_month"])
        repo_path = choose_repo_path(info.get("clone_path"), repo_name, treatment_clone_dir)
        repo_available = is_git_repo(repo_path, timeout_seconds)
        tip = info.get("analysis_tip_commit")
        tip_available = repo_available and commit_exists(repo_path, tip, timeout_seconds)

        legacy_group = (
            legacy_audit[legacy_audit["repo_name"] == repo_name].copy()
            if not legacy_audit.empty
            else pd.DataFrame()
        )
        current_group = (
            current_scan[current_scan["repo_name"] == repo_name].copy()
            if not current_scan.empty
            else pd.DataFrame()
        )

        legacy_first = first_legacy_row(legacy_group)
        legacy_count = len(legacy_group)
        legacy_resolved = int(legacy_group.get("commit_resolved", pd.Series(dtype=bool)).fillna(False).sum()) if legacy_count else 0
        legacy_reachable = int((legacy_group.get("reachable_from_analysis_tip", pd.Series(dtype=object)) == True).sum()) if legacy_count else 0
        legacy_unreachable = int((legacy_group.get("reachable_from_analysis_tip", pd.Series(dtype=object)) == False).sum()) if legacy_count else 0
        legacy_first_reachable: Optional[bool] = None
        legacy_first_hash: Optional[str] = None
        legacy_first_month: Optional[str] = None
        if legacy_first is not None:
            legacy_first_hash = str(legacy_first.get("commit_hash"))
            legacy_first_month = legacy_first.get("legacy_committed_month")
            value = legacy_first.get("reachable_from_analysis_tip")
            if value is True or value == True:
                legacy_first_reachable = True
            elif value is False or value == False:
                legacy_first_reachable = False

        current_count = len(current_group)
        current_first_hash: Optional[str] = None
        current_first_month: Optional[str] = None
        current_first_datetime: Optional[str] = None
        current_first_paths: Optional[str] = None
        current_hashes: Set[str] = set()
        if current_count:
            current_group = current_group.sort_values(["calendar_month", "commit_epoch", "commit_hash"])
            first = current_group.iloc[0]
            current_first_hash = str(first["commit_hash"])
            current_first_month = str(first["calendar_month"])
            current_first_datetime = str(first["calendar_datetime"])
            current_first_paths = str(first["cursor_paths"])
            current_hashes = set(current_group["commit_hash"].astype(str))

        legacy_hashes = set(legacy_group["commit_hash"].astype(str)) if legacy_count else set()
        overlap_count = len(legacy_hashes & current_hashes)
        first_legacy_recovered_by_scan = (
            legacy_first_hash in current_hashes if legacy_first_hash is not None else None
        )

        classification, action, reason, candidate_month = classify_repository(
            repo_available=repo_available,
            tip_available=tip_available,
            legacy_count=legacy_count,
            legacy_first_reachable=legacy_first_reachable,
            current_count=current_count,
            recorded_month=recorded_month,
            current_month=current_first_month,
        )

        rows.append(
            {
                "repo_name": repo_name,
                "recorded_event_month": recorded_month,
                "panel_rows": info.get("panel_rows"),
                "repo_path_used": str(repo_path),
                "repo_available": repo_available,
                "analysis_tip_commit": tip,
                "analysis_tip_available": tip_available,
                "calendar_timezone": str(calendar_tz.key),
                "legacy_cursor_commit_rows": legacy_count,
                "legacy_resolved_rows": legacy_resolved,
                "legacy_reachable_rows": legacy_reachable,
                "legacy_unreachable_rows": legacy_unreachable,
                "legacy_first_commit_hash": legacy_first_hash,
                "legacy_first_month": legacy_first_month,
                "legacy_first_reachable_from_analysis_tip": legacy_first_reachable,
                "current_reachable_cursor_commit_rows": current_count,
                "current_first_cursor_commit_hash": current_first_hash,
                "current_first_cursor_month": current_first_month,
                "current_first_cursor_datetime": current_first_datetime,
                "current_first_cursor_paths": current_first_paths,
                "current_minus_recorded_months": month_delta(current_first_month, recorded_month),
                "current_first_month_matches_recorded": (
                    current_first_month == recorded_month if current_first_month else False
                ),
                "legacy_current_hash_overlap_rows": overlap_count,
                "legacy_first_recovered_by_current_scan": first_legacy_recovered_by_scan,
                "scan_error": scan_errors.get(repo_name, ""),
                "history_consistency_class": classification,
                "recommended_action": action,
                "candidate_corrected_event_month": candidate_month,
                "recommendation_reason": reason,
            }
        )

    return pd.DataFrame(rows)


def build_current_scan(
    treatment_repos: pd.DataFrame,
    treatment_clone_dir: Path,
    calendar_tz: ZoneInfo,
    timeout_seconds: int,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    frames: List[pd.DataFrame] = []
    errors: Dict[str, str] = {}
    total = len(treatment_repos)
    for idx, (_, info) in enumerate(treatment_repos.sort_values("repo_name").iterrows(), start=1):
        repo_name = str(info["repo_name"])
        repo_path = choose_repo_path(info.get("clone_path"), repo_name, treatment_clone_dir)
        tip = info.get("analysis_tip_commit")
        logging.info("Scanning frozen Cursor history: %s (%d/%d)", repo_name, idx, total)
        if not is_git_repo(repo_path, timeout_seconds):
            errors[repo_name] = "repository unavailable or not a Git repository"
            continue
        if not commit_exists(repo_path, tip, timeout_seconds):
            errors[repo_name] = "analysis tip unavailable"
            continue
        scan, error = scan_current_reachable_history(
            repo_name=repo_name,
            repo_path=repo_path,
            tip_hash=str(tip),
            recorded_event_month=str(info["recorded_event_month"]),
            calendar_tz=calendar_tz,
            timeout_seconds=timeout_seconds,
        )
        if error:
            errors[repo_name] = error
            continue
        if not scan.empty:
            frames.append(scan)
    if frames:
        return pd.concat(frames, ignore_index=True), errors
    return pd.DataFrame(), errors


def build_qc(
    treatment_repos: pd.DataFrame,
    repo_summary: pd.DataFrame,
    current_scan: pd.DataFrame,
    expected_treatment_repos: int,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    def add(name: str, status: str, observed: object, expected: object, note: str) -> None:
        rows.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    add(
        "treatment_repository_count",
        "pass" if len(treatment_repos) == expected_treatment_repos else "fail",
        len(treatment_repos),
        expected_treatment_repos,
        "Treatment repositories loaded from the final b02 Python-velocity panel.",
    )
    repo_available = int(repo_summary["repo_available"].sum())
    add(
        "git_repository_available_count",
        "pass" if repo_available == len(repo_summary) else "fail",
        repo_available,
        len(repo_summary),
        "Every treatment repository should have an available local Git clone.",
    )
    tips_available = int(repo_summary["analysis_tip_available"].sum())
    add(
        "analysis_tip_available_count",
        "pass" if tips_available == len(repo_summary) else "fail",
        tips_available,
        len(repo_summary),
        "Every frozen b02 analysis-tip commit should resolve locally.",
    )
    scan_errors = int((repo_summary["scan_error"].fillna("") != "").sum())
    add(
        "current_history_scan_errors",
        "pass" if scan_errors == 0 else "fail",
        scan_errors,
        0,
        "Git path-history scans should complete for every treatment repository.",
    )

    reachable_legacy_first = repo_summary["legacy_first_reachable_from_analysis_tip"] == True
    recovered = repo_summary["legacy_first_recovered_by_current_scan"] == True
    reproduction_failures = int((reachable_legacy_first & (~recovered)).sum())
    add(
        "reachable_legacy_first_commit_recovered_by_scan",
        "pass" if reproduction_failures == 0 else "fail",
        reproduction_failures,
        0,
        "Any reachable legacy first Cursor commit must be rediscovered by the current-history scan.",
    )

    all_reachable_missing = int(
        (repo_summary["legacy_reachable_rows"] - repo_summary["legacy_current_hash_overlap_rows"]).clip(lower=0).sum()
    )
    add(
        "all_reachable_legacy_commits_recovered_by_scan",
        "pass" if all_reachable_missing == 0 else "fail",
        all_reachable_missing,
        0,
        "Every reachable legacy Cursor commit must be rediscovered by the independent current-history path scan.",
    )

    add(
        "legacy_missing_repositories",
        "info",
        int((repo_summary["legacy_cursor_commit_rows"] == 0).sum()),
        "audit",
        "Repositories with recorded treatment but no legacy cursor_commits.csv row.",
    )
    add(
        "legacy_first_unreachable_repositories",
        "info",
        int((repo_summary["legacy_first_reachable_from_analysis_tip"] == False).sum()),
        "audit",
        "Repositories whose first legacy Cursor commit is not an ancestor of the frozen b02 analysis tip.",
    )
    add(
        "no_current_cursor_evidence_repositories",
        "info",
        int((repo_summary["current_reachable_cursor_commit_rows"] == 0).sum()),
        "audit",
        "Repositories with no Cursor-related commit found in the frozen analysis history.",
    )
    add(
        "current_first_month_differs_from_recorded",
        "info",
        int(
            (
                repo_summary["current_first_cursor_month"].notna()
                & (~repo_summary["current_first_month_matches_recorded"])
            ).sum()
        ),
        "audit",
        "Repositories where frozen-history evidence supports a different first Cursor month.",
    )
    add(
        "candidate_repository_specific_corrections",
        "info",
        int((repo_summary["recommended_action"] == "candidate_repository_specific_correction").sum()),
        "audit",
        "Only these repositories should be considered for evidence-based timing correction in a later sensitivity run.",
    )
    add(
        "current_cursor_commit_rows",
        "info",
        len(current_scan),
        "audit",
        "Total Cursor-related commits rediscovered inside all frozen treatment histories.",
    )
    return pd.DataFrame(rows)


def build_summary(repo_summary: pd.DataFrame, current_scan: pd.DataFrame, legacy_audit: pd.DataFrame) -> pd.DataFrame:
    metrics: List[Tuple[str, object]] = [
        ("implementation_version", IMPLEMENTATION_VERSION),
        ("treatment_repositories", len(repo_summary)),
        ("legacy_cursor_commit_rows", len(legacy_audit)),
        ("current_reachable_cursor_commit_rows", len(current_scan)),
        ("legacy_missing_repositories", int((repo_summary["legacy_cursor_commit_rows"] == 0).sum())),
        (
            "legacy_first_unreachable_repositories",
            int((repo_summary["legacy_first_reachable_from_analysis_tip"] == False).sum()),
        ),
        (
            "no_current_cursor_evidence_repositories",
            int((repo_summary["current_reachable_cursor_commit_rows"] == 0).sum()),
        ),
        (
            "current_first_month_differs_from_recorded",
            int(
                (
                    repo_summary["current_first_cursor_month"].notna()
                    & (~repo_summary["current_first_month_matches_recorded"])
                ).sum()
            ),
        ),
        (
            "candidate_repository_specific_corrections",
            int((repo_summary["recommended_action"] == "candidate_repository_specific_correction").sum()),
        ),
        (
            "manual_review_repositories",
            int(repo_summary["recommended_action"].isin(["manual_review", "implementation_review"]).sum()),
        ),
    ]
    for class_name, count in repo_summary["history_consistency_class"].value_counts().sort_index().items():
        metrics.append((f"class_{class_name}", int(count)))
    return pd.DataFrame(metrics, columns=["metric", "value"])


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    logging.info("Wrote %d rows to %s", len(df), path)


def validate_required_outputs(args: argparse.Namespace) -> None:
    required = [
        "panel_file",
        "legacy_cursor_commits_file",
        "current_commit_output",
        "legacy_audit_output",
        "repo_output",
        "inconsistency_output",
        "candidate_output",
        "qc_output",
        "summary_output",
    ]
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        raise ValueError(
            "Missing required arguments: "
            + ", ".join("--" + name.replace("_", "-") for name in missing)
        )


def run_audit(args: argparse.Namespace) -> int:
    validate_required_outputs(args)
    calendar_tz = validate_timezone(args.calendar_timezone)
    panel_file = Path(args.panel_file)
    legacy_file = Path(args.legacy_cursor_commits_file)
    clone_dir = Path(args.treatment_clone_dir)
    if not panel_file.is_file():
        raise FileNotFoundError(f"Panel file not found: {panel_file}")
    if not legacy_file.is_file():
        raise FileNotFoundError(f"Legacy Cursor commits file not found: {legacy_file}")

    treatment_repos = load_treatment_repositories(
        panel_file,
        args.expected_treatment_repos,
        bool(args.strict_expected_counts),
    )
    legacy_cursor_commits = pd.read_csv(legacy_file)

    logging.info(
        "Auditing %d treatment repositories against frozen analysis-tip history in timezone %s",
        len(treatment_repos),
        args.calendar_timezone,
    )
    legacy_audit = build_legacy_commit_audit(
        treatment_repos=treatment_repos,
        legacy_cursor_commits=legacy_cursor_commits,
        treatment_clone_dir=clone_dir,
        calendar_tz=calendar_tz,
        timeout_seconds=args.git_timeout_seconds,
    )
    current_scan, scan_errors = build_current_scan(
        treatment_repos=treatment_repos,
        treatment_clone_dir=clone_dir,
        calendar_tz=calendar_tz,
        timeout_seconds=args.git_timeout_seconds,
    )
    repo_summary = build_repo_summary(
        treatment_repos=treatment_repos,
        legacy_audit=legacy_audit,
        current_scan=current_scan,
        treatment_clone_dir=clone_dir,
        calendar_tz=calendar_tz,
        timeout_seconds=args.git_timeout_seconds,
        scan_errors=scan_errors,
    )

    inconsistency_mask = ~repo_summary["history_consistency_class"].isin(
        ["consistent_legacy_reachable"]
    )
    inconsistencies = repo_summary[inconsistency_mask].copy()
    candidates = repo_summary[
        repo_summary["recommended_action"].isin(
            [
                "candidate_repository_specific_correction",
                "retain_recorded_supported_by_current_history",
                "manual_review",
                "implementation_review",
            ]
        )
    ].copy()
    qc = build_qc(treatment_repos, repo_summary, current_scan, args.expected_treatment_repos)
    summary = build_summary(repo_summary, current_scan, legacy_audit)

    write_csv(current_scan, Path(args.current_commit_output))
    write_csv(legacy_audit, Path(args.legacy_audit_output))
    write_csv(repo_summary, Path(args.repo_output))
    write_csv(inconsistencies, Path(args.inconsistency_output))
    write_csv(candidates, Path(args.candidate_output))
    write_csv(qc, Path(args.qc_output))
    write_csv(summary, Path(args.summary_output))

    failed = qc[qc["status"] == "fail"]
    if bool(args.strict_expected_counts) and not failed.empty:
        logging.error("Strict QC failures:\n%s", failed.to_string(index=False))
        return 2

    logging.info(
        "Completed treatment-history audit: repos=%d; current_cursor_commits=%d; inconsistencies=%d; candidate_corrections=%d",
        len(repo_summary),
        len(current_scan),
        len(inconsistencies),
        int((repo_summary["recommended_action"] == "candidate_repository_specific_correction").sum()),
    )
    return 0


def git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)


def git_commit_file(repo: Path, filename: str, content: str, date_text: str, message: str) -> str:
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True, capture_output=True, text=True)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date_text
    env["GIT_COMMITTER_DATE"] = date_text
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
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
    """Verify stable, rewritten, and missing-legacy treatment provenance cases."""
    with tempfile.TemporaryDirectory(prefix="cursor-treatment-history-audit-") as tmp:
        root = Path(tmp)
        clone_root = root / "treatment-repos"

        stable = clone_root / "owner_stable"
        git_init(stable)
        git_commit_file(stable, "README.md", "base\n", "2025-01-10T12:00:00-05:00", "base")
        stable_cursor = git_commit_file(
            stable, ".cursorrules", "rules\n", "2025-02-10T12:00:00-05:00", "add cursor rules"
        )

        rewritten = clone_root / "owner_rewritten"
        git_init(rewritten)
        base_hash = git_commit_file(
            rewritten, "README.md", "base\n", "2025-01-10T12:00:00-05:00", "base"
        )
        old_cursor = git_commit_file(
            rewritten, ".cursorrules", "old rules\n", "2025-02-20T12:00:00-05:00", "legacy cursor"
        )
        subprocess.run(
            ["git", "-C", str(rewritten), "reset", "--hard", base_hash],
            check=True,
            capture_output=True,
            text=True,
        )
        new_cursor = git_commit_file(
            rewritten,
            ".cursor/rules.md",
            "new rules\n",
            "2025-03-05T12:00:00-05:00",
            "replacement cursor evidence",
        )

        missing = clone_root / "owner_missing"
        git_init(missing)
        git_commit_file(missing, "README.md", "base\n", "2025-03-01T12:00:00-05:00", "base")
        missing_cursor = git_commit_file(
            missing, ".cursorignore", "cache\n", "2025-04-02T12:00:00-04:00", "add cursor ignore"
        )

        treatment = pd.DataFrame(
            [
                {
                    "repo_name": "owner/stable",
                    "recorded_event_month": "2025-02",
                    "panel_rows": 3,
                    "clone_path": str(stable),
                    "analysis_tip_commit": stable_cursor,
                },
                {
                    "repo_name": "owner/rewritten",
                    "recorded_event_month": "2025-02",
                    "panel_rows": 3,
                    "clone_path": str(rewritten),
                    "analysis_tip_commit": new_cursor,
                },
                {
                    "repo_name": "owner/missing",
                    "recorded_event_month": "2025-04",
                    "panel_rows": 3,
                    "clone_path": str(missing),
                    "analysis_tip_commit": missing_cursor,
                },
            ]
        )
        legacy = pd.DataFrame(
            [
                {
                    "repo_name": "owner/stable",
                    "commit_hash": stable_cursor,
                    "committed_at": "2025-02-10T12:00:00",
                    "authored_at": "2025-02-10T12:00:00",
                    "paths": ".cursorrules",
                    "message": "add cursor rules",
                },
                {
                    "repo_name": "owner/rewritten",
                    "commit_hash": old_cursor,
                    "committed_at": "2025-02-20T12:00:00",
                    "authored_at": "2025-02-20T12:00:00",
                    "paths": ".cursorrules",
                    "message": "legacy cursor",
                },
            ]
        )
        tz = ZoneInfo("America/New_York")
        legacy_audit = build_legacy_commit_audit(treatment, legacy, clone_root, tz, 10)
        current_scan, errors = build_current_scan(treatment, clone_root, tz, 10)
        summary = build_repo_summary(treatment, legacy_audit, current_scan, clone_root, tz, 10, errors)
        by_repo = summary.set_index("repo_name")

        if by_repo.loc["owner/stable", "history_consistency_class"] != "consistent_legacy_reachable":
            raise AssertionError("Stable repository classification failed")
        if by_repo.loc["owner/rewritten", "history_consistency_class"] != "history_rewritten_current_month_differs":
            raise AssertionError("Rewritten repository classification failed")
        if by_repo.loc["owner/rewritten", "candidate_corrected_event_month"] != "2025-03":
            raise AssertionError("Rewritten repository candidate month failed")
        if by_repo.loc["owner/missing", "history_consistency_class"] != "legacy_missing_current_same_month":
            raise AssertionError("Missing-legacy repository classification failed")
        if bool(by_repo.loc["owner/rewritten", "legacy_first_reachable_from_analysis_tip"]):
            raise AssertionError("Rewritten legacy commit should be unreachable")
        if old_cursor in set(current_scan["commit_hash"].astype(str)):
            raise AssertionError("Unreachable legacy commit must not appear in current reachable scan")

    logging.info(
        "Self-test PASS: stable evidence, history rewrite, missing legacy provenance, first-parent path scan, and candidate correction"
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
        logging.exception("Treatment-history audit failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
