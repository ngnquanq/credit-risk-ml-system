"""
SQLAlchemy base model with consistent naming conventions.
"""

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData


class Base(DeclarativeBase):
    """
    Base class for all database models.
    
    Provides consistent naming conventions for database constraints:
    - Indexes: ix_column_name
    - Unique constraints: uq_table_column
    - Check constraints: ck_table_constraint_name
    - Foreign keys: fk_table_column_referenced_table
    - Primary keys: pk_table
    """
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s", 
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s"
        }
    )