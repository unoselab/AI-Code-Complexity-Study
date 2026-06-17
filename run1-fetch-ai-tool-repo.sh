#!/usr/bin/env bash
set -euo pipefail

# Wrapper for:
#   python proc_scripts/fetch_ai_tool_repos.py
#
# Log format:
#   logs/run-fetch-ai-tool-repo-MMDD-HHMM.log

SCRIPT_NAME="run-fetch-ai-tool-repo"
PY_SCRIPT="proc_scripts/fetch_ai_tool_repos.py"
LOG_DIR="logs"
TIMESTAMP="$(date +%m%d-%H%M)"
LOG_FILE="${LOG_DIR}/${SCRIPT_NAME}-${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"

echo "============================================================"
echo "AI tool repository fetch"
echo "Started: $(date)"
echo "Working directory: $(pwd)"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not activated}"
echo "Python: $(which python)"
echo "Python version: $(python --version 2>&1)"
echo "Script: ${PY_SCRIPT}"
echo "Log file: ${LOG_FILE}"
echo "============================================================"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Cannot find ${PY_SCRIPT}"
  exit 1
fi

if [[ "${CONDA_DEFAULT_ENV:-}" != "aicomplexity" ]]; then
  echo "WARNING: Current conda env is '${CONDA_DEFAULT_ENV:-none}', expected 'aicomplexity'."
  echo "You may want to run:"
  echo "  conda activate aicomplexity"
  echo
fi

if [[ ! -f ".env" ]]; then
  echo "WARNING: .env file not found."
  echo "If the script needs GITHUB_TOKEN, create .env first."
  echo
fi

START_SECONDS="$(date +%s)"

{
  echo "============================================================"
  echo "AI tool repository fetch"
  echo "Started: $(date)"
  echo "Working directory: $(pwd)"
  echo "Conda env: ${CONDA_DEFAULT_ENV:-not activated}"
  echo "Python: $(which python)"
  echo "Python version: $(python --version 2>&1)"
  echo "Script: ${PY_SCRIPT}"
  echo "Arguments: $*"
  echo "============================================================"
  echo

  # -u makes Python output unbuffered so progress appears live.
  # stdbuf also helps line-buffer output before tee writes it.
  PYTHONUNBUFFERED=1 stdbuf -oL -eL python -u "${PY_SCRIPT}" "$@"

  echo
  echo "============================================================"
  echo "Completed successfully: $(date)"
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"

STATUS="${PIPESTATUS[0]}"
END_SECONDS="$(date +%s)"
DURATION="$((END_SECONDS - START_SECONDS))"

echo
echo "============================================================"
echo "Finished with status: ${STATUS}"
echo "Duration: ${DURATION} seconds"
echo "Log saved to: ${LOG_FILE}"
echo "============================================================"

exit "${STATUS}"
