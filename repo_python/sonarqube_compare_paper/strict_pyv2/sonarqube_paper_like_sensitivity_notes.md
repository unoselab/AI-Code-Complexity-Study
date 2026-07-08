# SonarQube paper-like sensitivity scan notes

## Purpose
Test whether a paper-like SonarScanner configuration moves pyv2 metrics closer to paper metrics for top outlier repo-month-commit rows.

## Configuration variants
- paper_like: `sonar.sources=.` plus original basic flags; no pyv2 exclusions; no explicit Python version.
- paper_like_python_version: paper_like plus `sonar.python.version=3.11` when requested.
- scope_exclude_common: paper_like plus common source-scope exclusions for frontend/tests/docs/examples/generated/vendor-like directories.

## Inputs
- evidence_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_outlier_root_cause_evidence_table.csv`
- comparison_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_commit_hash_comparison.csv`

## Target selection
- selected target rows: 3
- unique repos: 3
- variants: paper_like,scope_exclude_common
- dry_run: False

## Interpretation guide
- If paper_like reduces distance to paper for ncloc and warning metrics, pyv2 exclusions/source scope were a major driver.
- If ncloc becomes close to paper but warning metrics remain far, compare SonarQube server version, language analyzer/plugin version, quality profile, and active rules.
- If scope_exclude_common moves metrics away from paper, the paper likely included directories that pyv2 excluded.

## Summary by variant and metric
| variant              | metric                   |   target_metric_rows |   comparable_rows |   improved_rows |   improved_share |   sum_abs_diff_our_to_paper |   sum_abs_diff_sensitivity_to_paper |   sum_improvement_abs_diff |   median_abs_diff_sensitivity_to_paper |
|:---------------------|:-------------------------|---------------------:|------------------:|----------------:|-----------------:|----------------------------:|------------------------------------:|---------------------------:|---------------------------------------:|
| paper_like           | bugs                     |                    3 |                 3 |               0 |         0        |                      4069   |                      4069           |                        0   |                                  190   |
| scope_exclude_common | bugs                     |                    3 |                 3 |               0 |         0        |                      4069   |                      4342           |                     -273   |                                  253   |
| paper_like           | code_smells              |                    3 |                 3 |               1 |         0.333333 |                     11651   |                     11728           |                      -77   |                                 1806   |
| scope_exclude_common | code_smells              |                    3 |                 3 |               0 |         0        |                     11651   |                     17888           |                    -6237   |                                 6597   |
| paper_like           | cognitive_complexity     |                    3 |                 3 |               1 |         0.333333 |                     35826   |                     35713           |                      113   |                                 6271   |
| scope_exclude_common | cognitive_complexity     |                    3 |                 3 |               0 |         0        |                     35826   |                     97039           |                   -61213   |                                31431   |
| paper_like           | comment_lines_density    |                    3 |                 3 |               0 |         0        |                         2.3 |                         2.3         |                        0   |                                    0.2 |
| scope_exclude_common | comment_lines_density    |                    3 |                 3 |               0 |         0        |                         2.3 |                        17.9         |                      -15.6 |                                    6.9 |
| paper_like           | duplicated_lines_density |                    3 |                 3 |               0 |         0        |                        35.6 |                        35.6         |                        0   |                                    0.4 |
| scope_exclude_common | duplicated_lines_density |                    3 |                 3 |               1 |         0.333333 |                        35.6 |                        48.3         |                      -12.7 |                                    7.8 |
| paper_like           | ncloc                    |                    3 |                 3 |               0 |         0        |                    222303   |                    222561           |                     -258   |                                88438   |
| scope_exclude_common | ncloc                    |                    3 |                 3 |               0 |         0        |                    222303   |                         1.20365e+06 |                  -981351   |                               389149   |
| paper_like           | static_analysis_warnings |                    3 |                 3 |               1 |         0.333333 |                     15790   |                     15860           |                      -70   |                                 1871   |
| scope_exclude_common | static_analysis_warnings |                    3 |                 3 |               0 |         0        |                     15790   |                     22309           |                    -6519   |                                 6792   |
| paper_like           | technical_debt           |                    3 |                 3 |               1 |         0.333333 |                     81308   |                     81694           |                     -386   |                                18640   |
| scope_exclude_common | technical_debt           |                    3 |                 3 |               0 |         0        |                     81308   |                    123348           |                   -42040   |                                36308   |
| paper_like           | vulnerabilities          |                    3 |                 3 |               1 |         0.333333 |                       108   |                       101           |                        7   |                                   17   |
| scope_exclude_common | vulnerabilities          |                    3 |                 3 |               1 |         0.333333 |                       108   |                       203           |                      -95   |                                   58   |

