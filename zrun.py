#!/usr/bin/env python3
"""
Create a compact tar.gz archive for run-x-d02 results.

Input directory
---------------
repo_x01/run-x-d02/

Special handling
----------------
The large file:

    python_fun_file_quality_burden.csv.gz

is NOT copied into the archive in full. Instead, this script extracts:

1. python_fun_file_quality_burden_header.csv
   - Contains only the original CSV header.

2. python_fun_file_quality_burden_sample.csv
   - Contains the original header plus the first N data rows.

All other regular files directly under repo_x01/run-x-d02/ are included
unchanged in the archive.

Output
------
run-x-d02-results-audit.tar.gz

The archive preserves the relative directory:

    repo_x01/run-x-d02/

so extracted files remain easy to associate with the experiment.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import shutil
import tarfile
import tempfile
from pathlib import Path


DEFAULT_INPUT_DIR = Path("repo_x01/run-x-d02")
DEFAULT_LARGE_FILE = "python_fun_file_quality_burden.csv.gz"
DEFAULT_OUTPUT = Path("run-x-d02-results-audit.tar.gz")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package run-x-d02 results with a compact burden CSV sample."
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing run-x-d02 output files.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output tar.gz filename.",
    )

    parser.add_argument(
        "--sample-rows",
        type=int,
        default=10,
        help="Number of burden CSV data rows to include in the sample.",
    )

    return parser.parse_args()


def validate_inputs(
    input_dir: Path,
    large_file_path: Path,
    sample_rows: int,
) -> None:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    if not large_file_path.is_file():
        raise FileNotFoundError(
            f"Large burden CSV not found: {large_file_path}"
        )

    if sample_rows < 1:
        raise ValueError("--sample-rows must be at least 1")


def extract_header_and_sample(
    input_gz: Path,
    header_output: Path,
    sample_output: Path,
    sample_rows: int,
) -> int:
    """
    Extract the CSV header and the first N data rows from a gzip CSV.

    Returns
    -------
    int
        Number of data rows written to the sample file.
    """
    with gzip.open(
        input_gz,
        "rt",
        newline="",
        encoding="utf-8",
    ) as input_file:
        reader = csv.reader(input_file)

        try:
            header = next(reader)
        except StopIteration as exc:
            raise RuntimeError(
                f"Compressed CSV is empty: {input_gz}"
            ) from exc

        with header_output.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as header_file:
            writer = csv.writer(header_file)
            writer.writerow(header)

        copied_rows = 0

        with sample_output.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as sample_file:
            writer = csv.writer(sample_file)
            writer.writerow(header)

            for row in reader:
                writer.writerow(row)
                copied_rows += 1

                if copied_rows >= sample_rows:
                    break

    return copied_rows


def copy_other_files(
    input_dir: Path,
    staging_run_dir: Path,
    excluded_filename: str,
) -> list[Path]:
    """
    Copy all other regular files from run-x-d02 unchanged.

    The large burden CSV is deliberately excluded because only its header
    and sample are included in the compact archive.
    """
    copied_files: list[Path] = []

    for source_path in sorted(input_dir.iterdir()):
        if not source_path.is_file():
            continue

        if source_path.name == excluded_filename:
            continue

        destination_path = staging_run_dir / source_path.name
        shutil.copy2(source_path, destination_path)
        copied_files.append(destination_path)

    return copied_files


def create_archive(
    staging_root: Path,
    output_path: Path,
) -> None:
    """
    Create the final gzip-compressed tar archive.

    The archive starts at repo_x01/run-x-d02 so that the original
    experiment directory structure is preserved.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    archive_root = staging_root / "repo_x01" / "run-x-d02"

    with tarfile.open(output_path, "w:gz") as archive:
        archive.add(
            archive_root,
            arcname="repo_x01/run-x-d02",
        )


def main() -> int:
    args = parse_args()

    input_dir = args.input_dir
    large_file_path = input_dir / DEFAULT_LARGE_FILE

    validate_inputs(
        input_dir=input_dir,
        large_file_path=large_file_path,
        sample_rows=args.sample_rows,
    )

    with tempfile.TemporaryDirectory(
        prefix="run-x-d02-package-"
    ) as temp_dir:
        staging_root = Path(temp_dir)

        staging_run_dir = (
            staging_root
            / "repo_x01"
            / "run-x-d02"
        )
        staging_run_dir.mkdir(parents=True, exist_ok=True)

        header_output = (
            staging_run_dir
            / "python_fun_file_quality_burden_header.csv"
        )

        sample_output = (
            staging_run_dir
            / "python_fun_file_quality_burden_sample.csv"
        )

        copied_rows = extract_header_and_sample(
            input_gz=large_file_path,
            header_output=header_output,
            sample_output=sample_output,
            sample_rows=args.sample_rows,
        )

        copied_files = copy_other_files(
            input_dir=input_dir,
            staging_run_dir=staging_run_dir,
            excluded_filename=DEFAULT_LARGE_FILE,
        )

        create_archive(
            staging_root=staging_root,
            output_path=args.output,
        )

    print("run-x-d02 archive created successfully.")
    print(f"Output: {args.output}")
    print(f"Input directory: {input_dir}")
    print(f"Excluded full file: {large_file_path}")
    print(f"Sample rows copied: {copied_rows}")
    print(f"Other files included: {len(copied_files)}")
    print("")
    print("Generated diagnostic files:")
    print("  repo_x01/run-x-d02/python_fun_file_quality_burden_header.csv")
    print("  repo_x01/run-x-d02/python_fun_file_quality_burden_sample.csv")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())