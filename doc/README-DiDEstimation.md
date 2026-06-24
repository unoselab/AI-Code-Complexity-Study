# Progress Report: AI Code Complexity Study — Current Status and Next Plan

## 1. Project Goal

This project extends and partially reproduces the Cursor/AI-code-assistant study on whether AI coding-tool adoption increases short-term development velocity while potentially increasing longer-term software quality and complexity costs.

The current goal is not yet to produce final causal results. The current goal is to rebuild a smaller but methodologically aligned pipeline that can:

1. identify AI/Cursor-adopting repositories,
2. construct a matched treatment-control event panel,
3. validate the DiD estimation pipeline,
4. rerun SonarQube static analysis on selected repository-month snapshots,
5. merge quality metrics into the balanced event panel,
6. then estimate velocity and quality effects.

## 2. Current Working Environment

The active project repository is:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

The active conda environment is:

```text
aicomplexity
```

The current analysis uses new working directories and scripts rather than modifying the original replication notebooks directly.

We are following the project convention:

```text
scripts/
  Original or baseline replication package scripts

proc_scripts/
  Python processing and pipeline scripts

proc_r/
  R and Rmd analysis scripts derived from the original notebooks
```

## 3. Treatment Repository Set

We created a Python-focused treatment sample of 13 AI/Cursor-adopting repositories.

The treatment metadata file is:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

The treatment repositories are:

```text
airweave-ai/airweave
sirkirby/unifi-network-rules
VRSEN/agency-swarm
TextGeneratorio/text-generator.io
wdm0006/pygeohash
wdm0006/elote
KroMiose/nekro-agent
ttmouse/Wispr-Flow-CN
ToolUse/tool-use-ai
kenshiro-o/nagato-ai
Kiln-AI/Kiln
OpenMOSS/Language-Model-SAEs
wdm0006/git-pandas
```

We validated that the metadata adoption months match local Git-history AI/Cursor adoption detection for these repositories.

Result:

```text
13 / 13 treatment repositories matched
0 mismatches
0 missing adoption dates
```

This means the treatment `event_month` values are suitable for event-panel construction.

## 4. Control Matching

We reused existing GHArchive-style repository event features and control candidate files to build a matched control set.

The matching output files are:

```text
tmp_adoption_test/data/matched_controls_v2_pairs.csv
tmp_adoption_test/data/matched_controls_v2_treatment_only.csv
```

The matching result is:

```text
13 treatment repositories
3 matched controls per treatment repository
39 treatment-control pairs
38 unique control repositories
```

One control repository was matched to two treatment repositories, so the unique control count is 38 rather than 39.

No treatment-control leakage was found.

## 5. Repository Cloning and Git-History Analysis

Treatment repositories were analyzed from:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study_repo_dataset
```

Control repositories were cloned into:

```text
/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset
```

Control clone status:

```text
38 / 38 unique control repositories cloned
```

The control Git-history analysis was run using:

```text
proc_scripts/analyze_repos_v2.py
```

The control monthly time-series output is:

```text
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
```

Result:

```text
38 control repositories analyzed
0 control repositories showed Cursor adoption evidence
```

This confirms that the matched controls are still suitable as never-treated controls for the current small panel.

## 6. Balanced Event Panel Construction

We created a matched treatment-control event panel using:

```text
proc_scripts/prepare_panel_event_v2.py
```

The main balanced output is:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The unbalanced comparison output is:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv
```

The balanced panel is the current main activity panel.

Key balanced panel checks:

```text
rows = 738
treated repositories = 13
control repositories = 38
treated post-event rows = 98
control post-event rows = 0
control dynamic rows = 0
zero-activity treated post rows = 23
post-event mismatch rows = 0
```

Interpretation:

```text
The balanced panel preserves zero-commit months.
The 38 matched controls are retained.
Controls remain never-treated.
Treatment post-event status is absorbing.
The event-time structure is internally consistent.
```

This is the correct input for main activity-based DiD smoke testing.

## 7. Important Panel Warnings

Two treatment repositories have weak or empty pre-adoption activity windows:

```text
wdm0006/elote
wdm0006/git-pandas
```

This is not a code error. It is a data-quality warning.

Implication:

```text
Small-N pre-trend diagnostics may be unstable.
Cohort-level estimates should not be interpreted as final causal findings.
```

## 8. Borusyak Helper Refactoring

Instead of writing a completely new R program, we reused logic from the original notebook:

```text
notebooks/DiffInDiffBorusyak.Rmd
```

We created the helper file:

```text
proc_r/diff_in_diff_borusyak_helpers.R
```

This helper refactors and reuses the core Borusyak logic:

```text
run_borusyak_static()
  Derived from the original static did_imputation logic.
  Corresponds to the average ATT structure.

run_borusyak_dynamic()
  Derived from the original dynamic event-study did_imputation logic.
  Corresponds to horizon-specific ATT_h and pre-trend/placebo estimates.

extract_static_result()
  Reuses the original logic of extracting the term == "treat" coefficient.

extract_dynamic_result()
  Reuses the original event-study data construction logic.
```

The helper intentionally does not reuse full-paper-only logic such as:

```text
repo_metrics loading
matching-data subgroup logic
language subgroup analysis
quality outcomes
age / ncloc / stars / issues covariates
publication plotting sections
```

Reason:

```text
The current v2 panel is activity-only and does not yet contain SonarQube quality metrics.
```

## 9. Borusyak v2 Rmd

We created:

```text
proc_r/DiffInDiffBorusyak_v2.Rmd
```

This Rmd uses:

```text
proc_r/diff_in_diff_borusyak_helpers.R
```

and reads:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The v2 Rmd uses only the currently available activity outcomes:

```text
commits
lines_added
```

The available covariate is:

```text
contributors
```

The first-stage formula is:

```r
~ contributors | repo_name + time
```

This is a reduced version of the original full-paper formula:

```r
~ age + ncloc + contributors + stars + issues | repo_name + time
```

The full-paper covariates are not used yet because the current balanced activity panel does not contain them.

## 10. Borusyak Smoke Test Execution

The run script is:

```text
run5d-did-borusyak.sh
```

We decided to keep this file name.

The script renders:

```text
proc_r/DiffInDiffBorusyak_v2.Rmd
```

and writes output to:

```text
tmp_adoption_test/data/python_did_test/activity_did_smoke_borusyak_v2
```

The render completed successfully.

Generated main output:

```text
DiffInDiffBorusyak_v2.html
borusyak_v2_panel_checks.csv
borusyak_v2_static_effects.csv
borusyak_v2_dynamic_effects.csv
borusyak_v2_metadata.csv
dynamic_effects_borusyak_v2_activity_smoke.pdf
```

The panel check output was:

```text
rows = 738
treated_repos = 13
control_repos = 38
control_post_event_sum = 0
control_dynamic_sum = 0
treated_post_rows = 98
zero_activity_treated_post_rows = 23
post_event_mismatch_rows = 0
```

This confirms that the Borusyak pipeline can read the new balanced event panel and estimate static and dynamic activity models.

## 11. Interpretation of the Borusyak Smoke Test

The Borusyak smoke test is successful as a structural pipeline test.

It confirms:

```text
The balanced panel is readable by R.
The helper functions load correctly.
The Borusyak imputation estimator runs.
Static treatment effects are produced.
Dynamic event-study ATT_h results are produced.
The event-study plot is generated.
```

However, the resulting estimates should not be interpreted as final causal findings.

Reason:

```text
The sample is small.
There are only 13 treated repositories.
Some treatment cohorts contain very few repositories.
Some pre-adoption estimates are significant.
The current panel contains only activity outcomes, not quality outcomes.
```

Therefore, the current Borusyak output is a pipeline validation result, not a final research result.

## 12. SonarQube Work Completed So Far

We have not yet run the full SonarQube analysis for the current 13-treatment / 38-control balanced panel.

What we completed before was SonarQube setup and learning-oriented smoke testing.

Completed SonarQube setup:

```text
Local SonarQube Community Build server running in Docker
SonarQube UI reachable at http://localhost:9000 on the remote server
SONAR_TOKEN generated and saved in .env
SONAR_HOST configured
SONAR_SCANNER_PATH configured
SonarScanner CLI installed and executable
```

The scanner path is:

```text
/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

The local `.env` contains:

```text
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=<local token>
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

We also tested:

```text
SonarQube server status API
SonarQube token validation
SonarScanner --version
tiny local Python project scan
small-batch pipeline behavior
```

## 13. Tiny SonarQube Smoke Test

A tiny local project was created at:

```text
tmp_sonar_smoke/tiny_project
```

It contained:

```text
sonar-project.properties
src/app.py
```

The tiny project scan verified:

```text
SonarScanner can read a local project.
SonarScanner can analyze a Python file.
SonarScanner can upload analysis to local SonarQube.
SonarQube can create the dashboard.
```

This was an infrastructure validation test only.

It was not a research analysis.

## 14. Small-Batch SonarQube Learning Test

A later small-batch smoke test was also performed to understand the reusable SonarQube pipeline.

The test used:

```text
proc_scripts/create_tmp_repo_timeseries_input.py
proc_scripts/run_sonarqube_v2.py
```

It tested three repositories:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

The test confirmed that the pipeline can collect metrics such as:

```text
ncloc
bugs
vulnerabilities
code_smells
static_analysis_warnings
duplicated_lines_density
comment_lines_density
cognitive_complexity
technical_debt
```

However, this test used current repository HEAD commits and temporary months. It was not equivalent to the original paper pipeline, which analyzes historical repository-month snapshots.

Therefore, this small-batch test should be treated as a learning and infrastructure validation step.

## 15. What Has Not Yet Been Done

We have not yet run full SonarQube scanning for the current balanced panel.

Specifically, we have not yet scanned:

```text
13 treatment repositories
38 matched control repositories
all relevant repo-month snapshots
historical commits corresponding to each month
```

We also have not yet created the final quality-augmented panel:

```text
panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
```

Therefore, the next step is not “merge existing SonarQube results.” The next step is to run a controlled SonarQube analysis that produces those results.

## 16. Correct Next Step

The correct next step is:

```text
Run SonarQube static-analysis collection for the current balanced panel.
```

But this should be done carefully in stages.

We should not jump immediately to full 738-row scanning.

The next phase should be:

```text
Step 1: Reconfirm SonarQube infrastructure
Step 2: Prepare repo-month scan input from the balanced panel
Step 3: Run a controlled multi-month SonarQube smoke test
Step 4: Validate metric retrieval
Step 5: Scale to the 13-treatment / 38-control panel
Step 6: Merge SonarQube metrics into the balanced panel
Step 7: Rerun Borusyak with quality outcomes
```

## 17. Detailed Plan for the Next Step

### Step 1. Reconfirm SonarQube status

Before scanning repositories, reconfirm:

```text
Docker container is running.
SonarQube status API returns UP.
Token validation succeeds.
Scanner executable still works.
```

Suggested checks:

```bash
docker ps -a | grep -i sonar

python proc_scripts/test_sonarqube_connection.py

python - <<'PY'
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

scanner_path = os.getenv("SONAR_SCANNER_PATH")
print("SONAR_SCANNER_PATH:", scanner_path)

path = Path(scanner_path)
print("Exists:", path.exists())
print("Executable:", os.access(path, os.X_OK))

result = subprocess.run(
    [scanner_path, "--version"],
    text=True,
    capture_output=True,
)

print("Return code:", result.returncode)
print(result.stdout)
print(result.stderr)

if result.returncode != 0:
    raise SystemExit("scanner version check failed")
PY
```

### Step 2. Confirm required source information for repo-month scanning

The balanced event panel contains the repo-month structure. However, SonarQube scanning needs the commit to checkout for each repository-month.

We need to confirm whether the balanced panel contains:

```text
latest_commit
```

If it does, we can use it directly.

If it does not, we need to join the balanced event panel with the original treatment/control monthly time-series files:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
```

The required scan input should contain at least:

```text
repo_name
month or time
latest_commit
dataset_source
```

### Step 3. Build a SonarQube scan input file

Create a scan input file such as:

```text
tmp_adoption_test/data/python_did_test/sonarqube_scan_input_balanced_v2.csv
```

It should contain one row per repository-month that we want to scan.

Important distinction:

```text
The balanced panel may contain zero-commit months.
A zero-commit month may have no new latest_commit for that month.
For SonarQube scanning, we may need to carry forward the most recent commit available at that month or use the latest_commit from the original monthly time series.
```

This decision should be documented clearly before full scanning.

### Step 4. Run a multi-month SonarQube smoke test first

Before full scanning, use a very small subset.

Recommended initial subset:

```text
1 treatment repository
1 control repository
2 or 3 months each
```

The subset should include:

```text
at least one pre-adoption month
the adoption month if treatment
at least one post-adoption month
```

This will test whether:

```text
repository checkout works
historical commit checkout works
scanner works after checkout
SonarQube project versioning works
metric retrieval works
CSV writing works
```

This is closer to the original paper pipeline than the earlier HEAD-only smoke test.

### Step 5. Collect SonarQube metrics

The key metrics to collect are:

```text
ncloc
bugs
vulnerabilities
code_smells
duplicated_lines_density
cognitive_complexity
sqale_index
comment_lines_density
```

Then compute:

```text
static_analysis_warnings = bugs + vulnerabilities + code_smells
```

This is the first quality outcome needed for the paper-aligned analysis.

### Step 6. Distinguish zero warnings from missing scans

When merging SonarQube metrics into the balanced panel, we must not confuse:

```text
successful scan with zero warnings
```

with:

```text
missing scan or failed scan
```

Therefore, the merged panel should include a flag:

```text
has_sonarqube_scan
```

Suggested meaning:

```text
has_sonarqube_scan = 1
  SonarQube scan result exists for this repo-month.

has_sonarqube_scan = 0
  No scan result exists for this repo-month.
```

For successful scans, missing metric values can be converted to zero when appropriate.

For failed or missing scans, metric values should remain NA until the failure is resolved or explicitly excluded.

### Step 7. Merge metrics into the balanced panel

The output should be:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv
```

Merge keys:

```text
repo_name
time
```

Expected added columns:

```text
has_sonarqube_scan
ncloc
bugs
vulnerabilities
code_smells
static_analysis_warnings
duplicated_lines_density
cognitive_complexity
technical_debt
comment_lines_density
```

### Step 8. Rerun Borusyak v2 with quality outcomes

After SonarQube metrics are merged, update or extend:

```text
proc_r/DiffInDiffBorusyak_v2.Rmd
```

or create:

```text
proc_r/DiffInDiffBorusyak_quality_v2.Rmd
```

Quality outcomes:

```text
static_analysis_warnings
duplicated_lines_density
cognitive_complexity
```

This will move the current analysis from activity-only smoke testing toward the paper’s combined velocity-quality analysis.

## 18. Immediate Next Command Recommendation

The next immediate action should be to reconfirm SonarQube infrastructure:

```bash
docker ps -a | grep -i sonar

python proc_scripts/test_sonarqube_connection.py
```

Then confirm whether the balanced panel has `latest_commit`:

```bash
python - <<'PY'
import pandas as pd

panel = "tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv"
df = pd.read_csv(panel)

print("columns:")
print("\n".join(df.columns))

print()
print("has latest_commit:", "latest_commit" in df.columns)
print("rows:", len(df))
print("repos:", df["repo_name"].nunique())
PY
```

If `latest_commit` is missing, check the original time-series files:

```bash
python - <<'PY'
import pandas as pd

paths = [
    "tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv",
    "tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv",
]

for path in paths:
    df = pd.read_csv(path, nrows=5)
    print("\n", path)
    print(df.columns.tolist())
PY
```

This will determine how to build the SonarQube scan input.

## 19. Current Status Summary

Completed:

```text
13 treatment repositories selected and validated.
38 matched controls selected and cloned.
Treatment/control monthly Git-history time series generated.
Balanced event panel created.
Borusyak helper functions refactored.
Borusyak v2 Rmd created.
run5d-did-borusyak.sh successfully rendered Borusyak v2 Rmd.
Activity-only Borusyak smoke test completed.
SonarQube infrastructure was previously installed and tested.
Tiny SonarQube scan and small-batch learning tests were completed.
```

Not yet completed:

```text
Full SonarQube scan for the current balanced panel.
Historical multi-month SonarQube scan for 13 treatment + 38 controls.
Merge of SonarQube metrics into the balanced panel.
Quality-outcome Borusyak DiD.
TWFE / Callaway robustness analysis.
```

Next:

```text
Reconfirm SonarQube setup.
Build repo-month scan input from the balanced panel and monthly time-series files.
Run a small historical multi-month SonarQube smoke test.
Scale to the current 13-treatment / 38-control panel.
Merge metrics into the balanced panel.
Run Borusyak quality-outcome analysis.
```
