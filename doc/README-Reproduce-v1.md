# Reusable Workflow Report: Difference-in-Differences Analysis for GitHub Repository Velocity and Quality

## 1. Purpose

This report documents a reusable workflow for analyzing the effect of AI-tool adoption on GitHub repositories using Difference-in-Differences (DiD). The current experiment focused on a selected set of GitHub repositories, including Python repositories, but the workflow is intended to be reusable for other GitHub repository sets.

The workflow supports two related DiD analyses:

1. **Velocity DiD analysis**
   Measures whether AI-tool adoption changes repository development activity, such as commit activity, code churn, file changes, or other time-series activity outcomes produced from Git history.

2. **Quality DiD analysis**
   Measures whether AI-tool adoption changes software quality indicators, especially SonarQube-derived metrics such as bugs, vulnerabilities, code smells, cognitive complexity, duplicated-line density, maintainability remediation effort, and technical debt.

The main design principle is to reuse the existing shell-script wrappers whenever possible. These wrappers already encode the sequence of candidate selection, repository cloning, repository analysis, treatment/control construction, panel creation, SonarQube scanning, quality-panel merging, and Borusyak-style DiD estimation.

## 2. High-Level Directory and File Organization

A future researcher should keep the project organized around four major areas: wrapper scripts, Python processing scripts, R DiD notebooks, and generated experiment data.

```text
ai_code_complexity_study/
├── run*.sh
│   ├── run2*.sh      # SonarQube setup and smoke tests
│   ├── run3*.sh      # SonarQube warning collection smoke test
│   ├── run4*.sh      # AI adoption candidate selection and treatment repo analysis
│   ├── run5*.sh      # Control group construction, panel creation, velocity DiD
│   └── run6*.sh      # SonarQube full scan, quality panel, quality DiD
│
├── proc_scripts/
│   ├── find_repo_pre_post_ai_adoption.py
│   ├── clone_repos_v2.py
│   ├── check_python_repo_clone.py
│   ├── analyze_repos_v2.py
│   ├── check_time_of_event_and_adoption.py
│   ├── find_control_groups_v2.py
│   ├── prepare_panel_event_v2.py
│   ├── run_sonarqube_v2.py
│   ├── collect_sonarqube_warnings_v2.py
│   ├── merge-sonarqube-panel.py
│   ├── check-sonarqube-panel.py
│   ├── prepare-quality-did-input.py
│   └── summarize-borusyak-quality-results.py
│
├── proc_r/
│   ├── DiffInDiffBorusyak_v2.Rmd
│   └── DiffInDiffBorusyak_quality_v2.Rmd
│
├── data_baseline_backup/
│   └── baseline repository-level panel data used for candidate selection
│
├── tmp_adoption_test/data/
│   ├── top_100_clone_candidates.csv
│   ├── top_100_clone_candidates_all_eligible.csv
│   ├── ai_adopt_repo_python.csv
│   ├── control_repos_to_clone_v2.csv
│   ├── control_repos_to_clone_v2.txt
│   ├── matched_controls_v2_pairs.csv
│   ├── matched_controls_v2_treatment_only.csv
│   │
│   └── python_did_test/
│       ├── ts_repos_monthly.csv
│       ├── ai_adoption_dates.csv
│       ├── adoption_month_check.csv
│       ├── panel_event_monthly_matched_v2.csv
│       ├── panel_event_monthly_matched_v2_balanced.csv
│       ├── activity_did_smoke_borusyak_v2/
│       │   └── velocity DiD outputs
│       │
│       ├── sonarqube_full_treatment/data/
│       │   ├── ts_repos_monthly.csv
│       │   └── ts_repos_monthly_scanned.csv
│       │
│       ├── sonarqube_full_control/data/
│       │   ├── ts_repos_monthly.csv
│       │   └── ts_repos_monthly_scanned.csv
│       │
│       ├── panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
│       ├── panel_event_monthly_matched_v2_balanced_quality_did_input.csv
│       │
│       └── quality_did_borusyak_v2/
│           ├── borusyak_quality_v2_static_effects.csv
│           ├── borusyak_quality_v2_dynamic_effects.csv
│           ├── borusyak_quality_v2_panel_checks.csv
│           ├── borusyak_quality_v2_report_summary.csv
│           ├── borusyak_quality_v2_static_effects_with_pct.csv
│           └── borusyak_quality_v2_dynamic_pretrend_summary.csv
│
├── logs/
│   └── timestamped logs from long-running wrappers
│
├── ../ai_code_complexity_study_repo_dataset/
│   └── cloned treatment repositories
│
└── ../ai_code_complexity_control_repo_dataset/
    └── cloned control repositories
```

The paths above are based on the current wrappers. A future researcher can change repository roots, output directories, and input files by overriding the environment variables used in the shell scripts.

## 3. Reusable Workflow Overview

The complete workflow has two branches after treatment/control panel construction:

```text
Baseline GitHub repository data
        |
        v
AI adoption candidate selection
        |
        v
Clone and validate treatment repositories
        |
        v
Analyze treatment repository histories
        |
        v
Find and clone matched control repositories
        |
        v
Analyze control repository histories
        |
        v
Create matched treatment/control panel
        |
        +-----------------------------+
        |                             |
        v                             v
Velocity DiD analysis          SonarQube quality scan
        |                             |
        v                             v
Activity DiD results           Merge quality metrics into panel
                                      |
                                      v
                              Quality DiD input
                                      |
                                      v
                              Quality DiD results
```

## 4. Recommended Wrapper Execution Order

### 4.1 SonarQube preparation and smoke testing

Use these scripts before full quality analysis:

```bash
./run2-sonarqube-server.sh
./run2a-sonarqube-smoke-test.sh
./run2c-sonarqube-small-batch-test.sh
./run3a-detect-prog-warnings.sh
```

Purpose:

* Start a local SonarQube server.
* Test SonarQube connection, scanner configuration, tiny-project scan, metrics API, and issue API.
* Run a small batch scan before launching the full treatment/control quality scan.
* Verify that warning-level data can be collected.

Important clarification: in the current `run2a-sonarqube-smoke-test.sh`, `RUN_INFRA_TESTS` is initialized to `1`, and the script exits after infrastructure tests. If the intention is to continue to the one-repository scan, the wrapper should be edited to support a `--skip-infra-tests` option or set `RUN_INFRA_TESTS=0`.

### 4.2 Treatment group selection and analysis

Use:

```bash
./run4a-detect-ai-adoption.sh
./run4b-detect-ai-adoption.sh
./run4c-analyze-repo.sh
```

Purpose:

1. `run4a-detect-ai-adoption.sh` selects candidate repositories with enough pre- and post-adoption observations.
2. `run4b-detect-ai-adoption.sh` runs `run4a` in clone mode.
3. `run4c-analyze-repo.sh` analyzes cloned treatment repositories and verifies the relationship between the selected event month and detected adoption month.

The current treatment selection emphasizes AI/Cursor adoption evidence and then filters cloned repositories to Python repositories. For a future study on any GitHub repositories, the Python-specific filtering step should be parameterized, renamed, or generalized.

### 4.3 Control group construction and analysis

Use:

```bash
./run5a-find-control-group.sh
./run5b-analyze-repo-control-group.sh
```

Purpose:

1. Identify candidate control repositories.
2. Match controls to treated repositories.
3. Clone selected control repositories.
4. Analyze control repository histories using the same `analyze_repos_v2.py` logic used for treatment repositories.

The control group should be constructed from repositories that did not adopt the AI tool during the relevant observation window but have comparable pre/post coverage, language characteristics, and repository activity where possible.

### 4.4 Matched panel creation

Use:

```bash
./run5c-prepare-panel-event.sh
```

Purpose:

* Combine treatment metadata, matched treatment-control pairs, treatment time series, and control time series.
* Create an event-time panel.
* Create a balanced panel for DiD estimation.

Key output:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

### 4.5 Velocity DiD analysis

Use:

```bash
./run5d-did-borusyak.sh
```

Purpose:

* Render `proc_r/DiffInDiffBorusyak_v2.Rmd`.
* Estimate Borusyak-style DiD effects for repository activity or velocity outcomes.

Expected output directory:

```text
tmp_adoption_test/data/python_did_test/activity_did_smoke_borusyak_v2/
```

This branch answers questions such as:

* Did AI-tool adoption increase or decrease repository activity?
* Did treated repositories experience a post-adoption shift in commits, churn, or other velocity outcomes relative to matched controls?
* Are there visible pre-trend violations before adoption?

### 4.6 Quality DiD analysis

Use:

```bash
./run6c-create-input.sh
./run6d-sonarqube-full-treatment.sh
./run6e-sonarqube-full-control.sh
./run6f-check-sonarqube-coverage.sh
./run6g-merge-sonarqube-panel.sh
./run6h-check-sonarqube-panel.sh
./run6i-prepare-quality-did-input.sh
./run6j-did-borusyak-quality.sh
./run6k-summarize-borusyak-quality-results.sh
```

Purpose:

1. Create SonarQube scan inputs for treatment and control repositories.
2. Run full SonarQube scans for treatment repositories.
3. Run full SonarQube scans for control repositories.
4. Check scan coverage.
5. Merge SonarQube metrics into the balanced DiD panel.
6. Check missingness and quality outcome coverage.
7. Prepare quality-specific DiD input.
8. Run Borusyak-style DiD for quality outcomes.
9. Summarize static effects, dynamic effects, and pre-trend checks.

This branch answers questions such as:

* Did AI-tool adoption affect code smells, bugs, vulnerabilities, cognitive complexity, duplication, or technical debt?
* Are quality changes different from activity changes?
* Do quality effects appear immediately after adoption or gradually over event time?
* Are quality results supported by sufficient SonarQube coverage?

## 5. Input and Output Visualization

### 5.1 Treatment repository pipeline

```text
data_baseline_backup/
        |
        v
run4a-detect-ai-adoption.sh
        |
        +--> top_100_clone_candidates.csv
        +--> top_100_clone_candidates_all_eligible.csv
        |
        v
run4b-detect-ai-adoption.sh
        |
        +--> cloned treatment repositories
        +--> logs/run4a_clone_log_*.csv
        +--> ai_adopt_repo_python.csv
        |
        v
run4c-analyze-repo.sh
        |
        +--> python_did_test/ts_repos_monthly.csv
        +--> python_did_test/ai_adoption_dates.csv
        +--> python_did_test/adoption_month_check.csv
```

### 5.2 Control repository pipeline

```text
matched-control selection inputs
        |
        v
run5a-find-control-group.sh
        |
        +--> matched_controls_v2_pairs.csv
        +--> matched_controls_v2_treatment_only.csv
        +--> control_repos_to_clone_v2.csv
        +--> control_repos_to_clone_v2.txt
        +--> cloned control repositories
        |
        v
run5b-analyze-repo-control-group.sh
        |
        +--> python_control_did_test/ts_repos_monthly.csv
```

### 5.3 Velocity DiD pipeline

```text
treatment time series
control time series
matched pairs
treatment metadata
        |
        v
run5c-prepare-panel-event.sh
        |
        +--> panel_event_monthly_matched_v2.csv
        +--> panel_event_monthly_matched_v2_balanced.csv
        |
        v
run5d-did-borusyak.sh
        |
        +--> activity_did_smoke_borusyak_v2/
```

### 5.4 Quality DiD pipeline

```text
panel_event_monthly_matched_v2_balanced.csv
        |
        v
run6c-create-input.sh
        |
        +--> sonarqube_full_treatment/data/ts_repos_monthly.csv
        +--> sonarqube_full_control/data/ts_repos_monthly.csv
        |
        +-------------------------------+
        |                               |
        v                               v
run6d-sonarqube-full-treatment.sh   run6e-sonarqube-full-control.sh
        |                               |
        v                               v
treatment scanned CSV              control scanned CSV
        |                               |
        +---------------+---------------+
                        |
                        v
run6g-merge-sonarqube-panel.sh
                        |
                        +--> panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
                        +--> panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv
                        |
                        v
run6h-check-sonarqube-panel.sh
                        |
                        +--> panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv
                        +--> panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv
                        |
                        v
run6i-prepare-quality-did-input.sh
                        |
                        +--> panel_event_monthly_matched_v2_balanced_quality_did_input.csv
                        +--> panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv
                        |
                        v
run6j-did-borusyak-quality.sh
                        |
                        +--> quality_did_borusyak_v2/
                        |
                        v
run6k-summarize-borusyak-quality-results.sh
                        |
                        +--> borusyak_quality_v2_report_summary.csv
                        +--> borusyak_quality_v2_static_effects_with_pct.csv
                        +--> borusyak_quality_v2_dynamic_pretrend_summary.csv
```

## 6. Main CSV Files and Column Explanations

### 6.1 Candidate and treatment-selection files

#### `top_100_clone_candidates.csv`

Purpose: candidate AI-adopting repositories selected from the baseline data.

Important columns usually include:

| Column                               | Meaning                                        |
| ------------------------------------ | ---------------------------------------------- |
| `rank`                               | Candidate rank based on the ranking criterion. |
| `repo_name`                          | GitHub repository in `OWNER/REPO` format.      |
| `event_month`                        | Candidate AI-adoption event month.             |
| `pre_panel_months`                   | Number of usable months before adoption.       |
| `post_panel_months`                  | Number of usable months after adoption.        |
| `repo_primary_language`              | Primary language reported for the repository.  |
| `high_contributor` or ranking metric | Metric used to prioritize repositories.        |

#### `ai_adopt_repo_python.csv`

Purpose: validated treatment repositories after cloning and language filtering.

Important columns usually include:

| Column                  | Meaning                                                                             |
| ----------------------- | ----------------------------------------------------------------------------------- |
| `repo_name`             | Treatment repository name.                                                          |
| `event_month`           | Event month used for DiD alignment.                                                 |
| `repo_primary_language` | Repository primary language.                                                        |
| `status`                | Clone status such as `cloned`, `skipped_existing`, `updated_existing`, or `failed`. |
| `target_dir`            | Local directory where the repository was cloned.                                    |
| `note`                  | Diagnostic information from clone or validation.                                    |

#### `ai_adoption_dates.csv`

Purpose: detected AI-adoption timing from repository history.

Important columns usually include:

| Column            | Meaning                                                                 |
| ----------------- | ----------------------------------------------------------------------- |
| `repo_name`       | Repository name.                                                        |
| `adoption_month`  | Month where AI-tool adoption was detected from repository evidence.     |
| `adoption_commit` | Commit associated with adoption evidence, if available.                 |
| `evidence`        | Textual or file-based signal used for adoption detection, if available. |

#### `adoption_month_check.csv`

Purpose: comparison between selected `event_month` and detected `adoption_month`.

Important columns usually include:

| Column             | Meaning                                                   |
| ------------------ | --------------------------------------------------------- |
| `repo_name`        | Repository name.                                          |
| `event_month`      | Event month from candidate selection.                     |
| `adoption_month`   | Adoption month detected from cloned repository history.   |
| `match_status`     | Whether the two dates match or are acceptably close.      |
| `month_difference` | Difference between candidate and detected adoption month. |

### 6.2 Control-group files

#### `matched_controls_v2_pairs.csv`

Purpose: matched treatment-control repository pairs.

Important columns usually include:

| Column                | Meaning                                                      |
| --------------------- | ------------------------------------------------------------ |
| `treatment_repo_name` | Treated repository.                                          |
| `control_repo_name`   | Matched control repository.                                  |
| `event_month`         | Event month inherited from the treated repository.           |
| `match_rank`          | Rank of the selected control among possible controls.        |
| `match_distance`      | Distance or difference score used in matching, if available. |

#### `matched_controls_v2_treatment_only.csv`

Purpose: treatment metadata used when preparing the final event panel.

Important columns usually include:

| Column                  | Meaning                                |
| ----------------------- | -------------------------------------- |
| `repo_name`             | Treated repository.                    |
| `event_month`           | Treatment event month.                 |
| `pre_panel_months`      | Number of pre-treatment observations.  |
| `post_panel_months`     | Number of post-treatment observations. |
| `repo_primary_language` | Repository language.                   |

#### `control_repos_to_clone_v2.csv` and `control_repos_to_clone_v2.txt`

Purpose: repositories selected for control cloning and analysis.

Important columns usually include:

| Column                   | Meaning                                                        |
| ------------------------ | -------------------------------------------------------------- |
| `repo_name`              | Control repository to clone.                                   |
| `repo_primary_language`  | Control repository language, if available.                     |
| `matched_treatment_repo` | Treated repository associated with this control, if available. |
| `event_month`            | Assigned event month from the matched treatment repository.    |

### 6.3 Repository time-series files

#### `python_did_test/ts_repos_monthly.csv`

Purpose: treatment repository monthly time series generated from Git history.

Minimum expected columns:

| Column          | Meaning                                 |
| --------------- | --------------------------------------- |
| `repo_name`     | Repository name.                        |
| `month`         | Monthly time period.                    |
| `latest_commit` | Latest commit hash used for that month. |

Additional velocity columns depend on `analyze_repos_v2.py`. They may include commit counts, contributor counts, changed files, additions, deletions, churn, or other repository activity outcomes.

#### `python_control_did_test/ts_repos_monthly.csv`

Purpose: control repository monthly time series generated using the same logic as treatment repositories.

Expected columns are parallel to the treatment time-series file so that treatment and control outcomes can be combined in the same panel.

### 6.4 Matched panel files

#### `panel_event_monthly_matched_v2.csv`

Purpose: unbalanced event-time panel combining treatment and control observations.

Important columns usually include:

| Column            | Meaning                                        |
| ----------------- | ---------------------------------------------- |
| `repo_name`       | Repository name.                               |
| `dataset_source`  | `treatment` or `control`.                      |
| `time` or `month` | Calendar month.                                |
| `event_month`     | Assigned treatment event month.                |
| `event_time`      | Relative month, such as `month - event_month`. |
| `treated`         | Indicator for treatment repository.            |
| `post`            | Indicator for post-event period.               |
| outcome columns   | Velocity outcomes from repository history.     |

#### `panel_event_monthly_matched_v2_balanced.csv`

Purpose: balanced event-time panel used for DiD estimation.

This file should preserve comparable pre/post windows across treatment and control repositories. The balanced file is preferred for the main DiD analysis because it reduces missing-window inconsistencies.

### 6.5 SonarQube scan input and output files

#### `sonarqube_full_treatment/data/ts_repos_monthly.csv`

Purpose: treatment scan input created by `run6c-create-input.sh`.

Columns:

| Column          | Meaning                          |
| --------------- | -------------------------------- |
| `repo_name`     | Treatment repository.            |
| `month`         | Month to scan.                   |
| `latest_commit` | Commit checked out for the scan. |

#### `sonarqube_full_control/data/ts_repos_monthly.csv`

Purpose: control scan input created by `run6c-create-input.sh`.

Columns:

| Column          | Meaning                          |
| --------------- | -------------------------------- |
| `repo_name`     | Control repository.              |
| `month`         | Month to scan.                   |
| `latest_commit` | Commit checked out for the scan. |

#### `sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv`

Purpose: treatment repositories after SonarQube scanning.

Important columns include:

| Column                                                | Meaning                                                |
| ----------------------------------------------------- | ------------------------------------------------------ |
| `repo_name`                                           | Repository name.                                       |
| `month`                                               | Scan month.                                            |
| `latest_commit`                                       | Commit scanned.                                        |
| `ncloc`                                               | Non-comment lines of code.                             |
| `bugs`                                                | SonarQube bug count.                                   |
| `vulnerabilities`                                     | SonarQube vulnerability count.                         |
| `code_smells`                                         | SonarQube code smell count.                            |
| `static_analysis_warnings`                            | Derived total: `bugs + vulnerabilities + code_smells`. |
| `duplicated_lines_density`                            | Percentage of duplicated lines.                        |
| `comment_lines_density`                               | Percentage of comment lines.                           |
| `cognitive_complexity`                                | SonarQube cognitive complexity metric.                 |
| `software_quality_maintainability_remediation_effort` | Maintainability remediation effort.                    |
| `technical_debt`                                      | Technical debt measure.                                |

#### `sonarqube_full_control/data/ts_repos_monthly_scanned.csv`

Purpose: control repositories after SonarQube scanning.

Columns should parallel the treatment scanned file.

### 6.6 SonarQube warning files

#### `sonarqube_warnings.csv`

Purpose: detailed warning or issue records collected from SonarQube.

Important columns may include:

| Column          | Meaning                                                |
| --------------- | ------------------------------------------------------ |
| `repo_name`     | Repository name.                                       |
| `month`         | Month or time period.                                  |
| `latest_commit` | Commit scanned.                                        |
| `issue_key`     | SonarQube issue identifier.                            |
| `rule_key`      | SonarQube rule identifier.                             |
| `severity`      | Warning severity.                                      |
| `type`          | Issue type, such as bug, vulnerability, or code smell. |
| `component`     | File or component containing the issue.                |
| `line`          | Line number, if available.                             |
| `message`       | SonarQube issue message.                               |

#### `sonarqube_warning_definitions.csv`

Purpose: definitions of SonarQube rules appearing in the warning file.

Important columns may include:

| Column        | Meaning                    |
| ------------- | -------------------------- |
| `rule_key`    | SonarQube rule identifier. |
| `name`        | Rule name.                 |
| `severity`    | Default rule severity.     |
| `type`        | Rule type.                 |
| `description` | Rule explanation.          |

### 6.7 Quality merged panel and DiD input files

#### `panel_event_monthly_matched_v2_balanced_with_sonarqube.csv`

Purpose: balanced treatment/control event panel with SonarQube metrics merged in.

This file is the main bridge between the velocity DiD panel and quality DiD analysis.

#### `panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv`

Purpose: quality-control file from the merge step.

This file should be inspected to confirm whether treatment and control observations matched successfully to SonarQube scan outputs.

#### `panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv`

Purpose: summary of available SonarQube outcomes.

This file helps identify which quality metrics have sufficient coverage.

#### `panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv`

Purpose: missingness analysis for quality outcomes.

This file helps explain why some repositories or months may be excluded from quality DiD estimation.

#### `panel_event_monthly_matched_v2_balanced_quality_did_input.csv`

Purpose: final quality DiD input.

Important columns usually include:

| Column                         | Meaning                                 |
| ------------------------------ | --------------------------------------- |
| `repo_name` or unit identifier | Repository-level unit.                  |
| `time` or `month`              | Calendar month.                         |
| `event_month`                  | Treatment event month.                  |
| `event_time`                   | Relative event time.                    |
| `treated`                      | Treatment indicator.                    |
| `post`                         | Post-treatment indicator.               |
| quality outcomes               | SonarQube metrics used as DiD outcomes. |

#### `panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv`

Purpose: quality-control file for the final quality DiD input.

### 6.8 Borusyak quality result files

#### `borusyak_quality_v2_static_effects.csv`

Purpose: static post-adoption treatment effects for quality outcomes.

Important columns usually include:

| Column      | Meaning                           |
| ----------- | --------------------------------- |
| `outcome`   | Quality metric analyzed.          |
| `estimate`  | Estimated treatment effect.       |
| `std_error` | Standard error.                   |
| `conf_low`  | Lower confidence bound.           |
| `conf_high` | Upper confidence bound.           |
| `p_value`   | Statistical significance measure. |

#### `borusyak_quality_v2_dynamic_effects.csv`

Purpose: event-time dynamic treatment effects.

Important columns usually include:

| Column       | Meaning                       |
| ------------ | ----------------------------- |
| `outcome`    | Quality metric analyzed.      |
| `event_time` | Relative month from adoption. |
| `estimate`   | Estimated dynamic effect.     |
| `std_error`  | Standard error.               |
| `conf_low`   | Lower confidence bound.       |
| `conf_high`  | Upper confidence bound.       |

#### `borusyak_quality_v2_panel_checks.csv`

Purpose: DiD panel diagnostics.

Important columns may include:

| Column         | Meaning                        |
| -------------- | ------------------------------ |
| `outcome`      | Outcome being checked.         |
| `n_obs`        | Number of usable observations. |
| `n_units`      | Number of repositories.        |
| `n_treated`    | Number of treated units.       |
| `n_control`    | Number of control units.       |
| `pre_periods`  | Number of pre-event periods.   |
| `post_periods` | Number of post-event periods.  |

#### `borusyak_quality_v2_report_summary.csv`

Purpose: final compact summary for reporting quality results.

#### `borusyak_quality_v2_static_effects_with_pct.csv`

Purpose: static quality effects with percentage-change interpretation.

#### `borusyak_quality_v2_dynamic_pretrend_summary.csv`

Purpose: pre-trend diagnostics for dynamic quality outcomes.

## 7. Treatment and Control Group Construction

### 7.1 Treatment group

The treatment group consists of repositories that show evidence of AI-tool adoption. In the current experiment, the workflow emphasizes Cursor or AI-tool adoption evidence.

Treatment selection should satisfy the following conditions:

1. The repository has detectable AI-adoption evidence.
2. The repository has a clearly assigned `event_month`.
3. The repository has enough pre-treatment months.
4. The repository has enough post-treatment months.
5. The repository can be cloned with full Git history.
6. The repository can be analyzed by `analyze_repos_v2.py`.
7. For the current Python-focused experiment, the repository passes the Python repository check.

The current wrapper uses:

```bash
MIN_PRE_MONTHS=3
MIN_POST_MONTHS=3
REQUIRE_CURSOR_EVIDENCE=true
RANK_BY=high_contributor
TOP_N=100
```

These values can be changed for a broader GitHub study.

### 7.2 Control group

The control group consists of repositories that did not show the same AI-tool adoption event during the relevant window but are suitable comparisons for treated repositories.

Control selection should consider:

1. Same or similar primary language.
2. Similar repository activity level before the event.
3. Similar panel coverage.
4. No detected AI adoption during the study window.
5. Successful cloning and Git-history analysis.
6. Availability of matching monthly observations.

The workflow supports both language-matching and non-language-matching control searches. For the current study, the language-matching version is preferable because the treatment set is Python-focused.

### 7.3 Event month assignment for controls

Control repositories do not have their own adoption month. Instead, each control repository inherits the event month of the treated repository to which it is matched. This allows both treatment and control repositories to be aligned in event time.

For each observation:

$event\_time_{it} = month_{it} - event\_month_i$

where $i$ is a repository and $t$ is a month.

## 8. DiD Equations Used in the Report

### 8.1 Conventional static TWFE DiD model

A common two-way fixed effects model is:

$Y_{it} = \alpha_i + \beta_t + \tau D_{it} + \varepsilon_{it}$

where:

* $Y_{it}$ is the outcome for repository $i$ in month $t$.
* $\alpha_i$ is a repository fixed effect.
* $\beta_t$ is a month fixed effect.
* $D_{it}$ is the treatment indicator.
* $\tau$ is the average treatment effect.
* $\varepsilon_{it}$ is the error term.

In this project, $Y_{it}$ can be either a velocity outcome or a quality outcome.

### 8.2 Event-time definition

For treated repositories, define adoption month $E_i$. For both treated repositories and matched controls, define:

$K_{it} = t - E_i$

where $K_{it}$ is event time. Negative values are pre-adoption months, zero is the adoption month, and positive values are post-adoption months.

### 8.3 Dynamic event-study model

A conventional dynamic event-study specification can be written as:

$Y_{it} = \alpha_i + \beta_t + \sum_{k \neq -1} \tau_k \mathbf{1}[K_{it}=k] + \varepsilon_{it}$

where $\tau_k$ is the estimated effect at event time $k$, and one pre-treatment period, often $k=-1$, is omitted as the reference period.

This model is useful for visualization, but under staggered adoption and heterogeneous treatment effects, conventional TWFE event-study estimates can be biased. Therefore, the workflow uses a Borusyak-style imputation DiD estimator for the main analysis.

### 8.4 Borusyak-style untreated outcome model

The imputation approach first estimates untreated potential outcomes using untreated or not-yet-treated observations only:

$Y_{it} = A'*{it}\lambda_i + X'*{it}\delta + \varepsilon_{it}, \quad it \in \Omega_0$

where:

* $\Omega_0$ is the set of untreated observations.
* $A'_{it}\lambda_i$ represents unit-specific components such as repository fixed effects.
* $X'_{it}\delta$ represents time effects or other controls.
* $\varepsilon_{it}$ is the error term.

### 8.5 Imputed untreated potential outcome

For treated observations, the untreated counterfactual is imputed as:

$\widehat{Y}*{it}(0) = A'*{it}\widehat{\lambda}*i + X'*{it}\widehat{\delta}$

### 8.6 Observation-level treatment effect

The observation-level treatment effect estimate is:

$\widehat{\tau}*{it} = Y*{it} - \widehat{Y}_{it}(0)$

### 8.7 Weighted average treatment effect

The target treatment effect is estimated by averaging observation-level effects with researcher-specified weights:

$\widehat{\tau}*w = \sum*{it \in \Omega_1} w_{it}\widehat{\tau}_{it}$

where:

* $\Omega_1$ is the set of treated observations.
* $w_{it}$ are weights defining the target estimand.

### 8.8 Static DiD estimand

For a static post-adoption effect, the target can be written as:

$\widehat{\tau}_{static} = \frac{1}{|\Omega_{post}|}\sum_{it \in \Omega_{post}} \widehat{\tau}_{it}$

where $\Omega_{post}$ is the set of post-adoption treated observations.

### 8.9 Dynamic DiD estimand

For an event-time-specific effect at horizon $h$:

$\widehat{\tau}_{h} = \frac{1}{|\Omega_h|}\sum_{it \in \Omega_h} \widehat{\tau}_{it}$

where:

$\Omega_h = {it: K_{it}=h}$

This produces the dynamic event-study path used to check whether effects appear before adoption, immediately after adoption, or later.

## 9. Velocity Analysis

The velocity analysis uses repository history data generated by `analyze_repos_v2.py`.

### 9.1 Inputs

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/matched_controls_v2_pairs.csv
```

### 9.2 Panel construction

The wrapper:

```bash
./run5c-prepare-panel-event.sh
```

creates:

```text
panel_event_monthly_matched_v2.csv
panel_event_monthly_matched_v2_balanced.csv
```

### 9.3 DiD estimation

The wrapper:

```bash
./run5d-did-borusyak.sh
```

runs:

```text
proc_r/DiffInDiffBorusyak_v2.Rmd
```

and stores outputs in:

```text
activity_did_smoke_borusyak_v2/
```

### 9.4 Interpretation

For velocity outcomes:

* A positive post-adoption effect suggests increased development activity after AI-tool adoption.
* A negative post-adoption effect suggests reduced development activity.
* Dynamic effects should be inspected to see whether changes occur only after adoption.
* Pre-treatment coefficients should be checked to evaluate whether treated and control repositories had similar pre-adoption trends.

## 10. Quality Analysis

The quality analysis uses SonarQube metrics measured at repository-month snapshots.

### 10.1 Inputs

The quality branch begins from the balanced event panel:

```text
panel_event_monthly_matched_v2_balanced.csv
```

The script `run6c-create-input.sh` converts this panel into SonarQube scan inputs:

```text
sonarqube_full_treatment/data/ts_repos_monthly.csv
sonarqube_full_control/data/ts_repos_monthly.csv
```

Each scan input contains:

```text
repo_name, month, latest_commit
```

### 10.2 Full treatment and control scans

Treatment repositories:

```bash
./run6d-sonarqube-full-treatment.sh
```

Control repositories:

```bash
./run6e-sonarqube-full-control.sh
```

Outputs:

```text
sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv
sonarqube_full_control/data/ts_repos_monthly_scanned.csv
```

### 10.3 Quality panel merging

Use:

```bash
./run6g-merge-sonarqube-panel.sh
```

This creates:

```text
panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv
```

### 10.4 Quality coverage checks

Use:

```bash
./run6h-check-sonarqube-panel.sh
```

This creates:

```text
panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv
panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv
```

These files should be inspected before DiD estimation. If too many treatment or control observations are missing SonarQube metrics, quality DiD results may be unreliable.

### 10.5 Quality DiD input

Use:

```bash
./run6i-prepare-quality-did-input.sh
```

This creates:

```text
panel_event_monthly_matched_v2_balanced_quality_did_input.csv
panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv
```

### 10.6 Quality DiD estimation

Use:

```bash
./run6j-did-borusyak-quality.sh
```

This renders:

```text
proc_r/DiffInDiffBorusyak_quality_v2.Rmd
```

and writes results to:

```text
quality_did_borusyak_v2/
```

### 10.7 Quality result summarization

Use:

```bash
./run6k-summarize-borusyak-quality-results.sh
```

This creates:

```text
borusyak_quality_v2_report_summary.csv
borusyak_quality_v2_static_effects_with_pct.csv
borusyak_quality_v2_dynamic_pretrend_summary.csv
```

### 10.8 Interpretation

For quality outcomes:

* A positive effect on `bugs`, `vulnerabilities`, `code_smells`, or `static_analysis_warnings` suggests worse static-analysis quality after adoption.
* A negative effect on those warning-count outcomes suggests improved static-analysis quality.
* A positive effect on `cognitive_complexity` or `technical_debt` suggests increasing complexity or maintenance burden.
* A negative effect on `duplicated_lines_density` suggests reduced duplication.
* Percentage-change summaries should be used carefully when baseline values are near zero.

## 11. Clarifications from the Experiment

### 11.1 Why use a merged shell-script file?

The merged shell-script file is easier to review than many individual shell files because it preserves the complete workflow sequence in one document. However, the merged file must be complete. If any `run*.sh` scripts are missing from the merged file, the final report may miss early data acquisition or setup steps.

### 11.2 Why reuse shell wrappers?

The wrappers encode tested command sequences and concrete file paths. Reusing them reduces the chance that future researchers accidentally skip steps or produce incompatible intermediate files.

### 11.3 Why full Git clone is needed

Do not use shallow clones such as `--depth 1` for this workflow. Adoption timing and monthly history analysis require full Git history.

### 11.4 Why treatment and control analyses must use the same history-analysis script

Treatment and control repositories must be processed by the same `analyze_repos_v2.py` logic. Otherwise, velocity outcomes may not be comparable across groups.

### 11.5 Why balanced panels are important

The balanced panel ensures that treatment and control repositories have comparable event-time coverage. This is especially important when estimating pre-trends and post-adoption effects.

### 11.6 Why quality analysis is separate from velocity analysis

Velocity outcomes come from Git history. Quality outcomes come from SonarQube scans. They require different processing steps and different failure checks. Therefore, the workflow first builds a shared matched panel, then branches into velocity and quality analyses.

### 11.7 Why SonarQube coverage checks are necessary

Some repository-month snapshots may fail to scan because of missing files, unsupported build conditions, scanner errors, or repository checkout problems. The quality DiD analysis should only be interpreted after checking scan coverage and missingness.

### 11.8 How to generalize beyond Python repositories

To reuse the workflow for any GitHub repositories:

1. Remove or parameterize Python-only filtering.
2. Keep full Git history cloning.
3. Ensure SonarQube supports the target languages.
4. Keep treatment and control processing symmetric.
5. Rebuild the matched panel after changing the repository set.
6. Re-run both the velocity and quality branches.

## 12. Minimal Reproducible Command Sequence

For a full rerun using the current wrapper structure:

```bash
# 1. Start and test SonarQube
./run2-sonarqube-server.sh
./run2a-sonarqube-smoke-test.sh
./run2c-sonarqube-small-batch-test.sh

# 2. Select and clone treatment repositories
./run4a-detect-ai-adoption.sh
./run4b-detect-ai-adoption.sh

# 3. Analyze treatment repositories
./run4c-analyze-repo.sh

# 4. Find, clone, and analyze control repositories
./run5a-find-control-group.sh
./run5b-analyze-repo-control-group.sh

# 5. Prepare matched treatment/control panel
./run5c-prepare-panel-event.sh

# 6. Run velocity DiD
./run5d-did-borusyak.sh

# 7. Prepare quality scan input
./run6c-create-input.sh

# 8. Run full SonarQube scans
./run6d-sonarqube-full-treatment.sh
./run6e-sonarqube-full-control.sh

# 9. Check and merge SonarQube outputs
./run6f-check-sonarqube-coverage.sh
./run6g-merge-sonarqube-panel.sh
./run6h-check-sonarqube-panel.sh

# 10. Run quality DiD
./run6i-prepare-quality-did-input.sh
./run6j-did-borusyak-quality.sh
./run6k-summarize-borusyak-quality-results.sh
```

## 13. Recommended Reporting Tables

The final paper or technical report should include the following tables.

### Table 1. Repository sample construction

| Stage                                      | Number of repositories | Notes                                               |
| ------------------------------------------ | ---------------------: | --------------------------------------------------- |
| Candidate AI-adopting repositories         |                        | From `top_100_clone_candidates.csv`.                |
| Successfully cloned treatment repositories |                        | From clone log and `ai_adopt_repo_python.csv`.      |
| Final treatment repositories               |                        | After adoption-date validation.                     |
| Candidate control repositories             |                        | From control selection.                             |
| Successfully cloned control repositories   |                        | From control clone log.                             |
| Matched treatment-control pairs            |                        | From `matched_controls_v2_pairs.csv`.               |
| Final balanced-panel repositories          |                        | From `panel_event_monthly_matched_v2_balanced.csv`. |

### Table 2. Velocity DiD outcomes

| Outcome       | Estimate | Standard error | Confidence interval | Pre-trend check | Interpretation |
| ------------- | -------: | -------------: | ------------------- | --------------- | -------------- |
| commits       |          |                |                     |                 |                |
| changed files |          |                |                     |                 |                |
| additions     |          |                |                     |                 |                |
| deletions     |          |                |                     |                 |                |
| churn         |          |                |                     |                 |                |

### Table 3. Quality DiD outcomes

| Outcome                  | Estimate | Standard error | Percentage change | Pre-trend check | Interpretation |
| ------------------------ | -------: | -------------: | ----------------: | --------------- | -------------- |
| bugs                     |          |                |                   |                 |                |
| vulnerabilities          |          |                |                   |                 |                |
| code smells              |          |                |                   |                 |                |
| static analysis warnings |          |                |                   |                 |                |
| cognitive complexity     |          |                |                   |                 |                |
| duplicated lines density |          |                |                   |                 |                |
| technical debt           |          |                |                   |                 |                |

## 14. Final Checklist for Future Researchers

Before running the DiD analysis:

* Confirm all wrapper scripts are present in the merged script file.
* Confirm `.env` contains `SONAR_HOST`, `SONAR_TOKEN`, and `SONAR_SCANNER_PATH`.
* Confirm treatment and control clone directories exist.
* Confirm repositories are cloned with full Git history.
* Confirm treatment and control time-series files use compatible columns.
* Confirm matched controls are assigned the treated repository’s event month.
* Confirm the balanced panel has sufficient pre/post observations.
* Confirm SonarQube scans completed for enough treatment and control observations.
* Confirm quality missingness is not systematically different between treatment and control.
* Confirm velocity and quality DiD outputs are stored separately.
* Report static effects, dynamic effects, and pre-trend diagnostics for both velocity and quality outcomes.

## 15. Summary

This workflow provides a reusable DiD pipeline for GitHub repository research. The current implementation analyzes AI-tool adoption using Python repositories, but the design can be generalized to broader repository sets. The key reusable structure is:

1. Select AI-adopting treatment repositories.
2. Clone and analyze treatment repositories.
3. Select, clone, and analyze matched controls.
4. Create an event-time matched panel.
5. Run Borusyak-style DiD for velocity outcomes.
6. Run SonarQube scans.
7. Merge quality metrics into the panel.
8. Run Borusyak-style DiD for quality outcomes.
9. Summarize both velocity and quality results with static effects, dynamic effects, and pre-trend checks.

The final report should present both branches together because velocity and quality answer different but complementary questions: whether AI adoption changes how much repositories develop, and whether it changes the quality of the code being developed.
