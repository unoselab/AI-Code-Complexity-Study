#!/usr/bin/env python3
"""Audit target-month Git commit activity for frozen rematched donors.

This design-stage script reads only the frozen donor manifest, the prior
snapshot-availability audit, and local Git metadata. It does not read AGC
scores, class-method counts, detector outputs, or Difference-in-Differences
results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

OUTPUT_PREFIX = "webscout_rematched_donor_commit_activity"
DEFAULT_SELECTED_DONOR = "Hack-a-Day/2024-Supercon-8-Add-On-Badge"
DEFAULT_FALLBACK_DONOR = "viktoriasemaan/sa-ai-agent"
DEFAULT_TARGET_MONTHS = ("2025-04", "2025-06")


class AnalysisError(RuntimeError):
    """Raised when a frozen-design validation fails."""


@dataclass(frozen=True)
class MonthWindow:
    """A half-open UTC calendar-month interval."""

    label: str
    start_utc: datetime
    end_utc_exclusive: datetime


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess and optionally convert failures to AnalysisError."""

    completed = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AnalysisError(
            f"Command failed ({completed.returncode}): {' '.join(args)}: {detail}"
        )
    return completed


def git_try_output(repo_path: Path, args: Sequence[str], timeout: int = 120) -> str:
    """Return stripped Git output, or an empty string on failure."""

    completed = run_command(
        ["git", "-C", str(repo_path), *args],
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bool_value(value: object) -> bool:
    """Convert common CSV Boolean encodings to bool."""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def normalize_repo_name(value: object) -> str:
    """Normalize GitHub repository names and remote URLs."""

    text = "" if value is None else str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    text = text.removesuffix(".git").rstrip("/")
    if "github.com" in text:
        text = text.split("github.com", 1)[1].lstrip(":/")
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return text


def repository_name_from_remote(repo_path: Path) -> str:
    """Read a normalized repository name from origin."""

    url = git_try_output(repo_path, ["remote", "get-url", "origin"])
    return normalize_repo_name(url)


def discover_repo_path(clone_root: Path, repo_name: str) -> Path | None:
    """Locate a local clone by the standard directory name or origin URL."""

    expected = clone_root / repo_name.replace("/", "_")
    if expected.is_dir():
        return expected.resolve()

    for child in sorted(path for path in clone_root.iterdir() if path.is_dir()):
        if repository_name_from_remote(child) == repo_name:
            return child.resolve()
    return None


def month_window(value: str) -> MonthWindow:
    """Parse YYYY-MM into a half-open UTC month interval."""

    try:
        year_text, month_text = value.strip().split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
        if month < 1 or month > 12:
            raise ValueError
    except ValueError as exc:
        raise AnalysisError(f"Invalid target month: {value!r}; expected YYYY-MM") from exc

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return MonthWindow(value.strip(), start, end)


def verify_ref(repo_path: Path, ref: str) -> bool:
    """Check whether one ref expression can be resolved."""

    if ref == "--all":
        return True
    return bool(git_try_output(repo_path, ["rev-parse", "--verify", ref]))


def preferred_refs(repo_path: Path) -> list[str]:
    """Return deterministic refs matching the prior snapshot audit order."""

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

    ordered: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref not in seen:
            ordered.append(ref)
            seen.add(ref)
    ordered.append("--all")
    return ordered


def resolve_audit_ref(
    repo_path: Path,
    availability_rows: pd.DataFrame,
) -> tuple[str, str]:
    """Reuse the prior cutoff ref when possible, otherwise choose a fallback."""

    prior_refs = [
        str(value).strip()
        for value in availability_rows.get("cutoff_commit_ref", pd.Series(dtype=str))
        if str(value).strip() and str(value).strip().lower() != "nan"
    ]
    for ref in prior_refs:
        if verify_ref(repo_path, ref):
            return ref, "run_py_8e_cutoff_ref"

    for ref in preferred_refs(repo_path):
        if verify_ref(repo_path, ref):
            return ref, "preferred_ref_fallback"
    return "", "unresolved"


def list_commits_in_month(
    repo_path: Path,
    ref: str,
    window: MonthWindow,
) -> tuple[list[tuple[str, str, int]], str]:
    """List unique commits whose committer timestamps fall inside one month."""

    if not ref:
        return [], "audit_ref_unresolved"

    args = [
        "git",
        "-C",
        str(repo_path),
        "log",
        "--format=%H%x09%cI%x09%ct",
        "--reverse",
        f"--since={window.start_utc.isoformat()}",
        f"--before={window.end_utc_exclusive.isoformat()}",
    ]
    if ref == "--all":
        args.append("--all")
    else:
        args.append(ref)

    completed = run_command(args, timeout=300, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return [], f"git_log_failed:{detail}"

    commits_by_sha: dict[str, tuple[str, str, int]] = {}
    for line in completed.stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 3:
            continue
        sha, iso_text, epoch_text = parts
        try:
            epoch = int(epoch_text)
        except ValueError:
            continue
        commits_by_sha[sha] = (sha, iso_text, epoch)

    commits = sorted(commits_by_sha.values(), key=lambda item: (item[2], item[0]))
    return commits, ""


def load_freeze_inputs(
    freeze_path: Path,
    availability_path: Path,
    expected_selected_donor: str,
    expected_fallback_donor: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate the frozen donor identities and snapshot audit."""

    freeze = pd.read_csv(freeze_path, low_memory=False)
    availability = pd.read_csv(availability_path, low_memory=False)

    freeze_required = {
        "freeze_role",
        "candidate_control_repo",
        "common_donor_rank",
        "ranking_sha256",
        "frozen_before_post_adoption_outcome_review",
        "post_adoption_agc_outcome_read",
        "did_executed",
    }
    missing_freeze = sorted(freeze_required - set(freeze.columns))
    if missing_freeze:
        raise AnalysisError(f"Freeze manifest is missing columns: {missing_freeze}")

    availability_required = {
        "repo_name",
        "snapshot_month",
        "snapshot_available",
        "cutoff_commit_sha",
        "cutoff_commit_ref",
    }
    missing_availability = sorted(availability_required - set(availability.columns))
    if missing_availability:
        raise AnalysisError(
            f"Snapshot availability file is missing columns: {missing_availability}"
        )

    freeze["candidate_control_repo"] = freeze["candidate_control_repo"].map(
        normalize_repo_name
    )
    availability["repo_name"] = availability["repo_name"].map(normalize_repo_name)

    selected_rows = freeze[freeze["freeze_role"].eq("selected")]
    fallback_rows = freeze[freeze["freeze_role"].eq("fallback")]
    if len(selected_rows) != 1 or len(fallback_rows) != 1:
        raise AnalysisError("Freeze manifest must contain exactly one selected and fallback row.")

    selected_repo = str(selected_rows.iloc[0]["candidate_control_repo"])
    fallback_repo = str(fallback_rows.iloc[0]["candidate_control_repo"])
    if selected_repo != expected_selected_donor:
        raise AnalysisError(
            f"Selected donor mismatch: expected {expected_selected_donor}, observed {selected_repo}"
        )
    if fallback_repo != expected_fallback_donor:
        raise AnalysisError(
            f"Fallback donor mismatch: expected {expected_fallback_donor}, observed {fallback_repo}"
        )

    if int(pd.to_numeric(selected_rows.iloc[0]["common_donor_rank"])) != 1:
        raise AnalysisError("Selected donor is not frozen at common_donor_rank=1.")
    if int(pd.to_numeric(fallback_rows.iloc[0]["common_donor_rank"])) != 2:
        raise AnalysisError("Fallback donor is not frozen at common_donor_rank=2.")

    ranking_hashes = set(freeze["ranking_sha256"].dropna().astype(str))
    if len(ranking_hashes) != 1:
        raise AnalysisError("Freeze manifest contains inconsistent ranking SHA-256 values.")

    if not freeze["frozen_before_post_adoption_outcome_review"].map(bool_value).all():
        raise AnalysisError("Donor ranking was not frozen before outcome review.")
    if freeze["post_adoption_agc_outcome_read"].map(bool_value).any():
        raise AnalysisError("Freeze manifest indicates that an AGC outcome was already read.")
    if freeze["did_executed"].map(bool_value).any():
        raise AnalysisError("Freeze manifest indicates that DiD was already executed.")

    frozen_repos = {selected_repo, fallback_repo}
    available_repos = set(availability["repo_name"].astype(str))
    if not frozen_repos.issubset(available_repos):
        raise AnalysisError("Snapshot availability does not include both frozen donors.")

    return freeze, availability


def audit_repo_month(
    repo_name: str,
    repo_path: Path | None,
    availability_rows: pd.DataFrame,
    window: MonthWindow,
) -> dict[str, object]:
    """Audit whether a frozen donor has commits inside one target month."""

    record: dict[str, object] = {
        "repo_name": repo_name,
        "target_month": window.label,
        "month_start_utc": window.start_utc.isoformat(),
        "month_end_utc_exclusive": window.end_utc_exclusive.isoformat(),
        "clone_path": "" if repo_path is None else str(repo_path),
        "clone_exists": bool(repo_path and repo_path.is_dir()),
        "is_git_repository": False,
        "is_shallow_repository": None,
        "audit_ref": "",
        "audit_ref_source": "",
        "month_commit_count": None,
        "month_has_commit": False,
        "first_month_commit_sha": "",
        "first_month_commit_timestamp": "",
        "last_month_commit_sha": "",
        "last_month_commit_timestamp": "",
        "snapshot_available_from_run_py_8e": False,
        "snapshot_cutoff_commit_sha": "",
        "snapshot_cutoff_commit_timestamp": "",
        "activity_status": "",
        "failure_reason": "",
        "agc_outcome_read": False,
        "did_executed": False,
    }

    month_prior = availability_rows[
        availability_rows["snapshot_month"].astype(str).eq(window.label)
    ]
    if len(month_prior) != 1:
        record["activity_status"] = "invalid_prior_snapshot_audit"
        record["failure_reason"] = f"expected_one_prior_snapshot_row_observed_{len(month_prior)}"
        return record

    prior = month_prior.iloc[0]
    record["snapshot_available_from_run_py_8e"] = bool_value(
        prior["snapshot_available"]
    )
    record["snapshot_cutoff_commit_sha"] = str(prior.get("cutoff_commit_sha", ""))
    record["snapshot_cutoff_commit_timestamp"] = str(
        prior.get("cutoff_commit_timestamp", "")
    )

    if repo_path is None or not repo_path.is_dir():
        record["activity_status"] = "missing_local_clone"
        record["failure_reason"] = "local_clone_not_found"
        return record

    inside = git_try_output(repo_path, ["rev-parse", "--is-inside-work-tree"])
    if inside.lower() != "true":
        record["activity_status"] = "invalid_git_repository"
        record["failure_reason"] = "not_inside_git_work_tree"
        return record
    record["is_git_repository"] = True

    shallow = git_try_output(repo_path, ["rev-parse", "--is-shallow-repository"])
    record["is_shallow_repository"] = shallow.lower() == "true"

    audit_ref, ref_source = resolve_audit_ref(repo_path, availability_rows)
    record["audit_ref"] = audit_ref
    record["audit_ref_source"] = ref_source

    commits, failure = list_commits_in_month(repo_path, audit_ref, window)
    if failure:
        record["activity_status"] = "commit_activity_audit_failure"
        record["failure_reason"] = failure
        return record

    record["month_commit_count"] = len(commits)
    record["month_has_commit"] = len(commits) > 0
    if commits:
        first_sha, first_iso, _ = commits[0]
        last_sha, last_iso, _ = commits[-1]
        record["first_month_commit_sha"] = first_sha
        record["first_month_commit_timestamp"] = first_iso
        record["last_month_commit_sha"] = last_sha
        record["last_month_commit_timestamp"] = last_iso
        record["activity_status"] = "active_target_month"
    else:
        record["activity_status"] = "inactive_target_month_snapshot_carry_forward"

    return record


def validation_table(
    freeze: pd.DataFrame,
    availability: pd.DataFrame,
    activity: pd.DataFrame,
    selected_donor: str,
    fallback_donor: str,
    target_months: set[str],
) -> pd.DataFrame:
    """Build design and execution checks without requiring active months."""

    selected_rows = activity[activity["repo_name"].eq(selected_donor)]
    fallback_rows = activity[activity["repo_name"].eq(fallback_donor)]
    activity_failures = activity[activity["failure_reason"].fillna("").astype(str).ne("")]

    checks: list[tuple[str, bool, object]] = [
        (
            "selected_and_fallback_donors_remain_frozen",
            set(freeze["candidate_control_repo"].astype(str))
            == {selected_donor, fallback_donor},
            ",".join(sorted(freeze["candidate_control_repo"].astype(str))),
        ),
        (
            "ranking_hash_consistent_in_freeze_manifest",
            freeze["ranking_sha256"].dropna().astype(str).nunique() == 1,
            freeze["ranking_sha256"].dropna().astype(str).iloc[0],
        ),
        (
            "prior_snapshot_availability_covers_target_months",
            target_months.issubset(set(availability["snapshot_month"].astype(str))),
            ",".join(sorted(set(availability["snapshot_month"].astype(str)))),
        ),
        (
            "selected_donor_commit_activity_audited_for_all_target_months",
            target_months.issubset(set(selected_rows["target_month"].astype(str))),
            ",".join(sorted(set(selected_rows["target_month"].astype(str)))),
        ),
        (
            "fallback_donor_commit_activity_audited_for_all_target_months",
            target_months.issubset(set(fallback_rows["target_month"].astype(str))),
            ",".join(sorted(set(fallback_rows["target_month"].astype(str)))),
        ),
        (
            "commit_activity_audit_completed_without_failure",
            activity_failures.empty,
            int(len(activity_failures)),
        ),
        (
            "agc_outcome_not_read",
            bool(~activity["agc_outcome_read"].map(bool_value).any()),
            "No AGC outcome input exists",
        ),
        (
            "did_not_run",
            bool(~activity["did_executed"].map(bool_value).any()),
            "Git commit-activity audit only",
        ),
        (
            "causal_interpretation_disallowed",
            True,
            "Noncausal design-stage donor feasibility audit",
        ),
    ]
    return pd.DataFrame(
        [
            {"check": check, "passed": passed, "observed": observed}
            for check, passed, observed in checks
        ]
    )


def write_status(output_dir: Path, status: str, lines: Iterable[str]) -> None:
    """Write the status file consumed by the shell wrapper."""

    (output_dir / f"{OUTPUT_PREFIX}_status.txt").write_text(
        "\n".join([status, *lines]) + "\n",
        encoding="utf-8",
    )


def run_analysis(args: argparse.Namespace) -> dict[str, object]:
    """Run the frozen donor target-month commit-activity audit."""

    freeze_path = Path(args.freeze_manifest)
    availability_path = Path(args.snapshot_availability)
    clone_root = Path(args.control_clone_root)
    output_dir = Path(args.output_dir)

    if not freeze_path.is_file():
        raise AnalysisError(f"Freeze manifest not found: {freeze_path}")
    if not availability_path.is_file():
        raise AnalysisError(f"Snapshot availability not found: {availability_path}")
    if not clone_root.is_dir():
        raise AnalysisError(f"Control clone root not found: {clone_root}")

    selected_donor = normalize_repo_name(args.expected_selected_donor)
    fallback_donor = normalize_repo_name(args.expected_fallback_donor)
    freeze, availability = load_freeze_inputs(
        freeze_path,
        availability_path,
        selected_donor,
        fallback_donor,
    )

    windows = [month_window(value) for value in args.target_month]
    if len({window.label for window in windows}) != len(windows):
        raise AnalysisError("Target months must be unique.")

    output_dir.mkdir(parents=True, exist_ok=True)
    activity_rows: list[dict[str, object]] = []
    for repo_name in (selected_donor, fallback_donor):
        repo_path = discover_repo_path(clone_root, repo_name)
        repo_availability = availability[availability["repo_name"].eq(repo_name)].copy()
        for window in windows:
            activity_rows.append(
                audit_repo_month(repo_name, repo_path, repo_availability, window)
            )

    activity = pd.DataFrame(activity_rows)
    validation = validation_table(
        freeze,
        availability,
        activity,
        selected_donor,
        fallback_donor,
        {window.label for window in windows},
    )
    failed = validation[~validation["passed"].map(bool_value)]

    activity_path = output_dir / f"{OUTPUT_PREFIX}_monthly_commits.csv"
    validation_path = output_dir / f"{OUTPUT_PREFIX}_validation.csv"
    summary_path = output_dir / f"{OUTPUT_PREFIX}_summary.json"
    provenance_path = output_dir / f"{OUTPUT_PREFIX}_provenance.csv"

    activity.to_csv(activity_path, index=False)
    validation.to_csv(validation_path, index=False)

    provenance = pd.DataFrame(
        [
            {
                "freeze_manifest": str(freeze_path),
                "freeze_manifest_sha256": sha256_file(freeze_path),
                "snapshot_availability": str(availability_path),
                "snapshot_availability_sha256": sha256_file(availability_path),
                "ranking_sha256": freeze["ranking_sha256"].dropna().astype(str).iloc[0],
                "selected_donor": selected_donor,
                "fallback_donor": fallback_donor,
                "target_months": ",".join(window.label for window in windows),
                "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "post_adoption_agc_outcome_read": False,
                "did_executed": False,
            }
        ]
    )
    provenance.to_csv(provenance_path, index=False)

    selected_activity = activity[activity["repo_name"].eq(selected_donor)].copy()
    fallback_activity = activity[activity["repo_name"].eq(fallback_donor)].copy()
    selected_active_months = selected_activity.loc[
        selected_activity["month_has_commit"].map(bool_value), "target_month"
    ].astype(str).tolist()
    fallback_active_months = fallback_activity.loc[
        fallback_activity["month_has_commit"].map(bool_value), "target_month"
    ].astype(str).tolist()

    summary = {
        "status": "PASS" if failed.empty else "FAIL",
        "analysis": "frozen rematched donor target-month Git commit-activity audit",
        "interpretation": "noncausal design-stage donor feasibility audit",
        "selected_donor": selected_donor,
        "fallback_donor": fallback_donor,
        "target_months": [window.label for window in windows],
        "selected_donor_active_target_months": selected_active_months,
        "selected_donor_inactive_target_months": [
            window.label
            for window in windows
            if window.label not in set(selected_active_months)
        ],
        "fallback_donor_active_target_months": fallback_active_months,
        "fallback_donor_inactive_target_months": [
            window.label
            for window in windows
            if window.label not in set(fallback_active_months)
        ],
        "selected_donor_has_commits_in_all_target_months": len(selected_active_months)
        == len(windows),
        "fallback_donor_has_commits_in_all_target_months": len(fallback_active_months)
        == len(windows),
        "post_adoption_agc_outcome_read": False,
        "did_ran": False,
        "causal_interpretation_allowed": False,
        "output_hashes": {
            "monthly_commits": sha256_file(activity_path),
            "validation": sha256_file(validation_path),
            "provenance": sha256_file(provenance_path),
        },
        "next_step": (
            "Interpret inactive target months before defining any AGC outcome extraction "
            "or donor month-substitution rule."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status = "PASS" if failed.empty else "FAIL"
    write_status(
        output_dir,
        status,
        [
            f"freeze_manifest_sha256={sha256_file(freeze_path)}",
            f"snapshot_availability_sha256={sha256_file(availability_path)}",
            f"selected_donor={selected_donor}",
            f"fallback_donor={fallback_donor}",
            f"selected_active_target_months={','.join(selected_active_months) or 'NONE'}",
            f"fallback_active_target_months={','.join(fallback_active_months) or 'NONE'}",
            "post_adoption_agc_outcome_read=FALSE",
            "did_ran=FALSE",
        ],
    )

    print("=" * 80)
    print("run-py-8f: frozen donor target-month Git commit-activity audit")
    print("=" * 80)
    print(f"Selected donor: {selected_donor}")
    print(f"Fallback donor: {fallback_donor}")
    print(f"Target months: {', '.join(window.label for window in windows)}")
    print("Post-adoption AGC outcomes inspected: NO")
    print("DiD executed: NO")
    print("\nMonthly commit activity:")
    print(
        activity[
            [
                "repo_name",
                "target_month",
                "month_commit_count",
                "month_has_commit",
                "activity_status",
                "audit_ref",
                "first_month_commit_timestamp",
                "last_month_commit_timestamp",
            ]
        ].to_string(index=False)
    )
    print(f"\nOutput directory: {output_dir}")

    if not failed.empty:
        raise AnalysisError(
            "Validation failed: " + ", ".join(failed["check"].astype(str))
        )
    return summary


def initialize_test_repo(
    root: Path,
    repo_name: str,
    commits: Sequence[tuple[str, str]],
) -> Path:
    """Create a small repository with deterministic commit timestamps."""

    repo_path = root / repo_name.replace("/", "_")
    repo_path.mkdir(parents=True, exist_ok=True)
    run_command(["git", "init", "-b", "main"], cwd=repo_path, check=True)
    run_command(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
    run_command(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
    )
    run_command(
        ["git", "remote", "add", "origin", f"https://github.com/{repo_name}.git"],
        cwd=repo_path,
        check=True,
    )

    for index, (timestamp, content) in enumerate(commits, start=1):
        source = repo_path / "example.py"
        source.write_text(content + "\n", encoding="utf-8")
        run_command(["git", "add", "example.py"], cwd=repo_path, check=True)
        env = {
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
        }
        completed = subprocess.run(
            ["git", "commit", "-m", f"commit {index}"],
            cwd=repo_path,
            text=True,
            capture_output=True,
            env={**dict(**subprocess.os.environ), **env},
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise AnalysisError(f"Synthetic commit failed: {detail}")
    return repo_path


def run_self_test() -> None:
    """Exercise positive and inactive target-month paths end to end."""

    with tempfile.TemporaryDirectory(prefix="run-py-8f-self-test-") as temp_dir:
        root = Path(temp_dir)
        clone_root = root / "control-repos"
        clone_root.mkdir()
        output_dir = root / "output"

        selected = "example/SelectedDonor"
        fallback = "example/FallbackDonor"
        initialize_test_repo(
            clone_root,
            selected,
            [
                ("2025-03-17T12:00:00+00:00", "x = 1"),
                ("2025-04-15T12:00:00+00:00", "x = 2"),
                ("2025-06-15T12:00:00+00:00", "x = 3"),
            ],
        )
        initialize_test_repo(
            clone_root,
            fallback,
            [("2025-03-01T12:00:00+00:00", "y = 1")],
        )

        ranking_sha = "a" * 64
        freeze = pd.DataFrame(
            [
                {
                    "freeze_role": "selected",
                    "candidate_control_repo": selected,
                    "common_donor_rank": 1,
                    "ranking_sha256": ranking_sha,
                    "frozen_before_post_adoption_outcome_review": True,
                    "post_adoption_agc_outcome_read": False,
                    "did_executed": False,
                },
                {
                    "freeze_role": "fallback",
                    "candidate_control_repo": fallback,
                    "common_donor_rank": 2,
                    "ranking_sha256": ranking_sha,
                    "frozen_before_post_adoption_outcome_review": True,
                    "post_adoption_agc_outcome_read": False,
                    "did_executed": False,
                },
            ]
        )
        freeze_path = root / "freeze.csv"
        freeze.to_csv(freeze_path, index=False)

        availability_rows: list[dict[str, object]] = []
        for repo_name in (selected, fallback):
            repo_path = clone_root / repo_name.replace("/", "_")
            for month in DEFAULT_TARGET_MONTHS:
                cutoff = month_window(month)
                commit = git_try_output(
                    repo_path,
                    [
                        "rev-list",
                        "-1",
                        f"--before={cutoff.end_utc_exclusive.isoformat()}",
                        "HEAD",
                    ],
                )
                availability_rows.append(
                    {
                        "repo_name": repo_name,
                        "snapshot_month": month,
                        "snapshot_available": True,
                        "cutoff_commit_sha": commit,
                        "cutoff_commit_ref": "HEAD",
                        "cutoff_commit_timestamp": git_try_output(
                            repo_path,
                            ["show", "-s", "--format=%cI", commit],
                        ),
                    }
                )
        availability_path = root / "availability.csv"
        pd.DataFrame(availability_rows).to_csv(availability_path, index=False)

        args = argparse.Namespace(
            freeze_manifest=str(freeze_path),
            snapshot_availability=str(availability_path),
            control_clone_root=str(clone_root),
            output_dir=str(output_dir),
            expected_selected_donor=selected,
            expected_fallback_donor=fallback,
            target_month=list(DEFAULT_TARGET_MONTHS),
        )
        summary = run_analysis(args)
        activity = pd.read_csv(
            output_dir / f"{OUTPUT_PREFIX}_monthly_commits.csv"
        )

        selected_counts = activity[
            activity["repo_name"].eq(selected)
        ].set_index("target_month")["month_commit_count"].to_dict()
        fallback_counts = activity[
            activity["repo_name"].eq(fallback)
        ].set_index("target_month")["month_commit_count"].to_dict()

        assert selected_counts == {"2025-04": 1, "2025-06": 1}
        assert fallback_counts == {"2025-04": 0, "2025-06": 0}
        assert summary["selected_donor_has_commits_in_all_target_months"] is True
        assert summary["fallback_donor_has_commits_in_all_target_months"] is False
        assert summary["post_adoption_agc_outcome_read"] is False
        print("Self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Audit whether frozen Webscout replacement donors have Git commits "
            "inside the target calendar months without reading AGC outcomes."
        )
    )
    parser.add_argument("--freeze-manifest")
    parser.add_argument("--snapshot-availability")
    parser.add_argument("--control-clone-root")
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--expected-selected-donor",
        default=DEFAULT_SELECTED_DONOR,
    )
    parser.add_argument(
        "--expected-fallback-donor",
        default=DEFAULT_FALLBACK_DONOR,
    )
    parser.add_argument(
        "--target-month",
        action="append",
        default=None,
        help="Target calendar month in YYYY-MM format; may be repeated.",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> None:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return

    required = {
        "freeze_manifest": args.freeze_manifest,
        "snapshot_availability": args.snapshot_availability,
        "control_clone_root": args.control_clone_root,
        "output_dir": args.output_dir,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error("Missing required arguments: " + ", ".join(missing))

    if args.target_month is None:
        args.target_month = list(DEFAULT_TARGET_MONTHS)

    try:
        run_analysis(args)
    except AnalysisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
