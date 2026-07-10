# SonarQube outlier repository inspection notes

## Purpose
Inspect actual local repositories for the largest SonarQube differences between the paper data and the new Python pyv2 scan.

## Interpretation guide
- If a source-scope outlier has different tracked file counts or many generated/vendor/test files, source inclusion/exclusion is likely involved.
- If an exact-commit and ncloc-identical outlier still has warning metric differences, SonarQube rule/config/analyzer/profile differences remain the strongest explanation.
- Configuration files such as sonar-project.properties, pyproject.toml, setup.cfg, tox.ini, and .gitignore can explain local source-scope and analyzer behavior.

## Selected inspection size
Selected rows: 234
Selected unique repos: 12

## Git tree summary
Rows with Git tree summaries: 253
Repos with Git tree summaries: 12
