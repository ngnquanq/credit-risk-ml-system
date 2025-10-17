"""Debug script to check v22 feast_metadata.yaml"""
import mlflow
import yaml

mlflow.set_tracking_uri("http://localhost:5001")

# Get v22 model
client = mlflow.MlflowClient()
versions = client.search_model_versions("name='credit_risk_model'")

v22 = [v for v in versions if v.version == "22"]
if not v22:
    print("❌ Model version 22 not found")
    exit(1)

v22 = v22[0]
print(f"✓ Found v22: {v22.source}")
print(f"  Status: {v22.status}")
print(f"  Run ID: {v22.run_id}")

# Download feast_metadata.yaml
run = client.get_run(v22.run_id)
artifacts_uri = run.info.artifact_uri
print(f"\n Artifacts URI: {artifacts_uri}")

# Try to load feast_metadata
try:
    feast_metadata_path = client.download_artifacts(v22.run_id, "feast_metadata.yaml")
    with open(feast_metadata_path, 'r') as f:
        feast_metadata = yaml.safe_load(f)

    print(f"\n=== FEAST METADATA ===")
    print(f"Selected features (first 10):")
    for feat in feast_metadata.get("selected_features", [])[:10]:
        print(f"  • {feat} (type: {type(feat).__name__})")

    print(f"\nTotal features: {len(feast_metadata.get('selected_features', []))}")
    print(f"Entity key: {feast_metadata.get('entity_key')}")

    # Check case
    features = feast_metadata.get("selected_features", [])
    uppercase_count = sum(1 for f in features if f != f.lower())
    lowercase_count = sum(1 for f in features if f == f.lower())

    print(f"\n=== CASE ANALYSIS ===")
    print(f"Uppercase features: {uppercase_count}")
    print(f"Lowercase features: {lowercase_count}")

    if uppercase_count > 0:
        print(f"\n❌ FOUND UPPERCASE FEATURES!")
        print(f"Examples:")
        for feat in [f for f in features if f != f.lower()][:5]:
            print(f"  • {feat}")

except Exception as e:
    print(f"❌ Error loading feast_metadata.yaml: {e}")
