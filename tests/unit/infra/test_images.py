"""Images are tagged in one place (platform/config/images); manifests name them without a tag and never use :latest."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPONENT = yaml.safe_load((ROOT / "platform/config/images/kustomization.yaml").read_text())
TAGS = {i["name"]: i["newTag"] for i in COMPONENT["images"]}
SCANNED = ["services", "platform/foundation/identity", "platform/data", "portals/deploy"]


def _image_lines():
    for base in SCANNED:
        for path in (ROOT / base).rglob("*.yaml"):
            if {"charts", "kubeflow", "ha"} & set(path.parts) or path.name in {"training_pipeline.yaml"}:
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"\s*image:\s*([^\s#]+)", line)
                if m and not m.group(1).startswith("$"):
                    yield str(path.relative_to(ROOT)), m.group(1)


def test_no_manifest_uses_a_latest_tag():
    offenders = [(f, i) for f, i in _image_lines() if i.endswith(":latest")]
    assert not offenders, f"{offenders}: pin the image in platform/config/images instead"


def test_images_without_a_tag_are_tagged_by_the_component():
    untagged = {i for _, i in _image_lines() if ":" not in i.rsplit("/", 1)[-1] and "@" not in i}
    missing = untagged - set(TAGS)
    assert not missing, f"{sorted(missing)} have no tag in the manifest and none in platform/config/images"


def test_the_makefile_builds_with_the_tag_the_manifests_expect():
    makefile = (ROOT / "Makefile").read_text()
    default = re.search(r"^IMAGE_TAG \?= (\S+)", makefile, re.M).group(1)
    for name in ("ngnquanq/credit-risk-api", "ngnquanq/credit-risk-consumers", "flink-pyflink", "dbt-clickhouse"):
        assert TAGS[name] == default, f"{name}: component says {TAGS[name]}, Makefile builds {default}"
        assert f"-t {name}:$(IMAGE_TAG)" in makefile, f"the Makefile does not tag {name} with IMAGE_TAG"
