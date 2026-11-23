"""
Credit Risk Scoring Service (BentoML)

This package contains a production-ready BentoML service for real-time
credit risk scoring. It follows MLOps best practices:
- Clear input/output contracts via Pydantic schemas
- Config via environment variables (12-factor friendly)
- Separated concerns: loading, preprocessing, inference, logging
- Health/Readiness endpoints and structured logging
- Extensible hooks for feature store (Feast) and model registry (MLflow)
"""

__all__ = [
    "service",
]

