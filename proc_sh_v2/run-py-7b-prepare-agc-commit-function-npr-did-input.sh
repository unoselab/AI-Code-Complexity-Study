#!/usr/bin/env bash
#
# Prepare Borusyak DiD input panels for NPR-based commit-function AGC outcomes.
#
# Inputs:
#   repo_python/run-py-7a/strict/specifications/<SPECIFICATION>/
#     repo_month_agc_commit_function_npr_analysis_complete.csv
#
#   repo_python/run-py-4a/strict/
#     panel_event_monthly_agc_changed_block_py.csv
#
# Outputs:
#   repo_python/run-py-7b/strict/specifications/<SPECIFICATION>/
#     panel_event_monthly_agc_commit_function_npr.csv
#     panel_event_monthly_agc_commit_function_npr_ratio_positive.csv
#     panel_event_monthly_agc_commit_function_npr_parse_clean.csv
#     panel_event_monthly_agc_commit_function_npr_ratio_positive_parse_clean.csv
#     agc_commit_function_npr_event_time_support.csv
#     agc_commit_function_npr_outcome_completeness.csv
#     agc_commit_function_npr_covariate_completeness.csv
#     agc_commit_function_npr_sample_summary.csv
#     agc_commit_function_npr_specification_sample_summary.csv
#     qc/agc_commit_function_npr_did_input_checks.csv
#     qc/agc_commit_function_npr_did_input_summary.json
#     qc/agc_commit_function_npr_did_input_metadata.json
#
# Environment variables:
#   PYTHON_BIN       Python executable. Default: python
#   SPECIFICATION    Frozen NPR body-range specification. Default: range100_200
#   RUN_SELF_TEST    Run the synthetic Python self-test first. Default: 1
#   OVERWRITE_OUTPUT Replace an existing non-empty output directory. Default: 0
#
# Interpretation:
#   Count outcomes use the complete 1,633-row panel. The ratio-positive panel
#   is conditional on at least one NPR-selected function-change event and must
#   not be interpreted as an unconditional repository-month effect.
# 
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7b-prepare-agc-commit-function-npr-did-input.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
SPECIFICATION="${SPECIFICATION:-range100_200}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

PYTHON_SCRIPT="${REPO_ROOT}/proc_scripts/prepare_agc_commit_function_npr_did_input.py"
INPUT_TABLE="${REPO_ROOT}/repo_python/run-py-7a/strict/specifications/${SPECIFICATION}/repo_month_agc_commit_function_npr_analysis_complete.csv"
COVARIATE_PANEL="${REPO_ROOT}/repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv"
OUTPUT_DIR="${REPO_ROOT}/repo_python/run-py-7b/strict/specifications/${SPECIFICATION}"
QC_DIR="${OUTPUT_DIR}/qc"
LOG_DIR="${REPO_ROOT}/logs/run-py-7b"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-py-7b-prepare-agc-commit-function-npr-${SPECIFICATION}-${TIMESTAMP}.log"

EXPECTED_ROWS="${EXPECTED_ROWS:-1633}"
EXPECTED_POSITIVE_EVENT_ROWS="${EXPECTED_POSITIVE_EVENT_ROWS:-1142}"
EXPECTED_ZERO_EVENT_ROWS="${EXPECTED_ZERO_EVENT_ROWS:-491}"
EXPECTED_FUNCTION_EVENT_NO_SELECTED_ROWS="${EXPECTED_FUNCTION_EVENT_NO_SELECTED_ROWS:-147}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-780}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-853}"
EXPECTED_PARSE_EXCLUSION_MONTHS="${EXPECTED_PARSE_EXCLUSION_MONTHS:-97}"
KNOWN_AGE_MISSING="${KNOWN_AGE_MISSING:-15}"
KNOWN_CONTRIBUTORS_MISSING="${KNOWN_CONTRIBUTORS_MISSING:-0}"
KNOWN_STARS_MISSING="${KNOWN_STARS_MISSING:-15}"
KNOWN_ISSUES_MISSING="${KNOWN_ISSUES_MISSING:-15}"
KNOWN_PAPER_NCLOC_MISSING="${KNOWN_PAPER_NCLOC_MISSING:-37}"

FULL_PANEL="${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_npr.csv"
RATIO_PANEL="${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_npr_ratio_positive.csv"
PARSE_CLEAN_FULL_PANEL="${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_npr_parse_clean.csv"
PARSE_CLEAN_RATIO_PANEL="${OUTPUT_DIR}/panel_event_monthly_agc_commit_function_npr_ratio_positive_parse_clean.csv"
CHECKS_FILE="${QC_DIR}/agc_commit_function_npr_did_input_checks.csv"
SUMMARY_FILE="${QC_DIR}/agc_commit_function_npr_did_input_summary.json"
METADATA_FILE="${QC_DIR}/agc_commit_function_npr_did_input_metadata.json"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "${path}" ]]; then
        echo "ERROR: ${label} not found: ${path}" >&2
        exit 1
    fi
}

validate_binary_flag() {
    local value="$1"
    local name="$2"
    if [[ "${value}" != "0" && "${value}" != "1" ]]; then
        echo "ERROR: ${name} must be 0 or 1, observed: ${value}" >&2
        exit 1
    fi
}

sha256_file() {
    local path="$1"
    sha256sum "${path}" | awk '{print $1}'
}

mkdir -p "${LOG_DIR}"

START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

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
    echo "run-py-7b execution summary"
    echo "Started:               ${START_TEXT}"
    echo "Completed:             $(date)"
    printf 'Elapsed:               %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:             ${exit_code}"
    echo "Specification:         ${SPECIFICATION}"
    echo "Input table:           ${INPUT_TABLE}"
    echo "Covariate panel:       ${COVARIATE_PANEL}"
    echo "Output directory:      ${OUTPUT_DIR}"
    echo "QC directory:          ${QC_DIR}"
    echo "Log file:              ${LOG_FILE}"
    echo "============================================================================"

    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

validate_binary_flag "${RUN_SELF_TEST}" "RUN_SELF_TEST"
validate_binary_flag "${OVERWRITE_OUTPUT}" "OVERWRITE_OUTPUT"
require_file "${PYTHON_SCRIPT}" "Python script"
require_file "${INPUT_TABLE}" "run-py-7a complete analysis table"
require_file "${COVARIATE_PANEL}" "matched covariate panel"

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PYTHON_SCRIPT_SHA="$(sha256_file "${PYTHON_SCRIPT}")"
INPUT_TABLE_SHA="$(sha256_file "${INPUT_TABLE}")"
COVARIATE_PANEL_SHA="$(sha256_file "${COVARIATE_PANEL}")"

cat <<INFO
============================================================================
run-py-7b: prepare NPR commit-function Borusyak DiD inputs
Started:                               ${START_TEXT}
Workspace:                             ${REPO_ROOT}
Python:                                ${PYTHON_BIN}
Python version:                        ${PYTHON_VERSION}
Python script:                         ${PYTHON_SCRIPT}
Python script SHA:                     ${PYTHON_SCRIPT_SHA}
Specification:                        ${SPECIFICATION}
Input table:                          ${INPUT_TABLE}
Input table SHA:                      ${INPUT_TABLE_SHA}
Covariate panel:                      ${COVARIATE_PANEL}
Covariate panel SHA:                  ${COVARIATE_PANEL_SHA}
Output directory:                     ${OUTPUT_DIR}
QC directory:                         ${QC_DIR}
Expected full rows:                   ${EXPECTED_ROWS}
Expected ratio-positive rows:         ${EXPECTED_POSITIVE_EVENT_ROWS}
Expected zero NPR-selected rows:      ${EXPECTED_ZERO_EVENT_ROWS}
Expected function/no-selected rows:   ${EXPECTED_FUNCTION_EVENT_NO_SELECTED_ROWS}
Expected control rows:                ${EXPECTED_CONTROL_ROWS}
Expected treatment rows:              ${EXPECTED_TREATMENT_ROWS}
Expected parse-exclusion months:      ${EXPECTED_PARSE_EXCLUSION_MONTHS}
Known age missing rows:                ${KNOWN_AGE_MISSING}
Known contributors missing rows:       ${KNOWN_CONTRIBUTORS_MISSING}
Known stars missing rows:              ${KNOWN_STARS_MISSING}
Known issues missing rows:             ${KNOWN_ISSUES_MISSING}
Known paper NCLOC missing rows:         ${KNOWN_PAPER_NCLOC_MISSING}
Run self-test:                        ${RUN_SELF_TEST}
Overwrite output:                     ${OVERWRITE_OUTPUT}
Log file:                              ${LOG_FILE}
============================================================================
INFO

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

PYTHON_ARGS=(
    "${PYTHON_SCRIPT}"
    --input-table "${INPUT_TABLE}"
    --covariate-panel "${COVARIATE_PANEL}"
    --output-dir "${OUTPUT_DIR}"
    --qc-dir "${QC_DIR}"
    --specification-name "${SPECIFICATION}"
    --expected-rows "${EXPECTED_ROWS}"
    --expected-positive-event-rows "${EXPECTED_POSITIVE_EVENT_ROWS}"
    --expected-zero-event-rows "${EXPECTED_ZERO_EVENT_ROWS}"
    --expected-function-event-no-selected-rows "${EXPECTED_FUNCTION_EVENT_NO_SELECTED_ROWS}"
    --expected-control-rows "${EXPECTED_CONTROL_ROWS}"
    --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}"
    --expected-parse-exclusion-months "${EXPECTED_PARSE_EXCLUSION_MONTHS}"
    --known-age-missing "${KNOWN_AGE_MISSING}"
    --known-contributors-missing "${KNOWN_CONTRIBUTORS_MISSING}"
    --known-stars-missing "${KNOWN_STARS_MISSING}"
    --known-issues-missing "${KNOWN_ISSUES_MISSING}"
    --known-paper-ncloc-missing "${KNOWN_PAPER_NCLOC_MISSING}"
)

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    PYTHON_ARGS+=(--overwrite-output)
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PYTHON_ARGS[@]}"

require_file "${FULL_PANEL}" "full NPR DiD input panel"
require_file "${RATIO_PANEL}" "conditional-ratio NPR DiD input panel"
require_file "${PARSE_CLEAN_FULL_PANEL}" "parse-clean full NPR panel"
require_file "${PARSE_CLEAN_RATIO_PANEL}" "parse-clean ratio NPR panel"
require_file "${CHECKS_FILE}" "NPR DiD input checks"
require_file "${SUMMARY_FILE}" "NPR DiD input summary"
require_file "${METADATA_FILE}" "NPR DiD input metadata"

"${PYTHON_BIN}" - "${SUMMARY_FILE}" "${CHECKS_FILE}" <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd

summary_path = Path(sys.argv[1])
checks_path = Path(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
checks = pd.read_csv(checks_path)

failed_checks = int((~checks["passed"].astype(bool)).sum())
if summary.get("status") != "PASS":
    raise SystemExit(f"ERROR: summary status is {summary.get('status')}")
if failed_checks != 0:
    failed = checks.loc[~checks["passed"].astype(bool), ["check", "observed"]]
    raise SystemExit(
        "ERROR: failed run-py-7b checks:\n" + failed.to_string(index=False)
    )

print("============================================================================")
print("run-py-7b output verification")
print(f"Status:                                  {summary['status']}")
print(f"Specification:                           {summary['specification']}")
print(f"Full panel rows:                         {summary['full_panel_rows']}")
print(f"Conditional-ratio panel rows:            {summary['ratio_panel_rows']}")
print(f"Zero NPR-selected rows:                  {summary['zero_npr_selected_rows']}")
print(
    "Function-event rows with no selected NPR event: "
    f"{summary['function_event_positive_but_no_npr_selected_rows']}"
)
print(f"Control rows:                            {summary['control_rows']}")
print(f"Treatment rows:                          {summary['treatment_rows']}")
print(f"Parse-exclusion months:                  {summary['parse_exclusion_months']}")
print(f"Parse-clean full rows:                   {summary['parse_clean_full_rows']}")
print(f"Parse-clean ratio rows:                  {summary['parse_clean_ratio_rows']}")
print(f"Failed checks:                           {summary['failed_checks']}")
print(f"Checks:                                  {checks_path}")
print(f"Summary:                                 {summary_path}")
print("============================================================================")
PY
