import re
from fastapi import HTTPException, status
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import (
    create_access_token,
    find_user_by_email,
    get_current_user,
    hash_password,
    normalize_email,
    verify_password,
)
from app.core.database import get_db
from app.models.app_user import AppUser
from app.models.login_event import LoginEvent


router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str


def serialize_user(user: AppUser) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


def log_login_event(db: Session, email: str, success: bool, reason: str, user: AppUser | None = None) -> None:
    db.add(
        LoginEvent(
            user_id=user.id if user else None,
            email=normalize_email(email),
            success=success,
            reason=reason,
        )
    )


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    email = normalize_email(payload.email)
    user = find_user_by_email(db, email)
    if not user:
        log_login_event(db, email, False, "Email not allowed")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        log_login_event(db, email, False, "Blocked user", user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is blocked",
        )

    if not verify_password(payload.password, user.password_hash):
        log_login_event(db, email, False, "Invalid password", user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user.last_login_at = datetime.utcnow()
    log_login_event(db, email, True, "Success", user)
    db.commit()

    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@router.get("/me")
def get_me(user: AppUser = Depends(get_current_user)) -> dict[str, object]:
    return {"user": serialize_user(user)}

PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$"
)

@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not PASSWORD_REGEX.match(payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Password must be at least 8 characters long and contain at least "
                "one uppercase letter, one lowercase letter, one number, and one special character."
            ),
        )

    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)

    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": serialize_user(user),
    }
