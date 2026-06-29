# SonarQube Analysis Results for Treatment and Control Repositories

## 1. Overview

This report summarizes the SonarQube analysis results for the JavaScript/TypeScript matched Difference-in-Differences dataset. The analysis was performed separately for treatment repositories and matched control repositories. For each repository-month observation, the pipeline checked out the historical month-end commit and collected SonarQube quality metrics.

The SonarQube scan was completed successfully for both treatment and control datasets. Overall metric coverage is high, ranging from approximately 98.47% to 99.72% depending on the metric and dataset.

## 2. Input Datasets

### Treatment Dataset

The treatment SonarQube input contained:

* Rows: 5,028 repository-month observations
* Repositories: 380
* Time range: 2024-01 to 2025-08
* Missing `latest_commit`: 0
* Duplicate repository-month rows: 0

### Control Dataset

The control SonarQube input contained:

* Rows: 7,242 repository-month observations
* Repositories: 447
* Time range: 2024-01 to 2025-08
* Missing `latest_commit`: 0
* Duplicate repository-month rows: 0

The control input-output consistency check confirmed that all repository-month pairs were preserved:

* Input rows: 7,242
* Output rows: 7,242
* Input repositories: 447
* Output repositories: 447
* Input pairs missing in output: 0
* Output pairs not in input: 0

## 3. Treatment SonarQube Coverage

The treatment scan completed successfully and produced the following metric coverage:

| Metric                     | Non-null | Missing | Total | Coverage |
| -------------------------- | -------: | ------: | ----: | -------: |
| `ncloc`                    |    4,957 |      71 | 5,028 |   98.59% |
| `bugs`                     |    4,973 |      55 | 5,028 |   98.91% |
| `vulnerabilities`          |    4,973 |      55 | 5,028 |   98.91% |
| `code_smells`              |    4,973 |      55 | 5,028 |   98.91% |
| `duplicated_lines_density` |    4,957 |      71 | 5,028 |   98.59% |
| `comment_lines_density`    |    4,957 |      71 | 5,028 |   98.59% |
| `cognitive_complexity`     |    4,951 |      77 | 5,028 |   98.47% |
| `technical_debt`           |    4,973 |      55 | 5,028 |   98.91% |

The treatment dataset has strong coverage across all SonarQube metrics. The lowest coverage is for `cognitive_complexity`, with 98.47% non-null observations.

## 4. Control SonarQube Coverage

The control scan also completed successfully and produced the following metric coverage:

| Metric                     | Non-null | Missing | Total | Coverage |
| -------------------------- | -------: | ------: | ----: | -------: |
| `ncloc`                    |    7,187 |      55 | 7,242 |   99.24% |
| `bugs`                     |    7,222 |      20 | 7,242 |   99.72% |
| `vulnerabilities`          |    7,222 |      20 | 7,242 |   99.72% |
| `code_smells`              |    7,222 |      20 | 7,242 |   99.72% |
| `duplicated_lines_density` |    7,187 |      55 | 7,242 |   99.24% |
| `comment_lines_density`    |    7,187 |      55 | 7,242 |   99.24% |
| `cognitive_complexity`     |    7,187 |      55 | 7,242 |   99.24% |
| `technical_debt`           |    7,222 |      20 | 7,242 |   99.72% |

The control dataset has slightly higher metric coverage than the treatment dataset. The lowest coverage is 99.24%, observed for size, density, and complexity metrics.

## 5. Combined Treatment-Control Coverage

Across both treatment and control datasets, the SonarQube scanned dataset contains:

* Treatment rows: 5,028
* Control rows: 7,242
* Total rows: 12,270

Combined coverage is as follows:

| Metric                     | Non-null | Missing |  Total | Coverage |
| -------------------------- | -------: | ------: | -----: | -------: |
| `ncloc`                    |   12,144 |     126 | 12,270 |   98.97% |
| `bugs`                     |   12,195 |      75 | 12,270 |   99.39% |
| `vulnerabilities`          |   12,195 |      75 | 12,270 |   99.39% |
| `code_smells`              |   12,195 |      75 | 12,270 |   99.39% |
| `duplicated_lines_density` |   12,144 |     126 | 12,270 |   98.97% |
| `comment_lines_density`    |   12,144 |     126 | 12,270 |   98.97% |
| `cognitive_complexity`     |   12,138 |     132 | 12,270 |   98.92% |
| `technical_debt`           |   12,195 |      75 | 12,270 |   99.39% |

Overall, the combined dataset has high metric availability. The lowest combined coverage is for `cognitive_complexity` at 98.92%.

## 6. Control Missing Metrics

A detailed missing-metric check was performed for the control dataset.

Rows with at least one missing metric:

* Rows with any missing metric: 55
* Repositories with any missing metric: 11

Missing metric distribution:

| Missing Metric Count | Rows |
| -------------------: | ---: |
|                    4 |   35 |
|                    8 |   20 |

The top repositories with missing control metrics were:

| Repository                      | Missing Rows |
| ------------------------------- | -----------: |
| `rudderlabs/rudder-transformer` |           20 |
| `Hardcoding-1992/FeatherJS`     |           11 |
| `Adamant-im/developers`         |            9 |
| `yaming116/docker-pull-proxy`   |            5 |
| `zeke/yolox`                    |            3 |
| `aukilabs/posemesh`             |            2 |
| `AgentCoord/AgentCoord`         |            1 |
| `mpaiva/wcag-tokens`            |            1 |
| `keizerworks/invoicen`          |            1 |
| `MultiMote/niimbluelib`         |            1 |
| `zenml-io/vscode-zenml`         |            1 |

The most important missing-metric case is `rudderlabs/rudder-transformer`, which failed for all 20 months due to a SonarQube parsing error involving a generic test execution report file:

`reports/sonar/results-report.xml`

These 20 observations should remain in the dataset with missing SonarQube metrics rather than being imputed or dropped at this stage.

## 7. Control `ncloc == 0` Rows

The control dataset also contains a small number of rows where SonarQube returned metrics but `ncloc` was zero.

* Rows with `ncloc == 0`: 23
* Repositories with `ncloc == 0`: 2

Affected repositories:

| Repository                     | Rows with `ncloc == 0` |
| ------------------------------ | ---------------------: |
| `59de44955ebd/twitter-to-bsky` |                     20 |
| `Fevol/obsidian-typings`       |                      3 |

These rows should not be deleted during the merge step. Instead, they should be retained with a flag such as `sonar_ncloc_zero = 1`. A robustness analysis can later exclude `ncloc == 0` observations if needed.

## 8. Metric Sanity Checks

The control dataset passed the basic metric sanity checks:

* No negative values were found for any metric.
* `duplicated_lines_density` values were within the range [0, 100].
* `comment_lines_density` values were within the range [0, 100].

The descriptive statistics show a right-skewed distribution, which is expected because the control dataset includes both small repositories and very large repositories.

Selected control metric summary:

| Metric                     |      Mean |   Median | 95th Percentile |        Max |
| -------------------------- | --------: | -------: | --------------: | ---------: |
| `ncloc`                    | 16,366.42 | 2,656.00 |       72,768.20 | 586,723.00 |
| `bugs`                     |     20.00 |     2.00 |           89.00 |   1,312.00 |
| `vulnerabilities`          |      3.96 |     0.00 |            8.00 |     479.00 |
| `code_smells`              |    547.43 |    54.00 |        1,920.60 |  62,822.00 |
| `duplicated_lines_density` |      7.70 |     2.10 |           33.17 |      88.90 |
| `comment_lines_density`    |      7.10 |     4.60 |           19.90 |     100.00 |
| `cognitive_complexity`     |  1,611.09 |   163.00 |        5,987.80 | 151,064.00 |
| `technical_debt`           |  3,216.30 |   291.00 |       11,846.95 | 375,346.00 |

## 9. Backup Status

The control results were backed up successfully under:

`tmp_jsts_test/data/jsts_sonarqube_main/backups/after_control_20260629-133006`

The backup contains:

* `control_ts_repos_monthly.csv`
* `control_ts_repos_monthly_scanned.csv`
* `run9b_sonarqube_jsts_control_20260627-003624.log`
* `sonarqube_metric_coverage_treatment_control.csv`

The treatment results were previously backed up under:

`tmp_jsts_test/data/jsts_sonarqube_main/backups/after_treatment_20260627-003322`

## 10. Interpretation

The SonarQube data collection step was successful for both treatment and control repositories. The scan preserved all repository-month rows and achieved high metric coverage. The few missing values are concentrated in a small number of repositories, especially `rudderlabs/rudder-transformer`, where SonarQube failed due to a repository-specific report parsing issue.

The current dataset is ready for the next pipeline step: merging SonarQube metrics into the final matched Difference-in-Differences panels.

The recommended merge policy is:

1. Preserve all repository-month rows.
2. Merge SonarQube metrics by `repo_name` and `month`.
3. Keep missing SonarQube metrics as missing values.
4. Add a flag for rows with any missing SonarQube metric.
5. Add a flag for rows with `ncloc == 0`.
6. Do not impute missing quality metrics.
7. Use robustness checks later for:

   * observations with complete SonarQube metrics only;
   * observations with `ncloc > 0`;
   * exclusion of the `rudderlabs/rudder-transformer` failed scan case.

## 11. Next Step

The next step is to implement `run9c` to merge the scanned SonarQube treatment and control outputs into the final matched DiD panels.

The expected inputs are:

* `tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv`
* `tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean.csv`
* `tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/ts_repos_monthly_scanned.csv`
* `tmp_jsts_test/data/jsts_sonarqube_main/control/data/ts_repos_monthly_scanned.csv`

The expected outputs should include panel files with appended SonarQube metrics and QC flags.
