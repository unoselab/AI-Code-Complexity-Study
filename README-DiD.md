# Progress Report: Small-Scale Python DiD Pipeline for AI/Cursor Adoption Study

## 1. Project Goal

The current goal is to reproduce and understand the full pipeline behind the MSR 2026 study, “Speed at the Cost of Quality,” using a small-scale dataset before scaling to the full paper-level Difference-in-Differences analysis.

The immediate objective is not yet to produce the final paper-scale DiD results. Instead, we are building and validating an end-to-end small-scale workflow using Python repositories only. This allows us to verify each pipeline component: treatment selection, cloning, Git-history validation, adoption timing verification, and eventually control selection, SonarQube measurement, and DiD estimation.

## 2. Current Working Dataset

We selected Python repositories from the top 100 AI/Cursor adoption candidates and filtered them to keep only usable cloned repositories.

The current treatment input file is:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

This file contains 13 usable Python AI-adopting treatment repositories. Failed or inaccessible Python repositories were excluded from this file.

The file includes key columns such as:

```text
rank
repo_name
event_month
panel_first_month
panel_latest_month
pre_panel_months
post_panel_months
cursor_commit_rows
cursor_authors
repo_stars
repo_primary_language
repo_commits
repo_contributors
cursor_commit_share
status
target_dir
note
```

This file is now the clean treatment-repository input for the small-scale Python DiD pipeline.

## 3. Candidate Selection Completed

We created and used `proc_scripts/find_repo_pre_post_ai_adoption.py` to select candidate repositories from the baseline event-panel data.

The script reads from:

```text
data_baseline_backup/panel_event_monthly.csv
```

It selects treatment repositories with sufficient pre-adoption and post-adoption months, ranks them by a high-contributor Cursor adoption proxy, and writes two files:

```text
tmp_adoption_test/data/top_100_clone_candidates.csv
tmp_adoption_test/data/top_100_clone_candidates_all_eligible.csv
```

The `top_100_clone_candidates.csv` file contains the first 100 ranked repositories. The `top_100_clone_candidates_all_eligible.csv` file contains all eligible repositories in sorted rank order, so ranks 101, 102, and later can be used as replacements if some top-100 repositories fail to clone.

## 4. Repository Cloning Completed

We created `proc_scripts/clone_repos_v2.py` as a wrapper-style cloning script instead of modifying the original `scripts/clone_repos.py`.

This script supports:

```text
custom candidate CSV
custom clone root
timestamped clone logs
skip existing repositories
non-interactive Git cloning
```

The clone root is:

```text
../ai_code_complexity_study_repo_dataset
```

The full top-100 clone run processed 100 repositories:

```text
processed: 100
cloned: 71
skipped_existing: 23
failed: 6
```

Therefore, 94 repositories were locally usable from the top-100 list.

The non-interactive Git setting worked correctly. When GitHub required credentials for inaccessible repositories, the script logged the failure and continued instead of stopping at a username/password prompt.

## 5. Python Treatment Repository Filtering Completed

We created `proc_scripts/check_python_repo_clone.py` to identify usable Python repositories from the top-100 candidate list and clone log.

The script now writes only usable Python repositories to:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

It no longer creates a separate `_usable.csv` file. This keeps the workflow simpler.

The current result is:

```text
Python candidate repos: 15
Python usable repos written: 13
Python failed repos excluded: 2
```

The two failed Python repositories were excluded from the final Python treatment input file.

## 6. Git-History Repository Analysis Completed

We created and ran `run4c-analyze-repo.sh`.

This script runs:

```text
proc_scripts/analyze_repos_v2.py
```

using the 13 usable Python treatment repositories.

The run produced the following files:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_did_test/cursor_commits.csv
tmp_adoption_test/data/python_did_test/ai_adoption_dates.csv
```

The most important file for later DiD construction is:

```text
ts_repos_monthly.csv
```

This is the repo-month panel containing monthly activity data such as commits, lines added, lines removed, contributors, latest monthly commit, and Cursor status.

The second most important file is:

```text
ai_adoption_dates.csv
```

This file gives the Git-history detected Cursor adoption date and adoption month for each treatment repository.

## 7. Repo Name Consistency Fix Completed

We identified a correctness risk in the original analyzer: some original logic reconstructs `repo_name` from folder names by replacing underscores with slashes.

This can break repositories whose owner or repository name contains underscores.

To avoid downstream join errors, we updated `proc_scripts/analyze_repos_v2.py` so that after calling the original `process_repository()`, it overwrites the `repo_name` field in all returned rows using the authoritative value from the input CSV:

```python
correct_repo_name = str(repo_dict["repo_name"]).strip()

for rows in (repo_ts, contrib_ts, cursor_commits):
    for row in rows:
        row["repo_name"] = correct_repo_name
```

This keeps `ts_repos_monthly.csv`, `ts_contributors_monthly.csv`, `cursor_commits.csv`, and `ai_adoption_dates.csv` join-compatible.

## 8. Adoption Timing Validation Completed

We created `proc_scripts/check_time_of_event_and_adoption.py` and integrated it into `run4c-analyze-repo.sh`.

This script compares:

```text
ai_adopt_repo_python.csv:event_month
```

against:

```text
python_did_test/ai_adoption_dates.csv:adoption_month
```

The output file is:

```text
tmp_adoption_test/data/python_did_test/adoption_month_check.csv
```

The latest run showed:

```text
Treatment repos: 13
Matched event/adoption month: 13
Mismatched event/adoption month: 0
Missing adoption month: 0
```

This is a strong validation result. It means all 13 Python treatment repositories have Git-history Cursor evidence, and their detected adoption month exactly matches the baseline event month.

## 9. Current Status

The treatment side of the small-scale Python DiD pipeline is now ready.

We have:

```text
13 usable Python AI-adopting treatment repositories
verified Git-history Cursor adoption evidence
100% event_month/adoption_month agreement
repo-month activity panel
contributor-month activity panel
Cursor commit evidence
timestamped run logs
```

However, this is not yet a complete DiD dataset because we still need control repositories.

At this point:

```text
Treatment repos: ready
Control repos: not ready
SonarQube quality metrics: not yet collected for this small DiD panel
Final DiD regression: not yet run
```

## 10. Next Step: Control Repository Selection

The next major task is to find comparable Python control repositories.

Control repositories should satisfy:

```text
primary language = Python
no Cursor adoption evidence during the analysis window
similar stars
similar commit count
similar contributor count
similar repository size
similar pre-period activity if available
```

Each treatment repository should be matched with one or more control repositories.

For DiD, each matched control repository should receive the same pseudo-event month as its matched treatment repository. For example:

```text
Treatment repo: airweave-ai/airweave
event_month: 2025-03

Matched control repo: some-python/control-repo
pseudo_event_month: 2025-03
```

This allows treatment and control repositories to be aligned on the same relative event-time scale.

## 11. Planned Small-Scale DiD Pipeline

The next full small-scale pipeline should be:

```text
1. Finalize 13 validated Python treatment repositories
2. Select comparable Python control repositories
3. Clone control repositories
4. Verify controls have no Cursor adoption evidence
5. Build treated + control repo-month panel
6. Assign treatment indicator and event month
7. Run SonarQube on monthly historical snapshots
8. Merge SonarQube outcomes into the repo-month panel
9. Run small-scale DiD and event-study models
10. Inspect whether the pipeline produces sensible results before scaling up
```

## 12. Important Reminder

The current work is a small-scale validation pipeline. It is valuable because it checks the mechanics of the full study pipeline, but it should not yet be interpreted as the final empirical result of the paper.

The final paper-scale DiD analysis will require:

```text
larger treatment sample
matched control sample
full SonarQube metric collection
robust event-study design
pre-trend checks
sensitivity analyses
```

For now, the most important achievement is that the treatment-side pipeline works cleanly and the adoption timing validation is perfect for the 13 Python repositories.
