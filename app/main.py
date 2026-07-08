from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import check_database_connection


settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "SAP User Tracker API is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
def database_health_check() -> dict[str, str]:
    check_database_connection()
    return {"database": "connected"}
