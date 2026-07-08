# SonarQube outlier root cause notes

## Purpose
Summarize repo-level evidence for why the new Python pyv2 SonarQube results differ from the paper data.

## Inputs
- top_repos_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_main_difference_drivers_top_repos_final_did.csv`
- git_tree_summary_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_outlier_repo_git_tree_summary.csv`
- top_directories_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_outlier_repo_top_directories.csv`
- config_presence_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_outlier_repo_config_presence.csv`
- original_sonarqube_script: `scripts/run_sonarqube.py`
- pyv2_sonarqube_script: `proc_scripts/run_sonarqube_v2.py`

## Scanner configuration comparison
### Original paper scanner script
- Path: `scripts/run_sonarqube.py`
- Exists: True
- Key Sonar flags: -Dsonar.java.binaries=.; -Dsonar.scm.disabled=true; -Dsonar.sources=.
- Notes: basic scanner flags only

### Current Python pyv2 scanner script
- Path: `proc_scripts/run_sonarqube_v2.py`
- Exists: True
- Key Sonar flags: -Dsonar.exclusions=; -Dsonar.java.binaries=.; -Dsonar.python.version=3.11; -Dsonar.scm.disabled=true; -Dsonar.sourceEncoding=UTF-8; -Dsonar.sources=.
- Notes: language-specific helper present; waits for compute-engine readiness; explicit exclusions present; explicit Python version present

## Root cause distribution
- rule_config_analyzer_profile_difference: 64 repos
- source_scope_inclusion_exclusion_difference: 57 repos
- commit_selection_difference: 5 repos

## Key interpretation
The first target for reproducing the paper should be a paper-like SonarQube scanner configuration: `sonar.sources=.` with no pyv2 language-specific exclusions and no explicit `sonar.python.version=3.11`.
If this reduces the gap for source-scope outliers, then pyv2 exclusions/source scope were a major driver. If warning counts still differ under the same commit and ncloc, compare SonarQube server version, language analyzer/plugin version, quality profile, and active rules.

## Top repositories by summarized difference
- `PostHog/posthog`: source_scope_inclusion_exclusion_difference; metrics=ncloc; technical_debt; cognitive_complexity; static_analysis_warnings; code_smells; vulnerabilities; bugs; dirs=frontend:5886; posthog:3054; plugin-server:710; products:669; rust:575; ee:535; common:245; hogvm:167
- `zauberzeug/nicegui`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; ncloc; code_smells; static_analysis_warnings; bugs; cognitive_complexity; duplicated_lines_density; dirs=nicegui:836; website:190; examples:161; tests:107; (root):37; .github:11; scripts:5; .cursor:2
- `DataDog/integrations-core`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; static_analysis_warnings; code_smells; ncloc; bugs; cognitive_complexity; vulnerabilities; dirs=snmp:653; openstack_controller:448; datadog_checks_base:400; datadog_checks_dev:371; ddev:252; mongo:218; sqlserver:140; postgres:96
- `lancedb/lancedb`: source_scope_inclusion_exclusion_difference; metrics=ncloc; technical_debt; cognitive_complexity; code_smells; static_analysis_warnings; dirs=docs:302; python:115; nodejs:86; rust:63; java:39; node:35; .github:31; ci:19
- `getsentry/sentry`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; code_smells; static_analysis_warnings; ncloc; bugs; vulnerabilities; cognitive_complexity; dirs=static:7570; src:4725; tests:4706; fixtures:494; api-docs:75; .github:63; (root):42; bin:24
- `yeagerai/genlayer-studio`: source_scope_inclusion_exclusion_difference; metrics=ncloc; technical_debt; cognitive_complexity; static_analysis_warnings; code_smells; dirs=nan
- `TextGeneratorio/text-generator.io`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; ncloc; static_analysis_warnings; code_smells; vulnerabilities; bugs; dirs=nan
- `ethyca/fides`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; code_smells; static_analysis_warnings; ncloc; bugs; cognitive_complexity; vulnerabilities; dirs=nan
- `terryyin/lizard`: source_scope_inclusion_exclusion_difference; metrics=technical_debt; ncloc; static_analysis_warnings; code_smells; bugs; dirs=nan
- `wdm0006/elote`: source_scope_inclusion_exclusion_difference; metrics=cognitive_complexity; ncloc; technical_debt; static_analysis_warnings; code_smells; dirs=docs:85; tests:15; (root):12; examples:12; elote:11; .github:6; .cursor:5; scripts:1

## Recommended next step
Create a small `run-py-2b12` sensitivity scan for the highest-impact repositories. Start with the original paper-like scanner flags, then test one source-scope variant. Do not run a full rescan until the small sensitivity scan shows which configuration moves pyv2 metrics toward the paper values.
