mkdir -p proc_scripts/tmp

cp proc_scripts/count_repo_lang.py \
   proc_scripts/clone_repos_v2.py \
   proc_scripts/create_clone_usable_repos_with_event.py \
   proc_scripts/check_time_of_event_and_adoption.py \
   proc_scripts/extract_matched_control_repos.py \
   proc_scripts/filter_controls_by_local_cursor_evidence.py \
   proc_scripts/check_cache_control_repos.py \
   proc_scripts/create_control_usable_repos.py \
   proc_scripts/create_tmp_repo_timeseries_history.py \
   proc_scripts/prepare_panel_event_v2.py \
   proc_scripts/analyze_repos_v2.py \
   proc_scripts/save_treatment_options.py \
   proc_scripts/summarize_matched_panels.py \
   proc_scripts/run_sonarqube_v2.py \
   proc_scripts/check_sonarqube_panel.py \
   proc_scripts/merge_sonarqube_panel_v2.py \
   proc_scripts/prepare_sonarqube_input.py \
   proc_scripts/prepare_quality_did_input_v2.py \
   proc_scripts/summarize_borusyak_quality_outputs_python.py \
   proc_scripts/tmp/

