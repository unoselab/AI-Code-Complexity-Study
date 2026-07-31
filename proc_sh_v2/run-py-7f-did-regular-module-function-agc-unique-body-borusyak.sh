#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-7f-did-regular-module-function-agc-unique-body-borusyak.sh
# -----------------------------------------------------------------------------
# Estimate static and dynamic Borusyak DiD effects for the focused outcome:
#
#   Number of distinct AGC-like regular module-function bodies per
#   repository-month.
#
# This standalone wrapper follows the execution and validation structure of
# the existing run-py-7c wrapper, but it does not call or depend on that shell
# script.
#
# Scientific scope:
#   - Regular functions only: function_kind == "module_function"
#   - AGC-like classifications only
#   - Raw count outcome
#   - Distinct body SHA count within each repository-month
#   - Zero-count repository-months retained
#   - No HWC outcome
#   - No AGC/HWC ratio outcome
#
# Input:
#   repo_python/run-py-7e/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv
#
# Default output:
#   repo_python/run-py-7f/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#
# Default execution:
#   OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7f-did-regular-module-function-agc-unique-body-borusyak.sh
#
# Optional paper-compatible NCLOC robustness run:
#   NCLOC_SPECS="paper python_snapshot" OVERWRITE_OUTPUT=1 \
#   bash proc_sh/run-py-7f-did-regular-module-function-agc-unique-body-borusyak.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_regular_module_function_agc_unique_body.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-7f/strict/specifications/${SPECIFICATION_NAME}}"

NCLOC_SPECS="${NCLOC_SPECS:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f-did-regular-function-agc-unique-body-${SPECIFICATION_NAME}-${PARSE_EXCLUSION_MODE}-${RUN_TS}.log}"

case "${TIME_MODE}" in
    original_yyyymm|calendar_month) ;;
    *)
        echo "ERROR: Unsupported TIME_MODE: ${TIME_MODE}" >&2
        exit 2
        ;;
esac

case "${PARSE_EXCLUSION_MODE}" in
    all|parse_clean) ;;
    *)
        echo "ERROR: Unsupported PARSE_EXCLUSION_MODE: ${PARSE_EXCLUSION_MODE}" >&2
        exit 2
        ;;
esac

case "${OVERWRITE_OUTPUT}" in
    0|1) ;;
    *)
        echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
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

read -r -a NCLOC_ARRAY <<< "${NCLOC_SPECS}"
for ncloc_spec in "${NCLOC_ARRAY[@]}"; do
    case "${ncloc_spec}" in
        paper|python_snapshot) ;;
        *)
            echo "ERROR: Unsupported NCLOC specification: ${ncloc_spec}" >&2
            exit 2
            ;;
    esac
done

if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" ]]; then
    PANEL_PATH="${INPUT_ROOT}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv"
else
    PANEL_PATH="${INPUT_ROOT}/panel_event_monthly_regular_module_function_agc_unique_body.csv"
fi

if [[ ! -s "${PANEL_PATH}" ]]; then
    echo "ERROR: Input panel is missing or empty: ${PANEL_PATH}" >&2
    exit 2
fi

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"
PLANNED_RUNS="${#NCLOC_ARRAY[@]}"
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
    echo "run-py-7f execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Specification:       ${SPECIFICATION_NAME}"
    echo "Parse mode:          ${PARSE_EXCLUSION_MODE}"
    echo "Time mode:           ${TIME_MODE}"
    echo "Planned renders:     ${PLANNED_RUNS}"
    echo "Completed renders:   ${COMPLETED_RUNS}"
    echo "Last/current render: ${CURRENT_RUN}"
    echo "Exit code:           ${exit_code}"
    echo "Log file:            ${LOG_FILE}"
    echo "================================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

RMD_SHA="$(sha256sum "${RMD_FILE}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"
PANEL_SHA="$(sha256sum "${PANEL_PATH}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7f: Borusyak DiD for AGC-like regular-function unique bodies"
echo "Started:              ${START_TIME}"
echo "Project root:         ${PROJECT_ROOT}"
echo "Rscript:              $(command -v "${RSCRIPT_BIN}")"
echo "R version:            $("${RSCRIPT_BIN}" --version 2>&1 | head -1)"
echo "R Markdown:           ${RMD_FILE}"
echo "R Markdown SHA:       ${RMD_SHA}"
echo "Helper:               ${HELPER_FILE}"
echo "Helper SHA:           ${HELPER_SHA}"
echo "Specification:        ${SPECIFICATION_NAME}"
echo "Input panel:          ${PANEL_PATH}"
echo "Input panel SHA:      ${PANEL_SHA}"
echo "Output root:          ${OUTPUT_ROOT}"
echo "NCLOC specifications: ${NCLOC_ARRAY[*]}"
echo "Time mode:            ${TIME_MODE}"
echo "Parse mode:           ${PARSE_EXCLUSION_MODE}"
echo "Outcome:               raw distinct AGC-like regular-body count"
echo "Overwrite output:     ${OVERWRITE_OUTPUT}"
echo "Planned renders:      ${PLANNED_RUNS}"
echo "Log file:             ${LOG_FILE}"
echo "================================================================================"

for ncloc_spec in "${NCLOC_ARRAY[@]}"; do
    out_dir="${OUTPUT_ROOT}/${ncloc_spec}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}"
    panel_label="strict_${SPECIFICATION_NAME}_regular_module_function_agc_unique_body_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}"
    html_output="DiffInDiffBorusyak_regular_module_function_agc_unique_body_${SPECIFICATION_NAME}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"

    mkdir -p "${out_dir}"

    expected_outputs=(
        "${out_dir}/${html_output}"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_static_effects.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_dynamic_effects.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_panel_checks.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_input_summary.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_static_errors.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_dynamic_errors.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_final_model_validation.csv"
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_metadata.csv"
        "${out_dir}/dynamic_effects_borusyak_regular_module_function_agc_unique_body.pdf"
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

    CURRENT_RUN="ncloc=${ncloc_spec} time=${TIME_MODE} parse=${PARSE_EXCLUSION_MODE}"
    run_number=$((COMPLETED_RUNS + 1))
    render_start_epoch="$(date +%s)"

    echo
    echo "--------------------------------------------------------------------------------"
    printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
    echo "Input panel:      ${PANEL_PATH}"
    echo "Output directory: ${out_dir}"
    echo "HTML output:      ${html_output}"
    echo "--------------------------------------------------------------------------------"

    PROJECT_ROOT="${PROJECT_ROOT}" \
    PANEL_PATH="${PROJECT_ROOT}/${PANEL_PATH}" \
    OUT_DIR="${PROJECT_ROOT}/${out_dir}" \
    PANEL_LABEL="${panel_label}" \
    SPECIFICATION_NAME="${SPECIFICATION_NAME}" \
    NCLOC_SPEC="${ncloc_spec}" \
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

    forbidden_count="$(awk -F, '$1 == "forbidden_hwc_or_ratio_columns" {gsub(/\r/, "", $2); print $2}' \
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_panel_checks.csv")"
    parse_rows="$(awk -F, '$1 == "parse_exclusion_rows_in_model_sample" {gsub(/\r/, "", $2); print $2}' \
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_panel_checks.csv")"
    static_error_count="$(awk -F, '$1 == "static_model_error_count" {gsub(/\r/, "", $2); print $2}' \
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_final_model_validation.csv")"
    dynamic_error_count="$(awk -F, '$1 == "dynamic_model_error_count" {gsub(/\r/, "", $2); print $2}' \
        "${out_dir}/borusyak_regular_module_function_agc_unique_body_final_model_validation.csv")"

    if [[ "${forbidden_count}" != "0" ]]; then
        echo "ERROR: Focused model panel contains HWC or ratio columns." >&2
        exit 4
    fi
    if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" && "${parse_rows}" != "0" ]]; then
        echo "ERROR: Parse-clean run retained parse-exclusion rows: ${parse_rows:-missing}" >&2
        exit 4
    fi
    if [[ "${static_error_count}" != "0" || "${dynamic_error_count}" != "0" ]]; then
        echo "ERROR: Model validation contains estimator errors." >&2
        echo "       static=${static_error_count:-missing} dynamic=${dynamic_error_count:-missing}" >&2
        exit 4
    fi

    COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
    render_end_epoch="$(date +%s)"
    render_elapsed=$((render_end_epoch - render_start_epoch))
    printf '[%02d/%02d] PASS elapsed=%ds parse_exclusion_rows=%s static_errors=%s dynamic_errors=%s\n' \
        "${COMPLETED_RUNS}" "${PLANNED_RUNS}" "${render_elapsed}" \
        "${parse_rows:-unknown}" "${static_error_count:-unknown}" "${dynamic_error_count:-unknown}"
done

CURRENT_RUN="all requested renders completed"
echo
echo "All ${COMPLETED_RUNS} focused Borusyak renders completed successfully."
