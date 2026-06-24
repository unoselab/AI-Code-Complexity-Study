# Progress Report: Matched Control Construction and Event-Panel Preparation

## 1. Current Research Objective

The current phase of the project is to reproduce and extend the paper-style matched difference-in-differences setup for studying whether Cursor or Cursor-like AI coding tool adoption affects repository activity, quality, and complexity.

The immediate objective was to move from a small validated treatment set to a matched control design. Specifically, we aimed to:

1. Build a matched never-treated control group for the 13 Python treatment repositories.
2. Clone only the final matched control repositories, not all control candidates.
3. Generate monthly Git-history activity panels for both treatment and control repositories.
4. Construct a paper-faithful event panel that keeps treatment repositories as adopters and control repositories as never-treated units.

## 2. Environment

The work was performed in the project directory:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

The active conda environment was:

```text
aicomplexity
```

The treatment repositories were stored under:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study_repo_dataset
```

The matched control repositories were cloned under:

```text
/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset
```

## 3. Treatment Group Status

We used the existing Python treatment set:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

This file contains 13 Python repositories that adopted Cursor or Cursor-like AI coding tools. These repositories had already passed the earlier adoption validation step.

The treatment-side Git-history analysis had already generated:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_did_test/ai_adoption_dates.csv
```

The treatment event months were treated as verified because the metadata event months matched the local Git-history adoption detector output. The validation result showed:

```text
Treatment repos: 13
Matched event/adoption month: 13
Mismatched event/adoption month: 0
Missing adoption month: 0
```

Thus, for the next panel-preparation step, we decided not to re-detect adoption using `cursor == True` in the monthly time series. Instead, we use the verified `event_month` from the treatment metadata.

## 4. Existing Control Candidate Files

We confirmed that the project already had GHArchive-derived control candidate CSV files for the relevant adoption months:

```text
data/control_repo_candidates_202408.csv
data/control_repo_candidates_202409.csv
data/control_repo_candidates_202410.csv
data/control_repo_candidates_202411.csv
data/control_repo_candidates_202412.csv
data/control_repo_candidates_202501.csv
data/control_repo_candidates_202502.csv
data/control_repo_candidates_202503.csv
```

Because these files already existed locally, we chose not to rerun expensive BigQuery/GHArchive control discovery queries.

The design decision was:

```text
Use existing control candidate CSV files.
Run PSM locally.
Clone only the final matched controls.
```

## 5. Propensity Score Matching

We used the local matching wrapper:

```text
proc_scripts/find_control_groups_v2.py
```

This wrapper used:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
data/repo_events.csv
data/control_repo_candidates_YYYYMM.csv
```

It generated the matched control outputs:

```text
tmp_adoption_test/data/matched_controls_v2_summary.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/control_repos_to_clone_v2.txt
tmp_adoption_test/data/control_repos_to_clone_v2.csv
```

The final matched pair file had:

```text
matched_controls_v2_pairs.csv rows: 39
```

This corresponds to:

```text
13 treatment repositories × 3 matched controls = 39 matched pairs
```

The final unique control count was:

```text
38 unique matched control repositories
```

One control repository was matched to two treatment repositories. This is acceptable for the paper-faithful never-treated panel because controls are included as unique never-treated repositories rather than duplicated by matched pair.

Treatment-control leakage was checked earlier and found to be absent.

## 6. Control Repository Cloning

The clone script was patched so that it can accept either:

```text
CSV file with repo_name column
TXT file with one repository per line
```

The relevant script is:

```text
proc_scripts/clone_repos_v2.py
```

The final clone list was:

```text
tmp_adoption_test/data/control_repos_to_clone_v2.txt
```

The matched controls were cloned into:

```text
/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset
```

Clone verification showed:

```text
.git count = 38
clone log = logs/run5b_control_clone_log_20260620-0212.csv
status = cloned 38
```

Therefore, the matched control clone stage was completed successfully.

## 7. Control Git-History Analysis

We then ran Git-history analysis on the 38 matched control repositories using:

```text
proc_scripts/analyze_repos_v2.py
```

The control analysis output directory was:

```text
tmp_adoption_test/data/python_control_did_test
```

The resulting control-side files were:

```text
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_control_did_test/ai_adoption_dates.csv
```

The control analysis result was:

```text
ts_repos_monthly.csv rows: 395
unique repos: 38

ts_contributors_monthly.csv rows: 1361
unique repos: 38

ai_adoption_dates.csv rows: 0
```

No Cursor-related commits were found in the controls:

```text
Repos with Cursor adoption evidence: 0
```

This confirms that the matched controls are clean never-treated controls for the current small-scale Python analysis.

## 8. Review of Existing Panel Preparation Code

Before writing a new event-panel script, we reviewed the existing code:

```text
scripts/prepare_panel_event.py
```

This file was the closest existing script because it already contained logic for:

```text
relative event time
post_event
lead/lag indicators
never-treated control handling
```

However, it was not suitable to use unchanged.

The original script detects adoption by finding the first month where:

```text
cursor == True
```

It also resets `post_event` back to 0 when `cursor == False`, treating Cursor usage as a reversible or switching treatment.

That behavior is useful for dynamic usage analysis but does not match the paper-faithful main DiD design. The paper-style design treats adoption as an absorbing treatment: once a repository adopts Cursor, post-adoption observations remain post-adoption observations.

Therefore, we decided:

```text
Do not modify scripts/prepare_panel_event.py.
Create a new wrapper under proc_scripts.
Borrow only the event-time, lead/lag, and never-treated-control ideas.
Use verified event_month metadata.
Do not re-detect event_month from cursor.
Do not apply abandonment masking.
```

## 9. New Event Panel Script

We created:

```text
proc_scripts/prepare_panel_event_v2.py
```

The script builds a paper-faithful matched DiD event panel using:

```text
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
```

The output is:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

The design of the new script is:

### Treatment rows

```text
event = verified event_month
post_event = 1 if month >= event_month else 0
time_to_event = month - event_month
lead/lag indicators are generated from time_to_event
ever_treated = 1
is_treatment = absorbing treatment status
is_treatment_dynamic = monthly cursor evidence
```

### Control rows

```text
event = NA
post_event = 0
time_to_event = NA
all lead/lag indicators = 0
ever_treated = 0
is_treatment = 0
is_treatment_dynamic = cursor-based monthly evidence, expected to be 0
```

### Matching provenance

The PSM pair information is kept only as provenance:

```text
matched_as_control
matched_treatment_repos
match_ranks
matched_periods
```

Controls do not inherit pseudo-event months. Each unique control repository appears once.

## 10. Event Panel Execution Result

We ran:

```bash
python proc_scripts/prepare_panel_event_v2.py \
  --treatment-meta tmp_adoption_test/data/matched_controls_v2_treatment_only.csv \
  --pairs tmp_adoption_test/data/matched_controls_v2_pairs.csv \
  --treatment-ts tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv \
  --control-ts tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv \
  --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

The script completed successfully and generated:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

The output summary was:

```text
Rows: 324
treated repos: 13
control repos: 35
```

Panel summary:

```text
dataset_source  repos  rows  post_rows
control            35   185          0
treatment          13   139         75
```

The output file exists and has the expected event-panel columns, including:

```text
repo_name
time
dataset_source
ever_treated
is_treatment
is_treatment_dynamic
event
post_event
time_to_event
lead_6 ... lead_1
lag_0 ... lag_6
cursor
commits
lines_added
lines_removed
contributors
matched_as_control
matched_treatment_repos
match_ranks
matched_periods
```

The head of the output for `VRSEN/agency-swarm` confirms correct event-time construction:

```text
event = 2024-10
2024-09 has time_to_event = -1
lead_1 = 1
post_event = 0
```

This is consistent with the intended panel logic.

## 11. Warnings and Issues to Investigate

Two treatment repositories triggered pre-adoption activity warnings:

```text
wdm0006/elote
wdm0006/git-pandas
```

The warning means that these repositories have an empty or zero pre-adoption activity window in the selected lead period. This does not stop the pipeline, but it should be noted because these repositories may have weak pre-trend information.

A second issue is that control repositories decreased from 38 to 35 after the date filter:

```text
Filtered controls to PSM-selected repos: 38 -> 38
Date filter [2024-01-01..2025-08-31]: 649 -> 324 rows
Final control repos: 35
```

This suggests that 3 matched controls had no monthly activity rows inside the selected date window. This is not necessarily an error, because the monthly Git-history panel may only contain months with commits. However, it should be checked before running DiD models.

The next diagnostic should identify which three controls disappeared after filtering and whether they should be zero-filled or dropped.

## 12. Current Status

Completed:

```text
Treatment group validation
Treatment Git-history time series
Existing control candidate file validation
PSM matched control construction
Control clone list creation
Control repository cloning
Control Git-history time series
Control Cursor contamination check
Review of original prepare_panel_event.py
Creation of prepare_panel_event_v2.py
Paper-faithful matched event panel generation
```

Current output of interest:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

This is the first DiD-ready activity panel for the matched Python treatment-control sample.

## 13. Recommended Next Steps

The next step should not yet be SonarQube. First, we should complete sanity checks on the event panel.

### Step 1: Identify missing controls

Find which 3 PSM-selected controls are absent from the final event panel after date filtering.

### Step 2: Inspect their control time series

Check whether the missing controls have rows outside the date range or whether they have no usable monthly activity rows.

### Step 3: Decide on panel completion

If the missing controls are absent because zero-activity months are not represented in `ts_repos_monthly.csv`, we need to decide whether to:

```text
Option A: keep the unbalanced panel with 35 controls
Option B: add zero-filled repo-month rows for inactive months
```

For DiD robustness, zero-filling may be preferable if no commit activity genuinely means zero activity rather than missing data.

### Step 4: Run activity-based DiD smoke test

Before merging SonarQube outcomes, run a smoke test using existing activity outcomes:

```text
commits
lines_added
lines_removed
contributors
```

This checks whether the R DiD pipeline can read the new panel and estimate models correctly.

### Step 5: Merge SonarQube quality outcomes later

After the activity-panel structure is validated, proceed to SonarQube-based quality and complexity metrics.

The likely later outcomes include:

```text
bugs
vulnerabilities
code_smells
complexity
cognitive_complexity
duplicated_lines_density
security_hotspots
```

Those should be merged into the event panel in a later stage.
