# Progress Report: SonarQube Full-Panel Quality Measurement Pipeline

## Project Context

This work is part of the replication and extension pipeline for the study on whether Cursor AI adoption increases short-term development velocity and long-term code complexity in open-source projects. The current goal is to construct a matched monthly panel and attach SonarQube-based software quality metrics to each repository-month observation.

The main analysis dataset is a matched treatment-control panel with Cursor-adopting Python repositories and propensity-score-matched never-treated control repositories. The panel is designed for later difference-in-differences analysis, especially the Borusyak et al. imputation estimator.

## Completed Work So Far

### 1. Treatment and Control Repository Panel Construction

We prepared a monthly matched panel using 13 Cursor-adopting Python treatment repositories and 38 matched control repositories.

The balanced activity panel contains:

* 738 total repository-month rows
* 13 treatment repositories
* 38 control repositories
* 208 treatment repository-month rows
* 530 control repository-month rows
* Monthly coverage from January 2024 to August 2025, with repository-specific start months based on available commit history

The panel includes zero-commit months by carrying forward the latest commit available at the end of each month. This is important because the main DiD analysis should not be limited only to active commit months.

### 2. Historical Commit Lookup for SonarQube Input

A direct join with monthly Git activity data only provided `latest_commit` for active months. To support SonarQube measurement for zero-commit months, we used historical lookup based on the latest commit available as of each month-end.

The final SonarQube input source contains all 738 balanced panel rows with non-missing checkout commits.

This produced separate full scan inputs:

* Treatment scan input:

  * Path: `tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv`
  * Rows: 208
  * Repositories: 13
  * Missing latest commits: 0

* Control scan input:

  * Path: `tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv`
  * Rows: 530
  * Repositories: 38
  * Missing latest commits: 0

The control input was verified with `wc -l`, showing 531 lines including the header, which corresponds to 530 data rows.

### 3. SonarQube Smoke Tests

Before running the full scans, we verified the SonarQube infrastructure and scanner pipeline.

The local SonarQube server was confirmed to be available and authenticated. A tiny project scan completed successfully and returned expected metrics such as bugs, code smells, duplicated line density, cognitive complexity, and non-comment lines of code.

We then ran historical smoke tests on both treatment and control repositories:

* Treatment smoke test:

  * Repository: `VRSEN/agency-swarm`
  * Months: 2024-09, 2024-10, 2024-11
  * Result: all selected months scanned successfully and returned complete metrics

* Control smoke test:

  * Repository: `robotframework/statuschecker`
  * Months: 2024-01, 2024-02, 2024-03
  * Result: all selected months scanned successfully and returned complete metrics

These smoke tests confirmed that the full historical checkout and SonarQube metric extraction process works for both treatment and control clone directories.

### 4. Treatment Full SonarQube Scan

The full treatment scan was executed using:

* Script: `run6d-sonarqube-full-treatment.sh`
* Input: `tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv`
* Output: `tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv`
* Clone directory: `../ai_code_complexity_study_repo_dataset`
* Log file pattern: `logs/run6d-sonarqube-full-treatment-*.log`

The treatment full scan completed successfully.

Coverage summary:

* Rows: 208
* Repositories: 13
* Bugs: 208 / 208
* Vulnerabilities: 208 / 208
* Code smells: 208 / 208
* Technical debt: 208 / 208
* NCLOC: 207 / 208
* Duplicated line density: 207 / 208
* Comment line density: 207 / 208
* Cognitive complexity: 207 / 208

One row had missing source-size and complexity metrics:

* Repository: `kenshiro-o/nagato-ai`
* Month: 2024-03
* Commit: `cb13400a6f9b7dbdc9b83a080a09145a536a6111`

This was investigated and determined to be expected. The commit was the initial commit and contained only `.gitignore`, `LICENSE`, and `README.md`, with no analyzable source files. SonarQube returned zero bugs, vulnerabilities, code smells, and technical debt, but did not return NCLOC or complexity-related metrics because there was no source code to analyze.

This row should be handled in the later merge or analysis-preparation stage, not inside the raw scanner. A reasonable policy is to preserve raw missing values but create analysis-ready variables where source-less commits are treated as zero source code and zero complexity.

### 5. Incremental Save Patch for Long Control Scan

Before starting the full control scan, we improved `proc_scripts/run_sonarqube_v2.py` to support repo-level incremental saving.

The patch added:

* A new `--incremental-save` command-line option
* A `save_progress()` function
* Repo-level CSV saving after each completed repository
* Partial progress preservation if the process is interrupted
* Compatibility with the existing `--num-processes 1` workflow

Validation completed:

* `python -m py_compile proc_scripts/run_sonarqube_v2.py`: passed
* `python proc_scripts/run_sonarqube_v2.py --help`: confirmed that `--incremental-save` is available

This patch is important because the full control scan contains 530 repository-month rows. Without incremental saving, an interruption could lose all in-memory results before the final CSV write.

### 6. Control Full SonarQube Scan Started

The full control scan was started using:

* Script: `run6e-sonarqube-full-control.sh`
* Input: `tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv`
* Output: `tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv`
* Clone directory: `../ai_code_complexity_control_repo_dataset`
* Mode: repo-level incremental save
* Log file pattern: `logs/run6e-sonarqube-full-control-*.log`

Current observed progress:

* Total rows: 530
* Total repositories: 38
* Metric rows saved so far: 7 / 530
* Repositories with at least one saved NCLOC metric: 1

The first completed control repository is:

* `Arcanum-Sec/msftrecon`

The next repository being processed is:

* `BytedanceSpeech/seed-tts-eval`

The log confirms that after completing `Arcanum-Sec/msftrecon`, the script saved progress to:

`tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv`

This confirms that repo-level incremental saving is functioning as intended.

## Current Status

The control full scan is currently in progress. If it continues uninterrupted, it is expected to complete in approximately 2.5 to 4 hours based on the treatment full-scan runtime and the larger control workload.

The treatment scan required approximately 53 minutes for 208 rows, which is roughly 15.3 seconds per repository-month. The control scan has 530 rows, giving a simple estimate of about 2 hours and 15 minutes. Because some control repositories are larger, a safer expected runtime is around 2.5 to 3 hours, with a conservative upper bound of about 4 hours.

## Remaining Next Steps

1. Let the full control SonarQube scan complete.
2. Run coverage checks on the control scanned output.
3. Investigate any missing control metrics, especially source-less commits or failed scans.
4. Merge treatment and control SonarQube outputs into the balanced panel.
5. Compute derived quality outcomes, especially:

   * `static_analysis_warnings = bugs + vulnerabilities + code_smells`
   * `log1p(static_analysis_warnings)`
   * `log1p(cognitive_complexity)`
   * `duplicated_lines_density`
   * `log1p(technical_debt)`
6. Preserve raw SonarQube metrics and create analysis-ready versions separately.
7. Run Borusyak imputation-based DiD analysis for quality outcomes.
8. Optionally collect detailed SonarQube warning-level data for descriptive or appendix-style analysis after aggregate quality analysis is complete.

## Notes and Decisions

The SonarQube scanner should continue collecting raw metrics only. Derived metrics such as `static_analysis_warnings` should be computed during the merge or analysis-preparation stage.

Detailed SonarQube warnings are not the main DiD outcome. They are useful for descriptive analysis by rule, type, or severity, but the main quality outcomes should be based on aggregate repository-month metrics.

For source-less commits, missing source-size and complexity metrics are expected. These should be documented and handled during analysis preparation rather than treated as scan failures.
