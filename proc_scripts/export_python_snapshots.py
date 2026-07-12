#!/usr/bin/env python3
"""Export tracked Python files from the exact commits used by SonarQube."""
# 
# Usage: 
# PYTHONUNBUFFERED=1 python proc_scripts/export_python_snapshots.py 2>&1 | tee logs/run-py-3a_export_python_snapshots_strict_$(date +%Y%m%d-%H%M%S).log 

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pandas as pd

EXCLUDED_PARTS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".next", ".nuxt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--treatment-input",
        default="repo_python/run-py-2b/strict/treatment/ts_repos_monthly_scanned_python_only.csv",
    )
    parser.add_argument(
        "--control-input",
        default="repo_python/run-py-2b/strict/control/ts_repos_monthly_scanned_python_only.csv",
    )
    parser.add_argument("--treatment-clone-dir", default="../treatment-repos")
    parser.add_argument("--control-clone-dir", default="../control-repos")
    parser.add_argument("--output-dir", default="repo_python/run-py-3a/strict")
    parser.add_argument("--overwrite-incomplete", action="store_true")
    parser.add_argument("--max-unique-commits", type=int, default=0)
    return parser.parse_args()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


def load_rows(csv_path: Path, source: str, clone_dir: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    if not clone_dir.is_dir():
        raise FileNotFoundError(clone_dir)

    df = pd.read_csv(csv_path)
    time_col = "month" if "month" in df.columns else "time" if "time" in df.columns else None
    required = {"repo_name", "latest_commit"}
    if time_col is None or not required.issubset(df.columns):
        raise ValueError(f"Required columns are missing in {csv_path}")

    out = df[["repo_name", time_col, "latest_commit"]].copy()
    out.columns = ["repo_name", "month", "latest_commit"]
    out["dataset_source"] = source
    out["clone_dir"] = str(clone_dir.resolve())
    for column in ["repo_name", "month", "latest_commit"]:
        out[column] = out[column].astype(str).str.strip()
    if out[["repo_name", "month", "latest_commit"]].isin(["", "nan"]).any().any():
        raise ValueError(f"Blank repo/month/commit value in {csv_path}")
    return out


def eligible(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def list_python_blobs(repo: Path, commit: str) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    for item in git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not item:
            continue
        metadata, path_bytes = item.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
        path_text = path_bytes.decode("utf-8", errors="surrogateescape")
        if object_type == "blob" and eligible(path_text):
            records.append((mode, object_id, path_text))
    return records


def read_blob(proc: subprocess.Popen[bytes], object_id: str) -> bytes:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(object_id.encode("ascii") + b"\n")
    proc.stdin.flush()
    header = proc.stdout.readline().rstrip(b"\n").split()
    if len(header) != 3 or header[1] != b"blob":
        raise RuntimeError(f"Unexpected git cat-file response for {object_id}: {header}")
    size = int(header[2])
    data = proc.stdout.read(size)
    if len(data) != size or proc.stdout.read(1) != b"\n":
        raise RuntimeError(f"Incomplete Git blob: {object_id}")
    return data


def export_snapshot(
    repo: Path,
    source: str,
    repo_name: str,
    commit: str,
    snapshot_dir: Path,
    overwrite_incomplete: bool,
) -> dict:
    metadata_path = snapshot_dir / "_snapshot.json"
    file_list_path = snapshot_dir / "_files.jsonl"
    if metadata_path.is_file() and file_list_path.is_file():
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    if snapshot_dir.exists():
        if not overwrite_incomplete:
            raise RuntimeError(f"Incomplete snapshot exists: {snapshot_dir}")
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True)

    entries = list_python_blobs(repo, commit)
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    file_rows: list[dict] = []
    total_bytes = 0

    try:
        for mode, object_id, relative_path in entries:
            data = read_blob(proc, object_id)
            destination = snapshot_dir / Path(relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)

            if mode == "120000":
                destination.symlink_to(data.decode("utf-8", errors="surrogateescape"))
                file_type = "symlink"
            else:
                destination.write_bytes(data)
                file_type = "file"

            total_bytes += len(data)
            file_rows.append({
                "dataset_source": source,
                "repo_name": repo_name,
                "commit": commit,
                "relative_path": relative_path,
                "git_mode": mode,
                "git_blob_sha": object_id,
                "file_type": file_type,
                "content_sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "line_count": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
                "snapshot_file": str(destination),
            })
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        return_code = proc.wait()
        if return_code != 0:
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"git cat-file failed: {stderr}")

    with file_list_path.open("w", encoding="utf-8") as handle:
        for row in file_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    metadata = {
        "dataset_source": source,
        "repo_name": repo_name,
        "commit": commit,
        "snapshot_dir": str(snapshot_dir),
        "python_file_count": len(file_rows),
        "total_bytes": total_bytes,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection": "tracked **/*.py after the explicit Python-only SonarQube exclusions",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, path)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    snapshot_root = output_dir / "python_snapshots"

    rows = pd.concat([
        load_rows(Path(args.treatment_input), "treatment", Path(args.treatment_clone_dir)),
        load_rows(Path(args.control_input), "control", Path(args.control_clone_dir)),
    ], ignore_index=True).sort_values(["dataset_source", "repo_name", "month"])

    duplicates = rows.duplicated(["dataset_source", "repo_name", "month"]).sum()
    if duplicates:
        raise ValueError(f"Duplicate source/repo/month rows: {duplicates}")

    unique = rows.drop_duplicates(["dataset_source", "repo_name", "latest_commit"])
    if args.max_unique_commits > 0:
        unique = unique.head(args.max_unique_commits)
        keys = set(zip(unique.dataset_source, unique.repo_name, unique.latest_commit))
        rows = rows[rows.apply(
            lambda row: (row.dataset_source, row.repo_name, row.latest_commit) in keys,
            axis=1,
        )]

    print(f"Repo-month rows: {len(rows)}", flush=True)
    print(f"Unique repo commits: {len(unique)}", flush=True)
    print(f"Output directory: {output_dir}", flush=True)

    metadata_by_key: dict[tuple[str, str, str], dict] = {}
    failures: list[dict] = []

    for number, row in enumerate(unique.itertuples(index=False), start=1):
        source, repo_name, commit = row.dataset_source, row.repo_name, row.latest_commit
        repo_slug = repo_name.replace("/", "_")
        repo = Path(row.clone_dir) / repo_slug
        snapshot_dir = snapshot_root / source / repo_slug / commit
        print(f"[{number}/{len(unique)}] {source} {repo_name} {commit[:12]}", flush=True)
        try:
            if not repo.is_dir():
                raise FileNotFoundError(repo)
            git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
            metadata = export_snapshot(
                repo, source, repo_name, commit, snapshot_dir, args.overwrite_incomplete
            )
            metadata_by_key[(source, repo_name, commit)] = metadata
            print(f"  Python files: {metadata['python_file_count']}", flush=True)
        except Exception as exc:
            failures.append({
                "dataset_source": source,
                "repo_name": repo_name,
                "commit": commit,
                "repo_dir": str(repo),
                "error": str(exc),
            })
            print(f"  ERROR: {exc}", file=sys.stderr, flush=True)

    repo_month_rows: list[dict] = []
    for row in rows.itertuples(index=False):
        metadata = metadata_by_key.get((row.dataset_source, row.repo_name, row.latest_commit))
        if metadata is None:
            continue
        repo_month_rows.append({
            "dataset_source": row.dataset_source,
            "repo_name": row.repo_name,
            "month": row.month,
            "latest_commit": row.latest_commit,
            "snapshot_dir": metadata["snapshot_dir"],
            "python_file_count": metadata["python_file_count"],
            "total_bytes": metadata["total_bytes"],
            "has_python_files": int(metadata["python_file_count"] > 0),
        })

    file_rows: list[dict] = []
    for metadata in metadata_by_key.values():
        file_list = Path(metadata["snapshot_dir"]) / "_files.jsonl"
        with file_list.open("r", encoding="utf-8") as handle:
            file_rows.extend(json.loads(line) for line in handle if line.strip())

    write_csv(
        output_dir / "repo_month_snapshot_manifest.csv",
        repo_month_rows,
        ["dataset_source", "repo_name", "month", "latest_commit", "snapshot_dir",
         "python_file_count", "total_bytes", "has_python_files"],
    )
    write_csv(
        output_dir / "python_file_manifest.csv",
        file_rows,
        ["dataset_source", "repo_name", "commit", "relative_path", "git_mode",
         "git_blob_sha", "file_type", "content_sha256", "size_bytes", "line_count",
         "snapshot_file"],
    )
    write_csv(
        output_dir / "snapshot_failures.csv",
        failures,
        ["dataset_source", "repo_name", "commit", "repo_dir", "error"],
    )

    zero_python = sum(row["has_python_files"] == 0 for row in repo_month_rows)
    print(f"Saved repo-month rows: {len(repo_month_rows)}", flush=True)
    print(f"Saved unique Python files: {len(file_rows)}", flush=True)
    print(f"Repo-month rows with zero Python files: {zero_python}", flush=True)
    print(f"Failures: {len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
