#!/usr/bin/env bash
#
# Inspect the existing aicomplexity environment on system12.
#
# This script is read-only. It does not install, remove, or update packages.
#
# Inputs:
#   env_dev/r-installed-packages.csv
#   env_dev/r-session-info.txt
#   env_dev/cursorstudy-explicit-linux-64.txt
#
# Outputs:
#   env_dev/logs/env-check/aicomplexity-173-<timestamp>/
#     system-summary.txt
#     conda-list-current.txt
#     conda-explicit-current.txt
#     conda-r-packages-current.txt
#     r-installed-packages-current.csv
#     r-package-manifest-comparison.csv
#     r-package-validation-summary.txt
#     r-critical-packages.txt
#     r-package-descriptions.txt
#     r-session-info-current.txt
#     explicit-specification-comparison.txt

set -euo pipefail

ENV_NAME="${ENV_NAME:-aicomplexity}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REFERENCE_R_PACKAGES="${SCRIPT_DIR}/r-installed-packages.csv"
REFERENCE_R_SESSION="${SCRIPT_DIR}/r-session-info.txt"
REFERENCE_EXPLICIT="${SCRIPT_DIR}/cursorstudy-explicit-linux-64.txt"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${SCRIPT_DIR}/logs/env-check/aicomplexity-173-${TIMESTAMP}"

SYSTEM_SUMMARY="${OUTPUT_DIR}/system-summary.txt"
CONDA_LIST_FILE="${OUTPUT_DIR}/conda-list-current.txt"
CONDA_EXPLICIT_FILE="${OUTPUT_DIR}/conda-explicit-current.txt"
CONDA_R_PACKAGES_FILE="${OUTPUT_DIR}/conda-r-packages-current.txt"
CURRENT_R_PACKAGES="${OUTPUT_DIR}/r-installed-packages-current.csv"
R_COMPARISON_FILE="${OUTPUT_DIR}/r-package-manifest-comparison.csv"
R_SUMMARY_FILE="${OUTPUT_DIR}/r-package-validation-summary.txt"
CRITICAL_PACKAGES_FILE="${OUTPUT_DIR}/r-critical-packages.txt"
PACKAGE_DESCRIPTIONS_FILE="${OUTPUT_DIR}/r-package-descriptions.txt"
CURRENT_R_SESSION="${OUTPUT_DIR}/r-session-info-current.txt"
EXPLICIT_COMPARISON="${OUTPUT_DIR}/explicit-specification-comparison.txt"

mkdir -p "${OUTPUT_DIR}"

echo "============================================================"
echo "AICOMPLEXITY ENVIRONMENT CHECK ON SYSTEM12"
echo "============================================================"
echo "Repository:  ${REPO_DIR}"
echo "Environment: ${ENV_NAME}"
echo "Output:      ${OUTPUT_DIR}"
echo

for required_file in \
    "${REFERENCE_R_PACKAGES}" \
    "${REFERENCE_R_SESSION}" \
    "${REFERENCE_EXPLICIT}"
do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Missing or empty reference file: ${required_file}" >&2
        exit 1
    fi
done

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda was not found in PATH." >&2
    exit 1
fi

CONDA_BASE="$(conda info --base)"
CONDA_SH="${CONDA_BASE}/etc/profile.d/conda.sh"

if [[ ! -f "${CONDA_SH}" ]]; then
    echo "ERROR: Conda initialization file was not found: ${CONDA_SH}" >&2
    exit 1
fi

# Load Conda shell support.
source "${CONDA_SH}"

if ! conda env list |
    awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
    grep -Fxq "${ENV_NAME}"
then
    echo "ERROR: Conda environment does not exist: ${ENV_NAME}" >&2
    exit 1
fi

{
    echo "Date: $(date)"
    echo "Hostname: $(hostname)"
    echo "User: $(whoami)"
    echo "Repository: ${REPO_DIR}"
    echo "Conda base: ${CONDA_BASE}"
    echo "Conda version: $(conda --version)"
    echo "Environment: ${ENV_NAME}"
    echo
    uname -a
    echo
    if [[ -f /etc/os-release ]]; then
        cat /etc/os-release
    fi
} > "${SYSTEM_SUMMARY}"

echo "Exporting Conda package inventories..."

conda list \
    --name "${ENV_NAME}" \
    > "${CONDA_LIST_FILE}"

conda list \
    --name "${ENV_NAME}" \
    --explicit \
    > "${CONDA_EXPLICIT_FILE}"

grep -E '^r-|^_r-mutex[[:space:]]' \
    "${CONDA_LIST_FILE}" \
    > "${CONDA_R_PACKAGES_FILE}" || true

echo "Inspecting the R installation..."

conda run --no-capture-output --name "${ENV_NAME}" \
    Rscript - \
    "${REFERENCE_R_PACKAGES}" \
    "${CURRENT_R_PACKAGES}" \
    "${R_COMPARISON_FILE}" \
    "${R_SUMMARY_FILE}" \
    "${CRITICAL_PACKAGES_FILE}" \
    "${PACKAGE_DESCRIPTIONS_FILE}" \
    "${CURRENT_R_SESSION}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

reference_file <- args[[1]]
current_file <- args[[2]]
comparison_file <- args[[3]]
summary_file <- args[[4]]
critical_file <- args[[5]]
description_file <- args[[6]]
session_file <- args[[7]]

reference <- read.csv(
  reference_file,
  stringsAsFactors = FALSE,
  check.names = FALSE
)

required_columns <- c("Package", "Version", "LibPath")
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

current <- data.frame(
  Package = installed_matrix[, "Package"],
  Version = installed_matrix[, "Version"],
  LibPath = installed_matrix[, "LibPath"],
  Built = installed_matrix[, "Built"],
  Priority = installed_matrix[, "Priority"],
  stringsAsFactors = FALSE,
  row.names = NULL
)

current <- current[order(current$Package, current$LibPath), ]
current <- current[!duplicated(current$Package), ]

write.csv(
  current,
  current_file,
  row.names = FALSE,
  quote = TRUE
)

reference_compare <- reference[, c("Package", "Version")]
names(reference_compare)[2] <- "ExpectedVersion"

current_compare <- current[, c("Package", "Version", "LibPath", "Built")]
names(current_compare)[2] <- "ActualVersion"

comparison <- merge(
  reference_compare,
  current_compare,
  by = "Package",
  all.x = TRUE,
  sort = TRUE
)

comparison$Status <- ifelse(
  is.na(comparison$ActualVersion),
  "missing",
  ifelse(
    comparison$ExpectedVersion == comparison$ActualVersion,
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

summary_lines <- c(
  paste0("r_version=", paste(R.version$major, R.version$minor, sep = ".")),
  paste0("reference_packages=", nrow(reference)),
  paste0("installed_packages=", nrow(current)),
  paste0("matched_packages=", sum(comparison$Status == "match")),
  paste0("missing_packages=", sum(comparison$Status == "missing")),
  paste0(
    "version_mismatches=",
    sum(comparison$Status == "version_mismatch")
  ),
  paste0(
    "validation_failures=",
    sum(comparison$Status != "match")
  ),
  paste0("r_home=", R.home()),
  paste0("primary_library=", .libPaths()[[1]]),
  paste0("timezone=", Sys.timezone())
)

writeLines(summary_lines, summary_file)

critical_packages <- c(
  "didimputation",
  "fixest",
  "data.table",
  "knitr",
  "rmarkdown",
  "dplyr",
  "ggplot2",
  "tidyr",
  "readr",
  "modelsummary",
  "sandwich",
  "zoo",
  "plm",
  "remotes"
)

critical_connection <- file(critical_file, open = "wt")

for (package in critical_packages) {
  if (requireNamespace(package, quietly = TRUE)) {
    description <- packageDescription(package)

    cat(
      sprintf(
        "%-18s version=%-12s library=%s\n",
        package,
        as.character(packageVersion(package)),
        find.package(package)
      ),
      file = critical_connection
    )

    repository <- description[["Repository"]]
    remote_type <- description[["RemoteType"]]
    remote_repo <- description[["RemoteRepo"]]
    remote_ref <- description[["RemoteRef"]]

    cat(
      sprintf(
        "  Repository=%s RemoteType=%s RemoteRepo=%s RemoteRef=%s\n",
        ifelse(is.null(repository), "", repository),
        ifelse(is.null(remote_type), "", remote_type),
        ifelse(is.null(remote_repo), "", remote_repo),
        ifelse(is.null(remote_ref), "", remote_ref)
      ),
      file = critical_connection
    )
  } else {
    cat(
      sprintf("%-18s MISSING\n", package),
      file = critical_connection
    )
  }
}

close(critical_connection)

description_packages <- comparison$Package
description_connection <- file(description_file, open = "wt")

for (package in description_packages) {
  if (!requireNamespace(package, quietly = TRUE)) {
    next
  }

  description <- packageDescription(package)

  cat(
    paste0(
      "Package=", package,
      "\nVersion=", as.character(packageVersion(package)),
      "\nLibPath=", find.package(package),
      "\nBuilt=", description[["Built"]],
      "\nRepository=", description[["Repository"]],
      "\nRemoteType=", description[["RemoteType"]],
      "\nRemoteRepo=", description[["RemoteRepo"]],
      "\nRemoteRef=", description[["RemoteRef"]],
      "\n\n"
    ),
    file = description_connection
  )
}

close(description_connection)

session_connection <- file(session_file, open = "wt")

sink(session_connection)

cat("R executable:\n")
cat(file.path(R.home("bin"), "R"), "\n\n")

cat("R version:\n")
cat(R.version.string, "\n\n")

cat("Platform:\n")
cat(R.version$platform, "\n\n")

cat("R home:\n")
cat(R.home(), "\n\n")

cat("Library paths:\n")
print(.libPaths())

cat("\nTimezone:\n")
print(Sys.timezone())

cat("\nLocale:\n")
print(Sys.getlocale())

cat("\nSession information:\n")
print(sessionInfo())

sink()
close(session_connection)
RS

echo "Comparing the current Conda explicit specification..."

{
    echo "Reference explicit file:"
    echo "  ${REFERENCE_EXPLICIT}"
    echo "Current explicit file:"
    echo "  ${CONDA_EXPLICIT_FILE}"
    echo

    echo "Reference SHA-256:"
    sha256sum "${REFERENCE_EXPLICIT}"
    echo

    echo "Current SHA-256:"
    sha256sum "${CONDA_EXPLICIT_FILE}"
    echo

    echo "Reference line count:"
    wc -l "${REFERENCE_EXPLICIT}"
    echo

    echo "Current line count:"
    wc -l "${CONDA_EXPLICIT_FILE}"
    echo

    echo "Normalized URL differences:"
    diff -u \
        <(grep -v '^#' "${REFERENCE_EXPLICIT}" | sed '/^[[:space:]]*$/d') \
        <(grep -v '^#' "${CONDA_EXPLICIT_FILE}" | sed '/^[[:space:]]*$/d') \
        || true
} > "${EXPLICIT_COMPARISON}"

echo
echo "============================================================"
echo "173 AICOMPLEXITY SUMMARY"
echo "============================================================"

cat "${R_SUMMARY_FILE}"

echo
echo "Conda package counts:"
echo "  All Conda packages: $(grep -vc '^#' "${CONDA_LIST_FILE}")"
echo "  Conda R packages:   $(wc -l < "${CONDA_R_PACKAGES_FILE}")"

echo
echo "Critical R packages:"
cat "${CRITICAL_PACKAGES_FILE}"

echo
echo "Manifest differences:"

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
' "${R_COMPARISON_FILE}" || true

echo
echo "Current executables:"

conda run --no-capture-output --name "${ENV_NAME}" \
    bash -lc '
        echo "Python:  $(command -v python)"
        python --version
        echo "R:       $(command -v R)"
        R --version | head -1
        echo "Rscript: $(command -v Rscript)"
        Rscript --version
        echo "Pandoc:  $(command -v pandoc)"
        pandoc --version | head -2
    '

echo
echo "Output directory:"
echo "  ${OUTPUT_DIR}"
echo
echo "PASS: The system12 environment inspection completed."
echo "============================================================"
