#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2a: Create Python SonarQube scan inputs
# ============================================================
#
# Purpose:
#   Create treatment/control SonarQube scan input files from the
#   final Python matched DiD panels.
#
# Panel inputs:
#   flexible:
#     repo_python/run-py-1l/panel_event_matched_flexible.csv
#
#   strict:
#     repo_python/run-py-1l/panel_event_matched_strict.csv
#
# Full-run main outputs:
#   repo_python/run-py-2a/<variant>/treatment/data/ts_repos_monthly.csv
#   repo_python/run-py-2a/<variant>/control/data/ts_repos_monthly.csv
#
# Full-run extra outputs:
#   repo_python/tmp/run-py-2a/<variant>/months.txt
#   repo_python/tmp/run-py-2a/<variant>/treatment_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/control_repos.txt
#   repo_python/tmp/run-py-2a/<variant>/sonarqube_input_summary.csv
#
# Smoke outputs:
#   repo_python/tmp/run-py-2a/smoke/<variant>/
#
# Usage:
#   Smoke:
#     PANEL_VARIANT=flexible MAX_TREATMENT_REPOS=2 MAX_CONTROL_REPOS=2 bash run-py-2a-create-sonarqube-input.sh
#     PANEL_VARIANT=strict   MAX_TREATMENT_REPOS=2 MAX_CONTROL_REPOS=2 bash run-py-2a-create-sonarqube-input.sh
#
#   Full:
#     PANEL_VARIANT=flexible MAX_TREATMENT_REPOS=0 MAX_CONTROL_REPOS=0 bash run-py-2a-create-sonarqube-input.sh
#     PANEL_VARIANT=strict   MAX_TREATMENT_REPOS=0 MAX_CONTROL_REPOS=0 bash run-py-2a-create-sonarqube-input.sh
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_sonarqube_input.py}"
HISTORY_SCRIPT="${HISTORY_SCRIPT:-proc_scripts/create_tmp_repo_timeseries_history.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

DID_DIR="${DID_DIR:-${OUTPUT_BASE_DIR}/run-py-1l}"
PANEL_VARIANT="${PANEL_VARIANT:-flexible}"

case "${PANEL_VARIANT}" in
  flexible)
    PANEL_FILE="${PANEL_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
    ;;
  strict)
    PANEL_FILE="${PANEL_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
    ;;
  *)
    echo "ERROR: unsupported PANEL_VARIANT=${PANEL_VARIANT}"
    echo "Supported values: flexible, strict"
    exit 1
    ;;
esac

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

MAX_TREATMENT_REPOS="${MAX_TREATMENT_REPOS:-0}"
MAX_CONTROL_REPOS="${MAX_CONTROL_REPOS:-0}"
ALLOW_MISSING_LATEST_COMMIT="${ALLOW_MISSING_LATEST_COMMIT:-false}"

if [[ "${MAX_TREATMENT_REPOS}" -gt 0 || "${MAX_CONTROL_REPOS}" -gt 0 ]]; then
  RUN_MODE="smoke"
  DEFAULT_SONAR_ROOT="${TMP_DIR}/smoke/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${DEFAULT_SONAR_ROOT}/meta"
else
  RUN_MODE="full"
  DEFAULT_SONAR_ROOT="${MAIN_OUTPUT_DIR}/${PANEL_VARIANT}"
  DEFAULT_META_DIR="${TMP_DIR}/${PANEL_VARIANT}"
fi

SONAR_ROOT="${SONAR_ROOT:-${DEFAULT_SONAR_ROOT}}"
META_DIR="${META_DIR:-${DEFAULT_META_DIR}}"

TREATMENT_TS_FILE="${TREATMENT_TS_FILE:-${SONAR_ROOT}/treatment/data/ts_repos_monthly.csv}"
CONTROL_TS_FILE="${CONTROL_TS_FILE:-${SONAR_ROOT}/control/data/ts_repos_monthly.csv}"

MONTHS_FILE="${MONTHS_FILE:-${META_DIR}/months.txt}"
TREATMENT_REPOS_FILE="${TREATMENT_REPOS_FILE:-${META_DIR}/treatment_repos.txt}"
CONTROL_REPOS_FILE="${CONTROL_REPOS_FILE:-${META_DIR}/control_repos.txt}"
SUMMARY_FILE="${SUMMARY_FILE:-${META_DIR}/sonarqube_input_summary.csv}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_create_sonarqube_input_${PANEL_VARIANT}_${RUN_TS}.log}"

mkdir -p \
  "${LOG_DIR}" \
  "${SONAR_ROOT}" \
  "${META_DIR}" \
  "$(dirname "${TREATMENT_TS_FILE}")" \
  "$(dirname "${CONTROL_TS_FILE}")"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: create Python SonarQube scan inputs"
  echo "Timestamp:                    ${RUN_TS}"
  echo "Script name:                  ${SCRIPT_NAME}"
  echo "Run prefix:                   ${RUN_PREFIX}"
  echo "Run mode:                     ${RUN_MODE}"
  echo "Panel variant:                ${PANEL_VARIANT}"
  echo "Python script:                ${PY_SCRIPT}"
  echo "History script:               ${HISTORY_SCRIPT}"
  echo "Panel file:                   ${PANEL_FILE}"
  echo "Sonar root:                   ${SONAR_ROOT}"
  echo "Metadata dir:                 ${META_DIR}"
  echo "Main output dir:              ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:             ${TMP_DIR}"
  echo "Treatment clone root:         ${TREATMENT_CLONE_ROOT}"
  echo "Control clone root:           ${CONTROL_CLONE_ROOT}"
  echo "Treatment output:             ${TREATMENT_TS_FILE}"
  echo "Control output:               ${CONTROL_TS_FILE}"
  echo "Months file:                  ${MONTHS_FILE}"
  echo "Treatment repos file:         ${TREATMENT_REPOS_FILE}"
  echo "Control repos file:           ${CONTROL_REPOS_FILE}"
  echo "Summary file:                 ${SUMMARY_FILE}"
  echo "Max treatment repos:          ${MAX_TREATMENT_REPOS}"
  echo "Max control repos:            ${MAX_CONTROL_REPOS}"
  echo "Allow missing latest_commit:  ${ALLOW_MISSING_LATEST_COMMIT}"
  echo "Log file:                     ${LOG_FILE}"
  echo "============================================================"
  echo

  for f in "${PY_SCRIPT}" "${HISTORY_SCRIPT}" "${PANEL_FILE}"; do
    if [[ ! -f "${f}" ]]; then
      echo "ERROR: required file not found: ${f}"
      exit 1
    fi
  done

  for d in "${TREATMENT_CLONE_ROOT}" "${CONTROL_CLONE_ROOT}"; do
    if [[ ! -d "${d}" ]]; then
      echo "ERROR: required clone directory not found: ${d}"
      exit 1
    fi
  done

  echo "** Compile Python scripts"
  echo "------------------------------------------------------------"
  python -m py_compile "${PY_SCRIPT}"
  python -m py_compile "${HISTORY_SCRIPT}"
  echo

  echo "** Input panel summary"
  echo "------------------------------------------------------------"
  python - <<PY
import pandas as pd
from pathlib import Path

path = Path("${PANEL_FILE}")
df = pd.read_csv(path)

print("Panel file:", path)
print("Rows:", len(df))
print("Unique repos:", df["repo_name"].nunique())

if "dataset_source" in df.columns:
    print()
    print("Rows by dataset_source:")
    print(df["dataset_source"].value_counts(dropna=False).to_string())

    print()
    print("Repos by dataset_source:")
    print(df.groupby("dataset_source")["repo_name"].nunique().to_string())

time_col = "time" if "time" in df.columns else "month" if "month" in df.columns else None
if time_col:
    print()
    print("Time range:", df[time_col].min(), "to", df[time_col].max())
PY
  echo

  CMD=(
    python "${PY_SCRIPT}"
    --panel-file "${PANEL_FILE}"
    --sonar-root "${SONAR_ROOT}"
    --treatment-clone-root "${TREATMENT_CLONE_ROOT}"
    --control-clone-root "${CONTROL_CLONE_ROOT}"
    --history-script "${HISTORY_SCRIPT}"
    --treatment-output "${TREATMENT_TS_FILE}"
    --control-output "${CONTROL_TS_FILE}"
    --months-file "${MONTHS_FILE}"
    --treatment-repos-file "${TREATMENT_REPOS_FILE}"
    --control-repos-file "${CONTROL_REPOS_FILE}"
    --summary-file "${SUMMARY_FILE}"
    --max-treatment-repos "${MAX_TREATMENT_REPOS}"
    --max-control-repos "${MAX_CONTROL_REPOS}"
  )

  if [[ "${ALLOW_MISSING_LATEST_COMMIT}" == "true" ]]; then
    CMD+=(--allow-missing-latest-commit)
  fi

  echo "** Running SonarQube input preparation"
  echo "------------------------------------------------------------"
  echo "${CMD[*]}"
  echo

  "${CMD[@]}"

  echo
  echo "** Output file check"
  echo "------------------------------------------------------------"
  for f in \
    "${TREATMENT_TS_FILE}" \
    "${CONTROL_TS_FILE}" \
    "${MONTHS_FILE}" \
    "${TREATMENT_REPOS_FILE}" \
    "${CONTROL_REPOS_FILE}" \
    "${SUMMARY_FILE}"
  do
    if [[ -f "${f}" ]]; then
      echo "Command: wc -l ${f}"
      wc -l "${f}"
    else
      echo "MISSING: ${f}"
    fi
  done

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Run mode:        ${RUN_MODE}"
  echo "Panel variant:   ${PANEL_VARIANT}"
  echo "Treatment input: ${TREATMENT_TS_FILE}"
  echo "Control input:   ${CONTROL_TS_FILE}"
  echo "Summary file:    ${SUMMARY_FILE}"
  echo "Main output dir: ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:${TMP_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9a-create-jsts-sonarqube-input.sh,
# but it does NOT call the existing JS/TS shell wrapper.