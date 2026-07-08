# SonarQube outlier warning category comparison

## Purpose
Compare paper SonarQube warning rules/categories with issue-level warnings collected from the targeted 2b12 sensitivity scan.

## Inputs
- paper_warnings_file: `data_baseline_backup/sonarqube_warnings.csv`
- paper_definitions_file: `data_baseline_backup/sonarqube_warning_definitions.csv`
- targets_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_paper_like_sensitivity_targets.csv`
- plan_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_paper_like_sensitivity_plan.csv`
- results_file: `repo_python/sonarqube_compare_paper/strict_pyv2/sonarqube_paper_like_sensitivity_results.csv`
- variant: `paper_like`

## Data coverage
- selected targets: 3
- selected plan rows: 3
- paper warning rows for targets: 1
- sensitivity-scan issue rows fetched: 22058
- paper unique rules: 1
- sensitivity unique rules: 450

## Main interpretation guide
- Many paper-heavy rules missing from the sensitivity scan suggest quality profile, active rules, or analyzer/plugin version differences.
- Similar rules but different component/path distributions suggest source-scope or inclusion/exclusion differences.
- Differences in both rule distribution and path distribution suggest combined source-scope and rule/profile effects.

## Top paper-heavy missing rules
- No rows.

## Top sensitivity-heavy extra rules
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S878; type=CODE_SMELL; severity=MAJOR; category=Code Style; paper_count=0; our_count=2995; diff_our_minus_paper=2995
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S3504; type=CODE_SMELL; severity=CRITICAL; category=Code Style; paper_count=0; our_count=2056; diff_our_minus_paper=2056
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S2681; type=CODE_SMELL; severity=MAJOR; category=Logic Error; paper_count=0; our_count=1122; diff_our_minus_paper=1122
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S6759; type=CODE_SMELL; severity=MINOR; category=Type Safety; paper_count=0; our_count=995; diff_our_minus_paper=995
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S3358; type=CODE_SMELL; severity=MAJOR; category=Code Complexity; paper_count=0; our_count=801; diff_our_minus_paper=801
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S7735; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=712; diff_our_minus_paper=712
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S1121; type=CODE_SMELL; severity=MAJOR; category=Code Style; paper_count=0; our_count=661; diff_our_minus_paper=661
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S4325; type=CODE_SMELL; severity=MINOR; category=Type Safety; paper_count=0; our_count=551; diff_our_minus_paper=551
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=javascript:S7780; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=503; diff_our_minus_paper=503
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; rule=python:S3776; type=CODE_SMELL; severity=CRITICAL; category=Code Complexity; paper_count=0; our_count=453; diff_our_minus_paper=453
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S3358; type=CODE_SMELL; severity=MAJOR; category=Code Complexity; paper_count=0; our_count=428; diff_our_minus_paper=428
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S7748; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=426; diff_our_minus_paper=426
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S7764; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=359; diff_our_minus_paper=359
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S1135; type=CODE_SMELL; severity=INFO; category=Code Hygiene; paper_count=0; our_count=333; diff_our_minus_paper=333
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S7773; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=311; diff_our_minus_paper=311
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; rule=python:S1192; type=CODE_SMELL; severity=CRITICAL; category=Code Complexity; paper_count=0; our_count=303; diff_our_minus_paper=303
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S6861; type=CODE_SMELL; severity=CRITICAL; category=Code Style; paper_count=0; our_count=266; diff_our_minus_paper=266
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S3776; type=CODE_SMELL; severity=CRITICAL; category=Code Complexity; paper_count=0; our_count=260; diff_our_minus_paper=260
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S1763; type=BUG; severity=MAJOR; category=Logic Error; paper_count=0; our_count=245; diff_our_minus_paper=245
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S6582; type=CODE_SMELL; severity=MAJOR; category=Code Style; paper_count=0; our_count=214; diff_our_minus_paper=214
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S6749; type=CODE_SMELL; severity=MINOR; category=React Patterns; paper_count=0; our_count=196; diff_our_minus_paper=196
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S1874; type=CODE_SMELL; severity=MINOR; category=API Usage; paper_count=0; our_count=171; diff_our_minus_paper=171
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S3863; type=CODE_SMELL; severity=MINOR; category=Code Style; paper_count=0; our_count=170; diff_our_minus_paper=170
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S6479; type=CODE_SMELL; severity=MAJOR; category=React Patterns; paper_count=0; our_count=166; diff_our_minus_paper=166
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S7773; type=CODE_SMELL; severity=MINOR; category=Unmapped; paper_count=0; our_count=165; diff_our_minus_paper=165
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S2933; type=CODE_SMELL; severity=MAJOR; category=Code Style; paper_count=0; our_count=155; diff_our_minus_paper=155
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=typescript:S6767; type=CODE_SMELL; severity=MINOR; category=React Patterns; paper_count=0; our_count=138; diff_our_minus_paper=138
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; rule=css:S125; type=CODE_SMELL; severity=MAJOR; category=Code Hygiene; paper_count=0; our_count=133; diff_our_minus_paper=133
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S3776; type=CODE_SMELL; severity=CRITICAL; category=Code Complexity; paper_count=0; our_count=123; diff_our_minus_paper=123
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; rule=javascript:S2392; type=CODE_SMELL; severity=MAJOR; category=Naming Conventions; paper_count=0; our_count=122; diff_our_minus_paper=122

## Top type/severity differences
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=MINOR; paper_count=0; our_count=6134; diff_our_minus_paper=6134; abs_diff=6134
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=MAJOR; paper_count=0; our_count=5989; diff_our_minus_paper=5989; abs_diff=5989
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=CRITICAL; paper_count=0; our_count=2631; diff_our_minus_paper=2631; abs_diff=2631
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=MAJOR; paper_count=1; our_count=2630; diff_our_minus_paper=2629; abs_diff=2629
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=MINOR; paper_count=0; our_count=983; diff_our_minus_paper=983; abs_diff=983
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=CODE_SMELL; severity=CRITICAL; paper_count=0; our_count=853; diff_our_minus_paper=853; abs_diff=853
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=CODE_SMELL; severity=MAJOR; paper_count=0; our_count=524; diff_our_minus_paper=524; abs_diff=524
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=CRITICAL; paper_count=0; our_count=494; diff_our_minus_paper=494; abs_diff=494
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=INFO; paper_count=0; our_count=408; diff_our_minus_paper=408; abs_diff=408
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=CODE_SMELL; severity=MINOR; paper_count=0; our_count=349; diff_our_minus_paper=349; abs_diff=349
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=BUG; severity=MAJOR; paper_count=0; our_count=326; diff_our_minus_paper=326; abs_diff=326
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=BUG; severity=MAJOR; paper_count=0; our_count=152; diff_our_minus_paper=152; abs_diff=152
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=VULNERABILITY; severity=MAJOR; paper_count=0; our_count=124; diff_our_minus_paper=124; abs_diff=124
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=BUG; severity=MINOR; paper_count=0; our_count=103; diff_our_minus_paper=103; abs_diff=103
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=CODE_SMELL; severity=INFO; paper_count=0; our_count=94; diff_our_minus_paper=94; abs_diff=94
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=BUG; severity=MAJOR; paper_count=0; our_count=58; diff_our_minus_paper=58; abs_diff=58
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=BUG; severity=MINOR; paper_count=0; our_count=48; diff_our_minus_paper=48; abs_diff=48
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=VULNERABILITY; severity=BLOCKER; paper_count=0; our_count=37; diff_our_minus_paper=37; abs_diff=37
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=VULNERABILITY; severity=CRITICAL; paper_count=0; our_count=31; diff_our_minus_paper=31; abs_diff=31
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=BLOCKER; paper_count=0; our_count=15; diff_our_minus_paper=15; abs_diff=15
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=VULNERABILITY; severity=CRITICAL; paper_count=0; our_count=15; diff_our_minus_paper=15; abs_diff=15
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=BUG; severity=CRITICAL; paper_count=0; our_count=13; diff_our_minus_paper=13; abs_diff=13
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=CODE_SMELL; severity=BLOCKER; paper_count=0; our_count=9; diff_our_minus_paper=9; abs_diff=9
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=BUG; severity=BLOCKER; paper_count=0; our_count=8; diff_our_minus_paper=8; abs_diff=8
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=CODE_SMELL; severity=BLOCKER; paper_count=0; our_count=6; diff_our_minus_paper=6; abs_diff=6
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; type=BUG; severity=MINOR; paper_count=0; our_count=5; diff_our_minus_paper=5; abs_diff=5
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=VULNERABILITY; severity=MAJOR; paper_count=0; our_count=4; diff_our_minus_paper=4; abs_diff=4
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; type=VULNERABILITY; severity=MINOR; paper_count=0; our_count=4; diff_our_minus_paper=4; abs_diff=4
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=BUG; severity=CRITICAL; paper_count=0; our_count=3; diff_our_minus_paper=3; abs_diff=3
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; type=BUG; severity=BLOCKER; paper_count=0; our_count=2; diff_our_minus_paper=2; abs_diff=2

## Top category differences
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Code Style; type=CODE_SMELL; paper_count=0; our_count=6390; diff_our_minus_paper=6390; abs_diff=6390
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Unmapped; type=CODE_SMELL; paper_count=0; our_count=3452; diff_our_minus_paper=3452; abs_diff=3452
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Type Safety; type=CODE_SMELL; paper_count=0; our_count=1650; diff_our_minus_paper=1650; abs_diff=1650
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Code Complexity; type=CODE_SMELL; paper_count=0; our_count=1435; diff_our_minus_paper=1435; abs_diff=1435
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Logic Error; type=CODE_SMELL; paper_count=0; our_count=1218; diff_our_minus_paper=1218; abs_diff=1218
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Code Style; type=CODE_SMELL; paper_count=0; our_count=985; diff_our_minus_paper=985; abs_diff=985
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Unmapped; type=CODE_SMELL; paper_count=0; our_count=837; diff_our_minus_paper=837; abs_diff=837
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Code Complexity; type=CODE_SMELL; paper_count=0; our_count=778; diff_our_minus_paper=778; abs_diff=778
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Code Hygiene; type=CODE_SMELL; paper_count=0; our_count=648; diff_our_minus_paper=648; abs_diff=648
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Code Complexity; type=CODE_SMELL; paper_count=0; our_count=635; diff_our_minus_paper=635; abs_diff=635
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=React Patterns; type=CODE_SMELL; paper_count=0; our_count=616; diff_our_minus_paper=616; abs_diff=616
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Logic Error; type=BUG; paper_count=0; our_count=336; diff_our_minus_paper=336; abs_diff=336
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=API Usage; type=CODE_SMELL; paper_count=0; our_count=265; diff_our_minus_paper=265; abs_diff=265
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Code Hygiene; type=CODE_SMELL; paper_count=0; our_count=260; diff_our_minus_paper=260; abs_diff=260
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Naming Conventions; type=CODE_SMELL; paper_count=0; our_count=202; diff_our_minus_paper=202; abs_diff=202
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Infrastructure; type=CODE_SMELL; paper_count=0; our_count=167; diff_our_minus_paper=167; abs_diff=167
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Regex Issues; type=CODE_SMELL; paper_count=0; our_count=164; diff_our_minus_paper=164; abs_diff=164
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Accessibility; type=CODE_SMELL; paper_count=0; our_count=156; diff_our_minus_paper=156; abs_diff=156
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Naming Conventions; type=CODE_SMELL; paper_count=1; our_count=149; diff_our_minus_paper=148; abs_diff=148
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Naming Conventions; type=CODE_SMELL; paper_count=0; our_count=147; diff_our_minus_paper=147; abs_diff=147
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Error Handling; type=CODE_SMELL; paper_count=0; our_count=141; diff_our_minus_paper=141; abs_diff=141
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Error Handling; type=CODE_SMELL; paper_count=0; our_count=131; diff_our_minus_paper=131; abs_diff=131
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Security; type=VULNERABILITY; paper_count=0; our_count=115; diff_our_minus_paper=115; abs_diff=115
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Unmapped; type=CODE_SMELL; paper_count=0; our_count=113; diff_our_minus_paper=113; abs_diff=113
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Accessibility; type=BUG; paper_count=0; our_count=110; diff_our_minus_paper=110; abs_diff=110
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Regex Issues; type=CODE_SMELL; paper_count=0; our_count=103; diff_our_minus_paper=103; abs_diff=103
- repo_name=DataDog/integrations-core; time=2025-01; variant=paper_like; category=Code Style; type=CODE_SMELL; paper_count=0; our_count=99; diff_our_minus_paper=99; abs_diff=99
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Logic Error; type=BUG; paper_count=0; our_count=93; diff_our_minus_paper=93; abs_diff=93
- repo_name=zauberzeug/nicegui; time=2025-04; variant=paper_like; category=Code Hygiene; type=CODE_SMELL; paper_count=0; our_count=70; diff_our_minus_paper=70; abs_diff=70
- repo_name=PostHog/posthog; time=2025-04; variant=paper_like; category=Logic Error; type=CODE_SMELL; paper_count=0; our_count=59; diff_our_minus_paper=59; abs_diff=59

## Recommended next step
Inspect the missing-paper-rules and extra-our-rules files first. If missing paper rules dominate, compare SonarQube quality profiles, active rules, and analyzer/plugin versions before attempting more source-scope rescans.
