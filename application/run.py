import uvicorn
from core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "entrypoints.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )