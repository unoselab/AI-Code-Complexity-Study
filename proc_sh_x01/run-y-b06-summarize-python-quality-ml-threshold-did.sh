#!/usr/bin/env bash
set -euo pipefail

# Summarize ML-localized Python issue-burden DiD estimates for the paper table.
#
# Inputs:
#   RF_INPUT    RF total-threshold static estimates from run-x-d08 v2.
#   CM_INPUT    CM total-threshold static estimates from run-x-h07 v1.
#   RFCM_INPUT  RF+CM total-threshold static estimates from run-x-i09 v1.
#
# Outputs:
#   OUTPUT_DIR/tb_did_quality_ml_static_thresholds-v3.tex
#   OUTPUT_DIR/python_quality_ml_threshold_did_summary.csv
#   OUTPUT_DIR/python_quality_ml_threshold_did_summary.json
#   OUTPUT_DIR/python_quality_ml_threshold_did_summary_checks.csv
#
# The wrapper is independent of the upstream experiment wrappers. It only reads
# their completed CSV artifacts and passes all analysis parameters explicitly to
# the corresponding Python summarizer.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-${PROJECT_ROOT}/proc_script_x01/summarize_python_quality_ml_threshold_did.py}"

RF_INPUT="${RF_INPUT:-${PROJECT_ROOT}/repo_x01/run-x-d08/quality_ml_total_threshold_static.csv}"
CM_INPUT="${CM_INPUT:-${PROJECT_ROOT}/repo_x01/run-x-h07/quality_ml_cfun_total_threshold_static.csv}"
RFCM_INPUT="${RFCM_INPUT:-${PROJECT_ROOT}/repo_x01/run-x-i09/quality_ml_fun_cfun_total_threshold_static.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_x01/run-y-b06/python-quality-ml-threshold-did-table-v1}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-y-b06}"

SAMPLE_SPEC="${SAMPLE_SPEC:-exclude_scope_mismatch_repos}"
FECS_SPEC="${FECS_SPEC:-adjusted_burden}"
FEOS_SPEC="${FEOS_SPEC:-fe_only_burden}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-0.50}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
OMIT_DELTA="${OMIT_DELTA:-0.40}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "${1:-}" == "--self-test" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" "$@"
fi

for required_file in "${PYTHON_SCRIPT}" "${RF_INPUT}" "${CM_INPUT}" "${RFCM_INPUT}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file not found: %s\n' "${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${LOG_DIR}"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-y-b06-v1-${RUN_STAMP}-$$.log"

ARGS=(
  --rf-input "${RF_INPUT}"
  --cm-input "${CM_INPUT}"
  --rf-cm-input "${RFCM_INPUT}"
  --output-dir "${OUTPUT_DIR}"
  --sample-spec "${SAMPLE_SPEC}"
  --fecs-spec "${FECS_SPEC}"
  --feos-spec "${FEOS_SPEC}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --omit-delta "${OMIT_DELTA}"
)

if [[ "${OVERWRITE}" == "1" ]]; then
  ARGS+=(--overwrite)
fi

printf 'run-y-b06 v1 | log: %s\n' "${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${ARGS[@]}" "$@" 2>&1 | tee "${LOG_FILE}"
