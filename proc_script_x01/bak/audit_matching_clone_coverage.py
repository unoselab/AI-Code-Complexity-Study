#!/usr/bin/env python3
"""Audit treatment/control counts and local clone coverage for matching.csv.

This script is read-only with respect to repository clones. It:

1. Counts treatment repositories, control-pool repositories, matched-control slots,
   and unique matched controls in the paper replication matching.csv.
2. Audits whether each treatment and matched control exists in the configured
   local clone directories.
3. Validates that an existing clone is a usable Git repository and that its
   origin URL points to the expected GitHub repository when possible.
4. Optionally merges previously recorded clone-status CSV files.
5. Optionally probes missing repositories with `git ls-remote` to classify the
   current remote-side reason, such as available-but-not-cloned, not found,
   forbidden, legal restriction, network failure, or timeout.

The script does not clone, fetch, checkout, reset, clean, or modify repositories.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


LOGGER = logging.getLogger("audit_matching_clone_coverage")
CONTROL_COLUMNS = ("matched_control_1", "matched_control_2", "matched_control_3")
REPO_COLUMN_CANDIDATES = (
    "repo_name",
    "repository",
    "repo",
    "repository_name",
    "full_name",
)
STATUS_COLUMN_CANDIDATES = (
    "clone_status",
    "status",
    "result",
    "state",
)
REASON_COLUMN_CANDIDATES = (
    "clone_reason",
    "reason",
    "error_message",
    "error",
    "message",
    "details",
    "note",
)


@dataclass(frozen=True)
class GitCheck:
    """Read-only validation result for one local clone candidate."""

    clone_path: str
    path_exists: bool
    path_is_directory: bool
    is_git_repository: bool
    head_resolves: bool
    origin_url: str
    origin_repo_name: str
    origin_matches_expected: Optional[bool]
    local_status: str
    local_reason: str
    match_method: str


@dataclass(frozen=True)
class RemoteCheck:
    """Current remote availability result for one missing repository."""

    remote_status: str
    remote_reason: str
    remote_return_code: Optional[int]
    remote_detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Count repositories in matching.csv and audit treatment/matched-control "
            "clone coverage without modifying local repositories."
        )
    )
    parser.add_argument(
        "--matching-file",
        default="data_baseline_backup/matching.csv",
        help="Paper replication matching.csv file.",
    )
    parser.add_argument(
        "--treatment-clone-dir",
        default="../treatment-repos",
        help="Directory containing treatment clones named owner_repo.",
    )
    parser.add_argument(
        "--control-clone-dir",
        default="../control-repos",
        help="Directory containing control clones named owner_repo.",
    )
    parser.add_argument(
        "--output-dir",
        default="repo_x01/run-x-c00",
        help="Directory for audit CSV outputs.",
    )
    parser.add_argument(
        "--status-file",
        action="append",
        default=[],
        help=(
            "Optional prior clone-status CSV. Repeat this option for multiple files. "
            "The script auto-detects common repository/status/reason columns."
        ),
    )
    parser.add_argument(
        "--remote-check",
        choices=("none", "missing"),
        default="none",
        help=(
            "Optionally probe every locally missing repository with git ls-remote. "
            "Use 'missing' only when network access is available."
        ),
    )
    parser.add_argument(
        "--remote-workers",
        type=int,
        default=8,
        help="Maximum concurrent git ls-remote probes.",
    )
    parser.add_argument(
        "--remote-timeout-seconds",
        type=float,
        default=20.0,
        help="Timeout for each remote probe.",
    )
    parser.add_argument(
        "--remote-max-repos",
        type=int,
        default=0,
        help=(
            "Maximum number of missing repositories to probe. Zero means all. "
            "Repositories beyond the limit receive remote_check_not_run_limit."
        ),
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def normalize_repo_name(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().strip("/")


def repo_key(repo_name: str) -> str:
    return normalize_repo_name(repo_name).casefold()


def clone_directory_name(repo_name: str) -> str:
    return normalize_repo_name(repo_name).replace("/", "_")


def validate_repo_name(repo_name: str) -> bool:
    parts = normalize_repo_name(repo_name).split("/")
    return len(parts) == 2 and all(part.strip() for part in parts)


def run_git(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "true"
    return subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=env,
    )


def parse_github_repo_from_url(url: str) -> str:
    """Parse owner/repo from common HTTPS and SSH GitHub remote URL forms."""
    value = (url or "").strip()
    if not value:
        return ""

    patterns = (
        r"^https?://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
        r"^git://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1).removesuffix(".git").strip("/")
    return ""


def build_clone_indexes(clone_root: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    """Index immediate children by directory name and by GitHub origin repository."""
    by_name: dict[str, list[Path]] = {}
    by_origin: dict[str, list[Path]] = {}

    if not clone_root.exists() or not clone_root.is_dir():
        return by_name, by_origin

    for child in sorted(clone_root.iterdir(), key=lambda path: path.name.casefold()):
        by_name.setdefault(child.name.casefold(), []).append(child)
        if not child.is_dir():
            continue

        result = run_git(["-C", str(child), "remote", "get-url", "origin"])
        if result.returncode != 0:
            continue
        origin_repo = parse_github_repo_from_url(result.stdout.strip())
        if origin_repo:
            by_origin.setdefault(repo_key(origin_repo), []).append(child)

    return by_name, by_origin


def choose_clone_candidate(
    repo_name: str,
    clone_root: Path,
    by_name: dict[str, list[Path]],
    by_origin: dict[str, list[Path]],
) -> tuple[Optional[Path], str, str]:
    expected_path = clone_root / clone_directory_name(repo_name)
    if expected_path.exists():
        return expected_path, "expected_path", ""

    name_matches = by_name.get(expected_path.name.casefold(), [])
    if len(name_matches) == 1:
        return name_matches[0], "casefold_path", ""
    if len(name_matches) > 1:
        return None, "ambiguous_casefold_path", ";".join(str(path) for path in name_matches)

    origin_matches = by_origin.get(repo_key(repo_name), [])
    if len(origin_matches) == 1:
        return origin_matches[0], "origin_url", ""
    if len(origin_matches) > 1:
        return None, "ambiguous_origin_url", ";".join(str(path) for path in origin_matches)

    return None, "not_found", ""


def inspect_local_clone(
    repo_name: str,
    clone_root: Path,
    by_name: dict[str, list[Path]],
    by_origin: dict[str, list[Path]],
) -> GitCheck:
    candidate, match_method, ambiguity_detail = choose_clone_candidate(
        repo_name, clone_root, by_name, by_origin
    )

    if candidate is None:
        if match_method.startswith("ambiguous_"):
            return GitCheck(
                clone_path="",
                path_exists=False,
                path_is_directory=False,
                is_git_repository=False,
                head_resolves=False,
                origin_url="",
                origin_repo_name="",
                origin_matches_expected=None,
                local_status="ambiguous_local_clone",
                local_reason=ambiguity_detail,
                match_method=match_method,
            )
        return GitCheck(
            clone_path=str(clone_root / clone_directory_name(repo_name)),
            path_exists=False,
            path_is_directory=False,
            is_git_repository=False,
            head_resolves=False,
            origin_url="",
            origin_repo_name="",
            origin_matches_expected=None,
            local_status="clone_missing",
            local_reason="Expected clone path and matching GitHub origin were not found.",
            match_method=match_method,
        )

    if not candidate.is_dir():
        return GitCheck(
            clone_path=str(candidate),
            path_exists=True,
            path_is_directory=False,
            is_git_repository=False,
            head_resolves=False,
            origin_url="",
            origin_repo_name="",
            origin_matches_expected=None,
            local_status="clone_path_not_directory",
            local_reason="The expected clone path exists but is not a directory.",
            match_method=match_method,
        )

    inside = run_git(["-C", str(candidate), "rev-parse", "--is-inside-work-tree"])
    is_git = inside.returncode == 0 and inside.stdout.strip() == "true"
    if not is_git:
        return GitCheck(
            clone_path=str(candidate),
            path_exists=True,
            path_is_directory=True,
            is_git_repository=False,
            head_resolves=False,
            origin_url="",
            origin_repo_name="",
            origin_matches_expected=None,
            local_status="invalid_git_repository",
            local_reason=(inside.stderr or inside.stdout).strip()[:1000],
            match_method=match_method,
        )

    head = run_git(["-C", str(candidate), "rev-parse", "--verify", "HEAD^{commit}"])
    head_resolves = head.returncode == 0

    origin = run_git(["-C", str(candidate), "remote", "get-url", "origin"])
    origin_url = origin.stdout.strip() if origin.returncode == 0 else ""
    origin_repo = parse_github_repo_from_url(origin_url)
    origin_matches: Optional[bool]
    if origin_repo:
        origin_matches = repo_key(origin_repo) == repo_key(repo_name)
    else:
        origin_matches = None

    if not head_resolves:
        status = "git_head_unresolved"
        reason = (head.stderr or head.stdout).strip()[:1000]
    elif origin_matches is False:
        status = "available_origin_mismatch"
        reason = f"Expected {repo_name}, but origin points to {origin_repo or origin_url}."
    else:
        status = "available"
        reason = ""

    return GitCheck(
        clone_path=str(candidate),
        path_exists=True,
        path_is_directory=True,
        is_git_repository=True,
        head_resolves=head_resolves,
        origin_url=origin_url,
        origin_repo_name=origin_repo,
        origin_matches_expected=origin_matches,
        local_status=status,
        local_reason=reason,
        match_method=match_method,
    )


def detect_column(columns: Iterable[str], candidates: Iterable[str]) -> str:
    normalized = {str(column).strip().casefold(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.casefold() in normalized:
            return normalized[candidate.casefold()]
    return ""


def load_recorded_status_files(paths: list[str]) -> dict[str, dict[str, str]]:
    """Load optional prior clone-status records using common column names."""
    records: dict[str, dict[str, str]] = {}

    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            LOGGER.warning("Status file does not exist: %s", path)
            continue

        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        repo_column = detect_column(frame.columns, REPO_COLUMN_CANDIDATES)
        if not repo_column:
            LOGGER.warning("Skipping status file without a repository column: %s", path)
            continue

        status_column = detect_column(frame.columns, STATUS_COLUMN_CANDIDATES)
        reason_column = detect_column(frame.columns, REASON_COLUMN_CANDIDATES)

        for _, row in frame.iterrows():
            repository = normalize_repo_name(row.get(repo_column, ""))
            if not repository:
                continue
            key = repo_key(repository)
            entry = records.setdefault(
                key,
                {
                    "recorded_status": "",
                    "recorded_reason": "",
                    "recorded_status_source": "",
                },
            )
            status = str(row.get(status_column, "")).strip() if status_column else ""
            reason = str(row.get(reason_column, "")).strip() if reason_column else ""
            if status:
                entry["recorded_status"] = status
            if reason:
                entry["recorded_reason"] = reason
            entry["recorded_status_source"] = str(path)

    return records


def classify_remote_failure(stderr: str, stdout: str, return_code: int) -> RemoteCheck:
    detail = (stderr or stdout or "").strip()
    lowered = detail.casefold()

    if "unavailable for legal reasons" in lowered or "http 451" in lowered:
        status = "remote_legal_restriction"
        reason = "The remote appears unavailable for legal reasons."
    elif "repository not found" in lowered or "not found" in lowered:
        status = "remote_not_found_or_private"
        reason = "GitHub reports repository not found; it may be deleted, renamed, or private."
    elif "http 403" in lowered or "forbidden" in lowered:
        status = "remote_forbidden_or_blocked"
        reason = "GitHub returned a forbidden/blocked response."
    elif "authentication failed" in lowered or "could not read username" in lowered:
        status = "remote_authentication_required"
        reason = "The remote requires authentication or is private."
    elif "could not resolve host" in lowered:
        status = "remote_dns_failure"
        reason = "The GitHub host could not be resolved from this server."
    elif "failed to connect" in lowered or "connection timed out" in lowered:
        status = "remote_network_failure"
        reason = "The server could not connect to GitHub."
    else:
        status = "remote_probe_failed_other"
        reason = "git ls-remote failed for an unclassified reason."

    return RemoteCheck(status, reason, return_code, detail[:2000])


def probe_remote(repo_name: str, timeout_seconds: float) -> RemoteCheck:
    url = f"https://github.com/{repo_name}.git"
    try:
        result = run_git(["ls-remote", "--exit-code", url, "HEAD"], timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return RemoteCheck(
            "remote_timeout",
            f"git ls-remote exceeded {timeout_seconds:g} seconds.",
            None,
            "",
        )
    except OSError as exc:
        return RemoteCheck("remote_probe_os_error", str(exc), None, str(exc))

    if result.returncode == 0:
        return RemoteCheck(
            "remote_available",
            "The GitHub repository is currently reachable; it is missing only from the local clone directory.",
            0,
            result.stdout.strip()[:2000],
        )

    return classify_remote_failure(result.stderr, result.stdout, result.returncode)


def remote_checks_for_missing(
    repo_names: list[str],
    workers: int,
    timeout_seconds: float,
    max_repos: int,
) -> dict[str, RemoteCheck]:
    checks: dict[str, RemoteCheck] = {}
    ordered = sorted(set(repo_names), key=str.casefold)

    if max_repos > 0:
        selected = ordered[:max_repos]
        skipped = ordered[max_repos:]
    else:
        selected = ordered
        skipped = []

    for repo_name in skipped:
        checks[repo_key(repo_name)] = RemoteCheck(
            "remote_check_not_run_limit",
            f"Remote probe limit of {max_repos} repositories was reached.",
            None,
            "",
        )

    if not selected:
        return checks

    LOGGER.info("Probing %d missing repositories with git ls-remote", len(selected))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(probe_remote, repo_name, timeout_seconds): repo_name
            for repo_name in selected
        }
        completed = 0
        for future in as_completed(futures):
            repo_name = futures[future]
            try:
                checks[repo_key(repo_name)] = future.result()
            except Exception as exc:  # Defensive isolation for one remote probe.
                checks[repo_key(repo_name)] = RemoteCheck(
                    "remote_probe_internal_error", str(exc), None, str(exc)
                )
            completed += 1
            if completed % 100 == 0 or completed == len(selected):
                LOGGER.info("Remote probes completed: %d/%d", completed, len(selected))

    return checks


def derive_final_missing_reason(row: pd.Series) -> tuple[str, str]:
    local_status = str(row.get("local_status", ""))
    local_reason = str(row.get("local_reason", ""))
    recorded_status = str(row.get("recorded_status", ""))
    recorded_reason = str(row.get("recorded_reason", ""))
    remote_status = str(row.get("remote_status", ""))
    remote_reason = str(row.get("remote_reason", ""))

    if local_status == "available":
        return "not_missing", ""
    if local_status == "available_origin_mismatch":
        return "available_with_origin_mismatch", local_reason
    if local_status not in {"clone_missing", "ambiguous_local_clone"}:
        return local_status, local_reason
    if recorded_reason or recorded_status:
        detail = recorded_reason or recorded_status
        return "recorded_clone_status", detail
    if remote_status:
        return remote_status, remote_reason
    return local_status, local_reason


def build_role_audit(
    repositories: pd.DataFrame,
    role: str,
    clone_root: Path,
    recorded_statuses: dict[str, dict[str, str]],
) -> pd.DataFrame:
    by_name, by_origin = build_clone_indexes(clone_root)
    rows: list[dict[str, object]] = []

    for _, source_row in repositories.iterrows():
        repo_name = normalize_repo_name(source_row["repo_name"])
        check = inspect_local_clone(repo_name, clone_root, by_name, by_origin)
        recorded = recorded_statuses.get(
            repo_key(repo_name),
            {"recorded_status": "", "recorded_reason": "", "recorded_status_source": ""},
        )

        row = source_row.to_dict()
        row.update(
            {
                "scope_role": role,
                "clone_root": str(clone_root),
                "expected_clone_directory_name": clone_directory_name(repo_name),
                "clone_path": check.clone_path,
                "clone_match_method": check.match_method,
                "clone_path_exists": check.path_exists,
                "clone_path_is_directory": check.path_is_directory,
                "is_git_repository": check.is_git_repository,
                "git_head_resolves": check.head_resolves,
                "origin_url": check.origin_url,
                "origin_repo_name": check.origin_repo_name,
                "origin_matches_expected": check.origin_matches_expected,
                "local_status": check.local_status,
                "local_reason": check.local_reason,
                **recorded,
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def add_remote_and_final_reasons(
    audit: pd.DataFrame,
    remote_checks: dict[str, RemoteCheck],
) -> pd.DataFrame:
    result = audit.copy()
    remote_columns = {
        "remote_status": [],
        "remote_reason": [],
        "remote_return_code": [],
        "remote_detail": [],
    }

    for repo_name in result["repo_name"]:
        check = remote_checks.get(repo_key(repo_name))
        remote_columns["remote_status"].append(check.remote_status if check else "")
        remote_columns["remote_reason"].append(check.remote_reason if check else "")
        remote_columns["remote_return_code"].append(
            check.remote_return_code if check and check.remote_return_code is not None else pd.NA
        )
        remote_columns["remote_detail"].append(check.remote_detail if check else "")

    for column, values in remote_columns.items():
        result[column] = values

    final = result.apply(derive_final_missing_reason, axis=1, result_type="expand")
    final.columns = ["final_status", "final_reason"]
    result = pd.concat([result, final], axis=1)
    result["clone_available"] = result["local_status"].isin(
        ["available", "available_origin_mismatch"]
    )
    return result


def make_summary(
    matching: pd.DataFrame,
    treatments: pd.DataFrame,
    matched_controls: pd.DataFrame,
    treatment_audit: pd.DataFrame,
    control_audit: pd.DataFrame,
) -> pd.DataFrame:
    treatment_rows = matching[matching["group_normalized"] == "treatment"]
    control_pool_rows = matching[matching["group_normalized"] == "control"]
    slot_counts = treatment_rows[list(CONTROL_COLUMNS)].notna().sum(axis=1)

    metrics: list[tuple[str, object, str]] = [
        ("matching_rows_total", len(matching), "All rows in matching.csv."),
        ("treatment_rows", len(treatment_rows), "Rows with group=treatment."),
        ("unique_treatment_repositories", treatments["repo_name"].nunique(), "Unique treatment repositories."),
        ("control_pool_rows", len(control_pool_rows), "Rows with group=control in the candidate pool."),
        ("unique_control_pool_repositories", control_pool_rows["repo_name"].nunique(), "Unique control-pool repositories."),
        ("matched_control_slots_nonmissing", int(treatment_rows[list(CONTROL_COLUMNS)].notna().sum().sum()), "Non-empty matched_control_1..3 slots."),
        ("unique_matched_control_repositories", matched_controls["repo_name"].nunique(), "Unique controls actually selected in treatment rows."),
        ("treatments_with_0_matched_controls", int((slot_counts == 0).sum()), "Treatment rows with no selected control."),
        ("treatments_with_1_matched_control", int((slot_counts == 1).sum()), "Treatment rows with one selected control."),
        ("treatments_with_2_matched_controls", int((slot_counts == 2).sum()), "Treatment rows with two selected controls."),
        ("treatments_with_3_matched_controls", int((slot_counts == 3).sum()), "Treatment rows with three selected controls."),
        ("treatment_clones_available", int(treatment_audit["clone_available"].sum()), "Available treatment clones."),
        ("treatment_clones_missing_or_invalid", int((~treatment_audit["clone_available"]).sum()), "Missing, ambiguous, or invalid treatment clones."),
        ("matched_control_clones_available", int(control_audit["clone_available"].sum()), "Available matched-control clones."),
        ("matched_control_clones_missing_or_invalid", int((~control_audit["clone_available"]).sum()), "Missing, ambiguous, or invalid matched-control clones."),
    ]

    combined = pd.concat([treatment_audit, control_audit], ignore_index=True)
    for status, count in combined["final_status"].value_counts(dropna=False).sort_index().items():
        metrics.append((f"final_status::{status}", int(count), "Count across treatment and matched-control audits."))

    return pd.DataFrame(metrics, columns=["metric", "value", "note"])


def make_qc(
    matching: pd.DataFrame,
    treatments: pd.DataFrame,
    matched_controls: pd.DataFrame,
    treatment_audit: pd.DataFrame,
    control_audit: pd.DataFrame,
) -> pd.DataFrame:
    control_pool = set(
        matching.loc[matching["group_normalized"] == "control", "repo_key"]
    )
    matched_control_keys = set(matched_controls["repo_key"])

    checks = [
        (
            "duplicate_treatment_repository_names",
            int(treatments["repo_key"].duplicated().sum()),
            0,
            "Matching treatment repositories should be unique.",
        ),
        (
            "duplicate_matched_control_repository_names",
            int(matched_controls["repo_key"].duplicated().sum()),
            0,
            "Matched-control audit rows should be unique.",
        ),
        (
            "matched_controls_not_in_control_pool",
            len(matched_control_keys - control_pool),
            0,
            "Every selected matched control should appear in group=control rows.",
        ),
        (
            "invalid_treatment_repository_names",
            int((~treatments["repo_name"].map(validate_repo_name)).sum()),
            0,
            "Repository names should have owner/repository format.",
        ),
        (
            "invalid_matched_control_repository_names",
            int((~matched_controls["repo_name"].map(validate_repo_name)).sum()),
            0,
            "Repository names should have owner/repository format.",
        ),
        (
            "treatment_origin_mismatches",
            int((treatment_audit["local_status"] == "available_origin_mismatch").sum()),
            0,
            "Existing treatment clone origin should match the expected repository.",
        ),
        (
            "matched_control_origin_mismatches",
            int((control_audit["local_status"] == "available_origin_mismatch").sum()),
            0,
            "Existing control clone origin should match the expected repository.",
        ),
    ]

    rows = []
    for name, observed, expected, note in checks:
        rows.append(
            {
                "check_name": name,
                "status": "pass" if observed == expected else "warn",
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    LOGGER.info("Wrote %d rows to %s", len(frame), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    matching_file = Path(args.matching_file).expanduser().resolve()
    treatment_clone_dir = Path(args.treatment_clone_dir).expanduser().resolve()
    control_clone_dir = Path(args.control_clone_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not matching_file.exists():
        raise FileNotFoundError(f"Matching file does not exist: {matching_file}")

    LOGGER.info("Reading matching file: %s", matching_file)
    matching = pd.read_csv(matching_file)

    required = {"repo_name", "group", *CONTROL_COLUMNS}
    missing_columns = sorted(required - set(matching.columns))
    if missing_columns:
        raise ValueError(f"Missing required matching.csv columns: {missing_columns}")

    matching = matching.copy()
    matching["repo_name"] = matching["repo_name"].map(normalize_repo_name)
    matching["repo_key"] = matching["repo_name"].map(repo_key)
    matching["group_normalized"] = matching["group"].astype(str).str.strip().str.casefold()
    for column in CONTROL_COLUMNS:
        matching[column] = matching[column].map(normalize_repo_name).replace("", pd.NA)

    treatment_source = matching[matching["group_normalized"] == "treatment"].copy()
    treatments = treatment_source[["repo_name", "repo_key"]].drop_duplicates("repo_key")
    treatments = treatments.sort_values("repo_name", key=lambda series: series.str.casefold())

    control_long = treatment_source.melt(
        id_vars=["repo_name"],
        value_vars=list(CONTROL_COLUMNS),
        var_name="matched_control_slot",
        value_name="matched_control_repo",
    ).dropna(subset=["matched_control_repo"])
    control_long["matched_control_repo"] = control_long["matched_control_repo"].map(
        normalize_repo_name
    )
    control_long["matched_control_key"] = control_long["matched_control_repo"].map(repo_key)

    matched_controls = (
        control_long.groupby("matched_control_key", as_index=False)
        .agg(
            repo_name=("matched_control_repo", "first"),
            matched_slot_count=("matched_control_repo", "size"),
            matched_treatment_count=("repo_name", "nunique"),
            matched_treatments=("repo_name", lambda values: ";".join(sorted(set(values), key=str.casefold))),
            matched_slots=("matched_control_slot", lambda values: ";".join(sorted(set(values)))),
        )
        .rename(columns={"matched_control_key": "repo_key"})
        .sort_values("repo_name", key=lambda series: series.str.casefold())
    )

    treatment_slot_counts = control_long.groupby("repo_name").size().to_dict()
    treatments["matched_control_slot_count"] = treatments["repo_name"].map(treatment_slot_counts).fillna(0).astype(int)

    recorded_statuses = load_recorded_status_files(args.status_file)

    LOGGER.info("Auditing %d treatment repositories", len(treatments))
    treatment_audit = build_role_audit(
        treatments, "treatment", treatment_clone_dir, recorded_statuses
    )
    LOGGER.info("Auditing %d unique matched-control repositories", len(matched_controls))
    control_audit = build_role_audit(
        matched_controls, "matched_control", control_clone_dir, recorded_statuses
    )

    combined_pre_remote = pd.concat([treatment_audit, control_audit], ignore_index=True)
    remote_checks: dict[str, RemoteCheck] = {}
    if args.remote_check == "missing":
        missing_repositories = combined_pre_remote.loc[
            ~combined_pre_remote["local_status"].isin(
                ["available", "available_origin_mismatch"]
            ),
            "repo_name",
        ].tolist()
        remote_checks = remote_checks_for_missing(
            missing_repositories,
            workers=args.remote_workers,
            timeout_seconds=args.remote_timeout_seconds,
            max_repos=args.remote_max_repos,
        )

    treatment_audit = add_remote_and_final_reasons(treatment_audit, remote_checks)
    control_audit = add_remote_and_final_reasons(control_audit, remote_checks)

    missing_audit = pd.concat([treatment_audit, control_audit], ignore_index=True)
    missing_audit = missing_audit[~missing_audit["clone_available"]].copy()
    missing_audit = missing_audit.sort_values(
        ["scope_role", "repo_name"], key=lambda series: series.astype(str).str.casefold()
    )

    summary = make_summary(
        matching, treatments, matched_controls, treatment_audit, control_audit
    )
    qc = make_qc(
        matching, treatments, matched_controls, treatment_audit, control_audit
    )

    write_csv(summary, output_dir / "matching_repository_counts.csv")
    write_csv(treatment_audit, output_dir / "matching_treatment_clone_audit.csv")
    write_csv(control_audit, output_dir / "matching_control_clone_audit.csv")
    write_csv(missing_audit, output_dir / "matching_missing_clone_audit.csv")
    write_csv(qc, output_dir / "matching_clone_coverage_qc.csv")

    summary_map = dict(zip(summary["metric"], summary["value"]))
    print("=" * 68)
    print("matching.csv repository and clone coverage audit")
    print("=" * 68)
    print(f"Matching file:                    {matching_file}")
    print(f"Treatment rows/repositories:      {summary_map['treatment_rows']} / {summary_map['unique_treatment_repositories']}")
    print(f"Control-pool rows/repositories:   {summary_map['control_pool_rows']} / {summary_map['unique_control_pool_repositories']}")
    print(f"Matched-control slots:            {summary_map['matched_control_slots_nonmissing']}")
    print(f"Unique matched controls:          {summary_map['unique_matched_control_repositories']}")
    print(f"Treatment clones available:       {summary_map['treatment_clones_available']}")
    print(f"Treatment missing/invalid:        {summary_map['treatment_clones_missing_or_invalid']}")
    print(f"Matched-control clones available: {summary_map['matched_control_clones_available']}")
    print(f"Control missing/invalid:          {summary_map['matched_control_clones_missing_or_invalid']}")
    print(f"Output directory:                 {output_dir}")
    print("=" * 68)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        LOGGER.error("Interrupted by user")
        sys.exit(130)
    except Exception as exc:
        LOGGER.exception("Audit failed: %s", exc)
        sys.exit(1)
