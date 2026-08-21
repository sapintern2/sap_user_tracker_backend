import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, dashboard, deleted_users, history, reports, upload
from app.core.auth import require_ready_user
from app.core.config import get_settings
from app.core.database import SessionLocal, check_database_connection, create_database_tables


settings = get_settings()
logger = logging.getLogger(__name__)


def sync_sap_exports_in_background() -> None:
    """Run a non-interactive folder scan using its own database session."""
    with SessionLocal() as db:
        result = upload.sync_exports_from_folder(db, raise_when_nothing_to_sync=False)
        if result:
            logger.info("Automatically synced %s SAP export file(s).", result["uploaded_count"])


async def watch_sap_export_folder() -> None:
    while True:
        try:
            await asyncio.to_thread(sync_sap_exports_in_background)
        except Exception:
            logger.exception("Automatic SAP export sync failed.")
        await asyncio.sleep(max(settings.sap_export_auto_sync_interval_seconds, 10))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_database_tables()
    sync_task = None
    if settings.sap_export_watch_folder and settings.sap_export_auto_sync_enabled:
        sync_task = asyncio.create_task(watch_sap_export_folder())
    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
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
