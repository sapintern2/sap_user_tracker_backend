import os
import re
from datetime import datetime
from pathlib import Path
from shutil import copy2, copyfileobj

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.classification_movement import ClassificationMovement
from app.models.daily_user import DailyUser
from app.models.deleted_user import DeletedUser
from app.models.upload import Upload
from app.models.new_user import NewUser
from app.services.comparison import find_classification_movements, find_deleted_users, find_new_users
from app.services.excel_reader import read_sap_user_export

router = APIRouter(prefix="/upload", tags=["Upload"])
UPLOAD_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
EXPORT_FILENAME_PATTERN = re.compile(r"EXPORT_(\d{8})_(\d{6})", re.IGNORECASE)


def parse_export_datetime(filename: str) -> datetime | None:
    match = EXPORT_FILENAME_PATTERN.search(filename)
    if not match:
        return None

    date_part, time_part = match.groups()
    return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")


def parse_upload_date(upload_date: str | None, filename: str) -> datetime:
    if upload_date:
        return datetime.strptime(upload_date, "%Y-%m-%d")

    export_datetime = parse_export_datetime(filename)
    if export_datetime:
        return export_datetime

    return datetime.utcnow()

def find_export_files_from_folder() -> list[tuple[datetime, Path]]:
    folder_value = get_settings().sap_export_watch_folder
    if not folder_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SAP_EXPORT_WATCH_FOLDER is not configured.",
        )

    folder = Path(folder_value)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured SAP export folder does not exist.",
        )

    export_files: list[tuple[datetime, Path]] = []

    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        export_datetime = parse_export_datetime(file_path.name)
        if not export_datetime:
            continue

        export_files.append((export_datetime, file_path))

    if not export_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No EXPORT_YYYYMMDD_HHMMSS Excel files found in the configured folder.",
        )

    export_files.sort(key=lambda item: item[0])
    return export_files

def get_uploaded_date_keys(db: Session) -> set[str]:
    upload_dates = db.scalars(select(Upload.upload_date)).all()
    return {upload_date.date().isoformat() for upload_date in upload_dates}


def save_upload_result(
    *,
    db: Session,
    source_name: str,
    saved_name: str,
    saved_path: Path,
    parsed_upload_date: datetime,
    audit_action: str,
) -> dict[str, int | str]:
    try:
        users = read_sap_user_export(saved_path)
    except ValueError as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    duplicate_upload = db.scalar(
        select(Upload)
        .where(
            Upload.upload_date >= parsed_upload_date.replace(hour=0, minute=0, second=0, microsecond=0),
            Upload.upload_date <= parsed_upload_date.replace(hour=23, minute=59, second=59, microsecond=999999),
        )
        .limit(1)
    )
    if duplicate_upload:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An upload already exists for this date. Delete the existing latest upload "
                "first if you need to replace it."
            ),
        )

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
            user_id=user.get("user_id"),
            full_name=user.get("full_name"),
            category=user["category"],
        )
        for user in users
    )

    deleted_users = find_deleted_users(previous_users, users) if previous_upload else []
    new_users = find_new_users(previous_users, users) if previous_upload else []
    classification_movements = (
        find_classification_movements(previous_users, users) if previous_upload else []
    )
    if previous_upload:
        db.add_all(
            NewUser(
                username=user["username"],
                user_id=user.get("user_id"),
                full_name=user.get("full_name"),
                category=user["category"],
                added_date=parsed_upload_date,
                previous_upload_id=previous_upload.id,
                current_upload_id=current_upload.id,
            )
            for user in new_users
        )
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
        db.add_all(
            ClassificationMovement(
                username=movement["username"],
                user_id=movement["user_id"],
                full_name=movement["full_name"],
                from_category=movement["from_category"],
                to_category=movement["to_category"],
                movement_date=parsed_upload_date,
                previous_upload_id=previous_upload.id,
                current_upload_id=current_upload.id,
            )
            for movement in classification_movements
        )

    db.add(
        AuditLog(
            action=audit_action,
            description=(
                f"Uploaded {source_name}; saved {len(users)} users and "
                f"detected {len(deleted_users)} deleted users, "
                f"{len(new_users)} new users, and "
                f"{len(classification_movements)} classification movements."
            ),
        )
    )
    db.commit()

    return {
        "message": "Excel uploaded successfully",
        "upload_id": current_upload.id,
        "file_name": source_name,
        "total_users": len(users),
        "deleted_users": len(deleted_users),
        "new_users": len(new_users),
        "classification_movements": len(classification_movements),
        "upload_date": parsed_upload_date.date().isoformat(),
    }


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

    duplicate_upload = db.scalar(
        select(Upload)
        .where(
            Upload.upload_date >= parsed_upload_date.replace(hour=0, minute=0, second=0, microsecond=0),
            Upload.upload_date <= parsed_upload_date.replace(hour=23, minute=59, second=59, microsecond=999999),
        )
        .limit(1)
    )
    if duplicate_upload:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An upload already exists for this date. Delete the existing latest upload "
                "first if you need to replace it."
            ),
        )

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
            user_id=user.get("user_id"),
            full_name=user.get("full_name"),
            category=user["category"],
        )
        for user in users
    )

    deleted_users = find_deleted_users(previous_users, users) if previous_upload else []
    new_users = find_new_users(previous_users, users) if previous_upload else []
    classification_movements = (
        find_classification_movements(previous_users, users) if previous_upload else []
    )
    if previous_upload:
        db.add_all(
            NewUser(
                username=user["username"],
                user_id=user.get("user_id"),
                full_name=user.get("full_name"),
                category=user["category"],
                added_date=parsed_upload_date,
                previous_upload_id=previous_upload.id,
                current_upload_id=current_upload.id,
            )
            for user in new_users
        )
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
        db.add_all(
            ClassificationMovement(
                username=movement["username"],
                user_id=movement["user_id"],
                full_name=movement["full_name"],
                from_category=movement["from_category"],
                to_category=movement["to_category"],
                movement_date=parsed_upload_date,
                previous_upload_id=previous_upload.id,
                current_upload_id=current_upload.id,
            )
            for movement in classification_movements
        )

    db.add(
        AuditLog(
            action="excel_upload",
            description=(
                f"Uploaded {file.filename}; saved {len(users)} users and "
                f"detected {len(deleted_users)} deleted users, "
                f"{len(new_users)} new users, and "
                f"{len(classification_movements)} classification movements."
            ),
        )
    )
    db.commit()

    return {
        "message": "Excel uploaded successfully",
        "upload_id": current_upload.id,
        "total_users": len(users),
        "deleted_users": len(deleted_users),
        "new_users": len(new_users),
        "classification_movements": len(classification_movements),
        "upload_date": parsed_upload_date.date().isoformat(),
    }

@router.post("/latest-from-folder", status_code=status.HTTP_201_CREATED)
def upload_latest_from_folder(db: Session = Depends(get_db)) -> dict[str, int | str | list[str]]:
    export_files = find_export_files_from_folder()
    uploaded_date_keys = get_uploaded_date_keys(db)

    pending_files = [
        (export_datetime, file_path)
        for export_datetime, file_path in export_files
        if export_datetime.date().isoformat() not in uploaded_date_keys
    ]

    if not pending_files:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All SAP export files in the folder are already uploaded.",
        )

    uploaded_results = []

    for export_datetime, export_file in pending_files:
        UPLOAD_DIR.mkdir(exist_ok=True)

        saved_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{export_file.name}"
        saved_path = UPLOAD_DIR / saved_name
        copy2(export_file, saved_path)

        result = save_upload_result(
            db=db,
            source_name=export_file.name,
            saved_name=saved_name,
            saved_path=saved_path,
            parsed_upload_date=export_datetime,
            audit_action="auto_excel_upload",
        )

        uploaded_results.append(result)

    return {
        "message": "SAP export sync completed successfully",
        "uploaded_count": len(uploaded_results),
        "uploaded_files": [result["file_name"] for result in uploaded_results],
        "first_file": uploaded_results[0]["file_name"],
        "last_file": uploaded_results[-1]["file_name"],
        "total_users": uploaded_results[-1]["total_users"],
        "deleted_users": sum(int(result["deleted_users"]) for result in uploaded_results),
        "new_users": sum(int(result["new_users"]) for result in uploaded_results),
        "classification_movements": sum(
            int(result["classification_movements"]) for result in uploaded_results
        ),
        "upload_date": uploaded_results[-1]["upload_date"],
    }
