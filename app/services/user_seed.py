from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.allowed_users import ALLOWED_USERS
from app.core.auth import hash_password, normalize_email
from app.core.config import get_settings
from app.models.app_user import AppUser


def seed_allowed_users(db: Session) -> None:
    settings = get_settings()
    default_password_hash = hash_password(settings.auth_default_password)
    admin_email = normalize_email(settings.auth_admin_email)

    for allowed_user in ALLOWED_USERS:
        email = normalize_email(allowed_user["email"])
        role = "admin" if email == admin_email else "user"
        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if user:
            if user.deleted_at:
                continue

            user.name = allowed_user["name"]
            user.role = role
            user.failed_login_attempts = user.failed_login_attempts or 0
            if user.must_change_password:
                user.password_hash = default_password_hash
            continue

        db.add(
            AppUser(
                email=email,
                name=allowed_user["name"],
                role=role,
                password_hash=default_password_hash,
                must_change_password=True,
                is_active=True,
                failed_login_attempts=0,
            )
        )

    db.commit()
