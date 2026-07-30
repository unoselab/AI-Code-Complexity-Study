#!/usr/bin/env python3
"""Freeze the run-py-8d donor ranking and audit snapshot availability.

This design-stage script intentionally does not read AGC detector outputs,
class-method counts, or Difference-in-Differences results. It freezes the
pre-outcome donor choice from run-py-8d and checks only Git snapshot
availability for the requested future month-end cutoffs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

OUTPUT_PREFIX = "webscout_rematched_donor"
DEFAULT_SELECTED_DONOR = "Hack-a-Day/2024-Supercon-8-Add-On-Badge"
DEFAULT_FALLBACK_DONOR = "viktoriasemaan/sa-ai-agent"
DEFAULT_CUTOFFS = (
    "2025-04-30T23:59:59+00:00",
    "2025-06-30T23:59:59+00:00",
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
class SnapshotCutoff:
    label: str
    timestamp: datetime


class AnalysisError(RuntimeError):
    """Raised for a failed frozen-design validation."""


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
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
    completed = run_command(
        ["git", "-C", str(repo_path), *args],
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_utc(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def month_label(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m")


def normalize_repo_name(value: object) -> str:
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
    url = git_try_output(repo_path, ["remote", "get-url", "origin"])
    return normalize_repo_name(url)


def discover_repo_path(clone_root: Path, repo_name: str) -> Path | None:
    expected = clone_root / repo_name.replace("/", "_")
    if expected.is_dir():
        return expected.resolve()

    for child in sorted(path for path in clone_root.iterdir() if path.is_dir()):
        if repository_name_from_remote(child) == repo_name:
            return child.resolve()
    return None


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

    deduplicated: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            deduplicated.append(ref)
    deduplicated.append("--all")
    return deduplicated


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
    output = git_try_output(repo_path, ["show", "-s", "--format=%cI%x09%ct", commit])
    if not output:
        return "", None
    parts = output.splitlines()[0].split("\t")
    iso = parts[0].strip()
    epoch: int | None = None
    if len(parts) > 1:
        try:
            epoch = int(parts[1].strip())
        except ValueError:
            epoch = None
    return iso, epoch


def is_excluded_python_path(path_text: str, excluded_dirs: set[str]) -> bool:
    path = Path(path_text)
    return not path_text.lower().endswith(".py") or any(
        part in excluded_dirs for part in path.parts[:-1]
    )


def list_python_paths(
    repo_path: Path,
    commit: str,
    excluded_dirs: set[str],
) -> tuple[list[str], str]:
    completed = run_command(
        ["git", "-C", str(repo_path), "ls-tree", "-r", "--name-only", commit],
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip() or completed.stdout.strip()
        return [], f"git_ls_tree_failed:{reason}"
    paths = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not is_excluded_python_path(line.strip(), excluded_dirs)
    ]
    return paths, ""


def audit_snapshot(
    repo_name: str,
    repo_path: Path | None,
    cutoff: SnapshotCutoff,
    excluded_dirs: set[str],
) -> dict[str, object]:
    base: dict[str, object] = {
        "repo_name": repo_name,
        "clone_path": "" if repo_path is None else str(repo_path),
        "snapshot_month": cutoff.label,
        "snapshot_cutoff_utc": cutoff.timestamp.isoformat(),
        "clone_exists": bool(repo_path and repo_path.is_dir()),
        "is_git_repository": False,
        "is_shallow_repository": None,
        "cutoff_commit_sha": "",
        "cutoff_commit_ref": "",
        "cutoff_commit_timestamp": "",
        "cutoff_commit_epoch": None,
        "python_file_count": None,
        "python_source_present": False,
        "git_tree_readable": False,
        "snapshot_available": False,
        "availability_status": "",
        "failure_reason": "",
        "agc_outcome_read": False,
        "did_executed": False,
    }
    if repo_path is None or not repo_path.is_dir():
        base["availability_status"] = "missing_local_clone"
        base["failure_reason"] = "local_clone_not_found"
        return base

    inside = git_try_output(repo_path, ["rev-parse", "--is-inside-work-tree"])
    if inside.lower() != "true":
        base["availability_status"] = "invalid_git_repository"
        base["failure_reason"] = "not_inside_git_work_tree"
        return base
    base["is_git_repository"] = True

    shallow = git_try_output(repo_path, ["rev-parse", "--is-shallow-repository"])
    base["is_shallow_repository"] = shallow.lower() == "true"

    commit, ref = select_cutoff_commit(repo_path, cutoff.timestamp)
    if not commit:
        base["availability_status"] = "no_commit_at_or_before_cutoff"
        base["failure_reason"] = "no_commit_at_or_before_cutoff"
        return base

    base["cutoff_commit_sha"] = commit
    base["cutoff_commit_ref"] = ref
    commit_iso, commit_epoch = commit_timestamp(repo_path, commit)
    base["cutoff_commit_timestamp"] = commit_iso
    base["cutoff_commit_epoch"] = commit_epoch

    python_paths, failure = list_python_paths(repo_path, commit, excluded_dirs)
    if failure:
        base["availability_status"] = "git_tree_read_failure"
        base["failure_reason"] = failure
        return base

    base["git_tree_readable"] = True
    base["python_file_count"] = len(python_paths)
    base["python_source_present"] = len(python_paths) > 0
    base["snapshot_available"] = True
    base["availability_status"] = (
        "available_with_python_source"
        if python_paths
        else "available_without_python_source"
    )
    return base


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def load_and_validate_ranking(
    ranking_path: Path,
    expected_selected_donor: str,
    expected_fallback_donor: str,
) -> tuple[pd.DataFrame, pd.Series, pd.Series | None]:
    ranking = pd.read_csv(ranking_path, low_memory=False)
    required = {
        "candidate_control_repo",
        "common_donor_rank",
        "eligible_replacement_candidate",
        "is_original_control",
    }
    missing = sorted(required - set(ranking.columns))
    if missing:
        raise AnalysisError(f"Common donor ranking is missing columns: {missing}")

    ranking["candidate_control_repo"] = ranking["candidate_control_repo"].map(
        normalize_repo_name
    )
    ranking["common_donor_rank"] = pd.to_numeric(
        ranking["common_donor_rank"], errors="coerce"
    )
    eligible = ranking[
        ranking["eligible_replacement_candidate"].map(bool_value)
        & ~ranking["is_original_control"].map(bool_value)
        & ranking["common_donor_rank"].notna()
    ].copy()
    eligible = eligible.sort_values(
        ["common_donor_rank", "candidate_control_repo"]
    ).reset_index(drop=True)
    if eligible.empty:
        raise AnalysisError("No eligible non-original donor exists in the frozen ranking.")

    selected = eligible.iloc[0]
    selected_repo = str(selected["candidate_control_repo"])
    if selected_repo != expected_selected_donor:
        raise AnalysisError(
            "Frozen rank-1 donor mismatch: "
            f"expected {expected_selected_donor}, observed {selected_repo}"
        )
    if int(selected["common_donor_rank"]) != 1:
        raise AnalysisError("Selected donor does not have common_donor_rank=1.")

    fallback: pd.Series | None = None
    if len(eligible) >= 2:
        fallback = eligible.iloc[1]
        fallback_repo = str(fallback["candidate_control_repo"])
        if expected_fallback_donor and fallback_repo != expected_fallback_donor:
            raise AnalysisError(
                "Frozen rank-2 fallback mismatch: "
                f"expected {expected_fallback_donor}, observed {fallback_repo}"
            )
    elif expected_fallback_donor:
        raise AnalysisError("Expected a rank-2 fallback donor, but none was found.")

    return ranking, selected, fallback


def freeze_rows(
    ranking_path: Path,
    selected: pd.Series,
    fallback: pd.Series | None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role, row in (("selected", selected), ("fallback", fallback)):
        if row is None:
            continue
        record = row.to_dict()
        record.update(
            {
                "freeze_role": role,
                "ranking_file": str(ranking_path),
                "ranking_sha256": sha256_file(ranking_path),
                "frozen_before_post_adoption_outcome_review": True,
                "post_adoption_agc_outcome_read": False,
                "did_executed": False,
                "freeze_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        rows.append(record)
    return pd.DataFrame(rows)


def validation_table(
    freeze: pd.DataFrame,
    availability: pd.DataFrame,
    selected_donor: str,
    fallback_donor: str,
    required_months: set[str],
) -> pd.DataFrame:
    selected_availability = availability[
        availability["repo_name"].eq(selected_donor)
    ]
    selected_months = set(
        selected_availability.loc[
            selected_availability["snapshot_available"].map(bool_value),
            "snapshot_month",
        ].astype(str)
    )

    checks: list[tuple[str, bool, object]] = [
        (
            "ranking_frozen_before_post_adoption_outcome_review",
            bool(freeze["frozen_before_post_adoption_outcome_review"].map(bool_value).all()),
            "TRUE",
        ),
        (
            "selected_donor_is_rank_one",
            bool(
                (
                    pd.to_numeric(
                        freeze.loc[freeze["freeze_role"].eq("selected"), "common_donor_rank"],
                        errors="coerce",
                    )
                    == 1
                ).all()
            ),
            selected_donor,
        ),
        (
            "selected_donor_is_not_original_control",
            bool(
                ~freeze.loc[
                    freeze["freeze_role"].eq("selected"), "is_original_control"
                ].map(bool_value).any()
            ),
            selected_donor,
        ),
        (
            "fallback_donor_frozen",
            fallback_donor
            in set(freeze["candidate_control_repo"].astype(str)),
            fallback_donor,
        ),
        (
            "selected_donor_snapshot_available_2025_04",
            "2025-04" in selected_months,
            "2025-04" in selected_months,
        ),
        (
            "selected_donor_snapshot_available_2025_06",
            "2025-06" in selected_months,
            "2025-06" in selected_months,
        ),
        (
            "all_required_selected_donor_snapshots_available",
            required_months.issubset(selected_months),
            ",".join(sorted(selected_months)),
        ),
        (
            "agc_outcome_not_read",
            bool(~availability["agc_outcome_read"].map(bool_value).any()),
            "No AGC outcome input exists",
        ),
        (
            "did_not_run",
            bool(~availability["did_executed"].map(bool_value).any()),
            "Snapshot availability only",
        ),
    ]
    return pd.DataFrame(
        [
            {"check": check, "passed": passed, "observed": observed}
            for check, passed, observed in checks
        ]
    )


def write_status(output_dir: Path, status: str, lines: Iterable[str]) -> None:
    content = [status, *lines]
    (output_dir / f"{OUTPUT_PREFIX}_status.txt").write_text(
        "\n".join(content) + "\n", encoding="utf-8"
    )


def run_analysis(args: argparse.Namespace) -> dict[str, object]:
    ranking_path = Path(args.common_donor_ranking)
    clone_root = Path(args.control_clone_root)
    output_dir = Path(args.output_dir)

    if not ranking_path.is_file():
        raise AnalysisError(f"Common donor ranking not found: {ranking_path}")
    if not clone_root.is_dir():
        raise AnalysisError(f"Control clone root not found: {clone_root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    ranking, selected, fallback = load_and_validate_ranking(
        ranking_path,
        normalize_repo_name(args.expected_selected_donor),
        normalize_repo_name(args.expected_fallback_donor),
    )
    freeze = freeze_rows(ranking_path, selected, fallback)

    frozen_repos = freeze["candidate_control_repo"].astype(str).tolist()
    cutoffs = [
        SnapshotCutoff(month_label(parse_utc(value)), parse_utc(value))
        for value in args.snapshot_cutoff_utc
    ]
    excluded_dirs = {
        item.strip() for item in args.excluded_dirs.split(",") if item.strip()
    }

    availability_rows: list[dict[str, object]] = []
    for repo_name in frozen_repos:
        repo_path = discover_repo_path(clone_root, repo_name)
        for cutoff in cutoffs:
            availability_rows.append(
                audit_snapshot(repo_name, repo_path, cutoff, excluded_dirs)
            )
    availability = pd.DataFrame(availability_rows)

    validation = validation_table(
        freeze,
        availability,
        normalize_repo_name(args.expected_selected_donor),
        normalize_repo_name(args.expected_fallback_donor),
        {cutoff.label for cutoff in cutoffs},
    )
    failed = validation[~validation["passed"].map(bool_value)]

    freeze_path = output_dir / f"{OUTPUT_PREFIX}_freeze_manifest.csv"
    availability_path = output_dir / f"{OUTPUT_PREFIX}_snapshot_availability.csv"
    validation_path = output_dir / f"{OUTPUT_PREFIX}_validation.csv"
    summary_path = output_dir / f"{OUTPUT_PREFIX}_summary.json"

    freeze.to_csv(freeze_path, index=False)
    availability.to_csv(availability_path, index=False)
    validation.to_csv(validation_path, index=False)

    selected_rows = availability[
        availability["repo_name"].eq(normalize_repo_name(args.expected_selected_donor))
    ].copy()
    selected_ready = bool(
        len(selected_rows) == len(cutoffs)
        and selected_rows["snapshot_available"].map(bool_value).all()
    )
    summary = {
        "status": "PASS" if failed.empty else "FAIL",
        "analysis": "freeze run-py-8d donor ranking and check Git snapshot availability",
        "interpretation": "noncausal design-stage donor feasibility audit",
        "common_donor_ranking": str(ranking_path),
        "common_donor_ranking_sha256": sha256_file(ranking_path),
        "selected_donor": normalize_repo_name(args.expected_selected_donor),
        "fallback_donor": normalize_repo_name(args.expected_fallback_donor),
        "snapshot_cutoffs_utc": [cutoff.timestamp.isoformat() for cutoff in cutoffs],
        "selected_donor_all_snapshots_available": selected_ready,
        "post_adoption_agc_outcome_read": False,
        "did_ran": False,
        "causal_interpretation_allowed": False,
        "output_hashes": {
            "freeze_manifest": sha256_file(freeze_path),
            "snapshot_availability": sha256_file(availability_path),
            "validation": sha256_file(validation_path),
        },
        "next_step": (
            "Proceed to the separately defined donor outcome-extraction step only "
            "after preserving these hashes."
            if selected_ready
            else "Do not open AGC outcomes; apply the pre-frozen fallback rule or "
            "revise the design before outcome extraction."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    status = "PASS" if failed.empty else "FAIL"
    write_status(
        output_dir,
        status,
        [
            f"ranking_sha256={sha256_file(ranking_path)}",
            f"selected_donor={normalize_repo_name(args.expected_selected_donor)}",
            f"fallback_donor={normalize_repo_name(args.expected_fallback_donor)}",
            f"selected_donor_all_snapshots_available={str(selected_ready).upper()}",
            "post_adoption_agc_outcome_read=FALSE",
            "did_ran=FALSE",
        ],
    )

    print("=" * 80)
    print("run-py-8e: donor ranking freeze and snapshot availability")
    print("=" * 80)
    print(f"Ranking SHA-256: {sha256_file(ranking_path)}")
    print(f"Selected donor: {normalize_repo_name(args.expected_selected_donor)}")
    print(f"Fallback donor: {normalize_repo_name(args.expected_fallback_donor)}")
    print("Post-adoption AGC outcomes inspected: NO")
    print("DiD executed: NO")
    print("\nSnapshot availability:")
    print(
        availability[
            [
                "repo_name",
                "snapshot_month",
                "snapshot_available",
                "availability_status",
                "cutoff_commit_sha",
                "cutoff_commit_timestamp",
                "python_file_count",
            ]
        ].to_string(index=False)
    )
    print(f"\nOutput directory: {output_dir}")

    if not failed.empty:
        raise AnalysisError(
            "Validation failed: " + ", ".join(failed["check"].astype(str))
        )
    return summary


def initialize_test_repo(repo_path: Path, repo_name: str) -> None:
    repo_path.mkdir(parents=True, exist_ok=True)
    run_command(["git", "init", "-b", "main"], cwd=repo_path, check=True)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    run_command(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
    run_command(
        ["git", "remote", "add", "origin", f"https://github.com/{repo_name}.git"],
        cwd=repo_path,
        check=True,
    )


def commit_test_file(repo_path: Path, relative: str, content: str, timestamp: str) -> None:
    path = repo_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run_command(["git", "add", relative], cwd=repo_path, check=True)
    env = dict(**__import__("os").environ)
    env["GIT_AUTHOR_DATE"] = timestamp
    env["GIT_COMMITTER_DATE"] = timestamp
    completed = subprocess.run(
        ["git", "commit", "-m", f"add {relative}"],
        cwd=repo_path,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise AnalysisError(completed.stderr.strip() or completed.stdout.strip())


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-8e-self-test-") as tmp:
        root = Path(tmp)
        clone_root = root / "control-repos"
        selected_repo = DEFAULT_SELECTED_DONOR
        fallback_repo = DEFAULT_FALLBACK_DONOR

        selected_path = clone_root / selected_repo.replace("/", "_")
        fallback_path = clone_root / fallback_repo.replace("/", "_")
        initialize_test_repo(selected_path, selected_repo)
        initialize_test_repo(fallback_path, fallback_repo)
        commit_test_file(
            selected_path,
            "src/main.py",
            "def main():\n    return 1\n",
            "2025-04-15T12:00:00+00:00",
        )
        commit_test_file(
            selected_path,
            "src/june.py",
            "def june():\n    return 2\n",
            "2025-06-15T12:00:00+00:00",
        )
        commit_test_file(
            fallback_path,
            "fallback.py",
            "def fallback():\n    return 3\n",
            "2025-03-01T12:00:00+00:00",
        )

        ranking_path = root / "ranking.csv"
        pd.DataFrame(
            [
                {
                    "candidate_control_repo": selected_repo,
                    "common_donor_rank": 1,
                    "eligible_replacement_candidate": True,
                    "is_original_control": False,
                    "selection_strategy": "test",
                },
                {
                    "candidate_control_repo": fallback_repo,
                    "common_donor_rank": 2,
                    "eligible_replacement_candidate": True,
                    "is_original_control": False,
                    "selection_strategy": "test",
                },
            ]
        ).to_csv(ranking_path, index=False)

        args = argparse.Namespace(
            common_donor_ranking=str(ranking_path),
            control_clone_root=str(clone_root),
            output_dir=str(root / "output"),
            expected_selected_donor=selected_repo,
            expected_fallback_donor=fallback_repo,
            snapshot_cutoff_utc=list(DEFAULT_CUTOFFS),
            excluded_dirs=",".join(DEFAULT_EXCLUDED_DIRS),
        )
        summary = run_analysis(args)
        if not summary["selected_donor_all_snapshots_available"]:
            raise AnalysisError("Self-test selected donor snapshots were not available.")
        print("Self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the run-py-8d donor ranking and check 2025-04/2025-06 "
            "Git snapshot availability without reading AGC outcomes."
        )
    )
    parser.add_argument("--common-donor-ranking")
    parser.add_argument("--control-clone-root")
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--expected-selected-donor", default=DEFAULT_SELECTED_DONOR
    )
    parser.add_argument(
        "--expected-fallback-donor", default=DEFAULT_FALLBACK_DONOR
    )
    parser.add_argument(
        "--snapshot-cutoff-utc",
        action="append",
        default=None,
        help="Repeat for each month-end cutoff.",
    )
    parser.add_argument(
        "--excluded-dirs", default=",".join(DEFAULT_EXCLUDED_DIRS)
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return

    required = (
        "common_donor_ranking",
        "control_clone_root",
        "output_dir",
    )
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("Missing required arguments: " + ", ".join(missing))
    if args.snapshot_cutoff_utc is None:
        args.snapshot_cutoff_utc = list(DEFAULT_CUTOFFS)

    try:
        run_analysis(args)
    except (AnalysisError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
