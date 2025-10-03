#!/usr/bin/env python3
"""
Generate static schema file from ClickHouse for K8s Feast deployment.

This script connects to ClickHouse (accessible in Docker environment) and
generates a static JSON schema file that K8s Feast can use as a fallback
when ClickHouse is not accessible.

Usage:
    python generate_static_schema.py

Output:
    dwh_schema_static.json - Static schema file with all DWH fields
"""

import json
from pathlib import Path
from dwh_schema import infer_dwh_fields


def main():
    print("Connecting to ClickHouse to infer DWH schema...")

    # Infer fields from ClickHouse
    fields = infer_dwh_fields()

    if len(fields) <= 1:  # Only sk_id_curr means ClickHouse failed
        print("ERROR: ClickHouse connection failed or no fields found")
        print("Make sure ClickHouse is accessible (run from Docker environment)")
        return 1

    # Convert to serializable format
    from feast.types import Float32, Int64, String

    dtype_map = {
        Int64: 'Int64',
        Float32: 'Float32',
        String: 'String',
    }

    schema = []
    for f in fields:
        dtype_name = dtype_map.get(f.dtype, 'String')
        schema.append({
            'name': f.name,
            'dtype': dtype_name,
        })

    # Write to file
    output_file = Path(__file__).parent / 'dwh_schema_static.json'
    with open(output_file, 'w') as f:
        json.dump(schema, f, indent=2)

    print(f"✅ Successfully generated static schema")
    print(f"   File: {output_file}")
    print(f"   Fields: {len(fields)}")
    print(f"\nField breakdown:")

    # Show summary by type
    from collections import Counter
    type_counts = Counter(item['dtype'] for item in schema)
    for dtype, count in type_counts.items():
        print(f"   - {dtype}: {count} fields")

    print(f"\nThis file will be used by K8s Feast when ClickHouse is unreachable.")
    return 0


if __name__ == "__main__":
    exit(main())
