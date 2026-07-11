#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/run6d-sonarqube-full-treatment-${TS}.log"

echo "============================================================"
echo "run6d: full treatment SonarQube scan"
echo "Started:  $(date)"
echo "Log file: ${LOG_FILE}"
echo "============================================================"

{
  echo "============================================================"
  echo "run6d: full treatment SonarQube scan"
  echo "Started: $(date)"
  echo "Input:   tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv"
  echo "Output:  tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv"
  echo "Clone:   ../ai_code_complexity_study_repo_dataset"
  echo "============================================================"
  echo

  python proc_scripts/run_sonarqube_v2.py \
    --aggregation month \
    --input-file tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv \
    --output-file tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv \
    --clone-dir ../ai_code_complexity_study_repo_dataset \
    --num-processes 1

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
