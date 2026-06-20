# Progress Report: Control Group Construction and GHArchive Pipeline

## 1. Current Objective

The current phase is to build a matched control group for the 13 Python repositories that adopted Cursor or Cursor-like AI coding tools. The control group will be used later for downstream quality and complexity analysis, including code metrics and SonarQube-based static analysis.

The key design principle is:

```text
Do not clone all control candidates.
Use existing GHArchive-derived control candidate CSV files.
Run Propensity Score Matching.
Clone only the final matched control repositories.
```

## 2. Environment and Data Status

We are working in the project directory:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

The conda environment is:

```text
aicomplexity
```

We confirmed that the main GHArchive-derived files already exist locally:

```text
data/repo_events.csv
data/control_repo_candidates_202408.csv
data/control_repo_candidates_202409.csv
data/control_repo_candidates_202410.csv
data/control_repo_candidates_202411.csv
data/control_repo_candidates_202412.csv
data/control_repo_candidates_202501.csv
data/control_repo_candidates_202502.csv
data/control_repo_candidates_202503.csv
```

The backup copies also exist under:

```text
data_baseline_backup/
```

Because these control candidate files already exist, we chose **Option A**: use the existing control files instead of running a fresh expensive BigQuery control discovery query.

## 3. BigQuery and GHArchive Work Completed

We validated the BigQuery/GHArchive setup in several stages.

First, we verified that GCP authentication, project configuration, ADC quota project, and the Python BigQuery client work correctly with the project:

```text
se-project-438721
```

Then we tested a small treatment-side GHArchive query using daily tables. That query fetched raw events for a few known treatment repositories and confirmed that the treatment-side query shape works:

```text
type
created_at
repo
actor
```

This is the raw-event shape used for treatment repositories.

Next, we tested control-side queries.

The original monthly control candidate query was too large. A dry run showed roughly 60 to 100 GiB depending on the query variant. This was not a failure; it showed that the dry-run and safety cap logic worked correctly.

We then created and validated a daily-table seeded control smoke test. This daily test used:

```text
githubarchive.day.20*
```

instead of:

```text
githubarchive.month.*
```

The daily seeded control test succeeded under the 1 GiB cap. It produced the correct 12-column control schema:

```text
repo_name
period
period_type
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

This confirmed that the control aggregation logic and output schema are correct, even though the daily test is only a schema and logic smoke test, not a realistic six-month metrics run.

## 4. Existing Control Candidate Files Confirmed

We verified that the existing control candidate files have the expected schema for all relevant months:

```text
202408
202409
202410
202411
202412
202501
202502
202503
```

The 13 selected treatment repositories have adoption months within this available range:

```text
2024-10
2024-12
2025-01
2025-02
2025-03
```

This means each treatment repo has a corresponding existing control candidate file for its adoption month.

We also confirmed that all 13 treatment repositories are present in:

```text
data/repo_events.csv
```

The check showed:

```text
Treatment repos: 13
Missing treatment repos: 0
```

This means treatment-side metrics can be computed from the existing raw event file.

## 5. Propensity Score Matching Meaning

In this phase, “matching” means **Propensity Score Matching for building a control group**.

The logic is:

```text
Treatment group:
Repositories that adopted Cursor / AI coding tools.

Control group:
Repositories that did not adopt Cursor, but looked similar before the adoption month.
```

The matching features include pre-adoption activity metrics such as:

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

The matching process estimates a propensity score, which represents how similar a repository is to the treatment group based on pre-adoption behavior. Each treatment repository is then matched with the closest control repositories by propensity score.

## 6. Matching Wrapper Created and Executed

We created:

```text
proc_scripts/find_control_groups_v2.py
```

This wrapper uses existing local files only. It does not call BigQuery.

Inputs:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
data/repo_events.csv
data/control_repo_candidates_YYYYMM.csv
```

Outputs:

```text
tmp_adoption_test/data/matched_controls_v2_summary.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/control_repos_to_clone_v2.txt
```

Important behavior added in the wrapper:

```text
All treatment repositories are removed from the control pool before matching.
```

This prevents treatment-control leakage.

## 7. Python Environment Issue Fixed

When importing `scripts.matching_complex.py`, we initially hit a NumPy/SciPy/scikit-learn import error:

```text
ImportError: numpy._core.multiarray failed to import
```

The environment had mixed pip and conda packages:

```text
numpy        pypi_0
scipy        pypi_0
scikit-learn pypi_0
pandas       conda-forge
```

The issue was a binary compatibility problem between NumPy, SciPy, and scikit-learn.

The fix was to remove pip-installed binary packages and reinstall compatible conda-forge builds.

After this fix, the matching script ran successfully.

## 8. PSM Debug Run Completed

We first ran PSM without language matching to test the pipeline quickly.

This debug run confirmed:

```text
13 treatment repositories loaded
26,129 treatment event rows loaded
13 treatment metrics computed
control candidate files loaded by month
treatment repos removed from control pool
propensity scores computed
matched controls generated
clone list generated
```

However, the debug output showed:

```text
language: ignored
```

So that run was only a pipeline validation, not the final control group.

## 9. Language-Matched PSM Completed

We then ran the matching with language matching enabled.

The result generated final matched control candidates for the 13 Python treatment repositories.

The output showed:

```text
Treatment rows: 13
Matched pair rows: 39
Unique controls in pairs: 38
Clone list lines: 38
Unique clone list repos: 38
Treatment-control leakage: none
```

Each treatment repo has 3 matched controls:

```text
13 treatment repositories × 3 matched controls = 39 matched pairs
```

There is one repeated control repository:

```text
yuvraj108c/ComfyUI_InvSR
```

This repository was matched to two treatment repositories. This is acceptable for now unless we later decide to enforce unique controls per treatment.

Most importantly:

```text
Treatment-control leakage: none
```

This means no treatment repository appears in the final clone list as a control repository.

## 10. Final Clone List Created

The final clone list is:

```text
tmp_adoption_test/data/control_repos_to_clone_v2.txt
```

It contains 38 unique matched control repositories.

This is the list we should clone.

We should not clone all repositories from the large control candidate CSV files.

## 11. Existing Clone Script Reviewed

We reviewed:

```text
proc_scripts/clone_repos_v2.py
```

This script already supports:

```text
--repos-file
--repo-column
--clone-root
--logs-dir
--log-prefix
--timestamp
--max-repos
--existing-action
```

The original script expects a CSV input with a repo column. Since our final clone list is currently a TXT file, we decided to slightly modify `clone_repos_v2.py` so it can also accept a TXT file with one repository per line.

The desired behavior is:

```text
Input:
tmp_adoption_test/data/control_repos_to_clone_v2.txt

Automatic normalized output:
tmp_adoption_test/data/control_repos_to_clone_v2.csv

Then clone proceeds from the same repo list.
```

The modification makes `clone_repos_v2.py` more reusable and avoids needing a separate conversion step each time.

## 12. Current Recommended Next Step

The next step is to patch `proc_scripts/clone_repos_v2.py` so it accepts both CSV and TXT inputs.

After patching, run:

```bash
RUN_TS="$(date +%Y%m%d-%H%M)"
OUTPUT_FILE="tmp_adoption_test/data/control_repos_to_clone_v2.txt"
CLONE_ROOT="/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset"
LOG_DIR="logs"
MAX_CLONES=0

python proc_scripts/clone_repos_v2.py \
  --repos-file "${OUTPUT_FILE}" \
  --repo-column repo_name \
  --clone-root "${CLONE_ROOT}" \
  --logs-dir "${LOG_DIR}" \
  --log-prefix run5b_control_clone_log \
  --timestamp "${RUN_TS}" \
  --max-repos "${MAX_CLONES}" \
  --existing-action skip
```

Expected result:

```text
38 repositories processed
already cloned / cloned / failed statuses logged
timestamped clone log saved under logs/
```

## 13. After Cloning

After cloning the 38 matched control repositories, we should verify:

```bash
wc -l tmp_adoption_test/data/control_repos_to_clone_v2.txt

find /home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset \
  -mindepth 2 -maxdepth 2 -name .git | wc -l
```

Then inspect the latest clone log:

```bash
LATEST_LOG="$(ls -t logs/run5b_control_clone_log_*.csv | head -1)"

python - <<PY
import pandas as pd

log = pd.read_csv("${LATEST_LOG}")
print(log["status"].value_counts().to_string())

failed = log[log["status"] == "failed"]
if not failed.empty:
    print(failed.to_string(index=False))
PY
```

If clone succeeds, the next major stage will be to run the same repository-level metric and SonarQube pipeline on the matched control repositories.

## 14. Current Status Summary

Completed:

```text
GCP / BigQuery authentication and dry-run workflow
Treatment-side GHArchive fetch smoke test
Control-side monthly query risk diagnosis
Control-side daily schema smoke test
Existing control candidate file validation
Treatment repo event coverage validation
PSM wrapper creation
PSM debug run
Language-matched PSM final run
Control group QC
Final clone list generation
Review of clone_repos_v2.py
```

Ready next:

```text
Patch clone_repos_v2.py to accept TXT clone lists
Clone 38 matched control repositories
Verify clone log
Proceed to control-repo metric extraction and SonarQube analysis
```

Main decision made:

```text
Use existing control candidate CSV files.
Do not rerun expensive BigQuery control discovery.
Clone only PSM-selected matched controls.
```
