#!/usr/bin/env bash
set -euo pipefail

# Run Python SonarQube scan for control repo-month inputs.
# Use PANEL_VARIANT=flexible or PANEL_VARIANT=strict.
# Usage:
#       PANEL_VARIANT=strict    NUM_PROCESSES=1 bash run-py-2b2-sonarqube-control.sh
#       PANEL_VARIANT=flexible  NUM_PROCESSES=1 bash run-py-2b2-sonarqube-control.sh
# 
LANGUAGE_PROFILE=python TARGET=control ./run-py-2b-sonarqube-scan.sh
