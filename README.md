# A STUDY OF VELOCITY, COMPLEXITY, QUALITY, AND PRODUCTIVITY IN AI GENERATED CODE 

This repository contains a new empirical software engineering study on **AI-assisted software development, code velocity, code complexity, and long-term maintainability**.

---

## Project goal

Research direction:

```text
How do AI coding assistants affect short-term development velocity,
code complexity, static analysis warnings, and longer-term maintainability
in open-source software projects?
```

---

## Current status

Current checkpoint:

```text
Phase 1 reproduction: complete
New repository: AI-Code-Complexity-Study
New conda environment: aicomplexity
Phase 2 live data collection: not started
```

Phase 1 used the existing `data/` files and rendered the R Markdown notebooks. We did **not** rerun live GitHub, GHArchive, repository cloning, or SonarQube collection during Phase 1.

Successful Phase 1 reproduction was completed in:

```text
/home/user1-system12/project-workspace/ai_code_complexity_study
```

using:

```text
conda environment: aicomplexity
Python: 3.11.4
R: 4.3.3
Ubuntu: 22.04.5 LTS
```

---

## Phase 1 reproduction baseline

The following notebooks were successfully rendered:

```text
DataCollection.Rmd
PropensityScoreMatching.Rmd
DiffInDiffBorusyak.Rmd
DynamicPanel.Rmd
DiffInDiffAll.Rmd
DiffInDiffTWFE.Rmd
DiffInDiffCallaway.Rmd
AnalyzeSonarQubeWarnings.Rmd
NonCausalMethods.Rmd
DiffInDiffPosterFigures.Rmd
```

The main Phase 1 script is:

```text
run-phase1.sh
```

Run it from the repository root:

```bash
conda activate aicomplexity
./run-phase1.sh
```

Expected completion message:

```text
Phase 1 reproduction completed.
```

---

## Main reproduced outputs

Expected HTML outputs:

```text
notebooks/DataCollection.html
notebooks/PropensityScoreMatching.html
notebooks/DiffInDiffBorusyak.html
notebooks/DynamicPanel.html
notebooks/DiffInDiffAll.html
notebooks/DiffInDiffTWFE.html
notebooks/DiffInDiffCallaway.html
notebooks/AnalyzeSonarQubeWarnings.html
notebooks/NonCausalMethods.html
notebooks/DiffInDiffPosterFigures.html
```

Check with:

```bash
ls -lh notebooks/*html
```

Important reproduced plot files include:

```text
plots/dynamic_effects_borusyak.pdf
plots/dynamic_effects_activity_all.pdf
plots/dynamic_effects_agent_cohort_all.pdf
```

The key reproduced Figure 3 file is:

```text
plots/dynamic_effects_borusyak.pdf
```

### Figure 3 interpretation

The reproduced Figure 3 contains five panels:

```text
1. Commits
2. Lines Added
3. Static Analysis Warnings
4. Duplicated Lines Density
5. Code Complexity
```

### Dynamic panel / Table 3 interpretation

The dynamic panel results are reproduced by:

```text
notebooks/DynamicPanel.html
```

---

## Repository organization

### `data/`

The `data/` folder currently contains the original dataset used for the MSR 2026 reproduction baseline.

Important files include:

```text
repos.csv
cursor_commits.csv
cursor_files.csv
repo_events.csv
repo_events_control.csv
matching.csv
panel_event_monthly.csv
ts_repos_monthly.csv
ts_repos_control_monthly.csv
repo_metrics.csv
sonarqube_warnings.csv
sonarqube_warning_definitions.csv
control_repo_candidates_*.csv
```

Future versions may add new data files for non-Cursor AI tools and additional project cohorts.

### `notebooks/`

The `notebooks/` folder contains R Markdown notebooks for the reproduction baseline and future study extensions.

| Notebook | Role |
|---|---|
| `DataCollection.Rmd` | Dataset overview and descriptive statistics |
| `PropensityScoreMatching.Rmd` | Propensity score matching and balance diagnostics |
| `DiffInDiffBorusyak.Rmd` | Main Borusyak et al. DiD results, including Figure 3 |
| `DynamicPanel.Rmd` | Dynamic panel GMM results, corresponding to Table 3 |
| `DiffInDiffAll.Rmd` | Comparison across DiD estimators |
| `DiffInDiffTWFE.Rmd` | Two-way fixed effects DiD robustness analysis |
| `DiffInDiffCallaway.Rmd` | Callaway and Sant'Anna DiD robustness analysis |
| `AnalyzeSonarQubeWarnings.Rmd` | SonarQube warning severity/type analysis |
| `NonCausalMethods.Rmd` | Descriptive and correlational auxiliary analysis |
| `DiffInDiffPosterFigures.Rmd` | Poster-oriented versions of selected figures |

Future notebooks should be added for the new AI-code-complexity study rather than overwriting the reproduced baseline.

### `scripts/`

The `scripts/` folder contains Python scripts inherited from the Cursor baseline for:

```text
GitHub repository search
repository cloning
Git history analysis
GHArchive/BigQuery collection
propensity score matching
SonarQube scanning
panel dataset preparation
```

These scripts are useful for understanding the original pipeline and for designing the Phase 2 extension.

### `plots/`

The `plots/` folder stores generated figures.

Important reproduced files include:

```text
plots/dynamic_effects_borusyak.pdf
plots/dynamic_effects_activity_all.pdf
plots/dynamic_effects_agent_cohort_all.pdf
```

### `env_dev/`

The `env_dev/` folder stores environment snapshots.

For this new repository, the preferred environment name is:

```text
aicomplexity
```

Recommended snapshot files:

```text
env_dev/aicomplexity-full.yml
env_dev/aicomplexity-full-no-prefix.yml
env_dev/aicomplexity-explicit-linux-64.txt
env_dev/aicomplexity-conda-list.txt
env_dev/aicomplexity-pip-freeze.txt
env_dev/aicomplexity-r-installed-packages.csv
env_dev/aicomplexity-r-session-info.txt
env_dev/aicomplexity-export-date.txt
env_dev/aicomplexity-system-uname.txt
```

---

## Development environment

Successful Phase 1 reproduction used:

```text
Conda environment: aicomplexity
Python: 3.11.4
R: 4.3.3
Operating system: Ubuntu 22.04.5 LTS
Platform: Linux x86_64
```

The working R path should be similar to:

```text
{HOME-PATH}/miniconda3/envs/aicomplexity/bin/R
```

Check with:

```bash
which python
python --version

which R
R --version

which Rscript
Rscript --version
```

---

## Recreate the environment

### Option A: portable conda YAML

```bash
conda env create -f env_dev/aicomplexity-full-no-prefix.yml
conda activate aicomplexity
```

If the environment name already exists:

```bash
conda env create -n aicomplexity-rebuild -f env_dev/aicomplexity-full-no-prefix.yml
conda activate aicomplexity-rebuild
```

### Option B: exact Linux x86_64 reproduction

```bash
conda create -n aicomplexity-rebuild --file env_dev/aicomplexity-explicit-linux-64.txt
conda activate aicomplexity-rebuild
```

### If `conda activate` fails

```bash
conda init bash
exec bash
conda activate aicomplexity
```

For shell scripts or VS Code Remote SSH terminals:

```bash
source {HOME-PATH}/miniconda3/etc/profile.d/conda.sh
conda activate aicomplexity
```

---

## Verify required packages

### Verify Python packages

```bash
python --version
pip --version
pip freeze | grep -E "pandas|numpy|requests|GitPython|PyGithub|google-cloud-bigquery|scikit-learn|semver|node-semver|gql|aiohttp"
```

### Verify core R packages

```bash
Rscript -e "pkgs <- c('tidyverse','did','DRDID','didimputation','fixest','plm','modelsummary','rmarkdown','languageserver'); print(setNames(sapply(pkgs, requireNamespace, quietly=TRUE), pkgs))"
```

### Verify plotting and table packages

```bash
Rscript -e "pkgs <- c('systemfonts','magick','Cairo','svglite','ggfx','kableExtra'); print(setNames(sapply(pkgs, requireNamespace, quietly=TRUE), pkgs))"
```

---

## Install missing R packages

For conda-based reproduction, prefer conda-forge for large R packages and system-dependent graphics packages.

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

If an R package installation leaves a lock directory:

```bash
find "$CONDA_PREFIX/lib/R/library" -maxdepth 1 -name "00LOCK*" -type d -print -exec rm -rf {} +
```

---

## Notes about local patching

During Phase 1 reproduction, several notebooks required small compatibility patches for the local R/ggplot2/grid environment.

These patches affected plot rendering only. They did not change:

```text
data
models
estimates
confidence intervals
statistical interpretation
```

Examples of local rendering errors:

```text
object 'significant' not found
invalid hex digit in 'color' or 'lty'
Error in element_line(): unused argument (alpha = 0.25)
```

Safe fixes included:

```text
Draw significant and non-significant intervals as separate ggplot layers.
Use simpler point shapes for significance.
Remove unsupported alpha arguments from element_line()/theme() calls.
```

---

## VS Code Remote SSH setup

Recommended `.vscode/settings.json`:

```json
{
  "r.rpath.linux": "{HOME-PATH}/miniconda3/envs/aicomplexity/bin/R",
  "r.rterm.linux": "{HOME-PATH}/miniconda3/envs/aicomplexity/bin/R",
  "r.bracketedPaste": true
}
```

For interactive R chunks, set the working directory to the notebooks folder because many notebooks use paths such as `../data/...`:

```r
setwd("{HOME-PATH}/project-workspace/ai_code_complexity_study/notebooks")
```

---

## Refresh the environment snapshot

After a successful reproduction run:

```bash
conda activate aicomplexity

mkdir -p env_dev

conda env export > env_dev/aicomplexity-full.yml
grep -v "^prefix:" env_dev/aicomplexity-full.yml > env_dev/aicomplexity-full-no-prefix.yml

conda list --explicit > env_dev/aicomplexity-explicit-linux-64.txt
conda list > env_dev/aicomplexity-conda-list.txt

pip freeze > env_dev/aicomplexity-pip-freeze.txt

Rscript -e "ip <- as.data.frame(installed.packages()[, c('Package','Version','LibPath')]); write.csv(ip, 'env_dev/aicomplexity-r-installed-packages.csv', row.names=FALSE)"
Rscript -e "sink('env_dev/aicomplexity-r-session-info.txt'); sessionInfo(); sink()"

date > env_dev/aicomplexity-export-date.txt
uname -a > env_dev/aicomplexity-system-uname.txt
```

---

The project extends the MSR 2026 study:

> Hao He, Courtney Miller, Shyam Agarwal, Christian Kästner, and Bogdan Vasilescu. 2026. *Speed at the Cost of Quality: How Cursor AI Increases Short-Term Velocity and Long-Term Complexity in Open-Source Projects*. MSR 2026. https://doi.org/10.1145/3793302.3793349
