#!/usr/bin/env python3
"""Check what's actually in MinIO for v12"""
import boto3

# Port-forward first: kubectl port-forward -n model-serving svc/serving-minio 9000:9000

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9005',
    aws_access_key_id='minio_user',
    aws_secret_access_key='minio_password'
)

print("Checking v12 in MinIO...")
print("=" * 60)

prefix = "bentos/credit_risk_model/v12/"
response = s3.list_objects_v2(Bucket='bentoml-bundles', Prefix=prefix)

if 'Contents' in response:
    print(f"✅ Found {len(response['Contents'])} files in {prefix}:")
    for obj in response['Contents'][:10]:  # Show first 10
        print(f"   {obj['Key']} ({obj['Size']} bytes)")

    # Check if bento.yaml exists
    bento_yaml_key = f"{prefix}bento.yaml"
    for obj in response['Contents']:
        if obj['Key'] == bento_yaml_key:
            print(f"\n📄 Downloading bento.yaml to check version...")
            obj_data = s3.get_object(Bucket='bentoml-bundles', Key=bento_yaml_key)
            content = obj_data['Body'].read().decode('utf-8')
            print(content[:500])  # First 500 chars
            break
else:
    print(f"❌ NO FILES FOUND in {prefix}")
    print("\nLet's check what's actually there:")
    response = s3.list_objects_v2(Bucket='bentoml-bundles', Prefix='bentos/credit_risk_model/', Delimiter='/')
    print("\nVersions found:")
    for prefix_obj in response.get('CommonPrefixes', []):
        print(f"   {prefix_obj['Prefix']}")
