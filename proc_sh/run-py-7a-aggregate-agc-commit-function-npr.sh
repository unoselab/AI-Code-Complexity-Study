#!/usr/bin/env bash
#
# Aggregate frozen DetectCodeGPT NPR body scores into event-level and
# repository-month artifacts for the Python DiD workspace.
#
# This wrapper is standalone. It follows the logging, validation, and explicit
# input/output conventions of the existing run-py wrappers, but it does not
# call or depend on any existing shell wrapper.
#
# Default detector source workspace:
#   ../../detect_code_gpt
#
# Default detector specification:
#   range100_200 using the completed 173-server run-1d output
#
# Primary outputs:
#   repo_python/run-py-7a/strict/specifications/range100_200/
#     agc_commit_function_npr_body_classifications.csv
#     agc_commit_function_npr_event_classifications.csv
#     repo_month_agc_commit_function_npr_analysis_complete.csv
#     agc_commit_function_npr_mapping_audit.csv
#     qc/agc_commit_function_npr_aggregation_checks.csv
#     qc/agc_commit_function_npr_aggregation_summary.json
# 
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7a-aggregate-agc-commit-function-npr.sh
# 
# 

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-${PROJECT_ROOT}/proc_scripts/aggregate_agc_commit_function_npr.py}"

SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
MINIMUM_BODY_TOKENS="${MINIMUM_BODY_TOKENS:-100}"
MAXIMUM_BODY_TOKENS="${MAXIMUM_BODY_TOKENS:-200}"

# From ai-code-complexity-study, the detect_code_gpt workspace is normally
# two directory levels upward and then under project-workspace/detect_code_gpt.
DETECT_CODE_GPT_ROOT="${DETECT_CODE_GPT_ROOT:-${PROJECT_ROOT}/../../detect_code_gpt}"
DETECTOR_OUTPUT_DIR="${DETECTOR_OUTPUT_DIR:-${DETECT_CODE_GPT_ROOT}/output/commit_function/run-1d/range100_200-overlap-v1}"

INPUT_EVENTS="${INPUT_EVENTS:-${DETECT_CODE_GPT_ROOT}/output/commit_function/run-1a/strict/commit_function_detectcodegpt_input_events.csv}"
BODY_SCORES="${BODY_SCORES:-${DETECTOR_OUTPUT_DIR}/commit_function_npr_body_scores.csv}"
FULL_MANIFEST="${FULL_MANIFEST:-${DETECTOR_OUTPUT_DIR}/commit_function_npr_full_manifest.csv}"
THRESHOLD_SPECIFICATION="${THRESHOLD_SPECIFICATION:-${DETECT_CODE_GPT_ROOT}/output/commit_function/run-1c0b/mixedcode-overlap-threshold-v1/mixedcode_overlap_threshold_specification.json}"
DETECTOR_SUMMARY="${DETECTOR_SUMMARY:-${DETECTOR_OUTPUT_DIR}/qc/commit_function_npr_summary.json}"
DETECTOR_METADATA="${DETECTOR_METADATA:-${DETECTOR_OUTPUT_DIR}/qc/commit_function_npr_metadata.json}"

SOURCE_COUNTS="${SOURCE_COUNTS:-${PROJECT_ROOT}/repo_python/run-py-5a-py312/strict/repo_month_function_event_counts.csv}"
PANEL="${PANEL:-${PROJECT_ROOT}/repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv}"
PARSE_EXCLUSIONS="${PARSE_EXCLUSIONS:-${PROJECT_ROOT}/repo_python/run-py-5b-py312/strict/agc_commit_function_parse_exclusions_by_repo_month.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_python/run-py-7a/strict/specifications/${SPECIFICATION_NAME}}"
QC_DIR="${QC_DIR:-${OUTPUT_DIR}/qc}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-py-7a}"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1633}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-780}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-853}"
EXPECTED_SELECTED_BODIES="${EXPECTED_SELECTED_BODIES:-69231}"
EXPECTED_WINDOWS="${EXPECTED_WINDOWS:-114379}"
EXPECTED_PARTIAL_BODY_SCORES="${EXPECTED_PARTIAL_BODY_SCORES:-0}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

mkdir -p "${LOG_DIR}"
RUN_TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-py-7a-aggregate-agc-commit-function-npr-${SPECIFICATION_NAME}-${RUN_TIMESTAMP}.log"
START_EPOCH="$(date +%s)"

exec > >(tee -a "${LOG_FILE}") 2>&1

finish() {
    local exit_code="$?"
    local end_epoch
    local elapsed
    end_epoch="$(date +%s)"
    elapsed="$((end_epoch - START_EPOCH))"
    printf '\n============================================================================\n'
    echo "run-py-7a execution summary"
    echo "Completed:              $(date)"
    printf 'Elapsed seconds:        %s\n' "${elapsed}"
    printf 'Exit code:              %s\n' "${exit_code}"
    printf 'Log file:               %s\n' "${LOG_FILE}"
    echo "============================================================================"
    exit "${exit_code}"
}
trap finish EXIT

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "${path}" ]]; then
        echo "ERROR: ${label} not found: ${path}" >&2
        exit 1
    fi
}

sha256_value() {
    local path="$1"
    sha256sum "${path}" | awk '{print $1}'
}

require_file "${PYTHON_SCRIPT}" "Python script"
require_file "${INPUT_EVENTS}" "DetectCodeGPT input events"
require_file "${BODY_SCORES}" "DetectCodeGPT body scores"
require_file "${FULL_MANIFEST}" "DetectCodeGPT full manifest"
require_file "${THRESHOLD_SPECIFICATION}" "Frozen threshold specification"
require_file "${DETECTOR_SUMMARY}" "DetectCodeGPT summary"
require_file "${DETECTOR_METADATA}" "DetectCodeGPT metadata"
require_file "${SOURCE_COUNTS}" "Extraction-stage repository-month counts"
require_file "${PANEL}" "Matched repository-month panel"

OPTIONAL_PARSE_ARGS=()
if [[ -n "${PARSE_EXCLUSIONS}" ]]; then
    require_file "${PARSE_EXCLUSIONS}" "Parse-exclusion repository-month table"
    OPTIONAL_PARSE_ARGS=(
        --parse-exclusions-by-repo-month "${PARSE_EXCLUSIONS}"
    )
fi

OVERWRITE_ARGS=()
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    OVERWRITE_ARGS=(--overwrite-output)
elif [[ "${OVERWRITE_OUTPUT}" != "0" ]]; then
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1" >&2
    exit 1
fi

if [[ "${RUN_SELF_TEST}" != "0" && "${RUN_SELF_TEST}" != "1" ]]; then
    echo "ERROR: RUN_SELF_TEST must be 0 or 1" >&2
    exit 1
fi

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
SCRIPT_SHA="$(sha256_value "${PYTHON_SCRIPT}")"

printf '============================================================================\n'
echo "run-py-7a: aggregate commit-function NPR results"
echo "Started:                        $(date)"
echo "Workspace:                      ${PROJECT_ROOT}"
echo "Python:                         ${PYTHON_BIN}"
echo "Python version:                 ${PYTHON_VERSION}"
echo "Python script:                  ${PYTHON_SCRIPT}"
echo "Python script SHA:              ${SCRIPT_SHA}"
echo "Specification:                 ${SPECIFICATION_NAME}"
echo "Body-token range:               ${MINIMUM_BODY_TOKENS}-${MAXIMUM_BODY_TOKENS} inclusive"
echo "DetectCodeGPT root:             ${DETECT_CODE_GPT_ROOT}"
echo "Input events:                   ${INPUT_EVENTS}"
echo "Input events SHA:               $(sha256_value "${INPUT_EVENTS}")"
echo "Body scores:                    ${BODY_SCORES}"
echo "Body scores SHA:                $(sha256_value "${BODY_SCORES}")"
echo "Full manifest:                  ${FULL_MANIFEST}"
echo "Full manifest SHA:              $(sha256_value "${FULL_MANIFEST}")"
echo "Threshold specification:        ${THRESHOLD_SPECIFICATION}"
echo "Threshold specification SHA:    $(sha256_value "${THRESHOLD_SPECIFICATION}")"
echo "Detector summary:               ${DETECTOR_SUMMARY}"
echo "Detector metadata:              ${DETECTOR_METADATA}"
echo "Source counts:                  ${SOURCE_COUNTS}"
echo "Matched panel:                  ${PANEL}"
echo "Parse exclusions:               ${PARSE_EXCLUSIONS:-<disabled>}"
echo "Output directory:               ${OUTPUT_DIR}"
echo "QC directory:                   ${QC_DIR}"
echo "Expected panel rows:            ${EXPECTED_PANEL_ROWS}"
echo "Expected selected bodies:       ${EXPECTED_SELECTED_BODIES}"
echo "Expected windows:               ${EXPECTED_WINDOWS}"
echo "Expected partial body scores:   ${EXPECTED_PARTIAL_BODY_SCORES}"
echo "Run self-test:                  ${RUN_SELF_TEST}"
echo "Overwrite output:               ${OVERWRITE_OUTPUT}"
echo "Log file:                       ${LOG_FILE}"
printf '============================================================================\n'

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --input-events "${INPUT_EVENTS}" \
    --body-scores "${BODY_SCORES}" \
    --full-manifest "${FULL_MANIFEST}" \
    --threshold-specification "${THRESHOLD_SPECIFICATION}" \
    --detector-summary "${DETECTOR_SUMMARY}" \
    --detector-metadata "${DETECTOR_METADATA}" \
    --source-counts "${SOURCE_COUNTS}" \
    --panel "${PANEL}" \
    "${OPTIONAL_PARSE_ARGS[@]}" \
    --output-dir "${OUTPUT_DIR}" \
    --qc-dir "${QC_DIR}" \
    --specification-name "${SPECIFICATION_NAME}" \
    --minimum-body-tokens "${MINIMUM_BODY_TOKENS}" \
    --maximum-body-tokens "${MAXIMUM_BODY_TOKENS}" \
    --expected-panel-rows "${EXPECTED_PANEL_ROWS}" \
    --expected-control-rows "${EXPECTED_CONTROL_ROWS}" \
    --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}" \
    --expected-selected-bodies "${EXPECTED_SELECTED_BODIES}" \
    --expected-windows "${EXPECTED_WINDOWS}" \
    --expected-partial-body-scores "${EXPECTED_PARTIAL_BODY_SCORES}" \
    "${OVERWRITE_ARGS[@]}"

SUMMARY_FILE="${QC_DIR}/agc_commit_function_npr_aggregation_summary.json"
CHECKS_FILE="${QC_DIR}/agc_commit_function_npr_aggregation_checks.csv"
require_file "${SUMMARY_FILE}" "Aggregation summary"
require_file "${CHECKS_FILE}" "Aggregation checks"

"${PYTHON_BIN}" - "${SUMMARY_FILE}" "${CHECKS_FILE}" <<'PY'
import json
import sys

import pandas as pd

summary_path = sys.argv[1]
checks_path = sys.argv[2]

with open(summary_path, "r", encoding="utf-8") as handle:
    summary = json.load(handle)
checks = pd.read_csv(checks_path)

failed = checks.loc[~checks["passed"].astype(bool)]
if summary.get("status") != "PASS":
    raise SystemExit(f"Aggregation summary status is not PASS: {summary}")
if not failed.empty:
    raise SystemExit(
        "Aggregation QC contains failed checks:\n" + failed.to_string(index=False)
    )

print("============================================================================")
print("run-py-7a output verification")
print(f"Status:                         {summary['status']}")
print(f"Selected unique bodies:         {summary['selected_unique_bodies']}")
print(f"Selected event rows:            {summary['selected_event_rows']}")
print(f"Selected-event repo-months:     {summary['selected_event_repo_months']}")
print(f"Complete repository-months:     {summary['complete_repo_months']}")
print(f"Zero selected-event months:     {summary['zero_npr_selected_event_months']}")
print(f"AGC-like selected events:       {summary['npr_agc_function_change_events']}")
print(f"HWC-like selected events:       {summary['npr_hwc_function_change_events']}")
print(f"Conditional-ratio repo-months:  {summary['conditional_ratio_repo_months']}")
print(f"Failed checks:                  {summary['failed_checks']}")
print(f"Complete panel:                 {summary['outputs']['complete_repo_month_panel']}")
print(f"Checks:                         {checks_path}")
print(f"Summary:                        {summary_path}")
print("============================================================================")
PY
