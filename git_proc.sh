#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

# Print current git status for visibility
git status

# Local variable assignment (Bash requires lowercase 'local' inside functions, 
# but for a standalone script, standard variables are preferred)
ADDITIONAL_COMMENT="$1"

# Stage all changes
git add .

# Check if there are staged changes to commit
if ! git diff --cached --quiet; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
    
    if [ -n "$ADDITIONAL_COMMENT" ]; then
        git commit -m "$TIMESTAMP: $ADDITIONAL_COMMENT"
    else
        # -m "Updated" serves as a detailed description/body underneath the timestamp subject line
        git commit -m "$TIMESTAMP" -m "Updated"
    fi
else
    echo "Nothing to commit."
fi

# Pull latest changes securely, then push
git pull --rebase origin main
git push