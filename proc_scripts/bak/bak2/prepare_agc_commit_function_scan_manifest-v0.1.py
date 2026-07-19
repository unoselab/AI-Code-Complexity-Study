#!/usr/bin/env python3
"""Prepare repository-month commit/first-parent pairs for function-event analysis.

For every repository-month in the validated Python panel, this script selects
exactly the commits represented by the monthly ``commits`` activity count and
writes one direct first-parent pair for each selected commit:

    scan_parent_commit (X-1) -> scan_current_commit (X)

Selection strategy
------------------
1. For a consecutive month with a valid previous monthly snapshot, use the Git
   range ``previous_month_commit..month_end_commit``.
2. If that range is unavailable or its count differs from the panel count,
   recover the last ``panel_commits`` commits reachable from the month-end
   commit. This supports the first observed repository-month.
3. A zero-commit month produces no scan pairs.

Repeated changes and later reverts are intentionally retained because each
commit is compared only with its direct first parent. This stage does not parse
Python files and does not run the AGC detector.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")

PANEL_REQUIRED = {
    "dataset_source",
    "repo_name",
    "time",
    "latest_commit",
    "commits",
}
MANIFEST_REQUIRED = {
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit",
}

BOUNDARY_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_month_commit",
    "month_end_commit",
    "month_gap",
    "comparison_status",
    "selection_method",
    "repo_dir",
    "commit_range",
    "panel_commits",
    "range_commits_found",
    "selected_commits",
    "selected_count_matches_panel",
    "non_merge_commits_selected",
    "merge_commits_selected",
    "first_scan_commit",
    "last_scan_commit",
    "last_scan_commit_matches_month_end",
    "commits_with_committer_month_match",
    "commits_with_committer_month_mismatch",
]

MONTH_END_PAIR_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "month_end_commit",
    "month_end_parent_commit",
    "parent_count",
    "is_root_commit",
    "is_merge_commit",
    "repo_dir",
    "lookup_status",
]

PAIR_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month",
    "previous_month_commit",
    "month_end_commit",
    "commit_range",
    "selection_method",
    "panel_commits",
    "commit_order",
    "scan_parent_commit",
    "scan_current_commit",
    "parent_count",
    "is_root_commit",
    "is_merge_commit",
    "primary_scan_eligible",
    "is_month_end_commit",
    "committer_datetime",
    "committer_month",
    "committer_month_matches_panel_month",
    "repo_dir",
]

ERROR_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "previous_month_commit",
    "month_end_commit",
    "stage",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare direct first-parent pairs for commit-function events."
    )
    parser.add_argument(
        "--input-panel",
        type=Path,
        default=Path(
            "repo_python/run-py-4a/strict/"
            "panel_event_monthly_agc_changed_block_py.csv"
        ),
    )
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        default=Path(
            "repo_python/run-py-3a/strict/repo_month_snapshot_manifest.csv"
        ),
    )
    parser.add_argument(
        "--treatment-clone-dir",
        type=Path,
        default=Path("../treatment-repos"),
    )
    parser.add_argument(
        "--control-clone-dir",
        type=Path,
        default=Path("../control-repos"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("repo_python/run-py-5a/strict"),
    )
    parser.add_argument(
        "--qc-dir",
        type=Path,
        default=Path("repo_python/tmp/run-py-5a/strict"),
    )
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def run_git(repo_dir: Path, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *list(args)],
        text=True,
        capture_output=True,
        check=False,
    )


def require_git_ok(result: subprocess.CompletedProcess[str], label: str) -> str:
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{label}: {message}")
    return result.stdout.strip()


def valid_commit_text(value: Any) -> bool:
    text = str(value).strip()
    return bool(FULL_SHA_RE.fullmatch(text))


def commit_exists(repo_dir: Path, commit: str) -> bool:
    if not valid_commit_text(commit):
        return False
    return run_git(repo_dir, ["cat-file", "-e", f"{commit}^{{commit}}"]).returncode == 0


def is_ancestor(repo_dir: Path, previous: str, current: str) -> bool:
    return (
        run_git(repo_dir, ["merge-base", "--is-ancestor", previous, current]).returncode
        == 0
    )


def list_range_commits(repo_dir: Path, previous: str, current: str) -> list[str]:
    output = require_git_ok(
        run_git(
            repo_dir,
            ["rev-list", "--reverse", "--topo-order", f"{previous}..{current}"],
        ),
        "git rev-list range failed",
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def list_last_n_commits(repo_dir: Path, current: str, count: int) -> list[str]:
    if count <= 0:
        return []
    output = require_git_ok(
        run_git(
            repo_dir,
            [
                "rev-list",
                "--topo-order",
                f"--max-count={count}",
                current,
            ],
        ),
        "git rev-list backfill failed",
    )
    newest_first = [line.strip() for line in output.splitlines() if line.strip()]
    return list(reversed(newest_first))


def get_parents(repo_dir: Path, commit: str) -> list[str]:
    output = require_git_ok(
        run_git(repo_dir, ["rev-list", "--parents", "-n", "1", commit]),
        f"cannot read parents for {commit}",
    )
    fields = output.split()
    if not fields or fields[0] != commit:
        raise RuntimeError(f"unexpected parent record for {commit}: {output!r}")
    return fields[1:]


def get_committer_datetime(repo_dir: Path, commit: str) -> str:
    return require_git_ok(
        run_git(repo_dir, ["show", "-s", "--format=%cI", commit]),
        f"cannot read committer datetime for {commit}",
    )


def month_number(period: pd.Period) -> int:
    return period.year * 12 + period.month


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path, dtype={"latest_commit": "string"}, low_memory=False)
    missing = sorted(PANEL_REQUIRED - set(panel.columns))
    if missing:
        raise ValueError(f"Input panel missing columns: {missing}")

    for column in ["dataset_source", "repo_name", "time"]:
        panel[column] = panel[column].astype(str).str.strip()
    panel["latest_commit"] = panel["latest_commit"].fillna("").astype(str).str.strip()
    panel["commits"] = pd.to_numeric(panel["commits"], errors="coerce")
    if panel["commits"].isna().any() or panel["commits"].lt(0).any():
        raise ValueError("Panel commits must contain nonnegative numeric values")
    if (panel["commits"] % 1 != 0).any():
        raise ValueError("Panel commits must contain integer values")
    panel["commits"] = panel["commits"].astype(int)

    invalid_sources = sorted(
        set(panel["dataset_source"]) - {"treatment", "control"}
    )
    if invalid_sources:
        raise ValueError(f"Unsupported dataset sources: {invalid_sources}")

    duplicates = int(
        panel.duplicated(["dataset_source", "repo_name", "time"]).sum()
    )
    if duplicates:
        raise ValueError(f"Duplicate panel source/repo/month rows: {duplicates}")

    panel["month_period"] = pd.PeriodIndex(panel["time"], freq="M")
    return panel.sort_values(
        ["dataset_source", "repo_name", "month_period"]
    ).reset_index(drop=True)


def load_manifest(path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(path, dtype={"latest_commit": "string"}, low_memory=False)
    missing = sorted(MANIFEST_REQUIRED - set(manifest.columns))
    if missing:
        raise ValueError(f"Snapshot manifest missing columns: {missing}")

    for column in ["dataset_source", "repo_name", "month"]:
        manifest[column] = manifest[column].astype(str).str.strip()
    manifest["latest_commit"] = (
        manifest["latest_commit"].fillna("").astype(str).str.strip()
    )
    duplicates = int(
        manifest.duplicated(["dataset_source", "repo_name", "month"]).sum()
    )
    if duplicates:
        raise ValueError(f"Duplicate manifest source/repo/month rows: {duplicates}")

    manifest["month_period"] = pd.PeriodIndex(manifest["month"], freq="M")
    manifest = manifest.sort_values(
        ["dataset_source", "repo_name", "month_period"]
    ).reset_index(drop=True)
    grouped = manifest.groupby(["dataset_source", "repo_name"], sort=False)
    manifest["previous_month_period"] = grouped["month_period"].shift(1)
    manifest["previous_month_commit"] = grouped["latest_commit"].shift(1)
    current_number = manifest["month_period"].map(month_number)
    previous_number = manifest["previous_month_period"].map(
        lambda value: month_number(value) if pd.notna(value) else pd.NA
    )
    manifest["month_gap"] = current_number - previous_number
    return manifest


def attach_boundaries(panel: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    boundary = manifest[
        [
            "dataset_source",
            "repo_name",
            "month_period",
            "latest_commit",
            "previous_month_period",
            "previous_month_commit",
            "month_gap",
        ]
    ].rename(columns={"latest_commit": "manifest_latest_commit"})
    joined = panel.merge(
        boundary,
        on=["dataset_source", "repo_name", "month_period"],
        how="left",
        validate="one_to_one",
        indicator="_manifest_merge",
    )
    joined["manifest_row_found"] = joined["_manifest_merge"].eq("both")
    joined = joined.drop(columns=["_manifest_merge"])
    joined["current_commit_matches_manifest"] = (
        joined["manifest_row_found"]
        & joined["latest_commit"].eq(joined["manifest_latest_commit"])
    )
    return joined


def select_commits_for_month(
    repo_dir: Path,
    month_end: str,
    previous_commit: str,
    month_gap: int | str,
    panel_commits: int,
) -> tuple[list[str], list[str], str, str]:
    """Return selected commits, raw range commits, method, and status."""
    if panel_commits == 0:
        return [], [], "zero_commit_month", "no_commits"

    range_commits: list[str] = []
    range_usable = (
        bool(previous_commit)
        and month_gap == 1
        and commit_exists(repo_dir, previous_commit)
        and previous_commit != month_end
        and is_ancestor(repo_dir, previous_commit, month_end)
    )
    if range_usable:
        range_commits = list_range_commits(repo_dir, previous_commit, month_end)
        if len(range_commits) == panel_commits:
            return range_commits, range_commits, "monthly_snapshot_range", "ready"

    selected = list_last_n_commits(repo_dir, month_end, panel_commits)
    if len(selected) != panel_commits:
        return selected, range_commits, "panel_count_backfill", "commit_count_shortfall"
    if not selected or selected[-1] != month_end:
        return selected, range_commits, "panel_count_backfill", "backfill_end_mismatch"

    if previous_commit:
        method = "panel_count_backfill_after_range_mismatch"
    else:
        method = "first_observed_month_panel_count_backfill"
    return selected, range_commits, method, "ready"


def prepare(
    joined: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    progress_every: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    roots = {"treatment": treatment_clone_dir, "control": control_clone_dir}
    boundaries: list[dict[str, Any]] = []
    month_end_pairs: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    total = len(joined)
    for number, row in enumerate(joined.itertuples(index=False), start=1):
        source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        month = str(row.time)
        month_end = str(row.latest_commit).strip()
        panel_commits = int(row.commits)
        previous_month = (
            "" if pd.isna(row.previous_month_period) else str(row.previous_month_period)
        )
        previous_commit = (
            "" if pd.isna(row.previous_month_commit) else str(row.previous_month_commit).strip()
        )
        month_gap: int | str = "" if pd.isna(row.month_gap) else int(row.month_gap)
        root = roots[source]
        repo_dir = root / repo_slug(repo_name)
        commit_range = f"{previous_commit}..{month_end}" if previous_commit else ""

        month_end_lookup_status = "ready"
        month_end_parent = ""
        month_end_parent_count = 0
        month_end_is_root = 0
        month_end_is_merge = 0
        try:
            if panel_commits == 0 and not valid_commit_text(month_end):
                month_end_lookup_status = "no_commit_snapshot"
            elif not (repo_dir / ".git").exists():
                month_end_lookup_status = "missing_clone"
            elif not commit_exists(repo_dir, month_end):
                month_end_lookup_status = "missing_month_end_commit"
            else:
                parent_values = get_parents(repo_dir, month_end)
                month_end_parent_count = len(parent_values)
                month_end_parent = parent_values[0] if parent_values else EMPTY_TREE_SHA
                month_end_is_root = int(month_end_parent_count == 0)
                month_end_is_merge = int(month_end_parent_count > 1)
        except Exception as exc:
            month_end_lookup_status = "error"
            errors.append(
                {
                    "dataset_source": source,
                    "repo_name": repo_name,
                    "month": month,
                    "previous_month_commit": previous_commit,
                    "month_end_commit": month_end,
                    "stage": "month_end_parent_lookup",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        month_end_pairs.append(
            {
                "dataset_source": source,
                "repo_name": repo_name,
                "month": month,
                "month_end_commit": month_end,
                "month_end_parent_commit": month_end_parent,
                "parent_count": month_end_parent_count,
                "is_root_commit": month_end_is_root,
                "is_merge_commit": month_end_is_merge,
                "repo_dir": str(repo_dir),
                "lookup_status": month_end_lookup_status,
            }
        )

        status = "ready"
        method = ""
        range_commits: list[str] = []
        selected_commits: list[str] = []
        non_merge_count = 0
        merge_count = 0
        committer_month_match = 0
        committer_month_mismatch = 0
        first_scan = ""
        last_scan = ""

        try:
            if not bool(row.manifest_row_found):
                status = "missing_snapshot_manifest_row"
            elif not bool(row.current_commit_matches_manifest):
                status = "current_commit_manifest_mismatch"
            elif not (repo_dir / ".git").exists():
                status = "missing_clone"
            elif panel_commits == 0:
                status = "no_commits"
                method = "zero_commit_month"
            elif not commit_exists(repo_dir, month_end):
                status = "missing_month_end_commit"
            else:
                selected_commits, range_commits, method, status = select_commits_for_month(
                    repo_dir=repo_dir,
                    month_end=month_end,
                    previous_commit=previous_commit,
                    month_gap=month_gap,
                    panel_commits=panel_commits,
                )
                if status == "ready":
                    first_scan = selected_commits[0]
                    last_scan = selected_commits[-1]
                    for order, scan_current in enumerate(selected_commits, start=1):
                        parent_values = get_parents(repo_dir, scan_current)
                        parent_count = len(parent_values)
                        scan_parent = parent_values[0] if parent_values else EMPTY_TREE_SHA
                        is_root = int(parent_count == 0)
                        is_merge = int(parent_count > 1)
                        commit_dt = get_committer_datetime(repo_dir, scan_current)
                        commit_month = commit_dt[:7] if len(commit_dt) >= 7 else ""
                        month_matches = int(commit_month == month)
                        non_merge_count += int(not is_merge)
                        merge_count += is_merge
                        committer_month_match += month_matches
                        committer_month_mismatch += int(not month_matches)
                        pairs.append(
                            {
                                "dataset_source": source,
                                "repo_name": repo_name,
                                "month": month,
                                "previous_month": previous_month,
                                "previous_month_commit": previous_commit,
                                "month_end_commit": month_end,
                                "commit_range": commit_range,
                                "selection_method": method,
                                "panel_commits": panel_commits,
                                "commit_order": order,
                                "scan_parent_commit": scan_parent,
                                "scan_current_commit": scan_current,
                                "parent_count": parent_count,
                                "is_root_commit": is_root,
                                "is_merge_commit": is_merge,
                                "primary_scan_eligible": int(not is_merge),
                                "is_month_end_commit": int(scan_current == month_end),
                                "committer_datetime": commit_dt,
                                "committer_month": commit_month,
                                "committer_month_matches_panel_month": month_matches,
                                "repo_dir": str(repo_dir),
                            }
                        )
        except Exception as exc:
            status = "error"
            errors.append(
                {
                    "dataset_source": source,
                    "repo_name": repo_name,
                    "month": month,
                    "previous_month_commit": previous_commit,
                    "month_end_commit": month_end,
                    "stage": "commit_selection",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        boundaries.append(
            {
                "dataset_source": source,
                "repo_name": repo_name,
                "month": month,
                "previous_month": previous_month,
                "previous_month_commit": previous_commit,
                "month_end_commit": month_end,
                "month_gap": month_gap,
                "comparison_status": status,
                "selection_method": method,
                "repo_dir": str(repo_dir),
                "commit_range": commit_range,
                "panel_commits": panel_commits,
                "range_commits_found": len(range_commits),
                "selected_commits": len(selected_commits),
                "selected_count_matches_panel": int(
                    len(selected_commits) == panel_commits
                ),
                "non_merge_commits_selected": non_merge_count,
                "merge_commits_selected": merge_count,
                "first_scan_commit": first_scan,
                "last_scan_commit": last_scan,
                "last_scan_commit_matches_month_end": int(
                    bool(last_scan) and last_scan == month_end
                ),
                "commits_with_committer_month_match": committer_month_match,
                "commits_with_committer_month_mismatch": committer_month_mismatch,
            }
        )

        if progress_every > 0 and (number % progress_every == 0 or number == total):
            print(
                f"Commit-pair preparation: {number}/{total} repository-month rows; "
                f"scan pairs={len(pairs)}",
                flush=True,
            )

    return (
        pd.DataFrame(boundaries, columns=BOUNDARY_COLUMNS),
        pd.DataFrame(month_end_pairs, columns=MONTH_END_PAIR_COLUMNS),
        pd.DataFrame(pairs, columns=PAIR_COLUMNS),
        pd.DataFrame(errors, columns=ERROR_COLUMNS),
    )


def build_checks(
    panel: pd.DataFrame,
    joined: pd.DataFrame,
    boundaries: pd.DataFrame,
    month_end_pairs: pd.DataFrame,
    pairs: pd.DataFrame,
    errors: pd.DataFrame,
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(section: str, check: str, passed: bool, value: Any) -> None:
        checks.append(
            {
                "section": section,
                "check": check,
                "passed": int(bool(passed)),
                "value": value,
            }
        )

    add("input", "panel_rows_preserved", len(boundaries) == len(panel), len(boundaries))
    add(
        "manifest",
        "all_panel_rows_in_manifest",
        int((~joined["manifest_row_found"]).sum()) == 0,
        int((~joined["manifest_row_found"]).sum()),
    )
    add(
        "manifest",
        "panel_current_commits_match_manifest",
        int((~joined["current_commit_matches_manifest"]).sum()) == 0,
        int((~joined["current_commit_matches_manifest"]).sum()),
    )
    add("processing", "errors_zero", len(errors) == 0, len(errors))
    add(
        "month_end",
        "one_parent_record_per_panel_row",
        len(month_end_pairs) == len(panel),
        len(month_end_pairs),
    )

    positive_months = boundaries["panel_commits"].gt(0)
    invalid_positive_status = int(
        (positive_months & boundaries["comparison_status"].ne("ready")).sum()
    )
    add(
        "selection",
        "all_positive_commit_months_ready",
        invalid_positive_status == 0,
        invalid_positive_status,
    )
    count_mismatches = int(
        (
            positive_months
            & boundaries["selected_count_matches_panel"].ne(1)
        ).sum()
    )
    add(
        "selection",
        "selected_commit_counts_match_panel",
        count_mismatches == 0,
        count_mismatches,
    )
    end_mismatches = int(
        (
            positive_months
            & boundaries["last_scan_commit_matches_month_end"].ne(1)
        ).sum()
    )
    add(
        "selection",
        "positive_months_end_at_month_snapshot",
        end_mismatches == 0,
        end_mismatches,
    )

    duplicate_pair_keys = int(
        pairs.duplicated(
            ["dataset_source", "repo_name", "month", "scan_current_commit"]
        ).sum()
    )
    add("pairs", "repo_month_commit_keys_unique", duplicate_pair_keys == 0, duplicate_pair_keys)
    cross_month_duplicates = int(
        pairs.duplicated(
            ["dataset_source", "repo_name", "scan_current_commit"], keep=False
        ).sum()
    )
    add(
        "pairs",
        "scan_commits_do_not_overlap_repo_months",
        cross_month_duplicates == 0,
        cross_month_duplicates,
    )
    blank_scan_parent = int(
        pairs["scan_parent_commit"].astype(str).str.len().eq(0).sum()
    )
    add("pairs", "scan_parent_present", blank_scan_parent == 0, blank_scan_parent)
    eligibility_errors = int(
        (pairs["primary_scan_eligible"] != 1 - pairs["is_merge_commit"]).sum()
    )
    add(
        "pairs",
        "primary_eligibility_matches_merge_rule",
        eligibility_errors == 0,
        eligibility_errors,
    )
    selected_total = int(boundaries["selected_commits"].sum())
    add(
        "pairs",
        "boundary_selected_count_matches_pair_table",
        selected_total == len(pairs),
        f"{selected_total}:{len(pairs)}",
    )

    first_month_positive = boundaries[
        boundaries["previous_month_commit"].astype(str).str.len().eq(0)
        & boundaries["panel_commits"].gt(0)
    ]
    first_month_not_ready = int(
        first_month_positive["comparison_status"].ne("ready").sum()
    )
    add(
        "first_month",
        "first_observed_positive_months_recovered",
        first_month_not_ready == 0,
        first_month_not_ready,
    )
    return pd.DataFrame(checks)


def build_summary(
    panel: pd.DataFrame,
    boundaries: pd.DataFrame,
    month_end_pairs: pd.DataFrame,
    pairs: pd.DataFrame,
    errors: pd.DataFrame,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    status_counts = {
        str(key): int(value)
        for key, value in boundaries["comparison_status"].value_counts(dropna=False).items()
    }
    method_counts = {
        str(key): int(value)
        for key, value in boundaries["selection_method"].value_counts(dropna=False).items()
    }
    return {
        "status": "PASS" if checks["passed"].eq(1).all() else "FAIL",
        "checks_total": int(len(checks)),
        "checks_passed": int(checks["passed"].eq(1).sum()),
        "checks_failed": int(checks["passed"].ne(1).sum()),
        "panel_rows": int(len(panel)),
        "repositories": int(panel["repo_name"].nunique()),
        "positive_commit_repo_months": int(panel["commits"].gt(0).sum()),
        "zero_commit_repo_months": int(panel["commits"].eq(0).sum()),
        "month_end_parent_records": int(len(month_end_pairs)),
        "commit_parent_pairs": int(len(pairs)),
        "primary_non_merge_scan_pairs": int(pairs["primary_scan_eligible"].eq(1).sum()),
        "merge_scan_pairs": int(pairs["is_merge_commit"].eq(1).sum()),
        "first_observed_months_recovered": int(
            (
                boundaries["previous_month_commit"].astype(str).str.len().eq(0)
                & boundaries["panel_commits"].gt(0)
                & boundaries["comparison_status"].eq("ready")
            ).sum()
        ),
        "committer_month_mismatch_pairs": int(
            pairs["committer_month_matches_panel_month"].eq(0).sum()
        ),
        "errors": int(len(errors)),
        "comparison_status_counts": status_counts,
        "selection_method_counts": method_counts,
        "scan_pair_definition": (
            "Each selected commit X is compared with its direct first parent X-1. "
            "Repeated function changes and later reverts remain separate events."
        ),
        "primary_event_definition": (
            "One structurally added or modified named Python function in one "
            "non-merge commit."
        ),
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-commit-scan-") as temp_dir:
        repo = Path(temp_dir) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test User"],
            check=True,
        )
        commits: list[str] = []
        for index in range(1, 5):
            (repo / "sample.py").write_text(
                f"def f():\n    return {index}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-q", "-m", f"c{index}"],
                check=True,
            )
            commits.append(
                require_git_ok(run_git(repo, ["rev-parse", "HEAD"]), "rev-parse")
            )

        selected, range_rows, method, status = select_commits_for_month(
            repo_dir=repo,
            month_end=commits[-1],
            previous_commit="",
            month_gap="",
            panel_commits=3,
        )
        if selected != commits[-3:]:
            raise AssertionError(f"First-month recovery mismatch: {selected}")
        if range_rows:
            raise AssertionError("First-month recovery should not use a snapshot range")
        if method != "first_observed_month_panel_count_backfill" or status != "ready":
            raise AssertionError("Unexpected first-month recovery metadata")
        for current, expected_parent in zip(selected, commits[-4:-1]):
            parents = get_parents(repo, current)
            if parents != [expected_parent]:
                raise AssertionError("Direct first-parent mismatch")
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    input_panel = args.input_panel.expanduser().resolve()
    snapshot_manifest = args.snapshot_manifest.expanduser().resolve()
    treatment_clone_dir = args.treatment_clone_dir.expanduser().resolve()
    control_clone_dir = args.control_clone_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    qc_dir = args.qc_dir.expanduser().resolve()

    for path, label in [
        (input_panel, "input panel"),
        (snapshot_manifest, "snapshot manifest"),
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")
    for path, label in [
        (treatment_clone_dir, "treatment clone directory"),
        (control_clone_dir, "control clone directory"),
    ]:
        if not path.is_dir():
            raise FileNotFoundError(f"Missing {label}: {path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("Prepare repository-month direct first-parent scan pairs")
    print(f"Input panel:          {input_panel}")
    print(f"Snapshot manifest:    {snapshot_manifest}")
    print(f"Treatment clones:     {treatment_clone_dir}")
    print(f"Control clones:       {control_clone_dir}")
    print(f"Output directory:     {output_dir}")
    print(f"QC directory:         {qc_dir}")
    print("=" * 72)

    panel = load_panel(input_panel)
    manifest = load_manifest(snapshot_manifest)
    joined = attach_boundaries(panel, manifest)
    boundaries, month_end_pairs, pairs, errors = prepare(
        joined,
        treatment_clone_dir,
        control_clone_dir,
        args.progress_every,
    )
    checks = build_checks(panel, joined, boundaries, month_end_pairs, pairs, errors)
    summary = build_summary(
        panel,
        boundaries,
        month_end_pairs,
        pairs,
        errors,
        checks,
    )

    boundary_path = output_dir / "repo_month_commit_scan_boundaries.csv"
    month_end_path = output_dir / "month_end_parent_pairs.csv"
    pair_path = output_dir / "commit_parent_pairs.csv"
    checks_path = qc_dir / "agc_commit_function_scan_prepare_checks.csv"
    errors_path = qc_dir / "agc_commit_function_scan_prepare_errors.csv"
    summary_path = qc_dir / "agc_commit_function_scan_prepare_summary.json"

    atomic_csv(boundaries, boundary_path)
    atomic_csv(month_end_pairs, month_end_path)
    atomic_csv(pairs, pair_path)
    atomic_csv(checks, checks_path)
    atomic_csv(errors, errors_path)
    atomic_json(summary, summary_path)

    print("=" * 72)
    print("AGC commit-function scan preparation")
    print(f"Status:                     {summary['status']}")
    print(f"Checks passed:              {summary['checks_passed']}/{summary['checks_total']}")
    print(f"Panel rows:                 {summary['panel_rows']}")
    print(f"Repositories:               {summary['repositories']}")
    print(f"Positive-commit months:     {summary['positive_commit_repo_months']}")
    print(f"First months recovered:     {summary['first_observed_months_recovered']}")
    print(f"Commit-parent pairs:        {summary['commit_parent_pairs']}")
    print(f"Primary non-merge pairs:    {summary['primary_non_merge_scan_pairs']}")
    print(f"Merge pairs flagged:        {summary['merge_scan_pairs']}")
    print(f"Errors:                     {summary['errors']}")
    print(f"Boundary manifest:          {boundary_path}")
    print(f"Month-end parent records:   {month_end_path}")
    print(f"Commit-parent pairs:        {pair_path}")
    print(f"Summary:                    {summary_path}")
    print("=" * 72)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
