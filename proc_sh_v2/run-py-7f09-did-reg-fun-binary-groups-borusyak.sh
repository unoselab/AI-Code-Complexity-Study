#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f09-did-reg-fun-binary-groups-borusyak-v2.sh
# -----------------------------------------------------------------------------
# Apply one locked Borusyak imputation DiD specification to the three
# zero-inclusive run-py-7f08 regular-function outcomes:
#
#   1. testing
#   2. other_functions
#   3. all_regular_functions
#
# The wrapper is standalone. It reuses the scientific logic and shared R helper
# used by run-py-7f, but it does not call any earlier shell wrapper.
#
# Locked model contract:
#   - Outcome scale: raw distinct-body count per repository-month
#   - Zero-count months: retained
#   - NCLOC: ncloc_python_snapshot on its raw scale
#   - Other covariates: log1p_age, log1p_contributors, log1p_stars,
#     log1p_issues
#   - Fixed effects: repository and sequential calendar month
#   - Treatment cohorts: 2024-08 through 2025-03
#   - Dynamic horizon: -6 through +6
#   - Reference period: -1, omitted and normalized to zero
#   - Estimated dynamic periods: -6 through -2 and 0 through +6 (12 rows)
#   - Pre-trend leads: -6 through -2
#   - Uncertainty: didimputation analytic standard errors and 95% confidence
#     intervals, clustered at repository through the idname default
#
# Inputs:
#   repo_python/run-py-7f08/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f08-did-input-testing-regular-functions.csv
#       run-py-7f08-did-input-other-regular-functions.csv
#       run-py-7f08-did-input-all-regular-functions.csv
#
# Outputs:
#   repo_python/run-py-7f09/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/<outcome-group>/
#
# Default execution:
#   bash proc_sh_v2/run-py-7f09-did-reg-fun-binary-groups-borusyak.sh
#
# Overwrite an existing run:
#   OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7f09-did-reg-fun-binary-groups-borusyak.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_reg_fun_binary_groups.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"

INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-7f08/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7f09/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f09}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f09-did-reg-fun-binary-groups-${SPECIFICATION_NAME}-${RUN_TS}.log}"

OUTCOME_GROUPS=(testing other_functions all_regular_functions)
INPUT_FILES=(
    "run-py-7f08-did-input-testing-regular-functions.csv"
    "run-py-7f08-did-input-other-regular-functions.csv"
    "run-py-7f08-did-input-all-regular-functions.csv"
)

case "${NCLOC_SPEC}" in
    python_snapshot) ;;
    *)
        echo "ERROR: run-py-7f09 requires NCLOC_SPEC=python_snapshot." >&2
        exit 2
        ;;
esac

case "${TIME_MODE}" in
    calendar_month) ;;
    *)
        echo "ERROR: run-py-7f09 requires TIME_MODE=calendar_month." >&2
        exit 2
        ;;
esac

case "${PARSE_EXCLUSION_MODE}" in
    parse_clean) ;;
    *)
        echo "ERROR: run-py-7f09 requires PARSE_EXCLUSION_MODE=parse_clean." >&2
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

for input_file in "${INPUT_FILES[@]}"; do
    if [[ ! -s "${INPUT_ROOT}/${input_file}" ]]; then
        echo "ERROR: Input file is missing or empty: ${INPUT_ROOT}/${input_file}" >&2
        exit 2
    fi
done

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"
PLANNED_RUNS="${#OUTCOME_GROUPS[@]}"
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
    echo "run-py-7f09 execution summary"
    echo "Started:              ${START_TIME}"
    echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:              %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Planned outcome runs: ${PLANNED_RUNS}"
    echo "Completed runs:       ${COMPLETED_RUNS}"
    echo "Last/current run:     ${CURRENT_RUN}"
    echo "Exit code:            ${exit_code}"
    echo "Output root:          ${OUTPUT_ROOT}"
    echo "Log file:             ${LOG_FILE}"
    echo "================================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

RMD_SHA="$(sha256sum "${RMD_FILE}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7f09: Borusyak DiD for binary regular-function groups"
echo "Started:                         ${START_TIME}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
echo "R version:                       $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
echo "R Markdown:                      ${RMD_FILE}"
echo "R Markdown SHA:                  ${RMD_SHA}"
echo "Helper:                          ${HELPER_FILE}"
echo "Helper SHA:                      ${HELPER_SHA}"
echo "Input root:                      ${INPUT_ROOT}"
echo "Output root:                     ${OUTPUT_ROOT}"
echo "Outcome groups:                  ${OUTCOME_GROUPS[*]}"
echo "Outcome scale:                   raw_count"
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
echo "Pre-trend family-wise diagnostic: Bonferroni"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Self-test only:                  ${SELF_TEST_ONLY}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    INPUT_ROOT_ABS="${PROJECT_ROOT}/${INPUT_ROOT}" \
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

input_root <- Sys.getenv("INPUT_ROOT_ABS")
groups <- c("testing", "other_functions", "all_regular_functions")
files <- c(
  "run-py-7f08-did-input-testing-regular-functions.csv",
  "run-py-7f08-did-input-other-regular-functions.csv",
  "run-py-7f08-did-input-all-regular-functions.csv"
)
expected_totals <- c(627, 1622, 2249)
expected_positive <- c(198, 417, 486)
expected_zero <- c(1323, 1104, 1035)
count_col <- "npr_agc_regular_module_function_unique_bodies"
covariates <- c(
  "log1p_age", "ncloc_python_snapshot", "log1p_contributors",
  "log1p_stars", "log1p_issues"
)

panels <- lapply(file.path(input_root, files), fread)
reference_keys <- panels[[1]][, .(dataset_source, repo_name, time)]

for (i in seq_along(panels)) {
  panel <- panels[[i]]
  if (nrow(panel) != 1521) stop("Unexpected row count for ", groups[i])
  if (uniqueN(panel$repo_name) != 218) stop("Unexpected repo count for ", groups[i])
  if (!identical(reference_keys, panel[, .(dataset_source, repo_name, time)])) {
    stop("Repository-month keys or order differ for ", groups[i])
  }
  if (!all(panel$regular_function_outcome_group == groups[i])) {
    stop("Outcome-group label mismatch for ", groups[i])
  }
  if (sum(panel[[count_col]]) != expected_totals[i]) {
    stop("Count total mismatch for ", groups[i])
  }
  if (sum(panel[[count_col]] > 0) != expected_positive[i]) {
    stop("Positive-row mismatch for ", groups[i])
  }
  if (sum(panel[[count_col]] == 0) != expected_zero[i]) {
    stop("Zero-row mismatch for ", groups[i])
  }
  if (anyNA(panel[, ..covariates])) {
    stop("Covariate missingness for ", groups[i])
  }
}

if (!all(
  panels[[1]][[count_col]] + panels[[2]][[count_col]] ==
    panels[[3]][[count_col]]
)) {
  stop("testing + other_functions does not equal all_regular_functions.")
}

cat("Self-test: PASS\n")
cat("Rows per outcome: 1,521\n")
cat("Repositories per outcome: 218\n")
cat("Outcome totals (T/O/A): 627/1,622/2,249\n")
cat("Covariate missingness: 0\n")
cat("Row-level binary reconciliation mismatches: 0\n")
RS
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    CURRENT_RUN="self-test only completed"
    echo "run-py-7f09 self-test-only mode complete."
    exit 0
fi

mkdir -p "${OUTPUT_ROOT}"

for index in "${!OUTCOME_GROUPS[@]}"; do
    outcome_group="${OUTCOME_GROUPS[${index}]}"
    input_file="${INPUT_FILES[${index}]}"
    panel_path="${INPUT_ROOT}/${input_file}"
    out_dir="${OUTPUT_ROOT}/${outcome_group}"
    prefix="borusyak_reg_fun_binary_group_${outcome_group}"
    html_output="DiffInDiffBorusyak_reg_fun_binary_group_${outcome_group}_${SPECIFICATION_NAME}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"
    pdf_output="dynamic_effects_borusyak_reg_fun_binary_group_${outcome_group}.pdf"

    mkdir -p "${out_dir}"

    expected_outputs=(
        "${out_dir}/${html_output}"
        "${out_dir}/${prefix}_static_effects.csv"
        "${out_dir}/${prefix}_dynamic_effects.csv"
        "${out_dir}/${prefix}_uncertainty.csv"
        "${out_dir}/${prefix}_pretrend_effects.csv"
        "${out_dir}/${prefix}_pretrend_summary.csv"
        "${out_dir}/${prefix}_panel_checks.csv"
        "${out_dir}/${prefix}_input_summary.csv"
        "${out_dir}/${prefix}_static_errors.csv"
        "${out_dir}/${prefix}_dynamic_errors.csv"
        "${out_dir}/${prefix}_final_model_validation.csv"
        "${out_dir}/${prefix}_metadata.csv"
        "${out_dir}/${pdf_output}"
    )

    if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
        rm -f "${expected_outputs[@]}"
    else
        for expected_file in "${expected_outputs[@]}"; do
            if [[ -e "${expected_file}" ]]; then
                echo "ERROR: Output exists and OVERWRITE_OUTPUT=0: ${expected_file}" >&2
                exit 2
            fi
        done
    fi

    CURRENT_RUN="outcome_group=${outcome_group}"
    run_number=$((COMPLETED_RUNS + 1))
    render_start_epoch="$(date +%s)"

    echo
    echo "--------------------------------------------------------------------------------"
    printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
    echo "Input panel:      ${panel_path}"
    echo "Input SHA:        $(sha256sum "${panel_path}" | awk '{print $1}')"
    echo "Output directory: ${out_dir}"
    echo "HTML output:      ${html_output}"
    echo "--------------------------------------------------------------------------------"

    PROJECT_ROOT="${PROJECT_ROOT}" \
    PANEL_PATH="${PROJECT_ROOT}/${panel_path}" \
    OUT_DIR="${PROJECT_ROOT}/${out_dir}" \
    PANEL_LABEL="strict_${SPECIFICATION_NAME}_${outcome_group}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}" \
    OUTCOME_GROUP="${outcome_group}" \
    SPECIFICATION_NAME="${SPECIFICATION_NAME}" \
    NCLOC_SPEC="${NCLOC_SPEC}" \
    TIME_MODE="${TIME_MODE}" \
    PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE}" \
    HELPER_FILE="${PROJECT_ROOT}/${HELPER_FILE}" \
    OUTPUT_HTML="${html_output}" \
        "${RSCRIPT_BIN}" -e "rmarkdown::render(
          input = '${PROJECT_ROOT}/${RMD_FILE}',
          output_file = Sys.getenv('OUTPUT_HTML'),
          output_dir = Sys.getenv('OUT_DIR'),
          knit_root_dir = Sys.getenv('PROJECT_ROOT'),
          envir = new.env(parent = globalenv()),
          quiet = FALSE
        )"

    for expected_file in "${expected_outputs[@]}"; do
        if [[ ! -s "${expected_file}" ]]; then
            echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
            exit 3
        fi
    done

    status_value="$(awk -F, '$1 == "status" {gsub(/\r|\"/, "", $2); print $2}' \
        "${out_dir}/${prefix}_final_model_validation.csv")"
    static_errors="$(awk -F, '$1 == "static_model_error_count" {gsub(/\r|\"/, "", $2); print $2}' \
        "${out_dir}/${prefix}_final_model_validation.csv")"
    dynamic_errors="$(awk -F, '$1 == "dynamic_model_error_count" {gsub(/\r|\"/, "", $2); print $2}' \
        "${out_dir}/${prefix}_final_model_validation.csv")"
    dynamic_complete="$(awk -F, '$1 == "dynamic_effects_complete_12_estimated_periods" {gsub(/\r|\"/, "", $2); print $2}' \
        "${out_dir}/${prefix}_final_model_validation.csv")"
    pretrend_complete="$(awk -F, '$1 == "pretrend_effects_complete_5_periods" {gsub(/\r|\"/, "", $2); print $2}' \
        "${out_dir}/${prefix}_final_model_validation.csv")"

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

    COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
    render_elapsed=$(($(date +%s) - render_start_epoch))
    printf '[%02d/%02d] PASS elapsed=%ds static_errors=%s dynamic_errors=%s\n' \
        "${COMPLETED_RUNS}" "${PLANNED_RUNS}" "${render_elapsed}" \
        "${static_errors}" "${dynamic_errors}"
done

combined_outputs=(
    "${OUTPUT_ROOT}/run-py-7f09-static-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f09-dynamic-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f09-uncertainty-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f09-pretrend-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f09-pretrend-summary-all-outcomes.csv"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    rm -f "${combined_outputs[@]}"
else
    for combined_file in "${combined_outputs[@]}"; do
        if [[ -e "${combined_file}" ]]; then
            echo "ERROR: Combined output exists and OVERWRITE_OUTPUT=0: ${combined_file}" >&2
            exit 2
        fi
    done
fi

COMBINED_ROOT="${PROJECT_ROOT}/${OUTPUT_ROOT}" \
"${RSCRIPT_BIN}" - <<'RS'
suppressPackageStartupMessages(library(data.table))

root <- Sys.getenv("COMBINED_ROOT")
groups <- c("testing", "other_functions", "all_regular_functions")

combine_group_files <- function(suffix, output_name) {
  paths <- file.path(
    root,
    groups,
    paste0("borusyak_reg_fun_binary_group_", groups, suffix)
  )
  missing <- paths[!file.exists(paths)]
  if (length(missing) > 0) {
    stop("Missing group output(s): ", paste(missing, collapse = ", "))
  }
  combined <- rbindlist(lapply(paths, fread), fill = TRUE, use.names = TRUE)
  fwrite(combined, file.path(root, output_name))
}

combine_group_files(
  "_static_effects.csv",
  "run-py-7f09-static-effects-all-outcomes.csv"
)
combine_group_files(
  "_dynamic_effects.csv",
  "run-py-7f09-dynamic-effects-all-outcomes.csv"
)
combine_group_files(
  "_uncertainty.csv",
  "run-py-7f09-uncertainty-all-outcomes.csv"
)
combine_group_files(
  "_pretrend_effects.csv",
  "run-py-7f09-pretrend-effects-all-outcomes.csv"
)
combine_group_files(
  "_pretrend_summary.csv",
  "run-py-7f09-pretrend-summary-all-outcomes.csv"
)

cat("Combined result tables: PASS\n")
RS

for combined_file in "${combined_outputs[@]}"; do
    if [[ ! -s "${combined_file}" ]]; then
        echo "ERROR: Missing or empty combined output: ${combined_file}" >&2
        exit 3
    fi
done

CURRENT_RUN="all outcome groups and combined tables completed"
echo
echo "run-py-7f09 PASS: three matched-sample Borusyak analyses completed."
echo "Static ATT rows:       3"
echo "Dynamic-effect rows:   36"
echo "Reference period:      -1 (omitted; normalized to zero)"
echo "Uncertainty rows:      39"
echo "Pre-trend-effect rows: 15"
echo "Pre-trend summaries:   3"
