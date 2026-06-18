#!/usr/bin/env bash
set -euo pipefail

# Wrapper for testing a larger repository.
#
# Example:
#   ./run2b-sonarqube-smoke-test.sh OWNER/REPO
#   ./run2b-sonarqube-smoke-test.sh OWNER/REPO --month 2025-03
#
# This delegates to run2a-sonarqube-smoke-test.sh.

if [[ $# -lt 1 ]]; then
  echo "Usage:"
  echo "  ./run2b-sonarqube-smoke-test.sh OWNER/REPO [additional run2a options]"
  echo
  echo "Example:"
  echo "  ./run2b-sonarqube-smoke-test.sh ericzakariasson/uber-eats-mcp-server"
  echo "  ./run2b-sonarqube-smoke-test.sh OWNER/REPO --month 2025-03"
  exit 1
fi

REPO_NAME="$1"
REPO_NAME="xzq-xu/jvm-mcp-server"
shift

exec ./run2a-sonarqube-smoke-test.sh --repo "${REPO_NAME}" "$@"
