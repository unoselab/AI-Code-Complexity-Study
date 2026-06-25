Daily Research Report

Date: 2026-06-25

Objective:
Continue reconstructing the JavaScript/TypeScript matched DiD dataset for the Cursor adoption study and begin the long-running SonarQube quality-metric collection process.

What We Did:

1. Completed final panel QC for the matched JS/TS DiD dataset.
2. Generated four panel outputs:

   * Main final-clean unbalanced panel.
   * Main final-clean window-completed panel.
   * Strict 1:3 unbalanced robustness panel.
   * Strict 1:3 window-completed robustness panel.
3. Confirmed that all control rows in the generated panels have matched-pair provenance.
4. Created `proc_scripts/prepare_sonarqube_input.py` to move the SonarQube input-preparation logic out of the shell wrapper.
5. Created `run9a-create-jsts-sonarqube-input.sh` as a thin wrapper around `prepare_sonarqube_input.py`.
6. Ran a smoke test for `run9a` with two treatment repositories and two control repositories.
7. Ran the full `run9a` input generation using the main window-completed matched panel.
8. Verified that SonarQube input files were generated with no missing `latest_commit` values and no duplicate repository-month rows.
9. Ran a small SonarQube scan smoke test using one treatment repository and three months.
10. Confirmed that `proc_scripts/run_sonarqube_v2.py` successfully scanned historical commits and collected SonarQube metrics.
11. Started the full treatment-side SonarQube scan using `NUM_PROCESSES=1`.

Key Results:

1. Final panel QC summary:

   * Main unbalanced panel: 6,281 rows, 380 treated repositories, 393 control repositories.
   * Main window-completed panel: 12,270 rows, 380 treated repositories, 447 control repositories.
   * Strict 1:3 unbalanced panel: 5,518 rows, 337 treated repositories, 354 control repositories.
   * Strict 1:3 window-completed panel: 10,986 rows, 337 treated repositories, 404 control repositories.
   * Control rows without provenance: 0 for all panels.
2. Full SonarQube input generation:

   * Treatment input: 5,028 rows, 380 repositories, 2024-01 to 2025-08.
   * Control input: 7,242 rows, 447 repositories, 2024-01 to 2025-08.
   * Missing `latest_commit`: 0.
   * Duplicate repository-month rows: 0.
3. SonarQube smoke scan:

   * Repository: `zzfn/zzf`.
   * Months scanned: 2024-01, 2024-02, 2024-03.
   * Metrics were successfully collected for all three months.
4. Full treatment SonarQube scan:

   * Started with `NUM_PROCESSES=1`.
   * Input rows: 5,028.
   * Repositories: 380.
   * Incremental save mode is enabled.
   * The scan is currently processing treatment repositories and successfully collecting monthly metrics.

Errors / Issues:

1. A 404 error appeared when checking whether a SonarQube analysis already existed for a new project key. This is expected when the project/version has not yet been created in SonarQube.
2. The full SonarQube scan is expected to be long-running. Based on the smoke test speed, the treatment scan may take many hours.
3. SonarQube and Elasticsearch stability should be monitored. We are using `NUM_PROCESSES=1` for safety.

Interpretation:
The JS/TS matched DiD panel construction is complete and ready for quality-metric integration. The SonarQube input-preparation step is reliable, and the scanner pipeline has been validated with a smoke test. The current full treatment scan is the first long-running quality-metric collection step. Once treatment scanning completes, the same process should be repeated for the control repositories.

Files Generated:

1. `tmp_jsts_test/data/jsts_did_final/panel_qc_summary.csv`
2. `proc_scripts/prepare_sonarqube_input.py`
3. `run9a-create-jsts-sonarqube-input.sh`
4. `tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/ts_repos_monthly.csv`
5. `tmp_jsts_test/data/jsts_sonarqube_main/control/data/ts_repos_monthly.csv`
6. `tmp_jsts_test/data/jsts_sonarqube_main/sonarqube_input_summary.csv`
7. `tmp_jsts_test/data/jsts_sonarqube_scan_smoke/data/ts_repos_monthly.csv`
8. `tmp_jsts_test/data/jsts_sonarqube_scan_smoke/data/ts_repos_monthly_scanned.csv`
9. `run9b-sonarqube-jsts.sh`
10. `run9b1-sonarqube-jsts-treatment.sh`
11. `run9b2-sonarqube-jsts-control.sh`

Commands Used:

```bash
./run8e2-summarize-jsts-panels.sh

MAX_TREATMENT_REPOS=2 MAX_CONTROL_REPOS=2 ./run9a-create-jsts-sonarqube-input.sh

SONAR_ROOT=tmp_jsts_test/data/jsts_sonarqube_main \
MAX_TREATMENT_REPOS=0 \
MAX_CONTROL_REPOS=0 \
./run9a-create-jsts-sonarqube-input.sh

python proc_scripts/run_sonarqube_v2.py \
  --aggregation month \
  --input-file tmp_jsts_test/data/jsts_sonarqube_scan_smoke/data/ts_repos_monthly.csv \
  --output-file tmp_jsts_test/data/jsts_sonarqube_scan_smoke/data/ts_repos_monthly_scanned.csv \
  --clone-dir ../ai_code_complexity_study_jsts_repo_dataset \
  --num-processes 1 \
  --incremental-save

NUM_PROCESSES=1 ./run9b1-sonarqube-jsts-treatment.sh
```

Next Steps:

1. Let the full treatment SonarQube scan continue.
2. Monitor the log and SonarQube Docker resource usage periodically.
3. After treatment scanning completes, run the control-side SonarQube scan with `NUM_PROCESSES=1`.
4. Check metric coverage for both treatment and control scanned outputs.
5. Merge SonarQube metrics back into the final matched DiD panels.
6. Prepare activity and quality outcome datasets for DiD estimation.
