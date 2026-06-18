
# Step 1: Create historical month input 

python proc_scripts/create_tmp_repo_timeseries_history.py \
    --output tmp_sonar_batch/data/ts_repos_monthly.csv \
    --clone-root ../CursorRepos --months 2026-03,2026-04,2026-05 \
    TheSethRose/Agent-Chat utensils/mcp-nixos nextml-code/pytorch-datastream

# Step 2: Run SonarQube on the multi-month input

python proc_scripts/run_sonarqube_v2.py --aggregation month

# Step 2.1: Results

python proc_scripts/test_display_metrics.py tmp_sonar_batch/data/ts_repos_monthly.csv

