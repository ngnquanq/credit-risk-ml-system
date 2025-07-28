
1. Add IAP
gcloud services enable iap.googleapis.com
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member=user:YOUR_EMAIL@example.com --role=roles/iap.tunnelResourceAccessor
