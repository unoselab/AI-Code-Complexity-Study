#!/usr/bin/env bash
set -euo pipefail

# run-y-b01 v1: reproduce manuscript table tb:python-empirical-dataset.
# Install this file in proc_sh_x01 and the accompanying Python file in
# proc_script_x01. Run from the project root (or any working directory):
#   bash proc_sh_x01/run-y-b01-summarize-python-empirical-dataset.sh
#
# Default mode aggregates B05/B06 CSV accounting and reconciles A12/A15/C04/I06
# summaries. It does not rescan the large raw score and issue tables.
# C04 v2 and NPR > 1.515059 are explicitly verified. Finite NPR eligibility is
# reported in the table; threshold-selected counts appear separately in JSON
# and the log. Changing a threshold alone cannot change finite-score counts;
# changing the scores, coverage, or population can, so counts come from inputs.
#
# Dependencies: Bash, Python >=3.10 (standard library), tee, mktemp.
# Environment overrides: PROJECT_ROOT, PYTHON_BIN, ANALYSIS_SCRIPT, NPR_ROOT,
# SNAPSHOT_MAP, SNAPSHOT_ISSUES, A12_SUMMARY, A15_SUMMARY, C04_SUMMARY,
# I06_SUMMARY, OUTPUT_DIR, LOG_DIR, EXPECTED_NPR_THRESHOLD, EXPECTED_C04_VERSION.
# Relative overrides are interpreted from PROJECT_ROOT.
# Extra command-line arguments are forwarded unchanged to Python, for example:
#   bash proc_sh_x01/run-y-b01-summarize-python-empirical-dataset.sh --help
#   bash proc_sh_x01/run-y-b01-summarize-python-empirical-dataset.sh --output-dir /path/to/new-output
#
# Optional complete raw-file verification (more memory and I/O):
#   VERIFY_RAW=1 bash proc_sh_x01/run-y-b01-summarize-python-empirical-dataset.sh
# Raw-file locations can be overridden by NPR_FILES, ML_FILES, and ISSUES.
# Individual raw scans can also be requested with Python's --npr-files,
# --ml-files, or --issues arguments instead of VERIFY_RAW=1.
#
# Outputs: python_empirical_dataset.{tex,csv,json} and
# python_empirical_dataset_checks.csv. Existing output directories are rejected.
# The LaTeX table retains its label and needs no new macro-common.tex macros.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}"
cd -- "${PROJECT_ROOT}"
PROJECT_ROOT="$(pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-${PROJECT_ROOT}/proc_script_x01/summarize_python_empirical_dataset.py}"
NPR_ROOT="${NPR_ROOT:-${PROJECT_ROOT}/../../detect_code_gpt/output/snapshot_npr}"
SNAPSHOT_MAP="${SNAPSHOT_MAP:-${PROJECT_ROOT}/repo_x01/run-x-b06/python_quality_snapshot_join_audit.csv}"
SNAPSHOT_ISSUES="${SNAPSHOT_ISSUES:-${PROJECT_ROOT}/repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv}"
A12_SUMMARY="${A12_SUMMARY:-${NPR_ROOT}/run-x-a12/summary.json}"
A15_SUMMARY="${A15_SUMMARY:-${NPR_ROOT}/run-x-a15/summary.json}"
C04_SUMMARY="${C04_SUMMARY:-${NPR_ROOT}/run-x-c04/fun-cfun-threshold-v2/summary.json}"
I06_SUMMARY="${I06_SUMMARY:-${PROJECT_ROOT}/repo_x01/run-x-i06/summary.json}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_x01/run-y-b01/python-empirical-dataset-v1}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-y-b01}"
EXPECTED_NPR_THRESHOLD="${EXPECTED_NPR_THRESHOLD:-1.515059}"
EXPECTED_C04_VERSION="${EXPECTED_C04_VERSION:-run-x-c04-v2}"

command -v "${PYTHON_BIN}" >/dev/null || { echo "Python executable not found: ${PYTHON_BIN}" >&2; exit 1; }
[[ -f "${ANALYSIS_SCRIPT}" ]] || { echo "Python script not found: ${ANALYSIS_SCRIPT}" >&2; exit 1; }
"${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10 or later is required")'

args=(
  --project-root "${PROJECT_ROOT}"
  --npr-root "${NPR_ROOT}"
  --snapshot-map "${SNAPSHOT_MAP}"
  --snapshot-issues "${SNAPSHOT_ISSUES}"
  --a12-summary "${A12_SUMMARY}"
  --a15-summary "${A15_SUMMARY}"
  --c04-summary "${C04_SUMMARY}"
  --i06-summary "${I06_SUMMARY}"
  --expected-npr-threshold "${EXPECTED_NPR_THRESHOLD}"
  --expected-c04-version "${EXPECTED_C04_VERSION}"
  --output-dir "${OUTPUT_DIR}"
)
case "${VERIFY_RAW:-0}" in
  0) ;;
  1)
    args+=(
      --npr-files "${NPR_FILES:-${NPR_ROOT}/run-x-c04/fun-cfun-threshold-v2/python_fun_cfun_repo_month_file_npr_scores.csv}"
      --ml-files "${ML_FILES:-${PROJECT_ROOT}/repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv}"
      --issues "${ISSUES:-${PROJECT_ROOT}/repo_x01/run-x-b05/python_sonarqube_issues.csv.gz}"
    )
    ;;
  *) echo "VERIFY_RAW must be 0 or 1" >&2; exit 1 ;;
esac

mkdir -p -- "${LOG_DIR}"
LOG_FILE="$(mktemp "${LOG_DIR}/run-y-b01-v1-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
echo "run-y-b01 v1 | log: ${LOG_FILE}"
# pipefail preserves Python failures even when tee succeeds.
"${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" "${args[@]}" "$@" 2>&1 | tee "${LOG_FILE}"
