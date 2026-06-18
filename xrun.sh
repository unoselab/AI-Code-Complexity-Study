set -a
source .env
set +a

curl -s -u "$SONAR_TOKEN:" \
  "$SONAR_HOST/api/project_analyses/search?project=TheSethRose_Agent-Chat&category=VERSION&ps=100&p=1" \
  | python -m json.tool