"""The Kafka address is defined once (platform/config/endpoints/endpoints.env).

Manifests read it from the shared-endpoints ConfigMap. This test fails when a manifest writes the
address out again. Files in PENDING still do; remove each one from the list when it is converted,
so the list only ever shrinks.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LITERAL = "kafka-broker.data-services.svc.cluster.local:9092"
SCANNED = ["services", "platform/core", "platform/data", "portals/deploy"]

# The broker's own definition of where it listens is the source, not a copy.
SOURCE = {"platform/data/k8s/message-broker/01-kafka.yaml"}

# Not converted yet. Each needs its own change (a different variable name, a spec field, or an open edit).
PENDING = {
    "platform/core/k8s/01-api-config.yaml",
    "platform/data/k8s/cdc/01-debezium.yaml",
    "platform/data/k8s/message-broker/02-kafka-ui.yaml",
    "services/loan-api/deploy/09-decision-recorder.yaml",
    "services/scoring/deploy/kafka-dlq-sink.yaml",
    "services/scoring/deploy/kafka-sink.yaml",
    "services/scoring/deploy/kafka-source.yaml",
}


def _files_with_literal() -> set[str]:
    found = set()
    for base in SCANNED:
        for path in (ROOT / base).rglob("*.yaml"):
            if "charts" in path.parts or "kubeflow" in path.parts:
                continue
            if LITERAL in path.read_text(encoding="utf-8", errors="ignore"):
                found.add(str(path.relative_to(ROOT)))
    return found


def test_no_new_manifest_writes_the_kafka_address():
    unexpected = _files_with_literal() - SOURCE - PENDING
    assert not unexpected, (
        f"{sorted(unexpected)} write the Kafka address out. Read KAFKA_BOOTSTRAP_SERVERS from the "
        "shared-endpoints ConfigMap instead (platform/config/endpoints)."
    )


def test_pending_list_has_no_converted_files():
    converted = PENDING - _files_with_literal()
    assert not converted, f"Remove {sorted(converted)} from PENDING: they no longer hard-code the address."


def test_endpoints_env_defines_the_address():
    env = (ROOT / "platform/config/endpoints/endpoints.env").read_text(encoding="utf-8")
    assert f"KAFKA_BOOTSTRAP_SERVERS={LITERAL}" in env
