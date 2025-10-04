#!/usr/bin/env python3
"""Check requirements.txt in MinIO v12"""
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9005',
    aws_access_key_id='minio_user',
    aws_secret_access_key='minio_password'
)

key = "bentos/credit_risk_model/v12/env/python/requirements.txt"
print(f"Fetching {key}...")
print("=" * 60)

obj = s3.get_object(Bucket='bentoml-bundles', Key=key)
content = obj['Body'].read().decode('utf-8')

print(content)

print("\n" + "=" * 60)
print("CHECKING FOR CRITICAL PACKAGES:")
print("=" * 60)

for line in content.split('\n'):
    if any(pkg in line.lower() for pkg in ['feast', 'protobuf', 'mlflow']):
        print(f">>> {line}")
