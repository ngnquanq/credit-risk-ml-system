"""Pydantic schemas for scoring I/O."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Optional


class ScoreRequest(BaseModel):
    features: Dict[str, float] = Field(..., description="Model-ready numeric features")
    user_id: Optional[int] = Field(default=None, description="Optional user id for logging")


class ScoreResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    probability: float
    decision: str
    threshold: float
    model_name: str
    model_version: Optional[str] = None
