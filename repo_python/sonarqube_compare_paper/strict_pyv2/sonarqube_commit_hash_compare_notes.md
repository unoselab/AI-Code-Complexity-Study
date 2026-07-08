# SonarQube Commit Hash Comparison Notes

## Purpose
Compare paper monthly time-series latest_commit values with our pyv2 SonarQube scan latest_commit values.

## Key counts
- Overlap repo-months: 2169
- Commit exact matches: 1517
- Commit prefix matches: 0
- Commit mismatches: 101
- Paper-only repo-months: 56168
- Our-only repo-months: 874

## Interpretation guide
- If commit mismatches are common, metric differences can be explained by different checked-out commits.
- If commits match but metrics differ, the likely cause is SonarQube version, plugin, scanner option, exclusion rule, or language profile differences.
- static_analysis_warnings is computed as bugs + vulnerabilities + code_smells on both sides.

## Metric difference summary by commit status
| commit_match_status   | metric                   |   comparable_non_null |   identical_rows |   identical_share_among_non_null |    mean_diff |   median_abs_diff |   max_abs_diff |
|:----------------------|:-------------------------|----------------------:|-----------------:|---------------------------------:|-------------:|------------------:|---------------:|
| exact_match           | bugs                     |                  1510 |              683 |                       0.452318   |  -32.8801    |               1   |         3864   |
| exact_match           | code_smells              |                  1510 |              153 |                       0.101325   |  108.726     |              19.5 |         8448   |
| exact_match           | cognitive_complexity     |                  1487 |             1301 |                       0.874916   |  -20.7552    |               0   |        29442   |
| exact_match           | comment_lines_density    |                  1488 |             1257 |                       0.844758   |   -0.0729839 |               0   |           15.7 |
| exact_match           | duplicated_lines_density |                  1488 |             1239 |                       0.832661   |   -0.16586   |               0   |           46.6 |
| exact_match           | ncloc                    |                  1488 |              911 |                       0.612231   |  513.799     |               0   |       133392   |
| exact_match           | static_analysis_warnings |                  1517 |              130 |                       0.0856955  |  -30.8761    |              21   |        37725   |
| exact_match           | technical_debt           |                  1510 |              139 |                       0.092053   |  169.957     |              85   |        56847   |
| exact_match           | vulnerabilities          |                  1510 |              755 |                       0.5        |    4.03709   |               0.5 |          137   |
| mismatch              | bugs                     |                   101 |               45 |                       0.445545   |  -26.8317    |               1   |         1732   |
| mismatch              | code_smells              |                   101 |                2 |                       0.019802   |   87.4158    |              16   |         3320   |
| mismatch              | cognitive_complexity     |                   101 |               72 |                       0.712871   |   74.2871    |               0   |         3603   |
| mismatch              | comment_lines_density    |                   101 |               74 |                       0.732673   |    0.10297   |               0   |           14.5 |
| mismatch              | duplicated_lines_density |                   101 |               80 |                       0.792079   |    0.238614  |               0   |           25.3 |
| mismatch              | ncloc                    |                   101 |               53 |                       0.524752   |  935.218     |               0   |        68575   |
| mismatch              | static_analysis_warnings |                   101 |                1 |                       0.00990099 |   67.0099    |              13   |         1591   |
| mismatch              | technical_debt           |                   101 |               27 |                       0.267327   |  319.644     |              60   |        13489   |
| mismatch              | vulnerabilities          |                   101 |               37 |                       0.366337   |    6.42574   |               2   |           83   |
| paper_commit_missing  | bugs                     |                   422 |              263 |                       0.623223   |   -4.06872   |               0   |          338   |
| paper_commit_missing  | code_smells              |                   422 |               74 |                       0.175355   |    0.488152  |               6   |         1017   |
| paper_commit_missing  | cognitive_complexity     |                   413 |              385 |                       0.932203   | -462.516     |               0   |        25067   |
| paper_commit_missing  | comment_lines_density    |                   418 |              360 |                       0.861244   |    0.314354  |               0   |            9.1 |
| paper_commit_missing  | duplicated_lines_density |                   418 |              356 |                       0.851675   |   -0.29067   |               0   |            5.7 |
| paper_commit_missing  | ncloc                    |                   418 |              327 |                       0.782297   | -389.727     |               0   |         9217   |
| paper_commit_missing  | static_analysis_warnings |                   551 |               75 |                       0.136116   |   85.0163    |              14   |        10016   |
| paper_commit_missing  | technical_debt           |                   422 |               79 |                       0.187204   |  -63.891     |              25   |         5328   |
| paper_commit_missing  | vulnerabilities          |                   422 |              254 |                       0.601896   |    2.92891   |               0   |          137   |
