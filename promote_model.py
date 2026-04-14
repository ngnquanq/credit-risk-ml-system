#!/usr/bin/env python3
"""
Promote a model version to Production in MLflow (3.x compatible).

Sets a model version tag `stage=Production` which the MLflow Watcher poller
detects to trigger the Bento build pipeline. Optionally sets the MLflow 3.x
`champion` alias for UI visibility.

Usage:
    python promote_model.py                    # Promote latest version
    python promote_model.py --version 12       # Promote specific version
    python promote_model.py --list             # List all versions
    python promote_model.py --current-plus-1   # Promote current + 1

Requires:
    pip install mlflow
    export MLFLOW_TRACKING_URI=http://localhost:5001  # or pass --mlflow-url
"""

import argparse
import sys
from typing import Optional

from mlflow.tracking import MlflowClient


STAGE_TAG_KEY = "stage"
STAGE_PRODUCTION = "Production"
STAGE_ARCHIVED = "Archived"


def _get_stage(version) -> str:
    """Get the stage of a model version via tags (MLflow 3.x compatible)."""
    tags = version.tags or {}
    return tags.get(STAGE_TAG_KEY, "None")


def _is_production(version) -> bool:
    return _get_stage(version).lower() == STAGE_PRODUCTION.lower()


def get_all_versions(client: MlflowClient, model_name: str):
    """Get all versions for a model, sorted descending by version number."""
    versions = client.search_model_versions(f"name='{model_name}'")
    return sorted(versions, key=lambda v: int(v.version), reverse=True)


def get_latest_version(client: MlflowClient, model_name: str) -> Optional[int]:
    """Get the latest (highest) version number."""
    versions = get_all_versions(client, model_name)
    if not versions:
        print(f"No versions found for model '{model_name}'")
        return None

    latest = int(versions[0].version)
    print(f"Found {len(versions)} versions for '{model_name}'")
    print(f"  Latest version: {latest}")
    return latest


def get_current_production_version(client: MlflowClient, model_name: str) -> Optional[int]:
    """Get the current Production version (by tag)."""
    versions = get_all_versions(client, model_name)
    for v in versions:
        if _is_production(v):
            return int(v.version)

    print("No version currently tagged as Production")
    return None


def list_model_versions(client: MlflowClient, model_name: str):
    """List all versions with their stage tags and aliases."""
    versions = get_all_versions(client, model_name)
    if not versions:
        print(f"No versions found for model '{model_name}'")
        return

    # Get aliases from registered model
    try:
        rm = client.get_registered_model(model_name)
        alias_map = {}
        for alias_info in getattr(rm, "aliases", []):
            alias_map[alias_info.version] = alias_info.alias
    except Exception:
        alias_map = {}

    print(f"\nAll versions of '{model_name}':")
    print(f"{'Version':<10} {'Stage (tag)':<15} {'Alias':<15} {'Run ID':<40}")
    print("-" * 80)

    for v in versions:
        version = v.version
        stage = _get_stage(v)
        alias = alias_map.get(version, "")
        run_id = (v.run_id or "N/A")[:36]
        marker = " <-- PRODUCTION" if _is_production(v) else ""
        print(f"{version:<10} {stage:<15} {alias:<15} {run_id:<40}{marker}")


def promote_version(
    client: MlflowClient,
    model_name: str,
    version: int,
    archive_existing: bool = True,
):
    """Promote a version to Production by setting the stage tag."""
    version_str = str(version)

    # Archive existing production versions
    if archive_existing:
        all_versions = get_all_versions(client, model_name)
        for v in all_versions:
            if _is_production(v) and v.version != version_str:
                print(f"  Archiving previous Production version {v.version}")
                client.set_model_version_tag(
                    model_name, v.version, STAGE_TAG_KEY, STAGE_ARCHIVED
                )

    # Set the stage tag to Production
    print(f"\nPromoting '{model_name}' version {version} to {STAGE_PRODUCTION}...")
    client.set_model_version_tag(
        model_name, version_str, STAGE_TAG_KEY, STAGE_PRODUCTION
    )

    # Also set the MLflow 3.x alias for UI visibility
    try:
        client.set_registered_model_alias(model_name, "champion", version_str)
        print(f"  Set alias 'champion' -> version {version}")
    except Exception as e:
        print(f"  Warning: could not set alias 'champion': {e}")

    print(f"Successfully promoted version {version} to {STAGE_PRODUCTION}!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Promote a model version to Production in MLflow (3.x compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python promote_model.py --list              # List all versions
  python promote_model.py                     # Promote latest version
  python promote_model.py --version 13        # Promote specific version
  python promote_model.py --current-plus-1    # Promote current + 1
        """,
    )
    parser.add_argument(
        "--model-name",
        default="credit_risk_model",
        help="Name of the model (default: credit_risk_model)",
    )
    parser.add_argument("--version", type=int, help="Version number to promote")
    parser.add_argument(
        "--current-plus-1",
        action="store_true",
        help="Promote current Production version + 1",
    )
    parser.add_argument(
        "--mlflow-url",
        default="http://localhost:5001",
        help="MLflow tracking server URL (default: http://localhost:5001)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List all model versions and exit"
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't archive existing Production versions",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )

    args = parser.parse_args()
    client = MlflowClient(tracking_uri=args.mlflow_url)

    # List versions if requested
    if args.list:
        list_model_versions(client, args.model_name)
        return 0

    # Determine version to promote
    version = args.version

    if args.current_plus_1:
        current = get_current_production_version(client, args.model_name)
        if current is None:
            print("Cannot determine current Production version")
            return 1
        version = current + 1
        print(f"  Current Production: v{current}")
        print(f"  Will promote: v{version}")

    if version is None:
        print("No version specified, fetching latest version...")
        version = get_latest_version(client, args.model_name)
        if version is None:
            return 1

    # Show current state
    print("\n" + "=" * 70)
    print("CURRENT STATE:")
    print("=" * 70)
    list_model_versions(client, args.model_name)

    # Show promotion plan
    print("\n" + "=" * 70)
    print("PROMOTION PLAN:")
    print("=" * 70)
    print(f"   Model: {args.model_name}")
    print(f"   Version: {version}")
    print(f"   Stage tag: {STAGE_PRODUCTION}")
    print(f"   Archive existing: {not args.no_archive}")
    print(f"   Set alias: champion -> v{version}")
    print("=" * 70)

    if not args.yes:
        response = input("\nProceed with promotion? [y/N]: ")
        if response.lower() not in ["y", "yes"]:
            print("Aborted by user")
            return 1

    # Promote
    success = promote_version(
        client, args.model_name, version, archive_existing=not args.no_archive
    )

    if success:
        print("\n" + "=" * 70)
        print("MODEL PROMOTION COMPLETE!")
        print("=" * 70)
        print(f"\nThe MLflow Watcher will detect the tag change within ~10 seconds.")
        print(f"\nNext steps:")
        print(f"  1. Watch MLflow Watcher logs:")
        print(f"     kubectl logs deployment/mlflow-watcher -n model-registry --tail=50 -f")
        print(f"  2. Watch for builder job:")
        print(f"     kubectl get jobs -n kserve -w")
        print(f"  3. Watch serving watcher:")
        print(f"     kubectl logs deployment/serving-watcher -n model-serving -c watcher --tail=50 -f")
        print(f"  4. Check InferenceService:")
        print(f"     kubectl get isvc -n kserve")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
