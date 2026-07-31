#!/usr/bin/env python3
"""Extract outcome-blind Git evidence for run-py-7f03 source candidates.

The script reads only run-py-7f03 parse-audit outputs and local Git clones. It
verifies each historical commit:path mapping, extracts the exact Git blob, and
writes compact error-line context for manual review. Parser v2 requires Python
3.13 and reproduces the run-py-7f02 v2 dual-parse policy: first parse with
``type_comments=True`` and retry with ``type_comments=False`` only after a
primary failure. It does not read function roles, AGC/HWC labels, DiD panels,
treatment effects, or confidence intervals.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from typing import Any, Iterable, Sequence


ALLOWED_SOURCES = frozenset({"control", "treatment"})
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
LINE_RE = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)
SCRIPT_VERSION = "run-py-7f04-v2"
PARSER_VERSION = (
    "python-ast-parse-evidence-v2-dual-type-comments-"
    f"py{sys.version_info.major}.{sys.version_info.minor}"
)
RUN7F02_PARSER_VERSION = (
    "python-ast-raw-structure-v2-dual-type-comments-"
    f"py{sys.version_info.major}.{sys.version_info.minor}"
)
REQUIRED_PYTHON_MAJOR_MINOR = (3, 13)
PARSE_MODE_PRIMARY = "type_comments_true"
PARSE_MODE_FALLBACK = "type_comments_false_fallback"
PARSE_MODE_DUAL_FAILURE = "type_comments_true_and_false_failed"
PARSE_MODE_NOT_ATTEMPTED = "parse_not_attempted"

MANUAL_REQUIRED = frozenset(
    {
        "dataset_source",
        "repo_name",
        "relative_path",
        "git_blob_sha",
        "error_type",
        "error_message",
        "repository_commit_occurrences",
        "repository_month_occurrences",
        "commits_json",
        "months_json",
        "review_decision",
        "review_note",
    }
)

CLASSIFICATION_REQUIRED = frozenset(
    {
        "dataset_source",
        "repo_name",
        "latest_commit",
        "relative_path",
        "git_blob_sha",
        "error_type",
        "error_message",
        "path_category",
        "manual_review_required",
    }
)

VERIFICATION_FIELDS = (
    "review_id",
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "expected_git_blob_sha",
    "repository_directory",
    "repository_exists",
    "is_git_repository",
    "commit_exists",
    "path_exists_at_commit",
    "git_mode",
    "git_object_type",
    "actual_git_blob_sha",
    "blob_sha_matches",
    "verification_status",
    "verification_error",
)

EVIDENCE_FIELDS = (
    "review_id",
    "dataset_source",
    "repo_name",
    "relative_path",
    "git_blob_sha",
    "expected_error_type",
    "expected_error_message",
    "fresh_parse_status",
    "fresh_parse_mode",
    "fresh_error_type",
    "fresh_error_message",
    "fresh_primary_error_type",
    "fresh_primary_error_message",
    "fresh_fallback_error_type",
    "fresh_fallback_error_message",
    "error_line",
    "error_offset",
    "error_end_line",
    "error_end_offset",
    "context_start_line",
    "context_end_line",
    "source_encoding",
    "source_bytes",
    "physical_lines",
    "content_sha256",
    "git_object_hash_recomputed",
    "git_object_hash_matches",
    "git_modes_json",
    "git_object_types_json",
    "verified_commit_occurrences",
    "expected_commit_occurrences",
    "repository_month_occurrences",
    "commits_json",
    "months_json",
    "is_git_lfs_pointer",
    "is_symlink_mode",
    "contains_merge_conflict_marker",
    "contains_template_marker",
    "contains_notebook_magic",
    "probable_python2_syntax",
    "contains_null_byte",
    "diagnostic_flags_json",
    "raw_blob_file",
    "context_file",
    "review_decision",
    "review_note",
)

QC_FIELDS = (
    "check_name",
    "severity",
    "passed",
    "observed",
    "expected",
    "note",
)


class ValidationError(RuntimeError):
    """Raised when an input or Git invariant is violated."""


def require_supported_python() -> None:
    """Require the same Python major/minor used by the production v2 scan."""
    observed = (sys.version_info.major, sys.version_info.minor)
    if observed != REQUIRED_PYTHON_MAJOR_MINOR:
        required = ".".join(str(item) for item in REQUIRED_PYTHON_MAJOR_MINOR)
        found = ".".join(str(item) for item in observed)
        raise RuntimeError(
            f"Python {required}.x is required for run-py-7f04 v2; found {found}."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual-review-input", type=Path)
    parser.add_argument("--failure-classification-input", type=Path)
    parser.add_argument(
        "--treatment-clone-dir", type=Path, default=Path("../treatment-repos")
    )
    parser.add_argument(
        "--control-clone-dir", type=Path, default=Path("../control-repos")
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--context-lines", type=int, default=8)
    parser.add_argument("--expected-review-rows", type=int, default=0)
    parser.add_argument("--expected-commit-occurrences", type=int, default=0)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args()


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def stable_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_list(values: Iterable[str]) -> str:
    return json.dumps(sorted({str(value) for value in values}), ensure_ascii=False)


def parse_int(value: Any, label: str) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        raise ValidationError(f"{label} must be a non-negative integer: {value!r}")
    return int(text)


def parse_json_strings(value: str, label: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON for {label}: {error}") from error
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValidationError(f"{label} must be a JSON array of strings")
    if len(parsed) != len(set(parsed)):
        raise ValidationError(f"{label} contains duplicate values")
    return parsed


def validate_source(value: str, label: str) -> str:
    source = value.strip()
    if source not in ALLOWED_SOURCES:
        raise ValidationError(f"Invalid dataset_source for {label}: {value!r}")
    return source


def validate_repo_name(value: str, label: str) -> str:
    repo = value.strip()
    parts = repo.split("/")
    if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
        raise ValidationError(f"Invalid repo_name for {label}: {value!r}")
    return repo


def validate_relative_path(value: str, label: str) -> str:
    text = value.strip()
    path = PurePosixPath(text)
    if (
        not text
        or "\x00" in text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValidationError(f"Unsafe relative_path for {label}: {value!r}")
    return text


def validate_sha(value: str, label: str) -> str:
    sha = value.strip().lower()
    if not FULL_SHA_RE.fullmatch(sha):
        raise ValidationError(f"Invalid Git SHA for {label}: {value!r}")
    return sha


def read_csv(path: Path, required: frozenset[str], label: str) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Missing or empty {label}: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = required - set(fields)
        if missing:
            raise ValidationError(
                f"Missing columns in {label}: {sorted(missing)}; available={fields}"
            )
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValidationError(f"No rows found in {label}: {path}")
    return rows


def manual_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row["dataset_source"],
        row["repo_name"],
        row["relative_path"],
        row["git_blob_sha"],
    )


def normalize_inputs(
    manual_rows: list[dict[str, str]],
    classification_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    normalized_manual: list[dict[str, Any]] = []
    seen_manual: set[tuple[str, str, str, str]] = set()
    for number, raw in enumerate(manual_rows, start=2):
        label = f"manual-review row {number}"
        row: dict[str, Any] = dict(raw)
        row["dataset_source"] = validate_source(raw["dataset_source"], label)
        row["repo_name"] = validate_repo_name(raw["repo_name"], label)
        row["relative_path"] = validate_relative_path(raw["relative_path"], label)
        row["git_blob_sha"] = validate_sha(raw["git_blob_sha"], label)
        row["repository_commit_occurrences"] = parse_int(
            raw["repository_commit_occurrences"], f"{label} commit occurrences"
        )
        row["repository_month_occurrences"] = parse_int(
            raw["repository_month_occurrences"], f"{label} month occurrences"
        )
        commits = parse_json_strings(raw["commits_json"], f"{label} commits_json")
        months = parse_json_strings(raw["months_json"], f"{label} months_json")
        commits = [validate_sha(value, f"{label} commit") for value in commits]
        if len(commits) != row["repository_commit_occurrences"]:
            raise ValidationError(
                f"{label} commit count does not match commits_json: "
                f"{row['repository_commit_occurrences']} != {len(commits)}"
            )
        if len(months) != row["repository_month_occurrences"]:
            raise ValidationError(
                f"{label} month count does not match months_json: "
                f"{row['repository_month_occurrences']} != {len(months)}"
            )
        if raw["review_decision"].strip() or raw["review_note"].strip():
            raise ValidationError(
                f"{label} already contains a manual decision; run-py-7f04 "
                "requires the untouched outcome-blind run-py-7f03 inventory"
            )
        row["_commits"] = commits
        row["_months"] = months
        key = manual_key(row)
        if key in seen_manual:
            raise ValidationError(f"Duplicate manual-review key: {key}")
        seen_manual.add(key)
        normalized_manual.append(row)

    normalized_classification: list[dict[str, str]] = []
    seen_occurrences: set[tuple[str, str, str, str, str]] = set()
    for number, raw in enumerate(classification_rows, start=2):
        if raw["path_category"].strip() != "source_candidate":
            continue
        if raw["manual_review_required"].strip().lower() not in {"1", "true"}:
            continue
        label = f"failure-classification row {number}"
        row = dict(raw)
        row["dataset_source"] = validate_source(raw["dataset_source"], label)
        row["repo_name"] = validate_repo_name(raw["repo_name"], label)
        row["latest_commit"] = validate_sha(raw["latest_commit"], label)
        row["relative_path"] = validate_relative_path(raw["relative_path"], label)
        row["git_blob_sha"] = validate_sha(raw["git_blob_sha"], label)
        key = manual_key(row)
        if key not in seen_manual:
            raise ValidationError(
                f"Source-candidate classification row has no manual-review key: {key}"
            )
        occurrence = (
            row["dataset_source"],
            row["repo_name"],
            row["latest_commit"],
            row["relative_path"],
            row["git_blob_sha"],
        )
        if occurrence in seen_occurrences:
            raise ValidationError(f"Duplicate source-candidate occurrence: {occurrence}")
        seen_occurrences.add(occurrence)
        normalized_classification.append(row)

    classification_by_key: dict[tuple[str, str, str, str], set[str]] = {}
    for row in normalized_classification:
        classification_by_key.setdefault(manual_key(row), set()).add(row["latest_commit"])
    for row in normalized_manual:
        key = manual_key(row)
        actual = classification_by_key.get(key, set())
        expected = set(row["_commits"])
        if actual != expected:
            raise ValidationError(
                f"Commit coverage mismatch for {key}: "
                f"manual={sorted(expected)}, classification={sorted(actual)}"
            )

    normalized_manual.sort(key=manual_key)
    unique_blobs = {row["git_blob_sha"] for row in normalized_manual}
    if len(unique_blobs) != len(normalized_manual):
        raise ValidationError(
            "The run-py-7f03 source-candidate inventory must contain one row "
            "per unique Git blob for raw-blob extraction"
        )
    normalized_classification.sort(
        key=lambda row: (
            row["dataset_source"],
            row["repo_name"],
            row["relative_path"],
            row["git_blob_sha"],
            row["latest_commit"],
        )
    )
    return normalized_manual, normalized_classification


def run_git(
    repo_dir: Path,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git_message(result: subprocess.CompletedProcess[bytes]) -> str:
    payload = result.stderr or result.stdout
    return payload.decode("utf-8", errors="replace").strip()


def parse_ls_tree(payload: bytes) -> tuple[str, str, str, str]:
    entries = [item for item in payload.split(b"\0") if item]
    if len(entries) != 1:
        raise ValidationError(f"Expected one git ls-tree entry; found {len(entries)}")
    metadata, path_bytes = entries[0].split(b"\t", 1)
    mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
    relative_path = path_bytes.decode("utf-8", errors="surrogateescape")
    return mode, object_type, object_id.lower(), relative_path


def decode_source(payload: bytes) -> tuple[str, str, str]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(payload).readline)
        return payload.decode(encoding), encoding, ""
    except Exception as error:
        return payload.decode("utf-8", errors="replace"), "utf-8-replacement", str(error)


def safe_error_message(error: BaseException) -> str:
    return str(error).replace("\x00", "\\0")


def record_error(result: dict[str, Any], prefix: str, error: BaseException) -> None:
    result[f"{prefix}_error_type"] = type(error).__name__
    result[f"{prefix}_error_message"] = safe_error_message(error)


def parse_source(payload: bytes) -> dict[str, Any]:
    source, encoding, decode_error = decode_source(payload)
    result: dict[str, Any] = {
        "source": source,
        "source_encoding": encoding,
        "decode_error": decode_error,
        "parse_status": "success",
        "parse_mode": PARSE_MODE_NOT_ATTEMPTED,
        "error_type": "",
        "error_message": "",
        "primary_error_type": "",
        "primary_error_message": "",
        "fallback_error_type": "",
        "fallback_error_message": "",
        "error_line": 0,
        "error_offset": 0,
        "error_end_line": 0,
        "error_end_offset": 0,
    }
    try:
        ast.parse(source, filename="<git-blob>", type_comments=True)
        result["parse_mode"] = PARSE_MODE_PRIMARY
        return result
    except Exception as primary_error:
        record_error(result, "primary", primary_error)

    try:
        ast.parse(source, filename="<git-blob>", type_comments=False)
        result["parse_mode"] = PARSE_MODE_FALLBACK
        return result
    except Exception as fallback_error:
        record_error(result, "fallback", fallback_error)
        result["parse_status"] = "failure"
        result["parse_mode"] = PARSE_MODE_DUAL_FAILURE
        result["error_type"] = type(fallback_error).__name__
        result["error_message"] = safe_error_message(fallback_error)
        result["error_line"] = int(getattr(fallback_error, "lineno", 0) or 0)
        result["error_offset"] = int(getattr(fallback_error, "offset", 0) or 0)
        result["error_end_line"] = int(
            getattr(fallback_error, "end_lineno", 0) or 0
        )
        result["error_end_offset"] = int(
            getattr(fallback_error, "end_offset", 0) or 0
        )
    return result


def expected_error_line(message: str) -> int:
    matches = LINE_RE.findall(message)
    return int(matches[-1]) if matches else 0


def diagnose_payload(payload: bytes, source: str, modes: set[str]) -> dict[str, Any]:
    stripped = payload.lstrip()
    lfs = stripped.startswith(b"version https://git-lfs.github.com/spec/v1")
    conflict = bool(re.search(r"(?m)^(?:<<<<<<<|=======|>>>>>>>)", source))
    template = any(token in source for token in ("{{", "}}", "{%", "%}"))
    notebook_magic = bool(re.search(r"(?m)^\s*(?:%{1,2}|!)[A-Za-z]", source))
    python2 = any(
        (
            re.search(r"(?m)^\s*print\s+(?!\()\S", source),
            re.search(r"(?m)^\s*except\s+[^:\n]+,\s*\w+\s*:", source),
            re.search(r"(?m)^\s*raise\s+\w+\s*,", source),
            re.search(r"\b\d+[lL]\b", source),
            "xrange(" in source,
        )
    )
    flags: list[str] = []
    if lfs:
        flags.append("git_lfs_pointer")
    if "120000" in modes:
        flags.append("symlink_mode")
    if conflict:
        flags.append("merge_conflict_marker")
    if template:
        flags.append("template_marker")
    if notebook_magic:
        flags.append("notebook_magic")
    if python2:
        flags.append("probable_python2_syntax")
    if b"\x00" in payload:
        flags.append("null_byte")
    if not flags:
        flags.append("none_detected")
    return {
        "is_git_lfs_pointer": int(lfs),
        "is_symlink_mode": int("120000" in modes),
        "contains_merge_conflict_marker": int(conflict),
        "contains_template_marker": int(template),
        "contains_notebook_magic": int(notebook_magic),
        "probable_python2_syntax": int(python2),
        "contains_null_byte": int(b"\x00" in payload),
        "diagnostic_flags_json": json.dumps(flags, ensure_ascii=False),
    }


def recompute_git_hash(repo_dir: Path, payload: bytes) -> str:
    result = run_git(repo_dir, ["hash-object", "--stdin"], input_bytes=payload)
    if result.returncode != 0:
        raise RuntimeError(f"git hash-object failed: {git_message(result)}")
    return result.stdout.decode("ascii").strip().lower()


def safe_context_text(text: str) -> str:
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def render_context_packet(
    evidence: dict[str, Any],
    source: str,
) -> str:
    lines = source.splitlines()
    error_line = int(evidence["error_line"])
    start = int(evidence["context_start_line"])
    end = int(evidence["context_end_line"])
    rendered: list[str] = [
        f"Review ID: {evidence['review_id']}",
        f"Dataset source: {evidence['dataset_source']}",
        f"Repository: {evidence['repo_name']}",
        f"Path: {evidence['relative_path']}",
        f"Git blob SHA: {evidence['git_blob_sha']}",
        f"Git modes: {evidence['git_modes_json']}",
        f"Expected parse error: {evidence['expected_error_type']}: {evidence['expected_error_message']}",
        f"Fresh parse mode: {evidence['fresh_parse_mode']}",
        f"Fresh parse error: {evidence['fresh_error_type']}: {evidence['fresh_error_message']}",
        f"Primary parse error: {evidence['fresh_primary_error_type']}: {evidence['fresh_primary_error_message']}",
        f"Fallback parse error: {evidence['fresh_fallback_error_type']}: {evidence['fresh_fallback_error_message']}",
        f"Diagnostic flags: {evidence['diagnostic_flags_json']}",
        f"Commit occurrences: {evidence['commits_json']}",
        f"Month occurrences: {evidence['months_json']}",
        "",
        f"Source context (lines {start}-{end}; '>' marks the error line):",
    ]
    width = max(4, len(str(end)))
    for line_number in range(start, end + 1):
        marker = ">" if line_number == error_line else " "
        content = lines[line_number - 1] if 1 <= line_number <= len(lines) else ""
        rendered.append(
            f"{marker} {line_number:>{width}} | {safe_context_text(content)}"
        )
    rendered.extend(
        [
            "",
            "Manual review fields:",
            "review_decision=",
            "review_note=",
            "",
        ]
    )
    return "\n".join(rendered)


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def add_qc(
    rows: list[dict[str, Any]],
    name: str,
    severity: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
) -> None:
    rows.append(
        {
            "check_name": name,
            "severity": severity,
            "passed": str(bool(passed)),
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def prepare_output(output_dir: Path, overwrite: bool) -> tuple[Path, Path]:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists; set --overwrite-output to replace it: {output_dir}"
            )
        marker = output_dir / "run-py-7f04-extraction-metadata.json"
        if not marker.is_file():
            raise ValidationError(
                f"Refusing to replace an unrecognized output directory: {output_dir}"
            )
    staging = output_dir.with_name(f".{output_dir.name}.staging-{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"Staging directory already exists: {staging}")
    staging.mkdir(parents=True)
    (staging / "blobs").mkdir()
    (staging / "contexts").mkdir()
    return output_dir, staging


def finalize_output(output_dir: Path, staging: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    os.replace(staging, output_dir)


def extract_contexts(
    *,
    manual_path: Path,
    classification_path: Path,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    output_dir: Path,
    context_lines: int,
    expected_review_rows: int,
    expected_commit_occurrences: int,
    overwrite: bool,
) -> dict[str, Any]:
    if context_lines < 0 or context_lines > 100:
        raise ValidationError("context-lines must be between 0 and 100")
    manual_path = manual_path.resolve()
    classification_path = classification_path.resolve()
    treatment_clone_dir = treatment_clone_dir.resolve()
    control_clone_dir = control_clone_dir.resolve()
    if not treatment_clone_dir.is_dir():
        raise FileNotFoundError(f"Treatment clone directory not found: {treatment_clone_dir}")
    if not control_clone_dir.is_dir():
        raise FileNotFoundError(f"Control clone directory not found: {control_clone_dir}")

    raw_manual = read_csv(manual_path, MANUAL_REQUIRED, "manual-review input")
    raw_classification = read_csv(
        classification_path,
        CLASSIFICATION_REQUIRED,
        "failure-classification input",
    )
    manual_rows, classification_rows = normalize_inputs(raw_manual, raw_classification)
    output_dir, staging = prepare_output(output_dir, overwrite)

    manual_ids = {manual_key(row): f"source-review-{number:03d}" for number, row in enumerate(manual_rows, 1)}
    roots = {"treatment": treatment_clone_dir, "control": control_clone_dir}
    verification_rows: list[dict[str, Any]] = []
    verification_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    repo_cache: dict[Path, tuple[bool, str]] = {}

    for row in classification_rows:
        key = manual_key(row)
        repo_dir = roots[row["dataset_source"]] / repo_slug(row["repo_name"])
        output: dict[str, Any] = {
            "review_id": manual_ids[key],
            "dataset_source": row["dataset_source"],
            "repo_name": row["repo_name"],
            "latest_commit": row["latest_commit"],
            "relative_path": row["relative_path"],
            "expected_git_blob_sha": row["git_blob_sha"],
            "repository_directory": str(repo_dir),
            "repository_exists": int(repo_dir.is_dir()),
            "is_git_repository": 0,
            "commit_exists": 0,
            "path_exists_at_commit": 0,
            "git_mode": "",
            "git_object_type": "",
            "actual_git_blob_sha": "",
            "blob_sha_matches": 0,
            "verification_status": "failure",
            "verification_error": "",
        }
        try:
            if not repo_dir.is_dir():
                raise FileNotFoundError(f"Repository directory not found: {repo_dir}")
            if repo_dir not in repo_cache:
                probe = run_git(repo_dir, ["rev-parse", "--is-inside-work-tree"])
                ok = probe.returncode == 0 and probe.stdout.strip() == b"true"
                repo_cache[repo_dir] = (ok, git_message(probe) if not ok else "")
            is_git, repo_error = repo_cache[repo_dir]
            output["is_git_repository"] = int(is_git)
            if not is_git:
                raise ValidationError(repo_error or "Directory is not a Git work tree")

            commit = run_git(
                repo_dir,
                ["cat-file", "-e", f"{row['latest_commit']}^{{commit}}"],
            )
            output["commit_exists"] = int(commit.returncode == 0)
            if commit.returncode != 0:
                raise ValidationError(
                    f"Commit unavailable: {row['latest_commit']}: {git_message(commit)}"
                )

            tree = run_git(
                repo_dir,
                ["ls-tree", "-r", "--full-tree", "-z", row["latest_commit"], "--", row["relative_path"]],
            )
            if tree.returncode != 0:
                raise ValidationError(f"git ls-tree failed: {git_message(tree)}")
            if not tree.stdout:
                raise FileNotFoundError(
                    f"Path not found at commit: {row['relative_path']}"
                )
            mode, object_type, object_id, actual_path = parse_ls_tree(tree.stdout)
            if actual_path != row["relative_path"]:
                raise ValidationError(
                    f"Path mismatch: expected={row['relative_path']!r}, actual={actual_path!r}"
                )
            output["path_exists_at_commit"] = 1
            output["git_mode"] = mode
            output["git_object_type"] = object_type
            output["actual_git_blob_sha"] = object_id
            output["blob_sha_matches"] = int(object_id == row["git_blob_sha"])
            if object_type != "blob":
                raise ValidationError(f"Path object is not a blob: {object_type}")
            if object_id != row["git_blob_sha"]:
                raise ValidationError(
                    f"Blob mismatch: expected={row['git_blob_sha']}, actual={object_id}"
                )
            output["verification_status"] = "success"
        except Exception as error:
            output["verification_error"] = f"{type(error).__name__}: {error}"
        verification_rows.append(output)
        verification_by_key.setdefault(key, []).append(output)

    evidence_rows: list[dict[str, Any]] = []
    extraction_errors: list[str] = []
    for row in manual_rows:
        key = manual_key(row)
        review_id = manual_ids[key]
        verifies = verification_by_key.get(key, [])
        successes = [item for item in verifies if item["verification_status"] == "success"]
        repo_dir = roots[row["dataset_source"]] / repo_slug(row["repo_name"])
        payload = b""
        extract_error = ""
        if successes:
            result = run_git(repo_dir, ["cat-file", "blob", row["git_blob_sha"]])
            if result.returncode == 0:
                payload = result.stdout
            else:
                extract_error = f"git cat-file blob failed: {git_message(result)}"
        else:
            extract_error = "No verified commit:path occurrence is available"
        if extract_error:
            extraction_errors.append(f"{review_id}: {extract_error}")

        parsed = parse_source(payload) if not extract_error else {
            "source": "",
            "source_encoding": "",
            "decode_error": extract_error,
            "parse_status": "not_run",
            "parse_mode": PARSE_MODE_NOT_ATTEMPTED,
            "error_type": "",
            "error_message": "",
            "primary_error_type": "",
            "primary_error_message": "",
            "fallback_error_type": "",
            "fallback_error_message": "",
            "error_line": 0,
            "error_offset": 0,
            "error_end_line": 0,
            "error_end_offset": 0,
        }
        modes = {str(item["git_mode"]) for item in successes if item["git_mode"]}
        object_types = {
            str(item["git_object_type"])
            for item in successes
            if item["git_object_type"]
        }
        recomputed = ""
        if not extract_error:
            try:
                recomputed = recompute_git_hash(repo_dir, payload)
            except Exception as error:
                extraction_errors.append(f"{review_id}: {error}")

        line_count = payload.count(b"\n") + int(bool(payload) and not payload.endswith(b"\n"))
        error_line = int(parsed["error_line"] or expected_error_line(row["error_message"]))
        if line_count:
            error_line = min(max(error_line, 1), line_count)
            start = max(1, error_line - context_lines)
            end = min(line_count, error_line + context_lines)
        else:
            start = 0
            end = 0
        diagnostics = diagnose_payload(payload, str(parsed["source"]), modes)
        raw_relative = f"blobs/{row['git_blob_sha']}.py"
        context_relative = f"contexts/{row['git_blob_sha']}.txt"
        evidence: dict[str, Any] = {
            "review_id": review_id,
            "dataset_source": row["dataset_source"],
            "repo_name": row["repo_name"],
            "relative_path": row["relative_path"],
            "git_blob_sha": row["git_blob_sha"],
            "expected_error_type": row["error_type"],
            "expected_error_message": row["error_message"],
            "fresh_parse_status": parsed["parse_status"],
            "fresh_parse_mode": parsed["parse_mode"],
            "fresh_error_type": parsed["error_type"],
            "fresh_error_message": parsed["error_message"],
            "fresh_primary_error_type": parsed["primary_error_type"],
            "fresh_primary_error_message": parsed["primary_error_message"],
            "fresh_fallback_error_type": parsed["fallback_error_type"],
            "fresh_fallback_error_message": parsed["fallback_error_message"],
            "error_line": error_line,
            "error_offset": parsed["error_offset"],
            "error_end_line": parsed["error_end_line"],
            "error_end_offset": parsed["error_end_offset"],
            "context_start_line": start,
            "context_end_line": end,
            "source_encoding": parsed["source_encoding"],
            "source_bytes": len(payload),
            "physical_lines": line_count,
            "content_sha256": hashlib.sha256(payload).hexdigest() if not extract_error else "",
            "git_object_hash_recomputed": recomputed,
            "git_object_hash_matches": int(recomputed == row["git_blob_sha"]),
            "git_modes_json": json_list(modes),
            "git_object_types_json": json_list(object_types),
            "verified_commit_occurrences": len(successes),
            "expected_commit_occurrences": row["repository_commit_occurrences"],
            "repository_month_occurrences": row["repository_month_occurrences"],
            "commits_json": row["commits_json"],
            "months_json": row["months_json"],
            **diagnostics,
            "raw_blob_file": raw_relative,
            "context_file": context_relative,
            "review_decision": "",
            "review_note": "",
        }
        evidence_rows.append(evidence)
        if not extract_error:
            (staging / raw_relative).write_bytes(payload)
            packet = render_context_packet(evidence, str(parsed["source"]))
            (staging / context_relative).write_text(packet, encoding="utf-8")

    qc_rows: list[dict[str, Any]] = []
    add_qc(
        qc_rows,
        "manual_review_row_count",
        "critical" if expected_review_rows else "diagnostic",
        not expected_review_rows or len(manual_rows) == expected_review_rows,
        len(manual_rows),
        expected_review_rows or "not specified",
        "The source-candidate review inventory must have the expected number of rows.",
    )
    add_qc(
        qc_rows,
        "commit_occurrence_count",
        "critical" if expected_commit_occurrences else "diagnostic",
        not expected_commit_occurrences or len(verification_rows) == expected_commit_occurrences,
        len(verification_rows),
        expected_commit_occurrences or "not specified",
        "Every source-candidate repository-commit occurrence must be verified.",
    )
    verification_successes = sum(
        row["verification_status"] == "success" for row in verification_rows
    )
    add_qc(
        qc_rows,
        "all_commit_paths_verified",
        "critical",
        verification_successes == len(verification_rows),
        verification_successes,
        len(verification_rows),
        "Each historical commit:path must resolve to the expected Git blob.",
    )
    extracted = sum(bool(row["content_sha256"]) for row in evidence_rows)
    add_qc(
        qc_rows,
        "all_unique_blobs_extracted",
        "critical",
        extracted == len(evidence_rows),
        extracted,
        len(evidence_rows),
        "Every manual-review blob must be extracted as exact raw bytes.",
    )
    hash_matches = sum(bool(row["git_object_hash_matches"]) for row in evidence_rows)
    add_qc(
        qc_rows,
        "all_extracted_blob_hashes_match",
        "critical",
        hash_matches == len(evidence_rows),
        hash_matches,
        len(evidence_rows),
        "Recomputed Git object hashes must equal run-py-7f03 blob SHAs.",
    )
    failure_reproduced = sum(row["fresh_parse_status"] == "failure" for row in evidence_rows)
    add_qc(
        qc_rows,
        "all_parse_failures_reproduced",
        "critical",
        failure_reproduced == len(evidence_rows),
        failure_reproduced,
        len(evidence_rows),
        "The current parser must reproduce a failure for each audited blob.",
    )
    dual_failures = sum(
        row["fresh_parse_mode"] == PARSE_MODE_DUAL_FAILURE for row in evidence_rows
    )
    add_qc(
        qc_rows,
        "all_v2_dual_parse_failures_reproduced",
        "critical",
        dual_failures == len(evidence_rows),
        dual_failures,
        len(evidence_rows),
        "Every audited blob must fail both v2 parse attempts.",
    )
    exact_error_types = sum(
        row["fresh_error_type"] == row["expected_error_type"] for row in evidence_rows
    )
    add_qc(
        qc_rows,
        "fresh_error_types_match_run7f03",
        "diagnostic",
        exact_error_types == len(evidence_rows),
        exact_error_types,
        len(evidence_rows),
        "Exact exception types are parser-version-sensitive; mismatches remain visible.",
    )
    add_qc(
        qc_rows,
        "review_decisions_remain_blank",
        "critical",
        all(not row["review_decision"] and not row["review_note"] for row in evidence_rows),
        sum(bool(row["review_decision"] or row["review_note"]) for row in evidence_rows),
        0,
        "Evidence extraction must not make outcome-informed manual decisions.",
    )
    critical_failures = [
        row for row in qc_rows if row["severity"] == "critical" and row["passed"] != "True"
    ]
    status = "PASS" if not critical_failures else "FAIL"

    write_csv(
        staging / "run-py-7f04-commit-path-verification.csv",
        VERIFICATION_FIELDS,
        verification_rows,
    )
    write_csv(
        staging / "run-py-7f04-manual-review-evidence.csv",
        EVIDENCE_FIELDS,
        evidence_rows,
    )
    write_csv(staging / "run-py-7f04-extraction-qc.csv", QC_FIELDS, qc_rows)

    metadata = {
        "schema_version": SCRIPT_VERSION,
        "status": status,
        "purpose": "Outcome-blind Git blob and parse-error context extraction",
        "python_version": sys.version.split()[0],
        "python_version_info": {
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
            "micro": sys.version_info.micro,
        },
        "parser_version": PARSER_VERSION,
        "run_py_7f02_parser_version_reproduced": RUN7F02_PARSER_VERSION,
        "parse_policy": {
            "primary": "ast.parse(type_comments=True)",
            "fallback": "ast.parse(type_comments=False) after primary failure",
            "required_failure_mode": PARSE_MODE_DUAL_FAILURE,
        },
        "context_lines_each_side": context_lines,
        "inputs": {
            "manual_review_input": str(manual_path),
            "manual_review_input_sha256": stable_sha256(manual_path),
            "failure_classification_input": str(classification_path),
            "failure_classification_input_sha256": stable_sha256(classification_path),
            "treatment_clone_dir": str(treatment_clone_dir),
            "control_clone_dir": str(control_clone_dir),
            "agc_hwc_inputs": "NONE",
            "did_outcome_inputs": "NONE",
            "function_role_taxonomy": "NONE",
        },
        "counts": {
            "manual_review_rows": len(manual_rows),
            "unique_failed_blobs": len({row["git_blob_sha"] for row in manual_rows}),
            "repositories": len(
                {(row["dataset_source"], row["repo_name"]) for row in manual_rows}
            ),
            "repository_paths": len(
                {
                    (row["dataset_source"], row["repo_name"], row["relative_path"])
                    for row in manual_rows
                }
            ),
            "commit_path_occurrences": len(verification_rows),
            "verified_commit_path_occurrences": verification_successes,
            "extracted_blobs": extracted,
            "parse_failures_reproduced": failure_reproduced,
            "dual_parse_failures_reproduced": dual_failures,
            "primary_parse_successes": sum(
                row["fresh_parse_mode"] == PARSE_MODE_PRIMARY for row in evidence_rows
            ),
            "fallback_parse_successes": sum(
                row["fresh_parse_mode"] == PARSE_MODE_FALLBACK for row in evidence_rows
            ),
            "git_lfs_pointers": sum(row["is_git_lfs_pointer"] for row in evidence_rows),
            "symlink_mode_blobs": sum(row["is_symlink_mode"] for row in evidence_rows),
            "merge_conflict_marker_blobs": sum(
                row["contains_merge_conflict_marker"] for row in evidence_rows
            ),
            "template_marker_blobs": sum(row["contains_template_marker"] for row in evidence_rows),
            "notebook_magic_blobs": sum(row["contains_notebook_magic"] for row in evidence_rows),
            "probable_python2_syntax_blobs": sum(
                row["probable_python2_syntax"] for row in evidence_rows
            ),
            "critical_qc_failures": len(critical_failures),
            "extraction_errors": len(extraction_errors),
        },
        "extraction_errors": extraction_errors,
        "outputs": {
            "commit_path_verification": "run-py-7f04-commit-path-verification.csv",
            "manual_review_evidence": "run-py-7f04-manual-review-evidence.csv",
            "qc": "run-py-7f04-extraction-qc.csv",
            "raw_blob_directory": "blobs",
            "context_directory": "contexts",
        },
    }
    metadata_path = staging / "run-py-7f04-extraction-metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    finalize_output(output_dir, staging, overwrite)

    print(
        "Context extraction complete: "
        f"review_rows={len(manual_rows)}, "
        f"commit_path_occurrences={len(verification_rows)}, "
        f"verified={verification_successes}, extracted_blobs={extracted}, "
        f"parse_failures_reproduced={failure_reproduced}, "
        f"critical_qc_failures={len(critical_failures)}"
    )
    print(f"Status: {status}")
    if status != "PASS":
        names = ", ".join(row["check_name"] for row in critical_failures)
        raise SystemExit(f"run-py-7f04 critical QC failure: {names}")
    return metadata


def git(repo: Path, *arguments: str) -> str:
    result = run_git(repo, list(arguments))
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed: {git_message(result)}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def initialize_test_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "run-py-7f04@example.invalid")
    git(repo, "config", "user.name", "run-py-7f04 self-test")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def write_rows(path: Path, fields: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(path, fields, rows)


def run_self_test() -> None:
    require_supported_python()
    fallback_payload = b'''#     type: Literal["feature"]
def valid_after_ordinary_comment():
    return 1
'''
    fallback_result = parse_source(fallback_payload)
    assert fallback_result["parse_status"] == "success"
    assert fallback_result["parse_mode"] == PARSE_MODE_FALLBACK
    assert fallback_result["primary_error_type"] == "SyntaxError"
    assert fallback_result["fallback_error_type"] == ""

    python_313_payload = b'''class Box[T = int]:
    def get(self, value: T) -> T:
        return value
'''
    python_313_result = parse_source(python_313_payload)
    assert python_313_result["parse_status"] == "success"
    assert python_313_result["parse_mode"] == PARSE_MODE_PRIMARY

    with tempfile.TemporaryDirectory(prefix="run-py-7f04-self-test-") as temp:
        root = Path(temp)
        treatment_root = root / "treatment-repos"
        control_root = root / "control-repos"
        treatment_root.mkdir()
        control_root.mkdir()

        control_repo = control_root / "example_control"
        initialize_test_repo(control_repo)
        lfs_payload = (
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            b"size 123\n"
        )
        (control_repo / "model.py").write_bytes(lfs_payload)
        control_commit = commit_all(control_repo, "Add LFS pointer")
        control_blob = git(control_repo, "rev-parse", f"{control_commit}:model.py")

        treatment_repo = treatment_root / "example_treatment"
        initialize_test_repo(treatment_repo)
        (treatment_repo / "src").mkdir()
        broken_payload = b"def broken(:\n    pass\n"
        (treatment_repo / "src" / "app.py").write_bytes(broken_payload)
        treatment_commit_1 = commit_all(treatment_repo, "Add broken source")
        treatment_blob = git(
            treatment_repo, "rev-parse", f"{treatment_commit_1}:src/app.py"
        )
        (treatment_repo / "README.md").write_text("self-test\n", encoding="utf-8")
        treatment_commit_2 = commit_all(treatment_repo, "Keep source blob")

        control_error = parse_source(lfs_payload)
        treatment_error = parse_source(broken_payload)
        manual_fields = tuple(MANUAL_REQUIRED)
        manual_rows = [
            {
                "dataset_source": "control",
                "repo_name": "example/control",
                "relative_path": "model.py",
                "git_blob_sha": control_blob,
                "error_type": control_error["error_type"],
                "error_message": control_error["error_message"],
                "repository_commit_occurrences": 1,
                "repository_month_occurrences": 1,
                "commits_json": json.dumps([control_commit]),
                "months_json": json.dumps(["2025-01"]),
                "review_decision": "",
                "review_note": "",
            },
            {
                "dataset_source": "treatment",
                "repo_name": "example/treatment",
                "relative_path": "src/app.py",
                "git_blob_sha": treatment_blob,
                "error_type": treatment_error["error_type"],
                "error_message": treatment_error["error_message"],
                "repository_commit_occurrences": 2,
                "repository_month_occurrences": 2,
                "commits_json": json.dumps([treatment_commit_1, treatment_commit_2]),
                "months_json": json.dumps(["2025-01", "2025-02"]),
                "review_decision": "",
                "review_note": "",
            },
        ]
        classification_fields = tuple(CLASSIFICATION_REQUIRED)
        classification_rows: list[dict[str, Any]] = []
        for manual in manual_rows:
            for commit in json.loads(str(manual["commits_json"])):
                classification_rows.append(
                    {
                        "dataset_source": manual["dataset_source"],
                        "repo_name": manual["repo_name"],
                        "latest_commit": commit,
                        "relative_path": manual["relative_path"],
                        "git_blob_sha": manual["git_blob_sha"],
                        "error_type": manual["error_type"],
                        "error_message": manual["error_message"],
                        "path_category": "source_candidate",
                        "manual_review_required": "1",
                    }
                )
        manual_path = root / "manual.csv"
        classification_path = root / "classification.csv"
        write_rows(manual_path, manual_fields, manual_rows)
        write_rows(classification_path, classification_fields, classification_rows)
        output = root / "output"
        metadata = extract_contexts(
            manual_path=manual_path,
            classification_path=classification_path,
            treatment_clone_dir=treatment_root,
            control_clone_dir=control_root,
            output_dir=output,
            context_lines=2,
            expected_review_rows=2,
            expected_commit_occurrences=3,
            overwrite=False,
        )
        counts = metadata["counts"]
        assert metadata["schema_version"] == SCRIPT_VERSION
        assert metadata["parser_version"] == PARSER_VERSION
        assert (
            metadata["run_py_7f02_parser_version_reproduced"]
            == RUN7F02_PARSER_VERSION
        )
        assert metadata["status"] == "PASS"
        assert counts["manual_review_rows"] == 2
        assert counts["commit_path_occurrences"] == 3
        assert counts["verified_commit_path_occurrences"] == 3
        assert counts["extracted_blobs"] == 2
        assert counts["parse_failures_reproduced"] == 2
        assert counts["dual_parse_failures_reproduced"] == 2
        assert counts["primary_parse_successes"] == 0
        assert counts["fallback_parse_successes"] == 0
        assert counts["git_lfs_pointers"] == 1
        assert len(list((output / "blobs").glob("*.py"))) == 2
        assert len(list((output / "contexts").glob("*.txt"))) == 2
    print("Self-test: PASS")


def main() -> None:
    require_supported_python()
    args = parse_args()
    if args.self_test_only:
        run_self_test()
        return
    required = {
        "--manual-review-input": args.manual_review_input,
        "--failure-classification-input": args.failure_classification_input,
        "--output-dir": args.output_dir,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit(f"Missing required arguments: {', '.join(missing)}")
    extract_contexts(
        manual_path=args.manual_review_input,
        classification_path=args.failure_classification_input,
        treatment_clone_dir=args.treatment_clone_dir,
        control_clone_dir=args.control_clone_dir,
        output_dir=args.output_dir,
        context_lines=args.context_lines,
        expected_review_rows=args.expected_review_rows,
        expected_commit_occurrences=args.expected_commit_occurrences,
        overwrite=args.overwrite_output,
    )


if __name__ == "__main__":
    main()
