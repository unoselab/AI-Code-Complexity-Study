echo "python proc_scripts/analyze_repos_v2.py ..."
echo "--------------------------------------------"

python proc_scripts/analyze_repos_v2.py \
  --repos-file tmp_adoption_test/data/control_repos_to_clone_v2.csv \
  --clone-dir /home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset \
  --output-dir tmp_adoption_test/data/python_control_did_test \
  --aggregation month \
  --num-processes 1

echo "--------------------------------------------"
echo
