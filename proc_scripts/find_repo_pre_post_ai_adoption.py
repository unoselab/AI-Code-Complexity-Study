#!/usr/bin/env python3
"""
Find repositories with clean pre/post AI adoption history using existing monthly data.

This script uses an existing monthly time-series CSV, such as:

    data/ts_repos_monthly.csv
    tmp_adoption_test/data/ts_repos_monthly.csv

Then, for each repository in that existing data, it scans the cloned Git history
to find the first commit that introduces AI/Cursor evidence files.

It selects repositories that have enough monthly observations before and after
the detected adoption month.

This helps avoid cases where AI/Cursor evidence appears too early or too late
for event-panel smoke testing.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


DEFAULT_TIMESERIES_CANDIDATES = [
    Path("tmp_adoption_test/data/ts_repos_monthly.csv"),
    Path("data/ts_repos_monthly.csv"),
]

DEFAULT_EVIDENCE_PATTERNS = [
    ".cursorrules",
    ".cursor/",
    "CLAUDE.md",
    "AGENTS.md",
    ".windsurfrules",
    ".goosehints",
]

CURSOR_ONLY_PATTERNS = [
    ".cursorrules",
    ".cursor/",
]


@dataclass
class AdoptionResult:
    repo_name: str
    repo_path: str

    first_commit: str
    first_commit_month: str
    latest_commit: str
    latest_commit_month: str

    adoption_commit: str
    adoption_month: str
    adoption_subject: str
    evidence_paths: str

    adoption_at_initial_commit: bool

    panel_first_month: str
    panel_latest_month: str
    panel_month_count: int
    adoption_month_in_panel: bool
    pre_panel_months: int
    post_panel_months: int

    pre_git_months: int
    post_git_months: int

    eligible: bool
    skip_reason: str


def repo_to_project_key(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def run_git(repo_path: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def month_index(month: str) -> int:
    year, mon = map(int, month[:7].split("-"))
    return year * 12 + mon


def month_diff(start_month: str, end_month: str) -> int:
    return month_index(end_month) - month_index(start_month)


def normalize_month(value: object) -> str:
    text = str(value).strip()
    if len(text) < 7:
        return ""
    return text[:7]


def commit_month(repo_path: Path, commit: str) -> str:
    return run_git(repo_path, ["show", "-s", "--format=%cs", commit])[:7]


def commit_subject(repo_path: Path, commit: str) -> str:
    return run_git(repo_path, ["show", "-s", "--format=%s", commit])


def list_commits_oldest_first(repo_path: Path) -> list[str]:
    output = run_git(repo_path, ["rev-list", "--reverse", "HEAD"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def changed_paths_for_commit(repo_path: Path, commit: str) -> list[str]:
    """
    Return changed paths for one commit.

    --root is important because it lets us inspect paths introduced by the
    initial commit as well.
    """
    output = run_git(
        repo_path,
        [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            commit,
        ],
    )

    paths: list[str] = []

    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        status = parts[0]

        # Normal lines look like:
        # A\t.cursorrules
        # M\t.cursor/rules.md
        #
        # Rename lines look like:
        # R100\told_path\tnew_path
        if status.startswith("R") or status.startswith("C"):
            paths.extend(parts[1:])
        else:
            paths.extend(parts[1:])

    return paths


def path_matches_evidence(path: str, patterns: list[str]) -> bool:
    normalized = path.strip().lstrip("./").lower()

    for pattern in patterns:
        pattern_norm = pattern.strip().lstrip("./").lower()

        # Directory-style evidence, e.g. .cursor/
        if pattern_norm.endswith("/"):
            prefix = pattern_norm.rstrip("/") + "/"
            if normalized.startswith(prefix):
                return True

        # Exact file evidence, e.g. .cursorrules or CLAUDE.md
        else:
            if normalized == pattern_norm:
                return True

    return False


def find_first_adoption_commit(
    repo_path: Path,
    commits: list[str],
    patterns: list[str],
) -> tuple[str, list[str]] | None:
    for commit in commits:
        changed_paths = changed_paths_for_commit(repo_path, commit)
        evidence_paths = [
            path for path in changed_paths
            if path_matches_evidence(path, patterns)
        ]

        if evidence_paths:
            return commit, sorted(set(evidence_paths))

    return None


def resolve_timeseries_csv(path_arg: str | None) -> Path:
    if path_arg:
        path = Path(path_arg)
        if not path.exists():
            raise SystemExit(f"Missing time-series CSV: {path}")
        return path

    for path in DEFAULT_TIMESERIES_CANDIDATES:
        if path.exists():
            return path

    raise SystemExit(
        "Could not find a time-series CSV. Provide --timeseries-csv explicitly."
    )


def infer_column(df: pd.DataFrame, preferred: str, alternatives: list[str]) -> str:
    if preferred in df.columns:
        return preferred

    for column in alternatives:
        if column in df.columns:
            return column

    raise SystemExit(
        f"Could not find column '{preferred}'. "
        f"Available columns: {list(df.columns)}"
    )


def load_panel_months(
    timeseries_csv: Path,
    repo_column: str,
    time_column: str,
) -> dict[str, list[str]]:
    df = pd.read_csv(timeseries_csv, dtype=str)

    repo_column = infer_column(
        df,
        repo_column,
        ["repo_name", "repo", "full_name", "repository"],
    )

    time_column = infer_column(
        df,
        time_column,
        ["month", "time_period", "date", "week"],
    )

    df = df[[repo_column, time_column]].copy()
    df[repo_column] = df[repo_column].astype(str).str.strip()
    df[time_column] = df[time_column].map(normalize_month)

    df = df[(df[repo_column] != "") & (df[time_column] != "")]

    panel_months: dict[str, list[str]] = {}

    for repo_name, group in df.groupby(repo_column):
        months = sorted(set(group[time_column].tolist()), key=month_index)
        if months:
            panel_months[repo_name] = months

    return panel_months


def read_repo_names_from_csv(path: Path, repo_column: str) -> list[str]:
    repo_names: list[str] = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Could not read header from {path}")

        if repo_column not in reader.fieldnames:
            raise SystemExit(
                f"Column '{repo_column}' not found in {path}. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            repo_name = row.get(repo_column, "").strip()
            if repo_name:
                repo_names.append(repo_name)

    return repo_names


def evaluate_panel_window(
    panel_months: list[str],
    adoption_month: str,
) -> tuple[bool, int, int]:
    adoption_idx = month_index(adoption_month)

    adoption_month_in_panel = adoption_month in panel_months
    pre_months = sum(month_index(month) < adoption_idx for month in panel_months)
    post_months = sum(month_index(month) > adoption_idx for month in panel_months)

    return adoption_month_in_panel, pre_months, post_months


def analyze_repo(
    repo_name: str,
    repo_path: Path,
    panel_months: list[str],
    patterns: list[str],
    min_pre_months: int,
    min_post_months: int,
    require_event_month: bool,
    include_initial_adoption: bool,
) -> AdoptionResult | None:
    if not (repo_path / ".git").exists():
        print(f"  skipped: missing cloned Git repository: {repo_path}")
        return None

    try:
        commits = list_commits_oldest_first(repo_path)
    except subprocess.CalledProcessError as exc:
        print(f"  skipped: failed to list commits: {exc}")
        return None

    if not commits:
        print("  skipped: no commits found")
        return None

    adoption = find_first_adoption_commit(repo_path, commits, patterns)
    if not adoption:
        print("  skipped: no AI/Cursor evidence found")
        return None

    first_commit = commits[0]
    latest_commit = commits[-1]
    adoption_commit, evidence_paths = adoption

    first_commit_month = commit_month(repo_path, first_commit)
    latest_commit_month = commit_month(repo_path, latest_commit)
    adoption_month = commit_month(repo_path, adoption_commit)

    adoption_month_in_panel, pre_panel_months, post_panel_months = evaluate_panel_window(
        panel_months,
        adoption_month,
    )

    adoption_at_initial_commit = adoption_commit == first_commit

    eligible = True
    skip_reason = ""

    if adoption_at_initial_commit and not include_initial_adoption:
        eligible = False
        skip_reason = "adoption_at_initial_commit"
    elif require_event_month and not adoption_month_in_panel:
        eligible = False
        skip_reason = "adoption_month_not_in_existing_timeseries"
    elif pre_panel_months < min_pre_months:
        eligible = False
        skip_reason = "insufficient_pre_panel_months"
    elif post_panel_months < min_post_months:
        eligible = False
        skip_reason = "insufficient_post_panel_months"

    return AdoptionResult(
        repo_name=repo_name,
        repo_path=str(repo_path),

        first_commit=first_commit,
        first_commit_month=first_commit_month,
        latest_commit=latest_commit,
        latest_commit_month=latest_commit_month,

        adoption_commit=adoption_commit,
        adoption_month=adoption_month,
        adoption_subject=commit_subject(repo_path, adoption_commit),
        evidence_paths=";".join(evidence_paths),

        adoption_at_initial_commit=adoption_at_initial_commit,

        panel_first_month=panel_months[0],
        panel_latest_month=panel_months[-1],
        panel_month_count=len(panel_months),
        adoption_month_in_panel=adoption_month_in_panel,
        pre_panel_months=pre_panel_months,
        post_panel_months=post_panel_months,

        pre_git_months=month_diff(first_commit_month, adoption_month),
        post_git_months=month_diff(adoption_month, latest_commit_month),

        eligible=eligible,
        skip_reason=skip_reason,
    )


def write_results(output_path: Path, results: list[AdoptionResult]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(asdict(results[0]).keys()) if results else [
        "repo_name",
        "repo_path",
        "first_commit",
        "first_commit_month",
        "latest_commit",
        "latest_commit_month",
        "adoption_commit",
        "adoption_month",
        "adoption_subject",
        "evidence_paths",
        "adoption_at_initial_commit",
        "panel_first_month",
        "panel_latest_month",
        "panel_month_count",
        "adoption_month_in_panel",
        "pre_panel_months",
        "post_panel_months",
        "pre_git_months",
        "post_git_months",
        "eligible",
        "skip_reason",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            writer.writerow(asdict(result))


def sort_candidates(results: list[AdoptionResult]) -> list[AdoptionResult]:
    """
    Prefer balanced pre/post panel coverage.

    A repo with 6 pre months and 6 post months is usually more useful than
    a repo with 60 pre months and 1 post month for an event-panel smoke test.
    """
    return sorted(
        results,
        key=lambda r: (
            min(r.pre_panel_months, r.post_panel_months),
            r.pre_panel_months + r.post_panel_months,
            r.panel_month_count,
        ),
        reverse=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find repos with clean pre/post AI adoption history."
    )

    parser.add_argument(
        "repo_names",
        nargs="*",
        help="Optional GitHub repositories in OWNER/REPO format.",
    )

    parser.add_argument(
        "--timeseries-csv",
        default=None,
        help=(
            "Existing monthly time-series CSV. "
            "Default: tmp_adoption_test/data/ts_repos_monthly.csv if present, "
            "otherwise data/ts_repos_monthly.csv."
        ),
    )

    parser.add_argument(
        "--repo-list-csv",
        help="Optional CSV containing repository names.",
    )

    parser.add_argument(
        "--repo-column",
        default="repo_name",
        help="Repository column name. Default: repo_name.",
    )

    parser.add_argument(
        "--time-column",
        default="month",
        help="Time column in the time-series CSV. Default: month.",
    )

    parser.add_argument(
        "--clone-root",
        default="../CursorRepos",
        help="Directory containing cloned repositories. Default: ../CursorRepos.",
    )

    parser.add_argument(
        "--output",
        default="tmp_adoption_test/data/pre_post_ai_adoption_candidates.csv",
        help="Output CSV path for the top selected candidates.",
    )

    parser.add_argument(
        "--all-output",
        default="tmp_adoption_test/data/pre_post_ai_adoption_all_inspected.csv",
        help="Output CSV path for all inspected repos with evidence.",
    )

    parser.add_argument(
        "--min-pre-months",
        type=int,
        default=1,
        help="Minimum existing panel months before adoption. Default: 1.",
    )

    parser.add_argument(
        "--min-post-months",
        type=int,
        default=1,
        help="Minimum existing panel months after adoption. Default: 1.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Number of best candidates to write to --output. Default: 3.",
    )

    parser.add_argument(
        "--include-initial-adoption",
        action="store_true",
        help="Include repositories where evidence appears in the initial commit.",
    )

    parser.add_argument(
        "--no-require-event-month",
        action="store_true",
        help="Do not require adoption month to exist in the time-series CSV.",
    )

    parser.add_argument(
        "--cursor-only",
        action="store_true",
        help="Only detect Cursor evidence: .cursorrules and .cursor/.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of repositories to inspect.",
    )

    args = parser.parse_args()

    timeseries_csv = resolve_timeseries_csv(args.timeseries_csv)
    panel_months_by_repo = load_panel_months(
        timeseries_csv=timeseries_csv,
        repo_column=args.repo_column,
        time_column=args.time_column,
    )

    repo_names = list(args.repo_names)

    if args.repo_list_csv:
        repo_names.extend(
            read_repo_names_from_csv(Path(args.repo_list_csv), args.repo_column)
        )

    if not repo_names:
        repo_names = list(panel_months_by_repo.keys())

    # Preserve order while removing duplicates
    repo_names = list(dict.fromkeys(repo_names))

    if args.limit is not None:
        repo_names = repo_names[: args.limit]

    if not repo_names:
        raise SystemExit("No repositories to inspect.")

    clone_root = Path(args.clone_root)
    output_path = Path(args.output)
    all_output_path = Path(args.all_output)
    patterns = CURSOR_ONLY_PATTERNS if args.cursor_only else DEFAULT_EVIDENCE_PATTERNS
    require_event_month = not args.no_require_event_month

    print("Time-series CSV:", timeseries_csv)
    print("Clone root:", clone_root)
    print("Output top candidates:", output_path)
    print("Output all inspected:", all_output_path)
    print("Evidence patterns:", ", ".join(patterns))
    print("Minimum pre panel months:", args.min_pre_months)
    print("Minimum post panel months:", args.min_post_months)
    print("Require adoption month in panel:", require_event_month)
    print("Top N:", args.top_n)
    print("Repositories to inspect:", len(repo_names))
    print()

    inspected_with_evidence: list[AdoptionResult] = []

    for idx, repo_name in enumerate(repo_names, start=1):
        panel_months = panel_months_by_repo.get(repo_name)

        print(f"[{idx}/{len(repo_names)}] {repo_name}")

        if not panel_months:
            print("  skipped: repo not found in existing time-series data")
            continue

        repo_path = clone_root / repo_to_project_key(repo_name)

        result = analyze_repo(
            repo_name=repo_name,
            repo_path=repo_path,
            panel_months=panel_months,
            patterns=patterns,
            min_pre_months=args.min_pre_months,
            min_post_months=args.min_post_months,
            require_event_month=require_event_month,
            include_initial_adoption=args.include_initial_adoption,
        )

        if result is None:
            continue

        inspected_with_evidence.append(result)

        status = "eligible" if result.eligible else f"skipped: {result.skip_reason}"

        print(
            "  adoption_month:",
            result.adoption_month,
            "| panel:",
            f"{result.panel_first_month}..{result.panel_latest_month}",
            "| pre_panel:",
            result.pre_panel_months,
            "| post_panel:",
            result.post_panel_months,
            "| event_in_panel:",
            result.adoption_month_in_panel,
            "| initial:",
            result.adoption_at_initial_commit,
            "| evidence:",
            result.evidence_paths,
        )
        print(" ", status)

    eligible_results = [result for result in inspected_with_evidence if result.eligible]
    eligible_results = sort_candidates(eligible_results)
    top_results = eligible_results[: args.top_n]

    write_results(output_path, top_results)
    write_results(all_output_path, inspected_with_evidence)

    print()
    print("Inspected repositories:", len(repo_names))
    print("Repositories with evidence:", len(inspected_with_evidence))
    print("Eligible clean pre/post candidates:", len(eligible_results))
    print("Top candidates written:", len(top_results))
    print("Wrote top candidates:", output_path)
    print("Wrote all inspected:", all_output_path)

    if top_results:
        print()
        print("Top candidates:")
        for result in top_results:
            print(
                f"- {result.repo_name} | adoption={result.adoption_month} "
                f"| panel={result.panel_first_month}..{result.panel_latest_month} "
                f"| pre_panel={result.pre_panel_months} "
                f"| post_panel={result.post_panel_months} "
                f"| evidence={result.evidence_paths}"
            )


if __name__ == "__main__":
    main()
