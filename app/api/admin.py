from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.auth import hash_password, normalize_email, require_admin_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.time import sri_lanka_day_range, sri_lanka_iso, sri_lanka_now
from app.models.app_user import AppUser
from app.models.login_event import LoginEvent


router = APIRouter(prefix="/admin", tags=["Admin"])


class CreateUserRequest(BaseModel):
    name: str
    email: str


def serialize_admin_user(user: AppUser) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_active": user.is_active,
        "failed_login_attempts": user.failed_login_attempts,
        "must_change_password": user.must_change_password,
        "last_login_at": sri_lanka_iso(user.last_login_at),
        "created_at": sri_lanka_iso(user.created_at),
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, list[dict[str, object]]]:
    users = db.scalars(
        select(AppUser)
        .where(AppUser.deleted_at.is_(None))
        .order_by(AppUser.role, AppUser.name)
    ).all()
    return {"users": [serialize_admin_user(user) for user in users]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    email = normalize_email(payload.email)
    existing = db.scalar(select(AppUser).where(AppUser.email == email))
    if existing:
        if existing.deleted_at:
            existing.name = payload.name.strip()
            existing.role = "user"
            existing.password_hash = hash_password(get_settings().auth_default_password)
            existing.must_change_password = True
            existing.is_active = True
            existing.failed_login_attempts = 0
            existing.deleted_at = None
            db.commit()
            db.refresh(existing)
            return {"user": serialize_admin_user(existing)}

        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = AppUser(
        email=email,
        name=payload.name.strip(),
        role="user",
        password_hash=hash_password(get_settings().auth_default_password),
        must_change_password=True,
        is_active=True,
        failed_login_attempts=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": serialize_admin_user(user)}


@router.post("/users/{user_id}/block")
def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    user = db.get(AppUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot block self")

    user.is_active = False
    db.commit()
    db.refresh(user)
    return {"user": serialize_admin_user(user)}


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    user = db.get(AppUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
    user.failed_login_attempts = 0
    db.commit()
    db.refresh(user)
    return {"user": serialize_admin_user(user)}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    user = db.get(AppUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(get_settings().auth_default_password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.is_active = True
    db.commit()
    db.refresh(user)
    return {"user": serialize_admin_user(user)}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    user = db.get(AppUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot delete self")

    user.is_active = False
    user.deleted_at = sri_lanka_now()
    db.commit()
    return {"deleted": True, "user_id": user_id}


@router.get("/logins")
def list_login_events(
    login_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, list[dict[str, object]]]:
    statement = select(LoginEvent)
    if login_date:
        day_start, day_end = sri_lanka_day_range(login_date)
        statement = statement.where(
            LoginEvent.created_at >= day_start,
            LoginEvent.created_at <= day_end,
        )

    events = db.scalars(
        statement.order_by(LoginEvent.created_at.desc()).limit(200)
    ).all()
    return {
        "events": [
            {
                "id": event.id,
                "email": event.email,
                "name": event.user.name if event.user else None,
                "success": event.success,
                "reason": event.reason,
                "created_at": sri_lanka_iso(event.created_at),
            }
            for event in events
        ]
    }


@router.delete("/logins")
def clear_login_events(
    login_date: date = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, object]:
    day_start, day_end = sri_lanka_day_range(login_date)
    login_result = db.execute(
        delete(LoginEvent).where(
            LoginEvent.created_at >= day_start,
            LoginEvent.created_at <= day_end,
        )
    )
    user_result = db.execute(
        update(AppUser)
        .where(
            AppUser.last_login_at >= day_start,
            AppUser.last_login_at <= day_end,
        )
        .values(last_login_at=None)
    )
    db.commit()
    return {
        "deleted": login_result.rowcount or 0,
        "last_login_cleared": user_result.rowcount or 0,
        "login_date": login_date.isoformat(),
    }
