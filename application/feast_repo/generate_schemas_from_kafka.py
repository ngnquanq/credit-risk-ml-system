#!/usr/bin/env python3
"""
Generate Feast schema JSON files by sampling Kafka topics.

This script consumes messages from each Kafka topic and infers
the schema dynamically from the message structure.

Usage:
    python generate_schemas_from_kafka.py --bootstrap localhost:9092
    python generate_schemas_from_kafka.py --bootstrap broker:29092 --samples 20
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter
from kafka import KafkaConsumer


def infer_feast_type(value: Any) -> str:
    """Infer Feast type from Python value."""
    if value is None:
        return None  # Will be determined by other non-null samples
    elif isinstance(value, bool):
        return "Int64"  # Feast doesn't have Bool, use Int64
    elif isinstance(value, int):
        return "Int64"
    elif isinstance(value, float):
        return "Float32"
    elif isinstance(value, str):
        return "String"
    else:
        return "String"  # Default fallback


def sample_kafka_topic(
    bootstrap_servers: str,
    topic: str,
    num_samples: int = 10,
    timeout_ms: int = 10000
) -> List[Dict[str, Any]]:
    """Sample messages from a Kafka topic."""
    print(f"📥 Sampling {num_samples} messages from topic: {topic}")

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers.split(','),
        auto_offset_reset='earliest',  # Start from beginning
        enable_auto_commit=False,
        consumer_timeout_ms=timeout_ms,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else {}
    )

    samples = []
    try:
        for message in consumer:
            if len(samples) >= num_samples:
                break
            samples.append(message.value)
    except Exception as e:
        print(f"⚠ Error sampling topic {topic}: {e}")
    finally:
        consumer.close()

    print(f"✓ Collected {len(samples)} samples from {topic}")
    return samples


def infer_schema_from_samples(samples: List[Dict[str, Any]], exclude_fields: List[str] = None) -> List[Dict[str, str]]:
    """Infer schema from multiple message samples.

    Takes the union of all fields across samples and infers types
    from non-null values.
    """
    exclude_fields = exclude_fields or []
    field_types = {}  # field_name -> Counter of types

    for sample in samples:
        for field_name, value in sample.items():
            if field_name in exclude_fields:
                continue

            if field_name not in field_types:
                field_types[field_name] = Counter()

            feast_type = infer_feast_type(value)
            if feast_type:  # Skip None values
                field_types[field_name][feast_type] += 1

    # Build schema: pick most common type for each field
    schema = []
    for field_name, type_counts in sorted(field_types.items()):
        # Get most common type (or default to String if all nulls)
        if type_counts:
            most_common_type = type_counts.most_common(1)[0][0]
        else:
            most_common_type = "String"

        schema.append({
            "name": field_name,
            "type": most_common_type
        })

    return schema


def main():
    parser = argparse.ArgumentParser(description="Generate Feast schemas from Kafka topics")
    parser.add_argument(
        "--bootstrap",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        help="Kafka bootstrap servers (default: localhost:9092)"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of messages to sample per topic (default: 10)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10000,
        help="Consumer timeout in milliseconds (default: 10000)"
    )

    args = parser.parse_args()

    feast_dir = Path(__file__).parent

    # Topics to sample
    topics_config = [
        {
            "name": "application_features",
            "topic": os.getenv("FEAST_TOPIC_APP_FEATURES", "hc.application_features"),
            "output_file": feast_dir /  "feature_schema/application_schema.json",
            "exclude_fields": ["ts"],  # Timestamp field, not a feature
        },
        {
            "name": "external_features",
            "topic": os.getenv("FEAST_TOPIC_EXTERNAL", "hc.application_ext"),
            "output_file": feast_dir / "feature_schema/external_schema.json",
            "exclude_fields": ["ts"],
        },
        {
            "name": "dwh_features",
            "topic": os.getenv("FEAST_TOPIC_DWH", "hc.application_dwh"),
            "output_file": feast_dir / "feature_schema/dwh_schema.json",
            "exclude_fields": ["ts"],
        },
    ]

    print(f"🔍 Connecting to Kafka: {args.bootstrap}\n")

    for config in topics_config:
        print(f"\n{'='*60}")
        print(f"Processing: {config['name']}")
        print(f"{'='*60}")

        # Sample messages from Kafka
        samples = sample_kafka_topic(
            bootstrap_servers=args.bootstrap,
            topic=config["topic"],
            num_samples=args.samples,
            timeout_ms=args.timeout
        )

        if not samples:
            print(f"⚠ No samples collected from {config['topic']} - skipping")
            continue

        # Infer schema
        schema = infer_schema_from_samples(samples, exclude_fields=config["exclude_fields"])

        # Write to JSON (ensure parent directory exists)
        output_file = config["output_file"]
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(schema, f, indent=2)

        print(f"✅ Generated {output_file} with {len(schema)} fields")
        print(f"   Sample fields: {', '.join(s['name'] for s in schema[:5])}...")

    print("\n" + "="*60)
    print("✅ Schema generation complete!")
    print("="*60)


if __name__ == "__main__":
    main()
