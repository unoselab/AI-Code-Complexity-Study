#!/usr/bin/env bash
#
# Build a missing-only R package manifest by comparing the current
# selab3 aicomplexity environment with the canonical system12 snapshot.
#
# Input:
#   env_dev/logs-173/extracted/logs/env-check/
#     aicomplexity-173-20260725-232259/
#     r-installed-packages-current.csv
#
# Outputs:
#   env_dev/logs/env-reinstall/missing-r-packages-current-173.csv
#   env_dev/logs/env-reinstall/r-package-comparison-current-173.csv
#
# This script does not install, remove, or update any package.

set -euo pipefail

ENV_NAME="aicomplexity"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REFERENCE_FILE="${SCRIPT_DIR}/logs-173/extracted/logs/env-check/aicomplexity-173-20260725-232259/r-installed-packages-current.csv"
OUTPUT_DIR="${SCRIPT_DIR}/logs/env-reinstall"

MISSING_FILE="${OUTPUT_DIR}/missing-r-packages-current-173.csv"
COMPARISON_FILE="${OUTPUT_DIR}/r-package-comparison-current-173.csv"

mkdir -p "${OUTPUT_DIR}"

if [[ ! -s "${REFERENCE_FILE}" ]]; then
    echo "ERROR: Canonical R package manifest is missing:"
    echo "  ${REFERENCE_FILE}"
    exit 1
fi

if ! conda env list |
    awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
    grep -Fxq "${ENV_NAME}"
then
    echo "ERROR: Conda environment does not exist: ${ENV_NAME}"
    exit 1
fi

conda run --no-capture-output --name "${ENV_NAME}" \
    Rscript - \
    "${REFERENCE_FILE}" \
    "${MISSING_FILE}" \
    "${COMPARISON_FILE}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

reference_file <- args[[1]]
missing_file <- args[[2]]
comparison_file <- args[[3]]

reference <- read.csv(
  reference_file,
  stringsAsFactors = FALSE,
  check.names = FALSE
)

required_columns <- c(
  "Package",
  "Version",
  "LibPath",
  "Built",
  "Priority"
)

missing_columns <- setdiff(required_columns, names(reference))

if (length(missing_columns) > 0L) {
  stop(
    paste(
      "Reference manifest is missing columns:",
      paste(missing_columns, collapse = ", ")
    )
  )
}

installed_matrix <- installed.packages()

installed <- data.frame(
  Package = installed_matrix[, "Package"],
  ActualVersion = installed_matrix[, "Version"],
  ActualLibPath = installed_matrix[, "LibPath"],
  stringsAsFactors = FALSE,
  row.names = NULL
)

installed <- installed[order(installed$Package), ]
installed <- installed[!duplicated(installed$Package), ]

comparison <- merge(
  reference,
  installed,
  by = "Package",
  all.x = TRUE,
  sort = TRUE
)

comparison$Status <- ifelse(
  is.na(comparison$ActualVersion),
  "missing",
  ifelse(
    comparison$Version == comparison$ActualVersion,
    "match",
    "version_mismatch"
  )
)

write.csv(
  comparison,
  comparison_file,
  row.names = FALSE,
  quote = TRUE
)

missing_packages <- comparison[
  comparison$Status == "missing",
  c("Package", "Version", "Built", "Priority"),
  drop = FALSE
]

write.csv(
  missing_packages,
  missing_file,
  row.names = FALSE,
  quote = TRUE
)

cat("reference_packages=", nrow(reference), "\n", sep = "")
cat("installed_packages=", nrow(installed), "\n", sep = "")
cat(
  "matched_packages=",
  sum(comparison$Status == "match"),
  "\n",
  sep = ""
)
cat(
  "missing_packages=",
  sum(comparison$Status == "missing"),
  "\n",
  sep = ""
)
cat(
  "version_mismatches=",
  sum(comparison$Status == "version_mismatch"),
  "\n",
  sep = ""
)

cat("\nMissing packages:\n")

print(
  missing_packages,
  row.names = FALSE
)
RS

echo
echo "Generated:"
echo "  ${MISSING_FILE}"
echo "  ${COMPARISON_FILE}"

echo
echo "Missing manifest rows including header:"
wc -l "${MISSING_FILE}"

echo
echo "SHA-256:"
sha256sum "${MISSING_FILE}"
