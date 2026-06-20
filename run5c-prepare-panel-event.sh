python proc_scripts/prepare_panel_event_v2.py \
  --treatment-meta tmp_adoption_test/data/matched_controls_v2_treatment_only.csv \
  --pairs tmp_adoption_test/data/matched_controls_v2_pairs.csv \
  --treatment-ts tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv \
  --control-ts tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv \
  --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv