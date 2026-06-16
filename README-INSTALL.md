# README-INSTALL.md

# CursorStudy Installation and Reproduction Guide

This document explains how to recreate the working environment used to reproduce the paper results for:

**Speed at the Cost of Quality: How Cursor AI Increases Short-Term Velocity and Long-Term Complexity in Open-Source Projects**

This guide is based on the environment snapshot stored in:

```text
env_dev/
```

The current successful checkpoint is:

```text
DataCollection.Rmd                  rendered successfully
PropensityScoreMatching.Rmd         rendered successfully
DiffInDiffBorusyak.Rmd              rendered successfully
Figure 3 PDF generated successfully
```

The main reproduced Figure 3 file is:

```text
plots/dynamic_effects_borusyak.pdf
```

---

# 1. Purpose of this file

This file is for **Phase 1: reproducing the paper results from the existing dataset**.

In this phase, we do **not** rerun GitHub data collection, GHArchive collection, repository cloning, or SonarQube analysis.

Instead, we use the already downloaded data files in:

```text
data/
```

and run the R notebooks in:

```text
notebooks/
```

The Python scripts in `scripts/` are mainly for **Phase 2**, where we may later rebuild the dataset from scratch.

---

# 2. Directory assumptions

This guide assumes the repository root looks like this:

```text
cursor_study/
├── data/
├── env_dev/
├── notebooks/
├── plots/
├── scripts/
├── README.md
├── README-INSTALL.md
└── ...
```

Important data files should already exist:

```text
data/panel_event_monthly.csv
data/matching.csv
data/ts_repos_monthly.csv
data/ts_repos_control_monthly.csv
data/repo_metrics.csv
data/repos.csv
data/cursor_files.csv
data/cursor_commits.csv
data/sonarqube_warnings.csv
```

Important notebooks should exist:

```text
notebooks/DataCollection.Rmd
notebooks/PropensityScoreMatching.Rmd
notebooks/DiffInDiffBorusyak.Rmd
notebooks/DynamicPanel.Rmd
```

---

# 3. Environment snapshot files

The environment snapshot is stored in:

```text
env_dev/
```

Current files:

```text
env_dev/conda-list.txt
env_dev/cursorstudy-explicit-linux-64.txt
env_dev/cursorstudy-full-no-prefix.yml
env_dev/cursorstudy-full.yml
env_dev/export-date.txt
env_dev/pip-freeze.txt
env_dev/r-installed-packages.csv
env_dev/r-session-info.txt
env_dev/system-uname.txt
```

Each file has a different purpose.

## 3.1 `cursorstudy-full-no-prefix.yml`

Use this for normal conda environment recreation.

This file is portable because the local absolute `prefix:` line has been removed.

Recommended for most cases:

```bash
conda env create -f env_dev/cursorstudy-full-no-prefix.yml
```

## 3.2 `cursorstudy-full.yml`

This is the full conda export including the original local prefix.

It is useful for documentation, but usually should not be used directly on another machine because it may contain a machine-specific path such as:

```text
/home/user1-system12/miniconda3/envs/cursorstudy
```

## 3.3 `cursorstudy-explicit-linux-64.txt`

This is the most exact Linux reproduction file.

Use it only on a similar Linux x86_64 machine.

```bash
conda create -n cursorstudy-rebuild --file env_dev/cursorstudy-explicit-linux-64.txt
```

This is more exact than the YAML file, but less portable across operating systems.

## 3.4 `conda-list.txt`

This records all conda packages and versions in a human-readable format.

Useful for checking versions.

```bash
cat env_dev/conda-list.txt
```

## 3.5 `pip-freeze.txt`

This records pip-installed Python packages.

Useful for checking Python dependencies.

```bash
cat env_dev/pip-freeze.txt
```

## 3.6 `r-installed-packages.csv`

This records R packages installed in the environment.

Useful for checking package versions.

```bash
head env_dev/r-installed-packages.csv
```

## 3.7 `r-session-info.txt`

This records the R version, platform, and session information.

Useful for reproducibility reports.

```bash
cat env_dev/r-session-info.txt
```

## 3.8 `system-uname.txt`

This records the Linux kernel/system info.

```bash
cat env_dev/system-uname.txt
```

## 3.9 `export-date.txt`

This records when the environment snapshot was created.

```bash
cat env_dev/export-date.txt
```

---

# 4. Current successful environment

The working environment used today is:

```text
Conda environment: cursorstudy
Python: 3.11.4
R: 4.3.3
Platform: Ubuntu 22.04, Linux x86_64
```

The working R executable path was:

```text
/home/user1-system12/miniconda3/envs/cursorstudy/bin/R
```

The working Rscript path was:

```text
/home/user1-system12/miniconda3/envs/cursorstudy/bin/Rscript
```

Check with:

```bash
which R
R --version

which Rscript
Rscript --version
```

Expected R version:

```text
R version 4.3.3
```

---

# 5. Recreate the environment

There are two recommended ways.

---

## Option A: Recreate from YAML

This is the usual method.

```bash
conda env create -f env_dev/cursorstudy-full-no-prefix.yml
conda activate cursorstudy
```

If the environment name already exists, create a new one:

```bash
conda env create -n cursorstudy-rebuild -f env_dev/cursorstudy-full-no-prefix.yml
conda activate cursorstudy-rebuild
```

Then verify:

```bash
python --version
R --version
Rscript --version
```

---

## Option B: Recreate exactly on Linux x86_64

This is more exact, but less portable.

```bash
conda create -n cursorstudy-rebuild --file env_dev/cursorstudy-explicit-linux-64.txt
conda activate cursorstudy-rebuild
```

Then verify:

```bash
python --version
R --version
Rscript --version
```

---

# 6. If `conda activate` fails

If you see:

```text
CondaError: Run 'conda init' before 'conda activate'
```

run:

```bash
conda init bash
exec bash
conda activate cursorstudy
```

For shell scripts or VS Code remote terminals, this form is safer:

```bash
source /home/user1-system12/miniconda3/etc/profile.d/conda.sh
conda activate cursorstudy
```

Adjust the miniconda path if your system uses a different location.

---

# 7. Verify Python packages

Run:

```bash
python --version
pip --version
pip freeze | grep -E "pandas|numpy|requests|GitPython|PyGithub|google-cloud-bigquery|scikit-learn|semver|node-semver|gql|aiohttp"
```

The important Python packages include:

```text
pandas
numpy
requests
python-dotenv
GitPython
PyGithub
google-cloud-bigquery
scikit-learn
semver
node-semver
gql
aiohttp
```

These Python packages are mainly needed for data collection scripts, not for the first reproduction phase.

---

# 8. Verify R packages

Run:

```bash
Rscript -e "pkgs <- c('tidyverse','did','DRDID','didimputation','fixest','plm','modelsummary','rmarkdown','languageserver'); print(setNames(sapply(pkgs, requireNamespace, quietly=TRUE), pkgs))"
```

Expected result:

```text
tidyverse       TRUE
did             TRUE
DRDID           TRUE
didimputation   TRUE
fixest          TRUE
plm             TRUE
modelsummary    TRUE
rmarkdown       TRUE
languageserver  TRUE
```

Also verify plotting/table packages:

```bash
Rscript -e "pkgs <- c('systemfonts','magick','Cairo','svglite','ggfx','kableExtra'); print(setNames(sapply(pkgs, requireNamespace, quietly=TRUE), pkgs))"
```

Expected result:

```text
systemfonts TRUE
magick      TRUE
Cairo       TRUE
svglite     TRUE
ggfx        TRUE
kableExtra  TRUE
```

---

# 9. If R packages are missing

If core R packages are missing, install them from conda-forge first:

```bash
conda install -c conda-forge \
  r-base=4.3.3 \
  r-tidyverse \
  r-rmarkdown \
  r-knitr \
  r-data.table \
  r-fixest \
  r-did \
  r-drdid \
  r-fastglm \
  r-plm \
  r-modelsummary \
  r-kableextra \
  r-gridextra \
  r-cowplot \
  r-corrplot \
  r-rcolorbrewer \
  r-cairo \
  r-showtext \
  r-ggfx \
  r-languageserver \
  -y
```

If plotting packages are missing:

```bash
conda install -c conda-forge \
  r-systemfonts \
  r-magick \
  r-cairo \
  r-svglite \
  r-ggfx \
  r-kableextra \
  -y
```

If some smaller packages are still missing, install from R:

```bash
R
```

Then inside R:

```r
options(repos = c(CRAN = "https://cloud.r-project.org"))

install.packages(c(
  "didimputation",
  "bacondecomp"
))
```

When quitting R, choose not to save the workspace:

```text
Save workspace image? [y/n/c]: n
```

---

# 10. Remove failed R package locks

If an R package installation fails, remove stale lock directories:

```bash
find $CONDA_PREFIX/lib/R/library -maxdepth 1 -name "00LOCK*" -type d -print -exec rm -rf {} +
```

Then retry installation.

---

# 11. VS Code Remote SSH setup

This project can be reproduced using VS Code with Remote SSH.

Recommended workflow:

```text
Local MacBook:
- VS Code UI
- Remote SSH connection

Remote Ubuntu server:
- conda environment
- R execution
- R Markdown rendering
- data files
- generated plots
```

Install the VS Code R extension on the remote SSH target.

Recommended `.vscode/settings.json`:

```json
{
  "r.rpath.linux": "/home/user1-system12/miniconda3/envs/cursorstudy/bin/R",
  "r.rterm.linux": "/home/user1-system12/miniconda3/envs/cursorstudy/bin/R",
  "r.bracketedPaste": true
}
```

Adjust paths if your conda environment is elsewhere.

---

# 12. Reproduce paper results from existing data

Make sure you are in the repository root:

```bash
pwd
ls data/panel_event_monthly.csv
ls notebooks/DataCollection.Rmd
```

Activate the environment:

```bash
conda activate cursorstudy
```

If needed:

```bash
source /home/user1-system12/miniconda3/etc/profile.d/conda.sh
conda activate cursorstudy
```

---

## 12.1 Render DataCollection notebook

```bash
Rscript -e "rmarkdown::render('notebooks/DataCollection.Rmd')"
```

Expected output:

```text
Output created: DataCollection.html
```

Check:

```bash
ls -lh notebooks/DataCollection.html
```

This notebook checks the dataset overview, Cursor-adopting repositories, adoption timing, and related descriptive figures/tables.

---

## 12.2 Render PropensityScoreMatching notebook

```bash
Rscript -e "rmarkdown::render('notebooks/PropensityScoreMatching.Rmd')"
```

Expected output:

```text
Output created: PropensityScoreMatching.html
```

Check:

```bash
ls -lh notebooks/PropensityScoreMatching.html
```

This notebook checks whether the Cursor-adopting repositories and matched control repositories are comparable before treatment.

---

## 12.3 Render main DiD notebook

```bash
Rscript -e "rmarkdown::render('notebooks/DiffInDiffBorusyak.Rmd')"
```

Expected outputs:

```text
notebooks/DiffInDiffBorusyak.html
plots/dynamic_effects_borusyak.pdf
plots/dynamic_effects_activity_all.pdf
plots/dynamic_effects_agent_cohort_all.pdf
```

Check:

```bash
ls -lh notebooks/DiffInDiffBorusyak.html
ls -lh plots/dynamic_effects_borusyak.pdf
ls -lh plots/dynamic_effects_activity_all.pdf
ls -lh plots/dynamic_effects_agent_cohort_all.pdf
```

The file:

```text
plots/dynamic_effects_borusyak.pdf
```

corresponds to the paper's Figure 3.

---

# 13. Figure 3 interpretation

The reproduced Figure 3 is:

```text
plots/dynamic_effects_borusyak.pdf
```

It contains five panels:

```text
1. Commits
2. Lines Added
3. Static Analysis Warnings
4. Duplicated Lines Density
5. Code Complexity
```

The x-axis is:

```text
Months Relative to Cursor Adoption
```

Meaning:

```text
-6 to -2   months before Cursor adoption
0          adoption month
1 to 6     months after adoption
```

The y-axis is:

```text
Treatment Effect
```

A point above zero means the outcome increased after Cursor adoption compared to the estimated no-Cursor counterfactual.

The filled and hollow dots mean:

```text
Filled dot: statistically significant, p < 0.05
Hollow dot: not statistically significant, p >= 0.05
```

Main message:

```text
Cursor adoption produces a large but short-lived increase in development velocity,
especially lines added, while static analysis warnings and code complexity increase
more persistently.
```

In simple words:

```text
Cursor makes projects faster at first,
but the code also becomes more warning-heavy and complex over time.
```

---

# 14. Notes about local patching

During reproduction, `DiffInDiffBorusyak.Rmd` may fail on recent ggplot/grid combinations due to plot rendering issues such as:

```text
object 'significant' not found
invalid hex digit in 'color' or 'lty'
```

These are plotting-style problems, not statistical estimation problems.

The safe fix is to simplify the ggplot aesthetics:

```text
- keep the same estimates
- keep the same confidence intervals
- keep the same significance labels
- avoid fragile after_scale or linetype mappings
```

In our successful run, only plot rendering logic was adjusted. The data and model results were not changed.

---

# 15. Continue with DynamicPanel notebook

After Figure 3 is reproduced, continue with:

```bash
Rscript -e "rmarkdown::render('notebooks/DynamicPanel.Rmd')"
```

Expected output:

```text
notebooks/DynamicPanel.html
```

This notebook reproduces the dynamic panel GMM results, corresponding to the paper's Table 3.

---

# 16. What not to run during Phase 1

Do not run data collection yet:

```bash
bash data-collection.sh
python -m scripts.clone_repos
python -m scripts.analyze_repos
python -m scripts.fetch_gharchive
python -m scripts.run_sonarqube
```

These commands belong to Phase 2.

They may change the dataset because GitHub repositories, APIs, and SonarQube behavior can change over time.

---

# 17. Phase 2 later: full data collection

Later, to rebuild the dataset from scratch, the main script order is in:

```text
data-collection.sh
```

It performs roughly this pipeline:

```text
1. clone treatment repositories
2. analyze treatment repository commits and lines added
3. fetch GHArchive activity for treatment repositories
4. run SonarQube for treatment repositories

5. clone control repositories
6. analyze control repository commits and lines added
7. fetch GHArchive activity for control repositories
8. run SonarQube for control repositories
```

Before Phase 2, configure environment variables such as:

```text
GITHUB_TOKEN
SONAR_HOST
SONAR_SCANNER_PATH
SONAR_TOKEN
```

SonarQube is not needed for Phase 1.

---

# 18. SonarQube note

The file:

```text
sonarqube-start.sh
```

is for starting/stopping a local SonarQube server.

It is not needed for reproducing the paper results from existing data.

It will matter only when rerunning SonarQube static analysis during full data collection.

---

# 19. Recommended checkpoint command

After a successful reproduction run, refresh the environment snapshot:

```bash
conda activate cursorstudy

mkdir -p env_dev

conda env export > env_dev/cursorstudy-full.yml
grep -v "^prefix:" env_dev/cursorstudy-full.yml > env_dev/cursorstudy-full-no-prefix.yml

conda list --explicit > env_dev/cursorstudy-explicit-linux-64.txt
conda list > env_dev/conda-list.txt

pip freeze > env_dev/pip-freeze.txt

Rscript -e "ip <- as.data.frame(installed.packages()[, c('Package','Version','LibPath')]); write.csv(ip, 'env_dev/r-installed-packages.csv', row.names=FALSE)"
Rscript -e "sink('env_dev/r-session-info.txt'); sessionInfo(); sink()"

date > env_dev/export-date.txt
uname -a > env_dev/system-uname.txt
```

Check:

```bash
ls -lh env_dev/
```

---
