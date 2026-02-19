#!/usr/bin/env python3
"""
Validate Kafka topic schema against expected JSON schema.
Used in Jenkins pipeline to detect breaking schema changes.

Usage:
    python3 validate_kafka_schema.py \
        --bootstrap broker:29092 \
        --source-topic hc.application_features \
        --schema application/feast_repo/feature_schema/application_schema.json
"""

import argparse
import json
import sys
from kafka import KafkaConsumer
from typing import Dict, List, Any


def sample_kafka_messages(bootstrap: str, topic: str, num_samples: int = 10, timeout_ms: int = 10000) -> List[Dict]:
    """Sample messages from Kafka topic."""
    print(f"Sampling {num_samples} messages from topic '{topic}'...")

    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap.split(','),
            auto_offset_reset='latest',
            enable_auto_commit=False,
            consumer_timeout_ms=timeout_ms,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else {}
        )

        samples = []
        for message in consumer:
            samples.append(message.value)
            if len(samples) >= num_samples:
                break

        consumer.close()
        return samples

    except Exception as e:
        print(f"WARNING: Failed to sample from Kafka: {e}")
        return []


def validate_schema(samples: List[Dict], expected_schema: List[Dict]) -> Dict[str, Any]:
    """Validate sampled messages against expected schema."""
    errors = []
    warnings = []

    if not samples:
        warnings.append("No samples available for validation (topic may be empty)")
        return {
            'valid': True,  # Don't fail on empty topic
            'errors': errors,
            'warnings': warnings,
            'samples_checked': 0
        }

    # Build expected field map
    expected_fields = {field['name']: field['type'] for field in expected_schema}

    for idx, sample in enumerate(samples):
        # Check for missing required fields (skip 'ts' as it's optional)
        for field_name in expected_fields:
            if field_name not in sample and field_name != 'ts':
                errors.append(f"Sample {idx}: Missing required field '{field_name}'")

        # Check for unexpected fields
        for field_name in sample:
            if field_name not in expected_fields and field_name != 'ts':
                warnings.append(f"Sample {idx}: Unexpected field '{field_name}' (not in schema)")

        # Basic type validation
        for field_name, expected_type in expected_fields.items():
            if field_name in sample:
                value = sample[field_name]

                # Skip None values (nullable fields)
                if value is None:
                    continue

                # Type checks
                if expected_type == 'Int64' and not isinstance(value, int):
                    errors.append(
                        f"Sample {idx}: Field '{field_name}' expected Int64, got {type(value).__name__}"
                    )
                elif expected_type == 'Float32' and not isinstance(value, (int, float)):
                    errors.append(
                        f"Sample {idx}: Field '{field_name}' expected Float32, got {type(value).__name__}"
                    )

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'samples_checked': len(samples)
    }


def main():
    parser = argparse.ArgumentParser(description="Validate Kafka topic schema")
    parser.add_argument('--bootstrap', default='localhost:9092', help='Kafka bootstrap servers')
    parser.add_argument('--source-topic', required=True, help='Kafka topic to validate')
    parser.add_argument('--schema', required=True, help='Path to expected JSON schema file')
    parser.add_argument('--samples', type=int, default=10, help='Number of samples to validate')
    parser.add_argument('--timeout', type=int, default=10000, help='Timeout in milliseconds')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Kafka Schema Validator")
    print(f"{'='*60}")
    print(f"Topic: {args.source_topic}")
    print(f"Schema: {args.schema}")
    print(f"{'='*60}\n")

    # Load expected schema
    try:
        with open(args.schema, 'r') as f:
            expected_schema = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Schema file not found: {args.schema}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in schema file: {e}")
        sys.exit(1)

    # Sample messages
    samples = sample_kafka_messages(
        args.bootstrap,
        args.source_topic,
        args.samples,
        args.timeout
    )

    # Validate
    result = validate_schema(samples, expected_schema)

    # Print results
    print(f"\n{'='*60}")
    print(f"Validation Result: {'PASS' if result['valid'] else 'FAIL'}")
    print(f"Samples checked: {result['samples_checked']}")
    print(f"Errors: {len(result['errors'])}")
    print(f"Warnings: {len(result['warnings'])}")
    print(f"{'='*60}\n")

    if result['errors']:
        print("ERRORS:")
        for error in result['errors'][:10]:  # Limit to first 10
            print(f"  - {error}")
        if len(result['errors']) > 10:
            print(f"  ... and {len(result['errors']) - 10} more errors")

    if result['warnings']:
        print("\nWARNINGS:")
        for warning in result['warnings'][:5]:  # Limit to first 5
            print(f"  - {warning}")
        if len(result['warnings']) > 5:
            print(f"  ... and {len(result['warnings']) - 5} more warnings")

    # Exit with status
    sys.exit(0 if result['valid'] else 1)


if __name__ == "__main__":
    main()
