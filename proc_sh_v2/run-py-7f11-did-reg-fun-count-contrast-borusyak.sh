#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f11-did-reg-fun-count-contrast-borusyak-v1.sh
# -----------------------------------------------------------------------------
# Apply the locked run-py-7f09 Borusyak imputation DiD specification to the
# run-py-7f10 repository-month count contrast:
#
#   other_functions count - testing count
#
# This directly tests:
#
#   H0: ATT_other_functions - ATT_testing = 0
#
# Covariance-aware inference is obtained by combining the two outcomes within
# repository-month before estimation and clustering uncertainty by repository.
#
# The wrapper is standalone. It reuses the scientific logic and shared R helper
# used by run-py-7f09 but does not call any earlier shell wrapper.
#
# Locked model contract:
#   - Outcome scale: raw count difference; negative values are allowed
#   - No log1p outcome transformation
#   - Zero-count months: retained
#   - Covariates: log1p_age, raw ncloc_python_snapshot,
#     log1p_contributors, log1p_stars, log1p_issues
#   - Fixed effects: repository and sequential calendar month
#   - Treatment cohorts: 2024-08 through 2025-03
#   - Dynamic horizon: -6 through +6
#   - Reference period: -1, omitted and normalized to zero
#   - Estimated dynamic periods: -6 through -2 and 0 through +6 (12 rows)
#   - Pre-trend leads: -6 through -2
#   - Uncertainty: didimputation analytic standard errors and 95% confidence
#     intervals, clustered at repository through the idname default
#
# Input:
#   repo_python/run-py-7f10/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f10-did-input-other-minus-testing-count-contrast.csv
#
# Outputs:
#   repo_python/run-py-7f11/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/other_minus_testing/
#
# Server files are versionless:
#   proc_r/DiffInDiffBorusyak_reg_fun_count_contrast.Rmd
#   proc_sh_v2/run-py-7f11-did-reg-fun-count-contrast-borusyak.sh
#
# Default execution:
#   bash proc_sh_v2/run-py-7f11-did-reg-fun-count-contrast-borusyak.sh
#
# Intentional re-run:
#   OVERWRITE_OUTPUT=1 \
#   bash proc_sh_v2/run-py-7f11-did-reg-fun-count-contrast-borusyak.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_reg_fun_count_contrast.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"

ANALYSIS_SUFFIX="specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}"
INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-7f10/strict/${ANALYSIS_SUFFIX}}"
INPUT_FILE="${INPUT_FILE:-run-py-7f10-did-input-other-minus-testing-count-contrast.csv}"
PANEL_PATH="${PANEL_PATH:-${INPUT_ROOT}/${INPUT_FILE}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7f11/strict/${ANALYSIS_SUFFIX}}"
OUTCOME_GROUP="other_minus_testing"
OUT_DIR="${OUTPUT_ROOT}/${OUTCOME_GROUP}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f11}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f11-did-reg-fun-count-contrast-${SPECIFICATION_NAME}-${RUN_TS}.log}"

PREFIX="borusyak_reg_fun_count_contrast_other_minus_testing"
HTML_OUTPUT="DiffInDiffBorusyak_reg_fun_count_contrast_other_minus_testing_${SPECIFICATION_NAME}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"
PDF_OUTPUT="dynamic_effects_borusyak_reg_fun_count_contrast_other_minus_testing.pdf"

case "${NCLOC_SPEC}" in
    python_snapshot) ;;
    *)
        echo "ERROR: run-py-7f11 requires NCLOC_SPEC=python_snapshot." >&2
        exit 2
        ;;
esac
case "${TIME_MODE}" in
    calendar_month) ;;
    *)
        echo "ERROR: run-py-7f11 requires TIME_MODE=calendar_month." >&2
        exit 2
        ;;
esac
case "${PARSE_EXCLUSION_MODE}" in
    parse_clean) ;;
    *)
        echo "ERROR: run-py-7f11 requires PARSE_EXCLUSION_MODE=parse_clean." >&2
        exit 2
        ;;
esac

for binary_flag in RUN_SELF_TEST SELF_TEST_ONLY OVERWRITE_OUTPUT; do
    value="${!binary_flag}"
    case "${value}" in
        0|1) ;;
        *)
            echo "ERROR: ${binary_flag} must be 0 or 1." >&2
            exit 2
            ;;
    esac
done
if [[ "${SELF_TEST_ONLY}" == "1" && "${RUN_SELF_TEST}" != "1" ]]; then
    echo "ERROR: SELF_TEST_ONLY=1 requires RUN_SELF_TEST=1." >&2
    exit 2
fi

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
    exit 2
fi
for required_file in "${RMD_FILE}" "${HELPER_FILE}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required file is missing or empty: ${required_file}" >&2
        exit 2
    fi
done
if [[ "${SELF_TEST_ONLY}" != "1" && ! -s "${PANEL_PATH}" ]]; then
    echo "ERROR: Input file is missing or empty: ${PANEL_PATH}" >&2
    exit 2
fi

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"
COMPLETED_RUNS=0
CURRENT_RUN="not started"

finish() {
    local exit_code=$?
    local end_epoch elapsed hours minutes seconds
    end_epoch="$(date +%s)"
    elapsed=$((end_epoch - START_EPOCH))
    hours=$((elapsed / 3600))
    minutes=$(((elapsed % 3600) / 60))
    seconds=$((elapsed % 60))

    echo
    echo "================================================================================"
    echo "run-py-7f11 execution summary"
    echo "Started:          ${START_TIME}"
    echo "Completed:        $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:          %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Completed runs:   ${COMPLETED_RUNS}"
    echo "Last/current run: ${CURRENT_RUN}"
    echo "Exit code:        ${exit_code}"
    echo "Output root:      ${OUTPUT_ROOT}"
    echo "Log file:         ${LOG_FILE}"
    echo "================================================================================"
    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

RMD_SHA="$(sha256sum "${RMD_FILE}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7f11: covariance-aware Borusyak count contrast"
echo "Started:                         ${START_TIME}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
echo "R version:                       $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
echo "R Markdown:                      ${RMD_FILE}"
echo "R Markdown SHA:                  ${RMD_SHA}"
echo "Helper:                          ${HELPER_FILE}"
echo "Helper SHA:                      ${HELPER_SHA}"
echo "Input panel:                     ${PANEL_PATH}"
echo "Output directory:                ${OUT_DIR}"
echo "Contrast:                        other_functions - testing"
echo "Null hypothesis:                 ATT_other - ATT_testing = 0"
echo "Outcome scale:                   raw_count_difference"
echo "Negative values:                 allowed"
echo "log1p outcome transformation:    NONE"
echo "Zero-count months:               retained"
echo "Covariates:                      log1p_age + ncloc_python_snapshot + log1p_contributors + log1p_stars + log1p_issues"
echo "NCLOC scaling:                   raw"
echo "Fixed effects:                   repo_id + time_id"
echo "Time encoding:                   sequential calendar month"
echo "Treatment cohorts:               2024-08 through 2025-03"
echo "Dynamic horizon:                 -6 through +6"
echo "Reference period:                -1 (omitted; normalized to zero)"
echo "Estimated dynamic periods:       -6:-2 and 0:+6 (12)"
echo "Pre-trend leads:                 -6 through -2"
echo "Uncertainty:                     analytic SE and 95% CI; repository clustered"
echo "Covariance handling:             row-level contrast before estimation"
echo "Pre-trend family-wise diagnostic: Bonferroni"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    PANEL_PATH_ABS="${PROJECT_ROOT}/${PANEL_PATH}" \
    SELF_TEST_ONLY_FLAG="${SELF_TEST_ONLY}" \
    "${RSCRIPT_BIN}" - <<'RS'
suppressPackageStartupMessages(library(data.table))

required_packages <- c(
  "rmarkdown", "data.table", "dplyr", "ggplot2", "didimputation"
)
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_packages) > 0) {
  stop("Missing required R packages: ", paste(missing_packages, collapse = ", "))
}

if (Sys.getenv("SELF_TEST_ONLY_FLAG") == "1") {
  cat("Package self-test: PASS\n")
  quit(save = "no", status = 0)
}

panel <- fread(Sys.getenv("PANEL_PATH_ABS"))
count_col <-
  "npr_agc_other_minus_testing_regular_module_function_unique_bodies"
testing_col <- "npr_agc_testing_regular_module_function_unique_bodies"
other_col <- "npr_agc_other_regular_module_function_unique_bodies"
all_col <- "npr_agc_all_regular_module_function_unique_bodies"
covariates <- c(
  "log1p_age", "ncloc_python_snapshot", "log1p_contributors",
  "log1p_stars", "log1p_issues"
)

if (nrow(panel) != 1521) stop("Unexpected contrast-panel row count")
if (uniqueN(panel$repo_name) != 218) stop("Unexpected contrast-panel repo count")
if (anyDuplicated(panel[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Duplicate repository-month keys")
}
if (anyNA(panel[, c(count_col, covariates), with = FALSE])) {
  stop("Missing outcome or covariate values")
}
if (!all(panel[[count_col]] == panel[[other_col]] - panel[[testing_col]])) {
  stop("Contrast arithmetic mismatch")
}
if (!all(panel[[all_col]] == panel[[other_col]] + panel[[testing_col]])) {
  stop("Binary-group reconciliation mismatch")
}
if (sum(panel[[testing_col]]) != 627) stop("Testing total mismatch")
if (sum(panel[[other_col]]) != 1622) stop("Other-functions total mismatch")
if (sum(panel[[all_col]]) != 2249) stop("All-functions total mismatch")
if (sum(panel[[count_col]]) != 995) stop("Contrast total mismatch")
if (sum(panel[[count_col]] < 0) != 112) stop("Negative-row mismatch")
if (sum(panel[[count_col]] == 0) != 1064) stop("Zero-row mismatch")
if (sum(panel[[count_col]] > 0) != 345) stop("Positive-row mismatch")
if (!all(panel$regular_function_contrast_id == "other_minus_testing")) {
  stop("Contrast id mismatch")
}
if (!all(
  panel$regular_function_contrast_schema_version == "run-py-7f10-v1"
)) {
  stop("Contrast schema mismatch")
}

cat("Self-test: PASS\n")
cat("Rows/repositories: 1,521/218\n")
cat("Component totals (T/O/A): 627/1,622/2,249\n")
cat("Contrast total: 995\n")
cat("Contrast sign rows (N/Z/P): 112/1,064/345\n")
cat("Covariate missingness: 0\n")
cat("Row-level arithmetic mismatches: 0\n")
RS
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    CURRENT_RUN="self-test only completed"
    echo "run-py-7f11 self-test-only mode complete."
    exit 0
fi

mkdir -p "${OUT_DIR}"
EXPECTED_OUTPUTS=(
    "${OUT_DIR}/${HTML_OUTPUT}"
    "${OUT_DIR}/${PREFIX}_static_effects.csv"
    "${OUT_DIR}/${PREFIX}_dynamic_effects.csv"
    "${OUT_DIR}/${PREFIX}_uncertainty.csv"
    "${OUT_DIR}/${PREFIX}_pretrend_effects.csv"
    "${OUT_DIR}/${PREFIX}_pretrend_summary.csv"
    "${OUT_DIR}/${PREFIX}_panel_checks.csv"
    "${OUT_DIR}/${PREFIX}_input_summary.csv"
    "${OUT_DIR}/${PREFIX}_static_errors.csv"
    "${OUT_DIR}/${PREFIX}_dynamic_errors.csv"
    "${OUT_DIR}/${PREFIX}_final_model_validation.csv"
    "${OUT_DIR}/${PREFIX}_metadata.csv"
    "${OUT_DIR}/${PDF_OUTPUT}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    rm -f "${EXPECTED_OUTPUTS[@]}"
else
    for expected_file in "${EXPECTED_OUTPUTS[@]}"; do
        if [[ -e "${expected_file}" ]]; then
            echo "ERROR: Output exists and OVERWRITE_OUTPUT=0: ${expected_file}" >&2
            exit 2
        fi
    done
fi

CURRENT_RUN="outcome_group=${OUTCOME_GROUP}"
render_start_epoch="$(date +%s)"

echo
echo "--------------------------------------------------------------------------------"
echo "[01/01] ${CURRENT_RUN}"
echo "Input SHA:        $(sha256sum "${PANEL_PATH}" | awk '{print $1}')"
echo "Output directory: ${OUT_DIR}"
echo "HTML output:      ${HTML_OUTPUT}"
echo "--------------------------------------------------------------------------------"

PROJECT_ROOT="${PROJECT_ROOT}" \
PANEL_PATH="${PROJECT_ROOT}/${PANEL_PATH}" \
OUT_DIR="${PROJECT_ROOT}/${OUT_DIR}" \
PANEL_LABEL="strict_${SPECIFICATION_NAME}_${OUTCOME_GROUP}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}" \
OUTCOME_GROUP="${OUTCOME_GROUP}" \
SPECIFICATION_NAME="${SPECIFICATION_NAME}" \
NCLOC_SPEC="${NCLOC_SPEC}" \
TIME_MODE="${TIME_MODE}" \
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE}" \
HELPER_FILE="${PROJECT_ROOT}/${HELPER_FILE}" \
RMD_SOURCE_PATH="${RMD_FILE}" \
RMD_SHA256="${RMD_SHA}" \
OUTPUT_HTML="${HTML_OUTPUT}" \
    "${RSCRIPT_BIN}" -e "rmarkdown::render(
      input = '${PROJECT_ROOT}/${RMD_FILE}',
      output_file = Sys.getenv('OUTPUT_HTML'),
      output_dir = Sys.getenv('OUT_DIR'),
      knit_root_dir = Sys.getenv('PROJECT_ROOT'),
      envir = new.env(parent = globalenv()),
      quiet = FALSE
    )"

for expected_file in "${EXPECTED_OUTPUTS[@]}"; do
    if [[ ! -s "${expected_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
        exit 3
    fi
done

VALIDATION_FILE="${OUT_DIR}/${PREFIX}_final_model_validation.csv"
status_value="$(awk -F, '$1 == "status" {gsub(/\r|"/, "", $2); print $2}' \
    "${VALIDATION_FILE}")"
static_errors="$(awk -F, '$1 == "static_model_error_count" {gsub(/\r|"/, "", $2); print $2}' \
    "${VALIDATION_FILE}")"
dynamic_errors="$(awk -F, '$1 == "dynamic_model_error_count" {gsub(/\r|"/, "", $2); print $2}' \
    "${VALIDATION_FILE}")"
dynamic_complete="$(awk -F, '$1 == "dynamic_effects_complete_12_estimated_periods" {gsub(/\r|"/, "", $2); print $2}' \
    "${VALIDATION_FILE}")"
pretrend_complete="$(awk -F, '$1 == "pretrend_effects_complete_5_periods" {gsub(/\r|"/, "", $2); print $2}' \
    "${VALIDATION_FILE}")"

if [[ "${status_value}" != "PASS" ]]; then
    echo "ERROR: Final model status is not PASS: ${status_value:-missing}" >&2
    exit 4
fi
if [[ "${static_errors}" != "0" || "${dynamic_errors}" != "0" ]]; then
    echo "ERROR: Estimator errors detected." >&2
    exit 4
fi
if [[ "${dynamic_complete}" != "TRUE" || "${pretrend_complete}" != "TRUE" ]]; then
    echo "ERROR: Dynamic or pre-trend horizon validation failed." >&2
    exit 4
fi

COMPLETED_RUNS=1
CURRENT_RUN="covariance-aware contrast completed"
render_elapsed=$(($(date +%s) - render_start_epoch))

echo
echo "run-py-7f11 PASS: covariance-aware Borusyak contrast completed."
echo "Elapsed model time:     ${render_elapsed}s"
echo "Static ATT rows:        1"
echo "Dynamic-effect rows:    12"
echo "Reference period:       -1 (omitted; normalized to zero)"
echo "Uncertainty rows:       13"
echo "Pre-trend-effect rows:  5"
echo "Pre-trend summaries:    1"
