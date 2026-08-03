#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b01 v4: Compute Python-only NCLOC with AST and cloc
# ============================================================
#
# Purpose:
#   Compute two fast Python-only NCLOC values per historical
#   repository-commit snapshot for Model C.
#
# Method 1 -- primary AST/tokenize metric:
#   Count tracked Python physical lines after excluding:
#     - blank lines;
#     - comment-only lines; and
#     - bare constant-string expression statements.
#
#   Preserve strings that participate in assignments, returns, calls,
#   collections, formatting, or other executable expressions.
#
# Method 2 -- robustness cloc metric:
#   Run cloc in default Python mode over the exact same materialized
#   tracked-Python file set. The --skip-uniqueness option ensures that
#   different tracked paths with identical contents are all counted.
#
# Diagnostic reference:
#   Preserve prior SonarQube results for comparison only. SonarQube is
#   not used as a Model C input in this version.
#
# Git implementation:
#   - git ls-tree lists tracked .py blobs at the requested commit;
#   - git cat-file --batch reads blob contents;
#   - the main clone checkout is never changed.
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#
# Full run:
#   bash proc_sh_x01/run-x-b01-compute-ncloc-py.sh
#
# Structural dry run:
#   DRY_RUN=1 bash proc_sh_x01/run-x-b01-compute-ncloc-py.sh
#
# One-snapshot comparison smoke test:
#   LIMIT=1 bash proc_sh_x01/run-x-b01-compute-ncloc-py.sh
#
# Resume:
#   Re-run the same command. Snapshots with both AST and cloc success
#   are skipped unless ANALYSIS_AGAIN=1.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   CLOC_BIN=/path/to/cloc
#   START_ORDER=1
#   LIMIT=0
#   DATASET_SOURCE=treatment|control
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=0
#   STRICT_EXPECTED_COUNTS=1
#   SKIP_SELF_TEST=0
#   KEEP_CLOC_TEMP=0
#   GIT_TIMEOUT_SECONDS=300
#   CLOC_TIMEOUT_SECONDS=300
#   PROGRESS_EVERY=25
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b01"
IMPLEMENTATION_VERSION="v4"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-compute-ncloc-py-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
CLOC_BIN="${CLOC_BIN:-cloc}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/compute_ncloc_python.py}"
INPUT_MANIFEST_FILE="${INPUT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
CLOC_TEMP_ROOT="${CLOC_TEMP_ROOT:-${TMP_OUTPUT_DIR}/cloc-work}"

SNAPSHOT_MANIFEST_OUTPUT="${SNAPSHOT_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_snapshot_manifest.csv}"
SNAPSHOT_RESULTS_OUTPUT="${SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_snapshot_results.csv}"
COMPLETED_MANIFEST_OUTPUT="${COMPLETED_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_completed_manifest.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_unresolved.csv}"
SCAN_QC_OUTPUT="${SCAN_QC_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_scan_qc.csv}"
FILE_ISSUES_OUTPUT="${FILE_ISSUES_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_file_issues.csv}"
SONARQUBE_REFERENCE_FILE="${SONARQUBE_REFERENCE_FILE:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_snapshot_results_sonarqube.csv}"
BACKEND_COMPARISON_OUTPUT="${BACKEND_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_backend_comparison.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/model_c_ncloc_py_summary.csv}"

GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
CLOC_TIMEOUT_SECONDS="${CLOC_TIMEOUT_SECONDS:-300}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SKIP_SELF_TEST="${SKIP_SELF_TEST:-0}"
KEEP_CLOC_TEMP="${KEEP_CLOC_TEMP:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-706}"
EXPECTED_REPO_MONTH_ROWS="${EXPECTED_REPO_MONTH_ROWS:-1954}"
EXPECTED_TREATMENT_REPO_MONTH_ROWS="${EXPECTED_TREATMENT_REPO_MONTH_ROWS:-914}"
EXPECTED_CONTROL_REPO_MONTH_ROWS="${EXPECTED_CONTROL_REPO_MONTH_ROWS:-1040}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"

for numeric_value in \
  "${GIT_TIMEOUT_SECONDS}" \
  "${CLOC_TIMEOUT_SECONDS}" \
  "${PROGRESS_EVERY}" \
  "${START_ORDER}" \
  "${LIMIT}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPO_MONTH_ROWS}" \
  "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}" \
  "${EXPECTED_CONTROL_REPO_MONTH_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${START_ORDER}" -lt 1 ]]; then
  echo "ERROR: START_ORDER must be at least 1." >&2
  exit 1
fi

for boolean_name in \
  ANALYSIS_AGAIN \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  STRICT_EXPECTED_COUNTS \
  SKIP_SELF_TEST \
  KEEP_CLOC_TEMP; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ -n "${DATASET_SOURCE}" && "${DATASET_SOURCE}" != "treatment" && "${DATASET_SOURCE}" != "control" ]]; then
  echo "ERROR: DATASET_SOURCE must be treatment, control, or empty." >&2
  exit 1
fi

for required_file in "${PY_SCRIPT}" "${INPUT_MANIFEST_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v "${CLOC_BIN}" >/dev/null 2>&1; then
  echo "ERROR: cloc is required but was not found: ${CLOC_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${CLOC_TEMP_ROOT}"

# Preserve old output schemas before v4 starts writing to the active paths.
MIGRATION_NOTE="none"
if [[ -f "${SNAPSHOT_RESULTS_OUTPUT}" && -s "${SNAPSHOT_RESULTS_OUTPUT}" ]]; then
  HEADER_LINE="$(head -n 1 "${SNAPSHOT_RESULTS_OUTPUT}")"
  if [[ "${HEADER_LINE}" == *"scanner_return_code"* && "${HEADER_LINE}" != *"count_backend"* ]]; then
    if [[ ! -f "${SONARQUBE_REFERENCE_FILE}" ]]; then
      mv "${SNAPSHOT_RESULTS_OUTPUT}" "${SONARQUBE_REFERENCE_FILE}"
      MIGRATION_NOTE="moved legacy SonarQube results to ${SONARQUBE_REFERENCE_FILE}"
    else
      LEGACY_SONAR_BACKUP="${SONARQUBE_REFERENCE_FILE%.csv}-${RUN_TS}.csv"
      mv "${SNAPSHOT_RESULTS_OUTPUT}" "${LEGACY_SONAR_BACKUP}"
      MIGRATION_NOTE="moved additional SonarQube results to ${LEGACY_SONAR_BACKUP}"
    fi
  elif [[ "${HEADER_LINE}" == *"count_backend"* && "${HEADER_LINE}" != *"ncloc_py_ast"* ]]; then
    V2_BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-v2-backup-${RUN_TS}"
    mkdir -p "${V2_BACKUP_DIR}"
    for old_output in \
      "${SNAPSHOT_MANIFEST_OUTPUT}" \
      "${SNAPSHOT_RESULTS_OUTPUT}" \
      "${COMPLETED_MANIFEST_OUTPUT}" \
      "${UNRESOLVED_OUTPUT}" \
      "${FILE_ISSUES_OUTPUT}" \
      "${BACKEND_COMPARISON_OUTPUT}" \
      "${SCAN_QC_OUTPUT}"; do
      if [[ -f "${old_output}" ]]; then
        mv "${old_output}" "${V2_BACKUP_DIR}/$(basename "${old_output}")"
      fi
    done
    if [[ -f "${SUMMARY_OUTPUT}" ]]; then
      mv "${SUMMARY_OUTPUT}" "${V2_BACKUP_DIR}/$(basename "${SUMMARY_OUTPUT}")"
    fi
    MIGRATION_NOTE="moved local-Git v2 outputs to ${V2_BACKUP_DIR}"
  elif [[ "${HEADER_LINE}" == *"ncloc_py_ast"* ]] && grep -q ',v3,' "${SNAPSHOT_RESULTS_OUTPUT}"; then
    V3_BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-v3-backup-${RUN_TS}"
    mkdir -p "${V3_BACKUP_DIR}"
    for old_output in \
      "${SNAPSHOT_MANIFEST_OUTPUT}" \
      "${SNAPSHOT_RESULTS_OUTPUT}" \
      "${COMPLETED_MANIFEST_OUTPUT}" \
      "${UNRESOLVED_OUTPUT}" \
      "${FILE_ISSUES_OUTPUT}" \
      "${BACKEND_COMPARISON_OUTPUT}" \
      "${SCAN_QC_OUTPUT}"; do
      if [[ -f "${old_output}" ]]; then
        mv "${old_output}" "${V3_BACKUP_DIR}/$(basename "${old_output}")"
      fi
    done
    if [[ -f "${SUMMARY_OUTPUT}" ]]; then
      mv "${SUMMARY_OUTPUT}" "${V3_BACKUP_DIR}/$(basename "${SUMMARY_OUTPUT}")"
    fi
    MIGRATION_NOTE="moved local AST+cloc v3 outputs to ${V3_BACKUP_DIR}"
  elif [[ "${HEADER_LINE}" != *"ncloc_py_ast"* ]]; then
    echo "ERROR: unrecognized active snapshot-result schema: ${SNAPSHOT_RESULTS_OUTPUT}" >&2
    exit 1
  fi
fi

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
CLOC_VERSION="$("${CLOC_BIN}" --version 2>&1 | head -n 1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_MANIFEST_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: compute Python-only NCLOC with AST and cloc"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "cloc:                            ${CLOC_BIN} (${CLOC_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "SonarQube backup shell:           proc_sh_x01/run-x-b01-compute-ncloc-py-sonarqube.sh"
  echo "SonarQube backup Python:          proc_script_x01/compute_ncloc_python-sonarqube.py"
  echo "Input manifest:                  ${INPUT_MANIFEST_FILE}"
  echo "Input SHA256:                    ${INPUT_SHA256}"
  echo "Snapshot manifest output:        ${SNAPSHOT_MANIFEST_OUTPUT}"
  echo "Snapshot results output:         ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Completed manifest output:       ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "File issues output:              ${FILE_ISSUES_OUTPUT}"
  echo "Scan QC output:                  ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "SonarQube reference:             ${SONARQUBE_REFERENCE_FILE}"
  echo "Backend comparison:              ${BACKEND_COMPARISON_OUTPUT}"
  echo "Old-output migration:            ${MIGRATION_NOTE}"
  echo "Count backend:                   local_git_ast_tokenize_and_cloc"
  echo "Primary metric:                  ncloc_py_ast"
  echo "Robustness metric:               ncloc_py_cloc"
  echo "SonarQube role:                  diagnostic reference only"
  echo "Git file listing:                git ls-tree"
  echo "Git blob reader:                 git cat-file --batch"
  echo "Checkout/worktree creation:      none"
  echo "AST string policy:               exclude bare constant-string expressions"
  echo "cloc policy:                     default Python mode, same files, skip uniqueness"
  echo "cloc temporary root:             ${CLOC_TEMP_ROOT}"
  echo "Keep cloc temporary files:       ${KEEP_CLOC_TEMP}"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "cloc timeout seconds:            ${CLOC_TIMEOUT_SECONDS}"
  echo "Progress every:                  ${PROGRESS_EVERY}"
  echo "Start order:                     ${START_ORDER}"
  echo "Limit:                           ${LIMIT}"
  echo "Dataset-source filter:           ${DATASET_SOURCE:-<all>}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Analysis again:                  ${ANALYSIS_AGAIN}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Skip internal self-test:         ${SKIP_SELF_TEST}"
  echo "Expected snapshots:              ${EXPECTED_SNAPSHOTS}"
  echo "Expected treatment/control:      ${EXPECTED_TREATMENT_SNAPSHOTS}/${EXPECTED_CONTROL_SNAPSHOTS}"
  echo "Expected repo-month coverage:    ${EXPECTED_REPO_MONTH_ROWS}"
  echo "Expected repositories:           ${EXPECTED_REPOSITORIES}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --input-manifest-file "${INPUT_MANIFEST_FILE}"
  --snapshot-manifest-output "${SNAPSHOT_MANIFEST_OUTPUT}"
  --snapshot-results-output "${SNAPSHOT_RESULTS_OUTPUT}"
  --completed-manifest-output "${COMPLETED_MANIFEST_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --scan-qc-output "${SCAN_QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --file-issues-output "${FILE_ISSUES_OUTPUT}"
  --sonarqube-reference-file "${SONARQUBE_REFERENCE_FILE}"
  --backend-comparison-output "${BACKEND_COMPARISON_OUTPUT}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --cloc-bin "${CLOC_BIN}"
  --cloc-timeout-seconds "${CLOC_TIMEOUT_SECONDS}"
  --cloc-temp-root "${CLOC_TEMP_ROOT}"
  --progress-every "${PROGRESS_EVERY}"
  --start-order "${START_ORDER}"
  --limit "${LIMIT}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --expected-repo-month-rows "${EXPECTED_REPO_MONTH_ROWS}"
  --expected-treatment-repo-month-rows "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}"
  --expected-control-repo-month-rows "${EXPECTED_CONTROL_REPO_MONTH_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)

if [[ -n "${DATASET_SOURCE}" ]]; then
  COMMAND+=(--dataset-source "${DATASET_SOURCE}")
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  COMMAND+=(--analysis-again)
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi
if [[ "${SKIP_SELF_TEST}" == "1" ]]; then
  COMMAND+=(--skip-self-test)
fi
if [[ "${KEEP_CLOC_TEMP}" == "1" ]]; then
  COMMAND+=(--keep-cloc-temp)
fi

{
  echo
  echo "** Step 1: Compute AST/tokenize and cloc Python-only NCLOC"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${SNAPSHOT_MANIFEST_OUTPUT}" \
  "${SNAPSHOT_RESULTS_OUTPUT}" \
  "${COMPLETED_MANIFEST_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${FILE_ISSUES_OUTPUT}" \
  "${BACKEND_COMPARISON_OUTPUT}" \
  "${SCAN_QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SNAPSHOT_MANIFEST_OUTPUT}" \
    "${SNAPSHOT_RESULTS_OUTPUT}" \
    "${COMPLETED_MANIFEST_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${FILE_ISSUES_OUTPUT}" \
    "${BACKEND_COMPARISON_OUTPUT}" \
    "${SCAN_QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${SCAN_QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "AST/cloc/Sonar comparison preview:"
  head -n 11 "${BACKEND_COMPARISON_OUTPUT}"
  echo
  echo "File-issue preview:"
  head -n 11 "${FILE_ISSUES_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Completed manifest:              ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "File issues:                     ${FILE_ISSUES_OUTPUT}"
  echo "Backend comparison:              ${BACKEND_COMPARISON_OUTPUT}"
  echo "QC output:                       ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       run LIMIT=1 and compare AST, cloc, and Sonar diagnostics"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
