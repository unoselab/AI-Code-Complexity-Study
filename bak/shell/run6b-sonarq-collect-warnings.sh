python proc_scripts/collect_sonarqube_warnings_v2.py --help

python proc_scripts/collect_sonarqube_warnings_v2.py \
  --mode timeseries \
  --data-dir tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data \
  --timeseries-file tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly_scanned.csv \
  --warnings-output tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/sonarqube_warnings.csv \
  --definitions-output tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/sonarqube_warning_definitions.csv \
  --repos "VRSEN/agency-swarm"