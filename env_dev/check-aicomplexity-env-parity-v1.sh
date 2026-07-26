#!/usr/bin/env bash
#
# Compare the selab3 aicomplexity environment with the current system12/173
# reference snapshot.
#
# This script is read-only. It does not install, remove, or update packages.
#
# Comparison levels:
#   1. R package names and versions.
#   2. Conda package names, versions, and builds.
#   3. Runtime versions and critical DiD packages.
#   4. Primary DiD analytical CSV outputs.
#
# Exact Conda equality is reported separately because selab3 uses an
# Ubuntu 20.04-compatible compiler sysroot while system12 uses a newer one.

set -euo pipefail

ENV_NAME="aicomplexity"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

REFERENCE_ROOT="${SCRIPT_DIR}/logs-173/extracted/logs/env-check"

REFERENCE_DIR="$(
    find "${REFERENCE_ROOT}" \
        -maxdepth 1 \
        -type d \
        -name 'aicomplexity-173-*' \
        | sort \
        | tail -1
)"

if [[ -z "${REFERENCE_DIR}" ]]; then
    echo "ERROR: No system12/173 reference snapshot was found under:"
    echo "  ${REFERENCE_ROOT}"
    exit 1
fi

REFERENCE_R_PACKAGES="${REFERENCE_DIR}/r-installed-packages-current.csv"
REFERENCE_CONDA_LIST="${REFERENCE_DIR}/conda-list-current.txt"
REFERENCE_R_SESSION="${REFERENCE_DIR}/r-session-info-current.txt"
REFERENCE_SYSTEM="${REFERENCE_DIR}/system-summary.txt"

RUN_TS="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${SCRIPT_DIR}/logs/env-parity/aicomplexity-selab3-vs-173-${RUN_TS}"

CURRENT_R_PACKAGES="${OUTPUT_DIR}/selab3-r-installed-packages.csv"
CURRENT_CONDA_JSON="${OUTPUT_DIR}/selab3-conda-list.json"
CURRENT_CONDA_EXPLICIT="${OUTPUT_DIR}/selab3-conda-explicit.txt"
CURRENT_RUNTIME="${OUTPUT_DIR}/selab3-runtime.txt"

R_COMPARISON="${OUTPUT_DIR}/r-package-comparison.csv"
R_SUMMARY="${OUTPUT_DIR}/r-package-comparison-summary.txt"

CONDA_COMPARISON="${OUTPUT_DIR}/conda-package-comparison.csv"
CONDA_SUMMARY="${OUTPUT_DIR}/conda-package-comparison-summary.txt"

DID_SUMMARY="${OUTPUT_DIR}/primary-did-output-comparison.txt"
FINAL_SUMMARY="${OUTPUT_DIR}/final-parity-summary.txt"

mkdir -p "${OUTPUT_DIR}"

for required_file in \
    "${REFERENCE_R_PACKAGES}" \
    "${REFERENCE_CONDA_LIST}" \
    "${REFERENCE_R_SESSION}" \
    "${REFERENCE_SYSTEM}"
do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Missing or empty reference file:"
        echo "  ${required_file}"
        exit 1
    fi
done

if ! conda env list |
    awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
    grep -Fxq "${ENV_NAME}"
then
    echo "ERROR: Conda environment does not exist: ${ENV_NAME}"
    exit 1
fi

echo "============================================================"
echo "AICOMPLEXITY ENVIRONMENT PARITY CHECK"
echo "============================================================"
echo "Project root:    ${PROJECT_ROOT}"
echo "Environment:     ${ENV_NAME}"
echo "173 reference:   ${REFERENCE_DIR}"
echo "Output:          ${OUTPUT_DIR}"
echo

echo "============================================================"
echo "1. EXPORT CURRENT SELAB3 ENVIRONMENT"
echo "============================================================"

conda list \
    --name "${ENV_NAME}" \
    --json \
    > "${CURRENT_CONDA_JSON}"

conda list \
    --name "${ENV_NAME}" \
    --explicit \
    > "${CURRENT_CONDA_EXPLICIT}"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript - "${CURRENT_R_PACKAGES}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)
output_file <- args[[1]]

installed_matrix <- installed.packages()

packages <- data.frame(
  Package = installed_matrix[, "Package"],
  Version = installed_matrix[, "Version"],
  LibPath = installed_matrix[, "LibPath"],
  Built = installed_matrix[, "Built"],
  Priority = installed_matrix[, "Priority"],
  stringsAsFactors = FALSE,
  row.names = NULL
)

packages <- packages[order(packages$Package, packages$LibPath), ]
packages <- packages[!duplicated(packages$Package), ]

write.csv(
  packages,
  output_file,
  row.names = FALSE,
  quote = TRUE
)
RS

{
    echo "Date: $(date)"
    echo "Hostname: $(hostname)"
    echo "User: $(whoami)"
    echo

    conda run --no-capture-output -n "${ENV_NAME}" \
        Rscript -e 'cat(R.version.string, "\n")'

    conda run --no-capture-output -n "${ENV_NAME}" \
        python --version

    conda run --no-capture-output -n "${ENV_NAME}" \
        pandoc --version |
        head -2

    echo
    echo "Build toolchain:"

    conda list -n "${ENV_NAME}" |
        grep -E \
            '^(r-base|sysroot_linux-64|kernel-headers_linux-64|gcc_linux-64|gxx_linux-64)[[:space:]]' \
        || true
} | tee "${CURRENT_RUNTIME}"

echo
echo "============================================================"
echo "2. COMPARE R PACKAGE NAMES AND VERSIONS"
echo "============================================================"

python - \
    "${REFERENCE_R_PACKAGES}" \
    "${CURRENT_R_PACKAGES}" \
    "${R_COMPARISON}" \
    "${R_SUMMARY}" <<'PY'
import csv
import sys
from pathlib import Path

reference_path = Path(sys.argv[1])
current_path = Path(sys.argv[2])
comparison_path = Path(sys.argv[3])
summary_path = Path(sys.argv[4])


def read_manifest(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["Package"]: row["Version"]
            for row in csv.DictReader(handle)
        }


reference = read_manifest(reference_path)
current = read_manifest(current_path)

package_names = sorted(set(reference) | set(current))
rows = []

for package in package_names:
    expected = reference.get(package, "")
    actual = current.get(package, "")

    if package not in reference:
        status = "extra_on_selab3"
    elif package not in current:
        status = "missing_on_selab3"
    elif expected != actual:
        status = "version_mismatch"
    else:
        status = "match"

    rows.append(
        {
            "Package": package,
            "ExpectedVersion173": expected,
            "ActualVersionSelab3": actual,
            "Status": status,
        }
    )

with comparison_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "Package",
            "ExpectedVersion173",
            "ActualVersionSelab3",
            "Status",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

matched = sum(row["Status"] == "match" for row in rows)
missing = sum(row["Status"] == "missing_on_selab3" for row in rows)
mismatched = sum(row["Status"] == "version_mismatch" for row in rows)
extra = sum(row["Status"] == "extra_on_selab3" for row in rows)
differences = missing + mismatched + extra

summary_lines = [
    f"reference_r_packages={len(reference)}",
    f"selab3_r_packages={len(current)}",
    f"matched_r_packages={matched}",
    f"missing_r_packages={missing}",
    f"version_mismatches={mismatched}",
    f"extra_r_packages={extra}",
    f"r_package_differences={differences}",
]

summary_path.write_text(
    "\n".join(summary_lines) + "\n",
    encoding="utf-8",
)

print("\n".join(summary_lines))
PY

echo
echo "R package differences:"

awk -F',' '
    NR == 1 {
        next
    }
    {
        gsub(/"/, "", $0)
    }
    $NF != "match" {
        print
    }
' "${R_COMPARISON}" || true

echo
echo "============================================================"
echo "3. COMPARE CONDA PACKAGE VERSIONS AND BUILDS"
echo "============================================================"

python - \
    "${REFERENCE_CONDA_LIST}" \
    "${CURRENT_CONDA_JSON}" \
    "${CONDA_COMPARISON}" \
    "${CONDA_SUMMARY}" <<'PY'
import csv
import json
import sys
from pathlib import Path

reference_path = Path(sys.argv[1])
current_path = Path(sys.argv[2])
comparison_path = Path(sys.argv[3])
summary_path = Path(sys.argv[4])


def read_reference_conda_list(path: Path) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        fields = line.split()

        if len(fields) < 3:
            continue

        name = fields[0]
        version = fields[1]
        build = fields[2]
        channel = fields[3] if len(fields) >= 4 else ""

        result[name] = (version, build, channel)

    return result


def read_current_conda_json(path: Path) -> dict[str, tuple[str, str, str]]:
    rows = json.loads(path.read_text(encoding="utf-8"))

    return {
        row["name"]: (
            row.get("version", ""),
            row.get("build_string", row.get("build", "")),
            row.get("channel", ""),
        )
        for row in rows
    }


reference = read_reference_conda_list(reference_path)
current = read_current_conda_json(current_path)

package_names = sorted(set(reference) | set(current))
rows = []

for package in package_names:
    expected = reference.get(package, ("", "", ""))
    actual = current.get(package, ("", "", ""))

    if package not in reference:
        status = "extra_on_selab3"
    elif package not in current:
        status = "missing_on_selab3"
    elif expected[:2] != actual[:2]:
        status = "version_or_build_difference"
    else:
        status = "match"

    rows.append(
        {
            "Package": package,
            "Version173": expected[0],
            "Build173": expected[1],
            "VersionSelab3": actual[0],
            "BuildSelab3": actual[1],
            "Status": status,
        }
    )

with comparison_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "Package",
            "Version173",
            "Build173",
            "VersionSelab3",
            "BuildSelab3",
            "Status",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

matched = sum(row["Status"] == "match" for row in rows)
missing = sum(row["Status"] == "missing_on_selab3" for row in rows)
different = sum(
    row["Status"] == "version_or_build_difference"
    for row in rows
)
extra = sum(row["Status"] == "extra_on_selab3" for row in rows)
total_differences = missing + different + extra

summary_lines = [
    f"reference_conda_packages={len(reference)}",
    f"selab3_conda_packages={len(current)}",
    f"matched_conda_packages={matched}",
    f"missing_conda_packages={missing}",
    f"version_or_build_differences={different}",
    f"extra_conda_packages={extra}",
    f"conda_package_differences={total_differences}",
]

summary_path.write_text(
    "\n".join(summary_lines) + "\n",
    encoding="utf-8",
)

print("\n".join(summary_lines))
PY

echo
echo "Important Conda differences:"

awk -F',' '
    NR == 1 {
        next
    }
    {
        gsub(/"/, "", $0)
    }
    $1 ~ /^(r-base|python|pandoc|sysroot_linux-64|kernel-headers_linux-64|gcc_linux-64|gxx_linux-64)$/ {
        print
    }
' "${CONDA_COMPARISON}" || true

echo
echo "============================================================"
echo "4. VERIFY CRITICAL DID PACKAGES"
echo "============================================================"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript - <<'RS'
expected <- c(
  didimputation = "0.5.1",
  fixest = "0.14.1",
  data.table = "1.17.8",
  knitr = "1.50",
  lifecycle = "1.0.4",
  rlang = "1.1.6",
  rmarkdown = "2.29",
  dplyr = "1.1.4",
  ggplot2 = "3.5.2",
  tidyr = "1.3.1",
  readr = "2.1.5",
  modelsummary = "2.6.0",
  sandwich = "3.1-1",
  zoo = "1.8-15",
  plm = "2.6-7",
  sysfonts = "0.8.9",
  showtextdb = "3.0",
  showtext = "0.9-8"
)

installed_matrix <- installed.packages()
versions <- setNames(
  installed_matrix[, "Version"],
  installed_matrix[, "Package"]
)

failure_count <- 0L

for (package in names(expected)) {
  actual <- unname(versions[package])

  if (is.na(actual)) {
    actual <- "MISSING"
  }

  status <- if (identical(actual, expected[[package]])) {
    "PASS"
  } else {
    failure_count <- failure_count + 1L
    "FAIL"
  }

  cat(
    sprintf(
      "%-18s expected=%-10s actual=%-10s %s\n",
      package,
      expected[[package]],
      actual,
      status
    )
  )
}

quit(status = ifelse(failure_count == 0L, 0L, 1L))
RS

echo
echo "============================================================"
echo "5. COMPARE PRIMARY DID ANALYTICAL OUTPUTS"
echo "============================================================"

CURRENT_ROOT="repo_python/run-py-5f/strict"
BACKUP_ROOT="bak/run-py-5f/run-py-5f-before-selab3-20260726-003639/strict"

SPECIFICATIONS=(
    "full/paper_ncloc/calendar_month"
    "full/python_snapshot_ncloc/calendar_month"
    "ratio/paper_ncloc/calendar_month"
    "ratio/python_snapshot_ncloc/calendar_month"
)

CORE_FILES=(
    "borusyak_agc_commit_function_static_effects.csv"
    "borusyak_agc_commit_function_dynamic_effects.csv"
    "borusyak_agc_commit_function_panel_checks.csv"
    "borusyak_agc_commit_function_input_summary.csv"
    "borusyak_agc_commit_function_final_model_validation.csv"
    "borusyak_agc_commit_function_static_errors.csv"
    "borusyak_agc_commit_function_dynamic_errors.csv"
)

did_difference_count=0
did_identical_count=0

{
    for specification in "${SPECIFICATIONS[@]}"; do
        echo "[${specification}]"

        for file in "${CORE_FILES[@]}"; do
            current_file="${CURRENT_ROOT}/${specification}/${file}"
            backup_file="${BACKUP_ROOT}/${specification}/${file}"

            if [[ ! -f "${current_file}" || ! -f "${backup_file}" ]]; then
                echo "MISSING: ${file}"
                did_difference_count=$((did_difference_count + 1))
                continue
            fi

            if cmp -s "${backup_file}" "${current_file}"; then
                echo "IDENTICAL: ${file}"
                did_identical_count=$((did_identical_count + 1))
            else
                echo "DIFFERENT: ${file}"
                did_difference_count=$((did_difference_count + 1))
            fi
        done

        echo
    done

    echo "primary_did_identical_files=${did_identical_count}"
    echo "primary_did_different_or_missing_files=${did_difference_count}"
} | tee "${DID_SUMMARY}"

R_DIFFERENCES="$(
    awk -F= \
        '$1 == "r_package_differences" {print $2}' \
        "${R_SUMMARY}"
)"

CONDA_DIFFERENCES="$(
    awk -F= \
        '$1 == "conda_package_differences" {print $2}' \
        "${CONDA_SUMMARY}"
)"

{
    echo "============================================================"
    echo "FINAL PARITY SUMMARY"
    echo "============================================================"
    echo "r_package_differences=${R_DIFFERENCES}"
    echo "primary_did_output_differences=${did_difference_count}"
    echo "conda_package_differences=${CONDA_DIFFERENCES}"
    echo

    if [[ "${R_DIFFERENCES}" -eq 0 ]] &&
       [[ "${did_difference_count}" -eq 0 ]]
    then
        echo "ANALYSIS_ENVIRONMENT_PARITY=PASS"
        echo
        echo "Interpretation:"
        echo "  R package names and versions match system12/173."
        echo "  Primary DiD analytical CSV outputs match exactly."
        echo "  Conda differences are reported separately."
    else
        echo "ANALYSIS_ENVIRONMENT_PARITY=FAIL"
    fi

    echo
    echo "Output directory:"
    echo "  ${OUTPUT_DIR}"
    echo "============================================================"
} | tee "${FINAL_SUMMARY}"
