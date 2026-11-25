"""Kafka topic names are defined once, in contracts/topics/topics.env.

Manifests and scripts read them from the shared-topics ConfigMap or from that file. Python code and the
Flink Dockerfile keep local defaults, so those must at least spell a real topic.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_FILE = ROOT / "contracts/topics/topics.env"
TOPICS = {k: v for k, _, v in (l.partition("=") for l in REGISTRY_FILE.read_text().splitlines() if l.startswith("TOPIC_"))}
VALUES = set(TOPICS.values())
LITERAL = re.compile(r"\bhc\.[a-z_]+(?:\.[a-z_]+)*")
SCANNED = ["services", "platform/foundation", "platform/data", "platform/ml/k8s/knative", "scripts", "tests", "contracts"]
SKIP_PARTS = {"charts", "kubeflow", "node_modules", "reports"}
# Not written out as topic names: the generated Kubeflow file, and the Debezium topic prefix (hc.applications + schema.table).
GENERATED = {"services/model-lifecycle/pipeline/training_pipeline.yaml"}
# Feature definitions name the topic that produces each group (documentation the catalog already carries).
CATALOG = "contracts/feature_catalog/definitions/"


def _files(suffixes):
    for base in SCANNED:
        for path in (ROOT / base).rglob("*"):
            if path.is_file() and path.suffix in suffixes and not SKIP_PARTS & set(path.parts):
                rel = str(path.relative_to(ROOT))
                if rel not in GENERATED and not rel.startswith(CATALOG) and path != REGISTRY_FILE and not rel.startswith("tests/unit/infra/test_topics"):
                    yield rel, path.read_text(encoding="utf-8", errors="ignore")


def _is_known(name: str) -> bool:
    return name in VALUES or any(v.startswith(name + ".") for v in VALUES)


def test_every_topic_spelled_in_code_or_manifests_exists():
    unknown = {(rel, m) for rel, text in _files({".py", ".yaml", ".yml", ".sh"}) for m in LITERAL.findall(text) if not _is_known(m)}
    assert not unknown, f"not in contracts/topics/topics.env: {sorted(unknown)}"


def test_manifests_and_scripts_do_not_write_a_topic_name_out():
    written = {rel: sorted({m for m in LITERAL.findall(text) if m in VALUES}) for rel, text in _files({".yaml", ".yml", ".sh"})}
    written = {f: t for f, t in written.items() if t}
    assert not written, f"read these from the shared-topics ConfigMap (contracts/topics): {written}"


def test_topic_keys_are_unique_and_prefixed():
    assert len(VALUES) == len(TOPICS) and all(k.startswith("TOPIC_") for k in TOPICS)
