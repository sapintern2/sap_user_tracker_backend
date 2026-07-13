from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, dashboard, deleted_users, history, reports, upload
from app.core.auth import require_ready_user
from app.core.config import get_settings
from app.core.database import check_database_connection, create_database_tables


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_database_tables()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
protected = [Depends(require_ready_user)]

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(upload.router, dependencies=protected)
app.include_router(dashboard.router, dependencies=protected)
app.include_router(deleted_users.router, dependencies=protected)
app.include_router(history.router, dependencies=protected)
app.include_router(reports.router, dependencies=protected)


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
