"""Pydantic schemas for scoring I/O."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Optional, Any


class ScoreRequest(BaseModel):
    features: Dict[str, Any] = Field(
        ..., description="Feature map (supports numeric + categorical values)"
    )
    user_id: Optional[int] = Field(default=None, description="Optional user id for logging")


class ScoreByIdRequest(BaseModel):
    sk_id_curr: Any = Field(..., description="Customer/application id for Feast lookup")
    user_id: Optional[int] = Field(default=None, description="Optional user id for logging")


class ScoreResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())
    probability: float
    decision: str
    threshold: float
    model_name: str
    model_version: Optional[str] = None
