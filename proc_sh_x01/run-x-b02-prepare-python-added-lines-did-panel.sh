#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b02 v4: Prepare Python added-lines DiD panels
# ============================================================
#
# Purpose:
#   1. Recompute monthly physical lines added in tracked Python files.
#   2. Recompute Python-only NCLOC quickly with cloc for each unique snapshot.
#   3. Join the new outcome and cloc NCLOC with the existing SonarQube NCLOC.
#   4. Create exact-common-sample SonarQube and cloc DiD input panels.
#
# Velocity outcomes:
#   Primary:    log_lines_added_py_source
#   Robustness: log_lines_added_py_no_merge
#               log_lines_added_py_source_no_tests
#               log_lines_added_py_all
#
# Backward-compatible aliases:
#   lines_added_py and log_lines_added_py retain the broad merge-inclusive
#   v3 definition and equal lines_added_py_all/log_lines_added_py_all.
#
# NCLOC specifications:
#   - SonarQube: ncloc = ncloc_py_sonarqube from an existing result CSV.
#   - cloc:       ncloc = ncloc_py_cloc recomputed in this run.
#
# Git activity contract:
#   - The configured history ref is resolved once to a frozen commit SHA per repo.
#   - Commit universe is reachable from that frozen tip SHA.
#   - Commit month uses the committer timestamp in America/Chicago.
#   - Broad outcome compares merge commits with their first parent.
#   - Cleaned outcomes exclude merge commits while retaining branch commits in
#     their original committed month.
#   - Root commits count as commits but their added lines are excluded.
#   - Monthly activity is never carried forward.
#   - Model A commits/lines_added are warning-only drift references, not gates.
#   - Broad files are post-change regular tracked .py files outside the
#     configured excluded directories.
#   - Source outcome excludes explicit vendor/_vendor paths, conservative
#     generated API-client paths, and generated resource modules.
#   - Tests remain in the primary source outcome and are excluded only from the
#     source-no-tests sensitivity outcome.
#
# Required inputs:
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_results.csv
#
# Python programs:
#   proc_script_x01/collect_python_added_lines.py
#   proc_script_x01/compute_python_ncloc_cloc.py
#   proc_script_x01/prepare_python_added_lines_did_panels.py
#
# Full run:
#   bash proc_sh_x01/run-x-b02-prepare-python-added-lines-did-panel.sh
#
# Self-tests only:
#   SELF_TEST_ONLY=1 \
#     bash proc_sh_x01/run-x-b02-prepare-python-added-lines-did-panel.sh
#
# One-repository smoke test:
#   OUTPUT_BASE_DIR=repo_x01/smoke-run-x-b02 \
#   REPO_NAME=owner/repository LIMIT_REPOS=1 LIMIT_SNAPSHOTS=0 \
#   STRICT_EXPECTED_COUNTS=0 \
#     bash proc_sh_x01/run-x-b02-prepare-python-added-lines-did-panel.sh
#
# LIMIT_REPOS and LIMIT_SNAPSHOTS can also be used independently. The panel
# builder marks such executions as partial runs and reports unselected base
# rows as warnings rather than false identity or transformation failures.
#
# Resume:
#   Re-run the same command. The added-lines collector reuses completed
#   repository caches and the cloc stage skips successful snapshots.
#
# Important overrides:
#   PYTHON_BIN=/path/to/python
#   CLOC_BIN=/path/to/cloc
#   BASE_PANEL_FILE=...
#   SNAPSHOT_MANIFEST_FILE=...
#   SONARQUBE_RESULTS_FILE=...
#   ANALYSIS_TIMEZONE=America/Chicago
#   HISTORY_REF=HEAD
#   START_REPO_ORDER=1
#   LIMIT_REPOS=0
#   START_SNAPSHOT_ORDER=1
#   LIMIT_SNAPSHOTS=0
#   DATASET_SOURCE=treatment|control|empty
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   STRICT_EXPECTED_COUNTS=1
#   KEEP_CLOC_TEMP=0
#   SELF_TEST_ONLY=0
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b02"
IMPLEMENTATION_VERSION="v4"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-python-added-lines-did-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
CLOC_BIN="${CLOC_BIN:-cloc}"
COLLECTOR_SCRIPT="${COLLECTOR_SCRIPT:-proc_script_x01/collect_python_added_lines.py}"
CLOC_SCRIPT="${CLOC_SCRIPT:-proc_script_x01/compute_python_ncloc_cloc.py}"
PANEL_SCRIPT="${PANEL_SCRIPT:-proc_script_x01/prepare_python_added_lines_did_panels.py}"

BASE_PANEL_FILE="${BASE_PANEL_FILE:-repo_x01/run-x-a05/velocity_did_panel_model_a.csv}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"
SONARQUBE_RESULTS_FILE="${SONARQUBE_RESULTS_FILE:-repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_results.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
ADDED_OUTPUT_DIR="${ADDED_OUTPUT_DIR:-${MAIN_OUTPUT_DIR}/python-added-lines}"
CLOC_OUTPUT_DIR="${CLOC_OUTPUT_DIR:-${MAIN_OUTPUT_DIR}/python-ncloc-cloc}"
PANEL_OUTPUT_DIR="${PANEL_OUTPUT_DIR:-${MAIN_OUTPUT_DIR}/panels}"
LEGACY_PANEL_DIR="${LEGACY_PANEL_DIR:-${MAIN_OUTPUT_DIR}/legacy-python-ncloc-panels}"
CACHE_DIR="${CACHE_DIR:-${TMP_OUTPUT_DIR}/python-added-lines-repo-cache}"
CLOC_TEMP_ROOT="${CLOC_TEMP_ROOT:-${TMP_OUTPUT_DIR}/cloc-work}"

PYTHON_ADDED_REPO_MONTH_OUTPUT="${PYTHON_ADDED_REPO_MONTH_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_repo_month.csv}"
PYTHON_ADDED_COMMIT_OUTPUT="${PYTHON_ADDED_COMMIT_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_commit.csv}"
PYTHON_ADDED_FILE_OUTPUT="${PYTHON_ADDED_FILE_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_file.csv}"
PYTHON_ADDED_ISSUES_OUTPUT="${PYTHON_ADDED_ISSUES_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_issues.csv}"
PYTHON_ADDED_RECONCILIATION_OUTPUT="${PYTHON_ADDED_RECONCILIATION_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_reconciliation.csv}"
PYTHON_ADDED_QC_OUTPUT="${PYTHON_ADDED_QC_OUTPUT:-${ADDED_OUTPUT_DIR}/python_added_lines_qc.csv}"
PYTHON_ADDED_SUMMARY_OUTPUT="${PYTHON_ADDED_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_added_lines_summary.csv}"

CLOC_RESULTS_OUTPUT="${CLOC_RESULTS_OUTPUT:-${CLOC_OUTPUT_DIR}/python_ncloc_cloc_snapshot_results.csv}"
CLOC_ISSUES_OUTPUT="${CLOC_ISSUES_OUTPUT:-${CLOC_OUTPUT_DIR}/python_ncloc_cloc_issues.csv}"
CLOC_FILE_COUNT_AUDIT_OUTPUT="${CLOC_FILE_COUNT_AUDIT_OUTPUT:-${CLOC_OUTPUT_DIR}/python_ncloc_cloc_file_count_audit.csv}"
CLOC_QC_OUTPUT="${CLOC_QC_OUTPUT:-${CLOC_OUTPUT_DIR}/python_ncloc_cloc_qc.csv}"
CLOC_SUMMARY_OUTPUT="${CLOC_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_ncloc_cloc_summary.csv}"

COMBINED_PANEL_OUTPUT="${COMBINED_PANEL_OUTPUT:-${PANEL_OUTPUT_DIR}/velocity_did_panel_python_added_lines_combined.csv}"
SONARQUBE_PANEL_OUTPUT="${SONARQUBE_PANEL_OUTPUT:-${PANEL_OUTPUT_DIR}/velocity_did_panel_python_added_lines_sonarqube.csv}"
CLOC_PANEL_OUTPUT="${CLOC_PANEL_OUTPUT:-${PANEL_OUTPUT_DIR}/velocity_did_panel_python_added_lines_cloc.csv}"
COMMON_SAMPLE_OUTPUT="${COMMON_SAMPLE_OUTPUT:-${PANEL_OUTPUT_DIR}/velocity_did_panel_python_added_lines_common_sample.csv}"
SNAPSHOT_COMPARISON_OUTPUT="${SNAPSHOT_COMPARISON_OUTPUT:-${PANEL_OUTPUT_DIR}/python_ncloc_snapshot_backend_comparison.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${PANEL_OUTPUT_DIR}/python_added_lines_panel_unresolved.csv}"
PANEL_QC_OUTPUT="${PANEL_QC_OUTPUT:-${PANEL_OUTPUT_DIR}/python_added_lines_panel_qc.csv}"
PANEL_SUMMARY_OUTPUT="${PANEL_SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_added_lines_panel_summary.csv}"

ANALYSIS_TIMEZONE="${ANALYSIS_TIMEZONE:-America/Chicago}"
HISTORY_REF="${HISTORY_REF:-HEAD}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
CLOC_TIMEOUT_SECONDS="${CLOC_TIMEOUT_SECONDS:-300}"
START_REPO_ORDER="${START_REPO_ORDER:-1}"
LIMIT_REPOS="${LIMIT_REPOS:-0}"
START_SNAPSHOT_ORDER="${START_SNAPSHOT_ORDER:-1}"
LIMIT_SNAPSHOTS="${LIMIT_SNAPSHOTS:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
KEEP_CLOC_TEMP="${KEEP_CLOC_TEMP:-0}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
PROGRESS_EVERY_REPOS="${PROGRESS_EVERY_REPOS:-5}"
PROGRESS_EVERY_COMMITS="${PROGRESS_EVERY_COMMITS:-250}"
PROGRESS_EVERY_SNAPSHOTS="${PROGRESS_EVERY_SNAPSHOTS:-25}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-914}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-1040}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-706}"

PARTIAL_RUN=0
if [[ "${START_REPO_ORDER}" != "1" || "${LIMIT_REPOS}" != "0" || \
      "${START_SNAPSHOT_ORDER}" != "1" || "${LIMIT_SNAPSHOTS}" != "0" || \
      -n "${DATASET_SOURCE}" || -n "${REPO_NAME}" ]]; then
  PARTIAL_RUN=1
fi

for boolean_name in \
  ANALYSIS_AGAIN \
  STRICT_EXPECTED_COUNTS \
  KEEP_CLOC_TEMP \
  SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${GIT_TIMEOUT_SECONDS}" \
  "${CLOC_TIMEOUT_SECONDS}" \
  "${START_REPO_ORDER}" \
  "${LIMIT_REPOS}" \
  "${START_SNAPSHOT_ORDER}" \
  "${LIMIT_SNAPSHOTS}" \
  "${PROGRESS_EVERY_REPOS}" \
  "${PROGRESS_EVERY_COMMITS}" \
  "${PROGRESS_EVERY_SNAPSHOTS}" \
  "${EXPECTED_PANEL_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_ROWS}" \
  "${EXPECTED_CONTROL_ROWS}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${START_REPO_ORDER}" -lt 1 || "${START_SNAPSHOT_ORDER}" -lt 1 ]]; then
  echo "ERROR: start-order values must be at least 1." >&2
  exit 1
fi

if [[ -n "${DATASET_SOURCE}" && "${DATASET_SOURCE}" != "treatment" && "${DATASET_SOURCE}" != "control" ]]; then
  echo "ERROR: DATASET_SOURCE must be treatment, control, or empty." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

for required_script in "${COLLECTOR_SCRIPT}" "${CLOC_SCRIPT}" "${PANEL_SCRIPT}"; do
  if [[ ! -f "${required_script}" ]]; then
    echo "ERROR: required analysis program not found: ${required_script}" >&2
    exit 1
  fi
done

if ! "${PYTHON_BIN}" -c 'import numpy, pandas; from zoneinfo import ZoneInfo; ZoneInfo("America/Chicago")' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy, pandas, and timezone data." >&2
  exit 1
fi

mkdir -p \
  "${LOG_DIR}" \
  "${MAIN_OUTPUT_DIR}" \
  "${TMP_OUTPUT_DIR}" \
  "${ADDED_OUTPUT_DIR}" \
  "${CLOC_OUTPUT_DIR}" \
  "${PANEL_OUTPUT_DIR}" \
  "${LEGACY_PANEL_DIR}" \
  "${CACHE_DIR}" \
  "${CLOC_TEMP_ROOT}"

# Move legacy top-level Python-NCLOC-only panels away from current b02 outputs.
for legacy_name in \
  velocity_did_panel_python_ncloc_sonarqube.csv \
  velocity_did_panel_python_ncloc_cloc.csv; do
  legacy_source="${MAIN_OUTPUT_DIR}/${legacy_name}"
  legacy_target="${LEGACY_PANEL_DIR}/${legacy_name}"
  if [[ -f "${legacy_source}" && ! -e "${legacy_target}" ]]; then
    mv "${legacy_source}" "${legacy_target}"
  fi
done

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
COLLECTOR_SHA256="$(sha256sum "${COLLECTOR_SCRIPT}" | awk '{print $1}')"
CLOC_SCRIPT_SHA256="$(sha256sum "${CLOC_SCRIPT}" | awk '{print $1}')"
PANEL_SCRIPT_SHA256="$(sha256sum "${PANEL_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare Python added-lines DiD panels"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "cloc:                            ${CLOC_BIN}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Added-lines collector:           ${COLLECTOR_SCRIPT}"
  echo "Collector SHA256:                ${COLLECTOR_SHA256}"
  echo "cloc analysis program:           ${CLOC_SCRIPT}"
  echo "cloc program SHA256:             ${CLOC_SCRIPT_SHA256}"
  echo "Panel builder:                   ${PANEL_SCRIPT}"
  echo "Panel builder SHA256:            ${PANEL_SCRIPT_SHA256}"
  echo "Base Model A panel:              ${BASE_PANEL_FILE}"
  echo "Snapshot manifest:               ${SNAPSHOT_MANIFEST_FILE}"
  echo "Existing SonarQube results:      ${SONARQUBE_RESULTS_FILE}"
  echo "Primary raw outcome:             lines_added_py_source"
  echo "Primary transformed outcome:     log_lines_added_py_source"
  echo "Robustness raw outcomes:          lines_added_py_no_merge; lines_added_py_source_no_tests; lines_added_py_all"
  echo "Legacy aliases:                   lines_added_py=lines_added_py_all; log_lines_added_py=log_lines_added_py_all"
  echo "Analysis timezone:               ${ANALYSIS_TIMEZONE}"
  echo "History ref:                     ${HISTORY_REF}"
  echo "History tip policy:              resolve once to frozen SHA per repository"
  echo "Model A reconciliation:          warning-only reference drift audit"
  echo "Merge policy:                    broad includes first-parent merge diff; cleaned outcomes exclude merges"
  echo "Source policy:                   exclude vendor/generated; tests retained in primary"
  echo "Repository selection:            start=${START_REPO_ORDER}; limit=${LIMIT_REPOS}; source=${DATASET_SOURCE:-all}; repo=${REPO_NAME:-all}"
  echo "Snapshot selection:              start=${START_SNAPSHOT_ORDER}; limit=${LIMIT_SNAPSHOTS}"
  echo "Partial run:                     ${PARTIAL_RUN}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Analysis again:                  ${ANALYSIS_AGAIN}"
  echo "Self-test only:                  ${SELF_TEST_ONLY}"
  echo "Python added-lines output:       ${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  echo "cloc snapshot output:            ${CLOC_RESULTS_OUTPUT}"
  echo "cloc file-count audit:           ${CLOC_FILE_COUNT_AUDIT_OUTPUT}"
  echo "SonarQube DiD panel:             ${SONARQUBE_PANEL_OUTPUT}"
  echo "cloc DiD panel:                  ${CLOC_PANEL_OUTPUT}"
  echo "Common sample:                   ${COMMON_SAMPLE_OUTPUT}"
  echo "Panel QC:                        ${PANEL_QC_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

run_command_logged() {
  local step_title="$1"
  shift
  local -a command=("$@")
  {
    echo
    echo "** ${step_title}"
    echo "------------------------------------------------------------"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"
  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

run_command_logged \
  "Step 1: Validate Python added-lines implementation" \
  "${PYTHON_BIN}" "${COLLECTOR_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Validate cloc NCLOC implementation" \
  "${PYTHON_BIN}" "${CLOC_SCRIPT}" --self-test

run_command_logged \
  "Step 3: Compile panel builder" \
  "${PYTHON_BIN}" -m py_compile "${PANEL_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v "${CLOC_BIN}" >/dev/null 2>&1; then
  echo "ERROR: cloc is required but was not found: ${CLOC_BIN}" >&2
  exit 1
fi

for required_input in \
  "${BASE_PANEL_FILE}" \
  "${SNAPSHOT_MANIFEST_FILE}" \
  "${SONARQUBE_RESULTS_FILE}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" >&2
    exit 1
  fi
done

COLLECT_COMMAND=(
  "${PYTHON_BIN}"
  "${COLLECTOR_SCRIPT}"
  --panel-file "${BASE_PANEL_FILE}"
  --repo-month-output "${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  --commit-output "${PYTHON_ADDED_COMMIT_OUTPUT}"
  --file-output "${PYTHON_ADDED_FILE_OUTPUT}"
  --issues-output "${PYTHON_ADDED_ISSUES_OUTPUT}"
  --reconciliation-output "${PYTHON_ADDED_RECONCILIATION_OUTPUT}"
  --qc-output "${PYTHON_ADDED_QC_OUTPUT}"
  --summary-output "${PYTHON_ADDED_SUMMARY_OUTPUT}"
  --cache-dir "${CACHE_DIR}"
  --analysis-timezone "${ANALYSIS_TIMEZONE}"
  --history-ref "${HISTORY_REF}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --start-repo-order "${START_REPO_ORDER}"
  --limit-repos "${LIMIT_REPOS}"
  --dataset-source "${DATASET_SOURCE}"
  --repo-name "${REPO_NAME}"
  --progress-every-repos "${PROGRESS_EVERY_REPOS}"
  --progress-every-commits "${PROGRESS_EVERY_COMMITS}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}"
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  COLLECT_COMMAND+=(--analysis-again)
fi
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COLLECT_COMMAND+=(--strict-expected-counts)
fi
run_command_logged "Step 4: Collect monthly Python added lines" "${COLLECT_COMMAND[@]}"

CLOC_COMMAND=(
  "${PYTHON_BIN}"
  "${CLOC_SCRIPT}"
  --input-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --snapshot-results-output "${CLOC_RESULTS_OUTPUT}"
  --issues-output "${CLOC_ISSUES_OUTPUT}"
  --file-count-audit-output "${CLOC_FILE_COUNT_AUDIT_OUTPUT}"
  --qc-output "${CLOC_QC_OUTPUT}"
  --summary-output "${CLOC_SUMMARY_OUTPUT}"
  --cloc-bin "${CLOC_BIN}"
  --cloc-temp-root "${CLOC_TEMP_ROOT}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --cloc-timeout-seconds "${CLOC_TIMEOUT_SECONDS}"
  --start-order "${START_SNAPSHOT_ORDER}"
  --limit "${LIMIT_SNAPSHOTS}"
  --dataset-source "${DATASET_SOURCE}"
  --repo-name "${REPO_NAME}"
  --progress-every "${PROGRESS_EVERY_SNAPSHOTS}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --log-level "${LOG_LEVEL}"
)
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  CLOC_COMMAND+=(--analysis-again)
fi
if [[ "${KEEP_CLOC_TEMP}" == "1" ]]; then
  CLOC_COMMAND+=(--keep-cloc-temp)
fi
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  CLOC_COMMAND+=(--strict-expected-counts)
fi
run_command_logged "Step 5: Recompute Python-only NCLOC with cloc" "${CLOC_COMMAND[@]}"

PANEL_COMMAND=(
  "${PYTHON_BIN}"
  "${PANEL_SCRIPT}"
  --base-panel-file "${BASE_PANEL_FILE}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --python-added-lines-file "${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  --cloc-results-file "${CLOC_RESULTS_OUTPUT}"
  --sonarqube-results-file "${SONARQUBE_RESULTS_FILE}"
  --combined-panel-output "${COMBINED_PANEL_OUTPUT}"
  --sonarqube-panel-output "${SONARQUBE_PANEL_OUTPUT}"
  --cloc-panel-output "${CLOC_PANEL_OUTPUT}"
  --common-sample-output "${COMMON_SAMPLE_OUTPUT}"
  --snapshot-comparison-output "${SNAPSHOT_COMPARISON_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --qc-output "${PANEL_QC_OUTPUT}"
  --summary-output "${PANEL_SUMMARY_OUTPUT}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  PANEL_COMMAND+=(--strict-expected-counts)
fi
if [[ "${PARTIAL_RUN}" == "1" ]]; then
  PANEL_COMMAND+=(--partial-run)
fi
run_command_logged "Step 6: Build same-sample backend DiD panels" "${PANEL_COMMAND[@]}"

EXPECTED_OUTPUTS=(
  "${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  "${PYTHON_ADDED_COMMIT_OUTPUT}"
  "${PYTHON_ADDED_FILE_OUTPUT}"
  "${PYTHON_ADDED_ISSUES_OUTPUT}"
  "${PYTHON_ADDED_RECONCILIATION_OUTPUT}"
  "${PYTHON_ADDED_QC_OUTPUT}"
  "${PYTHON_ADDED_SUMMARY_OUTPUT}"
  "${CLOC_RESULTS_OUTPUT}"
  "${CLOC_ISSUES_OUTPUT}"
  "${CLOC_FILE_COUNT_AUDIT_OUTPUT}"
  "${CLOC_QC_OUTPUT}"
  "${CLOC_SUMMARY_OUTPUT}"
  "${COMBINED_PANEL_OUTPUT}"
  "${SONARQUBE_PANEL_OUTPUT}"
  "${CLOC_PANEL_OUTPUT}"
  "${COMMON_SAMPLE_OUTPUT}"
  "${SNAPSHOT_COMPARISON_OUTPUT}"
  "${UNRESOLVED_OUTPUT}"
  "${PANEL_QC_OUTPUT}"
  "${PANEL_SUMMARY_OUTPUT}"
)

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 7: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${PYTHON_ADDED_REPO_MONTH_OUTPUT}" \
    "${PYTHON_ADDED_COMMIT_OUTPUT}" \
    "${PYTHON_ADDED_FILE_OUTPUT}" \
    "${PYTHON_ADDED_RECONCILIATION_OUTPUT}" \
    "${CLOC_RESULTS_OUTPUT}" \
    "${CLOC_FILE_COUNT_AUDIT_OUTPUT}" \
    "${SONARQUBE_PANEL_OUTPUT}" \
    "${CLOC_PANEL_OUTPUT}" \
    "${COMMON_SAMPLE_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}"
  echo
  echo "Python added-lines QC:"
  cat "${PYTHON_ADDED_QC_OUTPUT}"
  echo
  echo "cloc QC:"
  cat "${CLOC_QC_OUTPUT}"
  echo
  echo "cloc file-count audit preview:"
  head -n 11 "${CLOC_FILE_COUNT_AUDIT_OUTPUT}"
  echo
  echo "Panel QC:"
  cat "${PANEL_QC_OUTPUT}"
  echo
  echo "Python added-lines preview:"
  head -n 11 "${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Python added-lines:              ${PYTHON_ADDED_REPO_MONTH_OUTPUT}"
  echo "New cloc NCLOC:                  ${CLOC_RESULTS_OUTPUT}"
  echo "cloc file-count audit:           ${CLOC_FILE_COUNT_AUDIT_OUTPUT}"
  echo "SonarQube DiD panel:             ${SONARQUBE_PANEL_OUTPUT}"
  echo "cloc DiD panel:                  ${CLOC_PANEL_OUTPUT}"
  echo "Common sample:                   ${COMMON_SAMPLE_OUTPUT}"
  echo "Unresolved audit:                ${UNRESOLVED_OUTPUT}"
  echo "Panel QC:                        ${PANEL_QC_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       update run-x-b03 for four Python velocity outcomes with log_lines_added_py_source primary"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
