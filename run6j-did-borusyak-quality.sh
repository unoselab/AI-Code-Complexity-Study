#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%m%d-%H%M)"
LOG_FILE="logs/run6j-did-borusyak-quality-${TS}.log"

export PROJECT_ROOT="$(pwd)"

{
  echo "============================================================"
  echo "run6j: Borusyak DiD for SonarQube quality outcomes"
  echo "Started: $(date)"
  echo "Log file: ${LOG_FILE}"
  echo "PROJECT_ROOT: ${PROJECT_ROOT}"
  echo "============================================================"
  echo

  Rscript -e "rmarkdown::render(
    'proc_r/DiffInDiffBorusyak_quality_v2.Rmd',
    output_dir = 'tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2',
    envir = new.env()
  )"

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
