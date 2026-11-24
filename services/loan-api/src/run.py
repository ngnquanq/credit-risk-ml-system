import os

import uvicorn
from core.config import settings
from core.log_setup import setup_logging

if __name__ == "__main__":
    setup_logging("api")
    uvicorn.run(
        "entrypoints.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_config=None,  # uvicorn's own handlers would bypass the shared log line
        log_level=(os.getenv("LOG_LEVEL") or settings.log_level).lower(),
    )
