"""Debug script to print all features from Feast StreamFeatureViews."""
from feast import FeatureStore
from pathlib import Path

# Initialize Feast
feast_repo = Path(__file__).parent
fs = FeatureStore(repo_path=str(feast_repo))

print("=" * 80)
print("FEAST FEATURE REGISTRY - ALL FEATURES")
print("=" * 80)

# Get all stream feature views
stream_views = list(fs.list_stream_feature_views())

print(f"\nFound {len(stream_views)} StreamFeatureViews\n")

for sfv in stream_views:
    print(f"\n{'─' * 80}")
    print(f"View: {sfv.name}")
    print(f"{'─' * 80}")

    # Get entity columns
    entity_cols = {e.name for e in sfv.entity_columns}
    print(f"Entity columns: {entity_cols}")

    # Get all fields
    feature_fields = []
    for field in sfv.schema:
        if field.name not in entity_cols:
            feature_fields.append(field.name)

    print(f"Feature count: {len(feature_fields)}")
    print(f"\nFeatures (alphabetically sorted):")
    for i, fname in enumerate(sorted(feature_fields), 1):
        print(f"  {i:3d}. {fname}")

print(f"\n{'=' * 80}")
print("SUMMARY")
print("=" * 80)

all_features = {}
for sfv in stream_views:
    entity_cols = {e.name for e in sfv.entity_columns}
    for field in sfv.schema:
        if field.name not in entity_cols:
            if field.name not in all_features:
                all_features[field.name] = []
            all_features[field.name].append(sfv.name)

print(f"\nTotal unique features: {len(all_features)}")
print(f"\nFeatures appearing in multiple views:")
for fname, views in sorted(all_features.items()):
    if len(views) > 1:
        print(f"  • {fname}: {views}")

print(f"\n{'=' * 80}\n")
