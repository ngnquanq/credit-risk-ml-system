"""
Simple database model - matches existing table structure.
"""

from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class LoanApplication(Base):
    """Matches your existing PostgreSQL applications table."""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    application_data = Column(JSONB, nullable=False)
    status = Column(String(50), default="submitted")
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())