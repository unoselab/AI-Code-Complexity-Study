#!/usr/bin/env python3
"""Prepare the Python-primary repository manifest for the run-x-c experiment.

This script reproduces the paper's programming-language subset logic before
cloning repositories. Treatment language is taken directly from repos.csv.
Matched controls are included because they are assigned to selected Python
treatments; their own language metadata is not required. It uses three
replication-package inputs:

1. ``matching.csv`` for treatment-to-control assignments.
2. ``repos.csv`` for ``repo_primary_language`` metadata.
3. ``panel_event_monthly.csv`` for the paper's estimable repository universe
   and adoption-event filtering.

The script intentionally does not clone, fetch, checkout, reset, or modify any
repository. It can inspect existing local clone directories using read-only Git
commands so that the next cloning stage knows which repositories still need to
be cloned.

The paper's Appendix reports 121 treatment repositories and 127 control
repositories for the Python language setting. Seven panel treatments are not
represented by treatment rows in matching.csv. They are still cloned and kept
in the Appendix-faithful DiD treatment sample; the missing pair provenance is
recorded explicitly because their original treatment-to-control assignments
cannot be recovered.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


IMPLEMENTATION_VERSION = "v4"
MATCHED_CONTROL_COLUMNS = (
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
)


@dataclasses.dataclass(frozen=True)
class CloneInspection:
    """Read-only local clone inspection result."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the paper-aligned Python-primary treatment/control manifest "
            "and inspect current local clone coverage."
        )
    )
    parser.add_argument(
        "--matching-file",
        default="data_baseline_backup/matching.csv",
        help="Replication-package matching.csv file.",
    )
    parser.add_argument(
        "--repos-file",
        default="data_baseline_backup/repos.csv",
        help="Replication-package repos.csv file with repo_primary_language.",
    )
    parser.add_argument(
        "--panel-file",
        default="data_baseline_backup/panel_event_monthly.csv",
        help="Replication-package repository-month event panel.",
    )
    parser.add_argument(
        "--treatment-clone-dir",
        default="../treatment-python-primary-repo",
        help="Python-scope treatment clone root inspected with read-only Git commands.",
    )
    parser.add_argument(
        "--control-clone-dir",
        default="../control-python-primary-repo",
        help="Matched-control clone root for Python-scope treatments.",
    )
    parser.add_argument(
        "--output-dir",
        default="repo_x01/run-x-c01",
        help="Directory for detailed C01 outputs.",
    )
    parser.add_argument(
        "--summary-output",
        default=(
            "repo_x01/tmp/run-x-c01/"
            "python_primary_repo_manifest_summary.csv"
        ),
        help="Compact key-value summary output.",
    )
    parser.add_argument(
        "--target-language",
        default="Python",
        help="Exact primary-language value selected case-insensitively.",
    )
    parser.add_argument(
        "--min-treatment-event",
        type=int,
        default=202408,
        help="Earliest treatment cohort included by the paper setting.",
    )
    parser.add_argument(
        "--max-treatment-event",
        type=int,
        default=202503,
        help="Latest treatment cohort included by the paper setting.",
    )
    parser.add_argument(
        "--expected-paper-treatment-repos",
        type=int,
        default=121,
        help="Published Appendix count for Python treatment repositories.",
    )
    parser.add_argument(
        "--expected-paper-control-repos",
        type=int,
        default=127,
        help="Published Appendix count for Python control repositories.",
    )
    parser.add_argument(
        "--expected-matched-treatment-repos",
        type=int,
        default=114,
        help=(
            "Expected Python treatment repositories that also have treatment "
            "rows in matching.csv."
        ),
    )
    parser.add_argument(
        "--expected-clone-target-repos",
        type=int,
        default=248,
        help=(
            "Expected Appendix-faithful clone targets: all Python treatments "
            "plus unique matched controls."
        ),
    )
    parser.add_argument(
        "--expected-treatment-repos-without-matching",
        type=int,
        default=7,
        help=(
            "Expected Python treatment repositories present in the paper panel "
            "but absent from treatment rows in matching.csv."
        ),
    )
    parser.add_argument(
        "--strict-expected-counts",
        type=int,
        choices=(0, 1),
        default=1,
        help="Fail when published treatment/control counts are not reproduced.",
    )
    parser.add_argument(
        "--inspect-local-clones",
        type=int,
        choices=(0, 1),
        default=1,
        help="Inspect existing clone roots using read-only Git commands.",
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


def repo_key(repo_name: object) -> str:
    return normalize_repo_name(repo_name).casefold()


def normalize_language(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def language_key(value: object) -> str:
    return normalize_language(value).casefold()


def clone_directory_name(repo_name: str) -> str:
    return normalize_repo_name(repo_name).replace("/", "_")


def validate_repo_name(repo_name: str) -> bool:
    parts = normalize_repo_name(repo_name).split("/")
    return len(parts) == 2 and all(part.strip() for part in parts)


def parse_yyyymm(value: object) -> Optional[int]:
    """Parse YYYY-MM, YYYYMM, date-like, or numeric event values."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "nat"}:
        return None

    if re.fullmatch(r"\d{6}(?:\.0+)?", text):
        return int(float(text))
    match = re.match(r"^(\d{4})[-/](\d{1,2})", text)
    if match:
        return int(match.group(1)) * 100 + int(match.group(2))

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return int(parsed.year) * 100 + int(parsed.month)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(frame: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def canonicalize_repo_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    result = frame.copy()
    result[column] = result[column].map(normalize_repo_name)
    result[f"{column}_key"] = result[column].map(repo_key)
    return result


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


def build_clone_indexes(
    clone_root: Path,
) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    """Index immediate child directories by name and GitHub origin."""
    by_name: dict[str, list[Path]] = {}
    by_origin: dict[str, list[Path]] = {}
    if not clone_root.exists() or not clone_root.is_dir():
        return by_name, by_origin

    for child in sorted(clone_root.iterdir(), key=lambda path: path.name.casefold()):
        by_name.setdefault(child.name.casefold(), []).append(child)
        if not child.is_dir():
            continue
        origin = run_git(["-C", str(child), "remote", "get-url", "origin"])
        if origin.returncode != 0:
            continue
        origin_repo = parse_github_repo_from_url(origin.stdout.strip())
        if origin_repo:
            by_origin.setdefault(repo_key(origin_repo), []).append(child)
    return by_name, by_origin


def choose_clone_candidate(
    repo_name: str,
    clone_root: Path,
    by_name: dict[str, list[Path]],
    by_origin: dict[str, list[Path]],
) -> tuple[Optional[Path], str, str]:
    expected = clone_root / clone_directory_name(repo_name)
    if expected.exists():
        return expected, "expected_path", ""

    name_matches = by_name.get(expected.name.casefold(), [])
    if len(name_matches) == 1:
        return name_matches[0], "casefold_path", ""
    if len(name_matches) > 1:
        return None, "ambiguous_casefold_path", ";".join(map(str, name_matches))

    origin_matches = by_origin.get(repo_key(repo_name), [])
    if len(origin_matches) == 1:
        return origin_matches[0], "origin_url", ""
    if len(origin_matches) > 1:
        return None, "ambiguous_origin_url", ";".join(map(str, origin_matches))
    return None, "not_found", ""


def inspect_local_clone(
    repo_name: str,
    clone_root: Path,
    by_name: dict[str, list[Path]],
    by_origin: dict[str, list[Path]],
) -> CloneInspection:
    candidate, match_method, detail = choose_clone_candidate(
        repo_name, clone_root, by_name, by_origin
    )
    if candidate is None:
        if match_method.startswith("ambiguous_"):
            return CloneInspection(
                clone_path="",
                path_exists=False,
                path_is_directory=False,
                is_git_repository=False,
                head_resolves=False,
                origin_url="",
                origin_repo_name="",
                origin_matches_expected=None,
                local_status="ambiguous_local_clone",
                local_reason=detail,
                match_method=match_method,
            )
        return CloneInspection(
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
        return CloneInspection(
            clone_path=str(candidate),
            path_exists=True,
            path_is_directory=False,
            is_git_repository=False,
            head_resolves=False,
            origin_url="",
            origin_repo_name="",
            origin_matches_expected=None,
            local_status="clone_path_not_directory",
            local_reason="The selected clone path exists but is not a directory.",
            match_method=match_method,
        )

    inside = run_git(["-C", str(candidate), "rev-parse", "--is-inside-work-tree"])
    is_git = inside.returncode == 0 and inside.stdout.strip() == "true"
    if not is_git:
        return CloneInspection(
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
    origin = run_git(["-C", str(candidate), "remote", "get-url", "origin"])
    origin_url = origin.stdout.strip() if origin.returncode == 0 else ""
    origin_repo = parse_github_repo_from_url(origin_url)
    origin_matches: Optional[bool]
    if origin_repo:
        origin_matches = repo_key(origin_repo) == repo_key(repo_name)
    else:
        origin_matches = None

    if head.returncode != 0:
        status = "git_head_unresolved"
        reason = (head.stderr or head.stdout).strip()[:1000]
    elif origin_matches is False:
        status = "available_origin_mismatch"
        reason = f"Expected {repo_name}, but origin points to {origin_repo or origin_url}."
    else:
        status = "available"
        reason = ""

    return CloneInspection(
        clone_path=str(candidate),
        path_exists=True,
        path_is_directory=True,
        is_git_repository=True,
        head_resolves=head.returncode == 0,
        origin_url=origin_url,
        origin_repo_name=origin_repo,
        origin_matches_expected=origin_matches,
        local_status=status,
        local_reason=reason,
        match_method=match_method,
    )


def build_repo_metadata(repos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    require_columns(repos, ["repo_name", "repo_primary_language"], "repos.csv")
    frame = canonicalize_repo_column(repos, "repo_name")
    frame["repo_primary_language"] = frame["repo_primary_language"].map(
        normalize_language
    )

    conflict_rows: list[dict[str, object]] = []
    for key, group in frame.groupby("repo_name_key", sort=True):
        languages = sorted(
            {value for value in group["repo_primary_language"] if value}
        )
        names = sorted({value for value in group["repo_name"] if value})
        if len(languages) > 1 or len(names) > 1:
            conflict_rows.append(
                {
                    "repo_name_key": key,
                    "repo_name_values": ";".join(names),
                    "repo_primary_language_values": ";".join(languages),
                    "row_count": len(group),
                }
            )

    metadata = frame.drop_duplicates("repo_name_key", keep="last").copy()
    conflicts = pd.DataFrame(
        conflict_rows,
        columns=[
            "repo_name_key",
            "repo_name_values",
            "repo_primary_language_values",
            "row_count",
        ],
    )
    return metadata, conflicts


def build_paper_python_scope(
    matching: pd.DataFrame,
    metadata: pd.DataFrame,
    panel: pd.DataFrame,
    target_language: str,
    min_event: int,
    max_event: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Reproduce the paper's programming-language setting.

    The replication analysis selects treated repositories by the language
    metadata in repos.csv and then includes the controls assigned to those
    treated repositories in matching.csv. Control-language metadata is not
    required for inclusion and is not inferred from repository contents.

    A treated repository can remain in the Appendix language setting even
    when matching.csv has no treatment row for it. Such repositories are kept
    in the Appendix treatment audit but excluded from the strict matched clone
    manifest because their original controls cannot be recovered.
    """
    require_columns(
        matching,
        ["repo_name", "group", *MATCHED_CONTROL_COLUMNS],
        "matching.csv",
    )
    require_columns(panel, ["repo_name", "event"], "panel_event_monthly.csv")

    matching_frame = canonicalize_repo_column(matching, "repo_name")
    matching_frame["group_normalized"] = (
        matching_frame["group"].astype(str).str.strip().str.casefold()
    )
    treatment_matching = matching_frame[
        matching_frame["group_normalized"].eq("treatment")
    ].copy()
    duplicated_treatment_matching = treatment_matching[
        treatment_matching.duplicated("repo_name_key", keep=False)
    ].copy()
    treatment_matching = treatment_matching.drop_duplicates(
        "repo_name_key", keep="last"
    )
    treatment_matching_map = treatment_matching.set_index("repo_name_key")

    panel_frame = canonicalize_repo_column(panel, "repo_name")
    panel_frame["event_yyyymm"] = panel_frame["event"].map(parse_yyyymm)
    language_map = metadata.set_index("repo_name_key")["repo_primary_language"]
    panel_frame["repo_primary_language"] = panel_frame["repo_name_key"].map(
        language_map
    )
    panel_frame["repo_primary_language"] = panel_frame[
        "repo_primary_language"
    ].map(normalize_language)

    event_values = panel_frame["event_yyyymm"].fillna(0).astype(int)
    paper_event_scope = panel_frame[
        event_values.eq(0)
        | event_values.between(min_event, max_event, inclusive="both")
    ].copy()
    paper_event_scope["paper_role"] = "control"
    paper_event_scope.loc[
        paper_event_scope["event_yyyymm"].fillna(0).astype(int).gt(0),
        "paper_role",
    ] = "treatment"

    target_key = language_key(target_language)
    treatment_panel = paper_event_scope[
        paper_event_scope["paper_role"].eq("treatment")
        & paper_event_scope["repo_primary_language"].map(language_key).eq(target_key)
    ].copy()
    treatment_keys = sorted(treatment_panel["repo_name_key"].dropna().unique())

    panel_name_map = (
        paper_event_scope[["repo_name_key", "repo_name"]]
        .drop_duplicates("repo_name_key", keep="last")
        .set_index("repo_name_key")["repo_name"]
    )
    metadata_name_map = metadata.set_index("repo_name_key")["repo_name"]
    metadata_language_map = metadata.set_index("repo_name_key")[
        "repo_primary_language"
    ]

    treatment_rows: list[dict[str, object]] = []
    slot_rows: list[dict[str, object]] = []
    missing_matching_rows: list[dict[str, object]] = []

    for treatment_key in treatment_keys:
        treatment_name = panel_name_map.get(
            treatment_key,
            metadata_name_map.get(treatment_key, treatment_key),
        )
        matching_available = treatment_key in treatment_matching_map.index
        nonempty_slots = 0

        if matching_available:
            matching_row = treatment_matching_map.loc[treatment_key]
            if isinstance(matching_row, pd.DataFrame):
                matching_row = matching_row.iloc[-1]

            for slot_index, slot_column in enumerate(
                MATCHED_CONTROL_COLUMNS, start=1
            ):
                control_name = normalize_repo_name(matching_row.get(slot_column, ""))
                if not control_name:
                    continue
                nonempty_slots += 1
                control_key = repo_key(control_name)
                control_language = normalize_language(
                    metadata_language_map.get(control_key, "")
                )
                control_present_as_control = bool(
                    (
                        paper_event_scope["repo_name_key"].eq(control_key)
                        & paper_event_scope["paper_role"].eq("control")
                    ).any()
                )
                if not control_present_as_control:
                    exclusion_reason = "matched_control_absent_from_paper_panel"
                else:
                    exclusion_reason = ""

                slot_rows.append(
                    {
                        "treatment_repo_name": treatment_name,
                        "treatment_repo_key": treatment_key,
                        "treatment_primary_language": target_language,
                        "matched_control_slot": slot_index,
                        "matched_control_column": slot_column,
                        "control_repo_name": control_name,
                        "control_repo_key": control_key,
                        "control_primary_language_metadata": control_language,
                        "control_language_metadata_available": bool(control_language),
                        "control_present_in_paper_panel_as_control": control_present_as_control,
                        "selected_in_paper_python_setting": control_present_as_control,
                        "eligible_for_python_scope_clone": control_present_as_control,
                        "scope_basis": "matched_control_of_python_treatment",
                        "clone_exclusion_reason": exclusion_reason,
                    }
                )
        else:
            missing_matching_rows.append(
                {
                    "issue_type": "python_treatment_missing_from_matching",
                    "repo_name": treatment_name,
                    "repo_name_key": treatment_key,
                    "detail": (
                        "Retained and cloned because the paper language setting "
                        "is defined from panel_event_monthly.csv plus repos.csv; "
                        "no treatment-specific controls can be recovered from "
                        "matching.csv."
                    ),
                }
            )

        treatment_group = treatment_panel[
            treatment_panel["repo_name_key"].eq(treatment_key)
        ]
        event_series = treatment_group["event_yyyymm"].dropna()
        treatment_rows.append(
            {
                "repo_name": treatment_name,
                "repo_name_key": treatment_key,
                "repo_primary_language": target_language,
                "language_scope_basis": "repos.csv:repo_primary_language",
                "matching_row_available": matching_available,
                "matched_control_slots_nonempty": nonempty_slots,
                "paper_panel_rows": len(treatment_group),
                "event_yyyymm": int(event_series.iloc[0]),
                "eligible_for_python_scope_clone": True,
                "included_in_clone_manifest": True,
                "matching_scope_status": (
                    "pair_available_in_matching_csv"
                    if matching_available
                    else "treatment_absent_from_matching_csv"
                ),
                "clone_exclusion_reason": "",
            }
        )

    treatment_repos = pd.DataFrame(treatment_rows)
    slot_audit = pd.DataFrame(slot_rows)

    if slot_audit.empty:
        paper_control_keys: set[str] = set()
    else:
        paper_control_keys = set(
            slot_audit.loc[
                slot_audit["selected_in_paper_python_setting"],
                "control_repo_key",
            ]
        )

    control_panel = paper_event_scope[
        paper_event_scope["paper_role"].eq("control")
        & paper_event_scope["repo_name_key"].isin(paper_control_keys)
    ].copy()
    control_rows: list[dict[str, object]] = []
    for control_key, group in control_panel.groupby("repo_name_key", sort=True):
        control_name = panel_name_map.get(
            control_key, metadata_name_map.get(control_key, control_key)
        )
        control_language = normalize_language(
            metadata_language_map.get(control_key, "")
        )
        linked = slot_audit[
            slot_audit["control_repo_key"].eq(control_key)
            & slot_audit["selected_in_paper_python_setting"]
        ]
        control_rows.append(
            {
                "repo_name": control_name,
                "repo_name_key": control_key,
                "repo_primary_language_metadata": control_language,
                "language_metadata_available": bool(control_language),
                "language_scope_basis": "matched_control_of_python_treatment",
                "paper_panel_rows": len(group),
                "matched_slot_count": len(linked),
                "linked_treatment_count": linked["treatment_repo_key"].nunique(),
                "linked_treatment_repos": ";".join(
                    sorted(linked["treatment_repo_name"].unique())
                ),
                "eligible_for_python_scope_clone": True,
            }
        )
    control_repos = pd.DataFrame(control_rows)

    scope_issues = pd.DataFrame(
        missing_matching_rows,
        columns=["issue_type", "repo_name", "repo_name_key", "detail"],
    )
    return (
        treatment_repos,
        control_repos,
        slot_audit,
        duplicated_treatment_matching,
        scope_issues,
    )

def build_clone_manifest(
    treatments: pd.DataFrame,
    controls: pd.DataFrame,
    treatment_clone_root: Path,
    control_clone_root: Path,
) -> pd.DataFrame:
    """Create clone targets for matched Python treatments and their controls."""
    rows: list[dict[str, object]] = []

    for _, row in treatments.sort_values("repo_name_key").iterrows():
        rows.append(
            {
                "scope_role": "treatment",
                "repo_name": row["repo_name"],
                "repo_name_key": row["repo_name_key"],
                "repo_primary_language": row["repo_primary_language"],
                "language_scope_basis": row["language_scope_basis"],
                "clone_root": str(treatment_clone_root),
                "expected_clone_directory": clone_directory_name(row["repo_name"]),
                "expected_clone_path": str(
                    treatment_clone_root / clone_directory_name(row["repo_name"])
                ),
                "clone_url": f"https://github.com/{row['repo_name']}.git",
                "repo_name_format_valid": validate_repo_name(row["repo_name"]),
                "matching_row_available": bool(row.get("matching_row_available", False)),
                "matching_scope_status": row.get(
                    "matching_scope_status", "pair_available_in_matching_csv"
                ),
                "analysis_inclusion_basis": "appendix_python_treatment",
            }
        )

    for _, row in controls.sort_values("repo_name_key").iterrows():
        rows.append(
            {
                "scope_role": "control",
                "repo_name": row["repo_name"],
                "repo_name_key": row["repo_name_key"],
                "repo_primary_language": row[
                    "repo_primary_language_metadata"
                ],
                "language_scope_basis": row["language_scope_basis"],
                "clone_root": str(control_clone_root),
                "expected_clone_directory": clone_directory_name(row["repo_name"]),
                "expected_clone_path": str(
                    control_clone_root / clone_directory_name(row["repo_name"])
                ),
                "clone_url": f"https://github.com/{row['repo_name']}.git",
                "repo_name_format_valid": validate_repo_name(row["repo_name"]),
            }
        )

    return pd.DataFrame(rows)

def inspect_clone_manifest(
    manifest: pd.DataFrame,
    treatment_clone_root: Path,
    control_clone_root: Path,
    enabled: bool,
) -> pd.DataFrame:
    if manifest.empty:
        return manifest.copy()

    root_indexes: dict[str, tuple[dict[str, list[Path]], dict[str, list[Path]]]] = {}
    if enabled:
        root_indexes["treatment"] = build_clone_indexes(treatment_clone_root)
        root_indexes["control"] = build_clone_indexes(control_clone_root)

    rows: list[dict[str, object]] = []
    for _, row in manifest.iterrows():
        role = row["scope_role"]
        root = treatment_clone_root if role == "treatment" else control_clone_root
        if enabled:
            by_name, by_origin = root_indexes[role]
            inspection = inspect_local_clone(
                row["repo_name"], root, by_name, by_origin
            )
        else:
            inspection = CloneInspection(
                clone_path=str(root / clone_directory_name(row["repo_name"])),
                path_exists=False,
                path_is_directory=False,
                is_git_repository=False,
                head_resolves=False,
                origin_url="",
                origin_repo_name="",
                origin_matches_expected=None,
                local_status="local_inspection_disabled",
                local_reason="Local clone inspection was disabled by argument.",
                match_method="not_run",
            )
        record = row.to_dict()
        record.update(dataclasses.asdict(inspection))
        record["clone_ready"] = inspection.local_status == "available"
        record["needs_clone_or_repair"] = inspection.local_status != "available"
        rows.append(record)
    return pd.DataFrame(rows)


def add_qc(
    records: list[dict[str, object]],
    name: str,
    observed: object,
    expected: object,
    status: str,
    note: str = "",
) -> None:
    records.append(
        {
            "check_name": name,
            "status": status,
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def bool_status(condition: bool, failure: str = "fail") -> str:
    return "pass" if condition else failure


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    logging.info("Wrote %d rows to %s", len(frame), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    matching_path = Path(args.matching_file)
    repos_path = Path(args.repos_file)
    panel_path = Path(args.panel_file)
    for label, path in (
        ("matching.csv", matching_path),
        ("repos.csv", repos_path),
        ("panel_event_monthly.csv", panel_path),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")

    output_dir = Path(args.output_dir)
    summary_path = Path(args.summary_output)
    treatment_clone_root = Path(args.treatment_clone_dir)
    control_clone_root = Path(args.control_clone_dir)

    logging.info("Reading matching data: %s", matching_path)
    matching = pd.read_csv(matching_path, low_memory=False)
    logging.info("Reading repository metadata: %s", repos_path)
    repos = pd.read_csv(repos_path, low_memory=False)
    logging.info("Reading event panel: %s", panel_path)
    panel = pd.read_csv(panel_path, low_memory=False)

    metadata, metadata_conflicts = build_repo_metadata(repos)
    (
        treatments,
        controls,
        slot_audit,
        duplicated_treatment_matching,
        scope_issues,
    ) = build_paper_python_scope(
        matching=matching,
        metadata=metadata,
        panel=panel,
        target_language=args.target_language,
        min_event=args.min_treatment_event,
        max_event=args.max_treatment_event,
    )

    appendix_treatments = treatments.copy()
    matched_treatments = treatments[
        treatments["matching_row_available"].astype(bool)
    ].copy()
    unmatched_treatments = treatments[
        ~treatments["matching_row_available"].astype(bool)
    ].copy()
    if not unmatched_treatments.empty:
        unmatched_treatments["exclusion_reason"] = ""
        unmatched_treatments["matching_scope_status"] = (
            "treatment_absent_from_matching_csv"
        )
        unmatched_treatments["included_in_clone_manifest"] = True
        unmatched_treatments["analysis_inclusion_basis"] = (
            "appendix_python_treatment"
        )

    clone_manifest = build_clone_manifest(
        treatments=appendix_treatments,
        controls=controls,
        treatment_clone_root=treatment_clone_root,
        control_clone_root=control_clone_root,
    )
    clone_availability = inspect_clone_manifest(
        manifest=clone_manifest,
        treatment_clone_root=treatment_clone_root,
        control_clone_root=control_clone_root,
        enabled=bool(args.inspect_local_clones),
    )

    # Control language metadata is not required by the paper's language-setting
    # construction. This output is reserved for unresolved treatment-language
    # metadata; selected treatments have already been verified as Python.
    language_unresolved = treatments[
        treatments["repo_primary_language"].map(language_key).ne(
            language_key(args.target_language)
        )
    ].copy()
    if not language_unresolved.empty:
        language_unresolved["unresolved_reason"] = (
            "treatment_primary_language_not_target"
        )

    treatment_count = appendix_treatments["repo_name_key"].nunique()
    matched_treatment_count = matched_treatments["repo_name_key"].nunique()
    paper_control_count = controls["repo_name_key"].nunique()
    eligible_control_count = paper_control_count
    treatment_without_matching_count = unmatched_treatments[
        "repo_name_key"
    ].nunique()
    clone_treatment_count = int(
        clone_manifest["scope_role"].eq("treatment").sum()
    )
    clone_control_count = int(clone_manifest["scope_role"].eq("control").sum())

    qc_records: list[dict[str, object]] = []
    add_qc(
        qc_records,
        "paper_python_treatment_repositories",
        treatment_count,
        args.expected_paper_treatment_repos,
        bool_status(
            treatment_count == args.expected_paper_treatment_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "Appendix Table 7 reports the Python treatment-repository count.",
    )
    add_qc(
        qc_records,
        "matched_python_treatment_repositories",
        matched_treatment_count,
        args.expected_matched_treatment_repos,
        bool_status(
            matched_treatment_count == args.expected_matched_treatment_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "Python treatments with recoverable assignments in matching.csv.",
    )
    add_qc(
        qc_records,
        "paper_python_control_repositories",
        paper_control_count,
        args.expected_paper_control_repos,
        bool_status(
            paper_control_count == args.expected_paper_control_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "Appendix Table 7 reports the Python control-repository count.",
    )
    add_qc(
        qc_records,
        "treatment_language_mismatches",
        int(
            (~treatments["repo_primary_language"].map(language_key).eq(
                language_key(args.target_language)
            )).sum()
        ),
        0,
        bool_status(
            treatments["repo_primary_language"].map(language_key).eq(
                language_key(args.target_language)
            ).all()
        ),
    )
    add_qc(
        qc_records,
        "control_language_metadata_missing_in_repos_csv",
        int((~controls["language_metadata_available"]).sum()),
        "informational",
        "info",
        (
            "Control inclusion is based on being matched to a Python treatment; "
            "repos.csv language metadata is not required for controls."
        ),
    )
    add_qc(
        qc_records,
        "python_treatments_without_matching_rows",
        treatment_without_matching_count,
        args.expected_treatment_repos_without_matching,
        bool_status(
            treatment_without_matching_count
            == args.expected_treatment_repos_without_matching,
            "fail" if args.strict_expected_counts else "warn",
        ),
        (
            "These treatments are retained in the Appendix-faithful clone "
            "manifest and DiD sample, while missing pair provenance is audited."
        ),
    )
    add_qc(
        qc_records,
        "duplicate_treatment_rows_in_matching",
        len(duplicated_treatment_matching),
        0,
        bool_status(duplicated_treatment_matching.empty),
    )
    add_qc(
        qc_records,
        "conflicting_repo_language_metadata",
        len(metadata_conflicts),
        0,
        bool_status(metadata_conflicts.empty),
    )
    add_qc(
        qc_records,
        "paper_scope_issue_rows",
        len(scope_issues),
        args.expected_treatment_repos_without_matching,
        bool_status(
            len(scope_issues) == args.expected_treatment_repos_without_matching,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "Expected audit rows for Python treatments absent from matching.csv.",
    )
    add_qc(
        qc_records,
        "clone_manifest_treatment_repositories",
        clone_treatment_count,
        args.expected_paper_treatment_repos,
        bool_status(
            clone_treatment_count == args.expected_paper_treatment_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "All Appendix Python treatments are clone targets, including seven without matching.csv treatment rows.",
    )
    add_qc(
        qc_records,
        "clone_manifest_control_repositories",
        clone_control_count,
        args.expected_paper_control_repos,
        bool_status(
            clone_control_count == args.expected_paper_control_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
    )
    add_qc(
        qc_records,
        "clone_manifest_total_repositories",
        len(clone_manifest),
        args.expected_clone_target_repos,
        bool_status(
            len(clone_manifest) == args.expected_clone_target_repos,
            "fail" if args.strict_expected_counts else "warn",
        ),
        "All Appendix Python treatments plus unique matched controls.",
    )
    add_qc(
        qc_records,
        "duplicate_treatment_manifest_repositories",
        int(
            clone_manifest.loc[
                clone_manifest["scope_role"].eq("treatment"), "repo_name_key"
            ].duplicated().sum()
        ),
        0,
        bool_status(
            not clone_manifest.loc[
                clone_manifest["scope_role"].eq("treatment"), "repo_name_key"
            ].duplicated().any()
        ),
    )
    add_qc(
        qc_records,
        "duplicate_control_manifest_repositories",
        int(
            clone_manifest.loc[
                clone_manifest["scope_role"].eq("control"), "repo_name_key"
            ].duplicated().sum()
        ),
        0,
        bool_status(
            not clone_manifest.loc[
                clone_manifest["scope_role"].eq("control"), "repo_name_key"
            ].duplicated().any()
        ),
    )
    role_overlap = set(
        clone_manifest.loc[
            clone_manifest["scope_role"].eq("treatment"), "repo_name_key"
        ]
    ) & set(
        clone_manifest.loc[
            clone_manifest["scope_role"].eq("control"), "repo_name_key"
        ]
    )
    add_qc(
        qc_records,
        "treatment_control_role_overlap",
        len(role_overlap),
        0,
        bool_status(not role_overlap),
    )
    add_qc(
        qc_records,
        "invalid_repository_names_in_clone_manifest",
        int((~clone_manifest["repo_name_format_valid"]).sum()),
        0,
        bool_status(clone_manifest["repo_name_format_valid"].all()),
    )
    if args.inspect_local_clones:
        add_qc(
            qc_records,
            "local_clone_origin_mismatches",
            int(
                clone_availability["local_status"]
                .eq("available_origin_mismatch")
                .sum()
            ),
            0,
            bool_status(
                not clone_availability["local_status"]
                .eq("available_origin_mismatch")
                .any(),
                "warn",
            ),
        )
        add_qc(
            qc_records,
            "ambiguous_local_clones",
            int(
                clone_availability["local_status"]
                .eq("ambiguous_local_clone")
                .sum()
            ),
            0,
            bool_status(
                not clone_availability["local_status"]
                .eq("ambiguous_local_clone")
                .any()
            ),
        )

    qc = pd.DataFrame(qc_records)
    hard_failures = int(qc["status"].eq("fail").sum())
    warnings = int(qc["status"].eq("warn").sum())

    counts_rows = [
        ("input", "matching_rows", len(matching), ""),
        (
            "input",
            "matching_treatment_unique_repositories",
            matching.loc[
                matching["group"].astype(str).str.strip().str.casefold().eq("treatment"),
                "repo_name",
            ].map(repo_key).nunique(),
            "",
        ),
        ("input", "repos_metadata_rows", len(repos), ""),
        ("input", "panel_rows", len(panel), ""),
        ("paper_python_setting", "appendix_treatment_repositories", treatment_count, ""),
        (
            "strict_matched_scope",
            "matched_treatment_repositories",
            matched_treatment_count,
            "Treatment rows available in matching.csv.",
        ),
        ("paper_python_setting", "control_repositories", paper_control_count, ""),
        (
            "paper_python_setting",
            "matched_control_slots",
            int(slot_audit["selected_in_paper_python_setting"].sum()),
            "",
        ),
        (
            "scope_construction",
            "matched_controls_selected_for_python_treatments",
            eligible_control_count,
            "Control language metadata is not required by the paper logic.",
        ),
        (
            "scope_construction",
            "python_treatments_without_matching_rows",
            treatment_without_matching_count,
            "Included in the clone manifest and DiD treatment sample; pair provenance unavailable.",
        ),
        (
            "metadata_diagnostic",
            "control_language_metadata_missing_in_repos_csv",
            int((~controls["language_metadata_available"]).sum()),
            "Informational only.",
        ),
        ("clone_manifest", "treatment_repositories", clone_treatment_count, ""),
        ("clone_manifest", "control_repositories", clone_control_count, ""),
        (
            "clone_manifest",
            "total_repositories",
            len(clone_manifest),
            "All Appendix Python treatments and the paper-selected control pool.",
        ),
    ]
    if args.inspect_local_clones:
        for role in ("treatment", "control"):
            subset = clone_availability[clone_availability["scope_role"].eq(role)]
            counts_rows.extend(
                [
                    (
                        "local_clone_coverage",
                        f"{role}_available",
                        int(subset["local_status"].eq("available").sum()),
                        "",
                    ),
                    (
                        "local_clone_coverage",
                        f"{role}_needs_clone_or_repair",
                        int((~subset["local_status"].eq("available")).sum()),
                        "",
                    ),
                ]
            )
    counts = pd.DataFrame(
        counts_rows, columns=["section", "metric", "value", "note"]
    )

    output_paths = {
        "treatments": output_dir / "python_primary_treatment_repos.csv",
        "matched_treatments": output_dir
        / "python_primary_matched_treatment_repos.csv",
        "unmatched_treatments": output_dir
        / "python_primary_treatments_absent_from_matching.csv",
        "controls": output_dir / "python_primary_matched_control_repos.csv",
        "manifest": output_dir / "python_primary_clone_manifest.csv",
        "language_audit": output_dir / "python_primary_matching_language_audit.csv",
        "language_unresolved": output_dir
        / "python_primary_language_metadata_unresolved.csv",
        "clone_availability": output_dir
        / "python_primary_clone_availability_audit.csv",
        "counts": output_dir / "python_primary_repo_counts.csv",
        "qc": output_dir / "python_primary_manifest_qc.csv",
        "metadata_conflicts": output_dir
        / "python_primary_repo_metadata_conflicts.csv",
        "scope_issues": output_dir / "python_primary_scope_issues.csv",
    }

    write_csv(appendix_treatments, output_paths["treatments"])
    write_csv(matched_treatments, output_paths["matched_treatments"])
    write_csv(unmatched_treatments, output_paths["unmatched_treatments"])
    write_csv(controls, output_paths["controls"])
    write_csv(clone_manifest, output_paths["manifest"])
    write_csv(slot_audit, output_paths["language_audit"])
    write_csv(language_unresolved, output_paths["language_unresolved"])
    write_csv(clone_availability, output_paths["clone_availability"])
    write_csv(counts, output_paths["counts"])
    write_csv(qc, output_paths["qc"])
    write_csv(metadata_conflicts, output_paths["metadata_conflicts"])
    write_csv(scope_issues, output_paths["scope_issues"])

    summary_rows = [
        ("implementation", "version", IMPLEMENTATION_VERSION, ""),
        ("definition", "target_language", args.target_language, ""),
        (
            "definition",
            "paper_event_window",
            f"{args.min_treatment_event}:{args.max_treatment_event}",
            "Controls are represented by event=0.",
        ),
        (
            "definition",
            "clone_policy",
            "appendix_python_treatments_and_paper_controls",
            (
                "All Appendix Python treatments enter the clone manifest; "
                "seven lack treatment rows in matching.csv and are explicitly audited."
            ),
        ),
        ("input_sha256", "matching_file", sha256_file(matching_path), str(matching_path)),
        ("input_sha256", "repos_file", sha256_file(repos_path), str(repos_path)),
        ("input_sha256", "panel_file", sha256_file(panel_path), str(panel_path)),
    ]
    summary_rows.extend(counts_rows)
    summary_rows.extend(
        [
            ("qc", "hard_failures", hard_failures, ""),
            ("qc", "warnings", warnings, ""),
        ]
    )
    summary = pd.DataFrame(
        summary_rows, columns=["section", "metric", "value", "note"]
    )
    write_csv(summary, summary_path)

    logging.info(
        "Completed run-x-c01-%s: Appendix treatments=%d; matched treatments=%d; "
        "paper controls=%d; clone treatments=%d; clone controls=%d; "
        "hard failures=%d; warnings=%d",
        IMPLEMENTATION_VERSION,
        treatment_count,
        matched_treatment_count,
        paper_control_count,
        clone_treatment_count,
        clone_control_count,
        hard_failures,
        warnings,
    )

    if hard_failures:
        logging.error("C01 produced %d hard QC failure(s).", hard_failures)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover - top-level execution guard
        logging.exception("run-x-c01 failed: %s", exc)
        sys.exit(1)
