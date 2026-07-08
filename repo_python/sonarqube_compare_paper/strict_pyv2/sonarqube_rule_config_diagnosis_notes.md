# SonarQube rule/config/analyzer difference diagnosis

This diagnostic uses the strongest comparable subset:
- Same repository
- Same month
- Exact same latest_commit hash
- Identical ncloc

If warning metrics differ in this subset, the most likely explanation is SonarQube rule set, quality profile, analyzer/plugin version, or scanner configuration.

## Input scope
- Exact-commit and ncloc-identical rows: 911
- Unique repositories: 178

## Warning metric signal
- bugs: identical_share=0.6169, different_share=0.3831, median_abs_diff=0.0, negative_share=0.2228, positive_share=0.1603
- vulnerabilities: identical_share=0.6641, different_share=0.3359, median_abs_diff=0.0, negative_share=0.0472, positive_share=0.2887
- code_smells: identical_share=0.1405, different_share=0.8595, median_abs_diff=8.0, negative_share=0.2689, positive_share=0.5906
- technical_debt: identical_share=0.1262, different_share=0.8738, median_abs_diff=40.0, negative_share=0.3019, positive_share=0.5719
- static_analysis_warnings: identical_share=0.1186, different_share=0.8814, median_abs_diff=9.0, negative_share=0.2887, positive_share=0.5928

## Interpretation
- ncloc-identical rows reduce the likelihood that the difference is caused only by source inclusion/exclusion scope.
- Large warning differences in this subset point to rule/config/analyzer/profile differences.
- Negative diff means our pyv2 value is lower than the paper value.
- Positive diff means our pyv2 value is higher than the paper value.

## All metric summary
- ncloc: identical_share=1.0000, median_abs_diff=0.0, max_abs_diff=0.0
- bugs: identical_share=0.6169, median_abs_diff=0.0, max_abs_diff=338.0
- vulnerabilities: identical_share=0.6641, median_abs_diff=0.0, max_abs_diff=19.0
- code_smells: identical_share=0.1405, median_abs_diff=8.0, max_abs_diff=837.0
- duplicated_lines_density: identical_share=0.9813, median_abs_diff=0.0, max_abs_diff=6.499999999999999
- comment_lines_density: identical_share=0.9989, median_abs_diff=0.0, max_abs_diff=0.2999999999999998
- cognitive_complexity: identical_share=0.9989, median_abs_diff=0.0, max_abs_diff=1.0
- technical_debt: identical_share=0.1262, median_abs_diff=40.0, max_abs_diff=3580.0
- static_analysis_warnings: identical_share=0.1186, median_abs_diff=9.0, max_abs_diff=841.0
