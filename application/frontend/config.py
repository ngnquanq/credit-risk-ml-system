"""
Frontend configuration loaded from environment variables.
This centralizes settings for easy tracking and reuse.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env (if present)
load_dotenv()

# API base URL for the backend service
API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8001")

# Application display name
APP_NAME: str = os.getenv("APP_NAME", "Home Credit Loan Application")

