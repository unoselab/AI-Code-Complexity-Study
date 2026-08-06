#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-d01b v2: Resolve Python 3.13 and malformed-source cases
# ============================================================
#
# Purpose:
#   Resolve only the file occurrences still unresolved after run-x-d01a.
#   The implementation is independent of the run-x-d01a shell wrapper and
#   does not overwrite run-x-d01 or run-x-d01a outputs.
#
# Recovery order:
#   1. Parse the original historical blob with Python 3.12 AST.
#   2. If Python 3.12 fails, parse the same unmodified blob with Python 3.13.
#   3. If both exact parsers fail for the reviewed HAL blob, use its approved
#      diagnostic mask while calculating all hashes and tokens from the
#      original historical source.
#   4. Record the manually reviewed TradeMind blob as an explicit malformed-
#      source exclusion; do not keep it as unclassified unresolved input.
#
# Production policy:
#   Python 3.13 exact recovery is applied automatically because the original
#   source is not modified. The reviewed HAL diagnostic has been approved and
#   is production-applied by default in v2. TradeMind remains metric-unavailable
#   but is finalized as an explicit manual-review exclusion.
#
# Inputs:
#   repo_x02/run-x-d01/model_c_token_py_snapshot_manifest.csv
#   repo_x02/run-x-d01a/model_c_token_py_snapshot_results_resolved.csv
#   repo_x02/run-x-d01a/model_c_token_py_snapshot_corrections.csv
#   repo_x02/run-x-d01a/model_c_token_py_unresolved_after_d01a.csv
#
# Outputs:
#   repo_x02/run-x-d01b/model_c_token_py_blob_resolution_review.csv
#   repo_x02/run-x-d01b/model_c_token_py_recovered_function_details.csv
#   repo_x02/run-x-d01b/model_c_token_py_file_resolutions.csv
#   repo_x02/run-x-d01b/model_c_token_py_snapshot_corrections.csv
#   repo_x02/run-x-d01b/model_c_token_py_snapshot_results_resolved.csv
#   repo_x02/run-x-d01b/model_c_token_py_resolution_decisions.csv
#   repo_x02/run-x-d01b/model_c_token_py_unresolved_after_d01b.csv
#   repo_x02/run-x-d01b/model_c_token_py_excluded_after_manual_review.csv
#   repo_x02/run-x-d01b/model_c_token_py_resolution_qc.csv
#   repo_x02/tmp/run-x-d01b/model_c_token_py_resolution_summary.csv
#
# Full diagnostic-first run:
#   bash proc_sh_x02/run-x-d01b-resolve-python313-and-malformed.sh
#
# One-blob smoke test:
#   LIMIT=1 bash proc_sh_x02/run-x-d01b-resolve-python313-and-malformed.sh
#
# Final approved run (HAL correction is enabled by default):
#   bash proc_sh_x02/run-x-d01b-resolve-python313-and-malformed.sh
#
# Diagnostic-only override that does not apply the HAL correction:
#   APPLY_REVIEWED_MALFORMED=0 FAIL_ON_UNRESOLVED=0 \
#     bash proc_sh_x02/run-x-d01b-resolve-python313-and-malformed.sh
#
# Optional overrides:
#   PYTHON_BIN=python
#   PYTHON312_BIN=/home/user1-system12/miniconda3/envs/agcparse312/bin/python
#   PYTHON313_BIN=/home/user1-system12/miniconda3/envs/agcparse313/bin/python
#   BODY_STORE_ROOT=/absolute/path/to/py-fun-body
#   BODY_SAVE_SCOPE=all|qualifying
#   APPLY_REVIEWED_MALFORMED=0|1  # default: 1
#   REPO_NAME=owner/repository
#   BLOB_OID=<40-character-oid>
#   LIMIT=0
#   DRY_RUN=0|1
#   FAIL_ON_UNRESOLVED=0|1        # default: 1
#   SKIP_SELF_TEST=0|1
#   GIT_TIMEOUT_SECONDS=300
#   WORKER_TIMEOUT_SECONDS=600
#   WORKER_BATCH_BYTES=20000000
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d01b"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-resolve-python313-and-malformed-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON312_BIN="${PYTHON312_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON313_BIN="${PYTHON313_BIN:-/home/user1-system12/miniconda3/envs/agcparse313/bin/python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x02/resolve_token_py_python313_and_malformed.py}"

D01_DIR="${D01_DIR:-repo_x02/run-x-d01}"
D01A_DIR="${D01A_DIR:-repo_x02/run-x-d01a}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-${D01_DIR}/model_c_token_py_snapshot_manifest.csv}"
D01A_SNAPSHOT_RESULTS_FILE="${D01A_SNAPSHOT_RESULTS_FILE:-${D01A_DIR}/model_c_token_py_snapshot_results_resolved.csv}"
D01A_SNAPSHOT_CORRECTIONS_FILE="${D01A_SNAPSHOT_CORRECTIONS_FILE:-${D01A_DIR}/model_c_token_py_snapshot_corrections.csv}"
D01A_UNRESOLVED_FILE="${D01A_UNRESOLVED_FILE:-${D01A_DIR}/model_c_token_py_unresolved_after_d01a.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

BLOB_REVIEW_OUTPUT="${BLOB_REVIEW_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_blob_resolution_review.csv}"
RECOVERED_FUNCTION_DETAILS_OUTPUT="${RECOVERED_FUNCTION_DETAILS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_recovered_function_details.csv}"
FILE_RESOLUTION_OUTPUT="${FILE_RESOLUTION_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_file_resolutions.csv}"
SNAPSHOT_CORRECTIONS_OUTPUT="${SNAPSHOT_CORRECTIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_corrections.csv}"
RESOLVED_SNAPSHOT_RESULTS_OUTPUT="${RESOLVED_SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_results_resolved.csv}"
RESOLUTION_DECISIONS_OUTPUT="${RESOLUTION_DECISIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_resolution_decisions.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_unresolved_after_d01b.csv}"
EXCLUSION_OUTPUT="${EXCLUSION_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_excluded_after_manual_review.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_resolution_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/model_c_token_py_resolution_summary.csv}"

BODY_STORE_ROOT="${BODY_STORE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/py-fun-body}"
BODY_SAVE_SCOPE="${BODY_SAVE_SCOPE:-all}"
APPLY_REVIEWED_MALFORMED="${APPLY_REVIEWED_MALFORMED:-1}"
REPO_NAME="${REPO_NAME:-}"
BLOB_OID="${BLOB_OID:-}"
LIMIT="${LIMIT:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-1}"
SKIP_SELF_TEST="${SKIP_SELF_TEST:-0}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
WORKER_TIMEOUT_SECONDS="${WORKER_TIMEOUT_SECONDS:-600}"
WORKER_BATCH_BYTES="${WORKER_BATCH_BYTES:-20000000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for numeric_value in \
  "${LIMIT}" \
  "${GIT_TIMEOUT_SECONDS}" \
  "${WORKER_TIMEOUT_SECONDS}" \
  "${WORKER_BATCH_BYTES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: numeric options must contain non-negative integers." >&2
    exit 1
  fi
done

for boolean_name in \
  APPLY_REVIEWED_MALFORMED \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  SKIP_SELF_TEST; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ "${BODY_SAVE_SCOPE}" != "all" && "${BODY_SAVE_SCOPE}" != "qualifying" ]]; then
  echo "ERROR: BODY_SAVE_SCOPE must be all or qualifying." >&2
  exit 1
fi

if [[ "${BODY_STORE_ROOT}" != /* ]]; then
  echo "ERROR: BODY_STORE_ROOT must be an absolute path." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${SNAPSHOT_MANIFEST_FILE}" \
  "${D01A_SNAPSHOT_RESULTS_FILE}" \
  "${D01A_SNAPSHOT_CORRECTIONS_FILE}" \
  "${D01A_UNRESOLVED_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: main Python executable was not found: ${PYTHON_BIN}" >&2
  exit 1
fi

for interpreter in "${PYTHON312_BIN}" "${PYTHON313_BIN}"; do
  if [[ ! -x "${interpreter}" ]] && ! command -v "${interpreter}" >/dev/null 2>&1; then
    echo "ERROR: AST Python executable was not found: ${interpreter}" >&2
    exit 1
  fi
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${BODY_STORE_ROOT}"

MIGRATION_NOTE="none"
if [[ -f "${BLOB_REVIEW_OUTPUT}" && -s "${BLOB_REVIEW_OUTPUT}" ]]; then
  BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-${IMPLEMENTATION_VERSION}-backup-${RUN_TS}"
  mkdir -p "${BACKUP_DIR}"
  for output_file in \
    "${BLOB_REVIEW_OUTPUT}" \
    "${RECOVERED_FUNCTION_DETAILS_OUTPUT}" \
    "${FILE_RESOLUTION_OUTPUT}" \
    "${SNAPSHOT_CORRECTIONS_OUTPUT}" \
    "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}" \
    "${RESOLUTION_DECISIONS_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${EXCLUSION_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"; do
    if [[ -f "${output_file}" ]]; then
      mv "${output_file}" "${BACKUP_DIR}/$(basename "${output_file}")"
    fi
  done
  MIGRATION_NOTE="moved previous D01b outputs to ${BACKUP_DIR}"
fi

MAIN_PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
PYTHON312_VERSION="$("${PYTHON312_BIN}" --version 2>&1 || true)"
PYTHON313_VERSION="$("${PYTHON313_BIN}" --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
UNRESOLVED_SHA256="$(sha256sum "${D01A_UNRESOLVED_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: resolve Python 3.13 and malformed-source cases"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Main Python:                     ${PYTHON_BIN} (${MAIN_PYTHON_VERSION})"
  echo "Python 3.12 AST:                 ${PYTHON312_BIN} (${PYTHON312_VERSION})"
  echo "Python 3.13 AST:                 ${PYTHON313_BIN} (${PYTHON313_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python script:                   ${PY_SCRIPT}"
  echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
  echo "Snapshot manifest:               ${SNAPSHOT_MANIFEST_FILE}"
  echo "D01a snapshot results:           ${D01A_SNAPSHOT_RESULTS_FILE}"
  echo "D01a snapshot corrections:       ${D01A_SNAPSHOT_CORRECTIONS_FILE}"
  echo "D01a unresolved:                 ${D01A_UNRESOLVED_FILE}"
  echo "D01a unresolved SHA256:          ${UNRESOLVED_SHA256}"
  echo "Body store root:                 ${BODY_STORE_ROOT}"
  echo "Body save scope:                 ${BODY_SAVE_SCOPE}"
  echo "Apply reviewed malformed:        ${APPLY_REVIEWED_MALFORMED}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Blob filter:                     ${BLOB_OID:-<all>}"
  echo "Unique-blob limit:               ${LIMIT}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Migration note:                  ${MIGRATION_NOTE}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --d01a-snapshot-results-file "${D01A_SNAPSHOT_RESULTS_FILE}"
  --d01a-snapshot-corrections-file "${D01A_SNAPSHOT_CORRECTIONS_FILE}"
  --d01a-unresolved-file "${D01A_UNRESOLVED_FILE}"
  --body-store-root "${BODY_STORE_ROOT}"
  --body-save-scope "${BODY_SAVE_SCOPE}"
  --blob-review-output "${BLOB_REVIEW_OUTPUT}"
  --recovered-function-details-output "${RECOVERED_FUNCTION_DETAILS_OUTPUT}"
  --file-resolution-output "${FILE_RESOLUTION_OUTPUT}"
  --snapshot-corrections-output "${SNAPSHOT_CORRECTIONS_OUTPUT}"
  --resolved-snapshot-results-output "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}"
  --resolution-decisions-output "${RESOLUTION_DECISIONS_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --exclusion-output "${EXCLUSION_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --python312-bin "${PYTHON312_BIN}"
  --python313-bin "${PYTHON313_BIN}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --worker-timeout-seconds "${WORKER_TIMEOUT_SECONDS}"
  --worker-batch-bytes "${WORKER_BATCH_BYTES}"
  --limit "${LIMIT}"
  --log-level "${LOG_LEVEL}"
)

if [[ "${APPLY_REVIEWED_MALFORMED}" == "1" ]]; then
  COMMAND+=(--apply-reviewed-malformed)
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ -n "${BLOB_OID}" ]]; then
  COMMAND+=(--blob-oid "${BLOB_OID}")
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi
if [[ "${SKIP_SELF_TEST}" == "1" ]]; then
  COMMAND+=(--skip-self-test)
fi

printf 'Command:' | tee -a "${LOG_FILE}"
printf ' %q' "${COMMAND[@]}" | tee -a "${LOG_FILE}"
printf '\n' | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${BLOB_REVIEW_OUTPUT}" \
  "${RECOVERED_FUNCTION_DETAILS_OUTPUT}" \
  "${FILE_RESOLUTION_OUTPUT}" \
  "${SNAPSHOT_CORRECTIONS_OUTPUT}" \
  "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}" \
  "${RESOLUTION_DECISIONS_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${EXCLUSION_OUTPUT}" \
  "${QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "QC preview:"
  head -n 30 "${QC_OUTPUT}"
  echo
  echo "Summary preview:"
  head -n 50 "${SUMMARY_OUTPUT}"
  echo
  echo "Remaining unclassified unresolved preview:"
  head -n 20 "${UNRESOLVED_OUTPUT}"
  echo
  echo "Explicit manual-review exclusion preview:"
  head -n 20 "${EXCLUSION_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Blob review:                    ${BLOB_REVIEW_OUTPUT}"
  echo "Recovered function details:     ${RECOVERED_FUNCTION_DETAILS_OUTPUT}"
  echo "File resolutions:               ${FILE_RESOLUTION_OUTPUT}"
  echo "Snapshot corrections:           ${SNAPSHOT_CORRECTIONS_OUTPUT}"
  echo "Resolved snapshot results:      ${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}"
  echo "Unresolved after D01b:          ${UNRESOLVED_OUTPUT}"
  echo "Manual-review exclusions:       ${EXCLUSION_OUTPUT}"
  echo "QC output:                      ${QC_OUTPUT}"
  echo "Summary output:                 ${SUMMARY_OUTPUT}"
  echo "Log file:                       ${LOG_FILE}"
  UNRESOLVED_COUNT="$(awk 'END { print (NR > 0 ? NR - 1 : 0) }' "${UNRESOLVED_OUTPUT}")"
  if [[ "${UNRESOLVED_COUNT}" == "0" ]]; then
    echo "Next step:                      prepare the repo-month panel with one documented snapshot exclusion"
  else
    echo "Next step:                      review remaining unclassified unresolved rows before panel preparation"
  fi
  echo "============================================================"
} | tee -a "${LOG_FILE}"
