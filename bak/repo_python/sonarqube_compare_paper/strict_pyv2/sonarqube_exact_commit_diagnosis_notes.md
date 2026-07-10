# SonarQube exact-commit difference diagnosis

This diagnostic focuses only on repo-month rows where the paper data and our pyv2 scan used the exact same latest_commit hash.

## Input scope
- Exact commit rows: 1517
- Unique repos: 211
- Available metrics: ncloc, bugs, vulnerabilities, code_smells, duplicated_lines_density, comment_lines_density, cognitive_complexity, technical_debt, static_analysis_warnings

## ncloc scope classification
- ncloc_identical: 911
- ncloc_close: 406
- ncloc_different: 171
- ncloc_missing: 29

## Interpretation guide
- If ncloc differs for the same commit, SonarQube source inclusion or exclusion scope likely differs.
- If ncloc is identical or close but warning metrics differ, SonarQube rule set, analyzer version, quality profile, or scanner options likely differ.
- Static analysis warnings are computed as bugs + vulnerabilities + code_smells when needed.

## Key metric summary
- static_analysis_warnings: identical_share=0.0857, median_abs_diff=21.0, max_abs_diff=37725.0
- code_smells: identical_share=0.1013, median_abs_diff=19.5, max_abs_diff=8448.0
- bugs: identical_share=0.4523, median_abs_diff=1.0, max_abs_diff=3864.0
- vulnerabilities: identical_share=0.5000, median_abs_diff=0.5, max_abs_diff=137.0
- cognitive_complexity: identical_share=0.8749, median_abs_diff=0.0, max_abs_diff=29442.0
- ncloc: identical_share=0.6122, median_abs_diff=0.0, max_abs_diff=133392.0

## ncloc-status split
- ncloc_close / ncloc: n=406, identical_share=0.0000, median_abs_diff=18.0
- ncloc_different / ncloc: n=171, identical_share=0.0000, median_abs_diff=1578.0
- ncloc_identical / ncloc: n=911, identical_share=1.0000, median_abs_diff=0.0
- ncloc_missing / ncloc: n=0, identical_share=nan, median_abs_diff=nan
- ncloc_close / bugs: n=406, identical_share=0.1626, median_abs_diff=8.0
- ncloc_different / bugs: n=171, identical_share=0.1930, median_abs_diff=4.0
- ncloc_identical / bugs: n=911, identical_share=0.6169, median_abs_diff=0.0
- ncloc_missing / bugs: n=22, identical_share=1.0000, median_abs_diff=0.0
- ncloc_close / vulnerabilities: n=406, identical_share=0.1379, median_abs_diff=7.0
- ncloc_different / vulnerabilities: n=171, identical_share=0.4211, median_abs_diff=1.0
- ncloc_identical / vulnerabilities: n=911, identical_share=0.6641, median_abs_diff=0.0
- ncloc_missing / vulnerabilities: n=22, identical_share=1.0000, median_abs_diff=0.0
- ncloc_close / code_smells: n=406, identical_share=0.0049, median_abs_diff=127.0
- ncloc_different / code_smells: n=171, identical_share=0.0058, median_abs_diff=60.0
- ncloc_identical / code_smells: n=911, identical_share=0.1405, median_abs_diff=8.0
- ncloc_missing / code_smells: n=22, identical_share=1.0000, median_abs_diff=0.0
- ncloc_close / cognitive_complexity: n=406, identical_share=0.8227, median_abs_diff=0.0
- ncloc_different / cognitive_complexity: n=171, identical_share=0.3392, median_abs_diff=36.0
- ncloc_identical / cognitive_complexity: n=910, identical_share=0.9989, median_abs_diff=0.0
- ncloc_missing / cognitive_complexity: n=0, identical_share=nan, median_abs_diff=nan
- ncloc_close / static_analysis_warnings: n=406, identical_share=0.0000, median_abs_diff=128.0
- ncloc_different / static_analysis_warnings: n=171, identical_share=0.0000, median_abs_diff=64.0
- ncloc_identical / static_analysis_warnings: n=911, identical_share=0.1186, median_abs_diff=9.0
- ncloc_missing / static_analysis_warnings: n=29, identical_share=0.7586, median_abs_diff=0.0
