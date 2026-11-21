"""
Custom UDFs for handling Debezium CDC data transformations in PyFlink.
These functions mirror the sophisticated data handling from the Python demo script.
"""

import base64
from datetime import date, timedelta
from typing import Optional

from pyflink.table.udf import udf
from pyflink.table.types import DataTypes

from application_transforms import days_employed


@udf(result_type=DataTypes.DOUBLE())
def decode_decimal_base64(base64_str: str, scale: int) -> Optional[float]:
    """
    Decode Debezium decimal field from base64 string.
    
    Args:
        base64_str: Base64 encoded decimal value from Debezium
        scale: Number of decimal places
    
    Returns:
        Decoded decimal value as float, or None if decoding fails
    """
    if not base64_str or scale is None:
        return None
    try:
        raw = base64.b64decode(base64_str)
        # Two's complement big-endian integer
        unscaled = int.from_bytes(raw, byteorder="big", signed=True)
        return float(unscaled) / (10 ** int(scale))
    except Exception:
        return None


@udf(result_type=DataTypes.DOUBLE())
def safe_parse_decimal(value_str: str) -> Optional[float]:
    """
    Safely parse a decimal value that might be a number string or base64 encoded.
    
    Args:
        value_str: String representation of decimal value
    
    Returns:
        Parsed decimal value as float, or None if parsing fails
    """
    if not value_str:
        return None
    try:
        # Try direct float conversion first
        return float(value_str)
    except ValueError:
        # Could be base64 encoded, but without scale info we can't decode
        # In production, you'd need schema metadata to get the scale
        return None


def _date_from_days_since_epoch(days: int) -> Optional[date]:
    """Helper (non-UDF) to convert days since epoch to date.
    Kept as a plain function so other UDFs can call it without embedding
    a UDF object (which is not picklable by cloudpickle).
    """
    if days is None:
        return None
    try:
        return date(1970, 1, 1) + timedelta(days=int(days))
    except Exception:
        return None


@udf(result_type=DataTypes.INT())
def calculate_days_birth(birth_date_str: str, created_at_str: str) -> Optional[int]:
    """
    Calculate days_birth field (negative days from birth to application).
    Handles both ISO date strings and integer days since epoch.
    
    Args:
        birth_date_str: Birth date as string (ISO format or days since epoch)
        created_at_str: Application creation timestamp
    
    Returns:
        Days between birth and application (typically negative)
    """
    if not birth_date_str or not created_at_str:
        return None
    
    try:
        from dateutil import parser as dtparser
        
        # Parse created_at
        created_at = dtparser.parse(created_at_str).date()
        
        # Handle birth_date - could be ISO string or integer days
        if birth_date_str.isdigit() or (birth_date_str.startswith('-') and birth_date_str[1:].isdigit()):
            # Integer days since epoch
            birth_date = _date_from_days_since_epoch(int(birth_date_str))
        else:
            # ISO string format
            birth_date = dtparser.parse(birth_date_str).date()
        
        if birth_date and created_at:
            return (birth_date - created_at).days
        return None
    except Exception:
        return None


@udf(result_type=DataTypes.INT())
def calculate_days_employed(employment_start_str: str, created_at_str: str) -> Optional[int]:
    """DAYS_EMPLOYED as in training: <= 0 while employed, 365243 when not employed (E2, F-01)."""
    return days_employed(employment_start_str, created_at_str)


@udf(result_type=DataTypes.INT())
def document_flag(document_id: str) -> int:
    """
    Convert document ID to binary flag (1 if exists and not empty, 0 otherwise).
    
    Args:
        document_id: Document identifier string
    
    Returns:
        1 if document exists and is not empty, 0 otherwise
    """
    return 1 if document_id and len(document_id.strip()) > 0 else 0
