#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Configuration variables
export PROJECT_ID="se-project-438721"
MAX_BYTES=1073741824  # 1 GB limit

# 2. Store the SQL query in a reusable variable
SQL_QUERY=$(cat << 'EOF'
SELECT type, COUNT(*) AS n
FROM `githubarchive.day.20250101`
GROUP BY type
ORDER BY n DESC
EOF
)

# Helper function to print what it's doing and then execute it
run_bq_command() {
    echo -e "\n============== [ RUNNING BQ COMMAND ] =============="
    echo "bq query --project_id=$PROJECT_ID $@"
    echo "----------------------------------------------------"
    
    # Execute the actual bq command with whatever flags were passed
    bq query --project_id="$PROJECT_ID" --use_legacy_sql=false "$@" "$SQL_QUERY"
}

# --- Execution ---

# Step 1: Perform the Dry Run
run_bq_command --dry_run

# Step 2: Perform the Actual Run with byte protection
run_bq_command --maximum_bytes_billed="$MAX_BYTES"
