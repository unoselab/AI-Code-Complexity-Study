## Progress Report: Figure 7 JavaScript/TypeScript Treatment Pipeline

### Objective

The current goal is to reproduce the **Figure 7-style JavaScript/TypeScript robustness setting** from the Cursor adoption paper. This setting should use a combined JavaScript/TypeScript treatment sample, not a TypeScript-only sample.

The main treatment candidate pool is:

```text
tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv
```

This file contains:

```text
441 JavaScript/TypeScript treatment repositories
- TypeScript: 379
- JavaScript: 62
```

The strict balanced-window subset is:

```text
tmp_jsts_test/data/original_paper_treatment_jsts_repos_bw6.csv
```

This contains:

```text
92 repositories with balanced_window >= 6
```

The main Figure 7-style analysis should use the **441 unbalanced JS/TS treatment repositories**. The 92-repository balanced-window subset should be used later only as a robustness or sensitivity check.

### Completed Steps

The following scripts have been renamed and reorganized for the Figure 7 JS/TS pipeline:

```text
run7a-count-repo.sh
run7b-detect-ai-adoption-repo.sh
run7c-clone-ai-adoption-repo.sh
run7d-analyze-ai-adoption-repo.sh
```

The clone wrapper `run7c-clone-ai-adoption-repo.sh` should now be updated to produce a timestamped log under:

```text
logs/
```

The updated wrapper will call `run7b-detect-ai-adoption-repo.sh` in clone mode and preserve a timestamped backup of the clone-status CSV.

### Smoke Clone Result

A smoke clone test was run with:

```bash
MAX_CLONES=10 bash run7c-clone-ai-adoption-repo.sh
```

The result was:

```text
Candidate rows: 441
Clone log rows: 10
Processed repositories: 10
Usable repositories: 8
Failed repositories: 2
Not attempted yet: 431
```

The 431 missing rows are expected because `MAX_CLONES=10` was used. They are not failures.

The two failed repositories were:

```text
0xAquaWolf/portfolio
0xsend/sendapp
```

Both failed with `Repository not found`, so this appears to be a GitHub availability issue rather than a script error.

### Smoke Analysis Result

A smoke repository-history analysis was run with:

```bash
MAX_REPOS=8 NUM_PROCESSES=1 bash run7d-analyze-ai-adoption-repo.sh
```

The repository history analysis succeeded. It produced the following files:

```text
tmp_jsts_test/data/jsts_did_test/ts_repos_monthly.csv
tmp_jsts_test/data/jsts_did_test/ts_contributors_monthly.csv
tmp_jsts_test/data/jsts_did_test/cursor_commits.csv
tmp_jsts_test/data/jsts_did_test/ai_adoption_dates.csv
```

The key success signal was:

```text
Repos with Cursor adoption evidence: 8
```

This means that the pipeline successfully found Cursor adoption evidence in all 8 usable cloned repositories from the smoke test.

### Current Known Issue

The `run7d` script failed only at the adoption-month validation step:

```text
Missing candidate columns: ['event_month']
```

This is not a repository analysis failure. The cause is that the usable clone list:

```text
tmp_jsts_test/data/jsts_treatment_clone_usable_repos.csv
```

was generated from the clone-status file, which does not currently include the `event_month` column.

The fix should be applied after the full clone finishes. At that point, we should attach `event_month` metadata from the original panel or event-window summary to the usable cloned repository list, then rerun the validation step.

### Immediate Next Step

The next step is to start the full treatment clone process in `tmux`.

Recommended tmux session:

```bash
tmux new -s aicomplexity-did
```

Inside tmux:

```bash
cd ~/Documents/repro-test01/ai_code_complexity_study
conda activate aicomplexity
MAX_CLONES=0 bash run7c-clone-ai-adoption-repo.sh
```

Detach from tmux:

```text
Ctrl-b d
```

Reattach later:

```bash
tmux attach -t aicomplexity-did
```

Monitor the latest clone log from another terminal:

```bash
cd ~/Documents/repro-test01/ai_code_complexity_study
LATEST_LOG=$(ls -t logs/run7c_clone_ai_adoption_repo_*.log | head -1)
tail -f "${LATEST_LOG}"
```

### After Full Clone Finishes

After the full clone completes, we should inspect:

```text
tmp_jsts_test/data/jsts_treatment_clone_status.csv
logs/run7c_clone_ai_adoption_repo_<timestamp>.log
logs/run7b_clone_log_<timestamp>.csv
```

The next checks should be:

```text
1. Number of usable JS/TS treatment repositories
2. Number of failed repositories
3. TypeScript vs JavaScript distribution among usable repositories
4. Whether the usable count is close to the paper's Figure 7 JS/TS treatment count
5. Whether failed repositories are mostly deleted/private/nonexistent repositories
```

### Planned Next Stage

After the full treatment clone is complete:

```text
1. Create the final usable treatment repository file.
2. Add event_month metadata to the usable repository file.
3. Rerun run7d on all usable treatment repositories.
4. Validate git-detected adoption_month against event_month.
5. Move to JS/TS control matching and control clone.
```

So the immediate action is:

```bash
MAX_CLONES=0 bash run7c-clone-ai-adoption-repo.sh
```

---
---
---
---
---
---
---

# June 24

```
run7a-count-repo.sh
  Step 1. Count and prepare the JS/TS treatment candidate pool.
  Output: original_paper_treatment_jsts_repos.csv

run7b-detect-ai-adoption-repo.sh
  Step 2. Core engine script.
  It can detect/filter candidates and perform clone/check logic.
  In this pipeline, it is usually called by wrapper scripts, not manually.

run7c1-clone-ai-adoption-repo.sh
  Step 3. Clone the JS/TS treatment candidate repositories.
  Input: original_paper_treatment_jsts_repos.csv
  Output: jsts_treatment_clone_status.csv

run7c2-create-clone-usable-repos.sh
  Step 4. Create a usable cloned repo list and attach event metadata.
  Input: jsts_treatment_clone_status.csv + panel_event_monthly.csv
  Output: jsts_treatment_clone_usable_repos_with_event.csv

run7c3-split-valid-event-repos.sh
  Step 5. Split usable repos into valid-event and missing-event files.
  Input: jsts_treatment_clone_usable_repos_with_event.csv
  Output:
    jsts_treatment_clone_usable_repos_with_event_valid.csv
    jsts_treatment_clone_usable_missing_event_month.csv

run7d-analyze-ai-adoption-repo.sh
  Step 6. Analyze git history for valid cloned treatment repos.
  Input should now be:
    jsts_treatment_clone_usable_repos_with_event_valid.csv
```

```
run7c1 = clone
run7c2 = attach event metadata
run7c3 = split valid vs missing event metadata
```

```
run7d1-analyze-ai-adoption-repo.sh
  Step 0. Decide which repo input file to use
  Step 0b. Validate the repo input file
  Step 1. Run git-history analysis
  Step 2. Compare event_month vs git-detected adoption_month
  Step 3. Print generated output files
```

---
---
---
---
---
---
---


Daily Research Report

Date: 2026-06-24

Project: 2026 MSR Speed at the Cost of Quality Replication / Extension

Objective:
The objective today was to complete the JavaScript/TypeScript treatment-side repository-history reconstruction and begin constructing the matched control repository sample for the JS/TS DiD pipeline. The main focus was to validate treatment adoption timing, preserve multiple treatment-sample options, extract matched controls from the original matching artifacts, remove treatment-control overlap, and smoke-test control repository cloning.

What We Did:

1. Completed the JS/TS treatment-side repository-history analysis.

We successfully ran the full `run7d` analysis on the valid JavaScript/TypeScript treatment sample.

Input:
`tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv`

The final valid treatment sample contained 398 repositories:

* TypeScript: 342
* JavaScript: 56

The full `run7d` analysis generated the following files:

`tmp_jsts_test/data/jsts_did_test/ts_repos_monthly.csv`
`tmp_jsts_test/data/jsts_did_test/ts_contributors_monthly.csv`
`tmp_jsts_test/data/jsts_did_test/cursor_commits.csv`
`tmp_jsts_test/data/jsts_did_test/ai_adoption_dates.csv`
`tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv`

2. Validated original `event_month` against locally detected `adoption_month`.

The adoption-month validation file contained 398 repositories.

Results:

* Matched: 381
* Mismatched: 13
* Missing local adoption month: 4
* Local adoption month detected: 394 / 398
* Exact match rate: 381 / 398 = 95.73%
* Local detection rate: 394 / 398 = 98.99%

Interpretation:
The original event metadata is strongly aligned with the local Git-history evidence. We decided to keep all 398 valid treatment repositories for the main treatment-side reconstruction, while also preserving stricter robustness samples.

3. Created treatment-sample options with `run7d3`.

We ran:

`./run7d3-save-treatment-options.sh`

Generated treatment sample files:

`tmp_jsts_test/data/jsts_treatment_sample_main_398.csv`
`tmp_jsts_test/data/jsts_treatment_sample_exact_match_381.csv`
`tmp_jsts_test/data/jsts_treatment_sample_within1_month_388.csv`
`tmp_jsts_test/data/jsts_treatment_sample_diagnostic_10.csv`

Sample definitions:

* Main sample: all 398 valid treatment repositories.
* Exact-match sample: 381 repositories where `event_month == adoption_month`.
* Within-one-month sample: 388 repositories where event/adoption timing matched exactly or differed by at most one month.
* Diagnostic sample: 10 repositories with missing local adoption month or large timing mismatch.

Decision:
Use the 398-repository sample for the main analysis. Preserve 381 and 388 repository subsets for robustness checks.

4. Began matched control extraction using original matching artifacts.

We inspected the original backup files and confirmed that `data_baseline_backup/matching.csv` is a wide-format matching file with columns:

`repo_name`
`matched_period`
`group`
`propensity_score`
`matched_control_1`
`matched_control_2`
`matched_control_3`

This means each treatment repository can have up to three matched controls.

We agreed that the next step is not to search for new control candidates from scratch. Instead, we should use the original matching artifacts and extract the matched controls corresponding to the current JS/TS treatment sample.

5. Detected treatment-control overlap/leakage.

Initial extraction found:

* Raw unique controls: 480
* Current JS/TS treatment overlap: 1
* Full Cursor-adopter population overlap: 13

The overlapping control repositories were:

`AmandaloveYang/ClearPage`
`Codehagen/Badget`
`SquirrelCorporation/SquirrelServersManager`
`abiteman/DumbKan`
`aldrin-labs/opensvm`
`extendui/extendui`
`gravity-ui/graph`
`janus-idp/backstage-showcase`
`maxentr/skyjo`
`mendix/web-widgets`
`moinulmoin/chadnext`
`thesysdev/crayon`
`yuiseki/TRIDENT`

We clarified the methodological distinction:

A treated repository can contribute untreated pre-adoption observations in the staggered DiD estimator. However, a repository that adopts Cursor should not be used as a never-treated matched control repository.

Therefore, these 13 overlapping repositories should be removed from the clean matched control clone list, while raw matching outputs should be preserved for audit.

6. Fixed `proc_scripts/extract-jsts-control-repos.py`.

We modified the extraction behavior so that the script now:

* Extracts raw matched pairs.
* Detects overlap with the current JS/TS treatment sample.
* Detects overlap with the full Cursor-adopting population.
* Saves raw outputs for audit.
* Saves overlap diagnostic files.
* Removes overlap rows from the clean matched-pair file.
* Saves a clean unique control clone list.
* Exits successfully after overlap removal.

After rerunning `run8a`, the result was:

* Treatment sample rows: 398
* Full adopter population size: 830
* Matching rows for treatment sample: 384
* Treatments missing matching row: 14
* Raw matched pair rows: 1152
* Clean matched pair rows: 1129
* Removed overlap pair rows: 23
* Raw unique control repos: 480
* Clean unique control repos: 467
* Removed overlap unique control repos: 13
* Treatment repos with clean pairs: 384

Generated files:

`tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv`
`tmp_jsts_test/data/jsts_treatment_missing_matching_main_398.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_overlap_pairs.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398_overlap_repos.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_raw.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398_raw.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_coverage.csv`
`tmp_jsts_test/data/jsts_control_extract_summary_main_398.csv`

Validation after cleaning:

* Clean control repos: 467
* Subset overlap after cleaning: 0
* Full adopter overlap after cleaning: 0

7. Smoke-tested control repository cloning with `run8b`.

We ran:

`MAX_CLONES=10 ./run8b-clone-jsts-control-repos.sh`

The script used:

`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv`

as the clean control clone list.

Smoke clone result:

* Processed: 10
* Cloned: 9
* Failed: 1

The failed repository was:

`AdrenaFoundation/frontend`

Reason:
The GitHub repository was not found. This likely means the repository was deleted, renamed, or made private after the original data collection.

Generated clone status files:

`tmp_jsts_test/data/jsts_control_clone_status_main_398.csv`
`tmp_jsts_test/data/jsts_control_clone_status_main_398_20260624-164811.csv`

Interpretation:
The smoke clone test was successful. One repository failure is expected and does not indicate a script problem. The full clone can proceed using the clean 467-repository control list.

Key Results:

Treatment-side pipeline:

* Final valid JS/TS treatment sample: 398 repositories
* Local Cursor adoption detected: 394 / 398
* Exact event/adoption match: 381 / 398
* Main treatment sample preserved: 398 repositories
* Robustness samples created: 381 and 388 repositories

Control-side extraction:

* Original matched treatment rows found: 384
* Missing matching rows: 14
* Raw matched pairs: 1152
* Clean matched pairs: 1129
* Raw unique controls: 480
* Clean unique controls after overlap removal: 467
* Overlap after cleaning: 0

Control clone smoke test:

* Smoke clone processed: 10
* Successfully cloned: 9
* Failed: 1
* Full clone target: 467 clean control repositories

Errors / Issues:

1. Four treatment repositories had original `event_month` metadata but no locally detected `adoption_month`.
   These were preserved in a diagnostic file and do not block the main treatment analysis.

2. Thirteen treatment repositories had mismatched `event_month` and local `adoption_month`.
   Most were small timing differences, but large mismatches were saved for diagnostic inspection.

3. Fourteen treatment repositories had no matching row in `matching.csv`.
   These repositories can remain part of the treatment-side descriptive reconstruction but cannot be included in the matched-control DiD sample unless we rematch or define an alternative strategy.

4. Thirteen raw matched controls overlapped with the full Cursor-adopting population.
   These were removed from the clean control clone list and saved as overlap diagnostics.

5. One smoke-test control repository failed to clone because GitHub reported that the repository was not found.

Interpretation:

The treatment-side JS/TS reconstruction is complete and reliable. The original `event_month` metadata is highly consistent with local Git-history evidence.

The control-side extraction is now methodologically cleaner than the raw recovered matching artifact because we removed matched controls that overlap with the full Cursor-adopting population. This is consistent with the paper’s design, where matched controls are intended to be never-treated repositories.

The current matched DiD sample is based on 384 treatment repositories with clean matched controls. Most treatment repositories retain three controls, while 23 treatment repositories retain two controls after overlap removal.

Next Steps:

1. Run the full control clone using the clean 467-repository control list.

Command:

`CONTROL_REPOS_FILE=tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv MAX_CLONES=0 ./run8b-clone-jsts-control-repos.sh`

Estimated completion time:

* Optimistic: 10–15 minutes
* Realistic: 20–45 minutes
* Conservative: up to 1 hour

2. After full clone, summarize clone status.

Check:

* Total processed controls
* Successfully cloned controls
* Failed controls
* Existing/skipped controls

3. Create `run8c` to build usable control files.

Expected `run8c` tasks:

* Keep only cloned or skipped-existing controls.
* Save failed controls separately.
* Remove failed controls from matched pairs.
* Recompute treatment-to-control coverage after clone availability.
* Save final usable control sample.

4. Create `run8d` to analyze cloned control repositories.

Expected `run8d` tasks:

* Run local Git-history analysis on usable control repositories.
* Generate monthly control time series.
* Generate contributor-level control time series.

5. Prepare treatment-control DiD panel.

After treatment and control monthly time series are both ready:

* Combine treatment and control time series.
* Attach matched pair information.
* Attach treatment event timing to matched controls.
* Construct `time_to_event`, `post_event`, lead, and lag variables.
* Prepare the final JS/TS matched panel for DiD estimation.

Files Generated Today:

Treatment-side:
`tmp_jsts_test/data/jsts_did_test/ts_repos_monthly.csv`
`tmp_jsts_test/data/jsts_did_test/ts_contributors_monthly.csv`
`tmp_jsts_test/data/jsts_did_test/cursor_commits.csv`
`tmp_jsts_test/data/jsts_did_test/ai_adoption_dates.csv`
`tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv`
`tmp_jsts_test/data/jsts_treatment_sample_main_398.csv`
`tmp_jsts_test/data/jsts_treatment_sample_exact_match_381.csv`
`tmp_jsts_test/data/jsts_treatment_sample_within1_month_388.csv`
`tmp_jsts_test/data/jsts_treatment_sample_diagnostic_10.csv`

Control-side:
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv`
`tmp_jsts_test/data/jsts_treatment_missing_matching_main_398.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_overlap_pairs.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398_overlap_repos.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_raw.csv`
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398_raw.csv`
`tmp_jsts_test/data/jsts_matched_control_pairs_main_398_coverage.csv`
`tmp_jsts_test/data/jsts_control_extract_summary_main_398.csv`
`tmp_jsts_test/data/jsts_control_clone_status_main_398.csv`
`logs/run8b_jsts_control_clone_log_20260624-164811.csv`

Commands Used:

`./run7d3-save-treatment-options.sh`

`./run8a-extract-jsts-control-repos.sh`

`MAX_CLONES=10 ./run8b-clone-jsts-control-repos.sh`

Main Decision Made Today:

Use:
`tmp_jsts_test/data/jsts_treatment_sample_main_398.csv`

as the main treatment-side sample.

Use:
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398.csv`

as the clean control clone list.

Do not use:
`tmp_jsts_test/data/jsts_control_repos_to_clone_main_398_raw.csv`

for cloning, because it contains control repositories overlapping with the Cursor-adopting population.
