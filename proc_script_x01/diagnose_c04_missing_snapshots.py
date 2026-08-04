#!/usr/bin/env python3
"""Materialize and inspect the five unresolved C04 historical snapshots.

This diagnostic is read-only with respect to the cloned repositories and the
existing C04 outputs. It preserves each Git archive, extracted tree, file
inventory, and raw cloc stdout/stderr under a user-selected temporary root.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional


REQUIRED_COLUMNS = {
    "manifest_order",
    "repo_snapshot_key",
    "scope_role",
    "repo_name",
    "clone_path",
    "resolved_commit",
    "first_repo_month",
    "last_repo_month",
    "status",
    "error_stage",
    "error_message",
}


@dataclass
class CommandResult:
    command: str
    return_code: Optional[int]
    timed_out: bool
    runtime_seconds: float
    stdout_file: str
    stderr_file: str


@dataclass
class SnapshotDiagnostic:
    manifest_order: int
    repo_snapshot_key: str
    scope_role: str
    repo_name: str
    clone_path: str
    resolved_commit: str
    first_repo_month: str
    last_repo_month: str
    original_error_stage: str
    original_error_message: str
    diagnostic_directory: str
    git_precheck_ok: bool = False
    git_archive_return_code: Optional[int] = None
    git_archive_timed_out: bool = False
    snapshot_tar_exists: bool = False
    snapshot_tar_bytes: int = 0
    system_tar_list_return_code: Optional[int] = None
    python_tarfile_open_ok: bool = False
    python_tarfile_error: str = ""
    system_tar_extract_return_code: Optional[int] = None
    extracted_file_count: int = 0
    extracted_bytes: int = 0
    extension_count: int = 0
    cloc_summary_return_code: Optional[int] = None
    cloc_summary_csv_exists: bool = False
    cloc_summary_csv_bytes: int = 0
    cloc_stdout_csv_return_code: Optional[int] = None
    cloc_stdout_csv_bytes: int = 0
    cloc_by_file_return_code: Optional[int] = None
    cloc_by_file_csv_exists: bool = False
    cloc_by_file_csv_bytes: int = 0
    diagnostic_status: str = "pending"
    diagnostic_note: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize and manually inspect unresolved C04 snapshots."
    )
    parser.add_argument(
        "--failure-file",
        default="repo_x01/run-x-c04/python_primary_whole_repo_cloc_failures.csv",
        help="C04 failure CSV containing the unresolved snapshots.",
    )
    parser.add_argument(
        "--diagnostic-root",
        required=True,
        help="Persistent output directory, normally under /mnt/samsung850ev/tmp/.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--cloc-bin", default="cloc")
    parser.add_argument("--git-timeout-seconds", type=int, default=600)
    parser.add_argument("--cloc-timeout-seconds", type=int, default=900)
    parser.add_argument("--expected-failures", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def sanitize(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:80]}__{digest}"


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_key_value_csv(path: Path, row: dict[str, object]) -> None:
    write_csv(
        path,
        ({"field": key, "value": "" if value is None else value} for key, value in row.items()),
        ["field", "value"],
    )


def run_command(
    command: list[str],
    *,
    timeout: int,
    stdout_file: Path,
    stderr_file: Path,
) -> CommandResult:
    stdout_file.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    return_code: Optional[int]
    with stdout_file.open("wb") as stdout_handle, stderr_file.open("wb") as stderr_handle:
        try:
            process = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
                timeout=timeout,
            )
            return_code = process.returncode
        except subprocess.TimeoutExpired:
            return_code = None
            timed_out = True
    runtime = round(time.monotonic() - started, 3)
    return CommandResult(
        command=" ".join(command),
        return_code=return_code,
        timed_out=timed_out,
        runtime_seconds=runtime,
        stdout_file=str(stdout_file),
        stderr_file=str(stderr_file),
    )


def load_failures(path: Path, expected_failures: int) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Failure CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Failure CSV missing columns: {sorted(missing)}")
        rows = [dict(row) for row in reader if row.get("status", "").strip().lower() == "failed"]
    if len(rows) != expected_failures:
        raise ValueError(
            f"Expected {expected_failures} failed snapshots, but found {len(rows)} in {path}"
        )
    return rows


def resolve_clone_path(project_root: Path, clone_path_text: str) -> Path:
    clone_path = Path(clone_path_text).expanduser()
    if not clone_path.is_absolute():
        clone_path = project_root / clone_path
    return clone_path.resolve()


def inventory_tree(tree_root: Path, snapshot_dir: Path) -> tuple[int, int, int]:
    inventory_rows: list[dict[str, object]] = []
    extension_counts: Counter[str] = Counter()
    total_bytes = 0
    for path in sorted(p for p in tree_root.rglob("*") if p.is_file()):
        relative = path.relative_to(tree_root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        suffix = path.suffix.lower() or "[no-extension]"
        extension_counts[suffix] += 1
        binary_guess = False
        try:
            with path.open("rb") as handle:
                binary_guess = b"\x00" in handle.read(8192)
        except OSError:
            binary_guess = True
        inventory_rows.append(
            {
                "relative_path": relative,
                "file_name": path.name,
                "extension": suffix,
                "size_bytes": size,
                "binary_guess": int(binary_guess),
            }
        )
    write_csv(
        snapshot_dir / "file-inventory.csv",
        inventory_rows,
        ["relative_path", "file_name", "extension", "size_bytes", "binary_guess"],
    )
    extension_rows = [
        {"extension": extension, "file_count": count}
        for extension, count in sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    write_csv(snapshot_dir / "extension-summary.csv", extension_rows, ["extension", "file_count"])
    return len(inventory_rows), total_bytes, len(extension_counts)


def inspect_snapshot(
    row: dict[str, str],
    *,
    project_root: Path,
    diagnostic_root: Path,
    cloc_bin: str,
    git_timeout: int,
    cloc_timeout: int,
) -> SnapshotDiagnostic:
    manifest_order = int(row["manifest_order"])
    snapshot_name = (
        f"{manifest_order:04d}__{row['scope_role']}__{sanitize(row['repo_name'])}__"
        f"{row['resolved_commit'][:12]}"
    )
    snapshot_dir = (diagnostic_root / snapshot_name).resolve()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    tree_root = snapshot_dir / "tree"
    tree_root.mkdir(parents=True, exist_ok=True)
    archive_path = snapshot_dir / "snapshot.tar"
    clone_path = resolve_clone_path(project_root, row["clone_path"])

    diagnostic = SnapshotDiagnostic(
        manifest_order=manifest_order,
        repo_snapshot_key=row["repo_snapshot_key"],
        scope_role=row["scope_role"],
        repo_name=row["repo_name"],
        clone_path=str(clone_path),
        resolved_commit=row["resolved_commit"],
        first_repo_month=row["first_repo_month"],
        last_repo_month=row["last_repo_month"],
        original_error_stage=row["error_stage"],
        original_error_message=row["error_message"],
        diagnostic_directory=str(snapshot_dir),
    )
    write_key_value_csv(snapshot_dir / "metadata.csv", asdict(diagnostic))

    command_records: list[dict[str, object]] = []

    repo_check = run_command(
        ["git", "-C", str(clone_path), "rev-parse", "--git-dir"],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "git-rev-parse.stdout.txt",
        stderr_file=snapshot_dir / "git-rev-parse.stderr.txt",
    )
    command_records.append(asdict(repo_check))
    commit_check = run_command(
        ["git", "-C", str(clone_path), "cat-file", "-e", f"{row['resolved_commit']}^{{commit}}"],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "git-cat-file.stdout.txt",
        stderr_file=snapshot_dir / "git-cat-file.stderr.txt",
    )
    command_records.append(asdict(commit_check))
    diagnostic.git_precheck_ok = repo_check.return_code == 0 and commit_check.return_code == 0
    if not diagnostic.git_precheck_ok:
        diagnostic.diagnostic_status = "git_precheck_failed"
        diagnostic.diagnostic_note = "The clone or commit could not be validated."
        write_csv(snapshot_dir / "commands.csv", command_records, list(asdict(repo_check).keys()))
        write_key_value_csv(snapshot_dir / "diagnostic-result.csv", asdict(diagnostic))
        return diagnostic

    ls_tree = run_command(
        ["git", "-C", str(clone_path), "ls-tree", "-r", "-l", "--full-tree", row["resolved_commit"]],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "git-ls-tree.txt",
        stderr_file=snapshot_dir / "git-ls-tree.stderr.txt",
    )
    command_records.append(asdict(ls_tree))

    archive_result = run_command(
        [
            "git",
            "-C",
            str(clone_path),
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            row["resolved_commit"],
        ],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "git-archive.stdout.txt",
        stderr_file=snapshot_dir / "git-archive.stderr.txt",
    )
    command_records.append(asdict(archive_result))
    diagnostic.git_archive_return_code = archive_result.return_code
    diagnostic.git_archive_timed_out = archive_result.timed_out
    diagnostic.snapshot_tar_exists = archive_path.exists()
    diagnostic.snapshot_tar_bytes = archive_path.stat().st_size if archive_path.exists() else 0

    if archive_result.return_code != 0 or not archive_path.exists():
        diagnostic.diagnostic_status = "git_archive_failed"
        diagnostic.diagnostic_note = "Git archive did not create a usable tar file."
        write_csv(snapshot_dir / "commands.csv", command_records, list(asdict(repo_check).keys()))
        write_key_value_csv(snapshot_dir / "diagnostic-result.csv", asdict(diagnostic))
        return diagnostic

    tar_list = run_command(
        ["tar", "-tvf", str(archive_path)],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "system-tar-list.txt",
        stderr_file=snapshot_dir / "system-tar-list.stderr.txt",
    )
    command_records.append(asdict(tar_list))
    diagnostic.system_tar_list_return_code = tar_list.return_code

    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            names = archive.getnames()
        (snapshot_dir / "python-tarfile-list.txt").write_text(
            "\n".join(names) + ("\n" if names else ""), encoding="utf-8"
        )
        diagnostic.python_tarfile_open_ok = True
    except Exception as exc:  # Preserve the exact Python tarfile failure for manual review.
        diagnostic.python_tarfile_open_ok = False
        diagnostic.python_tarfile_error = f"{type(exc).__name__}: {exc}"
        (snapshot_dir / "python-tarfile-error.txt").write_text(
            diagnostic.python_tarfile_error + "\n", encoding="utf-8"
        )

    extract_result = run_command(
        ["tar", "--no-same-owner", "-xf", str(archive_path), "-C", str(tree_root)],
        timeout=git_timeout,
        stdout_file=snapshot_dir / "system-tar-extract.stdout.txt",
        stderr_file=snapshot_dir / "system-tar-extract.stderr.txt",
    )
    command_records.append(asdict(extract_result))
    diagnostic.system_tar_extract_return_code = extract_result.return_code
    if extract_result.return_code != 0:
        diagnostic.diagnostic_status = "system_tar_extract_failed"
        diagnostic.diagnostic_note = "The persistent tar was saved, but system tar extraction failed."
        write_csv(snapshot_dir / "commands.csv", command_records, list(asdict(repo_check).keys()))
        write_key_value_csv(snapshot_dir / "diagnostic-result.csv", asdict(diagnostic))
        return diagnostic

    file_count, total_bytes, extension_count = inventory_tree(tree_root, snapshot_dir)
    diagnostic.extracted_file_count = file_count
    diagnostic.extracted_bytes = total_bytes
    diagnostic.extension_count = extension_count

    cloc_summary = run_command(
        [
            cloc_bin,
            "--csv",
            "--quiet",
            "--skip-uniqueness",
            f"--out={snapshot_dir / 'cloc-summary.csv'}",
            str(tree_root),
        ],
        timeout=cloc_timeout,
        stdout_file=snapshot_dir / "cloc-summary.stdout.txt",
        stderr_file=snapshot_dir / "cloc-summary.stderr.txt",
    )
    command_records.append(asdict(cloc_summary))
    diagnostic.cloc_summary_return_code = cloc_summary.return_code
    cloc_summary_path = snapshot_dir / "cloc-summary.csv"
    diagnostic.cloc_summary_csv_exists = cloc_summary_path.exists()
    diagnostic.cloc_summary_csv_bytes = cloc_summary_path.stat().st_size if cloc_summary_path.exists() else 0

    cloc_stdout_csv = run_command(
        [cloc_bin, "--csv", "--quiet", "--skip-uniqueness", str(tree_root)],
        timeout=cloc_timeout,
        stdout_file=snapshot_dir / "cloc-stdout.csv",
        stderr_file=snapshot_dir / "cloc-stdout.stderr.txt",
    )
    command_records.append(asdict(cloc_stdout_csv))
    diagnostic.cloc_stdout_csv_return_code = cloc_stdout_csv.return_code
    stdout_csv_path = snapshot_dir / "cloc-stdout.csv"
    diagnostic.cloc_stdout_csv_bytes = stdout_csv_path.stat().st_size if stdout_csv_path.exists() else 0

    cloc_by_file = run_command(
        [
            cloc_bin,
            "--by-file",
            "--csv",
            "--quiet",
            "--skip-uniqueness",
            f"--out={snapshot_dir / 'cloc-by-file.csv'}",
            str(tree_root),
        ],
        timeout=cloc_timeout,
        stdout_file=snapshot_dir / "cloc-by-file.stdout.txt",
        stderr_file=snapshot_dir / "cloc-by-file.stderr.txt",
    )
    command_records.append(asdict(cloc_by_file))
    diagnostic.cloc_by_file_return_code = cloc_by_file.return_code
    cloc_by_file_path = snapshot_dir / "cloc-by-file.csv"
    diagnostic.cloc_by_file_csv_exists = cloc_by_file_path.exists()
    diagnostic.cloc_by_file_csv_bytes = cloc_by_file_path.stat().st_size if cloc_by_file_path.exists() else 0

    if diagnostic.cloc_summary_return_code == 0 and diagnostic.cloc_summary_csv_exists:
        diagnostic.diagnostic_status = "cloc_output_created"
        diagnostic.diagnostic_note = "cloc created a summary CSV during the persistent diagnostic run."
    elif (
        diagnostic.cloc_summary_return_code == 0
        and not diagnostic.cloc_summary_csv_exists
        and diagnostic.cloc_stdout_csv_bytes == 0
    ):
        diagnostic.diagnostic_status = "possible_zero_recognized_languages"
        diagnostic.diagnostic_note = (
            "cloc returned zero but created no summary CSV and emitted no CSV output; "
            "review file-inventory.csv and extension-summary.csv."
        )
    else:
        diagnostic.diagnostic_status = "cloc_diagnostic_failure"
        diagnostic.diagnostic_note = "Review the preserved cloc stdout and stderr files."

    write_csv(snapshot_dir / "commands.csv", command_records, list(asdict(repo_check).keys()))
    write_key_value_csv(snapshot_dir / "diagnostic-result.csv", asdict(diagnostic))
    return diagnostic


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    failure_file = Path(args.failure_file).expanduser()
    if not failure_file.is_absolute():
        failure_file = project_root / failure_file
    failure_file = failure_file.resolve()
    diagnostic_root = Path(args.diagnostic_root).expanduser().resolve()

    if diagnostic_root.exists() and any(diagnostic_root.iterdir()) and not args.overwrite:
        raise FileExistsError(
            f"Diagnostic root is not empty: {diagnostic_root}. Use a new timestamped directory or --overwrite."
        )
    diagnostic_root.mkdir(parents=True, exist_ok=True)

    if shutil.which("git") is None:
        raise RuntimeError("git was not found in PATH")
    if shutil.which("tar") is None:
        raise RuntimeError("tar was not found in PATH")
    if shutil.which(args.cloc_bin) is None:
        raise RuntimeError(f"cloc was not found: {args.cloc_bin}")

    failures = load_failures(failure_file, args.expected_failures)
    diagnostics: list[SnapshotDiagnostic] = []
    for index, row in enumerate(failures, start=1):
        print(
            f"[{index}/{len(failures)}] {row['repo_name']} {row['resolved_commit'][:12]}",
            flush=True,
        )
        diagnostics.append(
            inspect_snapshot(
                row,
                project_root=project_root,
                diagnostic_root=diagnostic_root,
                cloc_bin=args.cloc_bin,
                git_timeout=args.git_timeout_seconds,
                cloc_timeout=args.cloc_timeout_seconds,
            )
        )

    summary_rows = [asdict(item) for item in diagnostics]
    summary_columns = list(asdict(diagnostics[0]).keys()) if diagnostics else []
    write_csv(diagnostic_root / "diagnostic_summary.csv", summary_rows, summary_columns)

    status_counts = Counter(item.diagnostic_status for item in diagnostics)
    write_csv(
        diagnostic_root / "diagnostic_status_counts.csv",
        (
            {"diagnostic_status": status, "snapshot_count": count}
            for status, count in sorted(status_counts.items())
        ),
        ["diagnostic_status", "snapshot_count"],
    )
    print(f"Diagnostic root: {diagnostic_root}")
    print(f"Snapshots inspected: {len(diagnostics)}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
