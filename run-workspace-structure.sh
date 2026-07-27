#!/usr/bin/env bash

# Print a tree-like view while pruning selected directories.
print_repo_python_tree() {
    find repo_python \
        \( \
            -type d \
            \( \
                -name '__pycache__' \
                -o -name 'bak' \
                -o -name 'compare-[0-9]*' \
            \) \
            -prune \
        \) \
        -o \
        \( \
            -type d \
            -name 'python_snapshots' \
            -print \
            -prune \
        \) \
        -o \
        \( \
            -type d \
            -name 'commit_function_sources' \
            -print \
            -prune \
        \) \
        -o \
        -print |
        LC_ALL=C sort |
        awk -F/ '
            NR == 1 {
                print $0
                next
            }
            {
                indent = ""
                for (i = 2; i < NF; i++) {
                    indent = indent "    "
                }
                print indent "|-- " $NF
            }
        '
}

echo
echo "============== [ data ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' data

echo
echo "============== [ data_baseline_backup ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' data_baseline_backup

echo
echo "============== [ repo_python ] =============="
print_repo_python_tree

echo
echo "============== [ proc_r ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' proc_r

echo
echo "============== [ proc_scripts ] =============="
tree --noreport -I '__pycache__|bak|bak2|compare-[0-9]*' proc_scripts

echo
echo "============== [ proc_sh ] =============="
tree --noreport -I '__pycache__|bak|bak2|compare-[0-9]*' proc_sh

echo
echo "============== [ run-py-* FILES ] =============="
find . -maxdepth 1 -type f -name 'run-py-*' -printf '%f\n' | sort