from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import hash_password, normalize_email, require_admin_user
from app.core.config import get_settings
from app.core.database import get_db
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
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, list[dict[str, object]]]:
    users = db.scalars(select(AppUser).order_by(AppUser.role, AppUser.name)).all()
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = AppUser(
        email=email,
        name=payload.name.strip(),
        role="user",
        password_hash=hash_password(get_settings().auth_default_password),
        must_change_password=True,
        is_active=True,
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
    if not user:
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
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
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
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(get_settings().auth_default_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)
    return {"user": serialize_admin_user(user)}


@router.get("/logins")
def list_login_events(
    login_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin_user),
) -> dict[str, list[dict[str, object]]]:
    statement = select(LoginEvent)
    if login_date:
        sri_lanka_offset = timedelta(hours=5, minutes=30)
        local_start = datetime.combine(login_date, time.min)
        local_end = datetime.combine(login_date, time.max)
        utc_start = local_start - sri_lanka_offset
        utc_end = local_end - sri_lanka_offset
        statement = statement.where(
            LoginEvent.created_at >= utc_start,
            LoginEvent.created_at <= utc_end,
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
                "created_at": event.created_at.replace(tzinfo=timezone.utc).isoformat(),
            }
            for event in events
        ]
    }
