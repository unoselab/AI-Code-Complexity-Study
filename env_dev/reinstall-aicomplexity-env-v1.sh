#!/usr/bin/env bash
#
# Remove and recreate the aicomplexity Conda environment by using the
# latest environment snapshot exported from system12 / 173.
#
# Canonical inputs:
#   env_dev/logs-173/extracted/logs/env-check/
#     aicomplexity-173-*/conda-explicit-current.txt
#
#   env_dev/logs-173/extracted/logs/env-check/
#     aicomplexity-173-*/r-installed-packages-current.csv
#
# Outputs:
#   env_dev/logs/env-reinstall/aicomplexity-<timestamp>/
#
# This script:
#   1. Saves the current selab3 environment inventory.
#   2. Removes the existing aicomplexity environment.
#   3. Recreates it from the latest 173 explicit Conda specification.
#   4. Compares all R package names and versions with the 173 snapshot.
#   5. Verifies critical DiD packages and executable versions.
#
# It does not run ML classification, panel preparation, or DiD analysis.

set -euo pipefail

ENV_NAME="aicomplexity"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
    echo "ERROR: No 173 environment snapshot was found under:"
    echo "  ${REFERENCE_ROOT}"
    exit 1
fi

REFERENCE_EXPLICIT="${REFERENCE_DIR}/conda-explicit-current.txt"
REFERENCE_R_PACKAGES="${REFERENCE_DIR}/r-installed-packages-current.csv"
REFERENCE_R_SESSION="${REFERENCE_DIR}/r-session-info-current.txt"
REFERENCE_CRITICAL="${REFERENCE_DIR}/r-critical-packages.txt"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${SCRIPT_DIR}/logs/env-reinstall/${ENV_NAME}-${TIMESTAMP}"

BEFORE_DIR="${OUTPUT_DIR}/before-removal"
AFTER_DIR="${OUTPUT_DIR}/after-install"

mkdir -p "${BEFORE_DIR}" "${AFTER_DIR}"

echo "============================================================"
echo "REINSTALL AICOMPLEXITY ENVIRONMENT"
echo "============================================================"
echo "Repository:           ${REPO_DIR}"
echo "Environment:          ${ENV_NAME}"
echo "173 reference:        ${REFERENCE_DIR}"
echo "Explicit input:       ${REFERENCE_EXPLICIT}"
echo "R package reference:  ${REFERENCE_R_PACKAGES}"
echo "Output directory:     ${OUTPUT_DIR}"
echo

for required_file in \
    "${REFERENCE_EXPLICIT}" \
    "${REFERENCE_R_PACKAGES}" \
    "${REFERENCE_R_SESSION}" \
    "${REFERENCE_CRITICAL}"
do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required reference file is missing or empty:"
        echo "  ${required_file}"
        exit 1
    fi
done

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda was not found in PATH."
    exit 1
fi

CONDA_BASE="$(conda info --base)"
CONDA_SH="${CONDA_BASE}/etc/profile.d/conda.sh"

if [[ ! -f "${CONDA_SH}" ]]; then
    echo "ERROR: Conda initialization script was not found:"
    echo "  ${CONDA_SH}"
    exit 1
fi

# Load the Conda shell function.
source "${CONDA_SH}"

environment_exists() {
    conda env list |
        awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
        grep -Fxq "${ENV_NAME}"
}

echo "Reference snapshot:"
echo "  Explicit lines:  $(wc -l < "${REFERENCE_EXPLICIT}")"
echo "  R package rows:  $(($(wc -l < "${REFERENCE_R_PACKAGES}") - 1))"
echo

echo "Reference checksums:" |
    tee "${OUTPUT_DIR}/reference-checksums.txt"

sha256sum \
    "${REFERENCE_EXPLICIT}" \
    "${REFERENCE_R_PACKAGES}" \
    "${REFERENCE_R_SESSION}" \
    "${REFERENCE_CRITICAL}" \
    | tee -a "${OUTPUT_DIR}/reference-checksums.txt"

echo
echo "============================================================"
echo "1. SAVE CURRENT SELAB3 ENVIRONMENT INVENTORY"
echo "============================================================"

if environment_exists; then
    conda list \
        --name "${ENV_NAME}" \
        > "${BEFORE_DIR}/conda-list-before.txt"

    conda list \
        --name "${ENV_NAME}" \
        --explicit \
        > "${BEFORE_DIR}/conda-explicit-before.txt"

    if conda run --no-capture-output --name "${ENV_NAME}" \
        command -v Rscript >/dev/null 2>&1
    then
        conda run --no-capture-output --name "${ENV_NAME}" \
            Rscript - "${BEFORE_DIR}/r-installed-packages-before.csv" <<'RS'
args <- commandArgs(trailingOnly = TRUE)
output_file <- args[[1]]

packages <- installed.packages()

result <- data.frame(
  Package = packages[, "Package"],
  Version = packages[, "Version"],
  LibPath = packages[, "LibPath"],
  stringsAsFactors = FALSE,
  row.names = NULL
)

result <- result[order(result$Package, result$LibPath), ]
result <- result[!duplicated(result$Package), ]

write.csv(
  result,
  output_file,
  row.names = FALSE,
  quote = TRUE
)
RS
    fi

    echo "Saved the current environment inventory:"
    echo "  ${BEFORE_DIR}"
else
    echo "Environment does not currently exist: ${ENV_NAME}"
fi

echo
echo "============================================================"
echo "2. DEACTIVATE AND REMOVE EXISTING ENVIRONMENT"
echo "============================================================"

# Deactivate aicomplexity inside this script before deleting it.
while [[ "${CONDA_DEFAULT_ENV:-}" == "${ENV_NAME}" ]]; do
    conda deactivate
done

if environment_exists; then
    conda env remove \
        --name "${ENV_NAME}" \
        --yes
fi

if environment_exists; then
    echo "ERROR: The environment still exists after removal."
    exit 1
fi

echo "PASS: Existing environment was removed."

echo
echo "============================================================"
echo "3. RECREATE FROM THE CURRENT 173 EXPLICIT SPECIFICATION"
echo "============================================================"

conda create \
    --name "${ENV_NAME}" \
    --file "${REFERENCE_EXPLICIT}" \
    --yes

if ! environment_exists; then
    echo "ERROR: Environment creation did not complete."
    exit 1
fi

echo "PASS: Environment was recreated."

echo
echo "============================================================"
echo "4. VERIFY REQUIRED EXECUTABLES"
echo "============================================================"

for executable in python R Rscript pandoc; do
    if ! conda run --no-capture-output --name "${ENV_NAME}" \
        command -v "${executable}" >/dev/null 2>&1
    then
        echo "ERROR: Required executable is unavailable: ${executable}"
        exit 1
    fi

    echo "FOUND: ${executable}"
done

ACTUAL_R_VERSION="$(
    conda run --no-capture-output --name "${ENV_NAME}" \
        Rscript -e 'cat(paste(R.version$major, R.version$minor, sep = "."))'
)"

if [[ "${ACTUAL_R_VERSION}" != "4.3.3" ]]; then
    echo "ERROR: Expected R 4.3.3 but found ${ACTUAL_R_VERSION}."
    exit 1
fi

echo "PASS: R ${ACTUAL_R_VERSION}"

echo
echo "============================================================"
echo "5. EXPORT THE RECREATED ENVIRONMENT"
echo "============================================================"

conda list \
    --name "${ENV_NAME}" \
    > "${AFTER_DIR}/conda-list-after.txt"

conda list \
    --name "${ENV_NAME}" \
    --explicit \
    > "${AFTER_DIR}/conda-explicit-after.txt"

grep -E '^r-|^_r-mutex[[:space:]]' \
    "${AFTER_DIR}/conda-list-after.txt" \
    > "${AFTER_DIR}/conda-r-packages-after.txt" || true

echo "Conda packages:"
echo "  $(grep -vc '^#' "${AFTER_DIR}/conda-list-after.txt")"

echo "Conda R packages:"
echo "  $(wc -l < "${AFTER_DIR}/conda-r-packages-after.txt")"

echo
echo "============================================================"
echo "6. COMPARE R PACKAGES WITH THE CURRENT 173 ENVIRONMENT"
echo "============================================================"

conda run --no-capture-output --name "${ENV_NAME}" \
    Rscript - \
    "${REFERENCE_R_PACKAGES}" \
    "${AFTER_DIR}/r-installed-packages-after.csv" \
    "${AFTER_DIR}/r-package-comparison.csv" \
    "${AFTER_DIR}/r-package-validation-summary.txt" \
    "${AFTER_DIR}/r-session-info-after.txt" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

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

installed_matrix <- installed.packages()

current <- data.frame(
  Package = installed_matrix[, "Package"],
  Version = installed_matrix[, "Version"],
  LibPath = installed_matrix[, "LibPath"],
  Built = installed_matrix[, "Built"],
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
  paste0(
    "r_version=",
    paste(R.version$major, R.version$minor, sep = ".")
  ),
  paste0("reference_packages=", nrow(reference)),
  paste0("installed_packages=", nrow(current)),
  paste0(
    "matched_packages=",
    sum(comparison$Status == "match")
  ),
  paste0(
    "missing_packages=",
    sum(comparison$Status == "missing")
  ),
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

session_connection <- file(session_file, open = "wt")
sink(session_connection)
print(sessionInfo())
sink()
close(session_connection)
RS

cat "${AFTER_DIR}/r-package-validation-summary.txt"

echo
echo "Package differences:"

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
' "${AFTER_DIR}/r-package-comparison.csv" \
    | tee "${AFTER_DIR}/r-package-differences.txt"

echo
echo "============================================================"
echo "7. VERIFY CRITICAL DID PACKAGES"
echo "============================================================"

conda run --no-capture-output --name "${ENV_NAME}" \
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
  sandwich = "3.1.1",
  zoo = "1.8.15",
  plm = "2.6.7"
)

installed <- installed.packages()
versions <- setNames(
  installed[, "Version"],
  installed[, "Package"]
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
echo "8. COMPARE EXPLICIT CONDA SPECIFICATIONS"
echo "============================================================"

{
    echo "Reference explicit lines:"
    wc -l "${REFERENCE_EXPLICIT}"
    echo

    echo "Recreated explicit lines:"
    wc -l "${AFTER_DIR}/conda-explicit-after.txt"
    echo

    echo "Normalized differences:"

    diff -u \
        <(
            grep -v '^#' "${REFERENCE_EXPLICIT}" |
                sed '/^[[:space:]]*$/d'
        ) \
        <(
            grep -v '^#' "${AFTER_DIR}/conda-explicit-after.txt" |
                sed '/^[[:space:]]*$/d'
        ) || true
} | tee "${AFTER_DIR}/conda-explicit-comparison.txt"

echo
echo "============================================================"
echo "9. FINAL VERSIONS"
echo "============================================================"

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

VALIDATION_FAILURES="$(
    awk -F= \
        '$1 == "validation_failures" {print $2}' \
        "${AFTER_DIR}/r-package-validation-summary.txt"
)"

echo
echo "============================================================"

if [[ -z "${VALIDATION_FAILURES}" ]]; then
    echo "ERROR: Could not determine the validation result."
    exit 1
fi

if [[ "${VALIDATION_FAILURES}" -ne 0 ]]; then
    echo "WARNING: ${VALIDATION_FAILURES} R package differences remain."
    echo
    echo "Review:"
    echo "  ${AFTER_DIR}/r-package-differences.txt"
    echo "  ${AFTER_DIR}/r-package-comparison.csv"
    echo
    echo "Do not run DiD yet."
    exit 1
fi

echo "PASS: The recreated environment matches the current 173 R environment."
echo
echo "Validation outputs:"
echo "  ${OUTPUT_DIR}"
echo "============================================================"
