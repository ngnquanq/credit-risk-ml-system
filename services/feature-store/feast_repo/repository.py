from feast import FeatureStore
from pathlib import Path
import os
# Support both package and direct module imports
try:
    from .entities import customer  # type: ignore
    from .feature_views import (  # type: ignore
        fv_application_features,
        fv_external,
        fv_dwh,
    )
    from .feature_services import realtime_scoring_v1  # type: ignore
except Exception:  # pragma: no cover
    from entities import customer  # type: ignore
    from feature_views import (  # type: ignore
        fv_application_features,
        fv_external,
        fv_dwh,
    )
    from feature_services import realtime_scoring_v1  # type: ignore
# from generate_config import generate as generate_feast_config  # File removed


def apply():
    # Use the existing feature_store.yaml configuration
    repo_dir = Path(__file__).parent.resolve()
    # generate_feast_config(path=str(repo_dir / "feature_store.yaml"))  # File removed
    # Ensure dummy Parquet files exist for batch FileSources referenced by older Feast
    def ensure_dummy_parquet(path: str, ts_col: str = "ts") -> None:
        try:
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                import pyarrow as pa
                import pyarrow.parquet as pq
                table = pa.table({ts_col: pa.array([], type=pa.int64())})
                pq.write_table(table, path)
        except Exception:
            # Best-effort safeguard
            pass

    ensure_dummy_parquet("/tmp/application_features.parquet", os.getenv("FEAST_TS_FIELD_APP", "ts"))
    ensure_dummy_parquet("/tmp/external_features.parquet", os.getenv("FEAST_TS_FIELD_EXT", "ts"))
    ensure_dummy_parquet("/tmp/dwh_features.parquet", os.getenv("FEAST_TS_FIELD_DWH", "ts"))

    # Clean up any old local registry files that might conflict with S3
    local_registry_path = repo_dir / "data" / "registry.db"
    if local_registry_path.exists():
        print(f"⚠️  Removing old local registry: {local_registry_path}")
        local_registry_path.unlink()

    fs = FeatureStore(repo_path=str(repo_dir))

    # Teardown first to clear any stale/conflicting feature view type registrations
    # (e.g., old FeatureView entries that conflict with current StreamFeatureViews)
    try:
        print("🧹 Tearing down stale registry entries before apply...")
        fs.teardown()
        print("✅ Teardown complete")
    except Exception as e:
        print(f"⚠️  Teardown skipped (ok on first run): {e}")

    # Re-init FeatureStore after teardown to get fresh registry handle
    fs = FeatureStore(repo_path=str(repo_dir))
    fs.apply([
        customer,
        fv_application_features,
        fv_external,
        fv_dwh,
        realtime_scoring_v1,
    ])

    # For S3 registries: Explicitly serialize and upload the full registry proto
    # This ensures the registry is properly synchronized to S3 for other services (e.g., BentoML)
    registry_path = os.getenv("FEAST_REGISTRY_URI", "")
    if registry_path.startswith("s3://"):
        print("📤 Syncing full registry proto to S3...")
        try:
            import boto3
            from urllib.parse import urlparse

            # Parse S3 path
            parsed = urlparse(registry_path)
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")

            # Get S3 endpoint configuration
            s3_endpoint = os.getenv("FEAST_S3_ENDPOINT_URL") or os.getenv("AWS_S3_ENDPOINT")

            # Serialize the full registry proto
            registry_proto = fs.registry.proto()
            serialized = registry_proto.SerializeToString()

            # Upload to S3
            s3_client = boto3.client(
                "s3",
                endpoint_url=s3_endpoint,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )

            s3_client.put_object(Bucket=bucket, Key=key, Body=serialized)

            # Verify upload
            obj_info = s3_client.head_object(Bucket=bucket, Key=key)
            print(f"✅ Registry synced to S3: {registry_path}")
            print(f"   Size: {obj_info['ContentLength']:,} bytes")
            print(f"   Stream feature views: {len(fs.list_stream_feature_views())}")
            print(f"   Total features: {sum(len(sfv.schema) for sfv in fs.list_stream_feature_views())}")

        except Exception as e:
            print(f"⚠️  Failed to sync registry to S3: {e}")
            print("   Registry may not be accessible to other services")
            # Don't fail the apply operation, just warn
    else:
        print(f"✅ Registry applied to local path: {registry_path or 'default'}")


def start_stream_processor():
    """Start the Kafka stream processor to materialize data to online store."""
    from stream_processor import FeastStreamProcessor
    processor = FeastStreamProcessor(repo_path=".")
    processor.start()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stream":
        start_stream_processor()
    else:
        apply()
