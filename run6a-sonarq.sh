python proc_scripts/run_sonarqube_v2.py \
  --aggregation month \
  --input-file tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly.csv \
  --output-file tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly_scanned.csv \
  --clone-dir ../ai_code_complexity_study_repo_dataset \
  --num-processes 1

