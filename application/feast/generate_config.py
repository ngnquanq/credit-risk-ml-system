"""
Generate Feast feature_store.yaml from environment variables to avoid hardcoding.

Env vars:
- FEAST_PROJECT (default: hc)
- FEAST_REGISTRY_PATH (default: data/registry.db)
- FEAST_REDIS_URL (default: redis://localhost:6379/0)
"""

import os


def generate(path: str = "feature_store.yaml") -> None:
    project = os.getenv("FEAST_PROJECT", "hc")
    registry = os.getenv("FEAST_REGISTRY_PATH", "data/registry.db")
    redis_url = os.getenv("FEAST_REDIS_URL", "localhost:6380")

    content = f"""project: {project}
registry: {registry}
provider: local
online_store:
  type: redis
  connection_string: {redis_url}
entity_key_serialization_version: 2
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    generate()

