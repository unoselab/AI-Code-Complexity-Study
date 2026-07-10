# run-py-2e paper-same-column diagnostic notes

## Purpose

Create a paper-schema diagnostic output from the analysis-ready Python quality DiD input.
Regenerated SonarQube metrics are preserved, while selected unavailable columns are filled from the frozen paper panel on exact repo-month matches.

## Inputs

- Analysis-ready source: `repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv`
- Frozen paper panel: `data/panel_event_monthly.csv`

## Output

- Paper-schema output: `repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete_paper_same_column_overlap.csv`
- Keep exact overlap only: `TRUE`

## Key summary

- Source complete rows: 1604
- Exact repo-month matches: 1589
- Unmatched repo-month rows: 15
- Output rows: 1589
- Output columns: 42
- Paper duplicate repo-month rows before deduplication: 153

## Columns filled from the paper panel

- `stars`
- `issues`
- `issue_comments`
- `age`
- `num_dependencies_total`
- `num_vulnerable_dependencies`
- `average_technical_lag`
- `other_agents`
- `high_confidence`

## Interpretation caution

This output is an overlap-restricted diagnostic dataset, not a full independent reproduction dataset.
Dropping unmatched repo-month rows changes the analysis sample and should be reported explicitly.
