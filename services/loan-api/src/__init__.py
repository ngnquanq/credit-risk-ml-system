"""Credit risk decisioning platform: application code.

Each deployable (API, consumers, scoring, Feast repo, Flink jobs, frontend)
is run with PYTHONPATH=application and imports its siblings by top-level name
(for example ``from core.config import settings``).
"""
