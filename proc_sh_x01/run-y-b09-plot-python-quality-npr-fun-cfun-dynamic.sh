#!/usr/bin/env bash
set -euo pipefail

# Create NPR-localized RF+CM issue-burden event-study figure panels.
#
# Input:
#   INPUT_FILE
#     Total-threshold dynamic DiD estimates for NPR-localized RF+CM issue
#     burden. The default CSV is produced by run-x-l02 v1. This wrapper reads
#     the completed estimates but neither invokes nor depends on an earlier
#     shell wrapper.
#
# Figure outputs:
#   FIGURE_DIR/fig_did_quality_npr_fun_cfun_dynamic-fecs-below-v1.pdf
#   FIGURE_DIR/fig_did_quality_npr_fun_cfun_dynamic-fecs-primary-above-v1.pdf
#   FIGURE_DIR/fig_did_quality_npr_fun_cfun_dynamic-feos-below-v1.pdf
#   FIGURE_DIR/fig_did_quality_npr_fun_cfun_dynamic-feos-primary-above-v1.pdf
#
# Reconciliation outputs:
#   OUTPUT_DIR/python_quality_npr_fun_cfun_dynamic_plot_data.csv
#   OUTPUT_DIR/python_quality_npr_fun_cfun_dynamic_plot_checks.csv
#   OUTPUT_DIR/python_quality_npr_fun_cfun_dynamic_plot_manifest.json
#
# THRESHOLD_X_SPREAD controls the total within-month horizontal separation of
# threshold estimates. The primary NPR threshold remains at the nominal event
# month. Environment variables may override all paths and analysis parameters.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-${PROJECT_ROOT}/proc_script_x01/plot_python_quality_npr_fun_cfun_dynamic.py}"

INPUT_FILE="${INPUT_FILE:-${PROJECT_ROOT}/repo_x01/run-x-l02/borusyak-threshold-quality-v1/quality_fun_cfun_npr_total_threshold_dynamic.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_x01/run-y-b09/python-quality-npr-fun-cfun-dynamic-figure-v1}"
FIGURE_DIR="${FIGURE_DIR:-${OUTPUT_DIR}/figure}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-y-b09}"

SAMPLE_SPEC="${SAMPLE_SPEC:-exclude_scope_mismatch_repos}"
FECS_SPEC="${FECS_SPEC:-adjusted_burden}"
FEOS_SPEC="${FEOS_SPEC:-fe_only_burden}"
OUTCOME="${OUTCOME:-log1p_selected_issue_total}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.515059}"
THRESHOLD_RADIUS="${THRESHOLD_RADIUS:-0.50}"
THRESHOLD_STEP="${THRESHOLD_STEP:-0.05}"
THRESHOLD_X_SPREAD="${THRESHOLD_X_SPREAD:-0.36}"
EVENT_MIN="${EVENT_MIN:--6}"
EVENT_MAX="${EVENT_MAX:-6}"
REFERENCE_EVENT="${REFERENCE_EVENT:--1}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
DPI="${DPI:-300}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "${1:-}" == "--self-test" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" "$@"
fi

for required_file in "${PYTHON_SCRIPT}" "${INPUT_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file not found: %s\n' "${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${FIGURE_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-y-b09-v1-${RUN_STAMP}-$$.log"

ARGS=(
  --input "${INPUT_FILE}"
  --figure-dir "${FIGURE_DIR}"
  --output-dir "${OUTPUT_DIR}"
  --sample-spec "${SAMPLE_SPEC}"
  --fecs-spec "${FECS_SPEC}"
  --feos-spec "${FEOS_SPEC}"
  --outcome "${OUTCOME}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --threshold-radius "${THRESHOLD_RADIUS}"
  --threshold-step "${THRESHOLD_STEP}"
  --threshold-x-spread "${THRESHOLD_X_SPREAD}"
  --event-min "${EVENT_MIN}"
  --event-max "${EVENT_MAX}"
  --reference-event "${REFERENCE_EVENT}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --dpi "${DPI}"
)

if [[ "${OVERWRITE}" == "1" ]]; then
  ARGS+=(--overwrite)
fi

printf 'run-y-b09 v1 | log: %s\n' "${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${ARGS[@]}" "$@" 2>&1 | tee "${LOG_FILE}"
