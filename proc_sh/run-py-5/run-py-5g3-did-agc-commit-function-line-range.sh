#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-5g3-did-agc-commit-function-line-range.sh
# -----------------------------------------------------------------------------
# Run Borusyak DiD analyses for commit-function outcomes restricted to an
# inclusive source-line-span range prepared by run-py-5g2.
#
# Research question:
#   After Cursor adoption, did function-change events spanning 3-8 source
#   lines increase or decrease relative to matched control repositories?
#
# Implementation note:
#   This wrapper reuses the execution and validation logic of the existing
#   run-py-5f Borusyak wrapper, but it is self-contained and does not call the
#   older shell script.
#
# Default specification for the research question:
#   - Function source-line span: 3-8 inclusive
#   - Sample: full zero-inclusive repository-month panel
#   - NCLOC control: Python snapshot NCLOC
#   - Time encoding: sequential calendar month
#   - Parse handling: parse-clean
#
# Inputs from run-py-5g2:
#   repo_python/run-py-5g2/strict/function_lines_3_8/
#     panel_event_monthly_agc_commit_function_lines_3_8.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_parse_clean.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_ratio_positive.csv
#     panel_event_monthly_agc_commit_function_lines_3_8_ratio_positive_parse_clean.csv
#
# R analysis inputs:
#   proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd
#   proc_r/diff_in_diff_borusyak_helpers.R
#
# Main outputs:
#   repo_python/run-py-5g3/strict/function_lines_3_8/
#     <sample>/<ncloc>_ncloc/<time_mode>/<parse_mode>/
#
# Default execution produces one render:
#   full / python_snapshot / calendar_month / parse_clean
#
# Optional overrides:
#   MIN_FUNCTION_LINES=3
#   MAX_FUNCTION_LINES=8
#   SAMPLE_TYPES="full"
#   NCLOC_SPECS="python_snapshot"
#   TIME_MODE="calendar_month"
#   PARSE_EXCLUSION_MODE="parse_clean"
#   RSCRIPT_BIN="Rscript"
#
# Example: run all full-sample NCLOC specifications
#   NCLOC_SPECS="paper python_snapshot" \
#   bash proc_sh/run-py-5/run-py-5g3-did-agc-commit-function-line-range.sh
#
# Example: run the conditional ratio specification separately
#   SAMPLE_TYPES="ratio" \
#   bash proc_sh/run-py-5/run-py-5g3-did-agc-commit-function-line-range.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"

MIN_FUNCTION_LINES="${MIN_FUNCTION_LINES:-3}"
MAX_FUNCTION_LINES="${MAX_FUNCTION_LINES:-8}"
LINE_RANGE_LABEL="function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}"
ANALYSIS_DESIGN_STATUS="${ANALYSIS_DESIGN_STATUS:-post_hoc_exploratory_heterogeneity}"

INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-5g2/strict/${LINE_RANGE_LABEL}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-5g3/strict/${LINE_RANGE_LABEL}}"

# The full sample directly answers the stated research question. Ratio is an
# optional conditional composition analysis and is not run by default.
SAMPLE_TYPES="${SAMPLE_TYPES:-full}"
NCLOC_SPECS="${NCLOC_SPECS:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-5g3}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-5g3-did-agc-commit-function-line-range-${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES}-${PARSE_EXCLUSION_MODE}-${RUN_TS}.log}"

if ! [[ "${MIN_FUNCTION_LINES}" =~ ^[0-9]+$ ]] || \
   ! [[ "${MAX_FUNCTION_LINES}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: MIN_FUNCTION_LINES and MAX_FUNCTION_LINES must be integers." >&2
    exit 2
fi

if (( MIN_FUNCTION_LINES < 1 || MAX_FUNCTION_LINES < MIN_FUNCTION_LINES )); then
    echo "ERROR: Invalid inclusive function-line range: ${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES}" >&2
    exit 2
fi

case "${TIME_MODE}" in
    original_yyyymm|calendar_month)
        ;;
    *)
        echo "ERROR: Unsupported TIME_MODE: ${TIME_MODE}" >&2
        echo "       Supported values: original_yyyymm calendar_month" >&2
        exit 2
        ;;
esac

case "${PARSE_EXCLUSION_MODE}" in
    all|parse_clean)
        ;;
    *)
        echo "ERROR: Unsupported PARSE_EXCLUSION_MODE: ${PARSE_EXCLUSION_MODE}" >&2
        echo "       Supported values: all parse_clean" >&2
        exit 2
        ;;
esac

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

if [[ ! -d "${INPUT_ROOT}" ]]; then
    echo "ERROR: Input directory does not exist: ${INPUT_ROOT}" >&2
    echo "       Run run-py-5g2 first for this line range." >&2
    exit 2
fi

read -r -a SAMPLE_ARRAY <<< "${SAMPLE_TYPES}"
read -r -a NCLOC_ARRAY <<< "${NCLOC_SPECS}"

if (( ${#SAMPLE_ARRAY[@]} == 0 || ${#NCLOC_ARRAY[@]} == 0 )); then
    echo "ERROR: SAMPLE_TYPES and NCLOC_SPECS must not be empty." >&2
    exit 2
fi

for sample_type in "${SAMPLE_ARRAY[@]}"; do
    case "${sample_type}" in
        full|ratio)
            ;;
        *)
            echo "ERROR: Unsupported sample type: ${sample_type}" >&2
            echo "       Supported values: full ratio" >&2
            exit 2
            ;;
    esac
done

for ncloc_spec in "${NCLOC_ARRAY[@]}"; do
    case "${ncloc_spec}" in
        paper|python_snapshot)
            ;;
        *)
            echo "ERROR: Unsupported NCLOC specification: ${ncloc_spec}" >&2
            echo "       Supported values: paper python_snapshot" >&2
            exit 2
            ;;
    esac
done

sha256_file() {
    local file_path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${file_path}" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${file_path}" | awk '{print $1}'
    else
        echo "unavailable"
    fi
}

csv_value() {
    local csv_file="$1"
    local requested_check="$2"

    awk -F',' -v requested_check="${requested_check}" '
        NR > 1 {
            check_name = $1
            check_value = $2
            gsub(/^"|"$/, "", check_name)
            gsub(/^"|"$/, "", check_value)
            gsub(/\r/, "", check_name)
            gsub(/\r/, "", check_value)
            if (check_name == requested_check) {
                print check_value
                exit
            }
        }
    ' "${csv_file}"
}

is_zero_value() {
    case "$1" in
        0|0.0|FALSE|False|false)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

is_true_value() {
    case "$1" in
        1|1.0|TRUE|True|true)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"
PLANNED_RUNS=$(( ${#SAMPLE_ARRAY[@]} * ${#NCLOC_ARRAY[@]} ))
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
    echo "============================================================================"
    echo "run-py-5g3 execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Function line range: ${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES} inclusive"
    echo "Design status:       ${ANALYSIS_DESIGN_STATUS}"
    echo "Parse mode:          ${PARSE_EXCLUSION_MODE}"
    echo "Time mode:           ${TIME_MODE}"
    echo "Planned renders:     ${PLANNED_RUNS}"
    echo "Completed renders:   ${COMPLETED_RUNS}"
    echo "Last/current render: ${CURRENT_RUN}"
    echo "Exit code:           ${exit_code}"
    echo "Output root:         ${OUTPUT_ROOT}"
    echo "Log file:            ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

SCRIPT_SHA="$(sha256_file "${BASH_SOURCE[0]}")"
RMD_SHA="$(sha256_file "${RMD_FILE}")"
HELPER_SHA="$(sha256_file "${HELPER_FILE}")"

 echo "============================================================================"
echo "run-py-5g3: Borusyak DiD for 3-8-line commit-function outcomes"
echo "Started:             ${START_TIME}"
echo "Project root:        ${PROJECT_ROOT}"
echo "Rscript:             $(command -v "${RSCRIPT_BIN}")"
echo "R Markdown:          ${RMD_FILE}"
echo "R Markdown SHA:      ${RMD_SHA}"
echo "Helper:              ${HELPER_FILE}"
echo "Helper SHA:          ${HELPER_SHA}"
echo "Shell script SHA:    ${SCRIPT_SHA}"
echo "Function line range: ${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES} inclusive"
echo "Design status:       ${ANALYSIS_DESIGN_STATUS}"
echo "Input root:          ${INPUT_ROOT}"
echo "Output root:         ${OUTPUT_ROOT}"
echo "Sample types:        ${SAMPLE_ARRAY[*]}"
echo "NCLOC specifications: ${NCLOC_ARRAY[*]}"
echo "Time mode:           ${TIME_MODE}"
echo "Parse mode:          ${PARSE_EXCLUSION_MODE}"
echo "Planned renders:     ${PLANNED_RUNS}"
echo "Log file:            ${LOG_FILE}"
echo "============================================================================"

for sample_type in "${SAMPLE_ARRAY[@]}"; do
    if [[ "${sample_type}" == "full" ]]; then
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" ]]; then
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}_parse_clean.csv"
        else
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}.csv"
        fi
    else
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" ]]; then
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}_ratio_positive_parse_clean.csv"
        else
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}_ratio_positive.csv"
        fi
    fi

    if [[ ! -s "${panel_path}" ]]; then
        echo "ERROR: Input panel is missing or empty: ${panel_path}" >&2
        exit 2
    fi

    panel_sha="$(sha256_file "${panel_path}")"

    for ncloc_spec in "${NCLOC_ARRAY[@]}"; do
        out_dir="${OUTPUT_ROOT}/${sample_type}/${ncloc_spec}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}"
        panel_label="strict_${LINE_RANGE_LABEL}_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}"
        html_output="DiffInDiffBorusyak_agc_commit_function_lines_${MIN_FUNCTION_LINES}_${MAX_FUNCTION_LINES}_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"
        run_metadata_output="${out_dir}/borusyak_agc_commit_function_line_range_run_metadata.csv"

        mkdir -p "${out_dir}"

        # Remove only artifacts generated by this exact specification. This
        # prevents stale outputs from being accepted as a successful rerun.
        rm -f \
            "${out_dir}/${html_output}" \
            "${out_dir}/borusyak_agc_commit_function_static_effects.csv" \
            "${out_dir}/borusyak_agc_commit_function_dynamic_effects.csv" \
            "${out_dir}/borusyak_agc_commit_function_panel_checks.csv" \
            "${out_dir}/borusyak_agc_commit_function_input_summary.csv" \
            "${out_dir}/borusyak_agc_commit_function_final_model_validation.csv" \
            "${out_dir}/borusyak_agc_commit_function_static_errors.csv" \
            "${out_dir}/borusyak_agc_commit_function_dynamic_errors.csv" \
            "${out_dir}/borusyak_agc_commit_function_metadata.csv" \
            "${out_dir}/dynamic_effects_borusyak_agc_commit_function.pdf" \
            "${run_metadata_output}"

        CURRENT_RUN="sample=${sample_type} ncloc=${ncloc_spec} time=${TIME_MODE} parse=${PARSE_EXCLUSION_MODE} lines=${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES}"
        run_number=$((COMPLETED_RUNS + 1))
        render_start_epoch="$(date +%s)"

        echo
        echo "----------------------------------------------------------------------------"
        printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
        echo "Input panel:      ${panel_path}"
        echo "Input panel SHA:  ${panel_sha}"
        echo "Panel label:      ${panel_label}"
        echo "Output directory: ${out_dir}"
        echo "HTML output:      ${html_output}"
        echo "----------------------------------------------------------------------------"

        PROJECT_ROOT="${PROJECT_ROOT}" \
        PANEL_PATH="${PROJECT_ROOT}/${panel_path}" \
        OUT_DIR="${PROJECT_ROOT}/${out_dir}" \
        PANEL_LABEL="${panel_label}" \
        NCLOC_SPEC="${ncloc_spec}" \
        SAMPLE_TYPE="${sample_type}" \
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

        expected_outputs=(
            "${out_dir}/${html_output}"
            "${out_dir}/borusyak_agc_commit_function_static_effects.csv"
            "${out_dir}/borusyak_agc_commit_function_dynamic_effects.csv"
            "${out_dir}/borusyak_agc_commit_function_panel_checks.csv"
            "${out_dir}/borusyak_agc_commit_function_input_summary.csv"
            "${out_dir}/borusyak_agc_commit_function_final_model_validation.csv"
            "${out_dir}/borusyak_agc_commit_function_static_errors.csv"
            "${out_dir}/borusyak_agc_commit_function_dynamic_errors.csv"
            "${out_dir}/borusyak_agc_commit_function_metadata.csv"
            "${out_dir}/dynamic_effects_borusyak_agc_commit_function.pdf"
        )

        for expected_file in "${expected_outputs[@]}"; do
            if [[ ! -s "${expected_file}" ]]; then
                echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
                exit 3
            fi
        done

        panel_checks_file="${out_dir}/borusyak_agc_commit_function_panel_checks.csv"
        model_validation_file="${out_dir}/borusyak_agc_commit_function_final_model_validation.csv"

        parse_rows="$(csv_value "${panel_checks_file}" "parse_exclusion_rows_in_model_sample")"
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" && "${parse_rows}" != "0" ]]; then
            echo "ERROR: Parse-clean run retained parse-exclusion rows: ${parse_rows:-missing}" >&2
            exit 4
        fi

        static_error_count="$(csv_value "${model_validation_file}" "static_model_error_count")"
        dynamic_error_count="$(csv_value "${model_validation_file}" "dynamic_model_error_count")"
        static_complete="$(csv_value "${model_validation_file}" "static_effects_complete")"
        dynamic_nonempty="$(csv_value "${model_validation_file}" "dynamic_effects_nonempty")"
        dynamic_pre_present="$(csv_value "${model_validation_file}" "dynamic_pre_period_present")"
        dynamic_post_present="$(csv_value "${model_validation_file}" "dynamic_post_period_present")"

        if ! is_zero_value "${static_error_count}"; then
            echo "ERROR: Static model validation failed: ${static_error_count:-missing}" >&2
            exit 5
        fi
        if ! is_zero_value "${dynamic_error_count}"; then
            echo "ERROR: Dynamic model validation failed: ${dynamic_error_count:-missing}" >&2
            exit 5
        fi
        if ! is_true_value "${static_complete}" || \
           ! is_true_value "${dynamic_nonempty}" || \
           ! is_true_value "${dynamic_pre_present}" || \
           ! is_true_value "${dynamic_post_present}"; then
            echo "ERROR: Final model completeness validation failed." >&2
            echo "       static_complete=${static_complete:-missing}" >&2
            echo "       dynamic_nonempty=${dynamic_nonempty:-missing}" >&2
            echo "       dynamic_pre_present=${dynamic_pre_present:-missing}" >&2
            echo "       dynamic_post_present=${dynamic_post_present:-missing}" >&2
            exit 5
        fi

        # Record the line-range specification separately because the reused Rmd
        # was originally written for the all-function run-py-5e panel.
        {
            echo "key,value"
            echo "function_line_range,${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES}"
            echo "minimum_function_lines_inclusive,${MIN_FUNCTION_LINES}"
            echo "maximum_function_lines_inclusive,${MAX_FUNCTION_LINES}"
            echo "analysis_design_status,${ANALYSIS_DESIGN_STATUS}"
            echo "research_question,Cursor adoption effect on function-change events spanning ${MIN_FUNCTION_LINES}-${MAX_FUNCTION_LINES} source lines"
            echo "sample_type,${sample_type}"
            echo "ncloc_specification,${ncloc_spec}"
            echo "time_mode,${TIME_MODE}"
            echo "parse_exclusion_mode,${PARSE_EXCLUSION_MODE}"
            echo "panel_label,${panel_label}"
            echo "panel_path,${panel_path}"
            echo "panel_sha256,${panel_sha}"
            echo "rmd_file,${RMD_FILE}"
            echo "rmd_sha256,${RMD_SHA}"
            echo "helper_file,${HELPER_FILE}"
            echo "helper_sha256,${HELPER_SHA}"
            echo "shell_script_sha256,${SCRIPT_SHA}"
        } > "${run_metadata_output}"

        if [[ ! -s "${run_metadata_output}" ]]; then
            echo "ERROR: Failed to create line-range run metadata: ${run_metadata_output}" >&2
            exit 6
        fi

        COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
        render_end_epoch="$(date +%s)"
        render_elapsed=$((render_end_epoch - render_start_epoch))

        printf '[%02d/%02d] PASS elapsed=%ds parse_exclusion_rows=%s static_errors=%s dynamic_errors=%s\n' \
            "${COMPLETED_RUNS}" \
            "${PLANNED_RUNS}" \
            "${render_elapsed}" \
            "${parse_rows:-unknown}" \
            "${static_error_count:-unknown}" \
            "${dynamic_error_count:-unknown}"
    done
done

CURRENT_RUN="all requested renders completed"
echo
echo "All ${COMPLETED_RUNS} Borusyak line-range renders completed successfully."
