# run-py-2b15 paper-structure panel notes

## Purpose

Create a diagnostic CSV with the same column order as the paper `data/panel_event_monthly.csv`.
The regenerated Python quality metrics are preserved, while unavailable paper covariates are filled from the frozen paper panel when repo-month keys match.

## Inputs

- Python quality input: `repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv`
- Paper panel: `data/panel_event_monthly.csv`

## Output

- Modified structure panel: `repo_python/did_final/panel_event_monthly_modified_structure.csv`

## Key summary

- Output rows: 1604
- Output columns: 42
- Columns copied from Python input: 33
- Columns filled from paper panel: 9
- Columns set to NA: 0
- Repo-month rows matched to paper panel: 1589
- Repo-month rows not matched to paper panel: 15

## Interpretation caution

This file is for schema and Rmd-compatibility diagnostics only.
It mixes regenerated Python SonarQube metrics with selected frozen paper covariates, so it should not be presented as a full paper reproduction dataset.

## Largest paper-vs-our metric differences

- zauberzeug/nicegui 2025-04 ncloc: our=78118.0, paper=211510.0, diff=-133392.0
- PostHog/posthog 2025-04 ncloc: our=1025455.0, paper=937017.0, diff=88438.0
- PostHog/posthog 2025-08 ncloc: our=1313277.0, paper=1232071.0, diff=81206.0
- PostHog/posthog 2025-07 ncloc: our=1224250.0, paper=1155675.0, diff=68575.0
- PostHog/posthog 2025-06 ncloc: our=1143141.0, paper=1079135.0, diff=64006.0
- zauberzeug/nicegui 2025-04 technical_debt: our=136099.0, paper=193776.0, diff=-57677.0
- PostHog/posthog 2025-05 ncloc: our=1075854.0, paper=1021926.0, diff=53928.0
- PostHog/posthog 2025-03 ncloc: our=981233.0, paper=936364.0, diff=44869.0
- PostHog/posthog 2025-02 ncloc: our=933176.0, paper=896790.0, diff=36386.0
- zauberzeug/nicegui 2025-02 technical_debt: our=228706.0, paper=193727.0, diff=34979.0
