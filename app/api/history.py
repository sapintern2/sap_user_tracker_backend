from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.deleted_user import DeletedUser
from app.models.upload import Upload


router = APIRouter(prefix="/history", tags=["Upload History"])
UPLOAD_DIR = Path("uploads")


@router.get("/uploads")
def get_upload_history(db: Session = Depends(get_db)) -> dict[str, list[dict[str, int | str]]]:
    deleted_counts = (
        select(
            DeletedUser.current_upload_id.label("upload_id"),
            func.count(DeletedUser.id).label("deleted_count"),
        )
        .group_by(DeletedUser.current_upload_id)
        .subquery()
    )

    rows = db.execute(
        select(
            Upload,
            func.coalesce(deleted_counts.c.deleted_count, 0).label("deleted_count"),
        )
        .outerjoin(deleted_counts, deleted_counts.c.upload_id == Upload.id)
        .order_by(Upload.upload_date.desc(), Upload.id.desc())
    ).all()

    return {
        "uploads": [
            {
                "id": upload.id,
                "file_name": upload.file_name,
                "upload_date": upload.upload_date.date().isoformat(),
                "total_users": upload.total_users,
                "deleted_users": deleted_count,
                "created_at": upload.created_at.isoformat(),
            }
            for upload, deleted_count in rows
        ]
    }


@router.get("/uploads/{upload_id}/download")
def download_uploaded_file(upload_id: int, db: Session = Depends(get_db)) -> FileResponse:
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    file_path = UPLOAD_DIR / upload.file_name
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file is missing from the uploads folder",
        )

    return FileResponse(
        path=file_path,
        filename=upload.file_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
