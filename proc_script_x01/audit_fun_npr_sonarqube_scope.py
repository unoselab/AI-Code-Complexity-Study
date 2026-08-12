#!/usr/bin/env python3
"""
Audit SonarQube Python issue-bearing paths that fall outside the frozen A12
FUN-NPR file universe.

The audit is intentionally outcome-blind with respect to the downstream DiD.
It inspects Git objects at the exact historical commit without checking out or
modifying repositories. The main goal is to determine whether SonarQube paths
outside A12 are filesystem aliases created by tracked symbolic links, tracked
files omitted from A12, path-normalization differences, or unresolved cases.

Inputs
------
1. D02 outside-A12 file-level issue exclusions.
2. Frozen A12 repo-month/file FUN-NPR artifact.
3. Local treatment/control Git clones.

Outputs
-------
- One detailed row per outside-A12 SonarQube path.
- Symlink-chain evidence used to resolve filesystem aliases.
- Snapshot- and repository-level summaries.
- QC checks and a compact summary.
- A pre-specified repository-exclusion sensitivity file for D03/D04.

No SonarScanner run, SonarQube API call, NPR thresholding, or causal outcome
analysis is performed here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import posixpath
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import pandas as pd

SCRIPT_VERSION = "run-x-d02-a-v1"

EXPECTED_OUTSIDE_ROWS_DEFAULT = 124
EXPECTED_OUTSIDE_ISSUES_DEFAULT = 774
EXPECTED_AFFECTED_SNAPSHOTS_DEFAULT = 21
EXPECTED_AFFECTED_REPOSITORIES_DEFAULT = 2

OUTSIDE_REQUIRED = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "component_path",
    "sonar_issue_total",
}
A12_REQUIRED = {
    "snapshot_id",
    "dataset_source",
    "repo_name",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
}


@dataclass(frozen=True)
class GitEntry:
    mode: str
    obj_type: str
    oid: str
    path: str


@dataclass(frozen=True)
class SymlinkHop:
    source_path: str
    target_text: str
    resolved_path_after_hop: str
    source_oid: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outside-a12-file", type=Path)
    parser.add_argument("--a12-file", type=Path)
    parser.add_argument("--d02-checks-file", type=Path)
    parser.add_argument("--d02-summary-file", type=Path)
    parser.add_argument("--treatment-repos-dir", type=Path)
    parser.add_argument("--control-repos-dir", type=Path)
    parser.add_argument("--detail-output", type=Path)
    parser.add_argument("--symlink-evidence-output", type=Path)
    parser.add_argument("--snapshot-summary-output", type=Path)
    parser.add_argument("--repo-summary-output", type=Path)
    parser.add_argument("--sensitivity-spec-output", type=Path)
    parser.add_argument("--checks-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--git-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--expected-outside-rows",
        type=int,
        default=EXPECTED_OUTSIDE_ROWS_DEFAULT,
    )
    parser.add_argument(
        "--expected-outside-issues",
        type=int,
        default=EXPECTED_OUTSIDE_ISSUES_DEFAULT,
    )
    parser.add_argument(
        "--expected-affected-snapshots",
        type=int,
        default=EXPECTED_AFFECTED_SNAPSHOTS_DEFAULT,
    )
    parser.add_argument(
        "--expected-affected-repositories",
        type=int,
        default=EXPECTED_AFFECTED_REPOSITORIES_DEFAULT,
    )
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_file(path: Path | None, label: str) -> Path:
    if path is None or not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def require_dir(path: Path | None, label: str) -> Path:
    if path is None or not path.is_dir():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_git(repo_dir: Path, args: list[str], timeout: int, text: bool = False) -> subprocess.CompletedProcess:
    command = ["git", "-C", str(repo_dir), *args]
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=text,
        timeout=timeout,
    )


def repo_clone_path(dataset_source: str, repo_name: str, treatment_root: Path, control_root: Path) -> Path:
    clone_name = repo_name.replace("/", "_")
    if dataset_source == "treatment":
        return treatment_root / clone_name
    if dataset_source == "control":
        return control_root / clone_name
    raise ValueError(f"Unexpected dataset_source: {dataset_source}")


def normalize_repo_relative(path: str) -> tuple[str | None, str]:
    """Normalize a POSIX path while rejecting absolute or repository-escaping paths."""
    raw = str(path).replace("\\", "/")
    if raw.startswith("/"):
        return None, "absolute_target"
    normalized = posixpath.normpath(raw)
    if normalized == ".":
        normalized = ""
    if normalized == ".." or normalized.startswith("../"):
        return None, "target_escapes_repository"
    return normalized, "ok"


def join_symlink_target(source_path: str, target_text: str, suffix: str) -> tuple[str | None, str]:
    parent = str(PurePosixPath(source_path).parent)
    if parent == ".":
        parent = ""
    target = target_text.strip().replace("\\", "/")
    if target.startswith("/"):
        return None, "absolute_symlink_target"
    combined = posixpath.join(parent, target)
    if suffix:
        combined = posixpath.join(combined, suffix)
    return normalize_repo_relative(combined)


def parse_ls_tree(raw: bytes) -> dict[str, GitEntry]:
    entries: dict[str, GitEntry] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path_bytes = item.split(b"\t", 1)
        mode_b, type_b, oid_b = meta.split(b" ", 2)
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        entries[path] = GitEntry(
            mode=mode_b.decode("ascii"),
            obj_type=type_b.decode("ascii"),
            oid=oid_b.decode("ascii"),
            path=path,
        )
    return entries


def load_tree(repo_dir: Path, commit_sha: str, timeout: int) -> dict[str, GitEntry]:
    result = run_git(repo_dir, ["ls-tree", "-r", "-z", commit_sha], timeout=timeout, text=False)
    return parse_ls_tree(result.stdout)


def read_blob(repo_dir: Path, oid: str, timeout: int) -> bytes:
    result = run_git(repo_dir, ["cat-file", "blob", oid], timeout=timeout, text=False)
    return result.stdout


def blob_sha256(repo_dir: Path, oid: str, timeout: int) -> str:
    return hashlib.sha256(read_blob(repo_dir, oid, timeout)).hexdigest()


def symlink_target_text(repo_dir: Path, entry: GitEntry, timeout: int) -> str:
    return read_blob(repo_dir, entry.oid, timeout).decode("utf-8", errors="replace").strip()


def find_longest_symlink_prefix(path: str, tree: dict[str, GitEntry]) -> GitEntry | None:
    parts = PurePosixPath(path).parts
    candidates: list[GitEntry] = []
    for i in range(1, len(parts) + 1):
        prefix = str(PurePosixPath(*parts[:i]))
        entry = tree.get(prefix)
        if entry is not None and entry.mode == "120000":
            candidates.append(entry)
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(PurePosixPath(item.path).parts))


def suffix_after_prefix(path: str, prefix: str) -> str:
    path_parts = PurePosixPath(path).parts
    prefix_parts = PurePosixPath(prefix).parts
    return str(PurePosixPath(*path_parts[len(prefix_parts):])) if len(path_parts) > len(prefix_parts) else ""


def resolve_through_symlinks(
    repo_dir: Path,
    original_path: str,
    tree: dict[str, GitEntry],
    timeout: int,
    max_hops: int = 8,
) -> tuple[str, list[SymlinkHop], str | None]:
    current = original_path
    hops: list[SymlinkHop] = []
    visited: set[str] = set()
    for _ in range(max_hops):
        if current in visited:
            return current, hops, "symlink_cycle"
        visited.add(current)
        link = find_longest_symlink_prefix(current, tree)
        if link is None:
            return current, hops, None
        target_text = symlink_target_text(repo_dir, link, timeout)
        suffix = suffix_after_prefix(current, link.path)
        resolved, status = join_symlink_target(link.path, target_text, suffix)
        if resolved is None:
            return current, hops, status
        hops.append(
            SymlinkHop(
                source_path=link.path,
                target_text=target_text,
                resolved_path_after_hop=resolved,
                source_oid=link.oid,
            )
        )
        current = resolved
    return current, hops, "symlink_hop_limit"


def load_a12_index(path: Path) -> tuple[dict[str, set[str]], dict[tuple[str, str], str], dict[str, tuple[str, str, str]]]:
    usecols = ["snapshot_id", "dataset_source", "repo_name", "snapshot_commit", "relative_path", "file_sha256"]
    frame = pd.read_csv(path, usecols=usecols, dtype=str, low_memory=False)
    require_columns(frame, A12_REQUIRED, "A12")
    frame = frame.drop_duplicates(subset=["snapshot_id", "relative_path"]).copy()
    paths_by_snapshot: dict[str, set[str]] = defaultdict(set)
    sha_by_key: dict[tuple[str, str], str] = {}
    identity_by_snapshot: dict[str, tuple[str, str, str]] = {}
    for row in frame.itertuples(index=False):
        paths_by_snapshot[row.snapshot_id].add(row.relative_path)
        sha_by_key[(row.snapshot_id, row.relative_path)] = str(row.file_sha256)
        identity = (str(row.dataset_source), str(row.repo_name), str(row.snapshot_commit))
        old = identity_by_snapshot.get(row.snapshot_id)
        if old is not None and old != identity:
            raise ValueError(f"A12 snapshot identity conflict for {row.snapshot_id}: {old} vs {identity}")
        identity_by_snapshot[row.snapshot_id] = identity
    return dict(paths_by_snapshot), sha_by_key, identity_by_snapshot


def classify_row(
    row: pd.Series,
    repo_dir: Path,
    tree: dict[str, GitEntry],
    a12_paths: set[str],
    a12_sha_by_path: dict[str, str],
    timeout: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    component_path = str(row["component_path"])
    exact = tree.get(component_path)
    case_matches = [p for p in tree if p.lower() == component_path.lower() and p != component_path]
    final_path, hops, resolution_error = resolve_through_symlinks(
        repo_dir=repo_dir,
        original_path=component_path,
        tree=tree,
        timeout=timeout,
    )
    final_entry = tree.get(final_path)
    final_in_a12 = final_path in a12_paths
    final_blob_sha256 = ""
    a12_sha256 = a12_sha_by_path.get(final_path, "")
    content_sha256_matches_a12: bool | None = None
    if final_entry is not None and final_entry.obj_type == "blob" and final_entry.mode in {"100644", "100755"}:
        final_blob_sha256 = blob_sha256(repo_dir, final_entry.oid, timeout)
        if a12_sha256:
            content_sha256_matches_a12 = final_blob_sha256 == a12_sha256

    if exact is not None and exact.mode in {"100644", "100755"}:
        classification = "tracked_regular_missing_from_a12"
        cause_strength = "high_concern"
    elif exact is not None and exact.mode == "120000":
        if hops and final_entry is not None and final_in_a12:
            classification = "tracked_symlink_alias_to_a12_file"
            cause_strength = "confirmed_scope_alias"
        else:
            classification = "tracked_symlink_outside_a12_or_unresolved"
            cause_strength = "needs_review"
    elif hops and final_entry is not None and final_in_a12:
        classification = "filesystem_alias_via_tracked_directory_symlink_to_a12_file"
        cause_strength = "confirmed_scope_alias"
    elif hops and final_entry is not None:
        classification = "filesystem_alias_via_tracked_symlink_target_outside_a12"
        cause_strength = "needs_review"
    elif case_matches:
        classification = "case_normalization_difference"
        cause_strength = "needs_review"
    elif resolution_error:
        classification = "symlink_resolution_error"
        cause_strength = "needs_review"
    else:
        classification = "not_tracked_no_symlink_resolution"
        cause_strength = "needs_review"

    evidence_rows = []
    for hop_index, hop in enumerate(hops, start=1):
        evidence_rows.append(
            {
                "snapshot_key": row["snapshot_key"],
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "commit_sha": row["commit_sha"],
                "component_path": component_path,
                "hop_index": hop_index,
                "symlink_path": hop.source_path,
                "symlink_oid": hop.source_oid,
                "symlink_target": hop.target_text,
                "resolved_path_after_hop": hop.resolved_path_after_hop,
            }
        )

    detail = {
        **row.to_dict(),
        "repo_clone_path": str(repo_dir),
        "git_exact_path_present": exact is not None,
        "git_exact_mode": exact.mode if exact else "",
        "git_exact_type": exact.obj_type if exact else "",
        "git_exact_oid": exact.oid if exact else "",
        "case_insensitive_match_count": len(case_matches),
        "case_insensitive_matches": "|".join(sorted(case_matches)[:10]),
        "symlink_hop_count": len(hops),
        "symlink_chain": " | ".join(f"{h.source_path} -> {h.target_text} => {h.resolved_path_after_hop}" for h in hops),
        "symlink_resolution_error": resolution_error or "",
        "resolved_git_path": final_path,
        "resolved_git_path_present": final_entry is not None,
        "resolved_git_mode": final_entry.mode if final_entry else "",
        "resolved_git_type": final_entry.obj_type if final_entry else "",
        "resolved_git_oid": final_entry.oid if final_entry else "",
        "resolved_path_in_a12": final_in_a12,
        "resolved_git_blob_sha256": final_blob_sha256,
        "a12_file_sha256_at_resolved_path": a12_sha256,
        "content_sha256_matches_a12": content_sha256_matches_a12,
        "scope_cause_class": classification,
        "scope_cause_strength": cause_strength,
    }
    return detail, evidence_rows


def check_row(name: str, observed: Any, expected: Any, passed: bool, detail: str = "") -> dict[str, Any]:
    return {
        "check": name,
        "observed": observed,
        "expected": expected,
        "status": "pass" if passed else "fail",
        "detail": detail,
    }


def build_repo_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        detail_df.groupby(["dataset_source", "repo_name", "scope_cause_class", "scope_cause_strength"], dropna=False)
        .agg(
            outside_files=("component_path", "size"),
            affected_snapshots=("snapshot_key", "nunique"),
            outside_issue_stock=("sonar_issue_total", "sum"),
            symlink_hops=("symlink_hop_count", "sum"),
            resolved_to_a12_files=("resolved_path_in_a12", "sum"),
        )
        .reset_index()
        .sort_values(["dataset_source", "repo_name", "scope_cause_class"])
    )
    return grouped


def build_snapshot_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    temp = detail_df.copy()
    temp["confirmed_scope_alias"] = temp["scope_cause_strength"].eq("confirmed_scope_alias")
    temp["needs_review"] = temp["scope_cause_strength"].ne("confirmed_scope_alias")
    grouped = (
        temp.groupby(["snapshot_key", "dataset_source", "repo_name", "commit_sha"], dropna=False)
        .agg(
            outside_files=("component_path", "size"),
            outside_issue_stock=("sonar_issue_total", "sum"),
            confirmed_scope_alias_files=("confirmed_scope_alias", "sum"),
            needs_review_files=("needs_review", "sum"),
        )
        .reset_index()
        .sort_values(["dataset_source", "repo_name", "commit_sha"])
    )
    return grouped


def build_sensitivity_spec(detail_df: pd.DataFrame) -> pd.DataFrame:
    repos = (
        detail_df[["dataset_source", "repo_name"]]
        .drop_duplicates()
        .sort_values(["dataset_source", "repo_name"])
        .reset_index(drop=True)
    )
    repos.insert(0, "sample_spec", "exclude_scope_mismatch_repos")
    repos["exclude_repository"] = 1
    repos["prespecified_before_d03"] = 1
    repos["reason"] = (
        "Repository has D02 SonarQube Python issue-bearing paths outside the frozen A12 FUN-NPR file universe; "
        "exclude the entire repository in the pre-specified scope sensitivity analysis."
    )
    return repos


def validate_d02_inputs(checks_path: Path, summary_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks = pd.read_csv(checks_path, dtype=str)
    summary = pd.read_csv(summary_path, dtype=str)
    if not {"check", "status"}.issubset(checks.columns):
        raise ValueError("D02 checks file must contain check,status columns")
    if not {"metric", "value"}.issubset(summary.columns):
        raise ValueError("D02 summary file must contain metric,value columns")
    failed = checks[checks["status"].str.lower() != "pass"]
    if not failed.empty:
        raise RuntimeError(f"D02 checks contain non-pass rows: {failed[['check','status']].to_dict('records')}")
    summary_map = dict(zip(summary["metric"], summary["value"]))
    if summary_map.get("status") != "PASS_WITH_SCOPE_EXCLUSIONS":
        raise RuntimeError(f"Unexpected D02 status: {summary_map.get('status')}")
    if int(summary_map.get("hard_qc_failures", "-1")) != 0:
        raise RuntimeError("D02 summary reports hard QC failures")
    return checks, summary


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    outside_path = require_file(args.outside_a12_file, "D02 outside-A12 CSV")
    a12_path = require_file(args.a12_file, "A12 file-NPR CSV")
    d02_checks_path = require_file(args.d02_checks_file, "D02 checks CSV")
    d02_summary_path = require_file(args.d02_summary_file, "D02 summary CSV")
    treatment_root = require_dir(args.treatment_repos_dir, "treatment repository root")
    control_root = require_dir(args.control_repos_dir, "control repository root")

    validate_d02_inputs(d02_checks_path, d02_summary_path)

    outside = pd.read_csv(outside_path, low_memory=False)
    require_columns(outside, OUTSIDE_REQUIRED, "D02 outside-A12")
    outside["sonar_issue_total"] = pd.to_numeric(outside["sonar_issue_total"], errors="raise").astype(int)
    outside = outside.sort_values(["dataset_source", "repo_name", "commit_sha", "component_path"]).reset_index(drop=True)

    a12_paths_by_snapshot, a12_sha_by_key, a12_identity = load_a12_index(a12_path)

    tree_cache: dict[tuple[str, str], dict[str, GitEntry]] = {}
    detail_rows: list[dict[str, Any]] = []
    symlink_rows: list[dict[str, Any]] = []
    repo_available: dict[tuple[str, str], bool] = {}
    commit_available: dict[tuple[str, str, str], bool] = {}

    for _, row in outside.iterrows():
        dataset_source = str(row["dataset_source"])
        repo_name = str(row["repo_name"])
        commit_sha = str(row["commit_sha"])
        snapshot_key = str(row["snapshot_key"])
        repo_dir = repo_clone_path(dataset_source, repo_name, treatment_root, control_root)
        repo_key = (dataset_source, repo_name)
        repo_available[repo_key] = repo_dir.is_dir()

        expected_identity = a12_identity.get(snapshot_key)
        identity_matches_a12 = expected_identity == (dataset_source, repo_name, commit_sha)

        if not repo_dir.is_dir():
            detail_rows.append(
                {
                    **row.to_dict(),
                    "repo_clone_path": str(repo_dir),
                    "a12_snapshot_identity_matches": identity_matches_a12,
                    "git_exact_path_present": False,
                    "git_exact_mode": "",
                    "git_exact_type": "",
                    "git_exact_oid": "",
                    "case_insensitive_match_count": 0,
                    "case_insensitive_matches": "",
                    "symlink_hop_count": 0,
                    "symlink_chain": "",
                    "symlink_resolution_error": "repo_clone_missing",
                    "resolved_git_path": "",
                    "resolved_git_path_present": False,
                    "resolved_git_mode": "",
                    "resolved_git_type": "",
                    "resolved_git_oid": "",
                    "resolved_path_in_a12": False,
                    "resolved_git_blob_sha256": "",
                    "a12_file_sha256_at_resolved_path": "",
                    "content_sha256_matches_a12": None,
                    "scope_cause_class": "audit_unavailable_repo_clone_missing",
                    "scope_cause_strength": "audit_unavailable",
                }
            )
            continue

        cache_key = (str(repo_dir), commit_sha)
        if cache_key not in tree_cache:
            try:
                run_git(repo_dir, ["cat-file", "-e", f"{commit_sha}^{{commit}}"], timeout=args.git_timeout_seconds, text=False)
                commit_available[(dataset_source, repo_name, commit_sha)] = True
                tree_cache[cache_key] = load_tree(repo_dir, commit_sha, timeout=args.git_timeout_seconds)
            except Exception as exc:
                commit_available[(dataset_source, repo_name, commit_sha)] = False
                detail_rows.append(
                    {
                        **row.to_dict(),
                        "repo_clone_path": str(repo_dir),
                        "a12_snapshot_identity_matches": identity_matches_a12,
                        "git_exact_path_present": False,
                        "git_exact_mode": "",
                        "git_exact_type": "",
                        "git_exact_oid": "",
                        "case_insensitive_match_count": 0,
                        "case_insensitive_matches": "",
                        "symlink_hop_count": 0,
                        "symlink_chain": "",
                        "symlink_resolution_error": f"commit_unavailable:{type(exc).__name__}",
                        "resolved_git_path": "",
                        "resolved_git_path_present": False,
                        "resolved_git_mode": "",
                        "resolved_git_type": "",
                        "resolved_git_oid": "",
                        "resolved_path_in_a12": False,
                        "resolved_git_blob_sha256": "",
                        "a12_file_sha256_at_resolved_path": "",
                        "content_sha256_matches_a12": None,
                        "scope_cause_class": "audit_unavailable_commit_missing",
                        "scope_cause_strength": "audit_unavailable",
                    }
                )
                continue

        tree = tree_cache[cache_key]
        snapshot_a12_paths = a12_paths_by_snapshot.get(snapshot_key, set())
        snapshot_a12_sha = {p: a12_sha_by_key[(snapshot_key, p)] for p in snapshot_a12_paths}
        detail, evidence = classify_row(
            row=row,
            repo_dir=repo_dir,
            tree=tree,
            a12_paths=snapshot_a12_paths,
            a12_sha_by_path=snapshot_a12_sha,
            timeout=args.git_timeout_seconds,
        )
        detail["a12_snapshot_identity_matches"] = identity_matches_a12
        detail_rows.append(detail)
        symlink_rows.extend(evidence)

    detail_df = pd.DataFrame(detail_rows)
    symlink_df = pd.DataFrame(symlink_rows)
    if symlink_df.empty:
        symlink_df = pd.DataFrame(
            columns=[
                "snapshot_key",
                "dataset_source",
                "repo_name",
                "commit_sha",
                "component_path",
                "hop_index",
                "symlink_path",
                "symlink_oid",
                "symlink_target",
                "resolved_path_after_hop",
            ]
        )

    repo_summary = build_repo_summary(detail_df)
    snapshot_summary = build_snapshot_summary(detail_df)
    sensitivity_spec = build_sensitivity_spec(detail_df)

    outside_rows = len(outside)
    outside_issues = int(outside["sonar_issue_total"].sum())
    affected_snapshots = int(outside["snapshot_key"].nunique())
    affected_repos = int(outside["repo_name"].nunique())
    duplicate_keys = int(outside.duplicated(["snapshot_key", "component_path"]).sum())
    identity_mismatches = int((~detail_df["a12_snapshot_identity_matches"].fillna(False)).sum())
    unavailable_rows = int(detail_df["scope_cause_strength"].eq("audit_unavailable").sum())
    confirmed_alias_rows = int(detail_df["scope_cause_strength"].eq("confirmed_scope_alias").sum())
    needs_review_rows = int(detail_df["scope_cause_strength"].eq("needs_review").sum())
    high_concern_rows = int(detail_df["scope_cause_strength"].eq("high_concern").sum())
    classified_rows = int(detail_df["scope_cause_class"].notna().sum())
    resolved_to_a12_rows = int(detail_df["resolved_path_in_a12"].fillna(False).sum())
    content_match_rows = int(detail_df["content_sha256_matches_a12"].fillna(False).sum())
    clone_repos_available = sum(repo_available.values())
    unique_commits_expected = outside[["dataset_source", "repo_name", "commit_sha"]].drop_duplicates().shape[0]
    unique_commits_available = sum(commit_available.values())

    checks: list[dict[str, Any]] = []
    strict = bool(args.strict_expected_counts)
    checks.append(check_row("outside_rows", outside_rows, args.expected_outside_rows if strict else ">=1", (outside_rows == args.expected_outside_rows) if strict else outside_rows > 0))
    checks.append(check_row("outside_issue_stock", outside_issues, args.expected_outside_issues if strict else ">=0", (outside_issues == args.expected_outside_issues) if strict else outside_issues >= 0))
    checks.append(check_row("affected_snapshots", affected_snapshots, args.expected_affected_snapshots if strict else ">=1", (affected_snapshots == args.expected_affected_snapshots) if strict else affected_snapshots > 0))
    checks.append(check_row("affected_repositories", affected_repos, args.expected_affected_repositories if strict else ">=1", (affected_repos == args.expected_affected_repositories) if strict else affected_repos > 0))
    checks.append(check_row("duplicate_snapshot_component_keys", duplicate_keys, 0, duplicate_keys == 0))
    checks.append(check_row("a12_snapshot_identity_mismatches", identity_mismatches, 0, identity_mismatches == 0))
    checks.append(check_row("affected_repo_clones_available", clone_repos_available, affected_repos, clone_repos_available == affected_repos))
    checks.append(check_row("affected_commits_available", unique_commits_available, unique_commits_expected, unique_commits_available == unique_commits_expected))
    checks.append(check_row("detail_rows_classified", classified_rows, outside_rows, classified_rows == outside_rows))
    checks.append(check_row("audit_unavailable_rows", unavailable_rows, 0, unavailable_rows == 0))
    checks.append(check_row("detail_issue_stock_reconciles", int(detail_df["sonar_issue_total"].sum()), outside_issues, int(detail_df["sonar_issue_total"].sum()) == outside_issues))
    checks.append(check_row("sensitivity_repositories_frozen", len(sensitivity_spec), affected_repos, len(sensitivity_spec) == affected_repos, "Repository-level exclusion sensitivity is frozen before D03 causal results."))

    checks_df = pd.DataFrame(checks)
    hard_failures = int((checks_df["status"] == "fail").sum())

    if hard_failures:
        status = "FAIL"
    elif high_concern_rows > 0:
        status = "PASS_WITH_HIGH_CONCERN_SCOPE_CAUSES"
    elif needs_review_rows > 0:
        status = "PASS_WITH_UNRESOLVED_SCOPE_CAUSES"
    elif confirmed_alias_rows == outside_rows:
        status = "PASS_CONFIRMED_FILESYSTEM_ALIAS_SCOPE"
    else:
        status = "PASS"

    summary_rows = [
        ("script_version", SCRIPT_VERSION),
        ("status", status),
        ("outside_rows", outside_rows),
        ("outside_issue_stock", outside_issues),
        ("affected_snapshots", affected_snapshots),
        ("affected_repositories", affected_repos),
        ("confirmed_scope_alias_rows", confirmed_alias_rows),
        ("needs_review_rows", needs_review_rows),
        ("high_concern_rows", high_concern_rows),
        ("audit_unavailable_rows", unavailable_rows),
        ("resolved_to_a12_rows", resolved_to_a12_rows),
        ("content_sha256_match_rows", content_match_rows),
        ("symlink_evidence_rows", len(symlink_df)),
        ("sensitivity_repositories", len(sensitivity_spec)),
        ("hard_qc_failures", hard_failures),
        ("thresholds_applied", 0),
        ("sonarqube_api_called", 0),
        ("sonarscanner_rerun", 0),
        ("git_checkout_performed", 0),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["metric", "value"])

    for output in [
        args.detail_output,
        args.symlink_evidence_output,
        args.snapshot_summary_output,
        args.repo_summary_output,
        args.sensitivity_spec_output,
        args.checks_output,
        args.summary_output,
    ]:
        if output is None:
            raise ValueError("All output paths are required")

    atomic_csv(detail_df, args.detail_output)
    atomic_csv(symlink_df, args.symlink_evidence_output)
    atomic_csv(snapshot_summary, args.snapshot_summary_output)
    atomic_csv(repo_summary, args.repo_summary_output)
    atomic_csv(sensitivity_spec, args.sensitivity_spec_output)
    atomic_csv(checks_df, args.checks_output)
    atomic_csv(summary_df, args.summary_output)

    metadata = {
        "script_version": SCRIPT_VERSION,
        "status": status,
        "input_sha256": {
            "outside_a12_file": sha256_file(outside_path),
            "a12_file": sha256_file(a12_path),
            "d02_checks_file": sha256_file(d02_checks_path),
            "d02_summary_file": sha256_file(d02_summary_path),
        },
        "repository_roots": {
            "treatment": str(treatment_root.resolve()),
            "control": str(control_root.resolve()),
        },
        "audit_semantics": {
            "git_inspection": "git ls-tree and git cat-file at exact historical commit",
            "checkout_performed": False,
            "sonarqube_api_called": False,
            "sonarscanner_rerun": False,
            "npr_threshold_applied": False,
            "sensitivity_policy": "exclude entire affected repository in a pre-specified D03/D04 scope sensitivity sample",
        },
        "counts": {k: v for k, v in summary_rows if isinstance(v, (int, float))},
        "cause_counts": dict(Counter(detail_df["scope_cause_class"])),
        "hard_qc_failures": hard_failures,
    }
    if args.metadata_output is None:
        raise ValueError("--metadata-output is required")
    atomic_json(metadata, args.metadata_output)

    print("=" * 80)
    print("run-x-d02-a FUN-NPR x SonarQube file-scope audit")
    print(f"Status:                              {status}")
    print(f"Outside-A12 file rows:               {outside_rows}")
    print(f"Outside-A12 issue stock:             {outside_issues}")
    print(f"Affected snapshots / repositories:   {affected_snapshots} / {affected_repos}")
    print(f"Confirmed filesystem-alias rows:     {confirmed_alias_rows}")
    print(f"Needs-review rows:                    {needs_review_rows}")
    print(f"High-concern rows:                    {high_concern_rows}")
    print(f"Resolved to A12 tracked paths:        {resolved_to_a12_rows}")
    print(f"Content SHA256 matches A12:           {content_match_rows}")
    print(f"Symlink evidence rows:                {len(symlink_df)}")
    print(f"Frozen sensitivity repositories:      {len(sensitivity_spec)}")
    print(f"Hard QC failures:                     {hard_failures}")
    print(f"Detail:                               {args.detail_output}")
    print(f"Repository summary:                   {args.repo_summary_output}")
    print(f"Sensitivity spec:                     {args.sensitivity_spec_output}")
    print("=" * 80)

    if hard_failures:
        raise RuntimeError(f"D02-a hard QC failures: {hard_failures}; see {args.checks_output}")
    return metadata


def initialize_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "audit@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Audit Self Test"], check=True)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="d02a-self-test-") as temp_raw:
        temp = Path(temp_raw)
        treatment_root = temp / "treatment-repos"
        control_root = temp / "control-repos"
        treatment_root.mkdir()
        control_root.mkdir()
        repo = treatment_root / "Org_repo"
        repo.mkdir()
        initialize_git_repo(repo)
        (repo / "src" / "pkg").mkdir(parents=True)
        source = repo / "src" / "pkg" / "a.py"
        source.write_text("def f():\n    return 1\n", encoding="utf-8")
        os.symlink("src", repo / "alias")
        os.symlink("src/pkg/a.py", repo / "link.py")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "test"], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        content_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        snapshot = "treatment__Org_repo__snapshot"

        a12 = pd.DataFrame(
            [
                {
                    "snapshot_id": snapshot,
                    "dataset_source": "treatment",
                    "repo_name": "Org/repo",
                    "snapshot_commit": commit,
                    "relative_path": "src/pkg/a.py",
                    "file_sha256": content_sha,
                }
            ]
        )
        a12_path = temp / "a12.csv"
        a12.to_csv(a12_path, index=False)
        outside = pd.DataFrame(
            [
                {
                    "snapshot_key": snapshot,
                    "dataset_source": "treatment",
                    "repo_name": "Org/repo",
                    "commit_sha": commit,
                    "component_path": "alias/pkg/a.py",
                    "sonar_issue_total": 3,
                },
                {
                    "snapshot_key": snapshot,
                    "dataset_source": "treatment",
                    "repo_name": "Org/repo",
                    "commit_sha": commit,
                    "component_path": "link.py",
                    "sonar_issue_total": 2,
                },
            ]
        )
        outside_path = temp / "outside.csv"
        outside.to_csv(outside_path, index=False)

        paths_by_snapshot, sha_by_key, _ = load_a12_index(a12_path)
        tree = load_tree(repo, commit, 30)
        classes = []
        for _, row in outside.iterrows():
            detail, _ = classify_row(
                row,
                repo,
                tree,
                paths_by_snapshot[snapshot],
                {p: sha_by_key[(snapshot, p)] for p in paths_by_snapshot[snapshot]},
                30,
            )
            classes.append(detail["scope_cause_class"])
            if not detail["resolved_path_in_a12"]:
                raise AssertionError(f"Self-test path did not resolve into A12: {detail}")
            if not detail["content_sha256_matches_a12"]:
                raise AssertionError(f"Self-test content hash did not match A12: {detail}")
        expected = {
            "filesystem_alias_via_tracked_directory_symlink_to_a12_file",
            "tracked_symlink_alias_to_a12_file",
        }
        if set(classes) != expected:
            raise AssertionError(f"Unexpected self-test classifications: {classes}")
    print("audit_fun_npr_sonarqube_scope self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    run_pipeline(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
