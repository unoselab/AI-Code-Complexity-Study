#!/usr/bin/env bash
set -euo pipefail

# Merge each run-py shell script with the Python source files it references.
# Python files are resolved only from ./proc_scripts.
# Merged content goes to stdout; progress messages go to stderr.
#
# Usage:
#   ./run-pyall-scripts-merge.sh > run-pyall-scripts-all.sh

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROC_DIR="${PROJECT_ROOT}/proc_scripts"
readonly IGNORED_PYTHON="extract-jsts-control-repos.py"
readonly GENERATED_SHELL="run-py-all-scripts.sh"

cd "${PROJECT_ROOT}"

if [[ ! -d "${PROC_DIR}" ]]; then
    echo "ERROR: Directory not found: ${PROC_DIR}" >&2
    exit 1
fi

shell_count=0
python_count=0

printf '#!/usr/bin/env bash\n'
printf '# Consolidated shell and Python sources generated on %s\n\n' "$(date)"

shopt -s nullglob

for shell_file in run-py-*.sh; do
    [[ -f "${shell_file}" ]] || continue
    [[ "${shell_file}" != "${GENERATED_SHELL}" ]] || continue

    shell_name="$(basename "${shell_file}")"
    echo "Processing shell script: ${shell_name}" >&2

    printf '%s\n' '###############################################################################'
    printf '# -- SHELL SCRIPT: %s --\n' "${shell_name}"
    printf '%s\n\n' '###############################################################################'
    sed '1{/^#!/d;}' "${shell_file}"
    printf '\n\n'

    shell_count=$((shell_count + 1))

    while IFS= read -r python_name; do
        [[ -n "${python_name}" ]] || continue
        [[ "${python_name}" != "${IGNORED_PYTHON}" ]] || continue

        python_file="${PROC_DIR}/${python_name}"

        if [[ ! -f "${python_file}" ]]; then
            echo "WARNING: Python script not found for ${shell_name}: proc_scripts/${python_name}" >&2
            continue
        fi

        python_count=$((python_count + 1))
        delimiter="__MERGED_PYTHON_${python_count}__"

        echo "  Including Python script: proc_scripts/${python_name}" >&2

        printf '%s\n' '###############################################################################'
        printf '# -- CALLED PYTHON SCRIPT: proc_scripts/%s --\n' "${python_name}"
        printf '%s\n\n' '###############################################################################'
        printf ": <<'%s'\n" "${delimiter}"
        cat "${python_file}"
        printf '\n%s\n\n' "${delimiter}"
    done < <(
        grep -Eo '([[:alnum:]_.-]+/)*[[:alnum:]_.-]+\.py' "${shell_file}" \
            | sed 's#^.*/##' \
            | awk '!seen[$0]++' \
            || true
    )
done

echo "Success! Shell scripts included: ${shell_count}; Python sections included: ${python_count}" >&2

