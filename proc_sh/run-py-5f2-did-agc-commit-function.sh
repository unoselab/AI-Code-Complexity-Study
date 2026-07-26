#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-5f2-did-agc-commit-function.sh
# -----------------------------------------------------------------------------
# Run Borusyak DiD analyses for commit-function AGC outcomes.
#
# Default behavior:
#   - Uses the parse-clean panels prepared by run-py-5e.
#   - Runs both sample types: full and ratio.
#   - Runs both NCLOC specifications: paper and python_snapshot.
#   - Uses sequential calendar-month encoding.
#
# Inputs:
#   repo_python/run-py-5e/strict/
#     panel_event_monthly_agc_commit_function_parse_clean.csv
#     panel_event_monthly_agc_commit_function_ratio_positive_parse_clean.csv
#
# Main outputs:
#   repo_python/run-py-5f/strict/<sample>/<ncloc>_ncloc/
#     <time_mode>/<parse_mode>/
#
# Optional overrides:
#   SAMPLE_TYPES="full ratio"
#   NCLOC_SPECS="paper python_snapshot"
#   TIME_MODE="calendar_month"
#   PARSE_EXCLUSION_MODE="parse_clean"
#   RSCRIPT_BIN="Rscript"
#
# Usage: 
#   bash proc_sh/run-py-5f2-did-agc-commit-function.sh
#   ** run only the parse-clean ratio/Python-snapshot specification **
#       SAMPLE_TYPES="ratio" NCLOC_SPECS="python_snapshot" \
#       bash proc_sh/run-py-5f2-did-agc-commit-function.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
INPUT_ROOT="${INPUT_ROOT:-repo_python/run-py-5e/strict}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-5f/strict}"

SAMPLE_TYPES="${SAMPLE_TYPES:-full ratio}"
NCLOC_SPECS="${NCLOC_SPECS:-paper python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-parse_clean}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-5f}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-5f-did-agc-commit-function-${PARSE_EXCLUSION_MODE}-${RUN_TS}.log}"

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

read -r -a SAMPLE_ARRAY <<< "${SAMPLE_TYPES}"
read -r -a NCLOC_ARRAY <<< "${NCLOC_SPECS}"

for sample_type in "${SAMPLE_ARRAY[@]}"; do
    case "${sample_type}" in
        full|ratio)
            ;;
        *)
            echo "ERROR: Unsupported sample type: ${sample_type}" >&2
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
            exit 2
            ;;
    esac
done

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
    echo "run-py-5f execution summary"
    echo "Started:             ${START_TIME}"
    echo "Completed:           $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:             %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Parse mode:          ${PARSE_EXCLUSION_MODE}"
    echo "Time mode:           ${TIME_MODE}"
    echo "Planned renders:     ${PLANNED_RUNS}"
    echo "Completed renders:   ${COMPLETED_RUNS}"
    echo "Last/current render: ${CURRENT_RUN}"
    echo "Exit code:           ${exit_code}"
    echo "Log file:            ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "============================================================================"
echo "run-py-5f: Borusyak DiD for commit-function AGC outcomes"
echo "Started:             ${START_TIME}"
echo "Project root:        ${PROJECT_ROOT}"
echo "Rscript:             $(command -v "${RSCRIPT_BIN}")"
echo "R Markdown:          ${RMD_FILE}"
echo "Helper:              ${HELPER_FILE}"
echo "Input root:          ${INPUT_ROOT}"
echo "Output root:         ${OUTPUT_ROOT}"
echo "Sample types:        ${SAMPLE_ARRAY[*]}"
echo "NCLOC specifications:${NCLOC_ARRAY[*]}"
echo "Time mode:           ${TIME_MODE}"
echo "Parse mode:          ${PARSE_EXCLUSION_MODE}"
echo "Planned renders:     ${PLANNED_RUNS}"
echo "Log file:            ${LOG_FILE}"
echo "============================================================================"

for sample_type in "${SAMPLE_ARRAY[@]}"; do
    if [[ "${sample_type}" == "full" ]]; then
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" ]]; then
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_parse_clean.csv"
        else
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function.csv"
        fi
    else
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" ]]; then
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_ratio_positive_parse_clean.csv"
        else
            panel_path="${INPUT_ROOT}/panel_event_monthly_agc_commit_function_ratio_positive.csv"
        fi
    fi

    if [[ ! -s "${panel_path}" ]]; then
        echo "ERROR: Input panel is missing or empty: ${panel_path}" >&2
        exit 2
    fi

    for ncloc_spec in "${NCLOC_ARRAY[@]}"; do
        out_dir="${OUTPUT_ROOT}/${sample_type}/${ncloc_spec}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}"
        panel_label="strict_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}"
        html_output="DiffInDiffBorusyak_agc_commit_function_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"

        mkdir -p "${out_dir}"

        # Remove only the artifacts generated by this specification so stale
        # outputs cannot be mistaken for a successful current run.
        rm -f \
            "${out_dir}/${html_output}" \
            "${out_dir}/borusyak_agc_commit_function_static_effects.csv" \
            "${out_dir}/borusyak_agc_commit_function_dynamic_effects.csv" \
            "${out_dir}/borusyak_agc_commit_function_panel_checks.csv" \
            "${out_dir}/borusyak_agc_commit_function_input_summary.csv" \
            "${out_dir}/borusyak_agc_commit_function_static_errors.csv" \
            "${out_dir}/borusyak_agc_commit_function_dynamic_errors.csv" \
            "${out_dir}/borusyak_agc_commit_function_metadata.csv" \
            "${out_dir}/dynamic_effects_borusyak_agc_commit_function.pdf"

        CURRENT_RUN="sample=${sample_type} ncloc=${ncloc_spec} time=${TIME_MODE} parse=${PARSE_EXCLUSION_MODE}"
        run_number=$((COMPLETED_RUNS + 1))
        render_start_epoch="$(date +%s)"

        echo
        echo "----------------------------------------------------------------------------"
        printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
        echo "Input panel:      ${panel_path}"
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

        parse_rows="$(awk -F, '$1 == "parse_exclusion_rows_in_model_sample" {gsub(/\r/, "", $2); print $2}' \
            "${out_dir}/borusyak_agc_commit_function_panel_checks.csv")"
        if [[ "${PARSE_EXCLUSION_MODE}" == "parse_clean" && "${parse_rows}" != "0" ]]; then
            echo "ERROR: Parse-clean run retained parse-exclusion rows: ${parse_rows:-missing}" >&2
            exit 4
        fi

        COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
        render_end_epoch="$(date +%s)"
        render_elapsed=$((render_end_epoch - render_start_epoch))
        printf '[%02d/%02d] PASS elapsed=%ds parse_exclusion_rows=%s\n' \
            "${COMPLETED_RUNS}" "${PLANNED_RUNS}" "${render_elapsed}" "${parse_rows:-unknown}"
    done
done

CURRENT_RUN="all requested renders completed"
echo
echo "All ${COMPLETED_RUNS} Borusyak parse-clean renders completed successfully."
