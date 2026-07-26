#!/usr/bin/env bash
#
# Create and validate the cursorstudy Conda environment exported from system12.
#
# Inputs:
#   cursorstudy-explicit-linux-64.txt
#       Exact Conda package URLs and builds exported from the source server.
#
#   r-installed-packages.csv
#       Reference R package names and versions exported from the source server.
#       The original LibPath values are host-specific and are not compared.
#
#   r-session-info.txt
#       Reference R session information from the source server.
#
# Outputs:
#   logs/env-setup/cursorstudy-<timestamp>/
#       conda-list-current.txt
#       conda-explicit-current.txt
#       r-installed-packages-current.csv
#       r-package-version-comparison.csv
#       r-package-validation-summary.txt
#       r-session-info-current.txt
#       verify-r-environment-v1.R
#
# Environment variables:
#   ENV_NAME=aicomplexity
#       Conda environment name.
#
#   RECREATE_ENV=0
#       Set to 1 to remove and recreate an existing environment.
#
# The script does not install R packages directly from the CSV manifest.
# The explicit Conda specification is the authoritative installation source.

set -euo pipefail

ENV_NAME="${ENV_NAME:-aicomplexity}"
RECREATE_ENV="${RECREATE_ENV:-0}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPLICIT_FILE="${REPO_DIR}/cursorstudy-explicit-linux-64.txt"
R_PACKAGE_MANIFEST="${REPO_DIR}/r-installed-packages.csv"
R_SESSION_REFERENCE="${REPO_DIR}/r-session-info.txt"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${REPO_DIR}/logs/env-setup/${ENV_NAME}-${TIMESTAMP}"

CURRENT_CONDA_LIST="${OUTPUT_DIR}/conda-list-current.txt"
CURRENT_CONDA_EXPLICIT="${OUTPUT_DIR}/conda-explicit-current.txt"
CURRENT_R_PACKAGES="${OUTPUT_DIR}/r-installed-packages-current.csv"
R_PACKAGE_COMPARISON="${OUTPUT_DIR}/r-package-version-comparison.csv"
R_VALIDATION_SUMMARY="${OUTPUT_DIR}/r-package-validation-summary.txt"
CURRENT_R_SESSION="${OUTPUT_DIR}/r-session-info-current.txt"
VERIFY_R_SCRIPT="${OUTPUT_DIR}/verify-r-environment-v1.R"

EXPECTED_R_VERSION="4.3.3"
EXPECTED_TIMEZONE="America/Chicago"

echo "============================================================"
echo "aicomplexity environment installation"
echo "============================================================"
echo "Repository:       ${REPO_DIR}"
echo "Environment:      ${ENV_NAME}"
echo "Explicit file:    ${EXPLICIT_FILE}"
echo "R package list:   ${R_PACKAGE_MANIFEST}"
echo "Session reference:${R_SESSION_REFERENCE}"
echo "Output directory: ${OUTPUT_DIR}"
echo "Recreate:         ${RECREATE_ENV}"
echo

for required_file in \
    "${EXPLICIT_FILE}" \
    "${R_PACKAGE_MANIFEST}" \
    "${R_SESSION_REFERENCE}"
do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty: ${required_file}" >&2
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
    echo "ERROR: Conda initialization script was not found: ${CONDA_SH}" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${CONDA_SH}"

mkdir -p "${OUTPUT_DIR}"

echo "Input checksums:" | tee "${OUTPUT_DIR}/input-checksums.txt"
sha256sum \
    "${EXPLICIT_FILE}" \
    "${R_PACKAGE_MANIFEST}" \
    "${R_SESSION_REFERENCE}" \
    | tee -a "${OUTPUT_DIR}/input-checksums.txt"

echo
echo "Reference information:"
echo "  Explicit specification lines: $(wc -l < "${EXPLICIT_FILE}")"
echo "  R package manifest rows:       $(($(wc -l < "${R_PACKAGE_MANIFEST}") - 1))"
echo "  Expected R version:            ${EXPECTED_R_VERSION}"
echo "  Expected timezone:             ${EXPECTED_TIMEZONE}"
echo

environment_exists() {
    conda env list |
        awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
        grep -Fxq "${ENV_NAME}"
}

if environment_exists; then
    if [[ "${RECREATE_ENV}" == "1" ]]; then
        echo "Removing existing environment: ${ENV_NAME}"
        conda env remove --name "${ENV_NAME}" --yes
    else
        echo "Environment already exists: ${ENV_NAME}"
        echo "The existing environment will be validated without recreation."
    fi
fi

if ! environment_exists; then
    echo
    echo "Creating environment from the explicit Conda specification..."
    conda create \
        --name "${ENV_NAME}" \
        --file "${EXPLICIT_FILE}" \
        --yes
fi

echo
echo "Verifying required executables..."

for executable in R Rscript python pandoc; do
    if ! conda run --no-capture-output --name "${ENV_NAME}" \
        command -v "${executable}" >/dev/null 2>&1
    then
        echo "ERROR: ${executable} is unavailable in ${ENV_NAME}." >&2
        exit 1
    fi
done

ACTUAL_R_VERSION="$(
    conda run --no-capture-output --name "${ENV_NAME}" \
        Rscript -e 'cat(paste(R.version$major, R.version$minor, sep="."))'
)"

echo "Expected R version: ${EXPECTED_R_VERSION}"
echo "Actual R version:   ${ACTUAL_R_VERSION}"

if [[ "${ACTUAL_R_VERSION}" != "${EXPECTED_R_VERSION}" ]]; then
    echo "ERROR: R version does not match the system12 reference." >&2
    exit 1
fi

# Preserve the original study timezone for reproducible date handling.
export TZ="${EXPECTED_TIMEZONE}"

# Use the source locale when it exists on the destination host.
if locale -a 2>/dev/null |
    grep -Eiq '^en_US[.]UTF-8$|^en_US[.]utf8$'
then
    export LANG="en_US.UTF-8"
    export LC_ALL="en_US.UTF-8"
else
    echo "WARNING: en_US.UTF-8 locale is unavailable on this host."
    echo "The current system locale will be used."
fi

cat > "${VERIFY_R_SCRIPT}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

if (length(args) != 5L) {
  stop(
    paste(
      "Expected arguments:",
      "<reference-packages.csv>",
      "<current-packages.csv>",
      "<comparison.csv>",
      "<summary.txt>",
      "<session-info.txt>"
    )
  )
}

reference_file <- args[[1]]
current_file <- args[[2]]
comparison_file <- args[[3]]
summary_file <- args[[4]]
session_file <- args[[5]]

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
      "Reference CSV is missing columns:",
      paste(missing_columns, collapse = ", ")
    )
  )
}

installed_matrix <- installed.packages()

current <- data.frame(
  Package = installed_matrix[, "Package"],
  Version = installed_matrix[, "Version"],
  LibPath = installed_matrix[, "LibPath"],
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
names(reference_compare)[names(reference_compare) == "Version"] <-
  "ExpectedVersion"

current_compare <- current[, c("Package", "Version")]
names(current_compare)[names(current_compare) == "Version"] <-
  "ActualVersion"

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

summary_values <- c(
  paste("reference_packages", nrow(reference), sep = "="),
  paste("installed_packages", nrow(current), sep = "="),
  paste(
    "matched_packages",
    sum(comparison$Status == "match"),
    sep = "="
  ),
  paste(
    "missing_packages",
    sum(comparison$Status == "missing"),
    sep = "="
  ),
  paste(
    "version_mismatches",
    sum(comparison$Status == "version_mismatch"),
    sep = "="
  ),
  paste(
    "validation_failures",
    sum(comparison$Status != "match"),
    sep = "="
  )
)

writeLines(summary_values, summary_file)

session_connection <- file(session_file, open = "wt")
sink(session_connection)
print(sessionInfo())
sink()
close(session_connection)
RS

echo
echo "Exporting the recreated environment..."

conda list \
    --name "${ENV_NAME}" \
    > "${CURRENT_CONDA_LIST}"

conda list \
    --name "${ENV_NAME}" \
    --explicit \
    > "${CURRENT_CONDA_EXPLICIT}"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript "${VERIFY_R_SCRIPT}" \
        "${R_PACKAGE_MANIFEST}" \
        "${CURRENT_R_PACKAGES}" \
        "${R_PACKAGE_COMPARISON}" \
        "${R_VALIDATION_SUMMARY}" \
        "${CURRENT_R_SESSION}"

echo
echo "R package validation:"
cat "${R_VALIDATION_SUMMARY}"

VALIDATION_FAILURES="$(
    awk -F= '$1 == "validation_failures" {print $2}' \
        "${R_VALIDATION_SUMMARY}"
)"

if [[ -z "${VALIDATION_FAILURES}" ]]; then
    echo "ERROR: Could not read the R package validation result." >&2
    exit 1
fi

echo
echo "Environment versions:"
conda run --no-capture-output --name "${ENV_NAME}" R --version |
    head -1
conda run --no-capture-output --name "${ENV_NAME}" Rscript --version
conda run --no-capture-output --name "${ENV_NAME}" python --version
conda run --no-capture-output --name "${ENV_NAME}" pandoc --version |
    head -2

echo
echo "Current R session information:"
cat "${CURRENT_R_SESSION}"

echo
echo "============================================================"

if [[ "${VALIDATION_FAILURES}" -eq 0 ]]; then
    echo "PASS: The aicomplexity environment matches the R package manifest."
else
    echo "WARNING: The environment was created, but package differences exist."
    echo "Review:"
    echo "  ${R_PACKAGE_COMPARISON}"
    echo
    echo "Do not install packages manually until the mismatch report is reviewed."
fi

echo
echo "Validation outputs:"
echo "  ${OUTPUT_DIR}"
echo "============================================================"
