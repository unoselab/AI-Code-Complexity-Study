# (aicomplexity) OISSE-IST173C01:ai-code-complexity-study$ 
python proc_scripts/analyze_agc_zero_event_months.py \
  --source-counts repo_python/run-py-5a-py312/strict/repo_month_function_event_counts.csv \
  --detector-summary ../python_commit_function_detect/codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast/strict/py312-full-450548-fresh/repo_month_function_event_summary_all.csv \
  --panel repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv \
  --parse-exclusions-by-repo-month repo_python/run-py-5b-py312/strict/agc_commit_function_parse_exclusions_by_repo_month.csv \
  --output-dir repo_python/run-py-5d/strict \
  --expected-panel-rows 1633 \
  --expected-detector-rows 1289 \
  --expected-zero-event-months 344

# ============================================================================
# Zero-function-event repository-month analysis
# ============================================================================
# Status:                       PASS
# Complete repository-months:   1633
# Event-positive months:        1289
# Zero-event months:            344
# Conditional-ratio months:     1289
# Parse-exclusion months:       97
# Complete table:               repo_python/run-py-5d/strict/repo_month_agc_function_event_analysis_complete.csv
# QC checks:                    repo_python/run-py-5d/strict/zero_function_event_month_checks.csv
# Summary:                      repo_python/run-py-5d/strict/zero_function_event_month_summary.json
# ============================================================================