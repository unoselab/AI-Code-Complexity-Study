#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-py-7j: Prepare module-function + class-method AGC unique-body panels
# -----------------------------------------------------------------------------
# Scientific scope:
#   - Include synchronous module-level functions: function_kind=module_function
#   - Include synchronous class methods:          function_kind=method
#   - Exclude async and nested function kinds.
#   - Use AGC-like classifications for the analysis outcome.
#   - Count distinct function_body_sha256 values per repository-month across
#     both included kinds. Cross-kind duplicates are counted once.
#   - Create zero-inclusive, parse-clean, positive-outcome, and positive-outcome
#     parse-clean panels.
#   - Do not carry HWC outcomes or AGC/HWC ratio outcomes into analysis panels.
#
# Inputs:
#   1. Event-level frozen NPR classifications from run-py-7a.
#   2. Zero-inclusive matched panel from run-py-7b, used for panel membership,
#      treatment timing, covariates, parse flags, and detector metadata.
#
# Main output for the planned run-py-7k selected-sample sensitivity:
#   repo_python/run-py-7j/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_and_class_method_
#       agc_unique_body_positive_outcome_parse_clean.csv
#
# Usage:
#   OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7j-prepare-regfun-classmethod-agc-uniquebody-did-input.sh
#
# Optional self-test followed by production execution:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7j-prepare-regfun-classmethod-agc-uniquebody-did-input.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_regfun_classmethod_agc_uniquebody_did_input.py}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
EVENT_CLASSIFICATIONS="${EVENT_CLASSIFICATIONS:-repo_python/run-py-7a/strict/specifications/${SPECIFICATION_NAME}/agc_commit_function_npr_event_classifications.csv}"
BASE_PANEL="${BASE_PANEL:-repo_python/run-py-7b/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_agc_commit_function_npr.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7j/strict/specifications/${SPECIFICATION_NAME}}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-0}"
SKIP_FROZEN_KIND_COUNT_CHECKS="${SKIP_FROZEN_KIND_COUNT_CHECKS:-0}"

RUN_TS="${RUN_TS:-$(date +'%Y%m%d-%H%M%S')}"
LOG_DIR="${LOG_DIR:-logs/run-py-7j}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7j-prepare-module-function-class-method-agc-unique-body-${SPECIFICATION_NAME}-${RUN_TS}.log}"

for binary_flag in OVERWRITE_OUTPUT RUN_SELF_TEST SKIP_FROZEN_KIND_COUNT_CHECKS; do
    value="${!binary_flag}"
    case "${value}" in
        0|1) ;;
        *)
            echo "ERROR: ${binary_flag} must be 0 or 1." >&2
            exit 2
            ;;
    esac
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

if [[ ! -s "${PYTHON_SCRIPT}" ]]; then
    echo "ERROR: Python script is missing or empty: ${PYTHON_SCRIPT}" >&2
    exit 2
fi

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%d %H:%M:%S %Z')"

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
    echo "run-py-7j execution summary"
    echo "Started:              ${START_TIME}"
    echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Elapsed:              %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Specification:        ${SPECIFICATION_NAME}"
    echo "Exit code:            ${exit_code}"
    echo "Log file:             ${LOG_FILE}"
    echo "================================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_SCRIPT_SHA="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

POSITIVE_PARSE_CLEAN_PANEL="${OUTPUT_DIR}/panel_event_monthly_regular_module_function_and_class_method_agc_unique_body_positive_outcome_parse_clean.csv"
CHECKS_FILE="${OUTPUT_DIR}/qc/regular_module_function_and_class_method_agc_unique_body_did_input_checks.csv"
SUMMARY_FILE="${OUTPUT_DIR}/qc/regular_module_function_and_class_method_agc_unique_body_did_input_summary.json"

cat <<EOF
================================================================================
run-py-7j: prepare module-function + class-method AGC unique-body panels
Started:                    ${START_TIME}
Project root:               ${PROJECT_ROOT}
Python:                     $(command -v "${PYTHON_BIN}")
Python version:             $("${PYTHON_BIN}" --version 2>&1)
Python script:              ${PYTHON_SCRIPT}
Python script SHA:          ${PYTHON_SCRIPT_SHA}
Specification:              ${SPECIFICATION_NAME}
Included function kinds:    module_function, method
Excluded function kinds:    async and nested variants
Classification outcome:     AGC-like only
Count unit:                 distinct body SHA per repository-month across kinds
Positive sample restriction:outcome > 0
Event classifications:      ${EVENT_CLASSIFICATIONS}
Base panel:                 ${BASE_PANEL}
Output directory:           ${OUTPUT_DIR}
Overwrite output:           ${OVERWRITE_OUTPUT}
Run self-test:              ${RUN_SELF_TEST}
Skip frozen count checks:   ${SKIP_FROZEN_KIND_COUNT_CHECKS}
Log file:                   ${LOG_FILE}
================================================================================
EOF

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

for required_input in "${EVENT_CLASSIFICATIONS}" "${BASE_PANEL}"; do
    if [[ ! -s "${required_input}" ]]; then
        echo "ERROR: Required input is missing or empty: ${required_input}" >&2
        exit 2
    fi
done

args=(
    "${PYTHON_SCRIPT}"
    --event-classifications "${EVENT_CLASSIFICATIONS}"
    --base-panel "${BASE_PANEL}"
    --output-dir "${OUTPUT_DIR}"
    --specification-name "${SPECIFICATION_NAME}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    args+=(--overwrite-output)
fi
if [[ "${SKIP_FROZEN_KIND_COUNT_CHECKS}" == "1" ]]; then
    args+=(--skip-frozen-kind-count-checks)
fi

"${PYTHON_BIN}" "${args[@]}"

expected_outputs=(
    "${OUTPUT_DIR}/panel_event_monthly_regular_module_function_and_class_method_agc_unique_body.csv"
    "${OUTPUT_DIR}/panel_event_monthly_regular_module_function_and_class_method_agc_unique_body_parse_clean.csv"
    "${OUTPUT_DIR}/panel_event_monthly_regular_module_function_and_class_method_agc_unique_body_positive_outcome.csv"
    "${POSITIVE_PARSE_CLEAN_PANEL}"
    "${OUTPUT_DIR}/regular_module_function_and_class_method_agc_unique_body_repo_month_counts.csv"
    "${OUTPUT_DIR}/regular_module_function_and_class_method_agc_unique_body_kind_summary.csv"
    "${OUTPUT_DIR}/regular_module_function_and_class_method_agc_unique_body_overlap_audit.csv"
    "${OUTPUT_DIR}/regular_module_function_and_class_method_agc_unique_body_rankify_audit.csv"
    "${CHECKS_FILE}"
    "${SUMMARY_FILE}"
)

for expected_file in "${expected_outputs[@]}"; do
    if [[ ! -s "${expected_file}" ]]; then
        echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
        exit 3
    fi
done

failed_checks="$(awk -F, 'NR > 1 && tolower($2) != "true" {count++} END {print count + 0}' "${CHECKS_FILE}")"
if [[ "${failed_checks}" != "0" ]]; then
    echo "ERROR: DiD input validation contains ${failed_checks} failed checks." >&2
    exit 4
fi

zero_rows_in_positive="$(awk -F, 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "npr_agc_regular_module_function_and_class_method_unique_bodies") c=i; next} c && $c == 0 {n++} END {print n + 0}' "${POSITIVE_PARSE_CLEAN_PANEL}")"
if [[ "${zero_rows_in_positive}" != "0" ]]; then
    echo "ERROR: Positive parse-clean panel contains ${zero_rows_in_positive} zero-outcome rows." >&2
    exit 5
fi

echo "run-py-7j PASS: combined-scope panel and QC artifacts were created."
echo "Next-stage input: ${POSITIVE_PARSE_CLEAN_PANEL}"
