# Task Report: AI Code Complexity Study Setup and Phase 2 Preparation

## 1. Project Context

We are working on the `AI-Code-Complexity-Study`, which is based on the original Cursor adoption replication package. The broader research goal is to understand whether AI coding-tool adoption increases short-term development speed while also increasing longer-term code complexity, static analysis warnings, or maintainability costs.

We already completed the Phase 1 reproduction using the original prepared data and R notebooks. After that, we began preparing for Phase 2, where we may rerun or partially rerun parts of the original data pipeline using live GitHub history, local cloned repositories, and local SonarQube static analysis.

The main focus of the recent work was:

```text
1. Prepare the new project repository.
2. Confirm GitHub API access.
3. Set up local self-hosted SonarQube.
4. Verify SonarScanner works end to end.
5. Understand event-panel construction.
6. Select candidate repositories for cloning and Git-history validation.
```

---

## 2. Repository Preparation

We created a new working project directory:

```text
~/project-workspace/ai_code_complexity_study
```

This directory was copied from the original `cursor_study` project.

We verified the copy using:

```bash
diff -qr --exclude='.git' cursor_study ai_code_complexity_study
```

The command produced no output, meaning the copied files matched except for `.git`.

Then `.git` was restored from an existing prepared copy:

```bash
cp -r ai_code_complexity_study_org01/.git ai_code_complexity_study/
```

Inside the new project directory, we confirmed the Git remote:

```bash
git remote -v
```

The remote points to:

```text
git@github.com:unoselab/AI-Code-Complexity-Study.git
```

This means we are now working in the new independent GitHub repository rather than the original `CursorStudy` repository.

---

## 3. GitHub Token Setup

We confirmed that the GitHub token is required for GitHub API operations, especially code search and repository metadata retrieval.

A `.env` file was created or updated in the project root:

```text
.env
```

The GitHub token was stored as:

```text
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

We initially encountered a `python-dotenv` issue when using:

```python
load_dotenv()
```

inside a `python - <<'PY'` heredoc. The error was:

```text
AssertionError inside dotenv.find_dotenv()
```

We fixed this by explicitly passing the `.env` path:

```python
load_dotenv(dotenv_path=".env")
```

After the fix, the token check succeeded:

```text
GITHUB_TOKEN is set: True
Token prefix: ghp_
```

We then tested GitHub API access using a small script:

```text
proc_scripts/test_github_query.py
```

The test confirmed:

```text
Core API limit: 5000 / 5000
Search API limit: 30 / 30
Query: filename:.cursorrules
Total count: 1000
```

This confirmed that authenticated GitHub API and GitHub code search are working.

Important note:

```text
GitHub code search results are capped around 1000 results per query.
This is why the original pipeline uses partitioning/adaptive search logic.
```

---

## 4. SonarQube Strategy

We decided to use:

```text
Self-hosted SonarQube Community Build
```

instead of SonarQube Cloud or a paid trial.

The reason is that local self-hosted SonarQube is free and more appropriate for research pipeline testing. It also avoids SonarQube Cloud trial/billing issues.

The selected approach is:

```text
Local Ubuntu server
→ Docker-based SonarQube Community Build
→ local SonarScanner CLI
→ local project scans
→ SonarQube Web API metric retrieval
```

---

## 5. SonarQube Server Setup

We confirmed that SonarQube is running through Docker.

The command:

```bash
docker ps -a | grep -i sonar
```

showed a running container:

```text
sonarqube:latest
container name: sonarqube
port mapping: 0.0.0.0:9000->9000/tcp
status: Up
```

This means the SonarQube server is available on the remote Ubuntu server at:

```text
http://localhost:9000
```

Because SonarQube is running on the remote server, browser access from a local laptop requires SSH port forwarding or VS Code port forwarding.

The browser access flow is:

```text
Local browser localhost:9000
→ SSH tunnel or VS Code port forwarding
→ remote Ubuntu server localhost:9000
→ SonarQube Docker container port 9000
```

For SSH tunneling, the pattern is:

```bash
ssh -L 9000:localhost:9000 user1-system12@<server-address>
```

Then the browser can open:

```text
http://localhost:9000
```

If local port `9000` is already occupied, we can use a different local port:

```bash
ssh -L 9001:localhost:9000 user1-system12@<server-address>
```

Then open:

```text
http://localhost:9001
```

For Python scripts running directly on the remote Ubuntu server, no SSH tunnel is needed. Those scripts can use:

```text
SONAR_HOST=http://localhost:9000
```

because the script and SonarQube server are on the same remote machine.

---

## 6. SonarQube Login and Token Generation

We opened the SonarQube UI in the browser.

The default login was:

```text
Username: admin
Password: admin
```

After first login, SonarQube required a password change.

We created a local project rather than importing from GitHub.

Selected option:

```text
Create a local project
```

This is the correct choice because our intended Phase 2 workflow is:

```text
clone repository locally
→ checkout target commit
→ run sonar-scanner locally
→ upload analysis result to local SonarQube
→ query SonarQube API for metrics and warnings
```

A SonarQube analysis token was generated from the UI and saved in `.env` as:

```text
SONAR_TOKEN=your_generated_sonarqube_token_here
```

The `.env` file now contains SonarQube-related variables:

```text
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=your_generated_sonarqube_token_here
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

We also made sure `.env` is ignored by Git:

```bash
grep -n '^.env$' .gitignore || echo ".env" >> .gitignore
```

---

## 7. SonarQube Connection Test

We created or used a small connection test script:

```text
proc_scripts/test_sonarqube_connection.py
```

The script checks:

```text
SONAR_HOST is set
SONAR_TOKEN is set
SONAR_SCANNER_PATH is set
SonarQube system status API is reachable
SonarQube token is valid
```

The connection test output showed:

```text
SONAR_HOST is set: True
SONAR_TOKEN is set: True
SONAR_SCANNER_PATH is set: True
System status HTTP: 200
System status response: {"id":"...","version":"26.6.0.123539","status":"UP"}
Authentication validate HTTP: 200
Authentication validate response: {"valid":true}
```

This confirms:

```text
Local SonarQube server is running.
The API endpoint is reachable.
The token is valid.
Python scripts can authenticate to SonarQube.
```

---

## 8. SonarScanner CLI Setup

We installed SonarScanner CLI under:

```text
/home/user1-system12/tools/sonar-scanner
```

The executable path is:

```text
/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

This path was saved in `.env` as:

```text
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

We tested the scanner executable with a Python wrapper that checked:

```text
Path exists
Path is file
Path is executable
sonar-scanner --version returns code 0
```

The test succeeded:

```text
SONAR_SCANNER_PATH: /home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
Exists: True
Is file: True
Executable: True
Return code: 0
SonarScanner CLI 8.0.1.6346
Linux 6.8.0-94-generic amd64
```

This confirms the local scanner is installed and executable.

---

## 9. Tiny SonarQube Smoke Test Project

Before running any real repository analysis, we created a tiny test project:

```text
tmp_sonar_smoke/tiny_project
```

Its structure is:

```text
tmp_sonar_smoke/
└── tiny_project
    ├── sonar-project.properties
    └── src
        └── app.py
```

The `sonar-project.properties` file contains:

```text
sonar.projectKey=cursorstudy-tiny-test
sonar.projectName=CursorStudy Tiny Test
sonar.projectVersion=1.0

sonar.sources=src
sonar.sourceEncoding=UTF-8
```

The purpose of this tiny project was not to generate meaningful research metrics. Its purpose was to verify the complete infrastructure path:

```text
local source files
→ SonarScanner CLI
→ local SonarQube server
→ analysis report upload
→ SonarQube dashboard creation
```

---

## 10. Tiny SonarQube Scan

We created and ran:

```text
run2c-sonarqube-tiny-scan.sh
```

The scan was executed as:

```bash
./run2c-sonarqube-tiny-scan.sh > ylog.txt
```

The scan completed successfully.

Important success signals:

```text
Return code: 0
Communicating with SonarQube Community Build 26.6.0.123539
Project key: cursorstudy-tiny-test
1 language detected in 1 preprocessed file
1 file indexed
Quality profile for py: Sonar way
Analysis report uploaded
ANALYSIS SUCCESSFUL
EXECUTION SUCCESS
Tiny SonarQube scan completed.
```

The generated dashboard URL was:

```text
http://localhost:9000/dashboard?id=cursorstudy-tiny-test
```

This confirmed that the scanner can analyze a local source tree and upload results to the local SonarQube server.

Warnings observed during the tiny scan were acceptable:

```text
Python version not specified
Missing blame information for src/app.py
```

These are not blockers. The Python version warning can be addressed later by setting:

```text
sonar.python.version=3.11
```

The missing blame warning appeared because the tiny smoke-test project was not a normal committed Git repository.

---

## 11. SonarQube Authentication Style

We compared two SonarQube API authentication styles.

The original scripts tend to use Bearer authentication:

```python
headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}
requests.get(url, headers=headers, params=params)
```

Our local working setup used token-as-basic-auth:

```python
requests.get(url, auth=(SONAR_TOKEN, ""), params=params)
```

Both can be legitimate SonarQube API styles, but our local Docker setup was already tested successfully with:

```python
auth=(SONAR_TOKEN, "")
```

So for our new local scripts, we plan to prefer token-as-basic-auth for SonarQube API reads.

For scanner upload, we should keep using:

```text
-Dsonar.token=${SONAR_TOKEN}
```

because that is how SonarScanner receives the authentication token.

Recommended local convention:

```text
SonarScanner upload:
-Dsonar.token=<token>

SonarQube API reads:
requests.get(..., auth=(SONAR_TOKEN, ""))
```

---

## 12. Event Panel Understanding

We discussed the meaning of an event panel.

An event panel is:

```text
repo-month time-series data
+ AI/Cursor adoption month
= event-study / DiD-ready panel dataset
```

Each row is one repository-month observation. The event is the adoption of Cursor or an AI coding-tool signal.

Example:

```text
repo_name           month     event     treated   relative_month
utensils/mcp-nixos  2025-02   2025-03   1         -1
utensils/mcp-nixos  2025-03   2025-03   1          0
utensils/mcp-nixos  2025-04   2025-03   1          1
```

Interpretation:

```text
relative_month = -1 → one month before adoption
relative_month = 0  → adoption month
relative_month = 1  → one month after adoption
```

The event panel allows repos that adopted at different calendar months to be aligned relative to their own adoption event.

The key idea:

```text
calendar time differs across repos,
but event time aligns repos around adoption.
```

This is necessary for event-study and difference-in-differences analysis.

---

## 13. Git-History AI Adoption Detection

We previously tested Git-history-based adoption detection on three repositories:

```text
TheSethRose/Agent-Chat
nextml-code/pytorch-datastream
utensils/mcp-nixos
```

The detection logic found `.cursorrules` or other AI-tool files in Git history.

However, those three were not ideal event-panel smoke-test candidates:

```text
TheSethRose/Agent-Chat:
insufficient pre-adoption months

nextml-code/pytorch-datastream:
insufficient post-adoption months

utensils/mcp-nixos:
insufficient pre-adoption months
```

Therefore, we needed a better way to select candidate repositories before cloning and validating Git history.

---

## 14. Need for Cloning Repositories

We attempted to run Git-history adoption detection across 867 repos from:

```text
data/ts_repos_monthly.csv
```

But nearly all repos were skipped because they were not cloned under:

```text
../CursorRepos
```

The log showed many messages like:

```text
skipped: missing cloned Git repository: ../CursorRepos/OWNER_REPO
```

Conclusion:

```text
The monthly CSV gives repo names and panel structure.
But actual Git history inspection requires cloned repositories.
```

Therefore, before running Git-history validation across many repos, we need to clone a selected candidate subset.

Instead of cloning all 867 repos immediately, we decided to use existing baseline data to select the best 100 candidates first.

---

## 15. Baseline Data Inspection

We inspected:

```text
data_baseline_backup/
```

Important files include:

```text
panel_event_monthly.csv
ts_repos_monthly.csv
cursor_commits.csv
cursor_files.csv
repo_metrics.csv
repos.csv
sonarqube_warnings.csv
```

The most important file for candidate selection is:

```text
data_baseline_backup/panel_event_monthly.csv
```

It contains:

```text
repo_name
time
event
post_event
time_to_event
cursor
dataset_source
other_agents
high_confidence
quality and velocity metrics
```

This file already tells us whether each repo has observed months before and after the adoption event.

The important interpretation is:

```text
time_to_event < 0   → pre-adoption month
time_to_event == 0  → adoption month
time_to_event > 0   → post-adoption month
```

We also inspected:

```text
data_baseline_backup/ts_repos_monthly.csv
```

This file contains:

```text
month
repo_name
latest_commit
cursor
commits
lines_added
lines_removed
contributors
SonarQube metrics
dependency metrics
```

This will be useful later for connecting monthly rows to actual commits.

---

## 16. Candidate Selection Script: Version 1 vs Version 2

We compared two versions of the candidate-selection script:

```text
proc_scripts/find_repo_pre_post_ai_adoption.py
proc_scripts/find_repo_pre_post_ai_adoption_v2.py
```

The goal of the script is to select 100 repositories that:

```text
have observed pre-adoption months,
have observed post-adoption months,
have Cursor or AI evidence,
are good candidates for cloning and Git-history validation.
```

Version 1 produced 501 eligible repos and selected 100 candidates.

However, Version 1 had a flaw: it counted rows rather than distinct repo-months. If a repo had duplicated `(repo_name, time)` rows, its pre/post window could be inflated.

This was visible because some top candidates had:

```text
event_months = 2
```

For a clean single-adoption event panel, `event_months` should normally be 1. A value of 2 is a duplication signature.

Version 2 fixed this by collapsing duplicated `(repo_name, time)` rows before counting pre/post months.

The Version 2 log showed:

```text
Duplicated (repo, month) rows collapsed: 51
```

Therefore, Version 2 is better and should be used as the canonical script.

---

## 17. Why Version 2 Is Better

Version 2 improves the candidate-selection logic in several ways:

```text
1. Counts distinct repo-months instead of raw rows.
2. Drops duplicated (repo_name, time) rows before calculating windows.
3. Adds a rank column.
4. Adds repository metadata such as stars, primary language, and repo size.
5. Adds --require-cursor-evidence.
6. Adds a window_touches_data_edge diagnostic.
7. Cleans bad month values such as nan, nat, none, and empty strings.
```

This matters because Version 1 promoted some repos to the top only because duplicated rows inflated their pre/post counts.

Version 2 produced stronger and more defensible top candidates, including:

```text
VRSEN/agency-swarm
helixml/helix
different-ai/note-companion
metriport/metriport
reliverse/cli-ai-app-site-anything-builder
YumNumm/EQMonitor
dcramer/peated
maidsafe/autonomi
owid/owid-grapher
ProcessMaker/processmaker
```

For example, `VRSEN/agency-swarm` is a strong candidate because it has:

```text
pre_panel_months = 9
post_panel_months = 10
cursor_commit_rows = 42
repo_stars = 3605
primary language = Python
```

This makes it a good target for Git-history validation.

---

## 18. Remaining Caveat About Candidate Selection

Version 2 reported:

```text
touching data edge: 96/100
```

This means many selected repos touch either the beginning or end of the observed panel data window.

This is not necessarily a problem. It means the true Git history may contain more pre/post months than the baseline panel shows.

But it also means the selected top 100 should be interpreted as:

```text
repos with sufficient observed pre/post panel months
and strong Cursor evidence
```

not necessarily:

```text
repos with the deepest possible historical windows
```

This is acceptable for the current goal, because our goal is not final causal estimation yet. Our current goal is to select good repositories to clone and validate against Git history.

---

## 19. Current Recommendation

We decided to use Version 2 as the canonical script.

Recommended action:

```bash
cp proc_scripts/find_repo_pre_post_ai_adoption_v2.py \
   proc_scripts/find_repo_pre_post_ai_adoption.py
```

Then run:

```bash
python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir data_baseline_backup \
  --top-n 100 \
  --min-pre-months 1 \
  --min-post-months 1 \
  --require-cursor-evidence \
  --output tmp_adoption_test/data/top_100_clone_candidates.csv
```

The `--require-cursor-evidence` flag is recommended because the next step is cloning repositories specifically for Cursor adoption validation. We therefore want repos that already have evidence in `cursor_commits.csv` or `cursor_files.csv`.

---

## 20. Current Status

Completed:

```text
New project repo prepared.
GitHub token configured and tested.
GitHub API search tested.
Local SonarQube server running in Docker.
SonarQube token generated and validated.
SonarScanner CLI installed and tested.
Tiny SonarQube project created.
Tiny SonarQube scan completed successfully.
Event panel concept clarified.
Baseline data inspected.
Candidate-selection Version 1 vs Version 2 compared.
Version 2 selected as the better/canonical approach.
```

Plan:

```text
Clone top 100 candidate repositories.
Run Git-history validation on cloned candidate repositories.
Select final 3 clean pre/post repos for smoke-test event panel.
Build small event panel from selected repos.
Find control repos for those 3 repos.
```

---

## 21. Suggested Next Steps After Break

When resuming, the recommended next steps are:

```text
1. Replace the candidate-selection script with Version 2.
2. Run Version 2 with --require-cursor-evidence.
3. Confirm top_100_clone_candidates.csv has 100 repos plus header.
4. Create a clone script for those 100 repos.
5. Clone into ../CursorRepos using OWNER_REPO directory names.
6. Rerun Git-history adoption validation on the cloned candidate set.
7. Select 3 repos with clean pre/post adoption windows.
8. Then return to SonarQube API metric retrieval and real-repo scan smoke tests.
```

The immediate next command should be:

```bash
cp proc_scripts/find_repo_pre_post_ai_adoption_v2.py \
   proc_scripts/find_repo_pre_post_ai_adoption.py

python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir data_baseline_backup \
  --top-n 100 \
  --min-pre-months 1 \
  --min-post-months 1 \
  --require-cursor-evidence \
  --output tmp_adoption_test/data/top_100_clone_candidates.csv
```

Then check:

```bash
wc -l tmp_adoption_test/data/top_100_clone_candidates.csv
head -20 tmp_adoption_test/data/top_100_clone_candidates.csv
```

Expected line count:

```text
101
```

because it should contain 1 header row plus 100 selected repositories.

---

## 22. Summary

We have now reached a stable checkpoint.

The infrastructure side is working:

```text
GitHub API works.
SonarQube server works.
SonarQube token works.
SonarScanner works.
Tiny SonarQube scan works.
```

The data-selection side is also clarified:

```text
Use baseline panel_event_monthly.csv to choose clone candidates.
Use Version 2 because it correctly counts distinct repo-months.
Use --require-cursor-evidence for Cursor-focused validation.
Clone only the top 100 candidates first, not all 867 repos.
```

The next phase should focus on cloning the selected candidate repositories and validating AI/Cursor adoption directly from Git history.




---
---
---
---
---
---




## SonarQube Post-Setup Validation and Small-Batch Pipeline Testing

After completing the SonarQube setup, we validated that the local SonarQube server and scanner were functioning correctly and then moved from isolated scanner tests to a reusable small-batch pipeline test.

First, we confirmed that SonarQube was reachable at `http://localhost:9000`, that the authentication token worked, and that the scanner path from `.env` was correctly detected. We also confirmed that the SonarQube Docker container was stable, with memory usage remaining low relative to the available system memory.

Next, we created a reusable helper script:

```text
proc_scripts/create_tmp_repo_timeseries_input.py
```

This script generates a temporary time-series input file for SonarQube testing without relying on the original paper’s `data/ts_repos_monthly.csv`. The script reads the current `HEAD` commit from already cloned repositories and writes a minimal CSV containing:

```text
repo_name, month, latest_commit
```

This temporary file is used by the patched SonarQube runner:

```text
proc_scripts/run_sonarqube_v2.py
```

We then updated the small-batch smoke test so that the workflow became:

```text
1. Clone missing repositories
2. Create temporary time-series input from cloned repository HEAD commits
3. Run the SonarQube pipeline
4. Display resulting metrics
```

During testing, we found that the temporary input used `2026-06` as the test month, while the SonarQube runner was originally hardcoded to process only the original study window, from `2024-01` to `2025-08`. Because of this mismatch, the runner initially skipped the `2026-06` rows and produced missing metric values.

To fix this, we modified `run_sonarqube_v2.py` so that it infers the processing window directly from the input CSV:

```text
START_DATE = min(input month)
END_DATE   = max(input month)
```

This allowed the runner to process arbitrary temporary test months such as `2026-06`.
the dynamic date range patch worked correctly. The runner logged:

```text
Using input-derived date range: 2026-06 to 2026-06
```

We also observed a SonarQube timing issue: immediately after a scan completed, the analysis version was sometimes not yet visible through the SonarQube analysis API. We confirmed that this was due to SonarQube server-side Compute Engine processing, not a scanner failure. After the analysis became available, the same pipeline successfully retrieved metrics.

The final small-batch smoke test succeeded for three repositories:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

The pipeline successfully collected SonarQube metrics including:

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

The final result confirmed that:

```text
1. Repository cloning works.
2. Temporary time-series input generation works.
3. Dynamic input-derived date range handling works.
4. SonarQube scanner execution works.
5. SonarQube metric retrieval works.
6. Metrics are correctly written back to the temporary CSV.
```

We also confirmed an important methodological distinction. The current smoke test analyzes one month per repository using the current repository `HEAD` commit. This is useful for infrastructure validation, but it is not equivalent to the original paper pipeline.

The original paper analyzed multiple months per repository. For each repository-month, the pipeline should use the commit corresponding to that historical month.

Therefore, the next planned step is:

```text
run3a:
  multi-month smoke test with actual multiple-month history
  instead of repeating current HEAD across multiple months
  tests whether run_sonarqube_v2.py handles multiple periods per repo
```

The goal of `run3a` is to move closer to the original paper’s design by testing multiple historical months per repository with actual month-specific commits.




