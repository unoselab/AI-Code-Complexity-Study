#!/usr/bin/env bash
set -euo pipefail

# Small-batch SonarQube smoke test using three original-paper repositories.
#
# This script does NOT modify the original data/ts_repos_monthly.csv.
# It writes temporary batch input to:
#   tmp_sonar_batch/data/ts_repos_monthly.csv
#
# It creates a safe patched copy:
#   proc_scripts/run_sonarqube_small_batch_test.py
#
# Target repos:
#   TheSethRose/Agent-Chat
#   utensils/mcp-nixos
#   nextml-code/pytorch-datastream

bash ./run2c-sonarqube-small-batch-test.sh