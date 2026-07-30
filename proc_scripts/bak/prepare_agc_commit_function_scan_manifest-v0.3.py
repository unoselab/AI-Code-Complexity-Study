#!/usr/bin/env python3
"""Prepare repository-month commit/first-parent pairs for function-event analysis.

This revision reproduces the monthly commit assignment used by the original
repository analyzer: commits are assigned to months with their committer
timestamp (``committed_at``), not by taking the last N commits from a monthly
snapshot.

For each repository, the script evaluates multiple recoverable Git-history
candidates instead of assuming that the current/default branch still matches
the clone state used to create the panel. Candidates include current branch
refs, local and remote branch tips, retained reflog tips, the union of panel
snapshot anchors, and all currently advertised refs. Each candidate enumerates
every reachable commit exactly once, groups commits by committer month, and is
validated against both the panel commit count and panel latest commit.

Each selected commit X is paired with its direct first parent X-1. Repeated
changes to the same function and later reverts therefore remain separate
commit-function change events in the next extraction stage.

Primary merge rule
------------------
Merge commits remain in the audit tables because the original monthly commit
count includes them. They are marked ``primary_scan_eligible = 0`` so the
primary function-event extraction uses non-merge commits only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
FIELD_SEPARATOR = "\x1f"

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
    "history_ref",
    "history_tip_commit",
    "history_commits_scanned",
    "commit_range",
    "panel_commits",
    "range_commits_found",
    "history_month_commits_found",
    "selected_commits",
    "selected_count_matches_panel",
    "non_merge_commits_selected",
    "merge_commits_selected",
    "first_scan_commit",
    "last_scan_commit",
    "reproduced_latest_commit",
    "last_scan_commit_matches_month_end",
    "selected_latest_matches_panel",
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
    "history_ref",
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
    "history_ref",
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

HISTORY_REF_COLUMNS = [
    "dataset_source",
    "repo_name",
    "repo_dir",
    "candidate_ref",
    "candidate_priority",
    "candidate_tip_commit",
    "candidate_kind",
    "candidate_revision_count",
    "candidate_contains_all_panel_anchors",
    "history_commits",
    "panel_months",
    "count_matches",
    "latest_matches",
    "count_and_latest_matches",
    "selected",
    "selection_status",
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


@dataclass(frozen=True)
class CommitRecord:
    commit: str
    committer_datetime: str
    committer_month: str
    committer_epoch: float
    parents: tuple[str, ...]
    history_order: int

    @property
    def parent_count(self) -> int:
        return len(self.parents)

    @property
    def first_parent(self) -> str:
        return self.parents[0] if self.parents else EMPTY_TREE_SHA

    @property
    def is_root(self) -> int:
        return int(not self.parents)

    @property
    def is_merge(self) -> int:
        return int(len(self.parents) > 1)


@dataclass(frozen=True)
class HistorySpec:
    label: str
    kind: str
    priority: int
    revisions: tuple[str, ...]
    use_all_refs: bool = False


@dataclass(frozen=True)
class HistoryCandidate:
    ref: str
    kind: str
    priority: int
    tip_commit: str
    revision_count: int
    contains_all_panel_anchors: int
    records: tuple[CommitRecord, ...]
    by_commit: dict[str, CommitRecord]
    by_month: dict[str, tuple[CommitRecord, ...]]
    reproduced_latest: dict[str, str]
    count_matches: int
    latest_matches: int
    count_and_latest_matches: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare direct first-parent pairs for commit-function events "
            "using the original committer-month assignment."
        )
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
    return bool(FULL_SHA_RE.fullmatch(str(value).strip()))


def commit_exists(repo_dir: Path, commit: str) -> bool:
    if not valid_commit_text(commit):
        return False
    return run_git(repo_dir, ["cat-file", "-e", f"{commit}^{{commit}}"]).returncode == 0


def resolve_ref_commit(repo_dir: Path, ref: str) -> str:
    result = run_git(repo_dir, ["rev-parse", "--verify", f"{ref}^{{commit}}"])
    if result.returncode != 0:
        return ""
    commit = result.stdout.strip()
    return commit if valid_commit_text(commit) else ""


def symbolic_ref(repo_dir: Path, ref: str) -> str:
    result = run_git(repo_dir, ["symbolic-ref", "--quiet", ref])
    return result.stdout.strip() if result.returncode == 0 else ""


def list_named_refs(repo_dir: Path) -> list[str]:
    result = run_git(
        repo_dir,
        [
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads",
            "refs/remotes",
        ],
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_reflog_tips(repo_dir: Path, max_tips: int = 200) -> list[str]:
    result = run_git(
        repo_dir,
        [
            "reflog",
            "--all",
            "--format=%H",
        ],
    )
    if result.returncode != 0:
        return []
    tips: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        commit = line.strip()
        if valid_commit_text(commit) and commit not in seen:
            tips.append(commit)
            seen.add(commit)
        if len(tips) >= max_tips:
            break
    return tips


def commit_contains_all_anchors(
    repo_dir: Path,
    tip_commit: str,
    panel_anchors: Sequence[str],
) -> bool:
    for anchor in panel_anchors:
        result = run_git(
            repo_dir,
            ["merge-base", "--is-ancestor", anchor, tip_commit],
        )
        if result.returncode != 0:
            return False
    return True


def candidate_history_specs(
    repo_dir: Path,
    repo_panel: pd.DataFrame,
) -> list[HistorySpec]:
    panel_anchors = tuple(
        dict.fromkeys(
            str(value).strip()
            for value in repo_panel["latest_commit"].tolist()
            if valid_commit_text(value)
        )
    )
    specs: list[HistorySpec] = []
    seen_identity: set[tuple[bool, tuple[str, ...]]] = set()
    priority = 1

    def add_spec(
        label: str,
        kind: str,
        revisions: Sequence[str],
        use_all_refs: bool = False,
    ) -> None:
        nonlocal priority
        normalized = tuple(str(value).strip() for value in revisions if str(value).strip())
        identity = (use_all_refs, normalized)
        if (not use_all_refs and not normalized) or identity in seen_identity:
            return
        specs.append(
            HistorySpec(
                label=label,
                kind=kind,
                priority=priority,
                revisions=normalized,
                use_all_refs=use_all_refs,
            )
        )
        seen_identity.add(identity)
        priority += 1

    # The panel anchors are immutable commit hashes from the validated panel.
    # Their union is robust to current-branch drift and force-pushed refs.
    add_spec(
        "panel_anchor_union",
        "panel_anchor_union",
        panel_anchors,
    )

    origin_head = symbolic_ref(repo_dir, "refs/remotes/origin/HEAD")
    local_head = symbolic_ref(repo_dir, "HEAD")
    ordered_refs = [
        origin_head,
        local_head,
        "refs/remotes/origin/main",
        "refs/remotes/origin/master",
        "refs/heads/main",
        "refs/heads/master",
        "HEAD",
        *list_named_refs(repo_dir),
    ]

    seen_tips: set[str] = set()
    for ref in ordered_refs:
        ref_text = str(ref).strip()
        tip = resolve_ref_commit(repo_dir, ref_text) if ref_text else ""
        if not tip or tip in seen_tips:
            continue
        if panel_anchors and not commit_contains_all_anchors(
            repo_dir,
            tip,
            panel_anchors,
        ):
            continue
        add_spec(ref_text, "named_ref", [tip])
        seen_tips.add(tip)

    # Reflog candidates can recover the exact branch tip used by the earlier
    # panel analysis even when the current branch has since advanced.
    for tip in list_reflog_tips(repo_dir):
        if tip in seen_tips:
            continue
        if panel_anchors and not commit_contains_all_anchors(
            repo_dir,
            tip,
            panel_anchors,
        ):
            continue
        add_spec(f"reflog:{tip}", "reflog_tip", [tip])
        seen_tips.add(tip)

    # Keep --all as a final diagnostic candidate. Candidate scoring prevents it
    # from being selected unless it reproduces the panel better than other
    # recoverable histories.
    add_spec("all_refs_union", "all_refs_union", [], use_all_refs=True)
    return specs


def parse_iso_epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_history(
    repo_dir: Path,
    revisions: Sequence[str],
    use_all_refs: bool = False,
    label: str = "history",
) -> tuple[CommitRecord, ...]:
    command = ["log"]
    if use_all_refs:
        command.append("--all")
    else:
        command.extend(revisions)
    command.append("--format=%H%x1f%cI%x1f%P")

    output = require_git_ok(
        run_git(repo_dir, command),
        f"git log failed for {label}",
    )

    records: list[CommitRecord] = []
    seen_commits: set[str] = set()
    for history_order, raw_line in enumerate(output.splitlines(), start=1):
        fields = raw_line.split(FIELD_SEPARATOR)
        if len(fields) == 2:
            fields.append("")
        if len(fields) != 3:
            raise RuntimeError(
                f"Unexpected git log record for {label}: {raw_line!r}"
            )
        commit, committer_datetime, parent_text = fields
        commit = commit.strip()
        committer_datetime = committer_datetime.strip()
        parents = tuple(value for value in parent_text.strip().split() if value)
        if not valid_commit_text(commit):
            raise RuntimeError(f"Invalid commit in git log for {label}: {commit!r}")
        if commit in seen_commits:
            continue
        seen_commits.add(commit)
        records.append(
            CommitRecord(
                commit=commit,
                committer_datetime=committer_datetime,
                committer_month=committer_datetime[:7],
                committer_epoch=parse_iso_epoch(committer_datetime),
                parents=parents,
                history_order=history_order,
            )
        )
    return tuple(records)


def group_history(
    records: Sequence[CommitRecord],
) -> tuple[
    dict[str, CommitRecord],
    dict[str, tuple[CommitRecord, ...]],
    dict[str, str],
]:
    by_commit = {record.commit: record for record in records}
    grouped: dict[str, list[CommitRecord]] = {}
    latest_record: dict[str, CommitRecord] = {}

    # Match the original strict greater-than update for timestamp ties.
    for record in records:
        grouped.setdefault(record.committer_month, []).append(record)
        current = latest_record.get(record.committer_month)
        if current is None or record.committer_epoch > current.committer_epoch:
            latest_record[record.committer_month] = record

    by_month: dict[str, tuple[CommitRecord, ...]] = {}
    for month, month_records in grouped.items():
        ordered = sorted(
            month_records,
            key=lambda record: (
                record.committer_epoch,
                -record.history_order,
                record.commit,
            ),
        )
        by_month[month] = tuple(ordered)

    reproduced_latest = {
        month: record.commit for month, record in latest_record.items()
    }
    return by_commit, by_month, reproduced_latest


def evaluate_history_candidate(
    repo_dir: Path,
    spec: HistorySpec,
    repo_panel: pd.DataFrame,
) -> HistoryCandidate:
    records = load_history(
        repo_dir,
        revisions=spec.revisions,
        use_all_refs=spec.use_all_refs,
        label=spec.label,
    )
    by_commit, by_month, reproduced_latest = group_history(records)

    count_matches = 0
    latest_matches = 0
    count_and_latest_matches = 0
    panel_anchors = [
        str(value).strip()
        for value in repo_panel["latest_commit"].tolist()
        if valid_commit_text(value)
    ]
    for row in repo_panel.itertuples(index=False):
        month = str(row.time)
        expected_count = int(row.commits)
        expected_latest = str(row.latest_commit).strip()
        selected = by_month.get(month, ())
        count_match = len(selected) == expected_count
        latest_match = reproduced_latest.get(month, "") == expected_latest
        count_matches += int(count_match)
        latest_matches += int(latest_match)
        count_and_latest_matches += int(count_match and latest_match)

    tip_commit = spec.revisions[0] if len(spec.revisions) == 1 else ""
    contains_all = int(all(anchor in by_commit for anchor in panel_anchors))
    return HistoryCandidate(
        ref=spec.label,
        kind=spec.kind,
        priority=spec.priority,
        tip_commit=tip_commit,
        revision_count=len(spec.revisions),
        contains_all_panel_anchors=contains_all,
        records=records,
        by_commit=by_commit,
        by_month=by_month,
        reproduced_latest=reproduced_latest,
        count_matches=count_matches,
        latest_matches=latest_matches,
        count_and_latest_matches=count_and_latest_matches,
    )


def choose_history_candidate(
    repo_dir: Path,
    repo_panel: pd.DataFrame,
) -> tuple[HistoryCandidate | None, list[dict[str, Any]], str]:
    specs = candidate_history_specs(repo_dir, repo_panel)
    if not specs:
        return None, [], "no_history_candidate"

    candidates: list[HistoryCandidate] = []
    audit_rows: list[dict[str, Any]] = []
    for spec in specs:
        candidate = evaluate_history_candidate(
            repo_dir=repo_dir,
            spec=spec,
            repo_panel=repo_panel,
        )
        candidates.append(candidate)

    selected = max(
        candidates,
        key=lambda item: (
            item.count_and_latest_matches,
            item.count_matches,
            item.latest_matches,
            item.contains_all_panel_anchors,
            -item.priority,
        ),
    )
    perfect = selected.count_and_latest_matches == len(repo_panel)
    selection_status = "perfect_panel_match" if perfect else "best_available_history"

    source = str(repo_panel.iloc[0]["dataset_source"])
    repo_name = str(repo_panel.iloc[0]["repo_name"])
    for candidate in candidates:
        audit_rows.append(
            {
                "dataset_source": source,
                "repo_name": repo_name,
                "repo_dir": str(repo_dir),
                "candidate_ref": candidate.ref,
                "candidate_priority": candidate.priority,
                "candidate_tip_commit": candidate.tip_commit,
                "candidate_kind": candidate.kind,
                "candidate_revision_count": candidate.revision_count,
                "candidate_contains_all_panel_anchors": (
                    candidate.contains_all_panel_anchors
                ),
                "history_commits": len(candidate.records),
                "panel_months": len(repo_panel),
                "count_matches": candidate.count_matches,
                "latest_matches": candidate.latest_matches,
                "count_and_latest_matches": candidate.count_and_latest_matches,
                "selected": int(candidate.ref == selected.ref),
                "selection_status": selection_status,
            }
        )

    return selected, audit_rows, selection_status

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

    invalid_sources = sorted(set(panel["dataset_source"]) - {"treatment", "control"})
    if invalid_sources:
        raise ValueError(f"Unsupported dataset sources: {invalid_sources}")

    duplicates = int(panel.duplicated(["dataset_source", "repo_name", "time"]).sum())
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


def prepare(
    joined: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    progress_every: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    roots = {"treatment": treatment_clone_dir, "control": control_clone_dir}
    boundaries: list[dict[str, Any]] = []
    month_end_pairs: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    history_ref_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    grouped = list(joined.groupby(["dataset_source", "repo_name"], sort=False))
    total_rows = len(joined)
    processed_rows = 0

    for (source_value, repo_name_value), repo_panel in grouped:
        source = str(source_value)
        repo_name = str(repo_name_value)
        repo_panel = repo_panel.sort_values("month_period").reset_index(drop=True)
        repo_dir = roots[source] / repo_slug(repo_name)

        history: HistoryCandidate | None = None
        history_selection_status = ""
        try:
            if not (repo_dir / ".git").exists():
                history_selection_status = "missing_clone"
            else:
                history, ref_audit, history_selection_status = choose_history_candidate(
                    repo_dir=repo_dir,
                    repo_panel=repo_panel,
                )
                history_ref_rows.extend(ref_audit)
        except Exception as exc:
            history_selection_status = "history_error"
            errors.append(
                {
                    "dataset_source": source,
                    "repo_name": repo_name,
                    "month": "",
                    "previous_month_commit": "",
                    "month_end_commit": "",
                    "stage": "history_ref_selection",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        for row in repo_panel.itertuples(index=False):
            processed_rows += 1
            month = str(row.time)
            month_end = str(row.latest_commit).strip()
            panel_commits = int(row.commits)
            previous_month = (
                ""
                if pd.isna(row.previous_month_period)
                else str(row.previous_month_period)
            )
            previous_commit = (
                ""
                if pd.isna(row.previous_month_commit)
                else str(row.previous_month_commit).strip()
            )
            month_gap: int | str = "" if pd.isna(row.month_gap) else int(row.month_gap)

            status = "ready"
            method = "committer_month_from_history_ref"
            selected_records: tuple[CommitRecord, ...] = ()
            reproduced_latest = ""
            history_ref = history.ref if history is not None else ""
            history_tip = history.tip_commit if history is not None else ""
            history_count = len(history.records) if history is not None else 0

            if not bool(row.manifest_row_found):
                status = "missing_snapshot_manifest_row"
            elif not bool(row.current_commit_matches_manifest):
                status = "current_commit_manifest_mismatch"
            elif history_selection_status == "missing_clone":
                status = "missing_clone"
            elif history is None:
                status = history_selection_status or "missing_history"
            else:
                selected_records = history.by_month.get(month, ())
                reproduced_latest = history.reproduced_latest.get(month, "")
                if len(selected_records) != panel_commits:
                    status = "committer_month_count_mismatch"
                elif reproduced_latest != month_end:
                    status = "committer_month_latest_mismatch"
                elif month_end not in history.by_commit:
                    status = "month_end_not_in_history_ref"

            non_merge_count = sum(1 - record.is_merge for record in selected_records)
            merge_count = sum(record.is_merge for record in selected_records)
            first_scan = selected_records[0].commit if selected_records else ""
            last_scan = selected_records[-1].commit if selected_records else ""
            month_match_count = sum(
                int(record.committer_month == month) for record in selected_records
            )
            month_mismatch_count = len(selected_records) - month_match_count

            # Keep pair rows for reconstructed months even when the count/latest
            # validation fails. They remain diagnostic and let the boundary/pair
            # arithmetic stay transparent. Stage 2 is blocked unless every QC
            # check passes.
            for order, record in enumerate(selected_records, start=1):
                pairs.append(
                    {
                        "dataset_source": source,
                        "repo_name": repo_name,
                        "month": month,
                        "previous_month": previous_month,
                        "previous_month_commit": previous_commit,
                        "month_end_commit": month_end,
                        "commit_range": f"committer-month:{month}@{history_ref}",
                        "selection_method": method,
                        "history_ref": history_ref,
                        "panel_commits": panel_commits,
                        "commit_order": order,
                        "scan_parent_commit": record.first_parent,
                        "scan_current_commit": record.commit,
                        "parent_count": record.parent_count,
                        "is_root_commit": record.is_root,
                        "is_merge_commit": record.is_merge,
                        "primary_scan_eligible": int(not record.is_merge),
                        "is_month_end_commit": int(record.commit == month_end),
                        "committer_datetime": record.committer_datetime,
                        "committer_month": record.committer_month,
                        "committer_month_matches_panel_month": int(
                            record.committer_month == month
                        ),
                        "repo_dir": str(repo_dir),
                    }
                )

            month_end_record = history.by_commit.get(month_end) if history else None
            if month_end_record is None:
                lookup_status = (
                    "missing_history" if history is None else "month_end_not_in_history_ref"
                )
                month_end_parent = ""
                month_end_parent_count = 0
                month_end_is_root = 0
                month_end_is_merge = 0
            else:
                lookup_status = "ready"
                month_end_parent = month_end_record.first_parent
                month_end_parent_count = month_end_record.parent_count
                month_end_is_root = month_end_record.is_root
                month_end_is_merge = month_end_record.is_merge

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
                    "history_ref": history_ref,
                    "repo_dir": str(repo_dir),
                    "lookup_status": lookup_status,
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
                    "history_ref": history_ref,
                    "history_tip_commit": history_tip,
                    "history_commits_scanned": history_count,
                    "commit_range": f"committer-month:{month}@{history_ref}",
                    "panel_commits": panel_commits,
                    "range_commits_found": 0,
                    "history_month_commits_found": len(selected_records),
                    "selected_commits": len(selected_records),
                    "selected_count_matches_panel": int(
                        len(selected_records) == panel_commits
                    ),
                    "non_merge_commits_selected": non_merge_count,
                    "merge_commits_selected": merge_count,
                    "first_scan_commit": first_scan,
                    "last_scan_commit": last_scan,
                    "reproduced_latest_commit": reproduced_latest,
                    "last_scan_commit_matches_month_end": int(last_scan == month_end),
                    "selected_latest_matches_panel": int(
                        reproduced_latest == month_end
                    ),
                    "commits_with_committer_month_match": month_match_count,
                    "commits_with_committer_month_mismatch": month_mismatch_count,
                }
            )

            if progress_every > 0 and (
                processed_rows % progress_every == 0 or processed_rows == total_rows
            ):
                print(
                    f"Commit-pair preparation: {processed_rows}/{total_rows} "
                    f"repository-month rows; scan pairs={len(pairs)}",
                    flush=True,
                )

    return (
        pd.DataFrame(boundaries, columns=BOUNDARY_COLUMNS),
        pd.DataFrame(month_end_pairs, columns=MONTH_END_PAIR_COLUMNS),
        pd.DataFrame(pairs, columns=PAIR_COLUMNS),
        pd.DataFrame(history_ref_rows, columns=HISTORY_REF_COLUMNS),
        pd.DataFrame(errors, columns=ERROR_COLUMNS),
    )


def build_checks(
    panel: pd.DataFrame,
    joined: pd.DataFrame,
    boundaries: pd.DataFrame,
    month_end_pairs: pd.DataFrame,
    pairs: pd.DataFrame,
    history_refs: pd.DataFrame,
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
        "history",
        "one_selected_history_ref_per_repository",
        int(history_refs["selected"].eq(1).sum())
        == len(panel[["dataset_source", "repo_name"]].drop_duplicates()),
        int(history_refs["selected"].eq(1).sum()),
    )
    selected_ref_failures = 0
    if not history_refs.empty:
        selected_ref_failures = int(
            history_refs.loc[history_refs["selected"].eq(1), "selection_status"]
            .ne("perfect_panel_match")
            .sum()
        )
    add(
        "history",
        "selected_history_refs_reproduce_all_panel_months",
        selected_ref_failures == 0,
        selected_ref_failures,
    )
    add(
        "month_end",
        "one_parent_record_per_panel_row",
        len(month_end_pairs) == len(panel),
        len(month_end_pairs),
    )
    month_end_lookup_failures = int(month_end_pairs["lookup_status"].ne("ready").sum())
    add(
        "month_end",
        "all_month_end_commits_in_selected_history",
        month_end_lookup_failures == 0,
        month_end_lookup_failures,
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
        (positive_months & boundaries["selected_count_matches_panel"].ne(1)).sum()
    )
    add(
        "selection",
        "selected_commit_counts_match_panel",
        count_mismatches == 0,
        count_mismatches,
    )
    latest_mismatches = int(
        (positive_months & boundaries["selected_latest_matches_panel"].ne(1)).sum()
    )
    add(
        "selection",
        "committer_month_latest_commits_match_panel",
        latest_mismatches == 0,
        latest_mismatches,
    )
    committer_month_mismatches = int(
        pairs["committer_month_matches_panel_month"].ne(1).sum()
    )
    add(
        "selection",
        "all_selected_commits_match_panel_committer_month",
        committer_month_mismatches == 0,
        committer_month_mismatches,
    )

    duplicate_pair_keys = int(
        pairs.duplicated(
            ["dataset_source", "repo_name", "month", "scan_current_commit"]
        ).sum()
    )
    add(
        "pairs",
        "repo_month_commit_keys_unique",
        duplicate_pair_keys == 0,
        duplicate_pair_keys,
    )
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
    history_refs: pd.DataFrame,
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
    selected_refs = history_refs[history_refs["selected"].eq(1)] if not history_refs.empty else history_refs
    ref_status_counts = {
        str(key): int(value)
        for key, value in selected_refs["selection_status"].value_counts(dropna=False).items()
    } if not selected_refs.empty else {}

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
        "cross_month_overlap_pair_rows": int(
            pairs.duplicated(
                ["dataset_source", "repo_name", "scan_current_commit"], keep=False
            ).sum()
        ),
        "selected_history_ref_status_counts": ref_status_counts,
        "errors": int(len(errors)),
        "comparison_status_counts": status_counts,
        "selection_method_counts": method_counts,
        "month_assignment": "committer timestamp month, matching committed_at",
        "scan_pair_definition": (
            "Each selected commit X is compared with its direct first parent X-1. "
            "Repeated function changes and later reverts remain separate events."
        ),
        "primary_event_definition": (
            "One structurally added or modified named Python function in one "
            "non-merge commit."
        ),
    }


def commit_file(
    repo: Path,
    message: str,
    content: str,
    committed_at: str,
) -> str:
    (repo / "sample.py").write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = committed_at
    env["GIT_COMMITTER_DATE"] = committed_at
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        env=env,
    )
    return require_git_ok(run_git(repo, ["rev-parse", "HEAD"]), "rev-parse")


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="agc-commit-scan-v4-") as temp_dir:
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

        january: list[str] = []
        february: list[str] = []
        january.append(
            commit_file(repo, "jan-1", "def f():\n    return 1\n", "2025-01-05T12:00:00+00:00")
        )
        january.append(
            commit_file(repo, "jan-2", "def f():\n    return 2\n", "2025-01-10T12:00:00+00:00")
        )
        january.append(
            commit_file(repo, "jan-3", "def f():\n    return 3\n", "2025-01-20T12:00:00+00:00")
        )
        february.append(
            commit_file(repo, "feb-1", "def f():\n    return 4\n", "2025-02-03T12:00:00+00:00")
        )
        february.append(
            commit_file(repo, "feb-2", "def f():\n    return 5\n", "2025-02-25T12:00:00+00:00")
        )

        records = load_history(repo, ["HEAD"], label="HEAD")
        _, by_month, reproduced_latest = group_history(records)
        if [record.commit for record in by_month["2025-01"]] != january:
            raise AssertionError("January committer-month reconstruction failed")
        if [record.commit for record in by_month["2025-02"]] != february:
            raise AssertionError("February committer-month reconstruction failed")
        if reproduced_latest["2025-01"] != january[-1]:
            raise AssertionError("January latest commit reconstruction failed")
        if reproduced_latest["2025-02"] != february[-1]:
            raise AssertionError("February latest commit reconstruction failed")

        selected = january + february
        if len(selected) != len(set(selected)):
            raise AssertionError("Commit assigned to more than one month")
        for record in by_month["2025-01"] + by_month["2025-02"]:
            if not record.first_parent:
                raise AssertionError("Direct first parent missing")

        panel = pd.DataFrame(
            [
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "time": "2025-01",
                    "latest_commit": january[-1],
                    "commits": len(january),
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "owner/repo",
                    "time": "2025-02",
                    "latest_commit": february[-1],
                    "commits": len(february),
                },
            ]
        )

        # Advance HEAD with a backdated commit. The current HEAD history no
        # longer reproduces the panel, but the previous tip remains in reflog.
        commit_file(
            repo,
            "later-backdated",
            "def f():\n    return 6\n",
            "2025-02-20T12:00:00+00:00",
        )
        selected_candidate, _, status = choose_history_candidate(repo, panel)
        if selected_candidate is None or status != "perfect_panel_match":
            raise AssertionError("Historical panel-tip recovery failed")
        if selected_candidate.count_and_latest_matches != len(panel):
            raise AssertionError("Recovered candidate does not match all months")

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
    print("Month assignment:    committer timestamp (committed_at)")
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
    boundaries, month_end_pairs, pairs, history_refs, errors = prepare(
        joined,
        treatment_clone_dir,
        control_clone_dir,
        args.progress_every,
    )
    checks = build_checks(
        panel,
        joined,
        boundaries,
        month_end_pairs,
        pairs,
        history_refs,
        errors,
    )
    summary = build_summary(
        panel,
        boundaries,
        month_end_pairs,
        pairs,
        history_refs,
        errors,
        checks,
    )

    boundary_path = output_dir / "repo_month_commit_scan_boundaries.csv"
    month_end_path = output_dir / "month_end_parent_pairs.csv"
    pair_path = output_dir / "commit_parent_pairs.csv"
    history_ref_path = qc_dir / "agc_commit_function_history_ref_selection.csv"
    checks_path = qc_dir / "agc_commit_function_scan_prepare_checks.csv"
    errors_path = qc_dir / "agc_commit_function_scan_prepare_errors.csv"
    summary_path = qc_dir / "agc_commit_function_scan_prepare_summary.json"

    atomic_csv(boundaries, boundary_path)
    atomic_csv(month_end_pairs, month_end_path)
    atomic_csv(pairs, pair_path)
    atomic_csv(history_refs, history_ref_path)
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
    print(f"Cross-month overlap rows:   {summary['cross_month_overlap_pair_rows']}")
    print(f"Committer-month mismatches: {summary['committer_month_mismatch_pairs']}")
    print(f"Errors:                     {summary['errors']}")
    print(f"Boundary manifest:          {boundary_path}")
    print(f"Month-end parent records:   {month_end_path}")
    print(f"Commit-parent pairs:        {pair_path}")
    print(f"History-ref audit:          {history_ref_path}")
    print(f"Summary:                    {summary_path}")
    print("=" * 72)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
