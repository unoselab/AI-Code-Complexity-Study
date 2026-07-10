# SonarQube Difference Main Driver Diagnosis

This report summarizes likely causes of paper-vs-pyv2 SonarQube metric differences.

## Overall cause ranking by total absolute metric difference
- source_scope_difference_or_mixed: total_abs_diff=3188655.900
- paper_commit_missing: total_abs_diff=735384.700
- rule_config_analyzer_profile_signal: total_abs_diff=233787.700
- ncloc_missing_exact_commit: total_abs_diff=167463.000
- commit_selection_difference: total_abs_diff=163421.500

## Final DiD input cause ranking by primary metrics
- static_analysis_warnings: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.818, different_share=1.000
- code_smells: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.849, different_share=0.995
- technical_debt: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.865, different_share=0.997
- bugs: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.849, different_share=0.828
- vulnerabilities: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.774, different_share=0.778
- ncloc: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.926, different_share=1.000
- cognitive_complexity: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.940, different_share=0.321
- duplicated_lines_density: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.857, different_share=0.402
- comment_lines_density: top_cause=source_scope_difference_or_mixed, share_total_abs_diff=0.831, different_share=0.399

## Final DiD group interpretation
Use sonarqube_main_difference_drivers_final_did_by_treatment_post.csv to check whether differences concentrate in treatment-post rows, which can directly alter the DiD trajectory.

## Interpretation
If source_scope_difference_or_mixed dominates total_abs_diff, large metric differences are mainly linked to rows where ncloc differs or source inclusion/exclusion differs.
If rule_config_analyzer_profile_signal remains large for warning metrics, the evidence supports differences in SonarQube rules, quality profile, analyzer/plugin version, or scanner configuration even under the same commit and ncloc.
If differences concentrate in treatment-post rows, they are more likely to affect the final ATT trajectory.
