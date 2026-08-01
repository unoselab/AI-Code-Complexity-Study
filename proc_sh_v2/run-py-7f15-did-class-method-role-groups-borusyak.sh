#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# run-py-7f15-did-class-method-role-groups-borusyak-v2.sh
# -----------------------------------------------------------------------------
# Apply the locked Borusyak imputation DiD specification to the four
# zero-inclusive run-py-7f14 synchronous class-method outcomes:
#
#   Category 4: all_class_methods
#   Category 5: testing_class_methods
#   Category 6: boilerplate_class_methods (exploratory and sparse)
#   Category 7: other_class_methods
#
# The wrapper is standalone. It reuses the shared Borusyak R helper but does not
# call an earlier shell wrapper.
#
# Locked model contract:
#   - Model outcome: log1p_npr_agc_class_method_unique_bodies
#   - Raw-count partition: Category 4 = Category 5 + Category 6 + Category 7
#   - Zero-count months: retained
#   - NCLOC: ncloc_python_snapshot on its raw scale
#   - Other covariates: log1p_age, log1p_contributors, log1p_stars,
#     log1p_issues
#   - Fixed effects: repository and sequential calendar month
#   - Treatment cohorts: 2024-08 through 2025-03
#   - Dynamic horizon: -6 through +6
#   - Reference period: -1, omitted and normalized to zero
#   - Estimated dynamic periods: -6 through -2 and 0 through +6
#   - Pre-trend leads: -6 through -2
#   - Uncertainty: didimputation analytic standard errors and 95% confidence
#     intervals, clustered at repository through the idname default
#   - Effective sample: exclude treated repositories with no pre-treatment row
#     before assigning repository fixed-effect ids
#   - Primary pre-trend diagnostic: covariance-aware repository-clustered joint
#     Wald test of the five lead coefficients
#   - Secondary pre-trend diagnostic: marginal lead tests with Bonferroni
#   - PDF device: cairo_pdf with wrapped titles and embedded fonts
#
# Error isolation:
#   - Every category is attempted even if an earlier category fails.
#   - Categories 4, 5, and 7 must finish with status PASS.
#   - Category 6 may finish with EXPLORATORY_PASS or EXPLORATORY_INCOMPLETE.
#   - A Category 6 estimator failure is recorded but does not fail the wrapper.
#   - A render/schema/output failure in any category fails the wrapper after all
#     categories have been attempted.
#
# Inputs:
#   repo_python/run-py-7f14/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f14-did-input-all-class-methods.csv
#       run-py-7f14-did-input-testing-class-methods.csv
#       run-py-7f14-did-input-boilerplate-class-methods.csv
#       run-py-7f14-did-input-other-class-methods.csv
#
# Outputs:
#   repo_python/run-py-7f15/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/<outcome-group>/
#
# Version 2 replaces the prior run-py-7f15 result, so use overwrite mode after
# removing -v2 from the development filenames:
#   OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7f15-did-class-method-role-groups-borusyak.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_class_method_role_groups.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"

INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-7f14/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7f15/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f15}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f15-did-class-method-role-groups-${SPECIFICATION_NAME}-${RUN_TS}.log}"

OUTCOME_GROUPS=(
    all_class_methods
    testing_class_methods
    boilerplate_class_methods
    other_class_methods
)
OUTCOME_CATEGORIES=(4 5 6 7)
INPUT_FILES=(
    run-py-7f14-did-input-all-class-methods.csv
    run-py-7f14-did-input-testing-class-methods.csv
    run-py-7f14-did-input-boilerplate-class-methods.csv
    run-py-7f14-did-input-other-class-methods.csv
)
EXPECTED_TOTALS=(3925 1201 28 2696)
EXPECTED_POSITIVE=(497 162 11 455)
EXPECTED_ZERO=(1024 1359 1510 1066)

case "${NCLOC_SPEC}" in
    python_snapshot) ;;
    *)
        echo "ERROR: run-py-7f15 requires NCLOC_SPEC=python_snapshot." >&2
        exit 2
        ;;
esac
case "${TIME_MODE}" in
    calendar_month) ;;
    *)
        echo "ERROR: run-py-7f15 requires TIME_MODE=calendar_month." >&2
        exit 2
        ;;
esac
case "${PARSE_EXCLUSION_MODE}" in
    parse_clean) ;;
    *)
        echo "ERROR: run-py-7f15 requires PARSE_EXCLUSION_MODE=parse_clean." >&2
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
ACCEPTED_RUNS=0
MAIN_FAILURES=0
EXPLORATORY_INCOMPLETE=0
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
    echo "run-py-7f15 execution summary"
    echo "Started:                       ${START_TIME}"
    echo "Completed:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:                       %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Planned category runs:          ${PLANNED_RUNS}"
    echo "Completed renders:              ${COMPLETED_RUNS}"
    echo "Accepted category runs:         ${ACCEPTED_RUNS}"
    echo "Required/render failures:       ${MAIN_FAILURES}"
    echo "Exploratory incomplete models:  ${EXPLORATORY_INCOMPLETE}"
    echo "Last/current run:               ${CURRENT_RUN}"
    echo "Exit code:                      ${exit_code}"
    echo "Output root:                    ${OUTPUT_ROOT}"
    echo "Log file:                       ${LOG_FILE}"
    echo "================================================================================"
    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

RMD_SHA="$(sha256sum "${RMD_FILE}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7f15: Borusyak DiD for class-method role groups"
echo "Analysis revision:                v2-effective-sample-joint-pretrend"
echo "Started:                         ${START_TIME}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Panel variant:                   strict"
echo "Specification:                   ${SPECIFICATION_NAME}"
echo "Snapshot metric:                 ${NCLOC_SPEC}_ncloc"
echo "Time aggregation:                ${TIME_MODE}"
echo "Parser scope:                    ${PARSE_EXCLUSION_MODE}"
echo "Rscript:                         $(command -v "${RSCRIPT_BIN}")"
echo "R version:                       $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
echo "R Markdown:                      ${RMD_FILE}"
echo "R Markdown SHA:                  ${RMD_SHA}"
echo "Helper:                          ${HELPER_FILE}"
echo "Helper SHA:                      ${HELPER_SHA}"
echo "Input root:                      ${INPUT_ROOT}"
echo "Output root:                     ${OUTPUT_ROOT}"
echo "Outcome groups:                  ${OUTCOME_GROUPS[*]}"
echo "Model outcome:                   log1p_npr_agc_class_method_unique_bodies"
echo "Raw-count identity:              Cat 4 = Cat 5 + Cat 6 + Cat 7"
echo "Zero-count months:               retained"
echo "Covariates:                      log1p_age + ncloc_python_snapshot + log1p_contributors + log1p_stars + log1p_issues"
echo "Fixed effects:                   repo_id + time_id"
echo "Treatment cohorts:               2024-08 through 2025-03"
echo "Effective-sample rule:           exclude treated repos with no pre-treatment row"
echo "Expected exclusions:             38 treated repositories / 96 rows"
echo "Expected effective sample:       1,425 rows / 180 repositories"
echo "Expected static ATT support:     297 rows / 61 treated repositories"
echo "Dynamic horizon:                 -6 through +6"
echo "Reference period:                -1 (omitted; normalized to zero)"
echo "Estimated dynamic periods:       -6:-2 and 0:+6 (12)"
echo "Pre-trend leads:                 -6 through -2"
echo "Primary pre-trend test:          repository-clustered joint Wald"
echo "Secondary pre-trend test:        marginal leads with Bonferroni"
echo "PDF device:                      cairo_pdf"
echo "Required categories:             4, 5, 7"
echo "Exploratory sparse category:     6 (28 bodies; 11 positive months)"
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
  "rmarkdown", "data.table", "dplyr", "ggplot2", "didimputation", "fixest"
)
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_packages) > 0) {
  stop("Missing required R packages: ", paste(missing_packages, collapse = ", "))
}
if (!capabilities("cairo")) {
  stop("R must provide Cairo PDF support for embedded-font figures.")
}

input_root <- Sys.getenv("INPUT_ROOT_ABS")
groups <- c(
  "all_class_methods", "testing_class_methods",
  "boilerplate_class_methods", "other_class_methods"
)
categories <- c(4L, 5L, 6L, 7L)
files <- c(
  "run-py-7f14-did-input-all-class-methods.csv",
  "run-py-7f14-did-input-testing-class-methods.csv",
  "run-py-7f14-did-input-boilerplate-class-methods.csv",
  "run-py-7f14-did-input-other-class-methods.csv"
)
expected_totals <- c(3925L, 1201L, 28L, 2696L)
expected_positive <- c(497L, 162L, 11L, 455L)
expected_zero <- c(1024L, 1359L, 1510L, 1066L)
count_col <- "npr_agc_class_method_unique_bodies"
log_col <- "log1p_npr_agc_class_method_unique_bodies"
covariates <- c(
  "log1p_age", "ncloc_python_snapshot", "log1p_contributors",
  "log1p_stars", "log1p_issues"
)

panels <- lapply(file.path(input_root, files), fread)
reference_keys <- panels[[1]][, .(dataset_source, repo_name, time)]

for (i in seq_along(panels)) {
  panel <- panels[[i]]
  if (nrow(panel) != 1521L) stop("Unexpected row count for ", groups[i])
  if (uniqueN(panel$repo_name) != 218L) {
    stop("Unexpected repository count for ", groups[i])
  }
  if (!identical(reference_keys, panel[, .(dataset_source, repo_name, time)])) {
    stop("Repository-month keys or order differ for ", groups[i])
  }
  if (!all(panel$class_method_outcome_group == groups[i])) {
    stop("Outcome-group label mismatch for ", groups[i])
  }
  if (!all(panel$class_method_outcome_category == categories[i])) {
    stop("Outcome-category mismatch for ", groups[i])
  }
  if (sum(panel[[count_col]]) != expected_totals[i]) {
    stop("Raw-count total mismatch for ", groups[i])
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
  if (any(abs(panel[[log_col]] - log1p(panel[[count_col]])) > 1e-12)) {
    stop("log1p outcome mismatch for ", groups[i])
  }
  if (!all(panel$class_method_outcome_schema_version == "run-py-7f14-v2")) {
    stop("Schema-version mismatch for ", groups[i])
  }
  if (!all(panel$class_method_taxonomy_status == "FROZEN_PARTITION")) {
    stop("Taxonomy status mismatch for ", groups[i])
  }
}

if (!all(
  panels[[2]][[count_col]] + panels[[3]][[count_col]] +
    panels[[4]][[count_col]] == panels[[1]][[count_col]]
)) {
  stop("Category 5 + Category 6 + Category 7 does not equal Category 4.")
}

normalize_yyyymm <- function(x) {
  x <- as.character(x)
  x[x %in% c("", "NA", "NaN", "NULL", "None")] <- NA_character_
  suppressWarnings(as.integer(gsub("-", "", x)))
}
yyyymm_to_month_id <- function(x) {
  x <- as.integer(x)
  year <- x %/% 100L
  month <- x %% 100L
  year * 12L + month
}

support_panel <- copy(panels[[1]])
support_panel[, time_yyyymm := normalize_yyyymm(time)]
support_panel[, event_yyyymm := normalize_yyyymm(event)]
support_panel[is.na(event_yyyymm), event_yyyymm := 0L]
support_panel[, time_id := yyyymm_to_month_id(time_yyyymm)]
support_panel[, event_id := fifelse(
  event_yyyymm == 0L,
  0L,
  yyyymm_to_month_id(event_yyyymm)
)]

treated_support <- support_panel[event_id > 0L, .(
  pre_rows = sum(time_id < event_id)
), by = repo_name]
excluded_repositories <- treated_support[pre_rows == 0L, repo_name]
excluded_rows <- support_panel[repo_name %chin% excluded_repositories, .N]
effective_panel <- support_panel[!(repo_name %chin% excluded_repositories)]
treated_post <- effective_panel[event_id > 0L & time_id >= event_id]

if (length(excluded_repositories) != 38L || excluded_rows != 96L) {
  stop("Effective-sample exclusion must equal 38 treated repositories / 96 rows.")
}
if (nrow(effective_panel) != 1425L || uniqueN(effective_panel$repo_name) != 180L) {
  stop("Effective model sample must equal 1,425 rows / 180 repositories.")
}
if (nrow(treated_post) != 297L || uniqueN(treated_post$repo_name) != 61L) {
  stop("Static ATT support must equal 297 rows / 61 treated repositories.")
}

cat("run-py-7f15 self-test PASS\n")
cat("Rows per outcome: 1,521\n")
cat("Repositories per outcome: 218\n")
cat("Raw totals (4/5/6/7): 3,925/1,201/28/2,696\n")
cat("Positive rows (4/5/6/7): 497/162/11/455\n")
cat("log1p arithmetic mismatches: 0\n")
cat("Row-level partition mismatches: 0\n")
cat("Excluded no-pre treated repositories/rows: 38/96\n")
cat("Effective model rows/repositories: 1,425/180\n")
cat("Static ATT treated post rows/repositories: 297/61\n")
cat("Cairo PDF support: PASS\n")
RS
fi

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
    CURRENT_RUN="self-test only completed"
    echo "run-py-7f15 self-test-only mode complete."
    exit 0
fi

mkdir -p "${OUTPUT_ROOT}"
RUN_STATUS_FILE="${OUTPUT_ROOT}/run-py-7f15-outcome-run-status.csv"
if [[ -e "${RUN_STATUS_FILE}" && "${OVERWRITE_OUTPUT}" == "0" ]]; then
    echo "ERROR: Output exists and OVERWRITE_OUTPUT=0: ${RUN_STATUS_FILE}" >&2
    exit 2
fi
printf '%s\n' \
    'outcome_category,outcome_group,required,exploratory,render_exit_code,model_status,accepted,status_note' \
    > "${RUN_STATUS_FILE}"

for index in "${!OUTCOME_GROUPS[@]}"; do
    outcome_group="${OUTCOME_GROUPS[${index}]}"
    outcome_category="${OUTCOME_CATEGORIES[${index}]}"
    input_file="${INPUT_FILES[${index}]}"
    expected_total="${EXPECTED_TOTALS[${index}]}"
    expected_positive="${EXPECTED_POSITIVE[${index}]}"
    expected_zero="${EXPECTED_ZERO[${index}]}"
    panel_path="${INPUT_ROOT}/${input_file}"
    out_dir="${OUTPUT_ROOT}/${outcome_group}"
    prefix="borusyak_class_method_role_group_${outcome_group}"
    html_output="DiffInDiffBorusyak_class_method_role_group_${outcome_group}_${SPECIFICATION_NAME}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"
    pdf_output="dynamic_effects_borusyak_class_method_role_group_${outcome_group}.pdf"

    required_flag=1
    exploratory_flag=0
    allow_model_failure=0
    if [[ "${outcome_category}" == "6" ]]; then
        required_flag=0
        exploratory_flag=1
        allow_model_failure=1
    fi

    mkdir -p "${out_dir}"
    expected_outputs=(
        "${out_dir}/${html_output}"
        "${out_dir}/${prefix}_static_effects.csv"
        "${out_dir}/${prefix}_dynamic_effects.csv"
        "${out_dir}/${prefix}_uncertainty.csv"
        "${out_dir}/${prefix}_pretrend_effects.csv"
        "${out_dir}/${prefix}_pretrend_summary.csv"
        "${out_dir}/${prefix}_pretrend_joint_wald.csv"
        "${out_dir}/${prefix}_pretrend_joint_errors.csv"
        "${out_dir}/${prefix}_panel_checks.csv"
        "${out_dir}/${prefix}_input_summary.csv"
        "${out_dir}/${prefix}_effective_sample_summary.csv"
        "${out_dir}/${prefix}_excluded_treated_repositories.csv"
        "${out_dir}/${prefix}_event_time_support.csv"
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

    CURRENT_RUN="category=${outcome_category} outcome_group=${outcome_group}"
    run_number=$((index + 1))
    render_start_epoch="$(date +%s)"

    echo
    echo "--------------------------------------------------------------------------------"
    printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
    echo "Input panel:       ${panel_path}"
    echo "Input SHA:         $(sha256sum "${panel_path}" | awk '{print $1}')"
    echo "Expected total:    ${expected_total}"
    echo "Expected positive: ${expected_positive}"
    echo "Expected zero:     ${expected_zero}"
    echo "Required:          ${required_flag}"
    echo "Exploratory:       ${exploratory_flag}"
    echo "Output directory:  ${out_dir}"
    echo "--------------------------------------------------------------------------------"

    set +e
    PROJECT_ROOT="${PROJECT_ROOT}" \
    PANEL_PATH="${PROJECT_ROOT}/${panel_path}" \
    OUT_DIR="${PROJECT_ROOT}/${out_dir}" \
    PANEL_LABEL="strict_${SPECIFICATION_NAME}_${outcome_group}_${NCLOC_SPEC}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}" \
    OUTCOME_GROUP="${outcome_group}" \
    SPECIFICATION_NAME="${SPECIFICATION_NAME}" \
    NCLOC_SPEC="${NCLOC_SPEC}" \
    TIME_MODE="${TIME_MODE}" \
    PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE}" \
    ALLOW_MODEL_FAILURE="${allow_model_failure}" \
    HELPER_FILE="${PROJECT_ROOT}/${HELPER_FILE}" \
    RMD_SCRIPT_LABEL="${RMD_FILE}" \
    OUTPUT_HTML="${html_output}" \
        "${RSCRIPT_BIN}" -e "rmarkdown::render(
          input = '${PROJECT_ROOT}/${RMD_FILE}',
          output_file = Sys.getenv('OUTPUT_HTML'),
          output_dir = Sys.getenv('OUT_DIR'),
          knit_root_dir = Sys.getenv('PROJECT_ROOT'),
          envir = new.env(parent = globalenv()),
          quiet = FALSE
        )"
    render_exit_code=$?
    set -e
    COMPLETED_RUNS=$((COMPLETED_RUNS + 1))

    if [[ "${render_exit_code}" != "0" ]]; then
        echo "ERROR: R Markdown render failed for ${outcome_group}." >&2
        printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "${outcome_category}" "${outcome_group}" "${required_flag}" \
            "${exploratory_flag}" "${render_exit_code}" "RENDER_FAILED" \
            "0" "render_or_schema_failure" >> "${RUN_STATUS_FILE}"
        MAIN_FAILURES=$((MAIN_FAILURES + 1))
        continue
    fi

    missing_output_count=0
    for expected_file in "${expected_outputs[@]}"; do
        if [[ ! -s "${expected_file}" ]]; then
            echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
            missing_output_count=$((missing_output_count + 1))
        fi
    done
    if ((missing_output_count > 0)); then
        printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "${outcome_category}" "${outcome_group}" "${required_flag}" \
            "${exploratory_flag}" "${render_exit_code}" "OUTPUT_INCOMPLETE" \
            "0" "missing_expected_output" >> "${RUN_STATUS_FILE}"
        MAIN_FAILURES=$((MAIN_FAILURES + 1))
        continue
    fi

    validation_file="${out_dir}/${prefix}_final_model_validation.csv"
    model_status="$(awk -F, '$1 == "status" {gsub(/\r|\"/, "", $2); print $2}' "${validation_file}")"
    accepted=0
    status_note="unexpected_model_status"

    if [[ "${required_flag}" == "1" ]]; then
        if [[ "${model_status}" == "PASS" ]]; then
            accepted=1
            status_note="required_model_complete"
        else
            MAIN_FAILURES=$((MAIN_FAILURES + 1))
        fi
    else
        case "${model_status}" in
            EXPLORATORY_PASS)
                accepted=1
                status_note="exploratory_model_complete"
                ;;
            EXPLORATORY_INCOMPLETE)
                accepted=1
                status_note="accepted_sparse_exploratory_model_incomplete"
                EXPLORATORY_INCOMPLETE=$((EXPLORATORY_INCOMPLETE + 1))
                ;;
            *)
                MAIN_FAILURES=$((MAIN_FAILURES + 1))
                ;;
        esac
    fi

    printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "${outcome_category}" "${outcome_group}" "${required_flag}" \
        "${exploratory_flag}" "${render_exit_code}" "${model_status:-MISSING}" \
        "${accepted}" "${status_note}" >> "${RUN_STATUS_FILE}"

    if [[ "${accepted}" == "1" ]]; then
        ACCEPTED_RUNS=$((ACCEPTED_RUNS + 1))
    fi
    render_elapsed=$(($(date +%s) - render_start_epoch))
    printf '[%02d/%02d] status=%s accepted=%s elapsed=%ds\n' \
        "${run_number}" "${PLANNED_RUNS}" "${model_status:-MISSING}" \
        "${accepted}" "${render_elapsed}"
done

combined_outputs=(
    "${OUTPUT_ROOT}/run-py-7f15-static-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-dynamic-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-uncertainty-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-pretrend-effects-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-pretrend-summary-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-pretrend-joint-wald-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-effective-sample-summary-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-event-time-support-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-excluded-treated-repositories.csv"
    "${OUTPUT_ROOT}/run-py-7f15-final-model-validation-all-outcomes.csv"
    "${OUTPUT_ROOT}/run-py-7f15-analysis-summary.csv"
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
RUN_STATUS_PATH="${PROJECT_ROOT}/${RUN_STATUS_FILE}" \
"${RSCRIPT_BIN}" - <<'RS'
suppressPackageStartupMessages(library(data.table))

root <- Sys.getenv("COMBINED_ROOT")
status_path <- Sys.getenv("RUN_STATUS_PATH")
groups <- c(
  "all_class_methods", "testing_class_methods",
  "boilerplate_class_methods", "other_class_methods"
)
prefixes <- paste0("borusyak_class_method_role_group_", groups)

combine_group_files <- function(suffix, output_name) {
  paths <- file.path(root, groups, paste0(prefixes, suffix))
  available <- paths[file.exists(paths) & file.info(paths)$size > 0]
  if (length(available) == 0) {
    stop("No available group outputs for suffix: ", suffix)
  }
  tables <- lapply(available, function(path) {
    tryCatch(fread(path), error = function(e) NULL)
  })
  tables <- tables[!vapply(tables, is.null, logical(1))]
  if (length(tables) == 0) stop("No readable outputs for suffix: ", suffix)
  combined <- rbindlist(tables, fill = TRUE, use.names = TRUE)
  fwrite(combined, file.path(root, output_name))
  combined
}

static <- combine_group_files(
  "_static_effects.csv", "run-py-7f15-static-effects-all-outcomes.csv"
)
dynamic <- combine_group_files(
  "_dynamic_effects.csv", "run-py-7f15-dynamic-effects-all-outcomes.csv"
)
uncertainty <- combine_group_files(
  "_uncertainty.csv", "run-py-7f15-uncertainty-all-outcomes.csv"
)
pretrend <- combine_group_files(
  "_pretrend_effects.csv", "run-py-7f15-pretrend-effects-all-outcomes.csv"
)
pretrend_summary <- combine_group_files(
  "_pretrend_summary.csv", "run-py-7f15-pretrend-summary-all-outcomes.csv"
)
pretrend_joint_wald <- combine_group_files(
  "_pretrend_joint_wald.csv",
  "run-py-7f15-pretrend-joint-wald-all-outcomes.csv"
)
effective_sample <- combine_group_files(
  "_effective_sample_summary.csv",
  "run-py-7f15-effective-sample-summary-all-outcomes.csv"
)
event_time_support <- combine_group_files(
  "_event_time_support.csv",
  "run-py-7f15-event-time-support-all-outcomes.csv"
)

excluded_path <- file.path(
  root,
  "all_class_methods",
  paste0(prefixes[1], "_excluded_treated_repositories.csv")
)
if (!file.exists(excluded_path)) {
  stop("Missing canonical excluded-treated-repository list.")
}
excluded_repositories <- fread(excluded_path)
excluded_repositories[, c("outcome_category", "outcome_group") := NULL]
if (nrow(excluded_repositories) != 38L ||
    uniqueN(excluded_repositories$repo_name) != 38L) {
  stop("Canonical excluded-treated-repository list must contain 38 repositories.")
}
fwrite(
  excluded_repositories,
  file.path(root, "run-py-7f15-excluded-treated-repositories.csv")
)

validation_paths <- file.path(
  root, groups, paste0(prefixes, "_final_model_validation.csv")
)
validation_rows <- list()
for (i in seq_along(validation_paths)) {
  if (!file.exists(validation_paths[i])) next
  x <- fread(validation_paths[i])
  x[, outcome_group := groups[i]]
  validation_rows[[length(validation_rows) + 1L]] <- x
}
if (length(validation_rows) == 0) stop("No final validation outputs found.")
validation <- rbindlist(validation_rows, fill = TRUE)
fwrite(
  validation,
  file.path(root, "run-py-7f15-final-model-validation-all-outcomes.csv")
)

run_status <- fread(status_path)
static_summary <- static[, .(
  estimate = estimate[1],
  std_error = std_error[1],
  conf_low = conf_low[1],
  conf_high = conf_high[1],
  p_value = p_value[1],
  estimate_percent_yplus1 = estimate_percent_yplus1[1]
), by = .(outcome_category, outcome_group, outcome_label, exploratory)]
joint_summary <- pretrend_joint_wald[, .(
  joint_wald_statistic = wald_statistic[1],
  joint_pretrend_p_value = p_value[1],
  joint_wald_df1 = df1[1],
  joint_wald_df2 = df2[1],
  joint_pretrend_test_complete = joint_test_complete[1],
  joint_pretrend_conclusion = conclusion[1]
), by = .(outcome_category, outcome_group)]
static_support_summary <- effective_sample[
  stage == "static_att_treated_post_observations",
  .(
    static_att_rows = rows[1],
    static_att_treated_repositories = treated_repositories[1],
    static_att_raw_count_total = raw_count_total[1],
    static_att_positive_outcome_rows = positive_outcome_rows[1]
  ),
  by = .(outcome_category, outcome_group)
]
analysis_summary <- merge(
  run_status,
  static_summary,
  by = c("outcome_category", "outcome_group"),
  all.x = TRUE,
  sort = FALSE
)
analysis_summary <- merge(
  analysis_summary,
  joint_summary,
  by = c("outcome_category", "outcome_group"),
  all.x = TRUE,
  sort = FALSE
)
analysis_summary <- merge(
  analysis_summary,
  static_support_summary,
  by = c("outcome_category", "outcome_group"),
  all.x = TRUE,
  sort = FALSE
)
setorder(analysis_summary, outcome_category)
fwrite(analysis_summary, file.path(root, "run-py-7f15-analysis-summary.csv"))

cat("Combined result tables: PASS\n")
cat("Static rows:", nrow(static), "\n")
cat("Dynamic rows:", nrow(dynamic), "\n")
cat("Uncertainty rows:", nrow(uncertainty), "\n")
cat("Pre-trend rows:", nrow(pretrend), "\n")
cat("Pre-trend summaries:", nrow(pretrend_summary), "\n")
cat("Joint Wald rows:", nrow(pretrend_joint_wald), "\n")
cat("Effective-sample summary rows:", nrow(effective_sample), "\n")
cat("Event-time support rows:", nrow(event_time_support), "\n")
cat("Excluded treated repositories:", nrow(excluded_repositories), "\n")
RS

for combined_file in "${combined_outputs[@]}"; do
    if [[ ! -s "${combined_file}" ]]; then
        echo "ERROR: Missing or empty combined output: ${combined_file}" >&2
        MAIN_FAILURES=$((MAIN_FAILURES + 1))
    fi
done

CURRENT_RUN="all category attempts and combined tables completed"
echo
echo "run-py-7f15 category execution status:"
column -s, -t "${RUN_STATUS_FILE}" 2>/dev/null || cat "${RUN_STATUS_FILE}"

if ((MAIN_FAILURES > 0)); then
    echo "ERROR: run-py-7f15 completed all category attempts but found ${MAIN_FAILURES} required/render/output failure(s)." >&2
    exit 5
fi

echo
echo "run-py-7f15 completed successfully."
echo "Accepted category runs:         ${ACCEPTED_RUNS}/${PLANNED_RUNS}"
echo "Exploratory incomplete models:  ${EXPLORATORY_INCOMPLETE}"
echo "Effective model sample:         1,425 rows / 180 repositories"
echo "Static ATT support:             297 rows / 61 treated repositories"
echo "Category 6 interpretation:      exploratory; static support has 10 bodies in 4 positive months"
echo "Reference period:               -1 (omitted; normalized to zero)"
echo "Model outcome:                  log1p class-method unique-body count"
echo "Primary pre-trend diagnostic:   repository-clustered joint Wald test"
