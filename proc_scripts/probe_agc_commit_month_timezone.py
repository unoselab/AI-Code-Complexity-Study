#!/usr/bin/env python3
"""
Probe commit-month timezone semantics for the run-py-5 pipeline.

The original repository analyzer used:

    datetime.fromtimestamp(commit.committed_date)

without an explicit timezone. That assigns each commit to a month using the
collection machine's local timezone. This diagnostic compares that exact
behavior with UTC, America/Chicago, and the timezone embedded in Git's %cI
value. It evaluates only a small set of named refs so a full 220-repository
history search is not required.

Outputs
-------
1. agc_commit_function_timezone_probe_summary.csv
   One row per repository, candidate ref, and timezone mode.
2. agc_commit_function_timezone_probe_months.csv
   Repository-month count/latest-commit comparisons.
3. agc_commit_function_timezone_probe_metadata.json
   Runtime environment and selected repositories.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

FIELD_SEPARATOR = "\x1f"
DEFAULT_REPOSITORIES = [
    "OpenMOSS/Language-Model-SAEs",
    "KroMiose/nekro-agent",
    "PostHog/posthog",
    "Kiln-AI/Kiln",
    "thefatedefeater/V2ray-Config",
]
TIMEZONE_MODES = (
    "original_local",
    "utc",
    "america_chicago",
    "commit_embedded_offset",
)


@dataclass(frozen=True)
class GitCommit:
    commit: str
    epoch: int
    committed_iso: str
    history_order: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-panel",
        type=Path,
        default=Path(
            "repo_python/run-py-4a/strict/"
            "panel_event_monthly_agc_changed_block_py.csv"
        ),
    )
    parser.add_argument(
        "--history-audit",
        type=Path,
        default=Path(
            "repo_python/tmp/run-py-5a/strict/"
            "agc_commit_function_history_ref_selection.csv"
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
        default=Path("repo_python/tmp/run-py-5a/strict/timezone-probe"),
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repositories",
        default=None,
        help=(
            "Repository name to probe. Repeat the option for multiple repos. "
            "A five-repository diagnostic sample is used when omitted."
        ),
    )
    parser.add_argument(
        "--max-named-refs",
        type=int,
        default=5,
        help="Maximum scored named refs per repository, excluding HEAD.",
    )
    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"[ERROR] required file not found: {path}")


def require_dir(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"[ERROR] required directory not found: {path}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def choose_column(fieldnames: Sequence[str], candidates: Sequence[str]) -> str:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    raise SystemExit(
        "[ERROR] none of the required column aliases were found: "
        + ", ".join(candidates)
    )


def int_value(value: object, default: int = 0) -> int:
    try:
        text = str(value).strip()
        return int(float(text)) if text else default
    except (TypeError, ValueError):
        return default


def repo_dir_for(
    dataset_source: str,
    repo_name: str,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> Path:
    root = treatment_clone_dir if dataset_source == "treatment" else control_clone_dir
    return root / repo_name.replace("/", "_")


def run_git_log(repo_dir: Path, revision: str) -> list[GitCommit]:
    command = [
        "git",
        "-C",
        str(repo_dir),
        "log",
        revision,
        f"--format=%H%x1f%ct%x1f%cI",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git log failed for {revision}: {message}")

    commits: list[GitCommit] = []
    for history_order, raw_line in enumerate(result.stdout.splitlines(), start=1):
        fields = raw_line.split(FIELD_SEPARATOR)
        if len(fields) != 3:
            raise RuntimeError(f"unexpected git log row: {raw_line!r}")
        commit, epoch_text, committed_iso = fields
        commits.append(
            GitCommit(
                commit=commit.strip(),
                epoch=int(epoch_text.strip()),
                committed_iso=committed_iso.strip(),
                history_order=history_order,
            )
        )
    return commits


def commit_datetime(commit: GitCommit, mode: str) -> datetime:
    if mode == "original_local":
        # Exact behavior used by the original analyzer.
        return datetime.fromtimestamp(commit.epoch)
    if mode == "utc":
        return datetime.fromtimestamp(commit.epoch, tz=timezone.utc)
    if mode == "america_chicago":
        return datetime.fromtimestamp(commit.epoch, tz=ZoneInfo("America/Chicago"))
    if mode == "commit_embedded_offset":
        return datetime.fromisoformat(commit.committed_iso)
    raise ValueError(f"unsupported timezone mode: {mode}")


def aggregate_commits(
    commits: Sequence[GitCommit],
    mode: str,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for commit in commits:
        dt = commit_datetime(commit, mode)
        month = dt.strftime("%Y-%m")
        row = result.setdefault(
            month,
            {
                "count": 0,
                "latest_commit": "",
                "latest_epoch": None,
                "latest_history_order": None,
            },
        )
        row["count"] = int(row["count"]) + 1

        current_epoch = row["latest_epoch"]
        # Match the original strict greater-than update. Git log order breaks
        # ties because the first equal-timestamp commit remains selected.
        if current_epoch is None or commit.epoch > int(current_epoch):
            row["latest_commit"] = commit.commit
            row["latest_epoch"] = commit.epoch
            row["latest_history_order"] = commit.history_order
    return result


def candidate_refs_for_repo(
    audit_rows: Sequence[dict[str, str]],
    dataset_source: str,
    repo_name: str,
    max_named_refs: int,
) -> list[str]:
    rows = [
        row
        for row in audit_rows
        if row.get("dataset_source") == dataset_source
        and row.get("repo_name") == repo_name
        and row.get("candidate_kind") == "named_ref"
    ]
    rows.sort(
        key=lambda row: (
            -int_value(row.get("candidate_contains_all_panel_anchors")),
            -int_value(row.get("count_and_latest_matches")),
            -int_value(row.get("count_matches")),
            -int_value(row.get("latest_matches")),
            int_value(row.get("candidate_priority"), default=10**9),
            row.get("candidate_ref", ""),
        )
    )

    refs = ["HEAD"]
    for row in rows:
        candidate = str(row.get("candidate_ref", "")).strip()
        if candidate and candidate not in refs:
            refs.append(candidate)
        if len(refs) - 1 >= max_named_refs:
            break
    return refs


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit(f"[ERROR] no rows available for {path}")
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    require_file(args.input_panel)
    require_file(args.history_audit)
    require_dir(args.treatment_clone_dir)
    require_dir(args.control_clone_dir)
    if args.max_named_refs <= 0:
        raise SystemExit("[ERROR] --max-named-refs must be positive")

    panel_rows = read_csv(args.input_panel)
    audit_rows = read_csv(args.history_audit)
    if not panel_rows:
        raise SystemExit("[ERROR] input panel is empty")

    fieldnames = list(panel_rows[0])
    month_column = choose_column(fieldnames, ("time", "month"))
    commit_column = choose_column(fieldnames, ("latest_commit", "month_end_commit"))
    repositories = args.repositories or DEFAULT_REPOSITORIES

    panel_by_repo: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in panel_rows:
        key = (str(row.get("dataset_source", "")), str(row.get("repo_name", "")))
        if key[1] in repositories:
            panel_by_repo[key].append(row)

    missing_repositories = sorted(
        set(repositories) - {repo_name for _, repo_name in panel_by_repo}
    )
    if missing_repositories:
        raise SystemExit(
            "[ERROR] repositories missing from panel: " + ", ".join(missing_repositories)
        )

    summary_rows: list[dict[str, object]] = []
    month_rows: list[dict[str, object]] = []

    print("=" * 72)
    print("AGC commit-month timezone probe")
    print(f"System TZ environment : {os.environ.get('TZ', '<unset>')}")
    print(f"time.tzname          : {time.tzname}")
    print(f"time.timezone        : {time.timezone}")
    print(f"time.altzone         : {getattr(time, 'altzone', '<unavailable>')}")
    print(f"Repositories         : {len(repositories)}")
    print("=" * 72)

    for dataset_source, repo_name in sorted(panel_by_repo):
        repo_dir = repo_dir_for(
            dataset_source,
            repo_name,
            args.treatment_clone_dir,
            args.control_clone_dir,
        )
        require_dir(repo_dir)
        refs = candidate_refs_for_repo(
            audit_rows,
            dataset_source,
            repo_name,
            args.max_named_refs,
        )
        repo_panel = sorted(panel_by_repo[(dataset_source, repo_name)], key=lambda r: r[month_column])

        print(f"[repo] {dataset_source} {repo_name}; refs={len(refs)}")
        for revision in refs:
            try:
                commits = run_git_log(repo_dir, revision)
            except RuntimeError as exc:
                print(f"  [skip] {revision}: {exc}")
                continue

            for mode in TIMEZONE_MODES:
                grouped = aggregate_commits(commits, mode)
                count_matches = 0
                latest_matches = 0
                both_matches = 0
                absolute_count_delta = 0

                for panel_row in repo_panel:
                    month = str(panel_row[month_column])
                    panel_count = int_value(panel_row.get("commits"))
                    panel_latest = str(panel_row.get(commit_column, "")).strip()
                    reconstructed = grouped.get(month, {})
                    selected_count = int_value(reconstructed.get("count"))
                    selected_latest = str(reconstructed.get("latest_commit", "")).strip()
                    count_match = int(selected_count == panel_count)
                    latest_match = int(selected_latest == panel_latest)
                    both_match = int(count_match and latest_match)
                    count_delta = selected_count - panel_count

                    count_matches += count_match
                    latest_matches += latest_match
                    both_matches += both_match
                    absolute_count_delta += abs(count_delta)
                    month_rows.append(
                        {
                            "dataset_source": dataset_source,
                            "repo_name": repo_name,
                            "candidate_ref": revision,
                            "timezone_mode": mode,
                            "month": month,
                            "panel_commits": panel_count,
                            "selected_commits": selected_count,
                            "count_delta": count_delta,
                            "panel_latest_commit": panel_latest,
                            "selected_latest_commit": selected_latest,
                            "count_match": count_match,
                            "latest_match": latest_match,
                            "count_and_latest_match": both_match,
                        }
                    )

                summary_rows.append(
                    {
                        "dataset_source": dataset_source,
                        "repo_name": repo_name,
                        "candidate_ref": revision,
                        "timezone_mode": mode,
                        "history_commits": len(commits),
                        "panel_months": len(repo_panel),
                        "count_matches": count_matches,
                        "latest_matches": latest_matches,
                        "count_and_latest_matches": both_matches,
                        "total_absolute_count_delta": absolute_count_delta,
                        "perfect_panel_match": int(both_matches == len(repo_panel)),
                    }
                )

    summary_rows.sort(
        key=lambda row: (
            row["dataset_source"],
            row["repo_name"],
            -int(row["count_and_latest_matches"]),
            int(row["total_absolute_count_delta"]),
            row["candidate_ref"],
            row["timezone_mode"],
        )
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "agc_commit_function_timezone_probe_summary.csv"
    months_path = args.output_dir / "agc_commit_function_timezone_probe_months.csv"
    metadata_path = args.output_dir / "agc_commit_function_timezone_probe_metadata.json"
    write_csv(summary_path, summary_rows)
    write_csv(months_path, month_rows)

    metadata = {
        "script": str(Path(__file__).resolve()),
        "input_panel": str(args.input_panel.resolve()),
        "history_audit": str(args.history_audit.resolve()),
        "repositories": repositories,
        "timezone_modes": list(TIMEZONE_MODES),
        "system_tz_environment": os.environ.get("TZ"),
        "time_tzname": list(time.tzname),
        "time_timezone": time.timezone,
        "time_altzone": getattr(time, "altzone", None),
        "max_named_refs": args.max_named_refs,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print()
    print("Best result per repository:")
    for dataset_source, repo_name in sorted(panel_by_repo):
        candidates = [
            row
            for row in summary_rows
            if row["dataset_source"] == dataset_source and row["repo_name"] == repo_name
        ]
        best = candidates[0]
        print(
            f"  {repo_name}: ref={best['candidate_ref']} "
            f"mode={best['timezone_mode']} "
            f"both={best['count_and_latest_matches']}/{best['panel_months']} "
            f"abs_delta={best['total_absolute_count_delta']}"
        )

    print()
    print(f"Summary : {summary_path}")
    print(f"Months  : {months_path}")
    print(f"Metadata: {metadata_path}")


if __name__ == "__main__":
    main()
