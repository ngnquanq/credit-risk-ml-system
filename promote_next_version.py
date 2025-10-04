#!/usr/bin/env python3
"""
Promote the latest MLflow model version to trigger a new Bento build.
This will create the next version number (e.g., v9 -> v10).
"""

import mlflow
from mlflow.tracking import MlflowClient

# Configuration
MLFLOW_TRACKING_URI = "http://localhost:5002"  # Adjust if different
MODEL_NAME = "credit_risk_model"

def main():
    print("=" * 60)
    print("MLflow Model Re-Promotion Script")
    print("=" * 60)
    print()

    # Set tracking URI
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    # Get all model versions
    print(f"📦 Fetching all versions of model: {MODEL_NAME}")
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")

    if not versions:
        print(f"❌ No versions found for model: {MODEL_NAME}")
        return

    # Sort by version number
    versions = sorted(versions, key=lambda v: int(v.version), reverse=True)

    # Show current versions
    print(f"\n📋 Found {len(versions)} versions:")
    for v in versions[:5]:  # Show top 5
        stage = v.current_stage if hasattr(v, 'current_stage') else 'None'
        print(f"   Version {v.version}: {stage}")

    # Find the latest Production version
    prod_versions = [v for v in versions if v.current_stage == "Production"]

    if prod_versions:
        latest_prod = prod_versions[0]
        print(f"\n✅ Current Production version: {latest_prod.version}")
        version_to_promote = latest_prod.version
    else:
        # If no production, use the latest version
        latest = versions[0]
        print(f"\n⚠️  No Production version found. Using latest: {latest.version}")
        version_to_promote = latest.version

    # Promote to Production (force v20 to avoid Docker Hub cache)
    print(f"\n🚀 Promoting version {version_to_promote} to Production...")
    print(f"   This will trigger bento-builder to create v20 (jumping to avoid Docker Hub cache)")
    print()

    # Register as v20 by transitioning back and forth to force rebuild
    try:
        # First transition to Staging (if not already)
        try:
            client.transition_model_version_stage(
                name=MODEL_NAME,
                version=version_to_promote,
                stage="Staging"
            )
            print(f"   Moved to Staging first...")
        except:
            pass

        # Then transition to Production (triggers rebuild)
        client.transition_model_version_stage(
            name=MODEL_NAME,
            version=version_to_promote,
            stage="Production"
        )
        print(f"✅ Successfully promoted version {version_to_promote} to Production")
        print()
        print("📊 Next steps:")
        print(f"   1. mlflow-watcher will detect the promotion")
        print(f"   2. bento-builder will create the next version")
        print(f"   3. serving-watcher will deploy the new version")
        print()
        print("🔍 Monitor progress:")
        print("   kubectl logs -n model-registry -l app=mlflow-watcher -f")
        print("   kubectl get jobs -n kserve --watch")
        print()

    except Exception as e:
        print(f"❌ Error promoting model: {e}")
        print()
        print("💡 Troubleshooting:")
        print(f"   - Check MLflow is running at: {MLFLOW_TRACKING_URI}")
        print(f"   - Verify model name: {MODEL_NAME}")
        print(f"   - Try: kubectl port-forward -n model-registry svc/mlflow 5001:80")

if __name__ == "__main__":
    main()
