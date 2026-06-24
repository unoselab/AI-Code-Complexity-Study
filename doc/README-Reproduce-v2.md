# Small-Scale Python Repository DiD Reproduction Report

## 1. Purpose

This document reports the small-scale Python repository reproduction pipeline for the AI-code-complexity study. The goal is to document how we constructed a matched treatment/control repository-month panel, enriched it with SonarQube quality metrics, and ran Borusyak-style Difference-in-Differences (DiD) analyses for quality outcomes.

This report is intentionally scoped to the **small Python repository experiment**. It is not the final full-scale reproduction of the paper. The purpose is to validate that the end-to-end pipeline works on a tractable subset before scaling to a larger repository set.

The current validated pipeline covers:

1. SonarQube setup and smoke testing.
2. AI/Cursor-adopting treatment repository selection.
3. Treatment repository cloning and Git-history analysis.
4. Matched control repository cloning and Git-history analysis.
5. Matched event-panel construction.
6. Velocity/activity Borusyak DiD smoke testing.
7. SonarQube scan-input construction for balanced treatment/control panels.
8. Full SonarQube scans for treatment and control repositories.
9. SonarQube metric merge and quality-panel checks.
10. Quality DiD input preparation.
11. Borusyak quality DiD estimation.
12. Quality DiD result summarization.

## 2. Project Context

Project root used in this reproduction:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

Treatment clone root:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study_repo_dataset
```

Control clone root:

```text
/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset
```

Conda environment:

```text
aicomplexity
```

Local SonarQube server:

```text
http://localhost:9000
```

SonarScanner path used in the experiment:

```text
/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

Important environment variables expected by SonarQube-related wrappers:

```bash
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=<local SonarQube token>
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

## 3. Scope of the Small-Scale Python Experiment

The final small-scale quality DiD panel contains:

| Item | Value |
|---|---:|
| Balanced panel rows | 738 |
| Treated repositories | 13 |
| Control repositories | 38 |
| Static quality outcomes | 3 |
| Dynamic quality outcomes | 3 |
| Source-less commit rows | 1 |
| Raw metric missing rows | 1 |
| Outcomes with pretrend warning | 2 |

The current treatment set consists of 13 Python repositories with Cursor/AI adoption evidence and validated event-month information. The control set consists of 38 matched repositories. The panel is monthly and includes zero-commit months after historical commit lookup and SonarQube scan-input construction.

The final quality DiD output directory is:

```text
tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2/
```

Key final files include:

```text
DiffInDiffBorusyak_quality_v2.html
dynamic_effects_borusyak_v2_quality.pdf
borusyak_quality_v2_static_effects.csv
borusyak_quality_v2_static_effects_with_pct.csv
borusyak_quality_v2_dynamic_effects.csv
borusyak_quality_v2_dynamic_pretrend_summary.csv
borusyak_quality_v2_report_summary.csv
borusyak_quality_v2_panel_checks.csv
borusyak_quality_v2_metadata.csv
```

## 4. High-Level Workflow

The full workflow is divided into setup, treatment construction, control construction, panel construction, velocity DiD, and quality DiD.

```text
SonarQube setup and smoke tests
        |
        v
Treatment candidate selection
        |
        v
Clone treatment repositories
        |
        v
Analyze treatment Git histories
        |
        v
Find and clone matched controls
        |
        v
Analyze control Git histories
        |
        v
Build matched event panel
        |
        +-----------------------------+
        |                             |
        v                             v
Velocity DiD smoke test        SonarQube quality scans
                                      |
                                      v
                              Merge quality metrics
                                      |
                                      v
                              Prepare quality DiD input
                                      |
                                      v
                              Borusyak quality DiD
                                      |
                                      v
                              Summarize report-ready results
```

## 5. Directory Layout

The reproduction uses the following project structure:

```text
ai_code_complexity_study/
├── run*.sh
│   ├── run2*.sh      # SonarQube setup and smoke tests
│   ├── run3*.sh      # detailed SonarQube issue/warning smoke test
│   ├── run4*.sh      # treatment candidate selection, cloning, history analysis
│   ├── run5*.sh      # control construction, matched panel, activity DiD
│   └── run6*.sh      # SonarQube full scans, quality panel, quality DiD
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
│   ├── DiffInDiffBorusyak_quality_v2.Rmd
│   └── diff_in_diff_borusyak_helpers.R
│
├── data_baseline_backup/
│   └── baseline data used for candidate selection
│
├── tmp_adoption_test/data/
│   ├── top_100_clone_candidates.csv
│   ├── top_100_clone_candidates_all_eligible.csv
│   ├── ai_adopt_repo_python.csv
│   ├── control_repos_to_clone_v2.csv
│   ├── control_repos_to_clone_v2.txt
│   ├── matched_controls_v2_pairs.csv
│   ├── matched_controls_v2_treatment_only.csv
│   ├── python_did_test/
│   └── python_control_did_test/
│
├── logs/
│   └── timestamped logs from wrapper scripts
│
├── ../ai_code_complexity_study_repo_dataset/
│   └── cloned treatment repositories
│
└── ../ai_code_complexity_control_repo_dataset/
    └── cloned control repositories
```

## 6. Wrapper Scripts Used

The wrappers were consolidated into a merged text file for review. The scripts are grouped below by pipeline stage.

### 6.1 SonarQube setup and smoke tests

| Script | Purpose |
|---|---|
| `run2-sonarqube-server.sh` | Starts a local SonarQube Docker container. |
| `run2a-sonarqube-smoke-candidates.sh` | Runs candidate-repository smoke test helper. |
| `run2a-sonarqube-smoke-test.sh` | Runs SonarQube infrastructure tests and optionally one-repository scan. |
| `run2b-sonarqube-smoke-test.sh` | Calls the one-repo smoke test for `nextml-code/pytorch-datastream`. |
| `run2c-sonarqube-small-batch-test.sh` | Clones a small batch of repositories and runs aggregate SonarQube metrics. |
| `run2d-sonarqube-small-batch-test.sh` | Convenience wrapper around `run2c`. |
| `run3a-detect-prog-warnings.sh` | Multi-month SonarQube smoke test with detailed issue/warning collection. |

### 6.2 Treatment repository construction

| Script | Purpose |
|---|---|
| `run4a-detect-ai-adoption.sh` | Selects top candidate repositories and optionally clones them. |
| `run4b-detect-ai-adoption.sh` | Runs `run4a` in clone mode. |
| `run4c-analyze-repo.sh` | Analyzes treatment Git histories and checks event/adoption month consistency. |

### 6.3 Control repository construction

| Script | Purpose |
|---|---|
| `run5a-find-control-group.sh` | Clones selected matched controls. Matching commands are present as commented steps. |
| `run5b-analyze-repo-control-group.sh` | Analyzes cloned control Git histories. |

### 6.4 Panel construction and activity DiD

| Script | Purpose |
|---|---|
| `run5c-prepare-panel-event.sh` | Builds matched unbalanced and balanced event panels. |
| `run5d-did-borusyak.sh` | Renders the activity/velocity Borusyak smoke-test Rmd. |

### 6.5 SonarQube quality branch

| Script | Purpose |
|---|---|
| `run6a-sonarq.sh` | Early real SonarQube smoke scan. |
| `run6b-sonarq-collect-warnings.sh` | Early detailed warning collection smoke test. |
| `run6c-create-input.sh` | Creates full treatment/control SonarQube scan inputs from historical lookup panel. |
| `run6d-sonarqube-full-treatment.sh` | Runs full treatment SonarQube scan. |
| `run6e-sonarqube-full-control.sh` | Runs full control SonarQube scan with repo-level incremental save. |
| `run6f-check-sonarqube-coverage.sh` | Checks SonarQube scan coverage. |
| `run6g-merge-sonarqube-panel.sh` | Merges SonarQube metrics into the balanced panel. |
| `run6h-check-sonarqube-panel.sh` | Checks merged SonarQube panel missingness and coverage. |
| `run6i-prepare-quality-did-input.sh` | Creates final quality DiD input and QC file. |
| `run6j-did-borusyak-quality.sh` | Renders quality Borusyak DiD Rmd. |
| `run6k-summarize-borusyak-quality-results.sh` | Creates report-ready quality DiD summaries. |

## 7. Step-by-Step Reproduction Details

### 7.1 Start SonarQube

Script:

```bash
./run2-sonarqube-server.sh
```

Command used by wrapper:

```bash
docker run -d \
  --name sonarqube \
  -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true \
  -p 9000:9000 \
  sonarqube:latest
```

Expected service:

```text
http://localhost:9000
```

The experiment confirmed:

```text
HTTP status: 200
SonarQube status: UP
SonarQube version: 26.6.0.123539
Token validation: valid
```

### 7.2 Run SonarQube infrastructure smoke tests

Script:

```bash
./run2a-sonarqube-smoke-test.sh
```

This wrapper checks `.env`, validates `SONAR_HOST`, `SONAR_TOKEN`, and `SONAR_SCANNER_PATH`, then runs:

```bash
python proc_scripts/test_sonarqube_connection.py
python proc_scripts/test_sonarqube_scan.py
python proc_scripts/test_sonarqube_metrics.py
python proc_scripts/test_sonarqube_tiny_issues.py
```

Important behavior:

```bash
RUN_INFRA_TESTS="1"
```

With the default setting, the wrapper exits after infrastructure tests and does not continue to the one-repository scan. This was intentional for infrastructure validation, but future users should edit the wrapper or add a `--skip-infra-tests` option if they want the one-repository scan path to run in the same invocation.

Tiny-project smoke results:

| Metric | Value |
|---|---:|
| bugs | 0 |
| code_smells | 0 |
| duplicated_lines_density | 0.0 |
| cognitive_complexity | 5 |
| ncloc | 21 |
| vulnerabilities | 0 |
| sqale_index | 0 |

### 7.3 Run small-batch SonarQube scan

Script:

```bash
./run2c-sonarqube-small-batch-test.sh
```

Repositories in the wrapper:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

This wrapper:

1. Clones missing repositories into `../CursorRepos`.
2. Creates temporary scan input in `tmp_sonar_batch/data/ts_repos_monthly.csv`.
3. Runs `proc_scripts/run_sonarqube_v2.py`.
4. Displays resulting metrics.
5. Prints a Docker memory snapshot for the SonarQube container.

### 7.4 Run multi-month detailed warning smoke test

Script:

```bash
./run3a-detect-prog-warnings.sh
```

Default months:

```bash
MONTHS="2026-03,2026-04,2026-05"
```

Outputs:

```text
tmp_sonar_batch/data/sonarqube_warnings.csv
tmp_sonar_batch/data/sonarqube_warning_definitions.csv
```

This validates that detailed SonarQube issue-level data can be collected. For the main DiD outcomes, however, the pipeline uses aggregate snapshot metrics rather than detailed issue records.

## 8. Treatment Repository Selection and Analysis

### 8.1 Select treatment candidates

Script:

```bash
./run4a-detect-ai-adoption.sh
```

Important default configuration:

```bash
DATA_DIR="data_baseline_backup"
OUTPUT_DIR="tmp_adoption_test/data"
OUTPUT_FILE="tmp_adoption_test/data/top_100_clone_candidates.csv"
ALL_ELIGIBLE_FILE="tmp_adoption_test/data/top_100_clone_candidates_all_eligible.csv"
CLONE_ROOT="../ai_code_complexity_study_repo_dataset"
TOP_N="100"
MIN_PRE_MONTHS="3"
MIN_POST_MONTHS="3"
RANK_BY="high_contributor"
REQUIRE_CURSOR_EVIDENCE="true"
```

The candidate-selection command is:

```bash
python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir "${DATA_DIR}" \
  --top-n "${TOP_N}" \
  --min-pre-months "${MIN_PRE_MONTHS}" \
  --min-post-months "${MIN_POST_MONTHS}" \
  --rank-by "${RANK_BY}" \
  --output "${OUTPUT_FILE}" \
  --require-cursor-evidence
```

Primary outputs:

```text
tmp_adoption_test/data/top_100_clone_candidates.csv
tmp_adoption_test/data/top_100_clone_candidates_all_eligible.csv
```

### 8.2 Clone treatment repositories

Script:

```bash
./run4b-detect-ai-adoption.sh
```

This wrapper runs `run4a` in clone mode:

```bash
GIT_TERMINAL_PROMPT=0 \
INSPECT_ONLY=false INSPECT_CLONE=true MAX_CLONES=0 \
./run4a-detect-ai-adoption.sh
```

The cloning command eventually calls:

```bash
python proc_scripts/clone_repos_v2.py \
  --repos-file "${OUTPUT_FILE}" \
  --repo-column repo_name \
  --clone-root "${CLONE_ROOT}" \
  --logs-dir "${LOG_DIR}" \
  --log-prefix run4a_clone_log \
  --timestamp "${RUN_TS}" \
  --max-repos "${MAX_CLONES}"
```

Important note:

```text
Do not use shallow clone mode. Full Git history is required for adoption-date detection and monthly history reconstruction.
```

After cloning, the wrapper runs:

```bash
python proc_scripts/check_python_repo_clone.py \
  --candidates-file "${OUTPUT_FILE}" \
  --clone-log "${CLONE_LOG}" \
  --output "${OUTPUT_DIR}/ai_adopt_repo_python.csv" \
  --language Python
```

Final Python treatment metadata file:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

### 8.3 Final treatment repositories

The small-scale Python treatment set contains 13 repositories:

| # | Repository | Event month |
|---:|---|---|
| 1 | `airweave-ai/airweave` | 2025-03 |
| 2 | `sirkirby/unifi-network-rules` | 2025-03 |
| 3 | `VRSEN/agency-swarm` | 2024-10 |
| 4 | `TextGeneratorio/text-generator.io` | 2025-03 |
| 5 | `wdm0006/pygeohash` | 2025-03 |
| 6 | `wdm0006/elote` | 2025-02 |
| 7 | `KroMiose/nekro-agent` | 2025-01 |
| 8 | `ttmouse/Wispr-Flow-CN` | 2024-12 |
| 9 | `ToolUse/tool-use-ai` | 2024-12 |
| 10 | `kenshiro-o/nagato-ai` | 2025-02 |
| 11 | `Kiln-AI/Kiln` | 2025-01 |
| 12 | `OpenMOSS/Language-Model-SAEs` | 2024-12 |
| 13 | `wdm0006/git-pandas` | 2025-03 |

Two Python candidates were excluded after validation:

```text
DutchCryptoDad/bamboo-ta
Metta-AI/metta
```

### 8.4 Analyze treatment Git histories

Script:

```bash
./run4c-analyze-repo.sh
```

Important paths:

```bash
REPOS_FILE="tmp_adoption_test/data/ai_adopt_repo_python.csv"
CLONE_DIR="../ai_code_complexity_study_repo_dataset"
OUTPUT_DIR="tmp_adoption_test/data/python_did_test"
AGGREGATION="month"
NUM_PROCESSES="1"
```

History-analysis command:

```bash
python proc_scripts/analyze_repos_v2.py \
  --repos-file "${REPOS_FILE}" \
  --clone-dir "${CLONE_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --aggregation "${AGGREGATION}" \
  --num-processes "${NUM_PROCESSES}"
```

Event/adoption month check:

```bash
python proc_scripts/check_time_of_event_and_adoption.py \
  --candidate-file "${REPOS_FILE}" \
  --adoption-file "${ADOPTION_FILE}" \
  --output-match-file "${ADOPTION_MATCH_FILE}"
```

Key outputs:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_did_test/ai_adoption_dates.csv
tmp_adoption_test/data/python_did_test/adoption_month_check.csv
tmp_adoption_test/data/python_did_test/cursor_commits.csv
```

Treatment time-series result:

| Item | Value |
|---|---:|
| Rows | 254 |
| Treatment repositories | 13 |
| Event/adoption mismatches | 0 |
| Missing detected adoption dates | 0 |

## 9. Control Repository Selection and Analysis

### 9.1 Find and clone controls

Script:

```bash
./run5a-find-control-group.sh
```

Important note: the merged wrapper contains two commented matching commands and then the clone step. The matching artifacts were produced before cloning. Future reruns should explicitly run the desired matching step before cloning controls.

Commented matching options in the wrapper:

```bash
python proc_scripts/find_control_groups_v2.py \
  --no-language-matching \
  --max-control-repos 5000 \
  --random-state 42
```

and:

```bash
python proc_scripts/find_control_groups_v2.py \
  --language-matching \
  --max-control-repos 10000 \
  --random-state 42
```

The small Python reproduction used language-aware matching artifacts:

```text
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/control_repos_to_clone_v2.csv
tmp_adoption_test/data/control_repos_to_clone_v2.txt
```

Clone command in the wrapper:

```bash
python proc_scripts/clone_repos_v2.py \
  --repos-file "tmp_adoption_test/data/control_repos_to_clone_v2.txt" \
  --repo-column repo_name \
  --clone-root "/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset" \
  --logs-dir "logs" \
  --log-prefix run5b_control_clone_log \
  --timestamp "${RUN_TS}" \
  --max-repos "0" \
  --existing-action skip
```

Control matching result:

| Item | Value |
|---|---:|
| Treatment repositories | 13 |
| Matched pairs | 39 |
| Controls per treatment | 3 |
| Unique control repositories | 38 |
| Repeated control repositories | 1 |
| Treatment-control leakage | 0 |

Repeated control:

```text
yuvraj108c/ComfyUI_InvSR
```

### 9.2 Analyze control Git histories

Script:

```bash
./run5b-analyze-repo-control-group.sh
```

Command:

```bash
python proc_scripts/analyze_repos_v2.py \
  --repos-file tmp_adoption_test/data/control_repos_to_clone_v2.csv \
  --clone-dir /home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset \
  --output-dir tmp_adoption_test/data/python_control_did_test \
  --aggregation month \
  --num-processes 1
```

Control time-series result:

| Item | Value |
|---|---:|
| Control repositories analyzed | 38 |
| Rows in `ts_repos_monthly.csv` | 395 |
| Rows in `ts_contributors_monthly.csv` | 1361 |
| Control repositories with Cursor adoption evidence | 0 |

Key output:

```text
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
```

## 10. Matched Panel Construction

Script:

```bash
./run5c-prepare-panel-event.sh
```

Command:

```bash
python proc_scripts/prepare_panel_event_v2.py \
  --treatment-meta tmp_adoption_test/data/matched_controls_v2_treatment_only.csv \
  --pairs tmp_adoption_test/data/matched_controls_v2_pairs.csv \
  --treatment-ts tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv \
  --control-ts tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv \
  --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv \
  --balanced-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

Outputs:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

Panel construction behavior:

1. Uses treatment event month from treatment metadata.
2. Treats controls as never-treated.
3. Keeps treatment `post_event` absorbing after event month.
4. Does not reset treatment status after possible Cursor abandonment.
5. Creates both active-month unbalanced panel and analysis-window completed balanced panel.
6. Completes zero-activity months after each repository's first observed local Git commit month.

Matched panel results:

| Panel | Rows | Treatment repos | Control repos | Notes |
|---|---:|---:|---:|---|
| Unbalanced | 324 | 13 | 35 | Active observed months only |
| Balanced | 738 | 13 | 38 | Main analysis-window completed panel |

Balanced panel diagnostics:

| Check | Value |
|---|---:|
| Control `post_event` sum | 0 |
| Control dynamic treatment sum | 0 |
| Treated post rows | 98 |
| Zero-activity treated post rows | 23 |
| Post-event mismatch rows | 0 |

Controls restored by balanced zero-activity completion:

```text
ayushtewari/DFM
kienmarkdo/Cybersecurity-Mini-Projects
hjhxy/2023-Chinese-Collegiate-Computing-Competition
```

Data-quality caveat:

```text
wdm0006/elote and wdm0006/git-pandas have empty or near-empty pre-adoption windows in the small sample.
```

## 11. Activity / Velocity Borusyak DiD Smoke Test

Script:

```bash
./run5d-did-borusyak.sh
```

Command:

```bash
export PROJECT_ROOT="$(pwd)"

Rscript -e "rmarkdown::render(
  'proc_r/DiffInDiffBorusyak_v2.Rmd',
  output_dir = 'tmp_adoption_test/data/python_did_test/activity_did_smoke_borusyak_v2',
  envir = new.env()
)"
```

Purpose:

```text
Validate the Borusyak imputation DiD pipeline on activity/velocity outcomes before running quality outcomes.
```

Activity Rmd:

```text
proc_r/DiffInDiffBorusyak_v2.Rmd
```

Output directory:

```text
tmp_adoption_test/data/python_did_test/activity_did_smoke_borusyak_v2/
```

The activity smoke test uses the balanced activity panel:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

Activity outcomes in the smoke test:

```text
commits
lines_added
```

First-stage formula:

```r
~ contributors | repo_name + time
```

This branch is retained as a velocity/activity validation artifact. It should not be overwritten by the quality DiD workflow.

## 12. SonarQube Quality Branch

### 12.1 Prerequisite: historical commit lookup

The balanced panel does not inherently contain `latest_commit` for every zero-commit month. Before full SonarQube scanning, the pipeline used historical lookup to assign each repository-month the latest commit available at that month end:

```text
git rev-list -n 1 --before "<month-end> 23:59:59" HEAD
```

The resulting scan-input source file was:

```text
tmp_adoption_test/data/python_did_test/sonarqube_input_check/sonarqube_scan_input_balanced_history_lookup.csv
```

Historical lookup result:

| Item | Value |
|---|---:|
| Rows | 738 |
| Repositories | 51 |
| Rows with checkout commit | 738 |
| Missing checkout commit | 0 |

This file is the input to `run6c-create-input.sh`.

### 12.2 Create full treatment/control scan input

Script:

```bash
./run6c-create-input.sh
```

Input:

```text
tmp_adoption_test/data/python_did_test/sonarqube_input_check/sonarqube_scan_input_balanced_history_lookup.csv
```

Outputs:

```text
tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv
```

The wrapper splits rows by `dataset_source`, renames `time` to `month`, and keeps:

```text
repo_name, month, latest_commit
```

Generated scan input summary:

| Dataset | Rows | Repositories | Month range | Missing latest commit |
|---|---:|---:|---|---:|
| Treatment | 208 | 13 | 2024-01 to 2025-08 | 0 |
| Control | 530 | 38 | 2024-01 to 2025-08 | 0 |

Duplicated commit checks:

| Dataset | Rows | Unique repo-commit pairs | Repeated same-commit rows | Explanation |
|---|---:|---:|---:|---|
| Treatment | 208 | 142 | 66 | zero-commit months reuse previous commit |
| Control | 530 | 194 | 336 | zero-commit months reuse previous commit |

Repeated repo-commit pairs are expected because months with no commits should scan the same most recent commit snapshot.

### 12.3 Full treatment SonarQube scan

Script:

```bash
./run6d-sonarqube-full-treatment.sh
```

Command:

```bash
python proc_scripts/run_sonarqube_v2.py \
  --aggregation month \
  --input-file tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv \
  --output-file tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv \
  --clone-dir ../ai_code_complexity_study_repo_dataset \
  --num-processes 1
```

Output:

```text
tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv
```

Treatment scan result:

| Item | Value |
|---|---:|
| Rows | 208 |
| Repositories | 13 |
| Runtime | about 53 minutes |
| Rows with all issue metrics | 208 |
| Rows with `ncloc` | 207 |
| Rows with density/complexity metrics | 207 |

One treatment row had no analyzable source code:

| Repository | Month | Commit | Explanation |
|---|---|---|---|
| `kenshiro-o/nagato-ai` | 2024-03 | `cb13400a6f9b7dbdc9b83a080a09145a536a6111` | initial commit containing only `.gitignore`, `LICENSE`, and `README.md` |

This row was later preserved as a source-less commit and filled as zero in analysis-ready metrics.

### 12.4 Full control SonarQube scan

Script:

```bash
./run6e-sonarqube-full-control.sh
```

Command:

```bash
python proc_scripts/run_sonarqube_v2.py \
  --aggregation month \
  --input-file tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv \
  --output-file tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv \
  --clone-dir ../ai_code_complexity_control_repo_dataset \
  --num-processes 1 \
  --incremental-save
```

Output:

```text
tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv
```

Control scan result:

| Item | Value |
|---|---:|
| Rows | 530 |
| Repositories | 38 |
| Runtime | about 2 hours 12 minutes |
| Rows with all metrics | 530 |
| Missing rows | 0 |

The control scan used repo-level incremental saving so partial progress would be preserved if interrupted.

### 12.5 SonarQube coverage check

Script:

```bash
./run6f-check-sonarqube-coverage.sh
```

Command:

```bash
python proc_scripts/check-sonarqube-coverage.py 2>&1 | tee "${LOG_FILE}"
```

Purpose:

```text
Check whether full treatment/control SonarQube scan outputs cover the expected repository-month inputs.
```

### 12.6 Merge SonarQube metrics into balanced panel

Script:

```bash
./run6g-merge-sonarqube-panel.sh
```

Command:

```bash
python proc_scripts/merge-sonarqube-panel.py \
  --panel tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv \
  --treatment-metrics tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv \
  --control-metrics tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv \
  --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
  --qc-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv
```

Outputs:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv
```

Merge result:

| Check | Value |
|---|---:|
| Merged rows | 738 |
| Treatment rows | 208 |
| Control rows | 530 |
| Treatment repositories | 13 |
| Control repositories | 38 |
| Rows with any raw metric missing | 1 |
| Source-less commits | 1 |
| Analysis-ready main quality metrics nonmissing | 738 |

Analysis-ready metric construction:

```text
static_analysis_warnings = bugs + vulnerabilities + code_smells
```

Raw metric columns were preserved with `_raw` suffix where appropriate. Source-less commits were preserved and filled as zero for analysis-ready `ncloc`, density, complexity, and issue-count metrics.

### 12.7 Check merged SonarQube panel

Script:

```bash
./run6h-check-sonarqube-panel.sh
```

Command:

```bash
python proc_scripts/check-sonarqube-panel.py \
  --input tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
  --summary-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv \
  --missing-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv
```

Outputs:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv
```

Merged panel sanity result:

| Check | Value |
|---|---:|
| Rows | 738 |
| Repositories | 51 |
| Treatment rows | 208 |
| Control rows | 530 |
| Duplicate repo-month-source keys | 0 |
| Main quality outcomes nonmissing | 738 |
| Per-KLOC ratios nonmissing | 737 |

The only missing per-KLOC ratio is due to the one source-less commit with `ncloc = 0`. Main quality outcomes remain complete.

### 12.8 Prepare quality DiD input

Script:

```bash
./run6i-prepare-quality-did-input.sh
```

Command:

```bash
python proc_scripts/prepare-quality-did-input.py \
  --input tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
  --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input.csv \
  --qc-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv
```

Outputs:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input.csv
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv
```

Created log-transformed variables:

```text
log_static_analysis_warnings = log1p(static_analysis_warnings)
log_cognitive_complexity = log1p(cognitive_complexity)
log_technical_debt = log1p(technical_debt)
log_ncloc = log1p(ncloc)
```

Quality DiD input QC:

| Check | Value |
|---|---:|
| Rows | 738 |
| Repositories | 51 |
| Treatment rows | 208 |
| Control rows | 530 |
| Treatment repositories | 13 |
| Control repositories | 38 |
| Duplicate repo-time-source keys | 0 |
| Control post-event sum | 0 |
| Source-less commit rows | 1 |
| Main outcomes finite/nonmissing | 738 |

## 13. Borusyak Quality DiD

### 13.1 Render quality DiD Rmd

Script:

```bash
./run6j-did-borusyak-quality.sh
```

Command:

```bash
export PROJECT_ROOT="$(pwd)"

Rscript -e "rmarkdown::render(
  'proc_r/DiffInDiffBorusyak_quality_v2.Rmd',
  output_dir = 'tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2',
  envir = new.env()
)"
```

Input panel:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input.csv
```

Output HTML:

```text
tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2/DiffInDiffBorusyak_quality_v2.html
```

Output plot:

```text
tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2/dynamic_effects_borusyak_v2_quality.pdf
```

### 13.2 Quality outcomes

The first quality DiD run used three main paper-aligned quality outcomes:

```text
log_static_analysis_warnings
log_duplicated_lines_density
log_cognitive_complexity
```

`log_duplicated_lines_density` is created inside the Rmd as:

```r
log_duplicated_lines_density = log(duplicated_lines_density + 1)
```

Secondary outcome intentionally excluded from the first main run:

```text
log_technical_debt
```

This can be added later as a secondary or robustness outcome.

### 13.3 First-stage formula

The quality Rmd uses:

```r
first_stage_formula <- ~ contributors + log_ncloc | repo_name + time
```

Interpretation:

| Component | Meaning |
|---|---|
| `contributors` | log-transformed monthly contributor activity from Git history |
| `log_ncloc` | log-transformed codebase size from SonarQube |
| `repo_name` fixed effect | controls for time-invariant repository differences |
| `time` fixed effect | controls for month-level shocks |

Full-paper covariates such as `age`, `stars`, and `issues` are not yet included in the small Python panel.

### 13.4 Estimator

The quality Rmd uses `didimputation::did_imputation` through the shared helper file:

```text
proc_r/diff_in_diff_borusyak_helpers.R
```

The helper supports:

1. Static Borusyak imputation DiD.
2. Dynamic event-study Borusyak imputation DiD.
3. Extraction of static effect table.
4. Extraction of dynamic event-study table.

Dynamic horizon used:

```r
horizon = -6:6
pretrends = -6:-2
```

## 14. Quality DiD Result Summary

### 14.1 Result summarization wrapper

Script:

```bash
./run6k-summarize-borusyak-quality-results.sh
```

Command:

```bash
python proc_scripts/summarize-borusyak-quality-results.py \
  --static-effects "${OUT_DIR}/borusyak_quality_v2_static_effects.csv" \
  --dynamic-effects "${OUT_DIR}/borusyak_quality_v2_dynamic_effects.csv" \
  --panel-checks "${OUT_DIR}/borusyak_quality_v2_panel_checks.csv" \
  --output-summary "${OUT_DIR}/borusyak_quality_v2_report_summary.csv" \
  --output-static "${OUT_DIR}/borusyak_quality_v2_static_effects_with_pct.csv" \
  --output-dynamic-summary "${OUT_DIR}/borusyak_quality_v2_dynamic_pretrend_summary.csv"
```

Final report-ready outputs:

```text
borusyak_quality_v2_report_summary.csv
borusyak_quality_v2_static_effects_with_pct.csv
borusyak_quality_v2_dynamic_pretrend_summary.csv
```

### 14.2 Static quality effects

| Outcome | Estimate | 95% CI | Approx. percent change | Percent CI | Significant? |
|---|---:|---:|---:|---:|---|
| Static Analysis Warnings | 0.0864 | [-0.3132, 0.4860] | +9.03% | [-26.89%, +62.58%] | No |
| Duplicated Lines Density | -0.0541 | [-0.4393, 0.3311] | -5.27% | [-35.55%, +39.25%] | No |
| Code Complexity | -0.0855 | [-0.4640, 0.2929] | -8.20% | [-37.12%, +34.03%] | No |

Interpretation:

```text
The small-scale Python panel does not show statistically significant average post-adoption quality effects for the three main quality outcomes. These estimates should be treated as pipeline-validation output, not final causal evidence.
```

### 14.3 Dynamic effects and pretrend summary

| Outcome | Pre-period rows | Pre significant count | Post-period rows | Post significant count | Post mean estimate | Approx. post mean percent change | Pretrend warning? |
|---|---:|---:|---:|---:|---:|---:|---:|
| Code Complexity | 5 | 0 | 7 | 0 | -0.2550 | -22.51% | No |
| Duplicated Lines Density | 5 | 1 | 7 | 1 | -0.1632 | -15.06% | Yes |
| Static Analysis Warnings | 5 | 4 | 7 | 0 | 0.0318 | +3.23% | Yes |

Pretrend conclusion:

```text
Two of the three quality outcomes show at least one significant pre-adoption placebo effect in the dynamic event-study output. This raises a pretrend concern for this small sample, especially for Static Analysis Warnings.
```

Therefore, the correct interpretation is:

```text
The quality DiD pipeline runs successfully end-to-end, but the small-scale Python sample should not be interpreted as final causal evidence because two outcomes show pretrend warnings and the sample is small.
```

## 15. Output Directory After `run6k`

After `run6j` and `run6k`, the quality DiD output directory contained:

```text
total 780K
borusyak_quality_v2_dynamic_effects.csv
borusyak_quality_v2_dynamic_pretrend_summary.csv
borusyak_quality_v2_input_summary.csv
borusyak_quality_v2_metadata.csv
borusyak_quality_v2_panel_checks.csv
borusyak_quality_v2_report_summary.csv
borusyak_quality_v2_static_effects.csv
borusyak_quality_v2_static_effects_with_pct.csv
DiffInDiffBorusyak_quality_v2.html
dynamic_effects_borusyak_v2_quality.pdf
```

The HTML file is the primary analysis artifact. The PDF event-study plot is useful for report figures.

Recommended artifact roles:

| Artifact | Role |
|---|---|
| `DiffInDiffBorusyak_quality_v2.html` | Primary reproducibility artifact for model output and code chunks |
| `dynamic_effects_borusyak_v2_quality.pdf` | Figure artifact for reports and slides |
| `borusyak_quality_v2_static_effects_with_pct.csv` | Main static summary table |
| `borusyak_quality_v2_dynamic_pretrend_summary.csv` | Main pretrend/dynamic diagnostic table |

## 16. Minimal Command Sequence for This Small-Scale Reproduction

The following sequence reproduces the current small-scale Python DiD workflow assuming the required baseline data, token configuration, and clone roots are available.

```bash
# 1. Start and test SonarQube
./run2-sonarqube-server.sh
./run2a-sonarqube-smoke-test.sh
./run2c-sonarqube-small-batch-test.sh
./run3a-detect-prog-warnings.sh

# 2. Select and clone treatment repositories
./run4a-detect-ai-adoption.sh
./run4b-detect-ai-adoption.sh

# 3. Analyze treatment repositories
./run4c-analyze-repo.sh

# 4. Match, clone, and analyze control repositories
# If needed, first run the matching command inside or before run5a:
# python proc_scripts/find_control_groups_v2.py \
#   --language-matching \
#   --max-control-repos 10000 \
#   --random-state 42
./run5a-find-control-group.sh
./run5b-analyze-repo-control-group.sh

# 5. Prepare matched panel
./run5c-prepare-panel-event.sh

# 6. Run activity/velocity Borusyak smoke test
./run5d-did-borusyak.sh

# 7. Create historical lookup scan input
# This prerequisite must produce:
# tmp_adoption_test/data/python_did_test/sonarqube_input_check/sonarqube_scan_input_balanced_history_lookup.csv

# 8. Prepare SonarQube full scan inputs
./run6c-create-input.sh

# 9. Run full SonarQube scans
./run6d-sonarqube-full-treatment.sh
./run6e-sonarqube-full-control.sh

# 10. Check, merge, and validate SonarQube panel
./run6f-check-sonarqube-coverage.sh
./run6g-merge-sonarqube-panel.sh
./run6h-check-sonarqube-panel.sh

# 11. Prepare quality DiD input
./run6i-prepare-quality-did-input.sh

# 12. Run and summarize quality Borusyak DiD
./run6j-did-borusyak-quality.sh
./run6k-summarize-borusyak-quality-results.sh
```

## 17. Important Caveats

### 17.1 Small sample

The current sample has only 13 treated repositories and 38 controls. This is appropriate for pipeline validation but not enough to claim final empirical results.

### 17.2 Python-only scope

This experiment is Python-focused. Results may not generalize to repositories in other languages.

### 17.3 Missing full-paper covariates

The current quality first-stage uses:

```r
~ contributors + log_ncloc | repo_name + time
```

The full-paper-style covariates such as `age`, `stars`, `issues`, `forks`, `pulls`, `releases`, and `comments` are not yet included.

### 17.4 Pretrend warnings

Two of three quality outcomes show pretrend warnings:

```text
Static Analysis Warnings
Duplicated Lines Density
```

This is the strongest reason not to interpret the current quality estimates as final causal evidence.

### 17.5 Source-less commit handling

One treatment row corresponds to an initial commit without analyzable source files. The pipeline preserves the row and fills analysis-ready metrics as zero, while raw missingness is retained for auditability.

### 17.6 SonarQube metric interpretation

SonarQube metrics are static-analysis indicators. They do not capture all dimensions of software quality. They are useful as systematic, reproducible quality proxies, but they should be interpreted alongside other evidence.

### 17.7 Detailed issue records versus aggregate metrics

The detailed warning collection pipeline exists and was smoke-tested. However, the main quality DiD uses aggregate snapshot metrics because they are better aligned with repository-month panel estimation.

## 18. How to Add Full-Paper Covariates Later

To make the small-scale pipeline closer to the full paper, add repository-month covariates such as:

| Covariate | Suggested source | Notes |
|---|---|---|
| `age_days` or `age_months` | GitHub API, GHArchive, or first observed event date | Time-varying age can be calculated per month. |
| `stars` | GHArchive `WatchEvent` or GitHub API snapshots | Use cumulative or pre-period counts consistently. |
| `forks` | GHArchive `ForkEvent` or GitHub API snapshots | Prefer pre-period matching variables and monthly controls if needed. |
| `issues` | GHArchive `IssuesEvent` | Monthly count or cumulative count. |
| `issue_comments` | GHArchive `IssueCommentEvent` | Useful for engagement/activity controls. |
| `pull_requests` | GHArchive `PullRequestEvent` | Useful for development process activity. |
| `releases` | GHArchive `ReleaseEvent` | Useful for project maturity. |
| `total_events` | GHArchive events | Broad project activity proxy. |

Recommended approach:

1. Use GHArchive + BigQuery to construct a repository-month covariate table.
2. Normalize repository names to lowercase for joins.
3. Aggregate event counts by `repo_name` and `month`.
4. Construct cumulative or lagged pre-period features for matching.
5. Merge monthly covariates into:

```text
panel_event_monthly_matched_v2_balanced_quality_did_input.csv
```

6. Update the quality first-stage formula, for example:

```r
first_stage_formula <- ~ contributors + log_ncloc + age_months + log_stars + log_issues | repo_name + time
```

7. Re-run:

```bash
./run6j-did-borusyak-quality.sh
./run6k-summarize-borusyak-quality-results.sh
```

## 19. Recommended Tables for a Paper or Technical Report

### Table A. Sample construction

| Stage | Count | Source |
|---|---:|---|
| Candidate AI/Cursor repositories | 100 top candidates | `top_100_clone_candidates.csv` |
| Final Python treatment repositories | 13 | `ai_adopt_repo_python.csv` |
| Matched treatment-control pairs | 39 | `matched_controls_v2_pairs.csv` |
| Unique controls | 38 | `control_repos_to_clone_v2.csv` |
| Balanced panel rows | 738 | `panel_event_monthly_matched_v2_balanced.csv` |
| Quality DiD input rows | 738 | `panel_event_monthly_matched_v2_balanced_quality_did_input.csv` |

### Table B. SonarQube scan coverage

| Dataset | Rows | Repositories | Missing main analysis metrics | Notes |
|---|---:|---:|---:|---|
| Treatment | 208 | 13 | 0 analysis-ready | one source-less raw row |
| Control | 530 | 38 | 0 | complete scan coverage |
| Merged panel | 738 | 51 | 0 main outcomes | per-KLOC ratio missing for one source-less row |

### Table C. Static quality DiD results

| Outcome | Estimate | Percent change | Significant? | Interpretation |
|---|---:|---:|---|---|
| Static Analysis Warnings | 0.0864 | +9.03% | No | Not significant in small sample |
| Duplicated Lines Density | -0.0541 | -5.27% | No | Not significant in small sample |
| Code Complexity | -0.0855 | -8.20% | No | Not significant in small sample |

### Table D. Dynamic/pretrend diagnostics

| Outcome | Pre significant count | Post significant count | Pretrend warning? |
|---|---:|---:|---|
| Code Complexity | 0 | 0 | No |
| Duplicated Lines Density | 1 | 1 | Yes |
| Static Analysis Warnings | 4 | 0 | Yes |

## 20. Final Interpretation

The current small-scale Python repository reproduction successfully validates the workflow from repository selection through SonarQube quality scanning and Borusyak DiD estimation.

The most important conclusions are:

1. The end-to-end pipeline runs successfully.
2. Treatment and control Git-history analysis are symmetric.
3. The balanced event panel contains 738 repository-month rows.
4. Full SonarQube scans completed for treatment and control panels.
5. Main analysis-ready quality outcomes are complete for all 738 rows.
6. The quality Borusyak Rmd renders successfully.
7. Static quality estimates are not statistically significant in this small sample.
8. Two quality outcomes show pretrend warnings.
9. Therefore, the current results should be interpreted as pipeline validation, not final causal evidence.

Recommended next step:

```text
Scale the pipeline to a larger sample, add full-paper covariates from GHArchive/BigQuery, and re-run both velocity and quality DiD analyses with stronger pretrend diagnostics.
```
