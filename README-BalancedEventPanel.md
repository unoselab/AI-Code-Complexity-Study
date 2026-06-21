# Progress Report: Matched Control Construction, Git-History Panels, and Balanced Event Panel Preparation

## 1. Project Context

This work is part of the replication and extension effort for the study on how Cursor AI adoption affects short-term development velocity and long-term software quality in open-source repositories.

The current phase focuses on building a small-scale, Python-only matched difference-in-differences dataset. The main goal is to prepare a clean treatment-control panel that can support later DiD smoke tests and SonarQube-based quality analysis.

The current working directory is:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

The active conda environment is:

```text
aicomplexity
```

## 2. Treatment Group

We used the validated Python treatment set:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

This file contains 13 Python repositories with Cursor adoption evidence. These repositories were previously cloned and analyzed using local git history.

The treatment-side Git-history outputs are:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_did_test/ai_adoption_dates.csv
```

The treatment event months were treated as verified because the event months in the metadata matched the local Git-history adoption detector output.

The validation result was:

```text
Treatment repos: 13
Matched event/adoption month: 13
Mismatched event/adoption month: 0
Missing adoption month: 0
```

Therefore, in the new panel-preparation logic, the adoption event month is read from metadata instead of being re-detected from the monthly `cursor` column.

## 3. Control Group Matching

The matched control group was built from existing paper/GHArchive-derived control candidate files. We did not rerun GHArchive or BigQuery collection.

The control candidate files were already available for the relevant adoption periods:

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

The propensity score matching step used paper-style pre-adoption repository activity features:

```text
age_days
users_involved
n_stars
n_forks
n_releases
n_pulls
n_issues
n_comments
total_events
```

The matching process produced:

```text
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/control_repos_to_clone_v2.txt
tmp_adoption_test/data/control_repos_to_clone_v2.csv
```

The matched-pair output contained:

```text
39 matched pairs
13 treatment repositories
3 matched controls per treatment repository
38 unique matched control repositories
```

One control repository appeared in more than one matched pair. For the paper-faithful never-treated design, we keep controls as unique repositories instead of duplicating them by matched pair.

## 4. Control Repository Cloning

The matched control repositories were cloned into:

```text
/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset
```

The clone result was:

```text
38 cloned control repositories
0 failed control repositories
```

The clone log was:

```text
logs/run5b_control_clone_log_20260620-0212.csv
```

The repository count was verified by checking `.git` directories in the control clone directory.

## 5. Control Git-History Analysis

After cloning, we used local git history to compute monthly code-change activity metrics for the control repositories.

The control analysis command used:

```text
proc_scripts/analyze_repos_v2.py
```

The control analysis outputs were saved under:

```text
tmp_adoption_test/data/python_control_did_test
```

The key output files were:

```text
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_control_did_test/ai_adoption_dates.csv
```

The result was:

```text
ts_repos_monthly.csv:
  rows = 395
  unique repos = 38

ts_contributors_monthly.csv:
  rows = 1361
  unique repos = 38

ai_adoption_dates.csv:
  rows = 0
```

No Cursor adoption evidence was found in the control repositories. This confirms that the matched controls are clean never-treated controls for the current small-scale Python analysis.

## 6. Clarifying the Role of PSM Features vs. Outcome Features

We clarified an important distinction.

PSM control selection used paper/GHArchive-derived repository activity features:

```text
age_days
users_involved
n_stars
n_forks
n_releases
n_pulls
n_issues
n_comments
total_events
```

After cloning, the local git history was used for outcome and activity panel construction:

```text
commits
lines_added
lines_removed
contributors
cursor evidence
```

The paper’s velocity outcomes are `commits` and `lines_added`. The `contributors` variable is better understood as a time-varying covariate. `lines_removed` can be retained as an auxiliary metric, but it is not part of the paper’s main velocity outcomes. The `cursor` column is treatment/adoption evidence, not an outcome.

## 7. Review of Existing `prepare_panel_event.py`

Before writing the new event-panel script, we reviewed the original script:

```text
scripts/prepare_panel_event.py
```

This script was the closest existing code because it already contained logic for:

```text
event-time construction
post_event
lead and lag indicators
never-treated control handling
```

However, the original script was not suitable to use unchanged.

It detects adoption using:

```text
first month where cursor == True
```

and it applies an abandonment-masking logic:

```text
if cursor == False after adoption, set post_event back to 0
```

This is a dynamic or switching-treatment design. It is useful for robustness analysis based on observed monthly Cursor evidence, but it does not match the paper-faithful absorbing treatment design.

For the new v2 panel, we decided:

```text
Do not modify scripts/prepare_panel_event.py.
Create a new script under proc_scripts.
Use verified event_month metadata.
Do not re-detect event months from cursor == True.
Do not apply abandonment masking.
Keep cursor evidence as a separate dynamic indicator.
```

## 8. New Event Panel Script

We created and updated:

```text
proc_scripts/prepare_panel_event_v2.py
```

The script takes explicit inputs:

```text
--treatment-meta tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
--pairs tmp_adoption_test/data/matched_controls_v2_pairs.csv
--treatment-ts tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
--control-ts tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
--output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
--balanced-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The script now generates two outputs in one run:

```text
panel_event_monthly_matched_v2.csv
panel_event_monthly_matched_v2_balanced.csv
```

The unbalanced output preserves the original commit-observed monthly structure. The balanced output adds window-completion logic for zero-commit months.

## 9. Treatment and Control Logic in `prepare_panel_event_v2.py`

### Treatment rows

For treatment repositories, the script uses verified `event_month` from the treatment metadata.

Treatment rows are assigned:

```text
event = verified event_month
time_to_event = month - event_month
post_event = 1 if time_to_event >= 0 else 0
ever_treated = 1
is_treatment = absorbing treatment status
is_treatment_dynamic = cursor evidence in that month
```

This preserves the paper-faithful absorbing treatment design while still retaining dynamic monthly Cursor evidence.

### Control rows

For control repositories, the script treats them as never-treated.

Control rows are assigned:

```text
event = NA
time_to_event = NA
post_event = 0
ever_treated = 0
is_treatment = 0
is_treatment_dynamic = 0
```

Controls do not inherit pseudo-event months from matched treatment repositories. Matching information is retained only as provenance:

```text
matched_as_control
matched_treatment_repos
match_ranks
matched_periods
```

## 10. Fixing Pandas FutureWarning

During testing, Pandas raised a `FutureWarning` related to `.fillna(False).astype(bool)` on an object-dtype column.

The issue appeared in the balanced panel construction after left-joining missing repo-month rows. The `cursor` column became object dtype because it contained boolean values and missing values.

We fixed this by introducing a warning-free helper:

```python
def coerce_cursor(series: pd.Series) -> pd.Series:
    """Return a clean boolean cursor series (handles bool, 'True'/'False', NaN).

    Avoids ``.fillna(False)`` on an object-dtype array: after a left-merge the
    cursor column is object (python bools + NaN for filled rows), and fillna on
    object dtype emits pandas' downcasting FutureWarning.
    """
    if series.dtype == bool:
        return series
    truthy = {"true", "1"}
    return series.map(lambda v: str(v).strip().lower() in truthy).astype(bool)
```

We also replaced:

```python
panel["matched_as_control"] = panel["matched_as_control"].fillna(0).astype(int)
```

with an explicit numeric conversion:

```python
panel["matched_as_control"] = pd.to_numeric(
    panel["matched_as_control"], errors="coerce"
).fillna(0).astype(int)
```

After patching, the script compiled successfully and ran without Pandas `FutureWarning`.

## 11. Unbalanced Event Panel Result

The unbalanced output was:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

The unbalanced result summary was:

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

This showed that 3 matched controls disappeared after date filtering.

The missing controls were:

```text
ayushtewari/DFM
hjhxy/2023-Chinese-Collegiate-Computing-Competition
kienmarkdo/Cybersecurity-Mini-Projects
```

Inspection showed that these repositories had no local git commits during the 2024-01 to 2025-08 analysis window, even though they had GitHub platform activity in the matching data. Therefore, they should not be treated as invalid controls. They should be represented as zero-code-activity controls in the activity panel.

## 12. Balanced Event Panel Construction

We added window completion to the panel-preparation script.

The analysis window is:

```text
2024-01 to 2025-08
```

The zero-fill rule is:

```text
start_month = max(analysis_start_month, first_commit_month)
end_month = analysis_end_month
```

For months with no local git commits, dynamic activity fields are filled with zero:

```text
commits = 0
lines_added = 0
lines_removed = 0
contributors = 0
cursor = False
is_treatment_dynamic = 0
```

This avoids fabricating rows before a repository’s first observed code-history month, while preserving zero-activity months after the repository exists.

## 13. Balanced Event Panel Result

The balanced output was:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The balanced result summary was:

```text
Rows: 738
treated repos: 13
control repos: 38
```

Panel summary:

```text
dataset_source  repos  rows  post_rows
control            38   530          0
treatment          13   208         98
```

This confirms that the balanced panel successfully restored all 38 controls.

The previously dropped controls were restored as zero-code-activity controls:

```text
ayushtewari/DFM:
  rows = 20
  time = 2024-01 to 2025-08
  commits sum = 0
  lines_added sum = 0
  contributors sum = 0

hjhxy/2023-Chinese-Collegiate-Computing-Competition:
  rows = 20
  time = 2024-01 to 2025-08
  commits sum = 0
  lines_added sum = 0
  contributors sum = 0

kienmarkdo/Cybersecurity-Mini-Projects:
  rows = 20
  time = 2024-01 to 2025-08
  commits sum = 0
  lines_added sum = 0
  contributors sum = 0
```

## 14. Sanity Checks

The balanced panel passed key sanity checks.

The treatment event logic is correct:

```text
post_event != (time_to_event >= 0) rows: 0
```

This means that for treatment repositories:

```text
time_to_event >= 0  => post_event = 1
time_to_event < 0   => post_event = 0
```

The balanced panel contains:

```text
treated post rows = 98
zero-activity treated post rows = 23
```

This is expected. It means that 23 post-adoption treatment rows had zero commits and zero lines added. These rows are still post-adoption observations under the absorbing treatment design.

The control checks also passed:

```text
control post_event sum = 0
control dynamic treatment sum = 0
```

This confirms that controls remain never-treated.

## 15. Remaining QC Warnings

The script still reports:

```text
Treated repo wdm0006/elote has empty/zero pre-adoption window
Treated repo wdm0006/git-pandas has empty/zero pre-adoption window
```

These are not code errors. They are data-quality warnings.

After balanced window completion, these warnings mean that the relevant pre-adoption windows have true zero or near-zero code activity, not merely missing rows. This is important to keep for interpretation because these repositories may have weak pre-trend information.

## 16. Current Status

Completed:

```text
Validated Python treatment set
Verified treatment adoption months
Built PSM matched control group
Cloned 38 unique matched controls
Computed local git-history activity for controls
Confirmed no Cursor evidence in controls
Reviewed original prepare_panel_event.py
Created prepare_panel_event_v2.py
Generated unbalanced matched event panel
Added window completion logic
Fixed Pandas FutureWarning
Generated balanced matched event panel
Restored all 38 controls in the balanced panel
Confirmed absorbing treatment structure
Confirmed never-treated control structure
```

The main analysis-ready activity panel is now:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

## 17. Recommended Next Step

The next step should be an activity-based DiD smoke test before moving to SonarQube.

Use the balanced panel and test the velocity outcomes aligned with the paper:

```text
commits
lines_added
```

Use `contributors` as a covariate rather than a main outcome.

The smoke test should verify that the R DiD pipeline can read the new balanced event panel and estimate models without structural errors.

After that, proceed to SonarQube quality outcome merging and analysis.

Potential next script:

```text
run6a-activity-did-smoke-test.sh
```

Potential input:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

Potential first outcomes:

```text
commits
lines_added
```


---
---
---

## Addendum: Clarifications for Reproducibility and Interpretation

### A. Missing Controls in the Unbalanced Panel

The unbalanced event panel contained only 35 of the 38 matched control repositories because three controls had no local git commits during the 2024-01 to 2025-08 analysis window. These controls were:

```text
ayushtewari/DFM
hjhxy/2023-Chinese-Collegiate-Computing-Competition
kienmarkdo/Cybersecurity-Mini-Projects
```

These repositories were not invalid controls. They were selected by the PSM process using GHArchive-derived platform activity features, but their local git commit activity during the analysis window was zero.

The affected matched pairs were:

```text
wdm0006/elote
  matched_period = 202501
  missing/restored control:
    rank 1: ayushtewari/DFM

TextGeneratorio/text-generator.io
  matched_period = 202502
  missing/restored controls:
    rank 1: kienmarkdo/Cybersecurity-Mini-Projects
    rank 2: hjhxy/2023-Chinese-Collegiate-Computing-Competition
```

In the unbalanced panel, these treated repositories effectively had fewer observed control rows. In the balanced panel, these controls were restored as zero-code-activity controls for the analysis window.

### B. Interpretation of Empty Pre-Adoption Windows

The warnings for `wdm0006/elote` and `wdm0006/git-pandas` indicate that their pre-adoption activity windows have zero or near-zero git activity after window completion. This is no longer a missing-row problem; it is a genuine weak-pre-period signal.

This matters for later DiD and event-study interpretation. These repositories may contribute little information to pre-trend estimation. In cohort-specific estimators, especially when a cohort contains only a small number of treated repositories, pre-trend diagnostics for the corresponding cohort may be weak or uninformative.

### C. Measurement Difference in `users_involved`

The PSM features are based on existing GHArchive-derived control candidate files and treatment event files. There is a minor measurement detail to keep in mind: control candidate generation counted involved users using GHArchive actor identifiers, while some treatment-side event processing may use actor login strings.

These are usually close to one-to-one in practice, but they are not conceptually identical. This should be recorded as a small reproducibility note rather than treated as a blocking issue.

### D. Outcome Scale Imbalance

The balanced panel shows that control repositories have a much larger total `lines_added` value than treatment repositories. This is expected because some matched controls are large repositories, and PSM was performed on pre-adoption platform activity features rather than directly on local git outcome scale.

This does not invalidate the panel, but it suggests that DiD smoke tests should inspect outliers and consider transformations such as `log1p(lines_added)` and `log1p(commits)` in addition to raw outcomes.

### E. Main Panel Choice

The balanced panel should be treated as the main activity panel for the paper-faithful velocity analysis because it preserves zero-commit months.

```text
Main activity panel:
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The unbalanced panel should be kept for comparison and possible robustness checks. It is closer to an active-month-only panel because months without commits are absent.

A later robustness analysis can derive active-month subsets from the balanced panel:

```text
Active months:
  commits > 0

Very active months:
  commits >= 10
```

### F. Scope of the Activity-Based DiD Smoke Test

The next activity-based DiD smoke test should be interpreted only as a pipeline validation step. The small sample size, with 13 treated repositories and small adoption cohorts, means that estimated effects and standard errors should not be interpreted as final empirical findings.

The smoke test is intended to check whether the balanced event panel can be read by the R DiD scripts and whether the expected model structure runs correctly for the velocity outcomes:

```text
outcomes:
  commits
  lines_added

covariate:
  contributors
```
