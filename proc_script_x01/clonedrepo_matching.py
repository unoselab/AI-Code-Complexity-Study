#!/usr/bin/env python3
"""
Audit alignment between the paper's matching.csv and locally cloned repositories.

The audit is scoped to the repositories currently cloned under the treatment clone
root. For each cloned treatment repository, the script finds its treatment row in
matching.csv, expands matched_control_1 through matched_control_3, and checks whether
the corresponding control repositories are present as valid Git repositories under
the control clone root.

Inputs:
- matching.csv from the paper replication package
- treatment clone directory
- control clone directory

Outputs:
- repository-level alignment CSV
- treatment-control pair-level alignment CSV
- summary/QC CSV

The script never modifies repositories, checks out commits, or changes matching.csv.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import pandas as pd


REQUIRED_MATCHING_COLUMNS = {
    "repo_name",
    "matched_period",
    "group",
    "propensity_score",
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
}
CONTROL_COLUMNS = [
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
]


@dataclass(frozen=True)
class CloneRecord:
    """Metadata discovered for one immediate child of a clone root."""

    role: str
    repo_name: Optional[str]
    clone_dir_name: str
    clone_path: str
    is_git_repository: bool
    origin_url: str
    repo_name_source: str
    identity_status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether cloned treatment and control repositories align with "
            "the treatment-control assignments in matching.csv."
        )
    )
    parser.add_argument("--matching-file", required=True, type=Path)
    parser.add_argument("--treatment-clone-dir", required=True, type=Path)
    parser.add_argument("--control-clone-dir", required=True, type=Path)
    parser.add_argument("--alignment-output", required=True, type=Path)
    parser.add_argument("--pairs-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help=(
            "Return exit code 2 when cloned treatments are missing from matching.csv, "
            "expected controls are missing, clone identities are unresolved, or clone "
            "directories are not valid Git repositories."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def normalize_repo_key(repo_name: object) -> Optional[str]:
    """Return a case-insensitive key for an owner/repository value."""
    if repo_name is None or pd.isna(repo_name):
        return None
    value = str(repo_name).strip().strip("/")
    if not value:
        return None
    return value.casefold()


def expected_dir_name(repo_name: str) -> str:
    """Convert owner/repository to the clone directory convention owner_repository."""
    return repo_name.replace("/", "_")


def run_git(repo_path: Path, args: list[str]) -> tuple[bool, str]:
    """Run a read-only Git command and return success plus stripped stdout."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return True, completed.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logging.debug("Git command failed for %s: %s", repo_path, exc)
        return False, ""


def parse_github_repo_from_origin(origin_url: str) -> Optional[str]:
    """Parse owner/repository from common GitHub HTTPS and SSH remote URL forms."""
    value = origin_url.strip()
    if not value:
        return None

    scp_match = re.match(r"^(?:[^@]+@)?github\.com:(?P<path>[^\s]+)$", value)
    if scp_match:
        path = scp_match.group("path")
    else:
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        if host != "github.com":
            return None
        path = parsed.path

    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def build_canonical_map(
    repo_names: Iterable[str],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Build a display-name map without rejecting case-only source-data variants.

    GitHub repository identity is case-insensitive, but the replication package can
    contain the same repository with different capitalization in different cohort
    files. A case-only variation is therefore recorded as a source-data collision,
    not treated as a fatal program error.

    Keys with exactly one spelling are added to the canonical map. Keys with more
    than one spelling are omitted so clone identities discovered from an origin URL
    keep their original spelling instead of being rewritten arbitrarily.
    """
    spellings_by_key: dict[str, set[str]] = {}

    for repo_name in repo_names:
        key = normalize_repo_key(repo_name)
        if key is None:
            continue
        value = str(repo_name).strip()
        spellings_by_key.setdefault(key, set()).add(value)

    canonical: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for key, spellings in spellings_by_key.items():
        ordered_spellings = sorted(spellings, key=lambda value: (value.casefold(), value))
        if len(ordered_spellings) == 1:
            canonical[key] = ordered_spellings[0]
        else:
            collisions[key] = ordered_spellings

    if collisions:
        examples = "; ".join(
            f"{key}: {values}" for key, values in list(collisions.items())[:5]
        )
        logging.warning(
            "matching.csv contains %d case-insensitive repository-name collision "
            "key(s); continuing with case-insensitive identity matching. Examples: %s",
            len(collisions),
            examples,
        )

    return canonical, collisions


def build_dir_name_candidates(repo_names: Iterable[str]) -> dict[str, list[str]]:
    """Build a fallback map from expected clone directory names to repository names."""
    result: dict[str, list[str]] = {}
    for repo_name in repo_names:
        value = str(repo_name).strip()
        if not value:
            continue
        result.setdefault(expected_dir_name(value), []).append(value)
    return result


def scan_clone_root(
    clone_root: Path,
    role: str,
    canonical_map: dict[str, str],
    dir_name_candidates: dict[str, list[str]],
) -> list[CloneRecord]:
    """Inspect immediate children of a clone root without modifying repositories."""
    records: list[CloneRecord] = []

    for child in sorted(clone_root.iterdir(), key=lambda path: path.name.casefold()):
        if not child.is_dir():
            continue

        git_ok, inside_work_tree = run_git(child, ["rev-parse", "--is-inside-work-tree"])
        is_git_repository = git_ok and inside_work_tree == "true"

        origin_url = ""
        parsed_repo_name: Optional[str] = None
        repo_name_source = "unresolved"
        identity_status = "unresolved"

        if is_git_repository:
            origin_ok, origin_url = run_git(child, ["remote", "get-url", "origin"])
            if origin_ok:
                parsed_repo_name = parse_github_repo_from_origin(origin_url)
                if parsed_repo_name:
                    repo_name_source = "origin_url"
                    identity_status = "resolved"

        if parsed_repo_name is None:
            candidates = dir_name_candidates.get(child.name, [])
            if len(candidates) == 1:
                parsed_repo_name = candidates[0]
                repo_name_source = "directory_name_fallback"
                identity_status = "resolved"
            elif len(candidates) > 1:
                repo_name_source = "directory_name_ambiguous"
                identity_status = "ambiguous"

        if parsed_repo_name is not None:
            key = normalize_repo_key(parsed_repo_name)
            if key in canonical_map:
                parsed_repo_name = canonical_map[key]

        if not is_git_repository:
            identity_status = "not_git_repository"

        records.append(
            CloneRecord(
                role=role,
                repo_name=parsed_repo_name,
                clone_dir_name=child.name,
                clone_path=str(child.resolve()),
                is_git_repository=is_git_repository,
                origin_url=origin_url,
                repo_name_source=repo_name_source,
                identity_status=identity_status,
            )
        )

    return records


def records_to_dataframe(records: list[CloneRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "role": record.role,
                "repo_name": record.repo_name,
                "clone_dir_name": record.clone_dir_name,
                "clone_path": record.clone_path,
                "is_git_repository": record.is_git_repository,
                "origin_url": record.origin_url,
                "repo_name_source": record.repo_name_source,
                "identity_status": record.identity_status,
                "repo_key": normalize_repo_key(record.repo_name),
            }
            for record in records
        ]
    )


def validate_matching_file(matching_df: pd.DataFrame) -> None:
    missing_columns = sorted(REQUIRED_MATCHING_COLUMNS - set(matching_df.columns))
    if missing_columns:
        raise ValueError(
            "matching.csv is missing required columns: " + ", ".join(missing_columns)
        )

    groups = set(matching_df["group"].dropna().astype(str).str.strip().str.casefold())
    if "treatment" not in groups:
        raise ValueError("matching.csv does not contain group='treatment' rows")


def ensure_unique_treatment_rows(treatment_df: pd.DataFrame) -> None:
    duplicate_mask = treatment_df["repo_key"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = sorted(
            treatment_df.loc[duplicate_mask, "repo_name"].astype(str).unique().tolist()
        )
        raise ValueError(
            "matching.csv contains duplicate treatment rows for repositories: "
            + ", ".join(duplicates[:20])
        )


def make_pairs(
    treatment_clone_df: pd.DataFrame,
    treatment_matching_df: pd.DataFrame,
    control_clone_df: pd.DataFrame,
) -> pd.DataFrame:
    """Expand the three matching slots for cloned treatment repositories."""
    treatment_lookup = treatment_matching_df.set_index("repo_key", drop=False)
    control_clone_lookup = {
        row.repo_key: row
        for row in control_clone_df.itertuples(index=False)
        if row.repo_key is not None
    }

    rows: list[dict[str, object]] = []
    for clone in treatment_clone_df.itertuples(index=False):
        if clone.repo_key is None or clone.repo_key not in treatment_lookup.index:
            continue

        match_row = treatment_lookup.loc[clone.repo_key]
        if isinstance(match_row, pd.DataFrame):
            raise ValueError(f"Duplicate matching rows for {clone.repo_name}")

        original_count = int(sum(pd.notna(match_row[column]) for column in CONTROL_COLUMNS))
        for rank, column in enumerate(CONTROL_COLUMNS, start=1):
            control_repo = match_row[column]
            control_repo = None if pd.isna(control_repo) else str(control_repo).strip()
            control_key = normalize_repo_key(control_repo)
            control_clone = control_clone_lookup.get(control_key)

            if control_repo is None:
                pair_status = "missing_control_in_matching_slot"
            elif control_clone is None:
                pair_status = "control_clone_missing"
            elif not bool(control_clone.is_git_repository):
                pair_status = "control_clone_not_git"
            else:
                pair_status = "aligned"

            rows.append(
                {
                    "treatment_repo": str(match_row["repo_name"]),
                    "treatment_clone_dir_name": clone.clone_dir_name,
                    "treatment_clone_path": clone.clone_path,
                    "treatment_is_git_repository": bool(clone.is_git_repository),
                    "matched_period": match_row["matched_period"],
                    "propensity_score": match_row["propensity_score"],
                    "original_matched_control_count": original_count,
                    "control_rank": rank,
                    "control_repo": control_repo,
                    "control_clone_found": control_clone is not None,
                    "control_clone_dir_name": (
                        control_clone.clone_dir_name if control_clone is not None else ""
                    ),
                    "control_clone_path": (
                        control_clone.clone_path if control_clone is not None else ""
                    ),
                    "control_is_git_repository": (
                        bool(control_clone.is_git_repository)
                        if control_clone is not None
                        else False
                    ),
                    "pair_status": pair_status,
                }
            )

    pairs_df = pd.DataFrame(rows)
    if pairs_df.empty:
        return pd.DataFrame(
            columns=[
                "treatment_repo",
                "treatment_clone_dir_name",
                "treatment_clone_path",
                "treatment_is_git_repository",
                "matched_period",
                "propensity_score",
                "original_matched_control_count",
                "control_rank",
                "control_repo",
                "control_clone_found",
                "control_clone_dir_name",
                "control_clone_path",
                "control_is_git_repository",
                "pair_status",
            ]
        )

    return pairs_df.sort_values(
        ["treatment_repo", "control_rank"], key=lambda col: col.astype(str).str.casefold()
    ).reset_index(drop=True)


def make_alignment(
    treatment_clone_df: pd.DataFrame,
    control_clone_df: pd.DataFrame,
    treatment_matching_df: pd.DataFrame,
    matching_control_candidate_keys: set[str],
    expected_control_names: dict[str, str],
) -> pd.DataFrame:
    """Create one repository-level alignment row per in-scope or cloned repository."""
    treatment_matching_keys = set(treatment_matching_df["repo_key"].dropna())
    treatment_clone_lookup = {
        row.repo_key: row
        for row in treatment_clone_df.itertuples(index=False)
        if row.repo_key is not None
    }
    control_clone_lookup = {
        row.repo_key: row
        for row in control_clone_df.itertuples(index=False)
        if row.repo_key is not None
    }

    rows: list[dict[str, object]] = []

    for clone in treatment_clone_df.itertuples(index=False):
        key = clone.repo_key
        in_matching = key in treatment_matching_keys if key is not None else False

        if key is None:
            status = "unresolved_clone_identity"
        elif not bool(clone.is_git_repository):
            status = "clone_not_git"
        elif not in_matching:
            status = "clone_not_in_matching_treatment"
        else:
            status = "aligned"

        rows.append(
            {
                "role": "treatment",
                "repo_name": clone.repo_name,
                "repo_dir_name_expected": (
                    expected_dir_name(clone.repo_name) if clone.repo_name else ""
                ),
                "expected_for_current_scope": in_matching,
                "in_matching_treatment_rows": in_matching,
                "in_matching_control_candidate_rows": False,
                "selected_by_cloned_treatment": False,
                "in_clone_directory": True,
                "is_git_repository": bool(clone.is_git_repository),
                "clone_dir_name": clone.clone_dir_name,
                "clone_path": clone.clone_path,
                "origin_url": clone.origin_url,
                "repo_name_source": clone.repo_name_source,
                "alignment_status": status,
            }
        )

    expected_control_keys = set(expected_control_names)
    all_control_keys = expected_control_keys | set(control_clone_lookup)

    for key in sorted(all_control_keys):
        clone = control_clone_lookup.get(key)
        repo_name = expected_control_names.get(key)
        if repo_name is None and clone is not None:
            repo_name = clone.repo_name

        expected = key in expected_control_keys
        in_candidate_rows = key in matching_control_candidate_keys

        if clone is None:
            status = "expected_control_clone_missing"
        elif clone.repo_key is None:
            status = "unresolved_clone_identity"
        elif not bool(clone.is_git_repository):
            status = "clone_not_git"
        elif not expected:
            status = "extra_control_clone_not_selected"
        else:
            status = "aligned"

        rows.append(
            {
                "role": "control",
                "repo_name": repo_name,
                "repo_dir_name_expected": expected_dir_name(repo_name) if repo_name else "",
                "expected_for_current_scope": expected,
                "in_matching_treatment_rows": False,
                "in_matching_control_candidate_rows": in_candidate_rows,
                "selected_by_cloned_treatment": expected,
                "in_clone_directory": clone is not None,
                "is_git_repository": (
                    bool(clone.is_git_repository) if clone is not None else False
                ),
                "clone_dir_name": clone.clone_dir_name if clone is not None else "",
                "clone_path": clone.clone_path if clone is not None else "",
                "origin_url": clone.origin_url if clone is not None else "",
                "repo_name_source": (
                    clone.repo_name_source if clone is not None else "not_applicable"
                ),
                "alignment_status": status,
            }
        )

    alignment_df = pd.DataFrame(rows)
    if alignment_df.empty:
        return alignment_df

    return alignment_df.sort_values(
        ["role", "repo_name", "clone_dir_name"],
        key=lambda col: col.fillna("").astype(str).str.casefold(),
    ).reset_index(drop=True)


def add_summary_row(
    rows: list[dict[str, object]],
    section: str,
    metric: str,
    value: object,
    note: str = "",
) -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def make_summary(
    matching_df: pd.DataFrame,
    treatment_matching_df: pd.DataFrame,
    treatment_clone_df: pd.DataFrame,
    control_clone_df: pd.DataFrame,
    pairs_df: pd.DataFrame,
    alignment_df: pd.DataFrame,
    case_collisions: dict[str, list[str]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    add_summary_row(rows, "input", "matching_rows", len(matching_df))
    add_summary_row(
        rows,
        "input",
        "matching_treatment_rows",
        int((matching_df["group"].astype(str).str.casefold() == "treatment").sum()),
    )
    add_summary_row(
        rows,
        "input",
        "matching_control_candidate_rows",
        int((matching_df["group"].astype(str).str.casefold() == "control").sum()),
    )
    add_summary_row(
        rows,
        "input",
        "case_insensitive_repo_name_collision_keys",
        len(case_collisions),
        (
            "Case-only repository-name variants are treated as the same GitHub "
            "repository identity and do not stop the alignment audit."
        ),
    )
    if case_collisions:
        collision_note = "; ".join(
            f"{key}: {values}" for key, values in list(case_collisions.items())[:10]
        )
        add_summary_row(
            rows,
            "input",
            "case_insensitive_repo_name_collision_examples",
            collision_note,
            "Up to 10 collision keys are shown.",
        )

    add_summary_row(rows, "treatment", "clone_directories", len(treatment_clone_df))
    add_summary_row(
        rows,
        "treatment",
        "valid_git_repositories",
        int(treatment_clone_df["is_git_repository"].sum()),
    )
    add_summary_row(
        rows,
        "treatment",
        "resolved_repository_names",
        int(treatment_clone_df["repo_key"].notna().sum()),
    )
    matched_treatment_keys = set(treatment_matching_df["repo_key"].dropna())
    add_summary_row(
        rows,
        "treatment",
        "cloned_treatments_found_in_matching",
        int(treatment_clone_df["repo_key"].isin(matched_treatment_keys).sum()),
    )
    add_summary_row(
        rows,
        "treatment",
        "cloned_treatments_missing_from_matching",
        int((~treatment_clone_df["repo_key"].isin(matched_treatment_keys)).sum()),
    )

    add_summary_row(rows, "control", "clone_directories", len(control_clone_df))
    add_summary_row(
        rows,
        "control",
        "valid_git_repositories",
        int(control_clone_df["is_git_repository"].sum()),
    )
    add_summary_row(
        rows,
        "control",
        "resolved_repository_names",
        int(control_clone_df["repo_key"].notna().sum()),
    )

    if pairs_df.empty:
        pair_status_counts: dict[str, int] = {}
        expected_slots = 0
        nonempty_slots = 0
        unique_expected_controls = 0
        aligned_slots = 0
    else:
        pair_status_counts = pairs_df["pair_status"].value_counts().to_dict()
        expected_slots = len(pairs_df)
        nonempty_slots = int(pairs_df["control_repo"].notna().sum())
        unique_expected_controls = int(pairs_df["control_repo"].dropna().nunique())
        aligned_slots = int((pairs_df["pair_status"] == "aligned").sum())

    add_summary_row(rows, "pair", "matching_slots_checked", expected_slots)
    add_summary_row(rows, "pair", "nonempty_matching_slots", nonempty_slots)
    add_summary_row(rows, "pair", "unique_expected_controls", unique_expected_controls)
    add_summary_row(rows, "pair", "aligned_matching_slots", aligned_slots)
    for status, count in sorted(pair_status_counts.items()):
        add_summary_row(rows, "pair_status", status, int(count))

    if alignment_df.empty:
        alignment_status_counts: dict[str, int] = {}
    else:
        alignment_status_counts = alignment_df["alignment_status"].value_counts().to_dict()
    for status, count in sorted(alignment_status_counts.items()):
        add_summary_row(rows, "alignment_status", status, int(count))

    add_summary_row(
        rows,
        "scope",
        "definition",
        "cloned_treatments_and_their_matching_controls",
        (
            "The audit does not treat all 840 paper treatments as expected local clones. "
            "It checks the currently cloned treatment subset and the controls assigned "
            "to that subset."
        ),
    )

    return pd.DataFrame(rows)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logging.info("Wrote %s rows to %s", len(df), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    for required_path, label in [
        (args.matching_file, "matching file"),
        (args.treatment_clone_dir, "treatment clone directory"),
        (args.control_clone_dir, "control clone directory"),
    ]:
        if not required_path.exists():
            logging.error("Required %s does not exist: %s", label, required_path)
            return 1

    if not args.treatment_clone_dir.is_dir() or not args.control_clone_dir.is_dir():
        logging.error("Treatment and control clone paths must both be directories")
        return 1

    try:
        matching_df = pd.read_csv(args.matching_file)
        validate_matching_file(matching_df)

        matching_df = matching_df.copy()
        matching_df["group"] = matching_df["group"].astype(str).str.strip().str.casefold()
        matching_df["repo_name"] = matching_df["repo_name"].astype(str).str.strip()
        matching_df["repo_key"] = matching_df["repo_name"].map(normalize_repo_key)

        treatment_matching_df = matching_df[matching_df["group"] == "treatment"].copy()
        ensure_unique_treatment_rows(treatment_matching_df)

        all_matching_repo_names = matching_df["repo_name"].dropna().astype(str).tolist()
        all_control_names = (
            matching_df.loc[matching_df["group"] == "control", "repo_name"]
            .dropna()
            .astype(str)
            .tolist()
        )
        matched_control_names = (
            treatment_matching_df[CONTROL_COLUMNS]
            .stack()
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )

        canonical_map, case_collisions = build_canonical_map(
            all_matching_repo_names + matched_control_names
        )
        treatment_dir_candidates = build_dir_name_candidates(
            treatment_matching_df["repo_name"].tolist()
        )
        control_dir_candidates = build_dir_name_candidates(
            all_control_names + matched_control_names
        )

        treatment_records = scan_clone_root(
            args.treatment_clone_dir,
            "treatment",
            canonical_map,
            treatment_dir_candidates,
        )
        control_records = scan_clone_root(
            args.control_clone_dir,
            "control",
            canonical_map,
            control_dir_candidates,
        )
        treatment_clone_df = records_to_dataframe(treatment_records)
        control_clone_df = records_to_dataframe(control_records)

        duplicate_treatment_keys = treatment_clone_df[
            treatment_clone_df["repo_key"].notna()
            & treatment_clone_df["repo_key"].duplicated(keep=False)
        ]
        duplicate_control_keys = control_clone_df[
            control_clone_df["repo_key"].notna()
            & control_clone_df["repo_key"].duplicated(keep=False)
        ]
        if not duplicate_treatment_keys.empty or not duplicate_control_keys.empty:
            raise ValueError(
                "Multiple clone directories resolve to the same repository name. "
                "Review clone roots before continuing."
            )

        pairs_df = make_pairs(
            treatment_clone_df,
            treatment_matching_df,
            control_clone_df,
        )

        expected_control_names = {
            normalize_repo_key(repo_name): repo_name
            for repo_name in pairs_df["control_repo"].dropna().astype(str)
            if normalize_repo_key(repo_name) is not None
        }
        matching_control_candidate_keys = set(
            matching_df.loc[matching_df["group"] == "control", "repo_key"].dropna()
        )

        alignment_df = make_alignment(
            treatment_clone_df,
            control_clone_df,
            treatment_matching_df,
            matching_control_candidate_keys,
            expected_control_names,
        )
        summary_df = make_summary(
            matching_df,
            treatment_matching_df,
            treatment_clone_df,
            control_clone_df,
            pairs_df,
            alignment_df,
            case_collisions,
        )

        write_csv(alignment_df, args.alignment_output)
        write_csv(pairs_df, args.pairs_output)
        write_csv(summary_df, args.summary_output)

        mismatch_statuses = {
            "clone_not_in_matching_treatment",
            "expected_control_clone_missing",
            "clone_not_git",
            "unresolved_clone_identity",
        }
        mismatch_count = int(
            alignment_df["alignment_status"].isin(mismatch_statuses).sum()
        )

        logging.info("Treatment clone directories: %d", len(treatment_clone_df))
        logging.info("Control clone directories: %d", len(control_clone_df))
        logging.info(
            "Cloned treatments found in matching.csv: %d",
            int(
                treatment_clone_df["repo_key"].isin(
                    set(treatment_matching_df["repo_key"].dropna())
                ).sum()
            ),
        )
        logging.info(
            "Expected unique controls for cloned treatments: %d",
            len(expected_control_names),
        )
        logging.info(
            "Aligned treatment-control slots: %d/%d",
            int((pairs_df["pair_status"] == "aligned").sum()) if not pairs_df.empty else 0,
            int(pairs_df["control_repo"].notna().sum()) if not pairs_df.empty else 0,
        )
        logging.info("Repository-level critical mismatches: %d", mismatch_count)

        if args.fail_on_mismatch and mismatch_count > 0:
            logging.error("Alignment mismatches found and --fail-on-mismatch was enabled")
            return 2

        return 0

    except (ValueError, pd.errors.ParserError, OSError) as exc:
        logging.error("Alignment audit failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
