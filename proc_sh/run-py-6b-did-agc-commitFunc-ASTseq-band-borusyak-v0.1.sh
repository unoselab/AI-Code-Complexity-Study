#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-6b-did-agc-commitFunc-ASTseq-band-borusyak.sh
# -----------------------------------------------------------------------------
# Run independent Borusyak DiD renders for ten pre-specified AST sequence
# token bands produced by run-py-6a.
#
# Default primary heterogeneity specification:
#   - Bands: 50-59, 60-69, ..., 140-149
#   - Samples: full zero-inclusive and ratio-positive conditional
#   - NCLOC: paper
#   - Time: sequential calendar month
#   - Parse exclusions: all analysis-ready repository-months
#   - Planned renders: 10 bands x 2 samples x 1 NCLOC = 20
#
# This wrapper is standalone. It reuses the validated R rendering logic from
# run-py-5f but does not call any existing shell wrapper.
# 
# Usage:
# bash proc_sh/run-py-6b-did-agc-commitFunc-ASTseq-band-borusyak.sh
# NCLOC_SUBSET="python_snapshot" bash proc_sh/run-py-6b-did-agc-commitFunc-ASTseq-band-borusyak.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

WRAPPER_SCRIPT="proc_sh/run-py-6b-did-agc-commitFunc-ASTseq-band-borusyak.sh"
RMD_FILE="proc_r/DiffInDiffBorusyak_agc_commit_function_ast_sequence_band.Rmd"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PYTHON_BIN="${PYTHON_BIN:-python}"

BAND_ROOT="repo_python/run-py-6a/strict/bands"
OUTPUT_ROOT="repo_python/run-py-6b/strict/bands"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_EXCLUSION_MODE="${PARSE_EXCLUSION_MODE:-all}"

BAND_LABELS=(
    "50-59" "60-69" "70-79" "80-89" "90-99"
    "100-109" "110-119" "120-129" "130-139" "140-149"
)
declare -A BAND_SLUGS=(
    ["50-59"]="50_59"
    ["60-69"]="60_69"
    ["70-79"]="70_79"
    ["80-89"]="80_89"
    ["90-99"]="90_99"
    ["100-109"]="100_109"
    ["110-119"]="110_119"
    ["120-129"]="120_129"
    ["130-139"]="130_139"
    ["140-149"]="140_149"
)
declare -A BAND_LOWERS=(
    ["50-59"]="50"
    ["60-69"]="60"
    ["70-79"]="70"
    ["80-89"]="80"
    ["90-99"]="90"
    ["100-109"]="100"
    ["110-119"]="110"
    ["120-129"]="120"
    ["130-139"]="130"
    ["140-149"]="140"
)
declare -A BAND_UPPERS=(
    ["50-59"]="60"
    ["60-69"]="70"
    ["70-79"]="80"
    ["80-89"]="90"
    ["90-99"]="100"
    ["100-109"]="110"
    ["110-119"]="120"
    ["120-129"]="130"
    ["130-139"]="140"
    ["140-149"]="150"
)

DEFAULT_NCLOC_SPECS=("paper")
DEFAULT_SAMPLE_TYPES=("full" "ratio")
VALID_NCLOC_SPECS=("paper" "python_snapshot")
VALID_SAMPLE_TYPES=("full" "ratio")
VALID_TIME_MODES=("calendar_month" "original_yyyymm")
VALID_PARSE_MODES=("all" "parse_clean")

contains_value() {
    local requested="$1"
    shift
    local candidate
    for candidate in "$@"; do
        if [[ "${candidate}" == "${requested}" ]]; then
            return 0
        fi
    done
    return 1
}

hash_file() {
    local file_path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${file_path}" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${file_path}" | awk '{print $1}'
    else
        printf '%s\n' "unavailable"
    fi
}

if [[ -n "${BAND_SUBSET:-}" ]]; then
    read -r -a REQUESTED_BANDS <<< "${BAND_SUBSET}"
else
    REQUESTED_BANDS=("${BAND_LABELS[@]}")
fi

if [[ -n "${NCLOC_SUBSET:-}" ]]; then
    read -r -a REQUESTED_NCLOC <<< "${NCLOC_SUBSET}"
else
    REQUESTED_NCLOC=("${DEFAULT_NCLOC_SPECS[@]}")
fi

if [[ -n "${SAMPLE_SUBSET:-}" ]]; then
    read -r -a REQUESTED_SAMPLES <<< "${SAMPLE_SUBSET}"
else
    REQUESTED_SAMPLES=("${DEFAULT_SAMPLE_TYPES[@]}")
fi

if ! command -v "${RSCRIPT_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Rscript executable not found: ${RSCRIPT_BIN}" >&2
    exit 2
fi

for required_file in "${RMD_FILE}" "${HELPER_FILE}"; do
    if [[ ! -f "${required_file}" ]]; then
        echo "ERROR: Required file not found: ${required_file}" >&2
        exit 2
    fi
done

if [[ ! -d "${BAND_ROOT}" ]]; then
    echo "ERROR: run-py-6a band directory not found: ${BAND_ROOT}" >&2
    echo "       Run run-py-6a before run-py-6b." >&2
    exit 2
fi

if (( ${#REQUESTED_BANDS[@]} == 0 ||
      ${#REQUESTED_NCLOC[@]} == 0 ||
      ${#REQUESTED_SAMPLES[@]} == 0 )); then
    echo "ERROR: Band, NCLOC, and sample selections must be non-empty." >&2
    exit 2
fi

for band_label in "${REQUESTED_BANDS[@]}"; do
    if [[ -z "${BAND_SLUGS[${band_label}]+set}" ]]; then
        echo "ERROR: Unknown AST sequence token band: ${band_label}" >&2
        echo "       Valid bands: ${BAND_LABELS[*]}" >&2
        exit 2
    fi
done

for ncloc_spec in "${REQUESTED_NCLOC[@]}"; do
    if ! contains_value "${ncloc_spec}" "${VALID_NCLOC_SPECS[@]}"; then
        echo "ERROR: Unknown NCLOC specification: ${ncloc_spec}" >&2
        echo "       Valid values: ${VALID_NCLOC_SPECS[*]}" >&2
        exit 2
    fi
done

for sample_type in "${REQUESTED_SAMPLES[@]}"; do
    if ! contains_value "${sample_type}" "${VALID_SAMPLE_TYPES[@]}"; then
        echo "ERROR: Unknown sample type: ${sample_type}" >&2
        echo "       Valid values: ${VALID_SAMPLE_TYPES[*]}" >&2
        exit 2
    fi
done

if ! contains_value "${TIME_MODE}" "${VALID_TIME_MODES[@]}"; then
    echo "ERROR: Unknown TIME_MODE: ${TIME_MODE}" >&2
    echo "       Valid values: ${VALID_TIME_MODES[*]}" >&2
    exit 2
fi

if ! contains_value "${PARSE_EXCLUSION_MODE}" "${VALID_PARSE_MODES[@]}"; then
    echo "ERROR: Unknown PARSE_EXCLUSION_MODE: ${PARSE_EXCLUSION_MODE}" >&2
    echo "       Valid values: ${VALID_PARSE_MODES[*]}" >&2
    exit 2
fi

for band_label in "${REQUESTED_BANDS[@]}"; do
    band_slug="${BAND_SLUGS[${band_label}]}"
    for sample_type in "${REQUESTED_SAMPLES[@]}"; do
        if [[ "${sample_type}" == "full" ]]; then
            panel_path="${BAND_ROOT}/${band_label}/panel_event_monthly_agc_commit_function_ast_${band_slug}.csv"
        else
            panel_path="${BAND_ROOT}/${band_label}/panel_event_monthly_agc_commit_function_ast_${band_slug}_ratio_positive.csv"
        fi
        if [[ ! -f "${panel_path}" ]]; then
            echo "ERROR: Required band panel not found: ${panel_path}" >&2
            exit 2
        fi
    done
done

RUN_TS="$(date +'%Y%m%d-%H%M%S')"
LOG_DIR="logs/run-py-6b"
LOG_FILE="${LOG_DIR}/run-py-6b-did-agc-commitFunc-ASTseq-band-borusyak-${RUN_TS}.log"
mkdir -p "${OUTPUT_ROOT}" "${LOG_DIR}"

START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"
PLANNED_RUNS=$((
    ${#REQUESTED_BANDS[@]} *
    ${#REQUESTED_NCLOC[@]} *
    ${#REQUESTED_SAMPLES[@]}
))
COMPLETED_RUNS=0
CURRENT_RUN="<not started>"

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
    echo "run-py-6b execution summary"
    echo "Started:          ${START_TIME}"
    echo "Completed:        $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:          %02d:%02d:%02d\n' \
        "${hours}" "${minutes}" "${seconds}"
    echo "Planned renders:  ${PLANNED_RUNS}"
    echo "Completed renders:${COMPLETED_RUNS}"
    echo "Last render:      ${CURRENT_RUN}"
    echo "Exit code:        ${exit_code}"
    echo "Output root:      ${OUTPUT_ROOT}"
    echo "Log file:         ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

RSCRIPT_PATH="$(command -v "${RSCRIPT_BIN}")"
PYTHON_PATH="$(command -v "${PYTHON_BIN}" 2>/dev/null || true)"
RMD_SHA256="$(hash_file "${RMD_FILE}")"
HELPER_SHA256="$(hash_file "${HELPER_FILE}")"

echo "============================================================================"
echo "run-py-6b: Borusyak DiD by AST sequence token band"
echo "Started:              ${START_TIME}"
echo "Wrapper script:       ${WRAPPER_SCRIPT}"
echo "Rscript path:         ${RSCRIPT_PATH}"
echo "Rmd file:             ${RMD_FILE}"
echo "Rmd SHA-256:          ${RMD_SHA256}"
echo "Helper file:          ${HELPER_FILE}"
echo "Helper SHA-256:       ${HELPER_SHA256}"
echo "Python path:          ${PYTHON_PATH:-<not used by this R-only stage>}"
echo "Python role:          not used by run-py-6b"
echo "Band input root:      ${BAND_ROOT}"
echo "Output root:          ${OUTPUT_ROOT}"
echo "Bands:                ${REQUESTED_BANDS[*]}"
echo "NCLOC specifications: ${REQUESTED_NCLOC[*]}"
echo "Sample types:         ${REQUESTED_SAMPLES[*]}"
echo "Time mode:            ${TIME_MODE}"
echo "Parse mode:           ${PARSE_EXCLUSION_MODE}"
echo "Planned renders:      ${PLANNED_RUNS}"
echo "Log file:             ${LOG_FILE}"
echo "============================================================================"
echo "NOTE: This stage estimates pre-specified bounded-band heterogeneity."
echo "      The primary >=50 specification with no upper bound is separate."
echo "============================================================================"

for band_label in "${REQUESTED_BANDS[@]}"; do
    band_slug="${BAND_SLUGS[${band_label}]}"
    band_lower="${BAND_LOWERS[${band_label}]}"
    band_upper="${BAND_UPPERS[${band_label}]}"

    for ncloc_spec in "${REQUESTED_NCLOC[@]}"; do
        for sample_type in "${REQUESTED_SAMPLES[@]}"; do
            if [[ "${sample_type}" == "full" ]]; then
                panel_path="${BAND_ROOT}/${band_label}/panel_event_monthly_agc_commit_function_ast_${band_slug}.csv"
            else
                panel_path="${BAND_ROOT}/${band_label}/panel_event_monthly_agc_commit_function_ast_${band_slug}_ratio_positive.csv"
            fi

            out_dir="${OUTPUT_ROOT}/${band_label}/${sample_type}/${ncloc_spec}_ncloc/${TIME_MODE}/${PARSE_EXCLUSION_MODE}"
            panel_label="strict_band_${band_slug}_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}"
            html_output="DiffInDiffBorusyak_agc_commit_function_ast_band_${band_slug}_${sample_type}_${ncloc_spec}_ncloc_${TIME_MODE}_${PARSE_EXCLUSION_MODE}.html"
            panel_sha256="$(hash_file "${panel_path}")"

            mkdir -p "${out_dir}"
            CURRENT_RUN="band=${band_label} sample=${sample_type} ncloc=${ncloc_spec} time=${TIME_MODE} parse=${PARSE_EXCLUSION_MODE}"
            run_number=$((COMPLETED_RUNS + 1))
            render_start_epoch="$(date +%s)"

            echo
            echo "----------------------------------------------------------------------------"
            printf '[%02d/%02d] %s\n' "${run_number}" "${PLANNED_RUNS}" "${CURRENT_RUN}"
            echo "Input panel:      ${panel_path}"
            echo "Input SHA-256:    ${panel_sha256}"
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
            AST_SEQUENCE_TOKEN_BAND="${band_label}" \
            AST_SEQUENCE_TOKEN_LOWER="${band_lower}" \
            AST_SEQUENCE_TOKEN_UPPER_EXCLUSIVE="${band_upper}" \
            OUTPUT_HTML="${html_output}" \
                "${RSCRIPT_BIN}" -e "rmarkdown::render(
                  input = '${PROJECT_ROOT}/${RMD_FILE}',
                  output_file = Sys.getenv('OUTPUT_HTML'),
                  output_dir = Sys.getenv('OUT_DIR'),
                  knit_root_dir = Sys.getenv('PROJECT_ROOT'),
                  envir = new.env(parent = globalenv()),
                  quiet = FALSE
                )"

            COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
            render_end_epoch="$(date +%s)"
            render_elapsed=$((render_end_epoch - render_start_epoch))
            printf '[%02d/%02d] PASS elapsed=%ds\n' \
                "${COMPLETED_RUNS}" "${PLANNED_RUNS}" "${render_elapsed}"
        done
    done
done

CURRENT_RUN="all requested renders completed"
echo
echo "All ${COMPLETED_RUNS} Borusyak band renders completed successfully."
