# SonarQube difference cause summary

This diagnostic summarizes likely causes of paper-vs-pyv2 metric differences.

## Interpretation rules

- Commit mismatch suggests commit-selection difference.
- Exact commit with different ncloc suggests source-scope difference or mixed source/config effects.
- Exact commit with identical ncloc but warning-metric differences suggests rule/config/analyzer/profile difference.

## Key signal

- bugs: cause=rule_config_analyzer_profile_signal, rows=911, different_share=0.38309549945115257, median_abs_diff=0.0, share_total_abs_diff_within_metric=0.09503025064822818
- code_smells: cause=rule_config_analyzer_profile_signal, rows=911, different_share=0.8594950603732162, median_abs_diff=8.0, share_total_abs_diff_within_metric=0.10421388125110213
- static_analysis_warnings: cause=rule_config_analyzer_profile_signal, rows=911, different_share=0.8814489571899012, median_abs_diff=9.0, share_total_abs_diff_within_metric=0.07515492358678379
- technical_debt: cause=rule_config_analyzer_profile_signal, rows=911, different_share=0.8737650933040615, median_abs_diff=40.0, share_total_abs_diff_within_metric=0.0958077028201498
- vulnerabilities: cause=rule_config_analyzer_profile_signal, rows=911, different_share=0.3358946212952799, median_abs_diff=0.0, share_total_abs_diff_within_metric=0.12287145242070117

## Files to inspect next

- sonarqube_difference_cause_summary_by_metric.csv
- sonarqube_difference_cause_top_repos.csv
- sonarqube_difference_cause_negative_outliers.csv
- sonarqube_difference_cause_positive_outliers.csv
