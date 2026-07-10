# SonarQube pyv2 vs paper panel comparison

## Inputs
- Paper panel: `data/panel_event_monthly.csv`
- Treatment scan: `repo_python/sonarqube_input/strict/treatment/data/ts_repos_monthly_scanned_pyv2.csv`
- Control scan: `repo_python/sonarqube_input/strict/control/data/ts_repos_monthly_scanned_pyv2.csv`
- Panel variant: `strict`
- Scan suffix: `pyv2`

## Key definition
- Comparison key: `repo_name + time`.
- Difference: `diff = our_value - paper_value`.
- A difference of 0 means identical within the configured tolerance.

## Overlap summary
- Our unique repo-months: 3043
- Paper unique repo-months: 21943
- Overlap repo-months: 2169
- Our repo-months missing in paper: 874
- Paper repo-months for our repos missing in ours: 1

## Metric difference summary
| metric                   |   comparable_non_null |   identical_rows |   identical_share_among_non_null |    mean_diff |   median_abs_diff |   max_abs_diff |
|:-------------------------|----------------------:|-----------------:|---------------------------------:|-------------:|------------------:|---------------:|
| bugs                     |                  2033 |              991 |                         0.487457 |  -26.5991    |                 1 |         3864   |
| code_smells              |                  2033 |              229 |                         0.112641 |   85.2002    |                15 |         8448   |
| cognitive_complexity     |                  2001 |             1758 |                         0.878561 | -107.136     |                 0 |        29442   |
| comment_lines_density    |                  2007 |             1691 |                         0.842551 |    0.0165421 |                 0 |           15.7 |
| duplicated_lines_density |                  2007 |             1675 |                         0.834579 |   -0.1715    |                 0 |           46.6 |
| ncloc                    |                  2007 |             1291 |                         0.643249 |  346.828     |                 0 |       133392   |
| static_analysis_warnings |                  2033 |              204 |                         0.100344 |   62.5268    |                16 |        12308   |
| technical_debt           |                  2033 |              245 |                         0.120512 |  128.852     |                70 |        56847   |
| vulnerabilities          |                  2033 |             1046 |                         0.514511 |    3.92573   |                 0 |          137   |

## Metric difference by scan group
| scan_group   | metric                   |   comparable_non_null |   identical_rows |   identical_share_among_non_null |     mean_diff |   median_abs_diff |   max_abs_diff |
|:-------------|:-------------------------|----------------------:|-----------------:|---------------------------------:|--------------:|------------------:|---------------:|
| control      | bugs                     |                  1074 |              616 |                        0.573557  |   -7.87709    |                 0 |          338   |
| control      | code_smells              |                  1074 |              145 |                        0.135009  |   15.9199     |                10 |         1018   |
| control      | cognitive_complexity     |                  1046 |              934 |                        0.892925  |  -22.8719     |                 0 |         2180   |
| control      | comment_lines_density    |                  1052 |              920 |                        0.874525  |   -0.00865019 |                 0 |            7   |
| control      | duplicated_lines_density |                  1052 |              929 |                        0.88308   |   -0.070057   |                 0 |            6.5 |
| control      | ncloc                    |                  1052 |              776 |                        0.737643  |  219.649      |                 0 |        22159   |
| control      | static_analysis_warnings |                  1074 |              143 |                        0.133147  |   10.8101     |                13 |         1095   |
| control      | technical_debt           |                  1074 |              184 |                        0.171322  |    0.708566   |                43 |         3580   |
| control      | vulnerabilities          |                  1074 |              625 |                        0.581937  |    2.76723    |                 0 |          137   |
| treatment    | bugs                     |                   959 |              375 |                        0.391032  |  -47.5662     |                 2 |         3864   |
| treatment    | code_smells              |                   959 |               84 |                        0.0875912 |  162.788      |                25 |         8448   |
| treatment    | cognitive_complexity     |                   955 |              824 |                        0.862827  | -199.429      |                 0 |        29442   |
| treatment    | comment_lines_density    |                   955 |              771 |                        0.80733   |    0.0442932  |                 0 |           15.7 |
| treatment    | duplicated_lines_density |                   955 |              746 |                        0.781152  |   -0.283246   |                 0 |           46.6 |
| treatment    | ncloc                    |                   955 |              515 |                        0.539267  |  486.925      |                 0 |       133392   |
| treatment    | static_analysis_warnings |                   959 |               61 |                        0.0636079 |  120.445      |                28 |        12308   |
| treatment    | technical_debt           |                   959 |               61 |                        0.0636079 |  272.363      |               111 |        56847   |
| treatment    | vulnerabilities          |                   959 |              421 |                        0.438999  |    5.22315    |                 1 |           87   |
