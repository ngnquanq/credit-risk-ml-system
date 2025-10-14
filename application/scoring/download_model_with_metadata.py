#!/usr/bin/env python3
"""
Download model and feast_metadata.yaml from MLflow for Bento packaging.

Usage:
    python download_model_with_metadata.py \
        --model-uri "models:/credit_risk_model/Production" \
        --output-dir ./bundle

This script:
1. Downloads the model from MLflow
2. Downloads feast_metadata.yaml from the same run
3. Saves both to the output directory for Bento packaging
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path


def download_model_and_metadata(model_uri: str, output_dir: str) -> None:
    """Download model and metadata from MLflow."""
    try:
        import mlflow
        import mlflow.sklearn
        import yaml
    except ImportError as e:
        print(f"Error: {e}")
        print("Install dependencies: pip install mlflow pyyaml")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"📥 Downloading model from MLflow: {model_uri}")

    # Download model
    model_path = output_path / "model.joblib"
    try:
        model = mlflow.sklearn.load_model(model_uri)
        import joblib
        joblib.dump(model, model_path)
        print(f"✓ Model saved to {model_path}")
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        sys.exit(1)

    # Get run_id to download feast_metadata.yaml
    try:
        import re
        client = mlflow.tracking.MlflowClient()

        # Parse model URI
        match = re.match(r"models:/([^/]+)/([^/]+)$", model_uri.strip())
        if not match:
            print(f"⚠ Cannot parse model URI: {model_uri}")
            print("  Skipping feast_metadata.yaml download")
            return

        model_name, stage_or_version = match.groups()

        # Resolve to specific version
        if stage_or_version.isalpha():
            # It's a stage name
            versions = client.get_latest_versions(model_name, [stage_or_version])
            if not versions:
                print(f"⚠ No versions found for {model_name}/{stage_or_version}")
                return
            model_version = versions[0]
        else:
            # It's a version number
            model_version = client.get_model_version(model_name, stage_or_version)

        run_id = model_version.run_id
        print(f"📋 Found run_id: {run_id}")

        # Download feast_metadata.yaml
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                artifact_path = client.download_artifacts(run_id, "feast_metadata.yaml", tmpdir)
                metadata_path = output_path / "feast_metadata.yaml"

                with open(artifact_path, "r") as src, open(metadata_path, "w") as dst:
                    metadata = yaml.safe_load(src)
                    yaml.dump(metadata, dst)

                print(f"✓ feast_metadata.yaml saved to {metadata_path}")
                print(f"  Features: {metadata.get('num_features', 'unknown')}")
                print(f"  Training date: {metadata.get('training_date', 'unknown')}")

            except Exception as e:
                print(f"⚠ Failed to download feast_metadata.yaml: {e}")
                print("  Scoring will fall back to feature_registry.py")

    except Exception as e:
        print(f"⚠ Failed to get model metadata: {e}")
        print("  Model will work but may have feature mismatch")


def main():
    parser = argparse.ArgumentParser(description="Download MLflow model with metadata")
    parser.add_argument(
        "--model-uri",
        required=True,
        help="MLflow model URI (e.g., models:/credit_risk_model/Production)",
    )
    parser.add_argument(
        "--output-dir",
        default="./bundle",
        help="Output directory for model and metadata (default: ./bundle)",
    )

    args = parser.parse_args()

    # Validate MLflow connection
    try:
        import mlflow
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", mlflow.get_tracking_uri())
        print(f"🔗 MLflow Tracking URI: {tracking_uri}")
    except Exception as e:
        print(f"❌ Failed to connect to MLflow: {e}")
        sys.exit(1)

    download_model_and_metadata(args.model_uri, args.output_dir)
    print("\n✅ Done! You can now build the Bento with: bentoml build")


if __name__ == "__main__":
    main()
