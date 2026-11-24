"""The InferenceService template is filled from the watcher's environment and arguments."""

import re
from pathlib import Path
from string import Template

import yaml

DIR = Path(__file__).resolve().parents[3] / "services" / "model-lifecycle" / "serving-watcher"


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\$\{(\w+)\}", text))


def test_template_placeholders_are_all_supplied_by_the_watcher():
    template = (DIR / "isvc-template-serverless.yaml").read_text(encoding="utf-8")
    code = (DIR / "watcher.py").read_text(encoding="utf-8")
    supplied = set(re.findall(r"^\s+([A-Z_]+)=", code[code.index("template.substitute("):], flags=re.M))
    missing = _placeholders(template) - supplied
    assert not missing, f"watcher.py does not pass {sorted(missing)} to template.substitute()"


def test_template_renders_to_valid_yaml_with_the_shared_addresses():
    template = (DIR / "isvc-template-serverless.yaml").read_text(encoding="utf-8")
    values = {name: f"value-of-{name}" for name in _placeholders(template)}
    values["SERVING_MINIO_URL"] = "http://minio.test:9000"
    values["FEAST_REDIS_HOST"] = "redis.test"
    isvc = yaml.safe_load(Template(template).substitute(values))
    env = {e["name"]: e.get("value") for e in isvc["spec"]["predictor"]["containers"][0]["env"]}
    assert env["AWS_S3_ENDPOINT"] == "http://minio.test:9000"
    assert env["FEAST_S3_ENDPOINT_URL"] == "http://minio.test:9000"
    assert env["SCORING_FEAST_REDIS_URL"] == "redis.test:6379"
