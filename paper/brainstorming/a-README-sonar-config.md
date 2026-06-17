# SonarQube Local Configuration and Smoke Test Notes

This document records the local SonarQube setup used for the `AI-Code-Complexity-Study` project.

The goal of this setup is to prepare for Phase 2 of the study, where we may rerun static analysis on cloned GitHub repositories and collect SonarQube metrics such as static analysis warnings, duplicated line density, and code complexity.

This setup uses:

```text
SonarQube Community Build
Self-hosted local server
Local SonarScanner CLI
Local project smoke test
```

This is different from using SonarQube Cloud or a paid SonarSource trial.

---

## 1. Why we need SonarQube

The paper studies whether Cursor adoption increases short-term development velocity and whether it also increases longer-term code quality or complexity costs.

In the replication package, SonarQube-related metrics are used for software quality outcomes such as:

```text
static analysis warnings
duplicated lines density
code complexity
technical debt
bugs
vulnerabilities
code smells
```

For Phase 1 reproduction, we used the already prepared data files in `data/`, so we did not need to rerun SonarQube.

For Phase 2 data rebuilding, SonarQube is needed because the pipeline may scan repository snapshots again.

---

## 2. Current SonarQube strategy

We decided to use:

```text
Self-hosted SonarQube Community Build
```

rather than SonarQube Cloud.

Reason:

```text
SonarQube Community Build is free and self-hosted.
It can run locally on the Ubuntu server.
It avoids SonarQube Cloud trial/billing concerns.
It is more appropriate for local research pipeline testing.
```

Important limitation:

```text
The current local setup uses the embedded database.
This is acceptable for smoke testing and small experiments.
It is not recommended for large-scale production-style scanning.
```

For a large Phase 2 rerun, a PostgreSQL-backed SonarQube setup may be safer.

---

## 3. Environment

The work was performed from the repository root:

```bash
cd ~/project-workspace/ai_code_complexity_study
```

The active conda environment was:

```text
aicomplexity
```

Earlier Phase 1 reproduction used:

```text
cursorstudy
```

The SonarQube smoke test used the current project environment and local `.env` configuration.

---

## 4. Required environment variables

The project uses a local `.env` file.

The relevant variables are:

```text
SONAR_HOST
SONAR_TOKEN
SONAR_SCANNER_PATH
```

Example structure:

```text
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=your_generated_sonarqube_token_here
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

The `.env` file should not be committed to Git.

Check that `.env` is ignored:

```bash
grep -n '^.env$' .gitignore || echo ".env" >> .gitignore
```

---

## 5. SonarQube server

The local SonarQube server was started and accessed through:

```text
http://localhost:9000
```

The browser showed the SonarQube login page.

The default login was:

```text
Username: admin
Password: admin
```

After first login, SonarQube asked for a password change.

A local project was created rather than importing from GitHub.

Selected option:

```text
Create a local project
```

Reason:

```text
The Phase 2 workflow will clone repositories locally,
checkout specific commits,
run sonar-scanner locally,
upload the analysis to the local SonarQube server,
and then query SonarQube APIs for metrics.
```

---

## 6. SonarQube token

A SonarQube analysis token was generated in the local SonarQube UI.

The token was added to `.env` as:

```text
SONAR_TOKEN=your_generated_sonarqube_token_here
```

The token was validated successfully using the local SonarQube authentication API.

The connection test confirmed:

```text
SONAR_HOST is set: True
SONAR_TOKEN is set: True
SONAR_SCANNER_PATH is set: True
System status HTTP: 200
Authentication validate HTTP: 200
Authentication validate response: {"valid":true}
```

This means:

```text
The local SonarQube server is reachable.
The token is valid.
The project can authenticate against the local server.
```

---

## 7. SonarScanner CLI installation

The SonarScanner CLI was installed under:

```text
/home/user1-system12/tools/sonar-scanner
```

The scanner executable path is:

```text
/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

This path was saved in `.env`:

```text
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

Scanner executable verification succeeded.

The version check confirmed:

```text
SONAR_SCANNER_PATH: /home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
Exists: True
Is file: True
Executable: True
Return code: 0
SonarScanner CLI 8.0.1.6346
Linux 6.8.0-94-generic amd64
```

This means:

```text
The scanner path points to a real file.
The scanner file is executable.
The scanner binary can run successfully.
```

---

## 8. Connection test script

The connection test script is stored at:

```text
proc_scripts/test_sonarqube_connection.py
```

It checks:

```text
whether SONAR_HOST is set
whether SONAR_TOKEN is set
whether SONAR_SCANNER_PATH is set
whether the SonarQube server status API is reachable
whether the SonarQube token is valid
```

The wrapper script currently used was:

```text
run2a-sonarqube-scanner.sh
```

Current content:

```bash
python proc_scripts/test_sonarqube_connection.py
```

Note:

```text
The script name says scanner, but the current content is a connection test.
A clearer name would be run2a-sonarqube-connection.sh.
```

Optional rename:

```bash
mv run2a-sonarqube-scanner.sh run2a-sonarqube-connection.sh
```

---

## 9. Scanner version test

A scanner version test was run using a temporary script called:

```text
xrun.sh
```

The test loaded `.env`, read `SONAR_SCANNER_PATH`, checked that the executable exists, and ran:

```bash
sonar-scanner --version
```

The test succeeded.

A cleaner permanent script name would be:

```text
run2b-sonarqube-scanner-version.sh
```

Suggested script content:

```bash
#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load project environment variables explicitly
load_dotenv(dotenv_path=".env")

scanner_path = os.getenv("SONAR_SCANNER_PATH")
print("SONAR_SCANNER_PATH:", scanner_path)

if not scanner_path:
    raise SystemExit("Missing SONAR_SCANNER_PATH")

path = Path(scanner_path)
print("Exists:", path.exists())
print("Is file:", path.is_file())
print("Executable:", os.access(path, os.X_OK))

# Check that the scanner binary can run
result = subprocess.run(
    [scanner_path, "--version"],
    text=True,
    capture_output=True,
)

print("Return code:", result.returncode)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)

if result.returncode != 0:
    raise SystemExit("sonar-scanner version check failed")
PY
```

---

## 10. Tiny SonarQube smoke test project

Before running the full research pipeline, we created a very small local project to verify that SonarQube scanning works end to end.

The tiny project path is:

```text
tmp_sonar_smoke/tiny_project
```

Directory structure:

```text
tmp_sonar_smoke/
└── tiny_project
    ├── sonar-project.properties
    └── src
        └── app.py
```

The project configuration file is:

```text
tmp_sonar_smoke/tiny_project/sonar-project.properties
```

Its content is:

```text
# SonarQube smoke test project configuration

sonar.projectKey=cursorstudy-tiny-test
sonar.projectName=CursorStudy Tiny Test
sonar.projectVersion=1.0

sonar.sources=src
sonar.sourceEncoding=UTF-8
```

Important values:

```text
Project key: cursorstudy-tiny-test
Project name: CursorStudy Tiny Test
Source directory: src
```

---

## 11. Tiny project source file

The tiny Python source file is:

```text
tmp_sonar_smoke/tiny_project/src/app.py
```

It was intentionally simple and used only for smoke testing.

The purpose was not to create meaningful research metrics, but to verify:

```text
SonarScanner can read a local project.
SonarScanner can analyze a Python file.
SonarScanner can upload the report to local SonarQube.
SonarQube can process the submitted report.
The dashboard can be created.
```

---

## 12. Tiny scan script

The tiny project scan was run with:

```text
run2c-sonarqube-tiny-scan.sh
```

The script loads:

```text
SONAR_HOST
SONAR_TOKEN
SONAR_SCANNER_PATH
```

from `.env`, then runs `sonar-scanner` from inside the tiny project directory.

The key idea is:

```text
The scanner reads sonar-project.properties from the current working directory.
```

The scanner command uses:

```text
-Dsonar.host.url=${SONAR_HOST}
-Dsonar.token=${SONAR_TOKEN}
```

The scan output was redirected to:

```text
ylog.txt
```

using:

```bash
./run2c-sonarqube-tiny-scan.sh > ylog.txt
```

---

## 13. Tiny scan result

The tiny scan completed successfully.

Key confirmed output:

```text
Return code: 0
SonarScanner CLI 8.0.1.6346
Communicating with SonarQube Community Build 26.6.0.123539
Project key: cursorstudy-tiny-test
1 language detected in 1 preprocessed file
1 file indexed
Quality profile for py: Sonar way
1 source file to be analyzed
1/1 source file has been analyzed
Analysis report uploaded
ANALYSIS SUCCESSFUL
EXECUTION SUCCESS
Tiny SonarQube scan completed.
```

Dashboard URL:

```text
http://localhost:9000/dashboard?id=cursorstudy-tiny-test
```

This confirms the complete path:

```text
local source directory
→ sonar-scanner
→ local SonarQube server
→ analysis report upload
→ SonarQube dashboard
```

---

## 14. Warnings seen during tiny scan

Some warnings appeared, but they are acceptable for this smoke test.

### Python version warning

Warning:

```text
Your code is analyzed as compatible with all Python 3 versions by default.
You can get a more precise analysis by setting the exact Python version
in your configuration via the parameter "sonar.python.version"
```

Meaning:

```text
The tiny project did not specify a Python version.
SonarQube used a broad default compatibility mode.
```

Optional future improvement:

```text
sonar.python.version=3.11
```

### Missing blame information warning

Warning:

```text
Missing blame information for the following files:
* src/app.py
```

Meaning:

```text
The tiny smoke test project was not a standalone committed Git repository.
SonarQube could not retrieve normal blame metadata for the test file.
```

This is not a blocker for scanner connectivity.

The real research pipeline disables SCM in `scripts/run_sonarqube.py` to speed analysis and reduce SCM-related friction.

---

## 15. Current checkpoint

At this point, the following pieces are working:

```text
Local SonarQube server: working
Browser access to localhost:9000: working
Admin login and local project setup: working
SONAR_TOKEN: created and valid
SONAR_HOST: configured
SONAR_SCANNER_PATH: configured
SonarScanner CLI executable: working
Tiny local project: created
Tiny scan: successful
Dashboard upload: successful
```

This means the SonarQube infrastructure is ready for the next small API test.

---

## 16. What we have not done yet

We have not yet run:

```text
run2d-sonarqube-tiny-metrics.sh
```

We also have not yet run the full pipeline script:

```text
scripts/run_sonarqube.py
```

We should not run the full script yet.

Before running the full script, we should:

```text
1. Query metrics for the tiny project through the SonarQube API.
2. Confirm metrics such as ncloc, bugs, vulnerabilities, code_smells, duplicated_lines_density, and cognitive_complexity can be fetched.
3. Read and understand scripts/run_sonarqube.py.
4. Run a controlled test on one small real repository or one selected cloned repository.
5. Only then consider larger Phase 2 scanning.
```

---

## 17. Next planned step

The next planned step is to create and run:

```text
run2d-sonarqube-tiny-metrics.sh
```

This script should query SonarQube's metrics API for:

```text
Project key: cursorstudy-tiny-test
```

Suggested metrics:

```text
ncloc
bugs
vulnerabilities
code_smells
duplicated_lines_density
cognitive_complexity
sqale_index
```

This will confirm:

```text
SonarQube API metric retrieval works.
The token can read project measures.
The same kind of API access needed by scripts/run_sonarqube.py is available.
```

---

## 18. Relationship to scripts/run_sonarqube.py

The full research script is:

```text
scripts/run_sonarqube.py
```

Its role is more complex than the tiny smoke test.

At a high level, it:

```text
reads treatment or control repository time series data
iterates over repositories
checks out specific commits
runs sonar-scanner for each repository snapshot
uses project version labels to identify analysis points
queries SonarQube metrics through the API
writes updated metrics back into time series CSV files
```

The tiny smoke test only verified the scanner upload path.

The full script additionally handles:

```text
Git repository checkout
multiple repositories
multiple time periods
parallel processing
metric collection
CSV updates
```

Therefore, the tiny smoke test should be treated as infrastructure validation, not as a replacement for understanding or testing the full script.

---

## 19. Git hygiene

The following files and directories are local setup artifacts and should normally not be committed unless intentionally documenting the workflow:

```text
.env
tmp_sonar_smoke/
ylog.txt
.scannerwork/
```

Recommended `.gitignore` entries:

```text
.env
tmp_sonar_smoke/
.scannerwork/
*.log
```

If we want to commit a clean, documented smoke test, we can keep this README and possibly keep the wrapper scripts, but avoid committing secrets or scanner-generated work directories.

Check Git status:

```bash
git status
```

---

## 20. Summary

The local SonarQube setup is now functional.

We successfully confirmed:

```text
The local SonarQube server is reachable.
The SonarQube token is valid.
The SonarScanner CLI is installed and executable.
A tiny Python project can be scanned.
The analysis report is uploaded to SonarQube.
The dashboard URL is generated.
```

The next step is to query metrics from the tiny project through the SonarQube API before attempting any full Phase 2 SonarQube scanning.
