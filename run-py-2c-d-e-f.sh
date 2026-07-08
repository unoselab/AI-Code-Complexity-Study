#!/usr/bin/env bash
set -euo pipefail

mkdir -p repo_python/did_final_pyv2_paper_overlap

cp -p repo_python/did_final/panel_event_matched_strict.csv \
  repo_python/did_final_pyv2_paper_overlap/panel_event_matched_strict.csv

PANEL_VARIANT=strict \
DID_DIR=repo_python/did_final_pyv2_paper_overlap \
TREATMENT_METRICS=repo_python/sonarqube_input/strict/treatment/data/ts_repos_monthly_scanned_pyv2_paper_overlap.csv \
CONTROL_METRICS=repo_python/sonarqube_input/strict/control/data/ts_repos_monthly_scanned_pyv2_paper_overlap.csv \
bash run-py-2c-merge-sonarqube-panel.sh

PANEL_VARIANT=strict \
DID_DIR=repo_python/did_final_pyv2_paper_overlap \
bash run-py-2d-check-sonarqube-panels.sh

PANEL_VARIANT=strict \
DID_DIR=repo_python/did_final_pyv2_paper_overlap \
bash run-py-2e-prepare-quality-did-input.sh

PANEL_VARIANT=strict \
DID_DIR=repo_python/did_final_pyv2_paper_overlap \
bash run-py-2f-did-borusyak-quality.sh