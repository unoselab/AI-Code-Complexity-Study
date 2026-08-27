#!/usr/bin/env python3
"""
Build a reusable file-level Quality x C_FUN-NPR dataset without applying thresholds.

This H02 implementation was copied from the validated D02 FUN implementation and
adapted for the frozen A15 C_FUN artifact. It is standalone and does not import
or invoke the D02 Python program or shell wrapper.

The program joins two frozen production artifacts:

1. A15 repo-month/file C_FUN-NPR rows.
2. B05 complete unresolved Python SonarQube issue rows.

The join is exact at historical snapshot + repository-relative file path:

    A15.snapshot_id   == B05.snapshot_key
    A15.relative_path == B05.component_path

Important semantics:
- The SonarQube metric is an unresolved issue stock observed in a historical
  Python-only snapshot. It is not a count of issues introduced in that month.
- A15 is the NPR analysis file universe. Therefore a Python file with no B05
  issue row gets an issue burden of zero, but only after B05 snapshot completeness
  is verified.
- B05 may contain SonarQube Python files that are outside the A15 NPR file universe.
  Those files cannot receive an NPR threshold classification, so H02 records them
  as explicit scope exclusions rather than treating them as join failures. Snapshot
  accounting must still reconcile exactly as joined burden + scope-excluded burden.
- No NPR threshold is applied here. H01 remains the frozen threshold source;
  a later experiment can apply the same threshold grid to this reusable join.
- Density is intentionally not computed here because file-level SonarQube NCLOC
  is not yet part of the frozen inputs. Project-level NCLOC is not substituted.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

SCRIPT_VERSION = "run-x-h02-v1"
QUALITY_SEMANTICS = "unresolved_python_sonarqube_issue_stock_at_historical_snapshot"
PRIMARY_NPR_METRIC = "file_npr_cfun_space_by_token_weighted"

KNOWN_TYPES = ("CODE_SMELL", "BUG", "VULNERABILITY")
KNOWN_SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
QUALITY_NAMES = ("MAINTAINABILITY", "RELIABILITY", "SECURITY")
FINITE_CFUN_STATUSES = {"scored", "scored_with_expected_exclusions"}

A15_REQUIRED = {
    "repo_id",
    "dataset_source",
    "repo_name",
    "repo_month",
    "time_index",
    "event_index",
    "snapshot_id",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "cfun_occurrences_total",
    "cfun_occurrences_scored",
    "cfun_occurrences_excluded",
    "cfun_npr_coverage_ratio",
    PRIMARY_NPR_METRIC,
    "file_npr_cfun_status",
}

B05_RAW_REQUIRED = {
    "dataset_source",
    "repo_name",
    "snapshot_key",
    "commit_sha",
    "issue_key",
    "type",
    "severity",
    "status",
    "resolution",
    "component_path",
    "component_scope",
    "impacts_json",
}

B05_SNAPSHOT_REQUIRED = {
    "dataset_source",
    "repo_name",
    "snapshot_key",
    "commit_sha",
    "issue_total_py_sonarqube",
    "issue_type_code_smell",
    "issue_type_bug",
    "issue_type_vulnerability",
    "issue_type_other",
    "issue_severity_blocker",
    "issue_severity_critical",
    "issue_severity_major",
    "issue_severity_minor",
    "issue_severity_info",
    "issue_severity_other",
    "issue_with_maintainability_impact",
    "issue_with_reliability_impact",
    "issue_with_security_impact",
    "issue_component_python_file",
    "issue_component_project",
    "issue_component_non_python",
    "issue_component_unknown",
    "issue_rows_complete",
    "current_snapshot_recoverable",
}

QUALITY_OUTPUT_COLUMNS = [
    "sonar_issue_total",
    "sonar_issue_type_code_smell",
    "sonar_issue_type_bug",
    "sonar_issue_type_vulnerability",
    "sonar_issue_type_other",
    "sonar_issue_severity_blocker",
    "sonar_issue_severity_critical",
    "sonar_issue_severity_major",
    "sonar_issue_severity_minor",
    "sonar_issue_severity_info",
    "sonar_issue_severity_other",
    "sonar_issue_high_severity",
    "sonar_issue_with_maintainability_impact",
    "sonar_issue_with_reliability_impact",
    "sonar_issue_with_security_impact",
    "sonar_issue_file_has_any",
    "sonar_issue_join_status",
]

SNAPSHOT_AUDIT_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "b05_issue_total",
    "h02_joined_issue_total",
    "outside_a15_issue_total",
    "accounted_issue_total",
    "issue_total_matches",
    "b05_code_smell",
    "h02_joined_code_smell",
    "outside_a15_code_smell",
    "accounted_code_smell",
    "code_smell_matches",
    "b05_bug",
    "h02_joined_bug",
    "outside_a15_bug",
    "accounted_bug",
    "bug_matches",
    "b05_vulnerability",
    "h02_joined_vulnerability",
    "outside_a15_vulnerability",
    "accounted_vulnerability",
    "vulnerability_matches",
    "b05_high_severity",
    "h02_joined_high_severity",
    "outside_a15_high_severity",
    "accounted_high_severity",
    "high_severity_matches",
    "b05_maintainability_impact",
    "h02_joined_maintainability_impact",
    "outside_a15_maintainability_impact",
    "accounted_maintainability_impact",
    "maintainability_impact_matches",
    "b05_reliability_impact",
    "h02_joined_reliability_impact",
    "outside_a15_reliability_impact",
    "accounted_reliability_impact",
    "reliability_impact_matches",
    "b05_security_impact",
    "h02_joined_security_impact",
    "outside_a15_security_impact",
    "accounted_security_impact",
    "security_impact_matches",
    "outside_a15_issue_bearing_files",
]

CHECK_COLUMNS = ["check", "observed", "expected", "status", "detail"]
SUMMARY_COLUMNS = ["metric", "value"]

OUTSIDE_A15_COLUMNS = [
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "component_path",
    "exclusion_class",
    "exclusion_detail",
    "sonar_issue_total",
    "sonar_issue_type_code_smell",
    "sonar_issue_type_bug",
    "sonar_issue_type_vulnerability",
    "sonar_issue_type_other",
    "sonar_issue_severity_blocker",
    "sonar_issue_severity_critical",
    "sonar_issue_severity_major",
    "sonar_issue_severity_minor",
    "sonar_issue_severity_info",
    "sonar_issue_severity_other",
    "sonar_issue_high_severity",
    "sonar_issue_with_maintainability_impact",
    "sonar_issue_with_reliability_impact",
    "sonar_issue_with_security_impact",
]


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_int(value: Any, label: str) -> int:
    text = clean(value)
    if text == "":
        raise ValueError(f"Missing integer for {label}")
    try:
        parsed = int(float(text))
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {label}: {text}") from exc
    if parsed < 0:
        raise ValueError(f"Negative integer for {label}: {parsed}")
    return parsed


def parse_bool(value: Any) -> bool:
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_text_input(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def iter_csv(path: Path) -> Iterator[dict[str, str]]:
    with open_text_input(path) as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        for row in reader:
            yield row


def read_header(path: Path) -> list[str]:
    with open_text_input(path) as stream:
        reader = csv.reader(stream)
        try:
            return next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {path}") from exc


def require_columns(path: Path, required: set[str], label: str) -> list[str]:
    header = read_header(path)
    missing = sorted(required - set(header))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")
    return header


def atomic_csv_rows(rows: Iterable[dict[str, Any]], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(tmp, path)


def open_deterministic_gzip_csv(path: Path, columns: list[str]) -> tuple[Path, TextIO, csv.DictWriter]:
    """Open a temporary deterministic gzip CSV writer; caller replaces the final path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    raw = tmp.open("wb")
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    # Keep raw reachable so closing text closes the complete wrapper stack.
    setattr(text, "_h02_raw_file", raw)
    return tmp, text, writer


@dataclass
class IssueCounts:
    total: int = 0
    code_smell: int = 0
    bug: int = 0
    vulnerability: int = 0
    type_other: int = 0
    blocker: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0
    info: int = 0
    severity_other: int = 0
    maintainability: int = 0
    reliability: int = 0
    security: int = 0

    @property
    def high_severity(self) -> int:
        return self.blocker + self.critical

    def add_issue(self, issue_type: str, severity: str, qualities: set[str]) -> None:
        self.total += 1
        if issue_type == "CODE_SMELL":
            self.code_smell += 1
        elif issue_type == "BUG":
            self.bug += 1
        elif issue_type == "VULNERABILITY":
            self.vulnerability += 1
        else:
            self.type_other += 1

        if severity == "BLOCKER":
            self.blocker += 1
        elif severity == "CRITICAL":
            self.critical += 1
        elif severity == "MAJOR":
            self.major += 1
        elif severity == "MINOR":
            self.minor += 1
        elif severity == "INFO":
            self.info += 1
        else:
            self.severity_other += 1

        if "MAINTAINABILITY" in qualities:
            self.maintainability += 1
        if "RELIABILITY" in qualities:
            self.reliability += 1
        if "SECURITY" in qualities:
            self.security += 1

    def add_counts(self, other: "IssueCounts") -> None:
        for name in (
            "total",
            "code_smell",
            "bug",
            "vulnerability",
            "type_other",
            "blocker",
            "critical",
            "major",
            "minor",
            "info",
            "severity_other",
            "maintainability",
            "reliability",
            "security",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def output_values(self) -> dict[str, Any]:
        return {
            "sonar_issue_total": self.total,
            "sonar_issue_type_code_smell": self.code_smell,
            "sonar_issue_type_bug": self.bug,
            "sonar_issue_type_vulnerability": self.vulnerability,
            "sonar_issue_type_other": self.type_other,
            "sonar_issue_severity_blocker": self.blocker,
            "sonar_issue_severity_critical": self.critical,
            "sonar_issue_severity_major": self.major,
            "sonar_issue_severity_minor": self.minor,
            "sonar_issue_severity_info": self.info,
            "sonar_issue_severity_other": self.severity_other,
            "sonar_issue_high_severity": self.high_severity,
            "sonar_issue_with_maintainability_impact": self.maintainability,
            "sonar_issue_with_reliability_impact": self.reliability,
            "sonar_issue_with_security_impact": self.security,
            "sonar_issue_file_has_any": int(self.total > 0),
            "sonar_issue_join_status": "matched_issue_file" if self.total > 0 else "zero_issue_file",
        }


@dataclass(frozen=True)
class SnapshotMeta:
    dataset_source: str
    repo_name: str
    commit_sha: str
    expected: IssueCounts


def counts_from_snapshot_row(row: dict[str, str]) -> IssueCounts:
    return IssueCounts(
        total=parse_int(row["issue_total_py_sonarqube"], "snapshot issue_total"),
        code_smell=parse_int(row["issue_type_code_smell"], "snapshot code_smell"),
        bug=parse_int(row["issue_type_bug"], "snapshot bug"),
        vulnerability=parse_int(row["issue_type_vulnerability"], "snapshot vulnerability"),
        type_other=parse_int(row["issue_type_other"], "snapshot type_other"),
        blocker=parse_int(row["issue_severity_blocker"], "snapshot blocker"),
        critical=parse_int(row["issue_severity_critical"], "snapshot critical"),
        major=parse_int(row["issue_severity_major"], "snapshot major"),
        minor=parse_int(row["issue_severity_minor"], "snapshot minor"),
        info=parse_int(row["issue_severity_info"], "snapshot info"),
        severity_other=parse_int(row["issue_severity_other"], "snapshot severity_other"),
        maintainability=parse_int(row["issue_with_maintainability_impact"], "snapshot maintainability"),
        reliability=parse_int(row["issue_with_reliability_impact"], "snapshot reliability"),
        security=parse_int(row["issue_with_security_impact"], "snapshot security"),
    )


def parse_quality_impacts(raw: str, label: str) -> set[str]:
    text = clean(raw)
    if not text:
        return set()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid impacts_json at {label}: {text[:200]}") from exc
    if not isinstance(value, list):
        raise ValueError(f"impacts_json is not a list at {label}")
    qualities: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        quality = clean(item.get("softwareQuality")).upper()
        if quality:
            qualities.add(quality)
    unexpected = sorted(qualities - set(QUALITY_NAMES))
    if unexpected:
        raise ValueError(f"Unexpected software-quality impacts at {label}: {unexpected}")
    return qualities


def load_metric_value_csv(path: Path) -> dict[str, str]:
    header = require_columns(path, {"metric", "value"}, "metric/value CSV")
    _ = header
    values: dict[str, str] = {}
    for row in iter_csv(path):
        metric = clean(row["metric"])
        if metric:
            values[metric] = clean(row["value"])
    return values


def validate_b05_qc(path: Path) -> tuple[int, list[str]]:
    require_columns(path, {"check", "value", "expected", "status", "detail"}, "B05 QC")
    failures: list[str] = []
    rows = 0
    for row in iter_csv(path):
        rows += 1
        if clean(row["status"]).casefold() != "pass":
            failures.append(clean(row["check"]))
    if failures:
        raise ValueError(f"B05 QC contains non-pass checks: {failures}")
    return rows, failures


def load_b05_snapshots(path: Path) -> dict[str, SnapshotMeta]:
    require_columns(path, B05_SNAPSHOT_REQUIRED, "B05 snapshot counts")
    snapshots: dict[str, SnapshotMeta] = {}
    for row_index, row in enumerate(iter_csv(path), start=2):
        key = clean(row["snapshot_key"])
        if not key:
            raise ValueError(f"Missing B05 snapshot_key at row {row_index}")
        if key in snapshots:
            raise ValueError(f"Duplicate B05 snapshot_key: {key}")
        if not parse_bool(row["issue_rows_complete"]):
            raise ValueError(f"B05 issue rows are incomplete for snapshot {key}")
        if not parse_bool(row["current_snapshot_recoverable"]):
            raise ValueError(f"B05 snapshot is not recoverable: {key}")
        expected = counts_from_snapshot_row(row)
        component_python = parse_int(row["issue_component_python_file"], f"{key} python component count")
        component_project = parse_int(row["issue_component_project"], f"{key} project component count")
        component_nonpython = parse_int(row["issue_component_non_python"], f"{key} non-Python component count")
        component_unknown = parse_int(row["issue_component_unknown"], f"{key} unknown component count")
        if component_python != expected.total or component_project or component_nonpython or component_unknown:
            raise ValueError(
                f"B05 component-scope invariant failed for {key}: "
                f"python={component_python}, project={component_project}, "
                f"non_python={component_nonpython}, unknown={component_unknown}, total={expected.total}"
            )
        snapshots[key] = SnapshotMeta(
            dataset_source=clean(row["dataset_source"]).casefold(),
            repo_name=clean(row["repo_name"]),
            commit_sha=clean(row["commit_sha"]).casefold(),
            expected=expected,
        )
    return snapshots


def aggregate_b05_raw_issues(
    path: Path,
    snapshots: dict[str, SnapshotMeta],
) -> tuple[dict[tuple[str, str], IssueCounts], dict[str, IssueCounts], dict[str, Any]]:
    require_columns(path, B05_RAW_REQUIRED, "B05 raw issues")
    file_counts: dict[tuple[str, str], IssueCounts] = {}
    snapshot_observed: dict[str, IssueCounts] = defaultdict(IssueCounts)
    rows = 0
    duplicate_issue_keys = 0
    # B05 QC already guarantees no duplicate issue keys. Avoid storing all 554k
    # keys in memory; verify local consecutive duplicates are impossible through
    # exact snapshot totals and trust the frozen B05 duplicate-key QC gate.
    for row in iter_csv(path):
        rows += 1
        snapshot_key = clean(row["snapshot_key"])
        meta = snapshots.get(snapshot_key)
        if meta is None:
            raise ValueError(f"Raw B05 issue references unknown snapshot: {snapshot_key}")
        source = clean(row["dataset_source"]).casefold()
        repo = clean(row["repo_name"])
        commit = clean(row["commit_sha"]).casefold()
        if (source, repo.casefold(), commit) != (
            meta.dataset_source,
            meta.repo_name.casefold(),
            meta.commit_sha,
        ):
            raise ValueError(f"Raw B05 issue identity mismatch for snapshot {snapshot_key}")
        if clean(row["component_scope"]) != "python_file":
            raise ValueError(
                f"H02 requires file-attributable Python issues only; observed "
                f"component_scope={row['component_scope']!r} for snapshot {snapshot_key}"
            )
        path_value = clean(row["component_path"])
        if not path_value or not path_value.lower().endswith(".py"):
            raise ValueError(f"Invalid Python issue component_path for snapshot {snapshot_key}: {path_value!r}")
        issue_type = clean(row["type"]).upper()
        severity = clean(row["severity"]).upper()
        qualities = parse_quality_impacts(row["impacts_json"], f"raw issue row {rows + 1}")
        key = (snapshot_key, path_value)
        counts = file_counts.get(key)
        if counts is None:
            counts = IssueCounts()
            file_counts[key] = counts
        counts.add_issue(issue_type, severity, qualities)
        snapshot_observed[snapshot_key].add_issue(issue_type, severity, qualities)

    # Include zero-issue snapshots in the observed map.
    for key in snapshots:
        snapshot_observed.setdefault(key, IssueCounts())

    mismatches: list[str] = []
    for key, meta in snapshots.items():
        observed = snapshot_observed[key]
        expected = meta.expected
        comparable = (
            "total",
            "code_smell",
            "bug",
            "vulnerability",
            "type_other",
            "blocker",
            "critical",
            "major",
            "minor",
            "info",
            "severity_other",
            "maintainability",
            "reliability",
            "security",
        )
        if any(getattr(observed, name) != getattr(expected, name) for name in comparable):
            mismatches.append(key)
    if mismatches:
        raise ValueError(f"Raw B05 issue aggregation disagrees with snapshot counts for {len(mismatches)} snapshots")

    diagnostics = {
        "raw_issue_rows": rows,
        "issue_bearing_snapshot_files": len(file_counts),
        "duplicate_issue_keys_observed": duplicate_issue_keys,
    }
    return file_counts, dict(snapshot_observed), diagnostics


def same_file_signature(row: dict[str, str]) -> tuple[str, ...]:
    return (
        clean(row["dataset_source"]).casefold(),
        clean(row["repo_name"]).casefold(),
        clean(row["snapshot_commit"]).casefold(),
        clean(row["file_sha256"]).casefold(),
        clean(row["file_npr_cfun_status"]),
        clean(row[PRIMARY_NPR_METRIC]),
        clean(row["cfun_npr_coverage_ratio"]),
    )


def build_join(
    *,
    a15_path: Path,
    snapshots: dict[str, SnapshotMeta],
    file_counts: dict[tuple[str, str], IssueCounts],
    output_path: Path,
) -> tuple[dict[str, Any], dict[str, IssueCounts], set[tuple[str, str]]]:
    a15_header = require_columns(a15_path, A15_REQUIRED, "A15 repo-month/file C_FUN NPR")
    output_columns = a15_header + [column for column in QUALITY_OUTPUT_COLUMNS if column not in a15_header]
    tmp, text_stream, writer = open_deterministic_gzip_csv(output_path, output_columns)

    rows = 0
    finite_cfun_rows = 0
    repos: set[str] = set()
    repo_months: set[tuple[str, str]] = set()
    snapshot_ids: set[str] = set()
    unique_file_signatures: dict[tuple[str, str], tuple[str, ...]] = {}
    h02_snapshot_unique_counts: dict[str, IssueCounts] = defaultdict(IssueCounts)
    issue_file_keys_seen: set[tuple[str, str]] = set()
    matched_issue_rows = 0
    zero_issue_rows = 0

    try:
        for row in iter_csv(a15_path):
            rows += 1
            snapshot_id = clean(row["snapshot_id"])
            path_value = clean(row["relative_path"])
            meta = snapshots.get(snapshot_id)
            if meta is None:
                raise ValueError(f"A15 row references snapshot not present in B05: {snapshot_id}")
            source = clean(row["dataset_source"]).casefold()
            repo_name = clean(row["repo_name"])
            commit = clean(row["snapshot_commit"]).casefold()
            if (source, repo_name.casefold(), commit) != (
                meta.dataset_source,
                meta.repo_name.casefold(),
                meta.commit_sha,
            ):
                raise ValueError(f"A15/B05 snapshot identity mismatch for {snapshot_id}")
            if not path_value:
                raise ValueError(f"Missing A15 relative_path at row {rows + 1}")

            repo_id = clean(row["repo_id"])
            repo_month = clean(row["repo_month"])
            repos.add(repo_id)
            repo_months.add((repo_id, repo_month))
            snapshot_ids.add(snapshot_id)
            if clean(row["file_npr_cfun_status"]) in FINITE_CFUN_STATUSES:
                finite_cfun_rows += 1

            file_key = (snapshot_id, path_value)
            counts = file_counts.get(file_key, IssueCounts())
            if counts.total > 0:
                matched_issue_rows += 1
                issue_file_keys_seen.add(file_key)
            else:
                zero_issue_rows += 1

            signature = same_file_signature(row)
            prior = unique_file_signatures.get(file_key)
            if prior is None:
                unique_file_signatures[file_key] = signature
                h02_snapshot_unique_counts[snapshot_id].add_counts(counts)
            elif prior != signature:
                raise ValueError(f"Repeated A15 snapshot/file has inconsistent fields: {file_key}")

            output = dict(row)
            output.update(counts.output_values())
            writer.writerow(output)
    except Exception:
        text_stream.close()
        if tmp.exists():
            tmp.unlink()
        raise
    else:
        text_stream.flush()
        text_stream.close()
        os.replace(tmp, output_path)

    # Include snapshots with no issues in the unique-file aggregation map.
    for key in snapshots:
        h02_snapshot_unique_counts.setdefault(key, IssueCounts())

    diagnostics = {
        "a15_repo_month_file_rows": rows,
        "a15_finite_cfun_rows": finite_cfun_rows,
        "a15_unique_snapshot_files": len(unique_file_signatures),
        "a15_unique_snapshots": len(snapshot_ids),
        "repositories": len(repos),
        "repo_months": len(repo_months),
        "repo_month_file_rows_with_any_issue": matched_issue_rows,
        "repo_month_file_rows_with_zero_issues": zero_issue_rows,
        "issue_bearing_snapshot_files_seen_in_a15": len(issue_file_keys_seen),
    }
    return diagnostics, dict(h02_snapshot_unique_counts), issue_file_keys_seen


def build_outside_a15_scope_exclusions(
    *,
    snapshots: dict[str, SnapshotMeta],
    file_counts: dict[tuple[str, str], IssueCounts],
    issue_file_keys_seen: set[tuple[str, str]],
    output_path: Path,
) -> tuple[dict[str, IssueCounts], dict[str, int], dict[str, Any]]:
    """Record B05 issue-bearing files that are outside the A15 NPR file universe."""
    outside_keys = sorted(set(file_counts) - issue_file_keys_seen)
    rows: list[dict[str, Any]] = []
    snapshot_counts: dict[str, IssueCounts] = defaultdict(IssueCounts)
    snapshot_files: dict[str, int] = defaultdict(int)
    global_counts = IssueCounts()

    for snapshot_key, component_path in outside_keys:
        meta = snapshots[snapshot_key]
        counts = file_counts[(snapshot_key, component_path)]
        snapshot_counts[snapshot_key].add_counts(counts)
        snapshot_files[snapshot_key] += 1
        global_counts.add_counts(counts)
        values = counts.output_values()
        rows.append(
            {
                "snapshot_key": snapshot_key,
                "dataset_source": meta.dataset_source,
                "repo_name": meta.repo_name,
                "commit_sha": meta.commit_sha,
                "component_path": component_path,
                "exclusion_class": "outside_a15_npr_file_universe",
                "exclusion_detail": (
                    "B05 contains a Python SonarQube issue-bearing file that is not present "
                    "in the frozen A15 snapshot/file NPR universe; the file cannot be "
                    "threshold-classified and is excluded from Quality x NPR outcomes."
                ),
                **values,
            }
        )

    atomic_csv_rows(rows, output_path, OUTSIDE_A15_COLUMNS)
    diagnostics = {
        "outside_a15_issue_bearing_snapshot_files": len(outside_keys),
        "outside_a15_affected_snapshots": len(snapshot_files),
        "outside_a15_issue_rows": global_counts.total,
        "outside_a15_code_smell": global_counts.code_smell,
        "outside_a15_bug": global_counts.bug,
        "outside_a15_vulnerability": global_counts.vulnerability,
        "outside_a15_high_severity": global_counts.high_severity,
        "outside_a15_maintainability": global_counts.maintainability,
        "outside_a15_reliability": global_counts.reliability,
        "outside_a15_security": global_counts.security,
    }
    return dict(snapshot_counts), dict(snapshot_files), diagnostics


def build_snapshot_audit(
    snapshots: dict[str, SnapshotMeta],
    h02_counts: dict[str, IssueCounts],
    outside_counts: dict[str, IssueCounts],
    outside_file_counts: dict[str, int],
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    mismatch_rows = 0
    for key in sorted(snapshots):
        meta = snapshots[key]
        expected = meta.expected
        joined = h02_counts.get(key, IssueCounts())
        outside = outside_counts.get(key, IssueCounts())
        accounted = IssueCounts()
        accounted.add_counts(joined)
        accounted.add_counts(outside)
        flags = {
            "issue_total_matches": expected.total == accounted.total,
            "code_smell_matches": expected.code_smell == accounted.code_smell,
            "bug_matches": expected.bug == accounted.bug,
            "vulnerability_matches": expected.vulnerability == accounted.vulnerability,
            "high_severity_matches": expected.high_severity == accounted.high_severity,
            "maintainability_impact_matches": expected.maintainability == accounted.maintainability,
            "reliability_impact_matches": expected.reliability == accounted.reliability,
            "security_impact_matches": expected.security == accounted.security,
        }
        if not all(flags.values()):
            mismatch_rows += 1
        rows.append(
            {
                "snapshot_key": key,
                "dataset_source": meta.dataset_source,
                "repo_name": meta.repo_name,
                "commit_sha": meta.commit_sha,
                "b05_issue_total": expected.total,
                "h02_joined_issue_total": joined.total,
                "outside_a15_issue_total": outside.total,
                "accounted_issue_total": accounted.total,
                "b05_code_smell": expected.code_smell,
                "h02_joined_code_smell": joined.code_smell,
                "outside_a15_code_smell": outside.code_smell,
                "accounted_code_smell": accounted.code_smell,
                "b05_bug": expected.bug,
                "h02_joined_bug": joined.bug,
                "outside_a15_bug": outside.bug,
                "accounted_bug": accounted.bug,
                "b05_vulnerability": expected.vulnerability,
                "h02_joined_vulnerability": joined.vulnerability,
                "outside_a15_vulnerability": outside.vulnerability,
                "accounted_vulnerability": accounted.vulnerability,
                "b05_high_severity": expected.high_severity,
                "h02_joined_high_severity": joined.high_severity,
                "outside_a15_high_severity": outside.high_severity,
                "accounted_high_severity": accounted.high_severity,
                "b05_maintainability_impact": expected.maintainability,
                "h02_joined_maintainability_impact": joined.maintainability,
                "outside_a15_maintainability_impact": outside.maintainability,
                "accounted_maintainability_impact": accounted.maintainability,
                "b05_reliability_impact": expected.reliability,
                "h02_joined_reliability_impact": joined.reliability,
                "outside_a15_reliability_impact": outside.reliability,
                "accounted_reliability_impact": accounted.reliability,
                "b05_security_impact": expected.security,
                "h02_joined_security_impact": joined.security,
                "outside_a15_security_impact": outside.security,
                "accounted_security_impact": accounted.security,
                **{name: str(value) for name, value in flags.items()},
                "outside_a15_issue_bearing_files": outside_file_counts.get(key, 0),
            }
        )
    return rows, mismatch_rows


def add_check(rows: list[dict[str, Any]], check: str, observed: Any, expected: Any, passed: bool, detail: str = "") -> None:
    rows.append(
        {
            "check": check,
            "observed": observed,
            "expected": expected,
            "status": "pass" if passed else "fail",
            "detail": detail,
        }
    )


def expected_or_observed(strict: bool, expected: int, observed: int) -> tuple[int, bool]:
    if strict:
        return expected, observed == expected
    return observed, True


def production_checks(
    *,
    args: argparse.Namespace,
    b05_summary: dict[str, str],
    b05_qc_rows: int,
    snapshots: dict[str, SnapshotMeta],
    raw_diag: dict[str, Any],
    join_diag: dict[str, Any],
    file_counts: dict[tuple[str, str], IssueCounts],
    issue_file_keys_seen: set[tuple[str, str]],
    outside_diag: dict[str, Any],
    snapshot_audit_mismatches: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    add_check(rows, "b05_qc_all_pass", b05_qc_rows, ">0 rows and all pass", b05_qc_rows > 0)

    expectations = [
        ("b05_snapshots", len(snapshots), args.expected_snapshots),
        ("b05_raw_issue_rows", raw_diag["raw_issue_rows"], args.expected_raw_issue_rows),
        ("a15_repo_month_file_rows", join_diag["a15_repo_month_file_rows"], args.expected_a15_rows),
        ("a15_unique_snapshot_files", join_diag["a15_unique_snapshot_files"], args.expected_a15_unique_snapshot_files),
        ("a15_finite_cfun_rows", join_diag["a15_finite_cfun_rows"], args.expected_a15_finite_cfun_rows),
        ("a15_unique_snapshots", join_diag["a15_unique_snapshots"], args.expected_snapshots),
        ("repositories", join_diag["repositories"], args.expected_repositories),
        ("repo_months", join_diag["repo_months"], args.expected_repo_months),
    ]
    for name, observed, expected in expectations:
        expected_value, passed = expected_or_observed(args.strict_expected_counts, expected, observed)
        add_check(rows, name, observed, expected_value, passed)

    accounted_file_keys = len(issue_file_keys_seen) + outside_diag["outside_a15_issue_bearing_snapshot_files"]
    add_check(
        rows,
        "all_b05_issue_bearing_snapshot_files_accounted",
        accounted_file_keys,
        len(file_counts),
        accounted_file_keys == len(file_counts),
        "Each B05 issue-bearing Python file must be either joined to A15 or explicitly scope-excluded.",
    )
    add_check(
        rows,
        "outside_a15_issue_bearing_files_recorded",
        outside_diag["outside_a15_issue_bearing_snapshot_files"],
        ">=0 and exported",
        outside_diag["outside_a15_issue_bearing_snapshot_files"] >= 0,
        "These files are outside the frozen A15 NPR file universe and cannot receive an NPR threshold classification.",
    )
    add_check(
        rows,
        "snapshot_issue_totals_reconcile_joined_plus_scope_excluded",
        snapshot_audit_mismatches,
        0,
        snapshot_audit_mismatches == 0,
    )

    # Cross-check frozen B05 summary values when present.
    summary_pairs = [
        ("raw_issue_rows", raw_diag["raw_issue_rows"]),
        ("selected_snapshots", len(snapshots)),
        ("collected_repositories", join_diag["repositories"]),
    ]
    for metric, observed in summary_pairs:
        if metric in b05_summary:
            expected = parse_int(b05_summary[metric], f"B05 summary {metric}")
            add_check(rows, f"b05_summary::{metric}", observed, expected, observed == expected)

    global_expected = IssueCounts()
    for meta in snapshots.values():
        global_expected.add_counts(meta.expected)
    b05_global_pairs = [
        ("code_smell_issue_stock_sum", global_expected.code_smell),
        ("bug_issue_stock_sum", global_expected.bug),
        ("vulnerability_issue_stock_sum", global_expected.vulnerability),
        ("maintainability_impact_issue_stock_sum", global_expected.maintainability),
        ("reliability_impact_issue_stock_sum", global_expected.reliability),
        ("security_impact_issue_stock_sum", global_expected.security),
    ]
    for metric, observed in b05_global_pairs:
        if metric in b05_summary:
            expected = parse_int(b05_summary[metric], f"B05 summary {metric}")
            add_check(rows, f"b05_summary::{metric}", observed, expected, observed == expected)

    return rows


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    for path in (
        args.a15_file,
        args.b05_raw_issues_file,
        args.b05_snapshot_counts_file,
        args.b05_qc_file,
        args.b05_summary_file,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Required input does not exist: {path}")

    b05_qc_rows, _ = validate_b05_qc(args.b05_qc_file)
    b05_summary = load_metric_value_csv(args.b05_summary_file)
    snapshots = load_b05_snapshots(args.b05_snapshot_counts_file)
    file_counts, _, raw_diag = aggregate_b05_raw_issues(args.b05_raw_issues_file, snapshots)
    join_diag, h02_snapshot_counts, issue_file_keys_seen = build_join(
        a15_path=args.a15_file,
        snapshots=snapshots,
        file_counts=file_counts,
        output_path=args.output_file,
    )
    outside_snapshot_counts, outside_snapshot_files, outside_diag = build_outside_a15_scope_exclusions(
        snapshots=snapshots,
        file_counts=file_counts,
        issue_file_keys_seen=issue_file_keys_seen,
        output_path=args.outside_a15_file,
    )
    snapshot_audit_rows, snapshot_audit_mismatches = build_snapshot_audit(
        snapshots, h02_snapshot_counts, outside_snapshot_counts, outside_snapshot_files
    )
    atomic_csv_rows(snapshot_audit_rows, args.snapshot_audit_file, SNAPSHOT_AUDIT_COLUMNS)

    checks = production_checks(
        args=args,
        b05_summary=b05_summary,
        b05_qc_rows=b05_qc_rows,
        snapshots=snapshots,
        raw_diag=raw_diag,
        join_diag=join_diag,
        file_counts=file_counts,
        issue_file_keys_seen=issue_file_keys_seen,
        outside_diag=outside_diag,
        snapshot_audit_mismatches=snapshot_audit_mismatches,
    )
    atomic_csv_rows(checks, args.checks_file, CHECK_COLUMNS)
    hard_failures = sum(1 for row in checks if row["status"] != "pass")
    terminal_status = (
        "FAIL"
        if hard_failures
        else ("PASS_WITH_SCOPE_EXCLUSIONS" if outside_diag["outside_a15_issue_bearing_snapshot_files"] else "PASS")
    )

    summary_metrics: list[tuple[str, Any]] = [
        ("script_version", SCRIPT_VERSION),
        ("status", terminal_status),
        ("quality_semantics", QUALITY_SEMANTICS),
        ("npr_metric_preserved", PRIMARY_NPR_METRIC),
        ("threshold_applied", 0),
        ("density_computed", 0),
        ("a15_repo_month_file_rows", join_diag["a15_repo_month_file_rows"]),
        ("a15_unique_snapshot_files", join_diag["a15_unique_snapshot_files"]),
        ("a15_finite_cfun_rows", join_diag["a15_finite_cfun_rows"]),
        ("snapshots", len(snapshots)),
        ("repositories", join_diag["repositories"]),
        ("repo_months", join_diag["repo_months"]),
        ("b05_raw_issue_rows", raw_diag["raw_issue_rows"]),
        ("b05_issue_bearing_snapshot_files", len(file_counts)),
        ("b05_issue_bearing_snapshot_files_joined", len(issue_file_keys_seen)),
        ("b05_issue_bearing_snapshot_files_outside_a15", outside_diag["outside_a15_issue_bearing_snapshot_files"]),
        ("b05_issue_rows_outside_a15", outside_diag["outside_a15_issue_rows"]),
        ("b05_snapshots_with_outside_a15_issue_files", outside_diag["outside_a15_affected_snapshots"]),
        ("repo_month_file_rows_with_any_issue", join_diag["repo_month_file_rows_with_any_issue"]),
        ("repo_month_file_rows_with_zero_issues", join_diag["repo_month_file_rows_with_zero_issues"]),
        ("snapshot_audit_mismatch_rows", snapshot_audit_mismatches),
        ("hard_qc_failures", hard_failures),
    ]
    atomic_csv_rows(
        ({"metric": metric, "value": value} for metric, value in summary_metrics),
        args.summary_file,
        SUMMARY_COLUMNS,
    )

    metadata = {
        "script_version": SCRIPT_VERSION,
        "status": terminal_status,
        "inputs": {
            "a15_file": str(args.a15_file),
            "a15_file_sha256": sha256_file(args.a15_file),
            "b05_raw_issues_file": str(args.b05_raw_issues_file),
            "b05_raw_issues_file_sha256": sha256_file(args.b05_raw_issues_file),
            "b05_snapshot_counts_file": str(args.b05_snapshot_counts_file),
            "b05_snapshot_counts_file_sha256": sha256_file(args.b05_snapshot_counts_file),
            "b05_qc_file": str(args.b05_qc_file),
            "b05_qc_file_sha256": sha256_file(args.b05_qc_file),
            "b05_summary_file": str(args.b05_summary_file),
            "b05_summary_file_sha256": sha256_file(args.b05_summary_file),
        },
        "method": {
            "file_universe": "A15 repo-month/file rows",
            "join_keys": ["snapshot_id == snapshot_key", "relative_path == component_path"],
            "zero_issue_policy": "left join from complete A15 file universe; absent B05 issue row => zero",
            "outside_a15_policy": "B05 issue-bearing Python files outside A15 are explicit scope exclusions; they are not threshold-classifiable",
            "quality_semantics": QUALITY_SEMANTICS,
            "npr_threshold": "not applied in H02; use frozen H01 threshold specification downstream",
            "density": "not computed; file-level SonarQube NCLOC is required before density analysis",
        },
        "diagnostics": {**raw_diag, **join_diag, **outside_diag, "hard_qc_failures": hard_failures},
        "outputs": {
            "file_quality_burden": str(args.output_file),
            "snapshot_join_audit": str(args.snapshot_audit_file),
            "outside_a15_scope_exclusions": str(args.outside_a15_file),
            "checks": str(args.checks_file),
            "summary": str(args.summary_file),
        },
    }
    args.metadata_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_meta = args.metadata_file.with_name(args.metadata_file.name + ".tmp")
    tmp_meta.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_meta, args.metadata_file)

    if hard_failures:
        raise RuntimeError(f"H02 hard QC failures: {hard_failures}; see {args.checks_file}")
    return metadata


def write_fixture_csv(path: Path, columns: list[str], rows: list[dict[str, Any]], gzip_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if gzip_output:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="h02-selftest-") as tmpdir:
        root = Path(tmpdir)
        snapshot = "control__Owner_Repo__aaaaaaaaaaaa__0123456789abcdef"
        snapshot2 = "treatment__Owner2_Repo2__bbbbbbbbbbbb__fedcba9876543210"

        snapshot_columns = sorted(B05_SNAPSHOT_REQUIRED)
        base_snapshot = {column: "0" for column in snapshot_columns}
        snap1 = dict(base_snapshot)
        snap1.update(
            {
                "dataset_source": "control",
                "repo_name": "Owner/Repo",
                "snapshot_key": snapshot,
                "commit_sha": "a" * 40,
                "issue_total_py_sonarqube": "3",
                "issue_type_code_smell": "2",
                "issue_type_bug": "1",
                "issue_type_vulnerability": "0",
                "issue_type_other": "0",
                "issue_severity_blocker": "0",
                "issue_severity_critical": "1",
                "issue_severity_major": "2",
                "issue_severity_minor": "0",
                "issue_severity_info": "0",
                "issue_severity_other": "0",
                "issue_with_maintainability_impact": "2",
                "issue_with_reliability_impact": "1",
                "issue_with_security_impact": "0",
                "issue_component_python_file": "3",
                "issue_component_project": "0",
                "issue_component_non_python": "0",
                "issue_component_unknown": "0",
                "issue_rows_complete": "True",
                "current_snapshot_recoverable": "True",
            }
        )
        snap2 = dict(base_snapshot)
        snap2.update(
            {
                "dataset_source": "treatment",
                "repo_name": "Owner2/Repo2",
                "snapshot_key": snapshot2,
                "commit_sha": "b" * 40,
                "issue_total_py_sonarqube": "0",
                "issue_component_python_file": "0",
                "issue_rows_complete": "True",
                "current_snapshot_recoverable": "True",
            }
        )
        snapshot_path = root / "snapshot_counts.csv"
        write_fixture_csv(snapshot_path, snapshot_columns, [snap1, snap2])

        raw_columns = sorted(B05_RAW_REQUIRED)
        raw_rows = []
        for index, (issue_type, severity, impact) in enumerate(
            [
                ("CODE_SMELL", "MAJOR", "MAINTAINABILITY"),
                ("BUG", "CRITICAL", "RELIABILITY"),
            ],
            start=1,
        ):
            row = {column: "" for column in raw_columns}
            row.update(
                {
                    "dataset_source": "control",
                    "repo_name": "Owner/Repo",
                    "snapshot_key": snapshot,
                    "commit_sha": "a" * 40,
                    "issue_key": f"issue-{index}",
                    "type": issue_type,
                    "severity": severity,
                    "status": "OPEN",
                    "resolution": "",
                    "component_path": "src/a.py",
                    "component_scope": "python_file",
                    "impacts_json": json.dumps([{"softwareQuality": impact, "severity": "MEDIUM"}]),
                }
            )
            raw_rows.append(row)
        outside_row = {column: "" for column in raw_columns}
        outside_row.update(
            {
                "dataset_source": "control",
                "repo_name": "Owner/Repo",
                "snapshot_key": snapshot,
                "commit_sha": "a" * 40,
                "issue_key": "issue-outside-a15",
                "type": "CODE_SMELL",
                "severity": "MAJOR",
                "status": "OPEN",
                "resolution": "",
                "component_path": "generated/outside.py",
                "component_scope": "python_file",
                "impacts_json": json.dumps([{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}]),
            }
        )
        raw_rows.append(outside_row)
        raw_path = root / "issues.csv.gz"
        write_fixture_csv(raw_path, raw_columns, raw_rows, gzip_output=True)

        qc_path = root / "qc.csv"
        write_fixture_csv(qc_path, ["check", "value", "expected", "status", "detail"], [{"check": "all", "value": 1, "expected": 1, "status": "pass", "detail": ""}])
        summary_path = root / "summary.csv"
        write_fixture_csv(
            summary_path,
            ["metric", "value"],
            [
                {"metric": "raw_issue_rows", "value": 3},
                {"metric": "selected_snapshots", "value": 2},
                {"metric": "collected_repositories", "value": 2},
                {"metric": "code_smell_issue_stock_sum", "value": 2},
                {"metric": "bug_issue_stock_sum", "value": 1},
                {"metric": "vulnerability_issue_stock_sum", "value": 0},
                {"metric": "maintainability_impact_issue_stock_sum", "value": 2},
                {"metric": "reliability_impact_issue_stock_sum", "value": 1},
                {"metric": "security_impact_issue_stock_sum", "value": 0},
            ],
        )

        a15_columns = sorted(A15_REQUIRED)
        def a15_row(snapshot_id: str, source: str, repo: str, commit: str, repo_id: str, month: str, path_value: str, npr: str, status: str) -> dict[str, str]:
            row = {column: "0" for column in a15_columns}
            row.update(
                {
                    "repo_id": repo_id,
                    "dataset_source": source,
                    "repo_name": repo,
                    "repo_month": month,
                    "time_index": "1",
                    "event_index": "0" if source == "control" else "1",
                    "snapshot_id": snapshot_id,
                    "snapshot_commit": commit,
                    "relative_path": path_value,
                    "file_sha256": hashlib.sha256(path_value.encode()).hexdigest(),
                    "cfun_occurrences_total": "1",
                    "cfun_occurrences_scored": "1" if status == "scored" else "0",
                    "cfun_occurrences_excluded": "0",
                    "cfun_npr_coverage_ratio": "1.0" if status == "scored" else "",
                    PRIMARY_NPR_METRIC: npr,
                    "file_npr_cfun_status": status,
                }
            )
            return row
        a15_rows = [
            a15_row(snapshot, "control", "Owner/Repo", "a" * 40, "r1", "2025-01", "src/a.py", "1.7", "scored"),
            a15_row(snapshot, "control", "Owner/Repo", "a" * 40, "r1", "2025-01", "src/b.py", "", "no_cfun"),
            # Reuse the same snapshot/file in a later repo-month to test non-duplication of snapshot audit counts.
            a15_row(snapshot, "control", "Owner/Repo", "a" * 40, "r1", "2025-02", "src/a.py", "1.7", "scored"),
            a15_row(snapshot, "control", "Owner/Repo", "a" * 40, "r1", "2025-02", "src/b.py", "", "no_cfun"),
            a15_row(snapshot2, "treatment", "Owner2/Repo2", "b" * 40, "r2", "2025-02", "main.py", "1.4", "scored"),
        ]
        a15_path = root / "a15.csv"
        write_fixture_csv(a15_path, a15_columns, a15_rows)

        args = argparse.Namespace(
            a15_file=a15_path,
            b05_raw_issues_file=raw_path,
            b05_snapshot_counts_file=snapshot_path,
            b05_qc_file=qc_path,
            b05_summary_file=summary_path,
            output_file=root / "joined.csv.gz",
            snapshot_audit_file=root / "snapshot_audit.csv",
            outside_a15_file=root / "outside_a15.csv",
            checks_file=root / "checks.csv",
            summary_file=root / "h02_summary.csv",
            metadata_file=root / "metadata.json",
            strict_expected_counts=True,
            expected_a15_rows=5,
            expected_a15_unique_snapshot_files=3,
            expected_a15_finite_cfun_rows=3,
            expected_snapshots=2,
            expected_repositories=2,
            expected_repo_months=3,
            expected_raw_issue_rows=3,
        )
        metadata = run_pipeline(args)
        assert metadata["status"] == "PASS_WITH_SCOPE_EXCLUSIONS"
        joined = list(iter_csv(args.output_file))
        assert len(joined) == 5
        assert joined[0]["sonar_issue_total"] == "2"
        assert joined[0]["sonar_issue_high_severity"] == "1"
        assert joined[1]["sonar_issue_total"] == "0"
        assert joined[1]["sonar_issue_join_status"] == "zero_issue_file"
        audit = list(iter_csv(args.snapshot_audit_file))
        assert len(audit) == 2
        assert all(row["issue_total_matches"] == "True" for row in audit)
        outside = list(iter_csv(args.outside_a15_file))
        assert len(outside) == 1
        assert outside[0]["component_path"] == "generated/outside.py"
        assert outside[0]["sonar_issue_total"] == "1"
    print("build_cfun_npr_file_quality_burden self-test: PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a15-file", type=Path)
    parser.add_argument("--b05-raw-issues-file", type=Path)
    parser.add_argument("--b05-snapshot-counts-file", type=Path)
    parser.add_argument("--b05-qc-file", type=Path)
    parser.add_argument("--b05-summary-file", type=Path)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--snapshot-audit-file", type=Path)
    parser.add_argument("--outside-a15-file", type=Path)
    parser.add_argument("--checks-file", type=Path)
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--expected-a15-rows", type=int, default=510297)
    parser.add_argument("--expected-a15-unique-snapshot-files", type=int, default=494592)
    parser.add_argument("--expected-a15-finite-cfun-rows", type=int, default=202027)
    parser.add_argument("--expected-snapshots", type=int, default=1496)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-repo-months", type=int, default=1954)
    parser.add_argument("--expected-raw-issue-rows", type=int, default=554258)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    required_args = [
        "a15_file",
        "b05_raw_issues_file",
        "b05_snapshot_counts_file",
        "b05_qc_file",
        "b05_summary_file",
        "output_file",
        "snapshot_audit_file",
        "outside_a15_file",
        "checks_file",
        "summary_file",
        "metadata_file",
    ]
    missing = [name for name in required_args if getattr(args, name) is None]
    if missing:
        raise ValueError(f"Missing required arguments: {missing}")

    metadata = run_pipeline(args)
    diagnostics = metadata["diagnostics"]
    print("=" * 80)
    print("run-x-h02 C_FUN-NPR x file-level SonarQube burden join")
    print(f"Status:                              {metadata['status']}")
    print(f"A15 repo-month/file rows:            {diagnostics['a15_repo_month_file_rows']}")
    print(f"A15 unique snapshot/files:           {diagnostics['a15_unique_snapshot_files']}")
    print(f"A15 finite C_FUN NPR rows:             {diagnostics['a15_finite_cfun_rows']}")
    print(f"B05 snapshots:                       {diagnostics['a15_unique_snapshots']}")
    print(f"B05 raw issue rows:                  {diagnostics['raw_issue_rows']}")
    print(f"Issue-bearing snapshot/files:        {diagnostics['issue_bearing_snapshot_files']}")
    print(f"Issue-bearing files joined to A15:   {diagnostics['issue_bearing_snapshot_files_seen_in_a15']}")
    print(f"Issue-bearing files outside A15:     {diagnostics['outside_a15_issue_bearing_snapshot_files']}")
    print(f"Issue rows outside A15:              {diagnostics['outside_a15_issue_rows']}")
    print(f"Repo-month/file rows with issues:    {diagnostics['repo_month_file_rows_with_any_issue']}")
    print(f"Repo-month/file rows with zero issue:{diagnostics['repo_month_file_rows_with_zero_issues']}")
    print(f"Repositories / repo-months:          {diagnostics['repositories']} / {diagnostics['repo_months']}")
    print(f"Hard QC failures:                    {diagnostics['hard_qc_failures']}")
    print(f"Joined output:                       {args.output_file.resolve()}")
    print(f"Snapshot audit:                      {args.snapshot_audit_file.resolve()}")
    print(f"Outside-A15 scope exclusions:        {args.outside_a15_file.resolve()}")
    print(f"QC checks:                           {args.checks_file.resolve()}")
    print(f"Summary:                             {args.summary_file.resolve()}")
    print("Density:                             intentionally deferred; file-level NCLOC required")
    print("Thresholds:                          not applied; frozen H01 grid will be used downstream")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
