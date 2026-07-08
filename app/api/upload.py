from datetime import datetime
from pathlib import Path
from shutil import copyfileobj

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.daily_user import DailyUser
from app.models.deleted_user import DeletedUser
from app.models.upload import Upload
from app.services.comparison import find_deleted_users
from app.services.excel_reader import read_sap_user_export


router = APIRouter(prefix="/upload", tags=["Upload"])
UPLOAD_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


def parse_upload_date(upload_date: str | None, filename: str) -> datetime:
    if upload_date:
        return datetime.strptime(upload_date, "%Y-%m-%d")

    parts = filename.split("_")
    for part in parts:
        if len(part) == 8 and part.isdigit():
            return datetime.strptime(part, "%Y%m%d")

    return datetime.utcnow()


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_excel(
    file: UploadFile = File(...),
    upload_date: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx and .xls Excel files are allowed",
        )

    UPLOAD_DIR.mkdir(exist_ok=True)
    saved_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    saved_path = UPLOAD_DIR / saved_name

    with saved_path.open("wb") as output_file:
        copyfileobj(file.file, output_file)

    try:
        users = read_sap_user_export(saved_path)
        parsed_upload_date = parse_upload_date(upload_date, file.filename or saved_name)
    except ValueError as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    previous_upload = db.scalar(
        select(Upload).order_by(Upload.upload_date.desc(), Upload.id.desc()).limit(1)
    )
    previous_users: list[DailyUser] = []
    if previous_upload:
        previous_users = list(
            db.scalars(
                select(DailyUser)
                .where(DailyUser.upload_id == previous_upload.id)
                .order_by(DailyUser.username)
            )
        )

    current_upload = Upload(
        file_name=saved_name,
        upload_date=parsed_upload_date,
        total_users=len(users),
    )
    db.add(current_upload)
    db.flush()

    db.add_all(
        DailyUser(
            upload_id=current_upload.id,
            username=user["username"],
            category=user["category"],
        )
        for user in users
    )

    deleted_users = find_deleted_users(previous_users, users) if previous_upload else []
    if previous_upload:
        db.add_all(
            DeletedUser(
                username=user.username,
                category=user.category,
                deleted_date=parsed_upload_date,
                last_seen_date=previous_upload.upload_date,
                previous_upload_id=previous_upload.id,
                current_upload_id=current_upload.id,
            )
            for user in deleted_users
        )

    db.add(
        AuditLog(
            action="excel_upload",
            description=(
                f"Uploaded {file.filename}; saved {len(users)} users and "
                f"detected {len(deleted_users)} deleted users."
            ),
        )
    )
    db.commit()

    return {
        "message": "Excel uploaded successfully",
        "upload_id": current_upload.id,
        "total_users": len(users),
        "deleted_users": len(deleted_users),
        "upload_date": parsed_upload_date.date().isoformat(),
    }
