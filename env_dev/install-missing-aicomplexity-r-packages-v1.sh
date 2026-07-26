#!/usr/bin/env bash
#
# Install only the R packages missing from the selab3 aicomplexity
# environment, using exact versions from the current system12 snapshot.
#
# Canonical inputs:
#   env_dev/logs-173/extracted/logs/env-check/aicomplexity-173-*/
#     r-installed-packages-current.csv
#
#   env_dev/logs/env-reinstall/
#     missing-r-packages-current-173.csv
#
# Outputs:
#   env_dev/logs/env-reinstall/
#     aicomplexity-missing-r-<timestamp>/
#
# Installation policy:
#   - Do not upgrade or downgrade already matching packages.
#   - Do not use the remotes package.
#   - Download exact source versions from CRAN or CRAN Archive.
#   - Install packages in dependency-aware passes.
#   - Validate all 250 canonical R packages after installation.
#
# This script does not run ML classification or DiD analysis.

set -euo pipefail

ENV_NAME="aicomplexity"
EXPECTED_R_VERSION="4.3.3"
MAX_PASSES="${MAX_PASSES:-8}"
NCPUS="${NCPUS:-4}"
CRAN_BASE="${CRAN_BASE:-https://cloud.r-project.org}"

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
    echo "ERROR: The current 173 environment snapshot was not found."
    echo "Expected under:"
    echo "  ${REFERENCE_ROOT}"
    exit 1
fi

CANONICAL_MANIFEST="${REFERENCE_DIR}/r-installed-packages-current.csv"
MISSING_MANIFEST="${SCRIPT_DIR}/logs/env-reinstall/missing-r-packages-current-173.csv"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${SCRIPT_DIR}/logs/env-reinstall/aicomplexity-missing-r-${TIMESTAMP}"
SOURCE_DIR="${OUTPUT_DIR}/sources"
PACKAGE_LOG_DIR="${OUTPUT_DIR}/package-logs"

ORDERED_TARGETS="${OUTPUT_DIR}/ordered-targets.tsv"
STATUS_FILE="${OUTPUT_DIR}/install-status.csv"
BEFORE_PACKAGES="${OUTPUT_DIR}/r-installed-packages-before.csv"
AFTER_PACKAGES="${OUTPUT_DIR}/r-installed-packages-after.csv"
COMPARISON_FILE="${OUTPUT_DIR}/r-package-comparison-after.csv"
DIFFERENCES_FILE="${OUTPUT_DIR}/r-package-differences-after.csv"
SUMMARY_FILE="${OUTPUT_DIR}/r-package-validation-summary.txt"
SESSION_FILE="${OUTPUT_DIR}/r-session-info-after.txt"

mkdir -p \
    "${OUTPUT_DIR}" \
    "${SOURCE_DIR}" \
    "${PACKAGE_LOG_DIR}"

echo "============================================================"
echo "INSTALL MISSING AICOMPLEXITY R PACKAGES"
echo "============================================================"
echo "Repository:          ${REPO_DIR}"
echo "Environment:         ${ENV_NAME}"
echo "173 snapshot:        ${REFERENCE_DIR}"
echo "Canonical manifest:  ${CANONICAL_MANIFEST}"
echo "Missing manifest:    ${MISSING_MANIFEST}"
echo "Maximum passes:      ${MAX_PASSES}"
echo "Compile jobs:        ${NCPUS}"
echo "CRAN base:           ${CRAN_BASE}"
echo "Output:              ${OUTPUT_DIR}"
echo

for required_file in \
    "${CANONICAL_MANIFEST}" \
    "${MISSING_MANIFEST}"
do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty:"
        echo "  ${required_file}"
        exit 1
    fi
done

EXPECTED_MISSING_SHA256="6a1890a19dfd6e8b1644b6d83b9d955a5eb3b5492de7fadeec6bdf735844430c"
ACTUAL_MISSING_SHA256="$(
    sha256sum "${MISSING_MANIFEST}" |
        awk '{print $1}'
)"

if [[ "${ACTUAL_MISSING_SHA256}" != "${EXPECTED_MISSING_SHA256}" ]]; then
    echo "ERROR: Missing-package manifest checksum does not match."
    echo "Expected: ${EXPECTED_MISSING_SHA256}"
    echo "Actual:   ${ACTUAL_MISSING_SHA256}"
    exit 1
fi

echo "PASS: Missing-package manifest checksum"

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

# Load the Conda shell function without changing the interactive shell.
source "${CONDA_SH}"

if ! conda env list |
    awk 'NF > 0 && $1 !~ /^#/ {print $1}' |
    grep -Fxq "${ENV_NAME}"
then
    echo "ERROR: Conda environment does not exist: ${ENV_NAME}"
    exit 1
fi

ACTUAL_R_VERSION="$(
    conda run \
        --no-capture-output \
        --name "${ENV_NAME}" \
        Rscript -e '
            cat(
              paste(
                R.version$major,
                R.version$minor,
                sep = "."
              )
            )
        '
)"

if [[ "${ACTUAL_R_VERSION}" != "${EXPECTED_R_VERSION}" ]]; then
    echo "ERROR: Unexpected R version."
    echo "Expected: ${EXPECTED_R_VERSION}"
    echo "Actual:   ${ACTUAL_R_VERSION}"
    exit 1
fi

echo "PASS: R ${ACTUAL_R_VERSION}"

export TZ="America/Chicago"
export MAKEFLAGS="-j${NCPUS}"

echo
echo "============================================================"
echo "1. SAVE THE PRE-INSTALL PACKAGE INVENTORY"
echo "============================================================"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript - "${BEFORE_PACKAGES}" <<'RS'
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

echo "Installed packages before installation:"
echo "  $(($(wc -l < "${BEFORE_PACKAGES}") - 1))"

echo
echo "============================================================"
echo "2. BUILD A DEPENDENCY-AWARE INSTALLATION ORDER"
echo "============================================================"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript - \
    "${MISSING_MANIFEST}" \
    "${ORDERED_TARGETS}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

manifest_file <- args[[1]]
output_file <- args[[2]]

targets <- read.csv(
  manifest_file,
  stringsAsFactors = FALSE,
  check.names = FALSE
)

priority <- c(
  "R.methodsS3",
  "R.oo",
  "R.utils",
  "R.cache",
  "brew",
  "commonmark",
  "collections",
  "otel",
  "rex",
  "xmlparsedata",
  "desc",
  "rprojroot",
  "checkmate",
  "S7",
  "zoo",
  "sandwich",
  "miscTools",
  "maxLik",
  "bdsmatrix",
  "lmtest",
  "collapse",
  "dreamerr",
  "stringmagic",
  "fixest",
  "didimputation",
  "insight",
  "datawizard",
  "bayestestR",
  "parameters",
  "performance",
  "tinytable",
  "tables",
  "modelsummary",
  "showtextdb",
  "sysfonts",
  "showtext",
  "pkgbuild",
  "pkgload",
  "roxygen2",
  "styler",
  "lintr",
  "languageserver",
  "plm",
  "bacondecomp"
)

priority_rank <- match(targets$Package, priority)
priority_rank[is.na(priority_rank)] <- length(priority) + 1L

targets <- targets[
  order(priority_rank, targets$Package),
  c("Package", "Version"),
  drop = FALSE
]

write.table(
  targets,
  output_file,
  sep = "\t",
  row.names = FALSE,
  col.names = FALSE,
  quote = FALSE,
  na = ""
)
RS

echo "Installation targets:"
cat "${ORDERED_TARGETS}"

echo
echo "Target count:"
wc -l "${ORDERED_TARGETS}"

echo
echo "============================================================"
echo "3. DOWNLOAD EXACT CRAN SOURCE VERSIONS"
echo "============================================================"

while IFS=$'\t' read -r package version; do
    [[ -n "${package}" ]] || continue

    source_file="${SOURCE_DIR}/${package}_${version}.tar.gz"

    if [[ -s "${source_file}" ]] &&
        gzip -t "${source_file}" 2>/dev/null
    then
        echo "CACHED: ${package} ${version}"
        continue
    fi

    rm -f "${source_file}"

    echo "Downloading ${package} ${version}"

    conda run \
        --no-capture-output \
        --name "${ENV_NAME}" \
        Rscript - \
        "${package}" \
        "${version}" \
        "${source_file}" \
        "${CRAN_BASE}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

package <- args[[1]]
version <- args[[2]]
destination <- args[[3]]
cran_base <- sub("/+$", "", args[[4]])

filename <- paste0(
  package,
  "_",
  version,
  ".tar.gz"
)

urls <- c(
  paste0(
    cran_base,
    "/src/contrib/",
    filename
  ),
  paste0(
    cran_base,
    "/src/contrib/Archive/",
    package,
    "/",
    filename
  )
)

downloaded <- FALSE
errors <- character()

for (url in urls) {
  message("Trying: ", url)

  result <- tryCatch(
    {
      suppressWarnings(
        download.file(
          url = url,
          destfile = destination,
          method = "libcurl",
          mode = "wb",
          quiet = FALSE
        )
      )

      if (!file.exists(destination)) {
        stop("The destination file was not created.")
      }

      if (file.info(destination)$size <= 0L) {
        stop("The downloaded file is empty.")
      }

      archive_entries <- utils::untar(
        destination,
        list = TRUE
      )

      if (length(archive_entries) == 0L) {
        stop("The downloaded archive has no entries.")
      }

      downloaded <- TRUE
      message("Downloaded: ", url)
      TRUE
    },
    error = function(error) {
      errors <<- c(
        errors,
        paste0(
          url,
          " :: ",
          conditionMessage(error)
        )
      )

      if (file.exists(destination)) {
        unlink(destination)
      }

      FALSE
    }
  )

  if (isTRUE(result) && downloaded) {
    break
  }
}

if (!downloaded) {
  stop(
    paste(
      c(
        paste0(
          "Could not download ",
          package,
          " ",
          version
        ),
        errors
      ),
      collapse = "\n"
    )
  )
}
RS

    gzip -t "${source_file}" || {
        echo "ERROR: Invalid source archive:"
        echo "  ${source_file}"
        exit 1
    }

    echo "PASS: ${source_file}"
done < "${ORDERED_TARGETS}"

echo
echo "Downloaded source archives:"
find "${SOURCE_DIR}" \
    -maxdepth 1 \
    -type f \
    -name '*.tar.gz' \
    | sort

echo
echo "Source archive count:"
find "${SOURCE_DIR}" \
    -maxdepth 1 \
    -type f \
    -name '*.tar.gz' \
    | wc -l

printf '%s\n' \
    '"Pass","Package","ExpectedVersion","Result","LogFile"' \
    > "${STATUS_FILE}"

package_is_exact() {
    local package="$1"
    local version="$2"

    conda run \
        --no-capture-output \
        --name "${ENV_NAME}" \
        Rscript -e '
            args <- commandArgs(trailingOnly = TRUE)
            package <- args[[1]]
            expected <- args[[2]]

            installed <- requireNamespace(
              package,
              quietly = TRUE
            )

            exact <- installed &&
              identical(
                as.character(packageVersion(package)),
                expected
              )

            quit(
              status = ifelse(exact, 0L, 1L)
            )
        ' \
        "${package}" \
        "${version}" \
        >/dev/null 2>&1
}

echo
echo "============================================================"
echo "4. INSTALL MISSING PACKAGES IN MULTIPLE PASSES"
echo "============================================================"

for pass in $(seq 1 "${MAX_PASSES}"); do
    remaining_before=0

    while IFS=$'\t' read -r package version; do
        [[ -n "${package}" ]] || continue

        if ! package_is_exact "${package}" "${version}"; then
            remaining_before=$((remaining_before + 1))
        fi
    done < "${ORDERED_TARGETS}"

    echo
    echo "------------------------------------------------------------"
    echo "Pass ${pass}"
    echo "Remaining before pass: ${remaining_before}"
    echo "------------------------------------------------------------"

    if [[ "${remaining_before}" -eq 0 ]]; then
        echo "All target packages are installed."
        break
    fi

    installed_this_pass=0

    while IFS=$'\t' read -r package version; do
        [[ -n "${package}" ]] || continue

        if package_is_exact "${package}" "${version}"; then
            continue
        fi

        source_file="${SOURCE_DIR}/${package}_${version}.tar.gz"
        safe_package="$(
            printf '%s' "${package}" |
                tr -c 'A-Za-z0-9._-' '_'
        )"
        log_file="${PACKAGE_LOG_DIR}/pass-${pass}-${safe_package}-${version}.log"

        echo
        echo "[Pass ${pass}] Installing ${package} ${version}"

        set +e

        conda run \
            --no-capture-output \
            --name "${ENV_NAME}" \
            R CMD INSTALL \
            --preclean \
            --no-multiarch \
            --with-keep.source \
            "${source_file}" \
            > >(tee "${log_file}") \
            2>&1

        install_exit=$?

        set -e

        if [[ "${install_exit}" -eq 0 ]] &&
            package_is_exact "${package}" "${version}"
        then
            result="installed"
            installed_this_pass=$((installed_this_pass + 1))
            echo "PASS: ${package} ${version}"
        else
            result="deferred_or_failed"
            echo "DEFERRED: ${package} ${version}"
            echo "Log: ${log_file}"
        fi

        printf '"%s","%s","%s","%s","%s"\n' \
            "${pass}" \
            "${package}" \
            "${version}" \
            "${result}" \
            "${log_file}" \
            >> "${STATUS_FILE}"
    done < "${ORDERED_TARGETS}"

    remaining_after=0

    while IFS=$'\t' read -r package version; do
        [[ -n "${package}" ]] || continue

        if ! package_is_exact "${package}" "${version}"; then
            remaining_after=$((remaining_after + 1))
        fi
    done < "${ORDERED_TARGETS}"

    echo
    echo "Installed during pass: ${installed_this_pass}"
    echo "Remaining after pass:  ${remaining_after}"

    if [[ "${remaining_after}" -eq 0 ]]; then
        break
    fi

    if [[ "${installed_this_pass}" -eq 0 ]]; then
        echo "No progress was made during this pass."
        echo "Stopping iterative installation."
        break
    fi
done

echo
echo "============================================================"
echo "5. VALIDATE AGAINST THE CURRENT 173 MANIFEST"
echo "============================================================"

conda run \
    --no-capture-output \
    --name "${ENV_NAME}" \
    Rscript - \
    "${CANONICAL_MANIFEST}" \
    "${AFTER_PACKAGES}" \
    "${COMPARISON_FILE}" \
    "${DIFFERENCES_FILE}" \
    "${SUMMARY_FILE}" \
    "${SESSION_FILE}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)

reference_file <- args[[1]]
current_file <- args[[2]]
comparison_file <- args[[3]]
differences_file <- args[[4]]
summary_file <- args[[5]]
session_file <- args[[6]]

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

current_compare <- current[, c(
  "Package",
  "Version",
  "LibPath",
  "Built"
)]
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
    comparison$ExpectedVersion ==
      comparison$ActualVersion,
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

differences <- comparison[
  comparison$Status != "match",
  ,
  drop = FALSE
]

write.csv(
  differences,
  differences_file,
  row.names = FALSE,
  quote = TRUE
)

summary_lines <- c(
  paste0(
    "r_version=",
    paste(
      R.version$major,
      R.version$minor,
      sep = "."
    )
  ),
  paste0(
    "reference_packages=",
    nrow(reference)
  ),
  paste0(
    "installed_packages=",
    nrow(current)
  ),
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
  paste0(
    "r_home=",
    R.home()
  ),
  paste0(
    "primary_library=",
    .libPaths()[[1]]
  ),
  paste0(
    "timezone=",
    Sys.timezone()
  )
)

writeLines(
  summary_lines,
  summary_file
)

session_connection <- file(
  session_file,
  open = "wt"
)

sink(session_connection)
print(sessionInfo())
sink()

close(session_connection)
RS

cat "${SUMMARY_FILE}"

echo
echo "Remaining differences:"

if [[ $(wc -l < "${DIFFERENCES_FILE}") -gt 1 ]]; then
    cat "${DIFFERENCES_FILE}"
else
    echo "None"
fi

echo
echo "============================================================"
echo "6. VERIFY CRITICAL DID PACKAGES"
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
  sandwich = "3.1.1",
  zoo = "1.8.15",
  plm = "2.6.7"
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

  status <- if (
    identical(
      actual,
      expected[[package]]
    )
  ) {
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

quit(
  status = ifelse(
    failure_count == 0L,
    0L,
    1L
  )
)
RS

VALIDATION_FAILURES="$(
    awk -F= \
        '$1 == "validation_failures" {print $2}' \
        "${SUMMARY_FILE}"
)"

echo
echo "============================================================"

if [[ -z "${VALIDATION_FAILURES}" ]]; then
    echo "ERROR: Validation result could not be determined."
    exit 1
fi

if [[ "${VALIDATION_FAILURES}" -ne 0 ]]; then
    echo "WARNING: ${VALIDATION_FAILURES} package differences remain."
    echo
    echo "Review:"
    echo "  ${DIFFERENCES_FILE}"
    echo "  ${STATUS_FILE}"
    echo "  ${PACKAGE_LOG_DIR}"
    echo
    echo "Do not run DiD yet."
    exit 1
fi

echo "PASS: All 250 canonical R packages match system12."
echo
echo "Validation output:"
echo "  ${OUTPUT_DIR}"
echo "============================================================"
