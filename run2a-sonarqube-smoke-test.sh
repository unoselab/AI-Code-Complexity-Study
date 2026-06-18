#!/usr/bin/env bash
set -euo pipefail

echo "Step 1: SonarQube connection test"
python proc_scripts/test_sonarqube_connection.py
echo

echo "Step 2: Tiny project scan test"
python proc_scripts/test_sonarqube_scan.py
echo

echo "Step 3: Tiny project metrics API test"
python proc_scripts/test_sonarqube_metrics.py
echo

echo "Step 4: Tiny project issues API test"
python proc_scripts/test_sonarqube_tiny_issues.py
echo

echo "SonarQube smoke test completed successfully."
