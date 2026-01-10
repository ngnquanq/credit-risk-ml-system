#!/usr/bin/env python3
"""
Simple script to promote a model version to production in MLflow.

This promotes an existing model version to Production stage, which triggers
KServe to deploy a new predictor pod with the promoted version number.

Usage:
    python promote_model.py                    # Promote latest version
    python promote_model.py --version 12       # Promote specific version
    python promote_model.py --list             # List all versions
"""

import argparse
import requests
import sys
from typing import Optional


def get_latest_version(mlflow_url: str, model_name: str) -> Optional[int]:
    """Get the latest version number for a model."""
    try:
        # Get all versions of the model
        response = requests.get(
            f"{mlflow_url}/api/2.0/mlflow/model-versions/search",
            params={"filter": f"name='{model_name}'"}
        )
        response.raise_for_status()

        versions = response.json().get("model_versions", [])
        if not versions:
            print(f"❌ No versions found for model '{model_name}'")
            return None

        # Get the highest version number
        version_numbers = [int(v["version"]) for v in versions]
        latest = max(version_numbers)

        print(f"✓ Found {len(version_numbers)} versions for '{model_name}'")
        print(f"  Latest version: {latest}")
        return latest

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching model versions: {e}")
        return None


def get_current_production_version(mlflow_url: str, model_name: str) -> Optional[int]:
    """Get the current Production version."""
    try:
        response = requests.get(
            f"{mlflow_url}/api/2.0/mlflow/model-versions/search",
            params={"filter": f"name='{model_name}'"}
        )
        response.raise_for_status()

        versions = response.json().get("model_versions", [])
        for v in versions:
            if v.get("current_stage") == "Production":
                return int(v["version"])

        print(f"ℹ️  No version currently in Production stage")
        return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching current Production version: {e}")
        return None


def list_model_versions(mlflow_url: str, model_name: str):
    """List all versions with their current stages."""
    try:
        response = requests.get(
            f"{mlflow_url}/api/2.0/mlflow/model-versions/search",
            params={"filter": f"name='{model_name}'"}
        )
        response.raise_for_status()

        versions = response.json().get("model_versions", [])
        if not versions:
            print(f"No versions found for model '{model_name}'")
            return

        print(f"\n📋 All versions of '{model_name}':")
        print(f"{'Version':<10} {'Stage':<15} {'Run ID':<40}")
        print("-" * 70)

        # Sort by version number (descending)
        versions_sorted = sorted(versions, key=lambda x: int(x["version"]), reverse=True)

        for v in versions_sorted:
            version = v["version"]
            stage = v.get("current_stage", "None")
            run_id = v.get("run_id", "N/A")[:36]
            marker = " ← PRODUCTION" if stage == "Production" else ""
            print(f"{version:<10} {stage:<15} {run_id:<40}{marker}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error listing model versions: {e}")


def transition_model_stage(
    mlflow_url: str,
    model_name: str,
    version: int,
    stage: str = "Production",
    archive_existing: bool = True
):
    """Transition a model version to Production stage."""
    try:
        payload = {
            "name": model_name,
            "version": str(version),
            "stage": stage,
            "archive_existing_versions": archive_existing
        }

        print(f"\n🚀 Promoting model '{model_name}' version {version} to {stage}...")

        response = requests.post(
            f"{mlflow_url}/api/2.0/mlflow/model-versions/transition-stage",
            json=payload
        )
        response.raise_for_status()

        print(f"✅ Successfully promoted version {version} to {stage}!")

        if archive_existing:
            print(f"   Previous {stage} versions automatically archived")

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Error promoting model: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Promote a model version to Production in MLflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python promote_model.py --list              # List all versions
  python promote_model.py                     # Promote latest version
  python promote_model.py --version 13        # Promote specific version
  python promote_model.py --current-plus-1    # Promote current + 1
        """
    )
    parser.add_argument(
        "--model-name",
        default="credit_risk_model",
        help="Name of the model (default: credit_risk_model)"
    )
    parser.add_argument(
        "--version",
        type=int,
        help="Version number to promote"
    )
    parser.add_argument(
        "--current-plus-1",
        action="store_true",
        help="Promote current Production version + 1"
    )
    parser.add_argument(
        "--mlflow-url",
        default="http://localhost:5001",
        help="MLflow tracking server URL (default: http://localhost:5001)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all model versions and exit"
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't archive existing Production versions"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    # List versions if requested
    if args.list:
        list_model_versions(args.mlflow_url, args.model_name)
        return 0

    # Determine version to promote
    version = args.version

    if args.current_plus_1:
        current = get_current_production_version(args.mlflow_url, args.model_name)
        if current is None:
            print("❌ Cannot determine current Production version")
            return 1
        version = current + 1
        print(f"ℹ️  Current Production: v{current}")
        print(f"ℹ️  Will promote: v{version}")

    if version is None:
        print("No version specified, fetching latest version...")
        version = get_latest_version(args.mlflow_url, args.model_name)
        if version is None:
            return 1

    # Show current state
    print("\n" + "="*70)
    print("CURRENT STATE:")
    print("="*70)
    list_model_versions(args.mlflow_url, args.model_name)

    # Confirm promotion
    print("\n" + "="*70)
    print("PROMOTION PLAN:")
    print("="*70)
    print(f"   Model: {args.model_name}")
    print(f"   Version: {version}")
    print(f"   Stage: Production")
    print(f"   Archive existing: {not args.no_archive}")
    print("="*70)

    if not args.yes:
        response = input("\nProceed with promotion? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Aborted by user")
            return 1

    # Promote the model
    success = transition_model_stage(
        args.mlflow_url,
        args.model_name,
        version,
        "Production",
        archive_existing=not args.no_archive
    )

    if success:
        print("\n" + "="*70)
        print("✅ MODEL PROMOTION COMPLETE!")
        print("="*70)
        print(f"\nKServe will now deploy a new predictor pod: credit-risk-v{version}-predictor")
        print(f"\nNext steps:")
        print(f"  1. Wait ~1-2 minutes for KServe to detect and deploy new pod")
        print(f"  2. Check pod status:")
        print(f"     kubectl get pods -n kserve | grep credit-risk-v{version}")
        print(f"  3. Monitor deployment:")
        print(f"     kubectl logs -n kserve -l serving.kserve.io/inferenceservice=credit-risk-v{version} --tail=100 -f")
        print(f"  4. Once running, check logs for feature mapping debug output")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
