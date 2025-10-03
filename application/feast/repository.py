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
    fs = FeatureStore(repo_path=str(repo_dir))
    fs.apply([
        customer,
        fv_application_features,
        fv_external,
        fv_dwh,
        realtime_scoring_v1,
    ])


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
