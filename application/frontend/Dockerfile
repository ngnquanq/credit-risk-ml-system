FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install streamlit and other frontend dependencies
RUN pip install streamlit requests python-dotenv

# Copy requirements from application directory (for any shared dependencies)
COPY requirements-api.txt ./requirements-api.txt
RUN pip install -r requirements-api.txt

# Copy frontend files
COPY frontend/ .

EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]