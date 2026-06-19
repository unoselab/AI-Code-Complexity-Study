gcloud auth list
gcloud config list

echo "GOOGLE CLOUD PROJECT_ID=se-project-438721"
echo 

export PROJECT_ID=se-project-438721

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

gcloud auth application-default set-quota-project "$PROJECT_ID"

gcloud services enable bigquery.googleapis.com --project "$PROJECT_ID"

bq query \
  --project_id="$PROJECT_ID" \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT COUNT(*) FROM `githubarchive.day.20250101`'
