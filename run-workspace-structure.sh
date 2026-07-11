echo
echo "============== [ data ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' data

echo
echo "============== [ data_baseline_backup ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' data_baseline_backup

echo
echo "============== [ repo_python ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' repo_python

echo
echo "============== [ proc_r ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' proc_r

echo
echo "============== [ proc_scripts ] =============="
tree --noreport -I '__pycache__|bak|compare-[0-9]*' proc_scripts

echo
echo "============== [ run-py-* FILES ] =============="
find . -maxdepth 1 -type f -name 'run-py-*' -printf '%f\n' | sort

